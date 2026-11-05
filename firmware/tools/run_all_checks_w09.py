"""Run every W09 check available without hardware.

    py firmware/tools/run_all_checks_w09.py

Runs, in order:

1. the W09 host-tool tests: the capture parser, the validity/invalidation layer,
   the run protocol, the per-probe noise estimator and the evidence-grade export
   plus the run index;
2. the whole existing host-tool suite (regression across W02-W07);
3. the firmware static contract checks for W02-W06 (regression - W09 adds no
   firmware code, so any change there is a regression to catch);
4. the W04, W05 and W06 evidence dossier validators (regression over the read-only
   inputs this slice analyzes);
5. the W09 artifact reproduction check and the W09 dossier validator, which pins
   the bytes and re-derives every published number from the real capture.

The W10 door and pairing tests are deliberately NOT a W09 gate. They were listed
here while both weeks sat in one branch, which made the W09 verdict depend on files
the W09 slice does not own; on a W09-only checkout that selection resolves to
nothing, and a runner that requires it can only pass by borrowing another week's
bytes. The dependency is checked in the direction that exists: W10 stacks on this
branch, and `run_all_checks_w10.py` runs the whole W09 suite as its regression.

Test selection is resolved from the files this runner can see and every selected
file is printed, because a published PASS must be reproducible from committed
state alone. An earlier revision of this file discovered ``test_cg_w11*``; those
tests belong to another slice and are not tracked here, so the W09 verdict was
being borrowed from bytes that were only ever sitting in somebody's working
tree. A slice may never depend on uncommitted work to look green.

Exit code 0 only when every check passes. Nothing here flashes, energizes or
touches hardware, and no check here stands in for the S1 acquisition session:
A-W09-02 stays recorded as NEED_USER_ACTION, because the required physical run
has not happened and no host fixture may be presented as a measured dataset.
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


def select_test_files(pattern: str) -> list[str]:
    """Resolve a discovery pattern to the test files that actually exist.

    A runner that hands an unresolvable glob to ``unittest discover`` reports a
    silent zero-test pass, and a glob that only matches a neighbour's uncommitted
    files reports a borrowed pass. Printing the resolved names is what lets a
    reviewer re-check the selection against ``git ls-files``.
    """
    return sorted(path.name for path in (TOOLS / "tests").glob(f"{pattern}.py"))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    evidence = REPO_ROOT / "evidence" / "A"
    w09 = evidence / "W09"
    test_suites = [
        ("host tools: W09 tests (parser, validity, noise, protocol, export, index)", "test_cg_w09*", True),
        ("host tools: full suite (regression W02-W07)", "test_*", False),
    ]
    checks: list[tuple[str, list[str], pathlib.Path]] = []
    unresolvable: list[str] = []
    for label, stem, show_files in test_suites:
        selected = select_test_files(stem)
        if not selected:
            # A selection that resolves to nothing is a failure, never an empty
            # pass: it means the runner depends on files this branch does not have.
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
        validator = evidence / folder / f"validate_{folder.lower()}.py"
        if validator.is_file():
            checks.append((
                f"evidence: {folder} dossier validator (regression)",
                [str(validator)],
                evidence / folder,
            ))
    checks += [
        (
            "evidence: W09 artifacts reproduce from the delivered tooling",
            [str(w09 / "build_w09_artifacts.py"), "--check"],
            w09,
        ),
        (
            "evidence: W09 dossier validator (hash pins, re-derived rows, honest verdicts)",
            [str(w09 / "validate_w09.py")],
            w09,
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
        print(f"W09 CHECKS: {total - failures}/{total} passed - {failures} FAILED")
        return 1

    print(f"W09 CHECKS: {total}/{total} passed")
    print("Reminder: no check here compiled the firmware, energized a stage, or ran a")
    print("physical session. A-W09-02 is REAL DATA NOT AVAILABLE -> NEED_USER_ACTION:")
    print("the S1 baseline runs still have to be acquired with the delivered checklist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
