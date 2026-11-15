"""Tests for the W05 1 Hz timing study analyzer (A-W05-03).

Two of these read a file that is already committed: the 60-second W04 G1
capture. That is deliberate. The analyzer's numbers must reproduce against real
device bytes, not only against a synthetic line, and the W05 pilot result in
``evidence/A/W05/`` is produced by this tool on that capture. The capture is a
W04 stream - schema 1, no producer sequences - and the tests assert that the
analyzer reports the missing W05 fields as absent rather than as clean.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
TESTS = pathlib.Path(__file__).resolve().parent
REPO = TOOLS.parent.parent

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TESTS))

import cg_timing_analysis as timing  # noqa: E402
from test_cg_telemetry_w05 import W04_CAPTURE, harness_fixture_line, v2_line  # noqa: E402


class RealCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = timing.analyse(W04_CAPTURE)

    def test_it_measures_the_committed_w04_stream(self) -> None:
        cadence = self.report["cadence"]
        self.assertEqual(cadence["accepted_frames"], 62)
        self.assertEqual(self.report["capture"]["rejected_lines"], 0)
        self.assertEqual(self.report["verdict"], "MEASURED")
        # The device clock says the run lasted about a minute; do not round that
        # into "60 s" as if it were the configured target.
        self.assertGreater(cadence["duration_ms"], 60_000)
        self.assertLess(cadence["duration_ms"], 62_000)

    def test_measured_gaps_are_reported_not_assumed(self) -> None:
        gaps = self.report["cadence"]["gaps"]
        self.assertEqual(gaps["count"], 61)
        self.assertEqual(gaps["min_ms"], 980)
        self.assertEqual(gaps["max_ms"], 1080)
        self.assertAlmostEqual(gaps["mean_ms"], 1001.279, places=3)
        # A 1 Hz stream that only ever had one spacing value would be suspicious:
        # the 100 ms control tick quantizes the deadline check into two spacings,
        # and the histogram is what makes that visible.
        self.assertGreaterEqual(len(self.report["cadence"]["gap_histogram"]), 2)
        self.assertEqual(self.report["cadence"]["late_frames"], 0)
        self.assertEqual(self.report["cadence"]["nonpositive_gaps"], 0)

    def test_schema_one_capture_reports_absent_w05_measurements(self) -> None:
        """None, not zero: a schema-1 line never carried a seq or a producer
        sequence, so the analyzer cannot claim those checks passed."""
        identity = self.report["identity"]
        self.assertEqual(identity["seq_frames"], 0)
        self.assertIsNone(identity["seq_duplicate_count"])
        self.assertIsNone(identity["seq_missing"])
        producers = self.report["producers"]
        self.assertIsNone(producers["thermal_repeat_frames"])
        self.assertIsNone(producers["power_longest_repeat_run"])

    def test_token_tally_covers_the_status_fields_that_exist(self) -> None:
        tally = self.report["token_tally"]
        self.assertIn("current_status", tally)
        self.assertNotIn("quality", tally, "a schema-1 capture has no quality token")


class SyntheticStreamTests(unittest.TestCase):
    def test_steady_schema_two_stream(self) -> None:
        lines = [v2_line(uptime_ms=1000 + 1000 * i, seq=i + 1) for i in range(12)]
        report = timing.analyse(lines)
        self.assertEqual(report["verdict"], "MEASURED")
        self.assertEqual(report["cadence"]["gaps"]["max_ms"], 1000)
        # 12 frames spanning 11 s is 1.0 Hz. Reporting 12/11 would be an
        # off-by-one that makes a compliant stream look faster than it is.
        self.assertAlmostEqual(report["cadence"]["frames_per_second"], 1.0, places=4)
        self.assertEqual(report["identity"]["seq_duplicate_count"], 0)
        self.assertEqual(report["identity"]["seq_missing"], 0)

    def test_duplicate_and_missing_seq_are_counted(self) -> None:
        lines = [v2_line(uptime_ms=1000 * (i + 1), seq=i + 1) for i in range(6)]
        report = timing.analyse(lines + [v2_line(uptime_ms=7000, seq=4)])
        self.assertEqual(report["identity"]["seq_duplicate_count"], 1)
        self.assertEqual(report["identity"]["seq_duplicates"], [4])

        # A frame that was refused by the line budget consumed its seq, leaving a
        # hole the report must name instead of smoothing over.
        report = timing.analyse(lines + [v2_line(uptime_ms=9000, seq=9)])
        self.assertEqual(report["identity"]["seq_missing"], 2)

    def test_late_early_and_backwards_frames_are_flagged(self) -> None:
        lines = [
            v2_line(uptime_ms=1000, seq=1),
            v2_line(uptime_ms=2000, seq=2),
            v2_line(uptime_ms=3600, seq=3),  # 1600 ms: late
            v2_line(uptime_ms=4200, seq=4),  # 600 ms: early
            v2_line(uptime_ms=4200, seq=5),  # 0 ms: not a forward step
        ]
        report = timing.analyse(lines)
        self.assertEqual(report["cadence"]["late_frames"], 1)
        self.assertEqual(report["cadence"]["early_frames"], 1)
        self.assertEqual(report["cadence"]["nonpositive_gaps"], 1)

    def test_stalled_producer_is_measured(self) -> None:
        lines = []
        for index in range(8):
            thermal_seq = 1 if index >= 2 else index + 1  # stops advancing
            lines.append(v2_line(uptime_ms=1000 * (index + 1), seq=index + 1,
                                 thermal_seq=thermal_seq, power_seq=index + 1))
        report = timing.analyse(lines)
        # [1, 2, 1, 1, 1, 1, 1, 1]: five frames carried the previous thermal
        # sequence in a row, i.e. the thermal producer stopped publishing while
        # the stream kept running.
        self.assertEqual(report["producers"]["thermal_repeat_frames"], 5)
        self.assertEqual(report["producers"]["thermal_longest_repeat_run"], 5)
        self.assertEqual(report["producers"]["power_repeat_frames"], 0)

    def test_quality_tally_is_reported(self) -> None:
        lines = [v2_line(seq=1), v2_line(seq=2, quality="INVALID", thermal_quality="INVALID"),
                 v2_line(seq=3, quality="DEGRADED", thermal_quality="DEGRADED")]
        report = timing.analyse(lines)
        self.assertEqual(report["token_tally"]["quality"],
                         {"UNKNOWN": 1, "INVALID": 1, "DEGRADED": 1})

    def test_short_capture_is_insufficient_not_characterised(self) -> None:
        report = timing.analyse([v2_line(), v2_line(seq=2)])
        self.assertIn("INSUFFICIENT_EVIDENCE", report["verdict"])
        self.assertIsNone(report["cadence"]["frames_per_second"])

    def test_saturated_age_is_counted_as_clock_skew_not_as_an_age(self) -> None:
        """The firmware writes 2^64-1 when an observation is timestamped after the
        frame clock. Averaging that into the age distribution would be worse than
        dropping the row, so it is reported as its own condition."""
        sentinel = 18446744073709551615
        lines = [v2_line(uptime_ms=1000 * (i + 1), seq=i + 1) for i in range(11)]
        lines.append(v2_line(uptime_ms=12000, seq=12, door_age_ms=sentinel))
        report = timing.analyse(lines)
        self.assertEqual(report["clock_skew_frames"], 1)
        self.assertEqual(report["cadence"]["accepted_frames"], 12)

    def test_clean_capture_reports_zero_clock_skew(self) -> None:
        lines = [v2_line(uptime_ms=1000 * (i + 1), seq=i + 1) for i in range(12)]
        self.assertEqual(timing.analyse(lines)["clock_skew_frames"], 0)

    def test_rejected_lines_are_kept_with_reasons(self) -> None:
        lines = [v2_line(), "ESP-ROM:esp32s3", v2_line(quality="GOOD")]
        report = timing.analyse(lines)
        self.assertEqual(report["capture"]["ignored_lines"], 1)
        self.assertEqual(report["capture"]["rejected_lines"], 1)
        self.assertIn("quality", report["capture"]["reject_reasons"][0])


class PercentileTests(unittest.TestCase):
    def test_nearest_rank_without_interpolation(self) -> None:
        self.assertEqual(timing._percentile([1, 2, 3, 4], 0.95), 4.0)
        self.assertEqual(timing._percentile([5], 0.5), 5.0)
        self.assertIsNone(timing._percentile([], 0.5))


class CliTests(unittest.TestCase):
    def test_jitter_csv_and_json_are_written(self) -> None:
        lines = [v2_line(uptime_ms=1000 * (i + 1), seq=i + 1) for i in range(12)]
        with tempfile.TemporaryDirectory(prefix="cg-timing-") as tmp:
            work = pathlib.Path(tmp)
            capture = work / "capture.log"
            capture.write_text("\n".join(lines) + "\n", encoding="utf-8")
            jitter = work / "timing-jitter.csv"
            json_out = work / "report.json"
            code = timing.main([str(capture), "--jitter-csv", str(jitter),
                                "--json", str(json_out)])
            self.assertEqual(code, 0)
            header = jitter.read_text(encoding="utf-8").splitlines()[0].split(",")
            for name in ("seq", "uptime_ms", "gap_ms", "thermal_seq", "quality", "health"):
                self.assertIn(name, header)
            self.assertEqual(len(jitter.read_text(encoding="utf-8").splitlines()), 13)
            self.assertIn('"verdict": "MEASURED"', json_out.read_text(encoding="utf-8"))

    def test_derived_files_use_lf_even_on_windows(self) -> None:
        """A CRLF in a committed derived CSV changes its SHA-256 between
        checkouts, which would break the evidence pins."""
        lines = [v2_line(uptime_ms=1000 * (i + 1), seq=i + 1) for i in range(12)]
        with tempfile.TemporaryDirectory(prefix="cg-timing-") as tmp:
            work = pathlib.Path(tmp)
            capture = work / "capture.log"
            capture.write_text("\n".join(lines) + "\n", encoding="utf-8")
            jitter = work / "timing-jitter.csv"
            timing.main([str(capture), "--jitter-csv", str(jitter)])
            self.assertNotIn("\r", jitter.read_bytes().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
