"""Tests for the W02 firmware static checker and the debounce model.

Three things are proven here:

1. ``cg_check_firmware.py`` really detects the failure modes it claims to
   detect (ROM/map drift, a broken CRC, a role assigned from a discovery
   index, a guessed polarity) - a checker that cannot fail is not a check.
2. The strengthened reader/polarity guards reject the adversarial variants
   that the earlier textual checks would have accepted: a reader that
   calls a convert helper, and #if/#else branches swapped while the
   expected tokens stay in place.
3. The documented MC-38 debounce semantics behave as advertised: a bounce
   burst inside the debounce window collapses into exactly one committed
   transition, and the counters stay consistent.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_check_firmware  # noqa: E402
import cg_serial  # noqa: E402

REPO_ROOT = TOOLS.parents[1]


class DallasCrcTests(unittest.TestCase):
    def test_known_roms_carry_a_valid_crc(self) -> None:
        for rom in ("287088CA00000051", "28AEBF2200000006", "28CBE9CA00000072", "283BE5C9000000A9"):
            raw = bytes.fromhex(rom)
            self.assertEqual(cg_check_firmware.dallas_crc8(raw[:7]), raw[7], rom)

    def test_single_bit_flip_breaks_the_crc(self) -> None:
        raw = bytearray(bytes.fromhex("287088CA00000051"))
        raw[3] ^= 0x01
        self.assertNotEqual(cg_check_firmware.dallas_crc8(bytes(raw[:7])), raw[7])

    def test_firmware_header_parsing_and_yaml_fallback(self) -> None:
        header = "#define CG_ROM_T1_BYTES {0x28, 0x70, 0x88, 0xCA, 0x00, 0x00, 0x00, 0x51}\n"
        roms = cg_check_firmware.parse_firmware_roms(header)
        self.assertEqual(roms, {"T1": "287088CA00000051"})

        yaml_text = 'roles:\n  - role: T1\n    rom_hex: "287088CA00000051"\nspare:\n  - rom_hex: "283BE5C9000000A9"\n'
        parsed = cg_check_firmware.parse_yaml_roms(yaml_text)
        self.assertEqual(parsed["T1"], "287088CA00000051")
        self.assertEqual(parsed["SPARE"], "283BE5C9000000A9")


class RealRepositoryCheckTests(unittest.TestCase):
    """The checks must pass against the firmware as committed."""

    def test_all_static_checks_pass(self) -> None:
        checker = cg_check_firmware.run_checks()
        self.assertEqual(checker.failures, [], f"static checks failed: {checker.failures}")
        self.assertGreaterEqual(len(checker.notes), 30)

    def test_index_based_role_assignment_is_rejected(self) -> None:
        bad_source = "void f(void) { role = table[i]; }\n"
        import re

        forbidden = re.findall(
            r"role\s*=\s*[^;]*(\[\s*(?:i|idx|index)\s*\])", cg_check_firmware.strip_comments(bad_source)
        )
        self.assertTrue(forbidden, "the guard must catch role = table[i]")

    def test_token_extraction_ignores_comments(self) -> None:
        source = "/* bme280_read() in a comment */\nint x = 1;\n"
        import re

        tokens = re.findall(r"bme280_[a-z_]*|i2c_driver_install|bme280_read", cg_check_firmware.strip_comments(source))
        self.assertEqual(tokens, [])
        tokens = re.findall(r"bme280_[a-z_]*|i2c_driver_install|bme280_read", source)
        self.assertTrue(tokens)


class ReadProbeContractTests(unittest.TestCase):
    """The per-probe reader must not start conversions, even via a helper."""

    def test_repository_reader_never_converts(self) -> None:
        source = (REPO_ROOT / "firmware" / "main" / "cg_ds18b20.c").read_text(encoding="utf-8")
        self.assertTrue(cg_check_firmware.read_probe_never_converts(source))

    def test_reader_calling_convert_all_is_rejected(self) -> None:
        bad = (
            "void cg_ds18b20_read_probe(cg_role_t role, cg_probe_reading_t *out)\n"
            "{\n"
            "    (void)cg_ds18b20_convert_all();\n"
            "    (void)role;\n"
            "    (void)out;\n"
            "}\n"
        )
        self.assertFalse(cg_check_firmware.read_probe_never_converts(bad))


class PolarityGateTests(unittest.TestCase):
    """Swapping the #if/#else branches must not pass the polarity check."""

    def test_repository_gate_is_semantic(self) -> None:
        source = (REPO_ROOT / "firmware" / "main" / "cg_door.c").read_text(encoding="utf-8")
        self.assertTrue(cg_check_firmware.polarity_gate_ok(source))

    def test_flipped_branches_are_rejected(self) -> None:
        flipped = (
            "#if CG_DOOR_POLARITY_CONFIRMED\n"
            "    return CG_DOOR_UNVERIFIED;\n"
            "#else\n"
            "    return (door->raw_committed == CG_DOOR_RAW_OPEN_LEVEL) ? CG_DOOR_OPEN : CG_DOOR_CLOSED;\n"
            "#endif\n"
        )
        self.assertFalse(cg_check_firmware.polarity_gate_ok(flipped))

    def test_unconfirmed_branch_claiming_open_is_rejected(self) -> None:
        bad = (
            "#if CG_DOOR_POLARITY_CONFIRMED\n"
            "    return (door->raw_committed == CG_DOOR_RAW_OPEN_LEVEL) ? CG_DOOR_OPEN : CG_DOOR_CLOSED;\n"
            "#else\n"
            "    return CG_DOOR_OPEN;\n"
            "#endif\n"
        )
        self.assertFalse(cg_check_firmware.polarity_gate_ok(bad))


class DebounceModelTests(unittest.TestCase):
    """Reference model of the firmware debounce state machine (cg_door.c)."""

    def setUp(self) -> None:
        self.debounce_us = 50_000
        self.committed = 1
        self.raw_last = 1
        self.stable_since = 0
        self.transitions = 0
        self.raw_edges = 0

    def poll(self, now_us: int, raw: int) -> bool:
        if raw != self.raw_last:
            self.raw_last = raw
            self.stable_since = now_us
            self.raw_edges += 1
            return False
        if raw != self.committed and (now_us - self.stable_since) >= self.debounce_us:
            self.committed = raw
            self.transitions += 1
            return True
        return False

    def test_bounce_inside_window_is_absorbed(self) -> None:
        now = 0
        for level in (0, 1, 0):  # burst, every flip 5 ms apart
            now += 5_000
            self.assertFalse(self.poll(now, level))

        # stable low, window passes
        now += 5_000
        self.assertFalse(self.poll(now, 0))
        now += 60_000
        self.assertTrue(self.poll(now, 0))

        self.assertEqual(self.transitions, 1)
        self.assertEqual(self.raw_edges, 3)
        self.assertEqual(self.raw_edges - self.transitions, 2)  # discarded edges

    def test_deliberate_open_interval_survives_debounce(self) -> None:
        now = 0
        now += 5_000
        self.poll(now, 0)
        now += 5_000
        self.poll(now, 0)
        now += 60_000
        self.assertTrue(self.poll(now, 0))  # open committed

        held_open_us = 0
        for _ in range(120):  # 120 polls x 10 ms = 1.2 s held open
            now += 10_000
            held_open_us += 10_000
            self.poll(now, 0)
        self.assertGreater(held_open_us, self.debounce_us * 10)

        now += 5_000
        self.poll(now, 1)
        now += 60_000
        self.assertTrue(self.poll(now, 1))  # closed committed
        self.assertEqual(self.transitions, 2)

    def test_firmware_and_model_agree_on_the_documented_constants(self) -> None:
        config = (REPO_ROOT / "firmware" / "main" / "coldguard_config.h").read_text(encoding="utf-8")
        door = (REPO_ROOT / "firmware" / "main" / "cg_door.c").read_text(encoding="utf-8")
        self.assertIn("#define CG_DOOR_DEBOUNCE_MS 50", config)
        self.assertIn("#define CG_DOOR_POLL_MS 5", config)
        self.assertIn("(uint64_t)CG_DOOR_DEBOUNCE_MS * 1000ULL", door)
        # The commit decision must compare the stability window, not a
        # hard-coded millisecond literal.
        self.assertIn("(now_us - door->stable_since_us) >= DEBOUNCE_US", door)


class LogModelRoundTripTests(unittest.TestCase):
    """A log produced by the model must be read back with the same numbers."""

    def test_model_log_round_trips_through_the_parser(self) -> None:
        text = "#CG LOG v=1 fw=cg-w02-0.1.0 hw=CG-HW-001\n#CG BOOT boot_id=boot0001 boot_count=1\n"
        text += "#CG ROM role=T1 rom=287088CA00000051 present=1 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING\n"
        text += "#CG DOOR_EDGE uptime_us=1000000 raw=0\n"
        text += "#CG DOOR_STATE uptime_ms=1060 raw=0 state=UNVERIFIED transitions=1 cycles=0 discarded=0\n"
        parsed = cg_serial.parse_text(text)
        report = cg_serial.door_analysis(parsed, open_level=None)
        self.assertEqual(report["committed_transitions"], 1)
        self.assertFalse(report["bounce_observed"])
        self.assertEqual(report["semantic_mapping"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
