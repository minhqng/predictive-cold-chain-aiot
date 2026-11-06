"""Manifest parsing and cross-binding validation (B-W02-05).

Implements the W01 artifact-convention shapes and the audit bindings W02
needs (``ml/artifact-convention.md`` §§2–5, §§7, 9):

* parses the §3.1 dataset manifest, the §3.2 split manifest and per-run
  manifests (run-record metadata) from dicts, YAML text or a file path;
* rejects duplicate YAML keys (yaml anchors silently overriding a key is
  the classic manifest corruption), unknown fields, wrong identifier
  patterns (§2: ``CG-DATA-…``/``CG-SPLIT-…``/``CG-HW-…``/``CG-CAL-…``/
  ``CG-S<s>-<arm>-<serial>``), non-canonical statuses and provenance gaps;
* lock discipline (§4): ``locked``/``final`` manifests must carry a
  ``content_sha256``; ``locked_test.opened_at`` without ``frozen_at``, or
  earlier than ``frozen_at``, is a contradiction (§3.2, ``03` §49`);
* cross-binds (§9, restricted to the W02 pipeline): **B1**
  (``split.dataset_id`` resolves and partition union == ``source_runs``),
  **B5** (single hardware lineage value), **B7** (synthetic-flag
  propagation consistency), plus split↔run-record resolution with
  pair-lineage and excluded-run checks.

Not in scope (W02 non-goals): no registry service, no hash recomputation
against stored artifacts (presence + format discipline only — the
recompute/audit checker is SCHEDULED_DEBT per §9), no model/feature/analysis
manifest classes (§3.3–§3.5).
"""

from __future__ import annotations

import copy as _copy
import datetime as _dt
import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ManifestError
from .observations import SUPPORTED_SCHEMA_VERSIONS, parse_event_time

__all__ = [
    "DatasetManifest",
    "SplitManifest",
    "RunRecordManifest",
    "ExcludedRunEntry",
    "parse_dataset_manifest",
    "parse_split_manifest",
    "parse_run_manifest",
    "parse_run_manifests",
    "bind_split_to_dataset",
    "bind_dataset_to_run_records",
    "bind_split_to_run_records",
    "canonical_manifest_yaml",
    "manifest_content_sha256",
    "DATASET_ID_PATTERN",
    "SPLIT_ID_PATTERN",
    "RUN_ID_PATTERN",
    "HARDWARE_ID_PATTERN",
    "CALIBRATION_ID_PATTERN",
]

# -- canonical identifier patterns (convention §2; extensions are provisional
#    and may only be recorded via §10 change control, never invented here) ----
DATASET_ID_PATTERN = re.compile(r"^CG-DATA-\d+$")
SPLIT_ID_PATTERN = re.compile(r"^CG-SPLIT-\d+$")
RUN_ID_PATTERN = re.compile(r"^CG-S(\d)+-[A-Za-z0-9]+-[A-Za-z0-9]+$")
HARDWARE_ID_PATTERN = re.compile(r"^CG-HW-\d+$")
CALIBRATION_ID_PATTERN = re.compile(r"^CG-CAL-\d+$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

SCENARIO_IDS: tuple[str, ...] = ("S1", "S2", "S3", "S4", "S5", "S6")
STATUSES: tuple[str, ...] = ("draft", "locked", "final")
LOCKED_STATUSES: tuple[str, ...] = ("locked", "final")
PARTITIONS: tuple[str, ...] = ("train", "validation", "test")

_DATASET_KEYS: set[str] = {
    "dataset_id",
    "source_runs",
    "hardware_configs",
    "schema_version",
    "calibration_ids",
    "export_query_hash",
    "created_at",
    "created_by",
    "git_commit",
    "status",
    "content_sha256",
    "synthetic",
}

_SPLIT_KEYS: set[str] = {
    "split_id",
    "dataset_id",
    "train_runs",
    "validation_runs",
    "test_runs",
    "grouping",
    "hardware_lineage",
    "locked_test",
    "controller_context",
    "pair_lineage",
    "excluded_runs",
    "split_seed",
    "created_at",
    "created_by",
    "git_commit",
    "status",
    "content_sha256",
}
# W02 additions over the §3.2 minimum shape (05B §12 split-manifest plan:
# excluded-run ledger + pair lineage are recorded for audit).
_SPLIT_EXTRA_KEYS_RECORDED = ("pair_lineage", "excluded_runs")

_RUN_KEYS: set[str] = {
    "run_id",
    "scenario_id",
    "controller_id",
    "pair_id",
    "device_id",
    "hardware_config_id",
    "firmware_version",
    "calibration_id",
    "schema_version",
    "is_valid",
    "invalid_reason",
    "synthetic",
    "seed",
    "boots",
    "start_time",
    "end_time",
    "note",
}

_BOOT_KEYS: set[str] = {"boot_id", "n_observations", "first_time", "last_time"}
_PAIR_LINEAGE_KEYS: set[str] = {"pair_id", "run_ids", "partition"}
_EXCLUDED_KEYS: set[str] = {"run_id", "reason"}


# -- strict YAML loading ------------------------------------------------------


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys and merge aliases."""


def _construct_mapping_no_duplicates(
    loader: yaml.Loader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            hash(key)
        except TypeError as exc:
            raise ManifestError(
                f"YAML mapping uses an unhashable key "
                f"(line {key_node.start_mark.line + 1}): {exc}"
            ) from exc
        if key in mapping:
            raise ManifestError(
                f"duplicate YAML key {key!r} (line {key_node.start_mark.line + 1}) — "
                "silently overriding a manifest field invalidates the artifact "
                "(artifact-convention §10 anti-drift discipline)"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping_no_duplicates
)


def _load_manifest(
    source: dict[str, Any] | str | Path, *, artifact_kind: str
) -> dict[str, Any]:
    """Load a manifest from a dict, YAML text, or a YAML file path.

    A ``str`` with no newline that names an existing file is read from
    disk; any other string is treated as YAML text.
    """
    if isinstance(source, dict):
        return _copy.deepcopy(source)
    if isinstance(source, (str, Path)):
        text: str
        origin: str
        if isinstance(source, Path):
            origin = str(source)
            try:
                text = source.read_text(encoding="utf-8")
            except OSError as exc:
                raise ManifestError(
                    f"cannot read {artifact_kind} manifest file {origin}: {exc}"
                ) from exc
        elif "\n" not in source and Path(source).is_file():
            origin = source
            text = Path(source).read_text(encoding="utf-8")
        else:
            origin = "<yaml-text>"
            text = source
        try:
            loaded = yaml.load(text, Loader=_StrictLoader)
        except yaml.YAMLError as exc:
            raise ManifestError(
                f"{artifact_kind} manifest is not valid YAML ({origin}): {exc}"
            ) from exc
        if not isinstance(loaded, dict):
            raise ManifestError(
                f"{artifact_kind} manifest ({origin}) must be a YAML mapping, "
                f"got {type(loaded).__name__}"
            )
        return loaded
    raise ManifestError(
        f"unsupported {artifact_kind} manifest input {type(source).__name__}; "
        "supply a dict, YAML text, or a file path"
    )


# -- validation primitives ----------------------------------------------------


def _reject_unknown_keys(payload: Mapping[str, Any], allowed: set[str], *, kind: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ManifestError(
            f"{kind} manifest carries unknown fields {unknown} — allowlisted fields for "
            f"{kind} manifests are {sorted(allowed)} (artifact-convention §3)"
        )


def _require_present(payload: Mapping[str, Any], key: str, *, kind: str, anchor: str) -> Any:
    if key not in payload:
        raise ManifestError(
            f"{kind} manifest is missing required field {key!r} "
            f"(artifact-convention {anchor})"
        )
    return payload[key]


def _require_nonempty_str(value: Any, field_path: str, *, anchor: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(
            f"{field_path} must be a non-empty string (received: {value!r}; "
            f"anchor: {anchor})"
        )
    return value


def _require_bool(value: Any, field_path: str, *, anchor: str) -> bool:
    if not isinstance(value, bool):
        raise ManifestError(
            f"{field_path} must be an explicit boolean (received: {value!r}; anchor: {anchor})"
        )
    return value


def _require_int(value: Any, field_path: str, *, anchor: str, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ManifestError(
            f"{field_path} must be an integer >= {minimum} (received: {value!r}; "
            f"anchor: {anchor})"
        )
    return value


def _require_pattern(value: Any, field_path: str, pattern: re.Pattern[str], anchor: str) -> str:
    if not isinstance(value, str) or pattern.match(value) is None:
        raise ManifestError(
            f"{field_path} must match the canonical identifier pattern {pattern.pattern!r} "
            f"(received: {value!r}; anchor: {anchor})"
        )
    return value


def _require_rfc3339(
    value: Any, field_path: str, *, anchor: str, allow_none: bool
) -> _dt.datetime | None:
    if value is None and allow_none:
        return None
    if value is None:
        raise ManifestError(
            f"{field_path} must not be null (received: null; anchor: {anchor})"
        )
    try:
        return parse_event_time(value, context=field_path)
    except Exception as exc:
        raise ManifestError(f"{field_path}: {exc} (anchor: {anchor})") from exc


def _require_hash_or_none(value: Any, field_path: str, *, anchor: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or SHA256_PATTERN.match(value) is None:
        raise ManifestError(
            f"{field_path} must be a lowercase sha256 hex digest or null "
            f"(received: {value!r}; anchor: {anchor})"
        )
    return value


def _require_str_list(value: Any, field_path: str, *, anchor: str) -> list[str]:
    if not isinstance(value, list):
        raise ManifestError(
            f"{field_path} must be a YAML list (received: {value!r}; anchor: {anchor})"
        )
    for item in value:
        if not isinstance(item, str):
            raise ManifestError(
                f"{field_path} entries must be strings (received: {item!r}; anchor: {anchor})"
            )
    return value


def _require_lock_content_hash(
    payload: Mapping[str, Any], *, kind: str
) -> str | None:
    status = _require_present(payload, "status", kind=kind, anchor="§4")
    content_sha256 = _require_present(
        payload, "content_sha256", kind=kind, anchor="§5"
    )
    digest = _require_hash_or_none(
        content_sha256, f"{kind}.content_sha256", anchor="§5"
    )
    if status in LOCKED_STATUSES and digest is None:
        raise ManifestError(
            f"{kind} manifest with status {status!r} must carry a content_sha256; "
            f"received {content_sha256!r} (artifact-convention §4/§5: content identity "
            "is recorded at lock time)"
        )
    if status in LOCKED_STATUSES and digest is not None:
        # Presence verification only; recomputation against stored artifacts
        # is the SCHEDULED_DEBT audit checker (artifact-convention §9).
        assert SHA256_PATTERN.match(digest)
    return digest


def _check_lock_test_fields(
    frozen_at_raw: Any,
    opened_at_raw: Any,
    *,
    kind: str,
) -> tuple[_dt.datetime | None, _dt.datetime | None]:
    frozen_at = _require_rfc3339(
        frozen_at_raw, f"{kind}.locked_test.frozen_at", anchor="§3.2 (Doc `03` §49)", allow_none=True
    )
    opened_at = _require_rfc3339(
        opened_at_raw, f"{kind}.locked_test.opened_at", anchor="§3.2 (Doc `03` §49)", allow_none=True
    )
    if opened_at is not None and frozen_at is None:
        raise ManifestError(
            f"{kind}.locked_test: opened_at is set but frozen_at is null — "
            "locked-test run IDs must be frozen before they can be opened "
            f"(received frozen_at={frozen_at_raw!r}, opened_at={opened_at_raw!r}; "
            "anchor: artifact-convention §3.2)"
        )
    if opened_at is not None and frozen_at is not None and opened_at < frozen_at:
        raise ManifestError(
            f"{kind}.locked_test: opened_at {event_or_none(opened_at)} precedes "
            f"frozen_at {event_or_none(frozen_at)} — the frozen-run-ids freeze "
            "happens before the test is opened (artifact-convention §4 / Doc `03` §49)"
        )
    return frozen_at, opened_at


def event_or_none(moment: _dt.datetime | None) -> str:
    from .observations import event_time_to_rfc3339

    return None if moment is None else event_time_to_rfc3339(moment)


# -- parsed artifact payload types -------------------------------------------


@dataclass(frozen=True)
class DatasetManifest:
    """Validated §3.1 dataset-manifest payload."""

    raw: dict[str, Any] = field(repr=False)
    dataset_id: str
    source_runs: tuple[str, ...]
    hardware_configs: tuple[str, ...]
    calibration_ids: tuple[str, ...]
    schema_version: int
    created_at: _dt.datetime
    created_by: str
    git_commit: str
    status: str
    synthetic: bool
    content_sha256: str | None
    export_query_hash: str | None

    @property
    def is_locked_or_final(self) -> bool:
        return self.status in LOCKED_STATUSES


@dataclass(frozen=True)
class SplitManifest:
    """Validated §3.2 split-manifest payload (plus W02 audit extensions)."""

    raw: dict[str, Any] = field(repr=False)
    split_id: str
    dataset_id: str
    train_runs: tuple[str, ...]
    validation_runs: tuple[str, ...]
    test_runs: tuple[str, ...]
    grouping_key: str
    hardware_lineage: str
    frozen_at: _dt.datetime | None
    opened_at: _dt.datetime | None
    controller_context: str
    pair_lineage: tuple[dict[str, Any], ...]
    excluded_runs: tuple["ExcludedRunEntry", ...]
    split_seed: int
    created_at: _dt.datetime
    created_by: str
    git_commit: str
    status: str
    content_sha256: str | None

    @property
    def partitioned_runs(self) -> tuple[str, ...]:
        return self.train_runs + self.validation_runs + self.test_runs

    @property
    def partition_of(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for partition in PARTITIONS:
            for run_id in getattr(self, f"{partition}_runs"):
                mapping[run_id] = partition
        return mapping

    @property
    def excluded_run_ids(self) -> frozenset[str]:
        return frozenset(run.run_id for run in self.excluded_runs)


@dataclass(frozen=True)
class ExcludedRunEntry:
    """One excluded-run ledger entry (W02 plan §27)."""

    run_id: str
    reason: str


@dataclass(frozen=True)
class RunRecordManifest:
    """Validated per-run manifest (run-record metadata, convention §2)."""

    raw: dict[str, Any] = field(repr=False)
    run_id: str
    scenario_id: str
    controller_id: str
    pair_id: str | None
    device_id: str
    hardware_config_id: str
    firmware_version: str
    calibration_id: str | None
    schema_version: int
    is_valid: bool
    invalid_reason: str | None
    synthetic: bool
    seed: int | None
    start_time: _dt.datetime | None
    end_time: _dt.datetime | None
    note: str | None

    @property
    def boots(self) -> tuple[dict[str, Any], ...]:
        boots = self.raw.get("boots") or []
        return tuple(boots)


# -- dataset manifest ---------------------------------------------------------


def parse_dataset_manifest(
    source: dict[str, Any] | str | Path, *, artifact_kind: str = "dataset"
) -> DatasetManifest:
    """Parse and validate an artifact-convention §3.1 dataset manifest."""
    payload = _load_manifest(source, artifact_kind=artifact_kind)
    _reject_unknown_keys(payload, _DATASET_KEYS, kind="dataset")

    dataset_id = _require_pattern(
        _require_present(payload, "dataset_id", kind=artifact_kind, anchor="§3.1"),
        "dataset.dataset_id",
        DATASET_ID_PATTERN,
        "convention §2 (dataset_id = CG-DATA-…; 05B §7)",
    )
    source_runs_raw = _require_present(
        payload, "source_runs", kind=artifact_kind, anchor="§3.1"
    )
    source_runs_list = _require_str_list(
        source_runs_raw, "dataset.source_runs", anchor="§3.1 (run-level, never row-level)"
    )
    if not source_runs_list:
        raise ManifestError(
            "dataset.source_runs must not be empty — a dataset without runs is not "
            "a dataset (anchor: artifact-convention §3.1)"
        )
    source_runs: list[str] = []
    seen: set[str] = set()
    for run_id in source_runs_list:
        checked = _require_pattern(
            run_id, f"dataset.source_runs[{run_id!r}]", RUN_ID_PATTERN,
            "convention §2 (CG-S<s>-<arm>-<serial>; 05B §7)",
        )
        if checked in seen:
            raise ManifestError(
                f"dataset.source_runs: duplicate run id {checked!r} "
                "(each source run is listed once)"
            )
        seen.add(checked)
        source_runs.append(checked)

    hardware_configs_raw = _require_present(
        payload, "hardware_configs", kind=artifact_kind, anchor="§3.1 (LRK-15)"
    )
    hardware_list = _require_str_list(
        hardware_configs_raw, "dataset.hardware_configs", anchor="§3.1 (LRK-15)"
    )
    if not hardware_list:
        raise ManifestError(
            "dataset.hardware_configs must not be empty — hardware lineage is the "
            "dataset comparability guard (LRK-15); register an exception with "
            "Member A via change control if there is truly none"
        )
    hardware_configs = tuple(
        _require_pattern(hw, f"dataset.hardware_configs[{i}]", HARDWARE_ID_PATTERN,
                         "convention §2 (CG-HW-…; Doc `01` §39.1)")
        for i, hw in enumerate(hardware_list)
    )
    deduped_hardware = tuple(sorted(set(hardware_configs)))
    if deduped_hardware != hardware_configs:
        raise ManifestError(
            f"dataset.hardware_configs carries duplicates {sorted(hardware_configs)} — "
            "each config is listed once"
        )

    calibration_raw = payload.get("calibration_ids", [])
    calibration_list = _require_str_list(
        calibration_raw, "dataset.calibration_ids", anchor="§3.1"
    )
    calibration_ids = tuple(
        _require_pattern(cal, f"dataset.calibration_ids[{i}]", CALIBRATION_ID_PATTERN,
                         "convention §2 (CG-CAL-…; Doc `01` §39.2)")
        for i, cal in enumerate(calibration_list)
    )
    if tuple(sorted(set(calibration_ids))) != calibration_ids:
        raise ManifestError(
            f"dataset.calibration_ids carries duplicates {calibration_ids}"
        )

    schema_version = _require_int(
        _require_present(payload, "schema_version", kind=artifact_kind, anchor="§3.1"),
        "dataset.schema_version",
        anchor="§3.1",
    )
    created_at = _require_rfc3339(
        _require_present(payload, "created_at", kind=artifact_kind, anchor="§5.4"),
        "dataset.created_at",
        anchor="§5.4 provenance",
        allow_none=False,
    )
    created_by = _require_nonempty_str(
        _require_present(payload, "created_by", kind=artifact_kind, anchor="§5.4"),
        "dataset.created_by",
        anchor="§5.4 provenance",
    )
    git_commit = _require_nonempty_str(
        _require_present(payload, "git_commit", kind=artifact_kind, anchor="§5.4"),
        "dataset.git_commit",
        anchor="§5.4 provenance",
    )
    status = _require_present(payload, "status", kind=artifact_kind, anchor="§4")
    if status not in STATUSES:
        raise ManifestError(
            f"dataset.status must be one of {STATUSES} (received: {status!r}; "
            "anchor: artifact-convention §4)"
        )
    synthetic = _require_bool(
        _require_present(payload, "synthetic", kind=artifact_kind, anchor="§11 flag; §3.1"),
        "dataset.synthetic",
        anchor="dictionary §11 fixture provenance flag (must be declared, not defaulted)",
    )
    content_sha256 = _require_lock_content_hash(payload, kind=artifact_kind)
    export_query_hash = _require_hash_or_none(
        payload.get("export_query_hash"),
        "dataset.export_query_hash",
        anchor="§3.1 hash of the canonical export query",
    )

    return DatasetManifest(
        raw=payload,
        dataset_id=dataset_id,
        source_runs=tuple(source_runs),
        hardware_configs=hardware_configs,
        calibration_ids=calibration_ids,
        schema_version=schema_version,
        created_at=created_at,
        created_by=created_by,
        git_commit=git_commit,
        status=status,
        synthetic=synthetic,
        content_sha256=content_sha256,
        export_query_hash=export_query_hash,
    )


# -- split manifest -----------------------------------------------------------


def parse_split_manifest(
    source: dict[str, Any] | str | Path, *, artifact_kind: str = "split"
) -> SplitManifest:
    """Parse and validate an artifact-convention §3.2 split manifest."""
    payload = _load_manifest(source, artifact_kind=artifact_kind)
    _reject_unknown_keys(payload, _SPLIT_KEYS, kind="split")

    split_id = _require_pattern(
        _require_present(payload, "split_id", kind=artifact_kind, anchor="§3.2"),
        "split.split_id",
        SPLIT_ID_PATTERN,
        "convention §2 (split_id = CG-SPLIT-…; 05B §8)",
    )
    dataset_id_ref = _require_pattern(
        _require_present(payload, "dataset_id", kind=artifact_kind, anchor="§3.2 (B1)"),
        "split.dataset_id",
        DATASET_ID_PATTERN,
        "convention §2 (dataset_id = CG-DATA-…; binding B1)",
    )

    partition_lists: dict[str, tuple[str, ...]] = {}
    for partition in PARTITIONS:
        key = f"{partition}_runs"
        raw_list = _require_present(payload, key, kind=artifact_kind, anchor="§3.2")
        partition_lists[partition] = tuple(
            _require_pattern(
                run, f"split.{key}[{i}]", RUN_ID_PATTERN,
                "convention §2 (CG-S<s>-<arm>-<serial>)",
            )
            for i, run in enumerate(
                _require_str_list(raw_list, f"split.{key}", anchor="§3.2")
            )
        )
        if len(set(partition_lists[partition])) != len(partition_lists[partition]):
            raise ManifestError(
                f"split.{key} carries duplicate run ids {sorted(partition_lists[partition])}"
            )
    overlap = {
        partition: set(partition_lists[partition])
        for partition in PARTITIONS
    }
    mismatches: list[str] = []
    for left in PARTITIONS:
        for right in PARTITIONS:
            if left < right and overlap[left] & overlap[right]:
                mismatches.append(f"{left} ∩ {right} = {sorted(overlap[left] & overlap[right])}")
    if mismatches:
        raise ManifestError(
            f"split partitions are not disjoint: {'; '.join(mismatches)} "
            "(grouped splitting requires run-exclusive partitions; anchor: Doc `03` §47)"
        )

    grouping = _require_present(payload, "grouping", kind=artifact_kind, anchor="§3.2")
    if not isinstance(grouping, dict):
        raise ManifestError(
            f"split.grouping must be a mapping with key 'key' (received: {grouping!r})"
        )
    _reject_unknown_keys(grouping, {"key"}, kind="split.grouping")
    grouping_key = _require_nonempty_str(
        _require_present(grouping, "key", kind="split.grouping", anchor="§3.2"),
        "split.grouping.key",
        anchor="§3.2",
    )
    if grouping_key != "run_id":
        raise ManifestError(
            f"split.grouping.key must be 'run_id' (received: {grouping_key!r}) — "
            "run_id is the minimal canonical grouping key (Doc `03` §47)"
        )

    hardware_lineage = _require_present(
        payload, "hardware_lineage", kind=artifact_kind, anchor="§3.2 (B5)"
    )
    if not isinstance(hardware_lineage, dict):
        raise ManifestError(
            f"split.hardware_lineage must be a mapping (received: {hardware_lineage!r})"
        )
    _reject_unknown_keys(hardware_lineage, {"hardware_config_id"}, kind="split.hardware_lineage")
    hw_value = _require_present(
        hardware_lineage, "hardware_config_id", kind="split.hardware_lineage",
        anchor="§3.2 (B5 single value)",
    )
    hardware_config = _require_pattern(
        hw_value, "split.hardware_lineage.hardware_config_id", HARDWARE_ID_PATTERN,
        "convention §2 (CG-HW-…). B5 forbids more than one lineage value in a "
        "split family without a documented Member-A exception",
    )

    locked_test = _require_present(payload, "locked_test", kind=artifact_kind, anchor="§3.2")
    if not isinstance(locked_test, dict):
        raise ManifestError(
            f"split.locked_test must be a mapping (received: {locked_test!r})"
        )
    _reject_unknown_keys(locked_test, {"frozen_at", "opened_at"}, kind="split.locked_test")
    frozen_at, opened_at = _check_lock_test_fields(
        locked_test.get("frozen_at"),
        locked_test.get("opened_at"),
        kind=artifact_kind,
    )

    controller_context = _require_nonempty_str(
        _require_present(payload, "controller_context", kind=artifact_kind, anchor="§3.2 (LRK-09)"),
        "split.controller_context",
        anchor="§3.2 (LRK-09: predictive-closed-loop requires an explicit variant tag)",
    )

    pair_lineage_raw = payload.get("pair_lineage", [])
    pair_lineage: tuple[dict[str, Any], ...] = _parse_pair_lineage(
        pair_lineage_raw, known_partitions={k: set(v) for k, v in partition_lists.items()}
    )

    excluded_raw = payload.get("excluded_runs", [])
    excluded: tuple[dict[str, str], ...] = _parse_excluded_runs(
        excluded_raw,
        partitioned=set(partition_lists["train"])
        | set(partition_lists["validation"])
        | set(partition_lists["test"]),
    )

    split_seed = _require_present(payload, "split_seed", kind=artifact_kind, anchor="§3.2 (Doc `03` §79)")
    if not isinstance(split_seed, int) or isinstance(split_seed, bool):
        raise ManifestError(
            f"split.split_seed must be an explicit integer (received: {split_seed!r}; "
            "anchor: convention §11 — the seed a step consumes is recorded)"
        )

    created_at = _require_rfc3339(
        _require_present(payload, "created_at", kind=artifact_kind, anchor="§5.4"),
        "split.created_at",
        anchor="§5.4 provenance",
        allow_none=False,
    )
    created_by = _require_nonempty_str(
        _require_present(payload, "created_by", kind=artifact_kind, anchor="§5.4"),
        "split.created_by",
        anchor="§5.4 provenance",
    )
    git_commit = _require_nonempty_str(
        _require_present(payload, "git_commit", kind=artifact_kind, anchor="§5.4"),
        "split.git_commit",
        anchor="§5.4 provenance",
    )
    status = _require_present(payload, "status", kind=artifact_kind, anchor="§4")
    if status not in STATUSES:
        raise ManifestError(
            f"split.status must be one of {STATUSES} (received: {status!r}; "
            "anchor: artifact-convention §4)"
        )
    content_sha256 = _require_lock_content_hash(payload, kind=artifact_kind)

    return SplitManifest(
        raw=payload,
        split_id=split_id,
        dataset_id=dataset_id_ref,
        train_runs=partition_lists["train"],
        validation_runs=partition_lists["validation"],
        test_runs=partition_lists["test"],
        grouping_key=grouping_key,
        hardware_lineage=hardware_config,
        frozen_at=frozen_at,
        opened_at=opened_at,
        controller_context=controller_context,
        pair_lineage=pair_lineage,
        excluded_runs=excluded,
        split_seed=split_seed,
        created_at=created_at,
        created_by=created_by,
        git_commit=git_commit,
        status=status,
        content_sha256=content_sha256,
    )


def _parse_pair_lineage(
    pair_lineage_raw: Any, known_partitions: Mapping[str, set[str]]
) -> tuple[dict[str, Any], ...]:
    if not isinstance(pair_lineage_raw, list):
        raise ManifestError(
            f"split.pair_lineage must be a YAML list (received: {pair_lineage_raw!r})"
        )
    parsed: list[dict[str, Any]] = []
    seen_pairs: set[str] = set()
    for i, entry in enumerate(pair_lineage_raw):
        path = f"split.pair_lineage[{i}]"
        if not isinstance(entry, dict):
            raise ManifestError(
                f"{path} must be a mapping with keys {_PAIR_LINEAGE_KEYS} "
                f"(received: {entry!r})"
            )
        _reject_unknown_keys(entry, _PAIR_LINEAGE_KEYS, kind=path)
        pair_id = _require_nonempty_str(
            _require_present(entry, "pair_id", kind=path, anchor="convention §3.2 (LRK-08)"),
            f"{path}.pair_id",
            anchor="convention §3.2 (LRK-08)",
        )
        members_raw = _require_present(entry, "run_ids", kind=path, anchor="convention §3.2")
        members = tuple(
            _require_pattern(run, f"{path}.run_ids[{i}]", RUN_ID_PATTERN,
                             "convention §2 (CG-S<s>-<arm>-<serial>)")
            for i, run in enumerate(
                _require_str_list(members_raw, f"{path}.run_ids", anchor="convention §3.2")
            )
        )
        if not members:
            raise ManifestError(
                f"{path}.run_ids must not be empty — a pair-lineage record with no "
                "members cannot describe pair membership"
            )
        if len(set(members)) != len(members):
            raise ManifestError(f"{path}.run_ids carries duplicates: {members}")
        partition_ref = _require_present(entry, "partition", kind=path, anchor="convention §3.2")
        if partition_ref not in PARTITIONS:
            raise ManifestError(
                f"{path}.partition must be one of {PARTITIONS} (received: {partition_ref!r})"
            )
        declared = set(members)
        actual_partition_runs = known_partitions[partition_ref]
        if not declared <= actual_partition_runs:
            raise ManifestError(
                f"{path}: pair {pair_id!r} lists runs outside {partition_ref!r}: "
                f"{sorted(declared - actual_partition_runs)} — a pair's arms must live "
                "in one partition (Doc `03` §123)"
            )
        if pair_id in seen_pairs:
            raise ManifestError(
                f"split.pair_lineage: pair_id {pair_id!r} appears more than once — "
                "each pair identity has exactly one lineage record; duplicated or "
                "contradictory identities are rejected"
            )
        seen_pairs.add(pair_id)
        parsed.append(
            {"pair_id": pair_id, "run_ids": members, "partition": partition_ref}
        )
    return tuple(parsed)


def _parse_excluded_runs(
    excluded_raw: Any, partitioned: set[str]
) -> tuple[ExcludedRunEntry, ...]:
    if not isinstance(excluded_raw, list):
        raise ManifestError(
            f"split.excluded_runs must be a YAML list (received: {excluded_raw!r})"
        )
    parsed: list[ExcludedRunEntry] = []
    seen: set[str] = set()
    for i, entry in enumerate(excluded_raw):
        path = f"split.excluded_runs[{i}]"
        if not isinstance(entry, dict):
            raise ManifestError(
                f"{path} must be a mapping with keys {_EXCLUDED_KEYS} (received: {entry!r})"
            )
        _reject_unknown_keys(entry, _EXCLUDED_KEYS, kind=path)
        run_id = _require_pattern(
            _require_present(entry, "run_id", kind=path, anchor="§3.2 (plan §27 ledger)"),
            f"{path}.run_id", RUN_ID_PATTERN, "convention §2 (CG-S<s>-<arm>-<serial>)",
        )
        reason = _require_nonempty_str(
            _require_present(entry, "reason", kind=path, anchor="§3.2 (plan §27 ledger)"),
            f"{path}.reason",
            anchor="§3.2 (exclusion without a reason is silent leakage)",
        )
        if run_id in seen:
            raise ManifestError(f"split.excluded_runs: run {run_id!r} appears twice")
        if run_id in partitioned:
            raise ManifestError(
                f"split.excluded_runs: run {run_id!r} is excluded and also assigned to a "
                "partition — an excluded run is not a partitioned run"
            )
        seen.add(run_id)
        parsed.append(ExcludedRunEntry(run_id=run_id, reason=reason))
    return tuple(parsed)


# -- run-record manifests -----------------------------------------------------


def parse_run_manifest(
    source: dict[str, Any] | str | Path, *, artifact_kind: str = "run"
) -> RunRecordManifest:
    """Parse one validated per-run manifest (B-W02-01 output record)."""
    payload = _load_manifest(source, artifact_kind=artifact_kind)
    _reject_unknown_keys(payload, _RUN_KEYS, kind="run")

    run_id = _require_pattern(
        _require_present(payload, "run_id", kind=artifact_kind, anchor="convention §2; 05B §7"),
        "run.run_id", RUN_ID_PATTERN, "convention §2 (CG-S<s>-<arm>-<serial>)",
    )
    scenario_id = _require_present(payload, "scenario_id", kind=artifact_kind, anchor="Doc `03` §31")
    if scenario_id not in SCENARIO_IDS:
        raise ManifestError(
            f"run.scenario_id must be one of {SCENARIO_IDS} (received: {scenario_id!r}; "
            "anchor: Doc `03` §31 canonical scenario vocabulary)"
        )
    controller_id = _require_nonempty_str(
        _require_present(payload, "controller_id", kind=artifact_kind, anchor="experiment key §11"),
        "run.controller_id", anchor="dictionary §11 experiment key",
    )
    pair_raw = payload.get("pair_id")
    pair_id = (
        None if pair_raw is None
        else _require_nonempty_str(pair_raw, "run.pair_id", anchor="dictionary §11")
    )
    device_id = _require_nonempty_str(
        _require_present(payload, "device_id", kind=artifact_kind, anchor="§1.2 identity"),
        "run.device_id", anchor="dictionary §1.2",
    )
    hardware_config_id = _require_pattern(
        _require_present(payload, "hardware_config_id", kind=artifact_kind, anchor="Doc `01` §39.1"),
        "run.hardware_config_id", HARDWARE_ID_PATTERN, "convention §2 (CG-HW-…)",
    )
    firmware_version = _require_nonempty_str(
        _require_present(payload, "firmware_version", kind=artifact_kind, anchor="§2 identity"),
        "run.firmware_version", anchor="dictionary §2",
    )
    calibration_raw = payload.get("calibration_id")
    calibration_id = (
        None if calibration_raw is None
        else _require_pattern(
            calibration_raw, "run.calibration_id", CALIBRATION_ID_PATTERN,
            "convention §2 (CG-CAL-…; Doc `01` §39.2)",
        )
    )
    schema_version = _require_int(
        _require_present(payload, "schema_version", kind=artifact_kind, anchor="§2 identity"),
        "run.schema_version", anchor="dictionary §2",
    )
    is_valid = _require_bool(
        _require_present(payload, "is_valid", kind=artifact_kind, anchor="Doc `01` §33"),
        "run.is_valid", anchor="Doc `01` §33 invalid-run ledger",
    )
    invalid_raw = payload.get("invalid_reason")
    invalid_reason = (
        None if invalid_raw is None
        else _require_nonempty_str(invalid_raw, "run.invalid_reason", anchor="Doc `01` §33")
    )
    if not is_valid and not invalid_reason:
        raise ManifestError(
            f"run {run_id!r}: is_valid=false requires a non-empty invalid_reason "
            "(A's invalid-run ledger is the gate; anchor: Doc `01` §33)"
        )
    synthetic = _require_bool(
        _require_present(payload, "synthetic", kind=artifact_kind, anchor="dictionary §11"),
        "run.synthetic", anchor="dictionary §11 fixture provenance flag",
    )
    note_raw = payload.get("note")
    note = (
        None if note_raw is None
        else _require_nonempty_str(note_raw, "run.note", anchor="dictionary §11")
    )
    if synthetic and not note:
        raise ManifestError(
            f"run {run_id!r}: synthetic=true requires a non-empty note declaring "
            "fixture provenance (dictionary §11: a synthetic record labels itself "
            "as synthetic everywhere)"
        )
    seed_raw = payload.get("seed")
    seed: int | None
    if seed_raw is None:
        if synthetic:
            raise ManifestError(
                f"run {run_id!r}: synthetic=true requires the consumed seed to be "
                "recorded (convention §11 seed policy)"
            )
        seed = None
    else:
        if not isinstance(seed_raw, int) or isinstance(seed_raw, bool):
            raise ManifestError(
                f"run.seed must be an explicit integer (received: {seed_raw!r}; "
                "anchor: convention §11)"
            )
        seed = seed_raw
    start_time = _require_rfc3339(
        payload.get("start_time"), "run.start_time", anchor="dictionary §3", allow_none=True
    )
    end_time = _require_rfc3339(
        payload.get("end_time"), "run.end_time", anchor="dictionary §3", allow_none=True
    )
    if start_time is not None and end_time is not None and end_time < start_time:
        raise ManifestError(
            f"run {run_id!r}: end_time {event_or_none(end_time)} precedes start_time "
            f"{event_or_none(start_time)} — a run's recorded span is contradictory"
        )
    boots = payload.get("boots")
    if boots is None:
        boots = []
    if not isinstance(boots, list):
        raise ManifestError(
            f"run.boots must be a YAML list (received: {boots!r})"
        )
    for i, boot in enumerate(boots):
        path = f"run.boots[{i}]"
        if not isinstance(boot, dict):
            raise ManifestError(f"{path} must be a mapping (received: {boot!r})")
        _reject_unknown_keys(boot, _BOOT_KEYS, kind=path)
        _require_nonempty_str(
            _require_present(boot, "boot_id", kind=path, anchor="dictionary §3"),
            f"{path}.boot_id", anchor="dictionary §3",
        )
        _require_int(
            _require_present(boot, "n_observations", kind=path, anchor="dictionary §3"),
            f"{path}.n_observations", anchor="dictionary §3",
        )
        first = _require_rfc3339(
            boot.get("first_time"), f"{path}.first_time", anchor="dictionary §3",
            allow_none=False,
        )
        last = _require_rfc3339(
            boot.get("last_time"), f"{path}.last_time", anchor="dictionary §3",
            allow_none=False,
        )
        if last < first:
            raise ManifestError(
                f"{path}: last_time {event_or_none(last)} precedes first_time "
                f"{event_or_none(first)} — boot summary is contradictory"
            )
    boot_ids = [boot["boot_id"] for boot in boots]
    if len(set(boot_ids)) != len(boot_ids):
        raise ManifestError(f"run.boots carries duplicate boot summaries: {boot_ids}")

    return RunRecordManifest(
        raw=payload,
        run_id=run_id,
        scenario_id=scenario_id,
        controller_id=controller_id,
        pair_id=pair_id,
        device_id=device_id,
        hardware_config_id=hardware_config_id,
        firmware_version=firmware_version,
        calibration_id=calibration_id,
        schema_version=schema_version,
        is_valid=is_valid,
        invalid_reason=invalid_reason,
        synthetic=synthetic,
        seed=seed,
        start_time=start_time,
        end_time=end_time,
        note=note,
    )


def parse_run_manifests(
    source: list[Any] | str | Path, *, artifact_kind: str = "run"
) -> tuple[RunRecordManifest, ...]:
    """Parse a list of run-record manifests (YAML list text, file, or list input).

    A top-level mapping is rejected: lists are ordered structures and the
    run-record list is not a mapping-shaped manifest.
    """
    if isinstance(source, list):
        payload = list(source)
    elif isinstance(source, (str, Path)):
        payload = _load_manifest_list_like(source, artifact_kind=artifact_kind)
    else:
        raise ManifestError(
            f"run-record list input must be a YAML list, list input, or file path "
            f"(received: {type(source).__name__})"
        )
    records = tuple(
        parse_run_manifest(entry, artifact_kind=artifact_kind)
        for entry in payload
    )
    ids = [record.run_id for record in records]
    duplicates = sorted({run for run in ids if ids.count(run) > 1})
    if duplicates:
        raise ManifestError(
            f"run-record list carries duplicate run manifests for {duplicates}"
        )
    return records


def _load_manifest_list_like(source: str | Path, *, artifact_kind: str) -> list[Any]:
    text: str
    origin: str
    if isinstance(source, Path):
        origin = str(source)
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise ManifestError(
                f"cannot read {artifact_kind} manifest file {origin}: {exc}"
            ) from exc
    elif "\n" not in source and Path(source).is_file():
        origin = source
        text = Path(source).read_text(encoding="utf-8")
    else:
        origin = "<yaml-text>"
        text = source
    try:
        loaded = yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        raise ManifestError(
            f"{artifact_kind} manifest list is not valid YAML ({origin}): {exc}"
        ) from exc
    if not isinstance(loaded, list):
        raise ManifestError(
            f"{artifact_kind} manifest list ({origin}) must be a YAML list, "
            f"got {type(loaded).__name__}"
        )
    return loaded


# -- cross-bindings (convention §9, W02 scope) --------------------------------


def bind_split_to_dataset(split: SplitManifest, dataset: DatasetManifest) -> None:
    """Binding B1 (plus the B5 comparability support check).

    * ``split.dataset_id`` resolves to the supplied dataset;
    * ``train ∪ validation ∪ test`` equals ``dataset.source_runs`` exactly;
    * the split's single hardware lineage value is inside the dataset's
      declared hardware configs (LRK-15 comparability chain).
    """
    if split.dataset_id != dataset.dataset_id:
        raise ManifestError(
            f"B1 violated: split {split.split_id!r} references dataset "
            f"{split.dataset_id!r} but was bound against dataset {dataset.dataset_id!r}"
        )
    union = set(split.partitioned_runs)
    source = set(dataset.source_runs)
    missing_from_union = sorted(source - union)
    extra_in_union = sorted(union - source)
    if missing_from_union or extra_in_union:
        raise ManifestError(
            f"B1 violated for split {split.split_id!r}: partition union does not equal "
            f"dataset {dataset.dataset_id!r} source_runs — "
            f"dataset runs not partitioned: {missing_from_union}; "
            f"partitioned runs not in dataset: {extra_in_union} "
            "(partition union must equal source_runs exactly; convention §9 B1)"
        )
    if dataset.hardware_configs and split.hardware_lineage not in dataset.hardware_configs:
        raise ManifestError(
            f"B5/LRK-15 violated: split {split.split_id!r} hardware lineage "
            f"{split.hardware_lineage!r} is not in dataset {dataset.dataset_id!r} "
            f"hardware_configs {list(dataset.hardware_configs)}"
        )


def bind_dataset_to_run_records(
    dataset: DatasetManifest, run_records: Iterable[RunRecordManifest]
) -> None:
    """Dataset ↔ run-record bindings: resolution, hardware/calibration registry
    subsets, and the B7 synthetic-flag propagation audit."""
    by_run: dict[str, RunRecordManifest] = {}
    for record in run_records:
        if record.run_id in by_run:
            raise ManifestError(
                f"run-record list carries duplicate manifests for {record.run_id!r}"
            )
        by_run[record.run_id] = record

    missing = sorted(set(dataset.source_runs) - set(by_run))
    if missing:
        raise ManifestError(
            f"B1 support violated: dataset {dataset.dataset_id!r} source_runs reference "
            f"runs without manifests: {missing} — every dataset run resolves to a "
            "run-record manifest (convention §9 audit-chain foundation)"
        )

    if dataset.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ManifestError(
            f"dataset {dataset.dataset_id!r} schema_version {dataset.schema_version!r} "
            f"is not supported; supported schema versions: "
            f"{sorted(SUPPORTED_SCHEMA_VERSIONS)} — an unsupported schema ancestry "
            "cannot be bound into a research dataset"
        )

    for run_id in dataset.source_runs:
        record = by_run[run_id]
        if record.schema_version != dataset.schema_version:
            raise ManifestError(
                f"schema ancestry violated: run {run_id!r} schema_version "
                f"{record.schema_version!r} differs from dataset "
                f"{dataset.dataset_id!r} schema_version {dataset.schema_version!r} — "
                "the supported contract is homogeneous dataset/run schema provenance"
            )
        if record.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ManifestError(
                f"run {run_id!r} schema_version {record.schema_version!r} is not "
                f"supported; supported schema versions: "
                f"{sorted(SUPPORTED_SCHEMA_VERSIONS)} (schema ancestry gate)"
            )
        if record.hardware_config_id not in dataset.hardware_configs:
            raise ManifestError(
                f"LRK-15 violated: run {run_id!r} hardware_config_id "
                f"{record.hardware_config_id!r} is not in dataset "
                f"{dataset.dataset_id!r} hardware_configs {list(dataset.hardware_configs)}"
            )
        if record.calibration_id is not None and record.calibration_id not in dataset.calibration_ids:
            raise ManifestError(
                f"run {run_id!r} calibration_id {record.calibration_id!r} not registered in "
                f"dataset {dataset.dataset_id!r} calibration_ids {list(dataset.calibration_ids)}"
            )
        # B7: a synthetic dataset claims synthetic content end to end; a
        # research dataset claims none. Any mixing must go through a fresh
        # dataset_id minting (convention §9 B7).
        if record.synthetic != dataset.synthetic:
            raise ManifestError(
                f"B7 violated in dataset {dataset.dataset_id!r}: run {run_id!r} "
                f"synthetic={record.synthetic!r} conflicts with dataset "
                f"synthetic={dataset.synthetic!r} — synthetic fixture content "
                "cannot merge into a differently-flagged dataset identity"
            )
        if record.is_valid is False:
            raise ManifestError(
                f"invalid-run ledger violated: run {run_id!r} is marked "
                f"invalid ({record.invalid_reason!r}) but appears in "
                f"dataset {dataset.dataset_id!r} source_runs — datasets are sources "
                "for evidence splits and cannot carry invalidated runs (Doc `01` §33)"
            )


def bind_split_to_run_records(
    split: SplitManifest, run_records: Iterable[RunRecordManifest]
) -> None:
    """Split ↔ run-record bindings.

    * every run cited by the split (partitions, pair lineage, excluded)
      must have a run record;
    * partitioned runs must be valid and match the split lineage;
    * excluded runs shall record why they are out (invalid-run ledger
      reason present for invalid ones);
    * pair lineage stays consistent with the recorded partitions.
    """
    by_run: dict[str, RunRecordManifest] = {}
    for record in run_records:
        if record.run_id in by_run:
            raise ManifestError(
                f"run-record list carries duplicate manifests for {record.run_id!r}"
            )
        by_run[record.run_id] = record

    referenced: list[str] = list(split.partitioned_runs)
    for entry in split.pair_lineage:
        referenced.extend(entry["run_ids"])
    missing = sorted(set(referenced) - set(by_run))
    if missing:
        raise ManifestError(
            f"split {split.split_id!r} references runs without manifests: {missing} "
            "(all referenced runs need run records)"
        )

    partition_by_run = split.partition_of

    # Derived pair membership is the leakage gate: pair_lineage is audit
    # metadata, never the source of truth. Runs sharing a pair_id must share a
    # partition even when the declaration is empty (LRK-08, Doc `03` §123).
    derived_pairs: dict[str, list[str]] = {}
    for run_id in split.partitioned_runs:
        pair_id = by_run[run_id].pair_id
        if pair_id is not None:
            derived_pairs.setdefault(pair_id, []).append(run_id)

    for pair_id, members in sorted(derived_pairs.items()):
        partitions = {partition_by_run[member] for member in members}
        if len(partitions) != 1:
            raise ManifestError(
                f"LRK-08 violated in split {split.split_id!r}: runs {sorted(members)} "
                f"share pair_id {pair_id!r} but straddle partitions "
                f"{sorted(partitions)} — paired runs must share one partition; an "
                "omitted pair_lineage cannot bypass the derived relationship "
                "(Doc `03` §123)"
            )

    declared_pairs: dict[str, set[str]] = {}
    for entry in split.pair_lineage:
        pair_id = entry["pair_id"]
        if pair_id in declared_pairs:
            raise ManifestError(
                f"split {split.split_id!r}: pair_id {pair_id!r} is declared more than "
                "once in pair_lineage"
            )
        declared_pairs[pair_id] = set(entry["run_ids"])

    for pair_id, members in sorted(derived_pairs.items()):
        if pair_id not in declared_pairs:
            # A co-located pair without a declaration is audit-incomplete but
            # cannot leak (the derived gate above protects the partition); the
            # normal producer declares pairs, and any present declaration is
            # still checked exactly below.
            continue
        if declared_pairs[pair_id] != set(members):
            raise ManifestError(
                f"split {split.split_id!r}: pair {pair_id!r} declares runs "
                f"{sorted(declared_pairs[pair_id])} but the run records derive "
                f"{sorted(set(members))} — declared membership must match derived "
                "membership exactly"
            )

    for pair_id in sorted(declared_pairs):
        if pair_id not in derived_pairs:
            raise ManifestError(
                f"split {split.split_id!r}: pair_lineage declares pair {pair_id!r} "
                "but no partitioned run record carries that pair_id — declared pair "
                "identity contradicts the run records"
            )

    for run_id in split.partitioned_runs:
        record = by_run[run_id]
        if not record.is_valid:
            raise ManifestError(
                f"contradiction in split {split.split_id!r}: run {run_id!r} is assigned "
                f"to partition {split.partition_of[run_id]!r} but its record flags it "
                f"invalid ({record.invalid_reason!r}) — invalidated runs are excluded, "
                "never partitioned (Doc `01` §33)"
            )
        if record.hardware_config_id != split.hardware_lineage:
            raise ManifestError(
                f"LRK-15 violated: run {run_id!r} hardware_config_id "
                f"{record.hardware_config_id!r} differs from split "
                f"{split.split_id!r} hardware_lineage {split.hardware_lineage!r}"
            )

    for entry in split.excluded_runs:
        record = by_run.get(entry.run_id)
        if record is not None:
            if record.is_valid and entry.reason == "predictive-closed-loop":
                continue  # controller-context exclusion of a valid variant run (LRK-09)
            if not record.is_valid:
                continue  # invalid run: reason snapshot is in the record itself
            if record.is_valid and entry.reason != "predictive-closed-loop":
                raise ManifestError(
                    f"split {split.split_id!r}: run {entry.run_id!r} is recorded "
                    f"valid but excluded with reason {entry.reason!r} — only the "
                    "predictive-closed-loop (LRK-09) exclusion may drop a valid run"
                )
        else:
            raise ManifestError(
                f"split {split.split_id!r}: excluded run {entry.run_id!r} has no run "
                "record — exclusions must still be traceable to a run manifest "
                "(the dataset QA and A's ledger rely on the ledger, not memory)"
            )

    for entry in split.pair_lineage:
        partition = entry["partition"]
        members = tuple(entry["run_ids"])
        for member in members:
            if split.partition_of.get(member) != partition:
                raise ManifestError(
                    f"split {split.split_id!r}: pair {entry['pair_id']!r} declares "
                    f"partition {partition!r} but run {member!r} is recorded in "
                    f"{split.partition_of.get(member)!r} — pair lineage contradicts "
                    "the recorded partitions"
                )


# -- canonical serialization / content identity -------------------------------


def canonical_manifest_yaml(payload: Mapping[str, Any]) -> str:
    """Canonical key-sorted YAML rendering of a manifest payload (convention §5)."""
    return yaml.safe_dump(
        payload,
        sort_keys=True,
        allow_unicode=True,
        default_flow_style=False,
        width=4096,
    )


def manifest_content_sha256(payload: Mapping[str, Any]) -> str:
    """Practical §5 recipe: sha256 over the canonical YAML rendering."""
    return hashlib.sha256(
        canonical_manifest_yaml(payload).encode("utf-8")
    ).hexdigest()
