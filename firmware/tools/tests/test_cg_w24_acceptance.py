"""Unit tests for ColdGuard Member A — W24 Final Acceptance Tool."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from cg_w24_final_freeze import (
    REQUIRED_INDEPENDENT_RUNS,
    SYSTEM_INTEGRATION_NOT_ASSERTABLE,
    VERDICT_DATA_INSUFFICIENT,
    VERDICT_PHYSICALLY_ACCEPTED,
    VERDICT_PHYSICAL_ACCEPTANCE_PENDING,
    collate_acceptance_census,
    validate_final_configuration,
)


HW_CONF = "HW-CONF-2026-10-27-ASBUILT-V2"
ALL_WEEKS = list(range(1, 25))


def _record(root, rel, body, n, device="DEV-A", boot=None, source="RAW_DEVICE_CAPTURE",
            conf=HW_CONF):
    """One evidence record whose hash matches the bytes actually on disk."""
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return {
        "run_id": f"RUN-{n}",
        "device_id": device,
        "boot_id": boot if boot is not None else f"BOOT-{n}",
        "source_type": source,
        "artifact_path": rel,
        "sha256": hashlib.sha256(body).hexdigest(),
        "hardware_config_id": conf,
    }


class TestW24FinalAcceptance(unittest.TestCase):

    def setUp(self):
        self.valid_config = {
            "hardware_config_id": "HW-CONF-2026-10-27-ASBUILT-V2",
            "evidence_class": "AS_BUILT_BENCH_AUDITED",
            "pin_map_v2": {
                "one_wire_gpio": 33,
                "bme280_sda_gpio": 21,
                "bme280_scl_gpio": 34,
                "door_reed_gpio": 35,
                "pzem_tx_gpio": 36,
                "pzem_rx_gpio": 37,
                "ibt2_rpwm_gpio": 5,
                "ibt2_r_en_gpio": 6,
                "ibt2_l_en_gpio": 10,
            },
            "sensor_roms": {
                "t1": "287088CA00000051",
                "t2": "28AEBF2200000006",
                "t3": "28CBE9CA00000072",
                "t4": "283BE5C9000000A9",
            },
            "sensor_positions": {
                "t1": "CHAMBER_CENTER",
                "t2": "TEC_HOT_SIDE",
                "t3": "CHAMBER_BOTTOM",
                "t4": "NEAR_DOOR",
            },
            "power_and_protection": {
                "fuse_type": "15A blade fuse",
                "fuse_slot_3_posture": "REMOVED (TEC isolated)",
                "pzem_shunt": "FL-2 0.5 50A/75mV",
            },
        }

    def test_validate_final_configuration_clean(self):
        res = validate_final_configuration(self.valid_config)
        self.assertTrue(res.valid)
        self.assertEqual(res.errors, [])
        self.assertEqual(res.evidence_class, "AS_BUILT_BENCH_AUDITED")

    def test_validate_final_configuration_wrong_pin(self):
        bad_config = dict(self.valid_config)
        bad_pins = dict(self.valid_config["pin_map_v2"])
        bad_pins["one_wire_gpio"] = 4  # Wrong old pin
        bad_config["pin_map_v2"] = bad_pins
        res = validate_final_configuration(bad_config)
        self.assertFalse(res.valid)
        self.assertTrue(any("PIN_MISMATCH: one_wire_gpio" in e for e in res.errors))

    def test_validate_final_configuration_wrong_fuse(self):
        bad_config = dict(self.valid_config)
        bad_power = dict(self.valid_config["power_and_protection"])
        bad_power["fuse_type"] = "10A blade fuse"  # Wrong fuse rating
        bad_config["power_and_protection"] = bad_power
        res = validate_final_configuration(bad_config)
        self.assertFalse(res.valid)
        self.assertTrue(any("FUSE_MISMATCH" in e for e in res.errors))

    def test_validate_final_configuration_fuse_not_removed(self):
        bad_config = dict(self.valid_config)
        bad_power = dict(self.valid_config["power_and_protection"])
        bad_power["fuse_slot_3_posture"] = "INSTALLED_ENERGIZED"  # Safety violation
        bad_config["power_and_protection"] = bad_power
        res = validate_final_configuration(bad_config)
        self.assertFalse(res.valid)
        self.assertTrue(any("FUSE_POSTURE_VIOLATION" in e for e in res.errors))

    def test_collate_acceptance_census_with_open_gates(self):
        all_weeks = list(range(1, 25))
        gates = ["H-GATE-1", "H-GATE-2", "H-GATE-5"]
        census = collate_acceptance_census(
            weeks_delivered=all_weeks,
            physical_runs_count=1,
            hardware_status="FAIL_CLOSED_FROZEN",
            open_hardware_gates=gates,
        )
        self.assertEqual(census["delivered_week_count"], 24)
        self.assertTrue(census["all_weeks_accounted_for"])
        self.assertTrue(census["software_contract_ready"])
        # Physical acceptance MUST NOT be granted when open hardware gates exist!
        self.assertFalse(census["physical_acceptance_ready"])
        self.assertEqual(
            census["handover_verdict"],
            "READY_FOR_SOFTWARE_INTEGRATION_PHYSICAL_ACCEPTANCE_BLOCKED",
        )

    def test_collate_acceptance_census_missing_weeks(self):
        partial = list(range(1, 17))
        census = collate_acceptance_census(
            weeks_delivered=partial,
            physical_runs_count=1,
            hardware_status="FAIL_CLOSED_FROZEN",
            open_hardware_gates=[],
        )
        self.assertEqual(census["delivered_week_count"], 16)
        self.assertFalse(census["all_weeks_accounted_for"])
        self.assertFalse(census["software_contract_ready"])
        self.assertEqual(census["handover_verdict"], "INCOMPLETE")


class TestW24CensusIsNotClaimDriven(unittest.TestCase):
    """A caller must not be able to reach physical acceptance by typing numbers."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def census(self, **kw):
        base = dict(weeks_delivered=ALL_WEEKS, physical_runs_count=0,
                    hardware_status="FAIL_CLOSED_FROZEN", open_hardware_gates=[],
                    repo_root=self.root, expected_hardware_config_id=HW_CONF)
        base.update(kw)
        return collate_acceptance_census(**base)

    def test_counts_alone_cannot_grant_physical_acceptance(self):
        res = self.census(physical_runs_count=9999, physical_evidence=None)
        self.assertFalse(res["physical_acceptance_ready"])
        self.assertEqual(res["acceptance_verdict"], VERDICT_DATA_INSUFFICIENT)
        self.assertNotEqual(res["handover_verdict"], "FULLY_ACCEPTED")

    def test_absent_gate_register_is_unknown_not_zero_gates(self):
        res = collate_acceptance_census(
            weeks_delivered=ALL_WEEKS, physical_runs_count=5,
            hardware_status="FAIL_CLOSED_FROZEN",
        )
        self.assertFalse(res["gate_register_supplied"])
        self.assertEqual(res["acceptance_verdict"], VERDICT_DATA_INSUFFICIENT)

    def test_cited_artifact_that_does_not_exist_is_refused(self):
        good = [self._mk(f"evidence/A/W24/run{i}.csv", i) for i in range(2)]
        bad = dict(self._mk("evidence/A/W24/run9.csv", 9))
        bad["artifact_path"] = "evidence/A/RC/remaining-hardware-gates.md"
        res = self.census(physical_runs_count=3, physical_evidence=good + [bad])
        self.assertEqual(res["physical_runs_verified"], 2)
        self.assertTrue(any("EVIDENCE_ARTIFACT_MISSING" in r for r in res["evidence_refusals"]))
        self.assertFalse(res["physical_acceptance_ready"])

    def test_recorded_hash_that_does_not_match_bytes_is_refused(self):
        rec = self._mk("evidence/A/W24/run1.csv", 1)
        rec["sha256"] = "0" * 64
        res = self.census(physical_evidence=[rec])
        self.assertTrue(any("EVIDENCE_HASH_MISMATCH" in r for r in res["evidence_refusals"]))
        self.assertEqual(res["physical_runs_verified"], 0)

    def test_host_fixture_cannot_count_as_physical_run(self):
        rec = self._mk("evidence/A/W24/run1.csv", 1, source="HOST_SYNTHETIC_FIXTURE")
        res = self.census(physical_evidence=[rec])
        self.assertTrue(any("EVIDENCE_SOURCE_SYNTHETIC" in r for r in res["evidence_refusals"]))
        self.assertEqual(res["physical_runs_verified"], 0)

    def test_segments_of_one_boot_count_as_one_independent_run(self):
        recs = [self._mk(f"evidence/A/W24/seg{i}.csv", i, boot="BOOT-SAME")
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        res = self.census(physical_runs_count=3, physical_evidence=recs)
        self.assertEqual(res["physical_runs_verified"], 1)
        self.assertTrue(any("EVIDENCE_RUN_NOT_INDEPENDENT" in r for r in res["evidence_refusals"]))
        self.assertFalse(res["physical_acceptance_ready"])

    def test_other_hardware_config_is_refused(self):
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i, conf="HW-CONF-OLD-V1")
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        res = self.census(physical_evidence=recs)
        self.assertTrue(any("EVIDENCE_HARDWARE_CONFIG_MISMATCH" in r for r in res["evidence_refusals"]))

    def test_incomplete_record_is_refused(self):
        rec = self._mk("evidence/A/W24/run1.csv", 1)
        del rec["device_id"]
        res = self.census(physical_evidence=[rec])
        self.assertTrue(any("EVIDENCE_FIELD_MISSING" in r for r in res["evidence_refusals"]))

    def test_positive_control_genuine_independent_runs_are_accepted(self):
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i)
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        res = self.census(physical_runs_count=REQUIRED_INDEPENDENT_RUNS, physical_evidence=recs)
        self.assertEqual(res["physical_runs_verified"], REQUIRED_INDEPENDENT_RUNS)
        self.assertTrue(res["physical_acceptance_ready"])
        self.assertEqual(res["acceptance_verdict"], VERDICT_PHYSICALLY_ACCEPTED)

    def test_open_gates_with_verified_runs_stay_pending(self):
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i)
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        res = self.census(physical_evidence=recs, open_hardware_gates=["H-GATE-1"])
        self.assertFalse(res["physical_acceptance_ready"])
        self.assertEqual(res["acceptance_verdict"], VERDICT_PHYSICAL_ACCEPTANCE_PENDING)

    def test_member_a_never_asserts_system_integration(self):
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i)
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        res = self.census(physical_evidence=recs)
        self.assertEqual(res["system_integration_verified"], SYSTEM_INTEGRATION_NOT_ASSERTABLE)

    def test_out_of_range_week_id_is_surfaced(self):
        res = self.census(weeks_delivered=ALL_WEEKS + [99])
        self.assertEqual(res["unexpected_week_ids"], [99])
        self.assertFalse(res["all_weeks_accounted_for"])

    def _mk(self, rel, n, **kw):
        return _record(self.root, rel, f"run {n} payload\n".encode(), n, **kw)


if __name__ == "__main__":
    unittest.main()
