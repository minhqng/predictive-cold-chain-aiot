"""Tests for read-only Digital Twin and telemetry APIs (C-W05-04, C-W05-05)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from coldguard_backend.main import app

client = TestClient(app)


def test_health_still_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_device_state_unknown_device_returns_404():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.mappings.return_value.first.return_value = None
    mock_conn.execute.return_value = mock_cursor
    mock_engine.begin.return_value.__enter__.return_value = mock_conn

    app.state.db_engine = mock_engine
    try:
        response = client.get("/api/devices/unknown-device-001/state")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    finally:
        app.state.db_engine = None


def test_get_device_state_returns_separated_twin_domains():
    now = datetime.now(timezone.utc)
    mock_twin_row = {
        "device_id": "coldguard-001",
        "twin_version": 4,
        "reported_state": {"cooling": "ON", "duty": 0.8},
        "desired_state": {"cooling": "ON", "target_temp_c": 4.0},
        "derived_state": {"thermal_risk": "NOMINAL"},
        "connectivity_state": "ONLINE",
        "device_mode": "ONLINE_NORMAL",
        "last_boot_id": "boot-123",
        "last_seq": 42,
        "last_reported_at": now,
        "last_desired_at": now,
        "last_derived_at": now,
        "updated_at": now,
    }

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.mappings.return_value.first.return_value = mock_twin_row
    mock_conn.execute.return_value = mock_cursor
    mock_engine.begin.return_value.__enter__.return_value = mock_conn

    app.state.db_engine = mock_engine
    try:
        response = client.get("/api/devices/coldguard-001/state")
        assert response.status_code == 200
        data = response.json()
        assert data["device_id"] == "coldguard-001"
        assert data["twin_version"] == 4
        # Verify separation of reported, desired, and derived domains
        assert data["reported_state"] == {"cooling": "ON", "duty": 0.8}
        assert data["desired_state"] == {"cooling": "ON", "target_temp_c": 4.0}
        assert data["derived_state"] == {"thermal_risk": "NOMINAL"}
        assert data["connectivity_state"] == "ONLINE"
        assert data["device_mode"] == "ONLINE_NORMAL"
        assert data["last_boot_id"] == "boot-123"
        assert data["last_seq"] == 42
    finally:
        app.state.db_engine = None


def test_get_device_telemetry_validates_pagination_bounds():
    # Validation errors should fail with HTTP 422 Unprocessable Entity
    resp_zero_limit = client.get("/api/devices/coldguard-001/telemetry?limit=0")
    assert resp_zero_limit.status_code == 422

    resp_excessive_limit = client.get("/api/devices/coldguard-001/telemetry?limit=1001")
    assert resp_excessive_limit.status_code == 422

    resp_negative_offset = client.get("/api/devices/coldguard-001/telemetry?offset=-1")
    assert resp_negative_offset.status_code == 422

    resp_invalid_order = client.get("/api/devices/coldguard-001/telemetry?order=random")
    assert resp_invalid_order.status_code == 422


def test_get_device_telemetry_returns_timing_and_provenance():
    now = datetime.now(timezone.utc)
    captured = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)
    received = datetime(2026, 11, 7, 12, 0, 0, 150000, tzinfo=timezone.utc)

    mock_telemetry_rows = [
        # 1: Synchronized record
        {
            "id": 1,
            "device_id": "coldguard-001",
            "boot_id": "boot-sync",
            "seq": 10,
            "run_id": "RUN-001",
            "time": captured,
            "backend_received_at": received,
            "t1_c": 4.2,
            "t2_c": 4.1,
            "t3_c": 4.3,
            "t_air_c": 21.0,
            "rh_pct": 55.0,
            "door_state": "CLOSED",
            "cooling_voltage_v": 12.1,
            "cooling_current_a": 1.2,
            "cooling_power_w": 14.52,
            "cooling_energy_counter_wh": 0.5,
            "applied_cooling": "ON",
            "applied_duty": 0.75,
            "thermal_quality": "VALID",
            "environment_quality": "VALID",
            "electrical_quality": "VALID",
            "overall_quality": "VALID",
            "device_mode": "ONLINE_NORMAL",
            "hardware_config_id": "CG-HW-001",
            "firmware_version": "cg-w05-0.1.0",
            "calibration_id": "CAL-01",
            "schema_version": 1,
            "raw_id": 1001,
            "serial_source": None,
        },
        # 2: Clockless record
        {
            "id": 2,
            "device_id": "coldguard-001",
            "boot_id": "boot-clockless",
            "seq": 11,
            "run_id": "RUN-001",
            "time": None,  # Clockless!
            "backend_received_at": received,
            "t1_c": 4.5,
            "t2_c": 4.4,
            "t3_c": None,
            "t_air_c": None,
            "rh_pct": None,
            "door_state": "UNKNOWN",
            "cooling_voltage_v": 12.0,
            "cooling_current_a": 1.0,
            "cooling_power_w": 12.0,
            "cooling_energy_counter_wh": 0.6,
            "applied_cooling": "OFF",
            "applied_duty": 0.0,
            "thermal_quality": "DEGRADED",
            "environment_quality": "UNKNOWN",
            "electrical_quality": "VALID",
            "overall_quality": "DEGRADED",
            "device_mode": "ONLINE_NORMAL",
            "hardware_config_id": "CG-HW-001",
            "firmware_version": "cg-w05-0.1.0",
            "calibration_id": None,
            "schema_version": 2,
            "raw_id": 1002,
            "serial_source": {
                "schema_version": 2,
                "clock_quality": "UNAVAILABLE",
                "gateway_received_at": received.isoformat(),
                "frame": "#CG TELEM ...",
            },
        },
    ]

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    # 1st execute: twin check (returns device_id)
    # 2nd execute: query_telemetry rows
    # 3rd execute: count_telemetry
    cursor_twin = MagicMock()
    cursor_twin.scalar_one_or_none.return_value = "coldguard-001"

    cursor_rows = MagicMock()
    cursor_rows.mappings.return_value.all.return_value = mock_telemetry_rows

    cursor_count = MagicMock()
    cursor_count.scalar.return_value = 2

    mock_conn.execute.side_effect = [cursor_twin, cursor_rows, cursor_count]
    mock_engine.begin.return_value.__enter__.return_value = mock_conn

    app.state.db_engine = mock_engine
    try:
        response = client.get("/api/devices/coldguard-001/telemetry?limit=50&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert len(data["items"]) == 2

        # Verify Item 1 (Synchronized)
        item1 = data["items"][0]
        assert item1["id"] == 1
        assert item1["time"] is not None
        assert item1["timing"]["status"] == "SYNCHRONIZED"
        assert item1["timing"]["latency_ms"] == 150.0
        assert item1["measurements"]["thermal"]["t1_c"] == 4.2
        assert item1["provenance"]["calibration_id"] == "CAL-01"

        # Verify Item 2 (Clockless)
        item2 = data["items"][1]
        assert item2["id"] == 2
        assert item2["time"] is None
        assert item2["timing"]["status"] == "UNAVAILABLE"
        assert item2["timing"]["latency_ms"] is None
        assert item2["provenance"]["serial_source"] is not None
        assert item2["provenance"]["serial_source"]["clock_quality"] == "UNAVAILABLE"
        assert item2["quality"]["environment"] == "UNKNOWN"
    finally:
        app.state.db_engine = None
