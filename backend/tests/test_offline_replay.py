"""Replay the real MQTT/PostgreSQL path using software-only telemetry."""

import json
from datetime import datetime
from uuid import uuid4

import pytest

from coldguard_backend.mqtt_consumer import MqttIngestConsumer
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.raw_store import telemetry_raw
from coldguard_backend.reconciliation import reconcile_telemetry
from coldguard_backend.twin_store import _retired_boot, device_twin, reconcile_reported_boot
from scripts.serial_gateway import translate
from tests.command_testkit import utcnow
from tests.mqtt_testkit import has_test_mqtt, make_test_config, mqtt_params, wait_for
from tests.test_command_publisher import _connect
from tests.test_migration_w05 import MEMBER_A_FIXTURE
from tests.test_twin import _history, _payload, _twin


@pytest.mark.skipif(not has_test_mqtt(), reason="requires disposable Mosquitto")
def test_offline_buffer_replay_preserves_evidence_and_current_boot(db_engine):
    params = mqtt_params()
    device = "coldguard-001"
    topic = f"coldguard/{device}/telemetry"
    run_id = f"w11-software-{uuid4().hex}"
    old_boot, active_boot = f"{run_id}-old", f"{run_id}-active"
    config = make_test_config(
        mqtt_user=params["backend_user"], mqtt_password=params["backend_password"],
    )
    consumer = MqttIngestConsumer(config, subscriptions=((topic, 1),))
    publisher = _connect(params["device_user"], params["device_password"], run_id)
    sent = 0

    def send(payload):
        nonlocal sent
        wire = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        delivery = publisher.publish(topic, wire, qos=1, retain=False)
        delivery.wait_for_publish(timeout=5)
        assert delivery.is_published()
        sent += 1
        assert wait_for(lambda: consumer.snapshot()["persisted"] == sent, timeout_s=5)

    def sample(seq, boot, **fields):
        return _payload(device, seq, boot_id=boot, run_id=run_id, **fields)

    try:
        with db_engine.begin() as conn:
            conn.execute(device_twin.delete().where(device_twin.c.device_id == device))
        consumer.start()
        first, winner, late = (sample(seq, old_boot) for seq in (100, 102, 101))
        for payload in (first, winner, late, winner, dict(winner, door={"state": "OPEN"})):
            send(payload)
        assert _twin(db_engine, device)["last_seq"] == 102
        assert consumer.snapshot()["out_of_order"] == 1
        assert consumer.snapshot()["exact_duplicates"] == 1
        assert consumer.snapshot()["conflicts"] == 1

        send(sample(0, active_boot))
        assert _twin(db_engine, device)["last_boot_id"] == old_boot
        with db_engine.begin() as conn:
            reconcile_reported_boot(
                conn, device_id=device, expected_boot_id=old_boot, new_boot_id=active_boot,
            )
        send(sample(103, old_boot, replay=True))
        send(sample(7, active_boot, is_replay=True))
        fields = json.loads(MEMBER_A_FIXTURE.read_text(encoding="utf-8"))["fields"]
        fields.update(device_id=device, boot_id=active_boot, seq=8, run_id=run_id)
        wire = ("#CG TELEM " + " ".join(f"{k}={v}" for k, v in fields.items())).encode("ascii")
        send(translate(wire, topic=topic, gateway_received_at=utcnow(), replay=True))
        assert consumer.snapshot()["explicit_replays"] == 3
        current = _twin(db_engine, device)
        assert (current["last_boot_id"], current["last_seq"]) == (active_boot, 0)
        observations = {
            (row["boot_id"], row["seq"]): row for row in _history(db_engine, device)
            if row["run_id"] == run_id
        }
        assert len(observations) == 7
        assert observations[old_boot, 102]["door_state"] == winner["door"]["state"]
        assert observations[old_boot, 103]["time"] == datetime.fromisoformat(winner["captured_at"])
        assert observations[active_boot, 8]["time"] is None
        assert not observations[active_boot, 7]["twin_eligible"]

        consumer.stop()
        consumer = MqttIngestConsumer(config, subscriptions=((topic, 1),))
        consumer.start()
        sent = 0
        assert consumer.snapshot()["explicit_replays"] == 0
        send(winner)
        assert _twin(db_engine, device) == current
        report = reconcile_telemetry(db_engine, device_id=device, run_id=run_id)
        assert report.is_reconciled, report.summary()
        assert (report.raw_total, report.normalized_total) == (10, 7)
        assert (report.exact_duplicates, report.conflicting_duplicates) == (2, 1)
    finally:
        consumer.stop()
        publisher.disconnect()
        publisher.loop_stop()
        with db_engine.begin() as conn:
            conn.execute(_retired_boot.delete().where(
                _retired_boot.c.device_id == device, _retired_boot.c.boot_id == old_boot,
            ))
            conn.execute(device_twin.delete().where(
                device_twin.c.device_id == device,
                device_twin.c.last_boot_id.in_((old_boot, active_boot)),
            ))
            conn.execute(telemetry.delete().where(telemetry.c.run_id == run_id))
            conn.execute(telemetry_raw.delete().where(telemetry_raw.c.run_id == run_id))
