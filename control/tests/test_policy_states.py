"""W03 state mapping, SAFE_LOCAL entry/exit and input-contract tests."""

from __future__ import annotations

import pytest

from _builders import (
    PLAIN_FAULT,
    make_config,
    make_input,
    make_prediction,
    make_remote,
    make_thermal,
)
from coldguard_control import (
    ActuationIntent,
    ControllerId,
    CoolingState,
    DeviceMode,
    PolicyInputError,
    PolicyPreconditionError,
    PolicyState,
    QualityState,
    ReasonCode,
    evaluate_policy,
    safe_local_exit_status,
)


# --------------------------------------------------------------------------
# Controller A hysteresis (no numbers beyond the synthetic config)
# --------------------------------------------------------------------------
def test_inside_band_holds_applied_state() -> None:
    decision = evaluate_policy(
        make_input(applied_cooling=CoolingState.ON), make_config()
    )

    assert decision.state is PolicyState.NORMAL
    assert decision.actuation_intent is ActuationIntent.HOLD


def test_below_lower_boundary_requests_off_with_recovery_reason() -> None:
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.VALID, 5.5, 1.0),
            applied_cooling=CoolingState.ON,
        ),
        make_config(),
    )

    assert decision.state is PolicyState.NORMAL
    assert decision.actuation_intent is ActuationIntent.OFF
    assert decision.reason_code is ReasonCode.THRESHOLD_RECOVERED


def test_below_lower_boundary_already_off_is_idempotent_hold() -> None:
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.VALID, 5.5, 1.0),
            applied_cooling=CoolingState.OFF,
        ),
        make_config(),
    )

    assert decision.actuation_intent is ActuationIntent.HOLD
    assert decision.reason_code is None


@pytest.mark.parametrize(
    ("temperature", "expected_state", "expected_intent"),
    [
        (8.0, PolicyState.CRITICAL_PROTECTION, ActuationIntent.ON),
        (6.0, PolicyState.NORMAL, ActuationIntent.OFF),
    ],
)
def test_boundaries_are_inclusive(
    temperature: float,
    expected_state: PolicyState,
    expected_intent: ActuationIntent,
) -> None:
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.VALID, temperature, 1.0),
            applied_cooling=CoolingState.ON,
        ),
        make_config(),
    )

    assert decision.state is expected_state
    assert decision.actuation_intent is expected_intent


def test_critical_protection_latches_until_recovery_boundary() -> None:
    decision = evaluate_policy(
        make_input(
            current_state=PolicyState.CRITICAL_PROTECTION,
            thermal=make_thermal(QualityState.VALID, 7.0, 1.0),
            applied_cooling=CoolingState.ON,
        ),
        make_config(),
    )

    assert decision.state is PolicyState.CRITICAL_PROTECTION
    assert decision.actuation_intent is ActuationIntent.ON
    assert decision.controller_id is ControllerId.REACTIVE


def test_critical_protection_releases_at_lower_boundary() -> None:
    decision = evaluate_policy(
        make_input(
            current_state=PolicyState.CRITICAL_PROTECTION,
            thermal=make_thermal(QualityState.VALID, 6.0, 1.0),
            applied_cooling=CoolingState.ON,
        ),
        make_config(),
    )

    assert decision.state is PolicyState.NORMAL
    assert decision.actuation_intent is ActuationIntent.OFF
    assert decision.reason_code is ReasonCode.THRESHOLD_RECOVERED


def test_watch_state_holds_and_does_not_actuate() -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(prediction=make_prediction(risk=0.55, persisted=0.0)),
        cfg,
    )

    assert decision.state is PolicyState.WATCH
    assert decision.actuation_intent is ActuationIntent.HOLD


def test_degraded_sensing_blocks_predictive_but_keeps_local_policy() -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.DEGRADED, 7.0, 1.0),
            prediction=make_prediction(risk=0.9, persisted=600.0),
        ),
        cfg,
    )

    assert decision.state is PolicyState.NORMAL
    assert decision.actuation_intent is ActuationIntent.HOLD
    assert decision.degraded_sensing is True
    assert decision.predictive_blocked is True
    assert decision.reason_code is ReasonCode.SENSOR_DEGRADED


def test_stale_thermal_state_is_fault_with_no_new_actuation() -> None:
    decision = evaluate_policy(
        make_input(thermal=make_thermal(QualityState.VALID, 7.0, 16.0)),
        make_config(),
    )

    assert decision.state is PolicyState.FAULT
    assert decision.actuation_intent is ActuationIntent.HOLD
    assert decision.predictive_blocked is True


@pytest.mark.parametrize(
    "quality", [QualityState.INVALID, QualityState.UNKNOWN]
)
def test_unusable_critical_thermal_state_locks_out(
    quality: QualityState,
) -> None:
    decision = evaluate_policy(
        make_input(thermal=make_thermal(quality, None, 1.0)),
        make_config(),
    )

    assert decision.state is PolicyState.FAULT_LOCKOUT
    assert decision.actuation_intent is ActuationIntent.HOLD
    assert decision.reason_code is ReasonCode.THERMAL_STATE_INVALID


def test_plain_fault_is_not_silently_optimized_away() -> None:
    decision = evaluate_policy(
        make_input(fault_active=True, fault_reason=PLAIN_FAULT),
        make_config(),
    )

    assert decision.state is PolicyState.FAULT
    assert decision.actuation_intent is ActuationIntent.HOLD
    assert decision.reason_code is PLAIN_FAULT


# --------------------------------------------------------------------------
# SAFE_LOCAL entry and exit
# --------------------------------------------------------------------------
def test_broker_loss_enters_safe_local_with_local_hysteresis() -> None:
    decision = evaluate_policy(
        make_input(
            remote=make_remote(
                broker_connected=False, broker_offline_s=120.0
            ),
            applied_cooling=CoolingState.ON,
        ),
        make_config(),
    )

    assert decision.state is PolicyState.SAFE_LOCAL
    assert decision.transition == "SAFE_LOCAL_ENTER"
    assert decision.reason_code is ReasonCode.NETWORK_UNAVAILABLE
    assert decision.actuation_intent is ActuationIntent.HOLD
    assert decision.controller_id is ControllerId.REACTIVE
    assert "broker_connected" in decision.safe_local_exit_missing


def test_untrusted_twin_state_enters_safe_local_not_remote_trust() -> None:
    decision = evaluate_policy(
        make_input(remote=make_remote(state_sync_trusted=False)),
        make_config(),
    )

    assert decision.state is PolicyState.SAFE_LOCAL
    assert decision.reason_code is ReasonCode.BACKEND_UNAVAILABLE
    assert decision.transition == "SAFE_LOCAL_ENTER"


def test_reconnect_alone_does_not_restore_remote_trust() -> None:
    decision = evaluate_policy(
        make_input(
            device_mode=DeviceMode.SAFE_LOCAL,
            current_state=PolicyState.SAFE_LOCAL,
            remote=make_remote(
                broker_connected=True,
                network_stable_s=0.0,
                state_sync_trusted=False,
            ),
        ),
        make_config(),
    )

    assert decision.state is PolicyState.SAFE_LOCAL
    assert decision.transition is None
    assert "network_stable" in decision.safe_local_exit_missing
    assert "state_sync_trusted" in decision.safe_local_exit_missing
    assert decision.actuation_intent is not ActuationIntent.ON


def test_safe_local_exits_only_when_every_requirement_holds() -> None:
    decision = evaluate_policy(
        make_input(
            device_mode=DeviceMode.SAFE_LOCAL,
            current_state=PolicyState.SAFE_LOCAL,
            remote=make_remote(network_stable_s=90.0),
            thermal=make_thermal(QualityState.VALID, 7.0, 1.0),
        ),
        make_config(),
    )

    assert decision.state is PolicyState.NORMAL
    assert decision.transition == "SAFE_LOCAL_EXIT"
    assert decision.safe_local_exit_missing == ()


@pytest.mark.parametrize(
    ("overrides", "missing"),
    [
        ({"broker_connected": False}, "broker_connected"),
        ({"network_stable_s": 0.0}, "network_stable"),
        ({"backend_state_synced": False}, "backend_state_synchronized"),
        ({"backend_state_age_s": 11.0}, "backend_state_fresh"),
        ({"state_sync_trusted": False}, "state_sync_trusted"),
        (
            {"remote_command_path_trusted": False},
            "remote_command_path_trusted",
        ),
        ({"stale_command_pending": True}, "no_stale_command"),
    ],
)
def test_safe_local_exit_reports_each_missing_remote_requirement(
    overrides: dict[str, object], missing: str
) -> None:
    ok, missing_requirements = safe_local_exit_status(
        make_input(remote=make_remote(**overrides)), make_config()
    )

    assert ok is False
    assert missing in missing_requirements


def test_safe_local_exit_requires_fresh_valid_telemetry_and_no_fault() -> None:
    ok, missing = safe_local_exit_status(
        make_input(
            thermal=make_thermal(QualityState.DEGRADED, 7.0, 1.0),
            fault_active=True,
        ),
        make_config(),
    )

    assert ok is False
    assert "fresh_valid_telemetry" in missing
    assert "no_critical_fault" in missing


def test_safe_local_exit_requires_healthy_prediction_when_predictive_on() -> None:
    ok, missing = safe_local_exit_status(
        make_input(prediction=None),
        make_config(predictive_enabled=True),
    )

    assert ok is False
    assert "prediction_healthy" in missing


def test_stale_pending_command_blocks_exit_even_with_good_telemetry() -> None:
    decision = evaluate_policy(
        make_input(
            device_mode=DeviceMode.SAFE_LOCAL,
            current_state=PolicyState.SAFE_LOCAL,
            remote=make_remote(stale_command_pending=True),
        ),
        make_config(),
    )

    assert decision.state is PolicyState.SAFE_LOCAL
    assert decision.safe_local_exit_missing == ("no_stale_command",)


# --------------------------------------------------------------------------
# Input contract and determinism
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mode", [DeviceMode.BOOT, DeviceMode.SELF_TEST]
)
def test_policy_undefined_before_online_modes(mode: DeviceMode) -> None:
    with pytest.raises(PolicyPreconditionError):
        evaluate_policy(make_input(device_mode=mode), make_config())


def test_valid_quality_requires_value_and_age() -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(thermal=make_thermal(QualityState.VALID, None, 1.0)),
            make_config(),
        )


def test_invalid_quality_must_not_carry_a_substituted_value() -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(
                thermal=make_thermal(QualityState.INVALID, 7.0, 1.0)
            ),
            make_config(),
        )


def test_risk_score_outside_unit_interval_is_rejected() -> None:
    cfg = make_config(predictive_enabled=True)
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(prediction=make_prediction(risk=1.5)), cfg
        )


def test_negative_age_is_rejected() -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(thermal=make_thermal(QualityState.VALID, 7.0, -1.0)),
            make_config(),
        )


def test_unknown_door_state_is_rejected() -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(make_input(door_state="AJAR"), make_config())


def test_evaluation_is_deterministic() -> None:
    cfg = make_config(predictive_enabled=True)
    inp = make_input(prediction=make_prediction(risk=0.6, persisted=0.0))

    assert evaluate_policy(inp, cfg) == evaluate_policy(inp, cfg)
