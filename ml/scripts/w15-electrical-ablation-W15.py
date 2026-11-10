#!/usr/bin/env python3
"""ColdGuard W15 A3 electrical ablation, electrical audit and model candidate.

This script is a reproducibility driver over the frozen W10/W11/W13/W14
contracts.  It never touches the locked synthetic test pair, real A/C/D source
files or the W10 feature registry.  Every number it emits is a synthetic
software control.

Outputs (default ``reports/W15``):
  A3-support-W15.csv, A3-fold-metrics-W15.csv, A3-arm-summary-W15.csv,
  A3-paired-folds-W15.csv, A3-feature-provenance-W15.csv,
  A3-electrical-audit-W15.csv, A3-electrical-diagnostics-W15.csv,
  A3-adversarial-probes-W15.json, hyperparameter-freeze-candidate-W15.json,
  model/model.ubj, model/model.json, model/model-manifest-W15.json,
  w15-manifest.json
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
from typing import Any, Mapping, Sequence

try:  # installed package
    from coldguard_ml.feature_fixtures import build_trajectory
    from coldguard_ml.feature_registry import load_registry
    from coldguard_ml.w14_ablation import (
        arm_summary,
        assert_matched_population,
        build_ablation_dataset,
        fold_metric_rows,
        paired_fold_comparison,
        population_identity,
        provenance_rows,
        run_ablation_arm,
        run_support,
    )
    from coldguard_ml.w15_ablation import (
        A3_ELECTRICAL_FEATURES,
        REFERENCE_HORIZON_STATUS,
        SYNTHETIC_SOFTWARE_CONTROL,
        W15_LAYER_VERSION,
        build_a3_views,
        counter_reset_probe,
        electrical_block_invariance,
        electrical_feature_diagnostics,
        electrical_provenance_rows,
        future_isolation_probe,
        transition_after_anchor_probe,
        unknown_electrical_probe,
        validate_a3_views,
    )
    from coldguard_ml.w15_artifact import (
        ARTIFACT_ID,
        NON_DEPLOYABLE,
        PRIMARY_FORMAT,
        PROBE_TOLERANCE,
        RISK_SCORE_ONLY,
        build_model_manifest,
        compute_model_inspection,
        fit_final_candidate,
        native_model_bytes,
        save_native_models,
        verify_fresh_process_parity,
    )
    from coldguard_ml.xgb_benchmark import (
        build_expanded_w11_fixture,
        feature_matrix,
        load_benchmark_config,
        package_versions,
    )
except ModuleNotFoundError:  # direct checkout invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml.feature_fixtures import build_trajectory
    from coldguard_ml.feature_registry import load_registry
    from coldguard_ml.w14_ablation import (
        arm_summary,
        assert_matched_population,
        build_ablation_dataset,
        fold_metric_rows,
        paired_fold_comparison,
        population_identity,
        provenance_rows,
        run_ablation_arm,
        run_support,
    )
    from coldguard_ml.w15_ablation import (
        A3_ELECTRICAL_FEATURES,
        REFERENCE_HORIZON_STATUS,
        SYNTHETIC_SOFTWARE_CONTROL,
        W15_LAYER_VERSION,
        build_a3_views,
        counter_reset_probe,
        electrical_block_invariance,
        electrical_feature_diagnostics,
        electrical_provenance_rows,
        future_isolation_probe,
        transition_after_anchor_probe,
        unknown_electrical_probe,
        validate_a3_views,
    )
    from coldguard_ml.w15_artifact import (
        ARTIFACT_ID,
        NON_DEPLOYABLE,
        PRIMARY_FORMAT,
        PROBE_TOLERANCE,
        RISK_SCORE_ONLY,
        build_model_manifest,
        compute_model_inspection,
        fit_final_candidate,
        native_model_bytes,
        save_native_models,
        verify_fresh_process_parity,
    )
    from coldguard_ml.xgb_benchmark import (
        build_expanded_w11_fixture,
        feature_matrix,
        load_benchmark_config,
        package_versions,
    )

W15_MANIFEST_SCHEMA = "coldguard-w15-manifest-v1"


class W15Error(RuntimeError):
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
        raise W15Error(f"required input is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise W15Error(f"expected a JSON object: {path}")
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
        package / "w15_ablation.py",
        package / "w15_artifact.py",
        package / "w14_ablation.py",
        package / "xgb_benchmark.py",
        package / "feature_fixtures.py",
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


def _fold_event_summary(result: Any) -> dict[str, Any]:
    fits = [fold for fold in result.fold_runs if fold.status == "FIT"]
    recalls = [
        fold.event_metrics.get("event_recall")
        for fold in fits
        if fold.event_metrics and fold.event_metrics.get("event_recall") is not None
    ]
    false_warnings = [
        fold.event_metrics.get("false_warning_episodes_per_hour")
        for fold in fits
        if fold.event_metrics
        and fold.event_metrics.get("false_warning_episodes_per_hour") is not None
    ]
    missed = [
        fold.event_metrics.get("missed_critical_events")
        for fold in fits
        if fold.event_metrics
        and fold.event_metrics.get("missed_critical_events") is not None
    ]
    return {
        "fit_folds": len(fits),
        "mean_event_recall": (sum(recalls) / len(recalls)) if recalls else None,
        "mean_false_warning_episodes_per_hour": (
            sum(false_warnings) / len(false_warnings) if false_warnings else None
        ),
        "total_missed_critical_events": sum(missed) if missed else None,
    }


def _hyperparameter_candidate(
    config: Any,
    registry: Any,
    fixture: Any,
    feature_ids: Sequence[str],
) -> dict[str, Any]:
    parameter_sources = {
        key: (
            "pre-existing W11 xgb-v1-config.yaml engineering default; not tuned "
            "on real physical data and not selected using the locked test"
        )
        for key in config.model_params
    }
    parameter_sources.update(
        {
            "scale_pos_weight": (
                "UNWEIGHTED artifact strategy fixes scale_pos_weight = 1.0; the "
                "weighted strategy remains a predeclared W11 comparison arm"
            ),
            "risk_threshold": (
                "pre-existing W11 illustrative threshold 0.5; W15 does not freeze "
                "an operating threshold"
            ),
        }
    )
    return {
        "schema": "coldguard-w15-hyperparameter-candidate-v1",
        "status": "DEVELOPMENT_CONFIG_CANDIDATE",
        "explicitly_not": [
            "PHYSICALLY_VALIDATED_MODEL",
            "APPROVED_RELEASE_MODEL",
            "W16_LOCKED_TEST_READY",
        ],
        "model_family": "XGBoost",
        "library_version": package_versions()["xgboost"],
        "config_version": config.config_version,
        "config_sha256": config.config_sha256,
        "parameters": {**dict(config.model_params), "scale_pos_weight": 1.0},
        "imbalance": {
            "artifact_strategy": "UNWEIGHTED",
            "predeclared_strategies": list(config.strategies),
            "selection_rule": config.raw.get("imbalance", {}).get(
                "selection_rule", "PREDECLARED_AP_ALL_FOLDS_REPORTED"
            ),
        },
        "feature_identity": {
            "feature_version": "CG-FEAT-1.0",
            "feature_schema_hash": registry.schema_sha256,
            "arm": "A3B",
            "ordered_feature_ids": list(feature_ids),
            "order_rule": "frozen W11 allowlist order; A3a is the same order minus the delta",
        },
        "target": {
            "spec_version": config.label.spec_version,
            "status": config.label.status,
            "frozen_at": config.label.frozen_at,
            "boundary_c": config.label.boundary_c,
        },
        "reference_horizon": {
            "value_s": config.label.horizon_s,
            "status": REFERENCE_HORIZON_STATUS,
            "primary_horizon_frozen": False,
        },
        "development_identity": {
            "dataset_id": fixture.dataset_id,
            "fixture_version": fixture.fixture_version,
            "split_seed": fixture.split.seed,
            "development_runs": list(fixture.split.train_runs)
            + list(fixture.split.validation_runs),
            "locked_test_runs": list(fixture.split.test_runs),
            "n_splits": config.cv.n_splits,
        },
        "output_semantics": config.score_semantics,
        "calibration_status": RISK_SCORE_ONLY,
        "operating_threshold": {
            "value": config.risk_threshold,
            "status": "ILLUSTRATIVE_NOT_FROZEN",
        },
        "warning_persistence": {"status": "NOT_FROZEN"},
        "parameter_sources": parameter_sources,
        "search_performed_in_w15": False,
        "provenance": SYNTHETIC_SOFTWARE_CONTROL,
    }


def _verdicts() -> dict[str, str]:
    return {
        "SOFTWARE": "COMPLETE",
        "A3": "SOFTWARE_VERIFIED",
        "PREDICTION_VALUE": "NOT_ESTABLISHED",
        "DIAGNOSIS_VALUE": "SOFTWARE_ONLY",
        "HYPERPARAMETER_CANDIDATE": "DECLARED",
        "MODEL_ARTIFACT": "SYNTHETIC_NON_DEPLOYABLE",
        "CALIBRATION": RISK_SCORE_ONLY,
        "DEEP_MODEL": "NO-GO",
        "DELIVERY": "PENDING_PUBLICATION",
    }


def _hard_boundaries() -> list[str]:
    return [
        "No W16 locked-test access.",
        "No final predictive model approval.",
        "No physical model release.",
        "No Controller B actuation.",
        "No online shadow deployment.",
        "No network or hardware commands.",
        "No invented qualified PZEM evidence.",
        "No promotion of synthetic AP to physical evidence.",
        "No known future-feature or controller-action leakage; causal probes are "
        "audited, but model-level shortcut attribution is not established.",
        "No probability wording without real calibration support.",
        "No arbitrary hyperparameter sweep.",
        "No deep-model implementation without a justified GO.",
        "No W10 registry mutation.",
        "No W11-W14 history rewriting.",
        "No modifications to A/C/D code or evidence.",
        "No canonical-document rewrites.",
        "No new infrastructure or model-registry service.",
        "No AGENTS.md, .opencode files or agent-session reports in the repository.",
        "No merge or signoff actions.",
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ColdGuard W15 A3 electrical/applied-state ablation and synthetic "
            "model candidate.  Synthetic results are software controls, never "
            "physical evidence."
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
    parser.add_argument("--w13-manifest", default="reports/W13/horizon-manifest-W13.json")
    parser.add_argument("--w12-manifest", default="reports/W12/w12-manifest.json")
    parser.add_argument(
        "--w14-manifest", default="reports/W14/w14-manifest.json"
    )
    parser.add_argument("--out", default="reports/W15")
    parser.add_argument("--repository-revision", default=None)
    args = parser.parse_args(argv)

    ml_root = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_dir = out_dir / "model"
    revision = args.repository_revision or _git_revision(ml_root)

    registry = load_registry(args.feature_registry)
    config = load_benchmark_config(args.config, registry)
    fixture = build_expanded_w11_fixture()
    views = build_a3_views(registry, config)
    validate_a3_views(views, registry, config)

    w13_path = Path(args.w13_manifest)
    w12_path = Path(args.w12_manifest)
    w14_path = Path(args.w14_manifest)
    w13_manifest = _load_json(w13_path)
    w12_manifest = _load_json(w12_path)
    w14_manifest = _load_json(w14_path)
    w13_verdicts = w13_manifest.get("scientific_verdicts", {})
    w12_verdicts = w12_manifest.get("scientific_verdicts", {})
    w14_calibration = w14_manifest.get("calibration", {}).get("decision", {})
    if int(w13_manifest.get("reconciliation", {}).get("predictive_eligible_runs", 0)) != 0:
        raise W15Error(
            "live W13 evidence reports predictive-eligible real runs; W15 must be "
            "re-evaluated instead of reusing the synthetic-only admission path"
        )
    if w13_verdicts.get("PRIMARY_HORIZON_FROZEN") != "NOT_FROZEN":
        raise W15Error("W13 primary horizon unexpectedly changed")
    if w12_verdicts.get("GATE_G3") != "NO-GO / FIX DATA":
        raise W15Error("W12 Gate G3 unexpectedly changed")
    if w14_calibration.get("decision") != RISK_SCORE_ONLY:
        raise W15Error("W14 calibration decision unexpectedly changed")
    if w13_verdicts.get("LOCKED_TEST") != "UNTOUCHED":
        raise W15Error("W13 locked-test verdict unexpectedly changed")

    datasets = {
        arm: build_ablation_dataset(fixture, registry, config, view)
        for arm, view in views.items()
    }
    assert_matched_population(*datasets.values())

    results: dict[str, Any] = {}
    for arm, view in views.items():
        with tempfile.TemporaryDirectory(prefix=f"coldguard-w15-{arm.lower()}-") as tmp:
            result, _ = run_ablation_arm(
                fixture, registry, config, view, scaffold_dir=Path(tmp)
            )
        results[arm] = result

    for arm, view in views.items():
        result = results[arm]
        if tuple(result.feature_ids) != view.feature_ids:
            raise W15Error(f"{arm} result feature identity drifted")
        if any(sample.partition == "test" for sample in result.labeled.samples):
            raise W15Error(f"{arm} contains a locked-test sample")
        if any(run_id in fixture.split.test_runs for run_id in result.labeled.run_ids):
            raise W15Error(f"{arm} contains a locked-test run")
    if not all(
        set(fold.train_groups).isdisjoint(fold.validation_groups)
        for result in results.values()
        for fold in result.cv.folds
    ):
        raise W15Error("a grouped fold shares groups between train and validation")

    scenario_by_run = {
        trajectory.run_id: trajectory.scenario_id
        for trajectory in fixture.development_trajectories
        if trajectory.run_id is not None
    }
    electrical_diagnostics = electrical_feature_diagnostics(
        datasets["A3B"], views["A3B"], scenario_by_run=scenario_by_run
    )
    invariance = electrical_block_invariance(fixture, registry, views["A3B"])

    probe_trajectory = fixture.development_trajectories[0]
    probe_group = fixture.split.group_of[probe_trajectory.run_id]
    probe_partition = fixture.split.partition_of(probe_trajectory.run_id)
    probe_anchor_index = 40
    adversarial = {
        "future_power_and_applied_mutation_isolated": {
            arm: future_isolation_probe(
                probe_trajectory,
                registry,
                view,
                group_id=probe_group,
                partition=probe_partition,
                anchor_index=probe_anchor_index,
            )
            for arm, view in views.items()
        },
        "applied_transition_after_anchor_isolated": {
            arm: transition_after_anchor_probe(
                probe_trajectory,
                registry,
                view,
                group_id=probe_group,
                partition=probe_partition,
                anchor_index=probe_anchor_index,
            )
            for arm, view in views.items()
        },
        "unknown_electrical_never_zero_or_valid": unknown_electrical_probe(
            probe_trajectory,
            registry,
            views["A3B"],
            group_id=probe_group,
            partition=probe_partition,
            start_index=60,
        ),
    }
    reset_trajectory, _ = build_trajectory(
        "W15-COUNTER-RESET",
        scenario="S2",
        seed=701,
        duration_s=120.0,
        door_start_s=40.0,
        door_duration_s=20.0,
        critical_offsets_s=(100.0,),
        counter_reset_at_s=60.0,
    )
    adversarial["counter_reset_refused"] = counter_reset_probe(
        reset_trajectory,
        registry,
        views["A3B"],
        group_id="W15-PAIR-X",
        partition="train",
        reset_anchor_s=60.0,
    )
    adversarial["electrical_block_run_invariance"] = invariance
    adversarial["scientific_class"] = SYNTHETIC_SOFTWARE_CONTROL
    if not all(
        adversarial["future_power_and_applied_mutation_isolated"][arm]
        for arm in views
    ):
        raise W15Error("a future mutation changed a past anchor")
    if not all(
        adversarial["applied_transition_after_anchor_isolated"][arm] for arm in views
    ):
        raise W15Error("an applied transition after the anchor changed a past anchor")
    if not all(
        adversarial["unknown_electrical_never_zero_or_valid"][key]
        for key in (
            "pzem_features_missing_after_unknown",
            "pzem_never_zero_or_valid",
        )
    ):
        raise W15Error("UNKNOWN electrical quality was promoted to a value")
    if not all(
        adversarial["counter_reset_refused"][key]
        for key in (
            "counter_present_before_reset",
            "counter_missing_after_reset",
            "reset_reason_recorded",
            "no_negative_counter_value",
        )
    ):
        raise W15Error("counter reset handling is not fail-closed")

    paired = paired_fold_comparison(results["A3A"], results["A3B"])
    summaries = {
        arm: arm_summary(results[arm], views[arm]) for arm in views
    }
    support_rows = run_support(datasets["A3A"])
    fold_rows = [
        {**row, "arm_id": arm}
        for arm in ("A3A", "A3B")
        for row in fold_metric_rows(results[arm])
    ]
    provenance = [
        {**row, "arm_id": arm, "view_id": views[arm].view_id}
        for arm in ("A3A", "A3B")
        for row in provenance_rows(views[arm], registry)
    ]
    electrical_audit = electrical_provenance_rows(registry)

    artifact_samples = list(datasets["A3B"].samples)
    model = fit_final_candidate(
        artifact_samples, config, views["A3B"].feature_ids
    )
    inspection = compute_model_inspection(model, views["A3B"].feature_ids)
    second_model = fit_final_candidate(
        artifact_samples, config, views["A3B"].feature_ids
    )
    deterministic_in_process = native_model_bytes(model) == native_model_bytes(
        second_model
    )
    probe_matrix, _ = feature_matrix(artifact_samples[:5], views["A3B"].feature_ids)
    files = save_native_models(model, model_dir, probe_matrix=probe_matrix)
    expected_scores = model.predict_proba(probe_matrix)[:, 1]
    fresh = verify_fresh_process_parity(
        model_path=model_dir / "model.ubj",
        probe_matrix=probe_matrix,
        expected_scores=expected_scores,
    )
    probe_parity = {**files, **fresh}
    training_population = {
        "run_count": len(datasets["A3B"].run_ids),
        "sample_count": len(artifact_samples),
        "positive": datasets["A3B"].positive_count,
        "negative": datasets["A3B"].negative_count,
        "development_only": True,
        "locked_test_used": False,
    }
    validation_evidence = {
        "protocol": "W11 grouped CV, 4 folds, seed 42, A3B arm",
        "oof_ap": summaries["A3B"]["oof_ap"],
        "fold_ap": summaries["A3B"]["strategy_fold_ap_values"],
        "event_summary": _fold_event_summary(results["A3B"]),
        "scientific_class": SYNTHETIC_SOFTWARE_CONTROL,
        "not_physical_evidence": True,
    }
    artifact_manifest = build_model_manifest(
        files=files,
        registry=registry,
        config=config,
        ordered_feature_ids=views["A3B"].feature_ids,
        training_dataset_id=fixture.dataset_id,
        training_population=training_population,
        validation_evidence=validation_evidence,
        training_code_revision=revision,
        probe_parity=probe_parity,
        deterministic_in_process=deterministic_in_process,
        model_inspection=inspection,
    )
    artifact_manifest_path = model_dir / "model-manifest-W15.json"
    artifact_manifest_payload = _json(artifact_manifest).encode("utf-8")
    artifact_manifest_path.write_bytes(artifact_manifest_payload)

    hyperparameter = _hyperparameter_candidate(
        config, registry, fixture, views["A3B"].feature_ids
    )
    hyperparameter_payload = _json(hyperparameter).encode("utf-8")

    artifacts: dict[str, bytes] = {
        "A3-support-W15.csv": _csv(
            support_rows,
            ("run_id", "group_id", "partition", "anchors", "positive", "negative"),
        ).encode("utf-8"),
        "A3-fold-metrics-W15.csv": _csv(
            fold_rows,
            (
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
            ),
        ).encode("utf-8"),
        "A3-arm-summary-W15.csv": _csv(
            [
                {
                    **summaries[arm],
                    "oof_ap": json.dumps(summaries[arm]["oof_ap"], sort_keys=True),
                    "strategy_fold_ap_values": json.dumps(
                        summaries[arm]["strategy_fold_ap_values"], sort_keys=True
                    ),
                }
                for arm in ("A3A", "A3B")
            ],
            (
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
            ),
        ).encode("utf-8"),
        "A3-paired-folds-W15.csv": _csv(
            [{**row, "component": "A3"} for row in paired],
            (
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
            ),
        ).encode("utf-8"),
        "A3-feature-provenance-W15.csv": _csv(
            provenance,
            (
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
            ),
        ).encode("utf-8"),
        "A3-electrical-audit-W15.csv": _csv(
            electrical_audit,
            (
                "feature_id",
                "family",
                "sensor_role",
                "source_field",
                "physical_source_meaning",
                "origin",
                "quality_requirement",
                "source_timestamp_domain",
                "available_at_prediction_time",
                "lookback_rule",
                "missingness_behavior",
                "online_real_availability",
                "leakage_or_shortcut_risk",
                "intended_role",
                "verified_actuation",
                "arm_membership",
            ),
        ).encode("utf-8"),
        "A3-electrical-diagnostics-W15.csv": _csv(
            electrical_diagnostics,
            (
                "feature_id",
                "evaluable_samples",
                "present",
                "missing",
                "present_fraction",
                "min",
                "max",
                "mean",
                "spearman_with_anchor_time",
                "scenario_auc",
                "label_auc_diagnostic",
                "monotonic_nondecreasing_within_runs",
                "diagnostic_only",
            ),
        ).encode("utf-8"),
        "A3-model-inspection-W15.json": _json(inspection).encode("utf-8"),
        "A3-adversarial-probes-W15.json": _json(adversarial).encode("utf-8"),
        "hyperparameter-freeze-candidate-W15.json": hyperparameter_payload,
    }

    population = _population_contract(fixture, datasets["A3A"])
    manifest = {
        "schema": W15_MANIFEST_SCHEMA,
        "layer_version": W15_LAYER_VERSION,
        "generation_base_revision": revision,
        "revision_semantics": "GENERATION_BASE_NOT_DELIVERY_COMMIT",
        "delivery_commit": "NOT_RECORDED_AT_GENERATION",
        "generation_command": (
            "uv run --locked --python 3.12 python scripts/w15-electrical-ablation-W15.py"
        ),
        "generated_at_utc": "NOT_RECORDED_BY_DESIGN",
        "analysis_code_sha256": _analysis_code_sha256(ml_root),
        "scientific_verdicts": _verdicts(),
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
            "fixture_generator": {
                "path": _relative_ml_path(
                    ml_root / "src" / "coldguard_ml" / "feature_fixtures.py", ml_root
                ),
                "file_sha256": _sha256_file(
                    ml_root / "src" / "coldguard_ml" / "feature_fixtures.py"
                ),
            },
            "w12_manifest": {
                "path": _relative_ml_path(w12_path, ml_root),
                "sha256": _sha256_file(w12_path),
                "gate_g3": w12_verdicts.get("GATE_G3"),
            },
            "w13_manifest": {
                "path": _relative_ml_path(w13_path, ml_root),
                "sha256": _sha256_file(w13_path),
                "primary_horizon_frozen": w13_verdicts.get("PRIMARY_HORIZON_FROZEN"),
                "predictive_eligible_runs": w13_manifest.get(
                    "reconciliation", {}
                ).get("predictive_eligible_runs"),
            },
            "w14_manifest": {
                "path": _relative_ml_path(w14_path, ml_root),
                "sha256": _sha256_file(w14_path),
                "calibration_decision": w14_calibration.get("decision"),
            },
            "fixture_dataset_id": fixture.dataset_id,
            "fixture_version": fixture.fixture_version,
            "model_family": "XGBoost",
            "model_params": dict(config.model_params),
            "risk_threshold": config.risk_threshold,
            "score_semantics": config.score_semantics,
        },
        "reference_horizon": {
            "value_s": config.label.horizon_s,
            "status": REFERENCE_HORIZON_STATUS,
            "source": "pre-existing W11 development label candidate; not selected by W15",
            "label_identity": dict(config.label.identity()),
            "primary_horizon_frozen": False,
        },
        "population": population,
        "fold_identity": results["A3A"].cv.to_manifest(),
        "views": {arm: view.to_dict() for arm, view in views.items()},
        "arms": summaries,
        "paired_folds": paired,
        "electrical_audit": {
            "provenance": electrical_audit,
            "diagnostics": electrical_diagnostics,
            "run_invariance": invariance,
            "adversarial_probes": adversarial,
        },
        "prediction_vs_diagnosis": {
            "classification": "SOFTWARE_ONLY_EVIDENCE",
            "prediction_value": "NOT_ESTABLISHED",
            "diagnosis_value": "SOFTWARE_ONLY",
            "track_p_evidence": (
                "synthetic grouped A3 on the W11 fixture only; zero predictive-eligible "
                "real runs; no real impending-critical labels; no physical claim"
            ),
            "track_d_evidence": (
                "contract-level applied-state vs branch-power consistency interface and "
                "software probes only; no empirical real fault labels or detector accuracy"
            ),
        },
        "model_artifact": {
            "manifest": artifact_manifest,
            "manifest_path": _relative_ml_path(artifact_manifest_path, ml_root),
            "manifest_sha256": _sha256_bytes(artifact_manifest_payload),
            "files": {
                name: {
                    "path": _relative_ml_path(model_dir / payload["file"], ml_root),
                    "sha256": payload["sha256"],
                    "bytes": payload["bytes"],
                }
                for name, payload in artifact_manifest["files"].items()
            },
            "fresh_process_reload": fresh,
            "model_bytes_deterministic_in_process": deterministic_in_process,
            "release_eligibility": NON_DEPLOYABLE,
            "primary_format": PRIMARY_FORMAT,
            "probe_tolerance_abs": PROBE_TOLERANCE,
        },
        "hyperparameter_candidate": {
            "status": hyperparameter["status"],
            "artifact": "hyperparameter-freeze-candidate-W15.json",
            "sha256": _sha256_bytes(hyperparameter_payload),
        },
        "deep_model_decision": {
            "decision": "NO-GO",
            "reasons": [
                "zero predictive-eligible real runs",
                "no documented structured temporal failure of XGBoost",
                "no concrete incremental deep-model question",
                "insufficient independent development groups",
                "no time/infrastructure justification in W15",
            ],
            "reopening_conditions": [
                "admissible real grouped development population",
                "XGBoost demonstrably fails a structured temporal behavior",
                "a concrete incremental scientific question with a fair, leakage-safe protocol",
                "defensible dataset sufficiency and implementation time",
            ],
        },
        "verification": {
            "locked_test_untouched": True,
            "test_partition_used": False,
            "w10_registry_schema_sha256": registry.schema_sha256,
            "a3b_reproduces_w11_allowlist": True,
            "a3a_is_a3b_minus_exact_delta": True,
            "tec_hot_side_excluded": True,
            "requested_and_readback_cooling_excluded": True,
            "grouped_folds_disjoint_computed": True,
            "sample_population_identity_sha256": population[
                "sample_identity_sha256"
            ],
            "electrical_future_isolation": True,
            "electrical_unknown_never_zero": True,
            "counter_reset_refused": True,
            "model_native_round_trip": True,
            "fresh_process_reload": True,
            "model_bytes_deterministic_in_process": deterministic_in_process,
            "model_inspection_used_feature_count": inspection["used_feature_count"],
            "model_inspection_dominant_feature": (
                inspection["dominant_feature"] or {}
            ).get("feature_id"),
            "prior_gate_g3_declared": w12_verdicts.get("GATE_G3"),
            "w13_horizon_decision": w13_verdicts.get("HORIZON_DECISION"),
            "w13_primary_horizon_frozen": w13_verdicts.get("PRIMARY_HORIZON_FROZEN"),
            "w14_calibration_decision": w14_calibration.get("decision"),
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
    manifest_name = "w15-manifest.json"
    (out_dir / manifest_name).write_bytes(_json(manifest).encode("utf-8"))
    print(
        "W15 analysis complete: "
        f"A3 OOF AP {summaries['A3A']['oof_ap']} -> {summaries['A3B']['oof_ap']}; "
        f"electrical_run_invariant={invariance['electrical_block_run_invariant']}; "
        f"artifact={artifact_manifest['model_artifact_sha256'][:16]}...; "
        f"deterministic_in_process={deterministic_in_process}; "
        f"artifacts={out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
