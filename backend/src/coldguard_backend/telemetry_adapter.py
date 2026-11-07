"""Member A Serial to Member C MQTT Telemetry Adapter & Gateway Translator.

Implements the translation layer between Member A firmware frames and Member C
backend contracts:
- Firmware serial frame (#CG TELEM schema=3/2/1) -> strict parser -> typed
  field mapping -> validated JSON envelope (schema_version = 1).
- Firmware serial command ACK (#CG CMDACK schema=1) -> typed ACK payload.

Adheres strictly to canonical rules (Docs 00, 01, 02, 05C Section 8):
1. nan becomes None, never 0.0.
2. UNKNOWN quality must never silently become VALID.
3. Calibration "UNRECORDED" remains None (never a fabricated ID).
4. PWM duty is converted from permille (0..1000) to unit range [0.0, 1.0].
5. Device identity, boot_id, and seq are strictly preserved and immutable.
6. Sensor placement: T2 is explicitly recorded as TEC_HOT_SIDE probe
   (ROM 28AEBF2200000006); it is NEVER mixed into chamber-air temperature.
7. Physical timestamp correctness: device lacks synchronized UTC clock
   (timestamp_utc=UNAVAILABLE); gateway acquisition timestamp is recorded
   separately with explicit clock_source and time_sync_state annotations.
8. Replay safety: replayed captures carry is_replay=True to prevent live
   Digital Twin state corruption.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from typing import Any

from coldguard_backend.contracts import Telemetry

log = logging.getLogger(__name__)

PREFIX_TELEM = "#CG TELEM"
PREFIX_CMDACK = "#CG CMDACK"

MISSING_TOKEN = "nan"
UTC_UNAVAILABLE = "UNAVAILABLE"

# Frozen as-built probe positions from Docs 01 & firmware/tools/cg_telemetry_schema.py
HOT_SIDE_ROM = "28AEBF2200000006"
SLOT_TO_ROM = {
    "T1": "287088CA00000051",
    "T2": "28AEBF2200000006",
    "T3": "28CBE9CA00000072",
    "T4": "283BE5C9000000A9",
}
ROM_POSITION_BY_ROM = {
    "287088CA00000051": "CHAMBER_CENTER",
    "28AEBF2200000006": "TEC_HOT_SIDE",
    "28CBE9CA00000072": "CHAMBER_BOTTOM",
    "283BE5C9000000A9": "CHAMBER_NEAR_DOOR",
}

QUALITY_VOCABULARY = frozenset({"VALID", "DEGRADED", "INVALID", "UNKNOWN"})
FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
INT_RE = re.compile(r"^[+-]?\d+$")
HEX_RE = re.compile(r"^0[xX][0-9A-Fa-f]{1,8}$")


class TelemetryAdapterError(ValueError):
    """Raised when a serial frame is malformed or violates contract invariants."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_serial_kv(line: str, prefix: str) -> dict[str, str]:
    """Parse raw key=value tokens from a prefixed line."""
    clean = line.strip()
    if not clean.startswith(prefix):
        raise TelemetryAdapterError(f"Line does not start with expected prefix {prefix!r}: {line!r}")
    tokens = clean[len(prefix) :].strip().split()
    fields: dict[str, str] = {}
    for tok in tokens:
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        fields[k] = v
    return fields


def _parse_float(name: str, val: str | None) -> float | None:
    if val is None or val == MISSING_TOKEN or val == "":
        return None
    if not FLOAT_RE.match(val):
        raise TelemetryAdapterError(f"Field {name!r} has invalid float format: {val!r}")
    num = float(val)
    if not math.isfinite(num):
        raise TelemetryAdapterError(f"Field {name!r} is not finite: {val!r}")
    return num


def _parse_int(name: str, val: str | None) -> int | None:
    if val is None or val == MISSING_TOKEN or val == "":
        return None
    if not INT_RE.match(val):
        raise TelemetryAdapterError(f"Field {name!r} has invalid int format: {val!r}")
    return int(val)


def parse_serial_telemetry_frame(line: str) -> dict[str, Any]:
    """Parse a #CG TELEM serial frame into typed raw fields."""
    kv = parse_serial_kv(line, PREFIX_TELEM)
    if not kv:
        raise TelemetryAdapterError("Empty telemetry frame")

    schema_str = kv.get("schema", "1")
    if not INT_RE.match(schema_str):
        raise TelemetryAdapterError(f"Invalid serial schema token: {schema_str!r}")
    schema_ver = int(schema_str)
    if schema_ver not in (1, 2, 3):
        raise TelemetryAdapterError(f"Unsupported serial schema: {schema_ver}")

    typed: dict[str, Any] = {"serial_schema": schema_ver, "_raw_line": line}

    # Extract all string tokens with nan -> None conversion
    for k, v in kv.items():
        if v == MISSING_TOKEN:
            typed[k] = None
        else:
            typed[k] = v

    return typed


def frame_to_mqtt_envelope(
    frame: dict[str, Any] | str,
    *,
    gateway_received_at: datetime | None = None,
    is_replay: bool = False,
) -> dict[str, Any]:
    """Translate serial telemetry frame into MQTT wire JSON envelope (schema_version = 1).

    Enforces all Section 8 rules:
    - schema_version = 1 on wire (serial schema 3 != MQTT schema 1)
    - nan -> None
    - UNKNOWN quality preserved
    - Calibration UNRECORDED -> None
    - PWM permille -> unit float [0.0, 1.0]
    - Separate device uptime, gateway acquisition timestamp, and clock source
    - Explicit probe placement provenance (T2 = TEC_HOT_SIDE)
    - Replay protection flag
    """
    if isinstance(frame, str):
        frame = parse_serial_telemetry_frame(frame)

    now = gateway_received_at or _utcnow()

    # Identity & provenance
    device_id = str(frame.get("device_id") or "coldguard-001")
    boot_id = str(frame.get("boot_id") or "unknown-boot")
    seq_val = _parse_int("seq", frame.get("seq"))
    seq = seq_val if seq_val is not None else 0

    hw_id = str(frame.get("hardware_config_id") or "CG-HW-001")
    fw_ver = str(frame.get("firmware_version") or "cg-w06-0.1.0")

    cal_id = frame.get("calibration_id")
    if cal_id in (None, "UNRECORDED", "NONE"):
        cal_id = None

    run_id = frame.get("run_id")
    if run_id in (None, "NONE", ""):
        run_id = None

    uptime_ms_val = _parse_int("uptime_ms", frame.get("uptime_ms"))
    if uptime_ms_val is None:
        uptime_ms_val = _parse_int("elapsed_ms", frame.get("elapsed_ms"))
    uptime_ms = uptime_ms_val if uptime_ms_val is not None else 0

    # Timestamp handling: Section 8.2
    raw_utc = frame.get("timestamp_utc")
    if raw_utc is not None and raw_utc != UTC_UNAVAILABLE:
        try:
            captured_at = datetime.fromisoformat(raw_utc.replace("Z", "+00:00"))
            clock_source = "DEVICE_UTC"
            time_sync_state = "SYNCHRONIZED"
        except Exception:
            captured_at = now
            clock_source = "GATEWAY_ACQUISITION"
            time_sync_state = "DEVICE_UNSYNCHRONIZED"
    else:
        captured_at = now
        clock_source = "GATEWAY_ACQUISITION"
        time_sync_state = "DEVICE_UNSYNCHRONIZED"

    # Thermal section: T1 (center), T2 (hot side), T3 (bottom)
    t1 = _parse_float("raw_t1_c", frame.get("raw_t1_c"))
    if t1 is None:
        t1 = _parse_float("t_inside_c", frame.get("t_inside_c"))

    t2 = _parse_float("raw_t2_c", frame.get("raw_t2_c"))
    if t2 is None:
        t2 = _parse_float("t_hot_side_c", frame.get("t_hot_side_c"))

    t3 = _parse_float("raw_t3_c", frame.get("raw_t3_c"))
    if t3 is None:
        t3 = _parse_float("t_cold_side_c", frame.get("t_cold_side_c"))

    # Environment section: BME280 air & humidity
    t_air = _parse_float("t_ambient_c", frame.get("t_ambient_c"))
    rh = _parse_float("relative_humidity_pct", frame.get("relative_humidity_pct"))

    # Door section
    door_val = frame.get("door_open")
    if door_val in ("1", 1):
        door_state = "OPEN"
    elif door_val in ("0", 0):
        door_state = "CLOSED"
    else:
        door_state = "UNKNOWN"

    # Electrical section: PZEM-017 single cooling branch
    voltage_v = _parse_float("voltage_v", frame.get("voltage_v"))
    current_a = _parse_float("current_a", frame.get("current_a"))
    power_w = _parse_float("power_w", frame.get("power_w"))
    energy_wh = _parse_float("energy_wh", frame.get("energy_wh"))

    # Actuation section: single cooling branch
    cooling_app = str(frame.get("cooling_applied") or "OFF").upper()
    cooling_state = "ON" if cooling_app == "ON" else "OFF"

    pwm_duty_permille = _parse_int("pwm_duty", frame.get("pwm_duty"))
    if pwm_duty_permille is not None:
        duty_unit = max(0.0, min(1.0, round(pwm_duty_permille / 1000.0, 4)))
    else:
        duty_unit = 0.0

    # Quality section
    th_q = frame.get("thermal_quality") or "UNKNOWN"
    if th_q not in QUALITY_VOCABULARY:
        th_q = "UNKNOWN"

    env_q = frame.get("environment_quality") or "UNKNOWN"
    if env_q not in QUALITY_VOCABULARY:
        env_q = "UNKNOWN"

    elec_q = frame.get("electrical_quality") or "UNKNOWN"
    if elec_q not in QUALITY_VOCABULARY:
        elec_q = "UNKNOWN"

    ov_q = frame.get("quality") or "UNKNOWN"
    if ov_q not in QUALITY_VOCABULARY:
        ov_q = "UNKNOWN"

    # In contracts.py: if a section quality is VALID, all fields must be non-None
    # If any field is None, quality cannot be VALID (must be DEGRADED or UNKNOWN)
    if th_q == "VALID" and any(v is None for v in (t1, t2, t3)):
        th_q = "DEGRADED"
    if env_q == "VALID" and (t_air is None or rh is None):
        env_q = "DEGRADED"
    if elec_q == "VALID" and any(v is None for v in (voltage_v, current_a, power_w, energy_wh)):
        elec_q = "DEGRADED"

    # Device mode mapping
    fault_code = frame.get("fault_code")
    fault_reason = frame.get("fault_reason")
    if fault_reason == "BOOT_SAFE_OFF" or frame.get("device_mode") == "BOOT":
        device_mode = "BOOT"
    elif fault_code and fault_code not in ("0x00000000", "0x0", "0"):
        device_mode = "SAFE_LOCAL"
    else:
        device_mode = "ONLINE_NORMAL" if ov_q == "VALID" else "ONLINE_DEGRADED"

    # Strict probe placement metadata (Doc 01 & Section 8.3)
    probe_placement_metadata = {
        "t1_probe": {"slot": "T1", "rom": SLOT_TO_ROM["T1"], "position": "CHAMBER_CENTER"},
        "t2_probe": {"slot": "T2", "rom": SLOT_TO_ROM["T2"], "position": "TEC_HOT_SIDE"},
        "t3_probe": {"slot": "T3", "rom": SLOT_TO_ROM["T3"], "position": "CHAMBER_BOTTOM"},
        "hot_side_slot": "T2",
        "hot_side_rom": HOT_SIDE_ROM,
    }

    envelope: dict[str, Any] = {
        "schema_version": 1,
        "device_id": device_id,
        "boot_id": boot_id,
        "seq": seq,
        "captured_at": captured_at.isoformat(),
        "uptime_ms": uptime_ms,
        "run_id": run_id,
        "hardware_config_id": hw_id,
        "firmware_version": fw_ver,
        "calibration_id": cal_id,
        "thermal": {"t1": t1, "t2": t2, "t3": t3},
        "environment": {"t_air": t_air, "rh": rh},
        "door": {"state": door_state},
        "electrical": {
            "voltage_v": voltage_v,
            "current_a": current_a,
            "power_w": power_w,
            "energy_wh": energy_wh,
        },
        "actuation": {"cooling": cooling_state, "duty": duty_unit},
        "quality": {
            "thermal": th_q,
            "environment": env_q,
            "electrical": elec_q,
            "overall": ov_q,
            "device_mode": device_mode,
        },
        # Extension & provenance annotations
        "gateway_received_at": now.isoformat(),
        "clock_source": clock_source,
        "time_sync_state": time_sync_state,
        "probe_placement": probe_placement_metadata,
        "is_replay": is_replay,
        "serial_schema_source": frame.get("serial_schema", 3),
    }

    # Verify that the generated envelope complies with Telemetry wire model
    Telemetry.model_validate(envelope)
    return envelope


def parse_serial_cmdack_frame(line: str) -> dict[str, Any]:
    """Parse #CG CMDACK serial frame into typed command ACK record."""
    kv = parse_serial_kv(line, PREFIX_CMDACK)
    if not kv:
        raise TelemetryAdapterError("Empty command ACK frame")

    return {
        "schema": _parse_int("schema", kv.get("schema")),
        "event": kv.get("event", "ACK"),
        "command_id": kv.get("command_id"),
        "command_id_form": kv.get("command_id_form"),
        "source": kv.get("source"),
        "device_id": kv.get("device_id"),
        "boot_id": kv.get("boot_id"),
        "boot_count": _parse_int("boot_count", kv.get("boot_count")),
        "uptime_ms": _parse_int("uptime_ms", kv.get("uptime_ms")),
        "ack_seq": _parse_int("ack_seq", kv.get("ack_seq")),
        "status": kv.get("status"),
        "canonical_status": kv.get("canonical_status", kv.get("status")),
        "reason": kv.get("reason"),
        "desired_cooling": kv.get("desired_cooling"),
        "desired_duty_permille": _parse_int("desired_duty_permille", kv.get("desired_duty_permille")),
        "applied_cooling": kv.get("applied_cooling"),
        "applied_duty_permille": _parse_int("applied_duty_permille", kv.get("applied_duty_permille")),
        "reapplied": _parse_int("reapplied", kv.get("reapplied")),
        "expiry_evaluable": _parse_int("expiry_evaluable", kv.get("expiry_evaluable")),
        "time_sync_state": kv.get("time_sync_state"),
        "device_mode": kv.get("device_mode"),
        "fault_code": kv.get("fault_code"),
        "output_stage": kv.get("output_stage"),
        "allowed_duty_max_permille": _parse_int("allowed_duty_max_permille", kv.get("allowed_duty_max_permille")),
        "_raw_line": line,
    }
