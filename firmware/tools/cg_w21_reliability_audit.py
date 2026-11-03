"""ColdGuard Member A — W21 Reliability Soak & Degraded Fault Tool.

Validates compliance with docs/05A §30:
- A-W21-01: Soak test telemetry audit (continuous ~1 Hz cadence, read errors, PZEM errors, ESP stability).
- A-W21-02: Single-sensor degraded case (chamber air fallback without T2 hot-side contamination).
- A-W21-03: PZEM unavailable fault response (electrical degradation and safe control).
- A-W21-04: Support SAFE_LOCAL final test protocol.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# Soak protocol specifications (docs/05A §30, docs/03)
NOMINAL_CADENCE_HZ = 1.0
MAX_INTER_FRAME_GAP_MS = 3000
MIN_REQUIRED_SOAK_DURATION_HOURS = 2.0
MIN_CADENCE_THRESHOLD_HZ = 0.85  # At least 85% of expected 1 Hz frames present


@dataclass
class SoakAuditSummary:
    total_frames: int
    duration_hours: float
    effective_cadence_hz: float
    max_observed_gap_ms: int
    cadence_gap_violations: int
    sensor_drop_frames: int
    pzem_error_frames: int
    uptime_resets: int
    verdict: str
    reasons: List[str]


def evaluate_soak_telemetry(
    frames: List[Dict[str, Any]],
    min_duration_hours: float = MIN_REQUIRED_SOAK_DURATION_HOURS,
) -> SoakAuditSummary:
    """A-W21-01: Analyze continuous telemetry stream for soak stability.
    
    Rejects sparse/fake fixtures that span hours without continuous ~1 Hz frames.
    """
    if not frames:
        return SoakAuditSummary(
            total_frames=0,
            duration_hours=0.0,
            effective_cadence_hz=0.0,
            max_observed_gap_ms=0,
            cadence_gap_violations=0,
            sensor_drop_frames=0,
            pzem_error_frames=0,
            uptime_resets=0,
            verdict="NO_DATA",
            reasons=["Empty telemetry frame list"],
        )

    sensor_drops = 0
    pzem_errors = 0
    resets = 0
    gap_violations = 0
    max_gap_ms = 0
    reasons = []

    prev_uptime: Optional[int] = None
    first_uptime = frames[0].get("uptime_ms", 0)
    last_uptime = frames[-1].get("uptime_ms", 0)

    for i, f in enumerate(frames):
        up = f.get("uptime_ms")
        if up is not None:
            if prev_uptime is not None:
                if up < prev_uptime:
                    resets += 1
                    reasons.append(f"UPTIME_RESET at frame {i}: {up}ms < {prev_uptime}ms")
                else:
                    gap = up - prev_uptime
                    if gap > max_gap_ms:
                        max_gap_ms = gap
                    if gap > MAX_INTER_FRAME_GAP_MS:
                        gap_violations += 1
            prev_uptime = up

        # Sensor status checks: check t_inside or individual sensors
        t_inside_status = f.get("t_inside_status")
        t1_status = f.get("t1_status")
        t3_status = f.get("t3_status")
        t4_status = f.get("t4_status")
        
        has_sensor_err = False
        if t_inside_status is not None and t_inside_status not in ("OK", "VALID"):
            has_sensor_err = True
        if any(s is not None and s not in ("OK", "VALID") for s in (t1_status, t3_status, t4_status)):
            has_sensor_err = True
        if has_sensor_err:
            sensor_drops += 1

        # PZEM status checks
        pzem_status = f.get("current_status") or f.get("pzem_status")
        if pzem_status is not None and pzem_status not in ("OK", "VALID"):
            pzem_errors += 1

    dur_seconds = max(0.0, (last_uptime - first_uptime) / 1000.0)
    dur_hours = dur_seconds / 3600.0
    effective_cadence = (len(frames) / dur_seconds) if dur_seconds > 0 else 0.0

    # 1. Cadence & coverage check: reject sparse fixtures
    if dur_seconds > 0 and effective_cadence < MIN_CADENCE_THRESHOLD_HZ:
        reasons.append(
            f"INSUFFICIENT_CADENCE: {len(frames)} frames over {dur_seconds:.1f}s ({effective_cadence:.4f} Hz) "
            f"< minimum {MIN_CADENCE_THRESHOLD_HZ} Hz (sparse fixtures strictly rejected)"
        )

    # 2. Minimum duration check
    if dur_hours < min_duration_hours:
        reasons.append(f"INSUFFICIENT_DURATION: {dur_hours:.2f}h < required {min_duration_hours:.1f}h")

    # 3. Excessive inter-frame gap violations
    if gap_violations > 0:
        reasons.append(f"INTER_FRAME_GAPS: {gap_violations} gaps exceeded {MAX_INTER_FRAME_GAP_MS}ms (max gap {max_gap_ms}ms)")

    # 4. Resets
    if resets > 0:
        reasons.append(f"UNEXPECTED_REBOOTS: {resets} uptime resets detected")

    # 5. Determine verdict
    if dur_hours >= min_duration_hours and effective_cadence >= MIN_CADENCE_THRESHOLD_HZ and resets == 0 and gap_violations == 0 and sensor_drops == 0 and pzem_errors == 0:
        verdict = "PASS"
    elif any("INSUFFICIENT_CADENCE" in r or "INSUFFICIENT_DURATION" in r for r in reasons):
        verdict = "FAIL_CADENCE_OR_DURATION"
    elif resets > 0:
        verdict = "FAIL_REBOOT_DETECTED"
    else:
        verdict = "DEGRADED"

    return SoakAuditSummary(
        total_frames=len(frames),
        duration_hours=round(dur_hours, 2),
        effective_cadence_hz=round(effective_cadence, 3),
        max_observed_gap_ms=max_gap_ms,
        cadence_gap_violations=gap_violations,
        sensor_drop_frames=sensor_drops,
        pzem_error_frames=pzem_errors,
        uptime_resets=resets,
        verdict=verdict,
        reasons=reasons,
    )


def compute_degraded_chamber_air(
    t1_c: Optional[float],
    t3_c: Optional[float],
    t4_c: Optional[float],
    t2_hot_side_c: Optional[float] = None,  # Strictly excluded from chamber air
    bme_temp_c: Optional[float] = None,
) -> Tuple[Optional[float], str]:
    """A-W21-02: Fallback chamber air computation when one DS18B20 fails.
    
    T2 (TEC heatsink hot side) is NEVER included in chamber air calculations.
    """
    # Filter valid DS18B20 chamber air probes
    valid_temps = []
    for t in (t1_c, t3_c, t4_c):
        if t is not None and not math.isnan(t) and not math.isinf(t) and -40.0 <= t <= 85.0:
            valid_temps.append(t)

    if len(valid_temps) == 3:
        return (round(sum(valid_temps) / 3.0, 3), "FULL_CHAMBER_ARRAY")
    elif len(valid_temps) in (1, 2):
        return (round(sum(valid_temps) / len(valid_temps), 3), "DEGRADED_CHAMBER_ARRAY")
    elif len(valid_temps) == 0:
        # Check auxiliary BME280 backup
        if bme_temp_c is not None and not math.isnan(bme_temp_c) and -40.0 <= bme_temp_c <= 85.0:
            return (round(bme_temp_c, 3), "AUXILIARY_BME_BACKUP")
        return (None, "ALL_CHAMBER_SENSORS_FAILED")

    return (None, "UNKNOWN")


def verify_pzem_fault_behavior(
    pzem_available: bool,
    electrical_quality: str,
    output_stage_enabled: bool,
) -> Tuple[bool, List[str]]:
    """A-W21-03: Verify fail-safe electrical behavior on PZEM communication drop."""
    violations = []
    if not pzem_available:
        if electrical_quality in ("OK", "GOOD"):
            violations.append("ELECTRICAL_QUALITY_NOT_DEGRADED_ON_PZEM_DROP")
        if output_stage_enabled:
            violations.append("OUTPUT_STAGE_REMAINED_ENABLED_ON_PZEM_DROP")

    return (len(violations) == 0, violations)
