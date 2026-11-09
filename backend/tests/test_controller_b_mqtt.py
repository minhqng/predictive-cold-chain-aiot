"""Actual loopback Mosquitto failure windows with a software device peer.

Live-shaped telemetry and signed test-key approvals are generated solely to
exercise software contracts. The peer observes messages; it never actuates
hardware. Broker PUBACK/device ACK are never physical verification evidence.
"""

import hashlib
import hmac
import json
import secrets
import threading
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from coldguard_backend import command_store as cs
from coldguard_backend.ack_consumer import AckConsumer
from coldguard_backend.command_authorization import CommandAccessDenied
from coldguard_backend.command_publisher import PahoCommandTransport, command_topic
from coldguard_backend.controller_b import DPolicyAuthority, policy_approvals
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.experiment_store import (
    RunCreate, RunTransition, create_run, experiment_transitions, experiments, transition_run,
)
from coldguard_backend.ingest import ingest_message
from coldguard_backend.main import app, get_db_engine
from coldguard_backend.mqtt_consumer import MqttIngestConsumer
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.physical_verification import physical_assessments
from coldguard_backend.prediction_store import prediction_inputs, predictions, record_prediction
from coldguard_backend.raw_store import telemetry_raw
from coldguard_backend.recovery import reconcile_command_history
from coldguard_backend.twin_store import device_twin
from tests.command_testkit import ack_bytes, cleanup_commands, make_ack, make_command, utcnow
from tests.mqtt_testkit import has_test_db, has_test_mqtt, make_test_config, mqtt_params, wait_for
from tests.test_command_publisher import _connect, publisher_client  # noqa: F401
from tests.test_controller_b import SOFTWARE_MODEL, _dispatcher
from tests.test_migration_w05 import _cleanup_device
from tests.test_predictions import _draft
from tests.test_twin import _payload

pytestmark = pytest.mark.skipif(
    not (has_test_db() and has_test_mqtt()), reason="requires real PostgreSQL and disposable Mosquitto",
)


@pytest.fixture
def wire_case(db_engine):
    suffix, device = uuid4().hex, "coldguard-001"
    run_id = "software-w18-wire-" + suffix
    with db_engine.begin() as connection:
        assert connection.scalar(select(device_twin.c.device_id).where(device_twin.c.device_id == device)) is None
        create_run(connection, RunCreate(
            run_id=run_id, device_id=device, scenario_id="S2", controller_id="PREDICTIVE",
            pair_id="software-wire-pair", versions={
                "model_version": SOFTWARE_MODEL.model_version, "feature_version": SOFTWARE_MODEL.feature_version,
                "policy_version": "software-d-approval", "schema_version": 1,
            }, notes="Generated loopback broker fixture; no physical campaign or approval.",
        ))
        for status in ("ARMED", "RUNNING"):
            transition_run(connection, run_id, RunTransition(status=status))
    received = utcnow()
    sample = _payload(device, 1, run_id=run_id, captured_at=received.isoformat())
    result = ingest_message(db_engine, topic=f"coldguard/{device}/telemetry",
                            payload=json.dumps(sample).encode(), received_at=received)
    draft = _draft(device, run_id, [result["normalized"]["id"]], received)
    with db_engine.begin() as connection:
        record_prediction(connection, draft)
        version = connection.scalar(select(device_twin.c.twin_version).where(device_twin.c.device_id == device))
    command = make_command(
        "software-w18-command-" + suffix, device_id=device, run_id=run_id, ttl_s=15,
        controller_id="PREDICTIVE", prediction_id=draft.prediction_id,
        policy_version="software-d-approval", expected_twin_version=version,
    )
    token, key = secrets.token_urlsafe(32), secrets.token_bytes(32)
    authority = DPolicyAuthority(command.policy_version, key)
    signature = hmac.digest(key, cs.canonical_command_bytes(command), "sha256").hex()
    app.dependency_overrides[get_db_engine] = lambda: db_engine
    try:
        yield TestClient(app), command, token, authority, signature
    finally:
        app.dependency_overrides.pop(get_db_engine, None)
        with db_engine.begin() as connection:
            for table in (physical_assessments, policy_approvals):
                connection.execute(table.delete().where(table.c.command_id == command.command_id))
        cleanup_commands(db_engine, device)
        with db_engine.begin() as connection:
            ids = select(predictions.c.prediction_id).where(predictions.c.run_id == run_id)
            connection.execute(prediction_inputs.delete().where(prediction_inputs.c.prediction_id.in_(ids)))
            connection.execute(predictions.delete().where(predictions.c.run_id == run_id))
            connection.execute(experiment_transitions.delete().where(experiment_transitions.c.run_id == run_id))
            connection.execute(experiments.delete().where(experiments.c.run_id == run_id))
        _cleanup_device(db_engine, device)


@contextmanager
def _device_session(topic):
    params = mqtt_params()
    assert params["host"] in {"127.0.0.1", "localhost", "::1"}
    client = _connect(params["device_user"], params["device_password"], "software-w18-peer-" + uuid4().hex)
    received, suback = [], []
    subscribed, message_arrived = threading.Event(), threading.Event()

    def on_message(_client, _userdata, message):
        received.append(message)
        message_arrived.set()

    def on_subscribe(_client, _userdata, _mid, reasons, _properties):
        suback.extend(code.value for code in reasons)
        subscribed.set()

    client.on_message, client.on_subscribe = on_message, on_subscribe
    try:
        client.subscribe(topic, qos=1)
        assert subscribed.wait(5) and suback == [1]
        yield client, received, message_arrived
    finally:
        client.disconnect()
        client.loop_stop()


def _send(client, topic, payload):
    result = client.publish(topic, payload, qos=1, retain=False)
    result.wait_for_publish(timeout=5)
    assert result.is_published()


def _save_trace(client, command, tmp_path, evidence):
    path = f"/api/runs/{command.run_id}/controller-b-trace"
    first = client.get(path, params={"download": True})
    assert first.status_code == 200
    assert first.content == client.get(path, params={"download": True}).content
    trace = first.json()["commands"][0]
    assert trace["command"]["prediction_id"] == trace["prediction"]["prediction_id"] == command.prediction_id
    assert trace["policy_approval"]["command_sha256"] == cs.command_payload_sha256(command)
    assert trace["physical_response_status"] == "UNAVAILABLE"
    assert trace["physical_assessments"] == []
    (tmp_path / "controller-b-software-wire-trace.json").write_bytes(first.content)
    (tmp_path / "controller-b-software-wire-proof.json").write_bytes(encode_evidence({
        "data_class": "SOFTWARE_SIMULATION", "providers": "real loopback PostgreSQL and Mosquitto",
        "device_peer": "generated contract peer; no physical actuation", "evidence": evidence,
        "trace_sha256": hashlib.sha256(first.content).hexdigest(),
    }))
    return trace


def test_lost_ack_and_device_reconnect_do_not_repeat_predictive_dispatch(db_engine, wire_case, publisher_client, tmp_path):
    client, command, token, authority, signature = wire_case
    transport = PahoCommandTransport(publisher_client)
    service = _dispatcher(db_engine, command, token, authority, transport)
    with _device_session(command_topic(command.device_id)) as (_, received, message):
        assert service.dispatch(command, backend_token=token, approval_signature=signature)["outcome"] == "puback"
        assert message.wait(5)
        assert len(received) == 1 and received[0].qos == 1 and received[0].retain is False
        assert received[0].payload == cs.canonical_command_bytes(command)
        # Intentionally omit the device ACK despite real broker delivery.
        assert service.dispatch(command, backend_token=token, approval_signature=signature)["outcome"] == "not_publishable"
    with _device_session(command_topic(command.device_id)) as (_, after_reconnect, message):
        assert reconcile_command_history(db_engine) == {"uncertain_commands": [], "expired_commands": []}
        assert service.dispatch(command, backend_token=token, approval_signature=signature)["outcome"] == "not_publishable"
        assert not message.wait(0.25) and after_reconnect == []
    recovery = client.get(f"/api/devices/{command.device_id}/recovery").json()
    assert recovery["desired"]["status"] == cs.PUBLISHED and recovery["pending_attempts"] == 0
    assert recovery["latest_ack_receipt"] is None
    trace = _save_trace(client, command, tmp_path, {
        "failure_windows": ["lost_device_ack", "device_disconnect_reconnect"],
        "first_session_command_messages": 1, "reconnected_session_command_messages": 0,
    })
    assert len(trace["attempts"]) == 1 and trace["attempts"][0]["outcome"] == "PUBACK"
    assert trace["acks"] == [] and trace["command"]["verification_status"] == "NONE"


def test_delayed_broker_telemetry_keeps_acquisition_and_never_verifies_ack(db_engine, wire_case, publisher_client, tmp_path):
    client, command, token, authority, signature = wire_case
    params = mqtt_params()
    config = make_test_config(mqtt_user=params["backend_user"], mqtt_password=params["backend_password"])
    ack_consumer = AckConsumer(config, client_id="software-w18-ack-" + uuid4().hex)
    telemetry_consumer = MqttIngestConsumer(config, client_id="software-w18-ingest-" + uuid4().hex)
    transport = PahoCommandTransport(publisher_client)
    service = _dispatcher(db_engine, command, token, authority, transport)

    def command_row():
        with db_engine.connect() as connection:
            return cs.get_command(connection, command.command_id)

    def delayed_row():
        with db_engine.connect() as connection:
            row = connection.execute(select(telemetry).where(
                telemetry.c.run_id == command.run_id, telemetry.c.seq == 2,
            )).mappings().one_or_none()
            return dict(row) if row else None

    try:
        ack_consumer.start()
        telemetry_consumer.start()
        with _device_session(command_topic(command.device_id)) as (peer, received, message):
            assert service.dispatch(command, backend_token=token, approval_signature=signature)["outcome"] == "puback"
            assert message.wait(5) and len(received) == 1
            _send(peer, f"coldguard/{command.device_id}/command_ack", ack_bytes(make_ack(
                command.command_id, device_id=command.device_id, boot_id="boot-z",
            )))
            assert wait_for(lambda: command_row()["status"] == cs.ACK_ACCEPTED, timeout_s=5)
            acquired = command.created_at - timedelta(hours=1)
            sample = _payload(command.device_id, 2, run_id=command.run_id, captured_at=acquired.isoformat(),
                              actuation={"cooling": "ON", "duty": 0.5})
            _send(peer, f"coldguard/{command.device_id}/telemetry", json.dumps(sample).encode())
            assert wait_for(lambda: delayed_row() is not None, timeout_s=5)
            row = delayed_row()
            assert row["time"] == acquired
            assert row["backend_received_at"] > command.created_at
            assert (row["backend_received_at"] - row["time"]).total_seconds() >= 3600
            assert command_row()["status"] == cs.ACK_ACCEPTED
            assert command_row()["verification_status"] == "NONE"
            with pytest.raises(CommandAccessDenied):
                service.dispatch(command, backend_token=token, approval_signature=signature)
            assert len(received) == 1
        trace = _save_trace(client, command, tmp_path, {
            "failure_windows": ["delayed_telemetry"], "acquired_at": row["time"],
            "received_at": row["backend_received_at"], "command_messages": 1,
            "ack_is_protocol_only": True, "physical_verification": "UNAVAILABLE",
        })
        assert len(trace["attempts"]) == 1 and len(trace["acks"]) == 1
        assert trace["command"]["status"] == cs.ACK_ACCEPTED
        with db_engine.connect() as connection:
            source = connection.execute(select(telemetry_raw).where(telemetry_raw.c.id == row["raw_id"])).mappings().one()
            assert hashlib.sha256(source["raw_payload"].encode()).hexdigest() == source["payload_sha256"]
        assert ack_consumer.snapshot()["errors"] == 0 and telemetry_consumer.snapshot()["errors"] == 0
    finally:
        telemetry_consumer.stop()
        ack_consumer.stop()
