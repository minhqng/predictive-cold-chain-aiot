"""W04/W06 command TTL semantics and lifecycle tests (05D D-W04-03, D-W06-01/02).

These tests prove:
* absolute expires_at is authoritative (Doc 02 section 31.1);
* optional command_max_age_s bounds age since issue time;
* optional command_max_ttl_s bounds the declared validity window;
* clock_synchronized gate blocks expiry evaluation when unsynchronized;
* duplicate commands return canonical status without re-actuating.
"""

from __future__ import annotations

import pytest

from coldguard_control import (
    AckStatus,
    ActuationIntent,
    CoolingState,
    DeviceMode,
    LocalSafetyEvidence,
    PolicyConfig,
    PolicyState,
    QualityState,
    ReasonCode,
    validate_command,
)
from coldguard_control.commands import CommandRequest

NOW_S = 1000.0
EXPECTED_DEVICE = "cg-test-001"
PROCESSED_EMPTY: dict[str, AckStatus] = {}


def _cfg(
    predictive_enabled: bool = False,
    command_max_age_s: float | None = None,
    command_max_ttl_s: float | None = None,
    **overrides: object,
) -> PolicyConfig:
    values: dict[str, object] = {
        "policy_version": "test-ttl-v0",
        "representative_source": "TMAX",
        "upper_on_c": 8.0,
        "lower_off_c": 6.0,
        "thermal_max_age_s": 15.0,
        "command_max_future_skew_s": 5.0,
        "broker_offline_grace_s": 30.0,
        "backend_state_max_age_s": 10.0,
        "safe_local_exit_min_stable_s": 60.0,
        "predictive_enabled": predictive_enabled,
        "command_max_age_s": command_max_age_s,
        "command_max_ttl_s": command_max_ttl_s,
    }
    values.update(overrides)
    return PolicyConfig(**values)


def _evidence(
    clock_synchronized: bool = True,
    device_mode: DeviceMode = DeviceMode.ONLINE_NORMAL,
    **overrides: object,
) -> LocalSafetyEvidence:
    values: dict[str, object] = {
        "device_mode": device_mode,
        "policy_state": PolicyState.NORMAL,
        "thermal_quality": QualityState.VALID,
        "thermal_age_s": 1.0,
        "fan_available": True,
        "active_fault": False,
        "hardware_safety_condition": False,
        "clock_synchronized": clock_synchronized,
    }
    values.update(overrides)
    return LocalSafetyEvidence(**values)


def _cmd(
    created_at: float = 990.0,
    expires_at: float = 1030.0,
    action: CoolingState = CoolingState.ON,
    **overrides: object,
) -> CommandRequest:
    values: dict[str, object] = {
        "schema_version": 1,
        "command_id": "cmd-ttl-001",
        "device_id": EXPECTED_DEVICE,
        "action": action,
        "created_at": created_at,
        "expires_at": expires_at,
        "authorized": True,
        "duty": None,
        "retain": False,
    }
    values.update(overrides)
    return CommandRequest(**values)


def test_fresh_command_without_ttl_bounds_is_accepted() -> None:
    result = validate_command(
        _cmd(),
        _evidence(),
        _cfg(),
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed=PROCESSED_EMPTY,
    )

    assert result.status is AckStatus.ACCEPTED


def test_expired_command_by_absolute_time_is_rejected() -> None:
    result = validate_command(
        _cmd(expires_at=NOW_S - 1.0),
        _evidence(),
        _cfg(),
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed=PROCESSED_EMPTY,
    )

    assert result.status is AckStatus.EXPIRED
    assert result.reason_code is ReasonCode.COMMAND_EXPIRED


def test_command_max_age_s_rejects_old_issue_time() -> None:
    cfg = _cfg(command_max_age_s=5.0)
    result = validate_command(
        _cmd(created_at=NOW_S - 10.0, expires_at=NOW_S + 20.0),
        _evidence(),
        cfg,
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed=PROCESSED_EMPTY,
    )

    assert result.status is AckStatus.EXPIRED
    assert "age since created_at" in result.detail


def test_command_max_ttl_s_rejects_long_validity_window() -> None:
    cfg = _cfg(command_max_ttl_s=30.0)
    result = validate_command(
        _cmd(created_at=NOW_S - 5.0, expires_at=NOW_S + 50.0),
        _evidence(),
        cfg,
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed=PROCESSED_EMPTY,
    )

    assert result.status is AckStatus.OUT_OF_RANGE
    assert "validity window exceeds" in result.detail


def test_unsynchronized_clock_blocks_expiry_evaluation() -> None:
    cfg = _cfg(command_max_age_s=30.0)
    result = validate_command(
        _cmd(created_at=NOW_S - 10.0, expires_at=NOW_S + 20.0),
        _evidence(clock_synchronized=False),
        cfg,
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed=PROCESSED_EMPTY,
    )

    assert result.status is AckStatus.SAFETY_BLOCKED
    assert "clock" in result.detail.lower() or "synchronized" in result.detail.lower()


def test_duplicate_returns_canonical_without_reactuating() -> None:
    processed = {"cmd-ttl-001": AckStatus.ACCEPTED}
    result = validate_command(
        _cmd(),
        _evidence(),
        _cfg(),
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed=processed,
    )

    assert result.status is AckStatus.DUPLICATE_CANONICAL
    assert result.reason_code is ReasonCode.COMMAND_DUPLICATE
    assert result.actuation_intent is ActuationIntent.HOLD
    assert result.may_actuate is False


def test_duplicate_returns_original_rejection_reason() -> None:
    processed = {"cmd-ttl-001": AckStatus.SAFETY_BLOCKED}
    result = validate_command(
        _cmd(),
        _evidence(),
        _cfg(),
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed=processed,
    )

    assert result.status is AckStatus.DUPLICATE_CANONICAL
    assert result.canonical_status is AckStatus.SAFETY_BLOCKED


def test_ttl_bounds_are_optional_when_none() -> None:
    cfg = _cfg(command_max_age_s=None, command_max_ttl_s=None)
    result = validate_command(
        _cmd(created_at=NOW_S - 100.0, expires_at=NOW_S + 100.0),
        _evidence(),
        cfg,
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed=PROCESSED_EMPTY,
    )

    assert result.status is AckStatus.ACCEPTED


def test_ttl_config_rejects_non_positive_values() -> None:
    from coldguard_control import ConfigError

    with pytest.raises(ConfigError, match="must be positive"):
        _cfg(command_max_age_s=0)

    with pytest.raises(ConfigError, match="must be positive"):
        _cfg(command_max_ttl_s=-5.0)


def test_ttl_bounds_checked_before_safety() -> None:
    cfg = _cfg(command_max_age_s=5.0)
    result = validate_command(
        _cmd(created_at=NOW_S - 10.0, expires_at=NOW_S + 20.0),
        _evidence(fan_available=False),
        cfg,
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed=PROCESSED_EMPTY,
    )

    assert result.status is AckStatus.EXPIRED
