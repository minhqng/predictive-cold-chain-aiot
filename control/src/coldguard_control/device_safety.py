"""Device/actuator safety input contract (Member D, W04).

This module validates the *state the device reports about its own output
stage* before a decision may energize the TEC. It is intentionally pure: it
does not read GPIO, PZEM, sensors or firmware state, and it never actuates.
Member A supplies the physical state fields and the characterized duty ceiling;
Member D owns the rules that decide whether that state is legal to energize.

The contract encodes the W04 checklist (05D D-W04-02):

```text
boot/reset -> OFF, never an automatic ON
at most one H-bridge direction active
enable must be asserted before an ON request
fan/heat-rejection path must be confirmed before an ON request
duty must be a characterized per-mille value inside the allowed ceiling
unexpected drive while OFF is an electrical anomaly, not "probably idle"
```

Missing evidence is not healthy. An unresolved duty ceiling, an unknown fan
state or an incomplete boot all fail closed. No numeric limit is defined here;
the allowed ceiling is an input from Member A's characterization.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import CoolingState, ReasonCode


class DeviceSafetyInputError(ValueError):
    """Raised when the reported output-stage state is malformed."""


@dataclass(frozen=True, slots=True)
class ActuatorSafetyFinding:
    """One reason the reported state cannot authorize energization."""

    reason_code: ReasonCode
    detail: str
    critical: bool = False


@dataclass(frozen=True, slots=True)
class ActuatorSafetyDecision:
    """Deterministic safety verdict for one reported output-stage state."""

    may_apply: bool
    safe_to_energize: bool
    findings: tuple[ActuatorSafetyFinding, ...] = field(default_factory=tuple)

    @property
    def critical_violation(self) -> bool:
        return any(finding.critical for finding in self.findings)

    @property
    def safe_off_recommended(self) -> bool:
        return self.critical_violation


@dataclass(frozen=True, slots=True)
class ActuatorSafetyState:
    """Output-stage state as reported by the device (A -> D contract).

    ``commanded_cooling`` is the request being judged. ``applied_cooling`` and
    the drive flags are what the output stage reports, which may lag the
    request; they are never derived from the request.
    """

    boot_complete: bool
    reset_asserted: bool
    enable_asserted: bool
    forward_drive_active: bool
    reverse_drive_active: bool
    fan_available: bool | None
    applied_cooling: CoolingState
    commanded_cooling: CoolingState
    duty_permille: int | None
    allowed_duty_max_permille: int | None


def _require_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise DeviceSafetyInputError(
            f"{name} must be a boolean, "
            f"got {value!r} ({type(value).__name__})"
        )


def _require_cooling(name: str, value: object) -> None:
    if not isinstance(value, CoolingState):
        raise DeviceSafetyInputError(
            f"{name} must be a CoolingState member, "
            f"got {value!r} ({type(value).__name__})"
        )


def _require_permille(name: str, value: object, *, optional: bool) -> None:
    if value is None and optional:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise DeviceSafetyInputError(f"{name} must be an integer per-mille value")
    if not 0 <= value <= 1000:
        raise DeviceSafetyInputError(
            f"{name} must be within 0..1000 per-mille"
        )


def _validate(state: ActuatorSafetyState) -> None:
    _require_bool("boot_complete", state.boot_complete)
    _require_bool("reset_asserted", state.reset_asserted)
    _require_bool("enable_asserted", state.enable_asserted)
    _require_bool("forward_drive_active", state.forward_drive_active)
    _require_bool("reverse_drive_active", state.reverse_drive_active)
    if state.fan_available is not None:
        _require_bool("fan_available", state.fan_available)
    _require_cooling("applied_cooling", state.applied_cooling)
    _require_cooling("commanded_cooling", state.commanded_cooling)
    _require_permille("duty_permille", state.duty_permille, optional=True)
    _require_permille(
        "allowed_duty_max_permille",
        state.allowed_duty_max_permille,
        optional=True,
    )


def check_actuator_safety(state: ActuatorSafetyState) -> ActuatorSafetyDecision:
    """Return the deterministic safety verdict for a reported output state.

    The first blocking condition does not short-circuit the rest: all findings
    are returned so the audit record states every violated invariant.
    """
    _validate(state)

    findings: list[ActuatorSafetyFinding] = []
    any_drive = state.forward_drive_active or state.reverse_drive_active

    if state.forward_drive_active and state.reverse_drive_active:
        findings.append(
            ActuatorSafetyFinding(
                reason_code=ReasonCode.CONTROL_ELECTRICAL_ANOMALY,
                detail=(
                    "both H-bridge directions are active at once; the output "
                    "stage is in an invalid drive state"
                ),
                critical=True,
            )
        )

    if state.reset_asserted and (any_drive or state.applied_cooling is CoolingState.ON):
        findings.append(
            ActuatorSafetyFinding(
                reason_code=ReasonCode.CONTROL_ELECTRICAL_ANOMALY,
                detail=(
                    "reset is asserted while the output stage reports drive or "
                    "applied ON; reset must hold the actuator OFF"
                ),
                critical=True,
            )
        )

    if state.applied_cooling is CoolingState.OFF and any_drive:
        findings.append(
            ActuatorSafetyFinding(
                reason_code=ReasonCode.CONTROL_ELECTRICAL_ANOMALY,
                detail=(
                    "unexpected drive while the applied state is OFF; this is "
                    "an electrical anomaly, not an idle state (Doc 01 22.4/23.4)"
                ),
                critical=True,
            )
        )

    boot_ready = state.boot_complete and not state.reset_asserted
    if not boot_ready:
        findings.append(
            ActuatorSafetyFinding(
                reason_code=ReasonCode.COMMAND_SAFETY_BLOCKED,
                detail=(
                    "boot/self-test is incomplete or reset is asserted; no "
                    "energization is permitted before the safe boot state"
                ),
                critical=True,
            )
        )

    if state.commanded_cooling is CoolingState.ON:
        if not state.enable_asserted:
            findings.append(
                ActuatorSafetyFinding(
                    reason_code=ReasonCode.COMMAND_SAFETY_BLOCKED,
                    detail="enable is not asserted; ON is not a legal request",
                )
            )
        if state.fan_available is not True:
            findings.append(
                ActuatorSafetyFinding(
                    reason_code=ReasonCode.COMMAND_SAFETY_BLOCKED,
                    detail=(
                        "heat-rejection fan is not confirmed available; "
                        "UNKNOWN is not healthy (PHY-SAFE-002)"
                    ),
                )
            )
        if state.allowed_duty_max_permille is None:
            findings.append(
                ActuatorSafetyFinding(
                    reason_code=ReasonCode.COMMAND_SAFETY_BLOCKED,
                    detail=(
                        "allowed duty ceiling is unresolved; ON cannot be "
                        "authorized without a characterized range"
                    ),
                )
            )
        if state.duty_permille is None:
            findings.append(
                ActuatorSafetyFinding(
                    reason_code=ReasonCode.COMMAND_OUT_OF_RANGE,
                    detail="ON requires an explicit duty per-mille value",
                )
            )
        elif state.duty_permille <= 0:
            findings.append(
                ActuatorSafetyFinding(
                    reason_code=ReasonCode.COMMAND_OUT_OF_RANGE,
                    detail="ON with zero duty is not a legal energization",
                )
            )
        elif (
            state.allowed_duty_max_permille is not None
            and state.duty_permille > state.allowed_duty_max_permille
        ):
            findings.append(
                ActuatorSafetyFinding(
                    reason_code=ReasonCode.COMMAND_OUT_OF_RANGE,
                    detail=(
                        "duty exceeds the characterized allowed ceiling "
                        f"({state.allowed_duty_max_permille} per-mille)"
                    ),
                )
            )

    if state.commanded_cooling is CoolingState.OFF and state.duty_permille not in (
        None,
        0,
    ):
        findings.append(
            ActuatorSafetyFinding(
                reason_code=ReasonCode.COMMAND_OUT_OF_RANGE,
                detail="OFF must not request a non-zero duty",
            )
        )

    safe_to_energize = (
        state.commanded_cooling is CoolingState.ON
        and boot_ready
        and state.enable_asserted
        and state.fan_available is True
        and state.allowed_duty_max_permille is not None
        and state.duty_permille is not None
        and state.duty_permille > 0
        and state.duty_permille <= state.allowed_duty_max_permille
        and not (state.forward_drive_active and state.reverse_drive_active)
    )
    may_apply = not findings

    return ActuatorSafetyDecision(
        may_apply=may_apply,
        safe_to_energize=safe_to_energize and may_apply,
        findings=tuple(findings),
    )
