"""Database-backed raw/normalized telemetry reconciliation (C-W05-03).

Reconciles raw delivery evidence against authoritative normalized telemetry
from the database, never from transient in-memory counters.

Accounting equation (every raw delivery accounted for exactly once)::

    raw_total == (
        unique_normalized_deliveries
        + exact_duplicates
        + conflicting_duplicates
        + normalization_failures
        + historical_raw_unnormalized      # confirmed pre-normalization
        + historical_unverified            # pre-boundary, unaudited (UNKNOWN)
        + rejected_invalid_schema
        + rejected_malformed_json
        + rejected_topic_mismatch
        + observed_non_telemetry
        + unknown_status_count
    )

Integrity gates (independent of the accounting equation) fail the report when
a normalized "winner" cannot be proven against its raw source:

* winner raw row must exist and be admitted ``RECEIVED_VALID``;
* the exact raw payload must re-validate as canonical telemetry for the
  claimed schema, with topic/device agreement;
* device/boot/seq identity and schema version must agree;
* normalized measurements, quality, actuation, firmware/hardware/calibration
  provenance, run and event-time/serial semantics must equal a fresh mapping
  of the validated raw payload (backend receipt time is never compared as a
  physical measurement).

Historical classification (W05-FIX-02) uses the durable
``reconciliation_boundary`` admission instant plus explicit
``reconciliation_legacy_audit`` verdicts — never numerical row ordering. A
pre-boundary delivery without an audit verdict is ``historical_unverified``
and fails reconciliation rather than fabricating a PASS.

Memory is bounded (W05-FIX-03): counts come from SQL aggregates and row-level
validation runs in keyset batches of ``batch_size``; no full-table load. The
Engine path runs in a single REPEATABLE READ transaction so concurrent inserts
cannot manufacture a discrepancy. A caller-supplied Connection must already be
in a suitable snapshot transaction (the caller owns that transaction).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    Text,
    func,
    select,
    tuple_,
)
from sqlalchemy.engine import Connection, Engine

from coldguard_backend.normalized_store import (
    COMPARE_FIELDS,
    _values_equal,
    classify_replay,
    map_to_row,
    telemetry,
)
from coldguard_backend.raw_store import (
    RECEIVED_INVALID_SCHEMA,
    RECEIVED_MALFORMED_JSON,
    RECEIVED_OBSERVED,
    RECEIVED_VALID,
    REJECTED_TOPIC_MISMATCH,
    telemetry_raw,
)
from coldguard_backend.validation import (
    validate_telemetry_payload,
    validate_topic_identity,
)

DEFAULT_BATCH_SIZE = 500

_METADATA = MetaData()

reconciliation_boundary = Table(
    "reconciliation_boundary",
    _METADATA,
    Column("id", Integer, primary_key=True),
    Column("normalization_active_since", DateTime(timezone=True), nullable=False),
    Column("basis", Text, nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
)

reconciliation_legacy_audit = Table(
    "reconciliation_legacy_audit",
    _METADATA,
    Column("raw_id", BigInteger, primary_key=True),
    Column("verdict", Text, nullable=False),
    Column("basis", Text, nullable=False),
    Column("audited_by", Text, nullable=False),
    Column("audited_at", DateTime(timezone=True), nullable=False),
)

CONFIRMED_HISTORICAL = "CONFIRMED_HISTORICAL"
CONFIRMED_FAILURE = "CONFIRMED_FAILURE"


@dataclass(frozen=True)
class ProvenanceAudit:
    """Audit of message provenance markers across raw evidence."""

    missing_identity_count: int
    topic_mismatch_count: int
    unrecorded_calibration_count: int
    unset_run_count: int
    provenance_mismatch_count: int = 0
    cross_run_collision_count: int = 0


@dataclass(frozen=True)
class WinnerIntegrity:
    """Raw-to-normalized winner content integrity discrepancies (W05-FIX-01)."""

    missing_raw_count: int = 0
    not_admitted_count: int = 0
    invalid_payload_count: int = 0
    topic_mismatch_count: int = 0
    content_mismatch_count: int = 0

    @property
    def total(self) -> int:
        return (
            self.missing_raw_count
            + self.not_admitted_count
            + self.invalid_payload_count
            + self.topic_mismatch_count
            + self.content_mismatch_count
        )


@dataclass(frozen=True)
class ReconciliationReport:
    """Complete, auditable raw/normalized reconciliation report."""

    raw_total: int
    normalized_total: int
    unique_identities: int

    unique_normalized_deliveries: int
    exact_duplicates: int
    conflicting_duplicates: int
    normalization_failures: int
    historical_raw_unnormalized: int
    historical_unverified: int

    rejected_invalid_schema: int
    rejected_malformed_json: int
    rejected_topic_mismatch: int
    observed_non_telemetry: int
    unknown_status_count: int

    provenance: ProvenanceAudit
    winner_integrity: WinnerIntegrity

    accounted_total: int
    discrepancy: int
    is_reconciled: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        status = "PASSED" if self.is_reconciled else "FAILED"
        return (
            f"Reconciliation {status}: raw={self.raw_total}, "
            f"normalized={self.normalized_total}, exact_dup={self.exact_duplicates}, "
            f"conflicts={self.conflicting_duplicates}, "
            f"norm_failures={self.normalization_failures}, "
            f"historical_raw={self.historical_raw_unnormalized}, "
            f"historical_unverified={self.historical_unverified}, "
            f"rejected_schema={self.rejected_invalid_schema}, "
            f"rejected_json={self.rejected_malformed_json}, "
            f"topic_mismatch={self.rejected_topic_mismatch}, "
            f"observed={self.observed_non_telemetry}, "
            f"unknown_status={self.unknown_status_count}, "
            f"prov_mismatch={self.provenance.provenance_mismatch_count}, "
            f"cross_run_collisions={self.provenance.cross_run_collision_count}, "
            f"winner_integrity={self.winner_integrity.total}, "
            f"discrepancy={self.discrepancy}"
        )


def classify_unnormalized_valid(
    received_at: datetime,
    boundary_since: datetime,
    audit_verdict: str | None,
) -> str:
    """Classify a ``RECEIVED_VALID`` raw delivery with no normalized identity.

    Returns ``normalization_failure``, ``historical_confirmed`` or
    ``historical_unverified``. Pure and unit-testable: the decision uses the
    durable admission boundary and an explicit audit verdict, never row order.

    * received at/after the boundary → provable normalization failure;
    * before the boundary with CONFIRMED_HISTORICAL → confirmed historical;
    * before the boundary with CONFIRMED_FAILURE → normalization failure;
    * before the boundary with no verdict → unverified (fail closed).
    """
    if received_at >= boundary_since:
        return "normalization_failure"
    if audit_verdict == CONFIRMED_HISTORICAL:
        return "historical_confirmed"
    if audit_verdict == CONFIRMED_FAILURE:
        return "normalization_failure"
    return "historical_unverified"


def validate_winner(norm: dict[str, Any], raw: dict[str, Any] | None) -> list[str]:
    """Validate a normalized row against its winning raw evidence.

    Returns discrepancy codes (empty == proven). ``raw`` is the joined raw row
    or ``None`` when the referenced raw row is missing. Backend receipt time is
    deliberately not compared as a physical measurement; ``twin_eligible`` is
    not re-derived because the MQTT retained flag is not persisted in raw.
    """
    if raw is None:
        return ["WINNER_MISSING"]
    codes: list[str] = []
    if raw.get("ingest_status") != RECEIVED_VALID:
        codes.append("WINNER_NOT_ADMITTED")

    payload = raw.get("raw_payload")
    try:
        parsed = json.loads(payload) if isinstance(payload, str) else None
    except (ValueError, TypeError):
        parsed = None
    validated, _errors = validate_telemetry_payload(parsed)
    if validated is None:
        codes.append("WINNER_INVALID_PAYLOAD")
        return _dedupe(codes)

    if validate_topic_identity(raw.get("topic", ""), validated):
        codes.append("WINNER_TOPIC_MISMATCH")

    if (
        raw.get("device_id") != norm.get("device_id")
        or raw.get("boot_id") != norm.get("boot_id")
        or raw.get("seq") != norm.get("seq")
        or validated.device_id != norm.get("device_id")
        or validated.boot_id != norm.get("boot_id")
        or validated.seq != norm.get("seq")
    ):
        codes.append("WINNER_IDENTITY_MISMATCH")

    expected = map_to_row(
        validated, raw_id=norm.get("raw_id"), received_at=raw["backend_received_at"]
    )
    for field in COMPARE_FIELDS:
        if not _values_equal(expected.get(field), norm.get(field)):
            codes.append("WINNER_CONTENT_MISMATCH")
            break

    expected_serial = expected.get("serial_source")
    norm_serial = norm.get("serial_source")
    if (expected_serial is None) != (norm_serial is None):
        codes.append("WINNER_CONTENT_MISMATCH")
    elif expected_serial is not None and norm_serial is not None:
        for key in ("schema_version", "clock_quality", "gateway_received_at",
                    "uptime_ms", "frame_sha256"):
            if not _values_equal(expected_serial.get(key), norm_serial.get(key)):
                codes.append("WINNER_CONTENT_MISMATCH")
                break

    if not (
        _values_equal(raw.get("run_id"), norm.get("run_id"))
        and _values_equal(validated.run_id, norm.get("run_id"))
    ):
        codes.append("WINNER_CONTENT_MISMATCH")

    return _dedupe(codes)


def _dedupe(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def reconcile_telemetry(
    engine_or_conn: Engine | Connection,
    *,
    device_id: str | None = None,
    run_id: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> ReconciliationReport:
    """Run memory-bounded, snapshot-consistent reconciliation."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if isinstance(engine_or_conn, Engine):
        with engine_or_conn.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            with connection.begin():
                return _execute_reconciliation(
                    connection,
                    device_id=device_id,
                    run_id=run_id,
                    batch_size=batch_size,
                )
    return _execute_reconciliation(
        engine_or_conn,
        device_id=device_id,
        run_id=run_id,
        batch_size=batch_size,
    )


def _scoped_clauses(table: Table, device_id: str | None, run_id: str | None) -> list:
    clauses = []
    if device_id is not None:
        clauses.append(table.c.device_id == device_id)
    if run_id is not None:
        clauses.append(table.c.run_id == run_id)
    return clauses


def _execute_reconciliation(
    connection: Connection,
    *,
    device_id: str | None,
    run_id: str | None,
    batch_size: int,
) -> ReconciliationReport:
    raw_clauses = _scoped_clauses(telemetry_raw, device_id, run_id)
    norm_clauses = _scoped_clauses(telemetry, device_id, run_id)

    boundary_since = connection.execute(
        select(reconciliation_boundary.c.normalization_active_since).where(
            reconciliation_boundary.c.id == 1
        )
    ).scalar_one_or_none()
    if boundary_since is None:
        raise RuntimeError(
            "reconciliation_boundary is absent; upgrade the database to revision "
            "0007 before reconciling (historical classification requires a durable "
            "admission boundary)"
        )

    raw_total = connection.execute(
        select(func.count()).select_from(telemetry_raw).where(*raw_clauses)
    ).scalar_one()
    normalized_total = connection.execute(
        select(func.count()).select_from(telemetry).where(*norm_clauses)
    ).scalar_one()
    identity_subq = (
        select(telemetry.c.device_id, telemetry.c.boot_id, telemetry.c.seq)
        .where(*norm_clauses)
        .distinct()
        .subquery()
    )
    unique_identities = connection.execute(
        select(func.count()).select_from(identity_subq)
    ).scalar_one()

    winner, identity_mismatch = _validate_winners(connection, norm_clauses, batch_size)
    buckets, prov = _classify_raw_deliveries(
        connection,
        raw_clauses=raw_clauses,
        device_id=device_id,
        batch_size=batch_size,
        boundary_since=boundary_since,
    )

    accounted_total = (
        buckets["unique_normalized"]
        + buckets["exact_duplicates"]
        + buckets["conflicting_duplicates"]
        + buckets["normalization_failures"]
        + buckets["historical_confirmed"]
        + buckets["historical_unverified"]
        + buckets["rejected_invalid_schema"]
        + buckets["rejected_malformed_json"]
        + buckets["rejected_topic_mismatch"]
        + buckets["observed_non_telemetry"]
        + buckets["unknown_status"]
    )
    discrepancy = raw_total - accounted_total
    is_reconciled = (
        discrepancy == 0
        and buckets["unique_normalized"] == normalized_total
        and buckets["normalization_failures"] == 0
        and buckets["historical_unverified"] == 0
        and prov["provenance_mismatch"] == 0
        and identity_mismatch == 0
        and buckets["unknown_status"] == 0
        and winner.total == 0
    )

    provenance = ProvenanceAudit(
        missing_identity_count=prov["missing_identity"],
        topic_mismatch_count=prov["topic_mismatch"],
        unrecorded_calibration_count=prov["unrecorded_calibration"],
        unset_run_count=prov["unset_run"],
        provenance_mismatch_count=prov["provenance_mismatch"] + identity_mismatch,
        cross_run_collision_count=prov["cross_run"],
    )

    return ReconciliationReport(
        raw_total=raw_total,
        normalized_total=normalized_total,
        unique_identities=unique_identities,
        unique_normalized_deliveries=buckets["unique_normalized"],
        exact_duplicates=buckets["exact_duplicates"],
        conflicting_duplicates=buckets["conflicting_duplicates"],
        normalization_failures=buckets["normalization_failures"],
        historical_raw_unnormalized=buckets["historical_confirmed"],
        historical_unverified=buckets["historical_unverified"],
        rejected_invalid_schema=buckets["rejected_invalid_schema"],
        rejected_malformed_json=buckets["rejected_malformed_json"],
        rejected_topic_mismatch=buckets["rejected_topic_mismatch"],
        observed_non_telemetry=buckets["observed_non_telemetry"],
        unknown_status_count=buckets["unknown_status"],
        provenance=provenance,
        winner_integrity=winner,
        accounted_total=accounted_total,
        discrepancy=discrepancy,
        is_reconciled=is_reconciled,
    )


def _validate_winners(
    connection: Connection, norm_clauses: list, batch_size: int
) -> tuple[WinnerIntegrity, int]:
    """Keyset-batched raw-to-normalized winner content validation."""
    missing = not_admitted = invalid_payload = topic_mismatch = content_mismatch = 0
    identity_mismatch = 0
    last_id = 0
    norm_fields = list(telemetry.c.keys())
    while True:
        stmt = (
            select(
                telemetry,
                telemetry_raw.c.id.label("raw_row_id"),
                telemetry_raw.c.raw_payload.label("raw_payload"),
                telemetry_raw.c.ingest_status.label("raw_status"),
                telemetry_raw.c.topic.label("raw_topic"),
                telemetry_raw.c.device_id.label("raw_device_id"),
                telemetry_raw.c.boot_id.label("raw_boot_id"),
                telemetry_raw.c.seq.label("raw_seq"),
                telemetry_raw.c.run_id.label("raw_run_id"),
                telemetry_raw.c.backend_received_at.label("raw_received_at"),
            )
            .select_from(
                telemetry.outerjoin(
                    telemetry_raw, telemetry.c.raw_id == telemetry_raw.c.id
                )
            )
            .where(*norm_clauses, telemetry.c.id > last_id)
            .order_by(telemetry.c.id)
            .limit(batch_size)
        )
        rows = connection.execute(stmt).mappings().all()
        if not rows:
            break
        for r in rows:
            last_id = r["id"]
            norm = {field: r[field] for field in norm_fields}
            if r["raw_row_id"] is None:
                raw = None
            else:
                raw = {
                    "id": r["raw_row_id"],
                    "raw_payload": r["raw_payload"],
                    "ingest_status": r["raw_status"],
                    "topic": r["raw_topic"],
                    "device_id": r["raw_device_id"],
                    "boot_id": r["raw_boot_id"],
                    "seq": r["raw_seq"],
                    "run_id": r["raw_run_id"],
                    "backend_received_at": r["raw_received_at"],
                }
            for code in validate_winner(norm, raw):
                if code == "WINNER_MISSING":
                    missing += 1
                elif code == "WINNER_NOT_ADMITTED":
                    not_admitted += 1
                elif code == "WINNER_INVALID_PAYLOAD":
                    invalid_payload += 1
                elif code == "WINNER_TOPIC_MISMATCH":
                    topic_mismatch += 1
                elif code == "WINNER_IDENTITY_MISMATCH":
                    identity_mismatch += 1
                elif code == "WINNER_CONTENT_MISMATCH":
                    content_mismatch += 1
    return (
        WinnerIntegrity(
            missing_raw_count=missing,
            not_admitted_count=not_admitted,
            invalid_payload_count=invalid_payload,
            topic_mismatch_count=topic_mismatch,
            content_mismatch_count=content_mismatch,
        ),
        identity_mismatch,
    )


def _classify_raw_deliveries(
    connection: Connection,
    *,
    raw_clauses: list,
    device_id: str | None,
    batch_size: int,
    boundary_since: datetime,
) -> tuple[dict[str, int], dict[str, int]]:
    """Keyset-batched classification of every raw delivery (bounded memory)."""
    buckets = {
        "unique_normalized": 0,
        "exact_duplicates": 0,
        "conflicting_duplicates": 0,
        "normalization_failures": 0,
        "historical_confirmed": 0,
        "historical_unverified": 0,
        "rejected_invalid_schema": 0,
        "rejected_malformed_json": 0,
        "rejected_topic_mismatch": 0,
        "observed_non_telemetry": 0,
        "unknown_status": 0,
    }
    prov = {
        "missing_identity": 0,
        "topic_mismatch": 0,
        "unrecorded_calibration": 0,
        "unset_run": 0,
        "provenance_mismatch": 0,
        "cross_run": 0,
    }
    last_id = 0
    while True:
        stmt = (
            select(telemetry_raw)
            .where(*raw_clauses, telemetry_raw.c.id > last_id)
            .order_by(telemetry_raw.c.id)
            .limit(batch_size)
        )
        rows = [dict(r) for r in connection.execute(stmt).mappings().all()]
        if not rows:
            break
        last_id = rows[-1]["id"]
        batch_ids = [r["id"] for r in rows]

        winner_ids = set(
            connection.execute(
                select(telemetry.c.raw_id).where(telemetry.c.raw_id.in_(batch_ids))
            ).scalars().all()
        )

        identities = [
            (r["device_id"], r["boot_id"], r["seq"])
            for r in rows
            if r["ingest_status"] == RECEIVED_VALID
            and r["id"] not in winner_ids
            and r["device_id"] is not None
            and r["boot_id"] is not None
            and r["seq"] is not None
        ]
        global_norm: dict[tuple, dict] = {}
        if identities:
            gclauses = []
            if device_id is not None:
                gclauses.append(telemetry.c.device_id == device_id)
            gstmt = select(telemetry).where(
                *gclauses,
                tuple_(
                    telemetry.c.device_id, telemetry.c.boot_id, telemetry.c.seq
                ).in_(identities),
            )
            for gr in connection.execute(gstmt).mappings().all():
                global_norm[(gr["device_id"], gr["boot_id"], gr["seq"])] = dict(gr)

        audit_verdicts = dict(
            connection.execute(
                select(
                    reconciliation_legacy_audit.c.raw_id,
                    reconciliation_legacy_audit.c.verdict,
                ).where(reconciliation_legacy_audit.c.raw_id.in_(batch_ids))
            ).all()
        )

        for raw in rows:
            status = raw.get("ingest_status")
            if (
                raw.get("device_id") is None
                or raw.get("boot_id") is None
                or raw.get("seq") is None
            ):
                prov["missing_identity"] += 1
            if status == REJECTED_TOPIC_MISMATCH:
                prov["topic_mismatch"] += 1
            if raw.get("run_id") is None:
                prov["unset_run"] += 1
            if _calibration_unrecorded(raw):
                prov["unrecorded_calibration"] += 1

            if status == RECEIVED_INVALID_SCHEMA:
                buckets["rejected_invalid_schema"] += 1
            elif status == RECEIVED_MALFORMED_JSON:
                buckets["rejected_malformed_json"] += 1
            elif status == REJECTED_TOPIC_MISMATCH:
                buckets["rejected_topic_mismatch"] += 1
            elif status == RECEIVED_OBSERVED:
                buckets["observed_non_telemetry"] += 1
            elif status == RECEIVED_VALID:
                _classify_valid_raw(
                    raw,
                    winner_ids=winner_ids,
                    global_norm=global_norm,
                    boundary_since=boundary_since,
                    audit_verdict=audit_verdicts.get(raw["id"]),
                    buckets=buckets,
                    prov=prov,
                )
            else:
                buckets["unknown_status"] += 1
    return buckets, prov


def _calibration_unrecorded(raw: dict[str, Any]) -> bool:
    cal_id = None
    if isinstance(raw.get("raw_json"), dict):
        cal_id = raw["raw_json"].get("calibration_id")
    elif raw.get("raw_payload"):
        try:
            parsed = json.loads(raw["raw_payload"])
            if isinstance(parsed, dict):
                cal_id = parsed.get("calibration_id")
        except (ValueError, TypeError):
            pass
    return cal_id is None or str(cal_id).strip().upper() in ("", "UNRECORDED", "NONE", "NULL")


def _classify_valid_raw(
    raw: dict[str, Any],
    *,
    winner_ids: set,
    global_norm: dict[tuple, dict],
    boundary_since: datetime,
    audit_verdict: str | None,
    buckets: dict[str, int],
    prov: dict[str, int],
) -> None:
    if raw["id"] in winner_ids:
        buckets["unique_normalized"] += 1
        return
    identity = (raw.get("device_id"), raw.get("boot_id"), raw.get("seq"))
    existing = global_norm.get(identity)
    if existing is not None:
        if existing.get("run_id") != raw.get("run_id"):
            prov["cross_run"] += 1
        try:
            payload = raw.get("raw_payload")
            parsed = (
                json.loads(payload)
                if isinstance(payload, str)
                else (raw.get("raw_json") or {})
            )
            validated, _ = validate_telemetry_payload(parsed)
            if validated is not None:
                incoming = map_to_row(
                    validated, raw_id=raw["id"], received_at=raw["backend_received_at"]
                )
                if classify_replay(existing, incoming) == "exact_duplicate":
                    buckets["exact_duplicates"] += 1
                else:
                    buckets["conflicting_duplicates"] += 1
            else:
                buckets["conflicting_duplicates"] += 1
        except Exception:
            buckets["conflicting_duplicates"] += 1
        return
    category = classify_unnormalized_valid(
        raw["backend_received_at"], boundary_since, audit_verdict
    )
    if category == "normalization_failure":
        buckets["normalization_failures"] += 1
    elif category == "historical_confirmed":
        buckets["historical_confirmed"] += 1
    else:
        buckets["historical_unverified"] += 1