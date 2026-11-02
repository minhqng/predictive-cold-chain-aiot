"""ColdGuard plant repeatability analysis (A-W07-04).

Standard library only, host-only: nothing here drives or reads hardware. It
turns recorded bench captures into the per-outcome statistics week 07 asks for
and, just as importantly, refuses to report repeatability that the data cannot
support.

Why the representations are named (docs/01 §20):

* ``tmean_chamber3_v0`` is mean(T1,T2,T3) - the chamber-air definition Doc 01
  freezes. It is computed because it is the canonical one, not because T2's
  physical position is settled.
* ``tmean_t2excluded_v0`` is mean(T1,T3). The committed H8 capture labels the
  T2 probe ``HOT_SIDE``, and during cooling T2 rises while T1/T3/T4 fall, so
  the two definitions do not describe the same physical quantity. Publishing a
  single unlabelled "Tmean" would hide exactly that.
* ``tmean_all4_v0`` is mean(T1,T2,T3,T4) and is reported only as a sensitivity
  check: it changes the answer without settling the dispute.

Every slope names its representation, window and fit method, because docs/01
20.5 calls a bare ``dT/dt`` ambiguous. Spread uses the **sample** formula
(n-1) and says so (docs/01 §20.4). ``nan``, missing values and non-``OK``
statuses are excluded from means and counted, never treated as zero.

Repeatability is reported only when at least ``--min-runs`` valid runs of the
same phase exist. With fewer, the verdict is ``INSUFFICIENT_RUNS`` together with
how many more runs are needed - the alternative is a number that looks like a
measurement and is really a guess.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import statistics
import sys

SCHEMA_NOTE = "repeatability-v0"
MIN_RUNS_DEFAULT = 3
SLOPE_WINDOW_SAMPLES = 120
SLOPE_METHOD = "trailing_window_least_squares"

REPRESENTATIONS = {
    "tmean_chamber3_v0": ("t1_c", "t2_c", "t3_c"),
    "tmean_t2excluded_v0": ("t1_c", "t3_c"),
    "tmean_all4_v0": ("t1_c", "t2_c", "t3_c", "t4_c"),
}

# Outcomes whose spread across runs is the actual A-W07-04 question.
OUTCOMES = (
    "start_c",
    "end_c",
    "delta_c",
    "slope_c_per_min",
    "whole_phase_slope_c_per_min",
    "minutes_to_1c",
    "minutes_to_2c",
    "mean_current_a",
    "peak_current_a",
    "mean_power_w",
    "energy_wh",
    "valid_sample_fraction",
)


class AnalysisError(RuntimeError):
    pass


def _number(row: dict[str, str], key: str) -> float | None:
    """A reading is usable only when its status says so.

    `nan`, an empty cell and a non-OK status are three different ways of having
    no evidence; all three return None rather than a number.
    """
    raw = (row.get(key) or "").strip()
    if raw in ("", "nan", "NaN", "UNAVAILABLE", "UNRECORDED"):
        return None
    status_key = _status_key(row, key)
    if status_key is not None and (row.get(status_key) or "").strip() not in ("OK", ""):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _status_key(row: dict[str, str], key: str) -> str | None:
    """The status column that qualifies this value column, if the capture has one.

    `t1_c` is gated by `t1_status`, `current_a` by `current_status`. A column
    with no matching status column is used as recorded, and the value column is
    never its own status: that mis-read made every `device_ms` look unusable and
    silently emptied the slope input.
    """
    candidate = f"{key.split('_')[0]}_status"
    if candidate == key or candidate not in row:
        return None
    return candidate


def tmean(row: dict[str, str], representation: str) -> tuple[float | None, int, int]:
    """Return (mean, usable_count, term_count) for one row.

    A partial mean is not the same quantity as the full one, so usable_count is
    returned alongside and callers must treat a shortfall as its own condition.
    """
    terms = REPRESENTATIONS[representation]
    values = [v for v in (_number(row, t) for t in terms) if v is not None]
    if not values:
        return None, 0, len(terms)
    return sum(values) / len(values), len(values), len(terms)


def _least_squares(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    n = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    return (n * sxy - sx * sy) / denom


def trailing_slope_c_per_min(points: list[tuple[float, float]],
                             window: int = SLOPE_WINDOW_SAMPLES) -> float | None:
    """Slope over the trailing window of the phase, not the leading edge.

    The window is in samples at the capture cadence; a phase shorter than the
    window uses what it has and the sample count is reported, so the number is
    never detached from how it was made.
    """
    if len(points) < 2:
        return None
    tail = points[-window:] if len(points) > window else points
    return _least_squares(tail)


def minutes_to_first_1c_drop(points: list[tuple[float, float]],
                             threshold_c: float = 1.0) -> float | None:
    """Minutes from phase start until the representation moves `threshold_c`.

    A cooling step passes a positive threshold (fall); a recovery step passes a
    negative one (rise), which is why the number is an argument and not a hidden
    constant. None means the move never happened inside the phase - a result, not
    a gap, and callers must not render it as 0.
    """
    if len(points) < 2:
        return None
    start = points[0][1]
    base_t = points[0][0]
    for t, value in points:
        if (value <= start - threshold_c if threshold_c > 0.0
                else value >= start - threshold_c):
            return round(t - base_t, 4)
    return None


def is_cooling_row(row: dict[str, str]) -> bool:
    """The action reference is applied duty, not the bench stage label.

    Using the stage would fold the post-action cooldown into "cooling" and then
    call its rebound the cooling response, which is exactly what docs/01 §20.6
    warns about: recovery is a different phase measured after the action ended.
    """
    return (_number(row, "pwm_applied_permille") or 0.0) > 0.0


def read_rows(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise AnalysisError(f"{path} has no header row")
        needed = {"device_ms", "pwm_applied_permille", "current_a"}
        missing = needed - set(reader.fieldnames)
        if missing:
            raise AnalysisError(f"{path} is missing required columns: {sorted(missing)}")
        return [row for row in reader]


def split_phases(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Contiguous cooling blocks split the capture into before / during / after.

    A capture with no cooling block has a baseline only: that is an honest
    passive warm-up candidate and is labelled as such rather than silently
    treated as a cooling step.
    """
    marks = [is_cooling_row(row) for row in rows]
    if not any(marks):
        return {"baseline": rows, "cooling": [], "recovery": []}
    first = marks.index(True)
    last = len(marks) - 1 - marks[::-1].index(True)
    return {
        "baseline": rows[:first],
        "cooling": rows[first:last + 1],
        "recovery": rows[last + 1:],
    }


def _time_to_move(points: list[tuple[float, float]], phase: str,
                  threshold_c: float = 1.0) -> float | None:
    """When the representation has moved `threshold_c` in the direction of the phase.

    Cooling is a fall, recovery is a rise, and a baseline has no direction to
    answer, so it reports None instead of a number that implies an action that
    never happened.
    """
    if phase == "cooling":
        return minutes_to_first_1c_drop(points, threshold_c)
    if phase == "recovery":
        return minutes_to_first_1c_drop(points, -threshold_c)
    return None


def phase_metrics(rows: list[dict[str, str]], phase: str,
                  representation: str) -> dict[str, object]:
    points: list[tuple[float, float]] = []
    usable = 0
    for row in rows:
        value, count, terms = tmean(row, representation)
        if value is None:
            continue
        if count == terms:
            usable += 1
        t = _number(row, "device_ms")
        points.append(((t or 0.0) / 60000.0, value))
    if len(points) < 2:
        return {"phase": phase, "usable": False, "samples": len(points),
                "reason": "FEWER_THAN_TWO_USABLE_SAMPLES"}

    currents = [v for v in (_number(r, "current_a") for r in rows) if v is not None]
    powers = [v for v in (_number(r, "power_w") for r in rows) if v is not None]
    doors = [(r.get("door_open") or "").strip() for r in rows]
    durations_min = points[-1][0] - points[0][0]
    energies = [v for v in (_number(r, "energy_wh") for r in rows) if v is not None]
    slope = trailing_slope_c_per_min(points)
    whole = _least_squares(points)
    return {
        "phase": phase,
        "usable": True,
        "representation": representation,
        "slope_definition": f"{representation}/{SLOPE_WINDOW_SAMPLES}samples/"
                            f"{SLOPE_METHOD}_v0",
        "samples": len(points),
        "full_term_samples": usable,
        "partial_term_samples": len(points) - usable,
        "duration_min": round(durations_min, 4),
        "start_c": round(points[0][1], 4),
        "end_c": round(points[-1][1], 4),
        "min_c": round(min(p[1] for p in points), 4),
        "max_c": round(max(p[1] for p in points), 4),
        "delta_c": round(points[-1][1] - points[0][1], 4),
        "slope_c_per_min": None if slope is None else round(slope, 6),
        "whole_phase_slope_c_per_min": None if whole is None else round(whole, 6),
        "minutes_to_1c": _time_to_move(points, phase),
        "minutes_to_2c": _time_to_move(points, phase, 2.0),
        "mean_current_a": None if not currents else round(sum(currents) / len(currents), 4),
        "peak_current_a": None if not currents else round(max(currents), 4),
        "mean_power_w": None if not powers else round(sum(powers) / len(powers), 4),
        "energy_wh": None if not energies else round(energies[-1] - energies[0], 4),
        "door_open_tokens": {token or "MISSING": doors.count(token) for token in set(doors)},
        "valid_sample_fraction": round(usable / len(points), 4),
    }


def summarize(outcomes: list[float], label: str) -> dict[str, object]:
    """Sample statistics (n-1) over one outcome across runs, with no hiding."""
    out: dict[str, object] = {"outcome": label, "n": len(outcomes)}
    if not outcomes:
        out["status"] = "NO_SAMPLES"
        return out
    out["status"] = "OK"
    out["mean"] = round(statistics.fmean(outcomes), 6)
    out["min"] = round(min(outcomes), 6)
    out["max"] = round(max(outcomes), 6)
    out["range"] = round(max(outcomes) - min(outcomes), 6)
    if len(outcomes) >= 2:
        sd = statistics.stdev(outcomes)
        out["sd_sample"] = round(sd, 6)
        out["cv_pct"] = (
            round(100.0 * sd / statistics.fmean(outcomes), 4)
            if statistics.fmean(outcomes) != 0 else None
        )
        if out["cv_pct"] is None:
            out["cv_note"] = "CV undefined: the mean is zero, so a ratio has no meaning"
    else:
        out["sd_sample"] = None
        out["cv_pct"] = None
        out["cv_note"] = "spread needs at least two runs"
    return out


def analyze(paths: list[pathlib.Path], representation: str,
            min_runs: int) -> dict[str, object]:
    runs: list[dict[str, object]] = []
    for path in paths:
        phases = split_phases(read_rows(path))
        per_phase = {}
        for phase, rows in phases.items():
            if not rows:
                continue
            per_phase[phase] = phase_metrics(rows, phase, representation)
        runs.append({
            "capture": path.as_posix(),
            "phases": per_phase,
            "passive_candidate": len(phases["cooling"]) == 0,
            "cooling_candidate": len(phases["cooling"]) > 0,
        })

    usable_by_phase: dict[str, list[dict[str, object]]] = {}
    for run in runs:
        for phase, metrics in run["phases"].items():
            if metrics.get("usable"):
                usable_by_phase.setdefault(phase, []).append(metrics)

    phases_out: dict[str, object] = {}
    for phase, samples in usable_by_phase.items():
        stats = {}
        for outcome in OUTCOMES:
            values = [s[outcome] for s in samples
                      if isinstance(s.get(outcome), (int, float))]
            stats[outcome] = summarize(values, outcome)
        counts = [s["samples"] for s in samples]
        verdict = {
            "runs": len(samples),
            "min_runs_required": min_runs,
            "additional_runs_needed": max(0, min_runs - len(samples)),
            "status": "REPEATABILITY_COMPUTED" if len(samples) >= min_runs
                      else "INSUFFICIENT_RUNS",
        }
        phases_out[phase] = {
            "runs": samples,
            "statistics": stats,
            "samples_per_run": counts,
            "verdict": verdict,
        }

    return {
        "analysis": SCHEMA_NOTE,
        "representation": representation,
        "representation_terms": list(REPRESENTATIONS[representation]),
        "slope_definition": f"{representation}/{SLOPE_WINDOW_SAMPLES}samples/"
                            f"{SLOPE_METHOD}_v0",
        "spread_formula": "sample (n-1)",
        "runs_read": len(runs),
        "runs": runs,
        "phases": phases_out,
        "verdict": _overall_verdict(phases_out, runs),
        "notes": [
            "This is host analysis of recorded captures. It does not "
            "reproduce, energize or verify any physical action.",
            "The chosen representation is a contract question, not a "
            "measurement question: see the module docstring.",
            "A capture with no cooling block is a passive warm-up candidate "
            "only; it is never counted as a cooling step.",
        ],
    }


def _overall_verdict(phases: dict[str, object], runs: list[dict[str, object]]) -> dict[str, object]:
    cooling = phases.get("cooling")
    baseline = phases.get("baseline")
    def _status(block: object) -> str:
        if not isinstance(block, dict):
            return "NO_DATA"
        return block["verdict"]["status"]
    return {
        "cooling_step_runs": _status(cooling),
        "passive_warmup_runs": _status(baseline),
        "plant_variation_reportable": all(
            _status(p) == "REPEATABILITY_COMPUTED" for p in (cooling, baseline)),
        "captures_with_no_cooling_block": sum(1 for r in runs if r["passive_candidate"]),
    }


def overlay_rows(report: dict[str, object]) -> list[tuple[object, ...]]:
    """Trajectory overlay rows: header plus one row per (run, phase, sample)."""
    rows: list[tuple[object, ...]] = [
        ("run", "phase", "sample_index", "elapsed_min", "tmean_c", "representation")]
    for run in report["runs"]:
        source = pathlib.Path(run["capture"])  # type: ignore[arg-type]
        phases = split_phases(read_rows(source))
        for phase, metrics in run["phases"].items():  # type: ignore[union-attr]
            if not metrics.get("usable"):
                continue
            for index, (minutes, value) in enumerate(
                    _series_points(phases[phase], metrics["representation"])):
                rows.append((source.name, phase, index, round(minutes, 4),
                             round(value, 4), metrics["representation"]))
    return rows


def write_overlay_csv(path: pathlib.Path, report: dict[str, object]) -> None:
    """Write the trajectory overlay with LF endings, byte-reproducible.

    The default csv dialect emits CRLF, which would make a hash pin platform
    dependent.
    """
    import csv as csv_module
    import io

    buffer = io.StringIO()
    csv_module.writer(buffer, lineterminator="\n").writerows(overlay_rows(report))
    path.write_bytes(buffer.getvalue().encode("utf-8"))


def _series_points(rows: list[dict[str, str]],
                   representation: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for row in rows:
        value, count, terms = tmean(row, representation)
        if value is None or count != terms:
            continue
        t = _number(row, "device_ms") or 0.0
        points.append((t / 60000.0, value))
    return points


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("captures", nargs="+", type=pathlib.Path)
    parser.add_argument("--representation", default="tmean_chamber3_v0",
                        choices=sorted(REPRESENTATIONS))
    parser.add_argument("--min-runs", type=int, default=MIN_RUNS_DEFAULT)
    parser.add_argument("--json", dest="json_out", type=pathlib.Path)
    parser.add_argument("--csv", dest="csv_out", type=pathlib.Path,
                        help="write the trajectory overlay")
    args = parser.parse_args(argv)

    report = analyze(args.captures, args.representation, args.min_runs)
    for phase, block in sorted(report["phases"].items()):
        verdict = block["verdict"]
        print(f"phase={phase} runs={verdict['runs']} status={verdict['status']}")
        for outcome in OUTCOMES:
            stats = block["statistics"][outcome]
            if stats["status"] != "OK":
                continue
            print(f"  {outcome}: n={stats['n']} mean={stats['mean']} "
                  f"sd_sample={stats['sd_sample']} cv_pct={stats['cv_pct']} "
                  f"min={stats['min']} max={stats['max']}")
    print("verdict=" + json.dumps(report["verdict"], sort_keys=True))

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
        print(f"json={args.json_out}")
    if args.csv_out is not None:
        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        write_overlay_csv(args.csv_out, report)
        print(f"csv={args.csv_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
