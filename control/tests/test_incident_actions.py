"""Tests for incident action enums (W11)."""

from coldguard_control import IncidentAction


def test_incident_action_values():
    expected = [
        "WARN",
        "BLOCK_PREDICTIVE",
        "FORCE_OFF",
        "USE_LOCAL_THRESHOLD",
        "ENTER_LOCKOUT",
    ]
    assert [a.value for a in IncidentAction] == expected
