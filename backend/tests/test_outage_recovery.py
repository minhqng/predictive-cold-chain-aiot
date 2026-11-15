"""Fail-closed command recovery on verified disposable providers."""

import json
import secrets
import socket
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from coldguard_backend import command_store as commands
from coldguard_backend.command_authorization import AuthorizedCommandGateway, CommandDispatchUnavailable
from coldguard_backend.command_publisher import PahoCommandTransport, PublishResult, command_topic
from coldguard_backend.command_service import create_command_intent
from coldguard_backend.main import app
from coldguard_backend.normalized_store import telemetry as telemetry_table
from coldguard_backend.raw_store import telemetry_raw
from coldguard_backend.recovery import device_recovery_snapshot
from tests.command_testkit import ack_bytes, ack_topic, cleanup_commands, make_ack, make_command, utcnow
from tests.mqtt_testkit import has_test_mqtt, mqtt_params, wait_for
from tests.test_ack_consumer import _enable_app_ack
from tests.test_command_publisher import _connect
from tests.test_platform_reconnect import restartable_broker  # noqa: F401
from tests.test_twin import _payload


def _gateway(engine, transport, ready, token):
    return AuthorizedCommandGateway(
        engine, transport, backend_token=token, allowed_devices=frozenset({"coldguard-001"}),
        policy_allows=lambda _command: True, transport_ready=ready,
    )


@contextmanager
def _backend_process(log_path, pids):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    runner = """
import sys
from threading import Thread
from uvicorn import Config, Server

server = Server(Config("coldguard_backend.main:app", host="127.0.0.1", port=int(sys.argv[1])))

def stop_on_parent_close():
    sys.stdin.read()
    server.should_exit = True

Thread(target=stop_on_parent_close, daemon=True).start()
server.run()
"""
    with log_path.open("wb") as output:
        process = subprocess.Popen(
            [sys.executable, "-c", runner, str(port)],
            stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        pids.append(process.pid)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2, trust_env=False) as client:
                def ready():
                    assert process.poll() is None, log_path.read_text(encoding="utf-8", errors="replace")
                    try:
                        return client.get("/health").status_code == 200
                    except httpx.TransportError:
                        return False

                assert wait_for(ready, timeout_s=15)
                yield client
        finally:
            process.stdin.close()
            try:
                assert process.wait(timeout=10) == 0, log_path.read_text(encoding="utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise


def test_broker_outage_blocks_dispatch_and_never_fabricates_state(db_engine, restartable_broker):
    start, stop = restartable_broker
    cleanup_commands(db_engine)
    client = _connect("backend-command", "backend_cmd_dev_only", "w16-broker-proof")
    transport = PahoCommandTransport(client)
    token = secrets.token_urlsafe(32)
    gateway = _gateway(db_engine, transport, transport.is_ready, token)
    command = make_command("w16-broker-outage")
    try:
        assert transport.is_ready()
        stop()
        assert wait_for(lambda: not transport.is_ready(), timeout_s=5)
        with pytest.raises(CommandDispatchUnavailable):
            gateway.dispatch(command, backend_token=token)
        with db_engine.connect() as conn:
            assert commands.get_command(conn, command.command_id) is None
            evidence = device_recovery_snapshot(conn, command.device_id)
        assert evidence["reported"] == {}
        assert evidence["reported_boot_id"] is None
        assert evidence["desired"] is None
        start()
        assert not transport.is_ready()
        with pytest.raises(CommandDispatchUnavailable):
            gateway.dispatch(command, backend_token=token)
    finally:
        client.disconnect()
        client.loop_stop()
        cleanup_commands(db_engine)


def test_database_connection_outage_prevents_creation_and_transmission(db_engine):
    token = secrets.token_urlsafe(32)
    sent = []
    command = make_command("w16-db-outage")
    # Reserve a local port without listening. No other database is contacted.
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        broken = create_engine(db_engine.url.set(
            host="127.0.0.1", port=unused.getsockname()[1],
        ), connect_args={"connect_timeout": 2})
        try:
            gateway = _gateway(
                broken, lambda *args: sent.append(args) or PublishResult("PUBACK"),
                lambda: True, token,
            )
            with pytest.raises(OperationalError):
                gateway.dispatch(command, backend_token=token)
        finally:
            broken.dispose()
    assert not sent
    with db_engine.connect() as conn:
        assert commands.get_command(conn, command.command_id) is None


@pytest.mark.skipif(not has_test_mqtt(), reason="requires disposable Mosquitto")
@pytest.mark.parametrize("process_restart", [False, True], ids=["lifespan", "process"])
def test_backend_restart_resolves_pending_expiry_and_recovers_subscription(
    db_engine, monkeypatch, tmp_path, process_restart,
):
    params = mqtt_params()
    if process_restart and (params["host"] != "127.0.0.1" or db_engine.url.host != "127.0.0.1"):
        pytest.skip("process restart proof requires direct loopback providers")
    cleanup_commands(db_engine)
    _enable_app_ack(monkeypatch)
    monkeypatch.setenv("COLDGUARD_MQTT_INGEST", "true")
    monkeypatch.setenv("COLDGUARD_RECONCILE_COMMANDS", "true")
    monkeypatch.setattr(app.state, "db_engine", db_engine)
    if process_restart:
        monkeypatch.setenv("DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
        monkeypatch.delenv("MQTT_TLS_CA", raising=False)
    pids = []

    def backend(label):
        if process_restart:
            return _backend_process(tmp_path / f"{label}.log", pids)
        return TestClient(app)

    device = "coldguard-001"
    device_client = _connect(params["device_user"], params["device_password"], "w16-restart-device")
    subscribed, command_received = threading.Event(), threading.Event()
    device_client.on_subscribe = lambda *_: subscribed.set()
    device_client.on_message = lambda *_: command_received.set()
    path = f"/api/devices/{device}/recovery"
    command_id = "w16-unresolved-expired"
    boot_id = f"w16-software-{secrets.token_hex(6)}"

    def send(topic, payload):
        delivery = device_client.publish(topic, payload, qos=1, retain=False)
        delivery.wait_for_publish(timeout=5)
        assert delivery.is_published()

    def telemetry(seq, **kwargs):
        payload = _payload(device, seq, boot_id=boot_id, run_id=boot_id, **kwargs)
        send(f"coldguard/{device}/telemetry", json.dumps(payload).encode())

    try:
        device_client.subscribe(command_topic(device), qos=1)
        assert subscribed.wait(5)
        with backend("first") as first:
            assert first.get("/api/runtime/readiness").json()["telemetry_subscribed"]
            telemetry(1)
            assert wait_for(lambda: first.get(path).json()["reported_seq"] == 1, timeout_s=5)
            created = utcnow() - timedelta(minutes=3)
            stale = make_command(command_id, created_at=created, ttl_s=5)
            result = create_command_intent(db_engine, stale, now=created)
            with db_engine.begin() as conn:
                attempt = commands.begin_publish_attempt(
                    conn, command_id, payload_sha256=result["command"]["payload_sha256"], now=created,
                )
            assert first.get(path).json()["pending_attempts"] == 1
        with backend("second") as second:
            readiness = second.get("/api/runtime/readiness").json()
            assert all(readiness.values())
            if not process_restart:
                assert app.state.command_recovery["uncertain_commands"] == [command_id]
                assert app.state.command_recovery["expired_commands"] == [command_id]
            recovery = second.get(path).json()
            assert recovery["reported_boot_id"] == boot_id
            assert recovery["reported_seq"] == 1
            assert recovery["desired"]["expired"]
            assert recovery["desired"]["status"] == commands.EXPIRED
            assert recovery["pending_attempts"] == 0
            assert not command_received.wait(0.5)
            with db_engine.connect() as conn:
                assert commands.get_attempt(conn, attempt["attempt_id"])["outcome"] == "UNKNOWN"
            telemetry(99, replay=True)
            assert wait_for(
                lambda: second.get(path).json()["latest_observation"]["seq"] == 99, timeout_s=5,
            )
            assert second.get(path).json()["reported_seq"] == 1
            send(ack_topic(), ack_bytes(make_ack(command_id)))
            assert wait_for(lambda: second.get(path).json()["latest_ack_receipt"] is not None, timeout_s=5)
            assert second.get(path).json()["latest_ack_receipt"]["validity"] == "LATE"
            assert second.get(path).json()["desired"]["status"] == commands.EXPIRED
            telemetry(2)
            assert wait_for(lambda: second.get(path).json()["reported_seq"] == 2, timeout_s=5)
            assert not command_received.is_set()
        if process_restart:
            assert len(set(pids)) == 2
    finally:
        device_client.disconnect()
        device_client.loop_stop()
        cleanup_commands(db_engine)
        with db_engine.begin() as conn:
            conn.execute(telemetry_table.delete().where(telemetry_table.c.run_id == boot_id))
            conn.execute(telemetry_raw.delete().where(telemetry_raw.c.run_id == boot_id))
