"""Wire-contract models for ColdGuard telemetry and commands (C-W01-03).

Derived from Doc 02 (telemetry snapshot section 4, command contract
section 28, normalized field semantics section 14). This module validates
the MQTT wire representation only; it does not define database storage
(the future normalized names such as ``t1_c`` / ``cooling_current_a`` are
deliberately different from the wire names used here).

Wire ``schema_version`` is ``1`` per Doc 02. The fixture maturity label
"v0" refers to this development slice, never to the wire version.

Single-branch rule: the hardware has one TEC cooling branch (Docs 00-01).
Legacy dual-channel keys (``current_1``/``current_2``, ``power_1``/
``power_2``, ``cmd_1``/``cmd_2``) and INA226 references are rejected
anywhere in a payload instead of being silently accepted.

Identity rule: ``(device_id, boot_id, seq)`` is the logical dedup
identity. Timestamps are event time, never identity. W01 validates shape
only; database dedup belongs to a later slice.

Missing data rule: an unknown quantity uses ``None`` together with a
non-``VALID`` section quality. A ``None`` value under ``VALID`` quality,
or a fabricated measured value, fails validation.

Identifier rule: ``command_id`` is stable logical identity with no
enforced UUID/ULID textual encoding. ``expires_at`` must be strictly
after ``created_at``; expiry is safety-relevant command meaning and the
device must still validate it independently.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from coldguard_backend.serial_observation import serial_observation

WIRE_SCHEMA_VERSION = 1
SERIAL_FRAME_MAX = 3072

Quality = Literal["VALID", "DEGRADED", "INVALID", "UNKNOWN"]
DeviceMode = Literal[
    "BOOT", "SELF_TEST", "ONLINE_NORMAL", "ONLINE_DEGRADED", "SAFE_LOCAL", "FAULT_LOCKOUT"
]
DoorState = Literal["OPEN", "CLOSED", "UNKNOWN"]
CoolingState = Literal["ON", "OFF"]

# Dual-branch / superseded-hardware keys that must never re-enter the
# single-branch contract (Doc 02 section 14.3 plus Doc 00 no-substitution
# policy: INA226 and a second TEC are not part of P0).
LEGACY_FORBIDDEN_KEYS = frozenset(
    {
        "current_1",
        "current_2",
        "power_1",
        "power_2",
        "cmd_1",
        "cmd_2",
        "ina226",
        "tec_2",
        "second_tec",
    }
)


def _reject_legacy_keys(payload: Any) -> Any:
    """Recursively reject legacy dual-channel keys in raw input."""
    stack: list[Any] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and key.lower() in LEGACY_FORBIDDEN_KEYS:
                    raise ValueError(
                        f"legacy dual-channel field {key!r} is forbidden: "
                        "ColdGuard P0 has one cooling branch"
                    )
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return payload


class _WireBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    _forbid_legacy = model_validator(mode="before")(_reject_legacy_keys)


class ThermalSection(_WireBase):
    """Three DS18B20 probe readings in °C; None marks a missing channel."""

    t1: float | None = None
    t2: float | None = None
    t3: float | None = None


class EnvironmentSection(_WireBase):
    """BME280 context: air temperature in °C, relative humidity in %RH."""

    t_air: float | None = None
    rh: float | None = None


class DoorSection(_WireBase):
    """MC-38 contact state. UNKNOWN must not be read as CLOSED."""

    state: DoorState


class ElectricalSection(_WireBase):
    """PZEM-017 cooling-branch observation (never total-system power)."""

    voltage_v: float | None = None
    current_a: float | None = None
    power_w: float | None = None
    energy_wh: float | None = None

    @field_validator("energy_wh")
    @classmethod
    def _energy_counter_non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("energy_wh is a monotonic counter and cannot be negative")
        return value


class ActuationSection(_WireBase):
    """Edge applied state for the single cooling branch."""

    cooling: CoolingState
    duty: float | None = None

    @field_validator("duty")
    @classmethod
    def _duty_in_unit_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("duty must be within [0.0, 1.0]")
        return value


class QualitySection(_WireBase):
    """Per-section measurement trust. Missing values require non-VALID."""

    thermal: Quality
    environment: Quality
    electrical: Quality
    overall: Quality
    device_mode: DeviceMode | None = None


def _values_present(section: BaseModel, *fields: str) -> bool:
    return all(getattr(section, name) is not None for name in fields)


class SerialSource(_WireBase):
    """Provenance for the Member A clockless serial envelope."""

    schema_version: Literal[2, 3]
    clock_quality: Literal["UNAVAILABLE"]
    gateway_received_at: AwareDatetime
    frame: str = Field(max_length=SERIAL_FRAME_MAX, pattern=r"^#CG TELEM [ -~]+$")


class Telemetry(_WireBase):
    """One logical device-state snapshot (MQTT telemetry payload)."""

    schema_version: Literal[1, 2]
    device_id: str
    boot_id: str
    seq: int
    captured_at: datetime | None
    uptime_ms: int
    run_id: str | None = None
    hardware_config_id: str
    firmware_version: str
    calibration_id: str | None = None
    thermal: ThermalSection
    environment: EnvironmentSection
    door: DoorSection
    electrical: ElectricalSection
    actuation: ActuationSection
    quality: QualitySection
    serial_source: SerialSource | None = None

    @field_validator("device_id", "boot_id", "hardware_config_id", "firmware_version")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identity/provenance strings must be non-empty")
        return value

    @field_validator("seq", "uptime_ms")
    @classmethod
    def _counters_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("seq and uptime_ms are non-negative counters")
        return value

    @model_validator(mode="after")
    def _clock_contract(self) -> "Telemetry":
        if self.schema_version == 1:
            if self.captured_at is None or self.serial_source is not None:
                raise ValueError("schema 1 requires device event time and carries no serial source")
            if "UNKNOWN" in (
                self.quality.thermal, self.quality.environment,
                self.quality.electrical, self.quality.overall,
            ):
                raise ValueError("UNKNOWN quality requires schema 2")
        elif self.captured_at is not None or self.serial_source is None:
            raise ValueError("schema 2 requires null device event time and serial provenance")
        else:
            self._verify_serial_identity(self.serial_source)
        return self

    def _verify_serial_identity(self, source: SerialSource) -> None:
        fields = {}
        for token in source.frame.removeprefix("#CG TELEM ").split(" "):
            key, _, value = token.partition("=")
            if not key or not value or key in fields:
                raise ValueError("serial provenance has malformed or repeated fields")
            fields[key] = value
        expected = {
            "schema": str(source.schema_version),
            "timestamp_utc": "UNAVAILABLE",
            "timestamp_utc_source": "DEVICE_HAS_NO_WALL_CLOCK",
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "run_id": "UNSET" if self.run_id is None else self.run_id,
            "firmware_version": self.firmware_version,
            "hardware_config_id": self.hardware_config_id,
            "calibration_id": (
                "UNRECORDED" if self.calibration_id is None else self.calibration_id
            ),
        }
        if self.run_id == "UNSET" or self.calibration_id == "UNRECORDED" or any(
            fields.get(key) != value for key, value in expected.items()
        ):
            raise ValueError("serial provenance disagrees with envelope identity or clock")
        for key, value in (("seq", self.seq), ("uptime_ms", self.uptime_ms)):
            token = fields.get(key, "")
            if not token.isdecimal() or int(token) != value:
                raise ValueError(f"serial provenance disagrees with envelope {key}")
        if not 0 < self.seq < 2**63 or self.uptime_ms >= 2**64:
            raise ValueError("serial sequence or uptime is outside its storage range")
        for section, values in serial_observation(fields).items():
            envelope = getattr(self, section)
            if any(getattr(envelope, key) != value for key, value in values.items()):
                raise ValueError(f"serial provenance disagrees with envelope {section}")

    @model_validator(mode="after")
    def _missing_values_need_quality(self) -> "Telemetry":
        # Only one direction is enforced: VALID claims every section value
        # is present. A DEGRADED/INVALID section may still carry values
        # (reduced trust is not the same as absence), and overall quality
        # is the firmware's synthesis, not a re-derivation here.
        checks = (
            (self.quality.thermal, _values_present(self.thermal, "t1", "t2", "t3")),
            (
                self.quality.environment,
                _values_present(self.environment, "t_air", "rh"),
            ),
            (
                self.quality.electrical,
                _values_present(
                    self.electrical, "voltage_v", "current_a", "power_w", "energy_wh"
                ),
            ),
        )
        for quality, complete in checks:
            if quality == "VALID" and not complete:
                raise ValueError(
                    "VALID section quality requires all section values present; "
                    "use None values with DEGRADED/INVALID quality instead"
                )
        return self

    @property
    def message_identity(self) -> tuple[str, str, int]:
        """Logical dedup identity: (device_id, boot_id, seq)."""
        return (self.device_id, self.boot_id, self.seq)

    @property
    def is_clockless(self) -> bool:
        """True when the message carries no device event clock."""
        return self.schema_version == 2 or self.captured_at is None

    @property
    def has_event_timestamp(self) -> bool:
        """True when a timezone-aware device event timestamp is present.

        This is existence/format validation only. A well-formed
        ``captured_at`` does NOT prove the device clock is synchronized to
        any trusted time source; synchronization must be established by
        separate authoritative evidence before cross-clock latency is
        computed (see :mod:`coldguard_backend.timing`, which fails closed
        with ``UNVERIFIED_CLOCK``). No UTC is ever derived from uptime.
        """
        return (
            self.schema_version == 1
            and self.captured_at is not None
            and self.captured_at.tzinfo is not None
        )



class CommandAction(_WireBase):
    """Requested single-branch action. No second branch exists."""

    cooling: CoolingState
    duty: float | None = None

    @field_validator("duty")
    @classmethod
    def _duty_in_unit_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("duty must be within [0.0, 1.0]")
        return value


class Command(_WireBase):
    """Backend command request. A fixture/request is not an execution."""

    schema_version: Literal[1]
    command_id: str
    device_id: str
    created_at: AwareDatetime
    expires_at: AwareDatetime
    controller_id: str
    policy_version: str
    reason_code: str
    action: CommandAction
    prediction_id: str | None = None
    run_id: str | None = None
    expected_twin_version: int | None = None

    @field_validator(
        "command_id",
        "device_id",
        "controller_id",
        "policy_version",
        "reason_code",
    )
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("command identity/provenance strings must be non-empty")
        return value

    @field_validator("expected_twin_version")
    @classmethod
    def _twin_version_non_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("expected_twin_version cannot be negative")
        return value

    @model_validator(mode="after")
    def _expiry_after_creation(self) -> "Command":
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be strictly after created_at")
        return self


# Device command-ACK verdicts (Doc 02 §32.1, closed set; Member A W06 handoff).
# An ACK is protocol evidence, never physical verification (Doc 02 §32.2).
AckStatus = Literal[
    "ACCEPTED",
    "REJECTED",
    "DUPLICATE_CANONICAL",
    "EXPIRED",
    "SAFETY_BLOCKED",
    "INVALID_STATE",
    "OUT_OF_RANGE",
]


class AppliedState(_WireBase):
    """Device-reported applied output. Reported truth, not a thermal claim."""

    cooling: CoolingState
    duty: float | None = None

    @field_validator("duty")
    @classmethod
    def _duty_in_unit_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("duty must be within [0.0, 1.0]")
        return value


class CommandAck(_WireBase):
    """Backend MQTT command-ACK envelope (Doc 02 §32.3 / §64).

    Carries the device verdict plus the interpretability fields from the
    Member A W06 contract (time_sync_state, expiry_evaluable, output_stage,
    fault_code, ack_seq, reapplied, canonical_status). ``device_id`` is the
    device's own identity; the consumer additionally proves topic agreement.
    ``applied`` is what the device reports it applied — an ACCEPTED ACK with
    applied ON is still not proof the chamber cooled.
    """

    schema_version: Literal[1]
    command_id: str
    device_id: str
    boot_id: str
    status: AckStatus
    reason_code: str
    uptime_ms: int
    applied: AppliedState | None = None
    desired: CommandAction | None = None
    device_mode: str | None = None
    ack_seq: int | None = None
    canonical_status: AckStatus | None = None
    reapplied: bool | None = None
    expiry_evaluable: bool | None = None
    time_sync_state: Literal["SYNCHRONIZED", "UNSYNCHRONIZED"] | None = None
    output_stage: Literal["ENABLED", "DISABLED"] | None = None
    fault_code: str | None = None
    ack_time: AwareDatetime | None = None

    @field_validator("command_id", "device_id", "boot_id", "reason_code")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ACK identity/reason strings must be non-empty")
        return value

    @field_validator("uptime_ms")
    @classmethod
    def _uptime_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("uptime_ms is a non-negative counter")
        return value

    @field_validator("ack_seq")
    @classmethod
    def _ack_seq_non_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("ack_seq is a non-negative counter")
        return value

    @model_validator(mode="after")
    def _duplicate_carries_canonical(self) -> "CommandAck":
        if self.status == "DUPLICATE_CANONICAL" and self.canonical_status is None:
            raise ValueError(
                "DUPLICATE_CANONICAL must carry canonical_status (the original verdict)"
            )
        return self
