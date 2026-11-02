"""Tests for the W16 comparability framework and the physical-freeze guard.

The framework is only useful if it *blocks* a comparison across a changed
configuration and *never* lets a host-only run declare a physical freeze or a
team G4. These tests pin both of those properties, plus the schema/format
placeholders that must stay NOT_MEASURED.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
REPO = TOOLS.parent.parent
sys.path.insert(0, str(TOOLS))

import cg_w16_comparability as w16  # noqa: E402

COOLING = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"


def _sig(**over) -> dict[str, object]:
    # A fully-populated, genuinely comparable snapshot: all four frozen slots are
    # labelled, the physical output is ENABLED, and the config identity is derived
    # from that evidence (CG-HW-001). Absence on any of these is MISSING_SIDE.
    base = {
        "geometry_roles": {"observed": {"t1": "CHAMBER_CENTER", "t2": "TEC_HOT_SIDE",
                                        "t3": "CHAMBER_BOTTOM", "t4": "CHAMBER_NEAR_DOOR"},
                           "consistent_with_freeze": True, "fully_labelled": True},
        "cadence_hz": 1.0,
        "limits_policy": "APPROVED",
        "image_sha256": w16.BENCH_IMAGE_SHA256[0],
        "physical_output": "ENABLED",
        "hardware_config_id": "CG-HW-001",
    }
    base.update(over)
    return base


class ComparisonGateTests(unittest.TestCase):
    def test_identical_snapshots_are_comparable(self) -> None:
        a = _sig()
        b = _sig()
        cmp = w16.compare_snapshots(a, b)
        self.assertTrue(cmp["comparison_allowed"])
        self.assertEqual(cmp["verdict"], "COMPARABLE")
        self.assertTrue(all(v["state"] == "MATCH" for v in cmp["dimension_table"].values()))

    def test_different_image_blocks_the_comparison(self) -> None:
        a = _sig()
        b = _sig(image_sha256=w16.PRODUCTION_W06_IMAGE_SHA256[0])
        cmp = w16.compare_snapshots(a, b)
        self.assertFalse(cmp["comparison_allowed"])
        self.assertEqual(cmp["verdict"], "BLOCKED")
        self.assertEqual(cmp["dimension_table"]["image_sha256"]["state"], "MISMATCH")

    def test_missing_limits_or_cadence_side_blocks(self) -> None:
        a = _sig()
        b = {d: None for d in w16.COMPARISON_DIMENSIONS}
        cmp = w16.compare_snapshots(a, b)
        self.assertFalse(cmp["comparison_allowed"])
        self.assertIn("MISSING_SIDE",
                      {v["state"] for v in cmp["dimension_table"].values()})

    def test_role_inconsistency_blocks(self) -> None:
        a = _sig()
        b = _sig(geometry_roles={"observed": {}, "consistent_with_freeze": False,
                                 "fully_labelled": False})
        cmp = w16.compare_snapshots(a, b)
        self.assertFalse(cmp["comparison_allowed"])

    def test_unlabelled_geometry_is_missing_not_a_match(self) -> None:
        # H3: the committed baseline labels only T2. Copying that partial geometry on
        # BOTH sides must read as MISSING_SIDE (blocked), never COMPARABLE.
        partial = _sig(geometry_roles={"observed": {"t2": "HOT_SIDE"},
                                       "consistent_with_freeze": True, "fully_labelled": False},
                       hardware_config_id="UNVERIFIED", physical_output="UNQUALIFIED(empty column)")
        cmp = w16.compare_snapshots(partial, dict(partial))
        self.assertFalse(cmp["comparison_allowed"])
        self.assertEqual(cmp["verdict"], "BLOCKED")
        states = {v["state"] for v in cmp["dimension_table"].values()}
        self.assertIn("MISSING_SIDE", states)

    def test_unqualified_physical_output_is_missing_side(self) -> None:
        a = _sig()
        b = _sig(physical_output="UNQUALIFIED(empty column)")
        cmp = w16.compare_snapshots(a, b)
        self.assertEqual(cmp["dimension_table"]["physical_output"]["state"], "MISSING_SIDE")
        self.assertFalse(cmp["comparison_allowed"])


class ConfigurationDriftTests(unittest.TestCase):
    def test_drift_detected_on_a_single_changed_dimension(self) -> None:
        sigs = [_sig(), _sig(cadence_hz=0.5)]
        drift = w16.configuration_drift_detection(sigs)
        dims = {d["dimension"] for d in drift}
        self.assertIn("cadence_hz", dims)

    def test_no_drift_when_everything_matches(self) -> None:
        sigs = [_sig(), _sig()]
        self.assertEqual(w16.configuration_drift_detection(sigs), [])


class NoFreezeGuardTests(unittest.TestCase):
    def test_assert_no_freeze_rejects_a_tampered_frozen_flag(self) -> None:
        report = {"frozen": True, "final_freeze_evidence_schema": {}}
        with self.assertRaises(AssertionError):
            w16.assert_no_freeze(report)

    def test_assert_no_freeze_rejects_a_physical_claim(self) -> None:
        report = {"frozen": False, "verdict": "PHYSICALLY_VERIFIED",
                  "final_freeze_evidence_schema": {}}
        with self.assertRaises(AssertionError):
            w16.assert_no_freeze(report)

    def test_assert_no_freeze_rejects_a_g4_green_claim(self) -> None:
        report = {"frozen": False, "note": "team G4 GREEN",
                  "final_freeze_evidence_schema": {}}
        with self.assertRaises(AssertionError):
            w16.assert_no_freeze(report)

    def test_the_forbidden_labels_list_does_not_self_trip_the_guard(self) -> None:
        # The schema names PHYSICALLY_VERIFIED only to forbid it; the guard must
        # police claims, not the prohibition catalogue.
        report = w16.build_report([COOLING] if COOLING.is_file() else [])
        self.assertIn("PHYSICALLY_VERIFIED",
                      str(report["final_freeze_evidence_schema"]["forbidden_labels"]))
        # Building the report ran the guard without raising:
        self.assertFalse(report["frozen"])
        self.assertTrue(report["no_g4_claim"])


class ToleranceFormatTests(unittest.TestCase):
    def test_tolerances_ship_as_not_measured_placeholders(self) -> None:
        fmt = w16.response_tolerance_format()
        for field in ("initial_state", "gradient", "reset_criterion", "disturbance_tolerance"):
            self.assertEqual(fmt["fields"][field]["value"], "NOT_MEASURED")
        self.assertIn("no field may be filled from host evidence", fmt["policy"])


class ReportOnCommittedCaptureTests(unittest.TestCase):
    @unittest.skipUnless(COOLING.is_file(), "cooling capture absent")
    def test_run_on_authentic_data_asserts_no_freeze_and_blocks(self) -> None:
        report = w16.build_report([COOLING])
        self.assertFalse(report["frozen"])
        self.assertTrue(report["no_g4_claim"])
        self.assertFalse(report["w16_snapshot_present"])
        self.assertEqual(report["cross_era_comparison"]["verdict"], "BLOCKED")
        self.assertEqual(report["verdict"].startswith("NO_FREEZE"), True)
        # The baseline snapshot reads the installed bench image; the geometry flag
        # is True (no contradiction) but only T2 is labelled, so the config identity
        # is UNVERIFIED and comparability is blocked on ABSENCE, not on a real W16 side.
        base = report["baseline_signatures"][0]
        self.assertEqual(base["image_sha256"], w16.BENCH_IMAGE_SHA256[0])
        self.assertTrue(base["geometry_roles"]["consistent_with_freeze"])
        self.assertFalse(base["geometry_roles"]["fully_labelled"])
        self.assertEqual(base["hardware_config_id"], "UNVERIFIED")
        self.assertEqual(base["physical_output"], "UNQUALIFIED(empty column)")
        states = {v["state"] for v in report["cross_era_comparison"]["dimension_table"].values()}
        self.assertIn("MISSING_SIDE", states)


class ProbeIdentificationGuardTests(unittest.TestCase):
    """M8: a touch capture may not become a comparability baseline."""

    def _csv(self, d: pathlib.Path, name: str, session: str) -> pathlib.Path:
        header = ("session,seq,device_ms,pwm_applied_permille,t1_c,t1_status,t1_role,"
                  "t2_c,t2_status,t2_role,t3_c,t3_status,t3_role,t4_c,t4_status,t4_role,"
                  "limits_policy,physical_output,boot_id")
        row = (f"{session},1,1000,999,10,OK,CHAMBER_CENTER,30,OK,TEC_HOT_SIDE,10,OK,"
               "CHAMBER_BOTTOM,10,OK,CHAMBER_NEAR_DOOR,APPROVED,,bX")
        p = d / name
        p.write_text(header + "\n" + row + "\n", encoding="utf-8", newline="\n")
        return p

    def test_probe_id_capture_is_excluded_from_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td)
            p = self._csv(d, "probe-identification_touch.csv", "plant run")
            sig = w16.freeze_signature(w16.load_csv(p), p)
            self.assertTrue(sig.get("is_probe_identification"))
            self.assertEqual(sig.get("status"), "EXCLUDED_PROBE_IDENTIFICATION")
            report = w16.build_report([p])
            # Excluded as a baseline -> the comparison side is empty -> BLOCKED, and
            # the guard did not raise.
            self.assertEqual(report["cross_era_comparison"]["verdict"], "BLOCKED")

    def test_cadence_refused_across_a_boot_change(self) -> None:
        # _cadence_hz must not blend frame gaps across a device reboot.
        rows = [{"device_ms": str(i * 1000), "boot_id": ("bA" if i < 3 else "bB")}
                for i in range(6)]
        self.assertIsNone(w16._cadence_hz(rows))


class NoG4FlagWiringTests(unittest.TestCase):
    """The literal no_g4_claim flag is now read by the guard, not decorative."""

    def test_guard_rejects_a_flipped_claim_against_the_flag(self) -> None:
        # A report that carries a team-gate/freeze claim but a stale no_g4_claim
        # is caught; the flag is derived from the same scan the guard performs.
        report = {"frozen": False, "no_g4_claim": True,
                  "verdict": "FROZEN (physical freeze declared)",
                  "final_freeze_evidence_schema": {}}
        with self.assertRaises(AssertionError):
            w16.assert_no_freeze(report)

    def test_build_report_derives_no_g4_claim_true(self) -> None:
        report = w16.build_report([COOLING] if COOLING.is_file() else [])
        self.assertTrue(report["no_g4_claim"])


class GeometryMapComparisonTests(unittest.TestCase):
    """The mapping is the evidence; `consistent_with_freeze` is only a claim about it."""

    @staticmethod
    def _side(roles, flag=True, labelled=True):
        return {"observed": dict(roles), "consistent_with_freeze": flag,
                "fully_labelled": labelled}

    FROZEN = {"t1": "CHAMBER_CENTER", "t2": "TEC_HOT_SIDE",
              "t3": "CHAMBER_BOTTOM", "t4": "CHAMBER_NEAR_DOOR"}

    def _dim(self, result):
        return result["dimension_table"]["geometry_roles"]

    def test_identical_verified_maps_are_comparable(self) -> None:
        out = w16.compare_snapshots({"geometry_roles": self._side(self.FROZEN)},
                                    {"geometry_roles": self._side(self.FROZEN)})
        self.assertEqual(self._dim(out)["state"], "MATCH")

    def test_two_different_maps_cannot_both_be_match(self) -> None:
        """Both sides assert consistent_with_freeze=True; the maps disagree."""
        swapped = dict(self.FROZEN, t1="CHAMBER_NEAR_DOOR", t4="CHAMBER_CENTER")
        out = w16.compare_snapshots({"geometry_roles": self._side(self.FROZEN)},
                                    {"geometry_roles": self._side(swapped)})
        self.assertEqual(self._dim(out)["state"], "MISMATCH")
        self.assertFalse(out["comparison_allowed"])

    def test_unassigned_role_is_a_missing_side_not_a_match(self) -> None:
        out = w16.compare_snapshots(
            {"geometry_roles": self._side(self.FROZEN)},
            {"geometry_roles": self._side(dict(self.FROZEN, t3=None), labelled=False)})
        self.assertEqual(self._dim(out)["state"], "MISSING_SIDE")
        self.assertFalse(out["comparison_allowed"])

    def test_a_stale_flag_cannot_override_the_mapping(self) -> None:
        """Mapping is the frozen one but the side claims inconsistency: contradiction."""
        out = w16.compare_snapshots(
            {"geometry_roles": self._side(self.FROZEN, flag=False)},
            {"geometry_roles": self._side(self.FROZEN, flag=True)})
        entry = self._dim(out)
        self.assertEqual(entry["state"], "MISMATCH")
        self.assertEqual(entry["flag_contradicts_mapping"], ["baseline"])

    def test_flag_claiming_agreement_cannot_rescue_a_wrong_map(self) -> None:
        wrong = dict(self.FROZEN, t2="CHAMBER_CENTER")
        out = w16.compare_snapshots({"geometry_roles": self._side(self.FROZEN)},
                                    {"geometry_roles": self._side(wrong, flag=True)})
        self.assertEqual(self._dim(out)["state"], "MISMATCH")

    def test_comparison_of_unverified_configuration_never_allows_a_freeze(self) -> None:
        report = w16.build_report([COOLING] if COOLING.is_file() else [])
        self.assertFalse(report["cross_era_comparison"]["comparison_allowed"])
        self.assertTrue(report["verdict"].startswith("NO_FREEZE"))


if __name__ == "__main__":
    unittest.main()
