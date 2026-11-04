"""Protocol-specific handlers for W01-W24.

Kept separate so the generic evaluator module stays readable. The module
registers its handlers into ``evaluators.HANDLERS`` on import.
"""

from __future__ import annotations

import pathlib
import time
import uuid
from typing import Any

from . import analysis, protocol
from .evaluators import _bme_metrics, _safe_stop, handler_actuation_trace
from .model import Outcome, TestBlocked
from .runner import TestContext


def handler_bom_csv(ctx: TestContext) -> None:
    import csv

    imported = ctx.imported_first(".csv")
    if imported is not None:
        path = ctx.imported_path(imported)
        if imported not in ctx.evidence:
            ctx.evidence.append(imported)
    else:
        path = ctx.ask_file("Attach bom-audit.csv with HW-01..HW-24 rows", [("CSV", "*.csv")])
        if not path:
            ctx.block("BOM_CSV_NOT_PROVIDED")
        ctx.attach(path)
    try:
        with pathlib.Path(path).open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except Exception as exc:
        ctx.check("bom_csv_readable", False, detail=str(exc), failure_reason="BOM_CSV_UNREADABLE")
        return
    ids = {str(row.get("id", row.get("ID", ""))).strip().upper() for row in rows}
    expected = {f"HW-{index:02d}" for index in range(1, 25)}
    missing = sorted(expected - ids)
    headers = {header.lower(): header for header in (rows[0].keys() if rows else [])}
    presence_key = "present" if "present" in headers else "inspection_status"
    quantity_key = "quantity" if "quantity" in headers else "observed_qty"
    marking_key = "marking" if "marking" in headers else "visible_marking"
    condition_key = "condition" if "condition" in headers else "physical_condition"
    missing_headers = [key for key, present in (
        (presence_key, presence_key in headers),
        (quantity_key, quantity_key in headers),
        (marking_key, marking_key in headers),
        (condition_key, condition_key in headers)) if not present]
    incomplete_rows = [
        row for row in rows
        if not str(row.get(presence_key, "")).strip()
        or not str(row.get(quantity_key, "")).strip()
        or not str(row.get(condition_key, "")).strip()
    ]
    substitutions = [
        str(row.get("id", "")).strip().upper() for row in rows
        if str(row.get("inspection_status", "")).strip().upper() == "UNAPPROVED_SUBSTITUTION"
    ]
    ctx.measurements.update({"rows": len(rows), "ids": sorted(ids), "missing": missing,
                             "missing_headers": missing_headers,
                             "incomplete_rows": len(incomplete_rows),
                             "unapproved_substitutions": substitutions})
    ctx.check("bom_has_24_items", len(ids & expected) == 24,
              detail=f"{len(ids & expected)}/24", failure_reason="BOM_ITEMS_MISSING")
    ctx.check("bom_ids_canonical", not missing, detail=str(missing),
              failure_reason="BOM_IDS_NOT_CANONICAL")
    ctx.check("bom_required_columns", not missing_headers, detail=str(missing_headers),
              failure_reason="BOM_COLUMNS_MISSING")
    ctx.check("bom_rows_populated", len(incomplete_rows) == 0,
              detail=f"{len(incomplete_rows)} incomplete",
              failure_reason="BOM_ROWS_INCOMPLETE")
    ctx.check("no_unapproved_substitution", not substitutions,
              detail=str(substitutions), failure_reason="UNAPPROVED_SUBSTITUTION")
    ctx.check("bom_row_count", len(rows) >= 24, detail=str(len(rows)),
              failure_reason="BOM_ROWS_TOO_FEW")
    ctx.save_measurements()


def handler_photo_inventory(ctx: TestContext) -> None:
    subjects = list(ctx.definition.params.get("subjects", []))
    imported = [record for record in ctx.imported_files()
                if str(record.get("stored", "")).lower().endswith((".jpg", ".jpeg", ".png"))]
    keywords = {
        "dual ESP32 board — component side": ("esp32", "component"),
        "dual ESP32 board — solder side": ("esp32", "back"),
        "DS18B20 labels/probes": ("ds18b20",),
        "BME280 module": ("bme280",),
        "MC-38 reed switch": ("mc38",),
        "PZEM-017": ("pzem",),
        "50 A / 75 mV shunt": ("shunt", "marking"),
        "RS-485 transceiver module": ("rs485",),
        "IBT-2 module": ("ibt2",),
        "TEC1-12715 SKU marking": ("tec",),
        "V1 thermal assembly": ("v1",),
        "12 V PSU nameplate": ("psu", "label"),
        "fuse box and fuse set": ("fuse",),
    }
    missing = []
    for subject in subjects:
        candidates = []
        needles = keywords.get(subject, (subject.lower(),))
        for record in imported:
            name = f"{record.get('stored', '')} {record.get('source_path', '')}".lower()
            if all(needle in name for needle in needles):
                candidates.append(record)
        accepted = None
        for record in candidates:
            if ctx.ask_confirm(
                    f"The imported photo '{record.get('stored')}' is the required "
                    f"'{subject}'. Confirm it shows the right subject."):
                accepted = record
                break
        if accepted is not None:
            if accepted not in ctx.evidence:
                ctx.evidence.append(accepted)
            ctx.check(f"photo:{subject}", True, detail=f"imported {accepted.get('stored')}")
            continue
        path = ctx.ask_file(f"Attach the photo for: {subject}")
        if not path:
            missing.append(subject)
            ctx.check(f"photo:{subject}", False, failure_reason=f"PHOTO_MISSING: {subject}")
            continue
        try:
            ctx.attach(path)
            ctx.check(f"photo:{subject}", True, detail=subject)
        except Exception as exc:
            missing.append(subject)
            ctx.check(f"photo:{subject}", False, detail=str(exc),
                      failure_reason=f"PHOTO_INVALID: {subject}")
    ctx.measurements["missing_subjects"] = missing
    ctx.check("all_photos_present", not missing,
              detail=f"{len(subjects) - len(missing)}/{len(subjects)}",
              failure_reason="PHOTO_INVENTORY_INCOMPLETE")
    ctx.save_measurements()


def handler_token_scan(ctx: TestContext) -> None:
    imported = ctx.imported_first()
    if imported is not None:
        path = ctx.imported_path(imported)
        if imported not in ctx.evidence:
            ctx.evidence.append(imported)
    else:
        path = ctx.ask_file("Attach the legacy-assumption scan report (text/Markdown)",
                            [("Text", "*.txt *.md"), ("All", "*.*")])
        if not path:
            ctx.block("SCAN_REPORT_NOT_PROVIDED")
        ctx.attach(path)
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace").lower()
    except Exception as exc:
        ctx.check("scan_readable", False, detail=str(exc), failure_reason="SCAN_UNREADABLE")
        return
    tokens = list(ctx.definition.params.get(
        "tokens", ["ina226", "irlb3813", "two tec", "20l", "40a psu"]))
    found = [token for token in tokens if token in text]
    flagged = any(word in text for word in
                  ("obsolete", "superseded", "deprecated", "not authority"))
    ctx.measurements.update({"tokens": tokens, "found": found, "flagged_obsolete": flagged})
    ctx.check("all_tokens_searched", len(found) == len(tokens), detail=str(found),
              failure_reason="SCAN_TOKENS_MISSING")
    ctx.check("obsolete_flag_recorded", flagged, failure_reason="OBSOLETE_FLAG_MISSING")
    ctx.save_measurements()


def handler_sensor_enumeration(ctx: TestContext) -> None:
    device = ctx.require_live_device()
    if device.latest_frame() is not None and device.latest_frame().is_h8:
        ctx.block("H8_BENCH_IMAGE: the H8S frame does not carry the canonical #CG ROM role lines")
    cursor = device.event_cursor()
    events: list[protocol.ParsedLine] = []
    deadline = time.monotonic() + float(ctx.definition.params.get("timeout_s", 6))
    while time.monotonic() < deadline:
        new, cursor = device.events_since(cursor)
        events.extend(item for item in new if item.kind == "ROM")
        if len({item.rom.role for item in events if item.rom}) >= 3:
            break
        time.sleep(0.1)
    if not events:
        ctx.operator.info(
            ctx.definition.test_id,
            "No ROM lines were captured. Unplug/replug the ESP32 USB cable while the application "
            "is connected, then continue. Do not touch the 12 V PSU.",
        )
        if ctx.ask_confirm("Continue after the USB cold boot?"):
            previous = device.snapshot.boot.boot_id
            if not device.prepare_cold_boot():
                ctx.block("COLD_BOOT_PORT_PREPARE_FAILED")
            if not device.reopen_after_cold_boot():
                ctx.block("COLD_BOOT_REOPEN_FAILED")
            device.wait_for_boot(previous, 30)
            time.sleep(2.0)
            new, cursor = device.events_since(cursor)
            events.extend(item for item in new if item.kind == "ROM")
    roms = {item.rom.role: item.rom for item in events if item.rom is not None}
    ctx.measurements["roms"] = {role: entry.rom for role, entry in roms.items()}
    ctx.measurements["roles"] = sorted(roms)
    ctx.check("rom_lines_present", bool(roms), detail=str(sorted(roms)),
              failure_reason="NO_ROM_LINES")
    for role in ("T1", "T2", "T3"):
        entry = roms.get(role)
        ctx.check(f"role_{role}_present", entry is not None and entry.present,
                  failure_reason=f"REQUIRED_ROM_MISSING:{role}")
    unique = {entry.rom for entry in roms.values() if entry.present}
    required_unique = {roms[role].rom for role in ("T1", "T2", "T3")
                       if role in roms and roms[role].present}
    ctx.check("three_unique_roms", len(unique) >= 3, detail=str(len(unique)),
              failure_reason="ROM_IDENTITIES_NOT_UNIQUE")
    ctx.check("required_roles_unique", len(required_unique) == 3,
              detail=str(sorted(required_unique)),
              failure_reason="T1_T2_T3_NOT_UNIQUE")
    ctx.check("spare_role_reported", "SPARE" in roms, detail=str(sorted(roms)),
              failure_reason="SPARE_ROLE_NOT_REPORTED")
    ctx.save_measurements()


def handler_sensor_position_qa(ctx: TestContext) -> None:
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 15)),
                         min_frames=int(ctx.definition.params.get("min_frames", 5)),
                         label="position QA")
    device = ctx.require_live_device()
    roms = {role: entry.rom for role, entry in device.snapshot.rom_map.items()}
    expected = dict(analysis.FROZEN_ROM_BY_ROLE)
    ctx.measurements.update({"roms": roms, "expected": expected, "frames": len(frames)})
    ctx.check("frozen_rom_map_matches", roms == expected, detail=f"{roms}",
              failure_reason="SENSOR_ROM_MAP_CHANGED")
    ctx.check("four_unique_roms", len(set(roms.values())) == 4,
              detail=str(len(set(roms.values()))), failure_reason="ROM_MAP_INCOMPLETE")
    ctx.require_attachment("Attach a labeled photo of the unchanged sensor positions",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_bme_check(ctx: TestContext) -> None:
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 60)),
                         min_frames=int(ctx.definition.params.get("min_frames", 10)),
                         label="BME280")
    bme = _bme_metrics(frames)
    ctx.measurements.update({"bme": bme, "frames": len(frames)})
    ctx.check_closed("ambient_valid_rate", bme["ambient_valid_rate"], 0.9, None)
    ctx.check_closed("humidity_valid_rate", bme["humidity_valid_rate"], 0.9, None)
    ctx.check_closed("ambient_mean_c", bme["ambient_mean_c"], -40.0, 85.0)
    ctx.check_closed("humidity_mean_pct", bme["humidity_mean_pct"], 0.0, 100.0)
    if not ctx.ask_confirm("Is the BME280 mounted away from the ESP32/V1 heat path and not self-heating?"):
        ctx.check("mounting_not_heated", False, failure_reason="BME_MOUNTING_HEATED")
    else:
        ctx.check("mounting_not_heated", True)
    ctx.require_attachment("Attach a photo of the BME280 mounting position",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_door_cycles(ctx: TestContext) -> None:
    count = int(ctx.definition.params.get("cycles", 20))
    ctx.operator.info(ctx.definition.test_id,
                      f"Open and close the chamber door {count} times. The MC-38 transition is the "
                      "machine ground truth; the application records every edge.")
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 300)),
                         min_frames=int(ctx.definition.params.get("min_frames", 30)),
                         label="door cycles")
    metrics = analysis.door_metrics(frames)
    ctx.measurements.update(metrics)
    ctx.measurements["cycles_expected"] = count
    if metrics["transitions"] == 0:
        ctx.save_measurements()
        ctx.block("NO_DOOR_TRANSITIONS: no physical cycles were observed")
    ctx.check_closed("cycles", metrics["cycles"], count, None)
    ctx.check_closed("transitions", metrics["transitions"], count * 2, None)
    ctx.check("door_semantics_verified", metrics["unverified_frames"] == 0,
              detail=str(metrics["unverified_frames"]), failure_reason="DOOR_STATE_UNVERIFIED")
    ctx.save_measurements()


def handler_max3485(ctx: TestContext) -> None:
    ctx.source = "OPERATOR_MEASUREMENT"
    vcc = ctx.ask_number("Measured VCC at the RS-485 module (V)", "V", 0.0, 12.0)
    ctx.check_closed("vcc_3v3", vcc, 3.2, 3.4, detail="V")
    ctx.measurements["vcc_v"] = vcc
    for item in ctx.definition.params.get("items", []):
        if not ctx.ask_confirm(item):
            ctx.check(f"item:{item}", False, failure_reason=f"MODULE_CHECK_FAILED: {item}")
    ctx.require_attachment("Attach a photo of the RS-485 module and its power connection",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_ibt2_logic(ctx: TestContext) -> None:
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 15)),
                         min_frames=int(ctx.definition.params.get("min_frames", 5)),
                         label="IBT-2 logic")
    latest = frames[-1]
    ctx.measurements["output_stage"] = latest.output_stage
    ctx.measurements["default_off"] = all(frame.is_default_off for frame in frames)
    ctx.check("default_off_observed", ctx.measurements["default_off"],
              failure_reason="IBT2_NOT_DEFAULT_OFF")
    for item in ctx.definition.params.get("items", []):
        if not ctx.ask_confirm(item):
            ctx.check(f"item:{item}", False, failure_reason=f"IBT2_CHECK_FAILED: {item}")
    if not ctx.ask_confirm("Confirm no continuous-current claim is inferred from the 43 A chip limit."):
        ctx.check("no_43a_claim", False, failure_reason="43A_CONTINUOUS_CLAIM_MADE")
    else:
        ctx.check("no_43a_claim", True)
    ctx.require_attachment("Attach a photo of the IBT-2 pin labels",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_fuse(ctx: TestContext) -> None:
    ctx.source = "OPERATOR_MEASUREMENT"
    fuse = ctx.ask_choice("Installed fuse rating:", ["10 A", "15 A", "20 A"])
    rating = float(fuse.split()[0])
    steady = ctx.ask_number("Measured or planned steady branch current (A)", "A", 0.0, 40.0)
    transient = ctx.ask_number("Measured or planned transient current (A)", "A", 0.0, 60.0)
    rationale = ctx.ask_text("Record the fuse rationale (measured current, transient, terminals).")
    ctx.measurements.update({"fuse_a": rating, "steady_a": steady, "transient_a": transient,
                             "rationale": rationale})
    ctx.check("fuse_in_purchased_set", rating in {10.0, 15.0, 20.0}, detail=fuse,
              failure_reason="FUSE_NOT_FROM_PURCHASED_SET")
    ctx.check("fuse_has_headroom", rating >= 1.25 * steady, detail=f"{rating} vs {steady}",
              failure_reason="FUSE_HEADROOM_INSUFFICIENT")
    ctx.check("fuse_covers_transient", rating >= transient * 0.9, detail=f"{rating} vs {transient}",
              failure_reason="FUSE_BELOW_TRANSIENT")
    ctx.check("rationale_recorded", bool(rationale.strip()), failure_reason="FUSE_RATIONALE_EMPTY")
    ctx.require_attachment("Attach a photo of the installed fuse and holder",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.config["fuse_a"] = rating
    ctx.store.set_config("fuse_a", rating)
    ctx.save_measurements()


def handler_fuse_final(ctx: TestContext) -> None:
    ctx.require_result("A-W04-03")
    data = []
    for test_id in ctx.definition.params.get("current_sources", ["A-W04-05", "A-W07-03"]):
        result = ctx.store.result(test_id)
        if result is not None and result.outcome is Outcome.PASS:
            value = result.measurements.get("current_max_a") or result.measurements.get("current_mean_a")
            if isinstance(value, (int, float)):
                data.append(float(value))
    if not data:
        ctx.block("NO_MEASURED_ACTIVE_CURRENT: W04-05/W07-03 evidence is not available")
    peak = max(data)
    ctx.measurements["measured_peak_a"] = peak
    handler_fuse(ctx)
    rating = ctx.measurements.get("fuse_a")
    ctx.check("final_fuse_above_measured_peak",
              isinstance(rating, (int, float)) and rating >= peak * 1.25,
              detail=f"{rating} vs peak {peak}", failure_reason="FINAL_FUSE_TOO_SMALL")
    ctx.save_measurements()


def handler_polarity(ctx: TestContext) -> None:
    ctx.source = "DERIVED"
    result = ctx.require_result("A-W04-05")
    drop = result.measurements.get("chamber_drop_c")
    hot_start = result.measurements.get("hot_side_start_c")
    hot_max = result.measurements.get("hot_side_max_c")
    ctx.measurements.update({"chamber_drop_c": drop, "hot_side_start_c": hot_start,
                             "hot_side_max_c": hot_max})
    ctx.check_closed("cooling_direction", drop, ctx.definition.params.get("min_drop_c", 0.2), None)
    if hot_start is not None and hot_max is not None:
        ctx.check("hot_side_rises", hot_max >= hot_start, detail=f"{hot_start}->{hot_max}",
                  failure_reason="HOT_SIDE_DIRECTION_WRONG")
    orientation = ctx.ask_text("Record the physical TEC orientation that made the chamber side cold.")
    ctx.measurements["orientation"] = orientation
    ctx.check("orientation_recorded", bool(orientation.strip()),
              failure_reason="POLARITY_NOT_RECORDED")
    ctx.require_attachment("Attach the polarity photo with wire orientation",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_reset_criterion(ctx: TestContext) -> None:
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 60)),
                         min_frames=int(ctx.definition.params.get("min_frames", 10)),
                         label="initial state")
    latest = frames[-1]
    tmean_now = analysis.tmean(latest)
    gradient_now = analysis.gradient(latest)
    if tmean_now is None:
        ctx.block("CHAMBER_TEMPERATURE_UNAVAILABLE")
    lower = ctx.ask_number("Reset criterion lower Tmean bound (C)", "C", -20.0, 60.0)
    upper = ctx.ask_number("Reset criterion upper Tmean bound (C)", "C", lower, 60.0)
    gradient_max = ctx.ask_number("Reset criterion maximum gradient (C)", "C", 0.0, 20.0)
    ctx.measurements.update({"tmean_now_c": tmean_now, "gradient_now_c": gradient_now,
                             "tmean_min_c": lower, "tmean_max_c": upper,
                             "gradient_max_c": gradient_max,
                             "door_closed": latest.door_open is False,
                             "cooling_off": not latest.cooling_on,
                             "sensors_valid": all(latest.temp_valid(role)
                                                  for role in analysis.CHAMBER_ROLES)})
    ctx.check("criterion_band_ordered", lower < upper, detail=f"{lower}..{upper}",
              failure_reason="RESET_BAND_INVALID")
    ctx.check("measured_state_inside_band", lower <= tmean_now <= upper,
              detail=f"{tmean_now}", failure_reason="CURRENT_STATE_OUTSIDE_BAND")
    ctx.check("gradient_bounded", gradient_now is not None and gradient_now <= gradient_max,
              detail=f"{gradient_now} vs {gradient_max}",
              failure_reason="CURRENT_GRADIENT_OUTSIDE_BOUND")
    ctx.check("door_closed", latest.door_open is False, failure_reason="DOOR_NOT_CLOSED")
    ctx.check("cooling_off", not latest.cooling_on, failure_reason="COOLING_NOT_OFF")
    ctx.check("sensors_valid", ctx.measurements["sensors_valid"], failure_reason="SENSOR_INVALID")
    notes = ctx.ask_text("Record the state-based reset criterion and its limitations.")
    ctx.notes = notes
    ctx.check("criterion_documented", bool(notes.strip()), failure_reason="CRITERION_NOT_DOCUMENTED")
    ctx.store.set_config("reset_tmean_min_c", lower)
    ctx.store.set_config("reset_tmean_max_c", upper)
    ctx.store.set_config("reset_gradient_max_c", gradient_max)
    ctx.save_measurements()


def handler_state_reset(ctx: TestContext) -> None:
    result = ctx.require_result("A-W07-05")
    data = result.measurements
    lower = data.get("tmean_min_c")
    upper = data.get("tmean_max_c")
    gradient_max = data.get("gradient_max_c")
    if lower is None or upper is None:
        ctx.block("RESET_CRITERION_NOT_AVAILABLE")
    timeout = float(ctx.definition.params.get("timeout_s", 3600))
    started = time.monotonic()
    consecutive = 0
    while time.monotonic() - started < timeout:
        frame = ctx.latest_frame()
        value = analysis.tmean(frame)
        grad = analysis.gradient(frame)
        if (value is not None and lower <= value <= upper
                and (gradient_max is None or (grad is not None and grad <= gradient_max))
                and frame.door_open is False and not frame.cooling_on
                and all(frame.temp_valid(role) for role in analysis.CHAMBER_ROLES)):
            consecutive += 1
        else:
            consecutive = 0
        if consecutive >= 3:
            break
        ctx.progress(f"waiting for reset criterion ({consecutive}/3)", None)
        if ctx.operator.cancelled():
            raise TestBlocked("OPERATOR_CANCELLED")
        time.sleep(1.0)
    elapsed = time.monotonic() - started
    ctx.measurements.update({"reset_elapsed_s": elapsed, "consecutive_frames": consecutive})
    if consecutive < 3:
        ctx.save_measurements()
        ctx.block(f"RESET_CRITERION_NOT_MET after {elapsed:.0f}s")
    ctx.check("reset_criterion_met", True, detail=f"{elapsed:.0f}s")
    ctx.save_measurements()


def handler_pzem_recheck(ctx: TestContext) -> None:
    baseline = ctx.require_result("A-W03-05")
    baseline_off_max = (baseline.measurements.get("off_current_max_a")
                        or baseline.measurements.get("current_max_a"))
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 120)),
                         min_frames=int(ctx.definition.params.get("min_frames", 20)),
                         label="PZEM recheck")
    metrics = analysis.electrical_metrics(frames)
    ctx.measurements.update(metrics)
    ctx.measurements["baseline_off_current_max_a"] = baseline_off_max
    ctx.check("off_current_within_baseline", metrics["off_current_max_a"] is not None
              and baseline_off_max is not None
              and metrics["off_current_max_a"] <= float(baseline_off_max) + 0.02,
              detail=f"{metrics['off_current_max_a']} vs {baseline_off_max}",
              failure_reason="OFF_ENVELOPE_DRIFTED")
    ctx.check_closed("voltage_mean_v", metrics["voltage_mean_v"], 11.5, 12.5)
    ctx.check_closed("valid_rate", metrics["valid_rate"], 0.9, None)
    ctx.save_measurements()


def handler_drift_recheck(ctx: TestContext) -> None:
    baseline = ctx.require_result("A-W02-05")
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 600)),
                         min_frames=int(ctx.definition.params.get("min_frames", 60)),
                         label="drift recheck")
    current = analysis.consistency_metrics(frames)
    baseline_roles = baseline.measurements.get("per_role", {})
    deltas = {}
    for role in analysis.ALL_ROLES:
        old = (baseline_roles.get(role) or {}).get("mean_c")
        new = (current.get("per_role", {}).get(role) or {}).get("mean_c")
        deltas[role] = ((new - old) if isinstance(old, (int, float)) and isinstance(new, (int, float))
                        else None)
    ctx.measurements.update({"current": current, "deltas": deltas})
    ctx.check_closed("valid_rate", current["valid_rate"], 0.9, None)
    max_delta = max((abs(value) for value in deltas.values() if value is not None), default=None)
    ctx.measurements["max_abs_delta_c"] = max_delta
    ctx.check_closed("max_abs_delta_c", max_delta, None,
                     ctx.definition.params.get("max_drift_c", 0.3))
    ctx.save_measurements()


def handler_door_protocol(ctx: TestContext) -> None:
    ctx.source = "OPERATOR_MEASUREMENT"
    first = ctx.ask_number("Candidate door-open duration 1 (s)", "s", 1.0, 300.0)
    second = ctx.ask_number("Candidate door-open duration 2 (s)", "s", 1.0, 300.0)
    rationale = ctx.ask_text(
        "Record why these candidates are safe and likely to produce a measurable disturbance.")
    ctx.measurements.update({"candidate_1_s": first, "candidate_2_s": second,
                             "rationale": rationale})
    ctx.check("two_distinct_candidates", first != second and min(first, second) > 0,
              detail=f"{first}/{second}", failure_reason="DOOR_CANDIDATES_INVALID")
    ctx.check("rationale_recorded", bool(rationale.strip()), failure_reason="DOOR_RATIONALE_EMPTY")
    ctx.require_attachment("Attach the door-protocol candidate record",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_door_timing(ctx: TestContext) -> None:
    ctx.operator.info(ctx.definition.test_id,
                      "Open the door when the run starts and close it after the agreed interval. "
                      "The application measures the MC-38 transition and asks for your stopwatch value.")
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 120)),
                         min_frames=int(ctx.definition.params.get("min_frames", 20)),
                         label="door timing")
    metrics = analysis.door_metrics(frames)
    if not metrics["open_durations_s"]:
        ctx.save_measurements()
        ctx.block("NO_DOOR_EVENT: no open/close transition was observed")
    operator_time = ctx.ask_number("Stopwatch door-open duration (s)", "s", 0.1, 600.0)
    machine = metrics["open_durations_s"][0]
    delta = abs(operator_time - machine)
    ctx.measurements.update({"operator_s": operator_time, "mc38_s": machine, "delta_s": delta,
                             "transitions": metrics["transitions"]})
    ctx.check_closed("machine_duration_positive", machine, 0.1, None)
    ctx.check_closed("operator_machine_delta_s", delta, None,
                     ctx.definition.params.get("max_delta_s", 2.0))
    ctx.check_closed("transitions", metrics["transitions"], 2, None)
    ctx.save_measurements()


def handler_invalidation_log(ctx: TestContext) -> None:
    ctx.source = "OPERATOR_MEASUREMENT"
    missing = []
    invalid = 0
    for result in ctx.store.results().values():
        for run in result.repetitions:
            if run.get("valid") is False:
                invalid += 1
                if not str(run.get("reason", "")).strip():
                    missing.append(result.test_id)
    ctx.measurements.update({"invalid_attempts": invalid, "missing_reasons": missing})
    ctx.check("invalid_attempts_retained_with_reason", not missing, detail=str(missing),
              failure_reason="INVALID_ATTEMPT_WITHOUT_REASON")
    ctx.require_attachment("Attach the invalidation log or a statement that none occurred",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_safe_local(ctx: TestContext) -> None:
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 60)),
                         min_frames=int(ctx.definition.params.get("min_frames", 20)),
                         label="local-only")
    metrics = analysis.soak_metrics(frames)
    latest = frames[-1]
    local_channels = {
        "T1": latest.temp_valid("T1"),
        "T2": latest.temp_valid("T2"),
        "T3": latest.temp_valid("T3"),
        "door": latest.door_open is not None,
        "pzem": latest.electrical_valid(),
    }
    ctx.measurements.update({"metrics": metrics, "local_channels": local_channels})
    for name, value in local_channels.items():
        ctx.check(f"local_channel:{name}", value, failure_reason=f"LOCAL_CHANNEL_MISSING:{name}")
    ctx.check("default_off_preserved", all(frame.is_default_off for frame in frames),
              failure_reason="SAFE_LOCAL_DEFAULT_OFF_BROKEN")
    ctx.check("no_reboot", metrics["boot_changes"] == 0, detail=str(metrics["boot_changes"]),
              failure_reason="REBOOT_DURING_LOCAL_TEST")
    if not ctx.ask_confirm("Confirm the broker/backend path is removed for this test."):
        ctx.check("broker_removed", False, failure_reason="BROKER_NOT_REMOVED")
    else:
        ctx.check("broker_removed", True)
    ctx.save_measurements()


def handler_s4_method(ctx: TestContext) -> None:
    frame = ctx.latest_frame()
    if frame.is_h8:
        ctx.block("H8_BENCH_IMAGE: flash the W06 acceptance firmware")
    disabled = (frame.output_stage or "").upper() == "DISABLED"
    ctx.measurements["output_stage"] = frame.output_stage
    if not disabled:
        ctx.save_measurements()
        ctx.block("S4_TEST_MODE_NOT_AVAILABLE: the output stage is enabled and this build exposes "
                  "no refusal mode; do not short the branch or bypass the fuse")
    ctx.check("output_stage_disabled", True, detail=str(frame.output_stage))
    if not ctx.ask_confirm("Confirm no fuse bypass, branch short, or hardware defeat was used for S4."):
        ctx.check("no_destructive_bypass", False, failure_reason="S4_BYPASS_USED")
    else:
        ctx.check("no_destructive_bypass", True)
    ctx.require_attachment("Attach the S4 method record",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_s4_refusal(ctx: TestContext) -> None:
    frame = ctx.latest_frame()
    if frame.is_h8:
        ctx.block("H8_BENCH_IMAGE: flash the W06 acceptance firmware")
    if (frame.output_stage or "").upper() != "DISABLED":
        ctx.block("S4_REFUSAL_REQUIRES_DISABLED_STAGE: the shipped build must prove the refusal path")
    device = ctx.require_live_device()
    token = device.snapshot.auth_token
    if not token:
        token = ctx.ask_text("Enter the 8-hex ARM token printed at boot").strip()
    if not ctx.ask_confirm("Send ARM for the S4 refusal probe? No actuation is intended."):
        ctx.block("ARM_NOT_CONFIRMED")
    cursor = device.event_cursor()
    device.send(protocol.arm(token), "S4 ARM")
    armed = ctx.wait_for_event(
        lambda item: item.kind == "TEC" and item.kv.get("event") == "ARM", 6, cursor)
    if armed.kv.get("result") != "ARMED":
        ctx.block(f"ARM_REFUSED: {armed.raw}")
    if not ctx.ask_confirm("Send START 10 s for the S4 refusal probe? The output stage must refuse."):
        ctx.block("START_NOT_CONFIRMED")
    cursor = device.event_cursor()
    device.send(protocol.start(10), "S4 START (expected refusal)")
    try:
        start = ctx.wait_for_event(
            lambda item: item.kind == "TEC" and item.kv.get("event") == "START", 8, cursor)
    except TestBlocked:
        _safe_stop(ctx, estop=True)
        raise
    result = start.kv.get("result")
    ctx.measurements["start_result"] = result
    if result not in {"STAGE_UNAVAILABLE", "LIMITS_UNRESOLVED", "SENSOR", "INTERLOCK_OPEN",
                      "FAN_UNAVAILABLE"}:
        device.send(protocol.estop(), "S4 unexpected acceptance ESTOP")
        ctx.check("start_refused", False, detail=start.raw,
                  failure_reason="S4_REFUSAL_NOT_ENFORCED")
        ctx.save_measurements()
        return
    ctx.check("start_refused", True, detail=result)
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 120)),
                         min_frames=int(ctx.definition.params.get("min_frames", 20)),
                         label="S4 no-response")
    current_max = max((frame.current_a for frame in frames
                       if frame.electrical_valid() and frame.current_a is not None), default=None)
    baseline = analysis.tmean(frames[0]) if frames else None
    temperatures = [analysis.tmean(frame) for frame in frames]
    change = None
    if baseline is not None:
        valid = [value for value in temperatures if value is not None]
        change = max((abs(value - baseline) for value in valid), default=None)
    ctx.measurements.update({"current_max_a": current_max, "thermal_change_c": change,
                             "frames": len(frames)})
    ctx.check_closed("no_active_current", current_max, None,
                     ctx.definition.params.get("off_current_max_a", 0.05))
    ctx.check("no_thermal_response",
              change is not None and change <= ctx.definition.params.get("max_thermal_change_c", 0.5),
              detail=f"{change}", failure_reason="THERMAL_RESPONSE_DESPITE_REFUSAL")
    ctx.check("applied_state_off", all(not frame.cooling_on for frame in frames),
              failure_reason="APPLIED_STATE_ON_DESPITE_REFUSAL")
    ctx.save_measurements()


def handler_ablation(ctx: TestContext) -> None:
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 60)),
                         min_frames=int(ctx.definition.params.get("min_frames", 20)),
                         label="logical ablation")
    single = [frame.temperature("T1") for frame in frames if frame.temp_valid("T1")]
    three = [analysis.tmean(frame) for frame in frames if analysis.tmean(frame) is not None]
    if not single or not three:
        ctx.save_measurements()
        ctx.block("ABLATION_CHANNELS_UNAVAILABLE")
    difference = abs(analysis.mean(single) - analysis.mean(three))  # type: ignore[arg-type]
    ctx.measurements.update({"single_sensor_n": len(single), "three_sensor_n": len(three),
                             "single_mean_c": analysis.mean(single),
                             "three_mean_c": analysis.mean(three),
                             "mean_difference_c": difference})
    ctx.check("same_run_both_feature_sets", len(single) > 0 and len(three) > 0,
              failure_reason="FEATURE_SET_UNAVAILABLE")
    if not ctx.ask_confirm("Confirm T2/T3 were not physically disconnected for this ablation."):
        ctx.check("no_physical_disconnect", False, failure_reason="PHYSICAL_DISCONNECT_USED")
    else:
        ctx.check("no_physical_disconnect", True, detail="logical selection only")
    ctx.check_closed("mean_difference_c", difference, None,
                     ctx.definition.params.get("max_difference_c", 1.0))
    ctx.save_measurements()


def handler_dataset_support(ctx: TestContext) -> None:
    ctx.source = "DERIVED"
    sources = ctx.definition.params.get(
        "requirements", ["A-W09-02", "A-W10-03", "A-W11-03"])
    complete = []
    for test_id in sources:
        result = ctx.store.result(test_id)
        if result is None:
            continue
        for run in result.repetitions:
            metrics = run.get("metrics", {})
            has_command = metrics.get("applied_on_frames") is not None
            has_electrical = (metrics.get("current_mean_a") is not None
                              or metrics.get("current_max_a") is not None)
            has_thermal = (metrics.get("chamber_drop_c") is not None
                           or metrics.get("rise_c") is not None)
            if run.get("valid") and has_command and has_electrical and has_thermal:
                complete.append({"test_id": test_id, "attempt": run.get("attempt")})
    ctx.measurements.update({"complete_runs": complete, "count": len(complete)})
    if not complete:
        ctx.save_measurements()
        ctx.block("NO_COMMAND_APPLIED_POWER_THERMAL_RUN: no recorded run contains the full "
                  "command/applied/electrical/thermal chain")
    ctx.check("a3_dataset_run_present", True, detail=str(len(complete)))
    ctx.save_measurements()


def handler_pzem_reference(ctx: TestContext) -> None:
    ctx.source = "OPERATOR_MEASUREMENT"
    has_reference = ctx.ask_confirm("Is a trusted independent reference meter available?")
    if not has_reference:
        ctx.require_result("A-W15-01")
        notes = ctx.ask_text(
            "Record that this is a plausibility/consistency characterization, not calibration.")
        ctx.notes = notes
        ctx.check("consistency_statement_recorded", bool(notes.strip()),
                  failure_reason="CONSISTENCY_STATEMENT_MISSING")
        ctx.require_attachment("Attach the PZEM consistency report",
                               minimum=int(ctx.definition.params.get("min_files", 1)))
        ctx.save_measurements()
        return
    errors = []
    for index in range(int(ctx.definition.params.get("points", 2))):
        pzem_i = ctx.ask_number(f"Point {index + 1}: PZEM current (A)", "A", 0.0, 50.0)
        ref_i = ctx.ask_number(f"Point {index + 1}: reference current (A)", "A", 0.0, 50.0)
        pzem_v = ctx.ask_number(f"Point {index + 1}: PZEM voltage (V)", "V", 0.0, 30.0)
        ref_v = ctx.ask_number(f"Point {index + 1}: reference voltage (V)", "V", 0.0, 30.0)
        errors.append({"point": index + 1, "current_error_a": pzem_i - ref_i,
                       "voltage_error_v": pzem_v - ref_v})
    ctx.measurements["reference_errors"] = errors
    max_i = max(abs(item["current_error_a"]) for item in errors)
    max_v = max(abs(item["voltage_error_v"]) for item in errors)
    ctx.measurements.update({"max_abs_current_error_a": max_i,
                             "max_abs_voltage_error_v": max_v})
    ctx.check_closed("max_abs_current_error_a", max_i, None,
                     ctx.definition.params.get("max_current_error_a", 0.2))
    ctx.check_closed("max_abs_voltage_error_v", max_v, None,
                     ctx.definition.params.get("max_voltage_error_v", 0.2))
    ctx.require_attachment("Attach the reference-meter comparison record",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_protocol_freeze(ctx: TestContext) -> None:
    ctx.source = "OPERATOR_MEASUREMENT"
    for item in ctx.definition.params.get("items", []):
        if not ctx.ask_confirm(item):
            ctx.check(f"item:{item}", False, failure_reason=f"PROTOCOL_CHANGED: {item}")
    ctx.require_attachment("Attach the frozen protocol document used in the previous wave",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_rehearsal(ctx: TestContext) -> None:
    ctx.source = "OPERATOR_MEASUREMENT"
    count = int(ctx.definition.params.get("count", 3))
    records = []
    for index in range(count):
        setup = ctx.ask_number(f"Rehearsal {index + 1}: setup time (min)", "min", 0.0, 600.0)
        reset = ctx.ask_number(f"Rehearsal {index + 1}: thermal reset time (min)", "min", 0.0, 600.0)
        recovery = ctx.ask_text(f"Rehearsal {index + 1}: failure recovery notes")
        records.append({"setup_min": setup, "reset_min": reset, "recovery": recovery})
    ctx.repetitions = records
    ctx.measurements["rehearsals"] = records
    ctx.check("three_rehearsals", len(records) == count, detail=str(len(records)),
              failure_reason="REHEARSALS_INCOMPLETE")
    ctx.check("setup_times_recorded", all(item["setup_min"] > 0 for item in records),
              failure_reason="SETUP_TIME_MISSING")
    ctx.check("reset_times_recorded", all(item["reset_min"] >= 0 for item in records),
              failure_reason="RESET_TIME_MISSING")
    ctx.require_attachment("Attach the rehearsal record",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_recharacterization(ctx: TestContext) -> None:
    off_frames = ctx.capture(float(ctx.definition.params.get("off_duration_s", 120)),
                             min_frames=int(ctx.definition.params.get("min_frames", 20)),
                             label="W16 OFF envelope")
    off = analysis.electrical_metrics(off_frames)
    ctx.measurements["off_envelope"] = off
    frame = ctx.latest_frame()
    if frame.is_h8 or (frame.output_stage or "").upper() == "DISABLED":
        ctx.save_measurements()
        ctx.block("OUTPUT_STAGE_DISABLED: ON-point and response reruns cannot be executed")
    handler_actuation_trace(ctx)
    cooling = dict(ctx.measurements)
    ctx.operator.info(ctx.definition.test_id,
                      "Now run one S2 door disturbance: open the door after the run starts and "
                      "close it after the agreed interval.")
    s2_frames = ctx.capture(float(ctx.definition.params.get("s2_duration_s", 180)),
                            min_frames=int(ctx.definition.params.get("min_frames", 20)),
                            label="W16 S2")
    ctx.measurements["cooling"] = cooling
    ctx.measurements["s2"] = analysis.s2_metrics(s2_frames)
    ctx.check("off_envelope_captured", off["valid_rate"] >= 0.9,
              detail=f"{off['valid_rate']:.3f}", failure_reason="OFF_ENVELOPE_INCOMPLETE")
    ctx.check("actuation_rerun_captured", cooling.get("current_mean_a") is not None,
              failure_reason="ACTUATION_RERUN_MISSING")
    ctx.check("s2_rerun_captured", ctx.measurements["s2"].get("valid") is True,
              failure_reason="S2_RERUN_MISSING")
    ctx.save_measurements()


def handler_unsupported(ctx: TestContext) -> None:
    ctx.block(ctx.definition.params.get("reason", "UNSUPPORTED_OPERATION"))


def handler_command_reset(ctx: TestContext) -> None:
    device = ctx.require_live_device()
    latest = device.latest_frame()
    if latest is not None and latest.is_h8:
        ctx.block("H8_BENCH_IMAGE: CMDTEST is not part of the H8S command set")
    command_id = f"accept-rst-{uuid.uuid4().hex[:8]}"
    ctx.measurements["validator_command_id"] = command_id
    cursor = device.event_cursor()
    device.send(protocol.cmdtest(command_id, False, 0), "stale-command probe")
    ack = device.wait_for_ack(command_id, 5, cursor)
    ctx.measurements["ack"] = ack.raw if ack else None
    if ack is None or ack.status != "ACCEPTED":
        ctx.save_measurements()
        ctx.block("NO_ACCEPTED_COMMAND_STATE: the local console record is rejected before the "
                  "idempotency store; a network transport or accepted command state is required")
    if ack.applied_cooling != "ON":
        ctx.save_measurements()
        ctx.block("COMMAND_NOT_APPLIED: the accepted record did not reach an ON applied state, "
                  "so stale-actuation resume cannot be tested")
    previous = device.snapshot.boot.boot_id
    if not device.pulse_warm_reset():
        ctx.save_measurements()
        ctx.block("WARM_RESET_PULSE_FAILED")
    boot = device.wait_for_boot(previous, float(ctx.definition.params.get("boot_timeout_s", 12)))
    if boot is None:
        ctx.save_measurements()
        ctx.block("NO_NEW_BOOT_AFTER_RESET")
    frames = ctx.capture(float(ctx.definition.params.get("capture_s", 12)),
                         min_frames=int(ctx.definition.params.get("min_frames", 3)),
                         label="after command reset")
    current_max = max((frame.current_a for frame in frames
                       if frame.electrical_valid() and frame.current_a is not None), default=None)
    ctx.measurements.update({
        "boot_before": previous, "boot_after": boot.boot_id,
        "current_max_a": current_max, "frames": len(frames),
    })
    ctx.check("new_boot_identity", boot.boot_id != previous,
              detail=f"{previous}->{boot.boot_id}", failure_reason="BOOT_ID_DID_NOT_CHANGE")
    ctx.check("default_off_after_reset", all(frame.is_default_off for frame in frames),
              failure_reason="DEFAULT_OFF_NOT_PRESERVED")
    ctx.check("no_stale_applied_command", all(not frame.cooling_on for frame in frames),
              failure_reason="STALE_COMMAND_REAPPLIED")
    ctx.check_closed("no_active_current", current_max, None,
                     ctx.definition.params.get("off_current_max_a", 0.05))
    ctx.save_measurements()


def handler_hardware_config_signoff(ctx: TestContext) -> None:
    frame = ctx.latest_frame()
    runs = []
    for result in ctx.store.results().values():
        if result.repetitions:
            runs.extend({"test_id": result.test_id, "attempt": run.get("attempt"),
                         "valid": run.get("valid")} for run in result.repetitions)
    ctx.measurements.update({"hardware_config_id": frame.hardware_config_id,
                             "run_count": len(runs), "runs": runs})
    ctx.check("hardware_config_is_cg_hw_001", frame.hardware_config_id == "CG-HW-001",
              detail=str(frame.hardware_config_id), failure_reason="HARDWARE_CONFIG_MISMATCH")
    ctx.check("run_records_present", bool(runs), detail=str(len(runs)),
              failure_reason="NO_RUNS_RECORDED")
    disposition = ctx.ask_text(
        "Identify any non-poolable run and its disposition (write 'none' if none).")
    ctx.notes = disposition
    ctx.check("non_poolable_disposition", bool(disposition.strip()),
              failure_reason="NON_POOLABLE_RUNS_NOT_DISPOSITIONED")
    ctx.require_attachment("Attach the CG-HW-001 signoff record",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_campaign_manifest(ctx: TestContext) -> None:
    ctx.source = "OPERATOR_MEASUREMENT"
    unchanged = ctx.ask_confirm("Was the hardware configuration unchanged across the campaign?")
    exceptions = ctx.ask_text("Record exceptions or 'none'.")
    invalid = ctx.ask_text("Record invalid attempts or 'none' (retained, never deleted).")
    ctx.measurements.update({"hardware_unchanged": unchanged, "exceptions": exceptions,
                             "invalid_attempts": invalid})
    ctx.check("hardware_unchanged", unchanged, failure_reason="CAMPAIGN_HARDWARE_CHANGED")
    ctx.check("exceptions_recorded", bool(exceptions.strip()), failure_reason="EXCEPTIONS_NOT_RECORDED")
    ctx.check("invalid_attempts_recorded", bool(invalid.strip()),
              failure_reason="INVALID_ATTEMPTS_NOT_RECORDED")
    ctx.require_attachment("Attach the signed campaign manifest",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


def handler_alignment(ctx: TestContext) -> None:
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 30)),
                         min_frames=int(ctx.definition.params.get("min_frames", 10)),
                         label="field alignment")
    expected = list(ctx.definition.params.get("expected_fields", []))
    missing = [field for field in expected if field not in frames[-1].kv]
    ctx.measurements.update({"expected_fields": expected, "missing_fields": missing,
                             "frames": len(frames)})
    ctx.check("all_expected_fields_present", not missing, detail=str(missing),
              failure_reason="LIVE_FIELDS_MISSING")
    ctx.require_attachment("Attach the online/offline field-alignment record",
                           minimum=int(ctx.definition.params.get("min_files", 1)))
    ctx.save_measurements()


HANDLERS = {
    "bom_csv": handler_bom_csv,
    "photo_inventory": handler_photo_inventory,
    "token_scan": handler_token_scan,
    "sensor_enumeration": handler_sensor_enumeration,
    "sensor_position_qa": handler_sensor_position_qa,
    "bme_check": handler_bme_check,
    "door_cycles": handler_door_cycles,
    "max3485": handler_max3485,
    "ibt2_logic": handler_ibt2_logic,
    "fuse": handler_fuse,
    "fuse_final": handler_fuse_final,
    "polarity": handler_polarity,
    "reset_criterion": handler_reset_criterion,
    "state_reset": handler_state_reset,
    "pzem_recheck": handler_pzem_recheck,
    "drift_recheck": handler_drift_recheck,
    "door_protocol": handler_door_protocol,
    "door_timing": handler_door_timing,
    "invalidation_log": handler_invalidation_log,
    "safe_local": handler_safe_local,
    "s4_method": handler_s4_method,
    "s4_refusal": handler_s4_refusal,
    "ablation": handler_ablation,
    "dataset_support": handler_dataset_support,
    "pzem_reference": handler_pzem_reference,
    "protocol_freeze": handler_protocol_freeze,
    "rehearsal": handler_rehearsal,
    "recharacterization": handler_recharacterization,
    "command_reset": handler_command_reset,
    "hardware_config_signoff": handler_hardware_config_signoff,
    "campaign_manifest": handler_campaign_manifest,
    "alignment": handler_alignment,
    "unsupported": handler_unsupported,
}
