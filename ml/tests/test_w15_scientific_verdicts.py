"""W15 scientific-verdict matrix across W12/W13/W14/W15 evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "W15"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_w15_verdict_matrix_is_explicit():
    verdicts = _json(REPORT_DIR / "w15-manifest.json")["scientific_verdicts"]
    assert verdicts["A3"] == "SOFTWARE_VERIFIED"
    assert verdicts["PREDICTION_VALUE"] == "NOT_ESTABLISHED"
    assert verdicts["DIAGNOSIS_VALUE"] == "SOFTWARE_ONLY"
    assert verdicts["HYPERPARAMETER_CANDIDATE"] == "DECLARED"
    assert verdicts["MODEL_ARTIFACT"] == "SYNTHETIC_NON_DEPLOYABLE"
    assert verdicts["CALIBRATION"] == "RISK_SCORE_ONLY"
    assert verdicts["DEEP_MODEL"] == "NO-GO"


def test_synthetic_ap_cannot_establish_real_a3_benefit():
    manifest = _json(REPORT_DIR / "w15-manifest.json")
    assert manifest["scientific_class"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    assert manifest["arms"]["A3A"]["scientific_class"] == (
        "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    )
    assert manifest["arms"]["A3B"]["scientific_class"] == (
        "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    )
    assert manifest["prediction_vs_diagnosis"]["prediction_value"] == (
        "NOT_ESTABLISHED"
    )
    report = (REPORT_DIR / "A3-report.md").read_text(encoding="utf-8")
    assert "cannot estimate a real" in report
    assert "not a predictive-effect estimate" in report
    assert "evidence of feature equivalence" in report


def test_diagnosis_evidence_is_not_predictive_evidence():
    manifest = _json(REPORT_DIR / "w15-manifest.json")
    classification = manifest["prediction_vs_diagnosis"]
    assert classification["classification"] == "SOFTWARE_ONLY_EVIDENCE"
    assert classification["diagnosis_value"] == "SOFTWARE_ONLY"
    assert "no empirical real fault labels" in classification["track_d_evidence"]
    report = (REPORT_DIR / "prediction-vs-diagnosis-W15.md").read_text(
        encoding="utf-8"
    )
    assert "Diagnosis success would not automatically improve" in report


def test_hyperparameter_candidate_is_not_physical_acceptance():
    candidate = _json(REPORT_DIR / "hyperparameter-freeze-candidate-W15.json")
    assert candidate["status"] == "DEVELOPMENT_CONFIG_CANDIDATE"
    assert "PHYSICALLY_VALIDATED_MODEL" in candidate["explicitly_not"]
    assert "APPROVED_RELEASE_MODEL" in candidate["explicitly_not"]
    assert "W16_LOCKED_TEST_READY" in candidate["explicitly_not"]
    assert candidate["reference_horizon"]["primary_horizon_frozen"] is False


def test_w13_primary_horizon_remains_unselected():
    w13 = _json(ROOT / "reports" / "W13" / "horizon-manifest-W13.json")
    assert w13["scientific_verdicts"]["PRIMARY_HORIZON_FROZEN"] == "NOT_FROZEN"
    assert w13["decision"]["primary_horizon_s"] is None
    w15 = _json(REPORT_DIR / "w15-manifest.json")
    assert w15["reference_horizon"]["status"] == (
        "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN"
    )
    assert w15["reference_horizon"]["primary_horizon_frozen"] is False


def test_w14_calibration_remains_risk_score_only():
    w14 = _json(ROOT / "reports" / "W14" / "w14-manifest.json")
    assert w14["scientific_verdicts"]["CALIBRATION"] == "RISK_SCORE_ONLY"
    assert w14["calibration"]["decision"]["decision"] == "RISK_SCORE_ONLY"
    w15 = _json(REPORT_DIR / "w15-manifest.json")
    assert w15["scientific_verdicts"]["CALIBRATION"] == "RISK_SCORE_ONLY"
    assert w15["model_artifact"]["manifest"]["calibration_status"] == (
        "RISK_SCORE_ONLY"
    )


def test_w12_gate_g3_remains_no_go_fix_data():
    w12 = _json(ROOT / "reports" / "W12" / "w12-manifest.json")
    assert w12["scientific_verdicts"]["GATE_G3"] == "NO-GO / FIX DATA"
    assert w12["scientific_verdicts"]["REAL_GROUPED_BENCHMARK"] == (
        "NOT_ESTABLISHED"
    )
    w15 = _json(REPORT_DIR / "w15-manifest.json")
    assert w15["verification"]["prior_gate_g3_declared"] == "NO-GO / FIX DATA"


def test_real_ewt_and_aiw_remain_non_estimable():
    w12 = _json(ROOT / "reports" / "W12" / "w12-manifest.json")
    w13 = _json(ROOT / "reports" / "W13" / "horizon-manifest-W13.json")
    assert w12["scientific_verdicts"]["REAL_EWT"] == "NOT_ESTIMABLE"
    assert w12["scientific_verdicts"]["REAL_AIW"] == "NOT_ESTIMABLE"
    assert w13["scientific_verdicts"]["REAL_EWT"] == "NOT_ESTIMABLE"
    assert w13["scientific_verdicts"]["REAL_AIW"] == "NOT_ESTIMABLE"


def test_w16_locked_test_stays_untouched():
    w15 = _json(REPORT_DIR / "w15-manifest.json")
    assert w15["population"]["test_partition_used"] is False
    assert w15["verification"]["locked_test_untouched"] is True
    assert w15["verification"]["test_partition_used"] is False
    w13 = _json(ROOT / "reports" / "W13" / "horizon-manifest-W13.json")
    assert w13["scientific_verdicts"]["LOCKED_TEST"] == "UNTOUCHED"
    assert w15["verification"]["w13_primary_horizon_frozen"] == "NOT_FROZEN"


def test_artifact_is_not_w16_locked_test_ready():
    artifact = _json(REPORT_DIR / "w15-manifest.json")["model_artifact"]
    assert artifact["release_eligibility"] == "NON_DEPLOYABLE_CANDIDATE"
    detail = artifact["manifest"]
    assert detail["release_eligibility"] == "NON_DEPLOYABLE_CANDIDATE"
    assert detail["data_evidence_class"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    candidate = _json(REPORT_DIR / "hyperparameter-freeze-candidate-W15.json")
    assert "W16_LOCKED_TEST_READY" in candidate["explicitly_not"]


def test_no_deep_learning_dependency_was_added():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for dependency in ("torch", "tensorflow", "keras", "jax"):
        assert dependency not in pyproject
    assert not any(
        "torch" in path.name.lower() or "tensorflow" in path.name.lower()
        for path in (ROOT / "src" / "coldguard_ml").iterdir()
    )
