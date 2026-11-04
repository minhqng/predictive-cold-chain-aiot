"""H8 bench protocol parsing and command builders."""

from __future__ import annotations

import unittest

from .helpers import h8_boot_lines, h8_cmd, h8s_line

from member_a_app import protocol, protocol_h8


class H8ParseTests(unittest.TestCase):
    def test_boot_token_and_policy(self) -> None:
        boot = protocol.parse_line(h8_boot_lines()[0])
        self.assertEqual(boot.kind, "H8_BOOT")
        self.assertEqual(boot.boot.boot_id, "b45af2ff")
        self.assertEqual(boot.boot.firmware_version, "h8-bench")
        self.assertEqual(boot.auth_token, "DEADBEEF")
        policy = protocol.parse_line(h8_boot_lines()[1])
        self.assertEqual(policy.kind, "H8_BOOT_POLICY")
        self.assertEqual(policy.kv["check_pwm"], "20")
        off = protocol.parse_line(h8_boot_lines()[2])
        self.assertEqual(off.kind, "H8_BOOT_OFF_CURRENT")
        self.assertEqual(off.kv["off_current_approved"], "1")

    def test_command_result_line(self) -> None:
        parsed = protocol.parse_line(h8_cmd("START_STAGE_F_GUARD_UNAPPROVED",
                                            stage="H8-CHECK"))
        self.assertEqual(parsed.kind, "H8_CMD")
        self.assertEqual(parsed.kv["result"], "START_STAGE_F_GUARD_UNAPPROVED")
        self.assertEqual(parsed.kv["stage"], "H8-CHECK")

    def test_h8s_frame_still_parses(self) -> None:
        frame = protocol.parse_line(h8s_line(state="COOLING", current=1.8, pwm=200,
                                             t2=31.0)).frame
        assert frame is not None
        self.assertTrue(frame.is_h8)
        self.assertEqual(frame.state, "COOLING")
        self.assertEqual(frame.current_a, 1.8)
        self.assertEqual(frame.pwm_applied, 200)
        self.assertEqual(frame.temperature_by_role("HOT_SIDE"), 31.0)


class H8BuilderTests(unittest.TestCase):
    def test_builders(self) -> None:
        self.assertEqual(protocol_h8.stage("f"), b"STAGE F\n")
        self.assertEqual(protocol_h8.supervise("deadbeef"), b"SUPERVISE DEADBEEF\n")
        self.assertEqual(protocol_h8.arm("1234"), b"ARM 1234\n")
        self.assertEqual(protocol_h8.start(), b"START\n")
        self.assertEqual(protocol_h8.stop(), b"STOP\n")
        self.assertEqual(protocol_h8.estop(), b"ESTOP\n")
        self.assertEqual(protocol_h8.clear("1234"), b"CLEAR 1234\n")
        self.assertEqual(protocol_h8.fan("1234"), b"FAN 1234\n")
        self.assertEqual(protocol_h8.door(True, "1234"), b"DOOR NEAR_LOW 1234\n")
        self.assertEqual(protocol_h8.door(False, "1234"), b"DOOR NEAR_HIGH 1234\n")
        self.assertEqual(protocol_h8.status(), b"STATUS\n")
        self.assertEqual(protocol_h8.ack("run-00000001", 9), b"ACK 00000001 9\n")
        self.assertEqual(protocol_h8.ack(0x12, 3), b"ACK 00000012 3\n")

    def test_invalid_inputs(self) -> None:
        for value in ("", "XYZ", "123456789"):
            with self.assertRaises(protocol.CommandError):
                protocol_h8.token(value)
        with self.assertRaises(protocol.CommandError):
            protocol_h8.stage("G")
        with self.assertRaises(protocol.CommandError):
            protocol_h8.ack("run-zzzz", 1)
        with self.assertRaises(protocol.CommandError):
            protocol_h8.ack("run-00000001", -1)

    def test_ack_from_frame(self) -> None:
        frame = protocol.parse_line(h8s_line(seq=7, run_id="run-0000002a")).frame
        assert frame is not None
        self.assertEqual(protocol_h8.ack_from_frame(frame), b"ACK 0000002a 7\n")


if __name__ == "__main__":
    unittest.main()
