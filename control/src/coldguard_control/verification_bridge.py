"""A-to-D verification vocabulary bridge.

Member A's command trace uses stage names ending in ``*_VERIFIED`` for
run-level observational promotion.  Member D's health vocabulary has a
stronger authority rule: no stage name alone may become ``VERIFIED`` or
``HEALTHY_RESPONSE``.  This bridge makes that boundary executable.
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import CoolingHealthState, EnvelopeQualification


A_LIFECYCLE_ORDER = (
    "COMMAND_SEEN",
    "DEVICE_ACK",
    "APPLIED_STATE",
    "ELECTRICAL_VERIFIED",
    "THERMAL_VERIFIED",
)


@dataclass(frozen=True, slots=True)
class AObservationalLifecycle:
    command_id: str
    stages: tuple[str, ...]
    usable_for_health_claim: bool
    firmware_executed: bool
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.command_id, str) or not self.command_id.strip():
            raise ValueError("command_id must be non-empty")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be non-empty")
        for name in ("usable_for_health_claim", "firmware_executed"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        if not isinstance(self.stages, tuple) or not all(
            isinstance(stage, str) for stage in self.stages
        ):
            raise ValueError("stages must be a tuple of strings")
        unknown = tuple(stage for stage in self.stages if stage not in A_LIFECYCLE_ORDER)
        if unknown:
            raise ValueError(f"unknown A lifecycle stages: {unknown}")
        indexes = tuple(A_LIFECYCLE_ORDER.index(stage) for stage in self.stages)
        if indexes != tuple(sorted(set(indexes))):
            raise ValueError("A lifecycle stages must be unique and ordered")


@dataclass(frozen=True, slots=True)
class AtoDVerificationDecision:
    command_id: str
    observational_chain_complete: bool
    eligible_for_d_tracker_input: bool
    direct_health_promotion_allowed: bool
    d_health_state: CoolingHealthState
    reason: str


def assess_a_lifecycle_for_d(
    lifecycle: AObservationalLifecycle,
    qualification: EnvelopeQualification,
) -> AtoDVerificationDecision:
    """Classify A evidence while reserving D health authority for its tracker."""
    if not isinstance(lifecycle, AObservationalLifecycle):
        raise ValueError("lifecycle must be AObservationalLifecycle")
    if not isinstance(qualification, EnvelopeQualification):
        raise ValueError("qualification must be EnvelopeQualification")

    complete = lifecycle.stages == A_LIFECYCLE_ORDER
    eligible = (
        complete
        and lifecycle.firmware_executed
        and lifecycle.usable_for_health_claim
        and qualification is EnvelopeQualification.QUALIFIED
    )
    if not lifecycle.firmware_executed:
        reason = "FIXTURE_OR_HOST_TRACE_NOT_PHYSICAL"
    elif not lifecycle.usable_for_health_claim:
        reason = "A_OBSERVATIONAL_PROMOTION_ONLY"
    elif qualification is not EnvelopeQualification.QUALIFIED:
        reason = "D_ENVELOPE_NOT_QUALIFIED"
    elif not complete:
        reason = "A_LIFECYCLE_INCOMPLETE"
    else:
        reason = "ELIGIBLE_AS_TRACKER_INPUT_NOT_A_HEALTH_VERDICT"

    return AtoDVerificationDecision(
        command_id=lifecycle.command_id,
        observational_chain_complete=complete,
        eligible_for_d_tracker_input=eligible,
        direct_health_promotion_allowed=False,
        d_health_state=CoolingHealthState.UNKNOWN,
        reason=reason,
    )
