"""W19 delivery controls: determinism, hash binding, scope and capability."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from coldguard_ml.w19_no_peeking import W19OutcomeExposureError

ML_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ML_ROOT / "scripts" / "w19-campaign-audit-W19.py"
REPORTS_DIR = ML_ROOT / "reports" / "W19"

EXPECTED_REPORTS = (
    "pair-ledger-contract-W19.md",
    "validity-discipline-W19.md",
    "no-significance-peeking-W19.md",
    "campaign-readiness-W19.md",
)

PINNED_EARLIER_ARTIFACTS = {
    "reports/W15/model/model-manifest-W15.json": "85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e",
    "reports/W16/locked-test-manifest-W16.json": "6e7e7f23881785f76463344663e08f0cf626f5ee137aa1f98a99772e1a1fe165",
    "reports/W17/w17-manifest.json": "8b2e92e7c70134e5ab0c6ac796c900b681bc7d66f79eddb48ecc939ddcc33532",
    "reports/W18/w18-manifest.json": "bd1391d72d030af5e0ca99540059424fbf45ca1ccced255e8d41ca374799c9ab",
    "reports/W18/freeze-baseline-W18.json": "d1bcc8ff26ed28ed998fb2c43d7fa57ab928d6c4d90c1af801289016dd446581",
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
}


def _load_driver():
    spec = importlib.util.spec_from_file_location("w19_campaign_audit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver():
    return _load_driver()


@pytest.fixture(scope="module")
def generated(driver, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("w19-generated")
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
    assert set(_files(out_dir)) == set(EXPECTED_REPORTS) | {"w19-manifest.json"}


def test_manifest_binds_every_report_hash(generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w19-manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["reports"]) == set(EXPECTED_REPORTS)
    for name, digest in manifest["reports"].items():
        assert hashlib.sha256((out_dir / name).read_bytes()).hexdigest() == digest


def test_analysis_code_hash_matches_the_manifest(driver, generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w19-manifest.json").read_text(encoding="utf-8"))
    assert manifest["analysis_code_sha256"] == driver._analysis_code_sha256()


def test_committed_reports_match_a_fresh_generation(generated):
    out_dir, _ = generated
    assert REPORTS_DIR.is_dir(), "run the W19 driver into ml/reports/W19 first"
    for name in (*EXPECTED_REPORTS, "w19-manifest.json"):
        committed = (REPORTS_DIR / name).read_bytes()
        fresh = (out_dir / name).read_bytes()
        assert committed == fresh, f"{name} is stale; regenerate reports/W19"


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


def test_w19_sources_carry_no_runtime_or_outcome_imports(driver):
    import ast

    for path in driver.W19_SOURCE_FILES:
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


def test_manifest_keeps_physical_evidence_unestablished(generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w19-manifest.json").read_text(encoding="utf-8"))
    assert manifest["verdicts"]["PHYSICAL_PAIRS"] == "NOT_ESTABLISHED"
    assert manifest["verdicts"]["CAMPAIGN_TARGET"] == "UNFROZEN"
    assert manifest["verdicts"]["FINAL_CAMPAIGN"] == "NOT_AUTHORIZED"
    assert manifest["verdicts"]["W20_ANALYSIS"] == "NOT_UNLOCKED"
    assert manifest["verdicts"]["G4"] == "NOT_READY"
    assert manifest["campaign_state"]["pairs_recorded"] == 0
    assert manifest["fixture_validation"]["admitted_to_physical_campaign"] is False
    assert manifest["campaign_state"]["w16_holdout"]["status"] == "NOT_OPENED"


def test_manifest_records_the_frozen_sign_convention_without_computing_it(generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w19-manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["no_peeking"]["registered_sign_convention"]
        == "I_i = Y_A,i - Y_B,i"
    )
    assert manifest["validity_discipline"]["method"]
    report = (out_dir / "no-significance-peeking-W19.md").read_text(encoding="utf-8")
    assert "P_VALUE_COMPUTED = NONE" in report
    assert "PAIRED_EFFECT_COMPUTED = NONE" in report


def test_manifest_capabilities_are_all_false(generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w19-manifest.json").read_text(encoding="utf-8"))
    assert manifest["capabilities"]
    assert all(value is False for value in manifest["capabilities"].values())


def test_all_adversarial_controls_pass(generated):
    out_dir, _ = generated
    manifest = json.loads((out_dir / "w19-manifest.json").read_text(encoding="utf-8"))
    controls = manifest["adversarial_controls"]
    assert controls["probe_count"] >= 25
    assert controls["probes_passed"] == controls["probe_count"]
    assert all(probe["passed"] for probe in controls["probes"])


def test_driver_refuses_an_outcome_bearing_campaign_record(driver, tmp_path, monkeypatch):
    records = tmp_path / "campaign-records.json"
    records.write_text(
        json.dumps(
            {
                "pairs": [],
                "attempts": [
                    {
                        "attempt_id": "ATT-BAD",
                        "thermal_exposure": 11.2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(driver, "CAMPAIGN_RECORDS", records)
    with pytest.raises(W19OutcomeExposureError):
        driver.generate(tmp_path / "out")


def test_driver_main_returns_two_on_a_malformed_record(driver, tmp_path, monkeypatch):
    records = tmp_path / "campaign-records.json"
    records.write_text(
        json.dumps(
            {
                "campaign_authorization": {
                    "authorized": True,
                    "unexpected": "field",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(driver, "CAMPAIGN_RECORDS", records)
    assert driver.main(["--out-dir", str(tmp_path / "out")]) == 2


def test_manifest_records_no_machine_absolute_paths(generated):
    out_dir, _ = generated
    text = (out_dir / "w19-manifest.json").read_text(encoding="utf-8")
    assert "worktree-b-w19" not in text
    assert "D:\\\\" not in text
    manifest = json.loads(text)
    for entry in manifest["generation_inputs"].values():
        assert not entry["path"].startswith("D:")
    scanned = manifest["no_peeking"]["source_capability_audit"]["files_scanned"]
    assert scanned
    assert all(not path.startswith("D:") for path in scanned)


def test_w19_files_are_confined_to_member_b_ownership():
    for path in [
        ML_ROOT / "src" / "coldguard_ml" / "w19_no_peeking.py",
        ML_ROOT / "src" / "coldguard_ml" / "w19_validity.py",
        ML_ROOT / "src" / "coldguard_ml" / "w19_pair_ledger.py",
        ML_ROOT / "src" / "coldguard_ml" / "w19_progress.py",
        SCRIPT,
    ]:
        assert path.is_file()
        assert path.parent.name in {"coldguard_ml", "scripts"}
