"""Runner behavior: gating, simulation downgrade, no automatic actuation."""

from __future__ import annotations

import pathlib
import tempfile
import threading
import time
import unittest

from .helpers import boot_lines, rom_lines, telem_line

from member_a_app import evaluators, protocol
from member_a_app.device import FakeDeviceLink
from member_a_app.evidence import SessionStore
from member_a_app.model import Outcome, TestBlocked
from member_a_app.requirements import get
from member_a_app.runner import AutoOperator, TestContext, TestRunner


def _ack(command_id: str, status: str = "SAFETY_BLOCKED",
         reason: str = "SOURCE_NOT_CANONICAL") -> str:
    return (
        f"#CG CMDACK schema=1 event=ACK command_id={command_id} command_id_form=TEST_TOKEN "
        "source=LOCAL_CONSOLE device_id=coldguard-001 boot_id=abcd0123 boot_count=7 "
        "uptime_ms=1000 ack_seq=42 status=" + status + f" reason={reason} "
        "desired_cooling=ON desired_duty_permille=100 applied_cooling=OFF "
        "applied_duty_permille=0 reapplied=0 expiry_evaluable=0 "
        "time_sync_state=UNSYNCHRONIZED device_mode=OFF fault_code=0x00000000 "
        "output_stage=DISABLED allowed_duty_max_permille=0"
    )


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SessionStore(pathlib.Path(self.temp.name) / "session", operator="tester")
        self.device = FakeDeviceLink(self.store)
        self.operator = AutoOperator({"text": ["auto"], "confirm": [True] * 20,
                                      "choose": ["Confirmed"] * 20,
                                      "number": [5.0] * 20})
        self.runner = TestRunner(self.store, self.device, self.operator, [get("A-W05-04")])

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def feed(self, count: int = 30, **kwargs: object) -> None:
        for index in range(count):
            values = dict(kwargs)
            values.setdefault("seq", index + 1)
            values.setdefault("uptime_ms", 1_000_000 + index * 1000)
            self.device.feed_line(telem_line(**values))

    def test_capture_is_bounded_and_rejects_overlong_duration(self) -> None:
        self.device.feed_line(telem_line(seq=1, uptime_ms=1_000_000))
        context = TestContext(get("A-W02-04"), self.store, self.device,
                              self.operator,
                              {"fast_simulation": False, "max_capture_s": 1.0})
        started = time.monotonic()
        with self.assertRaises(TestBlocked) as bounded:
            context.capture(0.2, min_frames=1)
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertIn("INSUFFICIENT_TELEMETRY", bounded.exception.reason)
        with self.assertRaises(TestBlocked) as caught:
            context.capture(5.0, min_frames=1)
        self.assertIn("CAPTURE_DURATION_EXCEEDS_LIMIT", caught.exception.reason)

    def test_simulated_session_cannot_pass(self) -> None:
        self.feed(30)
        result = self.runner.run("A-W05-04")
        self.assertEqual(result.outcome, Outcome.INCOMPLETE)
        self.assertIn("SIMULATED_SESSION", result.failure_reason)
        self.assertTrue(all(check.passed for check in result.checks))
        stored = self.store.result("A-W05-04")
        self.assertEqual(stored.outcome, Outcome.INCOMPLETE)

    def test_failed_check_fails_even_in_simulation(self) -> None:
        self.feed(30, quality="BOGUS")
        result = self.runner.run("A-W05-04")
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertTrue(result.failure_reason)

    def test_nonzero_fault_fails_quality_check(self) -> None:
        self.feed(30, fault="0x00000008")
        definition = get("A-W05-05")
        runner = TestRunner(self.store, self.device, self.operator, [definition])
        result = runner.run("A-W05-05")
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertTrue(any(check.name == "no_fault" and check.passed is False
                            for check in result.checks))

    def test_prerequisite_gating_records_incomplete(self) -> None:
        definition = get("A-W04-06")
        runner = TestRunner(self.store, self.device, self.operator, [definition])
        result = runner.run("A-W04-06")
        self.assertEqual(result.outcome, Outcome.INCOMPLETE)
        self.assertIn("PREREQUISITE_NOT_RUN A-W04-05", result.failure_reason)

    def test_documentary_test_can_pass_with_real_attachment(self) -> None:
        attachment = pathlib.Path(self.temp.name) / "pin-candidates.md"
        attachment.write_text("known/likely/unknown/must-test", encoding="utf-8")
        operator = AutoOperator({"choose": ["Confirmed"] * 10, "text": ["notes"],
                                 "file": [str(attachment)]})
        definition = get("A-W01-03")
        runner = TestRunner(self.store, self.device, operator, [definition])
        result = runner.run("A-W01-03")
        self.assertEqual(result.outcome, Outcome.PASS, result.failure_reason)
        self.assertEqual(result.source, "DOCUMENTARY")
        self.assertEqual(len(result.evidence), 1)
        self.assertTrue(all(check.passed for check in result.checks))

    def test_powered_actuation_blocks_on_disabled_stage_without_writing(self) -> None:
        self.device.feed_line(telem_line(output_stage="DISABLED"))
        context = TestContext(get("A-W04-05"), self.store, self.device,
                              AutoOperator({"confirm": [True] * 10}), {"fast_simulation": True})
        with self.assertRaises(TestBlocked) as caught:
            evaluators.HANDLERS["actuation_trace"](context)
        self.assertIn("OUTPUT_STAGE_COMPILED_OUT", caught.exception.reason)
        self.assertEqual(self.device.sent, [])

    def test_s4_method_passes_without_energizing(self) -> None:
        self.device.feed_line(telem_line(output_stage="DISABLED"))
        attachment = pathlib.Path(self.temp.name) / "s4.md"
        attachment.write_text("software refusal only", encoding="utf-8")
        operator = AutoOperator({"confirm": [True], "file": [str(attachment)]})
        context = TestContext(get("A-W11-01"), self.store, self.device, operator,
                              {"fast_simulation": True})
        evaluators.HANDLERS["s4_method"](context)
        self.assertTrue(all(check.passed for check in context.checks))
        self.assertEqual(self.device.sent, [])

    def test_command_parser_rejects_malformed_and_out_of_range(self) -> None:
        self.device.feed_line(telem_line())
        operator = AutoOperator({})
        context = TestContext(get("A-W06-01"), self.store, self.device, operator,
                              {"fast_simulation": True})

        def responder() -> None:
            time.sleep(0.15)
            for line in protocol.PROBE_LINES:
                self.device.feed_line(
                    "#CG ERR console=PARSE_FAIL error=CMDTEST_BAD_DUTY"
                    if line.startswith("CMDTEST") else "#CG ERR console=PARSE_FAIL")
            command_id = None
            for _ in range(40):
                command_id = context.measurements.get("validator_command_id")
                if command_id:
                    break
                time.sleep(0.02)
            self.device.feed_line(_ack(command_id or "missing"))

        threading.Thread(target=responder, daemon=True).start()
        with self.assertRaises(TestBlocked) as caught:
            evaluators.HANDLERS["command_parser"](context)
        self.assertIn("NETWORK_TRANSPORT_UNAVAILABLE", caught.exception.reason)
        self.assertTrue(any(check.name == "malformed_lines_rejected" and check.passed
                            for check in context.checks))
        self.assertTrue(any(check.name == "console_duty_bound_rejected" and check.passed
                            for check in context.checks))
        self.assertTrue(any(check.name == "fail_closed_rejection" and check.passed
                            for check in context.checks))

    def test_command_expiry_records_fail_closed_and_blocks_exact_test(self) -> None:
        self.device.feed_line(telem_line())
        context = TestContext(get("A-W06-03"), self.store, self.device, AutoOperator({}),
                              {"fast_simulation": True})

        def responder() -> None:
            time.sleep(0.15)
            command_id = None
            for _ in range(40):
                command_id = context.measurements.get("validator_command_id")
                if command_id:
                    break
                time.sleep(0.02)
            self.device.feed_line(_ack(command_id or "missing"))

        threading.Thread(target=responder, daemon=True).start()
        with self.assertRaises(TestBlocked) as caught:
            evaluators.HANDLERS["command_expiry"](context)
        self.assertIn("NO_WALL_CLOCK", caught.exception.reason)
        self.assertTrue(any(check.name == "command_refused" and check.passed
                            for check in context.checks))


class FullRegistryRunnerTests(unittest.TestCase):
    def test_all_114_have_handlers(self) -> None:
        from member_a_app.requirements import DEFINITIONS
        for definition in DEFINITIONS:
            self.assertIn(definition.handler, evaluators.HANDLERS, definition.test_id)


if __name__ == "__main__":
    unittest.main()
