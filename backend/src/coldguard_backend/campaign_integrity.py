"""Evidence-only campaign health and versioned closure; never a validity approval."""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, MetaData, Table, Text, and_, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from coldguard_backend.campaign_store import campaign_plan, get_campaign, verify_membership
from coldguard_backend.dataset_export import run_integrity
from coldguard_backend.experiment_evidence import encode_evidence, run_samples
from coldguard_backend.experiment_store import RunConflict, experiments
from coldguard_backend.normalized_store import classify_replay, map_to_row, telemetry
from coldguard_backend.raw_store import RECEIVED_OBSERVED, RECEIVED_VALID, telemetry_raw
from coldguard_backend.validation import validate_telemetry_payload

run_closures = Table(
    "campaign_run_closures", MetaData(),
    Column("closure_id", Text, primary_key=True),
    Column("campaign_id", Text),
    Column("run_id", Text),
    Column("report", JSONB),
    Column("report_sha256", Text),
    Column("reason", Text),
    Column("recorded_at", DateTime(timezone=True)),
)


def critical_window_report(samples: list[dict], started_at: datetime | None, windows: list[dict]) -> list[dict]:
    reports = []
    for window in windows:
        if started_at is None:
            reports.append({"window_id": window["window_id"], "missing": True, "reason": "run_not_started"})
            continue
        start = started_at + timedelta(seconds=window["start_offset_sec"])
        end = started_at + timedelta(seconds=window["end_offset_sec"])
        acquired = sorted({row["event_time"] for row in samples if row["event_time"] is not None and start <= row["event_time"] <= end})
        boundaries = [start, *acquired, end]
        gaps = [{"start": left, "end": right, "duration_sec": (right - left).total_seconds()}
                for left, right in zip(boundaries, boundaries[1:]) if (right - left).total_seconds() > window["max_gap_sec"]]
        reports.append({"window_id": window["window_id"], "start": start, "end": end,
                        "sample_count": len(acquired), "max_gap_sec": window["max_gap_sec"],
                        "missing": not acquired or bool(gaps), "gaps": gaps,
                        "time_basis": "device_acquisition_unverified", "interpolated_samples": 0})
    return reports


def _raw_evidence(connection: Connection, run: dict) -> list[dict]:
    raw = telemetry_raw.c
    identity_in_run = select(telemetry.c.id).where(
        telemetry.c.device_id == run["device_id"], telemetry.c.run_id == run["run_id"],
        telemetry.c.device_id == raw.device_id, telemetry.c.boot_id == raw.boot_id, telemetry.c.seq == raw.seq,
    ).correlate(telemetry_raw).exists()
    unattributed = and_(raw.run_id.is_(None), raw.topic == f"coldguard/{run['device_id']}/telemetry")
    if run["started_at"] is None:
        unattributed = False
    else:
        unattributed = and_(unattributed, raw.backend_received_at >= run["started_at"])
        if run["ended_at"] is not None:
            unattributed = and_(unattributed, raw.backend_received_at <= run["ended_at"])
    query = select(telemetry_raw).where(or_(raw.run_id == run["run_id"], identity_in_run, unattributed)).order_by(raw.id)
    return [dict(row) for row in connection.execute(query).mappings()]


def assess_run(connection: Connection, campaign: dict, run_id: str) -> dict:
    run = verify_membership(connection, campaign, run_id)
    plan = campaign_plan(campaign, run_id)
    samples = run_samples(connection, run)
    raw = _raw_evidence(connection, run)
    basic = run_integrity(connection, run, samples)
    winners = {(row["boot_id"], row["seq"]): row for row in samples}
    identity_conflicts, wrong_associations, raw_only_valid, errors, schema = [], [], [], [], []
    events, event_ids = Counter(), defaultdict(set)
    for row in raw:
        document = row["raw_json"] if isinstance(row["raw_json"], dict) else {}
        if row["run_id"] not in (None, run_id) or row["device_id"] not in (None, run["device_id"]):
            wrong_associations.append(row["id"])
        if any(key in document and document[key] != run[key] for key in ("pair_id", "controller_id")):
            wrong_associations.append(row["id"])
        if row["ingest_status"] not in {RECEIVED_VALID, RECEIVED_OBSERVED}:
            errors.append(row["id"])
            if row["ingest_status"] == "RECEIVED_INVALID_SCHEMA":
                schema.append(row["id"])
        if row["ingest_status"] == RECEIVED_VALID and row["device_id"] == run["device_id"]:
            winner = winners.get((row["boot_id"], row["seq"]))
            if winner is None:
                raw_only_valid.append(row["id"])
            else:
                validated, _ = validate_telemetry_payload(document)
                if validated is None or classify_replay(
                    {**winner, "time": winner["event_time"]},
                    map_to_row(validated, raw_id=row["id"], received_at=row["backend_received_at"]),
                ) == "conflict":
                    identity_conflicts.append(row["id"])
        if (row["topic"] == f"coldguard/{run['device_id']}/event" and row["device_id"] == run["device_id"]
            and row["run_id"] == run_id and row["ingest_status"] == RECEIVED_OBSERVED
            and type(document.get("schema_version")) is int and document["schema_version"] == 1
            and isinstance(document.get("event_id"), str) and document["event_id"].strip()):
            event_ids[document["event_id"]].add(hashlib.sha256(encode_evidence(document)).hexdigest())
            if isinstance(document.get("event_type"), str):
                events[document["event_type"]] += 1
    critical = critical_window_report(samples, run["started_at"], plan["critical_windows"])
    missing_events = sorted(set(plan["required_events"]) - events.keys())
    event_conflicts = sorted(key for key, variants in event_ids.items() if len(variants) > 1)
    issues = []
    for code, evidence in (
        ("MISSING_SAMPLES", not samples), ("VERSION_MISMATCH", basic["version_mismatches"]),
        ("MIXED_VERSIONS", basic["mixed_version_fields"]), ("WRONG_ASSOCIATION", wrong_associations),
        ("CONFLICTING_IDENTITY", identity_conflicts), ("NORMALIZATION_INCOMPLETE", raw_only_valid),
        ("MESSAGE_ERROR", errors), ("SCHEMA_MISMATCH", schema), ("EVENT_ID_CONFLICT", event_conflicts),
        ("MISSING_REQUIRED_EVENTS", missing_events), ("CLOCKLESS_EVIDENCE", basic["clockless_count"]),
        ("ACQUISITION_OUTSIDE_RUN", basic["event_time_outside_run_unverified"]),
        ("MISSING_CRITICAL_WINDOW", [row["window_id"] for row in critical if row["missing"]]),
    ):
        if evidence:
            issues.append({"code": code, "evidence": evidence})
    if campaign["data_class"] == "SOFTWARE_SIMULATION" and any(row["synthetic"] is not True for row in samples):
        issues.append({"code": "UNLABELED_SIMULATION", "evidence": [row["id"] for row in samples if row["synthetic"] is not True]})
    return {
        "schema_version": 1, "campaign_id": campaign["campaign_id"], "namespace_sha256": campaign["namespace_sha256"],
        "run_id": run_id, "pair_id": run["pair_id"], "controller_id": run["controller_id"], "run_status": run["status"],
        "data_class": campaign["data_class"], "raw_count": len(raw), "normalized_count": len(samples),
        "raw_telemetry_count": sum(row["topic"].endswith("/telemetry") for row in raw),
        "raw_status_counts": dict(Counter(row["ingest_status"] for row in raw)),
        "source_sha256": hashlib.sha256(encode_evidence({"raw": raw, "samples": samples})).hexdigest(),
        "integrity": basic, "event_counts": dict(events), "missing_events": missing_events,
        "critical_windows": critical, "issues": issues,
        "assessment": "ISSUES_REQUIRING_VALIDITY_REVIEW" if issues else "SOFTWARE_INTEGRITY_CLEAR",
        "validity_authority": campaign["namespace"]["validity_rule_reference"],
        "automatic_validity_approval": False, "physical_acceptance": "BLOCKED_EXTERNAL",
    }


def close_run(connection: Connection, campaign_id: str, run_id: str, *, reason: str) -> dict:
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000 or "\x00" in reason:
        raise RunConflict("closure requires an explicit recorded reason")
    connection.execute(select(experiments.c.run_id).where(experiments.c.run_id == run_id).with_for_update())
    campaign = get_campaign(connection, campaign_id)
    report = assess_run(connection, campaign, run_id)
    if report["run_status"] not in {"COMPLETED_RAW", "VALIDITY_REVIEW", "VALID", "INVALID", "ABORTED"}:
        raise RunConflict("run-close requires completed raw evidence or a terminal attempt")
    digest = hashlib.sha256(encode_evidence(report)).hexdigest()
    closure_id = "campaign-close-" + digest
    row = connection.execute(insert(run_closures).values(
        closure_id=closure_id, campaign_id=campaign_id, run_id=run_id,
        report=json.loads(encode_evidence(report)), report_sha256=digest,
        reason=reason, recorded_at=func.clock_timestamp(),
    ).on_conflict_do_nothing(index_elements=["closure_id"]).returning(run_closures)).mappings().one_or_none()
    if row is None:
        row = connection.execute(select(run_closures).where(run_closures.c.closure_id == closure_id)).mappings().one()
    return dict(row)


def campaign_integrity(connection: Connection, campaign_id: str) -> dict:
    campaign = get_campaign(connection, campaign_id)
    assessments = [assess_run(connection, campaign, plan["run"]["run_id"]) for plan in campaign["namespace"]["runs"]]
    missing_closures = []
    for assessment in assessments:
        digest = hashlib.sha256(encode_evidence(assessment)).hexdigest()
        if not connection.scalar(select(run_closures.c.closure_id).where(
            run_closures.c.campaign_id == campaign_id, run_closures.c.run_id == assessment["run_id"],
            run_closures.c.report_sha256 == digest,
        )):
            missing_closures.append(assessment["run_id"])
    return {"campaign_id": campaign_id, "data_class": campaign["data_class"],
            "namespace_sha256": campaign["namespace_sha256"], "run_count": len(assessments), "runs": assessments,
            "missing_current_closures": missing_closures,
            "backup_ready": not missing_closures and all(not row["issues"] for row in assessments),
            "physical_acceptance": "BLOCKED_EXTERNAL"}


def live_integrity(engine: Engine, campaign_id: str, *, now: datetime | None = None, ingestion: dict | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("monitor time must be timezone-aware")
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            connection.scalar(select(1))
            report = campaign_integrity(connection, campaign_id)
            campaign = get_campaign(connection, campaign_id)
            for item in report["runs"]:
                times = item["integrity"]["event_time_range_unverified"]
                latest = times[-1] if times else None
                age = (now - latest).total_seconds() if latest else None
                item.update({"last_sample_age_sec": age if age is not None and age >= 0 else None,
                             "sample_time_in_future": age is not None and age < 0,
                             "sample_stale": age is None or age < 0 or age > campaign["namespace"]["max_sample_age_sec"],
                             "message_errors": item["raw_count"] - sum(item["raw_status_counts"].get(key, 0) for key in (RECEIVED_VALID, RECEIVED_OBSERVED)),
                             "schema_mismatches": item["raw_status_counts"].get("RECEIVED_INVALID_SCHEMA", 0)})
            return {**report, "database_health": "HEALTHY", "observed_at": now, "ingestion": ingestion or {"status": "NOT_OBSERVED"}}
    except SQLAlchemyError:
        return {"campaign_id": campaign_id, "database_health": "UNAVAILABLE", "backup_ready": False,
                "runs": None, "observed_at": now, "ingestion": ingestion or {"status": "NOT_OBSERVED"}}
