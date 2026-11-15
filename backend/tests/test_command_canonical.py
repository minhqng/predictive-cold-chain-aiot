"""Canonical command bytes are stable across PostgreSQL session time zones."""

import json
from datetime import datetime, timedelta, timezone

from coldguard_backend.command_publisher import command_from_row
from coldguard_backend.command_store import canonical_command_bytes
from tests.command_testkit import make_command


def test_canonical_envelope_uses_utc_independent_of_database_session_timezone():
    stamp = datetime(2026, 11, 8, 0, 0, 0, 123456, tzinfo=timezone.utc)
    command = make_command("software-canonical", created_at=stamp, ttl_s=60)
    row = command.model_dump()
    row.update(
        created_at=command.created_at.astimezone(timezone(timedelta(hours=7))),
        expires_at=command.expires_at.astimezone(timezone(timedelta(hours=7))),
        action_cooling=command.action.cooling, action_duty=command.action.duty,
    )
    encoded = canonical_command_bytes(command)
    assert canonical_command_bytes(command_from_row(row)) == encoded
    assert json.loads(encoded)["created_at"] == "2026-11-08T00:00:00.123456Z"
    assert json.loads(encoded)["expires_at"] == "2026-11-08T00:01:00.123456Z"


def test_non_utc_caller_is_canonicalized_without_mutating_the_input():
    stamp = datetime(2026, 11, 8, 7, tzinfo=timezone(timedelta(hours=7)))
    command = make_command("software-offset", created_at=stamp, ttl_s=60)
    encoded = json.loads(canonical_command_bytes(command))
    assert encoded["created_at"] == "2026-11-08T00:00:00Z"
    assert encoded["expires_at"] == "2026-11-08T00:01:00Z"
    assert command.created_at.isoformat() == "2026-11-08T07:00:00+07:00"
