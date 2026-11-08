"""Actual consistent pg_dump and clean TimescaleDB restore for SOFTWARE_SIMULATION."""

import os

import pytest
from sqlalchemy import create_engine

from coldguard_backend.campaign_integrity import close_run
from coldguard_backend.evidence_backup import backup_campaign, restore_backup, verify_backup
from tests.campaign_testkit import complete_run, register_fixture


def ready_campaign(engine):
    context = register_fixture(engine)
    for arm in ("A", "B"):
        run = complete_run(context, arm)
        with engine.begin() as connection:
            close_run(connection, context["draft"]["campaign_id"], run["run_id"], reason="SOFTWARE_SIMULATION wave block")
    return context


@pytest.mark.skipif(not os.environ.get("COLDGUARD_TEST_ARCHIVE_RESTORE_URL"), reason="requires separate empty disposable archive restore DB")
def test_wave1_consistent_archive_restores_all_evidence_and_detects_corruption(db_engine, tmp_path):
    context = ready_campaign(db_engine)
    directory = tmp_path / "wave1-backup"
    receipt = backup_campaign(db_engine, context["draft"]["campaign_id"], directory, pg_dump=os.environ["COLDGUARD_TEST_PG_DUMP"])
    assert receipt["snapshot_consistency"] == "pg_export_snapshot"
    assert receipt["restore_verified"] is False
    restored = restore_backup(directory, os.environ["COLDGUARD_TEST_ARCHIVE_RESTORE_URL"], pg_restore=os.environ["COLDGUARD_TEST_PG_RESTORE"])
    assert restored["match"] is True
    assert {"predictions", "prediction_inputs", "commands", "shadow_decisions", "physical_assessments", "campaign_run_closures"} <= restored["restored"]["tables"].keys()
    assert restored["restored"] == receipt["source_fingerprints"]
    with pytest.raises(ValueError, match="no application tables"):
        restore_backup(directory, os.environ["COLDGUARD_TEST_ARCHIVE_RESTORE_URL"], pg_restore=os.environ["COLDGUARD_TEST_PG_RESTORE"])
    with (directory / "database.dump").open("ab") as artifact:
        artifact.write(b"corruption")
    with pytest.raises(ValueError, match="checksum"):
        verify_backup(directory)


def test_backup_refuses_incomplete_campaign_and_failed_dump_leaves_no_published_artifact(db_engine, tmp_path, monkeypatch):
    context = register_fixture(db_engine)
    target = tmp_path / "incomplete"
    with pytest.raises(ValueError, match="incomplete evidence"):
        backup_campaign(db_engine, context["draft"]["campaign_id"], target)
    assert not target.exists()
    context = ready_campaign(db_engine)
    def failed(*_args, **_kwargs):
        raise RuntimeError("demonstrated dump failure")
    monkeypatch.setattr("coldguard_backend.evidence_backup._postgres_command", failed)
    target = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="dump failure"):
        backup_campaign(db_engine, context["draft"]["campaign_id"], target)
    assert not target.exists()
