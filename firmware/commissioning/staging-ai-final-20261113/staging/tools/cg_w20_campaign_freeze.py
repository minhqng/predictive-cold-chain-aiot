"""ColdGuard Member A — W20 Campaign Wave 2 & Data Freeze Tool.

Validates compliance with docs/05A §29 and docs/03:
- A-W20-01: Invariant protocol continuity.
- A-W20-02: Valid-pair completion rule validation (requires true matched pairs, not just equal counts).
- A-W20-03: Campaign close physical audit (sensor identity, drift, damage).
- A-W20-04: Freeze physical campaign data and generate signed manifest with digest/signoff distinction.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


VALID_CONTROLLERS = {"CONTROLLER_A", "CONTROLLER_B"}


@dataclass
class PairBalanceSummary:
    target_pairs: int
    completed_pairs: int
    matched_pairs: List[str]
    unmatched_a_runs: List[str]
    unmatched_b_runs: List[str]
    invalid_runs_count: int
    is_balanced: bool
    quota_met: bool
    validation_errors: List[str]


def verify_campaign_pair_balance(
    runs: List[Dict[str, Any]],
    target_pairs: int = 1,
) -> PairBalanceSummary:
    """A-W20-02: Ensure valid paired completion by true matched pair_id, not just equal A/B counts."""
    pairs_a: Dict[str, str] = {}  # pair_id -> run_id
    pairs_b: Dict[str, str] = {}  # pair_id -> run_id
    invalid_count = 0
    errors = []

    for idx, r in enumerate(runs):
        run_id = r.get("run_id", f"run_{idx}")
        pair_id = r.get("pair_id")
        controller = r.get("controller", "").upper()
        valid = r.get("valid_for_analysis", True)

        if not valid:
            invalid_count += 1
            continue

        if controller not in VALID_CONTROLLERS:
            errors.append(f"INVALID_CONTROLLER: run {run_id} has invalid controller '{controller}'")
            continue

        if not pair_id:
            errors.append(f"MISSING_PAIR_ID: run {run_id} has no pair_id")
            continue

        if controller == "CONTROLLER_A":
            if pair_id in pairs_a:
                errors.append(f"DUPLICATE_CONTROLLER_A: pair {pair_id} already has run {pairs_a[pair_id]}")
            pairs_a[pair_id] = run_id
        elif controller == "CONTROLLER_B":
            if pair_id in pairs_b:
                errors.append(f"DUPLICATE_CONTROLLER_B: pair {pair_id} already has run {pairs_b[pair_id]}")
            pairs_b[pair_id] = run_id

    # Compute intersection and discrepancies
    common_pairs = sorted(list(set(pairs_a.keys()) & set(pairs_b.keys())))
    unmatched_a = sorted([f"{pid}:{rid}" for pid, rid in pairs_a.items() if pid not in pairs_b])
    unmatched_b = sorted([f"{pid}:{rid}" for pid, rid in pairs_b.items() if pid not in pairs_a])

    is_balanced = len(common_pairs) > 0 and len(unmatched_a) == 0 and len(unmatched_b) == 0 and len(errors) == 0
    quota_met = is_balanced and len(common_pairs) >= target_pairs

    return PairBalanceSummary(
        target_pairs=target_pairs,
        completed_pairs=len(common_pairs),
        matched_pairs=common_pairs,
        unmatched_a_runs=unmatched_a,
        unmatched_b_runs=unmatched_b,
        invalid_runs_count=invalid_count,
        is_balanced=is_balanced,
        quota_met=quota_met,
        validation_errors=errors,
    )


def audit_post_campaign_hardware(
    expected_roms: List[str],
    observed_roms: List[str],
    terminal_tightness_ok: bool,
    fan_ok: bool,
) -> Tuple[bool, List[str]]:
    """A-W20-03: Post-campaign physical audit verifying no hardware drift."""
    defects = []
    if set(expected_roms) != set(observed_roms):
        defects.append("SENSOR_ROM_MISMATCH_OR_DROP")
    if not terminal_tightness_ok:
        defects.append("TERMINAL_LOOSE")
    if not fan_ok:
        defects.append("FAN_MALFUNCTION")

    return (len(defects) == 0, defects)


def verify_dataset_file_integrity(
    file_hashes: Dict[str, str],
    base_dir: Optional[Path] = None,
) -> Tuple[bool, List[str]]:
    """Verify actual existence and sha256 of dataset files on disk."""
    if base_dir is None:
        return (True, [])
    errors = []
    for rel_path, expected_hash in file_hashes.items():
        fpath = base_dir / rel_path
        if not fpath.is_file():
            errors.append(f"MISSING_FILE: {rel_path} does not exist in {base_dir}")
            continue
        h = hashlib.sha256()
        with fpath.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        actual = h.hexdigest()
        if actual.lower() != expected_hash.lower():
            errors.append(f"HASH_MISMATCH: {rel_path} got {actual}, expected {expected_hash}")
    return (len(errors) == 0, errors)


def build_frozen_manifest(
    campaign_id: str,
    target_pairs: int,
    completed_pairs: int,
    dataset_hashes: Dict[str, str],
    hardware_unchanged: bool,
    exceptions: List[str],
    invalid_attempts: int,
) -> Dict[str, Any]:
    """A-W20-04: Create immutable campaign manifest.
    
    Distinguishes the algorithmic SHA-256 content digest from human operator signoff.
    """
    canonical_payload = {
        "campaign_id": campaign_id,
        "target_pairs": target_pairs,
        "completed_pairs": completed_pairs,
        "hardware_unchanged": hardware_unchanged,
        "exceptions": sorted(exceptions),
        "invalid_attempts": invalid_attempts,
        "dataset_hashes": {k: dataset_hashes[k] for k in sorted(dataset_hashes.keys())},
    }
    
    serialized = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
    content_sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    return {
        "manifest_version": "1.1",
        "canonical_payload": canonical_payload,
        "manifest_digest_sha256": content_sha256,
        "operator_signature": {
            "status": "PENDING_OPERATOR_PHYSICAL_SIGNATURE",
            "signed": False,
            "signer_name": None,
            "signed_at": None,
            "note": "SHA-256 digest guarantees cryptographic integrity; human acceptance requires physical operator signoff.",
        },
    }
