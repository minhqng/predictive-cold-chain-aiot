"""Unit tests for ColdGuard Member A — W20 Campaign Freeze Tool."""

import tempfile
from pathlib import Path
import unittest

from cg_w20_campaign_freeze import (
    audit_post_campaign_hardware,
    build_frozen_manifest,
    verify_campaign_pair_balance,
    verify_dataset_file_integrity,
)


class TestW20CampaignFreeze(unittest.TestCase):

    def test_verify_campaign_pair_balance_clean(self):
        runs = [
            {"run_id": "r1", "pair_id": "P01", "controller": "CONTROLLER_A", "valid_for_analysis": True},
            {"run_id": "r2", "pair_id": "P01", "controller": "CONTROLLER_B", "valid_for_analysis": True},
            {"run_id": "r3", "pair_id": "P02", "controller": "CONTROLLER_A", "valid_for_analysis": False},
        ]
        bal = verify_campaign_pair_balance(runs, target_pairs=1)
        self.assertTrue(bal.is_balanced)
        self.assertTrue(bal.quota_met)
        self.assertEqual(bal.completed_pairs, 1)
        self.assertEqual(bal.matched_pairs, ["P01"])
        self.assertEqual(bal.invalid_runs_count, 1)
        self.assertEqual(bal.unmatched_a_runs, [])
        self.assertEqual(bal.unmatched_b_runs, [])

    def test_verify_campaign_pair_balance_unmatched_equal_counts(self):
        # Equal A and B counts (1 each), but different pair_ids!
        runs = [
            {"run_id": "r1", "pair_id": "P01", "controller": "CONTROLLER_A", "valid_for_analysis": True},
            {"run_id": "r2", "pair_id": "P02", "controller": "CONTROLLER_B", "valid_for_analysis": True},
        ]
        bal = verify_campaign_pair_balance(runs, target_pairs=1)
        self.assertFalse(bal.is_balanced)
        self.assertFalse(bal.quota_met)
        self.assertEqual(bal.completed_pairs, 0)
        self.assertIn("P01:r1", bal.unmatched_a_runs)
        self.assertIn("P02:r2", bal.unmatched_b_runs)

    def test_verify_campaign_pair_balance_quota_not_met(self):
        runs = [
            {"run_id": "r1", "pair_id": "P01", "controller": "CONTROLLER_A", "valid_for_analysis": True},
            {"run_id": "r2", "pair_id": "P01", "controller": "CONTROLLER_B", "valid_for_analysis": True},
        ]
        bal = verify_campaign_pair_balance(runs, target_pairs=2)
        self.assertTrue(bal.is_balanced)
        self.assertFalse(bal.quota_met)
        self.assertEqual(bal.completed_pairs, 1)

    def test_verify_campaign_pair_balance_invalid_controller(self):
        runs = [
            {"run_id": "r1", "pair_id": "P01", "controller": "CONTROLLER_UNKNOWN", "valid_for_analysis": True},
        ]
        bal = verify_campaign_pair_balance(runs, target_pairs=1)
        self.assertFalse(bal.is_balanced)
        self.assertTrue(any("INVALID_CONTROLLER" in e for e in bal.validation_errors))

    def test_audit_post_campaign_hardware_clean(self):
        roms = ["287088CA00000051", "28AEBF2200000006", "28CBE9CA00000072", "283BE5C9000000A9"]
        ok, defects = audit_post_campaign_hardware(roms, roms, terminal_tightness_ok=True, fan_ok=True)
        self.assertTrue(ok)
        self.assertEqual(defects, [])

    def test_audit_post_campaign_hardware_defects(self):
        roms_exp = ["287088CA00000051", "28AEBF2200000006"]
        roms_obs = ["287088CA00000051"]
        ok, defects = audit_post_campaign_hardware(roms_exp, roms_obs, terminal_tightness_ok=False, fan_ok=True)
        self.assertFalse(ok)
        self.assertIn("SENSOR_ROM_MISMATCH_OR_DROP", defects)
        self.assertIn("TERMINAL_LOOSE", defects)

    def test_build_frozen_manifest(self):
        m = build_frozen_manifest(
            campaign_id="CAMP-2026-11",
            target_pairs=5,
            completed_pairs=5,
            dataset_hashes={"run1.csv": "abc123hash"},
            hardware_unchanged=True,
            exceptions=["MINOR_AMBIENT_VARIATION"],
            invalid_attempts=2,
        )
        self.assertEqual(m["manifest_version"], "1.1")
        self.assertEqual(m["canonical_payload"]["campaign_id"], "CAMP-2026-11")
        self.assertIn("manifest_digest_sha256", m)
        # Verify operator signature separation
        self.assertEqual(m["operator_signature"]["status"], "PENDING_OPERATOR_PHYSICAL_SIGNATURE")
        self.assertFalse(m["operator_signature"]["signed"])

    def test_verify_dataset_file_integrity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            f = base / "sample.csv"
            f.write_text("hello,world\n", encoding="utf-8")
            import hashlib
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            ok, errs = verify_dataset_file_integrity({"sample.csv": h}, base_dir=base)
            self.assertTrue(ok)
            self.assertEqual(errs, [])

            # Test mismatch
            ok, errs = verify_dataset_file_integrity({"sample.csv": "wronghash"}, base_dir=base)
            self.assertFalse(ok)
            self.assertTrue(any("HASH_MISMATCH" in e for e in errs))

            # Test missing file
            ok, errs = verify_dataset_file_integrity({"missing.csv": h}, base_dir=base)
            self.assertFalse(ok)
            self.assertTrue(any("MISSING_FILE" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
