"""Tests for cg_w09_validity.py (A-W09-03).

The invalidation layer is where "unknown must not silently become normal"
(docs/01 §19.4) is either enforced or lost, so these tests attack it from both
sides: a frame that should be rejected must be rejected with a named reason, and
a frame that should survive an unrelated unqualified column must not be thrown
away with it. Both directions matter - over-rejection would discard the only
real thermal capture Member A has, and under-rejection would put unqualified
numbers into a dataset.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_w09_capture_parser as cp  # noqa: E402
import cg_w09_export as ex  # noqa: E402
import cg_w09_fixtures as fx  # noqa: E402
import cg_w09_validity as cv  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
W04_CSV = REPO_ROOT / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"


def _frame(**overrides):
    return fx.physical_frames(1, **overrides)[0]


def _codes(reasons) -> set[str]:
    return {reason.code for reason in reasons}


def _row_codes(frame) -> set[str]:
    return set(cv.evaluate_frame(frame).reason_codes)


class SnapshotRule(unittest.TestCase):
    def test_invalid_snapshot_is_invalidating(self):
        verdict = cv.evaluate_frame(_frame(snapshot="INVALID"))
        self.assertIn("SNAPSHOT_INVALID", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["producer"], cv.INVALID)
        self.assertNotIn("S1_NORMAL_BASELINE", verdict.usable_for)

    def test_absent_snapshot_is_unknown_not_valid(self):
        frame = _frame()
        frame.values.pop("snapshot")
        verdict = cv.evaluate_frame(frame)
        self.assertIn("SNAPSHOT_UNREPORTED", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["producer"], cv.UNKNOWN)

    def test_a_valid_snapshot_row_is_not_blocked(self):
        verdict = cv.evaluate_frame(_frame())
        self.assertNotIn("SNAPSHOT_INVALID", verdict.reason_codes)


class MaskRules(unittest.TestCase):
    def test_missing_bit_invalidates_only_its_domain(self):
        verdict = cv.evaluate_frame(_frame(missing="0x2"))  # T2 -> thermal
        self.assertIn("PROBE_MISSING", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["thermal"], cv.INVALID)

    def test_door_mask_lands_in_the_door_domain(self):
        verdict = cv.evaluate_frame(_frame(missing="0x80"))
        self.assertEqual(verdict.quality_by_domain["door"], cv.INVALID)
        self.assertEqual(verdict.quality_by_domain["thermal"], cv.VALID)

    def test_stale_is_degraded_not_invalid(self):
        # docs/01 §18.4: staleness is not the same fault as absence.
        verdict = cv.evaluate_frame(_frame(stale="0x1"))
        self.assertIn("PROBE_STALE", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["thermal"], cv.DEGRADED)
        self.assertIn("S1_NORMAL_BASELINE", verdict.usable_for)

    def test_masked_field_is_named(self):
        verdict = cv.evaluate_frame(_frame(invalid="0x4"))
        self.assertIn("t3", verdict.masked_fields)

    def test_csv_encoding_reports_masks_absent_as_degraded(self):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        verdict = cv.evaluate_frame(frames[500])
        self.assertIn("MASKS_ABSENT", verdict.reason_codes)
        # Degraded is a documented legal path, not a blocking state.
        self.assertEqual(verdict.quality_by_domain["producer"], cv.DEGRADED)


class StatusRules(unittest.TestCase):
    def test_non_ok_status_drops_the_number(self):
        verdict = cv.evaluate_frame(_frame(t1_status="IO_ERROR"))
        self.assertIn("FIELD_STATUS_NOT_OK", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["thermal"], cv.INVALID)

    def test_crc_fail_is_a_hard_failure(self):
        verdict = cv.evaluate_frame(_frame(t3_status="CRC_FAIL"))
        self.assertEqual(verdict.quality_by_domain["thermal"], cv.INVALID)

    def test_age_beyond_the_window_is_stale(self):
        frame = _frame()
        frame.values["t1_age_ms"] = 5000
        verdict = cv.evaluate_frame(frame)
        self.assertIn("FIELD_STALE_BY_AGE", verdict.reason_codes)

    def test_the_750_ms_conversion_latency_is_not_called_stale(self):
        verdict = cv.evaluate_frame(_frame())
        self.assertNotIn("FIELD_STALE_BY_AGE", verdict.reason_codes)


class ElectricalQualification(unittest.TestCase):
    def test_empty_status_is_not_ok(self):
        frame = _frame()
        frame.values["current_a_status"] = None
        verdict = cv.evaluate_frame(frame)
        self.assertIn("ELECTRICAL_UNQUALIFIED", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["electrical"], cv.UNKNOWN)

    def test_unqualified_electrical_does_not_destroy_the_thermal_domain(self):
        # This is the reason quality is per-domain: the committed capture's PZEM
        # columns are unqualified, and its probe columns are not.
        frame = _frame()
        frame.values["current_a_status"] = None
        frame.values["voltage_v_status"] = None
        verdict = cv.evaluate_frame(frame)
        self.assertEqual(verdict.quality_by_domain["electrical"], cv.UNKNOWN)
        self.assertEqual(verdict.quality_by_domain["thermal"], cv.VALID)
        self.assertIn("S1_NORMAL_BASELINE", verdict.usable_for)
        self.assertNotIn("S4_ACTUATION_RESPONSE_FAULT", verdict.usable_for)

    def test_energy_wh_has_no_status_field_anywhere_and_is_flagged(self):
        verdict = cv.evaluate_frame(_frame())
        codes = [r for r in verdict.reasons if r.field == "energy_wh"]
        self.assertTrue(codes, "energy_wh must be flagged somewhere")
        self.assertEqual(codes[0].code, "ENERGY_ACCUMULATOR_UNQUALIFIED")
        # Degraded, not blocking: the accumulator has no status in any encoding,
        # but that must not make a qualified current reading unusable.
        self.assertEqual(codes[0].quality, cv.DEGRADED)

    def test_qualified_electrical_unlocks_the_electrical_scenario(self):
        verdict = cv.evaluate_frame(_frame())
        self.assertIn("S4_ACTUATION_RESPONSE_FAULT", verdict.usable_for)


class DoorRules(unittest.TestCase):
    def test_unknown_door_is_not_closed(self):
        verdict = cv.evaluate_frame(_frame(door_open="UNKNOWN"))
        self.assertIn("DOOR_STATE_UNKNOWN", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["door"], cv.UNKNOWN)
        self.assertNotIn("S1_NORMAL_BASELINE", verdict.usable_for)

    def test_unconfirmed_polarity_blocks_the_door_domain(self):
        verdict = cv.evaluate_frame(_frame(door_polarity="UNCONFIRMED"))
        self.assertIn("DOOR_POLARITY_UNCONFIRMED", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["door"], cv.UNKNOWN)

    def test_unverified_door_status_is_unknown(self):
        verdict = cv.evaluate_frame(_frame(door_status="UNVERIFIED"))
        self.assertIn("DOOR_STATUS_NOT_OK", verdict.reason_codes)

    def test_closed_confirmed_door_is_fine(self):
        verdict = cv.evaluate_frame(_frame())
        self.assertEqual(verdict.quality_by_domain["door"], cv.VALID)


class DedupAndSequence(unittest.TestCase):
    def test_dedup_key_is_the_documented_triple(self):
        frames = fx.physical_frames(1)
        key = frames[0].dedup_key
        self.assertEqual(len(key), 3)
        self.assertEqual(key[1], "fixtureboot")
        self.assertEqual(key[2], 1)

    def test_duplicate_key_is_detected(self):
        frames = fx.physical_frames(seqs=[1, 1])
        verdicts = cv.evaluate_frames(frames)
        self.assertIn("SEQ_DUPLICATE", verdicts[1].reason_codes)

    def test_same_seq_different_boot_is_not_a_duplicate(self):
        # docs/02 §4.2: identity is per boot; two boots may each emit seq=1.
        frames = [
            fx.physical_frames(seqs=[1], boot_id="aaa")[0],
            fx.physical_frames(seqs=[1], boot_id="bbb")[0],
        ]
        verdicts = cv.evaluate_frames(frames)
        self.assertNotIn("SEQ_DUPLICATE", verdicts[0].reason_codes)
        self.assertNotIn("SEQ_DUPLICATE", verdicts[1].reason_codes)

    def test_seq_gap_is_detected_with_the_lost_count(self):
        frames = fx.physical_frames(seqs=[1, 2, 9])
        verdicts = cv.evaluate_frames(frames)
        gap_rows = [v for v in verdicts if "SEQ_GAP" in v.reason_codes]
        self.assertEqual(len(gap_rows), 1)
        reason = next(r for r in gap_rows[0].reasons if r.code == "SEQ_GAP")
        self.assertIn("6 frame(s) are lost", reason.detail)  # seq 3..8 never arrived

    def test_a_sequence_is_valid_when_contiguous(self):
        verdicts = cv.evaluate_frames(fx.physical_frames(6))
        self.assertFalse(any("SEQ_GAP" in v.reason_codes for v in verdicts))
        self.assertFalse(any("SEQ_DUPLICATE" in v.reason_codes for v in verdicts))

    def test_interpolation_is_never_applied(self):
        frames = fx.physical_frames(seqs=[1, 4])
        self.assertEqual([f.seq for f in frames], [1, 4])
        self.assertEqual(frames[1].values["t1"], frames[0].values["t1"])


class ProvenanceAndSessionClass(unittest.TestCase):
    def test_host_fixture_is_never_valid_as_a_measurement(self):
        frames = fx.fixture_frames(1)
        verdict = cv.evaluate_frame(frames[0])
        self.assertIn("NON_PHYSICAL_SOURCE", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["provenance"], cv.INVALID)
        self.assertEqual(verdict.usable_for, ())

    def test_probe_identification_is_rejected_by_run_label(self):
        frames = fx.physical_frames(1, run_label="PROBE_IDENTIFICATION_TOUCH_1")
        verdict = cv.evaluate_frame(frames[0])
        self.assertIn("EXCLUDED_SESSION_CLASS_PROBE_IDENTIFICATION", verdict.reason_codes)
        self.assertNotIn("S1_NORMAL_BASELINE", verdict.usable_for)

    def test_identification_rejection_survives_a_clean_looking_frame(self):
        # The point of matching on the label: the numbers in a touch window look
        # entirely normal, so a value-based rule would not catch it.
        frames = fx.physical_frames(3, run_label="PROBE_IDENTIFICATION")
        for verdict in cv.evaluate_frames(frames):
            self.assertIn("EXCLUDED_SESSION_CLASS_PROBE_IDENTIFICATION", verdict.reason_codes)

    def test_note_field_is_also_searched(self):
        frames = fx.physical_frames(1, note="session class PROBE_IDENTIFICATION")
        self.assertIn(
            "EXCLUDED_SESSION_CLASS_PROBE_IDENTIFICATION",
            _row_codes(frames[0]),
        )

    def test_a_normal_physical_run_is_not_excluded(self):
        frames = fx.physical_frames(1, run_label="S1_BASELINE_A")
        self.assertNotIn(
            "EXCLUDED_SESSION_CLASS_PROBE_IDENTIFICATION", _row_codes(frames[0])
        )


class AbsentQualifierFailsClosed(unittest.TestCase):
    """A status column that does not exist is not a status column that passed.

    PHASE: the committed W04 CSV really does carry no door/environment/power
    qualifier, so these absences block; the rule is the blocking, not the count.
    """

    def test_a_removed_probe_qualifier_blocks_its_domain(self):
        frame = _frame()
        del frame.values["t1_status"]
        verdict = cv.evaluate_frame(frame)
        self.assertIn("T1_STATUS_ABSENT", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["thermal"], cv.UNKNOWN)
        self.assertNotIn("S1_NORMAL_BASELINE", verdict.usable_for)
        self.assertNotIn("S2_DOOR_DISTURBANCE", verdict.usable_for)

    def test_a_removed_door_qualifier_blocks_the_door_domain(self):
        frame = _frame()
        del frame.values["door_status"]
        verdict = cv.evaluate_frame(frame)
        self.assertIn("DOOR_STATUS_ABSENT", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["door"], cv.UNKNOWN)
        self.assertNotIn("S1_NORMAL_BASELINE", verdict.usable_for)
        self.assertNotIn("S2_DOOR_DISTURBANCE", verdict.usable_for)

    def test_every_watched_qualifier_has_an_absence_code(self):
        # Dropping any one of them must produce a named reason, not silence.
        for domain, fields in cv.STATUS_FIELDS_BY_DOMAIN.items():
            for field in fields:
                with self.subTest(field=field):
                    frame = _frame()
                    del frame.values[field]
                    verdict = cv.evaluate_frame(frame)
                    self.assertIn(f"{field.upper()}_ABSENT", verdict.reason_codes)
                    self.assertEqual(verdict.quality_by_domain[domain], cv.UNKNOWN)
                    self.assertIn(f"{field.upper()}_ABSENT", cv.ABSENT_STATUS_CODES)

    def test_presence_of_the_column_is_what_changes_the_verdict(self):
        # Same values, one column removed: the only difference is knowability.
        kept = cv.evaluate_frame(_frame())
        frame = _frame()
        del frame.values["air_c_status"]
        dropped = cv.evaluate_frame(frame)
        self.assertEqual(kept.quality_by_domain["environment"], cv.VALID)
        self.assertEqual(dropped.quality_by_domain["environment"], cv.UNKNOWN)
        self.assertNotIn("S1_NORMAL_BASELINE", dropped.usable_for)

    def test_absent_is_not_degraded(self):
        # DEGRADED would read as "a documented degraded path remains legal"; an
        # unreported qualifier is not a documented path, it is an unknown.
        frame = _frame()
        del frame.values["t2_status"]
        reason = next(r for r in cv.evaluate_frame(frame).reasons
                      if r.code == "T2_STATUS_ABSENT")
        self.assertEqual(reason.quality, cv.UNKNOWN)
        self.assertIn(reason.quality, cv.BLOCKING_SEVERITIES)


class CoolingStateObserved(unittest.TestCase):
    """docs/01 §17.8: ON/OFF is a state; never observed is a third thing."""

    def test_a_frame_with_no_state_never_observed_the_cooling(self):
        frame = _frame()
        del frame.values["state"]
        verdict = cv.evaluate_frame(frame)
        self.assertIn("COOLING_STATE_UNOBSERVED", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["producer"], cv.UNKNOWN)
        self.assertNotIn("S1_NORMAL_BASELINE", verdict.usable_for)
        self.assertNotIn("S2_DOOR_DISTURBANCE", verdict.usable_for)

    def test_an_empty_state_column_is_the_same_unknown(self):
        frame = _frame()
        frame.values["state"] = ""
        self.assertIn("COOLING_STATE_UNOBSERVED", cv.evaluate_frame(frame).reason_codes)

    def test_a_duty_cycle_is_not_a_substitute_for_the_state(self):
        # pwm_applied_permille=0 is also what an unstarted controller reports.
        frame = _frame()
        del frame.values["state"]
        frame.values["pwm_applied_permille"] = 0
        verdict = cv.evaluate_frame(frame)
        self.assertIn("COOLING_STATE_UNOBSERVED", verdict.reason_codes)
        self.assertNotIn("S1_NORMAL_BASELINE", verdict.usable_for)

    def test_an_unrecognised_state_is_unknown_not_assumed_off(self):
        verdict = cv.evaluate_frame(_frame(state="MAINTENANCE"))
        self.assertIn("COOLING_STATE_UNRECOGNISED", verdict.reason_codes)
        self.assertEqual(verdict.quality_by_domain["producer"], cv.UNKNOWN)

    def test_a_reported_off_state_is_accepted(self):
        verdict = cv.evaluate_frame(_frame(state="OFF"))
        self.assertNotIn("COOLING_STATE_UNOBSERVED", verdict.reason_codes)
        self.assertNotIn("COOLING_STATE_UNRECOGNISED", verdict.reason_codes)

    def test_the_phase_label_still_refuses_to_invent_a_state(self):
        frames = fx.physical_frames(1, state="MAINTENANCE")
        self.assertEqual(ex.classify_phase(frames[0]), ex.PHASE_ARMED_OTHER)
        verdict = cv.evaluate_frame(frames[0])
        self.assertNotIn("S1_NORMAL_BASELINE", verdict.usable_for)


class QualityVocabularyIsClosed(unittest.TestCase):
    """docs/01 §19.4: an unrecorded or unrecognised token is not a pass."""

    def test_worst_of_an_unrecorded_token_is_unknown(self):
        self.assertEqual(cv.worst(["GOOD"]), cv.UNKNOWN)
        self.assertEqual(cv.worst(["bogus"]), cv.UNKNOWN)
        self.assertEqual(cv.worst([]), cv.UNKNOWN)

    def test_worst_still_ranks_the_known_vocabulary(self):
        self.assertEqual(cv.worst([cv.VALID, cv.DEGRADED]), cv.DEGRADED)
        self.assertEqual(cv.worst([cv.VALID, cv.UNKNOWN, cv.DEGRADED]), cv.UNKNOWN)
        self.assertEqual(cv.worst([cv.DEGRADED, cv.INVALID]), cv.INVALID)
        self.assertEqual(cv.worst([cv.VALID]), cv.VALID)

    def test_an_unknown_quality_is_refused_where_it_is_written(self):
        with self.assertRaises(ValueError):
            cv.Reason("X", "GOOD", "thermal", "d", "docs/01 §19.4")
        with self.assertRaises(ValueError):
            cv.Reason("X", "", "thermal", "d", "docs/01 §19.4")

    def test_an_unknown_domain_is_refused(self):
        with self.assertRaises(ValueError):
            cv.Reason("X", cv.UNKNOWN, "vibes", "d", "docs/01 §19.4")

    def test_domain_quality_refuses_to_be_asked_without_naming_domains(self):
        with self.assertRaises(TypeError):
            cv.domain_quality([])  # type: ignore[call-arg]

    def test_a_domain_that_was_not_evaluated_is_unknown_not_valid(self):
        out = cv.domain_quality([], ("thermal",))
        self.assertEqual(out["thermal"], cv.VALID)
        for domain in set(cv.DOMAINS) - {"thermal"}:
            self.assertEqual(out[domain], cv.UNKNOWN)
        with self.assertRaises(ValueError):
            cv.domain_quality([], ("not_a_domain",))

    def test_an_unevaluated_domain_blocks_a_scenario_that_needs_it(self):
        # A clean thermal sheet says nothing about the door; S1 needs the door.
        out = cv.domain_quality([], ("provenance", "producer", "thermal", "environment",
                                     "sequence"))
        self.assertNotIn("S1_NORMAL_BASELINE", cv.scenarios_usable(out))


class CommittedCaptureBehaviour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        cls.verdicts = cv.evaluate_frames(cls.frames)
        cls.summary = cv.summarize(cls.verdicts)

    def test_the_first_17_rows_are_the_startup_invalid_block(self):
        for index in range(17):
            self.assertIn("SNAPSHOT_INVALID", self.verdicts[index].reason_codes)
        self.assertNotIn("SNAPSHOT_INVALID", self.verdicts[17].reason_codes)

    def test_a_row_with_an_unreadable_door_is_never_counted_as_a_quiet_row(self):
        # Property, not a count: whatever the total, an unknown door never becomes
        # a closed door and never certifies the absence of a disturbance.
        unknown = [v for v in self.verdicts if "DOOR_STATE_UNKNOWN" in v.reason_codes]
        self.assertTrue(unknown)
        for verdict in unknown:
            self.assertEqual(verdict.quality_by_domain["door"], cv.UNKNOWN)
            self.assertNotIn("S1_NORMAL_BASELINE", verdict.usable_for)
            self.assertNotIn("S2_DOOR_DISTURBANCE", verdict.usable_for)
        self.assertEqual(
            len(unknown),
            sum(1 for f in self.frames if f.values.get("door_open") in (None, "UNKNOWN")),
        )

    def test_a_value_with_no_producer_qualifier_never_becomes_a_qualified_domain(self):
        for index, frame in enumerate(self.frames):
            unqualified = [
                field for field, status_field in cv.ELECTRICAL_STATUS_OF.items()
                if status_field is not None
                and frame.has(field) and frame.values.get(field) is not None
                and frame.values.get(status_field) in (None, "")
            ]
            if not unqualified:
                continue
            verdict = self.verdicts[index]
            self.assertEqual(verdict.quality_by_domain["electrical"], cv.UNKNOWN,
                             f"row {index} promoted unqualified {unqualified}")
            self.assertNotIn("S4_ACTUATION_RESPONSE_FAULT", verdict.usable_for)

    def test_no_row_is_dropped(self):
        self.assertEqual(self.summary["rows_total"], len(self.frames))

    def test_summary_reports_zero_count_codes_too(self):
        # 'checked and found none' must not look like 'did not check'.
        self.assertEqual(self.summary["reason_counts"].get("SEQ_GAP", 0), 0)
        self.assertIn("SEQ_GAP", self.summary["reason_codes_checked"])

    def test_every_code_the_layer_can_emit_is_declared_as_checked(self):
        # A reason code that fires but is not listed is a rule nobody can audit.
        emitted = {code for verdict in self.verdicts for code in verdict.reason_codes}
        self.assertEqual(
            sorted(emitted - set(self.summary["reason_codes_checked"])), [],
            "the summary declares fewer codes than the layer emits",
        )

    def test_electrical_scenarios_are_not_supported_by_this_capture(self):
        self.assertEqual(self.summary["rows_usable_per_scenario"]["S4_ACTUATION_RESPONSE_FAULT"], 0)

    def test_phase_snapshot_the_committed_csv_cannot_qualify_door_environment_or_power(self):
        """PHASE SNAPSHOT - MUST EVOLVE when the encoding carries the qualifiers.

        This asserts today's defect, so it is expected to fail the day firmware
        starts writing door_status/air_c_status/rh_pct_status/power_w_status into
        the derived table. That failure is the point: it must be met by retiring
        the snapshot, never by flipping the assertion, because the durable rule is
        in AbsentQualifierFailsClosed, not here.
        """
        for code in ("DOOR_STATUS_ABSENT", "AIR_C_STATUS_ABSENT",
                     "RH_PCT_STATUS_ABSENT", "POWER_W_STATUS_ABSENT"):
            self.assertEqual(self.summary["reason_counts"].get(code, 0), 957, code)
        for domain in ("door", "environment", "electrical"):
            self.assertEqual(self.summary["quality_counts_by_domain"][domain][cv.UNKNOWN], 957)

    def test_phase_snapshot_thermal_rows_and_the_scenario_count_are_not_the_same_claim(self):
        """PHASE SNAPSHOT - MUST EVOLVE with the capture, not with the rules.

        940 rows are clean enough for a mixed-probe thermal statistic; 0 rows are
        usable for the S1 *scenario*, because that scenario also asks for the door
        and environment domains this encoding cannot qualify. The two figures are
        reported apart so a partial count can never be read as the full one.
        """
        self.assertEqual(self.summary["rows_thermally_usable_for_statistics"], 940)
        self.assertEqual(self.summary["rows_usable_for_baseline"], 0)
        self.assertLessEqual(
            self.summary["rows_usable_for_baseline"],
            self.summary["rows_thermally_usable_for_statistics"],
        )


if __name__ == "__main__":
    unittest.main()
