"""ColdGuard Member A — W22 Rerun Governance & Physical Limitations Tool.

Validates compliance with docs/05A §31:
- Allowed rerun reasons vs forbidden justifications (no p-hacking or cherry-picking).
- A-W22-01: Evidence gap identification.
- A-W22-02: Approved rerun execution rules (mandates retention of original invalid attempts).
- A-W22-03: Physical limitation documentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


ALLOWED_RERUN_REASONS = (
    "INVALID_PAIR_UNDER_PREDECLARED_RULE",
    "MISSING_REQUIRED_RECORDING",
    "KNOWN_SENSOR_LOG_FAILURE",
    "FAILED_DETERMINISTIC_TEST_DUE_HARNESS_DEFECT",
)

FORBIDDEN_JUSTIFICATIONS = (
    "EFFECT_NOT_STATISTICALLY_SIGNIFICANT",
    "RERUN_WORST_PREDICTIVE_RESULT",
    "ADJUST_DOOR_TO_IMPROVE_CONTROLLER_B",
    "CHERRY_PICKING_DESIRED_OUTCOME",
    "OVERWRITE_PREVIOUS_FAILED_ATTEMPT",
    "DELETE_OUTLIER_RUN",
)


@dataclass
class RerunEvaluation:
    approved: bool
    rejection_reason: Optional[str]


def evaluate_rerun_eligibility(
    reason: str,
    original_attempt_id: Optional[str] = None,
    original_attempt_preserved: bool = True,
) -> RerunEvaluation:
    """Validate a requested rerun against strict Doc 03 governance rules.
    
    Rules:
    1. Reason must be in ALLOWED_RERUN_REASONS and not in FORBIDDEN_JUSTIFICATIONS.
    2. Must reference an existing original_attempt_id.
    3. The original invalid attempt must remain preserved (never deleted/overwritten).
    """
    normalized = reason.strip().upper()
    if normalized in FORBIDDEN_JUSTIFICATIONS:
        return RerunEvaluation(
            approved=False,
            rejection_reason=f"FORBIDDEN: {normalized} is an invalid scientific rerun justification",
        )

    if not original_attempt_id:
        return RerunEvaluation(
            approved=False,
            rejection_reason="MISSING_ORIGINAL_ATTEMPT_ID: Reruns must link to an explicit original attempt",
        )

    if not original_attempt_preserved:
        return RerunEvaluation(
            approved=False,
            rejection_reason="FORBIDDEN_PURGE: Original invalid attempt must be preserved in the campaign log",
        )

    if normalized in ALLOWED_RERUN_REASONS:
        return RerunEvaluation(approved=True, rejection_reason=None)

    return RerunEvaluation(
        approved=False,
        rejection_reason=f"UNKNOWN_REASON: '{reason}' is not in approved list ({ALLOWED_RERUN_REASONS})",
    )


def validate_rerun_log_entry(entry: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate that a rerun record properly preserves original attempt history."""
    required = ("rerun_id", "original_attempt_id", "justification", "approved", "prior_attempt_preserved")
    for field in required:
        if field not in entry:
            return (False, f"MISSING_FIELD: {field}")

    if not entry.get("prior_attempt_preserved", False):
        return (False, "DISCARDED_PRIOR_ATTEMPT: prior attempt must be marked preserved")

    return (True, None)


def build_physical_limitation_record(
    scale: str,
    units_tested: int,
    tec_uncertainty: str,
    sensor_limitations: List[str],
    ambient_effects: str,
    pzem_limits: str,
) -> Dict[str, Any]:
    """A-W22-03: Structure physical limitation summary."""
    return {
        "scale": scale,
        "units_tested": units_tested,
        "tec_uncertainty": tec_uncertainty,
        "sensor_limitations": sensor_limitations,
        "ambient_effects": ambient_effects,
        "pzem_limits": pzem_limits,
        "is_complete": True,
    }
