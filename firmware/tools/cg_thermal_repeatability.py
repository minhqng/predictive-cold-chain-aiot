"""ColdGuard plant repeatability analysis (A-W07-02/03/04).

Standard library only, host-only: nothing here drives or reads hardware. It turns
recorded bench captures into the per-outcome statistics week 07 asks for and, just
as importantly, refuses to report repeatability the data cannot support.

Representations are named, never implied (docs/01 §20.1, §20.5)

The 2026-11-02 operator-confirmed as-built geometry is:

    T1 = chamber CENTER          T2 = TEC HOT_SIDE
    T3 = chamber BOTTOM          T4/SPARE = near the CHAMBER DOOR

so the three chamber-air probes are T1, T3 and T4, and T2 sits on hot metal. That
makes the choice of mean a physical question with a measurable answer, not a style
preference:

* ``tmean_airroles_v0`` = mean(T1,T3,T4) - the as-built chamber-air mean and the
  primary statistic for this rig.
* ``tmean_chamber3_v0`` = mean(T1,T2,T3) - what docs/01 §20.1 writes literally,
  which on this rig averages a hot-side surface into an air temperature. Kept
  because it is the canonical text, and flagged ``includes_hot_side``.
* ``tmean_t2excluded_v0`` = mean(T1,T3) - the two-probe degraded mean.
* ``tmean_all4_v0`` - sensitivity check only.

On the single committed run the hot-side-contaminated mean reports -2.56 C over the
driven block where the role-correct air mean is several times larger: the
definition, not the chamber, moves the number. Nothing picks a winner silently -
every artifact carries ``representation``, ``representation_terms``,
``representation_roles`` and ``includes_hot_side``.

Statistics discipline

* a partial mean (one term missing) is not the same quantity, so partial rows are
  excluded from a phase series and counted in ``partial_term_rows``
  (docs/01 517-530, 2312-2318);
* a reading whose status column says anything other than ``OK`` is excluded;
* a reading whose status column exists but is EMPTY is used and counted as
  ``unqualified`` - the H8 capture left ``current_status`` and ``voltage_status``
  empty on all 957 rows, so its electrical figures are values with no recorded
  validity, and ``electrical_status_recorded`` says so;
* a row with no usable applied-duty value is ``undetermined`` and joins neither the
  baseline nor the recovery segment: defaulting it to "off" would invent passive
  run time;
* every slope names representation, window and method, and the trailing-window slope
  is never called "the cooling slope" - on a curve that bottoms out and rebounds it
  can be positive during a cooling phase;
* spread uses the sample (n-1) formula and says so (docs/01 §20.4);
* fewer than ``--min-runs`` valid runs of a phase yields ``INSUFFICIENT_RUNS`` plus
  the number still needed, never a fabricated distribution.
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

AS_BUILT_ROLES = {"t1_c": "CHAMBER_CENTER", "t2_c": "TEC_HOT_SIDE",
                  "t3_c": "CHAMBER_BOTTOM", "t4_c": "CHAMBER_NEAR_DOOR"}

REPRESENTATIONS: dict[str, dict[str, object]] = {
    "tmean_airroles_v0": {"terms": ("t1_c", "t3_c", "t4_c"), "includes_hot_side": False},
    "tmean_chamber3_v0": {"terms": ("t1_c", "t2_c", "t3_c"), "includes_hot_side": True},
    "tmean_t2excluded_v0": {"terms": ("t1_c", "t3_c"), "includes_hot_side": False},
    "tmean_all4_v0": {"terms": ("t1_c", "t2_c", "t3_c", "t4_c"), "includes_hot_side": True},
}

OUTCOMES = (
    "start_c", "end_c", "delta_c", "min_c", "max_c",
    "slope_c_per_min", "whole_phase_slope_c_per_min",
    "minutes_to_1c", "minutes_to_2c",
    "mean_current_a", "peak_current_a", "mean_power_w", "energy_wh",
    "valid_sample_fraction",
)

_MISSING_VALUE = ("", "nan", "NaN", "UNAVAILABLE", "UNRECORDED", "null")


class AnalysisError(RuntimeError):
    pass


def terms_of(representation: str) -> tuple[str, ...]:
    return tuple(REPRESENTATIONS[representation]["terms"])  # type: ignore[arg-type]


def includes_hot_side(representation: str) -> bool:
    return bool(REPRESENTATIONS[representation]["includes_hot_side"])


def _status_key(row: dict[str, str], key: str) -> str | None:
    """The status column qualifying a value column, if this capture has one.

    A column is never its own status: that mis-read once made every ``device_ms``
    look unusable and silently emptied a slope.
    """
    candidate = f"{key.split('_')[0]}_status"
    if candidate == key or candidate not in row:
        return None
    return candidate


def reading(row: dict[str, str], key: str) -> tuple[float | None, str]:
    """(value, state) where state is ok / unqualified / invalid / absent.

    `ok` requires a recorded OK, not the absence of a complaint: a field with no status
    column is unqualified, because nothing in the capture ever vouched for it.
    """
    raw = (row.get(key) or "").strip()
    if raw in _MISSING_VALUE:
        return None, "absent"
    status_key = _status_key(row, key)
    if status_key is None:
        # No status column exists for this field at all. That is not the same as a
        # recorded OK: power and energy are carried by this capture without any
        # validity field, and reading their silence as "fine" would qualify a whole
        # column of numbers that nothing ever checked.
        state = "unqualified"
    else:
        status = (row.get(status_key) or "").strip()
        if status == "":
            state = "unqualified"
        elif status != "OK":
            return None, "invalid"
        else:
            state = "ok"
    try:
        return float(raw), state
    except ValueError:
        return None, "invalid"


def number(row: dict[str, str], key: str) -> float | None:
    """The usable value of a field. Use `reading` whenever validity matters."""
    value, state = reading(row, key)
    return value if state in ("ok", "unqualified") else None


def tmean(row: dict[str, str], representation: str) -> tuple[float | None, int, int]:
    """(mean, usable_count, term_count); a shortfall means it is not the full quantity."""
    terms = terms_of(representation)
    values = [value for value in (number(row, term) for term in terms) if value is not None]
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
    """Recent motion over the trailing window - not a phase summary."""
    if len(points) < 2:
        return None
    tail = points[-window:] if len(points) > window else points
    return _least_squares(tail)


def minutes_to_threshold_drop(points: list[tuple[float, float]],
                              threshold_c: float = 1.0) -> float | None:
    """Minutes until the representation moves `threshold_c`; None if it never does."""
    if len(points) < 2:
        return None
    start = points[0][1]
    base_t = points[0][0]
    for t, value in points:
        if (value <= start - threshold_c if threshold_c > 0.0
                else value >= start - threshold_c):
            return round(t - base_t, 4)
    return None


def _time_to_move(points: list[tuple[float, float]], phase: str,
                  threshold_c: float = 1.0) -> float | None:
    if phase == "cooling":
        return minutes_to_threshold_drop(points, threshold_c)
    if phase == "recovery":
        return minutes_to_threshold_drop(points, -threshold_c)
    return None


def phase_of(row: dict[str, str]) -> str:
    """cooling / off / undetermined, keyed on applied duty (docs/01 §20.6)."""
    duty, state = reading(row, "pwm_applied_permille")
    if state in ("absent", "invalid"):
        return "undetermined"
    return "cooling" if (duty or 0.0) > 0.0 else "off"


def read_rows(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise AnalysisError(f"{path} has no header row")
        missing = {"device_ms", "pwm_applied_permille", "current_a"} - set(reader.fieldnames)
        if missing:
            raise AnalysisError(f"{path} is missing required columns: {sorted(missing)}")
        return [row for row in reader]


def split_phases(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    marks = [phase_of(row) == "cooling" for row in rows]
    if not any(marks):
        kept = [row for row in rows if phase_of(row) != "undetermined"]
        return {"baseline": kept, "cooling": [], "recovery": [],
                "undetermined": [row for row in rows if phase_of(row) == "undetermined"]}
    first = marks.index(True)
    last = len(marks) - 1 - marks[::-1].index(True)
    middle = rows[first:last + 1]

    def pending(segment: list[dict[str, str]]) -> list[dict[str, str]]:
        return [row for row in segment if phase_of(row) == "undetermined"]

    def usable(segment: list[dict[str, str]]) -> list[dict[str, str]]:
        return [row for row in segment if phase_of(row) != "undetermined"]

    return {
        "baseline": usable(rows[:first]),
        # The driven span is defined by its first and last cooling row, but a row inside
        # it that carries no applied duty is not evidence of the driven phase. Leaving it
        # in `cooling` while also listing it under `undetermined` counted the same row
        # twice; the four lists must partition the capture.
        "cooling": usable(middle),
        "recovery": usable(rows[last + 1:]),
        "undetermined": (pending(rows[:first]) + pending(middle)
                         + pending(rows[last + 1:])),
    }


def _phase_points(rows: list[dict[str, str]],
                  representation: str) -> tuple[list[tuple[float, float]], dict[str, int]]:
    points: list[tuple[float, float]] = []
    tallies = {"partial_term_rows": 0, "no_term_rows": 0, "unqualified_rows": 0}
    for row in rows:
        value, count, terms = tmean(row, representation)
        if value is None:
            tallies["no_term_rows"] += 1
            continue
        if count != terms:
            tallies["partial_term_rows"] += 1
            continue
        if any(reading(row, term)[1] == "unqualified" for term in terms_of(representation)):
            tallies["unqualified_rows"] += 1
        elapsed = number(row, "device_ms")
        points.append(((elapsed or 0.0) / 60000.0, value))
    return points, tallies


def _column_stats(rows: list[dict[str, str]],
                  key: str) -> tuple[list[float], int, int]:
    usable: list[float] = []
    unqualified = invalid = 0
    for row in rows:
        value, state = reading(row, key)
        if state == "unqualified":
            unqualified += 1
        if state == "invalid":
            invalid += 1
        if state in ("ok", "unqualified") and value is not None:
            usable.append(value)
    return usable, unqualified, invalid


def phase_metrics(rows: list[dict[str, str]], phase: str,
                  representation: str) -> dict[str, object]:
    points, tallies = _phase_points(rows, representation)
    base: dict[str, object] = {
        "phase": phase,
        "representation": representation,
        "representation_terms": list(terms_of(representation)),
        "representation_roles": [AS_BUILT_ROLES[t] for t in terms_of(representation)],
        "includes_hot_side": includes_hot_side(representation),
        "rows_read": len(rows),
        **tallies,
    }
    if len(points) < 2:
        return {**base, "usable": False, "samples": len(points),
                "skipped_rows": len(rows) - len(points),
                "reason": "FEWER_THAN_TWO_FULL_TERM_SAMPLES"}

    currents, current_unqualified, current_invalid = _column_stats(rows, "current_a")
    powers, power_unqualified, _ = _column_stats(rows, "power_w")
    energies, energy_unqualified, _ = _column_stats(rows, "energy_wh")
    voltages, voltage_unqualified, _ = _column_stats(rows, "voltage_v")
    electrical_unqualified = (current_unqualified + voltage_unqualified
                              + power_unqualified + energy_unqualified)
    doors = sorted({(row.get("door_open") or "MISSING").strip() or "MISSING" for row in rows})
    slope = trailing_slope_c_per_min(points)
    whole = _least_squares(points)
    return {
        **base,
        "usable": True,
        "slope_definition": f"{representation}/{SLOPE_WINDOW_SAMPLES}samples/{SLOPE_METHOD}_v0",
        "whole_phase_slope_definition": f"{representation}/whole_phase_least_squares_v0",
        "samples": len(points),
        "skipped_rows": len(rows) - len(points),
        "current_rows_unqualified": current_unqualified,
        "current_rows_invalid": current_invalid,
        "power_rows_unqualified": power_unqualified,
        "voltage_rows_unqualified": voltage_unqualified,
        "energy_rows_unqualified": energy_unqualified,
        "electrical_rows_unqualified": electrical_unqualified,
        "electrical_status_recorded": electrical_unqualified == 0,
        "electrical_status_note": (
            "no electrical column in this capture carries a recorded OK: current and "
            "voltage have empty status cells and power/energy have no status column at "
            "all, so the values are unqualified, not verified"
            if electrical_unqualified else "every electrical status was recorded OK"),
        "duration_min": round(points[-1][0] - points[0][0], 4),
        "start_c": round(points[0][1], 4),
        "end_c": round(points[-1][1], 4),
        "min_c": round(min(p[1] for p in points), 4),
        "max_c": round(max(p[1] for p in points), 4),
        "delta_c": round(points[-1][1] - points[0][1], 4),
        "trailing_slope_is_not_a_phase_summary": True,
        # Derived, so the claim above is checkable rather than decorative: if the two
        # definitions ever return the same number, this says so instead of hiding it.
        "trailing_differs_from_whole_phase": (slope is not None and whole is not None
                                              and abs(slope - whole) > 1e-9),
        "slope_c_per_min": None if slope is None else round(slope, 6),
        "whole_phase_slope_c_per_min": None if whole is None else round(whole, 6),
        "minutes_to_1c": _time_to_move(points, phase, 1.0),
        "minutes_to_2c": _time_to_move(points, phase, 2.0),
        "mean_current_a": None if not currents else round(sum(currents) / len(currents), 4),
        "peak_current_a": None if not currents else round(max(currents), 4),
        "mean_power_w": None if not powers else round(sum(powers) / len(powers), 4),
        "mean_voltage_v": None if not voltages else round(sum(voltages) / len(voltages), 4),
        "energy_wh": None if len(energies) < 2 else round(energies[-1] - energies[0], 4),
        "door_open_tokens": doors,
        "valid_sample_fraction": round(len(points) / len(rows), 4),
    }


def summarize(values: list[float], label: str) -> dict[str, object]:
    """Sample statistics (n-1) over one outcome across runs, with nothing hidden."""
    out: dict[str, object] = {"outcome": label, "n": len(values)}
    if not values:
        out["status"] = "NO_SAMPLES"
        out["note"] = "no run of this phase produced this outcome"
        return out
    out["status"] = "OK"
    out["mean"] = round(statistics.fmean(values), 6)
    out["min"] = round(min(values), 6)
    out["max"] = round(max(values), 6)
    out["range"] = round(max(values) - min(values), 6)
    if len(values) >= 2:
        sd = statistics.stdev(values)
        out["sd_sample"] = round(sd, 6)
        mean = statistics.fmean(values)
        out["cv_pct"] = round(100.0 * sd / mean, 4) if mean != 0 else None
        if out["cv_pct"] is None:
            out["cv_note"] = "CV undefined: the mean is zero, so a ratio has no meaning"
    else:
        out["sd_sample"] = None
        out["cv_pct"] = None
        out["cv_note"] = "spread needs at least two runs"
    return out


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def capture_id(path: pathlib.Path) -> str:
    """Name a capture the same way on every machine.

    Generated artifacts are hash-pinned, so an absolute path here would make one
    real capture produce different bytes per checkout - and would put a
    developer's home directory into the repository.
    """
    candidate = path if path.is_absolute() else pathlib.Path.cwd() / path
    try:
        return candidate.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        # Outside the repository: leave the path as given. Such a capture cannot be
        # committed here, and validate_w07.py fails the dossier if one ever is.
        return path.as_posix()


def capture_path(identifier: str) -> pathlib.Path:
    """Resolve what capture_id emitted back to the file it names.

    The published id is repository-relative, so it must not depend on the
    directory the next tool happened to be invoked from.
    """
    path = pathlib.Path(identifier)
    return path if path.is_absolute() else REPO_ROOT / path


def analyze(paths: list[pathlib.Path], representation: str,
            min_runs: int) -> dict[str, object]:
    runs: list[dict[str, object]] = []
    for path in paths:
        rows = read_rows(path)
        phases = split_phases(rows)
        per_phase: dict[str, object] = {}
        for phase, phase_rows in phases.items():
            if phase == "undetermined" or not phase_rows:
                continue
            per_phase[phase] = phase_metrics(phase_rows, phase, representation)
        runs.append({
            "capture": capture_id(path),
            "phases": per_phase,
            "passive_candidate": len(phases["cooling"]) == 0,
            "cooling_candidate": len(phases["cooling"]) > 0,
            "undetermined_rows": len(phases["undetermined"]),
            "rows_read": len(rows),
        })

    usable: dict[str, list[dict[str, object]]] = {}
    for run in runs:
        for phase, metrics in run["phases"].items():
            if metrics.get("usable"):
                usable.setdefault(phase, []).append(metrics)  # type: ignore[arg-type]

    phases_out: dict[str, object] = {}
    for phase, samples in usable.items():
        stats = {}
        for outcome in OUTCOMES:
            values = [s[outcome] for s in samples if isinstance(s.get(outcome), (int, float))]
            stats[outcome] = summarize(values, outcome)
        phases_out[phase] = {
            "runs": samples,
            "statistics": stats,
            "samples_per_run": [s["samples"] for s in samples],
            "verdict": {
                "runs": len(samples),
                "min_runs_required": min_runs,
                "additional_runs_needed": max(0, min_runs - len(samples)),
                "status": ("REPEATABILITY_COMPUTED" if len(samples) >= min_runs
                           else "INSUFFICIENT_RUNS"),
            },
        }

    return {
        "analysis": SCHEMA_NOTE,
        "representation": representation,
        "representation_terms": list(terms_of(representation)),
        "representation_roles": [AS_BUILT_ROLES[t] for t in terms_of(representation)],
        "includes_hot_side": includes_hot_side(representation),
        "slope_definition": f"{representation}/{SLOPE_WINDOW_SAMPLES}samples/{SLOPE_METHOD}_v0",
        "whole_phase_slope_definition": f"{representation}/whole_phase_least_squares_v0",
        "spread_formula": "sample (n-1)",
        "runs_read": len(runs),
        "runs": runs,
        "phases": phases_out,
        "verdict": _overall_verdict(phases_out, runs),
        "notes": [
            "Host analysis of recorded captures: nothing here reproduced, energized "
            "or verified a physical action.",
            "A capture with no cooling block is a passive candidate only, never a "
            "cooling step.",
            "Rows whose applied duty is absent are counted as undetermined and join "
            "neither the baseline nor the recovery segment.",
            "Partial means are excluded from a phase series and counted in "
            "partial_term_rows, so a published phase statistic is always the full "
            "quantity it names.",
            "Electrical values are published with an explicit statement of whether "
            "their validity was recorded at all.",
        ],
    }


def _overall_verdict(phases: dict[str, object], runs: list[dict[str, object]]) -> dict:
    def _status(block: object) -> str:
        return "NO_DATA" if not isinstance(block, dict) else block["verdict"]["status"]

    cooling = phases.get("cooling")
    baseline = phases.get("baseline")
    return {
        "cooling_step_runs": _status(cooling),
        "passive_warmup_runs": _status(baseline),
        "plant_variation_reportable": all(
            _status(p) == "REPEATABILITY_COMPUTED" for p in (cooling, baseline)),
        "captures_with_no_cooling_block": sum(1 for r in runs if r["passive_candidate"]),
        "undetermined_rows_total": sum(int(r["undetermined_rows"]) for r in runs),
    }


def overlay_rows(reports: list[dict[str, object]]) -> list[tuple[object, ...]]:
    """Overlay rows for one or more analyses, from the same series as the statistics.

    Two time bases: ``phase_elapsed_min`` aligns runs against each other,
    ``boot_elapsed_min`` keeps the device's own monotonic axis.
    """
    header = ("run", "phase", "representation", "includes_hot_side", "sample_index",
              "phase_elapsed_min", "boot_elapsed_min", "tmean_c")
    rows: list[tuple[object, ...]] = [header]
    for report in reports:
        representation = str(report["representation"])
        hot = includes_hot_side(representation)
        for run in report["runs"]:  # type: ignore[union-attr]
            source = capture_path(str(run["capture"]))
            phases = split_phases(read_rows(source))
            for phase, metrics in run["phases"].items():  # type: ignore[union-attr]
                if not metrics.get("usable"):
                    continue
                points, _ = _phase_points(phases[phase], representation)
                if not points:
                    continue
                base_t = points[0][0]
                for index, (minutes, value) in enumerate(points):
                    rows.append((source.name, phase, representation, int(hot), index,
                                 round(minutes - base_t, 4), round(minutes, 4),
                                 round(value, 4)))
    return rows


def write_overlay_csv(path: pathlib.Path, reports: list[dict[str, object]]) -> None:
    """LF-only overlay, so a hash pin is platform independent."""
    import io

    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(overlay_rows(reports))
    path.write_bytes(buffer.getvalue().encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("captures", nargs="+", type=pathlib.Path)
    parser.add_argument("--representation", default="tmean_airroles_v0",
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
                print(f"  {outcome}: NO_SAMPLES (n=0)")
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
        write_overlay_csv(args.csv_out, [report])
        print(f"csv={args.csv_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
