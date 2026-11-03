"""ColdGuard Member A — W24 Final Freeze, Acceptance & Handover Tool.

Validates compliance with docs/05A §33 and evidence/A/as-built-pinmap-2026-10-27.md:
- A-W24-01: Final hardware configuration record freeze (Map v2 pins, ROMs, fuse posture, shunt).
- A-W24-02: Final HIL smoke protocol verification (actuation forbidden while gates open).
- A-W24-03: Handover execution guidelines (software readiness distinguished from physical acceptance).
- A-W24-04: Final acceptance evidence census collation (honest disclosure of open H-GATEs).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
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


REQUIRED_INDEPENDENT_RUNS = 3
"""Minimum independent physical runs. Carried over from the previous census rule
(physical_runs_count >= 3) so the threshold is not silently re-invented here."""

PHYSICAL_SOURCE_TYPES = {"RAW_DEVICE_CAPTURE"}

EVIDENCE_REQUIRED_FIELDS = (
    "run_id",
    "device_id",
    "boot_id",
    "source_type",
    "artifact_path",
    "sha256",
    "hardware_config_id",
)

VERDICT_SOFTWARE_CONTRACT_READY = "SOFTWARE_CONTRACT_READY"
VERDICT_SYSTEM_INTEGRATION_VERIFIED = "SYSTEM_INTEGRATION_VERIFIED"
VERDICT_PHYSICAL_ACCEPTANCE_PENDING = "PHYSICAL_ACCEPTANCE_PENDING"
VERDICT_PHYSICALLY_ACCEPTED = "PHYSICALLY_ACCEPTED"
VERDICT_DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
VERDICT_INCOMPLETE = "INCOMPLETE"

SYSTEM_INTEGRATION_NOT_ASSERTABLE = "NOT_VERIFIABLE_BY_MEMBER_A_ALONE"


@dataclass
class EvidenceVerification:
    """Result of binding claimed physical runs to artifacts that exist on disk."""

    independent_run_count: int = 0
    counted_boot_identities: List[str] = field(default_factory=list)
    refusals: List[str] = field(default_factory=list)


def verify_physical_evidence(
    physical_evidence: Optional[List[Dict[str, Any]]],
    repo_root: Any,
    expected_hardware_config_id: Optional[str],
) -> EvidenceVerification:
    """Bind each claimed run to a real file whose bytes match its recorded hash.

    A count alone is not evidence: without this step a caller could reach
    PHYSICALLY_ACCEPTED by typing a number. Runs sharing a device boot id are
    segments of one power cycle, so they count once.
    """
    result = EvidenceVerification()
    if not physical_evidence:
        result.refusals.append("PHYSICAL_EVIDENCE_ABSENT: no per-run evidence records supplied")
        return result
    if repo_root is None:
        result.refusals.append("PHYSICAL_EVIDENCE_ABSENT: repo_root required to verify artifacts")
        return result

    root = Path(repo_root)
    seen_boots: Dict[str, str] = {}
    for index, record in enumerate(physical_evidence):
        if not isinstance(record, dict):
            result.refusals.append(f"EVIDENCE_FIELD_MISSING: record {index} is not a mapping")
            continue
        missing = [k for k in EVIDENCE_REQUIRED_FIELDS if not record.get(k)]
        if missing:
            result.refusals.append(
                f"EVIDENCE_FIELD_MISSING: record {index} lacks {','.join(sorted(missing))}"
            )
            continue
        if record["source_type"] not in PHYSICAL_SOURCE_TYPES:
            result.refusals.append(
                f"EVIDENCE_SOURCE_SYNTHETIC: record {index} source_type="
                f"{record['source_type']!r} cannot support physical acceptance"
            )
            continue
        if expected_hardware_config_id and record["hardware_config_id"] != expected_hardware_config_id:
            result.refusals.append(
                f"EVIDENCE_HARDWARE_CONFIG_MISMATCH: record {index} is "
                f"{record['hardware_config_id']!r}, expected {expected_hardware_config_id!r}"
            )
            continue

        artifact = root / record["artifact_path"]
        if not artifact.is_file():
            result.refusals.append(
                f"EVIDENCE_ARTIFACT_MISSING: record {index} cites {record['artifact_path']!r}, "
                "which does not exist in this tree"
            )
            continue
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if digest.lower() != str(record["sha256"]).lower():
            result.refusals.append(
                f"EVIDENCE_HASH_MISMATCH: record {index} {record['artifact_path']!r} "
                f"recorded {record['sha256']}, bytes are {digest}"
            )
            continue

        boot_key = f"{record['device_id']}|{record['boot_id']}"
        if boot_key in seen_boots:
            result.refusals.append(
                f"EVIDENCE_RUN_NOT_INDEPENDENT: record {index} shares boot {boot_key} with "
                f"record {seen_boots[boot_key]}"
            )
            continue
        seen_boots[boot_key] = str(index)
        result.counted_boot_identities.append(boot_key)

    result.independent_run_count = len(result.counted_boot_identities)
    return result


def collate_acceptance_census(
    weeks_delivered: List[int],
    physical_runs_count: int,
    hardware_status: str,
    open_hardware_gates: Optional[List[str]] = None,
    physical_evidence: Optional[List[Dict[str, Any]]] = None,
    repo_root: Any = None,
    expected_hardware_config_id: Optional[str] = None,
) -> Dict[str, Any]:
    """A-W24-04: Structured Member A final acceptance package census.

    CRITICAL DISTINCTION:
    - 24/24 weeks delivered guarantees SOFTWARE CONTRACT READINESS only.
    - Physical acceptance needs open gates explicitly closed AND independently
      verified captures, so a caller-supplied count can never reach it alone.
    - An absent gate register means "unknown", never "no gates".
    """
    expected_weeks = set(range(1, 25))
    delivered_set = set(weeks_delivered)
    unexpected_weeks = sorted(delivered_set - expected_weeks)
    all_weeks_delivered = (delivered_set == expected_weeks)
    gates = [] if open_hardware_gates == [] else open_hardware_gates
    gate_register_absent = open_hardware_gates is None

    verification = verify_physical_evidence(
        physical_evidence, repo_root, expected_hardware_config_id
    )

    software_ready = all_weeks_delivered
    physical_ready = (
        software_ready
        and not gate_register_absent
        and len(gates) == 0
        and verification.independent_run_count >= REQUIRED_INDEPENDENT_RUNS
    )

    if not software_ready:
        acceptance_verdict = VERDICT_INCOMPLETE
    elif physical_ready:
        acceptance_verdict = VERDICT_PHYSICALLY_ACCEPTED
    elif gate_register_absent or (verification.refusals and not verification.counted_boot_identities):
        acceptance_verdict = VERDICT_DATA_INSUFFICIENT
    else:
        acceptance_verdict = VERDICT_PHYSICAL_ACCEPTANCE_PENDING

    if software_ready and not physical_ready:
        handover_verdict = "READY_FOR_SOFTWARE_INTEGRATION_PHYSICAL_ACCEPTANCE_BLOCKED"
    elif physical_ready:
        handover_verdict = "FULLY_ACCEPTED"
    else:
        handover_verdict = VERDICT_INCOMPLETE

    return {
        "expected_week_count": 24,
        "delivered_week_count": len(delivered_set),
        "delivered_weeks": sorted(list(delivered_set)),
        "missing_weeks": sorted(list(expected_weeks - delivered_set)),
        "unexpected_week_ids": unexpected_weeks,
        "all_weeks_accounted_for": all_weeks_delivered,
        "physical_runs_claimed": physical_runs_count,
        "physical_runs_verified": verification.independent_run_count,
        "verified_boot_identities": verification.counted_boot_identities,
        "evidence_refusals": verification.refusals,
        "gate_register_supplied": not gate_register_absent,
        "hardware_status": hardware_status,
        "open_hardware_gates": [] if gates is None else list(gates),
        "open_hardware_gates_count": 0 if gates is None else len(gates),
        "software_contract_ready": software_ready,
        # Member A cannot certify a cross-team round trip; the claim needs B/C/D evidence.
        "system_integration_verified": SYSTEM_INTEGRATION_NOT_ASSERTABLE,
        "physical_acceptance_ready": physical_ready,
        "acceptance_verdict": acceptance_verdict,
        "handover_verdict": handover_verdict,
    }
