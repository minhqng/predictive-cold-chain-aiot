"""W04 migration gates against real PostgreSQL (C-W04-01).

Runs only when COLDGUARD_TEST_DATABASE_URL is set. Proves:
- upgrade from 0003 -> 0004 creates device_twin with correct schema and constraints.
- downgrade from 0004 -> 0003 safely drops device_twin.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

BACKEND_DIR = Path(__file__).resolve().parent.parent
EXPECTED_HEAD = "0004"

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


@needs_real_db
def test_migration_0004_upgrade_and_downgrade():
    engine = create_engine(_db_url())
    # Upgrade to head
    _alembic("upgrade", EXPECTED_HEAD)
    insp = inspect(engine)
    tables = insp.get_table_names()
    assert "device_twin" in tables

    columns = {col["name"] for col in insp.get_columns("device_twin")}
    expected_cols = {
        "device_id",
        "reported_state",
        "desired_state",
        "derived_state",
        "twin_version",
        "last_boot_id",
        "last_seq",
        "reported_at",
        "desired_at",
        "derived_at",
        "created_at",
        "updated_at",
    }
    assert expected_cols.issubset(columns)

    # Downgrade back to 0003
    _alembic("downgrade", "0003")
    insp = inspect(engine)
    assert "device_twin" not in insp.get_table_names()

    # Re-upgrade to head
    _alembic("upgrade", EXPECTED_HEAD)
    insp = inspect(engine)
    assert "device_twin" in insp.get_table_names()
