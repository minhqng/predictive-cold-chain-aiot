"""Unit tests for ColdGuard Member A — W22 Rerun Governance Tool."""

import unittest

from cg_w22_rerun_governance import (
    build_physical_limitation_record,
    evaluate_rerun_eligibility,
)


class TestW22Governance(unittest.TestCase):

    def test_evaluate_rerun_eligibility_approved(self):
        ev = evaluate_rerun_eligibility("INVALID_PAIR_UNDER_PREDECLARED_RULE")
        self.assertTrue(ev.approved)
        self.assertIsNone(ev.rejection_reason)

    def test_evaluate_rerun_eligibility_forbidden_tuning(self):
        ev = evaluate_rerun_eligibility("ADJUST_DOOR_TO_IMPROVE_CONTROLLER_B")
        self.assertFalse(ev.approved)
        self.assertIn("FORBIDDEN", ev.rejection_reason)

    def test_evaluate_rerun_eligibility_forbidden_p_hacking(self):
        ev = evaluate_rerun_eligibility("EFFECT_NOT_STATISTICALLY_SIGNIFICANT")
        self.assertFalse(ev.approved)
        self.assertIn("FORBIDDEN", ev.rejection_reason)

    def test_evaluate_rerun_eligibility_unknown(self):
        ev = evaluate_rerun_eligibility("OPERATOR_FEELS_LIKE_ANOTHER_TRY")
        self.assertFalse(ev.approved)
        self.assertIn("UNKNOWN_REASON", ev.rejection_reason)

    def test_build_physical_limitation_record(self):
        rec = build_physical_limitation_record(
            scale="BENCHTOP_SINGLE_CHAMBER",
            units_tested=1,
            tec_uncertainty="V1_UNCHARACTERIZED_SEEBECK_LEAKAGE",
            sensor_limitations=["1WIRE_BUS_CONTENTION", "SLOW_THERMAL_TIME_CONSTANT"],
            ambient_effects="UNREGULATED_ROOM_TEMPERATURE",
            pzem_limits="MODBUS_1S_HOLD_REGISTER_LATENCY",
        )
        self.assertEqual(rec["units_tested"], 1)
        self.assertTrue(rec["is_complete"])
        self.assertEqual(len(rec["sensor_limitations"]), 2)


if __name__ == "__main__":
    unittest.main()
