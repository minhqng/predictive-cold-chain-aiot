"""Unit tests for ColdGuard Member A — W18 Controller B Enablement Tool."""

import math
import unittest

from cg_w18_enablement_audit import (
    PROVISIONAL_MAX_CURRENT_A,
    PROVISIONAL_MAX_HOT_SIDE_TEMP_C,
    MAX_COMMUNICATION_TIMEOUT_MS,
    check_abort_criteria,
    evaluate_pre_run_safety_audit,
)


class TestW18EnablementAudit(unittest.TestCase):

    def test_pre_run_safety_audit_all_clean_including_prereqs(self):
        checks = {
            "fuse_verified": True,
            "fan_operational": True,
            "terminals_secured": True,
            "sensors_online": True,
            "pzem_responsive": True,
            "output_stage_default_off": True,
            "g4_gate_passed": True,
            "controller_b_model_frozen": True,
            "controller_d_policy_frozen": True,
        }
        res = evaluate_pre_run_safety_audit(checks)
        self.assertTrue(res.is_ready_for_dry_run)
        self.assertTrue(res.is_ready_for_physical_enablement)
        self.assertEqual(res.unresolved_items, [])

    def test_pre_run_safety_audit_bench_ok_but_prereqs_pending(self):
        checks = {
            "fuse_verified": True,
            "fan_operational": True,
            "terminals_secured": True,
            "sensors_online": True,
            "pzem_responsive": True,
            "output_stage_default_off": True,
            "g4_gate_passed": False,
            "controller_b_model_frozen": False,
            "controller_d_policy_frozen": False,
        }
        res = evaluate_pre_run_safety_audit(checks)
        self.assertTrue(res.is_ready_for_dry_run)
        self.assertFalse(res.is_ready_for_physical_enablement)
        self.assertIn("g4_gate_passed", res.unresolved_items)
        self.assertIn("controller_b_model_frozen", res.unresolved_items)
        self.assertIn("controller_d_policy_frozen", res.unresolved_items)

    def test_pre_run_safety_audit_missing_bench_items(self):
        checks = {
            "fuse_verified": False,
            "fan_operational": True,
            "terminals_secured": True,
            "sensors_online": True,
            "pzem_responsive": False,
            "output_stage_default_off": True,
            "g4_gate_passed": True,
            "controller_b_model_frozen": True,
            "controller_d_policy_frozen": True,
        }
        res = evaluate_pre_run_safety_audit(checks)
        self.assertFalse(res.is_ready_for_dry_run)
        self.assertFalse(res.is_ready_for_physical_enablement)
        self.assertIn("fuse_verified", res.unresolved_items)
        self.assertIn("pzem_responsive", res.unresolved_items)

    def test_check_abort_criteria_normal(self):
        aborted, reason, enf = check_abort_criteria(current_a=4.5, hot_side_temp_c=35.0, last_comm_gap_ms=1000)
        self.assertFalse(aborted)
        self.assertIsNone(reason)
        self.assertEqual(enf, "HOST_TRIP_RECOMMENDATION")

    def test_check_abort_criteria_overcurrent(self):
        aborted, reason, enf = check_abort_criteria(current_a=10.5, hot_side_temp_c=35.0, last_comm_gap_ms=1000)
        self.assertTrue(aborted)
        self.assertIn("OVERCURRENT_TRIP", reason)
        self.assertEqual(enf, "HOST_TRIP_RECOMMENDATION")

    def test_check_abort_criteria_overtemp_55c(self):
        aborted, reason, enf = check_abort_criteria(current_a=4.5, hot_side_temp_c=56.0, last_comm_gap_ms=1000)
        self.assertTrue(aborted)
        self.assertIn("OVERTEMP_TRIP", reason)
        self.assertIn("provisional 55.0A", reason.replace("C", "A"))  # checks threshold mention

    def test_check_abort_criteria_timeout(self):
        aborted, reason, enf = check_abort_criteria(current_a=4.5, hot_side_temp_c=35.0, last_comm_gap_ms=3500)
        self.assertTrue(aborted)
        self.assertIn("TIMEOUT_TRIP", reason)

    # Negative regression tests for audit defects:
    def test_negative_nan_current(self):
        aborted, reason, _ = check_abort_criteria(current_a=float("nan"), hot_side_temp_c=35.0, last_comm_gap_ms=1000)
        self.assertTrue(aborted)
        self.assertIn("INVALID_MEASUREMENT", reason)

    def test_negative_none_current(self):
        aborted, reason, _ = check_abort_criteria(current_a=None, hot_side_temp_c=35.0, last_comm_gap_ms=1000)
        self.assertTrue(aborted)
        self.assertIn("INVALID_MEASUREMENT", reason)

    def test_negative_negative_current(self):
        aborted, reason, _ = check_abort_criteria(current_a=-0.5, hot_side_temp_c=35.0, last_comm_gap_ms=1000)
        self.assertTrue(aborted)
        self.assertIn("INVALID_MEASUREMENT", reason)

    def test_negative_nan_temperature(self):
        aborted, reason, _ = check_abort_criteria(current_a=4.5, hot_side_temp_c=float("nan"), last_comm_gap_ms=1000)
        self.assertTrue(aborted)
        self.assertIn("INVALID_MEASUREMENT", reason)

    def test_negative_none_temperature(self):
        aborted, reason, _ = check_abort_criteria(current_a=4.5, hot_side_temp_c=None, last_comm_gap_ms=1000)
        self.assertTrue(aborted)
        self.assertIn("INVALID_MEASUREMENT", reason)

    def test_negative_out_of_range_temperature(self):
        aborted, reason, _ = check_abort_criteria(current_a=4.5, hot_side_temp_c=-50.0, last_comm_gap_ms=1000)
        self.assertTrue(aborted)
        self.assertIn("INVALID_MEASUREMENT", reason)

    def test_negative_negative_comm_gap(self):
        aborted, reason, _ = check_abort_criteria(current_a=4.5, hot_side_temp_c=35.0, last_comm_gap_ms=-10)
        self.assertTrue(aborted)
        self.assertIn("INVALID_MEASUREMENT", reason)


if __name__ == "__main__":
    unittest.main()
