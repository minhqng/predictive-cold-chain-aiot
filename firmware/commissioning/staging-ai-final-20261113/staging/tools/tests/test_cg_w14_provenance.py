"""Tests for the W14 conditioning proof and the guards that keep it honest.

Each case plants the defect the independent review found and requires the mechanism to
refuse it, so the repair is something that can fail and not a sentence in a document:

* a stamped `conditioning_fingerprint` the committed capture does not produce;
* a series row whose `feature_c` is not the mean of the terms that row names;
* a series row attributed to a `boot_id` the capture never recorded;
* `one_fingerprint_per_capture` true while the variants' used rows differ;
* unqualified gradient samples counted as usable without being named as unvouched;
* the 2026-11-02 identification session admitted because its filename was changed;
* a forbidden claim inside a JSON value, where a double quote exempted every line of it;
* a file dropped into the pinned folder being re-pinned into legitimacy.
"""

from __future__ import annotations

import csv as csv_module
import json
import pathlib
import sys
import tempfile
import unittest

# Importing the dossier's generator must not leave a __pycache__ inside a hash-pinned
# folder: check_pins treats a cache file as a defect, and it is one.
sys.dont_write_bytecode = True

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
TOOLS = REPO / "firmware" / "tools"
DOSSIER = REPO / "evidence" / "A" / "W14"
IDENTIFICATION_DIR = REPO / "evidence" / "A" / "W07" / "probe-identification"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(DOSSIER))

import build_w14_artifacts as gen  # noqa: E402
import cg_thermal_repeatability as rep  # noqa: E402
import cg_w14_sensor_qa as qa  # noqa: E402
import cg_w14_spatial as sp  # noqa: E402
from test_cg_w14_spatial import row, segment, write_capture  # noqa: E402

H8 = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"


def h8s_frames(path: pathlib.Path) -> list[dict[str, str]]:
    """The `#CG H8S` frames of a bench log, as the field map the firmware sent."""
    frames = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if "#CG H8S" not in line:
            continue
        fields: dict[str, str] = {}
        for token in line.split():
            if "=" in token:
                key, _, value = token.partition("=")
                fields[key] = value
        frames.append(fields)
    return frames


def csv_rows_from_frames(frames: list[dict[str, str]]) -> list[dict[str, str]]:
    """The same session re-stamped as a CSV, which is what a derivative of a log is."""
    rows = []
    for frame in frames:
        merged = {key: str(value) for key, value in row().items()}
        merged.update({
            "device_ms": frame.get("device_ms", ""),
            "boot_id": frame.get("boot_id", ""),
            "state": frame.get("state", ""),
            "stage": frame.get("stage", ""),
            "pwm_applied_permille": frame.get("pwm_applied_permille", "0"),
            "door_open": frame.get("door_open", ""),
            "door_polarity": frame.get("door_polarity", ""),
            "current_a": frame.get("current_a", "0.0"),
            "voltage_v": frame.get("voltage_v", "0.0"),
            "power_w": frame.get("power_w", "0.0"),
            "energy_wh": frame.get("energy_wh", "0"),
        })
        for index in ("1", "2", "3", "4"):
            merged[f"t{index}_c"] = frame.get(f"t{index}", "")
            merged[f"t{index}_status"] = frame.get(f"t{index}_status", "")
        rows.append(merged)
    return rows


class ConditioningControlIsMeasured(unittest.TestCase):
    """The A-W14-02 control is a recomputation over rows, not a label stamped once."""

    def test_fingerprint_reproduces_from_the_capture_rows(self):
        report = sp.ablation_matrix([H8], sp.ABLATION_VARIANTS, 3)
        capture = report["captures"][0]
        rows = rep.read_rows(H8)
        self.assertEqual(capture["conditioning_fingerprint"],
                         sp.conditioning_fingerprint(rows))
        self.assertEqual(sp.conditioning_fingerprint(rows), "d1671cc668ca0fa1")

    def test_the_control_flag_is_derived_not_literal(self):
        report = sp.ablation_matrix([H8], sp.ABLATION_VARIANTS, 3)
        capture = report["captures"][0]
        control = capture["physical_condition_control"]
        self.assertTrue(control["one_fingerprint_per_capture"])
        self.assertEqual(control["fingerprints_stamped_on_variant_rows"],
                         [capture["conditioning_fingerprint"]])
        self.assertEqual(control["phases_where_variants_disagree_on_used_rows"], [])
        self.assertEqual(report["physical_condition_control"]["one_fingerprint_per_capture"],
                         True)
        # The field is not a constant: rebuild it from the rows it claims to describe.
        rebuilt = sp.physical_condition_control(capture["conditioning_fingerprint"],
                                               rep.split_phases(rep.read_rows(H8)),
                                               capture["variants"])
        self.assertEqual(rebuilt, control)

    def test_used_rows_fingerprint_is_per_variant_and_recomputable(self):
        report = sp.ablation_matrix([H8], sp.ABLATION_VARIANTS, 3)
        capture = report["captures"][0]
        phases = rep.split_phases(rep.read_rows(H8))
        for name, per_phase in capture["variants"].items():
            terms = tuple(sp.VARIANTS[name]["terms"])
            for phase, metrics in per_phase.items():
                kept = [source for source in phases[phase]
                        if sp.mean_of_terms(source, terms)[1] == len(terms)
                        and sp.mean_of_terms(source, terms)[0] is not None]
                self.assertEqual(metrics["used_rows_conditioning_fingerprint"],
                                 sp.conditioning_fingerprint(kept), (name, phase))
                self.assertEqual(metrics["used_rows"], len(kept))

    def test_variants_that_used_different_rows_break_the_control(self):
        """Two rows with no usable T3: the sets that read T3 are no longer on those rows."""
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "one.csv"
            rows = segment(0, 30, 999) + segment(30000, 30, 0)
            write_capture(path, rows)
            clean = sp.ablation_matrix([path], sp.ABLATION_VARIANTS, 3)
            self.assertTrue(clean["captures"][0]["physical_condition_control"]
                            ["one_fingerprint_per_capture"])
            self.assertEqual(clean["physical_condition_control"]
                             ["one_fingerprint_per_capture"], True)

            broken = [dict(source) for source in rows]
            for index in (5, 12):
                broken[index]["t3_c"] = ""
            path2 = pathlib.Path(tmp) / "two.csv"
            write_capture(path2, broken)
            report = sp.ablation_matrix([path2], sp.ABLATION_VARIANTS, 3)
            control = report["captures"][0]["physical_condition_control"]
            self.assertIn("cooling", control["phases_where_variants_disagree_on_used_rows"])
            self.assertFalse(control["one_fingerprint_per_capture"])
            self.assertFalse(report["physical_condition_control"]
                             ["one_fingerprint_per_capture"])

    def test_every_published_csv_line_rederives_from_the_row_it_names(self):
        report = sp.ablation_matrix([H8], sp.ABLATION_VARIANTS, 3)
        lines = sp.ablation_csv_rows(report)
        header = {name: index for index, name in enumerate(lines[0])}
        rows = rep.read_rows(H8)
        phases = rep.split_phases(rows)
        by_phase_device: dict[tuple[str, str], list[dict[str, str]]] = {}
        for phase, segment_rows in phases.items():
            for source in segment_rows:
                by_phase_device.setdefault((phase, source["device_ms"]),
                                           []).append(source)
        fingerprint = sp.conditioning_fingerprint(rows)
        checked = 0
        for line in lines[1:]:
            key = (line[header["phase"]], line[header["device_ms"]])
            sources = by_phase_device.get(key, [])
            self.assertEqual(len(sources), 1, key)
            source = sources[0]
            self.assertEqual(line[header["boot_id"]], source["boot_id"])
            self.assertEqual(line[header["pwm_applied_permille"]],
                             source["pwm_applied_permille"])
            self.assertEqual(line[header["door_open"]], source["door_open"])
            self.assertEqual(line[header["conditioning_fingerprint"]], fingerprint)
            terms = tuple(sp.VARIANTS[line[header["variant"]]]["terms"])
            value, usable, total = sp.mean_of_terms(source, terms)
            self.assertEqual(usable, total)
            self.assertEqual(float(line[header["feature_c"]]), round(value, 4))
            checked += 1
        self.assertGreater(checked, 9000)
        self.assertEqual(checked, len(sp.ABLATION_VARIANTS) * len(rows))


class UnqualifiedGradientsAreCounted(unittest.TestCase):
    """A gradient over readings nobody vouched for is named, not treated as checked."""

    def test_blank_statuses_count_in_the_pairwise_tally(self):
        rows = segment(0, 12, 999)
        for source in rows:
            source["t3_status"] = ""
        series, tallies = sp.pairwise_series(rows, list(sp.AIR_TERMS))
        self.assertEqual(len(series), 12)
        self.assertEqual(tallies["usable_pairs"], 12)
        self.assertEqual(tallies["unqualified_rows"], 12)
        self.assertEqual(tallies["usable_pairs_all_terms_ok"], 0)

    def test_pair_agreement_publishes_the_unqualified_position(self):
        block = sp.pair_agreement(segment(0, 12, 999), list(sp.AIR_TERMS), "cooling", 1)
        self.assertTrue(block["gradients_are_all_status_qualified"])
        self.assertEqual(block["tallies"]["unqualified_rows"], 0)
        dirty_rows = segment(0, 12, 999)
        for source in dirty_rows:
            source.pop("t1_status")
        dirty = sp.pair_agreement(dirty_rows, list(sp.AIR_TERMS), "cooling", 1)
        self.assertFalse(dirty["gradients_are_all_status_qualified"])
        self.assertEqual(dirty["tallies"]["unqualified_rows"], 12)
        self.assertIn("never recorded", dirty["unqualified_rows_note"])

    def test_the_committed_capture_qualifies_every_gradient_row(self):
        """The published zeros are measurements, so they have to stay zero on this data."""
        rows = rep.read_rows(H8)
        phases = rep.split_phases(rows)
        for phase in ("baseline", "cooling", "recovery"):
            block = sp.pair_agreement(phases[phase], list(sp.AIR_TERMS), phase, 1)
            self.assertEqual(block["tallies"]["unqualified_rows"], 0, phase)
            self.assertTrue(block["gradients_are_all_status_qualified"], phase)
        for name in sp.ABLATION_VARIANTS:
            metrics = sp.variant_phase_metrics(phases["cooling"], "cooling", name)
            self.assertEqual(metrics["unqualified_rows"], 0, name)


class IdentificationRefusedByProvenance(unittest.TestCase):
    """The touch session is refused for what it is, not for the name on its file."""

    def test_a_documented_identification_boot_id_refuses_a_renamed_capture(self):
        rows = [row(boot_id="a1732532") for _ in range(3)]
        quiet = pathlib.Path("evidence/A/W04/tec-cooling-response-600s.csv")
        self.assertEqual(sp.capture_class(quiet, rows), sp.IDENTIFICATION_MARKER)
        with self.assertRaises(rep.AnalysisError):
            sp.require_thermal_capture(quiet, rows)

    def test_the_real_touch_logs_refuse_even_when_rewritten_as_csv_and_renamed(self):
        if not IDENTIFICATION_DIR.is_dir():
            self.skipTest("the identification captures are not in this tree")
        for source in sorted(IDENTIFICATION_DIR.glob("*.log")):
            frames = h8s_frames(source)
            self.assertTrue(frames, source.name)
            rows = csv_rows_from_frames(frames)
            with tempfile.TemporaryDirectory() as tmp:
                derivative = pathlib.Path(tmp) / "tec-cooling-response-600s.csv"
                write_capture(derivative, rows)
                self.assertTrue(sp.identification_boot_ids(rows), source.name)
                with self.assertRaises(rep.AnalysisError, msg=source.name):
                    sp.require_thermal_capture(derivative, rows)

    def test_the_documented_ids_are_the_ones_the_frozen_record_names(self):
        record = (REPO / "evidence" / "A" / "W07" / "probe-identification-v0.md")
        text = record.read_text(encoding="utf-8")
        for boot in sp.IDENTIFICATION_BOOT_IDS:
            self.assertIn(boot, text, boot)

    def test_the_path_marker_still_refuses_a_capture_with_no_boot_id_recorded(self):
        rows = [row(boot_id="") for _ in range(3)]
        named = pathlib.Path("evidence/A/W07/probe-identification/touch_9.log")
        self.assertEqual(sp.capture_class(named, rows), sp.IDENTIFICATION_MARKER)

    def test_the_real_thermal_capture_is_not_identification(self):
        rows = rep.read_rows(H8)
        self.assertEqual(sp.identification_boot_ids(rows), [])
        self.assertEqual(sp.capture_class(H8, rows), "THERMAL_RESPONSE")


class ClaimGuardHasNoQuoteHole(unittest.TestCase):
    """A double quote in the text is not evidence that the claim is being quoted."""

    def test_double_quote_is_not_a_claim_marker(self):
        self.assertNotIn('"', qa.CLAIM_MARKERS)

    def test_a_json_shaped_prose_line_is_now_caught(self):
        line = ('  "summary": "positions re-checked, '
                'no movement verified since the freeze",')
        with self.assertRaises(rep.AnalysisError):
            qa.assert_no_false_claim("sensor-position-qa.json", line)

    def test_the_structural_guard_catches_the_same_claim_in_a_payload(self):
        with self.assertRaises(rep.AnalysisError):
            qa.guard_no_forbidden_claim({"summary": "positions re-checked, "
                                                   "no movement verified since the freeze"})

    def test_genuine_quotation_and_negation_still_pass(self):
        qa.assert_no_false_claim("scratch.md",
                                 "The phrase `no movement verified` is never asserted here.")
        qa.assert_no_false_claim("scratch.md", "physically verified: false - host analysis only")

    def test_delivered_artifacts_carry_no_forbidden_claim_structurally(self):
        for name in ("sensor-position-qa.json", "spatial-statistics.json",
                     "ablation-support.json", "pairing-input.json"):
            payload = json.loads((DOSSIER / name).read_text(encoding="utf-8"))
            qa.guard_no_forbidden_claim(payload)


class PinSetIsAnAllowlist(unittest.TestCase):
    """Nothing may be dropped into a pinned folder and re-pinned into legitimacy."""

    def test_the_declared_set_is_the_delivered_set(self):
        present = [name for name in gen.present_dossier_files()
                   if name != "SHA256SUMS.txt"]
        self.assertEqual(sorted(gen.pinned_names()), sorted(present))

    def test_a_stray_file_and_a_cache_are_both_refused(self):
        caches, unknown, missing = gen.pin_rejections(
            list(gen.pinned_names()) + ["dropped-artifact.json",
                                        "__pycache__/x.cpython-314.pyc"])
        self.assertEqual(unknown, ["dropped-artifact.json"])
        self.assertEqual(caches, ["__pycache__/x.cpython-314.pyc"])
        self.assertEqual(missing, [])

    def test_a_missing_deliverable_is_refused(self):
        without = [name for name in gen.pinned_names() if name != "handoff.md"]
        self.assertEqual(gen.pin_rejections(without)[2], ["handoff.md"])

    def test_the_generated_names_match_what_the_builder_writes(self):
        self.assertEqual(sorted(gen.GENERATED_NAMES), sorted(gen.build()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
