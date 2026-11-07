"""Host proof for the test-only fault-injection module (A-W21-02/03).

Builds cg_fault_inject_harness.c against the real cg_fault_inject.c twice:
with CG_FAULT_INJECTION=1 (enabled) and =0 (production-disabled), and runs
both. Skips with an explicit reason when no host C compiler is present, never
passing vacuously. This is host software evidence only; it does not claim
on-device acceptance.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
MAIN = TESTS.parent.parent / "main"
sys.path.insert(0, str(TESTS))

from test_cg_tec_state_machine import find_gcc, find_vcvars  # noqa: E402

HARNESS = TESTS / "cg_fault_inject_harness.c"
SOURCES = [MAIN / "cg_fault_inject.c"]


def _build_and_run(workdir: pathlib.Path, define: str | None) -> str:
    vcvars = find_vcvars()
    if vcvars is not None:
        exe = workdir / "cg_fault_inject_harness.exe"
        log = workdir / "cl.log"
        dflag = f"/D{define}" if define else ""
        lines = [
            "@echo off",
            f'call "{vcvars}" >nul',
            f'cd /d "{workdir}"',
            f"cl /nologo /std:c11 /W4 /WX {dflag} "
            f'/I"{MAIN}" "{HARNESS}" '
            + " ".join(f'"{s}"' for s in SOURCES)
            + f' /Fe:"{exe}" > "{log}" 2>&1',
        ]
        (workdir / "build.bat").write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = subprocess.run(["cmd", "/c", str(workdir / "build.bat")],
                                capture_output=True, text=True, timeout=300)
        if result.returncode != 0 or not exe.exists():
            raise AssertionError(f"MSVC build failed:\n{result.stdout}\n"
                                 f"{(workdir / 'cl.log').read_text(errors='ignore')}")
    else:
        cc = find_gcc()
        if cc is None:
            raise unittest.SkipTest("no host C compiler (MSVC or cc/gcc) found")
        exe = workdir / "cg_fault_inject_harness"
        command = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror"]
        if define:
            command.append(f"-D{define}")
        command += ["-I", str(MAIN), str(HARNESS)] + [str(s) for s in SOURCES] + ["-o", str(exe)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise AssertionError(f"gcc build failed:\n{result.stdout}\n{result.stderr}")
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
    output = run.stdout + run.stderr
    assert run.returncode == 0, f"harness failed:\n{output}"
    assert "FAIL " not in output, output
    return output


class FaultInjectHarnessTests(unittest.TestCase):
    def test_enabled_build_scenarios_pass(self):
        with tempfile.TemporaryDirectory(prefix="cg-fi-on-") as td:
            output = _build_and_run(pathlib.Path(td), "CG_FAULT_INJECTION=1")
        self.assertIn("FAULT_INJECT ENABLED HARNESS: ALL PASS", output)

    def test_production_build_is_inert(self):
        with tempfile.TemporaryDirectory(prefix="cg-fi-off-") as td:
            output = _build_and_run(pathlib.Path(td), None)
        self.assertIn("FAULT_INJECT DISABLED HARNESS: ALL PASS", output)

    def test_pure_module_has_no_esp_dependency(self):
        text = (MAIN / "cg_fault_inject.c").read_text(encoding="utf-8")
        header = (MAIN / "cg_fault_inject.h").read_text(encoding="utf-8")
        for banned in ("driver/", "freertos/", "esp_", "i2c_master.h", "nvs"):
            self.assertNotIn(banned, text, f"cg_fault_inject.c must not include {banned}")
            self.assertNotIn(banned, header, f"cg_fault_inject.h must not include {banned}")

    def test_default_config_keeps_injection_disabled(self):
        config = (MAIN / "coldguard_config.h").read_text(encoding="utf-8")
        self.assertIn("#define CG_FAULT_INJECTION 0", config)


if __name__ == "__main__":
    unittest.main()
