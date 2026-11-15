"""W18 Controller B readiness assessment (B-W18-04).

Member B owns model and scientific readiness evidence.  It does not own the
physical controller, policy authorization or final acceptance.  This module
therefore derives the readiness status from declared evidence and always
withholds the physical signoff while any Gate G4 prerequisite is unmet.

It cannot issue a model release candidate, fabricate an approval, enable
Controller B or convert software evidence into physical evidence.

Canonical anchors: Doc 04 §31 Gate G4, §33 W18; Doc 05B §46 B-W18-04, §54.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

STATUS_READY = "READY"
STATUS_BLOCKED = "BLOCKED"
READY_FOR_TEAM_REVIEW = "READY_FOR_TEAM_REVIEW"

MONITORING_VERIFIED = "VERIFIED"
MONITORING_PARTIAL = "PARTIAL"
MONITORING_NOT_VERIFIED = "NOT_VERIFIED"

TRACE_ESTABLISHED = "ESTABLISHED"
TRACE_NOT_ESTABLISHED = "NOT_ESTABLISHED"

MODEL_RELEASE_ISSUED = "ISSUED"
MODEL_RELEASE_NOT_ISSUED = "NOT_ISSUED"

G4_READY = "READY"
G4_NOT_READY = "NOT_READY"

SIGNOFF_WITHHELD = "WITHHELD"
SIGNOFF_READY_FOR_HUMAN = "READY_FOR_HUMAN_SIGNOFF"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ReadinessDimensionSpec:
    dimension_id: str
    requirement: str
    owner: str
    canonical_ref: str


READINESS_DIMENSIONS: tuple[ReadinessDimensionSpec, ...] = (
    ReadinessDimensionSpec(
        "model_identity",
        "Correct model identity (artifact ID, SHA-256, config binding, library).",
        "B",
        "05B §46; 03 §92",
    ),
    ReadinessDimensionSpec(
        "feature_schema_compatibility",
        "Feature/schema compatibility (version, order, schema hash).",
        "B",
        "05B §46; 03 §92",
    ),
    ReadinessDimensionSpec(
        "prediction_freshness",
        "Prediction freshness under a defined runtime policy.",
        "C/D",
        "05B §46; 02 §5",
    ),
    ReadinessDimensionSpec(
        "risk_score_semantics",
        "Risk-score semantics (never calibrated probability).",
        "B",
        "03 §58-60",
    ),
    ReadinessDimensionSpec(
        "policy_freeze",
        "Horizon, threshold and persistence frozen by their authorities.",
        "B/D/TEAM_LEAD",
        "03 §44, §87-88; 04 §11.4",
    ),
    ReadinessDimensionSpec(
        "offline_parity",
        "Offline feature and prediction parity evidence.",
        "B",
        "05B §45; 03 §1.2",
    ),
    ReadinessDimensionSpec(
        "approved_model_candidate",
        "Approved real-model release candidate.",
        "TEAM_LEAD",
        "03 §92-93",
    ),
    ReadinessDimensionSpec(
        "locked_predictive_evaluation",
        "Authorized frozen-model locked predictive evaluation.",
        "B/TEAM_LEAD",
        "03 §92-93; 04 §31",
    ),
    ReadinessDimensionSpec(
        "c_inference_trace_integration",
        "Actual C inference/trace integration.",
        "C",
        "05B §46; C W17/W18",
    ),
    ReadinessDimensionSpec(
        "d_policy_safety_authorization",
        "D policy and safety authorization.",
        "D",
        "02 §1.6; 04 §33",
    ),
    ReadinessDimensionSpec(
        "a_physical_response_verification",
        "A independently verified electrical and thermal response.",
        "A",
        "01 §1.5-1.7; 03 §137",
    ),
    ReadinessDimensionSpec(
        "g4_evidence",
        "Complete Gate G4 evidence.",
        "TEAM",
        "04 §31",
    ),
)

G4_DIMENSIONS = (
    "prediction_freshness",
    "policy_freeze",
    "offline_parity",
    "approved_model_candidate",
    "locked_predictive_evaluation",
    "c_inference_trace_integration",
    "d_policy_safety_authorization",
    "a_physical_response_verification",
    "g4_evidence",
)


@dataclass(frozen=True)
class DimensionResult:
    dimension_id: str
    requirement: str
    owner: str
    status: str
    observed: str
    evidence: str
    canonical_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension_id": self.dimension_id,
            "requirement": self.requirement,
            "owner": self.owner,
            "status": self.status,
            "observed": self.observed,
            "evidence": self.evidence,
            "canonical_ref": self.canonical_ref,
        }


@dataclass(frozen=True)
class ControllerBReadiness:
    dimensions: tuple[DimensionResult, ...]
    blockers: tuple[str, ...]
    fake_approval_detected: bool
    software_monitoring: str
    trace_validator: str
    physical_intervention_trace: str
    model_release: str
    gate_g4: str
    readiness_status: str
    signoff: str
    signoff_withheld: bool
    human_authority_note: str
    approval_effect: str = "NONE_SOFTWARE_ASSESSMENT_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimensions": [dimension.to_dict() for dimension in self.dimensions],
            "blockers": list(self.blockers),
            "fake_approval_detected": self.fake_approval_detected,
            "software_monitoring": self.software_monitoring,
            "trace_validator": self.trace_validator,
            "physical_intervention_trace": self.physical_intervention_trace,
            "model_release": self.model_release,
            "gate_g4": self.gate_g4,
            "readiness_status": self.readiness_status,
            "signoff": self.signoff,
            "signoff_withheld": self.signoff_withheld,
            "human_authority_note": self.human_authority_note,
            "approval_effect": self.approval_effect,
        }


def _validate_approval_records(
    records: Sequence[Mapping[str, Any]],
) -> tuple[bool, list[str]]:
    """A record is valid only when its authority and evidence are bound."""
    problems: list[str] = []
    if not records:
        return True, problems
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            problems.append(f"approval[{index}] is not an object")
            continue
        if not record.get("role"):
            problems.append(f"approval[{index}] lacks a role")
        if not record.get("authority_id"):
            problems.append(f"approval[{index}] lacks an authority identity")
        if not _HEX64.match(str(record.get("evidence_sha256") or "")):
            problems.append(f"approval[{index}] lacks a bound evidence hash")
        if not record.get("canonical_ref"):
            problems.append(f"approval[{index}] lacks a canonical reference")
    return not problems, problems


def assess_controller_b_readiness(
    observations: Mapping[str, Mapping[str, Any]],
    *,
    trace_validator_verified: bool,
    freshness_software_verified: bool = False,
    approval_records: Sequence[Mapping[str, Any]] = (),
) -> ControllerBReadiness:
    """Derive the readiness status from declared evidence; never guess."""
    if not isinstance(observations, Mapping):
        raise ValueError("observations must be a mapping")
    approvals_valid, _ = _validate_approval_records(list(approval_records))
    rows: list[DimensionResult] = []
    ready_by_id: dict[str, bool] = {}
    for spec in READINESS_DIMENSIONS:
        observation = observations.get(spec.dimension_id)
        if not isinstance(observation, Mapping):
            ready = False
            observed = "MISSING_EVIDENCE"
            evidence = ""
        else:
            ready = observation.get("ready") is True
            observed = str(observation.get("observed") or "UNKNOWN")
            evidence = str(observation.get("evidence") or "")
        if not approvals_valid and spec.dimension_id in {
            "d_policy_safety_authorization",
            "a_physical_response_verification",
            "g4_evidence",
        }:
            ready = False
        ready_by_id[spec.dimension_id] = ready
        rows.append(
            DimensionResult(
                dimension_id=spec.dimension_id,
                requirement=spec.requirement,
                owner=spec.owner,
                status=STATUS_READY if ready else STATUS_BLOCKED,
                observed=observed,
                evidence=evidence,
                canonical_ref=spec.canonical_ref,
            )
        )
    blockers = tuple(
        spec.dimension_id
        for spec in READINESS_DIMENSIONS
        if not ready_by_id.get(spec.dimension_id, False)
    )
    software_dims = (
        "model_identity",
        "feature_schema_compatibility",
        "risk_score_semantics",
    )
    software_ready = all(
        ready_by_id.get(dimension, False) for dimension in software_dims
    ) and freshness_software_verified
    software_monitoring = (
        MONITORING_VERIFIED if software_ready else MONITORING_PARTIAL
    )
    trace_validator = (
        MONITORING_VERIFIED if trace_validator_verified else MONITORING_NOT_VERIFIED
    )
    physical_established = (
        ready_by_id.get("a_physical_response_verification", False)
        and approvals_valid
    )
    physical_intervention_trace = (
        TRACE_ESTABLISHED if physical_established else TRACE_NOT_ESTABLISHED
    )
    model_release = (
        MODEL_RELEASE_ISSUED
        if ready_by_id.get("approved_model_candidate", False) and approvals_valid
        else MODEL_RELEASE_NOT_ISSUED
    )
    g4_ready = (
        all(ready_by_id.get(dimension, False) for dimension in G4_DIMENSIONS)
        and approvals_valid
    )
    gate_g4 = G4_READY if g4_ready else G4_NOT_READY
    all_ready = all(ready_by_id.values()) and approvals_valid
    readiness_status = (
        READY_FOR_TEAM_REVIEW if all_ready else STATUS_BLOCKED
    )
    signoff_withheld = not (
        all_ready
        and g4_ready
        and model_release == MODEL_RELEASE_ISSUED
        and physical_intervention_trace == TRACE_ESTABLISHED
        and approvals_valid
    )
    signoff = SIGNOFF_WITHHELD if signoff_withheld else SIGNOFF_READY_FOR_HUMAN
    return ControllerBReadiness(
        dimensions=tuple(rows),
        blockers=blockers,
        fake_approval_detected=not approvals_valid,
        software_monitoring=software_monitoring,
        trace_validator=trace_validator,
        physical_intervention_trace=physical_intervention_trace,
        model_release=model_release,
        gate_g4=gate_g4,
        readiness_status=readiness_status,
        signoff=signoff,
        signoff_withheld=signoff_withheld,
        human_authority_note=(
            "Project lead and responsible A/C/D owners control final acceptance; "
            "this software assessment cannot issue a physical signoff, approve a "
            "model release, or authorize Controller B. Approval records are "
            "shape-checked only; B cannot verify external signatures offline."
        ),
        approval_effect="NONE_SOFTWARE_ASSESSMENT_ONLY",
    )
