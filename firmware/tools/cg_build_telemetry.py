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

CSV_COLUMNS_BASE = [
    # A W05 parser accepts schema 1 and 2, so one capture can legitimately mix
    # them. The row has to say which line produced it.
    "schema",
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

# W05 additions to the flat acquisition view. A schema-1 record has none of
# these, and they serialize as empty cells rather than as invented zeros - the
# W04 captures committed in evidence/A/W04/ build through this same tool.
W05_CSV_COLUMNS = [
    "device_id",
    "seq",
    "calibration_id",
    "role_status",
    "t1_rom",
    "t2_rom",
    "t3_rom",
    "spare_rom",
    "energy_wh",
    "energy_status",
    "thermal_age_ms",
    "power_age_ms",
    "door_age_ms",
    "thermal_seq",
    "power_seq",
    "door_transitions",
    "door_cycles",
    "probes_valid",
    "probes_expected",
    "thermal_quality",
    "environment_quality",
    "door_quality",
    "electrical_quality",
    "quality",
    "cooling_applied",
    "cooling_applied_source",
    "cooling_evidence",
    "health",
    "health_thermal",
    "health_bme",
    "health_door",
    "health_power",
    "health_telemetry",
    "health_control",
    "thermal_beats",
    "power_beats",
    "door_beats",
    "thermal_max_gap_ms",
    "power_max_gap_ms",
    "door_max_gap_ms",
]

CSV_COLUMNS = CSV_COLUMNS_BASE + W05_CSV_COLUMNS

# The ML handoff gains exactly the columns Member B needs to decide whether a
# frame is usable and where it came from: identity, the canonical quality
# verdict, the freshness it must not assume, and the applied cooling state.
# Values are still masked by status; quality names are never masked, because
# they are the mask signal itself.
W05_CORE_ML_COLUMNS = [
    "device_id",
    "seq",
    "calibration_id",
    "thermal_quality",
    "environment_quality",
    "door_quality",
    "electrical_quality",
    "quality",
    "thermal_age_ms",
    "power_age_ms",
    "door_age_ms",
    "probes_valid",
    "probes_expected",
    "cooling_applied",
    "cooling_evidence",
    "energy_wh",
    "health",
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
] + W05_CORE_ML_COLUMNS

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
    schemas = sorted({str(r.raw_fields.get("schema", "?")) for r in records})
    devices = sorted({str(r.value("device_id")) for r in records if r.value("device_id")})
    lines = [
        f"telemetry records     : {len(records)}",
        f"line schemas          : {', '.join(schemas)}",
        f"devices               : "
        f"{', '.join(devices) if devices else ('n/a (no records)' if not records else 'not carried (schema 1 lines)')}",
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

    # W05: the quality distribution is part of the handoff, not an afterthought.
    # A dataset built from frames that were mostly INVALID has to say so at the
    # point of conversion, before anyone plots it.
    quality_counts: dict[str, int] = {}
    for record in records:
        value = record.value("quality")
        if isinstance(value, str):
            quality_counts[value] = quality_counts.get(value, 0) + 1
    if quality_counts:
        order = ["VALID", "DEGRADED", "INVALID", "UNKNOWN"]
        rendered = ", ".join(
            f"{name}={quality_counts[name]}"
            for name in order
            if name in quality_counts
        )
        extra = sorted(set(quality_counts) - set(order))
        if extra:
            rendered += ", " + ", ".join(f"{name}={quality_counts[name]}" for name in extra)
        lines.append(f"frame quality           : {rendered}")

    seqs = [record.value("seq") for record in records if isinstance(record.value("seq"), int)]
    if seqs:
        duplicates = len(seqs) - len(set(seqs))
        lines.append(
            f"seq range               : {min(seqs)}..{max(seqs)} "
            f"(duplicates={duplicates}, non-monotonic="
            f"{sum(1 for a, b in zip(seqs, seqs[1:]) if b <= a)})"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build raw JSONL, acquisition CSV and ML dataset from a W04/W05 capture."
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
