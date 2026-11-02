"""Tests for cg_reset_criterion.py (A-W07-05).

The point of these tests is the three-way distinction, not the arithmetic: NOT_READY
must mean contradicted evidence, UNKNOWN must mean unmeasurable or unevidenced, and
neither may ever be reported as READY.
"""

from __future__ import annotations

import copy
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_reset_criterion as rc  # noqa: E402
import cg_thermal_repeatability as repeatability  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[3]
SHIPPED = REPO / "evidence" / "A" / "W07" / "reset-criterion-v0.yaml"
H8_CAPTURE = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"

GOOD_STATE = {
    "representation": "tmean_chamber3_v0",
    "tmean_c": 29.9,
    "slope_c_per_min": 0.02,
    "door_state": "CLOSED",
    "cooling_state": "OFF",
    "quality": "VALID",
}


def resolved_criteria() -> dict[str, object]:
    """The shipped candidate with its two open numbers given test values.

    These values exist only here: injecting them proves the evaluator can answer
    READY, and is not a claim that the project has frozen a threshold.
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
            self.assertEqual(status, "UNRESOLVED", name)
            self.assertEqual(value, "UNRESOLVED", name)


class StrictnessTests(unittest.TestCase):
    def bad(self, text: str) -> str:
        with tempfile.TemporaryDirectory() as workdir:
            path = pathlib.Path(workdir) / "c.yaml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(rc.CriteriaError) as caught:
                rc.load_criteria(path)
            return str(caught.exception)

    def test_rejects_unknown_and_duplicate_and_malformed(self) -> None:
        good = SHIPPED.read_text(encoding="utf-8")
        self.assertIn("unknown top-level key", self.bad(good + "\nmystery: 1\n"))
        self.assertIn("duplicate top-level key", self.bad(good.replace(
            "schema: reset-criterion-v0", "schema: reset-criterion-v0\nschema: x", 1)))
        self.assertIn("unparsable line", self.bad("schema reset-criterion-v0\n"))
        self.assertIn("schema", self.bad(good.replace("reset-criterion-v0", "other-v9", 1)))

    def test_rejects_a_missing_parameter_and_a_bogus_status(self) -> None:
        lines = [line for line in SHIPPED.read_text(encoding="utf-8").splitlines()
                 if "sensor_quality_required" not in line
                 and "docs/01 19 (VALID" not in line
                 and "value: VALID" not in line and "status: FROZEN" not in line
                 and "- name: door_required" not in line
                 and "value: CLOSED" not in line and "source: docs/01 17.7" not in line]
        self.assertIn("missing parameters", self.bad("\n".join(lines) + "\n"))
        self.assertIn("bad status", self.bad(SHIPPED.read_text(encoding="utf-8").replace(
            "status: FROZEN", "status: PROBABLY", 1)))

    def test_rejects_a_list_item_outside_parameters(self) -> None:
        self.assertIn("outside", self.bad("schema: reset-criterion-v0\n- name: x\n"))


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

    def test_resolved_and_satisfied_is_ready(self) -> None:
        result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE))
        self.assertEqual(result["verdict"], "READY", result["why"])

    def test_door_open_is_contradicted_not_unmeasurable(self) -> None:
        state = dict(GOOD_STATE, door_state="OPEN")
        result = rc.evaluate(resolved_criteria(), state)
        self.assertEqual(result["verdict"], "NOT_READY")
        self.assertTrue(any("door_state" in item for item in result["failing"]))

    def test_unknown_door_is_not_closed(self) -> None:
        for door in ("UNKNOWN", "", None):
            result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE, door_state=door))
            self.assertEqual(result["verdict"], "UNKNOWN", door)
            self.assertIn("door_state", result["missing_evidence"])

    def test_degraded_quality_is_not_valid(self) -> None:
        result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE, quality="DEGRADED"))
        self.assertEqual(result["verdict"], "NOT_READY")
        result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE, quality="UNKNOWN"))
        self.assertEqual(result["verdict"], "UNKNOWN")

    def test_an_unclassified_cooling_state_is_not_known(self) -> None:
        result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE, cooling_state="STANDBY"))
        self.assertEqual(result["verdict"], "NOT_READY")

    def test_gradient_beyond_the_bound_is_contradicted(self) -> None:
        result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE, slope_c_per_min=0.9))
        self.assertEqual(result["verdict"], "NOT_READY")
        self.assertTrue(any("gradient" in item for item in result["failing"]))

    def test_a_band_judged_against_another_mean_is_contradicted(self) -> None:
        """The open T2 decision cannot be smuggled in through the evidence."""
        state = dict(GOOD_STATE, representation="tmean_t2excluded_v0")
        result = rc.evaluate(resolved_criteria(), state)
        self.assertEqual(result["verdict"], "NOT_READY")
        self.assertTrue(any("criterion names" in item for item in result["failing"]))

    def test_missing_tmean_is_absent_evidence_not_zero(self) -> None:
        result = rc.evaluate(resolved_criteria(), {"door_state": "CLOSED",
                                                  "cooling_state": "OFF",
                                                  "quality": "VALID",
                                                  "slope_c_per_min": 0.0})
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertIn("tmean_c", result["missing_evidence"])

    def test_tmean_above_the_band_is_contradicted(self) -> None:
        result = rc.evaluate(resolved_criteria(), dict(GOOD_STATE, tmean_c=33.5))
        self.assertEqual(result["verdict"], "NOT_READY")


class CaptureAdapterTests(unittest.TestCase):
    @unittest.skipUnless(H8_CAPTURE.is_file(), "the committed H8 cooling capture is absent")
    def test_a_real_cooling_row_reads_as_closed_on_and_valid(self) -> None:
        rows = repeatability.read_rows(H8_CAPTURE)
        cooling = repeatability.split_phases(rows)["cooling"]
        driven = next(row for row in cooling
                      if (repeatability._number(row, "pwm_applied_permille") or 0) > 0)
        state = rc.state_from_capture_row(driven)
        self.assertEqual(state["door_state"], "CLOSED")
        self.assertEqual(state["cooling_state"], "ON")
        self.assertEqual(state["quality"], "VALID")
        self.assertIsInstance(state["tmean_c"], float)

    @unittest.skipUnless(H8_CAPTURE.is_file(), "the committed H8 cooling capture is absent")
    def test_a_row_with_no_identity_reads_as_unknown_not_off(self) -> None:
        state = rc.state_from_capture_row({"door_open": "", "t1_status": "", "t2_status": "",
                                          "t3_status": ""})
        self.assertEqual(state["door_state"], "UNKNOWN")
        self.assertEqual(state["cooling_state"], "UNKNOWN")
        self.assertEqual(state["quality"], "UNKNOWN")

    def test_the_adapter_does_not_smuggle_a_slope(self) -> None:
        """One row cannot show a gradient; a default would fabricate evidence."""
        state = rc.state_from_capture_row({"pwm_applied_permille": "0", "door_open": "0"})
        self.assertIsNone(state["slope_c_per_min"])

    def test_a_partial_mean_is_not_the_full_quantity(self) -> None:
        """docs/01 517-530: a degraded mean must not carry the same label silently."""
        row = {"t1_c": "30.0", "t1_status": "OK", "t2_c": "nan", "t2_status": "INVALID",
               "t3_c": "30.0", "t3_status": "OK", "door_open": "0",
               "pwm_applied_permille": "0"}
        state = rc.state_from_capture_row(row)
        self.assertIsNone(state["tmean_c"])
        self.assertEqual((state["tmean_usable_terms"], state["tmean_term_count"]), (2, 3))


class CliTests(unittest.TestCase):
    def test_the_evaluator_runs_on_the_shipped_file(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            state = pathlib.Path(workdir) / "state.json"
            state.write_text('{"tmean_c": 29.9, "door_state": "CLOSED",'
                             ' "cooling_state": "OFF", "quality": "VALID",'
                             ' "slope_c_per_min": 0.02}', encoding="utf-8")
            code = rc.main([str(SHIPPED), "--state-file", str(state)])
        self.assertEqual(code, 0)

    def test_a_copy_of_the_shipped_file_is_identical_after_a_round_trip(self) -> None:
        first = rc.load_criteria(SHIPPED)
        second = copy.deepcopy(first)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
