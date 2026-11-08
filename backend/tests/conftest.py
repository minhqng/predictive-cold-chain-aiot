"""Shared pytest fixtures for the backend test suite."""

import os

import pytest
from sqlalchemy.engine import make_url

from tests.command_testkit import db_engine  # noqa: F401  (registers the fixture)


@pytest.fixture(autouse=True)
def isolate_destructive_legacy_migrations(request, monkeypatch):
    """Migration rollback proofs must not delete or downgrade campaign evidence."""
    module = request.node.path.name
    destructive = module in {"test_migration_w02.py", "test_migration_w03.py", "test_migration_w04.py"} or (
        module == "test_migration_w05.py" and request.node.originalname == "test_migration_0006_upgrade_and_downgrade"
    ) or (
        module == "test_twin.py" and request.node.originalname == "test_upgrade_keeps_populated_w03_history_without_promoting_it"
    )
    if not destructive:
        return
    value = os.environ.get("COLDGUARD_TEST_LEGACY_MIGRATION_DB_URL")
    if not value:
        pytest.skip("destructive legacy migration proofs require a separate disposable COLDGUARD_TEST_LEGACY_MIGRATION_DB_URL")
    target = make_url(value)
    suite = make_url(os.environ["COLDGUARD_TEST_DATABASE_URL"])
    if (target.drivername != "postgresql+psycopg" or target.host != "127.0.0.1" or target.query
        or target.database in {None, "postgres", "template0", "template1"}
        or (target.host, target.port or 5432, target.database) == (suite.host, suite.port or 5432, suite.database)):
        raise ValueError("destructive migration database must be a separate direct loopback disposable database")
    monkeypatch.setenv("COLDGUARD_TEST_DATABASE_URL", value)
