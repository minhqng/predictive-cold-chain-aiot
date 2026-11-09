"""Real Mosquitto TLS, authentication and command ACL proof."""

import os
import secrets
import socket
import ssl
import subprocess
import threading
from dataclasses import replace
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest

from coldguard_backend.config import ColdGuardConfig
from coldguard_backend.ack_consumer import AckConsumer
from coldguard_backend.mqtt_consumer import MqttIngestConsumer
from coldguard_backend.mqtt_security import configure_mqtt_client
from tests.mqtt_testkit import make_test_config, wait_for


@pytest.fixture
def tls_broker(tmp_path):
    mosquitto = os.environ.get("COLDGUARD_TEST_MOSQUITTO_EXE")
    openssl = os.environ.get("COLDGUARD_TEST_OPENSSL_EXE")
    if not mosquitto or not openssl:
        pytest.skip("requires disposable Mosquitto and OpenSSL executables")
    broker = Path(mosquitto).resolve(strict=True)
    passwd = broker.with_name("mosquitto_passwd" + broker.suffix)
    signal = broker.with_name("mosquitto_signal" + broker.suffix)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def run(*args):
        subprocess.run(args, check=True, creationflags=flags, capture_output=True, timeout=15)

    cert, key = tmp_path / "server.crt", tmp_path / "server.key"
    run(
        openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-subj", "/CN=ColdGuard disposable TLS test", "-addext", "subjectAltName=IP:127.0.0.1",
        "-keyout", str(key), "-out", str(cert),
    )
    credentials = {
        user: secrets.token_urlsafe(20)
        for user in ("device-coldguard-001", "backend-ingest", "backend-command")
    }
    for number, (user, password) in enumerate(credentials.items()):
        run(str(passwd), "-b", *(["-c"] if number == 0 else []), str(tmp_path / "passwd"), user, password)
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    config_dir = Path(__file__).resolve().parents[2] / "infra/mosquitto"
    config = (config_dir / "mosquitto-tls.conf").read_text(encoding="utf-8")
    replacements = {
        "listener 8883": f"listener {port} 127.0.0.1",
        "/mosquitto/config/tls/server.crt": cert.as_posix(),
        "/mosquitto/config/tls/server.key": key.as_posix(),
        "/mosquitto/config/passwd": (tmp_path / "passwd").as_posix(),
        "/mosquitto/config/acl.conf": (config_dir / "acl.conf").as_posix(),
        "/mosquitto/data/": tmp_path.as_posix() + "/",
    }
    for before, after in replacements.items():
        config = config.replace(before, after)
    path = tmp_path / "broker.conf"
    path.write_text(config, encoding="utf-8")
    with (tmp_path / "broker.log").open("wb") as log:
        child = subprocess.Popen([str(broker), "-c", str(path)], creationflags=flags, stdout=log, stderr=log)

    def ready():
        if child.poll() is not None:
            raise RuntimeError("disposable TLS broker did not start")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            return False

    try:
        assert wait_for(ready, timeout_s=5)
        yield port, cert, credentials
    finally:
        if child.poll() is None:
            try:
                if os.name == "nt" and signal.is_file():
                    run(str(signal), "-p", str(child.pid), "shutdown")
                else:
                    child.terminate()
                child.wait(timeout=5)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)


def _client(port, cert, username, password):
    config = ColdGuardConfig.load(env={
        "MQTT_HOST": "127.0.0.1", "MQTT_PORT": str(port), "MQTT_TLS_CA": str(cert),
        "MQTT_USERNAME": username, "MQTT_PASSWORD": password,
    })
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5, reconnect_on_failure=False)
    configure_mqtt_client(client, config)
    return client


def test_tls_validates_trust_and_hostname(tls_broker):
    port, cert, credentials = tls_broker
    user = "backend-ingest"
    untrusted = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    untrusted.tls_set_context(ssl.create_default_context())
    with pytest.raises(ssl.SSLCertVerificationError):
        untrusted.connect("127.0.0.1", port)
    hostname = _client(port, cert, user, credentials[user])
    with pytest.raises(ssl.SSLCertVerificationError):
        hostname.connect("localhost", port)


def test_tls_authentication_and_command_acl(tls_broker):
    port, cert, credentials = tls_broker
    device = "device-coldguard-001"
    publisher = "backend-command"
    topic = "coldguard/coldguard-001/command"
    clients = []

    def connect(user, password, *, refused=False):
        client = _client(port, cert, user, password)
        clients.append(client)
        conns = []
        ready = threading.Event()
        client.on_connect = lambda c, u, f, rc, p: (conns.append(rc), ready.set())
        client.connect("127.0.0.1", port)
        client.loop_start()
        assert ready.wait(5)
        assert conns[0].is_failure is refused
        return client

    def publish(client, destination):
        outcomes = []
        ready = threading.Event()
        client.on_publish = lambda c, u, mid, rc, p: (outcomes.append(rc), ready.set())
        delivery = client.publish(destination, b'{"software_fixture":true}', qos=1, retain=False)
        assert ready.wait(5)
        delivery.wait_for_publish(timeout=5)
        return outcomes[0]

    try:
        connect(publisher, "wrong-password", refused=True)
        target = connect(device, credentials[device])
        subscribed, delivered = threading.Event(), threading.Event()
        target.on_subscribe = lambda *_: subscribed.set()
        target.on_message = lambda *_: delivered.set()
        target.subscribe(topic, qos=1)
        assert subscribed.wait(5)
        assert publish(target, topic).is_failure
        writer = connect(publisher, credentials[publisher])
        assert publish(writer, "coldguard/other-device/command").is_failure
        assert not publish(writer, topic).is_failure
        assert delivered.wait(5)
    finally:
        for client in clients:
            client.disconnect()
            client.loop_stop()


def test_backend_consumers_subscribe_with_verified_tls(tls_broker, db_engine):
    port, cert, credentials = tls_broker
    user = "backend-ingest"
    config = replace(
        make_test_config(mqtt_user=user, mqtt_password=credentials[user]),
        mqtt_host="127.0.0.1", mqtt_port=port, mqtt_tls_ca=str(cert),
    )
    telemetry = MqttIngestConsumer.from_config(config)
    ack = AckConsumer.from_config(config)
    try:
        telemetry.start()
        ack.start()
        assert telemetry.snapshot()["subscribed"]
        assert ack.snapshot()["subscribed"]
    finally:
        ack.stop()
        telemetry.stop()
