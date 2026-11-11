"""W09 deterministic baseline replay (B-W09-01 / B-W09-02).

Two baselines are implemented over a W04 normalized capture:

* ``B0_THRESHOLD`` — a stateless raw representative-temperature threshold
  comparator. It emits causal criterion detections, never commands.
* ``B1_HYSTERESIS`` — a stateful offline replay of the reactive hysteresis
  comparator used by Member D's pure ``_hysteresis`` policy. It is an
  analytical mirror, not the real controller.
* ``B1_PERSISTENCE_CANDIDATE`` — an explicitly exploratory extension with a
  reactive persistence/dwell parameter. No authoritative Controller A dwell
  has been frozen, so this mode is never labelled Controller A.

The module consumes W04 rows and W05 trusted-time semantics. It never parses a
wire format, never invents a threshold, never substitutes a missing value and
never issues an actuator command. Synthetic configurations are labelled; they
carry no physical authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Sequence

from .intake import (
    CHAMBER_AIR_POSITIONS,
    TIME_BOOT_SCOPED_UPTIME,
    TIME_EVENT_UTC,
    Capture,
    NormalizedRow,
)

W09_LAYER_VERSION = "coldguard-w09-deterministic-baselines-v1"
BASELINE_CONTRACT_VERSION = "coldguard-w09-baseline-contract-v1"

B0_THRESHOLD = "B0_THRESHOLD"
B1_HYSTERESIS = "B1_HYSTERESIS"
B1_PERSISTENCE_CANDIDATE = "B1_PERSISTENCE_CANDIDATE"
BASELINE_KINDS = (B0_THRESHOLD, B1_HYSTERESIS, B1_PERSISTENCE_CANDIDATE)

STATUS_FROZEN = "FROZEN"
STATUS_PROPOSED = "PROPOSED"
STATUS_NOT_FROZEN = "PARAMETERS_NOT_FROZEN"
STATUS_SYNTHETIC = "SYNTHETIC_ILLUSTRATIVE"
STATUS_EXPLORATORY = "EXPLORATORY_NOT_CONTROLLER_A"

REPRESENTATIVE_SINGLE = "SINGLE_PROBE"
REPRESENTATIVE_MEAN = "CHAMBER_AIR_MEAN"
REPRESENTATIVE_MAX = "CHAMBER_AIR_MAX"
REPRESENTATIVE_MODES = (
    REPRESENTATIVE_SINGLE,
    REPRESENTATIVE_MEAN,
    REPRESENTATIVE_MAX,
)

OPERATOR_GE = "GE"
OPERATOR_GT = "GT"
OPERATORS = (OPERATOR_GE, OPERATOR_GT)

INITIAL_ON = "ON"
INITIAL_OFF = "OFF"
INITIAL_UNAVAILABLE = "UNAVAILABLE"
INITIAL_STATES = (INITIAL_ON, INITIAL_OFF, INITIAL_UNAVAILABLE)

STATE_ON = "ON"
STATE_OFF = "OFF"
STATE_UNKNOWN = "UNKNOWN"
INTENT_ON = "ON"
INTENT_OFF = "OFF"
INTENT_HOLD = "HOLD"

SAMPLE_EVALUABLE = "EVALUABLE"
SAMPLE_INVALID_QUALITY = "INVALID_QUALITY"
SAMPLE_MISSING_VALUE = "MISSING_VALUE"
SAMPLE_NONFINITE = "NONFINITE_VALUE"
SAMPLE_STALE = "STALE_VALUE"
SAMPLE_UNKNOWN_FRESHNESS = "UNKNOWN_FRESHNESS"
SAMPLE_DUPLICATE = "DUPLICATE_DELIVERY"
SAMPLE_OUTSIDE_DOMAIN = "OUTSIDE_DECLARED_DOMAIN"
SAMPLE_NOT_EVALUABLE = "NOT_EVALUABLE"

TRANSITION_CRITERION = "REACTIVE_CRITERION_CROSSING"
TRANSITION_ON = "REACTIVE_ON_TRANSITION"
TRANSITION_OFF = "REACTIVE_OFF_TRANSITION"

CERTAINTY_EXACT = "EXACT_AT_SAMPLE"
CERTAINTY_INTERVAL = "WITHIN_SAMPLE_INTERVAL"
CERTAINTY_GAP = "WITHIN_GAP"
CERTAINTY_BEFORE = "BEFORE_OBSERVATION_START"

REFUSAL_NONE = "NONE"
REFUSAL_TIME_DOMAIN = "TIME_DOMAIN_MISMATCH"
REFUSAL_MIXED_BOOT = "MULTIPLE_BOOT_SESSIONS"
REFUSAL_TIME_REVERSED = "TIME_AXIS_NOT_NON_DECREASING"
REFUSAL_MISSING_TIME = "TIME_AXIS_MISSING"
REFUSAL_REPRESENTATIVE = "REPRESENTATIVE_NOT_QUALIFIED"
REFUSAL_NO_ROWS = "NO_ROWS"

EVALUABILITY_REFUSED = "REFUSED"
EVALUABILITY_DIAGNOSTIC = "EVALUABLE_DIAGNOSTIC"
EVALUABILITY_NOT_EVALUABLE = "NOT_EVALUABLE"

QUALITY_DOMAIN_THERMAL = "thermal"


class BaselineConfigError(ValueError):
    """A baseline configuration would invent or silently alter physical meaning."""


@dataclass(frozen=True)
class RepresentativeTemperature:
    """Explicit representative-temperature definition.

    Role qualification is enforced against the capture: a hot-side slot (T2)
    can never enter a chamber-air aggregate, even when a caller lists it.
    """

    name: str
    mode: str
    slots: tuple[str, ...]
    unit: str
    source: str
    freeze_status: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise BaselineConfigError("representative name must be non-empty")
        if self.mode not in REPRESENTATIVE_MODES:
            raise BaselineConfigError(
                f"representative mode must be one of {REPRESENTATIVE_MODES}"
            )
        if not self.slots or any(not slot.strip() for slot in self.slots):
            raise BaselineConfigError("representative slots must be non-empty")
        if len(set(self.slots)) != len(self.slots):
            raise BaselineConfigError("representative slots must be distinct")
        if self.mode == REPRESENTATIVE_SINGLE and len(self.slots) != 1:
            raise BaselineConfigError(
                "SINGLE_PROBE requires exactly one slot"
            )
        if self.unit != "degC":
            raise BaselineConfigError(
                "the canonical thermal unit is degC; refusing a wrong-unit "
                "representation"
            )
        if not self.source.strip():
            raise BaselineConfigError("representative source must be non-empty")
        if not self.freeze_status.strip():
            raise BaselineConfigError("representative freeze_status is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode,
            "slots": list(self.slots),
            "unit": self.unit,
            "source": self.source,
            "freeze_status": self.freeze_status,
        }


@dataclass(frozen=True)
class ThermalQualityPolicy:
    """Quality and freshness gates for a thermal representative."""

    accepted_row_quality: tuple[str, ...] = ("VALID",)
    accepted_probe_status: tuple[str, ...] = ("OK", "NONE")
    max_probe_age_s: float | None = None
    quality_domain: str = QUALITY_DOMAIN_THERMAL

    def __post_init__(self) -> None:
        if not self.accepted_row_quality:
            raise BaselineConfigError(
                "accepted_row_quality must not be empty; a baseline cannot "
                "silently accept every quality state"
            )
        for value in self.accepted_row_quality:
            if value not in ("VALID", "DEGRADED"):
                raise BaselineConfigError(
                    "accepted_row_quality may only name VALID or DEGRADED; "
                    "INVALID/UNKNOWN are never acceptable control truth"
                )
        if self.max_probe_age_s is not None:
            _require_positive_finite(
                "max_probe_age_s", self.max_probe_age_s
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted_row_quality": list(self.accepted_row_quality),
            "accepted_probe_status": list(self.accepted_probe_status),
            "max_probe_age_s": self.max_probe_age_s,
            "quality_domain": self.quality_domain,
        }


@dataclass(frozen=True)
class ThresholdConfig:
    representation: RepresentativeTemperature
    threshold_c: float | None
    operator: str
    time_domain: str
    quality: ThermalQualityPolicy
    threshold_source: str
    threshold_status: str
    max_continuity_gap_s: float
    run_id: str | None
    scenario_id: str | None
    policy_version: str = "not-applicable-stateless-b0"

    def __post_init__(self) -> None:
        if self.operator not in OPERATORS:
            raise BaselineConfigError(f"operator must be one of {OPERATORS}")
        if self.threshold_c is None:
            raise BaselineConfigError(
                "a B0 replay requires a numeric threshold_c; a missing value "
                "is PARAMETERS_NOT_FROZEN, not an executable baseline"
            )
        _require_finite("threshold_c", self.threshold_c)
        if not self.threshold_source.strip():
            raise BaselineConfigError("threshold_source must be explicit")
        if not self.threshold_status.strip():
            raise BaselineConfigError("threshold_status must be explicit")
        _require_positive_finite(
            "max_continuity_gap_s", self.max_continuity_gap_s
        )
        if self.time_domain not in (TIME_BOOT_SCOPED_UPTIME, TIME_EVENT_UTC):
            raise BaselineConfigError(
                "time_domain must be BOOT_SCOPED_UPTIME or EVENT_UTC"
            )
        if not (self.scenario_id or "").strip():
            raise BaselineConfigError(
                "scenario provenance is required; a baseline cannot be "
                "attached to an undeclared scenario"
            )
        if not self.policy_version.strip():
            raise BaselineConfigError("policy_version must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": B0_THRESHOLD,
            "representation": self.representation.to_dict(),
            "threshold_c": self.threshold_c,
            "operator": self.operator,
            "time_domain": self.time_domain,
            "quality": self.quality.to_dict(),
            "threshold_source": self.threshold_source,
            "threshold_status": self.threshold_status,
            "max_continuity_gap_s": self.max_continuity_gap_s,
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True)
class HysteresisConfig:
    representation: RepresentativeTemperature
    upper_on_c: float
    lower_off_c: float
    initial_state: str
    initial_state_source: str
    time_domain: str
    quality: ThermalQualityPolicy
    upper_lower_source: str
    freeze_status: str
    max_continuity_gap_s: float
    run_id: str | None
    scenario_id: str | None
    policy_version: str

    def __post_init__(self) -> None:
        _require_finite("upper_on_c", self.upper_on_c)
        _require_finite("lower_off_c", self.lower_off_c)
        if not self.upper_on_c > self.lower_off_c:
            raise BaselineConfigError(
                "upper_on_c must be strictly greater than lower_off_c"
            )
        if self.initial_state not in INITIAL_STATES:
            raise BaselineConfigError(
                f"initial_state must be one of {INITIAL_STATES}"
            )
        if not self.initial_state_source.strip():
            raise BaselineConfigError(
                "initial legal state requires explicit evidence/source"
            )
        if self.time_domain not in (TIME_BOOT_SCOPED_UPTIME, TIME_EVENT_UTC):
            raise BaselineConfigError(
                "time_domain must be BOOT_SCOPED_UPTIME or EVENT_UTC"
            )
        if not self.upper_lower_source.strip():
            raise BaselineConfigError("upper/lower boundary source is required")
        if not self.freeze_status.strip():
            raise BaselineConfigError("freeze_status is required")
        _require_positive_finite(
            "max_continuity_gap_s", self.max_continuity_gap_s
        )
        if not (self.scenario_id or "").strip():
            raise BaselineConfigError(
                "scenario provenance is required; a baseline cannot be "
                "attached to an undeclared scenario"
            )
        if not self.policy_version.strip():
            raise BaselineConfigError("policy_version must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": B1_HYSTERESIS,
            "representation": self.representation.to_dict(),
            "upper_on_c": self.upper_on_c,
            "lower_off_c": self.lower_off_c,
            "initial_state": self.initial_state,
            "initial_state_source": self.initial_state_source,
            "time_domain": self.time_domain,
            "quality": self.quality.to_dict(),
            "upper_lower_source": self.upper_lower_source,
            "freeze_status": self.freeze_status,
            "max_continuity_gap_s": self.max_continuity_gap_s,
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True)
class PersistenceCandidateConfig:
    """Exploratory reactive persistence; never the frozen Controller A dwell."""

    required_s: float
    source: str
    status: str = STATUS_EXPLORATORY

    def __post_init__(self) -> None:
        _require_positive_finite("required_s", self.required_s)
        if not self.source.strip():
            raise BaselineConfigError("persistence source must be non-empty")
        if self.status != STATUS_EXPLORATORY:
            raise BaselineConfigError(
                "reactive persistence has no frozen authority; only "
                "EXPLORATORY_NOT_CONTROLLER_A is accepted"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": B1_PERSISTENCE_CANDIDATE,
            "required_s": self.required_s,
            "source": self.source,
            "status": self.status,
        }


@dataclass(frozen=True)
class ReplaySample:
    index: int
    sample_id: str
    seq: int
    source_line_index: int | None
    time_s: float | None
    representative_c: float | None
    sample_status: str
    criterion_state: bool | None
    decision: str
    prior_state: str | None
    new_state: str | None
    transition: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "sample_id": self.sample_id,
            "seq": self.seq,
            "source_line_index": self.source_line_index,
            "time_s": self.time_s,
            "representative_c": self.representative_c,
            "sample_status": self.sample_status,
            "criterion_state": self.criterion_state,
            "decision": self.decision,
            "prior_state": self.prior_state,
            "new_state": self.new_state,
            "transition": self.transition,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BaselineTransition:
    event_type: str
    event_id: str
    time_s: float
    sample_index: int
    sample_id: str
    prior_state: str | None
    new_state: str
    crossing_interval_start_s: float | None
    crossing_interval_end_s: float
    time_certainty: str
    reason: str
    crossing_time_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "time_s": self.time_s,
            "detection_time_s": self.time_s,
            "crossing_time_s": self.crossing_time_s,
            "sample_index": self.sample_index,
            "sample_id": self.sample_id,
            "prior_state": self.prior_state,
            "new_state": self.new_state,
            "crossing_interval_start_s": self.crossing_interval_start_s,
            "crossing_interval_end_s": self.crossing_interval_end_s,
            "time_certainty": self.time_certainty,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RefusedInterval:
    start_s: float | None
    end_s: float | None
    reason: str
    sample_indices: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_s": self.start_s,
            "end_s": self.end_s,
            "reason": self.reason,
            "sample_indices": list(self.sample_indices),
        }


@dataclass(frozen=True)
class ReplayCoverage:
    observation_duration_s: float | None
    evaluable_duration_s: float | None
    unknown_duration_s: float | None
    evaluable_fraction: float | None
    sample_count: int
    evaluable_sample_count: int
    unknown_sample_count: int
    duplicate_sample_count: int
    gap_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_duration_s": self.observation_duration_s,
            "evaluable_duration_s": self.evaluable_duration_s,
            "unknown_duration_s": self.unknown_duration_s,
            "evaluable_fraction": self.evaluable_fraction,
            "sample_count": self.sample_count,
            "evaluable_sample_count": self.evaluable_sample_count,
            "unknown_sample_count": self.unknown_sample_count,
            "duplicate_sample_count": self.duplicate_sample_count,
            "gap_count": self.gap_count,
        }


@dataclass(frozen=True)
class ReplayResult:
    baseline: str
    config_version: str
    config_sha256: str
    source_path: str
    source_sha256: str
    run_id: str | None
    scenario_id: str | None
    boot_sessions: int
    time_domain: str | None
    parameter_status: str
    parameter_source: str
    evaluability: str
    refusal_reason: str
    samples: tuple[ReplaySample, ...]
    transitions: tuple[BaselineTransition, ...]
    refused_intervals: tuple[RefusedInterval, ...]
    coverage: ReplayCoverage
    persistence: dict[str, Any] | None
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": self.baseline,
            "config_version": self.config_version,
            "config_sha256": self.config_sha256,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "boot_sessions": self.boot_sessions,
            "time_domain": self.time_domain,
            "parameter_status": self.parameter_status,
            "parameter_source": self.parameter_source,
            "evaluability": self.evaluability,
            "refusal_reason": self.refusal_reason,
            "samples": [sample.to_dict() for sample in self.samples],
            "transitions": [
                transition.to_dict() for transition in self.transitions
            ],
            "refused_intervals": [
                interval.to_dict() for interval in self.refused_intervals
            ],
            "coverage": self.coverage.to_dict(),
            "persistence": self.persistence,
            "limitations": list(self.limitations),
        }

    def criterion_crossings(self) -> tuple[BaselineTransition, ...]:
        return tuple(
            item
            for item in self.transitions
            if item.event_type == TRANSITION_CRITERION
        )

    def on_transitions(self) -> tuple[BaselineTransition, ...]:
        return tuple(
            item for item in self.transitions if item.event_type == TRANSITION_ON
        )

    def off_transitions(self) -> tuple[BaselineTransition, ...]:
        return tuple(
            item for item in self.transitions if item.event_type == TRANSITION_OFF
        )


def _require_finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BaselineConfigError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise BaselineConfigError(f"{name} must be a finite number")
    return number


def _require_positive_finite(name: str, value: object) -> float:
    number = _require_finite(name, value)
    if number <= 0:
        raise BaselineConfigError(f"{name} must be positive")
    return number


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def config_sha256(config: ThresholdConfig | HysteresisConfig) -> str:
    return hashlib.sha256(_canonical_json(config.to_dict()).encode("utf-8")).hexdigest()


def _event_id(
    source_sha256: str,
    baseline: str,
    event_type: str,
    sample_id: str,
    sample_index: int,
) -> str:
    payload = "\0".join(
        (source_sha256, baseline, event_type, sample_id, str(sample_index))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _row_quality(row: NormalizedRow, domain: str) -> str:
    return dict(row.quality).get(domain, "UNKNOWN")


def _sample_id(row: NormalizedRow) -> str:
    if row.dedup_key:
        return "|".join(str(part) for part in row.dedup_key)
    return f"seq={row.seq}|line={row.source_line_index}"


def _session_key(row: NormalizedRow, capture: Capture) -> tuple[str | None, ...]:
    if row.boot_id is not None:
        return ("session", row.device_id, row.boot_id)
    if row.run_id is not None:
        return ("run", row.run_id)
    return ("source", capture.source.sha256)


def validate_representation(
    capture: Capture, representation: RepresentativeTemperature
) -> None:
    """Refuse unknown roles and any hot-side slot in a chamber-air aggregate."""
    for slot in representation.slots:
        try:
            role = capture.sensor(slot)
        except KeyError as exc:
            raise BaselineConfigError(
                f"slot {slot!r} has no physical role record; a role-qualified "
                "thermal representative is required"
            ) from exc
        if role.physical_position not in CHAMBER_AIR_POSITIONS:
            raise BaselineConfigError(
                f"slot {slot!r} is {role.physical_position!r}, not chamber air; "
                "TEC hot-side T2 must never enter a chamber-air baseline"
            )
        if role.in_chamber_air_aggregate is not True:
            raise BaselineConfigError(
                f"slot {slot!r} is excluded from the chamber-air aggregate"
                + (
                    f" ({role.exclusion_reason})"
                    if role.exclusion_reason
                    else ""
                )
            )
        if role.role_conflict is not None:
            raise BaselineConfigError(
                f"slot {slot!r} has a role conflict: {role.role_conflict}"
            )


def representative_value(
    capture: Capture,
    row: NormalizedRow,
    representation: RepresentativeTemperature,
) -> float | None:
    validate_representation(capture, representation)
    values: list[float] = []
    for slot in representation.slots:
        try:
            reading = row.probe(slot)
        except KeyError:
            return None
        if reading.value_c is None:
            return None
        if isinstance(reading.value_c, bool) or not isinstance(
            reading.value_c, (int, float)
        ):
            return None
        if not math.isfinite(float(reading.value_c)):
            return None
        values.append(float(reading.value_c))
    if representation.mode == REPRESENTATIVE_SINGLE:
        return values[0]
    if representation.mode == REPRESENTATIVE_MEAN:
        return sum(values) / len(values)
    return max(values)


def controller_a_hysteresis_intent(
    t: float | None,
    applied: str | None,
    upper_on_c: float,
    lower_off_c: float,
) -> str:
    """Exact comparator mirrored from D's ``_hysteresis``.

    ``applied`` is the prior legal state. ``None`` means unavailable: the
    function can establish ON at the upper boundary but never invents OFF.
    """
    if t is None:
        return INTENT_HOLD
    if t >= upper_on_c:
        return INTENT_ON
    if t <= lower_off_c:
        if applied == STATE_ON:
            return INTENT_OFF
        return INTENT_HOLD
    return INTENT_HOLD


@dataclass(frozen=True)
class _PreparedRow:
    index: int
    row: NormalizedRow
    time_s: float
    sample_id: str
    sample_status: str
    representative_c: float | None
    detail: str


@dataclass(frozen=True)
class _Trajectory:
    rows: tuple[_PreparedRow, ...]
    boot_sessions: int
    time_domain: str
    refusal_reason: str
    refusal_detail: str


def _prepare_trajectory(
    capture: Capture,
    representation: RepresentativeTemperature,
    quality: ThermalQualityPolicy,
    time_domain: str,
    max_continuity_gap_s: float,
) -> _Trajectory:
    rows = capture.rows
    if not rows:
        return _Trajectory((), 0, capture.time.domain, REFUSAL_NO_ROWS, "no rows")
    if capture.time.domain != time_domain:
        return _Trajectory(
            (),
            0,
            capture.time.domain,
            REFUSAL_TIME_DOMAIN,
            f"capture domain {capture.time.domain!r} != configured {time_domain!r}",
        )
    sessions = {_session_key(row, capture) for row in rows}
    if len(sessions) > 1:
        return _Trajectory(
            (),
            len(sessions),
            capture.time.domain,
            REFUSAL_MIXED_BOOT,
            "a capture spanning multiple boot/device sessions is not one "
            "continuous baseline trajectory",
        )
    if time_domain == TIME_BOOT_SCOPED_UPTIME:
        raw = [row.device_ms for row in rows]
        if any(value is None for value in raw):
            return _Trajectory(
                (),
                1,
                capture.time.domain,
                REFUSAL_MISSING_TIME,
                "boot uptime is missing on at least one row",
            )
        numeric = [float(value) for value in raw if value is not None]
        reference = numeric[0]
        times = [round((value - reference) / 1000.0, 9) for value in numeric]
    elif time_domain == TIME_EVENT_UTC:
        stamps = [row.event_time_utc for row in rows]
        if any(stamp is None for stamp in stamps):
            return _Trajectory(
                (),
                1,
                capture.time.domain,
                REFUSAL_MISSING_TIME,
                "event UTC is missing on at least one row",
            )
        known = [stamp for stamp in stamps if stamp is not None]
        reference_stamp = known[0]
        times = [
            round((stamp - reference_stamp).total_seconds(), 6)
            for stamp in known
        ]
    else:
        return _Trajectory(
            (),
            len(sessions),
            capture.time.domain,
            REFUSAL_TIME_DOMAIN,
            "capture has no trusted event-time or boot-uptime axis",
        )
    if any(
        right < left for left, right in zip(times, times[1:])
    ):
        return _Trajectory(
            (),
            1,
            capture.time.domain,
            REFUSAL_TIME_REVERSED,
            "source time is not non-decreasing; a trajectory cannot be rebuilt "
            "by silently sorting it",
        )
    prepared: list[_PreparedRow] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        sample_id = _sample_id(row)
        if sample_id in seen:
            prepared.append(
                _PreparedRow(
                    index=index,
                    row=row,
                    time_s=times[index],
                    sample_id=sample_id,
                    sample_status=SAMPLE_DUPLICATE,
                    representative_c=None,
                    detail="repeated delivery of one sample identity",
                )
            )
            continue
        seen.add(sample_id)
        quality_state = _row_quality(row, quality.quality_domain)
        if quality_state not in quality.accepted_row_quality:
            prepared.append(
                _PreparedRow(
                    index=index,
                    row=row,
                    time_s=times[index],
                    sample_id=sample_id,
                    sample_status=SAMPLE_INVALID_QUALITY,
                    representative_c=None,
                    detail=f"{quality.quality_domain} quality {quality_state!r}",
                )
            )
            continue
        stale = False
        unknown_freshness = False
        for slot in representation.slots:
            try:
                reading = row.probe(slot)
            except KeyError:
                prep_status = SAMPLE_MISSING_VALUE
                detail = f"slot {slot!r} is missing"
                break
            status = reading.status
            status_token = "NONE" if status is None else status
            if status_token not in quality.accepted_probe_status:
                prep_status = SAMPLE_INVALID_QUALITY
                detail = f"slot {slot!r} probe status {status_token!r}"
                break
            if reading.value_c is None:
                prep_status = SAMPLE_MISSING_VALUE
                detail = f"slot {slot!r} carries no numeric value"
                break
            if isinstance(reading.value_c, bool) or not isinstance(
                reading.value_c, (int, float)
            ):
                prep_status = SAMPLE_NONFINITE
                detail = f"slot {slot!r} is not a real number"
                break
            if not math.isfinite(float(reading.value_c)):
                prep_status = SAMPLE_NONFINITE
                detail = f"slot {slot!r} is not finite"
                break
            if quality.max_probe_age_s is not None:
                if reading.age_ms is None:
                    unknown_freshness = True
                elif reading.age_ms / 1000.0 > quality.max_probe_age_s:
                    stale = True
        else:
            prep_status = SAMPLE_EVALUABLE
            detail = "all required probes are valid"
        if stale:
            prep_status = SAMPLE_STALE
            detail = "probe age exceeds the configured freshness bound"
        elif unknown_freshness and quality.max_probe_age_s is not None:
            prep_status = SAMPLE_UNKNOWN_FRESHNESS
            detail = "probe age is unavailable while a freshness bound is required"
        value = (
            representative_value(capture, row, representation)
            if prep_status == SAMPLE_EVALUABLE
            else None
        )
        if prep_status == SAMPLE_EVALUABLE and value is None:
            prep_status = SAMPLE_MISSING_VALUE
            detail = "representative value is undefined"
        prepared.append(
            _PreparedRow(
                index=index,
                row=row,
                time_s=times[index],
                sample_id=sample_id,
                sample_status=prep_status,
                representative_c=value,
                detail=detail,
            )
        )
    return _Trajectory(
        tuple(prepared), 1, capture.time.domain, REFUSAL_NONE, ""
    )


def _coverage(
    prepared: Sequence[_PreparedRow],
    *,
    max_continuity_gap_s: float,
) -> ReplayCoverage:
    times = [item.time_s for item in prepared]
    observation = (
        round(times[-1] - times[0], 9) if len(times) >= 2 else 0.0
    )
    evaluable_duration = 0.0
    unknown_duration = 0.0
    gaps = 0
    for left, right in zip(prepared, prepared[1:]):
        delta = right.time_s - left.time_s
        if delta > max_continuity_gap_s:
            gaps += 1
        if (
            left.sample_status == SAMPLE_EVALUABLE
            and right.sample_status == SAMPLE_EVALUABLE
            and delta <= max_continuity_gap_s
        ):
            evaluable_duration += delta
        else:
            unknown_duration += delta
    evaluable = round(evaluable_duration, 9)
    unknown = round(unknown_duration, 9)
    fraction = (
        round(evaluable / observation, 9) if observation > 0 else None
    )
    return ReplayCoverage(
        observation_duration_s=round(observation, 9) if len(times) >= 2 else 0.0,
        evaluable_duration_s=evaluable,
        unknown_duration_s=unknown,
        evaluable_fraction=fraction,
        sample_count=len(prepared),
        evaluable_sample_count=sum(
            1 for item in prepared if item.sample_status == SAMPLE_EVALUABLE
        ),
        unknown_sample_count=sum(
            1
            for item in prepared
            if item.sample_status
            not in (SAMPLE_EVALUABLE, SAMPLE_DUPLICATE)
        ),
        duplicate_sample_count=sum(
            1 for item in prepared if item.sample_status == SAMPLE_DUPLICATE
        ),
        gap_count=gaps,
    )


def _gap_intervals(
    prepared: Sequence[_PreparedRow], max_continuity_gap_s: float
) -> tuple[RefusedInterval, ...]:
    intervals: list[RefusedInterval] = []
    for left, right in zip(prepared, prepared[1:]):
        if right.time_s - left.time_s > max_continuity_gap_s:
            intervals.append(
                RefusedInterval(
                    start_s=left.time_s,
                    end_s=right.time_s,
                    reason="CONTINUITY_GAP_EXCEEDED",
                    sample_indices=(left.index, right.index),
                )
            )
    return tuple(intervals)


def _refused_intervals(
    prepared: Sequence[_PreparedRow],
) -> tuple[RefusedInterval, ...]:
    intervals: list[RefusedInterval] = []
    current_reason: str | None = None
    current_indices: list[int] = []
    current_start: float | None = None
    current_end: float | None = None
    for item in prepared:
        bad = item.sample_status not in (SAMPLE_EVALUABLE, SAMPLE_DUPLICATE)
        if bad:
            if current_reason is None:
                current_reason = item.sample_status
                current_start = item.time_s
            elif current_reason != item.sample_status:
                intervals.append(
                    RefusedInterval(
                        start_s=current_start,
                        end_s=current_end,
                        reason=current_reason,
                        sample_indices=tuple(current_indices),
                    )
                )
                current_reason = item.sample_status
                current_start = item.time_s
                current_indices = []
            current_indices.append(item.index)
            current_end = item.time_s
        else:
            if current_reason is not None:
                intervals.append(
                    RefusedInterval(
                        start_s=current_start,
                        end_s=current_end,
                        reason=current_reason,
                        sample_indices=tuple(current_indices),
                    )
                )
                current_reason = None
                current_indices = []
                current_start = None
                current_end = None
    if current_reason is not None:
        intervals.append(
            RefusedInterval(
                start_s=current_start,
                end_s=current_end,
                reason=current_reason,
                sample_indices=tuple(current_indices),
            )
        )
    return tuple(intervals)


def _result_limitations(baseline: str) -> tuple[str, ...]:
    common = (
        "A baseline replay is a criterion detection, not an actuator command.",
        "Only W04 quality-qualified rows are evaluated; missing values are "
        "never substituted.",
        "A crossing between samples is an interval, not a fabricated instant.",
    )
    if baseline == B1_PERSISTENCE_CANDIDATE:
        return common + (
            "Reactive persistence is exploratory; no frozen Controller A "
            "dwell exists and D's predictive persistence parameter was not "
            "reused.",
        )
    if baseline == B1_HYSTERESIS:
        return common + (
            "The replay mirrors D's pure hysteresis comparator only; it does "
            "not implement fault, SAFE_LOCAL or device-mode priority.",
        )
    return common


def _build_result(
    *,
    baseline: str,
    config_version: str,
    config_hash: str,
    capture: Capture,
    trajectory: _Trajectory,
    parameter_status: str,
    parameter_source: str,
    run_id: str | None,
    scenario_id: str | None,
    samples: Sequence[ReplaySample],
    transitions: Sequence[BaselineTransition],
    max_continuity_gap_s: float,
    persistence: dict[str, Any] | None = None,
) -> ReplayResult:
    prepared = trajectory.rows
    evaluability = (
        EVALUABILITY_REFUSED
        if trajectory.refusal_reason != REFUSAL_NONE
        else (
            EVALUABILITY_DIAGNOSTIC
            if any(
                item.sample_status == SAMPLE_EVALUABLE for item in prepared
            )
            else EVALUABILITY_NOT_EVALUABLE
        )
    )
    return ReplayResult(
        baseline=baseline,
        config_version=config_version,
        config_sha256=config_hash,
        source_path=capture.source.path,
        source_sha256=capture.source.sha256,
        run_id=run_id,
        scenario_id=scenario_id,
        boot_sessions=trajectory.boot_sessions,
        time_domain=trajectory.time_domain,
        parameter_status=parameter_status,
        parameter_source=parameter_source,
        evaluability=evaluability,
        refusal_reason=trajectory.refusal_reason,
        samples=tuple(samples),
        transitions=tuple(transitions),
        refused_intervals=_gap_intervals(
            prepared, max_continuity_gap_s
        )
        + _refused_intervals(prepared),
        coverage=_coverage(
            prepared,
            max_continuity_gap_s=max_continuity_gap_s,
        ),
        persistence=persistence,
        limitations=_result_limitations(baseline),
    )


def evaluate_b0(capture: Capture, config: ThresholdConfig) -> ReplayResult:
    """Stateless causal threshold replay over W04 rows."""
    validate_representation(capture, config.representation)
    trajectory = _prepare_trajectory(
        capture,
        config.representation,
        config.quality,
        config.time_domain,
        config.max_continuity_gap_s,
    )
    config_hash = config_sha256(config)
    if trajectory.refusal_reason != REFUSAL_NONE:
        return _build_result(
            baseline=B0_THRESHOLD,
            config_version=BASELINE_CONTRACT_VERSION,
            config_hash=config_hash,
            capture=capture,
            trajectory=trajectory,
            parameter_status=config.threshold_status,
            parameter_source=config.threshold_source,
            run_id=config.run_id,
            scenario_id=config.scenario_id,
            samples=(),
            transitions=(),
            max_continuity_gap_s=config.max_continuity_gap_s,
        )
    samples: list[ReplaySample] = []
    transitions: list[BaselineTransition] = []
    last_known_state: bool | None = None
    last_known_time: float | None = None
    last_known_index: int | None = None
    invalid_since_last_known = False
    for item in trajectory.rows:
        if item.sample_status == SAMPLE_DUPLICATE:
            samples.append(
                ReplaySample(
                    index=item.index,
                    sample_id=item.sample_id,
                    seq=item.row.seq,
                    source_line_index=item.row.source_line_index,
                    time_s=item.time_s,
                    representative_c=None,
                    sample_status=item.sample_status,
                    criterion_state=None,
                    decision=SAMPLE_DUPLICATE,
                    prior_state=None,
                    new_state=None,
                    transition=None,
                    reason="repeated delivery ignored; no extra crossing",
                )
            )
            continue
        if item.sample_status != SAMPLE_EVALUABLE:
            invalid_since_last_known = True
            samples.append(
                ReplaySample(
                    index=item.index,
                    sample_id=item.sample_id,
                    seq=item.row.seq,
                    source_line_index=item.row.source_line_index,
                    time_s=item.time_s,
                    representative_c=item.representative_c,
                    sample_status=item.sample_status,
                    criterion_state=None,
                    decision=SAMPLE_NOT_EVALUABLE,
                    prior_state=None,
                    new_state=None,
                    transition=None,
                    reason=item.detail,
                )
            )
            continue
        value = item.representative_c
        assert value is not None
        threshold = config.threshold_c
        assert threshold is not None
        satisfied = (
            value >= threshold
            if config.operator == OPERATOR_GE
            else value > threshold
        )
        transition: str | None = None
        certainty = CERTAINTY_INTERVAL
        interval_start = last_known_time
        if satisfied and last_known_state is not True:
            transition = TRANSITION_CRITERION
            if last_known_time is None and last_known_index is None:
                certainty = CERTAINTY_BEFORE
                interval_start = None
            elif invalid_since_last_known:
                certainty = CERTAINTY_GAP
            elif value == threshold and config.operator == OPERATOR_GE:
                certainty = CERTAINTY_EXACT
            elif (
                last_known_time is not None
                and item.time_s - last_known_time
                > config.max_continuity_gap_s
            ):
                certainty = CERTAINTY_GAP
            transitions.append(
                BaselineTransition(
                    event_type=TRANSITION_CRITERION,
                    event_id=_event_id(
                        capture.source.sha256,
                        B0_THRESHOLD,
                        TRANSITION_CRITERION,
                        item.sample_id,
                        item.index,
                    ),
                    time_s=item.time_s,
                    sample_index=item.index,
                    sample_id=item.sample_id,
                    prior_state=None,
                    new_state="SATISFIED",
                    crossing_interval_start_s=interval_start,
                    crossing_interval_end_s=item.time_s,
                    time_certainty=certainty,
                    reason=(
                        f"{config.operator} threshold {threshold} at "
                        f"representative {value}"
                    ),
                    crossing_time_s=(
                        item.time_s
                        if certainty == CERTAINTY_EXACT
                        else None
                    ),
                )
            )
        samples.append(
            ReplaySample(
                index=item.index,
                sample_id=item.sample_id,
                seq=item.row.seq,
                source_line_index=item.row.source_line_index,
                time_s=item.time_s,
                representative_c=value,
                sample_status=item.sample_status,
                criterion_state=satisfied,
                decision=(
                    "CRITERION_SATISFIED" if satisfied else "CRITERION_NOT_MET"
                ),
                prior_state=(
                    None
                    if last_known_state is None
                    else ("SATISFIED" if last_known_state else "NOT_MET")
                ),
                new_state="SATISFIED" if satisfied else "NOT_MET",
                transition=transition,
                reason=(
                    "criterion satisfied"
                    if satisfied
                    else "criterion not satisfied"
                ),
            )
        )
        last_known_state = satisfied
        last_known_time = item.time_s
        last_known_index = item.index
        invalid_since_last_known = False
    return _build_result(
        baseline=B0_THRESHOLD,
        config_version=BASELINE_CONTRACT_VERSION,
        config_hash=config_hash,
        capture=capture,
        trajectory=trajectory,
        parameter_status=config.threshold_status,
        parameter_source=config.threshold_source,
        run_id=config.run_id,
        scenario_id=config.scenario_id,
        samples=samples,
        transitions=transitions,
        max_continuity_gap_s=config.max_continuity_gap_s,
    )


def evaluate_b1(
    capture: Capture,
    config: HysteresisConfig,
    *,
    persistence: PersistenceCandidateConfig | None = None,
) -> ReplayResult:
    """Stateful offline replay of D's reactive hysteresis comparator."""
    validate_representation(capture, config.representation)
    trajectory = _prepare_trajectory(
        capture,
        config.representation,
        config.quality,
        config.time_domain,
        config.max_continuity_gap_s,
    )
    baseline = (
        B1_PERSISTENCE_CANDIDATE if persistence is not None else B1_HYSTERESIS
    )
    config_hash = config_sha256(config)
    if trajectory.refusal_reason != REFUSAL_NONE:
        return _build_result(
            baseline=baseline,
            config_version=BASELINE_CONTRACT_VERSION,
            config_hash=config_hash,
            capture=capture,
            trajectory=trajectory,
            parameter_status=(
                persistence.status
                if persistence is not None
                else config.freeze_status
            ),
            parameter_source=(
                persistence.source
                if persistence is not None
                else config.upper_lower_source
            ),
            run_id=config.run_id,
            scenario_id=config.scenario_id,
            samples=(),
            transitions=(),
            max_continuity_gap_s=config.max_continuity_gap_s,
            persistence=(
                None if persistence is None else persistence.to_dict()
            ),
        )
    samples: list[ReplaySample] = []
    transitions: list[BaselineTransition] = []
    state: str | None = (
        None if config.initial_state == INITIAL_UNAVAILABLE else config.initial_state
    )
    pending_on_start: float | None = None
    persistence_info: dict[str, Any] | None = None
    if persistence is not None:
        persistence_info = {
            **persistence.to_dict(),
            "accumulated_continuous_s": 0.0,
            "reset_events": 0,
            "met_count": 0,
        }
    previous_time: float | None = None
    for item in trajectory.rows:
        if item.sample_status == SAMPLE_DUPLICATE:
            samples.append(
                ReplaySample(
                    index=item.index,
                    sample_id=item.sample_id,
                    seq=item.row.seq,
                    source_line_index=item.row.source_line_index,
                    time_s=item.time_s,
                    representative_c=None,
                    sample_status=item.sample_status,
                    criterion_state=None,
                    decision=SAMPLE_DUPLICATE,
                    prior_state=state,
                    new_state=state,
                    transition=None,
                    reason="repeated delivery ignored; state is not re-evaluated",
                )
            )
            continue
        if item.sample_status != SAMPLE_EVALUABLE:
            if persistence_info is not None:
                persistence_info["reset_events"] += 1
                persistence_info["accumulated_continuous_s"] = 0.0
            pending_on_start = None
            samples.append(
                ReplaySample(
                    index=item.index,
                    sample_id=item.sample_id,
                    seq=item.row.seq,
                    source_line_index=item.row.source_line_index,
                    time_s=item.time_s,
                    representative_c=item.representative_c,
                    sample_status=item.sample_status,
                    criterion_state=None,
                    decision=SAMPLE_NOT_EVALUABLE,
                    prior_state=state,
                    new_state=state,
                    transition=None,
                    reason=item.detail,
                )
            )
            previous_time = item.time_s
            continue
        value = item.representative_c
        assert value is not None
        gap = (
            previous_time is not None
            and item.time_s - previous_time > config.max_continuity_gap_s
        )
        if gap and persistence_info is not None:
            persistence_info["reset_events"] += 1
            persistence_info["accumulated_continuous_s"] = 0.0
            pending_on_start = None
        prior_state = state
        transition: str | None = None
        reason: str
        if persistence_info is not None and value >= config.upper_on_c:
            if pending_on_start is None:
                pending_on_start = item.time_s
            elapsed = item.time_s - pending_on_start
            persistence_info["accumulated_continuous_s"] = round(elapsed, 9)
            if elapsed >= persistence.required_s and state != STATE_ON:
                state = STATE_ON
                transition = TRANSITION_ON
                persistence_info["met_count"] += 1
                reason = (
                    f"T={value} >= {config.upper_on_c} for {elapsed} s "
                    f">= exploratory persistence {persistence.required_s} s"
                )
            elif state == STATE_ON:
                reason = "already ON; persistence does not create a second transition"
            else:
                reason = (
                    f"T={value} >= upper but persistence {elapsed} s < "
                    f"{persistence.required_s} s"
                )
        else:
            if persistence_info is not None and value < config.upper_on_c:
                if pending_on_start is not None:
                    persistence_info["reset_events"] += 1
                pending_on_start = None
                persistence_info["accumulated_continuous_s"] = 0.0
            intent = controller_a_hysteresis_intent(
                value, state, config.upper_on_c, config.lower_off_c
            )
            if intent == INTENT_ON and state != STATE_ON:
                state = STATE_ON
                transition = TRANSITION_ON
                reason = f"T={value} >= upper boundary {config.upper_on_c}"
            elif intent == INTENT_OFF and state == STATE_ON:
                state = STATE_OFF
                transition = TRANSITION_OFF
                reason = f"T={value} <= lower boundary {config.lower_off_c}"
            elif value >= config.upper_on_c:
                reason = "already ON at the upper boundary"
            elif value <= config.lower_off_c:
                reason = (
                    "at/below lower boundary but prior state is not ON; hold"
                )
            else:
                reason = "inside hysteresis band; hold prior legal state"
        if transition is not None:
            transitions.append(
                BaselineTransition(
                    event_type=transition,
                    event_id=_event_id(
                        capture.source.sha256,
                        baseline,
                        transition,
                        item.sample_id,
                        item.index,
                    ),
                    time_s=item.time_s,
                    sample_index=item.index,
                    sample_id=item.sample_id,
                    prior_state=prior_state,
                    new_state=state,
                    crossing_interval_start_s=previous_time,
                    crossing_interval_end_s=item.time_s,
                    time_certainty=(
                        CERTAINTY_EXACT
                        if value in (config.upper_on_c, config.lower_off_c)
                        else CERTAINTY_INTERVAL
                    ),
                    reason=reason,
                    crossing_time_s=item.time_s,
                )
            )
        samples.append(
            ReplaySample(
                index=item.index,
                sample_id=item.sample_id,
                seq=item.row.seq,
                source_line_index=item.row.source_line_index,
                time_s=item.time_s,
                representative_c=value,
                sample_status=item.sample_status,
                criterion_state=(
                    None if state is None else state == STATE_ON
                ),
                decision=(
                    state
                    if state is not None
                    else STATE_UNKNOWN
                ),
                prior_state=prior_state,
                new_state=state,
                transition=transition,
                reason=reason,
            )
        )
        previous_time = item.time_s
    result = _build_result(
        baseline=baseline,
        config_version=BASELINE_CONTRACT_VERSION,
        config_hash=config_hash,
        capture=capture,
        trajectory=trajectory,
        parameter_status=(
            persistence.status
            if persistence is not None
            else config.freeze_status
        ),
        parameter_source=(
            persistence.source
            if persistence is not None
            else config.upper_lower_source
        ),
        run_id=config.run_id,
        scenario_id=config.scenario_id,
        samples=samples,
        transitions=transitions,
        max_continuity_gap_s=config.max_continuity_gap_s,
        persistence=persistence_info,
    )
    return result


def replay_events_csv(results: Sequence[ReplayResult]) -> str:
    """Deterministic CSV for transitions and refused intervals."""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "baseline",
            "parameter_status",
            "run_id",
            "source_sha256",
            "record_type",
            "event_type",
            "event_id",
            "start_s",
            "end_s",
            "sample_id",
            "prior_state",
            "new_state",
            "time_certainty",
            "reason",
        ]
    )
    for result in results:
        for transition in result.transitions:
            writer.writerow(
                [
                    result.baseline,
                    result.parameter_status,
                    result.run_id or "",
                    result.source_sha256,
                    "TRANSITION",
                    transition.event_type,
                    transition.event_id,
                    transition.crossing_interval_start_s
                    if transition.crossing_interval_start_s is not None
                    else "",
                    transition.crossing_interval_end_s,
                    transition.sample_id,
                    transition.prior_state or "",
                    transition.new_state,
                    transition.time_certainty,
                    transition.reason,
                ]
            )
        for interval in result.refused_intervals:
            writer.writerow(
                [
                    result.baseline,
                    result.parameter_status,
                    result.run_id or "",
                    result.source_sha256,
                    "REFUSED_INTERVAL",
                    interval.reason,
                    "",
                    interval.start_s if interval.start_s is not None else "",
                    interval.end_s if interval.end_s is not None else "",
                    ",".join(str(index) for index in interval.sample_indices),
                    "",
                    "",
                    "",
                    "interval excluded from evaluable time",
                ]
            )
    return buffer.getvalue()
