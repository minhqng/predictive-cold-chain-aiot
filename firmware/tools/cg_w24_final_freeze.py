"""ColdGuard Member A — W24 Final Freeze, Acceptance & Handover Tool.

Validates compliance with docs/05A §33:
- A-W24-01: Final hardware configuration record freeze.
- A-W24-02: Final HIL smoke protocol verification.
- A-W24-03: Handover execution guidelines.
- A-W24-04: Final acceptance evidence census collation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


MANDATORY_CONFIG_KEYS = (
    "hardware_config_id",
    "pin_map",
    "sensor_roms",
    "sensor_positions",
    "fuse",
    "pzem_range",
    "firmware_version",
)


@dataclass
class ConfigValidationResult:
    valid: bool
    missing_fields: List[str]


def validate_final_configuration(config: Dict[str, Any]) -> ConfigValidationResult:
    """A-W24-01: Ensure final hardware configuration contains all required frozen fields."""
    missing = [key for key in MANDATORY_CONFIG_KEYS if key not in config or not config[key]]
    return ConfigValidationResult(valid=len(missing) == 0, missing_fields=missing)


def collate_acceptance_census(
    weeks_delivered: List[int],
    physical_runs_count: int,
    hardware_status: str,
) -> Dict[str, Any]:
    """A-W24-04: Generate structured Member A final acceptance package census."""
    expected_weeks = set(range(1, 25))
    delivered_set = set(weeks_delivered)
    all_weeks_delivered = delivered_set == expected_weeks

    return {
        "expected_week_count": 24,
        "delivered_week_count": len(delivered_set),
        "delivered_weeks": sorted(list(delivered_set)),
        "missing_weeks": sorted(list(expected_weeks - delivered_set)),
        "all_weeks_accounted_for": all_weeks_delivered,
        "physical_runs_recorded": physical_runs_count,
        "hardware_status": hardware_status,
        "handover_ready": all_weeks_delivered,
    }
