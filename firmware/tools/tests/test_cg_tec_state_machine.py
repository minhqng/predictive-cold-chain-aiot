"""Compile and run the W04 TEC state-machine harness on the host.

The harness (``cg_tec_harness.c``) links the real, unchanged control core
(``firmware/main/cg_tec_control.c`` + ``cg_tec_limits.c``) against a recording
fake backend and asserts the fail-closed contract offline: boot, reset,
timeout, invalid/stale sensor, hardware rejection, unauthorized request and
every fault path end with the branch de-energized.

Needs a host C compiler. MSVC is located through vswhere (or the standard
install roots); ``cc``/``gcc`` on PATH is used as a fallback. If neither is
available the test is skipped with an explicit reason rather than silently
passing.
"""

from __future__ import annotations

import glob
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
MAIN = TOOLS.parent / "main"
TESTS = pathlib.Path(__file__).resolve().parent

HARNESS = TESTS / "cg_tec_harness.c"
SOURCES = [MAIN / "cg_tec_control.c", MAIN / "cg_tec_limits.c", MAIN / "cg_telemetry.c",
           MAIN / "cg_quality.c", MAIN / "cg_health.c"]

VSWHERE = pathlib.Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")


def find_vcvars() -> pathlib.Path | None:
    candidates: list[pathlib.Path] = []
    if VSWHERE.exists():
        try:
            result = subprocess.run(
                [
                    str(VSWHERE),
                    "-latest",
                    "-products",
                    "*",
                    "-requires",
                    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                    "-property",
                    "installationPath",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line:
                    candidates.append(pathlib.Path(line) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat")
        except (OSError, subprocess.SubprocessError):
            pass
    for root in (
        r"C:\Program Files (x86)\Microsoft Visual Studio",
        r"C:\Program Files\Microsoft Visual Studio",
    ):
        candidates.extend(pathlib.Path(p) for p in glob.glob(os.path.join(root, "*", "*", "VC", "Auxiliary", "Build", "vcvars64.bat")))
        candidates.extend(pathlib.Path(p) for p in glob.glob(os.path.join(root, "*", "VC", "Auxiliary", "Build", "vcvars64.bat")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def find_gcc() -> str | None:
    for name in ("cc", "gcc", "clang"):
        path = shutil.which(name)
        if path:
            return path
    return None


def build_with_msvc(vcvars: pathlib.Path, workdir: pathlib.Path) -> pathlib.Path:
    exe = workdir / "cg_tec_harness.exe"
    bat = workdir / "build.bat"
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
    # cmd.exe needs CRLF in a .bat file.
    bat.write_text("\r\n".join(lines) + "\r\n", encoding="ascii", newline="")
    result = subprocess.run(["cmd", "/c", str(bat)], capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not exe.exists():
        output = log.read_text(encoding="utf-8", errors="replace") if log.exists() else result.stdout + result.stderr
        raise AssertionError(f"MSVC build failed (exit {result.returncode}):\n{output}")
    return exe


def build_with_gcc(cc: str, workdir: pathlib.Path) -> pathlib.Path:
    exe = workdir / "cg_tec_harness"
    command = [
        cc,
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(MAIN),
        str(HARNESS),
        *[str(source) for source in SOURCES],
        "-o",
        str(exe),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise AssertionError(f"C build failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return exe


class StateMachineHarnessTests(unittest.TestCase):
    def test_fail_closed_scenarios(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cg-tec-harness-") as tmp:
            workdir = pathlib.Path(tmp)
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
            self.assertIn("TEC STATE MACHINE: ALL SCENARIOS PASS", output)
            self.assertIn("34/34 scenarios passed", output)
            # The harness prints one PASS line per scenario; a buried FAIL
            # would be a contradiction even if main() miscounted.
            self.assertNotIn("FAIL ", output)
            self.assertNotIn("assert failed", output)


if __name__ == "__main__":
    unittest.main()
