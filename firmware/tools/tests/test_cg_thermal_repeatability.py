"""Tests for cg_thermal_repeatability.py (A-W07-02/03/04 analysis)."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_thermal_repeatability as rep  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[3]
H8_CAPTURE = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"


def row(**fields) -> dict[str, str]:
    base = {
        "device_ms": "0", "pwm_applied_permille": "0", "current_a": "0.0",
        "power_w": "0.0", "energy_wh": "0", "door_open": "0", "stage": "NONE",
        "t1_c": "30.0", "t1_status": "OK",
        "t2_c": "30.0", "t2_status": "OK",
        "t3_c": "30.0", "t3_status": "OK",
        "t4_c": "30.0", "t4_status": "OK",
    }
    base.update({key: str(value) for key, value in fields.items()})
    return base


def write_capture(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    import csv

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def ramp(start_ms: int, count: int, duty: int, drop: float) -> list[dict[str, str]]:
    """A synthetic segment: chamber-air probes fall, T2 rises while it is driven."""
    rows = []
    for index in range(count):
        value = 30.0 - drop * index
        rows.append(row(device_ms=start_ms + index * 1000, pwm_applied_permille=duty,
                        current_a=7.0 if duty else 0.0, power_w=68.0 if duty else 0.0,
                        energy_wh=round(index * 0.02, 4),
                        t1_c=value, t2_c=30.0 + 0.01 * index, t3_c=value - 0.1,
                        t4_c=value + 0.05))
    return rows


class RepresentationTests(unittest.TestCase):
    def test_the_two_definitions_are_not_the_same_number(self) -> None:
        sample = row(t1_c="30.0", t2_c="34.0", t3_c="30.0")
        chamber3, _, _ = rep.tmean(sample, "tmean_chamber3_v0")
        excluded, _, _ = rep.tmean(sample, "tmean_t2excluded_v0")
        self.assertEqual(chamber3, 31.333333333333332)
        self.assertEqual(excluded, 30.0)

    def test_a_partial_mean_reports_its_term_count(self) -> None:
        sample = row(t2_c="nan", t2_status="INVALID")
        value, count, terms = rep.tmean(sample, "tmean_chamber3_v0")
        self.assertEqual(terms, 3)
        self.assertEqual(count, 2)
        self.assertAlmostEqual(value, 30.0)

    def test_an_unusable_probe_is_never_read_as_zero(self) -> None:
        value, count, _ = rep.tmean(row(t1_c="nan", t2_c="nan", t3_c="nan"),
                                    "tmean_chamber3_v0")
        self.assertIsNone(value)
        self.assertEqual(count, 0)

    def test_a_stale_status_is_not_evidence(self) -> None:
        """A value with a non-OK status has no usable reading, whatever it says."""
        self.assertIsNone(rep._number(row(t1_c="25.0", t1_status="STALE"), "t1_c"))
        self.assertIsNotNone(rep._number(row(t1_c="25.0", t1_status="OK"), "t1_c"))

    def test_a_column_is_never_its_own_status(self) -> None:
        """device_ms has no status column; reading one from itself emptied a slope."""
        self.assertIsNone(rep._status_key(row(device_ms="123"), "device_ms"))
        self.assertEqual(rep._number(row(device_ms="123"), "device_ms"), 123.0)


class PhaseTests(unittest.TestCase):
    def test_applied_duty_defines_the_cooling_block(self) -> None:
        rows = ([row(device_ms=i * 1000) for i in range(3)]
                + ramp(3000, 4, 999, 0.3)
                + [row(device_ms=7000), row(device_ms=8000)])
        phases = rep.split_phases(rows)
        self.assertEqual(len(phases["baseline"]), 3)
        self.assertEqual(len(phases["cooling"]), 4)
        self.assertEqual(len(phases["recovery"]), 2)

    def test_a_capture_with_no_cooling_block_is_a_passive_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            path = pathlib.Path(workdir) / "passive.csv"
            write_capture(path, ramp(0, 30, 0, -0.01))
            report = rep.analyze([path], "tmean_chamber3_v0", 3)
        self.assertTrue(report["runs"][0]["passive_candidate"])
        self.assertFalse(report["runs"][0]["cooling_candidate"])
        self.assertNotIn("cooling", report["phases"])
        self.assertEqual(report["verdict"]["captures_with_no_cooling_block"], 1)


class MetricsTests(unittest.TestCase):
    def test_slope_is_none_when_every_sample_shares_a_timestamp(self) -> None:
        """A degenerate x-axis must not become a slope of zero."""
        points = [(0.0, 30.0), (0.0, 29.0), (0.0, 28.0)]
        self.assertIsNone(rep.trailing_slope_c_per_min(points))

    def test_minutes_to_1c_is_none_when_it_never_happens(self) -> None:
        points = [(0.0, 30.0), (1.0, 29.9), (2.0, 29.85)]
        self.assertIsNone(rep.minutes_to_first_1c_drop(points))

    def test_minutes_to_1c_counts_the_first_crossing(self) -> None:
        points = [(0.0, 30.0), (1.0, 29.5), (2.0, 28.0)]
        self.assertEqual(rep.minutes_to_first_1c_drop(points), 2.0)

    def test_a_short_phase_is_reported_not_invented(self) -> None:
        metrics = rep.phase_metrics([row(device_ms="0")], "cooling", "tmean_chamber3_v0")
        self.assertFalse(metrics["usable"])
        self.assertEqual(metrics["reason"], "FEWER_THAN_TWO_USABLE_SAMPLES")

    def test_recovery_is_separated_from_the_action(self) -> None:
        """docs/01 20.6: recovery is measured after the action ended, not inside it."""
        rows = ramp(0, 8, 999, 0.6) + ramp(8000, 6, 0, -0.4)
        phases = rep.split_phases(rows)
        cooling = rep.phase_metrics(phases["cooling"], "cooling", "tmean_chamber3_v0")
        recovery = rep.phase_metrics(phases["recovery"], "recovery", "tmean_chamber3_v0")
        self.assertLess(cooling["delta_c"], 0.0)
        self.assertGreater(recovery["delta_c"], 0.0)
        # A phase that crosses one degree reports the crossing; a shallow one
        # reports nothing rather than a zero that would read as instant cooling.
        self.assertIsNotNone(cooling["minutes_to_1c"])
        shallow = rep.phase_metrics(ramp(0, 6, 999, 0.05), "cooling",
                                    "tmean_chamber3_v0")
        self.assertIsNone(shallow["minutes_to_1c"])


class StatisticsTests(unittest.TestCase):
    def test_spread_uses_the_sample_formula(self) -> None:
        values = [1.0, 3.0]
        result = rep.summarize(values, "delta_c")
        self.assertEqual(result["mean"], 2.0)
        self.assertAlmostEqual(result["sd_sample"], 1.414214, places=6)
        self.assertEqual(result["n"], 2)

    def test_one_run_never_produces_a_spread(self) -> None:
        result = rep.summarize([2.0], "delta_c")
        self.assertIsNone(result["sd_sample"])
        self.assertIn("spread needs at least two runs", result["cv_note"])

    def test_cv_is_undefined_at_a_zero_mean(self) -> None:
        result = rep.summarize([-1.0, 1.0], "delta_c")
        self.assertEqual(result["mean"], 0.0)
        self.assertIsNone(result["cv_pct"])
        self.assertIn("mean is zero", result["cv_note"])

    def test_insufficient_runs_says_how_many_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            path = pathlib.Path(workdir) / "one.csv"
            write_capture(path, ramp(0, 20, 0, -0.01) + ramp(20000, 40, 999, 0.05)
                          + ramp(60000, 20, 0, -0.05))
            report = rep.analyze([path], "tmean_chamber3_v0", 3)
        verdict = report["phases"]["cooling"]["verdict"]
        self.assertEqual(verdict["status"], "INSUFFICIENT_RUNS")
        self.assertEqual(verdict["additional_runs_needed"], 2)
        self.assertFalse(report["verdict"]["plant_variation_reportable"])

    def test_three_runs_produce_a_repeatability_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            paths = []
            for index in range(3):
                path = pathlib.Path(workdir) / f"run{index}.csv"
                write_capture(path, ramp(0, 20, 0, -0.01)
                              + ramp(20000, 40, 999, 0.05 + 0.002 * index)
                              + ramp(60000, 20, 0, -0.05))
                paths.append(path)
            report = rep.analyze(paths, "tmean_chamber3_v0", 3)
        verdict = report["phases"]["cooling"]["verdict"]
        self.assertEqual(verdict["status"], "REPEATABILITY_COMPUTED")
        self.assertEqual(verdict["runs"], 3)
        stats = report["phases"]["cooling"]["statistics"]["delta_c"]
        self.assertEqual(stats["n"], 3)
        self.assertIsNotNone(stats["sd_sample"])
        self.assertIsNotNone(stats["cv_pct"])


class RealCaptureTests(unittest.TestCase):
    @unittest.skipUnless(H8_CAPTURE.is_file(), "the committed H8 cooling capture is absent")
    def test_the_committed_cooling_run_analyses_in_both_definitions(self) -> None:
        chamber3 = rep.analyze([H8_CAPTURE], "tmean_chamber3_v0", 3)
        excluded = rep.analyze([H8_CAPTURE], "tmean_t2excluded_v0", 3)
        c3 = chamber3["phases"]["cooling"]["runs"][0]
        ex = excluded["phases"]["cooling"]["runs"][0]
        # Recorded fact: during cooling T2 rises while T1/T3/T4 fall, so including
        # it in a chamber-air mean flattens the measured response. This is the
        # evidence for the open T2 decision, not a resolution of it.
        self.assertGreater(c3["delta_c"], ex["delta_c"])
        self.assertLess(ex["delta_c"], -5.0)
        self.assertEqual(chamber3["verdict"]["cooling_step_runs"], "INSUFFICIENT_RUNS")
        self.assertEqual(excluded["representation"], "tmean_t2excluded_v0")

    @unittest.skipUnless(H8_CAPTURE.is_file(), "the committed H8 cooling capture is absent")
    def test_the_gate_that_never_moved_is_reported_as_current_not_absent(self) -> None:
        report = rep.analyze([H8_CAPTURE], "tmean_chamber3_v0", 3)
        baseline = report["phases"]["baseline"]["runs"][0]
        cooling = report["phases"]["cooling"]["runs"][0]
        self.assertEqual(baseline["mean_current_a"], 0.0)
        self.assertGreater(cooling["peak_current_a"], 5.0)
        self.assertGreater(cooling["valid_sample_fraction"], 0.99)


class OverlayTests(unittest.TestCase):
    def test_the_overlay_carries_the_representation_of_every_point(self) -> None:
        import csv as csv_module

        with tempfile.TemporaryDirectory() as workdir:
            capture = pathlib.Path(workdir) / "run.csv"
            out = pathlib.Path(workdir) / "overlay.csv"
            write_capture(capture, ramp(0, 5, 0, -0.01) + ramp(5000, 8, 999, 0.2))
            report = rep.analyze([capture], "tmean_t2excluded_v0", 3)
            rep.write_overlay_csv(out, report)
            with out.open(encoding="utf-8") as handle:
                rows = list(csv_module.DictReader(handle))
        self.assertTrue(rows)
        self.assertEqual({r["representation"] for r in rows}, {"tmean_t2excluded_v0"})
        self.assertEqual({r["phase"] for r in rows}, {"baseline", "cooling"})


if __name__ == "__main__":
    unittest.main()
