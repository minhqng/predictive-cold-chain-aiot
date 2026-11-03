"""Tests for cg_probe_roles.py - the T2/TEC_HOT_SIDE chamber-air exclusion guard.

The claim under test is narrow and load-bearing: a hot-side probe must never be
folded into a chamber-air aggregate. Before this module the only thing enforcing
that was a hand-written `includes_hot_side: False` literal sitting next to the term
list it described, so editing the term list and leaving the literal alone was a
silent, green pass. These tests break that by deriving the answer from the frozen
ROM map and by re-reading the device's own role token on the one real capture.

Class discipline: the geometry is OPERATOR_FROZEN_AS_BUILT, not a measurement taken
here. Nothing in this file asserts that a probe was re-verified in place.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_probe_roles as roles  # noqa: E402
import cg_thermal_repeatability as rep  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[3]
H8_CAPTURE = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"


class FrozenMapTests(unittest.TestCase):
    def test_the_hot_side_is_keyed_on_rom_bytes_not_on_the_word_t2(self) -> None:
        self.assertEqual(roles.HOT_SIDE_ROM, "28AEBF2200000006")
        self.assertEqual(roles.ROM_POSITION_BY_ROM[roles.HOT_SIDE_ROM], "TEC_HOT_SIDE")
        self.assertNotIn(roles.HOT_SIDE_ROM, roles.CHAMBER_AIR_ROMS)

    def test_all_four_enumerated_roms_are_classified_exactly_once(self) -> None:
        enumerated = {
            "287088CA00000051", "28AEBF2200000006",
            "28CBE9CA00000072", "283BE5C9000000A9",
        }
        self.assertEqual(set(roles.ROM_POSITION_BY_ROM), enumerated)
        self.assertEqual(roles.CHAMBER_AIR_ROMS | {roles.HOT_SIDE_ROM}, enumerated)
        self.assertFalse(roles.CHAMBER_AIR_ROMS & {roles.HOT_SIDE_ROM})

    def test_the_chamber_air_set_is_derived_not_typed_in(self) -> None:
        # t4/SPARE in the W02 plan is chamber near-door in the as-built record, and
        # it IS air; the air set comes out of the positions, so it cannot drift.
        self.assertEqual(roles.CHAMBER_AIR_SLOTS, ("t1", "t3", "t4"))
        self.assertEqual(roles.CHAMBER_AIR_COLUMNS, ("t1_c", "t3_c", "t4_c"))
        self.assertEqual(roles.HOT_SIDE_SLOT, "t2")
        self.assertEqual(roles.HOT_SIDE_COLUMN, "t2_c")
        self.assertEqual(
            roles.CHAMBER_AIR_ROLE_NAMES, ("T1", "T3", "T4"))

    def test_positions_match_the_frozen_operator_record(self) -> None:
        self.assertEqual(roles.position_of_slot("t1"), "CHAMBER_CENTER")
        self.assertEqual(roles.position_of_slot("t3"), "CHAMBER_BOTTOM")
        self.assertEqual(roles.position_of_slot("t4"), "CHAMBER_NEAR_DOOR")
        with self.assertRaises(KeyError):
            roles.position_of_slot("t9")

    def test_the_record_is_labelled_as_operator_frozen_not_remeasured(self) -> None:
        self.assertIn("OPERATOR_FROZEN", roles.FROZEN_GEOMETRY_CLASS)
        self.assertIn("NOT_REMEASURED", roles.FROZEN_GEOMETRY_CLASS)


class GuardTests(unittest.TestCase):
    def test_a_chamber_air_aggregate_refuses_the_hot_side(self) -> None:
        with self.assertRaises(roles.HotSideInChamberAirError):
            roles.require_chamber_air(("t1_c", "t2_c", "t3_c"), name="tmean_chamber3_v0")

    def test_the_real_chamber_air_set_passes(self) -> None:
        roles.require_chamber_air(roles.CHAMBER_AIR_COLUMNS, name="tmean_airroles_v0")
        self.assertTrue(roles.is_chamber_air_safe(("t1_c", "t3_c")))
        self.assertFalse(roles.is_chamber_air_safe(("t1_c", "t2_c")))

    def test_the_committed_capture_agrees_with_the_frozen_map(self) -> None:
        """The device's own t2_role token is the cross-check, not a restatement."""
        rows = rep.read_rows(H8_CAPTURE)
        report = roles.check_capture_against_frozen_map(rows)
        self.assertEqual(report["device_role_check"], "AGREES")
        self.assertEqual(report["device_declared_hot_side"], ["t2_c"])
        # Honest about the limit: all four role columns are PRESENT, but only t2
        # carries a HOT_SIDE token; t1/t3/t4 read UNASSIGNED, so their air
        # membership is the operator record and not a device readback.
        self.assertEqual(report["device_role_columns_present"],
                         ["t1_role", "t2_role", "t3_role", "t4_role"])
        self.assertEqual(report["device_role_unassigned_slots"], ["t1", "t3", "t4"])
        self.assertEqual(
            roles.derive_hot_side_columns_from_device(rows), {"t2_c"})

    def test_a_capture_that_moves_the_hot_side_is_refused(self) -> None:
        rows = [{"t3_role": "HOT_SIDE", "t3_c": "5.0"}]
        with self.assertRaises(roles.HotSideInChamberAirError):
            roles.check_capture_against_frozen_map(rows)

    def test_no_device_role_is_reported_as_no_evidence_not_as_agreement(self) -> None:
        report = roles.check_capture_against_frozen_map([{"t2_c": "5.0"}])
        self.assertEqual(report["device_role_check"], "NO_DEVICE_EVIDENCE")
        self.assertEqual(report["device_declared_hot_side"], [])


class RepresentationWiringTests(unittest.TestCase):
    def test_every_published_air_representation_is_clean(self) -> None:
        for name in rep.CHAMBER_AIR_REPRESENTATIONS:
            self.assertFalse(rep.includes_hot_side(name), name)
            self.assertTrue(roles.is_chamber_air_safe(rep.terms_of(name)), name)

    def test_the_hot_side_flag_is_derived_from_terms_not_from_the_literal(self) -> None:
        """The circular-pass this replaces: the literal used to be the only answer.

        Flipping the declared literal must NOT change what `includes_hot_side`
        returns, because the terms decide it.
        """
        original = rep.REPRESENTATIONS["tmean_airroles_v0"]["includes_hot_side"]
        try:
            rep.REPRESENTATIONS["tmean_airroles_v0"]["includes_hot_side"] = True
            self.assertFalse(rep.includes_hot_side("tmean_airroles_v0"))
        finally:
            rep.REPRESENTATIONS["tmean_airroles_v0"]["includes_hot_side"] = original

    def test_adding_the_hot_side_to_an_air_mean_is_refused_at_import(self) -> None:
        """Proof the guard bites: mutate the term list and reload the module.

        The declared literal is left at False - exactly the edit that used to pass
        every test in the suite while redefining chamber air.
        """
        source = textwrap.dedent("""
            import sys, pathlib
            sys.path.insert(0, str(pathlib.Path(%r)))
            import cg_thermal_repeatability as rep
            rep.REPRESENTATIONS["tmean_airroles_v0"]["terms"] = ("t1_c", "t2_c", "t3_c")
            try:
                rep.check_hot_side_guard()
            except Exception as exc:
                print(type(exc).__name__ + ": " + str(exc))
            else:
                print("NOT-REFUSED")
        """) % str(REPO / "firmware" / "tools")
        result = subprocess.run([sys.executable, "-c", source], capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        combined = (result.stdout or "") + (result.stderr or "")
        self.assertIn("HotSideInChamberAirError", combined)
        self.assertNotIn("NOT-REFUSED", combined)

    def test_a_false_air_claim_fails_the_module_import_itself(self) -> None:
        """Not just a function call: the module refuses to load.

        `importlib.reload` cannot prove this - reloading re-runs the module body and
        rebuilds REPRESENTATIONS from its own literals, discarding any in-memory
        mutation. So this patches the SOURCE TEXT the way an editor would (add
        `t2_c` to a chamber-air representation, leave `includes_hot_side: False`
        untouched) and executes it.
        """
        path = REPO / "firmware" / "tools" / "cg_thermal_repeatability.py"
        source = path.read_text(encoding="utf-8")
        tampered = source.replace(
            '"tmean_airroles_v0": {"terms": ("t1_c", "t3_c", "t4_c"), '
            '"includes_hot_side": False}',
            '"tmean_airroles_v0": {"terms": ("t1_c", "t2_c", "t3_c", "t4_c"), '
            '"includes_hot_side": False}', 1)
        self.assertNotEqual(
            tampered, source,
            "the term list this test tampers with has moved; update the test rather "
            "than let it pass vacuously")
        with self.assertRaises(roles.HotSideInChamberAirError) as caught:
            exec(compile(tampered, str(path), "exec"),
                 {"__name__": "tampered_rep", "__file__": str(path)})
        self.assertIn("chamber air", str(caught.exception))

    def test_a_lie_about_the_flag_is_also_refused(self) -> None:
        """The other tamper: keep the terms clean, flip the declaration."""
        self.assertTrue(rep.check_hot_side_guard())
        original = rep.REPRESENTATIONS["tmean_all4_v0"]["includes_hot_side"]
        try:
            rep.REPRESENTATIONS["tmean_all4_v0"]["includes_hot_side"] = False
            with self.assertRaises(roles.HotSideInChamberAirError) as caught:
                rep.check_hot_side_guard()
            self.assertIn("tmean_all4_v0", str(caught.exception))
        finally:
            rep.REPRESENTATIONS["tmean_all4_v0"]["includes_hot_side"] = original
        self.assertTrue(rep.check_hot_side_guard())

    def test_the_module_imports_clean_and_reports_its_guard(self) -> None:
        self.assertEqual(rep.HOT_SIDE_GUARD["hot_side_rom"], roles.HOT_SIDE_ROM)
        self.assertEqual(rep.HOT_SIDE_GUARD["chamber_air_columns"],
                         list(roles.CHAMBER_AIR_COLUMNS))
        self.assertEqual(rep.AS_BUILT_ROLES["t2_c"], "TEC_HOT_SIDE")
        self.assertEqual(rep.AS_BUILT_ROLES["t4_c"], "CHAMBER_NEAR_DOOR")


class ExportFieldTests(unittest.TestCase):
    """The per-slot role field B's pipeline gates on, and what it must not claim."""

    def test_every_exported_slot_carries_rom_and_air_eligibility(self) -> None:
        export = roles.probe_identity_export()
        self.assertEqual(sorted(export["slots"]), ["t1", "t2", "t3", "t4"])
        for slot, block in export["slots"].items():
            self.assertRegex(block["rom"], r"^[0-9A-F]{16}$")
            self.assertIsInstance(block["in_chamber_air_aggregate"], bool)
            self.assertEqual(block["position_provenance"], roles.FROZEN_GEOMETRY_CLASS)
            if block["physical_position"] == "TEC_HOT_SIDE":
                self.assertFalse(block["in_chamber_air_aggregate"])
                self.assertTrue(block["exclusion_reason"])
            else:
                self.assertTrue(block["in_chamber_air_aggregate"])
                self.assertEqual(block["exclusion_reason"], "")

    def test_the_export_does_not_claim_movement_was_verified(self) -> None:
        """Level 4 of the IHA-01 reconciliation is NOT_AVAILABLE; say so."""
        for block in roles.probe_identity_export()["slots"].values():
            self.assertFalse(block["independently_verified_no_movement"])

    def test_the_export_runs_on_the_committed_capture(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            payload = pathlib.Path(workdir) / "probe-roles.json"
            result = subprocess.run(
                [sys.executable,
                 str(REPO / "firmware" / "tools" / "cg_probe_roles.py"),
                 str(H8_CAPTURE.relative_to(REPO)), "--json", str(payload)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=str(REPO))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(payload.read_text(encoding="utf-8"))
        self.assertEqual(data["capture_rows"], 957)
        self.assertEqual(data["device_role_check"]["device_role_check"], "AGREES")
        self.assertFalse(data["slots"]["t2"]["in_chamber_air_aggregate"])
        self.assertTrue(data["slots"]["t4"]["in_chamber_air_aggregate"])


if __name__ == "__main__":
    unittest.main()
