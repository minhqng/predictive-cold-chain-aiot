"""Build acquisition files from a ColdGuard W04 serial capture.

Three separate outputs; the raw capture is never rewritten:

* ``--jsonl``: one record per ``#CG TELEM`` line, including the exact
  device line (``raw``) and both the token view (``raw_fields``) and the
  typed view (``fields``). This is the traceable extraction of the raw
  record.
* ``--csv``: the flat acquisition table required by the A-W04 data
  contract. Missing values are empty cells with an explicit ``*_status``
  column; they are never 0 and never carried forward.
* ``--ml-out``: a derived dataset, deliberately separate from the raw
  files. A numeric feature is only populated when its status is ``OK``;
  anomalies stay empty and remain visible through the status columns.

Usage:

    py firmware/tools/cg_build_telemetry.py evidence/A/W04/serial-w04.log \
        --jsonl evidence/A/W04/telemetry-raw.jsonl \
        --csv evidence/A/W04/telemetry.csv \
        --ml-out evidence/A/W04/ml-dataset.csv

Exit codes: 0 = usable (at least one record, nothing rejected),
1 = no records or at least one rejected telemetry line,
2 = usage/IO error. A rejected line means the capture is not fully
trustworthy even though the valid records are still written.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import cg_telemetry_schema as schema  # noqa: E402

CSV_COLUMNS = [
    "timestamp_utc",
    "timestamp_utc_source",
    "elapsed_ms",
    "run_id",
    "boot_id",
    "firmware_version",
    "hardware_config_id",
    "test_phase",
    "t_inside_c",
    "t_inside_status",
    "t_cold_side_c",
    "t_cold_side_status",
    "t_hot_side_c",
    "t_hot_side_status",
    "t_ambient_c",
    "t_ambient_status",
    "relative_humidity_pct",
    "relative_humidity_status",
    "door_open",
    "door_status",
    "voltage_v",
    "voltage_status",
    "current_a",
    "current_status",
    "power_w",
    "power_status",
    "pwm_duty",
    "fan_command",
    "fan_status",
    "output_stage",
    "tec_state",
    "fault_code",
    "fault_reason",
    "sensor_validity",
    "power_validity",
]

ML_COLUMNS = [
    "elapsed_ms",
    "run_id",
    "boot_id",
    "test_phase",
    "t_inside_c",
    "t_ambient_c",
    "t_cold_side_c",
    "t_hot_side_c",
    "relative_humidity_pct",
    "voltage_v",
    "current_a",
    "power_w",
    "pwm_duty",
    "fan_on",
    "tec_state",
    "fault_code",
    "t_inside_status",
    "sensor_validity",
    "power_validity",
    "door_open",
]

# The ML view masks a value unless its companion status is OK. The raw
# and flat CSV views keep the device token untouched.
ML_MASKED_FIELDS = (
    "t_inside_c",
    "t_ambient_c",
    "t_cold_side_c",
    "t_hot_side_c",
    "relative_humidity_pct",
    "voltage_v",
    "current_a",
    "power_w",
    "door_open",
)


def _csv_cell(name: str, value: object) -> object:
    if value is None:
        return ""
    if name == "fault_code" and isinstance(value, int):
        return f"0x{value:08X}"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def _ml_cell(record: schema.TelemetryRecord, name: str) -> object:
    if name == "fan_on":
        fan = record.value("fan_command")
        if fan == "ON":
            return 1
        if fan == "OFF":
            return 0
        return None
    if name in ML_MASKED_FIELDS:
        return record.value(name) if record.usable(name) else None
    return record.value(name)


def write_jsonl(path: pathlib.Path, records: list[schema.TelemetryRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(
                json.dumps(
                    {
                        "line_index": record.line_index,
                        "raw": record.raw,
                        "fields": record.fields,
                        "raw_fields": record.raw_fields,
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                )
                + "\n"
            )


def write_csv(path: pathlib.Path, records: list[schema.TelemetryRecord], columns: list[str], ml: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for record in records:
            row = {}
            for name in columns:
                value = _ml_cell(record, name) if ml else record.value(name)
                row[name] = _csv_cell(name, value)
            writer.writerow(row)


def summarize(records: list[schema.TelemetryRecord], report: dict) -> str:
    boots = sorted({str(r.value("boot_id")) for r in records})
    runs = sorted({str(r.value("run_id")) for r in records})
    phases = sorted({str(r.value("test_phase")) for r in records})
    lines = [
        f"telemetry records     : {len(records)}",
        f"boots                 : {', '.join(boots) if boots else 'none'}",
        f"run_ids               : {', '.join(runs) if runs else 'none'}",
        f"test phases           : {', '.join(phases) if phases else 'none'}",
        f"ignored lines         : {report['ignored']}",
        f"rejected telemetry    : {len(report['rejected'])}",
    ]
    for item in report["rejected"][:10]:
        lines.append(f"  line {item['line_index']}: {item['reason']}")
    if len(report["rejected"]) > 10:
        lines.append(f"  ... {len(report['rejected']) - 10} more rejected lines")
    lines.append("timestamp_utc         : UNAVAILABLE on every record (device has no wall clock)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build raw JSONL, acquisition CSV and ML dataset from a W04 capture."
    )
    parser.add_argument("log", help="serial capture produced by cg_capture.py")
    parser.add_argument("--jsonl", required=True, help="output raw JSONL path")
    parser.add_argument("--csv", required=True, help="output flat acquisition CSV path")
    parser.add_argument("--ml-out", default=None, help="optional derived ML dataset CSV path")
    args = parser.parse_args(argv)

    try:
        records, report = schema.read_capture(args.log)
    except OSError as exc:
        print(f"cannot read {args.log}: {exc}", file=sys.stderr)
        return 2

    if not records:
        print("no #CG TELEM lines in this capture - nothing to build", file=sys.stderr)
        print(summarize(records, report), file=sys.stderr)
        return 1

    write_jsonl(pathlib.Path(args.jsonl), records)
    write_csv(pathlib.Path(args.csv), records, CSV_COLUMNS, ml=False)
    print(summarize(records, report))
    print(f"jsonl written: {args.jsonl}")
    print(f"csv written  : {args.csv}")

    if args.ml_out:
        write_csv(pathlib.Path(args.ml_out), records, ML_COLUMNS, ml=True)
        print(f"ml written   : {args.ml_out}")

    if report["rejected"]:
        print("TELEMETRY ACQUISITION: NOT CLEAN (rejected telemetry lines present)")
        return 1
    print("TELEMETRY ACQUISITION: CLEAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
