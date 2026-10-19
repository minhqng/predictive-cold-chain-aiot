"""One command that runs every W03 check available without hardware.

    py firmware/tools/run_all_checks_w03.py

Runs, in order:

1. the host-tool unit/integration suite (``unittest``, standard library);
2. the W03 firmware static contract checks
   (``cg_check_firmware_w03.py`` - register parity, read-only, CRC,
   actuator default-OFF, grammar, build completeness);
3. the W02 firmware static contract checks (``cg_check_firmware.py``) -
   the W03 branch contains the W02 firmware, so its invariants must keep
   passing;
4. the W02 evidence dossier validator (``evidence/A/W02/validate_w02.py``);
5. the W03 evidence dossier validator (``evidence/A/W03/validate_w03.py``).

Exit code 0 only when every check passes. The script prints one line per
check so a reviewer can see exactly what was executed. No check here
compiles the firmware or touches hardware: the compile check is the
GitHub Actions ESP-IDF build documented in evidence/A/W03/.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]


def run(args: list[str], cwd: pathlib.Path) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8"
    )
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    checks = [
        (
            "host tools: unittest suite (W02 + W03)",
            ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"],
            TOOLS,
        ),
        (
            "firmware: W03 static contract checks",
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
            "evidence: W03 dossier validator",
            [str(REPO_ROOT / "evidence" / "A" / "W03" / "validate_w03.py")],
            REPO_ROOT / "evidence" / "A" / "W03",
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
        print(f"W03 CHECKS: {len(checks) - failures}/{len(checks)} passed - {failures} FAILED")
        print("Reminder: no check here compiles the firmware or touches hardware.")
        return 1

    print(f"W03 CHECKS: {len(checks)}/{len(checks)} passed")
    print("Reminder: no check here compiles the firmware or touches hardware.")
    print("Compile check: GitHub Actions ESP-IDF v6.1 build (see evidence/A/W03/README.md).")
    print(
        "Hardware still pending: RS-485 logic-level approval (D), PZEM real readback + >=10 min "
        "TEC-OFF window, XL4015 loaded verification, IBT-2 cold-boot log, shunt inspection under power."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
