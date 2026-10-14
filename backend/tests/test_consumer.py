"""Backend MQTT consumer proof against real broker + PostgreSQL (C-W02-03/04).

Runs only with COLDGUARD_TEST_DATABASE_URL and COLDGUARD_TEST_MQTT_HOST
set. Proves: a real subscribed consumer receives MQTT messages and
commits matching raw rows, exact payloads are recoverable, malformed
and invalid-schema payloads are retained with diagnostics, DB failure
is counted (never silent-green), refused credentials raise a
distinguishable error, and no duplicate consumer can start from one
instance.

Completion is condition-driven (DB polling), never sleep-and-assume.
"""

import hashlib
import json
import uuid

import pytest
from sqlalchemy import create_engine, text

from coldguard_backend.mqtt_consumer import MqttIngestConsumer
from coldguard_backend.simulator import build_telemetry, run_simulation
from tests.mqtt_testkit import (
    has_test_db,
    has_test_mqtt,
    make_test_config,
    mqtt_params,
    wait_for,
)

needs_real_providers = pytest.mark.skipif(
    not (has_test_db() and has_test_mqtt()),
    reason="requires COLDGUARD_TEST_DATABASE_URL and COLDGUARD_TEST_MQTT_HOST",
)

TELEMETRY_TOPIC = "coldguard/coldguard-001/telemetry"


def _db() -> str:
    import os

    return os.environ["COLDGUARD_TEST_DATABASE_URL"]


def _rows_for_run(run_id: str, topic: str = TELEMETRY_TOPIC) -> list:
    engine = create_engine(_db())
    try:
        with engine.connect() as connection:
            return connection.execute(
                text(
                    "SELECT seq, ingest_status, raw_payload, payload_sha256, "
                    "device_id, boot_id, run_id "
                    "FROM telemetry_raw WHERE run_id = :run_id AND topic = :topic "
                    "ORDER BY seq"
                ),
                {"run_id": run_id, "topic": topic},
            ).all()
    finally:
        engine.dispose()


def _row_for_sha(sha: str):
    engine = create_engine(_db())
    try:
        with engine.connect() as connection:
            return connection.execute(
                text(
                    "SELECT ingest_status, raw_payload, validation_errors "
                    "FROM telemetry_raw WHERE payload_sha256 = :sha"
                ),
                {"sha": sha},
            ).first()
    finally:
        engine.dispose()


def _backend_consumer() -> MqttIngestConsumer:
    params = mqtt_params()
    return MqttIngestConsumer.from_config(
        make_test_config(mqtt_user=params["backend_user"], mqtt_password=params["backend_password"])
    )


@needs_real_providers
def test_consumer_ingests_valid_telemetry_with_exact_recovery():
    params = mqtt_params()
    run_id = f"CG-W02-CONS-{uuid.uuid4().hex[:8]}"
    boot_id = f"boot-cons-{uuid.uuid4().hex[:8]}"
    consumer = _backend_consumer()
    consumer.start()
    try:
        result = run_simulation(
            host=params["host"],
            port=params["port"],
            username=params["device_user"],
            password=params["device_password"],
            boot_id=boot_id,
            run_id=run_id,
            count=5,
            start_seq=100,
        )
        assert result["publish_acknowledged"] == 5
        assert wait_for(lambda: len(_rows_for_run(run_id)) == 5, timeout_s=30), (
            "backend received fewer committed raw rows than published messages"
        )
    finally:
        consumer.stop()
    rows = _rows_for_run(run_id)
    assert [row[0] for row in rows] == [100, 101, 102, 103, 104]
    assert {row[1] for row in rows} == {"RECEIVED_VALID"}
    expected_wire = json.dumps(
        build_telemetry(boot_id=boot_id, seq=100, run_id=run_id),
        separators=(",", ":"),
        sort_keys=True,
    )
    assert rows[0][2] == expected_wire, "stored payload is not byte-identical"
    assert rows[0][3] == hashlib.sha256(expected_wire.encode()).hexdigest()
    assert (rows[0][4], rows[0][5], rows[0][6]) == ("coldguard-001", boot_id, run_id)


@needs_real_providers
def test_consumer_retains_malformed_and_invalid_payloads():
    import paho.mqtt.client as mqtt

    params = mqtt_params()
    consumer = _backend_consumer()
    consumer.start()
    malformed = b"{broken-json-sequence"
    invalid_doc = build_telemetry(boot_id="boot-invalid-001", seq=1, run_id="r")
    del invalid_doc["boot_id"]
    invalid_wire = json.dumps(invalid_doc, sort_keys=True).encode()
    malformed_sha = hashlib.sha256(malformed).hexdigest()
    invalid_sha = hashlib.sha256(invalid_wire).hexdigest()
    publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    try:
        publisher.username_pw_set(params["device_user"], params["device_password"])
        publisher.connect(params["host"], params["port"], keepalive=15)
        publisher.loop_start()
        publisher.publish(TELEMETRY_TOPIC, malformed, qos=1).wait_for_publish(timeout=10)
        publisher.publish(TELEMETRY_TOPIC, invalid_wire, qos=1).wait_for_publish(timeout=10)
        assert wait_for(lambda: _row_for_sha(malformed_sha) is not None, timeout_s=20), (
            "malformed payload never landed in raw storage"
        )
        assert wait_for(lambda: _row_for_sha(invalid_sha) is not None, timeout_s=20), (
            "invalid-schema payload never landed in raw storage"
        )
    finally:
        publisher.loop_stop()
        try:
            publisher.disconnect()
        except Exception:  # noqa: BLE001 - test teardown
            pass
        consumer.stop()
    malformed_row = _row_for_sha(malformed_sha)
    invalid_row = _row_for_sha(invalid_sha)
    assert malformed_row[0] == "RECEIVED_MALFORMED_JSON"
    assert malformed_row[1] == malformed.decode()
    assert malformed_row[2], "malformed row needs diagnostics"
    assert invalid_row[0] == "RECEIVED_INVALID_SCHEMA"
    assert invalid_row[2], "invalid-schema row needs diagnostics"


@needs_real_providers
def test_db_failure_counted_never_silent_green():
    import paho.mqtt.client as mqtt

    params = mqtt_params()
    config = make_test_config(
        mqtt_user=params["backend_user"], mqtt_password=params["backend_password"]
    )
    broken = MqttIngestConsumer(config)
    # Point the engine at a closed port: inserts must fail loudly.
    import dataclasses

    broken._config = dataclasses.replace(broken._config, postgres_port=9)
    broken.start()
    try:
        publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        publisher.username_pw_set(params["device_user"], params["device_password"])
        publisher.connect(params["host"], params["port"], keepalive=15)
        publisher.loop_start()
        try:
            marker = f"dbfail-{uuid.uuid4().hex[:12]}".encode()
            publisher.publish(TELEMETRY_TOPIC, marker, qos=1).wait_for_publish(timeout=10)
            assert wait_for(lambda: broken.snapshot()["errors"] >= 1, timeout_s=30), (
                "DB outage during ingest produced no observable error state"
            )
        finally:
            publisher.loop_stop()
            try:
                publisher.disconnect()
            except Exception:  # noqa: BLE001 - test teardown
                pass
    finally:
        broken.stop()
    snapshot = broken.snapshot()
    assert snapshot["persisted"] == 0, "failed inserts must not count as persisted"
    assert snapshot["received"] >= 1


@needs_real_providers
def test_refused_credentials_raise_distinguishable_error():
    params = mqtt_params()
    consumer = MqttIngestConsumer(
        make_test_config(mqtt_user=params["backend_user"], mqtt_password="wrong-password")
    )
    with pytest.raises(ConnectionError, match="authentication refused"):
        consumer.start()


@needs_real_providers
def test_double_start_rejected_and_stop_idempotent():
    consumer = _backend_consumer()
    consumer.start()
    try:
        with pytest.raises(RuntimeError, match="already running"):
            consumer.start()
    finally:
        consumer.stop()
        consumer.stop()
