"""Durable raw MQTT ingestion evidence (C-W02-04).

Every MQTT message the backend consumer receives is persisted to
``telemetry_raw`` before any downstream interpretation, so a later
parser/feature bug cannot destroy the original evidence (Doc 02,
raw-before-derived principle).

Design notes, all load-bearing:

* Exact bytes win. ``raw_payload`` (TEXT) holds the exact UTF-8 wire
  text; ``payload_sha256`` fingerprints the exact received bytes so a
  stored row can be checked against publisher-side records. ``raw_json``
  (JSONB) is a *convenience projection* for queries, never the
  authority: JSONB does not preserve original formatting, and malformed
  input cannot be represented as JSONB at all (hence nullable).
* Malformed input is evidence, not garbage. A payload that is not
  UTF-8/JSON, or that fails the W01 wire contracts, is still stored
  with a truthful status and diagnostics. Nullable identity columns
  exist precisely so such rows survive.
* Statuses are preliminary (W02), not verdicts. ``RECEIVED_VALID`` means
  "wire-shape valid per the W01 contracts"; full semantic validation
  (topic/device agreement, schema policy) and normalized authority
  belong to W03. Non-telemetry device-data families are stored as
  ``RECEIVED_OBSERVED``: received and retained, family validation
  deferred to the owning slice. Nothing here is a validated physical
  sample and nothing here updates a twin (W04).
* No uniqueness yet. Duplicate QoS 1 deliveries land as separate rows
  so retransmission is *observable*. The canonical
  ``UNIQUE(device_id, boot_id, seq)`` enforcement with ``ON CONFLICT``
  handling is owned by C-W03-04; adding it here would silently discard
  the duplicate evidence W03 must reason about.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from coldguard_backend.contracts import Telemetry

RECEIVED_VALID = "RECEIVED_VALID"
RECEIVED_INVALID_SCHEMA = "RECEIVED_INVALID_SCHEMA"
RECEIVED_MALFORMED_JSON = "RECEIVED_MALFORMED_JSON"
RECEIVED_OBSERVED = "RECEIVED_OBSERVED"

INGEST_STATUSES = frozenset(
    {
        RECEIVED_VALID,
        RECEIVED_INVALID_SCHEMA,
        RECEIVED_MALFORMED_JSON,
        RECEIVED_OBSERVED,
    }
)

_METADATA = MetaData()

telemetry_raw = Table(
    "telemetry_raw",
    _METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("device_id", Text, nullable=True),
    Column("boot_id", Text, nullable=True),
    Column("seq", BigInteger, nullable=True),
    Column("topic", Text, nullable=False),
    Column("schema_version", Integer, nullable=True),
    Column("captured_at", DateTime(timezone=True), nullable=True),
    Column(
        "backend_received_at",
        DateTime(timezone=True),
        nullable=False,
    ),
    Column("raw_payload", Text, nullable=False),
    Column("raw_json", JSON().with_variant(JSONB, "postgresql"), nullable=True),
    Column("payload_sha256", String(64), nullable=False),
    Column("ingest_status", Text, nullable=False),
    Column("validation_errors", JSON().with_variant(JSONB, "postgresql"), nullable=True),
    Column("run_id", Text, nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
    ),
)

_TELEMETRY_SUFFIX = "/telemetry"
_MAX_ERRORS = 20


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _best_effort_identity(parsed: Any) -> dict[str, Any]:
    """Extract diagnostic identity from a parsed JSON document, if shaped so."""
    identity: dict[str, Any] = {
        "device_id": None,
        "boot_id": None,
        "seq": None,
        "schema_version": None,
        "captured_at": None,
        "run_id": None,
    }
    if not isinstance(parsed, dict):
        return identity
    device_id = parsed.get("device_id")
    boot_id = parsed.get("boot_id")
    seq = parsed.get("seq")
    schema_version = parsed.get("schema_version")
    run_id = parsed.get("run_id")
    if isinstance(device_id, str) and device_id.strip():
        identity["device_id"] = device_id
    if isinstance(boot_id, str) and boot_id.strip():
        identity["boot_id"] = boot_id
    if isinstance(seq, int) and not isinstance(seq, bool):
        identity["seq"] = seq
    if isinstance(schema_version, int) and not isinstance(schema_version, bool):
        identity["schema_version"] = schema_version
    if isinstance(run_id, str) and run_id.strip():
        identity["run_id"] = run_id
    captured = parsed.get("captured_at")
    if isinstance(captured, str):
        try:
            identity["captured_at"] = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except ValueError:
            identity["captured_at"] = None
    return identity


def classify_raw(topic: str, payload: bytes) -> dict[str, Any]:
    """Classify one received MQTT payload without touching the database.

    Returns the row fields (minus id/created_at/backend_received_at).
    Pure function: the unit-testable home of the W02/W03 validation
    boundary decision.
    """
    sha256 = hashlib.sha256(payload).hexdigest()
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {
            "device_id": None,
            "boot_id": None,
            "seq": None,
            "topic": topic,
            "schema_version": None,
            "captured_at": None,
            "raw_payload": payload.decode("utf-8", errors="replace"),
            "raw_json": None,
            "payload_sha256": sha256,
            "ingest_status": RECEIVED_MALFORMED_JSON,
            "validation_errors": [{"code": "NOT_UTF8", "message": str(exc)[:500]}],
            "run_id": None,
        }
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return {
            "device_id": None,
            "boot_id": None,
            "seq": None,
            "topic": topic,
            "schema_version": None,
            "captured_at": None,
            "raw_payload": text,
            "raw_json": None,
            "payload_sha256": sha256,
            "ingest_status": RECEIVED_MALFORMED_JSON,
            "validation_errors": [
                {"code": "JSON_DECODE_ERROR", "message": str(exc)[:500]}
            ],
            "run_id": None,
        }
    if not topic.endswith(_TELEMETRY_SUFFIX):
        # Non-telemetry device-data family (event/state/health): retained
        # as receipt evidence; family-specific validation belongs to the
        # owning slice, so no VALID claim is made here.
        identity = _best_effort_identity(parsed)
        return {
            **identity,
            "topic": topic,
            "raw_payload": text,
            "raw_json": parsed if isinstance(parsed, (dict, list)) else None,
            "payload_sha256": sha256,
            "ingest_status": RECEIVED_OBSERVED,
            "validation_errors": None,
        }
    try:
        telemetry = Telemetry.model_validate(parsed)
    except ValidationError as exc:
        identity = _best_effort_identity(parsed)
        errors = [
            {
                "code": "SCHEMA_VIOLATION",
                "loc": ".".join(str(part) for part in err.get("loc", ())),
                "message": str(err.get("msg", ""))[:500],
            }
            for err in exc.errors()[:_MAX_ERRORS]
        ]
        return {
            **identity,
            "topic": topic,
            "raw_payload": text,
            "raw_json": parsed if isinstance(parsed, (dict, list)) else None,
            "payload_sha256": sha256,
            "ingest_status": RECEIVED_INVALID_SCHEMA,
            "validation_errors": errors,
            "run_id": identity["run_id"],
        }
    return {
        "device_id": telemetry.device_id,
        "boot_id": telemetry.boot_id,
        "seq": telemetry.seq,
        "topic": topic,
        "schema_version": telemetry.schema_version,
        "captured_at": telemetry.captured_at,
        "raw_payload": text,
        "raw_json": parsed,
        "payload_sha256": sha256,
        # Preliminary: wire-shape valid per W01 contracts. Full semantic
        # validation (topic/device agreement, schema policy) is W03.
        "ingest_status": RECEIVED_VALID,
        "validation_errors": None,
        "run_id": telemetry.run_id,
    }


def store_raw(
    engine_or_conn: Engine | Connection,
    *,
    topic: str,
    payload: bytes,
    received_at: datetime | None = None,
) -> dict[str, Any]:
    """Persist one received MQTT message and return its stored identity.

    Insert failures (DB down, commit failure) propagate to the caller;
    this function never swallows persistence errors into a fake success.
    With an Engine the insert runs in its own committed transaction;
    with a Connection it joins the caller's transaction.
    """
    row = classify_raw(topic, payload)
    row["backend_received_at"] = received_at or _utcnow()
    row["created_at"] = _utcnow()
    statement = insert(telemetry_raw).values(**row).returning(telemetry_raw.c.id)
    if isinstance(engine_or_conn, Engine):
        with engine_or_conn.begin() as connection:
            stored_id = connection.execute(statement).scalar_one()
    else:
        stored_id = engine_or_conn.execute(statement).scalar_one()
    return {
        "id": stored_id,
        "ingest_status": row["ingest_status"],
        "device_id": row["device_id"],
        "boot_id": row["boot_id"],
        "seq": row["seq"],
        "run_id": row["run_id"],
        "payload_sha256": row["payload_sha256"],
    }
