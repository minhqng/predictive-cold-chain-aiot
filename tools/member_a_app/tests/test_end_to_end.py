"""End-to-end mixed session: documentary PASS, simulated hardware INCOMPLETE."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from .helpers import boot_lines, rom_lines, telem_line

from member_a_app.device import FakeDeviceLink
from member_a_app.evidence import SessionStore
from member_a_app.model import Outcome
from member_a_app.requirements import DEFINITIONS, get
from member_a_app.runner import AutoOperator, TestRunner


class EndToEndSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name) / "session"
        self.store = SessionStore(self.root, operator="operator")
        self.device = FakeDeviceLink(self.store)
        for line in boot_lines() + rom_lines():
            self.device.feed_line(line)
        for index in range(30):
            self.device.feed_line(telem_line(
                seq=index + 1, uptime_ms=1_000_000 + index * 1000,
                door=0, ambient=24.0, humidity=45.0))
        self.attachment = pathlib.Path(self.temp.name) / "evidence.md"
        self.attachment.write_text("documented evidence", encoding="utf-8")
        self.operator = AutoOperator({
            "choose": ["Confirmed"] * 12,
            "confirm": [True] * 12,
            "text": ["notes", "rationale", "none", "none", "none"],
            "file": [str(self.attachment)] * 6,
        })
        self.ids = ["A-W01-03", "A-W05-04", "A-W06-04"]
        self.runner = TestRunner(self.store, self.device, self.operator,
                                 [get(test_id) for test_id in self.ids])

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_documentary_pass_and_hardware_incomplete(self) -> None:
        for test_id in self.ids:
            self.runner.run(test_id)
        self.assertEqual(self.store.result("A-W01-03").outcome, Outcome.PASS)
        for test_id in ("A-W05-04", "A-W06-04"):
            result = self.store.result(test_id)
            self.assertEqual(result.outcome, Outcome.INCOMPLETE, test_id)
            self.assertIn("SIMULATED_SESSION", result.failure_reason)
            self.assertTrue(all(check.passed for check in result.checks), test_id)

    def test_report_is_complete_and_marks_simulated_sources(self) -> None:
        for test_id in self.ids:
            self.runner.run(test_id)
        paths = self.store.export_report(DEFINITIONS)
        payload = json.loads(pathlib.Path(paths["json"]).read_text(encoding="utf-8"))
        self.assertEqual(len(payload["results"]), 114)
        by_id = {row["test_id"]: row for row in payload["results"]}
        self.assertEqual(by_id["A-W01-03"]["outcome"], "PASS")
        self.assertEqual(by_id["A-W05-04"]["outcome"], "INCOMPLETE")
        self.assertEqual(payload["summary"]["PASS"], 1)
        self.assertEqual(payload["summary"]["INCOMPLETE"], 2)
        self.assertEqual(payload["summary"]["NOT_RUN"], 111)
        self.assertTrue(payload["evidence_integrity"]["ok"])
        self.assertIsInstance(payload["session_digest"], str)
        self.assertEqual(len(payload["session_digest"]), 64)


if __name__ == "__main__":
    unittest.main()
