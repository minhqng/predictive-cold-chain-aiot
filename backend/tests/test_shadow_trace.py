"""Exercise shadow inference, existing pure policy and audit without dispatch."""

import json
from datetime import timedelta
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest
from sqlalchemy import select

from coldguard_backend import command_store as commands
from coldguard_backend.inference import InferenceUnavailable, load_frozen_model
from coldguard_backend.ingest import ingest_message
from coldguard_backend.prediction_store import predictions
from coldguard_backend.shadow_trace import OnlineFeatureAdapter, ShadowVerdict, run_shadow, shadow_decisions
from tests.command_testkit import make_command, utcnow
from tests.test_experiments import run_context  # noqa: F401
from tests.test_inference import model_fixture  # noqa: F401
from tests.test_predictions import prediction_case  # noqa: F401
from tests.test_twin import _payload


@pytest.fixture
def shadow_case(prediction_case, db_engine):
    client, device, run_id, _ = prediction_case
    for status in ("ARMED", "RUNNING"):
        assert client.post(f"/api/runs/{run_id}/transitions", json={"status": status}).status_code == 200
    try:
        yield prediction_case
    finally:
        with db_engine.begin() as conn:
            conn.execute(shadow_decisions.delete().where(
                shadow_decisions.c.prediction_id.in_(
                    select(predictions.c.prediction_id).where(predictions.c.run_id == run_id),
                ),
            ))


def _live_sample(engine, device, run_id, seq, receipt, *, replay=False):
    sample = _payload(
        device, seq, run_id=run_id, replay=replay,
        thermal={"t1": 6.0, "t2": 8.0, "t3": 7.0},
    )
    result = ingest_message(
        engine, topic=f"coldguard/{device}/telemetry", received_at=receipt,
        payload=json.dumps(sample).encode(),
    )
    assert result["normalized"]["outcome"] == "inserted"
    return result["normalized"]["id"]


def _software_model(model_fixture):
    artifact, feature_path, spec, loader = model_fixture
    model = load_frozen_model(artifact, feature_path, manifest=spec, approved=spec, loader=loader)
    adapter = OnlineFeatureAdapter(
        spec.feature_version, spec.feature_schema_sha256,
        lambda rows: {"t1": rows[-1]["t1_c"], "t2": rows[-1]["t2_c"]},
    )
    return model, adapter


def _member_d_policy(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "control/src"))
    from coldguard_control.config import PolicyConfig
    from coldguard_control.policy import PolicyInput, PredictionView, RemotePathView, ThermalView, evaluate_policy
    from coldguard_control.types import CoolingState, DeviceMode, ModelHealth, PolicyState, QualityState

    config = PolicyConfig(
        policy_version="software-policy-proof", representative_source="TMAX",
        upper_on_c=9.0, lower_off_c=6.0, thermal_max_age_s=15.0,
        command_max_future_skew_s=5.0, broker_offline_grace_s=30.0,
        backend_state_max_age_s=10.0, safe_local_exit_min_stable_s=60.0,
        predictive_enabled=True, watch_threshold=0.5, preemptive_threshold=0.65,
        persistence_required_s=2.0, prediction_max_age_s=60.0,
    )

    def evaluate(result, rows):
        value = rows[-1]
        return ShadowVerdict.from_policy_decision(evaluate_policy(PolicyInput(
            device_mode=DeviceMode.ONLINE_NORMAL,
            thermal=ThermalView(QualityState.VALID, max(value["t1_c"], value["t2_c"], value["t3_c"]), 1.0),
            applied_cooling=CoolingState.OFF,
            remote=RemotePathView(True, 0.0, True, 1.0, True, True, 120.0, False),
            current_state=PolicyState.NORMAL,
            fan_available=True, electrical_quality=QualityState.VALID, door_state="CLOSED",
            prediction=PredictionView(
                ModelHealth.READY, "synthetic-adapter-fixture", "synthetic-features",
                result["risk_score"], 1.0, 90.0, 3.0,
            ),
        ), config))

    return config.policy_version, evaluate


def test_shadow_trace_persists_exact_features_and_never_publishes(
    db_engine, shadow_case, model_fixture, monkeypatch,
):
    client, device, run_id, other = shadow_case
    model, adapter = _software_model(model_fixture)
    version, policy = _member_d_policy(monkeypatch)
    now = utcnow()
    live_id = _live_sample(db_engine, device, run_id, 1, now - timedelta(seconds=1))
    _live_sample(db_engine, device, run_id, 99, now, replay=True)
    _live_sample(db_engine, other, run_id, 1, now)
    _live_sample(db_engine, device, run_id, 2, now + timedelta(seconds=5))
    emitted = []
    monkeypatch.setattr(mqtt.Client, "publish", lambda *args, **kw: emitted.append((args, kw)))
    args = {
        "run_id": run_id, "decision_id": "w17-shadow", "prediction_id": "w17-prediction<proof>",
        "model": model, "feature_adapter": adapter, "policy_version": version,
        "input_window_start": now - timedelta(seconds=5), "input_window_end": now,
        "created_at": utcnow(), "max_input_age_sec": 30,
    }
    result = run_shadow(db_engine, evaluate_policy=policy, **args)
    assert result["status"] == "EVALUATED"
    assert result["would_command"]["cooling"] == "ON"
    assert not emitted
    assert run_shadow(
        db_engine, evaluate_policy=lambda *_: pytest.fail("retry reevaluated policy"), **args,
    ) == result
    path = f"/api/runs/{run_id}/shadow-trace"
    assert client.get(path).json()["controller_a_commands"] == []
    with db_engine.begin() as conn:
        assert conn.execute(select(commands.commands.c.command_id).where(
            commands.commands.c.run_id == run_id,
        )).first() is None
        for identity, label, controller in (
            (device, "w17-reactive", "REACTIVE"),
            (other, "w17-other-reactive", "REACTIVE"),
            (device, "w17-predictive", "PREDICTIVE"),
        ):
            commands.create_command(conn, make_command(
                label, device_id=identity, run_id=run_id, controller_id=controller,
            ))
    trace = client.get(path, params={"limit": 1}).json()
    item = trace["predictions"][0]
    assert item["input_telemetry_ids"] == [live_id]
    assert item["prediction"]["risk_score"] == 0.7
    shadow = item["shadow_policy"]
    assert shadow["feature_names"] == ["t1", "t2"]
    assert shadow["feature_values"] == [6.0, 8.0]
    assert model.score(dict(zip(shadow["feature_names"], shadow["feature_values"]))) == item["prediction"]["risk_score"]
    assert shadow["evaluated_at"] and shadow["policy_duration_ms"] >= 0
    assert [row["command_id"] for row in trace["controller_a_commands"]] == ["w17-reactive"]
    assert trace["physical_response"]["status"] == "UNAVAILABLE"
    assert client.get(path, params={"limit": 51}).status_code == 422

    audit = client.get(f"/audit/runs/{run_id}/shadow", params={"limit": 1})
    assert audit.status_code == 200
    assert audit.headers["content-type"].startswith("text/html")
    assert "w17-prediction&lt;proof&gt;" in audit.text
    assert "Prediction created" in audit.text
    assert "Policy evaluated" in audit.text
    assert "Policy duration (ms)" in audit.text
    assert item["prediction"]["recorded_at"].replace("Z", "+00:00") in audit.text
    assert shadow["evaluated_at"].replace("Z", "+00:00") in audit.text
    assert "Policy decisions are hypothetical" in audit.text
    assert client.get(f"/audit/runs/{run_id}/shadow", params={"limit": 51}).status_code == 422
    assert not emitted


def test_stale_shadow_records_no_policy_command_and_rejects_unapproved_adapter(
    db_engine, shadow_case, model_fixture,
):
    client, device, run_id, _ = shadow_case
    model, adapter = _software_model(model_fixture)
    old = utcnow() - timedelta(minutes=5)
    _live_sample(db_engine, device, run_id, 1, old)

    def reject_policy(*_):
        pytest.fail("stale output reached policy")

    args = {
        "run_id": run_id, "decision_id": "w17-stale-shadow", "prediction_id": "w17-stale-prediction",
        "model": model, "policy_version": "software-fixture", "evaluate_policy": reject_policy,
        "input_window_start": old - timedelta(seconds=5), "input_window_end": old,
        "created_at": utcnow(), "max_input_age_sec": 30,
    }
    with pytest.raises(InferenceUnavailable, match="not approved"):
        run_shadow(db_engine, feature_adapter=OnlineFeatureAdapter(
            "unapproved", adapter.feature_schema_sha256, adapter.build,
        ), **args)
    result = run_shadow(db_engine, feature_adapter=adapter, **args)
    assert result["status"] == "SKIPPED_STALE"
    assert result["would_command"] is None
    assert result["reason_code"] == "STALE_PREDICTION"
    assert client.get(f"/api/runs/{run_id}/shadow-trace").json()["physical_response"]["status"] == "UNAVAILABLE"
