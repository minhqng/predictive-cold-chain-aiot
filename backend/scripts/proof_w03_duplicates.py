#!/usr/bin/env python3
"""Authoritative C-W03 duplicate/idempotency proof (real Mosquitto → backend → PostgreSQL).

Proves the full W03 path on real providers with a duplicate-heavy
finite run whose expected identities are known before publication::

    authenticated simulator/publisher
    → real Mosquitto → backend consumer → raw handling
    → runtime validation → normalized PostgreSQL
    → uniqueness arbitration → duplicate/rejection diagnostics

Preconditions (started beforehand):

* ``infra/mosquitto/provision-dev.sh`` generated the password file;
* ``docker compose -f infra/compose.yaml -p <project> up -d --build``
  is healthy (postgres + mosquitto + backend with W03 code);
* ``alembic -c alembic.ini upgrade head`` applied migration 0003.

Readiness is proven, not assumed: one probe message must round-trip
to a committed raw row before the measured run starts (the consumer
subscription is live only then). Completion is condition-driven
polling with an explicit timeout. Exit code is 0 only for RESULT:
PASS.

Reconciliation (all numbers from provider state, never counters):

* Phase A — duplicate-heavy: N distinct identities × K deliveries.
  raw_deliveries == N*K, distinct raw identities == N, normalized
  samples == N, exact_duplicates == raw_valid - normalized, missing
  == [].
* Phase B — conflicting replay: same identity, different payload.
  raw +1, normalized unchanged, authoritative values preserved.
* Phase C — rejections: malformed / missing identity / wrong type /
  unsupported schema / topic mismatch. Each leaves raw evidence with
  diagnostics and no normalized sample.

Configuration via environment (defaults match infra/.env.example)::

    MQTT_HOST/PORT, MQTT_DEVICE_USER/PASSWORD, DATABASE_URL (or
    POSTGRES_HOST/PORT/DB/USER/PASSWORD), PROOF_N (default 50),
    PROOF_K (default 3), PROOF_RUN_ID / PROOF_BOOT_ID (default:
    generated, unique per run), BACKEND_URL (health pre-check).
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

from coldguard_backend.simulator import build_telemetry  # noqa: E402

N = int(os.environ.get("PROOF_N", "50"))
K = int(os.environ.get("PROOF_K", "3"))
RUN_ID = os.environ.get("PROOF_RUN_ID", f"CG-W03-PROOF-{uuid.uuid4().hex[:8]}")
BOOT_ID = os.environ.get("PROOF_BOOT_ID", f"boot-proof-{uuid.uuid4().hex[:8]}")
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


def _wire(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


class _Publisher:
    """One persistent authenticated publisher connection for the run."""

    def __init__(self) -> None:
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        self.client.username_pw_set(DEVICE_USER, DEVICE_PASSWORD)
        self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
        self.client.loop_start()

    def publish(self, topic: str, payload: bytes) -> None:
        info = self.client.publish(topic, payload, qos=1, retain=False)
        info.wait_for_publish(timeout=15)
        assert info.is_published(), f"PUBACK missing for {topic}"

    def close(self) -> None:
        self.client.loop_stop()
        try:
            self.client.disconnect()
        except Exception:  # noqa: BLE001 - proof teardown
            pass


def _wait_for(condition_desc: str, fn, timeout: float = POLL_TIMEOUT_S):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(f"timed out waiting for: {condition_desc}")


def main() -> int:
    stamp = datetime.now(timezone.utc).isoformat()
    print(f"PROOF_START: {stamp} run_id={RUN_ID} boot_id={BOOT_ID} N={N} K={K}")
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/health", timeout=10) as response:
            assert response.status == 200
        print(f"BACKEND_HEALTH: ok ({BACKEND_URL})")
    except Exception as exc:
        print(f"BACKEND_HEALTH: FAILED ({exc})")
        return 2

    engine = create_engine(_database_url())

    def raw_count(run: str) -> int:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT count(*) FROM telemetry_raw WHERE run_id = :run"),
                {"run": run},
            ).scalar()

    def norm_count(run: str) -> int:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT count(*) FROM telemetry WHERE run_id = :run"),
                {"run": run},
            ).scalar()

    # Readiness probe: one message must round-trip to a committed row,
    # proving the consumer subscription is live before the measured run.
    publisher = _Publisher()
    probe_run = f"{RUN_ID}-probe"
    publisher.publish(
        TELEMETRY_TOPIC,
        _wire(build_telemetry(boot_id=BOOT_ID, seq=0, run_id=probe_run)),
    )
    try:
        _wait_for("readiness probe commit", lambda: raw_count(probe_run) >= 1, timeout=60)
    except TimeoutError:
        print("READINESS_PROBE: FAILED (probe message never committed)")
        publisher.close()
        return 2
    print("READINESS_PROBE: ok (consumer subscription live)")

    # Phase A — duplicate-heavy finite run: N identities × K deliveries.
    acknowledged = 0
    for seq in range(1, N + 1):
        wire = _wire(build_telemetry(boot_id=BOOT_ID, seq=seq, run_id=RUN_ID))
        for _ in range(K):
            publisher.publish(TELEMETRY_TOPIC, wire)
            acknowledged += 1
    print(f"PUBLISHED: {acknowledged} deliveries over {N} logical identities")

    expected_raw = N * K
    try:
        _wait_for(
            f"{expected_raw} raw deliveries",
            lambda: raw_count(RUN_ID) >= expected_raw or False,
        )
    except TimeoutError:
        print(f"RAW_DELIVERIES: only {raw_count(RUN_ID)} of {expected_raw} committed")
        publisher.close()
        return 1
    # Settle window: broker redelivery (if any) arrives as extra raw rows.
    time.sleep(3)
    with engine.connect() as connection:
        raw_total = connection.execute(
            text("SELECT count(*) FROM telemetry_raw WHERE run_id = :run"), {"run": RUN_ID}
        ).scalar()
        distinct_identities = connection.execute(
            text(
                "SELECT count(*) FROM (SELECT DISTINCT device_id, boot_id, seq "
                "FROM telemetry_raw WHERE run_id = :run) AS identities"
            ),
            {"run": RUN_ID},
        ).scalar()
        statuses = dict(
            connection.execute(
                text(
                    "SELECT ingest_status, count(*) FROM telemetry_raw "
                    "WHERE run_id = :run GROUP BY ingest_status"
                ),
                {"run": RUN_ID},
            ).all()
        )
        present = {
            row[0]
            for row in connection.execute(
                text("SELECT seq FROM telemetry_raw WHERE run_id = :run"), {"run": RUN_ID}
            ).all()
        }
        norm_total = connection.execute(
            text("SELECT count(*) FROM telemetry WHERE run_id = :run"), {"run": RUN_ID}
        ).scalar()
    missing = [seq for seq in range(1, N + 1) if seq not in present]
    exact_duplicates = statuses.get("RECEIVED_VALID", 0) - norm_total

    print(f"RAW_DELIVERIES: {raw_total} (expected {expected_raw})")
    print(f"DISTINCT_RAW_IDENTITIES: {distinct_identities} (expected {N})")
    print(f"NEW_NORMALIZED_SAMPLES: {norm_total} (expected {N})")
    print(f"EXACT_DUPLICATES: {exact_duplicates} (expected {N * K - N})")
    print(f"STATUS_BREAKDOWN: {statuses}")
    print(f"MISSING_IDENTITIES: {missing if missing else '[]'}")
    phase_a = (
        raw_total == expected_raw
        and distinct_identities == N
        and norm_total == N
        and exact_duplicates == N * K - N
        and not missing
        and statuses.get("RECEIVED_VALID", 0) == expected_raw
    )
    print(f"PHASE_A_DUPLICATE_HEAVY: {'PASS' if phase_a else 'FAIL'}")

    # Phase B — conflicting replay: same identity, different physical reading.
    conflict_seq = 1
    original = build_telemetry(boot_id=BOOT_ID, seq=conflict_seq, run_id=RUN_ID)
    tampered = dict(original)
    tampered["thermal"] = dict(original["thermal"], t1=round(original["thermal"]["t1"] + 5.0, 3))
    publisher.publish(TELEMETRY_TOPIC, _wire(tampered))
    try:
        _wait_for(
            "conflicting raw evidence",
            lambda: raw_count(RUN_ID) >= expected_raw + 1 or False,
        )
    except TimeoutError:
        print("PHASE_B_CONFLICT: FAIL (conflicting delivery never landed)")
        publisher.close()
        return 1
    time.sleep(2)
    with engine.connect() as connection:
        norm_after = connection.execute(
            text("SELECT count(*) FROM telemetry WHERE run_id = :run"), {"run": RUN_ID}
        ).scalar()
        stored_t1 = connection.execute(
            text(
                "SELECT t1_c FROM telemetry WHERE device_id = :device "
                "AND boot_id = :boot AND seq = :seq"
            ),
            {"device": DEVICE_ID, "boot": BOOT_ID, "seq": conflict_seq},
        ).scalar()
    conflicting_identities = 1
    print(f"CONFLICTING_IDENTITIES: {conflicting_identities}")
    print(f"NORMALIZED_AFTER_CONFLICT: {norm_after} (must stay {N})")
    print(f"AUTHORITATIVE_T1: {stored_t1} (must stay {original['thermal']['t1']})")
    phase_b = norm_after == N and stored_t1 == original["thermal"]["t1"]
    print(f"PHASE_B_CONFLICT: {'PASS' if phase_b else 'FAIL'}")

    # Phase C — rejections: each leaves raw evidence, no normalized sample.
    reject_cases: list[tuple[str, str, bytes, str]] = []
    malformed = b"{proof-malformed-payload"
    reject_cases.append(("malformed_json", TELEMETRY_TOPIC, malformed, "RECEIVED_MALFORMED_JSON"))
    no_identity = build_telemetry(boot_id=BOOT_ID, seq=9001, run_id=RUN_ID)
    del no_identity["boot_id"]
    reject_cases.append(
        ("missing_identity", TELEMETRY_TOPIC, _wire(no_identity), "RECEIVED_INVALID_SCHEMA")
    )
    wrong_type = build_telemetry(boot_id=BOOT_ID, seq=9002, run_id=RUN_ID)
    wrong_type["seq"] = "not-a-seq"
    reject_cases.append(
        ("wrong_type", TELEMETRY_TOPIC, _wire(wrong_type), "RECEIVED_INVALID_SCHEMA")
    )
    bad_schema = build_telemetry(boot_id=BOOT_ID, seq=9003, run_id=RUN_ID)
    bad_schema["schema_version"] = 99
    reject_cases.append(
        ("unsupported_schema", TELEMETRY_TOPIC, _wire(bad_schema), "RECEIVED_INVALID_SCHEMA")
    )
    mismatch = build_telemetry(boot_id=BOOT_ID, seq=9004, run_id=RUN_ID)
    mismatch["device_id"] = "coldguard-999"
    # Published on the device's OWN topic (ACL-permitted) while the
    # payload claims a different device: the backend must detect the
    # disagreement (broker ACL cannot see inside the payload).
    reject_cases.append(
        ("topic_mismatch", TELEMETRY_TOPIC, _wire(mismatch), "REJECTED_TOPIC_MISMATCH")
    )
    phase_c_ok = True
    rejected = 0
    for name, topic, wire, expected_status in reject_cases:
        sha = hashlib.sha256(wire).hexdigest()
        publisher.publish(topic, wire)
        try:
            row = _wait_for(
                f"raw evidence for {name}",
                lambda: _row_for_sha(engine, sha),
            )
        except TimeoutError:
            print(f"REJECTED[{name}]: MISSING raw evidence -> FAIL")
            phase_c_ok = False
            continue
        status, errors, norm = row
        print(f"REJECTED[{name}]: status={status} errors={bool(errors)} normalized={norm}")
        if status != expected_status or not errors or norm != 0:
            phase_c_ok = False
        else:
            rejected += 1
    print(f"REJECTED: {rejected} (expected {len(reject_cases)})")
    print(f"PHASE_C_REJECTIONS: {'PASS' if phase_c_ok else 'FAIL'}")

    passed = phase_a and phase_b and phase_c_ok
    print(f"RESULT: {'PASS' if passed else 'FAIL'}")
    publisher.close()
    engine.dispose()
    return 0 if passed else 1


def _row_for_sha(engine, sha: str):
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT ingest_status, validation_errors FROM telemetry_raw "
                "WHERE payload_sha256 = :sha"
            ),
            {"sha": sha},
        ).first()
        if row is None:
            return None
        norm = connection.execute(
            text("SELECT count(*) FROM telemetry WHERE raw_id IN "
                 "(SELECT id FROM telemetry_raw WHERE payload_sha256 = :sha)"),
            {"sha": sha},
        ).scalar()
        return row[0], row[1], norm


if __name__ == "__main__":
    raise SystemExit(main())
