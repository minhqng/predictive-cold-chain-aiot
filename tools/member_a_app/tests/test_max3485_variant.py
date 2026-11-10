"""A-W03-02 RS-485 supply acceptance: frozen vs owner-approved 5 V variant.

The frozen BOM part (MAX3485) is a 3.3 V module; its module-VCC gate must stay
3.2..3.4 V. The as-built TTL485-V2.0 is a 5 V module whose substitution was
approved by the project owner (CR-A-W01-01, 2026-11-09; evidence/A/W01/
freeze-deviation-review.md). The approved variant must NOT relax the ESP32 input
safety: the RX logic level behind the divider is validated separately
(2.475..3.4 V), approval provenance is required, a missing level measurement
blocks, and a direct 5 V rail to a GPIO is forbidden.

These tests drive handler_max3485 directly and assert the named checks, so they
discriminate the safe from the unsafe path rather than trusting a single PASS.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from .helpers import TOOLS  # noqa: F401  (ensures member_a_app importable)

from member_a_app import evaluators
from member_a_app.evidence import SessionStore
from member_a_app.model import TestBlocked
from member_a_app.requirements import get
from member_a_app.runner import AutoOperator, TestContext

handler_max3485 = evaluators.HANDLERS["max3485"]

FROZEN = "MAX3485 3.3 V (frozen BOM)"
APPROVED = "TTL485-V2.0 5 V (W01 approved substitution)"
ITEM_CONFIRMS = [True] * 6  # DI / RO / DE / /RE / A / B mapped


def _checks(ctx: TestContext) -> dict[str, bool]:
    return {check.name: check.passed for check in ctx.checks}


class Max3485VariantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.store = SessionStore(self.root / "session", operator="tester")
        self.photo = self.root / "rs485-module.jpg"
        self.photo.write_bytes(b"\xff\xd8\xff\xe0placeholder-jpeg")

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def _run(self, answers: dict[str, list]) -> TestContext:
        operator = AutoOperator(answers)
        ctx = TestContext(get("A-W03-02"), self.store, None, operator, {})
        handler_max3485(ctx)
        return ctx

    def test_frozen_max3485_path_still_requires_3v3(self) -> None:
        ctx = self._run({"choose": [FROZEN], "number": [3.3],
                         "confirm": list(ITEM_CONFIRMS), "file": [str(self.photo)]})
        checks = _checks(ctx)
        self.assertEqual(ctx.measurements["variant"], "MAX3485_3V3_FROZEN")
        self.assertTrue(checks["vcc_3v3"])
        self.assertNotIn("vcc_5v_module_supply", checks)
        self.assertNotIn("esp32_gpio_input_level", checks)

    def test_frozen_path_rejects_a_5v_supply(self) -> None:
        # The frozen 3.3 V gate must NOT have been widened to accept 5 V.
        ctx = self._run({"choose": [FROZEN], "number": [5.0],
                         "confirm": list(ITEM_CONFIRMS), "file": [str(self.photo)]})
        self.assertFalse(_checks(ctx)["vcc_3v3"])

    def test_approved_5v_variant_passes_with_safe_gpio_level(self) -> None:
        ctx = self._run({"choose": [APPROVED], "number": [5.0, 3.314],
                         "confirm": [True, True] + ITEM_CONFIRMS,
                         "file": [str(self.photo)]})
        checks = _checks(ctx)
        self.assertEqual(ctx.measurements["variant"], "TTL485_V2_0_5V_OWNER_APPROVED")
        self.assertTrue(checks["vcc_5v_module_supply"])
        self.assertTrue(checks["approved_substitution_provenance"])
        self.assertTrue(checks["esp32_gpio_input_level"])
        self.assertTrue(checks["no_direct_5v_to_gpio"])
        self.assertEqual(ctx.measurements["gpio_input_level_v"], 3.314)

    def test_5v_variant_rejects_unrecorded_approval(self) -> None:
        ctx = self._run({"choose": [APPROVED], "number": [5.0, 3.314],
                         "confirm": [False, True] + ITEM_CONFIRMS,
                         "file": [str(self.photo)]})
        self.assertFalse(_checks(ctx)["approved_substitution_provenance"])

    def test_5v_variant_rejects_gpio_at_5v_direct_level(self) -> None:
        # A 5 V logic level at the ESP32 RX pin exceeds the 3.4 V ceiling.
        ctx = self._run({"choose": [APPROVED], "number": [5.0, 5.0],
                         "confirm": [True, True] + ITEM_CONFIRMS,
                         "file": [str(self.photo)]})
        self.assertFalse(_checks(ctx)["esp32_gpio_input_level"])

    def test_5v_variant_rejects_gpio_below_vih(self) -> None:
        # Below VIH = 0.75 x 3.3 V = 2.475 V the input is not a valid HIGH.
        ctx = self._run({"choose": [APPROVED], "number": [5.0, 2.0],
                         "confirm": [True, True] + ITEM_CONFIRMS,
                         "file": [str(self.photo)]})
        self.assertFalse(_checks(ctx)["esp32_gpio_input_level"])

    def test_5v_variant_rejects_direct_5v_to_gpio(self) -> None:
        ctx = self._run({"choose": [APPROVED], "number": [5.0, 3.314],
                         "confirm": [True, False] + ITEM_CONFIRMS,
                         "file": [str(self.photo)]})
        self.assertFalse(_checks(ctx)["no_direct_5v_to_gpio"])

    def test_5v_variant_rejects_out_of_range_module_supply(self) -> None:
        ctx = self._run({"choose": [APPROVED], "number": [3.3, 3.314],
                         "confirm": [True, True] + ITEM_CONFIRMS,
                         "file": [str(self.photo)]})
        self.assertFalse(_checks(ctx)["vcc_5v_module_supply"])

    def test_5v_variant_blocks_when_gpio_measurement_missing(self) -> None:
        operator = AutoOperator({"choose": [APPROVED], "number": [5.0, None],
                                 "confirm": [True, True] + ITEM_CONFIRMS,
                                 "file": [str(self.photo)]})
        ctx = TestContext(get("A-W03-02"), self.store, None, operator, {})
        with self.assertRaises(TestBlocked) as caught:
            handler_max3485(ctx)
        self.assertIn("GPIO_LEVEL_MEASUREMENT_MISSING", str(caught.exception))

    def _approved(self, vcc: float, gpio: float) -> dict[str, bool]:
        ctx = self._run({"choose": [APPROVED], "number": [vcc, gpio],
                         "confirm": [True, True] + ITEM_CONFIRMS,
                         "file": [str(self.photo)]})
        return _checks(ctx)

    def test_gpio_bounds_are_inclusive(self) -> None:
        # check_closed is inclusive: exactly the VIH floor and logic ceiling pass,
        # one millivolt outside either bound fails.
        self.assertTrue(self._approved(5.0, 2.475)["esp32_gpio_input_level"])
        self.assertTrue(self._approved(5.0, 3.4)["esp32_gpio_input_level"])
        self.assertFalse(self._approved(5.0, 2.474)["esp32_gpio_input_level"])
        self.assertFalse(self._approved(5.0, 3.401)["esp32_gpio_input_level"])

    def test_module_supply_bounds_are_inclusive(self) -> None:
        self.assertTrue(self._approved(4.5, 3.3)["vcc_5v_module_supply"])
        self.assertTrue(self._approved(5.5, 3.3)["vcc_5v_module_supply"])
        self.assertFalse(self._approved(4.499, 3.3)["vcc_5v_module_supply"])
        self.assertFalse(self._approved(5.501, 3.3)["vcc_5v_module_supply"])

    def test_frozen_vcc_bounds_are_inclusive(self) -> None:
        for vcc, expected in ((3.2, True), (3.4, True), (3.199, False), (3.401, False)):
            ctx = self._run({"choose": [FROZEN], "number": [vcc],
                             "confirm": list(ITEM_CONFIRMS), "file": [str(self.photo)]})
            self.assertEqual(_checks(ctx)["vcc_3v3"], expected, f"vcc={vcc}")


if __name__ == "__main__":
    unittest.main()