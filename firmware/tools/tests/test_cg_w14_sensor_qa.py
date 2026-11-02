"""Tests for cg_w14_sensor_qa.py (A-W14-01 sensor-position QA).

The defect this file has to make impossible is a sentence: "no movement verified".
Everything archived data can say is that labels and behaviour still match a frozen
record, so the tests plant each kind of mismatch and require the tool to name it,
while requiring the honest split between CURRENT-VERIFIABLE, NEEDS-A-NEW-CAPTURE and
NEEDS_PHYSICAL_EVIDENCE to survive every path.
"""

from __future__ import annotations

import csv as csv_module
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_thermal_repeatability as rep  # noqa: E402
import cg_w14_sensor_qa as qa  # noqa: E402
import cg_w14_spatial as sp  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[3]
H8_CAPTURE = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"

BASE_COLUMNS = {
    "device_ms": "0", "pwm_applied_permille": "0", "state": "OFF", "boot_id": "aaaaaaaa",
    "session": "H8 box-cooling 600 s", "stage": "H8-C", "door_open": "0",
    "door_polarity": "CONFIRMED", "current_a": "7.0", "current_status": "OK",
    "voltage_v": "12.0", "voltage_status": "OK", "power_w": "84.0", "energy_wh": "1.0",
    "t1_c": "30.0", "t1_status": "OK", "t1_role": "UNASSIGNED",
    "t2_c": "30.0", "t2_status": "OK", "t2_role": "HOT_SIDE",
    "t3_c": "29.6", "t3_status": "OK", "t3_role": "UNASSIGNED",
    "t4_c": "30.3", "t4_status": "OK", "t4_role": "UNASSIGNED",
}


def row(**fields) -> dict[str, str]:
    merged = dict(BASE_COLUMNS)
    merged.update({key: str(value) for key, value in fields.items()})
    return row_str(merged)


def row_str(merged: dict[str, str]) -> dict[str, str]:
    return merged


def write_capture(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv_module.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def session(start_ms: int, count: int, boot: str, off_count: int = 20) -> list[dict[str, str]]:
    """Baseline shape: a passive block, then air falling while the hot side rises."""
    rows = []
    for index in range(off_count):
        rows.append(row(device_ms=start_ms + index * 1000, boot_id=boot,
                        pwm_applied_permille=0,
                        t1_c=30.0, t2_c=30.0, t3_c=29.6, t4_c=30.3))
    driven = off_count
    for index in range(count):
        step = driven + index
        rows.append(row(device_ms=start_ms + step * 1000, boot_id=boot,
                        state="COOLING", pwm_applied_permille=999,
                        t1_c=30.0 - 0.02 * index, t2_c=30.0 + 0.03 * index,
                        t3_c=29.6 - 0.015 * index, t4_c=30.3 - 0.025 * index))
    return rows


class RoleLabelCheck(unittest.TestCase):
    def test_real_capture_labels_match_the_frozen_record(self):
        rows = rep.read_rows(H8_CAPTURE)
        check = qa.role_label_check(rows)
        self.assertEqual(check["state"], "MATCH")
        self.assertEqual(check["mismatched_columns"], [])
        self.assertEqual(check["per_column"]["t2_role"]["tokens"], ["HOT_SIDE"])

    def test_a_planted_label_change_is_a_mismatch_and_names_the_consequence(self):
        rows = [row(t2_role="CHAMBER_CENTER") for _ in range(3)]
        check = qa.role_label_check(rows)
        self.assertEqual(check["state"], "MISMATCH")
        self.assertEqual(check["mismatched_columns"], ["t2_role"])
        self.assertIn("different logical geometry", check["meaning_of_a_mismatch"])

    def test_absent_role_column_is_reported_not_guessed(self):
        rows = []
        for source in (row() for _ in range(3)):
            source.pop("t2_role")
            rows.append(source)
        check = qa.role_label_check(rows)
        self.assertEqual(check["state"], "COLUMN_ABSENT")
        self.assertIn("t2_role", check["absent_columns"])

    def test_a_changing_label_within_one_capture_is_a_mismatch(self):
        rows = [row(t3_role="UNASSIGNED"), row(t3_role="HOT_SIDE")]
        self.assertEqual(qa.role_label_check(rows)["mismatched_columns"], ["t3_role"])


class BehaviourSignature(unittest.TestCase):
    def test_real_session_rises_on_exactly_the_hot_side_slot(self):
        rows = rep.read_rows(H8_CAPTURE)
        signature = qa.behaviour_signature(rows)
        self.assertEqual(signature["rising_channel"], ["t2_c"])
        self.assertTrue(signature["consistent_with_hot_side_split"])
        self.assertEqual(signature["per_channel"]["t1_c"]["direction"], "DOWN")
        self.assertEqual(signature["phase_rows"], 600)

    def test_air_triad_spread_never_includes_the_hot_side(self):
        rows = rep.read_rows(H8_CAPTURE)
        signature = qa.behaviour_signature(rows)
        self.assertNotIn("t2_c", qa.AIR_TERMS)
        driven = rep.split_phases(rows)["cooling"]
        want = round(max(
            max(float(r[t]) for t in qa.AIR_TERMS) - min(float(r[t]) for t in qa.AIR_TERMS)
            for r in driven), 4)
        self.assertEqual(signature["air_triad_max_spread_c"], want)
        # the same statistic over all four channels is far larger, so the exclusion
        # is what keeps an air number an air number
        four = round(max(
            max(float(r[t]) for t in rep.AS_BUILT_ROLES)
            - min(float(r[t]) for t in rep.AS_BUILT_ROLES) for r in driven), 4)
        self.assertGreater(four, signature["air_triad_max_spread_c"])

    def test_a_probe_that_left_the_air_gives_a_different_signature(self):
        """Swap the hot-side response onto an air slot: the check must catch it."""
        rows = session(0, 60, "aaaaaaaa")
        for source in rows:
            if (rep.number(source, "pwm_applied_permille") or 0) > 0:
                source["t1_c"], source["t2_c"] = source["t2_c"], source["t1_c"]
        signature = qa.behaviour_signature(rows)
        self.assertFalse(signature["consistent_with_hot_side_split"])
        self.assertIn("t1_c", signature["rising_channel"])

    def test_a_capture_with_no_driven_block_is_refused(self):
        rows = [row(pwm_applied_permille=0) for _ in range(5)]
        with self.assertRaises(rep.AnalysisError):
            qa.behaviour_signature(rows)


class SignatureComparison(unittest.TestCase):
    def test_identical_shape_matches(self):
        base = qa.behaviour_signature(session(0, 60, "aaaaaaaa"))
        cand = qa.behaviour_signature(session(100000, 60, "bbbbbbbb"))
        checks = qa.compare_signatures(base, cand)
        self.assertEqual(checks["hot_side_channel"]["state"], "MATCH")
        self.assertEqual(checks["air_triad_direction"]["state"], "MATCH")
        self.assertEqual(checks["channel_rank_order"]["state"], "MATCH")
        self.assertIn(checks["air_separation"]["state"],
                      ("WITHIN_BASELINE_ORDER", "OUTSIDE_BASELINE_ORDER"))

    def test_hot_side_moving_to_another_slot_is_flagged_with_its_meaning(self):
        base = qa.behaviour_signature(session(0, 60, "aaaaaaaa"))
        rows = session(0, 60, "bbbbbbbb")
        for source in rows:
            if (rep.number(source, "pwm_applied_permille") or 0) > 0:
                source["t3_c"], source["t2_c"] = source["t2_c"], source["t3_c"]
        checks = qa.compare_signatures(base, qa.behaviour_signature(rows))
        self.assertEqual(checks["hot_side_channel"]["state"], "MISMATCH")
        self.assertIn("invalidates the air/hot split",
                      checks["hot_side_channel"]["meaning_if_mismatched"])

    def test_an_air_channel_that_stops_falling_is_flagged(self):
        base = qa.behaviour_signature(session(0, 60, "aaaaaaaa"))
        rows = session(0, 60, "bbbbbbbb")
        for index, source in enumerate(rows):
            if (rep.number(source, "pwm_applied_permille") or 0) > 0:
                source["t4_c"] = str(30.3 + 0.02 * index)
        checks = qa.compare_signatures(base, qa.behaviour_signature(rows))
        self.assertEqual(checks["air_triad_direction"]["state"], "MISMATCH")
        self.assertEqual(checks["air_triad_direction"]["candidate"]["t4_c"], "UP")

    def test_separation_screen_says_it_is_not_a_tolerance(self):
        checks = qa.compare_signatures(qa.behaviour_signature(session(0, 60, "aaaaaaaa")),
                                       qa.behaviour_signature(session(0, 60, "bbbbbbbb")))
        self.assertTrue(checks["air_separation"]["band_is_not_a_tolerance"])
        self.assertIn("one baseline session", checks["air_separation"]["band_basis"])


class HonestSplit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = qa.position_qa(H8_CAPTURE, [H8_CAPTURE])

    def test_the_three_states_are_always_present(self):
        for key in ("CURRENT_VERIFIABLE", "NEEDS_A_NEW_CAPTURE", "NEEDS_PHYSICAL_EVIDENCE"):
            self.assertIn(key, self.report)

    def test_movement_is_never_claimed(self):
        self.assertEqual(self.report["verdict"]["movement_since_freeze"],
                         "NOT_VERIFIABLE_FROM_ARCHIVED_DATA")
        self.assertEqual(self.report["verdict"]["non_movement_status"],
                         "NEEDS_A_NEW_CAPTURE_AND_PHYSICAL_EVIDENCE")

    def test_a_candidate_that_is_the_baseline_says_the_comparison_is_circular(self):
        self.assertEqual(len(self.report["candidates"]), 1)
        self.assertIn("circular", self.report["candidates"][0]["comparison_value"])
        self.assertEqual(self.report["NEEDS_A_NEW_CAPTURE"]["status"], "NO_CANDIDATE_CAPTURE")
        self.assertEqual(self.report["NEEDS_A_NEW_CAPTURE"]["distinct_candidate_sessions"], 0)

    def test_current_verifiable_names_the_rom_identity_gap(self):
        text = " ".join(self.report["CURRENT_VERIFIABLE"]["statements_this_does_not_support"])
        self.assertIn("no sensor ROM ids", text)
        self.assertIn("tip height", text)

    def test_needs_physical_evidence_points_at_the_photo_still_missing(self):
        items = " ".join(self.report["NEEDS_PHYSICAL_EVIDENCE"]["items"])
        self.assertIn("photo", items)
        self.assertIn("mounting method", items)

    def test_guard_refuses_a_forbidden_claim(self):
        planted = dict(self.report)
        planted["summary"] = ("sensor positions unchanged: no movement verified since "
                              "the freeze")
        with self.assertRaises(rep.AnalysisError):
            qa.guard_no_forbidden_claim(planted)
        qa.guard_no_forbidden_claim(self.report)

    def test_text_guard_blocks_a_bare_assertion_but_allows_a_quoted_one(self):
        """The reports have to discuss these claims; what they may not do is assert one."""
        bare = ("Sensor positions were re-checked against the freeze record and no "
                "movement verified since then.")
        with self.assertRaises(rep.AnalysisError) as caught:
            qa.assert_no_false_claim("scratch.md", bare)
        self.assertIn("no movement verified", str(caught.exception))
        quoted = ("The sentence this tool refuses to print is `\"no movement verified\"`; "
                  "it is never asserted.")
        qa.assert_no_false_claim("scratch.md", quoted)
        labelled = "- physically verified: `False`, host verified: `True`"
        qa.assert_no_false_claim("scratch.md", labelled)

    def test_text_guard_blocks_a_fabricated_tolerance_and_a_fake_distribution(self):
        for text in ("The initial matching tolerance agreed with Member B is 0.5 C.",
                     "Gradient distribution computed from the run-to-run spread.",
                     "One session is enough: the distribution of run-to-run behaviour "
                     "is now established."):
            with self.assertRaises(rep.AnalysisError, msg=text):
                qa.assert_no_false_claim("scratch.md", text)

    def test_every_mismatch_class_has_a_stated_physical_meaning(self):
        for key, text in qa.WHAT_A_MISMATCH_WOULD_MEAN.items():
            self.assertIsInstance(text, str, key)
            self.assertGreater(len(text), 40, key)

    def test_baseline_is_the_frozen_record_not_a_reinterpretation(self):
        baseline = self.report["frozen_baseline"]
        self.assertEqual(baseline["slot_to_position"], dict(rep.AS_BUILT_ROLES))
        self.assertIn("geometry-v1.md", baseline["geometry"])
        self.assertIn("probe-identification-v0.md", baseline["identification_record"])


class IdentificationStillExcluded(unittest.TestCase):
    def test_a_capture_under_probe_identification_is_refused(self):
        ident = REPO / "evidence" / "A" / "W07" / "probe-identification" / "baseline.log"
        self.assertEqual(sp.capture_class(ident, []), sp.IDENTIFICATION_MARKER)

    def test_position_qa_refuses_an_identification_session(self):
        rows = [row(session="PROBE_IDENTIFICATION label=touch_1") for _ in range(30)]
        rows += session(0, 30, "ffffffff")
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "ident.csv"
            write_capture(path, rows)
            with self.assertRaises(rep.AnalysisError):
                qa.position_qa(path, [path])

    def test_a_real_candidate_from_a_new_boot_is_counted_as_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = pathlib.Path(tmp) / "baseline.csv"
            candidate = pathlib.Path(tmp) / "candidate.csv"
            write_capture(baseline, session(0, 60, "aaaaaaaa"))
            write_capture(candidate, session(0, 60, "bbbbbbbb"))
            report = qa.position_qa(baseline, [candidate])
            self.assertEqual(report["NEEDS_A_NEW_CAPTURE"]["status"], "CANDIDATE_PRESENT")
            self.assertEqual(report["NEEDS_A_NEW_CAPTURE"]["distinct_candidate_sessions"], 1)
            self.assertTrue(report["candidates"][0]["distinct_from_baseline_session"])
            self.assertNotIn("circular", report["candidates"][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
