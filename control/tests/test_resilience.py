import pytest

from coldguard_control.resilience import (
    G4ReadinessEvidence,
    ResilienceInput,
    ResilienceMode,
    assess_resilience,
)


def healthy(**overrides):
    values = {
        "ai_available": True,
        "prediction_fresh": True,
        "broker_available": True,
        "backend_available": True,
        "db_available": True,
        "state_resynced": True,
        "stale_command_pending": False,
        "network_stable_s": 60.0,
        "required_stable_s": 60.0,
        # W16: G4 readiness evidence (software vector green only, not g4_ready)
        "g4_readiness_evidence": None,
    }
    values.update(overrides)
    return ResilienceInput(**values)


def healthy_with_g4(**overrides):
    """Helper for tests that require g4_ready=True."""
    g4_evidence = G4ReadinessEvidence(
        software_vector_green=True,
        live_resilience_evidence=True,
        resilience_signoff_member="D",
        resilience_signoff_timestamp="2026-11-12T10:00:00Z",
        resilience_test_scenarios=("broker_outage", "backend_outage"),
        evidence_reference="evidence/resilience-live-001",
    )
    values = {
        "ai_available": True,
        "prediction_fresh": True,
        "broker_available": True,
        "backend_available": True,
        "db_available": True,
        "state_resynced": True,
        "stale_command_pending": False,
        "network_stable_s": 60.0,
        "required_stable_s": 60.0,
        "g4_readiness_evidence": g4_evidence,
    }
    values.update(overrides)
    return ResilienceInput(**values)


def test_ai_failure_falls_back_without_reusing_score():
    decision = assess_resilience(healthy(ai_available=False))
    assert decision.mode is ResilienceMode.ONLINE_REACTIVE_ONLY
    assert decision.controller_b_available is False
    assert decision.stale_prediction_reused is False


@pytest.mark.parametrize("field", ["broker_available", "backend_available"])
def test_remote_transport_failure_enters_safe_local(field):
    decision = assess_resilience(healthy(**{field: False}))
    assert decision.mode is ResilienceMode.SAFE_LOCAL
    assert decision.allow_new_predictive_command is False


def test_db_failure_blocks_new_predictive_command():
    decision = assess_resilience(healthy(db_available=False))
    assert decision.mode is ResilienceMode.ONLINE_REACTIVE_ONLY
    assert decision.allow_new_predictive_command is False


def test_reconnect_requires_resync_no_stale_command_and_stability():
    for overrides in (
        {"state_resynced": False},
        {"stale_command_pending": True},
        {"network_stable_s": 59.9},
    ):
        decision = assess_resilience(healthy(**overrides))
        assert decision.mode is ResilienceMode.SAFE_LOCAL
        assert decision.g4_ready is False


def test_all_checks_pass_g4_logic_only():
    # W16: software_vector_green is separate from g4_ready
    decision = assess_resilience(healthy())
    assert decision.software_vector_green is True
    assert decision.g4_ready is False  # Requires G4ReadinessEvidence

    # W16: g4_ready requires live resilience evidence and signoff
    decision_g4 = assess_resilience(healthy_with_g4())
    assert decision_g4.g4_ready is True
    assert decision_g4.mode is ResilienceMode.ONLINE_REMOTE
