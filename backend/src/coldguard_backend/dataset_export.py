"""Repeatable S1 dataset packaging and run integrity checks (C-W09)."""

import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from coldguard_backend.experiment_evidence import encode_evidence, run_samples
from coldguard_backend.experiment_store import get_run, run_history
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.raw_store import RECEIVED_VALID, telemetry_raw

S1_SCENARIOS = frozenset({"S1", "NORMAL_BASELINE", "S1_NORMAL_BASELINE"})
QUALITY_FIELDS = ("thermal_quality", "environment_quality", "electrical_quality", "overall_quality")
VERSION_FIELDS = ("firmware_version", "hardware_config_id", "calibration_id", "schema_version")


def _duplicate_identities(connection: Connection, run: dict) -> list[dict]:
    raw = telemetry_raw.c
    sample = telemetry.c
    count = func.count()
    query = (
        select(raw.boot_id, raw.seq, count.label("raw_deliveries"))
        .join_from(telemetry_raw, telemetry, (
            (raw.device_id == sample.device_id) & (raw.boot_id == sample.boot_id)
            & (raw.seq == sample.seq)
        ))
        .where(
            sample.run_id == run["run_id"], sample.device_id == run["device_id"],
            raw.ingest_status == RECEIVED_VALID,
        )
        .group_by(raw.boot_id, raw.seq)
        .having(count > 1)
        .order_by(raw.boot_id, raw.seq)
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def run_integrity(connection: Connection, run: dict, samples: list[dict]) -> dict:
    by_boot = defaultdict(list)
    event_times = []
    received_times = []
    event_outside = []
    receipt_outside = []
    clockless = 0
    quality = {field: Counter() for field in QUALITY_FIELDS}
    versions = {field: set() for field in VERSION_FIELDS}
    mismatches = []
    start, end = run["started_at"], run["ended_at"]
    for sample in samples:
        by_boot[sample["boot_id"]].append(sample["seq"])
        event, receipt = sample["event_time"], sample["backend_received_at"]
        received_times.append(receipt)
        if event is None:
            clockless += 1
        else:
            event_times.append(event)
            if (start and event < start) or (end and event > end):
                event_outside.append(sample["id"])
        if (start and receipt < start) or (end and receipt > end):
            receipt_outside.append(sample["id"])
        for field in QUALITY_FIELDS:
            quality[field][sample[field] or "MISSING"] += 1
        for field in VERSION_FIELDS:
            value = sample[field]
            versions[field].add(value)
            declared = run["versions"].get(field)
            if declared is not None and value != declared:
                mismatches.append({
                    "telemetry_id": sample["id"], "field": field, "expected": declared, "actual": value,
                })
    gaps = []
    for boot_id, seqs in sorted(by_boot.items()):
        ordered = sorted(seqs)
        for left, right in zip(ordered, ordered[1:]):
            if right > left + 1:
                gaps.append({"boot_id": boot_id, "first_missing": left + 1, "last_missing": right - 1})
    return {
        "sample_count": len(samples),
        "sequence_gaps": gaps,
        "duplicate_identities": _duplicate_identities(connection, run),
        "event_time_range_unverified": [min(event_times), max(event_times)] if event_times else None,
        "receipt_time_range": [min(received_times), max(received_times)] if received_times else None,
        "event_time_outside_run_unverified": event_outside,
        "receipt_time_outside_run": receipt_outside,
        "clockless_count": clockless,
        "quality_counts": quality,
        "version_mismatches": mismatches,
        "mixed_version_fields": [field for field, values in versions.items() if len(values) > 1],
        "missing_version_refs": [field for field in VERSION_FIELDS if run["versions"].get(field) is None],
    }


def build_s1_export(
    connection: Connection, run_ids: list[str], *, created_at: datetime, backend_commit: str,
) -> bytes:
    if not run_ids or len(run_ids) != len(set(run_ids)):
        raise ValueError("provide one or more distinct run IDs")
    if created_at.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    if re.fullmatch(r"[0-9a-f]{40}", backend_commit) is None:
        raise ValueError("backend_commit must be a full Git SHA")
    datasets = []
    synthetic = 0
    for run_id in sorted(run_ids):
        run = get_run(connection, run_id)
        if run["status"] != "VALID" or run["scenario_id"] not in S1_SCENARIOS:
            raise ValueError(f"run {run_id!r} must be a valid S1 baseline")
        samples = run_samples(connection, run)
        if not samples:
            raise ValueError(f"run {run_id!r} has no normalized evidence")
        synthetic += sum(sample["synthetic"] is True for sample in samples)
        datasets.append({
            "run": run,
            "history": run_history(connection, run_id),
            "samples": samples,
            "integrity": run_integrity(connection, run, samples),
        })
    dataset = {"runs": datasets}
    checksum = hashlib.sha256(encode_evidence(dataset)).hexdigest()
    manifest = {
        "schema_version": 1,
        "dataset_id": f"coldguard-s1-{checksum}",
        "run_ids": sorted(run_ids),
        "query_config_version": "s1-v1",
        "created_at": created_at,
        "backend_commit": backend_commit,
        "dataset_sha256": checksum,
        "flagged_synthetic_samples": synthetic,
    }
    return encode_evidence({"manifest": manifest, "dataset": dataset})
