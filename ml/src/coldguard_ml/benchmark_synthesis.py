"""W12 source-aware synthesis of the W11 grouped benchmark (B-W12-01).

This module never retrains, never opens the locked test and never treats
correlated feature windows as independent physical experiments. It fails
closed on any missing or inconsistent source artifact.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .feature_registry import FeatureRegistry, load_registry
from .xgb_benchmark import BenchmarkConfig, load_benchmark_config

W11_MANIFEST_SCHEMA = "coldguard-w11-benchmark-manifest-v1"
W11_FOLD_MANIFEST_SCHEMA = "coldguard-w11-cv-fold-manifest-v1"
W12_SYNTHESIS_SCHEMA = "coldguard-w12-benchmark-synthesis-v1"
SYNTHETIC_PROVENANCE = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
NOT_A_SCIENTIFIC_BENCHMARK = "NOT_A_SCIENTIFIC_GROUPED_BENCHMARK"
CLAIM_SYNTHETIC = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
CLAIM_REAL_NOT_ESTABLISHED = "REAL_BENCHMARK_NOT_ESTABLISHED"
AP_UNIT = "sample_or_window_average_precision"
EVENT_UNIT = "warning_episode_vs_eligible_critical_event"
CI_UNDEFINED_REASON = "CORRELATED_WINDOWS_NOT_INDEPENDENT"

REQUIRED_W11_ARTIFACTS = (
    "baseline-comparison-W11.csv",
    "cv-fold-manifest.yaml",
    "fold-metrics-W11.csv",
    "xgb-v1-report.md",
)
REQUIRED_COMPARISON_COLUMNS = (
    "method",
    "fold_id",
    "validation_run_ids",
    "eligible_sample_count",
    "xgb_sample_count",
    "sample_population_differs",
    "sample_ap",
    "eligible_critical_event_count",
    "warning_episode_count",
    "matched_warning_episodes",
    "unmatched_warnings",
    "missed_critical_events",
    "false_warning_episodes_per_run",
    "false_warning_episodes_per_hour",
    "event_precision",
    "event_recall",
    "trusted_exposure_s",
    "untrusted_exposure_s",
    "coverage_trustworthy",
    "censored_exclusions",
    "untrusted_exclusions",
)
REQUIRED_FOLD_COLUMNS = (
    "fold_id",
    "strategy",
    "status",
    "validation_group_ids",
    "validation_run_ids",
    "train_group_ids",
    "train_run_ids",
    "validation_samples",
    "average_precision",
    "ap_status",
    "warning_episodes",
    "matched_episodes",
    "unmatched_warnings",
    "missed_events",
)


class SynthesisError(ValueError):
    """A W11 source bundle cannot support an honest W12 synthesis."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SynthesisError(f"missing source artifact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SynthesisError(f"invalid JSON source artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise SynthesisError(f"source artifact root must be an object: {path}")
    return payload


def _read_csv(path: Path) -> tuple[dict[str, str], ...]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return tuple(dict(row) for row in reader)
    except FileNotFoundError as exc:
        raise SynthesisError(f"missing source artifact: {path}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SynthesisError(message)


def _finite_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


def _split_list(value: str | None) -> tuple[str, ...]:
    if not value or not value.strip():
        return ()
    return tuple(item.strip() for item in value.split(";") if item.strip())


@dataclass(frozen=True)
class ArtifactCheck:
    name: str
    path: str
    expected_sha256: str | None
    actual_sha256: str
    verified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "verified": self.verified,
        }


@dataclass(frozen=True)
class W11Bundle:
    reports_dir: Path
    manifest: Mapping[str, Any]
    fold_manifest: Mapping[str, Any]
    fold_rows: tuple[dict[str, str], ...]
    comparison_rows: tuple[dict[str, str], ...]
    registry: FeatureRegistry
    config: BenchmarkConfig
    artifacts: tuple[ArtifactCheck, ...]
    registry_file_sha256: str
    config_file_sha256: str
    manifest_file_sha256: str


def load_w11_bundle(
    reports_dir: str | Path,
    *,
    registry_path: str | Path,
    config_path: str | Path,
) -> W11Bundle:
    root = Path(reports_dir)
    manifest_path = root / "benchmark-manifest-W11.json"
    manifest = _read_json(manifest_path)
    _require(
        manifest.get("schema") == W11_MANIFEST_SCHEMA,
        f"W11 manifest schema must be {W11_MANIFEST_SCHEMA}",
    )
    _require(
        manifest.get("deterministic") is True,
        "W11 manifest must declare deterministic replay",
    )
    _require(
        manifest.get("provenance") == SYNTHETIC_PROVENANCE,
        "W11 bundle must be synthetic software-control only",
    )
    _require(
        manifest.get("scientific_status") == SYNTHETIC_PROVENANCE,
        "W11 scientific status must remain synthetic software-control only",
    )
    registry = load_registry(registry_path)
    config = load_benchmark_config(config_path, registry)
    _require(
        manifest.get("registry_sha256") == registry.schema_sha256,
        "W11 manifest feature registry SHA does not match the current registry",
    )
    config_record = manifest.get("config")
    _require(isinstance(config_record, Mapping), "W11 manifest config is missing")
    _require(
        config_record.get("config_sha256") == config.config_sha256,
        "W11 manifest model-config SHA does not match the current config",
    )
    _require(
        config_record.get("feature_allowlist") == list(config.feature_policy.allowlist),
        "W11 manifest feature order does not match the configured allowlist",
    )
    _require(
        manifest.get("feature_ids") == list(config.feature_policy.allowlist),
        "W11 manifest feature order does not match the configured allowlist",
    )
    _require(
        config_record.get("score_semantics") == "risk_score",
        "W11 scores must remain risk_score semantics",
    )
    _require(
        config_record.get("calibration_status") == "NOT_PERFORMED",
        "W12 cannot synthesize a calibration claim that W11 did not perform",
    )

    artifact_checks: list[ArtifactCheck] = []
    expected_artifacts = manifest.get("artifacts")
    _require(
        isinstance(expected_artifacts, Mapping),
        "W11 manifest artifact hash table is missing",
    )
    for name in REQUIRED_W11_ARTIFACTS:
        _require(
            name in expected_artifacts,
            f"W11 manifest is missing required artifact hash {name!r}",
        )
    for name, metadata in expected_artifacts.items():
        path = root / name
        _require(path.exists(), f"W11 artifact listed in manifest is missing: {path}")
        actual = _sha256_bytes(path.read_bytes())
        expected = (
            metadata.get("sha256")
            if isinstance(metadata, Mapping)
            else None
        )
        artifact_checks.append(
            ArtifactCheck(
                name=name,
                path=str(path),
                expected_sha256=expected,
                actual_sha256=actual,
                verified=expected == actual,
            )
        )
        _require(
            expected == actual,
            f"W11 artifact hash mismatch for {name!r}: "
            f"manifest={expected!r} actual={actual!r}",
        )

    fold_manifest_path = root / "cv-fold-manifest.yaml"
    try:
        fold_manifest = yaml.safe_load(fold_manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SynthesisError(f"missing W11 fold manifest: {fold_manifest_path}") from exc
    _require(
        isinstance(fold_manifest, Mapping),
        "W11 fold manifest root must be a mapping",
    )
    _require(
        fold_manifest.get("schema") == W11_FOLD_MANIFEST_SCHEMA,
        f"W11 fold manifest schema must be {W11_FOLD_MANIFEST_SCHEMA}",
    )
    _require(
        fold_manifest.get("feature_registry_sha256") == registry.schema_sha256,
        "W11 fold manifest registry SHA does not match the current registry",
    )
    _require(
        fold_manifest.get("model_config_sha256") == config.config_sha256,
        "W11 fold manifest model-config SHA does not match the current config",
    )
    _require(
        fold_manifest.get("feature_ids") == list(config.feature_policy.allowlist),
        "W11 fold manifest feature order does not match the configured allowlist",
    )
    _require(
        fold_manifest.get("label_identity") == manifest.get("label_identity"),
        "W11 fold manifest label identity does not match the benchmark manifest",
    )
    _require(
        fold_manifest.get("test_partition_used") is False,
        "W11 fold manifest indicates locked-test use",
    )
    _require(
        manifest.get("label_identity")
        == _label_identity(config),
        "W11 label identity does not match the frozen development label config",
    )

    fold_rows = _read_csv(root / "fold-metrics-W11.csv")
    comparison_rows = _read_csv(root / "baseline-comparison-W11.csv")
    _require(fold_rows, "W11 fold metrics CSV is empty")
    _require(comparison_rows, "W11 baseline comparison CSV is empty")
    for row in fold_rows:
        for column in REQUIRED_FOLD_COLUMNS:
            _require(
                column in row,
                f"W11 fold metrics CSV is missing column {column!r}",
            )
    for row in comparison_rows:
        for column in REQUIRED_COMPARISON_COLUMNS:
            _require(
                column in row,
                f"W11 baseline comparison CSV is missing column {column!r}",
            )

    _validate_fold_structure(manifest, fold_manifest, fold_rows, comparison_rows)
    _validate_population(manifest, fold_rows, comparison_rows)
    _validate_event_reconciliation(manifest, fold_rows, comparison_rows)
    _validate_real_refusal(manifest)

    manifest_sha = _sha256_bytes(manifest_path.read_bytes())
    return W11Bundle(
        reports_dir=root,
        manifest=manifest,
        fold_manifest=fold_manifest,
        fold_rows=fold_rows,
        comparison_rows=comparison_rows,
        registry=registry,
        config=config,
        artifacts=tuple(artifact_checks),
        registry_file_sha256=_sha256_bytes(Path(registry_path).read_bytes()),
        config_file_sha256=_sha256_bytes(Path(config_path).read_bytes()),
        manifest_file_sha256=manifest_sha,
    )


def _label_identity(config: BenchmarkConfig) -> dict[str, Any]:
    return dict(config.label.spec().identity_fields)


def _folds_from_manifest(fold_manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    folds = fold_manifest.get("folds")
    _require(isinstance(folds, list) and folds, "W11 fold manifest has no folds")
    result: dict[str, Mapping[str, Any]] = {}
    for fold in folds:
        _require(isinstance(fold, Mapping), "W11 fold entry is not a mapping")
        fold_id = fold.get("fold_id")
        _require(bool(fold_id), "W11 fold entry has no fold_id")
        _require(fold_id not in result, f"duplicate fold id {fold_id!r}")
        result[str(fold_id)] = fold
    return result


def _validate_fold_structure(
    manifest: Mapping[str, Any],
    fold_manifest: Mapping[str, Any],
    fold_rows: Sequence[Mapping[str, str]],
    comparison_rows: Sequence[Mapping[str, str]],
) -> None:
    folds = _folds_from_manifest(fold_manifest)
    strategies = tuple(manifest.get("config", {}).get("imbalance_strategies", ()))
    _require(strategies, "W11 manifest lists no imbalance strategies")
    expected_pairs = {
        (fold_id, strategy) for fold_id in folds for strategy in strategies
    }
    seen_pairs: set[tuple[str, str]] = set()
    for row in fold_rows:
        pair = (row["fold_id"], row["strategy"])
        _require(pair not in seen_pairs, f"duplicate fold/strategy row {pair}")
        seen_pairs.add(pair)
    _require(
        seen_pairs == expected_pairs,
        "W11 fold metrics rows do not match the fold manifest/strategy set: "
        f"missing={sorted(expected_pairs - seen_pairs)} "
        f"extra={sorted(seen_pairs - expected_pairs)}",
    )
    comparison_pairs: set[tuple[str, str]] = set()
    for row in comparison_rows:
        pair = (row["fold_id"], row["method"])
        _require(
            pair not in comparison_pairs,
            f"duplicate comparison fold/method row {pair}",
        )
        comparison_pairs.add(pair)
    expected_comparison = {
        (fold_id, "B0_THRESHOLD") for fold_id in folds
    } | {(fold_id, "B1_HYSTERESIS") for fold_id in folds} | {
        (fold_id, f"XGBOOST_V1_{strategy}")
        for fold_id in folds
        for strategy in strategies
    }
    _require(
        comparison_pairs == expected_comparison,
        "W11 comparison rows do not match the fold manifest/method set: "
        f"missing={sorted(expected_comparison - comparison_pairs)} "
        f"extra={sorted(comparison_pairs - expected_comparison)}",
    )
    # Every development group appears in exactly one validation fold.
    validation_groups: list[str] = []
    validation_runs: list[str] = []
    for fold_id, fold in folds.items():
        rows = [
            row for row in fold_rows if row["fold_id"] == fold_id
        ]
        _require(rows, f"fold {fold_id!r} has no metrics rows")
        for row in rows:
            _require(
                _split_list(row["validation_group_ids"])
                == tuple(fold.get("validation_group_ids", ())),
                f"fold {fold_id!r} validation groups disagree with the manifest",
            )
            _require(
                _split_list(row["validation_run_ids"])
                == tuple(fold.get("validation_run_ids", ())),
                f"fold {fold_id!r} validation runs disagree with the manifest",
            )
            _require(
                _split_list(row["train_group_ids"])
                == tuple(fold.get("train_group_ids", ())),
                f"fold {fold_id!r} training groups disagree with the manifest",
            )
            _require(
                _split_list(row["train_run_ids"])
                == tuple(fold.get("train_run_ids", ())),
                f"fold {fold_id!r} training runs disagree with the manifest",
            )
        validation_groups.extend(fold.get("validation_group_ids", ()))
        validation_runs.extend(fold.get("validation_run_ids", ()))
    _require(
        len(validation_groups) == len(set(validation_groups)),
        "a validation group appears in more than one fold",
    )
    _require(
        len(validation_runs) == len(set(validation_runs)),
        "a validation run appears in more than one fold",
    )
    declared_groups = int(fold_manifest.get("effective_independent_groups", -1))
    _require(
        declared_groups == len(validation_groups),
        "declared independent group count does not reconcile with validation folds",
    )
    test_runs = set(fold_manifest.get("test_runs", ()))
    _require(
        test_runs.isdisjoint(validation_runs),
        "a locked-test run appears in validation folds",
    )
    for fold_id, fold in folds.items():
        _require(
            set(fold.get("train_run_ids", ())).isdisjoint(
                set(fold.get("validation_run_ids", ()))
            ),
            f"fold {fold_id!r} has train/validation run overlap",
        )
        _require(
            set(fold.get("train_group_ids", ())).isdisjoint(
                set(fold.get("validation_group_ids", ()))
            ),
            f"fold {fold_id!r} has train/validation group overlap",
        )


def _validate_population(
    manifest: Mapping[str, Any],
    fold_rows: Sequence[Mapping[str, str]],
    comparison_rows: Sequence[Mapping[str, str]],
) -> None:
    fold_manifest_runs = manifest.get("fold_runs")
    _require(isinstance(fold_manifest_runs, list), "W11 fold_runs record is missing")
    by_pair = {
        (row["fold_id"], row["strategy"]): row for row in fold_manifest_runs
    }
    for row in fold_rows:
        key = (row["fold_id"], row["strategy"])
        _require(key in by_pair, f"fold run record missing for {key}")
        record = by_pair[key]
        _require(
            int(row["validation_samples"]) == int(record["validation_sample_count"]),
            f"{key}: validation sample count does not reconcile",
        )
        _require(
            int(row["validation_positive"]) == int(record["validation_positive"]),
            f"{key}: validation positive count does not reconcile",
        )
        _require(
            int(row["validation_negative"]) == int(record["validation_negative"]),
            f"{key}: validation negative count does not reconcile",
        )
        _require(
            int(row["train_samples"]) == int(record["train_sample_count"]),
            f"{key}: training sample count does not reconcile",
        )
    labeled = manifest.get("labeled_dataset")
    _require(isinstance(labeled, Mapping), "W11 labeled dataset record is missing")
    dataset_samples = int(labeled.get("sample_count", -1))
    _require(dataset_samples > 0, "W11 labeled dataset has no samples")
    _require(
        dataset_samples
        == int(labeled.get("positive_count", -1))
        + int(labeled.get("negative_count", -1)),
        "W11 labeled dataset class counts do not reconcile",
    )
    fold_by_pair = {
        (row["fold_id"], row["strategy"]): row for row in fold_rows
    }
    for row in comparison_rows:
        if row["method"].startswith("XGBOOST_V1_"):
            strategy = row["method"].removeprefix("XGBOOST_V1_")
            fold_row = fold_by_pair.get((row["fold_id"], strategy))
            _require(
                fold_row is not None,
                f"{row['method']}/{row['fold_id']}: no fold metrics row",
            )
            _require(
                int(row["eligible_sample_count"])
                == int(fold_row["validation_samples"]),
                f"{row['method']}/{row['fold_id']}: XGB sample count does not reconcile",
            )
        else:
            _require(
                int(row["eligible_sample_count"]) == int(row["xgb_sample_count"]),
                f"{row['method']}/{row['fold_id']}: baseline and XGB populations differ",
            )
            _require(
                _as_bool(row["sample_population_differs"]) is False,
                f"{row['method']}/{row['fold_id']}: sample population mismatch flagged",
            )
        _require(
            int(row["eligible_sample_count"]) <= dataset_samples,
            f"{row['method']}/{row['fold_id']}: fold population exceeds the dataset",
        )


def _validate_event_reconciliation(
    manifest: Mapping[str, Any],
    fold_rows: Sequence[Mapping[str, str]],
    comparison_rows: Sequence[Mapping[str, str]],
) -> None:
    fold_by_pair = {
        (row["fold_id"], row["strategy"]): row for row in fold_rows
    }
    for row in comparison_rows:
        method = row["method"]
        if not method.startswith("XGBOOST_V1_"):
            continue
        strategy = method.removeprefix("XGBOOST_V1_")
        key = (row["fold_id"], strategy)
        _require(key in fold_by_pair, f"XGB comparison row has no fold metrics: {key}")
        fold_row = fold_by_pair[key]
        comparisons = (
            ("warning_episode_count", "warning_episodes"),
            ("matched_warning_episodes", "matched_episodes"),
            ("unmatched_warnings", "unmatched_warnings"),
            ("missed_critical_events", "missed_events"),
            ("event_precision", "event_precision"),
            ("event_recall", "event_recall"),
            ("censored_exclusions", "censored_exclusions"),
            ("untrusted_exclusions", "untrusted_exclusions"),
        )
        for comparison_column, fold_column in comparisons:
            actual = _finite_or_none(row[comparison_column])
            expected = _finite_or_none(fold_row[fold_column])
            _require(
                actual == expected,
                f"{key}: {comparison_column} does not reconcile with fold metrics",
            )
        ap_value = _finite_or_none(row["sample_ap"])
        fold_ap = _finite_or_none(fold_row["average_precision"])
        _require(
            ap_value == fold_ap,
            f"{key}: sample AP does not reconcile with fold metrics",
        )
        _require(
            _finite_or_none(row["trusted_exposure_s"]) is not None,
            f"{key}: trusted exposure is missing from the comparison row",
        )
        _require(
            _finite_or_none(row["untrusted_exposure_s"]) is not None,
            f"{key}: untrusted exposure is missing from the comparison row",
        )
        _require(
            _as_bool(row["coverage_trustworthy"]) is not None,
            f"{key}: coverage trustworthiness is missing",
        )
        validation_runs = _split_list(fold_row["validation_run_ids"])
        excluded = manifest.get("labeled_dataset", {}).get("excluded_by_run", {})
        expected_censored = sum(
            int(excluded.get(run_id, {}).get("CENSORED", 0))
            for run_id in validation_runs
        )
        expected_untrusted = sum(
            int(excluded.get(run_id, {}).get("UNTRUSTED_INFO", 0))
            for run_id in validation_runs
        )
        _require(
            int(row["censored_exclusions"] or 0) == expected_censored,
            f"{key}: censored exclusions do not reconcile with label summaries",
        )
        _require(
            int(row["untrusted_exclusions"] or 0) == expected_untrusted,
            f"{key}: untrusted exclusions do not reconcile with label summaries",
        )
    fold_manifest = manifest.get("cv")
    _require(isinstance(fold_manifest, Mapping), "W11 CV record is missing")
    _require(
        int(fold_manifest.get("n_splits", -1)) == len(
            {row["fold_id"] for row in fold_rows}
        ),
        "W11 CV fold count does not reconcile",
    )


def _validate_real_refusal(manifest: Mapping[str, Any]) -> None:
    real = manifest.get("real_development")
    _require(isinstance(real, Mapping), "W11 real-development refusal is missing")
    _require(
        real.get("REAL_EWT") == "NOT_ESTIMABLE",
        "W11 real EWT must remain NOT_ESTIMABLE",
    )
    _require(
        real.get("REAL_AIW") == "NOT_ESTIMABLE",
        "W11 real AIW must remain NOT_ESTIMABLE",
    )
    _require(
        real.get("REAL_XGBOOST_BENCHMARK") == "NOT_ESTABLISHED",
        "W11 must not claim a real XGBoost benchmark",
    )
    _require(
        real.get("PHYSICAL_GATE_B") in ("RED", "NOT_AVAILABLE"),
        "W11 real development must remain physically blocked",
    )


@dataclass(frozen=True)
class MethodSummary:
    method: str
    strategy: str
    population: str
    provenance: str
    group_count: int
    run_count: int
    fold_count: int
    defined_folds: int
    undefined_folds: int
    fold_values: tuple[tuple[str, float | None], ...]
    mean_ap: float | None
    median_ap: float | None
    min_ap: float | None
    max_ap: float | None
    sample_sd_ap: float | None
    sample_sd_reason: str
    mean_precision: float | None
    mean_recall: float | None
    mean_f1: float | None
    eligible_windows_total: int
    eligible_events_total: int
    warning_episodes_total: int
    matched_episodes_total: int
    unmatched_warnings_total: int
    missed_events_total: int
    event_precision: float | None
    event_recall: float | None
    undefined_metric_reasons: tuple[str, ...]
    confidence_interval: None
    confidence_interval_reason: str
    ap_aggregation: str
    event_aggregation: str
    scientific_claim_status: str

    def to_row(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "strategy": self.strategy,
            "population": self.population,
            "provenance": self.provenance,
            "group_count": self.group_count,
            "run_count": self.run_count,
            "fold_count": self.fold_count,
            "defined_folds": self.defined_folds,
            "undefined_folds": self.undefined_folds,
            "fold_values": ";".join(
                f"{fold_id}={value}" for fold_id, value in self.fold_values
            ),
            "mean_ap": self.mean_ap,
            "median_ap": self.median_ap,
            "min_ap": self.min_ap,
            "max_ap": self.max_ap,
            "sample_sd_ap": self.sample_sd_ap,
            "sample_sd_reason": self.sample_sd_reason,
            "mean_precision": self.mean_precision,
            "mean_recall": self.mean_recall,
            "mean_f1": self.mean_f1,
            "eligible_windows_total": self.eligible_windows_total,
            "eligible_events_total": self.eligible_events_total,
            "warning_episodes_total": self.warning_episodes_total,
            "matched_episodes_total": self.matched_episodes_total,
            "unmatched_warnings_total": self.unmatched_warnings_total,
            "missed_events_total": self.missed_events_total,
            "event_precision": self.event_precision,
            "event_recall": self.event_recall,
            "undefined_metric_reasons": ";".join(self.undefined_metric_reasons),
            "confidence_interval": "NOT_COMPUTED",
            "confidence_interval_reason": self.confidence_interval_reason,
            "ap_aggregation": self.ap_aggregation,
            "event_aggregation": self.event_aggregation,
            "scientific_claim_status": self.scientific_claim_status,
        }


@dataclass(frozen=True)
class GroupedSynthesis:
    schema: str
    population: Mapping[str, Any]
    method_summaries: tuple[MethodSummary, ...]
    source_identities: Mapping[str, Any]
    checks: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "population": dict(self.population),
            "method_summaries": [item.to_row() for item in self.method_summaries],
            "source_identities": dict(self.source_identities),
            "checks": list(self.checks),
            "limitations": list(self.limitations),
        }


def _numeric_column(row: Mapping[str, str], name: str) -> float | None:
    return _finite_or_none(row.get(name))


def _method_key(method: str) -> tuple[str, str]:
    if method.startswith("XGBOOST_V1_"):
        return "XGBoost v1", method.removeprefix("XGBOOST_V1_")
    if method == "B0_THRESHOLD":
        return "B0 threshold", "REACTIVE_THRESHOLD"
    if method == "B1_HYSTERESIS":
        return "B1 hysteresis", "REACTIVE_HYSTERESIS"
    return method, "UNKNOWN"


def synthesize_grouped_metrics(bundle: W11Bundle) -> GroupedSynthesis:
    fold_manifest = bundle.fold_manifest
    folds = _folds_from_manifest(fold_manifest)
    group_ids = sorted(
        {
            str(group)
            for fold in folds.values()
            for group in fold.get("validation_group_ids", ())
        }
    )
    run_ids = sorted(
        {
            str(run)
            for fold in folds.values()
            for run in fold.get("validation_run_ids", ())
        }
    )
    methods = sorted({row["method"] for row in bundle.comparison_rows})
    event_counts_by_fold: dict[str, set[int]] = {}
    for row in bundle.comparison_rows:
        event_counts_by_fold.setdefault(row["fold_id"], set()).add(
            int(row["eligible_critical_event_count"] or 0)
        )
    for fold_id, counts in event_counts_by_fold.items():
        _require(
            len(counts) == 1,
            f"fold {fold_id!r}: methods disagree on the eligible event denominator",
        )
    summaries: list[MethodSummary] = []
    for method in methods:
        rows = sorted(
            (row for row in bundle.comparison_rows if row["method"] == method),
            key=lambda row: row["fold_id"],
        )
        _require(rows, f"method {method!r} has no comparison rows")
        fold_values = tuple(
            (row["fold_id"], _numeric_column(row, "sample_ap")) for row in rows
        )
        defined = [value for _, value in fold_values if value is not None]
        undefined_folds = len(fold_values) - len(defined)
        mean_ap = sum(defined) / len(defined) if defined else None
        median_ap = statistics.median(defined) if defined else None
        min_ap = min(defined) if defined else None
        max_ap = max(defined) if defined else None
        sample_sd = (
            statistics.stdev(defined)
            if len(defined) >= 2
            else None
        )
        precision_values = [
            value
            for value in (
                _numeric_column(row, "sample_precision") for row in rows
            )
            if value is not None
        ]
        recall_values = [
            value
            for value in (
                _numeric_column(row, "sample_recall") for row in rows
            )
            if value is not None
        ]
        f1_values = [
            value
            for value in (_numeric_column(row, "sample_f1") for row in rows)
            if value is not None
        ]
        sd_reason = (
            ""
            if sample_sd is not None
            else "INSUFFICIENT_DEFINED_FOLDS"
        )
        reasons: list[str] = []
        if undefined_folds:
            reasons.append("UNDEFINED_FOLD_VALUES_RETAINED")
        if any(_as_bool(row["coverage_trustworthy"]) is False for row in rows):
            reasons.append("FALSE_WARNING_BURDEN_INCOMPLETE_COVERAGE")
        eligible_windows = sum(
            int(row["eligible_sample_count"]) for row in rows
        )
        eligible_events = sum(
            int(row["eligible_critical_event_count"] or 0) for row in rows
        )
        warning_episodes = sum(
            int(row["warning_episode_count"] or 0) for row in rows
        )
        matched = sum(
            int(row["matched_warning_episodes"] or 0) for row in rows
        )
        unmatched = sum(int(row["unmatched_warnings"] or 0) for row in rows)
        missed = sum(int(row["missed_critical_events"] or 0) for row in rows)
        event_precision = (
            matched / warning_episodes if warning_episodes else None
        )
        event_recall = matched / eligible_events if eligible_events else None
        if event_precision is None:
            reasons.append("NO_WARNING_EPISODE_DENOMINATOR")
        if event_recall is None:
            reasons.append("NO_ELIGIBLE_CRITICAL_EVENT_DENOMINATOR")
        display_name, strategy = _method_key(method)
        summaries.append(
            MethodSummary(
                method=display_name,
                strategy=strategy,
                population="synthetic development windows (not physical runs)",
                provenance=CLAIM_SYNTHETIC,
                group_count=len(group_ids),
                run_count=len(run_ids),
                fold_count=len(folds),
                defined_folds=len(defined),
                undefined_folds=undefined_folds,
                fold_values=fold_values,
                mean_ap=mean_ap,
                median_ap=median_ap,
                min_ap=min_ap,
                max_ap=max_ap,
                sample_sd_ap=sample_sd,
                sample_sd_reason=sd_reason,
                mean_precision=(
                    sum(precision_values) / len(precision_values)
                    if precision_values
                    else None
                ),
                mean_recall=(
                    sum(recall_values) / len(recall_values)
                    if recall_values
                    else None
                ),
                mean_f1=(
                    sum(f1_values) / len(f1_values) if f1_values else None
                ),
                eligible_windows_total=eligible_windows,
                eligible_events_total=eligible_events,
                warning_episodes_total=warning_episodes,
                matched_episodes_total=matched,
                unmatched_warnings_total=unmatched,
                missed_events_total=missed,
                event_precision=event_precision,
                event_recall=event_recall,
                undefined_metric_reasons=tuple(dict.fromkeys(reasons)),
                confidence_interval=None,
                confidence_interval_reason=CI_UNDEFINED_REASON,
                ap_aggregation="MEAN_OF_DEFINED_FOLD_VALUES",
                event_aggregation=(
                    "POOLED_EVENT_COUNTS_ACROSS_DISJOINT_VALIDATION_GROUPS"
                ),
                scientific_claim_status=CLAIM_SYNTHETIC,
            )
        )
    labeled = bundle.manifest["labeled_dataset"]
    population = {
        "dataset_id": bundle.manifest.get("dataset_id"),
        "dataset_origin": (
            "deterministic synthetic W11 fixture; no physical run enters the "
            "grouped benchmark"
        ),
        "provenance": bundle.manifest.get("provenance"),
        "independent_run_group_count": len(group_ids),
        "individual_run_count": len(run_ids),
        "correlated_feature_window_count": int(labeled.get("sample_count", 0)),
        "positive_window_count": int(labeled.get("positive_count", 0)),
        "negative_window_count": int(labeled.get("negative_count", 0)),
        "eligible_critical_event_count": sum(
            int(row["eligible_critical_event_count"] or 0)
            for row in bundle.comparison_rows
            if row["method"] == methods[0]
        ),
        "warning_episode_count_by_method": {
            method: sum(
                int(row["warning_episode_count"] or 0)
                for row in bundle.comparison_rows
                if row["method"] == method
            )
            for method in methods
        },
        "grouped_fold_count": len(folds),
        "feature_registry_sha256": bundle.manifest.get("registry_sha256"),
        "label_identity": dict(bundle.manifest.get("label_identity", {})),
        "model_config_sha256": bundle.manifest["config"].get("config_sha256"),
        "horizon_s": bundle.manifest.get("label_identity", {}).get("horizon_s"),
        "risk_score_semantics": bundle.manifest["config"].get("score_semantics"),
        "sample_unit": AP_UNIT,
        "event_unit": EVENT_UNIT,
        "real_benchmark_availability": CLAIM_REAL_NOT_ESTABLISHED,
    }
    checks = (
        "artifact SHA-256 matches actual bytes for every manifest-listed W11 artifact",
        "feature registry SHA matches the current registry and model feature order",
        "model-config SHA matches the benchmark manifest and fold manifest",
        "label identity matches the development label config",
        "every validation group appears in exactly one fold",
        "every validation run appears in exactly one fold",
        "train and validation runs/groups are disjoint per fold",
        "locked-test runs are absent from every fold",
        "paired groups are counted once as independent groups",
        "baseline and XGBoost sample populations reconcile",
        "fold event counts reconcile with the event evaluator outputs",
        "synthetic provenance and real-development refusal are retained",
    )
    limitations = (
        "The fixture is deterministic synthetic software control; it does not "
        "approximate real thermal performance.",
        "Eight pair groups and four folds are a software-control population, not "
        "a physical experiment population.",
        "Feature windows are correlated; fold AP values are not independent "
        "samples, so no confidence interval or physical effect size is computed.",
        "Sample/window AP and event-level metrics use different units and are "
        "never pooled into one unlabeled score.",
        "Synthetic AP=1.0 does not show that XGBoost physically outperforms "
        "Controller A or any baseline.",
    )
    source_identities = {
        "w11_reports_dir": str(bundle.reports_dir),
        "w11_manifest_sha256": bundle.manifest_file_sha256,
        "w11_analysis_code_sha256": bundle.manifest.get("analysis_code_sha256"),
        "w11_repository_revision": bundle.manifest.get("repository_revision"),
        "w11_fixture_version": bundle.manifest.get("fixture_version"),
        "feature_registry_file_sha256": bundle.registry_file_sha256,
        "feature_registry_schema_sha256": bundle.registry.schema_sha256,
        "model_config_file_sha256": bundle.config_file_sha256,
        "model_config_canonical_sha256": bundle.config.config_sha256,
    }
    return GroupedSynthesis(
        schema=W12_SYNTHESIS_SCHEMA,
        population=population,
        method_summaries=tuple(summaries),
        source_identities=source_identities,
        checks=checks,
        limitations=limitations,
    )


def grouped_metrics_csv_rows(synthesis: GroupedSynthesis) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for summary in synthesis.method_summaries:
        for fold_id, value in summary.fold_values:
            rows.append(
                {
                    "row_type": "FOLD",
                    "method": summary.method,
                    "strategy": summary.strategy,
                    "fold_id": fold_id,
                    "value": "" if value is None else value,
                    "metric": "sample_AP",
                    "population": summary.population,
                    "provenance": summary.provenance,
                    "group_count": summary.group_count,
                    "run_count": summary.run_count,
                    "fold_count": summary.fold_count,
                    "scientific_claim_status": summary.scientific_claim_status,
                }
            )
        row = summary.to_row()
        row.update(
            {
                "row_type": "SUMMARY",
                "fold_id": "",
                "value": "",
                "metric": "sample_AP",
            }
        )
        rows.append(row)
    return rows
