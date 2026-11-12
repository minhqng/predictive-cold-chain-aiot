"""W21 delivery controls: determinism, binding, scope and capability."""

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

ML_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ML_ROOT / "scripts" / "w21-resilience-audit-W21.py"
REPORTS_DIR = ML_ROOT / "reports" / "W21"

EXPECTED_REPORTS = (
    "diagnosis-table-W21.md",
    "safe-local-summary-W21.md",
    "degraded-sensor-pzem-W21.md",
    "optional-energy-gate-W21.md",
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
    "reports/W20/w20-manifest.json": "0d8c2ad1cb846599d3535a74ade65186b388702da59eb4bfb0271dcb5a849ece",
    "reports/W20/campaign-metadata-W20.json": "b0c49699036752c8707e650bb4f3b58a3389c12c94ae80106d38b8db94b3076b",
    "reports/W20/campaign-integrity.md": "89c02aa88a77f4b02eac12db92410a2bec84d0d51cd9750a91f5749a1ab9eae5",
    "reports/W20/paired-outcome-contract-W20.md": "2768273d029dc3f0894867e85df3de52a44093bb745e86efdbc6077f61cf08c1",
    "reports/W20/analysis-unlock-W20.md": "cea11179f2d58487dbc2cea5bba610c27bd4a84574b7278a3cfcd6ae43b19376",
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

REQUIRED_PROBES = (
    "authentic_on_device_injection_classified",
    "host_simulation_not_on_device",
    "injection_not_physical_disconnect",
    "output_disabled_not_enabled_validation",
    "shared_boot_not_independent",
    "raw_log_hash_mismatch_refused",
    "manifest_result_identity_mismatch_refused",
    "unmerged_c_not_physical",
    "pass_field_not_authority",
    "missing_physical_not_negative",
    "command_on_not_current",
    "ack_not_physical_response",
    "current_without_thermal",
    "unknown_not_healthy",
    "missing_pzem_not_zero",
    "disabled_stage_not_electrical_failure",
    "weak_thermal_not_component",
    "software_detection_accuracy_refused",
    "no_ground_truth_not_concordant",
    "synthetic_not_physical_reliability",
    "outage_duration_without_endpoints",
    "receipt_time_not_event_time",
    "reconnect_not_safe_local_exit",
    "twin_regression_refused",
    "stale_command_not_applied",
    "duplicate_not_inflate_sample",
    "resync_without_fresh_state",
    "ai_unavailable_score_not_trusted",
    "safe_local_not_physical_protection",
    "single_session_not_distribution",
    "hot_side_not_chamber_substitute",
    "rom_remap_not_concealed",
    "unknown_door_not_closed",
    "invalid_temperature_not_numeric",
    "stale_pzem_not_current",
    "missing_current_not_zero",
    "energy_reset_not_hidden",
    "recovery_requires_fresh_samples",
    "degraded_model_inference_refused",
    "test_fault_not_training_data",
    "gate_f_closed_no_energy_analysis",
    "pwm_not_claimed",
    "cooling_branch_not_whole_system",
    "w20_outcome_not_opened",
    "w16_locked_test_not_opened",
    "w15_model_not_deployable",
    "g4_g5_not_upgraded",
    "c_d_code_not_modified",
    "no_physical_fault_injection",
    "unknown_not_numeric_zero",
    "positive_valid_source_admitted",
    "positive_bounded_evidence_limited_gate",
    "positive_fixture_timeline_durations",
    "positive_replay_clean",
    "positive_exit_gate_ready",
    "positive_healthy_enabled_case",
    "positive_electrical_missing_case",
    "positive_unexpected_off_current",
)


def _load_driver():
    spec = importlib.util.spec_from_file_location("w21_delivery_driver", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver():
    return _load_driver()


@pytest.fixture(scope="module")
def generated(driver, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("w21-generated")
    summary = driver.generate(out_dir)
    return out_dir, summary


def _files(directory: Path) -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def _manifest(out_dir: Path) -> dict:
    return json.loads((out_dir / "w21-manifest.json").read_text(encoding="utf-8"))


def test_only_the_expected_report_family_is_generated(generated):
    out_dir, _ = generated
    assert set(_files(out_dir)) == set(EXPECTED_REPORTS) | {"w21-manifest.json"}


def test_manifest_binds_every_report_hash(generated):
    out_dir, _ = generated
    manifest = _manifest(out_dir)
    assert set(manifest["reports"]) == set(EXPECTED_REPORTS)
    for name, digest in manifest["reports"].items():
        assert hashlib.sha256((out_dir / name).read_bytes()).hexdigest() == digest


def test_analysis_code_hash_matches_the_manifest(driver, generated):
    out_dir, _ = generated
    assert _manifest(out_dir)["analysis_code_sha256"] == (
        driver._analysis_code_sha256()
    )


def test_committed_reports_match_a_fresh_generation(generated):
    out_dir, _ = generated
    assert REPORTS_DIR.is_dir(), "run the W21 driver into ml/reports/W21 first"
    for name in (*EXPECTED_REPORTS, "w21-manifest.json"):
        committed = (REPORTS_DIR / name).read_bytes()
        fresh = (out_dir / name).read_bytes()
        assert committed == fresh, f"{name} is stale; regenerate reports/W21"


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
    driver.generate(tmp_path / "a")
    driver.generate(tmp_path / "b")
    assert _files(tmp_path / "a") == _files(tmp_path / "b")


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


def test_w21_sources_carry_no_runtime_or_analysis_imports(driver):
    for path in driver.W21_SOURCE_FILES:
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


def test_manifest_verdicts_keep_science_incomplete(generated):
    out_dir, _ = generated
    verdicts = _manifest(out_dir)["verdicts"]
    assert verdicts["SOFTWARE"] == "COMPLETE"
    assert verdicts["B_W21_01_DIAGNOSIS_TABLE"] == "SOFTWARE_VERIFIED"
    assert verdicts["B_W21_01_REAL_DIAGNOSIS_EVIDENCE"] == (
        "BOUNDED_ON_DEVICE_EVIDENCE"
    )
    assert verdicts["B_W21_02_SAFE_LOCAL_SUMMARY"] == "SOFTWARE_VERIFIED"
    assert verdicts["B_W21_02_PHYSICAL_SAFE_LOCAL"] == "NOT_ESTABLISHED"
    assert verdicts["B_W21_03_DEGRADED_SENSOR_PZEM"] == "SOFTWARE_VERIFIED"
    assert verdicts["B_W21_03_RECORDED_DEVICE_EVIDENCE"] == (
        "BOUNDED_ON_DEVICE_EVIDENCE"
    )
    assert verdicts["B_W21_04_OPTIONAL_ENERGY"] == "GATE_F_NOT_OPENED"
    assert verdicts["REAL_MODEL_ROBUSTNESS"] == "NOT_ESTABLISHED"
    assert verdicts["W15_MODEL"] == "SYNTHETIC_NONDEPLOYABLE"
    assert verdicts["G4"] == "NOT_READY"
    assert verdicts["G5"] == "NOT_ESTABLISHED"
    assert verdicts["W16_HOLDOUT"] == "NOT_OPENED"
    assert verdicts["W20_FINAL_ANALYSIS"] == "NOT_RUN"
    assert verdicts["CONTROLLER_B_SIGNOFF"] == "WITHHELD"
    assert verdicts["DELIVERY"] == "PENDING_PUBLICATION"


def test_manifest_capabilities_are_all_false(generated):
    out_dir, _ = generated
    capabilities = _manifest(out_dir)["capabilities"]
    assert capabilities
    assert all(value is False for value in capabilities.values())


def test_all_adversarial_controls_pass(generated):
    out_dir, _ = generated
    controls = _manifest(out_dir)["adversarial_controls"]
    assert controls["probe_count"] >= 54
    assert controls["probes_passed"] == controls["probe_count"]
    assert all(probe["passed"] for probe in controls["probes"])
    names = {probe["name"] for probe in controls["probes"]}
    for required in REQUIRED_PROBES:
        assert required in names, required


def test_manifest_records_reproducibility_bindings(generated):
    out_dir, _ = generated
    manifest = _manifest(out_dir)
    for key in (
        "layer_version",
        "analysis_code_sha256",
        "source_revision",
        "revision_semantics",
        "source_register_identity",
        "source_inventory",
        "source_admissions",
        "external_evidence",
        "generation_inputs",
    ):
        assert key in manifest, key
    assert manifest["source_register_identity"]["schema"] == (
        "coldguard-w21-source-register-v1"
    )
    assert manifest["source_register_identity"]["independent_session_count"] == 1
    assert manifest["external_evidence"]["a_result_commit"] == (
        "cd1b40e08456a0a088f131cbdd2e1ef3b92052cc"
    )
    assert manifest["external_evidence"]["a_independent_replay"] == (
        "INDEPENDENT_EVALUATOR_REPLAY_PENDING"
    )
    assert manifest["external_evidence"]["a_bytes_verified_live"] is False


def test_manifest_session_identity_is_shared_boot(generated):
    out_dir, _ = generated
    manifest = _manifest(out_dir)
    session = manifest["session_identity"]
    assert session["boot_id"] == "4cf9be5f"
    assert session["independent_session_count"] == 1
    assert session["record_count"] == 50
    assert session["fault_window_frames"] == 50
    assert session["recovery_frames"] == 50
    assert session["total_recorded_frames"] == 100
    assert session["tec_actuation"] == "NONE"
    assert session["output_stage"] == "COMPILED_OUT"
    assert session["fuse"] == "OUT"
    assert session["physical_disconnection"] == "NONE"
    assert session["rom_map_unchanged"] is True


def test_diagnosis_table_is_bounded_and_not_population_scored(generated):
    out_dir, _ = generated
    manifest = _manifest(out_dir)
    table = manifest["diagnosis_table"]
    assert table["record_count"] == 50
    assert table["independent_session_count"] == 1
    assert all(
        value == "NOT_ESTIMABLE" for value in table["metrics"].values()
    )
    cases = {case["case_id"]: case for case in table["cases"]}
    assert cases["A-W21-02"]["classification"] == "DEGRADED_OR_UNKNOWN"
    assert cases["A-W21-03"]["classification"] == "DEGRADED_OR_UNKNOWN"
    assert cases["A-W21-02"]["concordance"] == "CONCORDANT_BOUNDED"
    assert cases["A-W21-03"]["concordance"] == "CONCORDANT_BOUNDED"
    for row in manifest["canonical_diagnosis_rows"]:
        assert row["status"] == "NOT_ESTIMABLE"


def test_gate_f_report_is_closed_and_has_no_energy_numbers(generated):
    out_dir, _ = generated
    text = (out_dir / "optional-energy-gate-W21.md").read_text(encoding="utf-8")
    assert "GATE_F = NOT_OPENED" in text
    assert "B_W21_04 = NOT_APPLICABLE_OPTIONAL_GATE_CLOSED" in text
    assert "ENERGY_ANALYSIS = NOT_PERFORMED" in text
    assert "PWM_CHARACTERIZATION = NOT_PERFORMED" in text
    assert "DUTY_CYCLE_SEARCH = NOT_PERFORMED" in text


def test_manifest_records_no_machine_absolute_paths(generated):
    out_dir, _ = generated
    text = (out_dir / "w21-manifest.json").read_text(encoding="utf-8")
    assert "D:\\\\" not in text
    assert "D:/" not in text
    assert "worktree-b-w21" not in text
    manifest = json.loads(text)
    for entry in manifest["generation_inputs"].values():
        assert not entry["path"].startswith("D:")
    assert manifest["capability_audit"]["files_scanned"]
    assert all(
        not path.startswith("D:")
        for path in manifest["capability_audit"]["files_scanned"]
    )
    for path in manifest["metadata_files_read"]:
        assert not path.startswith("D:")


def test_metadata_reads_exclude_w16_and_w20_outcomes(generated):
    out_dir, _ = generated
    manifest = _manifest(out_dir)
    assert manifest["metadata_files_read"] == [
        "reports/W18/w18-manifest.json",
        "reports/W20/w20-manifest.json",
        "reports/W15/A3-report.md",
    ]
    for path in manifest["metadata_files_read"]:
        lowered = path.lower()
        assert "w16" not in lowered
        assert "outcome" not in lowered
        assert "locked-test" not in lowered


def test_driver_refuses_hidden_evaluate_force_and_energy_routes(driver):
    for argument in ("--evaluate", "--force", "--energy", "--pwm"):
        with pytest.raises(SystemExit) as excinfo:
            driver._parse_args([argument])
        assert int(excinfo.value.code or 0) == 2


def test_driver_main_returns_zero(driver, tmp_path):
    assert driver.main(["--out-dir", str(tmp_path / "out")]) == 0


def test_no_pair_outcomes_csv_is_created(generated):
    out_dir, _ = generated
    assert not (out_dir / "pair-outcomes.csv").exists()
    assert not (REPORTS_DIR / "pair-outcomes.csv").exists()


def test_no_a_raw_evidence_is_copied_into_ml(driver):
    ml_tree = ML_ROOT
    assert not list(ml_tree.rglob("A-W21-02.json"))
    assert not list(ml_tree.rglob("A-W21-03.json"))
    assert not list(ml_tree.rglob("faf008eb6c7e-raw.log"))
    assert not (ml_tree / "evidence").exists()


def test_w21_files_are_confined_to_member_b_ownership(driver):
    for path in driver.W21_SOURCE_FILES:
        assert path.is_file()
        assert path.parent.name in {"coldguard_ml", "scripts", "tests"}
        assert ML_ROOT in path.parents
    for name in (*EXPECTED_REPORTS, "w21-manifest.json"):
        assert (REPORTS_DIR / name).is_file()


def test_source_inventory_hashes_are_pinned(driver, generated):
    out_dir, _ = generated
    manifest = _manifest(out_dir)
    inventory = {row["source_id"]: row for row in manifest["source_inventory"]}
    assert len(inventory) == 26
    assert inventory["A-W21-02-RESULT"]["source_sha256"] == (
        "4fbc22d3150d3e67a8e1c2556543c454e68e835426d8fd66a3bc0f6949b1682b"
    )
    assert inventory["A-W21-SESSION-RAW"]["source_sha256"] == (
        "faf008eb6c7e250c8b8f98385e6eb3817b1084771a56d800a3735c576c7106fa"
    )
    assert inventory["C-W21-INCIDENT-AUDIT"]["source_revision"] == (
        "72a5861c0dd47b69a9f326312e3e1b523c1bcaee"
    )
    assert inventory["D-POLICY"]["source_revision"] == (
        "da821094985006945d0306dd7b16be576378bc18"
    )
    for row in inventory.values():
        assert row["evidence_class"]
        assert row["gate"]
        assert row["admissible_inference"]


def test_committed_generation_marks_cross_checks_not_verified(generated):
    out_dir, _ = generated
    manifest = _manifest(out_dir)
    admissions = {
        row["source_id"]: row for row in manifest["source_admissions"]
    }
    result = admissions["A-W21-02-RESULT"]
    assert result["gate"] == "BOUNDED_ON_DEVICE_EVIDENCE"
    assert result["checks"]["SOURCE_BYTES_VERIFIED"] == "VERIFIED"
    assert result["checks"]["MANIFEST_COHERENT"] == "NOT_VERIFIED"
    assert result["checks"]["RECORDED_CHECK_PASSED"] == "NOT_VERIFIED"
    assert result["checks"]["ACCEPTANCE_AUTHORITY_VERIFIED"] == "NOT_VERIFIED"


def test_live_source_verification_accepts_the_pinned_a_checkout(tmp_path, driver):
    """The pinned A bytes verify when a read-only checkout is supplied."""
    repo = ML_ROOT.parent
    session = repo / "evidence" / "A" / "W21" / "fault-injection-session-20261108"
    if not session.is_dir():
        pytest.skip("A-W21 evidence checkout is not present")
    summary = driver.generate(tmp_path / "out", verify_sources_root=repo)
    manifest = _manifest(tmp_path / "out")
    assert summary["source_count"] == 26
    assert manifest["external_evidence"]["a_bytes_verified_live"] is True
    admissions = {
        row["source_id"]: row for row in manifest["source_admissions"]
    }
    assert admissions["A-W21-02-RESULT"]["checks"]["SOURCE_BYTES_VERIFIED"] == (
        "VERIFIED"
    )
    assert admissions["A-W21-02-RESULT"]["checks"]["MANIFEST_COHERENT"] == (
        "VERIFIED"
    )
    assert admissions["A-W21-02-RESULT"]["checks"]["RECORDED_CHECK_PASSED"] == (
        "VERIFIED"
    )
    assert admissions["A-W21-SESSION-RAW"]["checks"]["SOURCE_BYTES_VERIFIED"] == (
        "VERIFIED"
    )
