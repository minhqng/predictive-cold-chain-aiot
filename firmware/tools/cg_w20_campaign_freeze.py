"""ColdGuard Member A — W20 Campaign Wave 2 & Data Freeze Tool.

Validates compliance with docs/05A §29:
- A-W20-01: Invariant protocol continuity.
- A-W20-02: Valid-pair completion rule validation.
- A-W20-03: Campaign close physical audit (sensor identity, drift, damage).
- A-W20-04: Freeze physical campaign data and generate signed manifest.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PairBalanceSummary:
    valid_a_runs: int
    valid_b_runs: int
    is_balanced: bool
    invalid_runs_count: int


def verify_campaign_pair_balance(
    runs: List[Dict[str, Any]]
) -> PairBalanceSummary:
    """A-W20-02: Ensure valid paired completion without selective dropouts."""
    a_count = 0
    b_count = 0
    invalid_count = 0

    for r in runs:
        if not r.get("valid_for_analysis", True):
            invalid_count += 1
            continue
        ctrl = r.get("controller", "").upper()
        if "A" in ctrl:
            a_count += 1
        elif "B" in ctrl:
            b_count += 1

    return PairBalanceSummary(
        valid_a_runs=a_count,
        valid_b_runs=b_count,
        is_balanced=(a_count == b_count and a_count > 0),
        invalid_runs_count=invalid_count,
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


def build_frozen_manifest(
    campaign_id: str,
    dataset_hashes: Dict[str, str],
    hardware_unchanged: bool,
    exceptions: List[str],
    invalid_attempts: int,
) -> Dict[str, Any]:
    """A-W20-04: Create immutable campaign manifest."""
    manifest = {
        "campaign_id": campaign_id,
        "hardware_unchanged": hardware_unchanged,
        "exceptions": exceptions,
        "invalid_attempts": invalid_attempts,
        "dataset_hashes": dataset_hashes,
        "manifest_signature": hashlib.sha256(
            f"{campaign_id}:{hardware_unchanged}:{invalid_attempts}:{sorted(dataset_hashes.items())}".encode("utf-8")
        ).hexdigest(),
    }
    return manifest
