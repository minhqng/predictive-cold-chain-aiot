"""Normalized telemetry + DB-arbitrated idempotency against real PostgreSQL (C-W03-03/04).

Runs only with COLDGUARD_TEST_DATABASE_URL set (never SQLite: NULL
unique semantics, ON CONFLICT behavior and constraint enforcement are
provider facts under test). Proves: canonical UNIQUE enforcement,
intentional ON CONFLICT outcomes (insert / exact-duplicate /
conflict), authoritative-row preservation on conflicting replays,
nullable-identity exclusion from the normalized table, mapping
semantics (names, NULL-not-zero, no legacy fields), provenance, and
deterministic concurrency (exactly one authoritative sample under
barrier-synchronized competing inserts — no random delays).
"""

import json
import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from coldguard_backend.normalized_store import (
    COMPARE_FIELDS,
    fetch_by_identity,
    insert_normalized,
    map_to_row,
)
from coldguard_backend.raw_store import store_raw
from coldguard_backend.validation import validate_telemetry_payload

needs_real_db = pytest.mark.skipif(
    not __import__("os").environ.get("COLDGUARD_TEST_DATABASE_URL"),
    reason="requires COLDGUARD_TEST_DATABASE_URL pointing at a test database",
)

TOPIC = "coldguard/coldguard-001/telemetry"


def _db_url() -> str:
    import os

    return os.environ["COLDGUARD_TEST_DATABASE_URL"]


def _payload(**overrides) -> dict:
    from coldguard_backend.simulator import build_telemetry

    payload = build_telemetry(
        boot_id=overrides.pop("boot_id", f"boot-norm-{uuid.uuid4().hex[:8]}"),
        seq=overrides.pop("seq", 1),
        run_id=overrides.pop("run_id", f"CG-W03-NORM-{uuid.uuid4().hex[:8]}"),
    )
    payload.update(overrides)
    return payload


def _wire(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _validated_row(engine, payload: dict, topic: str = TOPIC) -> dict:
    validated, errors = validate_telemetry_payload(payload)
    assert validated is not None, errors
    received = datetime.now(timezone.utc)
    stored = store_raw(engine, topic=topic, payload=_wire(payload), received_at=received)
    row = map_to_row(validated, raw_id=stored["id"], received_at=received)
    row["_raw_status"] = stored["ingest_status"]
    return row


@needs_real_db
def test_new_identity_creates_one_sample_with_provenance():
    engine = create_engine(_db_url())
    try:
        payload = _payload()
        row = _validated_row(engine, payload)
        assert row["_raw_status"] == "RECEIVED_VALID"
        outcome = insert_normalized(engine, {k: v for k, v in row.items() if not k.startswith("_")})
        assert outcome["outcome"] == "inserted"
        stored = fetch_by_identity(
            engine,
            device_id=payload["device_id"],
            boot_id=payload["boot_id"],
            seq=payload["seq"],
        )
        assert stored is not None
        assert stored["id"] == outcome["id"]
        assert stored["raw_id"] == row["raw_id"]
        # Mapping semantics: wire names land on canonical columns.
        assert stored["t1_c"] == payload["thermal"]["t1"]
        assert stored["t_air_c"] == payload["environment"]["t_air"]
        assert stored["rh_pct"] == payload["environment"]["rh"]
        assert stored["door_state"] == payload["door"]["state"]
        assert stored["cooling_voltage_v"] == payload["electrical"]["voltage_v"]
        assert stored["cooling_current_a"] == payload["electrical"]["current_a"]
        assert stored["cooling_power_w"] == payload["electrical"]["power_w"]
        assert stored["cooling_energy_counter_wh"] == payload["electrical"]["energy_wh"]
        assert stored["applied_cooling"] == payload["actuation"]["cooling"]
        assert stored["applied_duty"] == payload["actuation"]["duty"]
        assert stored["thermal_quality"] == payload["quality"]["thermal"]
        assert stored["device_mode"] == payload["quality"]["device_mode"]
        assert stored["hardware_config_id"] == payload["hardware_config_id"]
        assert stored["schema_version"] == 1
        for legacy in ("current_1", "power_1", "cmd_1"):
            assert legacy not in COMPARE_FIELDS
    finally:
        engine.dispose()


@needs_real_db
def test_exact_replay_creates_no_second_sample():
    engine = create_engine(_db_url())
    try:
        payload = _payload()
        first = _validated_row(engine, payload)
        second = _validated_row(engine, payload)
        clean = lambda row: {k: v for k, v in row.items() if not k.startswith("_")}
        outcome_first = insert_normalized(engine, clean(first))
        outcome_second = insert_normalized(engine, clean(second))
        assert outcome_first["outcome"] == "inserted"
        assert outcome_second["outcome"] == "exact_duplicate"
        assert outcome_second["id"] == outcome_first["id"]
        with engine.connect() as connection:
            count = connection.execute(
                text(
                    "SELECT count(*) FROM telemetry WHERE device_id = :device "
                    "AND boot_id = :boot AND seq = :seq"
                ),
                {"device": payload["device_id"], "boot": payload["boot_id"], "seq": payload["seq"]},
            ).scalar()
        assert count == 1
    finally:
        engine.dispose()


@needs_real_db
def test_conflicting_replay_never_overwrites_authority():
    engine = create_engine(_db_url())
    try:
        payload = _payload()
        first = _validated_row(engine, payload)
        outcome_first = insert_normalized(
            engine, {k: v for k, v in first.items() if not k.startswith("_")}
        )
        tampered = dict(payload)
        tampered["thermal"] = dict(payload["thermal"], t1=payload["thermal"]["t1"] + 5.0)
        second = _validated_row(engine, tampered)
        outcome_second = insert_normalized(
            engine, {k: v for k, v in second.items() if not k.startswith("_")}
        )
        assert outcome_second["outcome"] == "conflict"
        assert outcome_second["id"] == outcome_first["id"]
        stored = fetch_by_identity(
            engine,
            device_id=payload["device_id"],
            boot_id=payload["boot_id"],
            seq=payload["seq"],
        )
        assert stored["t1_c"] == payload["thermal"]["t1"], (
            "authoritative physical truth was overwritten by a conflicting replay"
        )
        # Both deliveries remain visible as raw evidence.
        with engine.connect() as connection:
            raw_count = connection.execute(
                text(
                    "SELECT count(*) FROM telemetry_raw WHERE device_id = :device "
                    "AND boot_id = :boot AND seq = :seq"
                ),
                {"device": payload["device_id"], "boot": payload["boot_id"], "seq": payload["seq"]},
            ).scalar()
        assert raw_count == 2
    finally:
        engine.dispose()


@needs_real_db
def test_null_identity_cannot_enter_normalized_table():
    engine = create_engine(_db_url())
    try:
        payload = _payload()
        row = _validated_row(engine, payload)
        row = {k: v for k, v in row.items() if not k.startswith("_")}
        row["boot_id"] = None
        with pytest.raises(Exception):
            insert_normalized(engine, row)
        # Raw rejected evidence with NULL identity is still storable.
        malformed = store_raw(engine, topic=TOPIC, payload=b"{broken")
        assert malformed["boot_id"] is None
    finally:
        engine.dispose()


@needs_real_db
def test_same_timestamp_different_seq_are_distinct_samples():
    engine = create_engine(_db_url())
    try:
        boot = f"boot-ts-{uuid.uuid4().hex[:8]}"
        run = f"CG-W03-TS-{uuid.uuid4().hex[:8]}"
        outcomes = []
        for seq in (10, 11):
            row = _validated_row(engine, _payload(boot_id=boot, seq=seq, run_id=run))
            outcomes.append(
                insert_normalized(engine, {k: v for k, v in row.items() if not k.startswith("_")})
            )
        assert [outcome["outcome"] for outcome in outcomes] == ["inserted", "inserted"]
    finally:
        engine.dispose()


@needs_real_db
def test_same_seq_different_boot_or_device_are_distinct():
    engine = create_engine(_db_url())
    try:
        outcomes = []
        variants = [
            _payload(boot_id=f"boot-a-{uuid.uuid4().hex[:6]}", seq=77),
            _payload(boot_id=f"boot-b-{uuid.uuid4().hex[:6]}", seq=77),
        ]
        for payload in variants:
            row = _validated_row(engine, payload)
            outcomes.append(
                insert_normalized(engine, {k: v for k, v in row.items() if not k.startswith("_")})
            )
        assert [outcome["outcome"] for outcome in outcomes] == ["inserted", "inserted"]
    finally:
        engine.dispose()


@needs_real_db
def test_missing_measurements_stay_null_never_zero():
    engine = create_engine(_db_url())
    try:
        payload = _payload()
        payload["thermal"]["t3"] = None
        payload["quality"]["thermal"] = "DEGRADED"
        payload["quality"]["overall"] = "DEGRADED"
        row = _validated_row(engine, payload)
        outcome = insert_normalized(
            engine, {k: v for k, v in row.items() if not k.startswith("_")}
        )
        assert outcome["outcome"] == "inserted"
        stored = fetch_by_identity(
            engine,
            device_id=payload["device_id"],
            boot_id=payload["boot_id"],
            seq=payload["seq"],
        )
        assert stored["t3_c"] is None
        assert stored["t3_c"] != 0.0
        assert stored["thermal_quality"] == "DEGRADED"
    finally:
        engine.dispose()


@needs_real_db
def test_concurrent_delivery_yields_exactly_one_sample():
    # Deterministic race: two threads block on one barrier, then race
    # the same identity through separate connections. No random delays.
    engine = create_engine(_db_url())
    try:
        payload = _payload()
        validated, errors = validate_telemetry_payload(payload)
        assert validated is not None, errors
        received = datetime.now(timezone.utc)
        stored = store_raw(engine, topic=TOPIC, payload=_wire(payload), received_at=received)
        base = map_to_row(validated, raw_id=stored["id"], received_at=received)
        barrier = threading.Barrier(2)
        outcomes: list[dict] = []
        lock = threading.Lock()

        def worker() -> None:
            local_engine = create_engine(_db_url())
            try:
                barrier.wait(timeout=15)
                outcome = insert_normalized(local_engine, dict(base))
                with lock:
                    outcomes.append(outcome)
            finally:
                local_engine.dispose()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        assert len(outcomes) == 2
        kinds = sorted(outcome["outcome"] for outcome in outcomes)
        assert kinds == ["exact_duplicate", "inserted"], kinds
        assert outcomes[0]["id"] == outcomes[1]["id"]
        with engine.connect() as connection:
            count = connection.execute(
                text(
                    "SELECT count(*) FROM telemetry WHERE device_id = :device "
                    "AND boot_id = :boot AND seq = :seq"
                ),
                {"device": payload["device_id"], "boot": payload["boot_id"], "seq": payload["seq"]},
            ).scalar()
        assert count == 1
    finally:
        engine.dispose()


@needs_real_db
def test_same_instant_different_offset_is_exact_duplicate():
    # Event-time identity is the instant, not its textual offset.
    engine = create_engine(_db_url())
    try:
        from coldguard_backend.simulator import build_telemetry

        boot = f"boot-tz-{uuid.uuid4().hex[:8]}"
        run = f"CG-W03-TZ-{uuid.uuid4().hex[:8]}"
        first_payload = build_telemetry(boot_id=boot, seq=30, run_id=run)
        second_payload = build_telemetry(boot_id=boot, seq=30, run_id=run)
        from datetime import timedelta

        instant = datetime.fromisoformat(
            first_payload["captured_at"].replace("Z", "+00:00")
        )
        # Same instant, different textual offset (+02:00 vs Z).
        second_payload["captured_at"] = instant.astimezone(
            timezone(timedelta(hours=2))
        ).isoformat()
        assert second_payload["captured_at"] != first_payload["captured_at"]
        first = _validated_row(engine, first_payload)
        second = _validated_row(engine, second_payload)
        clean = lambda row: {k: v for k, v in row.items() if not k.startswith("_")}
        assert first["_raw_status"] == second["_raw_status"] == "RECEIVED_VALID"
        assert insert_normalized(engine, clean(first))["outcome"] == "inserted"
        outcome = insert_normalized(engine, clean(second))
        assert outcome["outcome"] == "exact_duplicate", (
            "same instant in a different textual offset must not be a conflict"
        )
    finally:
        engine.dispose()


@needs_real_db
def test_late_older_event_time_stored_historically():
    engine = create_engine(_db_url())
    try:
        boot = f"boot-ooo-{uuid.uuid4().hex[:8]}"
        run = f"CG-W03-OOO-{uuid.uuid4().hex[:8]}"
        from coldguard_backend.simulator import build_telemetry

        newer = build_telemetry(boot_id=boot, seq=20, run_id=run)
        older = build_telemetry(boot_id=boot, seq=19, run_id=run)
        for payload in (newer, older):
            row = _validated_row(engine, payload)
            outcome = insert_normalized(
                engine, {k: v for k, v in row.items() if not k.startswith("_")}
            )
            assert outcome["outcome"] == "inserted"
        with engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM telemetry WHERE boot_id = :boot"),
                {"boot": boot},
            ).scalar()
        assert count == 2, "out-of-order event time must not discard valid history"
    finally:
        engine.dispose()
