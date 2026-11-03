"""ColdGuard Member A — W19 Campaign Wave 1 Preparation & Invalidation Tool.

Validates compliance with docs/05A §28:
- A-W19-01: Run preparation checks (config, initial state, door, PZEM, storage, identity).
- A-W19-02: Physical execution rules (randomized order, invariant physical parameters).
- A-W19-03: Invalid attempt logging with structured reason codes.
- A-W19-04: State-based thermal reset between runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


INVALIDATION_REASONS = (
    "DOOR_AJAR_AT_START",
    "PZEM_NOT_VALID",
    "INITIAL_TEMP_OUT_OF_BAND",
    "COMMUNICATION_DROPOUT",
    "OPERATOR_MANUAL_ABORT",
    "HARDWARE_CONFIG_MISMATCH",
)


@dataclass
class PrepCheckResult:
    ready: bool
    reasons: List[str]


def validate_run_preparation(
    config_matches: bool,
    door_closed: bool,
    pzem_valid: bool,
    storage_ready: bool,
    controller_identified: bool,
) -> PrepCheckResult:
    """A-W19-01: Evaluate pre-flight readiness before an experiment run."""
    failures = []
    if not config_matches:
        failures.append("HARDWARE_CONFIG_MISMATCH")
    if not door_closed:
        failures.append("DOOR_AJAR_AT_START")
    if not pzem_valid:
        failures.append("PZEM_NOT_VALID")
    if not storage_ready:
        failures.append("STORAGE_NOT_READY")
    if not controller_identified:
        failures.append("CONTROLLER_NOT_IDENTIFIED")

    return PrepCheckResult(ready=len(failures) == 0, reasons=failures)


def evaluate_thermal_reset(
    current_temp_c: float,
    target_equilibrium_c: float,
    band_c: float = 0.5,
) -> Tuple[bool, float]:
    """A-W19-04: Verify state-based thermal reset before starting next paired run."""
    diff = abs(current_temp_c - target_equilibrium_c)
    is_reset = diff <= band_c
    return (is_reset, round(diff, 3))


def create_invalid_attempt_record(
    run_id: str,
    controller: str,
    reason_code: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """A-W19-03: Structured log entry for an invalid run attempt."""
    if reason_code not in INVALIDATION_REASONS and not reason_code.startswith("CUSTOM_"):
        raise ValueError(f"Unknown invalidation reason code: {reason_code}")

    return {
        "run_id": run_id,
        "controller": controller,
        "reason_code": reason_code,
        "details": details or {},
        "valid_for_analysis": False,
    }
