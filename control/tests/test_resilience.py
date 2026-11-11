import pytest

from coldguard_control.resilience import (
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
    decision = assess_resilience(healthy())
    assert decision.g4_ready is True
    assert decision.mode is ResilienceMode.ONLINE_REMOTE
