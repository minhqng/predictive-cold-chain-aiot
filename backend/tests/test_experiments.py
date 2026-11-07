"""W07 tests using the disposable provider and software-only evidence."""

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from coldguard_backend import command_store as commands
from coldguard_backend import experiment_store as runs
from coldguard_backend.dataset_export import build_s1_export
from coldguard_backend.ingest import ingest_message
from coldguard_backend.main import app, get_db_engine
from coldguard_backend.simulator import build_event, build_telemetry
from tests.command_testkit import cleanup_commands, make_ack, make_command, utcnow
from tests.test_command_store import _record_ack
from tests.test_migration_w05 import _cleanup_device, _seed_schema2


@pytest.fixture
def run_context(db_engine):
    suffix = uuid4().hex
    device, other_device = f"w07-{suffix}", f"other-{suffix}"
    request = {
        "run_id": f"run-{suffix}",
        "device_id": device,
        "scenario_id": "S2_DOOR_DISTURBANCE",
        "controller_id": "REACTIVE",
        "pair_id": "pair-test",
        "versions": {"firmware": "synthetic", "schema": 1, "model": None},
        "notes": "Software-only test fixture.",
    }
    app.dependency_overrides[get_db_engine] = lambda: db_engine
    try:
        yield TestClient(app), request, other_device
    finally:
        app.dependency_overrides.pop(get_db_engine, None)
        with db_engine.begin() as conn:
            for table in (runs.experiment_transitions, runs.experiments):
                conn.execute(table.delete().where(table.c.run_id == request["run_id"]))
        for identity in (device, other_device):
            cleanup_commands(db_engine, identity)
            _cleanup_device(db_engine, identity)


@pytest.mark.parametrize("run_id", ["", "UNSET", "two/parts"])
def test_register_rejects_non_addressable_run_id(run_id):
    response = TestClient(app).post("/api/runs", json={
        "run_id": run_id, "device_id": "unit-device", "scenario_id": "S2",
        "controller_id": "REACTIVE", "versions": {"schema": 1},
    })
    assert response.status_code == 422


def test_lifecycle_requires_explicit_review_and_final_reason(run_context):
    client, request, _ = run_context
    path = f"/api/runs/{request['run_id']}"
    assert client.get(path).status_code == 404
    assert client.post("/api/runs", json=request).status_code == 201
    assert client.post("/api/runs", json=request).status_code == 409
    assert client.post(path + "/transitions", json={"status": "RUNNING"}).status_code == 409
    for status in ("ARMED", "RUNNING", "COMPLETED_RAW"):
        assert client.post(path + "/transitions", json={"status": status}).status_code == 200
    assert client.post(path + "/transitions", json={"status": "VALID", "reason": "reviewed"}).status_code == 409
    assert client.post(path + "/transitions", json={"status": "VALIDITY_REVIEW"}).status_code == 200
    assert client.post(path + "/transitions", json={"status": "VALID"}).status_code == 409
    assert client.post(path + "/transitions", json={"status": "VALID", "reason": "synthetic QA"}).status_code == 200
    assert client.post(path + "/transitions", json={"status": "INVALID", "reason": "late edit"}).status_code == 409
    result = client.get(path).json()
    assert result["run"]["status"] == "VALID"
    assert result["run"]["started_at"] <= result["run"]["ended_at"]
    assert [row["to_status"] for row in result["history"]] == [
        "PLANNED", "ARMED", "RUNNING", "COMPLETED_RAW", "VALIDITY_REVIEW", "VALID",
    ]
    assert result["history"][-1]["reason"] == "synthetic QA"


def test_concurrent_finalization_records_one_terminal_transition(db_engine, run_context):
    client, request, _ = run_context
    run_id = request["run_id"]
    assert client.post("/api/runs", json=request).status_code == 201
    with db_engine.begin() as conn:
        for status in ("ARMED", "RUNNING", "COMPLETED_RAW", "VALIDITY_REVIEW"):
            runs.transition_run(conn, run_id, runs.RunTransition(status=status))
    ready = threading.Barrier(2)

    def finish(status):
        ready.wait(timeout=5)
        try:
            with db_engine.begin() as conn:
                return runs.transition_run(
                    conn, run_id, runs.RunTransition(status=status, reason="synthetic QA"),
                )["status"]
        except runs.RunConflict:
            return "conflict"

    with ThreadPoolExecutor(2) as threads:
        result = list(threads.map(finish, ("VALID", "INVALID")))
    assert result.count("conflict") == 1
    with db_engine.begin() as conn:
        history = runs.run_history(conn, run_id)
        assert len(history) == 6
        assert history[-1]["to_status"] == runs.get_run(conn, run_id)["status"]


def test_run_db_checks_and_abort_before_start(db_engine, run_context):
    client, request, _ = run_context
    run_id = request["run_id"]
    assert client.post("/api/runs", json=request).status_code == 201
    with pytest.raises(IntegrityError, match="ck_experiments_times"):
        with db_engine.begin() as conn:
            conn.execute(runs.experiments.update().where(runs.experiments.c.run_id == run_id).values(
                status="RUNNING",
            ))
    with pytest.raises(IntegrityError, match="foreign key"):
        with db_engine.begin() as conn:
            conn.execute(runs.experiment_transitions.insert().values(
                run_id="unregistered-run", to_status="PLANNED", occurred_at=utcnow(),
            ))
    response = client.post(f"/api/runs/{run_id}/transitions", json={
        "status": "ABORTED", "reason": "synthetic safety stop",
    })
    assert response.status_code == 200
    assert response.json()["started_at"] is None
    assert response.json()["ended_at"] is not None


def test_export_and_timeline_are_deterministic_and_isolated(db_engine, run_context):
    client, request, other_device = run_context
    device, run_id = request["device_id"], request["run_id"]
    path = f"/api/runs/{run_id}"
    assert client.post("/api/runs", json=request).status_code == 201
    for status in ("ARMED", "RUNNING"):
        assert client.post(path + "/transitions", json={"status": status}).status_code == 200
    stamp = utcnow()

    def send(identity, payload, kind="telemetry"):
        return ingest_message(
            db_engine, topic=f"coldguard/{identity}/{kind}",
            payload=json.dumps(payload).encode(), received_at=stamp,
        )

    sample = build_telemetry(device_id=device, boot_id="test-boot", seq=1, run_id=run_id)
    assert send(device, sample)["normalized"]["outcome"] == "inserted"
    assert send(device, sample)["normalized"]["outcome"] == "exact_duplicate"
    assert send(device, dict(sample, seq=2, run_id=None))["normalized"]["outcome"] == "inserted"
    assert send(device, dict(sample, run_id="conflicting-run"))["normalized"]["outcome"] == "conflict"
    assert send(other_device, dict(sample, device_id=other_device))["normalized"]["outcome"] == "inserted"
    clockless_id = _seed_schema2(db_engine, device, 3, stamp, run_id)
    event = build_event(device_id=device, boot_id="test-boot", seq=4, run_id=run_id, event_type="DOOR_OPENED")
    assert send(device, event, "event")["normalized"] == "observed"
    send(other_device, event, "event")
    with db_engine.begin() as conn:
        for command_id, identity in (("w07-in-scope", device), ("w07-wrong-device", other_device)):
            commands.create_command(conn, make_command(command_id, device_id=identity, run_id=run_id))
            commands.transition_command(conn, command_id, commands.PUBLISHED)
    assert _record_ack(db_engine, make_ack("w07-in-scope", device_id=device), topic_device=device)["outcome"] == "applied"

    export = client.get(path + "/export")
    assert export.status_code == 200
    assert export.content == client.get(path + "/export").content
    bundle = export.json()
    assert bundle["manifest"]["sample_count"] == 2
    assert bundle["manifest"]["clockless_count"] == 1
    data = bundle["dataset"]
    encoded = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == bundle["manifest"]["dataset_sha256"]
    normal, clockless = data["telemetry"]
    assert normal["synthetic"] is True
    assert normal["event_time"] is not None
    assert clockless["raw_id"] == clockless_id
    assert clockless["event_time"] is None
    assert clockless["timing"]["latency_ms"] is None

    timeline = client.get(path + "/timeline").json()
    assert timeline == client.get(path + "/timeline").json()
    entries = timeline["items"]
    assert [e["backend_at"] for e in entries] == sorted(e["backend_at"] for e in entries)
    assert [e["payload"]["event_type"] for e in entries if e["kind"] == "event_receipt"] == ["DOOR_OPENED"]
    assert [e["id"] for e in entries if e["kind"] == "command_intent"] == ["w07-in-scope"]
    assert [e["verdict"] for e in entries if e["kind"] == "ack_receipt"] == ["ACCEPTED"]
    page = client.get(path + "/telemetry", params={"limit": 1}).json()
    assert page["next_offset"] == 1
    assert page["items"][0]["seq"] == 1
    second = client.get(path + "/telemetry", params={"limit": 1, "offset": page["next_offset"]}).json()
    assert second["items"][0]["seq"] == 3
    assert second["next_offset"] is None
    assert len(client.get(path + "/events").json()["items"]) == 1
    assert [row["command_id"] for row in client.get(path + "/commands").json()["items"]] == ["w07-in-scope"]
    assert client.get(path + "/telemetry", params={"limit": 501}).status_code == 422
    assert client.get(path + "/telemetry", params={"offset": -1}).status_code == 422
    with db_engine.connect() as conn:
        assert conn.execute(select(runs.experiments.c.device_id).where(
            runs.experiments.c.run_id == run_id,
        )).scalar_one() == device


def test_s1_export_detects_integrity_anomalies_and_is_reproducible(db_engine, run_context):
    client, request, other_device = run_context
    device, run_id = request["device_id"], request["run_id"]
    request["scenario_id"] = "S1_NORMAL_BASELINE"
    request["versions"] = {"firmware_version": "declared-fw", "schema_version": 1}
    path = f"/api/runs/{run_id}"
    assert client.post("/api/runs", json=request).status_code == 201
    created_at = utcnow()
    commit = "a" * 40
    with db_engine.connect() as conn:
        with pytest.raises(ValueError, match="must be a valid S1 baseline"):
            build_s1_export(conn, [run_id], created_at=created_at, backend_commit=commit)
    for status in ("ARMED", "RUNNING"):
        assert client.post(path + "/transitions", json={"status": status}).status_code == 200
    first = build_telemetry(device_id=device, boot_id="software-boot", seq=10, run_id=run_id)
    second = build_telemetry(device_id=device, boot_id="software-boot", seq=12, run_id=run_id)
    for sample in (first, first, second, dict(second, device_id=other_device)):
        ingest_message(
            db_engine, topic=f"coldguard/{sample['device_id']}/telemetry",
            payload=json.dumps(sample).encode(),
        )
    for status in ("COMPLETED_RAW", "VALIDITY_REVIEW", "VALID"):
        assert client.post(path + "/transitions", json={
            "status": status, "reason": "software QA fixture",
        }).status_code == 200
    integrity = client.get(path + "/integrity").json()
    assert integrity["sequence_gaps"] == [
        {"boot_id": "software-boot", "first_missing": 11, "last_missing": 11},
    ]
    assert integrity["duplicate_identities"] == [
        {"boot_id": "software-boot", "seq": 10, "raw_deliveries": 2},
    ]
    assert len(integrity["event_time_outside_run_unverified"]) == 2
    assert not integrity["receipt_time_outside_run"]
    assert integrity["quality_counts"]["overall_quality"] == {"VALID": 2}
    assert {issue["field"] for issue in integrity["version_mismatches"]} == {"firmware_version"}
    with db_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        first_export = build_s1_export(conn, [run_id], created_at=created_at, backend_commit=commit)
        assert first_export == build_s1_export(conn, [run_id], created_at=created_at, backend_commit=commit)
    bundle = json.loads(first_export)
    assert bundle["manifest"]["run_ids"] == [run_id]
    assert bundle["manifest"]["backend_commit"] == commit
    assert bundle["manifest"]["flagged_synthetic_samples"] == 2
    assert bundle["manifest"]["schema_version"] == 1
    assert bundle["dataset"]["runs"][0]["integrity"]["sample_count"] == 2
    encoded = json.dumps(bundle["dataset"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == bundle["manifest"]["dataset_sha256"]
