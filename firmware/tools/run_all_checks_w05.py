"""Run every W05 check available without hardware.

    py firmware/tools/run_all_checks_w05.py

Runs, in order:

1. the host-tool suite (W02 + W03 + W04 + W05), which includes compiling and
   running both C harnesses against the real firmware sources - the W04 control
   core and the W05 quality/liveness/telemetry foundation;
2. the W05 firmware static contract checks (identity, coherence, quality
   vocabulary, producer liveness, applied state, host schema parity);
3. the W04, W03 and W02 static checks (regression - this branch stacks on them);
4. the W02, W03 and W04 evidence dossier validators (regression);
5. the W05 evidence dossier validator (hash pins over the committed pilot data).

Exit code 0 only when every check passes. Nothing here flashes, energizes or
touches hardware. In particular, no check here captured a 30-minute telemetry
run: the W05 timing pilot is derived from bytes that were already committed in
the W04 evidence, and the 30-minute study and timing-jitter capture stay marked
as requiring an authorized device run. The ESP-IDF compile check is recorded
separately in evidence/A/W05/build/.
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
            "host tools: unittest suite (W02 + W03 + W04 + W05)",
            ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"],
            TOOLS,
        ),
        (
            "firmware: W05 static contract checks",
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
            [str(REPO_ROOT / "evidence" / "A" / "W02" / "validate_w02.py")],
            REPO_ROOT / "evidence" / "A" / "W02",
        ),
        (
            "evidence: W03 dossier validator (regression)",
            [str(REPO_ROOT / "evidence" / "A" / "W03" / "validate_w03.py")],
            REPO_ROOT / "evidence" / "A" / "W03",
        ),
        (
            "evidence: W04 dossier validator (regression)",
            [str(REPO_ROOT / "evidence" / "A" / "W04" / "validate_w04.py")],
            REPO_ROOT / "evidence" / "A" / "W04",
        ),
        (
            "evidence: W05 dossier validator (hash pins, honest verdict)",
            [str(REPO_ROOT / "evidence" / "A" / "W05" / "validate_w05.py")],
            REPO_ROOT / "evidence" / "A" / "W05",
        ),
        (
            "tools: W05 timing pilot reproduced from the committed W04 capture",
            [str(REPO_ROOT / "evidence" / "A" / "W05" / "build_timing_pilot.py")],
            REPO_ROOT / "evidence" / "A" / "W05",
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
        print(f"W05 CHECKS: {len(checks) - failures}/{len(checks)} passed - {failures} FAILED")
        print("Reminder: no check here compiles the firmware or touches hardware.")
        return 1

    print(f"W05 CHECKS: {len(checks)}/{len(checks)} passed")
    print("Reminder: no check here compiled the firmware or touched hardware.")
    print("Compile check: ESP-IDF v6.1 build, logged in evidence/A/W05/build/.")
    print("A-W05-03 is PARTIAL: the pilot is measured from the committed 60 s W04 capture.")
    print("A 30-minute on-device telemetry run and a real timing-jitter CSV still require an")
    print("authorized, supervised flash and capture on the installed image.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
