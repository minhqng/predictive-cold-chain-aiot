"""Tests for cg_w10_door.py (A-W10-01/-02/-03).

These tests carry the W10 honesty contract. The door is the only disturbance
Member B is being promised, and the bench has never produced a protocolised one,
so the tool must be *unable* to manufacture that appearance. The properties under
test are: an unreadable door is never called closed; a frame cannot name its own
door state because the two polarity settings are complements; an attestation only
licenses the boot it was made for; and an incidental OPEN window inside a
commissioning stage is never counted as an S2 pilot disturbance.
"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_w09_capture_parser as cp  # noqa: E402
import cg_w09_export as ex  # noqa: E402
import cg_w09_fixtures as fx  # noqa: E402
import cg_w10_door as door  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
W04_CSV = REPO_ROOT / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"


class MappingIsAComplementarySwitch(unittest.TestCase):
    def test_near_low_mapping_is_the_documented_default(self):
        self.assertEqual(door.name_from_raw(0, door.NEAR_LOW), door.CLOSED)
        self.assertEqual(door.name_from_raw(1, door.NEAR_LOW), door.OPEN)

    def test_near_high_mapping_is_the_complement(self):
        self.assertEqual(door.name_from_raw(0, door.NEAR_HIGH), door.OPEN)
        self.assertEqual(door.name_from_raw(1, door.NEAR_HIGH), door.CLOSED)

    def test_unconfirmed_polarity_names_nothing(self):
        self.assertEqual(door.name_from_raw(0, "UNCONFIRMED"), door.UNKNOWN)
        self.assertEqual(door.name_from_raw(1, None), door.UNKNOWN)
        self.assertEqual(door.name_from_raw(None, door.NEAR_LOW), door.UNKNOWN)

    def test_frames_cannot_name_their_own_state(self):
        self.assertFalse(door.frames_can_name_their_own_door_state())

    def test_the_two_settings_invert_every_frame_in_a_real_capture(self):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        # The CSV carries no door_raw at all, which is its own finding: the
        # derived table dropped the field the polarity argument is about.
        report = door.polarity_inversion_check(frames)
        self.assertEqual(report["frames_with_raw_and_confirmed_polarity"], 0)
        self.assertFalse(report["frames_alone_can_name_door_state"])

    def test_inversion_is_measured_on_raw_bearing_frames(self):
        frames = fx.physical_frames(3, door_polarity="CONFIRMED", door_raw="1")
        report = door.polarity_inversion_check(frames)
        self.assertEqual(report["frames_with_raw_and_confirmed_polarity"], 3)
        self.assertEqual(report["frames_whose_state_inverts_under_the_other_polarity"], 3)
        self.assertEqual(report["inversion_fraction"], 1.0)


class AttestationRules(unittest.TestCase):
    def test_absent_attestation_is_not_trustworthy(self):
        frames = fx.physical_frames(3)
        status = door.attest_for_boot(frames, None)
        self.assertFalse(status["trustworthy"])
        self.assertIn("NO_ATTESTATION", status["reason"])

    def test_attestation_for_another_boot_does_not_license_this_one(self):
        frames = fx.physical_frames(3, boot_id="realboot")
        status = door.attest_for_boot(
            frames, door.PolarityAttestation("otherboot", door.NEAR_LOW, "operator", "touch test")
        )
        self.assertFalse(status["trustworthy"])
        self.assertIn("ATTESTATION_BOOT_MISMATCH", status["reason"])

    def test_attestation_for_the_same_boot_is_accepted(self):
        frames = fx.physical_frames(3, boot_id="realboot")
        status = door.attest_for_boot(
            frames, door.PolarityAttestation("realboot", door.NEAR_LOW, "operator", "touch test")
        )
        self.assertTrue(status["trustworthy"])

    def test_the_frame_cannot_state_which_mapping_was_used(self):
        frames = fx.physical_frames(2)
        status = door.attest_for_boot(
            frames, door.PolarityAttestation("fixtureboot", door.NEAR_LOW, "op", "ev")
        )
        self.assertFalse(status["frame_can_state_which_mapping_was_used"])
        self.assertTrue(status["mapping_identity_is_externally_attested_only"])

    def test_no_frame_corroboration_is_rejected(self):
        frames = fx.physical_frames(2, door_polarity="UNCONFIRMED", door_status="UNVERIFIED",
                                    door_open="UNKNOWN")
        status = door.attest_for_boot(
            frames, door.PolarityAttestation("fixtureboot", door.NEAR_LOW, "op", "ev")
        )
        self.assertFalse(status["trustworthy"])
        self.assertIn("NO_FRAME_CORROBORATION", status["reason"])

    def test_an_unknown_polarity_name_is_rejected(self):
        frames = fx.physical_frames(2)
        status = door.attest_for_boot(
            frames, door.PolarityAttestation("fixtureboot", "SIDEWAYS", "op", "ev")
        )
        self.assertFalse(status["trustworthy"])
        self.assertIn("UNKNOWN_POLARITY_NAME", status["reason"])


class UnknownIsNotClosed(unittest.TestCase):
    def test_an_unknown_door_run_is_its_own_state(self):
        frames = fx.physical_frames(3, door_open="UNKNOWN", door_status="UNVERIFIED",
                                    door_polarity="UNCONFIRMED")
        report = door.detect_events(frames)
        self.assertEqual(report["state_run_counts"], {door.UNKNOWN: 3})
        self.assertTrue(report["unknown_is_not_closed"])
        self.assertNotIn(door.CLOSED, report["state_run_counts"])

    def test_an_unknown_door_never_certifies_a_quiet_run(self):
        frames = fx.physical_frames(4, door_open="UNKNOWN", door_status="UNVERIFIED",
                                    door_polarity="UNCONFIRMED")
        report = door.detect_events(frames)
        for event in report["events"]:
            self.assertIn("DOOR_STATE_UNKNOWN_IS_NOT_A_NAMED_TRANSITION", event["not_s2_because"])

    def test_closed_run_is_not_a_disturbance(self):
        frames = fx.physical_frames(4)
        report = door.detect_events(frames)
        event = report["events"][0]
        # No attestation was supplied, so the run is the device's report of a
        # level, not a physical state; naming it CLOSED would be inventing one.
        self.assertEqual(event["state"], door.CLOSED_AS_REPORTED)
        self.assertNotEqual(event["state"], door.CLOSED)
        self.assertIn("CLOSED_RUN_IS_A_REST_STATE_NOT_A_DISTURBANCE", event["not_s2_because"])


class EventDetection(unittest.TestCase):
    def test_a_controlled_attested_open_window_becomes_an_s2_event(self):
        frames = (
            fx.physical_frames(3, door_raw="0", door_open="0")
            + fx.physical_frames(3, door_raw="1", door_open="1", seqs=[4, 5, 6])
            + fx.physical_frames(3, door_raw="0", door_open="0", seqs=[7, 8, 9])
        )
        attestation = door.PolarityAttestation("fixtureboot", door.NEAR_LOW, "operator",
                                               "magnet/lid test this boot")
        report = door.detect_events(
            frames, attestation=attestation, operator_controlled=True, protocol_id="S2-P-15s"
        )
        opens = [e for e in report["events"] if e["state"] == door.OPEN]
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0]["n_frames"], 3)
        self.assertEqual(opens[0]["state_semantics"], "NAMED_BY_ATTESTED_PER_BOOT_MAPPING")
        self.assertTrue(opens[0]["is_physical_measurement"])

    def test_the_same_frames_without_a_plan_are_not_pilot_evidence(self):
        frames = (
            fx.physical_frames(2)
            + fx.physical_frames(3, door_raw="1", door_open="1", seqs=[3, 4, 5])
            + fx.physical_frames(2, seqs=[6, 7])
        )
        attestation = door.PolarityAttestation("fixtureboot", door.NEAR_LOW, "operator", "ev")
        report = door.detect_events(frames, attestation=attestation)
        for event in report["events"]:
            if event["state"] == door.OPEN:
                self.assertIn("NO_OPERATOR_CONTROLLED_TIMING", event["not_s2_because"])
                self.assertNotEqual(event["event_class"], "S2_PILOT_DISTURBANCE")
        self.assertEqual(report["s2_pilot_events"], [])

    def test_a_host_fixture_event_says_it_is_not_a_measurement(self):
        frames = (
            fx.fixture_frames(2)
            + fx.fixture_frames(3, door_raw="1", door_open="1", seqs=[3, 4, 5])
            + fx.fixture_frames(2, seqs=[6, 7])
        )
        report = door.detect_events(frames, operator_controlled=True, protocol_id="S2-P-15s")
        self.assertFalse(report["events"][0]["is_physical_measurement"])
        self.assertEqual(report["s2_pilot_events"], [])
        self.assertTrue(any(
            "SOURCE_IS_NOT_A_PHYSICAL_MEASUREMENT" in e["not_s2_because"] for e in report["events"]
        ))

    def test_rise_is_measured_on_chamber_air_only(self):
        warm = dict(t1=26.0, t3=26.5, t4=27.0)
        frames = fx.physical_frames(3, **warm) + fx.physical_frames(
            3, seqs=[4, 5, 6], door_raw="1", door_open="1", t1=27.5, t3=28.0, t4=29.0
        )
        attestation = door.PolarityAttestation("fixtureboot", door.NEAR_LOW, "operator", "ev")
        report = door.detect_events(frames, attestation=attestation, operator_controlled=True,
                                    protocol_id="S2-P-3s")
        open_event = next(e for e in report["events"] if e["state"] == door.OPEN)
        self.assertIn("t1", open_event["thermal_rise"])
        self.assertIn("t4", open_event["thermal_rise"])
        self.assertNotIn("t2", open_event["thermal_rise"])
        self.assertIn("t2", open_event["thermal_rise"]["excluded_slots"])
        self.assertAlmostEqual(open_event["thermal_rise"]["t4"]["rise_c"], 2.0, places=3)

    def test_a_sub_floor_rise_is_rejected_as_undetectable(self):
        frames = fx.physical_frames(3, t1=25.0, t3=25.0, t4=25.0) + fx.physical_frames(
            4, seqs=[4, 5, 6, 7], door_raw="1", door_open="1", t1=25.01, t3=25.01, t4=25.01
        )
        attestation = door.PolarityAttestation("fixtureboot", door.NEAR_LOW, "operator", "ev")
        report = door.detect_events(
            frames, attestation=attestation, operator_controlled=True, protocol_id="S2-P",
            noise_floor_c={"t1": 0.5, "t3": 0.5, "t4": 0.5},
        )
        open_event = next(e for e in report["events"] if e["state"] == door.OPEN)
        self.assertTrue(any("BELOW_THE_BASELINE_NOISE_FLOOR" in r for r in open_event["not_s2_because"]))

    def test_empty_capture_is_refused_not_reported_as_clean(self):
        with self.assertRaises(ValueError):
            door.detect_events([])


class Mc38Timing(unittest.TestCase):
    def test_timing_constants_come_from_the_shipped_path(self):
        timing = door.timing_quantization()
        self.assertEqual(timing["debounce_ms"], 50)
        self.assertEqual(timing["poll_ms"], 10)
        self.assertEqual(timing["telemetry_hz"], 1.0)
        self.assertEqual(timing["minimum_resolvable_open_duration_s"], 1.0)
        self.assertEqual(timing["edge_time_uncertainty_s"], 1.0)

    def test_cycle_counter_cross_check_is_reported(self):
        frames = fx.physical_frames(4, door_cycles="0")
        report = door.detect_events(frames)
        self.assertEqual(
            report["mc38_alignment_cross_check"]["detected_open_to_closed_transitions"], 0
        )
        self.assertEqual(report["mc38_alignment_cross_check"]["device_reported_door_cycles"], 0)
        self.assertTrue(report["mc38_alignment_cross_check"]["aligned"])

    def test_a_missed_edge_is_detected_as_misalignment(self):
        # Device says two open->close cycles happened; the 1 Hz stream can only
        # show one. Under-resolution must surface as a failure, not as a quiet run.
        frames = (
            fx.physical_frames(2)
            + fx.physical_frames(2, seqs=[3, 4], door_raw="1", door_open="1")
            + fx.physical_frames(2, seqs=[5, 6], door_raw="0", door_open="0", door_cycles="2")
        )
        attestation = door.PolarityAttestation("fixtureboot", door.NEAR_LOW, "operator", "ev")
        report = door.detect_events(frames, attestation=attestation)
        check = report["mc38_alignment_cross_check"]
        self.assertEqual(check["detected_open_to_closed_transitions"], 1)
        self.assertEqual(check["device_reported_door_cycles"], 2)
        self.assertFalse(check["aligned"])

    def test_duration_is_measured_from_device_ms(self):
        # device_ms defaults to (seq-1)*1000+904 in the fixture, so a two-frame
        # OPEN run spans exactly one 1 Hz interval.
        frames = (
            fx.physical_frames(1, seqs=[1])
            + fx.physical_frames(2, seqs=[2, 3], door_raw="1", door_open="1")
            + fx.physical_frames(1, seqs=[4])
        )
        attestation = door.PolarityAttestation("fixtureboot", door.NEAR_LOW, "operator", "ev")
        report = door.detect_events(frames, attestation=attestation)
        event = report["events"][1]
        self.assertEqual(event["state"], door.OPEN)
        self.assertEqual(event["duration_s"], 1.0)
        self.assertEqual(event["timing_uncertainty"]["duration_uncertainty_s"], 1.0)


class CommittedCapturePosition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        cls.frames = frames
        cls.report = door.detect_events(frames)

    def test_no_open_event_exists_in_the_only_committed_capture(self):
        self.assertNotIn(door.OPEN, self.report["state_run_counts"])
        self.assertEqual(self.report["s2_pilot_events"], [])

    def test_the_startup_block_is_pending_not_closed(self):
        self.assertEqual(self.report["state_run_counts"][door.UNKNOWN], 17)

    def test_the_pilot_status_names_the_gap_and_the_recipe(self):
        status = door.pilot_status(self.report)
        self.assertEqual(status["status_label"], "NEED_USER_ACTION")
        self.assertEqual(status["valid_pilot_disturbances_available"], 0)
        self.assertEqual(status["valid_pilot_disturbances_target"],
                         ">=4-6 (docs/05A §19 A-W10-03)")
        self.assertFalse(status["is_physical_measurement"])
        recipe = status["recipe"]["capture_recipe"]
        self.assertGreaterEqual(recipe["repetitions"], 4)
        self.assertTrue(recipe["safety_prerequisites"])
        self.assertTrue(any("supervised" in line for line in recipe["per_repetition"]))

    def test_the_recipe_does_not_claim_any_disturbance_happened(self):
        text = str(door.S2_CAPTURE_RECIPE)
        self.assertIn("have never been collected", text)
        self.assertIn("NEED_USER_ACTION", text)
        # Nothing in the recipe may read as a completed capture.
        self.assertNotIn("pilot disturbances collected", text)

    def test_export_refuses_a_probe_identification_run_end_to_end(self):
        frames = fx.physical_frames(3, run_label="PROBE_IDENTIFICATION")
        source = ex.RunSource(
            path="evidence/A/W07/probe-identification/touch_1.log", sha256="0" * 64,
            source_kind="h8s_jsonl", is_physical_measurement=True,
            run_label="PROBE_IDENTIFICATION",
        )
        with self.assertRaises(ex.ExportError):
            ex.build_run_export(
                frames, run_label="PROBE_IDENTIFICATION",
                scenario_candidate="S2_DOOR_DISTURBANCE", status_label="REAL_DATA_ANALYZED",
                sources=[source],
            )


class ReportedLevelIsNotAState(unittest.TestCase):
    """A frame's own door label is a reading, and must be named as one (M7)."""

    def test_an_unattested_open_level_is_not_called_open(self):
        frames = fx.physical_frames(3, door_open="1", door_raw="1")
        report = door.detect_events(frames)
        event = report["events"][0]
        self.assertEqual(event["state"], door.OPEN_AS_REPORTED)
        self.assertNotIn(door.OPEN, report["state_run_counts"])
        self.assertEqual(event["state_semantics"], "REPORTED_BY_FRAME_ONLY_NOT_PHYSICALLY_NAMED")

    def test_an_attested_open_level_is_the_named_state(self):
        # The *_AS_REPORTED labels must not swallow the attested path: with a
        # trustworthy per-boot mapping the name really is OPEN.
        frames = fx.physical_frames(3, door_open="1", door_raw="1")
        attestation = door.PolarityAttestation("fixtureboot", door.NEAR_LOW, "operator", "ev")
        report = door.detect_events(frames, attestation=attestation)
        self.assertTrue(report["attestation"]["trustworthy"])
        self.assertEqual(report["events"][0]["state"], door.OPEN)
        self.assertEqual(report["events"][0]["state_semantics"],
                         "NAMED_BY_ATTESTED_PER_BOOT_MAPPING")

    def test_the_cross_check_still_counts_reported_transitions(self):
        # Relabelling must not silently zero the MC-38 alignment cross-check: a
        # reported OPEN->CLOSED run is still a transition the counter should see.
        frames = (
            fx.physical_frames(2, seqs=[1, 2])
            + fx.physical_frames(2, seqs=[3, 4], door_raw="1", door_open="1")
            + fx.physical_frames(2, seqs=[5, 6], door_raw="0", door_open="0", door_cycles="1")
        )
        report = door.detect_events(frames)
        self.assertNotIn(door.OPEN, [e["state"] for e in report["events"]])
        self.assertEqual(
            report["mc38_alignment_cross_check"]["detected_open_to_closed_transitions"], 1
        )
        self.assertTrue(report["mc38_alignment_cross_check"]["aligned"])

    def test_the_real_capture_publishes_no_bare_state_labels(self):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        report = door.detect_events(frames)
        self.assertFalse(report["attestation"]["trustworthy"])
        self.assertEqual(
            report["state_run_counts"],
            {door.UNKNOWN: 17, door.CLOSED_AS_REPORTED: 940},
        )
        for event in report["events"]:
            if event["state"] != door.UNKNOWN:
                self.assertTrue(event["state"].endswith("_AS_REPORTED"), event["state"])


class UncitableSourceHygiene(unittest.TestCase):
    """An untracked file may not be presented as the proof of a published claim."""

    TEXT_SUFFIXES = (".py", ".md", ".json")
    SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "build"}

    def _source_files(self):
        for path in REPO_ROOT.rglob("*"):
            if path.suffix not in self.TEXT_SUFFIXES or not path.is_file():
                continue
            if self.SKIP_DIRS.intersection(set(path.parts) - {REPO_ROOT.name}):
                continue
            yield path

    def test_the_contact_inversion_states_its_citation_status(self):
        record = door.DOOR_CONTACT_INVERSION
        self.assertEqual(record["code_level_proof_status"], door.UNCITABLE_UNTRACKED_SOURCE)
        self.assertIn("docs/01", record["assertion_basis"])
        self.assertTrue(record["why_not_citable"])
        self.assertTrue(record["closes_when"])
        # The mechanism is still carried into every report, not dropped.
        frames = fx.physical_frames(2, door_raw="1", door_open="1")
        report = door.polarity_inversion_check(frames)
        self.assertEqual(
            report["contact_inversion"]["code_level_proof_status"],
            door.UNCITABLE_UNTRACKED_SOURCE,
        )

    def test_the_cited_driver_is_not_tracked_in_this_repository(self):
        # The reason the label is needed: nothing here carries the file. If it
        # ever is committed, the label must be retired rather than left to rot.
        self.assertFalse((REPO_ROOT / "firmware" / "h8-bench").exists())

    def test_no_file_in_this_repo_quotes_the_untracked_driver_as_bare_proof(self):
        offenders = []
        for path in self._source_files():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "h8_door.c" in text and door.UNCITABLE_UNTRACKED_SOURCE not in text:
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(
            offenders, [],
            "every mention of the untracked door driver must carry its citation status",
        )

    def test_the_untracked_source_gap_is_registered(self):
        registry = json.loads(
            (REPO_ROOT / "evidence" / "A" / "W09" / "run-registry.json").read_text(
                encoding="utf-8")
        )
        entry = [
            p for p in registry["external_positions"]
            if p.get("eligibility") == door.UNCITABLE_UNTRACKED_SOURCE
        ]
        self.assertEqual(len(entry), 1, "the door driver gap is not registered")
        self.assertIn("claim_kept", entry[0])
        self.assertIn("h8_door.c", entry[0]["reason"])


if __name__ == "__main__":
    unittest.main()
