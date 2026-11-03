"""Tests for cg_w09_noise.py (A-W09-04).

The noise figure is W09 evidence: A-W09-04 publishes a healthy gradient reference,
and a gradient is only meaningful against the noise it has to clear. These tests
moved here verbatim with the estimator when the W09 and W10 slices were split, so
the code and its tests stay in the same week. They are mostly about refusal: a
noise figure must not be computed across a temperature ramp, and the two quiescent
segments of the committed capture must never be pooled as one.

The real numbers are asserted against the committed capture because that capture
is the only thermal data this repository holds.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_w09_capture_parser as cp  # noqa: E402
import cg_w09_fixtures as fx  # noqa: E402
import cg_w09_noise as nz  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
W04_CSV = REPO_ROOT / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"


def white_noise(sigma, n, seed=12345):
    import random

    rng = random.Random(seed)
    return [rng.gauss(0.0, sigma) for _ in range(n)]


class DifferenceEstimators(unittest.TestCase):
    def test_second_difference_kills_a_linear_ramp(self):
        series = [20.0 + 0.01 * i + noise for i, noise in enumerate(white_noise(0.02, 400))]
        second = nz.second_difference_sigma(series)["sigma_c"]
        self.assertAlmostEqual(second, 0.02, delta=0.008)

    def test_a_joined_step_inflates_the_first_difference(self):
        # This is the exact mistake the first revision made: two OFF segments of
        # the committed capture sit at ~30 degC and ~20.9 degC with 600 s of
        # cooling between them. Differencing them as one series reports the join
        # as instrument noise.
        joined = [30.0 + n for n in white_noise(0.02, 200)] + [20.9 + n for n in white_noise(0.02, 200)]
        joined_sigma = nz.successive_difference_sigma(joined)["sigma_c"]
        resting_sigma = nz.successive_difference_sigma(joined[:200])["sigma_c"]
        self.assertGreater(joined_sigma, 10 * resting_sigma)
        self.assertLess(resting_sigma, 0.05)

    def test_short_series_return_none_not_zero(self):
        self.assertIsNone(nz.second_difference_sigma([1.0, 2.0])["sigma_c"])
        self.assertIsNone(nz.successive_difference_sigma([1.0])["sigma_c"])

    def test_slope_is_measured_not_assumed(self):
        series = [(i * 1000, 20.0 + 0.002 * i) for i in range(50)]
        self.assertAlmostEqual(nz.linear_slope_c_per_s(series), 0.002, places=6)

    def test_flat_series_has_no_slope(self):
        series = [(i * 1000, 20.0) for i in range(50)]
        self.assertAlmostEqual(nz.linear_slope_c_per_s(series), 0.0, places=9)


class QuiescentRunSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        cls.profile = nz.probe_noise_profile(cls.frames)

    def test_the_two_off_segments_are_found_separately(self):
        # The committed capture has OFF frames before the stage and OFF frames
        # after it; the second group is the box recovering, not resting.
        self.assertEqual(self.profile["quiescent_runs_found"], 2)
        accepted = [r for r in self.profile["quiescent_runs"] if r["accepted_for_noise_estimation"]]
        self.assertEqual(len(accepted), 1)

    def test_the_recovery_segment_is_rejected_as_a_ramp(self):
        rejected = [r for r in self.profile["quiescent_runs"] if not r["accepted_for_noise_estimation"]]
        self.assertEqual(len(rejected), 1)
        slopes = [abs(v["slope_c_per_s"]) for v in rejected[0]["probes"].values()]
        self.assertTrue(all(s > self.profile["stationarity_threshold_c_per_s"] for s in slopes))

    def test_the_join_artifact_does_not_reappear(self):
        # Joining the two segments produced a single -9.25 degC step and a
        # 0.36 degC "noise" figure. Contiguous selection must keep sigma an order
        # of magnitude below that.
        sigma = self.profile["probes"]["t1"]["sigma_c"]
        self.assertLess(sigma, 0.05)
        self.assertGreater(sigma, 0.0)

    def test_sigma_is_near_the_quantisation_floor(self):
        for slot in ("t1", "t3", "t4"):
            entry = self.profile["probes"][slot]
            self.assertLess(entry["sigma_c"], 5 * entry["quantisation_noise_floor_c"])

    def test_hot_side_is_profiled_but_marked_excluded(self):
        entry = self.profile["probes"]["t2"]
        self.assertEqual(entry["physical_position"], "TEC_HOT_SIDE")
        self.assertIn("heatsink", entry["excluded_from_chamber_mean"])

    def test_a_capture_with_no_quiescent_segment_yields_no_sigma(self):
        frames = fx.physical_frames(4, state="COOLING", pwm_applied=999)
        profile = nz.probe_noise_profile(frames)
        self.assertEqual(profile["quiescent_runs_found"], 0)
        self.assertIsNone(profile["probes"]["t1"]["sigma_c"])
