"""W17 predictive shadow adapter with an explicit no-command invariant."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from .config import PolicyConfig
from .policy import PolicyDecision, PolicyInput, evaluate_policy


@dataclass(frozen=True, slots=True)
class ShadowDecision:
    policy_decision: PolicyDecision
    decision_sha256: str
    physical_command_emitted: bool = False


@dataclass(frozen=True, slots=True)
class ShadowTimingComparison:
    status: str
    lead_s: float | None


def evaluate_shadow(policy_input: PolicyInput, config: PolicyConfig) -> ShadowDecision:
    """Evaluate the full policy while making command emission impossible."""
    if not isinstance(config, PolicyConfig) or not config.predictive_enabled:
        raise ValueError("shadow evaluation requires predictive_enabled config")
    decision = evaluate_policy(policy_input, config)
    payload = {
        "policy_version": decision.policy_version,
        "state": decision.state.value,
        "actuation_intent": decision.actuation_intent.value,
        "controller_id": decision.controller_id.value,
        "reason_code": decision.reason_code.value if decision.reason_code else None,
        "reason_detail": decision.reason_detail,
        "predictive_blocked": decision.predictive_blocked,
        "transition": decision.transition,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ShadowDecision(decision, digest)


def compare_shadow_to_reactive(
    *, shadow_at_s: float | None, reactive_at_s: float | None
) -> ShadowTimingComparison:
    """Compare event timing only when both anchors are finite and qualified."""
    for value in (shadow_at_s, reactive_at_s):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError("timing anchors must be finite or None")
    if shadow_at_s is None or reactive_at_s is None:
        return ShadowTimingComparison("NOT_ESTIMABLE", None)
    return ShadowTimingComparison("ESTIMATED", reactive_at_s - shadow_at_s)
