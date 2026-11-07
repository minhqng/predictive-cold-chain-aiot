"""Backend MQTT command-ACK consumer with durable evidence (C-W06-03).

Subscribes to ``coldguard/+/command_ack`` (QoS 1) as the backend ingestion
principal and persists every receipt as evidence before interpretation. ACK
data is command lifecycle evidence — it is never ingested as ordinary
normalized telemetry.

For each receipt the consumer:
* preserves the exact raw bytes and their SHA-256;
* strict-validates the ACK schema and data types;
* proves topic/device identity agreement;
* correlates by an existing ``command_id`` and the target device;
* quarantines unmatched/forged/inconsistent ACKs (retained, never applied);
* handles duplicates idempotently and preserves conflicting ACKs as evidence;
* lets the store arbitrate late ACKs so an expired command is never resurrected.

An ACK may report an applied output; it is never treated as measured thermal
success (Doc 02 §32.2). Database commit, not MQTT PUBACK, is the durability
authority (automatic acknowledgement is the W02 boundary, unchanged here).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine

from coldguard_backend import command_store as cs
from coldguard_backend.config import ColdGuardConfig
from coldguard_backend.mqtt_consumer import reason_failed
from coldguard_backend.validation import (
    ack_topic_device_id,
    validate_ack_topic_identity,
    validate_command_ack,
)

log = logging.getLogger(__name__)

CLIENT_ID = "coldguard-backend-ack"
SUBSCRIPTIONS: tuple[tuple[str, int], ...] = (("coldguard/+/command_ack", 1),)
_CONNECT_TIMEOUT_S = 10.0
_DB_CONNECT_TIMEOUT_S = 5


class AckMetrics:
    """Process-local ACK accounting (resets on restart; DB is authoritative)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.received = 0
        self.valid = 0
        self.malformed_json = 0
        self.invalid_schema = 0
        self.topic_mismatch = 0
        self.unmatched = 0
        self.conflict = 0
        self.duplicate = 0
        self.late = 0
        self.errors = 0

    def bump(self, name: str) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + 1)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "received": self.received, "valid": self.valid,
                "malformed_json": self.malformed_json, "invalid_schema": self.invalid_schema,
                "topic_mismatch": self.topic_mismatch, "unmatched": self.unmatched,
                "conflict": self.conflict, "duplicate": self.duplicate,
                "late": self.late, "errors": self.errors,
            }


def classify_ack(topic: str, payload: bytes) -> dict:
    """Pure classification of one ACK receipt (unit-testable, no database)."""
    sha = hashlib.sha256(payload).hexdigest()
    topic_device = ack_topic_device_id(topic) or ""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {"validity": "MALFORMED_JSON", "ack": None, "raw_payload": payload.decode("utf-8", "replace"),
                "payload_sha256": sha, "topic_device_id": topic_device,
                "diagnostics": [{"code": "NOT_UTF8", "message": str(exc)[:200]}]}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"validity": "MALFORMED_JSON", "ack": None, "raw_payload": text,
                "payload_sha256": sha, "topic_device_id": topic_device,
                "diagnostics": [{"code": "JSON_DECODE_ERROR", "message": str(exc)[:200]}]}
    ack, errors = validate_command_ack(parsed)
    if ack is None:
        return {"validity": "INVALID_SCHEMA", "ack": None, "raw_payload": text,
                "payload_sha256": sha, "topic_device_id": topic_device, "diagnostics": errors}
    topic_errors = validate_ack_topic_identity(topic, ack)
    if topic_errors:
        return {"validity": "TOPIC_MISMATCH", "ack": ack, "raw_payload": text,
                "payload_sha256": sha, "topic_device_id": topic_device, "diagnostics": topic_errors}
    return {"validity": "VALID", "ack": ack, "raw_payload": text,
            "payload_sha256": sha, "topic_device_id": topic_device, "diagnostics": None}


class AckConsumer:
    """Single stateful MQTT command-ACK → Postgres consumer."""

    def __init__(
        self,
        config: ColdGuardConfig,
        *,
        client_id: str = CLIENT_ID,
        subscriptions: tuple[tuple[str, int], ...] = SUBSCRIPTIONS,
    ) -> None:
        self._config = config
        self._client_id = client_id
        self._subscriptions = subscriptions
        self._engine: Engine | None = None
        self._client: mqtt.Client | None = None
        self._lock = threading.Lock()
        self._running = False
        self._subscribed = threading.Event()
        self._startup_ready = threading.Event()
        self._startup_error: str | None = None
        self.metrics = AckMetrics()

    @classmethod
    def from_config(cls, config: ColdGuardConfig) -> "AckConsumer":
        return cls(config)

    def _build_engine(self) -> Engine:
        return create_engine(
            self._config.database_url,
            pool_size=5, max_overflow=5,
            connect_args={"connect_timeout": _DB_CONNECT_TIMEOUT_S},
        )

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                raise RuntimeError("AckConsumer is already running")
            self._running = True
        self._subscribed.clear()
        self._startup_ready.clear()
        self._startup_error = None
        try:
            self._start()
        except BaseException:
            self.stop()
            raise

    def _start(self) -> None:
        if not self._config.mqtt_username or not self._config.mqtt_password:
            raise ValueError("ACK ingestion requires provisioned MQTT credentials")
        self._engine = self._build_engine()
        with self._engine.connect() as connection:
            connection.execute(select(cs.command_acks.c.id).limit(0))
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=self._client_id, protocol=mqtt.MQTTv5,
        )
        client.username_pw_set(self._config.mqtt_username, self._config.mqtt_password)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        client.on_subscribe = self._on_subscribe
        self._client = client
        try:
            client.connect(self._config.mqtt_host, self._config.mqtt_port, keepalive=30)
        except OSError as exc:
            raise TimeoutError(
                f"mqtt broker unreachable at {self._config.mqtt_host}:{self._config.mqtt_port}: {exc}"
            ) from exc
        client.loop_start()
        if not self._startup_ready.wait(timeout=_CONNECT_TIMEOUT_S):
            raise TimeoutError("mqtt broker did not confirm the ACK subscription within timeout")
        if self._startup_error is not None or not self._subscribed.is_set():
            raise ConnectionError(self._startup_error or "mqtt ACK subscription lost during startup")

    def wait_subscribed(self, timeout_s: float = _CONNECT_TIMEOUT_S) -> bool:
        """Block until the broker has acknowledged the ACK subscription.

        Publishing test/ops traffic before SUBACK can race the subscription and
        lose a non-retained QoS 1 message; callers that must not miss the first
        ACK wait on this readiness signal.
        """
        return self._subscribed.wait(timeout=timeout_s)

    def stop(self) -> None:
        client, engine = self._shutdown_locked()
        try:
            if client is not None:
                try:
                    client.disconnect()
                except Exception:  # noqa: BLE001
                    log.warning("mqtt disconnect raised during stop", exc_info=True)
                finally:
                    client.loop_stop()
        finally:
            self._subscribed.clear()
            if engine is not None:
                engine.dispose()

    def _shutdown_locked(self):
        with self._lock:
            self._running = False
            client, self._client = self._client, None
            engine, self._engine = self._engine, None
        return client, engine

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if reason_failed(reason_code):
            self._subscription_failed(
                f"mqtt authentication refused for user {self._config.mqtt_username!r} "
                f"(reason {reason_code}); check provisioned broker credentials"
            )
            return
        result, _mid = client.subscribe([
            (topic, mqtt.SubscribeOptions(qos=qos, retainAsPublished=True, retainHandling=2))
            for topic, qos in self._subscriptions
        ])
        if result != mqtt.MQTT_ERR_SUCCESS:
            self._subscription_failed(f"mqtt ACK subscription failed: rc={result}")

    def _subscription_failed(self, message: str) -> None:
        self._startup_error = message
        log.error("%s", message)
        self._startup_ready.set()

    def _on_subscribe(self, client, userdata, mid, reason_code_list, properties=None) -> None:
        expected = [qos for _, qos in self._subscriptions]
        if [code.value for code in reason_code_list] != expected:
            self._subscription_failed(f"mqtt ACK subscription rejected or downgraded: {reason_code_list}")
            return
        self._subscribed.set()
        self._startup_ready.set()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None) -> None:
        self._subscribed.clear()
        if reason_failed(reason_code):
            log.warning("ack consumer disconnected unexpectedly: %s", reason_code)

    def _on_message(self, client, userdata, message) -> None:
        received_at = datetime.now(timezone.utc)
        self.metrics.bump("received")
        engine = self._engine
        if engine is None:
            self.metrics.bump("errors")
            log.error("ack dropped: consumer engine unavailable")
            return
        classified = classify_ack(message.topic, bytes(message.payload))
        if message.retain and classified["validity"] == "VALID":
            classified.update(validity="CONFLICT", diagnostics={"code": "RETAINED_ACK"})
        try:
            with engine.begin() as connection:
                result = cs.record_ack(
                    connection,
                    topic_device_id=classified["topic_device_id"],
                    raw_payload=classified["raw_payload"],
                    payload_sha256=classified["payload_sha256"],
                    backend_received_at=received_at,
                    ack=classified["ack"],
                    validity=classified["validity"],
                    diagnostics=classified["diagnostics"],
                )
        except Exception:  # noqa: BLE001 - contained, counted, observable
            self.metrics.bump("errors")
            log.exception("ack persistence failed: topic=%s", message.topic)
            return
        outcome = result["outcome"]
        metric_for = {
            "applied": "valid", "malformed_json": "malformed_json",
            "invalid_schema": "invalid_schema", "topic_mismatch": "topic_mismatch",
            "unmatched": "unmatched", "conflict": "conflict",
            "duplicate": "duplicate", "late_expired": "late",
        }
        self.metrics.bump(metric_for.get(outcome, "valid"))

    def snapshot(self) -> dict:
        with self._lock:
            base = {"running": self._running, "subscribed": self._subscribed.is_set()}
        base.update(self.metrics.snapshot())
        return base
