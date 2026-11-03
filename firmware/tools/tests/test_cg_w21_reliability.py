"""Unit tests for ColdGuard Member A — W21 Reliability Soak Tool."""

import unittest

from cg_w21_reliability_audit import (
    compute_degraded_chamber_air,
    evaluate_soak_telemetry,
    verify_pzem_fault_behavior,
)


class TestW21ReliabilityAudit(unittest.TestCase):

    def test_evaluate_soak_telemetry_clean(self):
        frames = [
            {"uptime_ms": 0, "t_inside_status": "OK", "current_status": "OK"},
            {"uptime_ms": 3600000, "t_inside_status": "OK", "current_status": "OK"},
            {"uptime_ms": 7200000, "t_inside_status": "OK", "current_status": "OK"},
        ]
        sumry = evaluate_soak_telemetry(frames)
        self.assertEqual(sumry.total_frames, 3)
        self.assertEqual(sumry.duration_hours, 2.0)
        self.assertEqual(sumry.uptime_resets, 0)
        self.assertEqual(sumry.verdict, "PASS")

    def test_evaluate_soak_telemetry_reset_detected(self):
        frames = [
            {"uptime_ms": 1000, "t_inside_status": "OK", "current_status": "OK"},
            {"uptime_ms": 500, "t_inside_status": "OK", "current_status": "OK"},  # Reset!
        ]
        sumry = evaluate_soak_telemetry(frames)
        self.assertEqual(sumry.uptime_resets, 1)
        self.assertEqual(sumry.verdict, "DEGRADED")

    def test_compute_degraded_chamber_air_full(self):
        mean_t, status = compute_degraded_chamber_air(t1_c=4.0, t3_c=5.0, t4_c=6.0, t2_hot_side_c=40.0)
        self.assertEqual(mean_t, 5.0)
        self.assertEqual(status, "FULL_CHAMBER_ARRAY")

    def test_compute_degraded_chamber_air_single_drop(self):
        # T1 dropped, T3 and T4 valid
        mean_t, status = compute_degraded_chamber_air(t1_c=None, t3_c=5.0, t4_c=7.0, t2_hot_side_c=40.0)
        self.assertEqual(mean_t, 6.0)
        self.assertEqual(status, "DEGRADED_CHAMBER_ARRAY")

    def test_compute_degraded_chamber_air_all_failed(self):
        mean_t, status = compute_degraded_chamber_air(t1_c=None, t3_c=None, t4_c=None)
        self.assertIsNone(mean_t)
        self.assertEqual(status, "ALL_CHAMBER_SENSORS_FAILED")

    def test_verify_pzem_fault_behavior_clean(self):
        ok, violations = verify_pzem_fault_behavior(
            pzem_available=False,
            electrical_quality="DEGRADED",
            output_stage_enabled=False,
        )
        self.assertTrue(ok)
        self.assertEqual(violations, [])

    def test_verify_pzem_fault_behavior_safety_violation(self):
        ok, violations = verify_pzem_fault_behavior(
            pzem_available=False,
            electrical_quality="OK",
            output_stage_enabled=True,
        )
        self.assertFalse(ok)
        self.assertIn("ELECTRICAL_QUALITY_NOT_DEGRADED_ON_PZEM_DROP", violations)
        self.assertIn("OUTPUT_STAGE_REMAINED_ENABLED_ON_PZEM_DROP", violations)


if __name__ == "__main__":
    unittest.main()
