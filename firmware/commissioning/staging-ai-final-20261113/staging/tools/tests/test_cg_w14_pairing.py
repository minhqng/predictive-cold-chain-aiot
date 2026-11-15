"""Tests for cg_w14_pairing.py (A-W14-04 Member A's input to the pairing decision).

A-W14-04 freezes tolerances *with* Member B, so the only failure mode that matters here
is a number arriving in this file dressed as an agreed band. The tests plant exactly
that - a value under a tolerance-named key, an 'agreed' phrase, a flag claiming B signed
- and require the guard to raise, while requiring the real observations the file does
carry to recompute from the capture.
"""

from __future__ import annotations

import csv as csv_module
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_thermal_repeatability as rep  # noqa: E402
import cg_w14_pairing as pair  # noqa: E402
import cg_w14_spatial as sp  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[3]
H8_CAPTURE = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"

BASE = {
    "device_ms": "0", "pwm_applied_permille": "0", "state": "OFF", "boot_id": "aaaaaaaa",
    "session": "H8 box-cooling 600 s", "stage": "H8-C", "door_open": "0",
    "door_polarity": "CONFIRMED", "current_a": "7.0", "current_status": "",
    "voltage_v": "12.0", "voltage_status": "", "power_w": "84.0", "energy_wh": "1.0",
    "t1_c": "30.0", "t1_status": "OK", "t2_c": "30.0", "t2_status": "OK",
    "t3_c": "29.6", "t3_status": "OK", "t4_c": "30.3", "t4_status": "OK",
}


def row(**fields) -> dict[str, str]:
    merged = dict(BASE)
    merged.update({key: str(value) for key, value in fields.items()})
    return merged


def write_capture(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv_module.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def session(boot: str, count: int = 60, start_ms: int = 0) -> list[dict[str, str]]:
    rows = [row(device_ms=start_ms, boot_id=boot)]
    for index in range(count):
        rows.append(row(device_ms=start_ms + (index + 1) * 1000, boot_id=boot,
                        state="COOLING", pwm_applied_permille=999,
                        t1_c=30.0 - 0.02 * index, t2_c=30.0 + 0.03 * index,
                        t3_c=29.6 - 0.015 * index, t4_c=30.3 - 0.025 * index))
    return rows


class NoInventedTolerance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = pair.pairing_input([H8_CAPTURE])

    def test_shipped_payload_carries_no_number_in_the_tolerance_slot(self):
        self.assertIs(self.payload["tolerance_proposed"], False)
        self.assertIsNone(self.payload["tolerance_value"])
        self.assertIs(self.payload["agreed_with_member_b"], False)
        self.assertIs(self.payload["verdict"]["tolerance_frozen"], False)

    def test_status_is_team_dependency_and_nothing_is_physically_verified(self):
        self.assertEqual(self.payload["status"], pair.STATUS)
        self.assertEqual(self.payload["verdict"]["status"], "TEAM_DEPENDENCY")
        self.assertIs(self.payload["verdict"]["physically_verified"], False)
        self.assertIs(self.payload["verdict"]["host_verified"], True)

    def test_planting_a_tolerance_value_raises(self):
        planted = dict(self.payload)
        planted["tolerance_value"] = 0.5
        with self.assertRaises(rep.AnalysisError):
            pair.assert_no_invented_tolerance(planted)

    def test_a_number_under_a_tolerance_key_raises_wherever_it_is_nested(self):
        planted = pair.pairing_input([H8_CAPTURE])
        planted["what_the_real_data_supports"]["temperature_tolerance_c"] = 0.75
        with self.assertRaises(rep.AnalysisError) as caught:
            pair.assert_no_invented_tolerance(planted)
        self.assertIn("temperature_tolerance_c", str(caught.exception))

    def test_a_matching_band_number_also_raises(self):
        planted = pair.pairing_input([H8_CAPTURE])
        planted["verdict"]["initial_matching_band_c"] = 1.0
        with self.assertRaises(rep.AnalysisError):
            pair.assert_no_invented_tolerance(planted)

    def test_claiming_b_agreement_raises(self):
        planted = dict(self.payload)
        planted["agreed_with_member_b"] = True
        with self.assertRaises(rep.AnalysisError):
            pair.assert_no_invented_tolerance(planted)

    def test_agreement_language_raises_even_without_a_number(self):
        planted = pair.pairing_input([H8_CAPTURE])
        planted["asks_for_member_b"].append("the tolerance agreed at the last review")
        with self.assertRaises(rep.AnalysisError):
            pair.assert_no_invented_tolerance(planted)

    def test_tolerance_proposed_flipping_raises(self):
        planted = dict(self.payload)
        planted["tolerance_proposed"] = True
        with self.assertRaises(rep.AnalysisError):
            pair.assert_no_invented_tolerance(planted)

    def test_more_sessions_still_do_not_produce_a_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for index, boot in enumerate(("aaaaaaaa", "bbbbbbbb", "cccccccc")):
                path = pathlib.Path(tmp) / f"run{index}.csv"
                write_capture(path, session(boot, start_ms=index * 200000))
                paths.append(path)
            payload = pair.pairing_input(paths, min_sessions=3)
            self.assertEqual(payload["status"], "TEAM_DEPENDENCY")
            self.assertIsNone(payload["tolerance_value"])
            self.assertIs(payload["tolerance_proposed"], False)


class RealObservationsRecomputed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ablation = sp.ablation_matrix([H8_CAPTURE])
        cls.sensitivity = pair.drop_one_sensitivity(cls.ablation)
        cls.payload = pair.pairing_input([H8_CAPTURE])

    def test_reference_is_the_role_correct_air_mean(self):
        self.assertEqual(self.sensitivity["reference_variant"], "tmean_airroles_v0")
        self.assertEqual(self.sensitivity["reference_delta_c"], -8.7083)
        self.assertEqual(self.sensitivity["phase"], "cooling")

    def test_drop_one_deviations_recomputed_from_the_ablation_rows(self):
        for entry in self.sensitivity["rows"]:
            metrics = self.ablation["captures"][0]["variants"][entry["variant"]]["cooling"]
            self.assertEqual(entry["delta_c"], metrics["delta_c"])
            self.assertEqual(entry["deviation_from_air3_delta_c"],
                             round(metrics["delta_c"]
                                   - self.sensitivity["reference_delta_c"], 4))
            self.assertEqual(entry["feature_terms"], metrics["feature_terms"])
            self.assertEqual(entry["includes_hot_side"], metrics["includes_hot_side"])

    def test_hot_side_variant_is_labelled_and_excluded_from_the_air_only_worst_case(self):
        hot = next(entry for entry in self.sensitivity["rows"]
                   if entry["variant"] == "hot_t2_surface_v0")
        self.assertTrue(hot["includes_hot_side"])
        self.assertFalse(hot["is_chamber_air"])
        air_worst = max(abs(float(entry["deviation_from_air3_delta_c"]))
                        for entry in self.sensitivity["rows"] if entry["is_chamber_air"])
        self.assertEqual(self.sensitivity["air_only_max_abs_deviation_c"], round(air_worst, 4))
        self.assertLess(self.sensitivity["air_only_max_abs_deviation_c"],
                        self.sensitivity["max_abs_deviation_c"])

    def test_air_only_worst_case_is_a_real_measured_number(self):
        # dropping T3 (chamber bottom) moves the driven response furthest of the air sets
        self.assertEqual(self.sensitivity["air_only_max_abs_deviation_c"], 0.5833)

    def test_the_observation_is_not_a_tolerance_by_its_own_words(self):
        self.assertIn("not a matching tolerance", self.sensitivity["read_as"])
        self.assertIn("independent sessions", self.sensitivity["not_a_tolerance_because"])
        self.assertEqual(self.sensitivity["conditioning_fingerprint"],
                         self.ablation["captures"][0]["conditioning_fingerprint"])

    def test_within_session_variability_is_labelled_as_such(self):
        block = self.payload["what_the_real_data_supports"]["within_session_variability"]
        self.assertEqual(block["status"], "WITHIN_SESSION_ONLY")
        self.assertEqual(block["independent_sessions"], 1)
        self.assertTrue(block["label_is_not_a_tolerance"])
        for pair_block in block["pair_blocks"].values():
            self.assertIn("sd_within_session_sample_c", pair_block)
            self.assertNotIn("sd_repeat_c", pair_block)

    def test_why_no_number_quotes_re_derived_data_limits(self):
        text = " ".join(self.payload["why_no_number"])
        self.assertIn("independent thermal sessions on disk: 1", text)
        self.assertIn("door-open events recorded anywhere in committed data: 0 of 957", text)
        self.assertIn("no recorded status in this capture: 957", text)

    def test_cannot_support_list_names_every_missing_axis(self):
        text = " ".join(self.payload["what_the_real_data_cannot_support"])
        for token in ("run-to-run", "door-open", "ROM ids", "hot-side"):
            self.assertIn(token, text)

    def test_join_keys_are_documented_for_b(self):
        keys = self.payload["join_keys_b_can_use"]
        for key in ("capture", "boot_id", "device_ms", "conditioning_fingerprint",
                    "variant", "phase"):
            self.assertIn(key, keys)

    def test_partial_mean_rule_reports_the_real_tally(self):
        block = self.payload["partial_mean_rule"]
        self.assertIn("517-530", block["rule"])
        self.assertTrue(block["partial_term_rows_in_this_capture"])
        self.assertEqual(set(block["partial_term_rows_in_this_capture"].values()), {0})

    def test_captures_are_named_repository_relatively(self):
        for capture in self.payload["captures"]:
            self.assertFalse(pathlib.Path(capture["capture"]).is_absolute())
            self.assertEqual(capture["capture"],
                             "evidence/A/W04/tec-cooling-response-600s.csv")

    def test_asks_for_b_are_actionable(self):
        text = " ".join(self.payload["asks_for_member_b"])
        self.assertIn("pairing axes", text)
        self.assertIn("minimum session count", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
