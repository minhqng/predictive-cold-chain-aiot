import pytest
from coldguard_control import (
    SafeLocalSession,
    SafeLocalStep,
    PolicyConfig,
    PolicyInput,
    ThermalView,
    RemotePathView,
    DeviceMode,
    QualityState,
    CoolingState,
    ReasonCode,
)

def make_config():
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

def make_remote_untrusted():
    return RemotePathView(
        broker_connected=False,
        broker_offline_s=0.0,
        backend_state_synced=True,
        backend_state_age_s=1.0,
        state_sync_trusted=True,
        remote_command_path_trusted=True,
        network_stable_s=0.0,
        stale_command_pending=False,
    )

def make_remote_trusted():
    return RemotePathView(
        broker_connected=True,
        broker_offline_s=0.0,
        backend_state_synced=True,
        backend_state_age_s=1.0,
        state_sync_trusted=True,
        remote_command_path_trusted=True,
        network_stable_s=120.0,
        stale_command_pending=False,
    )

def make_input(remote: RemotePathView) -> PolicyInput:
    return PolicyInput(
        device_mode=DeviceMode.ONLINE_NORMAL,
        thermal=ThermalView(quality=QualityState.VALID, t_representative_c=7.0, age_s=1.0),
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

def test_safe_local_entry_and_exit():
    cfg = make_config()
    session = SafeLocalSession(cfg)
    # Untrusted remote triggers entry
    step: SafeLocalStep = session.step(make_input(make_remote_untrusted()))
    assert step.active
    assert step.entered
    assert step.entry_reason == ReasonCode.NETWORK_UNAVAILABLE
    assert step.local_control_only
    # Now provide trusted remote, should exit immediately (exit_ready True)
    step2 = session.step(make_input(make_remote_trusted()))
    assert not step2.active
    assert step2.exited
    assert step2.exit_ready
