"""Tests for database-backed raw/normalized telemetry reconciliation (C-W05-03)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from coldguard_backend.reconciliation import (
    ProvenanceAudit,
    ReconciliationReport,
    reconcile_telemetry,
)


def test_reconciliation_math_with_known_totals():
    # Build synthetic database result sets with known expected outcomes
    now = datetime.now(timezone.utc)
    raw_payload_valid = (
        '{"schema_version":1,"device_id":"coldguard-001","boot_id":"boot-1","seq":1,'
        '"captured_at":"' + now.isoformat() + '","uptime_ms":1000,'
        '"run_id":"RUN-1","hardware_config_id":"HW-1","firmware_version":"0.1.0",'
        '"thermal":{"t1":4.0,"t2":4.0,"t3":4.0},'
        '"environment":{"t_air":20.0,"rh":50.0},'
        '"door":{"state":"CLOSED"},'
        '"electrical":{"voltage_v":12.0,"current_a":1.0,"power_w":12.0,"energy_wh":1.0},'
        '"actuation":{"cooling":"OFF","duty":0.0},'
        '"quality":{"thermal":"VALID","environment":"VALID","electrical":"VALID","overall":"VALID"}}'
    )
    raw_payload_conflict = (
        '{"schema_version":1,"device_id":"coldguard-001","boot_id":"boot-1","seq":1,'
        '"captured_at":"' + now.isoformat() + '","uptime_ms":1000,'
        '"run_id":"RUN-1","hardware_config_id":"HW-1","firmware_version":"0.1.0",'
        '"thermal":{"t1":14.0,"t2":14.0,"t3":14.0},'  # Changed temperature -> conflict
        '"environment":{"t_air":20.0,"rh":50.0},'
        '"door":{"state":"CLOSED"},'
        '"electrical":{"voltage_v":12.0,"current_a":1.0,"power_w":12.0,"energy_wh":1.0},'
        '"actuation":{"cooling":"OFF","duty":0.0},'
        '"quality":{"thermal":"VALID","environment":"VALID","electrical":"VALID","overall":"VALID"}}'
    )

    mock_raw_rows = [
        # Winning valid raw delivery 1
        {"id": 1, "device_id": "coldguard-001", "boot_id": "boot-1", "seq": 1, "run_id": "RUN-1", "ingest_status": "RECEIVED_VALID", "raw_payload": raw_payload_valid, "backend_received_at": now},
        # Exact duplicate of delivery 1
        {"id": 2, "device_id": "coldguard-001", "boot_id": "boot-1", "seq": 1, "run_id": "RUN-1", "ingest_status": "RECEIVED_VALID", "raw_payload": raw_payload_valid, "backend_received_at": now},
        # Conflicting duplicate of delivery 1
        {"id": 3, "device_id": "coldguard-001", "boot_id": "boot-1", "seq": 1, "run_id": "RUN-1", "ingest_status": "RECEIVED_VALID", "raw_payload": raw_payload_conflict, "backend_received_at": now},
        # Winning valid raw delivery 2
        {"id": 4, "device_id": "coldguard-001", "boot_id": "boot-1", "seq": 2, "run_id": "RUN-1", "ingest_status": "RECEIVED_VALID", "raw_payload": raw_payload_valid.replace('"seq":1', '"seq":2'), "backend_received_at": now},
        # Invalid schema
        {"id": 5, "device_id": "coldguard-001", "boot_id": "boot-1", "seq": 3, "run_id": "RUN-1", "ingest_status": "RECEIVED_INVALID_SCHEMA", "raw_payload": "{}", "backend_received_at": now},
        # Malformed JSON
        {"id": 6, "device_id": None, "boot_id": None, "seq": None, "run_id": None, "ingest_status": "RECEIVED_MALFORMED_JSON", "raw_payload": "{bad", "backend_received_at": now},
        # Topic mismatch
        {"id": 7, "device_id": "coldguard-002", "boot_id": "boot-1", "seq": 4, "run_id": "RUN-1", "ingest_status": "REJECTED_TOPIC_MISMATCH", "raw_payload": "{}", "backend_received_at": now},
        # Observed non-telemetry
        {"id": 8, "device_id": "coldguard-001", "boot_id": "boot-1", "seq": 5, "run_id": "RUN-1", "ingest_status": "RECEIVED_OBSERVED", "raw_payload": "{}", "backend_received_at": now},
    ]

    mock_norm_rows = [
        {
            "id": 101, "raw_id": 1, "device_id": "coldguard-001", "boot_id": "boot-1", "seq": 1,
            "run_id": "RUN-1", "time": now, "t1_c": 4.0, "t2_c": 4.0, "t3_c": 4.0,
            "t_air_c": 20.0, "rh_pct": 50.0, "door_state": "CLOSED",
            "cooling_voltage_v": 12.0, "cooling_current_a": 1.0, "cooling_power_w": 12.0,
            "cooling_energy_counter_wh": 1.0, "applied_cooling": "OFF", "applied_duty": 0.0,
            "thermal_quality": "VALID", "environment_quality": "VALID",
            "electrical_quality": "VALID", "overall_quality": "VALID",
            "device_mode": None, "hardware_config_id": "HW-1", "firmware_version": "0.1.0",
            "calibration_id": None, "schema_version": 1, "backend_received_at": now,
            "serial_source": None,
        },
        {
            "id": 102, "raw_id": 4, "device_id": "coldguard-001", "boot_id": "boot-1", "seq": 2,
            "run_id": "RUN-1", "time": now, "t1_c": 4.0, "t2_c": 4.0, "t3_c": 4.0,
            "t_air_c": 20.0, "rh_pct": 50.0, "door_state": "CLOSED",
            "cooling_voltage_v": 12.0, "cooling_current_a": 1.0, "cooling_power_w": 12.0,
            "cooling_energy_counter_wh": 1.0, "applied_cooling": "OFF", "applied_duty": 0.0,
            "thermal_quality": "VALID", "environment_quality": "VALID",
            "electrical_quality": "VALID", "overall_quality": "VALID",
            "device_mode": None, "hardware_config_id": "HW-1", "firmware_version": "0.1.0",
            "calibration_id": None, "schema_version": 1, "backend_received_at": now,
            "serial_source": None,
        },
    ]

    # Mock DB Connection
    mock_conn = MagicMock()
    mock_cursor_raw = MagicMock()
    mock_cursor_raw.mappings.return_value.all.return_value = mock_raw_rows
    mock_cursor_norm = MagicMock()
    mock_cursor_norm.mappings.return_value.all.return_value = mock_norm_rows
    mock_conn.execute.side_effect = [mock_cursor_raw, mock_cursor_norm]

    report = reconcile_telemetry(mock_conn)

    assert report.raw_total == 8
    assert report.normalized_total == 2
    assert report.unique_identities == 2
    assert report.unique_normalized_deliveries == 2
    assert report.exact_duplicates == 1
    assert report.conflicting_duplicates == 1
    assert report.normalization_failures == 0
    assert report.rejected_invalid_schema == 1
    assert report.rejected_malformed_json == 1
    assert report.rejected_topic_mismatch == 1
    assert report.observed_non_telemetry == 1
    assert report.discrepancy == 0
    assert report.is_reconciled is True
    assert "PASSED" in report.summary()


def test_reconciliation_detects_normalization_failures():
    now = datetime.now(timezone.utc)
    mock_raw_rows = [
        # Marked RECEIVED_VALID, but normalized write was dropped/failed
        {"id": 1, "device_id": "coldguard-001", "boot_id": "boot-1", "seq": 1, "run_id": "RUN-1", "ingest_status": "RECEIVED_VALID", "raw_payload": "{}", "backend_received_at": now},
    ]
    mock_norm_rows = []  # Empty normalized table!

    mock_conn = MagicMock()
    mock_cursor_raw = MagicMock()
    mock_cursor_raw.mappings.return_value.all.return_value = mock_raw_rows
    mock_cursor_norm = MagicMock()
    mock_cursor_norm.mappings.return_value.all.return_value = mock_norm_rows
    mock_conn.execute.side_effect = [mock_cursor_raw, mock_cursor_norm]

    report = reconcile_telemetry(mock_conn)

    assert report.raw_total == 1
    assert report.normalized_total == 0
    assert report.normalization_failures == 1
    assert report.unique_normalized_deliveries == 0
    assert report.accounted_total == 1
    assert report.discrepancy == 0
    assert report.is_reconciled is False
    assert "FAILED" in report.summary()

