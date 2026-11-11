#!/usr/bin/env python3
"""Recompute the healthy response reference (A-W09-04 input) from the committed
S1 dataset of 2026-11-07 (PR #91, merged to main) plus the committed H8-C
cooling capture import.

Measurement-only, offline. This artifact is an INPUT to A-W09-04; acceptance of
A-W09-04 itself remains gated on A-W08-03 per the store governance
(acceptance-decisions-20261108.md). Nothing here claims acceptance PASS.
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

S1_FILES = [
    "trial1-imported-normalized.csv",
    "trial2-normalized.csv",
    "trial3-normalized.csv",
    "trial4-normalized.csv",
]
H8C_FILE = "H8-C-600s-TEC-100pct-normalized.csv"
W07_PASSIVE_FILES = [
    "a-w07-02-run-1-4b555191-normalized.csv",
    "a-w07-02-run-2-4b555191-normalized.csv",
    "a-w07-02-run-3-4b555191-normalized.csv",
]
PROBES = ["t1_c", "t2_c", "t3_c", "t4_c"]


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def read_rows(path: pathlib.Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fnum(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def status_ok(value) -> bool:
    return str(value or "").strip().upper() == "OK"


def sigma_second_diff(values):
    d2 = []
    for i in range(2, len(values)):
        if values[i] is not None and values[i - 2] is not None:
            d2.append(values[i] - values[i - 2])
    if len(d2) < 2:
        return None
    return statistics.pstdev(d2)


def sigma_first_diff(values):
    d1 = [b - a for a, b in zip(values, values[1:]) if a is not None and b is not None]
    if len(d1) < 2:
        return None
    return statistics.pstdev(d1)


def ols_slope(times, values):
    pairs = [(t, v) for t, v in zip(times, values) if t is not None and v is not None]
    if len(pairs) < 3:
        return None
    t0, _ = pairs[0]
    ts = [t - t0 for t, _ in pairs]
    vs = [v for _, v in pairs]
    n = len(ts)
    tm = sum(ts) / n
    vm = sum(vs) / n
    den = sum((t - tm) ** 2 for t in ts)
    if den == 0:
        return None
    return sum((t - tm) * (v - vm) for t, v in zip(ts, vs)) / den


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(pct / 100.0 * (len(ordered) - 1))))
    return ordered[k]


def main() -> int:
    datasets = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASETS
    data_dir = datasets / "datasets"
    if not data_dir.is_dir():
        print(f"datasets dir not found: {data_dir}", file=sys.stderr)
        return 2

    inputs = []
    for name in S1_FILES + [H8C_FILE] + W07_PASSIVE_FILES:
        path = data_dir / name
        inputs.append({
            "file": f"evidence/A/SOURCES/20261107/datasets/datasets/{name}",
            "sha256": sha256(path),
        })

    rows_by_s1 = {name: read_rows(data_dir / name) for name in S1_FILES}
    identity = {}
    cadence_s = []
    s1_stats = {}
    for name, rows in rows_by_s1.items():
        if not identity and rows:
            identity = {
                "firmware_version": rows[0].get("firmware_version"),
                "hardware_config_id": rows[0].get("hardware_config_id"),
                "grammar": rows[0].get("grammar"),
            }
        run = {"frames": len(rows), "probes": {}, "tmean_air": {}, "cadence_s": None}
        for probe in PROBES:
            vals = [fnum(r[probe]) for r in rows if status_ok(r.get(probe[:-2] + "_status"))]
            run["probes"][probe] = {
                "n": len(vals),
                "mean_c": round(statistics.fmean(vals), 4) if vals else None,
                "min_c": min(vals) if vals else None,
                "max_c": max(vals) if vals else None,
                "sigma_first_diff_c": round(sigma_first_diff(vals), 6) if len(vals) > 2 else None,
                "sigma_second_diff_c": round(sigma_second_diff(vals), 6) if len(vals) > 2 else None,
            }
        tmean = [fnum(r["tmean_air_c"]) for r in rows if fnum(r.get("tmean_air_c")) is not None]
        tsmean = [fnum(r.get("uptime_ms")) / 1000.0 for r in rows
                  if fnum(r.get("tmean_air_c")) is not None]
        run["tmean_air"] = {
            "n": len(tmean),
            "mean_c": round(statistics.fmean(tmean), 4) if tmean else None,
            "min_c": min(tmean) if tmean else None,
            "max_c": max(tmean) if tmean else None,
            "ols_slope_c_per_s": round(ols_slope(tsmean, tmean), 8) if tmean else None,
        }
        ups = [fnum(r.get("uptime_ms")) for r in rows if fnum(r.get("uptime_ms")) is not None]
        deltas = [(b - a) / 1000.0 for a, b in zip(ups, ups[1:])]
        if deltas:
            run["cadence_s"] = {
                "mean": round(statistics.fmean(deltas), 4),
                "min": round(min(deltas), 4),
                "max": round(max(deltas), 4),
                "n_intervals": len(deltas),
            }
            cadence_s.extend(deltas)
        s1_stats[name] = run

    pooled = {}
    for probe in PROBES:
        series = []
        for name in S1_FILES:
            series.extend(fnum(r[probe]) for r in rows_by_s1[name]
                          if status_ok(r.get(probe[:-2] + "_status")))
        pooled[probe] = {
            "n_total": len(series),
            "sigma_second_diff_c": round(sigma_second_diff(series), 6) if len(series) > 2 else None,
            "min_c": min(series) if series else None,
            "max_c": max(series) if series else None,
        }

    off = {"current_a": [], "voltage_v": [], "power_w": [],
           "thermal_ok": 0, "thermal_total": 0, "electrical_ok": 0, "electrical_total": 0}
    for name, rows in rows_by_s1.items():
        for r in rows:
            off["thermal_total"] += 1
            if all(status_ok(r.get(p[:-2] + "_status")) for p in PROBES):
                off["thermal_ok"] += 1
            off["electrical_total"] += 1
            if (status_ok(r.get("current_status")) and status_ok(r.get("voltage_status"))
                    and status_ok(r.get("power_status"))):
                off["electrical_ok"] += 1
                off["current_a"].append(fnum(r["current_a"]))
                off["voltage_v"].append(fnum(r["voltage_v"]))
                off["power_w"].append(fnum(r["power_w"]))
    off_summary = {
        "frames": off["electrical_total"],
        "electrical_valid_rate": round(off["electrical_ok"] / off["electrical_total"], 5),
        "thermal_valid_rate": round(off["thermal_ok"] / off["thermal_total"], 5),
        "current_a": {
            "mean": round(statistics.fmean(off["current_a"]), 6) if off["current_a"] else None,
            "max": max(off["current_a"]) if off["current_a"] else None,
        },
        "voltage_v": {
            "mean": round(statistics.fmean(off["voltage_v"]), 4) if off["voltage_v"] else None,
            "min": min(off["voltage_v"]) if off["voltage_v"] else None,
            "max": max(off["voltage_v"]) if off["voltage_v"] else None,
        },
        "power_w": {
            "mean": round(statistics.fmean(off["power_w"]), 6) if off["power_w"] else None,
            "max": max(off["power_w"]) if off["power_w"] else None,
        },
        "qualification_note": (
            "Electrical status columns are OK-qualified throughout this dataset "
            "(cg-w06-0.1.0 TELEM schema), unlike the W09-era H8-C CSV whose status "
            "columns were empty (that dossier labeled the electrical domain UNQUALIFIED)."
        ),
    }

    h8c = read_rows(data_dir / H8C_FILE)
    on_rows = [r for r in h8c
               if str(r.get("tec_state", "")).upper() == "COOLING"
               or fnum(r.get("pwm_applied_permille")) not in (None, 0.0)]
    on_cur = [fnum(r["current_a"]) for r in on_rows if fnum(r.get("current_a")) is not None]
    on_v = [fnum(r["voltage_v"]) for r in on_rows if fnum(r.get("voltage_v")) is not None]
    on_p = [fnum(r["power_w"]) for r in on_rows if fnum(r.get("power_w")) is not None]
    active = {
        "source": "evidence/A/SOURCES/20261107/datasets/datasets/H8-C-600s-TEC-100pct-normalized.csv",
        "boot_id": h8c[0].get("boot_id") if h8c else None,
        "firmware_version": h8c[0].get("firmware_version") if h8c else None,
        "segment": "tec_state==COOLING (H8-C 600 s, 100% duty bench stage, run-00000001)",
        "frames": len(on_rows),
        "current_a": {
            "mean": round(statistics.fmean(on_cur), 4) if on_cur else None,
            "median": round(statistics.median(on_cur), 4) if on_cur else None,
            "p95": round(percentile(on_cur, 95), 4) if on_cur else None,
            "max": max(on_cur) if on_cur else None,
        },
        "voltage_v": {
            "mean": round(statistics.fmean(on_v), 4) if on_v else None,
            "min": min(on_v) if on_v else None,
            "max": max(on_v) if on_v else None,
        },
        "power_w": {
            "mean": round(statistics.fmean(on_p), 4) if on_p else None,
            "max": max(on_p) if on_p else None,
        },
        "caveat": ("Bench H8 image (grammar H8S), 100% duty. Production-stage W06 "
                   "verification of the active range remains part of A-W08-03/W16-01."),
    }

    output = {
        "schema": "cg-w09-healthy-ranges-s1-v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "authority": ("docs/05A section 18 (A-W09-04 input) — measurement-only; "
                      "acceptance of A-W09-04 stays gated on A-W08-03"),
        "evidence_kind": "HOST_ANALYSIS_OF_COMMITTED_DATASETS",
        "touches_hardware": False,
        "physical_verified": False,
        "identity": identity,
        "dataset": ("PR #91 (merged) evidence/A/SOURCES/20261107/datasets "
                    "(manifest.json: 18 runs, 9293 frames)"),
        "inputs": inputs,
        "s1_passive_runs": s1_stats,
        "pooled_passive_noise_trend_immune": pooled,
        "sampling_cadence_s": {
            "mean": round(statistics.fmean(cadence_s), 4) if cadence_s else None,
            "min": round(min(cadence_s), 4) if cadence_s else None,
            "max": round(max(cadence_s), 4) if cadence_s else None,
        },
        "off_electrical_envelope_s1": off_summary,
        "active_electrical_range_h8c": active,
        "excluded": {
            "w07_passive_repeats": ("a-w07-02-run-1..3: compact capture records without "
                                    "full 4-probe rows; excluded from thermal statistics, "
                                    "kept in the dataset manifest."),
        },
        "limitations": [
            "Derived offline from committed captures; no new physical measurement performed.",
            "S1 trials are passive warm-up/near-steady runs at room ambient; the active ON "
            "segment comes from the bench H8-C capture (production-stage ON evidence is A-W08-03).",
            "Trend-immune second-difference sigma follows the W09-era estimator; per-run "
            "ambient drift is recorded in per-run tmean ols_slope_c_per_s.",
        ],
    }

    out_path = pathlib.Path(__file__).resolve().parent / "healthy-ranges-s1-20261109.json"
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"WROTE {out_path}")
    assert off_summary["voltage_v"]["min"] and off_summary["voltage_v"]["min"] > 11.0, \
        "voltage out of expected rail"
    if active["current_a"]["max"]:
        assert active["current_a"]["max"] <= 10.0, "active current exceeds 10 A provisional ceiling"
    print("SANITY CHECKS PASS (OFF rail >11 V, active max I <=10 A)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
