"""CLI tests for the W03 PZEM tools (readback + TEC-OFF CSV builder).

Everything here runs on synthetic captures in a temporary directory; no
hardware, no serial port and no evidence file is touched.
"""

from __future__ import annotations

import contextlib
import csv
import io
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_build_pzem_off_csv  # noqa: E402
import cg_modbus  # noqa: E402
import cg_pzem_fixtures as fixtures  # noqa: E402
import cg_pzem_readback  # noqa: E402


def run_capture(main, capture: str, *args: str) -> tuple[int, str]:
    """Runs a tool's main() on a temporary capture and captures its output."""

    with tempfile.TemporaryDirectory() as tmp:
        log_path = pathlib.Path(tmp) / "capture.log"
        log_path.write_text(capture, encoding="utf-8")
        out_path = pathlib.Path(tmp) / "out.csv"
        rel_args = [str(log_path)] + [arg.replace("{out}", str(out_path)) for arg in args]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = main(rel_args)
        return code, buffer.getvalue()


def run_readback(capture: str, *args: str) -> tuple[int, str]:
    return run_capture(cg_pzem_readback.main, capture, *args)


def run_builder(capture: str, *args: str) -> tuple[int, str]:
    return run_capture(cg_build_pzem_off_csv.main, capture, *args)


class ReadbackTests(unittest.TestCase):
    def test_happy_path_decodes_and_cross_checks(self) -> None:
        capture = fixtures.cfg_line() + fixtures.range_log_line(1234, value=0x0001)
        code, output = run_readback(capture)
        self.assertEqual(code, 0, output)
        self.assertIn("PZEM READBACK: DECODED", output)
        self.assertIn("value firmware/host   : 0x0001 / 0x0001", output)
        self.assertIn("profile firmware/host : 50A / 50A", output)

    def test_prefixed_range_frame_decodes(self) -> None:
        for prefix in (b"\xaa" * 7, cg_modbus.build_read_range(1)):
            capture = fixtures.cfg_line() + fixtures.range_log_line(
                1234, value=0x0001, prefix=prefix
            )
            code, output = run_readback(capture)
            self.assertEqual(code, 0, output)
            self.assertIn("PZEM READBACK: DECODED", output)
            self.assertIn("frame host", output)

    def test_prefixed_exception_is_not_decoded_as_ok(self) -> None:
        frame = cg_modbus.append_crc(bytes((1, 0x83, 0x02)))
        prefix = cg_modbus.build_read_range(1)
        capture = fixtures.cfg_line() + (
            "#CG PZEM_RANGE uptime_ms=1234 status=EXCEPTION value=nan profile=nan "
            f"crc_ok=1 exc=2 tx={fixtures.hexs(cg_modbus.build_read_range(1))} "
            f"rx={fixtures.hexs(prefix + frame)}\n"
        )
        code, output = run_readback(capture)
        self.assertEqual(code, 1, output)
        self.assertIn("NOT DECODED", output)
        self.assertNotIn("PZEM READBACK: DECODED", output)

    def test_exception_code_disagreement_fails(self) -> None:
        frame = cg_modbus.append_crc(bytes((1, 0x83, 0x02)))
        prefix = cg_modbus.build_read_range(1)
        capture = fixtures.cfg_line() + (
            "#CG PZEM_RANGE uptime_ms=1234 status=EXCEPTION value=nan profile=nan "
            f"crc_ok=1 exc=3 tx={fixtures.hexs(cg_modbus.build_read_range(1))} "
            f"rx={fixtures.hexs(prefix + frame)}\n"
        )
        code, output = run_readback(capture)
        self.assertEqual(code, 1, output)
        self.assertIn("exception disagreement", output)

    def test_expected_profile_mismatch_fails(self) -> None:
        capture = fixtures.cfg_line() + fixtures.range_log_line(1234, value=0x0000)
        code, output = run_readback(capture, "--expect-profile", "50A")
        self.assertEqual(code, 1, output)
        self.assertIn("PROFILE MISMATCH", output)

    def test_expected_profile_match_passes(self) -> None:
        capture = fixtures.cfg_line() + fixtures.range_log_line(1234, value=0x0000)
        code, output = run_readback(capture, "--expect-profile", "100A")
        self.assertEqual(code, 0, output)

    def test_crc_disagreement_fails(self) -> None:
        # Firmware claims crc_ok=1 but the captured rx bytes do not check out.
        capture = fixtures.cfg_line() + fixtures.range_log_line(
            1234, value=0x0001, damaged_rx=True
        ).replace("crc_ok=0", "crc_ok=1")
        code, output = run_readback(capture)
        self.assertEqual(code, 1, output)
        self.assertIn("CRC disagreement", output)

    def test_missing_config_fails(self) -> None:
        capture = fixtures.range_log_line(1234)
        code, output = run_readback(capture)
        self.assertEqual(code, 1, output)
        self.assertIn("MISSING", output)

    def test_read_only_zero_fails(self) -> None:
        capture = fixtures.cfg_line(read_only=0) + fixtures.range_log_line(1234)
        code, output = run_readback(capture)
        self.assertEqual(code, 1, output)
        self.assertIn("read_only", output)

    def test_multi_boot_is_refused_unless_selected(self) -> None:
        capture = (
            "#CG BOOT boot_id=boot0001 boot_count=1\n"
            + fixtures.cfg_line()
            + fixtures.range_log_line(1000)
            + "#CG BOOT boot_id=boot0002 boot_count=2\n"
            + fixtures.range_log_line(1000, value=0x0001)
        )
        code, output = run_readback(capture)
        self.assertEqual(code, 1, output)
        self.assertIn("multiple boots", output)
        code, output = run_readback(capture, "--boot", "0")
        self.assertEqual(code, 0, output)

    def test_no_range_lines_is_reported_as_pending(self) -> None:
        code, output = run_readback(fixtures.cfg_line() + fixtures.poll_ok_line(1000, 1))
        self.assertEqual(code, 1)
        self.assertIn("PENDING", output)

    def test_json_output(self) -> None:
        capture = fixtures.cfg_line() + fixtures.range_log_line(1234)
        with tempfile.TemporaryDirectory() as tmp:
            log_path = pathlib.Path(tmp) / "capture.log"
            log_path.write_text(capture, encoding="utf-8")
            json_path = pathlib.Path(tmp) / "readback.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cg_pzem_readback.main(
                    [str(log_path), "--json", str(json_path)]
                )
            self.assertEqual(code, 0, stdout.getvalue())
            payload = json_path.read_text(encoding="utf-8")
            self.assertIn('"host_profile": "50A"', payload)


class PzemOffBuilderTests(unittest.TestCase):
    @staticmethod
    def window_capture(n_samples: int = 601, step_ms: int = 1000, ok: bool = True) -> str:
        text = fixtures.cfg_line()
        for index in range(n_samples):
            uptime = index * step_ms
            if ok or index % 10:
                text += fixtures.poll_ok_line(uptime, index + 1, voltage_v=12.34 + index * 0.001)
            else:
                text += fixtures.poll_fail_line(uptime, index + 1)
        return text

    def test_usable_window(self) -> None:
        capture = self.window_capture()
        code, output = run_builder(
            capture, "--out", "{out}", "--tec-off-confirmed"
        )
        self.assertEqual(code, 0, output)
        self.assertIn("PZEM OFF WINDOW: USABLE", output)
        self.assertIn("success rate      : 601/601 = 1.0000", output)
        self.assertIn("gaps              : none", output)

    def test_requires_operator_confirmation_of_tec_off(self) -> None:
        capture = self.window_capture()
        code, output = run_builder(capture, "--out", "{out}")
        self.assertEqual(code, 1, output)
        self.assertIn("TEC off was not confirmed", output)

    def test_short_window_is_not_usable(self) -> None:
        capture = self.window_capture(n_samples=301)
        code, output = run_builder(capture, "--out", "{out}", "--tec-off-confirmed")
        self.assertEqual(code, 1, output)
        self.assertIn("NOT USABLE", output)
        self.assertIn("duration 300.0 s < 600.0 s", output)

    def test_low_success_fraction_is_not_usable(self) -> None:
        capture = fixtures.cfg_line()
        for index in range(601):
            uptime = index * 1000
            if index % 10 == 0:
                capture += fixtures.poll_ok_line(uptime, index + 1)
            else:
                capture += fixtures.poll_fail_line(uptime, index + 1)
        code, output = run_builder(capture, "--out", "{out}", "--tec-off-confirmed")
        self.assertEqual(code, 1, output)
        self.assertIn("valid-sample fraction", output)

    def test_multi_boot_is_refused_unless_selected(self) -> None:
        capture = (
            "#CG BOOT boot_id=boot0001 boot_count=1\n"
            + self.window_capture(n_samples=2)
            + "#CG BOOT boot_id=boot0002 boot_count=2\n"
            + self.window_capture(n_samples=2)
        )
        code, output = run_builder(capture, "--out", "{out}", "--tec-off-confirmed")
        self.assertEqual(code, 1, output)
        self.assertIn("multiple boots", output)
        code, output = run_builder(
            capture, "--out", "{out}", "--tec-off-confirmed", "--boot", "0"
        )
        # Only 1 s of window inside boot 0 - refused, but not for multi-boot.
        self.assertEqual(code, 1, output)
        self.assertIn("NOT USABLE", output)

    def test_csv_has_empty_cells_for_failed_polls(self) -> None:
        capture = fixtures.cfg_line()
        capture += fixtures.poll_ok_line(0, 1, voltage_v=12.34)
        capture += fixtures.poll_fail_line(1000, 2, status="TIMEOUT")
        with tempfile.TemporaryDirectory() as tmp:
            log_path = pathlib.Path(tmp) / "capture.log"
            log_path.write_text(capture, encoding="utf-8")
            out_path = pathlib.Path(tmp) / "pzem-off.csv"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cg_build_pzem_off_csv.main([str(log_path), "--out", str(out_path)])
            with out_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(list(rows[0].keys()), cg_build_pzem_off_csv.CSV_COLUMNS)
            self.assertEqual(rows[0]["voltage_v"], "12.34")
            self.assertEqual(rows[0]["status"], "OK")
            self.assertEqual(rows[1]["voltage_v"], "")
            self.assertEqual(rows[1]["status"], "TIMEOUT")
            self.assertEqual(rows[1]["attempts"], "2")

    def test_missing_config_is_not_usable(self) -> None:
        capture = ""
        for index in range(601):
            capture += fixtures.poll_ok_line(index * 1000, index + 1)
        code, output = run_builder(capture, "--out", "{out}", "--tec-off-confirmed")
        self.assertEqual(code, 1, output)
        self.assertIn("no #CG PZEM_CFG", output)

    def test_json_summary_is_written(self) -> None:
        capture = self.window_capture()
        with tempfile.TemporaryDirectory() as tmp:
            log_path = pathlib.Path(tmp) / "capture.log"
            log_path.write_text(capture, encoding="utf-8")
            out_path = pathlib.Path(tmp) / "pzem-off.csv"
            json_path = pathlib.Path(tmp) / "summary.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cg_build_pzem_off_csv.main(
                    [
                        str(log_path),
                        "--out",
                        str(out_path),
                        "--tec-off-confirmed",
                        "--json",
                        str(json_path),
                    ]
                )
            self.assertEqual(code, 0, stdout.getvalue())
            text = json_path.read_text(encoding="utf-8")
            self.assertIn('"status_counts": {', text)
            self.assertIn('"tec_off_confirmed": true', text)


if __name__ == "__main__":
    unittest.main()
