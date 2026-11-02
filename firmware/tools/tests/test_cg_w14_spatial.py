"""Tests for cg_w14_spatial.py (A-W14-02 ablation support, A-W14-03 spatial statistics).

What is under test is not arithmetic - it is the four ways this module could quietly
lie: a hot-side surface counted as chamber air, one session's samples described as a
distribution, a disturbance that was never applied given an estimated response, and a
local helper drifting from the W07 definitions it is supposed to reuse.
"""

from __future__ import annotations

import csv as csv_module
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_thermal_repeatability as rep  # noqa: E402
import cg_w14_spatial as sp  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[3]
H8_CAPTURE = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"

BASE_COLUMNS = {
    "device_ms": "0", "pwm_applied_permille": "0", "current_a": "0.0",
    "current_status": "OK", "voltage_v": "12.0", "voltage_status": "OK",
    "power_w": "0.0", "energy_wh": "0", "door_open": "0", "door_polarity": "CONFIRMED",
    "state": "OFF", "boot_id": "aaaaaaaa", "session": "H8 box-cooling 600 s",
    "stage": "H8-C",
    "t1_c": "30.0", "t1_status": "OK",
    "t2_c": "30.0", "t2_status": "OK",
    "t3_c": "29.5", "t3_status": "OK",
    "t4_c": "30.2", "t4_status": "OK",
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


def segment(start_ms: int, count: int, duty: int, boot: str = "aaaaaaaa"
            ) -> list[dict[str, str]]:
    """Air probes fall while the hot-side surface rises: the rig's real signature."""
    rows = []
    for index in range(count):
        rows.append(row(device_ms=start_ms + index * 1000, pwm_applied_permille=duty,
                        boot_id=boot, state="COOLING" if duty else "OFF",
                        t1_c=30.0 - 0.02 * index, t2_c=30.0 + 0.03 * index,
                        t3_c=29.5 - 0.015 * index, t4_c=30.2 - 0.025 * index))
    return rows


class RoleMapReuse(unittest.TestCase):
    """The role map and definition table are imported; a fork would show up here."""

    def test_hot_side_predicate_agrees_with_w07_flag(self):
        for name in rep.REPRESENTATIONS:
            with self.subTest(name=name):
                self.assertEqual(sp.terms_include_hot_side(rep.terms_of(name)),
                                 rep.includes_hot_side(name))

    def test_air_terms_are_w07_air_roles_excluding_the_hot_side(self):
        self.assertNotIn("t2_c", sp.AIR_TERMS)
        self.assertEqual(set(sp.AIR_TERMS),
                         {t for t in rep.AS_BUILT_ROLES if rep.AS_BUILT_ROLES[t] != "TEC_HOT_SIDE"})
        self.assertFalse(sp.terms_include_hot_side(sp.AIR_TERMS))

    def test_w07_representations_are_imported_not_copied(self):
        for name in rep.REPRESENTATIONS:
            self.assertEqual(sp.VARIANTS[name]["terms"], list(rep.terms_of(name)))
            self.assertEqual(sp.VARIANTS[name]["source"], sp.W07_SOURCE)
            self.assertEqual(sp.VARIANTS[name]["includes_hot_side"],
                             rep.includes_hot_side(name))

    def test_a_map_table_disagreement_refuses_to_build_a_variant(self):
        """W07's flag and the role map are cross-checked, not merely both used."""
        with self.assertRaises(rep.AnalysisError) as caught:
            sp._variant("bogus_v0", ("t1_c", "t2_c"), "test", "multi_probe",
                        w07_flag=False)
        self.assertIn("one of the two is wrong", str(caught.exception))
        built = sp._variant("consistent_v0", ("t1_c", "t2_c"), "test", "multi_probe",
                            w07_flag=True)
        self.assertTrue(built["includes_hot_side"])
        self.assertFalse(built["is_chamber_air"])

    def test_mean_of_terms_equals_w07_tmean_for_every_registered_representation(self):
        """The generic helper must be W07's rule, not a near miss of it."""
        rows = segment(0, 20, 999)
        rows[3]["t3_status"] = "INVALID"
        rows[3]["t3_c"] = ""
        rows[4]["t4_c"] = "nan"
        rows[5]["t1_c"] = ""
        for name in rep.REPRESENTATIONS:
            for index, source in enumerate(rows):
                want = rep.tmean(source, name)
                got = sp.mean_of_terms(source, rep.terms_of(name))
                self.assertEqual(want, got, f"{name} row {index}")

    def test_least_squares_equals_w07_trailing_estimator_on_a_full_window(self):
        points = [(index / 60.0, 30.0 - 0.01 * index) for index in range(60)]
        self.assertAlmostEqual(sp.least_squares(points),
                               rep.trailing_slope_c_per_min(points), places=9)
        self.assertIsNone(sp.least_squares(points[:1]))


class HotSideContainment(unittest.TestCase):
    def test_no_chamber_air_variant_touches_the_hot_side(self):
        for name, variant in sp.VARIANTS.items():
            with self.subTest(name=name):
                if variant["is_chamber_air"]:
                    self.assertNotIn("t2_c", variant["terms"])
                    self.assertFalse(variant["includes_hot_side"])

    def test_hot_side_surface_variant_is_labelled_and_not_air(self):
        variant = sp.VARIANTS["hot_t2_surface_v0"]
        self.assertEqual(variant["terms"], ["t2_c"])
        self.assertTrue(variant["includes_hot_side"])
        self.assertFalse(variant["is_chamber_air"])

    def test_a_chamber_air_label_on_hot_terms_raises_instead_of_computing(self):
        """The exact defect the requirement forbids, planted and required to fail."""
        original = dict(sp.VARIANTS["air_t1_center_v0"])
        sp.VARIANTS["air_t1_center_v0"] = {**original, "terms": ["t1_c", "t2_c"],
                                          "is_chamber_air": True}
        try:
            with self.assertRaises(rep.AnalysisError):
                sp.require_air("air_t1_center_v0")
            with self.assertRaises(rep.AnalysisError):
                sp.variant_phase_metrics(segment(0, 10, 999), "cooling",
                                         "air_t1_center_v0")
        finally:
            sp.VARIANTS["air_t1_center_v0"] = original

    def test_all4_sensitivity_check_is_not_an_ablation_candidate(self):
        self.assertNotIn("tmean_all4_v0", sp.ABLATION_VARIANTS)
        self.assertIn("tmean_all4_v0", sp.VARIANTS)


class RowAccounting(unittest.TestCase):
    def test_partial_term_rows_are_excluded_and_counted(self):
        rows = segment(0, 10, 999)
        rows[4]["t3_c"] = ""
        points, tallies = sp.term_points(rows, ["t1_c", "t3_c"])
        self.assertEqual(len(points), 9)
        self.assertEqual(tallies["partial_term_rows"], 1)
        self.assertEqual(tallies["no_term_rows"], 0)

    def test_non_ok_status_excludes_a_value(self):
        rows = segment(0, 5, 999)
        rows[1]["t1_status"] = "INVALID"
        points, tallies = sp.term_points(rows, ["t1_c"])
        self.assertEqual(len(points), 4)
        self.assertEqual(tallies["no_term_rows"], 1)

    def test_status_free_readings_are_used_but_counted_unqualified(self):
        rows = segment(0, 6, 999)
        for source in rows:
            source.pop("t1_status")
        points, tallies = sp.term_points(rows, ["t1_c"])
        self.assertEqual(len(points), 6)
        self.assertEqual(tallies["unqualified_rows"], 6)


class IdentificationExcluded(unittest.TestCase):
    def test_session_marked_identification_is_refused(self):
        rows = [row(session="PROBE_IDENTIFICATION touch_1") for _ in range(3)]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "ident.csv"
            write_capture(path, rows)
            with self.assertRaises(rep.AnalysisError):
                sp.require_thermal_capture(path, sp.rep.read_rows(path))
            with self.assertRaises(rep.AnalysisError):
                sp.ablation_matrix([path])

    def test_capture_under_the_identification_directory_is_refused(self):
        ident = (REPO / "evidence" / "A" / "W07" / "probe-identification" / "touch_1.log")
        self.assertEqual(sp.capture_class(ident, []), sp.IDENTIFICATION_MARKER)

    def test_real_thermal_capture_is_admitted(self):
        rows = sp.rep.read_rows(H8_CAPTURE)
        admission = sp.require_thermal_capture(H8_CAPTURE, rows)
        self.assertEqual(admission["class"], "THERMAL_RESPONSE")
        self.assertEqual(admission["boot_ids"], ["56044b74"])
        self.assertEqual(admission["independent_sessions"], 1)
        self.assertEqual(admission["rows"], 957)


class SpatialStatistics(unittest.TestCase):
    def test_pair_differences_recomputed_from_the_rows(self):
        rows = segment(0, 12, 999)
        block = sp.pair_agreement(rows, list(sp.AIR_TERMS), "cooling", 1)
        first = rows[0]
        want = round(float(first["t1_c"]) - float(first["t3_c"]), 4)
        label = sp.pair_label("t1_c", "t3_c")
        self.assertAlmostEqual(block["pairs"][label]["min_c"], min(
            round(float(r["t1_c"]) - float(r["t3_c"]), 4) for r in rows), places=4)
        self.assertAlmostEqual(block["pairs"][label]["max_c"], max(
            round(float(r["t1_c"]) - float(r["t3_c"]), 4) for r in rows), places=4)
        self.assertEqual(block["pairs"][label]["n"], 12)
        self.assertEqual(want, 0.5)

    def test_one_session_is_never_called_a_distribution(self):
        rows = segment(0, 30, 999)
        block = sp.pair_agreement(rows, list(sp.AIR_TERMS), "cooling", 1, min_sessions=3)
        for pair in block["pairs"].values():
            self.assertEqual(pair["status"], "SINGLE_SESSION_OBSERVATION")
            self.assertTrue(pair["not_a_distribution"])
            self.assertEqual(pair["independent_sessions"], 1)
            self.assertNotEqual(pair["status"], "DISTRIBUTION")

    def test_the_only_spread_field_is_named_within_session(self):
        """A dispersion number that is not a repeat spread must say so in its own name."""
        rows = segment(0, 30, 999)
        block = sp.pair_agreement(rows, list(sp.AIR_TERMS), "cooling", 1, min_sessions=3)
        for pair in block["pairs"].values():
            self.assertIn("sd_within_session_sample_c", pair)
            self.assertNotIn("sd_repeat_c", pair)
            self.assertNotIn("cv_repeat_pct", pair)
        metrics = sp.variant_phase_metrics(rows, "cooling", "tmean_airroles_v0")
        self.assertIn("sd_within_session_sample_c", metrics)
        self.assertNotIn("sd_repeat_c", metrics)

    def test_three_sessions_change_the_label(self):
        rows = segment(0, 30, 999)
        block = sp.pair_agreement(rows, list(sp.AIR_TERMS), "cooling", 3, min_sessions=3)
        for pair in block["pairs"].values():
            self.assertEqual(pair["status"], "MULTI_SESSION_OBSERVATION")
            self.assertFalse(pair["not_a_distribution"])

    def test_air_pairs_and_surface_pairs_are_read_differently(self):
        rows = segment(0, 20, 999)
        block = sp.pair_agreement(rows, list(rep.AS_BUILT_ROLES), "cooling", 1)
        for label, pair in block["pairs"].items():
            if "TEC_HOT_SIDE" in label:
                self.assertTrue(pair["hot_side_pair"])
                self.assertIn("surface", pair["read_as"])
            else:
                self.assertFalse(pair["hot_side_pair"])
                self.assertIn("air", pair["read_as"])
        # the surface moves opposite to the air, so that separation must be the widest
        air_only = sp.pair_agreement(rows, list(sp.AIR_TERMS), "cooling", 1)
        self.assertGreater(block["max_pairwise_difference_c"],
                           air_only["max_pairwise_difference_c"])

    def test_partial_pair_rows_are_counted_not_guessed(self):
        rows = segment(0, 10, 999)
        rows[3]["t4_status"] = "INVALID"
        series, tallies = sp.pairwise_series(rows, list(sp.AIR_TERMS))
        self.assertEqual(len(series), 9)
        self.assertEqual(tallies["partial_rows"], 1)


class DisturbanceResponse(unittest.TestCase):
    def test_no_open_event_is_not_computable_and_says_why(self):
        rows = segment(0, 40, 999)
        for source in rows:
            source["door_open"] = "UNKNOWN"
        result = sp.disturbance_response(rows, list(sp.AIR_TERMS))
        self.assertEqual(result["status"], "NOT_COMPUTABLE")
        self.assertEqual(result["evidence"]["open_rows"], 0)
        self.assertIn("no door-open transition", result["reason"])
        self.assertTrue(result["what_would_make_it_computable"])

    def test_a_recorded_open_transition_does_compute(self):
        rows = segment(0, 40, 0)
        for index, source in enumerate(rows):
            source["door_open"] = "1" if index >= 20 else "0"
        events = sp.door_events(rows)
        self.assertEqual(len(events), 1)
        result = sp.disturbance_response(rows, list(sp.AIR_TERMS))
        self.assertEqual(result["status"], "COMPUTED_FROM_RECORDED_EVENTS")
        self.assertEqual(result["events"], 1)

    def test_unknowable_door_rows_are_reported_separately(self):
        rows = segment(0, 5, 0)
        rows[0]["door_open"] = "UNKNOWN"
        tokens = sp.disturbance_tokens(rows)
        self.assertEqual(tokens["confirmed_closed_rows"], 4)
        self.assertEqual(tokens["unknowable_rows"], 1)
        self.assertEqual(tokens["open_rows"], 0)

    def test_real_capture_has_no_door_open_event(self):
        rows = rep.read_rows(H8_CAPTURE)
        tokens = sp.disturbance_tokens(rows[:940] + rows[940:])
        self.assertEqual(tokens["open_rows"], 0)
        self.assertEqual(tokens["rows"], 957)


class AblationSupport(unittest.TestCase):
    def test_variants_share_one_conditioning_fingerprint(self):
        rows = segment(0, 20, 999) + segment(20000, 20, 0)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "run.csv"
            write_capture(path, rows)
            report = sp.ablation_matrix([path])
            capture = report["captures"][0]
            fingerprints = {metrics["conditioning_fingerprint"]
                            for block in capture["variants"].values()
                            for metrics in block.values()}
            self.assertEqual(len(fingerprints), 1)
            self.assertEqual(fingerprints, {capture["conditioning_fingerprint"]})

    def test_fingerprint_changes_when_the_duty_changes(self):
        a = sp.conditioning_fingerprint(segment(0, 10, 999))
        b = sp.conditioning_fingerprint(segment(0, 10, 500))
        self.assertNotEqual(a, b)

    def test_each_variant_reads_the_same_rows_per_phase(self):
        rows = segment(0, 30, 999) + segment(30000, 10, 0)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "run.csv"
            write_capture(path, rows)
            report = sp.ablation_matrix([path])
            counts = {name: block["cooling"]["samples"]
                      for name, block in report["captures"][0]["variants"].items()
                      if block.get("cooling", {}).get("usable")}
            self.assertEqual(len(set(counts.values())), 1, counts)

    def test_csv_is_variant_labelled_and_flags_hot_side_per_row(self):
        rows = segment(0, 25, 999) + segment(25000, 5, 0)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "run.csv"
            write_capture(path, rows)
            report = sp.ablation_matrix([path])
            out = pathlib.Path(tmp) / "out.csv"
            sp.write_csv(out, sp.ablation_csv_rows(report))
            with out.open(encoding="utf-8", newline="") as handle:
                data = list(csv_module.DictReader(handle))
            self.assertTrue(data)
            for line in data:
                terms = line["feature_terms"].split(";")
                self.assertEqual(line["includes_hot_side"],
                                 "1" if sp.terms_include_hot_side(terms) else "0")
                self.assertEqual(line["is_chamber_air"],
                                 "0" if sp.terms_include_hot_side(terms) else "1")

    def test_csv_row_count_matches_the_published_samples_exactly(self):
        """The series and the metrics must be the same rows, not a nearest-time proxy."""
        rows = segment(0, 25, 999) + segment(25000, 5, 0)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "run.csv"
            write_capture(path, rows)
            report = sp.ablation_matrix([path])
            counts = {}
            for line in sp.ablation_csv_rows(report)[1:]:
                counts[(line[3], line[2])] = counts.get((line[3], line[2]), 0) + 1
            for name, block in report["captures"][0]["variants"].items():
                for phase, metrics in block.items():
                    if metrics["usable"]:
                        self.assertEqual(counts[(name, phase)], metrics["samples"],
                                         f"{name}/{phase}")

    def test_csv_feature_values_recompute_from_the_row_they_came_from(self):
        rows = segment(0, 15, 999)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "run.csv"
            write_capture(path, rows)
            report = sp.ablation_matrix([path])
            by_device = {row["device_ms"]: row for row in rows}
            header = sp.ablation_csv_rows(report)
            data = header[1:]
            for line in data:
                record = dict(zip(header[0], line))
                if record["variant"] != "air_t1_center_v0":
                    continue
                source = by_device[str(int(float(record["device_ms"])))]
                self.assertAlmostEqual(float(record["feature_c"]), float(source["t1_c"]), 4)

    def test_single_probe_versus_three_air_is_the_headline_comparison(self):
        rows = segment(0, 40, 999) + segment(40000, 10, 0)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "run.csv"
            write_capture(path, rows)
            report = sp.ablation_matrix([path])
            cooling = report["captures"][0]["variants"]
            for name in ("air_t1_center_v0", "air_t3_bottom_v0", "air_t4_near_door_v0",
                         "tmean_airroles_v0"):
                self.assertTrue(cooling[name]["cooling"]["usable"])
                self.assertFalse(cooling[name]["cooling"]["includes_hot_side"])
            self.assertTrue(cooling["hot_t2_surface_v0"]["cooling"]["includes_hot_side"])
            self.assertFalse(cooling["hot_t2_surface_v0"]["cooling"]["is_chamber_air"])
            # the synthetic driven block cools the air and heats the surface: the
            # ablation table must show the two moving in opposite directions
            self.assertLess(cooling["tmean_airroles_v0"]["cooling"]["delta_c"], 0.0)
            self.assertGreater(cooling["hot_t2_surface_v0"]["cooling"]["delta_c"], 0.0)

    def test_outputs_name_captures_repository_relatively(self):
        report = sp.ablation_matrix([H8_CAPTURE])
        self.assertEqual(report["captures"][0]["capture"],
                         "evidence/A/W04/tec-cooling-response-600s.csv")


class RealSessionNumbers(unittest.TestCase):
    """The one session on disk, checked against W07's published figures."""

    @classmethod
    def setUpClass(cls):
        cls.spatial = sp.spatial_report([H8_CAPTURE])
        cls.ablation = sp.ablation_matrix([H8_CAPTURE])

    def test_reuses_w07_deltas_on_the_registered_representations(self):
        air = rep.analyze([H8_CAPTURE], "tmean_airroles_v0", 3)
        cooling = air["phases"]["cooling"]["runs"][0]["delta_c"]
        mine = self.ablation["captures"][0]["variants"]["tmean_airroles_v0"]["cooling"]
        self.assertEqual(mine["delta_c"], cooling)
        self.assertEqual(cooling, -8.7083)

    def test_single_session_is_reported_as_one_session(self):
        self.assertEqual(self.spatial["verdict"]["independent_sessions"], 1)
        self.assertTrue(self.spatial["verdict"]["single_session_observation"])
        self.assertFalse(self.spatial["verdict"]["distribution_computed"])
        self.assertEqual(self.spatial["gradient_distribution"]["status"],
                         "NOT_COMPUTABLE_AS_DISTRIBUTION")
        self.assertFalse(self.spatial["verdict"]["disturbance_response_computed"])

    def test_disturbance_is_not_computable_with_the_reread_tally(self):
        block = self.spatial["disturbance_specific_response"]
        self.assertEqual(block["status"], "NOT_COMPUTABLE")
        evidence = block["per_capture"][0]["evidence"]
        self.assertEqual(evidence["door_open_token_tally"], {"0": 940, "UNKNOWN": 17})
        self.assertEqual(evidence["open_rows"], 0)

    def test_cooling_air_gradient_is_smaller_than_the_surface_separation(self):
        cooling = self.spatial["captures"][0]["phases"]["cooling"]
        self.assertLess(cooling["air_gradient"]["max_pairwise_difference_c"],
                        cooling["phase_max_pairwise_difference_c"])
        self.assertEqual(cooling["air_gradient"]["tallies"]["usable_pairs"], 600)

    def test_hot_side_never_appears_in_an_air_gradient_block(self):
        for capture in self.spatial["captures"]:
            for phase, block in capture["phases"].items():
                if "air_gradient" not in block:
                    continue
                self.assertNotIn("t2_c", block["air_gradient"]["terms"])
                self.assertFalse(block["air_gradient"]["includes_hot_side"])
                self.assertNotIn("t2_c", sp.VARIANTS["tmean_airroles_v0"]["terms"])

    def test_air_roles_are_labelled_from_the_frozen_map(self):
        self.assertEqual(self.spatial["air_roles"],
                         ["CHAMBER_CENTER", "CHAMBER_BOTTOM", "CHAMBER_NEAR_DOOR"])
        self.assertEqual(self.spatial["hot_side_role"], "TEC_HOT_SIDE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
