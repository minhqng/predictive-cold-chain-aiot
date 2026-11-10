"""End-to-end command/ACK integration through the owner-owned bridge.

Producer is the real Member C ``Command`` (Doc 02 section 28.1, on main); the
device ACK input is Member A's committed evidence/A/W06/ack-fixture.json record
format. The bridge connects the two immutable implementations via the owner
adapters. These tests prove the full software loop executes and correlates, and
fails closed on mismatch/unknown verdict/naive time. The backend CommandAck
model itself is unmerged (C#69) and is validated against real PR source
separately, not duplicated here.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from coldguard_backend.ack_translation import AckTranslationError
from coldguard_backend.command_ack_bridge import (
    CommandAckCorrelationError,
    dispatch_command,
    ingest_ack,
    round_trip,
)
from coldguard_backend.command_translation import CommandTranslationError
from coldguard_backend.contracts import Command

# Member A device field contract: firmware/main/cg_command.c:559-561.
A_DEVICE_FIELDS = {
    "schema_version", "command_id", "device_id", "created_at_ms", "expires_at_ms",
    "controller_id", "policy_version", "reason_code", "action_cooling",
    "action_duty_permille",
}

FIXTURES = json.loads(
    (pathlib.Path(__file__).resolve().parents[2]
     / "evidence" / "A" / "W06" / "ack-fixture.json").read_text(encoding="utf-8")
)["fixtures"]

NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
COMMAND_ID = "00000000-0000-4000-8000-00000000000b"


def _command(**overrides) -> Command:
    base = dict(
        schema_version=1, command_id=COMMAND_ID, device_id="coldguard-001",
        created_at=NOW, expires_at=NOW + timedelta(seconds=120),
        controller_id="PREDICTIVE", policy_version="policy-v1",
        reason_code="PREDICTED_CRITICAL", action={"cooling": "ON", "duty": 0.25},
    )
    base.update(overrides)
    return Command(**base)


def _ack_line(fixture_name: str, command_id: str = COMMAND_ID) -> str:
    fields = dict(FIXTURES[fixture_name]["fields"], command_id=command_id)
    return "#CG CMDACK " + " ".join(f"{k}={v}" for k, v in fields.items())


def test_dispatch_produces_device_record_with_exact_field_set():
    record = dispatch_command(_command())
    keys = {token.split("=", 1)[0] for token in record.split(" ")}
    assert keys == A_DEVICE_FIELDS  # no unknown keys; device refuses unknown
    assert "action_duty_permille=250" in record  # 0.25 -> 250 permille
    assert "action_cooling=ON" in record


def test_full_round_trip_dispatches_and_correlates_ack():
    result = round_trip(_command(), _ack_line("synchronized-accepted"))
    record_keys = {t.split("=", 1)[0] for t in result["device_record"].split(" ")}
    assert record_keys == A_DEVICE_FIELDS
    envelope = result["ack_envelope"]
    assert envelope["command_id"] == COMMAND_ID
    assert envelope["status"] == "ACCEPTED"
    assert envelope["device_id"] == "coldguard-001"
    assert "ack_time" not in envelope  # no fabricated device wall-clock time


def test_duplicate_ack_round_trip_carries_canonical_verdict():
    result = round_trip(_command(), _ack_line("duplicate-replay"))
    envelope = result["ack_envelope"]
    assert envelope["status"] == "DUPLICATE_CANONICAL"
    assert envelope["canonical_status"] == "ACCEPTED"
    assert envelope["reapplied"] is False


def test_ack_with_mismatched_command_id_is_refused():
    with pytest.raises(CommandAckCorrelationError, match="ACK_COMMAND_MISMATCH"):
        round_trip(_command(), _ack_line("synchronized-accepted", command_id="other-command"))


def test_ingest_without_expectation_does_not_correlate():
    envelope = ingest_ack(_ack_line("synchronized-accepted", command_id="any-id"))
    assert envelope["command_id"] == "any-id"


def test_unsynchronized_clock_ack_preserved_not_fabricated():
    result = round_trip(_command(), _ack_line("shipped-unsynchronized"))
    envelope = result["ack_envelope"]
    assert envelope["time_sync_state"] == "UNSYNCHRONIZED"
    assert envelope["expiry_evaluable"] is False
    # The bridge does not turn an unsynchronized ACK into an accepted actuation.
    assert envelope["status"] == FIXTURES["shipped-unsynchronized"]["fields"]["status"]


def test_unknown_device_verdict_fails_closed():
    with pytest.raises(AckTranslationError, match="UNKNOWN_STATUS"):
        round_trip(_command(), _ack_line("synchronized-accepted").replace(
            "status=ACCEPTED", "status=BOGUS"))


def test_naive_command_time_fails_closed():
    naive = datetime(2026, 11, 10, 12, 0, 0)
    # Member C#69 rejects naive timestamps at the envelope (AwareDatetime);
    # fail-closed now lives in BOTH layers: rejection upstream of the
    # translation guard is equivalent for this invariant.
    with pytest.raises((CommandTranslationError, ValidationError)):
        dispatch_command(_command(created_at=naive, expires_at=naive + timedelta(seconds=120)))