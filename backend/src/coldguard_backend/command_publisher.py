"""Bounded, durable MQTT command publisher (C-W06-02).

Publishes the canonical Doc 02 §28.1 command envelope to
``coldguard/{device_id}/command`` with ``QoS=1`` and ``retain=False`` (Doc 02
§7: retained stale actuation is unsafe). The same ``command_id`` is reused on
every retry; a retry never creates a new logical command.

Durable three-phase design and its crash windows:

1. **Fence (DB txn).** Lock the command, refuse it if expired (-> EXPIRED) or
   not publishable, fence concurrent publishers with a PENDING attempt row,
   and commit. Nothing is sent to the broker yet.
2. **Publish (broker).** Send QoS 1 / retain=false and wait for the broker
   PUBACK. A PUBACK proves broker acceptance only — never device delivery,
   ACK, or physical actuation.
3. **Record (DB txn).** Persist the attempt outcome and advance the command:
   PUBACK -> PUBLISHED, definite failure -> PUBLISH_FAILED, timeout/ambiguous
   -> UNKNOWN (the device may or may not have applied it).

Crash window: a crash after phase 1 but before phase 3 leaves a PENDING
attempt and a non-settled command. ``reconcile_pending_attempts`` resolves
these to UNKNOWN on recovery and NEVER auto-replays them; an operator retry
reuses the command_id and re-checks expiry. A reconnect therefore cannot
resend an expired command (phase 1 expiry gate) nor silently re-actuate.

The transport is injected so unit tests use a fake publisher and provider
tests use a real disposable Mosquitto. No physical hardware is involved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.engine import Engine

from coldguard_backend import command_store as cs
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
            phase1 = cs.begin_publish_attempt(
                connection, command_id, payload_sha256=row["payload_sha256"], now=now
            )
        if phase1["outcome"] != "ready":
            return {"outcome": phase1["outcome"], "status": phase1["command"]["status"]}

        command = command_from_row(phase1["command"])
        payload = cs.canonical_command_bytes(command)
        topic = command_topic(command.device_id)
        attempt_id = phase1["attempt_id"]
        try:
            result = self._publish(topic, payload, COMMAND_QOS, COMMAND_RETAIN)
        except Exception as exc:  # noqa: BLE001 - transport failure is an outcome
            log.warning("command publish transport error: command_id=%s (%s)", command_id, exc)
            result = PublishResult(outcome="UNKNOWN", reason=f"transport_error:{exc}")

        with self._engine.begin() as connection:
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
    """Real MQTT transport over a connected paho client (disposable broker only)."""

    def __init__(self, client: Any, *, timeout_s: float = 10.0) -> None:
        self._client = client
        self._timeout_s = timeout_s

    def __call__(self, topic: str, payload: bytes, qos: int, retain: bool) -> PublishResult:
        info = self._client.publish(topic, payload, qos=qos, retain=retain)
        if info.rc != 0:
            return PublishResult(outcome="FAILED", mid=info.mid, reason=f"mqtt_rc:{info.rc}")
        try:
            info.wait_for_publish(timeout=self._timeout_s)
        except (ValueError, RuntimeError) as exc:
            return PublishResult(outcome="UNKNOWN", mid=info.mid, reason=f"wait_error:{exc}")
        except TimeoutError:
            return PublishResult(outcome="TIMEOUT", mid=info.mid, reason="puback_timeout")
        if info.is_published():
            return PublishResult(outcome="PUBACK", mid=info.mid)
        return PublishResult(outcome="UNKNOWN", mid=info.mid, reason="not_published")