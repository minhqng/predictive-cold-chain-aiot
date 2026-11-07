"""Deterministic Controller A runtime and replay (Member D, W07).

Controller A is the reactive threshold/hysteresis baseline and the local
fallback foundation (Doc 00 section 7.1, Doc 02 section 25, 05D section 4).
The W03 policy core already owns the safety gate and hysteresis decision; this
module adds the *time-dependent* parts that a single ``PolicyInput ->
PolicyDecision`` call cannot express:

* optional threshold persistence (the condition must hold for N seconds);
* optional minimum ON/OFF dwell (anti-chatter only, never a safety override);
* a replay runner that turns a sample sequence into a deterministic decision
  sequence for synthetic/recorded replay.

The module is pure. It owns no clock, imports no transport/database/GPIO code,
and never actuates. The caller supplies ``now_s`` on every sample. All numeric
values are explicit configuration; the package ships no candidate threshold.

Physical status: the candidate configuration is *not* frozen. Member A's W07
repeatability verdict is ``NOT ESTABLISHED`` (n=1), so no upper/lower boundary
may be quoted from this module as a project limit (Doc 04 W07; 05D D-W07-01).
Replay tests use synthetic values only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import ConfigError, PolicyConfig
from .policy import PolicyDecision, PolicyInput, evaluate_policy
from .types import ActuationIntent, CoolingState, PolicyState


def _finite_nonnegative(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ConfigError(f"{name} must be a finite number")
    if number < 0.0:
        raise ConfigError(f"{name} cannot be negative")
    return number


def _finite_now(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("now_s must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("now_s must be a finite number")
    return number


@dataclass(frozen=True, slots=True)
class ControllerAConfig:
    """Controller A timing parameters layered over the W03 policy config.

    ``persistence_s``, ``min_on_dwell_s`` and ``min_off_dwell_s`` are all
    mandatory so a caller cannot silently inherit an invented anti-chatter
    policy. Candidate values remain ``0.0`` until Member A's plant evidence
    shows that chatter or persistence is required (Doc 02 sections 24.2-24.4;
    05D D-W07-03/D-W07-04).
    """

    policy: PolicyConfig
    persistence_s: float
    min_on_dwell_s: float
    min_off_dwell_s: float
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.policy, PolicyConfig):
            raise ConfigError("policy must be a PolicyConfig")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ConfigError("source must be a non-empty provenance label")
        _finite_nonnegative("persistence_s", self.persistence_s)
        _finite_nonnegative("min_on_dwell_s", self.min_on_dwell_s)
        _finite_nonnegative("min_off_dwell_s", self.min_off_dwell_s)


@dataclass(frozen=True, slots=True)
class ControllerASample:
    """One caller-timed policy snapshot for Controller A replay."""

    now_s: float
    policy_input: PolicyInput


@dataclass(frozen=True, slots=True)
class ControllerADecision:
    """Controller A decision plus the timing evidence behind it.

    ``policy`` is the unchanged W03 safety/hysteresis decision. ``intent`` is
    the final Controller A request after persistence/dwell. It is still only an
    intent: the command validator and device interlock remain authoritative.
    """

    now_s: float
    policy: PolicyDecision
    intent: ActuationIntent
    applied_before: CoolingState
    applied_after: CoolingState
    persistence_elapsed_s: float | None
    persistence_blocked: bool
    dwell_blocked: bool
    detail: str

    @property
    def transitioned(self) -> bool:
        return self.applied_before is not self.applied_after


class ControllerA:
    """Stateful, deterministic Controller A used for replay and future runtime.

    The controller starts ``OFF`` (default-off invariant). Each sample supplies
    the observed applied state. A policy intent never changes that state;
    the command/ACK/device layer must report actual application separately.
    """

    def __init__(self, config: ControllerAConfig) -> None:
        self._config = config
        self._applied = CoolingState.OFF
        self._last_transition_s: float | None = None
        self._pending_intent: ActuationIntent | None = None
        self._pending_since_s: float | None = None

    @property
    def applied_cooling(self) -> CoolingState:
        return self._applied

    def step(self, sample: ControllerASample) -> ControllerADecision:
        """Evaluate one sample. Identical ``(sequence, config)`` is stable."""
        now = _finite_now(sample.now_s)
        policy = evaluate_policy(sample.policy_input, self._config.policy)
        applied_before = self._applied
        observed_applied = sample.policy_input.applied_cooling
        self._applied = observed_applied
        if observed_applied is not applied_before:
            self._last_transition_s = now
        base = policy.actuation_intent

        # A hardware/safety hold is never converted into an actuation by this
        # layer. Persistence is only about threshold timing.
        if base is ActuationIntent.HOLD or policy.state in (
            PolicyState.FAULT,
            PolicyState.FAULT_LOCKOUT,
        ):
            self._reset_pending()
            return self._decision(
                now,
                policy,
                ActuationIntent.HOLD,
                applied_before,
                persistence_elapsed=None,
                persistence_blocked=False,
                dwell_blocked=False,
                detail="policy hold/fault; Controller A does not change state",
            )

        # Critical thermal protection is never delayed by anti-chatter rules.
        if policy.state is PolicyState.CRITICAL_PROTECTION and base is ActuationIntent.ON:
            self._reset_pending()
            return self._decision(
                now, policy, base, applied_before,
                persistence_elapsed=None,
                persistence_blocked=False,
                dwell_blocked=False,
                detail="critical protection bypasses persistence and dwell",
            )

        target = CoolingState.ON if base is ActuationIntent.ON else CoolingState.OFF
        if target is self._applied:
            self._reset_pending()
            return self._decision(
                now,
                policy,
                base,
                applied_before,
                persistence_elapsed=None,
                persistence_blocked=False,
                dwell_blocked=False,
                detail="requested state already applied; idempotent",
            )

        # Persistence: the same legal transition request must remain true for
        # the configured duration before it is issued.
        if self._pending_intent is not base or self._pending_since_s is None:
            self._pending_intent = base
            self._pending_since_s = now
        elapsed = now - self._pending_since_s
        if elapsed < self._config.persistence_s:
            return self._decision(
                now,
                policy,
                ActuationIntent.HOLD,
                applied_before,
                persistence_elapsed=elapsed,
                persistence_blocked=True,
                dwell_blocked=False,
                detail=(
                    "threshold condition not persisted long enough "
                    f"({elapsed:.3f} s < {self._config.persistence_s:.3f} s)"
                ),
            )

        # Minimum dwell only limits ordinary threshold transitions. It never
        # blocks a fault/OFF safety response because the policy would already
        # have returned HOLD in those cases above.
        dwell = (
            self._config.min_on_dwell_s
            if self._applied is CoolingState.ON
            else self._config.min_off_dwell_s
        )
        if self._last_transition_s is not None:
            since_transition = now - self._last_transition_s
            if since_transition < dwell:
                return self._decision(
                    now,
                    policy,
                    ActuationIntent.HOLD,
                    applied_before,
                    persistence_elapsed=elapsed,
                    persistence_blocked=False,
                    dwell_blocked=True,
                    detail=(
                        "minimum dwell not elapsed "
                        f"({since_transition:.3f} s < {dwell:.3f} s)"
                    ),
                )

        self._reset_pending()
        return self._decision(
            now,
            policy,
            base,
            applied_before,
            persistence_elapsed=elapsed,
            persistence_blocked=False,
            dwell_blocked=False,
            detail="Controller A transition issued",
        )

    def _reset_pending(self) -> None:
        self._pending_intent = None
        self._pending_since_s = None

    def _decision(
        self,
        now: float,
        policy: PolicyDecision,
        intent: ActuationIntent,
        applied_before: CoolingState,
        *,
        persistence_elapsed: float | None,
        persistence_blocked: bool,
        dwell_blocked: bool,
        detail: str,
    ) -> ControllerADecision:
        return ControllerADecision(
            now_s=now,
            policy=policy,
            intent=intent,
            applied_before=applied_before,
            applied_after=self._applied,
            persistence_elapsed_s=persistence_elapsed,
            persistence_blocked=persistence_blocked,
            dwell_blocked=dwell_blocked,
            detail=detail,
        )


def replay_controller_a(
    samples: list[ControllerASample] | tuple[ControllerASample, ...],
    config: ControllerAConfig,
) -> tuple[ControllerADecision, ...]:
    """Replay samples in order; the result depends only on samples + config."""
    controller = ControllerA(config)
    return tuple(controller.step(sample) for sample in samples)
