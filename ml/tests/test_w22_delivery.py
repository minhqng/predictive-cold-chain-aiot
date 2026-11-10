"""W22 delivery controls: determinism, scope, capability and gate integrity."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ML_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ML_ROOT / "scripts" / "w22-statistics-contract-W22.py"
REPORTS_DIR = ML_ROOT / "reports" / "W22"

REPORT_NAMES = (
    "paired-statistics-contract-W22.md",
    "uncertainty-and-tests-W22.md",
    "sensitivity-contract-W22.md",
    "scientific-limitations-W22.md",
    "analysis-readiness-W22.md",
)
PLOT_NAME = "test-only-pair-plot-W22.svg"
MANIFEST_NAME = "w22-manifest.json"

PRIOR_ARTIFACTS = {
    "reports/W16/locked-test-manifest-W16.json": "6e7e7f23881785f76463344663e08f0cf626f5ee137aa1f98a99772e1a1fe165",
    "reports/W19/w19-manifest.json": "f3bbae932743b4b71c8e8ed7bbbb5334836353080361aa2746c3950cb989db82",
    "reports/W20/w20-manifest.json": "0d8c2ad1cb846599d3535a74ade65186b388702da59eb4bfb0271dcb5a849ece",
    "reports/W20/analysis-unlock-W20.md": "cea11179f2d58487dbc2cea5bba610c27bd4a84574b7278a3cfcd6ae43b19376",
    "reports/W20/paired-outcome-contract-W20.md": "2768273d029dc3f0894867e85df3de52a44093bb745e86efdbc6077f61cf08c1",
    "reports/W21/w21-manifest.json": "5b78141deca1d3f5fd5e16ac10b3344541261d66b5aaa6e49bb3169758fae2c3",
    "reports/W21/diagnosis-table-W21.md": "c67ada12603c810e5821546f3a3d4ebd6f780d6011f5a9f71f2190d3691477b4",
    "reports/W21/safe-local-summary-W21.md": "053095bef6e55599b45a1b468a145ca72f23acd0b90785cbecb4bb54143cb74d",
    "reports/W21/degraded-sensor-pzem-W21.md": "3cd357c61ebfdb9014116a722f4e004fa547bd9090600061ae347298d0631866",
    "reports/W21/optional-energy-gate-W21.md": "9939b5f0baa02710760551948c1395b35b6418d34c96041218b984223aa17897",
}

REQUIRED_PROBES = (
    "valid_pair_admitted",
    "two_a_arms_refused",
    "duplicate_pair_id_refused",
    "run_reused_across_pairs_refused",
    "arm_order_reversed_refused",
    "telemetry_windows_not_pairs",
    "arm_wise_bootstrap_refused",
    "invalid_pair_silently_included_refused",
    "rerun_extra_pair_refused",
    "unknown_value_not_zero",
    "known_descriptives",
    "sample_sd_denominator",
    "quantile_type7_pinned",
    "negative_improvement_not_beneficial",
    "constant_differences_refused_inference",
    "nan_inf_refused",
    "unit_mismatch_refused",
    "every_pair_plot_complete",
    "student_t_not_196",
    "degrees_of_freedom_n_minus_1",
    "row_window_bootstrap_refused",
    "pair_level_bootstrap_preserves_pairing",
    "unseeded_bootstrap_refused",
    "iteration_policy_enforced",
    "bootstrap_collapse_not_reliability",
    "n_below_minimum_refused",
    "two_primary_cis_refused",
    "favorable_ci_not_selected",
    "paired_not_independent_test",
    "no_smallest_p_selection",
    "wilcoxon_license_required",
    "zero_tie_handling",
    "two_sided_default",
    "paired_sd_effect_not_pooled",
    "zero_sd_effect_not_infinite",
    "relative_denominator_guard",
    "significance_not_usefulness",
    "extreme_pair_retained_primary",
    "loo_not_primary",
    "primary_n_unchanged",
    "secondary_not_promoted",
    "posthoc_not_preregistered",
    "horizon_shopping_refused",
    "synthetic_not_physical",
    "closed_loop_ewt_refused",
    "one_rig_not_multiple_sites",
    "w20_blocked_not_authorized",
    "w16_holdout_not_opened",
    "fixture_not_physical_campaign",
    "fake_approval_refused",
    "cli_lock_bypass_refused",
    "no_outcome_csv_artifact",
    "no_real_p_value",
    "g4_g5_not_promoted",
    "model_not_retuned",
    "prior_reports_unmodified",
)

PURE_MODULES = (
    "coldguard_ml.w22_paired_statistics",
    "coldguard_ml.w22_uncertainty",
    "coldguard_ml.w22_sensitivity",
)
ALLOWED_STDLIB_IMPORTS = {
    "__future__",
    "dataclasses",
    "fractions",
    "hashlib",
    "math",
    "random",
    "typing",
}


def _load_driver():
    spec = importlib.util.spec_from_file_location("w22_delivery_driver", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver():
    return _load_driver()


def _files(directory: Path) -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ML_ROOT / "src") + (
        os.pathsep + existing if existing else ""
    )
    return env


def _run_driver(out_dir: Path) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out_dir)],
        check=True,
        capture_output=True,
        text=True,
        env=_subprocess_env(),
        timeout=300,
    )


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("w22-generated")
    _run_driver(out_dir)
    return out_dir


def _manifest(out_dir: Path) -> dict:
    return json.loads((out_dir / MANIFEST_NAME).read_text(encoding="utf-8"))


def test_generated_report_set_is_complete(generated):
    files = _files(generated)
    assert set(files) == {*REPORT_NAMES, PLOT_NAME, MANIFEST_NAME}
    assert not any(name.endswith(".csv") for name in files)
    assert not any("pair-outcomes" in name for name in files)


def test_two_independent_processes_are_byte_identical(tmp_path):
    first = tmp_path / "run1"
    second = tmp_path / "run2"
    _run_driver(first)
    _run_driver(second)
    assert _files(first) == _files(second)


def test_reports_are_explicitly_test_only(generated):
    for name in REPORT_NAMES:
        text = (generated / name).read_text(encoding="utf-8")
        assert "TEST_ONLY" in text, name
        assert "Controller B wins" not in text
    uncertainty = (generated / "uncertainty-and-tests-W22.md").read_text(
        encoding="utf-8"
    )
    assert "SENSITIVITY ROLE" in uncertainty
    assert "exactly one primary interval" in uncertainty
    assert "role: `SENSITIVITY`" in uncertainty
    limitations = (generated / "scientific-limitations-W22.md").read_text(
        encoding="utf-8"
    )
    assert "TEMPLATE ONLY" in limitations
    assert "NO_INTERPRETATION_ANALYSIS_NOT_RUN" in limitations
    readiness = (generated / "analysis-readiness-W22.md").read_text(
        encoding="utf-8"
    )
    assert "physical" in readiness.lower()
    assert "NOT_AUTHORIZED" in readiness


def test_every_pair_plot_is_complete_and_labelled(generated):
    svg = (generated / PLOT_NAME).read_text(encoding="utf-8")
    assert "TEST_ONLY" in svg
    assert "SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY" in svg
    assert "PRIMARY OUTCOME" in svg
    for index in range(1, 9):
        assert f"P-{index:02d}" in svg
    assert "bar chart" not in svg.lower()


def test_manifest_schema_and_verdicts(generated):
    manifest = _manifest(generated)
    assert manifest["schema"] == "coldguard-w22-paired-statistics-contract-v1"
    assert manifest["sign_convention"] == "I_i = Y_A,i - Y_B,i"
    assert manifest["statistical_unit"].startswith("one accepted matched")
    verdicts = manifest["verdicts"]
    assert verdicts["B_W22_01_DESCRIPTIVE_STATISTICS"] == "SOFTWARE_VERIFIED"
    assert verdicts["B_W22_02_95_CI"] == "SOFTWARE_VERIFIED"
    assert verdicts["B_W22_03_TEST_FAMILY"] == "SOFTWARE_VERIFIED"
    assert verdicts["B_W22_04_EFFECT_SIZE"] == "SOFTWARE_VERIFIED"
    assert verdicts["B_W22_05_SENSITIVITY"] == "SOFTWARE_VERIFIED"
    assert verdicts["B_W22_06_LIMITATIONS"] == "DOCUMENTED"
    assert verdicts["REAL_PAIRED_ANALYSIS"] == "NOT_RUN"
    assert verdicts["FINAL_PHYSICAL_CI"] == "NOT_COMPUTED"
    assert verdicts["FINAL_PHYSICAL_P_VALUE"] == "NOT_COMPUTED"
    assert verdicts["FINAL_PHYSICAL_EFFECT"] == "NOT_ESTABLISHED"
    assert verdicts["W20_ANALYSIS_GATE"] == "LOCKED"
    assert verdicts["G4"] == "NOT_READY"
    assert verdicts["G5"] == "NOT_ESTABLISHED"
    assert verdicts["SOFTWARE"] == "COMPLETE"


def test_manifest_records_no_real_analysis(generated):
    integrity = _manifest(generated)["scientific_integrity"]
    assert integrity["PHYSICAL_ANALYSIS"] == "NOT_AUTHORIZED"
    assert integrity["REAL_PAIRED_STATISTICS"] == "NOT_COMPUTED"
    assert integrity["FINAL_PHYSICAL_CI"] == "NOT_COMPUTED"
    assert integrity["FINAL_PHYSICAL_P_VALUE"] == "NOT_COMPUTED"
    assert integrity["FINAL_PHYSICAL_EFFECT"] == "NOT_ESTABLISHED"
    assert integrity["W20_FINAL_ANALYSIS"] == "LOCKED"
    assert integrity["W16_HOLDOUT"] == "NOT_OPENED"
    assert integrity["PAIR_TARGET"] == "UNKNOWN_UNFROZEN"
    assert integrity["FINAL_AB_CAMPAIGN"] == "NOT_AUTHORIZED"
    assert integrity["INTERPRETATION"] == "NO_INTERPRETATION_ANALYSIS_NOT_RUN"


def test_manifest_readiness_comes_from_blocked_w20_gate(generated):
    readiness = _manifest(generated)["readiness"]
    assert readiness["physical_analysis"] == "NOT_AUTHORIZED"
    assert readiness["real_paired_statistics"] == "NOT_COMPUTED"
    assert readiness["gate_decision"] != "ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION"
    assert readiness["reasons"]


def test_adversarial_matrix_is_complete_and_passing(generated):
    controls = _manifest(generated)["verification"]["adversarial_controls"]
    assert controls["probe_count"] == 56
    assert controls["probes_passed"] == 56
    names = {probe["name"] for probe in controls["probes"]}
    assert set(REQUIRED_PROBES) <= names
    assert all(probe["passed"] for probe in controls["probes"])
    assert len(controls["probes"]) == 56


def test_reference_checks_recorded(generated):
    checks = _manifest(generated)["verification"]["reference_checks"]
    assert len(checks) >= 20
    assert all(check["passed"] for check in checks)
    names = {check["name"] for check in checks}
    for required in (
        "primary_mean",
        "primary_sample_sd",
        "t_critical_df7",
        "t_p_primary",
        "sign_p_primary",
        "wilcoxon_p_primary",
        "effect_dz_primary",
    ):
        assert required in names


def test_capability_audit_is_clean(generated):
    audit = _manifest(generated)["capability_audit"]
    assert audit["forbidden_imports"] == []
    assert audit["pure_statistics_file_access_imports"] == []
    assert audit["ewt_functions"] == []
    assert all(value is False for value in audit["capabilities"].values())
    assert all(
        value is False for value in _manifest(generated)["capabilities"].values()
    )


def test_reports_hashes_bind_generated_files(generated):
    manifest = _manifest(generated)
    for name in (*REPORT_NAMES, PLOT_NAME):
        digest = hashlib.sha256((generated / name).read_bytes()).hexdigest()
        assert manifest["reports"][name] == digest
    assert manifest["bootstrap_policy"]["resampling_unit"] == "COMPLETE_MATCHED_PAIRS"
    assert manifest["bootstrap_policy"]["minimum_iterations"] == 2000
    assert manifest["bootstrap_policy"]["seed"] == 20261110
    interval_policy = manifest["interval_policy"]
    assert interval_policy["primary_method"] == "PAIRED_T_95_CI"
    assert interval_policy["confidence_level"] == 0.95
    assert interval_policy["second_method_role"] == "SENSITIVITY"
    assert (
        interval_policy["selection_rule"]
        == "PREDECLARED_NO_FAVORABILITY_OR_WIDTH_SELECTION"
    )


def test_prior_artifacts_are_byte_unchanged(generated):
    rows = _manifest(generated)["prior_layer_immutability"]
    assert len(rows) == len(PRIOR_ARTIFACTS)
    for row in rows:
        assert row["unchanged"] is True, row["path"]
        expected = PRIOR_ARTIFACTS[row["path"]]
        observed = hashlib.sha256((ML_ROOT / row["path"]).read_bytes()).hexdigest()
        assert observed == expected


def test_w20_and_w19_do_not_import_w22():
    files = sorted((ML_ROOT / "src" / "coldguard_ml").glob("w19_*.py"))
    files += sorted((ML_ROOT / "src" / "coldguard_ml").glob("w20_*.py"))
    assert files
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(
                    alias.name.startswith(("w22", "coldguard_ml.w22"))
                    for alias in node.names
                ), path.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("w22"), path.name


def test_pure_statistics_modules_import_only_stdlib_and_w22():
    for module_name in PURE_MODULES:
        relative = Path("src") / Path(*module_name.split(".")).with_suffix(".py")
        tree = ast.parse((ML_ROOT / relative).read_text(encoding="utf-8"))
        absolute = set()
        relative_imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                absolute.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    absolute.add(node.module.split(".")[0])
                elif node.level > 0 and node.module:
                    relative_imports.add(node.module)
        assert absolute <= ALLOWED_STDLIB_IMPORTS, (module_name, absolute)
        assert all(name.startswith("w22_") for name in relative_imports), (
            module_name,
            relative_imports,
        )


def test_pure_modules_have_no_file_access_bindings():
    code = (
        "import coldguard_ml.w22_paired_statistics as a;"
        "import coldguard_ml.w22_uncertainty as b;"
        "import coldguard_ml.w22_sensitivity as c;"
        "names=('pathlib','json','csv','os','subprocess','socket','shutil');"
        "print(sorted(n for n in names if any(hasattr(m,n) for m in (a,b,c))))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=_subprocess_env(),
        timeout=60,
    )
    assert result.stdout.strip() == "[]"


def test_driver_cli_has_no_input_or_bypass(driver):
    parser = driver.build_parser()
    options = {
        option for action in parser._actions for option in action.option_strings
    }
    assert options == {"-h", "--help", "--out"}
    for forbidden in ("--force", "--unlock", "--ignore-lock", "--input", "--csv"):
        assert forbidden not in options
    with pytest.raises(SystemExit):
        parser.parse_args(["--force"])


def test_w16_manifest_is_hash_only_and_holdout_unopened():
    manifest = json.loads(
        (ML_ROOT / "reports" / "W21" / "w21-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["scientific_integrity"]["W16_HOLDOUT"] == "NOT_OPENED"
    w16_manifest = ML_ROOT / "reports" / "W16" / "locked-test-manifest-W16.json"
    assert hashlib.sha256(w16_manifest.read_bytes()).hexdigest() == PRIOR_ARTIFACTS[
        "reports/W16/locked-test-manifest-W16.json"
    ]


def test_readiness_rejects_a_prelabelled_assessment_object():
    from coldguard_ml.w22_readiness import assess_real_analysis_readiness

    class ForgedAssessment:
        gate_decision = "ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION"
        analysis_authorization_status = "ISSUED"
        refusal_reasons = ()
        outcome_access = False
        campaign_id = "FORGED"
        evidence_class = "PHYSICAL_CAMPAIGN_RECORD"

    with pytest.raises(TypeError):
        assess_real_analysis_readiness(ForgedAssessment())
