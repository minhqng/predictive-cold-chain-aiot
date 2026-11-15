"""W20 deterministic freeze, refusal, rollback and actual frozen-package restore."""

import hashlib
import json
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import DBAPIError

from coldguard_backend.campaign_export import build_campaign_export
from coldguard_backend.campaign_freeze import FreezeDraft, campaign_freezes, freeze_campaign, verify_frozen_package, verify_frozen_restore
from coldguard_backend.campaign_integrity import close_run
from coldguard_backend.experiment_store import experiments
from coldguard_backend import command_store
from coldguard_backend.normalized_store import telemetry
from tests.campaign_testkit import campaign_draft, complete_run, register_fixture, send_sample, snapshot_transaction
from tests.freeze_testkit import freeze_context
from tests.test_command_migration import ENV, _downgrade, _revision, _upgrade
from tests.command_testkit import make_command


def freeze(context):
    return freeze_campaign(context["engine"], context["freeze_draft"], artifact_root=context["artifact_root"],
                           backup_directory=context["backup"], destination=context["destination"])


def test_deterministic_export_and_exact_a_b_trace_reconstruction(db_engine, tmp_path):
    context = freeze_context(db_engine, tmp_path)
    draft = context["freeze_draft"]
    with db_engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        first = build_campaign_export(connection, draft.campaign_id, created_at=draft.created_at, backend_commit=draft.backend_commit)
        assert first == build_campaign_export(connection, draft.campaign_id, created_at=draft.created_at, backend_commit=draft.backend_commit)
    bundle = json.loads(first)
    assert bundle["manifest"]["data_class"] == "SOFTWARE_SIMULATION"
    assert bundle["manifest"]["run_ids"] == sorted(plan["run"]["run_id"] for plan in context["draft"]["runs"])
    assert len(bundle["manifest"]["pair_ids"]) == 1
    traces = bundle["dataset"]["traces"]
    assert {trace["controller_id"] for trace in traces} == {"REACTIVE", "PREDICTIVE"}
    assert all(len(trace["timeline"]) == 6 for trace in traces)
    assert all([row["backend_at"] for row in trace["timeline"]] == sorted(row["backend_at"] for row in trace["timeline"]) for trace in traces)


def test_physical_freeze_cannot_relabel_synthetic_measurements(db_engine):
    from tests.command_testkit import utcnow
    draft = campaign_draft()
    draft["data_class"] = "PHYSICAL"
    context = register_fixture(db_engine, draft)
    for arm in ("A", "B"):
        run = complete_run(context, arm)
        with snapshot_transaction(db_engine) as connection:
            close_run(connection, draft["campaign_id"], run["run_id"], reason="negative SOFTWARE_SIMULATION relabel test; no physical proof")
    with db_engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with pytest.raises(ValueError, match="clear integrity|cannot freeze synthetic"):
            build_campaign_export(connection, draft["campaign_id"], created_at=utcnow(), backend_commit="a" * 40)


def test_freeze_is_immutable_idempotent_and_manifests_match(db_engine, tmp_path):
    context = freeze_context(db_engine, tmp_path)
    record = freeze(context)
    assert freeze(context) == record
    manifest = verify_frozen_package(context["destination"], expected_manifest_sha256=record["manifest_sha256"])
    assert manifest["dataset_id"] == record["dataset_id"]
    assert manifest["data_class"] == "SOFTWARE_SIMULATION" and manifest["physical_acceptance"] == "BLOCKED_EXTERNAL"
    assert manifest["schema_revision"] == "0014"
    assert {"backup/database.dump", "backup/receipt.json", "campaign-export.json"} <= manifest["files"].keys()
    assert hashlib.sha256(record["export_bytes"]).hexdigest() == record["export_sha256"]
    with pytest.raises(DBAPIError, match="immutable"):
        with db_engine.begin() as connection:
            connection.execute(campaign_freezes.update().where(campaign_freezes.c.freeze_id == record["freeze_id"]).values(dataset_id="silently-mutated"))


@pytest.mark.parametrize("defect", ["missing_run_evidence", "invalid_run", "metadata_version", "missing_artifact", "corrupt_artifact", "changed_source_after_backup"])
def test_incomplete_or_conflicting_freeze_refused_with_no_record(db_engine, tmp_path, defect):
    context = freeze_context(db_engine, tmp_path)
    run = context["draft"]["runs"][1]["run"]
    if defect == "missing_run_evidence":
        with db_engine.begin() as connection:
            connection.execute(telemetry.delete().where(telemetry.c.run_id == run["run_id"]))
    elif defect == "invalid_run":
        with db_engine.begin() as connection:
            connection.execute(experiments.update().where(experiments.c.run_id == run["run_id"]).values(status="INVALID"))
    elif defect == "metadata_version":
        path = context["artifact_root"] / "model-metadata.json"
        metadata = json.loads(path.read_bytes())
        metadata["models"][0]["model_version"] = "conflicting-model"
        content = json.dumps(metadata).encode()
        path.write_bytes(content)
        context["freeze_draft"] = context["freeze_draft"].model_copy(update={"artifacts": [
            item.model_copy(update={"sha256": hashlib.sha256(content).hexdigest()}) if item.kind == "model_metadata" else item
            for item in context["freeze_draft"].artifacts]})
    elif defect == "missing_artifact":
        (context["artifact_root"] / "broker.conf").unlink()
    elif defect == "corrupt_artifact":
        (context["artifact_root"] / "model-reference.bin").write_bytes(b"changed")
    else:
        send_sample(context, run, 1)
        with snapshot_transaction(db_engine) as connection:
            close_run(connection, context["draft"]["campaign_id"], run["run_id"], reason="explicit receipt after backup")
    with pytest.raises((ValueError, FileNotFoundError)):
        freeze(context)
    assert not context["destination"].exists()
    with db_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(campaign_freezes).where(campaign_freezes.c.freeze_id == context["freeze_draft"].freeze_id)) == 0


def test_corrupt_frozen_artifact_and_conflicting_repeat_refused(db_engine, tmp_path):
    context = freeze_context(db_engine, tmp_path)
    record = freeze(context)
    context["freeze_draft"] = context["freeze_draft"].model_copy(update={"backend_commit": "b" * 40})
    with pytest.raises(ValueError, match="different immutable inputs"):
        freeze(context)
    artifact = context["destination"] / "campaign-export.json"
    artifact.write_bytes(artifact.read_bytes() + b" ")
    with pytest.raises(ValueError, match="checksum differs"):
        verify_frozen_package(context["destination"], expected_manifest_sha256=record["manifest_sha256"])


def test_freeze_partial_write_rolls_back_database_and_preserves_failed_staging(db_engine, tmp_path, monkeypatch):
    context = freeze_context(db_engine, tmp_path)
    from coldguard_backend import campaign_freeze as module
    original = module._write_artifact
    calls = 0
    def interrupted(path, content):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("simulated partial write")
        original(path, content)
    monkeypatch.setattr(module, "_write_artifact", interrupted)
    with pytest.raises(OSError, match="partial write"):
        freeze(context)
    assert not context["destination"].exists()
    assert list(tmp_path.glob(".freeze-staging-*"))
    with db_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(campaign_freezes).where(campaign_freezes.c.freeze_id == context["freeze_draft"].freeze_id)) == 0


def test_freeze_commit_failure_removes_ready_name_and_rolls_back_record(db_engine, tmp_path):
    context = freeze_context(db_engine, tmp_path)
    def reject_commit(_connection):
        raise RuntimeError("injected database commit failure")
    event.listen(db_engine, "commit", reject_commit)
    try:
        with pytest.raises(RuntimeError, match="commit failure"):
            freeze(context)
    finally:
        event.remove(db_engine, "commit", reject_commit)
    assert not context["destination"].exists()
    with db_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(campaign_freezes).where(campaign_freezes.c.freeze_id == context["freeze_draft"].freeze_id)) == 0


def test_export_refuses_command_with_missing_prediction_provenance(db_engine, tmp_path):
    context = freeze_context(db_engine, tmp_path)
    run = context["draft"]["runs"][1]["run"]
    with db_engine.begin() as connection:
        command_store.create_command(connection, make_command("missing-prediction-" + uuid4().hex,
            device_id=run["device_id"], run_id=run["run_id"], controller_id=run["controller_id"],
            policy_version=run["versions"]["policy_version"], prediction_id="absent-prediction"))
    with db_engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        draft = context["freeze_draft"]
        with pytest.raises(ValueError, match="prediction provenance is unavailable"):
            build_campaign_export(connection, draft.campaign_id, created_at=draft.created_at, backend_commit=draft.backend_commit)


@pytest.mark.skipif(not os.environ.get("COLDGUARD_TEST_FROZEN_RESTORE_URL"), reason="requires separate clean disposable frozen-package restore DB")
def test_restore_frozen_package_and_repeat_export(db_engine, tmp_path):
    context = freeze_context(db_engine, tmp_path)
    record = freeze(context)
    report = verify_frozen_restore(context["destination"], record, os.environ["COLDGUARD_TEST_FROZEN_RESTORE_URL"], pg_restore=os.environ["COLDGUARD_TEST_PG_RESTORE"])
    assert report["match"] is True and report["export_match"] is True
    assert report["restored"]["revisions"] == ["0014"] and len(report["restored"]["tables"]) == 22
    assert report["export_sha256"] == record["export_sha256"]


@pytest.mark.skipif(not os.environ.get("COLDGUARD_TEST_FREEZE_MIGRATION_URL"), reason="requires separate freeze migration DB")
def test_0014_migrates_before_freeze_and_refuses_populated_downgrade(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, os.environ["COLDGUARD_TEST_FREEZE_MIGRATION_URL"])
    engine = create_engine(os.environ[ENV])
    try:
        _upgrade("0013")
        _upgrade("0014")
        _downgrade("0013")
        _upgrade("0014")
        context = freeze_context(engine, tmp_path)
        freeze(context)
        with pytest.raises(DBAPIError, match="0014 downgrade refused"):
            _downgrade("0013")
        assert _revision(engine) == "0014"
    finally:
        engine.dispose()
