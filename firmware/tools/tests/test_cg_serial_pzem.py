"""Tests for the W03 PZEM grammar and analysis in cg_serial.py.

Fixtures are synthetic logs (see tests/cg_pzem_fixtures.py); they exercise
the parser and the statistics only and are never evidence. Grammar v1
captures must keep parsing: those tests pin the v1 -> v2 compatibility
promise.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_pzem_fixtures as fixtures  # noqa: E402
import cg_serial  # noqa: E402


class GrammarTests(unittest.TestCase):
    def test_grammar_version_is_2(self) -> None:
        self.assertEqual(cg_serial.GRAMMAR_VERSION, 2)

    def test_v1_capture_still_parses_and_pzem_lists_stay_empty(self) -> None:
        text = "#CG LOG v=1 fw=cg-w02-0.1.0 hw=CG-HW-001\n"
        text += "#CG SAMPLE uptime_ms=1000 seq=1 T1=29.0 T2=29.5 T3=29.2 SPARE=nan t1=1 t2=1 t3=1 thermal=VALID door_raw=1 door=UNVERIFIED\n"
        parsed = cg_serial.parse_text(text)
        self.assertEqual(len(parsed.samples), 1)
        self.assertEqual(parsed.pzem_configs, [])
        self.assertEqual(parsed.pzem_range_lines, [])
        self.assertEqual(parsed.pzem_samples, [])


class PzemConfigTests(unittest.TestCase):
    def test_config_line(self) -> None:
        parsed = cg_serial.parse_text(fixtures.cfg_line() + fixtures.poll_ok_line(1000, 1))
        config = parsed.pzem_configs[0]
        self.assertEqual(config.slave, 1)
        self.assertEqual(config.baud, 9600)
        self.assertEqual(config.framing, "8N1")
        self.assertEqual(config.direction, "AUTO")
        self.assertTrue(config.read_only)

    def test_config_without_slave_is_malformed(self) -> None:
        parsed = cg_serial.parse_text("#CG PZEM_CFG baud=9600 framing=8N1\n")
        self.assertEqual(parsed.pzem_configs, [])
        self.assertEqual(len(parsed.malformed_lines), 1)


class PzemSampleTests(unittest.TestCase):
    def test_ok_line_decodes_values(self) -> None:
        parsed = cg_serial.parse_text(
            fixtures.poll_ok_line(1000, 1, voltage_v=12.34, current_a=0.05, power_w=12.3, energy_wh=456)
        )
        sample = parsed.pzem_samples[0]
        self.assertEqual(sample.status, "OK")
        self.assertAlmostEqual(sample.voltage_v, 12.34)
        self.assertAlmostEqual(sample.current_a, 0.05)
        self.assertAlmostEqual(sample.power_w, 12.3)
        self.assertAlmostEqual(sample.energy_wh, 456.0)
        self.assertTrue(sample.values_valid)
        self.assertTrue(sample.crc_ok)
        self.assertEqual(sample.attempts, 1)

    def test_failed_line_keeps_nan_as_none(self) -> None:
        parsed = cg_serial.parse_text(fixtures.poll_fail_line(2000, 2, status="TIMEOUT"))
        sample = parsed.pzem_samples[0]
        self.assertEqual(sample.status, "TIMEOUT")
        self.assertIsNone(sample.voltage_v)
        self.assertIsNone(sample.current_a)
        self.assertIsNone(sample.power_w)
        self.assertIsNone(sample.energy_wh)
        self.assertFalse(sample.values_valid)

    def test_number_on_non_ok_line_never_counts_as_valid(self) -> None:
        # Defensive: even if a non-OK line carried numbers, they cannot
        # enter statistics - a contradiction is not a measurement.
        text = fixtures.poll_fail_line(2000, 2, status="CRC_ERR").replace(
            "v=nan i=nan p=nan e=nan", "v=12.34 i=0.05 p=12.3 e=456"
        )
        parsed = cg_serial.parse_text(text)
        sample = parsed.pzem_samples[0]
        self.assertFalse(sample.values_valid)
        self.assertIsNotNone(sample.voltage_v)  # parsed, but not usable

    def test_malformed_poll_line_is_recorded(self) -> None:
        parsed = cg_serial.parse_text("#CG PZEM seq=1 status=OK\n")
        self.assertEqual(parsed.pzem_samples, [])
        self.assertEqual(len(parsed.malformed_lines), 1)

    def test_boot_grouping(self) -> None:
        text = (
            "#CG BOOT boot_id=boot0001 boot_count=1\n"
            + fixtures.poll_ok_line(1000, 1)
            + "#CG BOOT boot_id=boot0002 boot_count=2\n"
            + fixtures.poll_ok_line(1000, 1)
        )
        parsed = cg_serial.parse_text(text)
        self.assertEqual([sample.boot_index for sample in parsed.pzem_samples], [0, 1])
        self.assertEqual(cg_serial.pzem_boot_indices(parsed), [0, 1])
        self.assertEqual(len(cg_serial.pzem_session(parsed, 1)), 1)


class PzemRangeTests(unittest.TestCase):
    def test_range_line(self) -> None:
        parsed = cg_serial.parse_text(fixtures.range_log_line(1000, value=0x0001))
        line = parsed.pzem_range_lines[0]
        self.assertEqual(line.status, "OK")
        self.assertEqual(line.raw_value, 1)
        self.assertEqual(line.value_hex, "0x0001")
        self.assertEqual(line.profile, "50A")
        self.assertTrue(line.crc_ok)

    def test_range_nan_token_stays_none(self) -> None:
        text = fixtures.range_log_line(1000).replace("value=0x0001", "value=nan").replace(
            "profile=50A", "profile=nan"
        )
        parsed = cg_serial.parse_text(text)
        line = parsed.pzem_range_lines[0]
        self.assertIsNone(line.raw_value)
        self.assertIsNone(line.value_hex)
        self.assertEqual(line.profile, "nan")


class LinkStatsTests(unittest.TestCase):
    def test_success_and_error_rates(self) -> None:
        text = ""
        for index in range(9):
            text += fixtures.poll_ok_line(1000 + index * 1000, index + 1)
        text += fixtures.poll_fail_line(10000, 10, status="TIMEOUT")
        parsed = cg_serial.parse_text(text)
        link = cg_serial.pzem_link_stats(parsed.pzem_samples)
        self.assertEqual(link["n_total"], 10)
        self.assertEqual(link["n_ok"], 9)
        self.assertEqual(link["n_error"], 1)
        self.assertAlmostEqual(link["success_rate"], 0.9)
        self.assertAlmostEqual(link["error_rate"], 0.1)
        self.assertEqual(link["timeout_count"], 1)
        self.assertEqual(link["crc_error_count"], 0)
        self.assertEqual(link["status_counts"], {"OK": 9, "TIMEOUT": 1})
        self.assertEqual(link["crc_ok_count"], 9)

    def test_interval_profile_and_gaps(self) -> None:
        text = ""
        covers = [0, 1000, 2000, 3000, 9000, 10000]  # 6 s jump between 3000 and 9000
        for index, uptime in enumerate(covers):
            text += fixtures.poll_ok_line(uptime, index + 1)
        parsed = cg_serial.parse_text(text)
        link = cg_serial.pzem_link_stats(parsed.pzem_samples)
        self.assertEqual(link["interval_ms"]["median"], 1000.0)
        self.assertEqual(link["interval_ms"]["max"], 6000)
        self.assertEqual(len(link["gaps"]), 1)
        self.assertEqual(link["gaps"][0]["gap_ms"], 6000)
        self.assertEqual(link["gaps"][0]["after_uptime_ms"], 3000)
        self.assertEqual(link["gap_total_ms"], 6000)
        self.assertEqual(link["duration_s"], 10.0)

    def test_empty_stats_are_none_not_zero(self) -> None:
        link = cg_serial.pzem_link_stats([])
        self.assertEqual(link["n_total"], 0)
        self.assertIsNone(link["success_rate"])
        self.assertIsNone(link["interval_ms"]["median"])


class PowerStatsTests(unittest.TestCase):
    def test_mean_sd_min_max_spread(self) -> None:
        voltages = [12.34, 12.35, 12.36]
        text = ""
        for index, voltage in enumerate(voltages):
            text += fixtures.poll_ok_line(1000 * (index + 1), index + 1, voltage_v=voltage)
        parsed = cg_serial.parse_text(text)
        stats = cg_serial.pzem_power_stats(parsed.pzem_samples)
        voltage = stats["voltage_v"]
        self.assertEqual(voltage["n_valid"], 3)
        self.assertAlmostEqual(voltage["mean"], 12.35, places=6)
        self.assertAlmostEqual(voltage["sd"], 0.01, places=6)
        self.assertAlmostEqual(voltage["min"], 12.34, places=6)
        self.assertAlmostEqual(voltage["max"], 12.36, places=6)
        self.assertAlmostEqual(voltage["spread"], 0.02, places=6)

    def test_failed_samples_do_not_enter_the_statistics(self) -> None:
        text = fixtures.poll_ok_line(1000, 1, voltage_v=12.34)
        text += fixtures.poll_fail_line(2000, 2)
        parsed = cg_serial.parse_text(text)
        stats = cg_serial.pzem_power_stats(parsed.pzem_samples)
        self.assertEqual(stats["voltage_v"]["n_valid"], 1)
        self.assertEqual(stats["voltage_v"]["n_total"], 2)
        self.assertAlmostEqual(stats["voltage_v"]["mean"], 12.34, places=6)


class CsvRowTests(unittest.TestCase):
    def test_failed_poll_rows_keep_missing_empty(self) -> None:
        text = fixtures.poll_ok_line(1000, 1, voltage_v=12.34)
        text += fixtures.poll_fail_line(2000, 2, status="CRC_ERR", crc_ok=0)
        parsed = cg_serial.parse_text(text)
        rows = cg_serial.pzem_csv_rows(parsed.pzem_samples)
        self.assertAlmostEqual(rows[0]["voltage_v"], 12.34)
        self.assertEqual(rows[0]["crc_ok"], 1)
        self.assertIsNone(rows[1]["voltage_v"])
        self.assertEqual(rows[1]["status"], "CRC_ERR")
        self.assertEqual(rows[1]["crc_ok"], 0)
        self.assertEqual(rows[1]["attempts"], 2)


if __name__ == "__main__":
    unittest.main()
