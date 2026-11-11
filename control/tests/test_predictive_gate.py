import pytest

from coldguard_control.aiw import AIWStatus
from coldguard_control.predictive_gate import (
    OutputSemantics,
    PredictiveCandidateEvidence,
    PredictiveGateStatus,
    assess_predictive_gate,
)


def current_b_evidence(**overrides):
    values = {
        "policy_version": "d-w14-candidate-v0",
        "output_semantics": OutputSemantics.RISK_SCORE_ONLY,
        "score_threshold": None,
        "persistence_s": None,
        "horizon_s": None,
        "model_frozen": False,
        "feature_contract_frozen": False,
        "calibration_qualified": False,
        "real_eligible_runs": 0,
        "aiw_status": AIWStatus.UNKNOWN,
        "g3_green": False,
        "g4_green": False,
    }
    values.update(overrides)
    return PredictiveCandidateEvidence(**values)


def test_current_b_w14_evidence_stays_blocked_and_is_not_probability():
    result = assess_predictive_gate(current_b_evidence())
    assert result.status is PredictiveGateStatus.BLOCKED_MISSING_POLICY
    assert "score_threshold" in result.blockers
    assert "positive_aiw" in result.blockers
    assert result.probability_wording_allowed is False
    assert result.physical_enablement is False


def test_complete_candidate_is_still_only_a_review_candidate():
    result = assess_predictive_gate(current_b_evidence(
        score_threshold=0.7,
        persistence_s=30.0,
        horizon_s=120.0,
        model_frozen=True,
        feature_contract_frozen=True,
        real_eligible_runs=4,
        aiw_status=AIWStatus.POSITIVE_CANDIDATE,
        g3_green=True,
        g4_green=True,
    ))
    assert result.status is PredictiveGateStatus.ACTUATION_REVIEW_CANDIDATE
    assert result.blockers == ()
    assert result.physical_enablement is False


def test_probability_wording_requires_calibration_evidence():
    with pytest.raises(ValueError, match="calibration"):
        current_b_evidence(
            output_semantics=OutputSemantics.CALIBRATED_PROBABILITY,
            calibration_qualified=False,
        )
