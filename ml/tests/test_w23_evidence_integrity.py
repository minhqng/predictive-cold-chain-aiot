"""W23 evidence integrity: manifest bindings, dataset/model card fidelity.

Adversarial probes A1–A10 (evidence identity), B11–B20 (dataset card),
C21–C30 (model card), D31–D40 (figures).
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
MANIFEST_PATH = ML_ROOT / "reports" / "W23" / "evidence-package-W23.json"
SCRIPT = ML_ROOT / "scripts" / "w23-evidence-audit-W23.py"
DATASET_CARD = ML_ROOT / "reports" / "W23" / "dataset-card-W23.md"
MODEL_CARD = ML_ROOT / "reports" / "W23" / "model-card-W23.md"
FIGURE_REPORT = ML_ROOT / "reports" / "W23" / "figure-availability-W23.md"
MODEL_MANIFEST = ML_ROOT / "reports" / "W15" / "model" / "model-manifest-W15.json"
MODEL_INSPECTION = ML_ROOT / "reports" / "W15" / "A3-model-inspection-W15.json"
W11_MANIFEST = ML_ROOT / "reports" / "W11" / "benchmark-manifest-W11.json"
W16_MANIFEST = ML_ROOT / "reports" / "W16" / "locked-test-manifest-W16.json"
W22_PLOT = ML_ROOT / "reports" / "W22" / "test-only-pair-plot-W22.svg"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _norm(path: Path) -> str:
    lines = [line.lstrip("> ").rstrip() for line in _text(path).splitlines()]
    return " ".join(" ".join(lines).split())


def _load_audit():
    spec = importlib.util.spec_from_file_location("w23_audit_driver", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def audit():
    return _load_audit()


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _entry(manifest: dict, source_id: str) -> dict:
    for entry in manifest["sources"]:
        if entry["source_id"] == source_id:
            return entry
    raise AssertionError(f"source not found: {source_id}")


# --- A. Evidence identity ---------------------------------------------------


def test_a1_correct_source_hash_verifies(audit, manifest):
    # Probe 1: positive control — the committed package must verify.
    result = audit.verify_package(manifest, REPO_ROOT)
    assert result["integrity_ok"] is True, result["violations"]
    assert result["summary"]["violations"] == 0
    verified = {
        entry["source_id"]
        for entry in result["entries"]
        if entry["status"] == "VERIFIED"
    }
    assert {
        "B-W15-MODEL-UBJ",
        "B-W15-MODEL-MANIFEST",
        "B-FEATURE-REGISTRY",
        "B-W11-SPLIT-MANIFEST",
    } <= verified


def test_a2_modified_model_file_fails_sha_binding(audit, manifest, tmp_path):
    # Probe 2: a modified model file fails its SHA-256 binding.
    entry = _entry(manifest, "B-W15-MODEL-UBJ")
    target = tmp_path / entry["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / entry["path"], target)
    assert audit.verify_entry(entry, tmp_path)["status"] == "VERIFIED"
    data = bytearray(target.read_bytes())
    data[-1] ^= 0x01
    target.write_bytes(bytes(data))
    assert audit.verify_entry(entry, tmp_path)["status"] == "MISMATCH"


def test_a3_modified_feature_registry_fails_verification(audit, manifest, tmp_path):
    # Probe 3: a modified feature registry fails verification.
    entry = _entry(manifest, "B-FEATURE-REGISTRY")
    target = tmp_path / entry["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / entry["path"], target)
    target.write_text(
        target.read_text(encoding="utf-8") + "\n# w23 mutation probe\n",
        encoding="utf-8",
    )
    assert audit.verify_entry(entry, tmp_path)["status"] == "MISMATCH"


def test_a4_wrong_split_manifest_hash_fails(audit, manifest, tmp_path):
    # Probe 4: a wrong split-manifest hash fails.
    entry = copy.deepcopy(_entry(manifest, "B-W11-SPLIT-MANIFEST"))
    target = tmp_path / entry["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / entry["path"], target)
    entry["sha256"] = "0" * 64
    assert audit.verify_entry(entry, tmp_path)["status"] == "MISMATCH"


def test_a5_git_blob_sha_mistaken_for_sha256_is_detected(audit, manifest, tmp_path):
    # Probe 5: a git blob SHA (40 hex) is not a file-content SHA-256 (64 hex).
    entry = _entry(manifest, "B-W15-MODEL-UBJ")
    data = (REPO_ROOT / entry["path"]).read_bytes()
    blob_sha = hashlib.sha1(
        b"blob " + str(len(data)).encode() + b"\0" + data
    ).hexdigest()
    assert len(blob_sha) == 40
    assert blob_sha != entry["sha256"]
    forged = copy.deepcopy(entry)
    forged["sha256"] = blob_sha
    target = tmp_path / entry["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    assert audit.verify_entry(forged, tmp_path)["status"] == "MISMATCH"
    # The manifest itself declares the hash kind explicitly.
    assert manifest["hash_semantics"]["FILE_CONTENT_SHA256"].startswith(
        "SHA-256 over the exact file bytes"
    )


def test_a6_unavailable_source_is_not_declared_verified(audit, manifest):
    # Probe 6: an unavailable source must not be reported as verified.
    unavailable = [
        entry for entry in manifest["sources"] if entry["availability"] != "LOCAL"
    ]
    assert unavailable
    result = audit.verify_package(manifest, REPO_ROOT)
    by_id = {entry["source_id"]: entry for entry in result["entries"]}
    for entry in unavailable:
        assert by_id[entry["source_id"]]["status"] != "VERIFIED"
        assert by_id[entry["source_id"]]["observed_sha256"] is None
        assert entry["sha256"] is None


def test_a7_duplicate_evidence_id_with_conflicting_content_is_rejected(audit, manifest):
    # Probe 7: duplicate source IDs are rejected even with different content.
    forged = copy.deepcopy(manifest)
    duplicate = copy.deepcopy(forged["sources"][0])
    duplicate["path"] = forged["sources"][1]["path"]
    duplicate["sha256"] = forged["sources"][1]["sha256"]
    forged["sources"].append(duplicate)
    with pytest.raises(audit.ManifestError):
        audit.validate_manifest(forged)


def test_a8_unmerged_external_source_is_not_accepted(manifest):
    # Probe 8: an unmerged A/C/D source is never marked accepted.
    accepted_classes = {
        "ACCEPTED_PREDICTIVE_PHYSICAL_EVIDENCE",
        "ACCEPTED_PAIRED_PHYSICAL_EVIDENCE",
    }
    for entry in manifest["sources"]:
        assert entry["evidence_class"] not in accepted_classes
    external = {row["dependency_id"]: row for row in manifest["external_dependencies"]}
    assert external["A-PR-95"]["observed_status"] == "OPEN_UNMERGED"
    assert external["C-PR-72"]["observed_status"] == "OPEN_UNMERGED"
    assert external["C-PR-98"]["observed_status"] == "OPEN_UNMERGED"
    assert external["D-FINAL-POLICY"]["observed_status"] == "NOT_FROZEN"
    assert external["W16-LOCKED-TEST"]["observed_status"] == "NOT_OPENED"


def test_a9_source_replaced_after_manifest_generation_is_detected(
    audit, manifest, tmp_path
):
    # Probe 9: a silent replacement after generation is detected.
    entry = _entry(manifest, "B-W15-MODEL-JSON")
    target = tmp_path / entry["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / entry["path"], target)
    assert audit.verify_entry(entry, tmp_path)["status"] == "VERIFIED"
    original = target.read_bytes()
    replacement = original[:-2] + b"{}"
    target.write_bytes(replacement)
    assert audit.verify_entry(entry, tmp_path)["status"] == "MISMATCH"


def test_a10_manifest_self_hash_is_absent_and_rejected(audit, manifest):
    # Probe 10: no self-referential manifest hashing.
    assert MANIFEST_PATH.name not in manifest["reports"]
    assert all(
        Path(entry["path"]).name != MANIFEST_PATH.name
        for entry in manifest["sources"]
    )
    forged = copy.deepcopy(manifest)
    self_entry = copy.deepcopy(forged["sources"][0])
    self_entry["source_id"] = "B-W23-SELF"
    self_entry["path"] = f"ml/reports/W23/{MANIFEST_PATH.name}"
    self_entry["sha256"] = "0" * 64
    forged["sources"].append(self_entry)
    with pytest.raises(audit.ManifestError):
        audit.validate_manifest(forged)


# --- B. Dataset card --------------------------------------------------------


def test_b11_frames_are_not_counted_as_independent_runs():
    # Probe 11.
    text = DATASET_CARD.read_text(encoding="utf-8")
    assert "Records / frames" in text
    assert "Independent runs" in text
    assert "0 predictive-eligible" in text
    assert "957 rows" in text and "9 293 frames" in text


def test_b12_segments_are_not_independent_runs():
    # Probe 12.
    text = DATASET_CARD.read_text(encoding="utf-8")
    assert "18 exported rows/segments" in text
    assert "18 segments = 18 independent runs" in text
    assert "not 18 independent" in text


def test_b13_shared_boot_is_counted_once():
    # Probe 13.
    text = DATASET_CARD.read_text(encoding="utf-8")
    assert "two test IDs share **one** boot" in text
    assert "independent session count = **1**" in text
    assert "2 W21 test IDs = 2 independent sessions" in text


def test_b14_synthetic_dataset_is_not_labelled_real_predictive_data():
    # Probe 14.
    text = DATASET_CARD.read_text(encoding="utf-8")
    assert "`SYNTHETIC_SOFTWARE_CONTROL_ONLY`" in text
    assert "REAL_PREDICTIVE_DATASET = NOT_ADMITTED" in text
    assert "D4 REAL PREDICTIVE DEVELOPMENT DATA = NOT_ADMITTED" in text


def test_b15_physical_qa_is_not_promoted_to_training_eligibility():
    # Probe 15.
    text = DATASET_CARD.read_text(encoding="utf-8")
    assert "`PHYSICAL_MEASUREMENT_DIAGNOSTIC_ONLY`" in text
    assert "0 predictive-eligible" in text
    assert "TRAINING_ELIGIBLE" not in text
    assert "D2 PHYSICAL CAPTURE PACKAGE = DIAGNOSTIC_ONLY / 0 ELIGIBLE" in text


def test_b16_calibration_and_time_provenance_are_present():
    # Probe 16.
    text = DATASET_CARD.read_text(encoding="utf-8")
    assert "Calibration status" in text
    assert "Time-domain status" in text
    assert "CALIBRATION_NOT_AVAILABLE" in text or "`NOT_AVAILABLE`" in text
    assert "BOOT_SCOPED_UPTIME" in text


def test_b17_locked_test_payload_is_not_read_for_documentation():
    # Probe 17.
    text = DATASET_CARD.read_text(encoding="utf-8")
    assert "declared membership only; payload never opened" in text
    assert "LOCKED_REAL_PREDICTIVE_TEST = NOT_EXECUTED" in text
    w16 = json.loads(W16_MANIFEST.read_text(encoding="utf-8"))
    assert w16["evaluation_status"] == "NOT_RUN"
    assert w16["holdout_opened"] is False


def test_b18_train_validation_pair_lineage_does_not_overlap():
    # Probe 18: every pair is in exactly one partition; both arms agree.
    w11 = json.loads(W11_MANIFEST.read_text(encoding="utf-8"))
    lineage = w11["split"]["pair_lineage"]
    partitions = {}
    arm_partitions = {}
    for pair in lineage:
        pair_id = pair["pair_id"]
        assert pair_id not in partitions
        partitions[pair_id] = pair["partition"]
        for run_id in pair["run_ids"]:
            assert run_id not in arm_partitions
            arm_partitions[run_id] = pair["partition"]
    assert set(partitions.values()) <= {"train", "validation", "test"}
    assert len(partitions) == 10
    for pair in lineage:
        for run_id in pair["run_ids"]:
            assert arm_partitions[run_id] == partitions[pair["pair_id"]]


def test_b19_t2_is_hot_side_not_chamber_air():
    # Probe 19.
    text = _text(DATASET_CARD)
    assert "**T2 is TEC hot-side**" in text
    assert "T2 `TEC_HOT_SIDE`" in text
    assert "is not chamber air" in text


def test_b20_unknown_label_and_horizon_are_not_presented_as_frozen():
    # Probe 20.
    text = DATASET_CARD.read_text(encoding="utf-8")
    assert "`NOT_FROZEN`" in text
    assert "`ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN`" in text
    assert "DEVELOPMENT_CANDIDATE_NOT_SELECTED" in text


# --- C. Model card ----------------------------------------------------------


def test_c21_native_model_hash_matches_actual_bytes(audit, manifest):
    # Probe 21.
    model = MODEL_MANIFEST.read_text(encoding="utf-8")
    actual = _sha(ML_ROOT / "reports" / "W15" / "model" / "model.ubj")
    assert actual == "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f"
    assert actual in model
    card = MODEL_CARD.read_text(encoding="utf-8")
    assert actual in card
    result = audit.verify_package(manifest, REPO_ROOT)
    by_id = {entry["source_id"]: entry for entry in result["entries"]}
    assert by_id["B-W15-MODEL-UBJ"]["status"] == "VERIFIED"


def test_c22_ordered_feature_hash_is_recomputable(manifest):
    # Probe 22.
    data = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    recomputed = hashlib.sha256(
        json.dumps(data["ordered_feature_ids"]).encode()
    ).hexdigest()
    assert recomputed == data["ordered_feature_ids_sha256"]
    assert recomputed in MODEL_CARD.read_text(encoding="utf-8")
    mutated = list(data["ordered_feature_ids"])
    mutated[0], mutated[1] = mutated[1], mutated[0]
    assert hashlib.sha256(json.dumps(mutated).encode()).hexdigest() != recomputed


def test_c23_w15_model_is_not_described_as_physically_validated():
    # Probe 23.
    card = MODEL_CARD.read_text(encoding="utf-8")
    assert "MODEL = SYNTHETIC_NON_DEPLOYABLE" in card
    assert "not a physical validation" in card
    assert "physical validation" in card


def test_c24_synthetic_ap_is_not_promoted_to_real_ap():
    # Probe 24.
    card = MODEL_CARD.read_text(encoding="utf-8")
    assert "Synthetic AP = 1.0 is **not** a physical AP" in card
    assert "SYNTHETIC_SOFTWARE_CONTROL_ONLY" in card


def test_c25_model_inspection_shortcut_is_disclosed():
    # Probe 25.
    inspection = json.loads(MODEL_INSPECTION.read_text(encoding="utf-8"))
    assert inspection["tree_count"] == 60
    assert inspection["total_split_count"] == 60
    assert inspection["used_feature_ids"] == ["time_since_open"]
    assert inspection["used_feature_count"] == 1
    assert inspection["unused_feature_count"] == 27
    assert inspection["dominant_feature_split_thresholds"] == [60.0]
    card = _text(MODEL_CARD)
    assert "60 trees and 60 splits" in card
    assert "unused in the fitted artifact" in _norm(MODEL_CARD)


def test_c26_risk_score_is_not_presented_as_probability():
    # Probe 26.
    card = _norm(MODEL_CARD)
    assert "not an empirically calibrated probability" in card
    assert "RISK_SCORE_ONLY" in card
    assert "percentage-risk" in card


def test_c27_illustrative_threshold_is_not_presented_as_frozen():
    # Probe 27.
    card = MODEL_CARD.read_text(encoding="utf-8")
    assert "ILLUSTRATIVE_NOT_FROZEN" in card
    assert "Warning persistence | `NOT_FROZEN`" in card


def test_c28_model_card_does_not_claim_locked_test_success():
    # Probe 28.
    card = MODEL_CARD.read_text(encoding="utf-8")
    assert "REAL_LOCKED_TEST = NOT_RUN" in card
    text = card.lower()
    assert "locked test" in text
    assert "locked-test ap" not in text


def test_c29_model_was_not_copied_to_release_folder():
    # Probe 29.
    assert not (ML_ROOT / "reports" / "W15" / "model-rc").exists()
    card = MODEL_CARD.read_text(encoding="utf-8")
    assert "did not create a" in card and "model-rc/" in card


def test_c30_model_bytes_are_unchanged(manifest):
    # Probe 30.
    entry = _entry(manifest, "B-W15-MODEL-UBJ")
    assert _sha(REPO_ROOT / entry["path"]) == entry["sha256"]
    assert not (ML_ROOT / "reports" / "W15" / "model" / "model-v2.ubj").exists()


# --- D. Figures -------------------------------------------------------------


def test_d31_synthetic_pair_plot_is_not_a_final_physical_outcome():
    # Probe 31.
    svg = W22_PLOT.read_text(encoding="utf-8")
    assert "TEST_ONLY" in svg
    assert "SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY" in svg
    assert "Final ColdGuard A/B Improvement" not in svg


def test_d32_pr_curve_is_not_derived_from_locked_test():
    # Probe 32.
    report = FIGURE_REPORT.read_text(encoding="utf-8")
    assert "no physical PR curve exists" in report
    assert "W16 locked test was not opened" in report
    w16 = json.loads(W16_MANIFEST.read_text(encoding="utf-8"))
    assert w16["holdout_opened"] is False


def test_d33_calibration_plot_is_not_a_real_probability_claim():
    # Probe 33.
    report = _norm(FIGURE_REPORT)
    assert "NOT_APPLICABLE_RISK_SCORE_ONLY" in report
    assert "not a validated real probability curve" in report


def test_d34_missing_ewt_is_not_rendered_as_zero():
    # Probe 34.
    report = FIGURE_REPORT.read_text(encoding="utf-8")
    assert "`NOT_ESTIMABLE`" in report
    assert "no zero bar" in report
    assert "proxy screening, not measured EWT" in report


def test_d35_missing_physical_ci_is_not_replaced_by_toy_ci():
    # Probe 35.
    report = FIGURE_REPORT.read_text(encoding="utf-8")
    assert "WITHHELD_UNTIL_PHYSICAL_ANALYSIS" in report
    assert "toy CI" in report and "statistical-engine unit test" in report


def test_d36_no_only_favorable_physical_run_is_selected():
    # Probe 36.
    report = FIGURE_REPORT.read_text(encoding="utf-8")
    assert "no accepted physical trajectory figure exists" in report
    assert "No cherry-picked physical trajectories | PASS" in report


def test_d37_no_inconsistent_axes_in_physical_ab_comparison():
    # Probe 37.
    report = FIGURE_REPORT.read_text(encoding="utf-8")
    assert "physical A/B plots absent" in report
    assert "single outcome axis" in report


def test_d38_figures_carry_source_identity_and_units():
    # Probe 38.
    report = FIGURE_REPORT.read_text(encoding="utf-8")
    assert report.count("Source data identity") >= 3
    assert "°C·s" in report
    assert "Figure SHA-256" in report


def test_d39_no_plot_mixes_incompatible_evidence_classes():
    # Probe 39.
    report = FIGURE_REPORT.read_text(encoding="utf-8")
    assert "Explicit evidence class on the figure | PASS" in report
    svg = W22_PLOT.read_text(encoding="utf-8")
    assert "PHYSICAL" not in svg


def test_d40_figure_manifest_present_matches_actual_files(manifest):
    # Probe 40.
    report = FIGURE_REPORT.read_text(encoding="utf-8")
    present_rows = [
        line for line in report.splitlines() if line.endswith("| `PRESENT` |")
    ]
    assert len(present_rows) == 6
    figures = manifest["figure_availability"]["present"]
    assert len(figures) == 6
    for relative in figures:
        assert (REPO_ROOT / relative).is_file(), relative
        assert relative in report
    for relative in manifest["figure_availability"]["withheld"]:
        assert not (REPO_ROOT / relative).exists()
