"""Build pzem-off.csv and the TEC-OFF power statistics from a real capture (A-W03-05).

Implements docs/05A A-W03-05: a >= 10 minute PZEM log with the TEC off,
turned into

* ``pzem-off.csv`` - one row per poll with uptime, V/A/W/Wh, link status,
  CRC flag, attempts and the firmware's ok/fail counters;
* a summary with sample count, window duration, success rate, error rate,
  status breakdown, poll gaps and per-quantity mean/min/max/noise (sample
  SD) over the *valid* samples only.

Hard rules, because this file may be quoted as measurement evidence:

* The tool never invents rows. ``nan`` stays an empty cell; a failed poll
  never repeats the previous value.
* "TEC off" is an operator assertion the tool cannot verify: without
  ``--tec-off-confirmed`` the window is still converted but the verdict is
  NOT USABLE and the exit code is 1.
* A capture that mixes several boots is refused unless ``--boot`` selects
  one block (counters from different sessions must never be fused).
* The window must cover at least ``--min-duration-s`` seconds of real
  ``uptime_ms`` and reach ``--min-ok-fraction`` valid samples before it is
  called usable.

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

CSV_COLUMNS = [
    "uptime_ms",
    "seq",
    "status",
    "crc_ok",
    "attempts",
    "exception_code",
    "voltage_v",
    "current_a",
    "power_w",
    "energy_wh",
    "ok_count",
    "fail_count",
]

# Exact display formats for the register least-significant bits:
# V 0.01, A 0.01, W 0.1, Wh 1.
_FLOAT_FORMATS = {
    "voltage_v": "{:.2f}",
    "current_a": "{:.2f}",
    "power_w": "{:.1f}",
    "energy_wh": "{:.0f}",
}


def write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            cooked: dict = {}
            for column in CSV_COLUMNS:
                value = row.get(column)
                if isinstance(value, float):
                    cooked[column] = _FLOAT_FORMATS[column].format(value)
                elif value is None:
                    cooked[column] = ""  # missing stays missing, never 0
                else:
                    cooked[column] = value
            writer.writerow(cooked)


def render(report: dict) -> str:
    lines: list[str] = []
    config = report["config"]
    if config is None:
        lines.append("config            : MISSING (#CG PZEM_CFG not present)")
    else:
        lines.append(
            f"config            : slave={config['slave']} baud={config['baud']} "
            f"framing={config['framing']} dir={config['direction']} "
            f"read_only={int(config['read_only'])}"
        )
    lines.append(f"boot              : {report['boot']}")
    lines.append(
        f"samples           : {report['n_total']} (ok {report['n_ok']}, error {report['n_error']})"
    )
    lines.append(
        f"window            : {report['first_uptime_ms']} -> {report['last_uptime_ms']} ms "
        f"({report['duration_s']} s, required >= {report['min_duration_s']} s)"
    )
    lines.append(f"success rate      : {report['success_rate_text']}")
    lines.append(f"error rate        : {report['error_rate_text']}")
    lines.append(f"status counts     : {report['status_counts']}")
    lines.append(f"attempts counts   : {report['attempts_counts']}")
    lines.append(
        f"crc ok            : {report['crc_ok_count']}/{report['n_total']} "
        f"(CRC_ERR {report['crc_error_count']}, TIMEOUT {report['timeout_count']}, "
        f"EXCEPTION {report['exception_count']}, UART_ERR {report['uart_error_count']})"
    )
    interval = report["interval_ms"]
    lines.append(
        f"poll interval ms  : n={interval['n']} min={interval['min']} "
        f"median={interval['median']} max={interval['max']}"
    )
    gaps = report["gaps"]
    if gaps:
        lines.append(f"gaps              : {len(gaps)} (total {report['gap_total_ms']} ms)")
        for gap in gaps[:10]:
            lines.append(
                f"  gap {gap['gap_ms']} ms: {gap['after_uptime_ms']} -> {gap['uptime_ms']} ms"
            )
    else:
        lines.append("gaps              : none (> 2x median interval)")
    lines.append("")
    lines.append("quantity   n_valid  mean       sd(noise)  min        max        spread")
    for key, label in (
        ("voltage_v", "voltage_v"),
        ("current_a", "current_a"),
        ("power_w", "power_w"),
        ("energy_wh", "energy_wh"),
    ):
        stat = report["stats"][key]

        def fmt(value: float | None) -> str:
            return "n/a" if value is None else f"{value:.4f}"

        lines.append(
            f"{label:<10} {stat['n_valid']:>7}  {fmt(stat['mean']):<10} "
            f"{fmt(stat['sd']):<10} {fmt(stat['min']):<10} {fmt(stat['max']):<10} {fmt(stat['spread'])}"
        )
    lines.append("")
    lines.append(f"TEC off confirmed : {report['tec_off_confirmed']} (operator assertion)")
    lines.append("NOTE: noise = sample standard deviation over valid samples of this window;")
    lines.append("      with the TEC off it is measurement noise, not a load-stability claim.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build pzem-off.csv from a real TEC-OFF capture (A-W03-05)."
    )
    parser.add_argument("log", help="serial capture produced by cg_capture.py")
    parser.add_argument("--out", required=True, help="output CSV path")
    parser.add_argument("--summary-out", default=None, help="optional markdown summary path")
    parser.add_argument(
        "--min-duration-s",
        type=float,
        default=600.0,
        help="minimum window duration in seconds (default: 600 = 10 min)",
    )
    parser.add_argument(
        "--min-ok-fraction",
        type=float,
        default=0.5,
        help="minimum fraction of polls with OK status and all values (default: 0.5)",
    )
    parser.add_argument(
        "--boot",
        type=int,
        default=None,
        help="boot index (0-based, order of #CG BOOT lines) when the capture spans several reboots",
    )
    parser.add_argument(
        "--tec-off-confirmed",
        action="store_true",
        help="operator assertion that the TEC was off for the whole window (cannot be verified by software)",
    )
    parser.add_argument("--json", dest="json_out", default=None, help="also write the statistics as JSON")
    args = parser.parse_args(argv)

    try:
        parsed = cg_serial.read_log(args.log)
    except OSError as exc:
        print(f"cannot read {args.log}: {exc}", file=sys.stderr)
        return 2

    if not parsed.pzem_samples:
        print("no #CG PZEM lines in this capture - nothing to build", file=sys.stderr)
        return 1

    indices = cg_serial.pzem_boot_indices(parsed)
    if args.boot is not None:
        if args.boot not in indices:
            print(
                f"--boot {args.boot} has no PZEM lines; capture contains boots {indices}",
                file=sys.stderr,
            )
            return 2
        samples = cg_serial.pzem_session(parsed, args.boot)
        configs = [cfg for cfg in parsed.pzem_configs if cfg.boot_index == args.boot]
    else:
        if len(indices) > 1:
            print(
                "capture contains PZEM lines from multiple boots "
                f"({indices}): capture one boot per window or select one with --boot N",
                file=sys.stderr,
            )
            return 1
        samples = cg_serial.pzem_session(parsed)
        configs = list(parsed.pzem_configs)

    link = cg_serial.pzem_link_stats(samples)
    stats = cg_serial.pzem_power_stats(samples)

    def rate_text(rate: float | None) -> str:
        if rate is None:
            return "n/a"
        return f"{link['n_ok']}/{link['n_total']} = {rate:.4f}"

    config = configs[0] if configs else None
    report = {
        "source_log": str(args.log),
        "boot": args.boot if args.boot is not None else indices[0],
        "config": None
        if config is None
        else {
            "slave": config.slave,
            "baud": config.baud,
            "framing": config.framing,
            "direction": config.direction,
            "read_only": config.read_only,
        },
        "n_total": link["n_total"],
        "n_ok": link["n_ok"],
        "n_error": link["n_error"],
        "success_rate": link["success_rate"],
        "success_rate_text": rate_text(link["success_rate"]),
        "error_rate": link["error_rate"],
        "error_rate_text": rate_text(link["error_rate"]),
        "status_counts": link["status_counts"],
        "attempts_counts": link["attempts_counts"],
        "crc_ok_count": link["crc_ok_count"],
        "crc_error_count": link["crc_error_count"],
        "timeout_count": link["timeout_count"],
        "exception_count": link["exception_count"],
        "uart_error_count": link["uart_error_count"],
        "first_uptime_ms": link["first_uptime_ms"],
        "last_uptime_ms": link["last_uptime_ms"],
        "duration_s": link["duration_s"],
        "min_duration_s": args.min_duration_s,
        "min_ok_fraction": args.min_ok_fraction,
        "interval_ms": link["interval_ms"],
        "gaps": link["gaps"],
        "gap_total_ms": link["gap_total_ms"],
        "stats": stats,
        "tec_off_confirmed": bool(args.tec_off_confirmed),
    }

    write_csv(pathlib.Path(args.out), cg_serial.pzem_csv_rows(samples))
    print(render(report))
    print()
    print(f"csv written: {args.out}")

    if args.summary_out:
        pathlib.Path(args.summary_out).write_text(render(report) + "\n", encoding="utf-8")
        print(f"summary written: {args.summary_out}")
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"json written: {args.json_out}")

    if not args.tec_off_confirmed:
        print("PZEM OFF WINDOW: NOT USABLE (TEC off was not confirmed by the operator)")
        return 1
    if config is None:
        print("PZEM OFF WINDOW: NOT USABLE (no #CG PZEM_CFG line - framing/provenance missing)")
        return 1
    if not config.read_only:
        print("PZEM OFF WINDOW: NOT USABLE (#CG PZEM_CFG does not state read_only=1)")
        return 1
    if link["duration_s"] < args.min_duration_s:
        print(
            f"PZEM OFF WINDOW: NOT USABLE (duration {link['duration_s']} s < "
            f"{args.min_duration_s} s)"
        )
        return 1
    if link["success_rate"] is None or link["success_rate"] < args.min_ok_fraction:
        fraction = "n/a" if link["success_rate"] is None else f"{link['success_rate']:.4f}"
        print(
            f"PZEM OFF WINDOW: NOT USABLE (valid-sample fraction {fraction} < "
            f"{args.min_ok_fraction})"
        )
        return 1
    print(
        f"PZEM OFF WINDOW: USABLE ({link['n_ok']}/{link['n_total']} valid, "
        f"{link['duration_s']} s >= {args.min_duration_s} s, TEC off operator-confirmed)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
