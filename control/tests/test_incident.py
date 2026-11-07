import pytest

from coldguard_control.incident import recommend_incident_actions
from coldguard_control.types import CoolingHealthState, IncidentAction


@pytest.mark.parametrize(
    ("health", "expected"),
    [
        (CoolingHealthState.HEALTHY_RESPONSE, ()),
        (CoolingHealthState.ELECTRICAL_RESPONSE_MISSING,
         (IncidentAction.WARN, IncidentAction.BLOCK_PREDICTIVE)),
        (CoolingHealthState.THERMAL_EFFECTIVENESS_DEGRADED,
         (IncidentAction.WARN, IncidentAction.BLOCK_PREDICTIVE)),
        (CoolingHealthState.CONTROL_ELECTRICAL_ANOMALY,
         (IncidentAction.WARN, IncidentAction.BLOCK_PREDICTIVE,
          IncidentAction.ENTER_LOCKOUT)),
    ],
)
def test_candidate_mapping_has_no_actuator_side_effect(health, expected):
    recommendation = recommend_incident_actions(
        health, thermal_safety_usable=True
    )
    assert recommendation.actions == expected
    assert recommendation.mapping_status == "CANDIDATE_NOT_RUNTIME_APPROVED"
    assert recommendation.actuates is False
    assert IncidentAction.FORCE_OFF not in recommendation.actions


def test_unknown_keeps_local_threshold_only_with_usable_thermal_state():
    usable = recommend_incident_actions(
        CoolingHealthState.UNKNOWN, thermal_safety_usable=True
    )
    unusable = recommend_incident_actions(
        CoolingHealthState.UNKNOWN, thermal_safety_usable=False
    )
    assert IncidentAction.USE_LOCAL_THRESHOLD in usable.actions
    assert IncidentAction.USE_LOCAL_THRESHOLD not in unusable.actions


def test_healthy_state_cannot_contradict_unusable_thermal_state():
    with pytest.raises(ValueError, match="contradicts"):
        recommend_incident_actions(
            CoolingHealthState.HEALTHY_RESPONSE, thermal_safety_usable=False
        )
