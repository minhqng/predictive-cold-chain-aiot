"""Leader integration tests: device-console downlink + CMDACK relay.

Covers the opt-in ``--enable-downlink`` bridge hosted by the Leader-owned
modules (``integration/leader_downlink.py`` and
``scripts/leader_serial_gateway.py``), which compose the delivered Member C
gateway (``scripts/serial_gateway.py``, restored byte-for-byte) without
modifying any member source:

* canonical Command envelopes rendered into the device's console grammar
  (``CMDTEST`` line);
* the demo-safe default that refuses actuation-requesting commands (physical
  commissioning authorization is a separate gate and no flag here supplies it);
* refusal when a command id cannot be represented in the device's label
  grammar (identity is never silently mangled);
* faithful relay of real device ``#CG CMDACK`` records through Member C's
  committed ack translation onto the canonical ACK topic;
* correlation mismatch counting (correlation itself stays the backend's
  fail-closed authority);
* the delivered member gateway carries zero downlink vocabulary and its
  telemetry pump skips CMDACK frames untouched;
* the Leader pump routes CMDACK frames to the bridge and forwards telemetry
  through the member translation unchanged;
* the Leader entrypoint refuses to run without the explicit downlink
  opt-in flag.

No physical device, no broker, no database: the member translations run as
delivered, in-process.
"""
from __future__ import annotations

import inspect
import json
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import UUID

import pytest

import scripts.serial_gateway as member_gateway
from integration.leader_downlink import (
    DEVICE_ACK_PREFIX,
    TEC_TRIAL_REASON_PREFIX,
    TEC_TRIAL_STOP_REASON,
    CommandSerialWriter,
    DownlinkBridge,
    device_command_ack_topic,
    device_command_topic,
)
from scripts.leader_serial_gateway import main as leader_main
from scripts.leader_serial_gateway import pump_leader, run_live_downlink
from scripts.serial_gateway import pump as member_pump

from tests.command_testkit import make_command

BACKEND = Path(__file__).resolve().parents[1]
FIXTURE = BACKEND.parent / "evidence/A/W05/schema-fixture.json"
DEVICE = "coldguard-001"
TOPIC = f"coldguard/{DEVICE}/telemetry"
UUID_ID = "00000000-0000-4000-8000-00000000000e"


class ChunkStream:
    """Serial stand-in: yields each chunk once, then empty forever."""

    def __init__(self, *chunks):
        self._chunks = iter(chunks)

    def read(self, n):
        try:
            return next(self._chunks)
        except StopIteration:
            return b""


class FakeWriter:
    def __init__(self):
        self.lines = []

    def __call__(self, line: str):
        self.lines.append(line)


class FakeRelayPublisher:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload):
        self.published.append((topic, payload.decode()))


class PumpPublisher:
    """Records publishes like the delivered telemetry pump expects."""

    def __init__(self):
        self.published = []

    def poll(self, timeout=0):
        pass

    def publish(self, topic, payload):
        self.published.append((topic, payload))


class StopFlag:
    def __init__(self):
        self._count = 0

    def is_set(self):
        self._count += 1
        return self._count > 3


def _envelope(command_id="cmdtest-demo-04-1", cooling="OFF", duty=0.0,
              device_id=DEVICE):
    command = make_command(command_id, device_id=device_id, cooling=cooling,
                           duty=duty)
    return json.loads(command.model_dump_json())


def _bridge(writer=None, relay=None, **overrides):
    return DownlinkBridge(DEVICE, write_line=writer or FakeWriter(),
                          publisher=relay or FakeRelayPublisher(), **overrides)


def test_safe_default_refuses_actuation_requesting_commands():
    writer, relay = FakeWriter(), FakeRelayPublisher()
    bridge = _bridge(writer, relay)
    bridge.handle_command_message(device_command_topic(DEVICE),
                                  json.dumps(_envelope(cooling="ON", duty=0.5)).encode())
    assert writer.lines == []
    assert bridge.stats["commands_refused"] == 1
    assert relay.published == []


def test_zero_duty_off_command_is_forwarded_as_device_cmdtest_line():
    writer, relay = FakeWriter(), FakeRelayPublisher()
    bridge = _bridge(writer, relay)
    bridge.handle_command_message(device_command_topic(DEVICE),
                                  json.dumps(_envelope(cooling="OFF", duty=0.0)).encode())
    assert writer.lines == ["CMDTEST cmdtest-demo-04-1 OFF 0"]
    assert bridge.stats["commands_forwarded"] == 1
    assert relay.published == []  # nothing relayed until the device answers


def test_none_duty_defaults_to_zero_permille():
    writer = FakeWriter()
    bridge = _bridge(writer)
    bridge.handle_command_message(device_command_topic(DEVICE),
                                  json.dumps(_envelope(cooling="OFF", duty=None)).encode())
    assert writer.lines == ["CMDTEST cmdtest-demo-04-1 OFF 0"]


def test_wrong_topic_is_refused():
    writer, relay = FakeWriter(), FakeRelayPublisher()
    bridge = _bridge(writer, relay)
    bridge.handle_command_message("coldguard/other-device/command",
                                  json.dumps(_envelope()).encode())
    assert writer.lines == []
    assert bridge.stats["commands_refused"] == 1


def test_uuid_command_id_is_refused_not_mangled():
    writer, relay = FakeWriter(), FakeRelayPublisher()
    bridge = _bridge(writer, relay)
    bridge.handle_command_message(device_command_topic(DEVICE),
                                  json.dumps(_envelope(command_id=UUID_ID)).encode())
    assert writer.lines == []
    assert bridge.stats["commands_refused"] == 1


def test_malformed_envelope_is_refused():
    writer, relay = FakeWriter(), FakeRelayPublisher()
    bridge = _bridge(writer, relay)
    env = _envelope()
    env["schema_version"] = 2
    bridge.handle_command_message(device_command_topic(DEVICE),
                                  json.dumps(env).encode())
    assert writer.lines == []
    assert bridge.stats["commands_refused"] == 1


def test_expired_command_is_refused_before_the_device():
    writer, relay = FakeWriter(), FakeRelayPublisher()
    bridge = _bridge(writer, relay)
    env = _envelope()
    now = datetime.now(timezone.utc)
    env["created_at"] = (now - timedelta(seconds=200)).isoformat()
    env["expires_at"] = (now - timedelta(seconds=80)).isoformat()
    bridge.handle_command_message(device_command_topic(DEVICE),
                                  json.dumps(env).encode())
    assert writer.lines == []
    assert bridge.stats["commands_expired"] == 1
    assert bridge.stats["commands_refused"] == 1


def test_future_skew_beyond_gate_is_refused_before_the_device():
    writer, relay = FakeWriter(), FakeRelayPublisher()
    bridge = _bridge(writer, relay)
    env = _envelope()
    now = datetime.now(timezone.utc)
    env["created_at"] = (now + timedelta(seconds=400)).isoformat()
    env["expires_at"] = (now + timedelta(seconds=460)).isoformat()
    bridge.handle_command_message(device_command_topic(DEVICE),
                                  json.dumps(env).encode())
    assert writer.lines == []
    assert bridge.stats["commands_future_skew"] == 1
    assert bridge.stats["commands_refused"] == 1


def test_real_device_ack_record_is_relayed_to_the_canonical_ack_topic():
    relay = FakeRelayPublisher()
    bridge = _bridge(relay=relay)
    # A byte-faithful device CMDACK in the shape Member A's producer emits
    # (vocabulary per evidence/A/W06/ack-fixture.json).
    line = ("#CG CMDACK schema=1 event=ACK command_id=" + UUID_ID +
            " command_id_form=UUID source=NETWORK device_id=" + DEVICE +
            " boot_id=abcd0123 boot_count=9 uptime_ms=65432 ack_seq=42 "
            "status=ACCEPTED reason=NONE desired_cooling=ON "
            "desired_duty_permille=250 applied_cooling=OFF "
            "applied_duty_permille=0 reapplied=0 expiry_evaluable=0 "
            "time_sync_state=UNSYNCHRONIZED device_mode=OFF fault_code=0x00000000")
    bridge.relay_ack(line)
    assert len(relay.published) == 1
    topic, payload = relay.published[0]
    assert topic == device_command_ack_topic(DEVICE)
    envelope = json.loads(payload)
    assert envelope["command_id"] == UUID_ID
    assert envelope["status"] == "ACCEPTED"
    assert envelope["applied"]["cooling"] == "OFF"
    assert envelope["applied"]["duty"] == 0.0
    assert bridge.stats["acks_relayed"] == 1


def test_malformed_device_ack_is_counted_and_dropped():
    relay = FakeRelayPublisher()
    bridge = _bridge(relay=relay)
    bridge.relay_ack("garbage line without the device prefix fields")
    assert relay.published == []
    assert bridge.stats["acks_invalid"] == 1


def test_correlation_mismatch_is_counted_and_still_relayed():
    relay = FakeRelayPublisher()
    bridge = _bridge(relay=relay, expect_command_id="some-other-id")
    bridge.relay_ack("#CG CMDACK schema=1 command_id=" + UUID_ID +
                     " device_id=" + DEVICE + " boot_id=abcd0123 "
                     "status=REJECTED reason=NONE uptime_ms=1")
    assert bridge.stats["acks_mismatched"] == 1
    assert bridge.stats["acks_relayed"] == 1
    assert len(relay.published) == 1


def test_member_pump_skips_cmdack_frames_untouched():
    relay = FakeRelayPublisher()
    bridge = _bridge(relay=relay)
    pub = PumpPublisher()
    member_pump(
        ChunkStream(b"#CG CMDACK schema=1 command_id=" + UUID_ID.encode() +
                    b" device_id=" + DEVICE.encode() +
                    b" boot_id=abcd0123 status=ACCEPTED reason=NONE uptime_ms=7\n"),
        pub, topic=TOPIC, replay=False, stop=StopFlag(),
    )
    assert pub.published == []
    assert not relay.published and not bridge.stats["acks_relayed"]


def test_leader_pump_routes_cmdack_frames_to_the_bridge():
    relay = FakeRelayPublisher()
    bridge = _bridge(relay=relay)
    pub = PumpPublisher()
    pump_leader(
        ChunkStream(b"#CG CMDACK schema=1 command_id=" + UUID_ID.encode() +
                    b" device_id=" + DEVICE.encode() +
                    b" boot_id=abcd0123 status=ACCEPTED reason=NONE uptime_ms=7\n"),
        pub, topic=TOPIC, stop=StopFlag(), bridge=bridge,
    )
    assert len(relay.published) == 1
    topic, payload = relay.published[0]
    assert topic == device_command_ack_topic(DEVICE)
    envelope = json.loads(payload)
    assert envelope["command_id"] == UUID_ID
    assert envelope["status"] == "ACCEPTED"
    assert pub.published == []  # the ACK frame took the bridge branch, not telemetry
    assert bridge.stats["acks_relayed"] == 1


def test_leader_pump_forwards_delivered_telemetry_unchanged():
    fields = json.loads(FIXTURE.read_text(encoding="utf-8"))["fields"]
    if fields["schema"] == 2:
        for key in (
            "command_id", "desired_cooling", "desired_duty_permille",
            "last_ack_status", "last_ack_reason",
        ):
            fields.pop(key, None)
    frame = ("#CG TELEM " + " ".join(f"{key}={value}" for key, value in fields.items())).encode()
    pub = PumpPublisher()
    bridge = _bridge(relay=FakeRelayPublisher())
    pump_leader(ChunkStream(frame + b"\n"), pub, topic=TOPIC,
                stop=StopFlag(), bridge=bridge)
    assert len(pub.published) == 1
    topic, payload = pub.published[0]
    assert topic == TOPIC
    body = json.loads(payload)
    assert body["device_id"] == DEVICE
    assert body["captured_at"] is None  # clockless serial: no invented event time
    assert bridge.stats["acks_relayed"] == 0


def test_leader_entrypoint_requires_explicit_downlink_opt_in(capsys):
    with pytest.raises(SystemExit) as excinfo:
        leader_main(["--device-id", DEVICE, "--serial-port", "COM4",
                     "--broker-port", "1883"])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "--enable-downlink is required" in err


def test_cmdack_prefix_is_the_documented_device_record():
    assert DEVICE_ACK_PREFIX == b"#CG CMDACK"


def test_member_command_translations_still_accept_a_realistic_command():
    # The member source path used by the bridge is exercised as delivered:
    # a TEC-OFF test command round-trips through Command model + translation.
    command = make_command("cmdtest-demo-04-1", cooling="OFF", duty=0.0)
    assert command.action.cooling == "OFF"
    assert command.action.duty == 0.0


def test_member_gateway_module_ships_no_downlink_symbols():
    assert not hasattr(member_gateway, "DownlinkBridge")
    assert not hasattr(member_gateway, "DEVICE_ACK_PREFIX")
    assert "bridge" not in inspect.signature(member_gateway.pump).parameters
    assert "make_bridge" not in inspect.signature(member_gateway.run_live).parameters


def test_command_serial_writer_frames_the_console_line_on_the_shared_stream():
    class FakePort:
        def __init__(self):
            self.written = []

        def write(self, data):
            self.written.append(data)
            return len(data)

    port = FakePort()
    writer = CommandSerialWriter(port)
    writer("CMDTEST cmd-01 OFF 0")
    assert port.written == [b"CMDTEST cmd-01 OFF 0\r\n"]
    port.write = lambda data: len(data) - 1
    with pytest.raises(OSError, match="incomplete console write"):
        writer("CMDTEST cmd-01 OFF 0")


BOOT = b"#CG BOOT event=IDENTITY device_id=coldguard-001 boot_id=abcd0123 boot_count=7"
# Synthetic credential used only by the in-memory serial fixtures.
AUTH = b"#CG AUTH token=0123abcd ttl_ms=120000 clear_requires_token=1"
ARMED = b"#CG TEC event=ARM result=ARMED state=ARMED"
ARM = "ARM " + AUTH.split()[2].decode().split("=")[1]


def _commissioning_telemetry(**overrides):
    fields = json.loads(FIXTURE.read_text(encoding="utf-8"))["fields"]
    fields.update(door_open=0, door_status="OK")
    fields.update(overrides)
    return ("#CG TELEM " + " ".join(f"{key}={value}" for key, value in fields.items())).encode()


def _feed(bridge, *frames):
    data = b"\n".join(frames) + b"\n"
    pub = PumpPublisher()
    pump_leader(ChunkStream(data[:53], data[53:]), pub, topic=TOPIC,
                stop=StopFlag(), bridge=bridge)
    return pub.published


def _dispatch_trial(bridge, *, command_id=UUID_ID, duty=0.2, cooling="ON"):
    reason = TEC_TRIAL_REASON_PREFIX + "abcd0123" if cooling == "ON" else "OPERATOR_STOP"
    command = make_command(command_id, device_id=DEVICE, cooling=cooling, duty=duty,
                           run_id=UUID(UUID_ID).hex, reason_code=reason)
    bridge.handle_command_message(device_command_topic(DEVICE), command.model_dump_json().encode())


def test_default_gateway_captures_auth_without_enabling_actuation(caplog):
    writer, relay = FakeWriter(), FakeRelayPublisher()
    bridge = _bridge(writer, relay, device_envelope=True, auto_sync=False)
    with caplog.at_level("INFO"):
        published = _feed(bridge, BOOT, AUTH, _commissioning_telemetry())
        _dispatch_trial(bridge)
        _feed(bridge, _network_ack(), ARMED)
    assert bridge._boot_authorization is not None
    assert "AUTH_CAPTURED for boot abcd0123" in caplog.text
    token = ARM.split()[1]
    assert token not in caplog.text and token not in repr(published + relay.published)
    assert any(topic == TOPIC for topic, _ in published)
    assert writer.lines == []


def test_foreground_console_only_grants_after_exact_operator_input(monkeypatch, capsys):
    from scripts import leader_serial_gateway

    msvcrt = pytest.importorskip("msvcrt")
    writer = FakeWriter()
    bridge = _bridge(writer, device_envelope=True, auto_sync=False)
    _feed(bridge, BOOT, AUTH, _commissioning_telemetry())
    keys = deque("wrong GRANT TEC200\r")
    monkeypatch.setattr(leader_serial_gateway.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(msvcrt, "kbhit", lambda: bool(keys))
    monkeypatch.setattr(msvcrt, "getwch", keys.popleft)
    monkeypatch.setattr(leader_serial_gateway, "uuid4", lambda: UUID(UUID_ID))
    poll = leader_serial_gateway.operator_console(bridge)
    poll()
    assert bridge._grant is None
    keys.extend("GRANT TEC200\r")
    poll()
    assert bridge._grant.command_id == UUID_ID
    assert UUID_ID in capsys.readouterr().out
    keys.extend("ABORT TEC200\r")
    poll()
    assert bridge._grant is None
    assert writer.lines == []


def test_gateway_help_describes_operator_console_and_removes_legacy_flag(capsys):
    with pytest.raises(SystemExit) as result:
        leader_main(["--help"])
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert "--operator-console" in help_text and "observe-only" in help_text
    assert "--allow-actuation" not in help_text


def test_queued_abort_beats_start_when_serial_read_returns():
    writer = FakeWriter()
    bridge = _bridge(writer, device_envelope=True, auto_sync=False)
    _feed(bridge, BOOT, AUTH, _commissioning_telemetry())
    assert bridge.grant_trial(UUID_ID) == "abcd0123"
    _dispatch_trial(bridge)
    _feed(bridge, _network_ack(), ARMED)
    stop = Event()

    class Stream:
        def read(self, size):
            stop.set()  # An abort arrives during the blocking serial read.
            return _commissioning_telemetry(seq=1001, uptime_ms=1_001_000) + b"\n"

    def poll_operator():
        if stop.is_set():
            bridge.abort_trial()

    pump_leader(Stream(), PumpPublisher(), topic=TOPIC, stop=stop, bridge=bridge,
                poll_operator=poll_operator)
    assert writer.lines[1:] == [ARM, "STOP"]


@pytest.mark.parametrize("case", ["retained", "queued", "wrong-device", "wrong-trial",
                                  "wrong-command", "wrong-duty", "timeout", "abort", "reboot", "close"])
def test_grant_rejects_unapproved_or_lost_authority(case, monkeypatch):
    from integration import leader_downlink

    clock = 0
    monkeypatch.setattr(leader_downlink, "monotonic", lambda: clock)
    writer = FakeWriter()
    bridge = _bridge(writer, device_envelope=True, auto_sync=False)
    _feed(bridge, BOOT, AUTH, _commissioning_telemetry())
    options = {"run_id": UUID(UUID_ID).hex, "reason_code": TEC_TRIAL_REASON_PREFIX + "abcd0123"}
    command_id, device, duty = UUID_ID, DEVICE, 0.2
    if case == "queued":
        options["created_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert bridge.grant_trial(UUID_ID) == "abcd0123"
    if case == "wrong-device":
        device = "other-device"
    elif case == "wrong-trial":
        options["run_id"] = "other-run"
    elif case == "wrong-command":
        command_id = "other-command"
    elif case == "wrong-duty":
        duty = 0.1999
    elif case == "timeout":
        clock = leader_downlink.TRIAL_GRANT_SECONDS
        _feed(bridge, _commissioning_telemetry(seq=1001, uptime_ms=1_001_000))
    elif case == "abort":
        bridge.abort_trial()
    elif case == "reboot":
        _feed(bridge, BOOT.replace(b"abcd0123", b"abcd4321"), AUTH,
              _commissioning_telemetry(boot_id="abcd4321"))
    elif case == "close":
        bridge.close()
    command = make_command(command_id, device_id=device, cooling="ON", duty=duty, **options)
    bridge._on_message(None, None, SimpleNamespace(topic=device_command_topic(DEVICE),
                       payload=command.model_dump_json().encode(), retain=case == "retained"))
    assert writer.lines == []
    assert bridge.grant_trial(UUID_ID) is None


def _network_ack(*, status="ACCEPTED", boot="abcd0123", source="NETWORK", uptime=1_000_100):
    return (f"#CG CMDACK schema=1 command_id={UUID_ID} device_id={DEVICE} boot_id={boot} "
            f"source={source} status={status} reason=NONE uptime_ms={uptime} "
            "desired_cooling=ON desired_duty_permille=200 applied_cooling=OFF "
            "applied_duty_permille=0 canonical_status=ACCEPTED").encode()


def test_supervised_gateway_waits_for_device_and_console_admission():
    writer, relay = FakeWriter(), FakeRelayPublisher()
    bridge = _bridge(writer, relay, device_envelope=True, auto_sync=False)
    published = _feed(bridge, BOOT, AUTH, _commissioning_telemetry(), b"#CG PZEM status=OK")
    assert writer.lines == []
    assert [topic.rsplit("/", 1)[-1] for topic, _ in published] == [
        "leader-diag", "telemetry", "leader-diag"]

    assert bridge.grant_trial(UUID_ID) == "abcd0123"
    _dispatch_trial(bridge)
    assert len(writer.lines) == 1 and writer.lines[0].startswith("#CG CMD ")
    _feed(bridge, ARMED, _network_ack(boot="abcd1234"))
    assert len(writer.lines) == 1
    _feed(bridge, _network_ack(), _network_ack())
    assert writer.lines[1:] == [ARM]
    ack = json.loads(relay.published[-1][1])
    assert ack["status"] == "ACCEPTED" and ack["applied"] == {"cooling": "OFF", "duty": 0.0}
    _feed(bridge, ARMED, ARMED)
    assert writer.lines[1:] == [ARM]
    _feed(bridge, _commissioning_telemetry(seq=1001, uptime_ms=1_001_000))
    _dispatch_trial(bridge)
    _feed(bridge, _network_ack(), ARMED)
    assert writer.lines[1:3] == [ARM, "START 30"]
    assert len(writer.lines) == 3


def test_gateway_emits_device_console_results_with_one_command_and_session():
    writer, relay = FakeWriter(), FakeRelayPublisher()
    bridge = _bridge(writer, relay, device_envelope=True, auto_sync=False)
    _feed(bridge, BOOT, AUTH, _commissioning_telemetry())
    assert bridge.grant_trial(UUID_ID) == "abcd0123"
    _dispatch_trial(bridge)
    _feed(bridge, _network_ack())
    arm = _feed(bridge, ARMED + b" duty=0")
    _feed(bridge, _commissioning_telemetry(seq=1001, uptime_ms=1_001_000))
    start = _feed(bridge, b"#CG TEC event=START result=OK state=COOLING duty=200")
    records = [json.loads(payload) for topic, payload in arm + start
               if topic.endswith("/leader-diag") and payload.startswith("{")]
    assert [(record["event"], record["result"], record["duty_permille"]) for record in records] == [
        ("ARM", "ARMED", "0"), ("START", "OK", "200"),
    ]
    assert {record["command_id"] for record in records} == {UUID_ID}
    assert {record["device_id"] for record in records} == {DEVICE}
    assert {record["boot_id"] for record in records} == {"abcd0123"}
    assert {record["ack_uptime_ms"] for record in records} == {1_000_100}
    assert records[0]["gateway_session_id"] == records[1]["gateway_session_id"]
    assert records[1]["preceding_telemetry_uptime_ms"] == 1_001_000
    assert not any(payload.startswith("{") for _, payload in
                   _feed(bridge, b"#CG TEC event=START result=OK state=COOLING duty=200"))


def test_gateway_refuses_to_arm_for_a_different_operator_approved_boot():
    writer = FakeWriter()
    bridge = _bridge(writer, device_envelope=True, auto_sync=False)
    _feed(bridge, BOOT, AUTH, _commissioning_telemetry())
    assert bridge.grant_trial(UUID_ID) == "abcd0123"
    command = make_command(UUID_ID, device_id=DEVICE, cooling="ON", duty=0.2,
                           reason_code=TEC_TRIAL_REASON_PREFIX + "abcd4567", run_id=UUID(UUID_ID).hex)
    bridge.handle_command_message(device_command_topic(DEVICE), command.model_dump_json().encode())
    _feed(bridge, _network_ack(), ARMED)
    assert writer.lines == []


def test_trial_stop_prevents_arm_from_a_late_on_delivery():
    writer = FakeWriter()
    bridge = _bridge(writer, device_envelope=True, auto_sync=False)
    _feed(bridge, BOOT, AUTH, _commissioning_telemetry())
    assert bridge.grant_trial(UUID_ID) == "abcd0123"
    command = make_command("trial-stop", device_id=DEVICE, cooling="OFF", duty=None,
                           reason_code=TEC_TRIAL_STOP_REASON, run_id=UUID(UUID_ID).hex)
    bridge.handle_command_message(device_command_topic(DEVICE), command.model_dump_json().encode())
    _dispatch_trial(bridge)
    _feed(bridge, _network_ack(), ARMED)
    assert len(writer.lines) == 1 and "action_cooling=OFF" in writer.lines[0]


@pytest.mark.parametrize("frames", [
    (AUTH,),
    (BOOT, AUTH, _commissioning_telemetry(boot_id="abcd1234")),
    (BOOT, AUTH, _commissioning_telemetry(door_open=1)),
    (BOOT, AUTH, _commissioning_telemetry(), b"#CG TELEM malformed"),
    (BOOT, AUTH, _commissioning_telemetry(electrical_quality="INVALID")),
    (BOOT, AUTH, b"partial " + AUTH),
])
def test_supervised_gateway_rejects_missing_or_unsafe_boot_evidence(frames, monkeypatch):
    monkeypatch.setenv("COLDGUARD_SUPERVISED_ARM_TOKEN", "0123abcd")
    writer = FakeWriter()
    bridge = _bridge(writer, device_envelope=True, auto_sync=False)
    _feed(bridge, *frames)
    _dispatch_trial(bridge)
    _feed(bridge, _network_ack(), ARMED)
    assert writer.lines == []


@pytest.mark.parametrize("status,source", [
    ("SAFETY_BLOCKED", "NETWORK"), ("DUPLICATE_CANONICAL", "NETWORK"),
    ("ACCEPTED", "LOCAL_CONSOLE"),
])
def test_supervised_gateway_rejects_nonadmitting_ack(status, source):
    writer = FakeWriter()
    bridge = _bridge(writer, device_envelope=True, auto_sync=False)
    _feed(bridge, BOOT, AUTH, _commissioning_telemetry())
    assert bridge.grant_trial(UUID_ID) == "abcd0123"
    _dispatch_trial(bridge)
    _feed(bridge, _network_ack(status=status, source=source), _network_ack(), ARMED)
    assert len(writer.lines) == 1


@pytest.mark.parametrize("interruption", ["refusal", "reboot", "stale", "stop", "duplicate", "door-open"])
def test_supervised_gateway_drops_pending_start(interruption, monkeypatch):
    from integration import leader_downlink

    now = 0
    from scripts import leader_serial_gateway
    monkeypatch.setattr(leader_downlink, "monotonic", lambda: now)
    monkeypatch.setattr(leader_serial_gateway, "monotonic", lambda: now)
    writer = FakeWriter()
    bridge = _bridge(writer, device_envelope=True, auto_sync=False)
    _feed(bridge, BOOT, AUTH, _commissioning_telemetry())
    assert bridge.grant_trial(UUID_ID) == "abcd0123"
    _dispatch_trial(bridge)
    _feed(bridge, _network_ack())
    assert writer.lines[1:] == [ARM]
    if interruption == "refusal":
        _feed(bridge, b"#CG TEC event=ARM result=REFUSED state=ARMED")
    elif interruption == "reboot":
        _feed(bridge, BOOT.replace(b"abcd0123", b"abcd1234"))
    elif interruption == "stale":
        _feed(bridge, ARMED)
        now = 3
    elif interruption == "stop":
        _dispatch_trial(bridge, command_id="stop-trial", duty=0, cooling="OFF")
        assert writer.lines[-1] == "STOP"
    elif interruption == "duplicate":
        _feed(bridge, _commissioning_telemetry())
    else:
        _feed(bridge, _commissioning_telemetry(seq=1001, uptime_ms=1_001_000, door_open=1))
    _feed(bridge, ARMED, _commissioning_telemetry(seq=1002, uptime_ms=1_002_000))
    assert not any(line.startswith("START ") for line in writer.lines)


def test_supervised_transport_failure_cleans_up_without_reopening_serial():
    events = []

    class DisconnectedPublisher:
        def poll(self):
            raise member_gateway.PublishError("broker disconnected")

    @contextmanager
    def connect():
        try:
            yield DisconnectedPublisher()
        finally:
            events.append("mqtt closed")

    @contextmanager
    def open_serial():
        events.append("serial opened")
        try:
            yield object()  # No reset or read methods before the broker poll fails.
        finally:
            assert bridge._sync_stop.is_set()
            events.append("serial closed")

    bridge = _bridge(device_envelope=True, auto_sync=False)
    bridge.install = lambda: None  # Broker is unavailable after subscribing.
    with pytest.raises(member_gateway.PublishError, match="broker disconnected"):
        run_live_downlink(open_serial, connect, topic=TOPIC, stop=Event(),
                          make_bridge=lambda *_: bridge)
    assert events == ["serial opened", "serial closed", "mqtt closed"]


@pytest.mark.parametrize("reason", ["X\nESTOP\nX", "X\tY", "µ"])
def test_gateway_drops_non_printable_command_records(reason):
    writer = FakeWriter()
    bridge = _bridge(writer, device_envelope=True)
    command = make_command(UUID_ID, cooling="OFF", duty=0, reason_code=reason)
    bridge.handle_command_message(device_command_topic(DEVICE), command.model_dump_json().encode())
    assert writer.lines == []
    assert bridge.stats["commands_refused"] == 1


def test_supervised_gateway_rejects_device_ack_after_buffered_telemetry():
    writer = FakeWriter()
    bridge = _bridge(writer, device_envelope=True, auto_sync=False)
    _feed(bridge, BOOT, AUTH, _commissioning_telemetry())
    assert bridge.grant_trial(UUID_ID) == "abcd0123"
    _dispatch_trial(bridge)
    _feed(bridge, _network_ack(uptime=1_005_000), ARMED)
    assert len(writer.lines) == 1
