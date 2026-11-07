"""Twin invariants against PostgreSQL and the real MQTT consumer."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import paho.mqtt.client as mqtt
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text

from coldguard_backend.contracts import Telemetry
from coldguard_backend.ingest import ingest_message
from coldguard_backend.mqtt_consumer import SUBSCRIPTIONS, MqttIngestConsumer
from coldguard_backend.normalized_store import insert_normalized, map_to_row, telemetry
from coldguard_backend.raw_store import store_raw
from coldguard_backend.twin_store import (
    TwinBootConflict,
    TwinVersionConflict,
    device_twin,
    reconcile_reported_boot,
    update_desired,
)
from tests.mqtt_testkit import has_test_db, has_test_mqtt, make_test_config, mqtt_params, wait_for

pytestmark = pytest.mark.skipif(not has_test_db(), reason="requires real PostgreSQL")

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "telemetry_v0.json"


@pytest.fixture
def engine():
    db = create_engine(os.environ["COLDGUARD_TEST_DATABASE_URL"])
    yield db
    db.dispose()


@pytest.fixture
def device_id():
    return f"twin-test-{uuid4().hex}"


def _payload(device_id, seq, **fields):
    # Exercise live-envelope behavior with generated test messages.
    payload = json.loads(FIXTURE.read_text())
    del payload["synthetic"], payload["note"]
    payload.update(device_id=device_id, boot_id="boot-z", seq=seq)
    payload.update(fields)
    return payload


def _ingest(target, payload, *, topic=None):
    return ingest_message(
        target,
        topic=topic or f"coldguard/{payload['device_id']}/telemetry",
        payload=json.dumps(payload).encode(),
    )


def _twin(engine, device_id):
    with engine.connect() as connection:
        return connection.execute(
            select(device_twin).where(device_twin.c.device_id == device_id)
        ).mappings().one_or_none()


def _history(engine, device_id):
    with engine.connect() as connection:
        return connection.execute(
            select(telemetry).where(telemetry.c.device_id == device_id)
        ).mappings().all()


def _race(*operations):
    gate = Barrier(len(operations), timeout=10)

    def run(operation):
        gate.wait()
        return operation()

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(run, operation) for operation in operations]
        return [future.result(timeout=20) for future in futures]


def test_seq_freshness_and_duplicate_provenance(engine, device_id):
    first = _payload(device_id, 100)
    assert _ingest(engine, first)["normalized"]["outcome"] == "inserted"
    latest = _payload(device_id, 102, captured_at="2001-01-01T00:00:00Z")
    inserted = _ingest(engine, latest)
    before = _twin(engine, device_id)
    assert before["last_seq"] == 102
    assert before["twin_version"] == 2
    assert before["reported_state"]["raw_id"] == inserted["raw_id"]
    assert before["reported_state"]["telemetry_id"] == inserted["normalized"]["id"]
    assert before["device_mode"] == "ONLINE_NORMAL"

    assert _ingest(engine, _payload(device_id, 101))["normalized"]["outcome"] == "inserted"
    assert _ingest(engine, latest)["normalized"]["outcome"] == "exact_duplicate"
    conflict = _ingest(engine, {**latest, "door": {"state": "OPEN"}})
    assert conflict["normalized"]["outcome"] == "conflict"
    assert conflict["raw_id"] != inserted["raw_id"]
    assert {row["seq"] for row in _history(engine, device_id)} == {100, 101, 102}
    assert _twin(engine, device_id) == before


def test_unverified_boot_stays_history_until_reconciliation(engine, device_id):
    _ingest(engine, _payload(device_id, 100))
    # Equal device timestamps and a later receipt cannot establish boot order.
    _ingest(engine, _payload(device_id, 0, boot_id="boot-a"))
    _ingest(engine, _payload(device_id, 1, boot_id="boot-a"))
    _ingest(engine, _payload(device_id, 999, boot_id="boot-a", replay=True))
    _ingest(engine, _payload(device_id, 0, boot_id="history-only", replay=True))
    assert _twin(engine, device_id)["last_boot_id"] == "boot-z"

    with engine.begin() as connection:
        with pytest.raises(TwinBootConflict, match="no eligible observation"):
            reconcile_reported_boot(
                connection, device_id=device_id, expected_boot_id="boot-z",
                new_boot_id="history-only",
            )
        assert reconcile_reported_boot(
            connection, device_id=device_id, expected_boot_id="boot-z", new_boot_id="boot-a",
        ) == 2

    # Re-open the database pool to exercise persisted state across restart.
    engine.dispose()
    before = _twin(engine, device_id)
    assert (before["last_boot_id"], before["last_seq"]) == ("boot-a", 1)
    _ingest(engine, _payload(device_id, 1000))
    _ingest(engine, _payload(device_id, 1000, boot_id="boot-a", replay=True))
    assert _twin(engine, device_id) == before
    with engine.begin() as connection:
        with pytest.raises(TwinBootConflict, match="retired"):
            reconcile_reported_boot(
                connection, device_id=device_id, expected_boot_id="boot-a", new_boot_id="boot-z",
            )
        with pytest.raises(TwinBootConflict, match="current boot did not match"):
            reconcile_reported_boot(
                connection, device_id=device_id, expected_boot_id="boot-z", new_boot_id="boot-a",
            )
    _ingest(engine, _payload(device_id, 2, boot_id="boot-a"))
    assert _twin(engine, device_id)["last_seq"] == 2
    assert len(_history(engine, device_id)) == 8


@pytest.mark.parametrize("marker", [{"synthetic": True}, {"replay": True}, {"replay": "false"}])
def test_history_only_delivery_cannot_initialize_or_be_promoted(engine, device_id, marker):
    payload = _payload(device_id, 1)
    inserted = _ingest(engine, {**payload, **marker})
    assert inserted["normalized"]["outcome"] == "inserted"
    assert _ingest(engine, payload)["normalized"]["outcome"] == "exact_duplicate"
    assert _history(engine, device_id)[0]["twin_eligible"] is False
    assert _twin(engine, device_id) is None


def test_rejected_or_non_observation_cannot_project(engine, device_id):
    payload = _payload(device_id, 1)
    assert _ingest(engine, payload, topic="coldguard/other/telemetry")["normalized"].startswith(
        "rejected:"
    )
    assert _ingest(engine, payload, topic=f"coldguard/{device_id}/state")["normalized"] == "observed"
    assert _ingest(engine, {**payload, "seq": "1"})["normalized"].startswith("rejected:")
    assert not _history(engine, device_id)
    assert _twin(engine, device_id) is None


@pytest.mark.parametrize("caller_transaction", [False, True])
def test_projection_failure_rolls_back_normalized_and_recovers(
    engine, device_id, monkeypatch, caller_transaction,
):
    from coldguard_backend import ingest

    def fail_after_projection(connection, telemetry_id):
        project(connection, telemetry_id)
        # A real PostgreSQL failure also tests that the caller transaction
        # stays usable after rolling back the normalization savepoint.
        connection.execute(text("SELECT 1 / 0"))

    payload = _payload(device_id, 1)
    project = ingest.project_reported
    with monkeypatch.context() as patch:
        patch.setattr(ingest, "project_reported", fail_after_projection)
        if caller_transaction:
            with engine.begin() as connection:
                failed = _ingest(connection, payload)
                assert connection.execute(text("SELECT 1")).scalar_one() == 1
        else:
            failed = _ingest(engine, payload)
    assert failed["normalized"] == "failed"
    assert _twin(engine, device_id) is None
    assert not _history(engine, device_id)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT ingest_status FROM telemetry_raw WHERE id = :id"), {"id": failed["raw_id"]}
        ).scalar_one() == "RECEIVED_VALID"

    retry = _ingest(engine, payload)
    assert retry["normalized"]["outcome"] == "inserted"
    assert _twin(engine, device_id)["reported_state"]["raw_id"] == retry["raw_id"]
    assert len(_history(engine, device_id)) == 1


def _desired(engine, device_id, expected_version, desired_state):
    with engine.begin() as connection:
        return update_desired(
            connection, device_id=device_id, desired_state=desired_state,
            expected_version=expected_version,
        )


def test_desired_intent_is_independent_of_observation(engine, device_id):
    assert _desired(engine, device_id, 0, {"cooling": "OFF"}) == 1
    desired_only = _twin(engine, device_id)
    assert desired_only["reported_state"] == desired_only["derived_state"] == {}
    assert desired_only["last_reported_at"] is None
    _ingest(engine, _payload(device_id, 1))
    reported = _twin(engine, device_id)
    assert reported["reported_state"]["applied_cooling"] == "ON"
    assert reported["desired_state"] == {"cooling": "OFF"}
    assert _desired(engine, device_id, 2, {"cooling": "ON"}) == 3
    updated = _twin(engine, device_id)
    assert updated["reported_state"] == reported["reported_state"]
    assert updated["last_reported_at"] == reported["last_reported_at"]
    assert updated["last_derived_at"] is None


def test_concurrent_first_reported_writes_converge_to_max_seq(engine, device_id):
    low, high = _race(
        lambda: _ingest(engine, _payload(device_id, 100)),
        lambda: _ingest(engine, _payload(device_id, 102)),
    )
    assert all(result["normalized"]["outcome"] == "inserted" for result in (low, high))
    assert _twin(engine, device_id)["reported_state"]["telemetry_id"] == high["normalized"]["id"]
    assert len(_history(engine, device_id)) == 2


def test_concurrent_first_boots_preserve_one_current_boot(engine, device_id):
    first = _payload(device_id, 100, boot_id="boot-a", captured_at="2099-01-01T00:00:00Z")
    second = _payload(device_id, 1, boot_id="boot-z", captured_at="2001-01-01T00:00:00Z")
    outcomes = _race(lambda: _ingest(engine, first), lambda: _ingest(engine, second))
    assert all(result["normalized"]["outcome"] == "inserted" for result in outcomes)
    state = _twin(engine, device_id)
    assert state["twin_version"] == 1
    assert (state["last_boot_id"], state["last_seq"]) in {("boot-a", 100), ("boot-z", 1)}
    assert len(_history(engine, device_id)) == 2

    other = second if state["last_boot_id"] == first["boot_id"] else first
    _ingest(engine, {**other, "seq": other["seq"] + 1})
    assert _twin(engine, device_id) == state


def test_concurrent_live_and_replay_duplicate_use_first_admission(engine, device_id):
    live = _payload(device_id, 1)
    outcomes = _race(
        lambda: _ingest(engine, live),
        lambda: _ingest(engine, {**live, "replay": True}),
    )
    assert {result["normalized"]["outcome"] for result in outcomes} == {
        "inserted", "exact_duplicate",
    }
    [row] = _history(engine, device_id)
    assert row["id"] == outcomes[0]["normalized"]["id"] == outcomes[1]["normalized"]["id"]
    assert row["twin_eligible"] == (row["raw_id"] == outcomes[0]["raw_id"])
    state = _twin(engine, device_id)
    if row["twin_eligible"]:
        assert state["reported_state"]["raw_id"] == row["raw_id"]
        assert state["twin_version"] == 1
    else:
        assert state is None


@pytest.mark.parametrize("expected_version", [0, 1])
def test_concurrent_desired_compare_and_swap(engine, device_id, expected_version):
    if expected_version:
        _desired(engine, device_id, 0, {"intent": "initial"})

    def writer(value):
        try:
            return _desired(engine, device_id, expected_version, {"intent": value})
        except TwinVersionConflict:
            return None

    results = _race(lambda: writer("a"), lambda: writer("b"))
    assert results.count(None) == 1
    winner = results.index(expected_version + 1)
    assert _twin(engine, device_id)["desired_state"] == {"intent": ("a", "b")[winner]}


@pytest.mark.parametrize("expected_version", [0, 1])
def test_concurrent_reported_and_desired_preserve_both_domains(
    engine, device_id, expected_version,
):
    if expected_version:
        _ingest(engine, _payload(device_id, 1))

    def write_intent():
        try:
            return _desired(engine, device_id, expected_version, {"cooling": "OFF"})
        except TwinVersionConflict:
            # Reported won the version race. Retry explicitly with fresh state.
            return _desired(engine, device_id, expected_version + 1, {"cooling": "OFF"})

    seq = expected_version + 1
    outcome, version = _race(lambda: _ingest(engine, _payload(device_id, seq)), write_intent)
    assert outcome["normalized"]["outcome"] == "inserted"
    assert version in (expected_version + 1, expected_version + 2)
    state = _twin(engine, device_id)
    assert (state["twin_version"], state["last_seq"]) == (expected_version + 2, seq)
    assert state["desired_state"] == {"cooling": "OFF"}
    assert state["reported_state"]["applied_cooling"] == "ON"


@pytest.mark.skipif(not has_test_mqtt(), reason="requires real Mosquitto")
@pytest.mark.parametrize("subscriptions", [SUBSCRIPTIONS, (("coldguard/+/+", 1),)])
def test_mqtt_live_retained_and_delayed_replay(engine, subscriptions):
    device = "coldguard-001"  # Scoped by the real device broker ACL.
    boot = f"mqtt-twin-{uuid4().hex}"
    topic = f"coldguard/{device}/telemetry"
    params = mqtt_params()
    config = make_test_config(
        mqtt_user=params["backend_user"], mqtt_password=params["backend_password"],
    )
    consumer = MqttIngestConsumer(config, subscriptions=subscriptions)
    publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    publisher.username_pw_set(params["device_user"], params["device_password"])
    assert _twin(engine, device) is None

    def send(seq, *, retain=False, **fields):
        message = json.dumps(_payload(device, seq, boot_id=boot, **fields))
        delivery = publisher.publish(topic, message, qos=1, retain=retain)
        delivery.wait_for_publish(timeout=10)
        assert delivery.is_published()

    def wait_for_sample(seq):
        assert wait_for(
            lambda: any(row["boot_id"] == boot and row["seq"] == seq
                        for row in _history(engine, device)),
            timeout_s=10,
        )

    def publish(seq, **fields):
        send(seq, **fields)
        wait_for_sample(seq)

    try:
        publisher.connect(params["host"], params["port"], keepalive=15)
        publisher.loop_start()
        # A retained delivery proves the subscriber is ready before live sends.
        send(0, retain=True)
        consumer.start()
        wait_for_sample(0)
        assert _twin(engine, device) is None
        publish(1)
        publish(10, retain=True)
        assert _twin(engine, device)["last_seq"] == 1
        consumer.stop()
        duplicates = consumer.metrics.snapshot()["exact_duplicates"]
        consumer.start()
        assert wait_for(
            lambda: consumer.metrics.snapshot()["exact_duplicates"] > duplicates, timeout_s=10,
        )
        publish(11, replay=True)
        assert _twin(engine, device)["last_seq"] == 1
        publish(2)
        assert _twin(engine, device)["last_seq"] == 2
    finally:
        consumer.stop()
        if publisher.is_connected():
            publisher.publish(topic, b"", qos=1, retain=True).wait_for_publish(timeout=10)
        publisher.disconnect()
        publisher.loop_stop()
        with engine.begin() as connection:
            connection.execute(device_twin.delete().where(
                device_twin.c.device_id == device, device_twin.c.last_boot_id == boot,
            ))


def test_upgrade_keeps_populated_w03_history_without_promoting_it(engine, device_id, monkeypatch):
    backend = FIXTURE.parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "src/coldguard_backend/migrations"))
    monkeypatch.setenv("DATABASE_URL", os.environ["COLDGUARD_TEST_DATABASE_URL"])
    command.downgrade(config, "0003")
    try:
        payload = _payload(device_id, 1)
        validated = Telemetry.model_validate(payload)
        received_at = validated.captured_at
        raw = store_raw(
            engine, topic=f"coldguard/{device_id}/telemetry",
            payload=json.dumps(payload).encode(), received_at=received_at,
        )
        sample = map_to_row(validated, raw_id=raw["id"], received_at=received_at)
        normalized = insert_normalized(engine, sample)
    finally:
        command.upgrade(config, "head")

    assert _history(engine, device_id)[0]["raw_id"] == raw["id"]
    assert _history(engine, device_id)[0]["twin_eligible"] is False
    assert _ingest(engine, payload)["normalized"] == {
        "outcome": "exact_duplicate", "id": normalized["id"],
    }
    assert _twin(engine, device_id) is None
    _ingest(engine, _payload(device_id, 2))
    assert _twin(engine, device_id)["last_seq"] == 2
