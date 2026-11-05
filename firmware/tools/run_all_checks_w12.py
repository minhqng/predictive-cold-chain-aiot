"""Run every W12 check available without hardware.

    py firmware/tools/run_all_checks_w12.py

Layers:

1. the full host-tool unittest suite (regression - this branch stacks on the
   W02/W03/W04/W05/W06 deliverables), which must stay green with the W12 tests
   added;
2. the W12 drift audit tool run on the committed W04 cooling capture (a self
   exit-code check);
3. the W12 evidence dossier validator (hash pins + honesty re-assert);
4. the W12 artifact reproduction check (``--check``).

Exit code 0 only when every layer passes. Nothing here touches hardware, opens a
serial port, flashes, or declares a whole-team gate. W12 is a *host drift audit*
feeding the Month-3 signoff; its PHYSICALLY_VERIFIED claims stay open.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]
W12 = REPO_ROOT / "evidence" / "A" / "W12"


def run(args: list[str], cwd: pathlib.Path) -> tuple[bool, str]:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, *args], cwd=str(cwd),
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=env)
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    checks = [
        ("host tools: unittest suite (W02..W06 + W12 regression)",
         ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"], TOOLS),
        ("tools: W12 drift audit runs on the committed capture",
         [str(TOOLS / "cg_w12_drift_audit.py")], TOOLS),
        ("evidence: W12 dossier validator (hash pins, honesty)",
         [str(W12 / "validate_w12.py")], W12),
        ("tools: W12 artifacts reproduce from the authentic capture",
         [str(W12 / "build_w12_artifacts.py"), "--check"], W12),
    ]

    failures = 0
    for label, args, cwd in checks:
        ok, output = run(args, cwd)
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            failures += 1
            for line in output.strip().splitlines()[-25:]:
                print(f"        {line}")

    print()
    if failures:
        print(f"W12 CHECKS: {len(checks) - failures}/{len(checks)} passed - {failures} FAILED")
        return 1
    print(f"W12 CHECKS: {len(checks)}/{len(checks)} passed")
    print("Reminder: W12 is a host drift audit. No check here touched hardware, and no")
    print("claim here is PHYSICALLY_VERIFIED. The gate G3 contribution is an A-side input,")
    print("never a whole-team GREEN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
