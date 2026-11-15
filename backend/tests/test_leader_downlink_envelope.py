"""Leader integration tests: the opt-in device-envelope transport mode.

Covers the ``--device-envelope`` branch of the Leader downlink bridge against
the device-side Leader ingress contract (cg_leader_ingress / "#CG CMD "):

* envelope mode renders Member C's committed flat record behind the reserved
  prefix; a canonical UUID is exactly the identity this form must carry;
* the actuation gate runs BEFORE any write in both modes;
* a record Member C's own renderer refuses is refused on the gateway side
  with nothing written;
* the default (no flag) stays the delivered CMDTEST path - where the label
  grammar legitimately refuses a canonical UUID instead of mangling it.

No physical device, no broker, no database: Member C's translations run as
delivered, in-process.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from integration.leader_downlink import DownlinkBridge  # noqa: E402
from tests.command_testkit import make_command  # noqa: E402

DEVICE = "coldguard-001"
UUID_ID = "00000000-0000-4000-8000-00000000000e"
COMMAND_TOPIC = f"coldguard/{DEVICE}/command"

ENVELOPE_FIELDS = (
    "command_id", "device_id", "created_at_ms", "expires_at_ms",
    "controller_id", "policy_version", "reason_code", "action_cooling",
    "action_duty_permille",
)


class FakeWriter:
    def __init__(self):
        self.lines = []

    def __call__(self, line: str):
        self.lines.append(line)


class FakePublisher:
    def poll(self, timeout=0):
        return None


def _envelope_json(command_id=UUID_ID, device_id=DEVICE, cooling="OFF",
                   duty=None, reason_code="PREDICTED_CRITICAL") -> bytes:
    created = datetime.now(timezone.utc)
    return json.dumps({
        "schema_version": 1,
        "command_id": command_id,
        "device_id": device_id,
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(seconds=300)).isoformat(),
        "controller_id": "REACTIVE",
        "policy_version": "policy-test-1",
        "reason_code": reason_code,
        "action": {"cooling": cooling, "duty": duty},
    }).encode()


def bridge(device_envelope: bool, auto_sync: bool = False) -> tuple[DownlinkBridge, FakeWriter]:
    writer = FakeWriter()
    return (DownlinkBridge(DEVICE, write_line=writer,
                           publisher=FakePublisher(),
                           device_envelope=device_envelope,
                           auto_sync=auto_sync), writer)


def test_envelope_mode_renders_the_reserved_canonical_form():
    br, writer = bridge(device_envelope=True)
    br.handle_command_message(COMMAND_TOPIC, _envelope_json())
    assert br.stats["commands_forwarded"] == 1
    assert br.stats["commands_refused"] == 0
    assert len(writer.lines) == 1
    line = writer.lines[0]
    assert line.startswith("#CG CMD ")
    record = line[len("#CG CMD "):]
    for field in ENVELOPE_FIELDS:
        assert f" {field}=" in f" {record}"
    assert "command_id=" + UUID_ID in record
    assert "device_id=" + DEVICE in record
    assert record.endswith(" action_cooling=OFF action_duty_permille=0")


def test_actuation_gate_outruns_envelope_rendering():
    br, writer = bridge(device_envelope=True)
    br.handle_command_message(COMMAND_TOPIC,
                              _envelope_json(cooling="ON", duty=0.5))
    assert writer.lines == []
    assert br.stats["commands_refused"] == 1
    assert br.stats["commands_forwarded"] == 0


def test_undeliverable_record_is_refused_side_effect_free():
    """Member C's renderer is the authority over a well-formed record; a
    reason_code with a space cannot become a device token, so the bridge
    refuses without writing anything (never a mangled command)."""
    br, writer = bridge(device_envelope=True)
    br.handle_command_message(COMMAND_TOPIC,
                              _envelope_json(reason_code="CRITICAL CONDITION"))
    assert writer.lines == []
    assert br.stats["commands_refused"] == 1
    assert br.stats["commands_forwarded"] == 0


def test_default_mode_keeps_the_cmdtest_form_and_its_label_grammar():
    br, writer = bridge(device_envelope=False)
    br.handle_command_message(COMMAND_TOPIC, _envelope_json())
    # The canonical UUID does not fit the device's operator label grammar
    # and is refused there rather than mangled - the documented reason the
    # envelope mode exists.
    assert writer.lines == []
    assert br.stats["commands_refused"] == 1
    assert br.stats["commands_forwarded"] == 0


def test_expired_commands_are_refused_before_the_device_in_envelope_mode():
    br, writer = bridge(device_envelope=True)
    created = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = json.dumps({
        "schema_version": 1,
        "command_id": UUID_ID,
        "device_id": DEVICE,
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(minutes=30)).isoformat(),
        "controller_id": "REACTIVE",
        "policy_version": "policy-test-1",
        "reason_code": "PREDICTED_CRITICAL",
        "action": {"cooling": "OFF", "duty": None},
    }).encode()
    br.handle_command_message(COMMAND_TOPIC, payload)
    assert writer.lines == []
    assert br.stats["commands_expired"] == 1
    assert br.stats["commands_forwarded"] == 0


# ---------------------------------------------------------------------------
# Host→device time anchor (challenge echo, verified host clock, staleness)
# ---------------------------------------------------------------------------

CAPABILITY = ("#CG NETCMD status=READY transport=USB_SERIAL_JTAG "
              "line_max=576 record_max=512 challenge=1a2b3c4d").encode()
BOOT_FRAME = b"#CG BOOT boot_id=89acac13"


def test_sync_never_engages_without_a_verified_host_clock(monkeypatch):
    """An offline or wrong-clock host must not anchor device time; the
    device then keeps its delivered fail-closed EPOCH state."""
    br, writer = bridge(device_envelope=True)
    br.note_frame(BOOT_FRAME)
    br.note_frame(CAPABILITY)
    from integration import leader_host_clock

    monkeypatch.setattr(leader_host_clock, "verify_host_clock",
                        lambda now=None: {"verdict": "UNVERIFIED", "source": None,
                                          "reasons": ["time.cloudflare.com: timeout"]})
    assert br.sync_tick() is False
    assert writer.lines == []
    assert br.stats["sync_refused_clock"] == 1


def test_sync_emits_a_challenge_echo_after_clock_verification(monkeypatch):
    br, writer = bridge(device_envelope=True)
    br.note_frame(BOOT_FRAME)
    br.note_frame(CAPABILITY)
    from integration import leader_host_clock

    monkeypatch.setattr(leader_host_clock, "verify_host_clock",
                        lambda now=None: {"verdict": "VERIFIED",
                                          "source": "pool.example",
                                          "skew_s": 0.05,
                                          "tolerance_s": 1.0})
    assert br.sync_tick() is True
    assert len(writer.lines) == 1 and writer.lines[0].startswith("#CG SYNC ")
    line = writer.lines[0]
    assert "challenge=1a2b3c4d" in line      # this boot's live echo
    assert "boot=89acac13" in line           # the id the device itself streams
    assert "host=" in line                   # host epoch ms, timezone-free
    assert br.stats["sync_records_sent"] == 1
    # A second tick within the recheck window reuses the VERIFIED verdict.
    assert br.sync_tick() is True
    assert br.stats["sync_records_sent"] == 2


def test_capability_capture_anchors_on_the_serial_pump(monkeypatch):
    from scripts.leader_serial_gateway import pump_leader
    from threading import Event
    br, writer = bridge(device_envelope=True, auto_sync=True)
    from integration import leader_host_clock

    monkeypatch.setattr(leader_host_clock, "verify_host_clock",
                        lambda now=None: {"verdict": "VERIFIED",
                                          "source": "pool.example",
                                          "skew_s": 0.05,
                                          "tolerance_s": 1.0})
    stop = Event()

    class Stream:
        def read(self, size):
            stop.set()
            return b"#CG BOOT boot_id=89acac13\n" + CAPABILITY + b"\n"

    class Publisher:
        def poll(self):
            pass

        def publish(self, topic, payload):
            pass

    pump_leader(Stream(), Publisher(), topic=f"coldguard/{DEVICE}/telemetry", stop=stop, bridge=br)
    assert br.stats["sync_records_sent"] == 1
    assert "challenge=1a2b3c4d" in writer.lines[0]


def test_new_boot_century_badging_invalidate_the_old_capability():
    """ESP32 reboot: the boot id changes, the old challenge dies with it,
    and the bridge forgets the capability it cannot trust to still be live."""
    br, writer = bridge(device_envelope=True)
    br.note_frame(b"#CG BOOT boot_id=89acac13")
    br.note_frame(CAPABILITY)
    rebooted = b"#CG BOOT boot_id=42698010"
    br.note_frame(rebooted)
    # No verification mock: a tick must NOT write a record anchored on a
    # challenge from a boot that no longer exists - sync stays unwritten
    # until the new boot advertises its own capability.
    assert br.sync_tick() is False
    assert writer.lines == []


def test_out_of_tolerance_host_clock_never_anchors(monkeypatch):
    br, writer = bridge(device_envelope=True)
    br.note_frame(BOOT_FRAME)
    br.note_frame(CAPABILITY)
    from integration import leader_host_clock

    monkeypatch.setattr(leader_host_clock, "verify_host_clock",
                        lambda now=None: {"verdict": "OUT_OF_TOLERANCE",
                                          "source": "pool.example",
                                          "skew_s": 71.5, "tolerance_s": 1.0,
                                          "system_utc": datetime.now(timezone.utc)})
    assert br.sync_tick() is False
    assert writer.lines == []


def test_timezone_difference_does_not_change_the_protocol_clock(monkeypatch):
    """A host in a non-UTC local timezone with a correct UTC produces the
    same anchored time: the record carries UTC epoch ms, never an offset."""
    br, _ = bridge(device_envelope=True)
    br.note_frame(BOOT_FRAME)
    br.note_frame(CAPABILITY)
    monkeypatch.setenv("TZ", "Asia/Bangkok")

    from integration import leader_downlink, leader_host_clock

    frozen = datetime(2026, 11, 12, 17, 0, 0, tzinfo=timezone.utc)

    class FakeUtcNow:
        @staticmethod
        def now(_tz=None):
            return frozen

    monkeypatch.setattr(leader_downlink, "datetime", FakeUtcNow)
    monkeypatch.setattr(leader_host_clock, "verify_host_clock",
                        lambda now=None: {"verdict": "VERIFIED",
                                          "source": "pool.example",
                                          "skew_s": 0.0, "tolerance_s": 1.0})

    class RecordingWriter:
        def __init__(self):
            self.lines = []
        def __call__(self, line):
            self.lines.append(line)

    writer2 = RecordingWriter()
    br._write_line = writer2
    assert br.sync_tick() is True
    host_token = next(t for t in writer2.lines[0].split() if t.startswith("host="))
    # The epoch ms of 2026-11-12T17:00:00Z exactly - the same number any
    # correct host prints in any timezone (tz-independence contract).
    assert host_token == "host=" + str(int(frozen.timestamp() * 1000))


def test_clock_check_defaults_on_even_when_the_flag_is_accepted():
    """The bridge requires a verified host clock unless explicitly told a
    host stands without the check; the default is verification."""
    br, _ = bridge(device_envelope=True)
    assert br.require_verified_clock is True


def test_host_clock_probe_builds_and_parses_ntp_frames():
    """The NTP exchange against a fake local server: request shape, the
    client-mode byte, and a parsed epoch that tracks the answering clock -
    offline-safe."""
    import socket
    import struct as _struct
    import threading

    from integration import leader_host_clock

    received = []
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(5.0)
    port = server.getsockname()[1]

    def serve() -> None:
        try:
            data, addr = server.recvfrom(1024)
            received.append((len(data), data[0]))
            now = datetime.now(timezone.utc).timestamp() + 2208988800
            out = bytearray(48)
            out[0] = 0x24  # LI=0, VN=4, Mode=4 (server)
            _struct.pack_into("!II", out, 40, int(now), 0)
            server.sendto(bytes(out), addr)
        except OSError:
            received.append((0, 0))
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    epoch = leader_host_clock._probe("127.0.0.1", timeout=3.0, port=port)
    thread.join(timeout=3.0)
    assert received and received[0][0] == 48
    assert received[0][1] == 0x23  # the request claims client mode, version 4
    assert abs(epoch - datetime.now(timezone.utc).timestamp()) < 3.0


def test_host_clock_probe_rejects_an_answer_of_wrong_shape():
    import socket
    import threading

    from integration import leader_host_clock

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(5.0)
    port = server.getsockname()[1]

    def serve() -> None:
        try:
            data, addr = server.recvfrom(1024)
            server.sendto(b"\x00" * 10, addr)  # short garbage: not an answer
        finally:
            server.close()

    threading.Thread(target=serve, daemon=True).start()
    try:
        leader_host_clock._probe("127.0.0.1", timeout=1.0, port=port)
        raise AssertionError("short garbage must be rejected")
    except OSError:
        pass


def test_verify_host_clock_reports_unverified_when_every_source_fails(monkeypatch):
    from integration import leader_host_clock

    def boom(host):
        raise OSError(f"{host} unreachable")

    monkeypatch.setattr(leader_host_clock, "_probe", boom)
    monkeypatch.setenv("COLDGUARD_NTP_HOSTS", "a.example,b.example")
    verdict = leader_host_clock.verify_host_clock()
    assert verdict["verdict"] == "UNVERIFIED"
    assert len(verdict["reasons"]) == 2
    assert verdict["system_utc"].tzinfo is not None
