"""Protocol parsing and command validation."""

from __future__ import annotations

import unittest

from .helpers import fixture, telem_line

from member_a_app import protocol


class TelemetryParsingTests(unittest.TestCase):
    def test_canonical_schema3_fixture(self) -> None:
        parsed = protocol.parse_line(fixture("telem_schema3.txt"))
        self.assertEqual(parsed.kind, "TELEM")
        frame = parsed.frame
        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame.schema, 3)
        self.assertEqual(frame.device_id, "coldguard-001")
        self.assertEqual(frame.boot_id, "abcd0123")
        self.assertEqual(frame.seq, 1)
        self.assertEqual(frame.t_inside_c if hasattr(frame, "t_inside_c") else frame.chamber_c, 25.0625)
        self.assertEqual(frame.chamber_c, 25.0625)
        self.assertEqual(frame.hot_side_c, 25.0625)
        self.assertIsNone(frame.ambient_c)
        self.assertIsNone(frame.humidity_pct)
        self.assertIsNone(frame.door_open)
        self.assertEqual(frame.door_status, "UNVERIFIED")
        self.assertTrue(frame.electrical_valid())
        self.assertEqual(frame.output_stage, "DISABLED")
        self.assertEqual(frame.state, "OFF")
        self.assertEqual(frame.cooling_applied, "OFF")
        self.assertEqual(frame.warnings, ())
        self.assertEqual(frame.temperature("T2"), 25.0625)
        self.assertEqual(frame.energy_wh, 12.0)

    def test_missing_value_is_none_not_zero(self) -> None:
        frame = protocol.parse_line(fixture("telem_schema3.txt")).frame
        assert frame is not None
        self.assertIsNone(frame.ambient_c)
        self.assertIsNone(frame.humidity_pct)
        self.assertIsNone(frame.door_open)
        missing_energy = protocol.parse_line(
            telem_line().replace("energy_wh=12.0000", "energy_wh=nan")).frame
        assert missing_energy is not None
        self.assertIsNone(missing_energy.energy_wh)

    def test_fault_code_is_parsed_as_hex(self) -> None:
        frame = protocol.parse_line(telem_line(fault="0x00000001")).frame
        assert frame is not None
        self.assertEqual(frame.fault_bits, 1)
        healthy = protocol.parse_line(telem_line(fault="0x00000000")).frame
        assert healthy is not None
        self.assertEqual(healthy.fault_bits, 0)

    def test_unknown_state_is_not_default_off(self) -> None:
        frame = protocol.parse_line(
            telem_line().replace("tec_state=OFF", "tec_state=UNKNOWN")
            .replace("cooling_applied=OFF", "cooling_applied=nan")).frame
        assert frame is not None
        self.assertFalse(frame.is_default_off)

    def test_non_ok_status_masks_numeric_value(self) -> None:
        line = telem_line(current=5.0).replace("current_status=OK", "current_status=INVALID")
        frame = protocol.parse_line(line).frame
        assert frame is not None
        self.assertIsNone(frame.current_a)
        self.assertFalse(frame.electrical_valid())

    def test_h8s_alias_mapping(self) -> None:
        frame = protocol.parse_line(fixture("h8s_sample.txt")).frame
        assert frame is not None
        self.assertTrue(frame.is_h8)
        self.assertEqual(frame.kind, "H8S")
        self.assertEqual(frame.boot_id, "b45af2ff")
        self.assertEqual(frame.state, "OFF")
        self.assertIsNone(frame.current_a)
        self.assertEqual(frame.temperature_by_role("HOT_SIDE"), 29.938)
        self.assertEqual(frame.hot_side_c, 29.938)
        self.assertIsNone(frame.door_open)

    def test_identity_boot_and_rom_lines(self) -> None:
        boot = protocol.parse_line(
            "#CG BOOT event=IDENTITY device_id=coldguard-001 boot_id=abcd0123 "
            "boot_count=7 firmware_version=cg-w06-0.1.0 hardware_config_id=CG-HW-001 "
            "calibration_id=UNRECORDED")
        self.assertEqual(boot.boot.boot_id, "abcd0123")
        self.assertEqual(boot.boot.hardware_config_id, "CG-HW-001")
        rom = protocol.parse_line(
            "#CG ROM role=T2 rom=28AEBF2200000006 present=1 status=ROLE_ASSIGNED")
        self.assertEqual(rom.rom.role, "T2")
        self.assertEqual(rom.rom.rom, "28AEBF2200000006")
        auth = protocol.parse_line("#CG AUTH token=DEADBEEF ttl_ms=120000 clear_requires_token=1")
        self.assertEqual(auth.auth_token, "DEADBEEF")

    def test_command_ack(self) -> None:
        ack = protocol.parse_line(
            "#CG CMDACK schema=1 event=ACK command_id=abc command_id_form=TEST_TOKEN "
            "source=LOCAL_CONSOLE device_id=coldguard-001 boot_id=abcd0123 boot_count=7 "
            "uptime_ms=1000 ack_seq=42 status=REJECTED reason=EXPIRY_UNEVALUABLE "
            "desired_cooling=ON desired_duty_permille=100 applied_cooling=OFF "
            "applied_duty_permille=0 reapplied=0 expiry_evaluable=0 "
            "time_sync_state=UNSYNCHRONIZED device_mode=OFF fault_code=0x00000000 "
            "output_stage=DISABLED allowed_duty_max_permille=0").ack
        self.assertIsNotNone(ack)
        assert ack is not None
        self.assertEqual(ack.status, "REJECTED")
        self.assertFalse(ack.expiry_evaluable)
        self.assertEqual(ack.applied_cooling, "OFF")
        self.assertEqual(ack.output_stage, "DISABLED")


class CommandBuilderTests(unittest.TestCase):
    def test_valid_builders(self) -> None:
        self.assertEqual(protocol.arm("DEADBEEF"), b"ARM DEADBEEF\n")
        self.assertEqual(protocol.start(10), b"START 10\n")
        self.assertEqual(protocol.stop(), b"STOP\n")
        self.assertEqual(protocol.estop(), b"ESTOP\n")
        self.assertEqual(protocol.status(), b"STATUS\n")
        self.assertEqual(protocol.run_label("CG-S1-001"), b"RUN CG-S1-001\n")
        self.assertEqual(protocol.phase("G2"), b"PHASE G2\n")
        self.assertEqual(protocol.cmdtest("id-1", True, 100), b"CMDTEST id-1 ON 100\n")

    def test_invalid_inputs_refused(self) -> None:
        with self.assertRaises(protocol.CommandError):
            protocol.arm("nothex!")
        with self.assertRaises(protocol.CommandError):
            protocol.arm("ABC")
        with self.assertRaises(protocol.CommandError):
            protocol.clear("12345678 ")
        with self.assertRaises(protocol.CommandError):
            protocol.start(0)
        with self.assertRaises(protocol.CommandError):
            protocol.start(601)
        with self.assertRaises(protocol.CommandError):
            protocol.start("10; rm -rf /")
        with self.assertRaises(protocol.CommandError):
            protocol.run_label("bad label with spaces")
        with self.assertRaises(protocol.CommandError):
            protocol.phase("RUN")
        with self.assertRaises(protocol.CommandError):
            protocol.cmdtest("id", True, 1001)

    def test_probe_lines_are_safe_invalid_commands(self) -> None:
        for line in protocol.PROBE_LINES:
            self.assertNotIn("\n", line)
            if line.startswith("CMDTEST"):
                self.assertIn(" OFF 1001", line)
                self.assertNotIn(" ON 1001", line)
            self.assertNotIn("ARM DEADBEEF", line)


if __name__ == "__main__":
    unittest.main()
