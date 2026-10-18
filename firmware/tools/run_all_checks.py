"""One command that runs every W02 check available without hardware.

    py firmware/tools/run_all_checks.py

Runs, in order:

1. the host-tool unit/integration suite (``unittest``, standard library);
2. the firmware static contract checks (``cg_check_firmware.py``);
3. the W02 evidence dossier validator (``evidence/A/W02/validate_w02.py``).

Exit code 0 only when all three pass. The script prints one line per
check so a reviewer can see exactly what was executed.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]


def run(label: str, args: list[str], cwd: pathlib.Path) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8"
    )
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    checks = [
        (
            "host tools: unittest suite",
            ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"],
            TOOLS,
        ),
        (
            "firmware: static contract checks",
            [str(TOOLS / "cg_check_firmware.py"), "--quiet"],
            REPO_ROOT,
        ),
        (
            "evidence: W02 dossier validator",
            [str(REPO_ROOT / "evidence" / "A" / "W02" / "validate_w02.py")],
            REPO_ROOT / "evidence" / "A" / "W02",
        ),
    ]

    failures = 0
    for label, args, cwd in checks:
        ok, output = run(label, args, cwd)
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {label}")
        if not ok:
            failures += 1
            for line in output.strip().splitlines()[-25:]:
                print(f"        {line}")

    print()
    if failures:
        print(f"W02 CHECKS: {len(checks) - failures}/{len(checks)} passed - {failures} FAILED")
        print("Reminder: no check here compiles the firmware or touches hardware.")
        return 1

    print(f"W02 CHECKS: {len(checks)}/{len(checks)} passed")
    print("Reminder: no check here compiles the firmware or touches hardware.")
    print("Compile check: Espressif idf docker build (see repository README).")
    print("Hardware still pending: BME280, physical sensor labeling, H0 mechanical.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
