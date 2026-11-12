"""W18 delivery integrity, determinism and no-command proofs."""

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

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "W18"
MANIFEST_PATH = REPORT_DIR / "w18-manifest.json"
SCRIPT_PATH = ROOT / "scripts" / "w18-runtime-audit-W18.py"
W15_MODEL_DIR = ROOT / "reports" / "W15" / "model"
W16_MANIFEST = ROOT / "reports" / "W16" / "locked-test-manifest-W16.json"
W17_DIR = ROOT / "reports" / "W17"
W17_TRACE = W17_DIR / "shadow-trace-W17.json"
A_W18_DIR = ROOT.parent / "evidence" / "A" / "W18"
EXPECTED_REPORTS = (
    "runtime-monitor-W18.md",
    "predictive-trace-W18.md",
    "no-online-tuning-W18.md",
    "controller-b-readiness-W18.md",
    "w18-manifest.json",
)

W15_MODEL_SHA256 = (
    "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f"
)
W15_MANIFEST_SHA256 = (
    "85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e"
)
W16_MANIFEST_SHA256 = (
    "6e7e7f23881785f76463344663e08f0cf626f5ee137aa1f98a99772e1a1fe165"
)
W17_MANIFEST_SHA256 = (
    "8b2e92e7c70134e5ab0c6ac796c900b681bc7d66f79eddb48ecc939ddcc33532"
)
W17_TRACE_SHA256 = (
    "b94822dea729cbf8953fe95b254a80689daa1c6c5bdd4a7fa442be0964eeb023"
)
FREEZE_BASELINE = ROOT / "reports" / "W18" / "freeze-baseline-W18.json"
FREEZE_BASELINE_SHA256 = (
    "d1bcc8ff26ed28ed998fb2c43d7fa57ab928d6c4d90c1af801289016dd446581"
)

FORBIDDEN_IMPORT_ROOTS = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "requests",
    "httpx",
    "paho",
    "pymongo",
    "serial",
    "smbus",
    "RPi",
    "gpiozero",
    "subprocess",
    "multiprocessing",
    "asyncio",
}
FORBIDDEN_CALL_NAMES = {
    "publish",
    "dispatch",
    "actuate",
    "energize",
    "publish_command",
    "send_command",
    "connect_broker",
    "open_device",
}
W18_SOURCE_FILES = (
    ROOT / "src" / "coldguard_ml" / "w18_runtime_monitor.py",
    ROOT / "src" / "coldguard_ml" / "w18_trace_integrity.py",
    ROOT / "src" / "coldguard_ml" / "w18_freeze_audit.py",
    ROOT / "src" / "coldguard_ml" / "w18_readiness.py",
    SCRIPT_PATH,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_driver():
    spec = importlib.util.spec_from_file_location(
        "w18_runtime_audit_driver", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_pinned_baseline_artifacts_are_unchanged():
    assert _sha256(W15_MODEL_DIR / "model.ubj") == W15_MODEL_SHA256
    assert (
        _sha256(W15_MODEL_DIR / "model-manifest-W15.json")
        == W15_MANIFEST_SHA256
    )
    assert _sha256(W16_MANIFEST) == W16_MANIFEST_SHA256
    assert _sha256(W17_DIR / "w17-manifest.json") == W17_MANIFEST_SHA256
    assert _sha256(W17_TRACE) == W17_TRACE_SHA256
    assert _sha256(FREEZE_BASELINE) == FREEZE_BASELINE_SHA256


def test_analysis_code_hash_matches_the_manifest():
    assert (
        _load_driver()._analysis_code_sha256()
        == _manifest()["analysis_code_sha256"]
    )


def test_committed_reports_match_a_fresh_generation(tmp_path):
    driver = _load_driver()
    revision = _manifest()["source_revision"]
    out_dir = tmp_path / "fresh"
    assert driver.main(["--out-dir", str(out_dir), "--source-revision", revision]) == 0
    assert set(path.name for path in out_dir.iterdir()) == set(EXPECTED_REPORTS)
    for name in EXPECTED_REPORTS:
        assert (out_dir / name).read_bytes() == (REPORT_DIR / name).read_bytes(), name


def test_driver_is_byte_deterministic_across_processes(tmp_path):
    revision = _manifest()["source_revision"]
    outputs = []
    for name in ("process-a", "process-b"):
        out_dir = tmp_path / name
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--out-dir",
                str(out_dir),
                "--source-revision",
                revision,
            ],
            cwd=str(ROOT),
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        outputs.append(out_dir)
    for name in EXPECTED_REPORTS:
        assert (outputs[0] / name).read_bytes() == (
            outputs[1] / name
        ).read_bytes(), name


def test_manifest_binds_actual_artifact_hashes():
    manifest = _manifest()
    inputs = manifest["generation_inputs"]
    assert inputs["w15_model"]["model_sha256"] == W15_MODEL_SHA256
    assert inputs["w15_model"]["manifest_sha256"] == W15_MANIFEST_SHA256
    assert inputs["w16_readiness"]["manifest_sha256"] == W16_MANIFEST_SHA256
    assert inputs["w17_shadow"]["manifest_sha256"] == W17_MANIFEST_SHA256
    assert inputs["w17_shadow"]["trace_file_sha256"] == W17_TRACE_SHA256
    assert inputs["freeze_baseline"]["sha256"] == FREEZE_BASELINE_SHA256
    for name, digest in manifest["reports"].items():
        assert _sha256(REPORT_DIR / name) == digest, name
    for relative, entry in inputs["member_a_w18"]["files"].items():
        path = A_W18_DIR / relative
        if path.is_file():
            assert entry["sha256"] == _sha256(path), relative


def test_manifest_verdicts_are_derived_and_limited():
    verdicts = _manifest()["verdicts"]
    assert verdicts["B_W18_01_MODEL_MONITORING"] == "SOFTWARE_VERIFIED"
    assert verdicts["B_W18_02_TRACE_VALIDATION"] == "SOFTWARE_VERIFIED"
    assert verdicts["PHYSICAL_INTERVENTION_TRACE"] == "NOT_ESTABLISHED"
    assert verdicts["B_W18_03_NO_ONLINE_TUNING"] == "SOFTWARE_VERIFIED"
    assert verdicts["B_W18_04_CONTROLLER_B_READINESS"] == "SIGNOFF_WITHHELD"
    assert verdicts["G4"] == "NOT_READY"
    assert verdicts["W16_HOLDOUT"] == "NOT_OPENED"
    assert verdicts["MODEL_RC"] == "NOT_ISSUED"
    assert verdicts["W17_LIVE_SHADOW"] == "LIVE_SHADOW_NOT_ESTABLISHED"
    assert verdicts["DELIVERY"] == "PENDING_PUBLICATION"
    assert verdicts["SOFTWARE"] == "COMPLETE_PERMITTED_W18_SCOPE"


def test_readiness_withholds_signoff():
    readiness = _manifest()["readiness"]
    assert readiness["signoff"] == "WITHHELD"
    assert readiness["signoff_withheld"] is True
    assert readiness["gate_g4"] == "NOT_READY"
    assert readiness["physical_intervention_trace"] == "NOT_ESTABLISHED"
    assert readiness["model_release"] == "NOT_ISSUED"
    assert readiness["approval_effect"] == "NONE_SOFTWARE_ASSESSMENT_ONLY"
    assert readiness["fake_approval_detected"] is False


def test_capabilities_are_all_false():
    capabilities = _manifest()["capabilities"]
    assert capabilities
    assert all(value is False for value in capabilities.values())


def test_manifest_records_external_open_interfaces():
    external = _manifest()["external_dependency_states"]
    assert external["member_c_pr_73_shadow_trace"].startswith("OPEN_UNMERGED")
    assert external["member_c_pr_74_controller_b_lifecycle"].startswith(
        "OPEN_UNMERGED"
    )
    assert external["member_d_predictive_policy"] == "NOT_FROZEN"
    assert external["gate_g4"] == "NOT_READY"
    assert external["runtime_freshness_policy"] == "PENDING_C_D"


def test_fixture_never_becomes_physical_evidence():
    manifest = _manifest()
    fixture = manifest["fixture_trace_assessment"]
    assert fixture["evidence_class"] == "TEST_ONLY_SYNTHETIC_FIXTURE"
    assert fixture["fixture"] is True
    assert fixture["physical_verified"] is False
    assert fixture["authorized_control"] is False
    assert fixture["real_intervention"] is False
    assert fixture["controller_b_acceptance"] is False
    w17 = manifest["w17_trace_assessment"]
    assert w17["outcome"] == "TRACE_PARTIAL_MISSING_EVIDENCE"
    assert w17["records_copied"] is False
    assert w17["physical_chain_status"].startswith("PHYSICAL_CHAIN_UNAVAILABLE")


def test_driver_does_not_modify_earlier_artifacts(tmp_path):
    before = {
        "w15_model": _sha256(W15_MODEL_DIR / "model.ubj"),
        "w15_manifest": _sha256(W15_MODEL_DIR / "model-manifest-W15.json"),
        "w16_manifest": _sha256(W16_MANIFEST),
        "w17_manifest": _sha256(W17_DIR / "w17-manifest.json"),
        "w17_trace": _sha256(W17_TRACE),
        "w17_parity": _sha256(W17_DIR / "online-offline-parity-W17.md"),
        "w17_freshness": _sha256(W17_DIR / "feature-freshness-W17.md"),
        "w17_readiness": _sha256(W17_DIR / "shadow-readiness-W17.md"),
    }
    assert _load_driver().main(["--out-dir", str(tmp_path / "run")]) == 0
    after = {
        "w15_model": _sha256(W15_MODEL_DIR / "model.ubj"),
        "w15_manifest": _sha256(W15_MODEL_DIR / "model-manifest-W15.json"),
        "w16_manifest": _sha256(W16_MANIFEST),
        "w17_manifest": _sha256(W17_DIR / "w17-manifest.json"),
        "w17_trace": _sha256(W17_TRACE),
        "w17_parity": _sha256(W17_DIR / "online-offline-parity-W17.md"),
        "w17_freshness": _sha256(W17_DIR / "feature-freshness-W17.md"),
        "w17_readiness": _sha256(W17_DIR / "shadow-readiness-W17.md"),
    }
    assert before == after


def test_reports_are_deterministic_text_without_wall_clock():
    timestamp = re.compile(r"\b20\d{2}-\d{2}-\d{2}T?\d{0,2}:?\d{0,2}")
    for name in EXPECTED_REPORTS:
        text = (REPORT_DIR / name).read_text(encoding="utf-8")
        assert "generated_at" not in text.lower(), name
        assert "timestamp" not in text.lower(), name
        assert timestamp.search(text) is None, name


def test_reports_never_claim_physical_verification():
    text = "\n".join(
        (REPORT_DIR / name).read_text(encoding="utf-8")
        for name in EXPECTED_REPORTS
    )
    lowered = text.lower()
    assert "physical_verified=true" not in lowered
    assert "controller_b_acceptance=true" not in lowered
    assert "authorized_control=true" not in lowered


def test_no_command_or_network_capability_in_w18_sources():
    for path in W18_SOURCE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root not in FORBIDDEN_IMPORT_ROOTS, (path.name, root)
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root not in FORBIDDEN_IMPORT_ROOTS, (path.name, root)
            elif isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_CALL_NAMES, (
                    path.name,
                    node.attr,
                )
            elif isinstance(node, ast.Name):
                assert node.id not in FORBIDDEN_CALL_NAMES, (path.name, node.id)


def test_only_w18_files_are_generated(tmp_path):
    out_dir = tmp_path / "scope"
    assert _load_driver().main(["--out-dir", str(out_dir)]) == 0
    assert sorted(path.name for path in out_dir.iterdir()) == sorted(
        EXPECTED_REPORTS
    )
    assert not any("W19" in path.name for path in out_dir.iterdir())


def test_driver_refuses_if_w18_holdout_were_opened(monkeypatch, tmp_path):
    driver = _load_driver()

    class FakeManifest(dict):
        pass

    original = driver._read_json

    def fake_read(path, label):
        payload = original(path, label)
        if label == "W16 locked-test manifest":
            payload = FakeManifest(payload)
            payload["holdout_opened"] = True
        return payload

    monkeypatch.setattr(driver, "_read_json", fake_read)
    with pytest.raises(driver.W18DriverError):
        driver.generate(tmp_path / "refused")
