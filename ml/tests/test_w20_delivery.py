"""W20 delivery controls: determinism, hash binding, scope and capability."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from coldguard_ml.w19_no_peeking import W19OutcomeExposureError
from coldguard_ml.w20_campaign_lock import W20EvidenceError

ML_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ML_ROOT / "scripts" / "w20-campaign-preflight-W20.py"
REPORTS_DIR = ML_ROOT / "reports" / "W20"

EXPECTED_REPORTS = (
    "campaign-integrity.md",
    "paired-outcome-contract-W20.md",
    "analysis-unlock-W20.md",
)

PINNED_EARLIER_ARTIFACTS = {
    "reports/W11/benchmark-manifest-W11.json": "855c5beb55f15c6e5bcd38640ff3a6ff02a41a525bf3f1601722abdeca2d47f0",
    "reports/W12/w12-manifest.json": "ef06f9712203b39c01351ad89a17368574e98a0db6436f842e926b68418073a7",
    "reports/W13/horizon-manifest-W13.json": "02a76660319f6118900ec54ee3d50fa96968ad14b0a7110f3fdaf1b62417a404",
    "reports/W14/w14-manifest.json": "e4a0263ead067a10df8d23ffc2bb10d6e750c88e515153fd6f637c733077357d",
    "reports/W15/model/model.ubj": "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f",
    "reports/W15/model/model-manifest-W15.json": "85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e",
    "reports/W16/locked-test-manifest-W16.json": "6e7e7f23881785f76463344663e08f0cf626f5ee137aa1f98a99772e1a1fe165",
    "reports/W17/w17-manifest.json": "8b2e92e7c70134e5ab0c6ac796c900b681bc7d66f79eddb48ecc939ddcc33532",
    "reports/W18/w18-manifest.json": "bd1391d72d030af5e0ca99540059424fbf45ca1ccced255e8d41ca374799c9ab",
    "reports/W18/freeze-baseline-W18.json": "d1bcc8ff26ed28ed998fb2c43d7fa57ab928d6c4d90c1af801289016dd446581",
    "reports/W19/w19-manifest.json": "f3bbae932743b4b71c8e8ed7bbbb5334836353080361aa2746c3950cb989db82",
    "reports/W19/campaign-readiness-W19.md": "f554788a441a2eebfc622d3731effc5fa93b010e06ba73a3cb699c6790a7187a",
    "reports/W19/pair-ledger-contract-W19.md": "1cc99bfcf99e2a95e74437c85c28c2c59e37979e272072c52e2f3add4af879df",
    "reports/W19/validity-discipline-W19.md": "e4514e709be0785fefe8da2f8e2f127d607f16a4040c2fdadc309e78e2f62fcf",
    "reports/W19/no-significance-peeking-W19.md": "20cf96565ab478d97e45196768465e6bf808e799c4eb4bccd28c6b22634eb996",
}

FORBIDDEN_RUNTIME_IMPORTS = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "requests",
    "httpx",
    "paho",
    "mqtt",
    "serial",
    "subprocess",
    "multiprocessing",
    "asyncio",
    "scipy",
    "statsmodels",
    "sklearn",
    "xgboost",
}


def _load_driver():
    spec = importlib.util.spec_from_file_location("w20_delivery_driver", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver():
    return _load_driver()


@pytest.fixture(scope="module")
def generated(driver, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("w20-generated")
    summary = driver.generate(out_dir)
    return out_dir, summary


def _files(directory: Path) -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def test_only_the_expected_report_family_is_generated(generated):
    out_dir, _ = generated
    assert set(_files(out_dir)) == set(EXPECTED_REPORTS) | {"w20-manifest.json"}


def test_manifest_binds_every_report_hash(generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w20-manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["reports"]) == set(EXPECTED_REPORTS)
    for name, digest in manifest["reports"].items():
        assert hashlib.sha256((out_dir / name).read_bytes()).hexdigest() == digest


def test_analysis_code_hash_matches_the_manifest(driver, generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w20-manifest.json").read_text(encoding="utf-8"))
    assert manifest["analysis_code_sha256"] == driver._analysis_code_sha256()


def test_committed_reports_match_a_fresh_generation(generated):
    out_dir, _ = generated
    assert REPORTS_DIR.is_dir(), "run the W20 driver into ml/reports/W20 first"
    for name in (*EXPECTED_REPORTS, "w20-manifest.json"):
        committed = (REPORTS_DIR / name).read_bytes()
        fresh = (out_dir / name).read_bytes()
        assert committed == fresh, f"{name} is stale; regenerate reports/W20"


def test_driver_is_byte_deterministic_across_processes(tmp_path):
    first = tmp_path / "run-1"
    second = tmp_path / "run-2"
    for out_dir in (first, second):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--out-dir", str(out_dir)],
            cwd=ML_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
    assert _files(first) == _files(second)


def test_in_process_generation_is_deterministic(driver, tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    driver.generate(first)
    driver.generate(second)
    assert _files(first) == _files(second)


def test_reports_are_deterministic_text_without_wall_clock(generated):
    out_dir, _ = generated
    for name in EXPECTED_REPORTS:
        text = (out_dir / name).read_text(encoding="utf-8")
        assert "generated_at" not in text
        assert "timestamp" not in text
        assert not re.search(r"\b20\d{2}-\d{2}-\d{2}T", text)


def test_earlier_artifacts_are_byte_unchanged():
    for relative, expected in PINNED_EARLIER_ARTIFACTS.items():
        digest = hashlib.sha256((ML_ROOT / relative).read_bytes()).hexdigest()
        assert digest == expected, f"{relative} changed"


def test_generation_does_not_touch_earlier_artifacts(driver, tmp_path):
    before = {
        relative: hashlib.sha256((ML_ROOT / relative).read_bytes()).hexdigest()
        for relative in PINNED_EARLIER_ARTIFACTS
    }
    driver.generate(tmp_path / "out")
    after = {
        relative: hashlib.sha256((ML_ROOT / relative).read_bytes()).hexdigest()
        for relative in PINNED_EARLIER_ARTIFACTS
    }
    assert before == after


def test_w20_sources_carry_no_runtime_or_analysis_imports(driver):
    for path in driver.W20_SOURCE_FILES:
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert (
                        alias.name.split(".")[0] not in FORBIDDEN_RUNTIME_IMPORTS
                    ), f"{path.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert (
                    module.split(".")[0] not in FORBIDDEN_RUNTIME_IMPORTS
                ), f"{path.name} imports from {module}"


def test_manifest_keeps_scientific_deliverables_incomplete(generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w20-manifest.json").read_text(encoding="utf-8"))
    verdicts = manifest["verdicts"]
    assert verdicts["PHYSICAL_PAIR_EVIDENCE"] == "NOT_ESTABLISHED"
    assert verdicts["PAIR_TARGET"] == "UNKNOWN_UNFROZEN"
    assert verdicts["FINAL_CAMPAIGN"] == "NOT_AUTHORIZED"
    assert verdicts["CAMPAIGN_LOCK"] == "BLOCKED"
    assert verdicts["W20_ANALYSIS"] == "NOT_AUTHORIZED"
    assert verdicts["W20_FINAL_ANALYSIS"] == "NOT_RUN"
    assert verdicts["SCIENTIFIC_W20"] == "NOT_COMPLETE"
    assert verdicts["G4"] == "NOT_READY"
    assert verdicts["G5"] == "NOT_ESTABLISHED"
    assert verdicts["W16_HOLDOUT"] == "NOT_OPENED"
    assert manifest["campaign_state"]["gate_decision"] == "ANALYSIS_PREFLIGHT_BLOCKED"
    assert manifest["campaign_state"]["closeout_state"] == "PAIR_TARGET_NOT_FROZEN"
    assert manifest["fixture_proof"]["admitted_to_physical_campaign"] is False
    assert manifest["fixture_proof"]["proof_class"] == "TEST_ONLY_SOFTWARE_GATE_PROOF"
    assert manifest["fixture_proof"]["gate_decision"] != (
        "ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION"
    )


def test_manifest_capabilities_are_all_false(generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w20-manifest.json").read_text(encoding="utf-8"))
    assert manifest["capabilities"]
    assert all(value is False for value in manifest["capabilities"].values())


def test_all_adversarial_controls_pass(generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w20-manifest.json").read_text(encoding="utf-8"))
    controls = manifest["adversarial_controls"]
    assert controls["probe_count"] >= 54
    assert controls["probes_passed"] == controls["probe_count"]
    assert all(probe["passed"] for probe in controls["probes"])
    names = {probe["name"] for probe in controls["probes"]}
    for required in (
        "missing_g4_blocks",
        "fake_approval_string_refused",
        "target_changed_after_attempts_started",
        "model_artifact_changed",
        "feature_schema_changed",
        "policy_threshold_changed",
        "warning_persistence_changed",
        "cooling_magnitude_changed",
        "hardware_or_firmware_changed",
        "calibration_changed",
        "disturbance_protocol_changed",
        "initial_tolerance_changed",
        "primary_outcome_definition_changed",
        "drift_without_comparability_approval",
        "thermal_outcome_payload_refused",
        "power_outcome_payload_refused",
        "p_value_capability_refused",
        "paired_effect_capability_refused",
        "effect_based_pair_selection_refused",
        "synthetic_outcome_table_refused",
        "locked_test_opened_refused",
        "preflight_does_not_start_analysis",
        "cli_override_refused",
        "closed_loop_b_ewt_refused",
        "missing_ewt_not_zero",
        "missing_aiw_not_zero",
        "ack_not_physical_response",
        "electrical_not_thermal_recovery",
        "pzem_gap_not_zero_energy",
        "cooling_branch_not_whole_system",
        "unfrozen_representative_temperature_refused",
        "synthetic_timing_not_actionability",
        "ledger_campaign_identity_mismatch_refused",
        "ledger_frozen_target_mismatch_refused",
        "ledger_statistical_freeze_mismatch_refused",
        "ledger_campaign_freeze_mismatch_refused",
        "malformed_target_history_refused",
        "malformed_n_inflation_claim_refused",
        "w16_holdout_missing_refused",
        "w16_holdout_malformed_refused",
        "post_intervention_warning_not_counterfactual",
        "unknown_provenance_aiw_refused",
    ):
        assert required in names, required


def test_manifest_records_reproducibility_bindings(generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w20-manifest.json").read_text(encoding="utf-8"))
    for key in (
        "layer_version",
        "analysis_code_sha256",
        "source_revision",
        "revision_semantics",
        "w19_pair_ledger_contract",
        "w19_validity_contract",
        "w18_freeze_baseline_identity",
        "w16_preregistration_identity",
        "campaign_metadata_source",
        "generation_inputs",
    ):
        assert key in manifest, key
    assert manifest["w19_pair_ledger_contract"]["schema"] == (
        "coldguard-w19-pair-ledger-v1"
    )
    assert manifest["campaign_state"]["g4"] == "NOT_READY"
    assert manifest["campaign_state"]["controller_b_signoff"] == "WITHHELD"
    assert manifest["paired_analysis_contract"]["sign_convention"] == (
        "I_i = Y_A,i - Y_B,i"
    )
    assert manifest["paired_analysis_contract"]["paired_effects_computed"] is False
    assert manifest["paired_analysis_contract"]["p_value_computed"] is False
    assert manifest["paired_analysis_contract"]["confidence_interval_computed"] is False


def test_manifest_records_no_machine_absolute_paths(generated):
    out_dir, _ = generated
    text = (out_dir / "w20-manifest.json").read_text(encoding="utf-8")
    assert "worktree-b-w20" not in text
    assert "D:\\\\" not in text
    manifest = json.loads(text)
    for entry in manifest["generation_inputs"].values():
        if isinstance(entry, dict) and "path" in entry:
            assert not entry["path"].startswith("D:")
    scanned = manifest["capability_audit"]["files_scanned"]
    assert scanned
    assert all(not path.startswith("D:") for path in scanned)
    for path in manifest["metadata_files_read"]:
        assert not path.startswith("D:")


def test_metadata_reads_exclude_outcome_paths(generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w20-manifest.json").read_text(encoding="utf-8"))
    assert manifest["metadata_files_read"]
    for path in manifest["metadata_files_read"]:
        lowered = path.lower()
        assert "outcome" not in lowered
        assert "thermal_series" not in lowered
        assert "power_series" not in lowered


def test_driver_refuses_an_outcome_bearing_campaign_record(driver, tmp_path, monkeypatch):
    record = {
        "schema": "coldguard-w20-campaign-metadata-v1",
        "campaign_id": "CG-BAD",
        "evidence_class": "METADATA_RECORD_ONLY",
        "fixture_markers": [],
        "pair_ledger": {
            "pairs": [],
            "attempts": [{"attempt_id": "ATT-BAD", "thermal_exposure": 11.2}],
        },
    }
    monkeypatch.setattr(driver, "_read_campaign_metadata", lambda reader: record)
    with pytest.raises(W19OutcomeExposureError):
        driver.generate(tmp_path / "out")


def test_driver_main_returns_two_on_a_malformed_record(driver, tmp_path, monkeypatch):
    record = {
        "schema": "coldguard-w20-campaign-metadata-v1",
        "campaign_id": "CG-BAD",
        "evidence_class": "METADATA_RECORD_ONLY",
        "fixture_markers": [],
        "unexpected": "field",
    }
    monkeypatch.setattr(driver, "_read_campaign_metadata", lambda reader: record)
    assert driver.main(["--out-dir", str(tmp_path / "out")]) == 2


def test_driver_refuses_hidden_evaluate_and_force_routes(driver):
    for argument in ("--evaluate", "--force"):
        with pytest.raises(SystemExit) as excinfo:
            driver._parse_args([argument])
        assert int(excinfo.value.code or 0) == 2


def test_no_pair_outcomes_csv_is_created(generated):
    out_dir, _ = generated
    assert not (out_dir / "pair-outcomes.csv").exists()
    assert not (REPORTS_DIR / "pair-outcomes.csv").exists()
    report = (out_dir / "paired-outcome-contract-W20.md").read_text(encoding="utf-8")
    assert "PAIR_OUTCOMES_CSV = WITHHELD_UNTIL_SEPARATE_AUTHORIZED_EXECUTION" in report
    assert "PAIR_LEDGER_FINAL = WITHHELD_NO_ACCEPTED_PHYSICAL_CAMPAIGN" in report
    unlock = (out_dir / "analysis-unlock-W20.md").read_text(encoding="utf-8")
    assert "PAIRED_EFFECT_COMPUTED = NONE" in unlock


def test_reports_declare_gate_and_analysis_not_run(generated):
    out_dir, _ = generated
    integrity = (out_dir / "campaign-integrity.md").read_text(encoding="utf-8")
    unlock = (out_dir / "analysis-unlock-W20.md").read_text(encoding="utf-8")
    assert "CAMPAIGN_LOCK = BLOCKED" in integrity
    assert "W20_ANALYSIS = NOT_AUTHORIZED" in integrity
    assert "W20_ANALYSIS = NOT_AUTHORIZED" in unlock
    assert "OUTCOME_SERIES_OPENED = NONE" in unlock
    assert "P_VALUE_COMPUTED = NONE" in unlock
    assert "CONFIDENCE_INTERVAL_COMPUTED = NONE" in unlock


def test_w20_files_are_confined_to_member_b_ownership(driver):
    for path in driver.W20_SOURCE_FILES:
        assert path.is_file()
        assert path.parent.name in {"coldguard_ml", "scripts", "tests"}
        assert ML_ROOT in path.parents
    for path in (
        ML_ROOT / "reports" / "W20" / "campaign-metadata-W20.json",
        ML_ROOT / "reports" / "W20" / "w20-manifest.json",
    ):
        assert path.is_file()
        assert path.parent == REPORTS_DIR


def test_malformed_bundle_cannot_pass(driver):
    with pytest.raises(W20EvidenceError):
        driver.assess_campaign_lock({"schema": "coldguard-w20-campaign-metadata-v1"})
