"""W20 independent-review regressions with real disposable DB/filesystem boundaries."""

import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import subprocess
import threading

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from coldguard_backend.campaign_freeze import FreezeDraft, campaign_freezes, freeze_campaign, get_freeze, verify_frozen_package
from coldguard_backend.campaign_integrity import close_run
from coldguard_backend.evidence_backup import backup_campaign, restore_backup, verify_backup
from coldguard_backend.raw_store import telemetry_raw
from tests.campaign_testkit import send_sample, snapshot_transaction
from tests.freeze_testkit import freeze_context
from tests.test_campaign_freeze import freeze


def test_json_spec_cli_preserves_strict_aware_datetime_validation(db_engine, tmp_path, monkeypatch):
    from scripts import freeze_campaign as cli
    context = freeze_context(db_engine, tmp_path)
    spec = tmp_path / "freeze-spec.json"
    spec.write_text(context["freeze_draft"].model_dump_json())
    monkeypatch.setenv("DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    # Source provenance is isolated for this JSON-boundary test; a separate actual clean-Git CLI drill is required.
    monkeypatch.setattr(cli, "clean_backend_commit", lambda _root: "a" * 40)
    monkeypatch.setattr("sys.argv", ["freeze_campaign.py", "freeze", "--spec", str(spec), "--artifact-root", str(context["artifact_root"]),
        "--backup", str(context["backup"]), "--directory", str(context["destination"]), "--report", str(tmp_path / "cli-report.json")])
    assert cli.main() == 0
    assert context["destination"].is_dir()


@pytest.mark.parametrize("defect", ["event_digest", "duplicate_digest", "synthetic_projection"])
def test_all_raw_evidence_is_validated_after_fresh_close_and_backup(db_engine, tmp_path, defect):
    context = freeze_context(db_engine, tmp_path)
    run = context["draft"]["runs"][0]["run"]
    with db_engine.begin() as connection:
        if defect == "event_digest":
            row = dict(connection.execute(select(telemetry_raw).where(telemetry_raw.c.run_id == run["run_id"],
                telemetry_raw.c.topic.endswith("/event")).order_by(telemetry_raw.c.id)).mappings().first())
        elif defect == "synthetic_projection":
            row = dict(connection.execute(select(telemetry_raw).where(telemetry_raw.c.run_id == run["run_id"],
                telemetry_raw.c.topic.endswith("/telemetry")).order_by(telemetry_raw.c.id)).mappings().first())
        else:
            row = None
    if defect == "duplicate_digest":
        _, result = send_sample(context, run, 1)
        with db_engine.connect() as connection:
            row = dict(connection.execute(select(telemetry_raw).where(telemetry_raw.c.id == result["raw_id"])).mappings().one())
    values = {"raw_json": row["raw_json"] | {"synthetic": False}} if defect == "synthetic_projection" else {"payload_sha256": "0" * 64}
    with db_engine.begin() as connection:
        connection.execute(telemetry_raw.update().where(telemetry_raw.c.id == row["id"]).values(**values))
    with snapshot_transaction(db_engine) as connection:
        close_run(connection, context["draft"]["campaign_id"], run["run_id"], reason="explicit corrupted-source re-close, no repair")
    fresh = tmp_path / "corrupted-source-backup"
    backup_campaign(db_engine, context["draft"]["campaign_id"], fresh, pg_dump=os.environ["COLDGUARD_TEST_PG_DUMP"])
    context["backup"] = fresh
    with pytest.raises(ValueError):
        freeze(context)
    assert not context["destination"].exists()
    with db_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(campaign_freezes).where(campaign_freezes.c.freeze_id == context["freeze_draft"].freeze_id)) == 0
        source = dict(connection.execute(select(telemetry_raw).where(telemetry_raw.c.id == row["id"])).mappings().one())
        assert all(source[key] == value for key, value in values.items())


@pytest.mark.parametrize("changed_file", ["database.dump", "receipt.json"])
def test_freeze_packages_only_the_exact_backup_bytes_it_verified(db_engine, tmp_path, monkeypatch, changed_file):
    context = freeze_context(db_engine, tmp_path)
    original = Path.read_bytes
    mutated = False
    def raced(path):
        nonlocal mutated
        content = original(path)
        if path == context["backup"] / "database.dump" and not mutated:
            mutated = True
            target = context["backup"] / changed_file
            if changed_file == "database.dump":
                target.write_bytes(content + b"changed-after-read")
            else:
                receipt = json.loads(original(target))
                receipt["archive_sha256"] = "0" * 64
                target.write_text(json.dumps(receipt))
        return content
    monkeypatch.setattr(Path, "read_bytes", raced)
    record = freeze(context)
    assert mutated
    verify_frozen_package(context["destination"], expected_manifest_sha256=record["manifest_sha256"])
    # Changing the input after its snapshot is safe only if the retained verified bytes were packaged.
    verify_backup(context["destination"] / "backup")


def test_verify_cli_refuses_report_inside_immutable_package_without_mutation(db_engine, tmp_path, monkeypatch):
    from scripts import freeze_campaign as cli
    context = freeze_context(db_engine, tmp_path)
    record = freeze(context)
    before = {path.relative_to(context["destination"]).as_posix(): path.read_bytes() for path in context["destination"].rglob("*") if path.is_file()}
    monkeypatch.setenv("DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr("sys.argv", ["freeze_campaign.py", "verify", "--directory", str(context["destination"]),
        "--freeze-id", record["freeze_id"], "--report", str(context["destination"] / "verify-report.json")])
    with pytest.raises((SystemExit, ValueError)):
        cli.main()
    assert {path.relative_to(context["destination"]).as_posix(): path.read_bytes() for path in context["destination"].rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("stamp", ["2026-11-07T00:00:00", "not-a-timestamp"])
def test_json_freeze_spec_rejects_naive_or_malformed_timestamp(stamp):
    kinds = ("model_metadata", "policy_metadata", "broker_config", "backend_config")
    payload = {"freeze_id": "strict-json", "campaign_id": "software-test", "created_at": stamp, "backend_commit": "a" * 40,
               "artifacts": [{"name": kind + ".json", "kind": kind, "sha256": "a" * 64} for kind in kinds]}
    with pytest.raises(ValueError):
        FreezeDraft.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("defect", ["manifest", "missing", "extra"])
def test_trusted_anchor_refuses_manifest_or_membership_tampering(db_engine, tmp_path, defect):
    context = freeze_context(db_engine, tmp_path)
    record = freeze(context)
    directory = context["destination"]
    if defect == "manifest":
        path = directory / "manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif defect == "missing":
        (directory / "artifacts/model-reference.bin").unlink()
    else:
        (directory / "unmanifested.txt").write_text("not frozen evidence")
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_frozen_package(directory, expected_manifest_sha256=record["manifest_sha256"])


def test_report_alias_into_package_is_refused(db_engine, tmp_path, monkeypatch):
    from scripts import freeze_campaign as cli
    context = freeze_context(db_engine, tmp_path)
    record = freeze(context)
    alias = tmp_path / "package-alias"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(context["destination"])], check=True, capture_output=True)
    else:
        alias.symlink_to(context["destination"], target_is_directory=True)
    monkeypatch.setattr("sys.argv", ["freeze_campaign.py", "verify", "--directory", str(context["destination"]),
        "--freeze-id", record["freeze_id"], "--report", str(alias / "verification.json")])
    with pytest.raises(SystemExit):
        cli.main()
    assert not (context["destination"] / "verification.json").exists()
    verify_frozen_package(context["destination"], expected_manifest_sha256=record["manifest_sha256"])


@pytest.mark.parametrize("case", ["same_id", "cross_campaign_id", "competing_destination"])
def test_bounded_concurrent_freezes_have_one_committed_owner(db_engine, tmp_path, case):
    first = freeze_context(db_engine, tmp_path / "first")
    second = first.copy()
    if case == "cross_campaign_id":
        second = freeze_context(db_engine, tmp_path / "second")
        second["freeze_draft"] = second["freeze_draft"].model_copy(update={"freeze_id": first["freeze_draft"].freeze_id})
        # Both inputs must see the complete unchanged DB inventory before racing.
        for index, context in enumerate((first, second)):
            context["backup"] = tmp_path / ("race-backup-" + str(index))
            backup_campaign(db_engine, context["draft"]["campaign_id"], context["backup"], pg_dump=os.environ["COLDGUARD_TEST_PG_DUMP"])
    elif case == "competing_destination":
        second["freeze_draft"] = second["freeze_draft"].model_copy(update={"freeze_id": first["freeze_draft"].freeze_id + "-second"})
    barrier = threading.Barrier(2)
    def attempt(context):
        barrier.wait(timeout=10)
        try:
            return context["destination"], freeze(context)
        except (ValueError, OSError, DBAPIError):
            return context["destination"], None
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(attempt, (first, second)))
    winners = [(path, row) for path, row in results if row is not None]
    assert winners
    ids = {first["freeze_draft"].freeze_id, second["freeze_draft"].freeze_id}
    with db_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(campaign_freezes).where(campaign_freezes.c.freeze_id.in_(ids))) == 1
    for path, record in winners:
        verify_frozen_package(path, expected_manifest_sha256=record["manifest_sha256"])


@pytest.mark.skipif(not os.environ.get("COLDGUARD_TEST_FROZEN_RECORD_RESTORE_URL"), reason="requires separate clean post-freeze record restore DB")
def test_later_backup_restores_freeze_record_and_original_manifest_anchor(db_engine, tmp_path):
    from sqlalchemy import create_engine
    from coldguard_backend.campaign_export import build_campaign_export
    context = freeze_context(db_engine, tmp_path)
    record = freeze(context)
    archive = tmp_path / "post-freeze-backup"
    receipt = backup_campaign(db_engine, context["draft"]["campaign_id"], archive, pg_dump=os.environ["COLDGUARD_TEST_PG_DUMP"])
    assert receipt["source_fingerprints"]["tables"]["campaign_freezes"]["rows"] >= 1
    restored = restore_backup(archive, os.environ["COLDGUARD_TEST_FROZEN_RECORD_RESTORE_URL"], pg_restore=os.environ["COLDGUARD_TEST_PG_RESTORE"])
    assert restored["match"] is True
    engine = create_engine(os.environ["COLDGUARD_TEST_FROZEN_RECORD_RESTORE_URL"])
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            copy = get_freeze(connection, record["freeze_id"])
            assert copy["export_bytes"] == record["export_bytes"] and copy["manifest_sha256"] == record["manifest_sha256"]
            verify_frozen_package(context["destination"], expected_manifest_sha256=copy["manifest_sha256"])
            draft = context["freeze_draft"]
            content = build_campaign_export(connection, draft.campaign_id, created_at=draft.created_at, backend_commit=draft.backend_commit)
            assert hashlib.sha256(content).hexdigest() == copy["export_sha256"]
    finally:
        engine.dispose()


def _replace_package_pair_after_anchored_reads(context, monkeypatch, replacement):
    directory = context["destination"]
    original = Path.read_bytes
    receipt_bytes = original(directory / "backup/receipt.json")
    archive_bytes = original(directory / "backup/database.dump")
    counts, changed = {}, []
    def raced(path):
        content = original(path)
        if directory in path.parents:
            name = path.relative_to(directory).as_posix()
            counts[name] = counts.get(name, 0) + 1
            if name == "campaign-export.json" and not changed:
                assert counts.get("backup/receipt.json") == 1 and counts.get("backup/database.dump") == 1
                receipt = json.loads(receipt_bytes)
                receipt.pop("run_issues", None)  # Standalone omit-only legacy compatibility must not be removed.
                receipt["replacement_note"] = "SOFTWARE_SIMULATION after anchor reads"
                if replacement == "archive_pair":
                    different_archive = archive_bytes + b"SOFTWARE_SIMULATION internally consistent replacement pair"
                    (directory / "backup/database.dump").write_bytes(different_archive)
                    receipt["archive_sha256"] = hashlib.sha256(different_archive).hexdigest()
                (directory / "backup/receipt.json").write_text(json.dumps(receipt))
                changed.append(True)
        return content
    monkeypatch.setattr(Path, "read_bytes", raced)
    return archive_bytes, counts, changed


@pytest.mark.parametrize("replacement", ["receipt", "archive_pair"])
def test_package_verification_uses_only_its_anchor_checked_byte_snapshot(db_engine, tmp_path, monkeypatch, replacement):
    context = freeze_context(db_engine, tmp_path)
    record = freeze(context)
    _, counts, changed = _replace_package_pair_after_anchored_reads(context, monkeypatch, replacement)
    verify_frozen_package(context["destination"], expected_manifest_sha256=record["manifest_sha256"])
    assert changed and counts["backup/receipt.json"] == counts["backup/database.dump"] == counts["campaign-export.json"] == 1
    # The raced on-disk pair is internally consistent, but it is not the immutable anchored pair.
    verify_backup(context["destination"] / "backup")
    with pytest.raises(ValueError, match="checksum"):
        verify_frozen_package(context["destination"], expected_manifest_sha256=record["manifest_sha256"])


@pytest.mark.parametrize("replacement,environment", [
    ("receipt", "COLDGUARD_TEST_ANCHORED_RECEIPT_RESTORE_URL"),
    ("archive_pair", "COLDGUARD_TEST_ANCHORED_ARCHIVE_RESTORE_URL"),
])
def test_actual_frozen_restore_consumes_the_original_anchor_checked_pair(db_engine, tmp_path, monkeypatch, replacement, environment):
    from coldguard_backend import evidence_backup as backup_module
    from coldguard_backend.campaign_freeze import verify_frozen_restore
    if not os.environ.get(environment):
        pytest.skip("requires its own empty anchored-byte restore DB")
    context = freeze_context(db_engine, tmp_path)
    record = freeze(context)
    archive_bytes, counts, changed = _replace_package_pair_after_anchored_reads(context, monkeypatch, replacement)
    original = backup_module._postgres_command
    consumed = []
    def inspected(executable, url, *arguments):
        content = Path(arguments[-1]).read_bytes()
        assert content == archive_bytes, "restore consumed replacement bytes outside the immutable anchor"
        consumed.append(hashlib.sha256(content).hexdigest())
        return original(executable, url, *arguments)
    monkeypatch.setattr(backup_module, "_postgres_command", inspected)
    report = verify_frozen_restore(context["destination"], record, os.environ[environment], pg_restore=os.environ["COLDGUARD_TEST_PG_RESTORE"])
    assert report["match"] and report["export_match"] and changed
    assert consumed == [hashlib.sha256(archive_bytes).hexdigest()]
    assert counts["backup/receipt.json"] == counts["backup/database.dump"] == counts["campaign-export.json"] == 1


@pytest.mark.parametrize("operation", ["freeze", "verify", "restore"])
def test_all_cli_operations_refuse_internal_report_before_engine_creation(tmp_path, monkeypatch, operation):
    from scripts import freeze_campaign as cli
    calls = []
    monkeypatch.setattr(cli, "create_engine", lambda *_args, **_kwargs: calls.append(True))
    directory = tmp_path / "package"
    monkeypatch.setattr("sys.argv", ["freeze_campaign.py", operation, "--directory", str(directory),
                                    "--report", str(directory / "operation.json")])
    with pytest.raises(SystemExit):
        cli.main()
    assert not calls and not directory.exists()
