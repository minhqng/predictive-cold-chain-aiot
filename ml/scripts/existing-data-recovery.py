#!/usr/bin/env python3
"""ColdGuard existing physical data recovery CLI (Member B).

Usage::

    python scripts/existing-data-recovery.py \
        --a-dataset-dir ../evidence/A/SOURCES/20261107/datasets \
        --a-timing-report ../evidence/A/W13/plant-timing-report.json \
        --w05-export ../evidence/A/W09/exports/CG-S1-H8C-600S.json \
        --w05-row-validity ../evidence/A/W09/exports/CG-S1-H8C-600S.row-validity.csv \
        --w05-raw ../evidence/A/W04/tec-cooling-response-600s.csv \
        --w21-manifest reports/W21/w21-manifest.json \
        --out reports/DataRecovery \
        --repository-revision <revision>

The A 20261107 package is merged on origin/main but is absent from this
branch ancestry. Export it read-only from the pinned revision::

    git archive d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85 \
        evidence/A/SOURCES/20261107/datasets | tar -x -C <export-dir>

Exit codes:

* 0 - the package was generated with honest statuses (a RED Gate B is a
  successful software result, not a CLI failure);
* 2 - a provenance/integrity refusal or a validator failure; no partial
  success is claimed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:  # installed package
    from coldguard_ml.existing_data_recovery import (
        RecoveryError,
        SourceIntegrityError,
        build_package,
        write_package,
    )
except ModuleNotFoundError:  # direct checkout invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml.existing_data_recovery import (
        RecoveryError,
        SourceIntegrityError,
        build_package,
        write_package,
    )


def _repo_revision(root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "UNCOMMITTED"
    return completed.stdout.strip() or "UNCOMMITTED"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Recover existing Member A physical data for bounded descriptive "
            "analysis. No new measurement, model training, W16 opening or "
            "Gate B override."
        )
    )
    parser.add_argument(
        "--a-dataset-dir",
        default="../evidence/A/SOURCES/20261107/datasets",
        help="read-only export of the A 20261107 dataset package",
    )
    parser.add_argument(
        "--a-dataset-label",
        default="evidence/A/SOURCES/20261107/datasets",
        help="declared source label used in generated artifacts",
    )
    parser.add_argument(
        "--a-timing-report",
        default="../evidence/A/W13/plant-timing-report.json",
    )
    parser.add_argument(
        "--w05-export", default="../evidence/A/W09/exports/CG-S1-H8C-600S.json"
    )
    parser.add_argument(
        "--w05-row-validity",
        default="../evidence/A/W09/exports/CG-S1-H8C-600S.row-validity.csv",
    )
    parser.add_argument(
        "--w05-raw", default="../evidence/A/W04/tec-cooling-response-600s.csv"
    )
    parser.add_argument(
        "--w05-run-index", default="../evidence/A/W09/s1-run-index.json"
    )
    parser.add_argument(
        "--w21-manifest", default="reports/W21/w21-manifest.json"
    )
    parser.add_argument("--out", default="reports/DataRecovery")
    parser.add_argument("--repository-revision", default=None)
    parser.add_argument(
        "--source-inventory",
        default=None,
        help=(
            "explicit allowlisted inventory JSON; the generated "
            "source-inventory.json can be fed back for replay"
        ),
    )
    parser.add_argument("--gate-b-timeout", type=int, default=180)
    return parser


def _resolve(ml_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (ml_root / path).resolve()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    ml_root = Path(__file__).resolve().parents[1]
    repo_root = ml_root.parent
    out_dir = _resolve(ml_root, args.out)
    revision = args.repository_revision or _repo_revision(repo_root)
    source_inventory = None
    if args.source_inventory:
        inventory_path = _resolve(ml_root, args.source_inventory)
        source_inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(
        prefix="coldguard-existing-data-recovery-"
    ) as scratch:
        try:
            package = build_package(
                repo_root=repo_root,
                ml_root=ml_root,
                a_dataset_dir=_resolve(ml_root, args.a_dataset_dir),
                a_dataset_label=args.a_dataset_label,
                a_timing_path=_resolve(ml_root, args.a_timing_report),
                w05_export=_resolve(ml_root, args.w05_export),
                w05_row_validity=_resolve(ml_root, args.w05_row_validity),
                w05_raw=_resolve(ml_root, args.w05_raw),
                w05_run_index=_resolve(ml_root, args.w05_run_index),
                w21_manifest=_resolve(ml_root, args.w21_manifest),
                repository_revision=revision,
                source_inventory=source_inventory,
                gate_b_out=Path(scratch) / "gate-b",
                gate_b_timeout=args.gate_b_timeout,
            )
            written = write_package(package, out_dir)
        except (RecoveryError, SourceIntegrityError) as exc:
            print(f"EXISTING_DATA_RECOVERY REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:  # fail closed, never a partial success claim
            print(f"EXISTING_DATA_RECOVERY REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
    statuses = package.statuses
    print(
        "EXISTING_DATA_RECOVERY COMPLETE: "
        f"audit={statuses['EXISTING_PHYSICAL_DATA_AUDIT']} "
        f"descriptive={statuses['USABLE_PHYSICAL_DESCRIPTIVE_DATA']} "
        f"door={statuses['USABLE_DOOR_DISTURBANCE_DATA']} "
        f"sensor={statuses['USABLE_SENSOR_DIAGNOSTIC_DATA']} "
        f"gate_b={statuses['GATE_B_PHYSICAL_DATA']}/"
        f"{statuses['PREDICTIVE_DATASET_READINESS']} "
        f"demo={statuses['DEADLINE_DEMO_PACKAGE']} "
        f"artifacts={len(written)} out={out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
