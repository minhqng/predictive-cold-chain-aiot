"""Tests for the host-side Modbus RTU codec (firmware/tools/cg_modbus.py).

The frames here are synthetic fixtures: they exercise the CRC, the
read-only builders, the response classification and the register scaling.
They are never evidence.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_modbus  # noqa: E402
import cg_pzem_fixtures as fixtures  # noqa: E402


class CrcTests(unittest.TestCase):
    def test_known_read_vector_from_bench_sketch(self) -> None:
        # 01 04 0000 0001 31 CA is the request the W01 bench sketch sent and
        # the PZEM answered to; the anchor is external to this codec.
        frame = bytes.fromhex("01040000000131CA")
        self.assertEqual(cg_modbus.crc16(frame[:-2]), 0xCA31)
        self.assertTrue(cg_modbus.crc_ok(frame))

    def test_append_crc_writes_low_byte_first(self) -> None:
        frame = cg_modbus.append_crc(bytes.fromhex("010400000001"))
        self.assertEqual(frame.hex().upper(), "01040000000131CA")

    def test_any_bit_flip_is_detected(self) -> None:
        frame = cg_modbus.append_crc(bytes.fromhex("010400000006"))
        for index in range(len(frame) - 1):
            damaged = frame[:index] + bytes((frame[index] ^ 0x01,)) + frame[index + 1 :]
            self.assertFalse(cg_modbus.crc_ok(damaged), f"flip at {index} not detected")

    def test_short_frames_are_not_certified(self) -> None:
        for frame in (b"", b"\x01", b"\x01\x02", b"\x01\x02\x03"):
            self.assertFalse(cg_modbus.crc_ok(frame))


class BuilderTests(unittest.TestCase):
    def test_read_input_request(self) -> None:
        self.assertEqual(cg_modbus.build_read_input(1).hex().upper(), "0104000000067008")

    def test_read_range_request(self) -> None:
        self.assertEqual(cg_modbus.build_read_range(1).hex().upper(), "010300030001740A")

    def test_write_function_codes_are_refused(self) -> None:
        for function in (0x05, 0x06, 0x0F, 0x10):
            with self.assertRaises(ValueError):
                cg_modbus.build_read_request(1, function, 0x0000, 1)

    def test_slave_and_count_ranges(self) -> None:
        with self.assertRaises(ValueError):
            cg_modbus.build_read_request(0, 0x04, 0x0000, 1)
        with self.assertRaises(ValueError):
            cg_modbus.build_read_request(248, 0x04, 0x0000, 1)
        with self.assertRaises(ValueError):
            cg_modbus.build_read_request(1, 0x04, 0x0000, 0)
        with self.assertRaises(ValueError):
            cg_modbus.build_read_request(1, 0x04, 0x0000, 0x7E)


class ParseInputTests(unittest.TestCase):
    def test_ok_frame_decodes_six_registers(self) -> None:
        rx = fixtures.input_response(1, 1234, 5, 123, 456)
        parsed = cg_modbus.parse_input(rx, 1)
        self.assertIs(parsed.status, cg_modbus.Status.OK)
        self.assertEqual(parsed.registers, (1234, 5, 123, 0, 456, 0))

    def test_bad_crc(self) -> None:
        rx = fixtures.input_response(1, 1234, 5, 123, 456)
        damaged = rx[:-1] + bytes((rx[-1] ^ 0xFF,))
        self.assertIs(cg_modbus.parse_input(damaged, 1).status, cg_modbus.Status.CRC_ERR)

    def test_wrong_slave(self) -> None:
        rx = fixtures.input_response(7, 1234, 5, 123, 456)
        self.assertIs(cg_modbus.parse_input(rx, 1).status, cg_modbus.Status.BAD_SLAVE)

    def test_wrong_function(self) -> None:
        # A properly framed 0x03 response is not an answer to a 0x04 read.
        rx = fixtures.range_response(1, 0x0001)
        self.assertIs(cg_modbus.parse_input(rx, 1).status, cg_modbus.Status.BAD_FUNCTION)
        # Same for a longer wrong-function frame.
        payload = bytes((1, 0x03, 12)) + bytes(12)
        rx = cg_modbus.append_crc(payload)
        parsed = cg_modbus.parse_input(rx, 1)
        self.assertIs(parsed.status, cg_modbus.Status.BAD_FUNCTION)

    def test_exception_frame_carries_the_code(self) -> None:
        rx = cg_modbus.append_crc(bytes((1, 0x04 | 0x80, 0x02)))
        parsed = cg_modbus.parse_input(rx, 1)
        self.assertIs(parsed.status, cg_modbus.Status.EXCEPTION)
        self.assertEqual(parsed.exception_code, 2)

    def test_short_and_no_response(self) -> None:
        self.assertIs(cg_modbus.parse_input(b"", 1).status, cg_modbus.Status.BAD_LENGTH)
        self.assertIs(cg_modbus.parse_input(b"\x01\x04", 1).status, cg_modbus.Status.BAD_LENGTH)

    def test_bad_byte_count(self) -> None:
        payload = bytes((1, 0x04, 10)) + bytes(10)
        rx = cg_modbus.append_crc(payload)
        self.assertIs(cg_modbus.parse_input(rx, 1).status, cg_modbus.Status.BAD_LENGTH)


class ParseRangeTests(unittest.TestCase):
    def test_ok_frame(self) -> None:
        parsed = cg_modbus.parse_range(fixtures.range_response(1, 0x0001), 1)
        self.assertIs(parsed.status, cg_modbus.Status.OK)
        self.assertEqual(parsed.registers, (0x0001,))

    def test_profile_names(self) -> None:
        self.assertEqual(cg_modbus.profile_name(0x0000), "100A")
        self.assertEqual(cg_modbus.profile_name(0x0001), "50A")
        self.assertEqual(cg_modbus.profile_name(0x0002), "200A")
        self.assertEqual(cg_modbus.profile_name(0x0003), "300A")
        self.assertEqual(cg_modbus.profile_name(0x0099), "UNKNOWN")

    def test_format_range_readback(self) -> None:
        report = cg_modbus.format_range_readback(fixtures.range_response(1, 0x0001), 1)
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["raw_value"], 1)
        self.assertEqual(report["value_hex"], "0x0001")
        self.assertEqual(report["profile"], "50A")
        self.assertTrue(report["crc_ok"])

    def test_format_range_readback_reports_rejections(self) -> None:
        damaged = fixtures.range_response(1, 0x0001)
        damaged = damaged[:-1] + bytes((damaged[-1] ^ 0xFF,))
        report = cg_modbus.format_range_readback(damaged, 1)
        self.assertEqual(report["status"], "CRC_ERR")
        self.assertIsNone(report["raw_value"])
        self.assertFalse(report["crc_ok"])


class ExtractResponseTests(unittest.TestCase):
    """The transport extractor must accept a framed tail, never an echo."""

    def test_input_exact_and_prefixed(self) -> None:
        frame = fixtures.input_response(1, 1234, 5, 123, 456)
        echo = cg_modbus.build_read_input(1)
        for prefix in (b"", b"\xaa" * 7, echo):
            extracted = cg_modbus.extract_response(prefix + frame)
            self.assertIs(extracted.status, cg_modbus.Status.OK)
            self.assertEqual(extracted.frame, frame)

    def test_range_exact_and_prefixed(self) -> None:
        frame = fixtures.range_response(1, 0x0001)
        echo = cg_modbus.build_read_range(1)
        for prefix in (b"", b"\xaa" * 7, echo):
            extracted = cg_modbus.extract_response(prefix + frame)
            self.assertIs(extracted.status, cg_modbus.Status.OK)
            self.assertEqual(extracted.frame, frame)

    def test_exception_exact_and_prefixed(self) -> None:
        frame = cg_modbus.append_crc(bytes((1, 0x84, 0x02)))
        for prefix in (b"", b"\xaa" * 7, cg_modbus.build_read_input(1)):
            extracted = cg_modbus.extract_response(prefix + frame)
            self.assertIs(extracted.status, cg_modbus.Status.OK)
            self.assertEqual(extracted.frame, frame)
            self.assertIs(
                cg_modbus.parse_input(extracted.frame, 1).status,
                cg_modbus.Status.EXCEPTION,
            )

    def test_bad_crc_is_rejected(self) -> None:
        frame = fixtures.input_response(1, 1234, 5, 123, 456)
        damaged = frame[:-1] + bytes((frame[-1] ^ 0xFF,))
        extracted = cg_modbus.extract_response(damaged)
        self.assertIs(extracted.status, cg_modbus.Status.CRC_ERR)
        self.assertIsNone(extracted.frame)

    def test_wrong_slave_function_and_byte_count_are_not_decoded(self) -> None:
        wrong_slave = fixtures.input_response(7, 1234, 5, 123, 456)
        parsed = cg_modbus.parse_input(
            cg_modbus.extract_response(wrong_slave).frame, 1
        )
        self.assertIs(parsed.status, cg_modbus.Status.BAD_SLAVE)

        wrong_function = fixtures.range_response(1, 0x0001)
        parsed = cg_modbus.parse_input(
            cg_modbus.extract_response(wrong_function).frame, 1
        )
        self.assertIs(parsed.status, cg_modbus.Status.BAD_FUNCTION)

        wrong_count = cg_modbus.append_crc(bytes((1, 0x04, 10)) + bytes(10))
        parsed = cg_modbus.parse_input(
            cg_modbus.extract_response(wrong_count).frame, 1
        )
        self.assertIs(parsed.status, cg_modbus.Status.BAD_LENGTH)

    def test_truncated_echo_and_garbage_are_not_frames(self) -> None:
        frame = fixtures.input_response(1, 1234, 5, 123, 456)
        for raw in (frame[:10], cg_modbus.build_read_input(1), b"\xde\xad\xbe\xef" * 4):
            extracted = cg_modbus.extract_response(raw)
            self.assertNotEqual(extracted.status, cg_modbus.Status.OK)
            self.assertIsNone(extracted.frame)

    def test_trailing_garbage_prevents_a_tail_match(self) -> None:
        frame = fixtures.range_response(1, 0x0001)
        extracted = cg_modbus.extract_response(frame + b"\x00")
        self.assertIs(extracted.status, cg_modbus.Status.BAD_LENGTH)
        self.assertIsNone(extracted.frame)

    def test_stale_frame_is_not_selected(self) -> None:
        stale = fixtures.range_response(1, 0x0000)
        current = fixtures.range_response(1, 0x0001)
        extracted = cg_modbus.extract_response(stale + current)
        self.assertIs(extracted.status, cg_modbus.Status.OK)
        self.assertEqual(extracted.frame, current)

    def test_two_valid_interpretations_are_ambiguous(self) -> None:
        # The 17-byte input response is valid; its last 7 bytes are also a
        # valid range response. Guessing either could fabricate telemetry.
        raw = bytes.fromhex("01040C2DCA00000000000103020000B844")
        self.assertIs(cg_modbus.parse_input(raw[:17], 1).status, cg_modbus.Status.OK)
        self.assertIs(cg_modbus.parse_range(raw[10:], 1).status, cg_modbus.Status.OK)
        extracted = cg_modbus.extract_response(raw)
        self.assertIs(extracted.status, cg_modbus.Status.BAD_LENGTH)
        self.assertIsNone(extracted.frame)

    def test_wrong_exception_function_and_length_are_rejected(self) -> None:
        wrong_function = cg_modbus.append_crc(bytes((1, 0x83, 0x02)))
        self.assertIs(
            cg_modbus.parse_input(wrong_function, 1).status,
            cg_modbus.Status.BAD_FUNCTION,
        )
        wrong_length = cg_modbus.append_crc(bytes((1, 0x84, 0x02, 0x00)))
        self.assertIs(
            cg_modbus.parse_input(wrong_length, 1).status,
            cg_modbus.Status.BAD_LENGTH,
        )


class ScalingTests(unittest.TestCase):
    def test_input_decode_uses_documented_lsb(self) -> None:
        # V = 12.34 V, I = 0.05 A, P = 12.3 W (123 * 0.1), E = 456 Wh.
        rx = fixtures.input_response(1, 1234, 5, 123, 456)
        parsed = cg_modbus.parse_input(rx, 1)
        values = cg_modbus.decode_input(parsed.registers)
        self.assertAlmostEqual(values.voltage_v, 12.34, places=6)
        self.assertAlmostEqual(values.current_a, 0.05, places=6)
        self.assertAlmostEqual(values.power_w, 12.3, places=6)
        self.assertAlmostEqual(values.energy_wh, 456.0, places=6)

    def test_power_and_energy_are_low_word_first(self) -> None:
        # Power raw words: low=0x0000, high=0x0001 -> 65536 * 0.1 = 6553.6 W.
        rx = fixtures.input_response(1, 0, 0, 0x10000, 0)
        parsed = cg_modbus.parse_input(rx, 1)
        values = cg_modbus.decode_input(parsed.registers)
        self.assertAlmostEqual(values.power_w, 6553.6, places=3)
        # Swapping the words would give 1 * 0.1 = 0.1 W instead.
        rx_swapped = fixtures.input_response(1, 0, 0, 0x0001, 0)
        swapped = cg_modbus.decode_input(cg_modbus.parse_input(rx_swapped, 1).registers)
        self.assertAlmostEqual(swapped.power_w, 0.1, places=3)

    def test_decode_needs_six_registers(self) -> None:
        with self.assertRaises(cg_modbus.FrameError):
            cg_modbus.decode_input((1, 2, 3))


if __name__ == "__main__":
    unittest.main()
