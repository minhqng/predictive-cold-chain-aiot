"""Software fixture coverage for the approved frozen-artifact boundary."""

import hashlib
from datetime import timedelta

import pytest

from coldguard_backend.inference import (
    FrozenModelSpec, InferenceUnavailable, infer_and_record, load_frozen_model,
)
from coldguard_backend.prediction_store import prediction_details
from tests.command_testkit import utcnow
from tests.test_experiments import run_context  # noqa: F401
from tests.test_predictions import _sample, prediction_case  # noqa: F401


@pytest.fixture
def model_fixture(tmp_path):
    model_bytes = b"SOFTWARE FIXTURE ONLY: no trained model"
    feature_bytes = b'{"fixture":true,"features":["t1","t2"]}'
    model = tmp_path / "software-model.ubj"
    features = tmp_path / "software-features.json"
    model.write_bytes(model_bytes)
    features.write_bytes(feature_bytes)
    spec = FrozenModelSpec(
        model_version="synthetic-adapter-fixture",
        feature_version="synthetic-features",
        artifact_sha256=hashlib.sha256(model_bytes).hexdigest(),
        feature_schema_sha256=hashlib.sha256(feature_bytes).hexdigest(),
        feature_names=("t1", "t2"), horizon_s=90,
    )

    def loader(payload, names):
        assert payload == model_bytes
        assert names == spec.feature_names
        return lambda values: sum(values) / 20

    return model, features, spec, loader


@pytest.mark.parametrize("bad_input", ["artifact_hash", "feature_hash", "feature_version", "model_version"])
def test_frozen_model_rejects_unapproved_artifact_or_manifest(model_fixture, bad_input):
    artifact, features, spec, loader = model_fixture
    manifest = spec
    if bad_input == "artifact_hash":
        artifact.write_bytes(b"incorrect")
    elif bad_input == "feature_hash":
        features.write_bytes(b"incorrect")
    else:
        manifest = spec.model_copy(update={bad_input: "unapproved"})
    with pytest.raises(InferenceUnavailable, match="mismatch|not approved"):
        load_frozen_model(artifact, features, manifest=manifest, approved=spec, loader=loader)


def test_frozen_model_rejects_bad_feature_order_and_values(model_fixture):
    artifact, features, spec, loader = model_fixture
    loaded = load_frozen_model(artifact, features, manifest=spec, approved=spec, loader=loader)
    assert loaded.score({"t1": 6.0, "t2": 8.0}) == 0.7
    for invalid in ({"t2": 8.0, "t1": 6.0}, {"t1": 6.0}, {"t1": float("nan"), "t2": 8.0}):
        with pytest.raises(InferenceUnavailable, match="invalid"):
            loaded.score(invalid)


def test_inference_returns_only_after_durable_provenance(db_engine, prediction_case, model_fixture):
    _, device, run_id, _ = prediction_case
    artifact, features, spec, loader = model_fixture
    loaded = load_frozen_model(artifact, features, manifest=spec, approved=spec, loader=loader)
    receipt = utcnow()
    sample_id = _sample(db_engine, device, run_id, 1, receipt)
    args = {
        "prediction_id": "w15-software-proof",
        "device_id": device, "run_id": run_id,
        "input_ids": [sample_id],
        "input_window_start": receipt - timedelta(seconds=5),
        "input_window_end": receipt,
        "created_at": utcnow(),
        "max_input_age_sec": 30,
    }
    with pytest.raises(InferenceUnavailable):
        infer_and_record(db_engine, loaded, features={"t1": 5.0}, **args)
    with db_engine.connect() as conn:
        assert prediction_details(conn, device, args["prediction_id"]) is None
    result = infer_and_record(db_engine, loaded, features={"t1": 6.0, "t2": 8.0}, **args)
    assert result == {"prediction_id": args["prediction_id"], "status": "FRESH", "risk_score": 0.7}
    with db_engine.connect() as conn:
        persisted = prediction_details(conn, device, args["prediction_id"])
    assert persisted["input_telemetry_ids"] == [sample_id]
    assert persisted["model_sha256"] == spec.artifact_sha256
    assert persisted["feature_version"] == spec.feature_version
    assert infer_and_record(db_engine, loaded, features={"t1": 6.0, "t2": 8.0}, **args) == result
