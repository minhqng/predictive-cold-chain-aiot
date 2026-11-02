"""Tests for cg_reset_criterion.py (A-W07-05).

The property under test is the three-way split, not the arithmetic: NOT_READY means
recorded evidence contradicts a resolved gate, UNKNOWN means the criterion cannot be
measured or the evidence is absent, and neither may ever be reported as READY.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_reset_criterion as rc  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[3]
SHIPPED = REPO / "evidence" / "A" / "W07" / "reset-criterion-v0.yaml"
H8_CAPTURE = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"
DEFINITION = "tmean_airroles_v0"

GOOD_STATE = {
    "representation": DEFINITION,
    "tmean_c": 29.9,
    "slope_c_per_min": 0.02,
    "door_state": "CLOSED",
    "cooling_state": "OFF",
    "quality": "VALID",
}


def resolved_criteria() -> dict[str, object]:
    """The shipped candidate with its two open numbers given test values.

    The values exist only here. Injecting them proves the evaluator can answer
    READY; it is not a claim that the project has frozen a threshold.
    """
    criteria = rc.load_criteria(SHIPPED)
    for entry in criteria["parameters"]:  # type: ignore[index]
        if entry["name"] == "tmean_band_c":
            entry["value"], entry["status"] = "31.0", "PROPOSED"
        if entry["name"] == "gradient_bound_c_per_min":
            entry["value"], entry["status"] = "0.5", "PROPOSED"
    return criteria


class ShippedFileTests(unittest.TestCase):
    def test_the_shipped_candidate_parses_and_names_every_parameter(self) -> None:
        criteria = rc.load_criteria(SHIPPED)
        self.assertEqual(criteria["schema"], rc.CRITERION_SCHEMA)
        names = [entry["name"] for entry in criteria["parameters"]]  # type: ignore[index]
        self.assertEqual(set(names), set(rc.REQUIRED_PARAMETERS))
        for entry in criteria["parameters"]:  # type: ignore[index]
            self.assertIn(entry["status"], rc.STATUS_VOCABULARY)
            self.assertTrue(entry["source"], "a parameter without a source is an opinion")

    def test_the_two_open_numbers_are_declared_open(self) -> None:
        criteria = rc.load_criteria(SHIPPED)
        for name in ("tmean_band_c", "gradient_bound_c_per_min"):
            value, status = rc.parameter(criteria, name)
            self.assertEqual((value, status), ("UNRESOLVED", "UNRESOLVED"), name)

    def test_the_named_mean_excludes_the_hot_side(self) -> None:
        import cg_thermal_repeatability as repeatability
        definition = rc.parameter(rc.load_criteria(SHIPPED), "tmean_definition")[0]
        self.assertEqual(definition, DEFINITION)
        self.assertFalse(repeatability.includes_hot_side(definition))

    def test_the_file_round_trips_through_disk(self) -> None:
        """A format that only parses from memory proves nothing about the artifact."""
        first = rc.load_criteria(SHIPPED)
        with tempfile.TemporaryDirectory() as workdir:
            path = pathlib.Path(workdir) / "copy.yaml"
            path.write_bytes(SHIPPED.read_bytes())
            second = rc.load_criteria(path)
        self.assertEqual(first, second)


class StrictnessTests(unittest.TestCase):
    def test_rejects_unknown_and_duplicate_top_level_keys(self) -> None:
        good = SHIPPED.read_text(encoding="utf-8")
        self.assertIn("unknown top-level key", _bad(good + "\nmystery: 1\n"))
        self.assertIn("duplicate top-level key",
                      _bad(good.replace("schema: reset-criterion-v0",
                                         "schema: reset-criterion-v0\nschema: x", 1)))

    def test_rejects_malformed_line_and_wrong_schema(self) -> None:
        self.assertIn("unparsable line", _bad("schema reset-criterion-v0\n"))
        self.assertIn("schema", _bad(SHIPPED.read_text(encoding="utf-8").replace(
            "reset-criterion-v0", "other-v9", 1)))

    def test_rejects_a_missing_parameter_and_a_bogus_status(self) -> None:
        lines = [line for line in SHIPPED.read_text(encoding="utf-8").splitlines()
                 if "sensor_quality_required" not in line
                 and "docs/01 19 (VALID" not in line
                 and "value: VALID" not in line
                 and "- name: door_required" not in line
                 and "value: CLOSED" not in line
                 and "source: docs/01 17.7" not in line
                 and "status: FROZEN" not in line]
        self.assertIn("missing parameters", _bad("\n".join(lines) + "\n"))
        self.assertIn("bad status", _bad(SHIPPED.read_text(encoding="utf-8").replace(
            "status: FROZEN", "status: PROBABLY", 1)))

    def test_rejects_a_list_item_outside_parameters(self) -> None:
        self.assertIn("outside", _bad("schema: reset-criterion-v0\n- name: x\n"))

    def test_rejects_a_repeated_block(self) -> None:
        """A duplicate block would let an invented value hide an UNRESOLVED one.

        `parameter()` answers the first match, so without this a second
        `tmean_band_c` block could stay UNRESOLVED in the file while the first one
        silently activated a number nobody measured.
        """
        text = SHIPPED.read_text(encoding="utf-8").replace(
            "  # Upper bound on the chamber-air mean",
            "  - name: tmean_band_c\n"
            "    value: 31.0\n"
            "    status: FROZEN\n"
            "    source: injected duplicate\n\n"
            "  # Upper bound on the chamber-air mean", 1)
        self.assertIn("repeated parameter blocks", _bad(text))
        # the shipped file must still load, or a rejection is just noise
        self.assertEqual(rc.parameter(rc.load_criteria(SHIPPED), "tmean_band_c")[1],
                         "UNRESOLVED")

    def test_rejects_a_duplicate_key_inside_one_block(self) -> None:
        self.assertIn("duplicate 'status' inside one parameter block",
                      _bad(SHIPPED.read_text(encoding="utf-8").replace(
                          "    status: PROPOSED\n    source: as-built",
                          "    status: PROPOSED\n    status: FROZEN\n    source: as-built", 1)))

    def test_rejects_a_block_missing_a_required_key(self) -> None:
        self.assertIn("has no 'source'", _bad(SHIPPED.read_text(encoding="utf-8").replace(
            "    source: docs/01 19 (VALID/DEGRADED/INVALID/UNKNOWN;"
            " unknown must not silently become normal)\n", "", 1)))


class VerdictTests(unittest.TestCase):
    def test_unresolved_numbers_can_never_yield_ready(self) -> None:
        result = rc.evaluate(rc.load_criteria(SHIPPED), dict(GOOD_STATE))
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertIn("UNKNOWN is not READY", result["why"])
        self.assertEqual(result["failing"], [])

    def test_every_criterion_unresolved_is_still_not_ready(self) -> None:
        criteria = rc.load_criteria(SHIPPED)
        for entry in criteria["parameters"]:  # type: ignore[index]
            entry["value"], entry["status"] = "UNRESOLVED", "UNRESOLVED"
        result = rc.evaluate(criteria, dict(GOOD_STATE))
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertEqual(len(result["unresolved_parameters"]), len(rc.REQUIRED_PARAMETERS))

    def test_an_unrecognised_status_cannot_activate_a_gate(self) -> None:
        """A hand-built criteria dict must not reach READY through a status string
        the file format would have rejected."""
        criteria = resolved_criteria()
        for entry in criteria["parameters"]:  # type: ignore[index]
            if entry["name"] in ("tmean_band_c", "gradient_bound_c_per_min"):
                entry["status"] = "TRUST_ME"
        result = rc.evaluate(criteria, dict(GOOD_STATE))
        self.assertEqual(result["verdict"], "UNKNOWN")

    def test_resolved_and_satisfied_is_ready(self) -> None:
        result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE))
        self.assertEqual(result["verdict"], "READY", result["why"])

    def test_door_open_is_contradicted_not_unmeasurable(self) -> None:
        result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE, door_state="OPEN"))
        self.assertEqual(result["verdict"], "NOT_READY")
        self.assertTrue(any("door_state" in item for item in result["failing"]))

    def test_unknown_door_is_not_closed(self) -> None:
        for door in ("UNKNOWN", "", None):
            result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE, door_state=door))
            self.assertEqual(result["verdict"], "UNKNOWN", repr(door))
            self.assertIn("door_state", result["missing_evidence"])

    def test_degraded_quality_is_not_valid(self) -> None:
        self.assertEqual(rc.evaluate(resolved_criteria(),
                                     dict(GOOD_STATE, quality="DEGRADED"))["verdict"],
                         "NOT_READY")
        self.assertEqual(rc.evaluate(resolved_criteria(),
                                     dict(GOOD_STATE, quality="UNKNOWN"))["verdict"],
                         "UNKNOWN")

    def test_an_unclassified_cooling_state_is_not_known(self) -> None:
        result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE, cooling_state="STANDBY"))
        self.assertEqual(result["verdict"], "NOT_READY")

    def test_gradient_beyond_the_bound_is_contradicted(self) -> None:
        result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE, slope_c_per_min=0.9))
        self.assertEqual(result["verdict"], "NOT_READY")
        self.assertTrue(any("gradient" in item for item in result["failing"]))

    def test_missing_tmean_is_absent_evidence_not_zero(self) -> None:
        result = rc.evaluate(resolved_criteria(),
                             {"representation": DEFINITION, "door_state": "CLOSED",
                              "cooling_state": "OFF", "quality": "VALID",
                              "slope_c_per_min": 0.0})
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertIn("tmean_c", result["missing_evidence"])

    def test_tmean_above_the_bound_is_contradicted(self) -> None:
        result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE, tmean_c=33.5))
        self.assertEqual(result["verdict"], "NOT_READY")

    def test_a_hot_side_mean_is_refused_not_judged(self) -> None:
        """A band written for the air probes cannot be applied to a mean that
        averages the hot-side surface into it."""
        for wrong in ("tmean_chamber3_v0", "tmean_all4_v0"):
            result = rc.evaluate(rc.load_criteria(SHIPPED), dict(GOOD_STATE,
                                                                representation=wrong))
            self.assertEqual(result["verdict"], "NOT_READY", wrong)
            self.assertTrue(result["failing"], wrong)

        # If the criterion itself were ever pointed at a hot-side mean, the refusal
        # must name that reason instead of falling through to a verdict.
        contaminated = rc.load_criteria(SHIPPED)
        for entry in contaminated["parameters"]:
            if entry["name"] == "tmean_definition":
                entry["value"] = "tmean_chamber3_v0"
        result = rc.evaluate(contaminated, dict(GOOD_STATE,
                                                 representation="tmean_chamber3_v0"))
        self.assertEqual(result["verdict"], "NOT_READY")
        self.assertTrue(any("hot-side" in item for item in result["failing"]),
                        result["failing"])

    def test_a_mismatched_mean_is_contradicted(self) -> None:
        result = rc.evaluate(rc.load_criteria(SHIPPED),
                             dict(GOOD_STATE, representation="tmean_t2excluded_v0"))
        self.assertEqual(result["verdict"], "NOT_READY")
        self.assertTrue(any("criterion names" in item for item in result["failing"]))

    def test_a_state_without_a_named_mean_is_missing_evidence(self) -> None:
        state = dict(GOOD_STATE)
        del state["representation"]
        result = rc.evaluate(resolved_criteria(), state)
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertIn("representation", result["missing_evidence"])


class CaptureAdapterTests(unittest.TestCase):
    def test_a_real_cooling_row_reads_as_closed_on_and_valid(self) -> None:
        import cg_thermal_repeatability as repeatability
        rows = repeatability.read_rows(H8_CAPTURE)
        cooling = repeatability.split_phases(rows)["cooling"]
        driven = next(r for r in cooling
                      if (repeatability.number(r, "pwm_applied_permille") or 0) > 0)
        state = rc.state_from_capture_row(driven, DEFINITION)
        self.assertEqual(state["door_state"], "CLOSED")
        self.assertEqual(state["cooling_state"], "ON")
        self.assertEqual(state["quality"], "VALID")
        self.assertIsInstance(state["tmean_c"], float)
        self.assertEqual(state["representation"], DEFINITION)

    def test_a_row_with_no_identity_reads_as_unknown_not_off(self) -> None:
        state = rc.state_from_capture_row({"door_open": "", "t1_status": "",
                                           "t2_status": "", "t3_status": ""}, DEFINITION)
        self.assertEqual(state["door_state"], "UNKNOWN")
        self.assertEqual(state["cooling_state"], "UNKNOWN")
        self.assertEqual(state["quality"], "UNKNOWN")

    def test_the_adapter_does_not_smuggle_a_slope(self) -> None:
        """One row cannot show a gradient; a default would fabricate evidence."""
        state = rc.state_from_capture_row({"pwm_applied_permille": "0",
                                           "door_open": "0"}, DEFINITION)
        self.assertIsNone(state["slope_c_per_min"])

    def test_a_partial_mean_is_not_the_full_quantity(self) -> None:
        row = {"t1_c": "30.0", "t1_status": "OK", "t2_c": "nan", "t2_status": "INVALID",
               "t3_c": "30.0", "t3_status": "OK", "t4_c": "30.0", "t4_status": "OK",
               "door_open": "0", "pwm_applied_permille": "0"}
        state = rc.state_from_capture_row(row, "tmean_airroles_v0")
        self.assertEqual((state["tmean_usable_terms"], state["tmean_term_count"]), (3, 3))
        row["t4_status"] = "STALE"
        row["t4_c"] = "nan"
        state = rc.state_from_capture_row(row, "tmean_airroles_v0")
        self.assertEqual((state["tmean_usable_terms"], state["tmean_term_count"]), (2, 3))
        self.assertIsNone(state["tmean_c"])


class CliTests(unittest.TestCase):
    def test_the_evaluator_runs_on_the_shipped_file(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            state = pathlib.Path(workdir) / "state.json"
            state.write_text('{"representation": "' + DEFINITION + '", "tmean_c": 29.9,'
                             ' "door_state": "CLOSED", "cooling_state": "OFF",'
                             ' "quality": "VALID", "slope_c_per_min": 0.02}',
                             encoding="utf-8")
            self.assertEqual(rc.main([str(SHIPPED), "--state-file", str(state)]), 0)


def _bad(text: str) -> str:
    with tempfile.TemporaryDirectory() as workdir:
        path = pathlib.Path(workdir) / "c.yaml"
        path.write_text(text, encoding="utf-8")
        try:
            rc.load_criteria(path)
        except rc.CriteriaError as error:
            return str(error)
    return ""


def _load_ok(path: pathlib.Path) -> dict[str, object]:
    return rc.load_criteria(path)


if __name__ == "__main__":
    unittest.main()
