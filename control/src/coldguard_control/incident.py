"""Reviewable W11 incident-action candidates, without actuator side effects.

The mapping answers D-W11-04's five action questions for each observable
cooling-health state. Physical fault campaigns and A/C integration are still
required before a deployment may enforce these recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import CoolingHealthState, IncidentAction

CANDIDATE_MAP_VERSION = "d-w11-candidate-v1"


@dataclass(frozen=True, slots=True)
class IncidentRecommendation:
    health: CoolingHealthState
    actions: tuple[IncidentAction, ...]
    rationale: str
    mapping_version: str = CANDIDATE_MAP_VERSION
    mapping_status: str = "CANDIDATE_NOT_RUNTIME_APPROVED"
    actuates: bool = False


_CANDIDATE_ACTIONS: dict[CoolingHealthState, tuple[IncidentAction, ...]] = {
    CoolingHealthState.HEALTHY_RESPONSE: (),
    CoolingHealthState.ELECTRICAL_RESPONSE_MISSING: (
        IncidentAction.WARN,
        IncidentAction.BLOCK_PREDICTIVE,
    ),
    CoolingHealthState.THERMAL_EFFECTIVENESS_DEGRADED: (
        IncidentAction.WARN,
        IncidentAction.BLOCK_PREDICTIVE,
    ),
    CoolingHealthState.CONTROL_ELECTRICAL_ANOMALY: (
        IncidentAction.WARN,
        IncidentAction.BLOCK_PREDICTIVE,
        IncidentAction.ENTER_LOCKOUT,
    ),
    CoolingHealthState.UNKNOWN: (
        IncidentAction.WARN,
        IncidentAction.BLOCK_PREDICTIVE,
    ),
}


def recommend_incident_actions(
    health: CoolingHealthState, *, thermal_safety_usable: bool
) -> IncidentRecommendation:
    """Return a candidate disposition, never an executable actuator command."""
    if not isinstance(health, CoolingHealthState):
        raise ValueError("health must be a CoolingHealthState")
    if not isinstance(thermal_safety_usable, bool):
        raise ValueError("thermal_safety_usable must be a boolean")
    if health is CoolingHealthState.HEALTHY_RESPONSE and not thermal_safety_usable:
        raise ValueError("HEALTHY_RESPONSE contradicts unusable thermal safety state")
    actions = _CANDIDATE_ACTIONS[health]
    if health is CoolingHealthState.UNKNOWN and thermal_safety_usable:
        # Missing electrical evidence alone must not remove local thermal
        # protection (Doc 01 F-ELEC-01; Doc 02 degraded-mode contract).
        actions += (IncidentAction.USE_LOCAL_THRESHOLD,)
    rationale = {
        CoolingHealthState.HEALTHY_RESPONSE: "qualified response; no incident",
        CoolingHealthState.ELECTRICAL_RESPONSE_MISSING:
            "W10 oracle: hold new actuation and block predictive; no root cause or lockout invented",
        CoolingHealthState.THERMAL_EFFECTIVENESS_DEGRADED:
            "effectiveness concern; physical disposition needs A's controlled evidence",
        CoolingHealthState.CONTROL_ELECTRICAL_ANOMALY:
            "unexpected OFF current is a lockout-class anomaly; hardware interlock remains authoritative",
        CoolingHealthState.UNKNOWN:
            "insufficient/conflicting response evidence; preserve local threshold only when thermal state is usable",
    }[health]
    return IncidentRecommendation(health, actions, rationale)
