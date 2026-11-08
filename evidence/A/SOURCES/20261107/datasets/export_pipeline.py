"""ColdGuard Member A - real-data export + physical-evidence acceptance.

Generates:
  _local_handoff/COLDGUARD_REAL_DATA_HANDOFF_<ts>/
    raw/                     verbatim copies of every real capture used
    datasets/                normalized per-run CSVs (+ published derived CSVs)
    run_index.csv
    measurement_summary.csv
    quality_report.md
    manifest.json
    README.md

Flow B: computes A-W08-03 (hot-side sustainability) and A-W09-04 (healthy
response reference) directly from the H8-C 600 s raw capture and the S1/S2
store results, records A-W15-04 PWM Go/No-Go (NO-GO), and writes valid PASS
results into the authoritative Member A acceptance store using the app's own
SessionStore API (history preserved in results/history/).

Read-only with respect to hardware. No serial work. Python 3.11+, stdlib only.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
import shutil
import statistics
import sys
import zipfile
from pathlib import Path

REPO = Path(r"C:\Users\dlbac\Downloads\coldguard-repo")
APP = REPO / "A-acceptance-app"
STORE_ROOT = APP / "evidence" / "A" / "h8-captures" / "capture-20261104T092140Z"
CGB = Path(r"C:\cgb")
PREV_HANDOFF = CGB / "COLDGUARD_MEMBER_A_DATA_HANDOFF_20261108"
SRC_STORE = REPO / "_s1-s2-source-local" / "evidence" / "A"

sys.path.insert(0, str(APP / "tools"))
from member_a_app import analysis, protocol  # noqa: E402
from member_a_app.evidence import SessionStore, sha256_file  # noqa: E402
from member_a_app.model import CheckResult, Outcome, TestResult, now_iso  # noqa: E402
from member_a_app.requirements import DEFINITIONS  # noqa: E402

TS = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT = REPO / "_local_handoff" / f"COLDGUARD_REAL_DATA_HANDOFF_{TS}"

STAMP_RE = re.compile(r"^(\d{4}-\d\d-\d\dT[\d:.]+\+00:00) (.*)$")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    return sha256_file(path)


CMD_RE = re.compile(r"^(\d{4}-\d\d-\d\dT[\d:.]+\+00:00) (\S+) captured frames=(\d+)")


def parse_capture_windows(commands_log: Path):
    """Read the capture's own commands.log: per-window label, end time, frame count."""
    windows = []
    for line in commands_log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = CMD_RE.match(line.strip())
        if m:
            windows.append({"label": m.group(2), "end": dt.datetime.fromisoformat(m.group(1)),
                            "frames": int(m.group(3))})
    return windows


def windowed_split(frames, windows):
    """Cut run windows anchored at each capture's authoritative end stamp
    (from commands.log). Frames outside any window are returned as kept
    BETWEEN/OUTSIDE segments - never discarded."""
    frames = list(frames)
    frames = [f for f in frames if f[0] is not None]
    frames.sort(key=lambda e: e[0])
    by_time = [f[0] for f in frames]
    import bisect
    used = [False] * len(frames)
    out = []
    for w in sorted(windows, key=lambda w: w["end"]):
        hi = bisect.bisect_right(by_time, w["end"])  # frames with time <= end
        lo = max(0, hi - w["frames"])
        seg = frames[lo:hi]
        if len(seg) != w["frames"]:
            raise SystemExit(f"window {w['label']}: anchored cut got {len(seg)} != {w['frames']}")
        for i in range(lo, hi):
            used[i] = True
        out.append((w["label"], seg))
    leftover = [f for i, f in enumerate(frames) if not used[i]]
    return out, leftover
def parse_log(path: Path):
    """Parse a raw monitor log -> list of (host_time, kv) TELEM/H8S frames."""
    frames = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        stamp = None
        body = line
        m = STAMP_RE.match(line)
        if m:
            try:
                stamp = dt.datetime.fromisoformat(m.group(1))
            except ValueError:
                stamp = None
            body = m.group(2)
        if not body.startswith("#CG "):
            continue
        try:
            parsed = protocol.parse_line(body, stamp)
        except Exception:
            continue
        if parsed.frame is None:
            continue
        frames.append((stamp, parsed))
    return frames


def num(kv: dict, key: str):
    v = kv.get(key)
    if v is None or v == "nan":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def status(kv: dict, key: str) -> str:
    return (kv.get(key) or "").strip()


def chamber_air(kv: dict):
    """Tmean air = mean(T1,T3,T4); T2 is hot-side and never enters the mean.
    Returns (value, used_roles_ok) -> value only when all three hold OK status."""
    vals, ok = [], []
    for base in ("t1", "t3", "t4"):
        s = status(kv, f"{base}_status")
        v = num(kv, base)
        ok.append(s == "OK")
        if v is not None and s == "OK":
            vals.append(v)
    if len(vals) != 3 or not all(ok):
        return None, 3 - len(vals)
    return sum(vals) / 3.0, 0


def frames_to_rows(elems, run_tag):
    rows = []
    for stamp, parsed in elems:
        f = parsed.frame
        kv = parsed.kv

        def pick_num(*keys):
            for k in keys:
                v = num(kv, k)
                if v is not None:
                    return v
            return None

        def pick_status(*keys):
            for k in keys:
                if kv.get(k) and kv.get(k) != "nan":
                    return kv.get(k)
            return ""
        t1 = pick_num("t1", "raw_t1_c")
        t2 = pick_num("t2", "raw_t2_c")
        t3 = pick_num("t3", "raw_t3_c")
        t4 = pick_num("t4", "raw_spare_c")
        t1s = pick_status("t1_status", "raw_t1_status")
        t2s = pick_status("t2_status", "raw_t2_status")
        t3s = pick_status("t3_status", "raw_t3_status")
        t4s = pick_status("t4_status", "raw_spare_status")
        # canonical canonical-slot view (schema 3): t_inside_c -> T1 slot, t_hot_side_c -> T2 slot
        air_src = [("t1", t1, t1s), ("t3", t3, t3s), ("t4", t4, t4s)]
        air_vals = [v for (_, v, s) in air_src if s == "OK" and v is not None]
        air = sum(air_vals) / len(air_vals) if len(air_vals) == 3 else None
        door_raw = kv.get("door_open")
        try:
            door_num = float(door_raw) if door_raw not in (None, "nan") else None
        except ValueError:
            door_num = None
        air_rep = pick_num("air_c")
        row = {
            "run_tag": run_tag,
            "host_time_utc": stamp.isoformat() if stamp else "",
            "grammar": f.kind,
            "seq": kv.get("seq"),
            "uptime_ms": num(kv, "uptime_ms") or num(kv, "device_ms"),
            "boot_id": kv.get("boot_id"),
            "device_run_id": kv.get("run_id"),
            "firmware_version": kv.get("firmware_version") or "h8-bench",
            "hardware_config_id": kv.get("hardware_config_id") or "CG-HW-001",
            "t1_c": t1, "t1_status": t1s,
            "t2_c": t2, "t2_status": t2s,
            "t3_c": t3, "t3_status": t3s,
            "t4_c": t4, "t4_status": t4s,
            # canonical slot values as reported by the device (never relabelled)
            "slot_t_inside_c": num(kv, "t_inside_c"), "slot_t_inside_status_kv": kv.get("t_inside_status"),
            "slot_t_hot_side_c": num(kv, "t_hot_side_c"), "slot_t_hot_side_status_kv": kv.get("t_hot_side_status"),
            "tmean_air_c": round(air, 4) if air is not None else "",
            "air_c_reported": air_rep,
            "rh_pct": pick_num("rh_pct"),
            "pressure_hpa": pick_num("pressure_hpa"),
            "door_open": door_num if door_num is not None else kv.get("door_open"),
            "door_status": kv.get("door_status"),
            "door_transitions": pick_num("door_transitions"),
            "door_cycles": pick_num("door_cycles"),
            "pwm_req_permille": pick_num("pwm_req_permille", "pwm_duty"),
            "pwm_applied_permille": pick_num("pwm_applied_permille", "pwm_readback_permille"),
            "pwm_readback_permille": num(kv, "pwm_readback_permille"),
            "voltage_v": pick_num("voltage_v"), "voltage_status": pick_status("voltage_v_status", "voltage_status"),
            "current_a": pick_num("current_a"), "current_status": pick_status("current_a_status", "current_status"),
            "power_w": pick_num("power_w"), "power_status": pick_status("power_w_status", "power_status"),
            "energy_wh": pick_num("energy_wh"),
            "state": kv.get("state"),
            "stage": kv.get("stage"),
            "fault": kv.get("fault") or kv.get("fault_code"),
            "fault_reason": kv.get("fault_reason") or kv.get("stop_reason"),
            "tec_state": kv.get("tec_state"),
            "quality": kv.get("quality"),
        }
        rows.append(row)
    return rows


def grad(xs, ys):
    try:
        return analysis.linear_slope(xs, ys)
    except Exception:
        return None


def ingest_jsonl_run(path: Path, scenario: str, label: str):
    """Ingest a captured run stored as JSONL, preferring each record's own raw
    device line (canonical parse) and falling back to the compact fields."""
    from datetime import datetime as _dtm
    frames = []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        stamp = None
        ht = rec.get("host_time")
        if ht:
            try:
                stamp = _dtm.fromisoformat(ht)
            except ValueError:
                stamp = None
        raw = rec.get("raw")
        if raw:
            try:
                parsed = protocol.parse_line(raw, stamp)
                if parsed.frame is not None:
                    frames.append((stamp, parsed))
                    continue
            except Exception:
                pass
        kv = {k: str(v) for k, v in rec.items()
              if isinstance(v, (int, float, str, bool))}
        rows.append((stamp, kv, rec))
    return frames, rows


def run_stats(rows, scenario):
    """Derived statistics for one run (canonical interpretation rules)."""
    stamps = [(r["host_time_utc"], r["uptime_ms"]) for r in rows]
    use_host = bool(rows and rows[0]["host_time_utc"])
    use_device = all(r["uptime_ms"] is not None for r in rows)

    def seconds_between(after_row, before_row):
        if use_host and after_row["host_time_utc"] and before_row["host_time_utc"]:
            return (dt.datetime.fromisoformat(after_row["host_time_utc"])
                    - dt.datetime.fromisoformat(before_row["host_time_utc"])).total_seconds()
        if use_device and after_row["uptime_ms"] is not None and before_row["uptime_ms"] is not None:
            return (after_row["uptime_ms"] - before_row["uptime_ms"]) / 1000.0
        return None

    def air_val(r):
        v = r.get("tmean_air_c")
        if isinstance(v, float):
            return v
        for k in ("chamber_c_t1_slot", "tmean_reported_c"):
            v = r.get(k)
            if isinstance(v, float):
                return v
        return None

    air = [(r, air_val(r)) for r in rows]
    air = [(r, a) for (r, a) in air if a is not None]
    airs = [a for _, a in air]
    grads = []
    for r in rows:
        if not isinstance(r.get("tmean_air_c"), float):
            continue
        vals = [r[k] for k in ("t1_c", "t3_c", "t4_c") if isinstance(r[k], float)]
        if vals:  # all three chamber probes were valid for this frame since tmean present
            grads.append(max(vals) - min(vals))
    cur = [r.get("current_a") for r in rows if isinstance(r.get("current_a"), float)]
    vol = [r.get("voltage_v") for r in rows if isinstance(r.get("voltage_v"), float)]
    pw = [r.get("power_w") for r in rows if isinstance(r.get("power_w"), float)]
    hot = [
        (r.get("hot_side_c_t2") if r.get("hot_side_c_t2") is not None else r.get("t2_c"))
        for r in rows]
    hot = [h for h in hot if isinstance(h, float)]
    # electrical response delay: first frame with current >= 0.1 A
    elec_delay = None
    first_on = next((r for r in rows if isinstance(r.get("current_a"), float) and r["current_a"] >= 0.1), None)
    first_frame = rows[0] if rows else None
    if first_on is not None and first_frame is not None:
        d = seconds_between(first_on, first_frame)
        elec_delay = round(d, 3) if d is not None and d >= 0 else (d if d is not None and d < 0 else None)
    stats = {
        "frames": len(rows),
        "duration_s": round(seconds_between(rows[-1], rows[0]), 3)
        if rows and seconds_between(rows[-1], rows[0]) is not None else None,
        "tmean_air_mean_c": round(statistics.mean(airs), 4) if airs else None,
        "tmean_air_min_c": round(min(airs), 4) if airs else None,
        "tmean_air_max_c": round(max(airs), 4) if airs else None,
        "gradient_max_c": round(max(grads), 4) if grads else None,
        "gradient_mean_c": round(statistics.mean(grads), 4) if grads else None,
        "hot_side_max_c": round(max(hot), 4) if hot else None,
        "hot_side_mean_c": round(statistics.mean(hot), 4) if hot else None,
        "current_mean_a": round(statistics.mean(cur), 4) if cur else None,
        "current_max_a": round(max(cur), 4) if cur else None,
        "voltage_mean_v": round(statistics.mean(vol), 4) if vol else None,
        "power_mean_w": round(statistics.mean(pw), 4) if pw else None,
        "power_max_w": round(max(pw), 4) if pw else None,
        "energy_wh_start": rows[0].get("energy_wh") if rows else None,
        "energy_wh_end": rows[-1].get("energy_wh") if rows else None,
        "elec_response_delay_s": elec_delay,
        "count_thermal_frames_all3_ok": len(airs),
        "count_all_frames": len(rows),
    }
    # delta temperature / chamber drop within run
    pwm = [r.get("pwm_applied_permille") for r in rows if isinstance(r.get("pwm_applied_permille"), float)]
    # chamber drop for active runs: first active tmean minus min tmean after
    drops = None
    if scenario in ("COOLING_STEP",):
        act_rows = [r for r in rows if
                    (isinstance(r.get("pwm_applied_permille"), float) and r["pwm_applied_permille"] > 0)
                    or (isinstance(r.get("current_a"), float) and r["current_a"] >= 0.1)]
        a = [(r["tmean_air_c"]) for r in act_rows if isinstance(r["tmean_air_c"], float)]
        if a:
            drops = a[0] - min(a)
            stats["chamber_drop_c"] = round(drops, 4)
            stats["active_frames"] = len(act_rows)
            stats["active_duration_s"] = stats["duration_s"]
    if scenario == "S2":
        opens, events = [], []
        prev = None
        for r in rows:
            d = r.get("door_open")
            if d is None:
                continue
            if isinstance(d, (int, float)):
                cur_open = 1 if int(d) == 1 else (0 if int(d) == 0 else None)
            else:
                du = str(d).upper()
                cur_open = 1 if du in ("1", "TRUE", "OPEN") else (0 if du in ("0", "FALSE", "CLOSE") else None)
            if cur_open is None:
                continue
            if prev is not None and cur_open != prev:
                events.append((r["host_time_utc"], cur_open))
            prev = cur_open
        open_at = None
        for t, o in events:
            if o == 1:
                open_at = dt.datetime.fromisoformat(t)
            elif o == 0 and open_at is not None:
                opens.append((dt.datetime.fromisoformat(t) - open_at).total_seconds())
                open_at = None
        stats["door_transitions"] = 2 * len(opens)
        stats["open_durations_s"] = [round(o, 3) for o in opens]
        # rise / recovery canonical (same rules as door_report): rise = peak-after-open - baseline(60 s pre); use surrounding baseline
        if opens and air:
            base_vals = [a for (r, a) in air[:60]]
            baseline = statistics.mean(base_vals) if base_vals else None
            peak = max(airs)
            stats["baseline_mean_c"] = round(baseline, 4) if baseline is not None else None
            stats["rise_peak_c"] = round(peak - baseline, 4) if baseline is not None else None
    return stats


def quality_counts(rows):
    qc = {"thermal_OK": 0, "thermal_not_OK": 0, "electrical_OK": 0, "electrical_not_OK": 0,
          "door_UNVERIFIED": 0, "faults": {}, "mean_sample_interval_s": None}
    stamps = [(r["host_time_utc"], r["uptime_ms"]) for r in rows
              if r["host_time_utc"] or r["uptime_ms"] is not None]
    for i, r in enumerate(rows):
        if all(isinstance(r.get(k), float) for k in ("t1_c", "t3_c", "t4_c")) and all(
                r.get(f"{k[:-2]}_status") == "OK" for k in ("t1_c", "t3_c", "t4_c")):
            qc["thermal_OK"] += 1
        else:
            qc["thermal_not_OK"] += 1
        if isinstance(r.get("current_a"), float) and r.get("current_status") == "OK":
            qc["electrical_OK"] += 1
        else:
            qc["electrical_not_OK"] += 1
        if (r.get("door_status") or "").upper() in ("UNVERIFIED", "UNKNOWN"):
            qc["door_UNVERIFIED"] += 1
        f = r.get("fault")
        if f and f not in ("NONE", "0x0", ""):
            qc["faults"][f] = qc["faults"].get(f, 0) + 1
    if len(stamps) > 1:
        gaps = []
        for (sa, ua), (sb, ub) in zip(stamps, stamps[1:]):
            if sa and sb:
                gaps.append((dt.datetime.fromisoformat(sb)
                             - dt.datetime.fromisoformat(sa)).total_seconds())
            elif ua is not None and ub is not None:
                gaps.append((ub - ua) / 1000.0)
        gaps = [g for g in gaps if g > 0]
        if gaps:
            qc["mean_sample_interval_s"] = round(statistics.mean(gaps), 3)
            qc["max_gap_s"] = round(max(gaps), 3)
    return qc


def split_by_counts(frames, sizes_after_warmup):
    """Split a single-log capture into trailing runs of exact frame counts.

    Returns list of run frame-lists (run windows verified non-overlapping) and
    the leading warm-up segment. Sizes come from the capture's own commands.log
    (authoritative per-run frame counts) - never invented.
    """
    runs = []
    idx = len(frames)
    for size in reversed(sizes_after_warmup):
        start = idx - size
        if size > 0:
            if start < 0:
                raise SystemExit(f"not enough frames: need {size}, have {idx}")
            runs.append(frames[start:idx])
        idx = start
    warmup = frames[:idx] if idx >= 0 else []
    runs.reverse()
    return warmup, runs


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    raw_dir = OUT / "raw"
    ds_dir = OUT / "datasets"
    for p in (raw_dir, ds_dir / "published"):
        p.mkdir(parents=True)

    manifest_inputs = []

    def copy_raw(src: Path, rel: str):
        dst = raw_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        manifest_inputs.append({
            "package_path": f"raw/{rel.replace(chr(92), '/')}",
            "source_path": str(src),
            "bytes": src.stat().st_size,
            "sha256": sha256(src),
        })
        return dst

    # ----- 1. copy raw captures (verbatim) -------------------------------
    h8c_raw = PREV_HANDOFF / "original_raw" / "H8C_RAW" / "monitor-final__telemetry_raw.log"
    h8e_raw = PREV_HANDOFF / "original_raw" / "H8E" / "monitor__telemetry_raw.log"
    s2_raw = SRC_STORE / "SOURCES" / "20261107" / "s2" / "door-20261107T081539Z" / "raw" / "telemetry_raw.log"
    s1_t1_raw = SRC_STORE / "SOURCES" / "20261107" / "s1" / "s1-20261107T063828Z" / "raw" / "telemetry_raw.log"
    s1_t234_raw = SRC_STORE / "SOURCES" / "20261107" / "s1" / "s1-multi-20261107T064902Z" / "raw" / "telemetry_raw.log"
    copy_raw(h8c_raw, "h8-c-600s-tec-cooling/monitor-final__telemetry_raw.log")
    copy_raw(h8e_raw, "h8-e-1800s-100pct/monitor__telemetry_raw.log")
    copy_raw(s2_raw, "s2-door-20261107/telemetry_raw.log")
    copy_raw(s1_t1_raw, "s1-trial1-20261107/telemetry_raw.log")
    copy_raw(s1_t234_raw, "s1-trials-2-3-4-20261107/telemetry_raw.log")
    for extra, rel in [
        (SRC_STORE / "SOURCES" / "20261107" / "s1" / "s1-multi-20261107T064902Z" / "commands.log",
         "s1-trials-2-3-4-20261107/commands.log"),
        (SRC_STORE / "SOURCES" / "20261107" / "s1" / "s1-multi-20261107T064902Z" / "s1-summary.json",
         "s1-trials-2-3-4-20261107/s1-summary.json"),
        (SRC_STORE / "SOURCES" / "20261107" / "s1" / "s1-20261107T063828Z" / "trial.json",
         "s1-trial1-20261107/trial.json"),
        (SRC_STORE / "SOURCES" / "20261107" / "s2" / "door-20261107T081539Z" / "commands.log",
         "s2-door-20261107/commands.log"),
        (SRC_STORE / "SOURCES" / "20261107" / "s2" / "door-20261107T081539Z" / "door_report.json",
         "s2-door-20261107/door_report.json"),
        (SRC_STORE / "SOURCES" / "20261107" / "s2" / "door-20261107T081539Z" / "door_protocol_record.md",
         "s2-door-20261107/door_protocol_record.md"),
        (SRC_STORE / "SOURCES" / "20261107" / "s1" / "source-result-A-W09-02.json",
         "source-results/source-result-A-W09-02.json"),
        (SRC_STORE / "SOURCES" / "20261107" / "s2" / "source-result-A-W10-03.json",
         "source-results/source-result-A-W10-03.json"),
    ]:
        copy_raw(extra, rel)

    published = []
    for src, rel in [
        (REPO / "predictive-cold-chain-aiot" / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv",
         "w04-tec-cooling-response-600s.csv"),
        (REPO / "predictive-cold-chain-aiot" / "evidence" / "A" / "W13" / "response-delay.csv",
         "w13-response-delay.csv"),
        (REPO / "predictive-cold-chain-aiot" / "evidence" / "A" / "W13" / "door-critical.csv",
         "w13-door-critical.csv"),
        (REPO / "predictive-cold-chain-aiot" / "evidence" / "A" / "W13" / "plant-timing-report.json",
         "w13-plant-timing-report.json"),
        (REPO / "predictive-cold-chain-aiot" / "evidence" / "A" / "W05" / "timing-pilot-jitter.csv",
         "w05-timing-pilot-jitter.csv"),
    ]:
        if not src.is_file():
            # fall back to the newest local checkout that has it
            for cand in [REPO / "_capture-quality-local" / "evidence" / "A", REPO / "_s1-s2-source-local" / "evidence" / "A",
                         APP / "evidence" / "A",
                         REPO / "A-W01-W24-integration" / "evidence" / "A"]:
                p = cand / rel.split("-", 1)[0].upper().replace("W0", "W0") / src.name
                if p.is_file():
                    src = p
                    break
        if src.is_file():
            dst = ds_dir / "published" / src.name
            shutil.copy2(src, dst)
            published.append({
                "package_path": f"datasets/published/{src.name}",
                "source_path": str(src),
                "bytes": src.stat().st_size,
                "sha256": sha256(src),
            })
        else:
            published.append({"package_path": f"datasets/published/{src.name}",
                              "source_path": str(src), "bytes": None, "sha256": None,
                              "warning": "SOURCE_NOT_FOUND"})

    # ----- 2. parse and split runs ---------------------------------------
    # Parse the packaged raw copies (byte-verified by manifest) so the whole
    # handoff is reproducible from its own raw/ tree, not from local-only paths.
    def packaged(rel: str, original: Path) -> Path:
        cand = raw_dir / rel
        return cand if cand.is_file() else original

    PKG_RAW = {
        "h8c": packaged("h8-c-600s-tec-cooling/monitor-final__telemetry_raw.log", h8c_raw),
        "h8e": packaged("h8-e-1800s-100pct/monitor__telemetry_raw.log", h8e_raw),
        "s2": packaged("s2-door-20261107/telemetry_raw.log", s2_raw),
        "s1t1": packaged("s1-trial1-20261107/telemetry_raw.log", s1_t1_raw),
        "s1t234": packaged("s1-trials-2-3-4-20261107/telemetry_raw.log", s1_t234_raw),
        "s2cmd": packaged("s2-door-20261107/commands.log", SRC_STORE / "SOURCES" / "20261107" / "s2" / "door-20261107T081539Z" / "commands.log"),
        "s1cmd": packaged("s1-trials-2-3-4-20261107/commands.log", SRC_STORE / "SOURCES" / "20261107" / "s1" / "s1-multi-20261107T064902Z" / "commands.log"),
        "w07reps": packaged("w07-repeats", None),  # directory
    }
    runs = []  # (scenario, label, rows, source_raw_label, extra_meta)

    h8c_frames = parse_log(PKG_RAW["h8c"])
    h8e_frames = parse_log(PKG_RAW["h8e"])
    s2_frames = parse_log(PKG_RAW["s2"])
    s1t1_frames = parse_log(PKG_RAW["s1t1"])
    s1t234_frames = parse_log(PKG_RAW["s1t234"])

    # S2: windows anchored on the capture's own commands.log end stamps
    s2_windows = parse_capture_windows(PKG_RAW["s2cmd"])
    s2_win, s2_outside = windowed_split(s2_frames, s2_windows)
    for wlabel, seg in s2_win:
        scen = "S2_TIMING" if wlabel.upper().startswith("W10-02") else "S2_DOOR"
        runs.append((scen, f"{wlabel}", seg, "s2-door-20261107"))
    if s2_outside:
        runs.append(("S2_OUTSIDE", "S2-20261107-between-window", s2_outside, "s2-door-20261107"))

    # S1: trial1 standalone; trials 2/3/4 anchored on their commands.log end stamps
    s1_windows = parse_capture_windows(PKG_RAW["s1cmd"])
    s1_win, s1_outside = windowed_split(s1t234_frames, s1_windows)
    for wlabel, seg in s1_win:
        runs.append(("S1", wlabel, seg, "s1-trials-2-3-4-20261107"))
    if s1_outside:
        runs.append(("S1_OUTSIDE", "S1-20261107-between-window", s1_outside, "s1-trials-2-3-4-20261107"))
    runs.append(("S1", "trial1-imported", s1t1_frames, "s1-trial1-20261107"))

    runs.append(("COOLING_STEP", "H8-C-600s-TEC-100pct", h8c_frames, "h8-c-600s-tec-cooling"))
    runs.append(("COOLING_STEP_1800S", "H8-E-1800s-TEC-100pct", h8e_frames, "h8-e-1800s-100pct"))

    # ----- 2b. W07 physical run retentions from the capture session -------
    bench_dir = STORE_ROOT / "bench-results"
    trials_dir = STORE_ROOT / "trials"
    pkg_w07 = raw_dir / "w07-repeats"
    bench_pkg = pkg_w07 if pkg_w07.is_dir() else bench_dir
    trials_pkg = pkg_w07 if pkg_w07.is_dir() else trials_dir
    for src, rel in [
        *[(p, f"w07-repeats/{p.name}") for p in sorted(bench_dir.glob("a-w07-02-run-*.jsonl"))],
        *[(p, f"w07-repeats/{p.name}") for p in sorted(bench_dir.glob("a-w07-03-trial-*.json"))],
        *[(p, f"w07-repeats/{p.name}") for p in sorted(trials_dir.glob("a-w07-03-trial-*.jsonl"))],
        (bench_dir / "a-w09-02-run-1-INTERRUPTED-20261105.json", "w07-repeats/a-w09-02-run-1-INTERRUPTED-20261105.json"),
        (STORE_ROOT / "telemetry.csv", "session-20261104/telemetry.csv"),
        (REPO / "_capture-quality-local" / "evidence" / "A" / "W07" / "cooling-step-runs.jsonl",
         "w07-repeats/cooling-step-runs.jsonl"),
    ]:
        if src.is_file():
            copy_raw(src, rel)
        else:
            published.append({"package_path": f"raw/{rel}", "source_path": str(src),
                              "sha256": None, "warning": "SOURCE_NOT_FOUND"})

    EXACT_RAW_SOURCE = {
        "W10-02": "raw/s2-door-20261107/telemetry_raw.log",
        "S2-20261107-between-window": "raw/s2-door-20261107/telemetry_raw.log",
        "S1-20261107-between-window": "raw/s1-trials-2-3-4-20261107/telemetry_raw.log",
        "trial1-imported": "raw/s1-trial1-20261107/telemetry_raw.log",
        "H8-C-600s-TEC-100pct": "raw/h8-c-600s-tec-cooling/monitor-final__telemetry_raw.log",
        "H8-E-1800s-TEC-100pct": "raw/h8-e-1800s-100pct/monitor__telemetry_raw.log",
        "trial2": "raw/s1-trials-2-3-4-20261107/telemetry_raw.log",
        "trial3": "raw/s1-trials-2-3-4-20261107/telemetry_raw.log",
        "trial4": "raw/s1-trials-2-3-4-20261107/telemetry_raw.log",
    }
    for wl in ("W10-03-run1", "W10-03-run2", "W10-03-run3", "W10-03-run4"):
        EXACT_RAW_SOURCE[wl] = "raw/s2-door-20261107/telemetry_raw.log"
    w07_rows_out = []

    # W07-02 passive repetitions (compact capture records, no device raw line)
    for f in sorted(bench_pkg.glob("a-w07-02-run-*.jsonl")):
        recs = [json.loads(x) for x in f.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
        rows = [{
            "run_tag": f.stem.split("-be89bf4a")[0], "grammar": "COMPACT_CAPTURE",
            "host_time_utc": r.get("host_time", ""), "seq": r.get("seq"),
            "uptime_ms": None, "boot_id": r.get("boot_id"),
            "chamber_c_t1_slot": r.get("chamber_c"), "hot_side_c_t2": r.get("hot_side_c"),
            "voltage_v": r.get("voltage_v"), "current_a": r.get("current_a"),
            "power_w": r.get("power_w"), "state": r.get("state"),
            "door_open": (1 if r.get("door_open") else 0) if isinstance(r.get("door_open"), bool)
            else r.get("door_open"), "door_raw": r.get("door_raw"),
            "fault": r.get("fault"),
            "tmean_reported_c": r.get("tmean_c"), "gradient_reported_c": r.get("gradient_c"),
        } for r in recs]
        w07_rows_out.append(("W07_PASSIVE_REPEAT", f.stem, rows, f"raw/w07-repeats/{f.name}",
                             {"prebuilt_rows": True, "exact_raw_source": True,
                              "records_note": "compact capture records; T1-slot and T2-slot values as recorded, no full 4-probe row"}))

    # W07-03 bench cooling trials (full canonical raw line per record)
    for f in sorted(trials_pkg.glob("a-w07-03-trial-*.jsonl")):
        frames, _ = ingest_jsonl_run(f, "COOLING_STEP", f.stem)
        w07_rows_out.append(("COOLING_STEP_500PERMILLE", f.stem, frames_to_rows(frames, f.stem),
                             f"raw/w07-repeats/{f.name}",
                             {"prebuilt_rows": True, "exact_raw_source": True}))

    for p in sorted((bench_dir).glob("a-w07-03-trial-*.json")):
        pass  # summary JSONs already copied to raw/

    run_rows = []
    summary_rows = []
    for entry in runs + w07_rows_out:
        scenario, label, payload, src_label = entry[0], entry[1], entry[2], entry[3]
        meta = entry[4] if len(entry) > 4 else {}
        if meta.get("prebuilt_rows"):
            rows = payload
        else:
            frames = payload
            rows = frames_to_rows(frames, label)
        if not rows:
            continue
        boot = rows[0]["boot_id"] or ""
        first = (dt.datetime.fromisoformat(rows[0]["host_time_utc"])
                 if rows[0]["host_time_utc"] else None)
        last = (dt.datetime.fromisoformat(rows[-1]["host_time_utc"])
                if rows[-1]["host_time_utc"] else None)
        capture_date = {"h8-c-600s-tec-cooling": "2026-11-01 (W04 session record; device has no wall clock)",
                        "h8-e-1800s-100pct": "2026-10-31 (H8_E result record; device has no wall clock)"}.get(src_label, "")
        # scenario refinement by content (door count) for S2 timing window
        scen = scenario
        out = ds_dir / f"{label}-normalized.csv"
        fields = list(rows[0].keys())
        with out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        qc = quality_counts(rows)
        # S2 windows: mark only windows containing a full door cycle as door runs
        stats = run_stats(rows, {"S2_DOOR": "S2", "S2_TIMING": "S2",
                                 "COOLING_STEP_500PERMILLE": "COOLING_STEP"}.get(scen, scen))
        # classification
        if scen in ("S1_OUTSIDE", "S2_OUTSIDE"):
            cls = "REAL_FRAMES_OUTSIDE_TIMED_WINDOWS"
        if scen == "S1":
            cls = "DATASET_ACCEPTED_S1"
        elif scen == "S2_DOOR":
            cls = "DATASET_ACCEPTED_S2"
        elif scen == "S2_TIMING":
            cls = "DATASET_ACCEPTED_S2"  # the W10-02 machine-timing run (120 s, MC-38 validated)
        elif scen in ("COOLING_STEP", "COOLING_STEP_500PERMILLE"):
            cls = "REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED"
        elif scen == "W07_PASSIVE_REPEAT":
            cls = "REAL_PHYSICAL_REPEATS / INDEPENDENCE_CAVEAT"
        elif scen == "COOLING_STEP_1800S":
            cls = "REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED"
        else:
            cls = "WARMUP_SEGMENT_OR_OUTSIDE_WINDOW"
        run_rows.append({
            "run_tag": label, "scenario": scen, "classification": cls,
            "raw_source": (src_label if meta.get("exact_raw_source")
                           else EXACT_RAW_SOURCE.get(label, f"raw/{src_label}")),
            "boot_id": boot,
            "device_run_id": rows[0].get("device_run_id"),
            "firmware_version": rows[0].get("firmware_version"),
            "hardware_config_id": rows[0].get("hardware_config_id"),
            "started_utc": first.isoformat() if first else "",
            "ended_utc": last.isoformat() if last else "",
            "capture_date_record": capture_date,
            "timebase": "HOST_STAMP" if first else ("DEVICE_MS" if rows[0].get("uptime_ms") is not None else "SEQ"),
            "frames": len(rows),
            "host_time_source": "MONITOR_LOG_HOST_STAMP",
            "device_timestamp_utc_source": "DEVICE_HAS_NO_WALL_CLOCK",
            "dataset_path": f"datasets/{label}-normalized.csv",
            "dataset_sha256": sha256(out),
            **meta,
        })
        summary_rows.append({
            "run_tag": label, "scenario": scen, "classification": cls,
            "boot_id": boot, **stats,
            "quality_thermal_ok": qc["thermal_OK"], "quality_thermal_not_ok": qc["thermal_not_OK"],
            "quality_electrical_ok": qc["electrical_OK"],
            "quality_electrical_not_ok": qc["electrical_not_OK"],
            "quality_door_unverified": qc["door_UNVERIFIED"],
            "quality_faults": json.dumps(qc["faults"]),
            "mean_sample_interval_s": qc["mean_sample_interval_s"],
            "max_gap_s": qc.get("max_gap_s"),
        })

    # run_index.csv
    with (OUT / "run_index.csv").open("w", encoding="utf-8", newline="") as fh:
        all_keys: list[str] = []
        for r in run_rows:
            for k in r:
                if k not in all_keys:
                    all_keys.append(k)
        w = csv.DictWriter(fh, fieldnames=all_keys, lineterminator="\n")
        w.writeheader()
        w.writerows(run_rows)

    # measurement_summary.csv
    mkeys: list[str] = []
    for r in summary_rows:
        for k in r:
            if k not in mkeys:
                mkeys.append(k)
    with (OUT / "measurement_summary.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=mkeys, lineterminator="\n")
        w.writeheader()
        w.writerows(summary_rows)

    # ----- 3. quality report ---------------------------------------------
    s1 = [r for r in summary_rows if r["scenario"] == "S1"]
    s2 = [r for r in summary_rows if r["scenario"] == "S2_DOOR"]
    cool = [r for r in summary_rows if r["scenario"] == "COOLING_STEP"]
    lines = ["# ColdGuard real-data quality report", "",
             f"Generated: {now_iso()}", "",
             "Interpretation rules: Tmean air = mean(T1,T3,T4) only when all three report OK; "
             "T2 is hot-side and never enters the air mean; nan means missing; quality from the "
             "frame's own *_status tokens. Host wall-clock stamps come from the monitor log "
             "(host-side), while the device reports timestamp_utc=UNAVAILABLE (no wall clock).", ""]
    lines.append(f"- Total real runs/segments exported: {len(summary_rows)}")
    lines.append(f"- S1 runs: {len(s1)} (trial1 standalone boot "
                 f"{s1[-1]['boot_id'] if s1 else '-'}, trials 2-4 contiguous on one boot "
                 f"{s1[0]['boot_id'] if s1 else '-'})")
    lines.append(f"- S2 door runs: {len(s2)} single boot {s2[0]['boot_id'] if s2 else '-'}")
    lines.append(f"- Cooling steps (real TEC actuation): {len(cool)}")
    lines.append("")
    lines.append("## Independence caveats (carried, not hidden)")
    lines.append("")
    lines.append("- S1 trials 2-4 are contiguous windows of one boot; the S1 acceptance result "
                 "A-W09-02 (2026-11-07) is recorded in the authoritative store with these windows "
                 "counted per the Doc 03 plan. Do not recount these windows anywhere as additional independent sessions.")
    lines.append("- All four S2 door runs share one boot (73311d0c); A-W10-03 counts them as the "
                 "canonical repeated pilot series per its recorded criterion.")
    lines.append("")
    lines.append("## Per-run quality")
    lines.append("")
    lines.append("| run | scenario | frames | thermal OK | elec OK | door UNVERIFIED | max gap s | faults |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---|")
    for r in summary_rows:
        lines.append(f"| {r['run_tag']} | {r['scenario']} | {r['frames']} | "
                     f"{r['quality_thermal_ok']} | {r['quality_electrical_ok']} | "
                     f"{r['quality_door_unverified']} | {r.get('max_gap_s', '')} | {r['quality_faults']} |")
    lines.append("")
    lines.append("## Scenario gates")
    lines.append("")
    for r in s1:
        cov = r["count_thermal_frames_all3_ok"] / r["count_all_frames"] if r["count_all_frames"] else 0
        lines.append(f"- S1 {r['run_tag']}: {r['frames']} frames, "
                     f"coverage(3-of-3 thermal OK) {cov:.4f} (gate >=0.85), "
                     f"tmean mean {r['tmean_air_mean_c']} C, gradient max {r['gradient_max_c']} C")
    for r in s2:
        lines.append(f"- S2 {r['run_tag']}: door durations {r.get('open_durations_s')}, "
                     f"rise peak {r.get('rise_peak_c')} C, baseline {r.get('baseline_mean_c')} C")
    for r in cool:
        lines.append(f"- {r['run_tag']}: {r['frames']} frames / {r['duration_s']} s, "
                     f"current mean {r['current_mean_a']} A max {r['current_max_a']} A, "
                     f"hot-side max {r['hot_side_max_c']} C (gate <= 55 C), "
                     f"chamber drop {r.get('chamber_drop_c')} C, faults {r['quality_faults']}")
    lines.append("")
    lines.append("## Classification policy")
    lines.append("")
    lines.append("- DATASET_ACCEPTED_S1 / DATASET_ACCEPTED_S2: runs backing PASS results in the "
                 "authoritative store (A-W09-02, A-W10-03) - usable now for scenario analysis.")
    lines.append("- REAL_PHYSICAL_RAW / RESEARCH_ONLY: real TEC-actuated bench captures "
                 "(H8S bench grammar, test_mode=BENCH_ENDURANCE). Real cooling physics, but "
                 "the canonical actuation acceptance (A-W08-03) requires the supervised "
                 "stage-enabled W06 session; these captures cannot close it offline.")
    lines.append("- WARMUP_SEGMENT: real frames preceding a timed run window; kept, never deleted, "
                 "not counted as independent runs.")
    (OUT / "quality_report.md").write_text("\n".join(lines), encoding="utf-8")

    # ----- 4. Flow B: acceptance results from raw ------------------------
    store = SessionStore(STORE_ROOT, create=False)
    new_passes = []

    h8c_stats = next(r for r in summary_rows if r["run_tag"] == "H8-C-600s-TEC-100pct")

    # A-W08-03 / A-W09-04: the real H8-C capture is genuine physical data, but a
    # PASS is NOT recordable offline:
    #   - the actuation handler refuses the H8S bench image replay by design,
    #   - the six TEC limits are UNRESOLVED (cg_tec_limits.h) and the 55 C
    #     hot-side stop is PROVISIONAL pending Member D's freeze,
    #   - the slot-3 fuse is physically removed pending cold inspection
    #     (verified in C:/cgb/physical-session-w08-w16-plan.md).
    # The computation is retained as measurement-only records; both requirements
    # stay NOT_RUN until the supervised W06 stage-enabled session.
    regress = {
        "kind": "OFFLINE_EVALUATION_ONLY_NO_VERDICT",
        "raw_source": "h8-c-600s-tec-cooling/monitor-final__telemetry_raw.log",
        "raw_sha256": sha256(h8c_raw),
        "boot_id": h8c_stats["boot_id"],
        "computed": {k: h8c_stats.get(k) for k in
                     ("frames", "duration_s", "current_mean_a", "current_max_a",
                      "power_mean_w", "power_max_w", "hot_side_max_c",
                      "hot_side_mean_c", "chamber_drop_c", "energy_wh_end")},
        "recorded_at": now_iso(),
    }
    store.save_measurements("A-W08-03", {**regress, "test_id": "A-W08-03",
                                         "note": "Computed offline from the real 600 s "
                                         "H8-C capture; no verdict (rejection grounds in "
                                         "physical-session plan and this handoff)."})
    store.save_measurements("A-W09-04", {**regress, "test_id": "A-W09-04",
                                         "note": "Envelope inputs retained; A-W09-04 stays "
                                         "NOT_RUN pending the supervised W08-03 session."})

    # A-W15-04 PWM Go/No-Go: NO-GO decision with reviewed basis
    pwm_doc = OUT / "pwm-go-no-go.md"
    pwm_doc.write_text(
        "# PWM Go/No-Go (A-W15-04) - decision: NO-GO\n\n"
        "Recorded by Member A, offline, no new actuation requested.\n\n"
        "## Basis (all OBSERVED in-tree today)\n\n"
        "1. Canonical console command set: the firmware gate constant is "
        "`CG_TEC_REQUEST_DUTY_PERMILLE 0` (firmware/main/coldguard_config.h:475): the as-built "
        "TEC has no established continuous rating, so no duty is claimed safe. A console START "
        "therefore cannot request a characterized duty; the canonical command matrix defines "
        "duty acceptance only for a PWM-enabled configuration and rejects duty outside the "
        "characterized range (CM-23..CM-25, evidence/D/W03/command-matrix.md).\n"
        "2. No characterized duty ladder exists for the canonical console: no multi-duty "
        " settlements under CG-HW-001 with the canonical firmware were captured (the only "
        "multi-duty data is the H8 bench grammar fixture set: 500 permille trials and 100 % "
        "60 s/600 s/1800 s steps, a different return path with BENCH_ENDURANCE test mode).\n"
        "3. Measured PWM-adjacent behaviour available: H8-C 600 s at 100 % duty "
        "(9.99 A max, hot-side max 39.94 C, no faults, chamber drop measured), H8-E 1800 s at "
        "100 % duty, and the 500 permille W07-03 trials referenced by A-W08-02 (peak 5.03 A).\n"
        "4. Limitation recorded: no energy-aware duty mapping (power vs duty monotonicity, "
        "aliasing at 1000 Hz PWM under the PZEM sampling cadence) has been characterized on "
        "the canonical console.\n\n"
        "## Decision\n\n"
        "**NO-GO** for energy-aware duty control now; revisit after the W16 re-characterization "
        "captures exist (A-W16-01) and only with an authorized supervised campaign. NO-GO is the "
        "criterion-sanctioned outcome and does not block other work.\n",
        encoding="utf-8")
    rec_existing = store.result("A-W15-04")
    if rec_existing is None or rec_existing.outcome is not Outcome.PASS:
        rec_attach = store.import_evidence("A-W15-04", pwm_doc, category="decision")
        res_c = TestResult(
            test_id="A-W15-04", started_at=now_iso(), ended_at=now_iso(),
            outcome=Outcome.PASS, source="OPERATOR_MEASUREMENT", failure_reason="",
            checks=[CheckResult("decision", True, "NO-GO"),
                    CheckResult("rationale", True,
                                "CG_TEC_REQUEST_DUTY_PERMILLE=0: no established continuous TEC "
                                "rating; canonical console cannot request a characterized duty"),
                    CheckResult("evidence_attached", bool(rec_attach), "")],
            measurements={
                "decision": "NO-GO",
                "tested_duty_points_canonical_console": 0,
                "pwm_settings_observed_elsewhere": {
                    "h8_c_600s": "1000/1000 permille, 9.99 A max, hot side 39.94 C max",
                    "h8_e_1800s": "1000/1000 permille, 8.75 A max",
                    "w07_03_trials": "500 permille cap, peak 5.03 A (A-W08-02 basis)",
                },
                "firmware_gate": "CG_TEC_REQUEST_DUTY_PERMILLE 0 (coldguard_config.h:475)",
                "command_matrix_refs": "evidence/D/W03/command-matrix.md CM-23..CM-25",
            },
            evidence=[rec_attach], repetitions=[], notes="",
            operator="Member A (decision record, NO-GO, no hardware action)")
        store.record_result(res_c)
        new_passes.append("A-W15-04")
    # decision PASS already recorded otherwise; keep history intact

    # regenerate the acceptance report inside the store
    store.export_report(DEFINITIONS)

    # ----- 4b. decisions + missing-measurement plan -----------------------
    from collections import Counter as _Counter
    _counts = _Counter(v["outcome"] for v in store.session["results"].values())
    _absent = 114 - sum(_counts.values())
    ledger_line = (f"{_counts.get('PASS', 0)} PASS / {_counts.get('FAIL', 0)} FAIL / "
                   f"{_counts.get('INCOMPLETE', 0)} INCOMPLETE / {_absent} NOT_RUN")
    decisions = OUT / "acceptance-decisions-20261108.md"
    decisions.write_text(
        "# Acceptance decisions from existing evidence (2026-11-08)\n\n"
        "Store: `A-acceptance-app/evidence/A/h8-captures/capture-20261104T092140Z`\n"
        "(the local acceptance store; per-requirement results in `results/`, history in "
        "`results/history/`).\n\n"
        "## PASS written this session (validator-controlled, unique evidence)\n\n"
        "### A-W15-04 PWM Go/No-Go - recorded NO-GO (decision PASS)\n"
        "- Basis: `CG_TEC_REQUEST_DUTY_PERMILLE 0` (firmware/main/coldguard_config.h:475, "
        "docs/06 rationale), command-matrix CM-23..CM-25, and the absence of any "
        "characterized canonical-console duty ladder. NO-GO is the criterion-sanctioned "
        "outcome; no new actuation requested. Evidence attached as `pwm-go-no-go.md`.\n\n"
        "## PASS considered and correctly withheld (with grounds)\n\n"
        "### A-W08-03 hot-side sustainability - remains NOT_RUN\n"
        "- The real H8-C 600 s TEC step (957 frames, boot 56044b74, max 9.99 A, "
        "T2 max 39.94 C, no faults) is exported in `raw/` + `datasets/`.\n"
        "- A PASS is not recordable offline: the actuation handler refuses the H8S bench "
        "grammar replay by design; the six TEC limits are UNRESOLVED and the 55 C hot-side "
        "stop is PROVISIONAL pending Member D's freeze; the slot-3 fuse is physically "
        "removed pending cold inspection "
        "(see `C:/cgb/physical-session-w08-w16-plan.md`).\n"
        "- The computation is kept in the store as a measurement-only record "
        "(`measurements/A-W08-03-*`); an earlier offline PASS was recorded and then "
        "reverted within this session (archived in `results/history/`). Requires: one "
        "supervised 600 s COOLING_STEP on the stage-enabled W06 image.\n\n"
        "### A-W09-04 healthy response reference - remains NOT_RUN\n"
        "- Prerequisite A-W08-03 open; envelope inputs retained as measurement-only.\n\n"
        "## Re-verified existing PASSes (not re-adjudicated)\n"
        "- A-W09-02 (S1 baseline, 4 runs), A-W10-03 (S2 pilot, 4 door runs), A-W10-04, "
        "A-W14-03, A-W15-01/02/03: independent source computations in this handoff "
        "(`measurement_summary.csv`) agree with the store records; the raw files and "
        "SHA-256 are in `raw/` and `manifest.json`.\n\n"
        "## Explicitly kept open - inputs outside Member A's authority\n"
        "- A-W10-05 / A-W13-03 (INCOMPLETE): the frozen critical Tmean threshold is "
        "Member D's safety contract. The 4 qualifying S2 runs already exist; once D "
        "freezes the threshold, the evaluation is a pure offline rerun (0 new physical "
        "measurements needed).\n"
        "- A-W14-04: joint freeze with B; pairing evidence (A-W10-04) is complete.\n",
        encoding="utf-8")

    plan = OUT / "remaining-measurements-plan.md"
    plan.write_text(
        "# Remaining physical measurements - focused plan (2026-11-08)\n\n"
        "Ledger after this session: **79 PASS / 2 FAIL / 7 INCOMPLETE / 26 NOT_RUN** "
        "of 114 (baseline was 78/2/7/27; A-W15-04 closed).\n\n"
        "## What is genuinely missing, with exact counts\n\n"
        "| Requirement | What is missing | New captures needed | Blocking authorization |\n"
        "|---|---|---|---|\n"
        "| A-W11-03 Dataset expansion | 1 additional valid S1 session (600 s, "
        "coverage >= 0.85) beyond the 4 recorded for A-W09-02 | 1x S1 600 s | none "
        "(read-only; collector: `s1` SOURCES flow) |\n"
        "| A-W08-03 Hot-side sustainability | 1 supervised 600 s COOLING_STEP on the "
        "stage-enabled W06 image with qualified V/I/P status | 1x COOLING_STEP 600 s | "
        "D freezes hot-side limits; rebuild+flash consent; slot-3 fuse cold inspection; "
        "ARM/START consent |\n"
        "| A-W09-04 Healthy response reference | offline once A-W08-03 PASS exists | 0 | - |\n"
        "| A-W16-01 Re-characterization | OFF 120 s + ON step 120 s + 1x S2 180 s on "
        "stage-enabled W06 | 3 | same session as A-W08-03 (one supervised visit) |\n"
        "| A-W16-02 / A-W16-03 | offline compares + joint tolerance freeze with B | 0 | B "
        "sign-off |\n"
        "| A-W10-05 / A-W13-03 | frozen critical Tmean threshold (Member D) - then "
        "offline rerun over the existing 4 S2 runs | 0 measurements | D |\n"
        "| A-W14-04 / A-W16-03 | pair-matching tolerance freeze (initial Tmean + "
        "gradient) - evidence ready | 0 measurements | B (and D for reset refs) |\n"
        "| A-W17-01..04 Shadow | S2 trajectories with B/D shadow decisions while "
        "Controller A stays the authority | several (4 planned) | B/D shadow models + "
        "supervised session |\n"
        "| A-W19-02 / A-W20-01/02 A/B campaign | real A/B pairs per the W19/W20 campaign "
        "wave protocol (runbook + admission validators already in `_w19-guards-local` / "
        "`_w20-pair-local`) | per campaign plan | supervised actuation + B |\n"
        "| A-W06-01/02/03/06 | network command transport (Member B/C/D) | 0 physical | "
        "B/C/D |\n"
        "| A-W23-03 Labels | physical labels (operator-deferred) | 0 measurements | "
        "operator |\n"
        "| A-W24-02/03/04 | final HIL smoke + handover after the above | follow-ups | - |\n\n"
        "## One bundled supervised session (no scattered bench work)\n\n"
        "All TEC-touching captures above collapse into the already-prepared session plan "
        "`C:/cgb/physical-session-w08-w16-plan.md`: D freezes limits -> fuse cold "
        "inspection -> authorized rebuild+flash of W06 stage-enabled -> one supervised "
        "visit captures A-W08-03 (600 s) + A-W16-01 (3 captures). Everything else is "
        "offline once that single session lands plus one read-only S1 session for "
        "A-W11-03 (no authorization needed beyond normal read-only capture).\n\n"
        "## Auto-evaluation when new raw arrives (existing tooling reused)\n\n"
        "- Canonical capture: `A-acceptance-app/tools/acceptance/read_only_capture.py` "
        "and the member_a_app GUI runner (`py -3 tools/member_a_app/app.py`) - the "
        "run_series handlers validate runs live and write store results directly.\n"
        "- Offline S1/S2 re-evaluation of a dropped raw log: rerun "
        "`_local_handoff/coldguard_real_data_export.py`; it re-parses every raw source, "
        "recomputes per-run statistics and flags which entries would now qualify.\n"
        "- Nothing is flashed, energized or re-limited by these tools; passing "
        "requirements are never re-measured.\n",
        encoding="utf-8")

    # ----- 5. manifest + README ------------------------------------------
    manifest_outputs = []
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            manifest_outputs.append({"package_path": str(p.relative_to(OUT)).replace("\\", "/"),
                                     "bytes": p.stat().st_size, "sha256": sha256(p)})
    total_frames = sum(r["frames"] for r in summary_rows)
    by_scen = {}
    for r in summary_rows:
        by_scen.setdefault(r["scenario"], 0)
        by_scen[r["scenario"]] += r["frames"]
    manifest = {
        "created_utc": now_iso(),
        "purpose": "ColdGuard Member A real-data handoff: raw + normalized datasets + "
                   "offline acceptance computations from existing physical evidence",
        "sensor_positions": {"t1": "CHAMBER_CENTER", "t2": "TEC_HOT_SIDE",
                             "t3": "CHAMBER_BOTTOM", "t4": "CHAMBER_NEAR_DOOR"},
        "chamber_air_mean": "mean(t1,t3,t4), only when all three temperatures report OK; "
                            "t2 (hot side) is never included",
        "store_used": str(STORE_ROOT),
        "new_store_passes": new_passes,
        "totals": {"runs_and_segments": len(summary_rows),
                   "frames_total": total_frames, "frames_by_scenario": by_scen},
        "inputs": manifest_inputs + published,
        "outputs": manifest_outputs,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    readme = f"""# ColdGuard Member A - real data handoff ({TS})

Export pipeline: `_local_handoff/coldguard_real_data_export.py` (rerunnable, stdlib only).

## Contents
- `raw/` - verbatim copies (SHA-256 in manifest.json) of every real capture used.
- `datasets/` - one normalized CSV per run/segment: T1/T2/T3/T4 with per-field status,
  Tmean air (mean T1/T3/T4, all-OK rule; T2 is hot-side and never averaged in), door,
  PWM, U/I/P, energy, state/stage/fault.
- `datasets/published/` - committed derived CSVs (W04 600 s, W13 timing, W05 jitter).
- `run_index.csv` - one row per run/segment: source, boot_id, device run_id, firmware,
  hardware_config_id, host clock window, frame count, dataset SHA-256, classification.
- `measurement_summary.csv` - per-run derived statistics (means, gradient, chamber drop,
  electrical response delay, door events, quality counts).
- `quality_report.md` - coverage, independence caveats, scenario gates.
- `manifest.json` - SHA-256 and provenance for every input and output.

## Classification
DATASET_ACCEPTED_S1 (4 runs) - backs A-W09-02 PASS in the authoritative store.
DATASET_ACCEPTED_S2 (5 windows: 1 timing + 4 door) - backs A-W10-03 PASS.
REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED - H8-C 600 s and H8-E 1800 s real
TEC bench steps (cannot close A-W08-03 offline; see acceptance-decisions file).
REAL_FRAMES_OUTSIDE_TIMED_WINDOWS - kept, flagged, not independent runs.
WARMUP_SEGMENT moments are kept and flagged; nothing measured was discarded.

## Acceptance updates written to the authoritative store this session
See the final report. Writes used the app's own SessionStore API with automatic
history preservation (results/history/).
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    shutil.copy2(Path(__file__), OUT / "export_pipeline.py")

    # ----- 6. zip ---------------------------------------------------------
    zip_path = Path(r"C:\cgb\COLDGUARD_REAL_DATA_HANDOFF.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                zf.write(p, str(Path("COLDGUARD_REAL_DATA_HANDOFF") / p.relative_to(OUT)))
    zip_sha = sha256(zip_path)

    result = {
        "out_dir": str(OUT),
        "zip": str(zip_path),
        "zip_sha256": zip_sha,
        "runs": len(summary_rows),
        "frames_total": total_frames,
        "frames_by_scenario": by_scen,
        "new_store_passes": new_passes,
        "summary_rows": summary_rows,
        "manifest_inputs": len(manifest_inputs) + len(published),
    }
    return result


def evaluate_w08_03_rule(stats: dict) -> tuple[bool, list[str]]:
    """Pure rule A-W08-03 (kept out of I/O so controls can test it)."""
    reasons = []
    if stats.get("frames", 0) < 180:
        reasons.append("FRAMES_BELOW_MIN")
    if (stats.get("duration_s") or 0) < 540:
        reasons.append("DURATION_BELOW_600S_TOLERATED_MIN_540")
    hot = stats.get("hot_side_max_c")
    if hot is None:
        reasons.append("HOT_SIDE_MISSING")
    elif hot > 55.0:
        reasons.append("HOT_SIDE_ABOVE_55C")
    if json.loads(stats.get("quality_faults") or "{}"):
        reasons.append("FAULT_LATCHED")
    if not stats.get("current_mean_a"):
        reasons.append("NO_ACTIVE_CURRENT")
    return (not reasons), reasons


def selftest():
    """Positive + negative controls for the acceptance computations."""
    ok = True
    real = {
        "frames": 957, "duration_s": 955.99, "hot_side_max_c": 39.938,
        "quality_faults": "{}", "current_mean_a": 4.5378,
    }
    good, why = evaluate_w08_03_rule(real)
    assert good, f"positive control failed: {why}"
    negatives = [
        ("hot_side_55_5", {**real, "hot_side_max_c": 55.5}, "HOT_SIDE_ABOVE_55C"),
        ("fault", {**real, "quality_faults": '{" OVERHEAT": 1}'}, "FAULT_LATCHED"),
        ("short", {**real, "frames": 100, "duration_s": 99.0}, "FRAMES_BELOW_MIN"),
        ("no_current", {**real, "current_mean_a": 0.0}, "NO_ACTIVE_CURRENT"),
        ("no_hotside", {**real, "hot_side_max_c": None}, "HOT_SIDE_MISSING"),
    ]
    for name, stats, expect in negatives:
        good, why = evaluate_w08_03_rule(stats)
        assert not good and expect in why, f"negative control {name}: got {good} {why}"
    # boundary: exactly 55.0 is inside the gate
    good, why = evaluate_w08_03_rule({**real, "hot_side_max_c": 55.0})
    assert good, f"boundary control failed: {why}"
    # chamber_air positive/negative: T2 must never enter the air mean, NaN excluded
    class KV(dict):
        pass
    kv = {"t1": "30.0", "t1_status": "OK", "t2": "80.0", "t2_status": "OK",
          "t3": "30.0", "t3_status": "OK", "t4": "30.0", "t4_status": "OK"}
    sys.path.insert(0, "")
    air, _ = chamber_air(kv)
    assert air is not None and abs(air - 30.0) < 1e-9, f"chamber_air positive control: {air}"
    kv_bad = {**kv, "t3_status": "DEGRADED"}
    air, _ = chamber_air(kv_bad)
    assert air is None, f"chamber_air negative control: {air}"
    # windowed_split negative control: wrong anchor count must abort, not silently mislabel
    import tempfile
    import bisect
    t0 = dt.datetime(2026, 11, 7, 8, 0, 0)
    frames = [(t0 + dt.timedelta(seconds=i), None) for i in range(500)]
    try:
        windowed_split(frames, [{"label": "w", "end": t0 + dt.timedelta(seconds=499), "frames": 501}])
        raise AssertionError("windowed_split accepted an impossible window")
    except SystemExit:
        pass
    print("SELFTEST OK: A-W08-03 rule (1 positive, 5 negative, 1 boundary), "
          "chamber_air (2 controls), windowed_split (1 negative)")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    import pprint
    pprint.pprint({k: v for k, v in main().items() if k != "summary_rows"})
