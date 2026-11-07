"""Revision 0006 storage baseline, query helpers, and migration preservation (C-W05-02).

Proves:
- Migration 0005 -> 0006 upgrade creates required indexes; downgrade drops them.
- Query helpers handle time-range, run-ID, device, and clockless queries.
- Bounded pagination and input validation rules.
- W05-FIX-01: reconciliation seeded through the REAL validation/mapping pipeline
  passes; the old ``{"calibration_id": "CAL-01"}`` false-positive seed is covered
  by test_reconciliation.py and must fail.
- W05-FIX-06: a populated 0005 -> 0006 -> 0005 -> 0006 cycle preserves every row,
  identity, raw link and key-field hash, proven on an isolated disposable
  database (COLDGUARD_TEST_MIGRATION_DB_URL) that is never wiped.
"""

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, func, inspect, select, text

from coldguard_backend.ingest import ingest_message
from coldguard_backend.normalized_store import (
    count_telemetry,
    insert_normalized,
    map_to_row,
    query_telemetry,
    telemetry,
)
from coldguard_backend.raw_store import store_raw, telemetry_raw
from coldguard_backend.reconciliation import reconcile_telemetry
from coldguard_backend.validation import validate_telemetry_payload
from scripts.serial_gateway import translate

BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURE_V0 = BACKEND_DIR / "fixtures" / "telemetry_v0.json"
MEMBER_A_FIXTURE = BACKEND_DIR.parent / "evidence" / "A" / "W05" / "schema-fixture.json"

needs_real_db = pytest.mark.skipif(
    not os.environ.get("COLDGUARD_TEST_DATABASE_URL"),
    reason="requires COLDGUARD_TEST_DATABASE_URL pointing at a test database",
)
needs_migration_db = pytest.mark.skipif(
    not os.environ.get("COLDGUARD_TEST_MIGRATION_DB_URL"),
    reason="requires COLDGUARD_TEST_MIGRATION_DB_URL pointing at an isolated "
    "disposable migration-proof database",
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
def _alembic_database(url: str):
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _upgrade(revision: str, url: str | None = None) -> None:
    with _alembic_database(url or _db_url()):
        command.upgrade(_config(), revision)


def _downgrade(revision: str, url: str | None = None) -> None:
    with _alembic_database(url or _db_url()):
        command.downgrade(_config(), revision)


# --- Unit tests (no database required) ---


def test_query_telemetry_validates_pagination_bounds():
    dummy_engine = None
    with pytest.raises(ValueError, match="limit must be between"):
        query_telemetry(dummy_engine, limit=0)
    with pytest.raises(ValueError, match="limit must be between"):
        query_telemetry(dummy_engine, limit=1001)
    with pytest.raises(ValueError, match="offset must be non-negative"):
        query_telemetry(dummy_engine, offset=-1)
    with pytest.raises(ValueError, match="order must be 'asc' or 'desc'"):
        query_telemetry(dummy_engine, order="invalid")
    with pytest.raises(ValueError, match="time_basis must be 'received' or 'event'"):
        query_telemetry(dummy_engine, time_basis="invalid")

    now = datetime.now(timezone.utc)
    naive = datetime(2026, 11, 7, 12, 0, 0)
    with pytest.raises(ValueError, match="start_time must be timezone-aware"):
        query_telemetry(dummy_engine, start_time=naive)
    with pytest.raises(ValueError, match="end_time must be timezone-aware"):
        query_telemetry(dummy_engine, end_time=naive)

    earlier = now - timedelta(microseconds=1)
    with pytest.raises(ValueError, match="start_time must be less than or equal to end_time"):
        query_telemetry(dummy_engine, start_time=now, end_time=earlier)
    with pytest.raises(ValueError, match="clockless_only is incompatible"):
        query_telemetry(dummy_engine, clockless_only=True, time_basis="event")


# --- Fresh-schema index proof (shared disposable test database) ---


@needs_real_db
def test_migration_0006_upgrade_and_downgrade():
    engine = create_engine(_db_url())
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM telemetry"))
            conn.execute(text("DELETE FROM telemetry_raw"))

        _downgrade("base")
        _upgrade("0005")

        inspector = inspect(engine)
        indexes_0005 = {idx["name"] for idx in inspector.get_indexes("telemetry")}
        assert "ix_telemetry_device_received_at" not in indexes_0005

        _upgrade("0006")
        inspector = inspect(engine)
        indexes_0006 = {idx["name"] for idx in inspector.get_indexes("telemetry")}
        assert "ix_telemetry_device_received_at" in indexes_0006
        assert "ix_telemetry_run_received_at" in indexes_0006
        assert "ix_telemetry_clockless" in indexes_0006

        _downgrade("0005")
        inspector = inspect(engine)
        indexes_downgraded = {idx["name"] for idx in inspector.get_indexes("telemetry")}
        assert "ix_telemetry_device_received_at" not in indexes_downgraded
        assert "ix_telemetry_run_received_at" not in indexes_downgraded
        assert "ix_telemetry_clockless" not in indexes_downgraded

        _upgrade("head")
    finally:
        engine.dispose()


# --- Genuine seeded query + reconciliation proof (W05-FIX-01) ---


def _seed_schema1(engine, device, boot, seq, received_at, run_id):
    payload = json.loads(FIXTURE_V0.read_text(encoding="utf-8"))
    payload.update(
        device_id=device,
        boot_id=boot,
        seq=seq,
        captured_at=(received_at - timedelta(milliseconds=100)).isoformat(),
        run_id=run_id,
        hardware_config_id="HW-1",
        firmware_version="0.1.0",
        calibration_id="CAL-01",
    )
    wire = json.dumps(payload).encode()
    stored = store_raw(
        engine, topic=f"coldguard/{device}/telemetry", payload=wire,
        received_at=received_at,
    )
    validated, errors = validate_telemetry_payload(json.loads(wire))
    assert validated is not None, errors
    row = map_to_row(validated, raw_id=stored["id"], received_at=received_at)
    row["twin_eligible"] = False
    insert_normalized(engine, row)
    return stored["id"]


def _seed_schema2(engine, device, seq, received_at, run_id):
    fields = json.loads(MEMBER_A_FIXTURE.read_text(encoding="utf-8"))["fields"]
    fields.update(device_id=device, boot_id=uuid4().hex, seq=seq, run_id=run_id)
    frame = ("#CG TELEM " + " ".join(f"{k}={v}" for k, v in fields.items())).encode()
    wire = translate(
        frame, topic=f"coldguard/{device}/telemetry",
        gateway_received_at=received_at, replay=False,
    )
    stored = store_raw(
        engine, topic=f"coldguard/{device}/telemetry", payload=wire,
        received_at=received_at,
    )
    validated, errors = validate_telemetry_payload(json.loads(wire))
    assert validated is not None, errors
    row = map_to_row(validated, raw_id=stored["id"], received_at=received_at)
    row["twin_eligible"] = False
    insert_normalized(engine, row)
    return stored["id"]


def _cleanup_device(engine, device):
    with engine.begin() as conn:
        conn.execute(telemetry.delete().where(telemetry.c.device_id == device))
        conn.execute(
            text("DELETE FROM reconciliation_legacy_audit WHERE raw_id IN "
                 "(SELECT id FROM telemetry_raw WHERE device_id = :d)"),
            {"d": device},
        )
        conn.execute(telemetry_raw.delete().where(telemetry_raw.c.device_id == device))


@needs_real_db
def test_query_telemetry_filters_and_ordering():
    _upgrade("head")
    engine = create_engine(_db_url())
    device = f"w05-query-{uuid4().hex}"
    boot = f"boot-{device}"
    run_id = "RUN-100"
    try:
        now = datetime.now(timezone.utc)
        t1 = now - timedelta(seconds=10)
        t2 = now - timedelta(seconds=5)
        t3 = now - timedelta(seconds=1)

        _seed_schema1(engine, device, boot, 10, t1, run_id)
        _seed_schema1(engine, device, boot, 11, t2, run_id)
        _seed_schema2(engine, device, 12, t3, run_id)

        received_results = query_telemetry(
            engine, device_id=device, time_basis="received", limit=10, order="desc",
        )
        assert len(received_results) == 3
        assert [r["seq"] for r in received_results] == [12, 11, 10]
        assert count_telemetry(engine, device_id=device, time_basis="received") == 3

        event_results = query_telemetry(
            engine, device_id=device, time_basis="event", limit=10, order="desc",
        )
        assert len(event_results) == 2
        assert all(r["time"] is not None for r in event_results)
        assert [r["seq"] for r in event_results] == [11, 10]
        assert count_telemetry(engine, device_id=device, time_basis="event") == 2

        clockless_results = query_telemetry(
            engine, device_id=device, clockless_only=True, limit=5,
        )
        assert len(clockless_results) == 1
        assert clockless_results[0]["seq"] == 12
        assert clockless_results[0]["time"] is None

        # Genuine raw/normalized seeds reconcile cleanly (winner content proven).
        report = reconcile_telemetry(engine, device_id=device)
        assert report.raw_total == 3
        assert report.normalized_total == 3
        assert report.unique_normalized_deliveries == 3
        assert report.discrepancy == 0
        assert report.winner_integrity.total == 0
        assert report.is_reconciled is True
    finally:
        _cleanup_device(engine, device)
        engine.dispose()


# --- Populated migration preservation proof (W05-FIX-06, isolated database) ---


def _ensure_0005(engine, url):
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current is None or current < "0005":
        _upgrade("0005", url)
    elif current > "0005":
        _downgrade("0005", url)


def _snapshot(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            select(telemetry).order_by(telemetry.c.id)
        ).mappings().all()
        raw_count = conn.execute(
            select(func.count()).select_from(telemetry_raw)
        ).scalar_one()
    digest = hashlib.sha256()
    links = []
    fields = (
        "id", "device_id", "boot_id", "seq", "time", "schema_version",
        "t1_c", "t2_c", "t3_c", "raw_id", "calibration_id",
        "hardware_config_id", "firmware_version", "run_id",
    )
    for r in rows:
        links.append((r["id"], r["raw_id"], r["device_id"], r["boot_id"], r["seq"]))
        for f in fields:
            digest.update(repr(r[f]).encode("utf-8"))
        digest.update(repr(r["serial_source"]).encode("utf-8"))
    return {
        "normalized_count": len(rows),
        "raw_count": raw_count,
        "links": links,
        "sha256": digest.hexdigest(),
    }


def _indexes(engine):
    return {idx["name"] for idx in inspect(engine).get_indexes("telemetry")}


@needs_migration_db
def test_populated_0005_0006_cycle_preserves_data():
    url = os.environ["COLDGUARD_TEST_MIGRATION_DB_URL"]
    engine = create_engine(url)
    device = f"mig-proof-{uuid4().hex}"
    boot = f"boot-{device}"
    try:
        _ensure_0005(engine, url)
        assert "ix_telemetry_device_received_at" not in _indexes(engine)

        now = datetime.now(timezone.utc)
        # Realistic schema-1 and schema-2 records through the real pipeline.
        for seq in (1, 2, 3):
            _seed_schema1(engine, device, boot, seq, now - timedelta(seconds=seq), "RUN-MIG")
        _seed_schema2(engine, device, 4, now, "RUN-MIG")

        before = _snapshot(engine)
        assert before["normalized_count"] >= 4
        assert before["raw_count"] >= 4

        _upgrade("0006", url)
        assert "ix_telemetry_device_received_at" in _indexes(engine)
        assert "ix_telemetry_run_received_at" in _indexes(engine)
        assert "ix_telemetry_clockless" in _indexes(engine)
        assert _snapshot(engine) == before

        _downgrade("0005", url)
        assert "ix_telemetry_device_received_at" not in _indexes(engine)
        assert _snapshot(engine) == before

        _upgrade("0006", url)
        assert "ix_telemetry_clockless" in _indexes(engine)
        assert _snapshot(engine) == before
    finally:
        engine.dispose()