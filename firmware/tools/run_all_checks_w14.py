"""Run every check that W14 depends on, in one command.

Six layers, none of which touches hardware:

1. the whole host unittest suite, W02 through W14;
2. the W14 artifact generator in check mode, so the dossier cannot drift from the
   captures and tools that produced it;
3. the W14 dossier validator, which pins bytes, recomputes every published number
   from the raw rows and re-checks each verdict for honesty;
4. the three W14 command lines as documented, so what the dossier tells a reader to
   run is what actually runs;
5. the W07 artifacts and dossier validator as regression - W14 imports W07's role map
   and representation table, so if W07 moves, W14 must fail here and not in silence;
6. the W06/W05/W04 firmware static checks and dossier validators as regression: W14
   changes no firmware, so a failure here means something moved that it should not have.

W14 adds analysis of captures that already exist. No layer here can make A-W14-01
"verify no movement" pass, put a distribution on one session, compute a response for a
door that was never opened, or freeze a pairing tolerance: each of those is reported
as NOT COMPUTABLE, NOT VERIFIABLE or TEAM_DEPENDENCY by design, and the suite proves
the refusal still works.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]
W14 = REPO_ROOT / "evidence" / "A" / "W14"
W07 = REPO_ROOT / "evidence" / "A" / "W07"
H8 = "evidence/A/W04/tec-cooling-response-600s.csv"


def run(args: list[str], cwd: pathlib.Path) -> tuple[bool, str]:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, *args], cwd=str(cwd), capture_output=True,
                            text=True, encoding="utf-8", errors="replace", env=env)
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    checks = [
        ("host tools: unittest suite (W02 + W03 + W04 + W05 + W06 + W07 + W14)",
         ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"], TOOLS),
        ("evidence: W14 artifacts reproduce from the tools and captures",
         [str(W14 / "build_w14_artifacts.py"), "--check"], REPO_ROOT),
        ("evidence: W14 dossier validator (hash pins, recomputed numbers, honest verdicts)",
         [str(W14 / "validate_w14.py")], REPO_ROOT),
        ("tools: W14 spatial CLI on the real capture",
         [str(TOOLS / "cg_w14_spatial.py"), H8, "--min-sessions", "3"], REPO_ROOT),
        ("tools: W14 sensor-position QA on the real capture",
         [str(TOOLS / "cg_w14_sensor_qa.py")], REPO_ROOT),
        ("tools: W14 pairing input on the real capture",
         [str(TOOLS / "cg_w14_pairing.py"), H8], REPO_ROOT),
        ("evidence: W07 artifacts + validator (regression - W14 imports W07)",
         [str(W07 / "build_w07_artifacts.py"), "--check"], REPO_ROOT),
        ("evidence: W07 dossier validator (regression)",
         [str(W07 / "validate_w07.py")], REPO_ROOT),
        ("evidence: W06 + W05 + W04 validators and W04-W06 static checks (regression)",
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
    verdict = "passed" if not failed else f"passed - {failed} FAILED"
    print(f"\nW14 CHECKS: {total - failed}/{total} {verdict}")
    print("Reminder: nothing here flashed a board, energized a stage or moved a probe. "
          "A-W14-01 non-movement is not verifiable from archived captures, A-W14-03 has "
          "one session and no door-open event, and A-W14-04 is frozen with Member B - "
          "those three stay open until the data and B arrive.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
