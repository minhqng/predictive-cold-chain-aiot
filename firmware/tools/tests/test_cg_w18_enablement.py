"""Unit tests for ColdGuard Member A — W18 Controller B Enablement Tool."""

import unittest

from cg_w18_enablement_audit import (
    MAX_ALLOWED_CURRENT_A,
    MAX_ALLOWED_HOT_SIDE_TEMP_C,
    check_abort_criteria,
    evaluate_pre_run_safety_audit,
)


class TestW18EnablementAudit(unittest.TestCase):

    def test_pre_run_safety_audit_all_clean(self):
        checks = {
            "fuse_verified": True,
            "fan_operational": True,
            "terminals_secured": True,
            "sensors_online": True,
            "pzem_responsive": True,
            "output_stage_default_off": True,
        }
        res = evaluate_pre_run_safety_audit(checks)
        self.assertTrue(res.is_ready_for_dry_run)
        self.assertEqual(res.unresolved_items, [])

    def test_pre_run_safety_audit_missing_items(self):
        checks = {
            "fuse_verified": False,
            "fan_operational": True,
            "terminals_secured": True,
            "sensors_online": True,
            "pzem_responsive": False,
            "output_stage_default_off": True,
        }
        res = evaluate_pre_run_safety_audit(checks)
        self.assertFalse(res.is_ready_for_dry_run)
        self.assertIn("fuse_verified", res.unresolved_items)
        self.assertIn("pzem_responsive", res.unresolved_items)

    def test_check_abort_criteria_normal(self):
        aborted, reason = check_abort_criteria(current_a=4.5, hot_side_temp_c=35.0, last_comm_gap_ms=1000)
        self.assertFalse(aborted)
        self.assertIsNone(reason)

    def test_check_abort_criteria_overcurrent(self):
        aborted, reason = check_abort_criteria(current_a=8.5, hot_side_temp_c=35.0, last_comm_gap_ms=1000)
        self.assertTrue(aborted)
        self.assertIn("OVERCURRENT_TRIP", reason)

    def test_check_abort_criteria_overtemp(self):
        aborted, reason = check_abort_criteria(current_a=4.5, hot_side_temp_c=70.0, last_comm_gap_ms=1000)
        self.assertTrue(aborted)
        self.assertIn("OVERTEMP_TRIP", reason)

    def test_check_abort_criteria_timeout(self):
        aborted, reason = check_abort_criteria(current_a=4.5, hot_side_temp_c=35.0, last_comm_gap_ms=4000)
        self.assertTrue(aborted)
        self.assertIn("TIMEOUT_TRIP", reason)


if __name__ == "__main__":
    unittest.main()
