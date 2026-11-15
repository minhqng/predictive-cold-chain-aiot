"""Leader downlink adapter: the device-directed command bridge, external to
the delivered member code.

Leader-owned module. The member-delivered gateway
(``backend/scripts/serial_gateway.py``) keeps its delivered source unchanged;
this module composes the opt-in downlink on top of the member sessions:

* it subscribes the canonical Member C Command topic
  (``coldguard/<device>/command``) on the device principal's MQTT session;
* it renders each well-formed Member C command envelope into the console
  grammar the delivered firmware parser accepts (``CMDTEST``);
* it relays the device's real ``#CG CMDACK`` records back onto the canonical
  acknowledge topic through Member C's committed ack translation.

Contract preserved: the bridge adds no policy vocabulary, never mangles a
command identity that does not fit the device label grammar, and leaves the
delivered members' own validation (provenance firewall, clock-less expiry
rule, compiled-out output stage) as the only admission authority over the
wire bytes. The telemetry-only gateway path is unchanged when the bridge is
not installed.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Event, Lock
from time import monotonic
from uuid import UUID, uuid4

import paho.mqtt.client as mqtt

from scripts.serial_gateway import NETWORK_TIMEOUT, PublishError

log = logging.getLogger(__name__)

DEVICE_ACK_PREFIX = b"#CG CMDACK"
AUTH_PREFIX = b"#CG AUTH"
NETCMD_PREFIX = b"#CG NETCMD"
BOOT_ID_RE = re.compile(r"[0-9a-f]{8}")
SUPERVISED_DUTY_PERMILLE = 200  # START uses the image's fixed commissioning duty.
SUPERVISED_RUN_SECONDS = 30
TEC_TRIAL_REASON_PREFIX = "TEC200_BOOT_"  # Firmware reason_code allows 23 bytes.
TEC_TRIAL_STOP_REASON = "TEC200_STOP"
TELEMETRY_MAX_AGE_S = 3  # Three periods of the device's 1 Hz telemetry.
TRIAL_GRANT_SECONDS = 60  # Time for the operator to submit the one trial command.
# The device's operator-console grammar (firmware/main/cg_tec_command.c):
# CMDTEST <label> <ON|OFF> <duty 0..1000>. The label must fit the device's
# own token form: [A-Za-z0-9_-]{1,32} (cg_tec_command.c label_is_valid and
# CG_TEC_CMD_ARG_MAX=33). A canonical id that cannot be represented in that
# form is refused, never silently mangled.
DEVICE_LABEL_RE = re.compile(r"\A[A-Za-z0-9_-]{1,32}\Z")
# Period between re-anchoring records while a session lives. The device
# drops its anchor (fail-closed) after CG_LEADER_SYNC_STALE_MS without one.
SYNC_PERIOD_S = float(os.environ.get("COLDGUARD_SYNC_PERIOD_S", "10"))


def _record_fields(frame: bytes) -> dict[str, str]:
    fields = {}
    for word in frame.decode("ascii", "replace").split()[2:]:
        key, sep, value = word.partition("=")
        if not sep or key in fields:
            return {}
        fields[key] = value
    return fields


@dataclass
class _PendingRun:
    command_id: str
    boot_id: str
    expires_at: datetime
    deadline: float
    accepted_uptime_ms: int | None = None
    ack_observed_at: datetime | None = None
    arm_confirmed: bool = False
    start_after_uptime_ms: int | None = None


@dataclass(frozen=True)
class _TrialGrant:
    command_id: str
    boot_id: str
    granted_at: datetime
    deadline: float


def device_command_topic(device_id: str) -> str:
    return f"coldguard/{device_id}/command"


def device_command_ack_topic(device_id: str) -> str:
    return f"coldguard/{device_id}/command_ack"


def _member_translations():
    """Member C's committed ack translation and command contract, imported
    lazily so importing the adapter without them stays independent of the
    full contracts stack."""
    from coldguard_backend.ack_translation import (  # noqa: F401  (error vocabulary)
        AckTranslationError, device_ack_to_backend,
    )
    from coldguard_backend.contracts import Command
    from pydantic import ValidationError

    return device_ack_to_backend, Command, (AckTranslationError, ValidationError)


def _member_command_translation():
    """Member C's committed canonical-record renderer + its error type."""
    from coldguard_backend.command_translation import (
        CommandTranslationError, translate_command_to_device_serial,
    )

    return translate_command_to_device_serial, CommandTranslationError


def subscribe_confirmed(publisher, topic, *, supervised=False):
    """Subscribe on the delivered member ``Publisher``'s paho client and wait
    for the broker's SUBACK via the member poll loop. No member code is
    modified: the paho subscribe callback is attached from here."""
    client = publisher.client
    outcome = []

    def _on_subscribe(client_, userdata, mid, reason_codes, properties):
        outcome.append((mid, reason_codes))

    client.on_subscribe = _on_subscribe
    if supervised:
        options = mqtt.SubscribeOptions(qos=1, retainAsPublished=True, retainHandling=2)
        result = client.subscribe(topic, options=options)
    else:
        result = client.subscribe(topic, qos=1)
    if result[0] != mqtt.MQTT_ERR_SUCCESS:
        raise PublishError(f"MQTT subscribe failed: {result[0]}")
    deadline = monotonic() + NETWORK_TIMEOUT
    while not (outcome and outcome[0][0] == result[1]):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise PublishError("timed out waiting for broker subscribe acknowledgement")
        publisher.poll(min(0.2, remaining))
    codes = outcome[0][1]
    codes = codes if isinstance(codes, list) else [codes]
    refused = [code for code in codes if code.is_failure]
    if refused:
        raise PublishError(f"MQTT subscribe refused: {refused[0]}")


class CommandSerialWriter:
    """Thread-safe console-line writer sharing the pump's stream handle.

    The foreground pump owns the port. Serial writes are serialized.
    """

    def __init__(self, stream):
        self._stream = stream
        self._lock = Lock()

    def __call__(self, line: str) -> None:
        if not line.isascii() or not line.isprintable():
            raise ValueError("console line must be printable ASCII")
        data = line.encode("ascii") + b"\r\n"
        with self._lock:
            if self._stream.write(data) != len(data):
                raise OSError("incomplete console write")


class DownlinkBridge:
    """Opt-in device-directed integration bridge (Leader adapter).

    Downlink: a canonical Member C Command envelope published on
    ``coldguard/<device>/command`` is rendered in the device's own
    operator-console grammar (CMDTEST line) and written to the shared
    console stream. Uplink: the device's real ``#CG CMDACK`` records are
    translated by Member C's committed ack translation and published on
    ``coldguard/<device>/command_ack``.

    Deliberate limits:
    - The device stamps such records SOURCE_LOCAL_CONSOLE and refuses
      anything but its canonical NETWORK source (SAFETY_BLOCKED /
      SOURCE_NOT_CANONICAL). This bridge does not and must not bypass that
      provenance firewall: console bytes are not authenticated network input.
    - The backend's own Command model and the device's own validator remain
      the only admission authorities over the forwarded bytes.
    """

    def __init__(self, device_id: str, *, write_line, publisher,
                 expect_command_id=None,
                 max_future_skew_s=300.0, device_envelope=False,
                 require_verified_clock=True, auto_sync=True):
        self.device_id = device_id
        self._write_line = write_line
        self._publisher = publisher
        self.expect_command_id = expect_command_id
        self.max_future_skew_s = max_future_skew_s
        # Envelope mode renders Member C's delivered flat record (the exact
        # field set the device's reserved "#CG CMD " entrypoint validates)
        # instead of the operator-console CMDTEST form. It requires the
        # device-side Leader ingress (the boot record advertises
        # "#CG NETCMD status=READY"); envelopes sent to an image without it
        # are refused by the delivered console as UNKNOWN_COMMAND, so this
        # flag is an operator-gated opt-in, never a default.
        self.device_envelope = device_envelope
        # Host→device time anchor: engaged only with the capture of a live
        # capability challenge and only while THIS host's clock verifies
        # against a trusted network source. The PC system clock is the UTC
        # authority on whatever machine runs the stack; an offline or
        # unverifiable clock never anchors device time, and the device then
        # simply stays in its delivered fail-closed EPOCH_UNSYNCHRONIZED
        # state. Any local timezone with a correct UTC is equivalent.
        self.require_verified_clock = require_verified_clock
        # The serial pump owns periodic re-anchoring and operator grants.
        self.auto_sync = auto_sync
        self.stats = {
            "commands_forwarded": 0, "commands_refused": 0,
            "commands_expired": 0, "commands_future_skew": 0,
            "acks_relayed": 0, "acks_invalid": 0, "acks_mismatched": 0,
            "sync_records_sent": 0, "sync_refused_clock": 0,
        }
        self._observed_boot_id: str | None = None
        self._challenge: str | None = None
        self._clock_verdict: dict | None = None
        self._clock_checked_at: float | None = None
        self._sync_stop = Event()
        self._sync_lock = Lock()
        # AUTH has no boot field. Only accept it between a BOOT record and
        # that boot's first telemetry, on this session's serial stream.
        self._boot_banner_id: str | None = None
        self._boot_authorization: tuple[str, str] | None = None
        self._safe_telemetry_at: float | None = None
        self._telemetry_seq = 0
        self._telemetry_uptime_ms = -1
        self._pending_run: _PendingRun | None = None
        self._start_result_run: _PendingRun | None = None
        self._session_id = str(uuid4())
        self._grant: _TrialGrant | None = None
        self._trial_command_id: str | None = None
        self._trial_boot_id: str | None = None
        self._arm_sent = False
        self.poll_operator = None

    def close(self) -> None:
        """Stops the sync loop (the device goes stale fail-closed on its
        own unless another session re-anchors it)."""
        with self._sync_lock:
            self._sync_stop.set()
            self._challenge = None
        self._boot_authorization = None
        self._grant = None
        self._boot_banner_id = None
        self._start_result_run = None
        self.invalidate_telemetry()

    def invalidate_telemetry(self) -> None:
        self._safe_telemetry_at = None
        self._grant = None
        self._pending_run = None

    def _note_boot(self, boot: str) -> None:
        with self._sync_lock:
            previous = self._observed_boot_id
            if boot == previous:
                return
            self._observed_boot_id = boot
            if previous is not None:
                self._challenge = None
        self._boot_banner_id = None
        self._boot_authorization = None
        self._grant = None
        self._start_result_run = None
        self._telemetry_seq = 0
        self._telemetry_uptime_ms = -1
        self.invalidate_telemetry()

    def note_telemetry(self, payload: dict, *, read_at: float) -> None:
        boot = payload["boot_id"]
        self._note_boot(boot)
        self._boot_banner_id = None
        seq, uptime = payload["seq"], payload["uptime_ms"]
        if seq <= self._telemetry_seq or uptime <= self._telemetry_uptime_ms:
            self.invalidate_telemetry()
            return
        self._telemetry_seq, self._telemetry_uptime_ms = seq, uptime
        if (payload["door"]["state"] == "CLOSED"
                and payload["quality"]["thermal"] == "VALID"
                and payload["quality"]["electrical"] == "VALID"
                and payload["actuation"] == {"cooling": "OFF", "duty": 0.0}):
            self._safe_telemetry_at = read_at
            run = self._live_pending_run()
            if (run and run.arm_confirmed
                    and 0 < uptime - run.accepted_uptime_ms < NETWORK_TIMEOUT * 1000):
                self._pending_run = None
                self._grant = None  # Consumed before the sole START write.
                self._write_line(f"START {SUPERVISED_RUN_SECONDS}")
                run.start_after_uptime_ms = uptime
                self._start_result_run = run
                log.info("downlink: console START requested for %s", run.command_id)
        else:
            self.invalidate_telemetry()

    # -- device-stream observation -------------------------------------------

    def note_frame(self, frame: bytes, *, observed_at: datetime | None = None) -> dict | None:
        """Absorbs one device stream frame (TELEM in particular) to track
        the live boot identity, and the NETCMD capability line to capture
        this boot's time-anchor challenge."""

        if frame.startswith(NETCMD_PREFIX) and b"status=READY" in frame:
            for token in frame.decode("ascii", "replace").split():
                if token.startswith("challenge="):
                    with self._sync_lock:
                        self._challenge = token.split("=", 1)[1]
                    break
            return
        if self._sync_stop.is_set():
            return
        if frame.startswith(b"#CG BOOT "):
            fields = _record_fields(frame)
            boot = fields.get("boot_id", "")
            self._boot_banner_id = None
            if BOOT_ID_RE.fullmatch(boot):
                self._note_boot(boot)
                if (self._telemetry_seq == 0 and fields.get("event") == "IDENTITY"
                        and fields.get("device_id") == self.device_id):
                    self._boot_banner_id = boot
        elif frame.startswith(AUTH_PREFIX + b" "):
            token = _record_fields(frame).get("token", "")
            boot = self._boot_banner_id
            self._boot_banner_id = None
            if boot and self._boot_authorization is None and BOOT_ID_RE.fullmatch(token):
                self._boot_authorization = (boot, token)
                log.info("downlink: AUTH_CAPTURED for boot %s", boot)
        elif frame.startswith(b"#CG TEC "):
            return self._note_console_result(_record_fields(frame), observed_at)
        return None

    # -- host→device time anchor ---------------------------------------------

    def _verify_clock_once(self) -> bool:
        from integration.leader_host_clock import recheck_interval_s, verify_host_clock

        verdict = self._clock_verdict
        fresh = (self._clock_checked_at is not None
                 and monotonic() - self._clock_checked_at < recheck_interval_s())
        if fresh:
            return verdict is not None and verdict["verdict"] == "VERIFIED"
        verdict = verify_host_clock()
        self._clock_verdict = verdict
        self._clock_checked_at = monotonic()
        if verdict["verdict"] != "VERIFIED":
            log.warning("clock: host time %s - %s; device time anchoring "
                        "stays disabled (fail-closed on the device)",
                        verdict["verdict"],
                        verdict.get("reasons") or
                        f"skew {verdict.get('skew_s')}s vs {verdict.get('source')}")
            return False
        log.info("clock: host UTC verified against %s (skew %.3fs)",
                 verdict["source"], verdict["skew_s"])
        return True

    def sync_tick(self) -> bool:
        """One anchor attempt; returns True when a record was written."""
        with self._sync_lock:
            challenge = self._challenge
            boot = self._observed_boot_id
        if self.device_envelope and challenge and boot:
            if self.require_verified_clock and not self._verify_clock_once():
                self.stats["sync_refused_clock"] += 1
                return False
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            with self._sync_lock:
                if (self._sync_stop.is_set() or boot != self._observed_boot_id
                        or challenge != self._challenge):
                    return False
                self._write_line(f"#CG SYNC host={now_ms} challenge={challenge} boot={boot}")
            self.stats["sync_records_sent"] += 1
            return True
        return False

    def install(self):
        """Wire this bridge onto the delivered member publisher: subscribe the
        canonical command topic on the device principal and route messages."""
        topic = device_command_topic(self.device_id)
        subscribe_confirmed(self._publisher, topic, supervised=True)
        self._publisher.client.on_message = self._on_message

    def _on_message(self, client, userdata, message) -> None:
        """paho CallbackAPI v2 seam: (client, userdata, message) -> bridge."""
        if message.retain:
            return
        self.handle_command_message(message.topic, message.payload)

    def handle_command_message(self, topic: str, payload: bytes) -> None:
        if self._sync_stop.is_set():
            return
        if topic != device_command_topic(self.device_id):
            log.warning("downlink: ignoring unexpected topic %s", topic)
            self.stats["commands_refused"] += 1
            return
        try:
            envelope = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            log.warning("downlink: undecodable command payload: %s", exc)
            self.stats["commands_refused"] += 1
            return
        _, Command, cmd_errors = _member_translations()
        try:
            command = Command.model_validate(envelope)
        except cmd_errors[1] as exc:
            log.warning("downlink: command refused by contract: %s", exc)
            self.stats["commands_refused"] += 1
            return
        if command.device_id != self.device_id:
            self.stats["commands_refused"] += 1
            return
        # Leader time gate (system UTC clock of this gateway/backend host): an
        # expired command, or one stamped implausibly far in the future, never
        # reaches the device. The device keeps its own EPOCH gating fail-closed
        # on top; this gate implements the owner-agreed split where only the
        # gateway/backend carry a wall clock.
        now = datetime.now(timezone.utc)
        if command.expires_at <= now:
            log.warning(
                "downlink: command %s expired at %s; refusing before the device",
                command.command_id, command.expires_at.isoformat(),
            )
            self.stats["commands_expired"] += 1
            self.stats["commands_refused"] += 1
            return
        if command.created_at > now + timedelta(seconds=self.max_future_skew_s):
            log.warning(
                "downlink: command %s created_at %s exceeds the %ss future "
                "skew gate; refusing before the device",
                command.command_id, command.created_at.isoformat(),
                self.max_future_skew_s,
            )
            self.stats["commands_future_skew"] += 1
            self.stats["commands_refused"] += 1
            return
        action = command.action
        duty_permille = 0 if action.duty is None else int(round(action.duty * 1000))
        energizing = action.cooling == "ON" or duty_permille > 0
        if energizing and not self._allows_trial(command):
            log.warning(
                "downlink: refusing actuation-requesting command %s "
                "(physical commissioning authorization is a separate gate)",
                command.command_id,
            )
            self.stats["commands_refused"] += 1
            return
        if self.device_envelope:
            # The device's reserved canonical entrypoint: Member C's committed
            # renderer, handed to the receiving layer unchanged. The label-
            # grammar gate does not apply here - a canonical UUID is exactly
            # the identity this form must carry, and the delivered device
            # parser is the authority over what fits.
            translate, translation_error = _member_command_translation()
            try:
                record = translate(command)
            except (translation_error, UnicodeEncodeError):
                log.warning(
                    "downlink: command %s cannot be rendered as a device record", command.command_id,
                )
                self.stats["commands_refused"] += 1
                return
            if not record.isascii() or not record.isprintable():
                log.warning("downlink: refusing a command record containing non-printable bytes")
                self.stats["commands_refused"] += 1
                return
            self._write_line(f"#CG CMD {record}")
            self.stats["commands_forwarded"] += 1
            log.info("downlink: forwarded canonical envelope %s", command.command_id)
            if energizing:
                self._pending_run = _PendingRun(command.command_id, self._observed_boot_id,
                                                command.expires_at, monotonic() + NETWORK_TIMEOUT)
            elif self._trial_command_id and command.action.cooling == "OFF" and duty_permille == 0:
                self.abort_trial()
            return
        if DEVICE_LABEL_RE.match(command.command_id) is None:
            log.warning(
                "downlink: command_id %r does not fit the device label grammar; "
                "refusing to mangle it",
                command.command_id,
            )
            self.stats["commands_refused"] += 1
            return
        self._write_line(f"CMDTEST {command.command_id} {action.cooling} {duty_permille}")
        self.stats["commands_forwarded"] += 1
        log.info("downlink: forwarded %s", command.command_id)

    def _has_ready_boot(self) -> bool:
        return (not self._sync_stop.is_set() and self._boot_authorization is not None
                and self._boot_authorization[0] == self._observed_boot_id
                and self._safe_telemetry_at is not None
                and monotonic() - self._safe_telemetry_at < TELEMETRY_MAX_AGE_S)

    def grant_trial(self, command_id: str) -> str | None:
        """Called by the foreground operator console, on the serial pump thread."""
        if self._trial_command_id or not self.device_envelope or not self._has_ready_boot():
            return None
        command_id = str(UUID(command_id))
        self._trial_command_id = command_id
        self._trial_boot_id = self._observed_boot_id
        self._grant = _TrialGrant(command_id, self._observed_boot_id,
                                  datetime.now(timezone.utc), monotonic() + TRIAL_GRANT_SECONDS)
        return self._observed_boot_id

    def abort_trial(self) -> None:
        should_stop = (self._trial_boot_id == self._observed_boot_id
                       and (self._pending_run is not None or self._arm_sent))
        self._grant = None
        self._pending_run = None
        self._start_result_run = None
        if should_stop and not self._sync_stop.is_set():
            self._write_line("STOP")

    def _live_grant(self) -> _TrialGrant | None:
        grant = self._grant
        if grant and (monotonic() >= grant.deadline or grant.boot_id != self._observed_boot_id):
            self._grant = None
        return self._grant

    def _allows_trial(self, command) -> bool:
        grant = self._live_grant()
        return (grant is not None and self._pending_run is None and not self._arm_sent
                and self._has_ready_boot() and command.command_id == grant.command_id
                and command.run_id == UUID(grant.command_id).hex
                and command.reason_code == TEC_TRIAL_REASON_PREFIX + grant.boot_id
                and grant.granted_at <= command.created_at <= datetime.now(timezone.utc)
                and command.action.cooling == "ON"
                and command.action.duty == SUPERVISED_DUTY_PERMILLE / 1000)

    def _live_pending_run(self) -> _PendingRun | None:
        run = self._pending_run
        if run and (run.boot_id != self._observed_boot_id
                    or monotonic() >= run.deadline or datetime.now(timezone.utc) >= run.expires_at
                    or not self._live_grant() or not self._has_ready_boot()):
            self._pending_run = None
            self._grant = None
        return self._pending_run

    def _note_console_result(self, fields: dict[str, str], observed_at: datetime | None) -> dict | None:
        event = fields.get("event")
        if event == "ARM":
            run = self._live_pending_run()
            if run is None or run.accepted_uptime_ms is None or run.arm_confirmed:
                return None
            if fields.get("result") == "ARMED" and fields.get("state") == "ARMED":
                run.arm_confirmed = True
            else:
                self._pending_run = None
                self._grant = None
        elif event == "START":
            run = self._start_result_run
            self._start_result_run = None
            if run is None:
                return None
        else:
            return None
        if observed_at is None:
            return None
        return {
            "kind": "tec_console_result", "event": event, "result": fields.get("result"),
            "state": fields.get("state"), "duty_permille": fields.get("duty"),
            "remaining_ms": fields.get("remaining_ms"),
            "device_id": self.device_id, "boot_id": run.boot_id, "command_id": run.command_id,
            "gateway_session_id": self._session_id, "ack_uptime_ms": run.accepted_uptime_ms,
            "preceding_telemetry_uptime_ms": (run.start_after_uptime_ms if event == "START"
                                               else self._telemetry_uptime_ms),
            "observed_at": observed_at.isoformat(),
            "ack_observed_at": run.ack_observed_at.isoformat(),
        }

    def relay_ack(self, line: str, *, observed_at: datetime | None = None) -> None:
        observed_at = observed_at or datetime.now(timezone.utc)
        device_ack_to_backend, _, ack_errors = _member_translations()
        try:
            envelope = device_ack_to_backend(line)
        except ack_errors[0] as exc:
            log.warning("uplink: invalid device ACK record: %s", exc)
            self.stats["acks_invalid"] += 1
            return
        if (self.expect_command_id is not None
                and envelope["command_id"] != self.expect_command_id):
            log.warning(
                "uplink: ACK command_id %r != expected %r; relaying uncorrelated "
                "(correlation stays the backend's fail-closed authority)",
                envelope["command_id"], self.expect_command_id,
            )
            self.stats["acks_mismatched"] += 1
        run = self._live_pending_run()
        self._publisher.publish(device_command_ack_topic(self.device_id),
                                json.dumps(envelope, separators=(",", ":")).encode())
        if run is not None and self.poll_operator is not None:
            self.poll_operator()
        self.stats["acks_relayed"] += 1
        log.info("uplink: relayed ACK %s status=%s", envelope["command_id"],
                 envelope["status"])
        if (run is None or self._live_pending_run() is not run or run.accepted_uptime_ms is not None
                or envelope["command_id"] != run.command_id
                or envelope["device_id"] != self.device_id or envelope["boot_id"] != run.boot_id):
            return
        if (envelope["status"] != "ACCEPTED" or _record_fields(line.encode("ascii")).get("source") != "NETWORK"
                or envelope.get("desired") != {"cooling": "ON", "duty": SUPERVISED_DUTY_PERMILLE / 1000}
                or not 0 <= envelope["uptime_ms"] - self._telemetry_uptime_ms < TELEMETRY_MAX_AGE_S * 1000):
            self._pending_run = None
            self._grant = None
            return
        self._arm_sent = True
        run.accepted_uptime_ms = envelope["uptime_ms"]
        run.ack_observed_at = observed_at
        run.deadline = monotonic() + TELEMETRY_MAX_AGE_S
        self._write_line(f"ARM {self._boot_authorization[1]}")
        log.info("downlink: console ARM requested for %s", run.command_id)
