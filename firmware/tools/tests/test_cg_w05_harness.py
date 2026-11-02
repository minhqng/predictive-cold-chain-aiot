"""Compile and run the W05 telemetry-foundation harness on the host.

``cg_w05_harness.c`` links the real, unchanged W05 sources
(``cg_quality.c``, ``cg_health.c``, ``cg_telemetry.c`` plus the control core it
reads) and asserts the A-W05-01/-04/-05 rules offline: the canonical quality
vocabulary, staleness, producer liveness, coherent-snapshot ages and sequences,
device identity, and the applied-vs-requested cooling split.

It also returns the measured worst-case schema-2 line length, which the budget
test below checks against ``CG_TELEMETRY_LINE_MAX`` in the shipped config. The
W04 budget argument was "the longest line we happened to capture is 1012 bytes";
W05 replaces it with a constructed worst case, because the field set grew and a
captured maximum no longer bounds the emitted maximum.

Needs a host C compiler (MSVC through vswhere, or cc/gcc on PATH). If neither
exists the test skips with an explicit reason instead of silently passing.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
MAIN = TOOLS.parent / "main"
TESTS = pathlib.Path(__file__).resolve().parent

sys.path.insert(0, str(TESTS))

from test_cg_tec_state_machine import find_gcc, find_vcvars  # noqa: E402

HARNESS = TESTS / "cg_w05_harness.c"
SOURCES = [
    MAIN / "cg_quality.c",
    MAIN / "cg_health.c",
    MAIN / "cg_snapshot.c",
    MAIN / "cg_telemetry.c",
    MAIN / "cg_tec_control.c",
    MAIN / "cg_tec_limits.c",
]
CONFIG = MAIN / "coldguard_config.h"


def _define_value(text: str, name: str) -> int | None:
    match = re.search(rf"^#define\s+{re.escape(name)}\s+(\d+)\b", text, re.MULTILINE)
    return int(match.group(1)) if match else None


def build_with_msvc(vcvars: pathlib.Path, workdir: pathlib.Path) -> pathlib.Path:
    exe = workdir / "cg_w05_harness.exe"
    bat = workdir / "build_w05.bat"
    log = workdir / "cl.log"
    lines = [
        "@echo off",
        f'call "{vcvars}" >nul',
        f'cd /d "{workdir}"',
        "cl /nologo /std:c11 /W4 /WX "
        f'/I"{MAIN}" "{HARNESS}" ' + " ".join(f'"{source}"' for source in SOURCES) + " "
        f'/Fe:"{exe}" > "{log}" 2>&1',
        "exit /b %ERRORLEVEL%",
    ]
    bat.write_text("\r\n".join(lines) + "\r\n", encoding="ascii", newline="")
    result = subprocess.run(["cmd", "/c", str(bat)], capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not exe.exists():
        output = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        raise AssertionError(f"MSVC build failed (exit {result.returncode}):\n{output}\n"
                             f"{result.stdout}\n{result.stderr}")
    return exe


def build_with_gcc(cc: str, workdir: pathlib.Path) -> pathlib.Path:
    exe = workdir / "cg_w05_harness"
    command = [
        cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(MAIN), str(HARNESS),
        *[str(source) for source in SOURCES], "-o", str(exe),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise AssertionError(f"C build failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return exe


class W05HarnessTests(unittest.TestCase):
    def _run(self) -> str:
        workdir = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory(prefix="cg-w05-")))
        vcvars = find_vcvars()
        if vcvars is not None:
            exe = build_with_msvc(vcvars, workdir)
            compiler = f"MSVC via {vcvars}"
        else:
            cc = find_gcc()
            if cc is None:
                self.skipTest("no host C compiler (MSVC or cc/gcc) found")
            exe = build_with_gcc(cc, workdir)
            compiler = cc
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, f"harness failed ({compiler}):\n{output}")
        self.assertNotIn("FAIL ", output)
        self.assertIn("W05 TELEMETRY FOUNDATION: ALL SCENARIOS PASS", output)
        return output

    def test_scenarios_pass(self) -> None:
        output = self._run()
        passed = re.search(r"(\d+)/(\d+) W05 scenarios passed", output)
        self.assertIsNotNone(passed, f"no scenario count in:\n{output}")
        self.assertEqual(passed.group(1), passed.group(2))
        self.assertGreaterEqual(int(passed.group(2)), 30)

    def test_measured_worst_case_fits_the_shipped_budget(self) -> None:
        output = self._run()
        match = re.search(r"worst_case_len=(\d+) budget=(\d+)", output)
        self.assertIsNotNone(match, f"harness did not report a worst-case length:\n{output}")
        measured = int(match.group(1))
        budget = int(match.group(2))
        declared = _define_value((CONFIG).read_text(encoding="utf-8"), "CG_TELEMETRY_LINE_MAX")
        self.assertEqual(budget, declared, "harness budget is not the shipped config value")
        # A worst case at 90 % of the budget would leave no room for a future
        # field, and the runner would silently start refusing frames.
        self.assertLess(measured * 10, budget * 9,
                        f"worst case {measured} leaves less than 10 % headroom in {budget}")

    def test_schema_version_is_two(self) -> None:
        text = CONFIG.read_text(encoding="utf-8")
        self.assertEqual(_define_value(text, "CG_TELEMETRY_SCHEMA_VERSION"), 2)


if __name__ == "__main__":
    unittest.main()
