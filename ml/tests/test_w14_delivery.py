"""W14 delivery integrity: manifest, hashes, reports and unchanged contracts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "W14"
MANIFEST_PATH = REPORT_DIR / "w14-manifest.json"
MANIFEST_SHA256 = "e4a0263ead067a10df8d23ffc2bb10d6e750c88e515153fd6f637c733077357d"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_required_reports_exist():
    for name in (
        "A1-report.md",
        "A2-report.md",
        "calibration-report.md",
        "AIW-report.md",
    ):
        path = REPORT_DIR / name
        assert path.exists(), name
        assert path.stat().st_size > 1000, name


def test_manifest_is_bound_and_artifact_hashes_match():
    manifest = _manifest()
    assert manifest["schema"] == "coldguard-w14-manifest-v1"
    assert manifest["deterministic"] is True
    assert manifest["generation_base_revision"] == (
        "824a5389c29ade0e56ecef7ef21eb35c2a379a7b"
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
    assert verdicts["SOFTWARE"] == "COMPLETE"
    assert verdicts["A1"] == "SOFTWARE_VERIFIED"
    assert verdicts["A2"] == "SOFTWARE_VERIFIED"
    assert verdicts["CALIBRATION"] == "RISK_SCORE_ONLY"
    assert verdicts["EWT"] == "NOT_ESTIMABLE"
    assert verdicts["AIW"] == "NOT_ESTIMABLE"
    assert verdicts["DELIVERY"] == "PENDING_PUBLICATION"


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


def test_ablation_arms_share_the_same_population_identity():
    manifest = _manifest()
    arms = manifest["arms"]
    assert arms["A1A"]["evaluable_samples"] == arms["A1B"]["evaluable_samples"]
    assert arms["A1A"]["positive"] == arms["A1B"]["positive"]
    assert arms["A2A"]["negative"] == arms["A2B"]["negative"]
    assert manifest["verification"]["sample_population_identity_sha256"] == (
        "6d6d265d03bd664bd808652789c48af3c79a508c01625bc445f5c5c427f4f889"
    )


def test_a1_is_role_correct_and_not_physical():
    report = (REPORT_DIR / "A1-report.md").read_text(encoding="utf-8")
    assert "SOFTWARE_VERIFIED" in report
    assert "NOT_ESTABLISHED" in report
    assert "CHAMBER_CENTER" in report
    assert "TEC_HOT_SIDE" in report
    assert "T1/T3/T4" in report
    assert "SYNTHETIC_SOFTWARE_CONTROL_ONLY" in report
    assert MANIFEST_SHA256 in report
    assert "A1a" in report and "A1b" in report
    assert "A1a single probe (predeclared): `CHAMBER_CENTER` (T1)" in report


def test_a2_truthfully_reports_the_scenario_identification_trap():
    report = (REPORT_DIR / "A2-report.md").read_text(encoding="utf-8")
    assert "SOFTWARE_VERIFIED" in report
    assert "NOT_ESTABLISHED" in report
    assert "UNKNOWN" in report and "never CLOSED" in report
    assert "door_open" in report
    assert "scenario-identification" in report.lower()
    assert "has **not** proven early physical prediction" in report
    assert MANIFEST_SHA256 in report


def test_calibration_decision_is_risk_score_only_with_contract_text():
    report = (REPORT_DIR / "calibration-report.md").read_text(encoding="utf-8")
    assert "RISK_SCORE_ONLY" in report
    assert "not an empirically calibrated probability" in report
    assert "percentage-risk wording" in report
    assert "72% chance" in report  # quoted only as a prohibited example
    assert "CALIBRATION_BLOCKED_NO_REAL_ELIGIBLE_DEVELOPMENT_POPULATION" in report
    assert "Brier" in report
    assert "sigmoid" in report
    assert "isotonic" in report
    assert MANIFEST_SHA256 in report


def test_aiw_report_states_both_not_estimable():
    report = (REPORT_DIR / "AIW-report.md").read_text(encoding="utf-8")
    assert "EWT = NOT_ESTIMABLE" in report
    assert "AIW = NOT_ESTIMABLE" in report
    assert "BLOCKED_BY_MISSING_EVIDENCE" in report
    assert MANIFEST_SHA256 in report


def test_reports_do_not_claim_physical_support_or_probability():
    forbidden = (
        "PHYSICALLY_SUPPORTED",
        "CALIBRATED_PROBABILITY_SUPPORTED as the W14 decision",
        "proven physical superiority",
        "validated probability",
    )
    for name in (
        "A1-report.md",
        "A2-report.md",
        "calibration-report.md",
        "AIW-report.md",
    ):
        text = (REPORT_DIR / name).read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, (name, phrase)


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
    assert manifest["inputs"]["feature_registry"]["file_sha256"] == (
        "f1c716a61c1d5c8eeaf0ff6e9596320c6df0bb47bce11ece0e67c038c72ffdbb"
    )
    assert manifest["inputs"]["model_config"]["file_sha256"] == (
        "01e48a55a116045233fd90da0d79bd0360e201c7ad310b60eb715b7b5009cb7a"
    )


def test_prior_layer_artifacts_are_hash_pinned():
    manifest = _manifest()
    assert _sha256(ROOT / "reports" / "W11" / "benchmark-manifest-W11.json") == (
        "855c5beb55f15c6e5bcd38640ff3a6ff02a41a525bf3f1601722abdeca2d47f0"
    )
    assert _sha256(ROOT / "reports" / "W12" / "benchmark-synthesis-W12.md") == (
        "f13735e35eb30c93232ce27ba25cfb7cff31493d8b7f8e849251cdef4c94492e"
    )
    assert _sha256(ROOT / "reports" / "W12" / "gate-g3-W12.md") == (
        "edf0d8e1740107975851d63ae86904993577c9f86043d2b27989c7120744ce89"
    )
    assert _sha256(ROOT / "reports" / "W13" / "horizon-manifest-W13.json") == (
        "02a76660319f6118900ec54ee3d50fa96968ad14b0a7110f3fdaf1b62417a404"
    )
    gate = (ROOT / "reports" / "W12" / "gate-g3-W12.md").read_text(
        encoding="utf-8"
    )
    assert "NO-GO / FIX DATA" in gate
    assert manifest["verification"]["prior_gate_g3_declared"] == "NO-GO / FIX DATA"


def test_manifest_declares_that_calibration_diagnostics_were_performed():
    inputs = _manifest()["inputs"]
    assert inputs["model_config_calibration_status"] == "NOT_PERFORMED"
    assert inputs["calibration_diagnostics_performed"] is True
    assert inputs["calibration_diagnostics_scientific_class"] == (
        "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    )
    calibration = _manifest()["calibration"]["diagnostics"]
    assert calibration["scientific_class"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    assert calibration["candidate_family"] == ["sigmoid"]


def test_manifest_fold_counts_are_unambiguous():
    for arm in _manifest()["arms"].values():
        assert arm["fold_count"] == 4
        assert arm["strategy_count"] == 2
        assert len(arm["strategy_fold_ap_values"]) == 2
        assert all(
            len(values) == 4 for values in arm["strategy_fold_ap_values"].values()
        )


def test_w13_scientific_decision_is_not_changed():
    w13 = json.loads(
        (ROOT / "reports" / "W13" / "horizon-manifest-W13.json").read_text(
            encoding="utf-8"
        )
    )
    assert w13["scientific_verdicts"]["HORIZON_DECISION"] == (
        "PROVISIONAL_CANDIDATE_ONLY"
    )
    assert w13["scientific_verdicts"]["PRIMARY_HORIZON_FROZEN"] == "NOT_FROZEN"
    assert w13["decision"]["primary_horizon_s"] is None
    assert w13["scientific_verdicts"]["LOCKED_TEST"] == "UNTOUCHED"
    manifest = _manifest()
    assert manifest["inputs"]["w13_manifest"]["sha256"] == _sha256(
        ROOT / "reports" / "W13" / "horizon-manifest-W13.json"
    )
    assert manifest["reference_horizon"]["status"] == (
        "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN"
    )
    assert manifest["reference_horizon"]["primary_horizon_frozen"] is False


def test_no_model_or_dataset_binaries_are_committed_in_w14():
    forbidden_suffixes = {".ubj", ".model", ".pkl", ".joblib", ".csv.gz", ".parquet"}
    for path in REPORT_DIR.iterdir():
        assert path.suffix not in forbidden_suffixes, path.name
    assert not (REPORT_DIR / "model-synthetic-smoke.ubj").exists()
    assert not (REPORT_DIR / "datasets").exists()


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


def test_provenance_and_paired_artifacts_have_explicit_scope_columns():
    import csv as _csv

    provenance_header = next(
        _csv.reader(
            (REPORT_DIR / "A1-feature-provenance-W14.csv").open(
                encoding="utf-8", newline=""
            )
        )
    )
    assert "view_source_fields" in provenance_header
    for name, component in (
        ("A1-paired-folds-W14.csv", "A1"),
        ("A2-paired-folds-W14.csv", "A2"),
    ):
        rows = list(
            _csv.DictReader(
                (REPORT_DIR / name).open(encoding="utf-8", newline="")
            )
        )
        assert rows
        assert set(row["component"] for row in rows) == {component}
    assert _sha256(REPORT_DIR / "A1-paired-folds-W14.csv") != _sha256(
        REPORT_DIR / "A2-paired-folds-W14.csv"
    )


def test_calibration_report_has_no_undefined_value_turned_zero():
    summary = json.loads(
        (REPORT_DIR / "calibration-summary-W14.json").read_text(encoding="utf-8")
    )
    assert summary["brier_definition"]["positive_class"].startswith("y=1")
    assert summary["brier_definition"]["scale"].startswith("[0, 1]")
    for fold in summary["folds"]:
        if fold["status"] != "FIT":
            assert fold["raw_brier"] is None
            assert fold["calibrated_brier"] is None
            assert fold["reason"]
    assert summary["pooled_empty_bin_count"] == 3
    assert summary["reliability_interpretable"] is False
    assert summary["perfect_separation"] is True


def test_report_headers_use_the_canonical_status_vocabulary():
    for name in (
        "A1-report.md",
        "A2-report.md",
        "calibration-report.md",
        "AIW-report.md",
    ):
        text = (REPORT_DIR / name).read_text(encoding="utf-8")
        assert re.search(r"\*\*Task:\*\* B-W14-0[1-5]", text), name
        assert "w14-manifest.json" in text, name
