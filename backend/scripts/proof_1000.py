#!/usr/bin/env python3
"""Authoritative C-W02-05 integration proof (real Mosquitto → backend → PostgreSQL).

Publishes COUNT distinct synthetic telemetry messages through the real
broker, then verifies against committed database state — never against
publisher counters or logs alone::

    GENERATED -> PUBLISH_ACKNOWLEDGED (MQTT PUBACKs) -> BACKEND_RECEIVED
    -> DB_COMMITTED (SELECT count ...) -> DISTINCT_IDENTITIES_PERSISTED

Preconditions (started beforehand, exactly as the README documents):

* ``infra/mosquitto/provision-dev.sh`` has generated the password file;
* ``docker compose -f infra/compose.yaml up -d`` is healthy;
* ``alembic -c alembic.ini upgrade head`` applied the W02 migration.

Readiness is proven, not assumed: one probe message must round-trip to
a committed row before the measured run starts. Completion is
condition-driven polling with an explicit timeout. Exit code is 0 only
for RESULT: PASS.

Configuration via environment (all have local defaults matching
infra/.env.example)::

    MQTT_HOST/PORT, MQTT_DEVICE_USER/PASSWORD, DATABASE_URL (or
    POSTGRES_HOST/PORT/DB/USER/PASSWORD), PROOF_COUNT (default 1000),
    PROOF_RUN_ID / PROOF_BOOT_ID (default: generated, unique per run),
    PROOF_START_SEQ (default 0), BACKEND_URL (default
    http://127.0.0.1:8000, health pre-check).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from coldguard_backend.simulator import (  # noqa: E402
    build_telemetry,
    run_simulation,
)

COUNT = int(os.environ.get("PROOF_COUNT", "1000"))
RUN_ID = os.environ.get("PROOF_RUN_ID", f"CG-W02-PROOF-{uuid.uuid4().hex[:8]}")
BOOT_ID = os.environ.get("PROOF_BOOT_ID", f"boot-proof-{uuid.uuid4().hex[:8]}")
START_SEQ = int(os.environ.get("PROOF_START_SEQ", "0"))
DEVICE_ID = "coldguard-001"
TELEMETRY_TOPIC = f"coldguard/{DEVICE_ID}/telemetry"

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
DEVICE_USER = os.environ.get("MQTT_DEVICE_USER", "device-coldguard-001")
DEVICE_PASSWORD = os.environ.get("MQTT_DEVICE_PASSWORD", "device_dev_only")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

POLL_TIMEOUT_S = float(os.environ.get("PROOF_TIMEOUT_S", "180"))
POLL_INTERVAL_S = 1.0


def _database_url() -> str:
    explicit = os.environ.get("DATABASE_URL", "").strip()
    if explicit:
        return explicit
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "coldguard")
    user = os.environ.get("POSTGRES_USER", "coldguard")
    password = os.environ.get("POSTGRES_PASSWORD", "coldguard_dev_only")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


def _query_count(engine, run_id: str, boot_id: str) -> tuple[int, int, dict[str, int]]:
    with engine.connect() as connection:
        total = connection.execute(
            text(
                "SELECT count(*) FROM telemetry_raw "
                "WHERE run_id = :run_id AND boot_id = :boot_id "
                "AND topic = :topic"
            ),
            {"run_id": run_id, "boot_id": boot_id, "topic": TELEMETRY_TOPIC},
        ).scalar()
        distinct = connection.execute(
            text(
                "SELECT count(*) FROM (SELECT DISTINCT device_id, boot_id, seq "
                "FROM telemetry_raw WHERE run_id = :run_id AND boot_id = :boot_id "
                "AND topic = :topic) AS identities"
            ),
            {"run_id": run_id, "boot_id": boot_id, "topic": TELEMETRY_TOPIC},
        ).scalar()
        statuses = dict(
            connection.execute(
                text(
                    "SELECT ingest_status, count(*) FROM telemetry_raw "
                    "WHERE run_id = :run_id AND boot_id = :boot_id "
                    "AND topic = :topic GROUP BY ingest_status"
                ),
                {"run_id": run_id, "boot_id": boot_id, "topic": TELEMETRY_TOPIC},
            ).all()
        )
    return total, distinct, statuses


def _missing_seqs(engine, run_id: str, boot_id: str, start: int, count: int) -> list[int]:
    with engine.connect() as connection:
        present = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT seq FROM telemetry_raw WHERE run_id = :run_id "
                    "AND boot_id = :boot_id AND topic = :topic"
                ),
                {"run_id": run_id, "boot_id": boot_id, "topic": TELEMETRY_TOPIC},
            ).all()
        }
    return [seq for seq in range(start, start + count) if seq not in present]


def _wait_for_count(engine, run_id, boot_id, expected: int) -> tuple[int, int, dict]:
    deadline = time.monotonic() + POLL_TIMEOUT_S
    total, distinct, statuses = _query_count(engine, run_id, boot_id)
    while time.monotonic() < deadline and total < expected:
        time.sleep(POLL_INTERVAL_S)
        total, distinct, statuses = _query_count(engine, run_id, boot_id)
    return total, distinct, statuses


def _publish_raw(topic: str, payload: bytes) -> str:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    client.username_pw_set(DEVICE_USER, DEVICE_PASSWORD)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=15)
    client.loop_start()
    try:
        client.publish(topic, payload, qos=1, retain=False).wait_for_publish(timeout=15)
    finally:
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001 - proof teardown
            pass
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    stamp = datetime.now(timezone.utc).isoformat()
    print(f"PROOF_START: {stamp} run_id={RUN_ID} boot_id={BOOT_ID} count={COUNT}")
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/health", timeout=10) as response:
            assert response.status == 200
        print(f"BACKEND_HEALTH: ok ({BACKEND_URL})")
    except Exception as exc:
        print(f"BACKEND_HEALTH: FAILED ({exc})")
        return 2

    engine = create_engine(_database_url())

    # Readiness probe: one message must round-trip to a committed row,
    # proving the consumer subscription is live before the measured run.
    probe_seq = START_SEQ - 1 if START_SEQ > 0 else -1
    probe_run = f"{RUN_ID}-probe"
    run_simulation(
        host=MQTT_HOST,
        port=MQTT_PORT,
        username=DEVICE_USER,
        password=DEVICE_PASSWORD,
        device_id=DEVICE_ID,
        boot_id=BOOT_ID,
        run_id=probe_run,
        count=1,
        start_seq=max(probe_seq, 0),
        publish_families=False,
    )
    total, _, _ = _wait_for_count(engine, probe_run, BOOT_ID, 1)
    if total < 1:
        print("READINESS_PROBE: FAILED (probe message never committed)")
        return 2
    print("READINESS_PROBE: ok (consumer subscription live)")

    result = run_simulation(
        host=MQTT_HOST,
        port=MQTT_PORT,
        username=DEVICE_USER,
        password=DEVICE_PASSWORD,
        device_id=DEVICE_ID,
        boot_id=BOOT_ID,
        run_id=RUN_ID,
        count=COUNT,
        start_seq=START_SEQ,
    )
    generated = result["generated"]
    acknowledged = result["publish_acknowledged"]

    # Invalid-payload evidence on the same boot marker: one malformed,
    # one schema-violating (missing boot_id). Malformed rows carry no
    # identity, so they are traced by exact payload hash.
    malformed = b"{proof-malformed-payload"
    bad_doc = build_telemetry(boot_id=BOOT_ID, seq=START_SEQ, run_id=RUN_ID)
    del bad_doc["boot_id"]
    invalid_wire = json.dumps(bad_doc, sort_keys=True).encode()
    malformed_sha = _publish_raw(TELEMETRY_TOPIC, malformed)
    invalid_sha = _publish_raw(TELEMETRY_TOPIC, invalid_wire)

    total, distinct, statuses = _wait_for_count(engine, RUN_ID, BOOT_ID, COUNT)
    deadline = time.monotonic() + POLL_TIMEOUT_S
    malformed_row = invalid_row = None
    with engine.connect() as connection:
        backend_received = connection.execute(
            text(
                "SELECT count(*) FROM telemetry_raw WHERE run_id = :run_id "
                "AND boot_id = :boot_id"
            ),
            {"run_id": RUN_ID, "boot_id": BOOT_ID},
        ).scalar()
    while time.monotonic() < deadline and (
        malformed_row is None or invalid_row is None
    ):
        with engine.connect() as connection:
            malformed_row = connection.execute(
                text(
                    "SELECT ingest_status FROM telemetry_raw WHERE payload_sha256 = :sha"
                ),
                {"sha": malformed_sha},
            ).first()
            invalid_row = connection.execute(
                text(
                    "SELECT ingest_status FROM telemetry_raw WHERE payload_sha256 = :sha"
                ),
                {"sha": invalid_sha},
            ).first()
        if malformed_row is None or invalid_row is None:
            time.sleep(POLL_INTERVAL_S)
    missing = _missing_seqs(engine, RUN_ID, BOOT_ID, START_SEQ, COUNT)
    duplicate_deliveries = total - distinct

    print(f"GENERATED: {generated}")
    print(f"PUBLISH_ACKNOWLEDGED: {acknowledged}")
    print(f"BACKEND_RECEIVED: {backend_received}")
    print(f"DB_COMMITTED: {total}")
    print(f"DISTINCT_IDENTITIES_PERSISTED: {distinct}")
    print(f"MISSING_IDENTITIES: {missing if missing else '[]'}")
    print(f"DUPLICATE_DELIVERIES: {duplicate_deliveries}")
    print(f"STATUS_BREAKDOWN: {statuses}")
    print(
        "INVALID_PAYLOAD_EVIDENCE: "
        f"malformed={malformed_row[0] if malformed_row else 'MISSING'} "
        f"invalid_schema={invalid_row[0] if invalid_row else 'MISSING'}"
    )
    expected_invalid = (
        malformed_row is not None
        and malformed_row[0] == "RECEIVED_MALFORMED_JSON"
        and invalid_row is not None
        and invalid_row[0] == "RECEIVED_INVALID_SCHEMA"
    )
    passed = (
        generated == COUNT
        and acknowledged == COUNT
        and total == COUNT
        and distinct == COUNT
        and not missing
        and statuses.get("RECEIVED_VALID", 0) == COUNT
        and expected_invalid
    )
    print(f"RESULT: {'PASS' if passed else 'FAIL'}")
    engine.dispose()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
