"""Real backend MQTT subscriber with validated normalized persistence (C-W03).

One consumer instance per backend process (see ``main.lifespan``): it
subscribes through the real broker as the ``backend-ingest`` principal
and ingests every received message via
:func:`coldguard_backend.ingest.ingest_message` — raw evidence commits
first, then (iff strictly valid with topic/device agreement) the
normalized sample and any reported Twin update commit together.

Durability boundary, stated honestly:

* ``paho-mqtt`` 2.1.0 sends the QoS 1 PUBACK after :meth:`on_message`
  returns (automatic acknowledgement; the library additionally offers
  ``manual_ack``/``Client.ack`` deferred acknowledgement, which this
  consumer intentionally does not use). Automatic acknowledgement
  is a W02 trade-off, not a durability proof: the authority for
  "durably processed" is therefore the database transaction commit,
  not the PUBACK. No outage-window zero-loss is claimed; deferred
  acknowledgement with MQTT session/persistence semantics may be
  evaluated in the owning future milestone. MQTT acknowledgement and
  database commit remain distinct facts.
* Raw and normalized commits are separate local transactions
  (raw-before-derived): if normalized processing fails, the raw row is
  already committed and the failure is counted with topic context —
  never a silent rollback of required evidence. A message is never
  reported as persisted unless its raw transaction committed.
* No application exactly-once claim is made from MQTT QoS 1. What is
  claimed: duplicate deliveries that reach the database converge to
  one authoritative normalized sample via ``UNIQUE(device_id,
  boot_id, seq)`` + ``ON CONFLICT DO NOTHING`` (C-W03-04), with
  exact-vs-conflicting replay classification and observable metrics.

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
from coldguard_backend.ingest import IngestMetrics, ingest_message

log = logging.getLogger(__name__)

CLIENT_ID = "coldguard-backend-ingest"

SUBSCRIPTIONS: tuple[tuple[str, int], ...] = (
    ("coldguard/+/telemetry", 1),
    ("coldguard/+/event", 1),
    ("coldguard/+/state", 1),
    ("coldguard/+/health", 1),
)

_CONNECT_TIMEOUT_S = 10.0
# Bound database connect attempts so an outage is observed (and counted)
# promptly instead of waiting for the platform TCP timeout. Without this, a
# DB outage can stall the ingest callback for minutes and look like silence.
_DB_CONNECT_TIMEOUT_S = 5


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
        self._subscribed = threading.Event()
        self._startup_ready = threading.Event()
        self._connect_error: str | None = None
        self.received_count = 0
        self.persisted_count = 0
        self.error_count = 0
        # W03 observable accounting (process-local; resets on restart —
        # durable truth is direct database inspection, never these).
        self.metrics = IngestMetrics()

    # -- construction -------------------------------------------------

    @classmethod
    def from_config(cls, config: ColdGuardConfig) -> "MqttIngestConsumer":
        return cls(config)

    def _build_engine(self) -> Engine:
        return create_engine(
            self._config.database_url,
            pool_size=5,
            max_overflow=5,
            connect_args={"connect_timeout": _DB_CONNECT_TIMEOUT_S},
        )

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
        self._subscribed.clear()
        self._startup_ready.clear()
        self._connect_error = None
        try:
            self._start()
        except BaseException:
            self.stop()
            raise

    def _start(self) -> None:
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
        client.on_subscribe = self._on_subscribe
        self._client = client
        try:
            client.connect(self._config.mqtt_host, self._config.mqtt_port, keepalive=30)
        except OSError as exc:
            raise TimeoutError(
                f"mqtt broker unreachable at "
                f"{self._config.mqtt_host}:{self._config.mqtt_port}: {exc}"
            ) from exc
        client.loop_start()
        if not self._startup_ready.wait(timeout=_CONNECT_TIMEOUT_S):
            raise TimeoutError(
                f"mqtt broker at {self._config.mqtt_host}:{self._config.mqtt_port} "
                f"did not confirm subscriptions within {_CONNECT_TIMEOUT_S:.0f}s"
            )
        if self._connect_error is not None or not self._subscribed.is_set():
            raise ConnectionError(self._connect_error or "mqtt subscription lost during startup")

    def stop(self) -> None:
        """Shut down the loop, connection, and engine. Idempotent."""
        client, engine = self._shutdown_locked()
        try:
            if client is not None:
                try:
                    client.disconnect()
                except Exception:  # noqa: BLE001 - shutdown must not raise
                    log.warning("mqtt disconnect raised during stop", exc_info=True)
                finally:
                    client.loop_stop()
        finally:
            self._connected.clear()
            self._subscribed.clear()
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
            log.error("%s", self._connect_error)
            self._startup_ready.set()
            return
        self._connected.set()
        self._connect_error = None
        result, _mid = client.subscribe([
            (topic, mqtt.SubscribeOptions(qos=qos, retainAsPublished=True))
            for topic, qos in self._subscriptions
        ])
        if result != mqtt.MQTT_ERR_SUCCESS:
            self._connect_error = f"mqtt subscription request failed: rc={result}"
            log.error("%s", self._connect_error)
            self._startup_ready.set()

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties=None) -> None:
        if [code.value for code in reason_codes] == [qos for _, qos in self._subscriptions]:
            self._subscribed.set()
            log.info("mqtt subscribed to %d topic filters", len(self._subscriptions))
        else:
            self._connect_error = f"mqtt subscription rejected or downgraded: {reason_codes}"
            log.error("%s", self._connect_error)
        self._startup_ready.set()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None) -> None:
        self._connected.clear()
        self._subscribed.clear()
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
            outcome = ingest_message(
                engine,
                topic=message.topic,
                payload=bytes(message.payload),
                received_at=received_at,
                metrics=self.metrics,
                retained=message.retain,
            )
        except Exception:  # noqa: BLE001 - contained, counted, observable
            with self._lock:
                self.error_count += 1
            # No payload bytes in logs: payloads may carry device data;
            # topic + length is enough for triage.
            log.exception(
                "raw persistence failed: topic=%s bytes=%d; "
                "db commit absent, failure counted; auto-ack enabled so "
                "delivery may still be acknowledged after callback "
                "returns and the message may be unavailable for replay",
                message.topic,
                len(message.payload or b""),
            )
            return
        with self._lock:
            self.persisted_count += 1
        log.debug(
            "ingested: raw_id=%s raw_status=%s normalized=%s topic=%s",
            outcome["raw_id"],
            outcome["raw_status"],
            outcome["normalized"],
            message.topic,
        )

    # -- observability --------------------------------------------------

    def snapshot(self) -> dict[str, int | bool]:
        with self._lock:
            base: dict[str, int | bool] = {
                "running": self._running,
                "broker_connected": self._connected.is_set(),
                "subscribed": self._subscribed.is_set(),
                "received": self.received_count,
                "persisted": self.persisted_count,
                "errors": self.error_count,
            }
        # W03 duplicate/rejection accounting (process-local counters;
        # durable proof is database inspection, see ingest module note).
        # Consumer-level received/persisted/errors stay authoritative;
        # only the normalized/rejection breakdown is merged in.
        for key, value in self.metrics.snapshot().items():
            if key not in ("received", "raw_persisted", "raw_errors"):
                base[key] = value
        return base
