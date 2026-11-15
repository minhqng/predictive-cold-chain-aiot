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

W16 Requirements:
- Separate software-vector green from signed G4
- g4_ready requires explicit live resilience evidence and signoff

W18 Requirements:
- Pinned policy/config/action identifiers (not just booleans)
- Threshold/persistence in review-ready gate (explicit values)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .resilience import G4ReadinessEvidence, G4ReadinessStatus


class EnablementStatus(str, Enum):
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    REVIEW_READY = "REVIEW_READY"


@dataclass(frozen=True, slots=True)
class EnablementPreconditions:
    enable_requested: bool
    g4_green: bool
    g4_readiness_evidence: G4ReadinessEvidence | None  # W16: explicit evidence
    a_physical_envelope_stable: bool
    b_model_frozen: bool
    b_policy_frozen: bool
    b_action_frozen: bool
    # W18: Pinned identifiers instead of just booleans
    policy_id: str  # Pinned policy identifier
    config_id: str  # Pinned config identifier
    action_id: str  # Pinned action identifier
    score_threshold: float | None  # W18: explicit threshold value
    persistence_s: float | None  # W18: explicit persistence value
    c_command_trace_stable: bool
    complete_prediction_to_thermal_trace: bool
    failure_behavior_frozen: bool
    clean_dry_runs_verified: bool
    witness_member_a: bool
    witness_member_b: bool
    witness_member_c: bool
    witness_member_d: bool

    def __post_init__(self) -> None:
        expected_bool_fields = (
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
        for name in expected_bool_fields:
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be a strict boolean, got {type(value).__name__}")

        # W18: Pinned identifier validation
        for name in ("policy_id", "config_id", "action_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise TypeError(f"{name} must be a non-empty string (pinned identifier)")

        # W18 records the frozen value; its scale belongs to the W14 output
        # semantics and must not be reinterpreted here.
        if self.score_threshold is not None:
            if isinstance(self.score_threshold, bool) or not isinstance(self.score_threshold, (int, float)):
                raise TypeError("score_threshold must be float or None")
            if not math.isfinite(float(self.score_threshold)):
                raise ValueError("score_threshold must be finite")
        if self.persistence_s is not None:
            if isinstance(self.persistence_s, bool) or not isinstance(self.persistence_s, (int, float)):
                raise TypeError("persistence_s must be float or None")
            if not math.isfinite(float(self.persistence_s)) or self.persistence_s <= 0:
                raise ValueError("persistence_s must be positive and finite")

        # W16: G4 readiness evidence validation
        if self.g4_readiness_evidence is not None:
            if not isinstance(self.g4_readiness_evidence, G4ReadinessEvidence):
                raise TypeError("g4_readiness_evidence must be G4ReadinessEvidence or None")


@dataclass(frozen=True, slots=True)
class EnablementDecision:
    status: EnablementStatus
    blockers: tuple[str, ...]
    review_ready: bool
    g4_ready: bool  # W16: explicit G4 readiness
    policy_id: str | None  # W18: pinned identifier in decision
    config_id: str | None  # W18: pinned identifier in decision
    action_id: str | None  # W18: pinned identifier in decision
    score_threshold: float | None  # W18: threshold in decision
    persistence_s: float | None  # W18: persistence in decision
    physical_command_emitted: bool = False


def evaluate_physical_enablement(
    preconditions: EnablementPreconditions,
) -> EnablementDecision:
    """Evaluate physical enablement preconditions fail-closed without physical actuation.

    W16: g4_ready requires explicit live resilience evidence and signoff.
    W18: review_ready requires pinned policy/config/action identifiers and threshold/persistence.
    """
    if not isinstance(preconditions, EnablementPreconditions):
        raise TypeError(
            f"preconditions must be EnablementPreconditions, got {type(preconditions).__name__}"
        )

    blockers: list[str] = []

    # W16: G4 readiness with live resilience evidence
    g4_ready = (
        preconditions.g4_green
        and preconditions.g4_readiness_evidence is not None
        and preconditions.g4_readiness_evidence.live_resilience_evidence
        and preconditions.g4_readiness_evidence.software_vector_green
        and bool(preconditions.g4_readiness_evidence.evidence_reference)
    )
    if not g4_ready:
        blockers.append("g4_ready")

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

    # W18: Pinned identifiers required
    if not preconditions.policy_id.strip():
        blockers.append("policy_id_required")
    if not preconditions.config_id.strip():
        blockers.append("config_id_required")
    if not preconditions.action_id.strip():
        blockers.append("action_id_required")

    # W18: Threshold/persistence required for review-ready
    if preconditions.score_threshold is None:
        blockers.append("score_threshold_required")
    if preconditions.persistence_s is None:
        blockers.append("persistence_s_required")

    if not preconditions.enable_requested:
        return EnablementDecision(
            status=EnablementStatus.DISABLED,
            blockers=tuple(blockers),
            review_ready=False,
            g4_ready=g4_ready,
            policy_id=preconditions.policy_id if preconditions.policy_id.strip() else None,
            config_id=preconditions.config_id if preconditions.config_id.strip() else None,
            action_id=preconditions.action_id if preconditions.action_id.strip() else None,
            score_threshold=preconditions.score_threshold,
            persistence_s=preconditions.persistence_s,
            physical_command_emitted=False,
        )

    if blockers:
        return EnablementDecision(
            status=EnablementStatus.BLOCKED,
            blockers=tuple(blockers),
            review_ready=False,
            g4_ready=g4_ready,
            policy_id=preconditions.policy_id if preconditions.policy_id.strip() else None,
            config_id=preconditions.config_id if preconditions.config_id.strip() else None,
            action_id=preconditions.action_id if preconditions.action_id.strip() else None,
            score_threshold=preconditions.score_threshold,
            persistence_s=preconditions.persistence_s,
            physical_command_emitted=False,
        )

    return EnablementDecision(
        status=EnablementStatus.REVIEW_READY,
        blockers=(),
        review_ready=True,
        g4_ready=g4_ready,
        policy_id=preconditions.policy_id,
        config_id=preconditions.config_id,
        action_id=preconditions.action_id,
        score_threshold=preconditions.score_threshold,
        persistence_s=preconditions.persistence_s,
        physical_command_emitted=False,
    )
