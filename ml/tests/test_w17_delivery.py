"""W17 delivery integrity, determinism and scientific-boundary proofs.

These tests bind the committed W17 report family to the generated code and
verify that the W17 delivery does not change any W11-W16 artifact, open the
locked test, issue a model RC, or claim live shadow acceptance.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "W17"
MANIFEST_PATH = REPORT_DIR / "w17-manifest.json"
SCRIPT_PATH = ROOT / "scripts" / "w17-shadow-replay-W17.py"
W15_MODEL_DIR = ROOT / "reports" / "W15" / "model"
W16_MANIFEST = ROOT / "reports" / "W16" / "locked-test-manifest-W16.json"
EXPECTED_REPORTS = (
    "online-offline-parity-W17.md",
    "feature-freshness-W17.md",
    "shadow-readiness-W17.md",
    "shadow-trace-W17.json",
    "w17-manifest.json",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_driver():
    spec = importlib.util.spec_from_file_location(
        "w17_shadow_replay_driver", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _trace() -> dict:
    return json.loads(
        (REPORT_DIR / "shadow-trace-W17.json").read_text(encoding="utf-8")
    )


def _iter_keys(payload):
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield key
            yield from _iter_keys(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_keys(item)


# ---------------------------------------------------------------------------
# Delivery integrity
# ---------------------------------------------------------------------------


def test_committed_report_family_exists():
    for name in EXPECTED_REPORTS:
        assert (REPORT_DIR / name).is_file(), name


def test_manifest_binds_every_report_and_trace():
    manifest = _manifest()
    for name in (
        "online-offline-parity-W17.md",
        "feature-freshness-W17.md",
        "shadow-readiness-W17.md",
    ):
        assert manifest["reports"][name] == _sha256(REPORT_DIR / name)
    trace = manifest["shadow_trace"]
    assert trace["file_sha256"] == _sha256(REPORT_DIR / "shadow-trace-W17.json")
    assert trace["internal_sha256"] == _trace()["trace_sha256"]
    assert trace["record_count"] == _trace()["record_count"]


def test_manifest_verdicts_are_honest():
    verdicts = _manifest()["verdicts"]
    assert verdicts["B_W17_01_FEATURE_PARITY"] == "OFFLINE_FEATURE_PARITY_VERIFIED"
    assert (
        verdicts["B_W17_01_PREDICTION_PARITY"]
        == "OFFLINE_PREDICTION_PARITY_VERIFIED"
    )
    assert verdicts["B_W17_02_SHADOW_TRACE"] == "SHADOW_TRACE_SOFTWARE_VERIFIED"
    assert verdicts["B_W17_03_FEATURE_FRESHNESS"] == "SOFTWARE_VERIFIED"
    assert verdicts["B_W17_04_REAL_SHADOW_READINESS"] == "LIVE_SHADOW_NOT_ESTABLISHED"
    assert verdicts["W16_HOLDOUT"] == "NOT_OPENED"
    assert verdicts["G4"] == "NOT_READY"
    assert verdicts["LIVE_SHADOW"] == "LIVE_SHADOW_NOT_ESTABLISHED"
    assert verdicts["PHYSICAL_SHADOW"] == "PHYSICAL_SHADOW_BLOCKED"
    assert "SHADOW PASS" not in json.dumps(verdicts)


def test_manifest_records_no_physical_or_command_capability():
    manifest = _manifest()
    assert manifest["physical_control_capability"] is False
    assert manifest["command_transport_capability"] is False
    assert manifest["network_capability"] is False
    assert manifest["model_registered"] is False
    assert manifest["physical_controller_b"] == "NOT_ENABLED"
    for record in _trace()["records"]:
        policy = record["hypothetical_policy"]
        assert policy["dispatchable"] is False
        assert policy["would_command"] is None
        assert policy["authorized_control_decision"] is None


def test_manifest_contains_no_timestamp_or_temp_path():
    text = MANIFEST_PATH.read_text(encoding="utf-8")
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text)
    assert "\\\\Temp" not in text
    assert "tmp" not in text.lower()
    for name in (
        "online-offline-parity-W17.md",
        "feature-freshness-W17.md",
        "shadow-readiness-W17.md",
    ):
        report = (REPORT_DIR / name).read_text(encoding="utf-8")
        assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", report)


def test_development_and_locked_test_runs_are_disjoint():
    manifest = _manifest()
    development = set(manifest["fixture"]["run_ids"])
    locked = set(manifest["w16_readiness"]["test_runs"])
    assert development
    assert locked
    assert development & locked == set()
    assert manifest["w16_readiness"]["development_test_overlap"] == []
    assert manifest["fixture"]["locked_test_used"] is False


def test_w16_holdout_and_model_rc_states_are_preserved():
    manifest = _manifest()
    w16 = manifest["w16_readiness"]
    assert w16["holdout_access"] == "NOT_AUTHORIZED"
    assert w16["holdout_opened"] is False
    assert w16["evaluation_status"] == "NOT_RUN"
    assert w16["locked_evaluation"] == "NOT_EXECUTED_PREREQUISITES_UNMET"
    assert w16["model_release_candidate"] == "NOT_ISSUED"
    assert w16["g4_ready"] is False
    assert w16["manifest_sha256"] == _sha256(W16_MANIFEST)


def test_w15_model_contract_is_bound_and_unchanged():
    manifest = _manifest()
    model = manifest["model_artifact"]
    assert model["model_artifact_sha256"] == _sha256(W15_MODEL_DIR / "model.ubj")
    assert (
        model["model_artifact_sha256"]
        == "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f"
    )
    assert model["feature_schema_hash"] == manifest["feature_registry"]["registry_sha256"]
    assert model["release_eligibility"] == "NON_DEPLOYABLE_CANDIDATE"
    assert model["data_evidence_class"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    assert model["score_semantics"] == "risk_score"
    assert model["calibration_status"] == "RISK_SCORE_ONLY"
    assert model["horizon_status"] == "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN"
    assert model["operating_threshold_status"] == "ILLUSTRATIVE_NOT_FROZEN"
    assert model["warning_persistence_status"] == "NOT_FROZEN"
    assert len(model["ordered_feature_ids"]) == 28


def test_no_scientific_metrics_are_fabricated():
    trace = _trace()
    forbidden = {"average_precision", "ap", "precision", "recall", "f1"}
    for record in trace["records"]:
        keys = {key.lower() for key in _iter_keys(record)}
        assert keys & forbidden == set()
        assert record["hypothetical_timing"]["aiw"] == "NOT_ESTIMABLE"
        assert record["hypothetical_timing"]["physical_latency"] == "NOT_MEASURED"
    manifest = _manifest()
    assert manifest["parity"]["feature_comparison_count"] >= 1
    assert manifest["w16_readiness"]["model_release_candidate"] == "NOT_ISSUED"


def test_external_dependency_snapshot_is_explicit():
    dependencies = _manifest()["external_dependency_states"]
    assert dependencies["member_a_w17_shadow_audit"] == (
        "DATA_INSUFFICIENT_ZERO_SYNCHRONIZED_RUNS"
    )
    assert dependencies["member_c_pr_73_shadow_trace"] == (
        "OPEN_UNMERGED_NOT_INTEGRATION_ACCEPTANCE"
    )
    assert dependencies["member_d_shadow_policy"] == "NOT_FROZEN"
    assert dependencies["runtime_freshness_policy"] == "PENDING_C_D"
    assert dependencies["gate_g4"] == "NOT_READY"
    assert _manifest()["external_dependency_semantics"] == (
        "INTERFACE_AUDIT_SNAPSHOT_AT_IMPLEMENTATION"
    )


def test_w16_test_count_reconciliation_is_arithmetically_consistent():
    record = _manifest()["w16_test_count_reconciliation"]
    assert (
        record["w15_base_collected"] + record["w16_added_test_functions"]
        == record["w16_collected"]
    )
    assert record["actual_passed"] + record["actual_skipped"] == record["w16_collected"]
    assert (
        record["pr_105_body_passed"] + record["pr_105_body_skipped"]
        == record["pr_105_body_collected"]
    )
    assert record["w16_collected"] - record["pr_105_body_collected"] == 6
    assert record["conclusion"] == "STALE_PR_BODY_NOT_A_DELIVERED_REGRESSION"


def test_late_delivery_is_injected_and_recorded():
    parity = _manifest()["parity"]
    late = parity["late_delivery"]
    assert late["injected"] is True
    assert late["scheduled_arrival_s"] == 60.0
    assert late["default_transport_delay_s"] == 0.25
    assert parity["late_observation_count"] >= 1


def test_freshness_verdict_is_derived_from_probes():
    driver = _load_driver()
    probes = _manifest()["freshness"]["probes"]
    verified, failure = driver._freshness_verified(probes)
    assert verified is True
    assert failure is None
    broken = json.loads(json.dumps(probes))
    for probe in broken:
        if probe["probe"] == "stale_pzem":
            probe["outcome"] = "UNEXPECTED"
    verified, failure = driver._freshness_verified(broken)
    assert verified is False
    assert failure.startswith("PROBE_stale_pzem")
    zero_filled = json.loads(json.dumps(probes))
    for probe in zero_filled:
        if probe["probe"] == "stale_pzem":
            probe["detail"]["cooling_power_is_zero"] = True
    verified, failure = driver._freshness_verified(zero_filled)
    assert verified is False
    assert failure == "STALE_PZEM_WAS_ZERO_FILLED"
    counter = json.loads(json.dumps(probes))
    for probe in counter:
        if probe["probe"] == "counter_reset":
            probe["detail"]["energy_counter_reason"] = "MISSING_INPUT"
    verified, failure = driver._freshness_verified(counter)
    assert verified is False
    assert failure == "COUNTER_RESET_NOT_MISSING"


def test_manifest_freshness_verdict_matches_the_probe_matrix():
    freshness = _manifest()["freshness"]
    assert freshness["verdict"] == "SOFTWARE_VERIFIED"
    assert freshness["failure_reason"] is None


def test_source_revision_is_the_verified_w16_base():
    manifest = _manifest()
    assert manifest["source_revision"] == (
        "c2b62234466b09585cf4e868c67a4d49ae06597f"
    )
    assert manifest["revision_semantics"] == (
        "W16_STACK_HEAD_BASE_NOT_W17_DELIVERY_COMMIT"
    )


def test_reports_contain_the_required_sections():
    parity = (REPORT_DIR / "online-offline-parity-W17.md").read_text(
        encoding="utf-8"
    )
    assert "## Verdicts" in parity
    assert "## Unused-feature mutation proof" in parity
    assert "## Provenance and boundaries" in parity
    freshness = (REPORT_DIR / "feature-freshness-W17.md").read_text(
        encoding="utf-8"
    )
    assert "## Clock domains" in freshness
    assert "## Disposition rules" in freshness
    assert "## Executable probes" in freshness
    readiness = (REPORT_DIR / "shadow-readiness-W17.md").read_text(
        encoding="utf-8"
    )
    assert "## Four levels" in readiness
    assert "## Team dependencies" in readiness
    assert "## One next Member B action" in readiness


# ---------------------------------------------------------------------------
# Determinism and reproducibility
# ---------------------------------------------------------------------------


def test_analysis_code_hash_matches_the_manifest():
    driver = _load_driver()
    assert driver._analysis_code_sha256() == _manifest()["analysis_code_sha256"]


def test_committed_reports_match_a_fresh_generation(tmp_path):
    driver = _load_driver()
    revision = _manifest()["source_revision"]
    out_dir = tmp_path / "fresh"
    assert driver.main(
        ["--out-dir", str(out_dir), "--source-revision", revision]
    ) == 0
    for name in EXPECTED_REPORTS:
        assert (out_dir / name).read_bytes() == (REPORT_DIR / name).read_bytes(), name


def test_driver_is_byte_deterministic_across_independent_processes(tmp_path):
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
