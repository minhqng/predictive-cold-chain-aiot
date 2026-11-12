"""W16 delivery integrity and no-access proofs (B-W16-01).

These tests bind the committed pre-registration manifest, the W16-only report
family, the unchanged W11-W15 artifacts, and the executable no-access claims:
the preflight code has no import path into any evaluator and opens no data
payload.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
REPORT_DIR = ROOT / "reports" / "W16"
MANIFEST_PATH = REPORT_DIR / "locked-test-manifest-W16.json"
MODULE_PATH = ROOT / "src" / "coldguard_ml" / "w16_readiness.py"
SCRIPT_PATH = ROOT / "scripts" / "w16-preflight-W16.py"

MODEL_SHA256 = "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f"

EXPECTED_REFUSAL_REASONS = {
    "APPROVAL_MISSING:A_PHYSICAL",
    "APPROVAL_MISSING:B_METHOD",
    "APPROVAL_MISSING:C_TELEMETRY",
    "APPROVAL_MISSING:D_POLICY",
    "APPROVAL_MISSING:TEAM_LEAD",
    "CALIBRATION_PROVENANCE_MISSING",
    "CRITICAL_TARGET_UNFROZEN",
    "DATASET_EVIDENCE_CLASS_NOT_PHYSICAL",
    "EVENT_MATCHING_POLICY_UNFROZEN",
    "FREEZE_LEDGER_INCOMPLETE",
    "HARDWARE_CONFIG_NOT_VERIFIED",
    "MODEL_SYNTHETIC_NON_DEPLOYABLE",
    "OPERATING_THRESHOLD_UNFROZEN",
    "PHYSICAL_DATASET_IDENTITY_MISSING",
    "PHYSICAL_RUN_VALIDITY_MISSING",
    "PRIMARY_HORIZON_UNFROZEN",
    "RELEASE_AUTHORIZATION_MISSING",
    "REPRESENTATIVE_TEMPERATURE_UNFROZEN",
    "RUN_SOURCE_IDENTITY_MISSING",
    "SAMPLE_QUALITY_UNTRUSTED",
    "SCIENTIFIC_PREREQUISITES_BLOCKED",
    "TEST_MEMBERSHIP_NOT_FROZEN",
    "TIME_PROVENANCE_INADEQUATE",
    "WARNING_PERSISTENCE_UNFROZEN",
}

FORBIDDEN_PAYLOAD_PATH = re.compile(
    r"(locked|holdout|test_features|test_labels|test_predictions)", re.IGNORECASE
)


def _is_forbidden_payload(path: Path) -> bool:
    if path.resolve() == MANIFEST_PATH.resolve():
        return False  # the pre-registration manifest itself is metadata
    return bool(FORBIDDEN_PAYLOAD_PATH.search(str(path)))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _load_script_module():
    spec = importlib.util.spec_from_file_location("w16_preflight_driver", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])
    return modules


# ---------------------------------------------------------------------------
# Committed manifest contract
# ---------------------------------------------------------------------------


def test_manifest_exists_and_hmac_header_is_honest():
    manifest = _manifest()
    assert manifest["schema"] == "coldguard-w16-preregistration-v1"
    assert manifest["manifest_kind"] == "PRE_REGISTRATION_ONLY"
    assert manifest["holdout_access"] == "NOT_AUTHORIZED"
    assert manifest["holdout_opened"] is False
    assert manifest["evaluation_status"] == "NOT_RUN"
    assert manifest["layer_version"] == (
        "coldguard-w16-locked-test-preregistration-v1"
    )


def test_manifest_refuses_with_the_exact_gate_ledger():
    manifest = _manifest()
    decision = manifest["readiness_decision"]
    assert decision["decision"] == "REFUSED_PREREQUISITES_UNMET"
    assert set(decision["refusal_reasons"]) == EXPECTED_REFUSAL_REASONS
    assert len(decision["refused_requirements"]) == len(EXPECTED_REFUSAL_REASONS)
    assert "granting Gate G4" in decision["forbidden_actions"]
    assert "opening locked-test observations" in decision["forbidden_actions"]


def test_manifest_evaluation_disposition_is_not_run():
    disposition = _manifest()["evaluation_disposition"]
    assert disposition == {
        "locked_evaluation": "NOT_EXECUTED_PREREQUISITES_UNMET",
        "interpretation": "NO_INTERPRETATION_TEST_NOT_RUN",
        "model_release_candidate": "NOT_ISSUED",
        "metrics_reported": False,
        "metrics_policy": disposition["metrics_policy"],
    }
    assert "NOT_ESTIMABLE" in disposition["metrics_policy"]


def test_manifest_registration_is_bound_to_the_w15_model():
    manifest = _manifest()
    registration = manifest["registration"]
    assert registration["model_artifact_sha256"] == MODEL_SHA256
    assert registration["test_runs"] == [
        "CG-W11-S1-001",
        "CG-W11-S1-002",
        "CG-W11-S2-001",
        "CG-W11-S2-002",
    ]
    assert registration["test_pairs"] == ["W11-PAIR-001", "W11-PAIR-002"]
    assert registration["feature_schema_hash"] == (
        "1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9"
    )
    assert registration["analysis_code_sha256"] == manifest["analysis_code_sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["analysis_code_sha256"])


def test_manifest_freeze_ledger_is_truthful():
    manifest = _manifest()
    statuses = {row["field_id"]: row["status"] for row in manifest["freeze_ledger"]}
    assert statuses == {
        "model_version": "DEVELOPMENT_CANDIDATE_ONLY",
        "native_model_sha256": "DEVELOPMENT_CANDIDATE_ONLY",
        "model_config_sha256": "DEVELOPMENT_CANDIDATE_ONLY",
        "feature_version": "FROZEN_APPROVED",
        "ordered_feature_ids_sha256": "FROZEN_APPROVED",
        "training_dataset_identity": "DEVELOPMENT_CANDIDATE_ONLY",
        "target_definition": "UNFROZEN",
        "representative_temperature": "UNFROZEN",
        "primary_horizon": "UNFROZEN",
        "risk_score_calibration_semantics": "FROZEN_APPROVED",
        "operating_threshold": "UNFROZEN",
        "warning_persistence": "UNFROZEN",
        "event_matching_policy": "DEVELOPMENT_CANDIDATE_ONLY",
        "missingness_policy": "FROZEN_APPROVED",
        "analysis_code_version": "FROZEN_APPROVED",
        "physical_dataset_identity": "MISSING_EVIDENCE",
        "hardware_configuration": "MISSING_EVIDENCE",
        "telemetry_time_provenance": "MISSING_EVIDENCE",
        "run_identity_and_pairing": "MISSING_EVIDENCE",
        "calibration_provenance": "MISSING_EVIDENCE",
    }
    horizon = next(
        row for row in manifest["freeze_ledger"] if row["field_id"] == "primary_horizon"
    )
    assert horizon["value"]["decision_freeze_status"] == "NOT_FROZEN"
    assert horizon["value"]["decision_primary_horizon_s"] is None
    assert horizon["authority"] == "B"
    target = next(
        row for row in manifest["freeze_ledger"] if row["field_id"] == "target_definition"
    )
    assert target["value"]["boundary_c"] is None
    assert target["authority"] == "D"


def test_manifest_has_no_fabricated_approvals():
    manifest = _manifest()
    assert manifest["required_approvals"]
    for approval in manifest["required_approvals"]:
        assert approval["status"] == "BLOCKED_BY_MISSING_EVIDENCE"
        assert approval["reason_code"].startswith("APPROVAL_MISSING:")
        assert approval["records"] == 0


def test_manifest_inputs_match_the_repository_files():
    manifest = _manifest()
    assert manifest["inputs_scope"] == "METADATA_ONLY"
    assert manifest["inputs"]
    for relative, entry in manifest["inputs"].items():
        path = ROOT / relative
        assert path.is_file(), relative
        assert _sha256(path) == entry["sha256"], relative


def test_manifest_contains_no_timestamp_or_temp_path():
    text = MANIFEST_PATH.read_text(encoding="utf-8")
    assert not re.search(r"\d{4}-\d{2}-\d{2}T", text)
    assert "pytest-of-" not in text
    assert "AppData" not in text


def test_manifest_records_the_registered_authority_owners():
    manifest = _manifest()
    authorities = {row["authority"] for row in manifest["freeze_ledger"]}
    assert authorities <= {"A", "B", "C", "D"}
    approvals = {row["role"] for row in manifest["required_approvals"]}
    assert approvals == {"A_PHYSICAL", "B_METHOD", "C_TELEMETRY", "D_POLICY", "TEAM_LEAD"}


# ---------------------------------------------------------------------------
# Withheld release artifacts
# ---------------------------------------------------------------------------


def test_model_rc_directory_is_withheld():
    assert not (REPORT_DIR / "model-rc").exists()
    assert not (REPORT_DIR / "model").exists()


def test_no_model_binary_or_payload_is_committed_under_w16():
    binaries = [
        path
        for path in REPORT_DIR.rglob("*")
        if path.is_file() and path.suffix in {".ubj", ".pkl", ".joblib", ".parquet"}
    ]
    assert binaries == []
    json_files = {path.name for path in REPORT_DIR.glob("*.json")}
    assert json_files == {"locked-test-manifest-W16.json"}
    assert REPORT_DIR / "locked-test-manifest-W16.json"


def test_prior_layer_artifacts_are_unchanged():
    pinned = {
        ROOT / "reports" / "W11" / "benchmark-manifest-W11.json": (
            "855c5beb55f15c6e5bcd38640ff3a6ff02a41a525bf3f1601722abdeca2d47f0"
        ),
        ROOT / "reports" / "W12" / "w12-manifest.json": (
            "ef06f9712203b39c01351ad89a17368574e98a0db6436f842e926b68418073a7"
        ),
        ROOT / "reports" / "W13" / "horizon-manifest-W13.json": (
            "02a76660319f6118900ec54ee3d50fa96968ad14b0a7110f3fdaf1b62417a404"
        ),
        ROOT / "reports" / "W14" / "w14-manifest.json": (
            "e4a0263ead067a10df8d23ffc2bb10d6e750c88e515153fd6f637c733077357d"
        ),
        ROOT / "reports" / "W15" / "w15-manifest.json": (
            "3f1a16939e1c16345e9948eb109085d123d3e57a57717132b0ab9c2d89d5eafa"
        ),
        ROOT / "reports" / "W15" / "model" / "model.ubj": MODEL_SHA256,
        ROOT / "reports" / "W15" / "model" / "model.json": (
            "67eef303104bca00a8a1669dcacf6b7ff08219fff493a99280d27086875f2efd"
        ),
        ROOT / "reports" / "W15" / "model" / "model-manifest-W15.json": (
            "85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e"
        ),
    }
    for path, digest in pinned.items():
        assert _sha256(path) == digest, path.name


# ---------------------------------------------------------------------------
# No-access proof: static imports
# ---------------------------------------------------------------------------


def test_preflight_module_imports_only_the_standard_library():
    imports = _module_imports(MODULE_PATH)
    assert imports == {
        "__future__",
        "hashlib",
        "json",
        "re",
        "dataclasses",
        "pathlib",
        "typing",
    }


def test_preflight_module_defines_no_evaluator_entry_points():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    function_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    forbidden = {
        "run_locked_evaluation",
        "evaluate_locked_test",
        "compute_locked_metrics",
        "run_test",
        "predict",
        "fit",
        "fit_model",
        "compute_ewt",
        "compute_aiw",
        "compute_average_precision",
    }
    assert function_names & forbidden == set()
    source = MODULE_PATH.read_text(encoding="utf-8")
    # Documentation may reference the canonical metric modules; executable code
    # must not import or call them.  Prove both sides:
    assert "xgboost" not in source
    assert "sklearn" not in source
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    for token in (
        "classification_metrics",
        "compute_ewt",
        "compute_aiw",
        "evaluate_events",
        "run_grouped_benchmark",
        "load_w11_bundle",
        "fit",
        "predict",
        "load_model",
    ):
        assert token not in called, token
    imports = _module_imports(MODULE_PATH)
    assert "coldguard_ml" not in imports


def test_preflight_module_has_no_write_or_subprocess_calls():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    forbidden = {
        "open",
        "read_text",
        "read_csv",
        "write_text",
        "write_bytes",
        "mkdir",
        "unlink",
        "remove",
        "eval",
        "exec",
        "__import__",
        "system",
        "Popen",
        "run",
        "load_model",
    }
    assert called & forbidden == set(), called & forbidden


def test_script_imports_only_metadata_readers():
    imports = _module_imports(SCRIPT_PATH)
    assert imports == {
        "__future__",
        "argparse",
        "hashlib",
        "json",
        "subprocess",
        "sys",
        "pathlib",
        "typing",
        "yaml",
        "coldguard_ml",
    }
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for token in (
        "run_grouped_benchmark",
        "build_labeled_dataset",
        "load_w11_bundle",
        "feature_matrix",
        "build_expanded_w11_fixture",
        "evaluate_events",
        "fit_final_candidate",
        "load_guarded_artifact",
        "compute_ewt",
        "compute_aiw",
        "load_benchmark_config",
        "load_registry",
    ):
        assert token not in source, token


def test_no_force_unlock_or_gate_bypass_option_exists():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for token in ("--force", "--ignore-gates", "--unlock", "ignore_gates"):
        assert token not in source, token
    module = _load_script_module()
    for flag in ("--force", "--unlock", "--ignore-gates"):
        with pytest.raises(SystemExit):
            module.main([flag])


# ---------------------------------------------------------------------------
# No-access proof: runtime instrumentation
# ---------------------------------------------------------------------------


def test_preflight_run_touches_only_declared_metadata(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    reads: list[Path] = []
    writes: list[Path] = []
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_write_bytes = Path.write_bytes

    def spy_read_text(self: Path, *args, **kwargs) -> str:
        reads.append(self.resolve())
        return real_read_text(self, *args, **kwargs)

    def spy_read_bytes(self: Path) -> bytes:
        reads.append(self.resolve())
        return real_read_bytes(self)

    def spy_write_bytes(self: Path, payload: bytes) -> int:
        writes.append(self.resolve())
        return real_write_bytes(self, payload)

    monkeypatch.setattr(Path, "read_text", spy_read_text)
    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)
    monkeypatch.setattr(Path, "write_bytes", spy_write_bytes)

    real_open = builtins.open

    def open_spy(file, *args, **kwargs):
        path = Path(str(file)).resolve()
        assert not _is_forbidden_payload(path), path
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", open_spy)

    module = _load_script_module()
    assert module.main(["--out", str(out_dir), "--repository-revision", "TEST-REV"]) == 0

    assert reads, "the preflight must read its declared metadata inputs"
    for path in reads:
        assert not _is_forbidden_payload(path), path
    for path in writes:
        assert out_dir.resolve() in path.parents, path
    produced = sorted(path.name for path in out_dir.iterdir())
    assert produced == ["locked-test-manifest-W16.json"]
    manifest = json.loads(
        (out_dir / "locked-test-manifest-W16.json").read_text(encoding="utf-8")
    )
    assert manifest["evaluation_status"] == "NOT_RUN"
    assert manifest["evaluation_disposition"]["metrics_reported"] is False


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_preflight_is_byte_deterministic_and_matches_the_committed_manifest(
    tmp_path,
):
    committed = _manifest()
    revision = committed["repository_revision"]
    module = _load_script_module()
    outputs = []
    for name in ("run-a", "run-b"):
        out_dir = tmp_path / name
        assert module.main(
            ["--out", str(out_dir), "--repository-revision", revision]
        ) == 0
        outputs.append((out_dir / "locked-test-manifest-W16.json").read_bytes())
    assert outputs[0] == outputs[1]

    # Re-running against the already generated manifest must change nothing.
    out_dir = tmp_path / "run-a"
    assert module.main(["--out", str(out_dir), "--repository-revision", revision]) == 0
    assert (out_dir / "locked-test-manifest-W16.json").read_bytes() == outputs[0]

    assert outputs[0] == MANIFEST_PATH.read_bytes()


def test_analysis_code_hash_recomputation_matches_the_manifest():
    module = _load_script_module()
    assert module._analysis_code_sha256(ROOT) == _manifest()["analysis_code_sha256"]


# ---------------------------------------------------------------------------
# Report family
# ---------------------------------------------------------------------------


def test_report_family_exists_and_binds_the_manifest():
    manifest_sha = _sha256(MANIFEST_PATH)
    documents = {
        "locked-test-result.md": (
            "NOT_RUN",
            "No AP",
            "unopened",
            manifest_sha,
        ),
        "model-card-rc.md": (
            "NOT_ISSUED",
            "NON_DEPLOYABLE_CANDIDATE",
            "no actual approved model release candidate",
            manifest_sha,
        ),
        "holdout-readiness-W16.md": (
            "G4_READY = false",
            "NOT_READY",
            manifest_sha,
        ),
        "locked-test-protocol-W16.md": (
            "one-time",
            "receipt",
            "NO_INTERPRETATION_TEST_NOT_RUN",
            "Post-test defect rule",
            manifest_sha,
        ),
    }
    for name, required in documents.items():
        path = REPORT_DIR / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert len(text) > 1000, name
        for phrase in required:
            assert phrase in text, (name, phrase)


def test_reports_do_not_imply_a_test_result_or_release():
    forbidden = (
        "AP = 0.",
        "AP is 0.",
        "EWT = 0",
        "AIW = 0",
        "model RC approved",
        "RELEASE_APPROVED",
        "test passed",
        "holdout was evaluated",
    )
    for path in REPORT_DIR.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, (path.name, phrase)
