"""W22 frozen-source package gates; all fixtures are SOFTWARE_SIMULATION."""

import json
from collections import Counter
from datetime import timedelta
import os
from pathlib import Path

import pytest

from coldguard_backend.campaign_export import build_campaign_export
from coldguard_backend.campaign_integrity import close_run
from coldguard_backend.evidence_package import digest
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.ingest import ingest_message
from coldguard_backend.simulator import build_event
from tests.campaign_testkit import campaign_draft, complete_run, register_fixture, snapshot_transaction
from tests.command_testkit import utcnow


def test_registered_s1_pair_can_export_complete_non_door_timelines(db_engine):
    draft = campaign_draft()
    for plan in draft["runs"]:
        plan["run"]["scenario_id"] = "S1_NORMAL_BASELINE"
        plan["required_events"] = ["SIM_RUN_START", "SIM_RUN_END"]
    context = register_fixture(db_engine, draft)
    for arm in ("A", "B"):
        run = complete_run(context, arm, events=False)
        for seq, kind in ((1, "SIM_RUN_START"), (4, "SIM_RUN_END")):
            event = build_event(device_id=run["device_id"], boot_id="software-boot-" + run["run_id"],
                                seq=seq, run_id=run["run_id"], event_type=kind, base_time=context["started"])
            ingest_message(db_engine, topic=f"coldguard/{run['device_id']}/event", payload=json.dumps(event).encode(),
                           received_at=context["started"] + timedelta(seconds=seq, milliseconds=100))
        with snapshot_transaction(db_engine) as connection:
            close_run(connection, draft["campaign_id"], run["run_id"], reason="SOFTWARE_SIMULATION baseline package audit")
    with db_engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        bundle = json.loads(build_campaign_export(connection, draft["campaign_id"], created_at=utcnow(), backend_commit="a" * 40))
    assert len(bundle["dataset"]["traces"]) == 2
    assert all(len(trace["timeline"]) == 6 for trace in bundle["dataset"]["traces"])
    assert all({row["kind"] for row in trace["timeline"]} == {"telemetry", "event_receipt"} for trace in bundle["dataset"]["traces"])


def final_context(engine, root, *, commands=False):
    from coldguard_backend import command_store as cs
    from coldguard_backend.evidence_backup import backup_campaign
    from tests.command_testkit import ack_bytes, make_ack, make_command
    from tests.freeze_testkit import freeze_context
    from tests.test_campaign_freeze import freeze
    context = freeze_context(engine, root)
    if commands:
        run = context["draft"]["runs"][0]["run"]
        command = make_command("software-final-command-" + run["run_id"], device_id=run["device_id"], run_id=run["run_id"],
                               policy_version=run["versions"]["policy_version"], cooling="OFF", duty=None)
        with engine.begin() as connection:
            cs.create_command(connection, command)
            pending = cs.begin_publish_attempt(connection, command.command_id, payload_sha256=cs.command_payload_sha256(command))
            cs.finish_publish_attempt(connection, command.command_id, pending["attempt_id"], outcome="PUBACK",
                                      broker_reason="SOFTWARE_SIMULATION protocol storage fixture; no broker publish")
            ack = make_ack(command.command_id, device_id=run["device_id"], applied={"cooling": "OFF", "duty": None})
            content = ack_bytes(ack)
            cs.record_ack(connection, topic_device_id=run["device_id"], raw_payload=content.decode(), payload_sha256=digest(content),
                          backend_received_at=utcnow(), ack=ack, validity="VALID")
        context["backup"] = root / "with-command-backup"
        backup_campaign(engine, context["draft"]["campaign_id"], context["backup"], pg_dump=os.environ["COLDGUARD_TEST_PG_DUMP"])
        context["freeze_draft"] = context["freeze_draft"].model_copy(update={"created_at": utcnow()})
    return context, freeze(context)


def rehashed(bundle):
    tables = bundle["dataset"]["tables"]
    bundle["manifest"]["table_sha256"] = {name: digest(encode_evidence(rows)) for name, rows in tables.items()}
    checksum = digest(encode_evidence(bundle["dataset"]))
    bundle["manifest"]["dataset_sha256"] = checksum
    bundle["manifest"]["dataset_id"] = "coldguard-" + bundle["manifest"]["data_class"].lower() + "-" + checksum
    return encode_evidence(bundle)


def test_frozen_audit_checks_live_equivalent_diagnostics_and_preserves_source(db_engine, tmp_path):
    from coldguard_backend.final_audit import audit_campaign_export
    context, record = final_context(db_engine, tmp_path)
    original = record["export_bytes"]
    audit = audit_campaign_export(original)
    assert audit["assessment"] == "FROZEN_INPUT_INTEGRITY_CLEAR" and audit["run_count"] == 2 and audit["pair_count"] == 1
    assert audit["invalid_run_records"] == audit["normalized_duplicate_identities"] == []
    assert audit["statistics"] == "NOT_COMPUTED" and audit["automatic_validity_approval"] is False
    assert audit["physical_acceptance"] == "BLOCKED_EXTERNAL"
    assert audit_campaign_export(original) == audit
    assert (context["destination"] / "campaign-export.json").read_bytes() == original


@pytest.mark.parametrize("defect", ["invalid_run", "pair_roster", "run_version", "duplicate_pk", "duplicate_sample_identity",
    "raw_digest", "raw_cache", "raw_metadata", "normalized_content", "source_report", "missing_current_close", "closure_digest",
    "unscoped_raw", "orphan_attempt", "orphan_prediction_input", "missing_version", "table_hash", "nonfinite"])
def test_final_audit_refuses_semantic_defects_even_with_rehashed_outer_export(db_engine, tmp_path, defect):
    from coldguard_backend.final_audit import audit_campaign_export
    _context, record = final_context(db_engine, tmp_path)
    bundle = json.loads(record["export_bytes"])
    dataset = bundle["dataset"]
    tables = dataset["tables"]
    if defect == "invalid_run":
        tables["experiments"][0]["status"] = "INVALID"
    elif defect == "pair_roster":
        dataset["pairs"][0]["runs"][0]["arm"] = "B"
    elif defect == "run_version":
        tables["experiments"][0]["versions"]["backend_version"] = "b" * 40
    elif defect == "duplicate_pk":
        tables["telemetry_raw"].append(tables["telemetry_raw"][0].copy())
    elif defect == "duplicate_sample_identity":
        tables["telemetry"].append({**tables["telemetry"][0], "id": 999999999})
    elif defect == "raw_digest":
        tables["telemetry_raw"][0]["payload_sha256"] = "0" * 64
    elif defect == "raw_cache":
        tables["telemetry_raw"][0]["raw_json"]["synthetic"] = False
    elif defect == "raw_metadata":
        tables["telemetry_raw"][0]["seq"] += 1
    elif defect == "normalized_content":
        tables["telemetry"][0]["t1_c"] += 1.0
    elif defect == "source_report":
        dataset["integrity"]["runs"][0]["raw_count"] += 1
    elif defect == "missing_current_close":
        tables["campaign_run_closures"] = []
    elif defect == "closure_digest":
        tables["campaign_run_closures"][0]["report_sha256"] = "0" * 64
    elif defect == "unscoped_raw":
        tables["telemetry_raw"][0]["run_id"] = "unregistered-software-run"
    elif defect == "orphan_attempt":
        tables["command_attempts"].append({"id": 999999999, "command_id": "unregistered-software-command", "attempt_no": 1})
    elif defect == "orphan_prediction_input":
        tables["prediction_inputs"].append({"prediction_id": "absent-software-prediction", "ordinal": 0, "telemetry_id": tables["telemetry"][0]["id"]})
    elif defect == "missing_version":
        dataset["campaign"]["namespace"]["runs"][0]["run"]["versions"].pop("model_version")
    elif defect == "nonfinite":
        with pytest.raises(ValueError):
            audit_campaign_export(record["export_bytes"].replace(b'"t1_c":', b'"t1_c":NaN,"ignored":', 1))
        return
    content = rehashed(bundle)
    if defect == "table_hash":
        bundle = json.loads(content)
        bundle["manifest"]["table_sha256"]["telemetry"] = "0" * 64
        content = encode_evidence(bundle)
    with pytest.raises(ValueError):
        audit_campaign_export(content)


def test_optional_wire_versions_cannot_contradict_frozen_run(db_engine, tmp_path):
    from coldguard_backend.final_audit import audit_campaign_export
    _context, record = final_context(db_engine, tmp_path)
    bundle = json.loads(record["export_bytes"])
    source = next(row for row in bundle["dataset"]["tables"]["telemetry_raw"] if row["topic"].endswith("/event"))
    wire = json.loads(source["raw_payload"])
    wire["backend_version"] = "b" * 40
    source["raw_json"] = wire
    source["raw_payload"] = json.dumps(wire)
    source["payload_sha256"] = digest(source["raw_payload"].encode())
    with pytest.raises(ValueError, match="wire version contradicts"):
        audit_campaign_export(rehashed(bundle))


def test_final_package_is_deterministic_frozen_source_not_live_reexport(db_engine, tmp_path, monkeypatch):
    from coldguard_backend.final_package import create_final_package, verify_final_package
    from tests.campaign_testkit import send_sample
    context, record = final_context(db_engine, tmp_path / "source")
    created = utcnow()
    first = tmp_path / "final-one"
    second = tmp_path / "final-two"
    result = create_final_package(context["destination"], record, destination=first, created_at=created, backend_commit="b" * 40)
    send_sample(context, context["draft"]["runs"][0]["run"], 5)  # Changes live evidence after its immutable freeze.
    monkeypatch.setattr("coldguard_backend.campaign_export.build_campaign_export", lambda *_args, **_kwargs: pytest.fail("final builder performed live re-export"))
    copy = create_final_package(context["destination"], record, destination=second, created_at=created, backend_commit="b" * 40)
    assert copy == result and verify_final_package(first, expected_manifest_sha256=result["manifest_sha256"]) == result["manifest"]
    assert (first / "dataset.json").read_bytes() == (first / "frozen/campaign-export.json").read_bytes() == record["export_bytes"]
    assert result["manifest"]["builder_commit"] == "b" * 40 and result["manifest"]["frozen_exporter_commit"] == "a" * 40
    assert {path.relative_to(first).as_posix(): path.read_bytes() for path in first.rglob("*") if path.is_file()} == {
        path.relative_to(second).as_posix(): path.read_bytes() for path in second.rglob("*") if path.is_file()}


def test_command_claims_are_exact_rows_not_physical_effect(db_engine, tmp_path):
    from coldguard_backend.final_package import create_final_package, verify_final_package
    context, record = final_context(db_engine, tmp_path / "source", commands=True)
    target = tmp_path / "final"
    result = create_final_package(context["destination"], record, destination=target, created_at=utcnow(), backend_commit="b" * 40)
    verify_final_package(target, expected_manifest_sha256=result["manifest_sha256"])
    claims = json.loads((target / "claim-index.json").read_bytes())
    assert {"COMMAND_INTENT_RECORDED", "BROKER_PUBACK_RECORDED", "DEVICE_ACCEPTANCE_ACK_RECORDED"} <= {row["status"] for row in claims["claims"]}
    bundle = json.loads(record["export_bytes"])
    for claim in claims["claims"]:
        assert claim["physical_acceptance"] == "BLOCKED_EXTERNAL"
        for reference in claim["references"]:
            assert reference["file_sha256"] == digest(record["export_bytes"])
            value = bundle
            for part in reference["json_pointer"].split("/")[1:]:
                value = value[int(part)] if isinstance(value, list) else value[part]
            assert digest(encode_evidence(value)) == reference["row_sha256"]


def test_separate_incident_package_stays_separately_scoped(db_engine, tmp_path):
    from coldguard_backend.final_package import create_final_package, verify_final_package
    from coldguard_backend.incident_audit import create_incident_package
    from tests.incident_testkit import journal_fixture
    from tests.test_campaign_backup import ready_campaign
    context, record = final_context(db_engine, tmp_path / "source")
    resilience = ready_campaign(db_engine)
    journal = journal_fixture(resilience, tmp_path / "observer-sources")
    incident_root = tmp_path / "incident"
    incident = create_incident_package(db_engine, journal, artifact_root=tmp_path / "observer-sources", destination=incident_root,
                                      created_at=utcnow(), backend_commit="b" * 40)
    target = tmp_path / "final"
    result = create_final_package(context["destination"], record, destination=target, created_at=utcnow(), backend_commit="b" * 40,
                                 incidents={"resilience": (incident_root, incident["manifest_sha256"])})
    verify_final_package(target, expected_manifest_sha256=result["manifest_sha256"])
    claims = json.loads((target / "claim-index.json").read_bytes())["claims"]
    observations = [row for row in claims if row["claim_id"].startswith("incident:")]
    assert len(observations) == 1 and observations[0]["campaign_id"] == resilience["draft"]["campaign_id"] != record["campaign_id"]
    assert observations[0]["status"] == "RECORDED_NOT_INDEPENDENTLY_ACCEPTED"
    assert json.loads((target / "run-list.json").read_bytes())["campaign_id"] == record["campaign_id"]
    for path in incident_root.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (target / "incidents/resilience" / path.relative_to(incident_root)).read_bytes()


@pytest.mark.parametrize("defect", ["anchor", "export", "missing", "extra", "record"])
def test_final_builder_refuses_corrupt_source_before_publication(db_engine, tmp_path, defect):
    from coldguard_backend.final_package import create_final_package
    context, record = final_context(db_engine, tmp_path / "source")
    source = context["destination"]
    if defect == "anchor":
        (source / "manifest.json").write_bytes((source / "manifest.json").read_bytes() + b" ")
    elif defect == "export":
        (source / "campaign-export.json").write_bytes(record["export_bytes"] + b" ")
    elif defect == "missing":
        (source / "artifacts/model-reference.bin").unlink()  # Newly owned negative fixture only.
    elif defect == "extra":
        (source / "unmanifested.json").write_bytes(b"{}")
    else:
        record = {**record, "export_bytes": record["export_bytes"] + b" "}
    target = tmp_path / "final"
    with pytest.raises((ValueError, FileNotFoundError)):
        create_final_package(source, record, destination=target, created_at=utcnow(), backend_commit="b" * 40)
    assert not target.exists()


def test_final_builder_copies_only_retained_anchor_checked_bytes(db_engine, tmp_path, monkeypatch):
    from coldguard_backend.final_package import create_final_package, verify_final_package
    context, record = final_context(db_engine, tmp_path / "source")
    original = Path.read_bytes
    reads = Counter()
    def raced(path):
        content = original(path)
        if context["destination"] in path.parents:
            reads[path.relative_to(context["destination"]).as_posix()] += 1
            if path.name == "campaign-export.json":
                path.write_bytes(content + b"changed-after-read")
        return content
    monkeypatch.setattr(Path, "read_bytes", raced)
    target = tmp_path / "final"
    result = create_final_package(context["destination"], record, destination=target, created_at=utcnow(), backend_commit="b" * 40)
    assert reads and set(reads.values()) == {1}
    verify_final_package(target, expected_manifest_sha256=result["manifest_sha256"])
    assert original(target / "dataset.json") == record["export_bytes"]


def test_partial_write_never_publishes_ready_final_or_mutates_source(db_engine, tmp_path, monkeypatch):
    from coldguard_backend.final_package import create_final_package
    context, record = final_context(db_engine, tmp_path / "source")
    original = Path.open
    def interrupted(path, mode="r", *args, **kwargs):
        if path.name == "claim-index.json" and mode == "xb":
            raise OSError("SOFTWARE_SIMULATION interrupted final output")
        return original(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", interrupted)
    target = tmp_path / "final"
    with pytest.raises(OSError, match="interrupted"):
        create_final_package(context["destination"], record, destination=target, created_at=utcnow(), backend_commit="b" * 40)
    assert not target.exists() and list(tmp_path.glob(".evidence-staging-*"))
    assert (context["destination"] / "campaign-export.json").read_bytes() == record["export_bytes"]


@pytest.mark.parametrize("defect", ["dataset", "claim", "extra"])
def test_final_verification_rejects_corruption(db_engine, tmp_path, defect):
    from coldguard_backend.final_package import create_final_package, verify_final_package
    context, record = final_context(db_engine, tmp_path / "source")
    target = tmp_path / "final"
    result = create_final_package(context["destination"], record, destination=target, created_at=utcnow(), backend_commit="b" * 40)
    path = target / {"dataset": "dataset.json", "claim": "claim-index.json", "extra": "unmanifested.json"}[defect]
    path.write_bytes(b"{}")
    with pytest.raises(ValueError):
        verify_final_package(target, expected_manifest_sha256=result["manifest_sha256"])


@pytest.mark.parametrize("operation", ["build", "verify"])
def test_final_cli_refuses_internal_report_before_engine_creation(tmp_path, monkeypatch, operation):
    from scripts import final_package as cli
    calls = []
    monkeypatch.setattr(cli, "create_engine", lambda *_args, **_kwargs: calls.append(True))
    directory = tmp_path / "package"
    monkeypatch.setattr("sys.argv", ["final_package.py", operation, "--directory", str(directory), "--report", str(directory / "report.json")])
    with pytest.raises(SystemExit):
        cli.main()
    assert not calls and not directory.exists()


def test_final_builder_rejects_overlap_and_reserved_labels_without_source_mutation(db_engine, tmp_path):
    from coldguard_backend.final_package import create_final_package
    context, record = final_context(db_engine, tmp_path / "source")
    source = context["destination"]
    with pytest.raises(ValueError, match="overlap"):
        create_final_package(source, record, destination=source / "nested-final", created_at=utcnow(), backend_commit="b" * 40)
    with pytest.raises(ValueError):
        create_final_package(source, record, destination=tmp_path / "final", created_at=utcnow(), backend_commit="b" * 40,
                             incidents={"NUL": (source, record["manifest_sha256"])})
    assert not (source / "nested-final").exists() and not (tmp_path / "final").exists()
