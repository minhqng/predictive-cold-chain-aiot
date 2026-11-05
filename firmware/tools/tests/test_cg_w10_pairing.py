"""Tests for cg_w10_pairing.py (A-W10-04/-05).

The estimator's job is to tell Member B what can be frozen today and what cannot,
so the tests are mostly about refusal: a tolerance must not be invented from one
run, a noise figure must not be computed across a temperature ramp, and a horizon
distribution must not be claimed without S2 data. The real numbers it does
produce are asserted against the committed capture, because they are the only
quantities this week can publish.
"""

from __future__ import annotations

import math
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_w09_capture_parser as cp  # noqa: E402
import cg_w09_fixtures as fx  # noqa: E402
import cg_w10_pairing as pr  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
W04_CSV = REPO_ROOT / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"


class MinimumDetectable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        cls.floor = pr.minimum_detectable_disturbance(cls.frames)

    def test_floor_is_reported_per_probe_and_per_mean(self):
        self.assertEqual(set(self.floor["sigma_by_probe_c"]), {"t1", "t3", "t4"})
        self.assertIsNotNone(self.floor["sigma_chamber_air_mean_c"])

    def test_mean_is_more_sensitive_than_the_worst_probe(self):
        self.assertLess(
            self.floor["sigma_chamber_air_mean_c"],
            max(self.floor["sigma_by_probe_c"].values()),
        )

    def test_longer_horizons_detect_less(self):
        values = [
            self.floor["horizons"][f"{h}s"]["chamber_air_mean_c"] for h in pr.DETECTION_HORIZONS_S
        ]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_a_higher_z_score_costs_magnitude(self):
        conservative = pr.minimum_detectable_disturbance(self.frames, z=3.0)
        self.assertGreater(
            conservative["practical_floor_c"], self.floor["practical_floor_c"]
        )

    def test_single_frame_bound_is_stated_without_the_averaging_assumption(self):
        self.assertIn("60s", self.floor["horizons"])
        self.assertGreater(
            self.floor["single_frame_floor_binding_c"],
            self.floor["horizons"]["60s"]["chamber_air_mean_c"],
        )

    def test_the_white_noise_assumption_is_visible(self):
        self.assertIn("optimistic bound", self.floor["assumption"])

    def test_the_published_formula_is_the_formula_that_was_evaluated(self):
        """docs/01 §20.5: the method must be named, and naming it wrongly is worse.

        The published assumption used to read ``sigma_horizon(H) =
        sigma_successive_diff / sqrt(H)`` while the code multiplied the
        trend-immune **second-difference** sigma by z = 2.58: recomputing the
        printed T3 60 s floor from the printed formula gave 0.00269 against the
        published 0.00695, exactly the missing factor.
        """
        formula = self.floor["detection_floor_formula"]
        self.assertIn("2.58", formula)
        self.assertIn("sigma_second_diff", formula)
        self.assertNotIn("sigma_successive_diff", formula)
        self.assertNotIn("sigma_successive_diff", self.floor["assumption"])
        self.assertEqual(self.floor["z_score"], 2.58)

    def test_every_published_floor_recomputes_from_the_published_formula(self):
        z = self.floor["z_score"]
        for horizon_key, entry in self.floor["horizons"].items():
            seconds = int(horizon_key.rstrip("s"))
            for slot, sigma in self.floor["sigma_by_probe_c"].items():
                with self.subTest(horizon=horizon_key, slot=slot):
                    self.assertEqual(
                        entry["per_probe_c"][slot],
                        round(z * sigma / math.sqrt(seconds), 5),
                    )

    def test_a_different_z_gives_a_different_formula_and_floor(self):
        conservative = pr.minimum_detectable_disturbance(self.frames, z=3.0)
        self.assertIn("3.0", conservative["detection_floor_formula"])
        self.assertEqual(
            conservative["horizons"]["60s"]["per_probe_c"]["t1"],
            round(3.0 * conservative["sigma_by_probe_c"]["t1"] / math.sqrt(60), 5),
        )

    def test_the_reading_names_a_magnitude_and_a_horizon(self):
        self.assertIn("indistinguishable from nothing", self.floor["reading"])

    def test_no_floor_is_claimed_without_quiescent_data(self):
        frames = fx.physical_frames(3, state="COOLING", pwm_applied=999)
        with self.assertRaises(Exception):
            # empty profile -> no sigma -> the estimator must not print a number
            pr.minimum_detectable_disturbance(frames)["practical_floor_c"]


class AchievableTolerance(unittest.TestCase):
    def test_one_run_cannot_produce_a_tolerance(self):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        report = pr.achievable_tolerance_from_available_runs({"H8C": frames})
        self.assertEqual(report["runs_available"], 1)
        self.assertIsNone(report["pairing_tolerance_c"])
        self.assertEqual(report["status_label"], "NEED_USER_ACTION")
        self.assertIn("cannot be estimated from one run", report["why"])

    def test_the_floor_is_still_offered_as_the_freezable_bound(self):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        report = pr.achievable_tolerance_from_available_runs({"H8C": frames})
        self.assertIn("noise floor", report["what_can_be_frozen_now"])

    def test_two_runs_make_the_spread_computable(self):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        report = pr.achievable_tolerance_from_available_runs({"A": frames, "B": frames})
        self.assertEqual(report["initial_tmean_spread_c"], "computable")


class HorizonSupport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        cls.floor = pr.minimum_detectable_disturbance(frames)
        cls.support = pr.horizon_support(0, cls.floor)

    def test_no_distribution_is_claimed_without_s2_data(self):
        self.assertFalse(
            self.support["distributions_requested"]["door_to_critical_s"]["computable_now"]
        )
        self.assertEqual(
            self.support["distributions_requested"]["door_to_critical_s"]["blocking_reason"],
            "no S2 pilot capture exists",
        )

    def test_member_a_does_not_choose_the_horizon(self):
        self.assertIn("ML horizon choice", self.support["member_b_decision_inputs_not_supplied_by_member_a"])
        self.assertIn("pair-matching tolerance value", self.support["member_b_decision_inputs_not_supplied_by_member_a"])
        self.assertNotIn("horizon_s", self.support)

    def test_controller_response_needs_member_d(self):
        requires = self.support["distributions_requested"]["controller_response_s"]["requires"]
        self.assertTrue(any("controller" in item for item in requires))

    def test_the_floor_is_still_published_as_support(self):
        self.assertEqual(self.support["what_is_supported_today"]["noise_floor_c"],
                         self.floor["practical_floor_c"])
        self.assertIn("60s", self.support["what_is_supported_today"]["horizon_curve_c"])

    def test_status_becomes_analyzed_when_events_exist(self):
        support = pr.horizon_support(4, self.floor)
        self.assertEqual(support["status_label"], "REAL_DATA_ANALYZED")


if __name__ == "__main__":
    unittest.main()
