"""Unit tests for ColdGuard Member A — W20 Campaign Freeze Tool."""

import unittest

from cg_w20_campaign_freeze import (
    audit_post_campaign_hardware,
    build_frozen_manifest,
    verify_campaign_pair_balance,
)


class TestW20CampaignFreeze(unittest.TestCase):

    def test_verify_campaign_pair_balance_clean(self):
        runs = [
            {"run_id": "r1", "controller": "CONTROLLER_A", "valid_for_analysis": True},
            {"run_id": "r2", "controller": "CONTROLLER_B", "valid_for_analysis": True},
            {"run_id": "r3", "controller": "CONTROLLER_A", "valid_for_analysis": False},
        ]
        bal = verify_campaign_pair_balance(runs)
        self.assertTrue(bal.is_balanced)
        self.assertEqual(bal.valid_a_runs, 1)
        self.assertEqual(bal.valid_b_runs, 1)
        self.assertEqual(bal.invalid_runs_count, 1)

    def test_verify_campaign_pair_balance_unbalanced(self):
        runs = [
            {"run_id": "r1", "controller": "CONTROLLER_A", "valid_for_analysis": True},
            {"run_id": "r2", "controller": "CONTROLLER_A", "valid_for_analysis": True},
        ]
        bal = verify_campaign_pair_balance(runs)
        self.assertFalse(bal.is_balanced)
        self.assertEqual(bal.valid_a_runs, 2)
        self.assertEqual(bal.valid_b_runs, 0)

    def test_audit_post_campaign_hardware_clean(self):
        roms = ["287088CA00000051", "28AEBF2200000006", "28CBE9CA00000072", "283BE5C9000000A9"]
        ok, defects = audit_post_campaign_hardware(roms, roms, terminal_tightness_ok=True, fan_ok=True)
        self.assertTrue(ok)
        self.assertEqual(defects, [])

    def test_audit_post_campaign_hardware_defects(self):
        roms_exp = ["287088CA00000051", "28AEBF2200000006"]
        roms_obs = ["287088CA00000051"]  # Missing 1
        ok, defects = audit_post_campaign_hardware(roms_exp, roms_obs, terminal_tightness_ok=False, fan_ok=True)
        self.assertFalse(ok)
        self.assertIn("SENSOR_ROM_MISMATCH_OR_DROP", defects)
        self.assertIn("TERMINAL_LOOSE", defects)

    def test_build_frozen_manifest(self):
        m = build_frozen_manifest(
            campaign_id="CAMP-2026-11",
            dataset_hashes={"run1.csv": "abc123"},
            hardware_unchanged=True,
            exceptions=[],
            invalid_attempts=2,
        )
        self.assertEqual(m["campaign_id"], "CAMP-2026-11")
        self.assertTrue(m["hardware_unchanged"])
        self.assertEqual(m["invalid_attempts"], 2)
        self.assertIn("manifest_signature", m)


if __name__ == "__main__":
    unittest.main()
