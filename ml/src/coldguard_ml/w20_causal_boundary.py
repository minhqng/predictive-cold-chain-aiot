"""W20 EWT causal-boundary enforcement (B-W20-04).

Canonical anchors: Doc 03 §§44-45, §68-72; Doc 05B §48 B-W20-04; W03
``metric-spec.md`` §§4-8; SAP §2 (P4 vs P5).

``EWT = t_reactive - t_predictive`` is defined only on admissible offline,
non-predictively-intervened trajectories.  A closed-loop Controller B run can
prevent the reactive crossing, so its unobserved crossing is a counterfactual
that must never be manufactured.  This module is metadata-only: it classifies
provenance, admits or refuses claims, and returns reason codes.  It computes no
EWT, AIW, recovery or energy value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

W20_CAUSAL_BOUNDARY_VERSION = "coldguard-w20-causal-boundary-v1"

PROVENANCE_OFFLINE = "OFFLINE_NON_INTERVENED_EWT_EVIDENCE"
PROVENANCE_CLOSED_LOOP = "CLOSED_LOOP_PHYSICAL_AB_OUTCOME"
PROVENANCE_SYNTHETIC = "SYNTHETIC_SOFTWARE_CONTROL"
PROVENANCE_UNKNOWN = "UNKNOWN_PROVENANCE"

PROVENANCE_CLASSES = (
    PROVENANCE_OFFLINE,
    PROVENANCE_CLOSED_LOOP,
    PROVENANCE_SYNTHETIC,
    PROVENANCE_UNKNOWN,
)

EWT_ADMISSIBLE = "EWT_ADMISSIBLE_METADATA_ONLY"
EWT_NOT_ADMISSIBLE = "EWT_NOT_ADMISSIBLE"
EWT_UNOBSERVED = "EWT_UNOBSERVED_NOT_ZERO"
EWT_UNKNOWN = "EWT_UNKNOWN_NOT_ZERO"
EWT_VALUE_LOCKED = "EWT_VALUE_REQUIRES_SEPARATE_AUTHORIZED_OFFLINE_ANALYSIS"

AIW_ADMISSIBLE = "AIW_ADMISSIBLE_METADATA_ONLY"
AIW_NOT_ADMISSIBLE = "AIW_NOT_ADMISSIBLE"
AIW_UNKNOWN = "AIW_INPUTS_UNKNOWN_NOT_ZERO"

RECOVERY_METADATA_OK = "RECOVERY_CLAIM_METADATA_OK"
RECOVERY_NOT_ADMISSIBLE = "RECOVERY_CLAIM_NOT_ADMISSIBLE"

ENERGY_METADATA_OK = "ENERGY_CLAIM_METADATA_OK"
ENERGY_NOT_ADMISSIBLE = "ENERGY_CLAIM_NOT_ADMISSIBLE"

AB_CONTRACT_ACCEPTED = "AB_REPORT_CONTRACT_ACCEPTED_METADATA_ONLY"
AB_CONTRACT_REJECTED = "AB_REPORT_CONTRACT_REJECTED"

CAUSAL_BOUNDARY_SOFTWARE_VERIFIED = "CAUSAL_BOUNDARY_SOFTWARE_VERIFIED"

SYNTHETIC_MARKERS = ("TEST_ONLY", "SYNTHETIC_SOFTWARE_CONTROL_ONLY")

EVENT_TIME_MEASURED = "MEASURED_EVENT_TIME"
EVENT_TIME_DOMAIN = "EVENT_TIME_DOMAIN"
SYNTHETIC_TIMING = "SYNTHETIC_REPLAY_TIMESTAMP"
TIMING_SOURCES = frozenset({EVENT_TIME_MEASURED, EVENT_TIME_DOMAIN, SYNTHETIC_TIMING, "UNKNOWN"})

CONTEXT_REACTIVE = "REACTIVE"
CONTEXT_PREDICTIVE = "PREDICTIVE"
CONTEXT_NONE = "NONE"
CONTROLLER_CONTEXTS = frozenset({CONTEXT_REACTIVE, CONTEXT_PREDICTIVE, CONTEXT_NONE, "UNKNOWN"})

INTERVENTION_APPLIED = "PREDICTIVE_COOLING_APPLIED"
INTERVENTION_NONE = "NONE"
INTERVENTIONS = frozenset({INTERVENTION_APPLIED, INTERVENTION_NONE, "UNKNOWN"})

EVIDENCE_PHYSICAL = "PHYSICAL"
EVIDENCE_OFFLINE_REPLAY = "OFFLINE_REPLAY"
EVIDENCE_SYNTHETIC = "SYNTHETIC"
EVIDENCE_CLASSES = frozenset(
    {EVIDENCE_PHYSICAL, EVIDENCE_OFFLINE_REPLAY, EVIDENCE_SYNTHETIC, "UNKNOWN"}
)

PZEM_COMPLETE = "COMPLETE"
PZEM_PARTIAL = "PARTIAL"
PZEM_MISSING = "MISSING"
PZEM_VALUES = frozenset({PZEM_COMPLETE, PZEM_PARTIAL, PZEM_MISSING, "UNKNOWN"})

ALLOWED_AB_OUTCOME_METRICS = frozenset(
    {
        "thermal_exposure",
        "recovery_time",
        "peak_temperature",
        "time_above_limit",
        "branch_energy",
    }
)
FORBIDDEN_AB_CLAIM_FIELDS = frozenset(
    {
        "ewt_seconds_from_closed_loop",
        "inferred_reactive_crossing",
        "counterfactual_ewt",
        "ewt_zero_because_no_crossing",
        "aiw_from_synthetic_timing",
        "ack_as_physical_response",
        "electrical_as_thermal_recovery",
        "whole_system_energy",
        "pzem_gap_zero_energy",
    }
)

CAUSAL_RESTRICTION_CHECKS = (
    "CLOSED_LOOP_B_RUNS_EXCLUDED_FROM_NAIVE_EWT",
    "UNOBSERVED_REACTIVE_CROSSING_IS_NOT_ZERO",
    "SYNTHETIC_TIMING_NOT_PROMOTED_TO_ACTIONABILITY",
    "ACK_NOT_SUBSTITUTED_FOR_PHYSICAL_RESPONSE",
    "ELECTRICAL_OBSERVATION_NOT_SUBSTITUTED_FOR_THERMAL_RECOVERY",
    "PZEM_GAP_NOT_CONVERTED_TO_ZERO_ENERGY",
    "COOLING_BRANCH_ENERGY_NOT_WHOLE_SYSTEM_ENERGY",
    "POST_INTERVENTION_WARNING_NOT_USED_AS_NO_CONTROL_COUNTERFACTUAL",
)


class W20CausalBoundaryError(ValueError):
    """Raised for malformed provenance metadata, never for a verdict."""


@dataclass(frozen=True)
class ProvenanceAssessment:
    record_id: str
    provenance_class: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "provenance_class": self.provenance_class,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ClaimAssessment:
    record_id: str
    claim: str
    status: str
    value_status: str
    reasons: tuple[str, ...]
    value_computed: bool = False
    approval_effect: str = "NONE_CAUSAL_SOFTWARE_ASSESSMENT_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "claim": self.claim,
            "status": self.status,
            "value_status": self.value_status,
            "reasons": list(self.reasons),
            "value_computed": self.value_computed,
            "approval_effect": self.approval_effect,
        }


def _require_choice(value: Any, allowed: frozenset[str], field: str) -> str:
    if value not in allowed:
        raise W20CausalBoundaryError(
            f"{field} has unknown value {value!r}; allowed: {sorted(allowed)}"
        )
    return str(value)


def classify_provenance(record: Mapping[str, Any]) -> ProvenanceAssessment:
    """Classify a timing/outcome record without computing anything."""
    if not isinstance(record, Mapping):
        raise W20CausalBoundaryError("provenance record must be an object")
    record_id = str(record.get("record_id") or "")
    if not record_id:
        raise W20CausalBoundaryError("record_id must be a non-empty string")
    markers = record.get("synthetic_markers") or []
    if not isinstance(markers, list) or any(not isinstance(m, str) for m in markers):
        raise W20CausalBoundaryError("synthetic_markers must be a list of strings")
    evidence_class = _require_choice(
        record.get("evidence_class", "UNKNOWN"), EVIDENCE_CLASSES, "evidence_class"
    )
    context = _require_choice(
        record.get("controller_context", CONTEXT_NONE), CONTROLLER_CONTEXTS, "controller_context"
    )
    intervention = _require_choice(
        record.get("intervention", "UNKNOWN"), INTERVENTIONS, "intervention"
    )
    if evidence_class == EVIDENCE_SYNTHETIC or markers:
        return ProvenanceAssessment(
            record_id, PROVENANCE_SYNTHETIC, ("SYNTHETIC_MARKERS_PRESENT",)
        )
    if context == CONTEXT_PREDICTIVE and intervention == INTERVENTION_APPLIED:
        return ProvenanceAssessment(
            record_id,
            PROVENANCE_CLOSED_LOOP,
            ("PREDICTIVE_INTERVENTION_APPLIED",),
        )
    if context in {CONTEXT_REACTIVE, CONTEXT_NONE} and intervention == INTERVENTION_NONE and (
        evidence_class in {EVIDENCE_PHYSICAL, EVIDENCE_OFFLINE_REPLAY}
    ):
        return ProvenanceAssessment(
            record_id, PROVENANCE_OFFLINE, ("NON_PREDICTIVE_NON_INTERVENED",)
        )
    return ProvenanceAssessment(
        record_id, PROVENANCE_UNKNOWN, ("PROVENANCE_INCOMPLETE_OR_AMBIGUOUS",)
    )


def _timing_ok(record: Mapping[str, Any]) -> bool:
    source = record.get("timing_source", "UNKNOWN")
    _require_choice(source, TIMING_SOURCES, "timing_source")
    return source in {EVENT_TIME_MEASURED, EVENT_TIME_DOMAIN}


def _bool_field(record: Mapping[str, Any], field: str) -> bool | None:
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise W20CausalBoundaryError(f"{field} must be a boolean or null")
    return value


def assess_ewt_admissibility(record: Mapping[str, Any]) -> ClaimAssessment:
    """EWT is admitted only from an offline non-intervened trajectory."""
    provenance = classify_provenance(record)
    record_id = provenance.record_id
    reasons: list[str] = []
    if provenance.provenance_class == PROVENANCE_CLOSED_LOOP:
        return ClaimAssessment(
            record_id,
            "EWT",
            EWT_NOT_ADMISSIBLE,
            "EWT_NOT_COMPUTED",
            ("CLOSED_LOOP_INTERVENTION_DESTROYS_THE_COUNTERFACTUAL",),
        )
    if provenance.provenance_class == PROVENANCE_SYNTHETIC:
        return ClaimAssessment(
            record_id,
            "EWT",
            EWT_NOT_ADMISSIBLE,
            "EWT_NOT_COMPUTED",
            ("SYNTHETIC_TIMING_IS_NOT_PHYSICAL_EVIDENCE",),
        )
    if provenance.provenance_class == PROVENANCE_UNKNOWN:
        return ClaimAssessment(
            record_id,
            "EWT",
            EWT_NOT_ADMISSIBLE,
            "EWT_NOT_COMPUTED",
            ("PROVENANCE_UNKNOWN_FAILS_CLOSED",),
        )
    if _bool_field(record, "post_intervention_warning_used") is True:
        return ClaimAssessment(
            record_id,
            "EWT",
            EWT_NOT_ADMISSIBLE,
            "EWT_NOT_COMPUTED",
            ("POST_INTERVENTION_WARNING_IS_NOT_A_NO_CONTROL_COUNTERFACTUAL",),
        )
    if not _timing_ok(record):
        reasons.append("TIMING_SOURCE_NOT_MEASURED_EVENT_TIME")
    if _bool_field(record, "ack_only") is True:
        reasons.append("ACK_IS_NOT_A_PHYSICAL_RESPONSE")
    crossing = _bool_field(record, "reactive_crossing_observed")
    if crossing is False:
        return ClaimAssessment(
            record_id,
            "EWT",
            EWT_UNOBSERVED,
            "EWT_UNOBSERVED_NOT_ZERO",
            tuple(sorted(set(reasons + ["REACTIVE_CROSSING_NOT_OBSERVED"]))),
        )
    if crossing is None:
        return ClaimAssessment(
            record_id,
            "EWT",
            EWT_UNKNOWN,
            "EWT_UNKNOWN_NOT_ZERO",
            tuple(sorted(set(reasons + ["REACTIVE_CROSSING_STATUS_UNKNOWN"]))),
        )
    if reasons:
        return ClaimAssessment(
            record_id,
            "EWT",
            EWT_NOT_ADMISSIBLE,
            "EWT_NOT_COMPUTED",
            tuple(sorted(set(reasons))),
        )
    return ClaimAssessment(
        record_id,
        "EWT",
        EWT_ADMISSIBLE,
        EWT_VALUE_LOCKED,
        ("OFFLINE_NON_INTERVENED_METADATA_ADMISSIBLE",),
    )


def assess_aiw_admissibility(record: Mapping[str, Any]) -> ClaimAssessment:
    """AIW requires measured, coherent timing inputs and physical response."""
    provenance = classify_provenance(record)
    record_id = provenance.record_id
    reasons: list[str] = []
    if provenance.provenance_class == PROVENANCE_SYNTHETIC:
        return ClaimAssessment(
            record_id,
            "AIW",
            AIW_NOT_ADMISSIBLE,
            "AIW_NOT_COMPUTED",
            ("SYNTHETIC_TIMING_IS_NOT_ACTIONABILITY_EVIDENCE",),
        )
    if provenance.provenance_class == PROVENANCE_UNKNOWN:
        return ClaimAssessment(
            record_id,
            "AIW",
            AIW_NOT_ADMISSIBLE,
            "AIW_NOT_COMPUTED",
            ("PROVENANCE_UNKNOWN_FAILS_CLOSED",),
        )
    if provenance.provenance_class == PROVENANCE_CLOSED_LOOP:
        reasons.append("CLOSED_LOOP_TIMING_IS_AN_AB_OUTCOME_NOT_AN_OFFLINE_AIW")
    if not _timing_ok(record):
        reasons.append("TIMING_SOURCE_NOT_MEASURED_EVENT_TIME")
    if _bool_field(record, "ack_only") is True:
        reasons.append("ACK_IS_NOT_A_PHYSICAL_RESPONSE")
    measured_inputs = _bool_field(record, "aiw_timing_inputs_measured")
    if measured_inputs is not True:
        return ClaimAssessment(
            record_id,
            "AIW",
            AIW_UNKNOWN,
            "AIW_INPUTS_UNKNOWN_NOT_ZERO",
            tuple(sorted(set(reasons + ["AIW_TIMING_INPUTS_UNKNOWN"]))),
        )
    if _bool_field(record, "thermal_response_verified") is not True:
        reasons.append("PHYSICAL_THERMAL_RESPONSE_NOT_VERIFIED")
    if _bool_field(record, "electrical_observation_only") is True:
        reasons.append("ELECTRICAL_OBSERVATION_IS_NOT_VERIFIED_THERMAL_RESPONSE")
    if reasons:
        return ClaimAssessment(
            record_id,
            "AIW",
            AIW_NOT_ADMISSIBLE,
            "AIW_NOT_COMPUTED",
            tuple(sorted(set(reasons))),
        )
    return ClaimAssessment(
        record_id,
        "AIW",
        AIW_ADMISSIBLE,
        "AIW_VALUE_REQUIRES_SEPARATE_AUTHORIZED_ANALYSIS",
        ("MEASURED_INPUTS_METADATA_ADMISSIBLE",),
    )


def assess_recovery_claim(record: Mapping[str, Any]) -> ClaimAssessment:
    """Recovery is a thermal-outcome claim; electrical-only evidence is refused."""
    record_id = str(record.get("record_id") or "")
    reasons: list[str] = []
    if _bool_field(record, "electrical_observation_only") is True:
        reasons.append("ELECTRICAL_OBSERVATION_IS_NOT_THERMAL_RECOVERY")
    if _bool_field(record, "thermal_response_verified") is not True:
        reasons.append("THERMAL_RECOVERY_NOT_VERIFIED")
    if record.get("recovery_censored") is True:
        reasons.append("RECOVERY_CENSORED_NOT_FINITE")
    if reasons:
        return ClaimAssessment(
            record_id,
            "RECOVERY",
            RECOVERY_NOT_ADMISSIBLE,
            "RECOVERY_NOT_COMPUTED",
            tuple(sorted(set(reasons))),
        )
    return ClaimAssessment(
        record_id,
        "RECOVERY",
        RECOVERY_METADATA_OK,
        "RECOVERY_VALUE_REQUIRES_SEPARATE_AUTHORIZED_ANALYSIS",
        ("THERMAL_RECOVERY_METADATA_ADMISSIBLE",),
    )


def assess_energy_claim(record: Mapping[str, Any]) -> ClaimAssessment:
    """Cooling-branch PZEM energy only; a gap is never zero Wh."""
    record_id = str(record.get("record_id") or "")
    coverage = _require_choice(
        record.get("pzem_coverage", "UNKNOWN"), PZEM_VALUES, "pzem_coverage"
    )
    reasons: list[str] = []
    if record.get("whole_system_claim") is True:
        reasons.append("COOLING_BRANCH_ENERGY_IS_NOT_WHOLE_SYSTEM_ENERGY")
    if record.get("energy_scope") != "COOLING_BRANCH":
        reasons.append("ENERGY_SCOPE_NOT_COOLING_BRANCH")
    if coverage == PZEM_MISSING:
        reasons.append("PZEM_GAP_IS_MISSING_SPAN_NOT_ZERO_ENERGY")
    elif coverage == PZEM_PARTIAL:
        reasons.append("PZEM_PARTIAL_COVERAGE_OUTCOME_UNDEFINED_FOR_GAP_SPAN")
    elif coverage != PZEM_COMPLETE:
        reasons.append("PZEM_COVERAGE_UNKNOWN")
    if reasons:
        return ClaimAssessment(
            record_id,
            "ENERGY",
            ENERGY_NOT_ADMISSIBLE,
            "ENERGY_NOT_COMPUTED",
            tuple(sorted(set(reasons))),
        )
    return ClaimAssessment(
        record_id,
        "ENERGY",
        ENERGY_METADATA_OK,
        "ENERGY_VALUE_REQUIRES_SEPARATE_AUTHORIZED_ANALYSIS",
        ("COOLING_BRANCH_PZEM_COVERAGE_METADATA_OK",),
    )


def validate_ab_report_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Reject a future A/B report contract that smuggles a naive EWT or AIW."""
    if not isinstance(contract, Mapping):
        raise W20CausalBoundaryError("AB report contract must be an object")
    problems: list[str] = []
    forbidden = sorted(set(contract) & FORBIDDEN_AB_CLAIM_FIELDS)
    if forbidden:
        problems.extend(f"FORBIDDEN_CLAIM_FIELD:{field}" for field in forbidden)
    metrics = contract.get("outcome_metrics") or []
    if not isinstance(metrics, list):
        problems.append("OUTCOME_METRICS_MALFORMED")
    else:
        unknown = sorted(set(map(str, metrics)) - ALLOWED_AB_OUTCOME_METRICS)
        if unknown:
            problems.extend(f"OUTCOME_METRIC_NOT_ADMISSIBLE:{metric}" for metric in unknown)
    ewt_claims = contract.get("ewt_claims") or []
    if ewt_claims:
        if not isinstance(ewt_claims, list):
            problems.append("EWT_CLAIMS_MALFORMED")
        else:
            for claim in ewt_claims:
                if not isinstance(claim, Mapping):
                    problems.append("EWT_CLAIM_MALFORMED")
                    continue
                source = claim.get("trajectory_class")
                if source != PROVENANCE_OFFLINE:
                    problems.append("EWT_CLAIM_NOT_FROM_OFFLINE_TRAJECTORY")
                if claim.get("crossing_observed") is False:
                    problems.append("EWT_CLAIM_WITHOUT_OBSERVED_CROSSING")
                if claim.get("timing_source") == SYNTHETIC_TIMING:
                    problems.append("EWT_CLAIM_USES_SYNTHETIC_TIMING")
    aiw_claims = contract.get("aiw_claims") or []
    if aiw_claims:
        if not isinstance(aiw_claims, list):
            problems.append("AIW_CLAIMS_MALFORMED")
        else:
            for claim in aiw_claims:
                if not isinstance(claim, Mapping):
                    problems.append("AIW_CLAIM_MALFORMED")
                    continue
                if claim.get("timing_source") == SYNTHETIC_TIMING:
                    problems.append("AIW_CLAIM_USES_SYNTHETIC_TIMING")
                if claim.get("ack_only") is True:
                    problems.append("AIW_CLAIM_USES_ACK_AS_PHYSICAL_RESPONSE")
    return {
        "status": AB_CONTRACT_REJECTED if problems else AB_CONTRACT_ACCEPTED,
        "reasons": sorted(set(problems)),
        "outcome_values_present": False,
        "approval_effect": "NONE_CAUSAL_SOFTWARE_ASSESSMENT_ONLY",
    }


def causal_restriction_proof() -> dict[str, Any]:
    """State the enforced restrictions; no value or counterfactual is produced."""
    return {
        "version": W20_CAUSAL_BOUNDARY_VERSION,
        "checks": {name: True for name in CAUSAL_RESTRICTION_CHECKS},
        "proof_status": CAUSAL_BOUNDARY_SOFTWARE_VERIFIED,
        "ewt_values_computed": False,
        "aiw_values_computed": False,
        "counterfactual_crossings_invented": False,
    }
