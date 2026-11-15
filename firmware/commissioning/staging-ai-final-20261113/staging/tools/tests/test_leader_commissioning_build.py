"""Generator profile validation: explicit TEC1000 demo, no silent envelopes."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "leader_commissioning_build", TOOLS / "leader_commissioning_build.py")
generator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generator
SPEC.loader.exec_module(generator)


class LeaderCommissioningBuildProfileTests(unittest.TestCase):
    def test_full_duty_demo_requires_every_explicit_flag(self) -> None:
        combos = (
            ["--supervised-full-duty-demo", "--supervised-limits",
             "--supervised-no-cold-probe"],  # missing duty 1000
            ["--supervised-full-duty-demo", "--supervised-no-cold-probe",
             "--duty-permille", "1000"],     # missing supervised limits
            ["--supervised-full-duty-demo", "--supervised-limits",
             "--duty-permille", "1000"],     # missing no-cold profile
            ["--supervised-limits", "--supervised-no-cold-probe",
             "--duty-permille", "1000"],     # 1000 without the demo flag
        )
        for extra in combos:
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as tmp:
                output = pathlib.Path(tmp) / "out"
                with self.assertRaises(SystemExit):
                    generator.main(["--output", str(output),
                                    "--interlock-mode", "none", *extra])
                # Refusal happens before any output mutation.
                self.assertFalse(output.exists())

    def test_tec200_no_cold_stays_the_normal_flag_only_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp) / "out"
            self.assertEqual(generator.main([
                "--output", str(output), "--interlock-mode", "none",
                "--supervised-limits", "--supervised-no-cold-probe",
                "--duty-permille", "200"]), 0)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["inputs"]["supervised_profile"], "TEC200")
            self.assertEqual(
                manifest["inputs"]["threshold_semantics"]["current_stop_a"], 5.0)
            self.assertIs(manifest["inputs"]["continuous"], False)
            self.assertIn("timed run deadline",
                          manifest["inputs"]["threshold_semantics"]["on_time_semantics"])

    def test_tec1000_manifest_records_profile_actual_pwm_and_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp) / "out"
            self.assertEqual(generator.main([
                "--output", str(output), "--interlock-mode", "none",
                "--supervised-limits", "--supervised-no-cold-probe",
                "--supervised-full-duty-demo", "--duty-permille", "1000"]), 0)
            inputs = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8"))["inputs"]
            self.assertEqual(inputs["supervised_profile"], "TEC1000")
            self.assertEqual(inputs["duty_permille"], 1000)
            self.assertIn("8191/8192", inputs["requested_pwm_steps"])
            self.assertEqual(inputs["threshold_semantics"]["current_stop_a"], 10.0)
            self.assertEqual(inputs["threshold_semantics"]["hot_side_stop_c"], 40.0)
            self.assertEqual(inputs["threshold_semantics"]["on_time_max_ms"], 30000)
            self.assertIs(inputs["continuous"], True)
            self.assertEqual(inputs["ai_demo_lease_ms"], 3000)
            self.assertIn("timed-command cap",
                          inputs["threshold_semantics"]["on_time_semantics"])
            self.assertIs(inputs["threshold_semantics"]["continuous_until_stop"], True)
            patched = (output / "staging" / "main" / "coldguard_config.h").read_text(
                encoding="utf-8")
            self.assertIn("#define CG_TEC_REQUEST_DUTY_PERMILLE 1000", patched)
            self.assertIn("CONFIG_CG_LEADER_TEC_HW_SUPERVISED_FULL_DUTY_DEMO=y",
                          (output / "staging" / "sdkconfig.defaults").read_text(
                              encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
