#!/usr/bin/env python3
"""ColdGuard W14 role-correct A1/A2, group-safe calibration and AIW evidence.

This script is a reproducibility driver over the frozen W10/W11/W13 contracts.
It never touches the locked synthetic test pair, real A/C/D source files or the
W10 feature registry. Every number it emits is a synthetic software control.

Outputs (default ``reports/W14``):
  A1-support-W14.csv, A1-fold-metrics-W14.csv, A1-arm-summary-W14.csv,
  A1-paired-folds-W14.csv, A1-feature-provenance-W14.csv
  A2-... (same family)
  calibration-folds-W14.csv, calibration-bins-W14.csv,
  calibration-summary-W14.json
  w14-manifest.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:  # installed package
    from coldguard_ml.feature_registry import load_registry
    from coldguard_ml.w14_ablation import (
        SYNTHETIC_SOFTWARE_CONTROL,
        W14_LAYER_VERSION,
        arm_summary,
        assert_matched_population,
        build_ablation_dataset,
        build_ablation_views,
        fold_metric_rows,
        paired_fold_comparison,
        population_identity,
        provenance_rows,
        run_ablation_arm,
        run_support,
        validate_arm_pair,
        validate_view,
    )
    from coldguard_ml.w14_calibration import (
        assess_w14_real_calibration_evidence,
        calibration_bin_rows,
        calibration_fold_rows,
        decide_output_semantics,
        run_grouped_calibration,
    )
    from coldguard_ml.xgb_benchmark import (
        build_expanded_w11_fixture,
        load_benchmark_config,
        package_versions,
    )
except ModuleNotFoundError:  # direct checkout invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml.feature_registry import load_registry
    from coldguard_ml.w14_ablation import (
        SYNTHETIC_SOFTWARE_CONTROL,
        W14_LAYER_VERSION,
        arm_summary,
        assert_matched_population,
        build_ablation_dataset,
        build_ablation_views,
        fold_metric_rows,
        paired_fold_comparison,
        population_identity,
        provenance_rows,
        run_ablation_arm,
        run_support,
        validate_arm_pair,
        validate_view,
    )
    from coldguard_ml.w14_calibration import (
        assess_w14_real_calibration_evidence,
        calibration_bin_rows,
        calibration_fold_rows,
        decide_output_semantics,
        run_grouped_calibration,
    )
    from coldguard_ml.xgb_benchmark import (
        build_expanded_w11_fixture,
        load_benchmark_config,
        package_versions,
    )

W14_MANIFEST_SCHEMA = "coldguard-w14-manifest-v1"
REFERENCE_HORIZON_STATUS = "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN"


class W14Error(RuntimeError):
    pass


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


def _json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"


def _csv(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        serialized: dict[str, Any] = {}
        for column in columns:
            value = row.get(column)
            if isinstance(value, (list, tuple)):
                value = ";".join(str(item) for item in value)
            serialized[column] = "" if value is None else value
        writer.writerow(serialized)
    return buffer.getvalue()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise W14Error(f"required input is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise W14Error(f"expected a JSON object: {path}")
    return payload


def _relative_ml_path(path: Path, ml_root: Path) -> str:
    try:
        return path.resolve().relative_to(ml_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _analysis_code_sha256(ml_root: Path) -> str:
    package = ml_root / "src" / "coldguard_ml"
    paths = (
        Path(__file__).resolve(),
        ml_root / "feature-registry-v1.yaml",
        ml_root / "xgb-v1-config.yaml",
        package / "w14_ablation.py",
        package / "w14_calibration.py",
        package / "xgb_benchmark.py",
        package / "grouped_evaluation.py",
        package / "feature_pipeline.py",
        package / "feature_registry.py",
        package / "labels.py",
        package / "splitting.py",
    )
    hasher = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _population_contract(fixture: Any, dataset: Any) -> dict[str, Any]:
    development_runs = list(fixture.split.train_runs) + list(
        fixture.split.validation_runs
    )
    return {
        "dataset_id": fixture.dataset_id,
        "fixture_version": fixture.fixture_version,
        "provenance": fixture.provenance,
        "development_runs": development_runs,
        "locked_test_runs": list(fixture.split.test_runs),
        "test_partition_used": False,
        "development_groups": sorted(
            {fixture.split.group_of[run_id] for run_id in development_runs}
        ),
        "evaluable_samples": len(dataset.samples),
        "positive": dataset.positive_count,
        "negative": dataset.negative_count,
        "excluded": dict(dataset.total_excluded),
        "excluded_by_run": {
            run_id: dict(value) for run_id, value in dataset.excluded_by_run.items()
        },
        "sample_identity_sha256": _sha256_bytes(
            json.dumps(population_identity(dataset), sort_keys=True).encode("utf-8")
        ),
    }


def _ewt_aiw_section(
    *,
    w13_manifest: Mapping[str, Any],
    w12_csv_text: str,
    pr95: Mapping[str, Any],
) -> dict[str, Any]:
    verdicts = w13_manifest.get("scientific_verdicts", {})
    plant = w13_manifest.get("plant_timing", {})
    reconciliation = w13_manifest.get("reconciliation", {})
    rows = list(csv.DictReader(io.StringIO(w12_csv_text)))
    real_rows = [
        row for row in rows if str(row.get("population", "")).upper().startswith("REAL")
    ]
    return {
        "EWT": {
            "status": verdicts.get("REAL_EWT", "NOT_ESTIMABLE"),
            "reason_code": "EWT_UNAVAILABLE_NO_QUALIFIED_COMMON_TRAJECTORY",
            "distinct_reasons": reconciliation.get("refusal_reasons", []),
            "measured_anchors": "NONE_IN_ONE_TRUSTED_EVENT_TIME_DOMAIN",
        },
        "AIW": {
            "status": verdicts.get("REAL_AIW", "NOT_ESTIMABLE"),
            "reason_code": "AIW_UNAVAILABLE_MEASURED_LATENCY_CHAIN_MISSING",
            "measured_inputs": {
                "command_to_electrical_s": plant.get("command_to_electrical_s"),
                "command_to_electrical_n": plant.get("electrical_n_measured"),
                "command_to_thermal_s": plant.get("command_to_thermal_s"),
                "door_to_critical_s": plant.get("door_to_critical_s"),
                "door_to_critical_status": plant.get("door_to_critical_status"),
                "physical_verified": plant.get("physical_verified"),
                "evidence_kind": plant.get("evidence_kind"),
            },
            "missing_dependencies": plant.get("gaps", []),
            "pr95": dict(pr95),
        },
        "w12_real_rows": real_rows,
        "w12_csv_sha256": _sha256_bytes(w12_csv_text.encode("utf-8")),
    }


def _verdicts(decision: str, ewt_status: str, aiw_status: str) -> dict[str, str]:
    return {
        "SOFTWARE": "COMPLETE",
        "A1": "SOFTWARE_VERIFIED",
        "A2": "SOFTWARE_VERIFIED",
        "CALIBRATION": decision,
        "EWT": ewt_status,
        "AIW": aiw_status,
        "DELIVERY": "PENDING_PUBLICATION",
    }


def _hard_boundaries() -> list[str]:
    return [
        "No W15 implementation.",
        "No A3 electrical ablation.",
        "No model release freeze.",
        "No locked-test evaluation.",
        "No physical control commands.",
        "No changes to A/C/D source or evidence.",
        "No rewriting canonical documentation.",
        "No fabricated calibration or physical result.",
        "No sensor-role relabeling to make A1 easier.",
        "No unapproved feature-registry mutation.",
        "No random row/window splitting.",
        "No use of locked test to select feature groups.",
        "No synthetic probability claim.",
        "No change to W13's scientific decision.",
        "No merging earlier PRs.",
        "No AGENTS.md, .opencode files or agent reports in the repository.",
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ColdGuard W14 A1/A2 ablation, group-safe calibration and AIW "
            "evidence. Synthetic results are software controls, never physical "
            "evidence."
        )
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parents[1] / "xgb-v1-config.yaml"),
    )
    parser.add_argument(
        "--feature-registry",
        default=str(Path(__file__).resolve().parents[1] / "feature-registry-v1.yaml"),
    )
    parser.add_argument(
        "--w13-manifest", default="reports/W13/horizon-manifest-W13.json"
    )
    parser.add_argument(
        "--w12-ewt", default="reports/W12/ewt-assessment-W12.csv"
    )
    parser.add_argument("--out", default="reports/W14")
    parser.add_argument("--repository-revision", default=None)
    args = parser.parse_args(argv)

    ml_root = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    revision = args.repository_revision or _git_revision(ml_root)

    registry = load_registry(args.feature_registry)
    config = load_benchmark_config(args.config, registry)
    fixture = build_expanded_w11_fixture()
    views = build_ablation_views(registry)
    validate_view(views["A1A"], registry)
    validate_view(views["A1B"], registry)
    validate_view(views["A2A"], registry)
    validate_view(views["A2B"], registry)
    validate_arm_pair(views["A1A"], views["A1B"])
    validate_arm_pair(views["A2A"], views["A2B"])
    if views["A1B"].feature_ids != config.feature_policy.allowlist:
        raise W14Error("A1B does not reproduce the frozen W11 feature allowlist")

    datasets = {
        arm: build_ablation_dataset(fixture, registry, config, view)
        for arm, view in views.items()
    }
    assert_matched_population(*datasets.values())

    results: dict[str, Any] = {}
    artifact_models: dict[str, Any] = {}
    for arm, view in views.items():
        with tempfile.TemporaryDirectory(prefix=f"coldguard-w14-{arm.lower()}-") as tmp:
            result, _ = run_ablation_arm(
                fixture, registry, config, view, scaffold_dir=Path(tmp)
            )
        results[arm] = result
        artifact_models[arm] = result.model_artifact

    calibration = run_grouped_calibration(
        fixture, registry, config, views["A1B"]
    )
    w13_path = Path(args.w13_manifest)
    w13_manifest = _load_json(w13_path)
    w12_path = Path(args.w12_ewt)
    w12_text = w12_path.read_text(encoding="utf-8")
    reconciliation = w13_manifest.get("reconciliation", {})
    pr95 = reconciliation.get("pr95_supplement", {})
    decision_inputs = w13_manifest.get("decision", {}).get(
        "selection_preconditions", {}
    )
    real_eligible = int(reconciliation.get("predictive_eligible_runs", 0))
    if real_eligible != 0:
        raise W14Error(
            "live W13 evidence now reports predictive-eligible real runs; W14 "
            "must be re-evaluated against the new real population instead of "
            "reusing the synthetic-only decision path"
        )
    label_frozen = bool(
        config.label.frozen_at is not None and config.label.boundary_c is not None
    )
    horizon_frozen = bool(
        w13_manifest.get("decision", {}).get("primary_horizon_s") is not None
        and decision_inputs.get("critical_criterion_frozen", False)
    )
    evidence = assess_w14_real_calibration_evidence(
        real_eligible_samples=0,
        real_eligible_groups=0,
        label_identity_frozen=label_frozen,
        horizon_frozen=horizon_frozen,
        product_requires_probability=False,
    )
    decision = decide_output_semantics(evidence)

    artifacts: dict[str, bytes] = {}
    support_columns = (
        "run_id",
        "group_id",
        "partition",
        "anchors",
        "positive",
        "negative",
    )
    fold_columns = (
        "arm_id",
        "fold_id",
        "strategy",
        "status",
        "reason",
        "validation_groups",
        "validation_runs",
        "train_samples",
        "validation_samples",
        "train_positive",
        "train_negative",
        "validation_positive",
        "validation_negative",
        "average_precision",
        "ap_status",
        "ap_reason",
        "roc_auc",
        "precision",
        "recall",
        "f1",
        "warning_episodes",
        "matched_episodes",
        "unmatched_warnings",
        "missed_events",
        "event_precision",
        "event_recall",
        "false_warnings_per_hour",
        "censored_exclusions",
        "untrusted_exclusions",
    )
    arm_columns = (
        "arm_id",
        "view_id",
        "feature_count",
        "group_count",
        "fold_count",
        "evaluable_samples",
        "positive",
        "negative",
        "censored_exclusions",
        "untrusted_exclusions",
        "fit_folds",
        "strategy_count",
        "fold_ap_min",
        "fold_ap_max",
        "strategy_fold_ap_values",
        "oof_ap",
        "scientific_class",
    )
    provenance_columns = (
        "arm_id",
        "view_id",
        "feature_id",
        "base_feature_id",
        "family",
        "registry_source_fields",
        "registry_sensor_roles",
        "view_source_roles",
        "view_source_fields",
        "transform",
        "time_domain",
        "lookback_s",
        "aggregation_definition",
    )
    paired_columns = (
        "component",
        "fold_id",
        "strategy",
        "ap_a",
        "ap_b",
        "delta_ap_b_minus_a",
        "event_recall_a",
        "event_recall_b",
        "false_warnings_a",
        "false_warnings_b",
        "missed_events_a",
        "missed_events_b",
    )

    paired: dict[str, Any] = {}
    summaries: dict[str, Any] = {}
    for component, arm_a, arm_b in (("A1", "A1A", "A1B"), ("A2", "A2A", "A2B")):
        pairs = paired_fold_comparison(results[arm_a], results[arm_b])
        pairs = [{**row, "component": component} for row in pairs]
        paired[component] = pairs
        artifacts[f"{component}-support-W14.csv"] = _csv(
            run_support(datasets[arm_a]), support_columns
        ).encode("utf-8")
        artifacts[f"{component}-fold-metrics-W14.csv"] = _csv(
            [
                {**row, "arm_id": arm_a}
                for row in fold_metric_rows(results[arm_a])
            ]
            + [
                {**row, "arm_id": arm_b}
                for row in fold_metric_rows(results[arm_b])
            ],
            fold_columns,
        ).encode("utf-8")
        summaries[arm_a] = arm_summary(results[arm_a], views[arm_a])
        summaries[arm_b] = arm_summary(results[arm_b], views[arm_b])
        artifacts[f"{component}-arm-summary-W14.csv"] = _csv(
            [
                {
                    **summary,
                    "oof_ap": json.dumps(summary["oof_ap"], sort_keys=True),
                    "strategy_fold_ap_values": json.dumps(
                        summary["strategy_fold_ap_values"], sort_keys=True
                    ),
                }
                for summary in (summaries[arm_a], summaries[arm_b])
            ],
            arm_columns,
        ).encode("utf-8")
        artifacts[f"{component}-paired-folds-W14.csv"] = _csv(
            pairs, paired_columns
        ).encode("utf-8")
        artifacts[f"{component}-feature-provenance-W14.csv"] = _csv(
            [
                {**row, "arm_id": arm_a, "view_id": views[arm_a].view_id}
                for row in provenance_rows(views[arm_a], registry)
            ]
            + [
                {**row, "arm_id": arm_b, "view_id": views[arm_b].view_id}
                for row in provenance_rows(views[arm_b], registry)
            ],
            provenance_columns,
        ).encode("utf-8")

    calibration_fold_columns = (
        "fold_id",
        "status",
        "reason",
        "detail",
        "model_fit_groups",
        "calibration_groups",
        "evaluation_groups",
        "model_fit_samples",
        "calibration_samples",
        "evaluation_samples",
        "calibration_positive",
        "calibration_negative",
        "evaluation_positive",
        "evaluation_negative",
        "raw_brier",
        "calibrated_brier",
        "brier_delta",
        "raw_ap",
        "calibrated_ap",
        "ap_reason",
        "non_empty_bins",
        "empty_bins",
        "perfect_separation",
    )
    bin_columns = (
        "scope",
        "bin_index",
        "lower",
        "upper",
        "count",
        "positive",
        "negative",
        "group_count",
        "mean_score",
        "observed_positive_fraction",
        "interpretable",
        "reason",
    )
    artifacts["calibration-folds-W14.csv"] = _csv(
        calibration_fold_rows(calibration), calibration_fold_columns
    ).encode("utf-8")
    artifacts["calibration-bins-W14.csv"] = _csv(
        calibration_bin_rows(calibration), bin_columns
    ).encode("utf-8")
    artifacts["calibration-summary-W14.json"] = _json(calibration.to_dict()).encode(
        "utf-8"
    )

    population = _population_contract(fixture, datasets["A1A"])
    ewt_aiw = _ewt_aiw_section(
        w13_manifest=w13_manifest,
        w12_csv_text=w12_text,
        pr95=pr95,
    )
    fold_identity = results["A1A"].cv.to_manifest()
    if population["test_partition_used"]:
        raise W14Error("the locked test partition was used")
    if any(
        run_id in population["locked_test_runs"]
        for run_id in population["development_runs"]
    ):
        raise W14Error("a locked-test run entered the W14 population")

    for arm, view in views.items():
        result = results[arm]
        if tuple(result.feature_ids) != view.feature_ids:
            raise W14Error(f"{arm} result feature identity drifted")
        if "test" in {sample.partition for sample in result.labeled.samples}:
            raise W14Error(f"{arm} contains a locked-test sample")

    grouped_folds_disjoint = all(
        set(fold.train_groups).isdisjoint(fold.validation_groups)
        for result in results.values()
        for fold in result.cv.folds
    )
    if not grouped_folds_disjoint:
        raise W14Error("a grouped fold shares groups between train and validation")

    manifest = {
        "schema": W14_MANIFEST_SCHEMA,
        "layer_version": W14_LAYER_VERSION,
        "generation_base_revision": revision,
        "revision_semantics": "GENERATION_BASE_NOT_DELIVERY_COMMIT",
        "delivery_commit": "NOT_RECORDED_AT_GENERATION",
        "generation_command": (
            "uv run --locked --python 3.12 python scripts/w14-ablation-W14.py"
        ),
        "generated_at_utc": "NOT_RECORDED_BY_DESIGN",
        "analysis_code_sha256": _analysis_code_sha256(ml_root),
        "scientific_verdicts": _verdicts(
            decision.decision,
            ewt_aiw["EWT"]["status"],
            ewt_aiw["AIW"]["status"],
        ),
        "scientific_class": SYNTHETIC_SOFTWARE_CONTROL,
        "inputs": {
            "feature_registry": {
                "path": _relative_ml_path(Path(args.feature_registry), ml_root),
                "schema_sha256": registry.schema_sha256,
                "file_sha256": _sha256_file(Path(args.feature_registry)),
            },
            "model_config": {
                "path": _relative_ml_path(Path(args.config), ml_root),
                "config_sha256": config.config_sha256,
                "file_sha256": _sha256_file(Path(args.config)),
            },
            "w13_manifest": {
                "path": _relative_ml_path(w13_path, ml_root),
                "sha256": _sha256_file(w13_path),
                "source_revision": reconciliation.get("source_revision"),
                "run_index_sha256": reconciliation.get("run_index_sha256"),
                "manifest_sha256": reconciliation.get("manifest_sha256"),
            },
            "w12_ewt": {
                "path": _relative_ml_path(w12_path, ml_root),
                "sha256": _sha256_file(w12_path),
            },
            "fixture_dataset_id": fixture.dataset_id,
            "fixture_version": fixture.fixture_version,
            "model_family": "XGBoost",
            "model_params": dict(config.model_params),
            "risk_threshold": config.risk_threshold,
            "score_semantics": config.score_semantics,
            "model_config_calibration_status": config.calibration_status,
            "calibration_diagnostics_performed": True,
            "calibration_diagnostics_scientific_class": SYNTHETIC_SOFTWARE_CONTROL,
        },
        "reference_horizon": {
            "value_s": config.label.horizon_s,
            "status": REFERENCE_HORIZON_STATUS,
            "source": "pre-existing W11 development label candidate; not selected by W14",
            "label_identity": dict(config.label.identity()),
            "primary_horizon_frozen": False,
        },
        "population": population,
        "fold_identity": fold_identity,
        "views": {arm: view.to_dict() for arm, view in views.items()},
        "arms": summaries,
        "paired_folds": paired,
        "calibration": {
            "diagnostics": calibration.to_dict(),
            "real_evidence": {
                **evidence.__dict__,
                "missing_requirements": list(evidence.missing_requirements()),
            },
            "decision": decision.to_dict(),
        },
        "ewt_aiw": ewt_aiw,
        "verification": {
            "locked_test_untouched": True,
            "test_partition_used": False,
            "w10_registry_schema_sha256": registry.schema_sha256,
            "a1b_reproduces_w11_allowlist": True,
            "a1a_single_sensor_role": "CHAMBER_CENTER",
            "a1a_excludes_tec_hot_side": True,
            "a2_door_unknown_never_closed_verified_by_test": True,
            "grouped_folds_disjoint_computed": grouped_folds_disjoint,
            "sample_population_identity_sha256": population[
                "sample_identity_sha256"
            ],
            "calibration_candidate_family": ["sigmoid"],
            "isotonic_refused": "CALIBRATION_ISOTONIC_REFUSED_INSUFFICIENT_CALIBRATION_SAMPLES",
            "default_cv_used": False,
            "prior_gate_g3_declared": "NO-GO / FIX DATA",
            "w13_horizon_decision": w13_manifest.get("scientific_verdicts", {}).get(
                "HORIZON_DECISION"
            ),
            "w13_primary_horizon_frozen": w13_manifest.get(
                "scientific_verdicts", {}
            ).get("PRIMARY_HORIZON_FROZEN"),
            "prior_layer_code_hash_drift": (
                "xgb_benchmark.py gained an optional labeled_override parameter "
                "after W11-W13; with override=None the W11 path is unchanged and "
                "the W14 test suite proves fold-level result equivalence. W11/W12/"
                "W13 result artifacts were not modified."
            ),
        },
        "model_artifacts_scratch_only": {
            arm: {
                "files": (artifact or {}).get("files", {}),
                "promotable_to_physical_model": False,
            }
            for arm, artifact in artifact_models.items()
        },
        "hard_boundaries": _hard_boundaries(),
        "artifacts": {
            name: {"sha256": _sha256_bytes(payload)}
            for name, payload in sorted(artifacts.items())
        },
        "package_versions": package_versions(),
        "deterministic": True,
    }
    for name, payload in artifacts.items():
        (out_dir / name).write_bytes(payload)
    manifest_name = "w14-manifest.json"
    (out_dir / manifest_name).write_bytes(
        _json(manifest).encode("utf-8")
    )
    print(
        "W14 analysis complete: "
        f"A1={summaries['A1A']['oof_ap']} vs {summaries['A1B']['oof_ap']}; "
        f"A2={summaries['A2A']['oof_ap']} vs {summaries['A2B']['oof_ap']}; "
        f"calibration={decision.decision}; "
        f"EWT={ewt_aiw['EWT']['status']}; AIW={ewt_aiw['AIW']['status']}; "
        f"artifacts={out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
