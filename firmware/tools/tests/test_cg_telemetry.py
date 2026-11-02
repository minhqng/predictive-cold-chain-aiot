"""Tests for the W04 telemetry schema and acquisition builders.

The telemetry lines here are *synthetic*: they mirror the exact grammar of
``firmware/main/cg_telemetry.c`` so the parser is exercised offline. They
are never evidence and never written into evidence/A/W04/.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_build_telemetry  # noqa: E402
import cg_telemetry_schema as schema  # noqa: E402


def telem_line(
    uptime_ms: int = 12345,
    run_id: str = "UNSET",
    phase: str = "TEC_OFF",
    t_inside: str = "24.5625",
    t_inside_status: str = "OK",
    voltage: str = "12.0400",
    voltage_status: str = "OK",
    door: str = "nan",
    door_status: str = "UNVERIFIED",
    fault_code: str = "0x00000000",
    elapsed: int | None = None,
) -> str:
    elapsed = uptime_ms if elapsed is None else elapsed
    return (
        "#CG TELEM schema=1 timestamp_utc=UNAVAILABLE timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK "
        f"uptime_ms={uptime_ms} elapsed_ms={elapsed} run_elapsed_ms=0 run_id={run_id} "
        "boot_id=boot0001 boot_count=1 firmware_version=cg-w04-0.1.0 hardware_config_id=CG-HW-001 "
        f"test_phase={phase} "
        f"t_inside_c={t_inside} t_inside_status={t_inside_status} t_inside_src=T2 "
        "t_cold_side_c=nan t_cold_side_status=NOT_ASSIGNED "
        "t_hot_side_c=nan t_hot_side_status=NOT_ASSIGNED "
        "t_ambient_c=nan t_ambient_status=NOT_ASSIGNED "
        "relative_humidity_pct=nan relative_humidity_status=SENSOR_NOT_PRESENT "
        f"door_open={door} door_status={door_status} door_raw=0 "
        f"voltage_v={voltage} voltage_status={voltage_status} "
        "current_a=0.0000 current_status=OK power_w=0.0000 power_status=OK "
        "pwm_duty=0 fan_command=OFF fan_status=NOT_COMMANDABLE output_stage=DISABLED "
        f"tec_state=OFF fault_code={fault_code} fault_reason=NONE "
        "sensor_validity=VALID power_validity=OK "
        "raw_t1_c=24.4375 raw_t1_status=OK raw_t2_c=24.5625 raw_t2_status=OK "
        "raw_t3_c=nan raw_t3_status=NO_DATA raw_spare_c=nan raw_spare_status=NO_DATA"
    )


class ParseLineTests(unittest.TestCase):
    def test_valid_line_is_typed(self) -> None:
        record = schema.parse_line(telem_line(), line_index=7)
        self.assertEqual(record.line_index, 7)
        self.assertEqual(record.value("elapsed_ms"), 12345)
        self.assertAlmostEqual(record.value("t_inside_c"), 24.5625)
        self.assertAlmostEqual(record.value("voltage_v"), 12.04)
        self.assertEqual(record.value("fault_code"), 0)
        self.assertEqual(record.value("timestamp_utc"), "UNAVAILABLE")
        self.assertIsNone(record.value("t_hot_side_c"))
        self.assertIsNone(record.value("door_open"))
        self.assertTrue(record.usable("t_inside_c"))
        self.assertFalse(record.usable("t_hot_side_c"))

    def test_missing_required_field_is_rejected(self) -> None:
        line = telem_line().replace(" t_ambient_c=nan", "")
        with self.assertRaises(schema.TelemetryError) as ctx:
            schema.parse_line(line)
        self.assertIn("t_ambient_c", str(ctx.exception))

    def test_missing_status_companion_is_rejected(self) -> None:
        line = telem_line().replace(" t_inside_status=OK", "")
        with self.assertRaises(schema.TelemetryError) as ctx:
            schema.parse_line(line)
        self.assertIn("t_inside_status", str(ctx.exception))

    def test_unsupported_schema_is_rejected(self) -> None:
        """Schema 2 is now the current line format, so an unknown future schema
        is what has to be refused. A schema-1 body relabelled as 2 is also
        refused, because it cannot carry the W05 identity fields."""
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(telem_line().replace("schema=1", "schema=9"))
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(telem_line().replace("schema=1", "schema=2"))

    def test_truncated_line_is_rejected_not_repaired(self) -> None:
        line = telem_line()
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(line[: len(line) // 2])
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(line + " t_hot_side_c=")

    def test_non_telemetry_line_is_rejected(self) -> None:
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line("#CG SAMPLE index=1 seq=1")

    def test_unknown_future_field_is_retained(self) -> None:
        line = telem_line() + " future_key=future_value"
        record = schema.parse_line(line)
        self.assertEqual(record.raw_fields["future_key"], "future_value")

    def test_nan_never_becomes_zero(self) -> None:
        record = schema.parse_line(telem_line())
        for name in ("t_hot_side_c", "t_ambient_c", "relative_humidity_pct"):
            self.assertIsNone(record.value(name), name)

    def test_fabricated_timestamp_is_rejected(self) -> None:
        line = telem_line().replace("timestamp_utc=UNAVAILABLE", "timestamp_utc=2026-10-29T00:00:00Z")
        with self.assertRaises(schema.TelemetryError) as ctx:
            schema.parse_line(line)
        self.assertIn("timestamp_utc", str(ctx.exception))

    def test_wrong_timestamp_source_is_rejected(self) -> None:
        line = telem_line().replace(
            "timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK", "timestamp_utc_source=HOST_CLOCK"
        )
        with self.assertRaises(schema.TelemetryError) as ctx:
            schema.parse_line(line)
        self.assertIn("timestamp_utc_source", str(ctx.exception))

    def test_non_finite_number_is_rejected(self) -> None:
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(telem_line(voltage="1e400"))


class ReadCaptureTests(unittest.TestCase):
    def test_counts_ignored_and_rejected_with_indexes(self) -> None:
        lines = [
            "ESP-ROM:esp32s3-20210327",
            telem_line(uptime_ms=1000),
            "#CG BOOT boot_id=boot0001 boot_count=1",
            telem_line(uptime_ms=2000).replace("schema=1", "schema=9"),
            telem_line(uptime_ms=3000),
        ]
        records, report = schema.read_capture(lines)
        self.assertEqual(len(records), 2)
        self.assertEqual([r.line_index for r in records], [2, 5])
        self.assertEqual(report["ignored"], 2)
        self.assertEqual(len(report["rejected"]), 1)
        self.assertEqual(report["rejected"][0]["line_index"], 4)


class BuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_main(self, lines: list[str], ml: bool = True) -> tuple[int, pathlib.Path, pathlib.Path, pathlib.Path]:
        log = self.tmp / "capture.log"
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        jsonl = self.tmp / "out.jsonl"
        csv_path = self.tmp / "out.csv"
        ml_path = self.tmp / "ml.csv"
        argv = [str(log), "--jsonl", str(jsonl), "--csv", str(csv_path)]
        if ml:
            argv += ["--ml-out", str(ml_path)]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = cg_build_telemetry.main(argv)
        self.stdout = out.getvalue()
        return code, jsonl, csv_path, ml_path

    def test_clean_capture_builds_three_views(self) -> None:
        code, jsonl, csv_path, ml_path = self.run_main(
            ["boot noise", telem_line(uptime_ms=1000), telem_line(uptime_ms=2000)],
        )
        self.assertEqual(code, 0)
        raw = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(raw), 2)
        self.assertEqual(raw[0]["raw"], telem_line(uptime_ms=1000))
        self.assertEqual(raw[0]["raw_fields"]["schema"], "1")
        self.assertEqual(raw[1]["fields"]["elapsed_ms"], 2000)

        header, *rows = list(csv.reader(csv_path.read_text(encoding="utf-8").splitlines()))
        self.assertIn("timestamp_utc", header)
        self.assertIn("t_cold_side_status", header)
        first = dict(zip(header, rows[0]))
        self.assertEqual(first["timestamp_utc"], "UNAVAILABLE")
        self.assertEqual(first["t_cold_side_c"], "")
        self.assertEqual(first["t_inside_c"], "24.5625")
        self.assertEqual(first["fault_code"], "0x00000000")

        ml_header, *ml_rows = list(csv.reader(ml_path.read_text(encoding="utf-8").splitlines()))
        ml_first = dict(zip(ml_header, ml_rows[0]))
        self.assertEqual(ml_first["t_inside_c"], "24.5625")
        self.assertEqual(ml_first["t_ambient_c"], "")
        self.assertEqual(ml_first["fan_on"], "0")
        self.assertEqual(ml_first["test_phase"], "TEC_OFF")
        self.assertNotIn("timestamp_utc", ml_header)

    def test_contradictory_value_is_masked_in_ml_only(self) -> None:
        line = telem_line(voltage="12.0400", voltage_status="STALE")
        code, _jsonl, csv_path, ml_path = self.run_main([line])
        self.assertEqual(code, 0)
        header, row = list(csv.reader(csv_path.read_text(encoding="utf-8").splitlines()))
        flat = dict(zip(header, row))
        self.assertEqual(flat["voltage_v"], "12.0400")  # raw view keeps the token
        self.assertEqual(flat["voltage_status"], "STALE")

        ml_header, ml_row = list(csv.reader(ml_path.read_text(encoding="utf-8").splitlines()))
        ml = dict(zip(ml_header, ml_row))
        self.assertEqual(ml["voltage_v"], "")  # ML view refuses a non-OK value
        self.assertEqual(ml["power_validity"], "OK")

    def test_rejected_line_fails_but_valid_records_are_written(self) -> None:
        code, jsonl, csv_path, _ml = self.run_main(
            [telem_line(uptime_ms=1000), telem_line(uptime_ms=2000).replace("schema=1", "schema=3")]
        )
        self.assertEqual(code, 1)
        self.assertIn("NOT CLEAN", self.stdout)
        self.assertEqual(len(jsonl.read_text(encoding="utf-8").splitlines()), 1)
        self.assertIn("TELEMETRY ACQUISITION", self.stdout)

    def test_capture_without_telemetry_exits_nonzero(self) -> None:
        code, jsonl, _csv, _ml = self.run_main(["ESP-ROM:esp32s3", "#CG BOOT boot_id=boot0001 boot_count=1"])
        self.assertEqual(code, 1)
        self.assertFalse(jsonl.exists())

    def test_run_id_and_phase_are_preserved(self) -> None:
        line = telem_line(run_id="g4-run-01", phase="G4")
        code, _jsonl, _csv, ml_path = self.run_main([line])
        self.assertEqual(code, 0)
        ml_header, ml_row = ml_path.read_text(encoding="utf-8").splitlines()
        ml = dict(zip(ml_header.split(","), ml_row.split(",")))
        self.assertEqual(ml["run_id"], "g4-run-01")
        self.assertEqual(ml["test_phase"], "G4")


if __name__ == "__main__":
    unittest.main()
