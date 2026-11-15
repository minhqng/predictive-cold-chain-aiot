"""ColdGuard W05 1 Hz timing study (A-W05-03; standard library only).

Reads a serial capture containing ``#CG TELEM`` lines and reports the *measured*
cadence of the telemetry stream and of the producers behind it. This is the tool
that decides whether "approximately 1 Hz" is true of a real capture, instead of
being a claim copied from a config macro.

What it measures, and why each number is here:

* Frame gap (``uptime_ms`` delta between accepted frames): mean, median, p50/
  p95/p99, max, and the count outside a tolerance band. ``uptime_ms`` is the
  device's own monotonic clock, so this is device cadence, not host arrival
  spacing. Host arrival spacing would include serial buffering and cannot be
  substituted for it (docs/01 2209-2213).
* ``seq`` continuity: duplicates and gaps. The backend dedup key is
  (device_id, boot_id, seq) (docs/02 633-646), so a duplicate is a contract
  break and a gap is a lost frame. The W05 formatter deliberately lets a refused
  frame consume its seq, so gaps here are expected when a line was too long, and
  they are reported rather than hidden.
* Producer advance: how many consecutive frames carried the same ``thermal_seq``
  or ``power_seq``. A producer that stops publishing while the stream keeps
  running is the failure mode A-W05-01 exists to make visible.
* Read-failure counts by status token, per source, so a warm-up run that lost
  DS18B20 or PZEM reads is quantified instead of noticed later in a plot.
* Quality token tallies, including whether any frame collapsed to INVALID or
  UNKNOWN and why.

It writes nothing unless asked, and it never synthesises a frame. A capture with
too few accepted frames to characterise is reported as insufficient evidence
rather than given a number anyway.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cg_telemetry_schema import (  # noqa: E402
    AGE_FIELDS,
    AGE_SATURATION_SENTINEL,
    QUALITY_VOCABULARY,
    TelemetryError,
    parse_line,
    read_capture,
)

DEFAULT_TARGET_PERIOD_MS = 1000
DEFAULT_TOLERANCE_MS = 150


def _clock_skew_frames(records) -> int:
    """Frames whose age is the saturation sentinel.

    The formatter writes 2^64-1 when an observation is timestamped after the
    frame's own clock, i.e. the two disagreed. That is not an age, so it must
    never be averaged into the distribution: it is counted here as a named,
    separately reported condition.
    """
    count = 0
    for record in records:
        if any(record.fields.get(name) == AGE_SATURATION_SENTINEL for name in AGE_FIELDS):
            count += 1
    return count


def _percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile. Deliberately not interpolated: a report that
    quotes p95 should name an observation that actually happened."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), int(-(-fraction * len(ordered) // 1))))
    return float(ordered[rank - 1])


def _gap_stats(gaps: list[int]) -> dict[str, object]:
    if not gaps:
        return {"count": 0}
    return {
        "count": len(gaps),
        "min_ms": min(gaps),
        "max_ms": max(gaps),
        "mean_ms": round(statistics.fmean(gaps), 3),
        "median_ms": round(statistics.median(gaps), 3),
        "p95_ms": _percentile(gaps, 0.95),
        "p99_ms": _percentile(gaps, 0.99),
        "stdev_ms": round(statistics.pstdev(gaps), 3) if len(gaps) > 1 else 0.0,
    }


def analyse(lines, target_period_ms: int = DEFAULT_TARGET_PERIOD_MS,
            tolerance_ms: int = DEFAULT_TOLERANCE_MS) -> dict[str, object]:
    """Return the timing report for one capture (path, text or line list)."""
    if isinstance(lines, (str, bytes)) or hasattr(lines, "read_text") or isinstance(
        lines, pathlib.PurePath
    ):
        records, capture_report = read_capture(lines)
    else:
        records, capture_report = read_capture(list(lines))

    accepted = [r for r in records]
    gaps: list[int] = []
    late = 0
    early = 0
    nonpositive = 0
    jitter_rows: list[dict[str, object]] = []

    seqs = [int(r.fields["seq"]) for r in accepted if isinstance(r.fields.get("seq"), int)]
    if len(seqs) == len(accepted) and seqs:
        duplicate_seqs = sorted({s for s in seqs if seqs.count(s) > 1})
        seq_gaps = 0
        for previous, current in zip(seqs, seqs[1:]):
            if current > previous + 1:
                seq_gaps += current - previous - 1
    else:
        # A schema-1 capture carries no per-boot sequence at all. "0 duplicates"
        # would read as a clean dedup key; the truth is that the key was never
        # sent, so the measurement does not exist.
        duplicate_seqs = None
        seq_gaps = None

    thermal_seq = [r.fields.get("thermal_seq") for r in accepted]
    power_seq = [r.fields.get("power_seq") for r in accepted]

    def _stall_runs(values: list[object]) -> tuple[int | None, int | None]:
        """(frames that repeated the previous producer sequence, longest such run).

        None means the field was absent - a schema-1 capture carries no producer
        sequences - which is not the same measurement as "never repeated".
        Reporting an absent field as 0 would turn unknown into a pass.
        """
        if all(value is None for value in values):
            return None, None
        repeats = 0
        run = 0
        longest = 0
        for previous, current in zip(values, values[1:]):
            if previous is not None and current is not None and current == previous:
                repeats += 1
                run += 1
                longest = max(longest, run)
            else:
                run = 0
        return repeats, longest

    thermal_repeats, thermal_longest = _stall_runs(thermal_seq)
    power_repeats, power_longest = _stall_runs(power_seq)

    status_tally: dict[str, dict[str, int]] = {}
    for record in accepted:
        for field in (
            "t_inside_status",
            "voltage_status",
            "current_status",
            "power_status",
            "door_status",
            "thermal_quality",
            "electrical_quality",
            "door_quality",
            "environment_quality",
            "quality",
            "health",
            "cooling_applied",
            "cooling_evidence",
        ):
            value = record.fields.get(field)
            if isinstance(value, str):
                status_tally.setdefault(field, {})
                status_tally[field][value] = status_tally[field].get(value, 0) + 1

    for index, record in enumerate(accepted):
        uptime = record.fields.get("uptime_ms")
        if not isinstance(uptime, int):
            continue
        gap = None
        if index > 0:
            previous_uptime = accepted[index - 1].fields.get("uptime_ms")
            if isinstance(previous_uptime, int):
                gap = uptime - previous_uptime
                gaps.append(gap)
                if gap <= 0:
                    nonpositive += 1
                elif gap > target_period_ms + tolerance_ms:
                    late += 1
                elif gap < target_period_ms - tolerance_ms:
                    early += 1
        jitter_rows.append(
            {
                "line_index": record.line_index,
                "seq": record.fields.get("seq", ""),
                "uptime_ms": uptime,
                "gap_ms": "" if gap is None else gap,
                "thermal_seq": record.fields.get("thermal_seq", ""),
                "power_seq": record.fields.get("power_seq", ""),
                "thermal_age_ms": record.fields.get("thermal_age_ms", ""),
                "power_age_ms": record.fields.get("power_age_ms", ""),
                "door_age_ms": record.fields.get("door_age_ms", ""),
                "health": record.fields.get("health", ""),
                "quality": record.fields.get("quality", ""),
            }
        )

    duration_ms = 0
    if len(accepted) >= 2:
        first = accepted[0].fields.get("uptime_ms")
        last = accepted[-1].fields.get("uptime_ms")
        if isinstance(first, int) and isinstance(last, int):
            duration_ms = last - first

    sufficient = len(accepted) >= 10 and bool(gaps)
    report: dict[str, object] = {
        "target_period_ms": target_period_ms,
        "tolerance_ms": tolerance_ms,
        "capture": {
            "lines_total": capture_report["lines_total"],
            "telemetry_records": capture_report["records"],
            "ignored_lines": capture_report["ignored"],
            "rejected_lines": len(capture_report["rejected"]),
            "reject_reasons": [r["reason"] for r in capture_report["rejected"][:20]],
        },
        "clock_skew_frames": _clock_skew_frames(accepted),
        "cadence": {
            "accepted_frames": len(accepted),
            "duration_ms": duration_ms,
            "gaps": _gap_stats(gaps),
            # The observed values, not a binned approximation: the W04 pilot
            # showed the stream alternating between two spacing values, which a
            # mean alone hides.
            "gap_histogram": {str(value): gaps.count(value) for value in sorted(set(gaps))},
            "late_frames": late,
            "early_frames": early,
            "nonpositive_gaps": nonpositive,
            # (frames - 1) intervals over the elapsed span. Counting the frames
            # themselves inflates the rate by one interval: 12 frames spread over
            # 11 s is 1.0 Hz, not 1.09 Hz.
            "frames_per_second": (
                round(len(gaps) / (duration_ms / 1000.0), 4) if duration_ms > 1000 else None
            ),
        },
        "identity": {
            "seq_frames": len(seqs),
            "seq_duplicate_count": len(duplicate_seqs) if duplicate_seqs is not None else None,
            "seq_duplicates": duplicate_seqs[:20] if duplicate_seqs is not None else None,
            "seq_missing": seq_gaps,
        },
        "producers": {
            "thermal_repeat_frames": thermal_repeats,
            "thermal_longest_repeat_run": thermal_longest,
            "power_repeat_frames": power_repeats,
            "power_longest_repeat_run": power_longest,
        },
        "token_tally": status_tally,
        "verdict": (
            "MEASURED"
            if sufficient
            else f"INSUFFICIENT_EVIDENCE ({len(accepted)} accepted frames; "
            f"{len(gaps)} gaps)"
        ),
    }
    report["jitter_rows"] = jitter_rows
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("capture", type=pathlib.Path, help="serial capture containing #CG TELEM")
    parser.add_argument("--period-ms", type=int, default=DEFAULT_TARGET_PERIOD_MS)
    parser.add_argument("--tolerance-ms", type=int, default=DEFAULT_TOLERANCE_MS)
    parser.add_argument("--jitter-csv", type=pathlib.Path,
                        help="write the per-frame gap table here")
    parser.add_argument("--json", dest="json_out", type=pathlib.Path,
                        help="write the whole report as JSON here")
    args = parser.parse_args(argv)

    try:
        report = analyse(args.capture, args.period_ms, args.tolerance_ms)
    except TelemetryError as exc:  # a whole unreadable capture is a hard error
        print(f"ANALYSIS_FAILED {exc}", file=sys.stderr)
        return 2

    jitter_rows = report.pop("jitter_rows")
    if args.jitter_csv is not None:
        written = 0
        with args.jitter_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(jitter_rows[0].keys()),
                                    lineterminator="\n") if jitter_rows else None
            if writer is not None:
                writer.writeheader()
                for row in jitter_rows:
                    writer.writerow(row)
                written = len(jitter_rows)
        print(f"jitter_csv={args.jitter_csv} rows={written}")
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
        print(f"json={args.json_out}")

    cadence = report["cadence"]
    gaps = cadence["gaps"]
    print(f"verdict={report['verdict']}")
    print(f"clock_skew_frames={report['clock_skew_frames']} "
          f"(age reported as the 2^64-1 sentinel: observation stamped after the frame clock)")
    print(f"accepted_frames={cadence['accepted_frames']} duration_ms={cadence['duration_ms']}")
    if gaps.get("count"):
        print(
            f"gap_ms mean={gaps['mean_ms']} median={gaps['median_ms']} p95={gaps['p95_ms']} "
            f"max={gaps['max_ms']} min={gaps['min_ms']} stdev={gaps['stdev_ms']}"
        )
    print(
        f"late={cadence['late_frames']} early={cadence['early_frames']} "
        f"nonpositive={cadence['nonpositive_gaps']} fps={cadence['frames_per_second']}"
    )
    identity = report["identity"]
    print(
        f"seq_frames={identity['seq_frames']} "
        f"seq_duplicates={'ABSENT (no seq in this schema)' if identity['seq_duplicate_count'] is None else identity['seq_duplicate_count']} "
        f"seq_missing={'ABSENT' if identity['seq_missing'] is None else identity['seq_missing']}"
    )
    producers = report["producers"]
    print(
        f"thermal_repeat_frames={producers['thermal_repeat_frames']} "
        f"power_repeat_frames={producers['power_repeat_frames']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
