"""Runtime boolean-type hardening tests.

Annotations do not enforce types at runtime. Python truthiness is especially
dangerous here because ``bool("false")`` is ``True``: a raw ``"false"`` passed
to a trust flag would look connected/synchronized/trusted, and ``""``/``0``
would silently clear a fault or safety flag. These tests require actual
``bool`` values at the policy, SAFE_LOCAL-exit and command-evidence boundaries
while preserving the documented safe-OFF behavior for well-typed evidence.

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
    make_remote,
)
from coldguard_control import (
    AckStatus,
    ActuationIntent,
    CoolingState,
    PolicyInputError,
    PolicyState,
    ReasonCode,
    evaluate_policy,
    safe_local_exit_status,
    validate_command,
)

REMOTE_FLAGS = [
    "broker_connected",
    "backend_state_synced",
    "state_sync_trusted",
    "remote_command_path_trusted",
    "stale_command_pending",
]

POLICY_SAFETY_FLAGS = [
    "fault_active",
    "control_electrical_anomaly",
    "hardware_safety_condition",
]

EXIT_TRUST_REQUIREMENTS = [
    ("broker_connected", "broker_connected"),
    ("backend_state_synced", "backend_state_synchronized"),
    ("state_sync_trusted", "state_sync_trusted"),
    ("remote_command_path_trusted", "remote_command_path_trusted"),
]


def _decide(
    evidence: object, action: CoolingState = CoolingState.ON
):
    return validate_command(
        make_command(action=action),
        evidence,  # type: ignore[arg-type]
        make_config(),
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed={},
    )


# ---------------------------------------------------------------------------
# PolicyInput booleans
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("field", REMOTE_FLAGS)
@pytest.mark.parametrize("value", ["false", 0, None])
def test_remote_flags_must_be_actual_bool(field: str, value: object) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(remote=make_remote(**{field: value})), make_config()
        )


@pytest.mark.parametrize("field", POLICY_SAFETY_FLAGS)
@pytest.mark.parametrize("value", ["false", "", 0])
def test_policy_safety_flags_must_be_actual_bool(
    field: str, value: object
) -> None:
    # In particular, "" and 0 must not silently clear a fault/safety flag.
    with pytest.raises(PolicyInputError):
        evaluate_policy(make_input(**{field: value}), make_config())


@pytest.mark.parametrize("value", ["false", "", 0, 1])
def test_fan_available_rejects_non_bool(value: object) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(make_input(fan_available=value), make_config())


@pytest.mark.parametrize("value", [True, False, None])
def test_fan_available_accepts_bool_or_none(value: object) -> None:
    decision = evaluate_policy(make_input(fan_available=value), make_config())
    assert decision.state is PolicyState.NORMAL
    assert decision.actuation_intent is ActuationIntent.HOLD


# ---------------------------------------------------------------------------
# Direct SAFE_LOCAL exit evaluation (no preceding _validate_input)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("field", "requirement"), EXIT_TRUST_REQUIREMENTS)
@pytest.mark.parametrize("value", ["false", 0])
def test_safe_local_exit_fails_closed_on_malformed_trust_flags(
    field: str, requirement: str, value: object
) -> None:
    ok, missing = safe_local_exit_status(
        make_input(remote=make_remote(**{field: value})), make_config()
    )
    assert ok is False
    assert requirement in missing


@pytest.mark.parametrize("value", ["false", "", 0, None])
def test_safe_local_exit_fails_closed_on_malformed_stale_flag(
    value: object,
) -> None:
    ok, missing = safe_local_exit_status(
        make_input(remote=make_remote(stale_command_pending=value)),
        make_config(),
    )
    assert ok is False
    assert "no_stale_command" in missing


@pytest.mark.parametrize("field", POLICY_SAFETY_FLAGS)
@pytest.mark.parametrize("value", ["", 0])
def test_safe_local_exit_fails_closed_on_malformed_fault_flags(
    field: str, value: object
) -> None:
    ok, missing = safe_local_exit_status(
        make_input(**{field: value}), make_config()
    )
    assert ok is False
    assert "no_critical_fault" in missing


def test_safe_local_exit_still_opens_for_valid_booleans() -> None:
    assert safe_local_exit_status(make_input(), make_config()) == (True, ())


# ---------------------------------------------------------------------------
# LocalSafetyEvidence booleans
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("field", ["active_fault", "hardware_safety_condition"])
@pytest.mark.parametrize("value", ["false", "", 0])
def test_malformed_evidence_safety_flags(
    field: str, value: object
) -> None:
    decision = _decide(make_evidence(**{field: value}))
    assert decision.status is AckStatus.INVALID_STATE
    assert decision.reason_code is ReasonCode.COMMAND_SAFETY_BLOCKED
    assert decision.may_actuate is False
    assert decision.actuation_intent is ActuationIntent.HOLD


@pytest.mark.parametrize("value", ["false", "", 0, 1])
def test_malformed_evidence_fan_available(value: object) -> None:
    decision = _decide(make_evidence(fan_available=value))
    assert decision.status is AckStatus.INVALID_STATE
    assert decision.reason_code is ReasonCode.COMMAND_SAFETY_BLOCKED
    assert decision.may_actuate is False


@pytest.mark.parametrize("value", [True, False, None])
def test_valid_evidence_fan_available_preserves_off(value: object) -> None:
    # OFF remains the recognized safe direction; only the evidence type is
    # checked, not a new state rule.
    decision = _decide(
        make_evidence(fan_available=value), action=CoolingState.OFF
    )
    assert decision.status is AckStatus.ACCEPTED
    assert decision.actuation_intent is ActuationIntent.OFF


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("active_fault", ""),
        ("hardware_safety_condition", 0),
        ("fan_available", "false"),
    ],
)
def test_malformed_evidence_bools_reject_off(
    field: str, value: object
) -> None:
    decision = _decide(
        make_evidence(**{field: value}), action=CoolingState.OFF
    )
    assert decision.status is AckStatus.INVALID_STATE
    assert decision.reason_code is ReasonCode.COMMAND_SAFETY_BLOCKED
    assert decision.may_actuate is False
