"""Tests for the ColdGuard W02 serial-log core (firmware/tools/cg_serial.py).

The fixtures below are *synthetic logs*. They exist to exercise the parser
and the arithmetic - they are never evidence and are never written into
evidence/A/W02/.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_serial  # noqa: E402

ROM_T1 = "287088CA00000051"
ROM_T2 = "28AEBF2200000006"
ROM_T3 = "28CBE9CA00000072"
ROM_SPARE = "283BE5C9000000A9"


def rom_block(boot_index: int) -> str:
    return (
        f"#CG ROM role=T1 rom={ROM_T1} present=1 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING\n"
        f"#CG ROM role=T2 rom={ROM_T2} present=1 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING\n"
        f"#CG ROM role=T3 rom={ROM_T3} present=1 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING\n"
        f"#CG ROM role=SPARE rom={ROM_SPARE} present=1 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING\n"
        "#CG ROMS required_present=3/3 known=4 known_present=4\n"
    )


def boot_block(boot_index: int) -> str:
    return f"#CG BOOT boot_id=boot{boot_index:04d} boot_count={boot_index}\n" + rom_block(boot_index)


def sample_line(uptime_ms: int, seq: int, t1: str, t2: str, t3: str, thermal="VALID") -> str:
    t1_flag = 0 if t1 == "nan" else 1
    t2_flag = 0 if t2 == "nan" else 1
    t3_flag = 0 if t3 == "nan" else 1
    return (
        f"#CG SAMPLE uptime_ms={uptime_ms} seq={seq} T1={t1} T2={t2} T3={t3} SPARE=nan "
        f"t1={t1_flag} t2={t2_flag} t3={t3_flag} thermal={thermal} door_raw=1 door=UNVERIFIED\n"
    )


class ParseTests(unittest.TestCase):
    def test_boot_grouping_and_rom_map(self) -> None:
        text = "#CG LOG v=1 fw=cg-w02-0.1.0 hw=CG-HW-001\n"
        text += boot_block(1)
        text += boot_block(2)
        parsed = cg_serial.parse_text(text)
        self.assertEqual(len(parsed.boots), 2)
        self.assertEqual(parsed.boots[0].rom_of("T1"), ROM_T1)
        self.assertEqual(parsed.boots[1].rom_of("T3"), ROM_T3)
        self.assertTrue(parsed.boots[0].role_present("T2"))
        self.assertEqual(parsed.boots[0].rom_summary["required_present"], 3)

    def test_non_machine_lines_are_counted_not_rewritten(self) -> None:
        text = "ESP-ROM:esp32s3-20210327\nBuild:Mar 27 2021\n" + boot_block(1)
        parsed = cg_serial.parse_text(text)
        self.assertEqual(parsed.non_machine_lines, 2)
        self.assertEqual(len(parsed.boots), 1)

    def test_unknown_machine_kind_is_preserved(self) -> None:
        parsed = cg_serial.parse_text("#CG FUTURE kind=1\n")
        self.assertEqual(parsed.unknown_machine_lines, ["#CG FUTURE kind=1"])

    def test_malformed_sample_is_recorded(self) -> None:
        parsed = cg_serial.parse_text("#CG SAMPLE seq=3 T1=1.0\n")
        self.assertEqual(len(parsed.malformed_lines), 1)
        self.assertEqual(parsed.samples, [])

    def test_capture_metadata_is_readable(self) -> None:
        text = "#CG CAPTURE started_at=2026-10-18T21:00:00Z port=COM4 baud=115200\n"
        text += boot_block(1)
        parsed = cg_serial.parse_text(text)
        self.assertEqual(parsed.captures[0]["port"], "COM4")


class SampleTests(unittest.TestCase):
    def test_nan_never_becomes_zero(self) -> None:
        parsed = cg_serial.parse_text(sample_line(1000, 1, "29.8125", "nan", "29.5625", "DEGRADED"))
        sample = parsed.samples[0]
        self.assertIsNone(sample.temp("T2"))
        self.assertFalse(sample.valid["T2"])
        self.assertEqual(sample.temp("T1"), 29.8125)

    def test_flag_wins_over_value(self) -> None:
        # A stale/duplicated value with t2=0 must stay missing.
        parsed = cg_serial.parse_text(sample_line(1000, 1, "29.0", "30.0", "29.0").replace("t2=1", "t2=0"))
        self.assertIsNone(parsed.samples[0].temp("T2"))

    def test_spare_validity_comes_from_the_value_token(self) -> None:
        # Grammar v1 has no tN flag for SPARE: nan is the only invalid marker.
        with_value = sample_line(1000, 1, "29.0", "29.5", "29.2").replace("SPARE=nan", "SPARE=28.5000")
        parsed = cg_serial.parse_text(with_value)
        self.assertEqual(parsed.samples[0].temp("SPARE"), 28.5)
        self.assertTrue(parsed.samples[0].valid["SPARE"])

        parsed_nan = cg_serial.parse_text(sample_line(1000, 1, "29.0", "29.5", "29.2"))
        self.assertIsNone(parsed_nan.samples[0].temp("SPARE"))
        self.assertFalse(parsed_nan.samples[0].valid["SPARE"])

    def test_csv_rows_keep_missing_empty(self) -> None:
        parsed = cg_serial.parse_text(sample_line(1000, 1, "29.8125", "nan", "29.5625", "DEGRADED"))
        row = cg_serial.sensor_csv_rows(parsed.samples)[0]
        self.assertIsNone(row["t2_c"])
        self.assertEqual(row["t2_valid"], 0)
        self.assertEqual(row["thermal"], "DEGRADED")


class StatisticsTests(unittest.TestCase):
    def test_mean_sd_and_pairwise_differences(self) -> None:
        text = ""
        values = [(10.0, 11.0, 10.5), (10.2, 11.2, 10.7), (10.4, 11.4, 10.9)]
        for index, (t1, t2, t3) in enumerate(values):
            text += sample_line(1000 * (index + 1), index + 1, f"{t1:.4f}", f"{t2:.4f}", f"{t3:.4f}")
        parsed = cg_serial.parse_text(text)
        stats = cg_serial.consistency_stats(parsed.samples)

        self.assertEqual(stats["T1"]["n_valid"], 3)
        self.assertAlmostEqual(stats["T1"]["mean_c"], 10.2, places=6)
        self.assertAlmostEqual(stats["T1"]["sd_c"], 0.2, places=6)
        self.assertAlmostEqual(stats["T2"]["mean_c"], 11.2, places=6)
        self.assertAlmostEqual(stats["T3"]["range_c"], 0.4, places=6)

        diffs = cg_serial.pairwise_mean_differences(stats)
        # "T1-T2" means mean(T1) - mean(T2), the same convention as
        # sensor-consistency-summary.md (DS1 - DS2 = -0.332 there).
        self.assertAlmostEqual(diffs["T1-T2"], -1.0, places=6)
        self.assertAlmostEqual(diffs["T2-T3"], 0.5, places=6)
        self.assertAlmostEqual(cg_serial.max_disagreement(stats), 1.0, places=6)

    def test_pairwise_sign_matches_the_dossier_convention(self) -> None:
        stats = {
            "T1": {"mean_c": 29.882},
            "T2": {"mean_c": 30.214},
            "T3": {"mean_c": 29.611},
        }
        diffs = cg_serial.pairwise_mean_differences(stats)
        self.assertAlmostEqual(diffs["T1-T2"], -0.332, places=3)
        self.assertAlmostEqual(diffs["T2-T3"], 0.603, places=3)

    def test_invalid_samples_are_excluded_but_counted(self) -> None:
        text = sample_line(1000, 1, "10.0", "11.0", "10.5")
        text += sample_line(2000, 2, "10.2", "nan", "10.7", "DEGRADED")
        parsed = cg_serial.parse_text(text)
        stats = cg_serial.consistency_stats(parsed.samples)
        self.assertEqual(stats["T2"]["n_valid"], 1)
        self.assertEqual(stats["T2"]["n_total"], 2)
        # One observation has no spread: sd is n/a, never a fake 0.0.
        self.assertIsNone(stats["T2"]["sd_c"])

    def test_effective_rate_uses_real_uptime(self) -> None:
        text = ""
        for index in range(11):
            text += sample_line(index * 1000, index + 1, "10.0", "11.0", "10.5")
        parsed = cg_serial.parse_text(text)
        duration_s, rate_hz = cg_serial.effective_rate(parsed.samples)
        self.assertAlmostEqual(duration_s, 10.0, places=6)
        self.assertAlmostEqual(rate_hz, 1.0, places=6)

    def test_no_samples_gives_none_not_zero(self) -> None:
        stats = cg_serial.consistency_stats([])
        self.assertIsNone(stats["T1"]["mean_c"])
        self.assertIsNone(cg_serial.max_disagreement(stats))


class RebootIdentityTests(unittest.TestCase):
    def test_stable_identity_across_five_boots(self) -> None:
        parsed = cg_serial.parse_text("".join(boot_block(index) for index in range(1, 6)))
        report = cg_serial.verify_reboot_identity(parsed, min_boots=5)
        self.assertEqual(report["verdict"], "IDENTITY_STABLE")
        self.assertEqual(report["boots_observed"], 5)

    def test_insufficient_boots(self) -> None:
        parsed = cg_serial.parse_text("".join(boot_block(index) for index in range(1, 5)))
        report = cg_serial.verify_reboot_identity(parsed, min_boots=5)
        self.assertEqual(report["verdict"], "INSUFFICIENT_BOOTS")

    def test_rom_change_is_a_mismatch(self) -> None:
        first = boot_block(1)
        second = boot_block(2).replace(ROM_T2, "28AEBF2200000007")
        parsed = cg_serial.parse_text(first + second)
        report = cg_serial.verify_reboot_identity(parsed, min_boots=2)
        self.assertEqual(report["verdict"], "IDENTITY_MISMATCH")
        self.assertEqual(report["mismatches"][0]["role"], "T2")

    def test_missing_role_is_reported(self) -> None:
        text = boot_block(1) + boot_block(2).replace(
            f"#CG ROM role=T3 rom={ROM_T3} present=1 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING\n",
            f"#CG ROM role=T3 rom={ROM_T3} present=0 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING\n",
        )
        parsed = cg_serial.parse_text(text)
        report = cg_serial.verify_reboot_identity(parsed, min_boots=2)
        self.assertEqual(report["verdict"], "ROLE_MISSING")
        self.assertEqual(report["missing_boot_indices"], [1])

    def test_same_rom_for_two_roles_is_detected(self) -> None:
        text = boot_block(1).replace(ROM_T2, ROM_T1)
        parsed = cg_serial.parse_text(text)
        report = cg_serial.verify_reboot_identity(parsed, min_boots=1)
        self.assertEqual(report["verdict"], "IDENTITY_MISMATCH")
        self.assertTrue(report["duplicated_roms"])

    def test_duplicated_boot_blocks_are_not_five_reboots(self) -> None:
        parsed = cg_serial.parse_text(boot_block(1) * 5)
        report = cg_serial.verify_reboot_identity(parsed, min_boots=5)
        self.assertEqual(report["verdict"], "BOOT_METADATA_INVALID")
        codes = {item["code"] for item in report["boot_metadata_issues"]}
        self.assertIn("BOOT_ID_DUPLICATED", codes)
        self.assertIn("BOOT_COUNT_NOT_INCREASING", codes)

    def test_zero_boot_count_is_flagged(self) -> None:
        parsed = cg_serial.parse_text(boot_block(0))
        report = cg_serial.verify_reboot_identity(parsed, min_boots=1)
        self.assertEqual(report["verdict"], "BOOT_METADATA_INVALID")
        self.assertEqual(report["boot_metadata_issues"][0]["code"], "BOOT_COUNT_ZERO")

    def test_missing_boot_id_is_flagged(self) -> None:
        parsed = cg_serial.parse_text("#CG BOOT boot_count=7\n" + rom_block(0))
        report = cg_serial.verify_reboot_identity(parsed, min_boots=1)
        self.assertEqual(report["verdict"], "BOOT_METADATA_INVALID")
        self.assertEqual(report["boot_metadata_issues"][0]["code"], "BOOT_ID_MISSING")

    def test_reset_boot_counter_is_flagged(self) -> None:
        text = boot_block(1) + boot_block(2) + boot_block(3).replace("boot_count=3", "boot_count=1")
        parsed = cg_serial.parse_text(text)
        report = cg_serial.verify_reboot_identity(parsed, min_boots=3)
        self.assertEqual(report["verdict"], "BOOT_METADATA_INVALID")
        codes = [item["code"] for item in report["boot_metadata_issues"]]
        self.assertIn("BOOT_COUNT_NOT_INCREASING", codes)


class DoorTests(unittest.TestCase):
    def test_cycles_discarded_and_open_intervals(self) -> None:
        text = ""
        # two committed transitions: raw1 -> raw0 (open) -> raw1 (closed)
        text += "#CG DOOR_EDGE uptime_us=1000000 raw=0\n"
        text += "#CG DOOR_STATE uptime_ms=1050 raw=0 state=UNVERIFIED transitions=1 cycles=0 discarded=0\n"
        text += "#CG DOOR_EDGE uptime_us=3000000 raw=1\n"
        text += "#CG DOOR_EDGE uptime_us=3001000 raw=0\n"  # bounce, same commit window
        text += "#CG DOOR_EDGE uptime_us=3002000 raw=1\n"
        text += "#CG DOOR_STATE uptime_ms=3100 raw=1 state=UNVERIFIED transitions=2 cycles=1 discarded=1\n"
        parsed = cg_serial.parse_text(text)

        report = cg_serial.door_analysis(parsed, open_level=None)
        self.assertEqual(report["committed_transitions"], 2)
        self.assertEqual(report["committed_cycles"], 1)
        self.assertEqual(report["raw_edges"], 4)
        self.assertEqual(report["discarded_edges"], 2)
        self.assertTrue(report["bounce_observed"])
        self.assertEqual(report["semantic_mapping"], "UNVERIFIED")

        verified = cg_serial.door_analysis(parsed, open_level=0)
        self.assertEqual(verified["open_intervals_ms"], [3100 - 1050])
        rows = cg_serial.door_csv_rows(parsed, open_level=0)
        self.assertEqual([row["state"] for row in rows], ["OPEN", "CLOSED"])

    def test_unverified_rows_never_claim_open_or_closed(self) -> None:
        parsed = cg_serial.parse_text(
            "#CG DOOR_STATE uptime_ms=1000 raw=0 state=UNVERIFIED transitions=1 cycles=0 discarded=0\n"
        )
        rows = cg_serial.door_csv_rows(parsed, open_level=None)
        self.assertEqual(rows[0]["state"], "UNVERIFIED")

    def test_door_boot_indices_and_boot_filtering(self) -> None:
        text = "#CG BOOT boot_id=a0000001 boot_count=1\n"
        text += "#CG DOOR_STATE uptime_ms=1000 raw=0 state=UNVERIFIED transitions=1 cycles=0 discarded=0\n"
        text += "#CG BOOT boot_id=a0000002 boot_count=2\n"
        text += "#CG DOOR_STATE uptime_ms=2000 raw=1 state=UNVERIFIED transitions=1 cycles=0 discarded=0\n"
        parsed = cg_serial.parse_text(text)
        self.assertEqual(cg_serial.door_boot_indices(parsed), [0, 1])

        first = cg_serial.door_analysis(parsed, open_level=None, boot_index=0)
        self.assertEqual(first["committed_transitions"], 1)
        rows_second = cg_serial.door_csv_rows(parsed, open_level=None, boot_index=1)
        self.assertEqual([int(row["raw"]) for row in rows_second], [1])


if __name__ == "__main__":
    unittest.main()
