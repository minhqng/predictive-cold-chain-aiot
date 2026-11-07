"""Bounded, durable MQTT command publisher (C-W06-02).

Publishes the canonical Doc 02 §28.1 command envelope to
``coldguard/{device_id}/command`` with ``QoS=1`` and ``retain=False`` (Doc 02
§7: retained stale actuation is unsafe). The same ``command_id`` is reused on
every retry; a retry never creates a new logical command.

Durable three-phase design and its crash windows:

1. **Fence (DB txn).** Lock the command, refuse it if expired (-> EXPIRED) or
   not publishable, fence concurrent publishers with a PENDING attempt row,
   and commit. Nothing is sent to the broker yet.
2. **Dispatch (new DB txn).** Recheck desired authority and expiry under the
   per-device fence. Send QoS 1 / retain=false and wait for broker PUBACK.
3. **Record (same DB txn).** Persist the attempt outcome and advance the command:
   PUBACK -> PUBLISHED, definite failure -> PUBLISH_FAILED, timeout/ambiguous
   -> UNKNOWN (the device may or may not have applied it).

Crash window: a crash after phase 1 but before phase 3 leaves a PENDING
attempt and a non-settled command. ``reconcile_pending_attempts`` resolves
these to UNKNOWN on recovery and NEVER auto-replays them; an operator retry
reuses the command_id and re-checks expiry. The Paho transport does not
reconnect or replay queued attempts.

The transport is injected so unit tests use a fake publisher and provider
tests use a real disposable Mosquitto. No physical hardware is involved.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from sqlalchemy.engine import Engine

from coldguard_backend import command_store as cs
from coldguard_backend.command_service import current_desired_command_id
from coldguard_backend.contracts import Command

log = logging.getLogger(__name__)

COMMAND_QOS = 1
COMMAND_RETAIN = False


@dataclass(frozen=True)
class PublishResult:
    """Broker-level publish outcome (not a device ACK)."""

    outcome: str  # PUBACK | FAILED | TIMEOUT | UNKNOWN
    mid: int | None = None
    reason: str | None = None


PublishFn = Callable[[str, bytes, int, bool], PublishResult]


def command_topic(device_id: str) -> str:
    return f"coldguard/{device_id}/command"


def command_from_row(row: dict[str, Any]) -> Command:
    """Reconstruct the canonical envelope from a stored command row."""
    return Command.model_validate(
        {
            "schema_version": row["schema_version"],
            "command_id": row["command_id"],
            "device_id": row["device_id"],
            "created_at": row["created_at"].isoformat(),
            "expires_at": row["expires_at"].isoformat(),
            "controller_id": row["controller_id"],
            "policy_version": row["policy_version"],
            "reason_code": row["reason_code"],
            "action": {"cooling": row["action_cooling"], "duty": row["action_duty"]},
            "prediction_id": row["prediction_id"],
            "run_id": row["run_id"],
            "expected_twin_version": row["expected_twin_version"],
        }
    )


class CommandPublisher:
    """Publishes stored commands through an injected MQTT transport."""

    def __init__(self, engine: Engine, publish_fn: PublishFn) -> None:
        self._engine = engine
        self._publish = publish_fn

    def publish(self, command_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        with self._engine.begin() as connection:
            row = cs.get_command(connection, command_id)
            if row is None:
                raise cs.CommandNotFound(f"command {command_id!r} does not exist")
            cs.lock_command_device(connection, row["device_id"])
            stamp = now or datetime.now(timezone.utc)
            if row["expires_at"] < stamp:
                cs.expire_command(connection, command_id, now=stamp)
                return {"outcome": "expired", "status": cs.get_command(connection, command_id)["status"]}
            if current_desired_command_id(connection, row["device_id"]) != command_id:
                return {"outcome": "superseded", "status": row["status"]}
            phase1 = cs.begin_publish_attempt(
                connection, command_id, payload_sha256=row["payload_sha256"], now=now
            )
        if phase1["outcome"] != "ready":
            return {"outcome": phase1["outcome"], "status": phase1["command"]["status"]}

        command = command_from_row(phase1["command"])
        payload = cs.canonical_command_bytes(command)
        topic = command_topic(command.device_id)
        attempt_id = phase1["attempt_id"]
        with self._engine.begin() as connection:
            # Keep supersession/recovery serialized through transport handoff.
            # The command row remains unlocked while waiting for the broker so
            # the device ACK can commit on a separate connection.
            cs.lock_command_device(connection, command.device_id)
            row = cs.get_command(connection, command_id)
            attempt = cs.get_attempt(connection, attempt_id)
            if attempt["outcome"] != "PENDING":
                return {"outcome": "not_publishable", "status": row["status"]}
            desired_id = current_desired_command_id(connection, command.device_id)
            stamp = now or datetime.now(timezone.utc)
            reason = None
            if desired_id != command_id:
                reason = "superseded"
            elif row["expires_at"] < stamp:
                reason = "expired"
            elif row["status"] not in cs.PUBLISHABLE_STATES:
                reason = "not_publishable"
            if reason is not None:
                cs.complete_attempt(connection, attempt_id, outcome="FAILED", broker_reason=reason)
                if reason == "expired" and row["status"] not in cs.SETTLED_STATES:
                    cs.expire_command(connection, command_id, now=stamp)
                    row = cs.get_command(connection, command_id)
                return {"outcome": reason, "status": row["status"], "attempt_id": attempt_id}
            try:
                result = self._publish(topic, payload, COMMAND_QOS, COMMAND_RETAIN)
            except Exception as exc:  # noqa: BLE001 - transport failure is an outcome
                log.warning("command publish transport error: command_id=%s (%s)", command_id, exc)
                result = PublishResult(outcome="UNKNOWN", reason=f"transport_error:{exc}")
            new = cs.finish_publish_attempt(
                connection, command_id, attempt_id,
                outcome=result.outcome, broker_reason=result.reason,
                mqtt_mid=result.mid, now=now,
            )
        return {
            "outcome": result.outcome.lower(),
            "status": new["status"],
            "attempt_id": attempt_id,
            "topic": topic,
            "qos": COMMAND_QOS,
            "retain": COMMAND_RETAIN,
        }


class PahoCommandTransport:
    """Own the publish callback of a dedicated, non-reconnecting MQTT 5 client."""

    def __init__(self, client: mqtt.Client, *, timeout_s: float = 10.0) -> None:
        # Paho 2.1 exposes this setting only at client construction. Refuse
        # a reconnecting client because it can automatically resend queued QoS 1.
        if client.protocol != mqtt.MQTTv5 or client._reconnect_on_failure:
            raise ValueError("command transport requires MQTT 5 with reconnect_on_failure=False")
        self._client = client
        self._timeout_s = timeout_s
        self._lock = threading.Lock()
        self._puback = None
        self._retired = False
        client.on_publish = self._on_publish

    def _on_publish(self, client, userdata, mid, reason_code, properties) -> None:
        self._puback = (mid, reason_code)

    def __call__(self, topic: str, payload: bytes, qos: int, retain: bool) -> PublishResult:
        with self._lock:
            if self._retired or not self._client.is_connected():
                return PublishResult("FAILED", reason="mqtt_not_connected")
            self._puback = None
            expiry = datetime.fromisoformat(json.loads(payload)["expires_at"])
            remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
            if remaining < 0:
                return PublishResult("FAILED", reason="expired_before_mqtt_send")
            properties = Properties(PacketTypes.PUBLISH)
            properties.MessageExpiryInterval = min(int(remaining), 2**32 - 1)
            return self._send(topic, payload, qos, retain, properties)

    def _send(self, topic, payload, qos, retain, properties) -> PublishResult:
        info = self._client.publish(topic, payload, qos=qos, retain=retain, properties=properties)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            self._retire()
            return PublishResult("UNKNOWN", mid=info.mid, reason=f"mqtt_rc:{info.rc}")
        try:
            info.wait_for_publish(timeout=self._timeout_s)
            if info.is_published() and self._puback is not None and self._puback[0] == info.mid:
                reason = self._puback[1]
                return PublishResult("FAILED" if reason.is_failure else "PUBACK", info.mid, str(reason))
        except (ValueError, RuntimeError, TimeoutError) as exc:
            self._retire()
            return PublishResult("UNKNOWN", mid=info.mid, reason=f"wait_error:{exc}")
        self._retire()
        return PublishResult("TIMEOUT", mid=info.mid, reason="puback_timeout")

    def _retire(self) -> None:
        self._retired = True
        self._client.disconnect()
