"""Executable proof for the BME280 producer's firmware integration (A-W02-06).

``cg_bme280_integration_harness.c`` compiles the unchanged ``firmware/main``
telemetry, snapshot and quality sources and drives the ambient channel through
the states a real module can be in. The unit is skipped with an explicit reason
when no host C compiler is present, never passed vacuously.
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
TOOLS = TESTS.parent
MAIN = TOOLS.parent / "main"
sys.path.insert(0, str(TESTS))

from test_cg_w05_harness import build_with_gcc, build_with_msvc  # noqa: E402
from test_cg_tec_state_machine import find_gcc, find_vcvars  # noqa: E402

HARNESS = TESTS / "cg_bme280_integration_harness.c"
SOURCES = [
    MAIN / "cg_bme280.c",
    MAIN / "cg_quality.c",
    MAIN / "cg_health.c",
    MAIN / "cg_snapshot.c",
    MAIN / "cg_telemetry.c",
    MAIN / "cg_command.c",
    MAIN / "cg_tec_control.c",
    MAIN / "cg_tec_limits.c",
]


class Bme280IntegrationHarnessTests(unittest.TestCase):
    def _run(self) -> str:
        workdir = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory(prefix="cg-bme-int-")))
        vcvars = find_vcvars()
        if vcvars is not None:
            exe = build_with_msvc(vcvars, workdir, harness=HARNESS, sources=SOURCES,
                                  exe_name="cg_bme280_integration_harness.exe")
            compiler = f"MSVC via {vcvars}"
        else:
            cc = find_gcc()
            if cc is None:
                self.skipTest("no host C compiler (MSVC or cc/gcc) found")
            exe = build_with_gcc(cc, workdir, harness=HARNESS, sources=SOURCES,
                                 exe_name="cg_bme280_integration_harness")
            compiler = cc
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, f"integration harness failed ({compiler}):\n{output}")
        self.assertNotIn("FAIL ", output)
        self.assertIn("BME280 INTEGRATION HARNESS: ALL SCENARIOS PASS", output)
        return output

    def test_scenarios_pass(self):
        self._run()

    def test_ambient_fields_are_emitted_from_the_snapshot_not_a_constant(self):
        """The formatter must read the published observation, so a hand-edited
        constant cannot silently replace the producer's answer."""
        text = (MAIN / "cg_telemetry.c").read_text(encoding="utf-8")
        self.assertIn("env_status(snap, now_ms)", text)
        self.assertIn("snap->env_temperature_c", text)
        self.assertIn("snap->env_humidity_pct", text)
        # The pre-integration build hard-coded both ambient slots as missing.
        self.assertNotIn("quality_in.bme_present = false;", text)

    def test_pure_producer_stays_free_of_esp_headers(self):
        """Only cg_bme280_idf.c may reach the I2C driver; that boundary is what
        lets this file and the decision-logic harness compile on a host."""
        for name in ("cg_bme280.c", "cg_bme280.h"):
            text = (MAIN / name).read_text(encoding="utf-8")
            for banned in ("driver/i2c", "freertos/", "esp_err.h", "esp_log.h", "i2c_master.h"):
                self.assertNotIn(banned, text, f"{name} must not include {banned}")


if __name__ == "__main__":
    unittest.main()
