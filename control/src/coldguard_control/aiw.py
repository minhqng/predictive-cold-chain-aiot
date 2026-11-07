"""Candidate actionable-intervention-window calculation (Member D, W13).

The calculation joins B warning timing, A physical response and C system
latency only when every input has explicit provenance and qualified status.
It never enables Controller B; G3 and the W14 policy gate remain separate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class AIWStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    POSITIVE_CANDIDATE = "POSITIVE_CANDIDATE"
    NON_POSITIVE = "NON_POSITIVE"


@dataclass(frozen=True, slots=True)
class TimingEvidence:
    """One timestamp or duration, with caller-owned qualification."""

    value_s: float | None
    source: str
    qualified: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("timing source must be non-empty")
        if not isinstance(self.qualified, bool):
            raise ValueError("qualified must be a boolean")
        if self.value_s is not None and (
            isinstance(self.value_s, bool)
            or not isinstance(self.value_s, (int, float))
            or not math.isfinite(float(self.value_s))
        ):
            raise ValueError("timing value must be finite or None")
        if self.qualified and self.value_s is None:
            raise ValueError("qualified timing requires a value")


@dataclass(frozen=True, slots=True)
class AIWInput:
    run_id: str
    hardware_config_id: str
    policy_version: str
    warning_at: TimingEvidence
    critical_at: TimingEvidence
    physical_response_delay: TimingEvidence
    system_latency: TimingEvidence
    warning_clock_domain: str
    critical_clock_domain: str
    warning_run_id: str
    critical_run_id: str
    response_hardware_config_id: str

    def __post_init__(self) -> None:
        for name in (
            "run_id", "hardware_config_id", "policy_version",
            "warning_clock_domain", "critical_clock_domain",
            "warning_run_id", "critical_run_id", "response_hardware_config_id",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        for name in (
            "warning_at", "critical_at", "physical_response_delay", "system_latency"
        ):
            if not isinstance(getattr(self, name), TimingEvidence):
                raise ValueError(f"{name} must be TimingEvidence")
        for name in ("physical_response_delay", "system_latency"):
            value = getattr(self, name).value_s
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True, slots=True)
class AIWResult:
    run_id: str
    policy_version: str
    status: AIWStatus
    value_s: float | None
    missing: tuple[str, ...]
    physical_enablement: bool = False


def assess_aiw(inputs: AIWInput) -> AIWResult:
    """Compute Doc 02 §27 AIW, refusing incomplete or incomparable evidence."""
    if not isinstance(inputs, AIWInput):
        raise ValueError("inputs must be AIWInput")
    missing = tuple(
        name for name in (
            "warning_at", "critical_at", "physical_response_delay", "system_latency"
        )
        if not getattr(inputs, name).qualified
        or getattr(inputs, name).value_s is None
    )
    if inputs.warning_clock_domain != inputs.critical_clock_domain:
        missing += ("common_warning_critical_clock",)
    if inputs.warning_run_id != inputs.run_id or inputs.critical_run_id != inputs.run_id:
        missing += ("common_run_id",)
    if inputs.response_hardware_config_id != inputs.hardware_config_id:
        missing += ("common_hardware_config",)
    if missing:
        return AIWResult(
            inputs.run_id, inputs.policy_version, AIWStatus.UNKNOWN, None, missing
        )
    assert inputs.warning_at.value_s is not None
    assert inputs.critical_at.value_s is not None
    assert inputs.physical_response_delay.value_s is not None
    assert inputs.system_latency.value_s is not None
    value_s = (
        inputs.critical_at.value_s
        - inputs.warning_at.value_s
        - inputs.physical_response_delay.value_s
        - inputs.system_latency.value_s
    )
    if not math.isfinite(value_s):
        return AIWResult(
            inputs.run_id, inputs.policy_version, AIWStatus.UNKNOWN,
            None, ("finite_aiw",),
        )
    return AIWResult(
        inputs.run_id,
        inputs.policy_version,
        AIWStatus.POSITIVE_CANDIDATE if value_s > 0 else AIWStatus.NON_POSITIVE,
        value_s,
        (),
    )
