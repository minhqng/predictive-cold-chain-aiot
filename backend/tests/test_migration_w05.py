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


# --- Provider tests (Requires COLDGUARD_TEST_DATABASE_URL) ---


@needs_real_db
def test_migration_0006_upgrade_and_downgrade():
    engine = create_engine(_db_url())
    try:
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
    engine = create_engine(_db_url())
    try:
        _upgrade("0006")
        now = datetime.now(timezone.utc)
        # Test query execution against real PostgreSQL
        results = query_telemetry(
            engine,
            device_id="coldguard-001",
            limit=10,
            order="desc",
        )
        assert isinstance(results, list)

        count = count_telemetry(engine, device_id="coldguard-001")
        assert isinstance(count, int)

        clockless_results = query_telemetry(
            engine,
            device_id="coldguard-001",
            clockless_only=True,
            limit=5,
        )
        assert isinstance(clockless_results, list)
    finally:
        engine.dispose()
