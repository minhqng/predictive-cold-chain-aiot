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

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

WIRE_SCHEMA_VERSION = 1

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


class Telemetry(_WireBase):
    """One logical device-state snapshot (MQTT telemetry payload)."""

    schema_version: Literal[1]
    device_id: str
    boot_id: str
    seq: int
    captured_at: datetime
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
            raise ValueError("seq and uptime_ms are monotonic counters (>= 0)")
        return value

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
    created_at: datetime
    expires_at: datetime
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
