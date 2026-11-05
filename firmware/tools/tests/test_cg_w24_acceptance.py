"""Unit tests for ColdGuard Member A — W24 Final Acceptance Tool."""

import unittest

from cg_w24_final_freeze import (
    collate_acceptance_census,
    validate_final_configuration,
)


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


if __name__ == "__main__":
    unittest.main()
