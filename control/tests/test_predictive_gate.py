import pytest

from coldguard_control.aiw import AIWStatus
from coldguard_control.predictive_gate import (
    OutputSemantics,
    PredictiveCandidateEvidence,
    PredictiveGateStatus,
    FalseWarningAssessment,
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
        "false_warning_assessment": None,
    }
    values.update(overrides)
    return PredictiveCandidateEvidence(**values)


def test_current_b_w14_evidence_stays_blocked_and_is_not_probability():
    result = assess_predictive_gate(current_b_evidence())
    assert result.status is PredictiveGateStatus.BLOCKED_MISSING_POLICY
    assert "score_threshold" in result.blockers
    assert "positive_aiw" in result.blockers
    assert result.probability_wording_allowed is False
    assert result.false_warning_assessed is False
    assert result.persistence_justified is False
    assert result.physical_enablement is False


def test_complete_candidate_is_still_only_a_review_candidate():
    false_warning = FalseWarningAssessment(
        false_positive_rate_at_threshold=0.05,
        false_warning_count_in_validation=2,
        total_validation_windows=100,
        persistence_justification="30s persistence prevents sensor chatter based on max transient of 5s",
        max_transient_duration_s=5.0,
    )
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
        false_warning_assessment=false_warning,
    ))
    assert result.status is PredictiveGateStatus.ACTUATION_REVIEW_CANDIDATE
    assert result.blockers == ()
    assert result.false_warning_assessed is True
    assert result.persistence_justified is True
    assert result.physical_enablement is False


def test_probability_wording_requires_calibration_evidence():
    with pytest.raises(ValueError, match="calibration"):
        current_b_evidence(
            output_semantics=OutputSemantics.CALIBRATED_PROBABILITY,
            calibration_qualified=False,
        )


def test_only_probability_threshold_must_be_in_unit_interval():
    assert current_b_evidence(score_threshold=1.5).score_threshold == 1.5
    with pytest.raises(ValueError, match="\\[0, 1\\]"):
        current_b_evidence(
            output_semantics=OutputSemantics.CALIBRATED_PROBABILITY,
            calibration_qualified=True,
            score_threshold=1.5,
        )
    with pytest.raises(ValueError, match="\\[0, 1\\]"):
        current_b_evidence(
            output_semantics=OutputSemantics.CALIBRATED_PROBABILITY,
            calibration_qualified=True,
            score_threshold=-0.1,
        )


def test_threshold_boundary_values():
    # 0 and 1 should be valid
    evidence = current_b_evidence(score_threshold=0.0)
    assert evidence.score_threshold == 0.0
    evidence = current_b_evidence(score_threshold=1.0)
    assert evidence.score_threshold == 1.0


def test_false_warning_assessment_required():
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
        # No false_warning_assessment
    ))
    assert "false_warning_assessment" in result.blockers
    assert result.false_warning_assessed is False


def test_persistence_justification_required():
    # Empty persistence justification should fail validation
    with pytest.raises(ValueError, match="persistence_justification"):
        FalseWarningAssessment(
            false_positive_rate_at_threshold=0.05,
            false_warning_count_in_validation=2,
            total_validation_windows=100,
            persistence_justification="",  # Empty justification
            max_transient_duration_s=5.0,
        )

    # Also test that missing false_warning_assessment causes blocker
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
        # No false_warning_assessment
    ))
    assert "persistence_justification" in result.blockers
    assert result.persistence_justified is False


def test_false_warning_assessment_validation():
    with pytest.raises(ValueError, match="false_positive_rate_at_threshold"):
        FalseWarningAssessment(
            false_positive_rate_at_threshold=1.5,  # Out of range
            false_warning_count_in_validation=0,
            total_validation_windows=10,
            persistence_justification="test",
            max_transient_duration_s=5.0,
        )
    with pytest.raises(ValueError, match="persistence_justification"):
        FalseWarningAssessment(
            false_positive_rate_at_threshold=0.05,
            false_warning_count_in_validation=0,
            total_validation_windows=10,
            persistence_justification="",  # Empty
            max_transient_duration_s=5.0,
        )
