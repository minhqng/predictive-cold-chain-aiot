"""Unit tests for ColdGuard Member A — W19 Campaign Preparation Tool."""

import unittest

from cg_w19_campaign_prep import (
    CampaignAttemptTracker,
    create_invalid_attempt_record,
    evaluate_pair_matching,
    evaluate_state_based_thermal_reset,
    validate_run_preparation,
)


class TestW19CampaignPrep(unittest.TestCase):

    def test_validate_run_preparation_clean(self):
        res = validate_run_preparation(
            config_matches=True,
            door_closed=True,
            pzem_valid=True,
            storage_ready=True,
            controller_identified=True,
        )
        self.assertTrue(res.ready)
        self.assertEqual(res.reasons, [])

    def test_validate_run_preparation_failures(self):
        res = validate_run_preparation(
            config_matches=False,
            door_closed=False,
            pzem_valid=True,
            storage_ready=True,
            controller_identified=True,
        )
        self.assertFalse(res.ready)
        self.assertIn("HARDWARE_CONFIG_MISMATCH", res.reasons)
        self.assertIn("DOOR_AJAR_AT_START", res.reasons)

    def test_evaluate_state_based_thermal_reset_success(self):
        res = evaluate_state_based_thermal_reset(
            current_tmean_c=25.2,
            band_min_c=24.5,
            band_max_c=25.5,
            gradient_c_per_min=0.02,
            max_gradient_c_per_min=0.05,
            door_closed=True,
            cooling_state_known=True,
            sensor_quality_ok=True,
        )
        self.assertTrue(res.is_reset)
        self.assertEqual(res.tmean_diff, 0.0)
        self.assertEqual(res.reasons, [])

    def test_evaluate_state_based_thermal_reset_gradient_failure(self):
        # Temp in band, but gradient exceeded
        res = evaluate_state_based_thermal_reset(
            current_tmean_c=25.0,
            band_min_c=24.5,
            band_max_c=25.5,
            gradient_c_per_min=0.15,
            max_gradient_c_per_min=0.05,
            door_closed=True,
            cooling_state_known=True,
            sensor_quality_ok=True,
        )
        self.assertFalse(res.is_reset)
        self.assertFalse(res.gradient_ok)
        self.assertTrue(any("INITIAL_GRADIENT_EXCEEDED" in r for r in res.reasons))

    def test_evaluate_state_based_thermal_reset_door_ajar(self):
        res = evaluate_state_based_thermal_reset(
            current_tmean_c=25.0,
            band_min_c=24.5,
            band_max_c=25.5,
            gradient_c_per_min=0.01,
            max_gradient_c_per_min=0.05,
            door_closed=False,
            cooling_state_known=True,
            sensor_quality_ok=True,
        )
        self.assertFalse(res.is_reset)
        self.assertIn("DOOR_AJAR_AT_START", res.reasons)

    def test_evaluate_pair_matching_valid(self):
        res = evaluate_pair_matching(
            pair_id="PAIR-01",
            run_a_id="RUN-A-01",
            run_b_id="RUN-B-01",
            run_a_scenario="SCENARIO_DOOR_30S",
            run_b_scenario="SCENARIO_DOOR_30S",
            run_a_hardware_config="BENCH_HW_V2",
            run_b_hardware_config="BENCH_HW_V2",
            run_a_disturbance_s=30,
            run_b_disturbance_s=30,
            run_a_initial_tmean_c=25.1,
            run_b_initial_tmean_c=25.3,
            run_a_initial_gradient=0.02,
            run_b_initial_gradient=0.03,
            delta_tmean_max_c=0.4,
            delta_gradient_max=0.05,
            run_a_ambient_c=26.0,
            run_b_ambient_c=26.2,
        )
        self.assertTrue(res.is_valid_match)
        self.assertEqual(res.discrepancies, [])

    def test_evaluate_pair_matching_scenario_mismatch(self):
        res = evaluate_pair_matching(
            pair_id="PAIR-02",
            run_a_id="RUN-A-02",
            run_b_id="RUN-B-02",
            run_a_scenario="SCENARIO_DOOR_30S",
            run_b_scenario="SCENARIO_DOOR_60S",
            run_a_hardware_config="BENCH_HW_V2",
            run_b_hardware_config="BENCH_HW_V2",
            run_a_disturbance_s=30,
            run_b_disturbance_s=60,
            run_a_initial_tmean_c=25.1,
            run_b_initial_tmean_c=25.2,
            run_a_initial_gradient=0.02,
            run_b_initial_gradient=0.02,
            delta_tmean_max_c=0.4,
            delta_gradient_max=0.05,
            run_a_ambient_c=26.0,
            run_b_ambient_c=26.0,
        )
        self.assertFalse(res.is_valid_match)
        self.assertTrue(any("SCENARIO_MISMATCH" in d for d in res.discrepancies))

    def test_evaluate_pair_matching_ambient_missing(self):
        res = evaluate_pair_matching(
            pair_id="PAIR-03",
            run_a_id="RUN-A-03",
            run_b_id="RUN-B-03",
            run_a_scenario="SCENARIO_DOOR_30S",
            run_b_scenario="SCENARIO_DOOR_30S",
            run_a_hardware_config="BENCH_HW_V2",
            run_b_hardware_config="BENCH_HW_V2",
            run_a_disturbance_s=30,
            run_b_disturbance_s=30,
            run_a_initial_tmean_c=25.1,
            run_b_initial_tmean_c=25.2,
            run_a_initial_gradient=0.02,
            run_b_initial_gradient=0.02,
            delta_tmean_max_c=0.4,
            delta_gradient_max=0.05,
            run_a_ambient_c=26.0,
            run_b_ambient_c=None,
        )
        self.assertFalse(res.is_valid_match)
        self.assertTrue(any("AMBIENT_NOT_RECORDED" in d for d in res.discrepancies))

    def test_attempt_tracker_preserves_all_attempts(self):
        tracker = CampaignAttemptTracker()
        tracker.record_attempt(
            session_id="SESS-01",
            run_id="RUN-01",
            pair_id="PAIR-01",
            controller="CONTROLLER_A",
            is_valid_attempt=False,
            invalidation_reason="DOOR_AJAR_AT_START",
        )
        tracker.record_attempt(
            session_id="SESS-01",
            run_id="RUN-02",
            pair_id="PAIR-01",
            controller="CONTROLLER_A",
            is_valid_attempt=True,
        )
        self.assertEqual(tracker.total_attempts(), 2)
        self.assertEqual(tracker.invalid_attempts(), 1)
        self.assertEqual(tracker.valid_attempts(), 1)
        self.assertEqual(tracker.attempts[0].attempt_seq, 1)
        self.assertEqual(tracker.attempts[1].attempt_seq, 2)


if __name__ == "__main__":
    unittest.main()
