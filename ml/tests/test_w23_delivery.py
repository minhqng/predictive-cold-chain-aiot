"""W23 delivery controls: canonical coverage, scope, narrative and release state.

Adversarial probes F51–F60 plus delivery/manifest structure checks.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
REPORTS = ML_ROOT / "reports" / "W23"
MANIFEST_PATH = REPORTS / "evidence-package-W23.json"
DATASET_CARD = REPORTS / "dataset-card-W23.md"
MODEL_CARD = REPORTS / "model-card-W23.md"
FIGURE_REPORT = REPORTS / "figure-availability-W23.md"
RUNBOOK = REPORTS / "reproducibility-runbook-W23.md"
RECEIPT = REPORTS / "clean-room-replay-W23.md"
DEMO = REPORTS / "demo-defense-W23.md"

PRIOR_ARTIFACTS = {
    "ml/reports/W15/model/model.ubj": "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f",
    "ml/reports/W15/model/model.json": "67eef303104bca00a8a1669dcacf6b7ff08219fff493a99280d27086875f2efd",
    "ml/reports/W15/w15-manifest.json": "3f1a16939e1c16345e9948eb109085d123d3e57a57717132b0ab9c2d89d5eafa",
    "ml/reports/W16/locked-test-manifest-W16.json": "6e7e7f23881785f76463344663e08f0cf626f5ee137aa1f98a99772e1a1fe165",
    "ml/reports/W19/w19-manifest.json": "f3bbae932743b4b71c8e8ed7bbbb5334836353080361aa2746c3950cb989db82",
    "ml/reports/W20/w20-manifest.json": "0d8c2ad1cb846599d3535a74ade65186b388702da59eb4bfb0271dcb5a849ece",
    "ml/reports/W21/w21-manifest.json": "5b78141deca1d3f5fd5e16ac10b3344541261d66b5aaa6e49bb3169758fae2c3",
    "ml/reports/W22/w22-manifest.json": "a027dbdda4f36de9cda87516719fe0e2aeb92076d00b67651934a50023bd01e2",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _norm(path: Path) -> str:
    lines = [line.lstrip("> ").rstrip() for line in _text(path).splitlines()]
    return " ".join(" ".join(lines).split())


def _narrative() -> str:
    text = _norm(DEMO)
    start = text.index("I’m Member B.")
    end = text.index("## B. Claim/evidence defense card")
    return text[start:end]


def test_reports_and_manifest_exist():
    expected = {
        "dataset-card-W23.md",
        "model-card-W23.md",
        "figure-availability-W23.md",
        "reproducibility-runbook-W23.md",
        "clean-room-replay-W23.md",
        "demo-defense-W23.md",
        "evidence-package-W23.json",
    }
    assert {path.name for path in REPORTS.iterdir() if path.is_file()} >= expected


def test_manifest_schema_and_report_bindings():
    manifest = _manifest()
    assert manifest["schema"] == "coldguard-w23-evidence-package-v1"
    assert manifest["package_id"] == "coldguard-b-w23-evidence-package"
    for name, expected in manifest["reports"].items():
        assert _sha(REPORTS / name) == expected, name
    assert MANIFEST_PATH.name not in manifest["reports"]


def test_canonical_coverage_b_w23_01_to_05():
    manifest = _manifest()
    coverage = {row["requirement"]: row for row in manifest["canonical_coverage"]}
    assert set(coverage) == {
        "B-W23-01",
        "B-W23-02",
        "B-W23-03",
        "B-W23-04",
        "B-W23-05",
    }
    for requirement, row in coverage.items():
        assert row["artifact"].startswith("ml/reports/W23/"), requirement
        assert row["status"] in {"VERIFIED", "PARTIAL", "BLOCKED"}
        assert row["source_provenance"]
        assert row["verification_method"]
        assert row["software_result"]
        assert row["scientific_limitation"]
    assert coverage["B-W23-01"]["status"] == "VERIFIED"
    assert coverage["B-W23-02"]["status"] == "VERIFIED"
    assert coverage["B-W23-03"]["status"] == "VERIFIED"
    assert coverage["B-W23-04"]["status"] == "PARTIAL"
    assert coverage["B-W23-05"]["status"] == "VERIFIED"


def test_scientific_status_block_is_honest():
    status = _manifest()["scientific_status"]
    assert status["SOFTWARE_EVIDENCE_PACKAGE"] == "COMPLETE"
    assert status["SCIENTIFIC_RESULT_PACKAGE"] == "INCOMPLETE"
    assert status["W16_LOCKED_TEST"] == "NOT_OPENED"
    assert status["W20_PHYSICAL_AB_ANALYSIS"] == "NOT_RUN"
    assert status["G4"] == "NOT_READY"
    assert status["G5"] == "NOT_ESTABLISHED"
    assert status["B_W23_03_FINAL_PHYSICAL_FIGURES"] == "WITHHELD"
    assert status["B_W23_04_INDEPENDENT_TEAM_MEMBER_REPLAY"] == "PENDING"
    assert status["DELIVERY"] == "PENDING_PUBLICATION"


def test_model_card_has_all_required_sections():
    text = _text(MODEL_CARD)
    required = (
        "Artifact identity and native format",
        "Ordered feature schema and hash",
        "Model configuration and dependency versions",
        "Training dataset and eligibility class",
        "Run/group counts and independent units",
        "Target definition and horizon status",
        "Operating threshold and persistence",
        "Calibration and score interpretation",
        "Existing grouped CV metrics and evidence class",
        "A1/A2/A3 findings",
        "Model inspection and shortcut risks",
        "Offline/online parity evidence",
        "Robustness and degraded-input limitations",
        "Intended use",
        "Prohibited use",
        "Release gates not yet satisfied",
        "Exact artifact/source checksums",
    )
    for heading in required:
        assert heading in text, heading


def test_dataset_card_has_all_required_sections():
    text = _text(DATASET_CARD)
    required = (
        "Dataset identities",
        "Provenance",
        "Independent units",
        "Split manifest",
        "Target and label",
        "Feature contract",
        "Invalidations and limitations",
        "Disposition",
    )
    for heading in required:
        assert heading in text, heading


def test_demo_script_fits_two_minutes():
    text = _narrative()
    words = re.findall(r"[A-Za-z0-9’'\-.]+", text)
    assert len(words) <= 300, f"script has {len(words)} words"
    assert len(words) / 150 * 60 < 120, "script exceeds two minutes at 150 wpm"


def test_dataset_card_covers_doc03_section_126_fields():
    text = _norm(DATASET_CARD)
    for field in (
        "Purpose and coverage",
        "Date range",
        "Scenarios",
        "Sampling cadence",
        "Invalid / aborted attempts",
    ):
        assert field in text, field


def test_prior_layers_remain_byte_unchanged():
    manifest = _manifest()
    bound = {entry["path"]: entry["sha256"] for entry in manifest["sources"]}
    for relative, expected in PRIOR_ARTIFACTS.items():
        assert bound[relative] == expected, relative
        assert _sha(REPO_ROOT / relative) == expected, relative


def test_no_model_feature_threshold_or_policy_change():
    manifest = _manifest()
    bound = {entry["path"]: entry["sha256"] for entry in manifest["sources"]}
    assert bound["ml/feature-registry-v1.yaml"] == (
        "f1c716a61c1d5c8eeaf0ff6e9596320c6df0bb47bce11ece0e67c038c72ffdbb"
    )
    assert bound["ml/xgb-v1-config.yaml"] == (
        "01e48a55a116045233fd90da0d79bd0360e201c7ad310b60eb715b7b5009cb7a"
    )
    assert not list((ML_ROOT / "reports" / "W15").glob("model-rc"))
    assert not list((ML_ROOT / "src" / "coldguard_ml").glob("w23_*model*"))
    assert not list((ML_ROOT / "scripts").glob("w23-*train*"))


def test_locked_boundaries_remain_closed():
    manifest = _manifest()
    assert all(
        entry["opens_locked_outcome"] is False for entry in manifest["sources"]
    )
    w16 = json.loads(
        (ML_ROOT / "reports" / "W16" / "locked-test-manifest-W16.json").read_text(
            encoding="utf-8"
        )
    )
    assert w16["holdout_opened"] is False
    w20 = json.loads(
        (ML_ROOT / "reports" / "W20" / "w20-manifest.json").read_text(encoding="utf-8")
    )
    assert w20["verdicts"]["W20_ANALYSIS"] == "NOT_AUTHORIZED"
    assert w20["verdicts"]["FINAL_CAMPAIGN"] == "NOT_AUTHORIZED"
    assert w20["verdicts"]["W20_FINAL_ANALYSIS"] == "NOT_RUN"


def test_generation_base_semantics_avoid_circular_revision():
    manifest = _manifest()
    assert manifest["git_source_revision"] == (
        "cf0716df90a1b9a617df0e61166e218a4f263374"
    )
    assert manifest["revision_semantics"] == "GENERATION_BASE_NOT_DELIVERY_COMMIT"
    assert manifest["delivery_commit"] == "NOT_RECORDED_AT_GENERATION"
    assert not re.fullmatch(r"[0-9a-f]{40}", manifest["package_version"])


def test_figure_availability_matches_canonical_requirements():
    manifest = _manifest()
    figures = manifest["figure_availability"]
    assert figures["status"] == "VERIFIED"
    assert len(figures["present"]) == 6
    assert {
        "representative_physical_trajectory",
        "pr_curve",
        "calibration_curve",
        "ewt_aiw",
        "paired_ab_effects",
        "outcome_ci",
    } <= set(figures["required"])
    assert len(figures["withheld"]) == 5
    assert all(relative for relative in figures["present"])


def test_clean_room_receipt_is_complete_and_reproducible():
    receipt = _text(RECEIPT)
    payload = json.loads(
        re.search(r"```json\n(.*?)\n```", receipt, re.DOTALL).group(1)
    )
    assert payload["technical_clean_room_replay"] in {"PASS", "PARTIAL", "FAIL"}
    assert payload["independent_team_member_replay"] == "PENDING"
    assert payload["final_physical_analysis"] == "NOT_AUTHORIZED"
    assert payload["tests"]["failed"] == 0
    assert payload["model_artifact"]["matches_declared_sha256"] is True
    assert payload["artifact_lock"]["sha256"] == _sha(ML_ROOT / "uv.lock")
    assert payload["audit"]["runs"] >= 2
    assert payload["audit"]["deterministic"] is True


# --- F. Narrative and release integrity ------------------------------------


def test_f51_demo_does_not_claim_a_physically_frozen_60s_horizon():
    # Probe 51.
    text = _narrative()
    assert "That horizon is not physically frozen" in text
    assert "60 seconds early" not in text
    assert "physically frozen 60" not in text


def test_f52_demo_does_not_claim_measured_early_prediction_from_synthetic_ap():
    # Probe 52.
    text = _narrative()
    assert "cannot claim a measured early-warning time" in text
    assert "synthetic ap of one is a software control" in text.lower()
    lowered = text.lower()
    assert "measured early prediction" not in lowered


def test_f53_demo_does_not_call_risk_score_a_probability():
    # Probe 53.
    text = _narrative()
    assert "risk score, not a calibrated probability" in text
    assert "`risk_score` is a probability" in _norm(DEMO)  # listed as forbidden


def test_f54_demo_does_not_claim_controller_b_physical_benefit():
    # Probe 54.
    text = _narrative()
    assert "Nothing yet" in text
    assert "not a Controller B benefit" in text
    assert "reduced thermal exposure by" in _norm(DEMO)  # listed as forbidden


def test_f55_demo_does_not_invent_a_final_p_value():
    # Probe 55.
    text = _norm(DEMO)
    assert "no final physical p-value" in text
    assert "invented p-value" in text
    assert not re.search(r"p\s*=\s*0\.0", text)


def test_f56_demo_does_not_claim_g4_g5_acceptance():
    # Probe 56.
    text = _norm(DEMO)
    assert "G4/G5 are accepted" in text  # listed as forbidden
    manifest = _manifest()
    assert manifest["scientific_status"]["G4"] == "NOT_READY"
    assert manifest["scientific_status"]["G5"] == "NOT_ESTABLISHED"


def test_f57_demo_does_not_claim_actuator_verification():
    # Probe 57.
    text = _norm(DEMO)
    assert "actuator output stage compiled out" in text
    assert "Actuator verification passed" in text  # listed as forbidden
    w21 = json.loads(
        (ML_ROOT / "reports" / "W21" / "w21-manifest.json").read_text(encoding="utf-8")
    )
    assert w21["session_identity"]["output_stage"] == "COMPILED_OUT"
    assert w21["session_identity"]["tec_actuation"] == "NONE"


def test_f58_demo_does_not_claim_full_team_rehearsals():
    # Probe 58.
    text = _norm(DEMO)
    assert "TEAM REHEARSAL STATUS = NOT_EVIDENCED" in text
    assert "NOT_EVIDENCED" in text
    assert "three full team rehearsals" in text.lower()


def test_f59_w23_does_not_change_model_threshold_or_feature_code():
    # Probe 59.
    manifest = _manifest()
    bound = {entry["path"]: entry["sha256"] for entry in manifest["sources"]}
    assert bound["ml/reports/W15/model/model.ubj"] == PRIOR_ARTIFACTS[
        "ml/reports/W15/model/model.ubj"
    ]
    assert bound["ml/feature-registry-v1.yaml"] == (
        "f1c716a61c1d5c8eeaf0ff6e9596320c6df0bb47bce11ece0e67c038c72ffdbb"
    )
    assert not (ML_ROOT / "reports" / "W23" / "model").exists()


def test_f60_w23_does_not_open_w16_or_w20_analysis_boundary():
    # Probe 60.
    manifest = _manifest()
    w16_hash = _sha(ML_ROOT / "reports" / "W16" / "locked-test-manifest-W16.json")
    w20_hash = _sha(ML_ROOT / "reports" / "W20" / "w20-manifest.json")
    bound = {entry["path"]: entry["sha256"] for entry in manifest["sources"]}
    assert bound["ml/reports/W16/locked-test-manifest-W16.json"] == w16_hash
    assert bound["ml/reports/W20/w20-manifest.json"] == w20_hash
    assert all(entry["opens_locked_outcome"] is False for entry in manifest["sources"])
    assert manifest["scientific_status"]["W16_LOCKED_TEST"] == "NOT_OPENED"
    assert manifest["scientific_status"]["W20_PHYSICAL_AB_ANALYSIS"] == "NOT_RUN"
