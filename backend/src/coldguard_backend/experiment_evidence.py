"""Read run evidence by explicit run and device identity (C-W07-03/04/05)."""

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.engine import Connection

from coldguard_backend.command_store import command_acks, command_transitions, commands
from coldguard_backend.experiment_store import run_history
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.raw_store import RECEIVED_OBSERVED, telemetry_raw
from coldguard_backend.timing import compute_timing_metrics


def _belongs_to_run(table, run: dict):
    return (table.c.run_id == run["run_id"]) & (table.c.device_id == run["device_id"])


def run_samples(connection: Connection, run: dict) -> list[dict]:
    """Use the unique normalized winner and its raw provenance, never overlap."""
    rows = connection.execute(
        select(
            telemetry, telemetry_raw.c.payload_sha256.label("raw_sha256"),
            telemetry_raw.c.ingest_status.label("raw_status"), telemetry_raw.c.raw_json,
        )
        .join(telemetry_raw, telemetry_raw.c.id == telemetry.c.raw_id)
        .where(_belongs_to_run(telemetry, run))
        .order_by(telemetry.c.backend_received_at, telemetry.c.id)
    ).mappings()
    samples = []
    for row in rows:
        sample = dict(row)
        raw = sample.pop("raw_json")
        raw = raw if isinstance(raw, dict) else {}
        event_time = sample.pop("time")
        sample["event_time"] = event_time
        sample["synthetic"] = raw.get("synthetic")
        sample["is_replay"] = raw.get("is_replay") is True or raw.get("replay") is True
        sample["timing"] = compute_timing_metrics(
            sample["backend_received_at"].astimezone(timezone.utc),
            event_time.astimezone(timezone.utc) if event_time else None,
            clock_sync_verified=False,
            serial_source=sample["serial_source"],
            is_replay=sample["is_replay"],
        ).to_dict()
        samples.append(sample)
    return samples


def _encode(value) -> bytes:
    def encode_date(stamp):
        if isinstance(stamp, datetime):
            return stamp.astimezone(timezone.utc).isoformat()
        raise TypeError(f"cannot export {type(stamp).__name__}")

    return json.dumps(
        value, default=encode_date, ensure_ascii=False, allow_nan=False,
        separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def export_run(connection: Connection, run: dict) -> bytes:
    samples = run_samples(connection, run)
    dataset = {"run": run, "history": run_history(connection, run["run_id"]), "telemetry": samples}
    manifest = {
        "format": "coldguard-run-json-v0",
        "run_id": run["run_id"],
        "device_id": run["device_id"],
        "sample_count": len(samples),
        "clockless_count": sum(row["event_time"] is None for row in samples),
        "dataset_sha256": hashlib.sha256(_encode(dataset)).hexdigest(),
        "order": ["backend_received_at", "id"],
    }
    return _encode({"manifest": manifest, "dataset": dataset})


def run_timeline(connection: Connection, run: dict) -> list[dict]:
    """Use backend chronology with separate observed timestamps and stable ties."""
    device = run["device_id"]
    command_scope = _belongs_to_run(commands, run)
    entries = []

    def add(kind, identity, occurred_at, **evidence):
        entries.append({
            "kind": kind, "id": identity, "backend_at": occurred_at, **evidence,
        })

    for sample in run_samples(connection, run):
        add(
            "telemetry", sample["id"], sample["backend_received_at"],
            raw_id=sample["raw_id"], boot_id=sample["boot_id"], seq=sample["seq"],
            event_time=sample["event_time"], door_state=sample["door_state"],
            applied_cooling=sample["applied_cooling"], applied_duty=sample["applied_duty"],
            synthetic=sample["synthetic"], is_replay=sample["is_replay"],
        )
    observations = connection.execute(
        select(telemetry_raw)
        .where(
            _belongs_to_run(telemetry_raw, run),
            telemetry_raw.c.ingest_status == RECEIVED_OBSERVED,
            telemetry_raw.c.topic.in_((f"coldguard/{device}/event", f"coldguard/{device}/state")),
        )
    ).mappings()
    for row in observations:
        add(
            row["topic"].rsplit("/", 1)[-1] + "_receipt", row["id"], row["backend_received_at"],
            validity=row["ingest_status"], payload=row["raw_json"],
        )
    for row in connection.execute(select(commands).where(command_scope)).mappings():
        add(
            "command_intent", row["command_id"], row["created_db_at"],
            cooling=row["action_cooling"], duty=row["action_duty"], expires_at=row["expires_at"],
        )
    transitions = connection.execute(
        select(command_transitions)
        .join(commands, commands.c.command_id == command_transitions.c.command_id)
        .where(command_scope)
    ).mappings()
    for row in transitions:
        add(
            "command_transition", row["id"], row["occurred_at"], command_id=row["command_id"],
            from_status=row["from_status"], to_status=row["to_status"], reason=row["reason"],
        )
    acks = connection.execute(
        select(command_acks).join(commands, commands.c.command_id == command_acks.c.command_id)
        .where(command_scope, command_acks.c.topic_device_id == device, command_acks.c.payload_device_id == device)
    ).mappings()
    for row in acks:
        add(
            "ack_receipt", row["id"], row["backend_received_at"],
            command_id=row["command_id"], event_time=row["ack_time"],
            verdict=row["device_status"], validity=row["validity"], reason=row["reason_code"],
        )
    return sorted(entries, key=lambda row: (row["backend_at"], row["kind"], row["id"]))
