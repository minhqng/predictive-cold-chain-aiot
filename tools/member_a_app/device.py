"""Serial device link for the ColdGuard ESP32-S3 console.

Opening the port may reset the board through USB-Serial/JTAG, so DTR and
RTS are de-asserted immediately and the application then waits for live
frames instead of assuming a clean boot. Commands are never retried: a
lost acknowledgement is evidence, not a transient to paper over.
"""

from __future__ import annotations

import collections
import dataclasses
import datetime as _dt
import queue
import threading
import time
from typing import Any, Callable

from . import protocol
from .evidence import SessionStore

try:
    import serial
    from serial.tools import list_ports as _list_ports
except ImportError:  # pragma: no cover - exercised on machines without pyserial
    serial = None
    _list_ports = None


class DeviceError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class PortInfo:
    device: str
    description: str
    hwid: str
    vid: int | None
    pid: int | None
    serial_number: str | None


@dataclasses.dataclass
class DeviceSnapshot:
    connected: bool = False
    port: str | None = None
    firmware_kind: str | None = None
    boot: protocol.BootIdentity = dataclasses.field(default_factory=protocol.BootIdentity)
    auth_token: str | None = None
    rom_map: dict[str, protocol.RomEntry] = dataclasses.field(default_factory=dict)
    last_frame: protocol.TelemetryFrame | None = None
    last_ack: protocol.AckRecord | None = None
    last_tec_event: str | None = None
    door_polarity: str | None = None
    h8: dict[str, Any] = dataclasses.field(default_factory=dict)
    h8_last_result: str | None = None
    h8_ack_count: int = 0
    last_error: str | None = None
    rx_lines: int = 0
    tx_commands: int = 0
    last_rx_time: _dt.datetime | None = None

    def identity(self) -> dict[str, Any]:
        boot = self.boot
        return {
            "device_id": boot.device_id,
            "boot_id": boot.boot_id,
            "boot_count": boot.boot_count,
            "firmware_version": boot.firmware_version,
            "hardware_config_id": boot.hardware_config_id,
            "pin_map": boot.pin_map,
            "grammar": boot.grammar,
            "calibration_id": boot.calibration_id,
            "firmware_kind": self.firmware_kind,
            "port": self.port,
            "h8": dict(self.h8) if self.h8 else {},
        }


def list_ports() -> list[PortInfo]:
    if _list_ports is None:
        return []
    out: list[PortInfo] = []
    for item in _list_ports.comports():
        out.append(PortInfo(
            device=item.device,
            description=item.description or "",
            hwid=item.hwid or "",
            vid=item.vid,
            pid=item.pid,
            serial_number=item.serial_number,
        ))
    return sorted(out, key=lambda item: item.device)


class DeviceLink:
    is_simulated = False

    def __init__(self, store: SessionStore | None = None):
        self._store = store
        self._serial = None
        self._reader: threading.Thread | None = None
        self._reader_stop: threading.Event | None = None
        self._generation = 0
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._events: collections.deque[protocol.ParsedLine] = collections.deque(maxlen=20000)
        self._frames: collections.deque[protocol.TelemetryFrame] = collections.deque(maxlen=20000)
        self._event_cursor = 0
        self._frame_cursor = 0
        self.h8_ack_enabled = False
        self.snapshot = DeviceSnapshot()

    def open(self, port: str, baud: int = protocol.BAUD) -> None:
        if serial is None:
            raise DeviceError("pyserial is not installed for this interpreter")
        with self._lock:
            if self._serial is not None:
                raise DeviceError("a port is already open")
            self._open_locked(port, baud)

    def _open_locked(self, port: str, baud: int) -> None:
        handle = serial.Serial()
        handle.port = port
        handle.baudrate = baud
        handle.timeout = 0.2
        handle.write_timeout = 2.0
        handle.open()
        try:
            handle.dtr = False
            handle.rts = False
        except Exception:
            pass
        self._serial = handle
        self.snapshot.connected = True
        self.snapshot.port = port
        self.snapshot.last_error = None
        self._generation += 1
        generation = self._generation
        stop_event = threading.Event()
        self._reader_stop = stop_event
        self._reader = threading.Thread(target=self._read_loop,
                                        args=(generation, handle, stop_event),
                                        name="cg-serial", daemon=True)
        self._reader.start()

    def _stop_reader(self) -> None:
        with self._lock:
            self.h8_ack_enabled = False
            stop_event = self._reader_stop
            reader = self._reader
            self._reader_stop = None
            self._reader = None
            self._generation += 1
            handle = self._serial
            self._serial = None
            self.snapshot.connected = False
            if stop_event is not None:
                stop_event.set()
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
        if reader is not None and reader.is_alive() and reader is not threading.current_thread():
            reader.join(timeout=2.0)

    def reboot_warm(self, gap_s: float = 0.3) -> bool:
        """Proven USB-Serial/JTAG reset: close, reopen, drop DTR/RTS.

        The repo's cg_auto_reboot.py showed that an RTS-only pulse does not
        reset this S3; the open->drop transition is the proven path. The
        previous ROM/auth/boot identity is cleared so a stale map cannot be
        reported for the new boot.
        """
        with self._lock:
            port = self.snapshot.port
            if port is None or self._serial is None:
                return False
        self._stop_reader()
        with self._lock:
            self.snapshot.rom_map.clear()
            self.snapshot.auth_token = None
            self.snapshot.last_frame = None
            self.snapshot.boot = protocol.BootIdentity()
            self.snapshot.h8.clear()
            self.snapshot.h8_last_result = None
            self.snapshot.h8_ack_count = 0
        time.sleep(max(0.0, gap_s))
        with self._lock:
            try:
                self._open_locked(port, protocol.BAUD)
                return True
            except Exception as exc:
                self.snapshot.last_error = f"WARM_REBOOT_FAILED: {exc}"
                self.snapshot.connected = False
                return False

    def prepare_cold_boot(self) -> bool:
        with self._lock:
            if self._serial is None:
                return False
        self._stop_reader()
        with self._lock:
            self.snapshot.rom_map.clear()
            self.snapshot.auth_token = None
            self.snapshot.last_frame = None
            self.snapshot.boot = protocol.BootIdentity()
            self.snapshot.h8.clear()
            self.snapshot.h8_last_result = None
            self.snapshot.h8_ack_count = 0
        return True

    def reopen_after_cold_boot(self) -> bool:
        with self._lock:
            port = self.snapshot.port
            if port is None:
                return False
            try:
                self._open_locked(port, protocol.BAUD)
                return True
            except Exception as exc:
                self.snapshot.last_error = f"COLD_BOOT_REOPEN_FAILED: {exc}"
                self.snapshot.connected = False
                return False

    def close(self) -> None:
        self._stop_reader()

    def send(self, command: bytes, description: str = "") -> None:
        if not isinstance(command, bytes):
            raise DeviceError("commands must be bytes")
        with self._lock:
            handle = self._serial
            if handle is None:
                raise DeviceError("no device connected")
            if not command.endswith(b"\n"):
                raise DeviceError("command must be newline terminated")
            handle.write(command)
            handle.flush()
            self.snapshot.tx_commands += 1
        text = command.decode("ascii", errors="replace")
        if self._store is not None:
            self._store.append_raw("TX", text)
        self._notify()

    def _read_loop(self, generation: int, handle: Any,
                   stop_event: threading.Event) -> None:
        buffer = bytearray()
        while not stop_event.is_set():
            if generation != self._generation:
                break
            try:
                chunk = handle.read(256)
            except Exception as exc:
                with self._lock:
                    if generation == self._generation:
                        self.snapshot.last_error = f"SERIAL_ERROR: {exc}"
                        self.snapshot.connected = False
                        self._serial = None
                        self._generation += 1
                stop_event.set()
                try:
                    handle.close()
                except Exception:
                    pass
                self._notify()
                break
            if not chunk:
                continue
            buffer.extend(chunk)
            while b"\n" in buffer:
                line, _, buffer = buffer.partition(b"\n")
                if generation != self._generation or stop_event.is_set():
                    return
                text = line.decode("utf-8", errors="replace").rstrip("\r")
                self.feed_line(text)

    def feed_line(self, line: str, host_time: _dt.datetime | None = None) -> protocol.ParsedLine:
        stamp = host_time or protocol.utcnow()
        parsed = protocol.parse_line(line, stamp)
        with self._lock:
            self._events.append(parsed)
            self._event_cursor += 1
            self.snapshot.rx_lines += 1
            self.snapshot.last_rx_time = stamp
            if parsed.boot is not None:
                self.snapshot.boot = self.snapshot.boot.merged(parsed.boot)
            if parsed.auth_token:
                self.snapshot.auth_token = parsed.auth_token
            if parsed.kind == "H8_BOOT":
                self.snapshot.firmware_kind = "H8_BENCH"
                for key in ("test_mode", "mandatory_roles", "mandatory_probes",
                            "supervised", "reset_cause", "sim_cooling"):
                    if key in parsed.kv:
                        self.snapshot.h8[key] = parsed.kv[key]
            elif parsed.kind in {"H8_BOOT_POLICY", "H8_BOOT_OFF_CURRENT"}:
                self.snapshot.firmware_kind = "H8_BENCH"
                for key, value in parsed.kv.items():
                    self.snapshot.h8[key] = value
            elif parsed.kind == "TEC_LIMITS" and "stage_f_guard" in parsed.kv:
                # Boot-time authorization flags; the H8 image reports the
                # Stage F guard here, not in the telemetry frame.
                for key in ("stage_f_guard", "endurance_stages",
                            "operator_approved", "required_resolved",
                            "all_resolved"):
                    if key in parsed.kv:
                        self.snapshot.h8[key] = parsed.kv[key]
            elif parsed.kind == "H8_CMD":
                self.snapshot.h8_last_result = parsed.kv.get("result")
                results = self.snapshot.h8.setdefault("cmd_results", [])
                if isinstance(results, list):
                    results.append({key: value for key, value in parsed.kv.items()})
                    del results[:-30]
            if parsed.rom is not None:
                self.snapshot.rom_map[parsed.rom.role] = parsed.rom
            if parsed.frame is not None:
                self.snapshot.last_frame = parsed.frame
                self.snapshot.firmware_kind = "H8_BENCH" if parsed.frame.is_h8 else "CANONICAL"
                self._frames.append(parsed.frame)
                self._frame_cursor += 1
                self.snapshot.boot = self.snapshot.boot.merged(protocol.BootIdentity(
                    boot_id=parsed.frame.boot_id,
                    device_id=parsed.frame.device_id,
                    firmware_version=parsed.frame.firmware_version,
                    hardware_config_id=parsed.frame.hardware_config_id,
                    calibration_id=parsed.frame.calibration_id,
                ))
                if parsed.frame.is_h8 and self.snapshot.boot.device_id is None:
                    self.snapshot.boot = self.snapshot.boot.merged(
                        protocol.BootIdentity(device_id="H8_BENCH"))
                if parsed.frame.is_h8:
                    for key in ("test_mode", "supervised_bench", "supervised_authorized",
                                "stage", "off_current_approved", "limits_operator_approved",
                                "limits_enforced", "interlock_state", "fan",
                                "door_polarity"):
                        if key in parsed.frame.kv:
                            self.snapshot.h8[key] = parsed.frame.kv[key]
                for role, key in (("T1", "t1_rom"), ("T2", "t2_rom"),
                                  ("T3", "t3_rom"), ("SPARE", "spare_rom")):
                    rom = (parsed.frame.kv.get(key) or "").upper()
                    if (len(rom) == 16 and all(ch in "0123456789ABCDEF" for ch in rom)
                            and role not in self.snapshot.rom_map):
                        self.snapshot.rom_map[role] = protocol.RomEntry(
                            role=role, rom=rom, present=True, status="TELEM_FIELD")
            if parsed.ack is not None:
                self.snapshot.last_ack = parsed.ack
            if parsed.kind == "TEC":
                self.snapshot.last_tec_event = parsed.kv.get("event")
            if parsed.kind == "DOOR_POLARITY":
                self.snapshot.door_polarity = (
                    f"{parsed.kv.get('state', 'UNKNOWN')} "
                    f"raw_open={parsed.kv.get('raw_open_level', '?')}")
            if parsed.frame is not None and parsed.frame.kv.get("door_polarity"):
                self.snapshot.door_polarity = parsed.frame.kv["door_polarity"]
            if parsed.kind == "ERR":
                self.snapshot.last_error = parsed.kv.get("msg", parsed.raw)
            if parsed.error:
                self.snapshot.last_error = parsed.error
        if self._store is not None:
            self._store.append_raw("RX", parsed.raw, stamp.isoformat())
            if parsed.frame is not None:
                self._store.append_telemetry(parsed.frame)
        if self.h8_ack_enabled and parsed.frame is not None and parsed.frame.is_h8:
            try:
                self.send_h8_ack(parsed.frame)
            except Exception as exc:
                with self._lock:
                    self.snapshot.last_error = f"H8_ACK_SEND_FAILED: {exc}"
        self._notify()
        return parsed

    def set_h8_ack(self, enabled: bool) -> None:
        self.h8_ack_enabled = bool(enabled)

    def send_h8_ack(self, frame: protocol.TelemetryFrame) -> bytes | None:
        from . import protocol_h8
        command = protocol_h8.ack_from_frame(frame)
        if command is None:
            return None
        self.send(command, "H8 host ACK")
        with self._lock:
            self.snapshot.h8_ack_count += 1
        return command

    def wait_for_h8_cmd(self, result_prefix: str, timeout_s: float,
                        cursor: int | None = None) -> protocol.ParsedLine | None:
        return self.wait_for_event(
            lambda event: event.kind == "H8_CMD"
            and str(event.kv.get("result", "")).startswith(result_prefix),
            timeout_s, cursor)

    def wait_for_h8_state(self, state: str, timeout_s: float) -> protocol.TelemetryFrame | None:
        return self.wait_for_frame(
            lambda frame: frame.is_h8 and frame.state == state, timeout_s)

    def _notify(self) -> None:
        with self._lock:
            self._condition.notify_all()

    def latest_frame(self) -> protocol.TelemetryFrame | None:
        with self._lock:
            return self.snapshot.last_frame

    def frames_since(self, cursor: int) -> tuple[list[protocol.TelemetryFrame], int]:
        with self._lock:
            if not self._frames:
                return [], self._frame_cursor
            start = max(0, self._frame_cursor - len(self._frames))
            skip = max(0, cursor - start)
            return list(self._frames)[skip:], self._frame_cursor

    def events_since(self, cursor: int) -> tuple[list[protocol.ParsedLine], int]:
        with self._lock:
            if not self._events:
                return [], self._event_cursor
            start = max(0, self._event_cursor - len(self._events))
            skip = max(0, cursor - start)
            return list(self._events)[skip:], self._event_cursor

    def event_cursor(self) -> int:
        with self._lock:
            return self._event_cursor

    def frame_cursor(self) -> int:
        with self._lock:
            return self._frame_cursor

    def wait_for_event(self, predicate: Callable[[protocol.ParsedLine], bool],
                       timeout_s: float, cursor: int | None = None) -> protocol.ParsedLine | None:
        deadline = time.monotonic() + max(0.0, timeout_s)
        position = self.event_cursor() if cursor is None else cursor
        while True:
            events, position = self.events_since(position)
            for event in events:
                if predicate(event):
                    return event
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            with self._condition:
                self._condition.wait(timeout=min(remaining, 0.25))

    def wait_for_boot(self, previous_boot_id: str | None, timeout_s: float,
                      cursor: int | None = None) -> protocol.BootIdentity | None:
        def is_new_boot(event: protocol.ParsedLine) -> bool:
            if event.kind not in {"BOOT", "LOG", "H8_BOOT"} or event.boot is None:
                return False
            boot_id = event.boot.boot_id
            return bool(boot_id and boot_id != previous_boot_id)

        event = self.wait_for_event(is_new_boot, timeout_s, cursor)
        return event.boot if event is not None else None

    def wait_for_frame(self, predicate: Callable[[protocol.TelemetryFrame], bool],
                       timeout_s: float) -> protocol.TelemetryFrame | None:
        deadline = time.monotonic() + max(0.0, timeout_s)
        while True:
            frame = self.latest_frame()
            if frame is not None and predicate(frame):
                return frame
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            with self._condition:
                self._condition.wait(timeout=min(remaining, 0.25))

    def wait_for_ack(self, command_id: str | None, timeout_s: float,
                     cursor: int | None = None) -> protocol.AckRecord | None:
        def matches(event: protocol.ParsedLine) -> bool:
            if event.ack is None:
                return False
            return command_id is None or event.ack.command_id == command_id

        event = self.wait_for_event(matches, timeout_s, cursor)
        return event.ack if event is not None else None

    def pulse_warm_reset(self) -> bool:
        """Backward-compatible name for the proven close/reopen reset path."""
        return self.reboot_warm()


class FakeDeviceLink(DeviceLink):
    """In-process device double.

    It never reports hardware evidence: every runner result produced with
    this link is stamped SIMULATED and cannot become PASS.
    """

    is_simulated = True

    def __init__(self, store: SessionStore | None = None):
        super().__init__(store)
        self.sent: list[bytes] = []
        self.snapshot.connected = True
        self.snapshot.port = "FAKE"

    def open(self, port: str = "FAKE", baud: int = protocol.BAUD) -> None:
        self.snapshot.connected = True
        self.snapshot.port = port

    def close(self) -> None:
        self.snapshot.connected = False

    def send(self, command: bytes, description: str = "") -> None:
        if not command.endswith(b"\n"):
            raise DeviceError("command must be newline terminated")
        self.sent.append(command)
        if self._store is not None:
            self._store.append_raw("TX", command.decode("ascii", errors="replace"))
        self.snapshot.tx_commands += 1

    def pulse_warm_reset(self) -> bool:
        return True

    def reboot_warm(self, gap_s: float = 0.3) -> bool:
        return True

    def prepare_cold_boot(self) -> bool:
        self.snapshot.connected = False
        return True

    def reopen_after_cold_boot(self) -> bool:
        self.snapshot.connected = True
        return True
