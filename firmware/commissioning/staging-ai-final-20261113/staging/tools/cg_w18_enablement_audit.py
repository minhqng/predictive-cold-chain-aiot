"""ColdGuard Member A — W18 Controller B Physical Enablement & Safety Tool.

Validates compliance with docs/05A §27:
- A-W18-01: Pre-run safety audit (fuse, fan, terminals, sensors, PZEM, default output, G4/B/D prerequisites).
- A-W18-02: Controlled predictive dry runs.
- A-W18-03: Electrical verification bounds (reconciled with 9.99A observed peak in H8).
- A-W18-04: Thermal verification bounds (reconciled with provisional 55.0°C cutoff).
- A-W18-05: Abort criteria (instant fail-closed trip recommendation on limit violation or invalid data).
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Tuple


# Reconciled operating bounds based on physical evidence (not invented approvals):
# H8-C box run observed peak current was 9.99 A. 15 A blade fuse rating.
# Provisional limit set to 10.0 A for host trip recommendation.
PROVISIONAL_MAX_CURRENT_A = 10.0

# Provisional hot-side ceiling established in W08 / W16 (55.0 °C).
# Note: Firmware cg_tec_limits.c marks CG_LIMIT_HOT_SIDE_MAX_C as UNRESOLVED
# (HOT_SIDE_LIMIT_NOT_ESTABLISHED). This is a provisional engineering limit, NOT a formal Gate A approval.
PROVISIONAL_MAX_HOT_SIDE_TEMP_C = 55.0

# Maximum inter-frame communication gap allowed before trip recommendation
MAX_COMMUNICATION_TIMEOUT_MS = 3000


@dataclass
class PreRunAuditStatus:
    fuse_verified: bool
    fan_operational: bool
    terminals_secured: bool
    sensors_online: bool
    pzem_responsive: bool
    output_stage_default_off: bool
    g4_gate_passed: bool
    controller_b_model_frozen: bool
    controller_d_policy_frozen: bool
    is_ready_for_dry_run: bool
    is_ready_for_physical_enablement: bool
    unresolved_items: List[str]


def evaluate_pre_run_safety_audit(checks: Dict[str, bool]) -> PreRunAuditStatus:
    """A-W18-01: Evaluate pre-run physical and prerequisite safety checklist.
    
    Dry-run requires all physical bench checks.
    Physical enablement requires BOTH physical bench checks AND cross-team prerequisites (G4, B model, D policy).
    """
    bench_required = (
        "fuse_verified",
        "fan_operational",
        "terminals_secured",
        "sensors_online",
        "pzem_responsive",
        "output_stage_default_off",
    )
    prereq_required = (
        "g4_gate_passed",
        "controller_b_model_frozen",
        "controller_d_policy_frozen",
    )
    
    unresolved = []
    for req in bench_required:
        if not checks.get(req, False):
            unresolved.append(req)
    for req in prereq_required:
        if not checks.get(req, False):
            unresolved.append(req)

    bench_ok = all(checks.get(req, False) for req in bench_required)
    prereqs_ok = all(checks.get(req, False) for req in prereq_required)

    return PreRunAuditStatus(
        fuse_verified=checks.get("fuse_verified", False),
        fan_operational=checks.get("fan_operational", False),
        terminals_secured=checks.get("terminals_secured", False),
        sensors_online=checks.get("sensors_online", False),
        pzem_responsive=checks.get("pzem_responsive", False),
        output_stage_default_off=checks.get("output_stage_default_off", False),
        g4_gate_passed=checks.get("g4_gate_passed", False),
        controller_b_model_frozen=checks.get("controller_b_model_frozen", False),
        controller_d_policy_frozen=checks.get("controller_d_policy_frozen", False),
        is_ready_for_dry_run=bench_ok,
        is_ready_for_physical_enablement=bench_ok and prereqs_ok,
        unresolved_items=unresolved,
    )


def check_abort_criteria(
    current_a: Optional[float],
    hot_side_temp_c: Optional[float],
    last_comm_gap_ms: Optional[int],
) -> Tuple[bool, Optional[str], str]:
    """A-W18-05: Verify real-time operating metrics against safety trip limits.
    
    Fails closed immediately on missing, NaN, negative, or invalid data.
    
    Returns:
        (trip_triggered: bool, trip_reason: Optional[str], enforcement: str)
        enforcement is always 'HOST_TRIP_RECOMMENDATION' (host recommends PWM=0;
        firmware fail-closed hardware shutdown enforces OFF on-device).
    """
    enforcement = "HOST_TRIP_RECOMMENDATION"

    # Fail closed on missing / None
    if current_a is None or hot_side_temp_c is None or last_comm_gap_ms is None:
        missing = []
        if current_a is None:
            missing.append("current_a")
        if hot_side_temp_c is None:
            missing.append("hot_side_temp_c")
        if last_comm_gap_ms is None:
            missing.append("last_comm_gap_ms")
        return (True, f"INVALID_MEASUREMENT: missing fields {missing}", enforcement)

    # Fail closed on NaN or Inf
    if math.isnan(current_a) or math.isinf(current_a):
        return (True, "INVALID_MEASUREMENT: current_a is NaN or Inf", enforcement)
    if math.isnan(hot_side_temp_c) or math.isinf(hot_side_temp_c):
        return (True, "INVALID_MEASUREMENT: hot_side_temp_c is NaN or Inf", enforcement)

    # Fail closed on negative current or impossible physical values
    if current_a < 0.0:
        return (True, f"INVALID_MEASUREMENT: negative current {current_a:.2f}A", enforcement)
    if hot_side_temp_c < -40.0 or hot_side_temp_c > 125.0:
        return (True, f"INVALID_MEASUREMENT: hot_side_temp_c {hot_side_temp_c:.1f}C out of physical sensor range", enforcement)
    if last_comm_gap_ms < 0:
        return (True, f"INVALID_MEASUREMENT: negative comm gap {last_comm_gap_ms}ms", enforcement)

    # Check bounds
    if current_a > PROVISIONAL_MAX_CURRENT_A:
        return (True, f"OVERCURRENT_TRIP: {current_a:.2f}A > provisional {PROVISIONAL_MAX_CURRENT_A}A", enforcement)
    if hot_side_temp_c > PROVISIONAL_MAX_HOT_SIDE_TEMP_C:
        return (True, f"OVERTEMP_TRIP: {hot_side_temp_c:.1f}C > provisional {PROVISIONAL_MAX_HOT_SIDE_TEMP_C}C", enforcement)
    if last_comm_gap_ms > MAX_COMMUNICATION_TIMEOUT_MS:
        return (True, f"TIMEOUT_TRIP: {last_comm_gap_ms}ms > {MAX_COMMUNICATION_TIMEOUT_MS}ms", enforcement)

    return (False, None, enforcement)
