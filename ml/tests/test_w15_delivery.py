"""W15 delivery integrity: manifest, hashes, reports and unchanged contracts."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "W15"
MANIFEST_PATH = REPORT_DIR / "w15-manifest.json"
MANIFEST_SHA256 = "3f1a16939e1c16345e9948eb109085d123d3e57a57717132b0ab9c2d89d5eafa"
MODEL_SHA256 = "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_required_reports_exist():
    for name in (
        "A3-report.md",
        "prediction-vs-diagnosis-W15.md",
        "hyperparameter-freeze-candidate-W15.md",
        "model-card-W15.md",
        "deep-model-decision-W15.md",
    ):
        path = REPORT_DIR / name
        assert path.exists(), name
        assert path.stat().st_size > 1000, name


def test_manifest_is_bound_and_artifact_hashes_match():
    manifest = _manifest()
    assert manifest["schema"] == "coldguard-w15-manifest-v1"
    assert manifest["deterministic"] is True
    assert manifest["generation_base_revision"] == (
        "9027c469a82859b4eb2dcf5b4d8255bf1f59c641"
    )
    assert manifest["revision_semantics"] == "GENERATION_BASE_NOT_DELIVERY_COMMIT"
    assert manifest["delivery_commit"] == "NOT_RECORDED_AT_GENERATION"
    assert manifest["scientific_class"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    for name, entry in manifest["artifacts"].items():
        path = REPORT_DIR / name
        assert path.exists(), name
        assert _sha256(path) == entry["sha256"], name
    assert _sha256(MANIFEST_PATH) == MANIFEST_SHA256


def test_manifest_verdicts_are_truthful():
    verdicts = _manifest()["scientific_verdicts"]
    assert verdicts == {
        "A3": "SOFTWARE_VERIFIED",
        "CALIBRATION": "RISK_SCORE_ONLY",
        "DEEP_MODEL": "NO-GO",
        "DELIVERY": "PENDING_PUBLICATION",
        "DIAGNOSIS_VALUE": "SOFTWARE_ONLY",
        "HYPERPARAMETER_CANDIDATE": "DECLARED",
        "MODEL_ARTIFACT": "SYNTHETIC_NON_DEPLOYABLE",
        "PREDICTION_VALUE": "NOT_ESTABLISHED",
        "SOFTWARE": "COMPLETE",
    }


def test_population_contract_keeps_the_locked_test_untouched():
    population = _manifest()["population"]
    assert population["test_partition_used"] is False
    assert sorted(population["locked_test_runs"]) == [
        "CG-W11-S1-001",
        "CG-W11-S1-002",
        "CG-W11-S2-001",
        "CG-W11-S2-002",
    ]
    assert not (
        set(population["development_runs"]) & set(population["locked_test_runs"])
    )
    assert population["evaluable_samples"] == 1936
    assert population["positive"] == 480
    assert population["negative"] == 1456
    assert population["excluded"] == {"CENSORED": 960}
    assert population["sample_identity_sha256"] == (
        "6d6d265d03bd664bd808652789c48af3c79a508c01625bc445f5c5c427f4f889"
    )


def test_a3_arms_are_controlled_and_saturated():
    manifest = _manifest()
    assert manifest["arms"]["A3A"]["feature_count"] == 20
    assert manifest["arms"]["A3B"]["feature_count"] == 28
    for arm in ("A3A", "A3B"):
        assert manifest["arms"][arm]["evaluable_samples"] == 1936
        assert manifest["arms"][arm]["positive"] == 480
        assert manifest["arms"][arm]["negative"] == 1456
        assert manifest["arms"][arm]["fold_count"] == 4
        assert manifest["arms"][arm]["fit_folds"] == 8
        assert manifest["arms"][arm]["oof_ap"] == {
            "UNWEIGHTED": 1.0,
            "TRAIN_FOLD_CLASS_WEIGHT": 1.0,
        }
    assert len(manifest["paired_folds"]) == 8
    assert all(row["delta_ap_b_minus_a"] == 0.0 for row in manifest["paired_folds"])
    assert all(row["missed_events_a"] == 0 for row in manifest["paired_folds"])
    assert all(row["missed_events_b"] == 0 for row in manifest["paired_folds"])


def test_a3b_is_the_frozen_allowlist_and_a3a_is_the_exact_delta():
    manifest = _manifest()
    assert manifest["views"]["A3B"]["feature_count"] == 28
    assert manifest["views"]["A3A"]["feature_count"] == 20
    b_ids = [feature["feature_id"] for feature in manifest["views"]["A3B"]["features"]]
    a_ids = [feature["feature_id"] for feature in manifest["views"]["A3A"]["features"]]
    delta = [feature_id for feature_id in b_ids if feature_id not in set(a_ids)]
    assert delta == [
        "applied_cooling",
        "applied_duty",
        "time_since_confirmed_applied_change",
        "cooling_voltage_v",
        "cooling_current_a",
        "cooling_power_w",
        "energy_counter_wh",
        "past_integrated_cooling_energy_wh",
    ]
    assert all(
        feature["family"] not in ("electrical_context", "actuation_context")
        for feature in manifest["views"]["A3A"]["features"]
    )
    assert "requested_cooling" not in b_ids
    assert "readback_cooling" not in b_ids
    assert "T_tec_hot_side_c" not in b_ids


def test_electrical_audit_has_all_eight_features_and_risk_classes():
    rows = list(
        csv.DictReader(
            (REPORT_DIR / "A3-electrical-audit-W15.csv").open(
                encoding="utf-8", newline=""
            )
        )
    )
    assert {row["feature_id"] for row in rows} == {
        "applied_cooling",
        "applied_duty",
        "time_since_confirmed_applied_change",
        "cooling_voltage_v",
        "cooling_current_a",
        "cooling_power_w",
        "energy_counter_wh",
        "past_integrated_cooling_energy_wh",
    }
    for row in rows:
        assert row["available_at_prediction_time"]
        assert row["missingness_behavior"]
        assert row["leakage_or_shortcut_risk"]
        assert row["online_real_availability"].startswith(
            "NOT_ESTABLISHED_FOR_PREDICTIVE_USE"
        )
        assert row["arm_membership"] == "A3B_ONLY"
        assert row["verified_actuation"].startswith("NO")


def test_electrical_diagnostics_show_the_saturated_fixture_limits():
    rows = {
        row["feature_id"]: row
        for row in csv.DictReader(
            (REPORT_DIR / "A3-electrical-diagnostics-W15.csv").open(
                encoding="utf-8", newline=""
            )
        )
    }
    assert len(rows) == 8
    for row in rows.values():
        assert row["diagnostic_only"] == "True"
        assert float(row["scenario_auc"]) == 0.5
    assert float(rows["energy_counter_wh"]["spearman_with_anchor_time"]) == 1.0
    assert rows["energy_counter_wh"]["monotonic_nondecreasing_within_runs"] == "True"


def test_adversarial_probes_all_pass_and_pin_run_invariance():
    probes = json.loads(
        (REPORT_DIR / "A3-adversarial-probes-W15.json").read_text(encoding="utf-8")
    )
    assert all(probes["future_power_and_applied_mutation_isolated"].values())
    assert all(probes["applied_transition_after_anchor_isolated"].values())
    assert probes["unknown_electrical_never_zero_or_valid"][
        "pzem_never_zero_or_valid"
    ]
    assert probes["unknown_electrical_never_zero_or_valid"]["applied_state_still_observed"]
    assert all(probes["counter_reset_refused"].values())
    invariance = probes["electrical_block_run_invariance"]
    assert invariance["electrical_block_run_invariant"] is True
    assert invariance["mismatch_count"] == 0


def test_model_artifact_files_and_manifest_bindings():
    manifest = _manifest()
    artifact = manifest["model_artifact"]
    assert artifact["release_eligibility"] == "NON_DEPLOYABLE_CANDIDATE"
    assert artifact["fresh_process_reload"]["fresh_process_reload_parity"] is True
    assert artifact["fresh_process_reload"]["max_abs_diff"] <= 1e-12
    assert artifact["model_bytes_deterministic_in_process"] is True
    detail = artifact["manifest"]
    assert detail["data_evidence_class"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    assert detail["release_eligibility"] == "NON_DEPLOYABLE_CANDIDATE"
    assert detail["score_semantics"] == "risk_score"
    assert detail["calibration_status"] == "RISK_SCORE_ONLY"
    assert detail["horizon_status"] == (
        "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN"
    )
    assert detail["operating_threshold_status"] == "ILLUSTRATIVE_NOT_FROZEN"
    assert detail["warning_persistence_status"] == "NOT_FROZEN"
    assert detail["model_artifact_sha256"] == MODEL_SHA256
    assert _sha256(REPORT_DIR / "model" / "model.ubj") == MODEL_SHA256
    assert _sha256(REPORT_DIR / "model" / "model.json") == (
        "67eef303104bca00a8a1669dcacf6b7ff08219fff493a99280d27086875f2efd"
    )
    assert _sha256(REPORT_DIR / "model" / "model-manifest-W15.json") == (
        "85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e"
    )
    assert detail["training_population"]["locked_test_used"] is False
    assert detail["ordered_feature_ids"] == [
        feature["feature_id"] for feature in manifest["views"]["A3B"]["features"]
    ]


def test_hyperparameter_candidate_is_declared_and_actual():
    candidate = json.loads(
        (REPORT_DIR / "hyperparameter-freeze-candidate-W15.json").read_text(
            encoding="utf-8"
        )
    )
    assert candidate["status"] == "DEVELOPMENT_CONFIG_CANDIDATE"
    assert candidate["explicitly_not"] == [
        "PHYSICALLY_VALIDATED_MODEL",
        "APPROVED_RELEASE_MODEL",
        "W16_LOCKED_TEST_READY",
    ]
    assert candidate["parameters"]["max_depth"] == 3
    assert candidate["parameters"]["learning_rate"] == 0.05
    assert candidate["parameters"]["n_estimators"] == 60
    assert candidate["parameters"]["random_state"] == 42
    assert candidate["imbalance"]["artifact_strategy"] == "UNWEIGHTED"
    assert candidate["parameters"]["scale_pos_weight"] == 1.0
    assert candidate["config_version"] == "coldguard-xgb-v1-development-v1"
    assert candidate["config_sha256"] == (
        "4369f39f44a1d3b4c27ec6dee8c47a7dc1fdfd3c5416a7660dd6481ee1f71a84"
    )
    assert candidate["reference_horizon"]["primary_horizon_frozen"] is False
    assert candidate["output_semantics"] == "risk_score"
    assert candidate["calibration_status"] == "RISK_SCORE_ONLY"
    assert candidate["search_performed_in_w15"] is False
    assert set(candidate["parameter_sources"]) >= set(candidate["parameters"])


def test_model_inspection_discloses_the_door_time_rule():
    inspection = json.loads(
        (REPORT_DIR / "A3-model-inspection-W15.json").read_text(encoding="utf-8")
    )
    assert inspection["diagnostic_only"] is True
    assert inspection["tree_count"] == 60
    assert inspection["total_split_count"] == 60
    assert inspection["used_feature_ids"] == ["time_since_open"]
    assert inspection["unused_feature_count"] == 27
    assert inspection["dominant_feature"]["feature_id"] == "time_since_open"
    assert inspection["dominant_feature"]["split_count"] == 60
    assert inspection["dominant_feature_split_thresholds"] == [60.0]
    assert len(inspection["features"]) == 28
    from xgboost import XGBClassifier

    from coldguard_ml.w15_artifact import compute_model_inspection

    model = XGBClassifier()
    model.load_model(str(REPORT_DIR / "model" / "model.ubj"))
    feature_ids = _manifest()["views"]["A3B"]["features"]
    recomputed = compute_model_inspection(
        model, [feature["feature_id"] for feature in feature_ids]
    )
    assert recomputed == inspection


def test_analysis_code_hash_covers_the_fixture_generator():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "w15_driver", ROOT / "scripts" / "w15-electrical-ablation-W15.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    manifest = _manifest()
    assert module._analysis_code_sha256(ROOT) == manifest["analysis_code_sha256"]
    assert manifest["inputs"]["fixture_generator"]["file_sha256"] == _sha256(
        ROOT / "src" / "coldguard_ml" / "feature_fixtures.py"
    )


def test_delivered_artifact_fresh_process_parity():
    import numpy as np

    from coldguard_ml.feature_registry import load_registry
    from coldguard_ml.w14_ablation import build_ablation_dataset
    from coldguard_ml.w15_ablation import build_a3_views
    from coldguard_ml.w15_artifact import (
        load_guarded_artifact,
        verify_fresh_process_parity,
    )
    from coldguard_ml.xgb_benchmark import (
        build_expanded_w11_fixture,
        feature_matrix,
        load_benchmark_config,
    )

    registry = load_registry(ROOT / "feature-registry-v1.yaml")
    config = load_benchmark_config(ROOT / "xgb-v1-config.yaml", registry)
    fixture = build_expanded_w11_fixture()
    views = build_a3_views(registry, config)
    dataset = build_ablation_dataset(fixture, registry, config, views["A3B"])
    probe, _ = feature_matrix(dataset.samples[:5], views["A3B"].feature_ids)
    manifest = _manifest()["model_artifact"]["manifest"]
    guarded = load_guarded_artifact(
        manifest_path=REPORT_DIR / "model" / "model-manifest-W15.json",
        model_path=REPORT_DIR / "model" / "model.ubj",
        expected_feature_ids=views["A3B"].feature_ids,
        expected_library_version=manifest["model_library_version"],
        expected_feature_schema_hash=manifest["feature_schema_hash"],
        expected_model_config_hash=manifest["model_config_hash"],
    )
    columns = {
        feature_id: probe[:, index]
        for index, feature_id in enumerate(guarded.ordered_feature_ids)
    }
    expected = np.asarray(guarded.predict_risk(columns), dtype=float)
    result = verify_fresh_process_parity(
        model_path=REPORT_DIR / "model" / "model.ubj",
        probe_matrix=probe,
        expected_scores=expected,
    )
    assert result["fresh_process_reload_parity"] is True
    assert result["max_abs_diff"] <= 1e-12


def test_report_markdown_hashes_are_pinned():
    expected = {
        "A3-report.md": "216f84618bd66f29d72853fbab5564f0a076c7d50ce6588cc3f1674f1967a233",
        "prediction-vs-diagnosis-W15.md": "a78ae90d78cce1af74b6a031918967178b8e928106dc3fc6b95e5283cc21e5b7",
        "hyperparameter-freeze-candidate-W15.md": "23979f661ead02e9b4b940e458efba88dd12bc16c738fb893d4e2f12aa44e67a",
        "model-card-W15.md": "1ea2488a9d79693fc80789f2f7a17b69a0cfb917cd408489af3b0fa2ce1be2dc",
        "deep-model-decision-W15.md": "d2d60160cd90c5e2accc2c04660bc078a9becbbfc852bdd0341248de9d478cb7",
    }
    for name, digest in expected.items():
        assert _sha256(REPORT_DIR / name) == digest, name


def test_w10_registry_and_w11_config_are_unchanged():
    manifest = _manifest()
    w11 = json.loads(
        (ROOT / "reports" / "W11" / "benchmark-manifest-W11.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["inputs"]["feature_registry"]["schema_sha256"] == (
        w11["registry_sha256"]
    )
    assert manifest["inputs"]["model_config"]["config_sha256"] == (
        w11["config"]["config_sha256"]
    )
    assert manifest["inputs"]["feature_registry"]["schema_sha256"] == (
        "1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9"
    )
    assert manifest["inputs"]["model_config"]["config_sha256"] == (
        "4369f39f44a1d3b4c27ec6dee8c47a7dc1fdfd3c5416a7660dd6481ee1f71a84"
    )
    assert manifest["inputs"]["feature_registry"]["file_sha256"] == _sha256(
        ROOT / "feature-registry-v1.yaml"
    )
    assert manifest["inputs"]["model_config"]["file_sha256"] == _sha256(
        ROOT / "xgb-v1-config.yaml"
    )


def test_prior_layer_artifacts_are_hash_pinned():
    assert _sha256(ROOT / "reports" / "W11" / "benchmark-manifest-W11.json") == (
        "855c5beb55f15c6e5bcd38640ff3a6ff02a41a525bf3f1601722abdeca2d47f0"
    )
    assert _sha256(ROOT / "reports" / "W12" / "w12-manifest.json") == (
        "ef06f9712203b39c01351ad89a17368574e98a0db6436f842e926b68418073a7"
    )
    assert _sha256(ROOT / "reports" / "W13" / "horizon-manifest-W13.json") == (
        "02a76660319f6118900ec54ee3d50fa96968ad14b0a7110f3fdaf1b62417a404"
    )
    assert _sha256(ROOT / "reports" / "W14" / "w14-manifest.json") == (
        "e4a0263ead067a10df8d23ffc2bb10d6e750c88e515153fd6f637c733077357d"
    )


def test_reports_bind_the_manifest_and_use_the_canonical_vocabulary():
    for name in (
        "A3-report.md",
        "prediction-vs-diagnosis-W15.md",
        "hyperparameter-freeze-candidate-W15.md",
        "model-card-W15.md",
        "deep-model-decision-W15.md",
    ):
        text = (REPORT_DIR / name).read_text(encoding="utf-8")
        assert MANIFEST_SHA256 in text, name
        assert re.search(r"\*\*Task:\*\* B-W15-0[1-6]", text), name
    a3 = (REPORT_DIR / "A3-report.md").read_text(encoding="utf-8")
    assert "SOFTWARE_VERIFIED" in a3
    assert "NOT_ESTABLISHED" in a3
    assert "SYNTHETIC_SOFTWARE_CONTROL_ONLY" in a3
    assert "saturat" in a3.lower()
    assert "run-invariant" in a3
    diagnosis = (REPORT_DIR / "prediction-vs-diagnosis-W15.md").read_text(
        encoding="utf-8"
    )
    assert "SOFTWARE_ONLY_EVIDENCE" in diagnosis
    assert "PREDICTION VALUE:   NOT_ESTABLISHED" in diagnosis
    assert "DIAGNOSIS VALUE:    SOFTWARE_ONLY" in diagnosis
    card = (REPORT_DIR / "model-card-W15.md").read_text(encoding="utf-8")
    assert "NON_DEPLOYABLE_CANDIDATE" in card
    assert "Not approved for" in card
    deep = (REPORT_DIR / "deep-model-decision-W15.md").read_text(encoding="utf-8")
    assert "NO-GO" in deep
    assert "Reopening conditions" in deep


def test_reports_do_not_claim_physical_support_or_probability():
    forbidden = (
        "PHYSICALLY_SUPPORTED",
        "CALIBRATED_PROBABILITY_SUPPORTED as the W15 decision",
        "proven physical superiority",
        "validated probability",
        "72% chance",
        "P(critical within",
    )
    for name in (
        "A3-report.md",
        "prediction-vs-diagnosis-W15.md",
        "hyperparameter-freeze-candidate-W15.md",
        "model-card-W15.md",
        "deep-model-decision-W15.md",
    ):
        text = (REPORT_DIR / name).read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, (name, phrase)


def test_every_csv_artifact_has_real_rows():
    manifest = _manifest()
    for name in manifest["artifacts"]:
        if not name.endswith(".csv"):
            continue
        lines = [
            line
            for line in (REPORT_DIR / name).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) >= 2, name


def test_only_native_model_binaries_are_committed_and_no_pickle():
    binaries = [
        path
        for path in REPORT_DIR.rglob("*")
        if path.is_file() and path.suffix in {".ubj", ".pkl", ".joblib"}
    ]
    assert {path.name for path in binaries} == {"model.ubj"}
    assert (REPORT_DIR / "model" / "model.json").exists()
    assert not any(path.suffix in {".pkl", ".joblib"} for path in binaries)
