"""Evidence persistence, hashing, resume and 114-ID report."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from .helpers import telem_line

from member_a_app import protocol
from member_a_app.evidence import EvidenceError, SessionStore, sha256_file
from member_a_app.model import CheckResult, Outcome, TestResult, now_iso
from member_a_app.requirements import DEFINITIONS


def result_for(test_id: str, outcome: Outcome = Outcome.PASS, source: str = "HARDWARE",
           reason: str = "") -> TestResult:
    return TestResult(
        test_id=test_id, outcome=outcome, started_at=now_iso(), ended_at=now_iso(),
        checks=[CheckResult(name="x", passed=outcome is Outcome.PASS)],
        failure_reason=reason, source=source,
    )


class SessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name) / "session"
        self.store = SessionStore(self.root, operator="tester")

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_result_roundtrip_and_resume(self) -> None:
        self.store.record_result(result_for("A-W01-01"))
        self.store.close()
        resumed = SessionStore(self.root)
        try:
            self.assertEqual(resumed.result("A-W01-01").outcome, Outcome.PASS)
            self.assertEqual(resumed.session["operator"], "tester")
        finally:
            resumed.close()

    def test_simulated_pass_is_rejected(self) -> None:
        with self.assertRaises(EvidenceError):
            self.store.record_result(result_for("A-W01-01", source="SIMULATED"))

    def test_noncanonical_id_is_rejected(self) -> None:
        with self.assertRaises(EvidenceError):
            self.store.record_result(result_for("A-W1-1"))

    def test_attachment_hash_and_tamper_detection(self) -> None:
        attachment = pathlib.Path(self.temp.name) / "photo.txt"
        attachment.write_text("evidence bytes", encoding="utf-8")
        record = self.store.attach("A-W01-02", attachment)
        self.assertEqual(record["sha256"], sha256_file(attachment))
        stored = self.root / record["stored"]
        self.assertTrue(stored.is_file())
        result = result_for("A-W01-02", Outcome.PASS, "DOCUMENTARY")
        result.evidence.append(record)
        self.store.record_result(result)
        self.assertEqual(self.store.verify_attachments(), [])
        stored.write_text("tampered", encoding="utf-8")
        problems = self.store.verify_attachments()
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["problem"], "HASH_MISMATCH")

    def test_empty_attachment_rejected(self) -> None:
        empty = pathlib.Path(self.temp.name) / "empty.txt"
        empty.write_text("", encoding="utf-8")
        with self.assertRaises(EvidenceError):
            self.store.attach("A-W01-02", empty)

    def test_raw_lines_and_telemetry_are_separate(self) -> None:
        self.store.append_raw("TX", "START 10\n")
        parsed = protocol.parse_line(telem_line())
        assert parsed.frame is not None
        self.store.append_telemetry(parsed.frame)
        raw = (self.root / "raw" / "serial.jsonl").read_text(encoding="utf-8").splitlines()
        telemetry = (self.root / "raw" / "telemetry.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(raw[0])["direction"], "TX")
        self.assertEqual(json.loads(telemetry[0])["kind"], "TELEM")

    def test_measurement_files_are_unique_and_verifiable(self) -> None:
        first = self.store.save_measurements("A-W04-05", {"v": 1})
        second = self.store.save_measurements("A-W04-05", {"v": 2})
        self.assertNotEqual(first["stored"], second["stored"])
        result = result_for("A-W04-05")
        result.evidence.append(second)
        self.store.record_result(result)
        self.assertEqual(self.store.verify_attachments(), [])
        (self.root / second["stored"]).write_text("tampered", encoding="utf-8")
        problems = self.store.verify_attachments()
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["problem"], "HASH_MISMATCH")

    def test_repeated_attempt_is_preserved(self) -> None:
        self.store.record_result(result_for("A-W01-01"))
        self.store.record_result(result_for("A-W01-01", Outcome.INCOMPLETE,
                                            "HARDWARE", "SECOND_ATTEMPT"))
        self.assertEqual(self.store.attempt_count("A-W01-01"), 2)
        history = list((self.root / "results" / "history").glob("A-W01-01-*.json"))
        self.assertEqual(len(history), 1)
        self.assertEqual(self.store.result("A-W01-01").outcome, Outcome.INCOMPLETE)

    def test_telemetry_csv_export(self) -> None:
        for index in range(2):
            parsed = protocol.parse_line(telem_line(seq=index + 1,
                                                   uptime_ms=1000 + index * 1000))
            assert parsed.frame is not None
            self.store.append_telemetry(parsed.frame)
        info = self.store.export_telemetry_csv()
        self.assertEqual(info["rows"], 2)
        text = pathlib.Path(info["path"]).read_text(encoding="utf-8")
        self.assertIn("t1_c", text)
        self.assertEqual(len(text.strip().splitlines()), 3)

    def test_report_contains_all_114_ids(self) -> None:
        self.store.record_result(result_for("A-W01-01"))
        self.store.record_result(result_for("A-W05-04", Outcome.INCOMPLETE, reason="NO_HARDWARE"))
        paths = self.store.export_report(DEFINITIONS)
        payload = json.loads(pathlib.Path(paths["json"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["coverage"]["canonical"], 114)
        self.assertEqual(len(payload["results"]), 114)
        ids = {row["test_id"] for row in payload["results"]}
        self.assertEqual(ids, {definition.test_id for definition in DEFINITIONS})
        self.assertEqual(payload["summary"]["PASS"], 1)
        self.assertEqual(payload["summary"]["INCOMPLETE"], 1)
        self.assertEqual(payload["summary"]["NOT_RUN"], 112)
        markdown = pathlib.Path(paths["markdown"]).read_text(encoding="utf-8")
        self.assertIn("A-W24-04", markdown)
        csv_text = pathlib.Path(paths["csv"]).read_text(encoding="utf-8")
        self.assertEqual(len(csv_text.strip().splitlines()), 115)

    def test_session_digest_changes_when_result_is_added(self) -> None:
        first = self.store.session_digest()
        self.store.record_result(result_for("A-W01-01"))
        self.assertNotEqual(first, self.store.session_digest())


if __name__ == "__main__":
    unittest.main()
