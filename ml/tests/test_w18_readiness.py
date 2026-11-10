"""W18 B-W18-04 readiness-gate controls.

The gate must derive its status from evidence and always withhold the physical
signoff; it must never fabricate an approval or let a red G4 pass.
"""

from __future__ import annotations

import pytest

from coldguard_ml.w18_readiness import (
    G4_NOT_READY,
    G4_READY,
    MODEL_RELEASE_ISSUED,
    MODEL_RELEASE_NOT_ISSUED,
    MONITORING_VERIFIED,
    READINESS_DIMENSIONS,
    READY_FOR_TEAM_REVIEW,
    SIGNOFF_READY_FOR_HUMAN,
    SIGNOFF_WITHHELD,
    TRACE_NOT_ESTABLISHED,
    assess_controller_b_readiness,
)


def _observations(all_ready: bool = True, *, g4_ready: bool | None = None):
    observations = {}
    for spec in READINESS_DIMENSIONS:
        ready = all_ready
        if spec.dimension_id == "g4_evidence" and g4_ready is not None:
            ready = g4_ready
        observations[spec.dimension_id] = {
            "ready": ready,
            "observed": "TEST_FIXTURE",
            "evidence": "test://w18-readiness",
        }
    return observations


def test_twelve_dimensions_declared():
    assert len(READINESS_DIMENSIONS) == 12
    assert len({spec.dimension_id for spec in READINESS_DIMENSIONS}) == 12


def test_all_evidence_ready_is_review_only_and_never_auto_issued():
    result = assess_controller_b_readiness(
        _observations(all_ready=True),
        trace_validator_verified=True,
        freshness_software_verified=True,
    )
    assert result.readiness_status == READY_FOR_TEAM_REVIEW
    assert result.gate_g4 == G4_READY
    assert result.model_release == MODEL_RELEASE_ISSUED
    assert result.signoff == SIGNOFF_READY_FOR_HUMAN
    assert result.signoff_withheld is False
    assert result.approval_effect == "NONE_SOFTWARE_ASSESSMENT_ONLY"


def test_blocked_dimensions_withhold_signoff():
    observations = _observations(all_ready=True)
    observations["a_physical_response_verification"] = {
        "ready": False,
        "observed": "ZERO_DRY_RUNS",
        "evidence": "test://member-a",
    }
    result = assess_controller_b_readiness(
        observations,
        trace_validator_verified=True,
        freshness_software_verified=True,
    )
    assert result.gate_g4 == G4_NOT_READY
    assert result.physical_intervention_trace == TRACE_NOT_ESTABLISHED
    assert result.signoff == SIGNOFF_WITHHELD
    assert result.signoff_withheld is True
    assert "a_physical_response_verification" in result.blockers


def test_red_g4_blocks_even_when_software_is_ready():
    result = assess_controller_b_readiness(
        _observations(all_ready=True, g4_ready=False),
        trace_validator_verified=True,
        freshness_software_verified=True,
    )
    assert result.gate_g4 == G4_NOT_READY
    assert result.signoff == SIGNOFF_WITHHELD
    assert result.blockers == ("g4_evidence",)


def test_fake_approval_metadata_is_blocked():
    fake = [
        {
            "role": "TEAM_LEAD",
            "authority_id": "anonymous",
            "canonical_ref": "test://fake",
        }
    ]
    result = assess_controller_b_readiness(
        _observations(all_ready=True),
        trace_validator_verified=True,
        freshness_software_verified=True,
        approval_records=fake,
    )
    assert result.fake_approval_detected is True
    assert result.gate_g4 == G4_NOT_READY
    assert result.model_release == MODEL_RELEASE_NOT_ISSUED
    assert result.signoff == SIGNOFF_WITHHELD
    assert result.signoff_withheld is True


def test_blocked_freshness_blocks_g4_even_when_other_dimensions_ready():
    observations = _observations(all_ready=True)
    observations["prediction_freshness"] = {
        "ready": False,
        "observed": "RUNTIME_FRESHNESS_POLICY_PENDING_C_D",
        "evidence": "test://c-d",
    }
    result = assess_controller_b_readiness(
        observations,
        trace_validator_verified=True,
        freshness_software_verified=True,
    )
    assert "prediction_freshness" in result.blockers
    assert result.gate_g4 == G4_NOT_READY
    assert result.signoff == SIGNOFF_WITHHELD


def test_valid_bound_approval_does_not_become_software_signoff():
    approvals = [
        {
            "role": "TEAM_LEAD",
            "authority_id": "team-lead",
            "evidence_sha256": "a" * 64,
            "canonical_ref": "04 §33",
        }
    ]
    result = assess_controller_b_readiness(
        _observations(all_ready=True),
        trace_validator_verified=True,
        freshness_software_verified=True,
        approval_records=approvals,
    )
    assert result.fake_approval_detected is False
    assert result.signoff == SIGNOFF_READY_FOR_HUMAN
    assert result.approval_effect == "NONE_SOFTWARE_ASSESSMENT_ONLY"


def test_missing_observation_blocks_rather_than_passes():
    observations = _observations(all_ready=True)
    observations.pop("d_policy_safety_authorization")
    result = assess_controller_b_readiness(
        observations,
        trace_validator_verified=True,
        freshness_software_verified=True,
    )
    assert "d_policy_safety_authorization" in result.blockers
    assert result.signoff == SIGNOFF_WITHHELD


def test_current_style_evidence_reports_software_only_verification():
    observations = _observations(all_ready=False)
    observations["model_identity"]["ready"] = True
    observations["feature_schema_compatibility"]["ready"] = True
    observations["risk_score_semantics"]["ready"] = True
    result = assess_controller_b_readiness(
        observations,
        trace_validator_verified=True,
        freshness_software_verified=True,
    )
    assert result.software_monitoring == MONITORING_VERIFIED
    assert result.model_release == MODEL_RELEASE_NOT_ISSUED
    assert result.gate_g4 == G4_NOT_READY
    assert result.signoff == SIGNOFF_WITHHELD
