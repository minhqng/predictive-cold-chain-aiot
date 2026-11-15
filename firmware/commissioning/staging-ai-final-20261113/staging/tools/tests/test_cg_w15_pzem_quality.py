"""Durable tests for the W15 PZEM data-quality analyzer and its dossier.

The analyzer under test is ``firmware/tools/cg_w15_pzem_quality.py`` - the module
the W08 dossier generator, the W15 dossier and ``run_all_checks_w15.py`` all
import. An earlier duplicate, ``cg_pzem_quality.py``, covered the same ground with
a different API; its rules live here now, against the one module that ships.

Rules asserted here:
* zero is distinct from absent (docs/01 1.10-1.12);
* the device clock, not the host wall clock, is the sample time (docs/01 18.3/18.5);
* the duty-0-with-current frame is surfaced as an ON/OFF anomaly and never
  averaged into a driven peak;
* undocumented device bitmasks are reported verbatim, never interpreted;
* PWM Go/No-Go stays a methodology and never declares GO;
* nothing is promoted to PHYSICALLY_VERIFIED, no absolute developer path is
  pinned, and both guards are proved to fire on a mutated dossier.
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
REPO = TOOLS.parent.parent
sys.path.insert(0, str(TOOLS))

import cg_w08_envelope as env  # noqa: E402
import cg_w15_pzem_quality as q  # noqa: E402
import cg_w15_pwm_gonogo as pwm  # noqa: E402

W15_DOSSIER = REPO / "evidence" / "A" / "W15"


def committed_audit() -> dict[str, object]:
    """The reproducible-from-git view: no local bench, only committed captures."""
    return q.audit(REPO, None)


class KeeperIsTheOnlyAnalyzer(unittest.TestCase):
    def test_the_duplicate_analyzer_is_gone(self) -> None:
        # One analyzer per question: a second module with the same job drifts.
        self.assertFalse((TOOLS / "cg_pzem_quality.py").exists())

    def test_quality_vocabulary_is_canonical(self) -> None:
        self.assertEqual(q.QUALITY_ENUM, ("VALID", "DEGRADED", "INVALID", "UNKNOWN"))
        self.assertEqual(q.FORBIDDEN_STATUS, env.FORBIDDEN_STATUS)


class ZeroVersusAbsent(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = committed_audit()
        cls.zero = cls.report["zero_vs_absent"]

    def test_failclosed_build_absence_is_not_read_as_zero(self) -> None:
        g1 = self.zero["W04-G1-production-failclosed"]
        for field in ("voltage", "current", "power"):
            self.assertEqual(g1[field]["present"], 0,
                             f"{field} must be absent, not zero, on the "
                             "fail-closed build")
            self.assertEqual(g1[field]["explicit_zero_with_value"], 0)

    def test_w03_off_capture_publishes_a_real_zero(self) -> None:
        w03 = self.zero["W03-132b-off-envelope"]["current"]
        self.assertGreater(w03["explicit_zero_with_value"], 0)
        self.assertTrue(w03["status_token_present"])

    def test_empty_status_column_is_unqualified_not_ok(self) -> None:
        # The committed 600 s CSV has status cells but they are empty: an absent
        # token must never read as a satisfied condition.
        h8 = self.zero["W04-H8C-box-600s"]["current"]
        self.assertFalse(h8["status_token_present"])
        self.assertGreater(h8["present"], 0)


class ClockSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = committed_audit()
        cls.clock = cls.report["clock_semantics"]

    def test_host_wall_clock_is_never_the_sample_time(self) -> None:
        for source, entry in self.clock["per_source"].items():
            self.assertFalse(entry["host_wall_clock_used_as_sample_time"], source)
        self.assertTrue(self.clock["raw_declares_no_wall_clock"])

    def test_device_ms_is_monotonic_within_a_boot_on_the_pinned_capture(self) -> None:
        self.assertTrue(
            self.clock["per_source"]["W04-H8C-box-600s"][
                "device_ms_monotonic_non_decreasing"])

    def test_expiry_at_receipt_and_per_boot_clock_are_stated_as_rules(self) -> None:
        # device_ms restarts per boot, so an absolute TTL measured on arrival
        # cannot be honoured; the rule has to be visible in the data.
        self.assertIn("fails closed", self.clock["ttl_at_receipt_rule"])
        self.assertIn("boot_id", self.clock["authoritative_device_time"])


class OnOffConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = committed_audit()
        cls.consistency = cls.report["on_off_consistency"]
        cls.anomalies = cls.consistency["anomalies"]

    def test_flagged_duty_zero_frame_is_surfaced_not_averaged(self) -> None:
        hits = [a for a in self.anomalies
                if a["clock_ms"] == 826894.0 and a["source"] == "W04-H8C-box-600s"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["current_a"], 7.15)
        self.assertEqual(hits[0]["kind"], "APPLIED_OFF_CURRENT_ABOVE_FLOOR")
        self.assertFalse(hits[0]["electrical_status_recorded"])

    def test_the_anomaly_is_not_a_driven_frame_so_it_cannot_set_a_peak(self) -> None:
        hit = [a for a in self.anomalies if a["clock_ms"] == 826894.0][0]
        self.assertNotEqual(hit["classification"], env.DRIVEN)
        frames = env.load_sources(REPO, None)["W04-H8C-box-600s"]
        driven_seqs = {f.seq for f in frames if f.classification == env.DRIVEN}
        self.assertNotIn(hit["seq"], driven_seqs)
        drive = env.drive_stats(frames)
        # The published peak comes from the driven block only, and both means are
        # published so the holdover shows up as a difference instead of silently
        # moving a single number.
        self.assertEqual(drive["current_a"]["max"], 9.99)
        self.assertNotEqual(drive["mean_current_a_excluding_holdovers"],
                            drive["mean_current_a_inclusive_of_holdovers"])
        self.assertLess(drive["mean_current_a_inclusive_of_holdovers"],
                        drive["mean_current_a_excluding_holdovers"])

    def test_the_classification_question_is_left_open(self) -> None:
        # Host tooling must not pick between anomaly and register holdover.
        self.assertIn("holdover", self.consistency["note"].lower())

    def test_the_recorded_duty_zero_decay_is_carried_with_the_anomaly(self) -> None:
        """The operator-confirmed follow-through is published, not paraphrased.

        The applied duty stays 0 while the PZEM-reported current decays
        7.15 -> 0.56 -> 0.02 -> 0.0 A and reaches zero at device_ms=829894. Recording
        the whole sequence is what turns "it is only the holdover frame" from an
        assertion into evidence - and the trace is labelled as the meter's own report,
        because nothing independent backs it.
        """
        hit = [a for a in self.anomalies
               if a["clock_ms"] == 826894.0 and a["source"] == "W04-H8C-box-600s"][0]
        self.assertEqual(hit["zero_duty_current_sequence_a"], [7.15, 0.56, 0.02, 0.0])
        self.assertEqual([f["device_ms"] for f in hit["frames_after_suspect"]],
                         [827894.0, 828894.0, 829894.0])
        self.assertEqual(hit["current_returns_to_zero_at_device_ms"], 829894.0)
        self.assertTrue(hit["applied_duty_stayed_zero_throughout"])
        self.assertIn("no independent instrument", hit["trace_provenance"])
        self.assertIn("no independent instrument",
                      self.consistency["zero_duty_trace_provenance"])

    def test_the_follow_through_walk_stops_when_the_duty_is_not_zero(self) -> None:
        # A re-energized branch must never be read as part of an OFF decay: one
        # synthetic duty-0 spike followed by a driven frame ends the walk.
        frames = [
            env.Frame(source="synthetic", seq="1", clock_ms=0.0, state="COOLING",
                      duty_req=999, duty_applied=999, voltage_v=11.8, current_a=7.0,
                      power_w=82.6),
            env.Frame(source="synthetic", seq="2", clock_ms=1000.0, state="COOLDOWN",
                      duty_req=0, duty_applied=0, voltage_v=11.8, current_a=7.0,
                      power_w=82.6),
            env.Frame(source="synthetic", seq="3", clock_ms=2000.0, state="COOLING",
                      duty_req=999, duty_applied=999, voltage_v=11.8, current_a=7.1,
                      power_w=83.0),
        ]
        trace = q.zero_duty_follow_through(frames, 1)
        self.assertEqual(trace["zero_duty_current_sequence_a"], [7.0])
        self.assertEqual(trace["frames_after_suspect"], [])
        self.assertIsNone(trace["current_returns_to_zero_at_device_ms"])

    def test_the_note_names_the_canonical_safety_candidate(self) -> None:
        # docs/01 22.4/23.4 name CONTROL_ELECTRICAL_ANOMALY (high severity) as the
        # class a commanded-OFF-with-current frame maps to; W15 keeps that option
        # open next to the holdover reading, so the note must say it out loud.
        note = self.consistency["note"]
        self.assertIn("CONTROL_ELECTRICAL_ANOMALY", note)
        self.assertIn("high severity", note)
        self.assertIn("holdover", note.lower())


class BitmaskHonesty(unittest.TestCase):
    def test_bit_positions_are_not_invented(self) -> None:
        masks = q.quality_bitmasks(None, REPO)
        self.assertFalse(masks["bit_position_meaning_documented_in_repo"])
        # No local bench means nothing to read: an honest empty, not a pass.
        self.assertEqual(masks["per_source"], {})

    def test_raw_quality_tokens_are_parsed_verbatim(self) -> None:
        line = json.dumps({"raw": "EML Q miss=0 inv=0 stale=1 age=636"})
        tokens = q.read_raw_quality(
            pathlib.Path(self._write(line)))
        self.assertEqual(tokens[0]["stale"], "1")

    def _write(self, text: str) -> str:
        handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                             encoding="utf-8")
        handle.write(text + "\n")
        handle.close()
        self.addCleanup(pathlib.Path(handle.name).unlink)
        return handle.name


class PhysicalClaimGuard(unittest.TestCase):
    def test_guard_rejects_a_promoted_claim(self) -> None:
        with self.assertRaises(ValueError):
            q.assert_no_physical_status({"a": {"b": q.FORBIDDEN_STATUS}})

    def test_clean_report_passes_the_guard(self) -> None:
        q.assert_no_physical_status({"a": q.STATUS_LABEL})
        q.assert_no_physical_status(committed_audit())

    def test_the_pinned_report_only_ever_denies_a_physical_claim(self) -> None:
        # A host analysis is never a physical verification: the dossier may use
        # the word only inside a sentence that denies it.
        text = (W15_DOSSIER / "pzem-quality-report.md").read_text(encoding="utf-8")
        for line in text.splitlines():
            if q.FORBIDDEN_STATUS in line:
                self.assertTrue(
                    any(n in line.lower() for n in ("not", "never", "no ", "without",
                                                    "refus", "none")),
                    f"the report asserts the physical label: {line[:90]!r}")
        self.assertIn("826894", text)


class PwmMethodology(unittest.TestCase):
    def test_decide_never_emits_go_on_this_tree(self) -> None:
        decision = pwm.decide()
        self.assertNotEqual(decision["decision"], "GO")
        self.assertEqual(decision["decision"], "NOT_DECIDED")

    def test_criteria_and_evidence_exist_without_thresholds(self) -> None:
        thresholds = pwm.evaluate_thresholds()
        self.assertTrue(thresholds)
        criteria = pwm.render_criteria_csv()
        self.assertTrue(criteria.splitlines()[0])
        self.assertIn("UNRESOLVED", criteria)
        self.assertNotIn(q.FORBIDDEN_STATUS, criteria)


class ReferenceGap(unittest.TestCase):
    def test_reference_check_reports_consistency_only(self) -> None:
        report = committed_audit()
        reference = q.reference_check(report)
        self.assertFalse(reference["trusted_independent_meter_available"])
        self.assertFalse(reference["certified_calibration"])
        self.assertEqual(reference["status_label"], "NEED_USER_ACTION")


class DossierValidatorFires(unittest.TestCase):
    """The W15 validator must reject a mutated dossier - proved, not asserted."""

    @staticmethod
    def _load_validator():
        path = W15_DOSSIER / "validate_w15.py"
        spec = importlib.util.spec_from_file_location("validate_w15_under_test", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def _run_mutated(self, mutate, prefix: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory(prefix=prefix) as dirn:
            work = pathlib.Path(dirn) / "W15"
            shutil.copytree(W15_DOSSIER, work)
            mutate(work)
            sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
                    for p in sorted(work.iterdir())
                    if p.is_file() and p.name != "SHA256SUMS.txt"]
            (work / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n",
                                                 encoding="utf-8", newline="\n")
            module = self._load_validator()
            module.DOSSIER = work
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = module.main()
            return code, buffer.getvalue()

    def test_committed_dossier_validates(self) -> None:
        module = self._load_validator()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = module.main()
        self.assertEqual(code, 0, buffer.getvalue())

    def test_absolute_developer_path_makes_the_validator_fail(self) -> None:
        def mutate(work: pathlib.Path) -> None:
            readme = work / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8")
                              + "\nSee X:\\Users\\someone\\repo\\evidence\\A\\W04.\n",
                              encoding="utf-8", newline="\n")

        code, output = self._run_mutated(mutate, "cg-w15-abs-")
        self.assertEqual(code, 1, output)
        self.assertIn("absolute developer path", output)

    def test_unpinned_artifact_makes_the_validator_fail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cg-w15-unpinned-") as dirn:
            work = pathlib.Path(dirn) / "W15"
            shutil.copytree(W15_DOSSIER, work)
            (work / "electrical-frame-quality.csv").write_text(
                (work / "electrical-frame-quality.csv").read_text(encoding="utf-8")
                + "# appended\n", encoding="utf-8", newline="\n")
            module = self._load_validator()
            module.DOSSIER = work
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = module.main()
            self.assertEqual(code, 1, buffer.getvalue())
            self.assertIn("hash mismatch", buffer.getvalue())

    def test_a_new_file_without_a_pin_makes_the_validator_fail(self) -> None:
        def mutate(work: pathlib.Path) -> None:
            (work / "extra-notes.md").write_text("unpinned\n", encoding="utf-8",
                                                 newline="\n")

        # The re-pin in _run_mutated would pin it, so drop that one line instead.
        with tempfile.TemporaryDirectory(prefix="cg-w15-missing-pin-") as dirn:
            work = pathlib.Path(dirn) / "W15"
            shutil.copytree(W15_DOSSIER, work)
            mutate(work)
            module = self._load_validator()
            module.DOSSIER = work
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = module.main()
            self.assertEqual(code, 1, buffer.getvalue())
            self.assertIn("not hash-pinned", buffer.getvalue())

    def test_a_pwm_go_decision_makes_the_validator_fail(self) -> None:
        def mutate(work: pathlib.Path) -> None:
            go = work / "pwm-go-no-go.md"
            go.write_text(go.read_text(encoding="utf-8").replace(
                "decision: NOT_DECIDED", "decision: GO", 1) + "\ndecision: GO\n",
                encoding="utf-8", newline="\n")

        code, output = self._run_mutated(mutate, "cg-w15-go-")
        self.assertEqual(code, 1, output)

    def test_an_injected_physical_claim_makes_the_validator_fail(self) -> None:
        def mutate(work: pathlib.Path) -> None:
            target = work / "electrical-frame-quality.csv"
            target.write_text(
                target.read_text(encoding="utf-8")
                + "W04-H8C-box-600s,957,PHYSICALLY_VERIFIED\n",
                encoding="utf-8", newline="\n")

        code, output = self._run_mutated(mutate, "cg-w15-claim-")
        self.assertEqual(code, 1, output)
        self.assertIn(q.FORBIDDEN_STATUS, output)

    def test_a_resolved_pwm_threshold_makes_the_validator_fail(self) -> None:
        def mutate(work: pathlib.Path) -> None:
            target = work / "pwm-criteria.csv"
            text = target.read_text(encoding="utf-8").replace("UNRESOLVED", "1.50", 1)
            target.write_text(text, encoding="utf-8", newline="\n")

        code, output = self._run_mutated(mutate, "cg-w15-threshold-")
        self.assertEqual(code, 1, output)

    def test_a_report_that_lost_the_anomaly_class_makes_the_validator_fail(self) -> None:
        # F1: the canonical high-severity class must stay in the published evidence;
        # requiring the token is what stops it silently disappearing again.
        def mutate(work: pathlib.Path) -> None:
            report = work / "pzem-quality-report.md"
            report.write_text(report.read_text(encoding="utf-8").replace(
                "CONTROL_ELECTRICAL_ANOMALY", "the anomaly class"),
                encoding="utf-8", newline="\n")

        code, output = self._run_mutated(mutate, "cg-w15-anomaly-")
        self.assertEqual(code, 1, output)
        self.assertIn("CONTROL_ELECTRICAL_ANOMALY", output)

    def test_pinned_pycache_entry_makes_the_validator_fail(self) -> None:
        # F3: a cache byte must never pass as a pinned dossier artifact. Copy the
        # dossier, add __pycache__/evil.pyc and pin its correct hash - the pin
        # itself must be rejected.
        with tempfile.TemporaryDirectory(prefix="cg-w15-pyc-") as dirn:
            work = pathlib.Path(dirn) / "W15"
            shutil.copytree(W15_DOSSIER, work)
            cache = work / "__pycache__"
            cache.mkdir(exist_ok=True)
            (cache / "evil.cpython-314.pyc").write_bytes(b"not evidence")
            lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  "
                     f"{p.relative_to(work).as_posix()}"
                     for p in sorted(work.rglob("*"))
                     if p.is_file() and p.name != "SHA256SUMS.txt"]
            (work / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n",
                                                 encoding="utf-8", newline="\n")
            module = self._load_validator()
            module.DOSSIER = work
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = module.main()
            self.assertEqual(code, 1, buffer.getvalue())
            self.assertIn("Python cache", buffer.getvalue())

    def test_empty_bench_root_reports_byte_checks_not_run(self) -> None:
        # F2: with the bench tree pointed at an empty scratch dir the per-original
        # SHA-256 checks cannot run, and the OK must say so instead of bundling
        # the skip into a silent pass.
        module = self._load_validator()
        with tempfile.TemporaryDirectory(prefix="cg-w15-emptybench-") as dirn:
            saved = os.environ.get("CG_W08_BENCH_ROOT")
            os.environ["CG_W08_BENCH_ROOT"] = dirn
            buffer = io.StringIO()
            try:
                with contextlib.redirect_stdout(buffer):
                    code = module.main()
            finally:
                if saved is None:
                    os.environ.pop("CG_W08_BENCH_ROOT", None)
                else:
                    os.environ["CG_W08_BENCH_ROOT"] = saved
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("local-bench original byte-checks: NOT RUN", buffer.getvalue())


class RunIndexCaveats(unittest.TestCase):
    """F4: the A3 run index must not drop its own caveat column."""

    def test_caveats_is_a_run_index_column(self) -> None:
        self.assertIn("caveats", q.RUN_INDEX_COLUMNS)

    def test_csv_carries_the_h7_and_unqualified_caveats(self) -> None:
        rows = list(csv.DictReader(
            (W15_DOSSIER / "A3-run-index.csv").open(encoding="utf-8", newline="")))
        self.assertTrue(all("caveats" in row for row in rows))
        h7 = [row for row in rows if row["session"].startswith("H7")]
        self.assertTrue(h7)
        for row in h7:
            self.assertIn("electrical-only", row["caveats"], row["session"])
        committed = next(row for row in rows
                         if row["session"] == "W04-H8C-box-600s")
        self.assertIn("validity token", committed["caveats"])

    def test_a3_row_exposes_the_caveat_field(self) -> None:
        frame_rows = q.a3_run_index(REPO, None, committed_audit())
        self.assertTrue(all("caveats" in row for row in frame_rows))


if __name__ == "__main__":
    unittest.main()
