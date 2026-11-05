"""Run every W15 check available without hardware.

    py firmware/tools/run_all_checks_w15.py

Runs, in order:

1. the host-tool unittest suite (which includes the W15 provenance/quality and
   PWM-methodology tests);
2. the W15 electrical-producer audit and the A3 tables on the committed captures
   only, so a machine without Member A's bench tree still proves that half;
3. the W15 PWM go/no-go decision object, which must stay `NOT_DECIDED`;
4. the W15 artifact reproduction check and the W15 dossier validator;
5. the W08 dossier validator as regression, because W15 reads the shared
   `local-bench-observations.json` declaration;
6. the W04-W06 static contract checks and the W02-W06 dossier validators.

Exit code 0 only when every check passes. Nothing here opens a port, energizes a
branch or measures an instrument. A-W15-03 stays NEED_USER_ACTION because no
trusted independent meter exists, and A-W15-04 stays BLOCKED_HARDWARE because
every decision threshold is an `UNRESOLVED` parameter owned by Member D.
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
            "host tools: unittest suite (W02 + W03 + W04 + W05 + W06 + W08 + W15)",
            ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"],
            TOOLS,
        ),
        (
            "tools: W15 PZEM quality + A3 tables, committed captures only",
            [str(TOOLS / "cg_w15_pzem_quality.py"), "--no-local"],
            TOOLS,
        ),
        (
            "tools: W15 PWM go/no-go methodology (decision must stay NOT_DECIDED)",
            [str(TOOLS / "cg_w15_pwm_gonogo.py")],
            TOOLS,
        ),
        (
            "evidence: W15 artifacts reproduce from the committed captures + declaration",
            [str(evidence / "W15" / "build_w15_artifacts.py"), "--check"],
            evidence / "W15",
        ),
        (
            "evidence: W15 dossier validator (pins, honest verdicts, no physical claim)",
            [str(evidence / "W15" / "validate_w15.py")],
            evidence / "W15",
        ),
        (
            "evidence: W08 dossier validator (regression: W15 consumes its declaration)",
            [str(evidence / "W08" / "validate_w08.py")],
            evidence / "W08",
        ),
        (
            "firmware: W06 static contract checks (regression)",
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
            "evidence: W06 dossier validator (regression)",
            [str(evidence / "W06" / "validate_w06.py")],
            evidence / "W06",
        ),
    ]

    failures = 0
    bench_byte_checks_not_run = False
    for label, args, cwd in checks:
        ok, output = run(args, cwd)
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {label}")
        if "byte-checks: NOT RUN" in output:
            # The validator passes on a machine without the bench tree, but the
            # declared originals' SHA-256 checks did not run there: surface that
            # instead of folding it into the pass count.
            bench_byte_checks_not_run = True
            print("        [NOT RUN] local-bench original byte-checks "
                  "(bench tree absent) - not a pass, see the validator note")
        if not ok:
            failures += 1
            for line in output.strip().splitlines()[-25:]:
                print(f"        {line}")

    print()
    if failures:
        print(f"W15 CHECKS: {len(checks) - failures}/{len(checks)} passed - {failures} FAILED")
        print("Reminder: no check here measured an instrument or touched hardware.")
        return 1

    print(f"W15 CHECKS: {len(checks)}/{len(checks)} passed")
    if bench_byte_checks_not_run:
        print("NOT RUN (not counted as passed): local-bench original byte-checks - "
              "the declared H7/H8 originals live only in Member A's local W04 tree "
              "and were absent here; set CG_W08_BENCH_ROOT to a tree that has them.")
    print("Reminder: no check here measured an instrument or touched hardware.")
    print("A-W15-03 remains NEED_USER_ACTION: with no trusted independent meter this")
    print("dossier reports plausibility and internal consistency, never calibration.")
    print("A-W15-04 remains BLOCKED_HARDWARE and its decision is NOT_DECIDED: all six")
    print("criteria parameters and all six delivered limits are UNRESOLVED, so the")
    print("method is delivered and the decision is deliberately not taken here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
