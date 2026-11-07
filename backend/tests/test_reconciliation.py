"""Reconciliation tests (C-W05-03; W05-FIX-01/02/03).

Two layers:

* pure unit tests for the historical-classification and winner-validation
  decision functions (no database);
 * real-PostgreSQL provider tests for the full bounded, snapshot-consistent
  reconciliation. These skip honestly when ``COLDGUARD_TEST_DATABASE_URL`` is
  unset — never a silent pass — and each scopes itself to a unique device and
  cleans up so the shared disposable database is not polluted.

The provider suite deliberately reproduces the original audit defects: the
false-positive ``{"calibration_id": "CAL-01"}`` winner seed must now FAIL, a
normalization failure immediately before a later success must NOT be classified
historical, and an unaudited pre-boundary delivery must fail closed.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from coldguard_backend.contracts import Telemetry
from coldguard_backend.ingest import ingest_message
from coldguard_backend.normalized_store import map_to_row, telemetry
from coldguard_backend.raw_store import (
    RECEIVED_INVALID_SCHEMA,
    RECEIVED_VALID,
    store_raw,
    telemetry_raw,
)
from coldguard_backend.reconciliation import (
    CONFIRMED_FAILURE,
    CONFIRMED_HISTORICAL,
    classify_unnormalized_valid,
    reconcile_telemetry,
    validate_winner,
)
from coldguard_backend.validation import validate_telemetry_payload

BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURE_V0 = BACKEND_DIR / "fixtures" / "telemetry_v0.json"

OLD = datetime(2020, 1, 1, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Pure unit tests (no database)
# ---------------------------------------------------------------------------


def test_classify_post_boundary_missing_normalized_is_failure():
    assert classify_unnormalized_valid(NOW, NOW, None) == "normalization_failure"
    assert classify_unnormalized_valid(NOW, OLD, None) == "normalization_failure"


def test_classify_pre_boundary_unaudited_is_unverified():
    assert classify_unnormalized_valid(OLD, NOW, None) == "historical_unverified"


def test_classify_pre_boundary_confirmed_historical():
    assert (
        classify_unnormalized_valid(OLD, NOW, CONFIRMED_HISTORICAL)
        == "historical_confirmed"
    )


def test_classify_pre_boundary_confirmed_failure():
    assert (
        classify_unnormalized_valid(OLD, NOW, CONFIRMED_FAILURE)
        == "normalization_failure"
    )


def test_classification_uses_boundary_not_row_order():
    # Two deliveries with identical timestamps but different audit verdicts
    # classify differently — proof the decision is not derived from ordering.
    assert classify_unnormalized_valid(OLD, NOW, None) == "historical_unverified"
    assert (
        classify_unnormalized_valid(OLD, NOW, CONFIRMED_HISTORICAL)
        == "historical_confirmed"
    )


def _valid_payload(**overrides) -> dict:
    payload = json.loads(FIXTURE_V0.read_text(encoding="utf-8"))
    payload.update(
        device_id="coldguard-001",
        boot_id="boot-unit",
        seq=1,
        captured_at=NOW.isoformat(),
    )
    payload.update(overrides)
    return payload


def _winner_pair(payload: dict) -> tuple[dict, dict]:
    validated, errors = validate_telemetry_payload(payload)
    assert validated is not None, errors
    norm = map_to_row(validated, raw_id=1, received_at=NOW)
    norm["id"] = 1
    norm["twin_eligible"] = False
    raw = {
        "id": 1,
        "raw_payload": json.dumps(payload),
        "ingest_status": RECEIVED_VALID,
        "topic": f"coldguard/{payload['device_id']}/telemetry",
        "device_id": payload["device_id"],
        "boot_id": payload["boot_id"],
        "seq": payload["seq"],
        "run_id": payload.get("run_id"),
        "backend_received_at": NOW,
    }
    return norm, raw


def test_validate_winner_accepts_genuine_payload():
    norm, raw = _winner_pair(_valid_payload())
    assert validate_winner(norm, raw) == []


def test_validate_winner_flags_missing_raw():
    norm, _ = _winner_pair(_valid_payload())
    assert validate_winner(norm, None) == ["WINNER_MISSING"]


def test_validate_winner_rejects_invalid_calibration_only_seed():
    # The original false-positive fixture: not a telemetry message at all.
    norm, raw = _winner_pair(_valid_payload())
    raw["raw_payload"] = '{"calibration_id": "CAL-01"}'
    assert "WINNER_INVALID_PAYLOAD" in validate_winner(norm, raw)


def test_validate_winner_flags_unadmitted_raw():
    norm, raw = _winner_pair(_valid_payload())
    raw["ingest_status"] = RECEIVED_INVALID_SCHEMA
    assert "WINNER_NOT_ADMITTED" in validate_winner(norm, raw)


def test_validate_winner_flags_content_mismatch():
    norm, raw = _winner_pair(_valid_payload())
    norm["t1_c"] = (norm["t1_c"] or 0.0) + 5.0
    assert "WINNER_CONTENT_MISMATCH" in validate_winner(norm, raw)


def test_validate_winner_flags_identity_mismatch():
    norm, raw = _winner_pair(_valid_payload())
    norm["seq"] = 999
    codes = validate_winner(norm, raw)
    assert "WINNER_IDENTITY_MISMATCH" in codes


def test_validate_winner_flags_topic_mismatch():
    norm, raw = _winner_pair(_valid_payload())
    raw["topic"] = "coldguard/other-device/telemetry"
    assert "WINNER_TOPIC_MISMATCH" in validate_winner(norm, raw)


# ---------------------------------------------------------------------------
# Real PostgreSQL provider tests
# ---------------------------------------------------------------------------


def _db_url() -> str:
    return os.environ["COLDGUARD_TEST_DATABASE_URL"]


def _upgrade_head() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(BACKEND_DIR / "src/coldguard_backend/migrations")
    )
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _db_url()
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture
def db_engine():
    if not os.environ.get("COLDGUARD_TEST_DATABASE_URL"):
        pytest.skip("requires COLDGUARD_TEST_DATABASE_URL pointing at a test database")
    _upgrade_head()
    engine = create_engine(_db_url())
    try:
        yield engine
    finally:
        engine.dispose()


def _device() -> str:
    return f"recon-{uuid4().hex}"


def _payload(device: str, seq: int, **overrides) -> dict:
    payload = json.loads(FIXTURE_V0.read_text(encoding="utf-8"))
    payload.update(
        device_id=device,
        boot_id=f"boot-{device}",
        seq=seq,
        captured_at=datetime.now(timezone.utc).isoformat(),
        run_id=f"RUN-{device}",
    )
    payload.update(overrides)
    return payload


def _cleanup(engine, device: str) -> None:
    with engine.begin() as conn:
        conn.execute(telemetry.delete().where(telemetry.c.device_id == device))
        conn.execute(
            text("DELETE FROM reconciliation_legacy_audit WHERE raw_id IN "
                 "(SELECT id FROM telemetry_raw WHERE device_id = :d)"),
            {"d": device},
        )
        conn.execute(telemetry_raw.delete().where(telemetry_raw.c.device_id == device))


def _ingest(engine, device: str, seq: int, **overrides) -> dict:
    payload = _payload(device, seq, **overrides)
    return ingest_message(
        engine,
        topic=f"coldguard/{device}/telemetry",
        payload=json.dumps(payload).encode(),
    )


def test_reconcile_valid_end_to_end_passes(db_engine):
    device = _device()
    try:
        for seq in (1, 2, 3):
            result = _ingest(db_engine, device, seq)
            assert result["normalized"]["outcome"] == "inserted"
        report = reconcile_telemetry(db_engine, device_id=device)
        assert report.raw_total == 3
        assert report.normalized_total == 3
        assert report.unique_normalized_deliveries == 3
        assert report.discrepancy == 0
        assert report.winner_integrity.total == 0
        assert report.is_reconciled is True
    finally:
        _cleanup(db_engine, device)


def test_reconcile_rejects_invalid_winner_seed(db_engine):
    """The old false-positive fixture must now FAIL reconciliation."""
    device = _device()
    try:
        with db_engine.begin() as conn:
            raw_id = conn.execute(
                text(
                    "INSERT INTO telemetry_raw (device_id, boot_id, seq, topic, "
                    "schema_version, backend_received_at, raw_payload, payload_sha256, "
                    "ingest_status, run_id, created_at) "
                    "VALUES (:d, 'boot-bad', 1, :topic, 1, :now, :payload, 'sha', "
                    "'RECEIVED_VALID', :run, :now) RETURNING id"
                ),
                {
                    "d": device,
                    "topic": f"coldguard/{device}/telemetry",
                    "now": datetime.now(timezone.utc),
                    "payload": '{"calibration_id": "CAL-01"}',
                    "run": f"RUN-{device}",
                },
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO telemetry (time, device_id, boot_id, seq, run_id, "
                    "door_state, applied_cooling, thermal_quality, environment_quality, "
                    "electrical_quality, overall_quality, hardware_config_id, "
                    "firmware_version, schema_version, backend_received_at, raw_id, "
                    "twin_eligible, calibration_id) "
                    "VALUES (:now, :d, 'boot-bad', 1, :run, 'CLOSED', 'OFF', 'VALID', "
                    "'VALID', 'VALID', 'VALID', 'HW-1', '0.1.0', 1, :now, :raw, false, "
                    "'CAL-01')"
                ),
                {
                    "d": device,
                    "now": datetime.now(timezone.utc),
                    "run": f"RUN-{device}",
                    "raw": raw_id,
                },
            )
        report = reconcile_telemetry(db_engine, device_id=device)
        assert report.winner_integrity.invalid_payload_count == 1
        assert report.is_reconciled is False
    finally:
        _cleanup(db_engine, device)


def test_reconcile_detects_normalization_failure(db_engine):
    device = _device()
    try:
        # Admitted valid raw, but normalization never happened (post-boundary).
        store_raw(
            db_engine,
            topic=f"coldguard/{device}/telemetry",
            payload=json.dumps(_payload(device, 1)).encode(),
        )
        report = reconcile_telemetry(db_engine, device_id=device)
        assert report.normalization_failures == 1
        assert report.historical_raw_unnormalized == 0
        assert report.historical_unverified == 0
        assert report.is_reconciled is False
    finally:
        _cleanup(db_engine, device)


def test_reconcile_failure_before_later_success_is_not_historical(db_engine):
    """Regression: raw.id < min(normalized.raw_id) must not hide a failure."""
    device = _device()
    try:
        # seq=1 admitted valid but never normalized (a real failure) ...
        store_raw(
            db_engine,
            topic=f"coldguard/{device}/telemetry",
            payload=json.dumps(_payload(device, 1)).encode(),
        )
        # ... then seq=2 normalizes successfully (higher raw id).
        result = _ingest(db_engine, device, 2)
        assert result["normalized"]["outcome"] == "inserted"
        report = reconcile_telemetry(db_engine, device_id=device)
        assert report.normalization_failures == 1
        assert report.historical_raw_unnormalized == 0
        assert report.historical_unverified == 0
        assert report.is_reconciled is False
    finally:
        _cleanup(db_engine, device)


def test_reconcile_pre_boundary_unaudited_fails_closed(db_engine):
    device = _device()
    try:
        store_raw(
            db_engine,
            topic=f"coldguard/{device}/telemetry",
            payload=json.dumps(_payload(device, 1)).encode(),
            received_at=OLD,
        )
        report = reconcile_telemetry(db_engine, device_id=device)
        assert report.historical_unverified == 1
        assert report.historical_raw_unnormalized == 0
        assert report.normalization_failures == 0
        assert report.is_reconciled is False
    finally:
        _cleanup(db_engine, device)


def test_reconcile_confirmed_historical_passes(db_engine):
    device = _device()
    try:
        stored = store_raw(
            db_engine,
            topic=f"coldguard/{device}/telemetry",
            payload=json.dumps(_payload(device, 1)).encode(),
            received_at=OLD,
        )
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO reconciliation_legacy_audit "
                    "(raw_id, verdict, basis, audited_by) "
                    "VALUES (:raw, 'CONFIRMED_HISTORICAL', :basis, 'test-operator')"
                ),
                {"raw": stored["id"], "basis": "pre-normalization W02 evidence audit"},
            )
        report = reconcile_telemetry(db_engine, device_id=device)
        assert report.historical_raw_unnormalized == 1
        assert report.historical_unverified == 0
        assert report.is_reconciled is True
    finally:
        _cleanup(db_engine, device)


def test_reconcile_exact_duplicate(db_engine):
    device = _device()
    try:
        payload = json.dumps(_payload(device, 1)).encode()
        topic = f"coldguard/{device}/telemetry"
        first = ingest_message(db_engine, topic=topic, payload=payload)
        second = ingest_message(db_engine, topic=topic, payload=payload)
        assert first["normalized"]["outcome"] == "inserted"
        assert second["normalized"]["outcome"] == "exact_duplicate"
        report = reconcile_telemetry(db_engine, device_id=device)
        assert report.raw_total == 2
        assert report.normalized_total == 1
        assert report.exact_duplicates == 1
        assert report.unique_normalized_deliveries == 1
        assert report.is_reconciled is True
    finally:
        _cleanup(db_engine, device)


def test_reconcile_cross_run_collision(db_engine):
    device = _device()
    try:
        run_a = f"RUN-A-{device}"
        run_b = f"RUN-B-{device}"
        boot = f"boot-{device}"
        _ingest(db_engine, device, 1, run_id=run_a, boot_id=boot)
        # Same identity admitted under another run; never normalized.
        store_raw(
            db_engine,
            topic=f"coldguard/{device}/telemetry",
            payload=json.dumps(_payload(device, 1, run_id=run_b, boot_id=boot)).encode(),
        )
        report = reconcile_telemetry(db_engine, device_id=device, run_id=run_b)
        assert report.conflicting_duplicates == 1
        assert report.provenance.cross_run_collision_count == 1
        assert report.normalization_failures == 0
        assert report.is_reconciled is True
    finally:
        _cleanup(db_engine, device)


def test_reconcile_provenance_mismatch_fails(db_engine):
    device = _device()
    try:
        result = _ingest(db_engine, device, 1)
        raw_id = result["raw_id"]
        # Point a normalized row at a raw row whose seq disagrees.
        with db_engine.begin() as conn:
            other_raw = conn.execute(
                text(
                    "INSERT INTO telemetry_raw (device_id, boot_id, seq, topic, "
                    "schema_version, backend_received_at, raw_payload, payload_sha256, "
                    "ingest_status, run_id, created_at) "
                    "VALUES (:d, :boot, 777, :topic, 1, :now, :payload, 'sha', "
                    "'RECEIVED_VALID', :run, :now) RETURNING id"
                ),
                {
                    "d": device,
                    "boot": f"boot-{device}",
                    "topic": f"coldguard/{device}/telemetry",
                    "now": datetime.now(timezone.utc),
                    "payload": json.dumps(_payload(device, 777)),
                    "run": f"RUN-{device}",
                },
            ).scalar_one()
            conn.execute(
                telemetry.update()
                .where(telemetry.c.raw_id == raw_id)
                .values(raw_id=other_raw)
            )
        report = reconcile_telemetry(db_engine, device_id=device)
        assert report.provenance.provenance_mismatch_count >= 1
        assert report.is_reconciled is False
    finally:
        _cleanup(db_engine, device)


def test_reconcile_bounded_volume_across_batches(db_engine):
    """Bounded stress: more rows than the batch size reconcile correctly."""
    device = _device()
    count = 1200
    try:
        with db_engine.begin() as conn:
            for seq in range(1, count + 1):
                ingest_message(
                    conn,
                    topic=f"coldguard/{device}/telemetry",
                    payload=json.dumps(_payload(device, seq)).encode(),
                )
        report = reconcile_telemetry(db_engine, device_id=device, batch_size=100)
        assert report.raw_total == count
        assert report.normalized_total == count
        assert report.unique_normalized_deliveries == count
        assert report.discrepancy == 0
        assert report.winner_integrity.total == 0
        assert report.is_reconciled is True
    finally:
        _cleanup(db_engine, device)