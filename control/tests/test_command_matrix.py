"""W03 command decision matrix (05D D-W03-02) and check ordering."""

from __future__ import annotations

from _builders import (
    EXPECTED_DEVICE,
    NOW_S,
    make_command,
    make_config,
    make_evidence,
    make_thermal,
)
from coldguard_control import (
    ActuationIntent,
    AckStatus,
    CoolingState,
    DeviceMode,
    PolicyState,
    QualityState,
    ReasonCode,
    validate_command,
)


def _run(request=None, evidence=None, cfg=None, processed=None):
    return validate_command(
        request or make_command(),
        evidence or make_evidence(),
        cfg or make_config(),
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed=processed or {},
    )


def test_fresh_valid_on_is_accepted() -> None:
    decision = _run()

    assert decision.status is AckStatus.ACCEPTED
    assert decision.accepted is True
    assert decision.may_actuate is True
    assert decision.actuation_intent is ActuationIntent.ON
    assert decision.reason_code is ReasonCode.OK
    assert decision.checks_passed == (
        "schema",
        "authorization",
        "device_identity",
        "expiry",
        "duplicate",
        "range",
        "safety",
        "state_freshness",
    )


def test_fresh_off_is_accepted() -> None:
    decision = _run(make_command(action=CoolingState.OFF))

    assert decision.status is AckStatus.ACCEPTED
    assert decision.actuation_intent is ActuationIntent.OFF


def test_expired_command_is_rejected() -> None:
    decision = _run(make_command(expires_at=NOW_S))

    assert decision.status is AckStatus.EXPIRED
    assert decision.reason_code is ReasonCode.COMMAND_EXPIRED
    assert decision.may_actuate is False


def test_duplicate_returns_canonical_status_without_reactuating() -> None:
    decision = _run(processed={"cmd-synthetic-001": AckStatus.SAFETY_BLOCKED})

    assert decision.status is AckStatus.DUPLICATE_CANONICAL
    assert decision.reason_code is ReasonCode.COMMAND_DUPLICATE
    assert decision.canonical_status is AckStatus.SAFETY_BLOCKED
    assert decision.actuation_intent is ActuationIntent.HOLD
    assert decision.may_actuate is False


def test_expiry_is_checked_before_duplicate() -> None:
    decision = _run(
        make_command(expires_at=1005.0),
        processed={"cmd-synthetic-001": AckStatus.ACCEPTED},
    )

    assert decision.status is AckStatus.EXPIRED


def test_wrong_device_is_rejected_before_expiry() -> None:
    decision = _run(
        make_command(device_id="cg-other-999", expires_at=1005.0)
    )

    assert decision.status is AckStatus.REJECTED
    assert decision.reason_code is ReasonCode.COMMAND_WRONG_DEVICE


def test_duty_on_non_pwm_configuration_is_out_of_range() -> None:
    decision = _run(make_command(duty=0.5))

    assert decision.status is AckStatus.OUT_OF_RANGE
    assert decision.reason_code is ReasonCode.COMMAND_OUT_OF_RANGE


def test_full_duty_on_non_pwm_configuration_matches_wire_fixture() -> None:
    decision = _run(make_command(duty=1.0))

    assert decision.status is AckStatus.ACCEPTED
    assert decision.actuation_intent is ActuationIntent.ON


def test_pwm_duty_outside_characterized_range_is_out_of_range() -> None:
    cfg = make_config(
        allow_pwm_duty=True,
        allowed_duty_min=0.2,
        allowed_duty_max=0.8,
    )
    decision = _run(make_command(duty=0.9), cfg=cfg)

    assert decision.status is AckStatus.OUT_OF_RANGE


def test_pwm_enabled_on_without_duty_is_out_of_range() -> None:
    cfg = make_config(
        allow_pwm_duty=True,
        allowed_duty_min=0.2,
        allowed_duty_max=0.8,
    )
    decision = _run(make_command(duty=None), cfg=cfg)

    assert decision.status is AckStatus.OUT_OF_RANGE


def test_pwm_enabled_on_inside_range_is_accepted() -> None:
    cfg = make_config(
        allow_pwm_duty=True,
        allowed_duty_min=0.2,
        allowed_duty_max=0.8,
    )
    decision = _run(make_command(duty=0.5), cfg=cfg)

    assert decision.status is AckStatus.ACCEPTED


def test_off_with_nonzero_duty_is_out_of_range() -> None:
    decision = _run(
        make_command(action=CoolingState.OFF, duty=0.5)
    )

    assert decision.status is AckStatus.OUT_OF_RANGE


def test_safe_local_mode_rejects_remote_command() -> None:
    decision = _run(
        evidence=make_evidence(device_mode=DeviceMode.SAFE_LOCAL)
    )

    assert decision.status is AckStatus.INVALID_STATE
    assert decision.reason_code is ReasonCode.COMMAND_SAFETY_BLOCKED


def test_boot_mode_rejects_remote_command() -> None:
    decision = _run(evidence=make_evidence(device_mode=DeviceMode.BOOT))

    assert decision.status is AckStatus.INVALID_STATE


def test_stale_local_state_rejects_command() -> None:
    decision = _run(evidence=make_evidence(thermal_age_s=16.0))

    assert decision.status is AckStatus.INVALID_STATE
    assert decision.reason_code is ReasonCode.COMMAND_STATE_STALE


def test_missing_local_state_age_rejects_command() -> None:
    decision = _run(evidence=make_evidence(thermal_age_s=None))

    assert decision.status is AckStatus.INVALID_STATE
    assert decision.reason_code is ReasonCode.COMMAND_STATE_STALE


def test_active_fault_blocks_energization() -> None:
    decision = _run(
        evidence=make_evidence(
            active_fault=True, policy_state=PolicyState.FAULT
        )
    )

    assert decision.status is AckStatus.SAFETY_BLOCKED
    assert decision.reason_code is ReasonCode.COMMAND_SAFETY_BLOCKED


def test_lockout_policy_state_blocks_energization() -> None:
    decision = _run(
        evidence=make_evidence(
            policy_state=PolicyState.FAULT_LOCKOUT,
            device_mode=DeviceMode.FAULT_LOCKOUT,
        )
    )

    assert decision.status is AckStatus.SAFETY_BLOCKED


def test_hardware_safety_condition_blocks_energization() -> None:
    decision = _run(
        evidence=make_evidence(hardware_safety_condition=True)
    )

    assert decision.status is AckStatus.SAFETY_BLOCKED


def test_unknown_fan_state_is_not_treated_as_healthy() -> None:
    decision = _run(evidence=make_evidence(fan_available=None))

    assert decision.status is AckStatus.SAFETY_BLOCKED
    assert "PHY-SAFE-002" in decision.detail


def test_fan_unavailable_blocks_energization() -> None:
    decision = _run(evidence=make_evidence(fan_available=False))

    assert decision.status is AckStatus.SAFETY_BLOCKED


def test_invalid_thermal_quality_blocks_energization() -> None:
    decision = _run(
        evidence=make_evidence(thermal_quality=QualityState.UNKNOWN)
    )

    assert decision.status is AckStatus.SAFETY_BLOCKED


def test_off_remains_accepted_during_fault_lockout() -> None:
    decision = _run(
        make_command(action=CoolingState.OFF),
        evidence=make_evidence(
            device_mode=DeviceMode.FAULT_LOCKOUT,
            policy_state=PolicyState.FAULT_LOCKOUT,
        ),
    )

    assert decision.status is AckStatus.ACCEPTED
    assert decision.actuation_intent is ActuationIntent.OFF


def test_safety_is_checked_before_state_freshness() -> None:
    decision = _run(
        evidence=make_evidence(
            fan_available=False,
            thermal_age_s=999.0,
        )
    )

    assert decision.status is AckStatus.SAFETY_BLOCKED


def test_unsupported_schema_is_rejected() -> None:
    decision = _run(make_command(schema_version=2))

    assert decision.status is AckStatus.REJECTED
    assert decision.reason_code is ReasonCode.INVALID_JSON
    assert decision.checks_passed == ()


def test_retained_command_is_rejected() -> None:
    decision = _run(make_command(retain=True))

    assert decision.status is AckStatus.REJECTED
    assert decision.reason_code is ReasonCode.INVALID_JSON


def test_expiry_not_later_than_creation_is_rejected_as_schema() -> None:
    decision = _run(make_command(created_at=1010.0, expires_at=1010.0))

    assert decision.status is AckStatus.REJECTED
    assert decision.reason_code is ReasonCode.INVALID_JSON


def test_command_from_far_future_is_rejected() -> None:
    decision = _run(make_command(created_at=1020.0, expires_at=1060.0))

    assert decision.status is AckStatus.REJECTED
    assert decision.reason_code is ReasonCode.INVALID_JSON


def test_unauthorized_command_is_rejected() -> None:
    decision = _run(make_command(authorized=False))

    assert decision.status is AckStatus.REJECTED
    assert decision.reason_code is ReasonCode.AUTHORIZATION_FAILED


def test_non_boolean_authorization_is_a_schema_error() -> None:
    decision = _run(make_command(authorized="yes"))

    assert decision.status is AckStatus.REJECTED
    assert decision.reason_code is ReasonCode.INVALID_JSON


def test_boolean_schema_version_is_not_accepted_as_integer_one() -> None:
    decision = _run(make_command(schema_version=True))

    assert decision.status is AckStatus.REJECTED
    assert decision.reason_code is ReasonCode.INVALID_JSON


def test_empty_command_id_is_rejected() -> None:
    decision = _run(make_command(command_id="  "))

    assert decision.status is AckStatus.REJECTED
    assert decision.reason_code is ReasonCode.INVALID_JSON


def test_accepted_decision_does_not_claim_physical_verification() -> None:
    decision = _run()

    assert decision.status is AckStatus.ACCEPTED
    assert "physical verification" in decision.detail
