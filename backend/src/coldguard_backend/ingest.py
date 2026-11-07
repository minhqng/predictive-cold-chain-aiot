"""Raw-before-derived ingestion orchestration with observable accounting (C-W03-05).

For one received MQTT message::

    raw INSERT + COMMIT (authoritative source, always first)
    → strict + topic validation (already reflected in the raw status)
    → normalized INSERT and eligible Twin projection in one transaction
    → duplicate/conflict classification via the UNIQUE constraint
    → metrics update

Transaction strategy (minimal, no distributed machinery):

* raw and normalized commits are *separate* local transactions when
  called with an Engine (the consumer path). If normalized processing
  fails, the raw evidence row is already committed — the failure stays
  visible and recoverable instead of discarding evidence. With a
  Connection both steps join the caller's transaction; a savepoint
  protects raw evidence from failures in the normalized/Twin step.
* a normalized sample never appears without its committed raw source:
  ``telemetry.raw_id`` references the raw row committed in step one,
  and insertion order guarantees the reference exists.
* MQTT acknowledgement stays automatic (W02 boundary, unchanged): no
  exactly-once delivery is claimed, and DB-outage zero-loss is still
  out of scope. Application idempotency here covers *duplicate
  deliveries that reach the database*, not broker/DB zero-loss during
  outages.

Metrics are small, real, and honestly scoped: process-local counters
(accepted new samples, exact duplicates, conflicts, rejections by
class, normalization failures). They reset on restart and are never
presented as durable counts — durable truth is direct database
inspection (row counts per identity/status), which every proof and
test reconciles against.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.engine import Connection, Engine

from coldguard_backend.normalized_store import insert_normalized, map_to_row
from coldguard_backend.raw_store import RECEIVED_VALID, store_raw
from coldguard_backend.twin_store import project_reported
from coldguard_backend.validation import validate_telemetry_payload

log = logging.getLogger(__name__)


@dataclass
class IngestMetrics:
    """Process-local ingestion accounting (resets on restart)."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    received: int = 0
    raw_persisted: int = 0
    raw_errors: int = 0
    normalized_new: int = 0
    exact_duplicates: int = 0
    conflicts: int = 0
    rejected_schema: int = 0
    rejected_topic_mismatch: int = 0
    observed_other: int = 0
    normalization_failures: int = 0

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "received": self.received,
                "raw_persisted": self.raw_persisted,
                "raw_errors": self.raw_errors,
                "normalized_new": self.normalized_new,
                "exact_duplicates": self.exact_duplicates,
                "conflicts": self.conflicts,
                "rejected_schema": self.rejected_schema,
                "rejected_topic_mismatch": self.rejected_topic_mismatch,
                "observed_other": self.observed_other,
                "normalization_failures": self.normalization_failures,
            }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _decode_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Mark repeated provenance keys as ambiguous for Twin admission."""
    obj = {}
    for key, value in pairs:
        obj[key] = None if key in ("synthetic", "replay") and key in obj else value
    return obj


def _normalize(connection: Connection, row: dict[str, Any]) -> dict[str, Any]:
    outcome = insert_normalized(connection, row)
    if outcome["outcome"] == "inserted" and row["twin_eligible"]:
        project_reported(connection, outcome["id"])
    return outcome


def ingest_message(
    engine_or_conn: Engine | Connection,
    *,
    topic: str,
    payload: bytes,
    received_at: datetime | None = None,
    metrics: IngestMetrics | None = None,
    retained: bool = False,
) -> dict[str, Any]:
    """Ingest one MQTT message: raw commit first, then normalized iff valid.

    Returns ``{"raw_id", "raw_status", "normalized": <outcome dict> |
    None}``. Normalized outcomes are ``inserted`` / ``exact_duplicate``
    / ``conflict`` (see :mod:`coldguard_backend.normalized_store`), or
    ``rejected:<STATUS>`` / ``observed`` / ``failed`` markers when no
    normalized attempt applies. Raw commit failures propagate (never a
    fake success); normalized failures are contained, counted, and
    reported — the committed raw row remains as evidence.
    """
    stamp = received_at or _utcnow()
    if metrics is not None:
        with metrics._lock:
            metrics.received += 1
    # Step 1: raw evidence commits first (own transaction on Engine).
    stored = store_raw(engine_or_conn, topic=topic, payload=payload, received_at=stamp)
    if metrics is not None:
        with metrics._lock:
            metrics.raw_persisted += 1
    status = stored["ingest_status"]
    if status != RECEIVED_VALID:
        if metrics is not None:
            with metrics._lock:
                if status in ("RECEIVED_INVALID_SCHEMA", "RECEIVED_MALFORMED_JSON"):
                    metrics.rejected_schema += 1
                elif status == "REJECTED_TOPIC_MISMATCH":
                    metrics.rejected_topic_mismatch += 1
                else:
                    metrics.observed_other += 1
        return {
            "raw_id": stored["id"],
            "raw_status": status,
            "normalized": f"rejected:{status}" if status != "RECEIVED_OBSERVED" else "observed",
        }
    # Step 2: the raw row is RECEIVED_VALID, hence strictly validated
    # with topic agreement already proven at classification time.
    # Re-derive the validated model from the exact received bytes so
    # mapping input equals stored evidence (VALID implies UTF-8 JSON).
    try:
        parsed = json.loads(payload.decode("utf-8"), object_pairs_hook=_decode_object)
        validated, errors = validate_telemetry_payload(parsed)
        if validated is None:  # pragma: no cover - defensive; status says valid
            raise RuntimeError(f"raw row marked valid but revalidation failed: {errors}")
        row = map_to_row(validated, raw_id=stored["id"], received_at=stamp)
        row["twin_eligible"] = (
            not retained
            and parsed.get("synthetic", False) is False
            and parsed.get("replay", False) is False
        )
        if isinstance(engine_or_conn, Engine):
            with engine_or_conn.begin() as connection:
                outcome = _normalize(connection, row)
        else:
            with engine_or_conn.begin_nested():
                outcome = _normalize(engine_or_conn, row)
    except Exception:
        if metrics is not None:
            with metrics._lock:
                metrics.normalization_failures += 1
        log.exception(
            "normalized/Twin transaction failed: topic=%s raw_id=%s; raw evidence kept",
            topic,
            stored["id"],
        )
        return {"raw_id": stored["id"], "raw_status": status, "normalized": "failed"}
    if metrics is not None:
        with metrics._lock:
            if outcome["outcome"] == "inserted":
                metrics.normalized_new += 1
            elif outcome["outcome"] == "exact_duplicate":
                metrics.exact_duplicates += 1
            else:
                metrics.conflicts += 1
    if outcome["outcome"] == "conflict":
        log.warning(
            "conflicting replay for identity (%s, %s, %s): raw_id=%s kept as "
            "evidence; authoritative normalized id=%s NOT overwritten",
            row["device_id"],
            row["boot_id"],
            row["seq"],
            stored["id"],
            outcome["id"],
        )
    return {"raw_id": stored["id"], "raw_status": status, "normalized": outcome}
