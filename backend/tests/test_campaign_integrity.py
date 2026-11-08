"""W19 campaign invariants against real disposable PostgreSQL and Mosquitto."""

import copy
import hashlib
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import DBAPIError

from coldguard_backend.campaign_integrity import assess_run, campaign_integrity, close_run, critical_window_report, live_integrity, run_closures
from coldguard_backend.campaign_store import CampaignCreate, campaign_runs, get_campaign, register_campaign
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.experiment_store import RunConflict, experiments, get_run
from coldguard_backend.ingest import ingest_message
from coldguard_backend.main import app, get_db_engine
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.raw_store import telemetry_raw
from tests.campaign_testkit import campaign_draft, complete_run, finish_run, register_fixture, send_sample, start_run
from tests.command_testkit import utcnow


@pytest.mark.parametrize("mutation,match", [
    ("duplicate_run", "run IDs must be distinct"), ("missing_arm", "both A and B"),
    ("wrong_controller", "canonical controller"), ("missing_version", "version references"),
    ("conflicting_hardware", "conflicting physical"), ("invalid_window", "positive duration"),
    ("duplicate_event", "event types must be distinct"), ("unsupported_schema", "schema_version 1"),
])
def test_campaign_plan_rejects_identity_and_version_conflicts(mutation, match):
    draft = campaign_draft()
    if mutation == "duplicate_run":
        draft["runs"][1]["run"]["run_id"] = draft["runs"][0]["run"]["run_id"]
    elif mutation == "missing_arm":
        draft["runs"][1]["run"]["pair_id"] = "unrelated-pair"
    elif mutation == "wrong_controller":
        draft["runs"][1]["run"]["controller_id"] = "REACTIVE"
    elif mutation == "missing_version":
        del draft["runs"][0]["run"]["versions"]["model_version"]
    elif mutation == "conflicting_hardware":
        draft["runs"][1]["run"]["versions"]["hardware_config_id"] = "different"
    elif mutation == "invalid_window":
        draft["runs"][0]["critical_windows"][0]["end_offset_sec"] = 0.5
    elif mutation == "duplicate_event":
        draft["runs"][0]["required_events"].append("DOOR_OPENED")
    else:
        draft["runs"][0]["run"]["versions"]["schema_version"] = 99
    with pytest.raises(ValidationError, match=match):
        CampaignCreate.model_validate(draft)


def test_missing_window_has_no_interpolation_or_invented_sample():
    windows = [{"window_id": "critical", "start_offset_sec": 0.0, "end_offset_sec": 3.0, "max_gap_sec": 1.0}]
    report = critical_window_report([], utcnow(), windows)[0]
    assert report["missing"] is True and report["sample_count"] == 0
    assert report["interpolated_samples"] == 0
    assert report["gaps"][0]["duration_sec"] == 3.0


def test_namespace_retries_are_idempotent_and_conflicting_registration_rolls_back(db_engine):
    context = register_fixture(db_engine)
    draft = context["draft"]
    with db_engine.begin() as connection:
        again = register_campaign(connection, CampaignCreate.model_validate(draft))
        assert again == context["campaign"]
    changed = copy.deepcopy(draft)
    changed["runs"][1]["run"]["versions"]["policy_version"] = "changed-policy"
    with pytest.raises(RunConflict, match="different frozen namespace"):
        with db_engine.begin() as connection:
            register_campaign(connection, CampaignCreate.model_validate(changed))
    changed["campaign_id"] += "-other"
    with pytest.raises(RunConflict, match="another campaign"):
        with db_engine.begin() as connection:
            register_campaign(connection, CampaignCreate.model_validate(changed | {"runs": draft["runs"]}))
    with db_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(campaign_runs).where(campaign_runs.c.campaign_id == draft["campaign_id"])) == 2


def test_namespace_and_associated_run_versions_are_db_immutable(db_engine):
    context = register_fixture(db_engine)
    run_id = context["draft"]["runs"][0]["run"]["run_id"]
    for values in ({"pair_id": "wrong-pair"}, {"controller_id": "PREDICTIVE"}, {"versions": {"schema_version": 1}}):
        with pytest.raises(DBAPIError, match="identity and versions are frozen"):
            with db_engine.begin() as connection:
                connection.execute(experiments.update().where(experiments.c.run_id == run_id).values(**values))
    with pytest.raises(DBAPIError, match="immutable"):
        with db_engine.begin() as connection:
            connection.execute(campaign_runs.delete().where(campaign_runs.c.run_id == run_id))


def test_valid_synthetic_campaign_closes_without_automatic_validity_approval(db_engine):
    context = register_fixture(db_engine)
    campaign_id = context["draft"]["campaign_id"]
    for arm in ("A", "B"):
        run = complete_run(context, arm)
        with db_engine.begin() as connection:
            closed = close_run(connection, campaign_id, run["run_id"], reason="SOFTWARE_SIMULATION block close")
            assert closed["report"]["normalized_count"] == 4
            assert closed["report"]["raw_count"] == 6
            assert closed["report"]["assessment"] == "SOFTWARE_INTEGRITY_CLEAR"
            assert closed["report"]["automatic_validity_approval"] is False
            assert closed["report"]["physical_acceptance"] == "BLOCKED_EXTERNAL"
            assert hashlib.sha256(encode_evidence(closed["report"])).hexdigest() == closed["report_sha256"]
            assert close_run(connection, campaign_id, run["run_id"], reason="retry") == closed
    with db_engine.connect() as connection:
        assert campaign_integrity(connection, campaign_id)["backup_ready"] is True


def test_missing_primary_window_and_events_are_preserved_for_doc03_review(db_engine):
    context = register_fixture(db_engine)
    run = complete_run(context, sequences=(1, 4), events=False, final_status="INVALID")
    with db_engine.begin() as connection:
        closed = close_run(connection, context["draft"]["campaign_id"], run["run_id"], reason="Doc03 telemetry gap covers primary event")
        report = closed["report"]
        assert report["normalized_count"] == 2
        assert report["integrity"]["sequence_gaps"] == [{"boot_id": "software-boot-" + run["run_id"], "first_missing": 2, "last_missing": 3}]
        assert {issue["code"] for issue in report["issues"]} >= {"MISSING_CRITICAL_WINDOW", "MISSING_REQUIRED_EVENTS"}
        assert report["critical_windows"][0]["interpolated_samples"] == 0
        assert get_run(connection, run["run_id"])["status"] == "INVALID"


def test_raw_duplicate_conflict_wrong_run_and_wrong_pair_remain_visible(db_engine):
    context = register_fixture(db_engine)
    run = complete_run(context)
    sample, result = send_sample(context, run, 1)
    assert result["normalized"]["outcome"] == "exact_duplicate"
    with db_engine.connect() as connection:
        report = assess_run(connection, context["campaign"], run["run_id"])
        assert not report["issues"]
        assert report["integrity"]["duplicate_identities"][0]["raw_deliveries"] == 2
    _, result = send_sample(context, run, 1, run_id="unrelated-run", pair_id="unrelated-pair", firmware_version="conflicting-fw")
    assert result["normalized"]["outcome"] == "conflict"
    with db_engine.connect() as connection:
        report = assess_run(connection, context["campaign"], run["run_id"])
        assert {issue["code"] for issue in report["issues"]} >= {"CONFLICTING_IDENTITY", "WRONG_ASSOCIATION"}
        assert report["raw_count"] == 8 and report["normalized_count"] == 4
        winner = connection.execute(select(telemetry).where(telemetry.c.raw_id == result["raw_id"])).first()
        assert winner is None
        assert connection.scalar(select(telemetry_raw.c.id).where(telemetry_raw.c.id == result["raw_id"])) == result["raw_id"]


def test_live_monitor_separates_acquisition_age_from_late_ingestion_and_errors(db_engine):
    context = register_fixture(db_engine)
    run = start_run(context)
    sample, _ = send_sample(context, run, 1)
    # A delayed exact redelivery cannot renew the latest acquisition age.
    ingest_message(db_engine, topic=f"coldguard/{run['device_id']}/telemetry", payload=json.dumps(sample).encode(), received_at=utcnow())
    ingest_message(db_engine, topic=f"coldguard/{run['device_id']}/telemetry", payload=json.dumps(sample | {"schema_version": 99, "seq": 2}).encode(), received_at=utcnow())
    monitor = live_integrity(db_engine, context["draft"]["campaign_id"], now=context["started"] + timedelta(seconds=20))
    first = next(row for row in monitor["runs"] if row["run_id"] == run["run_id"])
    assert monitor["database_health"] == "HEALTHY" and monitor["ingestion"] == {"status": "NOT_OBSERVED"}
    assert first["last_sample_age_sec"] == 19.0 and first["sample_stale"] is True
    assert first["schema_mismatches"] == 1 and first["message_errors"] == 1


def test_interrupted_normalization_leaves_raw_evidence_and_refuses_ready_backup(db_engine, monkeypatch):
    context = register_fixture(db_engine)
    run = start_run(context)
    def interrupted(*_args, **_kwargs):
        raise RuntimeError("simulated normalization interruption")
    monkeypatch.setattr("coldguard_backend.ingest.insert_normalized", interrupted)
    _, result = send_sample(context, run, 1)
    assert result["normalized"] == "failed"
    finish_run(context, run, final_status="INVALID")
    with db_engine.begin() as connection:
        report = close_run(connection, context["draft"]["campaign_id"], run["run_id"], reason="interrupted ingestion")
        assert report["report"]["raw_count"] == 1 and report["report"]["normalized_count"] == 0
        assert "NORMALIZATION_INCOMPLETE" in {issue["code"] for issue in report["report"]["issues"]}
        assert campaign_integrity(connection, context["draft"]["campaign_id"])["backup_ready"] is False


def test_running_close_is_rejected_and_late_evidence_creates_new_immutable_report(db_engine):
    context = register_fixture(db_engine)
    run_id = context["draft"]["runs"][0]["run"]["run_id"]
    with pytest.raises(RunConflict, match="completed raw"):
        with db_engine.begin() as connection:
            close_run(connection, context["draft"]["campaign_id"], run_id, reason="too early")
    run = complete_run(context)
    with db_engine.begin() as connection:
        first = close_run(connection, context["draft"]["campaign_id"], run_id, reason="first close")
    send_sample(context, run, 3)
    with db_engine.begin() as connection:
        second = close_run(connection, context["draft"]["campaign_id"], run_id, reason="explicit late receipt assessment")
        assert second["closure_id"] != first["closure_id"]
        assert connection.scalar(select(func.count()).select_from(run_closures).where(run_closures.c.run_id == run_id)) == 2
    with pytest.raises(DBAPIError, match="immutable"):
        with db_engine.begin() as connection:
            connection.execute(run_closures.update().where(run_closures.c.closure_id == first["closure_id"]).values(reason="silent repair"))


def test_campaign_api_is_read_only_and_has_real_db_health(db_engine):
    context = register_fixture(db_engine)
    app.dependency_overrides[get_db_engine] = lambda: db_engine
    try:
        client = TestClient(app)
        path = "/api/campaigns/" + context["draft"]["campaign_id"]
        assert client.get(path).json()["data_class"] == "SOFTWARE_SIMULATION"
        assert client.post(path).status_code == 405
        assert client.get(path + "/integrity").json()["database_health"] == "HEALTHY"
        assert client.get(path + "/closures", params={"limit": 0}).status_code == 422
        assert client.get("/api/campaigns/unknown").status_code == 404
    finally:
        app.dependency_overrides.pop(get_db_engine, None)


def test_database_unavailable_monitor_fails_closed_without_credentials():
    import socket
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    engine = create_engine(f"postgresql+psycopg://unused:private@127.0.0.1:{port}/disposable", connect_args={"connect_timeout": 1})
    try:
        report = live_integrity(engine, "software-test")
        assert report["database_health"] == "UNAVAILABLE" and report["backup_ready"] is False
        assert report["runs"] is None and "private" not in json.dumps(report, default=str)
    finally:
        engine.dispose()


@pytest.mark.skipif(not __import__("os").environ.get("COLDGUARD_TEST_MQTT_HOST"), reason="requires a disposable authenticated Mosquitto broker")
def test_live_campaign_ingestion_over_real_mqtt_and_stopped_consumer(db_engine):
    from coldguard_backend.mqtt_consumer import MqttIngestConsumer
    from coldguard_backend.simulator import build_event, build_telemetry
    from tests.mqtt_testkit import make_test_config, mqtt_params, wait_for
    from tests.test_broker_security import _Probe

    draft = campaign_draft()
    for plan in draft["runs"]:
        plan["run"]["device_id"] = "coldguard-001"
    context = register_fixture(db_engine, draft)
    run = start_run(context)
    params = mqtt_params()
    consumer = MqttIngestConsumer.from_config(make_test_config(
        mqtt_user=params["backend_user"], mqtt_password=params["backend_password"],
    ))
    publisher = _Probe(username=params["device_user"], password=params["device_password"])
    try:
        consumer.start()
        for seq in (1, 2, 3, 4):
            sample = build_telemetry(device_id=run["device_id"], boot_id="software-mqtt", seq=seq,
                                     run_id=run["run_id"], base_time=context["started"])
            sample["calibration_id"] = "SOFTWARE_SIMULATION"
            publisher.publish_sync(f"coldguard/{run['device_id']}/telemetry", json.dumps(sample).encode())
        for seq, event_type in ((2, "DOOR_OPENED"), (4, "DOOR_CLOSED")):
            event = build_event(device_id=run["device_id"], boot_id="software-mqtt", seq=seq,
                                run_id=run["run_id"], event_type=event_type, base_time=context["started"])
            publisher.publish_sync(f"coldguard/{run['device_id']}/event", json.dumps(event).encode())
        def fully_ingested():
            with db_engine.connect() as connection:
                return assess_run(connection, context["campaign"], run["run_id"])["raw_count"] == 6
        assert wait_for(fully_ingested, timeout_s=10)
        finish_run(context, run)
        with db_engine.begin() as connection:
            assert close_run(connection, draft["campaign_id"], run["run_id"], reason="SOFTWARE_SIMULATION real MQTT ingestion")["report"]["assessment"] == "SOFTWARE_INTEGRITY_CLEAR"
        report = live_integrity(db_engine, draft["campaign_id"], ingestion=consumer.snapshot())
        assert report["ingestion"]["broker_connected"] is True and report["ingestion"]["subscribed"] is True
        consumer.stop()
        report = live_integrity(db_engine, draft["campaign_id"], ingestion=consumer.snapshot())
        assert report["ingestion"]["broker_connected"] is False
    finally:
        consumer.stop()
        publisher.close()
