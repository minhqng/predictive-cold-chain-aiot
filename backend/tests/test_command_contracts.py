"""Wire-contract unit tests for commands and ACKs (C-W06-01/03/06)."""

import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from coldguard_backend.contracts import Command, CommandAck
from coldguard_backend.validation import (
    ack_topic_device_id,
    validate_ack_topic_identity,
    validate_command_ack,
)
from tests.command_testkit import make_ack, make_command, utcnow


def test_command_canonical_valid():
    cmd = make_command("cmd-1")
    assert cmd.schema_version == 1
    assert cmd.action.cooling == "ON"
    assert cmd.expires_at > cmd.created_at


def test_command_rejects_expiry_not_after_creation():
    now = utcnow()
    with pytest.raises(ValidationError):
        make_command("cmd-1", created_at=now, ttl_s=0)


def test_command_rejects_out_of_range_duty():
    with pytest.raises(ValidationError):
        make_command("cmd-1", duty=1.5)
    with pytest.raises(ValidationError):
        make_command("cmd-1", duty=-0.1)


def test_command_rejects_unknown_action():
    with pytest.raises(ValidationError):
        make_command("cmd-1", cooling="MAYBE")


def test_command_rejects_empty_identity():
    with pytest.raises(ValidationError):
        make_command("cmd-1", device_id="  ")


def test_command_rejects_legacy_dual_branch_keys():
    with pytest.raises(ValidationError):
        make_command("cmd-1", action={"cooling": "ON", "duty": 0.5, "cmd_2": 1})


def test_ack_accepts_closed_verdict_set():
    for status in ("ACCEPTED", "REJECTED", "SAFETY_BLOCKED", "INVALID_STATE",
                   "OUT_OF_RANGE", "EXPIRED"):
        ack = make_ack("cmd-1", status=status, reason_code="X")
        assert ack.status == status


def test_ack_rejects_unknown_verdict():
    with pytest.raises(ValidationError):
        make_ack("cmd-1", status="COOLED")


def test_ack_duplicate_requires_canonical_status():
    with pytest.raises(ValidationError):
        CommandAck.model_validate(
            {
                "schema_version": 1, "command_id": "c", "device_id": "coldguard-001",
                "boot_id": "b", "status": "DUPLICATE_CANONICAL", "reason_code": "NONE",
                "uptime_ms": 1,
            }
        )
    ack = make_ack("cmd-1", status="DUPLICATE_CANONICAL", canonical_status="ACCEPTED")
    assert ack.canonical_status == "ACCEPTED"


def test_ack_rejects_negative_uptime():
    with pytest.raises(ValidationError):
        make_ack("cmd-1", uptime_ms=-1)


def test_ack_applied_duty_range():
    with pytest.raises(ValidationError):
        make_ack("cmd-1", applied={"cooling": "ON", "duty": 2.0})


def test_strict_ack_rejects_wrong_types():
    base = make_ack("cmd-1").model_dump(mode="json")
    bad = {**base, "uptime_ms": "123"}
    ack, errors = validate_command_ack(bad)
    assert ack is None
    assert any(e["code"] == "WRONG_TYPE" for e in errors)


def test_strict_ack_rejects_unsupported_schema():
    base = make_ack("cmd-1").model_dump(mode="json")
    ack, errors = validate_command_ack({**base, "schema_version": 2})
    assert ack is None
    assert errors[0]["code"] == "UNSUPPORTED_SCHEMA"


def test_strict_ack_rejects_bool_duty():
    base = make_ack("cmd-1").model_dump(mode="json")
    base["applied"] = {"cooling": "ON", "duty": True}
    ack, errors = validate_command_ack(base)
    assert ack is None


def test_ack_topic_device_segment():
    assert ack_topic_device_id("coldguard/coldguard-001/command_ack") == "coldguard-001"
    assert ack_topic_device_id("coldguard//command_ack") is None
    assert ack_topic_device_id("coldguard/coldguard-001/telemetry") is None


def test_ack_topic_identity_agreement():
    ack = make_ack("cmd-1")
    assert validate_ack_topic_identity("coldguard/coldguard-001/command_ack", ack) == []
    errors = validate_ack_topic_identity("coldguard/other-device/command_ack", ack)
    assert errors[0]["code"] == "TOPIC_MISMATCH"