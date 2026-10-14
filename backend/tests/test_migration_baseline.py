"""Migration baseline proof against real PostgreSQL/Timescale (C-W01-04).

Runs only when COLDGUARD_TEST_DATABASE_URL is set, against a real
provider (never SQLite, never mocked). Proves: upgrade from an empty
database reaches the expected head, the head is persisted in
``alembic_version``, no application tables were created by the skeletal
baseline, and re-applying upgrade-to-head is safe.

Defects detected: a baseline revision that cannot apply from empty, a
drifted expected head, or a baseline that silently creates domain
tables reserved for later slices.
"""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = Path(__file__).resolve().parent.parent
EXPECTED_HEAD = "0001"

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
    assert tables == {"alembic_version"}


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
