from dataclasses import replace
import pytest
from coldguard_control import (
    ControllerAConfig,
    ControllerASample,
    replay_controller_a,
    ActuationIntent,
    CoolingState,
    PolicyDecision,
    PolicyInput,
    ThermalView,
    DeviceMode,
    QualityState,
    PolicyConfig,
)

def make_basic_config() -> PolicyConfig:
    return PolicyConfig(
        policy_version="test-policy",
        representative_source="TMAX",
        upper_on_c=8.0,
        lower_off_c=6.0,
        thermal_max_age_s=15.0,
        command_max_future_skew_s=5.0,
        broker_offline_grace_s=30.0,
        backend_state_max_age_s=10.0,
        safe_local_exit_min_stable_s=0.0,
        predictive_enabled=False,
    )

# Helper to create a PolicyInput with a proper RemotePathView using defaults
from coldguard_control import RemotePathView

def make_input_with_remote() -> PolicyInput:
    remote = RemotePathView(
        broker_connected=True,
        broker_offline_s=0.0,
        backend_state_synced=True,
        backend_state_age_s=1.0,
        state_sync_trusted=True,
        remote_command_path_trusted=True,
        network_stable_s=120.0,
        stale_command_pending=False,
    )
    return PolicyInput(
        device_mode=DeviceMode.ONLINE_NORMAL,
        thermal=ThermalView(quality=QualityState.VALID, t_representative_c=9.0, age_s=1.0),
        applied_cooling=CoolingState.OFF,
        remote=remote,
        current_state=None,
        fan_available=True,
        electrical_quality=QualityState.VALID,
        door_state="CLOSED",
        prediction=None,
        fault_active=False,
        fault_reason=None,
        control_electrical_anomaly=False,
        hardware_safety_condition=False,
    )

def test_controller_a_basic_transition():
    cfg = ControllerAConfig(
        policy=make_basic_config(),
        persistence_s=0.0,
        min_on_dwell_s=0.0,
        min_off_dwell_s=0.0,
        source="test",
    )
    pi = make_input_with_remote()
    sample = ControllerASample(now_s=0.0, policy_input=pi)
    decision = replay_controller_a([sample], cfg)[0]
    assert decision.intent is ActuationIntent.ON
    assert not decision.transitioned
    assert decision.applied_before == CoolingState.OFF
    assert decision.applied_after == CoolingState.OFF

def test_controller_a_persistence_blocks():
    cfg = ControllerAConfig(
        policy=make_basic_config(),
        persistence_s=1.0,
        min_on_dwell_s=0.0,
        min_off_dwell_s=0.0,
        source="test",
    )
    recovering = replace(
        make_input_with_remote(),
        applied_cooling=CoolingState.ON,
        thermal=ThermalView(QualityState.VALID, 5.0, 1.0),
    )
    first, second = replay_controller_a(
        [ControllerASample(0.0, recovering), ControllerASample(1.1, recovering)],
        cfg,
    )
    assert first.intent is ActuationIntent.HOLD
    assert first.persistence_blocked
    assert second.intent is ActuationIntent.OFF
    assert not second.persistence_blocked


def test_minimum_on_dwell_blocks_ordinary_off_transition():
    cfg = ControllerAConfig(make_basic_config(), 0.0, 2.0, 0.0, "test")
    warm = make_input_with_remote()
    recovering = replace(
        warm, applied_cooling=CoolingState.ON,
        thermal=ThermalView(QualityState.VALID, 5.0, 1.0),
    )
    _, blocked, allowed = replay_controller_a(
        [ControllerASample(0.0, warm), ControllerASample(0.5, recovering),
         ControllerASample(2.6, recovering)], cfg,
    )
    assert blocked.intent is ActuationIntent.HOLD
    assert blocked.dwell_blocked
    assert allowed.intent is ActuationIntent.OFF


def test_controller_a_rejects_backwards_sample_time():
    cfg = ControllerAConfig(make_basic_config(), 0.0, 0.0, 0.0, "test")
    with pytest.raises(ValueError, match="backwards"):
        replay_controller_a(
            [ControllerASample(1.0, make_input_with_remote()),
             ControllerASample(0.5, make_input_with_remote())], cfg,
        )


def test_applied_state_changes_only_after_feedback():
    cfg = ControllerAConfig(make_basic_config(), 0.0, 0.0, 0.0, "test")
    initial = make_input_with_remote()
    feedback = replace(initial, applied_cooling=CoolingState.ON)
    first, second = replay_controller_a(
        [ControllerASample(0.0, initial), ControllerASample(1.0, feedback)], cfg
    )
    assert first.intent is ActuationIntent.ON
    assert first.applied_after is CoolingState.OFF
    assert second.transitioned
    assert second.applied_after is CoolingState.ON


def test_critical_protection_bypasses_persistence_and_dwell():
    cfg = ControllerAConfig(make_basic_config(), 30.0, 30.0, 30.0, "test")
    result = replay_controller_a([ControllerASample(0.0, make_input_with_remote())], cfg)[0]
    assert result.intent is ActuationIntent.ON
    assert not result.persistence_blocked
    assert not result.dwell_blocked
