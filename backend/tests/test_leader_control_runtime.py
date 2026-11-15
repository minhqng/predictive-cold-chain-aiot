"""Leader-owned tests: live prediction-freshness preflight (fail-closed, PC-UTC).

Uses the delivered member fixtures (db_engine, prediction_case, _sample,
record_prediction) so the prediction rows exercised are REAL member-recorded
rows on the disposable QA database. No member file is modified.
"""

import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest

WORKTREE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKTREE / "backend"))

from tests.command_testkit import db_engine, make_command, utcnow  # noqa: E402,F401
from tests.test_experiments import run_context  # noqa: E402,F401
from tests.test_predictions import _sample, prediction_case  # noqa: E402,F401

from backend.integration.leader_control_runtime import (  # type: ignore  # noqa: E402
    PREDICTION_MAX_AGE_S, LeaderControlRuntime,
)

from coldguard_backend.evidence_package import digest  # noqa: E402
from coldguard_backend.prediction_store import PredictionDraft, record_prediction  # noqa: E402


MODEL_SHA = digest(b"leader-runtime-check-model")


def record_fresh_prediction(engine, device_id: str, run_id: str, sample_id: int, *, age_s: float = 0.0) -> str:
    """Record a member-store prediction whose created_at is age_s in the past.

    Member contract: max_input_age_sec <= horizon_sec, and the input window
    must end at or before created_at. The W24 policy limit (600 s) lives in
    the LeaderControlRuntime preflight, which is the quantity under test.
    """
    receipt = utcnow()
    created = receipt - timedelta(seconds=age_s)
    draft = PredictionDraft(
        prediction_id=f"pred-{uuid.uuid4().hex}", device_id=device_id, run_id=run_id,
        model_version="runtime-check-model", model_sha256=MODEL_SHA,
        feature_version="runtime-check-features", feature_schema_sha256=digest(b"feat-schema"),
        risk_score=0.42, horizon_sec=60, max_input_age_sec=60,
        created_at=created,
        input_window_start=created - timedelta(seconds=5), input_window_end=created,
        input_telemetry_ids=[sample_id],
    )
    with engine.begin() as connection:
        saved = record_prediction(connection, draft)
    return saved["prediction_id"]


def runtime(engine) -> tuple[LeaderControlRuntime, list]:
    calls: list = []

    def member_dispatch(command, *, backend_token=None, approval_signature=None):
        calls.append(command.command_id)
        return {"outcome": "MEMBER_LAYER_REACHED", "command_id": command.command_id}

    return LeaderControlRuntime(engine, member_dispatch), calls


def predictive_command(device_id: str, prediction_id: str | None = None) -> object:
    return make_command(
        f"cmd-{uuid.uuid4().hex}", device_id, cooling="OFF", duty=None,
        controller_id="PREDICTIVE", prediction_id=prediction_id,
        run_id="pred-run", policy_version="policy-w24",
    )


def test_610s_prediction_refused_before_any_persistence(prediction_case, db_engine):
    client, device, run_id, _ = prediction_case
    receipt = utcnow()
    sample_id = _sample(db_engine, device, run_id, 1, receipt)
    prediction_id = record_fresh_prediction(db_engine, device, run_id, sample_id)

    rt, calls = runtime(db_engine)
    command = predictive_command(device, prediction_id)
    # The PC system clock is the authority: 610 s after the member recorded
    # the prediction while its own fresh_until view was computed shortly after
    # recording — exactly the observed live defect (age accepted vs limit).
    result = rt.dispatch(command, backend_token=None, now=utcnow() + timedelta(seconds=610))
    assert result["outcome"] == "PREDICTION_FRESHNESS_REFUSED"
    # Member's own fresh_until view still reads FRESH at the real clock, so
    # refusal must come from the Leader PC-clock age check against the W24
    # 600 s policy limit — the exact live defect.
    assert result["verdict"] == "PREDICTION_AGE_EXCEEDS_LIMIT", result
    assert result["detail"]["age_s"] > 600.0
    assert calls == []


def test_prediction_at_exact_limit_passes_and_reaches_member_layer(prediction_case, db_engine):
    client, device, run_id, _ = prediction_case
    created = utcnow() - timedelta(seconds=10)
    # The telemetry input must fall inside the prediction window ending at creation.
    sample_id = _sample(db_engine, device, run_id, 2, created)
    prediction_id = record_fresh_prediction(db_engine, device, run_id, sample_id, age_s=10.0)

    rt, calls = runtime(db_engine)
    command = predictive_command(device, prediction_id)
    result = rt.dispatch(command, backend_token=None, now=utcnow())
    assert result["outcome"] == "MEMBER_LAYER_REACHED", result
    assert calls == [command.command_id]


def test_missing_prediction_refused(prediction_case, db_engine):
    client, device, run_id, other = prediction_case
    rt, calls = runtime(db_engine)
    result = rt.dispatch(predictive_command(other, None), backend_token=None)
    assert result["outcome"] == "PREDICTION_FRESHNESS_REFUSED"
    assert result["verdict"] == "PREDICTION_MISSING"
    assert calls == []


def test_prediction_id_mismatch_refused(prediction_case, db_engine):
    client, device, run_id, _ = prediction_case
    receipt = utcnow()
    sample_id = _sample(db_engine, device, run_id, 3, receipt)
    first = record_fresh_prediction(db_engine, device, run_id, sample_id)
    second = record_fresh_prediction(db_engine, device, run_id, sample_id)
    assert first != second

    rt, calls = runtime(db_engine)
    # A command minted against the superseded prediction must not run.
    result = rt.dispatch(predictive_command(device, first), backend_token=None)
    if result.get("verdict") != "PREDICTION_ID_MISMATCH":  # diagnostic dump
        from coldguard_backend.prediction_store import current_prediction
        with db_engine.connect() as conn:
            proj = current_prediction(conn, device, None)
        print("DIAG_CURRENT:", {k: proj.get(k) for k in ("status",)},
              {k: str(proj["prediction"].get(k)) if proj.get("prediction") else None
               for k in ("prediction_id", "created_at", "latest_input_at", "fresh_until")})
        print("DIAG_RESULT:", result)
    assert result["outcome"] == "PREDICTION_FRESHNESS_REFUSED"
    assert result["verdict"] == "PREDICTION_ID_MISMATCH"
    assert calls == []
    # The current one still computes fine.
    ok = rt.dispatch(predictive_command(device, second), backend_token=None)
    assert ok["outcome"] == "MEMBER_LAYER_REACHED"


def test_nonpredictive_bypasses_prediction_preflight(prediction_case, db_engine):
    client, device, run_id, _ = prediction_case
    rt, calls = runtime(db_engine)
    command = make_command(f"cmd-{uuid.uuid4().hex}", device, cooling="OFF", duty=None)
    result = rt.dispatch(command, backend_token=None)
    assert result["outcome"] == "MEMBER_LAYER_REACHED"
    assert calls == [command.command_id]
