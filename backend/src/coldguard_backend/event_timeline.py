"""Canonical S2 event projection and bounded backend-time feed."""

import base64
import binascii
import json
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, Text, case, cast, func, literal, null, select, tuple_, union_all
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from coldguard_backend.command_store import ACK_ACCEPTED, command_acks, command_transitions, commands
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.raw_store import RECEIVED_OBSERVED, telemetry_raw


class EventType(StrEnum):
    DOOR_OPENED = "DOOR_OPENED"
    DOOR_CLOSED = "DOOR_CLOSED"
    COMMAND_CREATED = "COMMAND_CREATED"
    COMMAND_ACCEPTED = "COMMAND_ACCEPTED"
    ELECTRICAL_VERIFIED = "ELECTRICAL_VERIFIED"
    THERMAL_VERIFIED = "THERMAL_VERIFIED"


S2_SCENARIOS = frozenset({"S2", "DOOR_DISTURBANCE", "S2_DOOR_DISTURBANCE"})
_SOURCES = {"telemetry", "device_event", "command_transition", "ack_receipt"}


def _decode_cursor(cursor: str | None, run_id: str):
    if cursor is None:
        return None
    try:
        cursor_run, stamp, kind, row_id = json.loads(
            base64.b64decode(cursor, altchars=b"-_", validate=True),
        )
        backend_at = datetime.fromisoformat(stamp)
        if (
            cursor_run == run_id and backend_at.utcoffset() is not None and kind in _SOURCES
            and type(row_id) is int and 0 < row_id < 2**63
        ):
            return backend_at, kind, row_id
    except (TypeError, ValueError, OverflowError, binascii.Error):
        pass
    raise ValueError("invalid timeline cursor")


def _encode_cursor(run_id: str, row: dict) -> str:
    key = [run_id, row["backend_at"].astimezone(timezone.utc).isoformat(), row["kind"], row["source_id"]]
    return base64.urlsafe_b64encode(json.dumps(key, separators=(",", ":")).encode()).decode()


def _entry(kind, source_id, backend_at, event_time, details):
    return select(
        literal(kind).label("kind"), source_id.label("source_id"),
        backend_at.label("backend_at"), event_time.label("event_time"),
        details.label("details"),
    )


def _optional_string(document, key):
    return case((func.jsonb_typeof(document[key]) == "string", document[key].astext))


def _timeline_sources(run):
    device, run_id = run["device_id"], run["run_id"]
    samples, raw, cmd, steps, ack = (
        telemetry.c, telemetry_raw.c, commands.c, command_transitions.c, command_acks.c,
    )
    scope = (cmd.device_id == device) & (cmd.run_id == run_id)
    normalized = _entry(
        "telemetry", samples.id, samples.backend_received_at, samples.time,
        func.jsonb_build_object(
            "raw_id", samples.raw_id, "boot_id", samples.boot_id, "seq", samples.seq,
            "door_state", samples.door_state, "t1_c", samples.t1_c, "t2_c", samples.t2_c,
            "t3_c", samples.t3_c, "voltage_v", samples.cooling_voltage_v,
            "current_a", samples.cooling_current_a, "power_w", samples.cooling_power_w,
            "applied_cooling", samples.applied_cooling, "applied_duty", samples.applied_duty,
            "thermal_quality", samples.thermal_quality, "electrical_quality", samples.electrical_quality,
            "synthetic", raw.raw_json["synthetic"],
        ),
    ).join_from(telemetry, telemetry_raw, samples.raw_id == raw.id).where(
        samples.device_id == device, samples.run_id == run_id,
    )
    raw_doc = cast(raw.raw_json, JSONB)
    source_event_id = raw_doc["event_id"].astext
    event_type = raw_doc["event_type"].astext
    first_event_receipt = func.min(raw.id).over(partition_by=source_event_id)
    reported_command = _optional_string(raw_doc, "caused_by_command_id")
    linked_command = select(cmd.command_id).where(
        scope, cmd.command_id == reported_command,
    ).correlate(telemetry_raw).scalar_subquery()
    no_event_time = cast(null(), DateTime(timezone=True))
    door_rows = _entry(
        "device_event", raw.id, raw.backend_received_at, no_event_time,
        func.jsonb_build_object(
            "event_type", event_type, "source_event_id", source_event_id,
            "boot_id", raw.boot_id, "event_id_conflict", raw.id != first_event_receipt,
            "reported_event_time", raw_doc["event_time"], "reported_command_id", reported_command,
            "command_id", linked_command, "prediction_id", _optional_string(raw_doc, "prediction_id"),
            "correlation_id", _optional_string(raw_doc, "correlation_id"), "synthetic", raw_doc["synthetic"],
        ),
    ).where(
        raw.device_id == device, raw.run_id == run_id, raw.topic == f"coldguard/{device}/event",
        raw.ingest_status == RECEIVED_OBSERVED, raw_doc["schema_version"] == cast(literal("1"), JSONB),
        func.jsonb_typeof(raw_doc["event_id"]) == "string", func.btrim(source_event_id) != "",
        event_type.in_((EventType.DOOR_OPENED.value, EventType.DOOR_CLOSED.value)),
    ).add_columns(
        func.row_number().over(
            partition_by=(source_event_id, raw_doc), order_by=raw.id,
        ).label("receipt_number"),
    ).subquery()
    door = select(
        door_rows.c.kind, door_rows.c.source_id, door_rows.c.backend_at,
        door_rows.c.event_time, door_rows.c.details,
    ).where(door_rows.c.receipt_number == 1)
    applied_ack = select(ack.id).where(
        ack.command_id == cmd.command_id, ack.topic_device_id == device,
        ack.payload_device_id == device, ack.validity == "VALID",
        (ack.device_status == "ACCEPTED")
        | ((ack.device_status == "DUPLICATE_CANONICAL") & (ack.canonical_status == "ACCEPTED")),
    ).correlate(commands).exists()
    transitions = _entry(
        "command_transition", steps.id, steps.occurred_at, no_event_time,
        func.jsonb_build_object(
            "event_type", case(
                (steps.from_status.is_(None), literal(EventType.COMMAND_CREATED.value, Text)),
                ((steps.to_status == ACK_ACCEPTED) & applied_ack,
                 literal(EventType.COMMAND_ACCEPTED.value, Text)),
            ),
            "command_id", cmd.command_id, "prediction_id", cmd.prediction_id,
            "from_status", steps.from_status, "to_status", steps.to_status,
            "reason", steps.reason, "cooling", cmd.action_cooling, "duty", cmd.action_duty,
        ),
    ).join_from(command_transitions, commands, steps.command_id == cmd.command_id).where(scope)
    receipts = _entry(
        "ack_receipt", ack.id, ack.backend_received_at, ack.ack_time,
        func.jsonb_build_object(
            "command_id", cmd.command_id, "prediction_id", cmd.prediction_id,
            "verdict", ack.device_status, "validity", ack.validity, "reason", ack.reason_code,
        ),
    ).join_from(command_acks, commands, ack.command_id == cmd.command_id).where(
        scope, ack.topic_device_id == device, ack.payload_device_id == device,
    )
    return union_all(normalized, door, transitions, receipts).subquery()


def _reported_time(value):
    if isinstance(value, str):
        try:
            stamp = datetime.fromisoformat(value)
            if stamp.utcoffset() is not None:
                return stamp
        except ValueError:
            pass
    return None


def s2_timeline_page(
    connection: Connection, run: dict, *, limit: int, cursor: str | None = None,
) -> dict:
    if run["scenario_id"] not in S2_SCENARIOS:
        raise ValueError("run must be an S2 door-disturbance run")
    after = _decode_cursor(cursor, run["run_id"])
    sources = _timeline_sources(run)
    sort_key = (sources.c.backend_at, sources.c.kind, sources.c.source_id)
    query = select(sources).order_by(*sort_key).limit(limit + 1)
    if after:
        query = query.where(tuple_(*sort_key) > tuple_(*after))
    rows = connection.execute(query).mappings().all()
    items = []
    for row in rows[:limit]:
        entry = dict(row)
        entry["id"] = f"{entry['kind']}:{entry['source_id']}"
        if entry["kind"] == "device_event":
            entry["event_time"] = _reported_time(entry["details"]["reported_event_time"])
        items.append(entry)
    return {
        "schema_version": 1, "run_id": run["run_id"], "device_id": run["device_id"],
        "items": items,
        "next_cursor": _encode_cursor(run["run_id"], items[-1]) if items else cursor,
        "has_more": len(rows) > limit,
    }
