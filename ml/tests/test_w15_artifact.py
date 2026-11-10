"""W15 model-artifact acceptance matrix (B-W15-04)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import xgboost

from coldguard_ml.feature_registry import load_registry
from coldguard_ml.w14_ablation import build_ablation_dataset
from coldguard_ml.w15_ablation import build_a3_views
from coldguard_ml.w15_artifact import (
    ArtifactError,
    build_model_manifest,
    compute_model_inspection,
    fit_final_candidate,
    load_guarded_artifact,
    native_model_bytes,
    save_native_models,
    verify_fresh_process_parity,
)
from coldguard_ml.xgb_benchmark import (
    build_expanded_w11_fixture,
    feature_matrix,
    load_benchmark_config,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = load_registry(ROOT / "feature-registry-v1.yaml")
CONFIG = load_benchmark_config(ROOT / "xgb-v1-config.yaml", REGISTRY)
FIXTURE = build_expanded_w11_fixture()
VIEWS = build_a3_views(REGISTRY, CONFIG)


@pytest.fixture(scope="module")
def artifact(tmp_path_factory):
    base = tmp_path_factory.mktemp("w15-artifact")
    dataset = build_ablation_dataset(FIXTURE, REGISTRY, CONFIG, VIEWS["A3B"])
    model = fit_final_candidate(
        dataset.samples, CONFIG, VIEWS["A3B"].feature_ids
    )
    probe, _ = feature_matrix(dataset.samples[:5], VIEWS["A3B"].feature_ids)
    files = save_native_models(model, base, probe_matrix=probe)
    fresh = verify_fresh_process_parity(
        model_path=base / "model.ubj",
        probe_matrix=probe,
        expected_scores=model.predict_proba(probe)[:, 1],
    )
    manifest = build_model_manifest(
        files=files,
        registry=REGISTRY,
        config=CONFIG,
        ordered_feature_ids=VIEWS["A3B"].feature_ids,
        training_dataset_id=FIXTURE.dataset_id,
        training_population={
            "run_count": len(dataset.run_ids),
            "sample_count": len(dataset.samples),
            "positive": dataset.positive_count,
            "negative": dataset.negative_count,
            "development_only": True,
            "locked_test_used": False,
        },
        validation_evidence={"protocol": "test", "not_physical_evidence": True},
        training_code_revision="TEST-REVISION",
        probe_parity={**files, **fresh},
        deterministic_in_process=True,
        model_inspection=compute_model_inspection(
            model, VIEWS["A3B"].feature_ids
        ),
    )
    manifest_path = base / "model-manifest-W15.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return {
        "dir": base,
        "model_path": base / "model.ubj",
        "manifest_path": manifest_path,
        "manifest": manifest,
        "probe": probe,
        "dataset": dataset,
    }


def _load(artifact, manifest_path=None):
    return load_guarded_artifact(
        manifest_path=manifest_path or artifact["manifest_path"],
        model_path=artifact["model_path"],
        expected_feature_ids=VIEWS["A3B"].feature_ids,
    )


def _load_paths(artifact, manifest_path, model_path=None, **kwargs):
    return load_guarded_artifact(
        manifest_path=manifest_path,
        model_path=model_path or artifact["model_path"],
        expected_feature_ids=VIEWS["A3B"].feature_ids,
        **kwargs,
    )


def _manifest_variant(artifact, tmp_path, **changes):
    payload = json.loads(json.dumps(artifact["manifest"]))
    payload.update(changes)
    path = tmp_path / "mutated-manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_native_round_trip_and_manifest_binding(artifact):
    guarded = _load(artifact)
    columns = {
        feature_id: artifact["probe"][:, index]
        for index, feature_id in enumerate(guarded.ordered_feature_ids)
    }
    scores = guarded.predict_risk(columns)
    assert scores.shape == (5,)
    assert all(0.0 <= score <= 1.0 for score in scores)
    manifest = artifact["manifest"]
    assert manifest["release_eligibility"] == "NON_DEPLOYABLE_CANDIDATE"
    assert manifest["data_evidence_class"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    assert manifest["score_semantics"] == "risk_score"
    assert manifest["calibration_status"] == "RISK_SCORE_ONLY"
    assert manifest["horizon_status"] == (
        "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN"
    )
    assert manifest["operating_threshold_status"] == "ILLUSTRATIVE_NOT_FROZEN"
    assert manifest["warning_persistence_status"] == "NOT_FROZEN"
    assert manifest["model_library_version"] == xgboost.__version__
    for name in ("ubj", "json"):
        assert (artifact["dir"] / manifest["files"][name]["file"]).exists()


def test_fresh_process_reload_parity_is_exact(artifact):
    guarded = _load(artifact)
    columns = {
        feature_id: artifact["probe"][:, index]
        for index, feature_id in enumerate(guarded.ordered_feature_ids)
    }
    expected = np.asarray(guarded.predict_risk(columns), dtype=float)
    result = verify_fresh_process_parity(
        model_path=artifact["model_path"],
        probe_matrix=artifact["probe"],
        expected_scores=expected,
    )
    assert result["fresh_process_reload_parity"] is True
    assert result["max_abs_diff"] <= 1e-12


def test_wrong_feature_order_is_refused(artifact):
    guarded = _load(artifact)
    columns = {
        feature_id: artifact["probe"][:, index]
        for index, feature_id in enumerate(guarded.ordered_feature_ids)
    }
    reversed_columns = dict(reversed(list(columns.items())))
    with pytest.raises(ArtifactError, match="feature contract mismatch"):
        guarded.predict_risk(reversed_columns)


def test_missing_required_feature_is_refused(artifact):
    guarded = _load(artifact)
    columns = {
        feature_id: artifact["probe"][:, index]
        for index, feature_id in enumerate(guarded.ordered_feature_ids)
    }
    columns.pop(guarded.ordered_feature_ids[-1])
    with pytest.raises(ArtifactError, match="feature contract mismatch"):
        guarded.predict_risk(columns)


def test_unexpected_extra_feature_is_refused(artifact):
    guarded = _load(artifact)
    columns = {
        feature_id: artifact["probe"][:, index]
        for index, feature_id in enumerate(guarded.ordered_feature_ids)
    }
    columns["unexpected_extra"] = np.zeros(artifact["probe"].shape[0])
    with pytest.raises(ArtifactError, match="feature contract mismatch"):
        guarded.predict_risk(columns)


def test_corrupted_model_bytes_are_refused(artifact, tmp_path):
    corrupted = tmp_path / "model.ubj"
    corrupted.write_bytes(b"not an xgboost model")
    import hashlib

    payload = json.loads(json.dumps(artifact["manifest"]))
    corrupted_sha = hashlib.sha256(corrupted.read_bytes()).hexdigest()
    payload["files"]["ubj"]["sha256"] = corrupted_sha
    payload["files"]["ubj"]["bytes"] = corrupted.stat().st_size
    payload["model_artifact_sha256"] = corrupted_sha
    manifest_path = tmp_path / "corrupted-manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ArtifactError, match="cannot be loaded"):
        _load_paths(artifact, manifest_path, model_path=corrupted)


def test_byte_hash_mismatch_is_refused(artifact, tmp_path):
    other = tmp_path / "model.ubj"
    other.write_bytes(artifact["model_path"].read_bytes() + b"tamper")
    with pytest.raises(ArtifactError, match="byte hash"):
        _load_paths(
            artifact, artifact["manifest_path"], model_path=other
        )


def test_feature_schema_hash_mismatch_is_refused(artifact):
    with pytest.raises(ArtifactError, match="feature schema hash"):
        _load_paths(
            artifact,
            artifact["manifest_path"],
            expected_feature_schema_hash="deadbeef",
        )


def test_configuration_hash_mismatch_is_refused(artifact):
    with pytest.raises(ArtifactError, match="configuration hash"):
        _load_paths(
            artifact,
            artifact["manifest_path"],
            expected_model_config_hash="deadbeef",
        )


def test_library_version_mismatch_is_refused(artifact):
    with pytest.raises(ArtifactError, match="library version"):
        _load_paths(
            artifact,
            artifact["manifest_path"],
            expected_library_version="0.0.0",
        )


def test_missing_evidence_class_is_refused(artifact, tmp_path):
    payload = json.loads(json.dumps(artifact["manifest"]))
    payload.pop("data_evidence_class")
    path = tmp_path / "missing-evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ArtifactError, match="missing required fields"):
        _load_paths(artifact, path)


def test_physical_evidence_class_is_refused(artifact, tmp_path):
    path = _manifest_variant(
        artifact, tmp_path, data_evidence_class="REAL_PHYSICAL_EVIDENCE"
    )
    with pytest.raises(ArtifactError, match="evidence class"):
        _load_paths(artifact, path)


def test_synthetic_model_marked_release_approved_is_refused(artifact, tmp_path):
    path = _manifest_variant(
        artifact, tmp_path, release_eligibility="APPROVED_RELEASE_MODEL"
    )
    with pytest.raises(ArtifactError, match="NON_DEPLOYABLE"):
        _load_paths(artifact, path)


def test_probability_wording_is_refused(artifact, tmp_path):
    path = _manifest_variant(
        artifact, tmp_path, score_semantics="calibrated_probability"
    )
    with pytest.raises(ArtifactError, match="risk_score"):
        _load_paths(artifact, path)


def test_unfrozen_horizon_recorded_as_final_is_refused(artifact, tmp_path):
    path = _manifest_variant(
        artifact, tmp_path, horizon_status="PRIMARY_HORIZON_FROZEN"
    )
    with pytest.raises(ArtifactError, match="horizon"):
        _load_paths(artifact, path)


def test_ordered_feature_contract_hash_tamper_is_refused(artifact, tmp_path):
    payload = json.loads(json.dumps(artifact["manifest"]))
    payload["ordered_feature_ids"] = list(
        reversed(payload["ordered_feature_ids"])
    )
    path = tmp_path / "reordered-contract.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ArtifactError, match="ordered feature contract hash"):
        _load_paths(artifact, path)


def test_zero_artifact_sha_is_refused(artifact, tmp_path):
    path = _manifest_variant(artifact, tmp_path, model_artifact_sha256="0" * 64)
    with pytest.raises(ArtifactError, match="does not match the primary artifact"):
        _load_paths(artifact, path)


def test_empty_training_revision_is_refused(artifact, tmp_path):
    path = _manifest_variant(artifact, tmp_path, training_code_revision="")
    with pytest.raises(ArtifactError, match="training code revision"):
        _load_paths(artifact, path)


def test_runtime_library_version_is_checked_by_default(artifact, tmp_path):
    path = _manifest_variant(
        artifact, tmp_path, model_library_version="0.0.0"
    )
    with pytest.raises(ArtifactError, match="runtime library version"):
        _load_paths(artifact, path)


def test_guarded_interface_is_required(artifact, tmp_path):
    path = _manifest_variant(
        artifact, tmp_path, guarded_interface_required=False
    )
    with pytest.raises(ArtifactError, match="guarded inference interface"):
        _load_paths(artifact, path)


def test_model_bytes_are_deterministic_for_identical_inputs(artifact):
    dataset = artifact["dataset"]
    second = fit_final_candidate(
        dataset.samples, CONFIG, VIEWS["A3B"].feature_ids
    )
    first = fit_final_candidate(
        dataset.samples, CONFIG, VIEWS["A3B"].feature_ids
    )
    assert native_model_bytes(first) == native_model_bytes(second)


def test_artifact_training_population_excludes_the_locked_test(artifact):
    dataset = artifact["dataset"]
    assert not (set(dataset.run_ids) & set(FIXTURE.split.test_runs))
    assert all(
        sample.partition in ("train", "validation") for sample in dataset.samples
    )
    assert artifact["manifest"]["training_population"]["locked_test_used"] is False
