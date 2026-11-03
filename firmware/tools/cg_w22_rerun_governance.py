"""ColdGuard Member A — W22 Rerun Governance & Physical Limitations Tool.

Validates compliance with docs/05A §31:
- Allowed rerun reasons vs forbidden justifications (no p-hacking or cherry-picking).
- A-W22-01: Evidence gap identification.
- A-W22-02: Approved rerun execution rules.
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
)


@dataclass
class RerunEvaluation:
    approved: bool
    rejection_reason: Optional[str]


def evaluate_rerun_eligibility(reason: str) -> RerunEvaluation:
    """Validate a requested rerun against strict Doc 03 governance rules."""
    normalized = reason.strip().upper()
    if normalized in FORBIDDEN_JUSTIFICATIONS:
        return RerunEvaluation(
            approved=False,
            rejection_reason=f"FORBIDDEN: {normalized} is an invalid scientific rerun justification",
        )
    if normalized in ALLOWED_RERUN_REASONS:
        return RerunEvaluation(approved=True, rejection_reason=None)

    return RerunEvaluation(
        approved=False,
        rejection_reason=f"UNKNOWN_REASON: '{reason}' is not in approved list ({ALLOWED_RERUN_REASONS})",
    )


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
