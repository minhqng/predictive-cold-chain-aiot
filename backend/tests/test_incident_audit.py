"""Bounded reconstruction, source-integrity and real-provider W21 proof artifacts."""

from datetime import timedelta
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess

import pytest
from sqlalchemy import create_engine, select

from coldguard_backend import command_store as commands
from coldguard_backend.campaign_integrity import close_run, live_integrity
from coldguard_backend.command_authorization import AuthorizedCommandGateway, CommandDispatchUnavailable
from coldguard_backend.command_service import create_command_intent
from coldguard_backend.evidence_backup import backup_campaign, restore_backup
from coldguard_backend.evidence_package import digest, package_path, publish_package, verify_package
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.incident_audit import IncidentJournal, build_incident_audit, create_incident_package, verify_incident_package
from coldguard_backend.mqtt_consumer import MqttIngestConsumer
from coldguard_backend.raw_store import telemetry_raw
from coldguard_backend.recovery import reconcile_command_history
from tests.campaign_testkit import campaign_draft, complete_run, register_fixture, snapshot_transaction
from tests.command_testkit import make_command, utcnow
from tests.incident_testkit import journal_fixture
from tests.mqtt_testkit import has_test_mqtt, make_test_config, mqtt_params, wait_for
from tests.test_broker_security import DEVICE_COMMAND, _Probe
from tests.test_campaign_backup import ready_campaign
from tests.test_platform_reconnect import restartable_broker  # noqa: F401


def capture(context, journal, root, target, created_at=None):
    return create_incident_package(context["engine"], journal, artifact_root=root, destination=target,
                                    created_at=created_at or utcnow(), backend_commit="a" * 40)


def observation(run, event_id, event_type, name, content, *, command_ids=None, raw_ids=None):
    return {"event_id": event_id, "event_type": event_type, "observed_at": utcnow(), "run_id": run["run_id"],
        "device_id": run["device_id"], "source_name": name, "source_sha256": digest(content), "source_kind": "observer_snapshot",
        "summary": "SOFTWARE_SIMULATION actual owned-provider observation; no hardware or peer acceptance",
        "command_ids": command_ids or [], "raw_ids": raw_ids or []}


@pytest.mark.parametrize("stamp", [None, 1, True, [], {}, "not-a-time", "2026-11-08T00:00:00"])
def test_journal_json_time_is_strict_and_aware(stamp):
    document = {"campaign_id": "software-campaign", "data_class": "SOFTWARE_SIMULATION", "observations": [{
        "event_id": "software-event", "event_type": "BROKER_DISCONNECTED", "observed_at": stamp,
        "source_name": "observer.json", "source_sha256": "a" * 64, "source_kind": "observer_snapshot", "summary": "SOFTWARE_SIMULATION"}]}
    with pytest.raises(ValueError):
        IncidentJournal.model_validate_json(json.dumps(document))


def test_journal_refuses_duplicate_ids_conflicting_sources_and_false_approval(tmp_path, db_engine):
    context = ready_campaign(db_engine)
    journal = journal_fixture(context, tmp_path / "sources")
    document = journal.model_dump(mode="json")
    document["observations"].append(document["observations"][0].copy())
    with pytest.raises(ValueError, match="distinct"):
        IncidentJournal.model_validate_json(json.dumps(document))
    document["observations"][1].update(event_id="second", source_sha256="0" * 64)
    with pytest.raises(ValueError, match="conflicting checksums"):
        IncidentJournal.model_validate_json(json.dumps(document))
    document = journal.model_dump(mode="json") | {"physical_acceptance": "PASS"}
    with pytest.raises(ValueError):
        IncidentJournal.model_validate_json(json.dumps(document))


@pytest.mark.parametrize("defect", ["checksum", "run_scope", "device_scope", "raw_scope", "command_scope", "class", "future"])
def test_incident_refuses_corrupt_or_misattributed_input_without_publication(db_engine, tmp_path, defect):
    context = ready_campaign(db_engine)
    root = tmp_path / "sources"
    journal = journal_fixture(context, root)
    row = journal.observations[0]
    changed = {"run_scope": {"run_id": "outside-run"}, "device_scope": {"device_id": "outside-device"},
               "raw_scope": {"raw_ids": [2**62]}, "command_scope": {"command_ids": ["absent-command"]},
               "future": {"observed_at": utcnow() + timedelta(hours=1)}}
    if defect == "checksum":
        (root / "observer.json").write_bytes(b"altered")
    elif defect == "class":
        journal = journal.model_copy(update={"data_class": "PHYSICAL"})
    else:
        journal = journal.model_copy(update={"observations": [row.model_copy(update=changed[defect])]})
    destination = tmp_path / "refused"
    with pytest.raises(ValueError):
        capture(context, journal, root, destination)
    assert not destination.exists()


def test_audit_refuses_multi_snapshot_transaction(db_engine, tmp_path):
    context = ready_campaign(db_engine)
    journal = journal_fixture(context, tmp_path / "sources")
    with db_engine.connect() as connection, pytest.raises(ValueError, match="repeatable snapshot"):
        build_incident_audit(connection, journal, created_at=utcnow(), backend_commit="a" * 40)


@pytest.mark.skipif(not os.environ.get("COLDGUARD_TEST_INCIDENT_RESTORE_URL"), reason="requires a separate empty incident restore DB")
def test_incident_export_and_pending_command_survive_clean_restore_byte_identically(db_engine, tmp_path):
    context = ready_campaign(db_engine)
    run = context["draft"]["runs"][0]["run"]
    command = make_command("software-incident-" + secrets.token_hex(8), device_id=run["device_id"], run_id=run["run_id"],
                           cooling="OFF", duty=None, policy_version=run["versions"]["policy_version"])
    intent = create_command_intent(db_engine, command)
    with db_engine.begin() as connection:
        attempt = commands.begin_publish_attempt(connection, command.command_id, payload_sha256=intent["command"]["payload_sha256"])
    recovery = reconcile_command_history(db_engine)
    assert command.command_id in recovery["uncertain_commands"]
    source = encode_evidence({"data_class": "SOFTWARE_SIMULATION", "recovery": recovery, "hardware": "NOT_USED",
                              "note": "actual DB crash-window reconciliation; no publish occurred"})
    root = tmp_path / "sources"
    journal = journal_fixture(context, root, sources={"recovery.json": source}, observations=[
        observation(run, "software-pending", "COMMAND_DISPATCH_BLOCKED", "recovery.json", source, command_ids=[command.command_id])])
    created = utcnow()
    first = capture(context, journal, root, tmp_path / "first", created)
    second = capture(context, journal, root, tmp_path / "second", created)
    assert first == second
    content = (tmp_path / "first/incident-audit.json").read_bytes()
    audit = json.loads(content)
    assert any(row["id"] == attempt["attempt_id"] and row["outcome"] == "UNKNOWN" for row in audit["command_evidence"]["command_attempts"])
    assert audit["physical_acceptance"] == "BLOCKED_EXTERNAL" and audit["observation_status"] == "RECORDED_NOT_INDEPENDENTLY_ACCEPTED"
    archive = tmp_path / "archive"
    backup_campaign(db_engine, context["draft"]["campaign_id"], archive, pg_dump=os.environ["COLDGUARD_TEST_PG_DUMP"])
    restore = restore_backup(archive, os.environ["COLDGUARD_TEST_INCIDENT_RESTORE_URL"], pg_restore=os.environ["COLDGUARD_TEST_PG_RESTORE"])
    assert restore["match"]
    engine = create_engine(os.environ["COLDGUARD_TEST_INCIDENT_RESTORE_URL"])
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True) as connection:
            rebuilt = build_incident_audit(connection, journal, created_at=created, backend_commit="a" * 40)
        assert rebuilt == content
    finally:
        engine.dispose()
    verify_incident_package(tmp_path / "first", expected_manifest_sha256=first["manifest_sha256"])


@pytest.mark.parametrize("defect", ["manifest", "missing", "extra", "source"])
def test_anchored_incident_package_rejects_tampering(db_engine, tmp_path, defect):
    context = ready_campaign(db_engine)
    root = tmp_path / "sources"
    journal = journal_fixture(context, root)
    directory = tmp_path / "package"
    record = capture(context, journal, root, directory)
    if defect == "manifest":
        path = directory / "manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif defect == "missing":
        (directory / "incident-audit.json").unlink()
    elif defect == "extra":
        (directory / "unexpected.txt").write_text("SOFTWARE_SIMULATION unmanifested input")
    else:
        (directory / "sources/observer.json").write_bytes(b"altered")
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_incident_package(directory, expected_manifest_sha256=record["manifest_sha256"])


def test_partial_package_write_and_existing_destination_cannot_publish_ready(tmp_path, monkeypatch):
    destination = tmp_path / "failed"
    original = Path.open
    def broken(path, *args, **kwargs):
        if path.name == "second.json":
            raise OSError("demonstrated disk write failure")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", broken)
    with pytest.raises(OSError, match="disk write"):
        publish_package(destination, {"first.json": b"1", "second.json": b"2"}, format="software-test", metadata={})
    assert not destination.exists()
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        publish_package(existing, {"first.json": b"1"}, format="software-test", metadata={})
    assert list(existing.iterdir()) == []


@pytest.mark.parametrize("name", ["../escape", "nested/../escape", "/absolute", "C:/absolute", "nested\\escape"])
def test_package_paths_refuse_traversal_and_platform_aliases(tmp_path, name):
    with pytest.raises(ValueError):
        package_path(tmp_path, name)


def test_package_source_junction_escape_is_refused(tmp_path):
    root, other = tmp_path / "package", tmp_path / "external"
    root.mkdir()
    other.mkdir()
    alias = root / "sources"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(other)], check=True, capture_output=True)
    else:
        alias.symlink_to(other, target_is_directory=True)
    with pytest.raises(ValueError):
        package_path(root, "sources/observer.json")


def test_incident_cli_refuses_internal_report_before_any_operation(tmp_path, monkeypatch):
    from scripts import audit_incidents as cli
    directory = tmp_path / "package"
    monkeypatch.setattr("sys.argv", ["audit_incidents.py", "verify", "--directory", str(directory),
                                    "--report", str(directory / "verify.json"), "--manifest-sha256", "a" * 64])
    with pytest.raises(SystemExit):
        cli.main()
    assert not directory.exists()


@pytest.mark.skipif(not has_test_mqtt(), reason="requires real owned Mosquitto")
def test_actual_denied_publish_and_legitimate_device_receipts_are_reconstructable(db_engine, tmp_path):
    draft = campaign_draft()
    for plan in draft["runs"]:
        plan["run"]["device_id"] = "coldguard-001"
    context = register_fixture(db_engine, draft)
    a, _ = complete_run(context), complete_run(context, "B")
    params = mqtt_params()
    consumer = MqttIngestConsumer(make_test_config(mqtt_user=params["backend_user"], mqtt_password=params["backend_password"]),
                                  subscriptions=(("coldguard/coldguard-001/telemetry", 1),))
    device = _Probe(username=params["device_user"], password=params["device_password"])
    try:
        consumer.start()
        device.subscribe(DEVICE_COMMAND)
        marker = b"SOFTWARE_SIMULATION denied command probe, no hardware"
        device.publish_sync(DEVICE_COMMAND, marker)
        assert wait_for(lambda: len(device.publish_results) == 1, timeout_s=5)
        denied = device.publish_results[0]
        assert "not authorized" in denied.lower()
        assert not wait_for(lambda: any(payload == marker for _, payload in device.received), timeout_s=0.5)
        with db_engine.connect() as connection:
            payload = connection.execute(select(telemetry_raw.c.raw_payload).where(telemetry_raw.c.run_id == a["run_id"],
                telemetry_raw.c.topic.endswith("/telemetry")).order_by(telemetry_raw.c.id)).scalar()
        device.publish_sync("coldguard/coldguard-001/telemetry", payload.encode())
        assert wait_for(lambda: consumer.snapshot()["persisted"] == 1 and len(device.publish_results) == 2, timeout_s=5)
        assert "not authorized" not in device.publish_results[1].lower()
        with snapshot_transaction(db_engine) as connection:
            for plan in draft["runs"]:
                close_run(connection, draft["campaign_id"], plan["run"]["run_id"], reason="SOFTWARE_SIMULATION actual ACL probe close")
            raw_id = connection.scalar(select(telemetry_raw.c.id).where(telemetry_raw.c.run_id == a["run_id"],
                telemetry_raw.c.topic.endswith("/telemetry")).order_by(telemetry_raw.c.id.desc()).limit(1))
        receipt = encode_evidence({"data_class": "SOFTWARE_SIMULATION", "denied_puback": denied,
            "legitimate_puback": device.publish_results[1], "ingestion": consumer.snapshot(),
            "no_denied_command_delivery_observed": True, "observation_window_sec": 0.5, "hardware": "NOT_USED"})
        root = tmp_path / "sources"
        entries = [observation(a, "acl-denied", "MQTT_PUBLISH_DENIED", "protocol.json", receipt),
                   observation(a, "device-accepted", "MQTT_PUBLISH_ACCEPTED", "protocol.json", receipt, raw_ids=[raw_id])]
        for entry in entries:
            entry["source_kind"] = "protocol_receipt"
        journal = journal_fixture(context, root, sources={"protocol.json": receipt}, observations=entries)
        record = capture(context, journal, root, tmp_path / "actual-acl-package")
        verify_incident_package(tmp_path / "actual-acl-package", expected_manifest_sha256=record["manifest_sha256"])
    finally:
        consumer.stop()
        device.close()


def test_real_broker_outage_reconnect_and_blocked_dispatch_are_retained(db_engine, restartable_broker, tmp_path):
    start, stop = restartable_broker
    context = ready_campaign(db_engine)
    params = mqtt_params()
    consumer = MqttIngestConsumer(make_test_config(mqtt_user=params["backend_user"], mqtt_password=params["backend_password"]),
                                  subscriptions=(("coldguard/+/telemetry", 1),))
    try:
        consumer.start()
        before = consumer.snapshot()
        stop()
        assert wait_for(lambda: not consumer.snapshot()["broker_connected"], timeout_s=5)
        down = consumer.snapshot()
        token = secrets.token_urlsafe(24)
        gateway = AuthorizedCommandGateway(db_engine, lambda *_: pytest.fail("outage dispatched a command"), backend_token=token,
            allowed_devices=frozenset({"coldguard-001"}), policy_allows=lambda _: True,
            transport_ready=lambda: consumer.snapshot()["broker_connected"] and consumer.snapshot()["subscribed"])
        rejected = make_command("software-outage-" + secrets.token_hex(6), cooling="OFF", duty=None)
        with pytest.raises(CommandDispatchUnavailable):
            gateway.dispatch(rejected, backend_token=token)
        with db_engine.connect() as connection:
            assert commands.get_command(connection, rejected.command_id) is None
        start()
        assert wait_for(lambda: consumer.snapshot()["subscribed"], timeout_s=10)
        receipt = encode_evidence({"data_class": "SOFTWARE_SIMULATION", "before": before, "during": down,
            "after": consumer.snapshot(), "rejected_command_id": rejected.command_id, "command_persisted": False,
            "hardware": "NOT_USED", "physical_SAFE_LOCAL": "BLOCKED_EXTERNAL"})
        run = context["draft"]["runs"][0]["run"]
        root = tmp_path / "sources"
        journal = journal_fixture(context, root, sources={"outage.json": receipt}, observations=[
            observation(run, "broker-down", "BROKER_DISCONNECTED", "outage.json", receipt),
            observation(run, "dispatch-refused", "COMMAND_DISPATCH_BLOCKED", "outage.json", receipt),
            observation(run, "broker-up", "BROKER_RECONNECTED", "outage.json", receipt)])
        record = capture(context, journal, root, tmp_path / "outage-package")
        verify_incident_package(tmp_path / "outage-package", expected_manifest_sha256=record["manifest_sha256"])
    finally:
        consumer.stop()


def test_database_unavailability_is_retained_without_fabricated_inventory(db_engine, tmp_path):
    context = ready_campaign(db_engine)
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        broken = create_engine(db_engine.url.set(port=reserved.getsockname()[1]), connect_args={"connect_timeout": 1})
        try:
            report = live_integrity(broken, context["draft"]["campaign_id"])
        finally:
            broken.dispose()
    assert report["database_health"] == "UNAVAILABLE" and report["runs"] is None
    source = encode_evidence({"data_class": "SOFTWARE_SIMULATION", "observed": report,
        "method": "owned reserved unlistening loopback port; original database not stopped"})
    root = tmp_path / "sources"
    run = context["draft"]["runs"][0]["run"]
    journal = journal_fixture(context, root, sources={"database.json": source}, observations=[
        observation(run, "db-unavailable", "DATABASE_UNAVAILABLE", "database.json", source)])
    capture(context, journal, root, tmp_path / "database-package")


def test_incident_verification_retains_each_anchor_checked_file_once(db_engine, tmp_path, monkeypatch):
    context = ready_campaign(db_engine)
    root = tmp_path / "sources"
    journal = journal_fixture(context, root)
    directory = tmp_path / "package"
    record = capture(context, journal, root, directory)
    original = Path.read_bytes
    counts, changed = {}, []
    def raced(path):
        content = original(path)
        if directory in path.parents:
            name = path.relative_to(directory).as_posix()
            counts[name] = counts.get(name, 0) + 1
            if name == "sources/observer.json" and not changed:
                path.write_bytes(content + b"SOFTWARE_SIMULATION changed after anchor read")
                changed.append(True)
        return content
    monkeypatch.setattr(Path, "read_bytes", raced)
    verify_incident_package(directory, expected_manifest_sha256=record["manifest_sha256"])
    assert changed and all(count == 1 for count in counts.values())
    with pytest.raises(ValueError, match="checksum"):
        verify_incident_package(directory, expected_manifest_sha256=record["manifest_sha256"])


@pytest.mark.skipif(not has_test_mqtt(), reason="requires real owned MQTT/backend process providers")
def test_real_backend_restart_and_expiry_have_retained_logs_and_command_history(db_engine, tmp_path, monkeypatch):
    from tests.test_ack_consumer import _enable_app_ack
    from tests.test_outage_recovery import _backend_process
    context = ready_campaign(db_engine)
    run = context["draft"]["runs"][0]["run"]
    _enable_app_ack(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("COLDGUARD_MQTT_INGEST", "true")
    monkeypatch.setenv("COLDGUARD_RECONCILE_COMMANDS", "true")
    monkeypatch.delenv("MQTT_TLS_CA", raising=False)
    pids = []
    created = utcnow() - timedelta(minutes=3)
    command = make_command("software-restart-" + secrets.token_hex(8), device_id=run["device_id"], run_id=run["run_id"],
        created_at=created, ttl_s=5, cooling="OFF", duty=None, policy_version=run["versions"]["policy_version"])
    endpoint = f"/api/devices/{run['device_id']}/recovery"
    with _backend_process(tmp_path / "before.log", pids) as first:
        assert all(first.get("/api/runtime/readiness").json().values())
        first_observed = utcnow()
        intent = create_command_intent(db_engine, command, now=created)
        with db_engine.begin() as connection:
            attempt = commands.begin_publish_attempt(connection, command.command_id,
                payload_sha256=intent["command"]["payload_sha256"], now=created)
        before = first.get(endpoint).json()
        assert before["pending_attempts"] == 1
    with _backend_process(tmp_path / "after.log", pids) as second:
        assert all(second.get("/api/runtime/readiness").json().values())
        second_observed = utcnow()
        after = second.get(endpoint).json()
        assert after["pending_attempts"] == 0 and after["desired"]["status"] == commands.EXPIRED
    assert len(set(pids)) == 2
    with db_engine.connect() as connection:
        assert commands.get_attempt(connection, attempt["attempt_id"])["outcome"] == "UNKNOWN"
    receipt = encode_evidence({"data_class": "SOFTWARE_SIMULATION", "process_pids": pids, "before": before, "after": after,
        "hardware": "NOT_USED", "note": "generated expired pending intent; real process restart and DB reconciliation"})
    root = tmp_path / "sources"
    sources = {"before.log": (tmp_path / "before.log").read_bytes(), "after.log": (tmp_path / "after.log").read_bytes(), "recovery.json": receipt}
    entries = [observation(run, "backend-started", "BACKEND_STARTED", "before.log", sources["before.log"]),
               observation(run, "backend-restarted", "BACKEND_RESTARTED", "after.log", sources["after.log"]),
               observation(run, "expired-no-replay", "COMMAND_DISPATCH_BLOCKED", "recovery.json", receipt, command_ids=[command.command_id])]
    entries[0].update(source_kind="backend_log", observed_at=first_observed)
    entries[1].update(source_kind="backend_log", observed_at=second_observed)
    journal = journal_fixture(context, root, sources=sources, observations=entries)
    record = capture(context, journal, root, tmp_path / "backend-restart-package")
    verify_incident_package(tmp_path / "backend-restart-package", expected_manifest_sha256=record["manifest_sha256"])


@pytest.mark.parametrize("name", ["observer.json.", "observer.json.."])
def test_trailing_dot_source_alias_cannot_publish_a_ready_incident(db_engine, tmp_path, name):
    context = ready_campaign(db_engine)
    root = tmp_path / "sources"
    journal = journal_fixture(context, root)
    if os.name != "nt":
        (root / name).write_bytes((root / "observer.json").read_bytes())
    changed = journal.model_copy(update={"observations": [journal.observations[0].model_copy(update={"source_name": name})]})
    destination = tmp_path / "refused-alias"
    with pytest.raises(ValueError, match="portable|filename|alias"):
        capture(context, changed, root, destination)
    assert not destination.exists()


@pytest.mark.parametrize("name", ["sources./observer.json", "sources /observer.json", "observer.json "])
def test_nonportable_intermediate_and_leaf_components_refused_before_publication(tmp_path, name):
    destination = tmp_path / "refused-path"
    with pytest.raises(ValueError, match="portable|filename|alias"):
        publish_package(destination, {name: b"SOFTWARE_SIMULATION"}, format="software-path-test", metadata={})
    assert not destination.exists()


@pytest.mark.parametrize("name", ["NUL", "NUL.json", "CON", "con.txt", "COM1.txt", "LPT9"])
def test_shared_artifact_name_model_refuses_reserved_devices_without_io(name):
    from coldguard_backend.campaign_freeze import ArtifactReference
    with pytest.raises(ValueError):
        ArtifactReference.model_validate({"name": name, "kind": "model_reference", "sha256": "a" * 64})


@pytest.mark.parametrize("name", ["COM1", "LPT2.txt", "COM\u00b9"])
def test_reserved_component_rejected_before_any_filesystem_resolution(tmp_path, monkeypatch, name):
    def forbidden(*_args, **_kwargs):
        pytest.fail("reserved filename reached filesystem resolution; no device/hardware access is permitted")
    monkeypatch.setattr(Path, "resolve", forbidden)
    with pytest.raises(ValueError, match="portable|filename|reserved"):
        package_path(tmp_path, name)
