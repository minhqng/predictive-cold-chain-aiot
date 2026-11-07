"""W06 provenance-aware event alignment and command/response timing.

This module implements the Member B W06 slice (B-W06-01 … B-W06-04). It
consumes the W04 normalized capture model for A exports and C snapshots,
and it adds one distinct, explicitly versioned adapter for A's
``#CG CMDACK schema=1`` serial command-event representation. Serial
telemetry frames are never fed through the C JSON telemetry parser.

The layer separates claims that are easy to conflate:

* a unified event timeline formed only from records that actually carry the
  event, never from a timestamp coincidence;
* ordering inside one trusted clock/boot domain versus an explicit partial
  protocol order that carries no measured latency;
* clock, sequence and provenance diagnostics that retain every unalignable
  event instead of dropping it;
* bounded, configurable response detection whose numeric result is only
  emitted when the anchor, quality and clock evidence justify it;
* deterministic duplicate handling that preserves delivery multiplicity
  and reports contradictory identities instead of choosing a favorable one.

No W06 function computes AIW. ``compute_aiw`` in the W04 contract remains
the gate for a complete, non-overlapping multi-component chain.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .intake import (
    Capture,
    NormalizedRow,
    RoleError,
    TIME_BOOT_SCOPED_UPTIME,
    TIME_EVENT_UTC,
    chamber_air_mean,
)

W06_LAYER_VERSION = "coldguard-w06-timing-v1"
W06_EVENT_FIXTURE_SCHEMA = "coldguard-w06-event-fixture-v1"

EVENT_DOOR_TRANSITION = "DOOR_TRANSITION"
EVENT_TELEMETRY_SAMPLE = "TELEMETRY_SAMPLE"
EVENT_POLICY_DECISION = "POLICY_DECISION"
EVENT_COMMAND_CREATED_OR_PUBLISHED = "COMMAND_CREATED_OR_PUBLISHED"
EVENT_DEVICE_ACK = "DEVICE_ACK"
EVENT_APPLIED_STATE = "APPLIED_STATE"
EVENT_ELECTRICAL_RESPONSE = "ELECTRICAL_RESPONSE"
EVENT_THERMAL_RESPONSE = "THERMAL_RESPONSE"

EVENT_TYPES = (
    EVENT_DOOR_TRANSITION,
    EVENT_TELEMETRY_SAMPLE,
    EVENT_POLICY_DECISION,
    EVENT_COMMAND_CREATED_OR_PUBLISHED,
    EVENT_DEVICE_ACK,
    EVENT_APPLIED_STATE,
    EVENT_ELECTRICAL_RESPONSE,
    EVENT_THERMAL_RESPONSE,
)

PROVENANCE_PHYSICAL_MEASURED = "PHYSICAL_MEASURED"
PROVENANCE_HOST_GENERATED_SYNTHETIC = "HOST_GENERATED_SYNTHETIC"
PROVENANCE_SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
PROVENANCE_UNVERIFIED = "UNVERIFIED"
PROVENANCE_CATEGORIES = (
    PROVENANCE_PHYSICAL_MEASURED,
    PROVENANCE_HOST_GENERATED_SYNTHETIC,
    PROVENANCE_SYNTHETIC_FIXTURE,
    PROVENANCE_UNVERIFIED,
)

ELIGIBILITY_DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
ELIGIBILITY_SYNTHETIC_UNIT_TEST = "SYNTHETIC_UNIT_TEST"
ELIGIBILITY_UNVERIFIED = "UNVERIFIED_PROVENANCE"

CLOCK_DEVICE_BOOT_UPTIME = "DEVICE_BOOT_UPTIME"
CLOCK_DEVICE_EVENT_UTC = "DEVICE_EVENT_UTC"
CLOCK_HOST_CAPTURE_UTC = "HOST_CAPTURE_UTC"
CLOCK_BACKEND_RECEIVE_UTC = "BACKEND_RECEIVE_UTC"
CLOCK_BACKEND_PERSISTED_UTC = "BACKEND_PERSISTED_UTC"
CLOCK_UNKNOWN = "UNKNOWN_CLOCK_DOMAIN"
CLOCK_DOMAINS = (
    CLOCK_DEVICE_BOOT_UPTIME,
    CLOCK_DEVICE_EVENT_UTC,
    CLOCK_HOST_CAPTURE_UTC,
    CLOCK_BACKEND_RECEIVE_UTC,
    CLOCK_BACKEND_PERSISTED_UTC,
    CLOCK_UNKNOWN,
)

CLOCK_SYNC_EVIDENCED = "EVIDENCED"
CLOCK_SYNC_SYNTHETIC_EXACT = "SYNTHETIC_EXACT"
CLOCK_SYNC_UNVERIFIED = "UNVERIFIED_SYNC"
CLOCK_SYNC_NOT_EVIDENCED = "NOT_EVIDENCED"
CLOCK_SYNC_UNSYNCHRONIZED = "UNSYNCHRONIZED"

ORDERED_IN_DOMAIN = "ORDERED_IN_DOMAIN"
ORDER_AMBIGUOUS = "AMBIGUOUS_ORDER"
ORDER_NOT_ALIGNABLE = "NOT_ALIGNABLE"
ORDER_MIXED_CLOCK = "NOT_ALIGNABLE_MIXED_CLOCK_DOMAINS"
ORDER_MIXED_BOOT = "NOT_ALIGNABLE_MIXED_BOOT_IDENTITIES"
ORDER_MIXED_DEVICE = "NOT_ALIGNABLE_MIXED_DEVICE_IDENTITIES"
ORDER_MISSING_TIMESTAMP = "MISSING_TIMESTAMP"

REASON_NOT_ALIGNABLE = "NOT_ALIGNABLE"
REASON_UNTRUSTED_CLOCK = "UNTRUSTED_CLOCK"
REASON_MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
REASON_TIME_REVERSAL = "TIME_REVERSAL"
REASON_AMBIGUOUS_ORDER = "AMBIGUOUS_ORDER"
REASON_MIXED_CLOCK_DOMAINS = "MIXED_CLOCK_DOMAINS"
REASON_CROSS_BOOT_REFUSED = "CROSS_BOOT_JOIN_REFUSED"
REASON_HOST_TIME_NOT_SOURCE_TIME = "HOST_CAPTURE_TIME_NOT_SOURCE_TIME"

IDENTITY_RESOLVED = "RESOLVED"
IDENTITY_PARTIAL = "PARTIAL"
IDENTITY_MISSING = "MISSING"

ACK_STATUSES = (
    "ACCEPTED",
    "REJECTED",
    "DUPLICATE_CANONICAL",
    "EXPIRED",
    "SAFETY_BLOCKED",
    "INVALID_STATE",
    "OUT_OF_RANGE",
)
ACK_ACCEPT_STATUSES = ("ACCEPTED", "DUPLICATE_CANONICAL")

RESPONSE_OBSERVED_DIAGNOSTIC_ONLY = "OBSERVED_DIAGNOSTIC_ONLY"
RESPONSE_VERIFIED_MEASURED_RESPONSE = "VERIFIED_MEASURED_RESPONSE"
RESPONSE_NOT_OBSERVED = "NOT_OBSERVED"
RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR = "NOT_ESTIMABLE_MISSING_ANCHOR"
RESPONSE_NOT_ESTIMABLE_CLOCK = "NOT_ESTIMABLE_CLOCK"
RESPONSE_NOT_ESTIMABLE_QUALITY = "NOT_ESTIMABLE_QUALITY"
RESPONSE_NOT_ESTIMABLE_BASELINE = "NOT_ESTIMABLE_BASELINE"
RESPONSE_NOT_ESTIMABLE_UNCERTAINTY = "NOT_ESTIMABLE_UNCERTAINTY"
RESPONSE_CENSORED = "CENSORED"
RESPONSE_CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
RESPONSE_NOT_APPLICABLE_ACK_NOT_ACCEPTED = "NOT_APPLICABLE_ACK_NOT_ACCEPTED"
RESPONSE_DUPLICATE_CANONICAL_NOT_APPLICATION = (
    "DUPLICATE_CANONICAL_NOT_AN_APPLICATION"
)
RESPONSE_STATES = (
    RESPONSE_OBSERVED_DIAGNOSTIC_ONLY,
    RESPONSE_VERIFIED_MEASURED_RESPONSE,
    RESPONSE_NOT_OBSERVED,
    RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR,
    RESPONSE_NOT_ESTIMABLE_CLOCK,
    RESPONSE_NOT_ESTIMABLE_QUALITY,
    RESPONSE_NOT_ESTIMABLE_BASELINE,
    RESPONSE_NOT_ESTIMABLE_UNCERTAINTY,
    RESPONSE_CENSORED,
    RESPONSE_CONTRADICTORY_EVIDENCE,
    RESPONSE_NOT_APPLICABLE_ACK_NOT_ACCEPTED,
    RESPONSE_DUPLICATE_CANONICAL_NOT_APPLICATION,
)

DEFAULT_ELECTRICAL_MIN_CHANGE_A = 0.05
DEFAULT_THERMAL_MIN_CHANGE_C = 0.25
DEFAULT_TIMING_UNCERTAINTY_S = 1.0


class TimingAlignmentError(ValueError):
    """A source or timing request cannot be interpreted without guessing."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class TimelineEvent:
    """One typed event with source, identity, clock and quality provenance."""

    event_id: str
    event_type: str
    provenance: str
    source_path: str
    source_sha256: str
    source_namespace: str
    source_record_index: int | None = None
    device_id: str | None = None
    boot_id: str | None = None
    run_id: str | None = None
    identity_status: str = IDENTITY_MISSING
    command_id: str | None = None
    ack_seq: int | None = None
    seq: int | None = None
    device_uptime_ms: int | None = None
    event_time_utc: str | None = None
    backend_received_at: str | None = None
    persisted_at: str | None = None
    clock_domain: str = CLOCK_UNKNOWN
    clock_sync: str = CLOCK_SYNC_NOT_EVIDENCED
    raw_fields: tuple[tuple[str, str], ...] = ()
    normalized_fields: tuple[tuple[str, str], ...] = ()
    measurement_quality: str = "UNKNOWN"
    uncertainty_s: float | None = None
    source_line_index: int | None = None
    eligibility: str = ELIGIBILITY_DIAGNOSTIC_ONLY
    reason_codes: tuple[str, ...] = ()
    delivery_count: int = 1

    def __post_init__(self) -> None:
        if self.event_type not in EVENT_TYPES:
            raise TimingAlignmentError(
                "UNKNOWN_EVENT_TYPE", f"{self.event_type!r} is not a W06 event type"
            )
        if self.provenance not in PROVENANCE_CATEGORIES:
            raise TimingAlignmentError(
                "UNKNOWN_PROVENANCE", f"{self.provenance!r} is not a provenance category"
            )
        if self.clock_domain not in CLOCK_DOMAINS:
            raise TimingAlignmentError(
                "UNKNOWN_CLOCK_DOMAIN", f"{self.clock_domain!r} is not a clock domain"
            )
        if self.uncertainty_s is not None and self.uncertainty_s < 0:
            raise TimingAlignmentError(
                "NEGATIVE_UNCERTAINTY", "event uncertainty must be non-negative"
            )

    @property
    def field_origin(self) -> str:
        if self.raw_fields and self.normalized_fields:
            return "RAW_AND_NORMALIZED"
        if self.raw_fields:
            return "RAW_ONLY"
        return "NORMALIZED_ONLY"

    def field(self, name: str) -> str | None:
        for key, value in self.normalized_fields:
            if key == name:
                return value
        return None

    def raw_field(self, name: str) -> str | None:
        for key, value in self.raw_fields:
            if key == name:
                return value
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "provenance": self.provenance,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "source_namespace": self.source_namespace,
            "source_record_index": self.source_record_index,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "run_id": self.run_id,
            "identity_status": self.identity_status,
            "command_id": self.command_id,
            "ack_seq": self.ack_seq,
            "seq": self.seq,
            "device_uptime_ms": self.device_uptime_ms,
            "event_time_utc": self.event_time_utc,
            "backend_received_at": self.backend_received_at,
            "persisted_at": self.persisted_at,
            "clock_domain": self.clock_domain,
            "clock_sync": self.clock_sync,
            "raw_fields": dict(self.raw_fields),
            "normalized_fields": dict(self.normalized_fields),
            "field_origin": self.field_origin,
            "measurement_quality": self.measurement_quality,
            "uncertainty_s": self.uncertainty_s,
            "source_line_index": self.source_line_index,
            "eligibility": self.eligibility,
            "reason_codes": list(self.reason_codes),
            "delivery_count": self.delivery_count,
        }


@dataclass(frozen=True)
class OrderedTimeline:
    status: str
    events: tuple[TimelineEvent, ...]
    reason_codes: tuple[str, ...]
    clock_domain: str | None
    device_id: str | None
    boot_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "clock_domain": self.clock_domain,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "reason_codes": list(self.reason_codes),
            "event_ids": [event.event_id for event in self.events],
        }


@dataclass(frozen=True)
class ProtocolRelation:
    before_event_id: str
    after_event_id: str
    command_id: str
    relation: str
    latency_claim: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "before_event_id": self.before_event_id,
            "after_event_id": self.after_event_id,
            "command_id": self.command_id,
            "relation": self.relation,
            "latency_claim": self.latency_claim,
        }


@dataclass(frozen=True)
class DomainAudit:
    clock_domain: str
    device_id: str | None
    boot_id: str | None
    event_count: int
    first_time: float | None
    last_time: float | None
    monotonic: bool
    timestamp_reversals: int
    sequence_gaps: int
    sequence_reversals: int
    sequence_duplicates: int
    uptime_resets: int
    capture_receive_conflicts: int
    missing_capture_times: int
    missing_receive_times: int
    impossible_negative_intervals: int
    uncertain_cross_stream_associations: int
    max_uncertainty_s: float | None
    median_interval_s: float | None
    p95_interval_s: float | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "clock_domain": self.clock_domain,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "event_count": self.event_count,
            "first_time": self.first_time,
            "last_time": self.last_time,
            "monotonic": self.monotonic,
            "timestamp_reversals": self.timestamp_reversals,
            "sequence_gaps": self.sequence_gaps,
            "sequence_reversals": self.sequence_reversals,
            "sequence_duplicates": self.sequence_duplicates,
            "uptime_resets": self.uptime_resets,
            "capture_receive_conflicts": self.capture_receive_conflicts,
            "missing_capture_times": self.missing_capture_times,
            "missing_receive_times": self.missing_receive_times,
            "impossible_negative_intervals": self.impossible_negative_intervals,
            "uncertain_cross_stream_associations": (
                self.uncertain_cross_stream_associations
            ),
            "max_uncertainty_s": self.max_uncertainty_s,
            "median_interval_s": self.median_interval_s,
            "p95_interval_s": self.p95_interval_s,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class TimingAudit:
    domains: tuple[DomainAudit, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "domains": [domain.to_dict() for domain in self.domains],
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class DedupResult:
    canonical_events: tuple[TimelineEvent, ...]
    contradictory_events: tuple[TimelineEvent, ...]
    missing_identity_events: tuple[TimelineEvent, ...]
    duplicate_deliveries: int
    contradictory_identity_count: int
    duplicate_canonical_acks: int
    multiple_ack_without_canonical: int
    reboot_identity_resets: int
    new_commands_same_action: int
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_events": [
                event.to_dict() for event in self.canonical_events
            ],
            "contradictory_events": [
                event.to_dict() for event in self.contradictory_events
            ],
            "missing_identity_events": [
                event.to_dict() for event in self.missing_identity_events
            ],
            "duplicate_deliveries": self.duplicate_deliveries,
            "contradictory_identity_count": self.contradictory_identity_count,
            "duplicate_canonical_acks": self.duplicate_canonical_acks,
            "multiple_ack_without_canonical": self.multiple_ack_without_canonical,
            "reboot_identity_resets": self.reboot_identity_resets,
            "new_commands_same_action": self.new_commands_same_action,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ResponsePolicy:
    """A named, configurable response-detection method, never a contract limit."""

    name: str
    channel: str
    physical_role: str
    quality_key: str
    expected_direction: str
    min_change: float
    baseline_window_s: float = 10.0
    max_window_s: float = 60.0
    sustained_observations: int = 3
    max_gap_s: float = 5.0
    max_uncertainty_s: float | None = None
    gap_policy: str = "CENSOR"

    def __post_init__(self) -> None:
        if self.expected_direction not in ("UP", "DOWN"):
            raise TimingAlignmentError(
                "INVALID_DIRECTION", "expected_direction must be UP or DOWN"
            )
        if self.min_change <= 0:
            raise TimingAlignmentError(
                "INVALID_MIN_CHANGE", "min_change must be positive"
            )
        if self.baseline_window_s <= 0 or self.max_window_s <= 0:
            raise TimingAlignmentError(
                "INVALID_WINDOW", "response windows must be positive"
            )
        if self.sustained_observations < 1:
            raise TimingAlignmentError(
                "INVALID_SUSTAINED_COUNT",
                "sustained_observations must be at least 1",
            )
        if self.max_gap_s <= 0:
            raise TimingAlignmentError("INVALID_MAX_GAP", "max_gap_s must be positive")
        if self.physical_role in ("TEC_HOT_SIDE", "HOT_SIDE"):
            raise RoleError(
                "the TEC hot side is never a chamber-air response channel"
            )
        if self.channel in ("t2", "t2_c", "hot_side_c", "tec_hot_side_c"):
            raise RoleError(
                "the TEC hot side is never a chamber-air response channel"
            )
        if self.quality_key not in (
            "thermal",
            "electrical",
            "environment",
            "door",
            "overall",
        ):
            raise TimingAlignmentError(
                "INVALID_QUALITY_KEY", f"unknown quality key {self.quality_key!r}"
            )
        if self.gap_policy not in ("CENSOR", "SKIP"):
            raise TimingAlignmentError(
                "INVALID_GAP_POLICY", "gap_policy must be CENSOR or SKIP"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "channel": self.channel,
            "physical_role": self.physical_role,
            "quality_key": self.quality_key,
            "expected_direction": self.expected_direction,
            "min_change": self.min_change,
            "baseline_window_s": self.baseline_window_s,
            "max_window_s": self.max_window_s,
            "sustained_observations": self.sustained_observations,
            "max_gap_s": self.max_gap_s,
            "max_uncertainty_s": self.max_uncertainty_s,
            "gap_policy": self.gap_policy,
            "threshold_status": (
                "CONFIGURABLE_ANALYSIS_FLOOR_NOT_A_CONTRACT_THRESHOLD"
            ),
        }


@dataclass(frozen=True)
class ResponseResult:
    relationship: str
    state: str
    command_id: str | None
    anchor_event_id: str | None
    latency_s: float | None
    uncertainty_s: float | None
    evidence_class: str
    independent_application: bool | None
    sample_count: int
    baseline_median: float | None
    policy_name: str
    reason_codes: tuple[str, ...]
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "relationship": self.relationship,
            "state": self.state,
            "command_id": self.command_id,
            "anchor_event_id": self.anchor_event_id,
            "latency_s": self.latency_s,
            "uncertainty_s": self.uncertainty_s,
            "evidence_class": self.evidence_class,
            "independent_application": self.independent_application,
            "sample_count": self.sample_count,
            "baseline_median": self.baseline_median,
            "policy_name": self.policy_name,
            "reason_codes": list(self.reason_codes),
        }


DEFAULT_ELECTRICAL_POLICY = ResponsePolicy(
    name="electrical-current-step-v1",
    channel="cooling_current_a",
    physical_role="COOLING_BRANCH_ELECTRICAL",
    quality_key="electrical",
    expected_direction="UP",
    min_change=DEFAULT_ELECTRICAL_MIN_CHANGE_A,
    baseline_window_s=10.0,
    max_window_s=60.0,
    sustained_observations=3,
    max_gap_s=5.0,
    max_uncertainty_s=5.0,
)

DEFAULT_THERMAL_POLICY = ResponsePolicy(
    name="chamber-air-temperature-step-v1",
    channel="chamber_air_mean_c",
    physical_role="CHAMBER_AIR",
    quality_key="thermal",
    expected_direction="DOWN",
    min_change=DEFAULT_THERMAL_MIN_CHANGE_C,
    baseline_window_s=10.0,
    max_window_s=300.0,
    sustained_observations=3,
    max_gap_s=5.0,
    max_uncertainty_s=10.0,
)


# ---------------------------------------------------------------------------
# event construction
# ---------------------------------------------------------------------------


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _quality_map(row: NormalizedRow) -> dict[str, str]:
    return {key: value for key, value in row.quality}


def _identity_status(
    device_id: str | None, boot_id: str | None, run_id: str | None, seq: int | None
) -> str:
    present = sum(
        1 for value in (device_id, boot_id, run_id, seq) if value is not None
    )
    if present == 4:
        return IDENTITY_RESOLVED
    if present:
        return IDENTITY_PARTIAL
    return IDENTITY_MISSING


def _provenance_for_capture(capture: Capture) -> tuple[str, str]:
    if capture.source.provenance == "PHYSICAL" and capture.source.is_physical_measurement:
        return PROVENANCE_PHYSICAL_MEASURED, ELIGIBILITY_DIAGNOSTIC_ONLY
    if capture.source.provenance == "SYNTHETIC":
        return PROVENANCE_SYNTHETIC_FIXTURE, ELIGIBILITY_SYNTHETIC_UNIT_TEST
    return PROVENANCE_UNVERIFIED, ELIGIBILITY_UNVERIFIED


def _event_id(
    source_sha256: str,
    event_type: str,
    device_id: str | None,
    boot_id: str | None,
    discriminator: Any,
    suffix: str = "",
) -> str:
    return ":".join(
        [
            source_sha256[:16],
            event_type,
            device_id or "NO_DEVICE_ID",
            boot_id or "NO_BOOT_ID",
            str(discriminator),
            suffix or "base",
        ]
    )


def _session_rows(capture: Capture) -> dict[tuple[str | None, str | None], list[NormalizedRow]]:
    sessions: dict[tuple[str | None, str | None], list[NormalizedRow]] = {}
    for row in capture.rows:
        sessions.setdefault((row.device_id, row.boot_id), []).append(row)
    return sessions


def _ordered_session_rows(
    capture: Capture, rows: Sequence[NormalizedRow]
) -> tuple[list[NormalizedRow], bool, str | None]:
    """Order one boot session and report whether source-time order is ambiguous."""
    if capture.time.domain == TIME_BOOT_SCOPED_UPTIME and all(
        row.device_ms is not None for row in rows
    ):
        ordered = sorted(rows, key=lambda row: (row.device_ms, row.seq))
        reversal = any(
            left.device_ms > right.device_ms
            for left, right in zip(rows, rows[1:])
            if left.device_ms is not None and right.device_ms is not None
        )
        return ordered, reversal, REASON_TIME_REVERSAL if reversal else None
    if (
        capture.time.domain == TIME_EVENT_UTC
        and all(row.event_time_utc is not None for row in rows)
    ):
        ordered = sorted(rows, key=lambda row: (row.event_time_utc, row.seq))
        reversal = any(
            left.event_time_utc > right.event_time_utc
            for left, right in zip(rows, rows[1:])
            if left.event_time_utc is not None and right.event_time_utc is not None
        )
        return ordered, reversal, REASON_TIME_REVERSAL if reversal else None
    return list(rows), True, REASON_MISSING_TIMESTAMP


def _normalized_row_fields(
    capture: Capture, row: NormalizedRow
) -> tuple[tuple[str, str], ...]:
    fields: dict[str, str] = {
        "seq": str(row.seq),
        "door_state": row.door_state,
        "door_polarity": row.door_polarity or "",
        "applied_cooling": row.applied_cooling or "",
        "applied_duty_permille": (
            str(row.applied_duty_permille)
            if row.applied_duty_permille is not None
            else ""
        ),
        "requested_duty_permille": (
            str(row.requested_duty_permille)
            if row.requested_duty_permille is not None
            else ""
        ),
        "readback_duty_permille": (
            str(row.readback_duty_permille)
            if row.readback_duty_permille is not None
            else ""
        ),
        "cooling_voltage_v": _number_text(row.cooling_voltage_v),
        "cooling_current_a": _number_text(row.cooling_current_a),
        "cooling_power_w": _number_text(row.cooling_power_w),
        "cooling_energy_counter_wh": _number_text(row.cooling_energy_counter_wh),
        "t_air_c": _number_text(row.t_air_c),
        "rh_pct": _number_text(row.rh_pct),
        "pressure_hpa": _number_text(row.pressure_hpa),
        "device_state": row.device_state or "",
        "experiment_phase": row.experiment_phase or "",
    }
    for probe in row.probes:
        fields[f"{probe.slot}_c"] = _number_text(probe.value_c)
        fields[f"quality.probe.{probe.slot}"] = probe.status or ""
    quality = _quality_map(row)
    for key, value in quality.items():
        fields[f"quality.{key}"] = value
    fields["quality.overall"] = row.overall_quality or quality.get("overall", "")
    try:
        mean = chamber_air_mean(capture, row)
    except RoleError:
        mean = None
    fields["chamber_air_mean_c"] = _number_text(mean)
    if mean is None:
        fields["chamber_air_status"] = "ROLE_NOT_QUALIFIED_OR_MISSING"
    else:
        fields["chamber_air_status"] = "ROLE_QUALIFIED_CHAMBER_AIR"
    return tuple(sorted(fields.items()))


def _number_text(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


def events_from_capture(capture: Capture) -> tuple[TimelineEvent, ...]:
    """Build typed events from a W04 capture without inventing command records."""
    provenance, eligibility = _provenance_for_capture(capture)
    events: list[TimelineEvent] = []
    sessions = _session_rows(capture)
    for (device_id, boot_id), rows in sorted(
        sessions.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))
    ):
        ordered, reversal, order_reason = _ordered_session_rows(capture, rows)
        last_known_applied: str | None = None
        last_known_applied_time_s: float | None = None
        previous_door: str | None = None
        for row in ordered:
            time_s = _row_time_s(capture, row, ordered)
            common_reasons: list[str] = []
            if reversal and order_reason:
                common_reasons.append(order_reason)
            if capture.run.run_id is None:
                common_reasons.append("RUN_ID_UNRESOLVED")
            if row.device_id is None:
                common_reasons.append("DEVICE_ID_NOT_CARRIED")
            if capture.time.clock_sync not in (
                CLOCK_SYNC_EVIDENCED,
                CLOCK_SYNC_SYNTHETIC_EXACT,
            ):
                common_reasons.append("CLOCK_SYNC_NOT_EVIDENCED")
            if provenance != PROVENANCE_PHYSICAL_MEASURED:
                common_reasons.append("SYNTHETIC_OR_UNVERIFIED_PROVENANCE")
            fields = _normalized_row_fields(capture, row)
            field_map = dict(fields)
            event = TimelineEvent(
                event_id=_event_id(
                    capture.source.sha256,
                    EVENT_TELEMETRY_SAMPLE,
                    device_id,
                    boot_id,
                    row.seq,
                ),
                event_type=EVENT_TELEMETRY_SAMPLE,
                provenance=provenance,
                source_path=capture.source.path,
                source_sha256=capture.source.sha256,
                source_namespace=capture.source.schema_namespace,
                source_record_index=row.source_line_index,
                device_id=device_id,
                boot_id=boot_id,
                run_id=row.run_id,
                identity_status=_identity_status(
                    device_id, boot_id, row.run_id, row.seq
                ),
                seq=row.seq,
                device_uptime_ms=row.device_ms,
                event_time_utc=_iso(row.event_time_utc),
                clock_domain=_capture_clock_domain(capture),
                clock_sync=capture.time.clock_sync,
                normalized_fields=fields,
                measurement_quality=(
                    row.overall_quality
                    or row.producer_quality
                    or "UNKNOWN"
                ),
                uncertainty_s=None,
                source_line_index=row.source_line_index,
                eligibility=eligibility,
                reason_codes=tuple(sorted(set(common_reasons))),
            )
            events.append(event)

            door = row.door_state
            if door in ("OPEN", "CLOSED"):
                if (
                    previous_door in ("OPEN", "CLOSED")
                    and previous_door != door
                ):
                    transition_reasons = list(common_reasons)
                    transition_reasons.append("DOOR_TRANSITION")
                    events.append(
                        replace(
                            event,
                            event_id=_event_id(
                                capture.source.sha256,
                                EVENT_DOOR_TRANSITION,
                                device_id,
                                boot_id,
                                row.seq,
                                "door",
                            ),
                            event_type=EVENT_DOOR_TRANSITION,
                            normalized_fields=tuple(
                                sorted(
                                    {
                                        **field_map,
                                        "door_from": previous_door,
                                        "door_to": door,
                                        "event_subtype": "door",
                                    }.items()
                                )
                            ),
                            measurement_quality=field_map.get(
                                "quality.door", "UNKNOWN"
                            ),
                            uncertainty_s=(
                                1.0
                                if capture.source.format.startswith(
                                    "a-w09-run-export"
                                )
                                else None
                            ),
                            reason_codes=tuple(sorted(set(transition_reasons))),
                        )
                    )
                previous_door = door
            elif door == "UNKNOWN":
                previous_door = "UNKNOWN"

            applied = row.applied_cooling
            if applied in ("ON", "OFF"):
                if last_known_applied is not None and applied != last_known_applied:
                    applied_uncertainty = None
                    if (
                        time_s is not None
                        and last_known_applied_time_s is not None
                        and time_s >= last_known_applied_time_s
                    ):
                        applied_uncertainty = round(
                            time_s - last_known_applied_time_s, 6
                        )
                    applied_reasons = list(common_reasons)
                    applied_reasons.extend(
                        [
                            "APPLIED_STATE_DEVICE_REPORTED",
                            "APPLIED_STATE_NOT_COMMAND_LINKED",
                        ]
                    )
                    events.append(
                        replace(
                            event,
                            event_id=_event_id(
                                capture.source.sha256,
                                EVENT_APPLIED_STATE,
                                device_id,
                                boot_id,
                                row.seq,
                                "applied",
                            ),
                            event_type=EVENT_APPLIED_STATE,
                            normalized_fields=tuple(
                                sorted(
                                    {
                                        **field_map,
                                        "applied_from": last_known_applied,
                                        "applied_to": applied,
                                        "event_subtype": "applied",
                                    }.items()
                                )
                            ),
                            measurement_quality=field_map.get(
                                "quality.overall", "UNKNOWN"
                            ),
                            uncertainty_s=applied_uncertainty,
                            reason_codes=tuple(sorted(set(applied_reasons))),
                        )
                    )
                last_known_applied = applied
                last_known_applied_time_s = time_s
    return tuple(
        sorted(
            events,
            key=lambda item: (
                item.source_path,
                str(item.device_id),
                str(item.boot_id),
                item.device_uptime_ms if item.device_uptime_ms is not None else -1,
                item.seq if item.seq is not None else -1,
                item.event_type,
                item.event_id,
            ),
        )
    )


def _capture_clock_domain(capture: Capture) -> str:
    if capture.time.domain == TIME_BOOT_SCOPED_UPTIME:
        return CLOCK_DEVICE_BOOT_UPTIME
    if capture.time.domain == TIME_EVENT_UTC:
        return CLOCK_DEVICE_EVENT_UTC
    return CLOCK_UNKNOWN


def _row_time_s(
    capture: Capture,
    row: NormalizedRow,
    ordered: Sequence[NormalizedRow],
) -> float | None:
    if capture.time.domain == TIME_BOOT_SCOPED_UPTIME and row.device_ms is not None:
        return row.device_ms / 1000.0
    if row.event_time_utc is not None:
        return row.event_time_utc.astimezone(timezone.utc).timestamp()
    return None


# ---------------------------------------------------------------------------
# A W06 serial command-log adapter
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommandLog:
    """Parsed command-envelope lines plus what was deliberately not parsed."""

    events: tuple[TimelineEvent, ...]
    ignored_telemetry_lines: int
    source_line_count: int


_A_CMDACK_PREFIX = "#CG CMDACK"
_A_CMDACK_REQUIRED = (
    "schema",
    "event",
    "command_id",
    "command_id_form",
    "source",
    "device_id",
    "boot_id",
    "uptime_ms",
    "ack_seq",
    "status",
    "reason",
    "desired_cooling",
    "desired_duty_permille",
    "applied_cooling",
    "applied_duty_permille",
    "reapplied",
    "expiry_evaluable",
    "time_sync_state",
    "device_mode",
)


def load_a_command_events(
    path: str | Path,
    *,
    provenance: str = PROVENANCE_UNVERIFIED,
) -> CommandLog:
    """Parse A's distinct ``#CG CMDACK schema=1`` serial command representation.

    This is a command-envelope adapter, not a telemetry parser. ``#CG TELEM``
    lines are ignored and counted, never translated through the C JSON schema.
    """
    if provenance not in (
        PROVENANCE_HOST_GENERATED_SYNTHETIC,
        PROVENANCE_UNVERIFIED,
    ):
        raise TimingAlignmentError(
            "COMMAND_LOG_PROVENANCE_NOT_ALLOWED",
            "A command logs are host-generated or unverified; they are not "
            "physical command-lifecycle evidence",
        )
    command_path = Path(path)
    if not command_path.is_file():
        raise TimingAlignmentError(
            "SOURCE_NOT_FOUND", f"{command_path.name!r} is not a readable file"
        )
    digest = hashlib.sha256(command_path.read_bytes()).hexdigest()
    events: list[TimelineEvent] = []
    ignored_telemetry = 0
    for line_index, raw in enumerate(
        command_path.read_text(encoding="utf-8", errors="replace").splitlines(),
        start=1,
    ):
        text = raw.strip()
        if not text:
            continue
        if text.startswith("#CG TELEM"):
            ignored_telemetry += 1
            continue
        if not text.startswith(_A_CMDACK_PREFIX):
            continue
        fields = _parse_key_value_command_line(text, line_index)
        if fields.get("schema") != "1":
            raise TimingAlignmentError(
                "ACK_SCHEMA_NOT_COMMAND_ENVELOPE",
                f"line {line_index}: #CG CMDACK schema must be 1 (docs/02 §28.1), "
                f"got {fields.get('schema')!r}",
            )
        if fields.get("event") != "ACK":
            raise TimingAlignmentError(
                "ACK_EVENT_NOT_ACK",
                f"line {line_index}: #CG CMDACK event must be ACK, "
                f"got {fields.get('event')!r}",
            )
        missing = [name for name in _A_CMDACK_REQUIRED if name not in fields]
        if missing:
            raise TimingAlignmentError(
                "ACK_LINE_INCOMPLETE",
                f"line {line_index}: missing command fields {missing}",
            )
        status = fields["status"]
        if status not in ACK_STATUSES:
            raise TimingAlignmentError(
                "ACK_STATUS_NOT_CANONICAL",
                f"line {line_index}: status {status!r} is not in {ACK_STATUSES}",
            )
        uptime = _required_int(fields, "uptime_ms", line_index)
        ack_seq = _required_int(fields, "ack_seq", line_index)
        command_id = fields["command_id"]
        if command_id == "NONE":
            continue
        reason_codes = [
            "ACK_IS_NOT_APPLIED_STATE",
            "NO_COMMAND_PUBLICATION_TIME",
            "DEVICE_UPTIME_IS_BOOT_SCOPED",
        ]
        if provenance == PROVENANCE_HOST_GENERATED_SYNTHETIC:
            reason_codes.append("HOST_GENERATED_SYNTHETIC")
        if fields.get("time_sync_state") != "SYNCHRONIZED":
            reason_codes.append("DEVICE_CLOCK_UNSYNCHRONIZED")
        if fields.get("expiry_evaluable") == "0":
            reason_codes.append("EXPIRY_NOT_EVALUABLE")
        if fields.get("reapplied") == "1":
            reason_codes.append("REAPPLIED_VIOLATION")
        if status == "DUPLICATE_CANONICAL":
            reason_codes.append("DUPLICATE_CANONICAL_REPLY")
        events.append(
            TimelineEvent(
                event_id=_event_id(
                    digest,
                    EVENT_DEVICE_ACK,
                    fields["device_id"],
                    fields["boot_id"],
                    f"{command_id}:{ack_seq}",
                ),
                event_type=EVENT_DEVICE_ACK,
                provenance=provenance,
                source_path=str(command_path),
                source_sha256=digest,
                source_namespace="coldguard.command-ack-serial/v1",
                source_record_index=line_index,
                device_id=fields["device_id"],
                boot_id=fields["boot_id"],
                run_id=None,
                identity_status=IDENTITY_PARTIAL,
                command_id=command_id,
                ack_seq=ack_seq,
                seq=None,
                device_uptime_ms=uptime,
                event_time_utc=None,
                clock_domain=CLOCK_DEVICE_BOOT_UPTIME,
                clock_sync=fields.get("time_sync_state", "UNKNOWN"),
                raw_fields=tuple(sorted(fields.items())),
                normalized_fields=tuple(sorted(fields.items())),
                measurement_quality="NOT_APPLICABLE_PROTOCOL_EVIDENCE",
                uncertainty_s=None,
                source_line_index=line_index,
                eligibility=(
                    ELIGIBILITY_SYNTHETIC_UNIT_TEST
                    if provenance == PROVENANCE_HOST_GENERATED_SYNTHETIC
                    else ELIGIBILITY_UNVERIFIED
                ),
                reason_codes=tuple(sorted(set(reason_codes))),
            )
        )
    # ``#CG TELEM`` lines are counted as ignored by the caller; they are never
    # translated through the C JSON telemetry parser.
    return CommandLog(
        events=tuple(events),
        ignored_telemetry_lines=ignored_telemetry,
        source_line_count=sum(
            1
            for line in command_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
            if line.strip()
        ),
    )


def _parse_key_value_command_line(text: str, line_index: int) -> dict[str, str]:
    tokens = text.split(" ")
    if len(tokens) < 3:
        raise TimingAlignmentError(
            "ACK_LINE_MALFORMED", f"line {line_index}: truncated command line"
        )
    fields: dict[str, str] = {}
    for token in tokens[2:]:
        if "=" not in token:
            raise TimingAlignmentError(
                "ACK_LINE_MALFORMED",
                f"line {line_index}: token without '=': {token!r}",
            )
        key, value = token.split("=", 1)
        if not key or value == "":
            raise TimingAlignmentError(
                "ACK_LINE_MALFORMED",
                f"line {line_index}: empty key or value in {token!r}",
            )
        if key in fields:
            raise TimingAlignmentError(
                "ACK_LINE_MALFORMED",
                f"line {line_index}: duplicate field {key!r}",
            )
        fields[key] = value
    return fields


def _required_int(fields: dict[str, str], name: str, line_index: int) -> int:
    raw = fields.get(name, "")
    if not raw.isdigit():
        raise TimingAlignmentError(
            "ACK_LINE_MALFORMED",
            f"line {line_index}: {name} must be a non-negative integer, got {raw!r}",
        )
    return int(raw)


# ---------------------------------------------------------------------------
# explicit software event fixtures (tests only; never physical evidence)
# ---------------------------------------------------------------------------


def load_event_fixture(path: str | Path) -> tuple[TimelineEvent, ...]:
    """Load an explicitly synthetic W06 event fixture for software tests."""
    fixture_path = Path(path)
    if not fixture_path.is_file():
        raise TimingAlignmentError(
            "SOURCE_NOT_FOUND", f"{fixture_path.name!r} is not a readable file"
        )
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TimingAlignmentError("FIXTURE_MALFORMED", str(exc)) from exc
    if not isinstance(payload, dict):
        raise TimingAlignmentError("FIXTURE_MALFORMED", "fixture must be an object")
    if payload.get("fixture_schema") != W06_EVENT_FIXTURE_SCHEMA:
        raise TimingAlignmentError(
            "FIXTURE_SCHEMA_MISMATCH",
            f"fixture_schema must be {W06_EVENT_FIXTURE_SCHEMA!r}, "
            f"got {payload.get('fixture_schema')!r}",
        )
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        raise TimingAlignmentError("FIXTURE_MALFORMED", "events must be a list")
    digest = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    events: list[TimelineEvent] = []
    for index, item in enumerate(raw_events):
        if not isinstance(item, dict):
            raise TimingAlignmentError(
                "FIXTURE_MALFORMED", f"event {index} must be an object"
            )
        event_type = item.get("event_type")
        clock_domain = item.get("clock_domain", CLOCK_DEVICE_BOOT_UPTIME)
        normalized = item.get("normalized_fields") or {}
        if not isinstance(normalized, dict):
            raise TimingAlignmentError(
                "FIXTURE_MALFORMED", f"event {index} normalized_fields must be an object"
            )
        events.append(
            TimelineEvent(
                event_id=str(item.get("event_id") or f"{digest[:12]}:fixture:{index}"),
                event_type=str(event_type),
                provenance=PROVENANCE_SYNTHETIC_FIXTURE,
                source_path=str(fixture_path),
                source_sha256=digest,
                source_namespace="coldguard.w06-event-fixture/v1",
                source_record_index=_optional_int(item.get("source_record_index")),
                device_id=_optional_str(item.get("device_id")),
                boot_id=_optional_str(item.get("boot_id")),
                run_id=_optional_str(item.get("run_id")),
                identity_status=str(
                    item.get("identity_status")
                    or _identity_status(
                        _optional_str(item.get("device_id")),
                        _optional_str(item.get("boot_id")),
                        _optional_str(item.get("run_id")),
                        _optional_int(item.get("seq")),
                    )
                ),
                command_id=_optional_str(item.get("command_id")),
                ack_seq=_optional_int(item.get("ack_seq")),
                seq=_optional_int(item.get("seq")),
                device_uptime_ms=_optional_int(item.get("device_uptime_ms")),
                event_time_utc=_optional_str(item.get("event_time_utc")),
                backend_received_at=_optional_str(item.get("backend_received_at")),
                persisted_at=_optional_str(item.get("persisted_at")),
                clock_domain=str(clock_domain),
                clock_sync=str(item.get("clock_sync", CLOCK_SYNC_SYNTHETIC_EXACT)),
                raw_fields=(),
                normalized_fields=tuple(
                    sorted(
                        (str(key), "" if value is None else str(value))
                        for key, value in normalized.items()
                    )
                ),
                measurement_quality=str(item.get("measurement_quality", "VALID")),
                uncertainty_s=(
                    float(item["uncertainty_s"])
                    if item.get("uncertainty_s") is not None
                    else None
                ),
                source_line_index=_optional_int(item.get("source_line_index")),
                eligibility=ELIGIBILITY_SYNTHETIC_UNIT_TEST,
                reason_codes=tuple(
                    sorted(
                        set(
                            [str(code) for code in item.get("reason_codes", [])]
                            + ["SYNTHETIC_UNIT_TEST_FIXTURE"]
                        )
                    )
                ),
            )
        )
    return tuple(events)


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TimingAlignmentError("FIXTURE_MALFORMED", "boolean is not an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TimingAlignmentError(
            "FIXTURE_MALFORMED", f"{value!r} is not an integer"
        ) from exc


# ---------------------------------------------------------------------------
# B-W06-01: ordering and partial order
# ---------------------------------------------------------------------------


def order_timeline(
    events: Sequence[TimelineEvent],
    *,
    clock_domain: str | None = None,
    device_id: str | None = None,
    boot_id: str | None = None,
) -> OrderedTimeline:
    """Order events inside one declared clock/boot domain.

    Events that cannot be aligned keep their evidence and reason codes; they are
    never dropped. No cross-domain or cross-boot subtraction happens here.
    """
    materialized = list(events)
    if not materialized:
        return OrderedTimeline(
            status=ORDER_NOT_ALIGNABLE,
            events=(),
            reason_codes=(REASON_NOT_ALIGNABLE,),
            clock_domain=clock_domain,
            device_id=device_id,
            boot_id=boot_id,
        )
    domains = {event.clock_domain for event in materialized}
    if clock_domain is not None and any(
        event.clock_domain != clock_domain for event in materialized
    ):
        return OrderedTimeline(
            status=ORDER_MIXED_CLOCK,
            events=tuple(materialized),
            reason_codes=(REASON_MIXED_CLOCK_DOMAINS,),
            clock_domain=None,
            device_id=device_id,
            boot_id=boot_id,
        )
    if clock_domain is not None:
        domains = {clock_domain}
    if len(domains) > 1:
        return OrderedTimeline(
            status=ORDER_MIXED_CLOCK,
            events=tuple(materialized),
            reason_codes=(REASON_MIXED_CLOCK_DOMAINS,),
            clock_domain=None,
            device_id=device_id,
            boot_id=boot_id,
        )
    domain = next(iter(domains))
    devices = {event.device_id for event in materialized if event.device_id}
    boots = {event.boot_id for event in materialized if event.boot_id}
    if device_id is not None:
        devices = {device_id}
    if boot_id is not None:
        boots = {boot_id}
    if len(devices) > 1:
        return OrderedTimeline(
            status=ORDER_MIXED_DEVICE,
            events=tuple(materialized),
            reason_codes=("MIXED_DEVICE_IDENTITIES",),
            clock_domain=domain,
            device_id=None,
            boot_id=boot_id,
        )
    if len(boots) > 1:
        return OrderedTimeline(
            status=ORDER_MIXED_BOOT,
            events=tuple(materialized),
            reason_codes=(REASON_CROSS_BOOT_REFUSED,),
            clock_domain=domain,
            device_id=next(iter(devices), None),
            boot_id=None,
        )
    if domain == CLOCK_DEVICE_BOOT_UPTIME:
        if any(event.device_uptime_ms is None for event in materialized):
            return OrderedTimeline(
                status=ORDER_MISSING_TIMESTAMP,
                events=tuple(materialized),
                reason_codes=(REASON_MISSING_TIMESTAMP,),
                clock_domain=domain,
                device_id=next(iter(devices), None),
                boot_id=next(iter(boots), None),
            )
        time_of = lambda event: float(event.device_uptime_ms)  # noqa: E731
    elif domain == CLOCK_DEVICE_EVENT_UTC:
        if any(event.event_time_utc is None for event in materialized):
            return OrderedTimeline(
                status=ORDER_MISSING_TIMESTAMP,
                events=tuple(materialized),
                reason_codes=(REASON_MISSING_TIMESTAMP,),
                clock_domain=domain,
                device_id=next(iter(devices), None),
                boot_id=next(iter(boots), None),
            )
        time_of = lambda event: _parse_utc(event.event_time_utc)  # noqa: E731
    else:
        return OrderedTimeline(
            status=ORDER_NOT_ALIGNABLE,
            events=tuple(materialized),
            reason_codes=(REASON_NOT_ALIGNABLE, "NO_EVENT_TIME_DOMAIN"),
            clock_domain=domain,
            device_id=next(iter(devices), None),
            boot_id=next(iter(boots), None),
        )

    source_indexed = [
        event for event in materialized if event.source_record_index is not None
    ]
    by_source = sorted(
        source_indexed, key=lambda event: (event.source_record_index, event.event_id)
    )
    reversal = len(by_source) >= 2 and any(
        time_of(left) > time_of(right)
        for left, right in zip(by_source, by_source[1:])
    )
    ordered = sorted(
        materialized,
        key=lambda event: (
            time_of(event),
            event.seq if event.seq is not None else -1,
            event.event_id,
        ),
    )
    reasons: list[str] = []
    if reversal:
        reasons.extend([REASON_TIME_REVERSAL, REASON_AMBIGUOUS_ORDER])
    if domain == CLOCK_DEVICE_EVENT_UTC and any(
        event.clock_sync not in (CLOCK_SYNC_EVIDENCED, CLOCK_SYNC_SYNTHETIC_EXACT)
        for event in materialized
    ):
        reasons.append("CLOCK_SYNC_UNVERIFIED_FOR_ABSOLUTE_LATENCY")
    return OrderedTimeline(
        status=ORDER_AMBIGUOUS if reversal else ORDERED_IN_DOMAIN,
        events=tuple(ordered if not reversal else by_source),
        reason_codes=tuple(sorted(set(reasons))),
        clock_domain=domain,
        device_id=next(iter(devices), None),
        boot_id=next(iter(boots), None),
    )


def partial_order(events: Sequence[TimelineEvent]) -> tuple[ProtocolRelation, ...]:
    """Protocol-stage relations only; never a measured latency claim."""
    stage_rank = {
        EVENT_COMMAND_CREATED_OR_PUBLISHED: 0,
        EVENT_DEVICE_ACK: 1,
        EVENT_APPLIED_STATE: 2,
        EVENT_ELECTRICAL_RESPONSE: 3,
        EVENT_THERMAL_RESPONSE: 4,
    }
    by_command: dict[tuple[str, str | None, str | None], list[TimelineEvent]] = {}
    for event in events:
        if event.command_id is None:
            continue
        if event.event_type not in stage_rank:
            continue
        by_command.setdefault(
            (event.command_id, event.device_id, event.boot_id), []
        ).append(event)
    relations: list[ProtocolRelation] = []
    for key in sorted(by_command, key=lambda item: str(item)):
        command_id = key[0]
        items = sorted(
            by_command[key],
            key=lambda event: (
                stage_rank[event.event_type],
                event.event_id,
                event.ack_seq if event.ack_seq is not None else -1,
            ),
        )
        for left, right in zip(items, items[1:]):
            if stage_rank[left.event_type] < stage_rank[right.event_type]:
                relations.append(
                    ProtocolRelation(
                        before_event_id=left.event_id,
                        after_event_id=right.event_id,
                        command_id=command_id,
                        relation=(
                            f"{left.event_type}_BEFORE_{right.event_type}"
                        ),
                        latency_claim=False,
                    )
                )
            elif (
                left.event_type == EVENT_DEVICE_ACK
                and right.event_type == EVENT_DEVICE_ACK
                and right.field("status") == "DUPLICATE_CANONICAL"
            ):
                relations.append(
                    ProtocolRelation(
                        before_event_id=left.event_id,
                        after_event_id=right.event_id,
                        command_id=command_id,
                        relation="ACK_BEFORE_DUPLICATE_CANONICAL_REPLY",
                        latency_claim=False,
                    )
                )
    return tuple(relations)


def _parse_utc(value: str | None) -> float:
    if value is None:
        raise TimingAlignmentError("MISSING_TIMESTAMP", "event has no UTC time")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


# ---------------------------------------------------------------------------
# B-W06-02: clock, sequence and provenance diagnostics
# ---------------------------------------------------------------------------


def audit_timeline(
    events: Sequence[TimelineEvent],
    *,
    expected_sequence_step: int = 1,
) -> TimingAudit:
    groups: dict[tuple[str, str | None, str | None], list[TimelineEvent]] = {}
    for event in events:
        groups.setdefault(
            (event.clock_domain, event.device_id, event.boot_id), []
        ).append(event)
    domains: list[DomainAudit] = []
    all_reasons: set[str] = set()
    for key in sorted(groups, key=lambda item: str(item)):
        domain, device_id, boot_id = key
        items = groups[key]
        primary = [
            event
            for event in items
            if event.event_type
            in (
                EVENT_TELEMETRY_SAMPLE,
                EVENT_DOOR_TRANSITION,
                EVENT_APPLIED_STATE,
            )
        ] or items
        if all(event.source_record_index is not None for event in primary):
            primary_order = sorted(
                primary,
                key=lambda event: (
                    event.source_record_index,
                    event.event_id,
                ),
            )
        else:
            primary_order = sorted(
                primary,
                key=lambda event: (
                    _primary_event_time(domain, event)
                    if _primary_event_time(domain, event) is not None
                    else float("inf"),
                    event.event_id,
                ),
            )
        source_timed = [
            (time_s, event)
            for event in primary_order
            for time_s in [_primary_event_time(domain, event)]
            if time_s is not None
        ]
        missing_capture = sum(
            1 for event in primary if event.event_time_utc is None
        )
        missing_receive = sum(
            1 for event in primary if event.backend_received_at is None
        )
        times = [time_s for time_s, _event in source_timed]
        intervals = [
            round(right - left, 9)
            for left, right in zip(times, times[1:])
        ]
        positive = [value for value in intervals if value > 0]
        sequence_values = [
            event.seq
            for event in primary_order
            if event.event_type == EVENT_TELEMETRY_SAMPLE and event.seq is not None
        ]
        gaps = sum(
            1
            for left, right in zip(sequence_values, sequence_values[1:])
            if right - left > expected_sequence_step
        )
        seq_reversals = sum(
            1
            for left, right in zip(sequence_values, sequence_values[1:])
            if right < left
        )
        seq_duplicates = len(sequence_values) - len(set(sequence_values))
        uptimes = [
            event.device_uptime_ms
            for event in primary_order
            if event.device_uptime_ms is not None
        ]
        uptime_resets = sum(
            1 for left, right in zip(uptimes, uptimes[1:]) if right < left
        )
        timestamp_reversals = sum(1 for value in intervals if value < 0)
        capture_receive_conflicts = 0
        for event in primary:
            if (
                event.event_time_utc is not None
                and event.backend_received_at is not None
                and _parse_utc(event.backend_received_at)
                < _parse_utc(event.event_time_utc)
            ):
                capture_receive_conflicts += 1
        uncertain_associations = sum(
            1
            for event in primary
            if event.event_type in (EVENT_DEVICE_ACK, EVENT_APPLIED_STATE)
            and event.command_id is None
        )
        uncertainties = [
            event.uncertainty_s
            for event in primary
            if event.uncertainty_s is not None
        ]
        reasons: set[str] = set()
        if any(_primary_event_time(domain, event) is None for event in primary):
            reasons.add(REASON_MISSING_TIMESTAMP)
        if timestamp_reversals or seq_reversals or uptime_resets:
            reasons.add(REASON_TIME_REVERSAL)
        if capture_receive_conflicts:
            reasons.add("CAPTURE_RECEIVE_ORDER_CONFLICT")
        if missing_capture:
            reasons.add("MISSING_CAPTURE_TIME")
        if missing_receive:
            reasons.add("MISSING_RECEIVE_TIME")
        if uncertain_associations:
            reasons.add("UNCERTAIN_CROSS_STREAM_ASSOCIATION")
        if any(value < 0 for value in intervals):
            reasons.add("IMPOSSIBLE_NEGATIVE_INTERVAL")
        if seq_duplicates:
            reasons.add("SEQUENCE_DUPLICATE_PRESENT")
        if gaps:
            reasons.add("SEQUENCE_GAP_PRESENT")
        domains.append(
            DomainAudit(
                clock_domain=domain,
                device_id=device_id,
                boot_id=boot_id,
                event_count=len(items),
                first_time=min(times) if times else None,
                last_time=max(times) if times else None,
                monotonic=not (timestamp_reversals or seq_reversals or uptime_resets),
                timestamp_reversals=timestamp_reversals,
                sequence_gaps=gaps,
                sequence_reversals=seq_reversals,
                sequence_duplicates=seq_duplicates,
                uptime_resets=uptime_resets,
                capture_receive_conflicts=capture_receive_conflicts,
                missing_capture_times=missing_capture,
                missing_receive_times=missing_receive,
                impossible_negative_intervals=sum(
                    1 for value in intervals if value < 0
                ),
                uncertain_cross_stream_associations=uncertain_associations,
                max_uncertainty_s=max(uncertainties) if uncertainties else None,
                median_interval_s=_percentile(positive, 0.5),
                p95_interval_s=_percentile(positive, 0.95),
                reason_codes=tuple(sorted(reasons)),
            )
        )
        all_reasons.update(reasons)
    return TimingAudit(
        domains=tuple(domains), reason_codes=tuple(sorted(all_reasons))
    )


def _primary_event_time(domain: str, event: TimelineEvent) -> float | None:
    if domain == CLOCK_DEVICE_BOOT_UPTIME and event.device_uptime_ms is not None:
        return event.device_uptime_ms / 1000.0
    if domain == CLOCK_DEVICE_EVENT_UTC and event.event_time_utc is not None:
        return _parse_utc(event.event_time_utc)
    return None


def _domain_times(
    domain: str, events: Sequence[TimelineEvent]
) -> tuple[list[float], tuple[str, ...]]:
    reasons: list[str] = []
    times: list[float] = []
    for event in events:
        if domain == CLOCK_DEVICE_BOOT_UPTIME and event.device_uptime_ms is not None:
            times.append(event.device_uptime_ms / 1000.0)
        elif domain == CLOCK_DEVICE_EVENT_UTC and event.event_time_utc is not None:
            times.append(_parse_utc(event.event_time_utc))
        else:
            reasons.append(REASON_MISSING_TIMESTAMP)
    return times, tuple(sorted(set(reasons)))


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


# ---------------------------------------------------------------------------
# B-W06-04: deterministic duplicate handling
# ---------------------------------------------------------------------------


def _event_identity_key(event: TimelineEvent) -> tuple[Any, ...] | None:
    if event.event_type in (EVENT_DEVICE_ACK,):
        if (
            event.command_id is None
            or event.device_id is None
            or event.boot_id is None
            or event.ack_seq is None
        ):
            return None
        return ("ack", event.command_id, event.device_id, event.boot_id, event.ack_seq)
    if event.event_type == EVENT_COMMAND_CREATED_OR_PUBLISHED:
        if event.command_id is None or event.boot_id is None:
            return None
        return (
            "command",
            event.command_id,
            event.device_id or event.source_sha256,
            event.boot_id,
        )
    if event.event_type in (
        EVENT_TELEMETRY_SAMPLE,
        EVENT_DOOR_TRANSITION,
        EVENT_APPLIED_STATE,
    ):
        if event.boot_id is None or event.seq is None:
            return None
        device = event.device_id or f"source:{event.source_sha256}"
        subtype = event.field("event_subtype") or event.event_type
        return ("telemetry", device, event.boot_id, event.seq, subtype)
    return None


def _event_signature(event: TimelineEvent) -> tuple[Any, ...]:
    return (
        event.event_type,
        event.raw_fields,
        event.normalized_fields,
        event.measurement_quality,
        event.device_uptime_ms,
        event.event_time_utc,
        event.clock_domain,
        event.clock_sync,
    )


def deduplicate_events(events: Sequence[TimelineEvent]) -> DedupResult:
    ordered = sorted(events, key=lambda event: event.event_id)
    groups: dict[tuple[Any, ...], list[TimelineEvent]] = {}
    missing: list[TimelineEvent] = []
    for event in ordered:
        key = _event_identity_key(event)
        if key is None:
            missing.append(event)
        else:
            groups.setdefault(key, []).append(event)

    canonical: list[TimelineEvent] = []
    contradictory: list[TimelineEvent] = []
    duplicate_deliveries = 0
    contradictory_identity_count = 0
    reasons: set[str] = set()
    for key in sorted(groups, key=lambda item: str(item)):
        items = groups[key]
        signatures = {_event_signature(event) for event in items}
        if len(signatures) > 1:
            contradictory.extend(items)
            contradictory_identity_count += 1
            reasons.add("CONTRADICTORY_IDENTITY")
            continue
        representative = items[0]
        if len(items) > 1:
            duplicate_deliveries += len(items) - 1
            reasons.add("IDENTICAL_DUPLICATE_DELIVERY")
        canonical.append(replace(representative, delivery_count=len(items)))

    duplicate_canonical = sum(
        1
        for event in canonical
        if event.event_type == EVENT_DEVICE_ACK
        and event.field("status") == "DUPLICATE_CANONICAL"
    )
    acks_by_command: dict[str, list[TimelineEvent]] = {}
    for event in canonical:
        if event.event_type == EVENT_DEVICE_ACK and event.command_id:
            acks_by_command.setdefault(event.command_id, []).append(event)
    multiple_without_canonical = 0
    for command_id, acks in acks_by_command.items():
        if len(acks) > 1 and not any(
            event.field("status") == "DUPLICATE_CANONICAL" for event in acks
        ):
            multiple_without_canonical += 1
            reasons.add("MULTIPLE_ACKS_WITHOUT_DUPLICATE_CANONICAL")
        boots = {event.boot_id for event in acks if event.boot_id}
        if len(boots) > 1:
            reasons.add("REBOOT_RESETS_IDENTITY")
    reboot_resets = sum(
        1
        for acks in acks_by_command.values()
        if len({event.boot_id for event in acks if event.boot_id}) > 1
    )
    new_commands_same_action = _new_commands_same_action(canonical)
    if new_commands_same_action:
        reasons.add("NEW_COMMAND_SAME_ACTION")
    if duplicate_canonical:
        reasons.add("DUPLICATE_CANONICAL_REPLY")
    if missing:
        reasons.add("MISSING_IDENTITY")
    if contradictory:
        reasons.add("CONTRADICTORY_IDENTITY")
    return DedupResult(
        canonical_events=tuple(
            sorted(canonical, key=lambda event: event.event_id)
        ),
        contradictory_events=tuple(
            sorted(contradictory, key=lambda event: event.event_id)
        ),
        missing_identity_events=tuple(
            sorted(missing, key=lambda event: event.event_id)
        ),
        duplicate_deliveries=duplicate_deliveries,
        contradictory_identity_count=contradictory_identity_count,
        duplicate_canonical_acks=duplicate_canonical,
        multiple_ack_without_canonical=multiple_without_canonical,
        reboot_identity_resets=reboot_resets,
        new_commands_same_action=new_commands_same_action,
        reason_codes=tuple(sorted(reasons)),
    )


def _new_commands_same_action(events: Sequence[TimelineEvent]) -> int:
    action_to_commands: dict[tuple[str, str], set[str]] = {}
    seen: set[str] = set()
    for event in events:
        if event.command_id is None:
            continue
        if event.event_type not in (
            EVENT_COMMAND_CREATED_OR_PUBLISHED,
            EVENT_DEVICE_ACK,
        ):
            continue
        if event.command_id in seen:
            continue
        seen.add(event.command_id)
        cooling = event.field("desired_cooling") or ""
        duty = event.field("desired_duty_permille") or ""
        action_to_commands.setdefault((cooling, duty), set()).add(event.command_id)
    return sum(
        max(0, len(commands) - 1) for commands in action_to_commands.values()
    )


# ---------------------------------------------------------------------------
# B-W06-03: bounded response analysis
# ---------------------------------------------------------------------------


def analyze_response(
    relationship: str,
    anchor: TimelineEvent | None,
    samples: Sequence[TimelineEvent],
    policy: ResponsePolicy,
    *,
    anchor_quality: str | None = None,
    anchor_overall_quality: str | None = None,
) -> ResponseResult:
    """Detect a sustained response after an explicit anchor.

    A missing response is never a zero-second response. Numeric latency is
    returned only for a synthetic unit-test control or for physical evidence
    whose anchor, channel quality and clock evidence are qualified.
    """
    if anchor is None:
        return _response(
            relationship,
            RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR,
            None,
            None,
            None,
            None,
            0,
            None,
            policy,
            ["NO_ANCHOR_EVENT"],
        )
    anchor_time, anchor_reason = _event_time(anchor)
    if anchor_time is None:
        return _response(
            relationship,
            RESPONSE_NOT_ESTIMABLE_CLOCK,
            anchor.command_id,
            anchor.event_id,
            None,
            None,
            None,
            0,
            None,
            policy,
            [anchor_reason or REASON_MISSING_TIMESTAMP],
        )
    if anchor.clock_domain == CLOCK_DEVICE_EVENT_UTC and anchor.clock_sync not in (
        CLOCK_SYNC_EVIDENCED,
        CLOCK_SYNC_SYNTHETIC_EXACT,
    ):
        return _response(
            relationship,
            RESPONSE_NOT_ESTIMABLE_CLOCK,
            anchor.command_id,
            anchor.event_id,
            None,
            None,
            None,
            0,
            None,
            policy,
            ["UNVERIFIED_CLOCK_SYNC"],
        )

    compatible: list[tuple[float, TimelineEvent]] = []
    quality_excluded = 0
    for sample in samples:
        if not _same_stream(anchor, sample):
            continue
        sample_time, _ = _event_time(sample)
        if sample_time is None:
            continue
        value = _response_value(sample, policy.channel)
        quality = _response_quality(sample, policy.quality_key)
        if value is None or quality != "VALID":
            quality_excluded += 1
            continue
        compatible.append((sample_time, sample))
    compatible.sort(key=lambda item: (item[0], item[1].event_id))

    baseline = [
        value
        for time_s, sample in compatible
        if anchor_time - policy.baseline_window_s <= time_s < anchor_time
        for value in [_response_value(sample, policy.channel)]
        if value is not None
    ]
    if not baseline:
        baseline_quality_excluded = sum(
            1
            for sample in samples
            if _same_stream(anchor, sample)
            and (sample_time := _event_time(sample)[0]) is not None
            and anchor_time - policy.baseline_window_s <= sample_time < anchor_time
            and (
                _response_value(sample, policy.channel) is None
                or _response_quality(sample, policy.quality_key) != "VALID"
            )
        )
        if baseline_quality_excluded:
            return _response(
                relationship,
                RESPONSE_NOT_ESTIMABLE_QUALITY,
                anchor.command_id,
                anchor.event_id,
                None,
                None,
                "NOT_ESTIMABLE",
                0,
                None,
                policy,
                ["BASELINE_QUALITY_NOT_VALID"],
            )
        return _response(
            relationship,
            RESPONSE_NOT_ESTIMABLE_BASELINE,
            anchor.command_id,
            anchor.event_id,
            None,
            None,
            None,
            0,
            None,
            policy,
            ["BASELINE_NOT_OBSERVED"]
            + (["QUALITY_EXCLUDED_SAMPLES"] if quality_excluded else []),
        )
    baseline_median = statistics.median(baseline)

    post = [
        (time_s, sample)
        for time_s, sample in compatible
        if anchor_time <= time_s <= anchor_time + policy.max_window_s
    ]
    if not post:
        post_quality_excluded = sum(
            1
            for sample in samples
            if _same_stream(anchor, sample)
            and (sample_time := _event_time(sample)[0]) is not None
            and anchor_time <= sample_time <= anchor_time + policy.max_window_s
            and (
                _response_value(sample, policy.channel) is None
                or _response_quality(sample, policy.quality_key) != "VALID"
            )
        )
        if post_quality_excluded:
            return _response(
                relationship,
                RESPONSE_NOT_ESTIMABLE_QUALITY,
                anchor.command_id,
                anchor.event_id,
                None,
                None,
                "NOT_ESTIMABLE",
                0,
                baseline_median,
                policy,
                ["NO_QUALITY_VALID_POST_ANCHOR_SAMPLES"],
            )
        return _response(
            relationship,
            RESPONSE_CENSORED,
            anchor.command_id,
            anchor.event_id,
            None,
            None,
            "NOT_ESTIMABLE",
            0,
            baseline_median,
            policy,
            ["NO_POST_ANCHOR_SAMPLES_IN_WINDOW"],
        )

    direction = 1.0 if policy.expected_direction == "UP" else -1.0
    sustained: list[tuple[float, TimelineEvent]] = []
    previous_time: float | None = None
    gap_seen_before_response = False
    opposite_sustained = False
    reverse_run = 0
    for time_s, sample in post:
        if previous_time is not None and time_s - previous_time > policy.max_gap_s:
            if policy.gap_policy == "CENSOR" and not sustained:
                gap_seen_before_response = True
                break
            if policy.gap_policy == "CENSOR":
                break
            sustained = []
            reverse_run = 0
        previous_time = time_s
        value = _response_value(sample, policy.channel)
        if value is None:
            continue
        delta = (value - baseline_median) * direction
        reverse_delta = (value - baseline_median) * -direction
        if delta >= policy.min_change:
            sustained.append((time_s, sample))
            if len(sustained) >= policy.sustained_observations:
                break
        else:
            sustained = []
        if reverse_delta >= policy.min_change:
            reverse_run += 1
            if reverse_run >= policy.sustained_observations:
                opposite_sustained = True
        else:
            reverse_run = 0

    if len(sustained) >= policy.sustained_observations:
        onset_time, onset_sample = sustained[0]
        latency = round(onset_time - anchor_time, 6)
        uncertainty = _response_uncertainty(anchor, onset_sample, policy)
        evidence_class = _evidence_class(anchor, onset_sample)
        if latency < 0:
            return _response(
                relationship,
                RESPONSE_CONTRADICTORY_EVIDENCE,
                anchor.command_id,
                anchor.event_id,
                None,
                uncertainty,
                evidence_class,
                len(sustained),
                baseline_median,
                policy,
                ["NEGATIVE_RESPONSE_INTERVAL"],
            )
        if (
            policy.max_uncertainty_s is not None
            and uncertainty is not None
            and uncertainty > policy.max_uncertainty_s
        ):
            return _response(
                relationship,
                RESPONSE_NOT_ESTIMABLE_UNCERTAINTY,
                anchor.command_id,
                anchor.event_id,
                None,
                uncertainty,
                evidence_class,
                len(sustained),
                baseline_median,
                policy,
                ["UNCERTAINTY_EXCEEDS_ANALYSIS_BOUND"],
            )
        qualified = evidence_class == "PHYSICAL_MEASURED" and (
            anchor.clock_domain != CLOCK_DEVICE_EVENT_UTC
            or anchor.clock_sync == CLOCK_SYNC_EVIDENCED
        )
        if evidence_class == "SYNTHETIC_UNIT_TEST":
            return _response(
                relationship,
                RESPONSE_OBSERVED_DIAGNOSTIC_ONLY,
                anchor.command_id,
                anchor.event_id,
                latency,
                uncertainty,
                evidence_class,
                len(sustained),
                baseline_median,
                policy,
                ["SYNTHETIC_UNIT_TEST_EVIDENCE"],
            )
        if not qualified:
            return _response(
                relationship,
                RESPONSE_NOT_ESTIMABLE_CLOCK,
                anchor.command_id,
                anchor.event_id,
                None,
                uncertainty,
                evidence_class,
                len(sustained),
                baseline_median,
                policy,
                ["MIXED_OR_UNVERIFIED_CLOCK_DOMAIN"],
            )
        channel_quality = (
            anchor_quality
            if anchor_quality is not None
            else _response_quality(anchor, policy.quality_key)
        )
        overall_quality = (
            anchor_overall_quality
            if anchor_overall_quality is not None
            else anchor.measurement_quality
        )
        if channel_quality == "INVALID" or overall_quality == "INVALID":
            return _response(
                relationship,
                RESPONSE_NOT_ESTIMABLE_QUALITY,
                anchor.command_id,
                anchor.event_id,
                None,
                uncertainty,
                evidence_class,
                len(sustained),
                baseline_median,
                policy,
                ["ANCHOR_QUALITY_INVALID"],
            )
        if channel_quality != "VALID" or overall_quality != "VALID":
            return _response(
                relationship,
                RESPONSE_OBSERVED_DIAGNOSTIC_ONLY,
                anchor.command_id,
                anchor.event_id,
                latency,
                uncertainty,
                evidence_class,
                len(sustained),
                baseline_median,
                policy,
                ["ANCHOR_QUALITY_NOT_VALID_DIAGNOSTIC_ONLY"],
            )
        return _response(
            relationship,
            RESPONSE_VERIFIED_MEASURED_RESPONSE,
            anchor.command_id,
            anchor.event_id,
            latency,
            uncertainty,
            evidence_class,
            len(sustained),
            baseline_median,
            policy,
            [],
        )

    window_end = anchor_time + policy.max_window_s
    last_time = post[-1][0]
    if opposite_sustained:
        state = RESPONSE_CONTRADICTORY_EVIDENCE
        reasons = ["SUSTAINED_CHANGE_OPPOSITE_TO_EXPECTED_DIRECTION"]
    elif gap_seen_before_response:
        state = RESPONSE_CENSORED
        reasons = ["OBSERVATION_GAP_BEFORE_RESPONSE"]
    elif last_time < window_end:
        state = RESPONSE_CENSORED
        reasons = ["ANALYSIS_WINDOW_INCOMPLETE"]
    else:
        state = RESPONSE_NOT_OBSERVED
        reasons = ["NO_SUSTAINED_CHANGE_ABOVE_ANALYSIS_FLOOR"]
    if quality_excluded:
        reasons.append("QUALITY_EXCLUDED_SAMPLES")
    return _response(
        relationship,
        state,
        anchor.command_id,
        anchor.event_id,
        None,
        None,
        _evidence_class(anchor, post[0][1]),
        len(post),
        baseline_median,
        policy,
        reasons,
    )


def _response(
    relationship: str,
    state: str,
    command_id: str | None,
    anchor_event_id: str | None,
    latency_s: float | None,
    uncertainty_s: float | None,
    evidence_class: str | None,
    sample_count: int,
    baseline_median: float | None,
    policy: ResponsePolicy,
    reasons: Sequence[str],
) -> ResponseResult:
    return ResponseResult(
        relationship=relationship,
        state=state,
        command_id=command_id,
        anchor_event_id=anchor_event_id,
        latency_s=latency_s,
        uncertainty_s=uncertainty_s,
        evidence_class=evidence_class or "NOT_ESTIMABLE",
        independent_application=None,
        sample_count=sample_count,
        baseline_median=baseline_median,
        policy_name=policy.name,
        reason_codes=tuple(sorted(set(reasons))),
    )


def _event_time(event: TimelineEvent) -> tuple[float | None, str | None]:
    if event.clock_domain == CLOCK_DEVICE_BOOT_UPTIME:
        if event.device_uptime_ms is None:
            return None, REASON_MISSING_TIMESTAMP
        return event.device_uptime_ms / 1000.0, None
    if event.clock_domain == CLOCK_DEVICE_EVENT_UTC:
        if event.event_time_utc is None:
            return None, REASON_MISSING_TIMESTAMP
        return _parse_utc(event.event_time_utc), None
    return None, "NO_ANALYZABLE_EVENT_TIME_DOMAIN"


def _same_stream(anchor: TimelineEvent, sample: TimelineEvent) -> bool:
    if anchor.clock_domain != sample.clock_domain:
        return False
    if anchor.device_id and sample.device_id and anchor.device_id != sample.device_id:
        return False
    if anchor.boot_id and sample.boot_id and anchor.boot_id != sample.boot_id:
        return False
    if not anchor.device_id and not sample.device_id:
        return anchor.source_sha256 == sample.source_sha256
    return True


def _response_value(event: TimelineEvent, channel: str) -> float | None:
    raw = event.field(channel)
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _response_quality(event: TimelineEvent, quality_key: str) -> str | None:
    return event.field(f"quality.{quality_key}") or None


def _response_uncertainty(
    anchor: TimelineEvent, sample: TimelineEvent, policy: ResponsePolicy
) -> float | None:
    components = [
        value
        for value in (anchor.uncertainty_s, sample.uncertainty_s)
        if value is not None
    ]
    if not components:
        return None
    return round(max(components), 6)


def _evidence_class(anchor: TimelineEvent, sample: TimelineEvent) -> str:
    if (
        anchor.provenance == PROVENANCE_PHYSICAL_MEASURED
        and sample.provenance == PROVENANCE_PHYSICAL_MEASURED
    ):
        return "PHYSICAL_MEASURED"
    if (
        anchor.provenance
        in (PROVENANCE_HOST_GENERATED_SYNTHETIC, PROVENANCE_SYNTHETIC_FIXTURE)
        or sample.provenance
        in (PROVENANCE_HOST_GENERATED_SYNTHETIC, PROVENANCE_SYNTHETIC_FIXTURE)
    ):
        return "SYNTHETIC_UNIT_TEST"
    return "UNVERIFIED"


def command_to_ack(
    command_events: Sequence[TimelineEvent],
    ack_events: Sequence[TimelineEvent],
) -> tuple[ResponseResult, ...]:
    """Command-publication → ACK latency, or an explicit non-estimable reason."""
    commands_by_id: dict[str, list[TimelineEvent]] = {}
    for event in command_events:
        if event.event_type == EVENT_COMMAND_CREATED_OR_PUBLISHED and event.command_id:
            commands_by_id.setdefault(event.command_id, []).append(event)
    acks_by_id: dict[str, list[TimelineEvent]] = {}
    for event in ack_events:
        if event.event_type == EVENT_DEVICE_ACK and event.command_id:
            acks_by_id.setdefault(event.command_id, []).append(event)
    results: list[ResponseResult] = []
    for command_id in sorted(set(commands_by_id) | set(acks_by_id)):
        command = _first_by_time(commands_by_id.get(command_id, []))
        ack = _first_by_time(acks_by_id.get(command_id, []))
        if command is None:
            results.append(
                _response(
                    "COMMAND_TO_ACK",
                    RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR,
                    command_id,
                    ack.event_id if ack else None,
                    None,
                    None,
                    "NOT_ESTIMABLE",
                    1 if ack else 0,
                    None,
                    DEFAULT_ELECTRICAL_POLICY,
                    [
                        "NO_COMMAND_PUBLICATION_EVENT",
                        "ACK_RELATIVE_LATENCY_IS_NOT_COMMAND_PUBLICATION_LATENCY",
                    ],
                )
            )
            continue
        if ack is None:
            results.append(
                _response(
                    "COMMAND_TO_ACK",
                    RESPONSE_NOT_OBSERVED,
                    command_id,
                    command.event_id,
                    None,
                    None,
                    _evidence_class(command, command),
                    0,
                    None,
                    DEFAULT_ELECTRICAL_POLICY,
                    ["NO_ACK_FOR_COMMAND"],
                )
            )
            continue
        start, start_reason = _event_time(command)
        end, end_reason = _event_time(ack)
        if start is None or end is None:
            results.append(
                _response(
                    "COMMAND_TO_ACK",
                    RESPONSE_NOT_ESTIMABLE_CLOCK,
                    command_id,
                    command.event_id,
                    None,
                    None,
                    _evidence_class(command, ack),
                    2,
                    None,
                    DEFAULT_ELECTRICAL_POLICY,
                    [start_reason or end_reason or REASON_MISSING_TIMESTAMP],
                )
            )
            continue
        if command.clock_domain != ack.clock_domain or not _same_stream(command, ack):
            results.append(
                _response(
                    "COMMAND_TO_ACK",
                    RESPONSE_NOT_ESTIMABLE_CLOCK,
                    command_id,
                    command.event_id,
                    None,
                    None,
                    _evidence_class(command, ack),
                    2,
                    None,
                    DEFAULT_ELECTRICAL_POLICY,
                    ["MIXED_CLOCK_DOMAIN_OR_STREAM"],
                )
            )
            continue
        if (
            command.clock_domain == CLOCK_DEVICE_EVENT_UTC
            and (
                command.clock_sync != CLOCK_SYNC_SYNTHETIC_EXACT
                and ack.clock_sync != CLOCK_SYNC_SYNTHETIC_EXACT
            )
            and (
                command.clock_sync != CLOCK_SYNC_EVIDENCED
                or ack.clock_sync != CLOCK_SYNC_EVIDENCED
            )
        ):
            results.append(
                _response(
                    "COMMAND_TO_ACK",
                    RESPONSE_NOT_ESTIMABLE_CLOCK,
                    command_id,
                    command.event_id,
                    None,
                    None,
                    _evidence_class(command, ack),
                    2,
                    None,
                    DEFAULT_ELECTRICAL_POLICY,
                    ["UNVERIFIED_CLOCK_SYNC"],
                )
            )
            continue
        latency = round(end - start, 6)
        evidence = _evidence_class(command, ack)
        if latency < 0:
            state = RESPONSE_CONTRADICTORY_EVIDENCE
            reasons = ["NEGATIVE_COMMAND_TO_ACK_INTERVAL"]
        elif evidence == "SYNTHETIC_UNIT_TEST":
            state = RESPONSE_OBSERVED_DIAGNOSTIC_ONLY
            reasons = ["SYNTHETIC_UNIT_TEST_EVIDENCE"]
        elif command.clock_domain == CLOCK_DEVICE_EVENT_UTC and (
            command.clock_sync != CLOCK_SYNC_EVIDENCED
            or ack.clock_sync != CLOCK_SYNC_EVIDENCED
        ):
            state = RESPONSE_NOT_ESTIMABLE_CLOCK
            reasons = ["UNVERIFIED_CLOCK_SYNC"]
        else:
            state = RESPONSE_VERIFIED_MEASURED_RESPONSE
            reasons = []
        results.append(
            _response(
                "COMMAND_TO_ACK",
                state,
                command_id,
                command.event_id,
                latency if state in (
                    RESPONSE_OBSERVED_DIAGNOSTIC_ONLY,
                    RESPONSE_VERIFIED_MEASURED_RESPONSE,
                ) else None,
                _response_uncertainty(command, ack, DEFAULT_ELECTRICAL_POLICY),
                evidence,
                2,
                None,
                DEFAULT_ELECTRICAL_POLICY,
                reasons,
            )
        )
    return tuple(results)


def command_to_response(
    command_events: Sequence[TimelineEvent],
    applied_events: Sequence[TimelineEvent],
    samples: Sequence[TimelineEvent],
    policy: ResponsePolicy,
    *,
    relationship: str,
) -> tuple[ResponseResult, ...]:
    """Command-publication → observed plant response, only with applied evidence.

    The applied-state event is a required chain link. A change after a command
    without applied evidence is not attributed to the command.
    """
    results: list[ResponseResult] = []
    for command in sorted(
        (
            event
            for event in command_events
            if event.event_type == EVENT_COMMAND_CREATED_OR_PUBLISHED
            and event.command_id is not None
        ),
        key=lambda event: event.event_id,
    ):
        applied = [
            event
            for event in applied_events
            if event.event_type == EVENT_APPLIED_STATE
            and event.command_id == command.command_id
            and _same_stream(command, event)
        ]
        if not applied:
            results.append(
                _response(
                    relationship,
                    RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR,
                    command.command_id,
                    command.event_id,
                    None,
                    None,
                    "NOT_ESTIMABLE",
                    0,
                    None,
                    policy,
                    [
                        "NO_APPLIED_STATE_EVIDENCE",
                        "COMMAND_TO_RESPONSE_REQUIRES_APPLIED_CHAIN_LINK",
                    ],
                )
            )
            continue
        results.append(
            analyze_response(
                relationship,
                command,
                samples,
                policy,
                anchor_quality=_response_quality(applied[0], policy.quality_key),
                anchor_overall_quality=applied[0].measurement_quality,
            )
        )
    return tuple(results)


def ack_to_applied(
    ack_events: Sequence[TimelineEvent],
    applied_events: Sequence[TimelineEvent],
) -> tuple[ResponseResult, ...]:
    results: list[ResponseResult] = []
    acks_by_id: dict[str, list[TimelineEvent]] = {}
    for event in ack_events:
        if event.event_type == EVENT_DEVICE_ACK and event.command_id:
            acks_by_id.setdefault(event.command_id, []).append(event)
    applied_by_id: dict[str, list[TimelineEvent]] = {}
    for event in applied_events:
        if event.event_type == EVENT_APPLIED_STATE and event.command_id:
            applied_by_id.setdefault(event.command_id, []).append(event)
    for command_id in sorted(set(acks_by_id) | set(applied_by_id)):
        ack = _first_by_time(acks_by_id.get(command_id, []))
        applied = _first_by_time(applied_by_id.get(command_id, []))
        if ack is None:
            results.append(
                _response(
                    "ACK_TO_APPLIED_STATE",
                    RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR,
                    command_id,
                    applied.event_id if applied else None,
                    None,
                    None,
                    "NOT_ESTIMABLE",
                    1 if applied else 0,
                    None,
                    DEFAULT_ELECTRICAL_POLICY,
                    ["NO_ACK_ANCHOR_EVENT"],
                )
            )
            continue
        status = ack.field("status")
        if status == "DUPLICATE_CANONICAL":
            results.append(
                replace(
                    _response(
                        "ACK_TO_APPLIED_STATE",
                        RESPONSE_DUPLICATE_CANONICAL_NOT_APPLICATION,
                        command_id,
                        ack.event_id,
                        None,
                        None,
                        _evidence_class(ack, applied or ack),
                        1 if applied else 0,
                        None,
                        DEFAULT_ELECTRICAL_POLICY,
                        [
                            "DUPLICATE_CANONICAL_DOES_NOT_COUNT_AS_ANOTHER_APPLICATION"
                        ],
                    ),
                    independent_application=False,
                )
            )
            continue
        if status not in ACK_ACCEPT_STATUSES:
            results.append(
                _response(
                    "ACK_TO_APPLIED_STATE",
                    RESPONSE_NOT_APPLICABLE_ACK_NOT_ACCEPTED,
                    command_id,
                    ack.event_id,
                    None,
                    None,
                    _evidence_class(ack, applied or ack),
                    1 if applied else 0,
                    None,
                    DEFAULT_ELECTRICAL_POLICY,
                    [f"ACK_STATUS_{status}"],
                )
            )
            continue
        if applied is None:
            results.append(
                _response(
                    "ACK_TO_APPLIED_STATE",
                    RESPONSE_NOT_OBSERVED,
                    command_id,
                    ack.event_id,
                    None,
                    None,
                    _evidence_class(ack, ack),
                    0,
                    None,
                    DEFAULT_ELECTRICAL_POLICY,
                    ["NO_APPLIED_STATE_EVIDENCE_AFTER_ACCEPTED_ACK"],
                )
            )
            continue
        start, start_reason = _event_time(ack)
        end, end_reason = _event_time(applied)
        if start is None or end is None:
            results.append(
                _response(
                    "ACK_TO_APPLIED_STATE",
                    RESPONSE_NOT_ESTIMABLE_CLOCK,
                    command_id,
                    ack.event_id,
                    None,
                    None,
                    _evidence_class(ack, applied),
                    2,
                    None,
                    DEFAULT_ELECTRICAL_POLICY,
                    [start_reason or end_reason or REASON_MISSING_TIMESTAMP],
                )
            )
            continue
        if ack.clock_domain != applied.clock_domain or not _same_stream(ack, applied):
            results.append(
                _response(
                    "ACK_TO_APPLIED_STATE",
                    RESPONSE_NOT_ESTIMABLE_CLOCK,
                    command_id,
                    ack.event_id,
                    None,
                    None,
                    _evidence_class(ack, applied),
                    2,
                    None,
                    DEFAULT_ELECTRICAL_POLICY,
                    ["MIXED_CLOCK_DOMAIN_OR_STREAM"],
                )
            )
            continue
        latency = round(end - start, 6)
        evidence = _evidence_class(ack, applied)
        state = (
            RESPONSE_OBSERVED_DIAGNOSTIC_ONLY
            if evidence == "SYNTHETIC_UNIT_TEST"
            else RESPONSE_VERIFIED_MEASURED_RESPONSE
        )
        if latency < 0:
            state = RESPONSE_CONTRADICTORY_EVIDENCE
        results.append(
            replace(
                _response(
                    "ACK_TO_APPLIED_STATE",
                    state,
                    command_id,
                    ack.event_id,
                    latency if state in (
                        RESPONSE_OBSERVED_DIAGNOSTIC_ONLY,
                        RESPONSE_VERIFIED_MEASURED_RESPONSE,
                    ) else None,
                    _response_uncertainty(ack, applied, DEFAULT_ELECTRICAL_POLICY),
                    evidence,
                    2,
                    None,
                    DEFAULT_ELECTRICAL_POLICY,
                    [] if latency >= 0 else ["NEGATIVE_ACK_TO_APPLIED_INTERVAL"],
                ),
                independent_application=True,
            )
        )
    return tuple(results)


def _first_by_time(events: Sequence[TimelineEvent]) -> TimelineEvent | None:
    if not events:
        return None
    return sorted(
        events,
        key=lambda event: (
            _event_time(event)[0]
            if _event_time(event)[0] is not None
            else float("inf"),
            event.event_id,
        ),
    )[0]


# ---------------------------------------------------------------------------
# deterministic serialization helpers
# ---------------------------------------------------------------------------


def event_counts(
    events: Sequence[TimelineEvent],
    responses: Sequence[ResponseResult],
    dedup: DedupResult,
    ordering: Sequence[OrderedTimeline],
    audit: TimingAudit,
) -> dict[str, int]:
    canonical = dedup.canonical_events
    by_type = {
        event_type: sum(1 for event in canonical if event.event_type == event_type)
        for event_type in EVENT_TYPES
    }
    unalignable = sum(
        len(ordered.events)
        for ordered in ordering
        if ordered.status
        in (
            ORDER_NOT_ALIGNABLE,
            ORDER_MIXED_CLOCK,
            ORDER_MIXED_BOOT,
            ORDER_MIXED_DEVICE,
            ORDER_MISSING_TIMESTAMP,
            ORDER_AMBIGUOUS,
        )
    )
    return {
        "telemetry_events": by_type[EVENT_TELEMETRY_SAMPLE],
        "door_transitions": by_type[EVENT_DOOR_TRANSITION],
        "command_events": by_type[EVENT_COMMAND_CREATED_OR_PUBLISHED],
        "ack_events": by_type[EVENT_DEVICE_ACK],
        "applied_state_observations": by_type[EVENT_APPLIED_STATE],
        "electrical_response_events": by_type[EVENT_ELECTRICAL_RESPONSE],
        "thermal_response_events": by_type[EVENT_THERMAL_RESPONSE],
        "electrical_responses": sum(
            1
            for result in responses
            if result.relationship in (
                "APPLIED_TO_ELECTRICAL",
                "COMMAND_TO_ELECTRICAL",
            )
            and result.latency_s is not None
        ),
        "thermal_responses": sum(
            1
            for result in responses
            if result.relationship in (
                "APPLIED_TO_THERMAL",
                "COMMAND_TO_THERMAL",
            )
            and result.latency_s is not None
        ),
        "electrical_verified_responses": sum(
            1
            for result in responses
            if result.relationship in (
                "APPLIED_TO_ELECTRICAL",
                "COMMAND_TO_ELECTRICAL",
            )
            and result.state == RESPONSE_VERIFIED_MEASURED_RESPONSE
        ),
        "thermal_verified_responses": sum(
            1
            for result in responses
            if result.relationship in (
                "APPLIED_TO_THERMAL",
                "COMMAND_TO_THERMAL",
            )
            and result.state == RESPONSE_VERIFIED_MEASURED_RESPONSE
        ),
        "duplicate_deliveries": dedup.duplicate_deliveries,
        "contradictory_identities": dedup.contradictory_identity_count,
        "contradictory_events": len(dedup.contradictory_events),
        "missing_identity_events": len(dedup.missing_identity_events),
        "unalignable_events": unalignable,
        "unalignable_domain_reasons": len(audit.reason_codes),
        "real_measured_response_delays": sum(
            1
            for result in responses
            if result.state == RESPONSE_VERIFIED_MEASURED_RESPONSE
            and result.latency_s is not None
        ),
        "synthetic_example_delays": sum(
            1
            for result in responses
            if result.evidence_class == "SYNTHETIC_UNIT_TEST"
            and result.latency_s is not None
        ),
        "not_estimable_responses": sum(
            1 for result in responses if result.state.startswith("NOT_ESTIMABLE")
        ),
        "censored_responses": sum(
            1 for result in responses if result.state == RESPONSE_CENSORED
        ),
        "contradictory_responses": sum(
            1
            for result in responses
            if result.state == RESPONSE_CONTRADICTORY_EVIDENCE
        ),
    }


def response_summary_csv(responses: Sequence[ResponseResult]) -> str:
    buffer = io.StringIO()
    columns = (
        "source_path",
        "relationship",
        "state",
        "command_id",
        "anchor_event_id",
        "latency_s",
        "uncertainty_s",
        "evidence_class",
        "independent_application",
        "sample_count",
        "baseline_median",
        "policy_name",
        "reason_codes",
    )
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for result in sorted(
        responses,
        key=lambda item: (
            item.relationship,
            item.command_id or "",
            item.anchor_event_id or "",
            item.state,
        ),
    ):
        payload = result.to_dict()
        payload["reason_codes"] = "|".join(result.reason_codes)
        writer.writerow({key: payload.get(key) for key in columns})
    return buffer.getvalue()


def event_timeline_csv(events: Sequence[TimelineEvent]) -> str:
    buffer = io.StringIO()
    columns = (
        "event_id",
        "event_type",
        "provenance",
        "source_path",
        "source_sha256",
        "source_namespace",
        "source_record_index",
        "device_id",
        "boot_id",
        "run_id",
        "identity_status",
        "command_id",
        "ack_seq",
        "seq",
        "device_uptime_ms",
        "event_time_utc",
        "backend_received_at",
        "persisted_at",
        "clock_domain",
        "clock_sync",
        "measurement_quality",
        "uncertainty_s",
        "eligibility",
        "delivery_count",
        "reason_codes",
        "field_origin",
    )
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for event in sorted(
        events,
        key=lambda item: (
            item.source_path,
            str(item.device_id),
            str(item.boot_id),
            item.clock_domain,
            item.device_uptime_ms if item.device_uptime_ms is not None else -1,
            item.event_time_utc or "",
            item.seq if item.seq is not None else -1,
            item.event_type,
            item.event_id,
        ),
    ):
        payload = event.to_dict()
        payload["reason_codes"] = "|".join(event.reason_codes)
        writer.writerow({key: payload.get(key) for key in columns})
    return buffer.getvalue()


def source_contract_ledger() -> tuple[dict[str, str], ...]:
    """Source field -> namespace -> time domain -> identity -> quality -> use."""
    return (
        {
            "source_field": "A W09 seq/boot_id/device_id",
            "namespace": "w09-run-export/v2",
            "time_domain": "boot-scoped identity; no absolute time",
            "identity": "device_id may be NOT_CARRIED; boot_id+seq is the session identity",
            "quality": "sequence_quality",
            "authority": "A export; W04 intake preserves unresolved values",
            "w06_use": "telemetry event identity and duplicate key",
        },
        {
            "source_field": "A W09 device_ms",
            "namespace": "w09-run-export/v2",
            "time_domain": "DEVICE_BOOT_UPTIME",
            "identity": "boot_id",
            "quality": "sequence/provenance quality",
            "authority": "A export",
            "w06_use": "within-boot ordering and elapsed intervals only",
        },
        {
            "source_field": "A W09 host_capture_time_utc",
            "namespace": "w09-run-export/v2",
            "time_domain": "HOST_CAPTURE_UTC",
            "identity": "row/session",
            "quality": "NOT_AVAILABLE in the committed capture",
            "authority": "A export",
            "w06_use": "never promoted to device event UTC",
        },
        {
            "source_field": "A W09 door_open/door_polarity",
            "namespace": "w09-run-export/v2",
            "time_domain": "DEVICE_BOOT_UPTIME",
            "identity": "boot_id+seq",
            "quality": "door_quality",
            "authority": "A export",
            "w06_use": "named OPEN/CLOSED transitions only; UNKNOWN is not a transition",
        },
        {
            "source_field": "A W09 pwm_applied_permille/state",
            "namespace": "w09-run-export/v2",
            "time_domain": "DEVICE_BOOT_UPTIME",
            "identity": "boot_id+seq",
            "quality": "overall_quality",
            "authority": "A export",
            "w06_use": "device-reported applied-state observation; not command proof",
        },
        {
            "source_field": "A W09 voltage/current/power/energy",
            "namespace": "w09-run-export/v2",
            "time_domain": "DEVICE_BOOT_UPTIME",
            "identity": "boot_id+seq",
            "quality": "electrical_quality",
            "authority": "A export",
            "w06_use": "electrical response candidate; UNKNOWN quality never certifies",
        },
        {
            "source_field": "A W09 t1/t2/t3/t4",
            "namespace": "w09-run-export/v2",
            "time_domain": "DEVICE_BOOT_UPTIME",
            "identity": "boot_id+seq",
            "quality": "per-probe status and sensor roles",
            "authority": "A export plus frozen ROM role map",
            "w06_use": "chamber-air mean from role-qualified slots only; T2 hot side excluded",
        },
        {
            "source_field": "A W06 #CG CMDACK command envelope",
            "namespace": "coldguard.command-ack-serial/v1 (schema=1)",
            "time_domain": "DEVICE_BOOT_UPTIME; no UTC epoch",
            "identity": "command_id + device_id + boot_id + ack_seq",
            "quality": "protocol evidence; not measurement quality",
            "authority": "A host-generated fixture; synthetic until a real transport exists",
            "w06_use": "ACK event and duplicate-canonical semantics; never applied proof",
        },
        {
            "source_field": "A W06 #CG TELEM schema=3",
            "namespace": "coldguard.telem-serial/v3",
            "time_domain": "DEVICE_BOOT_UPTIME; DEVICE_HAS_NO_WALL_CLOCK",
            "identity": "boot_id+seq",
            "quality": "per-field status tokens",
            "authority": "A firmware serial namespace, not C MQTT JSON",
            "w06_use": "not parsed by W06; the C JSON parser is never substituted",
        },
        {
            "source_field": "C telemetry JSON captured_at/uptime_ms/seq",
            "namespace": "coldguard.telemetry/v1 (schema_version=1)",
            "time_domain": "DEVICE_EVENT_UTC for captured_at; boot-scoped uptime_ms",
            "identity": "device_id+boot_id+seq",
            "quality": "quality sections",
            "authority": "C wire contract; current fixture is synthetic/unverified",
            "w06_use": "telemetry event time and identity; no command/ACK linkage",
        },
        {
            "source_field": "C telemetry_raw backend_received_at/created_at",
            "namespace": "backend storage (C W02)",
            "time_domain": "BACKEND_RECEIVE_UTC / BACKEND_PERSISTED_UTC",
            "identity": "raw delivery row",
            "quality": "ingest_status",
            "authority": "C backend",
            "w06_use": "receive/persisted provenance only; never source acquisition time",
        },
        {
            "source_field": "A W10 door-events timing_uncertainty",
            "namespace": "A W10 s2-horizon evidence",
            "time_domain": "DEVICE_BOOT_UPTIME",
            "identity": "boot_id+seq",
            "quality": "door mapping not attested",
            "authority": "A W10 evidence; reference only for W06 uncertainty",
            "w06_use": "documented 1 s edge uncertainty; no door-open claim",
        },
    )


def _event_index(event: TimelineEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "provenance": event.provenance,
        "source_path": event.source_path,
        "source_sha256": event.source_sha256,
        "source_namespace": event.source_namespace,
        "device_id": event.device_id,
        "boot_id": event.boot_id,
        "run_id": event.run_id,
        "identity_status": event.identity_status,
        "command_id": event.command_id,
        "ack_seq": event.ack_seq,
        "seq": event.seq,
        "clock_domain": event.clock_domain,
        "clock_sync": event.clock_sync,
        "measurement_quality": event.measurement_quality,
        "uncertainty_s": event.uncertainty_s,
        "eligibility": event.eligibility,
        "delivery_count": event.delivery_count,
        "reason_codes": list(event.reason_codes),
    }


def _compact_dedup(dedup: DedupResult) -> dict[str, Any]:
    return {
        "canonical_event_ids": [
            event.event_id for event in dedup.canonical_events
        ],
        "canonical_delivery_counts": {
            event.event_id: event.delivery_count
            for event in dedup.canonical_events
            if event.delivery_count > 1
        },
        "contradictory_events": [
            event.to_dict() for event in dedup.contradictory_events
        ],
        "missing_identity_events": [
            event.to_dict() for event in dedup.missing_identity_events
        ],
        "duplicate_deliveries": dedup.duplicate_deliveries,
        "contradictory_identity_count": dedup.contradictory_identity_count,
        "duplicate_canonical_acks": dedup.duplicate_canonical_acks,
        "multiple_ack_without_canonical": dedup.multiple_ack_without_canonical,
        "reboot_identity_resets": dedup.reboot_identity_resets,
        "new_commands_same_action": dedup.new_commands_same_action,
        "reason_codes": list(dedup.reason_codes),
    }


def event_manifest(
    events: Sequence[TimelineEvent],
    responses: Sequence[ResponseResult],
    dedup: DedupResult,
    ordering: Sequence[OrderedTimeline],
    audit: TimingAudit,
    *,
    command: str,
    repository_revision: str,
    analysis_code_sha256: str,
    sources: Sequence[dict[str, Any]],
    configs: Sequence[ResponsePolicy],
    statuses: dict[str, str],
    run_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "w06_layer_version": W06_LAYER_VERSION,
        "manifest_schema": "coldguard-w06-timing-manifest-v1",
        "analysis_code_sha256": analysis_code_sha256,
        "repository_revision": repository_revision,
        "generation_command": command,
        "run_index": run_index,
        "source_contract_ledger": list(source_contract_ledger()),
        "sources": list(sources),
        "ordering": [result.to_dict() for result in ordering],
        "audit": audit.to_dict(),
        "dedup": _compact_dedup(dedup),
        "responses": [result.to_dict() for result in responses],
        "counts": event_counts(events, responses, dedup, ordering, audit),
        "policies": [policy.to_dict() for policy in configs],
        "timeline_events": [_event_index(event) for event in events],
        "separation": dict(statuses),
    }
