"""Prove revision 0005 preserves W04 history and fences clockless provenance.

Runs only with ``COLDGUARD_TEST_DATABASE_URL`` against real PostgreSQL. These
tests rebuild the disposable test database, matching the other migration
tests; never point them at a database holding evidence you intend to keep.

Revision 0005 keeps schema-1 history exactly as it was (event time present,
no serial source) while allowing schema-2 clockless rows only with explicit
serial provenance. Its downgrade is deliberately fail-closed while clockless
observations exist, and the failed migration transaction must leave both the
schema and the observations untouched.
"""

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text

from coldguard_backend.ingest import ingest_message
from coldguard_backend.normalized_store import telemetry
from scripts.serial_gateway import translate

BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURE_V0 = BACKEND_DIR / "fixtures" / "telemetry_v0.json"
MEMBER_A_FIXTURE = BACKEND_DIR.parent / "evidence/A/W05/schema-fixture.json"

needs_real_db = pytest.mark.skipif(
    not os.environ.get("COLDGUARD_TEST_DATABASE_URL"),
    reason="requires COLDGUARD_TEST_DATABASE_URL pointing at a test database",
)


def _db_url() -> str:
    return os.environ["COLDGUARD_TEST_DATABASE_URL"]


def _config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option(
        "script_location", str(BACKEND_DIR / "src/coldguard_backend/migrations")
    )
    return config


@contextmanager
def _alembic_database():
    """Point the in-process alembic environment at the disposable test database."""
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _db_url()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _upgrade(revision: str) -> None:
    with _alembic_database():
        command.upgrade(_config(), revision)


def _downgrade(revision: str) -> None:
    with _alembic_database():
        command.downgrade(_config(), revision)


def _reset_to(revision: str) -> None:
    """Clear test data and rebuild the schema at ``revision``."""
    engine = create_engine(_db_url())
    try:
        tables = set(inspect(engine).get_table_names())
        with engine.begin() as connection:
            for table in (
                "device_twin_retired_boot", "device_twin", "telemetry", "telemetry_raw",
            ):
                if table in tables:
                    connection.execute(text(f"DELETE FROM {table}"))
    finally:
        engine.dispose()
    if "alembic_version" in tables:
        _downgrade("base")
    _upgrade(revision)


def _revision() -> str | None:
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
    finally:
        engine.dispose()


def _event_time(device_id: str, *, boot_id: str):
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            return connection.execute(
                select(telemetry).where(
                    telemetry.c.device_id == device_id,
                    telemetry.c.boot_id == boot_id,
                )
            ).mappings().one()
    finally:
        engine.dispose()


def _schema1_payload(device_id: str) -> dict:
    payload = json.loads(FIXTURE_V0.read_text(encoding="utf-8"))
    payload.update(device_id=device_id, boot_id=f"boot-w04-{uuid4().hex[:8]}", seq=1)
    return payload


def _clockless_wire(device_id: str) -> bytes:
    """Translate the committed Member A schema-3 frame through the gateway."""
    fields = json.loads(MEMBER_A_FIXTURE.read_text(encoding="utf-8"))["fields"]
    fields.update(device_id=device_id, boot_id=uuid4().hex, seq=1)
    frame = ("#CG TELEM " + " ".join(f"{k}={v}" for k, v in fields.items())).encode()
    return translate(
        frame,
        topic=f"coldguard/{device_id}/telemetry",
        gateway_received_at=datetime.now(timezone.utc),
        replay=False,
    )


def _ingest(device_id: str, payload: bytes) -> dict:
    engine = create_engine(_db_url())
    try:
        return ingest_message(
            engine, topic=f"coldguard/{device_id}/telemetry", payload=payload,
        )
    finally:
        engine.dispose()


@needs_real_db
def test_populated_w04_upgrade_preserves_history_and_fences_clockless_rows():
    _reset_to("0004")
    device = f"mig-w04-{uuid4().hex}"
    old_payload = _schema1_payload(device)
    old = _ingest(device, json.dumps(old_payload).encode())
    assert old["normalized"]["outcome"] == "inserted"

    _upgrade("head")
    assert _revision() == "0005"

    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            constraints = {
                row["name"]
                for row in inspect(connection).get_check_constraints("telemetry")
            }
    finally:
        engine.dispose()
    history = _event_time(device, boot_id=old_payload["boot_id"])
    # Pre-0005 rows are untouched: device event time stays present and
    # revision 0005 adds no invented serial provenance to them.
    assert history["time"] is not None
    assert history["serial_source"] is None
    assert history["schema_version"] == 1
    assert "ck_telemetry_event_time" in constraints

    clockless_device = f"mig-w04-clockless-{uuid4().hex}"
    clockless_wire = _clockless_wire(clockless_device)
    result = _ingest(clockless_device, clockless_wire)
    assert result["normalized"]["outcome"] == "inserted"
    clockless_boot = json.loads(clockless_wire)["boot_id"]
    clockless = _event_time(clockless_device, boot_id=clockless_boot)
    assert clockless["time"] is None
    assert clockless["serial_source"]["clock_quality"] == "UNAVAILABLE"

    engine = create_engine(_db_url())
    try:
        # The XOR constraint cannot be bypassed by direct SQL either.
        for statement in (
            "UPDATE telemetry SET time = NULL WHERE id = :id",
            "UPDATE telemetry SET serial_source = NULL WHERE id = :id",
        ):
            params = {"id": history["id"] if "time" in statement else clockless["id"]}
            with pytest.raises(Exception):
                with engine.begin() as connection:
                    connection.execute(text(statement), params)
    finally:
        engine.dispose()


@needs_real_db
def test_downgrade_refuses_while_clockless_observation_exists():
    _reset_to("head")
    device = f"mig-w04-down-{uuid4().hex}"
    wire = _clockless_wire(device)
    result = _ingest(device, wire)
    assert result["normalized"]["outcome"] == "inserted"
    boot = json.loads(wire)["boot_id"]

    with pytest.raises(Exception):
        _downgrade("0004")
    # The refused migration transaction preserved both schema and evidence.
    assert _revision() == "0005"
    assert _event_time(device, boot_id=boot)["time"] is None

    engine = create_engine(_db_url())
    try:
        with engine.begin() as connection:
            connection.execute(telemetry.delete().where(telemetry.c.device_id == device))
            connection.execute(
                text("DELETE FROM telemetry_raw WHERE device_id = :device"),
                {"device": device},
            )
    finally:
        engine.dispose()

    _downgrade("0004")
    assert _revision() == "0004"
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            constraints = {
                row["name"]
                for row in inspect(connection).get_check_constraints("telemetry")
            }
    finally:
        engine.dispose()
    assert "ck_telemetry_event_time" not in constraints

    _upgrade("head")
    assert _revision() == "0005"
