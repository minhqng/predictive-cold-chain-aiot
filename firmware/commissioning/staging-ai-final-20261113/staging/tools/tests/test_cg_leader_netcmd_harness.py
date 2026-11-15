"""Compile and run the Leader netcmd-ingress harness on the host.

``cg_leader_netcmd_harness.c`` links the real, unchanged W06 member sources
together with the Leader core (``cg_leader_ingress_core.c``) and asserts the
device-side integration contract offline: the envelope routing boundary, the
receiving-layer source classification, the delivered fail-closed validation
chain through the ingress, the idempotency replay, the not-stored mismatch
rule, and the TELEM-observation world model (complete-view policy, no ACK
self-pollution, reader-capacity parity).

Needs a host C compiler (MSVC through vswhere, or cc/gcc on PATH); skips with
an explicit reason if neither exists.
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

HARNESS = TESTS / "cg_leader_netcmd_harness.c"
COMPONENT_DIR = TOOLS.parent / "components" / "cg_leader_ingress"
CORE = COMPONENT_DIR / "cg_leader_ingress_core.c"
SOURCES = [
    MAIN / "cg_command.c",
    MAIN / "cg_quality.c",
    MAIN / "cg_health.c",
    MAIN / "cg_snapshot.c",
    MAIN / "cg_telemetry.c",
    MAIN / "cg_tec_control.c",
    MAIN / "cg_tec_limits.c",
    MAIN / "cg_tec_command.c",
    CORE,
]


def build_with_msvc(vcvars: pathlib.Path, workdir: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    exe = workdir / "cg_leader_netcmd_harness.exe"
    bat = workdir / "build_leader_netcmd.bat"
    log = workdir / "cl.log"
    lines = [
        "@echo off",
        f'call "{vcvars}" >nul',
        f'cd /d "{workdir}"',
        "cl /nologo /std:c11 /W4 /WX "
        f'/I"{MAIN}" /I"{COMPONENT_DIR}" "{HARNESS}" '
        + " ".join(f'"{source}"' for source in SOURCES) + " "
        f'/Fe:"{exe}" > "{log}" 2>&1',
        "exit /b %ERRORLEVEL%",
    ]
    bat.write_text("\r\n".join(lines) + "\r\n", encoding="ascii", newline="")
    result = subprocess.run(["cmd", "/c", str(bat)], capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not exe.exists():
        output = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        raise AssertionError(f"MSVC build failed (exit {result.returncode}):\n{output}\n"
                             f"{result.stdout}\n{result.stderr}")
    return exe, log


def build_with_gcc(cc: str, workdir: pathlib.Path) -> pathlib.Path:
    exe = workdir / "cg_leader_netcmd_harness"
    command = [
        cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I", str(MAIN), "-I", str(COMPONENT_DIR), str(HARNESS),
        *[str(source) for source in SOURCES], "-o", str(exe),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise AssertionError(f"C build failed: {' '.join(command)}\n"
                             f"{result.stdout}\n{result.stderr}")
    return exe


class LeaderNetcmdHarnessTests(unittest.TestCase):
    def _run(self) -> str:
        workdir = pathlib.Path(
            self.enterContext(tempfile.TemporaryDirectory(prefix="cg-leader-netcmd-")))
        vcvars = find_vcvars()
        if vcvars is not None:
            exe, _ = build_with_msvc(vcvars, workdir)
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
        self.assertIn("LEADER NETCMD CONTRACT: ALL SCENARIOS PASS", output)
        return output

    def test_scenarios_pass(self) -> None:
        output = self._run()
        match = re.search(r"(\d+)/(\d+) LEADER NETCMD scenarios passed", output)
        self.assertIsNotNone(match, f"no scenario count in:\n{output}")
        self.assertEqual(match.group(1), match.group(2))
        self.assertGreaterEqual(int(match.group(2)), 17)

    def test_component_reads_no_member_source(self) -> None:
        """The integration component must not carry member implementation
        copies: the delivered contracts are imported and linked, never
        duplicated into Leader files."""
        for source in (CORE, COMPONENT_DIR / "cg_leader_ingress.c"):
            text = source.read_text(encoding="utf-8")
            for delivered in ("cg_command_from_local_test(", "cg_tec_arm(",
                              "cg_tec_start(", "cg_log_init("):
                self.assertNotIn(delivered, text)

    def test_ingress_never_routes_to_the_actuator(self) -> None:
        """The netcmd path ends at the delivered validator: no call may exist
        from the component to a controller function (the W06 rule, held at
        the Leader seam as well)."""
        for source in (CORE, COMPONENT_DIR / "cg_leader_ingress.c"):
            text = source.read_text(encoding="utf-8")
            for forbidden in ("cg_tec_start(", "cg_actuator_", "cg_tec_arm(",
                              "cg_tec_control_init(", "set_cooling_duty("):
                self.assertNotIn(forbidden, text)

    def test_capable_build_stays_fail_closed_by_default(self) -> None:
        """The shipped world cannot accept a canonical command; the harness
        must pin that as the observable outcome (SAFETY_BLOCKED at the clock
        gate), not merely as an implementation detail."""
        harness = HARNESS.read_text(encoding="utf-8")
        self.assertIn("EPOCH_UNSYNCHRONIZED", harness)
        self.assertIn("SAFETY_BLOCKED", harness)


if __name__ == "__main__":
    unittest.main()
