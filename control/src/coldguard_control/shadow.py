"""W17 predictive shadow adapter with an explicit no-command invariant.

W17 Shadow Exit Report aggregates:
- False policy transitions
- Stale-state issues
- Unresolved ambiguity
- Safety-block reasons

No commands are emitted - this is a pure assessment layer.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum

from .config import PolicyConfig
from .policy import PolicyDecision, PolicyInput, evaluate_policy


class ShadowExitStatus(str, Enum):
    """W17 shadow exit status classification."""
    CLEAN_EXIT = "CLEAN_EXIT"
    FALSE_TRANSITION_DETECTED = "FALSE_TRANSITION_DETECTED"
    STALE_STATE_ISSUE = "STALE_STATE_ISSUE"
    UNRESOLVED_AMBIGUITY = "UNRESOLVED_AMBIGUITY"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    MULTIPLE_ISSUES = "MULTIPLE_ISSUES"


@dataclass(frozen=True, slots=True)
class FalsePolicyTransition:
    """W17 false policy transition record.

    Documents a policy transition that did not correspond to actual
    physical state change - a false positive in policy decision.
    """
    transition_id: str
    from_state: str
    to_state: str
    predicted_at_s: float
    physical_state_unchanged: bool  # Must be True for false transition
    reason: str  # Why this was a false transition

    def __post_init__(self) -> None:
        if not isinstance(self.transition_id, str) or not self.transition_id.strip():
            raise ValueError("transition_id must be non-empty string")
        if not isinstance(self.from_state, str) or not self.from_state.strip():
            raise ValueError("from_state must be non-empty string")
        if not isinstance(self.to_state, str) or not self.to_state.strip():
            raise ValueError("to_state must be non-empty string")
        if isinstance(self.predicted_at_s, bool) or not isinstance(self.predicted_at_s, (int, float)) or not math.isfinite(self.predicted_at_s):
            raise ValueError("predicted_at_s must be finite number")
        if not isinstance(self.physical_state_unchanged, bool):
            raise ValueError("physical_state_unchanged must be boolean")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be non-empty string")


@dataclass(frozen=True, slots=True)
class StaleStateIssue:
    """W17 stale-state issue record.

    Documents when the shadow model operated on outdated state information.
    """
    issue_id: str
    state_age_at_decision_s: float  # How stale the state was
    max_freshness_bound_s: float  # Expected freshness bound
    decision_affected: bool  # Whether the decision was impacted

    def __post_init__(self) -> None:
        if not isinstance(self.issue_id, str) or not self.issue_id.strip():
            raise ValueError("issue_id must be non-empty string")
        if isinstance(self.state_age_at_decision_s, bool) or not isinstance(self.state_age_at_decision_s, (int, float)) or self.state_age_at_decision_s < 0:
            raise ValueError("state_age_at_decision_s must be non-negative number")
        if isinstance(self.max_freshness_bound_s, bool) or not isinstance(self.max_freshness_bound_s, (int, float)) or self.max_freshness_bound_s <= 0:
            raise ValueError("max_freshness_bound_s must be positive number")
        if not isinstance(self.decision_affected, bool):
            raise ValueError("decision_affected must be boolean")


@dataclass(frozen=True, slots=True)
class UnresolvedAmbiguity:
    """W17 unresolved ambiguity record.

    Documents ambiguous situations where the policy could not make a
    clear decision due to conflicting or insufficient evidence.
    """
    ambiguity_id: str
    ambiguity_type: str  # Type of ambiguity (e.g., "CONFLICTING_SENSORS")
    affected_decision: str  # The decision that was ambiguous
    resolution_method: str  # How it was resolved (or "UNRESOLVED")

    def __post_init__(self) -> None:
        if not isinstance(self.ambiguity_id, str) or not self.ambiguity_id.strip():
            raise ValueError("ambiguity_id must be non-empty string")
        if not isinstance(self.ambiguity_type, str) or not self.ambiguity_type.strip():
            raise ValueError("ambiguity_type must be non-empty string")
        if not isinstance(self.affected_decision, str) or not self.affected_decision.strip():
            raise ValueError("affected_decision must be non-empty string")
        if not isinstance(self.resolution_method, str) or not self.resolution_method.strip():
            raise ValueError("resolution_method must be non-empty string")


@dataclass(frozen=True, slots=True)
class SafetyBlockReason:
    """W17 safety-block reason record.

    Documents when a predictive decision was blocked by safety constraints.
    No commands are emitted - this is assessment only.
    """
    block_id: str
    safety_constraint: str  # Which safety constraint triggered the block
    blocked_action: str  # What action was blocked
    block_justified: bool  # Whether the block was correct

    def __post_init__(self) -> None:
        if not isinstance(self.block_id, str) or not self.block_id.strip():
            raise ValueError("block_id must be non-empty string")
        if not isinstance(self.safety_constraint, str) or not self.safety_constraint.strip():
            raise ValueError("safety_constraint must be non-empty string")
        if not isinstance(self.blocked_action, str) or not self.blocked_action.strip():
            raise ValueError("blocked_action must be non-empty string")
        if not isinstance(self.block_justified, bool):
            raise ValueError("block_justified must be boolean")


@dataclass(frozen=True, slots=True)
class ShadowExitReport:
    """W17 shadow exit report aggregating all exit issues.

    Aggregates false policy transitions, stale-state issues,
    unresolved ambiguity, and safety-block reasons.

    IMPORTANT: No commands are emitted - this is assessment only.
    """
    false_transitions: tuple[FalsePolicyTransition, ...]
    stale_state_issues: tuple[StaleStateIssue, ...]
    unresolved_ambiguities: tuple[UnresolvedAmbiguity, ...]
    safety_block_reasons: tuple[SafetyBlockReason, ...]
    total_shadow_decisions: int
    total_commands_emitted: int = 0  # Must be 0 - no commands in shadow

    def __post_init__(self) -> None:
        if not isinstance(self.false_transitions, tuple) or not all(
            isinstance(t, FalsePolicyTransition) for t in self.false_transitions
        ):
            raise ValueError("false_transitions must be tuple of FalsePolicyTransition")
        if not isinstance(self.stale_state_issues, tuple) or not all(
            isinstance(i, StaleStateIssue) for i in self.stale_state_issues
        ):
            raise ValueError("stale_state_issues must be tuple of StaleStateIssue")
        if not isinstance(self.unresolved_ambiguities, tuple) or not all(
            isinstance(a, UnresolvedAmbiguity) for a in self.unresolved_ambiguities
        ):
            raise ValueError("unresolved_ambiguities must be tuple of UnresolvedAmbiguity")
        if not isinstance(self.safety_block_reasons, tuple) or not all(
            isinstance(r, SafetyBlockReason) for r in self.safety_block_reasons
        ):
            raise ValueError("safety_block_reasons must be tuple of SafetyBlockReason")
        if isinstance(self.total_shadow_decisions, bool) or not isinstance(self.total_shadow_decisions, int) or self.total_shadow_decisions < 0:
            raise ValueError("total_shadow_decisions must be non-negative integer")
        if isinstance(self.total_commands_emitted, bool) or not isinstance(self.total_commands_emitted, int) or self.total_commands_emitted != 0:
            raise ValueError("total_commands_emitted must be 0 (no commands in shadow)")

    @property
    def exit_status(self) -> ShadowExitStatus:
        """Determine overall exit status based on issues found."""
        issues = []
        if len(self.false_transitions) > 0:
            issues.append("false_transition")
        if len(self.stale_state_issues) > 0:
            issues.append("stale_state")
        if len(self.unresolved_ambiguities) > 0:
            issues.append("unresolved_ambiguity")
        if len(self.safety_block_reasons) > 0:
            issues.append("safety_block")

        if len(issues) == 0:
            return ShadowExitStatus.CLEAN_EXIT
        elif len(issues) > 1:
            return ShadowExitStatus.MULTIPLE_ISSUES
        elif "false_transition" in issues:
            return ShadowExitStatus.FALSE_TRANSITION_DETECTED
        elif "stale_state" in issues:
            return ShadowExitStatus.STALE_STATE_ISSUE
        elif "unresolved_ambiguity" in issues:
            return ShadowExitStatus.UNRESOLVED_AMBIGUITY
        elif "safety_block" in issues:
            return ShadowExitStatus.SAFETY_BLOCKED
        return ShadowExitStatus.CLEAN_EXIT


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


def build_shadow_exit_report(
    false_transitions: list[FalsePolicyTransition],
    stale_state_issues: list[StaleStateIssue],
    unresolved_ambiguities: list[UnresolvedAmbiguity],
    safety_block_reasons: list[SafetyBlockReason],
    total_shadow_decisions: int,
) -> ShadowExitReport:
    """Build a W17 shadow exit report.

    W17 requirement: No commands emitted - total_commands_emitted is always 0.
    """
    return ShadowExitReport(
        false_transitions=tuple(false_transitions),
        stale_state_issues=tuple(stale_state_issues),
        unresolved_ambiguities=tuple(unresolved_ambiguities),
        safety_block_reasons=tuple(safety_block_reasons),
        total_shadow_decisions=total_shadow_decisions,
        total_commands_emitted=0,  # Invariant: no commands in shadow
    )
