"""Wire-contract validation for telemetry and command fixtures (C-W01-03).

Defects detected: a fixture that no longer parses, required
device/message identity dropped, legacy dual-channel fields silently
re-entering the single-branch contract, inverted command expiry, a
missing measurement marked VALID, or a wire schema version other than
the canonical v1.
"""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from coldguard_backend.contracts import (
    WIRE_SCHEMA_VERSION,
    Command,
    Telemetry,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_wire_schema_version_is_one_not_fixture_maturity():
    assert WIRE_SCHEMA_VERSION == 1


def test_valid_telemetry_fixture_parses():
    telemetry = Telemetry.model_validate(_load("telemetry_v0.json"))
    assert telemetry.schema_version == 1
    assert telemetry.message_identity == ("coldguard-001", "boot-w01-fixture-001", 12345)
    assert telemetry.actuation.cooling == "ON"
    assert telemetry.door.state == "CLOSED"


def test_valid_command_fixture_parses():
    command = Command.model_validate(_load("command_v0.json"))
    assert command.schema_version == 1
    assert command.action.cooling == "ON"
    assert command.expires_at > command.created_at


def test_telemetry_requires_device_message_identity():
    payload = _load("telemetry_v0.json")
    del payload["boot_id"]
    with pytest.raises(ValidationError):
        Telemetry.model_validate(payload)


def test_telemetry_rejects_legacy_dual_channel_fields():
    payload = _load("telemetry_v0.json")
    payload["electrical"]["power_1"] = 10.0
    with pytest.raises(ValidationError, match="legacy dual-channel"):
        Telemetry.model_validate(payload)


def test_command_rejects_legacy_dual_channel_action():
    payload = _load("command_v0.json")
    payload["action"]["cmd_1"] = "ON"
    with pytest.raises(ValidationError, match="legacy dual-channel"):
        Command.model_validate(payload)


def test_command_rejects_non_positive_ttl():
    payload = _load("command_v0.json")
    payload["expires_at"] = payload["created_at"]
    with pytest.raises(ValidationError, match="expires_at"):
        Command.model_validate(payload)


def test_telemetry_rejects_missing_value_marked_valid():
    payload = _load("telemetry_v0.json")
    payload["thermal"]["t3"] = None
    with pytest.raises(ValidationError, match="VALID section quality"):
        Telemetry.model_validate(payload)


def test_telemetry_accepts_missing_value_with_degraded_quality():
    payload = _load("telemetry_v0.json")
    payload["thermal"]["t3"] = None
    payload["quality"]["thermal"] = "DEGRADED"
    payload["quality"]["overall"] = "DEGRADED"
    telemetry = Telemetry.model_validate(payload)
    assert telemetry.thermal.t3 is None


def test_telemetry_rejects_zero_wire_schema_version():
    payload = _load("telemetry_v0.json")
    payload["schema_version"] = 0
    with pytest.raises(ValidationError):
        Telemetry.model_validate(payload)


def test_telemetry_allows_compatible_future_optional_fields():
    payload = _load("telemetry_v0.json")
    payload["future_optional_field"] = "reserved-for-later"
    assert Telemetry.model_validate(payload).schema_version == 1


def test_wire_names_are_not_normalized_db_names():
    """Wire names must not borrow future normalized storage names."""
    raw = (FIXTURES / "telemetry_v0.json").read_text()
    for normalized_name in ("t1_c", "t2_c", "t3_c", "cooling_current_a", "cooling_power_w"):
        assert normalized_name not in raw


def test_timestamp_alone_is_not_message_identity():
    first = _load("telemetry_v0.json")
    second = copy.deepcopy(first)
    second["seq"] = first["seq"] + 1
    assert Telemetry.model_validate(first).message_identity != Telemetry.model_validate(
        second
    ).message_identity
