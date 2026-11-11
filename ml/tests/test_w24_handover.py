"""W24 final handover verification.

Covers the canonical W24 assertions: artifact hashes, model identity, descriptive
data classification, 12 real plots, T2 exclusion, refusal records, missing
scientific outputs, unchanged prior artifacts, deterministic manifest, internal
links and independent-replay status.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
W24 = ML_ROOT / "reports" / "W24"
DATA_RECOVERY = ML_ROOT / "reports" / "DataRecovery"
W23 = ML_ROOT / "reports" / "W23"

CHECKS_PATH = W24 / "artifact-checksums-W24.json"
HANDOVER_PATH = W24 / "handover-manifest-W24.json"
RECEIPT_TEMPLATE = W24 / "independent-replay-receipt-template-W24.json"

DISPOSITIONS = {
    "COMPLETE_AND_VERIFIED",
    "AVAILABLE_WITH_LIMITATIONS",
    "REQUIRES_TEAM_REVIEW",
    "BLOCKED_BY_EXTERNAL_EVIDENCE",
    "NOT_PRODUCED",
    "NOT_APPLICABLE",
}

W24_DOCS = [
    "artifact-checksums-W24.json",
    "artifact-integrity-W24.md",
    "reproduction-runbook-W24.md",
    "reproduction-result-W24.md",
    "oral-defense-vi-W24.md",
    "defense-questions-vi-W24.md",
    "FINAL-HANDOVER-MEMBER-B.md",
    "scientific-gaps-and-owners-W24.md",
    "independent-replay-receipt-template-W24.json",
    "handover-manifest-W24.json",
]

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

EXPECTED_MODEL_SHA = "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _checks() -> dict:
    return _load(CHECKS_PATH)


def _handover() -> dict:
    return _load(HANDOVER_PATH)


def _artifact_matches(entry: dict, root: Path = REPO_ROOT) -> bool:
    path = root / entry["source_path"]
    return path.is_file() and _sha(path) == entry["content_sha256"]


def _all_check_entries(checks: dict) -> list[dict]:
    return [
        entry
        for category in checks["categories"].values()
        for entry in category.get("artifacts", [])
    ]


def test_w24_outputs_exist():
    assert {name for name in W24_DOCS} <= {p.name for p in W24.iterdir()}
    outputs = _handover()["w24_outputs"]
    assert len(outputs) == 10
    for output in outputs:
        path = REPO_ROOT / output["path"]
        assert path.is_file(), output["path"]
        assert _sha(path) == output["sha256"], output["path"]
    assert all("handover-manifest-W24.json" not in o["path"] for o in outputs)


def test_every_inventoried_artifact_hash_matches_bytes():
    checks = _checks()
    failures = [
        entry["artifact_id"]
        for entry in checks["artifact_index"].values()
        if not _artifact_matches(entry)
    ]
    assert failures == []
    assert checks["entry_count"] >= 40
    assert checks["unique_artifact_count"] == len(checks["artifact_index"])


def test_model_artifact_sha256_matches_expected():
    checks = _checks()
    entry = checks["artifact_index"]["B-W15-MODEL-UBJ"]
    assert entry["source_path"] == "ml/reports/W15/model/model.ubj"
    assert entry["content_sha256"] == EXPECTED_MODEL_SHA
    assert (REPO_ROOT / entry["source_path"]).is_file()
    assert _sha(REPO_ROOT / entry["source_path"]) == EXPECTED_MODEL_SHA
    assert checks["categories"]["D_model_artifact"]["summary"]["matches_expected"] is True


def test_w11_synthetic_dataset_is_not_labeled_physical():
    checks = _checks()
    synthetic = checks["categories"]["A_dataset_export"]["summary"]["w11_synthetic"]
    assert synthetic["evidence_class"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    assert synthetic["generated_in_memory"] is True
    assert "physical" not in synthetic["permitted_use"].lower()
    w11 = _load(ML_ROOT / "reports" / "W11" / "benchmark-manifest-W11.json")
    assert w11["scientific_status"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    assert w11["provenance"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    assert w11["split"]["test_partition_used"] is False


def test_data_recovery_is_descriptive_only():
    checks = _checks()
    category = checks["categories"]["E_final_result_files"]["summary"]
    assert category["FINAL_PREDICTIVE_RESULT_CSV"] == "NOT_PRODUCED"
    assert category["FINAL_PHYSICAL_AB_RESULT_CSV"] == "NOT_PRODUCED"
    entry = checks["artifact_index"]["B-DATARECOVERY-REAL-OBSERVATIONS"]
    assert entry["evidence_class"] == "PHYSICAL_RECORDED_DATA"
    assert "descriptive" in entry["limitations"].lower()
    recovery = _load(DATA_RECOVERY / "recovery-manifest.json")
    assert recovery["scientific_status"]["REAL_PREDICTIVE_BENCHMARK"] == "NOT_ESTABLISHED"
    assert recovery["family_totals"]["independent_qualified_runs"] == 0


def test_final_result_csvs_are_not_invented():
    checks = _checks()
    assert checks["categories"]["E_final_result_files"]["summary"][
        "FINAL_PREDICTIVE_RESULT_CSV"
    ] == "NOT_PRODUCED"
    assert checks["categories"]["E_final_result_files"]["summary"][
        "FINAL_PHYSICAL_AB_RESULT_CSV"
    ] == "NOT_PRODUCED"
    names = [p.name.lower() for p in (ML_ROOT / "reports").rglob("*.csv")]
    assert not [n for n in names if "final-predictive" in n or "final-physical-ab" in n]


def test_twelve_real_plots_match_declared_hashes():
    plots = _checks()["categories"]["G_real_physical_figures"]
    assert plots["summary"]["count"] == 12
    assert plots["summary"]["manifest_declared_count"] == 12
    assert plots["summary"]["all_match_declared"] is True
    for entry in plots["artifacts"]:
        assert entry["matches_declared"] is True
        assert _artifact_matches(entry)


def test_real_plot_metadata_has_units_and_source_hash():
    hash_re = re.compile(r"\b[a-f0-9]{64}\b")
    for entry in _checks()["categories"]["G_real_physical_figures"]["artifacts"]:
        text = (REPO_ROOT / entry["source_path"]).read_text(encoding="utf-8")
        assert "PHYSICAL_RECORDED_DATA" in text
        assert "degC" in text
        assert "sha256" in text.lower()
        assert hash_re.search(text), entry["source_path"]


def test_t2_is_never_chamber_air():
    registry = yaml.safe_load((ML_ROOT / "feature-registry-v1.yaml").read_text(encoding="utf-8"))
    roles = registry["role_map"]["observed_rig"]["slots"]
    assert roles["t1"]["physical_position"] == "CHAMBER_CENTER"
    assert roles["t2"]["physical_position"] == "TEC_HOT_SIDE"
    assert roles["t2"]["in_chamber_air_aggregate"] is False
    assert roles["t3"]["physical_position"] == "CHAMBER_BOTTOM"
    assert roles["t4"]["physical_position"] == "CHAMBER_NEAR_DOOR"
    chamber = {"CHAMBER_CENTER", "CHAMBER_BOTTOM", "CHAMBER_NEAR_DOOR"}
    for feature in registry["features"]:
        if feature["feature_id"].startswith("T_chamber_"):
            assert set(feature["sensor_roles"]) == chamber
            assert "t2_c" not in feature["source_fields"]


def test_w16_refusal_is_not_mislabeled():
    text = (W23.parent / "W16" / "locked-test-result.md").read_text(encoding="utf-8")
    assert "NOT_EXECUTED_PREREQUISITES_UNMET" in text
    assert "NO_INTERPRETATION_TEST_NOT_RUN" in text
    assert "the only valid W16 interpretation record is" in text
    assert "holdout_opened = false" in text
    assert "evaluation_status = NOT_RUN" in text
    assert "No AP, precision, recall, false-warning burden, missed-event" in text
    assert _handover()["scientific_status"]["W16_LOCKED_TEST"] == "NOT_OPENED"
    assert _handover()["scientific_absences"]["REAL_LOCKED_PREDICTIVE_TEST"] == "NOT_RUN"


def test_w22_toy_statistics_are_not_physical():
    w22 = _load(ML_ROOT / "reports" / "W22" / "w22-manifest.json")
    assert w22["readiness"]["physical_analysis"] == "NOT_AUTHORIZED"
    assert w22["readiness"]["real_paired_statistics"] == "NOT_COMPUTED"
    assert w22["scientific_integrity"]["FINAL_PHYSICAL_EFFECT"] == "NOT_ESTABLISHED"
    item = next(i for i in _handover()["canonical_items"] if i["item"] == "ab_statistics")
    assert item["evidence_class"] == "SOFTWARE_VERIFICATION"
    assert item["real_outcomes"] == "NOT_PRODUCED"
    assert "toy" in item["limitations"].lower()


def test_ewt_and_aiw_are_not_represented_as_zero():
    status = _handover()["scientific_status"]
    assert status["REAL_EWT"] == "NOT_ESTIMABLE"
    assert status["REAL_AIW"] == "NOT_ESTIMABLE"
    text = (ML_ROOT / "reports" / "W14" / "AIW-report.md").read_text(encoding="utf-8")
    assert "NOT_ESTIMABLE" in text
    figures = (W23 / "figure-availability-W23.md").read_text(encoding="utf-8")
    assert "No zero bar" in figures or "no zero bar" in figures


def test_missing_external_sources_are_not_silently_verified():
    package = _load(W23 / "evidence-package-W23.json")
    unavailable = [s for s in package["sources"] if s["availability"] == "SOURCE_UNAVAILABLE"]
    assert len(unavailable) == 9
    for source in unavailable:
        assert source["sha256"] is None
    external = _checks()["external_sources"]
    assert external["declared_total"] == 97
    assert external["local"] == 88
    assert external["unavailable"] == 9
    assert external["current_audit_verified"] == 88
    assert external["historical_receipt_verified"] == 83
    assert "92-entry" in external["revision_explanation"]


def test_independent_human_replay_is_still_pending():
    receipt = _load(RECEIPT_TEMPLATE)
    assert receipt["status"] == "PENDING_TEMPLATE_NOT_A_COMPLETED_RECEIPT"
    assert receipt["completed"] is False
    assert receipt["declaration"]["i_am_a_different_human_reviewer"] is None
    assert not (W24 / "independent-replay-receipt-W24.json").exists()
    absences = _handover()["scientific_absences"]
    assert absences["INDEPENDENT_TEAM_MEMBER_REPLAY"] == "PENDING"
    checks = _checks()["scientific_status"]
    assert checks["GATE_B_PHYSICAL_DATA"] == "RED"
    assert checks["G3"] == "NO-GO / FIX DATA"


def test_handover_readiness_does_not_promote_gates():
    handover = _handover()
    assert handover["completion_states"]["MEMBER_B_SOFTWARE_HANDOVER"] == "READY"
    assert handover["completion_states"]["FINAL_PREDICTIVE_SCIENTIFIC_ACCEPTANCE"] == "INCOMPLETE"
    status = handover["scientific_status"]
    assert status["GATE_B_PHYSICAL_DATA"] == "RED"
    assert status["PREDICTIVE_DATASET_READINESS"] == "NOT_READY"
    assert status["G3"] == "NO-GO / FIX DATA"
    assert status["G4"] == "NOT_READY"
    assert status["G5"] == "NOT_ESTABLISHED"
    assert status["SCIENTIFIC_ACCEPTANCE"] == "INCOMPLETE"
    w08 = _load(ML_ROOT / "reports" / "W08" / "gate-b-manifest-W08.json")
    assert w08["physical_gate"]["observed_status"] == "RED"
    assert w08["software_gate"]["observed_status"] == "GREEN"


def test_prior_w01_to_w23_artifacts_are_unchanged():
    for rel, expected in PRIOR_ARTIFACTS.items():
        assert _sha(REPO_ROOT / rel) == expected, rel
    recovery = _load(DATA_RECOVERY / "recovery-manifest.json")
    for name, expected in recovery["reports"].items():
        assert _sha(DATA_RECOVERY / name) == expected, name
    for name, expected in recovery["plots"].items():
        assert _sha(DATA_RECOVERY / name) == expected, name


def _all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_keys(child)


def _all_strings(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _all_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_strings(child)
    elif isinstance(value, str):
        yield value


def test_handover_manifest_is_deterministic_and_portable():
    handover = _handover()
    raw = HANDOVER_PATH.read_text(encoding="utf-8")
    assert raw == json.dumps(handover, indent=2, ensure_ascii=False) + "\n"
    volatile_keys = {"generated_at", "generated_at_utc", "timestamp", "creation_date"}
    assert volatile_keys.isdisjoint(set(_all_keys(handover)))
    for text in _all_strings(handover):
        assert not text.startswith(("D:\\", "C:\\", "/d/", "/c/")), text
        assert "D:\\" not in text and "C:\\" not in text, text


def test_handover_has_exactly_ten_canonical_items_with_one_disposition():
    items = _handover()["canonical_items"]
    assert len(items) == 10
    assert {i["item"] for i in items} == {
        "dataset_card",
        "split_manifest",
        "feature_registry",
        "model_card",
        "model_artifact",
        "locked_test_report",
        "ab_statistics",
        "analysis_scripts",
        "figures",
        "limitations",
    }
    for item in items:
        assert item["disposition"] in DISPOSITIONS
        assert item["paths"]
        for path_entry in item["paths"]:
            assert (REPO_ROOT / path_entry["path"]).is_file(), path_entry["path"]
            assert _sha(REPO_ROOT / path_entry["path"]) == path_entry["sha256"]


def test_readiness_matrix_has_one_disposition_per_artifact():
    rows = _handover()["readiness_matrix"]
    ids = [r["artifact_id"] for r in rows]
    assert len(ids) == len(set(ids))
    for row in rows:
        assert row["disposition"] in DISPOSITIONS
    dispositions = {r["artifact_id"]: r["disposition"] for r in rows}
    assert dispositions["FINAL_PREDICTIVE_RESULT_CSV"] == "NOT_PRODUCED"
    assert dispositions["FINAL_PHYSICAL_AB_RESULT_CSV"] == "NOT_PRODUCED"
    assert dispositions["INDEPENDENT_HUMAN_REPLAY"] == "BLOCKED_BY_EXTERNAL_EVIDENCE"
    assert dispositions["GATE_B"] == "BLOCKED_BY_EXTERNAL_EVIDENCE"
    assert dispositions["HARDWARE_ACCEPTANCE"] == "REQUIRES_TEAM_REVIEW"


def test_all_internal_links_in_w24_docs_resolve():
    link_re = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    unresolved = []
    for doc in W24.glob("*.md"):
        text = doc.read_text(encoding="utf-8")
        for target in link_re.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue
            resolved = (doc.parent / path_part).resolve()
            if not resolved.exists():
                unresolved.append(f"{doc.name} -> {target}")
    assert unresolved == []


def test_reproduction_runbook_is_portable_and_complete():
    text = (W24 / "reproduction-runbook-W24.md").read_text(encoding="utf-8")
    for required in (
        "uv lock --check",
        "uv sync --locked --python 3.12 --extra test",
        "pytest -q",
        "uv build",
        "git archive d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85",
        "existing-data-recovery.py",
        "INDEPENDENT_TEAM_MEMBER_REPLAY = PENDING",
    ):
        assert required in text, required
    for forbidden in ("D:\\", "/d/iot", "C:\\"):
        assert forbidden not in text


def test_analysis_scripts_and_figures_are_indexed():
    items = {i["item"]: i for i in _handover()["canonical_items"]}
    scripts = items["analysis_scripts"]["paths"]
    assert len(scripts) >= 15
    assert any(p["path"].endswith("existing-data-recovery.py") for p in scripts)
    assert any(p["path"].endswith("w23-evidence-audit-W23.py") for p in scripts)
    figures = items["figures"]["paths"]
    real = [p for p in figures if "real-physical-plots" in p["path"]]
    assert len(real) == 12
    assert any("test-only-pair-plot-W22.svg" in p["path"] for p in figures)


def test_verifier_has_positive_and_negative_controls(tmp_path):
    entry = _checks()["artifact_index"]["B-W15-MODEL-UBJ"]
    assert _artifact_matches(entry) is True
    tampered = tmp_path / "model.ubj"
    tampered.write_bytes((REPO_ROOT / entry["source_path"]).read_bytes() + b"\x00")
    fake = dict(entry, source_path=tampered.name)
    assert _artifact_matches(fake, root=tmp_path) is False
    missing = dict(entry, source_path="does-not-exist.ubj")
    assert _artifact_matches(missing, root=tmp_path) is False


def test_scientific_absences_are_explicit():
    absences = _handover()["scientific_absences"]
    for key in (
        "FINAL_PREDICTIVE_RESULT_CSV",
        "FINAL_PHYSICAL_AB_RESULT_CSV",
        "REAL_EWT",
        "REAL_AIW",
        "FINAL_PHYSICAL_EFFECT",
        "FINAL_PHYSICAL_CI",
        "FINAL_PHYSICAL_P_VALUE",
    ):
        assert absences[key] in {"NOT_PRODUCED", "NOT_ESTIMABLE", "NOT_COMPUTED", "NOT_ESTABLISHED"}
    assert absences["LIVE_TEAM_REHEARSAL"] == "PENDING"
