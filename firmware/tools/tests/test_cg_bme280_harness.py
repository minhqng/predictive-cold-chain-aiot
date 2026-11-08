"""Executable proof for the BME280 producer (A-W02-06).

``cg_bme280_harness.c`` compiles the real, unchanged ``firmware/main/cg_bme280.c``
against a scripted I2C port. When no host C compiler is present the test skips
with an explicit reason rather than passing vacuously.
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

HARNESS = TESTS / "cg_bme280_harness.c"
SOURCES = [MAIN / "cg_bme280.c"]


class Bme280HarnessTests(unittest.TestCase):
    def _run(self) -> str:
        workdir = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory(prefix="cg-bme-")))
        vcvars = find_vcvars()
        if vcvars is not None:
            exe = build_with_msvc(vcvars, workdir, harness=HARNESS, sources=SOURCES,
                                  exe_name="cg_bme280_harness.exe")
            compiler = f"MSVC via {vcvars}"
        else:
            cc = find_gcc()
            if cc is None:
                self.skipTest("no host C compiler (MSVC or cc/gcc) found")
            exe = build_with_gcc(cc, workdir, harness=HARNESS, sources=SOURCES,
                                 exe_name="cg_bme280_harness")
            compiler = cc
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, f"harness failed ({compiler}):\n{output}")
        self.assertNotIn("FAIL ", output)
        self.assertIn("BME280 PRODUCER HARNESS: ALL SCENARIOS PASS", output)
        return output

    def test_scenarios_pass(self):
        self._run()

    def test_trim_gate_keeps_discarded_values_for_the_reference_comparison(self):
        """The fail-closed gate must drop the published value yet preserve the
        compensated numbers in an explicit UNVALIDATED diagnostic, otherwise the
        trim layout could never be confirmed against a reference instrument."""
        output = self._run()
        line = next((l for l in output.splitlines() if l.startswith("TRIM_GATE")), None)
        self.assertIsNotNone(line, f"no TRIM_GATE line in:\n{output}")
        self.assertIn("valid=0", line)
        self.assertIn("reason=TRIM_UNCONFIRMED", line)
        self.assertIn("unvalidated_t_c=24.37", line)
        self.assertIn("unvalidated_rh_pct=51.28", line)

    def test_driver_does_not_reach_the_i2c_driver_from_pure_code(self):
        """The transport boundary must stay real: the pure producer cannot pull in
        ESP-IDF headers, which is what lets this file compile on a host at all."""
        text = (MAIN / "cg_bme280.c").read_text(encoding="utf-8")
        header = (MAIN / "cg_bme280.h").read_text(encoding="utf-8")
        for banned in ("driver/i2c", "freertos/", "esp_err.h", "esp_log.h", "i2c_master.h"):
            self.assertNotIn(banned, text, f"pure producer must not include {banned}")
            self.assertNotIn(banned, header, f"public header must not include {banned}")

    def test_no_ambient_value_is_published_without_a_reading(self):
        """Absence and refusal paths must never mint a value or a sequence number."""
        text = (MAIN / "cg_bme280.c").read_text(encoding="utf-8")
        self.assertIn("out->valid = true", text)
        self.assertEqual(text.count("out->valid = true"), 1,
                         "exactly one place may declare an ambient reading valid")
        self.assertIn("s->seq++", text)
        self.assertEqual(text.count("s->seq++"), 1,
                         "exactly one place may consume a producer sequence number")


if __name__ == "__main__":
    unittest.main()
