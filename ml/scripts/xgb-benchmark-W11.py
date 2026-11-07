#!/usr/bin/env python3
"""ColdGuard W11 grouped XGBoost benchmark CLI.

Modes
-----
``synthetic-smoke``
    W10 two-development-group compatibility fixture. The result is a software
    control only and is never a scientific grouped benchmark.

``synthetic-grouped-cv``
    Expanded deterministic W11 synthetic fixture with enough independent
    groups and class support to exercise grouped CV, imbalance strategies,
    W09 baseline comparison and the leakage audit.

``real-development``
    Read the W08 Gate B manifest and the real A capture through the physical
    admission gate. With the current evidence this is a scientific refusal:
    no model is fitted and no real benchmark is established.

Exit codes
----------
* 0 — synthetic software control completed, or an audit-only real refusal was
  written with an explicit blocked status.
* 1 — configuration, manifest or I/O error.
* 2 — the requested real-development benchmark is scientifically refused.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

try:  # installed package
    from coldguard_ml import load_capture
    from coldguard_ml.feature_registry import load_registry
    from coldguard_ml.leakage_audit import LeakageAuditResult, run_leakage_audit
    from coldguard_ml.xgb_benchmark import (
        SYNTHETIC_PROVENANCE,
        BenchmarkConfig,
        BenchmarkFixture,
        BenchmarkResult,
        build_expanded_w11_fixture,
        build_w10_compatibility_fixture,
        load_benchmark_config,
        load_w08_manifest,
        package_versions,
        real_development_status,
        run_grouped_benchmark,
    )
except ModuleNotFoundError:  # direct checkout invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml import load_capture
    from coldguard_ml.feature_registry import load_registry
    from coldguard_ml.leakage_audit import LeakageAuditResult, run_leakage_audit
    from coldguard_ml.xgb_benchmark import (
        SYNTHETIC_PROVENANCE,
        BenchmarkConfig,
        BenchmarkFixture,
        BenchmarkResult,
        build_expanded_w11_fixture,
        build_w10_compatibility_fixture,
        load_benchmark_config,
        load_w08_manifest,
        package_versions,
        real_development_status,
        run_grouped_benchmark,
    )

W11_REPORT_SCHEMA = "coldguard-w11-benchmark-manifest-v1"
W11_LAYER_VERSION = "coldguard-w11-grouped-xgb-benchmark-v1"
PINNED_TEST_RUN_NOTICE = "W10 held-out synthetic test pair remains untouched"
REAL_STATUS_KEYS = (
    "PHYSICAL_GATE_B",
    "ELIGIBLE_RUNS",
    "TRAINING_EXECUTED",
    "BENCHMARK_STATUS",
    "REAL_DEVELOPMENT_SPLIT",
    "REAL_XGBOOST_BENCHMARK",
    "REAL_BASELINE_COMPARISON",
    "REAL_EWT",
    "REAL_AIW",
)


class CliError(RuntimeError):
    pass


def _scientific_verdicts(
    result: BenchmarkResult,
    audit: LeakageAuditResult,
    real_status: Mapping[str, Any],
) -> dict[str, str]:
    probes = {probe.probe_id: probe.status for probe in audit.probes}
    audit_ok = all(probe.status != "FAIL" for probe in audit.probes)
    fits_ok = all(row.status == "FIT" for row in result.fold_runs)
    framework_ok = (
        probes.get("grouped_disjoint") == "PASS"
        and probes.get("pair_preservation") == "PASS"
        and probes.get("locked_test") == "PASS"
    )
    return {
        "W11_SOFTWARE": "GREEN" if audit_ok and fits_ok else "REVIEW_PENDING",
        "SYNTHETIC_TRAINING": "PASSED" if audit_ok and fits_ok else "FAILED",
        "GROUPED_EVALUATION_FRAMEWORK": (
            "VERIFIED_BY_TESTS" if framework_ok else "BLOCKED"
        ),
        "PHYSICAL_GATE_B": real_status["PHYSICAL_GATE_B"],
        "REAL_PREDICTIVE_DATASET": "NOT_READY",
        "REAL_XGBOOST_BENCHMARK": "NOT_ESTABLISHED",
        "REAL_BASELINE_COMPARISON": "NOT_ESTABLISHED",
        "REAL_EWT": "NOT_ESTIMABLE",
        "REAL_AIW": "NOT_ESTIMABLE",
    }


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _git_revision(root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNRECORDED"
    return completed.stdout.strip() or "UNRECORDED"


def _analysis_code_sha256(root: Path) -> str:
    package = root / "src" / "coldguard_ml"
    paths = (
        Path(__file__).resolve(),
        root / "xgb-v1-config.yaml",
        package / "xgb_benchmark.py",
        package / "grouped_evaluation.py",
        package / "leakage_audit.py",
        package / "feature_pipeline.py",
        package / "feature_registry.py",
        package / "labels.py",
        package / "splitting.py",
        package / "baselines.py",
        package / "event_evaluator.py",
        package / "__init__.py",
    )
    hasher = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _load_w10_binding(path: Path, config: BenchmarkConfig, registry_sha: str) -> dict[str, Any]:
    if not path.exists():
        raise CliError(f"W10 manifest not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CliError("W10 manifest root must be a mapping")
    manifest_registry = (payload.get("registry") or {}).get("registry_sha256")
    if manifest_registry != registry_sha:
        raise CliError(
            "W10 manifest registry identity does not match the supplied feature registry"
        )
    split = payload.get("split") or {}
    if split.get("test_partition_used") is not False:
        raise CliError("W10 manifest does not prove the test partition was unused")
    return {
        "path": str(path).replace("\\", "/"),
        "sha256": _sha256_file(path),
        "registry_sha256": manifest_registry,
        "fixture_version": (payload.get("fixture") or {}).get("version"),
        "test_partition_used": False,
    }


def _fold_metrics_csv(result: BenchmarkResult) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "fold_id",
            "strategy",
            "status",
            "reason",
            "train_group_ids",
            "validation_group_ids",
            "train_run_ids",
            "validation_run_ids",
            "train_samples",
            "validation_samples",
            "train_positive",
            "train_negative",
            "validation_positive",
            "validation_negative",
            "scale_pos_weight",
            "weight_formula",
            "average_precision",
            "ap_status",
            "ap_reason",
            "roc_auc",
            "precision",
            "recall",
            "f1",
            "tn",
            "fp",
            "fn",
            "tp",
            "pr_curve_points",
            "warning_episodes",
            "matched_episodes",
            "unmatched_warnings",
            "missed_events",
            "event_precision",
            "event_recall",
            "censored_exclusions",
            "untrusted_exclusions",
        ]
    )
    for row in result.fold_runs:
        metrics = row.metrics or {}
        event = row.event_metrics or {}

        def metric(name: str, field: str = "value") -> Any:
            value = (metrics.get(name) or {}).get(field)
            return "" if value is None else value

        confusion = metrics.get("confusion_matrix") or {}
        writer.writerow(
            [
                row.fold_id,
                row.strategy,
                row.status,
                row.reason or "",
                ";".join(row.train_groups),
                ";".join(row.validation_groups),
                ";".join(row.train_runs),
                ";".join(row.validation_runs),
                row.train_sample_count,
                row.validation_sample_count,
                row.train_positive,
                row.train_negative,
                row.validation_positive,
                row.validation_negative,
                "" if row.scale_pos_weight is None else row.scale_pos_weight,
                row.weight_formula or "",
                metric("average_precision"),
                metric("average_precision", "status"),
                metric("average_precision", "reason"),
                metric("roc_auc"),
                metric("precision"),
                metric("recall"),
                metric("f1"),
                confusion.get("tn", ""),
                confusion.get("fp", ""),
                confusion.get("fn", ""),
                confusion.get("tp", ""),
                metrics.get("pr_curve_points", ""),
                event.get("warning_episode_count", ""),
                event.get("matched_warning_episodes", ""),
                event.get("unmatched_warnings", ""),
                event.get("missed_critical_events", ""),
                event.get("event_precision", ""),
                event.get("event_recall", ""),
                row.censored_exclusions,
                row.untrusted_exclusions,
            ]
        )
    return buffer.getvalue()


def _baseline_comparison_csv(result: BenchmarkResult) -> str:
    buffer = io.StringIO()
    rows = result.baseline_rows
    columns = (
        "method",
        "version",
        "fold_id",
        "run_groups",
        "validation_run_ids",
        "baseline_evaluability",
        "not_evaluable_runs",
        "eligible_sample_count",
        "xgb_sample_count",
        "sample_population_differs",
        "eligible_critical_event_count",
        "warning_episode_count",
        "matched_warning_episodes",
        "unmatched_warnings",
        "missed_critical_events",
        "false_warning_episodes_per_run",
        "false_warning_episodes_per_hour",
        "event_precision",
        "event_recall",
        "sample_threshold",
        "sample_comparison",
        "sample_ap",
        "sample_precision",
        "sample_recall",
        "sample_f1",
        "sample_undefined_reasons",
        "ewt",
        "ewt_reason",
        "undefined_reasons",
        "censored_exclusions",
        "untrusted_exclusions",
        "exclusion_reason_codes",
        "score_semantics",
    )
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        serialized = {}
        for column in columns:
            value = row.get(column)
            if isinstance(value, (list, tuple)):
                value = ";".join(str(item) for item in value)
            serialized[column] = "" if value is None else value
        writer.writerow(serialized)
    return buffer.getvalue()


def _cv_fold_manifest(result: BenchmarkResult) -> dict[str, Any]:
    first = result.fold_runs[0] if result.fold_runs else None
    entries = []
    for fold in result.cv.folds:
        matching = [
            row
            for row in result.fold_runs
            if row.fold_id == fold.fold_id
            and row.strategy == (first.strategy if first is not None else "")
        ]
        fold_result = matching[0] if matching else None
        entries.append(
            {
                **fold.to_manifest(result.cv.seed),
                "train_window_count": (
                    fold_result.train_sample_count if fold_result else None
                ),
                "validation_window_count": (
                    fold_result.validation_sample_count if fold_result else None
                ),
                "train_class_counts": (
                    {
                        "positive": fold_result.train_positive,
                        "negative": fold_result.train_negative,
                    }
                    if fold_result
                    else None
                ),
                "validation_class_counts": (
                    {
                        "positive": fold_result.validation_positive,
                        "negative": fold_result.validation_negative,
                    }
                    if fold_result
                    else None
                ),
                "censored_exclusions": (
                    fold_result.censored_exclusions if fold_result else None
                ),
                "untrusted_exclusions": (
                    fold_result.untrusted_exclusions if fold_result else None
                ),
            }
        )
    return {
        "schema": "coldguard-w11-cv-fold-manifest-v1",
        "layer_version": W11_LAYER_VERSION,
        "dataset_id": result.dataset_id,
        "fixture_version": result.fixture_version,
        "provenance": result.provenance,
        "grouping_key": result.cv.grouping_key,
        "effective_independent_groups": result.cv.effective_groups,
        "n_splits": result.cv.n_splits,
        "split_seed": result.cv.seed,
        "feature_registry_sha256": result.registry_sha256,
        "feature_ids": list(result.feature_ids),
        "label_identity": dict(result.label_identity),
        "model_config_sha256": result.config_sha256,
        "test_partition_used": False,
        "test_runs": list(result.split_identity.get("test_runs", ())),
        "folds": entries,
    }


def _fold_summary_table(result: BenchmarkResult) -> list[str]:
    rows = [
        "| Fold | Strategy | Train groups | Validation groups | Train +/- | "
        "Validation +/- | AP | Undefined reason |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in result.fold_runs:
        ap = ""
        reason = ""
        if row.metrics is not None:
            ap_metric = row.metrics["average_precision"]
            ap = (
                "undefined"
                if ap_metric["value"] is None
                else f"{ap_metric['value']:.4f}"
            )
            reason = ap_metric["reason"] or ""
        rows.append(
            f"| {row.fold_id} | {row.strategy} | {len(row.train_groups)} | "
            f"{len(row.validation_groups)} | {row.train_positive}/{row.train_negative} | "
            f"{row.validation_positive}/{row.validation_negative} | {ap} | {reason} |"
        )
    return rows


def _baseline_table(result: BenchmarkResult) -> list[str]:
    rows = [
        "| Method | Fold | Eligible samples | Event denominator | Sample AP | "
        "Event precision | Event recall | Matched | Unmatched | Missed | EWT |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in result.baseline_rows:
        def fmt(value: Any, digits: int = 4) -> str:
            if value is None:
                return "N/A"
            if isinstance(value, float):
                return f"{value:.{digits}f}"
            return str(value)

        rows.append(
            f"| {row['method']} | {row['fold_id']} | "
            f"{fmt(row.get('eligible_sample_count'))} | "
            f"{fmt(row.get('eligible_critical_event_count'))} | "
            f"{fmt(row.get('sample_ap'))} | "
            f"{fmt(row.get('event_precision'))} | {fmt(row.get('event_recall'))} | "
            f"{fmt(row.get('matched_warning_episodes'))} | "
            f"{fmt(row.get('unmatched_warnings'))} | "
            f"{fmt(row.get('missed_critical_events'))} | {row.get('ewt')} |"
        )
    return rows


def _oof_table(result: BenchmarkResult) -> list[str]:
    rows = [
        "| Strategy | OOF status | OOF AP | Fold AP values | Fold instability | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for strategy, payload in result.oof.items():
        metrics = payload.get("metrics") or {}
        ap = (metrics.get("average_precision") or {}).get("value")
        fold_ap = payload.get("fold_ap") or {}
        values = fold_ap.get("fold_values") or fold_ap.get("defined_values") or []
        rows.append(
            f"| {strategy} | {payload.get('status')} | "
            f"{'N/A' if ap is None else f'{ap:.4f}'} | "
            f"{', '.join(f'{value:.4f}' for value in values) if values else 'N/A'} | "
            f"{'N/A' if fold_ap.get('instability_range') is None else f'{fold_ap['instability_range']:.4f}'} | "
            f"{payload.get('reason') or (fold_ap.get('reason') or '')} |"
        )
    return rows


def _report_markdown(
    result: BenchmarkResult,
    audit: LeakageAuditResult,
    *,
    config: BenchmarkConfig,
    w10_binding: Mapping[str, Any],
    w08_binding: Mapping[str, Any],
    real_status: Mapping[str, Any],
    artifact_hashes: Mapping[str, Any],
    repository_revision: str,
) -> str:
    verdicts = _scientific_verdicts(result, audit, real_status)
    lines = [
        "# W11 grouped XGBoost benchmark report",
        "",
        "> W11 software report. Synthetic training is a software control, never "
        "physical evidence. The real A capture is invalid and Gate B is RED; no "
        "real model was trained and no real benchmark exists.",
        "",
        "## 1. Scientific verdicts",
        "",
        "| Domain | Status |",
        "|---|---|",
        f"| W11 software | {verdicts['W11_SOFTWARE']} |",
        f"| Synthetic training | {verdicts['SYNTHETIC_TRAINING']} |",
        f"| Grouped evaluation framework | {verdicts['GROUPED_EVALUATION_FRAMEWORK']} |",
        f"| Physical Gate B | {verdicts['PHYSICAL_GATE_B']} |",
        f"| Real predictive dataset | {verdicts['REAL_PREDICTIVE_DATASET']} |",
        f"| Real XGBoost benchmark | {verdicts['REAL_XGBOOST_BENCHMARK']} |",
        f"| Real baseline comparison | {verdicts['REAL_BASELINE_COMPARISON']} |",
        f"| Real EWT | {verdicts['REAL_EWT']} |",
        f"| Real AIW | {verdicts['REAL_AIW']} |",
        "",
        "## 2. Population and provenance",
        "",
        f"- Dataset: `{result.dataset_id}`",
        f"- Fixture version: `{result.fixture_version}`",
        f"- Provenance: `{result.provenance}`",
        f"- W10 parent manifest: `{w10_binding['path']}` SHA-256 `{w10_binding['sha256']}`",
        f"- W08 Gate B manifest: `{w08_binding.get('path')}` SHA-256 `{w08_binding.get('sha256')}`",
        f"- Feature registry SHA-256: `{result.registry_sha256}`",
        f"- Model config SHA-256: `{result.config_sha256}`",
        f"- Repository revision at generation: `{repository_revision}`",
        f"- Test runs (untouched): {', '.join(result.split_identity.get('test_runs', ())) or 'none'}",
        f"- {PINNED_TEST_RUN_NOTICE}",
        "",
        "The W11 expanded fixture is independently generated with deterministic "
        "synthetic sources. It does not borrow, inspect or modify the W10 "
        "held-out synthetic test pair or any real physical data.",
        "",
        "## 3. Grouped development split and CV",
        "",
        f"- Grouping key: {result.cv.grouping_key}",
        f"- Effective independent groups: {result.cv.effective_groups}",
        f"- Folds: {result.cv.n_splits} (seed {result.cv.seed})",
        f"- Development samples: {len(result.labeled.samples)} "
        f"({result.labeled.positive_count} positive, "
        f"{result.labeled.negative_count} negative)",
        f"- Censored label exclusions: {result.labeled.total_excluded.get('CENSORED', 0)}",
        f"- Untrusted label exclusions: {result.labeled.total_excluded.get('UNTRUSTED_INFO', 0)}",
        "- Bound-preserving order: grouped split → causal feature windows → labels → "
        "train-only transforms → fit → grouped evaluation.",
        "",
        "Fold inventory:",
        "",
        "| Fold | Train runs | Validation runs | Train groups | Validation groups |",
        "|---|---|---|---|---|",
    ]
    for fold in result.cv.folds:
        lines.append(
            f"| {fold.fold_id} | {', '.join(fold.train_runs)} | "
            f"{', '.join(fold.validation_runs)} | {', '.join(fold.train_groups)} | "
            f"{', '.join(fold.validation_groups)} |"
        )
    lines.extend(
        [
            "",
            "## 4. Label and feature identity",
            "",
            f"- Label spec: `{config.label.spec_version}`",
            f"- Horizon H: {config.label.horizon_s:g} s (development candidate; not frozen)",
            f"- Label identity: `{json.dumps(dict(result.label_identity), sort_keys=True)}`",
            f"- Feature count: {len(result.feature_ids)}",
            "- Explicit allowlist: " + ", ".join(f"`{item}`" for item in result.feature_ids),
            "- Excluded diagnostic feature: `T_tec_hot_side_c`",
            "- Missing values become NaN; an UNKNOWN electrical quality is never zero-filled.",
            "",
            "## 5. Model and score semantics",
            "",
            f"- Model family: XGBoost {result.versions.get('xgboost')}",
            f"- Parameters: `{json.dumps(dict(config.model_params), sort_keys=True)}`",
            f"- Imbalance strategies: {', '.join(config.strategies)}",
            f"- Score semantics: `{config.score_semantics}` — not a calibrated probability",
            f"- Calibration: `{config.calibration_status}`",
            f"- Risk operating threshold: {config.risk_threshold} (illustrative development point)",
            f"- Package versions: `{json.dumps(dict(result.versions), sort_keys=True)}`",
            "",
            "## 6. Fold results",
            "",
            *_fold_summary_table(result),
            "",
            "### Out-of-fold summary",
            "",
            *_oof_table(result),
            "",
            "Per-fold values are retained; no best-looking fold is presented as the benchmark.",
            "",
            "> The expanded fixture is a deterministic software control. A perfect "
            "or near-perfect AP here reflects scenario-identifying synthetic "
            "features such as door state and thermal excursion, not physical "
            "predictive performance. No synthetic AP is a ColdGuard result.",
            "",
            "## 7. Imbalance comparison",
            "",
            "Both strategies reuse the same folds, feature order and label population. "
            "Class weights are derived only from the training group labels in each fold; "
            "a single-class training fold refuses fit rather than inventing a weight.",
            "",
            "| Strategy | Fit folds | Refused folds | Weight formula |",
            "|---|---|---|---|",
        ]
    )
    for strategy in config.strategies:
        rows = [row for row in result.fold_runs if row.strategy == strategy]
        fitted = [row for row in rows if row.status == "FIT"]
        refused = [row for row in rows if row.status != "FIT"]
        formula = (
            fitted[0].weight_formula if fitted else "not applicable"
        )
        lines.append(
            f"| {strategy} | {len(fitted)} | {len(refused)} | {formula} |"
        )
    lines.extend(
        [
            "",
            "## 8. B0/B1 versus XGBoost",
            "",
            "The comparison uses the same eligible development runs, physical source "
            "identity, event-time domain, label/critical-event definition, horizon, "
            "warning-episode policy and censoring rules. The methods have different "
            "semantics: B0 is a raw threshold criterion, B1 is a reactive hysteresis "
            "ON state, and XGBoost is a learned risk score. Their AP values are not "
            "an equal-semantics contest; the metric unit is named below.",
            "",
            *_baseline_table(result),
            "",
            "- Sample unit: feature anchor window.",
            "- Event unit: warning episode versus prescribed critical event.",
            "- B0/B1 are reused from W09; their state machines are not reimplemented.",
            "- EWT and AIW are `NOT_ESTIMABLE`: W11 has no measured command/ACK/thermal "
            "latency chain.",
            "- A warning episode is one operational event, not one positive sample.",
            "- Eventless and censored populations remain undefined, never zero.",
            "",
            "## 9. Real physical data",
            "",
            f"- Gate B: `{real_status['PHYSICAL_GATE_B']}`",
            f"- Eligible real runs: {real_status['ELIGIBLE_RUNS']}",
            f"- Real development split: `{real_status['REAL_DEVELOPMENT_SPLIT']}`",
            f"- Training executed: `{real_status['TRAINING_EXECUTED']}`",
            f"- Benchmark status: `{real_status['BENCHMARK_STATUS']}`",
            f"- Real XGBoost benchmark: `{real_status['REAL_XGBOOST_BENCHMARK']}`",
            f"- Real baseline comparison: `{real_status['REAL_BASELINE_COMPARISON']}`",
            f"- Real EWT: `{real_status['REAL_EWT']}`",
            f"- Real AIW: `{real_status['REAL_AIW']}`",
            "- Refusal reasons: " + (", ".join(real_status.get("REASONS", ())) or "none"),
            "",
            "The A W09 capture is diagnostic only. Gate B RED is not permission to "
            "train on its rows, and no synthetic metric is promoted into physical evidence.",
            "",
            "## 10. Leakage audit",
            "",
            "| Result | Count |",
            "|---|---|",
        ]
    )
    for name, count in audit.summary().items():
        lines.append(f"| `{name}` | {count} |")
    lines.extend(
        [
            "",
            "Full record: `leakage-audit-W11.md`.",
            "",
            "## 11. Artifacts",
            "",
            "```text",
            "ml/xgb-v1-config.yaml",
            "ml/src/coldguard_ml/xgb_benchmark.py",
            "ml/src/coldguard_ml/grouped_evaluation.py",
            "ml/src/coldguard_ml/leakage_audit.py",
            "ml/scripts/xgb-benchmark-W11.py",
            "ml/reports/W11/cv-fold-manifest.yaml",
            "ml/reports/W11/xgb-v1-report.md",
            "ml/reports/W11/leakage-audit-W11.md",
            "ml/reports/W11/benchmark-manifest-W11.json",
            "ml/reports/W11/fold-metrics-W11.csv",
            "ml/reports/W11/baseline-comparison-W11.csv",
            "ml/reports/W11/model-synthetic-smoke.ubj",
            "ml/reports/W11/model-synthetic-smoke.json",
            "```",
            "",
            "| Artifact | SHA-256 |",
            "|---|---|",
        ]
    )
    for name, digest in sorted(artifact_hashes.items()):
        lines.append(f"| `{name}` | `{digest}` |")
    lines.extend(
        [
            "",
            "## 12. Limitations",
            "",
        ]
    )
    for limitation in result.limitations:
        lines.append(f"- {limitation}")
    lines.extend(
        [
            "- The synthetic AP is not a ColdGuard predictive-science result.",
            "- No real calibration, EWT, AIW, false-warning burden or baseline "
            "improvement is established.",
            "- W12 owns the consolidated benchmark and Gate G3 report; W11 does not "
            "implement W12 conclusions.",
            "",
        ]
    )
    return "\n".join(lines)


def _benchmark_manifest(
    result: BenchmarkResult,
    audit: LeakageAuditResult,
    *,
    config: BenchmarkConfig,
    w10_binding: Mapping[str, Any],
    w08_binding: Mapping[str, Any],
    w09_binding: Mapping[str, Any],
    real_status: Mapping[str, Any],
    artifact_hashes: Mapping[str, Any],
    analysis_code_sha256: str,
    repository_revision: str,
    command: str,
) -> dict[str, Any]:
    return {
        "schema": W11_REPORT_SCHEMA,
        "layer_version": W11_LAYER_VERSION,
        "dataset_id": result.dataset_id,
        "fixture_version": result.fixture_version,
        "provenance": result.provenance,
        "scientific_status": result.status,
        "repository_revision": repository_revision,
        "generation_command": command,
        "generated_at_utc": "NOT_RECORDED_BY_DESIGN",
        "analysis_code_sha256": analysis_code_sha256,
        "registry_sha256": result.registry_sha256,
        "config": config.to_dict(),
        "feature_ids": list(result.feature_ids),
        "label_identity": dict(result.label_identity),
        "label": {
            "spec_version": config.label.spec_version,
            "horizon_s": config.label.horizon_s,
            "frozen_at": None,
            "status": config.label.status,
        },
        "split": dict(result.split_identity),
        "cv": result.cv.to_manifest(),
        "labeled_dataset": result.labeled.to_dict(),
        "fold_runs": [row.to_dict() for row in result.fold_runs],
        "oof": dict(result.oof),
        "baseline_comparison": [dict(row) for row in result.baseline_rows],
        "model_artifact": dict(result.model_artifact) if result.model_artifact else None,
        "package_versions": dict(result.versions),
        "w10_binding": dict(w10_binding),
        "w08_binding": dict(w08_binding),
        "w09_binding": dict(w09_binding),
        "real_development": dict(real_status),
        "leakage_audit": audit.to_dict(),
        "verification": {
            "future_perturbation": {
                probe.probe_id: probe.status for probe in audit.probes
            }.get("future_mutation", "NOT_TESTED"),
            "grouped_folds_disjoint": {
                probe.probe_id: probe.status for probe in audit.probes
            }.get("grouped_disjoint", "NOT_TESTED"),
            "pair_lineage_preserved": {
                probe.probe_id: probe.status for probe in audit.probes
            }.get("pair_preservation", "NOT_TESTED"),
            "gate_b_bypass_refused": {
                probe.probe_id: probe.status for probe in audit.probes
            }.get("gate_b_bypass", "NOT_TESTED"),
            "locked_test_used": False,
            "training_only_preprocessing": "XGBoost native NaN handling; no global fit",
            "model_load_predictions_match": (
                result.model_artifact or {}
            ).get("load_predictions_match", False),
        },
        "reason_codes": list(result.reason_codes),
        "scientific_verdicts": _scientific_verdicts(result, audit, real_status),
        "artifacts": {
            name: {"sha256": digest} for name, digest in sorted(artifact_hashes.items())
        },
        "deterministic": True,
    }


def _load_w08_binding(path: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not path.exists():
        return (
            {
                "path": str(path).replace("\\", "/"),
                "sha256": None,
                "physical_gate": "NOT_AVAILABLE",
            },
            None,
        )
    w08 = load_w08_manifest(path)
    return (
        {
            "path": str(path).replace("\\", "/"),
            "sha256": _sha256_file(path),
            "physical_gate": w08["physical_gate"]["observed_status"],
            "data_origin": w08.get("data_origin"),
        },
        w08,
    )


def _load_w09_binding(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path).replace("\\", "/"),
            "sha256": None,
            "status": "NOT_AVAILABLE",
        }
    return {
        "path": str(path).replace("\\", "/"),
        "sha256": _sha256_file(path),
        "status": "RECORDED",
    }


def _write_synthetic_artifacts(
    *,
    mode: str,
    fixture: BenchmarkFixture,
    result: BenchmarkResult,
    registry,
    config: BenchmarkConfig,
    out_dir: Path,
    w10_binding: Mapping[str, Any],
    w08_binding: Mapping[str, Any],
    w08_payload: Mapping[str, Any] | None,
    w09_binding: Mapping[str, Any],
    real_status: Mapping[str, Any],
    repository_revision: str,
    command: str,
    ml_root: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    model_dir = out_dir if mode == "synthetic-grouped-cv" else out_dir / "smoke"
    model_dir.mkdir(parents=True, exist_ok=True)
    # The benchmark saved model files to the requested model directory.
    audit = run_leakage_audit(fixture, registry, config, benchmark=result)
    fold_csv = _fold_metrics_csv(result)
    baseline_csv = _baseline_comparison_csv(result)
    fold_yaml = yaml.safe_dump(
        _cv_fold_manifest(result), sort_keys=False, allow_unicode=True
    )
    artifact_payloads: dict[str, bytes] = {}
    if mode == "synthetic-grouped-cv":
        artifact_payloads["fold-metrics-W11.csv"] = fold_csv.encode("utf-8")
        artifact_payloads["baseline-comparison-W11.csv"] = baseline_csv.encode("utf-8")
        artifact_payloads["cv-fold-manifest.yaml"] = fold_yaml.encode("utf-8")
        artifact_payloads["leakage-audit-W11.md"] = audit.to_markdown().encode("utf-8")
    model_files = (result.model_artifact or {}).get("files", {})
    artifact_hashes: dict[str, str] = {}
    for name, payload in artifact_payloads.items():
        (out_dir / name).write_bytes(payload)
        artifact_hashes[name] = _sha256_bytes(payload)
    for name, entry in model_files.items():
        source = model_dir / entry["file"]
        if source.exists():
            artifact_hashes[entry["file"]] = _sha256_bytes(source.read_bytes())
    if mode == "synthetic-grouped-cv":
        report = _report_markdown(
            result,
            audit,
            config=config,
            w10_binding=w10_binding,
            w08_binding=w08_binding,
            real_status=real_status,
            artifact_hashes=artifact_hashes,
            repository_revision=repository_revision,
        )
        report_bytes = report.encode("utf-8")
        (out_dir / "xgb-v1-report.md").write_bytes(report_bytes)
        artifact_hashes["xgb-v1-report.md"] = _sha256_bytes(report_bytes)
    manifest = _benchmark_manifest(
        result,
        audit,
        config=config,
        w10_binding=w10_binding,
        w08_binding=w08_binding,
        w09_binding=w09_binding,
        real_status=real_status,
        artifact_hashes=artifact_hashes,
        analysis_code_sha256=_analysis_code_sha256(ml_root),
        repository_revision=repository_revision,
        command=command,
    )
    manifest_name = (
        "benchmark-manifest-W11.json"
        if mode == "synthetic-grouped-cv"
        else "synthetic-smoke-W11.json"
    )
    manifest["artifacts"] = {
        name: {"sha256": digest} for name, digest in sorted(artifact_hashes.items())
    }
    (out_dir / manifest_name).write_bytes(
        (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")
    )
    print(
        f"W11 {mode} complete: status={result.status} "
        f"folds={len(result.fold_runs)} effective_groups={result.cv.effective_groups} "
        f"artifacts={out_dir}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ColdGuard W11 grouped XGBoost benchmark. Synthetic results are "
            "software controls, never physical evidence."
        )
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("synthetic-smoke", "synthetic-grouped-cv", "real-development"),
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parents[1] / "xgb-v1-config.yaml"),
        help="W11 model/config YAML",
    )
    parser.add_argument(
        "--feature-registry",
        default=str(Path(__file__).resolve().parents[1] / "feature-registry-v1.yaml"),
        help="frozen W10 feature registry",
    )
    parser.add_argument(
        "--w08-manifest",
        default="reports/W08/gate-b-manifest-W08.json",
        help="read-only W08 Gate B manifest",
    )
    parser.add_argument(
        "--w09-manifest",
        default="reports/W09/baseline-manifest-W09.json",
        help="read-only W09 baseline manifest",
    )
    parser.add_argument(
        "--w10-manifest",
        default="reports/W10/feature-manifest-W10.json",
        help="read-only W10 feature manifest",
    )
    parser.add_argument(
        "--a-capture",
        default="../evidence/A/W09/exports/CG-S1-H8C-600S.json",
        help="read-only A W09 capture for the real admission gate",
    )
    parser.add_argument("--out", default="reports/W11", help="artifact output directory")
    parser.add_argument(
        "--repository-revision",
        default=None,
        help="recorded repository revision (default: git HEAD)",
    )
    args = parser.parse_args(argv)
    ml_root = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out)
    revision = args.repository_revision or _git_revision(ml_root)
    command = "python " + " ".join(sys.argv)
    try:
        registry = load_registry(args.feature_registry)
        config = load_benchmark_config(args.config, registry)
        w10_binding = _load_w10_binding(
            Path(args.w10_manifest), config, registry.schema_sha256
        )
        w08_binding, w08_payload = _load_w08_binding(Path(args.w08_manifest))
        w09_binding = _load_w09_binding(Path(args.w09_manifest))
        capture = None
        capture_sha = None
        capture_path = Path(args.a_capture)
        if capture_path.exists():
            capture = load_capture(capture_path)
            capture_sha = capture.source.sha256
        if w08_payload is not None:
            real_status = real_development_status(
                w08_payload, capture=capture, capture_sha256=capture_sha
            )
        else:
            real_status = {
                "MODE": "real-development",
                "PHYSICAL_GATE_B": "NOT_AVAILABLE",
                "ELIGIBLE_RUNS": 0,
                "TRAINING_EXECUTED": "NO",
                "BENCHMARK_STATUS": "NOT_FEASIBLE",
                "REAL_DEVELOPMENT_SPLIT": "NOT_FEASIBLE",
                "REAL_XGBOOST_BENCHMARK": "NOT_ESTABLISHED",
                "REAL_BASELINE_COMPARISON": "NOT_ESTABLISHED",
                "REAL_EWT": "NOT_ESTIMABLE",
                "REAL_AIW": "NOT_ESTIMABLE",
                "REASONS": ["W08_MANIFEST_NOT_AVAILABLE"],
            }
        if args.mode == "real-development":
            out_dir.mkdir(parents=True, exist_ok=True)
            refusal = {
                "schema": "coldguard-w11-real-development-status-v1",
                "layer_version": W11_LAYER_VERSION,
                "generated_at_utc": "NOT_RECORDED_BY_DESIGN",
                "repository_revision": revision,
                "command": command,
                **dict(real_status),
            }
            (out_dir / "real-development-refusal-W11.json").write_text(
                json.dumps(refusal, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            for key in REAL_STATUS_KEYS:
                print(f"{key}: {real_status[key]}")
            print(
                "W11 REAL DEVELOPMENT REFUSED: no model was fitted; "
                "scientific status NOT_FEASIBLE"
            )
            return 2
        if args.mode == "synthetic-smoke":
            fixture = build_w10_compatibility_fixture()
            result, _ = run_grouped_benchmark(
                fixture,
                registry,
                config,
                out_dir=out_dir / "smoke",
                n_splits_override=2,
            )
        else:
            fixture = build_expanded_w11_fixture()
            result, _ = run_grouped_benchmark(
                fixture, registry, config, out_dir=out_dir
            )
        _write_synthetic_artifacts(
            mode=args.mode,
            fixture=fixture,
            result=result,
            registry=registry,
            config=config,
            out_dir=out_dir,
            w10_binding=w10_binding,
            w08_binding=w08_binding,
            w08_payload=w08_payload,
            w09_binding=w09_binding,
            real_status=real_status,
            repository_revision=revision,
            command=command,
            ml_root=ml_root,
        )
        return 0
    except CliError as exc:
        print(f"W11 CONFIGURATION REFUSAL: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"W11 CONFIGURATION ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
