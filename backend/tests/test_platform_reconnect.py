"""Disposable Mosquitto restart and backend subscription recovery."""

import json
import os
import socket
import subprocess
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from coldguard_backend.command_publisher import CommandPublisher, PahoCommandTransport, command_topic
from coldguard_backend.command_service import create_command_intent
from coldguard_backend.mqtt_consumer import MqttIngestConsumer
from tests.command_testkit import cleanup_commands, make_command
from tests.mqtt_testkit import has_test_db, make_test_config, mqtt_params, wait_for
from tests.test_command_publisher import _connect
from tests.test_twin import _history, _payload, _twin


@pytest.fixture
def restartable_broker(tmp_path, monkeypatch):
    executable = os.environ.get("COLDGUARD_TEST_MOSQUITTO_EXE")
    if not executable or not has_test_db():
        pytest.skip("requires disposable PostgreSQL and COLDGUARD_TEST_MOSQUITTO_EXE")
    broker = Path(executable).resolve(strict=True)
    suffix = broker.suffix
    passwd_tool = broker.with_name("mosquitto_passwd" + suffix)
    signal_tool = broker.with_name("mosquitto_signal" + suffix)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    monkeypatch.setenv("COLDGUARD_TEST_MQTT_HOST", "127.0.0.1")
    monkeypatch.setenv("COLDGUARD_TEST_MQTT_PORT", str(port))
    params = mqtt_params()
    passwd = tmp_path / "passwd"
    for index, (username, password) in enumerate([
        (params["device_user"], params["device_password"]),
        (params["backend_user"], params["backend_password"]),
        ("backend-command", "backend_cmd_dev_only"),
    ]):
        options = ["-b", "-c"] if index == 0 else ["-b"]
        subprocess.run([str(passwd_tool), *options, str(passwd), username, password],
                       check=True, creationflags=flags, capture_output=True)
    acl = tmp_path / "acl"
    acl.write_text(
        f"user {params['device_user']}\ntopic write coldguard/coldguard-001/telemetry\n"
        f"topic read coldguard/coldguard-001/command\n"
        f"user {params['backend_user']}\ntopic read coldguard/+/telemetry\n"
        "user backend-command\ntopic write coldguard/coldguard-001/command\n",
        encoding="utf-8",
    )
    config = tmp_path / "broker.conf"
    config.write_text(
        f"listener {port} 127.0.0.1\nallow_anonymous false\n"
        f"password_file {passwd.as_posix()}\nacl_file {acl.as_posix()}\n"
        f"persistence true\npersistence_location {tmp_path.as_posix()}/\n",
        encoding="utf-8",
    )
    child = None

    def ready():
        if child.poll() is not None:
            raise RuntimeError(f"disposable broker exited with {child.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            return False

    def start():
        nonlocal child
        child = subprocess.Popen(
            [str(broker), "-c", str(config)], creationflags=flags,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        assert wait_for(ready, timeout_s=5)

    def stop():
        if child is None or child.poll() is not None:
            return
        try:
            if os.name == "nt" and signal_tool.is_file():
                subprocess.run([str(signal_tool), "-p", str(child.pid), "shutdown"],
                               check=True, creationflags=flags, capture_output=True, timeout=4)
            else:
                child.terminate()
            child.wait(timeout=5)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    try:
        start()
        yield start, stop
    finally:
        stop()


def test_broker_restart_recovers_subscriptions_without_retained_command(db_engine, restartable_broker):
    start, stop = restartable_broker
    params = mqtt_params()
    device = "coldguard-001"
    boot = f"software-reconnect-{uuid4().hex}"
    command_id = f"reconnect-{uuid4().hex}"
    config = make_test_config(
        mqtt_user=params["backend_user"], mqtt_password=params["backend_password"],
    )
    consumer = MqttIngestConsumer(config, subscriptions=(("coldguard/+/telemetry", 1),))
    clients = []
    cleanup_commands(db_engine)

    def device_client(label):
        client = _connect(params["device_user"], params["device_password"], label)
        clients.append(client)
        return client

    def send(client, seq):
        payload = json.dumps(_payload(device, seq, boot_id=boot))
        delivery = client.publish(f"coldguard/{device}/telemetry", payload, qos=1)
        delivery.wait_for_publish(timeout=5)
        assert delivery.is_published()
        assert wait_for(
            lambda: any(row["boot_id"] == boot and row["seq"] == seq for row in _history(db_engine, device)),
            timeout_s=5,
        )

    try:
        consumer.start()
        sender = device_client("software-reconnect-before")
        send(sender, 1)
        before = _twin(db_engine, device)
        assert before["last_seq"] == 1
        publish_client = _connect("backend-command", "backend_cmd_dev_only", "software-command")
        clients.append(publish_client)
        create_command_intent(db_engine, make_command(command_id))
        assert CommandPublisher(db_engine, PahoCommandTransport(publish_client)).publish(command_id)["outcome"] == "puback"
        stop()
        assert wait_for(lambda: not consumer.snapshot()["broker_connected"], timeout_s=5)
        assert not consumer.snapshot()["subscribed"]
        assert _twin(db_engine, device)["last_seq"] == 1
        start()
        assert wait_for(lambda: consumer.snapshot()["subscribed"], timeout_s=10)

        resumed = device_client("software-reconnect-after")
        subscribed = threading.Event()
        retained = threading.Event()
        resumed.on_subscribe = lambda *_: subscribed.set()
        resumed.on_message = lambda *_: retained.set()
        resumed.subscribe(command_topic(device), qos=1)
        assert subscribed.wait(5)
        assert not retained.wait(0.5)
        send(resumed, 2)
        assert _twin(db_engine, device)["last_seq"] == 2

        consumer.stop()
        consumer = MqttIngestConsumer(config, subscriptions=(("coldguard/+/telemetry", 1),))
        consumer.start()
        assert _twin(db_engine, device)["last_seq"] == 2
        send(resumed, 1)
        assert wait_for(lambda: consumer.snapshot()["exact_duplicates"] == 1, timeout_s=5)
        assert _twin(db_engine, device)["last_seq"] == 2
        send(resumed, 3)
        assert _twin(db_engine, device)["last_seq"] == 3
    finally:
        consumer.stop()
        for client in clients:
            client.disconnect()
            client.loop_stop()
        cleanup_commands(db_engine)
