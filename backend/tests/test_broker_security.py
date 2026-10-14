"""Broker authentication/ACL proof against real Mosquitto (C-W02-01).

Runs only with COLDGUARD_TEST_MQTT_HOST set (plus credential vars),
against the real pinned broker with the committed ACL — never a mocked
permission function. Proves: anonymous CONNECT denied, wrong password
refused (distinguishable from unreachable), device publishes its own
telemetry and the backend receives it, device command publishing
denied, cross-device publishing denied, and the backend ingestion
identity cannot spoof device telemetry.

Negative assertions use bounded condition waits (a receive event that
must stay unset), not assumed completion.
"""

import threading
import uuid

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

from coldguard_backend.mqtt_consumer import reason_failed
from tests.mqtt_testkit import has_test_mqtt, mqtt_params, wait_for

needs_real_broker = pytest.mark.skipif(
    not has_test_mqtt(),
    reason="requires COLDGUARD_TEST_MQTT_HOST pointing at the W02 test broker",
)

DEVICE_TELEMETRY = "coldguard/coldguard-001/telemetry"
DEVICE_COMMAND = "coldguard/coldguard-001/command"

# MQTT 5 SUBACK success codes: the only grant outcomes that prove the
# broker accepted the subscription. Every other defined SUBACK code is
# a refusal (128 Unspecified error, 131 Implementation specific error,
# 135 Not authorized, 143 Topic Filter invalid, ... — all >= 0x80).
_SUBACK_GRANTED_CODES = frozenset({0, 1, 2})


def _is_suback_granted(granted: list[int]) -> bool:
    """True only when every SUBACK code is a genuine Granted QoS 0/1/2."""
    return bool(granted) and all(code in _SUBACK_GRANTED_CODES for code in granted)


def _reason_failed(reason) -> bool:
    return reason_failed(reason)


class _Probe:
    """One throwaway client recording CONNECT/PUBLISH/disconnect outcomes."""

    def __init__(self, *, username: str | None, password: str = "") -> None:
        params = mqtt_params()
        self.connected = threading.Event()
        self.disconnects: list[str] = []
        self.failures: list[str] = []
        self.received: list[tuple[str, bytes]] = []
        self.publish_results: list[str] = []
        # SUBACK tracking: mid -> (event, granted codes). A subscribe()
        # return only means the SUBSCRIBE packet was queued; the broker
        # has processed it only after the matching SUBACK arrives.
        self._sub_locks: dict[int, threading.Event] = {}
        self._sub_grants: dict[int, list[int]] = {}
        self._sub_mu = threading.Lock()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5
        )
        if username is not None:
            self.client.username_pw_set(username, password)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
        self.client.on_subscribe = self._on_subscribe
        self.client.connect(params["host"], params["port"], keepalive=15)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if _reason_failed(reason_code):
            self.failures.append(str(reason_code))
        else:
            self.connected.set()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        if _reason_failed(reason_code):
            self.disconnects.append(str(reason_code))

    def _on_message(self, client, userdata, message):
        self.received.append((message.topic, bytes(message.payload)))

    def _on_publish(self, client, userdata, mid, reason_code=None, properties=None):
        self.publish_results.append(str(reason_code))

    @staticmethod
    def _granted_value(code) -> int:
        value = getattr(code, "value", code)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 128

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties=None):
        granted = [self._granted_value(code) for code in (reason_codes or [])]
        with self._sub_mu:
            self._sub_grants[mid] = granted
            event = self._sub_locks.get(mid)
        if event is not None:
            event.set()

    def subscribe(self, topic: str) -> None:
        assert self.connected.wait(timeout=10), "probe never connected"
        result, mid = self.client.subscribe(topic, qos=1)
        assert result == mqtt.MQTT_ERR_SUCCESS, f"subscribe call failed: rc={result}"
        event = threading.Event()
        with self._sub_mu:
            self._sub_locks[mid] = event
        try:
            assert event.wait(timeout=10), (
                f"SUBACK never arrived for subscribe mid={mid} topic={topic!r}; "
                "publishing now would race broker-side subscription setup"
            )
        finally:
            with self._sub_mu:
                self._sub_locks.pop(mid, None)
        granted = self._sub_grants.get(mid, [])
        assert _is_suback_granted(granted), (
            f"broker refused subscription to {topic!r}: granted={granted}"
        )

    def publish_sync(self, topic: str, payload: bytes) -> None:
        assert self.connected.wait(timeout=10), "probe never connected"
        info = self.client.publish(topic, payload, qos=1, retain=False)
        info.wait_for_publish(timeout=10)

    def close(self) -> None:
        try:
            self.client.loop_stop()
        finally:
            try:
                self.client.disconnect()
            except Exception:  # noqa: BLE001 - test teardown
                pass


@pytest.fixture()
def device():
    params = mqtt_params()
    probe = _Probe(username=params["device_user"], password=params["device_password"])
    assert probe.connected.wait(timeout=10), f"device login failed: {probe.failures}"
    yield probe
    probe.close()


@pytest.fixture()
def backend():
    params = mqtt_params()
    probe = _Probe(username=params["backend_user"], password=params["backend_password"])
    assert probe.connected.wait(timeout=10), f"backend login failed: {probe.failures}"
    yield probe
    probe.close()


@needs_real_broker
def test_anonymous_access_denied():
    probe = _Probe(username=None)
    try:
        assert not probe.connected.wait(timeout=5), "anonymous CONNECT was accepted"
        assert probe.failures or probe.disconnects, (
            "anonymous denial left no protocol evidence"
        )
    finally:
        probe.close()


@needs_real_broker
def test_wrong_password_refused_not_hanging():
    params = mqtt_params()
    probe = _Probe(username=params["device_user"], password="wrong-password-value")
    try:
        assert not probe.connected.wait(timeout=5), "wrong password was accepted"
        assert probe.failures, "refusal carried no CONNACK failure reason"
    finally:
        probe.close()


@needs_real_broker
def test_device_telemetry_reaches_backend_subscriber(device, backend):
    marker = f"sec-probe-{uuid.uuid4().hex[:12]}".encode()
    backend.subscribe("coldguard/+/telemetry")
    device.publish_sync(DEVICE_TELEMETRY, marker)
    assert wait_for(
        lambda: any(payload == marker for _, payload in backend.received),
        timeout_s=10,
    ), "permitted device telemetry never arrived at the backend subscriber"


@needs_real_broker
def test_device_command_publish_denied(device):
    device.subscribe(DEVICE_COMMAND)
    marker = f"cmd-spoof-{uuid.uuid4().hex[:12]}".encode()
    device.publish_sync(DEVICE_COMMAND, marker)
    assert not wait_for(
        lambda: any(payload == marker for _, payload in device.received),
        timeout_s=3,
    ), "device published to its command topic and got it echoed: ACL missing"


@needs_real_broker
def test_device_cannot_publish_other_device_topic(device, backend):
    backend.subscribe("coldguard/+/telemetry")
    marker = f"xdev-{uuid.uuid4().hex[:12]}".encode()
    device.publish_sync("coldguard/other-device/telemetry", marker)
    assert not wait_for(
        lambda: any(payload == marker for _, payload in backend.received),
        timeout_s=3,
    ), "device published outside its namespace and the backend received it"


@needs_real_broker
def test_backend_cannot_spoof_device_telemetry(backend):
    params = mqtt_params()
    subscriber = _Probe(
        username=params["backend_user"], password=params["backend_password"]
    )
    try:
        assert subscriber.connected.wait(timeout=10)
        subscriber.subscribe("coldguard/+/telemetry")
        marker = f"spoof-{uuid.uuid4().hex[:12]}".encode()
        info = backend.client.publish(DEVICE_TELEMETRY, marker, qos=1, retain=False)
        info.wait_for_publish(timeout=10)
        assert not wait_for(
            lambda: any(payload == marker for _, payload in subscriber.received),
            timeout_s=3,
        ), "backend ingestion identity spoofed device telemetry"
    finally:
        subscriber.close()


def test_suback_grant_predicate_accepts_only_granted_qos():
    """F-01 negative proof: genuine grants pass, refusals fail (no broker)."""
    for code in (0, 1, 2):
        assert _is_suback_granted([code]) is True
        rc = ReasonCode(PacketTypes.SUBACK, identifier=code)
        assert _is_suback_granted([_Probe._granted_value(rc)]) is True
        assert rc.is_failure is False
    assert _is_suback_granted([0, 1, 2]) is True
    for code in (128, 131, 135, 143):
        assert _is_suback_granted([code]) is False
        rc = ReasonCode(PacketTypes.SUBACK, identifier=code)
        assert rc.is_failure is True
        assert _is_suback_granted([_Probe._granted_value(rc)]) is False
    assert _is_suback_granted([]) is False
    assert _is_suback_granted([1, 135]) is False
