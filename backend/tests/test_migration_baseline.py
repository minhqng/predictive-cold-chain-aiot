"""Migration baseline proof against real PostgreSQL/Timescale (C-W01-04,
evolved by C-W02-04).

Runs only when COLDGUARD_TEST_DATABASE_URL is set, against a real
provider (never SQLite, never mocked). Proves: upgrade from an empty
database reaches the expected head, the head is persisted in
``alembic_version``, only the reviewed application tables exist, and
re-applying upgrade-to-head is safe.

C-W02 evolution note: the expected head moved 0001 → 0002 and the
reviewed ``telemetry_raw`` table (revision 0002, C-W02-04) and the
reviewed normalized ``telemetry`` table (revision 0003, C-W03-03/04)
are part of the expected schema, alongside the revision 0004 Twin tables.
The W01 "no domain tables" assertion is
superseded by that reviewed revision; the W01→W02 upgrade path itself
is proven in ``test_migration_w02.py``.

Defects detected: a baseline revision that cannot apply from empty, a
drifted expected head, or unreviewed tables outside the migration
history.
"""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = Path(__file__).resolve().parent.parent
# Campaign namespace, closure and immutable freeze evidence are reviewed through 0014.
EXPECTED_HEAD = "0014"

needs_real_db = pytest.mark.skipif(
    not os.environ.get("COLDGUARD_TEST_DATABASE_URL"),
    reason="requires COLDGUARD_TEST_DATABASE_URL pointing at a fresh database",
)


def _alembic(*args: str) -> None:
    env = dict(os.environ)
    env["DATABASE_URL"] = os.environ["COLDGUARD_TEST_DATABASE_URL"]
    subprocess.run(
        ["uv", "run", "--locked", "alembic", "-c", "alembic.ini", *args],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


@needs_real_db
def test_baseline_upgrades_from_empty_and_persists_head():
    _alembic("upgrade", "head")
    engine = create_engine(os.environ["COLDGUARD_TEST_DATABASE_URL"])
    try:
        with engine.connect() as connection:
            head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert head == EXPECTED_HEAD
    assert tables == {
        "alembic_version", "telemetry_raw", "telemetry",
        "device_twin", "device_twin_retired_boot",
        "reconciliation_boundary", "reconciliation_legacy_audit",
        "commands", "command_attempts", "command_acks", "command_transitions",
        "experiments", "experiment_transitions",
        "predictions", "prediction_inputs", "shadow_decisions", "physical_assessments",
        "policy_approvals",
        "campaigns", "campaign_runs", "campaign_run_closures",
        "campaign_freezes",
    }


@needs_real_db
def test_repeated_upgrade_to_head_is_safe():
    _alembic("upgrade", "head")
    _alembic("upgrade", "head")
    engine = create_engine(os.environ["COLDGUARD_TEST_DATABASE_URL"])
    try:
        with engine.connect() as connection:
            head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()
    assert head == EXPECTED_HEAD
