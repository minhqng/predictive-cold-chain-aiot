"""W08 Gate B dataset readiness (B-W08-01 … B-W08-04).

The module validates one physical candidate run and aggregates transparent
``GREEN`` / ``YELLOW`` / ``RED`` decisions. It reuses W04 intake/admission,
W05 sampling QA, W06 timing/event diagnostics, W07 physical-run independence
semantics and W02 grouped split logic; it does not parse A/C formats, retrain,
or create a locked test manifest.

Scientific boundaries enforced here:

* A's explicit invalidation is authoritative; B never promotes A-INVALID to
  A-VALID, and plausible temperatures do not override an invalid ledger;
* a structurally valid capture is not automatically a physically qualified
  run, and a physically qualified run is not automatically a ready dataset;
* an export SHA is evidence of different bytes, not a separate experiment;
  repeated views of one physical source are counted once;
* completeness denominators use the observed acquisition cadence, never a
  filename-implied 1 Hz and never a fabricated full-run duration;
* short event-window gaps are not hidden by a high whole-run percentage;
* a missing event anchor, missing critical channel, or unresolved threshold is
  reported as ``NOT_ESTIMABLE``/blocked, never silently replaced with zero;
* a provisional split is a planning shape, not a locked test-set assignment.
"""

from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass
from typing import Any, Sequence

from .intake import (
    AdmissionResult,
    AdmissionStage,
    Capture,
    NormalizedRow,
    evaluate_admission,
    summarize_readiness,
)
from .real_data_qa import (
    QAConfig,
    QAAnalysis,
    analyze_capture,
)
from .splitting import (
    RunInfo,
    SplitConfig,
    SplitError,
    SplitProportions,
    split_runs,
)
from .timing_alignment import (
    TimingAudit,
    audit_timeline,
    deduplicate_events,
    events_from_capture,
)

W08_LAYER_VERSION = "coldguard-w08-gate-b-readiness-v1"
W08_REPORT_SCHEMA = "coldguard-w08-gate-b-readiness-report-v1"
W08_MANIFEST_SCHEMA = "coldguard-w08-gate-b-readiness-manifest-v1"
COMPLETENESS_POLICY_VERSION = "coldguard-w08-completeness-policy-draft-v1"

GATE_SOFTWARE = "W08_SOFTWARE_VERIFICATION"
GATE_B_PHYSICAL = "GATE_B_PHYSICAL_DATA"
GATE_PREDICTIVE = "PREDICTIVE_DATASET_READINESS"
GATE_SPLIT = "SPLIT_FEASIBILITY"

VERDICT_GREEN = "GREEN"
VERDICT_YELLOW = "YELLOW"
VERDICT_RED = "RED"
VERDICT_PASS = "PASS"
VERDICT_BLOCKED = "BLOCKED"
VERDICT_NOT_READY = "NOT_READY"
VERDICT_READY = "READY"
VERDICT_NOT_VERIFIED = "NOT_VERIFIED"

CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"
CHECK_NOT_EVALUABLE = "NOT_EVALUABLE"
CHECK_NOT_APPLICABLE = "NOT_APPLICABLE"

SEVERITY_BLOCKING = "BLOCKING"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"

THRESHOLD_FROZEN = "FROZEN"
THRESHOLD_PROPOSED = "PROPOSED"
THRESHOLD_UNRESOLVED = "UNRESOLVED"

STAGE_IDENTITY = "IDENTITY_AND_LINEAGE"
STAGE_CONFIGURATION = "PHYSICAL_CONFIGURATION"
STAGE_MEASUREMENTS = "MEASUREMENTS"
STAGE_PROTOCOL = "PROTOCOL_AND_EVENTS"
STAGE_AUTHORITY = "AUTHORITY"

ELIGIBILITY_ELIGIBLE = "ELIGIBLE_FOR_DATASET"
ELIGIBILITY_DIAGNOSTIC = "DIAGNOSTIC_ONLY"
ELIGIBILITY_BLOCKED = "BLOCKED"

DIMENSION_WHOLE = "WHOLE_CAPTURE_COMPLETENESS"
DIMENSION_EVENT = "PRIMARY_EVENT_WINDOW_COMPLETENESS"
DIMENSION_BASELINE = "PRE_EVENT_BASELINE_COMPLETENESS"
DIMENSION_RECOVERY = "POST_EVENT_OR_RECOVERY_COMPLETENESS"
DIMENSION_CRITICAL = "CRITICAL_CHANNEL_COMPLETENESS"
DIMENSION_TIMING = "TIMING_ALIGNMENT_COMPLETENESS"
COMPLETENESS_DIMENSIONS = (
    DIMENSION_WHOLE,
    DIMENSION_EVENT,
    DIMENSION_BASELINE,
    DIMENSION_RECOVERY,
    DIMENSION_CRITICAL,
    DIMENSION_TIMING,
)

SPLIT_FEASIBLE = "FEASIBLE"
SPLIT_PROVISIONAL = "PROVISIONAL"
SPLIT_NOT_FEASIBLE = "NOT_FEASIBLE"

P3_NOT_FROZEN = "PLANNING_CANDIDATES_ONLY_NOT_A_LOCKED_TEST"

REASON_PASS = "CHECK_PASSED"
REASON_NOT_APPLICABLE = "CHECK_NOT_APPLICABLE"
REASON_AUTHORITY_INVALID = "AUTHORITY_A_LEDGER_INVALID"
REASON_AUTHORITY_MISSING = "AUTHORITY_A_LEDGER_MISSING"
REASON_DIAGNOSTIC_ONLY = "STRUCTURALLY_VALID_BUT_NOT_DATASET_ELIGIBLE"
REASON_MANIFEST_MISSING = "RUN_MANIFEST_LINKAGE_NOT_PROVIDED"
REASON_MANIFEST_MISMATCH = "RUN_MANIFEST_LINKAGE_MISMATCH"
REASON_CAPTURE_DURATION = "CAPTURE_DURATION_NOT_DECLARED"
REASON_CAPTURE_SHORTER = "CAPTURE_SHORTER_THAN_PLANNED_INTERVAL"
REASON_EVENT_ANCHOR_MISSING = "REQUIRED_EVENT_ANCHOR_MISSING"
REASON_EVENT_UNQUALIFIED = "REQUIRED_EVENT_UNQUALIFIED"
REASON_EVENT_WINDOW_GAP = "PRIMARY_EVENT_WINDOW_INCOMPLETE"
REASON_EVENT_WINDOW_CENSORED = "RECOVERY_WINDOW_CENSORED"
REASON_BASELINE_INCOMPLETE = "PRE_EVENT_BASELINE_INCOMPLETE"
REASON_RECOVERY_INCOMPLETE = "RECOVERY_WINDOW_INCOMPLETE"
REASON_CRITICAL_CHANNEL = "CRITICAL_CHANNEL_NOT_VALID"
REASON_CRITICAL_MISSING = "CRITICAL_CHANNEL_SAMPLE_MISSING"
REASON_WHOLE_INCOMPLETE = "WHOLE_CAPTURE_COMPLETENESS_BELOW_THRESHOLD"
REASON_COMPLETENESS_NOT_ESTIMABLE = "COMPLETENESS_NOT_ESTIMABLE"
REASON_THRESHOLD_UNRESOLVED = "COMPLETENESS_THRESHOLD_UNRESOLVED"
REASON_THRESHOLD_EQUALITY = "THRESHOLD_EQUALITY_PASSES"
REASON_SEQUENCE_DUPLICATE = "SEQUENCE_IDENTITY_DUPLICATE"
REASON_SEQUENCE_NON_MONOTONIC = "SEQUENCE_NOT_MONOTONIC"
REASON_TIME_ABSOLUTE = "ABSOLUTE_TIME_NOT_EVIDENCED"
REASON_PZEM_UNQUALIFIED = "PZEM_NOT_QUALIFIED_FOR_ELECTRICAL_CLAIM"
REASON_DOOR_UNQUALIFIED = "DOOR_CHANNEL_NOT_QUALIFIED_FOR_DISTURBANCE"
REASON_COMMAND_CHAIN = "REQUIRED_COMMAND_CHAIN_ABSENT"
REASON_INTERVENTION = "INTERVENTION_OR_CENSORING_NOT_RECORDED"
REASON_POPULATION = "NO_ELIGIBLE_RUNS_FOR_DECLARED_SCENARIO"
REASON_INDEPENDENT_POPULATION = "INDEPENDENT_RUN_POPULATION_INSUFFICIENT"
REASON_DUPLICATE_CONFLICT = "DUPLICATE_VIEW_ADMISSION_CONFLICT"
REASON_SPLIT_INFEASIBLE = "SPLIT_POPULATION_INSUFFICIENT"
REASON_SPLIT_PAIR_STRADDLE = "PAIR_LINEAGE_CANNOT_BE_SPLIT"
REASON_SPLIT_PLANNING = "SPLIT_PLAN_IS_PROVISIONAL"
REASON_W07_NOT_ESTABLISHED = "W07_PHYSICAL_REPEATABILITY_NOT_ESTABLISHED"
REASON_SOFTWARE_COMPLETE = "SOFTWARE_VALIDATION_COMPLETED"
REASON_PERMUTATION = "INPUT_PERMUTATION_INVARIANT"


@dataclass(frozen=True)
class CompletenessThreshold:
    name: str
    dimension: str
    applicable_scenario: str
    channel_family: str
    required_event_window: str
    definition: str
    denominator: str
    missing_semantics: str
    source_justification: str
    status: str
    equality_behavior: str
    blocking_severity: str
    owner: str
    review_authority: str
    value: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dimension": self.dimension,
            "applicable_scenario": self.applicable_scenario,
            "channel_family": self.channel_family,
            "required_event_window": self.required_event_window,
            "definition": self.definition,
            "expected_sample_denominator": self.denominator,
            "missing_quality_semantics": self.missing_semantics,
            "threshold_source_justification": self.source_justification,
            "threshold_status": self.status,
            "comparison_at_equality": self.equality_behavior,
            "blocking_severity": self.blocking_severity,
            "owner": self.owner,
            "review_authority": self.review_authority,
            "threshold_value": self.value,
        }


@dataclass(frozen=True)
class CompletenessPolicy:
    policy_version: str
    thresholds: tuple[CompletenessThreshold, ...]
    notes: tuple[str, ...]

    def threshold(self, dimension: str) -> CompletenessThreshold:
        for threshold in self.thresholds:
            if threshold.dimension == dimension:
                return threshold
        raise KeyError(f"no completeness threshold for {dimension!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "thresholds": [threshold.to_dict() for threshold in self.thresholds],
            "notes": list(self.notes),
        }


def default_completeness_policy() -> CompletenessPolicy:
    """Draft policy derived from physical/event requirements, not a global %.

    Numerical PROPOSED values are planning candidates pending owner review;
    they are never silently frozen. The timing-alignment fraction stays
    UNRESOLVED because no cadence tolerance has been frozen by the project.
    """
    owner = "Member B — AI & Experimental Data"
    review = "Project lead + Member A (physical evidence)"
    thresholds = (
        CompletenessThreshold(
            name="whole_capture_frames",
            dimension=DIMENSION_WHOLE,
            applicable_scenario="S1 and S2",
            channel_family="all received frames",
            required_event_window="whole capture",
            definition=(
                "received frames divided by expected samples derived from the "
                "observed modal cadence and the measured capture duration"
            ),
            denominator=(
                "declared planned capture duration divided by the observed "
                "modal cadence, plus one; the W05 observed-window fraction is "
                "diagnostic only"
            ),
            missing_semantics=(
                "missing frames reduce the numerator; an undeclared planned "
                "duration makes the value NOT_ESTIMABLE, never 1.0"
            ),
            source_justification=(
                "Doc 03 §119 requires completeness against actual cadence; W05 "
                "supplies the observed cadence and a provisional denominator"
            ),
            status=THRESHOLD_PROPOSED,
            equality_behavior="fraction >= threshold passes",
            blocking_severity=SEVERITY_BLOCKING,
            owner=owner,
            review_authority=review,
            value=0.95,
        ),
        CompletenessThreshold(
            name="critical_channel_samples",
            dimension=DIMENSION_CRITICAL,
            applicable_scenario="S1 and S2",
            channel_family="required thermal channels; door for S2; PZEM only when claimed",
            required_event_window="whole capture for S1; event windows for S2",
            definition=(
                "frames where every declared critical channel is present and "
                "source-quality VALID divided by expected samples"
            ),
            denominator=(
                "declared planned capture duration divided by the observed "
                "modal cadence, plus one"
            ),
            missing_semantics=(
                "missing, INVALID and DEGRADED critical samples are counted "
                "separately; none is converted to a numeric zero"
            ),
            source_justification=(
                "Doc 01 §§19,33 and Doc 03 §122: a critical channel gap "
                "overlapping the primary outcome invalidates the run; the "
                "numeric fraction is provisional pending A's physical review"
            ),
            status=THRESHOLD_PROPOSED,
            equality_behavior="fraction >= threshold passes",
            blocking_severity=SEVERITY_BLOCKING,
            owner=owner,
            review_authority=review,
            value=0.99,
        ),
        CompletenessThreshold(
            name="primary_event_window_samples",
            dimension=DIMENSION_EVENT,
            applicable_scenario="S2 (event-required scenarios)",
            channel_family="required thermal + door channels",
            required_event_window="[event anchor, anchor + event window]",
            definition=(
                "critical-valid frames inside the primary event window divided "
                "by expected samples for that window at the observed cadence"
            ),
            denominator="round(event_window_s / nominal_dt_s)",
            missing_semantics=(
                "a window gap is counted separately from whole-capture loss; "
                "a missing event anchor makes the dimension NOT_ESTIMABLE"
            ),
            source_justification=(
                "Doc 03 §119 requires stronger completeness around the event "
                "that defines the primary outcome than over the whole run; the "
                "event window length is a planning candidate only"
            ),
            status=THRESHOLD_PROPOSED,
            equality_behavior="fraction >= threshold passes",
            blocking_severity=SEVERITY_BLOCKING,
            owner=owner,
            review_authority=review,
            value=0.99,
        ),
        CompletenessThreshold(
            name="pre_event_baseline_samples",
            dimension=DIMENSION_BASELINE,
            applicable_scenario="S2 (event-required scenarios)",
            channel_family="required thermal + door channels",
            required_event_window="[anchor - baseline window, anchor)",
            definition=(
                "critical-valid frames in the pre-event baseline divided by "
                "expected samples for that window at the observed cadence"
            ),
            denominator="round(baseline_window_s / nominal_dt_s)",
            missing_semantics=(
                "a baseline shorter than the required window is incomplete; "
                "missing samples are never back-filled"
            ),
            source_justification=(
                "Doc 03 §§5–8 require a pre-event baseline for response and "
                "prediction claims; W10's 120 s recipe is a planning candidate"
            ),
            status=THRESHOLD_PROPOSED,
            equality_behavior="fraction >= threshold passes",
            blocking_severity=SEVERITY_BLOCKING,
            owner=owner,
            review_authority=review,
            value=0.95,
        ),
        CompletenessThreshold(
            name="recovery_followup_samples",
            dimension=DIMENSION_RECOVERY,
            applicable_scenario="S2 (event-required scenarios)",
            channel_family="required thermal channels",
            required_event_window="[anchor + event window, anchor + horizon)",
            definition=(
                "critical-valid frames in the follow-up window divided by "
                "expected samples for that window at the observed cadence; a "
                "capture ending before the horizon is censored"
            ),
            denominator="round((horizon_s - event_window_s) / nominal_dt_s)",
            missing_semantics=(
                "a censored capture is reported as CENSORED and does not pass; "
                "the recovery criterion itself is not invented here"
            ),
            source_justification=(
                "Doc 01 §20.6 and Doc 03 §7 require a defined recovery "
                "reference; W07 reports reset criteria as unresolved, so the "
                "numeric value stays provisional"
            ),
            status=THRESHOLD_PROPOSED,
            equality_behavior="fraction >= threshold passes",
            blocking_severity=SEVERITY_BLOCKING,
            owner=owner,
            review_authority=review,
            value=0.90,
        ),
        CompletenessThreshold(
            name="timing_alignment_intervals",
            dimension=DIMENSION_TIMING,
            applicable_scenario="S1 and S2",
            channel_family="sequence/time",
            required_event_window="whole capture and primary event window",
            definition=(
                "observed intervals inside a frozen cadence tolerance divided "
                "by expected intervals"
            ),
            denominator="expected sample count minus one",
            missing_semantics=(
                "negative/zero intervals, sequence reversals and long gaps are "
                "reported individually; no tolerance is fabricated here"
            ),
            source_justification=(
                "Doc 03 §120 forbids assuming exact 1.000 s cadence; the "
                "project has not frozen a tolerance, so the fraction remains "
                "UNRESOLVED while timing-integrity booleans are still checked"
            ),
            status=THRESHOLD_UNRESOLVED,
            equality_behavior="not evaluable until a tolerance is frozen",
            blocking_severity=SEVERITY_INFO,
            owner=owner,
            review_authority=review,
            value=None,
        ),
    )
    return CompletenessPolicy(
        policy_version=COMPLETENESS_POLICY_VERSION,
        thresholds=thresholds,
        notes=(
            "No universal 99.9% threshold is asserted.",
            "PROPOSED values are planning candidates and must be reviewed "
            "before any frozen dataset claim.",
            "UNRESOLVED is not zero: the validator reports what is not evaluable.",
        ),
    )


@dataclass(frozen=True)
class CheckResult:
    code: str
    stage: str
    status: str
    severity: str
    detail: str
    evidence: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "stage": self.stage,
            "status": self.status,
            "severity": self.severity,
            "detail": self.detail,
            "evidence": list(self.evidence),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class CompletenessResult:
    dimension: str
    status: str
    threshold: float | None
    threshold_status: str
    equality_behavior: str
    expected_samples: int | None
    observed_samples: int | None
    missing_samples: int | None
    invalid_samples: int | None
    untrusted_samples: int | None
    fraction: float | None
    passes: bool | None
    denominator_definition: str
    detail: str
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "status": self.status,
            "threshold": self.threshold,
            "threshold_status": self.threshold_status,
            "equality_behavior": self.equality_behavior,
            "expected_samples": self.expected_samples,
            "observed_samples": self.observed_samples,
            "missing_samples": self.missing_samples,
            "invalid_samples": self.invalid_samples,
            "untrusted_samples": self.untrusted_samples,
            "fraction": self.fraction,
            "passes": self.passes,
            "denominator_definition": self.denominator_definition,
            "detail": self.detail,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class RunManifestLinkage:
    run_id: str
    device_id: str | None
    boot_id: str
    scenario_id: str
    hardware_config_id: str
    calibration_id: str | None
    source_sha256: str
    manifest_sha256: str | None = None
    pair_id: str | None = None
    controller_id: str | None = None
    planned_capture_duration_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "scenario_id": self.scenario_id,
            "hardware_config_id": self.hardware_config_id,
            "calibration_id": self.calibration_id,
            "source_sha256": self.source_sha256,
            "manifest_sha256": self.manifest_sha256,
            "pair_id": self.pair_id,
            "controller_id": self.controller_id,
            "planned_capture_duration_s": self.planned_capture_duration_s,
        }


@dataclass(frozen=True)
class ScenarioRequirement:
    scenario_id: str
    dataset_purpose: str
    requires_door_event: bool
    requires_command_chain: bool
    requires_electrical_evidence: bool
    baseline_window_s: float
    event_window_s: float
    recovery_horizon_s: float
    require_absolute_time: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "dataset_purpose": self.dataset_purpose,
            "requires_door_event": self.requires_door_event,
            "requires_command_chain": self.requires_command_chain,
            "requires_electrical_evidence": self.requires_electrical_evidence,
            "baseline_window_s": self.baseline_window_s,
            "event_window_s": self.event_window_s,
            "recovery_horizon_s": self.recovery_horizon_s,
            "require_absolute_time": self.require_absolute_time,
        }


def default_scenario_requirement(
    scenario_id: str,
    *,
    dataset_purpose: str | None = None,
    requires_command_chain: bool = False,
    requires_electrical_evidence: bool = False,
    baseline_window_s: float = 120.0,
    event_window_s: float = 60.0,
    recovery_horizon_s: float = 900.0,
) -> ScenarioRequirement:
    normalized = (scenario_id or "").upper()
    requires_door = normalized.startswith("S2")
    return ScenarioRequirement(
        scenario_id=normalized,
        dataset_purpose=dataset_purpose
        or (
            "S2 door-disturbance response dataset"
            if requires_door
            else "S1 normal-baseline predictive dataset"
        ),
        requires_door_event=requires_door,
        requires_command_chain=requires_command_chain,
        requires_electrical_evidence=requires_electrical_evidence,
        baseline_window_s=baseline_window_s,
        event_window_s=event_window_s,
        recovery_horizon_s=recovery_horizon_s,
        require_absolute_time=True,
    )


@dataclass(frozen=True)
class EventCoverage:
    required: bool
    anchor_present: bool
    anchor_time_s: float | None
    anchor_source: str
    anchor_count: int
    baseline_seconds: float | None
    event_seconds: float | None
    recovery_seconds: float | None
    censored: bool
    detail: str
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "anchor_present": self.anchor_present,
            "anchor_time_s": self.anchor_time_s,
            "anchor_source": self.anchor_source,
            "anchor_count": self.anchor_count,
            "baseline_seconds": self.baseline_seconds,
            "event_seconds": self.event_seconds,
            "recovery_seconds": self.recovery_seconds,
            "censored": self.censored,
            "detail": self.detail,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class RunValidation:
    source_path: str
    source_sha256: str
    physical_source_key: tuple[Any, ...]
    run_id: str | None
    run_id_status: str
    device_id: str | None
    boot_id: str | None
    scenario_id: str | None
    scenario_status: str | None
    hardware_config_id: str | None
    hardware_config_status: str | None
    calibration_id: str | None
    calibration_status: str | None
    firmware_version: str | None
    controller_id: str | None
    pair_id: str | None
    time_domain: str
    clock_sync_status: str
    a_ledger_verdict: str
    a_ledger_reasons: tuple[str, ...]
    admission_status: str
    admission_highest_stage: str
    eligibility: str
    checks: tuple[CheckResult, ...]
    completeness: tuple[CompletenessResult, ...]
    event_coverage: EventCoverage
    channel_coverage: tuple[dict[str, Any], ...]
    quality_findings: tuple[dict[str, Any], ...]
    reason_codes: tuple[str, ...]

    @property
    def blocking_failures(self) -> tuple[CheckResult, ...]:
        return tuple(
            check
            for check in self.checks
            if check.severity == SEVERITY_BLOCKING
            and check.status in (CHECK_FAIL, CHECK_NOT_EVALUABLE)
        )

    @property
    def warnings(self) -> tuple[CheckResult, ...]:
        return tuple(
            check
            for check in self.checks
            if check.severity == SEVERITY_WARNING
            and check.status in (CHECK_FAIL, CHECK_NOT_EVALUABLE)
        )

    def completeness_for(self, dimension: str) -> CompletenessResult | None:
        for result in self.completeness:
            if result.dimension == dimension:
                return result
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "physical_source_key": list(self.physical_source_key),
            "run_id": self.run_id,
            "run_id_status": self.run_id_status,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "scenario_id": self.scenario_id,
            "scenario_status": self.scenario_status,
            "hardware_config_id": self.hardware_config_id,
            "hardware_config_status": self.hardware_config_status,
            "calibration_id": self.calibration_id,
            "calibration_status": self.calibration_status,
            "firmware_version": self.firmware_version,
            "controller_id": self.controller_id,
            "pair_id": self.pair_id,
            "time_domain": self.time_domain,
            "clock_sync_status": self.clock_sync_status,
            "a_ledger_verdict": self.a_ledger_verdict,
            "a_ledger_reasons": list(self.a_ledger_reasons),
            "admission_status": self.admission_status,
            "admission_highest_stage": self.admission_highest_stage,
            "eligibility": self.eligibility,
            "checks": [check.to_dict() for check in self.checks],
            "completeness": [item.to_dict() for item in self.completeness],
            "event_coverage": self.event_coverage.to_dict(),
            "channel_coverage": [dict(item) for item in self.channel_coverage],
            "quality_findings": [dict(item) for item in self.quality_findings],
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class GateDecision:
    gate: str
    declared_dataset_purpose: str
    scenario: str
    population: str
    required_checks: tuple[str, ...]
    observed_status: str
    severity: str
    evidence_paths: tuple[str, ...]
    evidence_sha256: tuple[str, ...]
    reason_codes: tuple[str, ...]
    owner: str
    next_evidence_required: str
    allowed_uses: tuple[str, ...] = ()
    prohibited_uses: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "declared_dataset_purpose": self.declared_dataset_purpose,
            "scenario": self.scenario,
            "population": self.population,
            "required_checks": list(self.required_checks),
            "observed_status": self.observed_status,
            "severity": self.severity,
            "evidence_paths": list(self.evidence_paths),
            "evidence_sha256": list(self.evidence_sha256),
            "reason_codes": list(self.reason_codes),
            "owner": self.owner,
            "next_evidence_required": self.next_evidence_required,
            "allowed_uses": list(self.allowed_uses),
            "prohibited_uses": list(self.prohibited_uses),
        }


@dataclass(frozen=True)
class SplitCandidate:
    run_id: str
    scenario_id: str
    controller_id: str
    physical_source_key: tuple[Any, ...]
    pair_id: str | None
    hardware_config_id: str | None
    eligible: bool
    reason: str
    source_path: str
    source_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "controller_id": self.controller_id,
            "physical_source_key": list(self.physical_source_key),
            "pair_id": self.pair_id,
            "hardware_config_id": self.hardware_config_id,
            "eligible": self.eligible,
            "reason": self.reason,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True)
class SplitPlan:
    feasibility: str
    planning_shape: str
    candidate_count: int
    eligible_count: int
    p1_training: tuple[str, ...]
    p2_held_back_development_validation: tuple[str, ...]
    p3_future_locked_planning_candidates: tuple[str, ...]
    development_runs: tuple[str, ...]
    excluded: tuple[dict[str, Any], ...]
    pair_lineage: tuple[dict[str, Any], ...]
    grouping_key: str
    split_seed: int | None
    p3_status: str
    reasons: tuple[str, ...]
    minimum_evidence: tuple[str, ...]
    synthetic_control: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "feasibility": self.feasibility,
            "planning_shape": self.planning_shape,
            "candidate_count": self.candidate_count,
            "eligible_count": self.eligible_count,
            "P1_training": list(self.p1_training),
            "P2_held_back_development_validation": list(
                self.p2_held_back_development_validation
            ),
            "P3_future_locked_planning_candidates": list(
                self.p3_future_locked_planning_candidates
            ),
            "development_runs": list(self.development_runs),
            "definition": "development = P1_training ∪ P2_held_back_validation",
            "excluded": [dict(item) for item in self.excluded],
            "pair_lineage": [dict(item) for item in self.pair_lineage],
            "grouping_key": self.grouping_key,
            "split_seed": self.split_seed,
            "P3_status": self.p3_status,
            "reasons": list(self.reasons),
            "minimum_evidence": list(self.minimum_evidence),
            "synthetic_control": self.synthetic_control,
        }


@dataclass(frozen=True)
class GateBReport:
    scenario_requirement: ScenarioRequirement
    policy: CompletenessPolicy
    validations: tuple[RunValidation, ...]
    suite: dict[str, Any]
    software_gate: GateDecision
    physical_gate: GateDecision
    predictive_gate: GateDecision
    split_gate: GateDecision
    split_plan: SplitPlan
    separation: dict[str, str]
    w07_evidence: dict[str, Any] | None
    limitations: tuple[str, ...]

    @property
    def eligible_runs(self) -> tuple[RunValidation, ...]:
        return tuple(
            item
            for item in self.validations
            if item.eligibility == ELIGIBILITY_ELIGIBLE
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "w08_layer_version": W08_LAYER_VERSION,
            "scenario_requirement": self.scenario_requirement.to_dict(),
            "completeness_policy": self.policy.to_dict(),
            "suite": self.suite,
            "software_gate": self.software_gate.to_dict(),
            "physical_gate": self.physical_gate.to_dict(),
            "predictive_gate": self.predictive_gate.to_dict(),
            "split_gate": self.split_gate.to_dict(),
            "split_plan": self.split_plan.to_dict(),
            "runs": [item.to_dict() for item in self.validations],
            "separation": dict(self.separation),
            "w07_evidence": self.w07_evidence,
            "limitations": list(self.limitations),
        }


def _check(
    code: str,
    stage: str,
    passed: bool | None,
    *,
    severity: str = SEVERITY_BLOCKING,
    detail: str,
    evidence: Sequence[str] = (),
    reason_codes: Sequence[str] = (),
) -> CheckResult:
    if passed is None:
        status = CHECK_NOT_EVALUABLE
    elif passed:
        status = CHECK_PASS
    else:
        status = CHECK_FAIL
    return CheckResult(
        code=code,
        stage=stage,
        status=status,
        severity=severity,
        detail=detail,
        evidence=tuple(evidence),
        reason_codes=tuple(reason_codes)
        or ((REASON_PASS,) if status == CHECK_PASS else ()),
    )


def _row_time_s(row: NormalizedRow) -> float | None:
    if row.device_ms is None:
        return None
    return row.device_ms / 1000.0


def _quality(row: NormalizedRow, domain: str) -> str:
    return dict(row.quality).get(domain, "UNKNOWN")


def _critical_row_ok(
    row: NormalizedRow,
    capture: Capture,
    requirement: ScenarioRequirement,
) -> tuple[bool, bool, bool]:
    """Return (all_critical_valid, any_critical_missing, any_critical_invalid)."""
    missing = False
    invalid = False
    for slot in capture.chamber_air_slots:
        try:
            probe = row.probe(slot)
        except KeyError:
            missing = True
            continue
        if probe.value_c is None:
            missing = True
    if _quality(row, "thermal") != "VALID":
        invalid = True
    if _quality(row, "thermal") != "VALID":
        invalid = True
    if requirement.requires_door_event:
        if row.door_state not in ("OPEN", "CLOSED"):
            missing = True
        if _quality(row, "door") != "VALID":
            invalid = True
    if requirement.requires_electrical_evidence:
        if (
            row.cooling_voltage_v is None
            or row.cooling_current_a is None
            or row.cooling_power_w is None
        ):
            missing = True
        if _quality(row, "electrical") != "VALID":
            invalid = True
    ok = not missing and not invalid
    return ok, missing, invalid


def _window_rows(
    rows: Sequence[NormalizedRow],
    start_s: float,
    end_s: float,
) -> list[NormalizedRow]:
    selected: list[NormalizedRow] = []
    for row in rows:
        time_s = _row_time_s(row)
        if time_s is None:
            continue
        if start_s <= time_s < end_s:
            selected.append(row)
    return selected


def _expected_samples(duration_s: float, nominal_dt_s: float | None, *, inclusive: bool) -> int | None:
    if nominal_dt_s is None or nominal_dt_s <= 0 or duration_s < 0:
        return None
    if inclusive:
        return max(0, int(math.floor(duration_s / nominal_dt_s + 1e-9)) + 1)
    return max(0, int(round(duration_s / nominal_dt_s)))


def _completeness_result(
    *,
    dimension: str,
    policy: CompletenessPolicy,
    expected: int | None,
    observed: int | None,
    missing: int | None,
    invalid: int | None,
    untrusted: int | None,
    detail: str,
    applicable: bool = True,
) -> CompletenessResult:
    threshold = policy.threshold(dimension)
    if not applicable:
        return CompletenessResult(
            dimension=dimension,
            status=CHECK_NOT_APPLICABLE,
            threshold=threshold.value,
            threshold_status=threshold.status,
            equality_behavior=threshold.equality_behavior,
            expected_samples=expected,
            observed_samples=observed,
            missing_samples=missing,
            invalid_samples=invalid,
            untrusted_samples=untrusted,
            fraction=None,
            passes=None,
            denominator_definition=threshold.denominator,
            detail=detail,
            reason_codes=(REASON_NOT_APPLICABLE,),
        )
    if threshold.status == THRESHOLD_UNRESOLVED or threshold.value is None:
        return CompletenessResult(
            dimension=dimension,
            status=CHECK_NOT_EVALUABLE,
            threshold=None,
            threshold_status=threshold.status,
            equality_behavior=threshold.equality_behavior,
            expected_samples=expected,
            observed_samples=observed,
            missing_samples=missing,
            invalid_samples=invalid,
            untrusted_samples=untrusted,
            fraction=None,
            passes=None,
            denominator_definition=threshold.denominator,
            detail=detail,
            reason_codes=(REASON_THRESHOLD_UNRESOLVED,),
        )
    if expected is None or expected <= 0 or observed is None:
        return CompletenessResult(
            dimension=dimension,
            status=CHECK_NOT_EVALUABLE,
            threshold=threshold.value,
            threshold_status=threshold.status,
            equality_behavior=threshold.equality_behavior,
            expected_samples=expected,
            observed_samples=observed,
            missing_samples=missing,
            invalid_samples=invalid,
            untrusted_samples=untrusted,
            fraction=None,
            passes=None,
            denominator_definition=threshold.denominator,
            detail=detail,
            reason_codes=(REASON_COMPLETENESS_NOT_ESTIMABLE,),
        )
    fraction = observed / expected
    passes = fraction >= threshold.value
    reasons = (REASON_THRESHOLD_EQUALITY,) if passes else (REASON_WHOLE_INCOMPLETE,)
    if dimension == DIMENSION_CRITICAL and not passes:
        reasons = (REASON_CRITICAL_CHANNEL,)
    if dimension == DIMENSION_EVENT and not passes:
        reasons = (REASON_EVENT_WINDOW_GAP,)
    if dimension == DIMENSION_BASELINE and not passes:
        reasons = (REASON_BASELINE_INCOMPLETE,)
    if dimension == DIMENSION_RECOVERY and not passes:
        reasons = (REASON_RECOVERY_INCOMPLETE,)
    return CompletenessResult(
        dimension=dimension,
        status=CHECK_PASS if passes else CHECK_FAIL,
        threshold=threshold.value,
        threshold_status=threshold.status,
        equality_behavior=threshold.equality_behavior,
        expected_samples=expected,
        observed_samples=observed,
        missing_samples=missing,
        invalid_samples=invalid,
        untrusted_samples=untrusted,
        fraction=round(fraction, 6),
        passes=passes,
        denominator_definition=threshold.denominator,
        detail=detail,
        reason_codes=reasons,
    )


def _channel_coverage(
    qa: QAAnalysis,
    capture: Capture,
    requirement: ScenarioRequirement,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    critical_names = set(capture.chamber_air_slots)
    if requirement.requires_door_event:
        critical_names.update({"door_state", "door_polarity"})
    if requirement.requires_electrical_evidence:
        critical_names.update(
            {"cooling_voltage_v", "cooling_current_a", "cooling_power_w"}
        )
    coverage: list[dict[str, Any]] = []
    quality_counts: dict[str, dict[str, int]] = {}
    for channel in qa.channels:
        entry = {
            "channel": channel.channel,
            "family": channel.family,
            "physical_role": channel.physical_role,
            "required": channel.channel in critical_names,
            "present_count": channel.present_count,
            "missing_count": channel.missing_count,
            "quality_VALID": channel.quality_valid,
            "quality_DEGRADED": channel.quality_degraded,
            "quality_INVALID": channel.quality_invalid,
            "quality_UNKNOWN": channel.quality_unknown,
            "diagnostic_status": channel.diagnostic_status,
            "reason_codes": list(channel.reason_codes),
        }
        coverage.append(entry)
        if channel.channel in critical_names:
            quality_counts[channel.channel] = {
                "VALID": channel.quality_valid,
                "DEGRADED": channel.quality_degraded,
                "INVALID": channel.quality_invalid,
                "UNKNOWN": channel.quality_unknown,
            }
    findings: list[dict[str, Any]] = []
    for domain in ("thermal", "environment", "door", "electrical", "sequence", "provenance"):
        counts = {"VALID": 0, "DEGRADED": 0, "INVALID": 0, "UNKNOWN": 0}
        for row in capture.rows:
            value = _quality(row, domain)
            counts[value if value in counts else "UNKNOWN"] += 1
        findings.append(
            {
                "domain": domain,
                "rows": len(capture.rows),
                **counts,
                "critical_channels": sorted(
                    name for name in critical_names if name in quality_counts
                )
                if domain == "thermal"
                else [],
            }
        )
    return tuple(coverage), tuple(findings)


def _door_anchor(capture: Capture) -> tuple[float | None, int, str]:
    ordered = [row for row in capture.rows if _row_time_s(row) is not None]
    previous: str | None = None
    anchor: float | None = None
    count = 0
    for row in ordered:
        state = row.door_state
        if state in ("OPEN", "CLOSED"):
            if previous in ("OPEN", "CLOSED") and previous != state:
                count += 1
                if anchor is None and state == "OPEN":
                    anchor = _row_time_s(row)
            previous = state
        else:
            previous = "UNKNOWN"
    return anchor, count, "ROW_DERIVED_CLOSED_TO_OPEN_TRANSITION"


def _event_coverage(
    capture: Capture,
    requirement: ScenarioRequirement,
    completeness: Sequence[CompletenessResult],
    rows: Sequence[NormalizedRow],
) -> EventCoverage:
    if not requirement.requires_door_event:
        return EventCoverage(
            required=False,
            anchor_present=False,
            anchor_time_s=None,
            anchor_source="NOT_REQUIRED",
            anchor_count=0,
            baseline_seconds=None,
            event_seconds=None,
            recovery_seconds=None,
            censored=False,
            detail="the declared scenario does not require a disturbance event",
            reason_codes=(REASON_NOT_APPLICABLE,),
        )
    anchor, count, source = _door_anchor(capture)
    if anchor is None:
        return EventCoverage(
            required=True,
            anchor_present=False,
            anchor_time_s=None,
            anchor_source=source,
            anchor_count=count,
            baseline_seconds=None,
            event_seconds=None,
            recovery_seconds=None,
            censored=False,
            detail="no CLOSED→OPEN door transition is observable in the capture",
            reason_codes=(REASON_EVENT_ANCHOR_MISSING,),
        )
    end_s = max((_row_time_s(row) or 0.0) for row in rows) if rows else None
    event = next(
        (
            item
            for item in completeness
            if item.dimension == DIMENSION_EVENT
        ),
        None,
    )
    baseline = next(
        (
            item
            for item in completeness
            if item.dimension == DIMENSION_BASELINE
        ),
        None,
    )
    recovery = next(
        (
            item
            for item in completeness
            if item.dimension == DIMENSION_RECOVERY
        ),
        None,
    )
    censored = (
        end_s is None
        or end_s < anchor + requirement.recovery_horizon_s
    )
    reasons: list[str] = []
    if event is not None and event.status == CHECK_FAIL:
        reasons.append(REASON_EVENT_WINDOW_GAP)
    if baseline is not None and baseline.status == CHECK_FAIL:
        reasons.append(REASON_BASELINE_INCOMPLETE)
    if recovery is not None and recovery.status == CHECK_FAIL:
        reasons.append(REASON_RECOVERY_INCOMPLETE)
    if censored:
        reasons.append(REASON_EVENT_WINDOW_CENSORED)
    return EventCoverage(
        required=True,
        anchor_present=True,
        anchor_time_s=round(anchor, 3),
        anchor_source=source,
        anchor_count=count,
        baseline_seconds=round(anchor, 3),
        event_seconds=(
            None if end_s is None else round(min(end_s, anchor + requirement.event_window_s) - anchor, 3)
        ),
        recovery_seconds=(
            None
            if end_s is None
            else round(min(end_s, anchor + requirement.recovery_horizon_s) - anchor, 3)
        ),
        censored=censored,
        detail=(
            f"first CLOSED→OPEN transition at {anchor:.3f} s; "
            f"{count} transition(s); follow-up "
            f"{'censored' if censored else 'covers the planned horizon'}"
        ),
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def _sequence_checks(capture: Capture) -> tuple[bool, bool, int, int]:
    keys: set[tuple[str | None, str, int]] = set()
    duplicates = 0
    monotonic = True
    previous: int | None = None
    for row in capture.rows:
        key = (row.device_id, row.boot_id, row.seq)
        if key in keys:
            duplicates += 1
        keys.add(key)
        if previous is not None and row.seq <= previous:
            monotonic = False
        previous = row.seq
    return duplicates == 0, monotonic, duplicates, len(keys)


def _manifest_check(
    capture: Capture,
    linkage: RunManifestLinkage | None,
) -> CheckResult:
    if linkage is None:
        return _check(
            "RUN_MANIFEST_LINKED",
            STAGE_IDENTITY,
            None,
            detail=(
                "no run manifest linkage was supplied; an A ledger entry or "
                "file label is not a complete run manifest"
            ),
            reason_codes=(REASON_MANIFEST_MISSING,),
        )
    mismatches: list[str] = []
    if linkage.run_id != capture.run.run_id:
        mismatches.append("run_id")
    if linkage.boot_id != capture.run.boot_id:
        mismatches.append("boot_id")
    if linkage.device_id != capture.run.device_id:
        mismatches.append("device_id")
    if linkage.scenario_id != capture.run.scenario_id:
        mismatches.append("scenario_id")
    if linkage.hardware_config_id != capture.run.hardware_config_id:
        mismatches.append("hardware_config_id")
    if linkage.calibration_id != capture.run.calibration_id:
        mismatches.append("calibration_id")
    if linkage.source_sha256 != capture.source.sha256:
        mismatches.append("source_sha256")
    if linkage.controller_id is not None and linkage.controller_id != capture.run.controller_id:
        mismatches.append("controller_id")
    return _check(
        "RUN_MANIFEST_LINKED",
        STAGE_IDENTITY,
        not mismatches,
        detail=(
            "run manifest linkage matches the capture identity and source hash"
            if not mismatches
            else f"run manifest linkage mismatches: {sorted(mismatches)}"
        ),
        evidence=(
            f"manifest_sha256={linkage.manifest_sha256 or 'NOT_RECORDED'}",
        ),
        reason_codes=(REASON_MANIFEST_MISMATCH,) if mismatches else (),
    )


def validate_run(
    capture: Capture,
    *,
    admission: AdmissionResult | None = None,
    qa: QAAnalysis | None = None,
    requirement: ScenarioRequirement | None = None,
    policy: CompletenessPolicy | None = None,
    manifest_linkage: RunManifestLinkage | None = None,
    timing_audit: TimingAudit | None = None,
    qa_config: QAConfig | None = None,
) -> RunValidation:
    """Evaluate one physical candidate without mutating its evidence."""
    requirement = requirement or default_scenario_requirement(
        capture.run.scenario_id or "UNKNOWN"
    )
    policy = policy or default_completeness_policy()
    admission = admission or evaluate_admission(capture)
    qa = qa or analyze_capture(
        capture,
        admission=admission,
        config=qa_config or QAConfig(),
    )
    if timing_audit is None:
        events = events_from_capture(capture)
        dedup = deduplicate_events(events)
        timing_audit = audit_timeline(dedup.canonical_events)

    checks: list[CheckResult] = []
    session = qa.sessions[0] if qa.sessions else None
    interval = session.interval_stats if session is not None else None
    nominal_dt = interval.nominal_dt_s if interval is not None else None
    rows = capture.rows

    # --- Identity and lineage ------------------------------------------------
    checks.append(
        _check(
            "SOURCE_HASH_PRESENT",
            STAGE_IDENTITY,
            bool(capture.source.sha256),
            detail=f"source SHA-256 {capture.source.sha256 or 'MISSING'}",
            evidence=(capture.source.path,),
        )
    )
    checks.append(
        _check(
            "SCHEMA_NAMESPACE_RECOGNIZED",
            STAGE_IDENTITY,
            bool(capture.source.schema_namespace),
            detail=f"schema namespace {capture.source.schema_namespace!r}",
            evidence=(capture.source.format,),
        )
    )
    physical_provenance = capture.source.provenance == "PHYSICAL"
    checks.append(
        _check(
            "PHYSICAL_PROVENANCE",
            STAGE_IDENTITY,
            physical_provenance,
            detail=(
                f"source provenance {capture.source.provenance!r}; only a "
                "declared physical measurement can enter a physical dataset"
            ),
            reason_codes=() if physical_provenance else ("NON_PHYSICAL_PROVENANCE",),
        )
    )
    run_identity_ok = (
        capture.run.run_id is not None
        and capture.run.run_id_status == "SOURCE_CARRIED_SINGLE"
    )
    checks.append(
        _check(
            "RUN_IDENTITY_CARRIED",
            STAGE_IDENTITY,
            run_identity_ok,
            detail=(
                f"run_id={capture.run.run_id!r} status={capture.run.run_id_status!r}"
            ),
            reason_codes=() if run_identity_ok else ("RUN_IDENTITY_UNRESOLVED",),
        )
    )
    boot_identity_ok = (
        capture.run.boot_id is not None
        and capture.run.boot_id_status == "SOURCE_CARRIED_SINGLE"
    )
    checks.append(
        _check(
            "BOOT_IDENTITY_CARRIED",
            STAGE_IDENTITY,
            boot_identity_ok,
            detail=(
                f"boot_id={capture.run.boot_id!r} "
                f"status={capture.run.boot_id_status!r}"
            ),
            reason_codes=() if boot_identity_ok else ("BOOT_IDENTITY_UNRESOLVED",),
        )
    )
    device_identity_ok = capture.run.device_id is not None
    checks.append(
        _check(
            "DEVICE_IDENTITY_CARRIED",
            STAGE_IDENTITY,
            device_identity_ok,
            detail=(
                f"device_id={capture.run.device_id!r} "
                f"status={capture.run.device_id_status!r}"
            ),
            reason_codes=() if device_identity_ok else ("DEVICE_IDENTITY_MISSING",),
        )
    )
    unique_sequence, monotonic, duplicates, unique_keys = _sequence_checks(capture)
    checks.append(
        _check(
            "SEQUENCE_IDENTITY_UNIQUE",
            STAGE_IDENTITY,
            unique_sequence,
            detail=(
                f"{duplicates} duplicate (device,boot,seq) key(s) across "
                f"{len(rows)} rows"
            ),
            reason_codes=(REASON_SEQUENCE_DUPLICATE,) if not unique_sequence else (),
        )
    )
    checks.append(
        _check(
            "SEQUENCE_MONOTONIC",
            STAGE_IDENTITY,
            monotonic,
            detail=(
                "sequence strictly increases within the boot"
                if monotonic
                else "sequence is not strictly increasing within the boot"
            ),
            reason_codes=(REASON_SEQUENCE_NON_MONOTONIC,) if not monotonic else (),
        )
    )
    checks.append(_manifest_check(capture, manifest_linkage))
    planned_duration = (
        manifest_linkage.planned_capture_duration_s
        if manifest_linkage is not None
        else None
    )
    duration_declared = (
        planned_duration is not None and planned_duration > 0
    )
    checks.append(
        _check(
            "CAPTURE_DURATION_DECLARED",
            STAGE_IDENTITY,
            duration_declared,
            detail=(
                f"planned capture duration {planned_duration!r} s from the run "
                "manifest; the observed partial window is never used as the "
                "expected full-run denominator"
                if duration_declared
                else "no planned capture duration was declared; whole-capture "
                "completeness cannot be estimated from the observed partial "
                "window"
            ),
            reason_codes=(REASON_CAPTURE_DURATION,)
            if not duration_declared
            else (),
        )
    )
    observed_times = [
        time_s for row in rows if (time_s := _row_time_s(row)) is not None
    ]
    planned_start_s = min(observed_times) if observed_times else None
    planned_end_s = (
        planned_start_s + planned_duration
        if planned_start_s is not None and duration_declared
        else None
    )
    interval_covered = (
        planned_end_s is not None
        and observed_times
        and max(observed_times) >= planned_end_s - (nominal_dt or 0.0)
    )
    checks.append(
        _check(
            "PLANNED_INTERVAL_COVERED",
            STAGE_MEASUREMENTS,
            interval_covered if duration_declared else None,
            detail=(
                f"observed capture reaches the planned end {planned_end_s!r} s"
                if interval_covered
                else "the capture ends before the declared planned interval; "
                "missing planned samples cannot be replaced by observed rows "
                "outside the plan"
            ),
            reason_codes=() if interval_covered else (REASON_CAPTURE_SHORTER,),
        )
    )
    checks.append(
        _check(
            "SCENARIO_DESIGNATED",
            STAGE_IDENTITY,
            capture.run.scenario_id is not None,
            detail=f"scenario {capture.run.scenario_id!r}",
        )
    )

    # --- A authority ---------------------------------------------------------
    validity = capture.a_validity
    if validity is None:
        a_verdict = "MISSING"
        a_reasons: tuple[str, ...] = (REASON_AUTHORITY_MISSING,)
        checks.append(
            _check(
                "A_LEDGER_VERDICT",
                STAGE_AUTHORITY,
                None,
                detail="no A validity ledger or run index was supplied",
                reason_codes=(REASON_AUTHORITY_MISSING,),
            )
        )
    elif validity.is_valid is True:
        a_verdict = "VALID"
        a_reasons = ()
        checks.append(
            _check(
                "A_LEDGER_VERDICT",
                STAGE_AUTHORITY,
                True,
                detail=(
                    f"A grants validity for {list(validity.valid_scenarios) or ['no scenario']}"
                ),
                evidence=(validity.source,),
            )
        )
    elif validity.is_valid is False:
        a_verdict = "INVALID"
        a_reasons = (REASON_AUTHORITY_INVALID,) + tuple(validity.reasons)
        checks.append(
            _check(
                "A_LEDGER_VERDICT",
                STAGE_AUTHORITY,
                False,
                detail=(
                    "A's authoritative ledger excludes this run; B never "
                    "overrides it: " + ("; ".join(validity.reasons) or "no reason")
                ),
                evidence=(validity.source,),
                reason_codes=(REASON_AUTHORITY_INVALID,),
            )
        )
    else:
        a_verdict = "UNKNOWN"
        a_reasons = (REASON_AUTHORITY_MISSING,)
        checks.append(
            _check(
                "A_LEDGER_VERDICT",
                STAGE_AUTHORITY,
                None,
                detail=f"A validity status {validity.status!r} is not a verdict",
                evidence=(validity.source,),
                reason_codes=(REASON_AUTHORITY_MISSING,),
            )
        )
    scenario_scope_ok: bool | None = (
        None
        if validity is None or validity.is_valid is None
        else capture.run.scenario_id in validity.valid_scenarios
    )
    checks.append(
        _check(
            "A_SCENARIO_SCOPE_GRANTED",
            STAGE_AUTHORITY,
            scenario_scope_ok,
            detail=(
                f"A validity scope {list(validity.valid_scenarios) if validity else []} "
                f"vs run scenario {capture.run.scenario_id!r}"
            ),
            reason_codes=(
                ("SCENARIO_VALIDITY_NOT_GRANTED",)
                if scenario_scope_ok is False
                else ()
            ),
        )
    )

    # --- Physical configuration ---------------------------------------------
    hardware_ok = (
        bool(capture.run.hardware_config_id)
        and validity is not None
        and validity.hardware_config_verified is True
    )
    checks.append(
        _check(
            "HARDWARE_CONFIG_VERIFIED",
            STAGE_CONFIGURATION,
            hardware_ok,
            detail=(
                f"hardware config {capture.run.hardware_config_id!r} "
                f"status={capture.run.hardware_config_status!r}"
            ),
            reason_codes=() if hardware_ok else ("HARDWARE_CONFIG_NOT_VERIFIED",),
        )
    )
    checks.append(
        _check(
            "FIRMWARE_IDENTITY_CARRIED",
            STAGE_CONFIGURATION,
            bool(capture.run.firmware_version),
            detail=f"firmware {capture.run.firmware_version!r}",
        )
    )
    checks.append(
        _check(
            "CONTROLLER_IDENTITY_CARRIED",
            STAGE_CONFIGURATION,
            bool(capture.run.controller_id),
            severity=(
                SEVERITY_BLOCKING
                if requirement.requires_command_chain
                else SEVERITY_INFO
            ),
            detail=(
                f"controller identity {capture.run.controller_id!r} "
                f"status={capture.run.controller_status!r}; required for paired "
                "A/B comparisons, not for a passive S1 baseline"
            ),
        )
    )
    calibration_ok = (
        bool(capture.run.calibration_id)
        and validity is not None
        and validity.calibration_verified is True
    )
    checks.append(
        _check(
            "CALIBRATION_VERIFIED",
            STAGE_CONFIGURATION,
            calibration_ok,
            detail=(
                f"calibration {capture.run.calibration_id!r} "
                f"status={capture.run.calibration_status!r}"
            ),
            reason_codes=() if calibration_ok else ("CALIBRATION_UNVERIFIED",),
        )
    )
    checks.append(
        _check(
            "PROBE_ROM_IDENTITY_KNOWN",
            STAGE_CONFIGURATION,
            all(role.rom for role in capture.sensors),
            detail=(
                "all probe ROM identities are carried"
                if all(role.rom for role in capture.sensors)
                else "one or more probe ROM identities are missing"
            ),
        )
    )
    roles_ok = not capture.unknown_role_slots
    checks.append(
        _check(
            "PROBE_ROLES_KNOWN",
            STAGE_CONFIGURATION,
            roles_ok,
            detail=(
                "all physical positions and chamber-air roles are known"
                if roles_ok
                else f"unknown/conflicting slots: {list(capture.unknown_role_slots)}"
            ),
            reason_codes=() if roles_ok else ("SENSOR_ROLE_UNKNOWN",),
        )
    )
    checks.append(
        _check(
            "PROBE_ROM_READBACK_VERIFIED",
            STAGE_CONFIGURATION,
            all(role.rom_readback_verified is True for role in capture.sensors),
            severity=SEVERITY_INFO,
            detail=(
                "ROM readback verified for every probe"
                if all(role.rom_readback_verified is True for role in capture.sensors)
                else "ROM readback is not independently verified; positions rely "
                "on the operator-frozen record"
            ),
        )
    )
    unit_required = set(capture.chamber_air_slots)
    if requirement.requires_electrical_evidence:
        unit_required.update(
            {"cooling_voltage_v", "cooling_current_a", "cooling_power_w"}
        )
    unit_missing = [
        name
        for name in sorted(unit_required)
        if name not in {channel.channel: channel for channel in qa.channels}
        or not {channel.channel: channel for channel in qa.channels}[name].unit
    ]
    checks.append(
        _check(
            "INSTRUMENT_UNITS_CONSISTENT",
            STAGE_CONFIGURATION,
            not unit_missing,
            detail=(
                "all required physical channels carry a declared unit"
                if not unit_missing
                else f"required channels without a unit: {unit_missing}"
            ),
        )
    )

    # --- Measurements --------------------------------------------------------
    required_names = set(capture.chamber_air_slots)
    if requirement.requires_door_event:
        required_names.update({"door_state", "door_polarity"})
    if requirement.requires_electrical_evidence:
        required_names.update(
            {"cooling_voltage_v", "cooling_current_a", "cooling_power_w"}
        )
    channels_by_name = {channel.channel: channel for channel in qa.channels}
    missing_required = [
        name
        for name in sorted(required_names)
        if name not in channels_by_name
        or channels_by_name[name].present_count == 0
    ]
    checks.append(
        _check(
            "REQUIRED_CHANNEL_PRESENT",
            STAGE_MEASUREMENTS,
            not missing_required,
            detail=(
                f"required channels present: {sorted(required_names)}"
                if not missing_required
                else f"missing required channels: {missing_required}"
            ),
            reason_codes=(REASON_CRITICAL_MISSING,) if missing_required else (),
        )
    )
    critical_invalid = []
    for name in sorted(required_names):
        channel = channels_by_name.get(name)
        if channel is None:
            continue
        valid = channel.quality_valid
        if valid < channel.row_count:
            critical_invalid.append(name)
    checks.append(
        _check(
            "CRITICAL_CHANNELS_QUALIFIED",
            STAGE_MEASUREMENTS,
            not critical_invalid,
            detail=(
                "all required channels are source-quality VALID for every row"
                if not critical_invalid
                else f"required channels with non-VALID rows: {critical_invalid}"
            ),
            reason_codes=(REASON_CRITICAL_CHANNEL,) if critical_invalid else (),
        )
    )
    checks.append(
        _check(
            "TIME_DOMAIN_DECLARED",
            STAGE_MEASUREMENTS,
            capture.time.domain != "NONE",
            detail=(
                f"time domain {capture.time.domain!r}; event time "
                f"{capture.time.event_time_status!r}; clock sync "
                f"{capture.time.clock_sync!r}"
            ),
        )
    )
    absolute_time_ok: bool | None
    if not requirement.require_absolute_time:
        absolute_time_ok = None
    else:
        absolute_time_ok = (
            capture.time.domain == "EVENT_UTC"
            and capture.time.event_time_status == "AVAILABLE"
            and (
                capture.time.clock_sync == "EVIDENCED"
                or (validity is not None and validity.clock_sync_verified is True)
            )
        )
    checks.append(
        _check(
            "ABSOLUTE_TIME_FOR_CLAIM",
            STAGE_MEASUREMENTS,
            absolute_time_ok,
            detail=(
                "event-time UTC and clock synchronization are evidenced"
                if absolute_time_ok
                else "absolute-time claims require event-time UTC and evidenced "
                "clock synchronization; boot-relative data is diagnostic only"
            ),
            reason_codes=(REASON_TIME_ABSOLUTE,) if absolute_time_ok is False else (),
        )
    )
    timing_ok = (
        timing_audit is None
        or not timing_audit.reason_codes
        or all(
            code
            in (
                "MISSING_CAPTURE_TIME",
                "MISSING_RECEIVE_TIME",
            )
            for code in timing_audit.reason_codes
        )
    )
    checks.append(
        _check(
            "TIMING_INTEGRITY",
            STAGE_MEASUREMENTS,
            timing_ok,
            detail=(
                "sequence/timestamp audit has no reversals, resets or impossible "
                "intervals"
                if timing_ok
                else f"timing audit reason codes: {list(timing_audit.reason_codes) if timing_audit else []}"
            ),
            reason_codes=() if timing_ok else ("TIMING_INTEGRITY_FAILED",),
        )
    )
    pzem_channel = channels_by_name.get("cooling_power_w")
    pzem_ok = (
        pzem_channel is not None
        and pzem_channel.quality_valid == pzem_channel.row_count
    )
    checks.append(
        _check(
            "PZEM_QUALIFIED_IF_CLAIMED",
            STAGE_MEASUREMENTS,
            pzem_ok if requirement.requires_electrical_evidence else None,
            severity=(
                SEVERITY_BLOCKING
                if requirement.requires_electrical_evidence
                else SEVERITY_INFO
            ),
            detail=(
                "PZEM power is source-quality VALID"
                if pzem_ok
                else "PZEM power/current/voltage are unqualified or the "
                "declared analysis does not require electrical evidence; "
                "numeric values are diagnostic only and missing values are "
                "never zero"
            ),
            reason_codes=(REASON_PZEM_UNQUALIFIED,)
            if requirement.requires_electrical_evidence and not pzem_ok
            else (),
        )
    )
    door_channel = channels_by_name.get("door_state")
    door_ok = door_channel is not None and door_channel.quality_valid > 0
    checks.append(
        _check(
            "DOOR_QUALIFIED_IF_REQUIRED",
            STAGE_MEASUREMENTS,
            door_ok if requirement.requires_door_event else None,
            severity=(
                SEVERITY_BLOCKING
                if requirement.requires_door_event
                else SEVERITY_INFO
            ),
            detail=(
                "door state is qualified for the disturbance claim"
                if door_ok
                else "door state/polarity are unqualified; no disturbance claim "
                "is admissible"
            ),
            reason_codes=(REASON_DOOR_UNQUALIFIED,)
            if requirement.requires_door_event and not door_ok
            else (),
        )
    )

    # --- Completeness --------------------------------------------------------
    completeness: list[CompletenessResult] = []
    expected_whole = (
        _expected_samples(planned_duration, nominal_dt, inclusive=True)
        if duration_declared and nominal_dt
        else None
    )
    rows_in_plan = (
        [
            row
            for row in rows
            if (time_s := _row_time_s(row)) is not None
            and planned_start_s <= time_s <= planned_end_s
        ]
        if planned_start_s is not None and planned_end_s is not None
        else []
    )
    received_whole = len(rows_in_plan) if expected_whole is not None else None
    diagnostic_whole = interval.captured_frame_completeness if interval else None
    whole_missing = (
        max((expected_whole or 0) - (received_whole or 0), 0)
        if expected_whole is not None and received_whole is not None
        else None
    )
    completeness.append(
        _completeness_result(
            dimension=DIMENSION_WHOLE,
            policy=policy,
            expected=expected_whole,
            observed=received_whole,
            missing=whole_missing,
            invalid=None,
            untrusted=None,
            detail=(
                f"expected samples from the declared planned duration "
                f"{planned_duration!r} s and observed nominal cadence "
                f"{nominal_dt!r} from {interval.nominal_source!r}; "
                f"{len(rows) - len(rows_in_plan)} observed row(s) outside the "
                f"planned interval are excluded; the W05 observed-window "
                f"fraction {diagnostic_whole!r} "
                f"({interval.completeness_status!r}) is diagnostic only"
                if expected_whole is not None and interval is not None
                else "no declared planned capture duration; the observed "
                "partial window is not a full-run denominator"
            ),
        )
    )
    critical_expected = expected_whole
    critical_observed = 0
    critical_missing = 0
    critical_invalid_rows = 0
    for row in rows_in_plan:
        ok, missing, invalid = _critical_row_ok(row, capture, requirement)
        if ok:
            critical_observed += 1
        if missing:
            critical_missing += 1
        if invalid:
            critical_invalid_rows += 1
    completeness.append(
        _completeness_result(
            dimension=DIMENSION_CRITICAL,
            policy=policy,
            expected=critical_expected,
            observed=critical_observed,
            missing=critical_missing,
            invalid=critical_invalid_rows,
            untrusted=None,
            detail=(
                "critical channels are thermal chamber-air slots"
                + (" + door" if requirement.requires_door_event else "")
                + (" + PZEM" if requirement.requires_electrical_evidence else "")
            ),
        )
    )
    if requirement.requires_door_event:
        anchor, _count, _source = _door_anchor(capture)
        end_s = max((_row_time_s(row) or 0.0) for row in rows) if rows else None
        baseline_expected = _expected_samples(
            requirement.baseline_window_s, nominal_dt, inclusive=False
        )
        baseline_rows = (
            _window_rows(
                rows,
                anchor - requirement.baseline_window_s,
                anchor,
            )
            if anchor is not None
            else []
        )
        baseline_observed = sum(
            1
            for row in baseline_rows
            if _critical_row_ok(row, capture, requirement)[0]
        )
        baseline_missing = sum(
            1
            for row in baseline_rows
            if _critical_row_ok(row, capture, requirement)[1]
        )
        baseline_invalid = sum(
            1
            for row in baseline_rows
            if _critical_row_ok(row, capture, requirement)[2]
        )
        completeness.append(
            _completeness_result(
                dimension=DIMENSION_BASELINE,
                policy=policy,
                expected=baseline_expected if anchor is not None else None,
                observed=baseline_observed if anchor is not None else None,
                missing=baseline_missing if anchor is not None else None,
                invalid=baseline_invalid if anchor is not None else None,
                untrusted=None,
                detail=(
                    f"pre-event window [{requirement.baseline_window_s} s before "
                    "the first CLOSED→OPEN transition]"
                    if anchor is not None
                    else "no event anchor; the baseline window is undefined"
                ),
                applicable=True,
            )
        )
        event_expected = _expected_samples(
            requirement.event_window_s, nominal_dt, inclusive=False
        )
        event_rows = (
            _window_rows(rows, anchor, anchor + requirement.event_window_s)
            if anchor is not None
            else []
        )
        event_observed = sum(
            1 for row in event_rows if _critical_row_ok(row, capture, requirement)[0]
        )
        event_missing = sum(
            1 for row in event_rows if _critical_row_ok(row, capture, requirement)[1]
        )
        event_invalid = sum(
            1 for row in event_rows if _critical_row_ok(row, capture, requirement)[2]
        )
        completeness.append(
            _completeness_result(
                dimension=DIMENSION_EVENT,
                policy=policy,
                expected=event_expected if anchor is not None else None,
                observed=event_observed if anchor is not None else None,
                missing=event_missing if anchor is not None else None,
                invalid=event_invalid if anchor is not None else None,
                untrusted=None,
                detail=(
                    f"primary event window [anchor, anchor+{requirement.event_window_s} s]"
                    if anchor is not None
                    else "no event anchor; the primary event window is undefined"
                ),
                applicable=True,
            )
        )
        recovery_start = anchor + requirement.event_window_s if anchor is not None else None
        recovery_end = anchor + requirement.recovery_horizon_s if anchor is not None else None
        recovery_expected = _expected_samples(
            max(requirement.recovery_horizon_s - requirement.event_window_s, 0.0),
            nominal_dt,
            inclusive=False,
        )
        recovery_rows = (
            _window_rows(rows, recovery_start, recovery_end)
            if recovery_start is not None and recovery_end is not None
            else []
        )
        recovery_observed = sum(
            1
            for row in recovery_rows
            if _critical_row_ok(row, capture, requirement)[0]
        )
        recovery_missing = sum(
            1
            for row in recovery_rows
            if _critical_row_ok(row, capture, requirement)[1]
        )
        recovery_invalid = sum(
            1
            for row in recovery_rows
            if _critical_row_ok(row, capture, requirement)[2]
        )
        censored = (
            end_s is None
            or recovery_end is None
            or end_s < recovery_end
        )
        completeness.append(
            _completeness_result(
                dimension=DIMENSION_RECOVERY,
                policy=policy,
                expected=recovery_expected if anchor is not None else None,
                observed=recovery_observed if anchor is not None else None,
                missing=recovery_missing if anchor is not None else None,
                invalid=recovery_invalid if anchor is not None else None,
                untrusted=None,
                detail=(
                    (
                        f"follow-up window [anchor+{requirement.event_window_s} s, "
                        f"anchor+{requirement.recovery_horizon_s} s]; capture is "
                        f"{'censored' if censored else 'complete'}"
                    )
                    if anchor is not None
                    else "no event anchor; the follow-up window is undefined"
                ),
                applicable=True,
            )
        )
    else:
        for dimension in (DIMENSION_BASELINE, DIMENSION_EVENT, DIMENSION_RECOVERY):
            completeness.append(
                _completeness_result(
                    dimension=dimension,
                    policy=policy,
                    expected=None,
                    observed=None,
                    missing=None,
                    invalid=None,
                    untrusted=None,
                    detail="the declared scenario has no required disturbance event",
                    applicable=False,
                )
            )
    interval_count = interval.interval_count if interval else None
    long_gap_count = interval.long_gap_count if interval else None
    timing_observed = (
        max((interval_count or 0) - (long_gap_count or 0), 0)
        if interval_count is not None
        else None
    )
    completeness.append(
        _completeness_result(
            dimension=DIMENSION_TIMING,
            policy=policy,
            expected=interval_count,
            observed=timing_observed,
            missing=long_gap_count,
            invalid=(interval.negative_interval_count if interval else None),
            untrusted=None,
            detail=(
                "observed cadence is not assumed to be exactly 1 Hz; no cadence "
                "tolerance has been frozen, so this fraction is not evaluable"
            ),
        )
    )
    for item in completeness:
        if item.status == CHECK_FAIL and item.reason_codes:
            checks.append(
                CheckResult(
                    code=f"COMPLETENESS_{item.dimension}",
                    stage=STAGE_MEASUREMENTS,
                    status=CHECK_FAIL,
                    severity=SEVERITY_BLOCKING,
                    detail=item.detail,
                    evidence=(item.dimension,),
                    reason_codes=item.reason_codes,
                )
            )

    # --- Protocol and events -------------------------------------------------
    scenario_ok = (
        capture.run.scenario_id is not None
        and capture.run.scenario_id.upper() == requirement.scenario_id
    )
    checks.append(
        _check(
            "PLANNED_VERSUS_OBSERVED_SCENARIO",
            STAGE_PROTOCOL,
            scenario_ok,
            detail=(
                f"declared dataset scenario {requirement.scenario_id!r} vs "
                f"source scenario {capture.run.scenario_id!r}"
            ),
        )
    )
    event_coverage = _event_coverage(capture, requirement, completeness, rows)
    if requirement.requires_door_event:
        checks.append(
            _check(
                "EVENT_ANCHOR_PRESENT",
                STAGE_PROTOCOL,
                event_coverage.anchor_present,
                detail=event_coverage.detail,
                reason_codes=(
                    REASON_EVENT_ANCHOR_MISSING,
                ) if not event_coverage.anchor_present else (),
            )
        )
        checks.append(
            _check(
                "EVENT_WINDOW_COVERAGE",
                STAGE_PROTOCOL,
                next(
                    (
                        item.passes
                        for item in completeness
                        if item.dimension == DIMENSION_EVENT
                    ),
                    None,
                ),
                detail=event_coverage.detail,
                reason_codes=event_coverage.reason_codes,
            )
        )
        checks.append(
            _check(
                "RECOVERY_FOLLOWUP_COVERAGE",
                STAGE_PROTOCOL,
                (
                    None
                    if event_coverage.censored
                    else next(
                        (
                            item.passes
                            for item in completeness
                            if item.dimension == DIMENSION_RECOVERY
                        ),
                        None,
                    )
                ),
                detail=event_coverage.detail,
                reason_codes=(
                    (REASON_EVENT_WINDOW_CENSORED,)
                    if event_coverage.censored
                    else ()
                ),
            )
        )
    command_ok: bool | None
    if not requirement.requires_command_chain:
        command_ok = None
    else:
        command_ok = any(
            event.event_type
            in (
                "COMMAND_CREATED_OR_PUBLISHED",
                "DEVICE_ACK",
                "APPLIED_STATE",
            )
            for event in deduplicate_events(events_from_capture(capture)).canonical_events
        )
    checks.append(
        _check(
            "COMMAND_CHAIN_COMPLETE_IF_REQUIRED",
            STAGE_PROTOCOL,
            command_ok,
            severity=(
                SEVERITY_BLOCKING
                if requirement.requires_command_chain
                else SEVERITY_INFO
            ),
            detail=(
                "the declared analysis does not require a command/ACK chain"
                if not requirement.requires_command_chain
                else "command/ACK/applied chain evidence is required and must be present"
            ),
            reason_codes=(REASON_COMMAND_CHAIN,)
            if requirement.requires_command_chain and not command_ok
            else (),
        )
    )
    intervention_codes = sorted(
        {
            code
            for row in rows
            for code in row.invalidation_reasons
        }
    )
    checks.append(
        _check(
            "INTERVENTION_AND_CENSORING_RECORDED",
            STAGE_PROTOCOL,
            bool(capture.rows),
            severity=SEVERITY_WARNING,
            detail=(
                f"row invalidation/censoring codes: {intervention_codes or 'none recorded'}; "
                "the recovery criterion remains unresolved"
            ),
            reason_codes=(REASON_INTERVENTION,) if intervention_codes else (),
        )
    )

    # --- Eligibility ---------------------------------------------------------
    blocking = [
        check
        for check in checks
        if check.severity == SEVERITY_BLOCKING
        and check.status in (CHECK_FAIL, CHECK_NOT_EVALUABLE)
    ]
    a_failed = a_verdict in ("INVALID", "UNKNOWN", "MISSING")
    if a_verdict == "INVALID" or any(
        check.code == "A_LEDGER_VERDICT" and check.status == CHECK_FAIL
        for check in checks
    ):
        eligibility = ELIGIBILITY_BLOCKED
        reason_codes = [REASON_AUTHORITY_INVALID]
    elif blocking:
        eligibility = ELIGIBILITY_BLOCKED
        reason_codes = sorted(
            {
                code
                for check in blocking
                for code in (check.reason_codes or (check.code,))
            }
        )
    elif admission.status is not AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET:
        eligibility = ELIGIBILITY_DIAGNOSTIC
        reason_codes = [REASON_DIAGNOSTIC_ONLY]
    else:
        eligibility = ELIGIBILITY_ELIGIBLE
        reason_codes = [REASON_PASS]
    if a_failed and not reason_codes:
        reason_codes = [REASON_AUTHORITY_MISSING]
    channel_coverage, quality_findings = _channel_coverage(qa, capture, requirement)
    unique_reasons = tuple(
        sorted(
            set(
                reason_codes
                + [
                    code
                    for check in checks
                    if check.status in (CHECK_FAIL, CHECK_NOT_EVALUABLE)
                    and check.severity != SEVERITY_INFO
                    for code in (check.reason_codes or (check.code,))
                ]
            )
        )
    )
    return RunValidation(
        source_path=capture.source.path,
        source_sha256=capture.source.sha256,
        physical_source_key=_capture_source_key(capture),
        run_id=capture.run.run_id,
        run_id_status=capture.run.run_id_status,
        device_id=capture.run.device_id,
        boot_id=capture.run.boot_id,
        scenario_id=capture.run.scenario_id,
        scenario_status=capture.run.scenario_status,
        hardware_config_id=capture.run.hardware_config_id,
        hardware_config_status=capture.run.hardware_config_status,
        calibration_id=capture.run.calibration_id,
        calibration_status=capture.run.calibration_status,
        firmware_version=capture.run.firmware_version,
        controller_id=capture.run.controller_id,
        pair_id=manifest_linkage.pair_id if manifest_linkage else None,
        time_domain=capture.time.domain,
        clock_sync_status=capture.time.clock_sync,
        a_ledger_verdict=a_verdict,
        a_ledger_reasons=tuple(a_reasons),
        admission_status=admission.status.value,
        admission_highest_stage=admission.highest_stage.value,
        eligibility=eligibility,
        checks=tuple(checks),
        completeness=tuple(completeness),
        event_coverage=event_coverage,
        channel_coverage=channel_coverage,
        quality_findings=quality_findings,
        reason_codes=unique_reasons,
    )


def _capture_source_key(capture: Capture) -> tuple[Any, ...]:
    from .intake import physical_source_key

    return physical_source_key(capture)


# ---------------------------------------------------------------------------
# Gate aggregation
# ---------------------------------------------------------------------------


def _gate(
    gate: str,
    requirement: ScenarioRequirement,
    *,
    observed_status: str,
    severity: str,
    required_checks: Sequence[str],
    reason_codes: Sequence[str],
    validations: Sequence[RunValidation],
    next_evidence_required: str,
    allowed_uses: Sequence[str] = (),
    prohibited_uses: Sequence[str] = (),
) -> GateDecision:
    return GateDecision(
        gate=gate,
        declared_dataset_purpose=requirement.dataset_purpose,
        scenario=requirement.scenario_id,
        population=(
            f"{len(validations)} candidate run(s); "
            f"{sum(1 for item in validations if item.eligibility == ELIGIBILITY_ELIGIBLE)} eligible"
        ),
        required_checks=tuple(required_checks),
        observed_status=observed_status,
        severity=severity,
        evidence_paths=tuple(sorted({item.source_path for item in validations})),
        evidence_sha256=tuple(
            sorted({item.source_sha256 for item in validations})
        ),
        reason_codes=tuple(sorted(set(reason_codes))),
        owner="Member B — AI & Experimental Data",
        next_evidence_required=next_evidence_required,
        allowed_uses=tuple(allowed_uses),
        prohibited_uses=tuple(prohibited_uses),
    )


def assess_gate_b(
    validations: Sequence[RunValidation],
    admissions: Sequence[AdmissionResult],
    requirement: ScenarioRequirement,
    *,
    min_independent_runs: int = 3,
    w07_evidence: dict[str, Any] | None = None,
) -> tuple[GateDecision, GateDecision, GateDecision]:
    """Aggregate the separately reported W08, Gate B and predictive gates."""
    scenario_runs = [
        item
        for item in validations
        if (item.scenario_id or "").upper().startswith(requirement.scenario_id)
    ]
    eligible = [
        item for item in scenario_runs if item.eligibility == ELIGIBILITY_ELIGIBLE
    ]
    independent = {
        tuple(item.physical_source_key) for item in eligible
    }
    suite = summarize_readiness(admissions) if admissions else None
    conflicts = []
    if suite is not None:
        conflicts = [
            exclusion
            for exclusion in suite.exclusions
            if any(
                blocker.get("code") == REASON_DUPLICATE_CONFLICT
                for blocker in exclusion.get("blockers", [])
            )
        ]

    software_reasons = [REASON_SOFTWARE_COMPLETE]
    software_gate = _gate(
        GATE_SOFTWARE,
        requirement,
        observed_status=VERDICT_GREEN,
        severity=SEVERITY_INFO,
        required_checks=(
            "RUN_VALIDATION_COMPLETED",
            "CHECKS_EVALUATED",
            "DETERMINISTIC_SERIALIZATION",
        ),
        reason_codes=software_reasons,
        validations=scenario_runs,
        next_evidence_required="none; software verification is independent of the data verdict",
    )

    reasons: list[str] = []
    if not scenario_runs:
        reasons.append(REASON_POPULATION)
    if scenario_runs and not eligible:
        reasons.append(REASON_POPULATION)
    if len(independent) < min_independent_runs:
        reasons.append(REASON_INDEPENDENT_POPULATION)
    if conflicts:
        reasons.append(REASON_DUPLICATE_CONFLICT)
    required_failed = [
        item
        for item in eligible
        if item.blocking_failures
    ]
    if required_failed:
        reasons.append("ELIGIBLE_RUN_HAS_BLOCKING_FAILURE")
    for item in scenario_runs:
        for check in item.blocking_failures:
            reasons.extend(check.reason_codes or (check.code,))
    # A RED hard prerequisite cannot be hidden by GREEN supporting checks.
    a_invalid = any(item.a_ledger_verdict == "INVALID" for item in scenario_runs)
    if a_invalid:
        reasons.append(REASON_AUTHORITY_INVALID)
    missing_event = any(
        item.event_coverage.required and not item.event_coverage.anchor_present
        for item in scenario_runs
    )
    if requirement.requires_door_event and missing_event:
        reasons.append(REASON_EVENT_ANCHOR_MISSING)
    if reasons:
        physical_status = VERDICT_RED
        severity = SEVERITY_BLOCKING
        allowed: tuple[str, ...] = (
            "diagnostic QA of structurally valid captures",
        )
        prohibited = (
            "predictive model training or benchmark claims",
            "locked test or Gate C evidence",
            "any claim that physical repeatability is established",
        )
        next_evidence = (
            "A-valid, independently identified runs with verified hardware, "
            "calibration and clock evidence; required event coverage; run "
            "manifest linkage; and at least "
            f"{min_independent_runs} independent run(s) for the declared scenario"
        )
    else:
        warnings = [
            warning
            for item in eligible
            for warning in item.warnings
        ]
        unresolved_thresholds = [
            item
            for item in eligible
            for result in item.completeness
            if result.threshold_status == THRESHOLD_UNRESOLVED
            and default_completeness_policy()
            .threshold(result.dimension)
            .blocking_severity
            != SEVERITY_INFO
        ]
        w07_not_established = (
            w07_evidence is not None
            and w07_evidence.get("verdict") == "NOT_ESTABLISHED"
        )
        if warnings or unresolved_thresholds or w07_not_established:
            physical_status = VERDICT_YELLOW
            severity = SEVERITY_WARNING
            allowed = (
                f"limited use for {requirement.dataset_purpose} after the named "
                "provisional conditions are recorded",
            )
            prohibited = (
                "serious XGBoost campaign or predictive benchmark claims",
                "locked-test claims or Gate C evidence",
            )
            next_evidence = (
                "resolve the named provisional completeness/timing conditions "
                "and review them with the project owner"
            )
            if w07_not_established:
                reasons.append(REASON_W07_NOT_ESTABLISHED)
        else:
            physical_status = VERDICT_GREEN
            severity = SEVERITY_INFO
            allowed = (requirement.dataset_purpose,)
            prohibited = ("locked test outcomes before the W12 freeze",)
            next_evidence = "none for the declared purpose; preserve provenance"
    if physical_status == VERDICT_GREEN and not eligible:
        physical_status = VERDICT_RED
        severity = SEVERITY_BLOCKING
        reasons.append(REASON_POPULATION)
    physical_gate = _gate(
        GATE_B_PHYSICAL,
        requirement,
        observed_status=physical_status,
        severity=severity,
        required_checks=(
            "A_LEDGER_VALID",
            "PHYSICAL_RUN_IDENTITY",
            "HARDWARE_AND_CALIBRATION_VERIFIED",
            "REQUIRED_CHANNELS_QUALIFIED",
            "EVENT_COMPLETENESS_FOR_DECLARED_SCENARIO",
            "RUN_MANIFEST_LINKAGE",
            "INDEPENDENT_RUN_POPULATION",
            "NO_DUPLICATE_VIEW_CONFLICT",
        ),
        reason_codes=reasons or [REASON_PASS],
        validations=scenario_runs,
        next_evidence_required=next_evidence,
        allowed_uses=allowed,
        prohibited_uses=prohibited,
    )

    predictive_status = (
        VERDICT_READY
        if physical_status == VERDICT_GREEN
        else VERDICT_NOT_READY
    )
    predictive_reasons = (
        [REASON_PASS]
        if predictive_status == VERDICT_READY
        else [
            "GATE_B_NOT_GREEN",
            *reasons,
        ]
    )
    predictive_gate = _gate(
        GATE_PREDICTIVE,
        requirement,
        observed_status=predictive_status,
        severity=SEVERITY_INFO
        if predictive_status == VERDICT_READY
        else SEVERITY_BLOCKING,
        required_checks=("GATE_B_PHYSICAL_DATA_GREEN",),
        reason_codes=predictive_reasons,
        validations=scenario_runs,
        next_evidence_required=(
            "none"
            if predictive_status == VERDICT_READY
            else "a GREEN Gate B physical-data decision for the declared population"
        ),
        allowed_uses=("dataset readiness reporting",),
        prohibited_uses=("model training while NOT_READY",),
    )
    return software_gate, physical_gate, predictive_gate


def build_gate_b_report(
    validations: Sequence[RunValidation],
    admissions: Sequence[AdmissionResult],
    requirement: ScenarioRequirement,
    *,
    policy: CompletenessPolicy | None = None,
    split_plan: SplitPlan | None = None,
    min_independent_runs: int = 3,
    w07_evidence: dict[str, Any] | None = None,
    limitations: Sequence[str] = (),
) -> GateBReport:
    """Assemble the four separately reported gates and the split plan."""
    policy = policy or default_completeness_policy()
    software_gate, physical_gate, predictive_gate = assess_gate_b(
        validations,
        admissions,
        requirement,
        min_independent_runs=min_independent_runs,
        w07_evidence=w07_evidence,
    )
    if split_plan is None:
        split_plan = plan_development_split(
            _split_candidates_from_validations(validations)
        )
    if split_plan.feasibility == SPLIT_FEASIBLE:
        split_status = VERDICT_GREEN
        split_severity = SEVERITY_INFO
        split_reasons = (REASON_SPLIT_PLANNING,)
    elif split_plan.feasibility == SPLIT_PROVISIONAL:
        split_status = VERDICT_YELLOW
        split_severity = SEVERITY_WARNING
        split_reasons = (REASON_SPLIT_PLANNING,)
    else:
        split_status = VERDICT_RED
        split_severity = SEVERITY_BLOCKING
        split_reasons = (REASON_SPLIT_INFEASIBLE,)
    split_gate = _gate(
        GATE_SPLIT,
        requirement,
        observed_status=split_status,
        severity=split_severity,
        required_checks=(
            "INDEPENDENT_RUN_GROUPS",
            "PAIR_LINEAGE_PRESERVED",
            "NO_REPEATED_VIEW_GROUPS",
            "P1_P2_P3_DISJOINT",
            "P3_NOT_FROZEN",
        ),
        reason_codes=split_reasons,
        validations=validations,
        next_evidence_required=(
            "none for planning; a future frozen split requires enough real "
            "independent runs and the project-freeze authorization"
            if split_plan.feasibility != SPLIT_NOT_FEASIBLE
            else "enough independently valid physical runs to populate three "
            "non-empty grouped partitions"
        ),
        allowed_uses=(
            ("planning candidate only",)
            if split_plan.feasibility != SPLIT_NOT_FEASIBLE
            else ()
        ),
        prohibited_uses=(
            "frozen locked-test IDs",
            "model selection against test outcomes",
        ),
    )
    suite = {
        "analyzed_sources": len(validations),
        "unique_physical_sources": len(
            {tuple(item.physical_source_key) for item in validations}
        ),
        "eligible_runs": len(
            [
                item
                for item in validations
                if item.eligibility == ELIGIBILITY_ELIGIBLE
            ]
        ),
        "duplicate_views": max(len(validations) - len({tuple(item.physical_source_key) for item in validations}), 0),
        "predictive_dataset_readiness": predictive_gate.observed_status,
    }
    separation = {
        "STRUCTURAL_VALIDITY": (
            "PASS"
            if all(
                item.admission_highest_stage
                in (
                    AdmissionStage.STRUCTURALLY_VALID.value,
                    AdmissionStage.USABLE_FOR_DIAGNOSTIC_QA.value,
                    AdmissionStage.PHYSICALLY_QUALIFIED.value,
                    AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET.value,
                )
                for item in validations
            )
            else "BLOCKED"
        ),
        "DIAGNOSTIC_USABILITY": (
            "PASS"
            if any(
                item.admission_highest_stage
                in (
                    AdmissionStage.USABLE_FOR_DIAGNOSTIC_QA.value,
                    AdmissionStage.PHYSICALLY_QUALIFIED.value,
                    AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET.value,
                )
                for item in validations
            )
            else "NOT_AVAILABLE"
        ),
        "PHYSICAL_RUN_VALIDITY": physical_gate.observed_status,
        "SCENARIO_ELIGIBILITY": (
            "ELIGIBLE"
            if any(
                item.eligibility == ELIGIBILITY_ELIGIBLE for item in validations
            )
            else "INELIGIBLE"
        ),
        "DATASET_READINESS": predictive_gate.observed_status,
        "SPLIT_FEASIBILITY": split_plan.feasibility,
    }
    default_limitations = [
        "A scientific RED is a successful software result, not a CLI failure.",
        "No locked test manifest is created, inspected or frozen by W08.",
        "Synthetic controls never enter the physical dataset or the real split.",
        "A GREEN W08 software gate does not make the physical data GREEN.",
    ]
    return GateBReport(
        scenario_requirement=requirement,
        policy=policy,
        validations=tuple(validations),
        suite=suite,
        software_gate=software_gate,
        physical_gate=physical_gate,
        predictive_gate=predictive_gate,
        split_gate=split_gate,
        split_plan=split_plan,
        separation=separation,
        w07_evidence=w07_evidence,
        limitations=tuple(default_limitations) + tuple(limitations),
    )


def _split_candidates_from_validations(
    validations: Sequence[RunValidation],
) -> tuple[SplitCandidate, ...]:
    candidates: list[SplitCandidate] = []
    for item in validations:
        candidates.append(
            SplitCandidate(
                run_id=item.run_id or "UNRESOLVED_RUN_ID",
                scenario_id=item.scenario_id or "UNKNOWN_SCENARIO",
                controller_id=item.controller_id or "OBSERVATIONAL",
                physical_source_key=tuple(item.physical_source_key),
                pair_id=item.pair_id,
                hardware_config_id=item.hardware_config_id,
                eligible=item.eligibility == ELIGIBILITY_ELIGIBLE,
                reason=(
                    "ELIGIBLE"
                    if item.eligibility == ELIGIBILITY_ELIGIBLE
                    else ";".join(item.reason_codes)
                ),
                source_path=item.source_path,
                source_sha256=item.source_sha256,
            )
        )
    return tuple(candidates)


# ---------------------------------------------------------------------------
# Grouped split planning (B-W08-04)
# ---------------------------------------------------------------------------


def _dedupe_candidates(
    candidates: Sequence[SplitCandidate],
) -> tuple[list[SplitCandidate], list[dict[str, Any]]]:
    """One group per physical source; contradictory run identities fail closed."""
    grouped: dict[tuple[Any, ...], list[SplitCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(tuple(candidate.physical_source_key), []).append(
            candidate
        )
    accepted: list[SplitCandidate] = []
    excluded: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items(), key=lambda item: str(item[0])):
        items = sorted(items, key=lambda item: (item.source_path, item.source_sha256))
        run_ids = sorted({item.run_id for item in items})
        if len(run_ids) > 1:
            excluded.extend(
                {
                    "source_path": item.source_path,
                    "source_sha256": item.source_sha256,
                    "run_id": item.run_id,
                    "reason": (
                        "CONTRADICTORY_RUN_IDENTITIES_ON_ONE_PHYSICAL_SOURCE; "
                        "one boot session cannot be split into independent "
                        "groups without reset/certification evidence"
                    ),
                }
                for item in items
            )
            continue
        representative = items[0]
        if len(items) > 1:
            excluded.extend(
                {
                    "source_path": item.source_path,
                    "source_sha256": item.source_sha256,
                    "run_id": item.run_id,
                    "reason": (
                        "REPEATED_VIEW_OF_ONE_PHYSICAL_SOURCE; one run group "
                        "only, never an extra independent group"
                    ),
                }
                for item in items[1:]
            )
        accepted.append(representative)
    return accepted, excluded


def plan_development_split(
    candidates: Sequence[SplitCandidate],
    *,
    seed: int = 0,
    min_groups_per_partition: int = 1,
    planning_shape_runs: int = 24,
    synthetic_control: bool = False,
) -> SplitPlan:
    """Plan a grouped split; never freezes P3 and never emits real IDs when infeasible."""
    accepted, excluded = _dedupe_candidates(candidates)
    eligible = [item for item in accepted if item.eligible]
    if not eligible:
        return SplitPlan(
            feasibility=SPLIT_NOT_FEASIBLE,
            planning_shape=(
                "Doc 03 §48 illustrative shape ~16 development / 4 validation "
                "/ 4 test for ~24 runs; not executable with the current population"
            ),
            candidate_count=len(candidates),
            eligible_count=0,
            p1_training=(),
            p2_held_back_development_validation=(),
            p3_future_locked_planning_candidates=(),
            development_runs=(),
            excluded=tuple(excluded),
            pair_lineage=(),
            grouping_key="run_id; pair_id groups both arms",
            split_seed=None,
            p3_status=P3_NOT_FROZEN,
            reasons=(REASON_SPLIT_INFEASIBLE, REASON_POPULATION),
            minimum_evidence=(
                "at least one A-valid, physically qualified run with a resolved "
                "run identity, verified hardware/calibration and complete event "
                "coverage for the declared scenario",
            ),
            synthetic_control=synthetic_control,
        )
    infos = [
        RunInfo(
            run_id=item.run_id,
            scenario_id=item.scenario_id,
            controller_id=item.controller_id,
            pair_id=item.pair_id,
            hardware_config_id=item.hardware_config_id,
            is_valid=True,
        )
        for item in eligible
    ]
    n_groups = len({item.pair_id or item.run_id for item in eligible})
    if n_groups < min_groups_per_partition * 3:
        return SplitPlan(
            feasibility=SPLIT_NOT_FEASIBLE,
            planning_shape="three partitions P1/P2/P3; grouped by run/pair",
            candidate_count=len(candidates),
            eligible_count=len(eligible),
            p1_training=(),
            p2_held_back_development_validation=(),
            p3_future_locked_planning_candidates=(),
            development_runs=(),
            excluded=tuple(excluded),
            pair_lineage=(),
            grouping_key="run_id; pair_id groups both arms",
            split_seed=None,
            p3_status=P3_NOT_FROZEN,
            reasons=(REASON_SPLIT_INFEASIBLE, REASON_INDEPENDENT_POPULATION),
            minimum_evidence=(
                f"at least {min_groups_per_partition * 3} independent run/pair "
                "groups so every partition receives a group",
            ),
            synthetic_control=synthetic_control,
        )
    # Doc 03 §48's ~16/4/4 shape needs about 12 groups before rounding can
    # fill all three partitions. Below that floor, a balanced provisional
    # shape is used explicitly; it is a planning candidate, not a frozen split.
    if n_groups < 12:
        proportions = SplitProportions(
            train=1 / 3,
            validation=1 / 3,
            test=1 / 3,
        )
        shape_prefix = "balanced small-population shape (one third each)"
    else:
        proportions = SplitProportions(
            train=16 / 24,
            validation=4 / 24,
            test=4 / 24,
        )
        shape_prefix = "Doc 03 §48 shape ~16 development / 4 validation / 4 test"
    config = SplitConfig(
        proportions=proportions,
        seed=seed,
        controller_context="reactive-or-observational",
        min_groups_per_partition=min_groups_per_partition,
    )
    try:
        split = split_runs(infos, config)
    except SplitError as exc:
        reason = (
            REASON_SPLIT_PAIR_STRADDLE
            if "straddle" in str(exc)
            else REASON_SPLIT_INFEASIBLE
        )
        return SplitPlan(
            feasibility=SPLIT_NOT_FEASIBLE,
            planning_shape="three partitions P1/P2/P3; grouped by run/pair",
            candidate_count=len(candidates),
            eligible_count=len(eligible),
            p1_training=(),
            p2_held_back_development_validation=(),
            p3_future_locked_planning_candidates=(),
            development_runs=(),
            excluded=tuple(excluded),
            pair_lineage=(),
            grouping_key="run_id; pair_id groups both arms",
            split_seed=seed,
            p3_status=P3_NOT_FROZEN,
            reasons=(reason, str(exc)),
            minimum_evidence=(
                "enough independent run/pair groups for three non-empty "
                "partitions with intact pair lineage",
            ),
            synthetic_control=synthetic_control,
        )
    feasibility = (
        SPLIT_FEASIBLE
        if n_groups >= planning_shape_runs
        else SPLIT_PROVISIONAL
    )
    reasons = [REASON_SPLIT_PLANNING] if feasibility == SPLIT_PROVISIONAL else []
    return SplitPlan(
        feasibility=feasibility,
        planning_shape=(
            f"{shape_prefix}; {n_groups} independent group(s) available, so "
            "this is a planning candidate only"
        ),
        candidate_count=len(candidates),
        eligible_count=len(eligible),
        p1_training=split.train_runs,
        p2_held_back_development_validation=split.validation_runs,
        p3_future_locked_planning_candidates=split.test_runs,
        development_runs=tuple(sorted(split.train_runs + split.validation_runs)),
        excluded=tuple(excluded)
        + tuple(
            {"run_id": item.run_id, "reason": item.reason}
            for item in split.excluded_runs
        ),
        pair_lineage=split.pair_lineage,
        grouping_key="run_id; pair_id groups both arms",
        split_seed=seed,
        p3_status=P3_NOT_FROZEN,
        reasons=tuple(reasons),
        minimum_evidence=(
            "A-valid independent runs; verified hardware/calibration; complete "
            "event evidence for the declared scenario; pair lineage preserved; "
            f"at least {planning_shape_runs} groups for a stable planning shape",
        ),
        synthetic_control=synthetic_control,
    )


# ---------------------------------------------------------------------------
# Report, CSV and manifest rendering
# ---------------------------------------------------------------------------


def _fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "NOT_ESTIMABLE"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _bool(value: bool | None) -> str:
    if value is None:
        return "NOT_EVALUABLE"
    return "YES" if value else "NO"


def run_validation_csv(report: GateBReport) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "source_path",
            "source_sha256",
            "physical_source_key",
            "run_id",
            "device_id",
            "boot_id",
            "scenario_id",
            "hardware_config_id",
            "hardware_config_status",
            "calibration_id",
            "calibration_status",
            "time_domain",
            "clock_sync_status",
            "a_ledger_verdict",
            "admission_status",
            "admission_highest_stage",
            "b_eligibility",
            "anchor_present",
            "whole_capture_completeness",
            "critical_channel_completeness",
            "event_window_completeness",
            "baseline_completeness",
            "recovery_completeness",
            "timing_alignment_status",
            "blocking_checks",
            "reason_codes",
        ]
    )
    for item in report.validations:
        whole = item.completeness_for(DIMENSION_WHOLE)
        critical = item.completeness_for(DIMENSION_CRITICAL)
        event = item.completeness_for(DIMENSION_EVENT)
        baseline = item.completeness_for(DIMENSION_BASELINE)
        recovery = item.completeness_for(DIMENSION_RECOVERY)
        timing = item.completeness_for(DIMENSION_TIMING)

        def fraction(result: CompletenessResult | None) -> str:
            if result is None:
                return "NOT_ESTIMABLE"
            if result.fraction is None:
                return result.status
            return _fmt(result.fraction)

        writer.writerow(
            [
                item.source_path,
                item.source_sha256,
                "|".join(str(part) for part in item.physical_source_key),
                item.run_id or "",
                item.device_id or "",
                item.boot_id or "",
                item.scenario_id or "",
                item.hardware_config_id or "",
                item.hardware_config_status or "",
                item.calibration_id or "",
                item.calibration_status or "",
                item.time_domain,
                item.clock_sync_status,
                item.a_ledger_verdict,
                item.admission_status,
                item.admission_highest_stage,
                item.eligibility,
                _bool(item.event_coverage.anchor_present)
                if item.event_coverage.required
                else "NOT_APPLICABLE",
                fraction(whole),
                fraction(critical),
                fraction(event),
                fraction(baseline),
                fraction(recovery),
                timing.status if timing is not None else "NOT_ESTIMABLE",
                ";".join(
                    check.code
                    for check in item.blocking_failures
                ),
                ";".join(item.reason_codes),
            ]
        )
    return buffer.getvalue()


def render_completeness_policy(policy: CompletenessPolicy) -> str:
    lines = [
        "# W08 completeness threshold draft (B-W08-02)",
        "",
        f"Policy version: `{policy.policy_version}`",
        "",
        "The policy is derived from physical and event requirements. It does "
        "not assert a universal 99.9% threshold. `PROPOSED` values are planning "
        "candidates and remain provisional until the owner and reviewer freeze "
        "them. `UNRESOLVED` means the validator cannot evaluate the dimension; "
        "it is never replaced by zero.",
        "",
        "| Dimension | Threshold | Status | Applicability | Denominator | Equality | Blocking | Owner |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for threshold in policy.thresholds:
        lines.append(
            f"| `{threshold.dimension}` | {_fmt(threshold.value)} | "
            f"{threshold.status} | {threshold.applicable_scenario} | "
            f"{threshold.denominator} | {threshold.equality_behavior} | "
            f"{threshold.blocking_severity} | {threshold.owner} |"
        )
    lines.extend(["", "## Threshold definitions", ""])
    for threshold in policy.thresholds:
        lines.extend(
            [
                f"### `{threshold.name}` — {threshold.dimension}",
                "",
                f"- Definition: {threshold.definition}",
                f"- Channel family: {threshold.channel_family}",
                f"- Required event window: {threshold.required_event_window}",
                f"- Missing/quality semantics: {threshold.missing_semantics}",
                f"- Source/justification: {threshold.source_justification}",
                f"- Review authority: {threshold.review_authority}",
                "",
            ]
        )
    lines.extend(["## Policy notes", ""])
    lines.extend(f"- {note}" for note in policy.notes)
    lines.append("")
    return "\n".join(lines)


def render_split_plan(plan: SplitPlan) -> str:
    lines = [
        "# W08 provisional grouped development split plan (B-W08-04)",
        "",
        f"**Feasibility: `{plan.feasibility}`**",
        "",
        "This is a plan, not a final physical holdout. P3 is not frozen and no "
        "locked-test manifest is created or inspected.",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Planning shape | {plan.planning_shape} |",
        f"| Candidate runs | {plan.candidate_count} |",
        f"| Eligible runs | {plan.eligible_count} |",
        f"| Grouping key | {plan.grouping_key} |",
        f"| Split seed | {_fmt(plan.split_seed)} |",
        f"| P3 status | `{plan.p3_status}` |",
        f"| Development definition | P1 training ∪ P2 held-back validation |",
        "",
        "## Assignments (planning candidates only)",
        "",
        f"- P1 training: {', '.join(plan.p1_training) or 'none'}",
        f"- P2 held-back development validation: "
        f"{', '.join(plan.p2_held_back_development_validation) or 'none'}",
        f"- P3 future locked-test planning candidates (NOT FROZEN): "
        f"{', '.join(plan.p3_future_locked_planning_candidates) or 'none'}",
        f"- Development (P1 ∪ P2): {', '.join(plan.development_runs) or 'none'}",
        "",
        "## Excluded views/runs",
        "",
    ]
    if plan.excluded:
        lines.append("| Run/source | Reason |")
        lines.append("|---|---|")
        for item in plan.excluded:
            lines.append(
                f"| {item.get('run_id') or item.get('source_path') or 'unknown'} | "
                f"{item.get('reason')} |"
            )
    else:
        lines.append("None recorded.")
    lines.extend(
        [
            "",
            "## Pair lineage",
            "",
        ]
    )
    if plan.pair_lineage:
        for entry in plan.pair_lineage:
            lines.append(
                f"- pair `{entry.get('pair_id')}` → "
                f"{', '.join(entry.get('run_ids', []))} "
                f"(partition {entry.get('partition')})"
            )
    else:
        lines.append("No paired groups in the current population.")
    lines.extend(
        [
            "",
            "## Reasons and minimum evidence",
            "",
        ]
    )
    lines.extend(f"- {reason}" for reason in plan.reasons)
    lines.extend(f"- Required evidence: {item}" for item in plan.minimum_evidence)
    if plan.synthetic_control:
        lines.extend(
            [
                "",
                "**Synthetic control:** these assignments demonstrate the "
                "feasibility logic only. Synthetic success is never physical "
                "dataset readiness.",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def render_readiness_report(
    report: GateBReport,
    *,
    code_sha256: str,
    repository_revision: str,
    generation_command: str,
    source_index_sha256: str | None = None,
) -> str:
    lines = [
        "# ColdGuard W08 — Gate B dataset readiness",
        "",
        f"Report schema: `{W08_REPORT_SCHEMA}` · layer `{W08_LAYER_VERSION}`",
        "",
        "| Provenance | Value |",
        "|---|---|",
        f"| Analysis code SHA-256 | `{code_sha256}` |",
        f"| Repository revision | `{repository_revision}` |",
        f"| Generation command | `{generation_command}` |",
        f"| A run index SHA-256 | `{source_index_sha256 or 'NOT_PROVIDED'}` |",
        f"| Completeness policy | `{report.policy.policy_version}` |",
        "",
        "## 1. Declared purpose",
        "",
        f"- Scenario: `{report.scenario_requirement.scenario_id}`",
        f"- Purpose: {report.scenario_requirement.dataset_purpose}",
        f"- Event required: {_bool(report.scenario_requirement.requires_door_event)}",
        f"- Absolute event-time claim: "
        f"{_bool(report.scenario_requirement.require_absolute_time)}",
        "",
        "## 2. Gate decisions",
        "",
        "| Gate | Observed status | Severity | Reason codes |",
        "|---|---|---|---|",
    ]
    for gate in (
        report.software_gate,
        report.physical_gate,
        report.predictive_gate,
        report.split_gate,
    ):
        lines.append(
            f"| `{gate.gate}` | **{gate.observed_status}** | {gate.severity} | "
            f"{', '.join(gate.reason_codes) or 'none'} |"
        )
    lines.extend(
        [
            "",
            "A RED physical gate cannot become GREEN because other gates are "
            "GREEN. W08 software verification is reported separately from the "
            "physical-data verdict.",
            "",
            "## 3. Run validation",
            "",
            "| Source | Run | Scenario | A ledger | B eligibility | Blocking checks |",
            "|---|---|---|---|---|---|",
        ]
    )
    for item in report.validations:
        lines.append(
            f"| `{item.source_path}` | `{item.run_id or 'UNRESOLVED'}` | "
            f"`{item.scenario_id or 'NONE'}` | {item.a_ledger_verdict} | "
            f"**{item.eligibility}** | "
            f"{', '.join(check.code for check in item.blocking_failures) or 'none'} |"
        )
    lines.extend(
        [
            "",
            "### Reason codes and evidence",
            "",
        ]
    )
    for item in report.validations:
        lines.append(f"#### `{item.source_path}`")
        lines.append("")
        lines.append(f"- Source SHA-256: `{item.source_sha256}`")
        lines.append(
            f"- Physical acquisition identity: `{'|'.join(str(part) for part in item.physical_source_key)}`"
        )
        lines.append(
            f"- Identity: run={item.run_id!r} device={item.device_id!r} boot={item.boot_id!r}"
        )
        lines.append(
            f"- Configuration: hardware={item.hardware_config_id!r} "
            f"({item.hardware_config_status}) calibration={item.calibration_id!r} "
            f"({item.calibration_status}) firmware={item.firmware_version!r}"
        )
        lines.append(
            f"- Time: domain={item.time_domain!r} clock_sync={item.clock_sync_status!r}"
        )
        lines.append(
            f"- A ledger: {item.a_ledger_verdict} "
            f"({', '.join(item.a_ledger_reasons) or 'no reasons'})"
        )
        lines.append(
            f"- Event coverage: {item.event_coverage.detail}"
        )
        lines.append(f"- Reason codes: {', '.join(item.reason_codes) or 'none'}")
        lines.append("")
    lines.extend(
        [
            "## 4. Completeness evaluation",
            "",
            "| Dimension | Status | Threshold | Expected | Observed | Missing | Invalid | Fraction |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for item in report.validations:
        for result in item.completeness:
            lines.append(
                f"| `{result.dimension}` | {result.status} | "
                f"{_fmt(result.threshold)} ({result.threshold_status}) | "
                f"{_fmt(result.expected_samples)} | {_fmt(result.observed_samples)} | "
                f"{_fmt(result.missing_samples)} | {_fmt(result.invalid_samples)} | "
                f"{_fmt(result.fraction)} |"
            )
    lines.extend(
        [
            "",
            "Whole-capture completeness never substitutes for event-window "
            "completeness; missing critical samples are counted distinctly and "
            "are never converted to zero.",
            "",
            "## 5. Gate evidence and required next evidence",
            "",
        ]
    )
    for gate in (
        report.physical_gate,
        report.predictive_gate,
        report.split_gate,
    ):
        lines.extend(
            [
                f"### `{gate.gate}`",
                "",
                f"- Observed status: **{gate.observed_status}**",
                f"- Population: {gate.population}",
                f"- Required checks: {', '.join(gate.required_checks)}",
                f"- Evidence paths: {', '.join(gate.evidence_paths) or 'none'}",
                f"- Evidence SHA-256: "
                f"{', '.join(gate.evidence_sha256) or 'none'}",
                f"- Allowed uses: {', '.join(gate.allowed_uses) or 'none'}",
                f"- Prohibited uses: {', '.join(gate.prohibited_uses) or 'none'}",
                f"- Next evidence required: {gate.next_evidence_required}",
                "",
            ]
        )
    lines.extend(
        [
            "## 6. Split feasibility",
            "",
            f"**SPLIT_FEASIBILITY = `{report.split_plan.feasibility}`**",
            "",
            f"- P1 training assignments: "
            f"{', '.join(report.split_plan.p1_training) or 'none'}",
            f"- P2 held-back validation assignments: "
            f"{', '.join(report.split_plan.p2_held_back_development_validation) or 'none'}",
            f"- P3 locked-test planning candidates: "
            f"{', '.join(report.split_plan.p3_future_locked_planning_candidates) or 'none'} "
            f"(`{report.split_plan.p3_status}`)",
            f"- Reasons: {', '.join(report.split_plan.reasons) or 'none'}",
            "",
            "No final test ID list is created or frozen. "
            "`development-split-plan-W08.md` carries the planning detail.",
            "",
            "## 7. W07 physical-repeatability evidence",
            "",
        ]
    )
    if report.w07_evidence is None:
        lines.append(
            "No W07 manifest was supplied. Run-level independence is still "
            "enforced from the W04/W07 physical-source key; no repeatability "
            "claim is inferred."
        )
    else:
        lines.append(
            f"- Verdict: `{report.w07_evidence.get('verdict')}`; qualified "
            f"independent runs: {report.w07_evidence.get('qualified_independent_runs')}; "
            f"independent physical sources: {report.w07_evidence.get('independent_physical_sources')}"
        )
        lines.append(
            f"- Reason codes: "
            f"{', '.join(report.w07_evidence.get('reason_codes', [])) or 'none'}"
        )
    lines.extend(
        [
            "",
            "## 8. Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report.limitations)
    lines.append("")
    return "\n".join(lines)


def build_gate_manifest(
    report: GateBReport,
    *,
    code_sha256: str,
    repository_revision: str,
    generation_command: str,
    artifact_sha256: dict[str, str],
    source_index_sha256: str | None = None,
    generated_at_utc: str | None = None,
) -> str:
    payload = {
        "schema": W08_MANIFEST_SCHEMA,
        "layer_version": W08_LAYER_VERSION,
        "analysis_code_sha256": code_sha256,
        "repository_revision": repository_revision,
        "generation_command": generation_command,
        "source_index_sha256": source_index_sha256,
        "generated_at_utc": generated_at_utc or "NOT_RECORDED_BY_DESIGN",
        "artifact_sha256": dict(sorted(artifact_sha256.items())),
        "completeness_policy_version": report.policy.policy_version,
        **report.to_dict(),
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
