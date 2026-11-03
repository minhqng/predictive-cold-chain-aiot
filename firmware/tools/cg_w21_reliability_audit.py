"""ColdGuard Member A — W21 Reliability Soak & Degraded Fault Tool.

Validates compliance with docs/05A §30:
- A-W21-01: Soak test telemetry audit (read errors, PZEM errors, ESP stability).
- A-W21-02: Single-sensor degraded case (chamber air fallback without T2 hot-side contamination).
- A-W21-03: PZEM unavailable fault response (electrical degradation and safe control).
- A-W21-04: Support SAFE_LOCAL final test protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SoakAuditSummary:
    total_frames: int
    duration_hours: float
    sensor_drop_frames: int
    pzem_error_frames: int
    uptime_resets: int
    verdict: str


def evaluate_soak_telemetry(frames: List[Dict[str, Any]]) -> SoakAuditSummary:
    """A-W21-01: Analyze continuous telemetry stream for soak stability."""
    if not frames:
        return SoakAuditSummary(0, 0.0, 0, 0, 0, "NO_DATA")

    sensor_drops = 0
    pzem_errors = 0
    resets = 0

    prev_uptime = None
    first_uptime = frames[0].get("uptime_ms", 0)
    last_uptime = frames[-1].get("uptime_ms", 0)

    for f in frames:
        up = f.get("uptime_ms")
        if up is not None:
            if prev_uptime is not None and up < prev_uptime:
                resets += 1
            prev_uptime = up

        # Sensor status check
        if f.get("t_inside_status") not in ("OK", "VALID"):
            sensor_drops += 1

        # PZEM status check
        if f.get("current_status") not in ("OK", "VALID"):
            pzem_errors += 1

    dur_hours = max(0.0, (last_uptime - first_uptime) / (1000.0 * 3600.0))
    verdict = "PASS" if resets == 0 and sensor_drops == 0 and pzem_errors == 0 else "DEGRADED"

    return SoakAuditSummary(
        total_frames=len(frames),
        duration_hours=round(dur_hours, 2),
        sensor_drop_frames=sensor_drops,
        pzem_error_frames=pzem_errors,
        uptime_resets=resets,
        verdict=verdict,
    )


def compute_degraded_chamber_air(
    t1_c: Optional[float],
    t3_c: Optional[float],
    t4_c: Optional[float],
    t2_hot_side_c: Optional[float] = None,  # Explicitly forbidden from chamber air
) -> Tuple[Optional[float], str]:
    """A-W21-02: Fallback chamber air computation when one DS18B20 fails."""
    # Collect available chamber air probes (strictly excluding T2)
    valid_temps = [t for t in (t1_c, t3_c, t4_c) if t is not None]
    if not valid_temps:
        return (None, "ALL_CHAMBER_SENSORS_FAILED")

    mean_t = sum(valid_temps) / len(valid_temps)
    if len(valid_temps) == 3:
        status = "FULL_CHAMBER_ARRAY"
    elif len(valid_temps) in (1, 2):
        status = "DEGRADED_CHAMBER_ARRAY"
    else:
        status = "UNKNOWN"

    return (round(mean_t, 2), status)


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
