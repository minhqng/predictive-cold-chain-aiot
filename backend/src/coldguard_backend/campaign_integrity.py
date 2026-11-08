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
from coldguard_backend.measurement_integrity import measurement_rows
from coldguard_backend.normalized_store import classify_replay, map_to_row, telemetry
from coldguard_backend.raw_store import RECEIVED_OBSERVED, RECEIVED_VALID, classify_raw, telemetry_raw
from coldguard_backend.reconciliation import validate_winner
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
    winner_source = raw.id.in_(select(telemetry.c.raw_id).where(
        telemetry.c.device_id == run["device_id"], telemetry.c.run_id == run["run_id"],
    ))
    unattributed = and_(raw.run_id.is_(None), raw.topic.in_(
        [f"coldguard/{run['device_id']}/{family}" for family in ("telemetry", "event", "state", "health")]
    ))
    if run["started_at"] is None:
        unattributed = False
    else:
        unattributed = and_(unattributed, raw.backend_received_at >= run["started_at"])
        if run["ended_at"] is not None:
            unattributed = and_(unattributed, raw.backend_received_at <= run["ended_at"])
    query = select(telemetry_raw).where(or_(raw.run_id == run["run_id"], identity_in_run, winner_source, unattributed)).order_by(raw.id)
    return [dict(row) for row in connection.execute(query).mappings()]


def _raw_source_errors(source: dict) -> tuple[list[str], dict]:
    """Use authoritative wire text; JSONB and extracted identity are only projections."""
    try:
        expected = classify_raw(source["topic"], source["raw_payload"].encode("utf-8"))
        document = json.loads(source["raw_payload"])
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        document, expected = None, None
    errors = []
    if hashlib.sha256(source["raw_payload"].encode("utf-8")).hexdigest() != source["payload_sha256"]:
        errors.append("RAW_DIGEST_MISMATCH")
    if expected is not None:
        if encode_evidence(expected["raw_json"]) != encode_evidence(source["raw_json"]):
            errors.append("RAW_PROJECTION_MISMATCH")
        if any(expected[key] != source[key] for key in ("device_id", "boot_id", "seq", "run_id", "schema_version", "captured_at", "ingest_status")):
            errors.append("RAW_METADATA_MISMATCH")
    elif source["raw_json"] is not None or source["ingest_status"] in {RECEIVED_VALID, RECEIVED_OBSERVED}:
        errors.append("RAW_PROJECTION_MISMATCH")
    return errors, document if isinstance(document, dict) else {}


def _observed_schema_errors(document: dict, *, event: bool) -> tuple[list[str], bool]:
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        return ["UNSUPPORTED_OBSERVED_SCHEMA"], True
    if not event:
        return [], False
    if any(not isinstance(document.get(key), str) or not document[key].strip() for key in ("event_id", "event_type", "device_id", "boot_id", "run_id")):
        return ["EVENT_IDENTITY_MISSING"], False
    try:
        if datetime.fromisoformat(document["event_time"].replace("Z", "+00:00")).utcoffset() is None:
            raise ValueError("unverified event time")
    except (KeyError, TypeError, ValueError):
        return ["EVENT_TIME_UNAVAILABLE"], False
    return [], False


def _global_event_conflicts(connection: Connection, event_ids: set[str]) -> list[dict]:
    if not event_ids:
        return []
    variants, identities = defaultdict(set), defaultdict(list)
    # A JSONB index cannot establish identity when its projection is corrupted.
    query = select(telemetry_raw).where(telemetry_raw.c.topic.endswith("/event")).order_by(telemetry_raw.c.id)
    for row in connection.execute(query).mappings():
        source = dict(row)
        errors, document = _raw_source_errors(source)
        event_id = document.get("event_id")
        if not isinstance(event_id, str) or event_id not in event_ids:
            continue
        variants[event_id].add(hashlib.sha256(encode_evidence(document)).hexdigest())
        identities[event_id].append({"raw_id": source["id"], "run_id": document.get("run_id"),
                                     "device_id": document.get("device_id"), "provenance_errors": errors})
    return [{"event_id": event_id, "variant_count": len(variants[event_id]), "receipts": identities[event_id]}
            for event_id in sorted(variants) if len(variants[event_id]) > 1]


def assess_run(connection: Connection, campaign: dict, run_id: str) -> dict:
    run = verify_membership(connection, campaign, run_id)
    plan = campaign_plan(campaign, run_id)
    samples = run_samples(connection, run)
    raw = _raw_evidence(connection, run)
    basic = run_integrity(connection, run, samples)
    winners = {(row["boot_id"], row["seq"]): row for row in samples}
    identity_conflicts, wrong_associations, raw_only_valid, errors, schema = [], [], [], [], []
    events, event_ids = Counter(), set()
    provenance_errors, generated_raw_ids, replay_raw_ids = [], [], []
    for sample, source in measurement_rows(connection, [row["id"] for row in samples]):
        codes = validate_winner(sample, source)
        if source["backend_received_at"] != sample["backend_received_at"]:
            codes.append("WINNER_RECEIPT_MISMATCH")
        if codes:
            provenance_errors.append({"raw_id": source["id"], "telemetry_id": sample["id"], "codes": codes})
    for row in raw:
        source_errors, document = _raw_source_errors(row)
        if source_errors:
            provenance_errors.append({"raw_id": row["id"], "codes": source_errors})
            errors.append(row["id"])
        if document.get("synthetic") is True:
            generated_raw_ids.append(row["id"])
        if document.get("replay") is True or document.get("is_replay") is True:
            replay_raw_ids.append(row["id"])
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
        event_receipt = row["topic"] == f"coldguard/{run['device_id']}/event"
        observed_errors = []
        if row["ingest_status"] == RECEIVED_OBSERVED:
            observed_errors, schema_mismatch = _observed_schema_errors(document, event=event_receipt)
            if observed_errors:
                errors.append(row["id"])
            if schema_mismatch:
                schema.append(row["id"])
        if event_receipt and isinstance(document.get("event_id"), str) and document["event_id"].strip():
            event_ids.add(document["event_id"])
        if (event_receipt and not source_errors and not observed_errors and row["device_id"] == run["device_id"]
            and row["run_id"] == run_id and row["ingest_status"] == RECEIVED_OBSERVED
            and type(document.get("schema_version")) is int and document["schema_version"] == 1
            and isinstance(document.get("event_id"), str) and document["event_id"].strip()):
            if isinstance(document.get("event_type"), str):
                events[document["event_type"]] += 1
    critical = critical_window_report(samples, run["started_at"], plan["critical_windows"])
    missing_events = sorted(set(plan["required_events"]) - events.keys())
    global_conflicts = _global_event_conflicts(connection, event_ids)
    event_conflicts = [row["event_id"] for row in global_conflicts]
    errors, schema = sorted(set(errors)), sorted(set(schema))
    issues = []
    for code, evidence in (
        ("MISSING_SAMPLES", not samples), ("VERSION_MISMATCH", basic["version_mismatches"]),
        ("MIXED_VERSIONS", basic["mixed_version_fields"]), ("WRONG_ASSOCIATION", wrong_associations),
        ("CONFLICTING_IDENTITY", identity_conflicts), ("NORMALIZATION_INCOMPLETE", raw_only_valid),
        ("MESSAGE_ERROR", errors), ("SCHEMA_MISMATCH", schema), ("EVENT_ID_CONFLICT", event_conflicts),
        ("MISSING_REQUIRED_EVENTS", missing_events), ("CLOCKLESS_EVIDENCE", basic["clockless_count"]),
        ("ACQUISITION_OUTSIDE_RUN", basic["event_time_outside_run_unverified"]),
        ("MISSING_CRITICAL_WINDOW", [row["window_id"] for row in critical if row["missing"]]),
        ("RAW_PROVENANCE_INCONSISTENT", provenance_errors),
    ):
        if evidence:
            issues.append({"code": code, "evidence": evidence})
    if campaign["data_class"] == "SOFTWARE_SIMULATION" and any(row["synthetic"] is not True for row in samples):
        issues.append({"code": "UNLABELED_SIMULATION", "evidence": [row["id"] for row in samples if row["synthetic"] is not True]})
    if campaign["data_class"] == "PHYSICAL" and generated_raw_ids:
        issues.append({"code": "SYNTHETIC_IN_PHYSICAL_CAMPAIGN", "evidence": generated_raw_ids})
    if campaign["data_class"] == "PHYSICAL" and replay_raw_ids:
        issues.append({"code": "REPLAY_REQUIRES_PHYSICAL_VALIDITY_REVIEW", "evidence": replay_raw_ids})
    return {
        "schema_version": 1, "assessment_recipe": "campaign-integrity-v2", "campaign_id": campaign["campaign_id"], "namespace_sha256": campaign["namespace_sha256"],
        "run_id": run_id, "pair_id": run["pair_id"], "controller_id": run["controller_id"], "run_status": run["status"],
        "data_class": campaign["data_class"], "raw_count": len(raw), "normalized_count": len(samples),
        "raw_telemetry_count": sum(row["topic"].endswith("/telemetry") for row in raw),
        "raw_status_counts": dict(Counter(row["ingest_status"] for row in raw)),
        "source_sha256": hashlib.sha256(encode_evidence({"raw": raw, "samples": samples})).hexdigest(),
        "integrity": basic, "event_counts": dict(events), "missing_events": missing_events,
        "global_event_conflicts": global_conflicts, "message_error_raw_ids": errors, "schema_mismatch_raw_ids": schema,
        "known_generated_input": bool(generated_raw_ids), "synthetic_raw_count": len(generated_raw_ids), "replay_raw_count": len(replay_raw_ids),
        "observed_origin": "KNOWN_SOFTWARE_SIMULATION" if generated_raw_ids else "PHYSICAL_ORIGIN_UNPROVEN",
        "critical_windows": critical, "issues": issues,
        "assessment": "ISSUES_REQUIRING_VALIDITY_REVIEW" if issues else "SOFTWARE_INTEGRITY_CLEAR",
        "validity_authority": campaign["namespace"]["validity_rule_reference"],
        "automatic_validity_approval": False, "physical_acceptance": "BLOCKED_EXTERNAL",
    }


def close_run(connection: Connection, campaign_id: str, run_id: str, *, reason: str) -> dict:
    if connection.get_isolation_level() not in {"REPEATABLE READ", "SERIALIZABLE"}:
        raise ValueError("close_run requires a REPEATABLE READ or SERIALIZABLE write transaction before its first read")
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
    archiveable = not missing_closures and all(row["run_status"] in {"COMPLETED_RAW", "VALIDITY_REVIEW", "VALID", "INVALID", "ABORTED"} for row in assessments)
    clear = all(not row["issues"] for row in assessments)
    return {"campaign_id": campaign_id, "data_class": campaign["data_class"],
            "namespace_sha256": campaign["namespace_sha256"], "run_count": len(assessments), "runs": assessments,
            "missing_current_closures": missing_closures,
            "backup_ready": archiveable, "integrity_clear": clear,
            "freeze_ready": archiveable and clear and all(row["run_status"] == "VALID" for row in assessments),
            "known_generated_input": any(row["known_generated_input"] for row in assessments),
            "run_status_counts": dict(Counter(row["run_status"] for row in assessments)),
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
                             "message_errors": len(item["message_error_raw_ids"]),
                             "schema_mismatches": len(item["schema_mismatch_raw_ids"])})
            return {**report, "database_health": "HEALTHY", "observed_at": now, "ingestion": ingestion or {"status": "NOT_OBSERVED"}}
    except SQLAlchemyError:
        return {"campaign_id": campaign_id, "database_health": "UNAVAILABLE", "backup_ready": False,
                "runs": None, "observed_at": now, "ingestion": ingestion or {"status": "NOT_OBSERVED"}}
