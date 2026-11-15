"""Leader gateway entrypoint with the opt-in device-directed downlink.

Composes the delivered Member C gateway (telemetry translation, serial
framing, MQTT publisher sessions, serial port handling) with the Leader-owned
bridge in ``integration.leader_downlink``. Member-delivered files are
imported verbatim, never modified, and the COM port keeps a single owner by
construction: the downlink runs in this same process over the same serial
stream and MQTT session as the telemetry pump; no second serial process is
started.

Telemetry-only operation does not need this entrypoint: run the delivered
``scripts/serial_gateway.py`` unchanged. This entrypoint exists for the demo
command path and installs the bridge only with an explicit
``--enable-downlink``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from time import monotonic
from uuid import uuid4

# Import layout mirrors backend/scripts/serial_gateway.py: this checkout's
# backend/ goes on sys.path so the member gateway module and the Leader
# integration package resolve as delivered.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integration.leader_downlink import (
    AUTH_PREFIX, DEVICE_ACK_PREFIX, SYNC_PERIOD_S, CommandSerialWriter, DownlinkBridge,
)
from scripts.serial_gateway import (  # Member C, delivered verbatim
    NETWORK_TIMEOUT, Publisher, SerialFramer, TelemetryError,
    open_serial_port, translate,
)

log = logging.getLogger(__name__)


def operator_console(bridge):
    """Read the foreground Windows console without blocking the serial pump."""
    if os.name != "nt" or not sys.stdin.isatty():
        return None
    import msvcrt

    line = ""
    overflow = False
    print("Observe only. After operator GO, type GRANT TEC200. Type ABORT TEC200 to stop.", flush=True)

    def poll():
        nonlocal line, overflow
        for _ in range(32):
            if not msvcrt.kbhit():
                break
            char = msvcrt.getwch()
            if char == "\r":
                print(flush=True)
                if not overflow and line == "GRANT TEC200":
                    command = str(uuid4())
                    boot = bridge.grant_trial(command)
                    if boot:
                        print(f"Trial grant: device={bridge.device_id} boot={boot} command={command}", flush=True)
                    else:
                        print("Grant refused: requires a ready current boot and an unused session.", flush=True)
                elif not overflow and line == "ABORT TEC200":
                    bridge.abort_trial()
                    print("Trial authority revoked. Verify final OFF/0.", flush=True)
                line = ""
                overflow = False
            elif char == "\b":
                line = line[:-1]
            elif len(line) < 32:
                line += char
            else:
                overflow = True

    return poll


def pump_leader(stream, publisher, *, topic, stop, bridge, poll_operator=None):
    """The delivered Member C telemetry loop, hosted by this Leader
    entrypoint so CMDACK frames can take the opt-in bridge branch. Member
    semantics (framing, translation, provenance retention, discards) run
    through the member's own code paths, called unchanged.

    Leader addition: the member pump discards non-TELEM/CMDACK #CG frames
    (SAMPLE/PZEM/BOOT and other source records) because they carry their own
    contracts. Those same frames are the device's own hardware-health
    evidence (BME280 state/reason, PZEM Modbus discovery, boot provenance),
    so while the member contract stays untouched, this entrypoint mirrors
    each discarded frame verbatim to the device's .../leader-diag topic for
    out-of-band inspection on a Leader-owned runtime topic.
    """
    framer = SerialFramer()
    bridge.poll_operator = poll_operator
    diag_topic = topic.rsplit("/", 1)[0] + "/leader-diag"
    next_sync_at = 0.0
    while not stop.is_set():
        if poll_operator is not None:
            poll_operator()
        publisher.poll()
        chunk = stream.read(512)
        read_at = monotonic()
        received_at = datetime.now(timezone.utc)
        for frame in framer.feed(chunk):
            if poll_operator is not None:
                poll_operator()
            if AUTH_PREFIX in frame or b"token=" in frame:
                # A partial serial line may be joined to AUTH. Keep the
                # credential out of diagnostics and parser error messages.
                bridge.note_frame(frame)
                continue
            if frame.startswith(DEVICE_ACK_PREFIX):
                try:
                    bridge.relay_ack(frame.decode("ascii"), observed_at=received_at)
                except UnicodeDecodeError as exc:
                    log.warning("uplink: non-ASCII device ACK discarded: %s", exc)
                    bridge.stats["acks_invalid"] += 1
                continue  # relayed by the opt-in bridge above; no telemetry contract
            if frame != b"#CG TELEM" and not frame.startswith(b"#CG TELEM "):
                result = bridge.note_frame(frame, observed_at=received_at)
                if result is not None:
                    publisher.publish(diag_topic, json.dumps(result, separators=(",", ":")))
                if frame.startswith(b"#CG "):
                    publisher.publish(diag_topic, frame.decode("ascii", "replace").rstrip("\n"))
                continue  # SAMPLE/PZEM/BOOT and other source records have their own contracts.
            try:
                payload = translate(
                    frame, topic=topic, gateway_received_at=received_at, replay=False,
                )
            except TelemetryError as exc:
                bridge.invalidate_telemetry()
                log.warning("discarding invalid telemetry frame: %s", exc)
                continue
            bridge.note_telemetry(json.loads(payload), read_at=read_at)
            publisher.publish(topic, payload)
        if bridge.auto_sync and monotonic() >= next_sync_at:
            bridge.sync_tick()
            next_sync_at = monotonic() + SYNC_PERIOD_S


def run_live_downlink(open_serial, connect, *, topic, stop, make_bridge, console=None):
    """Own one serial session. Transport loss ends all authority and capture."""
    if stop.is_set():
        return
    with connect() as publisher, open_serial() as stream:
        bridge = make_bridge(publisher, stream)
        try:
            bridge.install()
            pump_leader(stream, publisher, topic=topic, stop=stop, bridge=bridge,
                        poll_operator=console(bridge) if console else None)
        except KeyboardInterrupt:
            bridge.abort_trial()
            raise
        finally:
            bridge.close()


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
    parser.add_argument("--enable-downlink", action="store_true",
                        help="install the device-directed command bridge "
                        "(downlink subscription + CMDACK relay). Required on "
                        "this Leader entrypoint; telemetry-only sessions are "
                        "served by the delivered scripts/serial_gateway.py.")
    parser.add_argument("--operator-console", action="store_true",
                        help="enable local trial confirmation on a foreground Windows console. "
                             "Starts in observe-only mode and captures BOOT/AUTH. "
                             "A trial needs a separate typed operator grant.")
    parser.add_argument("--expect-command-id",
                        help="with --enable-downlink: log ACK correlation "
                        "against this command id (correlation itself stays "
                        "the backend's fail-closed authority)")
    parser.add_argument("--device-envelope", action="store_true",
                        help="with --enable-downlink: deliver commands as "
                        "the device's reserved '#CG CMD <record>' canonical "
                        "envelope instead of the operator-console CMDTEST "
                        "form. Requires a device image whose boot record "
                        "advertises '#CG NETCMD status=READY' (the "
                        "Leader-owned cg_leader_ingress component); on an "
                        "image without it the delivered console refuses "
                        "envelopes as UNKNOWN_COMMAND.")
    args = parser.parse_args(argv)
    canonical_topic = f"coldguard/{args.device_id}/telemetry"
    if not args.device_id.strip() or any(c in args.device_id for c in "/+#\0"):
        parser.error("invalid device ID")
    if args.topic and args.topic != canonical_topic:
        parser.error("--topic must be the configured device's canonical telemetry topic")
    if args.baud <= 0 or (args.broker_port is not None and not 1 <= args.broker_port <= 65535):
        parser.error("baud must be positive and broker port must be in 1..65535")
    if not args.enable_downlink:
        parser.error("--enable-downlink is required on the Leader entrypoint; "
                     "telemetry-only operation belongs to scripts/serial_gateway.py")
    if args.replay_file:
        parser.error("--enable-downlink requires a live serial port, not replay")
    if args.operator_console and not (args.device_envelope and os.name == "nt" and sys.stdin.isatty()):
        parser.error("--operator-console requires --device-envelope and a foreground Windows console")
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

    def open_stream():
        stream = open_serial_port(args.serial_port, args.baud)
        try:
            stream.write_timeout = NETWORK_TIMEOUT
        except BaseException:
            stream.close()
            raise
        return stream

    logging.basicConfig(level=logging.INFO)
    stop = Event()
    try:
        run_live_downlink(
            open_stream, connect,
            topic=canonical_topic, stop=stop,
            console=operator_console if args.operator_console else None,
            make_bridge=lambda publisher, stream: DownlinkBridge(
                args.device_id,
                write_line=CommandSerialWriter(stream),
                publisher=publisher,
                expect_command_id=args.expect_command_id,
                device_envelope=args.device_envelope,
            ),
        )
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        log.error("gateway stopped: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
