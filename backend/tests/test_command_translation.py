"""Command JSON -> device serial translation (W06 handoff section 6.2 item 2).

Producer is the real Member C ``Command`` envelope (Doc 02 section 28.1);
consumer contract is the Member A device record encoding read from
firmware/main/cg_command.c:559-561 and the HANDOFF command_surface: exactly ten
space-separated key=value names, all mandatory except controller_id, record
<= 512 bytes, unknown key refused, duty in permille, times in epoch ms.

These tests prove the bounded prerequisite produces a record the device parser
accepts at the encoding boundary, and that it fails closed (never invents a
timezone or an over-long record). Device-side admission/safety (expiry, clock
sync, action range) remains the device's own fail-closed authority.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from coldguard_backend.contracts import Command
from coldguard_backend.command_translation import (
    CG_COMMAND_RECORD_MAX,
    DEVICE_COMMAND_FIELDS,
    CommandTranslationError,
    command_to_device_fields,
    translate_command_to_device_serial,
)

# Member A device field contract: firmware/main/cg_command.c:559-561.
A_DEVICE_FIELDS = {
    "schema_version", "command_id", "device_id", "created_at_ms", "expires_at_ms",
    "controller_id", "policy_version", "reason_code", "action_cooling",
    "action_duty_permille",
}
A_MANDATORY = A_DEVICE_FIELDS - {"controller_id"}  # controller_id optional per §28.3

NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


def _command(**overrides) -> Command:
    base = dict(
        schema_version=1,
        command_id="cmd-0001",
        device_id="coldguard-001",
        created_at=NOW,
        expires_at=NOW + timedelta(seconds=120),
        controller_id="PREDICTIVE",
        policy_version="policy-v1",
        reason_code="PREDICTED_CRITICAL",
        action={"cooling": "ON", "duty": 1.0},
    )
    base.update(overrides)
    return Command(**base)


def _parse_device_record(record: str) -> dict[str, str]:
    # Same key=value convention the device uses (cg_command.c cursor walk;
    # firmware/tools/cg_command_trace.py _fields splits on the first '=').
    fields = {}
    for token in record.split(" "):
        key, value = token.split("=", 1)
        assert key not in fields, f"DUPLICATE_FIELD {key}"
        fields[key] = value
    return fields


def test_field_set_is_one_to_one_with_device_contract():
    assert set(DEVICE_COMMAND_FIELDS) == A_DEVICE_FIELDS


def test_translated_record_satisfies_device_encoding_contract():
    record = translate_command_to_device_serial(_command())
    fields = _parse_device_record(record)
    assert set(fields) == A_DEVICE_FIELDS  # no unknown keys (device refuses unknown)
    assert A_MANDATORY <= set(fields)
    assert len(record.encode("ascii")) <= CG_COMMAND_RECORD_MAX
    assert fields["schema_version"] == "1"
    assert fields["device_id"] == "coldguard-001"
    assert fields["action_cooling"] == "ON"


def test_timestamps_convert_to_epoch_ms():
    fields = command_to_device_fields(_command())
    assert fields["created_at_ms"] == int(NOW.timestamp() * 1000)
    assert fields["expires_at_ms"] == int((NOW + timedelta(seconds=120)).timestamp() * 1000)
    assert fields["expires_at_ms"] > fields["created_at_ms"]


@pytest.mark.parametrize("duty,permille", [(1.0, 1000), (0.5, 500), (0.25, 250), (0.0, 0)])
def test_duty_converts_to_permille(duty, permille):
    fields = command_to_device_fields(_command(action={"cooling": "ON", "duty": duty}))
    assert fields["action_duty_permille"] == permille
    assert 0 <= fields["action_duty_permille"] <= 1000


def test_null_duty_maps_to_zero_permille():
    fields = command_to_device_fields(_command(action={"cooling": "OFF", "duty": None}))
    assert fields["action_duty_permille"] == 0
    assert fields["action_cooling"] == "OFF"


def test_optional_envelope_fields_are_stripped_not_renamed():
    command = _command(prediction_id="pred-1", run_id="CG-S1-A-001", expected_twin_version=3)
    record = translate_command_to_device_serial(command)
    fields = _parse_device_record(record)
    # Device refuses unknown keys; optional §28.3 fields have no device name.
    assert "prediction_id" not in fields
    assert "run_id" not in fields
    assert "expected_twin_version" not in fields
    assert set(fields) == A_DEVICE_FIELDS


def test_naive_timestamp_fails_closed():
    naive = datetime(2026, 11, 10, 12, 0, 0)
    # Member C#69 rejects naive timestamps at the envelope (AwareDatetime);
    # fail-closed now lives in BOTH layers: rejection upstream of the
    # translation guard is equivalent for this invariant.
    with pytest.raises((CommandTranslationError, ValidationError)):
        translate_command_to_device_serial(
            _command(created_at=naive, expires_at=naive + timedelta(seconds=120))
        )


def test_oversize_record_fails_closed():
    with pytest.raises(CommandTranslationError, match="RECORD_TOO_LONG"):
        translate_command_to_device_serial(_command(command_id="x" * 600))


def test_record_round_trips_through_device_key_value_parsing():
    record = translate_command_to_device_serial(_command(action={"cooling": "OFF", "duty": 0.0}))
    fields = _parse_device_record(record)
    assert fields["action_cooling"] == "OFF"
    assert fields["action_duty_permille"] == "0"
    assert fields["reason_code"] == "PREDICTED_CRITICAL"