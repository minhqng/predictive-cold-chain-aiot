"""Pure ColdGuard policy and safety gate (Member D, W03).

Authority and decision order come from Doc 00 section 2.7 / Doc 02 section 22
and the Doc 05D section 7 safety-gate concept:

```text
hard safety fault
  -> validate physical-state quality/freshness
  -> critical thermal protection from usable fresh state (Controller A dominates)
  -> remote path untrusted (SAFE_LOCAL regime)
  -> predictive intervention (only when the predictive contract exists)
  -> normal reactive behavior
```

The module is a pure function of its input plus an explicit, versioned
configuration. It imports no MQTT, database, GPIO, FastAPI or hardware code,
keeps no clock of its own (the caller supplies ages/elapsed values), and
performs no actuation. It returns a ``PolicyDecision`` only; turning a
decision into a command/actuation belongs to later weeks and other layers
(Doc 02 sections 21-23; Doc 04 W03; Doc 05D D-W03-01).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import PolicyConfig
from .types import (
    ActuationIntent,
    ControllerId,
    CoolingState,
    DeviceMode,
    ModelHealth,
    PolicyState,
    QualityState,
    ReasonCode,
)


class PolicyInputError(ValueError):
    """Raised when an input contradicts the documented semantics."""


class PolicyPreconditionError(RuntimeError):
    """Policy evaluation is undefined for this device mode."""


@dataclass(frozen=True, slots=True)
class ThermalView:
    """Locally observed thermal state for one evaluation.

    ``t_representative_c`` must already be the configured representation
    (Doc 01 sections 20.5, 37); this module does not choose between T1/T2/T3.
    Values with ``INVALID``/``UNKNOWN`` quality must not be supplied: Doc 01
    PHY-DS-004 forbids substituting 0, previous or interpolated values.
    """

    quality: QualityState
    t_representative_c: float | None
    age_s: float | None


@dataclass(frozen=True, slots=True)
class PredictionView:
    """Fresh or stale predictive warning input (advisory only)."""

    health: ModelHealth
    model_version: str
    feature_version: str
    risk_score: float | None
    age_s: float | None
    horizon_s: float | None
    above_preemptive_s: float | None


@dataclass(frozen=True, slots=True)
class RemotePathView:
    """Trust/freshness of the remote control path.

    ``network_stable_s`` is how long connectivity has been continuously
    stable; SAFE_LOCAL exit requires it to reach the configured window, so a
    reconnect alone never re-enables remote trust (Doc 02 sections 31.3, 38;
    05D section 19).
    """

    broker_connected: bool
    broker_offline_s: float
    backend_state_synced: bool
    backend_state_age_s: float
    state_sync_trusted: bool
    remote_command_path_trusted: bool
    network_stable_s: float
    stale_command_pending: bool


@dataclass(frozen=True, slots=True)
class PolicyInput:
    """Structured policy snapshot (Doc 02 section 21)."""

    device_mode: DeviceMode
    thermal: ThermalView
    applied_cooling: CoolingState
    remote: RemotePathView
    current_state: PolicyState | None = None
    fan_available: bool | None = None
    electrical_quality: QualityState = QualityState.UNKNOWN
    door_state: str = "UNKNOWN"
    prediction: PredictionView | None = None
    fault_active: bool = False
    fault_reason: ReasonCode | None = None
    control_electrical_anomaly: bool = False
    hardware_safety_condition: bool = False


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Deterministic policy result. Never an actuator command.

    ``actuation_intent`` is what a future command/actuation layer is allowed to
    consider; W03 does not publish, validate at the device, or actuate.
    """

    policy_version: str
    state: PolicyState
    actuation_intent: ActuationIntent
    controller_id: ControllerId
    reason_code: ReasonCode | None
    reason_detail: str
    predictive_blocked: bool
    degraded_sensing: bool
    safe_local_exit_missing: tuple[str, ...] = ()
    transition: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_safe_local(self) -> bool:
        return self.state is PolicyState.SAFE_LOCAL


# Reason codes that indicate physical energization/actuation cannot be
# guaranteed safe. Doc 02 section 2.7 lists actuator electrical anomaly and
# hardware safety conditions under FAULT_LOCKOUT; Doc 01 sections 22.4/23.4
# classify unexpected OFF current as a high-severity anomaly.
_LOCKOUT_REASONS = frozenset({ReasonCode.CONTROL_ELECTRICAL_ANOMALY})


def _require_enum(name: str, value: object, enum_type: type) -> None:
    """Require an actual enum member, not a look-alike raw value.

    The state vocabularies derive from ``str``/``Enum``, so a raw string such
    as ``"FAULT_LOCKOUT"`` compares *equal by value* to the member while
    ``member is value`` remains false. Identity comparisons are used
    throughout this module, so an unvalidated raw string could bypass a gate
    (for example, skip the FAULT_LOCKOUT check and reach an ON decision).
    Validation therefore happens before any identity/state comparison and
    never coerces the value.
    """
    if not isinstance(value, enum_type):
        raise PolicyInputError(
            f"{name} must be a {enum_type.__name__} member, "
            f"got {value!r} ({type(value).__name__})"
        )


def _require_bool(name: str, value: object) -> None:
    """Require an actual ``bool``; truthy/falsy look-alikes are rejected."""
    if not isinstance(value, bool):
        raise PolicyInputError(
            f"{name} must be a boolean, "
            f"got {value!r} ({type(value).__name__})"
        )


def _require_bool_or_none(name: str, value: object) -> None:
    """Require ``bool`` or ``None``; other truthy/falsy values are rejected."""
    if value is not None and not isinstance(value, bool):
        raise PolicyInputError(
            f"{name} must be a boolean or None, "
            f"got {value!r} ({type(value).__name__})"
        )


def _require_finite(name: str, value: float | None) -> None:
    """Reject non-finite/bool numeric inputs that would fail open.

    ``None`` means "not supplied" and is left to the field's own requirement
    logic. A NaN age/duration makes every ``>``/``<=`` comparison false, so an
    unguarded check would treat it as trustworthy. ``bool`` is excluded because
    it is an ``int`` subclass.
    """
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyInputError(f"{name} must be a finite number")
    if not math.isfinite(float(value)):
        raise PolicyInputError(f"{name} must be a finite number")


def _validate_input(pi: PolicyInput, cfg: PolicyConfig) -> None:
    # Enum-typed fields are validated before any identity comparison: a raw
    # string with the same value is not the enum member and must not be
    # reinterpreted (Doc 02 sections 2.1/23; 05D sections 3/34).
    _require_enum("device_mode", pi.device_mode, DeviceMode)
    _require_enum("thermal.quality", pi.thermal.quality, QualityState)
    _require_enum("applied_cooling", pi.applied_cooling, CoolingState)
    _require_enum("electrical_quality", pi.electrical_quality, QualityState)
    if pi.current_state is not None:
        _require_enum("current_state", pi.current_state, PolicyState)
    if pi.fault_reason is not None:
        _require_enum("fault_reason", pi.fault_reason, ReasonCode)
    if pi.prediction is not None:
        _require_enum("prediction.health", pi.prediction.health, ModelHealth)

    _require_bool_or_none("fan_available", pi.fan_available)
    _require_bool("fault_active", pi.fault_active)
    _require_bool("control_electrical_anomaly", pi.control_electrical_anomaly)
    _require_bool(
        "hardware_safety_condition", pi.hardware_safety_condition
    )

    if pi.device_mode in (DeviceMode.BOOT, DeviceMode.SELF_TEST):
        raise PolicyPreconditionError(
            "policy evaluation is undefined before boot/self-test completes "
            "(Doc 02 sections 2.2-2.3); the device must hold actuator OFF"
        )

    thermal = pi.thermal
    if thermal.quality is QualityState.VALID:
        if thermal.t_representative_c is None or thermal.age_s is None:
            raise PolicyInputError(
                "VALID thermal quality requires a representative value and "
                "age"
            )
    elif thermal.quality in (QualityState.INVALID, QualityState.UNKNOWN):
        if thermal.t_representative_c is not None:
            raise PolicyInputError(
                "INVALID/UNKNOWN thermal quality cannot carry a usable value "
                "(Doc 01 PHY-DS-004)"
            )
    _require_finite("t_representative_c", thermal.t_representative_c)
    _require_finite("thermal age_s", thermal.age_s)
    if thermal.age_s is not None and thermal.age_s < 0:
        raise PolicyInputError("thermal age_s cannot be negative")

    pred = pi.prediction
    if pred is not None:
        _require_finite("risk_score", pred.risk_score)
        _require_finite("prediction age_s", pred.age_s)
        _require_finite("prediction horizon_s", pred.horizon_s)
        _require_finite(
            "above_preemptive_s", pred.above_preemptive_s
        )
        if pred.risk_score is not None and not 0.0 <= pred.risk_score <= 1.0:
            raise PolicyInputError("risk_score must be within [0, 1]")
        if pred.health is ModelHealth.READY:
            if pred.risk_score is None or pred.age_s is None:
                raise PolicyInputError(
                    "READY prediction requires risk_score and age_s"
                )
            if not pred.model_version.strip():
                raise PolicyInputError(
                    "READY prediction requires model_version"
                )
            if not pred.feature_version.strip():
                raise PolicyInputError(
                    "READY prediction requires feature_version"
                )
        if pred.age_s is not None and pred.age_s < 0:
            raise PolicyInputError("prediction age_s cannot be negative")
        if (
            pred.above_preemptive_s is not None
            and pred.above_preemptive_s < 0
        ):
            raise PolicyInputError(
                "above_preemptive_s cannot be negative"
            )

    remote = pi.remote
    _require_bool("broker_connected", remote.broker_connected)
    _require_bool("backend_state_synced", remote.backend_state_synced)
    _require_bool("state_sync_trusted", remote.state_sync_trusted)
    _require_bool(
        "remote_command_path_trusted", remote.remote_command_path_trusted
    )
    _require_bool("stale_command_pending", remote.stale_command_pending)
    _require_finite("broker_offline_s", remote.broker_offline_s)
    _require_finite("backend_state_age_s", remote.backend_state_age_s)
    _require_finite("network_stable_s", remote.network_stable_s)
    if remote.broker_offline_s < 0:
        raise PolicyInputError("broker_offline_s cannot be negative")
    if remote.backend_state_age_s < 0:
        raise PolicyInputError("backend_state_age_s cannot be negative")
    if remote.network_stable_s < 0:
        raise PolicyInputError("network_stable_s cannot be negative")

    if pi.door_state not in ("OPEN", "CLOSED", "UNKNOWN"):
        raise PolicyInputError(
            "door_state must be OPEN, CLOSED or UNKNOWN "
            "(Doc 01 section 17.7)"
        )


def _prediction_healthy(pi: PolicyInput, cfg: PolicyConfig) -> bool:
    pred = pi.prediction
    if pred is None or pred.health is not ModelHealth.READY:
        return False
    if pred.age_s is None:
        return False
    assert cfg.prediction_max_age_s is not None
    return pred.age_s <= cfg.prediction_max_age_s


def _remote_untrusted(
    pi: PolicyInput, cfg: PolicyConfig
) -> tuple[bool, ReasonCode | None, str]:
    """Return why the remote intelligence path cannot be trusted."""
    r = pi.remote
    if (not r.broker_connected) or (
        r.broker_offline_s > cfg.broker_offline_grace_s
    ):
        return (
            True,
            ReasonCode.NETWORK_UNAVAILABLE,
            "broker disconnected beyond grace",
        )
    if not r.backend_state_synced:
        return (
            True,
            ReasonCode.BACKEND_UNAVAILABLE,
            "backend state unavailable",
        )
    if r.backend_state_age_s > cfg.backend_state_max_age_s:
        return (
            True,
            ReasonCode.BACKEND_UNAVAILABLE,
            "backend state older than allowed",
        )
    if not r.state_sync_trusted:
        return (
            True,
            ReasonCode.BACKEND_UNAVAILABLE,
            "twin state synchronization not trustworthy",
        )
    if not r.remote_command_path_trusted:
        return (
            True,
            ReasonCode.BACKEND_UNAVAILABLE,
            "remote command path not trusted",
        )
    if cfg.predictive_enabled and not _prediction_healthy(pi, cfg):
        return (
            True,
            ReasonCode.AI_UNAVAILABLE,
            "prediction unavailable or stale while predictive policy is "
            "enabled; one old score is never reused",
        )
    return False, None, ""


def _finite_number(value: object) -> bool:
    """True only for a finite ``int``/``float`` (``bool`` rejected)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _nonnegative_finite(value: object) -> bool:
    """True only for a finite, non-negative ``int``/``float``."""
    return _finite_number(value) and float(value) >= 0.0


def safe_local_exit_status(
    pi: PolicyInput, cfg: PolicyConfig
) -> tuple[bool, tuple[str, ...]]:
    """Evaluate every SAFE_LOCAL exit requirement (Doc 02 section 38).

    All conditions must hold. A reconnect alone never satisfies them; the
    caller must supply stable-connectivity duration, reconciled twin state,
    fresh telemetry and absence of stale commands/critical faults
    (Doc 02 section 31.3, 05D section 19).

    This function is fail-closed on its own: a non-finite or negative timing
    (NaN/+/-inf, negative) never counts as a satisfied requirement, even if it
    is called without going through ``_validate_input``. NaN comparisons are
    always false, so without this guard a NaN duration would silently look
    "long enough" or "fresh enough". For the same reason, malformed booleans
    (for example the truthy string ``"false"``) never count as trusted/clear;
    they are reported as the relevant missing requirement. Only the exact
    ``True``/``False`` values satisfy the gate.
    """
    missing: list[str] = []
    r = pi.remote

    if r.broker_connected is not True:
        missing.append("broker_connected")
    if not (
        _nonnegative_finite(r.network_stable_s)
        and r.network_stable_s >= cfg.safe_local_exit_min_stable_s
    ):
        missing.append("network_stable")
    if r.backend_state_synced is not True:
        missing.append("backend_state_synchronized")
    if not (
        _nonnegative_finite(r.backend_state_age_s)
        and r.backend_state_age_s <= cfg.backend_state_max_age_s
    ):
        missing.append("backend_state_fresh")
    if r.state_sync_trusted is not True:
        missing.append("state_sync_trusted")
    if r.remote_command_path_trusted is not True:
        missing.append("remote_command_path_trusted")
    if r.stale_command_pending is not False:
        missing.append("no_stale_command")

    thermal = pi.thermal
    fresh_valid_thermal = (
        thermal.quality is QualityState.VALID
        and _finite_number(thermal.t_representative_c)
        and _nonnegative_finite(thermal.age_s)
        and thermal.age_s <= cfg.thermal_max_age_s
    )
    if not fresh_valid_thermal:
        missing.append("fresh_valid_telemetry")

    if cfg.predictive_enabled and not _prediction_healthy(pi, cfg):
        missing.append("prediction_healthy")

    if not (
        pi.fault_active is False
        and pi.control_electrical_anomaly is False
        and pi.hardware_safety_condition is False
    ):
        missing.append("no_critical_fault")

    return (not missing, tuple(missing))


def _hysteresis(
    t: float | None, applied: CoolingState, cfg: PolicyConfig
) -> tuple[ActuationIntent, ReasonCode | None, str]:
    """Controller A hysteresis held inside the policy core.

    Upper/lower values are caller-supplied characterization results
    (Doc 02 section 24.4); this function contains no constants.
    """
    if t is None:
        return (
            ActuationIntent.HOLD,
            None,
            "no usable thermal representative; hold applied state",
        )
    if t >= cfg.upper_on_c:
        return (
            ActuationIntent.ON,
            ReasonCode.THRESHOLD_HIGH,
            "representative temperature at/above upper boundary",
        )
    if t <= cfg.lower_off_c:
        if applied is CoolingState.ON:
            return (
                ActuationIntent.OFF,
                ReasonCode.THRESHOLD_RECOVERED,
                "representative temperature at/below lower boundary",
            )
        return (
            ActuationIntent.HOLD,
            None,
            "below lower boundary and already OFF; hold",
        )
    return (
        ActuationIntent.HOLD,
        None,
        "inside hysteresis band; hold current legal state",
    )


def _decision(
    *,
    cfg: PolicyConfig,
    state: PolicyState,
    intent: ActuationIntent,
    controller: ControllerId,
    reason: ReasonCode | None,
    detail: str,
    predictive_blocked: bool = False,
    degraded: bool = False,
    missing: tuple[str, ...] = (),
    transition: str | None = None,
    notes: tuple[str, ...] = (),
) -> PolicyDecision:
    return PolicyDecision(
        policy_version=cfg.policy_version,
        state=state,
        actuation_intent=intent,
        controller_id=controller,
        reason_code=reason,
        reason_detail=detail,
        predictive_blocked=predictive_blocked,
        degraded_sensing=degraded,
        safe_local_exit_missing=missing,
        transition=transition,
        notes=notes,
    )


def evaluate_policy(pi: PolicyInput, cfg: PolicyConfig) -> PolicyDecision:
    """Evaluate one deterministic policy decision.

    The decision is a pure function of ``(pi, cfg)``; identical inputs yield
    identical outputs (Doc 05D D-W17-04 determinism requirement).
    """
    _validate_input(pi, cfg)

    prior = pi.current_state
    entering_local = prior is not PolicyState.SAFE_LOCAL

    # ---- 1. Hard safety faults: safe actuation cannot be guaranteed. -------
    if pi.device_mode is DeviceMode.FAULT_LOCKOUT:
        return _decision(
            cfg=cfg,
            state=PolicyState.FAULT_LOCKOUT,
            intent=ActuationIntent.HOLD,
            controller=ControllerId.REACTIVE,
            reason=pi.fault_reason,
            detail="device already in FAULT_LOCKOUT; no actuation permitted",
            predictive_blocked=True,
        )

    if pi.control_electrical_anomaly:
        return _decision(
            cfg=cfg,
            state=PolicyState.FAULT_LOCKOUT,
            intent=ActuationIntent.HOLD,
            controller=ControllerId.REACTIVE,
            reason=ReasonCode.CONTROL_ELECTRICAL_ANOMALY,
            detail=(
                "unexpected energization/anomaly; actuation cannot be "
                "guaranteed safe (Doc 01 sections 22.4/23.4, Doc 02 2.7)"
            ),
            predictive_blocked=True,
        )

    if pi.hardware_safety_condition:
        return _decision(
            cfg=cfg,
            state=PolicyState.FAULT_LOCKOUT,
            intent=ActuationIntent.HOLD,
            controller=ControllerId.REACTIVE,
            reason=None,
            detail=(
                "characterized hardware safety stop condition asserted; do "
                "not escalate (Doc 01 PHY-ACT-004/PHY-SAFE-009, Doc 02 2.7)"
            ),
            predictive_blocked=True,
        )

    if pi.fault_active:
        reason = pi.fault_reason
        if reason is not None and reason in _LOCKOUT_REASONS:
            return _decision(
                cfg=cfg,
                state=PolicyState.FAULT_LOCKOUT,
                intent=ActuationIntent.HOLD,
                controller=ControllerId.REACTIVE,
                reason=reason,
                detail="lockout-class fault; no actuation permitted",
                predictive_blocked=True,
            )
        return _decision(
            cfg=cfg,
            state=PolicyState.FAULT,
            intent=ActuationIntent.HOLD,
            controller=ControllerId.REACTIVE,
            reason=reason,
            detail=(
                "active fault invalidates normal policy; hold and wait for "
                "the W10 fault-oracle disposition (Doc 02 23.5)"
            ),
            predictive_blocked=True,
        )

    # ---- 2. Physical state usability --------------------------------------
    thermal = pi.thermal
    fresh = (
        thermal.age_s is not None
        and thermal.age_s <= cfg.thermal_max_age_s
    )

    if thermal.quality in (QualityState.INVALID, QualityState.UNKNOWN):
        return _decision(
            cfg=cfg,
            state=PolicyState.FAULT_LOCKOUT,
            intent=ActuationIntent.HOLD,
            controller=ControllerId.REACTIVE,
            reason=ReasonCode.THERMAL_STATE_INVALID,
            detail=(
                "critical thermal state invalid/unknown; safe actuation "
                "cannot be guaranteed (Doc 02 2.7, Doc 01 19.4/PHY-SAFE-008)"
            ),
            predictive_blocked=True,
        )

    if not fresh:
        return _decision(
            cfg=cfg,
            state=PolicyState.FAULT,
            intent=ActuationIntent.HOLD,
            controller=ControllerId.REACTIVE,
            reason=None,
            detail=(
                "thermal state stale beyond policy freshness; no new "
                "actuation request and predictive prohibited until fresh "
                "data arrives (Doc 01 18.4, SW-SAFE-004; W05 owns the final "
                "degraded/freshness fallback rule)"
            ),
            predictive_blocked=True,
        )

    t = thermal.t_representative_c
    usable = (
        thermal.quality is QualityState.VALID
        or (
            thermal.quality is QualityState.DEGRADED
            and t is not None
        )
    )

    # ---- 3. Critical thermal protection dominates everything below --------
    # CRITICAL_PROTECTION latches through the hysteresis band until the lower
    # recovery boundary. Entering only at the upper boundary and dropping the
    # label immediately below it would chatter at the boundary even though the
    # actuator remains ON; the latch uses the same caller-supplied hysteresis
    # values as Controller A (Doc 02 section 24.1).
    critical_latched = (
        prior is PolicyState.CRITICAL_PROTECTION
        and t is not None
        and t > cfg.lower_off_c
    )
    if usable and t is not None and (
        t >= cfg.upper_on_c or critical_latched
    ):
        return _decision(
            cfg=cfg,
            state=PolicyState.CRITICAL_PROTECTION,
            intent=ActuationIntent.ON,
            controller=ControllerId.REACTIVE,
            reason=ReasonCode.THRESHOLD_HIGH,
            detail=(
                "reactive critical boundary reached; Controller A "
                "protection dominates any predictive advice"
                if not critical_latched
                else "critical protection latched until the lower recovery "
                "boundary; Controller A remains authoritative"
            ),
            predictive_blocked=thermal.quality is not QualityState.VALID,
            degraded=thermal.quality is not QualityState.VALID,
            notes=(
                "Doc 02 23.4; 05D D-W13-04 and section 7 safety gate",
            ),
        )

    # ---- 4. SAFE_LOCAL regime and exit gate -------------------------------
    # The prior policy state is authoritative: a caller-reported ONLINE_* mode
    # must not bypass the exit gate while the last decision is still
    # SAFE_LOCAL. Otherwise an inconsistent pair (mode ONLINE_NORMAL, state
    # SAFE_LOCAL) with otherwise trusted remote evidence could reach the
    # predictive path with network_stable_s=0 or a stale command pending.
    # Both sources of "we are in SAFE_LOCAL" therefore share one gate, and an
    # unmet gate keeps the device in SAFE_LOCAL (fail-closed).
    safe_local_regime = (
        pi.device_mode is DeviceMode.SAFE_LOCAL
        or prior is PolicyState.SAFE_LOCAL
    )
    if safe_local_regime:
        exit_ok, missing = safe_local_exit_status(pi, cfg)
        if not exit_ok:
            intent, reason, detail = _hysteresis(t if usable else None,
                                                 pi.applied_cooling, cfg)
            return _decision(
                cfg=cfg,
                state=PolicyState.SAFE_LOCAL,
                intent=intent,
                controller=ControllerId.REACTIVE,
                reason=reason,
                detail=(
                    "SAFE_LOCAL held; local deterministic protection only. "
                    + detail
                ),
                predictive_blocked=True,
                degraded=thermal.quality is not QualityState.VALID,
                missing=missing,
                transition=(
                    "SAFE_LOCAL_ENTER" if entering_local else None
                ),
            )

    untrusted, reason, detail = _remote_untrusted(pi, cfg)
    if untrusted:
        intent, local_reason, local_detail = _hysteresis(
            t if usable else None, pi.applied_cooling, cfg
        )
        return _decision(
            cfg=cfg,
            state=PolicyState.SAFE_LOCAL,
            intent=intent,
            controller=ControllerId.REACTIVE,
            reason=reason or local_reason,
            detail=(
                "remote intelligence unavailable/untrusted; local "
                "deterministic protection only: " + detail
            ),
            predictive_blocked=True,
            degraded=thermal.quality is not QualityState.VALID,
            missing=safe_local_exit_status(pi, cfg)[1],
            transition="SAFE_LOCAL_ENTER" if entering_local else None,
            notes=(local_detail,),
        )

    # ---- 5. Degraded sensing: predictive prohibited, A continues ----------
    if thermal.quality is QualityState.DEGRADED:
        intent, reason, detail = _hysteresis(
            t, pi.applied_cooling, cfg
        )
        return _decision(
            cfg=cfg,
            state=PolicyState.NORMAL,
            intent=intent,
            controller=ControllerId.REACTIVE,
            reason=ReasonCode.SENSOR_DEGRADED,
            detail=(
                "degraded thermal sensing; predictive intervention "
                "prohibited unless the model explicitly supports the "
                "missing-channel state (Doc 02 40.1)"
            ),
            predictive_blocked=True,
            degraded=True,
            notes=(detail,),
        )

    # ---- 6. Predictive path (only with a frozen predictive contract) ------
    if cfg.predictive_enabled:
        pred = pi.prediction
        assert pred is not None and pred.risk_score is not None
        assert cfg.watch_threshold is not None
        assert cfg.preemptive_threshold is not None
        assert cfg.persistence_required_s is not None

        persisted = pred.above_preemptive_s or 0.0
        if (
            pred.risk_score >= cfg.preemptive_threshold
            and persisted >= cfg.persistence_required_s
        ):
            return _decision(
                cfg=cfg,
                state=PolicyState.PREEMPTIVE_COOLING,
                intent=ActuationIntent.ON,
                controller=ControllerId.PREDICTIVE,
                reason=ReasonCode.PREDICTED_CRITICAL,
                detail=(
                    "fresh persistent predictive warning; preemptive action "
                    "allowed within the same characterized action family"
                ),
                transition=(
                    "SAFE_LOCAL_EXIT" if prior is PolicyState.SAFE_LOCAL
                    else None
                ),
                notes=(
                    "risk persistence " + str(persisted)
                    + " s >= policy requirement",
                    ReasonCode.RISK_PERSISTENT.value,
                ),
            )
        if pred.risk_score >= cfg.watch_threshold:
            return _decision(
                cfg=cfg,
                state=PolicyState.WATCH,
                intent=ActuationIntent.HOLD,
                controller=ControllerId.REACTIVE,
                reason=ReasonCode.PREDICTED_CRITICAL,
                detail=(
                    "risk elevated but persistence/intervention condition "
                    "not met; watch only, no preemptive actuation"
                ),
                transition=(
                    "SAFE_LOCAL_EXIT" if prior is PolicyState.SAFE_LOCAL
                    else None
                ),
                notes=(
                    "persistence " + str(persisted) + " s < required "
                    + str(cfg.persistence_required_s) + " s",
                ),
            )

    # ---- 7. Normal reactive behavior --------------------------------------
    intent, reason, detail = _hysteresis(t, pi.applied_cooling, cfg)
    return _decision(
        cfg=cfg,
        state=PolicyState.NORMAL,
        intent=intent,
        controller=ControllerId.REACTIVE,
        reason=reason,
        detail=detail,
        transition=(
            "SAFE_LOCAL_EXIT" if prior is PolicyState.SAFE_LOCAL else None
        ),
    )
