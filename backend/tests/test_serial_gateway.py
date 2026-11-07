"""Verify Member A serial input at the gateway and provider boundaries."""

from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text

from coldguard_backend import ingest
from coldguard_backend.mqtt_consumer import MqttIngestConsumer
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.twin_store import device_twin, reconcile_reported_boot
from coldguard_backend.validation import validate_telemetry_payload
from scripts.serial_gateway import (
    Publisher, SerialFramer, TelemetryError, run_live, translate,
)
from tests.mqtt_testkit import has_test_db, has_test_mqtt, make_test_config, mqtt_params, wait_for

BACKEND = Path(__file__).resolve().parents[1]
FIXTURE = BACKEND.parent / "evidence/A/W05/schema-fixture.json"
DEVICE = "coldguard-001"
TOPIC = f"coldguard/{DEVICE}/telemetry"
RECEIVED = datetime(2026, 10, 30, tzinfo=timezone.utc)


def _frame(**overrides):
    fields = json.loads(FIXTURE.read_text(encoding="utf-8"))["fields"]
    fields.update(overrides)
    if fields["schema"] == 2:
        for key in (
            "command_id", "desired_cooling", "desired_duty_permille", "last_ack_status", "last_ack_reason",
        ):
            del fields[key]
    return ("#CG TELEM " + " ".join(f"{key}={value}" for key, value in fields.items())).encode()


def _translate(frame, **overrides):
    return translate(frame, **({"topic": TOPIC, "gateway_received_at": RECEIVED, "replay": False} | overrides))


@pytest.mark.parametrize("version", [2, 3])
def test_committed_member_a_fixture_preserves_clock_and_measurement_semantics(version):
    frame = _frame(
        schema=version, cooling_applied="ON", pwm_duty=250,
        raw_t1_c="nan", raw_t1_status="MISSING",
    )
    payload = json.loads(_translate(frame))
    assert payload["captured_at"] is None
    assert payload["uptime_ms"] == 1_000_000
    assert payload["serial_source"] == {
        "frame": frame.decode(), "schema_version": version,
        "clock_quality": "UNAVAILABLE", "gateway_received_at": RECEIVED.isoformat(),
    }
    assert payload["quality"]["overall"] == "UNKNOWN"
    assert payload["quality"]["thermal"] == "DEGRADED"
    assert payload["thermal"]["t1"] is None
    assert payload["thermal"]["t2"] == 25.0625
    assert payload["thermal"]["t2_role"] == "TEC_HOT_SIDE"
    assert payload["environment"] == {"t_air": None, "rh": None}
    assert payload["door"]["state"] == "UNKNOWN"
    assert payload["electrical"]["current_a"] == 0
    assert payload["actuation"] == {"cooling": "ON", "duty": 0.25}
    assert payload["calibration_id"] is None
    assert (payload["device_id"], payload["boot_id"], payload["seq"]) == (DEVICE, "abcd0123", 1)
    assert payload["run_id"] == "CG-S1-A-001"
    assert validate_telemetry_payload(payload)[0] is not None


@pytest.mark.parametrize("change", [
    {"schema": 1}, {"schema": 9}, {"seq": 0}, {"raw_t2_c": "1e999"},
    {"pwm_duty": 1001}, {"timestamp_utc": "2026-10-30T00:00:00Z"},
    {"device_id": "other"}, {"thermal_quality": "MAGIC"},
])
def test_invalid_or_untranslatable_source_fields(change):
    with pytest.raises(TelemetryError):
        _translate(_frame(**change))


@pytest.mark.parametrize(("cooling", "duty"), [("OFF", 250), ("ON", 0)])
def test_applied_state_and_duty_stay_independent(cooling, duty):
    # Member A's own harness (firmware/tools/tests/cg_w05_harness.c) proves a
    # requested duty can reach the line while the output layer never engaged,
    # and that an energized output can read zero duty. Applied is not requested.
    payload = json.loads(_translate(_frame(cooling_applied=cooling, pwm_duty=duty)))
    assert payload["actuation"] == {"cooling": cooling, "duty": duty / 1000}


def test_serial_framing_discards_oversize_and_preserves_fragments():
    framer = SerialFramer()
    assert list(framer.feed(b"x" * 4000)) == []
    assert list(framer.feed(b"overflow\n#CG CMDACK foo=bar\r\n#CG TE")) == [b"#CG CMDACK foo=bar"]
    assert list(framer.feed(b"")) == []
    assert list(framer.feed(b"LEM schema=3\r\n")) == [b"#CG TELEM schema=3"]
    for invalid in (_frame() + b" seq=9", b"#CG TELEM schema=3", _frame() + b"\x00"):
        with pytest.raises(TelemetryError):
            _translate(invalid)
    with pytest.raises(TelemetryError, match="missing raw_t2_c or raw_t2_status"):
        _translate(_frame().replace(b" raw_t2_status=OK", b""))


def test_clockless_wire_requires_typed_provenance():
    payload = json.loads(_translate(_frame()))
    for replacement in (
        {"captured_at": RECEIVED.isoformat()},
        {"serial_source": None},
        {"serial_source": {**payload["serial_source"], "gateway_received_at": 1234}},
        {"serial_source": {**payload["serial_source"], "schema_version": 2}},
        {"serial_source": {**payload["serial_source"], "frame": _frame(seq=2).decode()}},
        {"uptime_ms": 1},
        {"actuation": {"cooling": "ON", "duty": 0.0}},
        {"thermal": {**payload["thermal"], "t2": 999}},
    ):
        assert validate_telemetry_payload(payload | replacement)[0] is None


def test_unset_run_label_is_preserved_as_source_text_and_normalized_to_null():
    payload = json.loads(_translate(_frame(run_id="UNSET")))
    assert payload["run_id"] is None
    assert " run_id=UNSET " in payload["serial_source"]["frame"]


@pytest.fixture
def engine():
    db = create_engine(os.environ["COLDGUARD_TEST_DATABASE_URL"])
    yield db
    db.dispose()


def _current(engine, device):
    with engine.connect() as connection:
        return connection.execute(select(device_twin).where(
            device_twin.c.device_id == device,
        )).mappings().one_or_none()


@pytest.mark.skipif(not has_test_db(), reason="requires real PostgreSQL")
def test_clockless_projection_failure_retains_raw_and_retries(engine, monkeypatch):
    device = f"serial-failure-{uuid4().hex}"
    topic = f"coldguard/{device}/telemetry"
    wire = _translate(_frame(device_id=device), topic=topic)
    project = ingest.project_reported

    def fail(connection, row_id):
        project(connection, row_id)
        connection.execute(text("SELECT 1 / 0"))

    try:
        with monkeypatch.context() as patch:
            patch.setattr(ingest, "project_reported", fail)
            result = ingest.ingest_message(engine, topic=topic, payload=wire)
        assert result["normalized"] == "failed"
        assert _current(engine, device) is None
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT raw_payload FROM telemetry_raw WHERE id=:id"), {"id": result["raw_id"]},
            ).scalar_one() == wire.decode()
            assert connection.execute(select(telemetry.c.id).where(
                telemetry.c.device_id == device,
            )).first() is None
        retry = ingest.ingest_message(engine, topic=topic, payload=wire)
        assert retry["normalized"]["outcome"] == "inserted"
        assert _current(engine, device)["reported_state"]["raw_id"] == retry["raw_id"]
    finally:
        with engine.begin() as connection:
            connection.execute(device_twin.delete().where(device_twin.c.device_id == device))
            connection.execute(telemetry.delete().where(telemetry.c.device_id == device))


@pytest.mark.skipif(not (has_test_db() and has_test_mqtt()), reason="requires PostgreSQL and Mosquitto")
def test_gateway_serial_restart_replay_and_reported_twin(engine, tmp_path, monkeypatch):
    params = mqtt_params()
    boot, next_boot = uuid4().hex, uuid4().hex
    consumer = MqttIngestConsumer.from_config(make_test_config(
        mqtt_user=params["backend_user"], mqtt_password=params["backend_password"],
    ))
    topic = TOPIC
    stop = Event()
    opened = []

    def history():
        with engine.connect() as connection:
            return connection.execute(select(telemetry).where(
                telemetry.c.boot_id.in_([boot, next_boot]),
            )).mappings().all()

    def connect():
        return Publisher(
            host=params["host"], port=params["port"], client_id=f"w04-test-{boot}",
            username=params["device_user"], password=params["device_password"],
        ).session()

    class SerialInput(BytesIO):
        def reset_input_buffer(self):
            opened.append(True)

        def read(self, size):
            chunk = super().read(size)
            if not chunk:
                if len(opened) == 1:
                    raise OSError("test serial disconnection")
                stop.set()
            return chunk

    first = _frame(boot_id=boot, seq=1)
    latest = _frame(boot_id=boot, seq=3)
    chunks = iter([
        first + b"\n" + b"#CG TELEM schema=3 seq=400",
        b"\n".join((
            b"#CG CMDACK test=no-command-output", latest, _frame(boot_id=boot, seq=2),
            latest, _frame(boot_id=boot, seq=3, voltage_v=12.4),
            _frame(boot_id=next_boot, seq=1),
        )) + b"\n",
    ])
    assert _current(engine, DEVICE) is None
    consumer.start()
    try:
        # Retained, synthetic, and capture replay arrive before any live boot.
        with connect() as publisher:
            retained = _translate(_frame(boot_id=boot, seq=98))
            info = publisher.client.publish(topic, retained, qos=1, retain=True)
            publisher._wait(lambda: publisher.ack is not None and publisher.ack[0] == info.mid)
            assert wait_for(lambda: len(history()) == 1, timeout_s=8)
            synthetic = json.loads(_translate(_frame(boot_id=boot, seq=99)))
            publisher.publish(topic, json.dumps(synthetic | {"synthetic": True}).encode())
        capture = tmp_path / "capture.txt"
        capture.write_bytes(_frame(boot_id=boot, seq=100) + b"\n")
        monkeypatch.setenv("MQTT_USERNAME", params["device_user"])
        monkeypatch.setenv("MQTT_PASSWORD", params["device_password"])
        subprocess.run([
            sys.executable, str(BACKEND / "scripts/serial_gateway.py"), "--replay-file", str(capture),
            "--broker-host", params["host"], "--broker-port", str(params["port"]),
            "--device-id", DEVICE,
        ], check=True, timeout=15)
        assert wait_for(lambda: len(history()) == 3, timeout_s=8)
        assert all(not row["twin_eligible"] for row in history())
        assert _current(engine, DEVICE) is None

        @contextmanager
        def open_serial():
            with SerialInput(next(chunks)) as serial:
                yield serial

        run_live(open_serial, connect, topic=topic, stop=stop, retry_delay=0)
        assert len(opened) == 2
        assert wait_for(lambda: len(history()) == 7, timeout_s=8)
        assert wait_for(lambda: consumer.metrics.snapshot()["conflicts"] == 1, timeout_s=8)
        assert consumer.metrics.snapshot()["exact_duplicates"] == 1
        current = _current(engine, DEVICE)
        assert (current["last_boot_id"], current["last_seq"]) == (boot, 3)
        observed = current["reported_state"]
        assert observed["captured_at"] is None
        assert observed["serial_source"]["clock_quality"] == "UNAVAILABLE"
        assert observed["serial_source"]["uptime_ms"] == 1_000_000
        with engine.begin() as connection:
            raw = connection.execute(text(
                "SELECT captured_at, raw_json FROM telemetry_raw WHERE id=:id",
            ), {"id": observed["raw_id"]}).one()
            assert raw.captured_at is None
            assert raw.raw_json["serial_source"]["frame"] == latest.decode()
            reconcile_reported_boot(
                connection, device_id=DEVICE, expected_boot_id=boot, new_boot_id=next_boot,
            )
        assert _current(engine, DEVICE)["last_boot_id"] == next_boot
    finally:
        consumer.stop()
        try:
            with connect() as publisher:
                info = publisher.client.publish(topic, b"", qos=1, retain=True)
                publisher._wait(lambda: publisher.ack is not None and publisher.ack[0] == info.mid)
        finally:
            with engine.begin() as connection:
                connection.execute(text(
                    "DELETE FROM device_twin_retired_boot WHERE device_id=:device AND boot_id=:boot",
                ), {"device": DEVICE, "boot": boot})
                connection.execute(device_twin.delete().where(
                    device_twin.c.device_id == DEVICE,
                    device_twin.c.last_boot_id.in_([boot, next_boot]),
                ))
                connection.execute(telemetry.delete().where(telemetry.c.boot_id.in_([boot, next_boot])))
