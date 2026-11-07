"""Unit and integration tests for Member A -> Member C telemetry adapter (Section 8).

Validates:
- Real committed A-W05 fixture: evidence/A/W05/schema-fixture.json
- Real committed A-W06 ACK fixture: evidence/A/W06/ack-fixture.json
- Source semantics: nan -> None, permille -> [0.0, 1.0], UNKNOWN quality preservation,
  calibration UNRECORDED -> None.
- Probe placement correctness: T2 mapped with TEC_HOT_SIDE provenance.
- Separate gateway vs physical device timestamp semantics.
- Malformed frame rejection.
- Replay flag propagation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coldguard_backend.contracts import Telemetry
from coldguard_backend.telemetry_adapter import (
    HOT_SIDE_ROM,
    TelemetryAdapterError,
    frame_to_mqtt_envelope,
    parse_serial_cmdack_frame,
    parse_serial_telemetry_frame,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
W05_FIXTURE_PATH = REPO_ROOT / "evidence" / "A" / "W05" / "schema-fixture.json"
W06_ACK_FIXTURE_PATH = REPO_ROOT / "evidence" / "A" / "W06" / "ack-fixture.json"


def test_w05_committed_fixture_translation():
    """Translate Member A committed W05 telemetry fixture into backend envelope."""
    data = json.loads(W05_FIXTURE_PATH.read_text(encoding="utf-8"))
    fields = data["fields"]

    envelope = frame_to_mqtt_envelope(fields)
    assert envelope["schema_version"] == 1  # MQTT wire schema is 1
    assert envelope["device_id"] == "coldguard-001"
    assert envelope["boot_id"] == "abcd0123"
    assert envelope["seq"] == 1
    assert envelope["calibration_id"] is None  # UNRECORDED -> None
    assert envelope["run_id"] == "CG-S1-A-001"

    # Thermal checks: T2 is hot-side probe
    assert envelope["thermal"]["t1"] == 25.0625
    assert envelope["thermal"]["t2"] == 25.0625
    assert envelope["thermal"]["t3"] == 25.0625
    assert envelope["probe_placement"]["hot_side_slot"] == "T2"
    assert envelope["probe_placement"]["hot_side_rom"] == HOT_SIDE_ROM

    # Environment & door checks: nan -> None
    assert envelope["environment"]["t_air"] is None
    assert envelope["environment"]["rh"] is None
    assert envelope["door"]["state"] == "UNKNOWN"

    # Electrical checks
    assert envelope["electrical"]["voltage_v"] == 11.9
    assert envelope["electrical"]["current_a"] == 0.0
    assert envelope["electrical"]["power_w"] == 0.0
    assert envelope["electrical"]["energy_wh"] == 12.0

    # Actuation checks: pwm_duty=0 -> duty=0.0
    assert envelope["actuation"]["cooling"] == "OFF"
    assert envelope["actuation"]["duty"] == 0.0

    # Quality checks: UNKNOWN quality preserved
    assert envelope["quality"]["overall"] == "UNKNOWN"
    assert envelope["quality"]["thermal"] == "VALID"
    assert envelope["quality"]["environment"] == "DEGRADED"

    # Timestamp checks
    assert envelope["time_sync_state"] == "DEVICE_UNSYNCHRONIZED"
    assert envelope["clock_source"] == "GATEWAY_ACQUISITION"

    # Validates against Telemetry wire model
    validated = Telemetry.model_validate(envelope)
    assert validated.device_id == "coldguard-001"


def test_serial_line_parsing_and_envelope_generation():
    """Parse a realistic #CG TELEM schema=3 line and produce validated envelope."""
    line = (
        "#CG TELEM schema=3 device_id=cg-test-01 boot_id=boot-456 seq=42 "
        "elapsed_ms=5000 uptime_ms=5000 timestamp_utc=UNAVAILABLE "
        "raw_t1_c=4.125 raw_t2_c=28.5 raw_t3_c=4.5 "
        "t_ambient_c=22.0 relative_humidity_pct=55.5 door_open=0 "
        "voltage_v=12.1 current_a=1.85 power_w=22.38 energy_wh=10.5 "
        "cooling_applied=ON pwm_duty=750 "
        "thermal_quality=VALID environment_quality=VALID electrical_quality=VALID quality=VALID "
        "calibration_id=UNRECORDED"
    )

    envelope = frame_to_mqtt_envelope(line)
    assert envelope["schema_version"] == 1
    assert envelope["device_id"] == "cg-test-01"
    assert envelope["seq"] == 42
    assert envelope["actuation"]["cooling"] == "ON"
    assert envelope["actuation"]["duty"] == 0.75  # 750 permille -> 0.75
    assert envelope["door"]["state"] == "CLOSED"
    assert envelope["thermal"]["t2"] == 28.5  # Hot side reading
    assert envelope["quality"]["overall"] == "VALID"

    # Telemetry Pydantic model validates cleanly
    model = Telemetry.model_validate(envelope)
    assert model.actuation.duty == 0.75


def test_nan_never_becomes_zero():
    """Missing measurements (nan) must become None, never 0.0."""
    line = (
        "#CG TELEM schema=3 device_id=cg-test-01 boot_id=boot-1 seq=1 uptime_ms=100 "
        "raw_t1_c=nan raw_t2_c=nan raw_t3_c=nan voltage_v=nan current_a=nan "
        "thermal_quality=DEGRADED electrical_quality=DEGRADED quality=DEGRADED"
    )
    envelope = frame_to_mqtt_envelope(line)
    assert envelope["thermal"]["t1"] is None
    assert envelope["thermal"]["t2"] is None
    assert envelope["thermal"]["t3"] is None
    assert envelope["electrical"]["voltage_v"] is None
    assert envelope["electrical"]["current_a"] is None
    assert envelope["quality"]["thermal"] == "DEGRADED"


def test_malformed_serial_frames_rejected():
    """Corrupted lines must raise TelemetryAdapterError with diagnostics."""
    with pytest.raises(TelemetryAdapterError, match="prefix"):
        parse_serial_telemetry_frame("INVALID PREFIX schema=3")

    with pytest.raises(TelemetryAdapterError, match="Empty"):
        parse_serial_telemetry_frame("#CG TELEM")

    with pytest.raises(TelemetryAdapterError, match="Unsupported serial schema"):
        parse_serial_telemetry_frame("#CG TELEM schema=99 device_id=test")


def test_replay_flag_preservation():
    """Historical file replay sets is_replay=True."""
    line = "#CG TELEM schema=3 device_id=test boot_id=b1 seq=1 uptime_ms=10"
    live_env = frame_to_mqtt_envelope(line, is_replay=False)
    assert live_env["is_replay"] is False

    replay_env = frame_to_mqtt_envelope(line, is_replay=True)
    assert replay_env["is_replay"] is True


def test_w06_committed_ack_fixture_parsing():
    """Parse Member A committed command ACK fixtures across all scenarios."""
    data = json.loads(W06_ACK_FIXTURE_PATH.read_text(encoding="utf-8"))
    fixtures = data["fixtures"]

    for name, fix in fixtures.items():
        raw_line = fix["raw_line"]
        ack = parse_serial_cmdack_frame(raw_line)
        assert ack["event"] == "ACK"
        assert ack["command_id"] == fix["fields"]["command_id"]
        assert ack["status"] == fix["fields"]["status"]
        assert ack["reason"] == fix["fields"]["reason"]
        assert ack["device_id"] == "coldguard-001"
        assert ack["uptime_ms"] == 123456
        assert ack["ack_seq"] == 42
