"""Build sensor-consistency.csv and a consistency summary from a serial capture.

Implements docs/05A A-W02-05 / docs/03 SEN-H1-03 from *real* logged samples:
per-probe mean, sample SD, min, max, pairwise mean differences and the
maximum disagreement. Requires ``--min-samples`` valid samples per probe
before it will call the window usable.

It never invents samples: ``nan`` readings stay empty cells, and the
result is reported as a consistency check, never as certified calibration
(no traceable reference exists).

Exit codes: 0 = window usable, 1 = window not usable, 2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import cg_serial  # noqa: E402

CSV_COLUMNS = ["uptime_ms", "seq", "t1_c", "t2_c", "t3_c", "t1_valid", "t2_valid", "t3_valid", "thermal"]


def write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            cooked = {}
            for column in CSV_COLUMNS:
                value = row.get(column)
                if isinstance(value, float):
                    cooked[column] = f"{value:.4f}"
                elif value is None:
                    cooked[column] = ""  # missing stays missing, never 0
                else:
                    cooked[column] = value
            writer.writerow(cooked)


def render_summary(report: dict) -> str:
    lines = []
    lines.append(f"samples               : {report['n_samples']}")
    lines.append(f"window duration       : {report['duration_s']} s")
    lines.append(f"effective rate        : {report['rate_hz']} Hz")
    lines.append(f"thermal quality counts: {report['quality_counts']}")
    lines.append("")
    lines.append("role  n_valid/n_total  mean_c    sd_c     min_c    max_c    range_c")
    for role in cg_serial.MEASUREMENT_ROLES:
        stat = report["stats"][role]
        def fmt(value):
            return "n/a" if value is None else f"{value:.4f}"
        lines.append(
            f"{role:<4}  {stat['n_valid']}/{stat['n_total']:<10}  {fmt(stat['mean_c']):<8} "
            f"{fmt(stat['sd_c']):<8} {fmt(stat['min_c']):<8} {fmt(stat['max_c']):<8} {fmt(stat['range_c'])}"
        )
    lines.append("")
    lines.append("pairwise mean differences (first role minus second role):")
    for pair, diff in report["pairwise_mean_differences"].items():
        lines.append(f"pairwise mean difference {pair}: " + ("n/a" if diff is None else f"{diff:+.4f} C"))
    max_dis = report["max_disagreement_c"]
    lines.append("max disagreement      : " + ("n/a" if max_dis is None else f"{max_dis:.4f} C"))
    lines.append("")
    lines.append("NOTE: consistency check only - no traceable reference was used.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build sensor-consistency.csv from a real capture (A-W02-05).")
    parser.add_argument("log", help="serial capture produced by cg_capture.py")
    parser.add_argument("--out", required=True, help="output CSV path")
    parser.add_argument("--summary-out", default=None, help="optional markdown summary path")
    parser.add_argument("--min-samples", type=int, default=600, help="minimum valid samples per probe (default: 600)")
    parser.add_argument("--json", dest="json_out", default=None, help="also write the statistics as JSON")
    args = parser.parse_args(argv)

    try:
        parsed = cg_serial.read_log(args.log)
    except OSError as exc:
        print(f"cannot read {args.log}: {exc}", file=sys.stderr)
        return 2

    samples = parsed.samples
    if not samples:
        print("no #CG SAMPLE lines in this capture - nothing to build", file=sys.stderr)
        return 1

    stats = cg_serial.consistency_stats(samples)
    duration_s, rate_hz = cg_serial.effective_rate(samples)
    quality_counts: dict[str, int] = {}
    for sample in samples:
        quality_counts[sample.thermal or "UNKNOWN"] = quality_counts.get(sample.thermal or "UNKNOWN", 0) + 1

    report = {
        "source_log": str(args.log),
        "n_samples": len(samples),
        "duration_s": None if duration_s is None else round(duration_s, 3),
        "rate_hz": None if rate_hz is None else round(rate_hz, 4),
        "quality_counts": quality_counts,
        "stats": stats,
        "pairwise_mean_differences": cg_serial.pairwise_mean_differences(stats),
        "max_disagreement_c": cg_serial.max_disagreement(stats),
        "min_samples_required": args.min_samples,
    }

    write_csv(pathlib.Path(args.out), cg_serial.sensor_csv_rows(samples))
    print(render_summary(report))
    print()
    print(f"csv written: {args.out}")

    if args.summary_out:
        pathlib.Path(args.summary_out).write_text(render_summary(report) + "\n", encoding="utf-8")
        print(f"summary written: {args.summary_out}")
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"json written: {args.json_out}")

    usable = [
        stat["n_valid"] >= args.min_samples and stat["n_valid"] == stat["n_total"]
        for stat in stats.values()
    ]
    if all(usable):
        print(f"SENSOR CONSISTENCY: WINDOW USABLE (>= {args.min_samples} valid samples on every probe)")
        return 0
    print(f"SENSOR CONSISTENCY: WINDOW NOT USABLE (< {args.min_samples} valid samples or invalid readings present)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
