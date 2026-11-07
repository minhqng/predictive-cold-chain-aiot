"""Behavioral tests for the shared Member A acceptance core.

These run against the main-based core package only (model/protocol/analysis/
evidence). They use temporary directories and never touch hardware, the
canonical ledger, or any real evidence corpus.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
TOOLS = HERE.parent.parent  # .../tools
sys.path.insert(0, str(TOOLS))

from member_a_app import analysis, evidence, model, protocol  # noqa: E402


def _telem_line(**over) -> str:
    kv = {
        "schema": "2", "device_id": "coldguard-001", "boot_id": "boot0001",
        "seq": "7", "uptime_ms": "12345", "test_phase": "IDLE",
        "t_inside_c": "25.0625", "t_inside_status": "OK",
        "t_hot_side_c": "26.0", "t_hot_side_status": "OK",
        "t_ambient_c": "30.41", "t_ambient_status": "OK",
        "relative_humidity_pct": "68.51", "relative_humidity_status": "OK",
        "voltage_v": "11.9", "voltage_status": "OK",
        "current_a": "0.0", "current_status": "OK",
        "power_w": "0.0", "power_status": "OK",
        "pwm_duty": "0", "tec_state": "OFF", "quality": "VALID",
        "door_raw": "1", "door_open": "0", "door_status": "OK",
    }
    kv.update(over)
    return "#CG TELEM " + " ".join(f"{k}={v}" for k, v in kv.items())


class CoreImportTests(unittest.TestCase):
    def test_core_modules_import(self):
        self.assertTrue(hasattr(model, "TestDefinition"))
        self.assertTrue(hasattr(model, "TestResult"))
        self.assertTrue(hasattr(model, "Outcome"))
        self.assertTrue(callable(protocol.parse_line))
        self.assertTrue(callable(analysis.mean))
        self.assertTrue(hasattr(evidence, "SessionStore"))

    def test_core_has_no_live_hardware_dependency(self):
        # Importing the core must not pull in the serial driver or downstream
        # runner/evaluator/GUI modules.
        self.assertNotIn("serial", sys.modules)
        for bad in ("member_a_app.device", "member_a_app.runner",
                    "member_a_app.evaluators", "member_a_app.gui"):
            self.assertNotIn(bad, sys.modules)


class ModelTests(unittest.TestCase):
    def test_outcome_rank_order(self):
        self.assertGreater(model.Outcome.PASS.rank, model.Outcome.FAIL.rank)
        self.assertGreater(model.Outcome.FAIL.rank, model.Outcome.INCOMPLETE.rank)
        self.assertGreater(model.Outcome.INCOMPLETE.rank, model.Outcome.NOT_RUN.rank)

    def test_result_roundtrip(self):
        r = model.TestResult(test_id="A-W02-06", outcome=model.Outcome.PASS,
                             started_at="s", ended_at="e",
                             checks=[model.CheckResult("c", True)])
        back = model.TestResult.from_dict(r.to_dict())
        self.assertEqual(back.test_id, r.test_id)
        self.assertIs(back.outcome, model.Outcome.PASS)
        self.assertEqual(back.checks[0].name, "c")

    def test_definition_is_frozen(self):
        d = model.TestDefinition(test_id="A-W02-06", week=2, title="t",
                                 criterion="c", mode=model.TestMode.GUIDED,
                                 safety=model.SafetyClass.READ_ONLY, handler="h")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            d.title = "changed"

    def test_blocked_carries_reason_and_is_not_an_outcome(self):
        err = model.TestBlocked("hardware-gate-unmet")
        self.assertEqual(err.reason, "hardware-gate-unmet")
        self.assertIsInstance(err, Exception)
        # A blocked requirement is never a PASS; the runner (excluded from the
        # core) maps it to INCOMPLETE. There is no BLOCKED outcome value.
        self.assertNotIn("BLOCKED", [o.value for o in model.Outcome])
        self.assertIsNot(model.Outcome.PASS, model.Outcome.INCOMPLETE)


class ProtocolTests(unittest.TestCase):
    def test_parse_kv(self):
        self.assertEqual(protocol.parse_kv(["a=1", "b=two"]), {"a": "1", "b": "two"})

    def test_schema2_ambient_and_quality(self):
        parsed = protocol.parse_line(_telem_line())
        frame = parsed.frame
        self.assertEqual(frame.schema, 2)
        self.assertAlmostEqual(frame.ambient_c, 30.41)
        self.assertAlmostEqual(frame.humidity_pct, 68.51)
        self.assertEqual(frame.quality, "VALID")

    def test_nan_is_not_zero(self):
        parsed = protocol.parse_line(_telem_line(t_ambient_c="nan",
                                                 t_ambient_status="STALE"))
        self.assertIsNone(parsed.frame.ambient_c)


class AnalysisTests(unittest.TestCase):
    def test_basic_stats(self):
        self.assertAlmostEqual(analysis.mean([1, 2, 3]), 2.0)
        self.assertAlmostEqual(analysis.median([1, 2, 3]), 2.0)
        self.assertIsNotNone(analysis.sd([1, 2, 3]))
        self.assertIsNotNone(analysis.p95([1, 2, 3, 4]))

    def test_empty_is_none_not_zero(self):
        self.assertIsNone(analysis.mean([]))
        self.assertIsNone(analysis.sd([]))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cg-core-")
        self.root = pathlib.Path(self._tmp.name)
        self.store = evidence.SessionStore(self.root / "session")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _source_file(self, name="ev.bin", payload=b"real-bytes"):
        p = self.root / name
        p.write_bytes(payload)
        return p

    def test_sha256_matches_hashlib(self):
        p = self._source_file()
        self.assertEqual(evidence.sha256_file(p),
                         hashlib.sha256(p.read_bytes()).hexdigest())

    def test_attach_records_identity(self):
        p = self._source_file()
        rec = self.store.attach("A-W02-06", p)
        self.assertEqual(rec["sha256"], hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertEqual(rec["size"], p.stat().st_size)
        self.assertTrue((self.store.root / rec["stored"]).is_file())

    def test_attach_rejects_missing_and_empty(self):
        with self.assertRaises(evidence.EvidenceError):
            self.store.attach("A-W02-06", self.root / "nope.bin")
        empty = self._source_file("empty.bin", b"")
        with self.assertRaises(evidence.EvidenceError):
            self.store.attach("A-W02-06", empty)

    def _result_with_evidence(self, rec):
        return model.TestResult(test_id="A-W02-06", outcome=model.Outcome.PASS,
                                started_at="s", ended_at="e", evidence=[rec],
                                source="HARDWARE")

    def test_verify_intact_ok(self):
        rec = self.store.attach("A-W02-06", self._source_file())
        self.store.record_result(self._result_with_evidence(rec))
        self.assertEqual(self.store.verify_attachments(), [])

    def test_verify_tampered_hash_mismatch(self):
        rec = self.store.attach("A-W02-06", self._source_file())
        self.store.record_result(self._result_with_evidence(rec))
        (self.store.root / rec["stored"]).write_bytes(b"tampered")
        problems = self.store.verify_attachments()
        self.assertEqual(problems[0]["problem"], "HASH_MISMATCH")

    def test_verify_missing(self):
        rec = self.store.attach("A-W02-06", self._source_file())
        self.store.record_result(self._result_with_evidence(rec))
        (self.store.root / rec["stored"]).unlink()
        self.assertEqual(self.store.verify_attachments()[0]["problem"], "MISSING")

    def test_record_rejects_noncanonical_id(self):
        r = model.TestResult(test_id="not-canonical", outcome=model.Outcome.FAIL,
                             started_at="s", ended_at="e")
        with self.assertRaises(evidence.EvidenceError):
            self.store.record_result(r)

    def test_record_rejects_synthetic_pass(self):
        r = model.TestResult(test_id="A-W02-06", outcome=model.Outcome.PASS,
                             started_at="s", ended_at="e", source="SIMULATION")
        with self.assertRaises(evidence.EvidenceError):
            self.store.record_result(r)

    def test_record_archives_no_silent_overwrite(self):
        a = model.TestResult(test_id="A-W02-06", outcome=model.Outcome.FAIL,
                             started_at="s", ended_at="e", source="HARDWARE")
        self.store.record_result(a)
        b = model.TestResult(test_id="A-W02-06", outcome=model.Outcome.PASS,
                             started_at="s", ended_at="e", source="HARDWARE")
        self.store.record_result(b)
        self.assertEqual(self.store.attempt_count("A-W02-06"), 2)
        self.assertIs(self.store.result("A-W02-06").outcome, model.Outcome.PASS)

    def test_resolve_within_rejects_traversal(self):
        with self.assertRaises(evidence.EvidenceError):
            evidence.resolve_within(self.store.root, "../outside.json")

    def test_resolve_within_rejects_absolute(self):
        with self.assertRaises(evidence.EvidenceError):
            evidence.resolve_within(self.store.root, str(self.root / "abs.json"))

    def test_resolve_within_allows_relative(self):
        got = evidence.resolve_within(self.store.root, "results/A-W02-06.json")
        self.assertEqual(got, (self.store.root / "results/A-W02-06.json").resolve())

    def test_resolve_within_rejects_symlink_escape(self):
        target = self.root / "outside"
        target.mkdir()
        link = self.store.root / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation not permitted on this host")
        with self.assertRaises(evidence.EvidenceError):
            evidence.resolve_within(self.store.root, "link/secret.json")

    def test_update_measurements_rejects_escape(self):
        rec = self.store.save_measurements("A-W02-06", {"x": 1})
        rec["stored"] = "../escape.json"
        with self.assertRaises(evidence.EvidenceError):
            self.store.update_measurements(rec, {"x": 2})

    def test_verify_attachments_path_escape(self):
        rec = {"stored": "../escape.json", "sha256": "0" * 64}
        self.store.record_result(self._result_with_evidence(rec))
        self.assertEqual(self.store.verify_attachments()[0]["problem"], "PATH_ESCAPE")

    def test_import_dedup_by_hash(self):
        p = self._source_file()
        a = self.store.import_evidence("A-W02-06", p)
        b = self.store.import_evidence("A-W02-06", p)
        self.assertEqual(a["sha256"], b["sha256"])
        self.assertEqual(len(self.store.imported_for("A-W02-06")), 1)

    def test_export_report_no_synthetic_pass(self):
        d = model.TestDefinition(test_id="A-W02-06", week=2, title="t", criterion="c",
                                 mode=model.TestMode.GUIDED,
                                 safety=model.SafetyClass.READ_ONLY, handler="h")
        out = self.store.export_report([d], target=self.root / "report")
        payload = json.loads(pathlib.Path(out["json"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["results"][0]["outcome"], "NOT_RUN")
        self.assertEqual(payload["summary"]["PASS"], 0)

    def test_results_reads_main_layout(self):
        # Compatibility with the existing evidence/A/.../results/<ID>.json layout.
        payload = {"test_id": "A-W02-06", "outcome": "PASS", "started_at": "s",
                   "ended_at": "e", "checks": [], "source": "HARDWARE"}
        (self.store.results_dir / "A-W02-06.json").write_text(
            json.dumps(payload), encoding="utf-8")
        got = self.store.result("A-W02-06")
        self.assertIsNotNone(got)
        self.assertIs(got.outcome, model.Outcome.PASS)

    def test_bench_result_accepts_safe_kind(self):
        rec = self.store.record_bench_result("h8-stage-f", {"outcome": "PASS"})
        self.assertTrue((self.store.root / rec["stored"]).is_file())
        self.assertEqual(rec["sha256"],
                         hashlib.sha256((self.store.root / rec["stored"]).read_bytes()).hexdigest())

    def test_bench_result_rejects_unsafe_kind(self):
        for bad in ("../escape", "a/b", "a\\b", "/abs", "..", "", ".hidden", "C:x"):
            with self.assertRaises(evidence.EvidenceError, msg=f"kind={bad!r}"):
                self.store.record_bench_result(bad, {})

    def test_attempt_count_rejects_noncanonical_id(self):
        for bad in ("../escape", "a/b", "A-W02-06/..", "not-canonical", ""):
            with self.assertRaises(evidence.EvidenceError, msg=f"id={bad!r}"):
                self.store.attempt_count(bad)

    def test_attempt_count_accepts_canonical_id(self):
        self.assertEqual(self.store.attempt_count("A-W02-06"), 0)
        r = model.TestResult(test_id="A-W02-06", outcome=model.Outcome.FAIL,
                             started_at="s", ended_at="e", source="HARDWARE")
        self.store.record_result(r)
        self.assertEqual(self.store.attempt_count("A-W02-06"), 1)

    def test_bench_result_rejects_overlong_kind(self):
        with self.assertRaises(evidence.EvidenceError):
            self.store.record_bench_result("k" * 121, {})

    def test_attachment_name_is_confined(self):
        f = evidence._safe_attachment_name
        self.assertEqual(f("trailing."), "trailing")
        self.assertEqual(f("..."), "evidence")
        self.assertEqual(f(""), "evidence")
        self.assertLessEqual(len(f("a" * 200)), 120)
        cleaned = f("a/b\\c:d")
        self.assertNotIn("/", cleaned)
        self.assertNotIn("\\", cleaned)
        self.assertNotIn(":", cleaned)

    def test_update_measurements_confined_to_measurements(self):
        # Legitimate update of a saved measurement works.
        rec = self.store.save_measurements("A-W02-06", {"x": 1})
        self.store.update_measurements(rec, {"x": 2})
        # A crafted record must not clobber canonical results or the session.
        result_path = self.store.results_dir / "A-W02-06.json"
        result_path.write_text('{"outcome": "PASS"}', encoding="utf-8")
        before = result_path.read_bytes()
        for bad in ("results/A-W02-06.json", "session.json", "."):
            with self.assertRaises(evidence.EvidenceError, msg=f"stored={bad!r}"):
                self.store.update_measurements({"stored": bad}, {"x": 3})
        self.assertEqual(result_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()