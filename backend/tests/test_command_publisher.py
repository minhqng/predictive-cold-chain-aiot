"""Command publisher proofs against a real disposable Mosquitto (C-W06-02).

Requires COLDGUARD_TEST_DATABASE_URL and COLDGUARD_TEST_MQTT_HOST. Verifies
QoS 1 / retain=false on the wire, stable command_id retry, the pre-publish
expiry gate, durable failure/unknown outcomes, crash-window reconciliation and
concurrent-publisher fencing. The broker is disposable; no hardware is involved.
"""

import json
import os
import threading
from datetime import timedelta

import paho.mqtt.client as mqtt
import pytest
from sqlalchemy import create_engine

from coldguard_backend import command_store as cs
from coldguard_backend.command_publisher import (
    COMMAND_QOS,
    COMMAND_RETAIN,
    CommandPublisher,
    PahoCommandTransport,
    PublishResult,
    command_topic,
)
from tests.command_testkit import cleanup_commands, make_command, utcnow
from tests.mqtt_testkit import has_test_db, has_test_mqtt, mqtt_params, wait_for

needs_providers = pytest.mark.skipif(
    not (has_test_db() and has_test_mqtt()),
    reason="requires COLDGUARD_TEST_DATABASE_URL and COLDGUARD_TEST_MQTT_HOST",
)

PUBLISH_USER = "backend-command"
PUBLISH_PASSWORD = "backend_cmd_dev_only"


def _connect(user: str, password: str, client_id: str):
    params = mqtt_params()
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, protocol=mqtt.MQTTv5
    )
    client.username_pw_set(user, password)
    connected = threading.Event()
    client.on_connect = lambda *a, **k: connected.set()
    client.connect(params["host"], params["port"], keepalive=30)
    client.loop_start()
    if not connected.wait(timeout=10):
        raise TimeoutError("test broker client did not connect")
    return client


@pytest.fixture
def publisher_client():
    client = _connect(PUBLISH_USER, PUBLISH_PASSWORD, "w06-test-publisher")
    yield client
    client.loop_stop()
    client.disconnect()


@pytest.fixture
def device_subscriber():
    params = mqtt_params()
    client = _connect(params["device_user"], params["device_password"], "w06-test-device")
    yield client
    client.loop_stop()
    client.disconnect()


def _subscribe(client, topic, qos=1):
    received = []

    def on_message(c, u, message):
        received.append(message)

    client.on_message = on_message
    client.subscribe(topic, qos=qos)
    return received


@needs_providers
def test_publish_qos1_non_retained_on_wire(db_engine, publisher_client, device_subscriber):
    cleanup_commands(db_engine)
    try:
        cmd = make_command("cmd-wire")
        with db_engine.begin() as conn:
            cs.create_command(conn, cmd)
        topic = command_topic(cmd.device_id)
        received = _subscribe(device_subscriber, topic, qos=1)
        import time

        time.sleep(0.3)  # allow SUBACK to settle before publishing
        publisher = CommandPublisher(db_engine, PahoCommandTransport(publisher_client))
        result = publisher.publish("cmd-wire")
        assert result["outcome"] == "puback"
        assert result["status"] == cs.PUBLISHED
        assert result["qos"] == 1
        assert result["retain"] is False
        assert wait_for(lambda: len(received) >= 1, timeout_s=5)
        message = received[0]
        assert message.qos == COMMAND_QOS == 1
        assert message.retain is COMMAND_RETAIN is False
        assert message.topic == topic
        payload = json.loads(message.payload)
        assert payload["command_id"] == "cmd-wire"
        assert payload["action"] == {"cooling": "ON", "duty": 0.5}
    finally:
        cleanup_commands(db_engine)


@needs_providers
def test_no_retained_command_for_late_subscriber(db_engine, publisher_client):
    cleanup_commands(db_engine)
    try:
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-retain"))
        publisher = CommandPublisher(db_engine, PahoCommandTransport(publisher_client))
        publisher.publish("cmd-retain")
        # A brand-new subscriber after the publish must receive nothing retained.
        late = _connect(
            mqtt_params()["device_user"], mqtt_params()["device_password"], "w06-late-sub"
        )
        try:
            received = _subscribe(late, command_topic("coldguard-001"), qos=1)
            import time

            time.sleep(0.5)
            assert received == []  # retain=false: no stale actuation delivered
        finally:
            late.loop_stop()
            late.disconnect()
    finally:
        cleanup_commands(db_engine)


@needs_providers
def test_expired_command_never_published(db_engine, publisher_client, device_subscriber):
    cleanup_commands(db_engine)
    try:
        now = utcnow()
        expired = make_command("cmd-expired", created_at=now - timedelta(minutes=10), ttl_s=60)
        with db_engine.begin() as conn:
            cs.create_command(conn, expired)
        received = _subscribe(device_subscriber, command_topic("coldguard-001"))
        publisher = CommandPublisher(db_engine, PahoCommandTransport(publisher_client))
        result = publisher.publish("cmd-expired", now=now)
        assert result["outcome"] == "expired"
        assert result["status"] == cs.EXPIRED
        import time

        time.sleep(0.3)
        assert received == []
    finally:
        cleanup_commands(db_engine)


def test_retry_reuses_command_id_and_increments_attempt(db_engine):
    cleanup_commands(db_engine)
    try:
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-retry"))
        outcomes = iter([PublishResult("FAILED", reason="broker_down"), PublishResult("PUBACK", mid=2)])
        publisher = CommandPublisher(db_engine, lambda *a: next(outcomes))
        first = publisher.publish("cmd-retry")
        assert first["status"] == cs.PUBLISH_FAILED
        second = publisher.publish("cmd-retry")
        assert second["status"] == cs.PUBLISHED
        with db_engine.begin() as conn:
            attempts = conn.execute(
                cs.command_attempts.select().where(
                    cs.command_attempts.c.command_id == "cmd-retry"
                ).order_by(cs.command_attempts.c.attempt_no)
            ).mappings().all()
            row = cs.get_command(conn, "cmd-retry")
        assert [a["attempt_no"] for a in attempts] == [1, 2]
        assert row["command_id"] == "cmd-retry"  # stable identity
        assert row["status"] == cs.PUBLISHED
    finally:
        cleanup_commands(db_engine)


def test_timeout_marks_unknown(db_engine):
    cleanup_commands(db_engine)
    try:
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-timeout"))
        publisher = CommandPublisher(db_engine, lambda *a: PublishResult("TIMEOUT", reason="puback_timeout"))
        result = publisher.publish("cmd-timeout")
        assert result["status"] == cs.UNKNOWN
    finally:
        cleanup_commands(db_engine)


def test_crash_window_pending_reconciles_to_unknown_no_replay(db_engine):
    cleanup_commands(db_engine)
    try:
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-crash"))
            phase1 = cs.begin_publish_attempt(conn, "cmd-crash", payload_sha256="x")
        assert phase1["outcome"] == "ready"
        # Simulate a crash before phase 3: PENDING attempt remains.
        with db_engine.begin() as conn:
            affected = cs.reconcile_pending_attempts(conn)
        assert "cmd-crash" in affected
        with db_engine.begin() as conn:
            row = cs.get_command(conn, "cmd-crash")
            attempt = cs.pending_attempt(conn, "cmd-crash")
        assert row["status"] == cs.UNKNOWN
        assert attempt is None  # resolved, not left pending
    finally:
        cleanup_commands(db_engine)


def test_concurrent_publishers_fenced(db_engine):
    cleanup_commands(db_engine)
    try:
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-fence"))
            cs.begin_publish_attempt(conn, "cmd-fence", payload_sha256="x")
        with pytest.raises(cs.PublishInProgress):
            with db_engine.begin() as conn:
                cs.begin_publish_attempt(conn, "cmd-fence", payload_sha256="x")
    finally:
        cleanup_commands(db_engine)