"""Raw-ingestion migration proof against real PostgreSQL (C-W02-04).

Runs only when COLDGUARD_TEST_DATABASE_URL is set, against a real
provider (never SQLite, never mocked). Proves: the W02 migration
applies to an empty database through the full 0001→0002 chain, upgrades
from an existing W01 revision, persists the new head, creates exactly
the expected raw schema (columns, indexes, status CHECK), creates no
hypertable and no unplanned tables, and repeated upgrade is safe.

Defects detected: a chain that cannot apply from empty, a W01 database
that cannot upgrade, missing/incorrect raw columns or indexes, an
absent status guard, a premature Timescale hypertable, or drifted head.
"""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = Path(__file__).resolve().parent.parent
EXPECTED_HEAD = "0002"

EXPECTED_COLUMNS = {
    "id",
    "device_id",
    "boot_id",
    "seq",
    "topic",
    "schema_version",
    "captured_at",
    "backend_received_at",
    "raw_payload",
    "raw_json",
    "payload_sha256",
    "ingest_status",
    "validation_errors",
    "run_id",
    "created_at",
}

EXPECTED_INDEXES = {
    "ix_telemetry_raw_identity",
    "ix_telemetry_raw_run_id",
    "ix_telemetry_raw_ingest_status",
}

needs_real_db = pytest.mark.skipif(
    not os.environ.get("COLDGUARD_TEST_DATABASE_URL"),
    reason="requires COLDGUARD_TEST_DATABASE_URL pointing at a test database",
)


def _db_url() -> str:
    return os.environ["COLDGUARD_TEST_DATABASE_URL"]


def _alembic(*args: str) -> None:
    env = dict(os.environ)
    env["DATABASE_URL"] = _db_url()
    subprocess.run(
        ["uv", "run", "--locked", "alembic", "-c", "alembic.ini", *args],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _assert_expected_schema() -> None:
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            tables = set(inspect(engine).get_table_names())
            columns = {col["name"] for col in inspect(engine).get_columns("telemetry_raw")}
            indexes = {index["name"] for index in inspect(engine).get_indexes("telemetry_raw")}
            hypertables = connection.execute(
                text("SELECT count(*) FROM timescaledb_information.hypertables "
                     "WHERE hypertable_name = 'telemetry_raw'")
            ).scalar()
    finally:
        engine.dispose()
    assert head == EXPECTED_HEAD
    assert tables == {"alembic_version", "telemetry_raw"}, tables
    assert columns == EXPECTED_COLUMNS, columns - EXPECTED_COLUMNS or EXPECTED_COLUMNS - columns
    assert EXPECTED_INDEXES <= indexes, EXPECTED_INDEXES - indexes
    assert hypertables == 0, "W02 must not create a Timescale hypertable"


@needs_real_db
def test_upgrade_from_empty_reaches_head_with_expected_schema():
    _alembic("downgrade", "base")
    _alembic("upgrade", "head")
    _assert_expected_schema()


@needs_real_db
def test_upgrade_from_w01_revision_reaches_head():
    _alembic("downgrade", "base")
    _alembic("upgrade", "0001")
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert tables == {"alembic_version"}
    _alembic("upgrade", "head")
    _assert_expected_schema()


@needs_real_db
def test_malformed_identity_columns_are_nullable():
    _alembic("upgrade", "head")
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    "INSERT INTO telemetry_raw "
                    "(topic, backend_received_at, raw_payload, payload_sha256, "
                    " ingest_status, created_at) "
                    "VALUES ('coldguard/coldguard-001/telemetry', now(), "
                    " '{broken', '0', 'RECEIVED_MALFORMED_JSON', now())"
                )
            )
            connection.commit()
            count = connection.execute(
                text("SELECT count(*) FROM telemetry_raw "
                     "WHERE ingest_status = 'RECEIVED_MALFORMED_JSON'")
            ).scalar()
            connection.execute(text("DELETE FROM telemetry_raw WHERE raw_payload = '{broken'"))
            connection.commit()
    finally:
        engine.dispose()
    assert count >= 1


@needs_real_db
def test_status_check_rejects_invented_status():
    _alembic("upgrade", "head")
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            with pytest.raises(Exception):
                connection.execute(
                    text(
                        "INSERT INTO telemetry_raw "
                        "(topic, backend_received_at, raw_payload, payload_sha256, "
                        " ingest_status, created_at) "
                        "VALUES ('t', now(), '{}', '0', 'INVENTED_STATUS', now())"
                    )
                )
    finally:
        engine.dispose()


@needs_real_db
def test_repeated_upgrade_to_head_is_safe():
    _alembic("upgrade", "head")
    _alembic("upgrade", "head")
    _assert_expected_schema()
