"""Run every W13 check available without hardware.

    py firmware/tools/run_all_checks_w13.py

Layers:

1. the full host-tool unittest suite (regression, W12 + W13 tests included);
2. the W13 timing tool run on the committed H6 trace and cooling capture;
3. the W13 evidence dossier validator (hash pins + honesty re-assert);
4. the W13 artifact reproduction check.

Exit code 0 only when every layer passes. Nothing here touches hardware. The
door->critical ask is NOT COMPUTABLE (no door-open event exists), and the
backend-command->device latency is a named gap (the production firmware has no
network command path); neither is simulated.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]
W13 = REPO_ROOT / "evidence" / "A" / "W13"


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
        ("host tools: unittest suite (W02..W06 + W12/W13 regression)",
         ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"], TOOLS),
        ("tools: W13 timing runs on the committed traces",
         [str(TOOLS / "cg_w13_timing.py")], TOOLS),
        ("evidence: W13 dossier validator (hash pins, honesty)",
         [str(W13 / "validate_w13.py")], W13),
        ("tools: W13 artifacts reproduce from the authentic captures",
         [str(W13 / "build_w13_artifacts.py"), "--check"], W13),
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
        print(f"W13 CHECKS: {len(checks) - failures}/{len(checks)} passed - {failures} FAILED")
        return 1
    print(f"W13 CHECKS: {len(checks)}/{len(checks)} passed")
    print("Reminder: W13 is host timing analysis. No check here touched hardware; no claim")
    print("is PHYSICALLY_VERIFIED; door->critical is NOT COMPUTABLE and backend->device")
    print("latency is a named gap, not an estimate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
