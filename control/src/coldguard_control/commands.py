"""Pure remote-command validator (Member D, W03 command matrix).

Wire shape follows the backend v0 command contract (``command_id``,
``device_id``, ``action``, ``duty``, ``created_at``, ``expires_at``,
``schema_version``) plus the authority/freshness evidence the validator needs.
The check order follows the Doc 02 section 63 decision logic:

```text
schema -> authorization -> device identity -> expiry -> duplicate
       -> range -> local safety -> state freshness
```

The validator is pure: it receives an explicit ``now_s``, the expected device
identity and the set of already-processed commands. It never publishes,
subscribes, queries a database, reads GPIO or actuates. An ``ACCEPTED`` result
means only "this layer found no rejection reason"; it is not physical proof
that an actuator changed state (Doc 02 section 32.2, SW-SAFE-008).

Reason-code mapping notes
-------------------------
* ``COMMAND_WRONG_DEVICE`` / ``AUTHORIZATION_FAILED`` are the 05D section 28
  supplementary vocabulary; Doc 02 section 58 has ``DEVICE_ID_MISMATCH`` for
  the same physical condition. This validator returns the 05D name and keeps
  the Doc 02 alias documented, rather than emitting two codes for one event.
* ``COMMAND_REJECTED_*`` (Doc 02 section 59) are retained in ``ReasonCode``
  for audit aggregation; per-rejection detail uses the Doc 02 section 58
  ``COMMAND_*`` name so a single event has a single canonical code.
* ``duty`` omitted means "plain ON/OFF". ``duty == 1.0`` is full-load ON and
  matches the v0 wire fixture's ``action.duty``. Any intermediate duty requires
  an explicitly characterized PWM range (Doc 01 section 24.3); with PWM
  disabled, W03 rejects duty values other than 1.0 instead of guessing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping

from .config import PolicyConfig
from .types import (
    AckStatus,
    ActuationIntent,
    CoolingState,
    DeviceMode,
    PhysicalVerificationState,
    PolicyState,
    QualityState,
    ReasonCode,
)

SUPPORTED_SCHEMA_VERSION = 1

# Device modes in which a remote control command is meaningful. BOOT and
# SELF_TEST are excluded by Doc 02 sections 2.2-2.3; SAFE_LOCAL must be exited
# through the verified exit sequence, not through a remote ON (05D section 19).
_REMOTE_MODES = frozenset(
    {
        DeviceMode.ONLINE_NORMAL,
        DeviceMode.ONLINE_DEGRADED,
        DeviceMode.FAULT_LOCKOUT,
    }
)

_BLOCKING_POLICY_STATES = frozenset(
    {PolicyState.FAULT, PolicyState.FAULT_LOCKOUT}
)


class CommandSchemaError(ValueError):
    """The request cannot be interpreted as a schema-v1 command."""


@dataclass(frozen=True, slots=True)
class CommandRequest:
    """One remote command plus the evidence required to judge it.

    ``authorized`` is asserted by the authenticated backend path; this pure
    layer cannot re-verify credentials and must not be used as the sole
    authorization check. Backend authn/authz remains Member C/backend scope
    (Doc 04 section 6; Doc 05D section 28).
    """

    schema_version: int
    command_id: str
    device_id: str
    action: CoolingState
    created_at: float
    expires_at: float
    authorized: bool
    duty: float | None = None
    retain: bool = False


@dataclass(frozen=True, slots=True)
class LocalSafetyEvidence:
    """Local state answering "is it physically safe to energize now?"."""

    device_mode: DeviceMode
    policy_state: PolicyState
    thermal_quality: QualityState
    thermal_age_s: float | None
    fan_available: bool | None
    active_fault: bool = False
    hardware_safety_condition: bool = False
    # The device may have no synchronized wall clock. Absolute command expiry
    # is only evaluable when this is explicitly known to be true; absence is
    # not "probably synchronized" (A-W06 handoff; Doc 02 section 31.1).
    clock_synchronized: bool = False


@dataclass(frozen=True, slots=True)
class CommandDecision:
    """Deterministic validation result."""

    command_id: str | None
    status: AckStatus
    reason_code: ReasonCode | None
    actuation_intent: ActuationIntent
    detail: str
    canonical_status: AckStatus | None = None
    checks_passed: tuple[str, ...] = field(default_factory=tuple)

    @property
    def accepted(self) -> bool:
        """True only when the request passed every check.

        ``DUPLICATE_CANONICAL`` is deliberately not ``accepted``: a duplicate
        never causes a second actuation (Doc 02 sections 31.4, 32.1).
        """

        return self.status is AckStatus.ACCEPTED

    @property
    def may_actuate(self) -> bool:
        return self.status is AckStatus.ACCEPTED


def _reject(
    request: CommandRequest,
    *,
    status: AckStatus,
    reason: ReasonCode,
    detail: str,
    passed: tuple[str, ...],
) -> CommandDecision:
    return CommandDecision(
        command_id=request.command_id,
        status=status,
        reason_code=reason,
        actuation_intent=ActuationIntent.HOLD,
        detail=detail,
        checks_passed=passed,
    )


def _validate_schema(request: CommandRequest) -> None:
    if not isinstance(request.schema_version, int) or isinstance(
        request.schema_version, bool
    ):
        raise CommandSchemaError("schema_version must be an integer")
    if request.schema_version != SUPPORTED_SCHEMA_VERSION:
        raise CommandSchemaError(
            f"unsupported schema_version {request.schema_version!r}; "
            f"supported: {SUPPORTED_SCHEMA_VERSION}"
        )
    if not isinstance(request.authorized, bool):
        raise CommandSchemaError("authorized must be a boolean")
    if not isinstance(request.retain, bool):
        raise CommandSchemaError("retain must be a boolean")
    if not isinstance(request.command_id, str) or not (
        request.command_id.strip()
    ):
        raise CommandSchemaError("command_id must be a non-empty string")
    if not isinstance(request.device_id, str) or not (
        request.device_id.strip()
    ):
        raise CommandSchemaError("device_id must be a non-empty string")
    if not isinstance(request.action, CoolingState):
        raise CommandSchemaError("action must be CoolingState.ON or .OFF")
    for name, value in (
        ("created_at", request.created_at),
        ("expires_at", request.expires_at),
    ):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise CommandSchemaError(f"{name} must be a number")
        if not math.isfinite(float(value)):
            raise CommandSchemaError(f"{name} must be finite")
    if request.expires_at <= request.created_at:
        raise CommandSchemaError("expires_at must be later than created_at")
    if request.retain:
        # Doc 02 retains last state but forbids retained command delivery:
        # replaying an old retained command would be a stale-actuation path.
        raise CommandSchemaError("retained commands are not allowed")


def _validate_ttl(
    request: CommandRequest, cfg: PolicyConfig, now_s: float
) -> tuple[AckStatus, ReasonCode, str] | None:
    """Apply the optional W04 candidate TTL bounds.

    ``expires_at`` remains authoritative regardless of these bounds. When a
    bound is configured, it adds two protections against a long-lived remote
    intent:

    * age since issue time (never since device receipt) must be within
      ``command_max_age_s``;
    * the declared validity window must be within ``command_max_ttl_s``.

    ``None`` means the corresponding number has not been characterized yet;
    the check is skipped and the evidence record must say so. No default value
    is substituted.
    """
    age_s = float(now_s) - float(request.created_at)
    max_age = cfg.command_max_age_s
    if max_age is not None and age_s > float(max_age):
        return (
            AckStatus.EXPIRED,
            ReasonCode.COMMAND_EXPIRED,
            (
                "command age since created_at exceeds the configured maximum "
                f"({age_s:.3f} s > {max_age} s); the freshness clock starts at "
                "issue time, not device receipt"
            ),
        )

    window_s = float(request.expires_at) - float(request.created_at)
    max_ttl = cfg.command_max_ttl_s
    if max_ttl is not None and window_s > float(max_ttl):
        return (
            AckStatus.OUT_OF_RANGE,
            ReasonCode.COMMAND_OUT_OF_RANGE,
            (
                "declared command validity window exceeds the configured TTL "
                f"({window_s:.3f} s > {max_ttl} s)"
            ),
        )
    return None


def _validate_range(
    request: CommandRequest, cfg: PolicyConfig
) -> str | None:
    """Return a rejection detail, or ``None`` when the action is legal."""
    duty = request.duty
    if duty is not None and (
        isinstance(duty, bool)
        or not isinstance(duty, (int, float))
        or not math.isfinite(float(duty))
    ):
        return "duty must be a finite number or omitted"

    if request.action is CoolingState.OFF:
        if duty is not None and duty != 0.0:
            return "OFF command must not request a non-zero duty"
        return None

    if not cfg.allow_pwm_duty:
        if duty is not None and duty != 1.0:
            return (
                "duty other than 1.0 requires a characterized PWM range; "
                "this policy configuration has PWM disabled"
            )
        return None

    assert cfg.allowed_duty_min is not None
    assert cfg.allowed_duty_max is not None
    if duty is None:
        return "PWM-enabled configuration requires an explicit duty for ON"
    if not cfg.allowed_duty_min <= duty <= cfg.allowed_duty_max:
        return (
            "duty outside the characterized range "
            f"[{cfg.allowed_duty_min}, {cfg.allowed_duty_max}]"
        )
    return None


def _evidence_type_problem(evidence: LocalSafetyEvidence) -> str | None:
    """Return a description when safety evidence is not well typed.

    ``DeviceMode``/``PolicyState``/``QualityState`` derive from ``str``/``Enum``,
    so raw strings compare equal by value while identity/membership checks in
    this validator are not interchangeable. An unvalidated raw value could
    therefore skip the FAULT/LOCKOUT gate or the remote-mode gate. Boolean
    fields have the mirror problem: the truthy string ``"false"`` would count
    as an asserted fault/stop, while an empty string or ``0`` would silently
    clear one. Such evidence is untrusted: no command (including OFF) may be
    accepted from an unknown state. ``None`` means the evidence is well typed.
    """
    for field_name, enum_type in (
        ("device_mode", DeviceMode),
        ("policy_state", PolicyState),
        ("thermal_quality", QualityState),
    ):
        value = getattr(evidence, field_name)
        if not isinstance(value, enum_type):
            return (
                f"{field_name} must be a {enum_type.__name__} member, "
                f"got {value!r} ({type(value).__name__})"
            )

    for field_name in (
        "active_fault",
        "hardware_safety_condition",
        "clock_synchronized",
    ):
        value = getattr(evidence, field_name)
        if not isinstance(value, bool):
            return (
                f"{field_name} must be a boolean, "
                f"got {value!r} ({type(value).__name__})"
            )

    fan = evidence.fan_available
    if fan is not None and not isinstance(fan, bool):
        return (
            "fan_available must be a boolean or None, "
            f"got {fan!r} ({type(fan).__name__})"
        )
    return None


def validate_command(
    request: CommandRequest,
    evidence: LocalSafetyEvidence,
    cfg: PolicyConfig,
    *,
    now_s: float,
    expected_device_id: str,
    processed: Mapping[str, AckStatus],
) -> CommandDecision:
    """Validate one command against the W03 command decision matrix.

    Check order is normative (Doc 02 section 63). The first failing check wins
    so the returned reason is stable and auditable.
    """
    if isinstance(now_s, bool) or not isinstance(now_s, (int, float)):
        raise ValueError("now_s must be a finite number")
    if not math.isfinite(float(now_s)):
        raise ValueError("now_s must be a finite number")
    if not expected_device_id.strip():
        raise ValueError("expected_device_id must be non-empty")

    passed: list[str] = []

    # 1. Schema ------------------------------------------------------------
    try:
        _validate_schema(request)
    except CommandSchemaError as exc:
        return _reject(
            request,
            status=AckStatus.REJECTED,
            reason=ReasonCode.INVALID_JSON,
            detail=f"schema: {exc}",
            passed=tuple(passed),
        )
    passed.append("schema")

    # 2. Authorization -----------------------------------------------------
    if not request.authorized:
        return _reject(
            request,
            status=AckStatus.REJECTED,
            reason=ReasonCode.AUTHORIZATION_FAILED,
            detail="command path did not assert authenticated authorization",
            passed=tuple(passed),
        )
    passed.append("authorization")

    # 3. Device identity ---------------------------------------------------
    if request.device_id != expected_device_id:
        return _reject(
            request,
            status=AckStatus.REJECTED,
            reason=ReasonCode.COMMAND_WRONG_DEVICE,
            detail=(
                "command targets another device "
                f"(Doc 02 alias: {ReasonCode.DEVICE_ID_MISMATCH.value})"
            ),
            passed=tuple(passed),
        )
    passed.append("device_identity")

    # 4. Expiry / clock ----------------------------------------------------
    # When the device clock is not synchronized, absolute expiry cannot be
    # evaluated. This is a safety block, not an expiry verdict: the device
    # cannot prove the command is fresh, so it must not actuate (A-W06 handoff;
    # Doc 02 section 31.1).
    if not evidence.clock_synchronized:
        return _reject(
            request,
            status=AckStatus.SAFETY_BLOCKED,
            reason=ReasonCode.COMMAND_SAFETY_BLOCKED,
            detail=(
                "device clock is not synchronized; absolute command expiry "
                "cannot be evaluated; local protections remain available"
            ),
            passed=tuple(passed),
        )
    if float(request.created_at) > float(now_s) + cfg.command_max_future_skew_s:
        return _reject(
            request,
            status=AckStatus.REJECTED,
            reason=ReasonCode.INVALID_JSON,
            detail="created_at is implausibly in the future (clock/schema)",
            passed=tuple(passed),
        )
    if float(now_s) >= float(request.expires_at):
        return _reject(
            request,
            status=AckStatus.EXPIRED,
            reason=ReasonCode.COMMAND_EXPIRED,
            detail="command expired before validation",
            passed=tuple(passed),
        )
    ttl_result = _validate_ttl(request, cfg, float(now_s))
    if ttl_result is not None:
        status, reason, detail = ttl_result
        return _reject(
            request,
            status=status,
            reason=reason,
            detail=detail,
            passed=tuple(passed),
        )
    passed.append("expiry")

    # 5. Duplicate ---------------------------------------------------------
    canonical = processed.get(request.command_id)
    if canonical is not None:
        return CommandDecision(
            command_id=request.command_id,
            status=AckStatus.DUPLICATE_CANONICAL,
            reason_code=ReasonCode.COMMAND_DUPLICATE,
            actuation_intent=ActuationIntent.HOLD,
            detail=(
                "command_id already processed; returning canonical status "
                "without re-actuating"
            ),
            canonical_status=canonical,
            checks_passed=tuple(passed),
        )
    passed.append("duplicate")

    # 6. Range -------------------------------------------------------------
    range_problem = _validate_range(request, cfg)
    if range_problem is not None:
        return _reject(
            request,
            status=AckStatus.OUT_OF_RANGE,
            reason=ReasonCode.COMMAND_OUT_OF_RANGE,
            detail=range_problem,
            passed=tuple(passed),
        )
    passed.append("range")

    # Evidence vocabularies and safety booleans are validated before the first
    # safety/mode use so a look-alike raw value cannot skip a gate. Malformed
    # state is rejected for both directions: the contract only permits OFF in a
    # *recognized* FAULT_LOCKOUT/plain-fault state, not in an unknown one.
    evidence_problem = _evidence_type_problem(evidence)
    if evidence_problem is not None:
        return _reject(
            request,
            status=AckStatus.INVALID_STATE,
            reason=ReasonCode.COMMAND_SAFETY_BLOCKED,
            detail=(
                "local safety evidence is malformed "
                f"({evidence_problem}); no command, including OFF, is "
                "accepted on an unrecognized state"
            ),
            passed=tuple(passed),
        )

    # 7. Local safety ------------------------------------------------------
    intent = (
        ActuationIntent.ON
        if request.action is CoolingState.ON
        else ActuationIntent.OFF
    )

    if request.action is CoolingState.ON:
        if evidence.hardware_safety_condition:
            return _reject(
                request,
                status=AckStatus.SAFETY_BLOCKED,
                reason=ReasonCode.COMMAND_SAFETY_BLOCKED,
                detail=(
                    "characterized hardware safety stop condition asserted; "
                    "OFF is the only legal direction (PHY-SAFE-009)"
                ),
                passed=tuple(passed),
            )
        if evidence.active_fault or (
            evidence.policy_state in _BLOCKING_POLICY_STATES
        ):
            return _reject(
                request,
                status=AckStatus.SAFETY_BLOCKED,
                reason=ReasonCode.COMMAND_SAFETY_BLOCKED,
                detail=(
                    "active fault/lockout blocks new energization "
                    "(Doc 02 section 2.7)"
                ),
                passed=tuple(passed),
            )
        if evidence.fan_available is not True:
            # None/UNKNOWN is not healthy: PHY-SAFE-002 requires the heat
            # rejection path to be available before energizing the TEC.
            return _reject(
                request,
                status=AckStatus.SAFETY_BLOCKED,
                reason=ReasonCode.COMMAND_SAFETY_BLOCKED,
                detail=(
                    "heat-rejection fan is not confirmed available "
                    "(PHY-SAFE-002); UNKNOWN is not treated as healthy"
                ),
                passed=tuple(passed),
            )
        if evidence.thermal_quality in (
            QualityState.INVALID,
            QualityState.UNKNOWN,
        ):
            return _reject(
                request,
                status=AckStatus.SAFETY_BLOCKED,
                reason=ReasonCode.COMMAND_SAFETY_BLOCKED,
                detail=(
                    "critical thermal state invalid/unknown; energization "
                    "cannot be verified safe (PHY-SAFE-008)"
                ),
                passed=tuple(passed),
            )
    passed.append("safety")

    # 8. State / mode freshness (last: safety direction is already known) --
    if evidence.device_mode not in _REMOTE_MODES:
        return _reject(
            request,
            status=AckStatus.INVALID_STATE,
            reason=ReasonCode.COMMAND_SAFETY_BLOCKED,
            detail=(
                "device mode does not accept remote control commands; "
                "SAFE_LOCAL requires the verified exit sequence "
                "(05D section 19)"
            ),
            passed=tuple(passed),
        )
    if evidence.device_mode is DeviceMode.FAULT_LOCKOUT and (
        request.action is CoolingState.ON
    ):
        return _reject(
            request,
            status=AckStatus.INVALID_STATE,
            reason=ReasonCode.COMMAND_SAFETY_BLOCKED,
            detail="FAULT_LOCKOUT accepts only the safe OFF direction",
            passed=tuple(passed),
        )
    age = evidence.thermal_age_s
    if (
        age is None
        or isinstance(age, bool)
        or not isinstance(age, (int, float))
        or not math.isfinite(float(age))
        or float(age) < 0.0
        or float(age) > cfg.thermal_max_age_s
    ):
        return _reject(
            request,
            status=AckStatus.INVALID_STATE,
            reason=ReasonCode.COMMAND_STATE_STALE,
            detail=(
                "local state is missing, non-finite/negative, or older than "
                "the configured freshness bound; commands are not applied to "
                "invalid or stale state"
            ),
            passed=tuple(passed),
        )
    passed.append("state_freshness")

    return CommandDecision(
        command_id=request.command_id,
        status=AckStatus.ACCEPTED,
        reason_code=ReasonCode.OK,
        actuation_intent=intent,
        detail=(
            "all command checks passed at this layer; physical verification "
            "and ACK reporting remain outside W03"
        ),
        checks_passed=tuple(passed),
    )
