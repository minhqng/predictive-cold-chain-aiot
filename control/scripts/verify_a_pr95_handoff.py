"""Verify Member A PR #95's supplementary S1 handoff without admitting it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


PR_NUMBER = 95
PR_HEAD = "815387d19a3898e6b33ccb65758a554dd0c589e1"
PR_URL = "https://github.com/minhqng/predictive-cold-chain-aiot/pull/95"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root: Path) -> dict[str, object]:
    package = root / "evidence/A/SOURCES/20261109/s1/s1-20261109T081304Z"
    sums_path = package / "SHA256SUMS.txt"
    verification_path = package / "host-summary/acceptance-verification.json"
    capture_path = package / "host-summary/read-only-capture-summary.json"
    trial_path = package / "trial.json"
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    trial = json.loads(trial_path.read_text(encoding="utf-8"))

    checked: list[dict[str, str]] = []
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split(maxsplit=1)
        path = package / relative
        actual = _sha256(path)
        if actual != digest:
            raise ValueError(f"PR #95 S1 package hash mismatch: {relative}")
        checked.append({"path": relative, "sha256": actual})

    if verification.get("outcome") != "PASS":
        raise ValueError("PR #95 supplementary S1 verification is not PASS")
    if verification.get("telemetry_frames") != 600 or capture.get("telemetry_frames") != 600:
        raise ValueError("PR #95 supplementary S1 is not the declared 600-frame run")
    if capture.get("bytes_written") != 0 or trial.get("commands_sent") != 0:
        raise ValueError("PR #95 supplementary S1 is not read-only")
    if trial.get("boot_id") != "c0e43470" or trial.get("actuation") != "NONE":
        raise ValueError("PR #95 supplementary S1 identity/safety state changed")

    return {
        "scope": "D_READ_ONLY_A_PR95_SUPPLEMENTARY_S1_HANDOFF",
        "source_pr": {
            "number": PR_NUMBER,
            "url": PR_URL,
            "head": PR_HEAD,
            "branch": "fix/a-main-acceptance-integrity",
            "state_at_review": "OPEN",
        },
        "package": {
            "path": package.relative_to(root).as_posix(),
            "sha256sums_sha256": _sha256(sums_path),
            "files": checked,
        },
        "result": {
            "outcome": verification["outcome"],
            "frames": verification["telemetry_frames"],
            "duration_s": verification["metrics"]["duration_s"],
            "boot_id": trial["boot_id"],
            "thermal_valid_rate": verification["metrics"]["thermal_valid_rate"],
            "electrical_valid_rate": verification["metrics"]["electrical_valid_rate"],
            "commands_sent": trial["commands_sent"],
            "bytes_written": capture["bytes_written"],
            "actuation": trial["actuation"],
            "fuse": trial["fuse"],
        },
        "admission": {
            "physical_run_validity": "VALID_SUPPLEMENTARY_PASSIVE_S1",
            "frozen_18_run_package": "NOT_ADMITTED_MANIFEST_UNCHANGED",
            "b_training": "SUPPLEMENTARY_WITH_RESTRICTIONS",
            "restrictions": [
                "passive only; not cooling-response evidence",
                "door status is UNVERIFIED at frame level",
                "two startup PZEM timeout frames",
                "calibration_id is UNRECORDED",
                "one capture is one run, not multiple independent runs",
            ],
        },
        "verdict": "PR95_SUPPLEMENTARY_S1_HASH_VERIFIED_NOT_ADMITTED",
    }


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    result = verify(root)
    target = root / "evidence/D/W09/a-pr95-supplementary-s1-binding.json"
    target.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
