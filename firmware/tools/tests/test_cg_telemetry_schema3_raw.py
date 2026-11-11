"""Regression pins for raw DS18B20 temperature typing on schema-3 frames.

Frame base: the committed W06 demo capture (TELEM schema=3 line). Only raw
temperature token values are substituted; every other field is untouched.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_telemetry_schema as schema  # noqa: E402

COMMITTED = {
    "raw_t1_c": "25.0625",
    "raw_t2_c": "25.0625",
    "raw_t3_c": "25.0625",
    "raw_spare_c": "25.0625",
}


def _committed_frame() -> str:
    for ln in DEMO_CAPTURE.read_text(encoding="utf-8").splitlines():
        if ln.startswith(schema.PREFIX):
            return ln
    raise AssertionError("committed demo capture carries no schema-3 TELEM line")


def _with_raw_overrides(frame: str, **overrides: str) -> str:
    for token, value in overrides.items():
        needle = f"{token}={COMMITTED[token]}"
        if needle not in frame:
            raise AssertionError(f"fixture drift: {needle} absent from committed frame")
        frame = frame.replace(needle, f"{token}={value}", 1)
    return frame


DEMO_CAPTURE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "evidence" / "A" / "W06" / "demo-command-capture.log"
)


class RawTemperatureTyping(unittest.TestCase):
    def test_committed_capture_raw_fields_are_floats(self) -> None:
        record = schema.parse_line(_committed_frame())
        for name in ("raw_t1_c", "raw_t2_c", "raw_t3_c", "raw_spare_c"):
            self.assertIsInstance(record.fields[name], float, name)

    def test_negative_and_decimal_values_coerce_to_float(self) -> None:
        line = _with_raw_overrides(_committed_frame(), raw_t1_c="-12.5")
        record = schema.parse_line(line)
        self.assertEqual(record.fields["raw_t1_c"], -12.5)
        self.assertEqual(record.fields["raw_t2_c"], 25.0625)

    def test_nan_means_missing_not_zero(self) -> None:
        line = _with_raw_overrides(_committed_frame(), raw_t1_c="nan")
        self.assertIsNone(schema.parse_line(line).fields["raw_t1_c"])

    def test_duplicate_raw_field_is_rejected(self) -> None:
        line = _committed_frame() + " raw_t1_c=2.0"
        with self.assertRaises(schema.TelemetryError):
            schema.parse_line(line)


if __name__ == "__main__":
    unittest.main()
