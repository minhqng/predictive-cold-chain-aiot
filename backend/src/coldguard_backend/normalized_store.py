"""Normalized single-branch telemetry storage with DB-arbitrated idempotency (C-W03-03/04).

Doc 02 §14.2 normalized ``telemetry`` concept for **one physical
cooling branch**: event time, (device_id, boot_id, seq) identity,
run/provenance references, T1/T2/T3 + BME context + door, single
cooling-branch electrical observation, applied actuation, per-section
quality + device mode, and receive time — plus ``raw_id`` provenance so
every normalized row traces back to its admitted raw evidence row.

Canonical logical identity is exactly ``(device_id, boot_id, seq)``
(Doc 02 §4.2, §13.3, Doc 05C §4.1/§14):

* enforced by a PostgreSQL ``UNIQUE`` constraint (application
  pre-insert queries alone are not sufficient);
* ``INSERT ... ON CONFLICT DO NOTHING`` makes concurrent delivery of
  the same identity converge to exactly one authoritative row — the
  database arbitrates races, never the application;
* conflict outcomes never parse database human error messages: the
  ``DO NOTHING ... RETURNING`` shape reports insertion vs. conflict
  structurally, and exact-vs-conflicting replays are classified by
  comparing stored column values.

Outcome semantics:

* **new identity** → one normalized sample created;
* **exact replay** (same identity, same semantic fields) → no second
  sample, reported as ``exact_duplicate`` (harmless redelivery);
* **conflicting replay** (same identity, different semantic fields) →
  the authoritative row is never overwritten; the conflicting raw
  evidence is preserved upstream and the outcome is reported as
  ``conflict`` with diagnostics — never a silent ordinary duplicate;
* **incomplete identity** (NULL device/boot/seq) can never enter this
  table: identity columns are ``NOT NULL`` (PostgreSQL treats NULLs as
  distinct, so nullable identity would circumvent uniqueness). Such
  rows remain visible only in ``telemetry_raw``, whose nullable
  columns exist precisely for that evidence role.

Timestamp rule: ``captured_at`` (stored as ``time``) is event time.
Late and out-of-order messages are stored historically. The Twin
projection applies its own freshness rules in the ingestion transaction.

Timescale decision (Doc 02 calls the hypertable a *candidate*): this
slice uses a regular PostgreSQL table with sound indexes. A Timescale
hypertable requires every unique index to contain all partitioning
columns, which would force event time into the canonical
``(device_id, boot_id, seq)`` identity — changing the specified
uniqueness invariant to satisfy a storage optimization. At ~1 Hz from
one device the workload needs correctness, not chunk partitioning; a
hypertable conversion (if ever) belongs to a later slice with its
identity trade-off reviewed explicitly.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    MetaData,
    Table,
    Text,
    Float,
    Integer,
    ForeignKey,
    and_,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from coldguard_backend.contracts import Telemetry

_METADATA = MetaData()

telemetry = Table(
    "telemetry",
    _METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    # Event time (device-captured), not identity. Late messages are
    # stored historically; ordering policy belongs to W04 twin logic.
    Column("time", DateTime(timezone=True)),
    Column("device_id", Text, nullable=False),
    Column("boot_id", Text, nullable=False),
    Column("seq", BigInteger, nullable=False),
    Column("run_id", Text, nullable=True),
    Column("t1_c", Float, nullable=True),
    Column("t2_c", Float, nullable=True),
    Column("t3_c", Float, nullable=True),
    Column("t_air_c", Float, nullable=True),
    Column("rh_pct", Float, nullable=True),
    Column("door_state", Text, nullable=False),
    Column("cooling_voltage_v", Float, nullable=True),
    Column("cooling_current_a", Float, nullable=True),
    Column("cooling_power_w", Float, nullable=True),
    Column("cooling_energy_counter_wh", Float, nullable=True),
    Column("applied_cooling", Text, nullable=False),
    Column("applied_duty", Float, nullable=True),
    Column("thermal_quality", Text, nullable=False),
    Column("environment_quality", Text, nullable=False),
    Column("electrical_quality", Text, nullable=False),
    Column("overall_quality", Text, nullable=False),
    Column("device_mode", Text, nullable=True),
    Column("hardware_config_id", Text, nullable=False),
    Column("firmware_version", Text, nullable=False),
    Column("calibration_id", Text, nullable=True),
    Column("schema_version", Integer, nullable=False),
    Column("backend_received_at", DateTime(timezone=True), nullable=False),
    # Provenance: the admitted raw row this sample was derived from.
    # First writer wins; conflicting replays keep their own raw rows.
    Column("raw_id", BigInteger, ForeignKey("telemetry_raw.id"), nullable=False),
    # First delivery's admission decision. A duplicate cannot upgrade it.
    Column("twin_eligible", Boolean, nullable=False),
    Column("serial_source", JSONB),
)

# Semantic fields compared for exact-vs-conflicting replay. Identity
# columns are equal by construction (same UNIQUE conflict target).
# backend_received_at and raw_id are deliberately excluded: two
# deliveries of the same logical sample arrive at different times with
# different raw rows, and that must still classify as an exact
# duplicate rather than a conflict.
COMPARE_FIELDS = (
    "time",
    "run_id",
    "t1_c",
    "t2_c",
    "t3_c",
    "t_air_c",
    "rh_pct",
    "door_state",
    "cooling_voltage_v",
    "cooling_current_a",
    "cooling_power_w",
    "cooling_energy_counter_wh",
    "applied_cooling",
    "applied_duty",
    "thermal_quality",
    "environment_quality",
    "electrical_quality",
    "overall_quality",
    "device_mode",
    "hardware_config_id",
    "firmware_version",
    "calibration_id",
    "schema_version",
)


def map_to_row(
    validated: Telemetry,
    *,
    raw_id: int,
    received_at: datetime,
) -> dict[str, Any]:
    """Map a strictly validated telemetry snapshot to a storage row.

    Unavailable measurements stay NULL (never zero-filled); nested
    quality semantics map 1:1 onto per-section columns (never
    flattened into a single flag); wire names map onto the canonical
    normalized names (``t1`` → ``t1_c``, ``current_a`` →
    ``cooling_current_a``, …). No legacy dual-branch fields exist.
    """
    row = {
        "time": validated.captured_at,
        "device_id": validated.device_id,
        "boot_id": validated.boot_id,
        "seq": validated.seq,
        "run_id": validated.run_id,
        "t1_c": validated.thermal.t1,
        "t2_c": validated.thermal.t2,
        "t3_c": validated.thermal.t3,
        "t_air_c": validated.environment.t_air,
        "rh_pct": validated.environment.rh,
        "door_state": validated.door.state,
        "cooling_voltage_v": validated.electrical.voltage_v,
        "cooling_current_a": validated.electrical.current_a,
        "cooling_power_w": validated.electrical.power_w,
        "cooling_energy_counter_wh": validated.electrical.energy_wh,
        "applied_cooling": validated.actuation.cooling,
        "applied_duty": validated.actuation.duty,
        "thermal_quality": validated.quality.thermal,
        "environment_quality": validated.quality.environment,
        "electrical_quality": validated.quality.electrical,
        "overall_quality": validated.quality.overall,
        "device_mode": validated.quality.device_mode,
        "hardware_config_id": validated.hardware_config_id,
        "firmware_version": validated.firmware_version,
        "calibration_id": validated.calibration_id,
        "schema_version": validated.schema_version,
        "backend_received_at": received_at,
        "raw_id": raw_id,
    }
    if source := validated.serial_source:
        row["serial_source"] = {
            "schema_version": source.schema_version,
            "clock_quality": source.clock_quality,
            "gateway_received_at": source.gateway_received_at.isoformat(),
            "uptime_ms": validated.uptime_ms,
            "frame_sha256": hashlib.sha256(source.frame.encode("ascii")).hexdigest(),
        }
    return row


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, datetime) and isinstance(right, datetime):
        # Compare by instant, not text: the same event time written with
        # different UTC offsets (e.g. +00:00 vs +02:00) is one logical
        # sample, not a conflict.
        if left.tzinfo is not None and right.tzinfo is not None:
            return left.timestamp() == right.timestamp()
        return left.isoformat() == right.isoformat()
    if isinstance(left, float) and isinstance(right, float):
        # NaN never equals (non-finite values are rejected at validation,
        # so this is defense in depth, not a reachable branch).
        return left == right
    return left == right


def classify_replay(existing: dict[str, Any], incoming: dict[str, Any]) -> str:
    """``exact_duplicate`` when all semantic fields agree, else ``conflict``."""
    for field in COMPARE_FIELDS:
        if not _values_equal(existing.get(field), incoming.get(field)):
            return "conflict"
    # Acquisition time changes on replay. The source observation must agree.
    if (existing.get("serial_source") or {}).get("frame_sha256") != (
        incoming.get("serial_source") or {}
    ).get("frame_sha256"):
        return "conflict"
    return "exact_duplicate"


def insert_normalized(
    engine_or_conn: Engine | Connection,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Insert one normalized sample with DB-arbitrated idempotency.

    Returns ``{"outcome": "inserted"|"exact_duplicate"|"conflict",
    "id": <authoritative row id>}``. ``inserted`` holds the new row id;
    duplicate/conflict outcomes hold the *existing* authoritative row
    id (the winner is never overwritten). With an Engine the attempt
    runs in its own committed transaction; with a Connection it joins
    the caller's transaction.
    """
    statement = (
        pg_insert(telemetry)
        .values(**row)
        .on_conflict_do_nothing(
            index_elements=["device_id", "boot_id", "seq"],
        )
        .returning(telemetry.c.id)
    )
    if isinstance(engine_or_conn, Engine):
        with engine_or_conn.begin() as connection:
            inserted_id = connection.execute(statement).scalar_one_or_none()
            if inserted_id is not None:
                return {"outcome": "inserted", "id": inserted_id}
            existing = connection.execute(
                select(telemetry).where(
                    telemetry.c.device_id == row["device_id"],
                    telemetry.c.boot_id == row["boot_id"],
                    telemetry.c.seq == row["seq"],
                )
            ).mappings().first()
    else:
        inserted_id = engine_or_conn.execute(statement).scalar_one_or_none()
        if inserted_id is not None:
            return {"outcome": "inserted", "id": inserted_id}
        existing = engine_or_conn.execute(
            select(telemetry).where(
                telemetry.c.device_id == row["device_id"],
                telemetry.c.boot_id == row["boot_id"],
                telemetry.c.seq == row["seq"],
            )
        ).mappings().first()
    if existing is None:  # pragma: no cover - defensive; constraint guarantees a row
        raise RuntimeError("ON CONFLICT reported no insert but no conflicting row exists")
    outcome = classify_replay(dict(existing), row)
    return {"outcome": outcome, "id": existing["id"]}


def fetch_by_identity(
    engine_or_conn: Engine | Connection,
    *,
    device_id: str,
    boot_id: str,
    seq: int,
) -> dict[str, Any] | None:
    """Fetch one normalized sample by canonical identity (read helper)."""
    statement = select(telemetry).where(
        telemetry.c.device_id == device_id,
        telemetry.c.boot_id == boot_id,
        telemetry.c.seq == seq,
    )
    if isinstance(engine_or_conn, Engine):
        with engine_or_conn.begin() as connection:
            row = connection.execute(statement).mappings().first()
    else:
        row = engine_or_conn.execute(statement).mappings().first()
    return dict(row) if row is not None else None


def query_telemetry(
    engine_or_conn: Engine | Connection,
    *,
    device_id: str | None = None,
    run_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    clockless_only: bool = False,
    order: Literal["asc", "desc"] = "desc",
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query normalized telemetry with safe filtering, bounded pagination, and stable ordering.

    Supports:
    - device_id filter
    - run_id filter
    - time-range filter (start_time, end_time)
    - clockless filter (clockless_only)
    - stable ordering (by backend_received_at with seq and id tie-breaking)
    """
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if order not in ("asc", "desc"):
        raise ValueError(f"order must be 'asc' or 'desc', got {order!r}")

    clauses = []
    if device_id is not None:
        clauses.append(telemetry.c.device_id == device_id)
    if run_id is not None:
        clauses.append(telemetry.c.run_id == run_id)
    if clockless_only:
        clauses.append(telemetry.c.time.is_(None))
    if start_time is not None:
        effective_time = func.coalesce(telemetry.c.time, telemetry.c.backend_received_at)
        clauses.append(effective_time >= start_time)
    if end_time is not None:
        effective_time = func.coalesce(telemetry.c.time, telemetry.c.backend_received_at)
        clauses.append(effective_time <= end_time)

    statement = select(telemetry)
    if clauses:
        statement = statement.where(and_(*clauses))

    sort_col = telemetry.c.backend_received_at
    if order == "desc":
        statement = statement.order_by(
            sort_col.desc(), telemetry.c.seq.desc(), telemetry.c.id.desc()
        )
    else:
        statement = statement.order_by(
            sort_col.asc(), telemetry.c.seq.asc(), telemetry.c.id.asc()
        )

    statement = statement.limit(limit).offset(offset)

    if isinstance(engine_or_conn, Engine):
        with engine_or_conn.begin() as connection:
            rows = connection.execute(statement).mappings().all()
    else:
        rows = engine_or_conn.execute(statement).mappings().all()

    return [dict(r) for r in rows]


def count_telemetry(
    engine_or_conn: Engine | Connection,
    *,
    device_id: str | None = None,
    run_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    clockless_only: bool = False,
) -> int:
    """Count normalized telemetry matching the specified filters."""
    clauses = []
    if device_id is not None:
        clauses.append(telemetry.c.device_id == device_id)
    if run_id is not None:
        clauses.append(telemetry.c.run_id == run_id)
    if clockless_only:
        clauses.append(telemetry.c.time.is_(None))
    if start_time is not None:
        effective_time = func.coalesce(telemetry.c.time, telemetry.c.backend_received_at)
        clauses.append(effective_time >= start_time)
    if end_time is not None:
        effective_time = func.coalesce(telemetry.c.time, telemetry.c.backend_received_at)
        clauses.append(effective_time <= end_time)

    statement = select(func.count(telemetry.c.id))
    if clauses:
        statement = statement.where(and_(*clauses))

    if isinstance(engine_or_conn, Engine):
        with engine_or_conn.begin() as connection:
            return connection.execute(statement).scalar() or 0
    else:
        return engine_or_conn.execute(statement).scalar() or 0

