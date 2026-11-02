"""Run every check that W07 depends on, in one command.

Seven layers, none of which touches hardware:

1. the whole host unittest suite, W02 through W07;
2. the W07 artifact generator in check mode, so the report cannot drift from the
   captures and tools that produced it;
3. the W07 dossier validator, which pins bytes and re-reads every verdict;
4-6. the W06/W05/W04 firmware static checks, as regression: W07 changes no
   firmware, so a failure here means something moved that it should not have;
7. the W04 and W05 dossier validators, which fail if committed evidence was edited.

W07 adds analysis and a criterion candidate. It does not add a device result, and
no layer here can make A-W07-02/03 pass: those need physical runs, and the suite
reports them as insufficient rather than accepting a substitute.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]
W07 = REPO_ROOT / "evidence" / "A" / "W07"


def run(args: list[str], cwd: pathlib.Path) -> tuple[bool, str]:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, *args], cwd=str(cwd), capture_output=True,
                            text=True, encoding="utf-8", errors="replace", env=env)
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    checks = [
        ("host tools: unittest suite (W02 + W03 + W04 + W05 + W06 + W07)",
         ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"], TOOLS),
        ("evidence: W07 artifacts reproduce from the tools and captures",
         [str(W07 / "build_w07_artifacts.py"), "--check"], REPO_ROOT),
        ("evidence: W07 dossier validator (hash pins, honest verdicts)",
         [str(W07 / "validate_w07.py")], REPO_ROOT),
        ("firmware: W06 static contract checks (regression)",
         [str(TOOLS / "cg_check_firmware_w06.py"), "--quiet"], REPO_ROOT),
        ("firmware: W05 static contract checks (regression)",
         [str(TOOLS / "cg_check_firmware_w05.py"), "--quiet"], REPO_ROOT),
        ("firmware: W04 static contract checks (regression)",
         [str(TOOLS / "cg_check_firmware_w04.py"), "--quiet"], REPO_ROOT),
        ("evidence: W06 + W05 + W04 dossier validators (regression)",
         [str(TOOLS / "run_all_checks_w06.py")], TOOLS),
    ]

    failed = 0
    for label, args, cwd in checks:
        ok, output = run(args, cwd)
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            failed += 1
            tail = "\n".join(output.strip().splitlines()[-25:])
            print("        " + tail.replace("\n", "\n        "))

    total = len(checks)
    print(f"\nW07 CHECKS: {total - failed}/{total} passed"
          + (" - 1 FAILED" if failed else ""))
    print("Reminder: nothing here flashed a board, energized a stage or measured a "
          "physical quantity. The runs W07 needs are physical, and the report says so.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
