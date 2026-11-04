"""Regression tests for defects found by the independent review."""

from __future__ import annotations

import pathlib
import tempfile
import threading
import time
import unittest

from .helpers import boot_lines, fixture, rom_lines, telem_line

from member_a_app import analysis, evaluators, protocol
from member_a_app.device import FakeDeviceLink
from member_a_app.evidence import SessionStore
from member_a_app.model import Outcome, TestBlocked
from member_a_app.requirements import DEFINITIONS, get
from member_a_app.runner import AutoOperator, TestContext, TestRunner


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SessionStore(pathlib.Path(self.temp.name) / "session", operator="tester")
        self.device = FakeDeviceLink(self.store)
        for line in boot_lines() + rom_lines():
            self.device.feed_line(line)
        self.evidence = pathlib.Path(self.temp.name) / "evidence.md"
        self.evidence.write_text("evidence", encoding="utf-8")

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def context(self, test_id: str, operator: AutoOperator | None = None) -> TestContext:
        return TestContext(get(test_id), self.store, self.device,
                           operator or AutoOperator({"confirm": [True] * 50,
                                                      "choose": ["NO-GO"] * 10,
                                                      "text": ["rationale"] * 10,
                                                      "file": [str(self.evidence)] * 10}),
                           {"fast_simulation": True})

    def test_hil_smoke_requires_supervised_prechecks(self) -> None:
        for index in range(10):
            self.device.feed_line(telem_line(seq=index + 1, uptime_ms=1_000_000 + index * 1000,
                                             ambient=24.0, humidity=45.0,
                                             output_stage="ENABLED", current=0.0))
        operator = AutoOperator({"confirm": [False], "file": [str(self.evidence)]})
        context = self.context("A-W24-02", operator)
        with self.assertRaises(TestBlocked) as caught:
            evaluators.HANDLERS["hil_smoke"](context)
        self.assertIn("PRECHECK_NOT_CONFIRMED", caught.exception.reason)

    def test_cooling_step_rejects_zero_current(self) -> None:
        frames = [protocol.parse_line(telem_line(
            seq=index + 1, uptime_ms=1_000_000 + index * 1000,
            cooling="ON", state="COOLING", current=0.0,
            output_stage="ENABLED")).frame for index in range(10)]
        frames = [frame for frame in frames if frame is not None]
        metrics = analysis.cooling_step_metrics(frames)
        valid, reason = evaluators._run_valid("COOLING_STEP", metrics, {})
        self.assertFalse(valid)
        self.assertEqual(reason, "NO_ACTIVE_CURRENT")

    def test_pzem_link_blocks_without_pzem_lines(self) -> None:
        for index in range(30):
            self.device.feed_line(telem_line(seq=index + 1, uptime_ms=1_000_000 + index * 1000))
        context = self.context("A-W03-03")
        with self.assertRaises(TestBlocked) as caught:
            evaluators.HANDLERS["pzem_link"](context)
        self.assertIn("NO_PZEM_LINES", caught.exception.reason)

    def test_applied_state_blocks_h8_image(self) -> None:
        self.device.feed_line(fixture("h8s_sample.txt"))
        context = self.context("A-W06-04")
        with self.assertRaises(TestBlocked) as caught:
            evaluators.HANDLERS["applied_state"](context)
        self.assertIn("H8_BENCH_IMAGE", caught.exception.reason)

    def test_command_reset_requires_accepted_command(self) -> None:
        self.device.feed_line(telem_line())
        context = self.context("A-W06-06")

        def responder() -> None:
            time.sleep(0.15)
            command_id = None
            for _ in range(40):
                command_id = context.measurements.get("validator_command_id")
                if command_id:
                    break
                time.sleep(0.02)
            self.device.feed_line(
                "#CG CMDACK schema=1 event=ACK command_id=" + (command_id or "missing") +
                " command_id_form=TEST_TOKEN source=LOCAL_CONSOLE status=REJECTED "
                "reason=EXPIRY_UNEVALUABLE desired_cooling=ON desired_duty_permille=100 "
                "applied_cooling=OFF applied_duty_permille=0 expiry_evaluable=0 "
                "output_stage=DISABLED")

        threading.Thread(target=responder, daemon=True).start()
        with self.assertRaises(TestBlocked) as caught:
            evaluators.HANDLERS["command_reset"](context)
        self.assertIn("NO_ACCEPTED_COMMAND_STATE", caught.exception.reason)
        self.assertFalse(any(command.startswith(b"ARM") or command.startswith(b"START")
                             for command in self.device.sent))

    def test_s4_refusal_captures_no_response(self) -> None:
        self.device.feed_line("#CG AUTH token=DEADBEEF ttl_ms=120000 clear_requires_token=1")
        for index in range(20):
            self.device.feed_line(telem_line(seq=index + 1, uptime_ms=1_000_000 + index * 1000,
                                             output_stage="DISABLED", current=0.0))
        context = self.context("A-W11-02")

        def responder() -> None:
            time.sleep(0.1)
            self.device.feed_line(
                "#CG TEC event=ARM result=ARMED reason=OK state=ARMED fault=0x00000000 "
                "duty=0 elapsed_ms=0 remaining_ms=0 starts=0 stops=0 estops=0 faults=0 "
                "refusals=0 fan=0")
            time.sleep(0.1)
            self.device.feed_line(
                "#CG TEC event=START result=STAGE_UNAVAILABLE reason=STAGE_DISABLED "
                "state=ARMED fault=0x00000000 duty=0 elapsed_ms=0 remaining_ms=0 starts=0 "
                "stops=0 estops=0 faults=0 refusals=0 fan=0")

        threading.Thread(target=responder, daemon=True).start()
        evaluators.HANDLERS["s4_refusal"](context)
        self.assertTrue(any(check.name == "start_refused" and check.passed
                            for check in context.checks))
        self.assertTrue(any(check.name == "no_active_current" and check.passed
                            for check in context.checks))
        self.assertTrue(any(check.name == "applied_state_off" and check.passed
                            for check in context.checks))

    def test_s2_coverage_is_enforced(self) -> None:
        valid, reason = evaluators._run_valid("S2", {"coverage": 0.5, "valid": True},
                                              {"min_coverage": 0.85})
        self.assertFalse(valid)
        self.assertIn("LOW_COVERAGE", reason)

    def test_wait_for_off_waits_through_cooldown(self) -> None:
        self.device.feed_line(telem_line(seq=1, uptime_ms=1_000_000, state="COOLDOWN",
                                         cooling="OFF"))
        context = self.context("A-W04-05")

        def release() -> None:
            time.sleep(0.2)
            self.device.feed_line(telem_line(seq=2, uptime_ms=1_001_000, state="OFF",
                                             cooling="OFF"))

        threading.Thread(target=release, daemon=True).start()
        evaluators._wait_for_off(context, timeout_s=3.0)
        self.assertEqual(self.device.latest_frame().state, "OFF")

    def test_run_series_persists_completed_attempts_on_block(self) -> None:
        for index in range(60):
            self.device.feed_line(telem_line(seq=index + 1,
                                             uptime_ms=1_000_000 + index * 1000, door=1))
        operator = AutoOperator({"choose": ["Start run"] * 20, "text": ["reason"] * 20,
                                 "confirm": [True] * 20})
        context = self.context("A-W07-02", operator)
        with self.assertRaises(TestBlocked) as caught:
            evaluators.HANDLERS["run_series"](context)
        self.assertIn("VALID_RUN_TARGET_NOT_REACHED", caught.exception.reason)
        runs = context.measurements.get("runs") or []
        self.assertGreaterEqual(len(runs), 1)
        self.assertTrue(any("DOOR_OPEN_DURING_WARMUP" in str(run.get("reason"))
                            for run in runs))
        self.assertTrue(context.evidence)
        stored = self.store.root / context.evidence[0]["stored"]
        self.assertIn("DOOR_OPEN_DURING_WARMUP", stored.read_text(encoding="utf-8"))

    def test_stop_timeout_escalates_to_estop(self) -> None:
        self.device.feed_line(telem_line())
        context = self.context("A-W04-05")
        original = self.device.wait_for_event
        self.device.wait_for_event = lambda *args, **kwargs: None  # type: ignore[assignment]
        try:
            event = evaluators._stop_cooling(context)
        finally:
            self.device.wait_for_event = original  # type: ignore[assignment]
        self.assertIsNone(event)
        self.assertTrue(any(check.name == "stop_confirmed" and check.passed is False
                            for check in context.checks))
        self.assertTrue(any(command.startswith(b"ESTOP") for command in self.device.sent))

    def test_stop_ack_immediately_after_send_is_not_missed(self) -> None:
        self.device.feed_line(telem_line())
        context = self.context("A-W04-05")
        original_send = self.device.send

        def send_and_ack(command: bytes, description: str = "") -> None:
            original_send(command, description)
            if command == b"STOP\n":
                self.device.feed_line(
                    "#CG TEC event=STOP result=OK reason=OPERATOR state=COOLDOWN "
                    "fault=0x00000000 duty=0 elapsed_ms=0 remaining_ms=0 starts=0 stops=1 "
                    "estops=0 faults=0 refusals=0 fan=1")

        self.device.send = send_and_ack  # type: ignore[assignment]
        try:
            event = evaluators._stop_cooling(context)
        finally:
            self.device.send = original_send  # type: ignore[assignment]
        self.assertIsNotNone(event)
        self.assertTrue(any(check.name == "stop_confirmed" and check.passed
                            for check in context.checks))

    def test_canonical_supervised_arm_sends_supervise_first(self) -> None:
        self.device.feed_line(
            "#CG AUTH token=DEADBEEF ttl_ms=120000 clear_requires_token=1")
        for index in range(20):
            self.device.feed_line(telem_line(
                seq=index + 1, uptime_ms=1_000_000 + index * 1000,
                output_stage="ENABLED", state="OFF", cooling="OFF", current=0.0,
                supervised=1, interlock="ABSENT",
                bench_policy="SUPERVISED_HOT_SIDE_ONLY"))
        context = self.context("A-W04-05")
        seen = 0

        def responder() -> None:
            nonlocal seen
            while True:
                sent = list(self.device.sent)
                for command in sent[seen:]:
                    text = command.decode("ascii").strip()
                    if text.startswith("SUPERVISE"):
                        self.device.feed_line(
                            "#CG TEC event=SUPERVISE result=SUPERVISED_AUTHORIZED reason=OK "
                            "state=OFF fault=0x00000000 duty=0 elapsed_ms=0 remaining_ms=0 "
                            "starts=0 stops=0 estops=0 faults=0 refusals=0 fan=1")
                    elif text.startswith("ARM"):
                        self.device.feed_line(
                            "#CG TEC event=ARM result=ARMED reason=OK state=ARMED "
                            "fault=0x00000000 duty=0 elapsed_ms=0 remaining_ms=0 starts=0 "
                            "stops=0 estops=0 faults=0 refusals=0 fan=1")
                    elif text.startswith("START"):
                        self.device.feed_line(
                            "#CG TEC event=START result=START_OK reason=OK state=COOLING "
                            "fault=0x00000000 duty=500 elapsed_ms=0 remaining_ms=60000 "
                            "starts=1 stops=0 estops=0 faults=0 refusals=0 fan=1")
                    elif text == "STOP":
                        self.device.feed_line(
                            "#CG TEC event=STOP result=OK reason=OPERATOR_STOP "
                            "state=COOLDOWN fault=0x00000000 duty=0 elapsed_ms=1000 "
                            "remaining_ms=0 starts=1 stops=1 estops=0 faults=0 refusals=0 fan=1")
                seen = len(sent)
                time.sleep(0.01)

        threading.Thread(target=responder, daemon=True).start()
        started, _ = evaluators._arm_and_start(context, 60)
        self.assertTrue(started)
        evaluators._stop_cooling(context)
        commands = [command.decode("ascii").strip() for command in self.device.sent]
        supervise = next(i for i, command in enumerate(commands) if command.startswith("SUPERVISE"))
        arm = next(i for i, command in enumerate(commands) if command.startswith("ARM"))
        start = next(i for i, command in enumerate(commands) if command.startswith("START"))
        self.assertLess(supervise, arm)
        self.assertLess(arm, start)
        self.assertTrue(any(check.name == "supervise_authorized" and check.passed
                            for check in context.checks))

    def test_door_attestation_requires_same_boot_closed_raw_zero(self) -> None:
        unknown = (telem_line(seq=1, uptime_ms=1_000_000, door=0)
                   .replace("door_open=0", "door_open=UNKNOWN")
                   .replace("door_status=OK", "door_status=UNVERIFIED"))
        self.device.feed_line(unknown)
        context = self.context("A-W07-02")
        sent = False

        def responder() -> None:
            nonlocal sent
            while not sent:
                if any(command == b"DOOR\n" for command in self.device.sent):
                    self.device.feed_line(telem_line(seq=2, uptime_ms=1_001_000,
                                                     door=0, boot="abcd0123"))
                    sent = True
                time.sleep(0.01)

        threading.Thread(target=responder, daemon=True).start()
        evaluators._ensure_door_attested(context)
        self.assertTrue(any(check.name == "door_attested" and check.passed
                            for check in context.checks))

    def test_actuation_refuses_nonzero_off_baseline(self) -> None:
        for index in range(25):
            self.device.feed_line(telem_line(seq=index + 1,
                                             uptime_ms=1_000_000 + index * 1000,
                                             output_stage="ENABLED", current=1.0,
                                             state="OFF", cooling="OFF"))
        context = self.context("A-W04-05")
        with self.assertRaises(TestBlocked) as caught:
            evaluators.HANDLERS["actuation_trace"](context)
        self.assertIn("BASELINE_NOT_OFF", caught.exception.reason)
        self.assertFalse(any(command.startswith(b"ARM") for command in self.device.sent))

    def test_no_go_decision_is_an_acceptable_result(self) -> None:
        context = self.context("A-W15-04")
        evaluators.HANDLERS["decision"](context)
        self.assertEqual(context.measurements.get("decision"), "NO-GO")
        self.assertTrue(all(check.passed for check in context.checks), context.checks)

    def test_composite_requires_recorded_attempts(self) -> None:
        context = self.context("A-W12-05")
        with self.assertRaises(TestBlocked) as caught:
            evaluators.HANDLERS["composite"](context)
        self.assertIn("REQUIREMENT_NOT_RUN", caught.exception.reason)

    def test_soak_detects_reboot(self) -> None:
        frames = []
        for index in range(4):
            frames.append(protocol.parse_line(telem_line(
                seq=index + 1, uptime_ms=1_000_000 + index * 1000,
                boot="abcd0123" if index < 2 else "abcd9999")).frame)
        metrics = analysis.soak_metrics([frame for frame in frames if frame is not None])
        self.assertEqual(metrics["boot_changes"], 1)

    def test_measurement_record_is_updated_not_duplicated(self) -> None:
        context = self.context("A-W01-03")
        context.measurements["first"] = 1
        context.save_measurements()
        first_sha = context.evidence[0]["sha256"]
        context.measurements["second"] = 2
        context.save_measurements()
        self.assertEqual(len(context.evidence), 1)
        self.assertNotEqual(first_sha, context.evidence[0]["sha256"])
        stored = self.store.root / context.evidence[0]["stored"]
        self.assertIn("second", stored.read_text(encoding="utf-8"))


class RomFallbackTests(unittest.TestCase):
    def test_telem_rom_fields_populate_map_without_boot_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SessionStore(pathlib.Path(temp) / "session", operator="tester")
            try:
                device = FakeDeviceLink(store)
                device.feed_line(telem_line())
                self.assertEqual(len(device.snapshot.rom_map), 4)
                self.assertEqual(device.snapshot.rom_map["T2"].rom, "28AEBF2200000006")
            finally:
                store.close()


class ResetCriterionGradientTests(unittest.TestCase):
    """The reset-criterion gradient bound limits temporal Tmean movement, not the
    instantaneous cross-probe spread (which A-W12-01/A-W14-02 bound instead)."""

    def _run(self, lines):
        with tempfile.TemporaryDirectory() as temp:
            store = SessionStore(pathlib.Path(temp) / "session", operator="tester")
            try:
                device = FakeDeviceLink(store)
                for line in boot_lines() + rom_lines() + lines:
                    device.feed_line(line)
                operator = AutoOperator({"number": [29.5, 30.6, 0.05],
                                         "text": ["state-based criterion, temporal gradient"],
                                         "confirm": [True] * 5})
                context = TestContext(get("A-W07-05"), store, device, operator,
                                      {"fast_simulation": True})
                evaluators.HANDLERS["reset_criterion"](context)
                return context
            finally:
                store.close()

    def test_flat_state_with_wide_spatial_spread_passes(self):
        lines = [telem_line(seq=i + 1, uptime_ms=1_000_000 + i * 1000,
                            t1=30.00, t3=29.69, spare=30.06, t2=29.80,
                            output_stage="ENABLED") for i in range(12)]
        context = self._run(lines)
        by_name = {c.name: c for c in context.checks}
        self.assertTrue(by_name["gradient_bounded"].passed, by_name["gradient_bounded"].detail)
        self.assertTrue(all(c.passed for c in context.checks),
                        [(c.name, c.detail) for c in context.checks if not c.passed])

    def test_drifting_state_is_rejected_despite_tight_spatial_spread(self):
        lines = []
        for i in range(12):
            base = 29.95 + 0.09 * i / 11.0
            lines.append(telem_line(seq=i + 1, uptime_ms=1_000_000 + i * 1000,
                                    t1=base + 0.01, t3=base - 0.01, spare=base,
                                    t2=base, output_stage="ENABLED"))
        context = self._run(lines)
        by_name = {c.name: c for c in context.checks}
        self.assertFalse(by_name["gradient_bounded"].passed)
        self.assertIn("CURRENT_GRADIENT_OUTSIDE_BOUND",
                      [c.failure_reason for c in context.checks if not c.passed])


if __name__ == "__main__":
    unittest.main()
