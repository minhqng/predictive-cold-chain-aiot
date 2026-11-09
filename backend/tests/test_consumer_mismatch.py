"""Topic/device mismatch + malformed namespace through the actual consumer path (C-W03-02/06).

Runs only with real providers. Proves, through the real backend
``MqttIngestConsumer`` (not a direct function call): a payload whose
``device_id`` disagrees with the topic device segment is stored as
``REJECTED_TOPIC_MISMATCH`` raw evidence with diagnostics and yields
no normalized sample; a malformed telemetry namespace is rejected the
same way; and the consumer metrics expose the rejection. Completion
is condition-driven polling, never sleep-and-assume.
"""

import hashlib
import json
import os
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from coldguard_backend.mqtt_consumer import MqttIngestConsumer
from coldguard_backend.simulator import build_telemetry
from tests.mqtt_testkit import (
    has_test_db,
    has_test_mqtt,
    make_test_config,
    mqtt_params,
    wait_for,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module", autouse=True)
def _migrated_suite_schema():
    """Give the disposable suite database the current schema before tests run.

    The owned runners create the suite database empty and nothing in this
    module's scope ever migrated it, so these real-provider proofs only
    passed when an alphabetically-earlier module had already done so. The
    alembic upgrade is idempotent when the schema already exists.
    """
    if not os.environ.get("COLDGUARD_TEST_DATABASE_URL"):
        return
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(BACKEND_DIR / "src/coldguard_backend/migrations")
    )
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = os.environ["COLDGUARD_TEST_DATABASE_URL"]
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

needs_real_providers = pytest.mark.skipif(
    not (has_test_db() and has_test_mqtt()),
    reason="requires COLDGUARD_TEST_DATABASE_URL and COLDGUARD_TEST_MQTT_HOST",
)

OWN_TOPIC = "coldguard/coldguard-001/telemetry"


def _db() -> str:
    import os

    return os.environ["COLDGUARD_TEST_DATABASE_URL"]


def _wire(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _publish_own_topic(wire: bytes) -> None:
    params = mqtt_params()
    publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    try:
        publisher.username_pw_set(params["device_user"], params["device_password"])
        publisher.connect(params["host"], params["port"], keepalive=15)
        publisher.loop_start()
        info = publisher.publish(OWN_TOPIC, wire, qos=1, retain=False)
        info.wait_for_publish(timeout=10)
        assert info.is_published(), "PUBACK missing for mismatch delivery"
    finally:
        publisher.loop_stop()
        try:
            publisher.disconnect()
        except Exception:  # noqa: BLE001 - test teardown
            pass


def _raw_row(sha: str):
    engine = create_engine(_db())
    try:
        with engine.connect() as connection:
            return connection.execute(
                text(
                    "SELECT ingest_status, validation_errors FROM telemetry_raw "
                    "WHERE payload_sha256 = :sha"
                ),
                {"sha": sha},
            ).first()
    finally:
        engine.dispose()


def _normalized_for_boot(boot_id: str) -> int:
    engine = create_engine(_db())
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT count(*) FROM telemetry WHERE boot_id = :boot"),
                {"boot": boot_id},
            ).scalar()
    finally:
        engine.dispose()


@needs_real_providers
def test_consumer_rejects_topic_mismatch_without_normalized_sample():
    params = mqtt_params()
    boot_id = f"boot-mismatch-{uuid.uuid4().hex[:8]}"
    run_id = f"CG-W03-MISMATCH-{uuid.uuid4().hex[:8]}"
    payload = build_telemetry(boot_id=boot_id, seq=1, run_id=run_id)
    payload["device_id"] = "coldguard-999"
    wire = _wire(payload)
    sha = hashlib.sha256(wire).hexdigest()
    consumer = MqttIngestConsumer.from_config(
        make_test_config(mqtt_user=params["backend_user"], mqtt_password=params["backend_password"])
    )
    consumer.start()
    try:
        _publish_own_topic(wire)
        assert wait_for(lambda: _raw_row(sha) is not None, timeout_s=30), (
            "mismatched delivery never landed in raw storage"
        )
    finally:
        consumer.stop()
    row = _raw_row(sha)
    assert row[0] == "REJECTED_TOPIC_MISMATCH"
    assert row[1] and any(err.get("code") == "TOPIC_MISMATCH" for err in row[1])
    assert _normalized_for_boot(boot_id) == 0, (
        "topic/device mismatch must not create a normalized physical sample"
    )
    assert consumer.metrics.snapshot()["rejected_topic_mismatch"] >= 1


@needs_real_providers
def test_consumer_path_rejects_malformed_namespace():
    # A malformed telemetry namespace cannot be produced over real MQTT
    # with the available principals (the device ACL permits only its own
    # topics; the backend principal cannot publish at all), so this case
    # goes through the consumer's real ingest path (the exact function
    # ``_on_message`` delegates to) with a real database.
    import os

    from sqlalchemy import create_engine

    from coldguard_backend.ingest import ingest_message

    boot_id = f"boot-badns-{uuid.uuid4().hex[:8]}"
    run_id = f"CG-W03-BADNS-{uuid.uuid4().hex[:8]}"
    payload = build_telemetry(boot_id=boot_id, seq=1, run_id=run_id)
    wire = _wire(payload)
    sha = hashlib.sha256(wire).hexdigest()
    engine = create_engine(os.environ["COLDGUARD_TEST_DATABASE_URL"])
    try:
        outcome = ingest_message(engine, topic="coldguard//telemetry", payload=wire)
    finally:
        engine.dispose()
    assert outcome["raw_status"] == "REJECTED_TOPIC_MISMATCH"
    assert outcome["normalized"] == "rejected:REJECTED_TOPIC_MISMATCH"
    row = _raw_row(sha)
    assert row is not None and row[0] == "REJECTED_TOPIC_MISMATCH"
    assert row[1] and any(err.get("code") == "MALFORMED_TOPIC" for err in row[1])
    assert _normalized_for_boot(boot_id) == 0
