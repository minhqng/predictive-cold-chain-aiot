"""End-to-end ingest orchestration + rejection visibility on real PostgreSQL (C-W03-05/06).

Runs only with COLDGUARD_TEST_DATABASE_URL set. Proves the
raw-before-derived transaction strategy at the cheapest layer that can
show it (direct ``ingest_message`` calls, no broker needed): valid
input yields raw + normalized rows; every rejection class yields raw
evidence with diagnostics and no normalized sample; duplicate
deliveries yield N raw rows with one normalized sample and honest
metrics; conflicting replays never overwrite authority; a normalized
failure still leaves committed raw evidence (simulated by forcing the
normalized step to raise — the raw row must survive).
"""

import json
import uuid

import pytest
from sqlalchemy import create_engine, text

from coldguard_backend.ingest import IngestMetrics, ingest_message

needs_real_db = pytest.mark.skipif(
    not __import__("os").environ.get("COLDGUARD_TEST_DATABASE_URL"),
    reason="requires COLDGUARD_TEST_DATABASE_URL pointing at a test database",
)

TOPIC = "coldguard/coldguard-001/telemetry"


def _db_url() -> str:
    import os

    return os.environ["COLDGUARD_TEST_DATABASE_URL"]


def _wire(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _payload(**overrides) -> dict:
    from coldguard_backend.simulator import build_telemetry

    return build_telemetry(
        boot_id=overrides.pop("boot_id", f"boot-ing-{uuid.uuid4().hex[:8]}"),
        seq=overrides.pop("seq", 1),
        run_id=overrides.pop("run_id", f"CG-W03-ING-{uuid.uuid4().hex[:8]}"),
        **overrides,
    )


def _normalized_count(device_id: str, boot_id: str, seq: int) -> int:
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            return connection.execute(
                text(
                    "SELECT count(*) FROM telemetry WHERE device_id = :device "
                    "AND boot_id = :boot AND seq = :seq"
                ),
                {"device": device_id, "boot": boot_id, "seq": seq},
            ).scalar()
    finally:
        engine.dispose()


def _raw_statuses_for(payload_sha: str) -> list:
    engine = create_engine(_db_url())
    try:
        with engine.connect() as connection:
            return connection.execute(
                text(
                    "SELECT ingest_status, validation_errors FROM telemetry_raw "
                    "WHERE payload_sha256 = :sha ORDER BY id"
                ),
                {"sha": payload_sha},
            ).all()
    finally:
        engine.dispose()


@needs_real_db
def test_valid_message_yields_raw_and_normalized():
    import hashlib

    engine = create_engine(_db_url())
    try:
        metrics = IngestMetrics()
        payload = _payload()
        outcome = ingest_message(engine, topic=TOPIC, payload=_wire(payload), metrics=metrics)
        assert outcome["raw_status"] == "RECEIVED_VALID"
        assert outcome["normalized"]["outcome"] == "inserted"
        assert _normalized_count(payload["device_id"], payload["boot_id"], payload["seq"]) == 1
        rows = _raw_statuses_for(hashlib.sha256(_wire(payload)).hexdigest())
        assert rows and rows[0][0] == "RECEIVED_VALID"
        snapshot = metrics.snapshot()
        assert snapshot["normalized_new"] == 1
        assert snapshot["rejected_schema"] == 0
    finally:
        engine.dispose()


@needs_real_db
def test_duplicate_delivery_one_sample_with_metric():
    engine = create_engine(_db_url())
    try:
        metrics = IngestMetrics()
        payload = _payload()
        wire = _wire(payload)
        first = ingest_message(engine, topic=TOPIC, payload=wire, metrics=metrics)
        second = ingest_message(engine, topic=TOPIC, payload=wire, metrics=metrics)
        assert first["normalized"]["outcome"] == "inserted"
        assert second["normalized"]["outcome"] == "exact_duplicate"
        assert second["normalized"]["id"] == first["normalized"]["id"]
        assert _normalized_count(payload["device_id"], payload["boot_id"], payload["seq"]) == 1
        engine2 = create_engine(_db_url())
        try:
            with engine2.connect() as connection:
                raw_count = connection.execute(
                    text(
                        "SELECT count(*) FROM telemetry_raw WHERE device_id = :device "
                        "AND boot_id = :boot AND seq = :seq"
                    ),
                    {
                        "device": payload["device_id"],
                        "boot": payload["boot_id"],
                        "seq": payload["seq"],
                    },
                ).scalar()
        finally:
            engine2.dispose()
        assert raw_count == 2, "both deliveries must stay visible as raw evidence"
        assert metrics.snapshot()["exact_duplicates"] == 1
    finally:
        engine.dispose()


@needs_real_db
def test_conflicting_replay_preserves_authority_and_counts_conflict():
    engine = create_engine(_db_url())
    try:
        metrics = IngestMetrics()
        payload = _payload()
        tampered = dict(payload)
        tampered["environment"] = dict(payload["environment"], rh=10.0)
        first = ingest_message(engine, topic=TOPIC, payload=_wire(payload), metrics=metrics)
        second = ingest_message(engine, topic=TOPIC, payload=_wire(tampered), metrics=metrics)
        assert first["normalized"]["outcome"] == "inserted"
        assert second["normalized"]["outcome"] == "conflict"
        assert _normalized_count(payload["device_id"], payload["boot_id"], payload["seq"]) == 1
        assert metrics.snapshot()["conflicts"] == 1
        assert metrics.snapshot()["exact_duplicates"] == 0
    finally:
        engine.dispose()


@needs_real_db
def test_rejection_classes_visible_with_no_normalized_sample():
    import hashlib

    engine = create_engine(_db_url())
    try:
        metrics = IngestMetrics()
        cases: list[tuple[str, bytes]] = []
        # Malformed JSON.
        cases.append(("malformed", b"{broken-json"))
        # Missing identity.
        bad = _payload()
        del bad["boot_id"]
        cases.append(("missing_identity", _wire(bad)))
        # Wrong field type (lax coercion would have rescued this).
        bad = _payload()
        bad["seq"] = "not-a-seq"
        cases.append(("wrong_type", _wire(bad)))
        # Unsupported schema.
        bad = _payload()
        bad["schema_version"] = 99
        cases.append(("unsupported_schema", _wire(bad)))
        # Topic/payload device mismatch.
        bad = _payload()
        cases.append(("topic_mismatch", _wire(bad)))
        # Unusable required quality (None under VALID).
        bad = _payload()
        bad["thermal"]["t1"] = None
        cases.append(("bad_quality", _wire(bad)))

        for name, wire in cases:
            topic = "coldguard/other-device/telemetry" if name == "topic_mismatch" else TOPIC
            outcome = ingest_message(engine, topic=topic, payload=wire, metrics=metrics)
            assert outcome["normalized"] in (
                "rejected:RECEIVED_INVALID_SCHEMA",
                "rejected:RECEIVED_MALFORMED_JSON",
                "rejected:REJECTED_TOPIC_MISMATCH",
            ), name
            rows = _raw_statuses_for(hashlib.sha256(wire).hexdigest())
            assert rows, f"rejected case {name!r} left no raw evidence"
            assert rows[0][0] in (
                "RECEIVED_INVALID_SCHEMA",
                "RECEIVED_MALFORMED_JSON",
                "REJECTED_TOPIC_MISMATCH",
            ), name
            assert rows[0][1], f"rejected case {name!r} needs diagnostics"
        if True:
            mismatch_rows = _raw_statuses_for(hashlib.sha256(cases[4][1]).hexdigest())
            assert mismatch_rows[0][0] == "REJECTED_TOPIC_MISMATCH"
        snapshot = metrics.snapshot()
        assert snapshot["normalized_new"] == 0
        assert snapshot["rejected_schema"] >= 5
        assert snapshot["rejected_topic_mismatch"] == 1
    finally:
        engine.dispose()


@needs_real_db
def test_normalized_failure_preserves_committed_raw():
    engine = create_engine(_db_url())
    try:
        import coldguard_backend.ingest as ingest_module

        metrics = IngestMetrics()
        payload = _payload()
        real_insert = ingest_module.insert_normalized

        def _boom(engine_or_conn, row):
            raise RuntimeError("simulated normalized outage")

        ingest_module.insert_normalized = _boom
        try:
            outcome = ingest_message(
                engine, topic=TOPIC, payload=_wire(payload), metrics=metrics
            )
        finally:
            ingest_module.insert_normalized = real_insert
        assert outcome["raw_status"] == "RECEIVED_VALID"
        assert outcome["normalized"] == "failed"
        assert metrics.snapshot()["normalization_failures"] == 1
        # The raw row committed before the normalized failure.
        engine2 = create_engine(_db_url())
        try:
            with engine2.connect() as connection:
                raw_count = connection.execute(
                    text(
                        "SELECT count(*) FROM telemetry_raw WHERE device_id = :device "
                        "AND boot_id = :boot AND seq = :seq"
                    ),
                    {
                        "device": payload["device_id"],
                        "boot": payload["boot_id"],
                        "seq": payload["seq"],
                    },
                ).scalar()
        finally:
            engine2.dispose()
        assert raw_count == 1
        assert _normalized_count(payload["device_id"], payload["boot_id"], payload["seq"]) == 0
    finally:
        engine.dispose()


@needs_real_db
def test_non_telemetry_family_observed_without_normalized_sample():
    engine = create_engine(_db_url())
    try:
        metrics = IngestMetrics()
        event = {"schema_version": 1, "event_id": "e-1", "device_id": "coldguard-001"}
        outcome = ingest_message(
            engine,
            topic="coldguard/coldguard-001/event",
            payload=_wire(event),
            metrics=metrics,
        )
        assert outcome["raw_status"] == "RECEIVED_OBSERVED"
        assert outcome["normalized"] == "observed"
        assert metrics.snapshot()["observed_other"] == 1
    finally:
        engine.dispose()
