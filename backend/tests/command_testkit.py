"""Shared helpers for Member C W06 command-path tests (C-W06-06).

Provider tests use a disposable PostgreSQL database (COLDGUARD_TEST_DATABASE_URL)
and, where marked, a disposable Mosquitto broker (COLDGUARD_TEST_MQTT_HOST).
They skip honestly when a prerequisite is unset. No physical hardware is used;
the device side is a contract-compatible mock publisher of synthetic ACKs.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, text

from coldguard_backend.contracts import Command, CommandAck

BACKEND_DIR = Path(__file__).resolve().parent.parent


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_command(
    command_id: str,
    device_id: str = "coldguard-001",
    *,
    ttl_s: int = 300,
    created_at: datetime | None = None,
    cooling: str = "ON",
    duty: float | None = 0.5,
    **overrides,
) -> Command:
    created = created_at or utcnow()
    payload = {
        "schema_version": 1,
        "command_id": command_id,
        "device_id": device_id,
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(seconds=ttl_s)).isoformat(),
        "controller_id": "PREDICTIVE",
        "policy_version": "policy-test-1",
        "reason_code": "PREDICTED_CRITICAL",
        "action": {"cooling": cooling, "duty": duty},
    }
    payload.update(overrides)
    return Command.model_validate(payload)


def make_ack(
    command_id: str,
    status: str = "ACCEPTED",
    device_id: str = "coldguard-001",
    *,
    boot_id: str = "boot-test",
    reason_code: str = "NONE",
    **overrides,
) -> CommandAck:
    payload = {
        "schema_version": 1,
        "command_id": command_id,
        "device_id": device_id,
        "boot_id": boot_id,
        "status": status,
        "reason_code": reason_code,
        "uptime_ms": 123456,
        "applied": {"cooling": "ON", "duty": 0.5},
    }
    if status == "DUPLICATE_CANONICAL":
        payload["canonical_status"] = overrides.pop("canonical_status", "ACCEPTED")
    payload.update(overrides)
    return CommandAck.model_validate(payload)


def ack_bytes(ack: CommandAck) -> bytes:
    return json.dumps(ack.model_dump(mode="json")).encode("utf-8")


def ack_topic(device_id: str = "coldguard-001") -> str:
    return f"coldguard/{device_id}/command_ack"


def upgrade_head() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(BACKEND_DIR / "src/coldguard_backend/migrations")
    )
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = os.environ["COLDGUARD_TEST_DATABASE_URL"]
    try:
        alembic_command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture
def db_engine():
    if not os.environ.get("COLDGUARD_TEST_DATABASE_URL"):
        pytest.skip("requires COLDGUARD_TEST_DATABASE_URL pointing at a disposable test database")
    upgrade_head()
    engine = create_engine(os.environ["COLDGUARD_TEST_DATABASE_URL"])
    try:
        yield engine
    finally:
        engine.dispose()


def cleanup_commands(engine, device_id: str = "coldguard-001") -> None:
    from coldguard_backend import command_store as cs
    from coldguard_backend.twin_store import device_twin

    with engine.begin() as conn:
        ids = conn.execute(
            cs.commands.select().with_only_columns(cs.commands.c.command_id).where(
                cs.commands.c.device_id == device_id
            )
        ).scalars().all()
        if ids:
            conn.execute(
                cs.command_transitions.delete().where(cs.command_transitions.c.command_id.in_(ids))
            )
            conn.execute(
                cs.command_attempts.delete().where(cs.command_attempts.c.command_id.in_(ids))
            )
            conn.execute(cs.commands.delete().where(cs.commands.c.command_id.in_(ids)))
        conn.execute(
            cs.command_acks.delete().where(cs.command_acks.c.topic_device_id == device_id)
        )
        conn.execute(device_twin.delete().where(device_twin.c.device_id == device_id))