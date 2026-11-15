"""Build door-test.csv and door statistics from a serial capture (A-W02-07).

The firmware logs every raw edge (bounce included) and every committed
transition after the debounce window. This tool turns that into:

* door-test.csv - one row per committed transition;
* a summary with cycle count, raw edges, discarded edges and the
  per-transition edge count (the debounce/bounce evidence).

The raw -> OPEN/CLOSED mapping is an operator decision that must come from
a physical observation (docs/01 section 8.2). Without ``--open-level`` the
tool still builds the CSV but marks every state UNVERIFIED and fails, so a
guess can never be published as a frozen polarity.

A capture that contains door lines from more than one boot is refused
unless ``--boot`` selects one block: counters from different boots must
never be fused into a single number.

Exit codes: 0 = cycles satisfied and polarity supplied, 1 = not proven,
2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import cg_serial  # noqa: E402

CSV_COLUMNS = ["uptime_ms", "raw", "state", "transitions", "cycles", "discarded_edges"]


def write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def render(report: dict, require_cycles: int) -> str:
    lines = []
    lines.append(f"semantic mapping      : {report['semantic_mapping']}")
    lines.append(f"committed transitions : {report['committed_transitions']}")
    lines.append(f"committed cycles      : {report['committed_cycles']} (required >= {require_cycles})")
    lines.append(f"raw edges             : {report['raw_edges']}")
    lines.append(f"discarded raw edges   : {report['discarded_edges']}")
    lines.append(f"edges per transition  : {report['edges_per_transition']}")
    lines.append(f"bounce observed       : {report['bounce_observed']}")
    intervals = report["open_intervals_ms"]
    if intervals:
        lines.append(
            f"door-open intervals ms: n={len(intervals)} min={min(intervals)} "
            f"median={sorted(intervals)[len(intervals) // 2]} max={max(intervals)}"
        )
    else:
        lines.append("door-open intervals ms: none (needs --open-level and at least one OPEN->CLOSED pair)")
    lines.append("")
    lines.append("NOTE: debounce evidence is the per-transition edge count; a value > 1")
    lines.append("      means contact bounce was absorbed by the debounce window.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build door-test.csv from a real capture (A-W02-07).")
    parser.add_argument("log", help="serial capture produced by cg_capture.py")
    parser.add_argument("--out", required=True, help="output CSV path")
    parser.add_argument(
        "--open-level",
        type=int,
        choices=(0, 1),
        default=None,
        help="raw electrical level physically observed as OPEN (required to claim door semantics)",
    )
    parser.add_argument("--require-cycles", type=int, default=20, help="minimum committed cycles (default: 20)")
    parser.add_argument(
        "--boot",
        type=int,
        default=None,
        help="boot index (0-based, order of #CG BOOT lines) when the capture spans several reboots",
    )
    parser.add_argument("--json", dest="json_out", default=None, help="also write the statistics as JSON")
    args = parser.parse_args(argv)

    try:
        parsed = cg_serial.read_log(args.log)
    except OSError as exc:
        print(f"cannot read {args.log}: {exc}", file=sys.stderr)
        return 2

    if not parsed.door_states and not parsed.door_edges:
        print("no #CG DOOR_EDGE / #CG DOOR_STATE lines in this capture - nothing to build", file=sys.stderr)
        return 1

    indices = cg_serial.door_boot_indices(parsed)
    if args.boot is not None:
        if args.boot not in indices:
            print(
                f"--boot {args.boot} has no door lines; capture contains boots {indices}",
                file=sys.stderr,
            )
            return 2
    elif len(indices) > 1:
        print(
            "capture contains door lines from multiple boots "
            f"({indices}): capture one boot per door test or select one with --boot N",
            file=sys.stderr,
        )
        return 1

    report = cg_serial.door_analysis(parsed, args.open_level, boot_index=args.boot)

    write_csv(
        pathlib.Path(args.out),
        cg_serial.door_csv_rows(parsed, args.open_level, boot_index=args.boot),
    )
    print(render(report, args.require_cycles))
    print()
    print(f"csv written: {args.out}")

    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"json written: {args.json_out}")

    cycles_ok = report["committed_cycles"] >= args.require_cycles
    if args.open_level is None:
        print("DOOR TEST: NOT PROVEN (semantic polarity UNVERIFIED)")
        return 1
    if not cycles_ok:
        print(f"DOOR TEST: NOT PROVEN ({report['committed_cycles']} cycles < {args.require_cycles})")
        return 1
    tail = (
        "open duration evidence present"
        if report["open_intervals_ms"]
        else "no complete OPEN->CLOSED pair to measure duration"
    )
    print(f"DOOR TEST: CYCLES PROVEN ({report['committed_cycles']} >= {args.require_cycles}); {tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
