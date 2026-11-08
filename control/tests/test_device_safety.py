"""W04 device/actuator safety input contract tests (05D D-W04-02).

These tests prove the device-side safety checklist:
* boot/reset default OFF (no automatic ON at boot);
* at most one H-bridge direction active;
* enable must be asserted before ON;
* fan must be confirmed before ON (UNKNOWN is not healthy);
* duty must be inside characterized range;
* unexpected drive while OFF is an electrical anomaly.
"""

from __future__ import annotations

import pytest

from coldguard_control import (
    ActuatorSafetyDecision,
    ActuatorSafetyState,
    CoolingState,
    DeviceSafetyInputError,
    ReasonCode,
    check_actuator_safety,
)


def _state(
    boot_complete: bool = True,
    reset_asserted: bool = False,
    enable_asserted: bool = True,
    forward_drive_active: bool = False,
    reverse_drive_active: bool = False,
    fan_available: bool | None = True,
    applied_cooling: CoolingState = CoolingState.OFF,
    commanded_cooling: CoolingState = CoolingState.OFF,
    duty_permille: int | None = None,
    allowed_duty_max_permille: int | None = 500,
) -> ActuatorSafetyState:
    return ActuatorSafetyState(
        boot_complete=boot_complete,
        reset_asserted=reset_asserted,
        enable_asserted=enable_asserted,
        forward_drive_active=forward_drive_active,
        reverse_drive_active=reverse_drive_active,
        fan_available=fan_available,
        applied_cooling=applied_cooling,
        commanded_cooling=commanded_cooling,
        duty_permille=duty_permille,
        allowed_duty_max_permille=allowed_duty_max_permille,
    )


def test_boot_incomplete_blocks_energization() -> None:
    result = check_actuator_safety(_state(boot_complete=False))

    assert result.safe_to_energize is False
    assert result.critical_violation is True
    assert any("boot" in f.detail.lower() for f in result.findings)


def test_reset_asserted_blocks_energization() -> None:
    result = check_actuator_safety(_state(reset_asserted=True))

    assert result.safe_to_energize is False
    assert result.critical_violation is True


def test_both_hbridge_directions_is_critical_anomaly() -> None:
    result = check_actuator_safety(
        _state(
            forward_drive_active=True,
            reverse_drive_active=True,
            commanded_cooling=CoolingState.ON,
            duty_permille=250,
        )
    )

    assert result.critical_violation is True
    assert any(
        f.reason_code is ReasonCode.CONTROL_ELECTRICAL_ANOMALY
        for f in result.findings
    )
    assert any("both" in f.detail.lower() for f in result.findings)


def test_enable_not_asserted_blocks_on() -> None:
    result = check_actuator_safety(
        _state(
            enable_asserted=False,
            commanded_cooling=CoolingState.ON,
            duty_permille=250,
        )
    )

    assert result.safe_to_energize is False
    assert any("enable" in f.detail.lower() for f in result.findings)


def test_fan_unknown_is_not_healthy() -> None:
    result = check_actuator_safety(
        _state(
            fan_available=None,
            commanded_cooling=CoolingState.ON,
            duty_permille=250,
        )
    )

    assert result.safe_to_energize is False
    assert any("fan" in f.detail.lower() for f in result.findings)
    assert any("UNKNOWN is not healthy" in f.detail for f in result.findings)


def test_fan_unavailable_blocks_on() -> None:
    result = check_actuator_safety(
        _state(
            fan_available=False,
            commanded_cooling=CoolingState.ON,
            duty_permille=250,
        )
    )

    assert result.safe_to_energize is False


def test_unresolved_duty_ceiling_blocks_on() -> None:
    result = check_actuator_safety(
        _state(
            allowed_duty_max_permille=None,
            commanded_cooling=CoolingState.ON,
            duty_permille=250,
        )
    )

    assert result.safe_to_energize is False
    assert any("ceiling" in f.detail.lower() for f in result.findings)


def test_on_without_duty_is_out_of_range() -> None:
    result = check_actuator_safety(
        _state(
            commanded_cooling=CoolingState.ON,
            duty_permille=None,
        )
    )

    assert result.safe_to_energize is False
    assert any(
        f.reason_code is ReasonCode.COMMAND_OUT_OF_RANGE for f in result.findings
    )


def test_on_with_zero_duty_is_out_of_range() -> None:
    result = check_actuator_safety(
        _state(
            commanded_cooling=CoolingState.ON,
            duty_permille=0,
        )
    )

    assert result.safe_to_energize is False
    assert any("zero" in f.detail.lower() for f in result.findings)


def test_duty_above_ceiling_is_out_of_range() -> None:
    result = check_actuator_safety(
        _state(
            commanded_cooling=CoolingState.ON,
            duty_permille=600,
            allowed_duty_max_permille=500,
        )
    )

    assert result.safe_to_energize is False
    assert any(
        f.reason_code is ReasonCode.COMMAND_OUT_OF_RANGE for f in result.findings
    )


def test_off_with_nonzero_duty_is_out_of_range() -> None:
    result = check_actuator_safety(
        _state(
            commanded_cooling=CoolingState.OFF,
            duty_permille=250,
        )
    )

    assert result.safe_to_energize is False
    assert any(
        f.reason_code is ReasonCode.COMMAND_OUT_OF_RANGE for f in result.findings
    )


def test_valid_on_is_safe_to_energize() -> None:
    result = check_actuator_safety(
        _state(
            commanded_cooling=CoolingState.ON,
            duty_permille=250,
            allowed_duty_max_permille=500,
        )
    )

    assert result.safe_to_energize is True
    assert result.may_apply is True
    assert result.findings == ()


def test_valid_off_is_safe() -> None:
    result = check_actuator_safety(
        _state(
            commanded_cooling=CoolingState.OFF,
            duty_permille=0,
        )
    )

    assert result.may_apply is True
    assert result.safe_to_energize is False


def test_drive_while_off_is_anomaly() -> None:
    result = check_actuator_safety(
        _state(
            applied_cooling=CoolingState.OFF,
            forward_drive_active=True,
        )
    )

    assert result.critical_violation is True
    assert any(
        f.reason_code is ReasonCode.CONTROL_ELECTRICAL_ANOMALY
        for f in result.findings
    )
    assert any("anomaly" in f.detail.lower() for f in result.findings)


def test_non_boolean_boot_is_rejected() -> None:
    with pytest.raises(DeviceSafetyInputError, match="must be a boolean"):
        check_actuator_safety(_state(boot_complete="true"))


def test_non_enum_cooling_is_rejected() -> None:
    with pytest.raises(DeviceSafetyInputError, match="must be a CoolingState"):
        check_actuator_safety(_state(commanded_cooling="ON"))


def test_duty_out_of_permille_range_is_rejected() -> None:
    with pytest.raises(DeviceSafetyInputError, match="0..1000"):
        check_actuator_safety(_state(duty_permille=1500))


def test_all_findings_returned_not_short_circuited() -> None:
    result = check_actuator_safety(
        _state(
            boot_complete=False,
            reset_asserted=True,
            forward_drive_active=True,
            reverse_drive_active=True,
            enable_asserted=False,
            fan_available=None,
            commanded_cooling=CoolingState.ON,
            duty_permille=600,
            allowed_duty_max_permille=500,
        )
    )

    assert len(result.findings) >= 5
    assert result.critical_violation is True
