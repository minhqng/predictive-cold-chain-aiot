"""Dispatch one operator-approved TEC trial and verify its device evidence."""

from __future__ import annotations

import argparse
from collections import deque
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import paho.mqtt.client as mqtt
import psycopg
from psycopg.rows import dict_row
from sqlalchemy import create_engine

from coldguard_backend.command_authorization import AuthorizedCommandGateway
from coldguard_backend.command_publisher import PahoCommandTransport
from coldguard_backend.contracts import Command
from coldguard_backend.raw_store import RECEIVED_VALID
from integration.leader_downlink import (
    BOOT_ID_RE, SUPERVISED_DUTY_PERMILLE, SUPERVISED_RUN_SECONDS, TELEMETRY_MAX_AGE_S,
    TEC_TRIAL_REASON_PREFIX, TEC_TRIAL_STOP_REASON, _record_fields, subscribe_confirmed,
)
from scripts.serial_gateway import NETWORK_TIMEOUT, Publisher

DUTY = SUPERVISED_DUTY_PERMILLE / 1000
STOP_CURRENT_A = 5.0
STOP_HOT_C = 40.0
ACK_WAIT_S = 10
TRIAL_WAIT_S = ACK_WAIT_S + SUPERVISED_RUN_SECONDS + 5
STOP_WAIT_S = 6


class UnprovenTrial(Exception):
    """The evidence failed a required commissioning condition."""


def require(condition, reason):
    if not condition:
        raise UnprovenTrial(reason)


def utcnow():
    return datetime.now(timezone.utc)


def fresh(timestamp, now, limit=TELEMETRY_MAX_AGE_S):
    return (isinstance(timestamp, datetime) and timestamp.utcoffset() is not None
            and 0 <= (now - timestamp).total_seconds() < limit)


def frame_rows(conn, device, after=None):
    """Follow device rows across boots so a reboot cannot hide behind a filter."""
    with conn.cursor() as cur:
        if after is None:
            cur.execute(
                "SELECT * FROM telemetry_raw WHERE topic=%s AND device_id=%s"
                " ORDER BY id DESC LIMIT 1", (f"coldguard/{device}/telemetry", device),
            )
        else:
            cur.execute(
                "SELECT * FROM telemetry_raw WHERE topic=%s AND device_id=%s AND id>%s"
                " ORDER BY id LIMIT 16", (f"coldguard/{device}/telemetry", device, after),
            )
        return cur.fetchall()


def ack_now(conn, device, command_id, run_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.*, c.expires_at FROM command_acks a"
            " JOIN commands c ON c.command_id=a.command_id"
            " WHERE c.device_id=%s AND c.command_id=%s AND c.run_id=%s"
            " AND a.topic_device_id=%s AND a.payload_device_id=%s"
            " ORDER BY a.id LIMIT 1",
            (device, command_id, run_id, device, device),
        )
        return cur.fetchone()


@dataclass(frozen=True)
class Sample:
    seq: int
    uptime: int
    cooling: str
    duty: float
    current: float
    t2: float
    power_at: int
    power_seq: int
    electrical_evidence: str
    state: str
    reason: str
    received_at: datetime
    gateway_at: datetime

    @property
    def off(self):
        return (self.cooling == "OFF" and self.duty == self.current == 0
                and self.electrical_evidence == "MEASURED_IDLE_AND_ZERO")


def read_sample(row, device, boot, now):
    require(row["device_id"] == device, "WRONG_DEVICE")
    require(row["boot_id"] == boot, "BOOT_ID_CHANGED")
    require(row["ingest_status"] == RECEIVED_VALID, "INVALID_TELEMETRY")
    raw = row["raw_json"]
    require(isinstance(raw, dict) and raw.get("replay") is False, "INVALID_TELEMETRY")
    require(raw.get("device_id") == device and raw.get("boot_id") == boot
            and raw.get("seq") == row["seq"], "TELEMETRY_IDENTITY_MISMATCH")
    source = raw.get("serial_source") or {}
    frame = source.get("frame", "")
    require(isinstance(frame, str) and frame.startswith("#CG TELEM "), "MISSING_DEVICE_TELEMETRY")
    fields = _record_fields(frame.encode("ascii", "replace"))
    uptime, seq = raw.get("uptime_ms"), row["seq"]
    require(type(uptime) is int and type(seq) is int and seq > 0
            and fields.get("device_id") == device and fields.get("boot_id") == boot
            and fields.get("seq") == str(seq) and fields.get("uptime_ms") == str(uptime),
            "TELEMETRY_IDENTITY_MISMATCH")
    try:
        gateway_at = datetime.fromisoformat(source.get("gateway_received_at", ""))
    except (TypeError, ValueError):
        raise UnprovenTrial("STALE_TELEMETRY") from None
    received_at = row["backend_received_at"]
    require(fresh(received_at, now) and fresh(gateway_at, now) and gateway_at <= received_at,
            "STALE_TELEMETRY")

    def measurement(name, section, status, age):
        text = fields.get(name, "")
        require((raw.get("quality") or {}).get(section) == "VALID"
                and fields.get(status) == "OK", f"{section.upper()}_INVALID")
        require(age.isascii() and age.isdecimal()
                and 0 <= int(age) <= uptime
                and (now - gateway_at).total_seconds() + int(age) / 1000 < TELEMETRY_MAX_AGE_S,
                f"{section.upper()}_STALE")
        try:
            value = float(text)
        except ValueError:
            raise UnprovenTrial(f"{section.upper()}_MISSING") from None
        require(math.isfinite(value), f"{section.upper()}_INVALID")
        return value

    power_age = fields.get("power_age_ms", "")
    current = measurement("current_a", "electrical", "current_status", power_age)
    t2 = measurement("t_hot_side_c", "thermal", "t_hot_side_status", fields.get("thermal_age_ms", ""))
    require(fields.get("t_hot_side_src") == "T2" and fields.get("raw_t2_status") == "OK"
            and (raw.get("thermal") or {}).get("t2") == t2, "THERMAL_SOURCE_MISMATCH")
    electrical_current = (raw.get("electrical") or {}).get("current_a")
    power_seq = fields.get("power_seq", "")
    require(current >= 0 and type(electrical_current) in (int, float)
            and electrical_current == current and power_seq.isascii() and power_seq.isdecimal()
            and int(power_seq) > 0,
            "ELECTRICAL_INVALID")
    require(current < STOP_CURRENT_A and t2 < STOP_HOT_C, "SAFETY_LIMIT")
    require(fields.get("fault_code") == "0x00000000" and fields.get("output_stage") == "ENABLED",
            "DEVICE_FAULT_OR_DISABLED")
    require(fields.get("door_status") == "OK" and fields.get("door_open") == "0"
            and (raw.get("door") or {}).get("state") == "CLOSED", "DOOR_OPEN_OR_UNVERIFIED")
    applied = raw.get("actuation") or {}
    cooling, duty = applied.get("cooling"), applied.get("duty")
    require(fields.get("cooling_applied_source") == "FIRMWARE_OUTPUT_STATE"
            and cooling in ("ON", "OFF") and fields.get("cooling_applied") == cooling
            and type(duty) in (float, int) and math.isfinite(duty)
            and 0 <= duty <= 1 and fields.get("pwm_duty") == str(round(duty * 1000)),
            "APPLIED_STATE_INVALID")
    return Sample(seq, uptime, cooling, duty, current, t2, uptime - int(power_age), int(power_seq),
                  fields.get("cooling_evidence"), fields.get("tec_state"),
                  fields.get("fault_reason"), received_at, gateway_at)


@dataclass
class TrialEvidence:
    device: str
    boot: str
    command_id: str
    submitted_at: datetime
    baseline: Sample
    ack_uptime: int | None = None
    session: str | None = None
    arm_at: datetime | None = None
    start_at: datetime | None = None
    ack_observed_at: datetime | None = None
    start_window_ms: int | None = None
    start_anchor_seen: bool = False
    started_after: int | None = None
    first_on: int | None = None
    electrical: bool = False
    last_on: int | None = None
    last_on_power_seq: int | None = None
    applied_off_seen: bool = False
    final_off: bool = False

    def ack(self, row, now):
        require(row["command_id"] == self.command_id
                and row["topic_device_id"] == row["payload_device_id"] == self.device
                and row["boot_id"] == self.boot, "ACK_IDENTITY_MISMATCH")
        received = row["backend_received_at"]
        require(self.submitted_at <= received <= row["expires_at"]
                and fresh(received, now, ACK_WAIT_S), "ACK_STALE")
        require(row["validity"] == "VALID" and row["device_status"] == "ACCEPTED",
                "ACK_REJECTED")
        payload = json.loads(row["raw_payload"])
        require(row["time_sync_state"] == "SYNCHRONIZED" and row["expiry_evaluable"] is True
                and row["reapplied"] is False and row["output_stage"] == "ENABLED"
                and row["fault_code"] == "0x00000000"
                and payload.get("desired") == {"cooling": "ON", "duty": DUTY}
                and row["applied_cooling"] == "OFF" and row["applied_duty"] == 0,
                "ACK_REJECTED")
        uptime = row["uptime_ms"]
        require(type(uptime) is int and self.baseline.uptime < uptime
                < self.baseline.uptime + ACK_WAIT_S * 1000, "ACK_STALE")
        self.ack_uptime = uptime

    def console(self, event, now):
        if event.get("command_id") != self.command_id or event.get("device_id") != self.device:
            return
        require(event.get("boot_id") == self.boot and self.ack_uptime is not None
                and event.get("ack_uptime_ms") == self.ack_uptime, "CONSOLE_IDENTITY_MISMATCH")
        observed = datetime.fromisoformat(event["observed_at"])
        ack_observed = datetime.fromisoformat(event["ack_observed_at"])
        require(self.submitted_at <= ack_observed <= observed and fresh(observed, now, ACK_WAIT_S),
                "CONSOLE_RESULT_STALE")
        session = event.get("gateway_session_id")
        require(isinstance(session, str) and bool(session), "MISSING_GATEWAY_SESSION")
        if event.get("event") == "ARM":
            require(self.session is None and event.get("result") == event.get("state") == "ARMED",
                    "ARM_REJECTED")
            self.session = session
            self.arm_at = observed
            self.ack_observed_at = ack_observed
        elif event.get("event") == "START":
            require(self.session == session and self.started_after is None
                    and self.arm_at <= observed and self.ack_observed_at == ack_observed, "START_WITHOUT_ARM")
            require(event.get("result") == "OK" and event.get("state") == "COOLING"
                    and event.get("duty_permille") == str(SUPERVISED_DUTY_PERMILLE), "START_REJECTED")
            uptime = event.get("preceding_telemetry_uptime_ms")
            require(type(uptime) is int and 0 < uptime - self.ack_uptime < NETWORK_TIMEOUT * 1000,
                    "START_EVIDENCE_STALE")
            remaining = event.get("remaining_ms")
            require(isinstance(remaining, str) and remaining.isascii() and remaining.isdecimal()
                    and SUPERVISED_RUN_SECONDS * 1000 <= int(remaining) <= SUPERVISED_RUN_SECONDS * 1000 + 250,
                    "START_DURATION_INVALID")
            self.started_after = uptime
            self.start_at = observed
            self.start_window_ms = int(remaining)

    def observe(self, sample):
        if sample.uptime == self.started_after:
            require(sample.off and self.arm_at <= sample.gateway_at <= self.start_at,
                    "START_ANCHOR_INVALID")
            self.start_anchor_seen = True
        if sample.cooling == "ON":
            require(self.start_anchor_seen and sample.uptime > self.started_after
                    and sample.gateway_at >= self.start_at,
                    "APPLIED_WITHOUT_START_RESULT")
            require(not self.applied_off_seen, "UNEXPECTED_RESTART")
            require(sample.duty == DUTY and sample.state == "COOLING", "APPLIED_DUTY_MISMATCH")
            require(sample.uptime - self.started_after < (SUPERVISED_RUN_SECONDS + 3) * 1000,
                    "RUN_DURATION_EXCEEDED")
            if self.first_on is None:
                require(sample.uptime - self.started_after <= 2000, "APPLIED_TRANSITION_LATE")
                self.first_on = sample.uptime
            if sample.power_at >= self.first_on:
                require(sample.current > 0 and sample.electrical_evidence == "MEASURED_APPLIED_AND_DRAWING",
                        "PZEM_CONTRADICTS_APPLIED")
            self.last_on = sample.uptime
            self.last_on_power_seq = sample.power_seq
            self.electrical |= (sample.current > 0 and sample.power_at >= self.first_on
                                and sample.power_seq > self.baseline.power_seq
                                and sample.electrical_evidence == "MEASURED_APPLIED_AND_DRAWING")
        else:
            require(sample.duty == 0, "APPLIED_DUTY_MISMATCH")
            if self.first_on is not None:
                require(sample.reason in ("DURATION_REACHED", "COOLDOWN_DONE"), "RUN_ENDED_EARLY")
                require(sample.uptime - self.started_after >= self.start_window_ms - 250,
                        "RUN_ENDED_EARLY")
                require(self.last_on - self.first_on >= (SUPERVISED_RUN_SECONDS - 3) * 1000,
                        "RUN_ENDED_EARLY")
                self.applied_off_seen = True
                self.final_off = (sample.off and sample.power_at > self.last_on
                                  and sample.power_seq > self.last_on_power_seq)

    def verdict(self):
        if self.ack_uptime is None:
            return "ACK_MISSING"
        if self.session is None:
            return "ARM_RESULT_MISSING"
        if self.started_after is None:
            return "START_RESULT_MISSING"
        if self.first_on is None:
            return "APPLIED_TRANSITION_MISSING"
        if not self.electrical:
            return "PZEM_APPLIED_EVIDENCE_MISSING"
        if not self.final_off:
            return "FINAL_OFF_MISSING"
        return "TRIAL_PASS"


def run_trial(device, boot, command_id, *, frames, ack, receive, submit, stop, log,
              now=utcnow, clock=time.monotonic, pause=time.sleep):
    result = "TRIAL_INCOMPLETE"
    dispatch_attempted = False
    final_off = False
    try:
        rows = frames(None)
        require(bool(rows), "TELEMETRY_MISSING")
        row = rows[0]
        cursor = row["id"]
        previous = read_sample(row, device, boot, now())
        require(previous.off and previous.state == "OFF", "BASELINE_NOT_OFF_ZERO")
        state = TrialEvidence(device, boot, command_id, now(), previous)
        log("COMMAND_SUBMITTED", {})
        dispatch_attempted = True
        require(submit()["outcome"] == "puback", "COMMAND_DELIVERY_UNCONFIRMED")
        deadline = clock() + TRIAL_WAIT_S
        ack_deadline = clock() + ACK_WAIT_S
        console_events = []
        while clock() < deadline:
            console_events.extend(receive())
            require(len(console_events) <= 16, "CONSOLE_EVIDENCE_OVERFLOW")
            if state.ack_uptime is None and (ack_row := ack()) is not None:
                state.ack(ack_row, now())
                log("DEVICE_ACK", {"uptime_ms": state.ack_uptime})
            if state.ack_uptime is not None:
                for event in console_events:
                    state.console(event, now())
                    if event.get("command_id") == command_id and event.get("device_id") == device:
                        log("CONSOLE_RESULT", event)
                console_events.clear()
            elif clock() >= ack_deadline:
                break
            for row in frames(cursor):
                cursor = row["id"]
                sample = read_sample(row, device, boot, now())
                if sample.seq == previous.seq and sample.uptime == previous.uptime:
                    require(replace(sample, received_at=previous.received_at) == previous,
                            "TELEMETRY_ORDER_INVALID")
                    continue
                require(sample.seq == previous.seq + 1 and sample.uptime > previous.uptime,
                        "TELEMETRY_ORDER_INVALID")
                previous = sample
                state.observe(sample)
                log("DEVICE_SAMPLE", vars(sample))
            require(fresh(previous.received_at, now()), "STALE_TELEMETRY")
            if state.started_after is not None and previous.uptime == state.started_after and not state.start_anchor_seen:
                state.observe(previous)
            if state.final_off:
                break
            pause(0.15)
        result = state.verdict()
    except UnprovenTrial as exc:
        result = str(exc)
    except KeyboardInterrupt:
        result = "SUPERVISOR_ABORT"
    except Exception as exc:
        result = f"SUPERVISOR_FAILURE_{type(exc).__name__}"
    finally:
        if dispatch_attempted:
            try:
                # One zero-duty STOP attempt even if submission was ambiguous.
                stopped_at = now()
                stop_outcome = stop()
                log("STOP_REQUEST", {"outcome": stop_outcome.get("outcome")})
                until = clock() + STOP_WAIT_S
                while clock() < until:
                    rows = frames(cursor) if result == "TRIAL_PASS" else frames(None)
                    for row in rows:
                        cursor = row["id"]
                        sample = read_sample(row, device, boot, now())
                        if result == "TRIAL_PASS":
                            if replace(sample, received_at=previous.received_at) == previous:
                                continue
                            require(sample.seq == previous.seq + 1 and sample.uptime > previous.uptime,
                                    "TELEMETRY_ORDER_INVALID")
                            require(sample.off, "UNEXPECTED_OUTPUT_AFTER_TRIAL")
                            previous = sample
                        if sample.off and sample.gateway_at >= stopped_at:
                            final_off = True
                            log("STOP_OFF_CONFIRMED", vars(sample))
                    if final_off:
                        break
                    pause(0.15)
            except KeyboardInterrupt:
                result = "SUPERVISOR_ABORT"
                log("STOP_VERIFICATION_FAILED", {"error": "KeyboardInterrupt"})
            except Exception as exc:
                if result == "TRIAL_PASS":
                    result = str(exc) if isinstance(exc, UnprovenTrial) else "FINAL_OFF_MISSING"
                log("STOP_VERIFICATION_FAILED", {"error": type(exc).__name__})
            if not final_off:
                log("FINAL_OFF_MISSING", {})
                if result == "TRIAL_PASS":
                    result = "FINAL_OFF_MISSING"
        log("TRIAL_RESULT", {"result": result, "final_off_confirmed": final_off})
    return 0 if result == "TRIAL_PASS" and final_off else 1


@contextmanager
def console_results(host, port, device, command_id, password):
    topic = f"coldguard/{device}/leader-diag"
    publisher = Publisher(host=host, port=port, client_id=f"tec-evidence-{uuid4()}",
                          username="backend-ingest", password=password)
    pending = deque(maxlen=17)
    overflow = False

    def on_message(_client, _userdata, message):
        nonlocal overflow
        if message.topic != topic or message.retain or not message.payload.startswith(b"{"):
            return
        try:
            record = json.loads(message.payload)
        except (ValueError, UnicodeDecodeError):
            return
        if (isinstance(record, dict) and record.get("kind") == "tec_console_result"
                and record.get("command_id") == command_id):
            overflow |= len(pending) == pending.maxlen
            pending.append(record)

    def receive():
        publisher.poll()
        require(not overflow, "CONSOLE_EVIDENCE_OVERFLOW")
        events = list(pending)
        pending.clear()
        return events

    with publisher.session():
        publisher.client.on_message = on_message
        subscribe_confirmed(publisher, topic, supervised=True)
        yield receive


@contextmanager
def command_transport(host, port, password):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5,
                         reconnect_on_failure=False)
    client.connect_timeout = NETWORK_TIMEOUT
    client.username_pw_set("backend-command", password)
    transport = PahoCommandTransport(client, timeout_s=NETWORK_TIMEOUT)
    client.connect(host, port, keepalive=30)
    client.loop_start()
    try:
        until = time.monotonic() + NETWORK_TIMEOUT
        while not transport.is_ready() and time.monotonic() < until:
            time.sleep(0.05)
        require(transport.is_ready(), "COMMAND_TRANSPORT_UNAVAILABLE")
        yield transport
    finally:
        client.disconnect()
        client.loop_stop()


def runtime_config():
    names = ("DATABASE_URL", "MQTT_HOST", "MQTT_PORT",
             "MQTT_INGEST_PASSWORD", "MQTT_COMMAND_PASSWORD")
    for name in names:
        require(bool(os.environ.get(name)), f"CONFIGURATION_MISSING_{name}")
    dsn, host, port_text, ingest_password, command_password = (os.environ[name] for name in names)
    require(dsn.startswith(("postgresql://", "postgresql+psycopg://")), "DATABASE_URL_INVALID")
    # This runner uses plain MQTT, as did the local commissioning setup.
    require(host in ("localhost", "127.0.0.1", "::1"), "MQTT_HOST_REQUIRES_LOOPBACK")
    try:
        port = int(port_text)
    except ValueError:
        raise UnprovenTrial("MQTT_PORT_INVALID") from None
    require(1 <= port <= 65535, "MQTT_PORT_INVALID")
    return (dsn.replace("postgresql+psycopg://", "postgresql://", 1), host, port,
            {"backend-ingest": ingest_password, "backend-command": command_password})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--expected-boot", required=True)
    parser.add_argument("--command-id", required=True, type=UUID,
                        help="one-shot command ID displayed by the local Gateway console")
    parser.add_argument("--operator-approved", action="store_true",
                        help="confirm the operator authorized this specific live attempt")
    parser.add_argument("--evidence-dir", type=Path, default=Path("C:/cgb/demo-out"))
    args = parser.parse_args(argv)
    if not args.operator_approved:
        parser.error("separate operator authorization is required")
    if not BOOT_ID_RE.fullmatch(args.expected_boot) or not re.fullmatch(r"[A-Za-z0-9_-]+", args.device_id):
        parser.error("invalid device or boot identity")

    run_id, command_id = args.command_id.hex, str(args.command_id)
    base = {"run_id": run_id, "command_id": command_id,
            "device_id": args.device_id, "boot_id": args.expected_boot}
    path = args.evidence_dir / f"tec200-run-{run_id}.jsonl"
    try:
        with path.open("x", encoding="utf-8") as output, ExitStack() as stack:
            def log(event, fields):
                record = {**base, "event": event, "ts": utcnow(), "evidence": fields}
                print(json.dumps(record, default=str), file=output, flush=True)

            dsn, host, port, credentials = runtime_config()
            conn = stack.enter_context(psycopg.connect(
                dsn, autocommit=True, connect_timeout=4, row_factory=dict_row,
                options="-c default_transaction_read_only=on -c statement_timeout=2000",
            ))
            engine = create_engine(dsn.replace("postgresql://", "postgresql+psycopg://"),
                                   connect_args={"connect_timeout": 4})
            stack.callback(engine.dispose)
            receive = stack.enter_context(console_results(
                host, port, args.device_id, command_id, credentials["backend-ingest"],
            ))
            transport = stack.enter_context(command_transport(host, port, credentials["backend-command"]))
            key = uuid4().hex

            def dispatch(transport, *, cooling, duty, identity, reason):
                created = utcnow()
                command = Command.model_validate({
                    "schema_version": 1, "command_id": identity, "device_id": args.device_id,
                    "created_at": created, "expires_at": created + timedelta(seconds=15),
                    "controller_id": "REACTIVE", "policy_version": "leader-tec200",
                    "reason_code": reason, "run_id": run_id, "action": {"cooling": cooling, "duty": duty},
                })
                gateway = AuthorizedCommandGateway(
                    engine, transport, backend_token=key, allowed_devices=frozenset({args.device_id}),
                    policy_allows=lambda candidate: candidate == command,
                    transport_ready=transport.is_ready,
                )
                return gateway.dispatch(command, backend_token=key)

            def send_stop():
                # The ON transport retires itself on ambiguous QoS delivery.
                with command_transport(host, port, credentials["backend-command"]) as stop_transport:
                    return dispatch(stop_transport, cooling="OFF", duty=None, identity=str(uuid4()),
                                    reason=TEC_TRIAL_STOP_REASON)

            result = run_trial(
                args.device_id, args.expected_boot, command_id,
                frames=lambda after: frame_rows(conn, args.device_id, after),
                ack=lambda: ack_now(conn, args.device_id, command_id, run_id), receive=receive,
                submit=lambda: dispatch(transport, cooling="ON", duty=DUTY, identity=command_id,
                                        reason=TEC_TRIAL_REASON_PREFIX + args.expected_boot),
                stop=send_stop,
                log=log,
            )
            print(f"Trial exit={result}. Evidence: {path}")
            return result
    except UnprovenTrial as exc:
        print(f"Trial incomplete ({exc}). Evidence: {path}", file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt) as exc:
        print(f"Trial incomplete ({type(exc).__name__}). Evidence: {path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
