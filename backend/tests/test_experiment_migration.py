"""Exercise revision 0009 on the isolated command/run migration database."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError

from coldguard_backend import command_store as commands
from coldguard_backend import experiment_store as runs
from tests.command_testkit import make_command
from tests.test_command_migration import (
    _downgrade, _ensure, _revision, _tables, _upgrade, _url, needs_migration_db,
)


@needs_migration_db
def test_experiment_revision_refuses_to_drop_history_and_preserves_commands():
    engine = create_engine(_url())
    run_id = f"migration-{uuid4().hex}"
    command = make_command(f"cmd-{run_id}")
    try:
        _ensure("0008", engine)
        with engine.begin() as conn:
            saved = commands.create_command(conn, command)["command"]
        _upgrade("0009")
        assert _revision(engine) == "0009"
        with engine.begin() as conn:
            runs.create_run(conn, runs.RunCreate(
                run_id=run_id, device_id=command.device_id, scenario_id="S2",
                controller_id="REACTIVE", versions={"schema": 1},
            ))
        try:
            with pytest.raises(DBAPIError, match="run evidence exists"):
                _downgrade("0008")
            assert _revision(engine) == "0009"
            with engine.connect() as conn:
                assert runs.run_history(conn, run_id)[0]["to_status"] == "PLANNED"
        finally:
            with engine.begin() as conn:
                for table in (runs.experiment_transitions, runs.experiments):
                    conn.execute(table.delete().where(table.c.run_id == run_id))
        _downgrade("0008")
        assert "experiments" not in _tables(engine)
        with engine.connect() as conn:
            assert commands.get_command(conn, command.command_id) == saved
    finally:
        with engine.begin() as conn:
            conn.execute(commands.commands.delete().where(commands.commands.c.command_id == command.command_id))
        engine.dispose()
