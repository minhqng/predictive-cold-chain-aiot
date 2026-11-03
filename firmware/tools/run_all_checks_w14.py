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
6. the W06/W05/W04 firmware static checks and dossier validators as regression, but only
   where they can actually run: W02's and W03's validators resolve a `firmware_commit`
   against real git history, so on a `git archive` extraction (no `.git`) they fail for
   reasons that have nothing to do with W14. W14 changes no firmware, so a failure here
   in a real checkout does mean something moved - and it is still counted as a failure
   there. Where there is no git history the layer is reported NOT RUN: a skip, never a
   pass, and never W14's verdict either.

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


def in_git_checkout(root: pathlib.Path) -> bool:
    """Is this tree a real checkout, or an archive/export without history?

    The last layer needs the answer. W02's and W03's dossier validators prove their
    recorded `firmware_commit` contains the firmware sources by asking git, and a
    `git archive` extraction has nothing to ask. Running them there turned another
    week's archive sensitivity into a W14 gate failure on a clean export of W14's own
    HEAD, which is what it is: a cross-week finding for W02 and W03, not a W14 defect.
    """
    result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(root),
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
    return result.returncode == 0 and result.stdout.strip() == "true"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # The cross-week chain, held out of the list below so its runnability can be
    # decided on the tree it is being run on. It is not W14-owned and never was.
    cross_week = ("evidence: W06 + W05 + W04 validators and W04-W06 static checks "
                  "(regression, cross-week: the W02/W03 validators need real git history)",
                  [str(TOOLS / "run_all_checks_w06.py")], TOOLS)
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
    ]

    failed = 0
    for label, args, cwd in checks:
        ok, output = run(args, cwd)
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            failed += 1
            tail = "\n".join(output.strip().splitlines()[-25:])
            print("        " + tail.replace("\n", "\n        "))

    # Layer 6, and only layer 6, belongs to another week. It runs where it can mean
    # something and is named NOT RUN where it cannot - the pattern run_all_checks_w08.py
    # uses for its W15 step. An unrun cross-week layer never counts as a pass, and in a
    # real checkout a genuine failure there still counts against W14.
    cross_week_ran = False
    if in_git_checkout(REPO_ROOT):
        cross_week_ran = True
        label, args, cwd = cross_week
        ok, output = run(args, cwd)
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            failed += 1
            tail = "\n".join(output.strip().splitlines()[-25:])
            print("        " + tail.replace("\n", "\n        "))
    else:
        print(f"[NOT RUN] {cross_week[0]} - this tree has no git history (it is a "
              "`git archive`/export, not a checkout), so W02's and W03's "
              "firmware_commit checks cannot be answered here. Skipped, not passed: "
              "the state of that layer is UNKNOWN on this tree, and it is a cross-week "
              "finding for W02/W03 rather than a W14 defect - W14 owns no file in that "
              "chain.")

    total = len(checks) + (1 if cross_week_ran else 0)
    verdict = "passed" if not failed else f"passed - {failed} FAILED"
    print(f"\nW14 CHECKS: {total - failed}/{total} W14-runnable layers {verdict}")
    if not cross_week_ran:
        print("Cross-week layer: WAITING_TEAM_DEPENDENCY - NOT RUN on a tree without "
              "git history. Run this command in a real checkout to include W04-W06 and "
              "the W02/W03 dossier validators; nothing here claims they passed.")
    print("Reminder: nothing here flashed a board, energized a stage or moved a probe. "
          "A-W14-01 non-movement is not verifiable from archived captures, A-W14-03 has "
          "one session and no door-open event, and A-W14-04 is frozen with Member B - "
          "those three stay open until the data and B arrive.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
