"""Tests for the W10 fault‑injection protocol module (pure, no hardware)."""

import pytest

from coldguard_control import (
    FaultProtocol,
    FaultProtocolStatus,
    InjectionCheckResult,
    InjectionVerdict,
    check_injection,
    audit_protocols,
    get_protocol,
    FORBIDDEN_TECHNIQUE_IDS,
)


def test_audit_protocols_no_violations():
    violations = audit_protocols()
    # All defined protocols should have empty violation tuples
    for v in violations.values():
        assert v == (), f"Unexpected audit violations: {v}"


def test_check_injection_forbidden():
    # Use a known forbidden technique ID
    technique_id = next(iter(FORBIDDEN_TECHNIQUE_IDS))
    result = check_injection("S4-ELECTRICAL-RESPONSE-MISSING", technique_id)
    assert result.verdict == InjectionVerdict.FORBIDDEN
    assert "blacklist" in result.detail.lower()


def test_check_injection_not_in_protocol():
    result = check_injection("S4-ELECTRICAL-RESPONSE-MISSING", "UNKNOWN-TECH")
    assert result.verdict == InjectionVerdict.NOT_IN_PROTOCOL
    assert "no such protocol" not in result.detail.lower()


def test_check_injection_protocol_not_approved():
    # The S4‑ELECTRICAL‑RESPONSE‑MISSING protocol is marked OPEN
    # Attempt with an allowed technique
    result = check_injection("S4-ELECTRICAL-RESPONSE-MISSING", "SW-NO-ACTUATION-MODE")
    assert result.verdict == InjectionVerdict.PROTOCOL_NOT_APPROVED
    assert "status is open" in result.detail.lower()


def test_check_injection_safe():
    # SENSOR-DEGRADED is DEFINED and allows SENSOR-SAFE-DISCONNECT
    result = check_injection("SENSOR-DEGRADED", "SENSOR-SAFE-DISCONNECT")
    assert result.verdict == InjectionVerdict.SAFE
    assert result.detail.startswith("technique allowed")


def test_get_protocol_unknown_raises():
    with pytest.raises(KeyError):
        get_protocol("NON-EXISTENT")
