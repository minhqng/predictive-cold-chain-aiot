"""Real backend MQTT subscriber with durable raw persistence (C-W02-03).

One consumer instance per backend process (see ``main.lifespan``): it
subscribes through the real broker as the ``backend-ingest`` principal
and writes every received message to ``telemetry_raw`` via
:func:`coldguard_backend.raw_store.store_raw`.

Durability boundary, stated honestly:

* ``paho-mqtt`` acknowledges QoS 1 deliveries at the MQTT protocol
  level (PUBACK) before :meth:`on_message` runs; the client library
  offers no deferred-acknowledgement hook. The authority for "durably
  processed" is therefore the database transaction commit inside
  ``store_raw``, not the PUBACK.
* If the DB insert fails, the failure is counted, logged with topic
  context, and the exception is contained so the network loop survives;
  the broker may redeliver, which lands as a separate observable raw
  row (W02 keeps duplicates visible; W03 owns dedup). A message is
  never reported as persisted unless its transaction committed.
* No application exactly-once claim is made from MQTT QoS 1.

Lifecycle: :meth:`start` connects (failing fast with a distinguishable
error for refused credentials vs. unreachable broker), subscribes, and
runs the network loop on one background thread; :meth:`stop` is
idempotent and disposes the database engine. Reconnects resubscribe in
``on_connect`` because the consumer uses a clean session. The client id
is intentionally stable for operations; running two backend processes
with the same id would steal each other's session at the broker, so
multi-process ingestion is out of scope for this one-process slice.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from coldguard_backend.config import ColdGuardConfig
from coldguard_backend.raw_store import store_raw

log = logging.getLogger(__name__)

CLIENT_ID = "coldguard-backend-ingest"

SUBSCRIPTIONS: tuple[tuple[str, int], ...] = (
    ("coldguard/+/telemetry", 1),
    ("coldguard/+/event", 1),
    ("coldguard/+/state", 1),
    ("coldguard/+/health", 1),
)

_CONNECT_TIMEOUT_S = 10.0


def reason_failed(reason) -> bool:
    """True when an MQTT reason code / rc signals failure.

    Covers both paho callback shapes: MQTT v5 ``ReasonCode`` objects
    (which expose ``is_failure`` as a boolean property in paho-mqtt
    2.x) and plain integer return codes from the MQTT v3 path.
    ``None`` (client-initiated disconnect) is not a failure.
    """
    if reason is None:
        return False
    is_failure = getattr(reason, "is_failure", None)
    if isinstance(is_failure, bool):
        return is_failure
    if callable(is_failure):
        return bool(is_failure())
    value = getattr(reason, "value", reason)
    try:
        return int(value) != 0
    except (TypeError, ValueError):
        return True


class MqttIngestConsumer:
    """Single stateful MQTT→Postgres ingestion consumer."""

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
        self._connected = threading.Event()
        self._connect_error: str | None = None
        self.received_count = 0
        self.persisted_count = 0
        self.error_count = 0

    # -- construction -------------------------------------------------

    @classmethod
    def from_config(cls, config: ColdGuardConfig) -> "MqttIngestConsumer":
        return cls(config)

    def _build_engine(self) -> Engine:
        return create_engine(self._config.database_url, pool_size=5, max_overflow=5)

    # -- lifecycle ----------------------------------------------------

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(self) -> None:
        """Connect, subscribe, and begin background ingestion.

        Raises:
            ConnectionError: credentials refused (distinguishable from
                network failure by its message).
            TimeoutError: broker unreachable within the connect timeout.
            RuntimeError: this instance is already running (no duplicate
                consumers from one process).
        """
        with self._lock:
            if self._running:
                raise RuntimeError("MqttIngestConsumer is already running")
            self._running = True
        self._connected.clear()
        self._connect_error = None
        self._engine = self._build_engine()
        # MQTT 5 is the canonical preference (Doc 02 section 6.1); the
        # v3.1.1 subset would be acceptable only if chosen intentionally.
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self._client_id,
            protocol=mqtt.MQTTv5,
        )
        if self._config.mqtt_username:
            client.username_pw_set(self._config.mqtt_username, self._config.mqtt_password)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        self._client = client
        try:
            client.connect(self._config.mqtt_host, self._config.mqtt_port, keepalive=30)
        except Exception as exc:
            self._shutdown_locked()
            raise TimeoutError(
                f"mqtt broker unreachable at "
                f"{self._config.mqtt_host}:{self._config.mqtt_port}: {exc}"
            ) from exc
        client.loop_start()
        if not self._connected.wait(timeout=_CONNECT_TIMEOUT_S):
            self.stop()
            raise TimeoutError(
                f"mqtt broker at {self._config.mqtt_host}:{self._config.mqtt_port} "
                f"did not answer CONNECT within {_CONNECT_TIMEOUT_S:.0f}s"
            )
        if self._connect_error is not None:
            self.stop()
            raise ConnectionError(self._connect_error)

    def stop(self) -> None:
        """Shut down the loop, connection, and engine. Idempotent."""
        client, engine = self._shutdown_locked()
        if client is not None:
            try:
                client.loop_stop()
            finally:
                try:
                    client.disconnect()
                except Exception:  # noqa: BLE001 - shutdown must not raise
                    log.warning("mqtt disconnect raised during stop", exc_info=True)
        if engine is not None:
            engine.dispose()

    def _shutdown_locked(self) -> tuple[mqtt.Client | None, Engine | None]:
        with self._lock:
            self._running = False
            client, self._client = self._client, None
            engine, self._engine = self._engine, None
        return client, engine

    # -- callbacks (network-loop thread) -------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if reason_failed(reason_code):
            # Authentication/authorization refusal (e.g. 0x05 Not
            # Authorized) is recorded, not mistaken for connectivity loss.
            self._connect_error = (
                f"mqtt authentication refused for user "
                f"{self._config.mqtt_username!r} (reason {reason_code}); "
                f"check provisioned broker credentials"
            )
            self._connected.set()
            return
        for topic, qos in self._subscriptions:
            result, _mid = client.subscribe(topic, qos=qos)
            if result != mqtt.MQTT_ERR_SUCCESS:
                log.error("mqtt subscribe failed: topic=%s qos=%s rc=%s", topic, qos, result)
        log.info("mqtt connected; subscribed to %d topic filters", len(self._subscriptions))
        self._connected.set()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if reason_failed(reason_code):
            log.warning("mqtt disconnected unexpectedly: %s", reason_code)

    def _on_message(self, client, userdata, message) -> None:
        received_at = datetime.now(timezone.utc)
        with self._lock:
            self.received_count += 1
        engine = self._engine
        if engine is None:
            with self._lock:
                self.error_count += 1
            log.error("mqtt message dropped: consumer engine unavailable")
            return
        try:
            stored = store_raw(
                engine,
                topic=message.topic,
                payload=bytes(message.payload),
                received_at=received_at,
            )
        except Exception:  # noqa: BLE001 - contained, counted, observable
            with self._lock:
                self.error_count += 1
            # No payload bytes in logs: payloads may carry device data;
            # topic + length is enough for triage.
            log.exception(
                "raw persistence failed: topic=%s bytes=%d; "
                "message NOT acknowledged as processed",
                message.topic,
                len(message.payload or b""),
            )
            return
        with self._lock:
            self.persisted_count += 1
        log.debug(
            "raw persisted: id=%s status=%s topic=%s",
            stored["id"],
            stored["ingest_status"],
            message.topic,
        )

    # -- observability --------------------------------------------------

    def snapshot(self) -> dict[str, int | bool]:
        with self._lock:
            return {
                "running": self._running,
                "received": self.received_count,
                "persisted": self.persisted_count,
                "errors": self.error_count,
            }
