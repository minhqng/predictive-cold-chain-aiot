"""W03 migration gates against real PostgreSQL (C-W03-03/04/05).

Runs only when COLDGUARD_TEST_DATABASE_URL is set, against a real
provider (never SQLite). Proves the two required starting states:

* fresh database: base through the current head with
  the expected tables/constraints/indexes;
* existing W02 database: 0002 + real raw messages + repeated logical
  identities → 0003 succeeds, preserves every historical raw row
  (no silent deletion), creates no backfilled normalized rows, and
  leaves dedup enforceable;

plus: repeated upgrade safety, Timescale extension intact, no
hypertable created, raw CHECK widened with the mismatch status, and
the normalized UNIQUE + NOT NULL identity guardrails present.
"""

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = Path(__file__).resolve().parent.parent
# W06 added revision 0008 (durable command lifecycle storage).
EXPECTED_HEAD = "0008"


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
    product data (a genuine W02 database satisfies the guard by
    construction), so they are removed here first. The product
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


def _wire(device_id: str, boot_id: str, seq: int, run_id: str) -> str:
    from coldguard_backend.simulator import build_telemetry

    payload = build_telemetry(boot_id=boot_id, seq=seq, run_id=run_id)
    payload["device_id"] = device_id
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


@needs_real_db
def test_fresh_upgrade_preserves_w03_tables():
    _downgrade_to_base()
    _alembic("upgrade", "head")
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert head == EXPECTED_HEAD
    assert {"alembic_version", "telemetry_raw", "telemetry"} <= tables


@needs_real_db
def test_w02_existing_data_with_duplicates_upgrades_without_loss():
    _downgrade_to_base()
    _alembic("upgrade", "0002")
    boot = f"boot-w02up-{uuid.uuid4().hex[:8]}"
    run = f"CG-W02UP-{uuid.uuid4().hex[:8]}"
    topic = "coldguard/coldguard-001/telemetry"
    wire = _wire("coldguard-001", boot, 5, run)
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            # A valid W02 database already containing a repeated logical
            # identity (QoS 1 redelivery kept observable) plus malformed
            # and invalid evidence.
            for _ in range(2):
                connection.execute(
                    text(
                        "INSERT INTO telemetry_raw "
                        "(device_id, boot_id, seq, topic, schema_version, "
                        " backend_received_at, raw_payload, payload_sha256, "
                        " ingest_status, run_id, created_at) "
                        "VALUES (:device, :boot, 5, :topic, 1, now(), :wire, "
                        " 'dup', 'RECEIVED_VALID', :run, now())"
                    ),
                    {"device": "coldguard-001", "boot": boot, "topic": topic,
                     "wire": wire, "run": run},
                )
            connection.execute(
                text(
                    "INSERT INTO telemetry_raw "
                    "(topic, backend_received_at, raw_payload, payload_sha256, "
                    " ingest_status, created_at) "
                    "VALUES (:topic, now(), '{broken', 'm', "
                    " 'RECEIVED_MALFORMED_JSON', now())"
                ),
                {"topic": topic},
            )
            connection.commit()
            before = connection.execute(
                text("SELECT count(*) FROM telemetry_raw WHERE boot_id = :boot"),
                {"boot": boot},
            ).scalar()
            assert before == 2
    finally:
        engine.dispose()
    # The upgrade must succeed despite the repeated identity — no raw
    # UNIQUE constraint may have been added blindly.
    _alembic("upgrade", "head")
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            after = connection.execute(
                text("SELECT count(*) FROM telemetry_raw WHERE boot_id = :boot"),
                {"boot": boot},
            ).scalar()
            normalized = connection.execute(
                text("SELECT count(*) FROM telemetry WHERE boot_id = :boot"),
                {"boot": boot},
            ).scalar()
            constraint = connection.execute(
                text(
                    "SELECT count(*) FROM pg_constraint WHERE conname = "
                    "'uq_telemetry_identity'"
                )
            ).scalar()
            not_null_violations = connection.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name = 'telemetry' AND column_name IN "
                    "('device_id', 'boot_id', 'seq') AND is_nullable = 'YES'"
                )
            ).scalar()
    finally:
        engine.dispose()
    assert head == EXPECTED_HEAD
    assert after == before == 2, "historical raw duplicates must be preserved"
    assert normalized == 0, "no fabricated backfill from W02 raw rows"
    assert constraint == 1, "normalized UNIQUE(device_id, boot_id, seq) missing"
    assert not_null_violations == 0, "normalized identity must be NOT NULL"


@needs_real_db
def test_repeated_upgrade_to_current_head_is_safe():
    _alembic("upgrade", "head")
    _alembic("upgrade", "head")
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()
    assert head == EXPECTED_HEAD


@needs_real_db
def test_timescale_extension_intact_and_no_hypertable():
    _alembic("upgrade", "head")
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            extension = connection.execute(
                text("SELECT count(*) FROM pg_extension WHERE extname = 'timescaledb'")
            ).scalar()
            hypertables = connection.execute(
                text(
                    "SELECT count(*) FROM timescaledb_information.hypertables "
                    "WHERE hypertable_name IN ('telemetry_raw', 'telemetry')"
                )
            ).scalar()
    finally:
        engine.dispose()
    assert extension == 1, "Timescale extension must remain installed"
    assert hypertables == 0, "W03 creates no hypertable (regular table by design)"


@needs_real_db
def test_raw_check_accepts_mismatch_status_and_rejects_invented():
    _alembic("upgrade", "head")
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    "INSERT INTO telemetry_raw "
                    "(topic, backend_received_at, raw_payload, payload_sha256, "
                    " ingest_status, created_at) "
                    "VALUES ('coldguard/x/telemetry', now(), '{}', 's', "
                    " 'REJECTED_TOPIC_MISMATCH', now())"
                )
            )
            connection.commit()
            with pytest.raises(Exception):
                connection.execute(
                    text(
                        "INSERT INTO telemetry_raw "
                        "(topic, backend_received_at, raw_payload, payload_sha256, "
                        " ingest_status, created_at) "
                        "VALUES ('t', now(), '{}', '0', 'INVENTED_STATUS', now())"
                    )
                )
            connection.rollback()
            connection.execute(
                text("DELETE FROM telemetry_raw WHERE payload_sha256 = 's'")
            )
            connection.commit()
    finally:
        engine.dispose()
