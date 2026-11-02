"""Tests for the W05 telemetry schema, the builder handoff, and back-compat.

Two things are proved here that a synthetic fixture alone cannot:

1. **Schema 2 is what the firmware emits.** The line is taken from the host C
   harness output (``cg_w05_harness.c`` rendering a real frame), not typed by
   hand, so the parser is tested against the formatter's own bytes.
2. **Schema 1 still parses.** The W04 lines are read from a committed capture in
   ``evidence/A/W04/g1/``, so raising the serial schema is checked against the
   bytes that already exist in the repository, not against an imitation.
"""

from __future__ import annotations

import contextlib
import csv
import io
import pathlib
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
MAIN = TOOLS.parent / "main"
TESTS = pathlib.Path(__file__).resolve().parent
REPO = TOOLS.parent.parent

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TESTS))

import cg_build_telemetry  # noqa: E402
import cg_telemetry_schema as schema  # noqa: E402
from test_cg_tec_state_machine import find_gcc, find_vcvars  # noqa: E402
from test_cg_w05_harness import SOURCES, build_with_gcc, build_with_msvc  # noqa: E402
from test_cg_w05_harness import HARNESS  # noqa: E402

W04_CAPTURE = REPO / "evidence" / "A" / "W04" / "g1" / "40-g1-boot-60s.log"

_FIXTURE_LINE: str | None = None
_FIXTURE_LOCK = object()


def harness_fixture_line() -> str:
    """Render one frame with the real C formatter and return the emitted line."""
    global _FIXTURE_LINE
    if _FIXTURE_LINE is not None:
        return _FIXTURE_LINE
    with tempfile.TemporaryDirectory(prefix="cg-w05-fixture-") as tmp:
        workdir = pathlib.Path(tmp)
        vcvars = find_vcvars()
        if vcvars is not None:
            exe = build_with_msvc(vcvars, workdir)
        else:
            cc = find_gcc()
            if cc is None:
                raise unittest.SkipTest("no host C compiler (MSVC or cc/gcc) found")
            exe = build_with_gcc(cc, workdir)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
        for line in result.stdout.splitlines():
            if line.startswith("FIXTURE_V2 "):
                _FIXTURE_LINE = line[len("FIXTURE_V2 "):]
    if _FIXTURE_LINE is None:
        raise AssertionError(f"harness printed no fixture line:\n{result.stdout}\n{result.stderr}")
    return _FIXTURE_LINE


def v2_line(**overrides: object) -> str:
    line = harness_fixture_line()
    for name, value in overrides.items():
        token = f" {name}="
        start = line.index(token) + 1  # the leading space keeps the match on the whole key
        end = line.index(" ", start)
        line = line[:start] + f"{name}={value}" + line[end:]
    return line


class FormatterFixtureTests(unittest.TestCase):
    def test_real_frame_parses_as_schema_two(self) -> None:
        record = schema.parse_line(harness_fixture_line())
        self.assertEqual(record.value("schema"), schema.SCHEMA_VERSION)
        self.assertGreaterEqual(record.value("schema"), 2, "the fixture must be a W05-era frame")
        self.assertEqual(record.value("device_id"), "coldguard-001")
        self.assertEqual(record.value("calibration_id"), "UNRECORDED")
        self.assertGreaterEqual(record.value("seq"), 1)
        self.assertEqual(record.value("quality"), "UNKNOWN")
        self.assertEqual(record.value("door_quality"), "UNKNOWN")
        self.assertEqual(record.value("cooling_applied"), "OFF")

    def test_every_emitted_key_is_known_to_the_schema(self) -> None:
        """A field the parser does not know about is a handoff defect."""
        record = schema.parse_line(harness_fixture_line())
        known = set(schema.REQUIRED_FIELDS) | set(schema.REQUIRED_STATUS_FIELDS)
        known |= set(schema.W05_REQUIRED_FIELDS)
        known |= set(getattr(schema, "W06_REQUIRED_FIELDS", ()))
        known |= set(schema.INTEGER_FIELDS) | set(schema.FLOAT_FIELDS)
        known |= {
            # Vocabulary-only or descriptive fields the parser keeps as strings.
            "boot_count", "run_id", "firmware_version", "hardware_config_id",
            "test_phase", "pwm_duty", "fan_command", "fan_status", "output_stage",
            "tec_state", "fault_reason", "sensor_validity", "power_validity",
            "t_inside_src", "door_raw", "door_status", "elapsed_ms",
            "timestamp_utc", "timestamp_utc_source",
            "cooling_applied_source", "role_status", "rom_source",
            "raw_t1_c", "raw_t2_c", "raw_t3_c", "raw_spare_c",
            "raw_t1_status", "raw_t2_status", "raw_t3_status", "raw_spare_status",
            "thermal_beats", "power_beats", "door_beats",
            "thermal_max_gap_ms", "power_max_gap_ms", "door_max_gap_ms",
        }
        unknown = sorted(key for key in record.raw_fields if key not in known)
        self.assertEqual(unknown, [], f"formatter emits fields the schema does not declare: "
                                      f"{unknown}")

    def test_w05_fields_are_declared_required(self) -> None:
        for name in ("device_id", "seq", "calibration_id", "quality", "thermal_quality",
                     "cooling_applied", "cooling_evidence", "health", "thermal_age_ms"):
            self.assertIn(name, schema.W05_REQUIRED_FIELDS, name)


class BackCompatibilityTests(unittest.TestCase):
    def test_committed_w04_capture_still_parses(self) -> None:
        """Raising the serial schema must not orphan the W04 evidence."""
        self.assertTrue(W04_CAPTURE.exists(), f"missing committed capture {W04_CAPTURE}")
        records, report = schema.read_capture(W04_CAPTURE)
        self.assertGreaterEqual(len(records), 10, report)
        self.assertEqual(report["rejected"], [], "a real W04 line was rejected by the W05 parser")
        self.assertTrue(all(r.value("schema") == 1 for r in records))
        # A schema-1 frame carries none of the W05 fields; it must not be
        # silently upgraded with defaults either.
        self.assertIsNone(records[0].value("device_id"))
        self.assertIsNone(records[0].value("quality"))

    def test_schema_one_line_does_not_require_w05_fields(self) -> None:
        line = next(
            line for line in W04_CAPTURE.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.startswith("#CG TELEM")
        )
        record = schema.parse_line(line)
        self.assertEqual(record.value("schema"), 1)

    def test_unknown_schema_is_rejected(self) -> None:
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(v2_line(schema=schema.SCHEMA_VERSION + 1))


class W05VocabularyTests(unittest.TestCase):
    def test_missing_w05_field_is_rejected(self) -> None:
        line = v2_line()
        for name in ("device_id", "seq", "calibration_id", "quality", "cooling_applied",
                     "health", "thermal_age_ms", "t1_rom"):
            with self.subTest(name=name):
                with self.assertRaises(schema.TelemetryError) as ctx:
                    schema.parse_line(line.replace(f" {name}=", " cg_removed="))
                self.assertIn(name, str(ctx.exception))

    def test_quality_outside_canonical_vocabulary_is_rejected(self) -> None:
        # docs/01 2302-2306: UNKNOWN must not silently become normal. A typo or a
        # invented fifth state has to fail at the parser, not become a label.
        for bad in ("GOOD", "normal", "Partial", ""):
            if bad == "":
                continue
            with self.subTest(bad=bad):
                with self.assertRaises(schema.TelemetryError) as ctx:
                    schema.parse_line(v2_line(quality=bad))
                self.assertIn("quality", str(ctx.exception))

    def test_all_four_canonical_states_are_accepted(self) -> None:
        for good in schema.QUALITY_VOCABULARY:
            with self.subTest(good=good):
                record = schema.parse_line(v2_line(quality=good))
                self.assertEqual(record.value("quality"), good)

    def test_health_vocabulary_is_closed(self) -> None:
        for good in schema.HEALTH_VOCABULARY:
            record = schema.parse_line(v2_line(health=good, health_thermal=good))
            self.assertEqual(record.value("health"), good)
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(v2_line(health="FINE"))

    def test_cooling_evidence_vocabulary_is_closed(self) -> None:
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(v2_line(cooling_evidence="MEASURED"))
        record = schema.parse_line(v2_line(cooling_evidence="MEASURED_CONTRADICTS_APPLIED"))
        self.assertEqual(record.value("cooling_evidence"), "MEASURED_CONTRADICTS_APPLIED")

    def test_identity_consistency_is_enforced(self) -> None:
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(v2_line(seq=0))
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(v2_line(t2_rom="28aebf2200000006"))  # lowercase is not the token
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(v2_line(t2_rom="28AEBF22000000"))  # 14 hex, truncated
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(v2_line(probes_valid=4))  # probes_expected is 3
        self.assertEqual(
            schema.parse_line(v2_line(spare_rom="UNREAD")).value("spare_rom"), "UNREAD"
        )

    def test_negative_age_is_rejected(self) -> None:
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(v2_line(thermal_age_ms=-5))


class BuilderHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _build(self, lines: list[str]):
        log = self.tmp / "capture.log"
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        jsonl = self.tmp / "out.jsonl"
        csv_path = self.tmp / "out.csv"
        ml_path = self.tmp / "out-ml.csv"
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = cg_build_telemetry.main(
                [str(log), "--jsonl", str(jsonl), "--csv", str(csv_path),
                 "--ml-out", str(ml_path)]
            )
        return code, out.getvalue(), jsonl, csv_path, ml_path

    def test_w05_columns_reach_both_views(self) -> None:
        code, _out, _jsonl, csv_path, ml_path = self._build(
            [v2_line(), v2_line(uptime_ms=1001000)]
        )
        self.assertEqual(code, 0)
        header = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")
        for name in ("device_id", "seq", "calibration_id", "quality", "cooling_applied",
                     "thermal_age_ms", "health", "t2_rom"):
            self.assertIn(name, header)
        row = dict(zip(header, csv_path.read_text(encoding="utf-8").splitlines()[1].split(",")))
        self.assertEqual(row["device_id"], "coldguard-001")
        self.assertEqual(row["calibration_id"], "UNRECORDED")

        ml_header = ml_path.read_text(encoding="utf-8").splitlines()[0].split(",")
        for name in ("device_id", "seq", "quality", "cooling_applied", "probes_valid"):
            self.assertIn(name, ml_header)

    def test_quality_names_are_not_masked_in_ml_view(self) -> None:
        """The ML view masks a *value* whose status is not OK. It must never mask
        the quality verdict that tells the consumer the value was masked."""
        code, _out, _jsonl, _csv, ml_path = self._build([v2_line(thermal_quality="INVALID")])
        self.assertEqual(code, 0)
        header, row = ml_path.read_text(encoding="utf-8").splitlines()[:2]
        ml = dict(zip(header.split(","), row.split(",")))
        self.assertEqual(ml["thermal_quality"], "INVALID")

    def test_summary_reports_quality_distribution_and_seq_range(self) -> None:
        code, out, _jsonl, _csv, _ml = self._build(
            [v2_line(seq=1), v2_line(seq=2, quality="DEGRADED"), v2_line(seq=3)]
        )
        self.assertEqual(code, 0)
        self.assertIn("frame quality", out)
        self.assertIn("seq range", out)
        self.assertIn("1..3 (duplicates=0, non-monotonic=0)", out)

    def test_duplicate_seq_is_visible_in_the_summary(self) -> None:
        """(device_id, boot_id, seq) is the backend dedup key, so a capture that
        repeats a seq has to say so at conversion time rather than let two frames
        collapse into one row later."""
        code, out, _jsonl, _csv, _ml = self._build([v2_line(seq=4), v2_line(seq=4)])
        self.assertEqual(code, 0)
        self.assertIn("duplicates=1", out)

    def test_mixed_schema_capture_keeps_empty_w05_cells(self) -> None:
        w04 = next(
            line for line in W04_CAPTURE.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.startswith("#CG TELEM")
        )
        code, _out, _jsonl, csv_path, _ml = self._build([w04, v2_line()])
        self.assertEqual(code, 0)
        rows = list(csv.reader(csv_path.read_text(encoding="utf-8").splitlines()))
        header, first, second = rows[0], rows[1], rows[2]
        w04_row = dict(zip(header, first))
        self.assertEqual(w04_row["schema"], "1")
        self.assertEqual(w04_row["device_id"], "")
        self.assertEqual(w04_row["quality"], "")
        w05_row = dict(zip(header, second))
        self.assertEqual(w05_row["schema"], str(schema.SCHEMA_VERSION))
        self.assertEqual(w05_row["device_id"], "coldguard-001")


if __name__ == "__main__":
    unittest.main()
