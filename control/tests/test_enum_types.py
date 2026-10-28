"""Runtime enum-type hardening tests.

The dataclasses are annotated but not runtime-enforced. Because the state
vocabularies derive from ``str``/``Enum``, a raw string such as
``"FAULT_LOCKOUT"`` compares equal by value to the member while identity
checks (``is``) remain false. These tests make the boundary explicit: enum
fields must be actual members, and look-alike raw values are rejected rather
than reinterpreted or allowed to skip a safety gate.

All numeric values are synthetic and introduce no physical bound.
"""

from __future__ import annotations

import pytest

from _builders import (
    EXPECTED_DEVICE,
    NOW_S,
    make_command,
    make_config,
    make_evidence,
    make_input,
    make_prediction,
    make_thermal,
)
from coldguard_control import (
    AckStatus,
    ActuationIntent,
    CoolingState,
    DeviceMode,
    PolicyInputError,
    PolicyState,
    QualityState,
    ReasonCode,
    evaluate_policy,
    validate_command,
)

# ---------------------------------------------------------------------------
# PolicyInput enum fields
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["FAULT_LOCKOUT", "ONLINE_NORMAL", 1, None])
def test_device_mode_must_be_enum_member(value: object) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(make_input(device_mode=value), make_config())


def test_raw_string_fault_lockout_with_high_temperature_is_rejected() -> None:
    # 9.0 is above the synthetic upper bound, so a valid ONLINE_NORMAL input at
    # this temperature produces an ON intent. The raw string must raise instead
    # of bypassing the `is DeviceMode.FAULT_LOCKOUT` gate.
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(
                device_mode="FAULT_LOCKOUT",
                thermal=make_thermal(t=9.0),
            ),
            make_config(),
        )


def test_valid_fault_lockout_member_still_holds() -> None:
    decision = evaluate_policy(
        make_input(
            device_mode=DeviceMode.FAULT_LOCKOUT,
            thermal=make_thermal(t=9.0),
        ),
        make_config(),
    )
    assert decision.state is PolicyState.FAULT_LOCKOUT
    assert decision.actuation_intent is ActuationIntent.HOLD


@pytest.mark.parametrize("value", ["VALID", "INVALID", 1, None])
def test_thermal_quality_must_be_enum_member(value: object) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(thermal=make_thermal(quality=value)), make_config()
        )


@pytest.mark.parametrize("value", ["ON", "OFF", 1, None])
def test_applied_cooling_must_be_enum_member(value: object) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(make_input(applied_cooling=value), make_config())


@pytest.mark.parametrize("value", ["NORMAL", "SAFE_LOCAL", 1, object()])
def test_current_state_must_be_enum_member_when_present(value: object) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(make_input(current_state=value), make_config())


@pytest.mark.parametrize("value", ["VALID", "INVALID", 1, None])
def test_electrical_quality_must_be_enum_member(value: object) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(make_input(electrical_quality=value), make_config())


@pytest.mark.parametrize(
    "value",
    [ReasonCode.ELECTRICAL_RESPONSE_MISSING.value, DeviceMode.ONLINE_NORMAL, 1],
)
def test_fault_reason_must_be_reason_code_member(value: object) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(fault_reason=value, fault_active=True), make_config()
        )


@pytest.mark.parametrize("value", ["READY", "UNAVAILABLE", 1, None])
def test_prediction_health_must_be_enum_member(value: object) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(prediction=make_prediction(health=value)),
            make_config(),
        )


# ---------------------------------------------------------------------------
# LocalSafetyEvidence enum fields
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("device_mode", "ONLINE_NORMAL"),
        ("device_mode", "FAULT_LOCKOUT"),
        ("device_mode", 1),
        ("policy_state", "NORMAL"),
        ("policy_state", "FAULT_LOCKOUT"),
        ("policy_state", 1),
        ("thermal_quality", "VALID"),
        ("thermal_quality", 0),
    ],
)
def test_malformed_evidence_is_invalid_state(
    field: str, value: object
) -> None:
    decision = validate_command(
        make_command(),
        make_evidence(**{field: value}),
        make_config(),
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed={},
    )
    assert decision.status is AckStatus.INVALID_STATE
    assert decision.reason_code is ReasonCode.COMMAND_SAFETY_BLOCKED
    assert decision.may_actuate is False
    assert decision.actuation_intent is ActuationIntent.HOLD


def test_malformed_evidence_rejects_off_too() -> None:
    # The documented OFF exception requires a recognized FAULT_LOCKOUT/plain
    # fault state; an unrecognized policy_state is not that state.
    decision = validate_command(
        make_command(action=CoolingState.OFF),
        make_evidence(policy_state="FAULT"),
        make_config(),
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed={},
    )
    assert decision.status is AckStatus.INVALID_STATE
    assert decision.reason_code is ReasonCode.COMMAND_SAFETY_BLOCKED
    assert decision.may_actuate is False


def test_recognized_fault_lockout_still_accepts_safe_off() -> None:
    # Positive control: the documented safe-OFF direction is preserved when
    # the evidence carries real enum members.
    decision = validate_command(
        make_command(action=CoolingState.OFF),
        make_evidence(
            device_mode=DeviceMode.FAULT_LOCKOUT,
            policy_state=PolicyState.FAULT_LOCKOUT,
        ),
        make_config(),
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed={},
    )
    assert decision.status is AckStatus.ACCEPTED
    assert decision.actuation_intent is ActuationIntent.OFF


@pytest.mark.parametrize("value", [True, False, "1010"])
def test_now_s_rejects_bool_and_non_number(value: object) -> None:
    with pytest.raises(ValueError):
        validate_command(
            make_command(),
            make_evidence(),
            make_config(),
            now_s=value,  # type: ignore[arg-type]
            expected_device_id=EXPECTED_DEVICE,
            processed={},
        )


def test_raw_action_string_is_a_schema_error() -> None:
    decision = validate_command(
        make_command(action="ON"),
        make_evidence(),
        make_config(),
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed={},
    )
    assert decision.status is AckStatus.REJECTED
    assert decision.reason_code is ReasonCode.INVALID_JSON
