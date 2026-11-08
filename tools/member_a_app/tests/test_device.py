"""Device link identity, queueing and acknowledgement behavior."""

from __future__ import annotations

import pathlib
import tempfile
import threading
import time
import unittest

from .helpers import boot_lines, h8_boot_lines, rom_lines, telem_line

from member_a_app.device import FakeDeviceLink
from member_a_app.evidence import SessionStore


class FakeSerialHandle:
    def __init__(self) -> None:
        self.port = None
        self.baudrate = None
        self.timeout = None
        self.write_timeout = None
        self.dtr = True
        self.rts = True
        self.closed = False

    def open(self) -> None:
        pass

    def read(self, count: int) -> bytes:
        time.sleep(0.02)
        return b""

    def write(self, data: bytes) -> int:
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class ReaderLifecycleTests(unittest.TestCase):
    def test_reboot_warm_leaves_exactly_one_reader(self) -> None:
        import types
        import member_a_app.device as device_module

        original = device_module.serial
        fake_module = types.SimpleNamespace(Serial=FakeSerialHandle,
                                            SerialException=Exception)
        device_module.serial = fake_module
        try:
            with tempfile.TemporaryDirectory() as temp:
                store = SessionStore(pathlib.Path(temp) / "session", operator="tester")
                link = device_module.DeviceLink(store)
                try:
                    link.open("FAKE")
                    self.assertTrue(link.reboot_warm(gap_s=0.0))
                    time.sleep(0.2)
                    readers = [thread for thread in threading.enumerate()
                               if thread.name == "cg-serial" and thread.is_alive()]
                    self.assertEqual(len(readers), 1)
                finally:
                    link.close()
                    store.close()
        finally:
            device_module.serial = original


class FakeDeviceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SessionStore(pathlib.Path(self.temp.name) / "session", operator="tester")
        self.device = FakeDeviceLink(self.store)
        for line in boot_lines() + rom_lines():
            self.device.feed_line(line)

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_identity_and_rom_map(self) -> None:
        self.device.feed_line(telem_line())
        snapshot = self.device.snapshot
        self.assertEqual(snapshot.boot.device_id, "coldguard-001")
        self.assertEqual(snapshot.boot.boot_id, "abcd0123")
        self.assertEqual(snapshot.boot.firmware_version, "cg-w06-0.1.0")
        self.assertEqual(snapshot.boot.hardware_config_id, "CG-HW-001")
        self.assertEqual(len(snapshot.rom_map), 4)
        self.assertEqual(snapshot.firmware_kind, "CANONICAL")

    def test_frame_queue(self) -> None:
        for index in range(3):
            self.device.feed_line(telem_line(seq=index + 1, uptime_ms=1000 + index * 1000))
        frames, cursor = self.device.frames_since(0)
        self.assertEqual(len(frames), 3)
        self.assertEqual([frame.seq for frame in frames], [1, 2, 3])
        later, _ = self.device.frames_since(2)
        self.assertEqual([frame.seq for frame in later], [3])

    def test_raw_and_telemetry_are_logged(self) -> None:
        self.device.feed_line(telem_line())
        raw = (self.store.root / "raw" / "serial.jsonl").read_text(encoding="utf-8")
        telemetry = (self.store.root / "raw" / "telemetry.jsonl").read_text(encoding="utf-8")
        self.assertIn("#CG TELEM", raw)
        self.assertIn("#CG TELEM", telemetry)

    def test_send_requires_newline_and_records(self) -> None:
        self.device.send(b"STATUS\n")
        self.assertEqual(self.device.sent, [b"STATUS\n"])
        with self.assertRaises(Exception):
            self.device.send(b"STATUS")

    def test_wait_for_boot_accepts_h8_boot_line(self) -> None:
        def responder() -> None:
            time.sleep(0.1)
            self.device.feed_line(h8_boot_lines()[0])
        threading.Thread(target=responder, daemon=True).start()
        boot = self.device.wait_for_boot("previous-boot", 2)
        self.assertIsNotNone(boot)
        assert boot is not None
        self.assertEqual(boot.boot_id, "b45af2ff")

    def test_wait_for_ack(self) -> None:
        def responder() -> None:
            time.sleep(0.1)
            self.device.feed_line(
                "#CG CMDACK schema=1 event=ACK command_id=abc status=REJECTED reason=X "
                "source=LOCAL_CONSOLE desired_cooling=ON desired_duty_permille=100 "
                "applied_cooling=OFF applied_duty_permille=0 expiry_evaluable=0 "
                "output_stage=DISABLED")
        threading.Thread(target=responder, daemon=True).start()
        ack = self.device.wait_for_ack("abc", 3)
        self.assertIsNotNone(ack)
        assert ack is not None
        self.assertEqual(ack.status, "REJECTED")
        self.assertEqual(ack.applied_cooling, "OFF")


if __name__ == "__main__":
    unittest.main()
