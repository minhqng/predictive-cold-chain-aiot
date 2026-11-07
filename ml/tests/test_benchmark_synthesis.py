"""W12 grouped synthesis: fail-closed inputs and honest statistical units."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

from coldguard_ml.benchmark_synthesis import (
    SynthesisError,
    W11Bundle,
    load_w11_bundle,
    synthesize_grouped_metrics,
)
from coldguard_ml.feature_registry import load_registry
from coldguard_ml.xgb_benchmark import load_benchmark_config

ML_ROOT = Path(__file__).resolve().parents[1]
W11 = ML_ROOT / "reports" / "W11"
REGISTRY = ML_ROOT / "feature-registry-v1.yaml"
CONFIG = ML_ROOT / "xgb-v1-config.yaml"


@pytest.fixture(scope="module")
def bundle() -> W11Bundle:
    return load_w11_bundle(
        W11, registry_path=REGISTRY, config_path=CONFIG
    )


def _load(path: Path) -> W11Bundle:
    return load_w11_bundle(path, registry_path=REGISTRY, config_path=CONFIG)


def _copy_bundle(tmp_path: Path) -> Path:
    destination = tmp_path / "W11"
    shutil.copytree(W11, destination)
    return destination


def _rewrite_artifact_hash(root: Path, name: str) -> None:
    manifest_path = root / "benchmark-manifest-W11.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][name]["sha256"] = hashlib.sha256(
        (root / name).read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _fake_bundle(bundle: W11Bundle, comparison_rows) -> W11Bundle:
    fold_ids = sorted({row["fold_id"] for row in comparison_rows})
    fold_manifest = copy.deepcopy(dict(bundle.fold_manifest))
    fold_manifest["folds"] = [
        fold
        for fold in fold_manifest["folds"]
        if str(fold["fold_id"]) in fold_ids
    ]
    fold_rows = tuple(
        row for row in bundle.fold_rows if row["fold_id"] in fold_ids
    )
    return dataclasses.replace(
        bundle,
        fold_manifest=fold_manifest,
        fold_rows=fold_rows,
        comparison_rows=tuple(comparison_rows),
    )


def test_bundle_verifies_every_manifest_artifact_and_identity(bundle):
    assert len(bundle.artifacts) == 7
    assert all(item.verified for item in bundle.artifacts)
    assert bundle.manifest["registry_sha256"] == bundle.registry.schema_sha256
    assert bundle.manifest["config"]["config_sha256"] == bundle.config.config_sha256
    assert bundle.manifest_file_sha256


def test_missing_artifact_fails_closed(tmp_path):
    root = _copy_bundle(tmp_path)
    (root / "fold-metrics-W11.csv").unlink()
    with pytest.raises(SynthesisError, match="missing"):
        _load(root)


def test_artifact_hash_mismatch_fails_closed(tmp_path):
    root = _copy_bundle(tmp_path)
    row = root / "baseline-comparison-W11.csv"
    row.write_text(row.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(SynthesisError, match="hash mismatch"):
        _load(root)


def test_registry_hash_mismatch_fails_closed(tmp_path, bundle):
    root = _copy_bundle(tmp_path)
    manifest_path = root / "benchmark-manifest-W11.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["registry_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SynthesisError, match="registry SHA"):
        _load(root)


def test_config_hash_mismatch_fails_closed(tmp_path):
    root = _copy_bundle(tmp_path)
    manifest_path = root / "benchmark-manifest-W11.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["config"]["config_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SynthesisError, match="model-config SHA"):
        _load(root)


def test_locked_test_use_is_rejected(tmp_path):
    root = _copy_bundle(tmp_path)
    fold_path = root / "cv-fold-manifest.yaml"
    fold = yaml.safe_load(fold_path.read_text(encoding="utf-8"))
    fold["test_partition_used"] = True
    fold_path.write_text(yaml.safe_dump(fold), encoding="utf-8")
    _rewrite_artifact_hash(root, "cv-fold-manifest.yaml")
    with pytest.raises(SynthesisError, match="locked-test"):
        _load(root)


def test_locked_test_run_in_training_is_rejected(tmp_path):
    root = _copy_bundle(tmp_path)
    fold_path = root / "cv-fold-manifest.yaml"
    fold = yaml.safe_load(fold_path.read_text(encoding="utf-8"))
    locked_run = fold["test_runs"][0]
    fold["folds"][0]["train_run_ids"].append(locked_run)
    fold_path.write_text(yaml.safe_dump(fold), encoding="utf-8")
    _rewrite_artifact_hash(root, "cv-fold-manifest.yaml")
    csv_path = root / "fold-metrics-W11.csv"
    import csv

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    for row in rows:
        if row["fold_id"] == "F1":
            row["train_run_ids"] = row["train_run_ids"] + ";" + locked_run
    buffer = __import__("io").StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=list(rows[0].keys()), lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    csv_path.write_text(buffer.getvalue(), encoding="utf-8")
    _rewrite_artifact_hash(root, "fold-metrics-W11.csv")
    with pytest.raises(SynthesisError, match="locked-test run in training"):
        _load(root)


def test_baseline_validation_run_mismatch_is_rejected(tmp_path):
    root = _copy_bundle(tmp_path)
    csv_path = root / "baseline-comparison-W11.csv"
    import csv

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    for row in rows:
        if row["method"] == "B0_THRESHOLD" and row["fold_id"] == "F1":
            row["validation_run_ids"] = "BOGUS-RUN"
    buffer = __import__("io").StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_path.write_text(buffer.getvalue(), encoding="utf-8")
    _rewrite_artifact_hash(root, "baseline-comparison-W11.csv")
    with pytest.raises(SynthesisError, match="validation runs disagree"):
        _load(root)


def test_baseline_trusted_exposure_mismatch_is_rejected(tmp_path):
    root = _copy_bundle(tmp_path)
    csv_path = root / "baseline-comparison-W11.csv"
    import csv

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    for row in rows:
        if row["method"] == "B0_THRESHOLD" and row["fold_id"] == "F1":
            row["trusted_exposure_s"] = "60"
    buffer = __import__("io").StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_path.write_text(buffer.getvalue(), encoding="utf-8")
    _rewrite_artifact_hash(root, "baseline-comparison-W11.csv")
    with pytest.raises(SynthesisError, match="trusted exposure differs"):
        _load(root)


def test_episode_arithmetic_is_rejected(tmp_path):
    root = _copy_bundle(tmp_path)
    csv_path = root / "baseline-comparison-W11.csv"
    import csv

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    for row in rows:
        if row["method"] == "B0_THRESHOLD" and row["fold_id"] == "F1":
            row["warning_episode_count"] = "99"
    buffer = __import__("io").StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_path.write_text(buffer.getvalue(), encoding="utf-8")
    _rewrite_artifact_hash(root, "baseline-comparison-W11.csv")
    with pytest.raises(SynthesisError, match="episode count"):
        _load(root)


def test_duplicate_validation_run_across_folds_is_rejected(tmp_path):
    root = _copy_bundle(tmp_path)
    fold_path = root / "cv-fold-manifest.yaml"
    fold = yaml.safe_load(fold_path.read_text(encoding="utf-8"))
    duplicated = fold["folds"][0]["validation_run_ids"][0]
    fold["folds"][1]["validation_run_ids"].append(duplicated)
    fold_path.write_text(yaml.safe_dump(fold), encoding="utf-8")
    _rewrite_artifact_hash(root, "cv-fold-manifest.yaml")
    with pytest.raises(SynthesisError, match="validation run"):
        _load(root)


def test_duplicate_fold_row_is_rejected(tmp_path):
    root = _copy_bundle(tmp_path)
    csv_path = root / "fold-metrics-W11.csv"
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    csv_path.write_text(
        "\n".join(lines + [lines[1]]) + "\n", encoding="utf-8"
    )
    _rewrite_artifact_hash(root, "fold-metrics-W11.csv")
    with pytest.raises(SynthesisError, match="duplicate fold/strategy"):
        _load(root)


def test_missing_fold_row_is_rejected(tmp_path):
    root = _copy_bundle(tmp_path)
    csv_path = root / "fold-metrics-W11.csv"
    import csv

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    rows = [
        row
        for row in rows
        if not (row["fold_id"] == "F1" and row["strategy"] == "UNWEIGHTED")
    ]
    buffer = __import__("io").StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_path.write_text(buffer.getvalue(), encoding="utf-8")
    _rewrite_artifact_hash(root, "fold-metrics-W11.csv")
    with pytest.raises(SynthesisError, match="missing"):
        _load(root)


def test_missing_comparison_method_is_rejected(tmp_path):
    root = _copy_bundle(tmp_path)
    csv_path = root / "baseline-comparison-W11.csv"
    import csv

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    rows = [row for row in rows if row["method"] != "B1_HYSTERESIS"]
    buffer = __import__("io").StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_path.write_text(buffer.getvalue(), encoding="utf-8")
    _rewrite_artifact_hash(root, "baseline-comparison-W11.csv")
    with pytest.raises(SynthesisError, match="comparison rows"):
        _load(root)


def test_event_count_mismatch_is_rejected(tmp_path):
    root = _copy_bundle(tmp_path)
    csv_path = root / "baseline-comparison-W11.csv"
    import csv

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    for row in rows:
        if row["method"] == "XGBOOST_V1_UNWEIGHTED" and row["fold_id"] == "F1":
            row["warning_episode_count"] = "99"
    buffer = __import__("io").StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_path.write_text(buffer.getvalue(), encoding="utf-8")
    _rewrite_artifact_hash(root, "baseline-comparison-W11.csv")
    with pytest.raises(SynthesisError, match="episode count"):
        _load(root)


def test_sample_population_mismatch_is_rejected(tmp_path):
    root = _copy_bundle(tmp_path)
    csv_path = root / "baseline-comparison-W11.csv"
    import csv

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    for row in rows:
        if row["method"] == "B0_THRESHOLD" and row["fold_id"] == "F1":
            row["xgb_sample_count"] = "1"
    buffer = __import__("io").StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_path.write_text(buffer.getvalue(), encoding="utf-8")
    _rewrite_artifact_hash(root, "baseline-comparison-W11.csv")
    with pytest.raises(SynthesisError, match="populations differ"):
        _load(root)


def test_grouped_synthesis_reports_groups_runs_windows_separately(bundle):
    synthesis = synthesize_grouped_metrics(bundle)
    population = synthesis.population
    assert population["independent_run_group_count"] == 8
    assert population["individual_run_count"] == 16
    assert population["correlated_feature_window_count"] == 1936
    assert population["grouped_fold_count"] == 4
    assert population["eligible_critical_event_count"] == 8
    for summary in synthesis.method_summaries:
        assert summary.group_count == 8
        assert summary.run_count == 16
        assert summary.eligible_windows_total != summary.group_count
        assert summary.confidence_interval is None
        assert summary.confidence_interval_reason == "CORRELATED_WINDOWS_NOT_INDEPENDENT"


def test_undefined_fold_ap_is_retained_and_not_zeroed(bundle):
    rows = [copy.deepcopy(dict(row)) for row in bundle.comparison_rows]
    target = next(
        row
        for row in rows
        if row["method"] == "XGBOOST_V1_UNWEIGHTED" and row["fold_id"] == "F1"
    )
    target["sample_ap"] = ""
    fake = _fake_bundle(bundle, rows)
    synthesis = synthesize_grouped_metrics(fake)
    summary = next(
        item
        for item in synthesis.method_summaries
        if item.strategy == "UNWEIGHTED"
    )
    assert summary.undefined_folds == 1
    assert summary.fold_values[0][1] is None
    assert summary.mean_ap is not None


def test_mean_ap_is_not_a_pooled_window_metric(bundle):
    rows = [copy.deepcopy(dict(row)) for row in bundle.comparison_rows]
    for row in rows:
        if row["method"] == "XGBOOST_V1_UNWEIGHTED":
            row["sample_ap"] = "1.0" if row["fold_id"] in ("F1", "F2") else "0.0"
    fake = _fake_bundle(bundle, rows)
    synthesis = synthesize_grouped_metrics(fake)
    summary = next(
        item for item in synthesis.method_summaries if item.strategy == "UNWEIGHTED"
    )
    assert summary.mean_ap == pytest.approx(0.5)
    assert summary.min_ap == 0.0
    assert summary.max_ap == 1.0
    assert summary.sample_sd_ap == pytest.approx(
        (sum((value - 0.5) ** 2 for value in (1.0, 1.0, 0.0, 0.0)) / 3) ** 0.5
    )
