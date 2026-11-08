"""Independent W19 review counterexamples on generated, disposable evidence only."""

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from coldguard_backend.campaign_integrity import assess_run, campaign_integrity, close_run, live_integrity
from coldguard_backend.evidence_backup import backup_campaign, restore_backup
from coldguard_backend.experiment_store import RunTransition, transition_run
from coldguard_backend.ingest import ingest_message
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.raw_store import telemetry_raw
from coldguard_backend.simulator import build_event
from tests.campaign_testkit import campaign_draft, complete_run, register_fixture, send_sample, snapshot_transaction
from tests.test_campaign_backup import ready_campaign


@pytest.mark.parametrize("field", ["raw_payload", "payload_sha256", "projection_device", "projection_boot", "projection_seq"])
def test_corrupt_raw_authority_is_reported_without_silent_repair(db_engine, field):
    context = register_fixture(db_engine)
    run = complete_run(context)
    with db_engine.begin() as connection:
        sample = dict(connection.execute(select(telemetry).where(telemetry.c.run_id == run["run_id"]).order_by(telemetry.c.id)).mappings().first())
        source = dict(connection.execute(select(telemetry_raw).where(telemetry_raw.c.id == sample["raw_id"])).mappings().one())
        values = {"raw_payload": source["raw_payload"] + " "} if field == "raw_payload" else {"payload_sha256": "0" * 64} if field == "payload_sha256" else {
            "raw_json": source["raw_json"] | { {"projection_device": "device_id", "projection_boot": "boot_id", "projection_seq": "seq"}[field]: 999 if field == "projection_seq" else "conflicting-identity"}
        }
        connection.execute(telemetry_raw.update().where(telemetry_raw.c.id == sample["raw_id"]).values(**values))
    with snapshot_transaction(db_engine) as connection:
        before_raw = dict(connection.execute(select(telemetry_raw).where(telemetry_raw.c.id == sample["raw_id"])).mappings().one())
        report = close_run(connection, context["draft"]["campaign_id"], run["run_id"], reason="SOFTWARE_SIMULATION corrupted source audit")["report"]
        assert report["assessment"] != "SOFTWARE_INTEGRITY_CLEAR"
        assert "RAW_PROVENANCE_INCONSISTENT" in {issue["code"] for issue in report["issues"]}
        assert dict(connection.execute(select(telemetry_raw).where(telemetry_raw.c.id == sample["raw_id"])).mappings().one()) == before_raw
        assert dict(connection.execute(select(telemetry).where(telemetry.c.id == sample["id"])).mappings().one()) == sample


def test_close_refuses_read_committed_multi_snapshot_input(db_engine):
    context = ready_campaign(db_engine)
    run = context["draft"]["runs"][0]["run"]
    with pytest.raises(ValueError, match="REPEATABLE READ"):
        with db_engine.begin() as connection:
            close_run(connection, context["draft"]["campaign_id"], run["run_id"], reason="unsafe multi-snapshot close")


def test_snapshot_close_excludes_late_duplicate_consistently(db_engine, monkeypatch):
    context = register_fixture(db_engine)
    run = complete_run(context)
    from coldguard_backend import campaign_integrity as module
    original = module._raw_evidence
    injected = False
    def after_materialization(connection, target):
        nonlocal injected
        rows = original(connection, target)
        if not injected:
            injected = True
            send_sample(context, run, 1)
        return rows
    monkeypatch.setattr(module, "_raw_evidence", after_materialization)
    with snapshot_transaction(db_engine) as connection:
        report = close_run(connection, context["draft"]["campaign_id"], run["run_id"], reason="deterministic snapshot barrier")["report"]
        extra = sum(row["raw_deliveries"] - 1 for row in report["integrity"]["duplicate_identities"])
        assert report["raw_count"] == report["normalized_count"] + sum(report["event_counts"].values()) + extra
        assert report["raw_count"] == 6 and not report["integrity"]["duplicate_identities"]


def test_cross_arm_event_identity_conflict_and_exact_repeat_control(db_engine):
    context = register_fixture(db_engine)
    a, b = complete_run(context, "A"), complete_run(context, "B")
    with db_engine.connect() as connection:
        first = dict(connection.execute(select(telemetry_raw).where(
            telemetry_raw.c.run_id == a["run_id"], telemetry_raw.c.topic.endswith("/event"),
        ).order_by(telemetry_raw.c.id)).mappings().first())
    ingest_message(db_engine, topic=first["topic"], payload=first["raw_payload"].encode(), received_at=first["backend_received_at"])
    with db_engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        assert not assess_run(connection, context["campaign"], a["run_id"])["issues"]
    event = build_event(device_id=b["device_id"], boot_id="software-boot-" + b["run_id"], seq=2,
                        run_id=b["run_id"], event_type="DOOR_OPENED", base_time=context["started"])
    event["event_id"] = first["raw_json"]["event_id"]
    ingest_message(db_engine, topic=f"coldguard/{b['device_id']}/event", payload=json.dumps(event).encode(), received_at=first["backend_received_at"])
    with db_engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        for run in (a, b):
            assert "EVENT_ID_CONFLICT" in {issue["code"] for issue in assess_run(connection, context["campaign"], run["run_id"])["issues"]}


def test_observed_unknown_schema_remains_raw_and_is_reported_as_error(db_engine):
    context = register_fixture(db_engine)
    run = complete_run(context)
    event = build_event(device_id=run["device_id"], boot_id="software-boot-" + run["run_id"], seq=20,
                        run_id=run["run_id"], event_type="EXTRA_SCHEMA_TEST", base_time=context["started"])
    event["schema_version"] = 99
    result = ingest_message(db_engine, topic=f"coldguard/{run['device_id']}/event", payload=json.dumps(event).encode())
    assert result["raw_status"] == "RECEIVED_OBSERVED"
    report = live_integrity(db_engine, context["draft"]["campaign_id"])
    assessment = next(row for row in report["runs"] if row["run_id"] == run["run_id"])
    assert assessment["schema_mismatches"] == 1 and assessment["message_errors"] == 1
    assert "SCHEMA_MISMATCH" in {issue["code"] for issue in assessment["issues"]}
    with db_engine.connect() as connection:
        assert connection.scalar(select(telemetry_raw.c.id).where(telemetry_raw.c.id == result["raw_id"])) == result["raw_id"]


@pytest.mark.skipif(not os.environ.get("COLDGUARD_TEST_ISSUE_RESTORE_URL"), reason="requires clean separate issue-preserving restore DB")
def test_invalid_and_aborted_block_archives_without_repair(db_engine, tmp_path):
    context = register_fixture(db_engine)
    a = complete_run(context, "A", sequences=(1, 4), events=False, final_status="INVALID")
    b = context["draft"]["runs"][1]["run"]
    with db_engine.begin() as connection:
        transition_run(connection, b["run_id"], RunTransition(status="ABORTED", reason="SOFTWARE_SIMULATION abort before acquisition"))
    with snapshot_transaction(db_engine) as connection:
        for run in (a, b):
            close_run(connection, context["draft"]["campaign_id"], run["run_id"], reason="preserve failed attempt without repairing data")
        integrity = campaign_integrity(connection, context["draft"]["campaign_id"])
        assert integrity["backup_ready"] is True and integrity["freeze_ready"] is False
    directory = tmp_path / "failed-attempt-block"
    receipt = backup_campaign(db_engine, context["draft"]["campaign_id"], directory, pg_dump=os.environ["COLDGUARD_TEST_PG_DUMP"])
    assert receipt["integrity_clear"] is False
    assert receipt["run_status_counts"] == {"INVALID": 1, "ABORTED": 1}
    restored = restore_backup(directory, os.environ["COLDGUARD_TEST_ISSUE_RESTORE_URL"], pg_restore=os.environ["COLDGUARD_TEST_PG_RESTORE"])
    assert restored["match"] is True and restored["physical_acceptance"] == "BLOCKED_EXTERNAL"


@pytest.mark.skipif(not os.environ.get("COLDGUARD_TEST_RECEIPT_RESTORE_URL"), reason="requires clean separate receipt-verification restore DB")
def test_receipt_provenance_header_cannot_relabel_restored_campaign(db_engine, tmp_path):
    context = ready_campaign(db_engine)
    directory = tmp_path / "receipt-test"
    backup_campaign(db_engine, context["draft"]["campaign_id"], directory, pg_dump=os.environ["COLDGUARD_TEST_PG_DUMP"])
    path = directory / "receipt.json"
    receipt = json.loads(path.read_bytes())
    receipt["data_class"] = "PHYSICAL"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="receipt.*campaign"):
        restore_backup(directory, os.environ["COLDGUARD_TEST_RECEIPT_RESTORE_URL"], pg_restore=os.environ["COLDGUARD_TEST_PG_RESTORE"])


def test_known_generated_origin_cannot_be_hidden_by_physical_declaration(db_engine):
    draft = campaign_draft()
    draft["data_class"] = "PHYSICAL"
    context = register_fixture(db_engine, draft)
    run = complete_run(context)
    with db_engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        report = assess_run(connection, context["campaign"], run["run_id"])
    assert report["known_generated_input"] is True
    assert "SYNTHETIC_IN_PHYSICAL_CAMPAIGN" in {issue["code"] for issue in report["issues"]}
    assert report["physical_acceptance"] == "BLOCKED_EXTERNAL"


def test_destructive_fixture_refuses_same_database_through_localhost_alias(monkeypatch):
    from tests.conftest import isolate_destructive_legacy_migrations
    monkeypatch.setenv("COLDGUARD_TEST_DATABASE_URL", "postgresql+psycopg://fixture@localhost:5432/fixture_only")
    monkeypatch.setenv("COLDGUARD_TEST_LEGACY_MIGRATION_DB_URL", "postgresql+psycopg://fixture@127.0.0.1:5432/fixture_only")
    calls = []
    fake_patch = SimpleNamespace(setenv=lambda *args: calls.append(args))
    request = SimpleNamespace(node=SimpleNamespace(path=Path("test_migration_w02.py"), originalname="test_upgrade_from_empty_reaches_head_with_expected_schema"))
    with pytest.raises(ValueError, match="separate direct loopback"):
        isolate_destructive_legacy_migrations.__wrapped__(request, fake_patch)
    assert calls == []


def test_destructive_fixture_allows_distinct_canonical_databases_and_ignores_other_tests(monkeypatch):
    from tests.conftest import isolate_destructive_legacy_migrations
    monkeypatch.setenv("COLDGUARD_TEST_DATABASE_URL", "postgresql+psycopg://fixture@127.0.0.1:5432/suite_only")
    monkeypatch.setenv("COLDGUARD_TEST_LEGACY_MIGRATION_DB_URL", "postgresql+psycopg://fixture@127.0.0.1:5432/migration_only")
    calls = []
    patch = SimpleNamespace(setenv=lambda *args: calls.append(args))
    node = SimpleNamespace(path=Path("test_migration_w02.py"), originalname="test_upgrade_from_empty_reaches_head_with_expected_schema")
    isolate_destructive_legacy_migrations.__wrapped__(SimpleNamespace(node=node), patch)
    assert calls == [("COLDGUARD_TEST_DATABASE_URL", os.environ["COLDGUARD_TEST_LEGACY_MIGRATION_DB_URL"])]
    calls.clear()
    node.path = Path("test_campaign_integrity.py")
    isolate_destructive_legacy_migrations.__wrapped__(SimpleNamespace(node=node), patch)
    assert calls == []


def test_operator_close_cli_uses_a_repeatable_write_snapshot(db_engine, tmp_path, monkeypatch):
    from scripts import campaign as cli
    context = register_fixture(db_engine)
    run = complete_run(context)
    observed = []
    original = cli.close_run
    def inspected(connection, *args, **kwargs):
        observed.append(connection.get_isolation_level())
        return original(connection, *args, **kwargs)
    monkeypatch.setattr(cli, "close_run", inspected)
    monkeypatch.setenv("DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    target = tmp_path / "operator-close.json"
    monkeypatch.setattr("sys.argv", ["campaign.py", "--output", str(target), "close", "--campaign", context["draft"]["campaign_id"],
                                    "--run", run["run_id"], "--reason", "SOFTWARE_SIMULATION explicit operator close"])
    assert cli.main() == 0 and observed == ["REPEATABLE READ"]
    assert json.loads(target.read_bytes())["report"]["normalized_count"] == 4
