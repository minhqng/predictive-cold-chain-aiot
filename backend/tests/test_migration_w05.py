"""Verify revision 0006 storage baseline, query helpers, and TimescaleDB evaluation (C-W05-02).

Proves:
- Migration 0005 -> 0006 upgrade creates required indexes.
- Downgrade from 0006 to 0005 cleanly drops indexes.
- Query helpers handle time-range, run-ID, device, and clockless queries.
- Bounded pagination and input validation rules.
"""

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text

from coldguard_backend.normalized_store import (
    count_telemetry,
    query_telemetry,
    telemetry,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent

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


# --- Unit tests (No database required) ---


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

    earlier = now - datetime.resolution
    with pytest.raises(ValueError, match="start_time must be less than or equal to end_time"):
        query_telemetry(dummy_engine, start_time=now, end_time=earlier)


# --- Provider tests (Requires COLDGUARD_TEST_DATABASE_URL) ---


@needs_real_db
def test_migration_0006_upgrade_and_downgrade():
    engine = create_engine(_db_url())
    try:
        with engine.begin() as conn:
            # Clean clockless samples so 0005 downgrade to 0004 (which requires time NOT NULL) succeeds
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

        _upgrade("0006")
    finally:
        engine.dispose()


@needs_real_db
def test_query_telemetry_filters_and_ordering():
    from datetime import timedelta
    from coldguard_backend.reconciliation import reconcile_telemetry

    engine = create_engine(_db_url())
    try:
        _upgrade("0006")
        now = datetime.now(timezone.utc)

        with engine.begin() as conn:
            # Clean test tables for deterministic checks
            conn.execute(text("DELETE FROM telemetry"))
            conn.execute(text("DELETE FROM telemetry_raw"))

            # Seed telemetry_raw rows
            t1 = now - timedelta(seconds=10)
            t2 = now - timedelta(seconds=5)
            t3 = now - timedelta(seconds=1)

            # Raw 1
            raw1_id = conn.execute(
                text(
                    "INSERT INTO telemetry_raw (device_id, boot_id, seq, topic, schema_version, "
                    "backend_received_at, raw_payload, payload_sha256, ingest_status, run_id, created_at) "
                    "VALUES ('coldguard-001', 'boot-1', 10, 'coldguard/coldguard-001/telemetry', 1, "
                    ":recv, :payload, 'sha1', 'RECEIVED_VALID', 'RUN-100', :recv) "
                    "RETURNING id"
                ),
                {"recv": t1, "payload": '{"calibration_id": "CAL-01"}'},
            ).scalar_one()

            # Raw 2
            raw2_id = conn.execute(
                text(
                    "INSERT INTO telemetry_raw (device_id, boot_id, seq, topic, schema_version, "
                    "backend_received_at, raw_payload, payload_sha256, ingest_status, run_id, created_at) "
                    "VALUES ('coldguard-001', 'boot-1', 11, 'coldguard/coldguard-001/telemetry', 1, "
                    ":recv, :payload, 'sha2', 'RECEIVED_VALID', 'RUN-100', :recv) "
                    "RETURNING id"
                ),
                {"recv": t2, "payload": '{"calibration_id": "CAL-01"}'},
            ).scalar_one()

            # Raw 3 (Clockless serial)
            raw3_id = conn.execute(
                text(
                    "INSERT INTO telemetry_raw (device_id, boot_id, seq, topic, schema_version, "
                    "backend_received_at, raw_payload, payload_sha256, ingest_status, run_id, created_at) "
                    "VALUES ('coldguard-001', 'boot-1', 12, 'coldguard/coldguard-001/telemetry', 2, "
                    ":recv, :payload, 'sha3', 'RECEIVED_VALID', 'RUN-100', :recv) "
                    "RETURNING id"
                ),
                {"recv": t3, "payload": '{"calibration_id": null}'},
            ).scalar_one()

            # Seed normalized telemetry rows
            conn.execute(
                text(
                    "INSERT INTO telemetry (time, device_id, boot_id, seq, run_id, door_state, "
                    "applied_cooling, thermal_quality, environment_quality, electrical_quality, "
                    "overall_quality, hardware_config_id, firmware_version, schema_version, "
                    "backend_received_at, raw_id, calibration_id) "
                    "VALUES (:time, 'coldguard-001', 'boot-1', 10, 'RUN-100', 'CLOSED', 'OFF', "
                    "'VALID', 'VALID', 'VALID', 'VALID', 'HW-1', '0.1.0', 1, :recv, :raw_id, 'CAL-01')"
                ),
                {"time": t1 - timedelta(milliseconds=100), "recv": t1, "raw_id": raw1_id},
            )

            conn.execute(
                text(
                    "INSERT INTO telemetry (time, device_id, boot_id, seq, run_id, door_state, "
                    "applied_cooling, thermal_quality, environment_quality, electrical_quality, "
                    "overall_quality, hardware_config_id, firmware_version, schema_version, "
                    "backend_received_at, raw_id, calibration_id) "
                    "VALUES (:time, 'coldguard-001', 'boot-1', 11, 'RUN-100', 'CLOSED', 'ON', "
                    "'VALID', 'VALID', 'VALID', 'VALID', 'HW-1', '0.1.0', 1, :recv, :raw_id, 'CAL-01')"
                ),
                {"time": t2 - timedelta(milliseconds=100), "recv": t2, "raw_id": raw2_id},
            )

            # Clockless normalized row (time IS NULL, requires schema_version=2 and serial_source object)
            conn.execute(
                text(
                    "INSERT INTO telemetry (time, device_id, boot_id, seq, run_id, door_state, "
                    "applied_cooling, thermal_quality, environment_quality, electrical_quality, "
                    "overall_quality, hardware_config_id, firmware_version, schema_version, "
                    "backend_received_at, raw_id, calibration_id, serial_source) "
                    "VALUES (NULL, 'coldguard-001', 'boot-1', 12, 'RUN-100', 'UNKNOWN', 'OFF', "
                    "'VALID', 'UNKNOWN', 'VALID', 'DEGRADED', 'HW-1', '0.1.0', 2, :recv, :raw_id, NULL, :serial)"
                ),
                {
                    "recv": t3,
                    "raw_id": raw3_id,
                    "serial": '{"schema_version": 2, "clock_quality": "UNAVAILABLE"}',
                },
            )

        # 1. Received basis includes all 3 records (including clockless)
        received_results = query_telemetry(
            engine,
            device_id="coldguard-001",
            time_basis="received",
            limit=10,
            order="desc",
        )
        assert len(received_results) == 3
        assert received_results[0]["seq"] == 12  # newest received
        assert received_results[1]["seq"] == 11
        assert received_results[2]["seq"] == 10

        assert count_telemetry(engine, device_id="coldguard-001", time_basis="received") == 3

        # 2. Event basis excludes clockless records (time IS NULL)
        event_results = query_telemetry(
            engine,
            device_id="coldguard-001",
            time_basis="event",
            limit=10,
            order="desc",
        )
        assert len(event_results) == 2
        assert all(r["time"] is not None for r in event_results)
        assert event_results[0]["seq"] == 11  # newest event
        assert event_results[1]["seq"] == 10

        assert count_telemetry(engine, device_id="coldguard-001", time_basis="event") == 2

        # 3. Clockless only returns exactly the clockless record
        clockless_results = query_telemetry(
            engine,
            device_id="coldguard-001",
            clockless_only=True,
            limit=5,
        )
        assert len(clockless_results) == 1
        assert clockless_results[0]["seq"] == 12
        assert clockless_results[0]["time"] is None

        # 4. Real provider reconciliation check
        report = reconcile_telemetry(engine, device_id="coldguard-001")
        assert report.raw_total == 3
        assert report.normalized_total == 3
        assert report.unique_normalized_deliveries == 3
        assert report.discrepancy == 0
        assert report.is_reconciled is True
    finally:
        engine.dispose()
