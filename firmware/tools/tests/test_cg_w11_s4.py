"""Tests for cg_w11_s4.py, cg_s4_refusal.py and cg_w11_s3_feasibility.py
(A-W11-01..04).

S4 is the week where an analysis can most easily lie: a command verdict reads like
an outcome, and a harness that reports SAFETY_BLOCKED while the output is live
would look perfectly safe from the ACK alone. Every test here therefore pushes a
promotion attempt through the tool and asserts it is refused, and then asserts
the tooling still states plainly that no device ever received a command.
"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "evidence" / "A" / "W11"))

import cg_w09_capture_parser as cp  # noqa: E402
import cg_w09_fixtures as fx  # noqa: E402
import cg_s4_refusal as ref  # noqa: E402
import cg_w11_s3_feasibility as s3  # noqa: E402
import cg_w11_s4 as s4  # noqa: E402
import validate_w11  # noqa: E402  the dossier's own re-checker, tested as a mechanism

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
W04_CSV = REPO_ROOT / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"
W04_G1_LOG = REPO_ROOT / "evidence" / "A" / "W04" / "g1" / "40-g1-boot-60s.log"


def _command(status="SAFETY_BLOCKED", applied="OFF", desired="ON", duty=900,
             reapplied="0", stages=None, before=None, command_id="C1"):
    ack = {
        "status": status, "reason": "LIMIT_BELOW_MIN", "desired_cooling": desired,
        "desired_duty_permille": duty, "applied_cooling": applied, "reapplied": reapplied,
    }
    return [{
        "command_id": command_id, "ack_boot_id": "fixtureboot", "acks": [ack],
        "stages": stages if stages is not None else ["COMMAND_SEEN", "DEVICE_ACK"],
        "applied_state_before_command": before,
    }]


class LanesAreNeverDerivedFromIntent(unittest.TestCase):
    def test_an_intent_derived_applied_lane_is_refused(self):
        with self.assertRaises(s4.PromotionError):
            s4._lane(s4.APPLIED, {"applied_permille": 900}, s4.INFERRED_FROM_INTENT, True)

    def test_an_intent_derived_electrical_lane_is_refused(self):
        with self.assertRaises(s4.PromotionError):
            s4._lane(s4.ELECTRICAL, {"current_a": 5.0}, s4.INFERRED_FROM_INTENT, True)

    def test_a_missing_lane_is_stated_as_missing(self):
        lane = s4._lane(s4.ELECTRICAL, None, s4.LANE_MISSING, False, "no evidence")
        self.assertIsNone(lane.value)
        self.assertFalse(lane.qualified)

    def test_applied_lane_reads_the_frame_not_the_request(self):
        frame = fx.physical_frames(1, pwm_req=1000, pwm_applied=999, pwm_readback=999)[0]
        lane = s4.applied_lane_from_frame(frame)
        self.assertEqual(lane.source, s4.FRAME_READ)
        self.assertEqual(lane.value["applied_permille"], 999)
        self.assertEqual(lane.value["requested_permille"], 1000)
        self.assertIn("differs from requested", lane.note)

    def test_applied_lane_is_honest_when_duty_matches(self):
        frame = fx.physical_frames(1, pwm_req=0, pwm_applied=0, pwm_readback=0)[0]
        lane = s4.applied_lane_from_frame(frame)
        self.assertIn("observation, not an inference", lane.note)


class ElectricalQualification(unittest.TestCase):
    def test_empty_status_is_not_ok_so_the_lane_is_unqualified(self):
        frame = fx.physical_frames(1, current_a="7.150", current_status="OK")[0]
        frame.values["current_a_status"] = None
        lane = s4.electrical_lane_from_frame(frame)
        self.assertEqual(lane.source, s4.LANE_MISSING)
        self.assertFalse(lane.qualified)
        self.assertIn("candidate observation", lane.note)

    def test_ok_status_qualifies_the_lane(self):
        frame = fx.physical_frames(1, current_a="7.150", current_status="OK")[0]
        lane = s4.electrical_lane_from_frame(frame)
        self.assertEqual(lane.source, s4.FRAME_READ)
        self.assertTrue(lane.qualified)

    def test_stale_status_does_not_qualify(self):
        frame = fx.physical_frames(1, current_status="STALE")[0]
        self.assertFalse(s4.electrical_lane_from_frame(frame).qualified)

    def test_thermal_lane_excludes_the_hot_side(self):
        frame = fx.physical_frames(1, t2=45.0)[0]
        lane = s4.thermal_lane_from_frame(frame)
        self.assertNotIn("t2", lane.value)
        self.assertIn("TEC_HOT_SIDE excluded", lane.note)


class RefusalCannotBecomeAnAction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = fx.physical_frames(4)

    def test_refused_with_applied_off_is_the_s4_signature(self):
        trace = s4.build_s4_trace(self.frames, command_records=_command(applied="OFF"))
        row = trace["commands"][0]
        self.assertTrue(row["refused"])
        self.assertEqual(row["applied_semantics"], "REFUSED_NON_APPLICATION_OBSERVED")

    def test_refused_with_applied_on_is_rejected(self):
        with self.assertRaises(s4.PromotionError) as ctx:
            s4.build_s4_trace(self.frames, command_records=_command(applied="ON"))
        self.assertIn("cannot be presented alongside an applied action", str(ctx.exception))

    def test_refused_with_applied_on_is_allowed_only_when_it_predates_the_command(self):
        trace = s4.build_s4_trace(self.frames, command_records=_command(applied="ON", before="ON"))
        self.assertEqual(
            trace["commands"][0]["applied_semantics"], "REFUSED_PREEXISTING_APPLICATION"
        )

    def test_a_refusal_cannot_reach_electrical_verification(self):
        with self.assertRaises(s4.PromotionError) as ctx:
            s4.build_s4_trace(
                self.frames,
                command_records=_command(stages=["COMMAND_SEEN", "DEVICE_ACK", "ELECTRICAL_VERIFIED"]),
            )
        self.assertIn("never physical verification", str(ctx.exception))

    def test_a_refusal_cannot_reach_thermal_verification(self):
        with self.assertRaises(s4.PromotionError):
            s4.build_s4_trace(
                self.frames,
                command_records=_command(stages=["COMMAND_SEEN", "DEVICE_ACK", "THERMAL_VERIFIED"]),
            )

    def test_an_attributed_applied_action_on_a_refusal_is_rejected(self):
        records = _command(applied="OFF")
        records[0]["applied_action_attributed_to_command"] = True
        with self.assertRaises(s4.PromotionError):
            s4.build_s4_trace(self.frames, command_records=records)

    def test_every_refusal_status_is_covered(self):
        for status in s4.REFUSAL_STATUSES:
            trace = s4.build_s4_trace(self.frames, command_records=_command(status=status))
            self.assertTrue(trace["commands"][0]["refused"], status)

    def test_a_canonical_duplicate_that_applied_again_is_rejected(self):
        with self.assertRaises(s4.PromotionError) as ctx:
            s4.build_s4_trace(
                self.frames,
                command_records=_command(status="DUPLICATE_CANONICAL", reapplied="1"),
            )
        self.assertIn("docs/02 §30.1", str(ctx.exception))

    def test_an_accepted_command_is_not_a_refusal(self):
        trace = s4.build_s4_trace(self.frames, command_records=_command(status="ACCEPTED"))
        self.assertFalse(trace["commands"][0]["refused"])
        self.assertEqual(trace["commands"][0]["applied_semantics"], "NOT_A_REFUSAL")

    def test_no_frames_no_inference(self):
        trace = s4.build_s4_trace(self.frames, command_records=_command())
        row = trace["commands"][0]
        self.assertEqual(row["lanes"][s4.ELECTRICAL]["source"], s4.LANE_MISSING)
        self.assertEqual(row["lanes"][s4.THERMAL]["source"], s4.LANE_MISSING)


class RealCaptureLaneEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")

    def test_requested_applied_and_read_back_are_three_separate_claims(self):
        report = s4.request_applied_divergence(self.frames)
        self.assertEqual(report["frames_where_applied_differs_from_requested"], 600)
        self.assertIn("(1000, 999, 999)", report["distinct_req_applied_readback_tuples"])

    def test_a_cooling_frame_with_no_current_is_found_as_a_candidate(self):
        report = s4.find_command_electrical_disagreements(self.frames)
        candidates = report["no_active_response_candidates"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["seq"], 227)
        self.assertEqual(candidates[0]["pwm_applied_permille"], 999)
        self.assertEqual(candidates[0]["current_a"], 0.0)

    def test_residual_current_after_duty_removal_is_found(self):
        report = s4.find_command_electrical_disagreements(self.frames)
        residual = report["residual_response_candidates"]
        self.assertEqual([r["seq"] for r in residual], [827, 828])
        self.assertEqual(residual[0]["state"], "COOLDOWN")
        self.assertEqual(residual[0]["current_a"], 7.15)

    def test_none_of_those_currents_are_qualified(self):
        # The committed capture's current_status is empty in all 957 rows, so the
        # candidates above can never be certified electrical evidence from it.
        report = s4.find_command_electrical_disagreements(self.frames)
        self.assertEqual(report["qualified_no_active_response"], [])
        self.assertEqual(report["qualified_residual_response"], [])

    def test_a_qualified_capture_would_certify_the_candidate(self):
        frames = fx.physical_frames(2, state="COOLING", pwm_req=1000, pwm_applied=999,
                                    current_a="0.000", current_status="OK")
        report = s4.find_command_electrical_disagreements(frames)
        self.assertEqual(len(report["qualified_no_active_response"]), 2)


class EmptyTraceIsHonest(unittest.TestCase):
    def test_no_commands_is_reported_as_no_commands(self):
        frames = fx.physical_frames(3)
        trace = s4.build_s4_trace(frames)
        self.assertEqual(trace["commands_observed"], 0)
        self.assertEqual(trace["commands"], [])

    def test_the_trace_states_that_no_device_received_a_command(self):
        frames = fx.physical_frames(3)
        trace = s4.build_s4_trace(frames)
        position = trace["physical_s4_position"]
        self.assertEqual(position["status_label"], "NEED_USER_ACTION")
        self.assertFalse(position["device_received_any_command"])
        self.assertTrue(any("no transport" in reason for reason in position["reasons"]))

    def test_a_fixture_trace_is_labelled_non_physical(self):
        frames = fx.fixture_frames(3)
        trace = s4.build_s4_trace(frames, is_physical_measurement=False)
        self.assertFalse(trace["is_physical_measurement"])


class ScoreRunFailsClosedWithoutObservations(unittest.TestCase):
    """A run that observed nothing proved nothing - not even by default."""

    def test_zero_observations_prove_no_leg(self):
        score = ref.score_run([])
        self.assertEqual(score["verdict"], "NO_COMMAND_OBSERVATIONS")
        self.assertEqual(score["legs_never_observed"], list(ref.LEG_ORDER))
        self.assertFalse(score["thermal_non_response_proven"])
        self.assertFalse(score["command_not_equal_to_effect_proven"])
        self.assertFalse(score["s4_run_publishable"])

    def test_a_real_log_without_commands_is_scored_the_same_way(self):
        report = ref.analyze_capture(W04_G1_LOG, is_physical_measurement=True)
        self.assertEqual(report["summary"]["cmdack_lines"], 0)
        self.assertEqual(report["summary"]["attempts"], 0)
        self.assertGreater(report["summary"]["telem_frames"], 0)
        self.assertFalse(report["score"]["thermal_non_response_proven"])
        self.assertFalse(report["score"]["s4_run_publishable"])
        self.assertEqual(
            report["real_data_availability"]["status"], "REAL DATA NOT AVAILABLE"
        )

    def test_an_unnamed_baseline_leaves_the_thermal_leg_undetermined(self):
        # Thermal non-response is a comparison; without a matched healthy baseline
        # it is unmet, never "no change observed" as a positive result.
        legs = {"THERMAL_NON_RESPONSE": ref.classify_thermal_non_response(
            [], record=None, window_ms=None)}
        self.assertEqual(legs["THERMAL_NON_RESPONSE"]["state"], ref.UNDETERMINED)
        self.assertFalse(legs["THERMAL_NON_RESPONSE"]["evidence"]["observation_made"])


class ExcludedRowsAreCountedAndNamed(unittest.TestCase):
    """DoD: every row the comparison does not use is counted under a named reason.

    A silently dropped row is the same defect as a row that was believed: both
    make the published statistic about a different population than the capture.
    Absent and unreadable are excluded under separate names because they are
    separate defects - the first is a source limitation, the second a row defect.
    """

    @staticmethod
    def frame(seq: int, **values) -> cp.Frame:
        provenance = cp.SourceProvenance(
            source_kind="csv_capture", source_path="tests/inline", source_sha256=None,
            line_index=seq, is_physical_measurement=True, run_label="SOME_REAL_RUN",
        )
        return cp.Frame(provenance=provenance,
                        values={"seq": seq, "boot_id": "boot1", **values}, raw="")

    def test_a_frame_with_no_applied_field_is_named_not_dropped(self):
        report = s4.find_command_electrical_disagreements(
            [self.frame(1, current_a=5.0)]
        )
        account = report["row_account"]
        self.assertEqual(account["frames_scanned"], 1)
        self.assertEqual(account["rows_compared"], 0)
        self.assertEqual(
            account["rows_excluded"], {s4.EXCLUDED_APPLIED_FIELD_ABSENT: 1}
        )

    def test_an_unreadable_current_is_excluded_under_its_own_name(self):
        report = s4.find_command_electrical_disagreements(
            [self.frame(1, pwm_applied_permille=999, current_a="7.15")]
        )
        self.assertEqual(
            report["row_account"]["rows_excluded"], {s4.EXCLUDED_CURRENT_NOT_A_NUMBER: 1}
        )

    def test_every_frame_is_compared_or_exactly_one_exclusion(self):
        frames = [
            self.frame(1, pwm_applied_permille=999, current_a=0.0),
            self.frame(2, current_a=1.0),
            self.frame(3, pwm_applied_permille=True, current_a=1.0),
            self.frame(4, pwm_applied_permille=0),
            self.frame(5, pwm_applied_permille=0, current_a=None),
        ]
        account = s4.find_command_electrical_disagreements(frames)["row_account"]
        self.assertEqual(account["frames_scanned"], 5)
        self.assertEqual(
            account["rows_compared"] + account["rows_excluded_total"], account["frames_scanned"]
        )
        self.assertTrue(account["reconciles"])
        self.assertEqual(account["rows_compared"], 1)
        # a bool is not a duty, and a present-but-missing reading is not a number:
        # each excluded under its own name, never folded into "no disagreement seen"
        self.assertEqual(
            account["rows_excluded"],
            {
                s4.EXCLUDED_APPLIED_FIELD_ABSENT: 1,
                s4.EXCLUDED_APPLIED_NOT_AN_INTEGER: 1,
                s4.EXCLUDED_CURRENT_FIELD_ABSENT: 1,
                s4.EXCLUDED_CURRENT_NOT_A_NUMBER: 1,
            },
        )

    def test_a_current_without_a_status_is_a_candidate_not_an_exclusion(self):
        # Absence of qualification must not remove the row from the comparison; it
        # removes the row from certification. Conflating them would hide the S4
        # signature found in the real capture.
        report = s4.find_command_electrical_disagreements(
            [self.frame(1, pwm_applied_permille=999, current_a=0.0, current_a_status="")]
        )
        self.assertEqual(report["row_account"]["rows_excluded_total"], 0)
        self.assertEqual(len(report["no_active_response_candidates"]), 1)
        self.assertFalse(report["no_active_response_candidates"][0]["electrically_qualified"])
        self.assertEqual(report["rows_without_a_producer_status"], 1)

    def test_the_real_capture_excludes_no_row_and_says_which_checks_found_nothing(self):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        account = s4.find_command_electrical_disagreements(frames)["row_account"]
        self.assertEqual(account["frames_scanned"], 957)
        self.assertEqual(account["rows_compared"], 957)
        self.assertEqual(account["rows_excluded"], {})
        self.assertEqual(account["reasons_never_fired"], list(s4.EXCLUSION_REASONS))

    def test_divergence_excludes_a_frame_that_cannot_be_compared(self):
        report = s4.request_applied_divergence(
            [self.frame(1, pwm_applied_permille=999, pwm_readback_permille=999)]
        )
        self.assertEqual(
            report["row_account"]["rows_excluded"], {s4.EXCLUDED_REQUESTED_FIELD_ABSENT: 1}
        )
        self.assertEqual(report["distinct_req_applied_readback_tuples"], {})

    def test_a_missing_duty_is_not_counted_as_agreement(self):
        # present-but-missing on the wire normalises to None: it must not land in the
        # tuple statistic as (None, 0, 0) and read as "requested zero, applied zero".
        report = s4.request_applied_divergence(
            [self.frame(1, pwm_req_permille=None, pwm_applied_permille=0,
                        pwm_readback_permille=0)]
        )
        self.assertEqual(
            report["row_account"]["rows_excluded"], {s4.EXCLUDED_REQUESTED_NOT_AN_INTEGER: 1}
        )
        self.assertNotIn("(None, 0, 0)", report["distinct_req_applied_readback_tuples"])
        self.assertEqual(report["frames_where_applied_differs_from_requested"], 0)

    def test_the_duty_divergence_never_borrows_an_intent_claim(self):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        report = s4.request_applied_divergence(frames)
        self.assertIn("NOT SEPARABLE IN THIS SOURCE", report["intent_vs_application"])
        self.assertTrue(report["duty_fields_never_agree"])
        trace = s4.build_s4_trace(frames, is_physical_measurement=True)
        self.assertEqual(trace["commands_observed"], 0)


class ProtocolAndRecipe(unittest.TestCase):
    def test_protocol_names_all_four_lanes(self):
        lanes = [lane["lane"] for lane in s4.S4_PROTOCOL["required_evidence_lanes"]]
        self.assertEqual(set(lanes), {s4.INTENT, s4.APPLIED, s4.ELECTRICAL, s4.THERMAL})

    def test_protocol_forbids_the_unsafe_methods(self):
        text = str(s4.S4_PROTOCOL)
        for forbidden in ("short a branch", "bypass the fuse", "damage the TEC"):
            self.assertIn(forbidden, text)

    def test_protocol_names_the_hazard_it_exists_to_catch(self):
        self.assertIn("actually energised", s4.S4_PROTOCOL["hazard_this_protocol_avoids"])

    def test_recipe_requires_attendance_and_repetition(self):
        self.assertGreaterEqual(s4.S4_CAPTURE_RECIPE["repetitions"], 4)
        self.assertTrue(any("operator" in p for p in s4.S4_CAPTURE_RECIPE["prerequisites"]))
        self.assertEqual(s4.S4_CAPTURE_RECIPE["status_label"], "NEED_USER_ACTION")

    def test_recipe_requires_the_qualified_electrical_lane_first(self):
        # Without it the run cannot even state its own evidence, which is the
        # defect found in the committed capture.
        self.assertTrue(any(
            "current_status" in p for p in s4.S4_CAPTURE_RECIPE["prerequisites"]
        ))


class S3Feasibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = s3.assess()

    def test_verdict_is_no_go(self):
        self.assertEqual(self.report["verdict"], "NO-GO")

    def test_no_required_measurement_is_available(self):
        self.assertTrue(all(not item["available_now"] for item in self.report["required_measurements"]))

    def test_the_decisive_reason_is_the_missing_cold_side_probe(self):
        self.assertIn("UNRESOLVED", self.report["decisive_reason"])
        self.assertIn("cold_plate_min_c", self.report["decisive_reason"])

    def test_the_fan_obstruction_is_rejected_by_instruction(self):
        fan = next(m for m in self.report["candidate_methods"] if m["id"] == "C1-fan-obstruction")
        self.assertEqual(fan["verdict"], "REJECTED_BY_INSTRUCTION")
        self.assertIn("safe", fan["violates"])

    def test_door_and_drive_methods_are_reclassified_not_reused(self):
        # An S3 label that is really S2 or S4 would destroy the contrast B trains on.
        for method_id, other in (("C4-door_left_cracked", "S2"), ("C5-reduced-drive-in-software", "S4")):
            method = next(m for m in self.report["candidate_methods"] if m["id"] == method_id)
            self.assertEqual(method["verdict"], "RECLASSIFIED")
            self.assertIn(other, method["reason"])

    def test_every_candidate_violates_a_constraint(self):
        for method in self.report["candidate_methods"]:
            self.assertTrue(method["violates"], method["id"])

    def test_the_report_states_what_was_not_done(self):
        text = " ".join(self.report["not_done"])
        self.assertIn("no S3 run is claimed", text)
        self.assertIn("fan obstruction", text)

    def test_docs03_permits_the_omission(self):
        self.assertIn("docs/03 §31", self.report["docs03_position"])

    def test_the_path_to_a_yes_needs_instrumentation_not_manipulation(self):
        self.assertIn("probe", self.report["what_would_change_the_verdict"])

    def test_rendered_markdown_carries_the_verdict_and_the_methods(self):
        text = s3.render_markdown(self.report)
        self.assertIn("NO-GO", text)
        for method in self.report["candidate_methods"]:
            self.assertIn(method["id"], text)
        for item in self.report["required_measurements"]:
            self.assertIn(item["id"], text)


class RunExpansionCountsSessionsNotSegments(unittest.TestCase):
    """A-W11-03: 957 frames inside one boot of one stage run are not 957 runs."""

    def setUp(self):
        self.list_ = validate_w11.builder.additional_run_list()

    def test_zero_additional_runs_are_offered(self):
        self.assertEqual(self.list_["s1_runs_certified_valid"], 0)
        self.assertEqual(self.list_["s2_pilot_disturbances_available"], 0)
        self.assertEqual(self.list_["s4_runs_publishable"], 0)
        for capture in self.list_["captures"]:
            self.assertEqual(capture["additional_s1_or_s2_runs_available"], 0)

    def test_the_boot_segments_are_named_as_segments_of_a_registered_run(self):
        parseable = [c for c in self.list_["captures"]
                     if c["parseable_by_the_delivered_parser"]]
        self.assertEqual(len(parseable), 1)
        self.assertIn("not a new session", parseable[0]["why_not_a_run"])
        self.assertIn("one boot of one stage run", parseable[0]["why_not_a_run"])

    def test_an_unparseable_source_is_stated_as_unparseable_not_as_zero(self):
        unparseable = [c for c in self.list_["captures"]
                       if not c["parseable_by_the_delivered_parser"]]
        self.assertTrue(unparseable)
        for capture in unparseable:
            self.assertIsNone(capture["frames_usable_per_scenario"])
            self.assertIn("not counted", capture["why_not_parseable"])

    def test_the_list_reuses_the_w09_registry_instead_of_redefining_it(self):
        registry = json.loads(
            (validate_w11.builder.W09_REGISTRY).read_text(encoding="utf-8")
        )
        self.assertEqual(
            [c["capture_id"] for c in self.list_["captures"]],
            [c["capture_id"] for c in registry["captures"]],
        )
        self.assertEqual(
            [c["sha256"] for c in self.list_["captures"]],
            [c["sha256"] for c in registry["captures"]],
        )

    def test_a_new_run_names_what_it_needs_rather_than_being_assumed(self):
        self.assertTrue(self.list_["what_a_new_run_needs"])
        self.assertIn("NEED_USER_ACTION", self.list_["status_label"])


class S3SessionMethodologyAndPerCaptureShortfalls(unittest.TestCase):
    """A-W11-04 is methodology only: what to record, and why nothing existing qualifies."""

    dossier = pathlib.Path(__file__).resolve().parents[3] / "evidence" / "A" / "W11"
    validator = sys.modules["validate_w11"]

    def setUp(self):
        self.table = validate_w11.builder.s3_capture_shortfalls()
        self.registry_ids = [
            c["capture_id"] for c in json.loads(
                validate_w11.builder.W09_REGISTRY.read_text(encoding="utf-8")
            )["captures"]
        ]

    def test_the_table_covers_the_registry_and_not_a_second_list(self):
        # Reuse the W09 registry rather than duplicating it: a second capture list
        # would drift the moment W09 gained a source.
        self.assertEqual([e["capture_id"] for e in self.table], self.registry_ids)

    def test_no_committed_capture_can_support_an_s3_run(self):
        for entry in self.table:
            self.assertFalse(entry["could_support_an_s3_run"], entry["capture_id"])
            self.assertEqual(entry["measurements_it_could_supply"], [])
            self.assertEqual(
                sorted(entry["falls_short_of"]),
                sorted(m["id"] for m in s3.REQUIRED_MEASUREMENTS),
            )

    def test_every_shortfall_carries_a_reason(self):
        for entry in self.table:
            self.assertEqual(set(entry["shortfall_reasons"]), set(entry["falls_short_of"]))
            for measurement_id, reason in entry["shortfall_reasons"].items():
                self.assertTrue(reason.strip(), f"{entry['capture_id']}/{measurement_id} has no reason")

    def test_a_source_that_was_not_checked_is_not_reported_as_failed(self):
        # The timing table and the boot log are not frame streams this parser reads.
        # Saying "unchecked" is a different claim from saying "checked and unqualified".
        unchecked = [e for e in self.table if e["kind"] in ("telem_schema1", "derived_timing_table")]
        self.assertTrue(unchecked)
        for entry in unchecked:
            self.assertIn("NOT CHECKED", entry["shortfall_reasons"]["M1-qualified-electrical-power"])
        for entry in self.table:
            if entry["kind"] == "csv_capture":
                self.assertIn("no frame carries an OK producer status",
                              entry["shortfall_reasons"]["M1-qualified-electrical-power"])

    def test_a_host_fixture_never_supplies_a_measured_electrical_state(self):
        for entry in self.table:
            if not entry["is_physical_measurement"]:
                self.assertIn("protocol evidence only",
                              entry["shortfall_reasons"]["M1-qualified-electrical-power"])

    def test_the_session_methodology_names_no_result(self):
        ids = [item["id"] for item in s3.SESSION_RECORD_REQUIREMENTS]
        self.assertEqual(len(ids), len(set(ids)))
        text = json.dumps(s3.assess()["session_record_requirements"])
        for needed in ("producer status", "matched", "boot_id", "operator"):
            self.assertIn(needed, text)
        self.assertIn("no item below has been collected",
                      s3.render_markdown({**s3.assess(), "existing_capture_shortfalls": self.table}))

    def test_the_rendered_record_includes_the_per_capture_table(self):
        text = s3.render_markdown({**s3.assess(), "existing_capture_shortfalls": self.table})
        for entry in self.table:
            self.assertIn(entry["capture_id"], text)

    def test_promoting_a_capture_to_s3_capable_fails_the_sweep(self):
        broken = [dict(e, could_support_an_s3_run=True) for e in self.table]
        failures = self.validator.s3_shortfall_failures(broken, self.table, self.registry_ids)
        self.assertTrue(any("promoted to S3-capable" in f for f in failures), failures)

    def test_a_missing_reason_for_a_shortfall_fails_the_sweep(self):
        broken = [dict(e, shortfall_reasons={k: v for k, v in e["shortfall_reasons"].items()
                                             if k != "M2-cold-side-temperature"})
                  for e in self.table]
        failures = self.validator.s3_shortfall_failures(broken, self.table, self.registry_ids)
        self.assertTrue(any("no reason attached" in f for f in failures), failures)

    def test_dropping_a_registry_capture_from_the_table_fails_the_sweep(self):
        failures = self.validator.s3_shortfall_failures(
            self.table[:-1], self.table[:-1], self.registry_ids
        )
        self.assertTrue(any("no longer covers" in f for f in failures), failures)

    def test_the_shipped_table_passes_the_sweep(self):
        shipped = json.loads((self.dossier / "s4-s3" / "s3-feasibility.json").read_text(
            encoding="utf-8"
        ))
        self.assertEqual(
            self.validator.s3_shortfall_failures(
                shipped["existing_capture_shortfalls"], self.table, self.registry_ids
            ),
            [],
        )


class DossierPinSetIsExact(unittest.TestCase):
    """The manifest must cover every deliverable and nothing that is a build cache.

    A dossier whose pin set is a hand-maintained list drifts silently: a new
    artifact ships unpinned and nobody can tell whether it was ever derived. This
    mechanism is what the validator's pin sweep checks, so it gets its own test.
    """

    dossier = pathlib.Path(__file__).resolve().parents[3] / "evidence" / "A" / "W11"
    validator = sys.modules["validate_w11"]

    def on_disk(self) -> list[str]:
        return [p.relative_to(self.dossier).as_posix()
                for p in self.dossier.rglob("*") if p.is_file()]

    def test_an_unpinned_deliverable_fails_the_sweep(self):
        failures = self.validator.pin_set_failures(
            {"README.md", "SHA256SUMS.txt"},
            ["README.md", "SHA256SUMS.txt", "S4-runs/invented-run.json"],
        )
        self.assertEqual(
            [f for f in failures if "invented-run.json" in f and "not hash-pinned" in f],
            ["S4-runs/invented-run.json is present in the dossier but not hash-pinned"],
        )

    def test_a_pinned_build_cache_fails_the_sweep(self):
        failures = self.validator.pin_set_failures(
            {"README.md", "__pycache__/build_w11_artifacts.cpython-314.pyc"}, ["README.md"]
        )
        self.assertTrue(any("build cache" in f for f in failures), failures)

    def test_a_pinned_pyc_suffix_fails_the_sweep(self):
        failures = self.validator.pin_set_failures({"stale.pyc"}, [])
        self.assertTrue(any("build cache" in f for f in failures), failures)

    def test_the_pin_file_never_pins_itself(self):
        failures = self.validator.pin_set_failures(
            {"README.md", "SHA256SUMS.txt"}, ["README.md", "SHA256SUMS.txt"]
        )
        self.assertTrue(any("must not pin itself" in f for f in failures), failures)

    def test_a_local_cache_on_disk_is_not_demanded_as_evidence(self):
        failures = self.validator.pin_set_failures(
            {"README.md"}, ["README.md", "__pycache__/build_w11_artifacts.cpython-314.pyc"]
        )
        self.assertEqual(failures, [])

    def test_the_shipped_manifest_pins_exactly_the_shipped_dossier(self):
        sums = self.dossier / "SHA256SUMS.txt"
        if not sums.is_file():
            self.skipTest("SHA256SUMS.txt has not been written yet")
        pinned = {
            line.split("  ", 1)[1]
            for line in sums.read_text(encoding="utf-8").splitlines() if line.strip()
        }
        self.assertEqual(self.validator.pin_set_failures(pinned, self.on_disk()), [])
        self.assertEqual(pinned, set(self.validator.builder.PINNED_FILES))


class GeometryAndRowAccountAreChecked(unittest.TestCase):
    """The dossier's two structural rules, tested as mechanisms rather than prose.

    The geometry rule exists because docs/01 823-825 and the frozen as-built record
    disagree about which probe is where; the only safe posture is to reuse W09's
    authority and keep the disagreement written down. The row-account rule exists
    because a dropped row and a believed row produce the same published number.
    """

    validator = sys.modules["validate_w11"]
    dossier = pathlib.Path(__file__).resolve().parents[3] / "evidence" / "A" / "W11"

    def clean_basis(self) -> dict:
        lane = json.loads((self.dossier / "s4-s3" / "lane-evidence.json").read_text(
            encoding="utf-8"
        ))
        return lane["chamber_air_slot_basis"]

    def clean_account(self) -> dict:
        lane = json.loads((self.dossier / "s4-s3" / "lane-evidence.json").read_text(
            encoding="utf-8"
        ))
        return lane["command_electrical_disagreements"]["row_account"]

    def test_the_shipped_lane_evidence_passes_both_checks(self):
        self.assertEqual(self.validator.geometry_failures(self.clean_basis()), [])
        self.assertEqual(self.validator.row_account_failures(self.clean_account(), "x"), [])

    def test_the_hot_side_re_entering_chamber_air_fails(self):
        basis = self.clean_basis()
        basis["chamber_air_slots"] = ["t1", "t2", "t3", "t4"]
        self.assertTrue(any("hot side" in f for f in self.validator.geometry_failures(basis)))

    def test_losing_the_docs01_discrepancy_note_fails(self):
        basis = self.clean_basis()
        basis["docs01_discrepancy"] = "the probes are where the geometry says they are"
        failures = self.validator.geometry_failures(basis)
        self.assertTrue(any("823-825" in f for f in failures), failures)

    def test_re_deriving_the_geometry_instead_of_reusing_w09_fails(self):
        basis = self.clean_basis()
        basis["reused_not_rederived"] = "read off this capture's own role fields"
        self.assertTrue(any("re-derived" in f for f in self.validator.geometry_failures(basis)))

    def test_losing_the_w09_registry_gap_note_fails(self):
        # W09's run-registry.json has no geometry field; the dossier must keep saying
        # where the frozen positions actually came from instead of hiding the workaround.
        basis = self.clean_basis()
        basis["registry_gap"] = ""
        failures = self.validator.geometry_failures(basis)
        self.assertTrue(any("registry gap" in f for f in failures), failures)

    def test_a_missing_geometry_block_fails(self):
        self.assertTrue(self.validator.geometry_failures({}))

    def test_an_unreconciled_row_account_fails(self):
        # 957 scanned but only 900 accounted for: 57 rows vanished from the statistic.
        account = self.clean_account()
        account["rows_compared"] = 900
        failures = self.validator.row_account_failures(account, "applied/current comparison")
        self.assertTrue(any("do not reconcile" in f for f in failures), failures)

    def test_an_exclusion_under_an_unnamed_reason_fails(self):
        account = self.clean_account()
        account["rows_excluded"] = {"we did not like this row": 3}
        account["rows_excluded_total"] = 3
        account["rows_compared"] = account["frames_scanned"] - 3
        failures = self.validator.row_account_failures(account, "x")
        self.assertTrue(any("unnamed reason" in f for f in failures), failures)

    def test_a_row_account_that_is_not_published_at_all_fails(self):
        self.assertTrue(self.validator.row_account_failures({}, "duty-triple comparison"))

    def test_the_real_capture_needs_no_exclusion_to_be_believable(self):
        # The exclusion machinery is proved on fixtures; on the committed capture it
        # fires zero times, which is a checked-and-found-none claim.
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        account = self.clean_account()
        self.assertEqual(account["frames_scanned"], len(frames))
        self.assertEqual(account["rows_excluded_total"], 0)
        self.assertEqual(
            account["reasons_never_fired"],
            [r for r in s4.EXCLUSION_REASONS],
        )


class PublishedPathsStayRepositoryRelative(unittest.TestCase):
    """An evidence record that names one developer's machine is not evidence.

    The dossier scans every pinned file for an absolute developer path, so the
    refusal layer has to publish relative paths at the source instead of leaving
    the builder to scrub them.
    """

    def test_a_registered_capture_is_published_by_its_repository_path(self):
        source = ref.ObservationSource.from_path(W04_G1_LOG, True)
        self.assertEqual(source.path, "evidence/A/W04/g1/40-g1-boot-60s.log")
        self.assertNotIn(":", source.path)
        self.assertTrue(source.sha256 and len(source.sha256) == 64)

    def test_a_repository_relative_input_is_read_the_same_way_from_any_directory(self):
        # The registry writes capture paths repository-relative. Resolving them against
        # the caller's working directory would make the published evidence depend on
        # where the tool happened to run, so both spellings must agree.
        relative = pathlib.Path("evidence/A/W04/g1/40-g1-boot-60s.log")
        self.assertEqual(
            ref.repository_relative(relative),
            ref.repository_relative(REPO_ROOT / relative),
        )
        self.assertEqual(ref.repository_relative(relative), relative.as_posix())
        report = ref.analyze_capture(relative, is_physical_measurement=True)
        self.assertEqual(report["provenance"]["path"], relative.as_posix())
        self.assertEqual(report["summary"]["telem_frames"], 62)

    def test_a_path_outside_the_repository_is_not_faked_as_relative(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            outside = pathlib.Path(tmp) / "somewhere-else.log"
            outside.write_text("not in the repository\n", encoding="utf-8")
            published = ref.repository_relative(outside)
        # claiming a repository-relative path for a file outside the repo would be a
        # lie about where the observation came from, so the absolute form is kept
        self.assertTrue(pathlib.PurePosixPath(published).is_absolute() or
                        pathlib.PureWindowsPath(published).is_absolute(), published)
        self.assertNotIn("evidence/A", published)

    def test_the_refusal_analysis_carries_the_relative_path_into_its_report(self):
        report = ref.analyze_capture(W04_G1_LOG, is_physical_measurement=True)
        self.assertEqual(
            report["provenance"]["path"], "evidence/A/W04/g1/40-g1-boot-60s.log"
        )


if __name__ == "__main__":
    unittest.main()
