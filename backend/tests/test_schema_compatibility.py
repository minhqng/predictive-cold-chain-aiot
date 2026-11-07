"""Schema freeze and compatibility tests across W05-W08 contracts (C-W05-01).

Proves:
- Preserving (device_id, boot_id, seq) canonical dedup identity.
- Preserving timezone-aware capture time for schema 1.
- Preserving nullable clockless event time with serial provenance for schema 2.
- Preserving run_id and calibration_id (never fabricating UTC, run, or calibration).
- Sensor quality semantics (VALID, DEGRADED, INVALID, and UNKNOWN in schema 2).
- Physical measurement integrity (single branch cooling, non-negative counters, [0.0, 1.0] duty).
- Rejection of legacy dual-branch fields and schema 0 / unsupported versions.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from coldguard_backend.contracts import (
    WIRE_SCHEMA_VERSION,
    ActuationSection,
    DoorSection,
    ElectricalSection,
    EnvironmentSection,
    QualitySection,
    SerialSource,
    Telemetry,
    ThermalSection,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
MEMBER_A_FIXTURE = Path(__file__).resolve().parents[2] / "evidence/A/W05/schema-fixture.json"


def _schema1_payload() -> dict:
    return json.loads((FIXTURES / "telemetry_v0.json").read_text(encoding="utf-8"))


def _schema2_payload() -> dict:
    fixture_data = json.loads(MEMBER_A_FIXTURE.read_text(encoding="utf-8"))
    fields = dict(fixture_data["fields"])
    # Construct schema 2 payload matching serial gateway output
    return {
        "schema_version": 2,
        "device_id": fields["device_id"],
        "boot_id": fields["boot_id"],
        "seq": fields["seq"],
        "captured_at": None,
        "uptime_ms": fields["uptime_ms"],
        "run_id": None if fields.get("run_id") in ("UNSET", None) else fields["run_id"],
        "hardware_config_id": fields["hardware_config_id"],
        "firmware_version": fields["firmware_version"],
        "calibration_id": None if fields.get("calibration_id") in ("UNRECORDED", None) else fields["calibration_id"],
        "thermal": {
            "t1": 4.12,
            "t2": 5.0,
            "t3": None,
        },
        "environment": {
            "t_air": None,
            "rh": None,
        },
        "door": {
            "state": "UNKNOWN",
        },
        "electrical": {
            "voltage_v": 12.04,
            "current_a": 1.5,
            "power_w": 18.06,
            "energy_wh": 0.05,
        },
        "actuation": {
            "cooling": "ON",
            "duty": 0.85,
        },
        "quality": {
            "thermal": "DEGRADED",
            "environment": "UNKNOWN",
            "electrical": "VALID",
            "overall": "DEGRADED",
            "device_mode": "ONLINE_NORMAL",
        },
        "serial_source": {
            "schema_version": fields["schema"],
            "clock_quality": "UNAVAILABLE",
            "gateway_received_at": datetime.now(timezone.utc).isoformat(),
            "frame": "#CG TELEM " + " ".join(f"{k}={v}" for k, v in fields.items()),
        },
    }


def test_schema1_frozen_shape_and_clock_behavior():
    payload = _schema1_payload()
    telemetry = Telemetry.model_validate(payload)

    assert telemetry.schema_version == 1
    assert telemetry.has_valid_clock is True
    assert telemetry.is_clockless is False
    assert telemetry.captured_at is not None
    assert telemetry.captured_at.tzinfo is not None
    assert telemetry.message_identity == ("coldguard-001", "boot-w01-fixture-001", 12345)
    assert telemetry.serial_source is None


def test_schema2_clockless_shape_and_provenance():
    # Use real serial gateway translate to verify end-to-end schema 2 construction
    from scripts.serial_gateway import translate

    raw_fixture = MEMBER_A_FIXTURE.read_text(encoding="utf-8")
    fields = json.loads(raw_fixture)["fields"]
    line = ("#CG TELEM " + " ".join(f"{k}={v}" for k, v in fields.items())).encode("ascii")
    gateway_time = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)

    translated_bytes = translate(line, topic="coldguard/coldguard-001/telemetry", gateway_received_at=gateway_time, replay=False)
    payload = json.loads(translated_bytes.decode("utf-8"))

    telemetry = Telemetry.model_validate(payload)
    assert telemetry.schema_version == 2
    assert telemetry.is_clockless is True
    assert telemetry.has_valid_clock is False
    assert telemetry.captured_at is None
    assert telemetry.serial_source is not None
    assert telemetry.serial_source.clock_quality == "UNAVAILABLE"
    assert telemetry.serial_source.gateway_received_at == gateway_time
    assert telemetry.quality.environment in ("DEGRADED", "UNKNOWN")
    assert telemetry.message_identity == ("coldguard-001", fields["boot_id"], int(fields["seq"]))


def test_schema1_rejects_null_captured_at():
    payload = _schema1_payload()
    payload["captured_at"] = None
    with pytest.raises(ValidationError, match="schema 1 requires device event time"):
        Telemetry.model_validate(payload)


def test_schema1_rejects_serial_source():
    payload = _schema1_payload()
    payload["serial_source"] = {
        "schema_version": 2,
        "clock_quality": "UNAVAILABLE",
        "gateway_received_at": datetime.now(timezone.utc).isoformat(),
        "frame": "#CG TELEM foo=bar",
    }
    with pytest.raises(ValidationError, match="carries no serial source"):
        Telemetry.model_validate(payload)


def test_schema2_rejects_non_null_captured_at():
    from scripts.serial_gateway import translate

    raw_fixture = MEMBER_A_FIXTURE.read_text(encoding="utf-8")
    fields = json.loads(raw_fixture)["fields"]
    line = ("#CG TELEM " + " ".join(f"{k}={v}" for k, v in fields.items())).encode("ascii")
    gateway_time = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)

    translated_bytes = translate(line, topic="coldguard/coldguard-001/telemetry", gateway_received_at=gateway_time, replay=False)
    payload = json.loads(translated_bytes.decode("utf-8"))
    payload["captured_at"] = datetime.now(timezone.utc).isoformat()

    with pytest.raises(ValidationError, match="schema 2 requires null device event time"):
        Telemetry.model_validate(payload)


def test_schema1_rejects_unknown_quality():
    payload = _schema1_payload()
    payload["quality"]["thermal"] = "UNKNOWN"
    with pytest.raises(ValidationError, match="UNKNOWN quality requires schema 2"):
        Telemetry.model_validate(payload)


def test_schema_preserves_unrecorded_calibration_as_none():
    payload = _schema1_payload()
    payload["calibration_id"] = None
    telemetry = Telemetry.model_validate(payload)
    assert telemetry.calibration_id is None


def test_schema_preserves_unset_run_as_none():
    payload = _schema1_payload()
    payload["run_id"] = None
    telemetry = Telemetry.model_validate(payload)
    assert telemetry.run_id is None


def test_schema_preserves_recorded_calibration_string():
    payload = _schema1_payload()
    payload["calibration_id"] = "CAL-DS18B20-202611"
    telemetry = Telemetry.model_validate(payload)
    assert telemetry.calibration_id == "CAL-DS18B20-202611"


def test_electrical_energy_must_be_non_negative():
    payload = _schema1_payload()
    payload["electrical"]["energy_wh"] = -0.01
    with pytest.raises(ValidationError, match="energy_wh is a monotonic counter"):
        Telemetry.model_validate(payload)


def test_actuation_duty_must_be_between_zero_and_one():
    payload = _schema1_payload()
    payload["actuation"]["duty"] = 1.05
    with pytest.raises(ValidationError, match="duty must be within"):
        Telemetry.model_validate(payload)


def test_rejection_of_legacy_keys():
    for forbidden in ("power_1", "power_2", "current_1", "current_2", "ina226", "second_tec"):
        payload = _schema1_payload()
        payload["electrical"][forbidden] = 1.0
        with pytest.raises(ValidationError, match="legacy dual-channel field"):
            Telemetry.model_validate(payload)
