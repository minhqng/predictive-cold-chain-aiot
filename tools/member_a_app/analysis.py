"""Statistics over captured frames.

The role authority mirrors ``firmware/tools/cg_probe_roles.py``: T1, T3
and the spare probe are chamber air; T2 is the TEC hot side and must never
enter a chamber-air aggregate. The acceptance tests assert this mirror so
the two layers cannot drift silently.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Iterable, Mapping, Sequence

from .protocol import TelemetryFrame

CHAMBER_ROLES = ("T1", "T3", "SPARE")
HOT_SIDE_ROLE = "T2"
ALL_ROLES = ("T1", "T2", "T3", "SPARE")

# Mirrors evidence/A/W02/sensor-rom-map.yaml and
# firmware/tools/cg_probe_roles.py. T2 is the hot side by ROM bytes.
FROZEN_ROM_BY_ROLE = {
    "T1": "287088CA00000051",
    "T2": "28AEBF2200000006",
    "T3": "28CBE9CA00000072",
    "SPARE": "283BE5C9000000A9",
}


def mean(values: Sequence[float]) -> float | None:
    clean = [value for value in values if value is not None and math.isfinite(value)]
    return sum(clean) / len(clean) if clean else None


def sd(values: Sequence[float]) -> float | None:
    clean = [value for value in values if value is not None and math.isfinite(value)]
    return statistics.stdev(clean) if len(clean) >= 2 else None


def median(values: Sequence[float]) -> float | None:
    clean = [value for value in values if value is not None and math.isfinite(value)]
    return statistics.median(clean) if clean else None


def p95(values: Sequence[float]) -> float | None:
    clean = sorted(value for value in values if value is not None and math.isfinite(value))
    if not clean:
        return None
    index = min(len(clean) - 1, max(0, math.ceil(0.95 * len(clean)) - 1))
    return clean[index]


def cv(values: Sequence[float]) -> float | None:
    average = mean(values)
    spread = sd(values)
    if average is None or spread is None or average == 0:
        return None
    return spread / abs(average)


def linear_slope(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys)
             if x is not None and y is not None and math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return None
    mx = sum(x for x, _ in pairs) / len(pairs)
    my = sum(y for _, y in pairs) / len(pairs)
    denominator = sum((x - mx) ** 2 for x, _ in pairs)
    if denominator == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in pairs) / denominator


def frame_seconds(frames: Sequence[TelemetryFrame], start_uptime: float | None = None) -> list[float]:
    if not frames:
        return []
    base = start_uptime
    if base is None:
        base = frames[0].uptime_ms / 1000.0 if frames[0].uptime_ms is not None else 0.0
    out: list[float] = []
    for frame in frames:
        if frame.uptime_ms is not None:
            out.append(frame.uptime_ms / 1000.0 - base)
        else:
            out.append((frame.host_time - frames[0].host_time).total_seconds())
    return out


def chamber_temps(frame: TelemetryFrame) -> list[float]:
    values: list[float] = []
    for role in CHAMBER_ROLES:
        value = frame.temperature(role)
        if value is not None and frame.temp_valid(role):
            values.append(value)
    if not values and frame.chamber_c is not None:
        values.append(frame.chamber_c)
    return values


def tmean(frame: TelemetryFrame) -> float | None:
    return mean(chamber_temps(frame))


def gradient(frame: TelemetryFrame) -> float | None:
    values = chamber_temps(frame)
    return max(values) - min(values) if len(values) >= 2 else None


def hot_side(frame: TelemetryFrame) -> float | None:
    value = frame.temperature(HOT_SIDE_ROLE)
    if value is not None and frame.temp_valid(HOT_SIDE_ROLE):
        return value
    return frame.hot_side_c


def current(frame: TelemetryFrame) -> float | None:
    return frame.current_a if frame.electrical_valid() else None


def timing_metrics(frames: Sequence[TelemetryFrame]) -> dict:
    seconds = [frame.uptime_ms / 1000.0 for frame in frames if frame.uptime_ms is not None]
    intervals = [b - a for a, b in zip(seconds, seconds[1:]) if b >= a]
    boots = [frame.boot_id for frame in frames]
    boots_complete = bool(frames) and all(boot is not None for boot in boots)
    boot_ids = {boot for boot in boots if boot}
    boot_changes = 0
    if boots_complete and boot_ids:
        boot_changes = max(0, len(boot_ids) - 1)
    return {
        "frames": len(frames),
        "duration_s": (seconds[-1] - seconds[0]) if len(seconds) >= 2 else 0.0,
        "interval_mean_s": mean(intervals),
        "interval_p95_s": p95(intervals),
        "interval_max_s": max(intervals) if intervals else None,
        "boot_changes": boot_changes if boots_complete else None,
        "boot_ids_complete": boots_complete,
        "seq_complete": all(frame.seq is not None for frame in frames),
        "seq_regressions": _seq_regressions(frames),
    }


def _seq_regressions(frames: Sequence[TelemetryFrame]) -> int:
    regressions = 0
    previous: tuple[str | None, int | None] = (None, None)
    for frame in frames:
        boot, seq = previous
        if frame.boot_id == boot and frame.seq is not None and seq is not None and frame.seq <= seq:
            regressions += 1
        previous = (frame.boot_id, frame.seq)
    return regressions


def chamber_role_offsets(per_role: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    """Per-role offsets from the chamber-air common mean (T1/T3/SPARE)."""
    means = {}
    for role in CHAMBER_ROLES:
        value = (per_role.get(role) or {}).get("mean_c")
        if isinstance(value, (int, float)):
            means[role] = float(value)
    if len(means) < 2:
        return {}
    common = mean(list(means.values()))
    return {role: value - common for role, value in means.items()}


def offset_drift(baseline: Mapping[str, Mapping[str, Any]],
                 current: Mapping[str, Mapping[str, Any]]) -> tuple[float | None, float | None]:
    """Max absolute chamber offset drift and common-mode level shift."""
    base_offsets = chamber_role_offsets(baseline)
    now_offsets = chamber_role_offsets(current)
    common = [role for role in base_offsets if role in now_offsets]
    if not common:
        return None, None
    deltas = [abs(now_offsets[role] - base_offsets[role]) for role in common]
    base_level = mean([float(baseline[role]["mean_c"]) for role in common])
    now_level = mean([float(current[role]["mean_c"]) for role in common])
    return max(deltas), now_level - base_level


def consistency_metrics(frames: Sequence[TelemetryFrame], roles: Sequence[str] = ALL_ROLES) -> dict:
    series: dict[str, list[float]] = {role: [] for role in roles}
    valid_frames = 0
    for frame in frames:
        values = [frame.temperature(role) for role in roles]
        if all(value is not None for value in values):
            valid_frames += 1
            for role, value in zip(roles, values):
                series[role].append(float(value))
    per_role = {
        role: {
            "n": len(values),
            "mean_c": mean(values),
            "sd_c": sd(values),
            "min_c": min(values) if values else None,
            "max_c": max(values) if values else None,
        }
        for role, values in series.items()
    }
    pairwise: dict[str, float | None] = {}
    for i, first in enumerate(roles):
        for second in roles[i + 1:]:
            a = per_role[first]["mean_c"]
            b = per_role[second]["mean_c"]
            pairwise[f"{first}-{second}"] = abs(a - b) if a is not None and b is not None else None
    spreads = []
    for frame in frames:
        values = [frame.temperature(role) for role in roles]
        if all(value is not None for value in values):
            spreads.append(max(values) - min(values))  # type: ignore[arg-type]
    return {
        "frames": len(frames),
        "valid_frames": valid_frames,
        "valid_rate": valid_frames / len(frames) if frames else 0.0,
        "per_role": per_role,
        "pairwise_mean_difference_c": pairwise,
        "max_pairwise_mean_difference_c": max(
            (value for value in pairwise.values() if value is not None), default=None),
        "max_instantaneous_spread_c": max(spreads) if spreads else None,
    }


def electrical_metrics(frames: Sequence[TelemetryFrame]) -> dict:
    valid = [frame for frame in frames if frame.electrical_valid()]
    volts = [frame.voltage_v for frame in valid if frame.voltage_v is not None]
    currents = [frame.current_a for frame in valid if frame.current_a is not None]
    powers = [frame.power_w for frame in valid if frame.power_w is not None]
    residuals = [
        abs(frame.power_w - frame.voltage_v * frame.current_a) /
        max(1.0, abs(frame.power_w))
        for frame in valid
        if frame.power_w is not None and frame.voltage_v is not None and frame.current_a is not None
    ]
    return {
        "frames": len(frames),
        "valid_frames": len(valid),
        "valid_rate": len(valid) / len(frames) if frames else 0.0,
        "cooling_on_frames": sum(1 for frame in frames if frame.cooling_on),
        "cooling_off_frames": sum(1 for frame in frames if not frame.cooling_on),
        "voltage_mean_v": mean(volts),
        "voltage_min_v": min(volts) if volts else None,
        "voltage_max_v": max(volts) if volts else None,
        "current_mean_a": mean(currents),
        "current_sd_a": sd(currents),
        "current_min_a": min(currents) if currents else None,
        "current_max_a": max(currents) if currents else None,
        "off_current_max_a": max(
            (frame.current_a for frame in frames
             if not frame.cooling_on and frame.current_a is not None), default=None),
        "off_power_max_w": max(
            (frame.power_w for frame in frames
             if not frame.cooling_on and frame.power_w is not None), default=None),
        "power_mean_w": mean(powers),
        "power_max_w": max(powers) if powers else None,
        "power_consistency_max_rel_error": max(residuals) if residuals else None,
    }


def acquisition_metrics(frames: Sequence[TelemetryFrame]) -> dict:
    timing = timing_metrics(frames)
    probes_valid = [
        sum(1 for role in ("T1", "T2", "T3", "SPARE") if frame.temp_valid(role))
        for frame in frames
    ]
    thermal_seq_present = sum(1 for frame in frames if frame.kv.get("thermal_seq") is not None)
    return {
        **timing,
        "probes_valid_min": min(probes_valid) if probes_valid else None,
        "probes_valid_mean": mean(probes_valid),
        "thermal_seq_frames": thermal_seq_present,
        "shared_conversion_evidence_frames": sum(
            1 for frame in frames if frame.kv.get("thermal_seq") is not None),
        "raw_probe_fields": sum(
            1 for frame in frames
            if all(frame.kv.get(f"raw_{role.lower()}_c") is not None
                   for role in ("T1", "T2", "T3", "SPARE"))),
    }


def door_to_critical(frames: Sequence[TelemetryFrame], threshold_c: float) -> float | None:
    door = door_metrics(frames)
    open_events = [event for event in door["events"] if event["open"]]
    if not open_events:
        return None
    open_time = open_events[0]["time_s"]
    if open_time is None:
        return None
    for frame in frames:
        if frame.uptime_ms is None:
            continue
        stamp = frame.uptime_ms / 1000.0
        if stamp < open_time:
            continue
        value = tmean(frame)
        if value is not None and value >= threshold_c:
            return stamp - open_time
    return None


def door_metrics(frames: Sequence[TelemetryFrame]) -> dict:
    events: list[dict] = []
    previous: bool | None = None
    for frame in frames:
        if frame.door_open is None:
            continue
        if previous is not None and frame.door_open != previous:
            events.append({
                "time_s": frame.uptime_ms / 1000.0 if frame.uptime_ms is not None else None,
                "open": frame.door_open,
                "host_time": frame.host_time.isoformat(),
            })
        previous = frame.door_open
    open_durations: list[float] = []
    opened_at: float | None = None
    for event in events:
        stamp = event["time_s"]
        if event["open"] and stamp is not None:
            opened_at = stamp
        elif not event["open"] and opened_at is not None and stamp is not None:
            open_durations.append(stamp - opened_at)
            opened_at = None
    cycles = sum(1 for event in events if not event["open"])
    return {
        "transitions": len(events),
        "cycles": cycles,
        "open_durations_s": open_durations,
        "events": events,
        "unverified_frames": sum(1 for frame in frames if frame.door_open is None),
    }


def warmup_metrics(frames: Sequence[TelemetryFrame]) -> dict:
    seconds = frame_seconds(frames)
    temps = [tmean(frame) for frame in frames]
    pairs = [(t, value) for t, value in zip(seconds, temps) if value is not None]
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    return {
        "frames": len(frames),
        "duration_s": seconds[-1] if seconds else 0.0,
        "mean_temperature_c": mean(ys),
        "start_temperature_c": ys[0] if ys else None,
        "end_temperature_c": ys[-1] if ys else None,
        "slope_c_per_min": (linear_slope(xs, ys) or 0.0) * 60.0 if linear_slope(xs, ys) is not None else None,
        "gradient_mean_c": mean([gradient(frame) for frame in frames]),
        "door_closed_throughout": all(frame.door_open is False for frame in frames),
        "cooling_off_throughout": all(not frame.cooling_on for frame in frames),
        "coverage": len(pairs) / len(frames) if frames else 0.0,
    }


def cooling_step_metrics(frames: Sequence[TelemetryFrame]) -> dict:
    on_indexes = [index for index, frame in enumerate(frames) if frame.cooling_on]
    first_on = on_indexes[0] if on_indexes else None
    baseline_frames = frames[max(0, (first_on or 0) - 10):first_on or 0]
    baseline = mean([tmean(frame) for frame in baseline_frames])
    active = frames[first_on:] if first_on is not None else []
    currents = [current(frame) for frame in active]
    temps = [tmean(frame) for frame in active]
    hot = [hot_side(frame) for frame in active]
    electrical_delay = None
    if first_on is not None:
        for frame in active:
            if (current(frame) or 0.0) >= 0.1:
                electrical_delay = _delta_seconds(frames[first_on], frame)
                break
    thermal_delay = None
    if baseline is not None and first_on is not None:
        below = 0
        for frame in active:
            value = tmean(frame)
            if value is not None and value <= baseline - 0.2:
                below += 1
                if below >= 2:
                    thermal_delay = _delta_seconds(frames[first_on], frame)
                    break
            else:
                below = 0
    valid_temps = [value for value in temps if value is not None]
    valid_currents = [value for value in currents if value is not None]
    return {
        "frames": len(frames),
        "cooling_frames": len(active),
        "baseline_mean_c": baseline,
        "min_chamber_c": min(valid_temps) if valid_temps else None,
        "end_chamber_c": valid_temps[-1] if valid_temps else None,
        "chamber_drop_c": (baseline - min(valid_temps)) if baseline is not None and valid_temps else None,
        "current_mean_a": mean(valid_currents),
        "current_max_a": max(valid_currents) if valid_currents else None,
        "power_mean_w": mean([frame.power_w for frame in active if frame.electrical_valid()]),
        "hot_side_max_c": max((value for value in hot if value is not None), default=None),
        "hot_side_start_c": next((value for value in hot if value is not None), None),
        "electrical_delay_s": electrical_delay,
        "thermal_delay_s": thermal_delay,
        "fan_on_all": all((frame.fan or "").upper() == "ON" for frame in active if frame.fan),
        "fault_bits_max": max((frame.fault_bits or 0) for frame in frames),
        "applied_on_frames": sum(1 for frame in active if frame.cooling_on),
    }


def _delta_seconds(first: TelemetryFrame, second: TelemetryFrame) -> float | None:
    if first.uptime_ms is None or second.uptime_ms is None:
        return (second.host_time - first.host_time).total_seconds()
    return (second.uptime_ms - first.uptime_ms) / 1000.0


def s2_metrics(frames: Sequence[TelemetryFrame]) -> dict:
    door = door_metrics(frames)
    open_events = [event for event in door["events"] if event["open"]]
    if not open_events:
        return {"door": door, "valid": False, "reason": "NO_DOOR_OPEN_EVENT"}
    open_time = open_events[0]["time_s"]
    pre = [frame for frame in frames
           if frame.uptime_ms is not None and open_time is not None
           and frame.uptime_ms / 1000.0 < open_time]
    post = [frame for frame in frames
            if frame.uptime_ms is not None and open_time is not None
            and frame.uptime_ms / 1000.0 >= open_time]
    baseline = mean([tmean(frame) for frame in pre])
    peak = max((tmean(frame) for frame in post if tmean(frame) is not None), default=None)
    end = tmean(post[-1]) if post else None
    return {
        "door": door,
        "valid": baseline is not None and peak is not None,
        "coverage": (sum(1 for frame in frames if tmean(frame) is not None) / len(frames)
                     if frames else 0.0),
        "baseline_mean_c": baseline,
        "peak_mean_c": peak,
        "rise_c": (peak - baseline) if baseline is not None and peak is not None else None,
        "end_mean_c": end,
        "recovery_c": (peak - end) if peak is not None and end is not None else None,
        "open_durations_s": door["open_durations_s"],
        "gradient_peak_c": max((gradient(frame) for frame in post
                                if gradient(frame) is not None), default=None),
    }


def soak_metrics(frames: Sequence[TelemetryFrame]) -> dict:
    boots = [frame.boot_id for frame in frames]
    boots_complete = bool(frames) and all(boot is not None for boot in boots)
    boot_ids = {boot for boot in boots if boot}
    faults = [frame.fault_bits for frame in frames]
    faults_complete = bool(frames) and all(value is not None for value in faults)
    thermal_valid_rate = (
        sum(1 for frame in frames if all(frame.temp_valid(role) for role in CHAMBER_ROLES))
        / len(frames) if frames else 0.0
    )
    return {
        "frames": len(frames),
        "duration_s": (frame_seconds(frames)[-1] if frames else 0.0),
        "boot_ids": sorted(boot_ids),
        "boot_ids_complete": boots_complete,
        "boot_changes": (max(0, len(boot_ids) - 1) if boots_complete and boot_ids else None),
        "thermal_valid_rate": thermal_valid_rate,
        "coverage": thermal_valid_rate,
        "electrical_valid_rate": (
            sum(1 for frame in frames if frame.electrical_valid()) / len(frames) if frames else 0.0
        ),
        "fault_bits_complete": faults_complete,
        "fault_bits_max": (max(faults) if faults_complete and faults else None),
        "hot_side_max_c": max((hot_side(frame) for frame in frames
                               if hot_side(frame) is not None), default=None),
        "current_max_a": max((current(frame) for frame in frames
                              if current(frame) is not None), default=None),
        "quality_counts": _counts(frame.quality for frame in frames),
        "state_counts": _counts(frame.state for frame in frames),
    }


def _counts(values: Iterable[str | None]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = value or "UNKNOWN"
        out[key] = out.get(key, 0) + 1
    return out


def active_envelope(frames: Sequence[TelemetryFrame]) -> dict:
    active = [frame for frame in frames if frame.cooling_on and frame.electrical_valid()]
    off = [frame for frame in frames if not frame.cooling_on and frame.electrical_valid()]
    return {
        "active_frames": len(active),
        "active_current_mean_a": mean([frame.current_a for frame in active if frame.current_a is not None]),
        "active_current_max_a": max((frame.current_a for frame in active if frame.current_a is not None),
                                    default=None),
        "active_power_mean_w": mean([frame.power_w for frame in active if frame.power_w is not None]),
        "active_power_max_w": max((frame.power_w for frame in active if frame.power_w is not None),
                                  default=None),
        "off_frames": len(off),
        "off_current_max_a": max((frame.current_a for frame in off if frame.current_a is not None),
                                 default=None),
        "off_power_max_w": max((frame.power_w for frame in off if frame.power_w is not None),
                               default=None),
    }


def response_time_constant(frames: Sequence[TelemetryFrame]) -> dict:
    metrics = cooling_step_metrics(frames)
    baseline = metrics["baseline_mean_c"]
    final = metrics["end_chamber_c"]
    if baseline is None or final is None or baseline == final:
        return {"tau_s": None, "method": "SLOPE_63_PERCENT", "limitation": "NO_MONOTONIC_STEP"}
    target = baseline + 0.632 * (final - baseline)
    start = next((frame for frame in frames if frame.cooling_on), None)
    if start is None:
        return {"tau_s": None, "method": "SLOPE_63_PERCENT", "limitation": "NO_COOLING_FRAME"}
    for frame in frames:
        value = tmean(frame)
        if frame is start or frame.host_time < start.host_time:
            continue
        if (final < baseline and value is not None and value <= target) or \
           (final > baseline and value is not None and value >= target):
            return {
                "tau_s": _delta_seconds(start, frame),
                "method": "SLOPE_63_PERCENT",
                "limitation": "SINGLE_STEP_EMPIRICAL_PROXY_NOT_A_PHYSICAL_MODEL",
            }
    return {"tau_s": None, "method": "SLOPE_63_PERCENT", "limitation": "TARGET_NOT_REACHED"}


def spatial_metrics(frames: Sequence[TelemetryFrame]) -> dict:
    gradients = [gradient(frame) for frame in frames if gradient(frame) is not None]
    by_role = {}
    for role in CHAMBER_ROLES:
        values = [frame.temperature(role) for frame in frames
                  if frame.temperature(role) is not None and frame.temp_valid(role)]
        by_role[role] = {"mean_c": mean(values), "min_c": min(values) if values else None,
                         "max_c": max(values) if values else None, "n": len(values)}
    return {
        "gradient_mean_c": mean(gradients),
        "gradient_max_c": max(gradients) if gradients else None,
        "gradient_min_c": min(gradients) if gradients else None,
        "by_role": by_role,
        "frames": len(frames),
    }
