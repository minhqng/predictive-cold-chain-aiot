"""W11 XGBoost benchmark, imbalance, artifact and admission tests."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from xgboost import XGBClassifier

from coldguard_ml import load_capture
from coldguard_ml.feature_fixtures import build_development_dataset
from coldguard_ml.feature_registry import load_registry
from coldguard_ml.grouped_evaluation import Fold, FoldSupportError, GroupingLeakageError
from coldguard_ml.xgb_benchmark import (
    SYNTHETIC_PROVENANCE,
    ConfigError,
    FeaturePolicy,
    LabeledSample,
    _fit_fold,
    assess_real_admission,
    build_expanded_w11_fixture,
    build_w10_compatibility_fixture,
    feature_matrix,
    load_benchmark_config,
    load_w08_manifest,
    real_development_status,
    run_grouped_benchmark,
)

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
CONFIG_PATH = ML_ROOT / "xgb-v1-config.yaml"
REGISTRY_PATH = ML_ROOT / "feature-registry-v1.yaml"
W08 = ML_ROOT / "reports" / "W08" / "gate-b-manifest-W08.json"
W10 = ML_ROOT / "reports" / "W10" / "feature-manifest-W10.json"
EVIDENCE = REPO_ROOT / "evidence" / "A" / "W09" / "exports" / "CG-S1-H8C-600S.json"
SCRIPT = ML_ROOT / "scripts" / "xgb-benchmark-W11.py"


@pytest.fixture(scope="module")
def registry():
    return load_registry(REGISTRY_PATH)


@pytest.fixture(scope="module")
def config(registry):
    return load_benchmark_config(CONFIG_PATH, registry)


@pytest.fixture(scope="module")
def expanded(registry, config, tmp_path_factory):
    fixture = build_expanded_w11_fixture()
    out = tmp_path_factory.mktemp("w11-expanded")
    result, models = run_grouped_benchmark(fixture, registry, config, out_dir=out)
    return fixture, result, models, out


@pytest.fixture(scope="module")
def smoke(registry, config, tmp_path_factory):
    fixture = build_w10_compatibility_fixture()
    out = tmp_path_factory.mktemp("w11-smoke")
    result, models = run_grouped_benchmark(
        fixture, registry, config, out_dir=out, n_splits_override=2
    )
    return fixture, result, models, out


def _sample(run_id: str, y: int, features=(1.0, 0.0)) -> LabeledSample:
    return LabeledSample(
        run_id=run_id,
        group_id=f"PAIR-{run_id}",
        partition="train",
        source_sha256=f"{run_id}-sha",
        sample_identity=f"{run_id}:0",
        anchor_t_s=0.0,
        features=features,
        y=y,
        series_id="series",
    )


def _fit_inputs(train, validation):
    fold = Fold(
        fold_id="F1",
        train_groups=tuple({sample.group_id for sample in train}),
        validation_groups=tuple({sample.group_id for sample in validation}),
        train_runs=tuple({sample.run_id for sample in train}),
        validation_runs=tuple({sample.run_id for sample in validation}),
        pair_lineage=(),
    )
    return fold


def test_config_allowlist_is_explicit_and_excludes_diagnostic(registry, config):
    assert config.primary_metric == "AVERAGE_PRECISION"
    assert len(config.feature_policy.allowlist) == 28
    assert "T_tec_hot_side_c" in config.feature_policy.excluded_diagnostic_features
    assert "T_tec_hot_side_c" not in config.feature_policy.allowlist
    assert all(registry.feature(item) for item in config.feature_policy.allowlist)
    assert set(config.strategies) == {
        "UNWEIGHTED",
        "TRAIN_FOLD_CLASS_WEIGHT",
    }
    assert config.score_semantics == "risk_score"
    assert config.calibration_status == "NOT_PERFORMED"


def test_identifier_and_label_fields_cannot_enter_x(registry):
    policy = FeaturePolicy(
        allowlist=("critical_event_time_s",),
        excluded_diagnostic_features=(),
        prohibited_fields=("critical_event_time_s",),
    )
    with pytest.raises(ConfigError):
        policy.assert_safe(registry)
    with pytest.raises(ConfigError):
        FeaturePolicy(
            allowlist=("T_tec_hot_side_c",),
            excluded_diagnostic_features=("T_tec_hot_side_c",),
            prohibited_fields=(),
        ).assert_safe(registry)


def test_missing_electrical_is_nan_not_zero():
    sample = _sample("R1", 0, features=(float("nan"), 1.0))
    matrix, labels = feature_matrix([sample], ("electrical", "other"))
    assert matrix.shape == (1, 2)
    assert np.isnan(matrix[0, 0])
    assert matrix[0, 0] != 0
    assert labels.tolist() == [0]


def test_expanded_fixture_and_labels_exclude_locked_test(expanded):
    fixture, result, _, _ = expanded
    test_runs = set(fixture.test_runs)
    assert test_runs
    assert all(run not in test_runs for run in result.labeled.run_ids)
    assert result.split_identity["test_partition_used"] is False
    assert result.cv.effective_groups == 8
    assert result.cv.n_splits == 4
    assert len(result.fold_runs) == 8
    assert {row.strategy for row in result.fold_runs} == {
        "UNWEIGHTED",
        "TRAIN_FOLD_CLASS_WEIGHT",
    }
    for fold in result.cv.folds:
        assert set(fold.train_runs).isdisjoint(fold.validation_runs)
        assert set(fold.train_groups).isdisjoint(fold.validation_groups)
        assert set(fold.train_runs) | set(fold.validation_runs) == set(
            result.labeled.run_ids
        )


def test_b1_sample_metrics_use_the_on_state_threshold(expanded):
    _, result, _, _ = expanded
    rows = [
        row for row in result.baseline_rows if row["method"] == "B1_HYSTERESIS"
    ]
    assert rows
    for row in rows:
        assert row["sample_threshold"] == 1.0
        assert row["sample_comparison"] == "GE"
        assert row["sample_precision"] is not None
        assert row["sample_precision"] > 0.0
        assert row["sample_recall"] is not None
        assert row["sample_recall"] > 0.0
        assert row["sample_undefined_reasons"] == []


def test_baseline_and_xgb_share_the_evaluated_sample_population(expanded):
    _, result, _, _ = expanded
    for row in result.baseline_rows:
        if row["method"] not in ("B0_THRESHOLD", "B1_HYSTERESIS"):
            continue
        assert row["eligible_sample_count"] == row["xgb_sample_count"]
        assert row["sample_population_differs"] is False


def test_all_folds_and_strategies_are_reported(expanded, config):
    _, result, _, _ = expanded
    for strategy in config.strategies:
        rows = [row for row in result.fold_runs if row.strategy == strategy]
        assert len(rows) == result.cv.n_splits
    methods = {row["method"] for row in result.baseline_rows}
    assert "B0_THRESHOLD" in methods
    assert "B1_HYSTERESIS" in methods
    assert any(method.startswith("XGBOOST_V1_") for method in methods)
    for fold in result.cv.folds:
        assert any(row["fold_id"] == fold.fold_id for row in result.baseline_rows)


def test_class_weights_are_train_fold_only(expanded):
    _, result, _, _ = expanded
    unweighted = [row for row in result.fold_runs if row.strategy == "UNWEIGHTED"]
    weighted = [
        row for row in result.fold_runs if row.strategy == "TRAIN_FOLD_CLASS_WEIGHT"
    ]
    for plain, weighted_row in zip(unweighted, weighted):
        assert plain.train_runs == weighted_row.train_runs
        assert plain.validation_runs == weighted_row.validation_runs
        assert plain.scale_pos_weight == 1.0
        expected = weighted_row.train_negative / weighted_row.train_positive
        assert weighted_row.scale_pos_weight == pytest.approx(expected)
        assert weighted_row.weight_formula == (
            "scale_pos_weight = train_negative / train_positive"
        )


def test_single_class_training_fold_refuses_fit(config):
    train = [_sample("R1", 0), _sample("R2", 0)]
    validation = [_sample("R3", 0), _sample("R3B", 1)]
    result, model = _fit_fold(
        fold=_fit_inputs(train, validation),
        strategy="UNWEIGHTED",
        train_samples=train,
        validation_samples=validation,
        config=config,
        feature_ids=("a", "b"),
    )
    assert result.status == "REFUSED"
    assert result.reason == "SINGLE_CLASS_TRAINING_FOLD"
    assert model is None
    assert result.metrics is None


def test_single_class_validation_reports_undefined_ap(config):
    train = [_sample("R1", 0), _sample("R1B", 1), _sample("R2", 0), _sample("R2B", 1)]
    validation = [_sample("R3", 0), _sample("R3B", 0)]
    result, model = _fit_fold(
        fold=_fit_inputs(train, validation),
        strategy="UNWEIGHTED",
        train_samples=train,
        validation_samples=validation,
        config=config,
        feature_ids=("a", "b"),
    )
    assert model is not None
    assert result.status == "FIT"
    assert result.metrics["average_precision"]["value"] is None
    assert result.metrics["average_precision"]["reason"] == (
        "SINGLE_CLASS_VALIDATION_NO_POSITIVES"
    )
    assert result.metrics["roc_auc"]["value"] is None


def test_outputs_are_risk_scores_not_probabilities(config, expanded):
    assert config.score_semantics == "risk_score"
    assert config.calibration_status == "NOT_PERFORMED"
    _, result, _, _ = expanded
    assert result.model_artifact["classification"] == SYNTHETIC_PROVENANCE
    assert "probability" not in json.dumps(result.model_artifact)


def test_oof_metrics_and_fold_instability_are_present(expanded):
    _, result, _, _ = expanded
    for strategy in ("UNWEIGHTED", "TRAIN_FOLD_CLASS_WEIGHT"):
        payload = result.oof[strategy]
        assert payload["status"] == "DEFINED"
        assert payload["metrics"]["average_precision"]["value"] is not None
        assert payload["fold_ap"]["status"] == "DEFINED"
        assert payload["fold_ap"]["instability_range"] >= 0.0


def test_model_artifact_is_synthetic_and_loads(expanded):
    _, result, _, out = expanded
    artifact = result.model_artifact
    assert artifact is not None
    assert artifact["classification"] == SYNTHETIC_PROVENANCE
    assert artifact["promotable_to_physical_model"] is False
    assert artifact["load_predictions_match"] is True
    for entry in artifact["files"].values():
        path = out / entry["file"]
        assert path.exists()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    loaded = XGBClassifier()
    loaded.load_model(str(out / "model-synthetic-smoke.ubj"))
    probe = np.zeros((2, len(result.feature_ids)), dtype=float)
    assert loaded.predict_proba(probe).shape == (2, 2)


def test_w10_compatibility_smoke_is_software_only(smoke):
    fixture, result, _, _ = smoke
    assert result.status == "NOT_A_SCIENTIFIC_GROUPED_BENCHMARK"
    assert result.provenance == "SOFTWARE_ONLY"
    assert result.cv.effective_groups == 2
    assert result.cv.n_splits == 2
    assert set(fixture.test_runs).isdisjoint(set(result.labeled.run_ids))
    assert any("not a credible scientific population" in item for item in result.limitations)


def test_default_fold_count_refuses_the_two_group_fixture(registry, config, tmp_path):
    fixture = build_w10_compatibility_fixture()
    with pytest.raises(FoldSupportError, match="fold count may never exceed"):
        run_grouped_benchmark(fixture, registry, config, out_dir=tmp_path)


def test_real_admission_refuses_current_red_capture(registry, config):
    w08 = load_w08_manifest(W08)
    capture = load_capture(EVIDENCE)
    decision = assess_real_admission(
        w08, capture=capture, capture_sha256=capture.source.sha256
    )
    assert decision.allowed is False
    assert decision.gate == "RED"
    assert decision.admitted_run_ids == ()
    assert "PHYSICAL_GATE_RED" in decision.reasons
    assert "A_LEDGER_NOT_VALID" in decision.reasons
    assert "RUN_IDENTITY_UNRESOLVED" in decision.reasons
    assert "ABSOLUTE_EVENT_TIME_NOT_EVIDENCED" in decision.reasons
    assert "REAL_DEVELOPMENT_SPLIT_NOT_FEASIBLE" in decision.reasons


def test_gate_b_bypass_with_forged_green_manifest_is_refused():
    w08 = load_w08_manifest(W08)
    forged = copy.deepcopy(w08)
    forged["physical_gate"]["observed_status"] = "GREEN"
    forged["physical_gate"]["evidence_sha256"] = ["0" * 64]
    forged["runs"] = []
    decision = assess_real_admission(forged, capture=None, capture_sha256=None)
    assert decision.allowed is False
    assert "SOURCE_HASH_NOT_BOUND_BY_W08" in decision.reasons
    assert "PHYSICAL_GATE_RED" not in decision.reasons


def test_real_status_is_explicitly_not_feasible(registry, config):
    w08 = load_w08_manifest(W08)
    capture = load_capture(EVIDENCE)
    status = real_development_status(
        w08, capture=capture, capture_sha256=capture.source.sha256
    )
    assert status["TRAINING_EXECUTED"] == "NO"
    assert status["BENCHMARK_STATUS"] == "NOT_FEASIBLE"
    assert status["REAL_XGBOOST_BENCHMARK"] == "NOT_ESTABLISHED"
    assert status["REAL_BASELINE_COMPARISON"] == "NOT_ESTABLISHED"
    assert status["REAL_EWT"] == "NOT_ESTIMABLE"
    assert status["REAL_AIW"] == "NOT_ESTIMABLE"
    assert (
        status["REAL_EWT_REASON_CODE"]
        == "EWT_UNAVAILABLE_NO_QUALIFIED_COMMON_TRAJECTORY"
    )
    assert (
        status["REAL_AIW_REASON_CODE"]
        == "AIW_UNAVAILABLE_MEASURED_LATENCY_CHAIN_MISSING"
    )
    assert status["REAL_EWT_REASON_CODE"] != status["REAL_AIW_REASON_CODE"]


def _run_cli(out_dir: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ML_ROOT / "src")
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out_dir),
            "--repository-revision",
            "TEST-REV",
            *args,
        ],
        cwd=ML_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_cli_grouped_artifacts_are_byte_deterministic(tmp_path: Path):
    first = tmp_path / "out"
    left = _run_cli(first, "--mode", "synthetic-grouped-cv")
    assert left.returncode == 0, left.stderr
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in first.iterdir()
    }
    right = _run_cli(first, "--mode", "synthetic-grouped-cv")
    assert right.returncode == 0, right.stderr
    canonical = {
        "xgb-v1-report.md",
        "cv-fold-manifest.yaml",
        "leakage-audit-W11.md",
        "benchmark-manifest-W11.json",
        "fold-metrics-W11.csv",
        "baseline-comparison-W11.csv",
        "model-synthetic-smoke.ubj",
        "model-synthetic-smoke.json",
    }
    assert canonical <= {path.name for path in first.iterdir()}
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in first.iterdir()
    }
    assert before == after
    manifest = json.loads(
        (first / "benchmark-manifest-W11.json").read_text(encoding="utf-8")
    )
    assert manifest["scientific_verdicts"]["W11_SOFTWARE"] == "GREEN"
    assert manifest["scientific_verdicts"]["PHYSICAL_GATE_B"] == "RED"
    assert manifest["scientific_verdicts"]["REAL_XGBOOST_BENCHMARK"] == (
        "NOT_ESTABLISHED"
    )
    assert manifest["verification"]["locked_test_used"] is False
    assert manifest["model_artifact"]["classification"] == SYNTHETIC_PROVENANCE
    report = (first / "xgb-v1-report.md").read_text(encoding="utf-8")
    assert "No synthetic AP is a ColdGuard result" in report
    assert "not physical predictive performance" in report


def test_cli_real_refusal_is_exit_two_and_writes_status(tmp_path: Path):
    out = tmp_path / "real"
    result = _run_cli(out, "--mode", "real-development")
    assert result.returncode == 2
    assert "TRAINING_EXECUTED: NO" in result.stdout
    assert "BENCHMARK_STATUS: NOT_FEASIBLE" in result.stdout
    status = json.loads(
        (out / "real-development-refusal-W11.json").read_text(encoding="utf-8")
    )
    assert status["TRAINING_EXECUTED"] == "NO"
    assert status["BENCHMARK_STATUS"] == "NOT_FEASIBLE"
    assert not (out / "model-synthetic-smoke.ubj").exists()


def test_cli_refuses_w10_manifest_from_a_different_registry(tmp_path: Path):
    payload = json.loads(W10.read_text(encoding="utf-8"))
    payload["registry"]["registry_sha256"] = "0" * 64
    forged = tmp_path / "forged-W10.json"
    forged.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_cli(
        tmp_path / "out",
        "--mode",
        "synthetic-grouped-cv",
        "--w10-manifest",
        str(forged),
    )
    assert result.returncode == 1
    assert "registry identity" in result.stderr
