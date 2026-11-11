"""Synthetic builders shared by the W03 tests.

Every numeric value below is a *synthetic test value*. It exists only to
exercise branch logic and has no commissioning authority. Real thresholds,
freshness windows, persistence and duty bounds must come from Member A's
characterization and the frozen policy configuration (Docs 01 section 39,
02 section 24.4, 04 section 10.3).
"""

from __future__ import annotations

from coldguard_control import (
    CommandRequest,
    CoolingState,
    DeviceMode,
    LocalSafetyEvidence,
    ModelHealth,
    PolicyConfig,
    PolicyInput,
    PolicyState,
    PredictionView,
    QualityState,
    RemotePathView,
    ThermalView,
)
from coldguard_control.types import ReasonCode

SYNTHETIC_NOTE = "synthetic test value; not commissioning data"


def make_config(**overrides: object) -> PolicyConfig:
    values: dict[str, object] = {
        "policy_version": "test-policy-synthetic-v0",
        "representative_source": "TMAX",
        "upper_on_c": 8.0,
        "lower_off_c": 6.0,
        "thermal_max_age_s": 15.0,
        "command_max_future_skew_s": 5.0,
        "broker_offline_grace_s": 30.0,
        "backend_state_max_age_s": 10.0,
        "safe_local_exit_min_stable_s": 60.0,
        "predictive_enabled": False,
    }
    values.update(overrides)
    if values.get("predictive_enabled") is True:
        # Synthetic warning contract stand-in; real values must come from
        # Member B's frozen contract + Member A's characterization.
        values.setdefault("watch_threshold", 0.5)
        values.setdefault("preemptive_threshold", 0.7)
        values.setdefault("persistence_required_s", 30.0)
        values.setdefault("prediction_max_age_s", 300.0)
    return PolicyConfig(**values)  # type: ignore[arg-type]


def make_thermal(
    quality: QualityState = QualityState.VALID,
    t: float | None = 7.0,
    age: float | None = 1.0,
) -> ThermalView:
    return ThermalView(quality=quality, t_representative_c=t, age_s=age)


def make_remote(**overrides: object) -> RemotePathView:
    values: dict[str, object] = {
        "broker_connected": True,
        "broker_offline_s": 0.0,
        "backend_state_synced": True,
        "backend_state_age_s": 1.0,
        "state_sync_trusted": True,
        "remote_command_path_trusted": True,
        "network_stable_s": 120.0,
        "stale_command_pending": False,
    }
    values.update(overrides)
    return RemotePathView(**values)  # type: ignore[arg-type]


def make_prediction(
    risk: float | None = 0.9,
    persisted: float | None = 60.0,
    age: float | None = 5.0,
    health: ModelHealth = ModelHealth.READY,
) -> PredictionView:
    return PredictionView(
        health=health,
        model_version="model-synthetic-v0",
        feature_version="features-synthetic-v0",
        risk_score=risk,
        age_s=age,
        horizon_s=600.0,
        above_preemptive_s=persisted,
    )


def make_input(**overrides: object) -> PolicyInput:
    values: dict[str, object] = {
        "device_mode": DeviceMode.ONLINE_NORMAL,
        "thermal": make_thermal(),
        "applied_cooling": CoolingState.OFF,
        "remote": make_remote(),
        "current_state": PolicyState.NORMAL,
        "fan_available": True,
        "electrical_quality": QualityState.VALID,
        "door_state": "CLOSED",
        "prediction": None,
        "fault_active": False,
        "fault_reason": None,
        "control_electrical_anomaly": False,
        "hardware_safety_condition": False,
    }
    values.update(overrides)
    return PolicyInput(**values)  # type: ignore[arg-type]


def make_command(**overrides: object) -> CommandRequest:
    values: dict[str, object] = {
        "schema_version": 1,
        "command_id": "cmd-synthetic-001",
        "device_id": "cg-test-001",
        "action": CoolingState.ON,
        "created_at": 1000.0,
        "expires_at": 1030.0,
        "authorized": True,
        "duty": None,
        "retain": False,
    }
    values.update(overrides)
    return CommandRequest(**values)  # type: ignore[arg-type]


def make_evidence(**overrides: object) -> LocalSafetyEvidence:
    values: dict[str, object] = {
        "device_mode": DeviceMode.ONLINE_NORMAL,
        "policy_state": PolicyState.NORMAL,
        "thermal_quality": QualityState.VALID,
        "thermal_age_s": 1.0,
        "fan_available": True,
        "active_fault": False,
        "hardware_safety_condition": False,
        "clock_synchronized": True,
    }
    values.update(overrides)
    return LocalSafetyEvidence(**values)  # type: ignore[arg-type]


NOW_S = 1010.0
EXPECTED_DEVICE = "cg-test-001"
PLAIN_FAULT = ReasonCode.ELECTRICAL_RESPONSE_MISSING
