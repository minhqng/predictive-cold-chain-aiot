"""Run every W06 check available without hardware.

    py firmware/tools/run_all_checks_w06.py

Runs, in order:

1. the host-tool suite (W02 + W03 + W04 + W05 + W06), which compiles and runs
   three C harnesses against the real firmware sources: the W04 control core, the
   W05 telemetry foundation, and the W06 command/ACK contract;
2. the W06 firmware static contract checks (fail-closed posture, no actuation
   path, fail-closed freshness, idempotency ordering, volatile memory, ACK
   vocabulary and payload, applied state, host parity, console regression);
3. the W05, W04, W03 and W02 static checks (regression - this branch stacks on
   all of them);
4. the W02, W03, W04 and W05 evidence dossier validators (regression);
5. the W06 evidence dossier validator;
6. the W06 contract-artifact reproduction check.

Exit code 0 only when every check passes. Nothing here flashes, energizes or
touches hardware, and nothing here substitutes a real command round trip for the
backend: W06 has no transport, so the physical trace deliverable stays recorded
as requiring an authorized session with Member C's command issuer.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]


def run(args: list[str], cwd: pathlib.Path) -> tuple[bool, str]:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env
    )
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    evidence = REPO_ROOT / "evidence" / "A"
    checks = [
        (
            "host tools: unittest suite (W02 + W03 + W04 + W05 + W06)",
            ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"],
            TOOLS,
        ),
        (
            "firmware: W06 static contract checks",
            [str(TOOLS / "cg_check_firmware_w06.py"), "--quiet"],
            REPO_ROOT,
        ),
        (
            "firmware: W05 static contract checks (regression)",
            [str(TOOLS / "cg_check_firmware_w05.py"), "--quiet"],
            REPO_ROOT,
        ),
        (
            "firmware: W04 static contract checks (regression)",
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
            [str(evidence / "W02" / "validate_w02.py")],
            evidence / "W02",
        ),
        (
            "evidence: W03 dossier validator (regression)",
            [str(evidence / "W03" / "validate_w03.py")],
            evidence / "W03",
        ),
        (
            "evidence: W04 dossier validator (regression)",
            [str(evidence / "W04" / "validate_w04.py")],
            evidence / "W04",
        ),
        (
            "evidence: W05 dossier validator (regression)",
            [str(evidence / "W05" / "validate_w05.py")],
            evidence / "W05",
        ),
        (
            "evidence: W06 dossier validator (hash pins, honest verdict)",
            [str(evidence / "W06" / "validate_w06.py")],
            evidence / "W06",
        ),
        (
            "tools: W06 contract artifacts reproduce from the real sources",
            [str(evidence / "W06" / "build_contract_artifacts.py"), "--check"],
            evidence / "W06",
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
        print(f"W06 CHECKS: {len(checks) - failures}/{len(checks)} passed - {failures} FAILED")
        print("Reminder: no check here compiled the firmware or touched hardware.")
        return 1

    print(f"W06 CHECKS: {len(checks)}/{len(checks)} passed")
    print("Reminder: no check here compiled the firmware or touched hardware.")
    print("Compile check: ESP-IDF v6.1 build, logged in evidence/A/W06/build/.")
    print("A-W06-05 and A-W06-06 remain open physically: there is no transport, no backend")
    print("issuer, and no authorized energized session, so the physical trace and the")
    print("reset-command log are recorded as NEED_USER_ACTION rather than simulated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
