"""Unit tests for ColdGuard Member A — W17 Shadow Mode Verification Tool."""

import unittest

from cg_w17_shadow_audit import (
    REQUIRED_B_MODEL_CHANNELS,
    audit_shadow_session,
    monitor_plant_anomalies,
    verify_b_model_alignment,
    verify_no_predictive_leak,
)


class TestW17ShadowAudit(unittest.TestCase):

    def setUp(self):
        self.valid_frame = {
            "elapsed_ms": 1000,
            "t_inside_c": 5.0,
            "t_inside_status": "OK",
            "t_cold_side_c": 3.0,
            "t_hot_side_c": 28.0,
            "door_open": False,
            "door_status": "OK",
            "voltage_v": 12.0,
            "current_a": 4.5,
            "power_w": 54.0,
            "quality": "OK",
            "pwm_duty": 800,
        }

    def test_verify_b_model_alignment_success(self):
        missing = verify_b_model_alignment(self.valid_frame)
        self.assertEqual(missing, [])

    def test_verify_b_model_alignment_missing_channel(self):
        incomplete = dict(self.valid_frame)
        del incomplete["door_open"]
        del incomplete["power_w"]
        missing = verify_b_model_alignment(incomplete)
        self.assertEqual(missing, ["door_open", "power_w"])

    def test_verify_no_predictive_leak_clean(self):
        applied = [500, 500, 500]
        shadow = [800, 900, 1000]
        baseline = [500, 500, 500]
        leak, indices = verify_no_predictive_leak(applied, shadow, baseline)
        self.assertFalse(leak)
        self.assertEqual(indices, [])

    def test_verify_no_predictive_leak_detected(self):
        applied = [500, 900, 500]
        shadow = [800, 900, 1000]
        baseline = [500, 500, 500]
        leak, indices = verify_no_predictive_leak(applied, shadow, baseline)
        self.assertTrue(leak)
        self.assertEqual(indices, [1])

    def test_monitor_plant_anomalies_none(self):
        f1 = {"elapsed_ms": 1000, "t_inside_c": 20.0}
        f2 = {"elapsed_ms": 2000, "t_inside_c": 19.9}
        anomalies = monitor_plant_anomalies([f1, f2])
        self.assertEqual(anomalies, [])

    def test_monitor_plant_anomalies_detected(self):
        f1 = {"elapsed_ms": 1000, "t_inside_c": 20.0}
        f2 = {"elapsed_ms": 2000, "t_inside_c": 15.0}  # 5.0 C/s drop >> 0.5 C/s limit
        anomalies = monitor_plant_anomalies([f1, f2])
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["reason"], "CHAMBER_TEMPERATURE_RATE_EXCEEDED")

    def test_audit_shadow_session_pass(self):
        f1 = dict(self.valid_frame, elapsed_ms=1000, t_inside_c=20.0, pwm_duty=500)
        f2 = dict(self.valid_frame, elapsed_ms=2000, t_inside_c=19.9, pwm_duty=500)
        shadow_cmds = [800, 900]
        baseline = [500, 500]
        result = audit_shadow_session([f1, f2], shadow_cmds, baseline)
        self.assertEqual(result.verdict, "PASS")
        self.assertEqual(result.records_evaluated, 2)
        self.assertFalse(result.predictive_leak_detected)

    def test_audit_shadow_session_leak(self):
        f1 = dict(self.valid_frame, elapsed_ms=1000, t_inside_c=20.0, pwm_duty=500)
        f2 = dict(self.valid_frame, elapsed_ms=2000, t_inside_c=19.9, pwm_duty=900)
        shadow_cmds = [800, 900]
        baseline = [500, 500]
        result = audit_shadow_session([f1, f2], shadow_cmds, baseline)
        self.assertEqual(result.verdict, "LEAK_DETECTED")
        self.assertTrue(result.predictive_leak_detected)


if __name__ == "__main__":
    unittest.main()
