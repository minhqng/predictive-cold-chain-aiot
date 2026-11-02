"""Run every W04 check available without hardware.

    py firmware/tools/run_all_checks_w04.py

Runs, in order:

1. the host-tool unit/integration suite (W02 + W03 + W04), which includes
   compiling and running the TEC state-machine harness against the real
   control core with a fake backend;
2. the W04 firmware static contract checks (fail-closed posture, unresolved
   limits, ordering, telemetry integrity, grammar, GPIO, docs);
3. the W03 static checks (regression - the W04 branch contains W03);
4. the W02 static checks (regression);
5. the W02 and W03 evidence dossier validators.
6. the W04 evidence dossier validator (every committed capture re-hashed
   against ``evidence/A/W04/SHA256SUMS.txt``).

Exit code 0 only when every check passes. Nothing here flashes, energizes
or touches hardware, and nothing here substitutes for the ESP-IDF compile
check (recorded separately) or for the physical gates G0-G5 in docs/06.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]


def run(args: list[str], cwd: pathlib.Path) -> tuple[bool, str]:
    # Children print Vietnamese evidence text; without UTF-8 mode they emit the
    # Windows codepage and a strict utf-8 decode loses the failing output.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env
    )
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    checks = [
        (
            "host tools: unittest suite (W02 + W03 + W04)",
            ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"],
            TOOLS,
        ),
        (
            "firmware: W04 static contract checks",
            [str(TOOLS / "cg_check_firmware_w04.py"), "--quiet"],
            REPO_ROOT,
        ),
        (
            "firmware: W03 static contract checks (regression)",
            [str(TOOLS / "cg_check_firmware_w03.py"), "--quiet"],
            REPO_ROOT,
        ),
        (
            "firmware: W02 static contract checks (regression)",
            [str(TOOLS / "cg_check_firmware.py"), "--quiet"],
            REPO_ROOT,
        ),
        (
            "evidence: W02 dossier validator (regression)",
            [str(REPO_ROOT / "evidence" / "A" / "W02" / "validate_w02.py")],
            REPO_ROOT / "evidence" / "A" / "W02",
        ),
        (
            "evidence: W03 dossier validator (regression)",
            [str(REPO_ROOT / "evidence" / "A" / "W03" / "validate_w03.py")],
            REPO_ROOT / "evidence" / "A" / "W03",
        ),
        (
            "evidence: W04 dossier validator (hash pins, no flash images, honest verdict)",
            [str(REPO_ROOT / "evidence" / "A" / "W04" / "validate_w04.py")],
            REPO_ROOT / "evidence" / "A" / "W04",
        ),
    ]

    failures = 0
    for label, args, cwd in checks:
        ok, output = run(args, cwd)
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {label}")
        if not ok:
            failures += 1
            for line in output.strip().splitlines()[-25:]:
                print(f"        {line}")

    print()
    if failures:
        print(f"W04 CHECKS: {len(checks) - failures}/{len(checks)} passed - {failures} FAILED")
        print("Reminder: no check here compiles the firmware or touches hardware.")
        return 1

    print(f"W04 CHECKS: {len(checks)}/{len(checks)} passed")
    print("Reminder: no check here compiles the firmware or touches hardware.")
    print("Compile check: ESP-IDF v6.1 build, logged in evidence/A/W04/build-2026-11-01/.")
    print("W04 FOUNDATION DELIVERED — PRODUCTION TEC OUTPUT STAGE COMPILED OUT AND NOT AUTHORIZED")
    print("H6 bench energization already ran under operator supervision (2026-10-29, PWM 10%, 60s).")
    print("Physical W04 work still open: 5 genuine POWER_ON cold boots, one pin-level DMM/scope")
    print("reading of GPIO5/6/10, the fuse-label and conductor-marking photographs, a conservative")
    print("run that also records T1/T3, and the CR-A-W04-01/02 change reviews.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
