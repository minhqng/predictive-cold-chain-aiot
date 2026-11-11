"""B-W04-01 / B-W04-05 adversarial regressions.

Programmatic cases use explicit synthetic fixtures; the two integration
references are real, committed A evidence used read-only:

* ``evidence/A/W09/exports/CG-S1-H8C-600S.json`` plus its companion CSV;
* ``evidence/A/W09/s1-run-index.json`` (the authoritative A hand-off).

No fixture here is presented as a certified physical run.
"""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from coldguard_ml import (
    AdmissionResult,
    AdmissionStage,
    RunInfo,
    SourceRefusal,
    SplitConfig,
    SplitProportions,
    SyntheticRunSpec,
    build_synthetic_runs,
    chamber_air_mean,
    split_runs,
    classify_source,
    count_independent_runs,
    detect_source_format,
    evaluate_admission,
    load_capture,
    summarize_readiness,
)
from coldguard_ml.intake import (
    A_REQUIRED_ROW_COLUMNS,
    A_W09_EXPORT_VERSION,
    RoleError,
    SOURCE_FORMAT_A_W09_EXPORT,
    SOURCE_FORMAT_C_TELEMETRY_V1,
    SOURCE_FORMAT_H8S_SERIAL_V3,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_A_EXPORT = REPO_ROOT / "evidence/A/W09/exports/CG-S1-H8C-600S.json"
REAL_A_INDEX = REPO_ROOT / "evidence/A/W09/s1-run-index.json"
C_FIXTURE = REPO_ROOT / "backend/fixtures/telemetry_v0.json"
SCHEMA_CHECK = REPO_ROOT / "ml/scripts/schema-check.py"

A_HEADER = list(
    dict.fromkeys(
        [
            "seq",
            "run_id",
            "boot_id",
            "device_id",
            "hardware_config_id",
            "firmware_version",
            "device_ms",
            "timestamp_utc",
            "timestamp_utc_status",
            "host_capture_time_utc",
            "source_line_index",
            "dedup_key",
            "experiment_phase",
            "quality",
            "usable_for",
            "producer_quality",
            "thermal_quality",
            "environment_quality",
            "electrical_quality",
            "door_quality",
            "sequence_quality",
            "provenance_quality",
            "invalidation_reasons",
            "stage",
            "state",
            "stop_reason",
            "snapshot",
            "pwm_req_permille",
            "pwm_applied_permille",
            "pwm_readback_permille",
            "door_open",
            "door_polarity",
            *[
                f"{slot}{suffix}"
                for slot in ("t1", "t2", "t3", "t4")
                for suffix in (
                    "",
                    "_status",
                    "_role",
                    "_age_ms",
                    "_rom",
                    "_physical_position",
                )
            ],
            "air_c",
            "rh_pct",
            "pressure_hpa",
            "voltage_v",
            "current_a",
            "power_w",
            "energy_wh",
            *A_REQUIRED_ROW_COLUMNS,
        ]
    )
)

SENSORS = [
    {
        "raw_slot": "t1",
        "rom": "287088CA00000051",
        "rom_source": "TEST_FIXTURE",
        "rom_readback_verified": False,
        "physical_position": "CHAMBER_CENTER",
        "position_source": "TEST_FIXTURE",
        "raw_role_in_capture": ["UNASSIGNED"],
        "in_chamber_air_mean": True,
        "exclusion_reason": "",
    },
    {
        "raw_slot": "t2",
        "rom": "28AEBF2200000006",
        "rom_source": "TEST_FIXTURE",
        "rom_readback_verified": False,
        "physical_position": "TEC_HOT_SIDE",
        "position_source": "TEST_FIXTURE",
        "raw_role_in_capture": ["HOT_SIDE"],
        "in_chamber_air_mean": False,
        "exclusion_reason": "TEC_HOT_SIDE is a heatsink, not chamber air",
    },
    {
        "raw_slot": "t3",
        "rom": "28CBE9CA00000072",
        "rom_source": "TEST_FIXTURE",
        "rom_readback_verified": False,
        "physical_position": "CHAMBER_BOTTOM",
        "position_source": "TEST_FIXTURE",
        "raw_role_in_capture": ["UNASSIGNED"],
        "in_chamber_air_mean": True,
        "exclusion_reason": "",
    },
    {
        "raw_slot": "t4",
        "rom": "283BE5C9000000A9",
        "rom_source": "TEST_FIXTURE",
        "rom_readback_verified": False,
        "physical_position": "CHAMBER_NEAR_DOOR",
        "position_source": "TEST_FIXTURE",
        "raw_role_in_capture": ["UNASSIGNED"],
        "in_chamber_air_mean": True,
        "exclusion_reason": "",
    },
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _default_row(
    index: int,
    *,
    rows_run_id: str,
    boot_id: str,
    device_id: str,
    sensors: list[dict],
) -> dict[str, str]:
    positions = {sensor["raw_slot"]: sensor for sensor in sensors}
    row = {
        "seq": str(index),
        "run_id": rows_run_id,
        "boot_id": boot_id,
        "device_id": device_id,
        "hardware_config_id": "CG-HW-001",
        "firmware_version": "fw-test",
        "device_ms": str(index * 1000),
        "timestamp_utc": "NOT_AVAILABLE",
        "timestamp_utc_status": "UNAVAILABLE",
        "host_capture_time_utc": "NOT_AVAILABLE",
        "source_line_index": str(index + 1),
        "dedup_key": f"{device_id}|{boot_id}|{index}",
        "experiment_phase": "OFF_IDLE",
        "quality": "UNKNOWN",
        "usable_for": "NONE",
        "producer_quality": "DEGRADED",
        "thermal_quality": "VALID",
        "environment_quality": "UNKNOWN",
        "electrical_quality": "UNKNOWN",
        "door_quality": "UNKNOWN",
        "sequence_quality": "VALID",
        "provenance_quality": "VALID",
        "invalidation_reasons": "NONE",
        "stage": "OFF",
        "state": "OFF",
        "stop_reason": "NONE",
        "snapshot": "VALID",
        "pwm_req_permille": "0",
        "pwm_applied_permille": "0",
        "pwm_readback_permille": "0",
        "door_open": "0",
        "door_polarity": "CONFIRMED",
        "t1": "20.0",
        "t2": "35.0",
        "t3": "20.1",
        "t4": "20.2",
        "air_c": "20.0",
        "rh_pct": "50.0",
        "pressure_hpa": "1013.0",
        "voltage_v": "12.0",
        "current_a": "0.0",
        "power_w": "0.0",
        "energy_wh": "1.0",
    }
    for slot in ("t1", "t2", "t3", "t4"):
        row[f"{slot}_status"] = "OK"
        row[f"{slot}_role"] = "HOT_SIDE" if slot == "t2" else "UNASSIGNED"
        row[f"{slot}_age_ms"] = "1"
        row[f"{slot}_rom"] = positions[slot]["rom"]
        row[f"{slot}_physical_position"] = positions[slot]["physical_position"]
    return row


def write_a_export(
    tmp_path: Path,
    rows: list[dict[str, str]] | None = None,
    *,
    sensors: list[dict] | None = None,
    run_id: str | None = "CG-S1-A-001",
    run_id_status: str = "SOURCE_CARRIED_SINGLE",
    run_ids: list[str] | None = None,
    boot_id: str | None = "boot-test",
    boot_id_status: str = "SOURCE_CARRIED_SINGLE",
    boot_ids: list[str] | None = None,
    device_id: str | None = "cg-test-001",
    calibration_id: str | None = None,
    scenario_candidate: str = "S1_NORMAL_BASELINE",
    is_physical: bool = True,
    invalidation_summary: dict | None = None,
    timestamp_semantics: dict | None = None,
    extra_export: dict | None = None,
) -> Path:
    sensors = sensors or SENSORS
    rows = rows or [{}]
    # A repository marker makes the pinned source verifiable in the fixture,
    # exactly as it is in a real checkout (test-only marker).
    (tmp_path / ".git").mkdir(exist_ok=True)
    source = tmp_path / "source.csv"
    source.write_text("source-a,source-b\n1,2\n", encoding="utf-8")
    source_sha = _sha256(source)
    if run_ids is None:
        run_ids = [run_id] if run_id is not None else []
    if boot_ids is None:
        boot_ids = [boot_id] if boot_id is not None else []
    row_run_id = run_id or (run_ids[0] if run_ids else "")
    row_boot_id = boot_id or (boot_ids[0] if boot_ids else "")
    materialized: list[dict[str, str]] = []
    for index, override in enumerate(rows, start=1):
        row = _default_row(
            index,
            rows_run_id=row_run_id,
            boot_id=row_boot_id,
            device_id=device_id or "NOT_CARRIED_BY_THIS_ENCODING",
            sensors=sensors,
        )
        row.update({key: str(value) for key, value in override.items()})
        materialized.append(row)
    companion = tmp_path / "rows.csv"
    with companion.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=A_HEADER)
        writer.writeheader()
        writer.writerows(materialized)
    if invalidation_summary is None:
        invalidation_summary = {
            "rows_total": len(materialized),
            "rows_usable_per_scenario": {
                "S1_NORMAL_BASELINE": 0,
                "S2_DOOR_DISTURBANCE": 0,
            },
            "scenario_required_domains": {
                "S1_NORMAL_BASELINE": [
                    "provenance",
                    "producer",
                    "thermal",
                    "environment",
                    "door",
                    "sequence",
                ],
                "S2_DOOR_DISTURBANCE": [
                    "provenance",
                    "producer",
                    "thermal",
                    "door",
                    "sequence",
                ],
            },
            "reason_counts": {"TEST_REASON": len(materialized)},
            "usable_fraction": 0.0,
        }
    export = {
        "run_id": run_id,
        "run_id_status": run_id_status,
        "run_ids": list(run_ids),
        "boot_id": boot_id,
        "boot_id_status": boot_id_status,
        "boot_ids": list(boot_ids),
        "device_run_label": "TEST_RUN",
        "device_id": device_id or "NOT_CARRIED_BY_THIS_ENCODING",
        "hardware_config_id": "CG-HW-001",
        "firmware_version": "fw-test",
        "schema_version": None,
        "calibration_id": calibration_id,
        "scenario_candidate": scenario_candidate,
        "scenario_candidate_basis": "test fixture",
        "experiment_phase": {},
        "sensors": sensors,
        "timestamp_semantics": timestamp_semantics
        or {
            "timestamp_utc_status": "UNAVAILABLE",
            "timestamp_utc_source": "DEVICE_HAS_NO_WALL_CLOCK",
            "measurement_time_axis": "DEVICE_UPTIME_MS",
        },
        "uptime_semantics": {},
        "cadence": {},
        "frames": {
            "companion_file": "rows.csv",
            "columns_per_row": A_HEADER,
            "rows": len(materialized),
        },
        "row_contract": {
            "not_available_per_row": {
                "timestamp_utc": "NOT AVAILABLE (DEVICE_HAS_NO_WALL_CLOCK)"
            }
        },
        "per_field_quality": {},
        "invalidation": {"summary": invalidation_summary, "policy": "test"},
        "derived_thermal_states": {},
        "provenance": {
            "sources": [
                {
                    "path": "source.csv",
                    "sha256": source_sha,
                    "source_kind": "test",
                    "is_physical_measurement": is_physical,
                    "run_label": "TEST_RUN",
                    "repo_tracked": False,
                }
            ]
        },
        "is_physical_measurement": is_physical,
        "status_label": "TEST_FIXTURE",
        "export_version": A_W09_EXPORT_VERSION,
    }
    if extra_export:
        export.update(extra_export)
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_c_variant(tmp_path: Path, **overrides: object) -> Path:
    payload = json.loads(C_FIXTURE.read_text(encoding="utf-8"))
    payload.update(overrides)
    path = tmp_path / "telemetry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _positive_export(
    tmp_path: Path,
    *,
    scenario_candidate: str = "S1_NORMAL_BASELINE",
    scenario_key: str = "S1_NORMAL_BASELINE",
) -> Path:
    return write_a_export(
        tmp_path,
        rows=[
            {
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "timestamp_utc_status": "SYNCED",
                "usable_for": scenario_key,
                "quality": "VALID",
                "producer_quality": "VALID",
                "environment_quality": "VALID",
                "electrical_quality": "VALID",
                "door_quality": "VALID",
                "invalidation_reasons": "NONE",
            }
        ],
        scenario_candidate=scenario_candidate,
        calibration_id="CG-CAL-001",
        timestamp_semantics={
            "timestamp_utc_status": "SYNCED",
            "timestamp_utc_source": "DEVICE_CLOCK_SYNCED",
            "measurement_time_axis": "DEVICE_UTC",
        },
        invalidation_summary={
            "rows_total": 1,
            "rows_usable_per_scenario": {scenario_key: 1},
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


def _positive_index(
    tmp_path: Path,
    *,
    valid: bool = True,
    scenario_key: str = "S1_NORMAL_BASELINE",
    entry_extra: dict | None = None,
) -> Path:
    entry = {
        "run_id": "CG-S1-A-001",
        "boot_id": "boot-test",
        "device_run_label": "TEST_RUN",
        "frames_total": 1,
        "frames_usable_per_scenario": {scenario_key: 1},
        "top_invalidation_reasons": {},
        "usable_fraction": 1.0,
        "hardware_config_verified": True,
        "calibration_verified": True,
        "clock_sync_verified": True,
    }
    if entry_extra:
        entry.update(entry_extra)
    payload = {
        "index_version": "w09-run-index-v1",
        "runs": [entry],
        "valid_s1_run_ids_for_member_b": ["CG-S1-A-001"] if valid else [],
        "blocked_run_ids": (
            []
            if valid
            else [
                {
                    "run_id": "CG-S1-A-001",
                    "boot_id": "boot-test",
                    "device_run_label": "TEST_RUN",
                    "usable_fraction": 1.0,
                    "reasons": ["TEST_LEDGER_INVALID_WITH_PLAUSIBLE_READINGS"],
                }
            ]
        ),
    }
    path = tmp_path / "index.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# schema, roles and provenance
# ---------------------------------------------------------------------------


def test_valid_c_fixture_is_structurally_accepted_but_synthetic() -> None:
    capture = load_capture(C_FIXTURE)
    assert capture.source.format == SOURCE_FORMAT_C_TELEMETRY_V1
    assert capture.source.schema_namespace == "coldguard.telemetry/v1"
    assert capture.source.provenance == "SYNTHETIC"
    assert len(capture.rows) == 1
    admission = evaluate_admission(capture)
    assert admission.highest_stage is AdmissionStage.USABLE_FOR_DIAGNOSTIC_QA
    assert not admission.eligible


def test_legacy_dual_branch_fields_are_rejected(tmp_path: Path) -> None:
    payload = json.loads(C_FIXTURE.read_text(encoding="utf-8"))
    payload["current_1"] = 1.0
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(path)
    assert excinfo.value.code == "LEGACY_FORBIDDEN_FIELD"

    a_dir = tmp_path / "a"
    a_dir.mkdir()
    a_path = write_a_export(a_dir)
    a_payload = json.loads(a_path.read_text(encoding="utf-8"))
    a_payload["second_tec"] = {"present": True}
    a_path.write_text(json.dumps(a_payload), encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(a_path)
    assert excinfo.value.code == "LEGACY_FORBIDDEN_FIELD"


def test_unsupported_source_versions_are_rejected(tmp_path: Path) -> None:
    c_path = _write_c_variant(tmp_path, schema_version=2)
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(c_path)
    assert excinfo.value.code == "UNSUPPORTED_SOURCE_VERSION"

    export = json.loads(REAL_A_EXPORT.read_text(encoding="utf-8"))
    export["export_version"] = "w09-run-export-v999"
    a_path = tmp_path / "export.json"
    a_path.write_text(json.dumps(export), encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(a_path)
    assert excinfo.value.code == "UNSUPPORTED_SOURCE_VERSION"

    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(C_FIXTURE, source_format=SOURCE_FORMAT_A_W09_EXPORT)
    assert excinfo.value.code == "SOURCE_FORMAT_MISMATCH"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("thermal", "t1"), "8.5"),
        (("thermal", "t1"), True),
        (("electrical", "power_w"), "12.5"),
        (("actuation", "duty"), False),
        (("seq",), "1"),
        (("uptime_ms",), "1234567"),
        (("device_id",), 123),
        (("door", "state"), 1),
        (("quality", "thermal"), 1),
    ],
)
def test_c_json_wire_types_are_not_coerced(
    tmp_path: Path, path: tuple[str, ...], value: object
) -> None:
    payload = json.loads(C_FIXTURE.read_text(encoding="utf-8"))
    node = payload
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    source = tmp_path / "wire-type.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(source)
    assert excinfo.value.code == "C_TELEMETRY_WIRE_TYPE"
    assert ".".join(path) in excinfo.value.detail


def test_c_json_nullable_measurement_stays_nullable(tmp_path: Path) -> None:
    payload = json.loads(C_FIXTURE.read_text(encoding="utf-8"))
    payload["thermal"]["t1"] = None
    payload["quality"]["thermal"] = "DEGRADED"
    source = tmp_path / "nullable.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    capture = load_capture(source)
    assert capture.rows[0].t1_c is None
    assert capture.rows[0].probe("t1").value_c is None


def test_a_csv_numeric_text_keeps_its_source_encoding(tmp_path: Path) -> None:
    export = write_a_export(
        tmp_path,
        rows=[{"t1": "7.1", "power_w": "12.5", "electrical_quality": "DEGRADED"}],
    )
    capture = load_capture(export)
    row = capture.rows[0]
    assert row.t1_c == pytest.approx(7.1)
    assert row.cooling_power_w == pytest.approx(12.5)


def test_serial_and_backend_wire_namespaces_are_not_conflated(
    tmp_path: Path,
) -> None:
    serial = tmp_path / "h8s.log"
    serial.write_text(
        "#CG H8S schema=3 seq=1 timestamp_utc=UNAVAILABLE "
        "timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK device_ms=1 "
        "boot_id=b run_id=r stage=OFF state=OFF snapshot=VALID\n",
        encoding="utf-8",
    )
    assert detect_source_format(serial) == SOURCE_FORMAT_H8S_SERIAL_V3
    assert detect_source_format(C_FIXTURE) == SOURCE_FORMAT_C_TELEMETRY_V1
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(serial)
    assert excinfo.value.code == "SERIAL_SCHEMA_NOT_BACKEND_WIRE"
    assert "schema_version=1" in excinfo.value.detail

    telem = tmp_path / "telem.log"
    telem.write_text("#CG TELEM schema=3 seq=1\n", encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(telem)
    assert excinfo.value.code == "SERIAL_SCHEMA_NOT_BACKEND_WIRE"


def test_hot_side_probe_cannot_enter_chamber_air_aggregate() -> None:
    capture = load_capture(REAL_A_EXPORT, a_run_index=REAL_A_INDEX)
    assert capture.chamber_air_slots == ("t1", "t3", "t4")
    assert capture.hot_side_slots == ("t2",)
    row = capture.rows[0]
    assert chamber_air_mean(capture, row) == pytest.approx(
        (row.t1_c + row.t3_c + row.probe("t4").value_c) / 3.0
    )
    with pytest.raises(RoleError, match="not in the chamber-air aggregate"):
        chamber_air_mean(capture, row, slots=("t1", "t2", "t3"))


def test_unknown_role_cannot_be_silently_reassigned(tmp_path: Path) -> None:
    sensors = [dict(sensor) for sensor in SENSORS]
    sensors[1]["physical_position"] = "UNKNOWN"
    sensors[1]["in_chamber_air_mean"] = False
    path = write_a_export(tmp_path, sensors=sensors)
    capture = load_capture(path)
    assert "t2" in capture.unknown_role_slots
    admission = evaluate_admission(capture)
    assert "SENSOR_ROLE_UNKNOWN" in {blocker.code for blocker in admission.blockers}
    with pytest.raises(RoleError):
        chamber_air_mean(capture, capture.rows[0], slots=("t1", "t2"))

    invalid = [dict(sensor) for sensor in SENSORS]
    invalid[1]["physical_position"] = "UNKNOWN"
    invalid[1]["in_chamber_air_mean"] = True
    invalid_dir = tmp_path / "invalid"
    invalid_dir.mkdir()
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(write_a_export(invalid_dir, sensors=invalid))
    assert excinfo.value.code == "CHAMBER_AIR_ROLE_UNKNOWN"


def test_missing_calibration_and_config_are_not_synthesized() -> None:
    capture = load_capture(REAL_A_EXPORT, a_run_index=REAL_A_INDEX)
    assert capture.run.calibration_id is None
    assert capture.run.calibration_status == "NOT_AVAILABLE"
    assert capture.run.hardware_config_id == "CG-HW-001"
    assert capture.run.hardware_config_status == "DECLARED_NOT_VERIFIED"
    codes = {blocker.code for blocker in evaluate_admission(capture).blockers}
    assert "CALIBRATION_IDENTITY_MISSING" in codes
    assert "HARDWARE_CONFIG_UNVERIFIED" in codes


def test_missing_pzem_value_is_not_zero(tmp_path: Path) -> None:
    path = write_a_export(
        tmp_path,
        rows=[
            {
                "power_w": "NOT_AVAILABLE",
                "current_a": "NOT_AVAILABLE",
                "electrical_quality": "DEGRADED",
            },
            {
                "power_w": "0.0",
                "current_a": "0.0",
                "electrical_quality": "DEGRADED",
            },
        ],
    )
    capture = load_capture(path)
    missing = capture.rows[0]
    measured_zero = capture.rows[1]
    assert missing.cooling_power_w is None
    assert missing.cooling_current_a is None
    assert "power_w" not in missing.electrical_measured_fields
    assert measured_zero.cooling_power_w == 0.0
    assert measured_zero.cooling_current_a == 0.0
    assert "power_w" in measured_zero.electrical_measured_fields
    assert dict(missing.quality)["electrical"] == "DEGRADED"
    assert dict(measured_zero.quality)["electrical"] == "DEGRADED"


def test_measured_zero_and_missing_are_distinct_values(tmp_path: Path) -> None:
    path = write_a_export(
        tmp_path,
        rows=[{"power_w": "NOT_AVAILABLE"}, {"power_w": "0.0"}],
    )
    capture = load_capture(path)
    assert capture.rows[0].cooling_power_w is None
    assert capture.rows[1].cooling_power_w == 0.0
    assert capture.rows[0].cooling_power_w != capture.rows[1].cooling_power_w


def test_unqualified_capture_passes_diagnostic_qa_but_not_admission() -> None:
    capture = load_capture(REAL_A_EXPORT, a_run_index=REAL_A_INDEX)
    admission = evaluate_admission(capture)
    assert admission.highest_stage is AdmissionStage.USABLE_FOR_DIAGNOSTIC_QA
    assert admission.status is AdmissionStage.EXCLUDED_OR_BLOCKED
    assert not admission.eligible
    assert admission.eligible_s1_runs == 0
    assert admission.eligible_s2_runs == 0
    assert admission.blockers


# ---------------------------------------------------------------------------
# time and identity
# ---------------------------------------------------------------------------


def test_host_capture_time_never_becomes_device_event_time(tmp_path: Path) -> None:
    path = write_a_export(
        tmp_path,
        rows=[
            {
                "timestamp_utc": "NOT_AVAILABLE",
                "timestamp_utc_status": "UNAVAILABLE",
                "host_capture_time_utc": "2026-01-01T00:00:00Z",
            }
        ],
    )
    capture = load_capture(path)
    row = capture.rows[0]
    assert row.event_time_utc is None
    assert row.host_capture_time_utc == _dt.datetime(
        2026, 1, 1, tzinfo=_dt.timezone.utc
    )
    assert capture.time.domain == "BOOT_SCOPED_UPTIME"
    assert capture.time.absolute_latency_supported is False


def test_uptime_remains_boot_scoped(tmp_path: Path) -> None:
    path = write_a_export(
        tmp_path,
        rows=[
            {"boot_id": "boot-a", "device_ms": "1000"},
            {"boot_id": "boot-b", "device_ms": "1000"},
        ],
        boot_id=None,
        boot_id_status="UNRESOLVED_MULTIPLE_BOOT_IDS_IN_ONE_EXPORT",
        boot_ids=["boot-a", "boot-b"],
    )
    capture = load_capture(path)
    assert capture.time.boot_scoped is True
    assert capture.time.cross_boot_join_allowed is False
    assert capture.run.boot_id is None
    admission = evaluate_admission(capture)
    assert "BOOT_ID_UNRESOLVED" in {blocker.code for blocker in admission.blockers}


def test_naive_timestamps_are_rejected(tmp_path: Path) -> None:
    c_path = _write_c_variant(
        tmp_path, captured_at="2026-01-01T00:00:00"
    )
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(c_path)
    assert excinfo.value.code == "NAIVE_TIMESTAMP_OR_INVALID_TIME"

    a_dir = tmp_path / "a"
    a_dir.mkdir()
    a_path = write_a_export(
        a_dir,
        rows=[{"host_capture_time_utc": "2026-01-01T00:00:00"}],
    )
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(a_path)
    assert excinfo.value.code == "NAIVE_TIMESTAMP_OR_INVALID_TIME"


def test_contradictory_identity_and_sequence_are_refused(tmp_path: Path) -> None:
    for name in ("seq", "boot", "run", "device"):
        (tmp_path / name).mkdir()
    decreasing = write_a_export(
        tmp_path / "seq",
        rows=[{"seq": "2"}, {"seq": "1"}],
    )
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(decreasing)
    assert excinfo.value.code == "SEQUENCE_CONTRADICTION"

    wrong_boot = write_a_export(
        tmp_path / "boot",
        rows=[{"boot_id": "boot-other"}],
    )
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(wrong_boot)
    assert excinfo.value.code == "BOOT_ID_CONTRADICTION"

    wrong_run = write_a_export(
        tmp_path / "run",
        rows=[{"run_id": "CG-S1-A-999"}],
    )
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(wrong_run)
    assert excinfo.value.code == "RUN_ID_CONTRADICTION"

    wrong_device = write_a_export(
        tmp_path / "device",
        rows=[{"device_id": "cg-other-device"}],
    )
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(wrong_device)
    assert excinfo.value.code == "DEVICE_ID_CONTRADICTION"


def test_repeated_views_are_not_independent_physical_runs() -> None:
    capture = load_capture(REAL_A_EXPORT, a_run_index=REAL_A_INDEX)
    counts = count_independent_runs([capture, capture])
    assert counts.unique_physical_sources == 1
    assert counts.duplicate_views == 1

    admission = evaluate_admission(capture)
    readiness = summarize_readiness([admission, admission])
    assert readiness.unique_physical_sources == 1
    assert readiness.duplicate_views == 1
    assert readiness.eligible_s1_runs == 0
    assert readiness.eligible_s2_runs == 0
    assert readiness.predictive_dataset_readiness == "NOT_READY"


def _admission_view(
    tmp_path: Path, name: str, *, valid: bool
) -> AdmissionResult:
    directory = tmp_path / name
    directory.mkdir()
    export = _positive_export(directory).rename(directory / f"{name}.json")
    index = _positive_index(directory, valid=valid)
    return evaluate_admission(load_capture(export, a_run_index=index))


def _retarget_device(export: Path, device_id: str) -> None:
    payload = json.loads(export.read_text(encoding="utf-8"))
    payload["device_id"] = device_id
    export.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    rows = export.parent / "rows.csv"
    rows.write_text(
        rows.read_text(encoding="utf-8").replace("cg-test-001", device_id),
        encoding="utf-8",
    )


def test_duplicate_views_with_conflicting_admission_fail_closed(
    tmp_path: Path,
) -> None:
    eligible = _admission_view(tmp_path, "eligible", valid=True)
    excluded = _admission_view(tmp_path, "excluded", valid=False)
    assert eligible.eligible
    assert not excluded.eligible

    forward = summarize_readiness([eligible, excluded])
    reverse = summarize_readiness([excluded, eligible])
    assert forward.to_dict() == reverse.to_dict()
    assert forward.predictive_dataset_readiness == "NOT_READY"
    assert forward.eligible_s1_runs == 0
    assert forward.eligible_s2_runs == 0
    assert forward.unique_physical_sources == 1
    assert forward.duplicate_views == 1

    assert len(forward.exclusions) == 1
    exclusion = forward.exclusions[0]
    codes = [blocker["code"] for blocker in exclusion["blockers"]]
    assert codes[0] == "DUPLICATE_VIEW_ADMISSION_CONFLICT"
    assert "A_LEDGER_INVALID" in codes
    assert exclusion["views"] == 2
    assert (
        exclusion["highest_stage"]
        == AdmissionStage.USABLE_FOR_DIAGNOSTIC_QA.value
    )
    assert exclusion["source_paths"] == ["eligible.json", "excluded.json"]
    verdicts = {
        verdict["source_path"]: verdict["status"]
        for verdict in exclusion["view_verdicts"]
    }
    assert verdicts == {
        "eligible.json": "ELIGIBLE_FOR_PREDICTIVE_DATASET",
        "excluded.json": "EXCLUDED_OR_BLOCKED",
    }


def test_duplicate_identical_eligible_views_count_once(tmp_path: Path) -> None:
    eligible = _admission_view(tmp_path, "eligible", valid=True)
    readiness = summarize_readiness([eligible, eligible])
    assert readiness.predictive_dataset_readiness == "READY"
    assert readiness.eligible_s1_runs == 1
    assert readiness.eligible_s2_runs == 0
    assert readiness.unique_physical_sources == 1
    assert readiness.duplicate_views == 1
    assert readiness.exclusions == ()


def test_duplicate_identical_invalid_views_remain_invalid(tmp_path: Path) -> None:
    excluded = _admission_view(tmp_path, "excluded", valid=False)
    readiness = summarize_readiness([excluded, excluded])
    assert readiness.predictive_dataset_readiness == "NOT_READY"
    assert readiness.eligible_s1_runs == 0
    assert readiness.eligible_s2_runs == 0
    assert readiness.unique_physical_sources == 1
    assert readiness.duplicate_views == 1
    assert len(readiness.exclusions) == 1
    assert readiness.exclusions[0]["views"] == 2
    assert "DUPLICATE_VIEW_ADMISSION_CONFLICT" not in {
        blocker["code"] for blocker in readiness.exclusions[0]["blockers"]
    }


def test_distinct_devices_sharing_a_boot_id_are_not_merged(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "device-a"
    second_dir = tmp_path / "device-b"
    first_dir.mkdir()
    second_dir.mkdir()
    first_export = _positive_export(first_dir)
    second_export = _positive_export(second_dir)
    _retarget_device(first_export, "cg-device-a")
    _retarget_device(second_export, "cg-device-b")
    first = evaluate_admission(
        load_capture(
            first_export,
            a_run_index=_positive_index(first_dir, valid=True),
        )
    )
    second = evaluate_admission(
        load_capture(
            second_export,
            a_run_index=_positive_index(second_dir, valid=True),
        )
    )
    assert first.capture.run.boot_id == second.capture.run.boot_id
    assert first.capture.run.device_id != second.capture.run.device_id

    counts = count_independent_runs(
        [first.capture, second.capture]
    )
    assert counts.unique_physical_sources == 2
    readiness = summarize_readiness([first, second])
    assert readiness.unique_physical_sources == 2
    assert readiness.duplicate_views == 0
    assert readiness.eligible_s1_runs == 2
    assert readiness.predictive_dataset_readiness == "READY"


def test_same_boot_run_labels_do_not_create_independent_sources(
    tmp_path: Path,
) -> None:
    captures = []
    for label in ("first", "second"):
        directory = tmp_path / label
        directory.mkdir()
        export = _positive_export(directory)
        payload = json.loads(export.read_text(encoding="utf-8"))
        run_id = f"CG-S1-A-{label.upper()}"
        payload["run_id"] = run_id
        payload["run_ids"] = [run_id]
        payload["device_run_label"] = label.upper()
        export.write_text(json.dumps(payload), encoding="utf-8")
        rows = directory / "rows.csv"
        rows.write_text(
            rows.read_text(encoding="utf-8").replace("CG-S1-A-001", run_id),
            encoding="utf-8",
        )
        captures.append(load_capture(export))
    assert captures[0].run.run_id != captures[1].run.run_id
    assert captures[0].run.boot_id == captures[1].run.boot_id
    counts = count_independent_runs(captures)
    assert counts.unique_physical_sources == 1
    assert counts.duplicate_views == 1


# ---------------------------------------------------------------------------
# validity and data selection
# ---------------------------------------------------------------------------


def test_a_ledger_invalid_excludes_plausible_readings(tmp_path: Path) -> None:
    export = _positive_export(tmp_path)
    index = _positive_index(tmp_path, valid=False)
    capture = load_capture(export, a_run_index=index)
    admission = evaluate_admission(capture)
    assert "A_LEDGER_INVALID" in {blocker.code for blocker in admission.blockers}
    assert not admission.eligible
    assert admission.eligible_s1_runs == 0


def test_missing_validity_evidence_is_never_green(tmp_path: Path) -> None:
    export = _positive_export(tmp_path)
    admission = evaluate_admission(load_capture(export))
    codes = {blocker.code for blocker in admission.blockers}
    assert "PHYSICAL_VALIDITY_EVIDENCE_MISSING" in codes
    assert not admission.eligible


def test_synthetic_data_never_becomes_physical(tmp_path: Path) -> None:
    capture = load_capture(C_FIXTURE)
    assert capture.source.provenance == "SYNTHETIC"
    assert capture.source.is_physical_measurement is False
    admission = evaluate_admission(capture)
    assert "SYNTHETIC_PROVENANCE" in {
        blocker.code for blocker in admission.blockers
    }
    assert not admission.eligible


def test_contradictory_a_ledger_fails_closed(tmp_path: Path) -> None:
    export = _positive_export(tmp_path)
    index = _positive_index(tmp_path, valid=True)
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["blocked_run_ids"] = [
        {
            "run_id": "CG-S1-A-001",
            "boot_id": "boot-test",
            "device_run_label": "TEST_RUN",
            "usable_fraction": 1.0,
            "reasons": ["LEDGER_SAYS_INVALID"],
        }
    ]
    index.write_text(json.dumps(payload), encoding="utf-8")
    admission = evaluate_admission(load_capture(export, a_run_index=index))
    assert not admission.eligible
    assert "A_LEDGER_INVALID" in {blocker.code for blocker in admission.blockers}
    assert any(
        "CONTRADICTORY_LEDGER" in blocker.detail for blocker in admission.blockers
    )
    assert admission.eligible_s1_runs == 0


def test_blocked_ledger_identity_contradiction_still_blocks(
    tmp_path: Path,
) -> None:
    export = _positive_export(tmp_path)
    index = _positive_index(tmp_path)
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["blocked_run_ids"] = [
        {
            "run_id": "CG-S1-A-001",
            "boot_id": "boot-test",
            "device_run_label": "TYPO_LABEL",
            "reasons": ["LEDGER_SAYS_INVALID"],
        }
    ]
    index.write_text(json.dumps(payload), encoding="utf-8")
    admission = evaluate_admission(load_capture(export, a_run_index=index))
    assert "A_LEDGER_INVALID" in {blocker.code for blocker in admission.blockers}
    assert any(
        "LEDGER_IDENTITY_CONTRADICTION" in blocker.detail
        for blocker in admission.blockers
    )
    assert not admission.eligible


def test_blocked_ledger_sparse_run_entry_still_blocks(tmp_path: Path) -> None:
    export = _positive_export(tmp_path)
    index = _positive_index(
        tmp_path,
        valid=False,
        entry_extra={"is_valid": True, "valid_for_scenarios": ["S1"]},
    )
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["runs"][0].pop("run_id", None)
    payload["blocked_run_ids"] = [
        {"run_id": "CG-S1-A-001", "reasons": ["LEDGER_SAYS_INVALID"]}
    ]
    index.write_text(json.dumps(payload), encoding="utf-8")
    admission = evaluate_admission(load_capture(export, a_run_index=index))
    assert "A_LEDGER_INVALID" in {blocker.code for blocker in admission.blockers}
    assert not admission.eligible


def test_blocked_ledger_sparse_blocked_entry_still_blocks(
    tmp_path: Path,
) -> None:
    export = _positive_export(tmp_path)
    index = _positive_index(
        tmp_path,
        valid=False,
        entry_extra={"is_valid": True, "valid_for_scenarios": ["S1"]},
    )
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["runs"][0] = {
        "run_id": "CG-S1-A-001",
        "is_valid": True,
        "valid_for_scenarios": ["S1"],
        "frames_usable_per_scenario": {"S1_NORMAL_BASELINE": 1},
    }
    payload["blocked_run_ids"] = [
        {
            "boot_id": "boot-test",
            "device_run_label": "TEST_RUN",
            "reasons": ["LEDGER_SAYS_INVALID"],
        }
    ]
    index.write_text(json.dumps(payload), encoding="utf-8")
    admission = evaluate_admission(load_capture(export, a_run_index=index))
    assert "A_LEDGER_INVALID" in {blocker.code for blocker in admission.blockers}
    assert not admission.eligible


def test_blocked_ledger_matches_by_run_id_only(tmp_path: Path) -> None:
    export = _positive_export(tmp_path)
    index = _positive_index(tmp_path)
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["blocked_run_ids"] = [
        {"run_id": "CG-S1-A-001", "reasons": ["LEDGER_SAYS_INVALID"]}
    ]
    index.write_text(json.dumps(payload), encoding="utf-8")
    admission = evaluate_admission(load_capture(export, a_run_index=index))
    assert "A_LEDGER_INVALID" in {blocker.code for blocker in admission.blockers}
    assert not admission.eligible


def test_ambiguous_identity_status_cannot_reach_ready(tmp_path: Path) -> None:
    boot_dir = tmp_path / "boot"
    boot_dir.mkdir()
    boot_export = _positive_export(boot_dir)
    boot_payload = json.loads(boot_export.read_text(encoding="utf-8"))
    boot_payload["boot_id"] = "boot-a"
    boot_payload["boot_id_status"] = "UNRESOLVED_MULTIPLE_BOOT_IDS_IN_ONE_EXPORT"
    boot_payload["boot_ids"] = ["boot-a", "boot-b"]
    boot_export.write_text(json.dumps(boot_payload), encoding="utf-8")
    boot_index = _positive_index(boot_dir)
    boot_admission = evaluate_admission(
        load_capture(boot_export, a_run_index=boot_index)
    )
    assert "BOOT_ID_UNRESOLVED" in {
        blocker.code for blocker in boot_admission.blockers
    }
    assert not boot_admission.eligible

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    run_export = _positive_export(run_dir)
    run_payload = json.loads(run_export.read_text(encoding="utf-8"))
    run_payload["run_id_status"] = (
        "UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID"
    )
    run_payload["run_ids"] = ["CG-S1-A-001", "CG-S1-A-002"]
    run_export.write_text(json.dumps(run_payload), encoding="utf-8")
    run_index = _positive_index(run_dir)
    run_capture = load_capture(run_export, a_run_index=run_index)
    run_admission = evaluate_admission(run_capture)
    assert "RUN_ID_UNRESOLVED" in {
        blocker.code for blocker in run_admission.blockers
    }
    assert not run_admission.eligible
    assert run_capture.a_validity is not None
    assert run_capture.a_validity.is_valid is None
    assert run_capture.a_validity.status == "UNKNOWN"


def test_s1_validity_list_is_not_reused_for_s2(tmp_path: Path) -> None:
    denied_dir = tmp_path / "denied"
    denied_dir.mkdir()
    denied_export = _positive_export(
        denied_dir,
        scenario_candidate="S2_DOOR_DISTURBANCE",
        scenario_key="S2_DOOR_DISTURBANCE",
    )
    denied_index = _positive_index(
        denied_dir, scenario_key="S2_DOOR_DISTURBANCE"
    )
    denied = evaluate_admission(
        load_capture(denied_export, a_run_index=denied_index)
    )
    assert "SCENARIO_VALIDITY_NOT_GRANTED" in {
        blocker.code for blocker in denied.blockers
    }
    assert denied.eligible_s2_runs == 0
    assert not denied.eligible

    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    allowed_export = _positive_export(
        allowed_dir,
        scenario_candidate="S2_DOOR_DISTURBANCE",
        scenario_key="S2_DOOR_DISTURBANCE",
    )
    allowed_index = _positive_index(
        allowed_dir,
        scenario_key="S2_DOOR_DISTURBANCE",
        entry_extra={
            "is_valid": True,
            "valid_for_scenarios": ["S2_DOOR_DISTURBANCE"],
        },
    )
    allowed = evaluate_admission(
        load_capture(allowed_export, a_run_index=allowed_index)
    )
    assert allowed.eligible, [
        blocker.to_dict() for blocker in allowed.blockers
    ]
    assert allowed.eligible_s2_runs == 1


def test_row_hot_side_role_conflicts_with_chamber_air_slot(
    tmp_path: Path,
) -> None:
    path = write_a_export(tmp_path, rows=[{"t1_role": "HOT_SIDE"}])
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(path)
    assert excinfo.value.code == "SENSOR_ROLE_CONTRADICTION"


def test_unverifiable_pin_blocks_physical_qualification(
    tmp_path: Path,
) -> None:
    export = _positive_export(tmp_path)
    (tmp_path / ".git").rmdir()
    admission = evaluate_admission(load_capture(export))
    assert "PINNED_SOURCE_UNVERIFIABLE" in {
        blocker.code for blocker in admission.blockers
    }
    assert not admission.eligible


def test_out_of_vocabulary_position_is_refused(tmp_path: Path) -> None:
    sensors = [dict(sensor) for sensor in SENSORS]
    sensors[0]["physical_position"] = "CHAMBER_CENTRE"
    path = write_a_export(tmp_path, sensors=sensors)
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(path)
    assert excinfo.value.code == "SENSOR_POSITION_UNKNOWN_VOCABULARY"


def test_missing_pinned_source_blocks_physical_qualification(
    tmp_path: Path,
) -> None:
    export = _positive_export(tmp_path)
    (tmp_path / ".git").mkdir(exist_ok=True)
    payload = json.loads(export.read_text(encoding="utf-8"))
    payload["provenance"]["sources"][0]["path"] = "missing-source.csv"
    export.write_text(json.dumps(payload), encoding="utf-8")
    admission = evaluate_admission(load_capture(export))
    assert "PINNED_SOURCE_MISSING" in {
        blocker.code for blocker in admission.blockers
    }
    assert not admission.eligible


def test_pinned_source_hash_mismatch_is_refused(tmp_path: Path) -> None:
    export = _positive_export(tmp_path)
    (tmp_path / ".git").mkdir(exist_ok=True)
    payload = json.loads(export.read_text(encoding="utf-8"))
    payload["provenance"]["sources"][0]["sha256"] = "a" * 64
    export.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(export)
    assert excinfo.value.code == "SOURCE_HASH_MISMATCH"


def test_companion_header_and_row_count_mismatch_are_refused(
    tmp_path: Path,
) -> None:
    header_dir = tmp_path / "header"
    header_dir.mkdir()
    header_export = write_a_export(header_dir)
    header_payload = json.loads(header_export.read_text(encoding="utf-8"))
    header_payload["frames"]["columns_per_row"] = (
        header_payload["frames"]["columns_per_row"][:-1]
    )
    header_export.write_text(json.dumps(header_payload), encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(header_export)
    assert excinfo.value.code == "COMPANION_HEADER_MISMATCH"

    count_dir = tmp_path / "count"
    count_dir.mkdir()
    count_export = write_a_export(count_dir)
    count_payload = json.loads(count_export.read_text(encoding="utf-8"))
    count_payload["frames"]["rows"] = 99
    count_export.write_text(json.dumps(count_payload), encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(count_export)
    assert excinfo.value.code == "COMPANION_ROW_COUNT_MISMATCH"


def test_a_run_index_version_and_entry_mismatch_are_refused(
    tmp_path: Path,
) -> None:
    version_dir = tmp_path / "version"
    version_dir.mkdir()
    version_export = _positive_export(version_dir)
    version_index = _positive_index(version_dir)
    version_payload = json.loads(version_index.read_text(encoding="utf-8"))
    version_payload["index_version"] = "w09-run-index-v0"
    version_index.write_text(json.dumps(version_payload), encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(version_export, a_run_index=version_index)
    assert excinfo.value.code == "A_RUN_INDEX_VERSION_UNSUPPORTED"

    entry_dir = tmp_path / "entry"
    entry_dir.mkdir()
    entry_export = _positive_export(entry_dir)
    entry_index = _positive_index(entry_dir)
    entry_payload = json.loads(entry_index.read_text(encoding="utf-8"))
    entry_payload["runs"][0]["boot_id"] = "another-boot"
    entry_index.write_text(json.dumps(entry_payload), encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(entry_export, a_run_index=entry_index)
    assert excinfo.value.code == "A_RUN_INDEX_ENTRY_MISSING"


def test_malformed_valid_id_list_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "malformed"
    directory.mkdir()
    export = _positive_export(directory)
    index = _positive_index(directory)
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["valid_s1_run_ids_for_member_b"] = {"CG-S1-A-001": "oops"}
    index.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(export, a_run_index=index)
    assert excinfo.value.code == "A_RUN_INDEX_INVALID"

    payload["valid_s1_run_ids_for_member_b"] = None
    index.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(export, a_run_index=index)
    assert excinfo.value.code == "A_RUN_INDEX_INVALID"


def test_anonymous_a_ledger_entry_is_refused(tmp_path: Path) -> None:
    export = _positive_export(tmp_path)
    index = _positive_index(tmp_path)
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["blocked_run_ids"] = [{"reasons": ["NO_IDENTITY"]}]
    index.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(export, a_run_index=index)
    assert excinfo.value.code == "A_RUN_INDEX_INVALID"


def test_actuation_range_violation_is_refused(tmp_path: Path) -> None:
    path = write_a_export(
        tmp_path,
        rows=[{"pwm_applied_permille": "1001"}],
    )
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(path)
    assert excinfo.value.code == "ACTUATION_RANGE_VIOLATION"


def test_multi_boot_export_is_structurally_invalid_in_cli(
    tmp_path: Path,
) -> None:
    export = write_a_export(
        tmp_path,
        rows=[
            {"boot_id": "boot-a", "device_ms": "1000"},
            {"boot_id": "boot-b", "device_ms": "1000"},
        ],
        boot_id=None,
        boot_id_status="UNRESOLVED_MULTIPLE_BOOT_IDS_IN_ONE_EXPORT",
        boot_ids=["boot-a", "boot-b"],
    )
    result = _run_cli("check", str(export), "--format", "json")
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["structure"]["status"] == "INVALID"
    assert report["admission"]["highest_stage"] == "SOURCE_RECOGNIZED"
    assert "BOOT_ID_UNRESOLVED" in {
        blocker["code"] for blocker in report["exclusions"]
    }


def test_zero_admitted_runs_are_deterministic_and_honest() -> None:
    capture = load_capture(REAL_A_EXPORT, a_run_index=REAL_A_INDEX)
    first = evaluate_admission(capture)
    second = evaluate_admission(capture)
    assert first.to_dict() == second.to_dict()
    summary = summarize_readiness([first])
    assert summary.eligible_s1_runs == 0
    assert summary.eligible_s2_runs == 0
    assert summary.predictive_dataset_readiness == "NOT_READY"
    assert summary.to_dict() == summarize_readiness([second]).to_dict()


def test_w02_synthetic_split_behavior_is_preserved() -> None:
    specs = [
        SyntheticRunSpec(
            run_id=f"CG-S1-A-{index:03d}",
            scenario_id="S1",
            seed=index,
            duration_s=20.0,
        )
        for index in range(1, 7)
    ]
    runs = build_synthetic_runs(specs)
    infos = [
        RunInfo(
            run_id=run.run_id,
            scenario_id=run.spec.scenario_id,
            controller_id=run.spec.controller_id,
            hardware_config_id=run.spec.hardware_config_id,
        )
        for run in runs
    ]
    result = split_runs(
        infos,
        SplitConfig(
            proportions=SplitProportions(1 / 3, 1 / 3, 1 / 3),
            seed=7,
        ),
    )
    assert set(result.train_runs).isdisjoint(result.validation_runs)
    assert set(result.train_runs).isdisjoint(result.test_runs)
    assert set(result.validation_runs).isdisjoint(result.test_runs)
    assert set(result.train_runs + result.validation_runs + result.test_runs) == {
        info.run_id for info in infos
    }


def test_positive_control_reaches_predictive_eligibility(tmp_path: Path) -> None:
    export = _positive_export(tmp_path)
    index = _positive_index(tmp_path)
    capture = load_capture(export, a_run_index=index)
    admission = evaluate_admission(capture)
    assert admission.eligible, [
        blocker.to_dict() for blocker in admission.blockers
    ]
    assert admission.highest_stage is AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET
    assert admission.eligible_s1_runs == 1
    assert admission.eligible_s2_runs == 0
    assert admission.predictive_dataset_readiness == "READY"


# ---------------------------------------------------------------------------
# executable checker CLI
# ---------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCHEMA_CHECK), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_real_export_reports_zero_eligible_deterministically() -> None:
    args = (
        "check",
        str(REAL_A_EXPORT),
        "--a-run-index",
        str(REAL_A_INDEX),
        "--format",
        "json",
    )
    first = _run_cli(*args)
    second = _run_cli(*args)
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    report = json.loads(first.stdout)
    assert report["source_format"] == SOURCE_FORMAT_A_W09_EXPORT
    assert report["eligible_s1_runs"] == 0
    assert report["eligible_s2_runs"] == 0
    assert report["predictive_dataset_readiness"] == "NOT_READY"
    assert report["admission"]["highest_stage"] == "USABLE_FOR_DIAGNOSTIC_QA"
    assert report["roles"]["chamber_air_slots"] == ["t1", "t3", "t4"]
    assert report["roles"]["hot_side_slots"] == ["t2"]


def test_cli_invalid_fixture_exits_2_with_precise_refusal(
    tmp_path: Path,
) -> None:
    payload = json.loads(C_FIXTURE.read_text(encoding="utf-8"))
    payload["electrical"]["tec_2"] = 1.0
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_cli("check", str(path), "--format", "json")
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["reason_code"] == "LEGACY_FORBIDDEN_FIELD"


def test_cli_serial_refusal_exits_2(tmp_path: Path) -> None:
    serial = tmp_path / "h8s.log"
    serial.write_text("#CG H8S schema=3 seq=1\n", encoding="utf-8")
    result = _run_cli("check", str(serial), "--format", "json")
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["reason_code"] == "SERIAL_SCHEMA_NOT_BACKEND_WIRE"


def test_cli_identify_reports_supported_and_unsupported(tmp_path: Path) -> None:
    supported = _run_cli("identify", str(REAL_A_EXPORT))
    assert supported.returncode == 0
    assert json.loads(supported.stdout)["supported"] is True

    unknown = tmp_path / "unknown.bin"
    unknown.write_text("not a telemetry source\n", encoding="utf-8")
    refused = _run_cli("identify", str(unknown))
    assert refused.returncode == 2
    assert json.loads(refused.stdout)["supported"] is False


def test_cli_require_eligible_returns_1_for_not_ready() -> None:
    result = _run_cli(
        "check",
        str(REAL_A_EXPORT),
        "--a-run-index",
        str(REAL_A_INDEX),
        "--format",
        "json",
        "--require-eligible",
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["predictive_dataset_readiness"] == "NOT_READY"
