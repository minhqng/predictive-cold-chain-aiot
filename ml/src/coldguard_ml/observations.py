"""Canonical micro-sample identity, event-time semantics and row canon.

Implements the consumer-side rules of the W01 data dictionary
(``ml/data-dictionary-v0.md``):

* physical-sample identity is ``(device_id, boot_id, seq)`` (§1.2); timestamps
  are event-time evidence, never identity (§3, Doc ``01`` §18);
* duplicate deliveries of one identity are ONE normalized sample (QoS-1
  semantics, §1.2); a payload contradiction for one identity is an error;
* event-time ordering is canonical within ``(run_id, boot_id)``; sequence is
  strictly increasing within a boot (LRK-13); windows never join across boots;
* ``UNKNOWN`` door state and non-VALID quality phases are first-class values
  (§6, §9) — absent channels stay ``None`` and are never zero-filled (LRK-14);
* arrival time (``backend_received_at``) is arrival evidence only (§3).
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from .errors import DataContractError, IdentityContradictionError, OrderContradictionError

TIMEZONE_UTC = _dt.timezone.utc

QUALITY_VALUES: tuple[str, ...] = ("VALID", "DEGRADED", "INVALID")
DOOR_STATES: tuple[str, ...] = ("OPEN", "CLOSED", "UNKNOWN")
DEVICE_MODES: tuple[str, ...] = (
    "BOOT",
    "SELF_TEST",
    "ONLINE_NORMAL",
    "ONLINE_DEGRADED",
    "SAFE_LOCAL",
    "FAULT_LOCKOUT",
)
APPLIED_COOLING_STATES: tuple[str, ...] = ("ON", "OFF")

#: Sentinel alias for readability; values themselves must be tz-aware datetimes.
SampleIdentity = tuple[str, str, int]
TrajectoryKey = tuple[str, str]


def parse_event_time(value: Any, *, context: str) -> _dt.datetime:
    """Parse an RFC 3339 UTC instant (``...Z``) or accept a tz-aware datetime.

    Naive datetimes are rejected: Doc ``01`` §18 requires explicitly
    interpretable event time and forbids manufactured timestamp precision.
    """
    if isinstance(value, _dt.datetime):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise DataContractError(
                f"{context}: event time must be timezone-aware "
                "(RFC 3339 UTC / TIMESTAMPTZ semantics, data-dictionary-v0 §3)"
            )
        return value.astimezone(TIMEZONE_UTC)
    if isinstance(value, str):
        try:
            parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DataContractError(
                f"{context}: event time {value!r} is not an RFC 3339 instance"
            ) from exc
        return parsed.astimezone(TIMEZONE_UTC)
    raise DataContractError(
        f"{context}: event time must be an RFC 3339 string or tz-aware datetime, "
        f"got {type(value).__name__}"
    )


def event_time_to_rfc3339(moment: _dt.datetime) -> str:
    """Render a UTC instant deterministically (``...Z`` suffix, micro precision)."""
    normalized = moment.astimezone(TIMEZONE_UTC).replace(tzinfo=TIMEZONE_UTC)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Observation:
    """One normalized physical sample.

    Field semantics follow ``ml/data-dictionary-v0.md`` §§2–9. All value
    channels stay ``None`` when the section birthed them without data and the
    section quality says so; callers must never substitute 0 for absence.
    """

    device_id: str
    boot_id: str
    seq: int
    time: _dt.datetime  # tz-aware UTC event time (never inferred from seq)
    uptime_ms: int | None
    run_id: str

    # Thermal (DS18B20 x3), environment (BME280)
    t1_c: float | None
    t2_c: float | None
    t3_c: float | None
    t_air_c: float | None
    rh_pct: float | None
    door_state: str

    # Electrical (PZEM-017, cooling branch only), actuation (edge-applied)
    cooling_voltage_v: float | None
    cooling_current_a: float | None
    cooling_power_w: float | None
    cooling_energy_counter_wh: float | None
    applied_cooling: str
    applied_duty: float | None

    # Quality sections + device lifecycle mode
    thermal_quality: str
    environment_quality: str
    electrical_quality: str
    overall_quality: str
    device_mode: str | None

    # Provenance (Doc `00` §5.4)
    schema_version: int
    hardware_config_id: str
    firmware_version: str
    calibration_id: str | None
    backend_received_at: _dt.datetime | None = None  # arrival evidence only

    @property
    def identity(self) -> SampleIdentity:
        """Physical-sample identity ``(device_id, boot_id, seq)`` (§1.2)."""
        return (self.device_id, self.boot_id, self.seq)

    @property
    def trajectory_key(self) -> TrajectoryKey:
        """The boot-scoped trajectory this sample belongs to (§3 reboot rule)."""
        return (self.run_id, self.boot_id)

    @property
    def payload(self) -> tuple[Any, ...]:
        """Comparable content WITHOUT arrival-time evidence.

        QoS-1 re-deliveries arrive at different ``backend_received_at`` instants
        but describe the same physical sample (§1.2); the payload comparison
        therefore excludes arrival time only.
        """
        payload_fields = [f for f in _PAYLOAD_FIELDS]
        values = tuple(getattr(self, name) for name in payload_fields)
        # Replace datetimes with comparable RFC3339 strings so equality is exact
        # and independent of tzinfo object identity.
        return tuple(
            event_time_to_rfc3339(v) if isinstance(v, _dt.datetime) else v for v in values
        )


#: Fields compared when deciding whether two rows with one identity agree.
_PAYLOAD_FIELDS: tuple[str, ...] = (
    "time",
    "uptime_ms",
    "run_id",
    "t1_c",
    "t2_c",
    "t3_c",
    "t_air_c",
    "rh_pct",
    "door_state",
    "cooling_voltage_v",
    "cooling_current_a",
    "cooling_power_w",
    "cooling_energy_counter_wh",
    "applied_cooling",
    "applied_duty",
    "thermal_quality",
    "environment_quality",
    "electrical_quality",
    "overall_quality",
    "device_mode",
    "schema_version",
    "hardware_config_id",
    "firmware_version",
    "calibration_id",
)


def validate_observation(observation: Observation) -> None:
    """Raise ``DataContractError`` when a row violates the dictionary contract.

    Notable enforced rules (data-dictionary-v0):
    * identity fields non-empty, ``seq >= 0`` (§2);
    * tz-aware event time (§3);
    * enum domains for quality / door / applied state (§6, §8, §9);
    * non-negative electrical/thermal domains and duty ratio range (§7, §8);
    * ``rh_pct`` within 0..100 (§5);
    * VALID sections carry every value of that section; absence is legal only
      with DEGRADED/INVALID quality (§9, including the realized C-wire rule).
    """
    ctx = f"observation {_observation_id_repr(observation)}"
    for name in ("device_id", "boot_id", "run_id", "hardware_config_id", "firmware_version"):
        value = getattr(observation, name)
        if not isinstance(value, str) or not value.strip():
            raise DataContractError(f"{ctx}: required identity field {name!r} is empty")
    if not isinstance(observation.seq, int) or observation.seq < 0:
        raise DataContractError(f"{ctx}: seq must be an integer >= 0")
    parse_event_time(observation.time, context=ctx)

    for name in (
        "thermal_quality",
        "environment_quality",
        "electrical_quality",
        "overall_quality",
    ):
        if getattr(observation, name) not in QUALITY_VALUES:
            raise DataContractError(
                f"{ctx}: {name} must be one of {QUALITY_VALUES}, "
                f"got {getattr(observation, name)!r}"
            )
    if observation.door_state not in DOOR_STATES:
        raise DataContractError(
            f"{ctx}: door_state must be one of {DOOR_STATES}, got {observation.door_state!r}"
        )
    if observation.applied_cooling not in APPLIED_COOLING_STATES:
        raise DataContractError(
            f"{ctx}: applied_cooling must be one of {APPLIED_COOLING_STATES}, "
            f"got {observation.applied_cooling!r}"
        )
    if observation.device_mode is not None and observation.device_mode not in DEVICE_MODES:
        raise DataContractError(
            f"{ctx}: device_mode must be one of {DEVICE_MODES} or None, "
            f"got {observation.device_mode!r}"
        )

    _require_non_negative = (
        "cooling_voltage_v",
        "cooling_current_a",
        "cooling_power_w",
        "cooling_energy_counter_wh",
        "t1_c",
        "t2_c",
        "t3_c",
        "t_air_c",
    )
    for name in _require_non_negative:
        value = getattr(observation, name)
        if value is not None and value < 0:
            raise DataContractError(f"{ctx}: {name} must be >= 0, got {value!r}")
    if observation.rh_pct is not None and not 0.0 <= observation.rh_pct <= 100.0:
        raise DataContractError(f"{ctx}: rh_pct outside [0, 100]: {observation.rh_pct!r}")
    if observation.applied_duty is not None and not 0.0 <= observation.applied_duty <= 1.0:
        raise DataContractError(
            f"{ctx}: applied_duty outside validated range [0, 1]: {observation.applied_duty!r}"
        )

    _check_section(
        ctx,
        "thermal_quality",
        observation.thermal_quality,
        (("t1_c", observation.t1_c), ("t2_c", observation.t2_c), ("t3_c", observation.t3_c)),
    )
    _check_section(
        ctx,
        "environment_quality",
        observation.environment_quality,
        (("t_air_c", observation.t_air_c), ("rh_pct", observation.rh_pct)),
    )
    _check_section(
        ctx,
        "electrical_quality",
        observation.electrical_quality,
        (
            ("cooling_voltage_v", observation.cooling_voltage_v),
            ("cooling_current_a", observation.cooling_current_a),
            ("cooling_power_w", observation.cooling_power_w),
            ("cooling_energy_counter_wh", observation.cooling_energy_counter_wh),
        ),
    )


def _check_section(
    ctx: str, section: str, quality: str, values: tuple[tuple[str, Any], ...]
) -> None:
    if quality != "VALID":
        return  # DEGRADED/INVALID sections may carry partial values (reduced trust)
    absent = [name for name, value in values if value is None]
    if absent:
        raise DataContractError(
            f"{ctx}: VALID {section} section requires all values present "
            f"(absent: {', '.join(absent)}; data-dictionary-v0 §9 / C contract validator)"
        )


def _observation_id_repr(observation: Observation) -> str:
    return (
        f"{observation.run_id}/{observation.device_id}/{observation.boot_id}/seq"
        f"{observation.seq}"
    )


def validate_rows(rows: Iterable[Observation]) -> tuple[Observation, ...]:
    """Validate every row and return them as an ordered tuple (input order kept)."""
    validated = []
    for row in rows:
        validate_observation(row)
        validated.append(row)
    return tuple(validated)


def deduplicate_by_identity(rows: Iterable[Observation]) -> tuple[Observation, ...]:
    """Collapse duplicate deliveries of one physical sample (§1.2 / LRK-12).

    The same identity delivered multiple times must carry the same payload
    (QoS-1 re-delivery semantics; arrival time differs and is excluded from
    the comparison). Conflicting payloads for one identity raise
    ``IdentityContradictionError`` — they are two different physical claims
    and can never be silently merged.
    """
    by_identity: dict[SampleIdentity, list[Observation]] = {}
    for row in rows:
        validate_observation(row)
        identity = row.identity
        existing = by_identity.get(identity)
        if existing is None:
            by_identity[identity] = [row]
            continue
        for kept in existing:
            if kept.payload != row.payload:
                raise IdentityContradictionError(
                    f"identity {identity} carries conflicting payloads: "
                    f"first sample t={event_time_to_rfc3339(kept.time)} vs conflicting "
                    f"sample t={event_time_to_rfc3339(row.time)}; "
                    "duplicate deliveries must agree outside arrival time (data-dictionary-v0 §1.2)"
                )
        existing.append(row)
    # Deterministic canonical pick per identity: earliest arrival evidence (or
    # first seen when arrival is unknown).
    deduped: list[Observation] = []
    for identity in sorted(by_identity):
        deliveries = by_identity[identity]
        deliveries_with_arrival = [d for d in deliveries if d.backend_received_at is not None]
        if deliveries_with_arrival:
            chosen = min(deliveries_with_arrival, key=lambda d: d.backend_received_at)
        else:
            chosen = deliveries[0]
        deduped.append(replace(chosen, backend_received_at=chosen.backend_received_at))
    return tuple(deduped)


def canonical_order(rows: Iterable[Observation]) -> tuple[Observation, ...]:
    """Canonical event-time ordering per boot-scoped trajectory (§3 / LRK-13).

    Rows are grouped by ``(run_id, boot_id)`` and ordered by
    ``(time, seq)``. Within one boot the sequence must be strictly increasing
    along that order; a violation means corrupted time/sequence alignment
    (an A-side run-invalidation trigger per Doc ``01`` §33) and raises
    ``OrderContradictionError`` instead of being silently repaired.

    Output order: ``(run_id, boot_id)`` then ``(time, seq)``, so the same
    unduplicated sample set always yields the identical ordering regardless
    of arrival order.
    """
    deduped = deduplicate_by_identity(rows)
    by_trajectory: dict[TrajectoryKey, list[Observation]] = {}
    for row in deduped:
        by_trajectory.setdefault(row.trajectory_key, []).append(row)

    ordered: list[Observation] = []
    for trajectory in sorted(by_trajectory):
        bucket = sorted(
            by_trajectory[trajectory], key=lambda row: (row.time, row.seq, row.identity)
        )
        previous_time: _dt.datetime | None = None
        previous_seq: int | None = None
        for row in bucket:
            if previous_time is not None:
                if row.time < previous_time:
                    raise OrderContradictionError(
                        f"{trajectory}: event time {event_time_to_rfc3339(row.time)} precedes "
                        f"{event_time_to_rfc3339(previous_time)} after canonical sort — impossible"
                    )
                if row.seq <= previous_seq:
                    raise OrderContradictionError(
                        f"{trajectory}: seq {row.seq} does not strictly increase at "
                        f"t={event_time_to_rfc3339(row.time)}; corrupted time/sequence "
                        "alignment (data-dictionary-v0 §3, Doc `01` §33)"
                    )
            previous_time = row.time
            previous_seq = row.seq
            ordered.append(row)
    return tuple(ordered)


def rows_by_run(rows: Iterable[Observation]) -> dict[str, tuple[Observation, ...]]:
    """Group canonical rows by ``run_id`` (sorted output)."""
    grouped: dict[str, list[Observation]] = {}
    for row in rows:
        validate_observation(row)
        grouped.setdefault(row.run_id, []).append(row)
    return {run_id: tuple(items) for run_id, items in sorted(grouped.items())}


def trajectory_end(rows_by_run_map: Mapping[str, Iterable[Observation]]) -> dict[str, _dt.datetime]:
    """Last recorded event time per run (coverage evidence for labels)."""
    ends: dict[str, _dt.datetime] = {}
    for run_id, rows in rows_by_run_map.items():
        row_list = list(rows)
        if row_list:
            ends[run_id] = max(row.time for row in row_list)
    return dict(sorted(ends.items()))
