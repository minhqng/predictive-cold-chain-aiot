"""Deterministic synthetic ColdGuard device (C-W02-02).

A small finite-run publisher owned by Member C. It emits the four
device-owned topic families (telemetry/event/state/health) through the
real broker as the real device principal, using the canonical topic
namespace and QoS/retain policy (Doc 02 section 7):

* telemetry QoS 1, retain False;
* event QoS 1, retain False;
* state QoS 1, retain True (current snapshot only);
* health QoS 1, retain True.

Deliberate non-goals: this is pipeline proof, never physical sensor
evidence (payloads are deterministic functions of ``seq``, clearly
marked synthetic); it never publishes commands and never operates an
actuator. A retained state/health snapshot must not be read as physical
freshness (Doc 02 section 8).

Reproducibility: one canonical device identity by default; every run
takes explicit ``boot_id``/``run_id``/``start_seq`` so a validation run
is distinguishable in the database from all other traffic. Published
message counts report MQTT PUBACK completion only; durable persistence
is the backend's evidence (C-W02-05 proof script), never this counter.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

import paho.mqtt.client as mqtt

from coldguard_backend.mqtt_consumer import reason_failed

TELEMETRY_QOS = 1
EVENT_QOS = 1
STATE_QOS = 1
HEALTH_QOS = 1

TELEMETRY_RETAIN = False
EVENT_RETAIN = False
STATE_RETAIN = True
HEALTH_RETAIN = True

DEFAULT_DEVICE_ID = "coldguard-001"
BASE_CAPTURED_AT = datetime(2026, 10, 20, 0, 0, 0, tzinfo=timezone.utc)

_CONNECT_TIMEOUT_S = 10.0
_PUBLISH_TIMEOUT_S = 15.0


def topic_for(device_id: str, family: str) -> str:
    """Canonical topic for one device-owned family."""
    if family not in ("telemetry", "event", "state", "command_ack", "health"):
        raise ValueError(f"unknown device topic family {family!r}")
    return f"coldguard/{device_id}/{family}"


def qos_retain_for(family: str) -> tuple[int, bool]:
    """Canonical (QoS, retain) policy per family (Doc 02 section 7)."""
    policy = {
        "telemetry": (TELEMETRY_QOS, TELEMETRY_RETAIN),
        "event": (EVENT_QOS, EVENT_RETAIN),
        "state": (STATE_QOS, STATE_RETAIN),
        "health": (HEALTH_QOS, HEALTH_RETAIN),
    }
    try:
        return policy[family]
    except KeyError:
        raise ValueError(f"no publisher policy for family {family!r}") from None


def build_telemetry(
    *,
    device_id: str = DEFAULT_DEVICE_ID,
    boot_id: str,
    seq: int,
    run_id: str,
    base_time: datetime = BASE_CAPTURED_AT,
) -> dict:
    """One deterministic synthetic telemetry snapshot.

    Values are closed-form functions of ``seq`` (repeatable across
    runs); the payload always satisfies the W01 wire contracts with
    VALID quality so the simulator exercises the happy path. Corrupt or
    degraded inputs are the proof script's / tests' job, not this
    builder's.
    """
    captured = base_time + timedelta(seconds=seq)
    t1 = round(7.0 + 0.01 * (seq % 50), 3)
    voltage = round(12.0 - 0.001 * (seq % 10), 3)
    current = round(10.5 + 0.01 * (seq % 30), 3)
    return {
        "schema_version": 1,
        "device_id": device_id,
        "boot_id": boot_id,
        "seq": seq,
        "captured_at": captured.isoformat().replace("+00:00", "Z"),
        "uptime_ms": seq * 1000,
        "run_id": run_id,
        "hardware_config_id": "CG-HW-001",
        "firmware_version": "fw-sim-w02",
        "calibration_id": None,
        "synthetic": True,
        "thermal": {
            "t1": t1,
            "t2": round(t1 + 0.3, 3),
            "t3": round(t1 + 0.7, 3),
        },
        "environment": {
            "t_air": round(7.5 + 0.005 * (seq % 40), 3),
            "rh": round(84.0 + 0.05 * (seq % 20), 3),
        },
        "door": {"state": "CLOSED"},
        "electrical": {
            "voltage_v": voltage,
            "current_a": current,
            "power_w": round(voltage * current, 3),
            "energy_wh": round(seq * 0.035, 3),
        },
        "actuation": {"cooling": "ON", "duty": 1.0},
        "quality": {
            "thermal": "VALID",
            "environment": "VALID",
            "electrical": "VALID",
            "overall": "VALID",
            "device_mode": "ONLINE_NORMAL",
        },
    }


def build_event(
    *,
    device_id: str = DEFAULT_DEVICE_ID,
    boot_id: str,
    seq: int,
    run_id: str,
    event_type: str = "SIM_RUN_START",
    base_time: datetime = BASE_CAPTURED_AT,
) -> dict:
    captured = base_time + timedelta(seconds=seq)
    return {
        "schema_version": 1,
        "event_id": str(uuid5(
            NAMESPACE_URL, json.dumps(["coldguard/event", device_id, run_id, boot_id, seq, event_type]),
        )),
        "event_type": event_type,
        "device_id": device_id,
        "boot_id": boot_id,
        "seq": seq,
        "run_id": run_id,
        "event_time": captured.isoformat().replace("+00:00", "Z"),
        "severity": "INFO",
        "synthetic": True,
        "payload": {"note": "synthetic simulator event; not physical evidence"},
    }


def build_state(
    *,
    device_id: str = DEFAULT_DEVICE_ID,
    boot_id: str,
    seq: int,
    run_id: str,
    base_time: datetime = BASE_CAPTURED_AT,
) -> dict:
    captured = base_time + timedelta(seconds=seq)
    return {
        "schema_version": 1,
        "device_id": device_id,
        "boot_id": boot_id,
        "seq": seq,
        "run_id": run_id,
        "captured_at": captured.isoformat().replace("+00:00", "Z"),
        "mode": "ONLINE_NORMAL",
        "applied": {"cooling": "ON", "duty": 1.0},
        "synthetic": True,
    }


def build_health(
    *,
    device_id: str = DEFAULT_DEVICE_ID,
    boot_id: str,
    seq: int,
    status: str = "ONLINE",
    base_time: datetime = BASE_CAPTURED_AT,
) -> dict:
    captured = base_time + timedelta(seconds=seq)
    return {
        "schema_version": 1,
        "device_id": device_id,
        "boot_id": boot_id,
        "status": status,
        "uptime_ms": seq * 1000,
        "captured_at": captured.isoformat().replace("+00:00", "Z"),
        "synthetic": True,
    }


class SimulationResult(dict):
    """Counts for one finite run (PUBACK-level, not DB-level)."""


def _dumps(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def run_simulation(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    device_id: str = DEFAULT_DEVICE_ID,
    boot_id: str,
    run_id: str,
    count: int,
    start_seq: int = 0,
    publish_families: bool = True,
    interval_s: float = 0,
) -> SimulationResult:
    """Publish ``count`` distinct telemetry messages plus family snapshots.

    Blocks on each QoS 1 handshake (``wait_for_publish``), so the
    returned ``publish_acknowledged`` count reflects broker-accepted
    publications. Raises ConnectionError on refused credentials and
    TimeoutError on unreachable broker / missing PUBACK.
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    if not math.isfinite(interval_s) or interval_s < 0:
        raise ValueError("interval_s must be finite and non-negative")
    connected = threading.Event()
    failure: list[str] = []

    def _on_connect(client, userdata, flags, reason_code, properties=None):
        if reason_failed(reason_code):
            failure.append(
                f"simulator authentication refused for user {username!r} "
                f"(reason {reason_code})"
            )
        connected.set()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"sim-{device_id}-{run_id}",
        protocol=mqtt.MQTTv5,
    )
    client.username_pw_set(username, password)
    client.on_connect = _on_connect
    health_topic = topic_for(device_id, "health")
    client.will_set(
        health_topic,
        _dumps(build_health(device_id=device_id, boot_id=boot_id, seq=start_seq, status="OFFLINE_UNEXPECTED")),
        qos=HEALTH_QOS,
        retain=True,
    )
    try:
        client.connect(host, port, keepalive=30)
    except Exception as exc:
        raise TimeoutError(f"simulator: broker unreachable at {host}:{port}: {exc}") from exc
    client.loop_start()
    try:
        if not connected.wait(timeout=_CONNECT_TIMEOUT_S):
            raise TimeoutError(
                f"simulator: broker at {host}:{port} did not answer CONNECT "
                f"within {_CONNECT_TIMEOUT_S:.0f}s"
            )
        if failure:
            raise ConnectionError(failure[0])
        acknowledged = 0
        next_publish = time.monotonic()
        for offset in range(count):
            if interval_s:
                time.sleep(max(0, next_publish - time.monotonic()))
                next_publish = time.monotonic() + interval_s
            seq = start_seq + offset
            info = client.publish(
                topic_for(device_id, "telemetry"),
                _dumps(
                    build_telemetry(
                        device_id=device_id, boot_id=boot_id, seq=seq, run_id=run_id
                    )
                ),
                qos=TELEMETRY_QOS,
                retain=TELEMETRY_RETAIN,
            )
            info.wait_for_publish(timeout=_PUBLISH_TIMEOUT_S)
            if not info.is_published():
                raise TimeoutError(
                    f"simulator: PUBACK missing for seq={seq} "
                    f"within {_PUBLISH_TIMEOUT_S:.0f}s"
                )
            acknowledged += 1
        families = 0
        if publish_families:
            companions: list[tuple[str, dict]] = [
                ("event", build_event(device_id=device_id, boot_id=boot_id, seq=start_seq, run_id=run_id)),
                ("state", build_state(device_id=device_id, boot_id=boot_id, seq=start_seq + count, run_id=run_id)),
                ("health", build_health(device_id=device_id, boot_id=boot_id, seq=start_seq + count)),
            ]
            for family, payload in companions:
                qos, retain = qos_retain_for(family)
                info = client.publish(topic_for(device_id, family), _dumps(payload), qos=qos, retain=retain)
                info.wait_for_publish(timeout=_PUBLISH_TIMEOUT_S)
                if not info.is_published():
                    raise TimeoutError(f"simulator: PUBACK missing for family {family!r}")
                families += 1
        return SimulationResult(
            generated=count,
            publish_acknowledged=acknowledged,
            families_published=families,
            device_id=device_id,
            boot_id=boot_id,
            run_id=run_id,
            start_seq=start_seq,
        )
    finally:
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001 - post-run disconnect must not mask results
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ColdGuard synthetic device (C-W02-02)")
    # Prefer MQTT_PASSWORD in the environment over --password: CLI
    # arguments are visible in process listings and shell history.
    parser.add_argument("--host", default=os.environ.get("MQTT_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    parser.add_argument("--username", default=os.environ.get("MQTT_USERNAME", "device-coldguard-001"))
    parser.add_argument("--password", default=os.environ.get("MQTT_PASSWORD", ""))
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID)
    parser.add_argument("--boot-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--start-seq", type=int, default=0)
    args = parser.parse_args(argv)
    result = run_simulation(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        device_id=args.device_id,
        boot_id=args.boot_id,
        run_id=args.run_id,
        count=args.count,
        start_seq=args.start_seq,
    )
    print(json.dumps(dict(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
