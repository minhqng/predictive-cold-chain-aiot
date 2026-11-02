"""Tests for the W12 drift audit (A-W12-01 .. A-W12-05).

The tests split in two: synthetic fixtures pin the *rules* (pooling by
configuration, probe-identification exclusion, role contradictions, PZEM stale
reads, honesty of the gate G3 input), and one test runs the committed W04 cooling
capture so the tool's numbers reproduce against real device bytes rather than
only against a hand-made CSV.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

# The W12 validator is imported below to unit-test its honesty helper. Importing
# it would otherwise drop a ``validate_w12.*.pyc`` into the W12 dossier, which is
# exactly the committed-bytecode-cache defect the validator now fails on. Suppress
# bytecode writing for this test process so running the suite never dirties the
# pinned dossier.
sys.dont_write_bytecode = True

TOOLS = pathlib.Path(__file__).resolve().parents[1]
REPO = TOOLS.parent.parent
sys.path.insert(0, str(TOOLS))

import cg_w12_drift_audit as w12  # noqa: E402

# The W12 validator exposes a pure qualification-claim helper; import it so the
# "fail a claim without evidence, never qualification itself" rule is unit-tested.
sys.path.insert(0, str(REPO / "evidence" / "A" / "W12"))
import validate_w12  # noqa: E402

COOLING = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"

_COLUMNS = ["seq", "device_ms", "pwm_applied_permille", "current_a", "voltage_v",
            "current_status", "voltage_status", "bme_air_c",
            "t1_c", "t1_status", "t1_role", "t2_c", "t2_status", "t2_role",
            "t3_c", "t3_status", "t3_role", "t4_c", "t4_status", "t4_role",
            "door_open", "door_polarity", "session", "limits_policy", "boot_id",
            "physical_output"]


def _row(**kw) -> dict[str, str]:
    """A dict row (what csv.DictReader yields) with blank defaults for absent keys."""
    base = {c: "" for c in _COLUMNS}
    base.update({k: str(v) for k, v in kw.items()})
    return base


def _write_csv(dirpath: pathlib.Path, name: str, rows) -> pathlib.Path:
    p = dirpath / name
    lines = [",".join(_COLUMNS)]
    for r in rows:
        lines.append(",".join(r.get(c, "") for c in _COLUMNS))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return p


class SensorConsistencyTests(unittest.TestCase):
    def test_hot_side_is_never_folded_into_chamber_air(self) -> None:
        rows = [_row(seq=i, device_ms=i * 1000, pwm_applied_permille="999",
                     current_a="5.0", bme_air_c="10.0",
                     t1_c="10", t1_role="CHAMBER_CENTER",
                     t2_c="100", t2_role="TEC_HOT_SIDE",
                     t3_c="10", t3_role="CHAMBER_BOTTOM",
                     t4_c="10", t4_role="CHAMBER_NEAR_DOOR",
                     door_open="0", door_polarity="CONFIRMED",
                     session="synthetic", limits_policy="APPROVED")
                for i in range(10)]
        result = w12.sensor_consistency(rows)
        self.assertEqual(result["slot_offsets"]["t2"]["mean_c"], 100.0)
        self.assertEqual(result["chamber_air_agreement"]["mean_c"], 0.0)
        self.assertTrue(result["hot_side_reported_separately"])

    def test_agreement_ignores_the_hot_side_spread(self) -> None:
        rows = [_row(seq=i, device_ms=i * 1000, pwm_applied_permille="999",
                     t1_c="10", t1_role="CHAMBER_CENTER",
                     t2_c="100", t2_role="TEC_HOT_SIDE",
                     t3_c="10.5", t3_role="CHAMBER_BOTTOM",
                     t4_c="9.5", t4_role="CHAMBER_NEAR_DOOR")
                for i in range(6)]
        result = w12.sensor_consistency(rows)
        self.assertAlmostEqual(result["chamber_air_agreement"]["mean_c"], 1.0)


class RoleGeometryTests(unittest.TestCase):
    def test_capturing_a_conflicting_role_is_flagged(self) -> None:
        rows = [_row(seq=0, t1_c="10", t1_role="CHAMBER_CENTER",
                     t2_c="100", t2_role="CHAMBER_CENTER",   # T2 mislabeled as center
                     t3_c="10", t3_role="CHAMBER_BOTTOM",
                     t4_c="10", t4_role="CHAMBER_NEAR_DOOR")]
        audit = w12.role_geometry_audit(rows, pathlib.Path("weird.csv"))
        self.assertIn("ROLE_CONTRADICTION", {f["kind"] for f in audit["contradictions"]})
        self.assertEqual(audit["verdict"], "ROLE_DISAGREEMENT")

    def test_unassigned_roles_are_a_label_gap_not_a_contradiction(self) -> None:
        rows = [_row(seq=0, t1_role="UNASSIGNED", t2_role="HOT_SIDE",
                     t3_role="UNASSIGNED", t4_role="UNASSIGNED", door_polarity="UNCONFIRMED")]
        audit = w12.role_geometry_audit(rows, pathlib.Path("gap.csv"))
        self.assertEqual(audit["contradictions"], [])
        self.assertEqual(audit["role_label_status"]["t1"], "UNLABELLED")
        self.assertEqual(audit["role_label_status"]["t2"], "LABELLED")


class ProbeIdentificationExclusionTests(unittest.TestCase):
    def test_probe_id_capture_is_classified_and_excluded(self) -> None:
        self.assertTrue(w12.is_probe_identification(
            pathlib.Path("evidence/A/W07/probe-identification/touch_1.log")))
        self.assertFalse(w12.is_probe_identification(
            pathlib.Path("evidence/A/W04/tec-cooling-response-600s.csv")))

    def test_probe_id_capture_never_produces_drift_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td)
            p = _write_csv(d, "probe-identification_touch_1.csv",
                           [_row(seq=0, pwm_applied_permille="0", t1_c="30",
                                 t1_role="CHAMBER_CENTER", t2_c="30", t2_role="TEC_HOT_SIDE",
                                 t3_c="30", t3_role="CHAMBER_BOTTOM",
                                 t4_c="30", t4_role="CHAMBER_NEAR_DOOR",
                                 session="probe-identification session")])
            cap = w12.audit_capture(p)
            self.assertTrue(cap["is_probe_identification"])
            self.assertEqual(cap["sensor_consistency"]["status"], "EXCLUDED_PROBE_IDENTIFICATION")
            self.assertEqual(cap["pzem_audit"]["status"], "EXCLUDED_PROBE_IDENTIFICATION")
            self.assertEqual(cap["role_geometry_audit"]["verdict"], "PROBE_IDENTIFICATION_EXCLUDED")


class PzemZeroActiveTests(unittest.TestCase):
    def test_duty_zero_current_frames_listed_individually_not_averaged(self) -> None:
        rows = [
            _row(seq=0, pwm_applied_permille="0", current_a="7.15", t2_c="30", t2_role="TEC_HOT_SIDE"),
            _row(seq=1, device_ms=1000, pwm_applied_permille="0", current_a="0.02"),
            _row(seq=2, device_ms=2000, pwm_applied_permille="999", current_a="7.2"),
        ]
        audit = w12.pzem_zero_active_audit(rows)
        self.assertTrue(audit["duty0_with_current_frames"]["listed_individually_never_averaged"])
        stale = audit["duty0_with_current_frames"]["stale_register_frames"]
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["current_a"], 7.15)
        self.assertEqual(audit["electrical_qualification"], "UNQUALIFIED")


class PoolingRefusalTests(unittest.TestCase):
    def test_mixed_configurations_are_never_pooled_into_one_number(self) -> None:
        caps = [
            {"configuration": "image:AAA", "sensor_consistency": {"slot_offsets": {"t1": {"mean_c": 20.0}}}},
            {"configuration": "image:BBB", "sensor_consistency": {"slot_offsets": {"t1": {"mean_c": 25.0}}}},
        ]
        drift = w12.cross_session_drift(caps)
        self.assertIsNone(drift["pooled"])
        self.assertIn("pooled_refused_reason", drift)
        self.assertEqual(drift["per_configuration"]["image:AAA"]["sessions"], 1)
        self.assertIsNone(drift["per_configuration"]["image:AAA"]["range_c"])

    def test_signoff_table_marks_poolable_groups_by_configuration(self) -> None:
        captures = [
            {"capture": "a.csv", "configuration": "image:AAA",
             "role_geometry_audit": {"is_probe_identification": False, "verdict": "CONSISTENT_WITH_FREEZE"},
             "pzem_audit": {"electrical_qualification": "UNQUALIFIED"}},
            {"capture": "b.csv", "configuration": "image:BBB",
             "role_geometry_audit": {"is_probe_identification": False, "verdict": "ROLE_DISAGREEMENT"},
             "pzem_audit": {"electrical_qualification": "UNQUALIFIED"}},
        ]
        signoff = w12.hardware_config_signoff(captures)
        self.assertEqual(len(signoff["poolable_groups"]), 2)
        # The label may be present, but never as a column a consumer can read as a
        # certified configuration identity while signoff is unresolved.
        self.assertEqual(signoff["intended_hardware_config"], w12.INTENDED_HARDWARE_CONFIG)
        self.assertEqual(signoff["configuration_signoff_status"], "UNRESOLVED")
        for row in signoff["dataset_validity_table"]:
            self.assertNotIn("hardware_config_id", row)
            self.assertEqual(row["config_verification"], "UNVERIFIED")


class HonestyGateTests(unittest.TestCase):
    def test_gate_g3_input_refuses_to_sign_off_from_host_and_owns_no_green(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td)
            p = _write_csv(d, "c.csv",
                           [_row(seq=0, pwm_applied_permille="999", current_a="5", t2_c="30",
                                 t2_role="TEC_HOT_SIDE", t1_c="10", t1_role="CHAMBER_CENTER",
                                 t3_c="10", t3_role="CHAMBER_BOTTOM",
                                 t4_c="10", t4_role="CHAMBER_NEAR_DOOR", session="s")])
            report = w12.build_report([p])
            g3 = report["gate_g3_input"]
            # The A-side status is never a whole-team GREEN; it is an explicit
            # NEED_USER_ACTION and it refuses to sign off from host evidence.
            self.assertEqual(g3["a_side_status"], "NEED_USER_ACTION")
            self.assertNotEqual(g3["a_side_status"].upper(), "GREEN")
            self.assertIn("CANNOT BE SIGNED OFF", g3["statement"])
            self.assertTrue(g3["does_not_declare"].startswith("G3"))
            self.assertTrue(report["physical_verified"] is False)


class RealCaptureTests(unittest.TestCase):
    @unittest.skipUnless(COOLING.is_file(), "committed cooling capture not present")
    def test_tool_runs_on_the_committed_w04_cooling_capture(self) -> None:
        report = w12.build_report([COOLING])
        cap = report["captures"][0]
        self.assertIn("01cedce3", cap["configuration"])
        self.assertFalse(cap["is_probe_identification"])
        self.assertEqual(cap["role_geometry_audit"]["verdict"], "CONSISTENT_WITH_FREEZE")
        self.assertEqual(cap["pzem_audit"]["electrical_qualification"], "UNQUALIFIED")
        stale = cap["pzem_audit"]["duty0_with_current_frames"]["stale_register_frames"]
        self.assertTrue(any(s["current_a"] == 7.15 for s in stale))
        self.assertGreater(cap["sensor_consistency"]["slot_offsets"]["t2"]["mean_c"],
                           cap["sensor_consistency"]["slot_offsets"]["t1"]["mean_c"])


class ConfigurationKeyingTests(unittest.TestCase):
    """H1: configuration identity must use evidence that separates sessions."""

    def _row(self, **kw):
        base = _row(**kw)
        return base

    def test_no_image_marker_keys_by_boot_not_limits(self) -> None:
        # Two captures with the SAME limits_policy but DIFFERENT boot identities
        # and no installed-image marker must NOT collapse into one config key.
        # The reverted (buggy) ordering tested the limits_policy column before
        # the boot fallback, so both keyed as "limits_policy:APPROVED" here.
        a = w12.configuration_of(pathlib.Path("a.csv"),
                                 [_row(seq=0, boot_id="bootAAAA", limits_policy="APPROVED")])
        b = w12.configuration_of(pathlib.Path("b.csv"),
                                 [_row(seq=0, boot_id="bootBBBB", limits_policy="APPROVED")])
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, "limits_policy:APPROVED")
        self.assertIn("bootAAAA", a)
        self.assertIn("bootBBBB", b)

    def test_installed_image_and_limits_still_group_a_configuration(self) -> None:
        # Same installed image + same limits = one configuration regardless of boot.
        a = w12.configuration_of(pathlib.Path("a.csv"),
                                 [_row(seq=0, session="image 01cedce3 run",
                                       limits_policy="APPROVED", boot_id="bootX")])
        b = w12.configuration_of(pathlib.Path("b.csv"),
                                 [_row(seq=0, session="image 01cedce3 run",
                                       limits_policy="APPROVED", boot_id="bootY")])
        self.assertEqual(a, b)
        self.assertIn("01cedce3", a)

    def test_byte_copy_sharing_boot_is_not_pooled_into_zero_drift(self) -> None:
        # A byte-copy of one capture filed under a new name is ONE physical session
        # (same boot identity + same content). It must never show up as a 2-session
        # "zero intra-configuration drift" while the pooled refusal still claims refusal.
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td)
            rows = [_row(seq=i, device_ms=i * 1000, pwm_applied_permille="999",
                         t1_c="10", t1_status="OK", t2_c="30", t2_status="OK",
                         t3_c="10", t3_status="OK", t4_c="10", t4_status="OK",
                         boot_id="56044b74", session="image 01cedce3 run",
                         limits_policy="APPROVED") for i in range(5)]
            _write_csv(d, "orig.csv", rows)
            _write_csv(d, "copy_renamed.csv", rows)  # identical bytes, new name
            report = w12.build_report([d / "orig.csv", d / "copy_renamed.csv"])
            drift = report["cross_session_drift"]
            self.assertIsNone(drift["pooled"])
            per = drift["per_configuration"]
            self.assertEqual(len(per), 1)  # one configuration
            entry = next(iter(per.values()))
            self.assertEqual(entry["sessions"], 1)   # one distinct physical session
            self.assertIsNone(entry["range_c"])       # drift NOT manufactured


class QualityTokenTests(unittest.TestCase):
    """M6: a mean may only be taken over the valid state; count exclusions."""

    def test_nonvalid_status_is_skipped_and_counted_not_averaged(self) -> None:
        rows = [
            _row(seq=0, t1_c="10", t1_status="OK", t3_c="10", t3_status="OK",
                 t4_c="10", t4_status="OK"),
            _row(seq=1, t1_c="99", t1_status="FAIL", t3_c="10", t3_status="OK",
                 t4_c="10", t4_status="OK"),
            _row(seq=2, t1_c="10", t1_status="OK", t3_c="10", t3_status="OK",
                 t4_c="10", t4_status="OK"),
        ]
        result = w12.sensor_consistency(rows)
        # The FAIL frame's 99 C is excluded; the t1 mean is over the two valid 10 C.
        self.assertEqual(result["slot_offsets"]["t1"]["mean_c"], 10.0)
        self.assertEqual(result["slot_offsets"]["t1"]["excluded_nonvalid_terms"], 1)
        # The trio agreement excludes the frame carrying a non-valid term.
        self.assertEqual(result["chamber_air_agreement"]["n"], 2)
        self.assertGreaterEqual(
            result["chamber_air_agreement"]["excluded_nonvalid_terms"], 1)

    def test_empty_status_is_treated_as_valid_for_backward_compatibility(self) -> None:
        rows = [_row(seq=0, t1_c="12", t3_c="12", t4_c="12")]  # status columns blank
        result = w12.sensor_consistency(rows)
        self.assertEqual(result["slot_offsets"]["t1"]["mean_c"], 12.0)
        self.assertNotIn("excluded_nonvalid_terms", result["slot_offsets"]["t1"])


class ProbeIdentificationContentTests(unittest.TestCase):
    """M8: classify from path AND session/content, not path alone."""

    def test_session_field_content_triggers_exclusion_even_without_path_marker(self) -> None:
        rows = [_row(seq=0, pwm_applied_permille="999", t1_c="30", t2_c="30",
                     t3_c="30", t4_c="30",
                     session="probe-identification touch session")]
        self.assertTrue(w12.is_probe_identification(pathlib.Path("capture.csv"), rows))

    def test_audit_capture_excludes_a_content_flagged_probe_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td)
            # File name says nothing; only the session content marks it as probe-id.
            p = _write_csv(d, "mystery-session.csv",
                           [_row(seq=0, pwm_applied_permille="999", t1_c="30", t1_status="OK",
                                 t2_c="30", t2_status="OK", t3_c="30", t3_status="OK",
                                 t4_c="30", t4_status="OK",
                                 session="probe-identification touch session")])
            cap = w12.audit_capture(p)
            self.assertTrue(cap["is_probe_identification"])
            self.assertEqual(cap["sensor_consistency"]["status"], "EXCLUDED_PROBE_IDENTIFICATION")


class ValidatorQualificationClaimTests(unittest.TestCase):
    """H4: the validator fails a claim without evidence, never qualification itself."""

    def test_qualified_without_evidence_fails(self) -> None:
        audit = {"captures": [{"capture": "c.csv", "pzem_audit": {
            "electrical_qualification": "QUALIFIED",
            "qualified_frame_evidence": {"frames_with_nonempty_status": 0}}}] }
        failures = validate_w12.check_pzem_qualification_claim(audit)
        self.assertTrue(failures)

    def test_qualified_with_validating_tokens_passes(self) -> None:
        audit = {"captures": [{"capture": "c.csv", "pzem_audit": {
            "electrical_qualification": "QUALIFIED",
            "qualified_frame_evidence": {"frames_with_nonempty_status": 5,
                                         "frames_with_valid_status": 5}}}] }
        self.assertEqual(validate_w12.check_pzem_qualification_claim(audit), [])

    def test_nonempty_status_alone_is_no_longer_accepted_as_evidence(self) -> None:
        """The old evidence key counted any filled cell, INVALID included."""
        audit = {"captures": [{"capture": "c.csv", "pzem_audit": {
            "electrical_qualification": "QUALIFIED",
            "qualified_frame_evidence": {"frames_with_nonempty_status": 5,
                                         "frames_with_valid_status": 0}}}] }
        self.assertTrue(validate_w12.check_pzem_qualification_claim(audit))

    def test_unqualified_current_capture_does_not_fail(self) -> None:
        audit = {"captures": [{"capture": "c.csv", "pzem_audit": {
            "electrical_qualification": "UNQUALIFIED"}}] }
        self.assertEqual(validate_w12.check_pzem_qualification_claim(audit), [])



class ElectricalQualificationTokenTests(unittest.TestCase):
    """A non-empty status cell is not evidence of validity - only the producer's OK is."""

    def _audit(self, current_status, voltage_status, n=3):
        rows = [_row(seq=i, device_ms=i * 1000, pwm_applied_permille="999",
                     current_a="7.2", voltage_v="12.0",
                     current_status=current_status, voltage_status=voltage_status)
                for i in range(n)]
        return w12.pzem_zero_active_audit(rows)

    def test_empty_everywhere_is_unqualified(self) -> None:
        out = self._audit("", "")
        self.assertEqual(out["electrical_qualification"], "UNQUALIFIED")
        self.assertEqual(out["qualified_frame_evidence"]["frames_with_valid_status"], 0)

    def test_both_channels_ok_is_qualified(self) -> None:
        out = self._audit("OK", "OK")
        self.assertEqual(out["electrical_qualification"], "QUALIFIED")
        self.assertEqual(out["qualified_frame_evidence"]["frames_with_valid_status"], 3)

    def test_one_channel_ok_is_partially_qualified(self) -> None:
        out = self._audit("OK", "")
        self.assertEqual(out["electrical_qualification"], "PARTIALLY_QUALIFIED")
        per = out["qualified_frame_evidence"]["per_channel"]
        self.assertEqual(per["current_status"]["valid"], 3)
        self.assertEqual(per["voltage_status"]["valid"], 0)

    def test_an_error_token_never_qualifies(self) -> None:
        """TIMEOUT/CRC_ERR/INVALID are non-empty; the old code counted them as evidence."""
        for token in ("TIMEOUT", "CRC_ERR", "BAD_SLAVE", "INVALID", "STALE", "UNKNOWN",
                      "banana"):
            out = self._audit(token, token)
            self.assertEqual(out["electrical_qualification"], "UNQUALIFIED", token)
            self.assertEqual(out["qualified_frame_evidence"]["frames_with_valid_status"], 0,
                             token)

    def test_unsupported_tokens_are_named_not_swallowed(self) -> None:
        out = self._audit("banana", "")
        census = out["qualified_frame_evidence"]["per_channel"]["current_status"]
        self.assertEqual(census["unsupported"], 3)
        self.assertIn("banana", census["tokens_seen"])

    def test_mixed_ok_and_empty_is_partly_qualified(self) -> None:
        rows = [_row(seq=0, pwm_applied_permille="999", current_a="7.2",
                     current_status="OK", voltage_status="OK"),
                _row(seq=1, device_ms=1000, pwm_applied_permille="999", current_a="7.2",
                     current_status="", voltage_status="")]
        out = w12.pzem_zero_active_audit(rows)
        self.assertEqual(out["electrical_qualification"], "PARTIALLY_QUALIFIED")
        self.assertEqual(out["qualified_frame_evidence"]["frames_with_valid_status"], 1)

    def test_validator_fails_a_partially_qualified_claim_without_a_valid_token(self) -> None:
        audit = {"captures": [{"capture": "x.csv", "pzem_audit": {
            "electrical_qualification": "PARTIALLY_QUALIFIED",
            "duty0_with_current_frames": {"listed_individually_never_averaged": True},
            "qualified_frame_evidence": {"frames_with_nonempty_status": 5,
                                         "frames_with_valid_status": 0}}}]}
        self.assertTrue(validate_w12.check_pzem_qualification_claim(audit))
        audit["captures"][0]["pzem_audit"]["qualified_frame_evidence"][
            "frames_with_valid_status"] = 5
        self.assertEqual(validate_w12.check_pzem_qualification_claim(audit), [])

    def test_validator_rejects_an_unpublished_qualification_word(self) -> None:
        audit = {"captures": [{"capture": "x.csv", "pzem_audit": {
            "electrical_qualification": "GOOD_ENOUGH",
            "duty0_with_current_frames": {"listed_individually_never_averaged": True}}}]}
        self.assertTrue(validate_w12.check_pzem_qualification_claim(audit))


class ConfigIdentitySeparationTests(unittest.TestCase):
    """An intended label must not read as a verified configuration identity."""

    @staticmethod
    def _cap(name, image, boots, roles_frozen=True):
        return {"capture": name, "configuration": f"config:image={image}|limits=APPROVED",
                "boot_ids": boots, "image_sha256": image,
                "role_geometry_audit": {
                    "is_probe_identification": False,
                    "rom_readback_verified": False,
                    "role_label_status": ({"t1": "LABELLED", "t2": "LABELLED",
                                           "t3": "LABELLED", "t4": "LABELLED"}
                                          if roles_frozen else {"t1": "UNLABELLED"}),
                    "verdict": "MATCH"},
                "pzem_audit": {"electrical_qualification": "UNQUALIFIED"}}

    def test_no_row_is_stampable_as_a_certified_config_id(self) -> None:
        out = w12.hardware_config_signoff([self._cap("a.csv", "img1", ["b1"])])
        for row in out["dataset_validity_table"]:
            self.assertNotIn("hardware_config_id", row)
            self.assertEqual(row["intended_hardware_config"], w12.INTENDED_HARDWARE_CONFIG)
            self.assertEqual(row["config_verification"], "UNVERIFIED")
            self.assertTrue(row["verification_open_items"])
        self.assertEqual(out["configuration_signoff_status"], "UNRESOLVED")

    def test_two_independent_boots_of_one_identity_stay_poolable(self) -> None:
        out = w12.hardware_config_signoff([
            self._cap("a.csv", "img1", ["b1"]), self._cap("b.csv", "img1", ["b2"])])
        groups = out["poolable_groups"]
        self.assertEqual(len(groups), 1, "a legitimate two-session comparison was split")
        self.assertEqual(sorted(next(iter(groups.values()))), ["a.csv", "b.csv"])

    def test_different_images_never_share_a_pooling_group(self) -> None:
        out = w12.hardware_config_signoff([
            self._cap("a.csv", "img1", ["b1"]), self._cap("b.csv", "img2", ["b2"])])
        self.assertEqual(len(out["poolable_groups"]), 2)

    def test_missing_image_evidence_is_named_as_an_open_item(self) -> None:
        cap = self._cap("a.csv", "img1", ["b1"])
        cap["image_sha256"] = None
        out = w12.hardware_config_signoff([cap])
        items = out["dataset_validity_table"][0]["verification_open_items"]
        self.assertTrue(any("image" in item.lower() for item in items), items)

    def test_unlabelled_roles_are_an_open_item(self) -> None:
        out = w12.hardware_config_signoff([self._cap("a.csv", "img1", ["b1"],
                                                     roles_frozen=False)])
        items = out["dataset_validity_table"][0]["verification_open_items"]
        self.assertTrue(any("role labels" in item.lower() for item in items), items)


class ConductorUnitTests(unittest.TestCase):
    def test_the_record_states_diameter_and_the_derivation_assumption(self) -> None:
        text = w12.CONDUCTOR_OBSERVED
        self.assertIn("diameter", text)
        self.assertIn("solid", text)
        self.assertIn("not confirmed", text.lower())
        self.assertNotIn("1.75 mm^2 (operator-confirmed", text)

    def test_the_derived_area_is_the_steady_value_for_a_solid_round_core(self) -> None:
        self.assertAlmostEqual(w12.CONDUCTOR_AREA_IF_SOLID_MM2, 2.405, places=3)


if __name__ == "__main__":
    unittest.main()
