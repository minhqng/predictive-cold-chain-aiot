"""Run every W11 check available without hardware.

    py firmware/tools/run_all_checks_w11.py

Runs, in order:

1. the W11 host-tool tests: the four S4 evidence lanes and their promotion rules,
   the refusal/physical-evidence validator, the S3 feasibility assessment and the
   run-expansion list;
2. the W09 and W10 tests (regression - W11 consumes the W09 parser, validity layer
   and run registry directly, and the W10 pairing floor for its thermal lane);
3. the whole existing host-tool suite (regression W02-W06);
4. the W02-W06 firmware static contract checks (regression - W11 adds no firmware
   code, so any change there is a regression to catch);
5. the W04, W05, W06, W09 and W10 evidence dossier validators (regression over the
   read-only inputs this slice analyzes);
6. the W11 artifact reproduction check and the W11 dossier validator, which re-reads
   the capture, recomputes the divergence counts and the disagreement candidates,
   re-runs the refusal analysis over a real device log and fails if a fail-closed
   verdict stops being fail-closed.

Exit code 0 only when every check passes. Nothing here flashes, energizes, blocks a
command on a device or touches hardware. A-W11-02 and A-W11-03 stay recorded as REAL
DATA NOT AVAILABLE -> NEED_USER_ACTION, and A-W11-04 stays NO-GO: no device in this
repository has ever received a command, no refusal session has been run, and no host
test here may be read as physical verification of any of that.
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
    w09 = evidence / "W09"
    w10 = evidence / "W10"
    w11 = evidence / "W11"
    checks: list[tuple[str, list[str], pathlib.Path]] = [
        (
            "host tools: W11 tests (S4 lanes, refusal validator, S3 feasibility, run list, "
            "dossier pins)",
            ["-m", "unittest", "discover", "-s", "tests", "-t", "tests", "-p", "test_cg_w11*"],
            TOOLS,
        ),
        (
            "host tools: W10 tests (regression over the door and pairing layer)",
            ["-m", "unittest", "discover", "-s", "tests", "-t", "tests", "-p", "test_cg_w10*"],
            TOOLS,
        ),
        (
            "host tools: W09 tests (regression over the parser, validity and run registry)",
            ["-m", "unittest", "discover", "-s", "tests", "-t", "tests", "-p", "test_cg_w09*"],
            TOOLS,
        ),
        (
            "host tools: full suite (regression W02-W06)",
            ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"],
            TOOLS,
        ),
    ]
    for name, label in (
        ("cg_check_firmware_w06.py", "W06"),
        ("cg_check_firmware_w05.py", "W05"),
        ("cg_check_firmware_w04.py", "W04"),
        ("cg_check_firmware_w03.py", "W03"),
        ("cg_check_firmware.py", "W02"),
    ):
        checks.append((
            f"firmware: {label} static contract checks (regression)",
            [str(TOOLS / name), "--quiet"],
            REPO_ROOT,
        ))
    for folder in ("W04", "W05", "W06"):
        checks.append((
            f"evidence: {folder} dossier validator (regression)",
            [str(evidence / folder / f"validate_{folder.lower()}.py")],
            evidence / folder,
        ))
    checks += [
        (
            "evidence: W09 artifacts reproduce (regression)",
            [str(w09 / "build_w09_artifacts.py"), "--check"],
            w09,
        ),
        (
            "evidence: W09 dossier validator (regression)",
            [str(w09 / "validate_w09.py")],
            w09,
        ),
        (
            "evidence: W10 artifacts reproduce (regression)",
            [str(w10 / "build_w10_artifacts.py"), "--check"],
            w10,
        ),
        (
            "evidence: W10 dossier validator (regression)",
            [str(w10 / "validate_w10.py")],
            w10,
        ),
        (
            "evidence: W11 artifacts reproduce from the delivered tooling",
            [str(w11 / "build_w11_artifacts.py"), "--check"],
            w11,
        ),
        (
            "evidence: W11 dossier validator (hash pins, re-derived lane counts, "
            "NO-GO and zero-publishable-run verdicts intact)",
            [str(w11 / "validate_w11.py")],
            w11,
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
        print(f"W11 CHECKS: {len(checks) - failures}/{len(checks)} passed - {failures} FAILED")
        return 1

    print(f"W11 CHECKS: {len(checks)}/{len(checks)} passed")
    print("Reminder: no command was delivered to a device, no refusal was observed on")
    print("hardware and no S3 method was attempted. The S4 physical leg is REAL DATA NOT")
    print("AVAILABLE because no committed capture contains a command observation, so")
    print("A-W11-02 and A-W11-03 stay NEED_USER_ACTION / TEAM_DEPENDENCY, and A-W11-04")
    print("stays NO-GO on instrumentation. Run one repetition of S4-protocol.md section 9")
    print("on a supervised rig, or add the cold-side probe, and re-derive this dossier.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
