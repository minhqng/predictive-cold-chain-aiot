"""ColdGuard Member A — W19 Campaign Wave 1 Preparation & Invalidation Tool.

Validates compliance with docs/05A §28 and docs/03 §34-36:
- A-W19-01: Run preparation checks (config, initial state, door, PZEM, storage, identity).
- A-W19-02: Physical execution rules (randomized order, invariant physical parameters, pair identity).
- A-W19-03: Invalid attempt logging with structured reason codes and all-attempt preservation.
- A-W19-04: State-based thermal reset between runs (Doc 03 §34/35 criteria: Tmean band, gradient, door, cooling state).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple


INVALIDATION_REASONS = (
    "DOOR_AJAR_AT_START",
    "PZEM_NOT_VALID",
    "INITIAL_TEMP_OUT_OF_BAND",
    "INITIAL_GRADIENT_EXCEEDED",
    "COOLING_STATE_UNKNOWN",
    "COMMUNICATION_DROPOUT",
    "OPERATOR_MANUAL_ABORT",
    "HARDWARE_CONFIG_MISMATCH",
    "SCENARIO_PROTOCOL_MISMATCH",
    "DISTURBANCE_DURATION_MISMATCH",
    "PAIR_TMEAN_MISMATCH",
    "PAIR_GRADIENT_MISMATCH",
    "AMBIENT_NOT_RECORDED",
)


@dataclass
class PrepCheckResult:
    ready: bool
    reasons: List[str]


@dataclass
class ThermalResetResult:
    is_reset: bool
    tmean_diff: float
    gradient_ok: bool
    door_ok: bool
    cooling_state_ok: bool
    sensor_quality_ok: bool
    reasons: List[str]


@dataclass
class PairMatchResult:
    is_valid_match: bool
    delta_tmean_c: float
    delta_gradient: float
    discrepancies: List[str]


@dataclass
class AttemptRecord:
    attempt_seq: int
    session_id: str
    run_id: str
    pair_id: str
    controller: str
    is_valid_attempt: bool
    invalidation_reason: Optional[str]
    details: Dict[str, Any] = field(default_factory=dict)


class CampaignAttemptTracker:
    """A-W19-03 & Doc 03 §34: Preserves every run attempt without silent omission."""

    def __init__(self) -> None:
        self.attempts: List[AttemptRecord] = []

    def record_attempt(
        self,
        session_id: str,
        run_id: str,
        pair_id: str,
        controller: str,
        is_valid_attempt: bool,
        invalidation_reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AttemptRecord:
        if not is_valid_attempt and not invalidation_reason:
            raise ValueError("Invalid attempts must have an invalidation_reason")
        if invalidation_reason and invalidation_reason not in INVALIDATION_REASONS and not invalidation_reason.startswith("CUSTOM_"):
            raise ValueError(f"Unknown invalidation reason: {invalidation_reason}")

        record = AttemptRecord(
            attempt_seq=len(self.attempts) + 1,
            session_id=session_id,
            run_id=run_id,
            pair_id=pair_id,
            controller=controller,
            is_valid_attempt=is_valid_attempt,
            invalidation_reason=invalidation_reason,
            details=details or {},
        )
        self.attempts.append(record)
        return record

    def total_attempts(self) -> int:
        return len(self.attempts)

    def valid_attempts(self) -> int:
        return sum(1 for a in self.attempts if a.is_valid_attempt)

    def invalid_attempts(self) -> int:
        return sum(1 for a in self.attempts if not a.is_valid_attempt)


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


def evaluate_state_based_thermal_reset(
    current_tmean_c: float,
    band_min_c: float,
    band_max_c: float,
    gradient_c_per_min: float,
    max_gradient_c_per_min: float,
    door_closed: bool,
    cooling_state_known: bool,
    sensor_quality_ok: bool,
) -> ThermalResetResult:
    """A-W19-04 & Doc 03 §34: Verify state-based thermal reset criteria.
    
    Runs start based on physical state, not merely elapsed clock time.
    Requires:
    1. Tmean within frozen start band [band_min_c, band_max_c]
    2. Gradient below frozen maximum
    3. Door closed
    4. Cooling state known
    5. Sensor quality valid
    """
    reasons = []
    tmean_diff = 0.0

    if current_tmean_c < band_min_c:
        tmean_diff = band_min_c - current_tmean_c
        reasons.append(f"INITIAL_TEMP_BELOW_BAND: {current_tmean_c:.2f}C < {band_min_c:.2f}C")
    elif current_tmean_c > band_max_c:
        tmean_diff = current_tmean_c - band_max_c
        reasons.append(f"INITIAL_TEMP_ABOVE_BAND: {current_tmean_c:.2f}C > {band_max_c:.2f}C")

    gradient_ok = abs(gradient_c_per_min) <= max_gradient_c_per_min
    if not gradient_ok:
        reasons.append(f"INITIAL_GRADIENT_EXCEEDED: |{gradient_c_per_min:.3f}| > {max_gradient_c_per_min:.3f} C/min")

    if not door_closed:
        reasons.append("DOOR_AJAR_AT_START")
    if not cooling_state_known:
        reasons.append("COOLING_STATE_UNKNOWN")
    if not sensor_quality_ok:
        reasons.append("PZEM_OR_SENSOR_NOT_VALID")

    is_reset = len(reasons) == 0
    return ThermalResetResult(
        is_reset=is_reset,
        tmean_diff=round(tmean_diff, 3),
        gradient_ok=gradient_ok,
        door_ok=door_closed,
        cooling_state_ok=cooling_state_known,
        sensor_quality_ok=sensor_quality_ok,
        reasons=reasons,
    )


def evaluate_pair_matching(
    pair_id: str,
    run_a_id: str,
    run_b_id: str,
    run_a_scenario: str,
    run_b_scenario: str,
    run_a_hardware_config: str,
    run_b_hardware_config: str,
    run_a_disturbance_s: int,
    run_b_disturbance_s: int,
    run_a_initial_tmean_c: float,
    run_b_initial_tmean_c: float,
    run_a_initial_gradient: float,
    run_b_initial_gradient: float,
    delta_tmean_max_c: float,
    delta_gradient_max: float,
    run_a_ambient_c: Optional[float],
    run_b_ambient_c: Optional[float],
) -> PairMatchResult:
    """Doc 03 §35: Validate that an A/B pair meets all pair-matching criteria."""
    discrepancies = []

    if run_a_scenario != run_b_scenario:
        discrepancies.append(f"SCENARIO_MISMATCH: A={run_a_scenario} vs B={run_b_scenario}")

    if run_a_hardware_config != run_b_hardware_config:
        discrepancies.append(f"CONFIG_MISMATCH: A={run_a_hardware_config} vs B={run_b_hardware_config}")

    if run_a_disturbance_s != run_b_disturbance_s:
        discrepancies.append(f"DISTURBANCE_MISMATCH: A={run_a_disturbance_s}s vs B={run_b_disturbance_s}s")

    delta_tmean = abs(run_a_initial_tmean_c - run_b_initial_tmean_c)
    if delta_tmean > delta_tmean_max_c:
        discrepancies.append(f"PAIR_TMEAN_MISMATCH: |A-B|={delta_tmean:.3f}C > tolerance {delta_tmean_max_c:.3f}C")

    delta_grad = abs(run_a_initial_gradient - run_b_initial_gradient)
    if delta_grad > delta_gradient_max:
        discrepancies.append(f"PAIR_GRADIENT_MISMATCH: |A-B|={delta_grad:.3f} > tolerance {delta_gradient_max:.3f}")

    if run_a_ambient_c is None or run_b_ambient_c is None:
        discrepancies.append("AMBIENT_NOT_RECORDED: ambient context must be recorded for both runs")

    return PairMatchResult(
        is_valid_match=len(discrepancies) == 0,
        delta_tmean_c=round(delta_tmean, 3),
        delta_gradient=round(delta_grad, 3),
        discrepancies=discrepancies,
    )


def create_invalid_attempt_record(
    run_id: str,
    controller: str,
    reason_code: str,
    session_id: str = "UNKNOWN_SESSION",
    pair_id: str = "UNPAIRED",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """A-W19-03: Structured log entry for an invalid run attempt."""
    if reason_code not in INVALIDATION_REASONS and not reason_code.startswith("CUSTOM_"):
        raise ValueError(f"Unknown invalidation reason code: {reason_code}")

    return {
        "session_id": session_id,
        "run_id": run_id,
        "pair_id": pair_id,
        "controller": controller,
        "reason_code": reason_code,
        "details": details or {},
        "valid_for_analysis": False,
    }
