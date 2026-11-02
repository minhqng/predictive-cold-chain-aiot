"""Tests for cg_thermal_repeatability.py (A-W07-02/03/04 analysis).

The claims under test are the ones that could quietly make a single run look like a
distribution: what counts as evidence, what is merely unqualified, what is excluded
and counted, which slope summarizes a phase, and what happens when the runs simply
are not there.
"""

from __future__ import annotations

import csv as csv_module
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_thermal_repeatability as rep  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[3]
H8_CAPTURE = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"

BASE_COLUMNS = {
    "device_ms": "0", "pwm_applied_permille": "0", "current_a": "0.0",
    "current_status": "OK", "voltage_v": "12.0", "voltage_status": "OK",
    "power_w": "0.0", "energy_wh": "0", "door_open": "0", "stage": "NONE",
    "t1_c": "30.0", "t1_status": "OK",
    "t2_c": "30.0", "t2_status": "OK",
    "t3_c": "30.0", "t3_status": "OK",
    "t4_c": "30.0", "t4_status": "OK",
}


def row(**fields) -> dict[str, str]:
    merged = dict(BASE_COLUMNS)
    merged.update({key: str(value) for key, value in fields.items()})
    return merged


def write_capture(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv_module.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def ramp(start_ms: int, count: int, duty: int, drop: float) -> list[dict[str, str]]:
    """A synthetic segment: air probes move by `drop` per sample, hot side the other way."""
    rows = []
    for index in range(count):
        value = 30.0 - drop * index
        rows.append(row(device_ms=start_ms + index * 1000, pwm_applied_permille=duty,
                        current_a=7.0 if duty else 0.0,
                        current_status="OK" if duty else "",
                        power_w=68.0 if duty else 0.0,
                        energy_wh=round(index * 0.02, 4),
                        t1_c=value, t2_c=30.0 + 0.01 * index, t3_c=value - 0.1,
                        t4_c=value + 0.05))
    return rows


class RepresentationTests(unittest.TestCase):
    def test_definitions_name_their_terms_roles_and_hot_side(self) -> None:
        report = {name: rep.REPRESENTATIONS[name] for name in rep.REPRESENTATIONS}
        self.assertFalse(report["tmean_airroles_v0"]["includes_hot_side"])
        self.assertTrue(report["tmean_chamber3_v0"]["includes_hot_side"])
        self.assertEqual(rep.terms_of("tmean_airroles_v0"), ("t1_c", "t3_c", "t4_c"))
        self.assertEqual(
            [rep.AS_BUILT_ROLES[t] for t in rep.terms_of("tmean_airroles_v0")],
            ["CHAMBER_CENTER", "CHAMBER_BOTTOM", "CHAMBER_NEAR_DOOR"])
        self.assertEqual(rep.AS_BUILT_ROLES["t2_c"], "TEC_HOT_SIDE")

    def test_the_hot_side_flattens_the_mean_and_the_flag_says_so(self) -> None:
        sample = row(t1_c="30.0", t2_c="34.0", t3_c="30.0", t4_c="30.0")
        air, _, _ = rep.tmean(sample, "tmean_airroles_v0")
        literal, _, _ = rep.tmean(sample, "tmean_chamber3_v0")
        self.assertEqual(air, 30.0)
        self.assertEqual(literal, 31.333333333333332)

    def test_a_partial_mean_reports_its_term_count(self) -> None:
        value, count, terms = rep.tmean(row(t2_c="nan", t2_status="INVALID"),
                                        "tmean_chamber3_v0")
        self.assertEqual((count, terms), (2, 3))
        self.assertAlmostEqual(value, 30.0)

    def test_an_unusable_probe_is_never_read_as_zero(self) -> None:
        value, count, _ = rep.tmean(row(t1_c="nan", t2_c="nan", t3_c="nan"),
                                    "tmean_chamber3_v0")
        self.assertIsNone(value)
        self.assertEqual(count, 0)

    def test_a_stale_status_is_not_evidence(self) -> None:
        self.assertIsNone(rep.number(row(t1_c="25.0", t1_status="STALE"), "t1_c"))
        self.assertIsNotNone(rep.number(row(t1_c="25.0", t1_status="OK"), "t1_c"))

    def test_empty_status_is_usable_but_marked_unqualified(self) -> None:
        """"No recorded validity" is a third state, not OK and not invalid."""
        value, state = rep.reading(row(current_a="7.15", current_status=""), "current_a")
        self.assertEqual(value, 7.15)
        self.assertEqual(state, "unqualified")
        self.assertEqual(rep.reading(row(current_a="7.15", current_status="OK"),
                                     "current_a")[1], "ok")
        self.assertEqual(rep.reading(row(current_a="7.15", current_status="INVALID"),
                                     "current_a")[1], "invalid")

    def test_a_column_is_never_its_own_status(self) -> None:
        self.assertIsNone(rep._status_key(row(device_ms="123"), "device_ms"))
        self.assertEqual(rep.number(row(device_ms="123"), "device_ms"), 123.0)


class PhaseTests(unittest.TestCase):
    def test_applied_duty_defines_the_cooling_block(self) -> None:
        rows = ([row(device_ms=i * 1000) for i in range(3)]
                + ramp(3000, 4, 999, 0.3)
                + [row(device_ms=7000), row(device_ms=8000)])
        phases = rep.split_phases(rows)
        self.assertEqual((len(phases["baseline"]), len(phases["cooling"]),
                          len(phases["recovery"])), (3, 4, 2))
        self.assertEqual(phases["undetermined"], [])

    def test_a_row_with_no_duty_value_is_undetermined_not_passive(self) -> None:
        rows = [row(device_ms=0), row(device_ms=1000, pwm_applied_permille="nan"),
                row(device_ms=2000, pwm_applied_permille=999), row(device_ms=3000)]
        phases = rep.split_phases(rows)
        self.assertEqual(len(phases["undetermined"]), 1)
        self.assertEqual(len(phases["baseline"]), 1)

    def test_a_capture_with_no_cooling_block_is_a_passive_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            path = pathlib.Path(workdir) / "passive.csv"
            write_capture(path, ramp(0, 30, 0, -0.01))
            report = rep.analyze([path], "tmean_airroles_v0", 3)
        self.assertTrue(report["runs"][0]["passive_candidate"])
        self.assertFalse(report["runs"][0]["cooling_candidate"])
        self.assertNotIn("cooling", report["phases"])
        self.assertEqual(report["verdict"]["captures_with_no_cooling_block"], 1)


class MetricsTests(unittest.TestCase):
    def test_slope_is_none_when_every_sample_shares_a_timestamp(self) -> None:
        self.assertIsNone(rep.trailing_slope_c_per_min([(0.0, 30.0), (0.0, 29.0),
                                                        (0.0, 28.0)]))

    def test_threshold_time_is_none_when_it_never_happens(self) -> None:
        points = [(0.0, 30.0), (1.0, 29.9), (2.0, 29.85)]
        self.assertIsNone(rep.minutes_to_threshold_drop(points))

    def test_threshold_time_counts_the_first_crossing(self) -> None:
        points = [(0.0, 30.0), (1.0, 29.5), (2.0, 28.0)]
        self.assertEqual(rep.minutes_to_threshold_drop(points), 2.0)

    def test_recovery_measures_a_rise_not_a_fall(self) -> None:
        points = [(0.0, 28.0), (1.0, 28.6), (2.0, 29.2)]
        self.assertIsNone(rep.minutes_to_threshold_drop(points, 1.0))
        self.assertEqual(rep._time_to_move(points, "recovery", 1.0), 2.0)
        self.assertIsNone(rep._time_to_move(points, "baseline", 1.0))

    def test_partial_means_are_excluded_from_a_phase_series_and_counted(self) -> None:
        rows = ramp(0, 6, 999, 0.1) + [row(device_ms=6000, pwm_applied_permille=999,
                                           t1_c="nan", t1_status="INVALID")]
        metrics = rep.phase_metrics(rows, "cooling", "tmean_chamber3_v0")
        self.assertEqual(metrics["samples"], 6)
        self.assertEqual(metrics["partial_term_rows"], 1)
        self.assertEqual(metrics["skipped_rows"], 1)
        self.assertEqual(metrics["rows_read"], 7)
        self.assertLess(metrics["valid_sample_fraction"], 1.0)

    def test_unqualified_electrical_values_are_reported_not_assumed_valid(self) -> None:
        rows = [row(device_ms=i * 1000, pwm_applied_permille=999, current_a="7.0",
                    current_status="", power_w="84.0") for i in range(5)]
        metrics = rep.phase_metrics(rows, "cooling", "tmean_airroles_v0")
        self.assertTrue(metrics["usable"])
        self.assertFalse(metrics["electrical_status_recorded"])
        self.assertEqual(metrics["current_rows_unqualified"], 5)
        self.assertEqual(metrics["peak_current_a"], 7.0)

    def test_a_short_phase_is_reported_not_invented(self) -> None:
        metrics = rep.phase_metrics([row(device_ms="0")], "cooling", "tmean_airroles_v0")
        self.assertFalse(metrics["usable"])
        self.assertEqual(metrics["reason"], "FEWER_THAN_TWO_FULL_TERM_SAMPLES")
        self.assertEqual(metrics["rows_read"], 1)

    def test_trailing_slope_is_marked_as_not_a_phase_summary(self) -> None:
        # Fall for 40 samples, then rebound for 140 - continuously, inside one
        # driven block - which is what the committed H8 curve actually does.
        rows = ramp(0, 180, 999, 0.05)        # 30.0 -> 21.0 over three minutes
        last = float(rows[-1]["t1_c"])
        for index in range(120):              # +3.6 C rebound at the tail
            value = last + 0.03 * index
            rows.append(row(device_ms=180000 + index * 1000, pwm_applied_permille=999,
                            current_a=7.0, power_w=68.0, energy_wh=round(index * 0.02, 4),
                            t1_c=value, t2_c=30.0 + 0.01 * index, t3_c=value - 0.1,
                            t4_c=value + 0.05))
        metrics = rep.phase_metrics(rows, "cooling", "tmean_airroles_v0")
        self.assertTrue(metrics["trailing_slope_is_not_a_phase_summary"])
        self.assertGreater(metrics["slope_c_per_min"], 0.0)
        self.assertLess(metrics["whole_phase_slope_c_per_min"], 0.0)
        self.assertIn("trailing_window_least_squares_v0", metrics["slope_definition"])
        self.assertIn("whole_phase_least_squares_v0",
                      metrics["whole_phase_slope_definition"])


class StatisticsTests(unittest.TestCase):
    def test_spread_uses_the_sample_formula(self) -> None:
        result = rep.summarize([1.0, 3.0], "delta_c")
        self.assertEqual(result["mean"], 2.0)
        self.assertAlmostEqual(result["sd_sample"], 1.414214, places=6)

    def test_one_run_never_produces_a_spread(self) -> None:
        result = rep.summarize([2.0], "delta_c")
        self.assertIsNone(result["sd_sample"])
        self.assertIn("spread needs at least two runs", result["cv_note"])

    def test_cv_is_undefined_at_a_zero_mean(self) -> None:
        result = rep.summarize([-1.0, 1.0], "delta_c")
        self.assertEqual(result["mean"], 0.0)
        self.assertIsNone(result["cv_pct"])
        self.assertIn("mean is zero", result["cv_note"])

    def test_an_outcome_no_run_produced_is_listed_not_dropped(self) -> None:
        result = rep.summarize([], "minutes_to_2c")
        self.assertEqual(result["status"], "NO_SAMPLES")
        self.assertIn("note", result)

    def test_insufficient_runs_says_how_many_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            path = pathlib.Path(workdir) / "one.csv"
            write_capture(path, ramp(0, 20, 0, -0.01) + ramp(20000, 40, 999, 0.05)
                          + ramp(60000, 20, 0, -0.05))
            report = rep.analyze([path], "tmean_airroles_v0", 3)
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
            report = rep.analyze(paths, "tmean_airroles_v0", 3)
        verdict = report["phases"]["cooling"]["verdict"]
        self.assertEqual(verdict["status"], "REPEATABILITY_COMPUTED")
        stats = report["phases"]["cooling"]["statistics"]["delta_c"]
        self.assertEqual(stats["n"], 3)
        self.assertIsNotNone(stats["sd_sample"])
        self.assertIsNotNone(stats["cv_pct"])
        self.assertTrue(report["verdict"]["plant_variation_reportable"])


class RealCaptureTests(unittest.TestCase):
    def test_the_committed_capture_is_present(self) -> None:
        """A skipped-by-default suite once let a missing capture pass unnoticed."""
        self.assertTrue(H8_CAPTURE.is_file(), f"{H8_CAPTURE} must be committed")

    def test_the_committed_run_analyses_in_every_definition(self) -> None:
        reports = {name: rep.analyze([H8_CAPTURE], name, 3) for name in rep.REPRESENTATIONS}
        air = reports["tmean_airroles_v0"]["phases"]["cooling"]["runs"][0]
        literal = reports["tmean_chamber3_v0"]["phases"]["cooling"]["runs"][0]
        self.assertEqual(air["samples"], 600)
        self.assertEqual(air["rows_read"], 600)
        self.assertLess(air["delta_c"], -8.0)
        self.assertGreater(literal["delta_c"], air["delta_c"])
        self.assertEqual(reports["tmean_airroles_v0"]["includes_hot_side"], False)
        self.assertEqual(reports["tmean_all4_v0"]["includes_hot_side"], True)
        self.assertEqual(reports["tmean_airroles_v0"]["verdict"]["cooling_step_runs"],
                         "INSUFFICIENT_RUNS")

    def test_electrical_validity_was_never_recorded_in_the_committed_capture(self) -> None:
        report = rep.analyze([H8_CAPTURE], "tmean_airroles_v0", 3)
        cooling = report["phases"]["cooling"]["runs"][0]
        self.assertFalse(cooling["electrical_status_recorded"])
        self.assertEqual(cooling["current_rows_unqualified"], cooling["rows_read"])

    def test_the_recovery_peak_is_the_single_zero_duty_frame(self) -> None:
        """Named, not averaged: the recovery segment's peak current is suspect."""
        rows = rep.read_rows(H8_CAPTURE)
        suspect = [r for r in rows if r["device_ms"] == "826894"]
        self.assertEqual(len(suspect), 1)
        self.assertEqual(suspect[0]["pwm_applied_permille"], "0")
        self.assertEqual(suspect[0]["current_a"], "7.15")
        self.assertEqual(suspect[0]["current_status"], "")
        report = rep.analyze([H8_CAPTURE], "tmean_airroles_v0", 3)
        recovery = report["phases"]["recovery"]["runs"][0]
        self.assertEqual(recovery["peak_current_a"], 7.15)
        self.assertLess(recovery["mean_current_a"], 1.0)


class OverlayTests(unittest.TestCase):
    def test_overlay_carries_both_time_bases_and_every_definition(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            capture = pathlib.Path(workdir) / "run.csv"
            write_capture(capture, ramp(0, 5, 0, -0.01) + ramp(5000, 30, 999, 0.05))
            reports = [rep.analyze([capture], name, 3)
                       for name in ("tmean_airroles_v0", "tmean_chamber3_v0",
                                    "tmean_t2excluded_v0")]
            out = pathlib.Path(workdir) / "overlay.csv"
            rep.write_overlay_csv(out, reports)
            with out.open(encoding="utf-8") as handle:
                rows = list(csv_module.DictReader(handle))
            raw = out.read_text(encoding="utf-8")
        self.assertEqual(list(rows[0].keys()),
                         ["run", "phase", "representation", "includes_hot_side",
                          "sample_index", "phase_elapsed_min", "boot_elapsed_min",
                          "tmean_c"])
        self.assertEqual({r["representation"] for r in rows},
                         {"tmean_airroles_v0", "tmean_chamber3_v0", "tmean_t2excluded_v0"})
        first = [r for r in rows if r["phase"] == "cooling"][0]
        self.assertEqual(first["phase_elapsed_min"], "0.0")
        self.assertGreater(float(first["boot_elapsed_min"]), 0.0)
        self.assertNotIn("\r", raw)

    def test_the_overlay_series_is_the_series_behind_the_statistics(self) -> None:
        """The report's samples and the overlay rows must be the same points."""
        with tempfile.TemporaryDirectory() as workdir:
            capture = pathlib.Path(workdir) / "run.csv"
            write_capture(capture, ramp(0, 4, 0, -0.01)
                          + [row(device_ms=4000, pwm_applied_permille=999,
                                t1_c="nan", t1_status="INVALID")]
                          + ramp(5000, 8, 999, 0.1))
            report = rep.analyze([capture], "tmean_chamber3_v0", 3)
            rows = rep.overlay_rows([report])
        cooling_rows = [r for r in rows[1:] if r[1] == "cooling"]
        cooling = report["phases"]["cooling"]["runs"][0]
        self.assertEqual(len(cooling_rows), cooling["samples"])
        self.assertEqual(cooling["partial_term_rows"] + cooling["no_term_rows"],
                         cooling["skipped_rows"])


if __name__ == "__main__":
    unittest.main()
