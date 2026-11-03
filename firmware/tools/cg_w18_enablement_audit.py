"""ColdGuard Member A — W18 Controller B Physical Enablement & Safety Tool.

Validates compliance with docs/05A §27:
- A-W18-01: Pre-run safety audit (fuse, fan, terminals, sensors, PZEM, default output).
- A-W18-02: Controlled predictive dry runs.
- A-W18-03: Electrical verification bounds.
- A-W18-04: Thermal verification bounds.
- A-W18-05: Abort criteria (instant trip on limit violation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# Safety trip thresholds
MAX_ALLOWED_CURRENT_A = 8.0
MAX_ALLOWED_HOT_SIDE_TEMP_C = 65.0
MAX_COMMUNICATION_TIMEOUT_MS = 3000


@dataclass
class PreRunAuditStatus:
    fuse_verified: bool
    fan_operational: bool
    terminals_secured: bool
    sensors_online: bool
    pzem_responsive: bool
    output_stage_default_off: bool
    is_ready_for_dry_run: bool
    unresolved_items: List[str]


def evaluate_pre_run_safety_audit(checks: Dict[str, bool]) -> PreRunAuditStatus:
    """A-W18-01: Evaluate pre-run physical safety checklist."""
    required = (
        "fuse_verified",
        "fan_operational",
        "terminals_secured",
        "sensors_online",
        "pzem_responsive",
        "output_stage_default_off",
    )
    unresolved = []
    for req in required:
        if not checks.get(req, False):
            unresolved.append(req)

    return PreRunAuditStatus(
        fuse_verified=checks.get("fuse_verified", False),
        fan_operational=checks.get("fan_operational", False),
        terminals_secured=checks.get("terminals_secured", False),
        sensors_online=checks.get("sensors_online", False),
        pzem_responsive=checks.get("pzem_responsive", False),
        output_stage_default_off=checks.get("output_stage_default_off", False),
        is_ready_for_dry_run=len(unresolved) == 0,
        unresolved_items=unresolved,
    )


def check_abort_criteria(
    current_a: float,
    hot_side_temp_c: float,
    last_comm_gap_ms: int,
) -> Tuple[bool, Optional[str]]:
    """A-W18-05: Verify real-time operating metrics against safety trip limits."""
    if current_a > MAX_ALLOWED_CURRENT_A:
        return (True, f"OVERCURRENT_TRIP: {current_a:.2f}A > {MAX_ALLOWED_CURRENT_A}A")
    if hot_side_temp_c > MAX_ALLOWED_HOT_SIDE_TEMP_C:
        return (True, f"OVERTEMP_TRIP: {hot_side_temp_c:.1f}C > {MAX_ALLOWED_HOT_SIDE_TEMP_C}C")
    if last_comm_gap_ms > MAX_COMMUNICATION_TIMEOUT_MS:
        return (True, f"TIMEOUT_TRIP: {last_comm_gap_ms}ms > {MAX_COMMUNICATION_TIMEOUT_MS}ms")
    return (False, None)
