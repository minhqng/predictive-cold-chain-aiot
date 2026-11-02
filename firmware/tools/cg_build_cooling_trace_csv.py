"""Derive a cooling-response trace CSV from a raw H8 monitor `samples.jsonl`.

    py firmware/tools/cg_build_cooling_trace_csv.py \
        <samples.jsonl> --csv evidence/A/W04/tec-cooling-response-600s.csv \
        --session "H8 box-cooling 600 s, 2026-11-01"

The JSONL is the device's own telemetry stream, one object per second. This
builder only selects and renames fields that exist in the raw record; every
column carries the device's own status/role label, so a reader can see which
channels the device actually assigned a role to and which it left
`UNASSIGNED`. Nothing is interpolated and no row is dropped silently: the
counts of parsed, skipped and per-state rows are printed.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

COLUMNS = [
    "session", "seq", "device_ms", "stage_elapsed_s", "state", "stage",
    "stop_reason", "fault_bits", "snapshot",
    "pwm_req_permille", "pwm_applied_permille", "pwm_readback_permille",
    "voltage_v", "voltage_status", "current_a", "current_status",
    "power_w", "energy_wh",
    "t1_c", "t1_status", "t1_role", "t1_age_ms",
    "t2_c", "t2_status", "t2_role", "t2_age_ms",
    "t3_c", "t3_status", "t3_role", "t3_age_ms",
    "t4_c", "t4_status", "t4_role", "t4_age_ms",
    "bme_air_c", "bme_rh_pct", "bme_pressure_hpa", "bme_pressure_status",
    "fan", "fan_readback", "door_open", "door_polarity",
    "boot_id", "run_id", "limits_policy", "physical_output",
]

# The monitor writes `t1`..`t4` plus `t<n>_status/_role/_age_ms`; the electrical
# fields are named per the H8 schema. Missing keys stay empty, never zero.
ALIASES = {
    "t1_c": ("t1",), "t1_status": ("t1_status",), "t1_role": ("t1_role",), "t1_age_ms": ("t1_age_ms",),
    "t2_c": ("t2",), "t2_status": ("t2_status",), "t2_role": ("t2_role",), "t2_age_ms": ("t2_age_ms",),
    "t3_c": ("t3",), "t3_status": ("t3_status",), "t3_role": ("t3_role",), "t3_age_ms": ("t3_age_ms",),
    "t4_c": ("t4",), "t4_status": ("t4_status",), "t4_role": ("t4_role",), "t4_age_ms": ("t4_age_ms",),
    "bme_air_c": ("air_c",), "bme_rh_pct": ("rh_pct",),
    "bme_pressure_hpa": ("pressure_hpa",), "bme_pressure_status": ("pressure_status",),
    "pwm_req_permille": ("pwm_req",), "pwm_applied_permille": ("pwm_applied", "pwm_applied_permille"),
    "pwm_readback_permille": ("pwm_readback", "pwm_readback_permille"),
    "voltage_status": ("voltage_status", "voltage_v_status"),
    "current_status": ("current_status", "current_a_status"),
    "power_w": ("power_w",),
    "stage_elapsed_s": ("stage_elapsed_ms",),
    "physical_output": ("physical_output",),
}


def pick(raw: dict[str, object], column: str) -> str:
    for name in ALIASES.get(column, (column,)):
        if name in raw and raw[name] is not None:
            value = raw[name]
            if name == "stage_elapsed_ms" and column == "stage_elapsed_s":
                return f"{float(value) / 1000:.3f}"
            return str(value)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=pathlib.Path)
    parser.add_argument("--csv", type=pathlib.Path, required=True)
    parser.add_argument("--session", default="UNLABELLED")
    args = parser.parse_args()

    rows: list[dict[str, str]] = []
    skipped = 0
    for line in args.jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not isinstance(raw, dict):
            skipped += 1
            continue
        rows.append({"session": args.session, **{column: pick(raw, column) for column in COLUMNS[1:]}})

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    states: dict[str, int] = {}
    for row in rows:
        states[row["state"] or "EMPTY"] = states.get(row["state"] or "EMPTY", 0) + 1
    roles = sorted({(row["t2_role"] or "EMPTY") for row in rows})
    print(f"rows written : {len(rows)} -> {args.csv}  (skipped unparsable lines: {skipped})")
    print(f"states       : {states}")
    print(f"t2_role seen : {roles}")
    for column in ("t1_role", "t3_role", "t4_role"):
        seen = sorted({(row[column] or "EMPTY") for row in rows})
        print(f"{column:9s} seen : {seen}")
    cooling = [row for row in rows if row["state"] == "COOLING" and row["current_a"] not in ("", None)]
    if cooling:
        peak = max(cooling, key=lambda r: float(r["current_a"] or 0))
        print(f"COOLING rows : {len(cooling)}, peak current {peak['current_a']} A")
    return 0


if __name__ == "__main__":
    sys.exit(main())
