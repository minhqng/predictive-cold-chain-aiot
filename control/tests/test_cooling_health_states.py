"""Tests for cooling‑health diagnosis enums (W11)."""

from coldguard_control import CoolingHealthState


def test_cooling_health_state_values():
    expected = [
        "HEALTHY_RESPONSE",
        "ELECTRICAL_RESPONSE_MISSING",
        "THERMAL_EFFECTIVENESS_DEGRADED",
        "CONTROL_ELECTRICAL_ANOMALY",
        "UNKNOWN",
    ]
    assert [s.value for s in CoolingHealthState] == expected
