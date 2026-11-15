"""Run every W16 check available without hardware.

    py firmware/tools/run_all_checks_w16.py

Layers:

1. the full host-tool unittest suite (regression, W12/W13/W16 tests included);
2. the W16 comparability framework run on the committed baseline capture, which
   executes ``assert_no_freeze`` and prints the no-freeze verdict;
3. the W16 evidence dossier validator (hash pins + honesty re-assert);
4. the W16 artifact reproduction check.

Exit code 0 only when every layer passes. The whole point of W16 is that a
physical freeze may NOT be declared from host evidence: this slice asserts no
freeze, declares no team G4, and fills no response tolerance from data that was
never re-measured. Nothing here touches hardware.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]
W16 = REPO_ROOT / "evidence" / "A" / "W16"


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
        ("host tools: unittest suite (W02..W06 + W12/W13/W16 regression)",
         ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"], TOOLS),
        ("tools: W16 framework runs on the authentic baseline, asserts no freeze",
         [str(TOOLS / "cg_w16_comparability.py")], TOOLS),
        ("evidence: W16 dossier validator (hash pins, honesty)",
         [str(W16 / "validate_w16.py")], W16),
        ("tools: W16 artifacts reproduce from the authentic baseline",
         [str(W16 / "build_w16_artifacts.py"), "--check"], W16),
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
        print(f"W16 CHECKS: {len(checks) - failures}/{len(checks)} passed - {failures} FAILED")
        return 1
    print(f"W16 CHECKS: {len(checks)}/{len(checks)} passed")
    print("Reminder: W16 asserts NO physical freeze from host evidence and declares no")
    print("team gate. A freeze needs a real W16 re-measurement (A-W16-01) that this slice")
    print("cannot perform; it is recorded as NEED_USER_ACTION, never simulated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
