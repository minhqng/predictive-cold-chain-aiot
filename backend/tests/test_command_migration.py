"""Revision 0008 command-storage migration proofs (C-W06-01).

Runs against an isolated disposable database
(COLDGUARD_TEST_COMMAND_MIGRATION_DB_URL) so destructive downgrade cycles never
touch the shared suite database or any evidence worth keeping. Proves upgrade,
populated upgrade (existing telemetry preserved), downgrade and re-upgrade, and
the presence of the command integrity constraints.
"""

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select, text

from coldguard_backend import command_store as cs
from coldguard_backend.normalized_store import insert_normalized, map_to_row, telemetry
from coldguard_backend.raw_store import store_raw, telemetry_raw
from coldguard_backend.validation import validate_telemetry_payload
from tests.command_testkit import make_command

BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURE_V0 = BACKEND_DIR / "fixtures" / "telemetry_v0.json"
ENV = "COLDGUARD_TEST_COMMAND_MIGRATION_DB_URL"

needs_migration_db = pytest.mark.skipif(
    not os.environ.get(ENV),
    reason=f"requires {ENV} pointing at an isolated disposable migration database",
)

COMMAND_TABLES = {"commands", "command_attempts", "command_acks", "command_transitions"}


def _url() -> str:
    return os.environ[ENV]


def _config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(BACKEND_DIR / "src/coldguard_backend/migrations")
    )
    return cfg


@contextmanager
def _alembic_db():
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _url()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _upgrade(revision: str) -> None:
    with _alembic_db():
        command.upgrade(_config(), revision)


def _downgrade(revision: str) -> None:
    with _alembic_db():
        command.downgrade(_config(), revision)


def _revision(engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def _ensure(revision: str, engine) -> None:
    current = _revision(engine)
    if current is None or current < revision:
        _upgrade(revision)
    elif current > revision:
        _downgrade(revision)


def _tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _seed_telemetry(engine, device: str) -> dict:
    payload = json.loads(FIXTURE_V0.read_text(encoding="utf-8"))
    payload.update(device_id=device, boot_id=f"boot-{device}", seq=1,
                   captured_at=datetime.now(timezone.utc).isoformat())
    wire = json.dumps(payload).encode()
    received = datetime.now(timezone.utc)
    stored = store_raw(engine, topic=f"coldguard/{device}/telemetry", payload=wire, received_at=received)
    validated, errors = validate_telemetry_payload(json.loads(wire))
    assert validated is not None, errors
    row = map_to_row(validated, raw_id=stored["id"], received_at=received)
    row["twin_eligible"] = False
    insert_normalized(engine, row)
    return {"raw_id": stored["id"], "sha": stored["payload_sha256"]}


def _telemetry_snapshot(engine, device: str) -> dict:
    with engine.connect() as conn:
        rows = conn.execute(select(telemetry).where(telemetry.c.device_id == device)).mappings().all()
        raw = conn.execute(
            select(telemetry_raw).where(telemetry_raw.c.device_id == device)
        ).mappings().all()
    digest = hashlib.sha256()
    for r in rows:
        digest.update(repr((r["id"], r["device_id"], r["boot_id"], r["seq"], r["raw_id"], r["time"])).encode())
    return {"normalized": len(rows), "raw": len(raw), "sha": digest.hexdigest()}


@needs_migration_db
def test_0008_upgrade_downgrade_reupgrade_creates_command_tables():
    engine = create_engine(_url())
    try:
        _ensure("0007", engine)
        assert not (COMMAND_TABLES & _tables(engine))
        _upgrade("0008")
        assert COMMAND_TABLES <= _tables(engine)
        assert _revision(engine) == "0008"
        _downgrade("0007")
        assert not (COMMAND_TABLES & _tables(engine))
        _upgrade("0008")
        assert COMMAND_TABLES <= _tables(engine)
    finally:
        engine.dispose()


@needs_migration_db
def test_0008_populated_upgrade_preserves_existing_telemetry():
    engine = create_engine(_url())
    device = f"w08-mig-{os.urandom(4).hex()}"
    try:
        _ensure("0007", engine)
        _seed_telemetry(engine, device)
        before = _telemetry_snapshot(engine, device)
        assert before["normalized"] == 1 and before["raw"] == 1

        _upgrade("0008")
        assert COMMAND_TABLES <= _tables(engine)
        assert _telemetry_snapshot(engine, device) == before

        # Command data lives only in 0008; a downgrade drops it (by design) but
        # must never disturb the pre-existing telemetry evidence.
        with engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-mig", device_id=device))
        _downgrade("0007")
        assert not (COMMAND_TABLES & _tables(engine))
        assert _telemetry_snapshot(engine, device) == before

        _upgrade("0008")
        assert COMMAND_TABLES <= _tables(engine)
        assert _telemetry_snapshot(engine, device) == before
    finally:
        with engine.begin() as conn:
            conn.execute(telemetry.delete().where(telemetry.c.device_id == device))
            conn.execute(telemetry_raw.delete().where(telemetry_raw.c.device_id == device))
        engine.dispose()


@needs_migration_db
def test_0008_command_integrity_constraints_present():
    engine = create_engine(_url())
    try:
        _ensure("0008", engine)
        insp = inspect(engine)
        checks = {c["name"] for c in insp.get_check_constraints("commands")}
        assert "ck_commands_expiry_after_created" in checks
        assert "ck_commands_action_duty" in checks
        assert "ck_commands_status" in checks
        assert "ck_commands_action_cooling" in checks
        pk = insp.get_pk_constraint("commands")
        assert pk["constrained_columns"] == ["command_id"]
        attempt_uniques = {u["name"] for u in insp.get_unique_constraints("command_attempts")}
        assert "uq_command_attempts_command_no" in attempt_uniques
        ack_checks = {c["name"] for c in insp.get_check_constraints("command_acks")}
        assert "ck_command_acks_validity" in ack_checks
    finally:
        engine.dispose()