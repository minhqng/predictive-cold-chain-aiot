"""ColdGuard W13 plant-timing and intervention-physics package (standard library only).

Docs anchor: ``docs/05A`` section 22 (Week 13 - Plant timing and intervention
physics), requirements A-W13-01 .. A-W13-04, with methods constrained by
``docs/01`` section 20.5 (a slope must declare its temperature representation,
window length and fit/filter method) and section 20.6 (recovery is evaluated
only after a defined disturbance/action reference).

This tool quantifies the physical delays Members B and D need for prediction
horizon and action-in-window, computed from already-committed captures. It
touches no hardware. Two honesty rules drive the whole design:

* A delay that the committed evidence cannot support is reported as a **named
  data gap**, never as an estimate. In particular:
  - **door -> critical time is NOT COMPUTABLE** - there is no door-open event in
    any committed capture (the cooling capture reports ``door_open`` only as 0 or
    UNKNOWN and ``door_polarity`` is never a confirmed open), so no
    trajectory-to-critical-under-door-disturbance distribution exists. This
    function refuses to emit a number for it.
  - **backend command -> device latency is NOT COMPUTABLE** - the production
    firmware has no network command path at all (docs/05A W06; the output stage
    is compiled out), so only a *console* command (an operator START typed into
    the local bridge) is observable. The command->electrical delay is therefore
    measured from the local command event, and the network hop is a named gap.

* Every timing summary names its representation, window and method in the output
  itself, per docs/01 section 20.5.

Requirements implemented:

* **A-W13-01 command->electrical delay** from H6/H7 console traces, with an
  explicit PZEM register-latency exclusion rule stated in code and in the output.
* **A-W13-02 command->thermal response delay** with a named detection method.
* **A-W13-03 door->critical time** - refuses, returns NOT_COMPUTABLE.
* **A-W13-04 passive/cooling time-constant proxies** - first-order empirical
  summaries only, never a fitted physics model.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import math
import pathlib
import statistics
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "evidence" / "A"

# The W12 drift audit owns the probe-identification classifier; W13 must honour
# the same exclusion (the W12 acceptance claim is "excluded from every drift and
# timing statistic"), so it imports the real rule rather than a weaker local copy.
import cg_w12_drift_audit as _w12  # noqa: E402

DEFAULT_CURRENT_THRESHOLD_A = 0.1   # "meaningful current" for electrical onset
# 1 C is Member A's OWN host-side response-detection choice for A-W13-02, not a
# docs/01-mandated value; the 0.85 min figure is what this capture reached at that
# threshold, not a documented constant.
DEFAULT_THERMAL_DELTA_C = 1.0
# docs/01 section 20.5: a slope must state which temperature representation is
# used. Chamber air here is the three-probe trio (T1 center, T3 bottom, T4 near
# door); the TEC hot side (T2) is excluded from this representation (the authored
# chamber-air-trio-v1 deviation, not a docs/01 ban).
THERMAL_REPRESENTATION = "mean(T1,T3,T4) - chamber-air trio, TEC_HOT_SIDE excluded"
CHAMBER_AIR_SLOTS = ("t1", "t3", "t4")
VALID_STATUS_TOKENS = {"OK", "VALID", "GOOD"}
# The H6 trace's bracket column is the device log uptime (seconds since boot in
# the console line), so the command anchor is the device "START accepted" line,
# not the operator keystroke; the operator-to-accept transport segment is excluded.
POLL_QUANTIZATION_S = 1.0           # onset is the first 1 Hz sample after the command


def _now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _f(value: object) -> float | None:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if out != out:
        return None
    return out


def _distinct_boot_ids(rows: list[dict[str, str]]) -> list[str]:
    return sorted({(r.get("boot_id") or "").strip() for r in rows
                   if (r.get("boot_id") or "").strip()})


def _boot_continuity(rows: list[dict[str, str]]) -> dict[str, object]:
    """Interval-safety note: an interval may not silently cross a boot_id change.

    W07's cadence discipline and the W12 boot-identity rule both say a device
    clock restart invalidates a span, so every W13 interval names the boot it was
    measured within and refuses to blend two boots.
    """
    boots = _distinct_boot_ids(rows)
    if len(boots) > 1:
        return {"boot_ids": boots, "single_boot": False,
                "note": "interval spans multiple boot identities - NOT COMPUTABLE "
                        "across a device clock restart"}
    if len(boots) == 1:
        return {"boot_id": boots[0], "single_boot": True}
    return {"boot_id": None, "single_boot": None,
            "note": "capture carries no boot_id column; boot continuity is UNVERIFIED"}


def _percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile - a quoted P95 names an observation that happened."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(q * len(ordered))))
    return float(ordered[rank - 1])


def load_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [r for r in csv.DictReader(handle) if r]


# ---------------------------------------------------------------------------
# A-W13-01 command -> electrical delay (H6/H7 console traces)
# ---------------------------------------------------------------------------
def _latency_exclusion_rule() -> str:
    return (
        "Onset is the FIRST post-command SAMPLE at or above the current threshold "
        "- it is never forced to skip the first sample. A sample is annotated as a "
        "stale pre-run PZEM register read ONLY when the record itself carries that "
        "evidence (a sub-poll `elapsed_ms`, i.e. the pre-ramp reading documented at "
        "evidence/A/W04/h6/41-h6-run-analysis.md:28); such an annotated sample is "
        "below threshold in practice, so the annotation never shifts a real onset. "
        "CLOCK: the bracket column `host_uptime_s` is the DEVICE LOG UPTIME (seconds "
        "since boot in the console line), not a host wall clock. The interval starts "
        "at the device's 'START accepted' line, NOT at the operator keystroke "
        "(\">>> START\"), so the ~0.156 s operator-to-accept transport/echo segment "
        "is EXCLUDED. The reported delay is command-accept -> electrical-onset, "
        "quantised to the 1 Hz poll: the true onset lies within +/-1 s (one poll "
        "period) of the reported value."
    )


def _is_prerun_stale(row: dict[str, str]) -> bool:
    """Evidence that a SAMPLE is the documented pre-ramp register read.

    Only the record itself decides: the H6 first post-command poll carries a
    sub-poll `elapsed_ms` (the pre-ramp reading at 41-h6-run-analysis.md:28). A
    sample with genuine post-ramp elapsed time is never called stale.
    """
    elapsed = _f(row.get("elapsed_ms"))
    return elapsed is not None and elapsed < 1000.0


def command_to_electrical_delay(trace_path: pathlib.Path,
                                current_threshold_a: float = DEFAULT_CURRENT_THRESHOLD_A
                                ) -> dict[str, object]:
    rows = load_csv(trace_path)
    if _w12.is_probe_identification(trace_path, rows):
        return {"capture": trace_path.name, "status": "EXCLUDED_PROBE_IDENTIFICATION",
                "delay_s": None,
                "note": "probe-identification touch capture excluded from timing (docs/01)"}
    boot = _boot_continuity(rows)
    if boot.get("single_boot") is False:
        # A console trace that spans a device reboot has no single uptime clock;
        # the command->electrical interval must never be blended across a boot.
        return {"capture": trace_path.name, "status": "BOOT_DISCONTINUITY", "delay_s": None,
                "boot_continuity": boot,
                "note": "trace spans multiple boot identities; interval refused"}
    # Command event: the first EVENT_CMD whose event_label is START (local console),
    # or, if no START is present, the EVENT_ON edge. This is a *console* command;
    # there is no network command path in production firmware.
    command_row = None
    for r in rows:
        if r.get("record_type") == "EVENT_CMD" and r.get("event_label") == "START":
            command_row = r
            break
    if command_row is None:
        for r in rows:
            if r.get("record_type") == "EVENT_ON":
                command_row = r
                break
    if command_row is None:
        return {
            "capture": trace_path.name,
            "status": "NO_COMMAND_EVENT",
            "delay_s": None,
            "note": "console trace has no START/ON event to anchor the delay",
        }
    t_cmd = _f(command_row.get("host_uptime_s"))

    # SAMPLE rows at-or-after the command time.
    samples_after = []
    for r in rows:
        if r.get("record_type") != "SAMPLE":
            continue
        t = _f(r.get("host_uptime_s"))
        if t is None or t_cmd is None:
            continue
        if t >= t_cmd - 1e-9:
            samples_after.append((t, _f(r.get("current_a")), r))
    samples_after.sort(key=lambda x: x[0])

    if not samples_after:
        return {"capture": trace_path.name, "status": "INSUFFICIENT_POST_COMMAND_SAMPLES",
                "delay_s": None, "note": "no SAMPLE rows at-or-after the command event"}

    # Onset = first at-or-above threshold. A pre-ramp register read is annotated
    # only when the record carries the evidence AND it is below threshold, so a
    # legitimately-current first sample is never shifted a poll late.
    onset = None
    annotated_prerun: list[dict[str, object]] = []
    for t, cur, r in samples_after:
        if _is_prerun_stale(r) and (cur is None or abs(cur) < current_threshold_a):
            annotated_prerun.append({"host_uptime_s": t, "current_a": cur,
                                     "evidence": "sub-poll elapsed_ms (pre-ramp reading, "
                                                 "41-h6-run-analysis.md:28)"})
            continue
        if cur is not None and abs(cur) >= current_threshold_a:
            onset = (t, cur, r)
            break
    if onset is None:
        return {
            "capture": trace_path.name,
            "status": "NO_POST_COMMAND_CURRENT",
            "delay_s": None,
            "note": "no post-command sample exceeded the current threshold; the delay is "
                    "NOT COMPUTABLE from this trace, not zero",
        }
    delay = round(onset[0] - t_cmd, 3)
    return {
        "capture": trace_path.name,
        "status": "MEASURED",
        "command_device_uptime_s": t_cmd,
        "command_anchor": "device 'START accepted' console line (device log uptime clock)",
        "command_label": command_row.get("event_label"),
        "prerun_samples_annotated": annotated_prerun,
        "electrical_onset_device_uptime_s": round(onset[0], 3),
        "electrical_onset_current_a": onset[1],
        "delay_s": delay,
        "onset_rule": "first post-command SAMPLE with |current_a| >= threshold",
        "poll_quantization_s": POLL_QUANTIZATION_S,
        "clock_semantics": _latency_exclusion_rule(),
        "latency_exclusion_rule": _latency_exclusion_rule(),
        "excluded_transport": "operator keystroke ('>>> START') to device START-accept "
                              "(~0.156 s echo/transport) is NOT in this interval",
        "command_provenance": "local console START (no network command path exists in "
                              "production firmware)",
        "boot_continuity": boot,
    }


def command_to_electrical_summary(delays: list[dict[str, object]]) -> dict[str, object]:
    measured = [d["delay_s"] for d in delays if d.get("status") == "MEASURED"]
    out: dict[str, object] = {
        "requirement": "A-W13-01",
        "per_run": delays,
        "n_measured": len(measured),
        "latency_exclusion_rule": _latency_exclusion_rule(),
    }
    if not measured:
        out["aggregate"] = {"status": "NO_MEASURED_DELAYS"}
        return out
    out["aggregate"] = {
        "median_s": round(statistics.median(measured), 3),
        "p95_s": _percentile(measured, 0.95),
        "min_s": round(min(measured), 3),
        "max_s": round(max(measured), 3),
        "max_useful_observed_s": round(max(measured), 3),
        "distribution_note": (
            "n=%d; a single committed console trace yields one command->electrical "
            "event, so median=P95=max by construction - this is not yet a distribution"
            % len(measured) if len(measured) == 1 else "n=%d observations" % len(measured)
        ),
    }
    return out


# ---------------------------------------------------------------------------
# A-W13-02 command -> thermal response delay
# ---------------------------------------------------------------------------
def _valid_value(row: dict[str, str], slot: str) -> float | None:
    """Slot temperature honoured only when the device quality token is valid.

    docs/01 section 19 / section 20.1: a mean may only be taken over the valid
    state. A term with a non-valid status is skipped (and counted by callers),
    never averaged. An empty status is kept so captures predating the token are
    not silently emptied.
    """
    status = (row.get(f"{slot}_status") or "").strip().upper()
    if status and status not in VALID_STATUS_TOKENS:
        return None
    return _f(row.get(f"{slot}_c"))


def _trio_mean(row: dict[str, str]) -> float | None:
    """Full chamber-air trio mean, or None when the frame is not fully valid.

    A frame contributes only when all three chamber probes carry a value AND a
    valid token; a partial trio is returned as None so it is excluded from the
    series rather than averaged under the full-mean label.
    """
    vals = [_valid_value(row, s) for s in CHAMBER_AIR_SLOTS]
    if all(v is not None for v in vals):
        return statistics.fmean(vals)
    return None


def command_to_thermal_delay(rows: list[dict[str, str]],
                            delta_c: float = DEFAULT_THERMAL_DELTA_C) -> dict[str, object]:
    """Time from applied-on (first duty-999 frame) to a named thermal deviation.

    Detection method (docs/05A A-W13-02 asks that the method be defined with
    B/D; this is A's host-side candidate): the representation is the chamber-air
    trio mean over frames whose probes are all valid; the baseline is that mean
    over the first 5 valid driven frames; the response is detected at the first
    valid driven frame whose trio mean has moved by ``delta_c`` in the cooling
    direction from the baseline. Frames carrying a non-valid probe token are
    skipped and counted, never averaged. No smoothing or filter is applied
    (method = "raw first-crossing"), and the window is the driven block only.
    """
    boot = _boot_continuity(rows)
    if boot.get("single_boot") is False:
        return {"status": "BOOT_DISCONTINUITY", "delay_min": None, "note": boot["note"]}
    driven = [r for r in rows if r.get("pwm_applied_permille") == "999"]
    trios = [_trio_mean(r) for r in driven]
    valid_pairs = [(r, t) for r, t in zip(driven, trios) if t is not None]
    excluded_frames = len(driven) - len(valid_pairs)
    valid_trios = [t for _r, t in valid_pairs]
    if len(valid_trios) < 6:
        return {"status": "INSUFFICIENT_DRIVEN_FRAMES", "delay_min": None,
                "excluded_nonvalid_frames": excluded_frames,
                "note": "fewer than 6 fully-valid driven trio frames to establish a baseline"}
    baseline = statistics.fmean(valid_trios[:5])
    start_ms = _f(valid_pairs[0][0].get("device_ms"))
    crossing = None
    for r, trio in valid_pairs:
        if trio <= baseline - delta_c:
            crossing = r
            break
    if crossing is None:
        return {"status": "NO_RESPONSE_WITHIN_WINDOW", "delay_min": None,
                "excluded_nonvalid_frames": excluded_frames,
                "note": f"no {delta_c} C deviation reached inside the driven block"}
    delay_min = (_f(crossing.get("device_ms")) - start_ms) / 60000.0
    return {
        "requirement": "A-W13-02",
        "status": "MEASURED",
        "representation": THERMAL_REPRESENTATION,
        "window": "driven block (duty 999), device_ms monotonic clock",
        "method": "raw first-crossing, no filter/smoothing; baseline = mean of first 5 "
                  "fully-valid driven frames",
        "delta_c": delta_c,
        "excluded_nonvalid_frames": excluded_frames,
        "delay_min": round(delay_min, 4),
        "delay_s": round(delay_min * 60.0, 2),
        "boot_continuity": boot,
        "note": "anchored on the applied-on frame inside the capture, not a host command; "
                "the console command->applied hop is a separate (network) gap",
    }


# ---------------------------------------------------------------------------
# A-W13-04 passive / cooling time-constant proxies
# ---------------------------------------------------------------------------
def estimate_time_constant(t: list[float], y: list[float],
                           direction: str = "auto") -> dict[str, object]:
    """First-order time constant via the 63.2%-of-total-swing rule.

    Empirical summary only (docs/05A A-W13-04: "simple empirical summaries only,
    no sophisticated physics model"). Given a monotonic approach, tau is the
    elapsed time from t[0] until the signal has completed (1 - 1/e) of the
    observed swing. This is a proxy, not a fitted ODE solution; the swing and
    endpoints are the observed ones, so a run that has not reached steady state
    under-estimates tau (stated as a limitation, not corrected by invention).
    """
    if len(t) < 3 or len(t) != len(y):
        return {"status": "INSUFFICIENT_POINTS", "tau_s": None}
    t0 = t[0]
    start = y[0]
    end = y[-1]
    span = end - start
    if abs(span) < 1e-9:
        return {"status": "NO_SWING", "tau_s": None}
    target = start + span * (1.0 - 1.0 / math.e)
    # auto direction: cooling -> decreasing, recovery -> increasing.
    idx = None
    if direction == "auto":
        direction = "decrease" if span < 0 else "increase"
    for i in range(len(y)):
        if direction == "decrease" and y[i] <= target:
            idx = i
            break
        if direction == "increase" and y[i] >= target:
            idx = i
            break
    if idx is None:
        return {"status": "SWING_INCOMPLETE_TARGET_UNREACHED", "tau_s": None,
                "fraction_of_swing_at_end": 1.0, "limitation":
                "the run ends before the signal completes the observed swing, so tau is "
                "a lower bound; not corrected with an invented asymptote"}
    tau = t[idx] - t0
    return {
        "status": "MEASURED",
        "tau_s": round(tau, 3),
        "method": "first-order 63.2%-of-observed-swing time constant (proxy, not an ODE fit)",
        "direction": direction,
        "start_value": round(start, 4),
        "end_value": round(end, 4),
        "target_value": round(target, 4),
        "limitation": "uses the observed endpoints as the swing; a run that has not "
                      "reached steady state under-estimates tau",
    }


def cooling_time_constant_proxy(rows: list[dict[str, str]]) -> dict[str, object]:
    driven = [r for r in rows if r.get("pwm_applied_permille") == "999"]
    pairs = [(_f(r.get("device_ms")), _trio_mean(r)) for r in driven]
    pairs = [(ms, trio) for ms, trio in pairs if ms is not None and trio is not None]
    excluded_frames = len(driven) - len(pairs)
    if len(pairs) < 3:
        return {"status": "INSUFFICIENT_DRIVEN_FRAMES", "tau_s": None,
                "excluded_nonvalid_frames": excluded_frames}
    boot = _boot_continuity(rows)
    if boot.get("single_boot") is False:
        return {"status": "BOOT_DISCONTINUITY", "tau_s": None, "note": boot["note"]}
    t = [(ms - pairs[0][0]) / 1000.0 for ms, _ in pairs]
    y = [trio for _, trio in pairs]
    res = estimate_time_constant(t, y, direction="decrease")
    res["requirement"] = "A-W13-04-cooling"
    res["representation"] = THERMAL_REPRESENTATION
    res["excluded_nonvalid_frames"] = excluded_frames
    res["boot_continuity"] = boot
    res["window_s"] = round(t[-1], 1) if t else None
    # slope-based response time summary (the other docs/01 section 20.5 candidate)
    if len(t) >= 2:
        mx = statistics.fmean(t); my = statistics.fmean(y)
        num = sum((a - mx) * (b - my) for a, b in zip(t, y))
        den = sum((a - mx) ** 2 for a in t)
        slope_per_min = (num / den) * 60.0 if den else None
        res["whole_window_slope_c_per_min"] = round(slope_per_min, 4) if slope_per_min is not None else None
        res["slope_method"] = "ordinary least squares over the full driven window on the trio mean"
    return res


def recovery_time_constant_proxy(rows: list[dict[str, str]]) -> dict[str, object]:
    """Recovery measured AFTER the action (docs/01 section 20.6).

    The action is the driven cooling block; recovery starts at the
    ``STAGE_DEADLINE`` (the frame where cooling stopped) and is the warm-up that
    follows. It is NOT computed continuously over the whole capture - only in
    the post-deadline window - because section 20.6 forbids treating an
    arbitrary always-on 'recovery' as ground truth.
    """
    deadline_idx = None
    for i, r in enumerate(rows):
        if r.get("stop_reason") == "STAGE_DEADLINE":
            deadline_idx = i
            break
    if deadline_idx is None:
        return {"status": "NO_ACTION_END_REFERENCE", "tau_s": None,
                "note": "no STAGE_DEADLINE frame: there is no defined action end to "
                        "anchor recovery (docs/01 section 20.6)"}
    tail = rows[deadline_idx:]
    pairs = [(_f(r.get("device_ms")), _trio_mean(r)) for r in tail]
    pairs = [(ms, trio) for ms, trio in pairs if ms is not None and trio is not None]
    if len(pairs) < 3:
        return {"status": "INSUFFICIENT_RECOVERY_FRAMES", "tau_s": None,
                "excluded_nonvalid_frames": len(tail) - len(pairs)}
    boot = _boot_continuity(tail)
    if boot.get("single_boot") is False:
        return {"status": "BOOT_DISCONTINUITY", "tau_s": None, "note": boot["note"]}
    t = [(ms - pairs[0][0]) / 1000.0 for ms, _ in pairs]
    y = [trio for _, trio in pairs]
    res = estimate_time_constant(t, y, direction="increase")
    res["requirement"] = "A-W13-04-recovery"
    res["representation"] = THERMAL_REPRESENTATION
    res["excluded_nonvalid_frames"] = len(tail) - len(pairs)
    res["boot_continuity"] = boot
    res["window_start"] = "first STAGE_DEADLINE frame (action end)"
    res["window_s"] = round(t[-1], 1) if t else None
    res["rise_c"] = round(y[-1] - y[0], 4)
    res["compliance_docs01"] = "recovery measured after the defined action per section 20.6"
    return res


def passive_time_constant_proxy(rows: list[dict[str, str]]) -> dict[str, object]:
    """Passive baseline before the action: the pre-drive OFF/NONE frames.

    Reported as a drift-rate check, not a time constant, because the plant is
    near equilibrium there and a tau over a flat signal is meaningless; docs/01
    section 20.5 still requires the window/method to be named.
    """
    pre = [r for r in rows if r.get("stage") == "NONE"]
    pairs = [(_f(r.get("device_ms")), _trio_mean(r)) for r in pre]
    pairs = [(ms, trio) for ms, trio in pairs if ms is not None and trio is not None]
    if len(pairs) < 3:
        return {"status": "INSUFFICIENT_PRE_FRAMES",
                "excluded_nonvalid_frames": len(pre) - len(pairs)}
    boot = _boot_continuity(pre)
    if boot.get("single_boot") is False:
        return {"status": "BOOT_DISCONTINUITY", "note": boot["note"]}
    t = [(ms - pairs[0][0]) / 1000.0 for ms, _ in pairs]
    y = [trio for _, trio in pairs]
    rise = y[-1] - y[0]
    dur_min = (t[-1]) / 60.0
    return {
        "requirement": "A-W13-04-passive",
        "representation": THERMAL_REPRESENTATION,
        "window": "pre-drive stage=NONE frames",
        "method": "first-to-last trio delta (near-equilibrium; no tau asserted)",
        "excluded_nonvalid_frames": len(pre) - len(pairs),
        "boot_continuity": boot,
        "passive_drift_c": round(rise, 4),
        "passive_window_min": round(dur_min, 3),
        "note": "a passive tau is not reported because the passive signal does not "
                "exhibit a first-order swing; inventing one would violate A-W13-04",
    }


# ---------------------------------------------------------------------------
# A-W13-03 door -> critical time (refuses)
# ---------------------------------------------------------------------------
def door_to_critical(rows: list[dict[str, str]]) -> dict[str, object]:
    door_vals = {r.get("door_open") for r in rows}
    polar = {r.get("door_polarity") for r in rows}
    has_open = any(v == "1" for v in door_vals)
    return {
        "requirement": "A-W13-03",
        "status": "NOT_COMPUTABLE",
        "value_s": None,
        "number_emitted": False,
        "reason": "no door-open event exists in any committed capture (door_open is only "
                  "'0' or 'UNKNOWN', door_polarity has no confirmed-open state); a "
                  "door->critical trajectory distribution requires an actual door-open "
                  "disturbance that was never recorded",
        "observed_door_open_values": sorted(str(v) for v in door_vals if v is not None),
        "observed_door_polarity_values": sorted(str(v) for v in polar if v is not None),
        "what_would_close_it": "a supervised S2 door-disturbance capture under the frozen "
                               "candidate critical definition (docs/05A A-W13-03) - a "
                               "physical action, so BLOCKED_HARDWARE from the host",
    } if not has_open else {
        "requirement": "A-W13-03",
        "status": "UNEXPECTED_DOOR_OPEN_PRESENT",
        "value_s": None,
        "number_emitted": False,
        "reason": "a door_open=1 value appeared where none was expected; the distribution "
                  "still requires the frozen critical definition before a number is legal",
    }


# ---------------------------------------------------------------------------
# Data-gap register
# ---------------------------------------------------------------------------
def data_gap_register(results: dict[str, object]) -> list[dict[str, object]]:
    gaps = [
        {
            "id": "GAP-DOOR-CRITICAL",
            "ask": "A-W13-03 door->critical time",
            "status": "NOT_COMPUTABLE",
            "why": "no door-open event in any committed capture",
            "closes_with": "supervised S2 door-disturbance capture under the frozen critical definition",
            "owner": "Member A (physical) / Member D (critical definition)",
        },
        {
            "id": "GAP-NETWORK-COMMAND-LATENCY",
            "ask": "backend command -> device latency",
            "status": "NOT_COMPUTABLE",
            "why": "production firmware has no network command path (output stage compiled out)",
            "closes_with": "a transport decision with Member C and an authorized energized session",
            "owner": "Member C / Member D",
        },
        {
            "id": "GAP-COMMAND-ELECTRICAL-DISTRIBUTION",
            "ask": "A-W13-01 median/P95 distribution",
            "status": "SINGLE_OBSERVATION",
            "why": "one committed console trace yields one command->electrical event; "
                   "H7 run logs live in a sibling commissioning worktree (read-only), "
                   "not in this branch",
            "closes_with": "additional clean START traces converted to the H6 schema, then re-run",
            "owner": "Member A",
        },
    ]
    for key in ("command_to_electrical", "command_to_thermal", "cooling_tau", "recovery_tau"):
        res = results.get(key)
        if isinstance(res, dict) and res.get("status") not in (None, "MEASURED"):
            gaps.append({
                "id": f"GAP-{key.upper()}",
                "ask": key,
                "status": res.get("status"),
                "why": res.get("note", res.get("limitation", "not measured")),
                "closes_with": "a capture with enough valid frames for the named window/method",
                "owner": "Member A",
            })
    return gaps


# ---------------------------------------------------------------------------
# Whole-report
# ---------------------------------------------------------------------------
def build_report(trace_paths: list[pathlib.Path],
                 cooling_path: pathlib.Path | None = None) -> dict[str, object]:
    delays = [command_to_electrical_delay(p) for p in trace_paths]
    cte = command_to_electrical_summary(delays)

    results: dict[str, object] = {
        "tool": "cg_w13_timing.py",
        "week": "W13",
        "generated_utc": _now_utc(),
        "evidence_kind": "HOST_ANALYSIS_OF_COMMITTED_CAPTURES",
        "physical_verified": False,
        "touches_hardware": False,
        "command_to_electrical": cte,
    }

    if cooling_path and cooling_path.is_file():
        rows = load_csv(cooling_path)
        if _w12.is_probe_identification(cooling_path, rows):
            # Probe-identification touch captures are excluded from EVERY timing
            # statistic, not just W12's own calls (docs/01; W12 acceptance claim).
            excluded = {"status": "EXCLUDED_PROBE_IDENTIFICATION",
                        "note": "probe-identification touch capture excluded from "
                                "timing/thermal statistics"}
            results["command_to_thermal"] = dict(excluded)
            results["cooling_tau"] = dict(excluded)
            results["recovery_tau"] = dict(excluded)
            results["passive_proxy"] = dict(excluded)
            results["door_to_critical"] = {"requirement": "A-W13-03",
                                           "status": "EXCLUDED_PROBE_IDENTIFICATION",
                                           "value_s": None, "number_emitted": False,
                                           "reason": "probe-identification capture carries "
                                                     "no plant door event"}
        else:
            results["command_to_thermal"] = command_to_thermal_delay(rows)
            results["cooling_tau"] = cooling_time_constant_proxy(rows)
            results["recovery_tau"] = recovery_time_constant_proxy(rows)
            results["passive_proxy"] = passive_time_constant_proxy(rows)
            results["door_to_critical"] = door_to_critical(rows)
    else:
        results["command_to_thermal"] = {"status": "NO_COOLING_CAPTURE"}
        results["door_to_critical"] = {
            "requirement": "A-W13-03", "status": "NOT_COMPUTABLE", "value_s": None,
            "number_emitted": False, "reason": "no cooling capture supplied",
        }
    results["data_gap_register"] = data_gap_register(results)
    return results


def default_paths() -> tuple[list[pathlib.Path], pathlib.Path | None]:
    traces = [EVIDENCE / "W04" / "h6" / "first-tec-trace.csv"]
    cooling = EVIDENCE / "W04" / "tec-cooling-response-600s.csv"
    return ([p for p in traces if p.is_file()], cooling if cooling.is_file() else None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace", type=pathlib.Path, action="append",
                        help="H6/H7 console trace CSV (command->electrical source)")
    parser.add_argument("--cooling", type=pathlib.Path, help="cooling-response CSV (thermal source)")
    parser.add_argument("--json-out", type=pathlib.Path)
    args = parser.parse_args(argv)

    traces = args.trace if args.trace else default_paths()[0]
    traces = [p if p.is_absolute() else REPO_ROOT / p for p in traces]
    cooling = (args.cooling if args.cooling else default_paths()[1])
    if cooling is not None and not cooling.is_absolute():
        cooling = REPO_ROOT / cooling
    if not traces:
        print("NO_TRACE_CAPTURES", file=sys.stderr)
        return 2

    report = build_report(traces, cooling)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8", newline="\n")

    cte = report["command_to_electrical"]
    agg = cte.get("aggregate", {})
    print(f"A-W13-01 command->electrical: n={cte.get('n_measured')} "
          f"median={agg.get('median_s')} p95={agg.get('p95_s')} max={agg.get('max_s')}")
    ctt = report.get("command_to_thermal", {})
    print(f"A-W13-02 command->thermal: status={ctt.get('status')} delay_min={ctt.get('delay_min')}")
    d2c = report.get("door_to_critical", {})
    print(f"A-W13-03 door->critical: status={d2c.get('status')} value={d2c.get('value_s')} "
          f"(number_emitted={d2c.get('number_emitted')})")
    print(f"A-W13-04 cooling_tau={report.get('cooling_tau', {}).get('tau_s')} "
          f"recovery_tau={report.get('recovery_tau', {}).get('tau_s')}")
    print(f"data gaps: {[g['id'] for g in report['data_gap_register']]}")
    print("W13 TIMING: HOST_ANALYSIS_ONLY (no hardware; door->critical NOT COMPUTABLE)")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
