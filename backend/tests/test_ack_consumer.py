"""ACK consumer proofs against a real disposable Mosquitto (C-W06-03).

Requires COLDGUARD_TEST_DATABASE_URL and COLDGUARD_TEST_MQTT_HOST. A real
backend AckConsumer subscribes to command_ack; a contract-compatible mock
device publishes synthetic ACKs. Verifies correlation, durable evidence,
quarantine of malformed/invalid/topic-mismatched/unmatched ACKs, idempotent
duplicates and late-ACK expiry arbitration. No physical hardware is used.
"""

import json
import os
import threading
from datetime import timedelta

import paho.mqtt.client as mqtt
import pytest
from sqlalchemy import create_engine

from coldguard_backend import command_store as cs
from coldguard_backend.ack_consumer import AckConsumer, classify_ack
from tests.command_testkit import (
    ack_bytes,
    ack_topic,
    cleanup_commands,
    make_ack,
    make_command,
    utcnow,
)
from tests.mqtt_testkit import (
    has_test_db,
    has_test_mqtt,
    make_test_config,
    mqtt_params,
    wait_for,
)

needs_providers = pytest.mark.skipif(
    not (has_test_db() and has_test_mqtt()),
    reason="requires COLDGUARD_TEST_DATABASE_URL and COLDGUARD_TEST_MQTT_HOST",
)


def _backend_consumer() -> AckConsumer:
    params = mqtt_params()
    return AckConsumer.from_config(
        make_test_config(mqtt_user=params["backend_user"], mqtt_password=params["backend_password"])
    )


@pytest.fixture
def device_publisher():
    params = mqtt_params()
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id="w06-ack-device", protocol=mqtt.MQTTv5
    )
    client.username_pw_set(params["device_user"], params["device_password"])
    connected = threading.Event()
    client.on_connect = lambda *a, **k: connected.set()
    client.connect(params["host"], params["port"], keepalive=30)
    client.loop_start()
    connected.wait(timeout=10)
    yield client
    client.loop_stop()
    client.disconnect()


def _publish_ack(client, payload: bytes, topic: str | None = None):
    info = client.publish(topic or ack_topic(), payload, qos=1)
    info.wait_for_publish(timeout=10)


def _prepare_published_command(engine, command_id: str, **kw):
    with engine.begin() as conn:
        cs.create_command(conn, make_command(command_id, **kw))
        cs.transition_command(conn, command_id, cs.PUBLISHED)


def _command_status(engine, command_id: str) -> str:
    with engine.begin() as conn:
        return cs.get_command(conn, command_id)["status"]


def _evidence(engine, command_id: str):
    with engine.begin() as conn:
        return conn.execute(
            cs.command_acks.select().where(cs.command_acks.c.command_id == command_id)
        ).mappings().all()


def test_classify_ack_pure_variants():
    valid = ack_bytes(make_ack("cmd-1"))
    assert classify_ack(ack_topic(), valid)["validity"] == "VALID"
    assert classify_ack(ack_topic(), b"{bad")["validity"] == "MALFORMED_JSON"
    bad_schema = json.dumps({**make_ack("cmd-1").model_dump(mode="json"), "uptime_ms": "x"}).encode()
    assert classify_ack(ack_topic(), bad_schema)["validity"] == "INVALID_SCHEMA"
    forged = ack_bytes(make_ack("cmd-1", device_id="other-device"))
    assert classify_ack(ack_topic(), forged)["validity"] == "TOPIC_MISMATCH"


def test_app_ack_ingestion_disabled_by_default(monkeypatch):
    from fastapi.testclient import TestClient
    from coldguard_backend.main import app

    monkeypatch.delenv("COLDGUARD_MQTT_ACK_INGEST", raising=False)
    monkeypatch.delenv("COLDGUARD_MQTT_INGEST", raising=False)
    with TestClient(app):
        assert app.state.ack_consumer is None


def _enable_app_ack(monkeypatch):
    from urllib.parse import urlsplit

    params = mqtt_params()
    db = urlsplit(os.environ["COLDGUARD_TEST_DATABASE_URL"])
    monkeypatch.delenv("COLDGUARD_MQTT_INGEST", raising=False)
    for name, value in {
        "COLDGUARD_PROFILE": "integration",
        "COLDGUARD_MQTT_ACK_INGEST": "true",
        "POSTGRES_HOST": db.hostname,
        "POSTGRES_PORT": db.port,
        "POSTGRES_DB": db.path.lstrip("/"),
        "POSTGRES_USER": db.username,
        "POSTGRES_PASSWORD": db.password or "",
        "MQTT_HOST": params["host"],
        "MQTT_PORT": params["port"],
        "MQTT_USERNAME": params["backend_user"],
        "MQTT_PASSWORD": params["backend_password"],
    }.items():
        monkeypatch.setenv(name, str(value))


@needs_providers
def test_app_ack_starts_subscribed_and_stops(db_engine, device_publisher, monkeypatch):
    from fastapi.testclient import TestClient
    from coldguard_backend.main import app

    cleanup_commands(db_engine)
    _enable_app_ack(monkeypatch)
    try:
        with TestClient(app):
            consumer = app.state.ack_consumer
            assert consumer.snapshot()["subscribed"]
            _prepare_published_command(db_engine, "cmd-app-ack")
            _publish_ack(device_publisher, ack_bytes(make_ack("cmd-app-ack")))
            assert wait_for(
                lambda: _command_status(db_engine, "cmd-app-ack") == cs.ACK_ACCEPTED,
                timeout_s=5,
            )
        assert not consumer.running
        assert not consumer.snapshot()["subscribed"]
        assert consumer._engine is None
    finally:
        cleanup_commands(db_engine)


@needs_providers
@pytest.mark.parametrize("bad_target", ["credentials", "database"])
def test_app_ack_startup_fails_closed(db_engine, monkeypatch, bad_target):
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import OperationalError
    from coldguard_backend.main import app

    _enable_app_ack(monkeypatch)
    if bad_target == "credentials":
        monkeypatch.setenv("MQTT_PASSWORD", "invalid-test-password")
        error, message = ConnectionError, "authentication refused"
    else:
        monkeypatch.setenv("POSTGRES_DB", "nonexistent_coldguard_db")
        error, message = OperationalError, "does not exist"
    with pytest.raises(error, match=message):
        with TestClient(app):
            pytest.fail("ACK startup should fail before serving")


@needs_providers
def test_app_ack_startup_fails_for_unreachable_broker(db_engine, monkeypatch):
    import socket
    from fastapi.testclient import TestClient
    from coldguard_backend.main import app

    _enable_app_ack(monkeypatch)
    # Reserve a loopback port without listening so no other provider is contacted.
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        monkeypatch.setenv("MQTT_HOST", "127.0.0.1")
        monkeypatch.setenv("MQTT_PORT", str(unused.getsockname()[1]))
        with pytest.raises(TimeoutError, match="broker unreachable"):
            with TestClient(app):
                pytest.fail("ACK startup should fail before serving")


@needs_providers
def test_valid_ack_correlates_and_transitions(db_engine, device_publisher):
    cleanup_commands(db_engine)
    consumer = _backend_consumer()
    consumer.start()
    assert consumer.wait_subscribed(10)
    try:
        _prepare_published_command(db_engine, "cmd-ack-ok")
        _publish_ack(device_publisher, ack_bytes(make_ack("cmd-ack-ok", "ACCEPTED")))
        assert wait_for(lambda: _command_status(db_engine, "cmd-ack-ok") == cs.ACK_ACCEPTED, timeout_s=10)
        evidence = _evidence(db_engine, "cmd-ack-ok")
        assert any(e["validity"] == "VALID" for e in evidence)
        with db_engine.begin() as conn:
            row = cs.get_command(conn, "cmd-ack-ok")
        assert row["verification_status"] == "NONE"  # ACK is not physical proof
    finally:
        consumer.stop()
        cleanup_commands(db_engine)


@needs_providers
@pytest.mark.parametrize(
    "payload",
    [b"{not json", b"[" * 5000 + b"0" + b"]" * 5000, b"9" * 4500],
    ids=["syntax", "nesting-limit", "integer-limit"],
)
def test_malformed_ack_retained_without_transition(db_engine, device_publisher, payload):
    cleanup_commands(db_engine)
    consumer = _backend_consumer()
    consumer.start()
    assert consumer.wait_subscribed(10)
    try:
        _prepare_published_command(db_engine, "cmd-bad-json")
        _publish_ack(device_publisher, payload)
        assert wait_for(lambda: consumer.metrics.snapshot()["malformed_json"] >= 1, timeout_s=10)
        assert _command_status(db_engine, "cmd-bad-json") == cs.PUBLISHED
        with db_engine.begin() as conn:
            rows = conn.execute(
                cs.command_acks.select().where(cs.command_acks.c.validity == "MALFORMED_JSON")
            ).mappings().all()
        assert any(row["raw_payload"] == payload.decode("utf-8") for row in rows)
        _publish_ack(device_publisher, ack_bytes(make_ack("cmd-bad-json", "ACCEPTED")))
        assert wait_for(lambda: _command_status(db_engine, "cmd-bad-json") == cs.ACK_ACCEPTED, timeout_s=10)
    finally:
        consumer.stop()
        cleanup_commands(db_engine)


@needs_providers
def test_topic_mismatch_ack_quarantined(db_engine, device_publisher):
    cleanup_commands(db_engine)
    consumer = _backend_consumer()
    consumer.start()
    assert consumer.wait_subscribed(10)
    try:
        _prepare_published_command(db_engine, "cmd-forged")
        # Device publishes on its own topic but forges a different payload device.
        forged = ack_bytes(make_ack("cmd-forged", device_id="other-device"))
        _publish_ack(device_publisher, forged)
        assert wait_for(lambda: consumer.metrics.snapshot()["topic_mismatch"] >= 1, timeout_s=10)
        assert _command_status(db_engine, "cmd-forged") == cs.PUBLISHED
    finally:
        consumer.stop()
        cleanup_commands(db_engine)


@needs_providers
def test_unmatched_ack_quarantined(db_engine, device_publisher):
    cleanup_commands(db_engine)
    consumer = _backend_consumer()
    consumer.start()
    assert consumer.wait_subscribed(10)
    try:
        _publish_ack(device_publisher, ack_bytes(make_ack("ghost-ack", "ACCEPTED")))
        assert wait_for(lambda: consumer.metrics.snapshot()["unmatched"] >= 1, timeout_s=10)
        with db_engine.begin() as conn:
            row = conn.execute(
                cs.command_acks.select().where(cs.command_acks.c.command_id == "ghost-ack")
            ).mappings().one()
        assert row["validity"] == "UNMATCHED"
    finally:
        consumer.stop()
        cleanup_commands(db_engine)


@needs_providers
def test_duplicate_ack_idempotent(db_engine, device_publisher):
    cleanup_commands(db_engine)
    consumer = _backend_consumer()
    consumer.start()
    assert consumer.wait_subscribed(10)
    try:
        _prepare_published_command(db_engine, "cmd-dup-ack")
        payload = ack_bytes(make_ack("cmd-dup-ack", "ACCEPTED"))
        _publish_ack(device_publisher, payload)
        assert wait_for(lambda: _command_status(db_engine, "cmd-dup-ack") == cs.ACK_ACCEPTED, timeout_s=10)
        _publish_ack(device_publisher, payload)
        assert wait_for(lambda: consumer.metrics.snapshot()["duplicate"] >= 1, timeout_s=10)
        with db_engine.begin() as conn:
            transitions = conn.execute(
                cs.command_transitions.select().where(
                    cs.command_transitions.c.command_id == "cmd-dup-ack",
                    cs.command_transitions.c.to_status == cs.ACK_ACCEPTED,
                )
            ).all()
        assert len(transitions) == 1
    finally:
        consumer.stop()
        cleanup_commands(db_engine)


@needs_providers
def test_late_ack_after_expiry_no_resurrection(db_engine, device_publisher):
    cleanup_commands(db_engine)
    consumer = _backend_consumer()
    consumer.start()
    assert consumer.wait_subscribed(10)
    try:
        now = utcnow()
        _prepare_published_command(
            db_engine, "cmd-late-ack", created_at=now - timedelta(minutes=10), ttl_s=60
        )
        with db_engine.begin() as conn:
            cs.expire_due_commands(conn, now=now)
        _publish_ack(device_publisher, ack_bytes(make_ack("cmd-late-ack", "ACCEPTED")))
        assert wait_for(lambda: consumer.metrics.snapshot()["late"] >= 1, timeout_s=10)
        assert _command_status(db_engine, "cmd-late-ack") == cs.EXPIRED
    finally:
        consumer.stop()
        cleanup_commands(db_engine)


@needs_providers
def test_refused_credentials_raise_connection_error():
    params = mqtt_params()
    consumer = AckConsumer.from_config(
        make_test_config(mqtt_user=params["backend_user"], mqtt_password="wrong-password")
    )
    with pytest.raises(ConnectionError):
        consumer.start()
    consumer.stop()


class _RecordingPahoClient:
    """Test double recording manual acknowledgements (never a real socket)."""

    def __init__(self):
        self.acked = []

    def ack(self, mid, qos):
        self.acked.append((mid, qos))


class _StubEngine:
    """Engine double whose transaction always opens and never touches a DB."""

    def begin(self):
        return self

    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


def _unit_config() -> "ColdGuardConfig":
    from coldguard_backend.config import ColdGuardConfig

    return ColdGuardConfig.load(
        env={
            "COLDGUARD_PROFILE": "integration",
            "POSTGRES_HOST": "127.0.0.1", "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "unavailable", "POSTGRES_USER": "n", "POSTGRES_PASSWORD": "n",
            "MQTT_HOST": "127.0.0.1", "MQTT_PORT": "1",
            "MQTT_USERNAME": "u", "MQTT_PASSWORD": "p",
        }
    )


def _unit_message(mid: int = 11):
    from types import SimpleNamespace

    return SimpleNamespace(
        mid=mid, qos=1, retain=False,
        topic=ack_topic(), payload=ack_bytes(make_ack("cmd-ack-unit")),
    )


def test_on_message_does_not_release_broker_when_evidence_commit_fails(monkeypatch):
    """Regression (W06): PUBACK must never precede the evidence transaction."""
    consumer = AckConsumer(_unit_config())
    consumer._engine = _StubEngine()
    client = _RecordingPahoClient()

    def failing(*args, **kwargs):
        raise RuntimeError("synthetic evidence outage")

    monkeypatch.setattr(cs, "record_ack", failing)
    consumer._on_message(client, None, _unit_message())
    snapshot = consumer.snapshot()
    assert client.acked == []  # absent before the fix: auto-PUBACK lost the evidence
    assert snapshot["errors"] == 1 and snapshot["received"] == 1


def test_on_message_releases_broker_once_after_evidence_commit(monkeypatch):
    consumer = AckConsumer(_unit_config())
    consumer._engine = _StubEngine()
    client = _RecordingPahoClient()
    monkeypatch.setattr(cs, "record_ack", lambda *args, **kwargs: {"outcome": "applied", "ack_id": 123})
    consumer._on_message(client, None, _unit_message(mid=11))
    assert client.acked == [(11, 1)]  # QoS 1 released exactly once, after the commit
    assert consumer.snapshot()["valid"] == 1


def test_on_message_counts_unknown_outcomes_as_errors_not_valid(monkeypatch):
    consumer = AckConsumer(_unit_config())
    consumer._engine = _StubEngine()
    client = _RecordingPahoClient()
    monkeypatch.setattr(cs, "record_ack", lambda *args, **kwargs: {"outcome": "brand-new", "ack_id": 1})
    consumer._on_message(client, None, _unit_message())
    snapshot = consumer.snapshot()
    assert snapshot["errors"] == 1 and snapshot["valid"] == 0
    assert client.acked == [(11, 1)]  # the evidence did commit, so the broker is released


@needs_providers
def test_ack_evidence_survives_db_outage_via_broker_redelivery(
    db_engine, device_publisher, monkeypatch
):
    """W06 durability contract: a DB outage during a valid ACK never loses evidence.

    With manual acknowledgement the failed delivery stays unacknowledged in the
    broker session; after the outage the consumer is restarted and the broker
    redelivers, persisting exactly one evidence row for the original bytes.
    """
    import hashlib

    cleanup_commands(db_engine)
    try:
        _prepare_published_command(db_engine, "cmd-ack-durable")
        payload = ack_bytes(make_ack("cmd-ack-durable"))
        digest = hashlib.sha256(payload).hexdigest()
        real_record_ack = cs.record_ack

        def failing(*args, **kwargs):
            raise RuntimeError("synthetic evidence outage")

        monkeypatch.setattr(cs, "record_ack", failing)
        consumer = _backend_consumer()
        consumer.start()
        try:
            _publish_ack(device_publisher, payload)
            assert wait_for(lambda: consumer.snapshot()["errors"] >= 1, timeout_s=10)
            assert _evidence(db_engine, "cmd-ack-durable") == []  # evidence not yet durable
        finally:
            consumer.stop()
        monkeypatch.setattr(cs, "record_ack", real_record_ack)
        consumer.start()  # broker resumes the session and redelivers the unacked QoS 1 ACK
        try:
            assert wait_for(
                lambda: _command_status(db_engine, "cmd-ack-durable") == cs.ACK_ACCEPTED,
                timeout_s=15,
            )
            rows = _evidence(db_engine, "cmd-ack-durable")
            assert [row["payload_sha256"] for row in rows] == [digest]
        finally:
            consumer.stop()
    finally:
        cleanup_commands(db_engine)
