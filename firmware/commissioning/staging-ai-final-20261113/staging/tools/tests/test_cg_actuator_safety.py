"""W03-specific actuator safety tests.

The shared ``cg_gpio_map`` module proves the generic rules; this file proves
the W03 firmware actually satisfies them, and that the W03 output gate
cannot be satisfied while authorization is absent:

1. ``cg_actuator_force_off`` drives RPWM, R_EN and L_EN low, enables first.
2. Dropping L_EN from that function is detected (the exact regression a
   two-pin W02-era edit would introduce).
3. The safe-OFF log line carries all three pins, so a capture can prove the
   three-pin state rather than infer it from two.
4. ``cg_actuator_outputs_allowed`` refuses while CG_ACTUATOR_ENABLE_ALLOWED
   is 0, and the permission is a compile-time gate, not a runtime default.
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_gpio_map  # noqa: E402

REPO_ROOT = TOOLS.parents[1]
MAIN = REPO_ROOT / "firmware" / "main"

SIGNATURE = r"void\s+cg_actuator_force_off\s*\([^)]*\)"


def problems(source: str) -> list[str]:
    return cg_gpio_map.safe_off_problems(
        source,
        rpwm="CG_ACTUATOR_RPWM_PIN",
        ren="CG_ACTUATOR_REN_PIN",
        len_pin="CG_ACTUATOR_LEN_PIN",
        signature=SIGNATURE,
    )


class RealActuatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = (MAIN / "cg_actuator.c").read_text(encoding="utf-8")

    def test_three_pin_safe_off_passes(self) -> None:
        self.assertEqual(problems(self.source), [])

    def test_every_pin_appears_in_the_mask(self) -> None:
        body = cg_gpio_map.extract_function_body(
            cg_gpio_map.strip_comments(self.source), SIGNATURE
        )
        self.assertIsNotNone(body)
        for macro in ("CG_ACTUATOR_RPWM_PIN", "CG_ACTUATOR_REN_PIN", "CG_ACTUATOR_LEN_PIN"):
            self.assertGreaterEqual(body.count(macro), 2, macro)

    def test_no_write_of_a_logical_one(self) -> None:
        stripped = cg_gpio_map.strip_comments(self.source)
        self.assertIsNone(
            re.search(r"gpio_set_level\s*\(\s*CG_ACTUATOR_\w+_PIN\s*,\s*1\s*\)", stripped)
        )

    def test_enables_are_cleared_before_rpwm(self) -> None:
        body = cg_gpio_map.extract_function_body(
            cg_gpio_map.strip_comments(self.source), SIGNATURE
        )
        self.assertLess(
            body.find("gpio_set_level(CG_ACTUATOR_REN_PIN, 0)"),
            body.find("gpio_set_level(CG_ACTUATOR_RPWM_PIN, 0)"),
        )
        self.assertLess(
            body.find("gpio_set_level(CG_ACTUATOR_LEN_PIN, 0)"),
            body.find("gpio_set_level(CG_ACTUATOR_RPWM_PIN, 0)"),
        )


class OmissionRegressionTests(unittest.TestCase):
    def test_omitting_len_is_detected(self) -> None:
        source = (MAIN / "cg_actuator.c").read_text(encoding="utf-8")
        broken = source.replace("    (void)gpio_set_level(CG_ACTUATOR_LEN_PIN, 0);\n", "")
        self.assertNotEqual(broken, source)
        detected = problems(broken)
        self.assertTrue(any("CG_ACTUATOR_LEN_PIN" in item for item in detected), detected)

    def test_omitting_len_from_mask_is_detected(self) -> None:
        source = """
void cg_actuator_force_off(void)
{
    gpio_config_t config = {
        .pin_bit_mask = (1ULL << 5) | (1ULL << 6),
    };
    (void)gpio_set_level(CG_ACTUATOR_REN_PIN, 0);
    (void)gpio_set_level(CG_ACTUATOR_RPWM_PIN, 0);
}
"""
        self.assertTrue(any("CG_ACTUATOR_LEN_PIN" in item for item in problems(source)))


class OutputGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = (MAIN / "coldguard_config.h").read_text(encoding="utf-8")
        self.source = cg_gpio_map.strip_comments(
            (MAIN / "cg_actuator.c").read_text(encoding="utf-8")
        )

    def test_enable_allowed_is_zero(self) -> None:
        self.assertIn("#define CG_ACTUATOR_ENABLE_ALLOWED 0", self.config)

    def test_enable_gate_is_compile_time(self) -> None:
        self.assertIn("#if CG_ACTUATOR_ENABLE_ALLOWED != 1", self.source)
        body = cg_gpio_map.extract_function_body(
            self.source, r"bool\s+cg_actuator_outputs_allowed\s*\([^)]*\)"
        )
        self.assertIsNotNone(body)
        gate = body.find("#if CG_ACTUATOR_ENABLE_ALLOWED != 1")
        self.assertNotEqual(gate, -1)
        self.assertLess(gate, body.find("return true"))

    def test_authorization_is_required(self) -> None:
        body = cg_gpio_map.extract_function_body(
            self.source, r"bool\s+cg_actuator_outputs_allowed\s*\([^)]*\)"
        )
        self.assertIn("if (!operator_authorized)", body)
        self.assertLess(
            body.find("if (!operator_authorized)"),
            body.find("return true"),
        )


class SafeOffLogTests(unittest.TestCase):
    def test_safety_line_carries_all_three_pins(self) -> None:
        log_c = (MAIN / "cg_log.c").read_text(encoding="utf-8")
        log_h = (MAIN / "cg_log.h").read_text(encoding="utf-8")
        self.assertIn("CG_PIN_IBT2_REN", log_c)
        self.assertIn("CG_PIN_IBT2_LEN", log_c)
        self.assertIn("CG_PIN_IBT2_COOLING_PWM", log_c)
        self.assertIn("#CG SAFETY actuator=OFF pwm=5 en=6 len=10", log_h)


if __name__ == "__main__":
    unittest.main()
