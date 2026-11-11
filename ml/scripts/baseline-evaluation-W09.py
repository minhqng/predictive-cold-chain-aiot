#!/usr/bin/env python3
"""ColdGuard W09 deterministic baseline and event-evaluation CLI.

Usage::

    python scripts/baseline-evaluation-W09.py --source PATH
        [--a-run-index PATH] [--scenario S1]
        [--a-w08-manifest reports/W08/gate-b-manifest-W08.json]
        [--parameters PATH] [--sensitivity PATH]
        [--synthetic-control] [--out reports/W09]
        [--repository-revision REV]

Exit codes:

* ``0`` — source loaded and the analysis completed. A scientific
  ``PARAMETERS_NOT_FROZEN`` or ``NOT_ESTIMABLE`` result is a successful run.
* ``1`` — invalid configuration, malformed parameters/W08 manifest or I/O.
* ``2`` — the source was refused; no artifacts are written.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

try:  # installed package
    from coldguard_ml import (
        SourceRefusal,
        analyze_capture,
        evaluate_admission,
        load_capture,
    )
    from coldguard_ml import baselines as _b
    from coldguard_ml.real_data_qa import QAConfig
    from coldguard_ml import event_evaluator as _e
    from coldguard_ml.baselines import (
        B0_THRESHOLD,
        B1_HYSTERESIS,
        B1_PERSISTENCE_CANDIDATE,
        HysteresisConfig,
        PersistenceCandidateConfig,
        RepresentativeTemperature,
        ThermalQualityPolicy,
        ThresholdConfig,
        evaluate_b0,
        evaluate_b1,
        replay_events_csv,
    )
    from coldguard_ml.event_evaluator import (
        AssociationPolicy,
        ChatterPolicy,
        EpisodePolicy,
        analyze_s1_run,
        aggregate_s1,
        aiw_boundary_status,
        build_warning_episodes,
        critical_events_from_replay,
        evaluate_events,
        event_definitions,
        warning_samples_from_replay,
    )
except ModuleNotFoundError:  # direct checkout invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml import (
        SourceRefusal,
        analyze_capture,
        evaluate_admission,
        load_capture,
    )
    from coldguard_ml import baselines as _b
    from coldguard_ml.real_data_qa import QAConfig
    from coldguard_ml import event_evaluator as _e
    from coldguard_ml.baselines import (
        B0_THRESHOLD,
        B1_HYSTERESIS,
        B1_PERSISTENCE_CANDIDATE,
        HysteresisConfig,
        PersistenceCandidateConfig,
        RepresentativeTemperature,
        ThermalQualityPolicy,
        ThresholdConfig,
        evaluate_b0,
        evaluate_b1,
        replay_events_csv,
    )
    from coldguard_ml.event_evaluator import (
        AssociationPolicy,
        ChatterPolicy,
        EpisodePolicy,
        analyze_s1_run,
        aggregate_s1,
        aiw_boundary_status,
        build_warning_episodes,
        critical_events_from_replay,
        evaluate_events,
        event_definitions,
        warning_samples_from_replay,
    )

W09_REPORT_SCHEMA = "coldguard-w09-baseline-report-v1"
W09_MANIFEST_SCHEMA = "coldguard-w09-baseline-manifest-v1"
W09_PARAMETERS_SCHEMA = "coldguard-w09-baseline-parameters-v1"

PARAMETERS_NOT_FROZEN = "PARAMETERS_NOT_FROZEN"
PARAMETERS_FROZEN = "FROZEN"
PARAMETERS_SYNTHETIC = "SYNTHETIC_ILLUSTRATIVE"
PARAMETERS_PROPOSED = "PROPOSED"

DIAGNOSTIC_REPRESENTATIVE_NAME = "DIAGNOSTIC_MEAN_T1_T3_T4"
DIAGNOSTIC_REPRESENTATIVE_SOURCE = (
    "rig role map T1=CHAMBER_CENTER, T3=CHAMBER_BOTTOM, "
    "T4=CHAMBER_NEAR_DOOR; diagnostic overlay only, not a frozen baseline "
    "representative"
)
SENSITIVITY_LABEL = "SOFTWARE_ONLY_SENSITIVITY_NOT_EVIDENTIARY"
SYNTHETIC_LABEL = "SYNTHETIC_CONTROL_ONLY"
AUTHORITATIVE_LABEL = "AUTHORITATIVE"


class CliError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedParameters:
    path: str | None
    sha256: str | None
    status: str
    parameter_source: str
    freeze_evidence: str | None
    run_id: str | None
    scenario_id: str | None
    representation: RepresentativeTemperature
    threshold: ThresholdConfig
    hysteresis: HysteresisConfig
    persistence: PersistenceCandidateConfig | None
    episode: EpisodePolicy
    association: AssociationPolicy
    chatter: ChatterPolicy
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "status": self.status,
            "parameter_source": self.parameter_source,
            "freeze_evidence": self.freeze_evidence,
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "representation": self.representation.to_dict(),
            "threshold": self.threshold.to_dict(),
            "hysteresis": self.hysteresis.to_dict(),
            "persistence_candidate": (
                None if self.persistence is None else self.persistence.to_dict()
            ),
            "episode": self.episode.to_dict(),
            "association": self.association.to_dict(),
            "chatter": self.chatter.to_dict(),
        }


@dataclass(frozen=True)
class W08Context:
    path: str | None
    sha256: str | None
    found: bool
    source_sha256_match: bool
    run_eligibility: str | None
    a_ledger_verdict: str | None
    physical_gate: str | None
    predictive_gate: str | None
    split_feasibility: str | None
    policy_statuses: tuple[dict[str, Any], ...]
    reason_codes: tuple[str, ...]
    s1_eligibility: str
    eligibility_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "found": self.found,
            "source_sha256_match": self.source_sha256_match,
            "run_eligibility": self.run_eligibility,
            "a_ledger_verdict": self.a_ledger_verdict,
            "physical_gate": self.physical_gate,
            "predictive_gate": self.predictive_gate,
            "split_feasibility": self.split_feasibility,
            "policy_statuses": [dict(item) for item in self.policy_statuses],
            "reason_codes": list(self.reason_codes),
            "s1_eligibility": self.s1_eligibility,
            "eligibility_reasons": list(self.eligibility_reasons),
        }


@dataclass(frozen=True)
class BaselineRun:
    label: str
    replay: Any
    evaluation: Any
    s1: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "replay": self.replay.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "s1": self.s1.to_dict(),
        }


def _repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return Path.cwd()


def _git_revision() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNRECORDED"
    return completed.stdout.strip() or "UNRECORDED"


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _analysis_code_sha256() -> str:
    package_dir = Path(_b.__file__).resolve().parent
    paths = {
        Path(__file__).resolve(),
        package_dir / "baselines.py",
        package_dir / "event_evaluator.py",
        package_dir / "intake.py",
        package_dir / "evaluation_contract.py",
        package_dir / "timing_alignment.py",
        package_dir / "data_readiness.py",
        package_dir / "__init__.py",
    }
    hasher = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _command_path(value: str, root: Path) -> str:
    candidate = Path(value)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return Path(os.path.relpath(candidate.resolve(), root / "ml")).as_posix()
    except ValueError:
        return candidate.name


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"INVALID CONFIGURATION: {message}", file=sys.stderr)
        raise SystemExit(1)


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        description=(
            "ColdGuard W09 deterministic threshold/hysteresis baseline and "
            "event evaluator. Read-only analysis: no hardware action, no "
            "model training, no locked-test access."
        )
    )
    parser.add_argument("--source", required=True, help="A W09 run export JSON")
    parser.add_argument("--a-run-index", help="A run-validity index JSON")
    parser.add_argument(
        "--scenario", default="S1", help="declared scenario (default: S1)"
    )
    parser.add_argument(
        "--a-w08-manifest",
        default="reports/W08/gate-b-manifest-W08.json",
        help="read-only W08 manifest with the eligibility gate",
    )
    parser.add_argument(
        "--parameters",
        help=(
            "explicit baseline parameters JSON; absent means "
            "PARAMETERS_NOT_FROZEN and no authoritative replay"
        ),
    )
    parser.add_argument(
        "--sensitivity",
        help=(
            "optional software-only sensitivity parameters JSON; results are "
            "labelled non-evidentiary"
        ),
    )
    parser.add_argument(
        "--synthetic-control",
        action="store_true",
        help="declare the parameters and input as a software positive control",
    )
    parser.add_argument(
        "--out", default="reports/W09", help="artifact output directory"
    )
    parser.add_argument(
        "--repository-revision",
        default=None,
        help="recorded repository revision (default: git HEAD)",
    )
    return parser


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CliError(f"{name} must be a JSON object")
    return value


def _require_text(mapping: dict[str, Any], name: str, label: str) -> str:
    value = mapping.get(name)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"{label} requires a non-empty {name}")
    return value


def _number(mapping: dict[str, Any], name: str, label: str) -> float:
    value = mapping.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CliError(f"{label}.{name} must be a finite number")
    if not math.isfinite(float(value)):
        raise CliError(f"{label}.{name} must be finite")
    return float(value)


def _optional_number(
    mapping: dict[str, Any], name: str, label: str
) -> float | None:
    if mapping.get(name) is None:
        return None
    return _number(mapping, name, label)


def _representation(payload: dict[str, Any]) -> RepresentativeTemperature:
    raw = _require_mapping(payload.get("representation"), "representation")
    return RepresentativeTemperature(
        name=_require_text(raw, "name", "representation"),
        mode=_require_text(raw, "mode", "representation"),
        slots=tuple(
            str(item) for item in raw.get("slots", ()) if str(item).strip()
        ),
        unit=str(raw.get("unit", "")),
        source=_require_text(raw, "source", "representation"),
        freeze_status=_require_text(raw, "freeze_status", "representation"),
    )


def _quality(payload: dict[str, Any]) -> ThermalQualityPolicy:
    raw = payload.get("quality")
    if raw is None:
        return ThermalQualityPolicy()
    raw = _require_mapping(raw, "quality")
    accepted = tuple(str(item) for item in raw.get("accepted_row_quality", ("VALID",)))
    probe_status = tuple(
        str(item) for item in raw.get("accepted_probe_status", ("OK", "NONE"))
    )
    return ThermalQualityPolicy(
        accepted_row_quality=accepted,
        accepted_probe_status=probe_status,
        max_probe_age_s=_optional_number(raw, "max_probe_age_s", "quality"),
    )


def _episode(payload: dict[str, Any]) -> EpisodePolicy:
    raw = _require_mapping(payload.get("episode"), "episode")
    return EpisodePolicy(
        policy_version=_require_text(raw, "policy_version", "episode"),
        min_persistence_s=_number(raw, "min_persistence_s", "episode"),
        bridge_gap_s=_number(raw, "bridge_gap_s", "episode"),
        bridge_unknown_gaps=bool(raw.get("bridge_unknown_gaps", False)),
        status=_require_text(raw, "status", "episode"),
        source=_require_text(raw, "source", "episode"),
    )


def _association(payload: dict[str, Any]) -> AssociationPolicy:
    raw = _require_mapping(payload.get("association"), "association")
    return AssociationPolicy(
        policy_version=_require_text(
            raw, "policy_version", "association"
        ),
        pre_window_s=_number(raw, "pre_window_s", "association"),
        post_window_s=_number(raw, "post_window_s", "association"),
        require_trusted_events=bool(raw.get("require_trusted_events", True)),
        allow_censored_events=bool(raw.get("allow_censored_events", False)),
        status=_require_text(raw, "status", "association"),
        source=_require_text(raw, "source", "association"),
    )


def _chatter(payload: dict[str, Any]) -> ChatterPolicy:
    raw = _require_mapping(payload.get("chatter"), "chatter")
    return ChatterPolicy(
        max_toggles=int(_number(raw, "max_toggles", "chatter")),
        window_s=_number(raw, "window_s", "chatter"),
        status=_require_text(raw, "status", "chatter"),
        source=_require_text(raw, "source", "chatter"),
    )


def _load_parameters(path: Path, *, synthetic_flag: bool) -> LoadedParameters:
    raw = _require_mapping(_load_json(path), "parameters")
    schema = raw.get("schema")
    if schema is not None and schema != W09_PARAMETERS_SCHEMA:
        raise CliError(f"unsupported parameters schema {schema!r}")
    status = str(raw.get("parameter_status", PARAMETERS_NOT_FROZEN))
    if status not in (
        PARAMETERS_FROZEN,
        PARAMETERS_SYNTHETIC,
        PARAMETERS_PROPOSED,
        PARAMETERS_NOT_FROZEN,
    ):
        raise CliError(f"unsupported parameter_status {status!r}")
    if status == PARAMETERS_SYNTHETIC and not synthetic_flag:
        raise CliError(
            "SYNTHETIC_ILLUSTRATIVE parameters require --synthetic-control"
        )
    if status == PARAMETERS_FROZEN:
        evidence = _require_text(raw, "freeze_evidence", "parameters")
        run_id = _require_text(raw, "run_id", "parameters")
        parameter_source = _require_text(raw, "parameter_source", "parameters")
    else:
        evidence = raw.get("freeze_evidence")
        run_id = raw.get("run_id")
        parameter_source = str(raw.get("parameter_source", "not-frozen"))
    representation = _representation(raw)
    time_domain = _require_text(raw, "time_domain", "parameters")
    max_gap = _number(raw, "max_continuity_gap_s", "parameters")
    b0 = _require_mapping(raw.get("b0"), "b0")
    b1 = _require_mapping(raw.get("b1"), "b1")
    threshold_status = _require_text(b0, "threshold_status", "b0")
    b1_status = _require_text(b1, "freeze_status", "b1")
    threshold_value = _optional_number(b0, "threshold_c", "b0")
    if status == PARAMETERS_FROZEN and (
        threshold_status != PARAMETERS_FROZEN
        or b1_status != PARAMETERS_FROZEN
    ):
        raise CliError(
            "FROZEN parameters require FROZEN b0.threshold_status and "
            "b1.freeze_status"
        )
    if status in (PARAMETERS_FROZEN, PARAMETERS_SYNTHETIC) and (
        threshold_value is None
    ):
        raise CliError(
            "a replayable parameter set requires a numeric b0.threshold_c"
        )
    threshold = ThresholdConfig(
        representation=representation,
        threshold_c=threshold_value,
        operator=_require_text(b0, "operator", "b0"),
        time_domain=time_domain,
        quality=_quality(raw),
        threshold_source=_require_text(b0, "threshold_source", "b0"),
        threshold_status=threshold_status,
        max_continuity_gap_s=max_gap,
        run_id=run_id,
        scenario_id=str(raw.get("scenario_id", "S1")),
    )
    hysteresis = HysteresisConfig(
        representation=representation,
        upper_on_c=_number(b1, "upper_on_c", "b1"),
        lower_off_c=_number(b1, "lower_off_c", "b1"),
        initial_state=_require_text(b1, "initial_state", "b1"),
        initial_state_source=_require_text(
            b1, "initial_state_source", "b1"
        ),
        time_domain=time_domain,
        quality=_quality(raw),
        upper_lower_source=_require_text(
            b1, "upper_lower_source", "b1"
        ),
        freeze_status=b1_status,
        max_continuity_gap_s=max_gap,
        run_id=run_id,
        scenario_id=str(raw.get("scenario_id", "S1")),
        policy_version=_require_text(b1, "policy_version", "b1"),
    )
    persistence = None
    if raw.get("persistence_candidate") is not None:
        candidate = _require_mapping(
            raw["persistence_candidate"], "persistence_candidate"
        )
        persistence = PersistenceCandidateConfig(
            required_s=_number(
                candidate, "required_s", "persistence_candidate"
            ),
            source=_require_text(
                candidate, "source", "persistence_candidate"
            ),
            status=str(
                candidate.get(
                    "status", _b.STATUS_EXPLORATORY
                )
            ),
        )
    return LoadedParameters(
        path=path.as_posix(),
        sha256=_sha256_file(path),
        status=status,
        parameter_source=parameter_source,
        freeze_evidence=evidence,
        run_id=run_id,
        scenario_id=str(raw.get("scenario_id", "S1")),
        representation=representation,
        threshold=threshold,
        hysteresis=hysteresis,
        persistence=persistence,
        episode=_episode(raw),
        association=_association(raw),
        chatter=_chatter(raw),
        raw=raw,
    )


def _load_w08_context(path: Path, capture: Any) -> W08Context:
    if not path.is_file():
        return W08Context(
            path=path.as_posix(),
            sha256=None,
            found=False,
            source_sha256_match=False,
            run_eligibility=None,
            a_ledger_verdict=None,
            physical_gate=None,
            predictive_gate=None,
            split_feasibility=None,
            policy_statuses=(),
            reason_codes=("W08_MANIFEST_NOT_PROVIDED",),
            s1_eligibility=_e.BLOCKED,
            eligibility_reasons=("W08_MANIFEST_NOT_PROVIDED",),
        )
    payload = _require_mapping(_load_json(path), "W08 manifest")
    runs = payload.get("runs", [])
    if not isinstance(runs, list):
        raise CliError("W08 manifest runs must be a list")
    matched = None
    for item in runs:
        if not isinstance(item, dict):
            raise CliError("W08 manifest run entries must be objects")
        if item.get("source_sha256") == capture.source.sha256:
            matched = item
            break
    source_match = matched is not None
    policy = payload.get("completeness_policy", {})
    policy_statuses = tuple(
        {
            "dimension": item.get("dimension"),
            "threshold_status": item.get("threshold_status"),
            "threshold_value": item.get("threshold_value"),
            "freeze_evidence": item.get("freeze_evidence"),
            "owner": item.get("owner"),
            "review_authority": item.get("review_authority"),
        }
        for item in policy.get("thresholds", [])
        if isinstance(item, dict)
    )
    physical = payload.get("physical_gate", {})
    predictive = payload.get("predictive_gate", {})
    split = payload.get("split_plan", {})
    run_eligibility = None if matched is None else matched.get("eligibility")
    a_ledger = None if matched is None else matched.get("a_ledger_verdict")
    reasons: set[str] = set()
    if matched is not None:
        reasons.update(str(code) for code in matched.get("reason_codes", []))
    if not source_match:
        reasons.add("W08_SOURCE_HASH_NOT_FOUND")
    if physical.get("observed_status") == "RED":
        reasons.add("W08_PHYSICAL_GATE_RED")
    if physical.get("observed_status") != "GREEN":
        reasons.add("W08_PHYSICAL_GATE_NOT_GREEN")
    if run_eligibility == "ELIGIBLE_FOR_DATASET" and (
        physical.get("observed_status") == "GREEN"
    ):
        s1_status = _e.ELIGIBLE_FOR_S1_DATASET
    elif run_eligibility is not None and run_eligibility != "BLOCKED":
        s1_status = _e.DIAGNOSTIC_ONLY
    else:
        s1_status = _e.BLOCKED
    return W08Context(
        path=path.as_posix(),
        sha256=_sha256_file(path),
        found=True,
        source_sha256_match=source_match,
        run_eligibility=run_eligibility,
        a_ledger_verdict=a_ledger,
        physical_gate=physical.get("observed_status"),
        predictive_gate=predictive.get("observed_status"),
        split_feasibility=split.get("feasibility"),
        policy_statuses=policy_statuses,
        reason_codes=tuple(sorted(reasons)),
        s1_eligibility=s1_status,
        eligibility_reasons=tuple(sorted(reasons)),
    )


def _validate_frozen_against_w08(
    parameters: LoadedParameters, context: W08Context
) -> None:
    if parameters.status != PARAMETERS_FROZEN:
        return
    if not context.found or not context.source_sha256_match:
        raise CliError(
            "FROZEN parameters require a matching W08 manifest run; threshold "
            "freeze provenance cannot be established"
        )
    if context.a_ledger_verdict != "VALID":
        raise CliError(
            "FROZEN parameters reference a run whose A ledger is not VALID; "
            "refusing to freeze a threshold from unqualified physical data"
        )
    if context.run_eligibility != "ELIGIBLE_FOR_DATASET":
        raise CliError(
            "FROZEN parameters reference a run that W08 did not mark eligible "
            "for the dataset"
        )


def _diagnostic_rows(capture: Any) -> list[dict[str, Any]]:
    """Role-qualified diagnostic overlay; never a baseline configuration."""
    rows: list[dict[str, Any]] = []
    times = [
        row.device_ms / 1000.0
        if row.device_ms is not None
        else None
        for row in capture.rows
    ]
    reference = next((value for value in times if value is not None), 0.0)
    for index, (row, time_s) in enumerate(zip(capture.rows, times)):
        quality = dict(row.quality).get("thermal", "UNKNOWN")
        value = None
        if quality == "VALID":
            try:
                from coldguard_ml.intake import chamber_air_mean

                value = chamber_air_mean(
                    capture, row, slots=("t1", "t3", "t4")
                )
            except Exception:
                value = None
        rows.append(
            {
                "index": index,
                "seq": row.seq,
                "time_s": None if time_s is None else round(time_s - reference, 9),
                "representative_c": value,
                "thermal_quality": quality,
                "applied_cooling": row.applied_cooling,
                "door_state": row.door_state,
                "source_line_index": row.source_line_index,
            }
        )
    return rows


def _build_replay(
    capture: Any,
    parameters: LoadedParameters,
    *,
    sensitivity: bool,
) -> tuple[Any, Any]:
    b0 = evaluate_b0(capture, parameters.threshold)
    b1 = evaluate_b1(
        capture,
        parameters.hysteresis,
        persistence=parameters.persistence,
    )
    return b0, b1


def _evaluate_baseline(
    replay: Any,
    parameters: LoadedParameters,
    context: W08Context,
    *,
    label: str,
    synthetic: bool,
    critical_events: Sequence[Any] | None = None,
) -> BaselineRun:
    warning_definition = (
        "B0_CRITERION_STATE_SATISFIED"
        if replay.baseline == B0_THRESHOLD
        else "B1_REACTIVE_ON_STATE"
    )
    samples, _duplicates = warning_samples_from_replay(
        replay, warning_definition=warning_definition
    )
    episodes = build_warning_episodes(
        samples,
        parameters.episode,
        run_id=replay.run_id,
        source_sha256=replay.source_sha256,
        synthetic_control=synthetic,
    )
    if critical_events is None:
        if replay.baseline == B0_THRESHOLD:
            critical_events = critical_events_from_replay(
                replay,
                definition_version=_e.EVENT_DEFINITION_VERSION,
                source="B0 declared critical criterion",
            )
        else:
            # A B1 ON transition is not a thermal crossing. The caller must
            # supply the declared B0 criterion on the same trajectory.
            critical_events = ()
    coverage_trustworthy = (
        replay.evaluability == _b.EVALUABILITY_DIAGNOSTIC
        and replay.coverage.evaluable_fraction == 1.0
        and not replay.refused_intervals
    )
    evaluation = evaluate_events(
        run_id=replay.run_id,
        source_sha256=replay.source_sha256,
        episodes=episodes.episodes,
        critical_events=critical_events,
        episode_policy=parameters.episode,
        association_policy=parameters.association,
        warning_definition=warning_definition,
        coverage_trustworthy=coverage_trustworthy,
        eligible_run_count=(
            1 if context.s1_eligibility == _e.ELIGIBLE_FOR_S1_DATASET else 0
        ),
        evaluable_duration_s=replay.coverage.evaluable_duration_s,
        untrusted_intervals=tuple(
            interval.to_dict() for interval in replay.refused_intervals
        ),
        synthetic_control=synthetic,
    )
    s1 = analyze_s1_run(
        replay,
        evaluation,
        eligibility_status=context.s1_eligibility,
        eligibility_reasons=context.eligibility_reasons,
        chatter_policy=parameters.chatter,
        coverage_trustworthy=coverage_trustworthy,
        eligible_run_count=(
            1 if context.s1_eligibility == _e.ELIGIBLE_FOR_S1_DATASET else 0
        ),
        synthetic_control=synthetic,
    )
    return BaselineRun(label=label, replay=replay, evaluation=evaluation, s1=s1)


def _manifest_baseline(run: BaselineRun) -> dict[str, Any]:
    replay = run.replay.to_dict()
    replay.pop("samples", None)
    return {
        "label": run.label,
        "replay": replay,
        "evaluation": run.evaluation.to_dict(),
        "s1": run.s1.to_dict(),
    }


def _events_csv(runs: Sequence[BaselineRun], diagnostic_rows: Sequence[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "label",
            "baseline",
            "parameter_status",
            "record_type",
            "event_type",
            "event_id",
            "run_id",
            "source_sha256",
            "start_s",
            "end_s",
            "duration_s",
            "sample_support",
            "prior_state",
            "new_state",
            "time_certainty",
            "match_status",
            "reason",
        ]
    )
    for run in runs:
        for transition in run.replay.transitions:
            writer.writerow(
                [
                    run.label,
                    run.replay.baseline,
                    run.replay.parameter_status,
                    "TRANSITION",
                    transition.event_type,
                    transition.event_id,
                    run.replay.run_id or "",
                    run.replay.source_sha256,
                    transition.crossing_interval_start_s
                    if transition.crossing_interval_start_s is not None
                    else "",
                    transition.crossing_interval_end_s,
                    "",
                    "",
                    transition.prior_state or "",
                    transition.new_state,
                    transition.time_certainty,
                    "",
                    transition.reason,
                ]
            )
        for event in run.evaluation.events:
            writer.writerow(
                [
                    run.label,
                    run.replay.baseline,
                    run.replay.parameter_status,
                    "EVENT",
                    event.get("event_type", ""),
                    event.get("event_id", ""),
                    run.replay.run_id or "",
                    run.replay.source_sha256,
                    event.get("start_s", event.get("time_s", "")),
                    event.get("end_s", ""),
                    event.get("duration_s", ""),
                    event.get("sample_count", ""),
                    "",
                    "",
                    event.get("time_certainty", ""),
                    event.get("match_status", ""),
                    event.get("reason", ""),
                ]
            )
    return buffer.getvalue()


def _false_warning_csv(
    runs: Sequence[BaselineRun],
    context: W08Context,
    diagnostic_rows: Sequence[dict[str, Any]],
) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "label",
            "baseline",
            "parameter_status",
            "eligibility_status",
            "observation_duration_s",
            "evaluable_time_s",
            "unknown_time_s",
            "diagnostic_unmatched_episodes",
            "false_warning_episode_count",
            "false_warning_episodes_per_run",
            "false_warning_episodes_per_hour",
            "state_transition_count",
            "on_off_toggles",
            "chatter_event_count",
            "outcome_status",
            "outcome_reason",
        ]
    )
    for run in runs:
        s1 = run.s1
        writer.writerow(
            [
                run.label,
                run.replay.baseline,
                run.replay.parameter_status,
                s1.eligibility_status,
                s1.observation_duration_s
                if s1.observation_duration_s is not None
                else "",
                s1.evaluable_time_s if s1.evaluable_time_s is not None else "",
                s1.unknown_time_s if s1.unknown_time_s is not None else "",
                s1.diagnostic_unmatched_episodes,
                s1.false_warning_episode_count
                if s1.false_warning_episode_count is not None
                else "",
                s1.warning_burden_per_run
                if s1.warning_burden_per_run is not None
                else "",
                s1.warning_burden_per_eligible_hour
                if s1.warning_burden_per_eligible_hour is not None
                else "",
                s1.state_transition_count,
                s1.on_off_toggles if s1.on_off_toggles is not None else "",
                s1.chatter_event_count
                if s1.chatter_event_count is not None
                else "",
                s1.outcome_status,
                s1.outcome_reason,
            ]
        )
    if not any(run.label == AUTHORITATIVE_LABEL for run in runs):
        known = [
            row["time_s"]
            for row in diagnostic_rows
            if row["time_s"] is not None
        ]
        observation = (
            round(max(known) - min(known), 9) if len(known) >= 2 else 0.0
        )
        writer.writerow(
            [
                AUTHORITATIVE_LABEL,
                "NONE",
                PARAMETERS_NOT_FROZEN,
                context.s1_eligibility,
                observation,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                _e.NOT_ESTIMABLE,
                "PARAMETERS_NOT_FROZEN: no authoritative B0/B1 replay; "
                + (
                    "the real run is not eligible for the S1 dataset"
                    if context.s1_eligibility != _e.ELIGIBLE_FOR_S1_DATASET
                    else "no frozen baseline parameters"
                ),
            ]
        )
    return buffer.getvalue()


def _svg_polyline(
    points: Sequence[tuple[float, float]],
    *,
    colour: str,
    width: float = 1.5,
    dash: str | None = None,
) -> str:
    if not points:
        return ""
    coords = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<polyline fill="none" stroke="{colour}" stroke-width="{width}"'
        f'{dash_attr} points="{coords}" />'
    )


def _render_svg(
    diagnostic_rows: Sequence[dict[str, Any]],
    runs: Sequence[BaselineRun],
    parameters: LoadedParameters | None = None,
    sensitivity: LoadedParameters | None = None,
) -> str:
    width, height = 1100, 420
    left, right, top, bottom = 70, 40, 50, 110
    plot_width = width - left - right
    plot_height = height - top - bottom
    values = [
        row["representative_c"]
        for row in diagnostic_rows
        if row["representative_c"] is not None
    ]
    times = [
        row["time_s"]
        for row in diagnostic_rows
        if row["time_s"] is not None
    ]
    if not values or not times:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}"><text x="20" y="40" font-family="monospace">'
            "W09 diagnostic overlay: no evaluable thermal trajectory</text></svg>\n"
        )
    min_t, max_t = min(times), max(times)
    min_v, max_v = min(values), max(values)
    if max_t == min_t:
        max_t = min_t + 1.0
    if max_v == min_v:
        min_v -= 0.5
        max_v += 0.5
    span_v = max_v - min_v
    min_v -= span_v * 0.1
    max_v += span_v * 0.1
    span_v = max_v - min_v

    def x_of(time_s: float) -> float:
        return left + (time_s - min_t) / (max_t - min_t) * plot_width

    def y_of(value: float) -> float:
        return top + (max_v - value) / span_v * plot_height

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{left}" y="26" font-family="monospace" font-size="15">'
        "W09 diagnostic overlay — NOT physical baseline evidence</text>",
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" '
        'fill="#fafafa" stroke="#999999"/>',
    ]
    for index in range(5):
        value = min_v + span_v * index / 4
        y = y_of(value)
        lines.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" '
            f'y2="{y:.2f}" stroke="#e5e5e5"/>'
        )
        lines.append(
            f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" '
            f'font-family="monospace" font-size="10">{value:.1f}</text>'
        )
    points = []
    for row in diagnostic_rows:
        if row["time_s"] is None or row["representative_c"] is None:
            continue
        points.append((x_of(row["time_s"]), y_of(row["representative_c"])))
    lines.append(_svg_polyline(points, colour="#1f4e79", width=1.6))
    for config, colour, label in (
        (
            parameters.threshold if parameters is not None else None,
            "#c0504d",
            "B0 threshold",
        ),
    ):
        if config is not None and config.threshold_c is not None:
            y = y_of(config.threshold_c)
            lines.append(
                f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" '
                f'y2="{y:.2f}" stroke="{colour}" stroke-dasharray="6,3"/>'
            )
            lines.append(
                f'<text x="{left + 4}" y="{y - 4:.2f}" font-family="monospace" '
                f'font-size="10" fill="{colour}">{label}</text>'
            )
    if sensitivity is not None:
        for value, colour, label in (
            (sensitivity.threshold.threshold_c, "#c0504d", "sensitivity B0"),
            (sensitivity.hysteresis.upper_on_c, "#8064a2", "sensitivity upper"),
            (sensitivity.hysteresis.lower_off_c, "#8064a2", "sensitivity lower"),
        ):
            if value is None:
                continue
            y = y_of(value)
            lines.append(
                f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" '
                f'y2="{y:.2f}" stroke="{colour}" stroke-dasharray="3,3" '
                f'opacity="0.7"/>'
            )
            lines.append(
                f'<text x="{left + plot_width - 4}" y="{y - 4:.2f}" '
                f'text-anchor="end" font-family="monospace" font-size="9" '
                f'fill="{colour}">{label}</text>'
            )
    for run in runs:
        if run.replay.parameter_status == PARAMETERS_NOT_FROZEN:
            continue
        colour = "#c0504d" if run.replay.baseline == B0_THRESHOLD else "#8064a2"
        for episode in run.evaluation.episodes:
            x1 = x_of(episode.start_s)
            x2 = x_of(episode.end_s if episode.end_s is not None else episode.start_s)
            if abs(x2 - x1) < 1.5:
                x2 = x1 + 1.5
            lines.append(
                f'<rect x="{x1:.2f}" y="{top}" width="{max(x2 - x1, 1.0):.2f}" '
                f'height="{plot_height}" fill="{colour}" opacity="0.08"/>'
            )
        for interval in run.replay.refused_intervals:
            if interval.start_s is None or interval.end_s is None:
                continue
            x1, x2 = x_of(interval.start_s), x_of(interval.end_s)
            lines.append(
                f'<rect x="{x1:.2f}" y="{top}" width="{max(x2 - x1, 1.0):.2f}" '
                f'height="{plot_height}" fill="#777777" opacity="0.15"/>'
            )
    applied_y = height - 55
    previous = None
    for row in diagnostic_rows:
        if row["time_s"] is None:
            continue
        state = row["applied_cooling"]
        colour = "#2e7d32" if state == "ON" else "#9e9e9e"
        x = x_of(row["time_s"])
        if previous is not None:
            lines.append(
                f'<rect x="{x:.2f}" y="{applied_y}" width="1.5" height="14" '
                f'fill="{colour}"/>'
            )
        previous = state
    lines.extend(
        [
            f'<text x="{left}" y="{height - 20}" font-family="monospace" '
            'font-size="11">top: role-qualified T1/T3/T4 mean (chamber air); '
            'bottom: device-reported applied state (not ACK/actuation proof); '
            'grey: refused intervals</text>',
            '</svg>',
            '',
        ]
    )
    return "\n".join(lines)


def _fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "NOT_ESTIMABLE"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _render_report(
    *,
    capture: Any,
    admission: Any,
    qa: Any,
    context: W08Context,
    authoritative_runs: Sequence[BaselineRun],
    sensitivity_runs: Sequence[BaselineRun],
    parameters: LoadedParameters | None,
    sensitivity: LoadedParameters | None,
    diagnostic_rows: Sequence[dict[str, Any]],
    provenance: dict[str, str],
    limitations: Sequence[str],
) -> str:
    lines = [
        "# ColdGuard W09 — deterministic baseline and event evaluation",
        "",
        f"Report schema: `{W09_REPORT_SCHEMA}` · layer `{_b.W09_LAYER_VERSION}`",
        "",
        "| Provenance | Value |",
        "|---|---|",
    ]
    for key, value in provenance.items():
        lines.append(f"| {key} | `{value}` |")
    lines.extend(
        [
            "",
            "## 1. Software implementation verdict",
            "",
            "```text",
            "W09 SOFTWARE: GREEN (implementation produced the declared artifacts)",
            "PHYSICAL BASELINE EVIDENCE: NOT_ESTABLISHED (no eligible S1 runs)",
            "```",
            "",
            "The software verdict is independent of the scientific verdict. The "
            "real A W09 capture is A-invalid, so no physical baseline "
            "performance is claimed.",
            "",
            "## 2. B0 threshold behavior",
            "",
        ]
    )
    if parameters is None:
        lines.extend(
            [
                "**PARAMETERS_NOT_FROZEN** — no authoritative B0 replay was "
                "executed. The diagnostic trajectory below is an overlay, not "
                "a baseline result.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"- Parameter status: `{parameters.status}`",
                f"- Source: {parameters.parameter_source}",
                f"- Representation: `{parameters.representation.name}` "
                f"({parameters.representation.mode}; slots "
                f"{', '.join(parameters.representation.slots)}; "
                f"{parameters.representation.unit})",
                f"- Threshold: {_fmt(parameters.threshold.threshold_c)} °C, "
                f"operator `{parameters.threshold.operator}`",
                f"- Threshold source: {parameters.threshold.threshold_source}",
                f"- Threshold status: `{parameters.threshold.threshold_status}`",
                f"- Time domain: `{parameters.threshold.time_domain}`",
                f"- Continuity gap bound: {parameters.threshold.max_continuity_gap_s} s",
                "",
            ]
        )
        for run in authoritative_runs:
            if run.replay.baseline == B0_THRESHOLD:
                lines.append(
                    f"- Authoritative B0: `{run.replay.evaluability}`, "
                    f"{len(run.replay.criterion_crossings())} criterion "
                    f"crossing(s), evaluable coverage "
                    f"{_fmt(run.replay.coverage.evaluable_fraction)}"
                )
        for run in sensitivity_runs:
            if run.replay.baseline == B0_THRESHOLD:
                lines.append(
                    f"- `{run.label}` B0: "
                    f"{len(run.replay.criterion_crossings())} criterion "
                    f"crossing(s), evaluable coverage "
                    f"{_fmt(run.replay.coverage.evaluable_fraction)}"
                )
        lines.append("")
    lines.extend(
        [
            "## 3. B1 hysteresis behavior",
            "",
        ]
    )
    if parameters is None:
        lines.append(
            "**PARAMETERS_NOT_FROZEN** — no authoritative B1 replay was executed."
        )
    else:
        lines.extend(
            [
                f"- Upper ON: {_fmt(parameters.hysteresis.upper_on_c)} °C; "
                f"lower OFF: {_fmt(parameters.hysteresis.lower_off_c)} °C",
                f"- Initial legal state: `{parameters.hysteresis.initial_state}` "
                f"({parameters.hysteresis.initial_state_source})",
                f"- Boundary source: {parameters.hysteresis.upper_lower_source}",
                f"- Policy version: `{parameters.hysteresis.policy_version}`",
                f"- Freeze status: `{parameters.hysteresis.freeze_status}`",
            ]
        )
        for run in list(authoritative_runs) + list(sensitivity_runs):
            if run.replay.baseline in (
                B1_HYSTERESIS,
                B1_PERSISTENCE_CANDIDATE,
            ):
                lines.append(
                    f"- `{run.label}` {run.replay.baseline}: "
                    f"{len(run.replay.on_transitions())} ON, "
                    f"{len(run.replay.off_transitions())} OFF transition(s)"
                )
    lines.extend(
        [
            "",
            "D parity is verified at the pure comparator boundary in "
            "`tests/test_baselines.py`; the full D priority/SAFE_LOCAL/fault "
            "layer is not mirrored and is not claimed.",
            "",
            "## 4. Persistence / dwell version status",
            "",
            (
                "No authoritative Controller A reactive persistence/dwell has "
                "been frozen. D's `PolicyConfig.persistence_required_s` is the "
                "predictive path and is not reused. The optional "
                "`B1_PERSISTENCE_CANDIDATE` mode is explicitly exploratory and "
                "is not Controller A."
            ),
            "",
            "## 5. Synthetic positive-control results",
            "",
            "Synthetic controls are software fixtures only. They exercise the "
            "threshold, hysteresis, episode and matching logic; they never "
            "enter a physical dataset or a scientific denominator.",
            "",
            "| Control | Expected branch | Label |",
            "|---|---|---|",
            "| stable no-event | no episode, no crossing | SYNTHETIC_CONTROL_ONLY |",
            "| oscillation around threshold | multiple episodes, chatter diagnostic | SYNTHETIC_CONTROL_ONLY |",
            "| isolated excursion | one episode | SYNTHETIC_CONTROL_ONLY |",
            "| persistent excursion | one sustained episode | SYNTHETIC_CONTROL_ONLY |",
            "| missing-data interruption | refused/unknown interval, censored match | SYNTHETIC_CONTROL_ONLY |",
            "| irregular cadence | interval certainty, no invented instant | SYNTHETIC_CONTROL_ONLY |",
            "| duplicate delivery | no extra crossing or episode | SYNTHETIC_CONTROL_ONLY |",
            "| exact boundary | documented operator outcome | SYNTHETIC_CONTROL_ONLY |",
            "",
            "The executable control suite is "
            "`tests/test_baselines.py` and `tests/test_event_evaluator.py`.",
            "",
        ]
    )
    if sensitivity_runs:
        lines.extend(
            [
                "| Sensitivity run | Baseline | Crossings / transitions | Episodes | Matched | Missed |",
                "|---|---|---|---|---|---|",
            ]
        )
        for run in sensitivity_runs:
            if run.replay.baseline == B0_THRESHOLD:
                count = len(run.replay.criterion_crossings())
                kind = "crossings"
            else:
                count = len(run.replay.on_transitions()) + len(
                    run.replay.off_transitions()
                )
                kind = "ON/OFF"
            lines.append(
                f"| `{run.label}` | {run.replay.baseline} | {count} {kind} | "
                f"{len(run.evaluation.episodes)} | "
                f"{run.evaluation.metrics.true_matched_warning_episodes} | "
                f"{run.evaluation.metrics.missed_critical_events} |"
            )
        lines.append("")
    lines.extend(
        [
            "## 6. Real physical diagnostic replay",
            "",
            f"- Source: `{capture.source.path}`",
            f"- Source SHA-256: `{capture.source.sha256}`",
            f"- Rows: {len(capture.rows)}",
            f"- Time domain: `{capture.time.domain}`; clock sync: "
            f"`{capture.time.clock_sync}`",
            f"- W05 admission status: `{admission.status.value}`; "
            f"QA execution: `{qa.statuses.qa_execution_status}`; "
            f"channel quality: `{qa.statuses.channel_quality_status}`",
            f"- Run identity: {capture.run.run_id!r}; boot: "
            f"{capture.run.boot_id!r}; device: {capture.run.device_id!r}",
            f"- Role-qualified chamber-air slots: "
            f"{', '.join(capture.chamber_air_slots) or 'none'}",
            f"- Hot-side slots excluded from chamber air: "
            f"{', '.join(capture.hot_side_slots) or 'none'}",
            f"- Diagnostic overlay representation: "
            f"`{DIAGNOSTIC_REPRESENTATIVE_NAME}` (not a frozen baseline choice)",
            "",
            "```text",
            "PARAMETERS_NOT_FROZEN: "
            f"{parameters is None or parameters.status not in (PARAMETERS_FROZEN, PARAMETERS_SYNTHETIC)}",
            f"authoritative replay executed: {bool(authoritative_runs)}",
            f"sensitivity replay executed: {bool(sensitivity_runs)}",
            "```",
            "",
            "The device-reported applied state is overlaid separately. It is "
            "not an ACK, not an electrical actuation proof and not a thermal "
            "response measurement.",
            "",
            "## 7. Scientifically eligible S1 evaluation",
            "",
            f"- W08 run eligibility: `{context.run_eligibility}`",
            f"- A ledger: `{context.a_ledger_verdict}`",
            f"- Gate B physical: `{context.physical_gate}`",
            f"- Predictive dataset: `{context.predictive_gate}`",
            f"- Split feasibility: `{context.split_feasibility}`",
            f"- S1 eligibility: `{context.s1_eligibility}`",
            f"- Reasons: {', '.join(context.reason_codes or context.eligibility_reasons) or 'none'}",
            "",
            "```text",
            "real S1 false-warning rate = NOT_ESTIMABLE",
            "real S1 stability claim = NOT_ESTABLISHED",
            "real normal-run performance = NOT_ESTIMABLE",
            "```",
            "",
            "The 957 measured rows are not 957 independent exposure units. A "
            "zero event count on an A-invalid capture is not a zero "
            "false-warning rate.",
            "",
            "## 8. Event matching and metric denominators",
            "",
            "| Label | Baseline | Eligible runs | Event denominator | Matched episodes | Unmatched episodes | Missed events | Precision | Recall |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for run in tuple(authoritative_runs) + tuple(sensitivity_runs):
        metrics = run.evaluation.metrics
        lines.append(
            f"| `{run.label}` | {run.replay.baseline} | {metrics.run_support} | "
            f"{metrics.eligible_critical_event_denominator} | "
            f"{metrics.true_matched_warning_episodes} | "
            f"{metrics.unmatched_warning_episodes} | "
            f"{metrics.missed_critical_events} | "
            f"{_fmt(metrics.event_precision)} | {_fmt(metrics.event_recall)} |"
        )
    lines.extend(
        [
            "",
            "Zero denominators stay undefined. Unmatched episodes are false "
            "warning burden only when the run is eligible and fully observed. "
            "Every evaluation also records "
            "`provenance_mismatch_event_count`/`provenance_mismatch_episode_count`; "
            "a nonzero value means foreign run/source evidence was retained but "
            "excluded, and the affected S1 outcome is undefined rather than a "
            "clean zero. "
            "Matching is a retrospective offline annotation; it is not an "
            "online causal warning stream. W09 contains no predictive action "
            "stream, so non-intervention is an explicit assumption rather "
            "than a measured closed-loop result. Sensitivity precision/recall "
            "rows are software-only demonstrations and are not scientific "
            "metrics.",
            "",
            "## 9. Frozen versus provisional parameters",
            "",
        ]
    )
    if context.policy_statuses:
        lines.append(
            "| W08 completeness dimension | Status | Value | Freeze evidence |"
        )
        lines.append("|---|---|---|---|")
        for item in context.policy_statuses:
            lines.append(
                f"| `{item['dimension']}` | {item['threshold_status']} | "
                f"{_fmt(item['threshold_value'])} | "
                f"{item['freeze_evidence'] or 'NOT_RECORDED'} |"
            )
    else:
        lines.append("W08 completeness policy statuses were not available.")
    lines.extend(
        [
            "",
            f"W09 authoritative parameters: `{parameters.status if parameters else PARAMETERS_NOT_FROZEN}`.",
            f"W09 sensitivity parameters: `{sensitivity.status if sensitivity else 'NOT_PROVIDED'}`.",
            "No W09 threshold, representative temperature, persistence/dwell or "
            "association window has been frozen for physical evidence.",
            "",
            "## 10. A / C / D owner dependencies",
            "",
            "- Member A owns physical sensor calibration, run identity, the "
            "validity ledger and measured thermal/electrical evidence.",
            "- Member C owns transport, backend timestamps and command evidence.",
            "- Member D owns the real Controller A policy, safety priority, "
            "SAFE_LOCAL and device modes. W09 only mirrors the pure hysteresis "
            "comparator for offline analysis.",
            "- The project lead and the named review authority own any threshold "
            "freeze decision.",
            "",
            "## 11. W10 / W11 / W12 handoff limitations",
            "",
            "- W09 does not build W10 features or a causal temporal pipeline.",
            "- W09 does not train or tune XGBoost or implement W11 comparisons.",
            "- W09 does not open or freeze the locked test or implement W12 "
            "conclusions.",
            "- W09 produces no real EWT because there is no predictive warning "
            "stream; EWT compatibility is tested only on synthetic controls.",
            "- W09 produces no AIW because no command/ACK/electrical/thermal "
            "latency chain was measured.",
            "",
            "## 12. Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in limitations)
    lines.append("")
    return "\n".join(lines)


def _verify_written_artifacts(output_dir: Path, manifest: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for name, digest in manifest.get("artifact_sha256", {}).items():
        path = output_dir / name
        if not path.is_file():
            problems.append(f"{name} missing")
        elif _sha256_file(path) != digest:
            problems.append(f"{name} hash mismatch")
    if manifest.get("locked_test_access") != "NONE":
        problems.append("locked_test_access must be NONE")
    if manifest.get("source_sha256") != manifest.get("source", {}).get(
        "sha256"
    ):
        problems.append("manifest source hash differs from the source record")
    for name, expected_rows in manifest.get("artifact_rows", {}).items():
        path = output_dir / name
        if not path.is_file():
            problems.append(f"{name} missing")
        elif len(path.read_text(encoding="utf-8").splitlines()) != expected_rows:
            problems.append(f"{name} row count changed after manifest write")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    try:
        parameters = (
            _load_parameters(
                Path(arguments.parameters),
                synthetic_flag=arguments.synthetic_control,
            )
            if arguments.parameters
            else None
        )
        sensitivity = (
            _load_parameters(
                Path(arguments.sensitivity), synthetic_flag=True
            )
            if arguments.sensitivity
            else None
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"INVALID CONFIGURATION: {exc}", file=sys.stderr)
        return 1
    source = Path(arguments.source)
    run_index = Path(arguments.a_run_index) if arguments.a_run_index else None
    try:
        capture = load_capture(source, a_run_index=run_index)
    except SourceRefusal as exc:
        print(f"SOURCE REFUSED: {exc.code}: {exc.detail}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"SOURCE ERROR: {exc}", file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"INVALID CONFIGURATION: {exc}", file=sys.stderr)
        return 1
    try:
        admission = evaluate_admission(capture)
        qa = analyze_capture(capture, admission=admission, config=QAConfig())
        context = _load_w08_context(
            Path(arguments.a_w08_manifest), capture
        )
        if parameters is not None:
            _validate_frozen_against_w08(parameters, context)
            if (
                parameters.run_id is not None
                and capture.run.run_id is not None
                and parameters.run_id != capture.run.run_id
            ):
                raise CliError(
                    "parameters.run_id does not match the source run identity"
                )
        if parameters is not None and parameters.threshold.time_domain != capture.time.domain:
            raise CliError(
                "parameters.time_domain does not match the capture time domain"
            )
        if sensitivity is not None and sensitivity.threshold.time_domain != capture.time.domain:
            raise CliError(
                "sensitivity.time_domain does not match the capture time domain"
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"INVALID CONFIGURATION: {exc}", file=sys.stderr)
        return 1
    diagnostic_rows = _diagnostic_rows(capture)
    authoritative_runs: list[BaselineRun] = []
    sensitivity_runs: list[BaselineRun] = []

    def build_runs(
        loaded: LoadedParameters, label: str, synthetic: bool
    ) -> list[BaselineRun]:
        if loaded.threshold.threshold_c is None:
            raise CliError(
                "a replay requires a numeric b0.threshold_c; "
                f"status {loaded.status!r} carries none"
            )
        b0, b1 = _build_replay(capture, loaded, sensitivity=synthetic)
        b0_events = critical_events_from_replay(
            b0,
            definition_version=_e.EVENT_DEFINITION_VERSION,
            source="B0 declared critical criterion",
        )
        return [
            _evaluate_baseline(
                b0,
                loaded,
                context,
                label=label,
                synthetic=synthetic,
            ),
            _evaluate_baseline(
                b1,
                loaded,
                context,
                label=label,
                synthetic=synthetic,
                critical_events=b0_events,
            ),
        ]

    try:
        if parameters is not None and parameters.status in (
            PARAMETERS_FROZEN,
            PARAMETERS_SYNTHETIC,
        ):
            authoritative_runs = build_runs(
                parameters,
                AUTHORITATIVE_LABEL,
                parameters.status == PARAMETERS_SYNTHETIC,
            )
        if sensitivity is not None:
            sensitivity_runs = build_runs(
                sensitivity, SENSITIVITY_LABEL, True
            )
    except (CliError, ValueError) as exc:
        print(f"INVALID CONFIGURATION: {exc}", file=sys.stderr)
        return 1
    output_dir = Path(arguments.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    revision = arguments.repository_revision or _git_revision()
    code_sha = _analysis_code_sha256()
    root = _repo_root()
    command_parts = [
        "python",
        "scripts/baseline-evaluation-W09.py",
        "--source",
        _command_path(arguments.source, root),
    ]
    if arguments.a_run_index:
        command_parts.extend(
            ["--a-run-index", _command_path(arguments.a_run_index, root)]
        )
    command_parts.extend(
        ["--scenario", arguments.scenario, "--out", _command_path(arguments.out, root)]
    )
    if arguments.a_w08_manifest:
        command_parts.extend(
            [
                "--a-w08-manifest",
                _command_path(arguments.a_w08_manifest, root),
            ]
        )
    if arguments.parameters:
        command_parts.extend(
            ["--parameters", _command_path(arguments.parameters, root)]
        )
    if arguments.sensitivity:
        command_parts.extend(
            ["--sensitivity", _command_path(arguments.sensitivity, root)]
        )
    if arguments.synthetic_control:
        command_parts.append("--synthetic-control")
    command_parts.extend(["--repository-revision", revision])
    generation_command = " ".join(command_parts)
    source_index_sha = (
        _sha256_file(run_index)
        if run_index is not None and run_index.is_file()
        else None
    )
    limitations = [
        "A baseline criterion detection is not an actuator command.",
        "The real A W09 capture is A-invalid; no physical baseline performance "
        "is established.",
        "The 957 rows are not independent exposure units.",
        "No real EWT is computed from a threshold baseline alone.",
        "No AIW is estimated without measured latency components.",
        "The locked test is not opened, inspected or frozen.",
    ]
    report_path = output_dir / "baseline-report.md"
    events_path = output_dir / "baseline-events-W09.csv"
    summary_path = output_dir / "false-warning-summary-W09.csv"
    svg_path = output_dir / "baseline-comparison-W09.svg"
    manifest_path = output_dir / "baseline-manifest-W09.json"
    provenance = {
        "Analysis code SHA-256": code_sha,
        "Repository revision": revision,
        "Generation command": generation_command,
        "Source": capture.source.path,
        "Source SHA-256": capture.source.sha256,
        "A run index SHA-256": source_index_sha or "NOT_PROVIDED",
        "W08 manifest SHA-256": context.sha256 or "NOT_PROVIDED",
        "W09 parameters": parameters.status if parameters else PARAMETERS_NOT_FROZEN,
        "W08 schema": "coldguard-w08-gate-b-readiness-manifest-v2",
    }
    report_path.write_text(
        _render_report(
            capture=capture,
            admission=admission,
            qa=qa,
            context=context,
            authoritative_runs=authoritative_runs,
            sensitivity_runs=sensitivity_runs,
            parameters=parameters,
            sensitivity=sensitivity,
            diagnostic_rows=diagnostic_rows,
            provenance=provenance,
            limitations=limitations,
        ),
        encoding="utf-8",
        newline="\n",
    )
    events_path.write_text(
        _events_csv(
            authoritative_runs + sensitivity_runs, diagnostic_rows
        ),
        encoding="utf-8",
        newline="\n",
    )
    summary_path.write_text(
        _false_warning_csv(
            authoritative_runs + sensitivity_runs,
            context,
            diagnostic_rows,
        ),
        encoding="utf-8",
        newline="\n",
    )
    svg_path.write_text(
        _render_svg(
            diagnostic_rows,
            authoritative_runs + sensitivity_runs,
            parameters,
            sensitivity,
        ),
        encoding="utf-8",
        newline="\n",
    )
    artifact_hashes = {
        report_path.name: _sha256_file(report_path),
        events_path.name: _sha256_file(events_path),
        summary_path.name: _sha256_file(summary_path),
        svg_path.name: _sha256_file(svg_path),
    }
    artifact_rows = {
        events_path.name: len(events_path.read_text(encoding="utf-8").splitlines()),
        summary_path.name: len(
            summary_path.read_text(encoding="utf-8").splitlines()
        ),
    }
    manifest = {
        "schema": W09_MANIFEST_SCHEMA,
        "layer_version": _b.W09_LAYER_VERSION,
        "analysis_code_sha256": code_sha,
        "repository_revision": revision,
        "generation_command": generation_command,
        "generated_at_utc": "NOT_RECORDED_BY_DESIGN",
        "source": {
            "path": capture.source.path,
            "sha256": capture.source.sha256,
            "rows": len(capture.rows),
            "time_domain": capture.time.domain,
            "chamber_air_slots": list(capture.chamber_air_slots),
            "hot_side_slots": list(capture.hot_side_slots),
        },
        "source_sha256": capture.source.sha256,
        "a_run_index_sha256": source_index_sha,
        "w05": {
            "admission_status": admission.status.value,
            "highest_stage": admission.highest_stage.value,
            "qa_execution_status": qa.statuses.qa_execution_status,
            "channel_quality_status": qa.statuses.channel_quality_status,
        },
        "w08": context.to_dict(),
        "parameters": None if parameters is None else parameters.to_dict(),
        "sensitivity": None if sensitivity is None else sensitivity.to_dict(),
        "authoritative_result": (
            PARAMETERS_NOT_FROZEN
            if parameters is None
            else parameters.status
        ),
        "baselines": [
            _manifest_baseline(run)
            for run in authoritative_runs + sensitivity_runs
        ],
        "diagnostic_overlay": {
            "representation": DIAGNOSTIC_REPRESENTATIVE_NAME,
            "source": DIAGNOSTIC_REPRESENTATIVE_SOURCE,
            "physical_authority": False,
        },
        "synthetic_controls": {
            "status": SYNTHETIC_LABEL,
            "evidence": [
                "tests/test_baselines.py",
                "tests/test_event_evaluator.py",
            ],
        },
        "event_definitions": list(event_definitions()),
        "locked_test_access": "NONE",
        "aiw": aiw_boundary_status(),
        "limitations": limitations,
        "artifact_sha256": dict(sorted(artifact_hashes.items())),
        "artifact_rows": dict(sorted(artifact_rows.items())),
    }
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    problems = _verify_written_artifacts(output_dir, manifest)
    if problems:
        print(
            "SOFTWARE VERIFICATION FAILED: " + "; ".join(problems),
            file=sys.stderr,
        )
        return 1
    print(
        "W09 BASELINE EVALUATION COMPLETE: "
        f"authoritative {manifest['authoritative_result']} · "
        f"W08 Gate B {context.physical_gate or 'UNVERIFIED'} · "
        f"S1 {context.s1_eligibility} · "
        f"artifacts {output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
