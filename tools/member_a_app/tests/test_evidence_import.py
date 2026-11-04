"""Existing W01-W04 evidence import and reuse."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from .helpers import TOOLS

from member_a_app import evaluators
from member_a_app.device import FakeDeviceLink
from member_a_app.evidence import SessionStore, sha256_file
from member_a_app.evidence_import import import_all, repo_root_from_app
from member_a_app.model import Outcome
from member_a_app.requirements import get
from member_a_app.runner import AutoOperator, TestRunner

REPO_ROOT = repo_root_from_app()


class EvidenceImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SessionStore(pathlib.Path(self.temp.name) / "session", operator="tester")
        self.device = FakeDeviceLink(self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_import_all_canonical_corpora(self) -> None:
        summary = import_all(self.store)
        self.assertGreaterEqual(summary["imported"], 25)
        self.assertEqual(summary["errors"], [])
        self.assertEqual(summary["missing"], [])
        self.assertEqual(self.store.results(), {})
        bom = self.store.imported_for("A-W01-01")
        self.assertEqual(len(bom), 1)
        stored = self.store.root / bom[0]["stored"]
        self.assertTrue(stored.is_file())
        self.assertEqual(bom[0]["sha256"], sha256_file(stored))
        photos = [record for record in self.store.imported_for("A-W01-02")
                  if str(record["stored"]).lower().endswith((".jpg", ".jpeg", ".png"))]
        self.assertGreaterEqual(len(photos), 10)
        self.assertTrue(self.store.imported_for("A-W03-05"))
        second = import_all(self.store)
        self.assertEqual(second["imported"], 0)
        self.assertGreater(second["skipped_duplicate"], 0)

    def test_bom_handler_uses_imported_csv(self) -> None:
        import_all(self.store)
        operator = AutoOperator({"text": ["imported BOM audit"], "file": []})
        runner = TestRunner(self.store, self.device, operator, [get("A-W01-01")])
        result = runner.run("A-W01-01")
        # The authoritative BOM records HW-07 as an unapproved substitution.
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertTrue(any(check.name == "no_unapproved_substitution"
                            and check.passed is False for check in result.checks))
        self.assertTrue(result.evidence)
        self.assertTrue(any("bom-audit.csv" in str(item.get("stored", ""))
                            for item in result.evidence))

    def test_photo_inventory_uses_imported_photos(self) -> None:
        import_all(self.store)
        operator = AutoOperator({"file": []})
        runner = TestRunner(self.store, self.device, operator, [get("A-W01-02")])
        result = runner.run("A-W01-02")
        self.assertEqual(result.outcome, Outcome.PASS, result.failure_reason)
        self.assertGreaterEqual(len(result.evidence), 13)

    def test_documentary_uses_imported_evidence(self) -> None:
        import_all(self.store)
        operator = AutoOperator({"choose": ["Confirmed"] * 10,
                                 "text": ["imported pin investigation record"],
                                 "file": []})
        runner = TestRunner(self.store, self.device, operator, [get("A-W01-03")])
        result = runner.run("A-W01-03")
        self.assertEqual(result.outcome, Outcome.PASS, result.failure_reason)
        self.assertTrue(any("pin-candidates-v0.md" in str(item.get("stored", ""))
                            for item in result.evidence))


class H8GuardTests(unittest.TestCase):
    def test_canonical_test_is_incomplete_on_h8(self) -> None:
        from .helpers import h8_boot_lines, h8s_line
        with tempfile.TemporaryDirectory() as temp:
            store = SessionStore(pathlib.Path(temp) / "session", operator="tester")
            device = FakeDeviceLink(store)
            try:
                for line in h8_boot_lines():
                    device.feed_line(line)
                device.feed_line(h8s_line())
                operator = AutoOperator({})
                runner = TestRunner(store, device, operator, [get("A-W05-04")])
                result = runner.run("A-W05-04")
                self.assertEqual(result.outcome, Outcome.INCOMPLETE)
                self.assertIn("H8_BENCH_IMAGE", result.failure_reason)
            finally:
                store.close()

    def test_operator_measurement_still_runs_on_h8(self) -> None:
        from .helpers import h8_boot_lines, h8s_line
        with tempfile.TemporaryDirectory() as temp:
            store = SessionStore(pathlib.Path(temp) / "session", operator="tester")
            device = FakeDeviceLink(store)
            try:
                for line in h8_boot_lines():
                    device.feed_line(line)
                device.feed_line(h8s_line())
                evidence = pathlib.Path(temp) / "meter.md"
                evidence.write_text("5.01 V", encoding="utf-8")
                operator = AutoOperator({"number": [5.0], "text": ["meter record"],
                                         "file": [str(evidence)]})
                runner = TestRunner(store, device, operator, [get("A-W03-01")])
                result = runner.run("A-W03-01")
                self.assertEqual(result.outcome, Outcome.PASS, result.failure_reason)
                self.assertEqual(result.source, "OPERATOR_MEASUREMENT")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
