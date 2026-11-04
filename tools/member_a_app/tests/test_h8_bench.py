"""H8 read-only capture and supervised Stage F flow."""

from __future__ import annotations

import pathlib
import tempfile
import threading
import time
import unittest

from .helpers import h8_boot_lines, h8_cmd, h8s_line

from member_a_app import h8_bench, protocol
from member_a_app.device import FakeDeviceLink
from member_a_app.evidence import SessionStore
from member_a_app.h8_bench import H8Bench
from member_a_app.runner import AutoOperator


class H8Simulator(threading.Thread):
    def __init__(self, device: FakeDeviceLink, start_result: str = "START_OK") -> None:
        super().__init__(daemon=True)
        self.device = device
        self.start_result = start_result
        self.stop_event = threading.Event()
        self.seen = 0
        self.run_id = "run-00000000"
        self.seq = 1

    def _frame(self, **kwargs: object) -> None:
        self.device.feed_line(h8s_line(**kwargs))

    def _handle(self, text: str) -> None:
        if text.startswith("SUPERVISE"):
            self.device.feed_line(h8_cmd("SUPERVISED_AUTHORIZED", state="OFF"))
            self._frame(supervised_authorized="1")
        elif text.startswith("STAGE"):
            self.device.feed_line(h8_cmd("STAGE_SELECTED", stage="H8-CHECK", duration_s="30"))
            self._frame(stage="H8-CHECK", supervised_authorized="1")
        elif text.startswith("FAN"):
            self.device.feed_line(h8_cmd("FAN_CONFIRMED", source="OPERATOR"))
            self._frame(stage="H8-CHECK", fan="CONFIRMED", supervised_authorized="1")
        elif text.startswith("DOOR"):
            self.device.feed_line(h8_cmd("DOOR_POLARITY_CONFIRMED", near="LOW"))
            self._frame(stage="H8-CHECK", fan="CONFIRMED", door_polarity="NEAR_LOW",
                        supervised_authorized="1")
        elif text.startswith("ACK"):
            parts = text.split()
            seq = int(parts[2]) if len(parts) >= 3 else 0
            self.device.feed_line(h8_cmd("ACK_ACCEPTED", seq=seq))
        elif text.startswith("ARM"):
            self.device.feed_line(h8_cmd("ARMED", stage="H8-CHECK", ttl_ms="30000"))
            self._frame(state="ARMED", stage="H8-CHECK", fan="CONFIRMED",
                        door_polarity="NEAR_LOW", supervised_authorized="1")
        elif text == "START":
            self.device.feed_line(h8_cmd(f"{self.start_result}", stage="H8-CHECK",
                                         run_counter="1"))
            if self.start_result in {"START_OK", "START_OK_SUPERVISED"}:
                self._frame(state="COOLING", stage="H8-CHECK", run_id="run-00000001",
                            seq=2, current=1.8, pwm=200, t2=31.0, fan="CONFIRMED",
                            door_polarity="NEAR_LOW", supervised_authorized="1")
        elif text == "STOP":
            self.device.feed_line(h8_cmd("STOP", state="COOLDOWN", duty_readback="0",
                                         off_verify="PASS"))
            self._frame(state="OFF", run_id="run-00000001", seq=3, current=0.0,
                        pwm=0, t2=30.0, fan="CONFIRMED", door_polarity="NEAR_LOW",
                        supervised_authorized="1")
        elif text == "ESTOP":
            self.device.feed_line(h8_cmd("ESTOP", state="FAULT_LATCH"))
            self._frame(state="FAULT_LATCH", run_id="run-00000001", seq=4,
                        current=0.0, pwm=0, fault="0x2000")

    def run(self) -> None:
        while not self.stop_event.is_set():
            sent = list(self.device.sent)
            for command in sent[self.seen:]:
                self._handle(command.decode("ascii", errors="replace").strip())
            self.seen = len(sent)
            time.sleep(0.01)


class H8BenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SessionStore(pathlib.Path(self.temp.name) / "session", operator="tester")
        self.device = FakeDeviceLink(self.store)
        for line in h8_boot_lines():
            self.device.feed_line(line)
        self.device.feed_line(h8s_line())
        self.operator = AutoOperator({
            "confirm": [True] * 30,
            "choose": ["NEAR_LOW (raw 0)"] * 5,
            "text": ["DEADBEEF"] * 5,
        })
        self.sim: H8Simulator | None = None

    def tearDown(self) -> None:
        if self.sim is not None:
            self.sim.stop_event.set()
            self.sim.join(timeout=2)
        self.store.close()
        self.temp.cleanup()

    def _start_sim(self, start_result: str = "START_OK") -> None:
        self.sim = H8Simulator(self.device, start_result)
        self.sim.start()

    def test_read_only_capture_sends_nothing(self) -> None:
        for index in range(10):
            self.device.feed_line(h8s_line(seq=index + 1, run_id=f"run-{index:08x}"))
        payload = H8Bench(self.device, self.store, self.operator).read_only(0.2)
        self.assertEqual(payload["outcome"], "PASS")
        self.assertEqual(self.device.sent, [])
        self.assertTrue(self.store.bench_results())

    def test_supervised_stage_f_pass_sequence(self) -> None:
        self._start_sim()
        cooling = protocol.parse_line(h8s_line(
            state="COOLING", run_id="run-00000001", seq=2, current=1.8,
            pwm=199, t2=31.0, fan="CONFIRMED", door_polarity="NEAR_LOW")).frame
        assert cooling is not None
        original = h8_bench._capture
        h8_bench._capture = lambda *args, **kwargs: ([cooling], None)  # type: ignore[assignment]
        try:
            payload = H8Bench(self.device, self.store, self.operator).supervised_stage_f()
        finally:
            h8_bench._capture = original  # type: ignore[assignment]
        self.assertEqual(payload["outcome"], "PASS", payload.get("reason"))
        sent = [command.decode("ascii").strip() for command in self.device.sent]
        self.assertIn("STAGE F", sent)
        self.assertIn("SUPERVISE DEADBEEF", sent)
        self.assertIn("FAN DEADBEEF", sent)
        self.assertIn("DOOR NEAR_LOW DEADBEEF", sent)
        self.assertIn("ARM DEADBEEF", sent)
        self.assertIn("START", sent)
        self.assertIn("STOP", sent)
        self.assertFalse(any(command in {"STAGE A", "STAGE B", "STAGE C", "STAGE D",
                                         "STAGE E"} for command in sent))
        self.assertTrue(any(command.startswith("ACK ") for command in sent))
        self.assertTrue(payload["measurements"]["ack_count"] >= 1)
        self.assertTrue(self.store.bench_results())

    def test_supervised_stage_f_rejects_pwm_outside_quantization(self) -> None:
        self._start_sim()
        cooling = protocol.parse_line(h8s_line(
            state="COOLING", run_id="run-00000001", seq=2, current=1.8,
            pwm=202, t2=31.0, fan="CONFIRMED", door_polarity="NEAR_LOW")).frame
        assert cooling is not None
        original = h8_bench._capture
        h8_bench._capture = lambda *args, **kwargs: ([cooling], None)  # type: ignore[assignment]
        try:
            payload = H8Bench(self.device, self.store, self.operator).supervised_stage_f()
        finally:
            h8_bench._capture = original  # type: ignore[assignment]
        self.assertEqual(payload["outcome"], "FAIL")
        self.assertTrue(any(item.get("failure_reason") == "H8_PWM_NOT_200_PERMILLE"
                            for item in payload["checks"]))

    def test_supervised_stage_f_refusal_is_incomplete_and_disarms(self) -> None:
        self._start_sim("START_STAGE_F_GUARD_UNAPPROVED")
        payload = H8Bench(self.device, self.store, self.operator).supervised_stage_f()
        self.assertEqual(payload["outcome"], "INCOMPLETE")
        self.assertIn("H8_START_REFUSED", payload["reason"])
        sent = [command.decode("ascii").strip() for command in self.device.sent]
        self.assertIn("STAGE F", sent)
        self.assertIn("STOP", sent)
        self.assertFalse(any(command.startswith("STAGE A") for command in sent))

    def test_start_not_confirmed_never_energizes_and_disarms(self) -> None:
        self._start_sim()
        self.operator.answers["confirm"] = [True, True, True, True, False]
        payload = H8Bench(self.device, self.store, self.operator).supervised_stage_f()
        self.assertEqual(payload["outcome"], "INCOMPLETE")
        self.assertIn("H8_STAGE_F_START_NOT_CONFIRMED", payload["reason"])
        sent = [command.decode("ascii").strip() for command in self.device.sent]
        self.assertNotIn("START", sent)
        self.assertIn("STOP", sent)

    def test_precheck_refusal_sends_no_commands(self) -> None:
        self.operator.answers["confirm"] = [False] * 5
        payload = H8Bench(self.device, self.store, self.operator).supervised_stage_f()
        self.assertEqual(payload["outcome"], "INCOMPLETE")
        self.assertIn("PRECHECK_NOT_CONFIRMED", payload["reason"])
        self.assertEqual(self.device.sent, [])

    def test_ack_keeper_emits_ack_for_h8_frame(self) -> None:
        self.device.set_h8_ack(True)
        self.device.feed_line(h8s_line(state="COOLING", run_id="run-00000005", seq=9,
                                       current=1.8, pwm=200))
        self.device.set_h8_ack(False)
        sent = [command.decode("ascii").strip() for command in self.device.sent]
        self.assertIn("ACK 00000005 9", sent)


if __name__ == "__main__":
    unittest.main()
