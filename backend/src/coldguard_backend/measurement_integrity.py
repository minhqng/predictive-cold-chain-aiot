"""Exact live-measurement provenance shared by dispatch and assessment gates.

This proves storage/content consistency, not that a generated envelope came
from real hardware. Physical provenance still requires an independent authority.
"""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.engine import Connection

from coldguard_backend.normalized_store import telemetry
from coldguard_backend.raw_store import telemetry_raw
from coldguard_backend.reconciliation import validate_winner


def measurement_rows(connection: Connection, ids: list[int], *, lock: bool = False) -> list[tuple[dict, dict]]:
    query = select(telemetry, *[
        column.label("source_" + column.name) for column in telemetry_raw.c
    ]).join_from(telemetry, telemetry_raw, telemetry.c.raw_id == telemetry_raw.c.id).where(
        telemetry.c.id.in_(ids),
    ).order_by(telemetry.c.id)
    if lock:
        query = query.with_for_update(read=True, of=[telemetry, telemetry_raw])
    return [(
        {column.name: row[column.name] for column in telemetry.c},
        {column.name: row["source_" + column.name] for column in telemetry_raw.c},
    ) for row in connection.execute(query).mappings()]


def live_measurement_errors(sample: dict, source: dict) -> list[str]:
    errors = validate_winner(sample, source)
    try:
        parsed = json.loads(source["raw_payload"])
        digest = hashlib.sha256(source["raw_payload"].encode("utf-8")).hexdigest()
    except (KeyError, TypeError, ValueError, UnicodeError):
        return [*errors, "RAW_BYTES_INVALID"]
    if digest != source["payload_sha256"]:
        errors.append("RAW_DIGEST_MISMATCH")
    if not isinstance(parsed, dict) or source["raw_json"] != parsed:
        errors.append("RAW_PROJECTION_MISMATCH")
    if not isinstance(parsed, dict) or any(
        parsed.get(flag, False) is not False for flag in ("synthetic", "replay", "is_replay")
    ) or sample["twin_eligible"] is not True:
        errors.append("NOT_LIVE_EVIDENCE")
    captured, received = sample["time"], sample["backend_received_at"]
    if captured is None or source["captured_at"] != captured or captured > received:
        errors.append("ACQUISITION_UNPROVEN")
    if source["backend_received_at"] != received:
        errors.append("RECEIPT_MISMATCH")
    return errors
