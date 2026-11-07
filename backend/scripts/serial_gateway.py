"""Read Member A telemetry and publish the clockless Member C wire envelope."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from time import monotonic

import paho.mqtt.client as mqtt

from coldguard_backend.contracts import SERIAL_FRAME_MAX
from coldguard_backend.serial_observation import serial_observation
from coldguard_backend.validation import validate_telemetry_payload, validate_topic_identity

# This checkout-based entrypoint uses Member A's committed parser directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from firmware.tools.cg_telemetry_schema import (  # noqa: E402
    TelemetryError, parse_line, position_of_rom,
)

log = logging.getLogger(__name__)
NETWORK_TIMEOUT = 5


def translate(frame: bytes, *, topic: str, gateway_received_at: datetime, replay: bool) -> bytes:
    """Validate and translate one complete serial frame, retaining its source text."""
    if len(frame) > SERIAL_FRAME_MAX or any(byte < 32 or byte > 126 for byte in frame):
        raise TelemetryError("oversized or non-printable telemetry frame")
    record = parse_line(frame.decode("ascii"))
    fields = record.fields
    if fields["schema"] == 1:
        raise TelemetryError("serial schema 1 lacks the canonical device/sequence identity")
    if "uptime_ms" not in fields:
        raise TelemetryError("missing device uptime")
    try:
        observation = serial_observation(record.raw_fields)
    except ValueError as exc:
        raise TelemetryError(str(exc)) from exc
    observation["thermal"]["t2_role"] = position_of_rom(fields["t2_rom"])

    payload = {
        "schema_version": 2,
        "captured_at": None,
        "serial_source": {
            "schema_version": fields["schema"],
            "clock_quality": "UNAVAILABLE",
            "gateway_received_at": gateway_received_at.isoformat(),
            "frame": record.raw,
        },
        **observation,
        "run_id": None if fields["run_id"] == "UNSET" else fields["run_id"],
        "calibration_id": None if fields["calibration_id"] == "UNRECORDED" else fields["calibration_id"],
        "replay": replay,
        **{key: fields[key] for key in (
            "device_id", "boot_id", "seq", "uptime_ms",
            "hardware_config_id", "firmware_version",
        )},
    }
    validated, errors = validate_telemetry_payload(payload)
    if validated is None:
        raise TelemetryError(f"cannot translate telemetry: {errors[0]['loc']}: {errors[0]['code']}")
    if validate_topic_identity(topic, validated):
        raise TelemetryError("serial device identity disagrees with the configured MQTT topic")
    return json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()


class SerialFramer:
    """Bounded newline framing across fragmented reads and serial timeouts."""

    def __init__(self):
        self.pending = bytearray()
        self.discard = False

    def feed(self, chunk):
        for byte in chunk:
            if byte == 10:
                if not self.discard:
                    yield bytes(self.pending).removesuffix(b"\r")
                self.pending.clear()
                self.discard = False
            elif not self.discard:
                if len(self.pending) == SERIAL_FRAME_MAX + 1:
                    log.warning("discarding oversized serial line")
                    self.pending.clear()
                    self.discard = True
                else:
                    self.pending.append(byte)


class PublishError(OSError):
    """The broker did not confirm publication."""


class Publisher:
    """One MQTT session with at most one in-flight QoS 1 message."""

    def __init__(self, *, host, port, client_id, username=None, password=None, tls=False, ca=None):
        self.host = host
        self.port = port
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=client_id,
            protocol=mqtt.MQTTv5, reconnect_on_failure=False,
        )
        self.client.connect_timeout = NETWORK_TIMEOUT
        if username is not None:
            self.client.username_pw_set(username, password)
        if tls:
            self.client.tls_set(ca_certs=ca)
        self.connect_reason = None
        self.ack = None
        self.client.on_connect = self._on_connect
        self.client.on_publish = self._on_publish

    def _on_connect(self, client, userdata, flags, reason, properties):
        self.connect_reason = reason

    def _on_publish(self, client, userdata, mid, reason, properties):
        self.ack = (mid, reason)

    def poll(self, timeout=0):
        if self.client.loop(timeout=timeout) != mqtt.MQTT_ERR_SUCCESS:
            raise PublishError("MQTT network loop disconnected")

    def _wait(self, ready):
        deadline = monotonic() + NETWORK_TIMEOUT
        while not ready():
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise PublishError("timed out waiting for broker acknowledgement")
            self.poll(min(0.2, remaining))

    @contextmanager
    def session(self):
        try:
            if self.client.connect(self.host, self.port) != mqtt.MQTT_ERR_SUCCESS:
                raise PublishError("MQTT connect failed")
            self._wait(lambda: self.connect_reason is not None)
            if self.connect_reason.is_failure:
                raise PublishError(f"MQTT connect refused: {self.connect_reason}")
            yield self
        finally:
            self.client.disconnect()

    def publish(self, topic, payload):
        self.ack = None
        delivery = self.client.publish(topic, payload, qos=1, retain=False)
        if delivery.rc != mqtt.MQTT_ERR_SUCCESS:
            raise PublishError(f"MQTT publish failed: {delivery.rc}")
        self._wait(lambda: self.ack is not None and self.ack[0] == delivery.mid)
        if self.ack[1].is_failure:
            raise PublishError(f"MQTT publish refused: {self.ack[1]}")


def pump(stream, publisher, *, topic, replay, stop):
    framer = SerialFramer()
    while not stop.is_set():
        publisher.poll()
        chunk = stream.read(512)
        received_at = datetime.now(timezone.utc)
        if not chunk and replay:
            if framer.pending:
                log.warning("discarding unterminated capture line")
            return
        for frame in framer.feed(chunk):
            if frame != b"#CG TELEM" and not frame.startswith(b"#CG TELEM "):
                continue  # CMDACK and other source records have their own contracts.
            try:
                payload = translate(
                    frame, topic=topic, gateway_received_at=received_at, replay=replay,
                )
            except TelemetryError as exc:
                log.warning("discarding invalid telemetry frame: %s", exc)
                continue
            publisher.publish(topic, payload)


def run_live(open_serial, connect, *, topic, stop, retry_delay=2):
    while not stop.is_set():
        try:
            with connect() as publisher, open_serial() as stream:
                # Discard unread driver backlog and any partial line on every session.
                stream.reset_input_buffer()
                pump(stream, publisher, topic=topic, replay=False, stop=stop)
        except OSError as exc:
            log.warning("live gateway session ended: %s", exc)
            stop.wait(retry_delay)


def open_serial_port(port, baud):
    import serial

    stream = serial.Serial(baudrate=baud, timeout=0.25)
    stream.dtr = stream.rts = False
    stream.port = port
    stream.open()
    return stream


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--serial-port")
    inputs.add_argument("--replay-file", type=Path)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--topic")
    parser.add_argument("--broker-host", default="localhost")
    parser.add_argument("--broker-port", type=int)
    parser.add_argument("--client-id")
    parser.add_argument("--tls", action="store_true")
    parser.add_argument("--ca-file")
    args = parser.parse_args(argv)
    canonical_topic = f"coldguard/{args.device_id}/telemetry"
    if not args.device_id.strip() or any(c in args.device_id for c in "/+#\0"):
        parser.error("invalid device ID")
    if args.topic and args.topic != canonical_topic:
        parser.error("--topic must be the configured device's canonical telemetry topic")
    if args.baud <= 0 or (args.broker_port is not None and not 1 <= args.broker_port <= 65535):
        parser.error("baud must be positive and broker port must be in 1..65535")
    username, password = os.environ.get("MQTT_USERNAME"), os.environ.get("MQTT_PASSWORD")
    tls = args.tls or args.ca_file is not None
    if password is not None and not username:
        parser.error("MQTT_PASSWORD requires MQTT_USERNAME")
    if not tls and args.broker_host not in ("localhost", "127.0.0.1", "::1"):
        parser.error("non-loopback MQTT requires TLS")

    def connect():
        return Publisher(
            host=args.broker_host, port=args.broker_port or (8883 if tls else 1883),
            client_id=args.client_id or f"serial-{args.device_id}",
            username=username, password=password, tls=tls, ca=args.ca_file,
        ).session()

    logging.basicConfig(level=logging.INFO)
    stop = Event()
    try:
        if args.replay_file:
            with connect() as publisher, args.replay_file.open("rb") as stream:
                pump(stream, publisher, topic=canonical_topic, replay=True, stop=stop)
        else:
            run_live(
                lambda: open_serial_port(args.serial_port, args.baud), connect,
                topic=canonical_topic, stop=stop,
            )
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        log.error("gateway stopped: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
