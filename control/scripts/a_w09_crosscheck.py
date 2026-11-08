"""Read-only admission cross-check for Member A's W09 export.

Usage: python control/scripts/a_w09_crosscheck.py <row-validity.csv>
       <s1-run-index.json> <output.json>

The result is a source-hashed negative control. It never qualifies an envelope
or changes Member A's source artifacts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def analyze(rows_path: Path, index_path: Path) -> dict[str, object]:
    with rows_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    required = {"electrical_quality", "boot_id", "run_id", "seq"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("A W09 export is empty or missing required identity/quality columns")
    if not isinstance(index, dict):
        raise ValueError("A W09 run index must be an object")
    eligible = index.get("valid_s1_run_ids_for_member_b")
    if not isinstance(eligible, list) or any(not isinstance(x, str) for x in eligible):
        raise ValueError("A W09 index must carry a string valid-S1 run list")
    quality = Counter(row["electrical_quality"] or "MISSING" for row in rows)
    run_labels = sorted({row["run_id"] for row in rows})
    source_admissible_for_review = (
        bool(eligible)
        and bool(rows)
        and set(quality) == {"VALID"}
        and set(run_labels).issubset(set(eligible))
    )
    return {
        "scope": "D_READ_ONLY_SOURCE_ADMISSION_NEGATIVE_CONTROL",
        "source_csv": rows_path.as_posix(),
        "source_csv_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
        "source_index": index_path.as_posix(),
        "source_index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "rows": len(rows),
        "boot_ids": sorted({row["boot_id"] for row in rows}),
        "run_labels": run_labels,
        "electrical_quality_counts": dict(sorted(quality.items())),
        "eligible_s1_run_ids": eligible,
        "source_admissible_for_review": source_admissible_for_review,
        "verdict": "SOURCE_ADMISSIBLE_ONLY" if source_admissible_for_review else "UNKNOWN",
        "note": (
            "Source admission alone never qualifies an OFF/ON envelope or proves "
            "cooling; the verifier also requires applied-state and physical windows."
        ),
    }


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    result = analyze(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
