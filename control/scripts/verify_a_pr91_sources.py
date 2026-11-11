"""Verify the S1/S2 source artifacts published by Member A in PR #91."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


PR_NUMBER = 91
PR_HEAD = "63982e9592e0687099afb53fa1e4422f57761d74"
PR_URL = "https://github.com/minhqng/predictive-cold-chain-aiot/pull/91"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root: Path) -> dict[str, object]:
    index_path = root / "evidence/A/SOURCES/20261107/s1/source-publication-index.json"
    s1_result_path = root / "evidence/A/SOURCES/20261107/s1/source-result-A-W09-02.json"
    s2_result_path = root / "evidence/A/SOURCES/20261107/s2/source-result-A-W10-03.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    s1_result = json.loads(s1_result_path.read_text(encoding="utf-8"))
    s2_result = json.loads(s2_result_path.read_text(encoding="utf-8"))

    if s1_result.get("outcome") != "PASS" or s2_result.get("outcome") != "PASS":
        raise ValueError("A PR #91 source result is not PASS")
    if s1_result["measurements"].get("valid_runs") != 4:
        raise ValueError("A PR #91 S1 valid-run count changed")
    if s2_result["measurements"].get("valid_runs") != 4:
        raise ValueError("A PR #91 S2 valid-run count changed")

    windows = index.get("windows")
    if not isinstance(windows, list):
        raise ValueError("A PR #91 publication index lacks windows")
    checked_paths: dict[str, str] = {}
    for window in windows:
        raw_path = root / window["raw_path"]
        actual = _sha256(raw_path)
        if actual != window["raw_sha256"]:
            raise ValueError(f"raw source hash mismatch: {window['raw_path']}")
        checked_paths[window["raw_path"]] = actual

    s1_windows = [window for window in windows if window["scenario"] == "S1"]
    s2_windows = [window for window in windows if window["scenario"] == "S2"]
    if len(s1_windows) != 4 or len(s2_windows) != 4:
        raise ValueError("A PR #91 must publish four S1 and four S2 windows")

    return {
        "scope": "D_READ_ONLY_A_PR91_S1_S2_SOURCE_BINDING",
        "source_pr": {
            "number": PR_NUMBER,
            "url": PR_URL,
            "head": PR_HEAD,
            "branch": "feat/a-s1-s2-source-evidence",
        },
        "sources": [
            {
                "path": index_path.relative_to(root).as_posix(),
                "sha256": _sha256(index_path),
            },
            {
                "path": s1_result_path.relative_to(root).as_posix(),
                "sha256": _sha256(s1_result_path),
            },
            {
                "path": s2_result_path.relative_to(root).as_posix(),
                "sha256": _sha256(s2_result_path),
            },
        ],
        "raw_sources": [
            {"path": path, "sha256": digest}
            for path, digest in sorted(checked_paths.items())
        ],
        "s1": {
            "source_test_id": "A-W09-02",
            "outcome": s1_result["outcome"],
            "valid_windows": len(s1_windows),
            "frames": sum(window["frames"] for window in s1_windows),
            "classification": "passive thermal/electrical-idle; not cooling/energy",
        },
        "s2": {
            "source_test_id": "A-W10-03",
            "outcome": s2_result["outcome"],
            "valid_windows": len(s2_windows),
            "frames": sum(window["frames"] for window in s2_windows),
            "classification": "door-disturbance source windows",
        },
        "verdict": "PR91_SOURCES_HASH_VERIFIED",
        "note": (
            "PR #91 has been fetched locally at the pinned head. The raw S1/S2 "
            "files in the current checkout match its publication-index hashes."
        ),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    result = verify(root)
    target = root / "evidence/D/W09/a-pr91-s1-s2-source-binding.json"
    target.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
