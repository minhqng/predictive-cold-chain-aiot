"""ColdGuard Member A — W24 Final Freeze, Acceptance & Handover Tool.

Validates compliance with docs/05A §33 and evidence/A/as-built-pinmap-2026-10-27.md:
- A-W24-01: Final hardware configuration record freeze (Map v2 pins, ROMs, fuse posture, shunt).
- A-W24-02: Final HIL smoke protocol verification (actuation forbidden while gates open).
- A-W24-03: Handover execution guidelines (software readiness distinguished from physical acceptance).
- A-W24-04: Final acceptance evidence census collation (honest disclosure of open H-GATEs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


EXPECTED_PIN_MAP_V2 = {
    "one_wire_gpio": 33,
    "bme280_sda_gpio": 21,
    "bme280_scl_gpio": 34,
    "door_reed_gpio": 35,
    "pzem_tx_gpio": 36,
    "pzem_rx_gpio": 37,
    "ibt2_rpwm_gpio": 5,
    "ibt2_r_en_gpio": 6,
    "ibt2_l_en_gpio": 10,
}

EXPECTED_SENSOR_ROMS = {
    "t1": "287088CA00000051",
    "t2": "28AEBF2200000006",
    "t3": "28CBE9CA00000072",
    "t4": "283BE5C9000000A9",
}

EXPECTED_SENSOR_ROLES = {
    "t1": "CHAMBER_CENTER",
    "t2": "TEC_HOT_SIDE",
    "t3": "CHAMBER_BOTTOM",
    "t4": "NEAR_DOOR",
}

EXPECTED_FUSE_TYPE = "15A blade fuse"
EXPECTED_SHUNT_TYPE = "FL-2 0.5 50A/75mV"


@dataclass
class ConfigValidationResult:
    valid: bool
    errors: List[str]
    evidence_class: str


def validate_final_configuration(config: Dict[str, Any]) -> ConfigValidationResult:
    """A-W24-01: Deep semantic validation of final hardware configuration.
    
    Verifies actual GPIO numbers against As-Built Map v2, frozen ROMs,
    sensor role assignments, fuse rating/posture, and shunt specification.
    """
    errors = []

    # Pin Map v2 checks
    pins = config.get("pin_map_v2") or config.get("pin_map")
    if not isinstance(pins, dict):
        errors.append("MISSING_PIN_MAP: pin_map_v2 missing or invalid")
    else:
        for pin_name, expected_val in EXPECTED_PIN_MAP_V2.items():
            actual_val = pins.get(pin_name)
            if actual_val != expected_val:
                errors.append(f"PIN_MISMATCH: {pin_name} expected {expected_val}, got {actual_val}")

    # Sensor ROMs checks
    roms = config.get("sensor_roms")
    if not isinstance(roms, dict):
        errors.append("MISSING_SENSOR_ROMS: sensor_roms missing or invalid")
    else:
        for slot, expected_rom in EXPECTED_SENSOR_ROMS.items():
            actual_rom = roms.get(slot)
            if actual_rom != expected_rom:
                errors.append(f"ROM_MISMATCH: {slot} expected {expected_rom}, got {actual_rom}")

    # Sensor Roles checks
    positions = config.get("sensor_positions")
    if not isinstance(positions, dict):
        errors.append("MISSING_SENSOR_POSITIONS: sensor_positions missing")
    else:
        for slot, expected_role in EXPECTED_SENSOR_ROLES.items():
            actual_role = positions.get(slot)
            if actual_role != expected_role:
                errors.append(f"ROLE_MISMATCH: {slot} expected {expected_role}, got {actual_role}")

    # Power and Protection checks
    power = config.get("power_and_protection", {})
    fuse_type = power.get("fuse_type") or config.get("fuse")
    if EXPECTED_FUSE_TYPE not in str(fuse_type):
        errors.append(f"FUSE_MISMATCH: expected '{EXPECTED_FUSE_TYPE}', got '{fuse_type}'")

    if "REMOVED" not in str(power.get("fuse_slot_3_posture", "")):
        errors.append("FUSE_POSTURE_VIOLATION: Slot 3 fuse must be documented as REMOVED (safe posture)")

    shunt_info = power.get("pzem_shunt") or config.get("pzem_range", "")
    if "50A" not in str(shunt_info) and "75mV" not in str(shunt_info):
        errors.append(f"SHUNT_MISMATCH: expected 50A/75mV external shunt, got '{shunt_info}'")

    evidence_class = config.get("evidence_class", "UNCLASSIFIED")

    return ConfigValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        evidence_class=evidence_class,
    )


def collate_acceptance_census(
    weeks_delivered: List[int],
    physical_runs_count: int,
    hardware_status: str,
    open_hardware_gates: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """A-W24-04: Structured Member A final acceptance package census.
    
    CRITICAL DISTINCTION:
    - 24/24 weeks delivered guarantees SOFTWARE CONTRACT READINESS.
    - Physical acceptance is strictly BLOCKED while open hardware gates remain.
    """
    expected_weeks = set(range(1, 25))
    delivered_set = set(weeks_delivered)
    all_weeks_delivered = (delivered_set == expected_weeks)
    gates = open_hardware_gates or []

    # Handover ready for software integration vs physical acceptance
    software_ready = all_weeks_delivered
    physical_ready = all_weeks_delivered and len(gates) == 0 and physical_runs_count >= 3

    return {
        "expected_week_count": 24,
        "delivered_week_count": len(delivered_set),
        "delivered_weeks": sorted(list(delivered_set)),
        "missing_weeks": sorted(list(expected_weeks - delivered_set)),
        "all_weeks_accounted_for": all_weeks_delivered,
        "physical_runs_recorded": physical_runs_count,
        "hardware_status": hardware_status,
        "open_hardware_gates": gates,
        "open_hardware_gates_count": len(gates),
        "software_contract_ready": software_ready,
        "physical_acceptance_ready": physical_ready,
        "handover_verdict": "READY_FOR_SOFTWARE_INTEGRATION_PHYSICAL_ACCEPTANCE_BLOCKED" if software_ready and not physical_ready else ("FULLY_ACCEPTED" if physical_ready else "INCOMPLETE"),
    }
