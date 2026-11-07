"""B-W08-01 … B-W08-04 adversarial and integration tests.

Controlled fixtures are synthetic A-export shapes. The real A W09 export and
run index are consumed read-only. No test drives hardware, trains a model,
creates a locked test manifest or inspects locked outcomes.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from coldguard_ml import load_capture, evaluate_admission, analyze_capture
from coldguard_ml.data_readiness import (
    CHECK_FAIL,
    CHECK_NOT_EVALUABLE,
    CHECK_PASS,
    DIMENSION_CRITICAL,
    DIMENSION_EVENT,
    DIMENSION_TIMING,
    DIMENSION_WHOLE,
    ELIGIBILITY_BLOCKED,
    ELIGIBILITY_ELIGIBLE,
    REASON_AUTHORITY_INVALID,
    REASON_CRITICAL_CHANNEL,
    REASON_DUPLICATE_CONFLICT,
    REASON_EVENT_ANCHOR_MISSING,
    REASON_MANIFEST_MISSING,
    REASON_MANIFEST_MISMATCH,
    REASON_THRESHOLD_EQUALITY,
    REASON_THRESHOLD_UNRESOLVED,
    SPLIT_NOT_FEASIBLE,
    SPLIT_PROVISIONAL,
    THRESHOLD_PROPOSED,
    RunManifestLinkage,
    SplitCandidate,
    assess_gate_b,
    build_gate_b_report,
    build_gate_manifest,
    default_completeness_policy,
    default_scenario_requirement,
    plan_development_split,
    render_completeness_policy,
    render_readiness_report,
    render_split_plan,
    run_validation_csv,
    validate_run,
)
from coldguard_ml.intake import AdmissionStage
from coldguard_ml.real_data_qa import QAConfig

from test_intake_schema import write_a_export

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPO_ROOT / "ml"
REAL_A_EXPORT = REPO_ROOT / "evidence/A/W09/exports/CG-S1-H8C-600S.json"
REAL_A_INDEX = REPO_ROOT / "evidence/A/W09/s1-run-index.json"
CLI = ML_ROOT / "scripts" / "gate-b-readiness-W08.py"

S1_KEY = "S1_NORMAL_BASELINE"
S2_KEY = "S2_DOOR_DISTURBANCE"


def _timestamp(index: int) -> str:
    return f"2026-01-01T00:{index // 60:02d}:{index % 60:02d}Z"


def _rows(
    count: int = 12,
    *,
    scenario_key: str = S1_KEY,
    door=None,
    thermal_quality: str = "VALID",
    electrical_quality: str = "VALID",
    door_quality: str = "VALID",
    power_w: str = "0.0",
    invalidation: str = "NONE",
    skip_times: set[int] | None = None,
) -> list[dict[str, str]]:
    skip_times = skip_times or set()
    rows: list[dict[str, str]] = []
    for index in range(count):
        if index in skip_times:
            continue
        row = {
            "timestamp_utc": _timestamp(index),
            "timestamp_utc_status": "SYNCED",
            "usable_for": scenario_key,
            "quality": "VALID",
            "producer_quality": "VALID",
            "thermal_quality": thermal_quality,
            "environment_quality": "VALID",
            "electrical_quality": electrical_quality,
            "door_quality": door_quality,
            "sequence_quality": "VALID",
            "provenance_quality": "VALID",
            "invalidation_reasons": invalidation,
            "device_ms": str(index * 1000),
            "power_w": power_w,
            "current_a": "0.0",
            "voltage_v": "12.0",
        }
        if door is not None:
            row["door_open"] = door(index)
        rows.append(row)
    return rows


def _write_export(
    directory: Path,
    *,
    run_id: str,
    boot_id: str,
    rows: list[dict[str, str]],
    scenario_key: str = S1_KEY,
    calibration_id: str | None = "CG-CAL-001",
    device_id: str = "cg-test-001",
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return write_a_export(
        directory,
        rows=rows,
        run_id=run_id,
        boot_id=boot_id,
        device_id=device_id,
        calibration_id=calibration_id,
        scenario_candidate=scenario_key,
        timestamp_semantics={
            "timestamp_utc_status": "SYNCED",
            "timestamp_utc_source": "DEVICE_CLOCK_SYNCED",
            "measurement_time_axis": "DEVICE_UTC",
        },
        invalidation_summary={
            "rows_total": len(rows),
            "rows_usable_per_scenario": {scenario_key: len(rows)},
            "scenario_required_domains": {
                scenario_key: [
                    "provenance",
                    "producer",
                    "thermal",
                    "environment",
                    "door",
                    "sequence",
                ]
            },
            "reason_counts": {},
            "usable_fraction": 1.0,
        },
        extra_export={
            "hardware_config_verified": True,
            "calibration_verified": True,
            "clock_sync_verified": True,
        },
    )


def _entry(
    run_id: str,
    boot_id: str,
    *,
    scenario_key: str = S1_KEY,
    rows: int = 12,
    valid_for: list[str] | None = None,
    hardware_verified: bool = True,
    calibration_verified: bool = True,
    clock_sync: bool = True,
) -> dict:
    entry = {
        "run_id": run_id,
        "boot_id": boot_id,
        "device_run_label": "TEST_RUN",
        "frames_total": rows,
        "frames_usable_per_scenario": {scenario_key: rows},
        "top_invalidation_reasons": {},
        "usable_fraction": 1.0,
        "hardware_config_verified": hardware_verified,
        "calibration_verified": calibration_verified,
        "clock_sync_verified": clock_sync,
    }
    if valid_for is not None:
        entry["valid_for_scenarios"] = list(valid_for)
    return entry


def _write_index(
    path: Path,
    entries: list[dict],
    *,
    valid_s1: list[str] | None = None,
    blocked: list[dict] | None = None,
) -> Path:
    payload = {
        "index_version": "w09-run-index-v1",
        "runs": entries,
        "valid_s1_run_ids_for_member_b": list(valid_s1 or []),
        "blocked_run_ids": list(blocked or []),
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _planned_duration(capture) -> float:
    times = [
        row.device_ms / 1000.0
        for row in capture.rows
        if row.device_ms is not None
    ]
    return max(times) - min(times) if times else 0.0


def _linkage(capture, *, pair_id=None, controller_id=None, **overrides):
    values = {
        "run_id": capture.run.run_id,
        "device_id": capture.run.device_id,
        "boot_id": capture.run.boot_id,
        "scenario_id": capture.run.scenario_id,
        "hardware_config_id": capture.run.hardware_config_id,
        "calibration_id": capture.run.calibration_id,
        "source_sha256": capture.source.sha256,
        "pair_id": pair_id,
        "controller_id": controller_id,
        "planned_capture_duration_s": _planned_duration(capture),
    }
    values.update(overrides)
    return RunManifestLinkage(**values)


def _load_and_validate(
    export: Path,
    index: Path,
    *,
    requirement=None,
    policy=None,
    linkage: RunManifestLinkage | None | bool = True,
    capture=None,
):
    capture = capture or load_capture(export, a_run_index=index)
    admission = evaluate_admission(capture)
    qa = analyze_capture(capture, admission=admission, config=QAConfig())
    if linkage is True:
        linkage = _linkage(capture)
    return capture, admission, qa, validate_run(
        capture,
        admission=admission,
        qa=qa,
        requirement=requirement or default_scenario_requirement("S1"),
        policy=policy,
        manifest_linkage=linkage,
    )


def _green_suite(tmp_path: Path, *, count: int = 3, rows: int = 12):
    exports, entries, linkages = [], [], []
    for index in range(1, count + 1):
        run_id = f"CG-S1-A-{index:03d}"
        boot = f"boot-{index}"
        source_dir = tmp_path / f"run-{index}"
        export = _write_export(
            source_dir, run_id=run_id, boot_id=boot, rows=_rows(rows)
        )
        exports.append(export)
        entries.append(_entry(run_id, boot, rows=rows))
    index_path = _write_index(
        tmp_path / "index.json",
        entries,
        valid_s1=[entry["run_id"] for entry in entries],
    )
    requirement = default_scenario_requirement("S1")
    validations, admissions = [], []
    for export in exports:
        capture = load_capture(export, a_run_index=index_path)
        admission = evaluate_admission(capture)
        qa = analyze_capture(capture, admission=admission, config=QAConfig())
        validations.append(
            validate_run(
                capture,
                admission=admission,
                qa=qa,
                requirement=requirement,
                manifest_linkage=_linkage(capture),
            )
        )
        admissions.append(admission)
    report = build_gate_b_report(validations, admissions, requirement)
    return report, validations, admissions


def _s2_capture(tmp_path: Path, *, count: int = 24, anchor: int = 8, bad_door=False):
    def door(index: int) -> str:
        return "1" if anchor <= index < anchor + 2 else "0"

    export = _write_export(
        tmp_path / "s2",
        run_id="CG-S2-A-001",
        boot_id="s2-boot",
        rows=_rows(count, scenario_key=S2_KEY, door=door, door_quality="VALID"),
        scenario_key=S2_KEY,
    )
    index = _write_index(
        tmp_path / "s2-index.json",
        [_entry("CG-S2-A-001", "s2-boot", scenario_key=S2_KEY, rows=count, valid_for=["S2"])],
    )
    return load_capture(export, a_run_index=index), index


# ---------------------------------------------------------------------------
# identity, authority and configuration
# ---------------------------------------------------------------------------


def test_a_invalid_source_with_perfect_measurements_is_blocked(tmp_path):
    export = _write_export(
        tmp_path / "bad", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows()
    )
    index = _write_index(
        tmp_path / "bad-index.json",
        [_entry("CG-S1-A-001", "boot-1")],
        blocked=[
            {
                "run_id": "CG-S1-A-001",
                "boot_id": "boot-1",
                "device_run_label": "TEST_RUN",
                "usable_fraction": 0.0,
                "reasons": ["TEST_LEDGER_INVALID_WITH_PLAUSIBLE_READINGS"],
            }
        ],
    )
    _, _, _, validation = _load_and_validate(export, index)
    assert validation.a_ledger_verdict == "INVALID"
    assert validation.eligibility == ELIGIBILITY_BLOCKED
    assert REASON_AUTHORITY_INVALID in validation.reason_codes
    assert validation.completeness_for(DIMENSION_CRITICAL).status == CHECK_PASS


def test_missing_a_ledger_is_never_promoted(tmp_path):
    export = _write_export(
        tmp_path / "source", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows()
    )
    capture = load_capture(export)
    admission = evaluate_admission(capture)
    validation = validate_run(
        capture,
        admission=admission,
        requirement=default_scenario_requirement("S1"),
        manifest_linkage=_linkage(capture),
    )
    assert validation.a_ledger_verdict in ("MISSING", "UNKNOWN")
    assert validation.eligibility == ELIGIBILITY_BLOCKED


def test_missing_run_id_blocks_dataset_eligibility(tmp_path):
    export = _write_export(
        tmp_path / "source",
        run_id="CG-S1-A-001",
        boot_id="boot-1",
        rows=_rows(),
    )
    index = _write_index(tmp_path / "index.json", [_entry("CG-S1-A-001", "boot-1")], valid_s1=["CG-S1-A-001"])
    capture = load_capture(export, a_run_index=index)
    capture = dataclasses.replace(
        capture,
        run=dataclasses.replace(
            capture.run,
            run_id=None,
            run_id_status="UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID",
            run_ids=(),
        ),
    )
    admission = evaluate_admission(capture)
    validation = validate_run(
        capture,
        admission=admission,
        requirement=default_scenario_requirement("S1"),
        manifest_linkage=None,
    )
    assert validation.eligibility == ELIGIBILITY_BLOCKED
    assert "RUN_IDENTITY_CARRIED" in {
        check.code for check in validation.blocking_failures
    }


def test_missing_calibration_blocks_eligibility(tmp_path):
    export = _write_export(
        tmp_path / "source",
        run_id="CG-S1-A-001",
        boot_id="boot-1",
        rows=_rows(),
        calibration_id=None,
    )
    index = _write_index(
        tmp_path / "index.json", [_entry("CG-S1-A-001", "boot-1")], valid_s1=["CG-S1-A-001"]
    )
    _, _, _, validation = _load_and_validate(export, index)
    assert validation.calibration_id is None
    assert validation.eligibility == ELIGIBILITY_BLOCKED
    assert "CALIBRATION_VERIFIED" in {
        check.code for check in validation.blocking_failures
    }


def test_unknown_sensor_role_blocks_eligibility(tmp_path):
    export = _write_export(
        tmp_path / "source", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows()
    )
    index = _write_index(
        tmp_path / "index.json", [_entry("CG-S1-A-001", "boot-1")], valid_s1=["CG-S1-A-001"]
    )
    capture = load_capture(export, a_run_index=index)
    sensors = tuple(
        dataclasses.replace(role, physical_position=None, in_chamber_air_aggregate=None)
        if role.slot == "t1"
        else role
        for role in capture.sensors
    )
    capture = dataclasses.replace(capture, sensors=sensors)
    admission = evaluate_admission(capture)
    validation = validate_run(
        capture,
        admission=admission,
        requirement=default_scenario_requirement("S1"),
        manifest_linkage=_linkage(capture),
    )
    assert "PROBE_ROLES_KNOWN" in {
        check.code for check in validation.blocking_failures
    }


def test_manifest_linkage_missing_or_mismatched_blocks(tmp_path):
    export = _write_export(
        tmp_path / "source", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows()
    )
    index = _write_index(
        tmp_path / "index.json", [_entry("CG-S1-A-001", "boot-1")], valid_s1=["CG-S1-A-001"]
    )
    _, _, _, missing = _load_and_validate(export, index, linkage=None)
    assert missing.eligibility == ELIGIBILITY_BLOCKED
    assert REASON_MANIFEST_MISSING in missing.reason_codes
    _, _, _, mismatched = _load_and_validate(
        export, index, linkage=None
    )
    capture = load_capture(export, a_run_index=index)
    wrong = _linkage(capture, boot_id="different-boot")
    admission = evaluate_admission(capture)
    mismatched = validate_run(
        capture,
        admission=admission,
        requirement=default_scenario_requirement("S1"),
        manifest_linkage=wrong,
    )
    assert mismatched.eligibility == ELIGIBILITY_BLOCKED
    assert REASON_MANIFEST_MISMATCH in mismatched.reason_codes


def test_structural_valid_but_scientifically_ineligible_is_not_eligible(tmp_path):
    export = _write_export(
        tmp_path / "source", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows()
    )
    capture = load_capture(export)
    admission = evaluate_admission(capture)
    validation = validate_run(
        capture,
        admission=admission,
        requirement=default_scenario_requirement("S1"),
        manifest_linkage=None,
    )
    assert admission.highest_stage is not AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET
    assert validation.eligibility != ELIGIBILITY_ELIGIBLE
    assert validation.admission_highest_stage != "ELIGIBLE_FOR_PREDICTIVE_DATASET"


def test_duplicate_view_conflict_fails_closed_at_suite_level(tmp_path):
    export = _write_export(
        tmp_path / "source", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows()
    )
    valid_index = _write_index(
        tmp_path / "valid.json", [_entry("CG-S1-A-001", "boot-1")], valid_s1=["CG-S1-A-001"]
    )
    invalid_index = _write_index(
        tmp_path / "invalid.json",
        [_entry("CG-S1-A-001", "boot-1")],
        blocked=[
            {
                "run_id": "CG-S1-A-001",
                "boot_id": "boot-1",
                "device_run_label": "TEST_RUN",
                "usable_fraction": 0.0,
                "reasons": ["TEST_INVALID"],
            }
        ],
    )
    valid_capture = load_capture(export, a_run_index=valid_index)
    invalid_capture = load_capture(export, a_run_index=invalid_index)
    validations, admissions = [], []
    for capture in (valid_capture, invalid_capture):
        admission = evaluate_admission(capture)
        admissions.append(admission)
        validations.append(
            validate_run(
                capture,
                admission=admission,
                requirement=default_scenario_requirement("S1"),
                manifest_linkage=_linkage(capture),
            )
        )
    report = build_gate_b_report(
        validations, admissions, default_scenario_requirement("S1")
    )
    assert report.physical_gate.observed_status == "RED"
    assert REASON_DUPLICATE_CONFLICT in report.physical_gate.reason_codes


def test_same_boot_exports_are_one_physical_source(tmp_path):
    rows = _rows()
    first = _write_export(
        tmp_path / "first", run_id="CG-S1-A-001", boot_id="boot-1", rows=rows
    )
    second = _write_export(
        tmp_path / "second", run_id="CG-S1-A-001", boot_id="boot-1", rows=rows
    )
    index = _write_index(
        tmp_path / "index.json", [_entry("CG-S1-A-001", "boot-1")], valid_s1=["CG-S1-A-001"]
    )
    captures = [load_capture(path, a_run_index=index) for path in (first, second)]
    validations, admissions = [], []
    for capture in captures:
        admission = evaluate_admission(capture)
        admissions.append(admission)
        validations.append(
            validate_run(
                capture,
                admission=admission,
                requirement=default_scenario_requirement("S1"),
                manifest_linkage=_linkage(capture),
            )
        )
    report = build_gate_b_report(
        validations, admissions, default_scenario_requirement("S1")
    )
    assert report.physical_gate.observed_status == "RED"
    assert "INDEPENDENT_RUN_POPULATION_INSUFFICIENT" in report.physical_gate.reason_codes


# ---------------------------------------------------------------------------
# completeness and events
# ---------------------------------------------------------------------------


def test_threshold_equality_passes_and_just_below_fails(tmp_path):
    export = _write_export(
        tmp_path / "source", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows(10)
    )
    index = _write_index(
        tmp_path / "index.json", [_entry("CG-S1-A-001", "boot-1", rows=10)], valid_s1=["CG-S1-A-001"]
    )
    base = default_completeness_policy()
    thresholds = []
    for threshold in base.thresholds:
        if threshold.dimension == DIMENSION_WHOLE:
            thresholds.append(
                dataclasses.replace(
                    threshold, value=1.0, status=THRESHOLD_PROPOSED
                )
            )
        else:
            thresholds.append(threshold)
    exact = dataclasses.replace(base, thresholds=tuple(thresholds))
    _, _, _, validation = _load_and_validate(export, index, policy=exact)
    whole = validation.completeness_for(DIMENSION_WHOLE)
    assert whole.fraction == 1.0
    assert whole.status == CHECK_PASS
    assert REASON_THRESHOLD_EQUALITY in whole.reason_codes

    above = dataclasses.replace(
        base,
        thresholds=tuple(
            dataclasses.replace(threshold, value=1.01)
            if threshold.dimension == DIMENSION_WHOLE
            else threshold
            for threshold in base.thresholds
        ),
    )
    _, _, _, failed = _load_and_validate(export, index, policy=above)
    whole = failed.completeness_for(DIMENSION_WHOLE)
    assert whole.status == CHECK_FAIL
    assert whole.passes is False


def test_short_capture_inside_declared_plan_cannot_pass_completeness(tmp_path):
    export = _write_export(
        tmp_path / "source", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows(12)
    )
    index = _write_index(
        tmp_path / "index.json", [_entry("CG-S1-A-001", "boot-1")], valid_s1=["CG-S1-A-001"]
    )
    capture = load_capture(export, a_run_index=index)
    linkage = dataclasses.replace(
        _linkage(capture), planned_capture_duration_s=24.0
    )
    admission = evaluate_admission(capture)
    validation = validate_run(
        capture,
        admission=admission,
        requirement=default_scenario_requirement("S1"),
        manifest_linkage=linkage,
    )
    whole = validation.completeness_for(DIMENSION_WHOLE)
    critical = validation.completeness_for(DIMENSION_CRITICAL)
    assert whole.status == CHECK_FAIL
    assert critical.status == CHECK_FAIL
    assert "CAPTURE_SHORTER_THAN_PLANNED_INTERVAL" in validation.reason_codes
    assert validation.eligibility == ELIGIBILITY_BLOCKED


def test_rows_outside_declared_plan_do_not_inflate_completeness(tmp_path):
    export = _write_export(
        tmp_path / "source", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows(20)
    )
    index = _write_index(
        tmp_path / "index.json", [_entry("CG-S1-A-001", "boot-1")], valid_s1=["CG-S1-A-001"]
    )
    capture = load_capture(export, a_run_index=index)
    linkage = dataclasses.replace(
        _linkage(capture), planned_capture_duration_s=10.0
    )
    admission = evaluate_admission(capture)
    validation = validate_run(
        capture,
        admission=admission,
        requirement=default_scenario_requirement("S1"),
        manifest_linkage=linkage,
    )
    whole = validation.completeness_for(DIMENSION_WHOLE)
    assert whole.expected_samples == 11
    assert whole.observed_samples == 11
    assert whole.fraction == 1.0
    assert whole.status == CHECK_PASS


def test_unresolved_threshold_is_not_evaluated_as_zero(tmp_path):
    export = _write_export(
        tmp_path / "source", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows()
    )
    index = _write_index(
        tmp_path / "index.json", [_entry("CG-S1-A-001", "boot-1")], valid_s1=["CG-S1-A-001"]
    )
    _, _, _, validation = _load_and_validate(export, index)
    timing = validation.completeness_for(DIMENSION_TIMING)
    assert timing.status == CHECK_NOT_EVALUABLE
    assert timing.fraction is None
    assert REASON_THRESHOLD_UNRESOLVED in timing.reason_codes


def test_whole_capture_complete_but_missing_s2_event_is_blocked(tmp_path):
    capture, index = _s2_capture(tmp_path)
    admission = evaluate_admission(capture)
    requirement = default_scenario_requirement(
        "S2", baseline_window_s=4, event_window_s=4, recovery_horizon_s=8
    )
    validation = validate_run(
        capture,
        admission=admission,
        requirement=requirement,
        manifest_linkage=_linkage(capture),
    )
    # Door transitions are extracted from door_open; a door quality of VALID
    # and at least one transition makes the anchor observable. Remove it.
    no_event = dataclasses.replace(
        capture,
        rows=tuple(
            dataclasses.replace(row, door_state="CLOSED") for row in capture.rows
        ),
    )
    admission = evaluate_admission(no_event)
    validation = validate_run(
        no_event,
        admission=admission,
        requirement=requirement,
        manifest_linkage=_linkage(no_event),
    )
    assert REASON_EVENT_ANCHOR_MISSING in validation.reason_codes
    assert validation.eligibility == ELIGIBILITY_BLOCKED


def test_event_window_gap_is_not_hidden_by_whole_run_completeness(tmp_path):
    def door(index: int) -> str:
        return "1" if 8 <= index < 10 else "0"

    export = _write_export(
        tmp_path / "s2",
        run_id="CG-S2-A-001",
        boot_id="s2-boot",
        rows=_rows(120, scenario_key=S2_KEY, door=door, skip_times=set(range(12, 18))),
        scenario_key=S2_KEY,
    )
    index = _write_index(
        tmp_path / "index.json",
        [_entry("CG-S2-A-001", "s2-boot", scenario_key=S2_KEY, rows=114, valid_for=["S2"])],
    )
    capture = load_capture(export, a_run_index=index)
    admission = evaluate_admission(capture)
    requirement = default_scenario_requirement(
        "S2", baseline_window_s=6, event_window_s=8, recovery_horizon_s=20
    )
    validation = validate_run(
        capture,
        admission=admission,
        requirement=requirement,
        manifest_linkage=_linkage(capture),
    )
    event = validation.completeness_for(DIMENSION_EVENT)
    assert event is not None
    assert event.status == CHECK_FAIL
    assert validation.eligibility == ELIGIBILITY_BLOCKED


def test_missing_critical_sensor_in_event_window_blocks(tmp_path):
    def door(index: int) -> str:
        return "1" if 8 <= index < 10 else "0"

    rows = _rows(24, scenario_key=S2_KEY, door=door, thermal_quality="VALID")
    for index in range(8, 14):
        rows[index]["thermal_quality"] = "INVALID"
    export = _write_export(
        tmp_path / "s2",
        run_id="CG-S2-A-001",
        boot_id="s2-boot",
        rows=rows,
        scenario_key=S2_KEY,
    )
    index = _write_index(
        tmp_path / "index.json",
        [_entry("CG-S2-A-001", "s2-boot", scenario_key=S2_KEY, rows=24, valid_for=["S2"])],
    )
    capture = load_capture(export, a_run_index=index)
    admission = evaluate_admission(capture)
    validation = validate_run(
        capture,
        admission=admission,
        requirement=default_scenario_requirement(
            "S2", baseline_window_s=4, event_window_s=8, recovery_horizon_s=12
        ),
        manifest_linkage=_linkage(capture),
    )
    assert REASON_CRITICAL_CHANNEL in validation.reason_codes


def test_valid_zero_electrical_reading_differs_from_missing(tmp_path):
    export = _write_export(
        tmp_path / "source",
        run_id="CG-S1-A-001",
        boot_id="boot-1",
        rows=_rows(power_w="0.0"),
    )
    index = _write_index(
        tmp_path / "index.json", [_entry("CG-S1-A-001", "boot-1")], valid_s1=["CG-S1-A-001"]
    )
    requirement = default_scenario_requirement(
        "S1", requires_electrical_evidence=True
    )
    _, _, _, zero = _load_and_validate(export, index, requirement=requirement)
    assert zero.eligibility == ELIGIBILITY_ELIGIBLE

    missing_rows = _rows(power_w="0.0")
    for row in missing_rows:
        row["power_w"] = "NOT_AVAILABLE"
        row["electrical_quality"] = "INVALID"
    export_missing = _write_export(
        tmp_path / "missing",
        run_id="CG-S1-A-002",
        boot_id="boot-2",
        rows=missing_rows,
    )
    index_missing = _write_index(
        tmp_path / "index2.json",
        [_entry("CG-S1-A-002", "boot-2")],
        valid_s1=["CG-S1-A-002"],
    )
    _, _, _, missing = _load_and_validate(
        export_missing, index_missing, requirement=requirement
    )
    assert missing.eligibility == ELIGIBILITY_BLOCKED
    assert "PZEM_NOT_QUALIFIED_FOR_ELECTRICAL_CLAIM" in missing.reason_codes


def test_censored_recovery_window_blocks(tmp_path):
    capture, index = _s2_capture(tmp_path, count=12, anchor=8)
    admission = evaluate_admission(capture)
    requirement = default_scenario_requirement(
        "S2", baseline_window_s=4, event_window_s=4, recovery_horizon_s=20
    )
    validation = validate_run(
        capture,
        admission=admission,
        requirement=requirement,
        manifest_linkage=_linkage(capture),
    )
    assert validation.event_coverage.censored is True
    assert validation.eligibility == ELIGIBILITY_BLOCKED


def test_command_chain_requirement_is_scenario_dependent(tmp_path):
    export = _write_export(
        tmp_path / "source", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows()
    )
    index = _write_index(
        tmp_path / "index.json", [_entry("CG-S1-A-001", "boot-1")], valid_s1=["CG-S1-A-001"]
    )
    passive = default_scenario_requirement("S1")
    _, _, _, passive_validation = _load_and_validate(
        export, index, requirement=passive
    )
    command = next(
        check
        for check in passive_validation.checks
        if check.code == "COMMAND_CHAIN_COMPLETE_IF_REQUIRED"
    )
    assert command.status == CHECK_NOT_EVALUABLE
    assert passive_validation.eligibility == ELIGIBILITY_ELIGIBLE
    required = default_scenario_requirement("S1", requires_command_chain=True)
    _, _, _, required_validation = _load_and_validate(
        export, index, requirement=required
    )
    assert required_validation.eligibility == ELIGIBILITY_BLOCKED
    assert "REQUIRED_COMMAND_CHAIN_ABSENT" in required_validation.reason_codes


def test_non_monotonic_sequence_is_detected(tmp_path):
    export = _write_export(
        tmp_path / "source", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows()
    )
    index = _write_index(
        tmp_path / "index.json", [_entry("CG-S1-A-001", "boot-1")], valid_s1=["CG-S1-A-001"]
    )
    capture = load_capture(export, a_run_index=index)
    reversed_capture = dataclasses.replace(capture, rows=tuple(reversed(capture.rows)))
    admission = evaluate_admission(reversed_capture)
    validation = validate_run(
        reversed_capture,
        admission=admission,
        requirement=default_scenario_requirement("S1"),
        manifest_linkage=_linkage(reversed_capture),
    )
    assert "SEQUENCE_MONOTONIC" in {
        check.code for check in validation.blocking_failures
    }


# ---------------------------------------------------------------------------
# gate decisions
# ---------------------------------------------------------------------------


def test_true_green_synthetic_contract_fixture_passes(tmp_path):
    report, validations, _ = _green_suite(tmp_path)
    assert all(item.eligibility == ELIGIBILITY_ELIGIBLE for item in validations)
    assert report.software_gate.observed_status == "GREEN"
    assert report.physical_gate.observed_status == "GREEN"
    assert report.predictive_gate.observed_status == "READY"
    assert report.split_plan.feasibility == SPLIT_PROVISIONAL
    assert report.split_gate.observed_status in ("YELLOW", "GREEN")


def test_hard_red_cannot_be_overridden_by_green_support(tmp_path):
    good_export = _write_export(
        tmp_path / "good", run_id="CG-S1-A-001", boot_id="boot-1", rows=_rows()
    )
    bad_export = _write_export(
        tmp_path / "bad", run_id="CG-S1-A-002", boot_id="boot-2", rows=_rows()
    )
    index = _write_index(
        tmp_path / "index.json",
        [_entry("CG-S1-A-001", "boot-1"), _entry("CG-S1-A-002", "boot-2")],
        valid_s1=["CG-S1-A-001"],
        blocked=[
            {
                "run_id": "CG-S1-A-002",
                "boot_id": "boot-2",
                "device_run_label": "TEST_RUN",
                "usable_fraction": 0.0,
                "reasons": ["TEST_INVALID"],
            }
        ],
    )
    validations, admissions = [], []
    for export in (good_export, bad_export):
        capture = load_capture(export, a_run_index=index)
        admission = evaluate_admission(capture)
        admissions.append(admission)
        validations.append(
            validate_run(
                capture,
                admission=admission,
                requirement=default_scenario_requirement("S1"),
                manifest_linkage=_linkage(capture),
            )
        )
    report = build_gate_b_report(
        validations, admissions, default_scenario_requirement("S1")
    )
    assert report.physical_gate.observed_status == "RED"
    assert REASON_AUTHORITY_INVALID in report.physical_gate.reason_codes


def test_zero_qualified_runs_is_red():
    report, _, _ = _real_report()
    assert report.physical_gate.observed_status == "RED"
    assert report.predictive_gate.observed_status == "NOT_READY"
    assert report.split_plan.feasibility == SPLIT_NOT_FEASIBLE
    assert report.eligible_runs == ()


def test_status_and_reason_codes_are_permutation_invariant(tmp_path):
    report, validations, admissions = _green_suite(tmp_path)
    requirement = default_scenario_requirement("S1")
    left = assess_gate_b(validations, admissions, requirement)
    right = assess_gate_b(
        list(reversed(validations)), list(reversed(admissions)), requirement
    )
    assert [gate.to_dict() for gate in left] == [gate.to_dict() for gate in right]


def test_report_csv_and_manifest_agree(tmp_path):
    report, _, _ = _green_suite(tmp_path)
    report_text = render_readiness_report(
        report,
        code_sha256="a" * 64,
        repository_revision="test",
        generation_command="test",
    )
    csv_text = run_validation_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    manifest = json.loads(
        build_gate_manifest(
            report,
            code_sha256="a" * 64,
            repository_revision="test",
            generation_command="test",
            artifact_sha256={"run-validation-W08.csv": "b" * 64},
        )
    )
    assert len(rows) == len(report.validations)
    assert manifest["physical_gate"]["observed_status"] == "GREEN"
    assert manifest["split_plan"]["feasibility"] == SPLIT_PROVISIONAL
    assert manifest["runs"][0]["eligibility"] == ELIGIBILITY_ELIGIBLE
    assert "GATE_B_PHYSICAL_DATA" in report_text
    assert "P1 training ∪ P2 held-back validation" in render_split_plan(
        report.split_plan
    )
    policy_text = render_completeness_policy(report.policy)
    assert "WHOLE_CAPTURE_COMPLETENESS" in policy_text
    assert "UNRESOLVED" in policy_text


def test_real_a_w09_result_remains_scientifically_blocked():
    report, _, _ = _real_report()
    run = report.validations[0]
    assert run.a_ledger_verdict == "INVALID"
    assert run.eligibility == ELIGIBILITY_BLOCKED
    for code in (
        REASON_AUTHORITY_INVALID,
        "DEVICE_IDENTITY_MISSING",
        "HARDWARE_CONFIG_NOT_VERIFIED",
        "CALIBRATION_UNVERIFIED",
    ):
        assert code in run.reason_codes
    assert report.physical_gate.observed_status == "RED"
    assert report.predictive_gate.observed_status == "NOT_READY"
    assert report.split_plan.feasibility == SPLIT_NOT_FEASIBLE
    assert report.split_plan.p1_training == ()


def _real_report():
    capture = load_capture(REAL_A_EXPORT, a_run_index=REAL_A_INDEX)
    admission = evaluate_admission(capture)
    qa = analyze_capture(capture, admission=admission, config=QAConfig())
    validation = validate_run(
        capture,
        admission=admission,
        qa=qa,
        requirement=default_scenario_requirement("S1"),
        manifest_linkage=None,
    )
    report = build_gate_b_report(
        [validation],
        [admission],
        default_scenario_requirement("S1"),
        w07_evidence={"verdict": "NOT_ESTABLISHED", "qualified_independent_runs": 0},
    )
    return report, [validation], [admission]


# ---------------------------------------------------------------------------
# grouped split planning
# ---------------------------------------------------------------------------


def _candidate(
    run_id: str,
    *,
    source: str | None = None,
    pair_id: str | None = None,
    eligible: bool = True,
    scenario: str = "S1",
):
    return SplitCandidate(
        run_id=run_id,
        scenario_id=scenario,
        controller_id="OBSERVATIONAL",
        physical_source_key=("session", "dev-A", source or run_id),
        pair_id=pair_id,
        hardware_config_id="CG-HW-001",
        eligible=eligible,
        reason="ELIGIBLE" if eligible else "INVALID",
        source_path=f"{run_id}.json",
        source_sha256=hashlib.sha256(run_id.encode()).hexdigest(),
    )


def test_split_partitions_are_disjoint_and_development_is_union():
    candidates = [_candidate(f"CG-S1-A-{index:03d}") for index in range(1, 7)]
    plan = plan_development_split(candidates)
    assert plan.feasibility == SPLIT_PROVISIONAL
    p1, p2, p3 = (
        set(plan.p1_training),
        set(plan.p2_held_back_development_validation),
        set(plan.p3_future_locked_planning_candidates),
    )
    assert p1.isdisjoint(p2) and p1.isdisjoint(p3) and p2.isdisjoint(p3)
    assert p1 | p2 | p3 == {candidate.run_id for candidate in candidates}
    assert set(plan.development_runs) == p1 | p2
    assert plan.p3_status.endswith("NOT_A_LOCKED_TEST")


def test_pair_lineage_never_straddles_partitions():
    candidates = [
        _candidate("A1", pair_id="PAIR-1"),
        _candidate("B1", pair_id="PAIR-1"),
        _candidate("A2", pair_id="PAIR-2"),
        _candidate("B2", pair_id="PAIR-2"),
        _candidate("A3", pair_id="PAIR-3"),
        _candidate("B3", pair_id="PAIR-3"),
    ]
    plan = plan_development_split(candidates)
    assert plan.feasibility == SPLIT_PROVISIONAL
    for entry in plan.pair_lineage:
        partition = entry["partition"]
        members = set(entry["run_ids"])
        for name in ("p1_training", "p2_held_back_development_validation", "p3_future_locked_planning_candidates"):
            assigned = set(getattr(plan, name))
            assert members.isdisjoint(assigned) or members <= assigned
        assert members


def test_repeated_views_of_one_run_stay_one_group():
    candidates = [
        _candidate("CG-S1-A-001", source="source-A"),
        _candidate("CG-S1-A-001", source="source-A"),
        _candidate("CG-S1-A-002", source="source-B"),
        _candidate("CG-S1-A-003", source="source-C"),
    ]
    plan = plan_development_split(candidates)
    assert plan.candidate_count == 4
    assert len(plan.p1_training) + len(plan.p2_held_back_development_validation) + len(
        plan.p3_future_locked_planning_candidates
    ) == 3
    assert any(
        "REPEATED_VIEW" in item["reason"] for item in plan.excluded
    )


def test_contradictory_run_ids_on_one_source_cannot_leak():
    candidates = [
        _candidate("CG-S1-A-001", source="source-A"),
        _candidate("CG-S1-A-002", source="source-A"),
        _candidate("CG-S1-A-003", source="source-B"),
        _candidate("CG-S1-A-004", source="source-C"),
        _candidate("CG-S1-A-005", source="source-D"),
    ]
    plan = plan_development_split(candidates)
    grouped = set(plan.p1_training) | set(plan.p2_held_back_development_validation) | set(
        plan.p3_future_locked_planning_candidates
    )
    assert "CG-S1-A-001" not in grouped
    assert "CG-S1-A-002" not in grouped
    assert plan.feasibility == SPLIT_PROVISIONAL
    assert any("CONTRADICTORY_RUN_IDENTITIES" in item["reason"] for item in plan.excluded)


def test_insufficient_population_is_not_feasible():
    for count in (0, 1, 2):
        plan = plan_development_split(
            [_candidate(f"CG-S1-A-{index:03d}") for index in range(1, count + 1)]
        )
        assert plan.feasibility == SPLIT_NOT_FEASIBLE
        assert plan.p1_training == ()
        assert plan.p2_held_back_development_validation == ()
        assert plan.p3_future_locked_planning_candidates == ()


def test_synthetic_control_is_flagged_and_never_physical_readiness():
    plan = plan_development_split(
        [_candidate(f"SYN-{index}") for index in range(1, 4)],
        synthetic_control=True,
    )
    assert plan.synthetic_control is True
    assert plan.feasibility == SPLIT_PROVISIONAL
    assert plan.p3_status.endswith("NOT_A_LOCKED_TEST")


# ---------------------------------------------------------------------------
# CLI behavior
# ---------------------------------------------------------------------------


def _run_cli(arguments, cwd=ML_ROOT):
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_cli_help():
    result = _run_cli(["--help"])
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()
    assert "Gate B dataset readiness" in result.stdout


def test_cli_invalid_configuration_is_exit_1():
    result = _run_cli(
        ["--source", str(REAL_A_EXPORT), "--min-runs", "0"]
    )
    assert result.returncode == 1
    assert "INVALID CONFIGURATION" in result.stderr


def test_cli_missing_required_argument_is_exit_1():
    result = _run_cli([])
    assert result.returncode == 1
    assert "INVALID CONFIGURATION" in result.stderr


def test_cli_malformed_index_is_refused_exit_2(tmp_path):
    bad_index = tmp_path / "bad-index.json"
    bad_index.write_text("{not-json", encoding="utf-8")
    result = _run_cli(
        [
            "--source",
            str(REAL_A_EXPORT),
            "--a-run-index",
            str(bad_index),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert result.returncode == 2
    assert "SOURCE REFUSED" in result.stderr
    assert not (tmp_path / "out").exists()


def test_cli_refused_source_is_exit_2(tmp_path):
    result = _run_cli(
        ["--source", str(REPO_ROOT / "evidence/A/W07/README.md"), "--out", str(tmp_path)]
    )
    assert result.returncode == 2
    assert "SOURCE REFUSED" in result.stderr


def test_cli_real_source_exits_0_with_red_gate_and_writes_artifacts(tmp_path):
    result = _run_cli(
        [
            "--source",
            str(REAL_A_EXPORT),
            "--a-run-index",
            str(REAL_A_INDEX),
            "--out",
            str(tmp_path / "w08"),
            "--repository-revision",
            "test-revision",
        ]
    )
    assert result.returncode == 0, result.stderr
    output = tmp_path / "w08"
    assert {
        "gate-b-readiness-W08.md",
        "run-validation-W08.csv",
        "completeness-policy-W08.md",
        "development-split-plan-W08.md",
        "gate-b-manifest-W08.json",
    } == {path.name for path in output.iterdir()}
    manifest = json.loads(
        (output / "gate-b-manifest-W08.json").read_text(encoding="utf-8")
    )
    assert manifest["physical_gate"]["observed_status"] == "RED"
    assert manifest["predictive_gate"]["observed_status"] == "NOT_READY"
    assert manifest["split_plan"]["feasibility"] == SPLIT_NOT_FEASIBLE
    assert manifest["source_index_sha256"]
    for name, digest in manifest["artifact_sha256"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    rows = list(
        csv.DictReader(
            io.StringIO((output / "run-validation-W08.csv").read_text(encoding="utf-8"))
        )
    )
    assert rows[0]["b_eligibility"] == "BLOCKED"
    assert rows[0]["a_ledger_verdict"] == "INVALID"


def test_cli_deterministic_replay(tmp_path):
    arguments = [
        "--source",
        str(REAL_A_EXPORT),
        "--a-run-index",
        str(REAL_A_INDEX),
        "--out",
        str(tmp_path / "w08"),
        "--repository-revision",
        "replay-test",
    ]
    first = _run_cli(arguments)
    assert first.returncode == 0, first.stderr
    output = tmp_path / "w08"
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in output.iterdir()
    }
    second = _run_cli(arguments)
    assert second.returncode == 0, second.stderr
    assert hashes == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in output.iterdir()
    }


def test_no_model_training_or_locked_test_access_in_w08_module():
    text = (ML_ROOT / "src" / "coldguard_ml" / "data_readiness.py").read_text(
        encoding="utf-8"
    )
    lowered = text.lower()
    for token in (
        "import sklearn",
        "from sklearn",
        "import xgboost",
        "from xgboost",
        "train_test_split",
        "model.fit",
        "locked_test_manifest",
    ):
        assert token not in lowered
