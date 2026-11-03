"""ColdGuard Member A — W17 Shadow Mode Verification and Channel Alignment Tool.

Validates compliance with docs/05A §26:
- A-W17-01: Controller A retains physical authority; Controller B decisions are shadow only.
- A-W17-02: Verifies no predictive physical path (applied == Controller A OR applied == 0 fail-closed).
- A-W17-03: Online/offline channel alignment (raw live channels match B model requirements).
- A-W17-04: Plant anomaly monitoring bound to W08 thermal envelope.

Rule: Never return PASS without synchronized shadow decisions AND authoritative Controller A baseline evidence.
"""

from __future__ import annotations

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

# Bound to W08 envelope: H8-A max rate of change observed was 1.457 K/min ≈ 0.025 K/s
# Any rate above 0.10 K/s (6.0 K/min) in chamber air represents physical anomaly or sensor glitch
ENVELOPE_BOUND_CHAMBER_MAX_RATE_C_PER_SEC = 0.10


@dataclass
class ShadowAuditResult:
    records_evaluated: int
    predictive_leak_detected: bool
    missing_b_channels: List[str]
    anomalies_detected: List[Dict[str, Any]]
    frame_sequence_errors: List[str]
    verdict: str  # PASS, LEAK_DETECTED, CHANNEL_MISMATCH, ANOMALY_DETECTED, SEQUENCE_ERROR, DATA_INSUFFICIENT
    details: Dict[str, Any]


def verify_frame_sequence_and_cadence(frames: List[Dict[str, Any]]) -> List[str]:
    """Verify monotonic sequence and timestamps, and valid non-null payload data."""
    errors = []
    if not frames:
        return ["EMPTY_FRAME_STREAM"]

    prev_seq = None
    prev_uptime = None

    for idx, f in enumerate(frames):
        seq = f.get("seq")
        uptime = f.get("uptime_ms", f.get("elapsed_ms"))

        if seq is not None:
            if prev_seq is not None and seq != prev_seq + 1:
                errors.append(f"FRAME_{idx}: Sequence gap {prev_seq} -> {seq}")
            prev_seq = seq

        if uptime is not None:
            if prev_uptime is not None and uptime <= prev_uptime:
                errors.append(f"FRAME_{idx}: Non-monotonic timestamp {prev_uptime} -> {uptime}")
            prev_uptime = uptime

    return errors


def verify_predictive_isolation(
    applied_duties: List[int],
    shadow_commands: List[int],
    authorized_controller_a_duties: List[int],
) -> Tuple[bool, List[int]]:
    """A-W17-02: Applied duty MUST equal authorized Controller A duty OR 0 (fail-closed).
    
    If applied matches shadow command when shadow command != authorized_a, that is a leak!
    """
    n = len(applied_duties)
    if len(shadow_commands) != n or len(authorized_controller_a_duties) != n:
        raise ValueError("Array length mismatch between applied, shadow, and authorized duties")

    leaking_indices = []
    for idx in range(n):
        applied = applied_duties[idx]
        shadow = shadow_commands[idx]
        auth_a = authorized_controller_a_duties[idx]

        # Valid states: applied == auth_a OR applied == 0 (fail-closed trip)
        if applied != auth_a and applied != 0:
            leaking_indices.append(idx)
        elif applied == shadow and shadow != auth_a and auth_a != 0:
            leaking_indices.append(idx)

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
    """A-W17-04: Detect physical thermal runaway bound to W08 envelope."""
    anomalies = []
    if len(records) < 2:
        return anomalies

    for i in range(1, len(records)):
        prev = records[i - 1]
        curr = records[i]

        t0 = prev.get(time_key, prev.get("uptime_ms"))
        t1 = curr.get(time_key, curr.get("uptime_ms"))
        temp0 = prev.get(temp_key)
        temp1 = curr.get(temp_key)

        if t0 is None or t1 is None or temp0 is None or temp1 is None:
            continue

        dt = (t1 - t0) / 1000.0
        if dt <= 0:
            continue

        rate = abs(temp1 - temp0) / dt
        if rate > ENVELOPE_BOUND_CHAMBER_MAX_RATE_C_PER_SEC:
            anomalies.append({
                "index": i,
                "elapsed_ms": t1,
                "delta_t_sec": dt,
                "rate_c_per_sec": round(rate, 4),
                "threshold_c_per_sec": ENVELOPE_BOUND_CHAMBER_MAX_RATE_C_PER_SEC,
                "reason": "CHAMBER_RATE_EXCEEDS_W08_ENVELOPE",
            })

    return anomalies


def audit_shadow_session(
    telemetry_records: List[Dict[str, Any]],
    shadow_commands: Optional[List[int]] = None,
    authorized_controller_a_duties: Optional[List[int]] = None,
) -> ShadowAuditResult:
    """Full A-W17 audit over a recorded session.
    
    CRITICAL INVARIANT: If shadow_commands OR authorized_controller_a_duties is absent,
    verdict is DATA_INSUFFICIENT, never PASS!
    """
    n = len(telemetry_records)
    if n == 0:
        return ShadowAuditResult(
            records_evaluated=0,
            predictive_leak_detected=False,
            missing_b_channels=list(REQUIRED_B_MODEL_CHANNELS),
            anomalies_detected=[],
            frame_sequence_errors=["EMPTY_STREAM"],
            verdict="DATA_INSUFFICIENT",
            details={"note": "Empty session"},
        )

    # 1. Sequence & Cadence checks
    seq_errors = verify_frame_sequence_and_cadence(telemetry_records)

    # 2. Alignment checks
    missing_channels = verify_b_model_alignment(telemetry_records[0])

    # 3. Check for presence of synchronized shadow commands and controller A baseline
    if shadow_commands is None or authorized_controller_a_duties is None:
        return ShadowAuditResult(
            records_evaluated=n,
            predictive_leak_detected=False,
            missing_b_channels=missing_channels,
            anomalies_detected=[],
            frame_sequence_errors=seq_errors,
            verdict="DATA_INSUFFICIENT",
            details={
                "note": "Synchronized shadow decisions or authoritative Controller A baseline absent. Cannot certify shadow isolation."
            },
        )

    # 4. Check predictive leakage
    applied_duties = [r.get("pwm_duty", r.get("pwm_applied_permille", 0)) for r in telemetry_records]
    leak_detected, leak_indices = verify_predictive_isolation(
        applied_duties, shadow_commands, authorized_controller_a_duties
    )

    # 5. Monitor envelope-bound plant anomalies
    anomalies = monitor_plant_anomalies(telemetry_records)

    # Verdict assignment
    if seq_errors:
        verdict = "SEQUENCE_ERROR"
    elif leak_detected:
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
        frame_sequence_errors=seq_errors,
        verdict=verdict,
        details={
            "leak_count": len(leak_indices),
            "anomaly_count": len(anomalies),
            "missing_channel_count": len(missing_channels),
            "sequence_error_count": len(seq_errors),
        },
    )
