"""Rebuild D's G3 readiness matrix from committed A and D evidence.

Run at repository root: python control/scripts/build_d_g3_matrix.py
This is a D readiness report, never a team G3 decision or physical signoff.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _source(path: Path, root: Path) -> dict[str, str]:
    return {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def build(root: Path) -> dict[str, object]:
    a_gate_path = root / "evidence/A/W12/gate-g3-input.json"
    a_crosscheck_path = root / "evidence/D/W09/a-w09-source-crosscheck.json"
    a_gate = json.loads(a_gate_path.read_text(encoding="utf-8"))
    crosscheck = json.loads(a_crosscheck_path.read_text(encoding="utf-8"))
    blockers = [item["blocker"] for item in a_gate["blockers"] if item["open"]]
    if not blockers or a_gate["a_side_status"] == "GREEN":
        raise ValueError("A G3 source changed; reassess the D matrix manually")
    if crosscheck["verdict"] != "UNKNOWN" or crosscheck["source_admissible_for_review"]:
        raise ValueError("A W09 source admission changed; reassess the D matrix manually")
    return {
        "scope": "MEMBER_D_G3_READINESS_ONLY",
        "overall": "NOT_VERIFIED",
        "team_gate_decision": "NOT_CLAIMED",
        "sources": [_source(a_gate_path, root), _source(a_crosscheck_path, root)],
        "checks": [
            {"id": "D-W12-01", "status": "OPEN", "reason": "Measured Controller A thresholds, persistence and applied-action state are not frozen"},
            {"id": "D-W12-02", "status": "CONTRACT_ONLY", "reason": "Replay contract exists; no admissible independent recorded run is committed"},
            {"id": "D-W12-03", "status": "BLOCKED", "reason": "Physical S2 benchmark and qualified electrical channel remain open"},
            {"id": "D-W12-04", "status": "SYNTHETIC_ONLY", "reason": "Unit lifecycle wiring is tested; device-to-actuation trace is absent"},
            {"id": "D-W12-05", "status": "OPEN", "reason": "A G3 input has open blockers; whole-team gate requires owner signoffs"},
        ],
        "a_open_blockers": blockers,
        "a_w09_electrical_quality_counts": crosscheck["electrical_quality_counts"],
        "rebuild_command": "python control/scripts/build_d_g3_matrix.py",
    }


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    result = build(root)
    target = root / "evidence/D/W12/g3-evidence-matrix.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
