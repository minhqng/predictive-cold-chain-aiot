"""Tests for the W08 hot-side sustainability and fuse evaluation.

These prove the two claims the A-W08-03 / A-W08-02 artifacts publish:

* the hot-side row for the committed 600 s capture is exactly what the CSV says
  (TEC_HOT_SIDE max 39.938 C, margin 15.062 K to the **provisional** 55 C
  ceiling, no continuous rating claimed anywhere), and a session that was never
  run as an endurance test cannot produce a sustainability verdict;
* the fuse evaluation returns NO_FREEZE with the conductor deviation recorded,
  and refuses to justify any candidate from observation alone.

Host analysis of recorded files; no measurement, no certification.
"""

from __future__ import annotations

import functools
import math
import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
REPO = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))

import cg_w08_envelope as env  # noqa: E402
import cg_w08_hot_side as hot  # noqa: E402


@functools.lru_cache(maxsize=1)
def committed_frames() -> list[env.Frame]:
    return env.classify(env.read_h8_csv(REPO / env.H8_CSV, "W04-H8C-box-600s"))


@functools.lru_cache(maxsize=1)
def committed_rows() -> list[hot.HotSideRow]:
    return hot.analyse_all(REPO, None)


@functools.lru_cache(maxsize=1)
def fuse() -> dict[str, object]:
    return hot.fuse_evaluation(hot.observed_currents(REPO, None))


class HotSideSustainability(unittest.TestCase):
    def test_committed_hot_side_row_matches_the_capture(self) -> None:
        row = next(r for r in committed_rows() if r.session == "W04-H8C-box-600s")
        self.assertEqual(row.trust, "COMMITTED")
        self.assertTrue(row.reproducible_from_git)
        self.assertEqual(row.duty_permille, 999)
        self.assertEqual(row.driven_frames, 599)
        self.assertEqual(row.driven_span_s, 598.0)
        self.assertEqual(row.max_c, 39.938)
        self.assertEqual(row.margin_to_provisional_limit_k, 15.062)
        self.assertEqual(row.final_drift_k_per_min, 0.1759)
        self.assertEqual(row.plateau_observed, "FLAT_WITHIN_0P2_K_PER_MIN")
        self.assertEqual(row.verdict, "OBSERVED_SUSTAINED_WITHIN_PROVISIONAL_MARGIN")
        self.assertIn("PROVISIONAL", row.caveats)
        self.assertIn("never averaged", row.caveats)

    def test_the_provisional_ceiling_is_never_a_rating(self) -> None:
        self.assertEqual(hot.PROVISIONAL_HOT_SIDE_LIMIT_C, 55.0)
        self.assertEqual(hot.HOT_SIDE_LIMIT_STATUS, "PROVISIONAL_NOT_A_RATING")
        self.assertFalse(hot.CONTINUOUS_RATING_CLAIMED)
        for row in committed_rows():
            self.assertLess(row.max_c, hot.PROVISIONAL_HOT_SIDE_LIMIT_C)

    def test_only_endurance_sessions_may_carry_a_sustainability_result(self) -> None:
        self.assertFalse(hot._sustainability_session("H7-60pct"))
        self.assertFalse(hot._sustainability_session("W04-H6-10pct"))
        self.assertTrue(hot._sustainability_session("W04-H8C-box-600s"))
        self.assertTrue(hot._sustainability_session("H8-E-1800s"))
        for row in committed_rows():
            if row.session.startswith("H7"):
                self.assertEqual(
                    row.verdict, "NOT_A_SUSTAINABILITY_RESULT_ELECTRICAL_ONLY_IMAGE",
                    "the H7 stages ran the electrical-only image")
                self.assertIn("not run as a hot-side endurance test", row.caveats)

    def test_hot_side_channel_and_role_are_pinned(self) -> None:
        self.assertEqual(hot.HOT_SIDE_CHANNEL, "t2")
        self.assertEqual(hot.AS_BUILT_ROLES, {
            "t1": "CHAMBER_CENTER", "t2": "TEC_HOT_SIDE",
            "t3": "CHAMBER_BOTTOM", "t4": "CHAMBER_NEAR_DOOR"})
        # ROM ids are by-source, never a readback, so the module says so.
        self.assertEqual(hot.ROM_BY_CHANNEL["t2"], "28AEBF2200000006")

    def test_rendered_csv_publishes_the_honest_flags(self) -> None:
        text = hot.render_thermal_csv(committed_rows())
        header, *rows = text.splitlines()
        self.assertIn("continuous_rating_claimed", header)
        self.assertIn("margin_to_provisional_limit_k", header)
        self.assertIn("limit_status", header)
        self.assertTrue(rows, "no thermal rows rendered")
        for line in rows:
            self.assertIn("PROVISIONAL_NOT_A_RATING", line)
            self.assertIn(",false,", "," + line + ",")
        self.assertNotIn(env.FORBIDDEN_STATUS, text)


class FuseAndConductorEvaluation(unittest.TestCase):
    def test_verdict_is_no_freeze(self) -> None:
        self.assertEqual(fuse()["verdict"], "NO_FREEZE")
        self.assertEqual(fuse()["status_label"], "BLOCKED_HARDWARE")
        self.assertEqual(
            fuse()["gate_a_pass_criterion_safe_physical_envelope_known"], "NOT_MET")

    def test_no_candidate_is_justified_by_observation_alone(self) -> None:
        table = fuse()["fuse"]["decision_table"]
        self.assertEqual([row["candidate_a"] for row in table], [10, 15, 20])
        for row in table:
            self.assertFalse(row["justified_by_observation_alone"])
            self.assertIn("ampacity", row["why_not"])
        # The 10 A candidate sits 0.01 A above the observed committed peak.
        ten = table[0]
        self.assertEqual(ten["headroom_over_observed_peak_a"], 0.01)

    def test_conductor_deviation_is_recorded_not_re_derived(self) -> None:
        conductor = fuse()["conductor"]
        # Operator correction 2026-11-02: the recorded "1.75" is the copper core
        # DIAMETER in mm, so the cross-section is derived from it, not asserted.
        self.assertEqual(conductor["recorded_figure"], "1.75")
        self.assertEqual(conductor["core_diameter_mm"], 1.75)
        self.assertEqual(conductor["installed_mm2"], 2.405)
        self.assertAlmostEqual(round(math.pi * (1.75 / 2) ** 2, 3), 2.405)
        self.assertEqual(conductor["area_gap_vs_canonical_pct"], 3.8)
        self.assertIn("unit error", conductor["recorded_unit_error_corrected"])
        self.assertIn("stranded", conductor["shape_assumption"])
        self.assertIn("derived", conductor["installed_mm2_basis"])
        self.assertFalse(conductor["nominal_canonical_compliance_claimed"])
        self.assertIn("2.405", conductor["termination_in_range"])
        self.assertIn("fit", conductor["termination_in_range"])
        self.assertIn("corrected", conductor["provenance"])
        self.assertEqual(conductor["canonical_ask"], "2 x 2.5 mm2")
        self.assertTrue(conductor["deviation_open"])
        self.assertEqual(conductor["status_label"], "TEAM_DEPENDENCY")
        self.assertFalse(conductor["insulation_class_recorded"])
        self.assertFalse(conductor["run_length_recorded"])
        self.assertIn("HW-19", conductor["deviation_register"])
        fuse_block = fuse()["fuse"]
        self.assertFalse(fuse_block["marking_photographed"])
        self.assertFalse(fuse_block["legible_on_installed_body"])
        self.assertFalse(fuse_block["suitability_proven"])
        self.assertEqual(fuse_block["installed_reported_a"], 15.0)
        self.assertIn("operator-reported", fuse_block["value_basis"])
        self.assertIn("catalogue", fuse_block["catalogue_is_not_installed_evidence"])

    def test_generated_note_states_the_conductor_unit_error_and_limits(self) -> None:
        """The corrected conductor record and the fuse-evidence limits are published.

        Both are the kind of statement a later edit can quietly smooth into a
        pass, so they are asserted as text, not only as dict fields.
        """
        text = hot.render_fuse_md(fuse())
        self.assertIn("unit error", text)
        self.assertIn("2.405 mm2", text)
        self.assertIn("round solid", text)
        self.assertIn("stranded", text)
        self.assertIn("3.8 %", text)
        self.assertIn("HW-19 stays UNVERIFIED", text)
        self.assertIn("operator-reported only", text)
        self.assertIn("catalogue entry is not evidence", text)
        # The old unit-error wording must not survive anywhere in the note.
        self.assertNotIn("1.75 mm2 branch", text)
        self.assertNotIn("Ampacity basis for 1.75 mm2", text)
        self.assertNotIn("nominal 2.5 mm2 compliance is claimed and", text)

    def test_observed_loads_are_the_committed_peak_and_flagged_unqualified(self) -> None:
        currents = hot.observed_currents(REPO, None)
        committed = {row["session"]: row for row in currents
                     if row["trust"] == "COMMITTED"}
        self.assertEqual(committed["W04-H8C-box-600s"]["current_max_a"], 9.99)
        self.assertEqual(committed["W04-H8C-box-600s"]["current_median_a"], 7.16)
        self.assertFalse(committed["W04-H8C-box-600s"]["electrical_status_recorded"])
        self.assertEqual(committed["W04-H6-10pct"]["duty_permille"], 100)
        self.assertEqual(committed["W04-H6-10pct"]["current_median_a"], 0.96)
        self.assertEqual(fuse()["observed"]["peak_current_committed_a"], 9.99)

    def test_off_gate_is_quoted_as_a_bench_field_not_a_canonical_limit(self) -> None:
        gate = fuse()["bench_off_gate"]
        self.assertEqual(gate["limit_a"], 0.2)
        self.assertIn("not a canonical limit", gate["provenance"])
        self.assertEqual(gate["observed_steady_off_max_a"], 0.02)

    def test_generated_note_separates_observed_from_recommended(self) -> None:
        text = hot.render_fuse_md(fuse())
        for heading in ("## 2. What was observed", "## 5. Recommended versus observed",
                        "## 6. Verdict"):
            self.assertIn(heading, text)
        self.assertIn("NO_FREEZE", text)
        # The corrected record replaces the unit-error wording outright.
        self.assertIn("2.405 mm2", text)
        self.assertNotRegex(text.replace("²", ""), r"1\.75\s*mm2")
        self.assertIn("Not claimed:", text)
        self.assertIn("BLOCKED_HARDWARE", text)
        self.assertNotIn("compliance is met", text)
        assert_only_denies_physical_claim(self, text)


NEGATIONS = ("not", "never", "no ", "without", "refus", "forbid", "false", "none")


def assert_only_denies_physical_claim(case: unittest.TestCase, text: str) -> None:
    """A physical label may appear only inside a sentence that denies it."""
    for line in text.splitlines():
        if env.FORBIDDEN_STATUS in line:
            case.assertTrue(any(n in line.lower() for n in NEGATIONS),
                            f"asserted a physical claim: {line[:100]!r}")


class NoSilentAveraging(unittest.TestCase):
    def test_holdover_frame_never_enters_a_mean(self) -> None:
        drive = env.drive_stats(committed_frames())
        off = env.off_stats(committed_frames())
        # The mean over 600 frames (with the pre-run zero) and over 599 frames
        # are both published; the 7.15 A duty-0 repeat is in neither.
        self.assertEqual(drive["mean_current_a_excluding_holdovers"], 7.2367)
        self.assertEqual(drive["mean_current_a_inclusive_of_holdovers"], 7.2247)
        self.assertLess(off["steady_max_current_a"], 7.15)

    def test_rows_to_render_carry_no_physical_claim(self) -> None:
        # The CSV may never mention the token at all; the markdown may mention it
        # only to deny it.
        csv_text = hot.render_thermal_csv(committed_rows())
        self.assertNotIn(env.FORBIDDEN_STATUS, csv_text)
        assert_only_denies_physical_claim(self, hot.render_fuse_md(fuse()))


if __name__ == "__main__":
    unittest.main()
