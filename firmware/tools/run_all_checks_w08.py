"""Run every W08 check available without hardware.

    py firmware/tools/run_all_checks_w08.py

Runs, in order:

1. the host-tool unittest suite (W02 + W03 + W04 + W05 + W06 + W08 + W15), which
   compiles and runs the C harnesses against the real firmware sources;
2. the W08 analyzers on the committed captures only (`--no-local`), so a machine
   without Member A's bench tree still proves the committed half;
3. the W08 analyzers again with the local bench tree when it exists;
4. the W08 artifact reproduction check and the W08 dossier validator;
5. the W02-W06 evidence dossier validators and the W04-W06 static contract checks
   as regression (this branch stacks on all of them).

Exit code 0 only when every check passes. Nothing here flashes, energizes, opens
a serial port, or rewrites a limit. W08 changes no firmware, so no ESP-IDF build
is run or needed. The physical halves of A-W08-02, A-W08-03 and A-W08-04 stay
recorded as BLOCKED_HARDWARE / NEED_USER_ACTION / TEAM_DEPENDENCY rather than
simulated.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]

sys.path.insert(0, str(TOOLS))
import cg_w08_envelope as envelope  # noqa: E402  (for DEFAULT_BENCH_ROOT only)


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
    checks: list[tuple[str, list[str], pathlib.Path]] = [
        (
            "host tools: unittest suite (W02 + W03 + W04 + W05 + W06 + W08 + W15)",
            ["-m", "unittest", "discover", "-s", "tests", "-t", "tests"],
            TOOLS,
        ),
        (
            "tools: W08 electrical envelope, committed captures only",
            [str(TOOLS / "cg_w08_envelope.py"), "--no-local"],
            TOOLS,
        ),
        (
            "tools: W08 hot-side sustainability + fuse evaluation, committed only",
            [str(TOOLS / "cg_w08_hot_side.py"), "--no-local"],
            TOOLS,
        ),
        (
            "tools: W08 Gate A package, committed only",
            [str(TOOLS / "cg_w08_gate_a.py"), "--no-local"],
            TOOLS,
        ),
        (
            "evidence: W08 artifacts reproduce from the committed captures",
            [str(evidence / "W08" / "build_w08_artifacts.py"), "--check"],
            evidence / "W08",
        ),
        (
            "evidence: W08 dossier validator (pins, honest verdicts, no physical claim)",
            [str(evidence / "W08" / "validate_w08.py")],
            evidence / "W08",
        ),
        (
            "evidence: W15 dossier validator (regression: W15 reads the W08 declaration)",
            [str(evidence / "W15" / "validate_w15.py")],
            evidence / "W15",
        ),
    ]
    for name, args, cwd in [
        ("firmware: W06 static contract checks", ["cg_check_firmware_w06.py"], REPO_ROOT),
        ("firmware: W05 static contract checks", ["cg_check_firmware_w05.py"], REPO_ROOT),
        ("firmware: W04 static contract checks", ["cg_check_firmware_w04.py"], REPO_ROOT),
        ("firmware: W03 static contract checks", ["cg_check_firmware_w03.py"], REPO_ROOT),
        ("firmware: W02 static contract checks", ["cg_check_firmware.py"], REPO_ROOT),
    ]:
        checks.append((name, [str(TOOLS / args[0]), "--quiet"], cwd))
    for name, args, cwd in [
        ("evidence: W02 dossier validator", ["validate_w02.py"], evidence / "W02"),
        ("evidence: W03 dossier validator", ["validate_w03.py"], evidence / "W03"),
        ("evidence: W04 dossier validator", ["validate_w04.py"], evidence / "W04"),
        ("evidence: W05 dossier validator", ["validate_w05.py"], evidence / "W05"),
        ("evidence: W06 dossier validator", ["validate_w06.py"], evidence / "W06"),
    ]:
        checks.append((name, [str(args[0])], cwd))

    # Derived from this checkout (a sibling worktree), never a hard-coded
    # developer path: a reviewer whose bench tree lives elsewhere exports
    # CG_W08_BENCH_ROOT, and a machine with no bench tree simply skips these.
    bench = pathlib.Path(os.environ.get("CG_W08_BENCH_ROOT",
                                        str(envelope.DEFAULT_BENCH_ROOT)))
    if bench.is_dir():
        checks.insert(4, (
            "tools: W08 envelope + hot side with the local bench tree (18 sessions)",
            [str(TOOLS / "cg_w08_envelope.py")],
            TOOLS,
        ))
        checks.append((
            "evidence: W08 declaration still matches the local bench tree",
            [str(evidence / "W08" / "build_w08_artifacts.py"), "--check", "--verify-bench"],
            evidence / "W08",
        ))

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
        print(f"W08 CHECKS: {len(checks) - failures}/{len(checks)} passed - {failures} FAILED")
        print("Reminder: no check here compiled the firmware, opened a port or touched hardware.")
        return 1

    print(f"W08 CHECKS: {len(checks)}/{len(checks)} passed")
    print("Reminder: no check here compiled the firmware, opened a port or touched hardware.")
    print("Gate A is NOT CLOSED by these checks. A-W08-02 stays BLOCKED_HARDWARE (no")
    print("ampacity basis for the installed 1.75 mm2 branch, fuse marking never")
    print("photographed), A-W08-03's terminals/IBT-2 bullet stays NEED_USER_ACTION, and")
    print("A-W08-04 stays TEAM_DEPENDENCY: SAFE_LOCAL is Member D's policy state and the")
    print("delivered firmware has no transport. See evidence/A/W08/acceptance.md §4 for")
    print("the physical actions owed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
