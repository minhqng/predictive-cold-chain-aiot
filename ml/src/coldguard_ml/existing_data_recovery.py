"""Existing physical data recovery for bounded analysis (Member B).

This layer consumes only the allowlisted Member A physical evidence that is
already committed or pinned read-only, and produces source-bound descriptive
results, plots and an honest predictive-eligibility review.

It does not create a new admission system, a new Gate B, a model, a locked
test, a physical action or a command path.  A source may be useful for physical
description or disturbance analysis and still be ineligible for predictive
training; those outcomes are kept separate.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import statistics
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from xml.sax.saxutils import escape

from .horizon_engineering import (
    A_20261107_MANIFEST_SHA256,
    A_20261107_RUN_INDEX_SHA256,
    A_SOURCE_REVISION,
    A_W13_TIMING_REPORT_SHA256,
    EvidencePinError,
    PlantTiming,
    ReconciledSource,
    ReconciliationError,
    load_plant_timing,
    reconcile_a_dataset,
    verify_sha256,
)

LAYER_VERSION = "coldguard-existing-data-recovery-v1"
INVENTORY_SCHEMA = "coldguard-existing-data-source-inventory-v1"
MANIFEST_SCHEMA = "coldguard-existing-data-recovery-manifest-v1"
OBSERVATION_SCHEMA = "coldguard-existing-data-observation-v1"
INPUT_INVENTORY_SCHEMA = "coldguard-existing-data-source-inventory-input-v1"
PLOT_LABEL = "PHYSICAL_RECORDED_DATA"

W05_EXPORT_SHA256 = (
    "f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb"
)
W05_ROW_VALIDITY_SHA256 = (
    "da27b2668097c207dd679e563fc18322742d68dfb4eb5a894f64958be35eebaf"
)
W05_RAW_SHA256 = (
    "f8716b5136f34542225b366c238be4e65ce309e78593e8bad90d578af9a7c14d"
)
W05_RUN_INDEX_SHA256 = (
    "eb71d3f58004a25e60315b39ed88e33daa7e069a7a1fc3df391713cfce33b5af"
)
W21_MANIFEST_SHA256 = (
    "5b78141deca1d3f5fd5e16ac10b3344541261d66b5aaa6e49bb3169758fae2c3"
)
W21_RAW_LOG_SHA256 = (
    "faf008eb6c7e250c8b8f98385e6eb3817b1084771a56d800a3735c576c7106fa"
)
PR95_HEAD_REVISION = "815387d19a3898e6b33ccb65758a554dd0c589e1"
PR95_TRIAL_SHA256 = (
    "f028441d10af53f43873000a6d16ab43e79a80f6defe0b974a6a5dc60c9d3b14"
)

SENSOR_ROLES: Mapping[str, str] = {
    "t1": "CHAMBER_CENTER",
    "t2": "TEC_HOT_SIDE",
    "t3": "CHAMBER_BOTTOM",
    "t4": "CHAMBER_NEAR_DOOR",
}
CHAMBER_AIR_SLOTS = ("t1", "t3", "t4")
HOT_SIDE_SLOT = "t2"

USE_DESCRIPTION = "PHYSICAL_DESCRIPTION_USABLE"
USE_DISTURBANCE = "PHYSICAL_DISTURBANCE_ANALYSIS_USABLE"
USE_SENSOR_DIAG = "PHYSICAL_SENSOR_DIAGNOSTIC_USABLE"
USE_EXPLORATORY = "EXPLORATORY_MODEL_INPUT_CANDIDATE"
USE_PREDICTIVE = "PREDICTIVE_ADMISSION_VERIFIED"
USE_NOT = "NOT_USABLE_FOR_REQUESTED_ANALYSIS"
USE_UNAVAILABLE = "SOURCE_UNAVAILABLE"

STATUS_AUDIT_COMPLETE = "COMPLETE"
STATUS_AUDIT_PARTIAL = "PARTIAL"
STATUS_AUDIT_BLOCKED = "BLOCKED"

EVIDENCE_PHYSICAL = "PHYSICAL_RECORDED_DATA"
EVIDENCE_DERIVED_TIMING = "HOST_ANALYSIS_OF_COMMITTED_CAPTURES"
EVIDENCE_ON_DEVICE = "ON_DEVICE_SOFTWARE_INJECTION"
EVIDENCE_DECLARED_ONLY = "UNMERGED_SUPPLEMENTARY_EVIDENCE"
EVIDENCE_SYNTHETIC = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
EVIDENCE_TEST_ONLY = "SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY"

NOT_ESTIMABLE = "NOT_ESTIMABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"

FORBIDDEN_PATH_TOKENS = (
    "w16",
    "locked-test",
    "locked_test",
    "holdout",
    "w20",
    "outcome",
    "campaign-wave2",
    "campaign_wave2",
    "predictive-test",
    "predictive_test",
)

ALLOWED_SOURCE_KINDS = frozenset(
    {
        "A_RUN_INDEX",
        "A_DATASET_MANIFEST",
        "A_TIMING_REPORT",
        "W05_EXPORT",
        "W05_ROW_VALIDITY",
        "W05_RAW",
        "W05_RUN_INDEX",
        "W21_MANIFEST",
        "W21_SUMMARY",
        "PR95_SUPPLEMENT",
    }
)

SOURCE_ROOTS = {
    "A_RUN_INDEX": "A_DATASET",
    "A_DATASET_MANIFEST": "A_DATASET",
    "A_TIMING_REPORT": "REPOSITORY",
    "W05_EXPORT": "REPOSITORY",
    "W05_ROW_VALIDITY": "REPOSITORY",
    "W05_RAW": "REPOSITORY",
    "W05_RUN_INDEX": "REPOSITORY",
    "W21_MANIFEST": "REPOSITORY",
    "W21_SUMMARY": "REPOSITORY",
    "PR95_SUPPLEMENT": "NONE",
}

W05_DEFAULTS = {
    "W05_EXPORT": (
        "evidence/A/W09/exports/CG-S1-H8C-600S.json",
        W05_EXPORT_SHA256,
    ),
    "W05_ROW_VALIDITY": (
        "evidence/A/W09/exports/CG-S1-H8C-600S.row-validity.csv",
        W05_ROW_VALIDITY_SHA256,
    ),
    "W05_RAW": (
        "evidence/A/W04/tec-cooling-response-600s.csv",
        W05_RAW_SHA256,
    ),
    "W05_RUN_INDEX": (
        "evidence/A/W09/s1-run-index.json",
        W05_RUN_INDEX_SHA256,
    ),
}


class RecoveryError(ValueError):
    """The recovery package would present unsupported evidence as a result."""


class SourceIntegrityError(RecoveryError):
    """A source byte stream does not match its provenance pin."""


class SourcePathRefused(RecoveryError):
    """A source path is outside the explicit allowlist."""


class DuplicateSourceError(RecoveryError):
    """Two supposedly distinct source records are byte- or frame-identical."""


class GateBRefusal(RecoveryError):
    """The authoritative Gate B validator refused or did not run."""


class FutureFeatureRefused(RecoveryError):
    """A feature timestamp is at or after the target timestamp."""


class SourceOverlapRefused(RecoveryError):
    """Train and test source lineage overlap."""


class SyntheticMetricPromotionRefused(RecoveryError):
    """A synthetic metric would be reported as physical evidence."""


# ---------------------------------------------------------------------------
# Explicit source inventory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceInput:
    source_id: str
    kind: str
    path: str | None
    expected_sha256: str | None
    required: bool
    root: str
    description: str = ""
    availability: str = "EXPECTED_PRESENT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": self.kind,
            "path": self.path,
            "expected_sha256": self.expected_sha256,
            "required": self.required,
            "root": self.root,
            "description": self.description,
            "availability": self.availability,
        }


def _is_hex_digest(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", value or ""))


def _normalized_relative(path_value: str) -> str:
    if not path_value:
        raise SourcePathRefused("an allowlisted source path must not be empty")
    path = Path(path_value)
    if path.is_absolute():
        raise SourcePathRefused(
            f"absolute source path {path_value!r} is refused; use a "
            "repository-relative allowlisted path"
        )
    parts = path.parts
    if ".." in parts:
        raise SourcePathRefused(
            f"source path {path_value!r} escapes its allowlisted root"
        )
    posix = path.as_posix()
    lowered = posix.lower()
    for token in FORBIDDEN_PATH_TOKENS:
        if token in lowered:
            raise SourcePathRefused(
                f"source path {path_value!r} matches forbidden token {token!r}; "
                "W16 locked-test and W20 outcome material must never be opened"
            )
    return posix


def validate_source_inputs(payload: Mapping[str, Any]) -> tuple[SourceInput, ...]:
    if payload.get("schema") != INPUT_INVENTORY_SCHEMA:
        raise RecoveryError(
            f"source inventory schema must be {INPUT_INVENTORY_SCHEMA!r}"
        )
    rows = payload.get("sources")
    if not isinstance(rows, list) or not rows:
        raise RecoveryError("source inventory must carry a non-empty sources list")
    seen: set[str] = set()
    result: list[SourceInput] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise RecoveryError("each source inventory entry must be an object")
        source_id = str(row.get("source_id", "")).strip()
        kind = str(row.get("kind", "")).strip()
        if not source_id:
            raise RecoveryError("a source inventory entry has no source_id")
        if source_id in seen:
            raise RecoveryError(f"duplicate source_id {source_id!r}")
        seen.add(source_id)
        if kind not in ALLOWED_SOURCE_KINDS:
            raise SourcePathRefused(
                f"source {source_id!r} has non-allowlisted kind {kind!r}"
            )
        root = str(row.get("root") or SOURCE_ROOTS[kind])
        if root not in {"A_DATASET", "REPOSITORY", "NONE"}:
            raise SourcePathRefused(
                f"source {source_id!r} has non-allowlisted root {root!r}"
            )
        path_value = row.get("path")
        if kind == "PR95_SUPPLEMENT":
            path_value = None
        elif path_value is None:
            raise SourcePathRefused(
                f"source {source_id!r} of kind {kind!r} requires a path"
            )
        normalized = (
            _normalized_relative(str(path_value)) if path_value is not None else None
        )
        expected = row.get("expected_sha256")
        if expected is not None and not _is_hex_digest(str(expected)):
            raise RecoveryError(
                f"source {source_id!r} expected_sha256 is not a 64-char digest"
            )
        result.append(
            SourceInput(
                source_id=source_id,
                kind=kind,
                path=normalized,
                expected_sha256=str(expected) if expected else None,
                required=bool(row.get("required", True)),
                root=root,
                description=str(row.get("description", "")),
                availability=str(row.get("availability", "EXPECTED_PRESENT")),
            )
        )
    return tuple(result)


def default_source_inputs(
    *,
    repo_root: Path,
    a_dataset_dir: Path,
    w05_export: Path,
    w05_row_validity: Path,
    w05_raw: Path,
    w05_run_index: Path,
    a_timing_report: Path,
    w21_manifest: Path,
) -> tuple[SourceInput, ...]:
    """The canonical allowlist; never a recursive repository scan."""

    def rel(path: Path, root: Path) -> str:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            raise SourcePathRefused(
                f"{path} is outside its declared source root {root}"
            ) from None

    return (
        SourceInput(
            "A20261107:RUN_INDEX",
            "A_RUN_INDEX",
            rel(a_dataset_dir / "run_index.csv", a_dataset_dir),
            A_20261107_RUN_INDEX_SHA256,
            True,
            "A_DATASET",
            "A 20261107 run index (18 rows/segments)",
        ),
        SourceInput(
            "A20261107:MANIFEST",
            "A_DATASET_MANIFEST",
            rel(a_dataset_dir / "manifest.json", a_dataset_dir),
            A_20261107_MANIFEST_SHA256,
            True,
            "A_DATASET",
            "A 20261107 package manifest with output pins",
        ),
        SourceInput(
            "A20261107:TIMING_REPORT",
            "A_TIMING_REPORT",
            rel(a_timing_report, repo_root),
            A_W13_TIMING_REPORT_SHA256,
            True,
            "REPOSITORY",
            "A W13 plant timing report (derived host analysis)",
        ),
        SourceInput(
            "W05A:EXPORT",
            "W05_EXPORT",
            rel(w05_export, repo_root),
            W05_EXPORT_SHA256,
            True,
            "REPOSITORY",
            "W05/W09 candidate capture export",
        ),
        SourceInput(
            "W05A:ROW_VALIDITY",
            "W05_ROW_VALIDITY",
            rel(w05_row_validity, repo_root),
            W05_ROW_VALIDITY_SHA256,
            True,
            "REPOSITORY",
            "W05 per-row validity companion CSV",
        ),
        SourceInput(
            "W05A:RAW",
            "W05_RAW",
            rel(w05_raw, repo_root),
            W05_RAW_SHA256,
            True,
            "REPOSITORY",
            "W04 raw H8-C telemetry CSV",
        ),
        SourceInput(
            "W05A:RUN_INDEX",
            "W05_RUN_INDEX",
            rel(w05_run_index, repo_root),
            W05_RUN_INDEX_SHA256,
            True,
            "REPOSITORY",
            "W05/W09 S1 run-validity index consumed by the W08 Gate B validator",
        ),
        SourceInput(
            "A-W21:MANIFEST",
            "W21_MANIFEST",
            rel(w21_manifest, repo_root),
            W21_MANIFEST_SHA256,
            True,
            "REPOSITORY",
            "W21 bounded diagnostic manifest",
        ),
    )


def _resolve_source_path(
    spec: SourceInput,
    *,
    repo_root: Path,
    a_dataset_dir: Path,
) -> Path:
    if spec.path is None:
        raise SourcePathRefused(f"source {spec.source_id!r} has no path")
    if spec.root == "A_DATASET":
        candidate = (a_dataset_dir / spec.path).resolve()
        try:
            candidate.relative_to(a_dataset_dir.resolve())
        except ValueError:
            raise SourcePathRefused(
                f"source {spec.source_id!r} escapes the A dataset directory"
            ) from None
    elif spec.root == "REPOSITORY":
        candidate = (repo_root / spec.path).resolve()
        try:
            candidate.relative_to(repo_root.resolve())
        except ValueError:
            raise SourcePathRefused(
                f"source {spec.source_id!r} escapes the repository root"
            ) from None
    else:
        raise SourcePathRefused(f"source {spec.source_id!r} has no readable path")
    return candidate


# ---------------------------------------------------------------------------
# Parsing and descriptive metrics
# ---------------------------------------------------------------------------


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in {
        "",
        "nan",
        "NaN",
        "NA",
        "NO_DATA",
        "UNKNOWN",
        "UNVERIFIED",
        "NOT_CARRIED",
        "NOT_AVAILABLE",
    }:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def parse_status(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text.upper() if text else None


def _status_usable(value: Any) -> bool:
    return parse_status(value) in {"OK", "VALID"}


def _door_state(row: Mapping[str, str]) -> str | None:
    if not _status_usable(row.get("door_status")):
        return None
    value = parse_float(row.get("door_open"))
    if value is None:
        return None
    if value == 0.0:
        return "0"
    if value == 1.0:
        return "1"
    return None


def _row_value(row: Mapping[str, str], *names: str) -> float | None:
    for name in names:
        if name in row:
            return parse_float(row.get(name))
    return None


def _slot_value(row: Mapping[str, str], slot: str) -> float | None:
    aliases = {
        "t1": ("t1_c", "t1", "chamber_c_t1_slot"),
        "t2": ("t2_c", "t2", "hot_side_c_t2"),
        "t3": ("t3_c", "t3"),
        "t4": ("t4_c", "t4"),
    }[slot]
    return _row_value(row, *aliases)


def _slot_status(row: Mapping[str, str], slot: str) -> str | None:
    return parse_status(row.get(f"{slot}_status"))


def _chamber_air(row: Mapping[str, str]) -> float | None:
    values = [_slot_value(row, slot) for slot in CHAMBER_AIR_SLOTS]
    statuses = [_slot_status(row, slot) for slot in CHAMBER_AIR_SLOTS]
    if any(value is None for value in values) or any(
        not _status_usable(status) for status in statuses
    ):
        return None
    return sum(values) / 3.0  # type: ignore[arg-type]


def _sensor_spread(row: Mapping[str, str]) -> float | None:
    values = [_slot_value(row, slot) for slot in CHAMBER_AIR_SLOTS]
    statuses = [_slot_status(row, slot) for slot in CHAMBER_AIR_SLOTS]
    if any(value is None for value in values) or any(
        not _status_usable(status) for status in statuses
    ):
        return None
    return max(values) - min(values)  # type: ignore[type-var]


def time_axis(rows: Sequence[Mapping[str, str]]) -> tuple[list[float | None], str, str]:
    boot_ids = {str(row.get("boot_id", "")) for row in rows if row.get("boot_id")}
    if len(boot_ids) > 1:
        return [None] * len(rows), "CROSS_BOOT_UNTRUSTED", (
            "multiple boot_id values inside one source; boot-relative durations "
            "are not trusted"
        )
    raw = [
        parse_float(row.get("uptime_ms"))
        if row.get("uptime_ms") not in (None, "")
        else parse_float(row.get("device_ms"))
        for row in rows
    ]
    if any(value is None for value in raw):
        return [None] * len(rows), "FRAME_INDEX_ONLY", (
            "device uptime is not carried on every frame; time is frame index "
            "only and slopes are NOT_ESTIMABLE"
        )
    numbers = [float(value) for value in raw]  # type: ignore[arg-type]
    if any(b < a for a, b in zip(numbers, numbers[1:])):
        return [None] * len(rows), "UNTRUSTED_NON_MONOTONIC", (
            "device uptime is not monotonically non-decreasing; time-based "
            "metrics are refused"
        )
    return [value / 1000.0 for value in numbers], "BOOT_SCOPED_UPTIME", (
        "device uptime within one boot; not an absolute synchronized time"
    )


@dataclass(frozen=True)
class TemperatureStats:
    valid_frames: int
    total_frames: int
    minimum_c: float | None
    maximum_c: float | None
    mean_c: float | None
    first_c: float | None
    last_c: float | None
    change_c: float | None
    slope_c_per_min: float | None
    missing_frames: int
    status_not_ok_frames: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_frames": self.valid_frames,
            "total_frames": self.total_frames,
            "minimum_c": self.minimum_c,
            "maximum_c": self.maximum_c,
            "mean_c": self.mean_c,
            "first_c": self.first_c,
            "last_c": self.last_c,
            "change_c": self.change_c,
            "slope_c_per_min": self.slope_c_per_min,
            "missing_frames": self.missing_frames,
            "status_not_ok_frames": self.status_not_ok_frames,
        }


def _ols_slope(times: Sequence[float], values: Sequence[float]) -> float | None:
    count = len(times)
    if count < 2:
        return None
    mean_t = sum(times) / count
    mean_v = sum(values) / count
    denominator = sum((value - mean_t) ** 2 for value in times)
    if denominator == 0:
        return None
    numerator = sum(
        (time - mean_t) * (value - mean_v)
        for time, value in zip(times, values)
    )
    return numerator / denominator


def summarize_channel(
    rows: Sequence[Mapping[str, str]],
    value_fn: Callable[[Mapping[str, str]], float | None],
    status_fn: Callable[[Mapping[str, str]], str | None],
    *,
    times: Sequence[float | None],
    include_fn: Callable[[Mapping[str, str]], bool] | None = None,
) -> TemperatureStats:
    values: list[float] = []
    valid_times: list[float | None] = []
    missing = 0
    not_ok = 0
    total = 0
    for row, time_value in zip(rows, times):
        if include_fn is not None and not include_fn(row):
            continue
        total += 1
        value = value_fn(row)
        if value is None:
            missing += 1
            continue
        status = status_fn(row)
        if not _status_usable(status):
            not_ok += 1
            continue
        values.append(value)
        valid_times.append(time_value)
    if not values:
        return TemperatureStats(
            valid_frames=0,
            total_frames=total,
            minimum_c=None,
            maximum_c=None,
            mean_c=None,
            first_c=None,
            last_c=None,
            change_c=None,
            slope_c_per_min=None,
            missing_frames=missing,
            status_not_ok_frames=not_ok,
        )
    paired = [(time, value) for time, value in zip(valid_times, values) if time is not None]
    slope = (
        _ols_slope([pair[0] for pair in paired], [pair[1] for pair in paired])
        if len(paired) == len(values)
        else None
    )
    return TemperatureStats(
        valid_frames=len(values),
        total_frames=total,
        minimum_c=min(values),
        maximum_c=max(values),
        mean_c=statistics.fmean(values),
        first_c=values[0],
        last_c=values[-1],
        change_c=values[-1] - values[0],
        slope_c_per_min=None if slope is None else slope * 60.0,
        missing_frames=missing,
        status_not_ok_frames=not_ok,
    )


def summarize_compact_channel(
    rows: Sequence[Mapping[str, str]],
    column: str,
) -> TemperatureStats:
    """A channel with no status column: present values are descriptive only."""
    values = [value for value in (parse_float(row.get(column)) for row in rows) if value is not None]
    if not values:
        return TemperatureStats(0, len(rows), None, None, None, None, None, None, None, len(rows), 0)
    return TemperatureStats(
        valid_frames=len(values),
        total_frames=len(rows),
        minimum_c=min(values),
        maximum_c=max(values),
        mean_c=statistics.fmean(values),
        first_c=values[0],
        last_c=values[-1],
        change_c=values[-1] - values[0],
        slope_c_per_min=None,
        missing_frames=len(rows) - len(values),
        status_not_ok_frames=0,
    )


@dataclass(frozen=True)
class SpreadStats:
    valid_frames: int
    mean_c: float | None
    maximum_c: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_frames": self.valid_frames,
            "mean_c": self.mean_c,
            "maximum_c": self.maximum_c,
        }


@dataclass(frozen=True)
class DoorWindow:
    source_id: str
    open_start_s: float | None
    open_end_s: float | None
    duration_s: float | None
    frame_count: int
    pre_frames: int
    during_frames: int
    post_frames: int
    pre_mean_c: float | None
    during_mean_c: float | None
    post_mean_c: float | None
    during_minus_pre_c: float | None
    post_minus_pre_c: float | None
    time_basis: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "open_start_s": self.open_start_s,
            "open_end_s": self.open_end_s,
            "duration_s": self.duration_s,
            "frame_count": self.frame_count,
            "pre_frames": self.pre_frames,
            "during_frames": self.during_frames,
            "post_frames": self.post_frames,
            "pre_mean_c": self.pre_mean_c,
            "during_mean_c": self.during_mean_c,
            "post_mean_c": self.post_mean_c,
            "during_minus_pre_c": self.during_minus_pre_c,
            "post_minus_pre_c": self.post_minus_pre_c,
            "time_basis": self.time_basis,
            "note": self.note,
        }


@dataclass(frozen=True)
class CoolingPhase:
    active_frames: int
    start_s: float | None
    end_s: float | None
    duration_s: float | None
    air_start_c: float | None
    air_end_c: float | None
    air_change_c: float | None
    t2_start_c: float | None
    t2_end_c: float | None
    t2_change_c: float | None
    current_mean_a: float | None
    current_max_a: float | None
    power_mean_w: float | None
    power_max_w: float | None
    energy_start_wh: float | None
    energy_end_wh: float | None
    energy_delta_wh: float | None
    active_rule: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_frames": self.active_frames,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "duration_s": self.duration_s,
            "air_start_c": self.air_start_c,
            "air_end_c": self.air_end_c,
            "air_change_c": self.air_change_c,
            "t2_start_c": self.t2_start_c,
            "t2_end_c": self.t2_end_c,
            "t2_change_c": self.t2_change_c,
            "current_mean_a": self.current_mean_a,
            "current_max_a": self.current_max_a,
            "power_mean_w": self.power_mean_w,
            "power_max_w": self.power_max_w,
            "energy_start_wh": self.energy_start_wh,
            "energy_end_wh": self.energy_end_wh,
            "energy_delta_wh": self.energy_delta_wh,
            "active_rule": self.active_rule,
            "note": self.note,
        }


@dataclass(frozen=True)
class SourceMetrics:
    air: TemperatureStats | None
    t2: TemperatureStats | None
    spread: SpreadStats | None
    compact_t1_slot: TemperatureStats | None
    compact_t2_slot: TemperatureStats | None
    door_events: tuple[DoorWindow, ...]
    cooling: CoolingPhase | None
    missing: Mapping[str, int]
    quality_invalid_frames: int
    door_unknown_frames: int
    current_status_not_carried_frames: int
    analyzed_frames: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "air": None if self.air is None else self.air.to_dict(),
            "t2": None if self.t2 is None else self.t2.to_dict(),
            "spread": None if self.spread is None else self.spread.to_dict(),
            "compact_t1_slot": None
            if self.compact_t1_slot is None
            else self.compact_t1_slot.to_dict(),
            "compact_t2_slot": None
            if self.compact_t2_slot is None
            else self.compact_t2_slot.to_dict(),
            "door_events": [event.to_dict() for event in self.door_events],
            "cooling": None if self.cooling is None else self.cooling.to_dict(),
            "missing": dict(sorted(self.missing.items())),
            "quality_invalid_frames": self.quality_invalid_frames,
            "door_unknown_frames": self.door_unknown_frames,
            "current_status_not_carried_frames": self.current_status_not_carried_frames,
            "analyzed_frames": self.analyzed_frames,
        }


def _mean_or_none(values: Iterable[float | None]) -> float | None:
    kept = [value for value in values if value is not None]
    return statistics.fmean(kept) if kept else None


def _window_values(
    rows: Sequence[Mapping[str, str]],
    times: Sequence[float | None],
    *,
    start_s: float | None,
    end_s: float | None,
    frame_start: int,
    frame_end: int,
) -> list[float]:
    if start_s is not None and end_s is not None:
        values = [
            _chamber_air(row)
            for row, time_value in zip(rows, times)
            if time_value is not None and start_s <= time_value < end_s
        ]
    else:
        values = [_chamber_air(row) for row in rows[frame_start:frame_end]]
    return [value for value in values if value is not None]


def _window_mean(
    rows: Sequence[Mapping[str, str]],
    times: Sequence[float | None],
    *,
    start_s: float | None,
    end_s: float | None,
    frame_start: int,
    frame_end: int,
) -> float | None:
    return _mean_or_none(
        _window_values(
            rows,
            times,
            start_s=start_s,
            end_s=end_s,
            frame_start=frame_start,
            frame_end=frame_end,
        )
    )


def detect_door_events(
    rows: Sequence[Mapping[str, str]],
    times: Sequence[float | None],
    *,
    source_id: str,
    window_s: float = 30.0,
) -> tuple[DoorWindow, ...]:
    events: list[DoorWindow] = []
    start_index: int | None = None
    time_basis = (
        "BOOT_SCOPED_UPTIME"
        if any(value is not None for value in times)
        else "FRAME_INDEX_ONLY"
    )
    for index, row in enumerate(rows):
        status = parse_status(row.get("door_status"))
        state = _door_state(row)
        if not _status_usable(status) or state not in {"0", "1"}:
            if start_index is not None:
                start_index = None
            continue
        if state == "1" and start_index is None:
            start_index = index
        elif state == "0" and start_index is not None:
            end_index = index - 1
            events.append(
                _door_window(
                    rows,
                    times,
                    start_index,
                    end_index,
                    source_id=source_id,
                    time_basis=time_basis,
                    window_s=window_s,
                )
            )
            start_index = None
    if start_index is not None:
        events.append(
            _door_window(
                rows,
                times,
                start_index,
                len(rows) - 1,
                source_id=source_id,
                time_basis=time_basis,
                window_s=window_s,
            )
        )
    return tuple(events)


def _door_window(
    rows: Sequence[Mapping[str, str]],
    times: Sequence[float | None],
    start_index: int,
    end_index: int,
    *,
    source_id: str,
    time_basis: str,
    window_s: float,
) -> DoorWindow:
    start_s = times[start_index]
    end_s = times[end_index]
    duration = (
        (end_s - start_s) + 1.0
        if start_s is not None and end_s is not None
        else None
    )
    pre_values = _window_values(
        rows,
        times,
        start_s=(
            None if start_s is None else max(0.0, start_s - window_s)
        ),
        end_s=start_s,
        frame_start=max(0, start_index - int(window_s)),
        frame_end=start_index,
    )
    during_values = [
        value
        for value in (
            _chamber_air(row) for row in rows[start_index : end_index + 1]
        )
        if value is not None
    ]
    post_start_s = (
        times[end_index + 1]
        if end_index + 1 < len(times)
        else (None if end_s is None else end_s + 1.0)
    )
    post_values = _window_values(
        rows,
        times,
        start_s=post_start_s,
        end_s=None if post_start_s is None else post_start_s + window_s,
        frame_start=end_index + 1,
        frame_end=min(len(rows), end_index + 1 + int(window_s)),
    )
    pre = _mean_or_none(pre_values)
    during = _mean_or_none(during_values)
    post = _mean_or_none(post_values)
    return DoorWindow(
        source_id=source_id,
        open_start_s=start_s,
        open_end_s=end_s,
        duration_s=duration,
        frame_count=end_index - start_index + 1,
        pre_frames=len(pre_values),
        during_frames=len(during_values),
        post_frames=len(post_values),
        pre_mean_c=pre,
        during_mean_c=during,
        post_mean_c=post,
        during_minus_pre_c=(
            None if pre is None or during is None else during - pre
        ),
        post_minus_pre_c=None if pre is None or post is None else post - pre,
        time_basis=time_basis,
        note=(
            "recorded door-state interval; duration is within-boot uptime, "
            "not an absolute event time; sensor resolution is 0.0625 C; "
            "pre/post counts are valid chamber-air samples in the declared window"
        ),
    )


def detect_cooling_phase(
    rows: Sequence[Mapping[str, str]],
    times: Sequence[float | None],
    *,
    source_id: str,
) -> CoolingPhase | None:
    applied = False
    current_only = False
    for row in rows:
        if parse_float(row.get("pwm_applied_permille")) not in (None, 0.0):
            applied = True
            break
        if (
            parse_float(row.get("current_a")) not in (None, 0.0)
            and _status_usable(row.get("current_status"))
        ):
            current_only = True
    if not applied and not current_only:
        return None
    active_rule = (
        "PWM_APPLIED_GREATER_THAN_ZERO"
        if applied
        else "PZEM_CURRENT_GREATER_THAN_ZERO_STATUS_OK"
    )
    active: list[int] = []
    for index, row in enumerate(rows):
        if applied:
            value = parse_float(row.get("pwm_applied_permille"))
            is_active = value is not None and value > 0.0
        else:
            value = parse_float(row.get("current_a"))
            is_active = (
                value is not None
                and value > 0.0
                and _status_usable(row.get("current_status"))
            )
        if is_active:
            active.append(index)
    if len(active) < 2:
        return None
    start_index, end_index = active[0], active[-1]
    start_s = times[start_index]
    end_s = times[end_index]
    duration = (
        (end_s - start_s) + 1.0
        if start_s is not None and end_s is not None
        else None
    )
    air_values = [
        _chamber_air(rows[index]) for index in range(start_index, end_index + 1)
    ]
    t2_values = [
        (
            _slot_value(rows[index], HOT_SIDE_SLOT)
            if _status_usable(_slot_status(rows[index], HOT_SIDE_SLOT))
            else None
        )
        for index in range(start_index, end_index + 1)
    ]
    current_values = [
        value
        for value in (
            parse_float(rows[index].get("current_a"))
            for index in range(start_index, end_index + 1)
            if _status_usable(rows[index].get("current_status"))
        )
        if value is not None
    ]
    power_values = [
        value
        for value in (
            parse_float(rows[index].get("power_w"))
            for index in range(start_index, end_index + 1)
            if _status_usable(rows[index].get("power_status"))
        )
        if value is not None
    ]
    energy_start = parse_float(rows[start_index].get("energy_wh"))
    energy_end = parse_float(rows[end_index].get("energy_wh"))
    energy_delta = (
        energy_end - energy_start
        if energy_start is not None
        and energy_end is not None
        and energy_end >= energy_start
        else None
    )
    air_start = next((value for value in air_values if value is not None), None)
    air_end = next(
        (value for value in reversed(air_values) if value is not None), None
    )
    t2_start = next((value for value in t2_values if value is not None), None)
    t2_end = next(
        (value for value in reversed(t2_values) if value is not None), None
    )
    return CoolingPhase(
        active_frames=len(active),
        start_s=start_s,
        end_s=end_s,
        duration_s=duration,
        air_start_c=air_start,
        air_end_c=air_end,
        air_change_c=(
            None
            if air_start is None or air_end is None
            else air_end - air_start
        ),
        t2_start_c=t2_start,
        t2_end_c=t2_end,
        t2_change_c=(
            None if t2_start is None or t2_end is None else t2_end - t2_start
        ),
        current_mean_a=_mean_or_none(current_values),
        current_max_a=max(current_values) if current_values else None,
        power_mean_w=_mean_or_none(power_values),
        power_max_w=max(power_values) if power_values else None,
        energy_start_wh=energy_start,
        energy_end_wh=energy_end,
        energy_delta_wh=energy_delta,
        active_rule=active_rule,
        note=(
            "PZEM measures the cooling branch, not necessarily the entire "
            "system; no missing current or power is replaced by zero"
        ),
    )


def _missingness(rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    def count_channel(
        value_names: Sequence[str],
        status_name: str,
        *,
        status_carried: bool,
    ) -> dict[str, int]:
        present = status_ok = status_not_ok = value_missing = not_carried = 0
        for row in rows:
            value = _row_value(row, *value_names)
            status = parse_status(row.get(status_name)) if status_carried else None
            if value is None:
                value_missing += 1
            else:
                present += 1
            if status is None:
                not_carried += 1
            elif _status_usable(status):
                status_ok += 1
            else:
                status_not_ok += 1
        return {
            "value_present": present,
            "status_ok": status_ok,
            "status_not_ok": status_not_ok,
            "value_missing": value_missing,
            "status_not_carried": not_carried,
        }

    columns = set(rows[0].keys()) if rows else set()
    result: dict[str, int] = {}
    for slot in ("t1", "t3", "t4"):
        counts = count_channel(
            (f"{slot}_c", slot, f"chamber_c_{slot}_slot" if slot == "t1" else ""),
            f"{slot}_status",
            status_carried=f"{slot}_status" in columns,
        )
        for key, value in counts.items():
            result[f"{slot}_{key}"] = value
    counts = count_channel(
        ("t2_c", "t2", "hot_side_c_t2"),
        "t2_status",
        status_carried="t2_status" in columns,
    )
    for key, value in counts.items():
        result[f"t2_{key}"] = value
    door_status_carried = "door_status" in columns
    door_counts = count_channel(
        ("door_open",),
        "door_status",
        status_carried=door_status_carried,
    )
    for key, value in door_counts.items():
        result[f"door_{key}"] = value
    current_carried = "current_a" in columns
    current_counts = count_channel(
        ("current_a",),
        "current_status",
        status_carried="current_status" in columns,
    )
    for key, value in current_counts.items():
        result[f"current_{key}"] = value
    result["quality_invalid"] = sum(
        1 for row in rows if parse_status(row.get("quality")) == "INVALID"
    )
    result["quality_unknown"] = sum(
        1 for row in rows if parse_status(row.get("quality")) == "UNKNOWN"
    )
    result["door_unknown"] = sum(1 for row in rows if _door_state(row) is None)
    result["current_status_not_carried"] = (
        len(rows) if "current_status" not in columns and current_carried else 0
    )
    return result


def build_metrics(
    rows: Sequence[Mapping[str, str]],
    *,
    source_id: str,
    include_fn: Callable[[Mapping[str, str]], bool] | None = None,
) -> SourceMetrics:
    if not rows:
        raise RecoveryError(f"source {source_id!r} carries no frames")
    first = rows[0]
    compact = "chamber_c_t1_slot" in first
    times, _domain, _note = time_axis(rows)
    analyzed = [row for row in rows if include_fn is None or include_fn(row)]
    analyzed_times = [
        time_value
        for row, time_value in zip(rows, times)
        if include_fn is None or include_fn(row)
    ]
    air = t2 = spread = compact_t1 = compact_t2 = None
    if compact:
        compact_t1 = summarize_compact_channel(analyzed, "chamber_c_t1_slot")
        compact_t2 = summarize_compact_channel(analyzed, "hot_side_c_t2")
    else:
        air = summarize_channel(
            analyzed,
            _chamber_air,
            lambda row: "OK",
            times=analyzed_times,
        )
        t2 = summarize_channel(
            analyzed,
            lambda row: _slot_value(row, HOT_SIDE_SLOT),
            lambda row: _slot_status(row, HOT_SIDE_SLOT),
            times=analyzed_times,
        )
        spread_values = [
            value
            for value in (_sensor_spread(row) for row in analyzed)
            if value is not None
        ]
        spread = SpreadStats(
            valid_frames=len(spread_values),
            mean_c=statistics.fmean(spread_values) if spread_values else None,
            maximum_c=max(spread_values) if spread_values else None,
        )
    door_events = (
        ()
        if compact
        else detect_door_events(analyzed, analyzed_times, source_id=source_id)
    )
    cooling = (
        None
        if compact
        else detect_cooling_phase(analyzed, analyzed_times, source_id=source_id)
    )
    missing = _missingness(rows)
    return SourceMetrics(
        air=air,
        t2=t2,
        spread=spread,
        compact_t1_slot=compact_t1,
        compact_t2_slot=compact_t2,
        door_events=door_events,
        cooling=cooling,
        missing=missing,
        quality_invalid_frames=missing.get("quality_invalid", 0),
        door_unknown_frames=missing.get("door_unknown", 0),
        current_status_not_carried_frames=missing.get(
            "current_status_not_carried", 0
        ),
        analyzed_frames=len(analyzed),
    )


# ---------------------------------------------------------------------------
# Source records and inventory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_family: str
    source_path: str
    source_commit: str
    source_sha256: str
    raw_source_path: str | None
    raw_source_sha256: str | None
    device_id: str
    boot_id: str
    run_id: str | None
    run_id_status: str
    session_id: str
    scenario: str
    hardware_config_id: str
    firmware_version: str
    calibration_id: str | None
    record_count: int
    start_time: Mapping[str, Any]
    end_time: Mapping[str, Any]
    time_domain: str
    sensor_roles: Mapping[str, str]
    required_channels: tuple[str, ...]
    quality_flags: tuple[str, ...]
    door_event_availability: str
    cooling_state_availability: str
    electrical_measurement_availability: str
    a_original_verdict: str
    b_original_verdict: str
    current_verified_disposition: str
    permitted_uses: tuple[str, ...]
    refusal_reasons: tuple[str, ...]
    counts_as_independent_experiment: bool
    independent_session_count: int
    shared_boot_group: str | None
    lineage_note: str
    metrics: SourceMetrics

    def to_dict(self, *, include_metrics: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_id": self.source_id,
            "source_family": self.source_family,
            "source_path": self.source_path,
            "source_commit": self.source_commit,
            "source_sha256": self.source_sha256,
            "raw_source_path": self.raw_source_path,
            "raw_source_sha256": self.raw_source_sha256,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "run_id": self.run_id,
            "run_id_status": self.run_id_status,
            "session_id": self.session_id,
            "scenario": self.scenario,
            "hardware_config_id": self.hardware_config_id,
            "firmware_version": self.firmware_version,
            "calibration_id": self.calibration_id,
            "record_count": self.record_count,
            "start_time": dict(self.start_time),
            "end_time": dict(self.end_time),
            "time_domain": self.time_domain,
            "sensor_roles": dict(self.sensor_roles),
            "required_channels": list(self.required_channels),
            "quality_flags": list(self.quality_flags),
            "door_event_availability": self.door_event_availability,
            "cooling_state_availability": self.cooling_state_availability,
            "electrical_measurement_availability": self.electrical_measurement_availability,
            "A_original_verdict": self.a_original_verdict,
            "B_original_verdict": self.b_original_verdict,
            "current_verified_disposition": self.current_verified_disposition,
            "permitted_uses": list(self.permitted_uses),
            "refusal_reasons": list(self.refusal_reasons),
            "counts_as_independent_experiment": self.counts_as_independent_experiment,
            "independent_session_count": self.independent_session_count,
            "shared_boot_group": self.shared_boot_group,
            "lineage_note": self.lineage_note,
        }
        if include_metrics:
            payload["descriptive_metrics"] = self.metrics.to_dict()
        return payload


def _time_bounds(
    rows: Sequence[Mapping[str, str]],
    *,
    prefer_host: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    host_values = [
        str(row.get("host_time_utc"))
        for row in rows
        if row.get("host_time_utc") not in (None, "", "NOT_AVAILABLE")
    ]
    uptime_values = [
        parse_float(row.get("uptime_ms"))
        if row.get("uptime_ms") not in (None, "")
        else parse_float(row.get("device_ms"))
        for row in rows
    ]
    uptime_kept = [value for value in uptime_values if value is not None]
    if prefer_host and host_values:
        start: dict[str, Any] = {
            "value": host_values[0],
            "kind": "HOST_RECEIPT_UTC",
            "physical_event_time": False,
        }
        end: dict[str, Any] = {
            "value": host_values[-1],
            "kind": "HOST_RECEIPT_UTC",
            "physical_event_time": False,
        }
        if uptime_kept:
            start["device_uptime_s"] = uptime_kept[0] / 1000.0
            end["device_uptime_s"] = uptime_kept[-1] / 1000.0
        return start, end
    if uptime_kept:
        return (
            {
                "value": uptime_kept[0] / 1000.0,
                "unit": "s_device_uptime",
                "kind": "BOOT_SCOPED_UPTIME",
                "physical_event_time": False,
            },
            {
                "value": uptime_kept[-1] / 1000.0,
                "unit": "s_device_uptime",
                "kind": "BOOT_SCOPED_UPTIME",
                "physical_event_time": False,
            },
        )
    return (
        {"value": None, "kind": "NOT_CARRIED", "physical_event_time": False},
        {"value": None, "kind": "NOT_CARRIED", "physical_event_time": False},
    )


def _quality_flags(rows: Sequence[Mapping[str, str]], metrics: SourceMetrics) -> tuple[str, ...]:
    flags: list[str] = []
    if metrics.quality_invalid_frames:
        flags.append(f"A_ROW_QUALITY_INVALID={metrics.quality_invalid_frames}")
    if metrics.door_unknown_frames:
        flags.append(f"DOOR_STATE_UNKNOWN={metrics.door_unknown_frames}")
    if metrics.current_status_not_carried_frames:
        flags.append(
            f"CURRENT_STATUS_NOT_CARRIED={metrics.current_status_not_carried_frames}"
        )
    if metrics.missing.get("door_status_not_carried", 0):
        flags.append(
            f"DOOR_STATUS_NOT_CARRIED={metrics.missing['door_status_not_carried']}"
        )
    if any(parse_status(row.get("door_status")) == "UNVERIFIED" for row in rows):
        flags.append("DOOR_STATUS_UNVERIFIED_PRESENT")
    if any(parse_status(row.get("snapshot")) == "INVALID" for row in rows):
        flags.append("SNAPSHOT_INVALID_PRESENT")
    return tuple(flags)


def _required_channels(metrics: SourceMetrics) -> tuple[str, ...]:
    if metrics.compact_t1_slot is not None:
        return ("T1_SLOT", "T2_HOT_SIDE_SLOT")
    required = ["T1", "T3", "T4", "T2"]
    if metrics.door_events:
        required.append("DOOR")
    if metrics.cooling is not None:
        required.extend(["PWM_APPLIED", "CURRENT", "POWER"])
    return tuple(required)


def _source_uses(scenario: str, metrics: SourceMetrics) -> tuple[str, ...]:
    if scenario in {"S1_OUTSIDE", "S2_OUTSIDE"}:
        return (USE_NOT,)
    if scenario in {"S2_DOOR", "S2_TIMING"} and metrics.door_events:
        return (USE_DESCRIPTION, USE_DISTURBANCE)
    if scenario.startswith("S1") and metrics.air is not None and metrics.air.valid_frames:
        return (USE_DESCRIPTION,)
    if "COOLING" in scenario and metrics.cooling is not None:
        uses = [USE_DESCRIPTION]
        if metrics.cooling.current_mean_a is not None:
            uses.append(USE_SENSOR_DIAG)
        return tuple(uses)
    if scenario == "W07_PASSIVE_REPEAT" and metrics.compact_t1_slot is not None:
        return (USE_SENSOR_DIAG,)
    return (USE_NOT,)


def _primary_disposition(uses: Sequence[str]) -> str:
    for candidate in (USE_DISTURBANCE, USE_DESCRIPTION, USE_SENSOR_DIAG, USE_NOT):
        if candidate in uses:
            return candidate
    return USE_NOT


def _predictive_refusal_reasons(
    *,
    scenario: str,
    time_domain: str,
    run_id_status: str,
    door_events: int,
) -> tuple[str, ...]:
    reasons = [
        "EVENT_UTC_UNAVAILABLE_DEVICE_HAS_NO_WALL_CLOCK",
        "HOST_RECEIPT_TIME_IS_NOT_PHYSICAL_EVENT_TIME",
        "CALIBRATION_TRACEABILITY_ABSENT_FROM_PACKAGE_SCHEMA",
        "CRITICAL_THRESHOLD_AND_REPRESENTATIVE_T_NOT_FROZEN",
        "NO_VALID_CRITICAL_EVENT_LABEL",
    ]
    if time_domain != "BOOT_SCOPED_UPTIME":
        reasons.append("TIME_DOMAIN_INSUFFICIENT_FOR_PREDICTIVE_DATASET")
    if run_id_status != "SINGLE_SOURCE_CARRIED_RUN":
        reasons.append("RUN_IDENTITY_UNRESOLVED")
    if scenario.startswith("S2") and not door_events:
        reasons.append("DOOR_EVENT_NOT_RECORDED")
    return tuple(reasons)


def build_a_source_record(
    source: ReconciledSource,
    *,
    run_row: Mapping[str, str],
    rows: Sequence[Mapping[str, str]],
    dataset_dir: Path,
    source_revision: str,
    raw_source_sha256: str | None,
    shared_boot: bool,
    source_path_prefix: str = "evidence/A/SOURCES/20261107/datasets",
    exact_duplicate_rows: int = 0,
) -> SourceRecord:
    del dataset_dir
    metrics = build_metrics(rows, source_id=source.run_tag)
    times, time_domain, _ = time_axis(rows)
    del times
    start, end = _time_bounds(rows, prefer_host=True)
    quality_flags = _quality_flags(rows, metrics)
    if exact_duplicate_rows:
        quality_flags = (
            *quality_flags,
            f"EXACT_DUPLICATE_ROWS_DEDUPLICATED={exact_duplicate_rows}",
        )
    if (
        metrics.cooling is not None
        and metrics.cooling.active_rule == "PZEM_CURRENT_GREATER_THAN_ZERO_STATUS_OK"
    ):
        quality_flags = (*quality_flags, "PWM_APPLIED_NOT_CARRIED")
    uses = _source_uses(source.scenario, metrics)
    run_id = run_row.get("device_run_id") or None
    run_id_status = (
        "SEGMENT_ONLY_NOT_AN_INDEPENDENT_RUN"
        if run_id in {"run-00000000", "run-00000001"}
        else "UNSET_NOT_A_RUN_ID"
        if run_id in {None, "", "UNSET"}
        else "RECORDED_NOT_QUALIFIED"
    )
    refusal_reasons = list(
        _predictive_refusal_reasons(
            scenario=source.scenario,
            time_domain=time_domain,
            run_id_status=run_id_status,
            door_events=len(metrics.door_events),
        )
    )
    if source.scenario in {"S1_OUTSIDE", "S2_OUTSIDE"}:
        refusal_reasons.append("OUTSIDE_TIMED_WINDOW_NOT_AN_INDEPENDENT_RUN")
    if metrics.compact_t1_slot is not None:
        refusal_reasons.append("T3_T4_NOT_CARRIED_COMPACT_CAPTURE")
    if (
        "COOLING" in source.scenario
        and metrics.door_unknown_frames
        and not metrics.door_events
    ):
        refusal_reasons.append("DOOR_STATE_UNKNOWN_NO_DISTURBANCE_EVENT")
    door_availability = (
        "RECORDED_TRANSITIONS_WITH_OPERATOR_COMMAND_LOG"
        if metrics.door_events
        else "RECORDED_UNVERIFIED_NO_EVENT"
        if metrics.door_unknown_frames
        else "RECORDED_CLOSED_NO_EVENT"
        if source.scenario.startswith("S1")
        else "NO_RECORDED_EVENT"
    )
    cooling_availability = (
        "RECORDED_APPLIED_DUTY"
        if metrics.cooling is not None
        and metrics.cooling.active_rule == "PWM_APPLIED_GREATER_THAN_ZERO"
        else "RECORDED_PZEM_CURRENT_ONLY"
        if metrics.cooling is not None
        else "NO_COOLING_PHASE_RECORDED"
    )
    electrical_availability = (
        "PZEM_BRANCH_RECORDED_STATUS_OK"
        if metrics.current_status_not_carried_frames == 0
        and any(parse_float(row.get("current_a")) is not None for row in rows)
        else "PZEM_BRANCH_VALUES_WITHOUT_STATUS"
        if any(parse_float(row.get("current_a")) is not None for row in rows)
        else "NOT_RECORDED"
    )
    return SourceRecord(
        source_id=f"A20261107:{source.run_tag}",
        source_family="A_20261107_DATASET",
        source_path=f"{source_path_prefix.rstrip('/')}/{source.dataset_path}",
        source_commit=source_revision,
        source_sha256=source.dataset_sha256,
        raw_source_path=run_row.get("raw_source"),
        raw_source_sha256=raw_source_sha256,
        device_id="NOT_CARRIED_BY_THIS_ENCODING",
        boot_id=source.boot_id,
        run_id=run_id,
        run_id_status=run_id_status,
        session_id=f"boot:{source.boot_id}",
        scenario=source.scenario,
        hardware_config_id=str(run_row.get("hardware_config_id") or "NOT_CARRIED"),
        firmware_version=str(run_row.get("firmware_version") or "NOT_CARRIED"),
        calibration_id=None,
        record_count=int(run_row.get("frames", len(rows))),
        start_time=start,
        end_time=end,
        time_domain=time_domain,
        sensor_roles=dict(SENSOR_ROLES),
        required_channels=_required_channels(metrics),
        quality_flags=quality_flags,
        door_event_availability=door_availability,
        cooling_state_availability=cooling_availability,
        electrical_measurement_availability=electrical_availability,
        a_original_verdict=source.a_classification,
        b_original_verdict=source.b_classification,
        current_verified_disposition=_primary_disposition(uses),
        permitted_uses=uses,
        refusal_reasons=tuple(refusal_reasons),
        counts_as_independent_experiment=False,
        independent_session_count=1,
        shared_boot_group=source.boot_id if shared_boot else None,
        lineage_note=(
            "exported row/segment; the independence ceiling is the boot, not "
            "the row or window"
            + ("; this boot is shared by other exported rows" if shared_boot else "")
        ),
        metrics=metrics,
    )


def detect_duplicate_records(records: Sequence[SourceRecord]) -> list[tuple[str, str]]:
    duplicates: list[tuple[str, str]] = []
    by_hash: dict[str, str] = {}
    for record in records:
        if record.source_sha256 in by_hash:
            duplicates.append((by_hash[record.source_sha256], record.source_id))
        else:
            by_hash[record.source_sha256] = record.source_id
    return duplicates


def family_totals(
    records: Sequence[SourceRecord],
    *,
    reconciliation: Any,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    a_records = [r for r in records if r.source_family == "A_20261107_DATASET"]
    boots = sorted({r.boot_id for r in a_records})
    return {
        "segments": int(reconciliation.row_count),
        "analyzed_segments": len(a_records),
        "frames_total": int(reconciliation.frames_total),
        "distinct_boots": len(boots),
        "boot_ids": boots,
        "accepted_s1_windows": reconciliation.accepted_s1_windows,
        "accepted_s2_windows": reconciliation.accepted_s2_windows,
        "predictive_eligible_runs": reconciliation.predictive_eligible_runs,
        "independent_qualified_runs": 0,
        "independent_sessions": len(boots),
        "cooling_step_segments": sum(
            1 for r in a_records if "COOLING" in r.scenario
        ),
        "door_windows": sum(
            1 for r in a_records if r.scenario in {"S2_DOOR", "S2_TIMING"}
        ),
        "manifest_totals": dict(manifest.get("totals", {})),
        "independence_statement": (
            f"{len(a_records)} exported rows/segments span {len(boots)} "
            "distinct boots; rows and windows are never independent runs"
        ),
    }


# ---------------------------------------------------------------------------
# Predictive eligibility
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PredictiveQuestion:
    key: str
    question: str
    answer: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "question": self.question,
            "answer": self.answer,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PredictiveAssessment:
    sources: tuple[dict[str, Any], ...]
    overall: str
    overall_reasons: tuple[str, ...]
    exploratory_metrics: str
    exploratory_reasons: tuple[str, ...]
    w15_status: str
    w15_missing_features: tuple[str, ...]
    w15_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": list(self.sources),
            "overall": self.overall,
            "overall_reasons": list(self.overall_reasons),
            "exploratory_metrics": self.exploratory_metrics,
            "exploratory_reasons": list(self.exploratory_reasons),
            "w15_status": self.w15_status,
            "w15_missing_features": list(self.w15_missing_features),
            "w15_reasons": list(self.w15_reasons),
        }


def _eight_questions(record: SourceRecord) -> tuple[PredictiveQuestion, ...]:
    compact = record.metrics.compact_t1_slot is not None
    full_air = (
        record.metrics.air is not None and record.metrics.air.valid_frames > 0
    )
    door = bool(record.metrics.door_events)
    independent = record.counts_as_independent_experiment
    return (
        PredictiveQuestion(
            "physically_measured",
            "Is the source physically measured?",
            "YES",
            "A physical capture package; not a synthetic fixture.",
        ),
        PredictiveQuestion(
            "sensor_mapping",
            "Is the sensor mapping trustworthy?",
            "PARTIAL" if compact else "YES",
            (
                "Only the T1 slot and T2 slot are carried; T3/T4 are absent."
                if compact
                else "As-built role map T1=CHAMBER_CENTER, T2=TEC_HOT_SIDE, "
                "T3=CHAMBER_BOTTOM, T4=CHAMBER_NEAR_DOOR."
            ),
        ),
        PredictiveQuestion(
            "timestamps",
            "Are the relevant timestamps coherent?",
            "NO",
            "Device has no wall clock; host receipt stamps are not physical "
            "event time; only boot-scoped uptime is available.",
        ),
        PredictiveQuestion(
            "disturbance",
            "Is the disturbance/event documented?",
            "YES" if door else "NO",
            (
                "Five A-accepted S2 windows carry recorded door transitions "
                "and an operator command log."
                if door
                else "No frozen critical event or controlled disturbance "
                "belongs to this source."
            ),
        ),
        PredictiveQuestion(
            "label",
            "Is the label definition available?",
            "NO",
            "The critical Tmean threshold and representative T are not frozen; "
            "no label is invented from an unfrozen threshold.",
        ),
        PredictiveQuestion(
            "independence",
            "Is the source independent from the other runs?",
            "NO",
            "The independence ceiling is the boot; exported windows share "
            "boots, so 18 rows are not 18 independent runs.",
        ),
        PredictiveQuestion(
            "causal_features",
            "Are model features causally available before the target?",
            "NO",
            "No frozen target time exists, so a feature/target temporal order "
            "cannot be established; future features are refused.",
        ),
        PredictiveQuestion(
            "suitable_use",
            "Suitable for training, development-only evaluation, or neither?",
            "NEITHER",
            "Descriptive/diagnostic use only; predictive training and "
            "development evaluation are refused.",
        ),
    )


def assess_predictive(
    records: Sequence[SourceRecord],
) -> PredictiveAssessment:
    a_records = [r for r in records if r.source_family == "A_20261107_DATASET"]
    source_rows: list[dict[str, Any]] = []
    for record in a_records:
        questions = _eight_questions(record)
        source_rows.append(
            {
                "source_id": record.source_id,
                "scenario": record.scenario,
                "questions": [question.to_dict() for question in questions],
                "suitable_use": "NEITHER",
                "reason_codes": list(record.refusal_reasons),
            }
        )
    overall_reasons = (
        "EVENT_UTC_NOT_EVIDENCED",
        "CALIBRATION_TRACEABILITY_ABSENT",
        "RUN_IDENTITY_UNRESOLVED",
        "SEGMENTS_SHARE_BOOTS_ROWS_ARE_NOT_INDEPENDENT_RUNS",
        "CRITICAL_THRESHOLD_AND_REPRESENTATIVE_T_NOT_FROZEN",
        "NO_VALID_CRITICAL_EVENT_LABEL",
    )
    missing_features = (
        "frozen_target_label",
        "critical_tmean_threshold",
        "event_time_utc",
        "calibration_id",
        "time_since_open_for_S1",
        "ambient_temperature_c_for_S1_S2",
        "relative_humidity_pct_for_S1_S2",
    )
    return PredictiveAssessment(
        sources=tuple(source_rows),
        overall="NOT_ESTIMABLE",
        overall_reasons=overall_reasons,
        exploratory_metrics="NOT_ESTIMABLE",
        exploratory_reasons=(
            "NO_FROZEN_LABEL",
            "NO_INDEPENDENT_HELD_OUT_SOURCE_GROUP",
            "NO_PHYSICAL_EVENT_TIME",
            "FIVE_S2_DOOR_EVENTS_IN_ONE_BOOT_ONLY",
            "S1_WINDOWS_ARE_PASSIVE_WITH_NO_EVENT_LABELS",
        ),
        w15_status="SKIPPED_FEATURE_INPUT_INCOMPLETE",
        w15_missing_features=missing_features,
        w15_reasons=(
            "W15_ARTIFACT_IS_SYNTHETIC_SOFTWARE_CONTROL_ONLY",
            "W15_ARTIFACT_IS_NON_DEPLOYABLE",
            "W15_ARTIFACT_IS_RISK_SCORE_ONLY_NOT_A_PROBABILITY",
            "NO_FEATURE_COMPLETE_SOURCE_QUALIFIED_INPUT",
            "MISSING_REAL_FEATURES_ARE_NOT_FORCED",
        ),
    )


def assert_feature_time_before_target(
    feature_time_s: float, target_time_s: float
) -> None:
    if feature_time_s >= target_time_s:
        raise FutureFeatureRefused(
            f"feature time {feature_time_s!r} is not before target time "
            f"{target_time_s!r}; future information is refused"
        )


def assert_disjoint_train_test(
    train_sources: Sequence[str], test_sources: Sequence[str]
) -> None:
    overlap = sorted(set(train_sources).intersection(test_sources))
    if overlap:
        raise SourceOverlapRefused(
            f"train/test source lineage overlap is refused: {overlap}"
        )


def safe_average_precision(
    labels: Sequence[int], scores: Sequence[float] | None = None
) -> float | None:
    """Test-only AP; single-class populations stay undefined.

    This helper exists to prove that a single-class population yields no AP.
    It is never applied to physical data and never promoted to physical
    evidence.
    """
    if not labels or len(set(labels)) < 2:
        return None
    if scores is None or len(scores) != len(labels):
        raise ValueError("average precision requires one score per label")
    positives = sum(labels)
    if positives == 0 or positives == len(labels):
        return None
    ranked = sorted(
        range(len(labels)), key=lambda index: (-scores[index], index)
    )
    true_positives = 0
    false_positives = 0
    previous_recall = 0.0
    average_precision = 0.0
    for index in ranked:
        if labels[index] == 1:
            true_positives += 1
            recall = true_positives / positives
            precision = true_positives / (true_positives + false_positives)
            average_precision += (recall - previous_recall) * precision
            previous_recall = recall
        else:
            false_positives += 1
    return average_precision


def promote_metric_to_physical(evidence_class: str, metric_name: str) -> None:
    if evidence_class != EVIDENCE_PHYSICAL:
        raise SyntheticMetricPromotionRefused(
            f"{metric_name!r} has evidence class {evidence_class!r}; a "
            "non-physical metric must never be reported as physical"
        )


def w15_score_semantics() -> str:
    return "RISK_SCORE_ONLY"


def ready_for_w15_scoring(available_features: Iterable[str]) -> tuple[bool, tuple[str, ...]]:
    required = {
        "T_chamber_max_c",
        "T_chamber_min_c",
        "T_chamber_mean_c",
        "T_chamber_spread_c",
        "T_center_c",
        "T_bottom_c",
        "T_near_door_c",
        "rolling_mean_temperature_60s",
        "rolling_std_temperature_60s",
        "rolling_min_temperature_60s",
        "rolling_max_temperature_60s",
        "past_only_slope_c_per_min_60s",
        "past_only_temperature_delta_60s",
        "past_only_spatial_spread_60s",
        "door_open",
        "time_since_open",
        "duration_so_far",
        "count_past_60s",
        "applied_cooling",
        "applied_duty",
        "time_since_confirmed_applied_change",
        "cooling_voltage_v",
        "cooling_current_a",
        "cooling_power_w",
        "energy_counter_wh",
        "past_integrated_cooling_energy_wh",
        "ambient_temperature_c",
        "relative_humidity_pct",
    }
    missing = tuple(sorted(required - set(available_features)))
    return (not missing, missing)


# ---------------------------------------------------------------------------
# Gate B: run the existing authoritative validator, never a replacement
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateBResult:
    command: tuple[str, ...]
    source_path: str
    source_sha256: str
    software_status: str
    physical_status: str
    predictive_status: str
    split_status: str
    split_feasibility: str
    physical_reasons: tuple[str, ...]
    predictive_reasons: tuple[str, ...]
    split_reasons: tuple[str, ...]
    population: str
    allowed_uses: tuple[str, ...]
    prohibited_uses: tuple[str, ...]
    validator_exit_code: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "software_status": self.software_status,
            "GATE_B_PHYSICAL_DATA": self.physical_status,
            "PREDICTIVE_DATASET_READINESS": self.predictive_status,
            "SPLIT_STATUS": self.split_status,
            "SPLIT_FEASIBILITY": self.split_feasibility,
            "physical_reasons": list(self.physical_reasons),
            "predictive_reasons": list(self.predictive_reasons),
            "split_reasons": list(self.split_reasons),
            "population": self.population,
            "allowed_uses": list(self.allowed_uses),
            "prohibited_uses": list(self.prohibited_uses),
            "validator_exit_code": self.validator_exit_code,
        }


def run_gate_b(
    *,
    repo_root: Path,
    ml_root: Path,
    w05_export: Path,
    a_run_index: Path,
    repository_revision: str,
    out_dir: Path,
    timeout_s: int = 180,
) -> GateBResult:
    script = ml_root / "scripts" / "gate-b-readiness-W08.py"
    if not script.is_file():
        raise GateBRefusal(f"authoritative W08 validator is absent: {script}")
    out_dir.mkdir(parents=True, exist_ok=True)

    def _display_path(path: Path) -> str:
        try:
            return path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return path.name

    actual_command = (
        sys.executable,
        str(script),
        "--source",
        str(w05_export),
        "--a-run-index",
        str(a_run_index),
        "--scenario",
        "S1",
        "--out",
        str(out_dir),
        "--repository-revision",
        repository_revision,
    )
    display_command = (
        "python",
        "scripts/gate-b-readiness-W08.py",
        "--source",
        _display_path(w05_export),
        "--a-run-index",
        _display_path(a_run_index),
        "--scenario",
        "S1",
        "--out",
        "<GATE_B_SCRATCH>",
        "--repository-revision",
        repository_revision,
    )
    try:
        completed = subprocess.run(
            actual_command,
            cwd=str(ml_root),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateBRefusal(f"W08 validator could not run: {exc}") from exc
    manifest_path = out_dir / "gate-b-manifest-W08.json"
    if completed.returncode != 0 or not manifest_path.is_file():
        raise GateBRefusal(
            "W08 validator did not produce a valid manifest; "
            f"exit={completed.returncode} stdout={completed.stdout[-500:]!r} "
            f"stderr={completed.stderr[-500:]!r}"
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    physical = payload.get("physical_gate") or {}
    predictive = payload.get("predictive_gate") or {}
    split = payload.get("split_gate") or {}
    software = payload.get("software_gate") or {}
    split_plan = payload.get("split_plan") or {}
    physical_status = str(physical.get("observed_status", ""))
    predictive_status = str(predictive.get("observed_status", ""))
    split_status = str(split.get("observed_status", ""))
    split_feasibility = str(
        split_plan.get("status")
        or split_plan.get("feasibility")
        or ("NOT_FEASIBLE" if split_status == "RED" else "UNKNOWN")
    )
    if not physical_status or not predictive_status:
        raise GateBRefusal("W08 manifest is missing a canonical gate status")
    if physical_status == "GREEN" and predictive_status == "READY":
        # Never silently accept an unexpected promotion without a fresh audit.
        raise GateBRefusal(
            "W08 returned GREEN/READY unexpectedly; the recovery package "
            "refuses to claim a Gate B promotion without a new audit"
        )
    return GateBResult(
        command=display_command,
        source_path=_display_path(w05_export),
        source_sha256=W05_EXPORT_SHA256,
        software_status=str(software.get("observed_status", "")),
        physical_status=physical_status,
        predictive_status=predictive_status,
        split_status=split_status,
        split_feasibility=split_feasibility,
        physical_reasons=tuple(physical.get("reason_codes") or ()),
        predictive_reasons=tuple(predictive.get("reason_codes") or ()),
        split_reasons=tuple(split.get("reason_codes") or ()),
        population=str(physical.get("population", "")),
        allowed_uses=tuple(physical.get("allowed_uses") or ()),
        prohibited_uses=tuple(physical.get("prohibited_uses") or ()),
        validator_exit_code=completed.returncode,
    )


# ---------------------------------------------------------------------------
# Deterministic formatting and observation rows
# ---------------------------------------------------------------------------


def fmt(value: float | None, digits: int = 4) -> str:
    if value is None:
        return NOT_ESTIMABLE
    if abs(value) < 0.5 * 10 ** (-digits):
        value = 0.0
    return f"{value:.{digits}f}"


def _obs(
    *,
    quantity: str,
    value: str,
    unit: str,
    record: SourceRecord | None,
    source_id: str,
    source_path: str,
    source_sha256: str,
    calculation_rule: str,
    frame_count: int | str,
    independent_run_count: int,
    independent_session_count: int,
    evidence_class: str,
    limitation: str,
) -> dict[str, Any]:
    return {
        "quantity": quantity,
        "value": value,
        "unit": unit,
        "source_id": source_id,
        "source_path": source_path,
        "source_sha256": source_sha256,
        "calculation_rule": calculation_rule,
        "frame_count": frame_count,
        "independent_run_count": independent_run_count,
        "independent_session_count": independent_session_count,
        "evidence_class": evidence_class,
        "limitation": limitation,
        "record": record,
    }


def observations_for_record(record: SourceRecord) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    metrics = record.metrics
    common = dict(
        record=record,
        source_id=record.source_id,
        source_path=record.source_path,
        source_sha256=record.source_sha256,
        independent_run_count=0,
        independent_session_count=record.independent_session_count,
        evidence_class=EVIDENCE_PHYSICAL,
    )
    rows.append(
        _obs(
            quantity="recorded_frames",
            value=str(record.record_count),
            unit="frames",
            calculation_rule="count of exported normalized rows",
            frame_count=record.record_count,
            limitation="rows are segments/windows, not independent runs",
            **common,
        )
    )
    rows.append(
        _obs(
            quantity="analyzed_frames",
            value=str(metrics.analyzed_frames),
            unit="frames",
            calculation_rule="frames used after the declared row-quality filter",
            frame_count=metrics.analyzed_frames,
            limitation="row-quality filter is disclosed in quality_flags",
            **common,
        )
    )
    if metrics.air is not None:
        stats = metrics.air
        for quantity, value, unit, rule in (
            ("chamber_air_mean_c", fmt(stats.mean_c), "degC", "mean of per-frame mean(T1,T3,T4) where all three statuses are OK"),
            ("chamber_air_min_c", fmt(stats.minimum_c), "degC", "minimum per-frame mean(T1,T3,T4)"),
            ("chamber_air_max_c", fmt(stats.maximum_c), "degC", "maximum per-frame mean(T1,T3,T4)"),
            ("chamber_air_observed_change_c", fmt(stats.change_c), "degC", "last valid mean minus first valid mean"),
            ("chamber_air_ols_slope_c_per_min", fmt(stats.slope_c_per_min), "degC/min", "ordinary least squares of mean(T1,T3,T4) on boot uptime"),
        ):
            rows.append(
                _obs(
                    quantity=quantity,
                    value=value,
                    unit=unit,
                    calculation_rule=rule,
                    frame_count=stats.valid_frames,
                    limitation="T2 hot-side is never included; boot-scoped time, not absolute event time",
                    **common,
                )
            )
        rows.append(
            _obs(
                quantity="chamber_air_valid_frames",
                value=str(stats.valid_frames),
                unit="frames",
                calculation_rule="frames where T1,T3,T4 are all present and status OK",
                frame_count=stats.total_frames,
                limitation="missing/invalid frames are disclosed, never replaced by zero",
                **common,
            )
        )
        rows.append(
            _obs(
                quantity="chamber_air_missing_frames",
                value=str(stats.missing_frames),
                unit="frames",
                calculation_rule="frames where at least one of T1,T3,T4 is absent or not OK",
                frame_count=stats.total_frames,
                limitation="missingness is not zero-filled",
                **common,
            )
        )
        rows.append(
            _obs(
                quantity="chamber_air_valid_coverage",
                value=f"{stats.valid_frames / max(1, metrics.analyzed_frames):.4f}",
                unit="fraction",
                calculation_rule="valid chamber-air frames / analyzed frames",
                frame_count=stats.valid_frames,
                limitation="coverage of the analyzed row set; missing is not zero",
                **common,
            )
        )
    if metrics.t2 is not None:
        stats = metrics.t2
        for quantity, value, unit, rule in (
            ("t2_hot_side_mean_c", fmt(stats.mean_c), "degC", "mean of T2 where status is OK"),
            ("t2_hot_side_min_c", fmt(stats.minimum_c), "degC", "minimum of T2 where status is OK"),
            ("t2_hot_side_max_c", fmt(stats.maximum_c), "degC", "maximum of T2 where status is OK"),
            ("t2_hot_side_observed_change_c", fmt(stats.change_c), "degC", "last valid T2 minus first valid T2"),
            ("t2_hot_side_ols_slope_c_per_min", fmt(stats.slope_c_per_min), "degC/min", "ordinary least squares of T2 on boot uptime"),
        ):
            rows.append(
                _obs(
                    quantity=quantity,
                    value=value,
                    unit=unit,
                    calculation_rule=rule,
                    frame_count=stats.valid_frames,
                    limitation="T2 is TEC_HOT_SIDE, not chamber air; never averaged into chamber air",
                    **common,
                )
            )
        rows.append(
            _obs(
                quantity="t2_hot_side_valid_coverage",
                value=f"{stats.valid_frames / max(1, metrics.analyzed_frames):.4f}",
                unit="fraction",
                calculation_rule="valid T2 frames / analyzed frames",
                frame_count=stats.valid_frames,
                limitation="T2 coverage only; T2 is not chamber air",
                **common,
            )
        )
    if metrics.spread is not None and metrics.spread.valid_frames:
        rows.append(
            _obs(
                quantity="chamber_air_sensor_spread_mean_c",
                value=fmt(metrics.spread.mean_c),
                unit="degC",
                calculation_rule="mean over frames of max(T1,T3,T4) - min(T1,T3,T4)",
                frame_count=metrics.spread.valid_frames,
                limitation="per-frame spatial spread; sample resolution 0.0625 degC",
                **common,
            )
        )
        rows.append(
            _obs(
                quantity="chamber_air_sensor_spread_max_c",
                value=fmt(metrics.spread.maximum_c),
                unit="degC",
                calculation_rule="maximum over frames of max(T1,T3,T4) - min(T1,T3,T4)",
                frame_count=metrics.spread.valid_frames,
                limitation="observed spread, not a calibrated uncertainty",
                **common,
            )
        )
    if metrics.compact_t1_slot is not None:
        stats = metrics.compact_t1_slot
        rows.extend(
            [
                _obs(
                    quantity="t1_slot_mean_c",
                    value=fmt(stats.mean_c),
                    unit="degC",
                    calculation_rule="mean of chamber_c_t1_slot; status not carried",
                    frame_count=stats.valid_frames,
                    limitation="T1-slot only; T3/T4 absent, so this is not a chamber-air mean",
                    **common,
                ),
                _obs(
                    quantity="t1_slot_min_c",
                    value=fmt(stats.minimum_c),
                    unit="degC",
                    calculation_rule="minimum of chamber_c_t1_slot",
                    frame_count=stats.valid_frames,
                    limitation="single-slot value; no per-channel status column",
                    **common,
                ),
                _obs(
                    quantity="t1_slot_max_c",
                    value=fmt(stats.maximum_c),
                    unit="degC",
                    calculation_rule="maximum of chamber_c_t1_slot",
                    frame_count=stats.valid_frames,
                    limitation="single-slot value; no per-channel status column",
                    **common,
                ),
                _obs(
                    quantity="t1_slot_valid_coverage",
                    value=f"{stats.valid_frames / max(1, metrics.analyzed_frames):.4f}",
                    unit="fraction",
                    calculation_rule="present T1-slot values / analyzed frames",
                    frame_count=stats.valid_frames,
                    limitation="value presence only; no status column",
                    **common,
                ),
            ]
        )
    if metrics.compact_t2_slot is not None:
        stats = metrics.compact_t2_slot
        rows.extend(
            [
                _obs(
                    quantity="t2_slot_mean_c",
                    value=fmt(stats.mean_c),
                    unit="degC",
                    calculation_rule="mean of hot_side_c_t2; status not carried",
                    frame_count=stats.valid_frames,
                    limitation="T2 is TEC hot side, not chamber air",
                    **common,
                ),
                _obs(
                    quantity="t2_slot_max_c",
                    value=fmt(stats.maximum_c),
                    unit="degC",
                    calculation_rule="maximum of hot_side_c_t2",
                    frame_count=stats.valid_frames,
                    limitation="single-slot value; no per-channel status column",
                    **common,
                ),
                _obs(
                    quantity="t2_slot_valid_coverage",
                    value=f"{stats.valid_frames / max(1, metrics.analyzed_frames):.4f}",
                    unit="fraction",
                    calculation_rule="present T2-slot values / analyzed frames",
                    frame_count=stats.valid_frames,
                    limitation="value presence only; T2 is hot side",
                    **common,
                ),
            ]
        )
    for event_index, event in enumerate(metrics.door_events, start=1):
        prefix = f"door_event_{event_index}"
        for quantity, value, unit, rule, frames in (
            (f"{prefix}_duration_s", fmt(event.duration_s), "s", "last open uptime minus first open uptime plus one nominal 1 s cadence", event.frame_count),
            (f"{prefix}_pre_mean_c", fmt(event.pre_mean_c), "degC", "mean chamber air over the 30 s before the recorded open interval", event.pre_frames),
            (f"{prefix}_during_mean_c", fmt(event.during_mean_c), "degC", "mean chamber air over the recorded open interval", event.during_frames),
            (f"{prefix}_post_mean_c", fmt(event.post_mean_c), "degC", "mean chamber air over the 30 s after the recorded open interval", event.post_frames),
            (f"{prefix}_during_minus_pre_c", fmt(event.during_minus_pre_c), "degC", "during mean minus pre mean", min(event.during_frames, event.pre_frames)),
            (f"{prefix}_post_minus_pre_c", fmt(event.post_minus_pre_c), "degC", "post mean minus pre mean", min(event.post_frames, event.pre_frames)),
        ):
            rows.append(
                _obs(
                    quantity=quantity,
                    value=value,
                    unit=unit,
                    calculation_rule=rule,
                    frame_count=frames,
                    limitation="door is the recorded reported state; no absolute event time; no critical crossing is inferred",
                    **common,
                )
            )
    if metrics.cooling is not None:
        cooling = metrics.cooling
        for quantity, value, unit, rule in (
            ("cooling_active_frames", str(cooling.active_frames), "frames", "frames satisfying " + cooling.active_rule),
            ("cooling_active_duration_s", fmt(cooling.duration_s), "s", "last active uptime minus first active uptime plus one cadence"),
            ("cooling_phase_air_change_c", fmt(cooling.air_change_c), "degC", "last valid chamber air in the active phase minus first valid chamber air"),
            ("cooling_phase_t2_change_c", fmt(cooling.t2_change_c), "degC", "last valid T2 in the active phase minus first valid T2"),
            ("cooling_current_mean_a", fmt(cooling.current_mean_a), "A", "mean PZEM current in the active phase where status is OK"),
            ("cooling_power_mean_w", fmt(cooling.power_mean_w), "W", "mean PZEM power in the active phase where status is OK"),
            ("cooling_energy_delta_wh", fmt(cooling.energy_delta_wh), "Wh", "last minus first recorded energy counter; negative/reset deltas are NOT_ESTIMABLE"),
        ):
            rows.append(
                _obs(
                    quantity=quantity,
                    value=value,
                    unit=unit,
                    calculation_rule=rule,
                    frame_count=cooling.active_frames,
                    limitation=(
                        "PZEM measures the cooling branch, not the whole system; "
                        "no missing value is zero-filled; source quality flags: "
                        + ("; ".join(record.quality_flags) or "none")
                    ),
                    **common,
                )
            )
    for key, value in sorted(metrics.missing.items()):
        rows.append(
            _obs(
                quantity=f"missingness_{key}",
                value=str(value),
                unit="frames",
                calculation_rule="explicit per-channel count; no zero substitution",
                frame_count=record.record_count,
                limitation="counts describe missing/invalid/unknown periods, not measurements",
                **common,
            )
        )
    return rows


def family_observations(
    *,
    family: Mapping[str, Any],
    manifest_sha256: str,
    source_path: str,
) -> list[dict[str, Any]]:
    common = dict(
        record=None,
        source_id="A20261107:DATASET",
        source_path=source_path,
        source_sha256=manifest_sha256,
        independent_run_count=0,
        independent_session_count=int(family["independent_sessions"]),
        evidence_class=EVIDENCE_PHYSICAL,
    )
    rows = []
    for quantity, value, unit, rule, limitation in (
        ("family_segments", str(family["segments"]), "segments", "count of exported rows/segments", "segments are not independent runs"),
        ("family_frames", str(family["frames_total"]), "frames", "sum of exported normalized row counts", "frame count is not a sample size for a predictive benchmark"),
        ("family_distinct_boots", str(family["distinct_boots"]), "boots", "count of distinct boot_id values", "the boot is the independence ceiling"),
        ("family_accepted_s1_windows", str(family["accepted_s1_windows"]), "windows", "A classification DATASET_ACCEPTED_S1", "A scenario acceptance is not B predictive eligibility"),
        ("family_accepted_s2_windows", str(family["accepted_s2_windows"]), "windows", "A classification DATASET_ACCEPTED_S2", "A scenario acceptance is not B predictive eligibility"),
        ("family_predictive_eligible_runs", str(family["predictive_eligible_runs"]), "runs", "W08/W13 admission ladder applied to the exported rows", "zero eligible predictive runs"),
        ("family_independent_sessions", str(family["independent_sessions"]), "sessions", "distinct boot_id count", "one physical session is not a statistical population"),
    ):
        rows.append(
            _obs(
                quantity=quantity,
                value=value,
                unit=unit,
                calculation_rule=rule,
                frame_count=int(family["frames_total"]),
                limitation=limitation,
                **common,
            )
        )
    return rows


def timing_observations(
    timing: PlantTiming,
    *,
    source_path: str,
    source_sha256: str = A_W13_TIMING_REPORT_SHA256,
) -> list[dict[str, Any]]:
    common = dict(
        record=None,
        source_id="A-W13:PLANT_TIMING",
        source_path=source_path,
        source_sha256=source_sha256,
        independent_run_count=0,
        independent_session_count=1,
        evidence_class=EVIDENCE_DERIVED_TIMING,
    )
    rows = [
        _obs(
            quantity="command_to_electrical_median_s",
            value=fmt(timing.command_to_electrical_s),
            unit="s",
            calculation_rule="A host-analysis command-accept to PZEM onset; n=1 console trace",
            frame_count=NOT_APPLICABLE,
            limitation="single observation, +/-1 s poll quantization; not a distribution and not a measured EWT",
            **common,
        ),
        _obs(
            quantity="command_to_thermal_s",
            value=fmt(timing.command_to_thermal_s),
            unit="s",
            calculation_rule="A host-analysis applied-on to first 1 degC thermal response",
            frame_count=NOT_APPLICABLE,
            limitation="truncation-biased proxy on one boot; not a measured warning lead time",
            **common,
        ),
        _obs(
            quantity="cooling_tau_proxy_s",
            value=fmt(timing.cooling_tau_s),
            unit="s",
            calculation_rule="A host-analysis cooling tau proxy from observed endpoints",
            frame_count=NOT_APPLICABLE,
            limitation="uses the observed swing; a run not at steady state under-estimates tau",
            **common,
        ),
        _obs(
            quantity="recovery_tau_proxy_s",
            value=fmt(timing.recovery_tau_s),
            unit="s",
            calculation_rule="A host-analysis recovery tau proxy from observed endpoints",
            frame_count=NOT_APPLICABLE,
            limitation="truncation-biased proxy; not a physical recovery model",
            **common,
        ),
        _obs(
            quantity="passive_drift_c",
            value=fmt(timing.passive_drift_c),
            unit="degC",
            calculation_rule="A host-analysis passive drift over the recorded window",
            frame_count=NOT_APPLICABLE,
            limitation="derived from a passive window; not a repeatability result",
            **common,
        ),
        _obs(
            quantity="passive_window_min",
            value=fmt(timing.passive_window_min),
            unit="min",
            calculation_rule="recorded passive window duration",
            frame_count=NOT_APPLICABLE,
            limitation="single window; no passive tau asserted",
            **common,
        ),
        _obs(
            quantity="door_to_critical_s",
            value=NOT_ESTIMABLE,
            unit="s",
            calculation_rule="NOT_COMPUTABLE because the critical definition is unfrozen",
            frame_count=NOT_APPLICABLE,
            limitation="no number is invented; offline rerun is possible once the threshold is frozen",
            **common,
        ),
        _obs(
            quantity="EWT",
            value=NOT_ESTIMABLE,
            unit="s",
            calculation_rule="no qualified non-intervened trajectory with frozen warning and reactive anchors",
            frame_count=NOT_APPLICABLE,
            limitation="NOT_ESTIMABLE, never a zero",
            **common,
        ),
        _obs(
            quantity="AIW",
            value=NOT_ESTIMABLE,
            unit="s",
            calculation_rule="no measured non-overlapping latency chain",
            frame_count=NOT_APPLICABLE,
            limitation="NOT_ESTIMABLE, never a zero",
            **common,
        ),
    ]
    return rows


# ---------------------------------------------------------------------------
# SVG rendering (deterministic, no external plotting dependency)
# ---------------------------------------------------------------------------


_SERIES_COLORS = ("#1f4e79", "#b45309", "#2f7d32", "#8b1e3f", "#5b5b5b")


def _svg_number(value: float) -> str:
    text = f"{value:.2f}"
    if text.endswith(".00"):
        return text[:-3]
    if text.endswith("0"):
        return text[:-1]
    return text


def _polyline_segments(
    points: Sequence[tuple[float, float | None]],
) -> list[list[tuple[float, float]]]:
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for x, y in points:
        if y is None:
            if len(current) > 1:
                segments.append(current)
            current = []
        else:
            current.append((x, y))
    if len(current) > 1:
        segments.append(current)
    return segments


def _nice_bounds(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    low, high = min(values), max(values)
    if low == high:
        pad = 1.0 if low == 0 else abs(low) * 0.05
        return low - pad, high + pad
    pad = (high - low) * 0.08
    return low - pad, high + pad


def _wrap_text(text: str, max_chars: int = 148) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        if current and length + 1 + len(word) > max_chars:
            lines.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += (1 if current[:-1] else 0) + len(word)
    if current:
        lines.append(" ".join(current))
    return lines or [""]


def render_line_svg(
    *,
    title: str,
    subtitle: str,
    panels: Sequence[Mapping[str, Any]],
    footer: str,
    width: int = 900,
) -> str:
    panel_height = 170
    gap = 42
    subtitle_lines = _wrap_text(subtitle)
    footer_lines = _wrap_text(footer)
    top = 66 + (len(subtitle_lines) - 1) * 12
    bottom = 70 + (len(footer_lines) - 1) * 12
    height = top + panel_height * len(panels) + gap * max(0, len(panels) - 1) + bottom
    left = 78
    right = 24
    plot_width = width - left - right
    footer_start = height - 44 - (len(footer_lines) - 1) * 12
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{left}" y="24" font-size="15" font-weight="700" fill="#111">'
        f"{escape(title)}</text>",
    ]
    for index, line in enumerate(subtitle_lines):
        parts.append(
            f'<text x="{left}" y="{42 + index * 12}" font-size="10" fill="#444">'
            f"{escape(line)}</text>"
        )
    for index, line in enumerate(footer_lines):
        parts.append(
            f'<text x="{left}" y="{footer_start + index * 12}" font-size="10" '
            f'fill="#444">{escape(line)}</text>'
        )
    parts.append(
        f'<text x="{left}" y="{height - 28}" font-size="10" fill="#b00020">'
        "PHYSICAL_RECORDED_DATA; no smoothing; gaps are missing data, not zero"
        "</text>"
    )
    for panel_index, panel in enumerate(panels):
        y0 = top + panel_index * (panel_height + gap)
        label = str(panel.get("label", ""))
        y_label = str(panel.get("y_label", ""))
        series = list(panel.get("series") or [])
        all_points: list[tuple[float, float | None]] = []
        for item in series:
            all_points.extend(item.get("points") or [])
        x_values = [x for x, _ in all_points]
        y_values = [y for _, y in all_points if y is not None]
        x_min, x_max = (min(x_values), max(x_values)) if x_values else (0.0, 1.0)
        if x_min == x_max:
            x_max = x_min + 1.0
        y_min = panel.get("y_min")
        y_max = panel.get("y_max")
        if y_min is None or y_max is None:
            y_min, y_max = _nice_bounds(y_values)
        if y_min == y_max:
            y_max = y_min + 1.0
        scale_x = lambda value: left + (value - x_min) / (x_max - x_min) * plot_width
        scale_y = lambda value: y0 + panel_height - (value - y_min) / (y_max - y_min) * panel_height
        parts.append(
            f'<rect x="{left}" y="{y0}" width="{plot_width}" height="{panel_height}" '
            'fill="#fbfbfb" stroke="#cccccc"/>'
        )
        for grid_index in range(5):
            fraction = grid_index / 4.0
            grid_y = y0 + panel_height * (1.0 - fraction)
            grid_value = y_min + fraction * (y_max - y_min)
            parts.append(
                f'<line x1="{left}" y1="{_svg_number(grid_y)}" x2="{left + plot_width}" '
                f'y2="{_svg_number(grid_y)}" stroke="#e6e6e6"/>'
            )
            parts.append(
                f'<text x="{left - 6}" y="{_svg_number(grid_y + 3)}" '
                f'font-size="9" text-anchor="end" fill="#555">{_svg_number(grid_value)}</text>'
            )
        parts.append(
            f'<text x="{left}" y="{y0 - 8}" font-size="11" font-weight="600" fill="#111">'
            f"{escape(label)}</text>"
        )
        parts.append(
            f'<text x="{left - 6}" y="{y0 - 8}" font-size="9" text-anchor="end" '
            f'fill="#555">{escape(y_label)}</text>'
        )
        for series_index, item in enumerate(series):
            color = str(item.get("color") or _SERIES_COLORS[series_index % len(_SERIES_COLORS)])
            points = list(item.get("points") or [])
            for segment in _polyline_segments(points):
                coordinates = " ".join(
                    f"{_svg_number(scale_x(x))},{_svg_number(scale_y(y))}"
                    for x, y in segment
                )
                parts.append(
                    f'<polyline points="{coordinates}" fill="none" stroke="{color}" '
                    'stroke-width="1.5"/>'
                )
            legend_x = left + 8 + series_index * 150
            parts.append(
                f'<rect x="{legend_x}" y="{y0 + 6}" width="10" height="3" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{legend_x + 14}" y="{y0 + 11}" font-size="9" fill="#222">'
                f"{escape(str(item.get('name', '')))}</text>"
            )
        parts.append(
            f'<text x="{left + plot_width}" y="{y0 + panel_height + 14}" '
            'font-size="9" text-anchor="end" fill="#555">boot uptime (s) / frame index</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_missingness_svg(
    *,
    records: Sequence[SourceRecord],
    title: str,
    subtitle: str,
    footer: str,
    width: int = 1000,
) -> str:
    columns = [
        ("t1", "T1"),
        ("t3", "T3"),
        ("t4", "T4"),
        ("t2", "T2"),
        ("door", "DOOR"),
        ("current", "PZEM"),
    ]
    row_height = 27
    top = 90
    left = 300
    column_width = 108
    bar_width = 92
    right = 24
    bottom = 76
    subtitle_lines = _wrap_text(subtitle, 160)
    footer_lines = _wrap_text(footer, 160)
    top += (len(subtitle_lines) - 1) * 12
    bottom += (len(footer_lines) - 1) * 12
    height = top + row_height * max(1, len(records)) + bottom
    footer_start = height - 44 - (len(footer_lines) - 1) * 12
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="24" y="24" font-size="15" font-weight="700" fill="#111">'
        f"{escape(title)}</text>",
    ]
    for index, line in enumerate(subtitle_lines):
        parts.append(
            f'<text x="24" y="{42 + index * 12}" font-size="10" fill="#444">'
            f"{escape(line)}</text>"
        )
    header_y = top - 16
    for column_index, (_key, label) in enumerate(columns):
        x = left + column_index * column_width
        parts.append(
            f'<text x="{x}" y="{header_y}" font-size="9" font-weight="700" '
            f'fill="#222">{escape(label)}</text>'
        )
    for index, record in enumerate(records):
        y0 = top + index * row_height
        label = record.source_id
        if len(label) > 38:
            label = label[:36] + "…"
        parts.append(
            f'<text x="24" y="{y0 + 16}" font-size="9" fill="#222">'
            f"{escape(label)}</text>"
        )
        missing = record.metrics.missing
        analyzed = max(1, record.metrics.analyzed_frames)
        for column_index, (key, _label) in enumerate(columns):
            status_not_carried = missing.get(f"{key}_status_not_carried", 0)
            if status_not_carried >= record.metrics.analyzed_frames:
                value = missing.get(f"{key}_value_present", 0)
                color = "#b45309"
            else:
                value = missing.get(f"{key}_status_ok", 0)
                color = "#1f4e79"
            value = min(value, analyzed)
            fraction = max(0.0, min(1.0, value / analyzed))
            x = left + column_index * column_width
            parts.append(
                f'<rect x="{x}" y="{y0 + 5}" width="{bar_width}" height="10" fill="#eeeeee"/>'
            )
            parts.append(
                f'<rect x="{x}" y="{y0 + 5}" width="{_svg_number(fraction * bar_width)}" '
                f'height="10" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{x}" y="{y0 + 25}" font-size="8" fill="#555">'
                f"{value}/{analyzed}</text>"
            )
    for index, line in enumerate(footer_lines):
        parts.append(
            f'<text x="24" y="{footer_start + index * 12}" font-size="10" '
            f'fill="#444">{escape(line)}</text>'
        )
    parts.append(
        f'<text x="24" y="{height - 28}" font-size="10" fill="#b00020">'
        "Bars show the fraction of analyzed frames with a usable value; "
        "blue=status OK, orange=value present without a status column; "
        "missing is not zero</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def plot_source_for_record(
    record: SourceRecord,
    rows: Sequence[Mapping[str, str]],
    *,
    include_fn: Callable[[Mapping[str, str]], bool] | None = None,
) -> dict[str, Any]:
    times, _domain, _note = time_axis(rows)
    x_values = [
        (time if time is not None else float(index))
        for index, time in enumerate(times)
    ]
    series = []
    for slot, name in (
        ("t1", "T1 CHAMBER_CENTER"),
        ("t3", "T3 CHAMBER_BOTTOM"),
        ("t4", "T4 CHAMBER_NEAR_DOOR"),
    ):
        points = []
        for index, row in enumerate(rows):
            if include_fn is not None and not include_fn(row):
                continue
            if compact_record(record):
                value = None
            else:
                value = (
                    _slot_value(row, slot)
                    if _status_usable(_slot_status(row, slot))
                    else None
                )
            points.append((x_values[index], value))
        series.append({"name": name, "points": points})
    air_points = []
    for index, row in enumerate(rows):
        if include_fn is not None and not include_fn(row):
            continue
        air_points.append(
            (x_values[index], None if compact_record(record) else _chamber_air(row))
        )
    series.append({"name": "air mean (T1,T3,T4)", "points": air_points})
    return {
        "label": f"chamber air — {record.source_id}",
        "y_label": "degC",
        "series": series,
    }


def compact_record(record: SourceRecord) -> bool:
    return record.metrics.compact_t1_slot is not None


def plot_t2_panel(
    record: SourceRecord,
    rows: Sequence[Mapping[str, str]],
    *,
    include_fn: Callable[[Mapping[str, str]], bool] | None = None,
) -> dict[str, Any]:
    times, _domain, _note = time_axis(rows)
    x_values = [
        (time if time is not None else float(index))
        for index, time in enumerate(times)
    ]
    points = []
    for index, row in enumerate(rows):
        if include_fn is not None and not include_fn(row):
            continue
        value = (
            _slot_value(row, HOT_SIDE_SLOT)
            if _status_usable(_slot_status(row, HOT_SIDE_SLOT))
            else None
        )
        points.append((x_values[index], value))
    return {
        "label": f"T2 TEC_HOT_SIDE — {record.source_id} (not chamber air)",
        "y_label": "degC",
        "series": [{"name": "T2 hot side", "points": points}],
    }


def plot_door_panels(
    record: SourceRecord,
    rows: Sequence[Mapping[str, str]],
    *,
    include_fn: Callable[[Mapping[str, str]], bool] | None = None,
) -> list[dict[str, Any]]:
    times, _domain, _note = time_axis(rows)
    x_values = [
        (time if time is not None else float(index))
        for index, time in enumerate(times)
    ]
    air_points = []
    door_points = []
    for index, row in enumerate(rows):
        if include_fn is not None and not include_fn(row):
            continue
        air_points.append((x_values[index], _chamber_air(row)))
        state = _door_state(row)
        value = 1.0 if state == "1" else 0.0 if state == "0" else None
        door_points.append((x_values[index], value))
    return [
        {
            "label": f"recorded door state — {record.source_id}",
            "y_label": "0/1",
            "y_min": -0.5,
            "y_max": 1.5,
            "series": [
                {
                    "name": "door 1=open, 0=closed",
                    "points": door_points,
                    "color": "#8b1e3f",
                }
            ],
        },
        {
            "label": f"chamber air during the same window — {record.source_id}",
            "y_label": "degC",
            "series": [
                {
                    "name": "air mean (T1,T3,T4)",
                    "points": air_points,
                    "color": "#1f4e79",
                }
            ],
        },
    ]


def plot_cooling_panels(
    record: SourceRecord,
    rows: Sequence[Mapping[str, str]],
    *,
    include_fn: Callable[[Mapping[str, str]], bool] | None = None,
) -> list[dict[str, Any]]:
    times, _domain, _note = time_axis(rows)
    x_values = [
        (time if time is not None else float(index))
        for index, time in enumerate(times)
    ]
    air_points = []
    t2_points = []
    current_points = []
    for index, row in enumerate(rows):
        if include_fn is not None and not include_fn(row):
            continue
        air_points.append((x_values[index], _chamber_air(row)))
        t2_points.append(
            (
                x_values[index],
                _slot_value(row, HOT_SIDE_SLOT)
                if _status_usable(_slot_status(row, HOT_SIDE_SLOT))
                else None,
            )
        )
        current_points.append(
            (
                x_values[index],
                parse_float(row.get("current_a"))
                if _status_usable(row.get("current_status"))
                else None,
            )
        )
    return [
        {
            "label": f"chamber air — {record.source_id}",
            "y_label": "degC",
            "series": [{"name": "air mean (T1,T3,T4)", "points": air_points}],
        },
        {
            "label": "T2 TEC hot side (not chamber air)",
            "y_label": "degC",
            "series": [{"name": "T2", "points": t2_points, "color": "#b45309"}],
        },
        {
            "label": "PZEM cooling-branch current (status OK only)",
            "y_label": "A",
            "series": [{"name": "current", "points": current_points, "color": "#2f7d32"}],
        },
    ]


# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return list(reader.fieldnames or []), rows


def deduplicate_rows(
    rows: Sequence[Mapping[str, str]], source_id: str
) -> tuple[list[dict[str, str]], int]:
    """Drop exact duplicate rows; refuse contradictory duplicate frame keys."""
    seen: dict[tuple[str, str], dict[str, str]] = {}
    kept: list[dict[str, str]] = []
    exact_duplicates = 0
    for row in rows:
        materialized = dict(row)
        sequence = materialized.get("seq")
        if sequence in (None, ""):
            kept.append(materialized)
            continue
        key = (str(materialized.get("boot_id", "")), str(sequence))
        if key in seen:
            if seen[key] == materialized:
                exact_duplicates += 1
                continue
            raise DuplicateSourceError(
                f"source {source_id!r} carries contradictory rows for "
                f"boot/seq={key}"
            )
        seen[key] = materialized
        kept.append(materialized)
    return kept, exact_duplicates


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration:
            raise RecoveryError(f"{path} is empty") from None


def load_a_dataset(
    *,
    a_dataset_dir: Path,
    run_index_path: Path,
    manifest_path: Path,
    run_index_sha256: str,
    manifest_sha256: str,
    source_revision: str,
    timing: PlantTiming,
    source_path_prefix: str = "evidence/A/SOURCES/20261107/datasets",
) -> tuple[Any, Mapping[str, Any], list[SourceRecord], list[dict[str, Any]]]:
    run_index_bytes = run_index_path.read_bytes()
    manifest_bytes = manifest_path.read_bytes()
    verify_sha256(run_index_bytes, run_index_sha256, "A run_index.csv")
    verify_sha256(manifest_bytes, manifest_sha256, "A package manifest")
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    run_rows = list(csv.DictReader(io.StringIO(run_index_bytes.decode("utf-8"))))
    if not run_rows:
        raise RecoveryError("A run_index.csv carries no rows")
    header_path = None
    for candidate in run_rows:
        path = a_dataset_dir / candidate["dataset_path"]
        if path.is_file():
            header_path = path
            break
    if header_path is None:
        raise RecoveryError(
            "none of the A normalized CSV sources is present in the export"
        )
    header = _read_header(header_path)
    reconciliation = reconcile_a_dataset(
        run_index_bytes,
        manifest_bytes,
        normalized_header=header,
        timing=timing,
        critical_criterion_frozen=False,
        run_index_sha256=run_index_sha256,
        manifest_sha256=manifest_sha256,
        source_revision=source_revision,
    )
    output_pins = {
        entry["package_path"]: entry["sha256"]
        for entry in manifest.get("outputs", [])
    }
    input_pins = {
        entry["package_path"]: entry["sha256"]
        for entry in manifest.get("inputs", [])
    }
    boot_counts: dict[str, int] = {}
    for row in run_rows:
        boot_counts[row["boot_id"]] = boot_counts.get(row["boot_id"], 0) + 1
    records: list[SourceRecord] = []
    unavailable: list[dict[str, Any]] = []
    for run_row, source in zip(run_rows, reconciliation.sources):
        csv_path = a_dataset_dir / source.dataset_path
        if not csv_path.is_file():
            unavailable.append(
                {
                    "source_id": f"A20261107:{source.run_tag}",
                    "source_path": f"{source_path_prefix.rstrip('/')}/{source.dataset_path}",
                    "source_sha256": source.dataset_sha256,
                    "status": USE_UNAVAILABLE,
                    "reason": "EXPORTED_NORMALIZED_CSV_NOT_PRESENT",
                }
            )
            continue
        observed = csv_path.read_bytes()
        digest = verify_sha256(
            observed, source.dataset_sha256, f"dataset {csv_path.name}"
        )
        if output_pins.get(source.dataset_path) != digest:
            raise SourceIntegrityError(
                f"source {source.run_tag!r} output pin disagrees with bytes"
            )
        _header, rows = _read_csv_rows(csv_path)
        if len(rows) != int(run_row["frames"]):
            raise SourceIntegrityError(
                f"source {source.run_tag!r} row count {len(rows)} disagrees "
                f"with run_index frames {run_row['frames']}"
            )
        rows, exact_duplicates = deduplicate_rows(rows, source.run_tag)
        raw_source = run_row.get("raw_source") or None
        raw_sha = input_pins.get(raw_source) if raw_source else None
        records.append(
            build_a_source_record(
                source,
                run_row=run_row,
                rows=rows,
                dataset_dir=a_dataset_dir,
                source_revision=source_revision,
                raw_source_sha256=raw_sha,
                shared_boot=boot_counts.get(source.boot_id, 0) > 1,
                source_path_prefix=source_path_prefix,
                exact_duplicate_rows=exact_duplicates,
            )
        )
    duplicates = detect_duplicate_records(records)
    if duplicates:
        raise DuplicateSourceError(
            f"duplicate source bytes detected: {duplicates}"
        )
    return reconciliation, manifest, records, unavailable


def load_w05(
    *,
    export_path: Path,
    row_validity_path: Path,
    raw_path: Path | None,
    repository_revision: str,
) -> SourceRecord:
    export_bytes = export_path.read_bytes()
    verify_sha256(export_bytes, W05_EXPORT_SHA256, "W05 export")
    verify_sha256(
        row_validity_path.read_bytes(), W05_ROW_VALIDITY_SHA256, "W05 row validity"
    )
    if raw_path is not None:
        verify_sha256(raw_path.read_bytes(), W05_RAW_SHA256, "W04 raw capture")
    metadata = json.loads(export_bytes.decode("utf-8"))
    _header, rows = _read_csv_rows(row_validity_path)
    rows, exact_duplicates = deduplicate_rows(rows, "W05A:CG-S1-H8C-600S")
    include = lambda row: parse_status(row.get("quality")) != "INVALID"
    metrics = build_metrics(
        rows, source_id="W05A:CG-S1-H8C-600S", include_fn=include
    )
    start, end = _time_bounds(rows, prefer_host=False)
    invalidation = metadata.get("invalidation", {})
    summary = invalidation.get("summary", {})
    quality_counts = summary.get("quality_counts", {})
    flags = [
        "AUTHORITY_A_LEDGER_INVALID",
        (
            "SNAPSHOT_INVALID="
            f"{quality_counts.get('INVALID', metrics.quality_invalid_frames)}"
        ),
        f"THERMALLY_USABLE={invalidation.get('rows_thermally_usable', 'UNKNOWN')}",
        f"DOOR_STATE_UNKNOWN={metrics.door_unknown_frames}",
        "ELECTRICAL_STATUS_NOT_CARRIED_IN_RAW",
    ]
    if exact_duplicates:
        flags.append(f"EXACT_DUPLICATE_ROWS_DEDUPLICATED={exact_duplicates}")
    reasons = (
        "AUTHORITY_A_LEDGER_INVALID",
        "RUN_IDENTITY_UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT",
        "EVENT_UTC_UNAVAILABLE_DEVICE_HAS_NO_WALL_CLOCK",
        "CALIBRATION_TRACEABILITY_ABSENT",
        "DOOR_STATE_UNKNOWN_NO_RECORDED_EVENT",
        "ELECTRICAL_STATUS_NOT_CARRIED",
        "CRITICAL_THRESHOLD_AND_REPRESENTATIVE_T_NOT_FROZEN",
        "NO_VALID_CRITICAL_EVENT_LABEL",
    )
    return SourceRecord(
        source_id="W05A:CG-S1-H8C-600S",
        source_family="W05_A_EXPORT",
        source_path=row_validity_path.as_posix(),
        source_commit=repository_revision,
        source_sha256=W05_ROW_VALIDITY_SHA256,
        raw_source_path=raw_path.as_posix() if raw_path is not None else None,
        raw_source_sha256=W05_RAW_SHA256 if raw_path is not None else None,
        device_id=str(metadata.get("device_id") or "NOT_CARRIED"),
        boot_id=str(metadata.get("boot_id") or "UNKNOWN"),
        run_id=None,
        run_id_status=str(metadata.get("run_id_status") or "UNRESOLVED"),
        session_id=f"boot:{metadata.get('boot_id')}",
        scenario="S1_NORMAL_BASELINE_CANDIDATE_LEDGER_INVALID",
        hardware_config_id=str(metadata.get("hardware_config_id") or "NOT_CARRIED"),
        firmware_version=str(metadata.get("firmware_version") or "NOT_CARRIED"),
        calibration_id=None,
        record_count=len(rows),
        start_time=start,
        end_time=end,
        time_domain="BOOT_SCOPED_UPTIME",
        sensor_roles=dict(SENSOR_ROLES),
        required_channels=_required_channels(metrics),
        quality_flags=tuple(flags),
        door_event_availability="RECORDED_DOOR_STATE_UNKNOWN_NO_EVENT",
        cooling_state_availability=(
            "RECORDED_APPLIED_DUTY"
            if metrics.cooling is not None
            else "NO_COOLING_PHASE_RECORDED"
        ),
        electrical_measurement_availability="PZEM_BRANCH_VALUES_WITHOUT_STATUS",
        a_original_verdict="A_LEDGER_INVALID",
        b_original_verdict="PHYSICAL_DIAGNOSTIC_ONLY",
        current_verified_disposition=_primary_disposition(
            (USE_DESCRIPTION, USE_SENSOR_DIAG)
        ),
        permitted_uses=(USE_DESCRIPTION, USE_SENSOR_DIAG),
        refusal_reasons=reasons,
        counts_as_independent_experiment=False,
        independent_session_count=1,
        shared_boot_group=str(metadata.get("boot_id") or "UNKNOWN"),
        lineage_note=(
            "row-validity CSV is the per-frame source for these values; the "
            "W05 export JSON (f6235e23...) is metadata and the W04 raw CSV "
            "(f8716b51...) is the raw capture; all three are one physical "
            "recording, same as A20261107:H8-C-600s-TEC-100pct, and are never "
            "counted twice"
        ),
        metrics=metrics,
    )


def load_w21(
    *,
    manifest_path: Path,
    repository_revision: str,
) -> tuple[SourceRecord, Mapping[str, Any]]:
    manifest_bytes = manifest_path.read_bytes()
    verify_sha256(manifest_bytes, W21_MANIFEST_SHA256, "W21 manifest")
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    identity = manifest.get("session_identity") or {}
    metrics = SourceMetrics(
        air=None,
        t2=None,
        spread=None,
        compact_t1_slot=None,
        compact_t2_slot=None,
        door_events=(),
        cooling=None,
        missing={},
        quality_invalid_frames=0,
        door_unknown_frames=0,
        current_status_not_carried_frames=0,
        analyzed_frames=0,
    )
    record = SourceRecord(
        source_id="A-W21:02_03",
        source_family="W21_ON_DEVICE",
        source_path=manifest_path.as_posix(),
        source_commit=repository_revision,
        source_sha256=W21_MANIFEST_SHA256,
        raw_source_path=None,
        raw_source_sha256=W21_RAW_LOG_SHA256,
        device_id=str(identity.get("device_id") or "coldguard-001"),
        boot_id=str(identity.get("boot_id") or "4cf9be5f"),
        run_id=None,
        run_id_status="TWO_TEST_IDS_ONE_BOOT",
        session_id=str(identity.get("session") or "W21-02_W21-03_combined"),
        scenario="A-W21-02_03_ON_DEVICE_INJECTION",
        hardware_config_id="CG-HW-001",
        firmware_version="cg-w06-0.1.0",
        calibration_id=None,
        record_count=int(identity.get("total_recorded_frames", 100)),
        start_time={
            "value": None,
            "kind": "NOT_CARRIED",
            "physical_event_time": False,
        },
        end_time={
            "value": None,
            "kind": "NOT_CARRIED",
            "physical_event_time": False,
        },
        time_domain="DEVICE_BOOT_SCOPED_NO_TIMESTAMPS",
        sensor_roles=dict(SENSOR_ROLES),
        required_channels=("T1_DIAGNOSTIC", "PZEM_DIAGNOSTIC"),
        quality_flags=(
            "RAW_LOG_SOURCE_UNAVAILABLE",
            "OUTPUT_STAGE_COMPILED_OUT",
            "PZEM_MISSING_IN_FAULT_WINDOW",
            "T1_INVALID_SOFTWARE_INJECTION",
        ),
        door_event_availability="NOT_RECORDED",
        cooling_state_availability="COMPILED_OUT",
        electrical_measurement_availability="PZEM_MISSING_IN_FAULT_WINDOW",
        a_original_verdict="A_W21_02_03_SOFTWARE_VERIFIED",
        b_original_verdict="ON_DEVICE_SOFTWARE_INJECTION",
        current_verified_disposition=USE_SENSOR_DIAG,
        permitted_uses=(USE_SENSOR_DIAG,),
        refusal_reasons=(
            "EVIDENCE_CLASS_ON_DEVICE_SOFTWARE_INJECTION_NOT_PHYSICAL_RESPONSE",
            "OUTPUT_STAGE_COMPILED_OUT",
            "NO_PHYSICAL_COOLING_RESPONSE",
            "NO_INDEPENDENT_FAULT_DETECTION_ACCURACY",
            "RAW_LOG_SOURCE_UNAVAILABLE",
            "ONE_INDEPENDENT_SESSION",
        ),
        counts_as_independent_experiment=False,
        independent_session_count=1,
        shared_boot_group=str(identity.get("boot_id") or "4cf9be5f"),
        lineage_note=(
            "one boot and one raw log for two test IDs; the raw log is "
            "declared but absent from this checkout"
        ),
        metrics=metrics,
    )
    return record, manifest


def w21_observations(manifest: Mapping[str, Any], *, source_path: str) -> list[dict[str, Any]]:
    identity = manifest.get("session_identity") or {}
    diagnosis = manifest.get("diagnosis_table") or {}
    resilience = manifest.get("resilience") or {}
    a_w21_session = resilience.get("a_w21_session") or {}
    common = dict(
        record=None,
        source_id="A-W21:02_03",
        source_path=source_path,
        source_sha256=W21_MANIFEST_SHA256,
        independent_run_count=0,
        independent_session_count=1,
        evidence_class=EVIDENCE_ON_DEVICE,
    )
    rows = [
        _obs(
            quantity="recorded_frames_total",
            value=str(identity.get("total_recorded_frames", 0)),
            unit="frames",
            calculation_rule="recorded count in the pinned W21 manifest",
            frame_count=int(identity.get("total_recorded_frames", 0)),
            limitation="two test IDs share one boot and one raw log; not two sessions",
            **common,
        ),
        _obs(
            quantity="fault_window_frames",
            value=str(identity.get("fault_window_frames", 0)),
            unit="frames",
            calculation_rule="recorded fault-window count",
            frame_count=int(identity.get("fault_window_frames", 0)),
            limitation="software injection, not a physical fault",
            **common,
        ),
        _obs(
            quantity="recovery_frames",
            value=str(identity.get("recovery_frames", 0)),
            unit="frames",
            calculation_rule="recorded recovery-window count",
            frame_count=int(identity.get("recovery_frames", 0)),
            limitation="software recovery, not a physical cooling recovery",
            **common,
        ),
        _obs(
            quantity="independent_on_device_sessions",
            value=str(identity.get("independent_session_count", 1)),
            unit="sessions",
            calculation_rule="one boot and one raw log for both test IDs",
            frame_count=int(identity.get("total_recorded_frames", 0)),
            limitation="one session is not a statistical population",
            **common,
        ),
        _obs(
            quantity="test_id_count",
            value=str(len(identity.get("test_ids") or [])),
            unit="test_ids",
            calculation_rule="distinct test IDs in the combined session",
            frame_count=int(identity.get("total_recorded_frames", 0)),
            limitation="test IDs are not independent sessions",
            **common,
        ),
        _obs(
            quantity="diagnosis_record_count",
            value=str(diagnosis.get("record_count", 0)),
            unit="frames",
            calculation_rule="diagnosis table record count",
            frame_count=int(diagnosis.get("record_count", 0)),
            limitation="bounded diagnostic count; no detection accuracy",
            **common,
        ),
        _obs(
            quantity="diagnostic_accuracy",
            value=NOT_ESTIMABLE,
            unit="ratio",
            calculation_rule="no authoritative physical ground truth for accuracy",
            frame_count=NOT_APPLICABLE,
            limitation="software injection and compiled-out output stage; not a physical fault-detection accuracy",
            **common,
        ),
        _obs(
            quantity="fault_recall",
            value=NOT_ESTIMABLE,
            unit="ratio",
            calculation_rule="no independent physical fault population",
            frame_count=NOT_APPLICABLE,
            limitation="NOT_ESTIMABLE, never zero",
            **common,
        ),
        _obs(
            quantity="physical_cooling_response",
            value="NOT_ESTABLISHED",
            unit="status",
            calculation_rule="actuator output stage compiled out; TEC actuation NONE",
            frame_count=NOT_APPLICABLE,
            limitation="do not claim physical cooling resilience",
            **common,
        ),
        _obs(
            quantity="safe_local_physical_thermal_protection",
            value=str(a_w21_session.get("physical_thermal_protection", False)).lower(),
            unit="boolean",
            calculation_rule="W21 resilience session record",
            frame_count=NOT_APPLICABLE,
            limitation="software state is not physical thermal protection",
            **common,
        ),
    ]
    return rows


def build_inventory(
    *,
    a_records: Sequence[SourceRecord],
    w05_record: SourceRecord | None,
    w21_record: SourceRecord | None,
    reconciliation: Any,
    manifest: Mapping[str, Any],
    unavailable: Sequence[Mapping[str, Any]],
    source_inputs: Sequence[SourceInput],
    a_dataset_label: str,
    a_package_pins: Mapping[str, Any],
) -> dict[str, Any]:
    available = [*a_records]
    if w05_record is not None:
        available.append(w05_record)
    if w21_record is not None:
        available.append(w21_record)
    family = family_totals(
        available,
        reconciliation=reconciliation,
        manifest=manifest,
    )
    records = available
    boot_groups: dict[str, list[str]] = {}
    for record in records:
        boot_groups.setdefault(record.boot_id, []).append(record.source_id)
    relationships = [
        {
            "boot_id": boot_id,
            "source_ids": sorted(source_ids),
            "independent_sessions": 1,
            "note": (
                "multiple exported windows/segments share one boot; the boot "
                "is the independence ceiling, never the row"
            ),
        }
        for boot_id, source_ids in sorted(boot_groups.items())
        if len(source_ids) > 1
    ]
    return {
        "schema": INVENTORY_SCHEMA,
        "layer_version": LAYER_VERSION,
        "a_package_revision": reconciliation.source_revision,
        "a_package_pins": dict(a_package_pins),
        "input_allowlist": [spec.to_dict() for spec in source_inputs],
        "a_run_index_sha256": reconciliation.run_index_sha256,
        "a_manifest_sha256": reconciliation.manifest_sha256,
        "source_export_command": (
            "git archive "
            f"{reconciliation.source_revision} "
            "evidence/A/SOURCES/20261107/datasets | tar -x -C <export-dir>"
        ),
        "family_totals": family,
        "sources": [record.to_dict() for record in records],
        "source_relationships": relationships,
        "packaging_aliases": [
            {
                "alias_id": "W05A:CG-S1-H8C-600S",
                "aliases": [
                    "evidence/A/W09/exports/CG-S1-H8C-600S.json",
                    "evidence/A/W09/exports/CG-S1-H8C-600S.row-validity.csv",
                    "evidence/A/W04/tec-cooling-response-600s.csv",
                ],
                "physical_recording": "A20261107:H8-C-600s-TEC-100pct",
                "counts_as_independent": False,
                "note": (
                    "same boot 56044b74 and same 957 frames; aliases are not "
                    "additional experiments and are never counted twice"
                ),
            },
            {
                "alias_id": "PR95:SUPPLEMENT",
                "aliases": [],
                "physical_recording": "2026-11-09 passive S1 trial",
                "counts_as_independent": False,
                "classification": "UNMERGED_SUPPLEMENTARY_EVIDENCE",
                "head_revision": PR95_HEAD_REVISION,
                "trial_json_sha256": PR95_TRIAL_SHA256,
                "consumed_as_canonical": False,
                "note": (
                    "OPEN_UNMERGED; cited only, never promoted to the accepted "
                    "population"
                ),
            },
        ],
        "unavailable_sources": [
            *[dict(item) for item in unavailable],
            {
                "source_id": "A-W21:RAW_LOG",
                "source_path": "evidence/A/W21/results/ (declared)",
                "source_sha256": W21_RAW_LOG_SHA256,
                "status": USE_UNAVAILABLE,
                "reason": "DECLARED_RAW_LOG_NOT_PRESENT_IN_CHECKOUT",
            },
            {
                "source_id": "PR95:SUPPLEMENT",
                "source_path": "PR #95 (unmerged)",
                "source_sha256": PR95_TRIAL_SHA256,
                "status": "UNMERGED_SUPPLEMENTARY_EVIDENCE",
                "reason": "OPEN_UNMERGED_NOT_CONSUMED",
            },
        ],
        "source_inputs": [spec.to_dict() for spec in source_inputs],
        "not_read": [
            "ml/reports/W16 (locked-test preregistration; values never opened)",
            "ml/reports/W20 (final A/B outcome material; analysis never run)",
        ],
        "a_dataset_label": a_dataset_label,
    }


def build_observations(
    *,
    a_records: Sequence[SourceRecord],
    w05_record: SourceRecord | None,
    w21_record: SourceRecord | None,
    w21_manifest: Mapping[str, Any] | None,
    reconciliation: Any,
    manifest: Mapping[str, Any],
    timing: PlantTiming,
    a_timing_path: str,
    timing_sha256: str = A_W13_TIMING_REPORT_SHA256,
    a_dataset_label: str = "evidence/A/SOURCES/20261107/datasets",
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for record in a_records:
        observations.extend(observations_for_record(record))
    if w05_record is not None:
        observations.extend(observations_for_record(w05_record))
    if w21_record is not None and w21_manifest is not None:
        observations.extend(
            w21_observations(
                w21_manifest, source_path=w21_record.source_path
            )
        )
    available = [*a_records]
    if w05_record is not None:
        available.append(w05_record)
    if w21_record is not None:
        available.append(w21_record)
    family = family_totals(
        available,
        reconciliation=reconciliation,
        manifest=manifest,
    )
    observations.extend(
        family_observations(
            family=family,
            manifest_sha256=reconciliation.manifest_sha256,
            source_path=f"{a_dataset_label.rstrip('/')}/manifest.json",
        )
    )
    observations.extend(
        timing_observations(
            timing,
            source_path=a_timing_path,
            source_sha256=timing_sha256,
        )
    )
    observations.sort(
        key=lambda row: (
            str(row["source_id"]),
            str(row["quantity"]),
            str(row["value"]),
        )
    )
    return observations


# ---------------------------------------------------------------------------
# Markdown and CSV report rendering
# ---------------------------------------------------------------------------


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = [
        "| " + " | ".join(_md_cell(header) for header in headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(value) for value in row) + " |")
    return "\n".join(lines)


def _source_key_results(record: SourceRecord) -> str:
    metrics = record.metrics
    parts: list[str] = []
    if metrics.air is not None and metrics.air.valid_frames:
        stats = metrics.air
        parts.append(
            "chamber air mean "
            f"{fmt(stats.mean_c)} degC (min {fmt(stats.minimum_c)}, "
            f"max {fmt(stats.maximum_c)}, change {fmt(stats.change_c)})"
        )
    if metrics.t2 is not None and metrics.t2.valid_frames:
        stats = metrics.t2
        parts.append(
            f"T2 hot side mean {fmt(stats.mean_c)} degC "
            f"(max {fmt(stats.maximum_c)})"
        )
    if metrics.compact_t1_slot is not None and metrics.compact_t1_slot.valid_frames:
        parts.append(
            f"T1-slot mean {fmt(metrics.compact_t1_slot.mean_c)} degC "
            "(not a chamber-air mean)"
        )
    if metrics.door_events:
        durations = ", ".join(
            fmt(event.duration_s, 1) for event in metrics.door_events
        )
        parts.append(f"{len(metrics.door_events)} recorded door event(s); duration(s) {durations} s")
    if metrics.cooling is not None:
        cooling = metrics.cooling
        parts.append(
            "cooling phase: air change "
            f"{fmt(cooling.air_change_c)} degC, T2 change "
            f"{fmt(cooling.t2_change_c)} degC"
        )
    if record.source_family == "W21_ON_DEVICE":
        parts.append(
            f"{record.record_count} frames, one session, two test IDs; "
            "no frame-level source available for plotting"
        )
    return "; ".join(parts) if parts else "descriptive statistics only"


def _source_measurement(record: SourceRecord) -> str:
    if record.source_family == "W21_ON_DEVICE":
        return (
            "on-device software injection: 25 T1-invalid + 25 PZEM-unavailable "
            "fault frames, 50 recovery frames; output stage compiled out"
        )
    if record.metrics.compact_t1_slot is not None:
        return "compact capture: T1 slot and T2 slot only; T3/T4 absent"
    channels = "T1/T3/T4 chamber air, T2 hot side"
    if record.metrics.door_events:
        channels += ", recorded door state, operator command log"
    if record.metrics.cooling is not None:
        if record.cooling_state_availability == "RECORDED_PZEM_CURRENT_ONLY":
            channels += (
                ", requested PWM (applied duty not carried), PZEM current/"
                "power/energy"
            )
        else:
            channels += ", PWM applied/current/power/energy"
    return channels


def _source_limitations(record: SourceRecord) -> str:
    bits = [
        f"time={record.time_domain}",
        f"run_id={record.run_id_status}",
        "calibration=NOT_AVAILABLE",
    ]
    if record.quality_flags:
        bits.append("quality=" + "; ".join(record.quality_flags))
    if record.door_event_availability:
        bits.append("door=" + record.door_event_availability)
    if record.cooling_state_availability:
        bits.append("cooling=" + record.cooling_state_availability)
    return "; ".join(bits)


def _status_block(statuses: Mapping[str, Any]) -> str:
    lines = ["```text"]
    for key in (
        "EXISTING_PHYSICAL_DATA_AUDIT",
        "USABLE_PHYSICAL_DESCRIPTIVE_DATA",
        "USABLE_DOOR_DISTURBANCE_DATA",
        "USABLE_SENSOR_DIAGNOSTIC_DATA",
        "EXPLORATORY_PREDICTIVE_ASSESSMENT",
        "REAL_PREDICTIVE_BENCHMARK",
        "GATE_B_PHYSICAL_DATA",
        "PREDICTIVE_DATASET_READINESS",
        "EXISTING_DATA_REUSE",
        "DEADLINE_DEMO_PACKAGE",
        "W16_LOCKED_TEST",
        "W20_PHYSICAL_AB_ANALYSIS",
    ):
        if key in statuses:
            lines.append(f"{key}:\n{statuses[key]}")
    lines.append("```")
    return "\n".join(lines)


def render_physical_assessment(
    *,
    inventory: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    gate_b: GateBResult,
    statuses: Mapping[str, Any],
    plots: Sequence[str],
) -> bytes:
    records = [
        record
        for record in inventory["sources"]
        if record["source_family"] == "A_20261107_DATASET"
    ]
    aliases = [
        record
        for record in inventory["sources"]
        if record["source_family"] != "A_20261107_DATASET"
    ]
    family = inventory["family_totals"]
    lines: list[str] = [
        "# Existing physical data assessment — Member B",
        "",
        "> Recovery package for bounded descriptive use of the physical data "
        "already in the repository. No new measurement, no model training, "
        "no Gate B override and no physical command path.",
        "",
        _status_block(statuses),
        "",
        "## 1. Scope and method",
        "",
        "- Sources are consumed only through the explicit allowlist in "
        "`source-inventory.json`; no repository-wide glob is used.",
        "- The 18-row A package is exported read-only from the pinned main "
        f"revision `{inventory['a_package_revision']}`; its manifest and run "
        "index are SHA-256 verified before any row is read.",
        "- Temperatures use T1=CHAMBER_CENTER, T3=CHAMBER_BOTTOM and "
        "T4=CHAMBER_NEAR_DOOR for chamber air; T2=TEC_HOT_SIDE is kept "
        "separate and never enters chamber-air means or spreads.",
        "- Missing and invalid measurements stay missing; no value is replaced "
        "by zero to make a plot continuous.",
        "- Time is boot-scoped device uptime. Host receipt stamps are not "
        "physical event time and are labelled as such.",
        "",
        "### Row-quality caveat",
        "",
        "The A-normalized S1/S2 rows carry a legacy combined `quality` token "
        "(`INVALID` on every row) while A's independent `quality_report.md` "
        "reports 120/120 and 300/300 thermal OK for the S2 windows, "
        "600/600–601/601 for S1 trials 2–4, 599/600 thermal and 598/600 "
        "electrical for trial1-imported, and 0 door-unverified on the accepted "
        "S2 windows. Trial1-imported and the outside windows carry one unknown "
        "door frame. The analysis therefore uses the per-channel `*_status` "
        "fields, discloses the row token, and never zero-fills. For H8-C, the "
        "W05 source excludes 17 startup frames whose snapshot is `INVALID`; "
        "the A-normalized segment includes them, but the reported cooling "
        "phase starts after frame 226 and is unaffected. One exact duplicate "
        "row in each W07 500-permille segment is deduplicated and counted; "
        "the exported row count remains 196.",
        "",
        "## 2. Inventory summary",
        "",
        _md_table(
            (
                "source",
                "scenario",
                "boot",
                "frames",
                "A verdict",
                "B use",
                "verified disposition",
            ),
            [
                (
                    record["source_id"],
                    record["scenario"],
                    record["boot_id"],
                    record["record_count"],
                    record["A_original_verdict"],
                    ", ".join(record["permitted_uses"]),
                    record["current_verified_disposition"],
                )
                for record in records
            ],
        ),
        "",
        f"Family totals: **{family['segments']} rows/segments**, "
        f"**{family['frames_total']} frames**, "
        f"**{family['distinct_boots']} distinct boots**, "
        f"**{family['accepted_s1_windows']} accepted S1 windows**, "
        f"**{family['accepted_s2_windows']} accepted S2 windows**, "
        f"**{family['predictive_eligible_runs']} predictive-eligible runs**.",
        "",
        family["independence_statement"] + ".",
        "",
        "Packaging aliases and declared-but-unavailable sources:",
        "",
        _md_table(
            ("source", "family", "boot/session", "frames", "disposition", "note"),
            [
                (
                    record["source_id"],
                    record["source_family"],
                    record["session_id"],
                    record["record_count"],
                    record["current_verified_disposition"],
                    record["lineage_note"],
                )
                for record in aliases
            ]
            + [
                (
                    item["source_id"],
                    "UNAVAILABLE",
                    "",
                    "",
                    item["status"],
                    item["reason"],
                )
                for item in inventory.get("unavailable_sources", [])
            ],
        ),
        "",
        "## 3. Source relationships",
        "",
        _md_table(
            ("boot", "sources", "independent sessions", "note"),
            [
                (
                    item["boot_id"],
                    ", ".join(item["source_ids"]),
                    item["independent_sessions"],
                    item["note"],
                )
                for item in inventory.get("source_relationships", [])
            ],
        ),
        "",
        "The W05 export/row-validity/raw trio is the same physical recording "
        "as the A H8-C segment (boot `56044b74`, 957 frames) and is never "
        "counted twice. PR #95 remains `UNMERGED_SUPPLEMENTARY_EVIDENCE` and "
        "is cited only.",
        "",
        "## 4. Per-source rescued evidence",
        "",
        _md_table(
            (
                "source",
                "physical measurement",
                "permitted analysis",
                "key calculated result",
                "limitations",
            ),
            [
                (
                    record["source_id"],
                    _source_measurement_from_dict(record),
                    ", ".join(record["permitted_uses"]),
                    _key_results_from_dict(record),
                    _limitations_from_dict(record),
                )
                for record in records + aliases
            ],
        ),
        "",
        "## 5. Real descriptive results",
        "",
        "Every quantitative row is in `real-observation-summary.csv` with its "
        "source path, SHA-256, calculation rule, frame count, independent run "
        "count and limitation. Representative values:",
        "",
        _md_table(
            ("quantity", "value", "unit", "source", "limitation"),
            [
                (
                    row["quantity"],
                    row["value"],
                    row["unit"],
                    row["source_id"],
                    row["limitation"],
                )
                for row in observations
                if row["quantity"]
                in {
                    "chamber_air_mean_c",
                    "chamber_air_min_c",
                    "chamber_air_max_c",
                    "cooling_phase_air_change_c",
                    "cooling_phase_t2_change_c",
                    "door_event_1_during_minus_pre_c",
                    "family_distinct_boots",
                    "family_predictive_eligible_runs",
                    "EWT",
                    "AIW",
                }
            ][:36]
        ),
        "",
        "## 6. Plots",
        "",
        "All plots declare `PHYSICAL_RECORDED_DATA`, source ID, revision, "
        "source SHA-256, scenario, boot/run identity, units and the "
        "measurement/time-domain limitations. T2 is always a separate panel "
        "or series. Gaps are missing data, never zero.",
        "",
        _md_table(
            ("plot", "source identity", "declared evidence"),
            [(name, "see SVG subtitle/footer", "PHYSICAL_RECORDED_DATA") for name in plots],
        ),
        "",
        "W21 has no frame-level plot: the declared raw log is not present in "
        "this checkout. Its bounded counts are reported in the CSV instead; "
        "no time series is invented.",
        "",
        "## 7. What this supports and what it does not",
        "",
        "- Supports: S1 passive temperature description; S2 recorded door "
        "state and thermal response description; cooling-branch observations "
        "for H8-C, H8-E and two W07 500-permille trials; T1-slot/T2 continuity "
        "for the W07 compact repeats; bounded W21 diagnostic counts.",
        "- Does not support: predictive training or AP/event-recall/forecast "
        "claims; EWT/AIW; physical model performance; a critical-threshold "
        "crossing; a full-system power claim; a calibrated temperature claim.",
        "- Gate B remains the authoritative verdict: "
        f"`{gate_b.physical_status}` / `{gate_b.predictive_status}`. "
        "`EXISTING_DATA_REUSE` and `DEADLINE_DEMO_PACKAGE` are delivery "
        "statuses, not Gate B.",
        "",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _source_measurement_from_dict(record: Mapping[str, Any]) -> str:
    if record["source_family"] == "W21_ON_DEVICE":
        return (
            "on-device software injection: 100 frames, one session, two test "
            "IDs; output stage compiled out"
        )
    metrics = record.get("descriptive_metrics") or {}
    if metrics.get("compact_t1_slot"):
        return "compact capture: T1 slot and T2 slot only; T3/T4 absent"
    channels = "T1/T3/T4 chamber air, T2 hot side"
    if metrics.get("door_events"):
        channels += ", recorded door state"
    if metrics.get("cooling"):
        if record.get("cooling_state_availability") == "RECORDED_PZEM_CURRENT_ONLY":
            channels += (
                ", requested PWM (applied duty not carried), PZEM current/"
                "power/energy"
            )
        else:
            channels += ", PWM applied/current/power/energy"
    return channels


def _key_results_from_dict(record: Mapping[str, Any]) -> str:
    metrics = record.get("descriptive_metrics") or {}
    parts: list[str] = []
    air = metrics.get("air")
    if air and air.get("valid_frames"):
        parts.append(
            "chamber air mean "
            f"{fmt(air.get('mean_c'))} degC (min {fmt(air.get('minimum_c'))}, "
            f"max {fmt(air.get('maximum_c'))}, change {fmt(air.get('change_c'))})"
        )
    t2 = metrics.get("t2")
    if t2 and t2.get("valid_frames"):
        parts.append(
            f"T2 hot side mean {fmt(t2.get('mean_c'))} degC "
            f"(max {fmt(t2.get('maximum_c'))})"
        )
    compact = metrics.get("compact_t1_slot")
    if compact and compact.get("valid_frames"):
        parts.append(
            f"T1-slot mean {fmt(compact.get('mean_c'))} degC "
            "(not a chamber-air mean)"
        )
    door_events = metrics.get("door_events") or []
    if door_events:
        durations = ", ".join(fmt(item.get("duration_s"), 1) for item in door_events)
        parts.append(f"{len(door_events)} recorded door event(s); durations {durations} s")
    cooling = metrics.get("cooling")
    if cooling:
        parts.append(
            "cooling phase: air change "
            f"{fmt(cooling.get('air_change_c'))} degC, T2 change "
            f"{fmt(cooling.get('t2_change_c'))} degC"
        )
    return "; ".join(parts) if parts else "descriptive counts only"


def _limitations_from_dict(record: Mapping[str, Any]) -> str:
    bits = [
        f"time={record['time_domain']}",
        f"run_id={record['run_id_status']}",
        "calibration=NOT_AVAILABLE",
    ]
    if record.get("quality_flags"):
        bits.append("quality=" + "; ".join(record["quality_flags"]))
    if record.get("door_event_availability"):
        bits.append("door=" + record["door_event_availability"])
    if record.get("cooling_state_availability"):
        bits.append("cooling=" + record["cooling_state_availability"])
    return "; ".join(bits)


def render_predictive_review(
    *, assessment: PredictiveAssessment, gate_b: GateBResult
) -> bytes:
    question_headers = (
        "source",
        "Q1 physical",
        "Q2 mapping",
        "Q3 time",
        "Q4 event",
        "Q5 label",
        "Q6 independence",
        "Q7 causal features",
        "Q8 suitable use",
    )
    rows = []
    for source in assessment.sources:
        answers = {item["key"]: item["answer"] for item in source["questions"]}
        rows.append(
            (
                source["source_id"],
                answers.get("physically_measured", ""),
                answers.get("sensor_mapping", ""),
                answers.get("timestamps", ""),
                answers.get("disturbance", ""),
                answers.get("label", ""),
                answers.get("independence", ""),
                answers.get("causal_features", ""),
                answers.get("suitable_use", ""),
            )
        )
    lines = [
        "# Predictive eligibility review — existing physical sources",
        "",
        "> This review answers the eight admission questions for every "
        "exported source. A descriptive use and a predictive refusal are both "
        "valid outcomes; they are kept in separate columns and statuses.",
        "",
        "```text",
        f"EXPLORATORY_PREDICTIVE_ASSESSMENT = {assessment.overall}",
        f"REAL_PREDICTIVE_BENCHMARK = NOT_ESTABLISHED",
        "AP / EVENT_RECALL / FORECAST_ACCURACY = NOT_ESTIMABLE",
        f"GATE_B_PHYSICAL_DATA = {gate_b.physical_status}",
        f"PREDICTIVE_DATASET_READINESS = {gate_b.predictive_status}",
        "```",
        "",
        "## 1. Eight-question matrix",
        "",
        _md_table(question_headers, rows),
        "",
        "## 2. Why predictive metrics are not estimable",
        "",
        "- No frozen critical Tmean threshold and no representative T, so no "
        "critical-event label can be defined without inventing one.",
        "- No device wall clock, no clock synchronization evidence and no "
        "physical event UTC. Host receipt time is not event time.",
        "- The 18 rows/segments span 8 boots; repeated windows in one boot are "
        "not independent runs. There is no independent held-out source group.",
        "- The five S2 door events are real and recorded, but they all belong "
        "to one boot. A door-event exploratory model would have five events in "
        "one session and no independent test group; AP and event recall remain "
        "undefined.",
        "- S1 windows are passive baselines with no event labels.",
        "- No source is assigned `EXPLORATORY_MODEL_INPUT_CANDIDATE` or "
        "`PREDICTIVE_ADMISSION_VERIFIED`: the five S2 door events share one "
        "session, the S1 windows have no event labels, and the critical "
        "threshold is unfrozen. A descriptive demonstration is still useful, "
        "but an exploratory predictive check is not estimable.",
        "",
        "Refusal reasons (exact):",
        "",
        "```text",
        "\n".join(assessment.overall_reasons),
        "```",
        "",
        "Exploratory reasons:",
        "",
        "```text",
        "\n".join(assessment.exploratory_reasons),
        "```",
        "",
        "## 3. W15 synthetic model",
        "",
        "```text",
        f"W15_SCORING = {assessment.w15_status}",
        f"MODEL_EVIDENCE_CLASS = {EVIDENCE_SYNTHETIC}",
        "MODEL_RELEASE = NON_DEPLOYABLE_CANDIDATE",
        "MODEL_SCORE_SEMANTICS = RISK_SCORE_ONLY",
        "W15_ARTIFACT_BYTES = NOT_MODIFIED",
        "```",
        "",
        "Missing feature inputs (exact):",
        "",
        "```text",
        "\n".join(assessment.w15_missing_features),
        "```",
        "",
        "A risk score is not a calibrated probability. No W15 inference is "
        "executed because the feature input is incomplete and the model is "
        "synthetic and non-deployable. Missing real features are not forced "
        "into the model.",
        "",
        "## 4. Boundary checks",
        "",
        "- The W05 export/row-validity/raw trio is a packaging alias of the "
        "H8-C segment already in the matrix; it is not an additional "
        "predictive candidate.",
        "- W21 is `ON_DEVICE_SOFTWARE_INJECTION`, not a physical predictive "
        "candidate; its diagnostic counts are reported separately.",
        "- W16 locked-test values: **NOT_OPENED**.",
        "- W20 final physical A/B outcomes: **NOT_RUN**.",
        "- No random row-level split and no overlapping train/test source "
        "lineage is used; the predictive path is refused before a split.",
        "- No label is fabricated from an unfrozen threshold; no synthetic "
        "metric is promoted to physical evidence.",
        "",
        "## 5. Gate B is separate",
        "",
        f"The canonical Gate B verdict remains **{gate_b.physical_status}** / "
        f"**{gate_b.predictive_status}**. The descriptive recovery status "
        "does not change it.",
        "",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def render_gate_b_reassessment(
    *,
    gate_b: GateBResult,
    inventory: Mapping[str, Any],
    statuses: Mapping[str, Any],
) -> bytes:
    family = inventory["family_totals"]
    lines = [
        "# Gate B reassessment — existing physical sources",
        "",
        "> The canonical validator is W08, run unchanged. This file is a "
        "reassessment record, not a replacement validator. The delivery "
        "statuses below are not Gate B statuses.",
        "",
        "## 1. Canonical run",
        "",
        _md_table(
            ("field", "value"),
            [
                ("validator", "ml/scripts/gate-b-readiness-W08.py"),
                ("command", " ".join(gate_b.command)),
                ("source", gate_b.source_path),
                ("source SHA-256", gate_b.source_sha256),
                ("validator exit code", gate_b.validator_exit_code),
                ("W08 software verification", gate_b.software_status),
                ("GATE_B_PHYSICAL_DATA", gate_b.physical_status),
                ("PREDICTIVE_DATASET_READINESS", gate_b.predictive_status),
                ("SPLIT_STATUS", gate_b.split_status),
                ("SPLIT_FEASIBILITY", gate_b.split_feasibility),
                ("population", gate_b.population),
                ("physical reason codes", ", ".join(gate_b.physical_reasons)),
                ("predictive reason codes", ", ".join(gate_b.predictive_reasons)),
                ("split reason codes", ", ".join(gate_b.split_reasons)),
            ],
        ),
        "",
        "## 2. Old refusal versus newly available evidence",
        "",
        "The old refusal was the A ledger `INVALID` / unresolved run identity "
        "on the W05 candidate capture "
        "(`UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID`, majority of "
        "frames unusable). The newly available authoritative "
        "evidence is the merged A 20261107 package: "
        f"**{family['segments']} rows/segments**, **{family['frames_total']} "
        f"frames**, **{family['distinct_boots']} distinct boots**, "
        f"**{family['accepted_s1_windows']} A-accepted S1 windows**, "
        f"**{family['accepted_s2_windows']} A-accepted S2 windows**, with "
        "per-file SHA-256 pins verified against the manifest.",
        "",
        "Checks now satisfied:",
        "",
        "- physical measurements and per-channel statuses are present;",
        "- A accepted the S1/S2 windows as scenarios, not as independent runs;",
        "- the five S2 windows carry recorded door transitions and operator "
        "command evidence;",
        "- source bytes, manifest and run index hashes match their pins;",
        "- cooling-branch observations exist for H8-C, H8-E and W07 trials.",
        "",
        "Remaining failures (all still blocking):",
        "",
        "- no device wall clock or clock-sync evidence for physical event UTC;",
        "- no calibration identity and no certified device identity;",
        "- run IDs are `UNSET` or segment-only;",
        "- repeated windows share boots, so they are not independent runs;",
        "- the critical Tmean threshold / representative T define no label;",
        "- the current W08 intake consumes the W09 export format and does not "
        "admit the 18-row normalized package; no weaker validator was "
        "invented.",
        "",
        "## 3. Actual canonical outcome",
        "",
        "```text",
        f"GATE_B_PHYSICAL_DATA = {gate_b.physical_status}",
        f"PREDICTIVE_DATASET_READINESS = {gate_b.predictive_status}",
        f"SPLIT_FEASIBILITY = {gate_b.split_feasibility}",
        "18_ROW_PACKAGE_ADMITTED = NO",
        "W08_EVALUATED = W05_CANDIDATE_ONLY",
        "CANONICAL_VALIDATOR_INTAKE = W09_RUN_EXPORT_V2",
        "```",
        "",
        "The W08 software verification is "
        f"`{gate_b.software_status}`; a software pass does not turn the "
        "physical gate green.",
        "",
        "## 4. Delivery statuses are separate",
        "",
        "```text",
        f"EXISTING_DATA_REUSE = {statuses['EXISTING_DATA_REUSE']}",
        f"DEADLINE_DEMO_PACKAGE = {statuses['DEADLINE_DEMO_PACKAGE']}",
        "```",
        "",
        "These statuses describe the usability of the existing-data package "
        "for a bounded descriptive demonstration. They do not change Gate B, "
        "do not authorize model training and do not authorize Controller B.",
        "",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _value_for(
    observations: Sequence[Mapping[str, Any]], source_id: str, quantity: str
) -> str:
    for row in observations:
        if row["source_id"] == source_id and row["quantity"] == quantity:
            return str(row["value"])
    return NOT_ESTIMABLE


def render_presentation_vi(
    *,
    inventory: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    gate_b: GateBResult,
    statuses: Mapping[str, Any],
) -> bytes:
    family = inventory["family_totals"]
    h8c = "A20261107:H8-C-600s-TEC-100pct"
    h8e = "A20261107:H8-E-1800s-TEC-100pct"
    w07 = "A20261107:a-w07-03-trial-2-be89bf4a"
    s1 = "A20261107:trial2"
    s2 = "A20261107:W10-03-run1"
    s1_means = []
    for tag in ("trial1-imported", "trial2", "trial3", "trial4"):
        value = _value_for(
            observations, f"A20261107:{tag}", "chamber_air_mean_c"
        )
        try:
            s1_means.append(float(value))
        except ValueError:
            pass
    s1_range = (
        f"{min(s1_means):.4f}–{max(s1_means):.4f}"
        if s1_means
        else NOT_ESTIMABLE
    )
    s2_durations = []
    for tag in ("W10-02", "W10-03-run1", "W10-03-run2", "W10-03-run3", "W10-03-run4"):
        value = _value_for(
            observations, f"A20261107:{tag}", "door_event_1_duration_s"
        )
        try:
            s2_durations.append(float(value))
        except ValueError:
            pass
    s2_duration_range = (
        f"{min(s2_durations):.1f}–{max(s2_durations):.1f}"
        if s2_durations
        else NOT_ESTIMABLE
    )
    lines = [
        "# Tóm tắt trình bày — dữ liệu vật lý hiện có (Member B)",
        "",
        "> Bản tóm tắt cho buổi bảo vệ đồ án đại học. Nội dung chỉ dựa trên "
        "các nguồn đã kiểm tra SHA-256 trong gói `ml/reports/DataRecovery/`.",
        "> Không có phép đo mới, không huấn luyện mô hình mới và không thay "
        "đổi kết luận Gate B.",
        "",
        "## 1. Nhóm đã thực sự thu được gì?",
        "",
        f"- Gói A 20261107 có **{family['segments']} dòng/đoạn**, "
        f"**{family['frames_total']} khung**, trên **{family['distinct_boots']} "
        "lần khởi động (boot)** khác nhau.",
        f"- Có **{family['accepted_s1_windows']} cửa sổ S1** được A chấp nhận "
        f"(nền nhiệt thụ động) và **{family['accepted_s2_windows']} cửa sổ S2** "
        "được A chấp nhận (4 lần mở cửa + 1 cửa sổ định thời).",
        "- Có 4 đoạn làm lạnh thực: H8-C 600 s, H8-E 1800 s và hai lần chạy "
        "W07 ở 500‰.",
        "- W21 có 100 khung ghi nhận trên một phiên thiết bị, hai test ID; "
        "tầng đầu ra đã bị biên dịch loại bỏ (compiled out).",
        "",
        "Điểm quan trọng: 18 dòng/đoạn **không phải** 18 thí nghiệm độc lập. "
        "Giới hạn độc lập là số boot (8), không phải số dòng hay số cửa sổ.",
        "",
        "## 2. Những quan sát thực có thể tin cậy",
        "",
        f"- **S1 (nền thụ động):** bốn cửa sổ S1 có nhiệt độ trung bình "
        f"{s1_range} °C; ví dụ trial2 là "
        f"{_value_for(observations, s1, 'chamber_air_mean_c')} °C với thay đổi "
        f"quan sát {_value_for(observations, s1, 'chamber_air_observed_change_c')} °C "
        "trong cửa sổ khoảng 10 phút. Đây là mô tả nhiệt, không phải kết quả "
        "dự báo.",
        f"- **S2 (mở cửa):** 5 cửa sổ, mỗi cửa sổ có một lần mở cửa được ghi "
        f"nhận; thời lượng theo khung ghi nhận {s2_duration_range} s (13–14 "
        "khung; log lệnh của người vận hành ghi thời lượng dài hơn, khác biệt "
        "do cách đo và độ phân giải 1 Hz, không dùng để suy ra cơ chế). "
        "Trong cửa sổ mở "
        f"cửa, nhiệt độ buồng thay đổi rất nhỏ (ví dụ W10-03-run1: "
        f"{_value_for(observations, s2, 'door_event_1_during_minus_pre_c')} °C "
        "so với trước khi mở). Không có ngưỡng tới hạn nào bị vượt qua và "
        "không được tạo ra sự kiện tới hạn giả.",
        f"- **H8-C 600 s:** giai đoạn làm lạnh có nhiệt độ buồng thay đổi "
        f"{_value_for(observations, h8c, 'cooling_phase_air_change_c')} °C; "
        f"T2 (phía nóng TEC) thay đổi "
        f"{_value_for(observations, h8c, 'cooling_phase_t2_change_c')} °C. "
        "PZEM chỉ đo nhánh làm lạnh, không đo toàn hệ thống.",
        f"- **H8-E 1800 s:** TEC chạy 100% và T2 tăng "
        f"{_value_for(observations, h8e, 'cooling_phase_t2_change_c')} °C, "
        "nhưng nhiệt độ buồng gần như không đổi "
        f"({_value_for(observations, h8e, 'cooling_phase_air_change_c')} °C). "
        "Đây là quan sát thật; không được biến nó thành bằng chứng làm lạnh "
        "hiệu quả.",
        f"- **W07 500‰:** nhiệt độ buồng thay đổi "
        f"{_value_for(observations, w07, 'cooling_phase_air_change_c')} °C, "
        f"T2 tăng {_value_for(observations, w07, 'cooling_phase_t2_change_c')} °C "
        "trong khoảng 180 khung.",
        "",
        "Các giá trị trên đều có nguồn, quy tắc tính và giới hạn trong "
        "`real-observation-summary.csv`.",
        "",
        "## 3. Member B đã xử lý như thế nào?",
        "",
        "- Kiểm tra SHA-256 của manifest, run index, từng CSV chuẩn hóa và "
        "các nguồn W05/W21 trước khi đọc.",
        "- Tách T2 (phía nóng TEC) khỏi mọi phép tính nhiệt độ buồng.",
        "- Chỉ dùng khung có trạng thái kênh `OK`; khung thiếu/không hợp lệ "
        "được đếm và công bố, không thay bằng 0.",
        "- Thời gian chỉ là uptime trong một boot; không gọi là thời gian "
        "tuyệt đối đã đồng bộ.",
        "- Không tạo nhãn từ ngưỡng tới hạn chưa chốt; không chia train/test "
        "theo dòng; không mở W16; không chạy W20.",
        "",
        "## 4. Prototype hiện tại chứng minh được gì?",
        "",
        "- Pipeline XGBoost tổng hợp (W15) và artifact có kiểm tra hash; mô "
        "hình là **SYNTHETIC_SOFTWARE_CONTROL_ONLY**, **NON_DEPLOYABLE**, "
        "điểm số chỉ là **RISK_SCORE_ONLY**, không phải xác suất đã hiệu "
        "chuẩn.",
        "- Sinh đặc trưng nhân quả, kiểm tra rò rỉ, đánh giá theo nhóm trên "
        "dữ liệu tổng hợp; các kết quả này **không phải** kết quả vật lý.",
        "- Kiểm tra chất lượng dữ liệu, độ tươi, shadow parity offline và "
        "thống kê cặp trên fixture kiểm thử.",
        "- Chẩn đoán cảm biến/PZEM có giới hạn trong W21; không phải độ "
        "chính xác phát hiện lỗi vật lý.",
        "",
        "## 5. Những gì chưa được xác minh",
        "",
        f"- Gate B vật lý: **{gate_b.physical_status}**; bộ dữ liệu dự báo: "
        f"**{gate_b.predictive_status}**. Đây là kết quả thật của W08, không "
        "phải trạng thái của gói demo.",
        "- Chưa có EWT/AIW thực; chưa có AP, recall sự kiện hay độ chính xác "
        "dự báo vật lý.",
        "- Chưa có calibration, device identity hay đồng hồ thời gian tuyệt "
        "đối; chưa có nhãn sự kiện tới hạn được chốt.",
        "- Raw log W21 không có trong checkout; PR #95 vẫn chưa merge và "
        "không được dùng làm bằng chứng chuẩn.",
        "",
        "## 6. Câu kết luận nên dùng",
        "",
        "\"Nhóm đã thu được dữ liệu vật lý thật và xử lý được một tập mô tả "
        "có giới hạn: nền S1, 5 cửa sổ mở cửa S2, các bước làm lạnh H8-C/"
        "H8-E/W07 và chẩn đoán W21 có giới hạn. Nhóm **chưa** chứng minh được "
        "mô hình dự báo vật lý: Gate B vẫn đỏ, chưa có nhãn tới hạn và chưa "
        "có thời gian sự kiện tuyệt đối. Vì vậy báo cáo chỉ trình bày mô tả "
        "vật lý và prototype phần mềm, không tuyên bố hiệu năng dự báo.\"",
        "",
        f"Trạng thái gói demo: **{statuses['DEADLINE_DEMO_PACKAGE']}**; "
        f"tái sử dụng dữ liệu hiện có: **{statuses['EXISTING_DATA_REUSE']}**.",
        "",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


OBSERVATION_COLUMNS = (
    "quantity",
    "value",
    "unit",
    "source_id",
    "source_path",
    "source_sha256",
    "calculation_rule",
    "frame_count",
    "independent_run_count",
    "independent_session_count",
    "evidence_class",
    "limitation",
)


def render_observations_csv(observations: Sequence[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(OBSERVATION_COLUMNS),
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in observations:
        writer.writerow({key: row.get(key, "") for key in OBSERVATION_COLUMNS})
    return buffer.getvalue().encode("utf-8")


def render_inventory_json(inventory: Mapping[str, Any]) -> bytes:
    return (json.dumps(inventory, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _analysis_code_sha256(ml_root: Path) -> str:
    paths = [
        Path(__file__).resolve(),
        ml_root / "scripts" / "existing-data-recovery.py",
        ml_root / "src" / "coldguard_ml" / "horizon_engineering.py",
        ml_root / "scripts" / "gate-b-readiness-W08.py",
        ml_root / "src" / "coldguard_ml" / "data_readiness.py",
    ]
    hasher = hashlib.sha256()
    for path in sorted({path.resolve() for path in paths}, key=lambda item: item.name):
        if not path.is_file():
            continue
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


@dataclass(frozen=True)
class RecoveryPackage:
    inventory: Mapping[str, Any]
    observations: Sequence[Mapping[str, Any]]
    reports: Mapping[str, bytes]
    plots: Mapping[str, bytes]
    manifest: Mapping[str, Any]
    statuses: Mapping[str, Any]
    gate_b: GateBResult


def _plot_footer(record: SourceRecord, extra: str) -> str:
    return (
        f"{PLOT_LABEL} | source {record.source_id} | "
        f"revision {record.source_commit} | sha256 "
        f"{record.source_sha256} | scenario {record.scenario} | "
        f"boot {record.boot_id} | run {record.run_id or 'NOT_CARRIED'} | "
        f"{record.time_domain} | A={record.a_original_verdict} | "
        f"B={record.b_original_verdict} | {extra}"
    )


def _slug(source_id: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", source_id.lower()).strip("-")
    return value or "source"


def _plot_for_record(
    record: SourceRecord,
    rows: Sequence[Mapping[str, str]],
    *,
    kind: str,
    include_fn: Callable[[Mapping[str, str]], bool] | None = None,
) -> bytes:
    if kind == "air":
        panels = [plot_source_for_record(record, rows, include_fn=include_fn)]
        title = f"{PLOT_LABEL} — chamber air — {record.source_id}"
        extra = (
            "T2 hot side is excluded from chamber air; boot-relative time; "
            "gaps are missing data"
        )
    elif kind == "door":
        panels = plot_door_panels(record, rows, include_fn=include_fn)
        title = f"{PLOT_LABEL} — recorded door disturbance — {record.source_id}"
        extra = (
            "door is the recorded reported state; open duration is within-boot "
            "uptime; no absolute event time and no critical crossing"
        )
    elif kind == "cooling":
        panels = plot_cooling_panels(record, rows, include_fn=include_fn)
        title = f"{PLOT_LABEL} — recorded cooling phase — {record.source_id}"
        extra = (
            "PZEM measures the cooling branch only; applied duty and current "
            "are shown separately; no full-system power claim"
        )
    elif kind == "w05":
        panels = [
            plot_source_for_record(record, rows, include_fn=include_fn),
            plot_t2_panel(record, rows, include_fn=include_fn),
        ]
        title = f"{PLOT_LABEL} — W05 diagnostic capture — {record.source_id}"
        extra = (
            "A ledger INVALID; 940/957 frames thermally usable; door UNKNOWN; "
            "electrical status not carried in the raw capture, so no PZEM "
            "panel is drawn"
        )
    else:
        raise RecoveryError(f"unknown plot kind {kind!r}")
    return render_line_svg(
        title=title,
        subtitle=(
            f"{PLOT_LABEL} | {record.source_id} | {record.scenario} | "
            f"boot {record.boot_id} | {record.time_domain}"
        ),
        panels=panels,
        footer=_plot_footer(record, extra),
    ).encode("utf-8")


def build_plots(
    *,
    records: Sequence[SourceRecord],
    rows_by_source: Mapping[str, Sequence[Mapping[str, str]]],
) -> dict[str, bytes]:
    plots: dict[str, bytes] = {}
    by_id = {record.source_id: record for record in records}
    for source_id, kind in (
        ("A20261107:trial2", "air"),
        ("A20261107:W10-03-run1", "air"),
    ):
        record = by_id.get(source_id)
        if record is not None:
            plots[f"chamber-air-{_slug(source_id)}.svg"] = _plot_for_record(
                record, rows_by_source[source_id], kind=kind
            )
    for source_id, record in by_id.items():
        if record.scenario in {"S2_DOOR", "S2_TIMING"} and record.metrics.door_events:
            plots[f"door-{_slug(source_id)}.svg"] = _plot_for_record(
                record, rows_by_source[source_id], kind="door"
            )
    for source_id in (
        "A20261107:H8-C-600s-TEC-100pct",
        "A20261107:H8-E-1800s-TEC-100pct",
        "A20261107:a-w07-03-trial-2-be89bf4a",
    ):
        record = by_id.get(source_id)
        if record is not None and record.metrics.cooling is not None:
            plots[f"cooling-{_slug(source_id)}.svg"] = _plot_for_record(
                record, rows_by_source[source_id], kind="cooling"
            )
    w05 = by_id.get("W05A:CG-S1-H8C-600S")
    if w05 is not None and "W05A:CG-S1-H8C-600S" in rows_by_source:
        plots["w05-diagnostic.svg"] = _plot_for_record(
            w05,
            rows_by_source["W05A:CG-S1-H8C-600S"],
            kind="w05",
            include_fn=lambda row: parse_status(row.get("quality")) != "INVALID",
        )
    plots["missingness-inventory.svg"] = render_missingness_svg(
        records=records,
        title=f"{PLOT_LABEL} — source missingness inventory",
        subtitle=(
            "fraction of analyzed frames with a usable per-channel value; "
            "units: degC (temperature), A (current); T2 is hot side; "
            "missing is not zero"
        ),
        footer=(
            "source set: A20261107 manifest sha256 "
            f"{A_20261107_MANIFEST_SHA256}; W05 export sha256 "
            f"{W05_EXPORT_SHA256}; scenarios, boot/session identities and "
            "per-source hashes are declared per source in source-inventory.json "
            "and real-observation-summary.csv; W05 analyzed 940/957, with 17 "
            "snapshot-invalid frames excluded from W05 metrics and plot; W21 "
            "has no frame-level source and is not plotted"
        ),
    ).encode("utf-8")
    return dict(sorted(plots.items()))


def build_statuses(
    *,
    a_records: Sequence[SourceRecord],
    w05_record: SourceRecord | None,
    w21_record: SourceRecord | None,
    unavailable: Sequence[Mapping[str, Any]],
    gate_b: GateBResult,
    plots: Mapping[str, bytes],
) -> dict[str, Any]:
    descriptive = any(
        record.metrics.air is not None and record.metrics.air.valid_frames
        for record in [
            *a_records,
            *([w05_record] if w05_record is not None else []),
        ]
    )
    door = any(record.metrics.door_events for record in [*a_records])
    blocking_unavailable = [
        item
        for item in unavailable
        if str(item.get("source_id", "")).startswith("A20261107:")
        or str(item.get("source_id", "")).startswith("W05A:")
    ]
    audit_complete = (
        len(a_records) == 18
        and w05_record is not None
        and not blocking_unavailable
    )
    demo_ready = (
        audit_complete
        and descriptive
        and door
        and len(plots) >= 3
        and gate_b.physical_status
        and gate_b.predictive_status
    )
    return {
        "EXISTING_PHYSICAL_DATA_AUDIT": (
            STATUS_AUDIT_COMPLETE if audit_complete else STATUS_AUDIT_PARTIAL
        ),
        "USABLE_PHYSICAL_DESCRIPTIVE_DATA": "VERIFIED" if descriptive else "NOT_AVAILABLE",
        "USABLE_DOOR_DISTURBANCE_DATA": "VERIFIED" if door else "NOT_AVAILABLE",
        "USABLE_SENSOR_DIAGNOSTIC_DATA": (
            "PARTIAL"
            if w21_record is not None
            else "PARTIAL"
        ),
        "EXPLORATORY_PREDICTIVE_ASSESSMENT": "NOT_ESTIMABLE",
        "REAL_PREDICTIVE_BENCHMARK": "NOT_ESTABLISHED",
        "GATE_B_PHYSICAL_DATA": gate_b.physical_status,
        "PREDICTIVE_DATASET_READINESS": gate_b.predictive_status,
        "EXISTING_DATA_REUSE": (
            "READY_FOR_BOUNDED_ANALYSIS" if descriptive else "BLOCKED"
        ),
        "DEADLINE_DEMO_PACKAGE": (
            "READY" if demo_ready else "PARTIAL" if descriptive else "BLOCKED"
        ),
        "W16_LOCKED_TEST": "NOT_OPENED",
        "W20_PHYSICAL_AB_ANALYSIS": "NOT_RUN",
        "DELIVERY": "PENDING_PUBLICATION",
    }


def render_manifest(
    *,
    inventory_bytes: bytes,
    observations_bytes: bytes,
    reports: Mapping[str, bytes],
    plots: Mapping[str, bytes],
    inventory: Mapping[str, Any],
    statuses: Mapping[str, Any],
    gate_b: GateBResult,
    repository_revision: str,
    a_source_revision: str,
    a_manifest_sha256: str,
    a_run_index_sha256: str,
    timing_sha256: str,
    analysis_code_sha256: str,
    source_export_command: str,
    replay_command: str,
) -> bytes:
    report_hashes = {
        name: hashlib.sha256(payload).hexdigest()
        for name, payload in sorted(reports.items())
    }
    plot_hashes = {
        f"real-physical-plots/{name}": hashlib.sha256(payload).hexdigest()
        for name, payload in sorted(plots.items())
    }
    payload = {
        "schema": MANIFEST_SCHEMA,
        "package_id": "coldguard-b-existing-data-recovery",
        "package_version": "2026-11-11-W24-v1",
        "layer_version": LAYER_VERSION,
        "repository_revision": repository_revision,
        "delivery_commit": "NOT_RECORDED_AT_GENERATION",
        "a_source_revision": a_source_revision,
        "a_manifest_sha256": a_manifest_sha256,
        "a_run_index_sha256": a_run_index_sha256,
        "a_timing_report_sha256": timing_sha256,
        "w05_export_sha256": W05_EXPORT_SHA256,
        "w21_manifest_sha256": W21_MANIFEST_SHA256,
        "source_inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
        "observations_csv_sha256": hashlib.sha256(observations_bytes).hexdigest(),
        "reports": report_hashes,
        "plots": plot_hashes,
        "scientific_status": dict(statuses),
        "gate_b": gate_b.to_dict(),
        "family_totals": inventory["family_totals"],
        "source_export_command": source_export_command,
        "replay_command": replay_command,
        "analysis_code_sha256": analysis_code_sha256,
        "not_read": inventory["not_read"],
        "hash_semantics": {
            "FILE_CONTENT_SHA256": "SHA-256 over the committed file bytes",
            "SOURCE_IDENTITY": "SHA-256 pins from the A manifest/run index and committed B sources",
            "GIT_BLOB_SHA1": "not used as a source pin",
        },
        "deterministic_replay": {
            "two_independent_processes": "VERIFIED_DURING_DELIVERY_NOT_EMBEDDED",
            "no_timestamps_in_generated_artifacts": True,
        },
    }
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Package orchestration
# ---------------------------------------------------------------------------


def _spec_by_kind(specs: Sequence[SourceInput], kind: str) -> SourceInput | None:
    for spec in specs:
        if spec.kind == kind:
            return spec
    return None


def _require_spec(specs: Sequence[SourceInput], kind: str) -> SourceInput:
    spec = _spec_by_kind(specs, kind)
    if spec is None:
        raise SourcePathRefused(
            f"the explicit source inventory has no {kind} entry"
        )
    return spec


def build_package(
    *,
    repo_root: Path,
    ml_root: Path,
    a_dataset_dir: Path,
    a_dataset_label: str = "evidence/A/SOURCES/20261107/datasets",
    a_timing_path: Path,
    w05_export: Path,
    w05_row_validity: Path,
    w05_raw: Path,
    w05_run_index: Path,
    w21_manifest: Path,
    repository_revision: str,
    source_inventory: Mapping[str, Any] | None = None,
    gate_b_out: Path | None = None,
    gate_b_timeout: int = 180,
) -> RecoveryPackage:
    if source_inventory is None:
        specs = default_source_inputs(
            repo_root=repo_root,
            a_dataset_dir=a_dataset_dir,
            w05_export=w05_export,
            w05_row_validity=w05_row_validity,
            w05_raw=w05_raw,
            w05_run_index=w05_run_index,
            a_timing_report=a_timing_path,
            w21_manifest=w21_manifest,
        )
        pins: Mapping[str, Any] = {
            "source_revision": A_SOURCE_REVISION,
            "manifest_sha256": A_20261107_MANIFEST_SHA256,
            "run_index_sha256": A_20261107_RUN_INDEX_SHA256,
        }
    else:
        payload = dict(source_inventory)
        if payload.get("schema") == INVENTORY_SCHEMA:
            payload = {
                "schema": INPUT_INVENTORY_SCHEMA,
                "sources": payload.get("input_allowlist", []),
                "a_package_pins": payload.get("a_package_pins", {}),
            }
        specs = validate_source_inputs(payload)
        pins = payload.get("a_package_pins") or {}
    a_source_revision = str(pins.get("source_revision") or A_SOURCE_REVISION)
    a_manifest_sha = str(pins.get("manifest_sha256") or A_20261107_MANIFEST_SHA256)
    a_run_index_sha = str(
        pins.get("run_index_sha256") or A_20261107_RUN_INDEX_SHA256
    )
    run_index_spec = _require_spec(specs, "A_RUN_INDEX")
    manifest_spec = _require_spec(specs, "A_DATASET_MANIFEST")
    timing_spec = _require_spec(specs, "A_TIMING_REPORT")
    w05_export_spec = _require_spec(specs, "W05_EXPORT")
    w05_validity_spec = _require_spec(specs, "W05_ROW_VALIDITY")
    w05_run_index_spec = _require_spec(specs, "W05_RUN_INDEX")
    w05_raw_spec = _spec_by_kind(specs, "W05_RAW")
    w21_spec = _spec_by_kind(specs, "W21_MANIFEST")
    required_pinned_kinds = {
        "A_RUN_INDEX",
        "A_DATASET_MANIFEST",
        "A_TIMING_REPORT",
        "W05_EXPORT",
        "W05_ROW_VALIDITY",
        "W05_RUN_INDEX",
        "W21_MANIFEST",
    }
    for spec in specs:
        if spec.kind in required_pinned_kinds and not spec.expected_sha256:
            raise SourceIntegrityError(
                f"required source {spec.source_id!r} has no SHA-256 pin; "
                "an unpinned source is refused"
            )

    run_index_path = _resolve_source_path(
        run_index_spec, repo_root=repo_root, a_dataset_dir=a_dataset_dir
    )
    manifest_path = _resolve_source_path(
        manifest_spec, repo_root=repo_root, a_dataset_dir=a_dataset_dir
    )
    timing_path = _resolve_source_path(
        timing_spec, repo_root=repo_root, a_dataset_dir=a_dataset_dir
    )
    w05_export_path = _resolve_source_path(
        w05_export_spec, repo_root=repo_root, a_dataset_dir=a_dataset_dir
    )
    w05_validity_path = _resolve_source_path(
        w05_validity_spec, repo_root=repo_root, a_dataset_dir=a_dataset_dir
    )
    w05_run_index_path = _resolve_source_path(
        w05_run_index_spec, repo_root=repo_root, a_dataset_dir=a_dataset_dir
    )
    for spec, path, label in (
        (run_index_spec, run_index_path, "A run_index.csv"),
        (manifest_spec, manifest_path, "A package manifest"),
        (timing_spec, timing_path, "A timing report"),
        (w05_export_spec, w05_export_path, "W05 export"),
        (w05_validity_spec, w05_validity_path, "W05 row validity"),
        (w05_run_index_spec, w05_run_index_path, "W05 run index"),
    ):
        if not path.is_file():
            raise SourceIntegrityError(f"required {label} is absent: {path}")
        if spec.expected_sha256:
            verify_sha256(path.read_bytes(), spec.expected_sha256, label)
    w05_raw_path: Path | None = None
    if w05_raw_spec is not None:
        candidate = _resolve_source_path(
            w05_raw_spec, repo_root=repo_root, a_dataset_dir=a_dataset_dir
        )
        if candidate.is_file():
            if w05_raw_spec.expected_sha256:
                verify_sha256(
                    candidate.read_bytes(), w05_raw_spec.expected_sha256, "W05 raw"
                )
            w05_raw_path = candidate
    timing_bytes = timing_path.read_bytes()
    timing_sha256 = timing_spec.expected_sha256
    assert timing_sha256 is not None
    verify_sha256(timing_bytes, timing_sha256, "A timing report")
    timing = load_plant_timing(json.loads(timing_bytes.decode("utf-8")))
    reconciliation, manifest, a_records, unavailable = load_a_dataset(
        a_dataset_dir=a_dataset_dir,
        run_index_path=run_index_path,
        manifest_path=manifest_path,
        run_index_sha256=a_run_index_sha,
        manifest_sha256=a_manifest_sha,
        source_revision=a_source_revision,
        timing=timing,
        source_path_prefix=a_dataset_label,
    )
    w05_record: SourceRecord | None = None
    if w05_validity_path.is_file():
        w05_record = load_w05(
            export_path=w05_export_path,
            row_validity_path=w05_validity_path,
            raw_path=w05_raw_path,
            repository_revision=repository_revision,
        )
        w05_record = replace(
            w05_record,
            source_path=(
                "evidence/A/W09/exports/CG-S1-H8C-600S.row-validity.csv"
            ),
            raw_source_path=(
                "evidence/A/W04/tec-cooling-response-600s.csv"
            ),
        )
        updated_records = []
        for record in a_records:
            if (
                record.boot_id == w05_record.boot_id
                and record.metrics.cooling is not None
            ):
                record = replace(
                    record,
                    quality_flags=(
                        *record.quality_flags,
                        "W05_RAW_ELECTRICAL_STATUS_ABSENT",
                        "SAME_RECORDING_AS_W05_ALIAS",
                    ),
                    electrical_measurement_availability=(
                        "PZEM_BRANCH_A_NORMALIZED_STATUS_RAW_STATUS_ABSENT"
                    ),
                    lineage_note=(
                        record.lineage_note
                        + "; same physical recording as the W05 export/"
                        "row-validity/raw alias"
                    ),
                )
            updated_records.append(record)
        a_records = updated_records
    w21_record: SourceRecord | None = None
    w21_payload: Mapping[str, Any] | None = None
    if w21_spec is not None:
        w21_path = _resolve_source_path(
            w21_spec, repo_root=repo_root, a_dataset_dir=a_dataset_dir
        )
        if w21_path.is_file():
            if w21_spec.expected_sha256:
                verify_sha256(
                    w21_path.read_bytes(), w21_spec.expected_sha256, "W21 manifest"
                )
            w21_record, w21_payload = load_w21(
                manifest_path=w21_path,
                repository_revision=repository_revision,
            )
            w21_record = replace(
                w21_record, source_path="ml/reports/W21/w21-manifest.json"
            )
        else:
            unavailable = [
                *unavailable,
                {
                    "source_id": "A-W21:MANIFEST",
                    "source_path": "ml/reports/W21/w21-manifest.json",
                    "source_sha256": W21_MANIFEST_SHA256,
                    "status": USE_UNAVAILABLE,
                    "reason": "W21_MANIFEST_NOT_PRESENT",
                },
            ]
    rows_by_source: dict[str, Sequence[Mapping[str, str]]] = {}
    run_rows = list(
        csv.DictReader(io.StringIO(run_index_path.read_text(encoding="utf-8")))
    )
    for run_row in run_rows:
        source_id = f"A20261107:{run_row['run_tag']}"
        csv_path = a_dataset_dir / run_row["dataset_path"]
        if csv_path.is_file():
            _header, rows = _read_csv_rows(csv_path)
            rows_by_source[source_id] = rows
    if w05_record is not None:
        _header, w05_rows = _read_csv_rows(w05_validity_path)
        rows_by_source[w05_record.source_id] = w05_rows
    inventory = build_inventory(
        a_records=a_records,
        w05_record=w05_record,
        w21_record=w21_record,
        reconciliation=reconciliation,
        manifest=manifest,
        unavailable=unavailable,
        source_inputs=specs,
        a_dataset_label=a_dataset_label,
        a_package_pins=pins,
    )
    observations = build_observations(
        a_records=a_records,
        w05_record=w05_record,
        w21_record=w21_record,
        w21_manifest=w21_payload,
        reconciliation=reconciliation,
        manifest=manifest,
        timing=timing,
        a_timing_path=(
            "evidence/A/W13/plant-timing-report.json"
            if timing_spec.path is None
            else timing_spec.path
        ),
        timing_sha256=timing_sha256,
        a_dataset_label=a_dataset_label,
    )
    gate_b_dir = gate_b_out or (ml_root / ".existing-data-recovery-gate-b")
    gate_b = run_gate_b(
        repo_root=repo_root,
        ml_root=ml_root,
        w05_export=w05_export_path,
        a_run_index=w05_run_index_path,
        repository_revision=repository_revision,
        out_dir=gate_b_dir,
        timeout_s=gate_b_timeout,
    )
    plot_records = [*a_records]
    if w05_record is not None:
        plot_records.append(w05_record)
    plots = build_plots(records=plot_records, rows_by_source=rows_by_source)
    statuses = build_statuses(
        a_records=a_records,
        w05_record=w05_record,
        w21_record=w21_record,
        unavailable=unavailable,
        gate_b=gate_b,
        plots=plots,
    )
    inventory_bytes = render_inventory_json(inventory)
    observations_bytes = render_observations_csv(observations)
    reports: dict[str, bytes] = {
        "physical-data-assessment.md": render_physical_assessment(
            inventory=inventory,
            observations=observations,
            gate_b=gate_b,
            statuses=statuses,
            plots=sorted(plots),
        ),
        "predictive-eligibility-review.md": render_predictive_review(
            assessment=assess_predictive([*a_records, *([w05_record] if w05_record else [])]),
            gate_b=gate_b,
        ),
        "gate-b-reassessment.md": render_gate_b_reassessment(
            gate_b=gate_b,
            inventory=inventory,
            statuses=statuses,
        ),
        "presentation-summary-vi.md": render_presentation_vi(
            inventory=inventory,
            observations=observations,
            gate_b=gate_b,
            statuses=statuses,
        ),
    }
    manifest_bytes = render_manifest(
        inventory_bytes=inventory_bytes,
        observations_bytes=observations_bytes,
        reports=reports,
        plots=plots,
        inventory=inventory,
        statuses=statuses,
        gate_b=gate_b,
        repository_revision=repository_revision,
        a_source_revision=a_source_revision,
        a_manifest_sha256=a_manifest_sha,
        a_run_index_sha256=a_run_index_sha,
        timing_sha256=timing_sha256,
        analysis_code_sha256=_analysis_code_sha256(ml_root),
        source_export_command=str(inventory["source_export_command"]),
        replay_command=(
            "uv run --locked --python 3.12 --extra test "
            "python scripts/existing-data-recovery.py "
            "--a-dataset-dir <A_DATASET_EXPORT>/evidence/A/SOURCES/20261107/datasets "
            "--source-inventory reports/DataRecovery/source-inventory.json "
            "--out reports/DataRecovery "
            f"--repository-revision {repository_revision}"
        ),
    )
    reports = {
        **reports,
        "source-inventory.json": inventory_bytes,
        "real-observation-summary.csv": observations_bytes,
    }
    return RecoveryPackage(
        inventory=inventory,
        observations=observations,
        reports=reports,
        plots=plots,
        manifest=json.loads(manifest_bytes.decode("utf-8")),
        statuses=statuses,
        gate_b=gate_b,
    )


def write_package(package: RecoveryPackage, out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_dir = out_dir / "real-physical-plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    for stale in plot_dir.glob("*.svg"):
        stale.unlink()
    written: list[str] = []
    for name, payload in sorted(package.reports.items()):
        (out_dir / name).write_bytes(payload)
        written.append(name)
    for name, payload in sorted(package.plots.items()):
        (plot_dir / name).write_bytes(payload)
        written.append(f"real-physical-plots/{name}")
    manifest_bytes = (
        json.dumps(package.manifest, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    (out_dir / "recovery-manifest.json").write_bytes(manifest_bytes)
    written.append("recovery-manifest.json")
    return sorted(written)
