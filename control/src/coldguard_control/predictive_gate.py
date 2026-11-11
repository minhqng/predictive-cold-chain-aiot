"""Fail-closed W14 gate between model evidence and predictive actuation.

The gate records whether B's recommendation is sufficiently specified for
offline shadow evaluation or for a later physical-enablement review.  It does
not enable Controller B and it never converts an uncalibrated risk score into
a probability.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .aiw import AIWStatus


class OutputSemantics(str, Enum):
    RISK_SCORE_ONLY = "RISK_SCORE_ONLY"
    CALIBRATED_PROBABILITY = "CALIBRATED_PROBABILITY"


class PredictiveGateStatus(str, Enum):
    BLOCKED_MISSING_POLICY = "BLOCKED_MISSING_POLICY"
    SHADOW_ONLY = "SHADOW_ONLY"
    ACTUATION_REVIEW_CANDIDATE = "ACTUATION_REVIEW_CANDIDATE"


@dataclass(frozen=True, slots=True)
class PredictiveCandidateEvidence:
    policy_version: str
    output_semantics: OutputSemantics
    score_threshold: float | None
    persistence_s: float | None
    horizon_s: float | None
    model_frozen: bool
    feature_contract_frozen: bool
    calibration_qualified: bool
    real_eligible_runs: int
    aiw_status: AIWStatus
    g3_green: bool
    g4_green: bool

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if not isinstance(self.output_semantics, OutputSemantics):
            raise ValueError("output_semantics must be OutputSemantics")
        if not isinstance(self.aiw_status, AIWStatus):
            raise ValueError("aiw_status must be AIWStatus")
        for name in (
            "model_frozen", "feature_contract_frozen", "calibration_qualified",
            "g3_green", "g4_green",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        if isinstance(self.real_eligible_runs, bool) or not isinstance(
            self.real_eligible_runs, int
        ) or self.real_eligible_runs < 0:
            raise ValueError("real_eligible_runs must be a non-negative integer")
        for name in ("score_threshold", "persistence_s", "horizon_s"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise ValueError(f"{name} must be finite or None")
        if self.score_threshold is not None and not 0 <= self.score_threshold <= 1:
            raise ValueError("score_threshold must be within [0, 1]")
        if self.persistence_s is not None and self.persistence_s <= 0:
            raise ValueError("persistence_s must be positive")
        if self.horizon_s is not None and self.horizon_s <= 0:
            raise ValueError("horizon_s must be positive")
        if (
            self.output_semantics is OutputSemantics.CALIBRATED_PROBABILITY
            and not self.calibration_qualified
        ):
            raise ValueError(
                "probability semantics require qualified calibration evidence"
            )


@dataclass(frozen=True, slots=True)
class PredictiveGateDecision:
    status: PredictiveGateStatus
    blockers: tuple[str, ...]
    probability_wording_allowed: bool
    physical_enablement: bool = False


def assess_predictive_gate(
    evidence: PredictiveCandidateEvidence,
) -> PredictiveGateDecision:
    """Classify W14 readiness without granting physical enablement."""
    if not isinstance(evidence, PredictiveCandidateEvidence):
        raise ValueError("evidence must be PredictiveCandidateEvidence")

    blockers: list[str] = []
    for field_name in ("score_threshold", "persistence_s", "horizon_s"):
        if getattr(evidence, field_name) is None:
            blockers.append(field_name)
    if not evidence.model_frozen:
        blockers.append("model_frozen")
    if not evidence.feature_contract_frozen:
        blockers.append("feature_contract_frozen")
    if evidence.real_eligible_runs < 1:
        blockers.append("real_eligible_runs")
    if evidence.aiw_status is not AIWStatus.POSITIVE_CANDIDATE:
        blockers.append("positive_aiw")
    if not evidence.g3_green:
        blockers.append("g3_green")
    if not evidence.g4_green:
        blockers.append("g4_green")

    missing_policy = any(
        getattr(evidence, name) is None
        for name in ("score_threshold", "persistence_s", "horizon_s")
    )
    if missing_policy:
        status = PredictiveGateStatus.BLOCKED_MISSING_POLICY
    elif blockers:
        status = PredictiveGateStatus.SHADOW_ONLY
    else:
        status = PredictiveGateStatus.ACTUATION_REVIEW_CANDIDATE

    return PredictiveGateDecision(
        status=status,
        blockers=tuple(blockers),
        probability_wording_allowed=(
            evidence.output_semantics is OutputSemantics.CALIBRATED_PROBABILITY
            and evidence.calibration_qualified
        ),
    )
