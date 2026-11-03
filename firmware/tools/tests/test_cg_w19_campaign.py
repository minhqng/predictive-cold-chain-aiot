"""Unit tests for ColdGuard Member A — W19 Campaign Preparation Tool."""

import unittest

from cg_w19_campaign_prep import (
    create_invalid_attempt_record,
    evaluate_thermal_reset,
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

    def test_evaluate_thermal_reset_success(self):
        reset, diff = evaluate_thermal_reset(current_temp_c=25.2, target_equilibrium_c=25.0, band_c=0.5)
        self.assertTrue(reset)
        self.assertEqual(diff, 0.2)

    def test_evaluate_thermal_reset_not_ready(self):
        reset, diff = evaluate_thermal_reset(current_temp_c=26.0, target_equilibrium_c=25.0, band_c=0.5)
        self.assertFalse(reset)
        self.assertEqual(diff, 1.0)

    def test_create_invalid_attempt_record(self):
        rec = create_invalid_attempt_record(
            run_id="run-001",
            controller="CONTROLLER_B",
            reason_code="DOOR_AJAR_AT_START",
            details={"door_raw": 1},
        )
        self.assertEqual(rec["run_id"], "run-001")
        self.assertFalse(rec["valid_for_analysis"])
        self.assertEqual(rec["reason_code"], "DOOR_AJAR_AT_START")


if __name__ == "__main__":
    unittest.main()
