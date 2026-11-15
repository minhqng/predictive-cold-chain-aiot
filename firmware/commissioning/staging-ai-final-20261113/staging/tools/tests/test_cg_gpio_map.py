"""Tests for the shared GPIO ownership validator (``cg_gpio_map.py``).

The validator is the mechanism that turns "the pins look fine" into a
machine check. A validator that cannot fail is not a check, so every
required negative case from the reconciliation brief is exercised here
with a synthetic pin map:

1. DS18B20 DATA and IBT-2 L_EN both on GPIO10 is rejected.
2. MC-38 and an active MANUAL RS-485 DE/RE both on GPIO35 is rejected.
3. Any duplicate GPIO ownership is rejected.
4. A safe-OFF that omits L_EN is detected.
5. A safe-OFF that writes a logical 1 (unauthorized enable/PWM) is rejected.

Positive cases keep the checks from becoming "always fail": the as-built
AUTO map passes, the octal-PSRAM reservation is profile-conditional, and a
correct three-pin safe-OFF passes.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_gpio_map  # noqa: E402


def config_text(
    *,
    ds18b20=33,
    sda=21,
    scl=34,
    mc38=35,
    tx=36,
    rx=37,
    rpwm=5,
    ren=6,
    len_pin=10,
    octal=0,
    dir_mode=None,
    de_re=None,
    version=2,
):
    lines = [
        f"#define CG_HW_PSRAM_OCTAL {octal}",
        f"#define CG_PIN_DS18B20_DATA {ds18b20}",
        f"#define CG_PIN_BME280_SDA {sda}",
        f"#define CG_PIN_BME280_SCL {scl}",
        f"#define CG_PIN_MC38 {mc38}",
        f"#define CG_PIN_UART_TX_TO_MAX3485_DI {tx}",
        f"#define CG_PIN_UART_RX_FROM_MAX3485_RO {rx}",
        f"#define CG_PIN_IBT2_COOLING_PWM {rpwm}",
        f"#define CG_PIN_IBT2_REN {ren}",
        f"#define CG_PIN_IBT2_LEN {len_pin}",
        f"#define CG_PIN_MAP_VERSION {version}",
    ]
    if dir_mode is not None:
        lines.append(f"#define CG_RS485_DIR_MODE {dir_mode}")
    if de_re is not None:
        lines.append(f"#define CG_PIN_MAX3485_DE_RE {de_re}")
    return "\n".join(lines) + "\n"


SAFE_OFF_OK = """
void cg_actuator_force_off(void)
{
    (void)gpio_set_level(CG_PIN_IBT2_REN, 0);
    (void)gpio_set_level(CG_PIN_IBT2_LEN, 0);
    (void)gpio_set_level(CG_PIN_IBT2_COOLING_PWM, 0);
}
"""


def _has(problems, needle):
    return any(needle in problem for problem in problems)


class NegativePinMapTests(unittest.TestCase):
    def test_ds18b20_and_len_on_gpio10_are_rejected(self) -> None:
        gpio = cg_gpio_map.evaluate(config_text(ds18b20=10, len_pin=10))
        problems = cg_gpio_map.conflicts(gpio)
        self.assertTrue(_has(problems, "DS18B20 DATA and IBT-2 L_EN"), problems)
        self.assertTrue(_has(problems, "multiple functions"), problems)

    def test_manual_de_re_colliding_with_mc38_is_rejected(self) -> None:
        gpio = cg_gpio_map.evaluate(
            config_text(mc38=35, dir_mode=cg_gpio_map.RS485_DIR_MANUAL, de_re=35)
        )
        problems = cg_gpio_map.conflicts(gpio)
        self.assertTrue(_has(problems, "collides with MC38"), problems)

    def test_duplicate_ownership_is_rejected(self) -> None:
        gpio = cg_gpio_map.evaluate(config_text(scl=34, mc38=34))
        problems = cg_gpio_map.conflicts(gpio)
        self.assertTrue(_has(problems, "multiple functions"), problems)

    def test_flash_and_strapping_pins_are_rejected(self) -> None:
        flash = cg_gpio_map.conflicts(cg_gpio_map.evaluate(config_text(tx=27)))
        self.assertTrue(_has(flash, "flash bus"), flash)
        strap = cg_gpio_map.conflicts(cg_gpio_map.evaluate(config_text(mc38=45)))
        self.assertTrue(_has(strap, "strapping pin"), strap)

    def test_octal_psram_reservation_is_enforced_only_on_that_profile(self) -> None:
        quad = cg_gpio_map.conflicts(cg_gpio_map.evaluate(config_text(octal=0)))
        self.assertFalse(_has(quad, "Octal"), quad)
        octal = cg_gpio_map.conflicts(cg_gpio_map.evaluate(config_text(octal=1)))
        self.assertTrue(_has(octal, "Octal-PSRAM"), octal)

    def test_manual_mode_without_de_re_pin_is_rejected(self) -> None:
        gpio = cg_gpio_map.evaluate(
            config_text(dir_mode=cg_gpio_map.RS485_DIR_MANUAL, de_re=None)
        )
        problems = cg_gpio_map.conflicts(gpio)
        self.assertTrue(_has(problems, "needs CG_PIN_MAX3485_DE_RE"), problems)


class PositivePinMapTests(unittest.TestCase):
    def test_as_built_auto_map_is_accepted(self) -> None:
        gpio = cg_gpio_map.evaluate(
            config_text(dir_mode=cg_gpio_map.RS485_DIR_AUTO)
        )
        self.assertEqual(cg_gpio_map.conflicts(gpio), [])
        self.assertEqual(cg_gpio_map.as_built_mismatches(gpio), [])

    def test_drift_from_as_built_is_reported(self) -> None:
        gpio = cg_gpio_map.evaluate(config_text(ds18b20=10))
        self.assertTrue(_has(cg_gpio_map.as_built_mismatches(gpio), "DS18B20_DATA"))
        self.assertTrue(_has(cg_gpio_map.as_built_mismatches(gpio), "as-built"))

    def test_manual_map_is_accepted_when_de_re_is_free(self) -> None:
        gpio = cg_gpio_map.evaluate(
            config_text(dir_mode=cg_gpio_map.RS485_DIR_MANUAL, de_re=4)
        )
        self.assertEqual(cg_gpio_map.conflicts(gpio), [])


class SafeOffTests(unittest.TestCase):
    signature = r"void\s+cg_actuator_force_off\s*\([^)]*\)"

    def _problems(self, source):
        return cg_gpio_map.safe_off_problems(
            source,
            rpwm="CG_PIN_IBT2_COOLING_PWM",
            ren="CG_PIN_IBT2_REN",
            len_pin="CG_PIN_IBT2_LEN",
            signature=self.signature,
        )

    def test_three_pin_safe_off_passes(self) -> None:
        self.assertEqual(self._problems(SAFE_OFF_OK), [])

    def test_omitting_len_is_detected(self) -> None:
        broken = SAFE_OFF_OK.replace("    (void)gpio_set_level(CG_PIN_IBT2_LEN, 0);\n", "")
        problems = self._problems(broken)
        self.assertTrue(_has(problems, "CG_PIN_IBT2_LEN"), problems)

    def test_omitting_len_from_mask_is_detected(self) -> None:
        source = """
void cg_actuator_force_off(void)
{
    gpio_config_t cfg = {
        .pin_bit_mask = (1ULL << 5) | (1ULL << 6),
    };
    (void)gpio_set_level(CG_PIN_IBT2_REN, 0);
    (void)gpio_set_level(CG_PIN_IBT2_COOLING_PWM, 0);
}
"""
        self.assertTrue(_has(self._problems(source), "CG_PIN_IBT2_LEN"))

    def test_writing_a_one_is_rejected(self) -> None:
        source = SAFE_OFF_OK.replace(
            "(void)gpio_set_level(CG_PIN_IBT2_COOLING_PWM, 0);",
            "(void)gpio_set_level(CG_PIN_IBT2_COOLING_PWM, 1);",
        )
        problems = self._problems(source)
        self.assertTrue(_has(problems, "logical 1"), problems)
        self.assertTrue(_has(problems, "never writes CG_PIN_IBT2_COOLING_PWM=0"), problems)

    def test_clearing_rpwm_before_enables_is_rejected(self) -> None:
        source = SAFE_OFF_OK.replace(
            "    (void)gpio_set_level(CG_PIN_IBT2_REN, 0);\n"
            "    (void)gpio_set_level(CG_PIN_IBT2_LEN, 0);\n"
            "    (void)gpio_set_level(CG_PIN_IBT2_COOLING_PWM, 0);\n",
            "    (void)gpio_set_level(CG_PIN_IBT2_COOLING_PWM, 0);\n"
            "    (void)gpio_set_level(CG_PIN_IBT2_REN, 0);\n"
            "    (void)gpio_set_level(CG_PIN_IBT2_LEN, 0);\n",
        )
        self.assertTrue(_has(self._problems(source), "before RPWM"))


class DirectionTests(unittest.TestCase):
    def test_missing_input_config_is_reported(self) -> None:
        problems = cg_gpio_map.direction_problems(
            {"cg_door.c": "void f(void){ }", "cg_onewire.c": ""}
        )
        self.assertTrue(_has(problems, "cg_door.c"), problems)
        self.assertTrue(_has(problems, "open-drain"), problems)

    def test_as_built_drivers_pass(self) -> None:
        door = "gpio_config(&cfg); cfg.mode = GPIO_MODE_INPUT; CG_PIN_MC38;"
        onewire = "cfg.mode = GPIO_MODE_INPUT_OUTPUT_OD;"
        self.assertEqual(
            cg_gpio_map.direction_problems({"cg_door.c": door, "cg_onewire.c": onewire}),
            [],
        )

    def test_foreign_module_touching_owned_pins_is_reported(self) -> None:
        problems = cg_gpio_map.direction_problems(
            {
                "cg_door.c": "gpio_config(&cfg); GPIO_MODE_INPUT; CG_PIN_MC38;",
                "cg_onewire.c": "GPIO_MODE_INPUT_OUTPUT_OD;",
                "cg_power.c": "gpio_set_level(CG_PIN_IBT2_LEN, 0);",
            }
        )
        self.assertTrue(_has(problems, "cg_power.c"), problems)


if __name__ == "__main__":
    unittest.main()
