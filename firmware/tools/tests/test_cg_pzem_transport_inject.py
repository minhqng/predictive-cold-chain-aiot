"""Regression guards for the A-W21-03 transport-boundary PZEM injection.

Two layers:
  * a host build of cg_pzem.c with the gate on/off proves INJECT_DISABLED exists
    and names correctly only in the test build (production unaffected);
  * source-contract assertions prove the injection sits at the transport
    boundary (before any RS-485 write) and that the former post-poll status
    override is gone, so a suppressed transaction can never be reported as a
    natural timeout or a successful Modbus parse.
"""
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
MAIN = TESTS.parent.parent / "main"
sys.path.insert(0, str(TESTS))

from test_cg_tec_state_machine import find_gcc, find_vcvars  # noqa: E402

HARNESS = TESTS / "cg_pzem_inject_harness.c"
SOURCES = [MAIN / "cg_pzem.c", MAIN / "cg_crc16.c"]


def _build_run(workdir, define):
    vcvars = find_vcvars()
    if vcvars is not None:
        exe = workdir / "h.exe"
        dflag = f"/D{define}" if define else ""
        lines = ["@echo off", f'call "{vcvars}" >nul', f'cd /d "{workdir}"',
                 f"cl /nologo /std:c11 /W4 /WX {dflag} "
                 f'/I"{MAIN}" "{HARNESS}" '
                 + " ".join(f'"{s}"' for s in SOURCES) + f' /Fe:"{exe}" > cl.log 2>&1']
        (workdir / "b.bat").write_text("\n".join(lines) + "\n", encoding="utf-8")
        r = subprocess.run(["cmd", "/c", str(workdir / "b.bat")],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not exe.exists():
            raise AssertionError(f"MSVC build failed:\n{(workdir/'cl.log').read_text(errors='ignore')}")
    else:
        cc = find_gcc()
        if cc is None:
            raise unittest.SkipTest("no host C compiler found")
        exe = workdir / "h"
        cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror"]
        if define:
            cmd.append(f"-D{define}")
        cmd += ["-I", str(MAIN), str(HARNESS)] + [str(s) for s in SOURCES] + ["-o", str(exe)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise AssertionError(f"gcc build failed:\n{r.stdout}\n{r.stderr}")
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout


class PzemTransportInjectTests(unittest.TestCase):
    def test_status_gated_on(self):
        with tempfile.TemporaryDirectory() as td:
            out = _build_run(pathlib.Path(td), "CG_FAULT_INJECTION=1")
        self.assertIn("PZEM_INJECT GATED_ON OK", out)

    def test_status_gated_off(self):
        with tempfile.TemporaryDirectory() as td:
            out = _build_run(pathlib.Path(td), None)
        self.assertIn("PZEM_INJECT GATED_OFF OK", out)

    def test_injection_is_at_transport_boundary_not_post_poll(self):
        power = (MAIN / "cg_power.c").read_text(encoding="utf-8")
        # The only pzem-down decision must live in link_transaction, before the
        # first RS-485 write, and must return the disabled status without parsing.
        link = power.split("static cg_link_result_t link_transaction", 1)[1]
        link = link.split("\nstatic ", 1)[0]
        self.assertIn("cg_fault_inject_pzem_down()", link)
        self.assertIn("CG_PZEM_INJECT_DISABLED", link)
        self.assertIn("cg_rs485_flush_input()", link)
        guard = link.index("cg_fault_inject_pzem_down()")
        write = link.index("cg_rs485_write(")
        self.assertLess(guard, write, "injection must precede any transmit")
        # poll_once must no longer override status after a successful parse.
        poll = power.split("static void poll_once", 1)[1].split("\nstatic ", 1)[0]
        self.assertNotIn("cg_fault_inject_pzem_down()", poll)

    def test_disabled_status_is_compile_gated(self):
        header = (MAIN / "cg_pzem.h").read_text(encoding="utf-8")
        self.assertRegex(header, r"#if defined\(CG_FAULT_INJECTION\) && CG_FAULT_INJECTION\s*\n[^#]*CG_PZEM_INJECT_DISABLED")

    def test_default_config_keeps_injection_disabled(self):
        config = (MAIN / "coldguard_config.h").read_text(encoding="utf-8")
        self.assertIn("#define CG_FAULT_INJECTION 0", config)


if __name__ == "__main__":
    unittest.main()
