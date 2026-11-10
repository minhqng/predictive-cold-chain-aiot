"""W21 SAFE_LOCAL, replay and recovery timeline assessment (B-W21-02).

Canonical anchors: Doc 02 sections 37-44, Doc 03 sections 66, 105-107, Doc 05D
sections 16-19, Doc 01 sections 18, 26.

A timeline is assessed only from declared fields.  A missing event stays
missing; a receipt time never becomes an event time; a reconnect never exits
SAFE_LOCAL on its own; and a software state transition is never reported as
physical thermal protection.  Durations keep their time-domain class and are
never merged into one distribution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from coldguard_ml.w21_evidence import (
    EVIDENCE_ACCEPTED_PHYSICAL_RESILIENCE_RESULT,
    EVIDENCE_CONTRACT_REFERENCE,
    EVIDENCE_HOST_SOFTWARE_SIMULATION,
    EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
    EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
)

PHYSICAL_EVIDENCE_CLASSES = frozenset(
    {
        EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
        EVIDENCE_ACCEPTED_PHYSICAL_RESILIENCE_RESULT,
    }
)

TIME_DEVICE_CAPTURED_AT = "DEVICE_CAPTURED_AT"
TIME_DEVICE_MONOTONIC = "DEVICE_MONOTONIC"
TIME_BACKEND_RECEIVED_AT = "BACKEND_RECEIVED_AT"
TIME_SOFTWARE_SIMULATION_CLOCK = "SOFTWARE_SIMULATION_CLOCK"
TIME_UNKNOWN = "UNKNOWN"

TIME_DOMAINS = (
    TIME_DEVICE_CAPTURED_AT,
    TIME_DEVICE_MONOTONIC,
    TIME_BACKEND_RECEIVED_AT,
    TIME_SOFTWARE_SIMULATION_CLOCK,
)

DURATION_SOFTWARE_SIMULATION = "SOFTWARE_SIMULATION_DURATION"
DURATION_ON_DEVICE_OBSERVED = "ON_DEVICE_OBSERVED_DURATION"
DURATION_PHYSICALLY_VERIFIED = "PHYSICALLY_VERIFIED_CONTROL_DURATION"

DURATION_CLASSES = (
    DURATION_SOFTWARE_SIMULATION,
    DURATION_ON_DEVICE_OBSERVED,
    DURATION_PHYSICALLY_VERIFIED,
)

STATUS_OUTAGE_NOT_OBSERVED = "OUTAGE_NOT_OBSERVED"
STATUS_SAFE_LOCAL_STATE_NOT_VERIFIED = "SAFE_LOCAL_STATE_NOT_VERIFIED"
STATUS_PHYSICAL_CONTROL_NOT_VERIFIED = "PHYSICAL_CONTROL_NOT_VERIFIED"
STATUS_RESYNC_NOT_VERIFIED = "RESYNC_NOT_VERIFIED"
STATUS_TIME_DOMAIN_INSUFFICIENT = "TIME_DOMAIN_INSUFFICIENT"
STATUS_DETECTION_NOT_OBSERVED = "DETECTION_NOT_OBSERVED"
STATUS_INVALID_ORDER = "INVALID_ORDER"

FAIL_CLOSED_STATUSES = (
    STATUS_OUTAGE_NOT_OBSERVED,
    STATUS_SAFE_LOCAL_STATE_NOT_VERIFIED,
    STATUS_PHYSICAL_CONTROL_NOT_VERIFIED,
    STATUS_RESYNC_NOT_VERIFIED,
    STATUS_TIME_DOMAIN_INSUFFICIENT,
)

REFUSAL_SAFE_LOCAL_NOT_PHYSICAL = (
    "SAFE_LOCAL_SOFTWARE_STATE_IS_NOT_PHYSICAL_THERMAL_PROTECTION"
)
REFUSAL_RECEIPT_TIME_SUBSTITUTION = "RECEIPT_TIME_CANNOT_REPLACE_EVENT_TIME"
REFUSAL_RECONNECT_NOT_EXIT = "RECONNECT_IS_NOT_SAFE_LOCAL_EXIT"
REFUSAL_NO_FRESH_STATE = "NO_FRESH_STATE_EVIDENCE"
REFUSAL_STALE_COMMAND = "STALE_COMMAND_MUST_NOT_BE_APPLIED"
REFUSAL_TWIN_REGRESSION = "HISTORICAL_REPLAY_MUST_NOT_REGRESS_TWIN"
REFUSAL_AI_SCORE_STALE = "OLD_RISK_SCORE_MUST_NOT_BE_TRUSTED_INDEFINITELY"
REFUSAL_SINGLE_SESSION_POPULATION = "SINGLE_SESSION_IS_NOT_A_DISTRIBUTION"
REFUSAL_CLASS_NOT_PHYSICAL = "EVIDENCE_CLASS_DOES_NOT_SUPPORT_PHYSICAL_CLAIM"
REFUSAL_HOST_SIMULATION_TIME = (
    "HOST_SIMULATION_CANNOT_PRODUCE_DEVICE_OBSERVED_DURATION"
)
REFUSAL_CONTRACT_NOT_TIMELINE = "CONTRACT_REFERENCE_IS_NOT_A_TIMELINE"

PHYSICAL_STATE_VERIFIED = "VERIFIED"
PHYSICAL_STATE_NOT_VERIFIED = "NOT_VERIFIED"

MODEL_HEALTH_READY = "READY"
MODEL_HEALTH_FALLBACK = "FALLBACK_REQUIRED"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class W21ResilienceError(ValueError):
    """Raised for a malformed timeline or replay record."""


def _require_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise W21ResilienceError(f"{name} must be an aware datetime")


def _seconds(start: datetime, end: datetime) -> float:
    _require_aware(start, "start")
    _require_aware(end, "end")
    return (end - start).total_seconds()


def _valid_state(value: str | None) -> bool:
    return value == PHYSICAL_STATE_VERIFIED


@dataclass(frozen=True)
class ResilienceTimeline:
    scenario_id: str
    source_id: str
    device_id: str
    boot_id: str
    time_domain: str
    source_hash: str
    evidence_class: str
    outage_start: datetime | None = None
    outage_end: datetime | None = None
    outage_detection: datetime | None = None
    safe_local_entered: datetime | None = None
    safe_local_exited: datetime | None = None
    local_control_state: str | None = None
    physical_electrical_state: str | None = None
    physical_thermal_state: str | None = None
    physical_thermal_evidence_ref: str | None = None
    reconnect_observed: datetime | None = None
    fresh_state_confirmed: bool | None = None
    resync_completed: datetime | None = None
    stale_command_rejected: bool | None = None

    def validate(self) -> None:
        for name in ("scenario_id", "source_id", "device_id", "boot_id"):
            if not getattr(self, name):
                raise W21ResilienceError(f"{name} must be non-empty")
        if self.time_domain not in TIME_DOMAINS + (TIME_UNKNOWN,):
            raise W21ResilienceError("unknown time_domain")
        if not _SHA256_RE.match(self.source_hash):
            raise W21ResilienceError("source_hash must be a sha256")
        if not self.evidence_class:
            raise W21ResilienceError("evidence_class must be non-empty")
        for name in (
            "outage_start",
            "outage_end",
            "outage_detection",
            "safe_local_entered",
            "safe_local_exited",
            "reconnect_observed",
            "resync_completed",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_aware(value, name)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, datetime):
                payload[name] = value.astimezone(timezone.utc).isoformat()
            else:
                payload[name] = value
        return payload


@dataclass(frozen=True)
class TimelineAssessment:
    scenario_id: str
    statuses: tuple[str, ...]
    durations: Mapping[str, Mapping[str, Any]]
    refusals: tuple[str, ...]
    physical_thermal_protection: bool
    independent_session_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "statuses": list(self.statuses),
            "durations": {key: dict(value) for key, value in self.durations.items()},
            "refusals": list(self.refusals),
            "physical_thermal_protection": self.physical_thermal_protection,
            "independent_session_count": self.independent_session_count,
        }


def duration_class(time_domain: str) -> str:
    if time_domain == TIME_SOFTWARE_SIMULATION_CLOCK:
        return DURATION_SOFTWARE_SIMULATION
    if time_domain in {TIME_DEVICE_CAPTURED_AT, TIME_DEVICE_MONOTONIC}:
        return DURATION_ON_DEVICE_OBSERVED
    if time_domain == TIME_BACKEND_RECEIVED_AT:
        raise W21ResilienceError(
            REFUSAL_RECEIPT_TIME_SUBSTITUTION
        )
    raise W21ResilienceError(STATUS_TIME_DOMAIN_INSUFFICIENT)


def assess_timeline(timeline: ResilienceTimeline) -> TimelineAssessment:
    timeline.validate()
    statuses: list[str] = []
    refusals: list[str] = []
    durations: dict[str, dict[str, Any]] = {}

    physical_evidence = timeline.evidence_class in PHYSICAL_EVIDENCE_CLASSES
    if timeline.evidence_class == EVIDENCE_CONTRACT_REFERENCE:
        statuses.append(STATUS_TIME_DOMAIN_INSUFFICIENT)
        refusals.append(REFUSAL_CONTRACT_NOT_TIMELINE)
        domain_class: str | None = None
    elif timeline.time_domain in {TIME_UNKNOWN, TIME_BACKEND_RECEIVED_AT}:
        statuses.append(STATUS_TIME_DOMAIN_INSUFFICIENT)
        refusals.append(REFUSAL_RECEIPT_TIME_SUBSTITUTION)
        domain_class = None
    else:
        domain_class = duration_class(timeline.time_domain)
        if timeline.evidence_class == EVIDENCE_HOST_SOFTWARE_SIMULATION:
            if domain_class == DURATION_ON_DEVICE_OBSERVED:
                refusals.append(REFUSAL_HOST_SIMULATION_TIME)
            domain_class = DURATION_SOFTWARE_SIMULATION
        elif timeline.evidence_class == EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION:
            if domain_class == DURATION_PHYSICALLY_VERIFIED:
                domain_class = DURATION_ON_DEVICE_OBSERVED

    def add_duration(
        name: str, start: datetime | None, end: datetime | None
    ) -> float | None:
        if start is None or end is None:
            return None
        if end < start:
            statuses.append(STATUS_INVALID_ORDER)
            return None
        value = _seconds(start, end)
        if domain_class is not None:
            durations[name] = {
                "value_s": value,
                "duration_class": domain_class,
                "start": start.astimezone(timezone.utc).isoformat(),
                "end": end.astimezone(timezone.utc).isoformat(),
            }
        return value

    if add_duration("outage_duration_s", timeline.outage_start, timeline.outage_end) is None:
        statuses.append(STATUS_OUTAGE_NOT_OBSERVED)

    if timeline.outage_detection is None:
        statuses.append(STATUS_DETECTION_NOT_OBSERVED)
    else:
        if add_duration(
            "detection_delay_s", timeline.outage_start, timeline.outage_detection
        ) is None and timeline.outage_start is None:
            statuses.append(STATUS_DETECTION_NOT_OBSERVED)

    if timeline.safe_local_entered is None:
        statuses.append(STATUS_SAFE_LOCAL_STATE_NOT_VERIFIED)
    else:
        if add_duration(
            "safe_local_interval_s",
            timeline.safe_local_entered,
            timeline.safe_local_exited,
        ) is None:
            statuses.append(STATUS_SAFE_LOCAL_STATE_NOT_VERIFIED)

    if timeline.reconnect_observed is None:
        statuses.append(STATUS_RESYNC_NOT_VERIFIED)
    else:
        if timeline.fresh_state_confirmed is not True:
            statuses.append(STATUS_RESYNC_NOT_VERIFIED)
            refusals.append(REFUSAL_NO_FRESH_STATE)
        if add_duration(
            "reconnect_to_resync_s",
            timeline.reconnect_observed,
            timeline.resync_completed,
        ) is None:
            statuses.append(STATUS_RESYNC_NOT_VERIFIED)
        if timeline.stale_command_rejected is not True:
            refusals.append(REFUSAL_STALE_COMMAND)

    electrical_verified = physical_evidence and _valid_state(
        timeline.physical_electrical_state
    )
    thermal_verified = (
        physical_evidence
        and _valid_state(timeline.physical_thermal_state)
        and bool(timeline.physical_thermal_evidence_ref)
    )
    if not physical_evidence and (
        timeline.physical_electrical_state == PHYSICAL_STATE_VERIFIED
        or timeline.physical_thermal_state == PHYSICAL_STATE_VERIFIED
    ):
        refusals.append(REFUSAL_CLASS_NOT_PHYSICAL)
    if not (electrical_verified and thermal_verified):
        statuses.append(STATUS_PHYSICAL_CONTROL_NOT_VERIFIED)
    if not thermal_verified:
        refusals.append(REFUSAL_SAFE_LOCAL_NOT_PHYSICAL)

    return TimelineAssessment(
        scenario_id=timeline.scenario_id,
        statuses=tuple(dict.fromkeys(statuses)),
        durations=durations,
        refusals=tuple(dict.fromkeys(refusals)),
        physical_thermal_protection=bool(
            electrical_verified and thermal_verified
        ),
        independent_session_count=1,
    )


@dataclass(frozen=True)
class TelemetryRecord:
    device_id: str
    boot_id: str
    seq: int
    captured_at: datetime | None
    received_at: datetime | None
    payload_sha256: str

    def validate(self) -> None:
        if not self.device_id or not self.boot_id:
            raise W21ResilienceError("telemetry identity is incomplete")
        if not isinstance(self.seq, int) or self.seq < 0:
            raise W21ResilienceError("seq must be a non-negative integer")
        if self.captured_at is not None:
            _require_aware(self.captured_at, "captured_at")
        if self.received_at is not None:
            _require_aware(self.received_at, "received_at")
        if not _SHA256_RE.match(self.payload_sha256):
            raise W21ResilienceError("payload_sha256 must be a sha256")


@dataclass(frozen=True)
class ReplayAssessment:
    normalized_sample_count: int
    missing_event_time_count: int
    duplicate_count: int
    conflicting_duplicate_count: int
    order_violation_count: int
    boot_change_count: int
    twin_regressions: int
    historical_replay_count: int
    gap_count: int
    refusals: tuple[str, ...]
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_sample_count": self.normalized_sample_count,
            "missing_event_time_count": self.missing_event_time_count,
            "duplicate_count": self.duplicate_count,
            "conflicting_duplicate_count": self.conflicting_duplicate_count,
            "order_violation_count": self.order_violation_count,
            "boot_change_count": self.boot_change_count,
            "twin_regressions": self.twin_regressions,
            "historical_replay_count": self.historical_replay_count,
            "gap_count": self.gap_count,
            "refusals": list(self.refusals),
            "status": self.status,
        }


def assess_replay(
    records: Sequence[TelemetryRecord],
    *,
    current_twin_seq: Mapping[str, int] | None = None,
) -> ReplayAssessment:
    if not records:
        raise W21ResilienceError("replay assessment requires records")
    current = dict(current_twin_seq or {})
    seen: dict[tuple[str, str, int], str] = {}
    canonical: list[TelemetryRecord] = []
    missing_event_time_count = 0
    duplicates = 0
    conflicts = 0
    order_violations = 0
    boot_changes = 0
    regressions = 0
    historical_replays = 0
    gap_count = 0
    refusals: list[str] = []
    previous_boot: str | None = None
    previous_seq: dict[str, int] = {}
    max_seq: dict[str, int] = {}

    for record in records:
        record.validate()
        if previous_boot is not None and record.boot_id != previous_boot:
            boot_changes += 1
            previous_seq.pop(record.boot_id, None)
            max_seq.pop(record.boot_id, None)
        previous_boot = record.boot_id
        key = (record.device_id, record.boot_id, record.seq)
        if key in seen:
            duplicates += 1
            if seen[key] != record.payload_sha256:
                conflicts += 1
            continue
        seen[key] = record.payload_sha256
        if record.captured_at is None:
            missing_event_time_count += 1
            refusals.append(REFUSAL_RECEIPT_TIME_SUBSTITUTION)
            continue
        known = current.get(record.boot_id)
        if known is not None and record.seq <= known:
            regressions += 1
            historical_replays += 1
            refusals.append(REFUSAL_TWIN_REGRESSION)
            continue
        last = previous_seq.get(record.boot_id)
        if last is not None and record.seq <= last:
            order_violations += 1
        highest = max_seq.get(record.boot_id)
        if highest is not None and record.seq > highest + 1:
            gap_count += record.seq - highest - 1
        previous_seq[record.boot_id] = record.seq
        max_seq[record.boot_id] = max(
            highest if highest is not None else 0, record.seq
        )
        canonical.append(record)

    if conflicts or regressions or missing_event_time_count:
        status = "FAILED"
    elif not canonical:
        status = "NOT_VERIFIED"
    elif duplicates or order_violations or boot_changes or gap_count:
        status = "VERIFIED_WITH_OBSERVED_VARIATION"
    else:
        status = "VERIFIED"
    return ReplayAssessment(
        normalized_sample_count=len(canonical),
        missing_event_time_count=missing_event_time_count,
        duplicate_count=duplicates,
        conflicting_duplicate_count=conflicts,
        order_violation_count=order_violations,
        boot_change_count=boot_changes,
        twin_regressions=regressions,
        historical_replay_count=historical_replays,
        gap_count=gap_count,
        refusals=tuple(dict.fromkeys(refusals)),
        status=status,
    )


@dataclass(frozen=True)
class StaleCommandAssessment:
    expired: bool
    applied: bool
    status: str
    refusals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "expired": self.expired,
            "applied": self.applied,
            "status": self.status,
            "refusals": list(self.refusals),
        }


def assess_stale_command(
    *,
    issued_at: datetime,
    evaluated_at: datetime,
    ttl_s: float,
    fresh_state_confirmed: bool,
    applied: bool,
) -> StaleCommandAssessment:
    _require_aware(issued_at, "issued_at")
    _require_aware(evaluated_at, "evaluated_at")
    if ttl_s <= 0:
        raise W21ResilienceError("ttl_s must be positive")
    if evaluated_at < issued_at:
        raise W21ResilienceError("evaluated_at precedes issued_at")
    expired = (evaluated_at - issued_at).total_seconds() > ttl_s
    refusals: list[str] = []
    if applied and (expired or not fresh_state_confirmed):
        refusals.append(REFUSAL_STALE_COMMAND)
        return StaleCommandAssessment(
            expired=expired,
            applied=applied,
            status="FAILED",
            refusals=tuple(refusals),
        )
    if expired:
        return StaleCommandAssessment(
            expired=True,
            applied=False,
            status="STALE_COMMAND_REJECTED",
            refusals=tuple(refusals),
        )
    if not fresh_state_confirmed:
        return StaleCommandAssessment(
            expired=False,
            applied=False,
            status="HELD_PENDING_FRESH_STATE",
            refusals=("NO_FRESH_STATE",),
        )
    return StaleCommandAssessment(
        expired=False, applied=applied, status="FRESH", refusals=()
    )


EXIT_REQUIREMENTS = (
    "network_stable",
    "broker_connected",
    "backend_synchronized",
    "fresh_telemetry",
    "no_stale_command",
    "ai_healthy_if_predictive",
    "no_critical_fault",
)


@dataclass(frozen=True)
class ExitAssessment:
    ready: bool
    missing: tuple[str, ...]
    refusals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "missing": list(self.missing),
            "refusals": list(self.refusals),
        }


def assess_safe_local_exit(
    state: Mapping[str, bool], *, reconnect_observed: bool = False
) -> ExitAssessment:
    missing = tuple(name for name in EXIT_REQUIREMENTS if state.get(name) is not True)
    refusals: list[str] = []
    if reconnect_observed and missing:
        refusals.append(REFUSAL_RECONNECT_NOT_EXIT)
    if "fresh_telemetry" in missing:
        refusals.append(REFUSAL_NO_FRESH_STATE)
    return ExitAssessment(
        ready=not missing,
        missing=missing,
        refusals=tuple(dict.fromkeys(refusals)),
    )


@dataclass(frozen=True)
class AiFallbackAssessment:
    status: str
    score_usable: bool
    refusals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score_usable": self.score_usable,
            "refusals": list(self.refusals),
        }


def assess_ai_fallback(
    *,
    model_health: str,
    risk_score_age_s: float | None,
    maximum_score_age_s: float,
) -> AiFallbackAssessment:
    if maximum_score_age_s <= 0:
        raise W21ResilienceError("maximum_score_age_s must be positive")
    if model_health != MODEL_HEALTH_READY:
        return AiFallbackAssessment(
            status=MODEL_HEALTH_FALLBACK,
            score_usable=False,
            refusals=(REFUSAL_AI_SCORE_STALE,),
        )
    if risk_score_age_s is None or risk_score_age_s > maximum_score_age_s:
        return AiFallbackAssessment(
            status=MODEL_HEALTH_FALLBACK,
            score_usable=False,
            refusals=(REFUSAL_AI_SCORE_STALE,),
        )
    return AiFallbackAssessment(
        status="READY", score_usable=True, refusals=()
    )


def population_distribution_status(independent_session_count: int) -> str:
    if independent_session_count < 2:
        return REFUSAL_SINGLE_SESSION_POPULATION
    return "ESTIMABLE_ONLY_WITH_ADMITTED_POPULATION_SUPPORT"
