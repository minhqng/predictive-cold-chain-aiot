"""W12 CLI artifacts, manifest hashes and deterministic replay."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ML_ROOT / "scripts" / "benchmark-g3-W12.py"
ARTIFACTS = (
    "benchmark-synthesis-W12.md",
    "grouped-metrics-W12.csv",
    "event-operational-summary-W12.csv",
    "ewt-assessment-W12.csv",
    "feature-importance-W12.csv",
    "gate-g3-W12.md",
    "gate-g3-evidence-matrix-W12.csv",
)


def _run(out: Path, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ML_ROOT / "src")
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--repository-revision",
            "TEST-REVISION",
            *extra,
        ],
        cwd=ML_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_cli_generates_all_artifacts_and_consistent_manifest(tmp_path):
    out = tmp_path / "W12"
    completed = _run(out)
    assert completed.returncode == 0, completed.stderr
    for name in ARTIFACTS:
        assert (out / name).exists(), name
    manifest = json.loads((out / "w12-manifest.json").read_text(encoding="utf-8"))
    for name, meta in manifest["artifacts"].items():
        assert _sha(out / name) == meta["sha256"], name
    assert manifest["deterministic"] is True
    assert manifest["scientific_verdicts"]["GATE_G3"] == "NO-GO / FIX DATA"
    assert manifest["scientific_verdicts"]["W12_SOFTWARE"] == "GREEN"
    assert manifest["scientific_verdicts"]["PHYSICAL_GATE_B"] == "RED"
    assert manifest["scientific_verdicts"]["REAL_EWT"] == "NOT_ESTIMABLE"
    assert manifest["scientific_verdicts"]["REAL_AIW"] == "NOT_ESTIMABLE"
    assert manifest["real_status"]["REAL_EWT_REASON_CODE"] != (
        manifest["real_status"]["REAL_AIW_REASON_CODE"]
    )


def test_cli_replay_is_byte_deterministic(tmp_path):
    out = tmp_path / "W12"
    first = _run(out)
    assert first.returncode == 0, first.stderr
    snapshot = {
        name: (out / name).read_bytes() for name in (*ARTIFACTS, "w12-manifest.json")
    }
    second = _run(out)
    assert second.returncode == 0, second.stderr
    for name, payload in snapshot.items():
        assert (out / name).read_bytes() == payload, name


def test_cli_is_read_only_for_a_and_d_evidence(tmp_path):
    watched = (
        ML_ROOT.parent / "evidence/A/W24/acceptance-census.json",
        ML_ROOT.parent / "evidence/A/W09/exports/CG-S1-H8C-600S.json",
        ML_ROOT.parent / "evidence/D/W01/hazard-ledger-v0.md",
    )
    before = {str(path): _sha(path) for path in watched}
    completed = _run(tmp_path / "W12")
    assert completed.returncode == 0, completed.stderr
    after = {str(path): _sha(path) for path in watched}
    assert before == after


def test_cli_refuses_broken_source_bundle(tmp_path):
    out = tmp_path / "W12"
    missing = tmp_path / "missing-W11"
    completed = _run(out, "--w11-reports", str(missing))
    assert completed.returncode == 2
    assert "REFUSED" in completed.stderr
