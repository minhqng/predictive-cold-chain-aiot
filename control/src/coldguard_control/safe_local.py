"""Testable SAFE_LOCAL session semantics (Member D, W08).

SAFE_LOCAL is a device-local deterministic mode used when the remote
control/intelligence path is unavailable or untrusted (Doc 02 section 37,
05D section 16). It must keep running without MQTT responses, a database,
XGBoost, or the frontend. Exit requires more than a reconnect: stable network,
reconciled twin state, fresh telemetry, no stale command, no critical fault and
(if predictive mode is enabled) a healthy prediction (Doc 02 section 38,
05D section 19).

This module is a thin stateful wrapper over ``evaluate_policy`` and
``safe_local_exit_status``. It adds only the session bookkeeping that a single
decision call cannot express: enter/exit events and the entry reason. The W03
policy remains the single safety gate. No transport, clock, database or
actuator code is imported.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .config import PolicyConfig
from .policy import PolicyDecision, PolicyInput, evaluate_policy, safe_local_exit_status
from .types import ControllerId, DeviceMode, PolicyState, ReasonCode


@dataclass(frozen=True, slots=True)
class SafeLocalStep:
    """One SAFE_LOCAL session step."""

    decision: PolicyDecision
    active: bool
    entered: bool
    exited: bool
    entry_reason: ReasonCode | None
    exit_ready: bool
    exit_missing: tuple[str, ...]
    local_control_only: bool

    @property
    def trigger_reason(self) -> ReasonCode | None:
        """Reason to enter, or the reason currently keeping local mode held."""
        if self.active:
            return self.entry_reason or self.decision.reason_code
        return None


class SafeLocalSession:
    """Deterministic SAFE_LOCAL entry/exit bookkeeping around the W03 policy.

    The session owns only the mode bit. It does not invent a second policy:
    local protection is the same Controller A hysteresis and safety gate used
    online. ``local_control_only`` is true whenever the session is active and
    the decision was produced by the reactive controller, which is the
    testable local-independence invariant (no predictive controller, no
    remote command).
    """

    def __init__(
        self,
        config: PolicyConfig,
        *,
        initial_active: bool = False,
    ) -> None:
        self._config = config
        self._active = bool(initial_active)
        self._mode = (
            DeviceMode.SAFE_LOCAL if self._active else DeviceMode.ONLINE_NORMAL
        )
        self._entry_reason: ReasonCode | None = None

    @property
    def active(self) -> bool:
        return self._active

    @property
    def mode(self) -> DeviceMode:
        return self._mode

    def step(self, policy_input: PolicyInput) -> SafeLocalStep:
        """Evaluate one input while preserving SAFE_LOCAL across a decision.

        While active, the effective device mode is forced to ``SAFE_LOCAL`` so
        a caller-supplied ``ONLINE_*`` mode cannot bypass the exit gate. A
        critical local thermal decision may still be reported as
        ``CRITICAL_PROTECTION``; in that case the session stays active until
        every exit requirement is met.
        """
        effective = policy_input
        if self._active and policy_input.device_mode is not DeviceMode.FAULT_LOCKOUT:
            effective = replace(policy_input, device_mode=DeviceMode.SAFE_LOCAL)

        decision = evaluate_policy(effective, self._config)
        if decision.state is PolicyState.FAULT_LOCKOUT:
            self._active = False
            self._mode = DeviceMode.FAULT_LOCKOUT
            self._entry_reason = None
            return SafeLocalStep(
                decision=decision,
                active=False,
                entered=False,
                exited=False,
                entry_reason=None,
                exit_ready=False,
                exit_missing=("fault_lockout",),
                local_control_only=False,
            )
        exit_ready, missing = safe_local_exit_status(effective, self._config)

        # The W03 policy may report CRITICAL_PROTECTION while the remote path
        # is still untrusted because local protection outranks the mode label.
        # The session remains SAFE_LOCAL until the full exit gate is satisfied.
        active = decision.state is PolicyState.SAFE_LOCAL or (
            self._active and not exit_ready
        )
        entered = active and not self._active
        exited = self._active and not active

        if entered:
            self._entry_reason = decision.reason_code
        elif exited:
            self._entry_reason = None

        self._active = active
        self._mode = (
            DeviceMode.SAFE_LOCAL
            if active
            else (
                policy_input.device_mode
                if policy_input.device_mode in (
                    DeviceMode.ONLINE_NORMAL, DeviceMode.ONLINE_DEGRADED
                )
                else DeviceMode.ONLINE_NORMAL
            )
        )
        local_only = active and decision.controller_id is ControllerId.REACTIVE

        return SafeLocalStep(
            decision=decision,
            active=active,
            entered=entered,
            exited=exited,
            entry_reason=self._entry_reason,
            exit_ready=exit_ready,
            exit_missing=missing,
            local_control_only=local_only,
        )
