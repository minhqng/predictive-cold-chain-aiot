"""Raw-before-derived ingestion orchestration with observable accounting (C-W03-05).

For one received MQTT message::

    raw INSERT + COMMIT (authoritative source, always first)
    → strict + topic validation (already reflected in the raw status)
    → normalized INSERT + COMMIT iff raw status is RECEIVED_VALID
    → duplicate/conflict classification via the UNIQUE constraint
    → metrics update

Transaction strategy (minimal, no distributed machinery):

* raw and normalized commits are *separate* local transactions when
  called with an Engine (the consumer path). If normalized processing
  fails, the raw evidence row is already committed — the failure stays
  visible and recoverable instead of silently discarding required
  rejected evidence (a shared transaction would roll the raw row back
  on a normalized failure). With a Connection both steps join the
  caller's transaction instead.
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

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.engine import Connection, Engine

from coldguard_backend.normalized_store import insert_normalized, map_to_row
from coldguard_backend.raw_store import RECEIVED_VALID, store_raw
from coldguard_backend.twin_store import update_twin_reported
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


def ingest_message(
    engine_or_conn: Engine | Connection,
    *,
    topic: str,
    payload: bytes,
    received_at: datetime | None = None,
    metrics: IngestMetrics | None = None,
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
    import json as _json

    try:
        parsed = _json.loads(payload.decode("utf-8"))
        validated, errors = validate_telemetry_payload(parsed)
        if validated is None:  # pragma: no cover - defensive; status says valid
            raise RuntimeError(f"raw row marked valid but revalidation failed: {errors}")
        row = map_to_row(validated, raw_id=stored["id"], received_at=stamp)
        outcome = insert_normalized(engine_or_conn, row)
    except Exception:
        if metrics is not None:
            with metrics._lock:
                metrics.normalization_failures += 1
        log.exception(
            "normalized persistence failed: topic=%s raw_id=%s; "
            "raw evidence committed, sample not normalized",
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
    twin_outcome: dict[str, Any] | None = None
    if outcome["outcome"] == "inserted":
        try:
            reported_snapshot = {
                "t1_c": row["t1_c"],
                "t2_c": row["t2_c"],
                "t3_c": row["t3_c"],
                "t_air_c": row["t_air_c"],
                "rh_pct": row["rh_pct"],
                "door_state": row["door_state"],
                "cooling_voltage_v": row["cooling_voltage_v"],
                "cooling_current_a": row["cooling_current_a"],
                "cooling_power_w": row["cooling_power_w"],
                "cooling_energy_counter_wh": row["cooling_energy_counter_wh"],
                "applied_cooling": row["applied_cooling"],
                "applied_duty": row["applied_duty"],
                "thermal_quality": row["thermal_quality"],
                "environment_quality": row["environment_quality"],
                "electrical_quality": row["electrical_quality"],
                "overall_quality": row["overall_quality"],
                "device_mode": row["device_mode"],
                "captured_at": row["time"].isoformat() if row.get("time") else None,
                "raw_id": row["raw_id"],
                "run_id": row.get("run_id"),
            }
            twin_outcome = update_twin_reported(
                engine_or_conn,
                device_id=row["device_id"],
                boot_id=row["boot_id"],
                seq=row["seq"],
                state=reported_snapshot,
                reported_at=row["time"],
            )
        except Exception:
            log.exception(
                "twin update failed for device=%s boot=%s seq=%s",
                row["device_id"],
                row["boot_id"],
                row["seq"],
            )
            twin_outcome = {"outcome": "failed"}

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
    return {
        "raw_id": stored["id"],
        "raw_status": status,
        "normalized": outcome,
        "twin": twin_outcome,
    }
