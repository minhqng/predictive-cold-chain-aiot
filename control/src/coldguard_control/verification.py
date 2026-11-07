"""Deterministic physical-response verification policy (Member D, W09).

The tracker implements the Doc 02 sections 35-36 policy:

```text
legal ON
  -> bounded electrical window: current/power must enter the characterized
     active envelope
  -> bounded thermal window: thermal trajectory must show the characterized
     useful cooling response
  -> terminal verification state + cooling-health classification
```

It is a state machine, not a blocking wait. The caller supplies every timestamp
and every observation, so identical inputs replay identically and local control
is never blocked by verification. The module imports no clock, transport,
database or GPIO code.

Claim discipline
----------------
``VERIFIED`` / ``HEALTHY_RESPONSE`` require a ``QUALIFIED`` envelope. Member A's
W08/W09 electrical values are real observations but their status tokens are
empty (`usable_for_a_health_claim: false`), so the imported candidate envelope
is marked ``CANDIDATE_UNQUALIFIED``. In that state the tracker can report that
an electrical/thermal response was observed, but it terminates at ``UNKNOWN``
instead of claiming physical verification. No root cause (TEC, fan, paste) is
ever inferred (05D section 15).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import ConfigError
from .types import (
    CoolingHealthState,
    CoolingState,
    EnvelopeQualification,
    QualityState,
    ReasonCode,
    VerificationState,
)

_TERMINAL_STATES = frozenset(
    {
        VerificationState.VERIFIED,
        VerificationState.FAILED_ELECTRICAL,
        VerificationState.FAILED_THERMAL,
        VerificationState.UNKNOWN,
    }
)


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ConfigError(f"{name} must be a finite number")
    return number


def _finite_value(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _optional_finite(name: str, value: object) -> float | None:
    if value is None:
        return None
    return _finite(name, value)


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    """Versioned characterization envelope and response windows.

    Every value is mandatory. The candidate JSON under ``evidence/D/W09`` is
    synthetic test input; this package ships no physical default and does not
    freeze an envelope.
    """

    policy_version: str
    envelope_id: str
    qualification: EnvelopeQualification
    active_current_min_a: float
    active_current_max_a: float
    off_current_max_a: float
    electrical_window_s: float
    thermal_window_s: float
    thermal_min_drop_c: float
    active_power_min_w: float | None = None
    active_power_max_w: float | None = None
    source: str = ""

    def __post_init__(self) -> None:
        for name, value in (
            ("policy_version", self.policy_version),
            ("envelope_id", self.envelope_id),
            ("source", self.source),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"{name} must be a non-empty string")
        if not isinstance(self.qualification, EnvelopeQualification):
            raise ConfigError("qualification must be an EnvelopeQualification")

        current_min = _finite("active_current_min_a", self.active_current_min_a)
        current_max = _finite("active_current_max_a", self.active_current_max_a)
        off_max = _finite("off_current_max_a", self.off_current_max_a)
        electrical_window = _finite("electrical_window_s", self.electrical_window_s)
        thermal_window = _finite("thermal_window_s", self.thermal_window_s)
        thermal_drop = _finite("thermal_min_drop_c", self.thermal_min_drop_c)

        if current_min < 0 or current_max < 0 or off_max < 0:
            raise ConfigError("current envelope values cannot be negative")
        if current_min > current_max:
            raise ConfigError(
                "active_current_min_a cannot exceed active_current_max_a"
            )
        if electrical_window <= 0 or thermal_window <= 0:
            raise ConfigError("response windows must be positive")
        if thermal_drop <= 0:
            raise ConfigError("thermal_min_drop_c must be positive")

        power_min = _optional_finite("active_power_min_w", self.active_power_min_w)
        power_max = _optional_finite("active_power_max_w", self.active_power_max_w)
        if (power_min is None) != (power_max is None):
            raise ConfigError(
                "active power bounds must either both be supplied or both omitted"
            )
        if power_min is not None and power_max is not None:
            if power_min < 0 or power_max < 0:
                raise ConfigError("power envelope values cannot be negative")
            if power_min > power_max:
                raise ConfigError(
                    "active_power_min_w cannot exceed active_power_max_w"
                )


@dataclass(frozen=True, slots=True)
class VerificationObservation:
    """One caller-timed physical observation.

    A value is usable as verification evidence only when its quality is exactly
    ``VALID``. ``DEGRADED``/``INVALID``/``UNKNOWN`` values are retained as
    evidence that data was missing/untusable, never silently treated as healthy
    (Doc 01 section 19.4).
    """

    now_s: float
    current_a: float | None = None
    current_quality: QualityState = QualityState.UNKNOWN
    power_w: float | None = None
    power_quality: QualityState = QualityState.UNKNOWN
    thermal_t_representative_c: float | None = None
    thermal_quality: QualityState = QualityState.UNKNOWN

    def __post_init__(self) -> None:
        _finite_value("now_s", self.now_s)
        for name, quality in (
            ("current_quality", self.current_quality),
            ("power_quality", self.power_quality),
            ("thermal_quality", self.thermal_quality),
        ):
            if not isinstance(quality, QualityState):
                raise ValueError(f"{name} must be a QualityState")
        for name, value, quality in (
            ("current_a", self.current_a, self.current_quality),
            ("power_w", self.power_w, self.power_quality),
            (
                "thermal_t_representative_c",
                self.thermal_t_representative_c,
                self.thermal_quality,
            ),
        ):
            if value is not None:
                _finite_value(name, value)
            if quality is QualityState.VALID and value is None:
                raise ValueError(f"VALID {name} requires a value")
            if quality in (QualityState.INVALID, QualityState.UNKNOWN) and (
                value is not None
            ):
                raise ValueError(
                    f"{name} cannot carry a value when quality is {quality.value}"
                )


@dataclass(frozen=True, slots=True)
class VerificationSnapshot:
    """Result of one tracker step."""

    command_id: str
    action: CoolingState
    state: VerificationState
    health: CoolingHealthState
    reason_code: ReasonCode | None
    detail: str
    now_s: float
    electrical_deadline_s: float
    thermal_deadline_s: float | None
    electrical_response_observed: bool
    thermal_response_observed: bool
    terminal: bool
    notes: tuple[str, ...] = field(default_factory=tuple)


class VerificationTracker:
    """Stateful, non-blocking physical verification of one command."""

    def __init__(
        self,
        policy: VerificationPolicy,
        *,
        command_id: str,
        action: CoolingState,
        started_s: float,
        baseline_temperature_c: float | None = None,
    ) -> None:
        if not isinstance(policy, VerificationPolicy):
            raise ValueError("policy must be a VerificationPolicy")
        if not isinstance(command_id, str) or not command_id.strip():
            raise ValueError("command_id must be a non-empty string")
        if not isinstance(action, CoolingState):
            raise ValueError("action must be a CoolingState")
        start = _finite_value("started_s", started_s)
        baseline = (
            None
            if baseline_temperature_c is None
            else _finite_value("baseline_temperature_c", baseline_temperature_c)
        )

        self._policy = policy
        self._command_id = command_id
        self._action = action
        self._started_s = start
        self._baseline_t = baseline
        self._now_s = start
        self._last_observation_s: float | None = None
        self._last_observation: VerificationObservation | None = None
        self._closed = False
        self._electrical_deadline_s = start + policy.electrical_window_s
        self._thermal_deadline_s: float | None = None
        self._electrical_verified_s: float | None = None
        self._electrical_response_observed = False
        self._thermal_response_observed = False
        self._valid_electrical_seen = False
        self._complete_electrical_seen = False
        self._valid_thermal_seen = False
        self._below_active_seen = False
        self._above_active_seen = False

        if action is CoolingState.ON:
            self._state = VerificationState.PENDING
            self._health = CoolingHealthState.UNKNOWN
            self._reason = None
            self._detail = (
                "ON accepted; waiting for the bounded electrical response window"
            )
        else:
            # OFF has no useful thermal response to verify, but unexpected
            # current while OFF is a high-severity anomaly (Doc 01 22.4/23.4).
            self._state = VerificationState.NOT_REQUIRED
            self._health = CoolingHealthState.UNKNOWN
            self._reason = None
            self._detail = (
                "OFF: no cooling response verification required; monitoring the "
                "OFF electrical envelope"
            )

    def observe(self, observation: VerificationObservation) -> VerificationSnapshot:
        """Record one observation and advance the timer to its timestamp."""
        if not isinstance(observation, VerificationObservation):
            raise ValueError("observation must be a VerificationObservation")
        now = float(observation.now_s)
        if now < self._started_s:
            raise ValueError("observation cannot precede command start")
        if now < self._now_s:
            raise ValueError("observation timestamps must not go backwards")
        if self._closed:
            return self.snapshot()
        self._now_s = now
        deadline = (
            self._thermal_deadline_s
            if self._state is VerificationState.ELECTRICAL_VERIFIED
            else self._electrical_deadline_s
        )
        if deadline is not None and now > deadline:
            # A sample collected after the window cannot retroactively prove
            # a response inside it. Expire the timer without that sample.
            self._advance(None)
            if self._closed:
                return self.snapshot()
        self._last_observation_s = now
        self._last_observation = observation
        self._advance(observation)
        return self.snapshot()

    def tick(self, now_s: float) -> VerificationSnapshot:
        """Advance timers without inventing a new observation.

        This is how a scheduler asks "has the window expired while no new
        sample arrived?" without blocking the local control task.
        """
        now = _finite_value("now_s", now_s)
        if now < self._started_s:
            raise ValueError("tick cannot precede command start")
        if now < self._now_s:
            raise ValueError("tick cannot move backwards")
        if self._closed:
            return self.snapshot()
        self._now_s = now
        # A timer advance is not a new physical sample.
        self._advance(None)
        return self.snapshot()

    def snapshot(self) -> VerificationSnapshot:
        return VerificationSnapshot(
            command_id=self._command_id,
            action=self._action,
            state=self._state,
            health=self._health,
            reason_code=self._reason,
            detail=self._detail,
            now_s=self._now_s,
            electrical_deadline_s=self._electrical_deadline_s,
            thermal_deadline_s=self._thermal_deadline_s,
            electrical_response_observed=self._electrical_response_observed,
            thermal_response_observed=self._thermal_response_observed,
            terminal=self._closed or self._state in _TERMINAL_STATES,
            notes=(
                "ACK/accepted command is not physical verification",
                "UNKNOWN is never converted to healthy",
                "classification states the observable response, not a root cause",
            ),
        )

    # ------------------------------------------------------------------
    # Internal transition logic
    # ------------------------------------------------------------------
    def _advance(self, observation: VerificationObservation | None) -> None:
        if self._action is CoolingState.OFF:
            self._advance_off(observation)
        else:
            self._advance_on(observation)

    def _advance_off(self, observation: VerificationObservation | None) -> None:
        valid_current = (
            observation is not None
            and observation.current_quality is QualityState.VALID
            and observation.current_a is not None
        )
        if valid_current:
            assert observation is not None and observation.current_a is not None
            self._valid_electrical_seen = True
            if observation.current_a > self._policy.off_current_max_a:
                if self._policy.qualification is not EnvelopeQualification.QUALIFIED:
                    self._state = VerificationState.UNKNOWN
                    self._health = CoolingHealthState.UNKNOWN
                    self._detail = "OFF envelope is unqualified; anomaly cannot be classified"
                    self._closed = True
                    return
                self._electrical_response_observed = True
                self._state = VerificationState.FAILED_ELECTRICAL
                self._health = CoolingHealthState.CONTROL_ELECTRICAL_ANOMALY
                self._reason = ReasonCode.CONTROL_ELECTRICAL_ANOMALY
                self._detail = (
                    "OFF current above the characterized OFF envelope; "
                    "unexpected energization candidate"
                )
                self._closed = True
                return

        if self._now_s >= self._electrical_deadline_s:
            self._closed = True
            if self._valid_electrical_seen and self._policy.qualification is EnvelopeQualification.QUALIFIED:
                self._state = VerificationState.NOT_REQUIRED
                self._health = CoolingHealthState.UNKNOWN
                self._reason = None
                self._detail = (
                    "OFF current stayed inside the OFF envelope; no ON "
                    "verification is required"
                )
            else:
                self._state = VerificationState.UNKNOWN
                self._health = CoolingHealthState.UNKNOWN
                self._reason = None
                self._detail = (
                    "no valid electrical evidence in the OFF window; the OFF "
                    "state cannot be confirmed from this path"
                )

    def _advance_on(self, observation: VerificationObservation | None) -> None:
        if self._state is VerificationState.ELECTRICAL_VERIFIED:
            self._advance_thermal(observation)
            return
        if self._state is not VerificationState.PENDING:
            return

        valid_current = (
            observation is not None
            and observation.current_quality is QualityState.VALID
            and observation.current_a is not None
        )
        in_active_envelope = False
        if valid_current:
            assert observation is not None and observation.current_a is not None
            self._valid_electrical_seen = True
            current = observation.current_a
            in_current = (
                self._policy.active_current_min_a
                <= current
                <= self._policy.active_current_max_a
            )
            if current < self._policy.active_current_min_a:
                self._below_active_seen = True
            elif current > self._policy.active_current_max_a:
                self._above_active_seen = True

            power_ok = True
            if self._policy.active_power_min_w is not None:
                assert self._policy.active_power_max_w is not None
                power_valid = (
                    observation.power_quality is QualityState.VALID
                    and observation.power_w is not None
                )
                if power_valid:
                    self._complete_electrical_seen = True
                power_ok = (
                    power_valid
                    and self._policy.active_power_min_w
                    <= observation.power_w
                    <= self._policy.active_power_max_w
                )
            else:
                self._complete_electrical_seen = True
            in_active_envelope = in_current and power_ok

        if in_active_envelope:
            self._electrical_response_observed = True
            if self._policy.qualification is not EnvelopeQualification.QUALIFIED:
                self._state = VerificationState.UNKNOWN
                self._health = CoolingHealthState.UNKNOWN
                self._detail = "active envelope is unqualified; electrical verification withheld"
                self._closed = True
                return
            self._state = VerificationState.ELECTRICAL_VERIFIED
            self._electrical_verified_s = self._now_s
            self._thermal_deadline_s = (
                self._now_s + self._policy.thermal_window_s
            )
            if self._baseline_t is None and observation is not None:
                if (
                    observation.thermal_quality is QualityState.VALID
                    and observation.thermal_t_representative_c is not None
                ):
                    self._baseline_t = observation.thermal_t_representative_c
            self._detail = (
                "current/power entered the active envelope; waiting for the "
                "bounded thermal response window"
            )
            self._advance_thermal(observation)
            return

        if self._now_s < self._electrical_deadline_s:
            if valid_current:
                self._detail = (
                    "valid electrical sample seen but outside the active "
                    "envelope; still inside the response window"
                )
            return

        # Deadline reached without a complete active-envelope response.
        if not self._valid_electrical_seen:
            self._state = VerificationState.UNKNOWN
            self._health = CoolingHealthState.UNKNOWN
            self._reason = None
            self._detail = (
                "no valid electrical evidence inside the electrical window; "
                "insufficient evidence to classify response"
            )
        elif (
            not self._complete_electrical_seen
            and not self._below_active_seen
            and not self._above_active_seen
        ):
            self._state = VerificationState.UNKNOWN
            self._health = CoolingHealthState.UNKNOWN
            self._reason = None
            self._detail = (
                "current was observed, but required power evidence was missing "
                "inside the electrical window"
            )
        else:
            if self._policy.qualification is not EnvelopeQualification.QUALIFIED:
                self._state = VerificationState.UNKNOWN
                self._health = CoolingHealthState.UNKNOWN
                self._reason = None
                self._detail = "active envelope is unqualified; electrical failure cannot be classified"
                self._closed = True
                return
            self._state = VerificationState.FAILED_ELECTRICAL
            if self._below_active_seen and not self._above_active_seen:
                self._health = CoolingHealthState.ELECTRICAL_RESPONSE_MISSING
                self._reason = ReasonCode.ELECTRICAL_RESPONSE_MISSING
                self._detail = (
                    "commanded ON but current/power stayed below the active "
                    "envelope for the whole response window"
                )
            else:
                self._health = CoolingHealthState.CONTROL_ELECTRICAL_ANOMALY
                self._reason = ReasonCode.CONTROL_ELECTRICAL_ANOMALY
                self._detail = (
                    "current/power left the characterized active envelope "
                    "without a complete valid response"
                )
        self._closed = True

    def _advance_thermal(
        self, observation: VerificationObservation | None
    ) -> None:
        if self._thermal_deadline_s is None:
            return
        valid_thermal = (
            observation is not None
            and observation.thermal_quality is QualityState.VALID
            and observation.thermal_t_representative_c is not None
        )
        if valid_thermal:
            assert observation is not None
            assert observation.thermal_t_representative_c is not None
            self._valid_thermal_seen = True
            if (
                self._baseline_t is not None
                and self._baseline_t
                - observation.thermal_t_representative_c
                >= self._policy.thermal_min_drop_c
            ):
                self._thermal_response_observed = True
                if (
                    self._policy.qualification
                    is EnvelopeQualification.QUALIFIED
                ):
                    self._state = VerificationState.VERIFIED
                    self._health = CoolingHealthState.HEALTHY_RESPONSE
                    self._reason = None
                    self._detail = (
                        "electrical and thermal responses both met the qualified "
                        "envelope; cooling response verified"
                    )
                else:
                    # Observable evidence exists, but the envelope is not
                    # qualified: never upgrade that to a physical claim.
                    self._state = VerificationState.UNKNOWN
                    self._health = CoolingHealthState.UNKNOWN
                    self._reason = None
                    self._detail = (
                        "thermal response met the candidate envelope, but the "
                        "envelope is not QUALIFIED; VERIFIED is withheld"
                    )
                self._closed = True
                return
            if self._now_s < self._thermal_deadline_s:
                return

        if self._now_s < self._thermal_deadline_s:
            return

        self._closed = True
        if self._valid_thermal_seen and self._baseline_t is not None:
            if self._policy.qualification is not EnvelopeQualification.QUALIFIED:
                self._state = VerificationState.UNKNOWN
                self._health = CoolingHealthState.UNKNOWN
                self._reason = None
                self._detail = "thermal envelope is unqualified; failure cannot be classified"
                return
            self._state = VerificationState.FAILED_THERMAL
            self._health = CoolingHealthState.THERMAL_EFFECTIVENESS_DEGRADED
            self._reason = ReasonCode.THERMAL_EFFECTIVENESS_DEGRADED
            self._detail = (
                "electrical response was valid but the thermal drop stayed "
                "below the characterized useful response inside the window"
            )
        else:
            self._state = VerificationState.UNKNOWN
            self._health = CoolingHealthState.UNKNOWN
            self._reason = None
            self._detail = (
                "no valid thermal evidence inside the thermal window; "
                "cooling effectiveness is unknown"
            )


def start_verification(
    policy: VerificationPolicy,
    *,
    command_id: str,
    action: CoolingState,
    started_s: float,
    baseline_temperature_c: float | None = None,
) -> VerificationTracker:
    """Create a tracker for one command (pure factory, no I/O)."""
    return VerificationTracker(
        policy,
        command_id=command_id,
        action=action,
        started_s=started_s,
        baseline_temperature_c=baseline_temperature_c,
    )
