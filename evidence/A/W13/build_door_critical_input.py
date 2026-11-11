#!/usr/bin/env python3
"""A-W10-05 / A-W13-03 helper: prepare the door-to-critical computation from the
committed S2 door-disturbance dataset of 2026-11-07 (PR #91, merged).

The frozen critical-Tmean boundary is Member D's safety contract; this tool
NEVER invents it. Two modes:

1. (default, no --critical-tmean)  Emit a D-input sheet: per-run door response
   envelope (baseline, rise, recovery, tmean extremes) so D can freeze a
   physically meaningful upper boundary with knowledge of the actual data
   envelope. door_to_critical stays non-numeric (value_s null,
   number_emitted false) consistent with door-critical.csv.
2. (--critical-tmean <degC>)       Draft-only computation of door-to-critical
   crossing times per run. Output is labeled DRAFT_PENDING_D_FREEZE and must
   not be treated as acceptance evidence until Member D freezes the threshold.

Inputs (all committed): datasets/datasets/W10-03-run*.csv and W10-02 CSV plus
raw/s2-door-20261107/door_report.json values referenced for cross-checking.
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import statistics
import sys
import time

DEFAULT_DATASETS = (pathlib.Path(__file__).resolve().parents[2]
                    / "evidence" / "A" / "SOURCES" / "20261107" / "datasets")
RUNS = {
    "W10-02": "W10-02-normalized.csv",
    "W10-03-run1": "W10-03-run1-normalized.csv",
    "W10-03-run2": "W10-03-run2-normalized.csv",
    "W10-03-run3": "W10-03-run3-normalized.csv",
    "W10-03-run4": "W10-03-run4-normalized.csv",
}


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def read_rows(path: pathlib.Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def run_envelope(path: pathlib.Path) -> dict:
    rows = read_rows(path)
    series = [(fnum(r.get("uptime_ms")) / 1000.0, fnum(r["tmean_air_c"]))
              for r in rows if fnum(r.get("tmean_air_c")) is not None]
    t0 = series[0][0] if series else None
    temps = [t for _, t in series]
    times = [t - t0 for t, _ in series] if t0 is not None else []
    # door event per protocol record: OPEN at ~0 s (cue), CLOSE ~15 s (W10-02
    # protocol); response window examined over the full run.
    baseline = statistics.fmean([t for _, t in series[:30]]) if len(series) >= 30 else None
    max_t = max(temps) if temps else None
    min_t = min(temps) if temps else None
    # first sustained (>=15 s) excursion >= 0.125 degC (2 LSB) above baseline
    delay = None
    if baseline is not None:
        for i, (t, v) in enumerate(series):
            if v - baseline >= 0.125:
                if all(w - baseline >= 0.125 for _, w in series[i:i + 15]) and \
                        len(series[i:i + 15]) == 15:
                    delay = times[i]
                    break
    return {
        "frames": len(rows),
        "tmean_min_c": min_t,
        "tmean_max_c": max_t,
        "baseline_mean_c_30s": round(baseline, 4) if baseline is not None else None,
        "first_sustained_rise_0p125C_delay_s": round(delay, 3) if delay is not None else None,
        "final_tmean_c": temps[-1] if temps else None,
    }


def crossing(series, critical):
    """First upward sustained (2 consecutive samples) crossing of `critical`
    after the door cue (t=0). Returns the relative time of the first of the two
    sustaining samples, or None if no such pair exists. Semantics labeled DRAFT:
    D's frozen definition governs."""
    for (t0, v0), (_t1, v1) in zip(series, series[1:]):
        if v0 >= critical and v1 >= critical:
            return round(t0, 3)
    return None


def main() -> int:
    datasets = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASETS
    critical = None
    for i, arg in enumerate(sys.argv):
        if arg == "--critical-tmean" and i + 1 < len(sys.argv):
            critical = float(sys.argv[i + 1])
    data_dir = datasets / "datasets"
    if not data_dir.is_dir():
        print(f"datasets dir not found: {data_dir}", file=sys.stderr)
        return 2

    per_run = {}
    inputs = []
    for tag, name in RUNS.items():
        path = data_dir / name
        env = run_envelope(path)
        series = [(fnum(r.get("uptime_ms")) / 1000.0, fnum(r["tmean_air_c"]))
                  for r in read_rows(path) if fnum(r.get("tmean_air_c")) is not None]
        if series:
            t_base = series[0][0]
            rel = [(t - t_base, v) for t, v in series]
        else:
            rel = []
        if critical is not None:
            env["door_to_critical_s_draft"] = crossing(rel, critical)
        per_run[tag] = env
        inputs.append({"file": f"evidence/A/SOURCES/20261107/datasets/datasets/{name}",
                       "sha256": sha256(path)})

    output = {
        "schema": "cg-w13-door-critical-input-v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "purpose": ("A-W10-05/A-W13-03 D-input: door response envelope of the 4 "
                    "qualifying S2 runs + timing run, per the recorded 2026-11-07 "
                    "door protocol (door_report.json: OPEN cue ~0 s, close ~15 s, "
                    "open duration ~13-14 s)."),
        "evidence_kind": "HOST_ANALYSIS_OF_COMMITTED_DATASETS",
        "touches_hardware": False,
        "critical_tmean_c": critical,  # None means: Member D threshold NOT frozen yet
        "critical_tmean_status": "FROZEN_DRAFT_ONLY" if critical is not None else "NOT_FROZEN_PENDING_MEMBER_D",
        "door_to_critical": {
            "value_s": None,
            "number_emitted": False,
            "reason": ("The frozen critical-Tmean threshold is Member D's decision; "
                       "no number may be emitted before that freeze "
                       "(A-W13-03 / A-W10-05 remain INCOMPLETE with reason "
                       "NO_DOOR_CRITICAL_SAMPLES until D freezes and the official "
                       "evaluator reruns)."),
        },
        "inputs": inputs,
        "per_run_envelope": per_run,
        "notes_for_member_d": [
            "All 4 S2 door runs and the timing run sit in the ~29.73-29.90 degC "
            "tmean band; door-open durations ~13-14 s produced a recorded rise_c "
            "of 0.04-0.05 degC (door_report.json). A critical upper boundary chosen "
            "near or below the in-run tmean maxima produces frequent positives; a "
            "boundary chosen above ~29.9 degC produces ZERO positive samples in "
            "this dataset - Doc 03 section 42 requires enough positive/negative "
            "events, so D must freeze with this envelope in view.",
            "first_sustained_rise_0p125C_delay_s uses a 0.125 degC/15 s detection "
            "proxy - NOT the canonical response definition (A-W13-02's method "
            "governs); null means no sustained excursion of that size occurred.",
        ],
        "limitations": [
            "Offline analysis of committed captures; no new physical measurement.",
            "Crossing semantics, if a draft critical value is passed, are "
            "provisional (upward, 2-sample sustain) and govern ONLY after D's "
            "frozen definition matches or a canonical evaluator consumes this.",
        ],
    }

    suffix = f"-draft-{str(critical).replace('.', 'p')}" if critical is not None else ""
    out_path = pathlib.Path(__file__).resolve().parent / f"door-critical-input-20261109{suffix}.json"
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"WROTE {out_path}")
    print(f"door->critical number_emitted={output['door_to_critical']['number_emitted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
