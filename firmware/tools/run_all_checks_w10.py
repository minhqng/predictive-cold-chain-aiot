"""Run every W10 check available without hardware.

    py firmware/tools/run_all_checks_w10.py

Runs, in order:

1. the W10 host-tool tests: door-state segmentation, the per-boot polarity
   attestation rule, the MC-38 cross-check, the pairing-tolerance estimator and
   the horizon-support analysis;
2. the W09 tests (regression - W10 consumes the W09 parser, validity layer and
   export schema directly);
3. the whole existing host-tool suite (regression W02-W06);
4. the W02-W06 firmware static contract checks (regression - W10 adds no firmware
   code, so any change there is a regression to catch);
5. the W04, W05, W06 and W09 evidence dossier validators (regression over the
   read-only inputs this slice analyzes);
6. the W10 artifact reproduction check and the W10 dossier validator, which
   re-counts the source's door values and re-runs the detector instead of trusting
   the published verdict.

Exit code 0 only when every check passes. Nothing here flashes, energizes, opens a
door or touches hardware. A-W10-03 and A-W10-05 stay recorded as NOT COMPUTABLE ->
NEED_USER_ACTION: no committed capture contains a door-open event, and no host test
here may be read as a disturbance measurement.

Every test selection is resolved to the files that exist and printed, so the verdict
is reproducible from committed state alone and never borrowed from a neighbouring
worktree's uncommitted tests.
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


def select_test_files(stem: str) -> list[str]:
    """Resolve a discovery pattern to the test files that actually exist.

    Same rule as the W09 runner: a published PASS has to be reproducible from
    committed state alone, so every selection is resolved and named here rather
    than left as a glob that can silently match a neighbour's uncommitted files.
    """
    return sorted(path.name for path in (TOOLS / "tests").glob(f"{stem}.py"))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    evidence = REPO_ROOT / "evidence" / "A"
    w09 = evidence / "W09"
    w10 = evidence / "W10"
    test_suites = [
        (
            "host tools: W10 tests (door segmentation, attestation, pairing, horizon)",
            "test_cg_w10*", True,
        ),
        (
            "host tools: W09 tests (regression over the parser and validity layer)",
            "test_cg_w09*", True,
        ),
        ("host tools: full suite (regression W02-W06)", "test_*", False),
    ]
    checks: list[tuple[str, list[str], pathlib.Path]] = []
    unresolvable: list[str] = []
    for label, stem, show_files in test_suites:
        selected = select_test_files(stem)
        if not selected:
            unresolvable.append(f"{label}: pattern '{stem}.py' matched no test file")
            continue
        resolved = f"{', '.join(selected)}" if show_files else f"{len(selected)} file(s)"
        checks.append((
            f"{label} [{resolved}]",
            ["-m", "unittest", "discover", "-s", "tests", "-t", "tests", "-p", f"{stem}.py"],
            TOOLS,
        ))
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
            "evidence: W10 artifacts reproduce from the delivered tooling",
            [str(w10 / "build_w10_artifacts.py"), "--check"],
            w10,
        ),
        (
            "evidence: W10 dossier validator (hash pins, re-counted door values, "
            "NOT COMPUTABLE verdict intact)",
            [str(w10 / "validate_w10.py")],
            w10,
        ),
    ]

    failures = len(unresolvable)
    for message in unresolvable:
        print(f"[FAIL] {message}")
    for label, args, cwd in checks:
        ok, output = run(args, cwd)
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {label}")
        if not ok:
            failures += 1
            for line in output.strip().splitlines()[-25:]:
                print(f"        {line}")

    total = len(checks) + len(unresolvable)
    print()
    if failures:
        print(f"W10 CHECKS: {total - failures}/{total} passed - {failures} FAILED")
        return 1

    print(f"W10 CHECKS: {total}/{total} passed")
    print("Reminder: no door was opened, no stage was energized and no disturbance was")
    print("measured. The door->response metric is NOT COMPUTABLE because no committed")
    print("capture contains a door-open event, so A-W10-03 and A-W10-05 stay")
    print("NEED_USER_ACTION: run one repetition of S2-protocol-v1.md and commit the capture.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
