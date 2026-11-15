"""ColdGuard W09 per-probe noise estimation: the instrument chain measured from a real capture.

docs/05A §18 A-W09-04 asks Member A to summarize the healthy response reference -
electrical active range, OFF range, thermal baseline and gradient - and a gradient
claim is meaningless without the noise it has to clear. This module is that noise
figure: the per-probe sigma measured from the quiescent segments of the committed
capture, published in ``evidence/A/W09/healthy-ranges.json`` under
``per_probe_noise``.

MOVED VERBATIM out of ``cg_w10_pairing.py`` when the W09 and W10 slices were split
into separate branches. The W09 dossier consumed the estimator, so on a W09-only
checkout the S1 dossier could not be reproduced: a week's evidence must be
derivable from the code that week owns, never from a later week's module. The
estimator is therefore W09's; W10's pairing layer imports it and adds the
detection floor that W10 publishes.

The estimator is **trend-immune**: it uses second differences
(``sigma = std(second diff)/sqrt(6)``) and rejects any run whose fitted slope
exceeds a stated threshold. That rejection does work - the committed capture has a
second OFF segment (seq 832-957) that is the box *recovering* after cooling, at
0.043-0.071 degC/s, and pooling it naively with the resting segment produced a
0.36 degC "noise" figure roughly 18x the truth.

Nothing here energizes a stage or opens a door; the sigma is a property of the
instrument chain read from frames that already exist.
"""

from __future__ import annotations

import math
import statistics

import cg_w09_export as run_export
from cg_w09_capture_parser import Frame

# A rise measured over a horizon H against a noise sigma. The published formula
# has to be the one the code runs: docs/01 §20.5 requires a method to be named,
# and an earlier revision of this constant stated ``sigma_successive_diff`` with
# no z factor while `minimum_detectable_disturbance` multiplies the **second
# difference** sigma by 2.58 - which made every published floor 2.58x larger than
# the formula it printed, and named an estimator that is contaminated by a slope.
WHITE_NOISE_ASSUMPTION = (
    "floor(H) = z * sigma_second_diff / sqrt(H), where sigma_second_diff is the trend-immune "
    "second-difference sigma (std of second differences / sqrt(6)) reported by "
    "probe_noise_profile(), and z is the stated detection z-score (default 2.58). The 1/sqrt(H) "
    "factor assumes white-noise residuals over the horizon; autocorrelated drift would make the "
    "floor larger, not smaller, so this is an optimistic bound"
)

MEASUREMENT_RESOLUTION_C = 0.0625  # DS18B20 12-bit conversion: 1/16 degC
QUANTISATION_NOISE_FLOOR_C = MEASUREMENT_RESOLUTION_C / math.sqrt(12)


def _quiescent_candidate_runs(frames: list[Frame]) -> list[list[int]]:
    """Contiguous runs of (snapshot VALID, state OFF, duty 0).

    Contiguity matters and is not a detail: the committed capture has OFF frames
    *before* the cooling stage (box sitting at room temperature) and OFF frames
    *after* it (box recovering). Filtering on state alone and then differencing
    joins those two regimes across 600 s of cooling, which is what first
    happened here and inflated the noise estimate by about 8x - the single
    -9.25 degC step in the difference histogram was the join, not the sensor.
    """
    runs: list[list[int]] = []
    current: list[int] = []
    previous_index: int | None = None

    def quiescent(index: int) -> bool:
        frame = frames[index]
        return (
            frame.values.get("snapshot") == "VALID"
            and frame.values.get("state") == "OFF"
            and frame.values.get("pwm_applied_permille") == 0
        )

    for index in range(len(frames)):
        if quiescent(index) and (previous_index is None or index == previous_index + 1):
            if not current:
                current = [index]
            else:
                current.append(index)
            previous_index = index
            continue
        if current:
            runs.append(current)
            current = []
        previous_index = index if quiescent(index) else None
        if quiescent(index) and current == [] and previous_index == index:
            current = [index]
    if current:
        runs.append(current)
    return [run for run in runs if len(run) >= 8]


def linear_slope_c_per_s(series: list[tuple[int, float]]) -> float | None:
    """Least-squares slope over device_ms, in degC per second."""
    if len(series) < 3:
        return None
    n = len(series)
    mean_x = statistics.fmean(x for x, _ in series)
    mean_y = statistics.fmean(y for _, y in series)
    denominator = sum((x - mean_x) ** 2 for x, _ in series)
    if denominator == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in series) / denominator * 1000.0


def second_difference_sigma(values: list[float]) -> dict:
    """Trend-immune white-noise sigma: std(second differences) / sqrt(6).

    For a signal that is white noise plus any linear drift, the second
    difference kills the drift and ``Var = 6 sigma^2``. The first difference
    cannot do that, which is why it is reported beside this as
    ``first_diff_sigma_c_contaminated_by_slope`` rather than used as the floor.
    """
    if len(values) < 4:
        return {"n": len(values), "sigma_c": None}
    second = [c - 2 * b + a for a, b, c in zip(values, values[1:], values[2:])]
    sigma = statistics.stdev(second) / math.sqrt(6.0)
    return {
        "n": len(values),
        "n_second_differences": len(second),
        "sigma_c": round(sigma, 6),
    }


def successive_difference_sigma(values: list[float]) -> dict:
    """sigma from successive differences: sd(diff)/sqrt(2) for white noise.

    Only valid on a genuinely stationary series; a slope adds directly to it.
    """
    if len(values) < 3:
        return {"n": len(values), "sigma_c": None}
    diffs = [b - a for a, b in zip(values, values[1:])]
    sd = statistics.stdev(diffs)
    return {
        "n": len(values),
        "n_differences": len(diffs),
        "successive_diff_stdev_c": round(sd, 6),
        "sigma_c": round(sd / math.sqrt(2.0), 6),
        "mean_abs_diff_c": round(statistics.fmean(abs(d) for d in diffs), 6),
        "max_abs_diff_c": round(max(abs(d) for d in diffs), 6),
    }


def probe_noise_profile(frames: list[Frame], max_slope_c_per_s: float = 0.002) -> dict:
    """Per-probe noise, estimated separately per contiguous quiescent run.

    A run whose fitted slope exceeds ``max_slope_c_per_s`` is rejected as a ramp
    and reported with its slope, so a drifting box can never be mistaken for an
    instrument noise figure. The accepted runs are pooled by averaging their
    variances, not by concatenating their values.
    """
    runs = _quiescent_candidate_runs(frames)
    per_run: list[dict] = []
    accepted_by_slot: dict[str, list[dict]] = {
        slot: [] for slot in (*run_export.CHAMBER_AIR_SLOTS, "t2")
    }
    for run in runs:
        entry: dict[str, object] = {
            "first_seq": frames[run[0]].seq,
            "last_seq": frames[run[-1]].seq,
            "n_frames": len(run),
            "start_device_ms": frames[run[0]].values.get("device_ms"),
            "end_device_ms": frames[run[-1]].values.get("device_ms"),
            "duration_s": round(
                (frames[run[-1]].values["device_ms"] - frames[run[0]].values["device_ms"]) / 1000.0, 3
            ),
            "probes": {},
        }
        run_accepted = True
        for slot in (*run_export.CHAMBER_AIR_SLOTS, "t2"):
            series = [
                (frames[i].values["device_ms"], frames[i].values[slot])
                for i in run
                if isinstance(frames[i].values.get(slot), (int, float))
                and isinstance(frames[i].values.get("device_ms"), int)
            ]
            slope = linear_slope_c_per_s(series)
            first = successive_difference_sigma([v for _, v in series])
            second = second_difference_sigma([v for _, v in series])
            stationary = slope is not None and abs(slope) <= max_slope_c_per_s
            entry["probes"][slot] = {
                "n": len(series),
                "slope_c_per_s": round(slope, 7) if slope is not None else None,
                "stationary": stationary,
                "sigma_c_second_diff_trend_immune": second["sigma_c"],
                "first_diff_sigma_c_contaminated_by_slope": first["sigma_c"],
                "max_abs_diff_c": first.get("max_abs_diff_c"),
            }
            if not stationary:
                run_accepted = False
            elif second["sigma_c"] is not None:
                accepted_by_slot[slot].append({"n": len(series), "sigma_c": second["sigma_c"]})
        entry["accepted_for_noise_estimation"] = run_accepted
        per_run.append(entry)

    pooled: dict[str, dict] = {}
    for slot, samples in accepted_by_slot.items():
        if not samples:
            pooled[slot] = {
                "quiescent_runs_accepted": 0,
                "sigma_c": None,
                "physical_position": run_export.FROZEN_SENSOR_GEOMETRY.get(slot, {}).get("position"),
            }
            continue
        total_n = sum(s["n"] for s in samples)
        variance = sum(s["sigma_c"] ** 2 * s["n"] for s in samples) / total_n
        pooled[slot] = {
            "physical_position": (
                run_export.FROZEN_SENSOR_GEOMETRY[slot]["position"]
                if slot in run_export.FROZEN_SENSOR_GEOMETRY else "TEC_HOT_SIDE"
            ),
            "quiescent_runs_accepted": len(samples),
            "n_frames_pooled": total_n,
            "sigma_c": round(math.sqrt(variance), 6),
            "per_run_sigma_c": [s["sigma_c"] for s in samples],
            "measurement_resolution_c": MEASUREMENT_RESOLUTION_C,
            "quantisation_noise_floor_c": round(QUANTISATION_NOISE_FLOOR_C, 6),
            "noise_exceeds_quantisation_only": math.sqrt(variance) > QUANTISATION_NOISE_FLOOR_C,
            "excluded_from_chamber_mean": run_export.EXCLUDED_FROM_CHAMBER_MEAN.get(slot, ""),
        }
    return {
        "quiescent_runs_found": len(runs),
        "quiescent_runs": per_run,
        "stationarity_threshold_c_per_s": max_slope_c_per_s,
        "selection_rule": "contiguous runs of snapshot=VALID AND state=OFF AND duty=0, "
                          "then rejected if the fitted slope exceeds the threshold",
        "estimator": "second-difference sigma (trend immune), pooled across accepted runs",
        "probes": pooled,
        "assumption": WHITE_NOISE_ASSUMPTION,
    }
