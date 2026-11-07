"""End-to-end command-path integration harness (C-W06-05/06).

Software-only integration reflecting Member A/D contracts: durable intent +
desired-Twin linkage, real-broker publish, mock-device ACK, consumer correlation,
domain separation, expiry/supersession, restart durability and a simulated
broker outage. No physical hardware; the device is a contract-compatible mock.
Physical acceptance is explicitly NOT claimed.
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import paho.mqtt.client as mqtt
import pytest
from sqlalchemy import create_engine

from coldguard_backend import command_store as cs
from coldguard_backend import command_service as svc
from coldguard_backend import command_publisher as publishing
from coldguard_backend.ack_consumer import AckConsumer
from coldguard_backend.command_publisher import (
    CommandPublisher,
    PahoCommandTransport,
    PublishResult,
    command_topic,
)
from coldguard_backend.twin_store import device_twin
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


def _connect(user, password, client_id):
    params = mqtt_params()
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, protocol=mqtt.MQTTv5, reconnect_on_failure=False
    )
    client.username_pw_set(user, password)
    connected = threading.Event()
    client.on_connect = lambda *a, **k: connected.set()
    client.connect(params["host"], params["port"], keepalive=30)
    client.loop_start()
    connected.wait(timeout=10)
    return client


def _twin(engine, device_id="coldguard-001"):
    with engine.begin() as conn:
        row = conn.execute(
            device_twin.select().where(device_twin.c.device_id == device_id)
        ).mappings().first()
    return dict(row) if row else None


# --- Desired-Twin integration (C-W06-05), database only --------------------


def test_desired_linked_reported_and_derived_untouched(db_engine):
    cleanup_commands(db_engine)
    try:
        result = svc.create_command_intent(db_engine, make_command("cmd-desired"))
        assert result["outcome"] == "created"
        twin = _twin(db_engine)
        assert twin["desired_state"]["command_id"] == "cmd-desired"
        assert twin["desired_state"]["cooling"] == "ON"
        # Command creation must not fabricate reported or derived state; the
        # W04 twin defaults these to an empty object (no device observation).
        assert twin["reported_state"] == {}
        assert twin["derived_state"] == {}
        active = svc.active_desired_intent(db_engine, "coldguard-001")
        assert active["command_id"] == "cmd-desired"
    finally:
        cleanup_commands(db_engine)


def test_desired_expiry_removes_executable_meaning(db_engine):
    cleanup_commands(db_engine)
    try:
        now = utcnow()
        cmd = make_command("cmd-exp-desired", created_at=now, ttl_s=120)
        svc.create_command_intent(db_engine, cmd, now=now)
        assert svc.active_desired_intent(db_engine, "coldguard-001", now=now)["command_id"] == "cmd-exp-desired"
        later = now + timedelta(seconds=180)
        with db_engine.begin() as conn:
            cs.expire_due_commands(conn, now=later)
        # Expired intent loses executable meaning; reported still untouched.
        assert svc.active_desired_intent(db_engine, "coldguard-001", now=later) is None
        assert _twin(db_engine)["reported_state"] == {}
    finally:
        cleanup_commands(db_engine)


def test_superseded_command_loses_executable_meaning(db_engine):
    cleanup_commands(db_engine)
    try:
        old = make_command("cmd-old")
        svc.create_command_intent(db_engine, old)
        svc.create_command_intent(db_engine, make_command("cmd-new"))
        version = _twin(db_engine)["twin_version"]
        assert svc.create_command_intent(db_engine, old)["outcome"] == "exists"
        assert _twin(db_engine)["twin_version"] == version
        sent = []
        publisher = CommandPublisher(db_engine, lambda *args: sent.append(args) or PublishResult("PUBACK"))
        assert publisher.publish("cmd-old")["outcome"] == "superseded"
        assert not sent
        active = svc.active_desired_intent(db_engine, "coldguard-001")
        assert active["command_id"] == "cmd-new"
        # Old command remains auditable but is no longer the active intent.
        with db_engine.begin() as conn:
            assert cs.get_command(conn, "cmd-old") is not None
    finally:
        cleanup_commands(db_engine)


@pytest.mark.parametrize("verdict,status", [
    ("ACCEPTED", cs.ACK_ACCEPTED), ("REJECTED", cs.ACK_REJECTED),
])
def test_early_ack_precedes_puback_commit(db_engine, verdict, status):
    from tests.test_command_store import _record_ack

    cleanup_commands(db_engine)
    try:
        svc.create_command_intent(db_engine, make_command("cmd-early"))
        ack = make_ack("cmd-early", verdict)
        assert _record_ack(db_engine, ack)["outcome"] == "conflict"

        def send(*_):
            assert _record_ack(db_engine, ack)["outcome"] == "applied"
            assert _record_ack(db_engine, ack)["outcome"] == "duplicate"
            return PublishResult("PUBACK", mid=1)

        result = CommandPublisher(db_engine, send).publish("cmd-early")
        assert result["status"] == status
        assert result["outcome"] == "puback"
        with db_engine.connect() as conn:
            row = cs.get_command(conn, "cmd-early")
            assert row["status"] == status
            assert row["published_at"] is not None
            assert row["verification_status"] == "NONE"
            assert cs.get_attempt(conn, result["attempt_id"])["outcome"] == "PUBACK"
    finally:
        cleanup_commands(db_engine)


def test_supersession_between_attempt_commit_and_send_fences_retry(db_engine, monkeypatch):
    cleanup_commands(db_engine)
    original = publishing.command_from_row

    def supersede(row):
        svc.create_command_intent(db_engine, make_command("cmd-new-between"))
        return original(row)

    try:
        svc.create_command_intent(db_engine, make_command("cmd-old-between"))
        monkeypatch.setattr(publishing, "command_from_row", supersede)
        sent = []
        publisher = CommandPublisher(db_engine, lambda *args: sent.append(args) or PublishResult("PUBACK"))
        result = publisher.publish("cmd-old-between")
        assert result["outcome"] == "superseded"
        assert publisher.publish("cmd-old-between")["outcome"] == "superseded"
        assert not sent
        with db_engine.connect() as conn:
            assert cs.get_attempt(conn, result["attempt_id"])["broker_reason"] == "superseded"
    finally:
        cleanup_commands(db_engine)


def test_device_fence_serializes_supersession_during_transport(db_engine):
    cleanup_commands(db_engine)
    started = threading.Event()
    release = threading.Event()
    creator_started = threading.Event()

    def transport(*_):
        started.set()
        assert release.wait(5)
        return PublishResult("PUBACK")

    def replace():
        creator_started.set()
        return svc.create_command_intent(db_engine, make_command("cmd-next"))

    try:
        svc.create_command_intent(db_engine, make_command("cmd-first"))
        publisher = CommandPublisher(db_engine, transport)
        with ThreadPoolExecutor(max_workers=2) as workers:
            publication = workers.submit(publisher.publish, "cmd-first")
            try:
                assert started.wait(5)
                supersession = workers.submit(replace)
                assert creator_started.wait(5)
                assert wait_for(lambda: _creator_waits_for_lock(db_engine), timeout_s=3)
                assert _twin(db_engine)["desired_state"]["command_id"] == "cmd-first"
            finally:
                release.set()
            assert publication.result(5)["outcome"] == "puback"
            assert supersession.result(5)["outcome"] == "created"
        assert _twin(db_engine)["desired_state"]["command_id"] == "cmd-next"
    finally:
        cleanup_commands(db_engine)


def _creator_waits_for_lock(engine):
    from sqlalchemy import text

    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_locks
                WHERE locktype = 'advisory' AND NOT granted
                  AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
            )
        """)).scalar_one()


def test_rejected_intent_not_executable(db_engine):
    cleanup_commands(db_engine)
    try:
        svc.create_command_intent(db_engine, make_command("cmd-rej-desired"))
        with db_engine.begin() as conn:
            cs.transition_command(conn, "cmd-rej-desired", cs.PUBLISHED)
        import hashlib

        ack = make_ack("cmd-rej-desired", "SAFETY_BLOCKED", reason_code="EPOCH_UNSYNCHRONIZED")
        raw = ack_bytes(ack)
        with db_engine.begin() as conn:
            cs.record_ack(
                conn, topic_device_id="coldguard-001", raw_payload=raw.decode(),
                payload_sha256=hashlib.sha256(raw).hexdigest(),
                backend_received_at=utcnow(), ack=ack, validity="VALID",
            )
        assert svc.active_desired_intent(db_engine, "coldguard-001") is None
    finally:
        cleanup_commands(db_engine)


def test_uncertain_publish_represented_not_fabricated(db_engine):
    cleanup_commands(db_engine)
    try:
        svc.create_command_intent(db_engine, make_command("cmd-uncertain"))
        publisher = CommandPublisher(db_engine, lambda *a: PublishResult("TIMEOUT", reason="lost"))
        result = publisher.publish("cmd-uncertain")
        assert result["status"] == cs.UNKNOWN
        active = svc.active_desired_intent(db_engine, "coldguard-001")
        # Uncertainty is represented explicitly; no fabricated OFF/ON reported state.
        assert active["status"] == cs.UNKNOWN
        assert _twin(db_engine)["reported_state"] == {}
    finally:
        cleanup_commands(db_engine)


def test_concurrent_intent_creators_consistent_desired(db_engine):
    cleanup_commands(db_engine)
    try:
        url = os.environ["COLDGUARD_TEST_DATABASE_URL"]
        barrier = threading.Barrier(2)
        errors = []

        def worker(command_id):
            engine = create_engine(url)
            try:
                barrier.wait()
                svc.create_command_intent(engine, make_command(command_id))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                engine.dispose()

        threads = [
            threading.Thread(target=worker, args=("cmd-race-a",)),
            threading.Thread(target=worker, args=("cmd-race-b",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        active = svc.active_desired_intent(db_engine, "coldguard-001")
        # Desired points to exactly one consistent intent (the last CAS winner).
        assert active["command_id"] in ("cmd-race-a", "cmd-race-b")
        twin = _twin(db_engine)
        assert twin["desired_state"]["command_id"] == active["command_id"]
    finally:
        cleanup_commands(db_engine)


# --- Contract negative cases (C-W06-06) ------------------------------------


def test_out_of_range_duty_rejected_before_executable_path(db_engine):
    cleanup_commands(db_engine)
    try:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            make_command("cmd-bad-duty", duty=1.5)
        with db_engine.begin() as conn:
            assert cs.get_command(conn, "cmd-bad-duty") is None
    finally:
        cleanup_commands(db_engine)


def test_duplicate_command_id_conflicting_payload_rejected(db_engine):
    cleanup_commands(db_engine)
    try:
        svc.create_command_intent(db_engine, make_command("cmd-dup-id"))
        with pytest.raises(cs.CommandConflict):
            svc.create_command_intent(db_engine, make_command("cmd-dup-id", reason_code="OTHER"))
    finally:
        cleanup_commands(db_engine)


def test_wrong_device_ack_cannot_transition(db_engine):
    cleanup_commands(db_engine)
    try:
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-wrong-dev"))
            cs.transition_command(conn, "cmd-wrong-dev", cs.PUBLISHED)
        import hashlib

        ack = make_ack("cmd-wrong-dev", "ACCEPTED", device_id="other-device")
        raw = ack_bytes(ack)
        with db_engine.begin() as conn:
            result = cs.record_ack(
                conn, topic_device_id="coldguard-001", raw_payload=raw.decode(),
                payload_sha256=hashlib.sha256(raw).hexdigest(),
                backend_received_at=utcnow(), ack=ack, validity="VALID",
            )
        assert result["outcome"] == "conflict"
        with db_engine.begin() as conn:
            assert cs.get_command(conn, "cmd-wrong-dev")["status"] == cs.PUBLISHED
    finally:
        cleanup_commands(db_engine)


# --- Full end-to-end through a real broker (C-W06-06) ----------------------


@needs_providers
def test_legal_fresh_command_end_to_end(db_engine):
    cleanup_commands(db_engine)
    params = mqtt_params()
    publisher_client = _connect("backend-command", "backend_cmd_dev_only", "w06-e2e-pub")
    device_client = _connect(params["device_user"], params["device_password"], "w06-e2e-dev")
    consumer = AckConsumer.from_config(
        make_test_config(mqtt_user=params["backend_user"], mqtt_password=params["backend_password"])
    )
    consumer.start()
    assert consumer.wait_subscribed(10)
    received_commands = []
    try:
        subscribed = threading.Event()
        device_client.on_subscribe = lambda *_: subscribed.set()

        def mock_device(c, u, message):
            received_commands.append(message)
            ack = make_ack(json.loads(message.payload)["command_id"])
            c.publish(ack_topic(), ack_bytes(ack), qos=1)

        device_client.on_message = mock_device
        device_client.subscribe(command_topic("coldguard-001"), qos=1)
        assert subscribed.wait(10)
        svc.create_command_intent(db_engine, make_command("cmd-e2e"))
        transport = PahoCommandTransport(publisher_client)
        observed_early = []

        def delay_puback_recording(*args):
            result = transport(*args)
            observed_early.append(wait_for(
                lambda: _status(db_engine, "cmd-e2e") == cs.ACK_ACCEPTED, timeout_s=10
            ))
            return result

        publisher = CommandPublisher(db_engine, delay_puback_recording)
        pub_result = publisher.publish("cmd-e2e")
        assert observed_early == [True]
        assert pub_result["outcome"] == "puback"
        assert pub_result["status"] == cs.ACK_ACCEPTED
        assert received_commands[0].qos == 1
        assert received_commands[0].retain is False
        with db_engine.begin() as conn:
            row = cs.get_command(conn, "cmd-e2e")
            assert row["published_at"] is not None
            assert cs.get_attempt(conn, pub_result["attempt_id"])["outcome"] == "PUBACK"
        assert row["verification_status"] == "NONE"
        assert row["status"] != cs.VERIFIED
        # Reported state is still untouched by the command/ACK path.
        assert _twin(db_engine)["reported_state"] == {}
    finally:
        consumer.stop()
        publisher_client.loop_stop()
        publisher_client.disconnect()
        device_client.loop_stop()
        device_client.disconnect()
        cleanup_commands(db_engine)


def _status(engine, command_id):
    with engine.begin() as conn:
        row = cs.get_command(conn, command_id)
    return row["status"] if row else None


@needs_providers
def test_simulated_broker_outage_then_recovery(db_engine):
    """Software-simulated outage: first publish uncertain, retry after recovery."""
    cleanup_commands(db_engine)
    params = mqtt_params()
    publisher_client = _connect("backend-command", "backend_cmd_dev_only", "w06-outage-pub")
    try:
        svc.create_command_intent(db_engine, make_command("cmd-outage"))
        real = PahoCommandTransport(publisher_client)
        state = {"down": True}

        def flaky(topic, payload, qos, retain):
            if state["down"]:
                return PublishResult("UNKNOWN", reason="broker_outage")
            return real(topic, payload, qos, retain)

        publisher = CommandPublisher(db_engine, flaky)
        first = publisher.publish("cmd-outage")
        assert first["status"] == cs.UNKNOWN  # uncertain, not assumed unapplied
        state["down"] = False
        second = publisher.publish("cmd-outage")
        assert second["status"] == cs.PUBLISHED
        with db_engine.begin() as conn:
            assert cs.get_command(conn, "cmd-outage")["command_id"] == "cmd-outage"
    finally:
        publisher_client.loop_stop()
        publisher_client.disconnect()
        cleanup_commands(db_engine)


@needs_providers
def test_backend_restart_preserves_durable_command_state(db_engine):
    cleanup_commands(db_engine)
    params = mqtt_params()
    publisher_client = _connect("backend-command", "backend_cmd_dev_only", "w06-restart-pub")
    try:
        svc.create_command_intent(db_engine, make_command("cmd-restart"))
        CommandPublisher(db_engine, PahoCommandTransport(publisher_client)).publish("cmd-restart")
        # Simulated restart: a fresh engine reads the same durable state.
        fresh = create_engine(os.environ["COLDGUARD_TEST_DATABASE_URL"])
        try:
            with fresh.begin() as conn:
                row = cs.get_command(conn, "cmd-restart")
            assert row["status"] == cs.PUBLISHED
            assert row["published_at"] is not None
            assert svc.active_desired_intent(fresh, "coldguard-001")["command_id"] == "cmd-restart"
        finally:
            fresh.dispose()
    finally:
        publisher_client.loop_stop()
        publisher_client.disconnect()
        cleanup_commands(db_engine)
