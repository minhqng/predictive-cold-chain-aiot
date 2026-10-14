"""Raw classification boundary tests (C-W02-04).

`classify_raw` is pure: these tests need no database. They pin the
W02/W03 validation boundary — what counts as valid, invalid-schema, or
malformed — and the exact-payload-preservation rule. Database
round-trip behavior lives in `test_consumer.py` (real provider).
"""

import copy
import hashlib
import json

from coldguard_backend.raw_store import (
    RECEIVED_INVALID_SCHEMA,
    RECEIVED_MALFORMED_JSON,
    RECEIVED_OBSERVED,
    RECEIVED_VALID,
    classify_raw,
)
from coldguard_backend.simulator import build_telemetry

BOOT = "boot-raw-test-001"
RUN = "CG-W02-RAW-001"
TOPIC = "coldguard/coldguard-001/telemetry"


def _wire_bytes(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def test_valid_telemetry_classified_with_identities():
    payload = build_telemetry(boot_id=BOOT, seq=3, run_id=RUN)
    row = classify_raw(TOPIC, _wire_bytes(payload))
    assert row["ingest_status"] == RECEIVED_VALID
    assert (row["device_id"], row["boot_id"], row["seq"]) == ("coldguard-001", BOOT, 3)
    assert row["run_id"] == RUN
    assert row["schema_version"] == 1
    assert row["captured_at"] is not None
    assert row["validation_errors"] is None
    assert row["raw_json"] == payload


def test_exact_wire_text_preserved_byte_identical():
    payload = build_telemetry(boot_id=BOOT, seq=4, run_id=RUN)
    wire = _wire_bytes(payload)
    row = classify_raw(TOPIC, wire)
    assert row["raw_payload"].encode("utf-8") == wire
    assert row["payload_sha256"] == hashlib.sha256(wire).hexdigest()


def test_malformed_json_retained_with_diagnostics():
    wire = b"{this is not json"
    row = classify_raw(TOPIC, wire)
    assert row["ingest_status"] == RECEIVED_MALFORMED_JSON
    assert row["device_id"] is None
    assert row["boot_id"] is None
    assert row["seq"] is None
    assert row["raw_json"] is None
    assert row["raw_payload"] == wire.decode("utf-8")
    assert row["validation_errors"], "malformed input needs diagnostic errors"


def test_non_utf8_bytes_retained_without_identity():
    wire = b"\xff\xfe\x00not-utf8"
    row = classify_raw(TOPIC, wire)
    assert row["ingest_status"] == RECEIVED_MALFORMED_JSON
    assert row["device_id"] is None
    assert row["raw_json"] is None
    assert row["payload_sha256"] == hashlib.sha256(wire).hexdigest()


def test_invalid_schema_retained_with_best_effort_identity():
    payload = build_telemetry(boot_id=BOOT, seq=5, run_id=RUN)
    del payload["boot_id"]
    row = classify_raw(TOPIC, _wire_bytes(payload))
    assert row["ingest_status"] == RECEIVED_INVALID_SCHEMA
    assert row["device_id"] == "coldguard-001"
    assert row["boot_id"] is None
    assert row["seq"] == 5
    assert row["run_id"] == RUN
    assert row["raw_json"] is not None, "parsed JSON projection must survive"
    assert row["validation_errors"], "schema failure needs diagnostic errors"


def test_legacy_dual_channel_is_invalid_not_valid():
    payload = build_telemetry(boot_id=BOOT, seq=6, run_id=RUN)
    payload["electrical"]["power_1"] = 10.0
    row = classify_raw(TOPIC, _wire_bytes(payload))
    assert row["ingest_status"] == RECEIVED_INVALID_SCHEMA


def test_non_telemetry_family_stored_as_observed_not_valid():
    event = {"schema_version": 1, "event_id": "e-1", "device_id": "coldguard-001"}
    row = classify_raw("coldguard/coldguard-001/event", _wire_bytes(event))
    assert row["ingest_status"] == RECEIVED_OBSERVED
    assert row["raw_json"] == event


def test_non_telemetry_malformed_json_is_malformed():
    row = classify_raw("coldguard/coldguard-001/state", b"nope{")
    assert row["ingest_status"] == RECEIVED_MALFORMED_JSON


def test_duplicate_deliveries_classify_identically_for_observable_rows():
    payload = build_telemetry(boot_id=BOOT, seq=9, run_id=RUN)
    wire = _wire_bytes(payload)
    first = classify_raw(TOPIC, wire)
    second = classify_raw(TOPIC, copy.deepcopy(wire))
    assert first["payload_sha256"] == second["payload_sha256"]
    assert first["ingest_status"] == second["ingest_status"] == RECEIVED_VALID
