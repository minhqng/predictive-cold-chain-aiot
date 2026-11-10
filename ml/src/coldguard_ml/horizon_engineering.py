"""W13 horizon engineering (B-W13-01..04): reconciliation, candidates, study.

This layer reuses the W04 admission contract, the W10 label contract, the W11
grouped benchmark and the W11 leakage audit. It does not create a second
evaluator, a new feature registry or a physical dataset.

Scientific boundaries enforced here:

* 18 exported rows/segments are never 18 independent runs: the independence
  ceiling is the distinct ``boot_id`` count, and shared-boot windows carry
  A's independence caveat;
* A scenario acceptance (A-W09-02 / A-W10-03 PASS) is not B predictive
  eligibility: EVENT_UTC, clock sync, calibration traceability, run identity
  and a frozen critical criterion are all still required;
* candidate horizons are screened against A's measured plant timing with the
  declared proxy biases; the screening is DERIVED, never a measured verdict;
* synthetic per-horizon metrics are software controls. The highest synthetic
  AP never selects a primary horizon;
* missing timing inputs stay ``NOT_ESTIMABLE``; they are never zero;
* the locked test partition is never read, and no horizon is frozen here.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .feature_registry import FeatureRegistry
from .grouped_evaluation import MetricValue, aggregate_fold_ap
from .leakage_audit import run_leakage_audit
from .xgb_benchmark import (
    AIW_REASON_MISSING_LATENCY_CHAIN,
    EWT_REASON_NO_COMMON_TRAJECTORY,
    FIT_STATUS_REFUSED,
    OOF_DEFINED,
    BenchmarkConfig,
    BenchmarkFixture,
    build_labeled_dataset,
    run_grouped_benchmark,
)

W13_LAYER_VERSION = "coldguard-w13-horizon-engineering-v1"
W13_MANIFEST_SCHEMA = "coldguard-w13-horizon-manifest-v1"
W13_LABEL_SPEC_VERSION = "coldguard-w13-horizon-sensitivity-v1"
CANDIDATE_HORIZONS_S: tuple[float, ...] = (30.0, 60.0, 120.0, 300.0)

# Pins verified against committed bytes at reconciliation time (2026-11-10).
# The 20261107 package is merged-canonical on origin/main at A_SOURCE_REVISION
# (PR #91); it is absent from the W12 stack ancestry, so the script consumes a
# read-only `git archive` export of that exact revision, never a rebase.
A_SOURCE_REVISION = "d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85"
A_W13_TIMING_REPORT_SHA256 = (
    "2826a71026e7d4b8dc2cf3413efb5e4983785fc59ae760586569b91279fb2169"
)
A_20261107_MANIFEST_SHA256 = (
    "5273e528e6505caf55dec79a5fccbe0e6407161c1fedb864b52a7160706cc72d"
)
A_20261107_RUN_INDEX_SHA256 = (
    "53d476747c4a865ddec09492c9c49601a72ab766e9862faac0a2c9a43a22bbb4"
)
# PR #95 is OPEN and unmerged: cited, never consumed as canonical evidence.
PR95_HEAD_REVISION = "815387d19a3898e6b33ccb65758a554dd0c589e1"
PR95_TRIAL_SHA256 = (
    "f028441d10af53f43873000a6d16ab43e79a80f6defe0b974a6a5dc60c9d3b14"
)

POPULATION_SYNTHETIC = "SYNTHETIC_DEVELOPMENT"
POPULATION_REAL = "REAL_PHYSICAL"
CLAIM_SYNTHETIC = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
CLAIM_REAL_REFUSAL = "REAL_METRICS_NOT_ESTIMABLE"
NOT_ESTIMABLE = "NOT_ESTIMABLE"

DECISION_PRIMARY = "PRIMARY_CANDIDATE_SELECTED"
DECISION_PROVISIONAL = "PROVISIONAL_CANDIDATE_ONLY"
DECISION_NO_SELECTION = "NO_SELECTION_INSUFFICIENT_EVIDENCE"
DECISION_NO_SELECTION_DISPLAY = "NO_SELECTION — INSUFFICIENT EVIDENCE"

SCREEN_PROVISIONAL = "PROVISIONAL_PENDING_EVIDENCE"
SCREEN_DEPRIORITIZED = "DEPRIORITIZED_PHYSICS_PROXY"

CLASS_PHYSICAL_NOT_ELIGIBLE = "PHYSICAL_BUT_NOT_ELIGIBLE"
CLASS_DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
CLASS_NOT_VERIFIED = "NOT_VERIFIED_FOR_CANONICAL_USE"
CLASS_SPECIFIC_ANALYSIS = "ELIGIBLE_FOR_SPECIFIC_ANALYSIS"


class HorizonEngineeringError(ValueError):
    """W13 would present unsupported evidence as a scientific result."""


class EvidencePinError(HorizonEngineeringError):
    """A consumed evidence byte stream does not match its provenance pin."""


class ReconciliationError(HorizonEngineeringError):
    """The A package is internally inconsistent or carries an unknown class."""


def verify_sha256(payload: bytes, expected: str, label: str) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected:
        raise EvidencePinError(
            f"{label} sha256 {digest} does not match the provenance pin "
            f"{expected}; stale or altered evidence is refused"
        )
    return digest


# ---------------------------------------------------------------------------
# A plant timing (merged evidence/A/W13/plant-timing-report.json)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlantTiming:
    evidence_kind: str
    physical_verified: bool
    command_to_electrical_s: float
    electrical_n_measured: int
    command_to_thermal_s: float
    thermal_delta_c: float
    cooling_tau_s: float
    recovery_tau_s: float
    tau_limitation: str
    passive_drift_c: float
    passive_window_min: float
    door_to_critical_status: str
    door_to_critical_s: float | None
    gaps: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_kind": self.evidence_kind,
            "physical_verified": self.physical_verified,
            "command_to_electrical_s": self.command_to_electrical_s,
            "electrical_n_measured": self.electrical_n_measured,
            "command_to_thermal_s": self.command_to_thermal_s,
            "thermal_delta_c": self.thermal_delta_c,
            "cooling_tau_s": self.cooling_tau_s,
            "recovery_tau_s": self.recovery_tau_s,
            "tau_limitation": self.tau_limitation,
            "passive_drift_c": self.passive_drift_c,
            "passive_window_min": self.passive_window_min,
            "door_to_critical_status": self.door_to_critical_status,
            "door_to_critical_s": self.door_to_critical_s,
            "gaps": [dict(gap) for gap in self.gaps],
        }


def load_plant_timing(payload: Mapping[str, Any]) -> PlantTiming:
    try:
        electrical = payload["command_to_electrical"]
        thermal = payload["command_to_thermal"]
        cooling = payload["cooling_tau"]
        recovery = payload["recovery_tau"]
        passive = payload["passive_proxy"]
        door = payload["door_to_critical"]
    except KeyError as exc:
        raise HorizonEngineeringError(
            f"plant timing report missing required key {exc}"
        ) from exc
    if door["status"] != "NOT_COMPUTABLE" or door["value_s"] is not None:
        raise HorizonEngineeringError(
            "door->critical evidence changed since the W13 pin; a computed "
            "door->critical value requires a frozen critical definition and "
            "a re-review before W13 may consume it"
        )
    if electrical["n_measured"] < 1 or thermal["status"] != "MEASURED":
        raise HorizonEngineeringError(
            "plant timing inputs are not measured; missing timing is "
            "NOT_ESTIMABLE, never zero"
        )
    return PlantTiming(
        evidence_kind=str(payload["evidence_kind"]),
        physical_verified=bool(payload["physical_verified"]),
        command_to_electrical_s=float(electrical["per_run"][0]["delay_s"]),
        electrical_n_measured=int(electrical["n_measured"]),
        command_to_thermal_s=float(thermal["delay_s"]),
        thermal_delta_c=float(thermal["delta_c"]),
        cooling_tau_s=float(cooling["tau_s"]),
        recovery_tau_s=float(recovery["tau_s"]),
        tau_limitation=str(cooling["limitation"]),
        passive_drift_c=float(passive["passive_drift_c"]),
        passive_window_min=float(passive["passive_window_min"]),
        door_to_critical_status=str(door["status"]),
        door_to_critical_s=None,
        gaps=tuple(dict(gap) for gap in payload["data_gap_register"]),
    )


# ---------------------------------------------------------------------------
# B-W13-01 candidate screening against measured plant physics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HorizonScreening:
    horizon_s: float
    screen: str
    aiw_upper_bound_s: float
    cooling_tau_ratio: float
    status: str
    rationale: str
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_s": self.horizon_s,
            "screen": self.screen,
            "aiw_upper_bound_s": self.aiw_upper_bound_s,
            "cooling_tau_ratio": self.cooling_tau_ratio,
            "status": self.status,
            "rationale": self.rationale,
            "caveats": list(self.caveats),
        }


def screen_horizon_candidates(
    timing: PlantTiming,
    horizons: Sequence[float] = CANDIDATE_HORIZONS_S,
) -> tuple[HorizonScreening, ...]:
    """DERIVED proxy screening, not a measured actionability verdict.

    AIW = t_critical - t_warning - T_system - T_physical. With the warning
    exactly H before critical and T_system unknown but >= 0, the most
    favorable AIW is H - T_physical. A's applied-on->1 degC delay is the only
    measured intervention->thermal proxy, so H <= that delay cannot be
    actionable even with zero system latency. The proxy is biased and its
    anchor differs from a warning anchor; the screen only deprioritizes,
    it never freezes or eliminates a sensitivity candidate.
    """
    if not horizons or any(h <= 0 for h in horizons):
        raise HorizonEngineeringError("candidate horizons must be positive")
    if timing.cooling_tau_s <= 0:
        raise HorizonEngineeringError("cooling tau proxy must be positive")
    screenings: list[HorizonScreening] = []
    for horizon in horizons:
        bound = float(horizon) - timing.command_to_thermal_s
        if bound <= 0:
            screen = SCREEN_DEPRIORITIZED
            rationale = (
                f"H={horizon:g}s does not exceed the measured applied-on->"
                f"{timing.thermal_delta_c:g} degC thermal response proxy "
                f"({timing.command_to_thermal_s:g}s); AIW <= {bound:g}s even "
                "with zero system latency, so this horizon is deprioritized "
                "as a primary candidate and retained for sensitivity only"
            )
        else:
            screen = SCREEN_PROVISIONAL
            rationale = (
                f"H={horizon:g}s leaves at most {bound:g}s of AIW headroom "
                "before the unknown system latency; actionability is not "
                "established and the horizon stays provisional"
            )
        screenings.append(
            HorizonScreening(
                horizon_s=float(horizon),
                screen=screen,
                aiw_upper_bound_s=bound,
                cooling_tau_ratio=float(horizon) / timing.cooling_tau_s,
                status="DERIVED_PROXY_SCREENING_NOT_A_MEASURED_VERDICT",
                rationale=rationale,
                caveats=(
                    "thermal proxy is a raw first-crossing on one boot, "
                    "anchored on the applied-on frame, not on a warning",
                    "tau proxies under-estimate tau by window truncation",
                    "command->electrical is n=1 on a console path, not a "
                    "backend-command distribution",
                    "T_system is unmeasured (network command path absent); "
                    "the bound assumes only T_system >= 0",
                ),
            )
        )
    return tuple(screenings)


# ---------------------------------------------------------------------------
# Phase A: reconcile the merged 18-row package against B admission rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconciledSource:
    run_tag: str
    scenario: str
    a_classification: str
    boot_id: str
    device_run_id: str
    timebase: str
    device_timestamp_utc_source: str
    frames: int
    dataset_path: str
    dataset_sha256: str
    b_classification: str
    permitted_use: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_tag": self.run_tag,
            "scenario": self.scenario,
            "a_classification": self.a_classification,
            "boot_id": self.boot_id,
            "device_run_id": self.device_run_id,
            "timebase": self.timebase,
            "device_timestamp_utc_source": self.device_timestamp_utc_source,
            "frames": self.frames,
            "dataset_path": self.dataset_path,
            "dataset_sha256": self.dataset_sha256,
            "b_classification": self.b_classification,
            "permitted_use": self.permitted_use,
        }


@dataclass(frozen=True)
class DatasetReconciliation:
    source_revision: str
    run_index_sha256: str
    manifest_sha256: str
    sources: tuple[ReconciledSource, ...]
    row_count: int
    distinct_boots: int
    frames_total: int
    accepted_s1_windows: int
    accepted_s2_windows: int
    s2_door_scenario_rows: int
    predictive_eligible_runs: int
    refusal_reasons: tuple[str, ...]
    superseded_evidence_notes: tuple[str, ...]
    pr95_supplement: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_revision": self.source_revision,
            "run_index_sha256": self.run_index_sha256,
            "manifest_sha256": self.manifest_sha256,
            "sources": [source.to_dict() for source in self.sources],
            "row_count": self.row_count,
            "distinct_boots": self.distinct_boots,
            "frames_total": self.frames_total,
            "accepted_s1_windows": self.accepted_s1_windows,
            "accepted_s2_windows": self.accepted_s2_windows,
            "s2_door_scenario_rows": self.s2_door_scenario_rows,
            "predictive_eligible_runs": self.predictive_eligible_runs,
            "refusal_reasons": list(self.refusal_reasons),
            "superseded_evidence_notes": list(self.superseded_evidence_notes),
            "pr95_supplement": dict(self.pr95_supplement),
            "verdict": "NO_RUN_ELIGIBLE_FOR_PREDICTIVE_DATASET",
            "independence_statement": (
                f"{self.row_count} exported rows/segments span "
                f"{self.distinct_boots} distinct boots; rows are never "
                "counted as independent runs"
            ),
        }


_A_CLASS_MAP: Mapping[str, tuple[str, str]] = {
    "DATASET_ACCEPTED_S1": (
        CLASS_PHYSICAL_NOT_ELIGIBLE,
        "SCENARIO_QA_AND_BASELINE_CHARACTERIZATION",
    ),
    "DATASET_ACCEPTED_S2": (
        CLASS_PHYSICAL_NOT_ELIGIBLE,
        "SCENARIO_QA_AND_DOOR_DISTURBANCE_CHARACTERIZATION",
    ),
    "REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED": (
        CLASS_PHYSICAL_NOT_ELIGIBLE,
        "PLANT_TIMING_ANALYSIS_ONLY",
    ),
    "REAL_FRAMES_OUTSIDE_TIMED_WINDOWS": (
        CLASS_DIAGNOSTIC_ONLY,
        "NEVER_COUNTED_AS_AN_INDEPENDENT_RUN",
    ),
    "REAL_PHYSICAL_REPEATS / INDEPENDENCE_CAVEAT": (
        CLASS_PHYSICAL_NOT_ELIGIBLE,
        "DIAGNOSTIC_CONTINUITY_ONLY_NO_FULL_PROBE_ROWS",
    ),
}


_CG_RUN_PATTERN = re.compile(r"^CG-S\d+-[A-Za-z0-9]+-[A-Za-z0-9]+$")


def _row_predictive_eligible(
    source: ReconciledSource,
    normalized_header: Sequence[str],
    *,
    critical_criterion_frozen: bool,
) -> bool:
    """W04 ladder test for one exported row (EVENT_UTC, clock, identity)."""
    return (
        source.device_timestamp_utc_source != "DEVICE_HAS_NO_WALL_CLOCK"
        and source.timebase != "HOST_STAMP"
        and bool(_CG_RUN_PATTERN.match(source.device_run_id))
        and "clock_sync" in normalized_header
        and "calibration_id" in normalized_header
        and critical_criterion_frozen
    )


def reconcile_a_dataset(
    run_index_bytes: bytes,
    manifest_bytes: bytes,
    *,
    normalized_header: Sequence[str],
    timing: PlantTiming,
    critical_criterion_frozen: bool = False,
    run_index_sha256: str = A_20261107_RUN_INDEX_SHA256,
    manifest_sha256: str = A_20261107_MANIFEST_SHA256,
    source_revision: str = A_SOURCE_REVISION,
) -> DatasetReconciliation:
    verify_sha256(run_index_bytes, run_index_sha256, "A run_index.csv")
    verify_sha256(manifest_bytes, manifest_sha256, "A 20261107 manifest.json")
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    reader = csv.DictReader(io.StringIO(run_index_bytes.decode("utf-8")))
    rows = list(reader)
    if not rows:
        raise ReconciliationError("A run_index.csv carries no rows")
    totals = manifest.get("totals", {})
    if totals.get("runs_and_segments") != len(rows):
        raise ReconciliationError(
            "manifest totals.runs_and_segments disagrees with run_index rows"
        )
    frames_total = sum(int(row["frames"]) for row in rows)
    if totals.get("frames_total") != frames_total:
        raise ReconciliationError(
            "manifest totals.frames_total disagrees with the run_index sum"
        )
    output_pins = {
        entry["package_path"]: entry["sha256"]
        for entry in manifest.get("outputs", [])
    }
    sources: list[ReconciledSource] = []
    boots: set[str] = set()
    for row in rows:
        a_class = row["classification"]
        if a_class not in _A_CLASS_MAP:
            raise ReconciliationError(
                f"unknown A classification {a_class!r}; W13 refuses to "
                "invent an admissibility bucket"
            )
        b_class, permitted = _A_CLASS_MAP[a_class]
        dataset_path = row["dataset_path"]
        if output_pins.get(dataset_path) != row["dataset_sha256"]:
            raise ReconciliationError(
                f"run {row['run_tag']!r} dataset pin disagrees with the "
                "manifest output pin"
            )
        boots.add(row["boot_id"])
        sources.append(
            ReconciledSource(
                run_tag=row["run_tag"],
                scenario=row["scenario"],
                a_classification=a_class,
                boot_id=row["boot_id"],
                device_run_id=row["device_run_id"],
                timebase=row["timebase"],
                device_timestamp_utc_source=row["device_timestamp_utc_source"],
                frames=int(row["frames"]),
                dataset_path=dataset_path,
                dataset_sha256=row["dataset_sha256"],
                b_classification=b_class,
                permitted_use=permitted,
            )
        )
    refusal: list[str] = []
    if all(
        source.device_timestamp_utc_source == "DEVICE_HAS_NO_WALL_CLOCK"
        for source in sources
    ):
        refusal.append("EVENT_UTC_UNAVAILABLE_DEVICE_HAS_NO_WALL_CLOCK")
    if any(source.timebase == "HOST_STAMP" for source in sources):
        refusal.append("HOST_RECEIPT_TIME_IS_NOT_PHYSICAL_EVENT_TIME")
    if "clock_sync" not in normalized_header:
        refusal.append("CLOCK_SYNC_NOT_EVIDENCED_IN_PACKAGE")
    if all(
        source.device_run_id in ("", "UNSET", "run-00000000")
        for source in sources
    ):
        refusal.append("RUN_IDENTITY_UNRESOLVED_FOR_CG_RUN_PATTERN")
    if "calibration_id" not in normalized_header:
        refusal.append("CALIBRATION_TRACEABILITY_ABSENT_FROM_PACKAGE_SCHEMA")
    if len(boots) < len(rows):
        refusal.append("SEGMENTS_SHARE_BOOTS_ROWS_ARE_NOT_INDEPENDENT_RUNS")
    refusal.append("CRITICAL_CRITERION_AND_REPRESENTATIVE_T_NOT_FROZEN")
    superseded = [
        "evidence/A/W09/run-registry.json and "
        "evidence/A/W11/additional-valid-run-list.json record zero valid "
        "S1/S2 runs; those historical verdicts predate the merged 20261107 "
        "package and are superseded for scenario validity by A-W09-02 / "
        "A-W10-03 PASS (4 S1 windows, 4 S2 door runs). They are not "
        "rewritten, and scenario acceptance still does not grant B "
        "predictive eligibility.",
    ]
    if timing.door_to_critical_status == "NOT_COMPUTABLE":
        s2_rows = sum(
            1 for source in sources if source.scenario in ("S2_DOOR", "S2_TIMING")
        )
        if s2_rows:
            superseded.append(
                "evidence/A/W13/plant-timing-report.json refuses "
                "door->critical with the reason 'no door-open event exists "
                "in any committed capture'; that reason is stale because "
                f"the merged package carries {s2_rows} S2 door/timing "
                "windows. The NOT_COMPUTABLE value itself stands: the "
                "critical definition is unfrozen (D threshold pending; "
                "A-W10-05 / A-W13-03 INCOMPLETE, offline rerun once frozen)."
            )
    return DatasetReconciliation(
        source_revision=source_revision,
        run_index_sha256=run_index_sha256,
        manifest_sha256=manifest_sha256,
        sources=tuple(sources),
        row_count=len(rows),
        distinct_boots=len(boots),
        frames_total=frames_total,
        accepted_s1_windows=sum(
            1 for source in sources if source.a_classification == "DATASET_ACCEPTED_S1"
        ),
        accepted_s2_windows=sum(
            1 for source in sources if source.a_classification == "DATASET_ACCEPTED_S2"
        ),
        s2_door_scenario_rows=sum(
            1 for source in sources if source.scenario in ("S2_DOOR", "S2_TIMING")
        ),
        predictive_eligible_runs=sum(
            1
            for source in sources
            if _row_predictive_eligible(
                source,
                normalized_header,
                critical_criterion_frozen=critical_criterion_frozen,
            )
        ),
        refusal_reasons=tuple(refusal),
        superseded_evidence_notes=tuple(superseded),
        pr95_supplement={
            "pr": 95,
            "head_revision": PR95_HEAD_REVISION,
            "merge_status": "OPEN_UNMERGED",
            "classification": CLASS_NOT_VERIFIED,
            "consumed_as_canonical_evidence": False,
            "trial_json_sha256": PR95_TRIAL_SHA256,
            "summary": (
                "2026-11-09 passive S1 trial: capture PASS, VALID passive "
                "baseline, NOT ADMITTED to the frozen 18-row/segment "
                "export; door_status=UNVERIFIED, calibration_id=UNRECORDED, "
                "2 PZEM timeout frames; supplementary material only, pending "
                "merge and its restrictions a-g"
            ),
        },
    )


# ---------------------------------------------------------------------------
# B-W13-02 per-horizon grouped study (synthetic development population)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MethodFoldMetrics:
    method: str
    fold_id: str
    fit_status: str
    average_precision: MetricValue
    event_recall: float | None
    false_warning_episodes_per_hour: float | None
    missed_critical_events: int | None
    unmatched_warnings: int | None
    undefined_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "fold_id": self.fold_id,
            "fit_status": self.fit_status,
            "average_precision": self.average_precision.to_dict(),
            "event_recall": self.event_recall,
            "false_warning_episodes_per_hour": self.false_warning_episodes_per_hour,
            "missed_critical_events": self.missed_critical_events,
            "unmatched_warnings": self.unmatched_warnings,
            "undefined_reasons": list(self.undefined_reasons),
        }


@dataclass(frozen=True)
class HorizonMetrics:
    horizon_s: float
    label_identity: Mapping[str, Any]
    evaluable_samples: int
    positive_count: int
    negative_count: int
    prevalence: float | None
    censored_exclusions: int
    untrusted_exclusions: int
    method_folds: tuple[MethodFoldMetrics, ...]
    aggregate_ap: Mapping[str, Mapping[str, Any]]
    oof_status: Mapping[str, str]
    leakage_audit_status: str
    leakage_probes: Mapping[str, str]
    ewt_status: str
    ewt_reason_code: str
    aiw_status: str
    aiw_reason_code: str
    model_artifact_hashes: Mapping[str, str]
    refusal_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_s": self.horizon_s,
            "population": POPULATION_SYNTHETIC,
            "label_identity": dict(self.label_identity),
            "evaluable_samples": self.evaluable_samples,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "positive_prevalence": self.prevalence,
            "censored_exclusions": self.censored_exclusions,
            "untrusted_exclusions": self.untrusted_exclusions,
            "method_folds": [item.to_dict() for item in self.method_folds],
            "aggregate_ap": {
                method: dict(value) for method, value in self.aggregate_ap.items()
            },
            "oof_status": dict(self.oof_status),
            "leakage_audit_status": self.leakage_audit_status,
            "leakage_probes": dict(self.leakage_probes),
            "ewt_status": self.ewt_status,
            "ewt_reason_code": self.ewt_reason_code,
            "aiw_status": self.aiw_status,
            "aiw_reason_code": self.aiw_reason_code,
            "model_artifact_hashes": dict(self.model_artifact_hashes),
            "refusal_reason": self.refusal_reason,
            "scientific_claim_status": CLAIM_SYNTHETIC,
        }


@dataclass(frozen=True)
class HorizonStudy:
    layer_version: str
    fixture_dataset_id: str
    fixture_version: str
    base_config_sha256: str
    registry_sha256: str
    spec_version: str
    horizons: tuple[HorizonMetrics, ...]
    split_identity: Mapping[str, Any]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer_version": self.layer_version,
            "fixture_dataset_id": self.fixture_dataset_id,
            "fixture_version": self.fixture_version,
            "base_config_sha256": self.base_config_sha256,
            "registry_sha256": self.registry_sha256,
            "spec_version": self.spec_version,
            "horizons": [item.to_dict() for item in self.horizons],
            "split_identity": dict(self.split_identity),
            "limitations": list(self.limitations),
        }


def _baseline_fold(row: Mapping[str, Any]) -> MethodFoldMetrics:
    ap_value = row["sample_ap"]
    reasons = tuple(row["sample_undefined_reasons"]) + tuple(row["undefined_reasons"])
    return MethodFoldMetrics(
        method=str(row["method"]),
        fold_id=str(row["fold_id"]),
        fit_status="BASELINE_REPLAY",
        average_precision=MetricValue(
            float(ap_value) if ap_value is not None else None,
            ";".join(reasons) if ap_value is None and reasons else None,
        ),
        event_recall=row["event_recall"],
        false_warning_episodes_per_hour=row["false_warning_episodes_per_hour"],
        missed_critical_events=row["missed_critical_events"],
        unmatched_warnings=row["unmatched_warnings"],
        undefined_reasons=tuple(dict.fromkeys(reasons)),
    )


def _xgb_fold(result: Any) -> MethodFoldMetrics:
    metrics = result.metrics
    events = result.event_metrics or {}
    if metrics is None:
        return MethodFoldMetrics(
            method=result.strategy,
            fold_id=result.fold_id,
            fit_status=result.status,
            average_precision=MetricValue(None, result.reason),
            event_recall=None,
            false_warning_episodes_per_hour=None,
            missed_critical_events=None,
            unmatched_warnings=None,
            undefined_reasons=(result.reason or "FOLD_REFUSED",),
        )
    ap = metrics["average_precision"]
    reasons = list(metrics.get("undefined_reasons") or [])
    if ap["value"] is None and ap.get("reason"):
        reasons.append(ap["reason"])
    reasons.extend(events.get("undefined_reasons", ()))
    return MethodFoldMetrics(
        method=result.strategy,
        fold_id=result.fold_id,
        fit_status=result.status,
        average_precision=MetricValue(
            float(ap["value"]) if ap["value"] is not None else None,
            ";".join(dict.fromkeys(reasons)) if ap["value"] is None else None,
        ),
        event_recall=events.get("event_recall"),
        false_warning_episodes_per_hour=events.get("false_warning_episodes_per_hour"),
        missed_critical_events=events.get("missed_critical_events"),
        unmatched_warnings=events.get("unmatched_warnings"),
        undefined_reasons=tuple(dict.fromkeys(reasons)),
    )


def run_horizon_study(
    fixture: BenchmarkFixture,
    registry: FeatureRegistry,
    base_config: BenchmarkConfig,
    *,
    model_out_dir: Path,
    horizons: Sequence[float] = CANDIDATE_HORIZONS_S,
    spec_version: str = W13_LABEL_SPEC_VERSION,
) -> HorizonStudy:
    """One-factor-at-a-time horizon sensitivity on the W11 grouped pipeline.

    Only the label horizon (and its spec version) changes between runs; the
    split, folds, seed, features, baselines and model params are the frozen
    W11 development configuration. Model artifacts are written to the caller's
    scratch directory and hash-recorded, never committed as W13 deliverables.
    """
    if base_config.label.frozen_at is not None or base_config.label.boundary_c is not None:
        raise HorizonEngineeringError(
            "W13 studies development label candidates; a frozen physical "
            "label boundary cannot enter this synthetic sensitivity path"
        )
    if not horizons or any(h <= 0 for h in horizons):
        raise HorizonEngineeringError("study horizons must be positive")
    horizon_metrics: list[HorizonMetrics] = []
    split_identity: Mapping[str, Any] | None = None
    for horizon in horizons:
        variant = replace(
            base_config,
            label=replace(
                base_config.label,
                horizon_s=float(horizon),
                spec_version=spec_version,
            ),
        )
        out_dir = model_out_dir / f"H{horizon:g}"
        labeled = build_labeled_dataset(fixture, registry, variant)
        labeled_run_ids = {sample.run_id for sample in labeled.samples}
        empty_runs = [
            run_id for run_id in labeled.run_ids if run_id not in labeled_run_ids
        ]
        evaluable = labeled.positive_count + labeled.negative_count
        if empty_runs:
            horizon_metrics.append(
                HorizonMetrics(
                    horizon_s=float(horizon),
                    label_identity=dict(labeled.label_identity),
                    evaluable_samples=evaluable,
                    positive_count=labeled.positive_count,
                    negative_count=labeled.negative_count,
                    prevalence=(
                        labeled.positive_count / evaluable if evaluable else None
                    ),
                    censored_exclusions=labeled.total_excluded.get("CENSORED", 0),
                    untrusted_exclusions=labeled.total_excluded.get("UNTRUSTED_INFO", 0),
                    method_folds=(),
                    aggregate_ap={},
                    oof_status={},
                    leakage_audit_status="NOT_RUN_HORIZON_REFUSED",
                    leakage_probes={},
                    ewt_status=NOT_ESTIMABLE,
                    ewt_reason_code=EWT_REASON_NO_COMMON_TRAJECTORY,
                    aiw_status=NOT_ESTIMABLE,
                    aiw_reason_code=AIW_REASON_MISSING_LATENCY_CHAIN,
                    model_artifact_hashes={},
                    refusal_reason=(
                        "W13_HORIZON_NOT_ESTIMABLE: the label configuration "
                        f"leaves {len(empty_runs)} of {len(labeled.run_ids)} "
                        "runs with zero evaluable anchors; the shared W11 "
                        "grouped benchmark refuses that declared population "
                        "deterministically "
                        "(DEV_RUN_WITHOUT_EVALUABLE_ANCHORS) instead of "
                        "dropping a run, so the horizon is not estimable under "
                        "the frozen benchmark contract; the remaining "
                        f"evaluable population is {labeled.positive_count} "
                        f"positive and {labeled.negative_count} negative"
                        + (
                            ", which is single-class, so AP and event metrics "
                            "stay undefined"
                            if labeled.positive_count == 0
                            or labeled.negative_count == 0
                            else ""
                        )
                    ),
                )
            )
            continue
        result, _models = run_grouped_benchmark(
            fixture, registry, variant, out_dir=out_dir
        )
        audit = run_leakage_audit(fixture, registry, variant, benchmark=result)
        failed = [probe.probe_id for probe in audit.probes if probe.status == "FAIL"]
        if failed:
            raise HorizonEngineeringError(
                f"leakage audit failed at horizon {horizon:g}s: {failed}"
            )
        folds = [
            _baseline_fold(row)
            for row in result.baseline_rows
            if not str(row["method"]).startswith("XGBOOST_V1_")
        ]
        folds.extend(_xgb_fold(item) for item in result.fold_runs)
        methods = sorted({fold.method for fold in folds})
        aggregate = {
            method: aggregate_fold_ap(
                [fold.average_precision for fold in folds if fold.method == method]
            )
            for method in methods
        }
        labeled = result.labeled
        evaluable = labeled.positive_count + labeled.negative_count
        artifact_hashes: dict[str, str] = {}
        if result.model_artifact:
            for name, entry in result.model_artifact["files"].items():
                artifact_hashes[f"H{horizon:g}/{name}"] = entry["sha256"]
        split_identity = result.split_identity
        horizon_metrics.append(
            HorizonMetrics(
                horizon_s=float(horizon),
                label_identity=dict(labeled.label_identity),
                evaluable_samples=evaluable,
                positive_count=labeled.positive_count,
                negative_count=labeled.negative_count,
                prevalence=(
                    labeled.positive_count / evaluable if evaluable else None
                ),
                censored_exclusions=labeled.total_excluded.get("CENSORED", 0),
                untrusted_exclusions=labeled.total_excluded.get("UNTRUSTED_INFO", 0),
                method_folds=tuple(folds),
                aggregate_ap=aggregate,
                oof_status={
                    strategy: str(payload["status"])
                    for strategy, payload in result.oof.items()
                },
                leakage_audit_status="PASS",
                leakage_probes={
                    probe.probe_id: probe.status for probe in audit.probes
                },
                ewt_status=NOT_ESTIMABLE,
                ewt_reason_code=EWT_REASON_NO_COMMON_TRAJECTORY,
                aiw_status=NOT_ESTIMABLE,
                aiw_reason_code=AIW_REASON_MISSING_LATENCY_CHAIN,
                model_artifact_hashes=artifact_hashes,
            )
        )
    if split_identity is None:
        raise HorizonEngineeringError("no horizon produced a split identity")
    if split_identity.get("test_partition_used"):
        raise HorizonEngineeringError("the locked test partition was touched")
    return HorizonStudy(
        layer_version=W13_LAYER_VERSION,
        fixture_dataset_id=fixture.dataset_id,
        fixture_version=fixture.fixture_version,
        base_config_sha256=base_config.config_sha256,
        registry_sha256=registry.schema_sha256,
        spec_version=spec_version,
        horizons=tuple(horizon_metrics),
        split_identity=dict(split_identity),
        limitations=(
            "synthetic development population only; no real physical run is "
            "eligible for the predictive dataset under the W04 ladder",
            "the synthetic data-generating process does not approximate the "
            "six-litre plant; AP values are software controls",
            "EWT and AIW are NOT_ESTIMABLE: no measured non-overlapping "
            "latency chain and no eligible non-intervened real pair exist",
            "censored horizons are excluded, never labeled negative",
            "the locked synthetic test pair and any locked physical test "
            "partition remain untouched",
            "a horizon whose label configuration leaves a run with zero "
            "evaluable anchors is recorded as NOT_ESTIMABLE because the shared "
            "W11 grouped benchmark refuses that declared population "
            "(DEV_RUN_WITHOUT_EVALUABLE_ANCHORS) rather than drop the run; the "
            "W11 repair is verified by the W13 regression, not reimplemented "
            "here",
        ),
    )


def real_refusal_rows(
    reconciliation: DatasetReconciliation, horizons: Sequence[float]
) -> tuple[dict[str, Any], ...]:
    reasons = ";".join(reconciliation.refusal_reasons)
    return tuple(
        {
            "row_type": "REAL_REFUSAL",
            "population": POPULATION_REAL,
            "horizon_s": float(horizon),
            "method": "ALL",
            "fold_id": "ALL",
            "evaluable_samples": 0,
            "positive_count": None,
            "negative_count": None,
            "positive_prevalence": None,
            "censored_exclusions": None,
            "untrusted_exclusions": None,
            "average_precision": None,
            "ap_status": NOT_ESTIMABLE,
            "ap_reason": reasons,
            "event_recall": None,
            "false_warning_episodes_per_hour": None,
            "missed_critical_events": None,
            "unmatched_warnings": None,
            "ewt_status": NOT_ESTIMABLE,
            "ewt_reason_code": "NO_ELIGIBLE_REAL_PREDICTIVE_RUNS",
            "aiw_status": NOT_ESTIMABLE,
            "aiw_reason_code": "DOOR_CRITICAL_NOT_COMPUTABLE_AND_LATENCY_CHAIN_MISSING",
            "undefined_reasons": reasons,
            "scientific_claim_status": CLAIM_REAL_REFUSAL,
            "provenance": f"origin/main@{reconciliation.source_revision}",
        }
        for horizon in horizons
    )


def horizon_metrics_csv_rows(
    study: HorizonStudy, reconciliation: DatasetReconciliation
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metrics in study.horizons:
        rows.append(
            {
                "row_type": "HORIZON_LABELS",
                "population": POPULATION_SYNTHETIC,
                "horizon_s": metrics.horizon_s,
                "method": "ALL",
                "fold_id": "ALL",
                "evaluable_samples": metrics.evaluable_samples,
                "positive_count": metrics.positive_count,
                "negative_count": metrics.negative_count,
                "positive_prevalence": metrics.prevalence,
                "censored_exclusions": metrics.censored_exclusions,
                "untrusted_exclusions": metrics.untrusted_exclusions,
                "average_precision": None,
                "ap_status": None,
                "ap_reason": None,
                "event_recall": None,
                "false_warning_episodes_per_hour": None,
                "missed_critical_events": None,
                "unmatched_warnings": None,
                "ewt_status": metrics.ewt_status,
                "ewt_reason_code": metrics.ewt_reason_code,
                "aiw_status": metrics.aiw_status,
                "aiw_reason_code": metrics.aiw_reason_code,
                "undefined_reasons": metrics.refusal_reason or "",
                "scientific_claim_status": CLAIM_SYNTHETIC,
                "provenance": study.fixture_dataset_id,
            }
        )
        for fold in metrics.method_folds:
            rows.append(
                {
                    "row_type": "METHOD_FOLD",
                    "population": POPULATION_SYNTHETIC,
                    "horizon_s": metrics.horizon_s,
                    "method": fold.method,
                    "fold_id": fold.fold_id,
                    "evaluable_samples": None,
                    "positive_count": None,
                    "negative_count": None,
                    "positive_prevalence": None,
                    "censored_exclusions": None,
                    "untrusted_exclusions": None,
                    "average_precision": fold.average_precision.value,
                    "ap_status": (
                        "DEFINED" if fold.average_precision.defined else "UNDEFINED"
                    ),
                    "ap_reason": fold.average_precision.reason,
                    "event_recall": fold.event_recall,
                    "false_warning_episodes_per_hour": (
                        fold.false_warning_episodes_per_hour
                    ),
                    "missed_critical_events": fold.missed_critical_events,
                    "unmatched_warnings": fold.unmatched_warnings,
                    "ewt_status": metrics.ewt_status,
                    "ewt_reason_code": metrics.ewt_reason_code,
                    "aiw_status": metrics.aiw_status,
                    "aiw_reason_code": metrics.aiw_reason_code,
                    "undefined_reasons": ";".join(fold.undefined_reasons),
                    "scientific_claim_status": CLAIM_SYNTHETIC,
                    "provenance": study.fixture_dataset_id,
                }
            )
    rows.extend(real_refusal_rows(reconciliation, [m.horizon_s for m in study.horizons]))
    return rows


# ---------------------------------------------------------------------------
# B-W13-03/04 decision: never freeze from synthetic or incomplete evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HorizonDecision:
    category: str
    display_category: str
    primary_horizon_s: float | None
    provisional_candidates_s: tuple[float, ...]
    deprioritized_s: tuple[float, ...]
    selection_preconditions: Mapping[str, bool]
    blockers: tuple[str, ...]
    rationale: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "display_category": self.display_category,
            "primary_horizon_s": self.primary_horizon_s,
            "provisional_candidates_s": list(self.provisional_candidates_s),
            "deprioritized_s": list(self.deprioritized_s),
            "selection_preconditions": dict(self.selection_preconditions),
            "blockers": list(self.blockers),
            "rationale": list(self.rationale),
            "freeze_status": "NOT_FROZEN",
        }


def selection_preconditions(
    study: HorizonStudy,
    reconciliation: DatasetReconciliation,
    timing: PlantTiming,
    base_config: BenchmarkConfig,
    *,
    selection_rule_frozen: bool = False,
    latency_chain_measured: bool = False,
) -> dict[str, bool]:
    return {
        "real_eligible_predictive_runs": reconciliation.predictive_eligible_runs > 0,
        "critical_criterion_frozen": (
            base_config.label.frozen_at is not None
            and base_config.label.boundary_c is not None
        ),
        "door_to_critical_measured": timing.door_to_critical_s is not None,
        "measured_latency_chain": latency_chain_measured,
        "selection_rule_frozen_before_outcomes": selection_rule_frozen,
        "locked_test_untouched": not study.split_identity.get("test_partition_used", True),
    }


def decide_primary_horizon(
    study: HorizonStudy,
    reconciliation: DatasetReconciliation,
    timing: PlantTiming,
    base_config: BenchmarkConfig,
    screenings: Sequence[HorizonScreening],
    *,
    selection_rule_frozen: bool = False,
    latency_chain_measured: bool = False,
    real_horizon_metrics: Mapping[float, Mapping[str, Any]] | None = None,
) -> HorizonDecision:
    """Selection requires real evidence plus a pre-frozen tradeoff rule.

    Synthetic AP — including a perfect 1.0 — is never decision-grade. The
    PRIMARY branch additionally requires caller-supplied real per-horizon
    metrics with defined AP and an actionability verdict; the W13 CLI never
    produces those while the admission ladder refuses every real run, and
    the caller's own selection rule (frozen before outcomes) owns any AP or
    false-warning floor.
    """
    preconditions = selection_preconditions(
        study,
        reconciliation,
        timing,
        base_config,
        selection_rule_frozen=selection_rule_frozen,
        latency_chain_measured=latency_chain_measured,
    )
    blockers = [name for name, ok in preconditions.items() if not ok]
    provisional = tuple(
        screening.horizon_s
        for screening in screenings
        if screening.screen == SCREEN_PROVISIONAL
    )
    deprioritized = tuple(
        screening.horizon_s
        for screening in screenings
        if screening.screen == SCREEN_DEPRIORITIZED
    )
    rationale = [
        "candidate set comes from the canonical 30/60/120/300 s exploratory "
        "horizons for the fast six-litre plant; no longer horizon is invented "
        "because the measured tau proxies are truncation-biased",
        "physics screening deprioritizes horizons at or below the measured "
        "applied-on->thermal response proxy (AIW upper bound <= 0 even with "
        "zero system latency); the screening is DERIVED, not a measured verdict",
        "synthetic per-horizon AP is a software control; the highest synthetic "
        "AP never selects a primary horizon",
        f"real predictive eligibility is refused ({reconciliation.predictive_eligible_runs} "
        "eligible runs); real prevalence, AP, event recall, false warnings, "
        "EWT and AIW are NOT_ESTIMABLE, not zero",
        "T_critical, representative temperature and the primary horizon "
        "remain unfrozen ledger items; D's critical-Tmean threshold freeze "
        "and A's offline door->critical rerun are outstanding",
    ]
    if all(preconditions.values()) and real_horizon_metrics:
        defined = {
            horizon: metrics
            for horizon, metrics in real_horizon_metrics.items()
            if metrics.get("average_precision") is not None
            and metrics.get("aiw_positive") is True
        }
        if len(defined) == 1:
            (horizon, _metrics), = defined.items()
            return HorizonDecision(
                category=DECISION_PRIMARY,
                display_category=DECISION_PRIMARY,
                primary_horizon_s=float(horizon),
                provisional_candidates_s=(),
                deprioritized_s=deprioritized,
                selection_preconditions=preconditions,
                blockers=(),
                rationale=tuple(rationale) + (
                    "exactly one real-evidence candidate passes the caller's "
                    "selection rule, which must have been declared frozen "
                    "before outcomes; the W13 layer does not itself define "
                    "AP or false-warning floors",
                ),
            )
        blockers.append("REAL_CANDIDATE_NOT_UNIQUE_UNDER_FROZEN_RULE")
    if provisional:
        category = DECISION_PROVISIONAL
        display = DECISION_PROVISIONAL
    else:
        category = DECISION_NO_SELECTION
        display = DECISION_NO_SELECTION_DISPLAY
    return HorizonDecision(
        category=category,
        display_category=display,
        primary_horizon_s=None,
        provisional_candidates_s=provisional,
        deprioritized_s=deprioritized,
        selection_preconditions=preconditions,
        blockers=tuple(blockers),
        rationale=tuple(rationale),
    )