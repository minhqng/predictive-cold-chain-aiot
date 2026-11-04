"""Wire protocol for the ColdGuard Member A acceptance application.

Parses the canonical W05/W06 `#CG TELEM` grammar and the H8 bench
`#CG H8S` grammar without inventing values. Missing or invalid
measurements stay ``None``; a numeric token is accepted only when its
companion status (when the grammar has one) is ``OK``.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import re
from typing import Iterable

PREFIX = "#CG"
BAUD = 115200

TELEM_REQUIRED = (
    "device_id",
    "boot_id",
    "seq",
    "uptime_ms",
    "t_inside_c",
    "t_hot_side_c",
    "t_ambient_c",
    "relative_humidity_pct",
    "door_open",
    "voltage_v",
    "current_a",
    "power_w",
    "pwm_duty",
    "output_stage",
    "cooling_applied",
    "fault_code",
    "quality",
)

QUALITY_VOCABULARY = {"VALID", "DEGRADED", "INVALID", "UNKNOWN"}
ACK_VOCABULARY = {
    "ACCEPTED",
    "REJECTED",
    "DUPLICATE_CANONICAL",
    "EXPIRED",
    "SAFETY_BLOCKED",
    "INVALID_STATE",
    "OUT_OF_RANGE",
}
TEC_STATES = {"BOOT", "OFF", "ARMED", "COOLING", "COOLDOWN", "FAULT_LATCH", "UNKNOWN"}

_HEX8_RE = re.compile(r"^[0-9A-Fa-f]{8}$")
_HEX16_RE = re.compile(r"^[0-9A-Fa-f]{16}$")
_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,35}$")
_TOKEN_RE = re.compile(r"^[0-9A-Fa-f]{8}$")
_PHASES = {"UNSET", "G0", "G1", "G2", "G3", "G4", "G5", "TEC_OFF"}

# Diagnostic lines the parser must reject. They are fixed here so the
# application never gains a general-purpose console write path. The CMDTEST
# line is deliberately outside the console parser's duty bound (1000) while
# the other lines are malformed; both rejection paths are under test.
PROBE_LINES = ("START", "FOO", "ARM 123", "START not-a-number",
               "CMDTEST accept-outofrange OFF 1001")


class CommandError(ValueError):
    """A command that the application refuses to put on the wire."""


def utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def parse_kv(tokens: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, _, value = token.partition("=")
        if key and key not in out:
            out[key] = value
    return out


def _number(value: str | None) -> float | None:
    if value is None or value in {"nan", "NaN", "UNAVAILABLE", "UNKNOWN", ""}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _integer(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if text.lower().startswith("0x"):
        try:
            return int(text, 16)
        except ValueError:
            return None
    number = _number(value)
    if number is None or not float(number).is_integer():
        return None
    return int(number)


def _flag(value: str | None) -> bool | None:
    if value is None:
        return None
    if value in {"1", "ON", "TRUE", "True", "true"}:
        return True
    if value in {"0", "OFF", "FALSE", "False", "false"}:
        return False
    return None


def _ok(value: str | None, status: str | None) -> bool:
    if value is None or value in {"nan", "NaN"}:
        return False
    if status is not None and status != "OK":
        return False
    return True


@dataclasses.dataclass(frozen=True)
class BootIdentity:
    boot_id: str | None = None
    boot_count: int | None = None
    device_id: str | None = None
    firmware_version: str | None = None
    hardware_config_id: str | None = None
    pin_map: int | None = None
    grammar: int | None = None
    calibration_id: str | None = None

    def merged(self, other: "BootIdentity") -> "BootIdentity":
        values = {}
        for field in dataclasses.fields(self):
            current = getattr(self, field.name)
            incoming = getattr(other, field.name)
            values[field.name] = current if current is not None else incoming
        return BootIdentity(**values)


@dataclasses.dataclass(frozen=True)
class RomEntry:
    role: str
    rom: str
    present: bool
    status: str | None


@dataclasses.dataclass(frozen=True)
class AckRecord:
    command_id: str
    status: str
    reason: str
    source: str
    expiry_evaluable: bool
    desired_cooling: str
    desired_duty_permille: int | None
    applied_cooling: str
    applied_duty_permille: int | None
    output_stage: str
    boot_id: str | None
    device_id: str | None
    uptime_ms: int | None
    raw: str
    host_time: _dt.datetime


@dataclasses.dataclass(frozen=True)
class TelemetryFrame:
    kind: str
    raw: str
    host_time: _dt.datetime
    schema: int | None
    warnings: tuple[str, ...]
    kv: dict[str, str]

    device_id: str | None
    boot_id: str | None
    seq: int | None
    uptime_ms: int | None
    firmware_version: str | None
    hardware_config_id: str | None
    calibration_id: str | None
    test_phase: str | None
    quality: str | None
    state: str | None
    fault_bits: int | None
    fault_reason: str | None
    stop_reason: str | None

    t: dict[str, float | None]
    t_status: dict[str, str | None]
    t_role: dict[str, str | None]
    chamber_c: float | None
    chamber_status: str | None
    hot_side_c: float | None
    hot_side_status: str | None
    ambient_c: float | None
    ambient_status: str | None
    humidity_pct: float | None
    humidity_status: str | None
    door_open: bool | None
    door_status: str | None
    door_raw: int | None

    voltage_v: float | None
    current_a: float | None
    power_w: float | None
    energy_wh: float | None
    electrical_status: str | None

    pwm_duty: int | None
    pwm_applied: int | None
    pwm_readback: int | None
    output_stage: str | None
    cooling_applied: str | None
    cooling_evidence: str | None
    fan: str | None
    desired_cooling: str | None
    desired_duty: int | None
    last_ack_status: str | None

    @property
    def is_h8(self) -> bool:
        return self.kind == "H8S"

    @property
    def is_canonical(self) -> bool:
        return self.kind == "TELEM"

    def temperature(self, role: str) -> float | None:
        aliases = {"SPARE": ("SPARE", "T4"), "T4": ("T4", "SPARE")}
        for name in aliases.get(role.upper(), (role.upper(),)):
            value = self.t.get(name)
            if value is not None:
                return value
        return None

    def temperature_status(self, role: str) -> str | None:
        aliases = {"SPARE": ("SPARE", "T4"), "T4": ("T4", "SPARE")}
        for name in aliases.get(role.upper(), (role.upper(),)):
            if name in self.t_status:
                return self.t_status[name]
        return None

    def role_of_slot(self, role: str) -> str | None:
        wanted = role.upper()
        for slot, actual in self.t_role.items():
            if actual and actual.upper() == wanted:
                return slot
        return None

    def temperature_by_role(self, role: str) -> float | None:
        slot = self.role_of_slot(role)
        return self.temperature(slot) if slot else None

    def temp_valid(self, role: str) -> bool:
        return _ok(
            "nan" if self.temperature(role) is None else str(self.temperature(role)),
            self.temperature_status(role),
        )

    def electrical_valid(self) -> bool:
        return (
            self.voltage_v is not None
            and self.current_a is not None
            and self.power_w is not None
            and (self.electrical_status is None or self.electrical_status == "OK")
        )

    @property
    def cooling_on(self) -> bool:
        if self.cooling_applied is not None:
            return self.cooling_applied.upper() == "ON"
        return (self.pwm_applied or 0) > 0 or (self.state == "COOLING")

    @property
    def is_default_off(self) -> bool:
        if self.state is None and self.cooling_applied is None and self.pwm_applied is None:
            return False
        if self.state is not None and self.state not in {"OFF", "BOOT", "COOLDOWN", "FAULT_LATCH"}:
            return False
        if self.cooling_applied is not None:
            return self.cooling_applied.upper() == "OFF"
        return (self.pwm_applied or 0) == 0


@dataclasses.dataclass(frozen=True)
class ParsedLine:
    kind: str
    raw: str
    host_time: _dt.datetime
    kv: dict[str, str]
    frame: TelemetryFrame | None = None
    boot: BootIdentity | None = None
    rom: RomEntry | None = None
    ack: AckRecord | None = None
    auth_token: str | None = None
    error: str | None = None


def _parse_float_field(kv: dict[str, str], value_key: str, status_key: str | None = None) -> tuple[float | None, str | None]:
    status = kv.get(status_key) if status_key else None
    raw = kv.get(value_key)
    value = _number(raw)
    if status is not None and status != "OK":
        value = None
    return value, status


def _probe_fields(kv: dict[str, str], kind: str) -> tuple[dict, dict, dict]:
    t: dict[str, float | None] = {}
    status: dict[str, str | None] = {}
    roles: dict[str, str | None] = {}
    if kind == "H8S":
        for slot in ("t1", "t2", "t3", "t4"):
            raw = kv.get(slot)
            st = kv.get(f"{slot}_status")
            t[slot.upper()] = _number(raw) if (st in (None, "OK")) else None
            status[slot.upper()] = st
            roles[slot.upper()] = kv.get(f"{slot}_role")
        return t, status, roles
    for slot in ("T1", "T2", "T3", "SPARE"):
        raw = kv.get(f"raw_{slot.lower()}_c")
        st = kv.get(f"raw_{slot.lower()}_status")
        if raw is None and slot != "SPARE":
            raw = kv.get(f"{slot.lower()}_c")
            st = kv.get(f"{slot.lower()}_status")
        value = _number(raw)
        if st is not None and st != "OK":
            value = None
        t[slot] = value
        status[slot] = st
        roles[slot] = None
    return t, status, roles


def parse_telemetry(kind: str, raw: str, kv: dict[str, str], host_time: _dt.datetime) -> TelemetryFrame:
    warnings: list[str] = []
    schema = _integer(kv.get("schema"))
    t, t_status, t_role = _probe_fields(kv, kind)

    if kind == "TELEM":
        for field in TELEM_REQUIRED:
            if field not in kv:
                warnings.append(f"missing:{field}")
        chamber_c, chamber_st = _parse_float_field(kv, "t_inside_c", "t_inside_status")
        hot_c, hot_st = _parse_float_field(kv, "t_hot_side_c", "t_hot_side_status")
        ambient_c, ambient_st = _parse_float_field(kv, "t_ambient_c", "t_ambient_status")
        rh, rh_st = _parse_float_field(kv, "relative_humidity_pct", "relative_humidity_status")
        voltage, v_st = _parse_float_field(kv, "voltage_v", "voltage_status")
        current, i_st = _parse_float_field(kv, "current_a", "current_status")
        power, p_st = _parse_float_field(kv, "power_w", "power_status")
        energy, _ = _parse_float_field(kv, "energy_wh", "energy_status")
        electrical_status = v_st if v_st == i_st == p_st else "MIXED"
        pwm_duty = _integer(kv.get("pwm_duty"))
        pwm_applied = None
        pwm_readback = None
        output_stage = kv.get("output_stage")
        cooling_applied = kv.get("cooling_applied")
        cooling_evidence = kv.get("cooling_evidence")
        fan = kv.get("fan_command")
        state = kv.get("tec_state")
        fault_bits = _integer(kv.get("fault_code"))
        fault_reason = kv.get("fault_reason")
        stop_reason = kv.get("stop_reason")
    else:
        chamber_c, chamber_st = _parse_float_field(kv, "air_c", "air_c_status")
        hot_slot = None
        for slot, role in t_role.items():
            if (role or "").upper() == "HOT_SIDE":
                hot_slot = slot
                break
        hot_c = t.get(hot_slot) if hot_slot else None
        hot_st = t_status.get(hot_slot) if hot_slot else None
        ambient_c, ambient_st = chamber_c, chamber_st
        rh, rh_st = _parse_float_field(kv, "rh_pct", "rh_pct_status")
        voltage, v_st = _parse_float_field(kv, "voltage_v", "voltage_v_status")
        current, i_st = _parse_float_field(kv, "current_a", "current_a_status")
        power, p_st = _parse_float_field(kv, "power_w", "power_w_status")
        energy = None
        electrical_status = v_st if v_st == i_st == p_st else "MIXED"
        pwm_duty = _integer(kv.get("pwm_req_permille"))
        pwm_applied = _integer(kv.get("pwm_applied_permille"))
        pwm_readback = _integer(kv.get("pwm_readback_permille"))
        output_stage = kv.get("output_stage")
        cooling_applied = "ON" if (pwm_applied or 0) > 0 else "OFF"
        cooling_evidence = None
        fan = kv.get("fan")
        state = kv.get("state")
        fault_bits = None
        raw_fault = kv.get("fault_bits")
        if raw_fault:
            try:
                fault_bits = int(raw_fault, 16)
            except ValueError:
                fault_bits = None
        fault_reason = kv.get("fault")
        stop_reason = kv.get("stop_reason")

    door_raw = _integer(kv.get("door_raw"))
    door_open = _flag(kv.get("door_open"))
    door_status = kv.get("door_status")
    uptime = _integer(kv.get("uptime_ms")) or _integer(kv.get("device_ms"))
    quality = kv.get("quality")
    if quality is not None and quality not in QUALITY_VOCABULARY:
        warnings.append(f"quality_vocabulary:{quality}")
    state_value = state or kv.get("state")
    if state_value is not None and state_value not in TEC_STATES:
        warnings.append(f"state_vocabulary:{state_value}")

    frame = TelemetryFrame(
        kind=kind,
        raw=raw,
        host_time=host_time,
        schema=schema,
        warnings=tuple(warnings),
        kv=kv,
        device_id=kv.get("device_id"),
        boot_id=kv.get("boot_id"),
        seq=_integer(kv.get("seq")),
        uptime_ms=uptime,
        firmware_version=kv.get("firmware_version") or kv.get("fw"),
        hardware_config_id=kv.get("hardware_config_id") or kv.get("hw"),
        calibration_id=kv.get("calibration_id"),
        test_phase=kv.get("test_phase") or kv.get("stage"),
        quality=quality,
        state=state_value,
        fault_bits=fault_bits,
        fault_reason=fault_reason,
        stop_reason=stop_reason,
        t=t,
        t_status=t_status,
        t_role=t_role,
        chamber_c=chamber_c,
        chamber_status=chamber_st,
        hot_side_c=hot_c,
        hot_side_status=hot_st,
        ambient_c=ambient_c,
        ambient_status=ambient_st,
        humidity_pct=rh,
        humidity_status=rh_st,
        door_open=door_open,
        door_status=door_status,
        door_raw=door_raw,
        voltage_v=voltage,
        current_a=current,
        power_w=power,
        energy_wh=energy,
        electrical_status=electrical_status,
        pwm_duty=pwm_duty,
        pwm_applied=pwm_applied,
        pwm_readback=pwm_readback,
        output_stage=output_stage,
        cooling_applied=cooling_applied,
        cooling_evidence=cooling_evidence,
        fan=fan,
        desired_cooling=kv.get("desired_cooling"),
        desired_duty=_integer(kv.get("desired_duty_permille")),
        last_ack_status=kv.get("last_ack_status"),
    )
    return frame


def parse_line(line: str, host_time: _dt.datetime | None = None) -> ParsedLine:
    stamp = host_time or utcnow()
    text = line.rstrip("\r\n")
    if not text.startswith(PREFIX + " "):
        return ParsedLine(kind="OTHER", raw=text, host_time=stamp, kv={})
    tokens = text.split()
    if len(tokens) < 2:
        return ParsedLine(kind="OTHER", raw=text, host_time=stamp, kv={})
    kind = tokens[1]
    kv = parse_kv(tokens[2:])

    if kind == "TELEM":
        return ParsedLine(kind="TELEM", raw=text, host_time=stamp, kv=kv,
                          frame=parse_telemetry("TELEM", text, kv, stamp))
    if kind == "H8S":
        return ParsedLine(kind="H8S", raw=text, host_time=stamp, kv=kv,
                          frame=parse_telemetry("H8S", text, kv, stamp))
    if kind == "BOOT":
        if kv.get("event") == "IDENTITY":
            boot = BootIdentity(
                boot_id=kv.get("boot_id"),
                boot_count=_integer(kv.get("boot_count")),
                device_id=kv.get("device_id"),
                firmware_version=kv.get("firmware_version"),
                hardware_config_id=kv.get("hardware_config_id"),
                calibration_id=kv.get("calibration_id"),
            )
        else:
            boot = BootIdentity(
                boot_id=kv.get("boot_id"),
                boot_count=_integer(kv.get("boot_count")),
            )
        return ParsedLine(kind="BOOT", raw=text, host_time=stamp, kv=kv, boot=boot)
    if kind == "LOG":
        boot = BootIdentity(
            device_id=kv.get("device"),
            firmware_version=kv.get("fw"),
            hardware_config_id=kv.get("hw"),
            pin_map=_integer(kv.get("pin_map")),
            grammar=_integer(kv.get("grammar")),
        )
        return ParsedLine(kind="LOG", raw=text, host_time=stamp, kv=kv, boot=boot)
    if kind == "ROM":
        role = (kv.get("role") or "").upper()
        rom = (kv.get("rom") or "").upper()
        if not role or not _HEX16_RE.match(rom):
            return ParsedLine(kind="ROM", raw=text, host_time=stamp, kv=kv,
                              error="MALFORMED_ROM_LINE")
        return ParsedLine(
            kind="ROM",
            raw=text,
            host_time=stamp,
            kv=kv,
            rom=RomEntry(role=role, rom=rom, present=kv.get("present") == "1",
                         status=kv.get("status")),
        )
    if kind == "AUTH":
        token = kv.get("token")
        return ParsedLine(kind="AUTH", raw=text, host_time=stamp, kv=kv,
                          auth_token=token if token and _HEX8_RE.match(token) else None,
                          error=None if token and _HEX8_RE.match(token) else "BAD_AUTH_TOKEN")
    if kind == "CMDACK":
        status = kv.get("status") or "UNKNOWN"
        ack = AckRecord(
            command_id=kv.get("command_id", ""),
            status=status,
            reason=kv.get("reason", "NONE"),
            source=kv.get("source", "UNKNOWN"),
            expiry_evaluable=kv.get("expiry_evaluable") == "1",
            desired_cooling=kv.get("desired_cooling", "UNKNOWN"),
            desired_duty_permille=_integer(kv.get("desired_duty_permille")),
            applied_cooling=kv.get("applied_cooling", "UNKNOWN"),
            applied_duty_permille=_integer(kv.get("applied_duty_permille")),
            output_stage=kv.get("output_stage", "UNKNOWN"),
            boot_id=kv.get("boot_id"),
            device_id=kv.get("device_id"),
            uptime_ms=_integer(kv.get("uptime_ms")),
            raw=text,
            host_time=stamp,
        )
        return ParsedLine(kind="CMDACK", raw=text, host_time=stamp, kv=kv, ack=ack)
    return ParsedLine(kind=kind, raw=text, host_time=stamp, kv=kv)


def arm(token: str) -> bytes:
    if not _TOKEN_RE.match(token or ""):
        raise CommandError("ARM token must be exactly 8 hexadecimal characters")
    return f"ARM {token.upper()}\n".encode("ascii")


def clear(token: str) -> bytes:
    if not _TOKEN_RE.match(token or ""):
        raise CommandError("CLEAR token must be exactly 8 hexadecimal characters")
    return f"CLEAR {token.upper()}\n".encode("ascii")


def start(seconds: int) -> bytes:
    try:
        value = int(seconds)
    except (TypeError, ValueError) as exc:
        raise CommandError("START duration must be an integer number of seconds") from exc
    if not 1 <= value <= 600:
        raise CommandError("START duration must be 1..600 seconds")
    return f"START {value}\n".encode("ascii")


def stop() -> bytes:
    return b"STOP\n"


def estop() -> bytes:
    return b"ESTOP\n"


def status() -> bytes:
    return b"STATUS\n"


def run_label(label: str) -> bytes:
    if not _SAFE_LABEL_RE.match(label or ""):
        raise CommandError("RUN label must be 1..36 safe characters")
    return f"RUN {label}\n".encode("ascii")


def phase(name: str) -> bytes:
    value = (name or "").upper()
    if value not in _PHASES:
        raise CommandError(f"PHASE must be one of {sorted(_PHASES)}")
    return f"PHASE {value}\n".encode("ascii")


def cmdtest(command_id: str, cooling_on: bool, duty_permille: int) -> bytes:
    if not _SAFE_LABEL_RE.match(command_id or ""):
        raise CommandError("CMDTEST id must be 1..36 safe characters")
    duty = int(duty_permille)
    if not 0 <= duty <= 1000:
        raise CommandError("CMDTEST duty must be 0..1000 permille")
    action = "ON" if cooling_on else "OFF"
    return f"CMDTEST {command_id} {action} {duty}\n".encode("ascii")


def boot_token_from_lines(lines: Iterable[str]) -> BootIdentity:
    boot = BootIdentity()
    for line in lines:
        parsed = parse_line(line)
        if parsed.boot is not None:
            boot = boot.merged(parsed.boot)
    return boot
