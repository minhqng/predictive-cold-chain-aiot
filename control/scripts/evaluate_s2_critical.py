"""Evaluate accepted S2 door runs against D's candidate critical threshold.

This is an offline, read-only calculation. A threshold crossing can describe
the committed capture; it never freezes a safety limit or enables control.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _csv_number(row: dict[str, str], name: str) -> float:
    try:
        result = float(row[name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name} in accepted S2 dataset") from exc
    if not math.isfinite(result):
        raise ValueError(f"non-finite {name} in accepted S2 dataset")
    return result


def _time(row: dict[str, str]) -> datetime:
    try:
        return datetime.fromisoformat(row["host_time_utc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("accepted S2 row lacks a valid host_time_utc") from exc


def evaluate(root: Path) -> dict[str, object]:
    candidate_path = root / "evidence/D/W13/critical-threshold-candidate-v0.json"
    pr_binding_path = root / "evidence/D/W09/a-pr91-s1-s2-source-binding.json"
    handoff_root = root / "evidence/A/SOURCES/20261107/datasets"
    run_index_path = handoff_root / "run_index.csv"
    manifest_path = handoff_root / "manifest.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    pr_binding = json.loads(pr_binding_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    threshold_c = _number("critical_threshold_c", candidate["critical_threshold_c"])
    if candidate.get("representative_source") != "TMEAN_AIR_MEAN_T1_T3_T4":
        raise ValueError("candidate representative source is not the S2 Tmean field")
    if candidate.get("status") != "CANDIDATE_NOT_SAFETY_FROZEN":
        raise ValueError("candidate status changed; reassess before evaluation")
    if pr_binding.get("verdict") != "PR91_SOURCES_HASH_VERIFIED":
        raise ValueError("A PR #91 S1/S2 source binding is not verified")
    if pr_binding["source_pr"].get("head") != "63982e9592e0687099afb53fa1e4422f57761d74":
        raise ValueError("A PR #91 head changed; reassess source provenance")
    pr_s2_hashes = {
        source["sha256"]
        for source in pr_binding["raw_sources"]
        if "/s2/" in source["path"]
    }
    normalized_s2_inputs = {
        source["sha256"]
        for source in manifest["inputs"]
        if source["package_path"] == "raw/s2-door-20261107/telemetry_raw.log"
    }
    if not pr_s2_hashes or normalized_s2_inputs != pr_s2_hashes:
        raise ValueError("normalized S2 handoff is not bound to A PR #91 raw data")

    with run_index_path.open(encoding="utf-8-sig", newline="") as stream:
        index_rows = list(csv.DictReader(stream))
    selected = [
        row
        for row in index_rows
        if row["classification"] == "DATASET_ACCEPTED_S2"
        and row["scenario"] == "S2_DOOR"
    ]
    if not selected:
        raise ValueError("no accepted S2 door runs in the handoff")

    results: list[dict[str, object]] = []
    for index in selected:
        dataset_path = handoff_root / index["dataset_path"]
        actual_hash = _sha256(dataset_path)
        if actual_hash != index["dataset_sha256"]:
            raise ValueError(f"dataset hash mismatch for {index['run_tag']}")
        with dataset_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if not rows or any(row.get("run_tag") != index["run_tag"] for row in rows):
            raise ValueError(f"run identity mismatch for {index['run_tag']}")

        qualified = [
            row
            for row in rows
            if row.get("t1_status") == "OK"
            and row.get("t3_status") == "OK"
            and row.get("t4_status") == "OK"
            and row.get("tmean_air_c") not in (None, "")
        ]
        door_rows = [
            row
            for row in qualified
            if row.get("door_status") == "OK"
            and _csv_number(row, "door_open") >= 1.0
        ]
        if not door_rows:
            raise ValueError(f"no qualified door-open anchor for {index['run_tag']}")
        door_row = door_rows[0]
        door_at = _time(door_row)
        after_door = [row for row in qualified if _time(row) >= door_at]
        crossings = [
            row
            for row in after_door
            if _csv_number(row, "tmean_air_c") >= threshold_c
        ]
        max_row = max(after_door, key=lambda row: _csv_number(row, "tmean_air_c"))
        last_at = _time(after_door[-1])
        if crossings:
            critical_row = crossings[0]
            critical_at = _time(critical_row)
            status = "THRESHOLD_REACHED"
            door_to_critical_s: float | None = (critical_at - door_at).total_seconds()
            lower_bound_s: float | None = None
            critical_at_text: str | None = critical_row["host_time_utc"]
        else:
            status = "RIGHT_CENSORED_THRESHOLD_NOT_REACHED"
            door_to_critical_s = None
            lower_bound_s = (last_at - door_at).total_seconds()
            critical_at_text = None
        results.append(
            {
                "run_id": index["run_tag"],
                "dataset": index["dataset_path"],
                "dataset_sha256": actual_hash,
                "boot_id": index["boot_id"],
                "hardware_config_id": index["hardware_config_id"],
                "firmware_version": index["firmware_version"],
                "clock_domain": index["timebase"],
                "qualified_rows": len(qualified),
                "door_open_at": door_row["host_time_utc"],
                "critical_at": critical_at_text,
                "door_to_critical_s": door_to_critical_s,
                "right_censored_lower_bound_s": lower_bound_s,
                "max_tmean_after_door_c": _csv_number(max_row, "tmean_air_c"),
                "status": status,
            }
        )

    reached = sum(item["status"] == "THRESHOLD_REACHED" for item in results)
    return {
        "scope": "D_OFFLINE_S2_CRITICAL_THRESHOLD_EVALUATION",
        "policy_version": candidate["policy_version"],
        "threshold_status": candidate["status"],
        "critical_threshold_c": threshold_c,
        "representative_source": candidate["representative_source"],
        "candidate_source": {
            "path": candidate_path.relative_to(root).as_posix(),
            "sha256": _sha256(candidate_path),
        },
        "source_pr": pr_binding["source_pr"],
        "pr91_source_binding": {
            "path": pr_binding_path.relative_to(root).as_posix(),
            "sha256": _sha256(pr_binding_path),
        },
        "normalized_handoff_manifest": {
            "path": manifest_path.relative_to(root).as_posix(),
            "sha256": _sha256(manifest_path),
        },
        "run_index": {
            "path": run_index_path.relative_to(root).as_posix(),
            "sha256": _sha256(run_index_path),
        },
        "accepted_s2_door_runs": len(results),
        "threshold_reached_runs": reached,
        "aggregate_status": (
            "MEASURED_CROSSING_AVAILABLE"
            if reached
            else "RIGHT_CENSORED_NO_CAPTURE_REACHED_THRESHOLD"
        ),
        "a_w13_03_result": (
            "CANDIDATE_TIMING_AVAILABLE"
            if reached
            else "NOT_COMPUTABLE_THRESHOLD_NOT_REACHED"
        ),
        "physical_enablement": False,
        "runs": results,
        "note": (
            "30.5 C is a team-supplied candidate, not a commissioned safety "
            "limit. A non-crossing run yields a lower observation bound, not "
            "a fabricated door-to-critical time."
        ),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    result = evaluate(root)
    target = root / "evidence/D/W13/s2-critical-threshold-evaluation.json"
    target.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
