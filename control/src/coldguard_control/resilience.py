"""W16 remote-path resilience gate for Controller B."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class ResilienceMode(str, Enum):
    ONLINE_REMOTE = "ONLINE_REMOTE"
    ONLINE_REACTIVE_ONLY = "ONLINE_REACTIVE_ONLY"
    SAFE_LOCAL = "SAFE_LOCAL"


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


@dataclass(frozen=True, slots=True)
class ResilienceDecision:
    mode: ResilienceMode
    controller_b_available: bool
    allow_new_predictive_command: bool
    stale_prediction_reused: bool
    g4_ready: bool
    blockers: tuple[str, ...]


def assess_resilience(state: ResilienceInput) -> ResilienceDecision:
    """Fail closed across AI, broker, backend, DB and reconnect state."""
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

    ready = not blockers
    return ResilienceDecision(
        mode=mode,
        controller_b_available=ready,
        allow_new_predictive_command=ready,
        stale_prediction_reused=False,
        g4_ready=ready,
        blockers=tuple(blockers),
    )
