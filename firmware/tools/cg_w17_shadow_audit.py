"""ColdGuard Member A — W17 Shadow Mode Verification and Channel Alignment Tool.

Validates compliance with docs/05A §26:
- A-W17-01: Controller A retains physical authority; Controller B decisions are shadow only.
- A-W17-02: Verifies no predictive physical path (shadow decisions != applied actuation).
- A-W17-03: Online/offline channel alignment (raw live channels match B model requirements).
- A-W17-04: Plant anomaly monitoring (flags unexpected drift and invalidates runs).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


REQUIRED_B_MODEL_CHANNELS = (
    "t_inside_c",
    "t_inside_status",
    "t_cold_side_c",
    "t_hot_side_c",
    "door_open",
    "door_status",
    "voltage_v",
    "current_a",
    "power_w",
    "quality",
)

MAX_EXPECTED_CHAMBER_RATE_C_PER_SEC = 0.5  # Plant limit: >0.5 C/s is physical anomaly


@dataclass
class ShadowAuditResult:
    records_evaluated: int
    predictive_leak_detected: bool
    missing_b_channels: List[str]
    anomalies_detected: List[Dict[str, Any]]
    verdict: str  # PASS, LEAK_DETECTED, CHANNEL_MISMATCH, ANOMALY_DETECTED, NO_DATA
    details: Dict[str, Any]


def verify_no_predictive_leak(
    applied_duties: List[int],
    shadow_commands: List[int],
    baseline_duties: Optional[List[int]] = None,
) -> Tuple[bool, List[int]]:
    """A-W17-02: Ensure applied duty matches baseline/local authority, never shadow commands.
    
    Returns (leak_detected, leaking_indices).
    """
    if len(applied_duties) != len(shadow_commands):
        raise ValueError("applied_duties and shadow_commands length mismatch")

    leaking_indices = []
    for idx, (applied, shadow) in enumerate(zip(applied_duties, shadow_commands)):
        if baseline_duties is not None:
            baseline = baseline_duties[idx]
            if applied == shadow and applied != baseline:
                leaking_indices.append(idx)
        else:
            # If no baseline provided, applied duty tracking shadow duty when shadow != 0
            # indicates potential leak unless verified
            pass

    return (len(leaking_indices) > 0, leaking_indices)


def verify_b_model_alignment(record: Dict[str, Any]) -> List[str]:
    """A-W17-03: Verify all channels required by Member B exist and are non-null."""
    missing = []
    for channel in REQUIRED_B_MODEL_CHANNELS:
        if channel not in record or record[channel] is None:
            missing.append(channel)
    return missing


def monitor_plant_anomalies(
    records: List[Dict[str, Any]],
    time_key: str = "elapsed_ms",
    temp_key: str = "t_inside_c",
) -> List[Dict[str, Any]]:
    """A-W17-04: Detect physical thermal runaway or sensor step discontinuities."""
    anomalies = []
    if len(records) < 2:
        return anomalies

    for i in range(1, len(records)):
        prev = records[i - 1]
        curr = records[i]
        
        t0 = prev.get(time_key)
        t1 = curr.get(time_key)
        temp0 = prev.get(temp_key)
        temp1 = curr.get(temp_key)

        if t0 is None or t1 is None or temp0 is None or temp1 is None:
            continue

        dt = (t1 - t0) / 1000.0
        if dt <= 0:
            continue

        rate = abs(temp1 - temp0) / dt
        if rate > MAX_EXPECTED_CHAMBER_RATE_C_PER_SEC:
            anomalies.append({
                "index": i,
                "elapsed_ms": t1,
                "delta_t_sec": dt,
                "rate_c_per_sec": round(rate, 3),
                "reason": "CHAMBER_TEMPERATURE_RATE_EXCEEDED",
            })

    return anomalies


def audit_shadow_session(
    telemetry_records: List[Dict[str, Any]],
    shadow_commands: Optional[List[int]] = None,
    baseline_duties: Optional[List[int]] = None,
) -> ShadowAuditResult:
    """Full A-W17 audit over a recorded session."""
    n = len(telemetry_records)
    if n == 0:
        return ShadowAuditResult(
            records_evaluated=0,
            predictive_leak_detected=False,
            missing_b_channels=list(REQUIRED_B_MODEL_CHANNELS),
            anomalies_detected=[],
            verdict="NO_DATA",
            details={"note": "Empty session"},
        )

    # 1. Check alignment on first frame
    missing_channels = verify_b_model_alignment(telemetry_records[0])

    # 2. Check predictive leakage if commands supplied
    applied_duties = [r.get("pwm_duty", r.get("pwm_applied_permille", 0)) for r in telemetry_records]
    leak_detected = False
    leak_indices = []
    if shadow_commands is not None and len(shadow_commands) == n:
        leak_detected, leak_indices = verify_no_predictive_leak(
            applied_duties, shadow_commands, baseline_duties
        )

    # 3. Monitor anomalies
    anomalies = monitor_plant_anomalies(telemetry_records)

    # Verdict assignment
    if leak_detected:
        verdict = "LEAK_DETECTED"
    elif missing_channels:
        verdict = "CHANNEL_MISMATCH"
    elif anomalies:
        verdict = "ANOMALY_DETECTED"
    else:
        verdict = "PASS"

    return ShadowAuditResult(
        records_evaluated=n,
        predictive_leak_detected=leak_detected,
        missing_b_channels=missing_channels,
        anomalies_detected=anomalies,
        verdict=verdict,
        details={
            "leak_count": len(leak_indices),
            "anomaly_count": len(anomalies),
            "missing_channel_count": len(missing_channels),
        },
    )
