"""W16/W18 physical enablement assessment tests."""
import pytest

from coldguard_control.enablement import (
    EnablementDecision,
    EnablementPreconditions,
    EnablementStatus,
    G4ReadinessEvidence,
    G4ReadinessStatus,
    evaluate_physical_enablement,
)


def test_g4_readiness_evidence_validation():
    evidence = G4ReadinessEvidence(
        software_vector_green=True,
        live_resilience_evidence=True,
        resilience_signoff_member="D",
        resilience_signoff_timestamp="2026-11-12T10:00:00Z",
        resilience_test_scenarios=("broker_outage", "backend_outage"),
        evidence_reference="evidence/D/W16/g4-live.json",
    )
    assert evidence.software_vector_green is True
    assert evidence.live_resilience_evidence is True


def test_enablement_preconditions_requires_pinned_identifiers():
    g4_evidence = G4ReadinessEvidence(
        software_vector_green=True,
        live_resilience_evidence=True,
        resilience_signoff_member="D",
        resilience_signoff_timestamp="2026-11-12T10:00:00Z",
        resilience_test_scenarios=("broker_outage",),
        evidence_reference="evidence/D/W16/g4-live.json",
    )
    preconditions = EnablementPreconditions(
        enable_requested=True,
        g4_green=True,
        g4_readiness_evidence=g4_evidence,
        a_physical_envelope_stable=True,
        b_model_frozen=True,
        b_policy_frozen=True,
        b_action_frozen=True,
        policy_id="policy-v1.0",
        config_id="config-v1.0",
        action_id="action-v1.0",
        score_threshold=0.7,
        persistence_s=30.0,
        c_command_trace_stable=True,
        complete_prediction_to_thermal_trace=True,
        failure_behavior_frozen=True,
        clean_dry_runs_verified=True,
        witness_member_a=True,
        witness_member_b=True,
        witness_member_c=True,
        witness_member_d=True,
    )
    assert preconditions.policy_id == "policy-v1.0"
    assert preconditions.score_threshold == 0.7


def test_enablement_preconditions_preserve_generic_score_scale():
    g4_evidence = G4ReadinessEvidence(
        software_vector_green=True,
        live_resilience_evidence=True,
        resilience_signoff_member="D",
        resilience_signoff_timestamp="2026-11-12T10:00:00Z",
        resilience_test_scenarios=("broker_outage",),
        evidence_reference="evidence/D/W16/g4-live.json",
    )
    preconditions = EnablementPreconditions(
        enable_requested=True,
        g4_green=True,
        g4_readiness_evidence=g4_evidence,
        a_physical_envelope_stable=True,
        b_model_frozen=True,
        b_policy_frozen=True,
        b_action_frozen=True,
        policy_id="policy-v1.0",
        config_id="config-v1.0",
        action_id="action-v1.0",
        score_threshold=1.5,
        persistence_s=30.0,
        c_command_trace_stable=True,
        complete_prediction_to_thermal_trace=True,
        failure_behavior_frozen=True,
        clean_dry_runs_verified=True,
        witness_member_a=True,
        witness_member_b=True,
        witness_member_c=True,
        witness_member_d=True,
    )
    assert preconditions.score_threshold == 1.5


def test_enablement_preconditions_requires_pinned_identifiers_not_empty():
    g4_evidence = G4ReadinessEvidence(
        software_vector_green=True,
        live_resilience_evidence=True,
        resilience_signoff_member="D",
        resilience_signoff_timestamp="2026-11-12T10:00:00Z",
        resilience_test_scenarios=("broker_outage",),
        evidence_reference="evidence/D/W16/g4-live.json",
    )
    with pytest.raises(TypeError, match="policy_id"):
        EnablementPreconditions(
            enable_requested=True,
            g4_green=True,
            g4_readiness_evidence=g4_evidence,
            a_physical_envelope_stable=True,
            b_model_frozen=True,
            b_policy_frozen=True,
            b_action_frozen=True,
            policy_id="",  # Empty
            config_id="config-v1.0",
            action_id="action-v1.0",
            score_threshold=0.7,
            persistence_s=30.0,
            c_command_trace_stable=True,
            complete_prediction_to_thermal_trace=True,
            failure_behavior_frozen=True,
            clean_dry_runs_verified=True,
            witness_member_a=True,
            witness_member_b=True,
            witness_member_c=True,
            witness_member_d=True,
        )


def test_g4_ready_requires_live_resilience_evidence():
    g4_evidence_no_live = G4ReadinessEvidence(
        software_vector_green=True,
        live_resilience_evidence=False,  # No live evidence
        resilience_signoff_member="D",
        resilience_signoff_timestamp="2026-11-12T10:00:00Z",
        resilience_test_scenarios=("broker_outage",),
        evidence_reference="evidence/D/W16/g4-live.json",
    )
    preconditions = EnablementPreconditions(
        enable_requested=True,
        g4_green=True,
        g4_readiness_evidence=g4_evidence_no_live,
        a_physical_envelope_stable=True,
        b_model_frozen=True,
        b_policy_frozen=True,
        b_action_frozen=True,
        policy_id="policy-v1.0",
        config_id="config-v1.0",
        action_id="action-v1.0",
        score_threshold=0.7,
        persistence_s=30.0,
        c_command_trace_stable=True,
        complete_prediction_to_thermal_trace=True,
        failure_behavior_frozen=True,
        clean_dry_runs_verified=True,
        witness_member_a=True,
        witness_member_b=True,
        witness_member_c=True,
        witness_member_d=True,
    )

    result = evaluate_physical_enablement(preconditions)
    assert result.g4_ready is False
    assert "g4_ready" in result.blockers


def test_g4_ready_with_live_resilience_evidence():
    g4_evidence_live = G4ReadinessEvidence(
        software_vector_green=True,
        live_resilience_evidence=True,  # Has live evidence
        resilience_signoff_member="D",
        resilience_signoff_timestamp="2026-11-12T10:00:00Z",
        resilience_test_scenarios=("broker_outage", "backend_outage"),
        evidence_reference="evidence/D/W16/g4-live.json",
    )
    preconditions = EnablementPreconditions(
        enable_requested=True,
        g4_green=True,
        g4_readiness_evidence=g4_evidence_live,
        a_physical_envelope_stable=True,
        b_model_frozen=True,
        b_policy_frozen=True,
        b_action_frozen=True,
        policy_id="policy-v1.0",
        config_id="config-v1.0",
        action_id="action-v1.0",
        score_threshold=0.7,
        persistence_s=30.0,
        c_command_trace_stable=True,
        complete_prediction_to_thermal_trace=True,
        failure_behavior_frozen=True,
        clean_dry_runs_verified=True,
        witness_member_a=True,
        witness_member_b=True,
        witness_member_c=True,
        witness_member_d=True,
    )

    result = evaluate_physical_enablement(preconditions)
    assert result.g4_ready is True
    assert result.status is EnablementStatus.REVIEW_READY
    assert result.review_ready is True
    # W18: Pinned identifiers in decision
    assert result.policy_id == "policy-v1.0"
    assert result.config_id == "config-v1.0"
    assert result.action_id == "action-v1.0"
    assert result.score_threshold == 0.7
    assert result.persistence_s == 30.0


def test_review_ready_requires_threshold_and_persistence():
    g4_evidence = G4ReadinessEvidence(
        software_vector_green=True,
        live_resilience_evidence=True,
        resilience_signoff_member="D",
        resilience_signoff_timestamp="2026-11-12T10:00:00Z",
        resilience_test_scenarios=("broker_outage",),
        evidence_reference="evidence/D/W16/g4-live.json",
    )
    preconditions = EnablementPreconditions(
        enable_requested=True,
        g4_green=True,
        g4_readiness_evidence=g4_evidence,
        a_physical_envelope_stable=True,
        b_model_frozen=True,
        b_policy_frozen=True,
        b_action_frozen=True,
        policy_id="policy-v1.0",
        config_id="config-v1.0",
        action_id="action-v1.0",
        score_threshold=None,  # Missing
        persistence_s=None,  # Missing
        c_command_trace_stable=True,
        complete_prediction_to_thermal_trace=True,
        failure_behavior_frozen=True,
        clean_dry_runs_verified=True,
        witness_member_a=True,
        witness_member_b=True,
        witness_member_c=True,
        witness_member_d=True,
    )

    result = evaluate_physical_enablement(preconditions)
    assert result.review_ready is False
    assert "score_threshold_required" in result.blockers
    assert "persistence_s_required" in result.blockers


def test_software_vector_green_not_sufficient_for_g4():
    """W16: software-vector green alone is not sufficient for G4."""
    g4_evidence_software_only = G4ReadinessEvidence(
        software_vector_green=True,
        live_resilience_evidence=False,  # No live resilience
        resilience_signoff_member="D",
        resilience_signoff_timestamp="2026-11-12T10:00:00Z",
        resilience_test_scenarios=("broker_outage",),
        evidence_reference="evidence/D/W16/g4-live.json",
    )
    preconditions = EnablementPreconditions(
        enable_requested=True,
        g4_green=True,
        g4_readiness_evidence=g4_evidence_software_only,
        a_physical_envelope_stable=True,
        b_model_frozen=True,
        b_policy_frozen=True,
        b_action_frozen=True,
        policy_id="policy-v1.0",
        config_id="config-v1.0",
        action_id="action-v1.0",
        score_threshold=0.7,
        persistence_s=30.0,
        c_command_trace_stable=True,
        complete_prediction_to_thermal_trace=True,
        failure_behavior_frozen=True,
        clean_dry_runs_verified=True,
        witness_member_a=True,
        witness_member_b=True,
        witness_member_c=True,
        witness_member_d=True,
    )

    result = evaluate_physical_enablement(preconditions)
    # Software vector green alone is not sufficient
    assert result.g4_ready is False
    assert "g4_ready" in result.blockers


def test_physical_command_never_emitted():
    """Invariant: physical_command_emitted is always False."""
    g4_evidence = G4ReadinessEvidence(
        software_vector_green=True,
        live_resilience_evidence=True,
        resilience_signoff_member="D",
        resilience_signoff_timestamp="2026-11-12T10:00:00Z",
        resilience_test_scenarios=("broker_outage",),
        evidence_reference="evidence/D/W16/g4-live.json",
    )
    preconditions = EnablementPreconditions(
        enable_requested=True,
        g4_green=True,
        g4_readiness_evidence=g4_evidence,
        a_physical_envelope_stable=True,
        b_model_frozen=True,
        b_policy_frozen=True,
        b_action_frozen=True,
        policy_id="policy-v1.0",
        config_id="config-v1.0",
        action_id="action-v1.0",
        score_threshold=0.7,
        persistence_s=30.0,
        c_command_trace_stable=True,
        complete_prediction_to_thermal_trace=True,
        failure_behavior_frozen=True,
        clean_dry_runs_verified=True,
        witness_member_a=True,
        witness_member_b=True,
        witness_member_c=True,
        witness_member_d=True,
    )

    result = evaluate_physical_enablement(preconditions)
    assert result.physical_command_emitted is False

    # Also test when not review ready
    preconditions_disabled = EnablementPreconditions(
        enable_requested=False,  # Not requested
        g4_green=True,
        g4_readiness_evidence=g4_evidence,
        a_physical_envelope_stable=True,
        b_model_frozen=True,
        b_policy_frozen=True,
        b_action_frozen=True,
        policy_id="policy-v1.0",
        config_id="config-v1.0",
        action_id="action-v1.0",
        score_threshold=0.7,
        persistence_s=30.0,
        c_command_trace_stable=True,
        complete_prediction_to_thermal_trace=True,
        failure_behavior_frozen=True,
        clean_dry_runs_verified=True,
        witness_member_a=True,
        witness_member_b=True,
        witness_member_c=True,
        witness_member_d=True,
    )
    result_disabled = evaluate_physical_enablement(preconditions_disabled)
    assert result_disabled.physical_command_emitted is False
