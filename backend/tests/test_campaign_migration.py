"""Preserve W18 evidence and verify campaign constraints in a separate migration DB."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import DBAPIError

from coldguard_backend.evidence_tables import fingerprint_connection
from coldguard_backend import command_store
from tests.campaign_testkit import register_fixture
from tests.command_testkit import make_command
from tests.test_command_migration import ENV, _downgrade, _revision, _upgrade
from tests.test_command_migration import _seed_telemetry


@pytest.mark.skipif(not os.environ.get("COLDGUARD_TEST_CAMPAIGN_MIGRATION_URL"), reason="requires a separate disposable campaign migration DB")
def test_0013_upgrade_rollback_preservation_and_populated_downgrade_refusal(monkeypatch):
    monkeypatch.setenv(ENV, os.environ["COLDGUARD_TEST_CAMPAIGN_MIGRATION_URL"])
    engine = create_engine(os.environ[ENV])
    try:
        _upgrade("0012")
        suffix = uuid4().hex
        _seed_telemetry(engine, "w19-migration-" + suffix)
        with engine.begin() as connection:
            command_store.create_command(connection, make_command("w19-migration-" + suffix))
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            before = fingerprint_connection(connection)["tables"]
            assert before["telemetry_raw"]["rows"] == 1 and before["commands"]["rows"] == 1
        _upgrade("0013")
        assert _revision(engine) == "0013"
        assert {"campaigns", "campaign_runs", "campaign_run_closures"} <= set(inspect(engine).get_table_names())
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            after = fingerprint_connection(connection)["tables"]
            assert {key: after[key] for key in before if key != "alembic_version"} == {key: value for key, value in before.items() if key != "alembic_version"}
        _downgrade("0012")
        _upgrade("0013")
        register_fixture(engine)
        with pytest.raises(DBAPIError, match="0013 downgrade refused"):
            _downgrade("0012")
        assert _revision(engine) == "0013"
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            assert fingerprint_connection(connection)["tables"]["campaign_runs"]["rows"] == 2
    finally:
        engine.dispose()
