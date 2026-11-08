"""Final populated restoration gates. SOFTWARE_SIMULATION; no human/physical signoff."""

import json
import os
from pathlib import Path
import re

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select

from coldguard_backend import command_store as cs
from coldguard_backend.campaign_export import build_campaign_export
from coldguard_backend.campaign_freeze import freeze_campaign, get_freeze, verify_frozen_package
from coldguard_backend.evidence_backup import backup_campaign, local_database_url, restore_backup
from coldguard_backend.evidence_tables import fingerprint_connection
from coldguard_backend.final_package import create_final_package, verify_final_package
from coldguard_backend.physical_verification import physical_assessments
from tests.command_testkit import utcnow
from tests.handover_testkit import populated_context


@pytest.mark.skipif(not os.environ.get("COLDGUARD_TEST_HANDOVER_SOURCE_URL") or not os.environ.get("COLDGUARD_TEST_HANDOVER_RESTORE_URL"),
                    reason="requires its own fresh populated-source and empty restore DBs")
def test_final_migration_and_all_populated_evidence_survive_clean_restore(tmp_path, monkeypatch):
    source = local_database_url(os.environ["COLDGUARD_TEST_HANDOVER_SOURCE_URL"])
    target = local_database_url(os.environ["COLDGUARD_TEST_HANDOVER_RESTORE_URL"])
    assert (source.host, source.port, source.database) != (target.host, target.port, target.database)
    engine = create_engine(source)
    restored_engine = create_engine(target)
    try:
        with engine.connect() as connection:
            assert inspect(connection).get_table_names(schema="public") == []
        with restored_engine.connect() as connection:
            assert inspect(connection).get_table_names(schema="public") == []
        monkeypatch.setenv("DATABASE_URL", source.render_as_string(hide_password=False))
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "src/coldguard_backend/migrations"))
        alembic_command.upgrade(config, "head")
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            zero = fingerprint_connection(connection)
        assert zero["revisions"] == ["0014"] and len(zero["tables"]) == 22
        assert all(row["rows"] == 0 for name, row in zero["tables"].items() if name not in {"alembic_version", "reconciliation_boundary"})
        context = populated_context(engine, tmp_path / "fixture", backend_commit="a" * 40)
        record = freeze_campaign(engine, context["freeze_draft"], artifact_root=context["artifact_root"],
                                 backup_directory=context["backup"], destination=context["destination"])
        archive = tmp_path / "post-freeze-backup"
        receipt = backup_campaign(engine, context["draft"]["campaign_id"], archive, pg_dump=os.environ["COLDGUARD_TEST_PG_DUMP"])
        assert all(row["rows"] > 0 for row in receipt["source_fingerprints"]["tables"].values())
        failed = json.loads((context["failed_archive"] / "receipt.json").read_bytes())
        assert failed["campaign_id"] != receipt["campaign_id"] and failed["freeze_ready"] is False
        assert failed["run_status_counts"] == {"INVALID": 1, "ABORTED": 1} and all(failed["run_issues"].values())
        with engine.connect() as connection:
            assert all(cs.get_command(connection, identity)["status"] == "ACK_ACCEPTED" for identity in context["command_ids"])
            assert all(cs.get_command(connection, identity)["verification_status"] not in {"EXECUTED", "VERIFIED", "ELECTRICAL_VERIFIED", "THERMAL_VERIFIED"}
                       for identity in context["command_ids"])
            assert all(row["claim"]["origin"] == "SOFTWARE_SIMULATION" for row in connection.execute(select(physical_assessments)).mappings())
        created = utcnow()
        first = tmp_path / "final-package"
        result = create_final_package(context["destination"], record, destination=first, created_at=created, backend_commit="b" * 40)
        restore = restore_backup(archive, target, pg_restore=os.environ["COLDGUARD_TEST_PG_RESTORE"])
        assert restore["match"] and restore["restored"] == receipt["source_fingerprints"]
        with restored_engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            copy = get_freeze(connection, record["freeze_id"])
            reexport = build_campaign_export(connection, record["campaign_id"], created_at=context["freeze_draft"].created_at, backend_commit="a" * 40)
        assert copy["manifest_sha256"] == record["manifest_sha256"] and copy["export_bytes"] == record["export_bytes"] == reexport
        verify_frozen_package(context["destination"], expected_manifest_sha256=copy["manifest_sha256"])
        second = tmp_path / "restored-final-package"
        assert create_final_package(context["destination"], copy, destination=second, created_at=created, backend_commit="b" * 40) == result
        verify_final_package(second, expected_manifest_sha256=result["manifest_sha256"])
        assert {path.relative_to(first).as_posix(): path.read_bytes() for path in first.rglob("*") if path.is_file()} == {
            path.relative_to(second).as_posix(): path.read_bytes() for path in second.rglob("*") if path.is_file()}
        claims = json.loads((first / "claim-index.json").read_bytes())["claims"]
        assert {"POLICY_APPROVAL_RECORD_PRESENT", "ASSESSMENT_RECORD_PRESENT", "DEVICE_ACCEPTANCE_ACK_RECORDED"} <= {row["status"] for row in claims}
        assert all(row["physical_acceptance"] == "BLOCKED_EXTERNAL" for row in claims)
        before = receipt["source_fingerprints"]
        with pytest.raises(ValueError, match="fresh empty"):
            populated_context(engine, tmp_path / "must-not-seed", backend_commit="a" * 40)
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            assert fingerprint_connection(connection) == before
        assert not (tmp_path / "must-not-seed").exists()
    finally:
        engine.dispose()
        restored_engine.dispose()


def test_handover_index_points_to_existing_local_contract_owners():
    root = Path(__file__).resolve().parents[2]
    document = root / "backend/HANDOVER.md"
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text())
    assert links
    for link in links:
        destination = (document.parent / link.split("#", 1)[0]).resolve()
        assert destination.is_relative_to(root.resolve()) and destination.exists(), link
    operations = (root / "README.md").read_text().split("## Member C operations", 1)[1].split("## Historical foundation", 1)[0]
    assert "(backend/HANDOVER.md)" in operations
