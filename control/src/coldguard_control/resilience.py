"""W16 remote-path resilience gate for Controller B.

W16 Requirements:
- Separate software-vector green from signed G4
- g4_ready requires live evidence reference and explicit signoff
- Do not fake live evidence in builders/tests
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class ResilienceMode(str, Enum):
    ONLINE_REMOTE = "ONLINE_REMOTE"
    ONLINE_REACTIVE_ONLY = "ONLINE_REACTIVE_ONLY"
    SAFE_LOCAL = "SAFE_LOCAL"


class G4ReadinessStatus(str, Enum):
    """W16 G4 readiness status: software vector separate from signed G4."""

    NOT_ASSESSED = "NOT_ASSESSED"
    SOFTWARE_VECTOR_GREEN = "SOFTWARE_VECTOR_GREEN"
    LIVE_RESILIENCE_SIGNED = "LIVE_RESILIENCE_SIGNED"


@dataclass(frozen=True, slots=True)
class G4ReadinessEvidence:
    """W16 G4 readiness evidence.

    Separates software-vector green from signed G4.
    g4_ready requires live resilience evidence and explicit signoff.
    """
    software_vector_green: bool
    live_resilience_evidence: bool  # Must be True for G4 readiness
    resilience_signoff_member: str  # Member who signed off (D for live)
    resilience_signoff_timestamp: str  # ISO 8601 timestamp
    resilience_test_scenarios: tuple[str, ...]  # Tested scenarios
    evidence_reference: str | None = None  # Live evidence reference

    def __post_init__(self) -> None:
        if not isinstance(self.software_vector_green, bool):
            raise ValueError("software_vector_green must be boolean")
        if not isinstance(self.live_resilience_evidence, bool):
            raise ValueError("live_resilience_evidence must be boolean")
        if not isinstance(self.resilience_signoff_member, str) or not self.resilience_signoff_member.strip():
            raise ValueError("resilience_signoff_member must be non-empty string")
        if not isinstance(self.resilience_signoff_timestamp, str) or not self.resilience_signoff_timestamp.strip():
            raise ValueError("resilience_signoff_timestamp must be non-empty string")
        if not isinstance(self.resilience_test_scenarios, tuple) or len(self.resilience_test_scenarios) == 0:
            raise ValueError("resilience_test_scenarios must be non-empty tuple")
        if not all(isinstance(s, str) and s.strip() for s in self.resilience_test_scenarios):
            raise ValueError("all resilience_test_scenarios must be non-empty strings")
        if self.evidence_reference is not None and (
            not isinstance(self.evidence_reference, str)
            or not self.evidence_reference.strip()
        ):
            raise ValueError("evidence_reference must be non-empty when provided")
        if self.live_resilience_evidence and self.evidence_reference is None:
            raise ValueError("live resilience evidence requires evidence_reference")


@dataclass(frozen=True, slots=True)
class ResilienceInput:
    ai_available: bool
    prediction_fresh: bool
    broker_available: bool
    backend_available: bool
    db_available: bool
    state_resynced: bool
    stale_command_pending: bool
    network_stable_s: float
    required_stable_s: float
    # W16: G4 readiness evidence
    g4_readiness_evidence: G4ReadinessEvidence | None = None

    def __post_init__(self) -> None:
        for name in (
            "ai_available", "prediction_fresh", "broker_available",
            "backend_available", "db_available", "state_resynced",
            "stale_command_pending",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        for name in ("network_stable_s", "required_stable_s"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise ValueError(f"{name} must be a finite non-negative number")
        if self.g4_readiness_evidence is not None:
            if not isinstance(self.g4_readiness_evidence, G4ReadinessEvidence):
                raise ValueError("g4_readiness_evidence must be G4ReadinessEvidence or None")


@dataclass(frozen=True, slots=True)
class ResilienceDecision:
    mode: ResilienceMode
    controller_b_available: bool
    allow_new_predictive_command: bool
    stale_prediction_reused: bool
    # W16: Separate g4_ready from software_vector_green
    g4_ready: bool
    software_vector_green: bool
    blockers: tuple[str, ...]


def assess_resilience(state: ResilienceInput) -> ResilienceDecision:
    """Fail closed across AI, broker, backend, DB and reconnect state.

    W16: g4_ready requires live resilience evidence and explicit signoff.
    Software-vector green alone is not sufficient.
    """
    if not isinstance(state, ResilienceInput):
        raise ValueError("state must be ResilienceInput")

    blockers: list[str] = []
    if not state.ai_available:
        blockers.append("ai_unavailable")
    if not state.prediction_fresh:
        blockers.append("prediction_stale")
    if not state.broker_available:
        blockers.append("broker_unavailable")
    if not state.backend_available:
        blockers.append("backend_unavailable")
    if not state.db_available:
        blockers.append("db_unavailable")
    if not state.state_resynced:
        blockers.append("state_not_resynced")
    if state.stale_command_pending:
        blockers.append("stale_command_pending")
    if state.network_stable_s < state.required_stable_s:
        blockers.append("network_not_stable")

    remote_path_blocked = any(
        blocker in blockers for blocker in (
            "broker_unavailable", "backend_unavailable", "state_not_resynced",
            "stale_command_pending", "network_not_stable",
        )
    )
    if remote_path_blocked:
        mode = ResilienceMode.SAFE_LOCAL
    elif blockers:
        mode = ResilienceMode.ONLINE_REACTIVE_ONLY
    else:
        mode = ResilienceMode.ONLINE_REMOTE

    # W16: Software vector green is separate from G4 readiness
    software_vector_green = not blockers

    # W16: g4_ready requires live resilience evidence and explicit signoff
    g4_ready = (
        software_vector_green
        and state.g4_readiness_evidence is not None
        and state.g4_readiness_evidence.live_resilience_evidence
        and state.g4_readiness_evidence.software_vector_green
        and bool(state.g4_readiness_evidence.resilience_signoff_member.strip())
        and bool(state.g4_readiness_evidence.resilience_signoff_timestamp.strip())
        and bool(state.g4_readiness_evidence.evidence_reference)
    )

    ready = not blockers
    return ResilienceDecision(
        mode=mode,
        controller_b_available=ready,
        allow_new_predictive_command=ready,
        stale_prediction_reused=False,
        g4_ready=g4_ready,
        software_vector_green=software_vector_green,
        blockers=tuple(blockers),
    )
