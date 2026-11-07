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
# W14 added revision 0010 (prediction evidence and ordered inputs).
EXPECTED_HEAD = "0010"

# C-W03 evolution: head moved 0002 -> 0003; the assertions above now
# cover the normalized telemetry table as well. The W02->W03 upgrade
# over pre-existing duplicate raw rows is proven in test_migration_w03.

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

EXPECTED_TELEMETRY_COLUMNS = {
    "id",
    "time",
    "device_id",
    "boot_id",
    "seq",
    "run_id",
    "t1_c",
    "t2_c",
    "t3_c",
    "t_air_c",
    "rh_pct",
    "door_state",
    "cooling_voltage_v",
    "cooling_current_a",
    "cooling_power_w",
    "cooling_energy_counter_wh",
    "applied_cooling",
    "applied_duty",
    "thermal_quality",
    "environment_quality",
    "electrical_quality",
    "overall_quality",
    "device_mode",
    "hardware_config_id",
    "firmware_version",
    "calibration_id",
    "schema_version",
    "backend_received_at",
    "raw_id",
    "twin_eligible",
    "serial_source",
}

EXPECTED_TELEMETRY_INDEXES = {
    "ix_telemetry_run_id",
    "ix_telemetry_device_time",
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


def _downgrade_to_base() -> None:
    """Reset to an empty schema for upgrade-path tests.

    Downgrading past 0003 restores the W02 status guard, which
    fail-closed rejects databases still holding W03-only statuses.
    Rows left behind by other test files are test pollution, not
    product data, so they are removed here first. The product
    migration itself never deletes evidence.
    """
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            for table in ("telemetry", "telemetry_raw"):
                try:
                    connection.execute(text(f"DELETE FROM {table}"))
                    connection.commit()
                except Exception:
                    connection.rollback()
    finally:
        engine.dispose()
    _alembic("downgrade", "base")


def _assert_expected_schema() -> None:
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            tables = set(inspect(engine).get_table_names())
            columns = {col["name"] for col in inspect(engine).get_columns("telemetry_raw")}
            indexes = {index["name"] for index in inspect(engine).get_indexes("telemetry_raw")}
            norm_columns = {col["name"] for col in inspect(engine).get_columns("telemetry")}
            norm_indexes = {index["name"] for index in inspect(engine).get_indexes("telemetry")}
            hypertables = connection.execute(
                text("SELECT count(*) FROM timescaledb_information.hypertables "
                     "WHERE hypertable_name IN ('telemetry_raw', 'telemetry')")
            ).scalar()
    finally:
        engine.dispose()
    assert head == EXPECTED_HEAD
    assert tables == {
        "alembic_version", "telemetry_raw", "telemetry",
        "device_twin", "device_twin_retired_boot",
        "reconciliation_boundary", "reconciliation_legacy_audit",
        "commands", "command_attempts", "command_acks", "command_transitions",
        "experiments", "experiment_transitions",
        "predictions", "prediction_inputs",
    }, tables
    assert columns == EXPECTED_COLUMNS, columns - EXPECTED_COLUMNS or EXPECTED_COLUMNS - columns
    assert EXPECTED_INDEXES <= indexes, EXPECTED_INDEXES - indexes
    assert norm_columns == EXPECTED_TELEMETRY_COLUMNS, (
        norm_columns - EXPECTED_TELEMETRY_COLUMNS or EXPECTED_TELEMETRY_COLUMNS - norm_columns
    )
    assert EXPECTED_TELEMETRY_INDEXES <= norm_indexes, (
        EXPECTED_TELEMETRY_INDEXES - norm_indexes
    )
    assert hypertables == 0, "W03 uses a regular table: no Timescale hypertable"


@needs_real_db
def test_upgrade_from_empty_reaches_head_with_expected_schema():
    _downgrade_to_base()
    _alembic("upgrade", "head")
    _assert_expected_schema()


@needs_real_db
def test_upgrade_from_w01_revision_reaches_head():
    _downgrade_to_base()
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
