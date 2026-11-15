"""W14 provider tests for immutable prediction authority."""

import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import DBAPIError

from coldguard_backend import prediction_store as predictions
from coldguard_backend.command_service import create_command_intent
from coldguard_backend.ingest import ingest_message
from coldguard_backend.simulator import build_telemetry
from coldguard_backend.normalized_store import fetch_by_identity
from coldguard_backend.twin_store import device_twin
from tests.command_testkit import make_command, utcnow
from tests.test_experiments import run_context  # noqa: F401
from tests.test_command_migration import (
    _downgrade, _ensure, _revision, _tables, _upgrade, _url, needs_migration_db,
)
from tests.test_migration_w05 import _cleanup_device
from tests.test_twin import _payload


@pytest.fixture
def prediction_case(db_engine, run_context):
    client, request, other = run_context
    assert client.post("/api/runs", json=request).status_code == 201
    device, run_id = request["device_id"], request["run_id"]
    try:
        yield client, device, run_id, other
    finally:
        with db_engine.begin() as conn:
            ids = select(predictions.predictions.c.prediction_id).where(
                predictions.predictions.c.device_id.in_((device, other)),
            )
            conn.execute(predictions.prediction_inputs.delete().where(
                predictions.prediction_inputs.c.prediction_id.in_(ids),
            ))
            conn.execute(predictions.predictions.delete().where(
                predictions.predictions.c.device_id.in_((device, other)),
            ))


def _sample(engine, device, run, seq, receipt, *, live=False):
    payload = (
        _payload(device, seq, run_id=run) if live
        else build_telemetry(device_id=device, boot_id="prediction-test", seq=seq, run_id=run)
    )
    result = ingest_message(
        engine, topic=f"coldguard/{device}/telemetry", payload=json.dumps(payload).encode(),
        received_at=receipt,
    )
    assert result["normalized"]["outcome"] == "inserted"
    return result["normalized"]["id"]


def _draft(device, run, ids, input_time, **overrides):
    values = {
        "prediction_id": f"software-{uuid4().hex}",
        "device_id": device,
        "run_id": run,
        "model_version": "software-contract-fixture",
        "model_sha256": "1" * 64,
        "feature_version": "software-features",
        "feature_schema_sha256": "2" * 64,
        "risk_score": 0.7,
        "horizon_sec": 120,
        "max_input_age_sec": 60,
        "created_at": utcnow(),
        "input_window_start": input_time - timedelta(seconds=10),
        "input_window_end": input_time,
        "input_telemetry_ids": ids,
        **overrides,
    }
    return predictions.PredictionDraft.model_validate(values)


def test_prediction_provenance_is_idempotent_and_sql_updates_are_refused(db_engine, prediction_case):
    client, device, run_id, _ = prediction_case
    input_at = utcnow()
    older = _sample(db_engine, device, run_id, 1, input_at - timedelta(seconds=1))
    latest = _sample(db_engine, device, run_id, 2, input_at)
    draft = _draft(device, run_id, [latest, older], input_at)
    with db_engine.begin() as conn:
        saved = predictions.record_prediction(conn, draft)
        assert predictions.record_prediction(conn, draft) == saved
        with pytest.raises(predictions.PredictionConflict, match="different provenance"):
            predictions.record_prediction(conn, draft.model_copy(update={"risk_score": 0.1}))
    with pytest.raises(DBAPIError, match="prediction evidence is immutable"):
        with db_engine.begin() as conn:
            conn.execute(predictions.predictions.update().where(
                predictions.predictions.c.prediction_id == draft.prediction_id,
            ).values(risk_score=0.1))
    with pytest.raises(DBAPIError, match="prediction evidence is immutable"):
        with db_engine.begin() as conn:
            conn.execute(predictions.prediction_inputs.update().where(
                predictions.prediction_inputs.c.prediction_id == draft.prediction_id,
            ).values(ordinal=100))
    path = f"/api/devices/{device}/predictions/{draft.prediction_id}"
    detail = client.get(path).json()
    assert detail["input_telemetry_ids"] == [latest, older]
    assert detail["model_sha256"] == draft.model_sha256
    assert detail["feature_schema_sha256"] == draft.feature_schema_sha256
    assert detail["risk_score"] == 0.7


def test_prediction_rejects_foreign_run_device_and_future_window(db_engine, prediction_case):
    _, device, run_id, other = prediction_case
    stamp = utcnow()
    sample = _sample(db_engine, other, run_id, 1, stamp)
    with db_engine.begin() as conn:
        with pytest.raises(predictions.PredictionConflict, match="exact device"):
            predictions.record_prediction(conn, _draft(device, run_id, [sample], stamp))
        with pytest.raises(predictions.PredictionConflict, match="run is unavailable"):
            predictions.record_prediction(conn, _draft(other, run_id, [sample], stamp))
        with pytest.raises(predictions.PredictionConflict, match="future"):
            predictions.record_prediction(conn, _draft(
                device, run_id, [sample], stamp, created_at=stamp + timedelta(hours=1),
            ))
    with pytest.raises(ValueError, match="input window"):
        _draft(device, run_id, [sample], stamp, created_at=stamp - timedelta(seconds=1))


def test_current_prediction_preserves_twin_domains_and_never_refreshes_old_input(db_engine, prediction_case):
    client, device, run_id, other = prediction_case
    path = f"/api/devices/{device}"
    assert client.get(path + "/predictions/current").json() == {"status": "UNAVAILABLE", "prediction": None}
    stamp = utcnow()
    stale_at = stamp - timedelta(minutes=3)
    stale_input = _sample(db_engine, device, run_id, 1, stale_at, live=True)
    live_input = _sample(db_engine, device, run_id, 2, stamp, live=True)
    create_command_intent(db_engine, make_command("prediction-desired", device_id=device, run_id=run_id))
    before = client.get(path + "/state").json()
    stale = _draft(device, run_id, [stale_input], stale_at)
    live = _draft(device, run_id, [live_input], stamp)
    with db_engine.begin() as conn:
        predictions.record_prediction(conn, stale)
    stale_view = client.get(path + "/predictions/current").json()
    assert stale_view["status"] == "STALE"
    assert stale_view["prediction"]["risk_score"] is None
    with db_engine.begin() as conn:
        saved = predictions.record_prediction(conn, live)
        predictions.record_prediction(conn, _draft(device, run_id, [stale_input], stale_at))
        twin = conn.execute(
            select(device_twin).where(device_twin.c.device_id == device),
        ).mappings().one()
    expired = predictions.derived_prediction_view(twin["derived_state"], saved["fresh_until"])
    assert expired["prediction"]["prediction_status"] == "STALE"
    assert expired["prediction"]["risk_score"] is None
    after = client.get(path + "/state").json()
    assert after["reported_state"] == before["reported_state"]
    assert after["desired_state"] == before["desired_state"]
    assert after["derived_state"]["prediction"]["prediction_id"] == live.prediction_id
    assert after["derived_state"]["prediction"]["prediction_status"] == "FRESH"
    assert after["derived_state"]["prediction"]["prediction_age_sec"] >= 0
    history = client.get(path + "/predictions", params={"run_id": run_id, "limit": 2}).json()["items"]
    assert len(history) == 2
    assert {row["prediction_status"] for row in history} == {"STALE", "FRESH"}
    assert client.get(path + "/predictions", params={"limit": 101}).status_code == 422
    assert client.get(path + "/predictions/current", params={"run_id": "unrelated"}).json()["status"] == "UNAVAILABLE"
    assert client.get(f"/api/devices/{other}/predictions/{live.prediction_id}").status_code == 404


@needs_migration_db
def test_prediction_migration_guards_history_and_preserves_telemetry():
    engine = create_engine(_url())
    device = f"prediction-migration-{uuid4().hex}"
    stamp = utcnow()
    try:
        _ensure("0009", engine)
        sample = _sample(engine, device, None, 1, stamp)
        draft = _draft(device, None, [sample], stamp)
        _upgrade("0010")
        assert _revision(engine) == "0010"
        with engine.begin() as conn:
            predictions.record_prediction(conn, draft)
        try:
            with pytest.raises(DBAPIError, match="prediction evidence exists"):
                _downgrade("0009")
            assert _revision(engine) == "0010"
            with engine.connect() as conn:
                assert predictions.prediction_details(conn, device, draft.prediction_id)[
                    "input_telemetry_ids"
                ] == [sample]
        finally:
            with engine.begin() as conn:
                for table in (predictions.prediction_inputs, predictions.predictions):
                    conn.execute(table.delete().where(table.c.prediction_id == draft.prediction_id))
                conn.execute(device_twin.delete().where(device_twin.c.device_id == device))
        _downgrade("0009")
        assert "predictions" not in _tables(engine)
        assert fetch_by_identity(engine, device_id=device, boot_id="prediction-test", seq=1)["id"] == sample
    finally:
        _cleanup_device(engine, device)
        engine.dispose()
