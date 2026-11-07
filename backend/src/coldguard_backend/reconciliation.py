"""Database-backed raw and normalized telemetry reconciliation (C-W05-03).

Reconciles raw delivery evidence against authoritative normalized telemetry
without relying solely on transient in-memory process counters.

Accounting equation:
    raw_total == (
        unique_normalized
        + exact_duplicates
        + conflicting_duplicates
        + normalization_failures
        + rejected_invalid_schema
        + rejected_malformed_json
        + rejected_topic_mismatch
        + observed_non_telemetry
    )

Invariants:
- Authoritative truth is derived from the database, never solely from in-memory counters.
- Raw evidence is immutable; reconciliation never silently deletes or repairs evidence.
- Every delivery is accounted for without double-counting.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.engine import Connection, Engine

from coldguard_backend.normalized_store import (
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
from coldguard_backend.validation import validate_telemetry_payload


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
class ReconciliationReport:
    """Complete, auditable raw/normalized reconciliation report."""

    raw_total: int
    normalized_total: int
    unique_identities: int

    # Breakdown of raw deliveries
    unique_normalized_deliveries: int
    exact_duplicates: int
    conflicting_duplicates: int
    normalization_failures: int
    historical_raw_unnormalized: int

    # Rejection and observation breakdown
    rejected_invalid_schema: int
    rejected_malformed_json: int
    rejected_topic_mismatch: int
    observed_non_telemetry: int
    unknown_status_count: int

    # Provenance audit
    provenance: ProvenanceAudit

    # Validation
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
            f"rejected_schema={self.rejected_invalid_schema}, "
            f"rejected_json={self.rejected_malformed_json}, "
            f"topic_mismatch={self.rejected_topic_mismatch}, "
            f"observed={self.observed_non_telemetry}, "
            f"unknown_status={self.unknown_status_count}, "
            f"prov_mismatch={self.provenance.provenance_mismatch_count}, "
            f"cross_run_collisions={self.provenance.cross_run_collision_count}, "
            f"discrepancy={self.discrepancy}"
        )


def reconcile_telemetry(
    engine_or_conn: Engine | Connection,
    *,
    device_id: str | None = None,
    run_id: str | None = None,
) -> ReconciliationReport:
    """Run database-backed reconciliation over raw and normalized tables."""
    raw_stmt = select(telemetry_raw)
    norm_stmt = select(telemetry)

    raw_clauses = []
    norm_clauses = []
    if device_id is not None:
        raw_clauses.append(telemetry_raw.c.device_id == device_id)
        norm_clauses.append(telemetry.c.device_id == device_id)
    if run_id is not None:
        raw_clauses.append(telemetry_raw.c.run_id == run_id)
        norm_clauses.append(telemetry.c.run_id == run_id)

    if raw_clauses:
        raw_stmt = raw_stmt.where(and_(*raw_clauses))
    if norm_clauses:
        norm_stmt = norm_stmt.where(and_(*norm_clauses))

    if isinstance(engine_or_conn, Engine):
        with engine_or_conn.begin() as connection:
            return _execute_reconciliation(
                connection,
                raw_stmt=raw_stmt,
                norm_stmt=norm_stmt,
                device_id=device_id,
                run_id=run_id,
            )
    else:
        return _execute_reconciliation(
            engine_or_conn,
            raw_stmt=raw_stmt,
            norm_stmt=norm_stmt,
            device_id=device_id,
            run_id=run_id,
        )


def _execute_reconciliation(
    connection: Connection,
    *,
    raw_stmt: Any,
    norm_stmt: Any,
    device_id: str | None,
    run_id: str | None,
) -> ReconciliationReport:
    raw_rows = [dict(r) for r in connection.execute(raw_stmt).mappings().all()]
    norm_rows = [dict(r) for r in connection.execute(norm_stmt).mappings().all()]

    raw_total = len(raw_rows)
    normalized_total = len(norm_rows)

    # When run_id is specified, fetch global normalized rows to detect cross-run collisions
    if run_id is not None:
        global_norm_stmt = select(telemetry)
        if device_id is not None:
            global_norm_stmt = global_norm_stmt.where(telemetry.c.device_id == device_id)
        global_norm_rows = [
            dict(r) for r in connection.execute(global_norm_stmt).mappings().all()
        ]
    else:
        global_norm_rows = norm_rows

    # Unique identities in normalized storage
    unique_identities = len(
        {(r["device_id"], r["boot_id"], r["seq"]) for r in norm_rows}
    )

    # Winning raw IDs in normalized storage
    winning_raw_ids = {r["raw_id"] for r in norm_rows}
    global_norm_by_identity = {
        (r["device_id"], r["boot_id"], r["seq"]): r for r in global_norm_rows
    }

    # Minimum normalized raw ID (used to distinguish historical pre-normalization raw rows)
    all_norm_raw_ids = [r["raw_id"] for r in global_norm_rows if r.get("raw_id") is not None]
    min_norm_raw_id = min(all_norm_raw_ids) if all_norm_raw_ids else None

    # Check raw_id provenance mismatch
    provenance_mismatch_count = 0
    raw_by_id = {r["id"]: r for r in raw_rows if "id" in r}
    missing_winning_raw_ids = [
        r["raw_id"] for r in norm_rows if r.get("raw_id") not in raw_by_id
    ]
    if missing_winning_raw_ids:
        missing_stmt = select(telemetry_raw).where(
            telemetry_raw.c.id.in_(missing_winning_raw_ids)
        )
        for r in connection.execute(missing_stmt).mappings().all():
            raw_by_id[r["id"]] = dict(r)

    for norm in norm_rows:
        raw_winner = raw_by_id.get(norm.get("raw_id"))
        if raw_winner is not None:
            if (
                raw_winner.get("device_id") != norm.get("device_id")
                or raw_winner.get("boot_id") != norm.get("boot_id")
                or raw_winner.get("seq") != norm.get("seq")
            ):
                provenance_mismatch_count += 1

    unique_normalized_deliveries = 0
    exact_duplicates = 0
    conflicting_duplicates = 0
    normalization_failures = 0
    historical_raw_unnormalized = 0

    rejected_invalid_schema = 0
    rejected_malformed_json = 0
    rejected_topic_mismatch = 0
    observed_non_telemetry = 0
    unknown_status_count = 0

    missing_identity_count = 0
    topic_mismatch_count = 0
    unrecorded_calibration_count = 0
    unset_run_count = 0
    cross_run_collision_count = 0

    for raw in raw_rows:
        status = raw.get("ingest_status")

        # Track provenance markers
        if raw.get("device_id") is None or raw.get("boot_id") is None or raw.get("seq") is None:
            missing_identity_count += 1
        if status == REJECTED_TOPIC_MISMATCH:
            topic_mismatch_count += 1
        if raw.get("run_id") is None:
            unset_run_count += 1

        # Check calibration provenance across raw telemetry evidence
        cal_id = None
        if isinstance(raw.get("raw_json"), dict):
            cal_id = raw["raw_json"].get("calibration_id")
        elif raw.get("raw_payload"):
            try:
                parsed = json.loads(raw["raw_payload"])
                if isinstance(parsed, dict):
                    cal_id = parsed.get("calibration_id")
            except Exception:
                pass
        if cal_id is None or str(cal_id).strip().upper() in ("", "UNRECORDED", "NONE", "NULL"):
            unrecorded_calibration_count += 1

        if status == RECEIVED_INVALID_SCHEMA:
            rejected_invalid_schema += 1
        elif status == RECEIVED_MALFORMED_JSON:
            rejected_malformed_json += 1
        elif status == REJECTED_TOPIC_MISMATCH:
            rejected_topic_mismatch += 1
        elif status == RECEIVED_OBSERVED:
            observed_non_telemetry += 1
        elif status == RECEIVED_VALID:
            # Check if this raw row was the winning row for a normalized sample in this scope
            if raw.get("id") in winning_raw_ids:
                unique_normalized_deliveries += 1
            else:
                identity = (raw.get("device_id"), raw.get("boot_id"), raw.get("seq"))
                existing = global_norm_by_identity.get(identity)
                if existing is not None:
                    # Detected existing identity. Check if it belonged to another run.
                    if existing.get("run_id") != raw.get("run_id"):
                        cross_run_collision_count += 1

                    # Re-classify against stored normalized row
                    try:
                        raw_payload = raw.get("raw_payload")
                        parsed = (
                            json.loads(raw_payload)
                            if isinstance(raw_payload, str)
                            else (raw.get("raw_json") or {})
                        )
                        validated, _ = validate_telemetry_payload(parsed)
                        if validated is not None:
                            incoming_row = map_to_row(
                                validated,
                                raw_id=raw["id"],
                                received_at=raw["backend_received_at"],
                            )
                            replay_kind = classify_replay(existing, incoming_row)
                            if replay_kind == "exact_duplicate":
                                exact_duplicates += 1
                            else:
                                conflicting_duplicates += 1
                        else:
                            conflicting_duplicates += 1
                    except Exception:
                        conflicting_duplicates += 1
                else:
                    # Identity not found in normalized table
                    if min_norm_raw_id is not None and raw["id"] < min_norm_raw_id:
                        # Raw row predates normalization activation (historical unnormalized)
                        historical_raw_unnormalized += 1
                    else:
                        # Marked RECEIVED_VALID after normalization activation but dropped
                        normalization_failures += 1
        else:
            # Unanticipated or invalid ingest_status is guarded and tracked explicitly
            unknown_status_count += 1

    accounted_total = (
        unique_normalized_deliveries
        + exact_duplicates
        + conflicting_duplicates
        + normalization_failures
        + historical_raw_unnormalized
        + rejected_invalid_schema
        + rejected_malformed_json
        + rejected_topic_mismatch
        + observed_non_telemetry
        + unknown_status_count
    )

    discrepancy = raw_total - accounted_total
    is_reconciled = (
        (discrepancy == 0)
        and (unique_normalized_deliveries == normalized_total)
        and (normalization_failures == 0)
        and (provenance_mismatch_count == 0)
        and (unknown_status_count == 0)
    )

    provenance = ProvenanceAudit(
        missing_identity_count=missing_identity_count,
        topic_mismatch_count=topic_mismatch_count,
        unrecorded_calibration_count=unrecorded_calibration_count,
        unset_run_count=unset_run_count,
        provenance_mismatch_count=provenance_mismatch_count,
        cross_run_collision_count=cross_run_collision_count,
    )

    return ReconciliationReport(
        raw_total=raw_total,
        normalized_total=normalized_total,
        unique_identities=unique_identities,
        unique_normalized_deliveries=unique_normalized_deliveries,
        exact_duplicates=exact_duplicates,
        conflicting_duplicates=conflicting_duplicates,
        normalization_failures=normalization_failures,
        historical_raw_unnormalized=historical_raw_unnormalized,
        rejected_invalid_schema=rejected_invalid_schema,
        rejected_malformed_json=rejected_malformed_json,
        rejected_topic_mismatch=rejected_topic_mismatch,
        observed_non_telemetry=observed_non_telemetry,
        unknown_status_count=unknown_status_count,
        provenance=provenance,
        accounted_total=accounted_total,
        discrepancy=discrepancy,
        is_reconciled=is_reconciled,
    )
