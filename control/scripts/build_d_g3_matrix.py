"""Rebuild D's G3 readiness matrix from the current committed evidence.

Run at repository root: python control/scripts/build_d_g3_matrix.py
This is a D readiness report, never a team G3 decision or physical signoff.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def _source(path: Path, root: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def build(root: Path) -> dict[str, object]:
    legacy_gate_path = root / "evidence/A/W12/gate-g3-input.json"
    inspection_path = root / "evidence/A/W12/results/A-W12-03.json"
    run_index_path = root / "evidence/A/SOURCES/20261107/datasets/run_index.csv"
    summary_path = root / "evidence/A/SOURCES/20261107/datasets/measurement_summary.csv"
    pr95_s1_path = root / "evidence/D/W09/a-pr95-supplementary-s1-binding.json"

    legacy_gate = json.loads(legacy_gate_path.read_text(encoding="utf-8"))
    inspection = json.loads(inspection_path.read_text(encoding="utf-8"))
    pr95_s1 = json.loads(pr95_s1_path.read_text(encoding="utf-8"))
    with run_index_path.open(encoding="utf-8-sig", newline="") as stream:
        runs = list(csv.DictReader(stream))
    with summary_path.open(encoding="utf-8-sig", newline="") as stream:
        summaries = list(csv.DictReader(stream))

    if inspection.get("outcome") != "PASS":
        raise ValueError("A-W12-03 is not PASS; reassess the D matrix manually")
    if not runs or not summaries:
        raise ValueError("A dataset handoff is empty; reassess the D matrix manually")
    if pr95_s1.get("verdict") != "PR95_SUPPLEMENTARY_S1_HASH_VERIFIED_NOT_ADMITTED":
        raise ValueError("A PR #95 supplementary S1 binding changed; reassess manually")

    classifications = Counter(row["classification"] for row in runs)
    accepted_s1 = classifications["DATASET_ACCEPTED_S1"]
    accepted_s2 = classifications["DATASET_ACCEPTED_S2"]
    if accepted_s1 < 1 or accepted_s2 < 1:
        raise ValueError("Accepted S1/S2 source set changed; reassess manually")

    qualified_s2_rows = sum(
        int(row["quality_electrical_ok"])
        for row in summaries
        if row["classification"] == "DATASET_ACCEPTED_S2"
    )
    s2_not_ok_rows = sum(
        int(row["quality_electrical_not_ok"])
        for row in summaries
        if row["classification"] == "DATASET_ACCEPTED_S2"
    )

    old_open = [item["blocker"] for item in legacy_gate["blockers"] if item["open"]]
    remaining_legacy = [item for item in old_open if "fuse/conductor" in item]
    if not remaining_legacy:
        raise ValueError("Fuse/conductor legacy blocker changed; reassess manually")

    return {
        "scope": "MEMBER_D_G3_READINESS_ONLY",
        "overall": "NOT_VERIFIED",
        "team_gate_decision": "NOT_CLAIMED",
        "sources": [
            _source(legacy_gate_path, root),
            _source(inspection_path, root),
            _source(run_index_path, root),
            _source(summary_path, root),
            _source(pr95_s1_path, root),
        ],
        "source_facts": {
            "accepted_s1_runs": accepted_s1,
            "accepted_s2_windows": accepted_s2,
            "accepted_s2_electrical_ok_rows": qualified_s2_rows,
            "accepted_s2_electrical_not_ok_rows": s2_not_ok_rows,
            "post_freeze_inspection": inspection["outcome"],
            "supplementary_s1_runs": 1,
            "supplementary_s1_frozen_package_admission": (
                pr95_s1["admission"]["frozen_18_run_package"]
            ),
        },
        "checks": [
            {
                "id": "D-W12-01",
                "status": "OPEN",
                "reason": "Measured Controller A representation, thresholds, persistence and applied-action state are not frozen",
            },
            {
                "id": "D-W12-02",
                "status": "SOURCE_AVAILABLE_RESULT_OPEN",
                "reason": "Accepted S1/S2 datasets exist, but no admitted frozen-Controller-A replay set exists",
            },
            {
                "id": "D-W12-03",
                "status": "PARTIAL_INPUTS",
                "reason": "Post-freeze inspection and qualified S2 source rows exist; a real Controller A command-to-applied/electrical/thermal benchmark is absent",
            },
            {
                "id": "D-W12-04",
                "status": "SYNTHETIC_ONLY",
                "reason": "Unit lifecycle wiring is tested; device command/ACK/dedup/applied-state trace is absent",
            },
            {
                "id": "D-W12-05",
                "status": "OPEN",
                "reason": "Fuse/conductor disposition, controller benchmark, command lifecycle and whole-team owner signoffs remain open",
            },
        ],
        "remaining_blockers": [
            remaining_legacy[0],
            "frozen Controller A configuration and supervised real Controller A run",
            "end-to-end command lifecycle with canonical ACK, applied state and physical dedup",
            "whole-team G3 owner review and signoff",
        ],
        "superseded_legacy_blockers": [
            item for item in old_open if item not in remaining_legacy
        ],
        "rebuild_command": "python control/scripts/build_d_g3_matrix.py",
    }


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    result = build(root)
    target = root / "evidence/D/W12/g3-evidence-matrix.json"
    target.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
