"""Pure fail-closed physical enablement gate for Controller B (Member D, W18).

This module implements the W18 preconditions and controlled enablement gate
before any physical predictive actuation may be reviewed or enabled.

Authority rules:
- AI never actuates directly.
- The gate is pure and fail-closed: it never emits a physical command.
- Strict boolean/type validation on all fields; no invented numeric physical thresholds.
- Evaluates explicit enable request and all documented prerequisites:
  G4 GREEN, stable A physical envelope, frozen B model/policy/action,
  stable C command trace, complete prediction-to-thermal trace,
  failure behavior, clean dry runs, and A/B/C/D witnesses.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EnablementStatus(str, Enum):
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    REVIEW_READY = "REVIEW_READY"


@dataclass(frozen=True, slots=True)
class EnablementPreconditions:
    enable_requested: bool
    g4_green: bool
    a_physical_envelope_stable: bool
    b_model_frozen: bool
    b_policy_frozen: bool
    b_action_frozen: bool
    c_command_trace_stable: bool
    complete_prediction_to_thermal_trace: bool
    failure_behavior_frozen: bool
    clean_dry_runs_verified: bool
    witness_member_a: bool
    witness_member_b: bool
    witness_member_c: bool
    witness_member_d: bool

    def __post_init__(self) -> None:
        expected_fields = (
            "enable_requested",
            "g4_green",
            "a_physical_envelope_stable",
            "b_model_frozen",
            "b_policy_frozen",
            "b_action_frozen",
            "c_command_trace_stable",
            "complete_prediction_to_thermal_trace",
            "failure_behavior_frozen",
            "clean_dry_runs_verified",
            "witness_member_a",
            "witness_member_b",
            "witness_member_c",
            "witness_member_d",
        )
        for name in expected_fields:
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be a strict boolean, got {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class EnablementDecision:
    status: EnablementStatus
    blockers: tuple[str, ...]
    review_ready: bool
    physical_command_emitted: bool = False


def evaluate_physical_enablement(
    preconditions: EnablementPreconditions,
) -> EnablementDecision:
    """Evaluate physical enablement preconditions fail-closed without physical actuation."""
    if not isinstance(preconditions, EnablementPreconditions):
        raise TypeError(
            f"preconditions must be EnablementPreconditions, got {type(preconditions).__name__}"
        )

    blockers: list[str] = []

    if not preconditions.g4_green:
        blockers.append("g4_green")
    if not preconditions.a_physical_envelope_stable:
        blockers.append("a_physical_envelope_stable")
    if not preconditions.b_model_frozen:
        blockers.append("b_model_frozen")
    if not preconditions.b_policy_frozen:
        blockers.append("b_policy_frozen")
    if not preconditions.b_action_frozen:
        blockers.append("b_action_frozen")
    if not preconditions.c_command_trace_stable:
        blockers.append("c_command_trace_stable")
    if not preconditions.complete_prediction_to_thermal_trace:
        blockers.append("complete_prediction_to_thermal_trace")
    if not preconditions.failure_behavior_frozen:
        blockers.append("failure_behavior_frozen")
    if not preconditions.clean_dry_runs_verified:
        blockers.append("clean_dry_runs_verified")
    if not preconditions.witness_member_a:
        blockers.append("witness_member_a")
    if not preconditions.witness_member_b:
        blockers.append("witness_member_b")
    if not preconditions.witness_member_c:
        blockers.append("witness_member_c")
    if not preconditions.witness_member_d:
        blockers.append("witness_member_d")

    if not preconditions.enable_requested:
        return EnablementDecision(
            status=EnablementStatus.DISABLED,
            blockers=tuple(blockers),
            review_ready=False,
            physical_command_emitted=False,
        )

    if blockers:
        return EnablementDecision(
            status=EnablementStatus.BLOCKED,
            blockers=tuple(blockers),
            review_ready=False,
            physical_command_emitted=False,
        )

    return EnablementDecision(
        status=EnablementStatus.REVIEW_READY,
        blockers=(),
        review_ready=True,
        physical_command_emitted=False,
    )
