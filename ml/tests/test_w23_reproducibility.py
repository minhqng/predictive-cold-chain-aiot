"""W23 reproducibility controls: environment, determinism, skips, boundaries.

Adversarial probes E41–E50.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
MANIFEST_PATH = ML_ROOT / "reports" / "W23" / "evidence-package-W23.json"
SCRIPT = ML_ROOT / "scripts" / "w23-evidence-audit-W23.py"
RUNBOOK = ML_ROOT / "reports" / "W23" / "reproducibility-runbook-W23.md"
RECEIPT = ML_ROOT / "reports" / "W23" / "clean-room-replay-W23.md"

import importlib.util


def _load_audit():
    spec = importlib.util.spec_from_file_location("w23_audit_repro", SCRIPT)
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


def _run_audit(out_dir: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    args = [
        sys.executable,
        str(SCRIPT),
        "--manifest",
        str(MANIFEST_PATH),
        "--root",
        str(REPO_ROOT),
        "--out",
        str(out_dir),
    ]
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


def test_e41_no_hidden_absolute_path_dependency(manifest):
    # Probe 41.
    source = SCRIPT.read_text(encoding="utf-8")
    assert "D:\\" not in source
    assert "/d/iot" not in source
    assert "C:\\" not in source
    for entry in manifest["sources"]:
        assert not Path(entry["path"]).is_absolute()
        assert ".." not in Path(entry["path"]).parts


def test_e42_no_undeclared_environment_variable_is_required(tmp_path):
    # Probe 42: run with a minimal environment, no PYTHONPATH, no COLDGUARD_*.
    env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    result = _run_audit(tmp_path / "audit", env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(
        (tmp_path / "audit" / "audit-result.json").read_text(encoding="utf-8")
    )
    assert payload["integrity_ok"] is True


def test_e43_unpinned_external_source_is_not_silently_loaded(audit, manifest):
    # Probe 43.
    result = audit.verify_package(manifest, REPO_ROOT)
    by_id = {entry["source_id"]: entry for entry in result["entries"]}
    for entry in manifest["sources"]:
        if entry["availability"] == "DECLARED_ONLY":
            assert by_id[entry["source_id"]]["status"] == "DECLARED_HASH_NOT_RECOMPUTED"
            assert by_id[entry["source_id"]]["observed_sha256"] is None
    for entry in manifest["sources"]:
        if entry["availability"] == "SOURCE_UNAVAILABLE":
            assert by_id[entry["source_id"]]["status"] == "SOURCE_UNAVAILABLE"


def test_e44_skipped_test_is_not_reported_as_pass():
    # Probe 44.
    text = RECEIPT.read_text(encoding="utf-8")
    payload = json.loads(
        re.search(r"```json\n(.*?)\n```", text, re.DOTALL).group(1)
    )
    tests = payload["tests"]
    assert tests["failed"] == 0
    assert tests["skipped"] == 4
    assert len(tests["skip_reasons"]) == 4
    assert tests["passed"] + tests["skipped"] == tests["collected"]
    joined = " ".join(tests["skip_reasons"])
    assert "20261107" in joined
    assert "A-W21" in joined or "A checkout" in joined
    assert "SKIPPED_AS_PASS" not in text


def test_e45_two_processes_generate_identical_outputs(tmp_path):
    # Probe 45.
    first = tmp_path / "run1"
    second = tmp_path / "run2"
    r1 = _run_audit(first)
    r2 = _run_audit(second)
    assert r1.returncode == 0, r1.stderr
    assert r2.returncode == 0, r2.stderr
    assert r1.stdout == r2.stdout
    assert (first / "audit-result.json").read_bytes() == (
        second / "audit-result.json"
    ).read_bytes()
    assert (first / "audit-summary.md").read_bytes() == (
        second / "audit-summary.md"
    ).read_bytes()


def test_e46_receipt_does_not_claim_another_member_executed_it(manifest):
    # Probe 46.
    clean_room = manifest["clean_room"]
    assert clean_room["independent_team_member_replay"] == "PENDING"
    text = RECEIPT.read_text(encoding="utf-8")
    assert "INDEPENDENT_TEAM_MEMBER_REPLAY = PENDING" in text
    assert "not claimed" in text.lower()
    assert not re.search(r"signed by|executed by [A-Z][a-z]+ [A-Z][a-z]+", text)


def test_e47_original_worktree_cache_cannot_mask_a_missing_file(audit, manifest, tmp_path):
    # Probe 47: a temp root missing a required package file must fail.
    result = audit.verify_package(manifest, tmp_path)
    assert result["integrity_ok"] is False
    missing = [item for item in result["violations"] if item.startswith("MISSING:")]
    assert missing
    assert any("B-W15-MODEL-UBJ" in item for item in missing)


def test_e48_hashes_do_not_pass_from_a_stale_duplicate(audit, manifest, tmp_path):
    # Probe 48: exact declared paths are used; duplicate paths are refused.
    seen = [entry["path"] for entry in manifest["sources"]]
    assert len(seen) == len(set(seen))
    forged = json.loads(json.dumps(manifest))
    duplicate = dict(forged["sources"][0])
    duplicate["source_id"] = "B-STALE-DUPLICATE"
    forged["sources"].append(duplicate)
    with pytest.raises(audit.ManifestError):
        audit.validate_manifest(forged)
    source = SCRIPT.read_text(encoding="utf-8")
    assert "glob(" not in source
    assert "rglob(" not in source


def test_e49_unmerged_external_evidence_is_not_copied(manifest):
    # Probe 49.
    for entry in manifest["sources"]:
        if entry["availability"] != "LOCAL":
            continue
        assert "pr95" not in entry["path"].lower()
        assert "feat/a-w21-evidence-final" not in entry["path"]
        assert "evidence/C/" not in entry["path"]
    external = {row["dependency_id"]: row for row in manifest["external_dependencies"]}
    assert external["A-PR-95"]["observed_status"] == "OPEN_UNMERGED"
    assert external["A-PR-95"]["copied_into_package"] is False


def test_e50_reproduction_commands_do_not_invoke_physical_or_locked_analysis():
    # Probe 50.
    runbook = RUNBOOK.read_text(encoding="utf-8")
    code_blocks = re.findall(r"```bash\n(.*?)```", runbook, re.DOTALL)
    assert code_blocks
    joined = "\n".join(code_blocks)
    for forbidden in (
        "--force",
        "--unlock",
        "actuate",
        "flash ",
        "broker",
        "publish_actuator",
        "--evaluate",
        "--energy",
        "--pwm",
    ):
        assert forbidden not in joined
    source = SCRIPT.read_text(encoding="utf-8")
    parser_text = source.split("def build_parser", 1)[1]
    for forbidden in ("--force", "--unlock", "--evaluate", "--energy", "--pwm"):
        assert forbidden not in parser_text
    imports = re.findall(r"^import (\w+)|^from (\w+)", source, re.MULTILINE)
    modules = {a or b for a, b in imports}
    assert modules <= {
        "__future__",
        "argparse",
        "hashlib",
        "json",
        "re",
        "sys",
        "pathlib",
        "typing",
    }


def test_lockfile_and_model_hashes_are_bound(manifest):
    lock = manifest["dependency_lock"]
    script = SCRIPT.read_text(encoding="utf-8")
    assert lock["path"] == "ml/uv.lock"
    assert len(lock["sha256"]) == 64
    assert "uv.lock" not in script  # the verifier reads the manifest, not a hardcoded lock
    model = next(
        entry for entry in manifest["sources"] if entry["source_id"] == "B-W15-MODEL-UBJ"
    )
    assert model["sha256"] == (
        "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f"
    )
    receipt = RECEIPT.read_text(encoding="utf-8")
    assert "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f" in receipt
    assert "Python 3.12" in receipt or "python" in receipt.lower()
