"""Durable tests for the W08 observed-envelope analyzer (firmware/tools/cg_w08_envelope.py).

These assert stable properties and rule behaviour, not this week's row counts.
Two classes deliberately read the frozen committed capture (so a statistic can
never silently drift against real device bytes) and one class drives synthetic
FRAMES - labelled fixtures - to prove each register-latency rule actually fires
and fails when the rule is inverted.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
TESTS = pathlib.Path(__file__).resolve().parent
REPO = TOOLS.parent.parent

sys.path.insert(0, str(TOOLS))

import cg_w08_envelope as env  # noqa: E402


def fixture_frame(**kwargs) -> env.Frame:
    """A synthetic frame. It is a unit-test fixture, never a measurement."""
    frame = env.Frame(source=kwargs.pop("source", "FIXTURE"))
    for name, value in kwargs.items():
        setattr(frame, name, value)
    return frame


class RealCaptureReproducibility(unittest.TestCase):
    """Numbers recomputed from the committed 600 s H8 capture, which is git-pinned."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.envelope = env.build_envelope(REPO, None, transport=False)
        cls.h8 = cls.envelope["sources"]["W04-H8C-box-600s"]

    def test_source_is_committed_and_single_boot(self) -> None:
        self.assertEqual(self.h8["trust"], "COMMITTED")
        # A pinned file reproduces exactly; a clean checkout must agree.
        self.assertEqual(self.h8["frames"], 957)

    def test_committed_current_voltage_have_no_validity_token(self) -> None:
        # The established finding: the derived CSV's current/voltage status cells
        # are empty and it has no power/energy/door status column, so its V/I/P
        # figures are unqualified. Assert the property, not a fixed count.
        cov = self.h8["status_coverage"]
        self.assertFalse(cov["electrical_status_recorded"])
        self.assertIn("current", cov["unqualified_columns"])
        self.assertIn("voltage", cov["unqualified_columns"])

    def test_flagged_duty_zero_frame_is_named_not_averaged(self) -> None:
        frames = [f for f in self.envelope["duty_zero_with_current_frames"]
                  if f["source"] == "W04-H8C-box-600s"
                  and f["clock_ms"] == 826894.0]
        self.assertEqual(len(frames), 1, "the 826894 / 7.15 A frame must appear exactly once")
        row = frames[0]
        self.assertEqual(row["current_a"], 7.15)
        self.assertEqual(row["classification"], "OUTPUTS_OFF_REGISTER")
        self.assertFalse(row["electrical_status_recorded"],
                         "the frame's current is unqualified; never present it as verified")


class RegisterLatencyRule(unittest.TestCase):
    """Each documented pattern is produced by the rule and disappears when inverted."""

    def test_outputs_off_register_repeat_is_excluded_from_off_envelope(self) -> None:
        driven = fixture_frame(seq="1", clock_ms=1000, duty_applied=999,
                               voltage_v=11.79, current_a=7.15, power_w=84.2)
        off = fixture_frame(seq="2", clock_ms=2000, duty_applied=0,
                            voltage_v=11.79, current_a=7.15, power_w=84.2)
        classified = env.classify([driven, off])
        self.assertEqual(classified[0].classification, env.DRIVEN)
        self.assertEqual(classified[1].classification, env.OFF_HOLD)
        stats = env.off_stats(classified)
        # The register-repeat frame must NOT enter the steady OFF envelope.
        self.assertEqual(stats["steady_frames_used"], 0)
        self.assertEqual(stats["excluded_register_frames"], 1)

    def test_same_frame_below_floor_becomes_steady_off(self) -> None:
        # Invert the floor condition: the same duty-0 frame with a real zero
        # current is genuine OFF evidence. Proves the floor is what excludes it.
        driven = fixture_frame(seq="1", clock_ms=1000, duty_applied=999,
                               voltage_v=11.9, current_a=7.15, power_w=84.2)
        off = fixture_frame(seq="2", clock_ms=2000, duty_applied=0,
                            voltage_v=11.93, current_a=0.02, power_w=0.2)
        classified = env.classify([driven, off])
        self.assertEqual(classified[1].classification, env.IDLE_OFF)
        self.assertEqual(env.off_stats(classified)["steady_frames_used"], 1)

    def test_pre_run_register_only_first_of_block(self) -> None:
        first = fixture_frame(seq="1", clock_ms=1000, duty_applied=999,
                              voltage_v=0.0, current_a=0.0, power_w=0.0)
        mid = fixture_frame(seq="2", clock_ms=2000, duty_applied=999,
                            voltage_v=11.9, current_a=0.0, power_w=0.0)
        classified = env.classify([first, mid])
        self.assertEqual(classified[0].classification, env.PRE_RUN_HOLD)
        self.assertEqual(classified[1].classification, env.SUSPECT_ZERO)

    def test_holdover_frames_are_listed_individually(self) -> None:
        driven = fixture_frame(seq="1", clock_ms=1000, duty_applied=999,
                               voltage_v=11.79, current_a=7.15, power_w=84.2)
        off = fixture_frame(seq="2", clock_ms=2000, duty_applied=0,
                            voltage_v=11.79, current_a=7.15, power_w=84.2)
        rows = env.holdover_rows(env.classify([driven, off]))
        self.assertTrue(any(r["classification"] == env.OFF_HOLD for r in rows))


class StatisticProperties(unittest.TestCase):
    def test_nearest_rank_percentile_no_interpolation(self) -> None:
        dist = env.distribution([1, 2, 3, 4, 5])
        self.assertEqual(dist["count"], 5)
        self.assertEqual(dist["min"], 1)
        self.assertEqual(dist["max"], 5)
        self.assertEqual(dist["median"], 3)
        # p95 must be an observed value, never an interpolated 4.8.
        self.assertIn(dist["p95"], (1, 2, 3, 4, 5))

    def test_none_values_are_filtered_and_counted_not_assumed_zero(self) -> None:
        dist = env.distribution([None, 2.0, None, 4.0])
        self.assertEqual(dist["count"], 2)
        self.assertEqual(dist["min"], 2.0)
        self.assertEqual(dist["max"], 4.0)

    def test_empty_distribution_reports_count_zero(self) -> None:
        self.assertEqual(env.distribution([]), {"count": 0})


class AccountingInvariant(unittest.TestCase):
    def test_used_plus_excluded_equals_driven_for_every_source(self) -> None:
        for source, summary in self._envelope()["sources"].items():
            drive = summary["drive"]
            self.assertEqual(
                drive["frames_used"] + drive["frames_excluded"],
                drive["driven_frames_in_source"],
                f"{source}: driven frames must be fully accounted for")

    def _envelope(self):
        return env.build_envelope(REPO, None, transport=False)


class ForbiddenStatusGuard(unittest.TestCase):
    def test_no_host_analysis_output_carries_the_physical_label(self) -> None:
        report = env.build_envelope(REPO, None, transport=False)
        self.assertNotIn(env.FORBIDDEN_STATUS, str(report))
        self.assertEqual(report["status_label"], "REAL_DATA_ANALYZED")


class CliSurface(unittest.TestCase):
    def test_renderers_all_run_on_the_committed_envelope(self) -> None:
        report = env.build_envelope(REPO, None, transport=False)
        for render in (env.render_duty_csv, env.render_holdover_csv,
                       env.render_duty_zero_current_csv, env.render_status_coverage_csv,
                       env.render_source_summary_csv, env.render_yaml):
            text = render(report)
            self.assertIsInstance(text, str)
            self.assertTrue(text.strip())

    def test_operating_envelope_yaml_declares_it_is_not_a_certified_limit(self) -> None:
        text = env.render_yaml(env.build_envelope(REPO, None, transport=False))
        self.assertIn("no value here is a limit, a rating, or a permission to energize", text)
        self.assertIn("reproducible_from_git", text)


if __name__ == "__main__":
    unittest.main()
