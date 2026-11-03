"""Unit tests for ColdGuard Member A — W24 Final Acceptance Tool."""

import unittest

from cg_w24_final_freeze import (
    collate_acceptance_census,
    validate_final_configuration,
)


class TestW24FinalAcceptance(unittest.TestCase):

    def setUp(self):
        self.valid_config = {
            "hardware_config_id": "HW-CONF-2026-11-03",
            "pin_map": {"ONE_WIRE_GPIO": 4, "IBT2_PWM_GPIO": 5},
            "sensor_roms": ["287088CA00000051", "28AEBF2200000006"],
            "sensor_positions": {"T1": "CHAMBER_CENTER", "T2": "HOT_SIDE"},
            "fuse": "10A_BLADE_FUSE",
            "pzem_range": "10A_100V",
            "firmware_version": "v1.0.0-rc1",
        }

    def test_validate_final_configuration_clean(self):
        res = validate_final_configuration(self.valid_config)
        self.assertTrue(res.valid)
        self.assertEqual(res.missing_fields, [])

    def test_validate_final_configuration_missing_keys(self):
        incomplete = dict(self.valid_config)
        del incomplete["fuse"]
        del incomplete["firmware_version"]
        res = validate_final_configuration(incomplete)
        self.assertFalse(res.valid)
        self.assertEqual(res.missing_fields, ["fuse", "firmware_version"])

    def test_collate_acceptance_census_full(self):
        all_weeks = list(range(1, 25))
        census = collate_acceptance_census(
            weeks_delivered=all_weeks,
            physical_runs_count=1,
            hardware_status="FAIL_CLOSED_FROZEN",
        )
        self.assertEqual(census["delivered_week_count"], 24)
        self.assertTrue(census["all_weeks_accounted_for"])
        self.assertTrue(census["handover_ready"])
        self.assertEqual(census["missing_weeks"], [])

    def test_collate_acceptance_census_partial(self):
        partial = list(range(1, 17))  # Missing 17-24
        census = collate_acceptance_census(
            weeks_delivered=partial,
            physical_runs_count=1,
            hardware_status="FAIL_CLOSED_FROZEN",
        )
        self.assertEqual(census["delivered_week_count"], 16)
        self.assertFalse(census["all_weeks_accounted_for"])
        self.assertIn(17, census["missing_weeks"])


if __name__ == "__main__":
    unittest.main()
