"""Tests for verification state enums (W11)."""

from coldguard_control import VerificationStatus


def test_verification_states_values():
    expected = [
        "NOT_REQUIRED",
        "PENDING",
        "ELECTRICAL_VERIFIED",
        "THERMAL_VERIFIED",
        "VERIFIED",
        "FAILED_ELECTRICAL",
        "FAILED_THERMAL",
        "UNKNOWN",
    ]
    assert [s.value for s in VerificationStatus] == expected
