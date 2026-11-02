"""Derive the W04 first-TEC-response CSV from a raw H6 bench capture.

    py firmware/tools/cg_build_h6_trace_csv.py \
        evidence/A/W04/h6/40-h6-run.log \
        --csv evidence/A/W04/h6/first-tec-trace.csv

The H6 image (`firmware/h6-bench/`) drives PWM and polls the PZEM-017; it does
not read the DS18B20 bus or the BME280, so `thermal_channels` is
`NOT_READ_BY_H6_IMAGE` on every row. Nothing is invented: each row is one
device line from the log, and each value is the value that line carries.
`--require-clean` makes the builder fail if the session shows any fault,
non-`OK` delivered sample, or missing terminal OFF/END record, so the CSV
cannot be produced from a run that was not actually clean.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import re
import sys

LINE = re.compile(r"^\[\s*(?P<uptime>\d+\.\d+)\]\s+(?P<utc>\d\d:\d\d:\d\d\.\d\d\d)\s+(?P<body>.*)$")
FIELD = re.compile(r"(\w+)=(\S+)")
SAMPLE = re.compile(r"\bH6 T\b")
EVENT = re.compile(r"\bH6 (CMD|ON|OFF|END|PRECHECK)\b")
TRACE = re.compile(r"\bH6 PZEM_TRACE\b")

COLUMNS = [
    "host_utc",
    "host_uptime_s",
    "record_type",
    "event_label",
    "state",
    "duty_permille",
    "vbus_v",
    "current_a",
    "power_w",
    "thermal_channels",
    "pzem_class",
    "pzem_attempt",
    "rpwm_level",
    "ren",
    "len",
    "elapsed_ms",
    "source_line",
]

# The H6 capture is 2026-10-29 (UTC) per its own `# capture start` header.
CAPTURE_DATE_RE = re.compile(r"# capture start (\d{4}-\d{2}-\d{2})")


def fields(body: str) -> dict[str, str]:
    return dict(FIELD.findall(body))


def build(log_path: pathlib.Path) -> tuple[list[dict[str, str]], dict[str, int]]:
    text = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    date = "UNKNOWN_DATE"
    for line in text[:5]:
        match = CAPTURE_DATE_RE.search(line)
        if match:
            date = match.group(1)
            break

    rows: list[dict[str, str]] = []
    counters = {"samples": 0, "samples_ok": 0, "traces": 0, "echo_only": 0, "events": 0}
    last_trace: dict[str, str] = {}

    for number, line in enumerate(text, start=1):
        outer = LINE.match(line.strip())
        if not outer:
            continue
        body = outer.group("body")
        parsed = fields(body)
        row = {column: "" for column in COLUMNS}
        row["host_utc"] = f"{date}T{outer.group('utc')}Z"
        row["host_uptime_s"] = outer.group("uptime")
        row["source_line"] = str(number)

        if SAMPLE.search(body):
            counters["samples"] += 1
            row["record_type"] = "SAMPLE"
            row["state"] = parsed.get("state", "")
            row["duty_permille"] = parsed.get("duty_permille", "")
            row["elapsed_ms"] = parsed.get("elapsed_ms", "")
            if "vbus_mv" in parsed:
                row["vbus_v"] = f"{int(parsed['vbus_mv']) / 1000:.3f}"
            if "current_ma" in parsed:
                row["current_a"] = f"{int(parsed['current_ma']) / 1000:.3f}"
            if "power_mw" in parsed:
                row["power_w"] = f"{int(parsed['power_mw']) / 1000:.3f}"
            row["pzem_class"] = parsed.get("pzem", "")
            if row["pzem_class"] == "OK":
                counters["samples_ok"] += 1
            row["pzem_attempt"] = last_trace.get("attempt", "")
            row["thermal_channels"] = "NOT_READ_BY_H6_IMAGE"
            rows.append(row)
        elif TRACE.search(body):
            counters["traces"] += 1
            last_trace = parsed
            if parsed.get("class") == "ECHO_ONLY":
                counters["echo_only"] += 1
        elif EVENT.search(body):
            counters["events"] += 1
            kind = re.search(r"H6 (CMD|ON|OFF|END|PRECHECK)", body).group(1)
            row["record_type"] = f"EVENT_{kind}"
            # A short label for the plot marker: ARM/START come through as CMD with
            # a `next=`/`state=` field, so name them from what the line actually says.
            if kind == "CMD":
                row["event_label"] = "ARM" if "ARM accepted" in body else "START"
            else:
                row["event_label"] = kind
            row["state"] = parsed.get("state", "")
            row["duty_permille"] = parsed.get("duty_permille", "")
            row["elapsed_ms"] = parsed.get("elapsed_ms", "")
            row["rpwm_level"] = parsed.get("rpwm_level", "")
            row["ren"] = parsed.get("ren", "")
            row["len"] = parsed.get("len", "")
            row["thermal_channels"] = "NOT_READ_BY_H6_IMAGE"
            if "vbus_mv" in parsed:
                row["vbus_v"] = f"{int(parsed['vbus_mv']) / 1000:.3f}"
            if "current_ma" in parsed:
                row["current_a"] = f"{int(parsed['current_ma']) / 1000:.3f}"
            if "power_mw" in parsed:
                row["power_w"] = f"{int(parsed['power_mw']) / 1000:.3f}"
            rows.append(row)

    return rows, counters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument("--csv", type=pathlib.Path, required=True)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()

    rows, counters = build(args.log)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    samples = [row for row in rows if row["record_type"] == "SAMPLE"]
    loaded = [s for s in samples if s["current_a"] and float(s["current_a"]) > 0]
    print(f"rows written        : {len(rows)} to {args.csv}")
    print(f"device samples      : {counters['samples']} ({counters['samples_ok']} pzem=OK)")
    print(f"loaded samples      : {len(loaded)}")
    if loaded:
        peak = max(loaded, key=lambda s: float(s["current_a"]))
        print(f"peak current        : {peak['current_a']} A at {peak['elapsed_ms']} ms")
    print(f"PZEM traces         : {counters['traces']} ({counters['echo_only']} ECHO_ONLY)")
    print(f"terminal OFF/END    : "
          f"{'present' if any(r['record_type'] == 'EVENT_OFF' for r in rows) and any(r['record_type'] == 'EVENT_END' for r in rows) else 'MISSING'}")

    if args.require_clean:
        problems = []
        if counters["samples"] == 0:
            problems.append("no device samples parsed")
        if counters["samples_ok"] != counters["samples"]:
            problems.append(f"{counters['samples'] - counters['samples_ok']} samples not pzem=OK")
        if not any(r["record_type"] == "EVENT_OFF" for r in rows):
            problems.append("no H6 OFF record")
        if not any(r["record_type"] == "EVENT_END" for r in rows):
            problems.append("no H6 END record")
        if any("fault" in row["state"].lower() for row in rows):
            problems.append("a fault state appears in the session")
        if problems:
            for problem in problems:
                print(f"FAIL: {problem}")
            return 1
        print("H6 TRACE CLEAN: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
