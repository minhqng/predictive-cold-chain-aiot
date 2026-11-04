"""Executable test handlers.

Every handler collects evidence and asserts named checks. A handler may
raise :class:`TestBlocked` when a canonical prerequisite cannot be met;
that becomes INCOMPLETE with the exact reason, never PASS.
"""

from __future__ import annotations

import datetime as _dt
import statistics
import time
import uuid
from typing import Any, Callable, Sequence

from . import analysis, protocol
from .model import Outcome, TestBlocked
from .runner import TestContext

# ---------------------------------------------------------------------------
# Declarative check evaluation
# ---------------------------------------------------------------------------


def lookup(metrics: dict[str, Any], key: str) -> Any:
    value: Any = metrics
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def evaluate_checks(ctx: TestContext, metrics: dict[str, Any],
                    checks: Sequence[dict[str, Any]]) -> None:
    for spec in checks:
        name = spec.get("name") or spec.get("key") or "check"
        key = spec.get("key")
        value = lookup(metrics, key) if key else None
        op = spec.get("op", "exists")
        target = spec.get("value")
        detail = spec.get("detail", "")
        reason = spec.get("failure_reason", f"CHECK_FAILED:{name}")
        passed = False
        if op == "exists":
            passed = value is not None
        elif op == "is_true":
            passed = value is True
        elif op == "is_false":
            passed = value is False
        elif op == "is_none":
            passed = value is None
        elif op == "eq":
            passed = value == target
        elif op == "ne":
            passed = value != target
        elif value is None:
            passed = False
        elif op == "ge":
            passed = value >= target
        elif op == "gt":
            passed = value > target
        elif op == "le":
            passed = value <= target
        elif op == "lt":
            passed = value < target
        elif op == "between":
            low, high = target
            passed = low <= value <= high
        elif op == "in":
            passed = value in target
        elif op == "not_in":
            passed = value not in target
        else:
            raise ValueError(f"unknown check op {op!r}")
        ctx.check(name, passed,
                  detail=f"{detail} value={value!r}"
                  + (f" expected={target!r}" if target is not None else ""),
                  failure_reason="" if passed else reason)


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------


def _identity_metrics(ctx: TestContext, frames: Sequence[protocol.TelemetryFrame]) -> dict:
    device = ctx.device
    boot = device.snapshot.boot if device is not None else protocol.BootIdentity()
    roms = {role: entry.rom for role, entry in (device.snapshot.rom_map.items()
                                               if device is not None else [])}
    unique_roms = sorted(set(roms.values()))
    seq_regressions = analysis._seq_regressions(frames)
    return {
        "frames": len(frames),
        "device_ids": sorted({frame.device_id for frame in frames if frame.device_id}),
        "boot_ids": sorted({frame.boot_id for frame in frames if frame.boot_id}),
        "firmware_versions": sorted({frame.firmware_version for frame in frames
                                     if frame.firmware_version}),
        "hardware_config_ids": sorted({frame.hardware_config_id for frame in frames
                                       if frame.hardware_config_id}),
        "calibration_ids": sorted({frame.calibration_id for frame in frames
                                   if frame.calibration_id}),
        "seq_regressions": seq_regressions,
        "rom_roles": roms,
        "unique_roms": unique_roms,
        "unique_rom_count": len(unique_roms),
        "t1_rom": roms.get("T1"),
        "t2_rom": roms.get("T2"),
        "t3_rom": roms.get("T3"),
        "spare_rom": roms.get("SPARE"),
        "boot_id": boot.boot_id,
        "boot_count": boot.boot_count,
        "pin_map": boot.pin_map,
        "grammar": boot.grammar,
        "firmware_kind": device.snapshot.firmware_kind if device is not None else None,
    }


def _quality_metrics(frames: Sequence[protocol.TelemetryFrame]) -> dict:
    quality = analysis._counts(frame.quality for frame in frames)
    bad = [frame for frame in frames
           if frame.quality is not None and frame.quality not in protocol.QUALITY_VOCABULARY]
    thermal = analysis._counts(frame.kv.get("thermal_quality") for frame in frames)
    electrical = analysis._counts(frame.kv.get("electrical_quality") for frame in frames)
    return {
        "quality_counts": quality,
        "thermal_quality_counts": thermal,
        "electrical_quality_counts": electrical,
        "invalid_vocabulary_frames": len(bad),
        "valid_frames": sum(1 for frame in frames if frame.quality == "VALID"),
        "nonzero_fault_frames": sum(1 for frame in frames if (frame.fault_bits or 0) != 0),
        "missing_fault_frames": sum(1 for frame in frames if frame.fault_bits is None),
    }


def _snapshot_metrics(frames: Sequence[protocol.TelemetryFrame]) -> dict:
    missing = sum(1 for frame in frames if any(item.startswith("missing:")
                                              for item in frame.warnings))
    warnings = sum(len(frame.warnings) for frame in frames)
    per_field: dict[str, int] = {}
    for frame in frames:
        for warning in frame.warnings:
            per_field[warning] = per_field.get(warning, 0) + 1
    return {
        "frames": len(frames),
        "missing_field_frames": missing,
        "warning_count": warnings,
        "warnings_by_field": per_field,
        "frames_with_identity": sum(1 for frame in frames
                                    if frame.device_id and frame.boot_id and frame.seq is not None),
        "negative_or_zero_current_ok": sum(1 for frame in frames
                                           if frame.current_a is None or frame.current_a >= 0),
    }


def _bme_metrics(frames: Sequence[protocol.TelemetryFrame]) -> dict:
    ambient = [frame.ambient_c for frame in frames
               if frame.ambient_c is not None and frame.ambient_status == "OK"]
    humidity = [frame.humidity_pct for frame in frames
                if frame.humidity_pct is not None and frame.humidity_status == "OK"]
    return {
        "frames": len(frames),
        "ambient_valid_rate": len(ambient) / len(frames) if frames else 0.0,
        "humidity_valid_rate": len(humidity) / len(frames) if frames else 0.0,
        "ambient_mean_c": analysis.mean(ambient),
        "ambient_min_c": min(ambient) if ambient else None,
        "ambient_max_c": max(ambient) if ambient else None,
        "humidity_mean_pct": analysis.mean(humidity),
        "humidity_min_pct": min(humidity) if humidity else None,
        "humidity_max_pct": max(humidity) if humidity else None,
        "ambient_statuses": analysis._counts(frame.ambient_status for frame in frames),
        "humidity_statuses": analysis._counts(frame.humidity_status for frame in frames),
    }


def telemetry_metrics(ctx: TestContext, key: str,
                      frames: Sequence[protocol.TelemetryFrame]) -> dict:
    if key == "identity":
        return _identity_metrics(ctx, frames)
    if key == "quality":
        return _quality_metrics(frames)
    if key == "snapshot":
        return _snapshot_metrics(frames)
    if key == "bme":
        return _bme_metrics(frames)
    if key == "timing":
        return analysis.timing_metrics(frames)
    if key == "acquisition":
        return analysis.acquisition_metrics(frames)
    if key == "consistency":
        return analysis.consistency_metrics(frames)
    if key == "electrical":
        return analysis.electrical_metrics(frames)
    if key == "door":
        return analysis.door_metrics(frames)
    if key == "warmup":
        return analysis.warmup_metrics(frames)
    if key == "cooling_step":
        metrics = analysis.cooling_step_metrics(frames)
        metrics["time_constant"] = analysis.response_time_constant(frames)
        return metrics
    if key == "s2":
        return analysis.s2_metrics(frames)
    if key == "soak":
        return analysis.soak_metrics(frames)
    if key == "active_envelope":
        return analysis.active_envelope(frames)
    if key == "spatial":
        return analysis.spatial_metrics(frames)
    raise ValueError(f"unknown telemetry analysis {key!r}")


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handler_documentary(ctx: TestContext) -> None:
    params = ctx.definition.params
    items: list[str] = list(params.get("items", []))
    unknown_ok = bool(params.get("unknown_ok", False))
    options = ["Confirmed"]
    if unknown_ok:
        options.append("Unknown (documented)")
    options += ["Not confirmed", "Stop"]
    failures = 0
    unknown = 0
    for item in items:
        choice = ctx.ask_choice(item, options)
        if choice == "Stop":
            raise TestBlocked("OPERATOR_STOPPED")
        if choice == "Not confirmed":
            failures += 1
            ctx.check(f"item:{item}", False, detail=choice,
                      failure_reason=f"ITEM_NOT_CONFIRMED: {item}")
        elif choice.startswith("Unknown"):
            unknown += 1
            ctx.check(f"item:{item}", True, detail=choice)
        else:
            ctx.check(f"item:{item}", True, detail=choice)
    ctx.check("all_checklist_items_confirmed", failures == 0,
              detail=f"{len(items) - failures}/{len(items)} confirmed, {unknown} unknown",
              failure_reason="CHECKLIST_ITEM_NOT_CONFIRMED")
    notes = ctx.ask_text(params.get("notes_prompt", "Record inspection notes, operator, date, and any deviation."))
    ctx.notes = notes
    ctx.check("notes_recorded", bool(notes.strip()), failure_reason="NOTES_EMPTY")
    if unknown and not notes.strip():
        ctx.check("unknown_items_documented", False, failure_reason="UNKNOWN_ITEM_NOT_DOCUMENTED")
    minimum = int(params.get("min_files", 1))
    ctx.require_attachment(params.get("evidence_prompt", "Attach photographic or documentary evidence"),
                           minimum=minimum,
                           kinds=params.get("file_kinds"))


def handler_numeric(ctx: TestContext) -> None:
    params = ctx.definition.params
    imported = ctx.imported_files()
    if imported:
        ctx.operator.info(
            ctx.definition.test_id,
            "Existing evidence is imported and attached; read the value from it instead of "
            "recreating the measurement: " + ", ".join(
                str(record.get("stored")) for record in imported),
        )
    values: dict[str, float] = {}
    for spec in params.get("measurements", []):
        value = ctx.ask_number(spec["label"], spec.get("unit", ""),
                               spec.get("min"), spec.get("max"))
        values[spec["key"]] = value
        ctx.check_closed(spec["key"], value, spec.get("min"), spec.get("max"),
                         detail=spec.get("unit", ""))
    ctx.measurements.update(values)
    ctx.source = "OPERATOR_MEASUREMENT"
    notes = ctx.ask_text(params.get("notes_prompt", "Record instrument, range, and measurement conditions."))
    ctx.notes = notes
    ctx.check("notes_recorded", bool(notes.strip()), failure_reason="NOTES_EMPTY")
    ctx.require_attachment(params.get("evidence_prompt", "Attach a photo of the measurement"),
                           minimum=int(params.get("min_files", 1)))


def handler_telemetry(ctx: TestContext) -> None:
    params = ctx.definition.params
    frames = ctx.capture(float(params.get("duration_s", 60)),
                         min_frames=int(params.get("min_frames", 1)),
                         label=params.get("label", "telemetry"))
    metrics = telemetry_metrics(ctx, params["analysis"], frames)
    ctx.measurements.update(metrics)
    ctx.measurements["captured_frames"] = len(frames)
    ctx.save_measurements()
    evaluate_checks(ctx, metrics, params.get("checks", []))
    if params.get("require_photo"):
        ctx.require_attachment(params.get("evidence_prompt", "Attach a photo of the setup"),
                               minimum=int(params.get("min_files", 1)))


def _pzem_events(ctx: TestContext, seconds: float) -> list[protocol.ParsedLine]:
    device = ctx.require_live_device()
    cursor = device.event_cursor()
    deadline = time.monotonic() + seconds
    events: list[protocol.ParsedLine] = []
    while time.monotonic() < deadline:
        new, cursor = device.events_since(cursor)
        events.extend(item for item in new if item.kind == "PZEM_RANGE")
        if events:
            break
        if ctx.operator.cancelled():
            raise TestBlocked("OPERATOR_CANCELLED")
        time.sleep(0.1)
    return events


def handler_pzem_range(ctx: TestContext) -> None:
    events = _pzem_events(ctx, float(ctx.definition.params.get("timeout_s", 8)))
    if not events:
        ctx.block("PZEM_RANGE_LINE_NOT_SEEN: power-cycle the 12 V PSU so the meter re-reads its range, then rerun")
    event = events[-1]
    profile = event.kv.get("profile")
    value = event.kv.get("value")
    status = event.kv.get("status")
    ctx.measurements.update({"profile": profile, "value": value, "status": status,
                             "crc_ok": event.kv.get("crc_ok"), "raw": event.raw})
    ctx.check("pzem_range_status_ok", status == "OK", detail=str(status),
              failure_reason="PZEM_RANGE_READ_FAILED")
    ctx.check("pzem_profile_50a", profile == "50A", detail=str(profile),
              failure_reason="PZEM_PROFILE_NOT_50A")
    ctx.check("pzem_range_value", value in {"0x0001", "0x1"}, detail=str(value),
              failure_reason="PZEM_RANGE_VALUE_NOT_0x0001")
    ctx.check("pzem_range_crc_ok", event.kv.get("crc_ok") == "1",
              failure_reason="PZEM_RANGE_CRC_FAILED")
    ctx.save_measurements()


def handler_pzem_link(ctx: TestContext) -> None:
    params = ctx.definition.params
    device = ctx.require_live_device()
    cursor = device.event_cursor()
    frames = ctx.capture(float(params.get("duration_s", 60)),
                         min_frames=int(params.get("min_frames", 10)),
                         label="PZEM link")
    events, _ = device.events_since(cursor)
    pzem = [event for event in events if event.kind == "PZEM"]
    ok = [event for event in pzem if event.kv.get("status") == "OK"]
    crc_ok = [event for event in pzem if event.kv.get("crc_ok") == "1"]
    electrical = analysis.electrical_metrics(frames)
    metrics = {
        "pzem_frames": len(pzem),
        "pzem_ok_frames": len(ok),
        "pzem_ok_rate": len(ok) / len(pzem) if pzem else None,
        "pzem_crc_ok_rate": len(crc_ok) / len(pzem) if pzem else None,
        "telemetry_valid_rate": electrical["valid_rate"],
        "voltage_mean_v": electrical["voltage_mean_v"],
        "current_mean_a": electrical["current_mean_a"],
        "current_max_a": electrical["current_max_a"],
        "link_source": "PZEM_LINES" if pzem else "TELEMETRY_ELECTRICAL_STATUS",
    }
    ctx.measurements.update(metrics)
    if not pzem:
        ctx.save_measurements()
        ctx.block("NO_PZEM_LINES: CRC and framing evidence requires #CG PZEM polls; "
                  "telemetry electrical status alone is not a substitute")
    ctx.check("pzem_polls_present", len(pzem) >= int(params.get("min_polls", 10)),
              detail=f"{len(pzem)}", failure_reason="PZEM_POLLS_MISSING")
    ctx.check_closed("pzem_ok_rate", metrics["pzem_ok_rate"], 0.9, 1.0)
    ctx.check_closed("pzem_crc_ok_rate", metrics["pzem_crc_ok_rate"], 0.9, 1.0)
    ctx.check_closed("voltage_mean_v", metrics["voltage_mean_v"], 11.5, 12.5)
    ctx.save_measurements()
    evaluate_checks(ctx, metrics, params.get("checks", []))


def _command_ack_event(ctx: TestContext, command_id: str, cursor: int) -> protocol.AckRecord | None:
    device = ctx.require_live_device()
    return device.wait_for_ack(command_id, float(ctx.definition.params.get("ack_timeout_s", 5)), cursor)


def handler_command_parser(ctx: TestContext) -> None:
    device = ctx.require_live_device()
    latest = device.latest_frame()
    if latest is not None and latest.is_h8:
        ctx.block("H8_BENCH_IMAGE: canonical console probes are not sent to the H8S command set")
    malformed = list(protocol.PROBE_LINES)
    start_cursor = device.event_cursor()
    cursor = start_cursor
    for line in malformed:
        device.send((line + "\n").encode("ascii"), "parser probe")
    deadline = time.monotonic() + float(ctx.definition.params.get("timeout_s", 4))
    errors = []
    while time.monotonic() < deadline and len(errors) < len(malformed):
        new, cursor = device.events_since(cursor)
        errors.extend(event for event in new if event.kind == "ERR")
        time.sleep(0.1)
    ctx.check("malformed_lines_rejected", len(errors) >= len(malformed),
              detail=f"{len(errors)}/{len(malformed)} #CG ERR lines",
              failure_reason="MALFORMED_COMMAND_NOT_REJECTED")
    ctx.measurements["malformed_probes"] = list(malformed)
    ctx.measurements["rejections"] = [event.raw for event in errors]
    ctx.check("console_duty_bound_rejected",
              any("CMDTEST_BAD_DUTY" in event.raw for event in errors),
              detail=str([event.raw for event in errors]),
              failure_reason="OUT_OF_RANGE_DUTY_ACCEPTED_BY_PARSER")

    command_id = f"accept-src-{uuid.uuid4().hex[:8]}"
    ctx.measurements["validator_command_id"] = command_id
    device.send(protocol.cmdtest(command_id, False, 0), "canonical validator probe")
    ack = _command_ack_event(ctx, command_id, start_cursor)
    if ack is None:
        ctx.block("CMDACK_TIMEOUT: cannot exercise the canonical validator")
    ctx.measurements["validator_ack"] = ack.raw
    ctx.check("canonical_validator_present", ack.status in protocol.ACK_VOCABULARY,
              detail=ack.status, failure_reason="ACK_STATUS_NOT_CANONICAL")
    ctx.check("fail_closed_rejection", ack.status in {"REJECTED", "SAFETY_BLOCKED"},
              detail=f"{ack.status}/{ack.reason}", failure_reason="VALIDATOR_NOT_FAIL_CLOSED")
    ctx.check("no_actuation_on_rejected_record", ack.applied_cooling == "OFF",
              detail=ack.applied_cooling, failure_reason="REJECTED_RECORD_APPLIED")
    ctx.check("validator_reports_output_stage", ack.output_stage in {"ENABLED", "DISABLED"},
              detail=ack.output_stage, failure_reason="ACK_OMITS_OUTPUT_STAGE")
    ctx.save_measurements()
    if ack.status == "SAFETY_BLOCKED":
        ctx.block("NETWORK_TRANSPORT_UNAVAILABLE: the local source gate precedes field-level "
                  "validation, so canonical duty/device/expiry checks are unreachable")


def handler_command_expiry(ctx: TestContext) -> None:
    device = ctx.require_live_device()
    latest = device.latest_frame()
    if latest is not None and latest.is_h8:
        ctx.block("H8_BENCH_IMAGE: CMDTEST is not part of the H8S command set")
    command_id = f"accept-exp-{uuid.uuid4().hex[:8]}"
    ctx.measurements["validator_command_id"] = command_id
    cursor = device.event_cursor()
    device.send(protocol.cmdtest(command_id, False, 0), "expiry probe")
    ack = _command_ack_event(ctx, command_id, cursor)
    if ack is None:
        ctx.block("CMDACK_TIMEOUT: cannot exercise expiry validation")
    ctx.measurements.update({
        "ack": ack.raw, "status": ack.status, "reason": ack.reason,
        "expiry_evaluable": ack.expiry_evaluable,
        "applied_cooling": ack.applied_cooling,
    })
    ctx.check("command_refused", ack.status in {"REJECTED", "SAFETY_BLOCKED"},
              detail=f"{ack.status}/{ack.reason}", failure_reason="UNVERIFIABLE_EXPIRY_NOT_REJECTED")
    ctx.check("expiry_evaluable_reported_false", ack.expiry_evaluable is False,
              detail=str(ack.expiry_evaluable), failure_reason="EXPIRY_EVALUABILITY_NOT_REPORTED")
    ctx.check("no_actuation_on_rejected_command", ack.applied_cooling == "OFF",
              detail=ack.applied_cooling, failure_reason="REJECTED_COMMAND_APPLIED")
    ctx.save_measurements()
    ctx.block("NO_WALL_CLOCK: the exact expired-command scenario needs an issuer clock; "
              "the observed fail-closed refusal is recorded, not a PASS")


def handler_applied_state(ctx: TestContext) -> None:
    latest = ctx.latest_frame()
    if latest.is_h8:
        ctx.block("H8_BENCH_IMAGE: the H8S frame has no canonical desired/applied ACK fields")
    frames = ctx.capture(float(ctx.definition.params.get("duration_s", 30)),
                         min_frames=int(ctx.definition.params.get("min_frames", 10)),
                         label="applied state")
    metrics = {
        "frames": len(frames),
        "with_applied_field": sum(1 for frame in frames if frame.cooling_applied is not None),
        "applied_source": sorted({frame.kv.get("cooling_applied_source", "") for frame in frames}),
        "default_off_frames": sum(1 for frame in frames if frame.is_default_off),
    }
    ctx.measurements.update(metrics)
    ctx.check("applied_state_present", metrics["with_applied_field"] == len(frames),
              detail=f"{metrics['with_applied_field']}/{len(frames)}",
              failure_reason="APPLIED_STATE_MISSING")
    ctx.check("default_off_observed", metrics["default_off_frames"] == len(frames),
              detail=f"{metrics['default_off_frames']}/{len(frames)}",
              failure_reason="DEFAULT_OFF_NOT_OBSERVED")
    ctx.check("applied_source_is_firmware", "FIRMWARE_OUTPUT_STATE" in metrics["applied_source"],
              detail=str(metrics["applied_source"]), failure_reason="APPLIED_STATE_SOURCE_UNKNOWN")
    ctx.save_measurements()
    evaluate_checks(ctx, metrics, ctx.definition.params.get("checks", []))


def handler_reset_series(ctx: TestContext) -> None:
    params = ctx.definition.params
    device = ctx.require_live_device()
    warm = int(params.get("warm_resets", 5))
    cold = int(params.get("cold_boots", 5))
    capture_s = float(params.get("capture_s", 8))
    off_max = float(params.get("off_current_max_a", 0.05))
    off_power_max = float(params.get("off_power_max_w", 1.0))
    events: list[dict[str, Any]] = []
    for index in range(warm):
        previous = device.snapshot.boot.boot_id
        ctx.progress(f"warm reset {index + 1}/{warm}", (index) / max(1, warm + cold))
        if not device.reboot_warm():
            ctx.save_measurements()
            ctx.block("WARM_REBOOT_FAILED: close/reopen + DTR/RTS drop did not complete")
        boot = device.wait_for_boot(previous, float(params.get("boot_timeout_s", 12)))
        if boot is None:
            ctx.save_measurements()
            ctx.block(f"NO_NEW_BOOT_AFTER_WARM_RESET {index + 1}")
        frames = ctx.capture(capture_s, min_frames=1, label="after warm reset")
        events.append(_reset_event("WARM_RESET", previous, boot.boot_id, frames, off_max, off_power_max,
                                   _rom_snapshot(device)))
    if cold:
        if not ctx.ask_confirm(
                "Cold boot requires the ESP32 logic power to come from USB, not the 12 V/XL4015 "
                "rail. If the board is powered from the 12 V rail, USB removal is NOT a power cycle "
                "and this test must stop. Confirm USB logic power."):
            ctx.save_measurements()
            ctx.block("COLD_BOOT_POWER_TOPOLOGY_UNSUPPORTED: do not switch the energized TEC branch")
    for index in range(cold):
        previous = device.snapshot.boot.boot_id
        ctx.progress(f"cold boot {index + 1}/{cold}", (warm + index) / max(1, warm + cold))
        if not device.prepare_cold_boot():
            ctx.save_measurements()
            ctx.block("COLD_BOOT_PORT_PREPARE_FAILED")
        ctx.operator.info(
            ctx.definition.test_id,
            "Cold boot: unplug the ESP32 USB cable, wait 3 seconds, plug it back in. "
            "Do NOT touch the 12 V PSU, the TEC fuse, or any power branch. "
            "This board has no reset button; USB removal is the logic-power cycle.",
        )
        if not ctx.ask_confirm("Confirm the USB cable has been replugged."):
            ctx.save_measurements()
            ctx.block(f"COLD_BOOT_NOT_PERFORMED {index + 1}")
        if not device.reopen_after_cold_boot():
            ctx.save_measurements()
            ctx.block(f"COLD_BOOT_REOPEN_FAILED {index + 1}")
        boot = device.wait_for_boot(previous, float(params.get("cold_boot_timeout_s", 30)))
        if boot is None:
            ctx.save_measurements()
            ctx.block(f"NO_NEW_BOOT_AFTER_COLD_BOOT {index + 1}")
        frames = ctx.capture(capture_s, min_frames=1, label="after cold boot")
        events.append(_reset_event("COLD_BOOT", previous, boot.boot_id, frames, off_max, off_power_max,
                                   _rom_snapshot(device)))
    ctx.repetitions = events
    ctx.measurements["events"] = events
    ctx.measurements["event_count"] = len(events)
    boots = {event["boot_after"] for event in events}
    currents = [event["current_max_a"] for event in events if event["current_max_a"] is not None]
    ctx.check("all_events_observed", len(events) == warm + cold,
              detail=f"{len(events)}/{warm + cold}", failure_reason="RESET_EVENT_MISSING")
    ctx.check("every_event_new_boot", all(event["new_boot"] for event in events),
              failure_reason="BOOT_IDENTITY_DID_NOT_CHANGE")
    ctx.check("unique_boot_ids", len(boots) == len(events) and None not in boots,
              detail=str(len(boots)), failure_reason="BOOT_IDS_REPEATED")
    ctx.check("electrical_evidence_present",
              bool(events) and all(event["valid_electrical_frames"] >= 1 for event in events),
              detail=str([event["valid_electrical_frames"] for event in events]),
              failure_reason="NO_PZEM_EVIDENCE_DURING_RESET")
    ctx.check("default_off_all", bool(events) and all(event["default_off_all"] for event in events),
              failure_reason="DEFAULT_OFF_NOT_OBSERVED")
    ctx.check("no_unintended_current",
              bool(events) and all(event["current_max_a"] is not None
                                   and event["current_max_a"] <= off_max for event in events),
              detail=f"max={max(currents) if currents else None} A", failure_reason="ACTIVE_CURRENT_DURING_RESET")
    ctx.check("no_unintended_power",
              bool(events) and all(event["power_max_w"] is not None
                                   and event["power_max_w"] <= off_power_max for event in events),
              failure_reason="ACTIVE_POWER_DURING_RESET")
    rom_maps = [tuple(sorted((event.get("roms") or {}).items())) for event in events]
    ctx.check("rom_map_stable",
              bool(rom_maps) and all(mapping for mapping in rom_maps)
              and all(mapping == rom_maps[0] for mapping in rom_maps),
              detail=f"{len(set(rom_maps))} distinct maps", failure_reason="ROM_MAP_CHANGED_ACROSS_RESET")
    ctx.save_measurements()


def _rom_snapshot(device: Any) -> dict[str, str]:
    return {role: entry.rom for role, entry in device.snapshot.rom_map.items()}


def _reset_event(kind: str, boot_before: str | None, boot_after: str | None,
                 frames: Sequence[protocol.TelemetryFrame], off_max: float,
                 power_max: float, roms: dict[str, str] | None = None) -> dict[str, Any]:
    currents = [frame.current_a for frame in frames if frame.electrical_valid()]
    powers = [frame.power_w for frame in frames if frame.electrical_valid()]
    return {
        "event": kind,
        "boot_before": boot_before,
        "boot_after": boot_after,
        "new_boot": bool(boot_after and boot_after != boot_before),
        "frames": len(frames),
        "valid_electrical_frames": len(currents),
        "current_max_a": max((value for value in currents if value is not None), default=None),
        "power_max_w": max((value for value in powers if value is not None), default=None),
        "default_off_all": all(frame.is_default_off for frame in frames),
        "off_envelope_a": off_max,
        "off_power_envelope_w": power_max,
        "roms": roms or {},
    }


def _run_frame_metrics(scenario: str, frames: Sequence[protocol.TelemetryFrame]) -> dict:
    if scenario == "WARMUP":
        return analysis.warmup_metrics(frames)
    if scenario == "COOLING_STEP":
        metrics = analysis.cooling_step_metrics(frames)
        metrics["time_constant"] = analysis.response_time_constant(frames)
        return metrics
    if scenario == "S2":
        return analysis.s2_metrics(frames)
    return analysis.soak_metrics(frames)


def _run_valid(scenario: str, metrics: dict, params: dict[str, Any]) -> tuple[bool, str]:
    coverage = metrics.get("coverage", 1.0)
    if coverage is not None and coverage < params.get("min_coverage", 0.8):
        return False, f"LOW_COVERAGE {coverage:.2f}"
    if scenario == "WARMUP":
        if not metrics.get("door_closed_throughout"):
            return False, "DOOR_OPEN_DURING_WARMUP"
        if not metrics.get("cooling_off_throughout"):
            return False, "COOLING_ON_DURING_WARMUP"
        if metrics.get("slope_c_per_min") is None:
            return False, "NO_TEMPERATURE_SERIES"
    elif scenario == "COOLING_STEP":
        if metrics.get("cooling_frames", 0) == 0:
            return False, "NO_COOLING_FRAMES"
        if (metrics.get("current_max_a") or 0.0) < params.get("min_current_a", 0.1):
            return False, "NO_ACTIVE_CURRENT"
        if metrics.get("applied_on_frames", 0) == 0:
            return False, "APPLIED_STATE_NEVER_ON"
        if metrics.get("hot_side_max_c") is None:
            return False, "NO_HOT_SIDE_SERIES"
        if metrics["hot_side_max_c"] > params.get("hot_side_max_c", 55.0):
            return False, "HOT_SIDE_LIMIT_EXCEEDED"
        if (metrics.get("fault_bits_max") or 0) != 0:
            return False, "FAULT_BITS_NONZERO"
    elif scenario == "S1":
        if (metrics.get("thermal_valid_rate") or 0.0) < 0.9:
            return False, "THERMAL_VALID_RATE_LOW"
        if (metrics.get("electrical_valid_rate") or 0.0) < 0.9:
            return False, "ELECTRICAL_VALID_RATE_LOW"
        if metrics.get("boot_changes") != 0:
            return False, "REBOOT_OR_MISSING_BOOT_ID"
    elif scenario == "S2":
        if not metrics.get("valid"):
            return False, metrics.get("reason", "S2_INVALID")
        if not metrics.get("open_durations_s"):
            return False, "DOOR_DURATION_MISSING"
    return True, ""


def handler_run_series(ctx: TestContext) -> None:
    params = ctx.definition.params
    scenario = params.get("scenario", "S1")
    required = int(params.get("runs_required", 1))
    duration = float(params.get("duration_s", 300))
    requires_actuation = bool(params.get("requires_actuation", False))
    if requires_actuation:
        frame = ctx.latest_frame()
        if (frame.output_stage or "").upper() == "DISABLED":
            ctx.block("OUTPUT_STAGE_COMPILED_OUT: this firmware build cannot energize the TEC; "
                      "a supervised stage-enabled image is required")
    runs: list[dict[str, Any]] = []
    valid = 0
    attempts = 0
    try:
        while valid < required:
            attempts += 1
            if attempts > int(params.get("max_attempts", required * 3)):
                ctx.block(f"VALID_RUN_TARGET_NOT_REACHED valid={valid}/{required}")
            choice = ctx.ask_choice(
                f"Run {valid + 1}/{required} — {scenario}. Start a valid run or record an invalid attempt?",
                ["Start run", "Record invalid attempt", "Stop"],
            )
            if choice == "Stop":
                ctx.block(f"OPERATOR_STOPPED valid={valid}/{required}")
            if choice == "Record invalid attempt":
                reason = ctx.ask_text(
                    "Reason this attempt is invalid (it is retained, never deleted):")
                runs.append({"valid": False, "reason": reason, "attempt": attempts})
                continue
            if requires_actuation:
                frame = ctx.latest_frame()
                if (frame.output_stage or "").upper() == "DISABLED":
                    ctx.block("OUTPUT_STAGE_COMPILED_OUT_DURING_RUN")
            ctx.progress(f"run {valid + 1}/{required} capturing", 0.0)
            if scenario == "S2" and params.get("door_protocol"):
                open_after = float(params["door_protocol"].get("open_after_s", 60))
                open_for = float(params["door_protocol"].get("open_for_s", 15))
                ctx.operator.info(
                    ctx.definition.test_id,
                    f"Prepare to open the chamber door after {open_after:.0f} s and keep it "
                    f"open for {open_for:.0f} s. The MC-38 transition is the timing authority.")
            started = False
            if requires_actuation:
                started, _ = _arm_and_start(ctx, min(600, int(duration) + 5))
                if not started:
                    break
            abnormal = None
            stop_event = None
            try:
                frames = ctx.capture(
                    duration, min_frames=int(params.get("min_frames", 10)),
                    stop_predicate=(lambda captured: any(
                        _abnormal_reason(ctx, frame) for frame in captured))
                    if requires_actuation else None,
                    label=f"{scenario} run {valid + 1}")
                if requires_actuation:
                    abnormal = next((_abnormal_reason(ctx, frame) for frame in frames
                                     if _abnormal_reason(ctx, frame)), None)
            finally:
                if started:
                    stop_event = _stop_cooling(ctx)
            if requires_actuation and started and stop_event is None:
                runs.append({"valid": False, "reason": "STOP_NOT_ACKNOWLEDGED",
                             "attempt": attempts, "frames": len(frames)})
                break
            if abnormal is not None:
                runs.append({"valid": False, "reason": f"SAFETY_STOP:{abnormal}",
                             "attempt": attempts, "frames": len(frames),
                             "metrics": _run_frame_metrics(scenario, frames)})
                ctx.check("no_safety_stop", False, detail=abnormal,
                          failure_reason=f"SAFETY_STOP_TRIGGERED:{abnormal}")
                break
            metrics = _run_frame_metrics(scenario, frames)
            if requires_actuation:
                metrics["stop_event"] = stop_event.raw if stop_event else None
            if scenario == "S2" and ctx.config.get("critical_tmax_c") is not None:
                metrics["door_critical_s"] = analysis.door_to_critical(
                    frames, float(ctx.config["critical_tmax_c"]))
            ok, reason = _run_valid(scenario, metrics, params)
            record = {
                "valid": ok,
                "reason": reason,
                "attempt": attempts,
                "frames": len(frames),
                "metrics": metrics,
                "started_at": frames[0].host_time.isoformat() if frames else None,
                "ended_at": frames[-1].host_time.isoformat() if frames else None,
            }
            runs.append(record)
            if ok:
                valid += 1
                ctx.check(f"run_{valid}_valid", True, detail=scenario)
    finally:
        ctx.repetitions = runs
        ctx.measurements["runs"] = runs
        ctx.measurements["valid_runs"] = valid
        ctx.measurements["attempts"] = attempts
        ctx.save_measurements()
    summary_keys = params.get("summary_keys", [])
    summary: dict[str, Any] = {}
    for key in summary_keys:
        values = [lookup(run.get("metrics", {}), key) for run in runs if run.get("valid")]
        clean = [float(value) for value in values if isinstance(value, (int, float))]
        summary[key] = {
            "n": len(clean),
            "mean": analysis.mean(clean),
            "sd": analysis.sd(clean),
            "cv": analysis.cv(clean),
            "min": min(clean) if clean else None,
            "max": max(clean) if clean else None,
        }
    ctx.measurements["summary"] = summary
    ctx.check("valid_run_count", valid >= required, detail=f"{valid}/{required}",
              failure_reason="VALID_RUN_COUNT_BELOW_TARGET")
    ctx.save_measurements()


def _ensure_stage_enabled(ctx: TestContext) -> protocol.TelemetryFrame:
    frame = ctx.latest_frame()
    if frame.is_h8:
        ctx.block("H8_BENCH_IMAGE: the installed image speaks the H8S command protocol, "
                  "not the canonical W06 console; flash the W06 acceptance firmware")
    stage = (frame.output_stage or "").upper()
    if stage == "DISABLED":
        ctx.block("OUTPUT_STAGE_COMPILED_OUT: the shipped firmware cannot energize the TEC")
    if stage not in {"ENABLED"}:
        ctx.block(f"OUTPUT_STAGE_UNKNOWN: {stage or 'missing'}")
    return frame


DEFAULT_PRECHECKS = (
    "Fuse installed and correct",
    "Fan available and unobstructed",
    "No loose terminal or exposed conductor",
    "Operator present and able to remove power",
)


def _actuation_prechecks(ctx: TestContext) -> None:
    for item in ctx.definition.params.get("precheck_items", DEFAULT_PRECHECKS):
        if not ctx.ask_confirm(f"Supervised precheck: {item}"):
            ctx.block(f"PRECHECK_NOT_CONFIRMED: {item}")


def _safe_stop(ctx: TestContext, estop: bool = False) -> None:
    try:
        device = ctx.device
        if device is None:
            return
        device.send(protocol.estop() if estop else protocol.stop(),
                    "safety ESTOP" if estop else "safety STOP")
    except Exception:
        pass


def _wait_for_off(ctx: TestContext, timeout_s: float = 120.0) -> None:
    device = ctx.require_live_device()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        frame = device.latest_frame()
        if frame is not None and frame.state == "OFF" and not frame.cooling_on:
            return
        if ctx.operator.cancelled():
            raise TestBlocked("OPERATOR_CANCELLED")
        ctx.progress("waiting for COOLDOWN to reach OFF", None)
        time.sleep(1.0)
    ctx.block(f"NOT_OFF_BEFORE_ARM: state did not reach OFF within {timeout_s:.0f}s")


def _arm_and_start(ctx: TestContext, duration_s: int) -> tuple[bool, Any]:
    device = ctx.require_live_device()
    _actuation_prechecks(ctx)
    _wait_for_off(ctx)
    token = device.snapshot.auth_token
    if not token:
        token = ctx.ask_text("Enter the 8-hex ARM token printed at boot (#CG AUTH)").strip()
    frame = ctx.latest_frame()
    supervised = (str(frame.kv.get("supervised_bench")) == "1"
                  or str(frame.kv.get("bench_policy", "")).upper().startswith("SUPERVISED"))
    if supervised:
        cursor = device.event_cursor()
        device.send(protocol.supervise(token), "SUPERVISE")
        event = ctx.wait_for_event(
            lambda item: item.kind == "TEC" and item.kv.get("event") == "SUPERVISE",
            6, cursor)
        result = event.kv.get("result") if event is not None else None
        if result != "SUPERVISED_AUTHORIZED":
            ctx.save_measurements()
            ctx.block(f"SUPERVISE_REFUSED: {result}")
        ctx.check("supervise_authorized", True, detail=str(result))
    if not ctx.ask_confirm(f"Send ARM with boot token {token}? This authorizes one bounded run."):
        ctx.block("ARM_NOT_CONFIRMED")
    cursor = device.event_cursor()
    device.send(protocol.arm(token), "ARM")
    event = ctx.wait_for_event(
        lambda item: item.kind == "TEC" and item.kv.get("event") == "ARM", 6, cursor)
    if event.kv.get("result") != "ARMED":
        ctx.save_measurements()
        ctx.block(f"ARM_REFUSED: {event.raw}")
    if not ctx.ask_confirm(f"Send START {duration_s} s now? Confirm the operator is present "
                           "and can remove power."):
        _safe_stop(ctx)
        ctx.block("START_NOT_CONFIRMED")
    cursor = device.event_cursor()
    try:
        device.send(protocol.start(duration_s), "START")
    except Exception:
        _safe_stop(ctx, estop=True)
        raise
    try:
        event = ctx.wait_for_event(
            lambda item: item.kind == "TEC" and item.kv.get("event") == "START", 8, cursor)
    except TestBlocked:
        _safe_stop(ctx, estop=True)
        raise
    result = event.kv.get("result")
    if result in {"STAGE_UNAVAILABLE", "LIMITS_UNRESOLVED", "SENSOR", "INTERLOCK_OPEN",
                  "FAN_UNAVAILABLE"}:
        _safe_stop(ctx)
        ctx.save_measurements()
        ctx.block(f"START_REFUSED: {result}")
    if result not in {"START_OK", "COOLING", "OK"}:
        _safe_stop(ctx)
        ctx.check("start_accepted", False, detail=event.raw,
                  failure_reason=f"START_REFUSED:{result}")
        ctx.save_measurements()
        return False, event
    ctx.check("start_accepted", True, detail=event.raw)
    return True, event


def _stop_cooling(ctx: TestContext) -> Any:
    device = ctx.require_live_device()
    cursor = device.event_cursor()
    device.send(protocol.stop(), "STOP")
    event = device.wait_for_event(
        lambda item: item.kind == "TEC" and item.kv.get("event") in {"STOP", "END"},
        10, cursor)
    if event is None:
        ctx.measurements["stop_timeout_escalated"] = True
        _safe_stop(ctx, estop=True)
        ctx.check("stop_confirmed", False, failure_reason="STOP_NOT_ACKNOWLEDGED")
        return None
    ctx.check("stop_confirmed", True, detail=event.raw)
    return event


def _abnormal_reason(ctx: TestContext, frame: protocol.TelemetryFrame) -> str | None:
    params = ctx.definition.params
    if (frame.fault_bits or 0) != 0:
        return f"FAULT_BITS=0x{frame.fault_bits:08X}"
    if frame.state == "FAULT_LATCH":
        return "FAULT_LATCH"
    maximum = params.get("max_current_a", 30.0)
    if frame.current_a is not None and frame.current_a > maximum:
        return f"OVERCURRENT={frame.current_a:.2f}A"
    limit = params.get("hot_side_max_c", 55.0)
    if frame.hot_side_c is not None and frame.hot_side_c > limit:
        return f"HOT_SIDE={frame.hot_side_c:.2f}C"
    return None


def handler_actuation_trace(ctx: TestContext) -> None:
    params = ctx.definition.params
    _ensure_stage_enabled(ctx)
    device = ctx.require_live_device()
    _wait_for_off(ctx)
    baseline_s = float(params.get("baseline_s", 10))
    baseline_min_frames = int(params.get("baseline_min_frames", 3))
    off_limit = float(params.get("off_current_max_a", 0.05))
    measured_off = ctx.store.result("A-W03-05")
    if measured_off is not None:
        envelope = measured_off.measurements.get("off_current_max_a")
        if isinstance(envelope, (int, float)):
            off_limit = max(off_limit, float(envelope) + 0.02)
    ctx.measurements["off_current_limit_a"] = off_limit
    baseline = ctx.capture(baseline_s, min_frames=baseline_min_frames,
                           label="pre-START baseline")
    baseline_current = max((frame.current_a for frame in baseline
                            if frame.electrical_valid() and frame.current_a is not None),
                           default=None)
    ctx.measurements["baseline_off_current_max_a"] = baseline_current
    ctx.check("baseline_captured", len(baseline) > 0, detail=str(len(baseline)),
              failure_reason="NO_PRE_START_BASELINE")
    ctx.check("baseline_default_off", all(frame.is_default_off for frame in baseline),
              failure_reason="BASELINE_NOT_DEFAULT_OFF")
    ctx.check_closed("baseline_off_current_max_a", baseline_current, None, off_limit)
    if (baseline_current is None
            or baseline_current > off_limit
            or any(not frame.is_default_off for frame in baseline)):
        ctx.save_measurements()
        ctx.block("BASELINE_NOT_OFF: refusing to energize the TEC while the OFF baseline is "
                  "missing, drawing current, or not in the default-off state")
    duration = int(params.get("duration_s", 60))
    capture_s = min(float(params.get("capture_s", duration)), float(duration))
    started, start_event = _arm_and_start(ctx, duration)
    if not started:
        return
    stop_event = None
    abnormal = None
    try:
        active = ctx.capture(
            capture_s,
            min_frames=int(params.get("min_frames", 10)),
            stop_predicate=lambda captured: any(
                _abnormal_reason(ctx, frame) for frame in captured),
            label="cooling",
        )
        abnormal = next((_abnormal_reason(ctx, frame) for frame in active
                         if _abnormal_reason(ctx, frame)), None)
    finally:
        stop_event = _stop_cooling(ctx)
    frames = baseline + active
    metrics = analysis.cooling_step_metrics(frames)
    metrics["time_constant"] = analysis.response_time_constant(frames)
    metrics["stop_event"] = stop_event.raw if stop_event else None
    metrics["safety_stop_reason"] = abnormal
    ctx.measurements.update(metrics)
    ctx.check("no_safety_stop", abnormal is None, detail=str(abnormal),
              failure_reason=f"SAFETY_STOP_TRIGGERED:{abnormal}")
    ctx.check("cooling_frames_present", metrics["cooling_frames"] > 0,
              detail=str(metrics["cooling_frames"]), failure_reason="NO_COOLING_FRAMES")
    ctx.check_closed("current_mean_a", metrics["current_mean_a"],
                     params.get("min_current_a", 0.1), params.get("max_current_a", 30.0))
    ctx.check_closed("hot_side_max_c", metrics["hot_side_max_c"],
                     None, params.get("hot_side_max_c", 55.0))
    ctx.check("fault_bits_zero", (metrics["fault_bits_max"] or 0) == 0,
              detail=str(metrics["fault_bits_max"]), failure_reason="FAULT_DURING_ACTUATION")
    ctx.check("applied_on", metrics["applied_on_frames"] > 0,
              detail=str(metrics["applied_on_frames"]), failure_reason="APPLIED_STATE_NEVER_ON")
    if params.get("require_chamber_drop", True):
        ctx.check_closed("chamber_drop_c", metrics["chamber_drop_c"],
                         params.get("min_chamber_drop_c", 0.2), None)
    ctx.save_measurements()


def _previous_measurements(ctx: TestContext, test_id: str) -> dict:
    result = ctx.require_result(test_id)
    return dict(result.measurements)


def _measurement_value(result: Any, key: str) -> Any:
    value = lookup(result.measurements or {}, key)
    if isinstance(value, (int, float)):
        return value
    summary = lookup(result.measurements or {}, f"summary.{key}.mean")
    if isinstance(summary, (int, float)):
        return summary
    cooling = lookup(result.measurements or {}, f"cooling.{key}")
    if isinstance(cooling, (int, float)):
        return cooling
    return None


def handler_derived(ctx: TestContext) -> None:
    params = ctx.definition.params
    for test_id in params.get("requirements", []):
        ctx.require_result(test_id)
    compute = params.get("compute", "aggregate")
    metrics = _compute(ctx, compute, params)
    ctx.measurements.update(metrics)
    ctx.source = "HARDWARE" if compute == "config_record" else "DERIVED"
    ctx.save_measurements()
    evaluate_checks(ctx, metrics, params.get("checks", []))
    if params.get("evidence_prompt"):
        ctx.require_attachment(params["evidence_prompt"], minimum=int(params.get("min_files", 1)))


def _compute(ctx: TestContext, compute: str, params: dict[str, Any]) -> dict:
    if compute == "repeatability":
        runs: list[dict] = []
        for test_id in params.get("requirements", []):
            result = ctx.require_result(test_id)
            runs.extend(result.repetitions)
        valid = [run for run in runs if run.get("valid")]
        keys = params.get("keys", [])
        summary = {}
        for key in keys:
            values = [lookup(run.get("metrics", {}), key) for run in valid]
            clean = [float(value) for value in values if isinstance(value, (int, float))]
            summary[key] = {"n": len(clean), "mean": analysis.mean(clean),
                            "sd": analysis.sd(clean), "cv": analysis.cv(clean),
                            "min": min(clean) if clean else None,
                            "max": max(clean) if clean else None}
        return {"valid_runs": len(valid), "summary": summary}
    if compute == "envelope":
        results = {}
        for test_id in params.get("requirements", []):
            results[test_id] = ctx.require_result(test_id)
        active_currents = []
        active_powers = []
        for test_id, result in results.items():
            current = _measurement_value(result, "current_mean_a")
            power = _measurement_value(result, "power_mean_w")
            if isinstance(current, (int, float)) and current > 0:
                active_currents.append(float(current))
            if isinstance(power, (int, float)) and power > 0:
                active_powers.append(float(power))
        off_currents = []
        for test_id in params.get("off_sources", ["A-W03-05"]):
            result = ctx.store.result(test_id)
            if result is None:
                continue
            value = (result.measurements.get("off_current_max_a")
                     if result.measurements.get("off_current_max_a") is not None
                     else result.measurements.get("current_max_a"))
            if isinstance(value, (int, float)):
                off_currents.append(float(value))
        return {
            "sources": sorted(results),
            "healthy_current_min_a": min(active_currents) if active_currents else None,
            "healthy_current_max_a": max(active_currents) if active_currents else None,
            "healthy_power_min_w": min(active_powers) if active_powers else None,
            "healthy_power_max_w": max(active_powers) if active_powers else None,
            "off_current_max_a": max(off_currents) if off_currents else None,
        }
    if compute == "drift_compare":
        baseline = ctx.store.result(params["baseline_test"])
        current = ctx.store.result(params["current_test"])
        if baseline is None:
            ctx.block(f"BASELINE_RESULT_MISSING {params['baseline_test']}")
        if current is None:
            ctx.block(f"CURRENT_RESULT_MISSING {params['current_test']}")
        deltas = {}
        for key in params.get("keys", []):
            first = _measurement_value(baseline, key)
            second = _measurement_value(current, key)
            deltas[key] = ((second - first) if isinstance(first, (int, float))
                           and isinstance(second, (int, float)) else None)
        return {"baseline_test": params["baseline_test"], "current_test": params["current_test"],
                "baseline": {key: _measurement_value(baseline, key) for key in params.get("keys", [])},
                "current": {key: _measurement_value(current, key) for key in params.get("keys", [])},
                "deltas": deltas}
    if compute == "response_delays":
        delays = []
        for test_id in params.get("requirements", []):
            result = ctx.require_result(test_id)
            for run in result.repetitions:
                value = lookup(run.get("metrics", {}), "electrical_delay_s")
                thermal = lookup(run.get("metrics", {}), "thermal_delay_s")
                if isinstance(value, (int, float)):
                    delays.append(value)
                if isinstance(thermal, (int, float)):
                    delays.append(thermal)
        return {"delay_samples_s": delays, "n": len(delays),
                "median_s": analysis.median(delays), "p95_s": analysis.p95(delays),
                "max_s": max(delays) if delays else None}
    if compute == "s2_summary":
        runs = []
        for test_id in params.get("requirements", []):
            result = ctx.require_result(test_id)
            runs.extend(run for run in result.repetitions if run.get("valid"))
        keys = ["baseline_mean_c", "rise_c", "recovery_c", "gradient_peak_c"]
        summary = {}
        for key in keys:
            values = [lookup(run.get("metrics", {}), key) for run in runs]
            clean = [float(value) for value in values if isinstance(value, (int, float))]
            summary[key] = {"n": len(clean), "mean": analysis.mean(clean),
                            "sd": analysis.sd(clean), "cv": analysis.cv(clean),
                            "min": min(clean) if clean else None,
                            "max": max(clean) if clean else None}
        durations = []
        for run in runs:
            durations.extend(lookup(run.get("metrics", {}), "open_durations_s") or [])
        return {"valid_runs": len(runs), "summary": summary,
                "door_durations_s": durations}
    if compute == "spatial":
        runs = []
        for test_id in params.get("requirements", []):
            result = ctx.require_result(test_id)
            runs.extend(run for run in result.repetitions if run.get("valid"))
        gradients = [lookup(run.get("metrics", {}), "gradient_peak_c") for run in runs]
        clean = [float(value) for value in gradients if isinstance(value, (int, float))]
        return {"valid_runs": len(runs), "gradient_samples_c": clean,
                "gradient_mean_c": analysis.mean(clean),
                "gradient_max_c": max(clean) if clean else None}
    if compute == "time_constants":
        taus = []
        for test_id in params.get("requirements", []):
            result = ctx.require_result(test_id)
            for run in result.repetitions:
                value = lookup(run.get("metrics", {}), "time_constant.tau_s")
                if isinstance(value, (int, float)):
                    taus.append(value)
        return {"tau_samples_s": taus, "n": len(taus),
                "median_s": analysis.median(taus), "p95_s": analysis.p95(taus)}
    if compute == "electrical_integrity":
        runs = []
        for test_id in params.get("requirements", []):
            result = ctx.require_result(test_id)
            runs.extend(run for run in result.repetitions if run.get("valid"))
        valid_rates = []
        for run in runs:
            metrics = run.get("metrics", {})
            value = (metrics.get("valid_rate")
                     or metrics.get("electrical_valid_rate")
                     or metrics.get("coverage"))
            if isinstance(value, (int, float)):
                valid_rates.append(float(value))
        return {"valid_runs": len(runs), "min_valid_rate": min(valid_rates) if valid_rates else None,
                "mean_valid_rate": analysis.mean(valid_rates)}
    if compute == "first_response":
        return _previous_measurements(ctx, "A-W04-05")
    if compute == "electrical_delays":
        delays = []
        for test_id in params.get("requirements", []):
            result = ctx.require_result(test_id)
            for run in result.repetitions:
                value = lookup(run.get("metrics", {}), "electrical_delay_s")
                if isinstance(value, (int, float)):
                    delays.append(value)
        return {"delay_samples_s": delays, "n": len(delays),
                "median_s": analysis.median(delays), "p95_s": analysis.p95(delays),
                "max_s": max(delays) if delays else None}
    if compute == "thermal_delays":
        delays = []
        for test_id in params.get("requirements", []):
            result = ctx.require_result(test_id)
            for run in result.repetitions:
                value = lookup(run.get("metrics", {}), "thermal_delay_s")
                if isinstance(value, (int, float)):
                    delays.append(value)
        return {"delay_samples_s": delays, "n": len(delays),
                "median_s": analysis.median(delays), "p95_s": analysis.p95(delays),
                "max_s": max(delays) if delays else None,
                "method": "FIRST_SUSTAINED_CHAMBER_DROP_0_2C_TWO_FRAMES"}
    if compute == "door_critical":
        values = []
        for test_id in params.get("requirements", []):
            result = ctx.require_result(test_id)
            for run in result.repetitions:
                value = lookup(run.get("metrics", {}), "door_critical_s")
                if isinstance(value, (int, float)):
                    values.append(value)
        if not values:
            ctx.block("NO_DOOR_CRITICAL_SAMPLES: set the frozen critical Tmean threshold in Config "
                      "and rerun the S2 series")
        return {"samples_s": values, "n": len(values),
                "median_s": analysis.median(values), "p95_s": analysis.p95(values),
                "max_s": max(values), "min_s": min(values)}
    if compute == "aggregate_results":
        outcomes = {}
        for test_id in params.get("requirements", []):
            result = ctx.store.result(test_id)
            outcomes[test_id] = result.outcome.value if result else "NOT_RUN"
        return {"outcomes": outcomes,
                "pass_count": sum(1 for value in outcomes.values() if value == "PASS"),
                "not_pass": sorted(key for key, value in outcomes.items() if value != "PASS")}
    if compute == "config_record":
        frames = ctx.capture(float(params.get("duration_s", 10)),
                             min_frames=int(params.get("min_frames", 3)), label="config record")
        frame = frames[-1]
        device = ctx.require_live_device()
        roms = {role: entry.rom for role, entry in device.snapshot.rom_map.items()}
        fuse_result = ctx.store.result("A-W08-02")
        profile_result = ctx.store.result("A-W03-04")
        fuse = (fuse_result.measurements.get("fuse_a") if fuse_result else None) \
            or ctx.config.get("fuse_a")
        profile = (profile_result.measurements.get("profile") if profile_result else None) \
            or ctx.config.get("pzem_profile")
        if fuse is None:
            ctx.block("FINAL_FUSE_NOT_RECORDED: run A-W08-02 before freezing the configuration")
        if profile is None:
            ctx.block("PZEM_PROFILE_NOT_RECORDED: run A-W03-04 before freezing the configuration")
        stage = (frame.output_stage or "").upper()
        allowed = ("OFF_ONLY_OUTPUT_STAGE_COMPILED_OUT" if stage == "DISABLED"
                   else "SUPERVISED_ON_WITHIN_MEASURED_ENVELOPE" if stage == "ENABLED"
                   else "UNKNOWN")
        return {
            "device_id": frame.device_id,
            "boot_id": frame.boot_id,
            "firmware_version": frame.firmware_version,
            "hardware_config_id": frame.hardware_config_id,
            "pin_map": device.snapshot.boot.pin_map,
            "calibration_id": frame.calibration_id,
            "roms": roms,
            "unique_rom_count": len(set(roms.values())),
            "positions": {"T1": "CHAMBER_CENTER", "T2": "TEC_HOT_SIDE",
                          "T3": "CHAMBER_BOTTOM", "SPARE": "CHAMBER_NEAR_DOOR"},
            "fuse_a": fuse,
            "pzem_profile": profile,
            "allowed_action": allowed,
            "output_stage": frame.output_stage,
        }
    raise ValueError(f"unknown compute {compute!r}")


def handler_team_evidence(ctx: TestContext) -> None:
    params = ctx.definition.params
    owner = params.get("owner", "B/C/D")
    missing = []
    for item in params.get("items", []):
        if not ctx.ask_confirm(f"{owner} evidence: {item}"):
            missing.append(item)
            ctx.check(f"item:{item}", False, detail="not provided",
                      failure_reason=f"TEAM_DEPENDENCY_{owner}: {item}")
        else:
            ctx.check(f"item:{item}", True, detail="provided")
    if missing:
        ctx.require_attachment(params.get("evidence_prompt", f"Attach {owner} evidence"),
                               minimum=int(params.get("min_files", 1)))
        ctx.block(f"TEAM_DEPENDENCY_{owner}: missing {len(missing)} item(s)")
    ctx.require_attachment(params.get("evidence_prompt", f"Attach {owner} evidence"),
                           minimum=int(params.get("min_files", 1)))
    notes = ctx.ask_text(params.get("notes_prompt", "Record the handover reference and date."))
    ctx.notes = notes
    ctx.check("notes_recorded", bool(notes.strip()), failure_reason="NOTES_EMPTY")


def handler_decision(ctx: TestContext) -> None:
    params = ctx.definition.params
    for item in params.get("required_checks", []):
        if not ctx.ask_confirm(f"Decision input: {item}"):
            ctx.block(f"DECISION_INPUT_MISSING: {item}")
    options = params.get("options", ["GO", "NO-GO"])
    choice = ctx.ask_choice(params.get("question", "Record the technical decision."), options)
    rationale = ctx.ask_text(params.get("rationale_prompt", "Record the rationale and limitations."))
    ctx.source = "OPERATOR_MEASUREMENT"
    ctx.measurements["decision"] = choice
    ctx.measurements["rationale"] = rationale
    ctx.check("decision_recorded", choice in options, detail=choice,
              failure_reason="DECISION_NOT_RECORDED")
    ctx.check("rationale_recorded", bool(rationale.strip()), failure_reason="RATIONALE_EMPTY")
    ctx.require_attachment(params.get("evidence_prompt", "Attach the decision record"),
                           minimum=int(params.get("min_files", 1)))
    ctx.save_measurements()


def handler_composite(ctx: TestContext) -> None:
    params = ctx.definition.params
    ctx.source = "DERIVED"
    allow_blockers = bool(params.get("allow_blockers_documented", False))
    blockers = []
    for test_id in params.get("requirements", []):
        result = ctx.store.result(test_id)
        if result is None:
            ctx.block(f"REQUIREMENT_NOT_RUN {test_id}: signoff requires a recorded attempt")
        outcome = result.outcome.value
        if outcome != "PASS":
            blockers.append(f"{test_id}={outcome}")
            ctx.check(f"requirement:{test_id}", allow_blockers, detail=outcome,
                      failure_reason=f"REQUIREMENT_NOT_PASS {test_id}={outcome}")
        else:
            ctx.check(f"requirement:{test_id}", True, detail="PASS")
    ctx.measurements["blockers"] = blockers
    if allow_blockers:
        note = ctx.ask_text("Sign off with explicit blockers (write 'none' if none):")
        ctx.notes = note
        ctx.check("blockers_documented", bool(note.strip()), failure_reason="BLOCKERS_NOT_DOCUMENTED")
        unnamed = [blocker.split("=")[0] for blocker in blockers
                   if blocker.split("=")[0] not in note]
        ctx.check("blockers_named", not unnamed, detail=str(unnamed),
                  failure_reason="BLOCKERS_NOT_NAMED")
    ctx.require_attachment(params.get("evidence_prompt", "Attach the package index"),
                           minimum=int(params.get("min_files", 1)))
    ctx.save_measurements()


def handler_degraded_sensor(ctx: TestContext) -> None:
    params = ctx.definition.params
    frame = ctx.latest_frame()
    if frame.cooling_on or (frame.current_a or 0) > 0.05:
        ctx.block("TEC_NOT_OFF: stop cooling and remove the TEC fuse before touching a probe")
    for item in params.get("preconditions", []):
        if not ctx.ask_confirm(item):
            ctx.block(f"PRECONDITION_NOT_CONFIRMED: {item}")
    choice = ctx.ask_choice(
        "Physically disconnect one DS18B20 data wire with the TEC off, or record NO-GO.",
        ["Disconnected one probe", "NO-GO — not performed", "Stop"])
    if choice.startswith("NO-GO"):
        ctx.measurements["performed"] = False
        ctx.save_measurements()
        ctx.block("PHYSICAL_FAULT_NOT_INJECTED: disconnect was not performed")
    frames = ctx.capture(float(params.get("duration_s", 60)),
                         min_frames=int(params.get("min_frames", 10)), label="degraded sensor")
    metrics = {
        "frames": len(frames),
        "thermal_invalid_frames": sum(1 for frame in frames
                                      if not all(frame.temp_valid(role) for role in analysis.CHAMBER_ROLES)),
        "thermal_quality": analysis._counts(frame.kv.get("thermal_quality") for frame in frames),
        "overall_quality": analysis._counts(frame.quality for frame in frames),
        "probes_valid_min": min((sum(1 for role in analysis.ALL_ROLES if frame.temp_valid(role))
                                 for frame in frames), default=None),
        "cooling_on_frames": sum(1 for frame in frames if frame.cooling_on),
        "fault_bits_max": max((frame.fault_bits or 0) for frame in frames),
        "rom_roles": {role: entry.rom for role, entry in ctx.require_live_device().snapshot.rom_map.items()},
    }
    ctx.measurements.update(metrics)
    ctx.check("explicit_degraded_state", metrics["thermal_invalid_frames"] > 0,
              detail=str(metrics["thermal_invalid_frames"]), failure_reason="MISSING_SENSOR_NOT_EXPLICIT")
    ctx.check("no_silent_remap", len(set(metrics["rom_roles"].values())) == len(metrics["rom_roles"]),
              failure_reason="ROM_MAP_CHANGED")
    ctx.check("output_stayed_off", metrics["cooling_on_frames"] == 0,
              failure_reason="OUTPUT_ON_DURING_FAULT")
    ctx.ask_confirm("Reconnect the probe now.")
    recovery = ctx.capture(float(params.get("recovery_s", 30)),
                           min_frames=int(params.get("min_frames", 5)), label="recovery")
    recovered = sum(1 for frame in recovery if all(frame.temp_valid(role)
                                                   for role in analysis.CHAMBER_ROLES))
    ctx.measurements["recovery_frames"] = len(recovery)
    ctx.measurements["recovery_valid_frames"] = recovered
    ctx.check("recovery_observed", recovered > 0, detail=str(recovered),
              failure_reason="SENSOR_DID_NOT_RECOVER")
    ctx.save_measurements()
    ctx.require_attachment(params.get("evidence_prompt", "Attach a photo of the disconnected probe"),
                           minimum=int(params.get("min_files", 1)))


def handler_degraded_pzem(ctx: TestContext) -> None:
    params = ctx.definition.params
    frame = ctx.latest_frame()
    if frame.cooling_on or (frame.current_a or 0) > 0.05:
        ctx.block("TEC_NOT_OFF: stop cooling and isolate the branch before removing the PZEM path")
    for item in params.get("preconditions", []):
        if not ctx.ask_confirm(item):
            ctx.block(f"PRECONDITION_NOT_CONFIRMED: {item}")
    choice = ctx.ask_choice(
        "Remove/disable the PZEM communication path with the 12 V PSU off, or record NO-GO.",
        ["Path removed", "NO-GO — not performed", "Stop"])
    if choice.startswith("NO-GO"):
        ctx.save_measurements()
        ctx.block("PHYSICAL_FAULT_NOT_INJECTED: PZEM path was not removed")
    frames = ctx.capture(float(params.get("duration_s", 60)),
                         min_frames=int(params.get("min_frames", 10)), label="PZEM unavailable")
    metrics = {
        "frames": len(frames),
        "electrical_invalid_frames": sum(1 for frame in frames if not frame.electrical_valid()),
        "electrical_quality": analysis._counts(frame.kv.get("electrical_quality") for frame in frames),
        "current_none_frames": sum(1 for frame in frames if frame.current_a is None),
        "cooling_on_frames": sum(1 for frame in frames if frame.cooling_on),
        "state_counts": analysis._counts(frame.state for frame in frames),
        "quality_counts": analysis._counts(frame.quality for frame in frames),
    }
    ctx.measurements.update(metrics)
    ctx.check("explicit_electrical_degradation", metrics["electrical_invalid_frames"] > 0,
              detail=str(metrics["electrical_invalid_frames"]),
              failure_reason="PZEM_LOSS_NOT_EXPLICIT")
    ctx.check("missing_current_not_carried_forward", metrics["current_none_frames"] > 0,
              failure_reason="CURRENT_VALUE_INVENTED")
    ctx.check("no_blind_actuation", metrics["cooling_on_frames"] == 0,
              failure_reason="ACTUATION_WITHOUT_POWER_OBSERVABILITY")
    ctx.ask_confirm("Restore the PZEM communication path now.")
    ctx.require_attachment(params.get("evidence_prompt", "Attach a photo of the removed path"),
                           minimum=int(params.get("min_files", 1)))
    ctx.save_measurements()


def handler_soak(ctx: TestContext) -> None:
    params = ctx.definition.params
    target = float(params.get("duration_s", 7200))
    configured = ctx.config.get("soak_duration_s")
    if configured is not None:
        target = float(configured)
    ctx.progress(f"soak target {target / 3600:.2f} h", 0.0)
    frames = ctx.capture(target, min_frames=int(params.get("min_frames", 60)), label="soak")
    metrics = analysis.soak_metrics(frames)
    ctx.measurements.update(metrics)
    ctx.measurements["target_s"] = target
    if ctx.is_simulated and metrics["duration_s"] < target * 0.98:
        ctx.save_measurements()
        ctx.block("SIMULATED_SESSION_CANNOT_PROVE_SOAK_DURATION")
    ctx.check_closed("duration_s", metrics["duration_s"], target * 0.98, None)
    ctx.check("sensor_errors_bounded", metrics["thermal_valid_rate"] >= 0.95,
              detail=f"{metrics['thermal_valid_rate']:.3f}",
              failure_reason="SENSOR_VALID_RATE_LOW")
    ctx.check("pzem_errors_bounded", metrics["electrical_valid_rate"] >= 0.95,
              detail=f"{metrics['electrical_valid_rate']:.3f}",
              failure_reason="PZEM_VALID_RATE_LOW")
    ctx.check("no_fault_latch", metrics["fault_bits_max"] == 0,
              detail=str(metrics["fault_bits_max"]), failure_reason="FAULT_DURING_SOAK")
    ctx.check("no_reboot", metrics["boot_changes"] == 0,
              detail=str(metrics["boot_changes"]), failure_reason="REBOOT_DURING_SOAK")
    ctx.check_closed("hot_side_bounded", metrics["hot_side_max_c"], None,
                     params.get("hot_side_max_c", 55.0))
    ctx.save_measurements()


def handler_hil_smoke(ctx: TestContext) -> None:
    params = ctx.definition.params
    frames = ctx.capture(float(params.get("duration_s", 30)),
                         min_frames=int(params.get("min_frames", 10)), label="HIL smoke")
    latest = frames[-1]
    device = ctx.require_live_device()
    roms = {role: entry.rom for role, entry in device.snapshot.rom_map.items()}
    metrics = {
        "frames": len(frames),
        "t1_valid": sum(1 for frame in frames if frame.temp_valid("T1")),
        "t2_valid": sum(1 for frame in frames if frame.temp_valid("T2")),
        "t3_valid": sum(1 for frame in frames if frame.temp_valid("T3")),
        "bme_valid": sum(1 for frame in frames
                         if frame.ambient_status == "OK" and frame.humidity_status == "OK"),
        "door_valid": sum(1 for frame in frames if frame.door_open is not None),
        "pzem_valid": sum(1 for frame in frames if frame.electrical_valid()),
        "default_off": all(frame.is_default_off for frame in frames),
        "rom_count": len(set(roms.values())),
        "output_stage": latest.output_stage,
        "fault_bits": latest.fault_bits,
    }
    ctx.measurements.update(metrics)
    ctx.check("three_probes", metrics["t1_valid"] > 0 and metrics["t2_valid"] > 0
              and metrics["t3_valid"] > 0, failure_reason="PROBE_MISSING")
    ctx.check("bme_channel", metrics["bme_valid"] > 0, failure_reason="BME_MISSING")
    ctx.check("door_channel", metrics["door_valid"] == len(frames), failure_reason="DOOR_UNVERIFIED")
    ctx.check("pzem_channel", metrics["pzem_valid"] > 0, failure_reason="PZEM_MISSING")
    ctx.check("default_off", metrics["default_off"], failure_reason="DEFAULT_OFF_NOT_OBSERVED")
    ctx.check("four_unique_roms", metrics["rom_count"] >= 3, detail=str(metrics["rom_count"]),
              failure_reason="ROM_MAP_INCOMPLETE")
    ctx.save_measurements()
    if (latest.output_stage or "").upper() == "DISABLED":
        ctx.block("OUTPUT_STAGE_COMPILED_OUT: short legal ON and current response cannot be executed")
    handler_actuation_trace(ctx)
    off_frames = ctx.capture(float(params.get("off_after_s", 15)),
                             min_frames=int(params.get("min_frames", 5)),
                             label="post-ON return OFF")
    off_current = max((frame.current_a for frame in off_frames
                       if frame.electrical_valid() and frame.current_a is not None),
                      default=None)
    ctx.measurements["post_on_off_current_max_a"] = off_current
    ctx.check("short_on_executed", ctx.measurements.get("current_mean_a") is not None,
              failure_reason="SHORT_ON_NOT_EXECUTED")
    ctx.check("returned_off", all(not frame.cooling_on for frame in off_frames),
              failure_reason="DID_NOT_RETURN_OFF")
    ctx.check_closed("return_off_current", off_current, None,
                     params.get("off_current_max_a", 0.05))
    ctx.save_measurements()


def handler_run_checklist(ctx: TestContext) -> None:
    params = ctx.definition.params
    device = ctx.require_live_device()
    frame = ctx.latest_frame()
    roms = {role: entry.rom for role, entry in device.snapshot.rom_map.items()}
    checks = {
        "hardware_config_present": bool(frame.hardware_config_id),
        "sensor_identity_present": len(set(roms.values())) >= 3,
        "pzem_range_verified": ctx.store.result("A-W03-04") is not None
        and ctx.store.result("A-W03-04").outcome is Outcome.PASS,
        "door_closed": frame.door_open is False,
        "default_off": frame.is_default_off,
        "storage_writable": ctx.store.root.is_dir(),
    }
    for name, value in checks.items():
        ctx.check(name, value, detail=str(value), failure_reason=f"RUN_PRECHECK_FAILED:{name}")
    for item in params.get("items", []):
        if not ctx.ask_confirm(item):
            ctx.check(f"item:{item}", False, failure_reason=f"RUN_CHECKLIST_ITEM_MISSING: {item}")
    if params.get("ask_post_run"):
        end_reason = ctx.ask_text("Record the run end reason (deadline/STOP/fault/operator).")
        intervention = ctx.ask_text("Record manual interventions or 'none'.")
        anomaly = ctx.ask_text("Record anomalies or 'none'.")
        validity = ctx.ask_choice("Validity candidate for this run:", ["VALID", "INVALID", "UNKNOWN"])
        ctx.measurements.update({"end_reason": end_reason, "manual_intervention": intervention,
                                "anomaly": anomaly, "validity": validity})
        ctx.check("end_reason_recorded", bool(end_reason.strip()), failure_reason="END_REASON_EMPTY")
        ctx.check("intervention_recorded", bool(intervention.strip()),
                  failure_reason="INTERVENTION_NOT_RECORDED")
        ctx.check("anomaly_recorded", bool(anomaly.strip()), failure_reason="ANOMALY_NOT_RECORDED")
    ctx.save_measurements()


def handler_evidence_audit(ctx: TestContext) -> None:
    params = ctx.definition.params
    missing = []
    for test_id in params.get("requirements", []):
        result = ctx.store.result(test_id)
        if result is None:
            missing.append(test_id)
            ctx.check(f"evidence:{test_id}", False, failure_reason=f"EVIDENCE_MISSING {test_id}")
        else:
            ctx.check(f"evidence:{test_id}", True, detail=result.outcome.value)
    for section in params.get("required_sections", []):
        present = any(section.lower() in str(item.get("stored", "")).lower()
                      for result in ctx.store.results().values()
                      for item in result.evidence)
        ctx.check(f"section:{section}", present or not params.get("strict_sections", True),
                  failure_reason=f"EVIDENCE_SECTION_MISSING: {section}")
    ctx.measurements["missing"] = missing
    ctx.require_attachment(params.get("evidence_prompt", "Attach the package index"),
                           minimum=int(params.get("min_files", 1)))
    ctx.save_measurements()


def handler_handover(ctx: TestContext) -> None:
    ctx.source = "OPERATOR_MEASUREMENT"
    params = ctx.definition.params
    member = ctx.ask_text("Name the team member who performed the handover run:")
    followed = ctx.ask_confirm("Did the other member follow the documented runbook end to end?")
    undocumented = ctx.ask_text("List undocumented steps found (write 'none' if none):")
    ctx.measurements.update({"member": member, "followed_runbook": followed,
                             "undocumented_steps": undocumented})
    ctx.check("other_member_present", bool(member.strip()), failure_reason="HANDOVER_MEMBER_MISSING")
    ctx.check("runbook_followed", followed, failure_reason="RUNBOOK_NOT_FOLLOWED")
    ctx.check("undocumented_steps_recorded", bool(undocumented.strip()),
              failure_reason="UNDOCUMENTED_STEPS_NOT_RECORDED")
    ctx.require_attachment(params.get("evidence_prompt", "Attach the signed handover record"),
                           minimum=int(params.get("min_files", 1)))
    ctx.save_measurements()


def handler_evidence_gap_list(ctx: TestContext) -> None:
    ctx.source = "OPERATOR_MEASUREMENT"
    results = ctx.store.results()
    gaps = [result for result in results.values()
            if result.outcome in {Outcome.INCOMPLETE, Outcome.FAIL, Outcome.NOT_RUN}]
    ctx.measurements["gap_count"] = len(gaps)
    ctx.measurements["gaps"] = [
        {"test_id": result.test_id, "outcome": result.outcome.value,
         "reason": result.failure_reason} for result in sorted(gaps, key=lambda item: item.test_id)
    ]
    statement = ctx.ask_text("Record the evidence-gap list with owner and disposition, or 'no gaps'.")
    ctx.notes = statement
    ctx.check("gap_list_recorded", bool(statement.strip()), failure_reason="GAP_LIST_EMPTY")
    ctx.save_measurements()


def handler_rerun_evidence(ctx: TestContext) -> None:
    ctx.source = "OPERATOR_MEASUREMENT"
    params = ctx.definition.params
    allowed = set(params.get("allowed_reasons", [
        "INVALID_PAIR", "MISSING_RECORDING", "SENSOR_OR_LOG_FAILURE", "HARNESS_DEFECT"]))
    choice = ctx.ask_choice("Was an approved rerun executed?",
                            ["Rerun executed", "No rerun needed", "Stop"])
    if choice == "Stop":
        ctx.block("OPERATOR_STOPPED")
    if choice == "No rerun needed":
        ctx.measurements["rerun_executed"] = False
        ctx.check("no_forbidden_rerun", True, detail="no rerun claimed")
    else:
        reason = ctx.ask_choice("Select the predeclared rerun reason:", sorted(allowed))
        original = ctx.ask_text("Reference the retained original invalid attempt:")
        ctx.measurements.update({"rerun_executed": True, "reason": reason, "original": original})
        ctx.check("reason_allowed", reason in allowed, detail=reason,
                  failure_reason="RERUN_REASON_NOT_ALLOWED")
        ctx.check("original_retained", bool(original.strip()),
                  failure_reason="ORIGINAL_ATTEMPT_NOT_RETAINED")
    ctx.require_attachment(params.get("evidence_prompt", "Attach the rerun record"),
                           minimum=int(params.get("min_files", 1)))
    ctx.save_measurements()


def handler_code_audit(ctx: TestContext) -> None:
    """Audit firmware facts that are visible in the live telemetry contract."""
    params = ctx.definition.params
    frames = ctx.capture(float(params.get("duration_s", 60)),
                         min_frames=int(params.get("min_frames", 10)), label="contract audit")
    latest = frames[-1]
    kv = latest.kv
    metrics = {
        "frames": len(frames),
        "producer_health_fields": {name: kv.get(name) for name in
                                   ("health_thermal", "health_bme", "health_door",
                                    "health_power", "health_telemetry", "health_control")},
        "health_unknown": sum(1 for name in ("health_thermal", "health_bme", "health_door",
                                             "health_power")
                              if kv.get(name) in {None, "UNKNOWN"}),
        "power_timeout_bounded": kv.get("power_status") in {"OK", "TIMEOUT", "STALE", "NO_DATA"},
        "telemetry_continues": len(frames) >= int(params.get("min_frames", 10)),
        "has_quality": latest.quality is not None,
    }
    ctx.measurements.update(metrics)
    evaluate_checks(ctx, metrics, params.get("checks", []))
    ctx.save_measurements()


HANDLERS: dict[str, Callable[[TestContext], None]] = {
    "documentary": handler_documentary,
    "numeric": handler_numeric,
    "telemetry": handler_telemetry,
    "pzem_range": handler_pzem_range,
    "pzem_link": handler_pzem_link,
    "command_parser": handler_command_parser,
    "command_expiry": handler_command_expiry,
    "applied_state": handler_applied_state,
    "reset_series": handler_reset_series,
    "run_series": handler_run_series,
    "actuation_trace": handler_actuation_trace,
    "derived": handler_derived,
    "team_evidence": handler_team_evidence,
    "decision": handler_decision,
    "composite": handler_composite,
    "degraded_sensor": handler_degraded_sensor,
    "degraded_pzem": handler_degraded_pzem,
    "soak": handler_soak,
    "hil_smoke": handler_hil_smoke,
    "run_checklist": handler_run_checklist,
    "evidence_audit": handler_evidence_audit,
    "handover": handler_handover,
    "evidence_gap_list": handler_evidence_gap_list,
    "rerun_evidence": handler_rerun_evidence,
    "code_audit": handler_code_audit,
}

from . import evaluators_extra  # noqa: E402  (registers the W01-W24 handlers)

HANDLERS.update(evaluators_extra.HANDLERS)
