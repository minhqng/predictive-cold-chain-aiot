"""Compile and run the W06 command/ACK harness on the host.

``cg_w06_harness.c`` links the real, unchanged W06 sources (``cg_command.c``,
``cg_telemetry.c``, ``cg_snapshot.c``, ``cg_tec_command.c`` plus the control core)
and asserts the docs/02 §28-§32 device rules offline: the validation chain,
idempotency, the fail-closed freshness decision, the ACK payload, and the
desired-versus-applied split.

Two things this test file pins explicitly, because they are the load-bearing
claims of the slice:

* on the shipped context the command layer cannot accept anything, so the
  firmware cannot actuate through it;
* the idempotency store is volatile, so no command identity survives a reset.

Needs a host C compiler (MSVC through vswhere, or cc/gcc on PATH); skips with an
explicit reason if neither exists.
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
from test_cg_w05_harness import build_with_gcc as w05_build_gcc  # noqa: E402
from test_cg_w05_harness import build_with_msvc as w05_build_msvc  # noqa: E402

HARNESS = TESTS / "cg_w06_harness.c"
SOURCES = [
    MAIN / "cg_command.c",
    MAIN / "cg_quality.c",
    MAIN / "cg_health.c",
    MAIN / "cg_snapshot.c",
    MAIN / "cg_telemetry.c",
    MAIN / "cg_tec_control.c",
    MAIN / "cg_tec_limits.c",
    MAIN / "cg_tec_command.c",
]
CONFIG = MAIN / "coldguard_config.h"
COMMISSION = MAIN / "cg_commission.c"


def build_with_msvc(vcvars: pathlib.Path, workdir: pathlib.Path) -> pathlib.Path:
    return w05_build_msvc(vcvars, workdir, HARNESS, SOURCES, "cg_w06_harness.exe")


def build_with_gcc(cc: str, workdir: pathlib.Path) -> pathlib.Path:
    return w05_build_gcc(cc, workdir, HARNESS, SOURCES, "cg_w06_harness")


class W06HarnessTests(unittest.TestCase):
    def _run(self) -> str:
        workdir = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory(prefix="cg-w06-")))
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
        self.assertIn("W06 COMMAND/ACK CONTRACT: ALL SCENARIOS PASS", output)
        return output

    def test_scenarios_pass(self) -> None:
        output = self._run()
        match = re.search(r"(\d+)/(\d+) W06 scenarios passed", output)
        self.assertIsNotNone(match, f"no scenario count in:\n{output}")
        self.assertEqual(match.group(1), match.group(2))
        self.assertGreaterEqual(int(match.group(2)), 30)

    def test_shipped_firmware_context_blocks_everything(self) -> None:
        """The command layer must not become a back door around the W04 gate."""
        config = CONFIG.read_text(encoding="utf-8")
        commission = COMMISSION.read_text(encoding="utf-8")
        self.assertIn("#define CG_TEC_OUTPUT_STAGE_ENABLED 0", config)
        self.assertIn("#define CG_TEC_REQUEST_DUTY_PERMILLE 0", config)
        self.assertIn("ctx->time_sync = CG_TIME_SYNC_UNSYNCHRONIZED;", commission)
        self.assertIn("ctx->local_safety_permits = ops->output_stage_available() && "
                     "limits_resolved;", commission)
        # The shipped allowed duty comes from the limit table, never a literal.
        self.assertNotIn("allowed_duty_max_permille = 1", commission)
        self.assertIn("allowed_duty_max_permille =", commission)

    def test_no_actuator_call_on_the_command_path(self) -> None:
        """A-W06 must not route a command to the output stage. Physical
        application belongs behind the controller gate and an operator
        authorization this slice does not have."""
        commission = COMMISSION.read_text(encoding="utf-8")
        command = (MAIN / "cg_command.c").read_text(encoding="utf-8")
        for forbidden in ("cg_tec_start(", "cg_actuator_", "cg_tec_hw_ops()->set_enables",
                          "set_cooling_duty("):
            self.assertNotIn(forbidden, command)
        # cg_tec_start stays exactly where W04 left it: the console START verb.
        self.assertEqual(commission.count("cg_tec_start(&s_ctl"), 1)

    def test_store_is_volatile(self) -> None:
        """No NVS, no persistence: a reset must not resurrect a command identity
        or a desire (docs/02 §31.2-§31.3)."""
        for source in (COMMISSION, MAIN / "cg_command.c"):
            text = source.read_text(encoding="utf-8")
            self.assertNotIn("nvs_", text)
        header = (MAIN / "cg_command.h").read_text(encoding="utf-8")
        self.assertRegex(header, r"CG_CMD_STORE_CAPACITY\s+\d+")


if __name__ == "__main__":
    unittest.main()
