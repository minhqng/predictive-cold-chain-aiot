"""Device #CG CMDACK -> backend CommandAck envelope translation.

Input fixtures are Member A's committed evidence/A/W06/ack-fixture.json (real
device ACK records). The output is the Doc 02 section 32.3 CommandAck JSON
shape; Member C's CommandAck model (unmerged C#69) is the validation authority
and is exercised separately against real PR source, not duplicated here.

Proves the bounded uplink prerequisite renders well-formed envelopes and fails
closed on unknown verdicts, missing canonical verdict for a duplicate, missing
identity, invalid booleans and out-of-range duty. No ack_time is invented.
"""

import json
import pathlib

import pytest

from coldguard_backend.ack_translation import (
    ACK_STATUS_VOCABULARY,
    AckTranslationError,
    device_ack_to_backend,
    parse_device_ack_fields,
)

FIXTURES = json.loads(
    (pathlib.Path(__file__).resolve().parents[2]
     / "evidence" / "A" / "W06" / "ack-fixture.json").read_text(encoding="utf-8")
)["fixtures"]


def _line(fields: dict) -> str:
    return "#CG CMDACK " + " ".join(f"{key}={value}" for key, value in fields.items())


def _fixture_line(name: str) -> str:
    return _line(FIXTURES[name]["fields"])


def test_ack_vocabulary_matches_doc02_closed_set():
    assert set(ACK_STATUS_VOCABULARY) == {
        "ACCEPTED", "REJECTED", "DUPLICATE_CANONICAL", "EXPIRED",
        "SAFETY_BLOCKED", "INVALID_STATE", "OUT_OF_RANGE",
    }


@pytest.mark.parametrize("name", list(FIXTURES))
def test_real_device_fixtures_translate_to_well_formed_envelope(name):
    fields = FIXTURES[name]["fields"]
    envelope = device_ack_to_backend(_line(fields))
    assert envelope["schema_version"] == 1
    assert envelope["command_id"] == fields["command_id"]
    assert envelope["device_id"] == fields["device_id"]
    assert envelope["boot_id"] == fields["boot_id"]
    assert envelope["status"] == fields["status"]
    assert envelope["reason_code"] == fields["reason"]
    assert envelope["uptime_ms"] == int(fields["uptime_ms"])
    assert "ack_time" not in envelope  # never fabricate a device wall-clock time


def test_duplicate_carries_original_canonical_verdict():
    envelope = device_ack_to_backend(_fixture_line("duplicate-replay"))
    assert envelope["status"] == "DUPLICATE_CANONICAL"
    assert envelope["canonical_status"] == "ACCEPTED"
    assert envelope["reapplied"] is False


def test_duty_permille_converts_to_unit_float():
    envelope = device_ack_to_backend(_fixture_line("synchronized-accepted"))
    fields = FIXTURES["synchronized-accepted"]["fields"]
    assert envelope["desired"]["cooling"] == fields["desired_cooling"]
    assert envelope["desired"]["duty"] == int(fields["desired_duty_permille"]) / 1000.0
    assert envelope["applied"]["cooling"] == fields["applied_cooling"]
    assert envelope["applied"]["duty"] == int(fields["applied_duty_permille"]) / 1000.0


def test_device_mode_passes_through_without_policy_mapping():
    envelope = device_ack_to_backend(_fixture_line("synchronized-accepted"))
    # device_mode is the device's free-string actuator mode; mapping it to a
    # policy state is Member D's decision and must not be invented here.
    assert envelope["device_mode"] == "OFF"


def test_unsynchronized_clock_is_preserved_not_fabricated():
    envelope = device_ack_to_backend(_fixture_line("shipped-unsynchronized"))
    assert envelope["time_sync_state"] == "UNSYNCHRONIZED"
    assert envelope["expiry_evaluable"] is False


def test_unknown_status_fails_closed():
    fields = dict(FIXTURES["synchronized-accepted"]["fields"], status="BOGUS")
    with pytest.raises(AckTranslationError, match="UNKNOWN_STATUS"):
        device_ack_to_backend(_line(fields))


def test_duplicate_without_canonical_fails_closed():
    fields = dict(FIXTURES["duplicate-replay"]["fields"])
    del fields["canonical_status"]
    with pytest.raises(AckTranslationError, match="DUPLICATE_MISSING_CANONICAL"):
        device_ack_to_backend(_line(fields))


def test_missing_identity_fails_closed():
    fields = dict(FIXTURES["synchronized-accepted"]["fields"])
    del fields["boot_id"]
    with pytest.raises(AckTranslationError, match="MISSING_FIELDS"):
        device_ack_to_backend(_line(fields))


def test_non_cmdack_line_fails_closed():
    with pytest.raises(AckTranslationError, match="NOT_CMDACK"):
        device_ack_to_backend("#CG TELEM schema=3 seq=1")


def test_invalid_boolean_fails_closed():
    fields = dict(FIXTURES["synchronized-accepted"]["fields"], reapplied="2")
    with pytest.raises(AckTranslationError, match="INVALID_BOOL"):
        device_ack_to_backend(_line(fields))


def test_duty_out_of_range_fails_closed():
    fields = dict(FIXTURES["synchronized-accepted"]["fields"], desired_duty_permille="1500")
    with pytest.raises(AckTranslationError, match="DUTY_OUT_OF_RANGE"):
        device_ack_to_backend(_line(fields))


def test_duplicate_field_fails_closed():
    line = _fixture_line("synchronized-accepted") + " uptime_ms=9999"
    with pytest.raises(AckTranslationError, match="DUPLICATE_FIELD"):
        parse_device_ack_fields(line)


def test_non_numeric_integer_field_fails_closed():
    fields = dict(FIXTURES["synchronized-accepted"]["fields"], uptime_ms="not-a-number")
    with pytest.raises(AckTranslationError, match="INVALID_INT"):
        device_ack_to_backend(_line(fields))