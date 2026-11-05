"""Unit tests for ColdGuard Member A — W22 Rerun Governance Tool."""

import unittest

from cg_w22_rerun_governance import (
    build_physical_limitation_record,
    evaluate_rerun_eligibility,
    validate_rerun_log_entry,
)


class TestW22Governance(unittest.TestCase):

    def test_evaluate_rerun_eligibility_valid(self):
        res = evaluate_rerun_eligibility(
            reason="KNOWN_SENSOR_LOG_FAILURE",
            original_attempt_id="RUN-ATTEMPT-001",
            original_attempt_preserved=True,
        )
        self.assertTrue(res.approved)
        self.assertIsNone(res.rejection_reason)

    def test_evaluate_rerun_eligibility_forbidden_cherry_picking(self):
        res = evaluate_rerun_eligibility(
            reason="CHERRY_PICKING_DESIRED_OUTCOME",
            original_attempt_id="RUN-ATTEMPT-001",
            original_attempt_preserved=True,
        )
        self.assertFalse(res.approved)
        self.assertIn("FORBIDDEN", res.rejection_reason)

    def test_evaluate_rerun_eligibility_missing_original_attempt(self):
        res = evaluate_rerun_eligibility(
            reason="KNOWN_SENSOR_LOG_FAILURE",
            original_attempt_id=None,
            original_attempt_preserved=True,
        )
        self.assertFalse(res.approved)
        self.assertIn("MISSING_ORIGINAL_ATTEMPT_ID", res.rejection_reason)

    def test_evaluate_rerun_eligibility_forbidden_purge(self):
        res = evaluate_rerun_eligibility(
            reason="KNOWN_SENSOR_LOG_FAILURE",
            original_attempt_id="RUN-ATTEMPT-001",
            original_attempt_preserved=False,  # Attempting to drop prior attempt!
        )
        self.assertFalse(res.approved)
        self.assertIn("FORBIDDEN_PURGE", res.rejection_reason)

    def test_validate_rerun_log_entry_valid(self):
        entry = {
            "rerun_id": "RERUN-01",
            "original_attempt_id": "ATTEMPT-01",
            "justification": "KNOWN_SENSOR_LOG_FAILURE",
            "approved": True,
            "prior_attempt_preserved": True,
        }
        ok, err = validate_rerun_log_entry(entry)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_validate_rerun_log_entry_discarded_prior(self):
        entry = {
            "rerun_id": "RERUN-02",
            "original_attempt_id": "ATTEMPT-02",
            "justification": "KNOWN_SENSOR_LOG_FAILURE",
            "approved": True,
            "prior_attempt_preserved": False,
        }
        ok, err = validate_rerun_log_entry(entry)
        self.assertFalse(ok)
        self.assertIn("DISCARDED_PRIOR_ATTEMPT", err)

    def test_build_physical_limitation_record(self):
        rec = build_physical_limitation_record(
            scale="1 unit",
            units_tested=1,
            tec_uncertainty="Single module Seebeck effect",
            sensor_limitations=["750ms DS18B20 conversion"],
            ambient_effects="Styrofoam non-hermetic chamber",
            pzem_limits="1Hz Modbus RTU polling",
        )
        self.assertTrue(rec["is_complete"])
        self.assertEqual(rec["units_tested"], 1)


if __name__ == "__main__":
    unittest.main()
