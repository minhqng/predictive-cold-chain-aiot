"""Import the authoritative W01-W04 documentary evidence into a session.

Only the four canonical Member A corpora are used. The truncated repository
root `evidence/` copy is deliberately not a source. Imported files are
referenced by hash and provenance; importing never marks a requirement PASS.
"""

from __future__ import annotations

import pathlib
from typing import Iterable

from .evidence import EvidenceError, SessionStore

# test_id -> repository-relative globs. Only documentary/measurement records
# that already exist in the authoritative worktrees are listed.
MAPPING: dict[str, tuple[str, ...]] = {
    "A-W01-01": ("A-W01-hardware-audit/evidence/A/W01/bom-audit.csv",),
    "A-W01-02": ("A-W01-hardware-audit/evidence/A/W01/photo-inventory.csv",
                 "A-W01-hardware-audit/evidence/A/W01/photos/*.jpg"),
    "A-W01-03": ("A-W01-hardware-audit/evidence/A/W01/pin-candidates-v0.md",),
    "A-W01-04": ("A-W01-hardware-audit/evidence/A/W01/physical-risk-ledger.md",),
    "A-W01-05": ("A-W01-hardware-audit/evidence/A/W01/legacy-assumption-check.md",),
    "A-W02-01": ("A-W01-hardware-audit/evidence/A/W01/photos/01-overview-wiring.jpg",
                 "A-W02-sensor-foundation/evidence/A/W02/bench-procedure-w02.md"),
    "A-W02-02": ("A-W02-sensor-foundation/evidence/A/W02/sensor-rom-map.yaml",),
    "A-W02-03": ("A-W02-sensor-foundation/evidence/A/W02/espidf-run/reboot-verification.md",
                 "A-W02-sensor-foundation/evidence/A/W02/espidf-run/reboot-verification.json"),
    "A-W02-04": ("A-W02-sensor-foundation/evidence/A/W02/espidf-run/runtime-cadence.md",),
    "A-W02-05": ("A-W02-sensor-foundation/evidence/A/W02/ds18b20/sensor-consistency.csv",
                 "A-W02-sensor-foundation/evidence/A/W02/ds18b20/sensor-consistency-report.md"),
    "A-W02-06": ("A-W02-sensor-foundation/evidence/A/W02/bme280/bme280-bench-report.md",
                 "A-W02-sensor-foundation/evidence/A/W02/bme280/bme280-bench.csv"),
    "A-W02-07": ("A-W02-sensor-foundation/evidence/A/W02/mc38/mc38-bench-report.md",
                 "A-W02-sensor-foundation/evidence/A/W02/mc38/mc38-bench.csv"),
    "A-W03-01": ("A-W03-power-pzem-logic/evidence/A/W03/logic-power-measurement.md",),
    "A-W03-02": ("A-W03-power-pzem-logic/evidence/A/W03/rs485-pin-and-compatibility.md",),
    "A-W03-03": ("A-W03-power-pzem-logic/evidence/A/W03/hardware-2026-10-27/README.md",
                 "A-W03-power-pzem-logic/evidence/A/W03/hardware-2026-10-20/crc-audit.md"),
    "A-W03-04": ("A-W03-power-pzem-logic/evidence/A/W03/pzem-register-readback.txt",
                 "A-W03-power-pzem-logic/evidence/A/W03/hardware-2026-10-27/test-131-profile-readback.md"),
    "A-W03-05": ("A-W03-power-pzem-logic/evidence/A/W03/hardware-2026-10-27/raw/test-132b-off-envelope.csv",),
    "A-W03-06": ("A-W03-power-pzem-logic/evidence/A/W03/hardware-2026-10-27/shunt-continuity.md",
                 "A-W01-hardware-audit/evidence/A/W01/photos/18-shunt-marking-actual.jpg"),
    "A-W03-07": ("A-W03-power-pzem-logic/evidence/A/W03/ibt2-pin-map.md",
                 "A-W03-power-pzem-logic/evidence/A/W03/hardware-deviation-and-safety.md"),
    "A-W04-01": ("A-W04-delivery/evidence/A/W04/g0-electrical-verification.md",),
    "A-W04-02": ("A-W03-power-pzem-logic/evidence/A/W03/hardware-deviation-and-safety.md",
                 "A-W04-delivery/evidence/A/W04/g0-electrical-verification.md"),
    "A-W04-03": ("A-W04-delivery/evidence/A/W04/fuse-commissioning-note.md",),
    "A-W04-04": ("A-W04-delivery/evidence/A/W04/boot-default-off.csv",
                 "A-W04-delivery/evidence/A/W04/boot-default-off-note.md"),
    "A-W04-05": ("A-W04-tec-commissioning/evidence/A/W04/h6/41-h6-run-analysis.md",
                 "A-W04-tec-commissioning/evidence/A/W04/h7/90-h7-commissioning-final-report.md"),
    "A-W04-06": ("A-W04-tec-commissioning/evidence/A/W04/h6-tec-polarity-test-plan.md",),
    "A-W04-07": ("A-W04-tec-commissioning/evidence/A/W04/h6/41-h6-run-analysis.md",
                 "A-W04-tec-commissioning/evidence/A/W04/h7/90-h7-commissioning-final-report.md"),
}

_ALLOWED_SUFFIXES = {".md", ".csv", ".txt", ".yaml", ".yml", ".json", ".jpg",
                     ".jpeg", ".png"}


def repo_root_from_app() -> pathlib.Path:
    # tools/member_a_app/evidence_import.py -> worktree root -> workspace root
    return pathlib.Path(__file__).resolve().parents[3]


def _expand(root: pathlib.Path, pattern: str) -> list[pathlib.Path]:
    matches = sorted(root.glob(pattern))
    out = []
    for path in matches:
        if path.is_file() and path.suffix.lower() in _ALLOWED_SUFFIXES and path.stat().st_size > 0:
            out.append(path)
    return out


def import_all(store: SessionStore, root: pathlib.Path | None = None,
               dry_run: bool = False) -> dict:
    root = pathlib.Path(root or repo_root_from_app())
    summary = {
        "root": str(root),
        "imported": 0,
        "skipped_duplicate": 0,
        "missing": [],
        "errors": [],
        "by_test": {},
    }
    if not root.is_dir():
        summary["errors"].append(f"source root is not a directory: {root}")
        return summary
    for test_id, patterns in MAPPING.items():
        imported_for_test = 0
        for pattern in patterns:
            paths = _expand(root, pattern)
            if not paths:
                summary["missing"].append({"test_id": test_id, "pattern": pattern})
                continue
            for path in paths:
                try:
                    before = len(store.imported_for(test_id))
                    if dry_run:
                        summary["imported"] += 1
                        imported_for_test += 1
                        continue
                    record = store.import_evidence(test_id, path,
                                                   category="photo" if path.suffix.lower()
                                                   in {".jpg", ".jpeg", ".png"} else "document")
                    after = len(store.imported_for(test_id))
                    if after > before:
                        summary["imported"] += 1
                        imported_for_test += 1
                    else:
                        summary["skipped_duplicate"] += 1
                    if record is None:
                        summary["errors"].append(
                            {"test_id": test_id, "path": str(path), "error": "no record"})
                except (EvidenceError, OSError) as exc:
                    summary["errors"].append(
                        {"test_id": test_id, "path": str(path), "error": str(exc)})
        if imported_for_test:
            summary["by_test"][test_id] = imported_for_test
    return summary


def imported_manifest_rows(store: SessionStore) -> list[dict]:
    return store.imported_manifest()
