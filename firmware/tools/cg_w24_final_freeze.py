"""ColdGuard Member A — W24 Final Freeze, Acceptance & Handover Tool.

Validates compliance with docs/05A §33 and evidence/A/as-built-pinmap-2026-10-27.md:
- A-W24-01: Final hardware configuration record freeze (Map v2 pins, ROMs, fuse posture, shunt).
- A-W24-02: Final HIL smoke protocol verification (actuation forbidden while gates open).
- A-W24-03: Handover execution guidelines (software readiness distinguished from physical acceptance).
- A-W24-04: Final acceptance evidence census collation (honest disclosure of open H-GATEs).
"""

from __future__ import annotations

import hashlib
import json
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
"""Only authentic device captures count toward physical acceptance. Host fixtures,
simulator output and derived tables are excluded, so an artefact copied from a test
cannot lift a census to PHYSICALLY_ACCEPTED."""

EVIDENCE_ROOT = "evidence"

WEEK_DOSSIER_DIR_FALLBACK = {w: f"{EVIDENCE_ROOT}/A/W{w:02d}" for w in range(1, 25)}
WEEK_DOSSIER_DIR_FALLBACK[23] = f"{EVIDENCE_ROOT}/A/RC"
"""Where each week's dossier lives. W23 delivers the release-candidate package under
evidence/A/RC/, so a week number is not the same thing as a directory name."""

SAFE_HARDWARE_POSTURES = {
    "FAIL_CLOSED_FROZEN",
    "DE_ENERGIZED_SAFE_POSTURE_PSU_OFF_FUSE_REMOVED",
}
"""Postures that state the bench is safe to leave unattended. Any other value is
treated as an unresolved hazard rather than as a free-text label."""

EVIDENCE_CLASSES = (
    "COLD_BOOT_IDENTITY",
    "COOLING_SESSION",
    "S1_REPEATABILITY_RUN",
    "ELECTRICAL_ENVELOPE_SAMPLE",
    "SHADOW_SESSION",
)
"""What a capture is able to prove. A cold boot does not evidence a cooling run,
and neither one evidences an electrical envelope, so a class is mandatory."""

EVIDENCE_CLASS_BY_NAME = (
    ("boot-default-off", "COLD_BOOT_IDENTITY"),
    ("tec-cooling-response-600s", "COOLING_SESSION"),
    ("cooling-step-runs", "S1_REPEATABILITY_RUN"),
    ("envelope-by-duty", "ELECTRICAL_ENVELOPE_SAMPLE"),
    ("duty-zero-current-frames", "ELECTRICAL_ENVELOPE_SAMPLE"),
    ("shadow", "SHADOW_SESSION"),
)
"""Classification is read from the delivered artifact names, not invented per call."""

REQUIREMENT_EVIDENCE_SPEC = {
    "A-W03-04": {"evidence_class": "COLD_BOOT_IDENTITY", "min_independent_runs": 1},
    "A-W04-03": {"evidence_class": "COOLING_SESSION", "min_independent_runs": 1},
    "A-W07-02": {"evidence_class": "S1_REPEATABILITY_RUN", "min_independent_runs": 3},
    "A-W08-01": {"evidence_class": "ELECTRICAL_ENVELOPE_SAMPLE", "min_independent_runs": 1},
    "A-W17-01": {"evidence_class": "SHADOW_SESSION", "min_independent_runs": 1},
}
"""Deliberately partial. Requirements with no entry report EVIDENCE_CLASS_UNSPECIFIED
rather than borrowing a neighbouring class, so extending coverage is an explicit,
reviewable edit instead of a silent pass."""

STATUS_SATISFIED = "SATISFIED_BY_VERIFIED_EVIDENCE"
STATUS_INSUFFICIENT = "NEEDS_OPERATOR_EVIDENCE"
STATUS_UNSPECIFIED = "EVIDENCE_CLASS_UNSPECIFIED"
STATUS_PROVENANCE_BACKFILL = "NEEDS_PROVENANCE_BACKFILL"

EVIDENCE_REQUIRED_FIELDS = (
    "run_id",
    "device_id",
    "boot_id",
    "source_type",
    "artifact_path",
    "sha256",
    "hardware_config_id",
    "evidence_class",
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
    runs_by_class: Dict[str, int] = field(default_factory=dict)
    verified_records: List[Dict[str, Any]] = field(default_factory=list)
    refusals: List[str] = field(default_factory=list)


def _pinned_digests(root: Path, artifact: Path) -> List[str]:
    """Digests that any SHA256SUMS.txt at or above `artifact` records for it.

    Citing an arbitrary readable file is not evidence. A capture counts only if a
    dossier pin file lists its path and digest, which is how the W01-W24 dossiers
    already record their own artifacts.
    """
    digests: List[str] = []
    directory = artifact.parent
    root_r = root.resolve()
    while True:
        sums = directory / "SHA256SUMS.txt"
        if sums.is_file():
            try:
                text = sums.read_bytes().decode("utf-8", errors="replace")
            except OSError:
                text = ""
            for line in text.splitlines():
                line = line.strip()
                if not line or len(line.split(None, 1)) < 2:
                    continue
                digest, rel = line.split(None, 1)
                target = directory / rel.strip().replace("\\", "/")
                try:
                    if target.is_file() and target.resolve() == artifact.resolve():
                        digests.append(digest.lower())
                except OSError:
                    continue
        if directory == root_r or directory.parent == directory:
            break
        directory = directory.parent
    return digests


def verify_physical_evidence(
    physical_evidence: Optional[List[Dict[str, Any]]],
    repo_root: Any,
    expected_hardware_config_id: Optional[str],
) -> EvidenceVerification:
    """Bind each claimed run to a pinned capture whose own bytes record its identity.

    A count alone is not evidence, and neither is the mere existence of some file:
    a record must name a pinned artifact whose bytes carry the claimed boot id and
    hardware configuration. Runs sharing a device boot id are segments of one power
    cycle, so they count once.
    """
    result = EvidenceVerification()
    if not physical_evidence:
        result.refusals.append("PHYSICAL_EVIDENCE_ABSENT: no per-run evidence records supplied")
        return result
    if repo_root is None:
        result.refusals.append("PHYSICAL_EVIDENCE_ABSENT: repo_root required to verify artifacts")
        return result
    if not expected_hardware_config_id:
        result.refusals.append(
            "PHYSICAL_EVIDENCE_ABSENT: expected_hardware_config_id required, so a stale "
            "configuration cannot be accepted by omission"
        )
        return result

    root = Path(repo_root).resolve()
    seen_boots: Dict[str, str] = {}
    seen_digests: Dict[str, str] = {}
    for index, record in enumerate(physical_evidence):
        if not isinstance(record, dict):
            result.refusals.append(f"EVIDENCE_FIELD_MISSING: record {index} is not a mapping")
            continue
        missing = [k for k in EVIDENCE_REQUIRED_FIELDS if record.get(k) in (None, "")]
        if missing:
            result.refusals.append(
                f"EVIDENCE_FIELD_MISSING: record {index} lacks {','.join(sorted(missing))}"
            )
            continue
        if record["evidence_class"] not in EVIDENCE_CLASSES:
            result.refusals.append(
                f"EVIDENCE_CLASS_UNKNOWN: record {index} declares "
                f"{record['evidence_class']!r}, which is not a recognised evidence class"
            )
            continue
        if record["source_type"] not in PHYSICAL_SOURCE_TYPES:
            result.refusals.append(
                f"EVIDENCE_SOURCE_SYNTHETIC: record {index} source_type="
                f"{record['source_type']!r} cannot support physical acceptance"
            )
            continue
        if record["hardware_config_id"] != expected_hardware_config_id:
            result.refusals.append(
                f"EVIDENCE_HARDWARE_CONFIG_MISMATCH: record {index} is "
                f"{record['hardware_config_id']!r}, expected {expected_hardware_config_id!r}"
            )
            continue

        rel = str(record["artifact_path"]).replace("\\", "/")
        if rel.startswith("/") or ".." in Path(rel).parts:
            result.refusals.append(
                f"EVIDENCE_ARTIFACT_UNTRUSTED: record {index} cites {rel!r}, which is not a "
                "repository-relative path"
            )
            continue
        if not rel.startswith(f"{EVIDENCE_ROOT}/"):
            result.refusals.append(
                f"EVIDENCE_ARTIFACT_UNTRUSTED: record {index} cites {rel!r} outside {EVIDENCE_ROOT}/"
            )
            continue

        artifact = root / rel
        if not artifact.is_file() or root not in artifact.resolve().parents:
            result.refusals.append(
                f"EVIDENCE_ARTIFACT_MISSING: record {index} cites {rel!r}, which does not exist "
                "inside this tree"
            )
            continue
        raw = artifact.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest.lower() != str(record["sha256"]).lower():
            result.refusals.append(
                f"EVIDENCE_HASH_MISMATCH: record {index} {rel!r} recorded {record['sha256']}, "
                f"bytes are {digest}"
            )
            continue
        pinned = _pinned_digests(root, artifact)
        if not pinned:
            result.refusals.append(
                f"EVIDENCE_ARTIFACT_UNPINNED: record {index} {rel!r} is not listed in any "
                "SHA256SUMS.txt, so it is not a declared dossier artifact"
            )
            continue
        if digest.lower() not in pinned:
            result.refusals.append(
                f"EVIDENCE_ARTIFACT_UNPINNED: record {index} {rel!r} digest {digest} does not "
                "match any pinned value"
            )
            continue
        # The identity has to exist at the source, not only in the claim about it.
        for field_name in ("boot_id", "hardware_config_id"):
            if str(record[field_name]).encode() not in raw:
                result.refusals.append(
                    f"EVIDENCE_IDENTITY_NOT_IN_ARTIFACT: record {index} claims {field_name}="
                    f"{record[field_name]!r}, which does not appear in {rel!r}"
                )
                break
        else:
            if digest.lower() in seen_digests:
                result.refusals.append(
                    f"EVIDENCE_RUN_NOT_INDEPENDENT: record {index} duplicates the bytes already "
                    f"counted for record {seen_digests[digest.lower()]}"
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
            seen_digests[digest.lower()] = str(index)
            result.counted_boot_identities.append(boot_key)
            cls = record["evidence_class"]
            result.runs_by_class[cls] = result.runs_by_class.get(cls, 0) + 1
            result.verified_records.append(dict(record))

    result.independent_run_count = len(result.counted_boot_identities)
    return result


def classify_artifact(name: str) -> Optional[str]:
    for token, cls in EVIDENCE_CLASS_BY_NAME:
        if token in name.lower():
            return cls
    return None


def _first_column_value(text: str, column: str) -> Optional[str]:
    """Read the first non-empty value of a CSV column, if the file has one."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    header = [h.strip() for h in lines[0].split(",")]
    if column not in header:
        return None
    idx = header.index(column)
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) > idx and parts[idx].strip():
            return parts[idx].strip()
    return None


def collect_pinned_evidence(repo_root: Any) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    """Build evidence records from the delivered dossiers themselves.

    Only artifacts that are pinned by a SHA256SUMS.txt, carry a recognised class name
    and record their own boot_id and hardware_config_id columns become runs. Anything
    else is reported as skipped instead of being silently counted.
    """
    root = Path(repo_root)
    records: List[Dict[str, Any]] = []
    skipped: List[str] = []
    unbound: List[Dict[str, Any]] = []
    for dossier in sorted(WEEK_DOSSIER_DIR_FALLBACK.values()):
        directory = root / dossier
        if not directory.is_dir():
            continue
        sums = directory / "SHA256SUMS.txt"
        if not sums.is_file():
            skipped.append(f"{dossier}: no SHA256SUMS.txt")
            continue
        pinned: Dict[str, str] = {}
        for line in sums.read_bytes().decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and len(line.split(None, 1)) == 2:
                digest, rel = line.split(None, 1)
                pinned[rel.strip().replace("\\", "/")] = digest
        for rel, digest in sorted(pinned.items()):
            target = directory / rel
            if not target.is_file() or target.suffix.lower() not in (".csv", ".jsonl"):
                continue
            cls = classify_artifact(target.name)
            if cls is None:
                continue
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest.lower():
                skipped.append(f"{dossier}/{rel}: pinned digest does not match bytes")
                continue
            text = target.read_bytes().decode("utf-8", errors="replace")
            # Older captures identify themselves with a free-text session banner rather
            # than a boot_id column; requiring the newer column would reject authentic
            # evidence for the shape of its format instead of its provenance.
            boot = _first_column_value(text, "boot_id") or _first_column_value(text, "session")
            conf = _first_column_value(text, "hardware_config_id")
            if not boot or not conf:
                detail = "no boot_id/session column" if not boot else "no hardware_config_id column"
                unbound.append({
                    "artifact_path": f"{dossier}/{rel}",
                    "evidence_class": cls,
                    "reason": f"{detail}; run identity cannot be bound to this artifact",
                })
                continue
            records.append({
                "run_id": f"{Path(rel).name}:{boot}",
                "device_id": _first_column_value(text, "device_id") or "UNRECORDED",
                "boot_id": boot,
                "source_type": "RAW_DEVICE_CAPTURE",
                "artifact_path": f"{dossier}/{rel}",
                "sha256": digest.lower(),
                "hardware_config_id": conf,
                "evidence_class": cls,
            })
    return records, skipped, unbound


def evaluate_requirement_evidence(
    verification: EvidenceVerification,
    spec: Dict[str, Dict[str, Any]],
    unbound: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """A requirement is satisfied only by runs of its own evidence class."""
    out: Dict[str, Dict[str, Any]] = {}
    for requirement in sorted(spec):
        rule = spec[requirement]
        cls = rule["evidence_class"]
        needed = int(rule.get("min_independent_runs", 1))
        available = verification.runs_by_class.get(cls, 0)
        if cls not in EVIDENCE_CLASSES:
            status, reason = STATUS_UNSPECIFIED, "class is not recognised"
        elif available >= needed:
            status, reason = STATUS_SATISFIED, f"{available} verified {cls} run(s)"
        else:
            # Captures of the right class may exist without a bindable run identity.
            # That is a provenance bookkeeping gap, not a missing measurement, and must
            # not be reported as though the operator still has to go to the bench.
            related = [u for u in (unbound or []) if u.get("evidence_class") == cls]
            if related:
                status = STATUS_PROVENANCE_BACKFILL
                reason = (f"{available} verified, needs {needed}; {len(related)} artifact(s) of "
                          f"class {cls} exist but lack a bindable run identity")
            else:
                status, reason = STATUS_INSUFFICIENT, (
                    f"{available} verified {cls} run(s), needs {needed}"
                )
        out[requirement] = {
            "evidence_class": cls,
            "required_independent_runs": needed,
            "verified_independent_runs": available,
            "status": status,
            "detail": reason,
        }
    return out


def generate_acceptance_census(repo_root: Any) -> str:
    """Deterministic census built from the repository, never from typed counters.

    No wall-clock value is embedded, so the same tree always yields byte-identical
    output and the digest can be pinned in the dossier.
    """
    records, skipped, unbound = collect_pinned_evidence(repo_root)
    weeks_present = sorted(
        f"W{week:02d}"
        for week, rel in WEEK_DOSSIER_DIR_FALLBACK.items()
        if (Path(repo_root) / rel).is_dir()
    )
    verification = EvidenceVerification()
    requirement_status: Dict[str, Dict[str, Any]] = {}
    config_ids = sorted({r["hardware_config_id"] for r in records})
    expected_config = config_ids[0] if len(config_ids) == 1 else None
    if len(config_ids) > 1:
        # Disagreement about which configuration produced the captures is not resolved
        # by picking one; the census is left refused until it does.
        expected_config = None

    census = collate_acceptance_census(
        weeks_delivered=[int(w[1:]) for w in weeks_present],
        physical_runs_count=len(records),
        hardware_status="FAIL_CLOSED_FROZEN",
        open_hardware_gates=["H-GATE-OPEN-PENDING-OPERATOR-QUALIFICATION"],
        physical_evidence=records,
        repo_root=repo_root,
        expected_hardware_config_id=expected_config,
    )
    recheck = verify_physical_evidence(records, repo_root, expected_config)
    if len(config_ids) > 1:
        recheck.refusals.insert(
            0,
            "EVIDENCE_HARDWARE_CONFIG_AMBIGUOUS: captures disagree on "
            + ",".join(config_ids),
        )
        census["evidence_refusals"] = recheck.refusals
    requirement_status = evaluate_requirement_evidence(recheck, REQUIREMENT_EVIDENCE_SPEC, unbound)
    census["generated_by"] = "firmware/tools/cg_w24_final_freeze.generate_acceptance_census"
    census["weeks_with_dossier"] = weeks_present
    census["evidence_skipped"] = skipped
    census["evidence_unbound"] = unbound
    census["runs_by_class"] = recheck.runs_by_class
    census["requirement_status"] = requirement_status
    census["requirements_unspecified"] = sorted(
        rid for rid, val in requirement_status.items() if val["status"] == STATUS_UNSPECIFIED
    )
    return json.dumps(census, indent=2, sort_keys=True) + "\n"


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
    gate_register_absent = open_hardware_gates is None
    gates = () if gate_register_absent else tuple(open_hardware_gates)

    verification = verify_physical_evidence(
        physical_evidence, repo_root, expected_hardware_config_id
    )

    posture_safe = hardware_status in SAFE_HARDWARE_POSTURES
    if not posture_safe:
        verification.refusals.append(
            f"HARDWARE_POSTURE_UNSAFE: {hardware_status!r} is not a recognised fail-closed "
            f"posture; physical acceptance cannot be granted while the bench state is unknown"
        )

    # A claimed week should have a dossier behind it, not only a number in a list.
    weeks_without_dossier: List[str] = []
    if repo_root is not None:
        for week in sorted(delivered_set & expected_weeks):
            rel = WEEK_DOSSIER_DIR_FALLBACK.get(week, f"{EVIDENCE_ROOT}/A/W{week:02d}")
            if not (Path(repo_root) / rel).is_dir():
                weeks_without_dossier.append(f"W{week:02d}")

    software_ready = all_weeks_delivered
    physical_ready = (
        software_ready
        and not gate_register_absent
        and len(gates) == 0
        and posture_safe
        and not weeks_without_dossier
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
        "weeks_without_dossier": weeks_without_dossier,
        "physical_runs_claimed": physical_runs_count,
        "physical_runs_verified": verification.independent_run_count,
        "verified_boot_identities": verification.counted_boot_identities,
        "evidence_refusals": verification.refusals,
        "gate_register_supplied": not gate_register_absent,
        "hardware_status": hardware_status,
        "hardware_posture_safe": posture_safe,
        "open_hardware_gates": [] if gate_register_absent else list(gates),
        # None, not 0: an unknown register must not read downstream as "no gates".
        "open_hardware_gates_count": None if gate_register_absent else len(gates),
        "software_contract_ready": software_ready,
        # Member A cannot certify a cross-team round trip; that claim needs B/C/D evidence.
        "system_integration_verified": False,
        "system_integration_note": SYSTEM_INTEGRATION_NOT_ASSERTABLE,
        "physical_acceptance_ready": physical_ready,
        "acceptance_verdict": acceptance_verdict,
        "handover_verdict": handover_verdict,
    }
