"""W05 diagnostic QA over the W04 normalized capture (B-W05-01/02/03/04).

This layer deliberately does not re-parse A/C wire formats and does not
compute a second admission verdict. It consumes :class:`~coldguard_ml.intake.Capture`
and :class:`~coldguard_ml.intake.AdmissionResult` and reports:

* sampling intervals, jitter, gaps and provisional completeness;
* per-channel missingness, quality, impossible values, flatline/stale
  candidates, duplicate identity and discontinuities;
* deterministic SVG panels for physical state.

The W04 admission verdict is reported unchanged. A QA finding never rewrites
A's validity ledger, and an A INVALID verdict never deletes readable
observations from the diagnostic view.
"""

from __future__ import annotations

import csv
import io
import math
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any, Iterable, Sequence
from xml.sax.saxutils import escape

from .intake import (
    AdmissionResult,
    AdmissionStage,
    Capture,
    NormalizedRow,
    SOURCE_FORMAT_A_W09_EXPORT,
    SOURCE_FORMAT_C_TELEMETRY_V1,
    TIME_BOOT_SCOPED_UPTIME,
    TIME_EVENT_UTC,
    count_independent_runs,
    evaluate_admission,
    summarize_readiness,
)

QA_LAYER_VERSION = "coldguard-w05-qa-v1"

QA_EXECUTION_COMPLETED = "COMPLETED"
QA_EXECUTION_FAILED = "FAILED"
SOURCE_STRUCTURE_VALID = "VALID"
SOURCE_STRUCTURE_INVALID = "INVALID"
CHANNEL_QUALITY_QUALIFIED = "QUALIFIED"
CHANNEL_QUALITY_ATTENTION = "ATTENTION_REQUIRED"
CHANNEL_QUALITY_NOT_ESTIMABLE = "NOT_ESTIMABLE"

TIME_BASE_TRUSTED_UPTIME = "TRUSTED_BOOT_SCOPED_UPTIME"
TIME_BASE_TRUSTED_EVENT_UTC = "TRUSTED_EVENT_UTC"
TIME_BASE_EVENT_UTC_UNVERIFIED_SYNC = "EVENT_UTC_UNVERIFIED_SYNC"
TIME_BASE_UNTRUSTED = "TIME_BASE_UNTRUSTED"

COMPLETENESS_PROVISIONAL = "PROVISIONAL_DIAGNOSTIC"
COMPLETENESS_NOT_ESTIMABLE = "NOT_ESTIMABLE"

LONG_GAP_POLICY = (
    "DIAGNOSTIC_ONLY_CONFIGURABLE_THRESHOLD_NOT_A_FEATURE_ELIGIBILITY_LIMIT"
)
STALE_POLICY = "DIAGNOSTIC_ASSUMPTION_SOURCE_AGE_NOT_CANONICALLY_THRESHOLDED"
CAMPAIGN_COMPLETENESS = "NOT_ESTIMABLE_ACQUISITION_BOUNDARIES_UNVERIFIED"

PERCENTILE_LINEAR = "linear"
PERCENTILE_NEAREST_RANK = "nearest_rank"
PERCENTILE_METHODS = (PERCENTILE_LINEAR, PERCENTILE_NEAREST_RANK)

# Canonical instrument limits. Temperature/RH come from Doc 01 §§6.1, 7.1,
# 17.2; the PZEM values follow the commissioned 50 A profile in Doc 01
# §§9.3, 17.3-17.5. Pressure is a BME280 datasheet operating range.
DS18B20_MIN_C = -55.0
DS18B20_MAX_C = 125.0
BME280_MIN_C = -40.0
BME280_MAX_C = 85.0
RH_MIN_PCT = 0.0
RH_MAX_PCT = 100.0
PRESSURE_MIN_HPA = 300.0
PRESSURE_MAX_HPA = 1100.0
PZEM_VOLTAGE_MIN_V = 0.0
PZEM_VOLTAGE_MAX_V = 300.0
PZEM_CURRENT_MIN_A = 0.0
PZEM_CURRENT_MAX_A = 50.0
PZEM_POWER_MIN_W = 0.0
PZEM_POWER_MAX_W = 15000.0
DUTY_MIN_PERMILLE = 0
DUTY_MAX_PERMILLE = 1000

# Numerical resolutions used as flatline tolerances. DS18B20 is 12-bit
# (0.0625 °C); BME280 temperature 0.01 °C, humidity 0.01 %RH, pressure
# 0.01 hPa. PZEM power 0.1 W; voltage/current 0.01.
DS18B20_RESOLUTION_C = 0.0625
BME280_RESOLUTION_C = 0.01
RH_RESOLUTION_PCT = 0.01
PRESSURE_RESOLUTION_HPA = 0.01
PZEM_VOLTAGE_RESOLUTION_V = 0.01
PZEM_CURRENT_RESOLUTION_A = 0.01
PZEM_POWER_RESOLUTION_W = 0.1


@dataclass(frozen=True)
class QAConfig:
    """Diagnostic thresholds; none of these is a feature-eligibility rule."""

    long_gap_ms: int = 5000
    flatline_min_observations: int = 10
    flatline_min_span_s: float = 0.0
    flatline_temperature_tolerance_c: float = DS18B20_RESOLUTION_C
    stale_age_ms: int = 5000
    nominal_cadence_ms: float | None = None
    percentile_method: str = PERCENTILE_LINEAR

    def validate(self) -> None:
        if self.long_gap_ms <= 0:
            raise ValueError("long_gap_ms must be positive")
        if self.flatline_min_observations < 2:
            raise ValueError("flatline_min_observations must be at least 2")
        if self.flatline_min_span_s < 0:
            raise ValueError("flatline_min_span_s must be non-negative")
        if self.flatline_temperature_tolerance_c < 0:
            raise ValueError("flatline_temperature_tolerance_c must be non-negative")
        if self.stale_age_ms <= 0:
            raise ValueError("stale_age_ms must be positive")
        if self.nominal_cadence_ms is not None and self.nominal_cadence_ms <= 0:
            raise ValueError("nominal_cadence_ms must be positive when supplied")
        if self.percentile_method not in PERCENTILE_METHODS:
            raise ValueError(
                f"percentile_method must be one of {PERCENTILE_METHODS}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "long_gap_ms": self.long_gap_ms,
            "long_gap_policy": LONG_GAP_POLICY,
            "flatline_min_observations": self.flatline_min_observations,
            "flatline_min_span_s": self.flatline_min_span_s,
            "flatline_temperature_tolerance_c": self.flatline_temperature_tolerance_c,
            "stale_age_ms": self.stale_age_ms,
            "stale_policy": STALE_POLICY,
            "nominal_cadence_ms": self.nominal_cadence_ms,
            "percentile_method": self.percentile_method,
            "percentile_definition": (
                "linear interpolation between closest ranks"
                if self.percentile_method == PERCENTILE_LINEAR
                else "nearest rank ceiling"
            ),
            "flatline_span_policy": (
                "BREAK_ON_MISSING_VALUE_SOURCE_QUALITY_INVALID_OR_LONG_GAP"
            ),
            "flatline_scope": (
                "DS18B20_AND_BME280_MEASUREMENT_CHANNELS_ONLY; "
                "STATE_AND_COUNTER_CHANNELS_EXCLUDED"
            ),
            "stale_scope": "DS18B20_SOURCE_PROVIDED_AGE_MS_ONLY",
            "campaign_completeness": CAMPAIGN_COMPLETENESS,
        }


DEFAULT_QA_CONFIG = QAConfig()


@dataclass(frozen=True)
class IntervalStatistics:
    time_base_status: str
    time_base_detail: str
    interval_count: int
    positive_interval_count: int
    zero_interval_count: int
    negative_interval_count: int
    median_dt_s: float | None
    p95_dt_s: float | None
    min_positive_dt_s: float | None
    max_positive_dt_s: float | None
    nominal_dt_s: float | None
    nominal_source: str
    nominal_confidence: str
    jitter_median_abs_s: float | None
    jitter_p95_abs_s: float | None
    jitter_min_s: float | None
    jitter_max_s: float | None
    long_gap_count: int
    long_gap_total_s: float | None
    seq_missing_estimate: int | None
    seq_semantics: str
    time_missing_estimate: int | None
    observation_window_s: float | None
    expected_samples_provisional: int | None
    captured_frame_completeness: float | None
    completeness_status: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_base_status": self.time_base_status,
            "time_base_detail": self.time_base_detail,
            "interval_count": self.interval_count,
            "positive_interval_count": self.positive_interval_count,
            "zero_interval_count": self.zero_interval_count,
            "negative_interval_count": self.negative_interval_count,
            "median_dt_s": self.median_dt_s,
            "p95_dt_s": self.p95_dt_s,
            "min_positive_dt_s": self.min_positive_dt_s,
            "max_positive_dt_s": self.max_positive_dt_s,
            "nominal_dt_s": self.nominal_dt_s,
            "nominal_source": self.nominal_source,
            "nominal_confidence": self.nominal_confidence,
            "jitter_median_abs_s": self.jitter_median_abs_s,
            "jitter_p95_abs_s": self.jitter_p95_abs_s,
            "jitter_min_s": self.jitter_min_s,
            "jitter_max_s": self.jitter_max_s,
            "long_gap_count": self.long_gap_count,
            "long_gap_total_s": self.long_gap_total_s,
            "seq_missing_estimate": self.seq_missing_estimate,
            "seq_semantics": self.seq_semantics,
            "time_missing_estimate": self.time_missing_estimate,
            "observation_window_s": self.observation_window_s,
            "expected_samples_provisional": self.expected_samples_provisional,
            "captured_frame_completeness": self.captured_frame_completeness,
            "completeness_status": self.completeness_status,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class RunSegment:
    run_id: str | None
    row_count: int
    start_s: float | None
    end_s: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "row_count": self.row_count,
            "start_s": self.start_s,
            "end_s": self.end_s,
        }


@dataclass(frozen=True)
class ChamberAirSpread:
    slots: tuple[str, ...]
    n: int
    min_c: float
    median_c: float
    p95_c: float
    max_c: float
    max_time_s: float | None
    max_values: tuple[tuple[str, float], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slots": list(self.slots),
            "n": self.n,
            "min_c": self.min_c,
            "median_c": self.median_c,
            "p95_c": self.p95_c,
            "max_c": self.max_c,
            "max_time_s": self.max_time_s,
            "max_values": dict(self.max_values),
        }


@dataclass(frozen=True)
class SessionSamplingSummary:
    session_id: str
    device_id: str | None
    boot_id: str
    row_count: int
    unique_identity_count: int
    duplicate_identity_count: int
    scientific_usable_rows: int
    scientific_sample_coverage: float
    scientific_coverage_note: str
    campaign_completeness: str
    interval_stats: IntervalStatistics
    first_time_s: float | None
    last_time_s: float | None
    run_segments: tuple[RunSegment, ...] = ()
    chamber_air_spread: ChamberAirSpread | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "session_id": self.session_id,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "row_count": self.row_count,
            "unique_identity_count": self.unique_identity_count,
            "duplicate_identity_count": self.duplicate_identity_count,
            "scientific_usable_rows": self.scientific_usable_rows,
            "scientific_sample_coverage": self.scientific_sample_coverage,
            "scientific_coverage_note": self.scientific_coverage_note,
            "campaign_completeness": self.campaign_completeness,
            "first_time_s": self.first_time_s,
            "last_time_s": self.last_time_s,
            "run_segments": [segment.to_dict() for segment in self.run_segments],
            "chamber_air_spread": (
                None
                if self.chamber_air_spread is None
                else self.chamber_air_spread.to_dict()
            ),
        }
        payload.update(self.interval_stats.to_dict())
        return payload


@dataclass(frozen=True)
class ChannelSpec:
    channel: str
    family: str
    physical_role: str
    unit: str | None
    domain: str
    kind: str
    minimum: float | None = None
    maximum: float | None = None
    flatline_applicable: bool = False
    flatline_tolerance: float | None = None
    stale_applicable: bool = False
    counter: bool = False
    state_values: tuple[str, ...] = ()
    source_age_field: str | None = None


@dataclass(frozen=True)
class ChannelSummary:
    source_id: str
    source_sha256: str
    session_id: str
    device_id: str | None
    boot_id: str
    run_id: str | None
    run_id_status: str
    run_segment_count: int
    channel: str
    family: str
    physical_role: str
    unit: str | None
    row_count: int
    present_count: int
    missing_count: int
    missing_fraction: float | None
    quality_valid: int
    quality_degraded: int
    quality_invalid: int
    quality_unknown: int
    impossible_count: int
    flatline_candidate_count: int | None
    stale_candidate_count: int | None
    duplicate_identity_count: int
    repeated_equal_consecutive_count: int | None
    discontinuity_count: int
    unknown_state_count: int
    quality_domain: str | None
    diagnostic_status: str
    reason_codes: tuple[str, ...]
    physical_admission_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "session_id": self.session_id,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "run_id": self.run_id,
            "run_id_status": self.run_id_status,
            "run_segment_count": self.run_segment_count,
            "channel": self.channel,
            "family": self.family,
            "physical_role": self.physical_role,
            "unit": self.unit,
            "row_count": self.row_count,
            "present_count": self.present_count,
            "missing_count": self.missing_count,
            "missing_fraction": self.missing_fraction,
            "quality_VALID": self.quality_valid,
            "quality_DEGRADED": self.quality_degraded,
            "quality_INVALID": self.quality_invalid,
            "quality_UNKNOWN": self.quality_unknown,
            "impossible_count": self.impossible_count,
            "flatline_candidate_count": self.flatline_candidate_count,
            "stale_candidate_count": self.stale_candidate_count,
            "duplicate_identity_count": self.duplicate_identity_count,
            "repeated_equal_consecutive_count": (
                self.repeated_equal_consecutive_count
            ),
            "discontinuity_count": self.discontinuity_count,
            "unknown_state_count": self.unknown_state_count,
            "quality_domain": self.quality_domain,
            "diagnostic_status": self.diagnostic_status,
            "reason_codes": list(self.reason_codes),
            "physical_admission_status": self.physical_admission_status,
        }


@dataclass(frozen=True)
class Anomaly:
    code: str
    severity: str
    scope: str
    channel: str | None
    count: int | None
    detail: str
    start_s: float | None = None
    end_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "scope": self.scope,
            "channel": self.channel,
            "count": self.count,
            "detail": self.detail,
            "start_s": self.start_s,
            "end_s": self.end_s,
        }


@dataclass(frozen=True)
class QAStatuses:
    qa_execution_status: str
    source_structure_status: str
    channel_quality_status: str
    physical_admission_status: str
    physical_highest_stage: str
    predictive_dataset_readiness: str

    def to_dict(self) -> dict[str, str]:
        return {
            "QA_EXECUTION_STATUS": self.qa_execution_status,
            "SOURCE_STRUCTURE_STATUS": self.source_structure_status,
            "CHANNEL_QUALITY_STATUS": self.channel_quality_status,
            "PHYSICAL_ADMISSION_STATUS": self.physical_admission_status,
            "PHYSICAL_HIGHEST_STAGE": self.physical_highest_stage,
            "PREDICTIVE_DATASET_READINESS": self.predictive_dataset_readiness,
        }


@dataclass(frozen=True)
class QAAnalysis:
    capture: Capture
    admission: AdmissionResult
    sessions: tuple[SessionSamplingSummary, ...]
    channels: tuple[ChannelSummary, ...]
    anomalies: tuple[Anomaly, ...]
    statuses: QAStatuses
    config: QAConfig

    def to_dict(self) -> dict[str, Any]:
        return {
            "qa_layer_version": QA_LAYER_VERSION,
            "statuses": self.statuses.to_dict(),
            "source": self.capture.source.to_dict(),
            "run": self.capture.run.to_dict(),
            "time": self.capture.time.to_dict(),
            "admission": self.admission.to_dict(),
            "sessions": [session.to_dict() for session in self.sessions],
            "channels": [channel.to_dict() for channel in self.channels],
            "anomalies": [anomaly.to_dict() for anomaly in self.anomalies],
            "config": self.config.to_dict(),
        }


@dataclass(frozen=True)
class QASuiteSummary:
    analyzed_sources: int
    unique_physical_sources: int
    duplicate_views: int
    eligible_s1_runs: int
    eligible_s2_runs: int
    predictive_dataset_readiness: str
    conflicts: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "analyzed_sources": self.analyzed_sources,
            "unique_physical_sources": self.unique_physical_sources,
            "duplicate_views": self.duplicate_views,
            "eligible_s1_runs": self.eligible_s1_runs,
            "eligible_s2_runs": self.eligible_s2_runs,
            "predictive_dataset_readiness": self.predictive_dataset_readiness,
            "conflicts": [dict(item) for item in self.conflicts],
        }


def percentile(values: Sequence[float], fraction: float, method: str) -> float | None:
    """Deterministic percentile with an explicitly documented method."""
    if not values:
        return None
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("percentile fraction must lie in [0, 1]")
    if method not in PERCENTILE_METHODS:
        raise ValueError(f"unsupported percentile method {method!r}")
    ordered = sorted(values)
    if method == PERCENTILE_NEAREST_RANK:
        index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
        return ordered[index]
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _mode_interval(
    positive: Sequence[float],
) -> tuple[float | None, str, str]:
    if not positive:
        return None, "NO_POSITIVE_INTERVAL", "NOT_ESTIMABLE"
    rounded = [round(value, 9) for value in positive]
    counts = Counter(rounded)
    highest = max(counts.values())
    modal = min(value for value, count in counts.items() if count == highest)
    share = highest / len(positive)
    if share >= 0.9:
        confidence = "HIGH"
    elif share >= 0.6:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
    return modal, "INFERRED_MODAL_OBSERVED_INTERVAL", confidence


def compute_interval_statistics(
    times_s: Sequence[float],
    seqs: Sequence[int],
    *,
    config: QAConfig = DEFAULT_QA_CONFIG,
) -> IntervalStatistics:
    """Compute session-local interval statistics from ordered event times.

    ``times_s`` are already reduced to one trusted domain for one boot. The
    caller never passes cross-boot uptime values. Non-positive intervals are
    counted and excluded from the distribution rather than silently dropped.
    """
    config.validate()
    if len(times_s) != len(seqs):
        raise ValueError("times_s and seqs must have the same length")
    if not times_s:
        return IntervalStatistics(
            time_base_status=TIME_BASE_UNTRUSTED,
            time_base_detail="no rows in session",
            interval_count=0,
            positive_interval_count=0,
            zero_interval_count=0,
            negative_interval_count=0,
            median_dt_s=None,
            p95_dt_s=None,
            min_positive_dt_s=None,
            max_positive_dt_s=None,
            nominal_dt_s=None,
            nominal_source="NOT_ESTIMABLE",
            nominal_confidence="NOT_ESTIMABLE",
            jitter_median_abs_s=None,
            jitter_p95_abs_s=None,
            jitter_min_s=None,
            jitter_max_s=None,
            long_gap_count=0,
            long_gap_total_s=None,
            seq_missing_estimate=None,
            seq_semantics="NOT_ESTIMABLE",
            time_missing_estimate=None,
            observation_window_s=None,
            expected_samples_provisional=None,
            captured_frame_completeness=None,
            completeness_status=COMPLETENESS_NOT_ESTIMABLE,
            reasons=("TIME_BASE_UNTRUSTED",),
        )
    raw_intervals = [
        round(times_s[index + 1] - times_s[index], 9)
        for index in range(len(times_s) - 1)
    ]
    positive = [value for value in raw_intervals if value > 0]
    zero_count = sum(1 for value in raw_intervals if value == 0)
    negative_count = sum(1 for value in raw_intervals if value < 0)
    reasons: list[str] = []

    seq_deltas = [seqs[index + 1] - seqs[index] for index in range(len(seqs) - 1)]
    if seq_deltas and all(delta > 0 for delta in seq_deltas):
        seq_missing: int | None = sum(max(0, delta - 1) for delta in seq_deltas)
        seq_semantics = (
            "ALL_DELTAS_ONE"
            if all(delta == 1 for delta in seq_deltas)
            else "NONUNIT_DELTAS_PRESENT"
        )
    else:
        seq_missing = None
        seq_semantics = "NON_MONOTONIC_OR_NOT_ESTIMABLE"
        reasons.append("SEQ_SEMANTICS_UNTRUSTED")

    if negative_count:
        reasons.append("NEGATIVE_INTERVAL_PRESENT")
        return IntervalStatistics(
            time_base_status=TIME_BASE_UNTRUSTED,
            time_base_detail=(
                "non-increasing event times within one boot; no sampling "
                "distribution is computed"
            ),
            interval_count=len(raw_intervals),
            positive_interval_count=len(positive),
            zero_interval_count=zero_count,
            negative_interval_count=negative_count,
            median_dt_s=None,
            p95_dt_s=None,
            min_positive_dt_s=min(positive) if positive else None,
            max_positive_dt_s=max(positive) if positive else None,
            nominal_dt_s=None,
            nominal_source="NOT_ESTIMABLE",
            nominal_confidence="NOT_ESTIMABLE",
            jitter_median_abs_s=None,
            jitter_p95_abs_s=None,
            jitter_min_s=None,
            jitter_max_s=None,
            long_gap_count=0,
            long_gap_total_s=None,
            seq_missing_estimate=seq_missing,
            seq_semantics=seq_semantics,
            time_missing_estimate=None,
            observation_window_s=None,
            expected_samples_provisional=None,
            captured_frame_completeness=None,
            completeness_status=COMPLETENESS_NOT_ESTIMABLE,
            reasons=tuple(reasons),
        )

    if zero_count:
        reasons.append("ZERO_INTERVAL_PRESENT")

    if config.nominal_cadence_ms is not None:
        nominal = config.nominal_cadence_ms / 1000.0
        nominal_source = "CONFIGURED_DIAGNOSTIC_CADENCE"
        nominal_confidence = "ASSUMED_CONFIGURED"
    else:
        nominal, nominal_source, nominal_confidence = _mode_interval(positive)

    short_gap_count = 0
    if positive and nominal is not None:
        threshold_s = config.long_gap_ms / 1000.0
        for value in positive:
            if value > threshold_s:
                short_gap_count += 1
        long_gap_count = short_gap_count
        long_gap_total = sum(
            value for value in positive if value > threshold_s
        )
    else:
        long_gap_count = 0
        long_gap_total = None

    jitter_values = (
        [value - nominal for value in positive]
        if positive and nominal is not None
        else []
    )

    observation_window = (
        times_s[-1] - times_s[0] if len(times_s) > 1 else 0.0
    )
    expected_samples: int | None = None
    completeness: float | None = None
    completeness_status = COMPLETENESS_NOT_ESTIMABLE
    if nominal is not None and observation_window is not None:
        expected_samples = max(1, int(round(observation_window / nominal)) + 1)
        completeness = len(times_s) / expected_samples
        completeness_status = COMPLETENESS_PROVISIONAL

    time_missing: int | None = None
    if positive and nominal is not None:
        time_missing = 0
        for value in positive:
            if value > 1.5 * nominal:
                time_missing += max(0, int(round(value / nominal)) - 1)

    return IntervalStatistics(
        time_base_status=TIME_BASE_TRUSTED_UPTIME,
        time_base_detail=(
            "single boot session; deltas are computed only inside this boot"
        ),
        interval_count=len(raw_intervals),
        positive_interval_count=len(positive),
        zero_interval_count=zero_count,
        negative_interval_count=negative_count,
        median_dt_s=percentile(positive, 0.5, config.percentile_method),
        p95_dt_s=percentile(positive, 0.95, config.percentile_method),
        min_positive_dt_s=min(positive) if positive else None,
        max_positive_dt_s=max(positive) if positive else None,
        nominal_dt_s=nominal,
        nominal_source=nominal_source,
        nominal_confidence=nominal_confidence,
        jitter_median_abs_s=percentile(
            [abs(value) for value in jitter_values], 0.5, config.percentile_method
        ),
        jitter_p95_abs_s=percentile(
            [abs(value) for value in jitter_values], 0.95, config.percentile_method
        ),
        jitter_min_s=min(jitter_values) if jitter_values else None,
        jitter_max_s=max(jitter_values) if jitter_values else None,
        long_gap_count=long_gap_count,
        long_gap_total_s=long_gap_total,
        seq_missing_estimate=seq_missing,
        seq_semantics=seq_semantics,
        time_missing_estimate=time_missing,
        observation_window_s=observation_window,
        expected_samples_provisional=expected_samples,
        captured_frame_completeness=completeness,
        completeness_status=completeness_status,
        reasons=tuple(reasons),
    )


def _session_key(row: NormalizedRow) -> str:
    device = row.device_id or "NO_DEVICE_ID"
    return f"{device}::{row.boot_id}"


def _session_rows(capture: Capture) -> dict[str, list[NormalizedRow]]:
    sessions: dict[str, list[NormalizedRow]] = {}
    for row in capture.rows:
        sessions.setdefault(_session_key(row), []).append(row)
    return sessions


def _identity_keys(rows: Sequence[NormalizedRow]) -> list[tuple[str, ...]]:
    keys: list[tuple[str, ...]] = []
    for row in rows:
        key = row.dedup_key or (
            row.device_id or "NO_DEVICE_ID",
            row.boot_id,
            str(row.seq),
        )
        keys.append(tuple(str(part) for part in key))
    return keys


def _trusted_times(
    capture: Capture, rows: Sequence[NormalizedRow]
) -> tuple[list[float] | None, str, str]:
    if capture.time.domain == TIME_EVENT_UTC:
        times = [row.event_time_utc for row in rows]
        if any(value is None for value in times):
            return (
                None,
                TIME_BASE_UNTRUSTED,
                "event-time domain declared but at least one row has no event "
                "timestamp; no host capture time is substituted",
            )
        first = times[0]
        assert first is not None
        seconds = [
            round((value - first).total_seconds(), 6)
            for value in times
            if value is not None
        ]
        if any(
            seconds[index + 1] < seconds[index]
            for index in range(len(seconds) - 1)
        ):
            return (
                None,
                TIME_BASE_UNTRUSTED,
                "event timestamps are not non-decreasing inside the boot",
            )
        trusted = (
            capture.time.clock_sync == "EVIDENCED"
            or capture.time.absolute_latency_supported
        )
        status = (
            TIME_BASE_TRUSTED_EVENT_UTC
            if trusted
            else TIME_BASE_EVENT_UTC_UNVERIFIED_SYNC
        )
        return (
            seconds,
            status,
            f"event UTC inside one boot; clock_sync={capture.time.clock_sync}; "
            "absolute latency and cross-boot joins remain unsupported unless "
            "sync is evidenced",
        )
    if capture.time.domain == TIME_BOOT_SCOPED_UPTIME:
        values = [row.device_ms for row in rows]
        if any(value is None for value in values):
            return (
                None,
                TIME_BASE_UNTRUSTED,
                "boot-scoped uptime domain declared but at least one row has no "
                "device_ms; no host capture time is substituted",
            )
        first = values[0]
        assert first is not None
        seconds = [
            round((value - first) / 1000.0, 9)
            for value in values
            if value is not None
        ]
        return seconds, TIME_BASE_TRUSTED_UPTIME, "device_ms inside one boot"
    return (
        None,
        TIME_BASE_UNTRUSTED,
        f"time domain {capture.time.domain!r} is not an analyzable event domain",
    )


def _run_segments(
    rows: Sequence[NormalizedRow], times: Sequence[float] | None
) -> tuple[RunSegment, ...]:
    """Source run_id segments inside one boot; never independent sessions."""
    if not rows:
        return ()
    spans: list[tuple[str | None, int, int]] = []
    start = 0
    current = rows[0].run_id
    for index in range(1, len(rows)):
        if rows[index].run_id != current:
            spans.append((current, start, index - 1))
            current = rows[index].run_id
            start = index
    spans.append((current, start, len(rows) - 1))
    aligned = times is not None and len(times) == len(rows)
    return tuple(
        RunSegment(
            run_id=run_id,
            row_count=end - begin + 1,
            start_s=times[begin] if aligned and times is not None else None,
            end_s=times[end] if aligned and times is not None else None,
        )
        for run_id, begin, end in spans
    )


def _chamber_air_spread(
    capture: Capture,
    rows: Sequence[NormalizedRow],
    times: Sequence[float] | None,
    config: QAConfig,
) -> ChamberAirSpread | None:
    slots = capture.chamber_air_slots
    if len(slots) < 2:
        return None
    spreads: list[tuple[int, float, tuple[tuple[str, float], ...]]] = []
    for index, row in enumerate(rows):
        quality = dict(row.quality).get("thermal")
        if quality == "INVALID":
            continue
        values: list[tuple[str, float]] = []
        for slot in slots:
            try:
                probe = row.probe(slot)
            except KeyError:
                values = []
                break
            if probe.value_c is None:
                values = []
                break
            values.append((slot, probe.value_c))
        if len(values) == len(slots):
            spread = max(value for _slot, value in values) - min(
                value for _slot, value in values
            )
            spreads.append((index, spread, tuple(values)))
    if not spreads:
        return None
    values = [spread for _index, spread, _pair in spreads]
    max_index, max_spread, max_pair = max(
        spreads, key=lambda item: item[1]
    )
    return ChamberAirSpread(
        slots=slots,
        n=len(values),
        min_c=min(values),
        median_c=percentile(values, 0.5, config.percentile_method) or 0.0,
        p95_c=percentile(values, 0.95, config.percentile_method) or 0.0,
        max_c=max_spread,
        max_time_s=(
            times[max_index]
            if times is not None and len(times) == len(rows)
            else None
        ),
        max_values=max_pair,
    )


def analyze_sessions(
    capture: Capture, *, config: QAConfig = DEFAULT_QA_CONFIG
) -> tuple[SessionSamplingSummary, ...]:
    summaries: list[SessionSamplingSummary] = []
    for session_id, rows in _session_rows(capture).items():
        times, domain_status, detail = _trusted_times(capture, rows)
        identity_keys = _identity_keys(rows)
        unique_identities = len(set(identity_keys))
        usable_rows = sum(
            1
            for row in rows
            if any(token not in ("", "NONE") for token in row.usable_for)
        )
        if times is None or len(times) < 2:
            if times is None:
                incomplete_reasons = ("TIME_BASE_UNTRUSTED",)
            else:
                incomplete_reasons = ("FEWER_THAN_TWO_SAMPLES",)
            stats = IntervalStatistics(
                time_base_status=domain_status,
                time_base_detail=detail,
                interval_count=0,
                positive_interval_count=0,
                zero_interval_count=0,
                negative_interval_count=0,
                median_dt_s=None,
                p95_dt_s=None,
                min_positive_dt_s=None,
                max_positive_dt_s=None,
                nominal_dt_s=None,
                nominal_source="NOT_ESTIMABLE",
                nominal_confidence="NOT_ESTIMABLE",
                jitter_median_abs_s=None,
                jitter_p95_abs_s=None,
                jitter_min_s=None,
                jitter_max_s=None,
                long_gap_count=0,
                long_gap_total_s=None,
                seq_missing_estimate=None,
                seq_semantics="NOT_ESTIMABLE",
                time_missing_estimate=None,
                observation_window_s=None,
                expected_samples_provisional=None,
                captured_frame_completeness=None,
                completeness_status=COMPLETENESS_NOT_ESTIMABLE,
                reasons=incomplete_reasons,
            )
            first_time = None
            last_time = None
        else:
            stats = compute_interval_statistics(
                times,
                [row.seq for row in rows],
                config=config,
            )
            if domain_status in (
                TIME_BASE_TRUSTED_EVENT_UTC,
                TIME_BASE_EVENT_UTC_UNVERIFIED_SYNC,
            ):
                stats = replace(
                    stats,
                    time_base_status=domain_status,
                    time_base_detail=detail,
                )
            first_time = times[0]
            last_time = times[-1]
        summaries.append(
            SessionSamplingSummary(
                session_id=session_id,
                device_id=rows[0].device_id,
                boot_id=rows[0].boot_id,
                row_count=len(rows),
                unique_identity_count=unique_identities,
                duplicate_identity_count=len(rows) - unique_identities,
                scientific_usable_rows=usable_rows,
                scientific_sample_coverage=usable_rows / len(rows),
                scientific_coverage_note=(
                    "row-level usable_for ledger from the source; never upgraded "
                    "by diagnostic readability"
                ),
                campaign_completeness=CAMPAIGN_COMPLETENESS,
                interval_stats=stats,
                first_time_s=first_time,
                last_time_s=last_time,
                run_segments=_run_segments(rows, times),
                chamber_air_spread=_chamber_air_spread(
                    capture, rows, times, config
                ),
            )
        )
    return tuple(summaries)


_C_OPTIONAL_FIELDS = {
    "pressure_hpa": "pressure_hpa",
    "door_polarity": "door_polarity",
    "pwm_req_permille": "requested_duty_permille",
    "pwm_readback_permille": "readback_duty_permille",
}


def _carried(capture: Capture, token: str, section: str | None = None) -> bool:
    if capture.source.format == SOURCE_FORMAT_A_W09_EXPORT:
        return token in capture.recognized_fields
    if capture.source.format == SOURCE_FORMAT_C_TELEMETRY_V1:
        if token in _C_OPTIONAL_FIELDS:
            channel = _C_OPTIONAL_FIELDS[token]
            return any(
                _extract_value(capture, row, channel) is not None
                for row in capture.rows
            )
        return section is not None and section in capture.recognized_fields
    return any(
        _extract_value(capture, row, token) is not None for row in capture.rows
    )


def _time_carried(capture: Capture, channel: str, c_wire_name: str) -> bool:
    if capture.source.format == SOURCE_FORMAT_C_TELEMETRY_V1:
        return c_wire_name in capture.recognized_fields
    return _carried(capture, channel, None)


def _extract_value(capture: Capture, row: NormalizedRow, channel: str) -> Any:
    if channel in ("t1", "t2", "t3", "t4"):
        try:
            return row.probe(channel).value_c
        except KeyError:
            return None
    return {
        "t_air_c": row.t_air_c,
        "rh_pct": row.rh_pct,
        "pressure_hpa": row.pressure_hpa,
        "door_state": row.door_state,
        "door_polarity": row.door_polarity,
        "cooling_voltage_v": row.cooling_voltage_v,
        "cooling_current_a": row.cooling_current_a,
        "cooling_power_w": row.cooling_power_w,
        "cooling_energy_counter_wh": row.cooling_energy_counter_wh,
        "applied_cooling_state": row.applied_cooling,
        "requested_duty_permille": row.requested_duty_permille,
        "applied_duty_permille": row.applied_duty_permille,
        "readback_duty_permille": row.readback_duty_permille,
        "seq": row.seq,
        "device_ms": row.device_ms,
        "event_time_utc": row.event_time_utc,
    }.get(channel)


def _quality_domains(capture: Capture) -> set[str]:
    return {domain for row in capture.rows for domain, _quality in row.quality}


def _effective_domain(capture: Capture, domain: str) -> str | None:
    """A missing per-domain verdict is NOT-VALID, never valid-by-default.

    ``overall`` is a different claim from a channel-domain verdict; using it
    as a fallback would silently over-qualify a channel whose producer never
    supplied that domain (Doc 01 §19.4; data-dictionary quality-absent rule).
    """
    return domain if domain in _quality_domains(capture) else None


def _channel_specs(capture: Capture, config: QAConfig) -> list[ChannelSpec]:
    specs: list[ChannelSpec] = []
    for slot in sorted({role.slot for role in capture.sensors}):
        role = capture.sensor(slot)
        specs.append(
            ChannelSpec(
                channel=slot,
                family="DS18B20",
                physical_role=role.physical_position or "UNKNOWN_ROLE_NOT_CARRIED",
                unit="degC",
                domain="thermal",
                kind="measurement",
                minimum=DS18B20_MIN_C,
                maximum=DS18B20_MAX_C,
                flatline_applicable=True,
                flatline_tolerance=config.flatline_temperature_tolerance_c,
                stale_applicable=True,
                source_age_field=f"{slot}_age_ms",
            )
        )
    if _carried(capture, "air_c", "environment"):
        specs.append(
            ChannelSpec(
                channel="t_air_c",
                family="BME280",
                physical_role="ENVIRONMENT_CONTEXT",
                unit="degC",
                domain="environment",
                kind="measurement",
                minimum=BME280_MIN_C,
                maximum=BME280_MAX_C,
                flatline_applicable=True,
                flatline_tolerance=BME280_RESOLUTION_C,
            )
        )
    if _carried(capture, "rh_pct", "environment"):
        specs.append(
            ChannelSpec(
                channel="rh_pct",
                family="BME280",
                physical_role="ENVIRONMENT_CONTEXT",
                unit="percent_RH",
                domain="environment",
                kind="measurement",
                minimum=RH_MIN_PCT,
                maximum=RH_MAX_PCT,
                flatline_applicable=True,
                flatline_tolerance=RH_RESOLUTION_PCT,
            )
        )
    if _carried(capture, "pressure_hpa", "environment"):
        specs.append(
            ChannelSpec(
                channel="pressure_hpa",
                family="BME280",
                physical_role="ENVIRONMENT_CONTEXT_NOT_P0_FEATURE",
                unit="hPa",
                domain="environment",
                kind="measurement",
                minimum=PRESSURE_MIN_HPA,
                maximum=PRESSURE_MAX_HPA,
                flatline_applicable=True,
                flatline_tolerance=PRESSURE_RESOLUTION_HPA,
            )
        )
    if _carried(capture, "door_open", "door"):
        specs.append(
            ChannelSpec(
                channel="door_state",
                family="DOOR",
                physical_role="CHAMBER_DOOR",
                unit="state",
                domain="door",
                kind="state",
                state_values=("OPEN", "CLOSED", "UNKNOWN"),
            )
        )
    if _carried(capture, "door_polarity", "door"):
        specs.append(
            ChannelSpec(
                channel="door_polarity",
                family="DOOR",
                physical_role="DOOR_POLARITY_EVIDENCE",
                unit="state",
                domain="door",
                kind="state",
                state_values=("CONFIRMED", "UNCONFIRMED"),
            )
        )
    if _carried(capture, "voltage_v", "electrical"):
        specs.append(
            ChannelSpec(
                channel="cooling_voltage_v",
                family="PZEM-017",
                physical_role="COOLING_BRANCH_VOLTAGE",
                unit="V",
                domain="electrical",
                kind="measurement",
                minimum=PZEM_VOLTAGE_MIN_V,
                maximum=PZEM_VOLTAGE_MAX_V,
            )
        )
    if _carried(capture, "current_a", "electrical"):
        specs.append(
            ChannelSpec(
                channel="cooling_current_a",
                family="PZEM-017",
                physical_role="COOLING_BRANCH_CURRENT",
                unit="A",
                domain="electrical",
                kind="measurement",
                minimum=PZEM_CURRENT_MIN_A,
                maximum=PZEM_CURRENT_MAX_A,
            )
        )
    if _carried(capture, "power_w", "electrical"):
        specs.append(
            ChannelSpec(
                channel="cooling_power_w",
                family="PZEM-017",
                physical_role="COOLING_BRANCH_POWER",
                unit="W",
                domain="electrical",
                kind="measurement",
                minimum=PZEM_POWER_MIN_W,
                maximum=PZEM_POWER_MAX_W,
            )
        )
    if _carried(capture, "energy_wh", "electrical"):
        specs.append(
            ChannelSpec(
                channel="cooling_energy_counter_wh",
                family="PZEM-017",
                physical_role="COOLING_BRANCH_ENERGY_COUNTER",
                unit="Wh",
                domain="electrical",
                kind="counter",
                minimum=0.0,
                maximum=None,
                counter=True,
            )
        )
    if _carried(capture, "pwm_req_permille", "actuation"):
        specs.append(
            ChannelSpec(
                channel="requested_duty_permille",
                family="ACTUATION",
                physical_role="REQUESTED_DUTY",
                unit="permille",
                domain="producer",
                kind="state",
                minimum=DUTY_MIN_PERMILLE,
                maximum=DUTY_MAX_PERMILLE,
            )
        )
    if _carried(capture, "pwm_applied_permille", "actuation"):
        specs.append(
            ChannelSpec(
                channel="applied_duty_permille",
                family="ACTUATION",
                physical_role="APPLIED_DUTY",
                unit="permille",
                domain="producer",
                kind="state",
                minimum=DUTY_MIN_PERMILLE,
                maximum=DUTY_MAX_PERMILLE,
            )
        )
        specs.append(
            ChannelSpec(
                channel="applied_cooling_state",
                family="ACTUATION",
                physical_role="APPLIED_COOLING_STATE",
                unit="state",
                domain="producer",
                kind="state",
                state_values=("ON", "OFF"),
            )
        )
    if _carried(capture, "pwm_readback_permille", "actuation"):
        specs.append(
            ChannelSpec(
                channel="readback_duty_permille",
                family="ACTUATION",
                physical_role="READBACK_DUTY",
                unit="permille",
                domain="producer",
                kind="state",
                minimum=DUTY_MIN_PERMILLE,
                maximum=DUTY_MAX_PERMILLE,
            )
        )
    if _time_carried(capture, "seq", "seq"):
        specs.append(
            ChannelSpec(
                channel="seq",
                family="IDENTITY",
                physical_role="SEQUENCE",
                unit="count",
                domain="sequence",
                kind="counter",
                minimum=0.0,
            )
        )
    if capture.time.domain == TIME_EVENT_UTC:
        if _time_carried(capture, "timestamp_utc", "captured_at"):
            specs.append(
                ChannelSpec(
                    channel="event_time_utc",
                    family="TIME",
                    physical_role="EVENT_TIME_UTC",
                    unit="datetime",
                    domain="provenance",
                    kind="time",
                )
            )
    elif capture.time.domain == TIME_BOOT_SCOPED_UPTIME:
        if _time_carried(capture, "device_ms", "uptime_ms"):
            specs.append(
                ChannelSpec(
                    channel="device_ms",
                    family="TIME",
                    physical_role="BOOT_SCOPED_UPTIME",
                    unit="ms",
                    domain="provenance",
                    kind="time",
                    minimum=0.0,
                )
            )
    else:
        if _time_carried(capture, "device_ms", "uptime_ms"):
            specs.append(
                ChannelSpec(
                    channel="device_ms",
                    family="TIME",
                    physical_role="BOOT_SCOPED_UPTIME_TIME_BASE_UNTRUSTED",
                    unit="ms",
                    domain="provenance",
                    kind="time",
                    minimum=0.0,
                )
            )
    return specs


def _quality_counts(
    rows: Sequence[NormalizedRow], domain: str | None
) -> tuple[dict[str, int], bool]:
    counts = {"VALID": 0, "DEGRADED": 0, "INVALID": 0, "UNKNOWN": 0}
    domain_absent = False
    for row in rows:
        mapping = dict(row.quality)
        quality = mapping.get(domain) if domain is not None else None
        if quality is None:
            domain_absent = True
            quality = "UNKNOWN"
        if quality not in counts:
            quality = "UNKNOWN"
        counts[quality] += 1
    return counts, domain_absent


def _flatline_candidates(
    rows: Sequence[NormalizedRow],
    times_s: Sequence[float] | None,
    values: Sequence[float | None],
    domain: str | None,
    *,
    tolerance: float,
    minimum_observations: int,
    minimum_span_s: float,
    long_gap_s: float,
) -> tuple[int, tuple[float, float] | None]:
    if times_s is None or len(times_s) != len(rows):
        return 0, None
    candidates = 0
    first_span: tuple[float, float] | None = None
    span_values: list[float] = []
    span_start: float | None = None
    span_end: float | None = None
    previous_time: float | None = None

    def close_span() -> None:
        nonlocal candidates, first_span, span_values, span_start, span_end
        if (
            span_values
            and len(span_values) >= minimum_observations
            and span_start is not None
            and span_end is not None
            and (span_end - span_start) >= minimum_span_s
            and (max(span_values) - min(span_values)) <= tolerance
        ):
            candidates += 1
            if first_span is None and span_start is not None and span_end is not None:
                first_span = (span_start, span_end)
        span_values = []
        span_start = None
        span_end = None

    for row, time_s, value in zip(rows, times_s, values):
        quality = dict(row.quality).get(domain) if domain is not None else None
        if value is None or quality == "INVALID":
            close_span()
            previous_time = time_s
            continue
        numeric = float(value)
        if previous_time is not None and (time_s - previous_time) > long_gap_s:
            close_span()
        if span_values and (
            abs(numeric - span_values[0]) > tolerance
            or abs(numeric - span_values[-1]) > tolerance
        ):
            # A plateau that later steps away is still a flatline candidate;
            # do not require a missing/INVALID row to close the span.
            close_span()
        if not span_values:
            span_start = time_s
        span_values.append(numeric)
        span_end = time_s
        previous_time = time_s
    close_span()
    return candidates, first_span


def _stale_count(
    capture: Capture,
    rows: Sequence[NormalizedRow],
    spec: ChannelSpec,
    stale_age_ms: int,
) -> tuple[int | None, bool, bool]:
    if not spec.stale_applicable or spec.source_age_field is None:
        return None, False, False
    if capture.source.format == SOURCE_FORMAT_A_W09_EXPORT:
        if spec.source_age_field not in capture.recognized_fields:
            return None, True, False
    ages: list[int] = []
    for row in rows:
        try:
            probe = row.probe(spec.channel)
        except KeyError:
            continue
        if probe.age_ms is not None:
            ages.append(probe.age_ms)
    if not ages:
        return None, True, False
    partial = len(ages) < len(rows)
    return sum(1 for age in ages if age > stale_age_ms), False, partial


def _diagnostic_status(
    *,
    row_count: int,
    present: int,
    impossible: int,
    quality_invalid: int,
    quality_degraded: int,
    quality_unknown: int,
    missing: int,
) -> str:
    if present == 0:
        return "NOT_ESTIMABLE"
    if impossible or quality_invalid:
        return "DIAGNOSTIC_CAUTION"
    if missing or quality_degraded or quality_unknown:
        return "DIAGNOSTIC_READABLE_UNQUALIFIED"
    return "DIAGNOSTIC_QUALIFIED"


def analyze_channels(
    capture: Capture,
    sessions: Sequence[SessionSamplingSummary],
    *,
    admission: AdmissionResult,
    config: QAConfig = DEFAULT_QA_CONFIG,
) -> tuple[ChannelSummary, ...]:
    config.validate()
    summaries: list[ChannelSummary] = []
    rows_by_session = _session_rows(capture)
    session_times: dict[str, Sequence[float] | None] = {}
    for session in sessions:
        rows = rows_by_session.get(session.session_id, [])
        times, _status, _detail = _trusted_times(capture, rows)
        session_times[session.session_id] = times

    for session in sessions:
        rows = rows_by_session.get(session.session_id, [])
        times = session_times[session.session_id]
        if not rows:
            continue
        identity_keys = _identity_keys(rows)
        duplicate_rows = len(identity_keys) - len(set(identity_keys))

        for spec in _channel_specs(capture, config):
            values = [_extract_value(capture, row, spec.channel) for row in rows]
            domain = _effective_domain(capture, spec.domain)
            quality, domain_absent = _quality_counts(rows, domain)
            reasons: list[str] = []
            if domain_absent:
                reasons.append("QUALITY_DOMAIN_ABSENT_TREATED_AS_UNKNOWN")

            if spec.kind == "state":
                if spec.channel == "door_state":
                    present = sum(1 for value in values if value in ("OPEN", "CLOSED"))
                    unknown_state = sum(1 for value in values if value == "UNKNOWN")
                    missing = len(rows) - present - unknown_state
                    open_count = sum(1 for value in values if value == "OPEN")
                    if unknown_state:
                        reasons.append("DOOR_STATE_UNKNOWN_PRESENT")
                    if open_count == 0 and present:
                        reasons.append("DOOR_NO_OPEN_EVENT_IN_CAPTURE")
                elif spec.channel == "door_polarity":
                    present = sum(
                        1 for value in values if value in ("CONFIRMED", "UNCONFIRMED")
                    )
                    unknown_state = len(rows) - present
                    missing = 0
                    unconfirmed = sum(
                        1 for value in values if value == "UNCONFIRMED"
                    )
                    if unconfirmed:
                        reasons.append("DOOR_POLARITY_UNCONFIRMED_PRESENT")
                elif spec.channel == "applied_cooling_state":
                    present = sum(1 for value in values if value in ("ON", "OFF"))
                    unknown_state = sum(1 for value in values if value is None)
                    missing = len(rows) - present - unknown_state
                    if unknown_state:
                        reasons.append("APPLIED_COOLING_STATE_UNOBSERVED")
                else:
                    present = sum(1 for value in values if value is not None)
                    unknown_state = 0
                    missing = len(rows) - present
                impossible = 0
                if spec.minimum is not None or spec.maximum is not None:
                    for value in values:
                        if isinstance(value, (int, float)) and not isinstance(
                            value, bool
                        ):
                            if spec.minimum is not None and value < spec.minimum:
                                impossible += 1
                            elif spec.maximum is not None and value > spec.maximum:
                                impossible += 1
                    if impossible:
                        reasons.append(
                            "IMPOSSIBLE_VALUE_OUTSIDE_INSTRUMENT_RANGE"
                        )
                flatline = None
                stale = None
                repeated = None
                discontinuity = 0
                missing_fraction = missing / len(rows)
            elif spec.channel == "event_time_utc":
                present = sum(1 for value in values if value is not None)
                unknown_state = 0
                missing = len(rows) - present
                missing_fraction = missing / len(rows)
                impossible = 0
                flatline = None
                stale = None
                repeated = None
                discontinuity = 0
            else:
                numeric_values = [
                    float(value) for value in values if value is not None
                ]
                present = len(numeric_values)
                missing = len(rows) - present
                missing_fraction = missing / len(rows)
                unknown_state = 0
                impossible = 0
                for value in numeric_values:
                    if not math.isfinite(value):
                        impossible += 1
                        continue
                    if spec.minimum is not None and value < spec.minimum:
                        impossible += 1
                    elif spec.maximum is not None and value > spec.maximum:
                        impossible += 1
                if impossible:
                    reasons.append("IMPOSSIBLE_VALUE_OUTSIDE_INSTRUMENT_RANGE")
                repeated = 0
                for index in range(1, len(values)):
                    left, right = values[index - 1], values[index]
                    if left is not None and right is not None and left == right:
                        repeated += 1
                discontinuity = 0
                if spec.counter:
                    previous: float | None = None
                    for value in numeric_values:
                        if previous is not None and value < previous:
                            discontinuity += 1
                        previous = value
                    if discontinuity:
                        reasons.append("COUNTER_DECREASE_OR_RESET")
                if spec.flatline_applicable and spec.flatline_tolerance is not None:
                    flatline, span = _flatline_candidates(
                        rows,
                        times,
                        values,
                        domain,
                        tolerance=spec.flatline_tolerance,
                        minimum_observations=config.flatline_min_observations,
                        minimum_span_s=config.flatline_min_span_s,
                        long_gap_s=config.long_gap_ms / 1000.0,
                    )
                    if flatline:
                        reasons.append("FLATLINE_CANDIDATE_DIAGNOSTIC_ONLY")
                        if span is not None:
                            reasons.append(
                                f"FLATLINE_FIRST_SPAN_{span[0]:.3f}_{span[1]:.3f}s"
                            )
                else:
                    flatline = None
                stale, age_absent, age_partial = _stale_count(
                    capture, rows, spec, config.stale_age_ms
                )
                if age_absent:
                    reasons.append("SOURCE_AGE_NOT_CARRIED")
                else:
                    if age_partial:
                        reasons.append("SOURCE_AGE_PARTIAL")
                    if stale:
                        reasons.append("SOURCE_AGE_EXCEEDS_DIAGNOSTIC_THRESHOLD")

            if missing:
                reasons.append("MISSING_VALUES")
            if quality["INVALID"]:
                reasons.append("SOURCE_QUALITY_INVALID")
            if quality["DEGRADED"]:
                reasons.append("SOURCE_QUALITY_DEGRADED")
            if quality["UNKNOWN"]:
                reasons.append("SOURCE_QUALITY_UNKNOWN")
            electrical_fully_valid = (
                present == len(rows)
                and quality["VALID"] == len(rows)
                and impossible == 0
            )
            if spec.channel == "cooling_power_w" and present:
                reasons.append(
                    "PZEM_POWER_DOMAIN_VALID"
                    if electrical_fully_valid
                    else "PZEM_POWER_UNQUALIFIED_DIAGNOSTIC_ONLY"
                )
            if spec.channel == "cooling_energy_counter_wh" and present:
                reasons.append(
                    "PZEM_ENERGY_DOMAIN_VALID"
                    if electrical_fully_valid
                    else "PZEM_ENERGY_UNQUALIFIED_DIAGNOSTIC_ONLY"
                )

            status = _diagnostic_status(
                row_count=len(rows),
                present=present + unknown_state,
                impossible=impossible,
                quality_invalid=quality["INVALID"],
                quality_degraded=quality["DEGRADED"],
                quality_unknown=quality["UNKNOWN"],
                missing=missing,
            )
            if spec.kind == "time" and times is None:
                status = "NOT_ESTIMABLE"
            summaries.append(
                ChannelSummary(
                    source_id=capture.source.path,
                    source_sha256=capture.source.sha256,
                    session_id=session.session_id,
                    device_id=session.device_id,
                    boot_id=session.boot_id,
                    run_id=capture.run.run_id,
                    run_id_status=capture.run.run_id_status,
                    run_segment_count=len(session.run_segments),
                    channel=spec.channel,
                    family=spec.family,
                    physical_role=spec.physical_role,
                    unit=spec.unit,
                    row_count=len(rows),
                    present_count=present,
                    missing_count=missing,
                    missing_fraction=missing_fraction,
                    quality_valid=quality["VALID"],
                    quality_degraded=quality["DEGRADED"],
                    quality_invalid=quality["INVALID"],
                    quality_unknown=quality["UNKNOWN"],
                    impossible_count=impossible,
                    flatline_candidate_count=flatline,
                    stale_candidate_count=stale,
                    duplicate_identity_count=duplicate_rows,
                    repeated_equal_consecutive_count=repeated,
                    discontinuity_count=discontinuity,
                    unknown_state_count=unknown_state,
                    quality_domain=domain,
                    diagnostic_status=status,
                    reason_codes=tuple(sorted(set(reasons))),
                    physical_admission_status=admission.status.value,
                )
            )
    return tuple(
        sorted(
            summaries,
            key=lambda item: (
                item.source_id,
                item.session_id,
                item.channel,
            ),
        )
    )


def _build_anomalies(
    capture: Capture,
    sessions: Sequence[SessionSamplingSummary],
    channels: Sequence[ChannelSummary],
    admission: AdmissionResult,
) -> tuple[Anomaly, ...]:
    anomalies: list[Anomaly] = []
    for session in sessions:
        stats = session.interval_stats
        if stats.time_base_status == TIME_BASE_UNTRUSTED:
            anomalies.append(
                Anomaly(
                    code="TIME_BASE_UNTRUSTED",
                    severity="HIGH",
                    scope="session",
                    channel=None,
                    count=None,
                    detail=stats.time_base_detail,
                )
            )
        if stats.time_base_status == TIME_BASE_EVENT_UTC_UNVERIFIED_SYNC:
            anomalies.append(
                Anomaly(
                    code="EVENT_TIME_SYNC_UNVERIFIED",
                    severity="MEDIUM",
                    scope="session",
                    channel=None,
                    count=None,
                    detail=(
                        "event UTC is usable for within-boot deltas only; "
                        "clock synchronisation is not evidenced, so absolute "
                        "latency and cross-boot claims remain unsupported"
                    ),
                )
            )
        if "FEWER_THAN_TWO_SAMPLES" in stats.reasons:
            anomalies.append(
                Anomaly(
                    code="SAMPLING_INTERVAL_NOT_ESTIMABLE",
                    severity="INFO",
                    scope="session",
                    channel=None,
                    count=session.row_count,
                    detail="fewer than two samples; no Δt distribution is computed",
                )
            )
        if stats.negative_interval_count:
            anomalies.append(
                Anomaly(
                    code="NEGATIVE_INTERVAL_PRESENT",
                    severity="HIGH",
                    scope="session",
                    channel=None,
                    count=stats.negative_interval_count,
                    detail="non-increasing event times were counted, not discarded",
                )
            )
        if stats.zero_interval_count:
            anomalies.append(
                Anomaly(
                    code="ZERO_INTERVAL_PRESENT",
                    severity="MEDIUM",
                    scope="session",
                    channel=None,
                    count=stats.zero_interval_count,
                    detail=(
                        "equal event times with increasing sequence; excluded "
                        "from the positive-interval distribution"
                    ),
                )
            )
        if stats.long_gap_count:
            anomalies.append(
                Anomaly(
                    code="LONG_GAP_PRESENT",
                    severity="MEDIUM",
                    scope="session",
                    channel=None,
                    count=stats.long_gap_count,
                    detail=(
                        f"{stats.long_gap_count} interval(s) above the "
                        f"diagnostic threshold, total "
                        f"{stats.long_gap_total_s or 0.0:.3f} s"
                    ),
                )
            )
        if stats.seq_missing_estimate:
            anomalies.append(
                Anomaly(
                    code="SEQUENCE_GAP_ESTIMATE",
                    severity="MEDIUM",
                    scope="session",
                    channel="seq",
                    count=stats.seq_missing_estimate,
                    detail=(
                        "sequence deltas exceed one; a gap is not proof of a "
                        "missing physical sample without sequence semantics"
                    ),
                )
            )
        if session.duplicate_identity_count:
            anomalies.append(
                Anomaly(
                    code="DUPLICATE_IDENTITY_PRESENT",
                    severity="HIGH",
                    scope="session",
                    channel=None,
                    count=session.duplicate_identity_count,
                    detail="duplicate (device, boot, seq) identity in one capture",
                )
            )
        anomalies.append(
            Anomaly(
                code="CAMPAIGN_COMPLETENESS_NOT_ESTIMABLE",
                severity="INFO",
                scope="session",
                channel=None,
                count=None,
                detail=(
                    "acquisition boundaries and schedule are not carried; "
                    "filename or label duration is not used as evidence"
                ),
            )
        )
    for channel in channels:
        if channel.missing_count:
            severity = "LOW" if channel.missing_fraction < 0.5 else "MEDIUM"
            anomalies.append(
                Anomaly(
                    code="CHANNEL_MISSING_VALUES",
                    severity=severity,
                    scope="channel",
                    channel=channel.channel,
                    count=channel.missing_count,
                    detail=(
                        f"{channel.missing_count}/{channel.row_count} missing "
                        f"({channel.missing_fraction:.6f})"
                    ),
                )
            )
        if channel.impossible_count:
            anomalies.append(
                Anomaly(
                    code="CHANNEL_IMPOSSIBLE_VALUE",
                    severity="HIGH",
                    scope="channel",
                    channel=channel.channel,
                    count=channel.impossible_count,
                    detail="value outside the canonical instrument/domain range",
                )
            )
        if channel.quality_invalid:
            anomalies.append(
                Anomaly(
                    code="CHANNEL_SOURCE_QUALITY_INVALID",
                    severity="MEDIUM",
                    scope="channel",
                    channel=channel.channel,
                    count=channel.quality_invalid,
                    detail="source marked observations INVALID; kept visible",
                )
            )
        if channel.quality_unknown:
            anomalies.append(
                Anomaly(
                    code="CHANNEL_SOURCE_QUALITY_UNKNOWN",
                    severity="LOW",
                    scope="channel",
                    channel=channel.channel,
                    count=channel.quality_unknown,
                    detail="values may exist but are unqualified for evidence",
                )
            )
        if channel.flatline_candidate_count:
            anomalies.append(
                Anomaly(
                    code="CHANNEL_FLATLINE_CANDIDATE",
                    severity="LOW",
                    scope="channel",
                    channel=channel.channel,
                    count=channel.flatline_candidate_count,
                    detail=(
                        "sustained constant span at measurement resolution; a "
                        "candidate only, never proof of sensor failure"
                    ),
                )
            )
        if channel.stale_candidate_count:
            anomalies.append(
                Anomaly(
                    code="CHANNEL_STALE_CANDIDATE",
                    severity="MEDIUM",
                    scope="channel",
                    channel=channel.channel,
                    count=channel.stale_candidate_count,
                    detail="source-provided sensor age exceeded the diagnostic threshold",
                )
            )
        if channel.discontinuity_count:
            anomalies.append(
                Anomaly(
                    code="CHANNEL_COUNTER_DISCONTINUITY",
                    severity="MEDIUM",
                    scope="channel",
                    channel=channel.channel,
                    count=channel.discontinuity_count,
                    detail="counter decrease/reset; energy conclusion remains unsupported",
                )
            )
        if channel.channel == "door_state":
            if channel.unknown_state_count:
                anomalies.append(
                    Anomaly(
                        code="DOOR_STATE_UNKNOWN_PRESENT",
                        severity="LOW",
                        scope="channel",
                        channel=channel.channel,
                        count=channel.unknown_state_count,
                        detail="UNKNOWN is retained; it is never interpreted as CLOSED",
                    )
                )
            if channel.present_count and "DOOR_NO_OPEN_EVENT_IN_CAPTURE" in channel.reason_codes:
                anomalies.append(
                    Anomaly(
                        code="DOOR_NO_QUALIFYING_OPEN_EVENT",
                        severity="INFO",
                        scope="channel",
                        channel=channel.channel,
                        count=0,
                        detail=(
                            "no OPEN interval observed; no door disturbance may "
                            "be claimed from this capture"
                        ),
                    )
                )
        if (
            channel.channel == "cooling_power_w"
            and "PZEM_POWER_UNQUALIFIED_DIAGNOSTIC_ONLY" in channel.reason_codes
        ):
            anomalies.append(
                Anomaly(
                    code="PZEM_POWER_UNQUALIFIED",
                    severity="INFO",
                    scope="channel",
                    channel=channel.channel,
                    count=channel.row_count - channel.quality_valid,
                    detail=(
                        "plotted for diagnostics only; not validated power or "
                        "energy evidence"
                    ),
                )
            )
    if capture.unknown_role_slots:
        anomalies.append(
            Anomaly(
                code="SENSOR_ROLE_UNKNOWN_OR_CONFLICTING",
                severity="HIGH",
                scope="source",
                channel=None,
                count=len(capture.unknown_role_slots),
                detail=(
                    f"slots {list(capture.unknown_role_slots)} cannot enter a "
                    "role-dependent aggregate"
                ),
            )
        )
    if capture.hot_side_slots:
        anomalies.append(
            Anomaly(
                code="HOT_SIDE_EXCLUDED_FROM_CHAMBER_AIR",
                severity="INFO",
                scope="source",
                channel=", ".join(capture.hot_side_slots),
                count=None,
                detail="TEC hot-side channel is reported separately, never as chamber air",
            )
        )
    unverified_rom = [
        role.slot for role in capture.sensors if role.rom_readback_verified is False
    ]
    if unverified_rom:
        anomalies.append(
            Anomaly(
                code="SENSOR_ROM_READBACK_UNVERIFIED",
                severity="LOW",
                scope="source",
                channel=", ".join(unverified_rom),
                count=len(unverified_rom),
                detail=(
                    "the sensor block carries ROMs whose readback is not "
                    "verified; positions come from the operator-frozen as-built "
                    "record, not from a W05 re-measurement"
                ),
            )
        )
    if capture.run.run_id_status != "SOURCE_CARRIED_SINGLE" or capture.run.run_id is None:
        anomalies.append(
            Anomaly(
                code="RUN_ID_UNRESOLVED",
                severity="MEDIUM",
                scope="source",
                channel=None,
                count=None,
                detail=(
                    f"run_id_status={capture.run.run_id_status}; multiple "
                    "filenames or row labels never create independent runs"
                ),
            )
        )
    if not admission.eligible:
        anomalies.append(
            Anomaly(
                code="W04_ADMISSION_BLOCKED",
                severity="INFO",
                scope="source",
                channel=None,
                count=len(admission.blockers),
                detail=(
                    f"W04 highest stage {admission.highest_stage.value}; the "
                    "diagnostic view remains readable"
                ),
            )
        )
    return tuple(
        sorted(
            anomalies,
            key=lambda item: (
                item.scope,
                item.channel or "",
                item.code,
            ),
        )
    )


def _structure_status(admission: AdmissionResult) -> str:
    structural_stages = {
        AdmissionStage.SOURCE_RECOGNIZED,
        AdmissionStage.STRUCTURALLY_VALID,
    }
    if any(blocker.stage in structural_stages for blocker in admission.blockers):
        return SOURCE_STRUCTURE_INVALID
    return SOURCE_STRUCTURE_VALID


def _channel_quality_status(channels: Sequence[ChannelSummary]) -> str:
    if not channels:
        return CHANNEL_QUALITY_NOT_ESTIMABLE
    readable = [channel for channel in channels if channel.diagnostic_status != "NOT_ESTIMABLE"]
    if not readable:
        return CHANNEL_QUALITY_NOT_ESTIMABLE
    for channel in readable:
        if (
            channel.impossible_count
            or channel.quality_invalid
            or channel.missing_count
            or channel.quality_degraded
            or channel.quality_unknown
            or channel.flatline_candidate_count
            or channel.stale_candidate_count
            or channel.discontinuity_count
            or channel.diagnostic_status
            in ("DIAGNOSTIC_CAUTION", "DIAGNOSTIC_READABLE_UNQUALIFIED")
        ):
            return CHANNEL_QUALITY_ATTENTION
    return CHANNEL_QUALITY_QUALIFIED


def analyze_capture(
    capture: Capture,
    *,
    config: QAConfig = DEFAULT_QA_CONFIG,
    admission: AdmissionResult | None = None,
) -> QAAnalysis:
    """Run diagnostic QA without changing the W04 admission verdict."""
    config.validate()
    result = admission if admission is not None else evaluate_admission(capture)
    sessions = analyze_sessions(capture, config=config)
    channels = analyze_channels(
        capture,
        sessions,
        admission=result,
        config=config,
    )
    anomalies = _build_anomalies(capture, sessions, channels, result)
    statuses = QAStatuses(
        qa_execution_status=QA_EXECUTION_COMPLETED,
        source_structure_status=_structure_status(result),
        channel_quality_status=_channel_quality_status(channels),
        physical_admission_status=result.status.value,
        physical_highest_stage=result.highest_stage.value,
        predictive_dataset_readiness=result.predictive_dataset_readiness,
    )
    return QAAnalysis(
        capture=capture,
        admission=result,
        sessions=sessions,
        channels=channels,
        anomalies=anomalies,
        statuses=statuses,
        config=config,
    )


def analyze_captures(
    captures: Iterable[Capture],
    *,
    config: QAConfig = DEFAULT_QA_CONFIG,
) -> tuple[QAAnalysis, ...]:
    analyses = [analyze_capture(capture, config=config) for capture in captures]
    return tuple(
        sorted(analyses, key=lambda item: (item.capture.source.path, item.capture.source.sha256))
    )


def summarize_qa_suite(analyses: Sequence[QAAnalysis]) -> QASuiteSummary:
    admissions = [analysis.admission for analysis in analyses]
    readiness = summarize_readiness(admissions)
    independent = count_independent_runs(
        analysis.capture for analysis in analyses
    )
    conflicts = tuple(
        exclusion
        for exclusion in readiness.exclusions
        if any(
            blocker.get("code") == "DUPLICATE_VIEW_ADMISSION_CONFLICT"
            for blocker in exclusion.get("blockers", [])
        )
    )
    return QASuiteSummary(
        analyzed_sources=len(analyses),
        unique_physical_sources=independent.unique_physical_sources,
        duplicate_views=independent.duplicate_views,
        eligible_s1_runs=readiness.eligible_s1_runs,
        eligible_s2_runs=readiness.eligible_s2_runs,
        predictive_dataset_readiness=readiness.predictive_dataset_readiness,
        conflicts=conflicts,
    )


CSV_COLUMNS = (
    "source_id",
    "source_sha256",
    "session_id",
    "device_id",
    "boot_id",
    "run_id",
    "run_id_status",
    "run_segment_count",
    "channel",
    "family",
    "physical_role",
    "unit",
    "row_count",
    "present_count",
    "missing_count",
    "missing_fraction",
    "quality_VALID",
    "quality_DEGRADED",
    "quality_INVALID",
    "quality_UNKNOWN",
    "impossible_count",
    "flatline_candidate_count",
    "stale_candidate_count",
    "duplicate_identity_count",
    "repeated_equal_consecutive_count",
    "discontinuity_count",
    "unknown_state_count",
    "quality_domain",
    "diagnostic_status",
    "reason_codes",
    "physical_admission_status",
)

_UNAVAILABLE = "NOT_ESTIMABLE"
_NOT_APPLICABLE = "NOT_APPLICABLE"


def _csv_value(value: Any, *, unavailable: str = _UNAVAILABLE) -> str:
    if value is None:
        return unavailable
    if isinstance(value, float):
        if not math.isfinite(value):
            return _UNAVAILABLE
        return f"{value:.6f}"
    if isinstance(value, (list, tuple)):
        return "|".join(str(item) for item in value)
    return str(value)


def channel_summary_csv(analyses: Sequence[QAAnalysis]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=CSV_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    rows: list[ChannelSummary] = []
    for analysis in analyses:
        rows.extend(analysis.channels)
    unique: dict[tuple[str, str, str], ChannelSummary] = {}
    for channel in rows:
        unique.setdefault(
            (channel.source_sha256, channel.session_id, channel.channel),
            channel,
        )
    for channel in sorted(
        unique.values(),
        key=lambda item: (item.source_id, item.session_id, item.channel),
    ):
        writer.writerow(
            {
                "source_id": channel.source_id,
                "source_sha256": channel.source_sha256,
                "session_id": channel.session_id,
                "device_id": channel.device_id or _UNAVAILABLE,
                "boot_id": channel.boot_id,
                "run_id": channel.run_id or _UNAVAILABLE,
                "run_id_status": channel.run_id_status,
                "run_segment_count": channel.run_segment_count,
                "channel": channel.channel,
                "family": channel.family,
                "physical_role": channel.physical_role,
                "unit": channel.unit or _NOT_APPLICABLE,
                "row_count": channel.row_count,
                "present_count": channel.present_count,
                "missing_count": channel.missing_count,
                "missing_fraction": _csv_value(channel.missing_fraction),
                "quality_VALID": channel.quality_valid,
                "quality_DEGRADED": channel.quality_degraded,
                "quality_INVALID": channel.quality_invalid,
                "quality_UNKNOWN": channel.quality_unknown,
                "impossible_count": channel.impossible_count,
                "flatline_candidate_count": _csv_value(
                    channel.flatline_candidate_count,
                    unavailable=_NOT_APPLICABLE,
                ),
                "stale_candidate_count": _csv_value(
                    channel.stale_candidate_count,
                    unavailable=_NOT_APPLICABLE,
                ),
                "duplicate_identity_count": channel.duplicate_identity_count,
                "repeated_equal_consecutive_count": _csv_value(
                    channel.repeated_equal_consecutive_count,
                    unavailable=_NOT_APPLICABLE,
                ),
                "discontinuity_count": channel.discontinuity_count,
                "unknown_state_count": channel.unknown_state_count,
                "quality_domain": channel.quality_domain or _NOT_APPLICABLE,
                "diagnostic_status": channel.diagnostic_status,
                "reason_codes": "|".join(channel.reason_codes),
                "physical_admission_status": channel.physical_admission_status,
            }
        )
    return buffer.getvalue()


def qa_manifest(
    analyses: Sequence[QAAnalysis],
    suite: QASuiteSummary,
    *,
    config: QAConfig,
    command: str,
    repository_revision: str,
    analysis_code_sha256: str = "NOT_RECORDED",
    source_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "qa_layer_version": QA_LAYER_VERSION,
        "report_schema": "coldguard-w05-qa-report-v1",
        "analysis_code_sha256": analysis_code_sha256,
        "repository_revision": repository_revision,
        "generation_command": command,
        "config": config.to_dict(),
        "suite": suite.to_dict(),
        "source_index": source_index,
        "sources": [analysis.to_dict() for analysis in analyses],
    }


# ---------------------------------------------------------------------------
# deterministic SVG physical-state plot
# ---------------------------------------------------------------------------

_PLOT_WIDTH = 1240
_PLOT_LEFT = 96
_PLOT_RIGHT = 34
_PLOT_TOP = 80
_PLOT_PANEL_HEIGHT = 122
_PLOT_PANEL_GAP = 38
_PLOT_BOTTOM = 64

_PANEL_COLORS = ("#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#8c564b")


def _svg_float(value: float) -> str:
    return f"{value:.2f}"


def _time_scale(times: Sequence[float]) -> tuple[float, float]:
    if not times:
        return 0.0, 1.0
    start = min(times)
    end = max(times)
    if end <= start:
        return start, start + 1.0
    return start, end


def _panel_y_range(values: Sequence[float]) -> tuple[float, float]:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return 0.0, 1.0
    low = min(finite)
    high = max(finite)
    if high <= low:
        return low - 0.5, high + 0.5
    padding = (high - low) * 0.08
    return low - padding, high + padding


def _segments(
    times: Sequence[float],
    values: Sequence[Any],
    invalid: Sequence[bool],
    *,
    long_gap_s: float,
) -> list[list[tuple[float, float]]]:
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    previous_time: float | None = None
    for time_s, value, is_invalid in zip(times, values, invalid):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            if current:
                segments.append(current)
                current = []
            previous_time = time_s
            continue
        numeric = float(value)
        if not math.isfinite(numeric) or is_invalid:
            if current:
                segments.append(current)
                current = []
            previous_time = time_s
            continue
        if previous_time is not None and (time_s - previous_time) > long_gap_s:
            if current:
                segments.append(current)
                current = []
        current.append((time_s, numeric))
        previous_time = time_s
    if current:
        segments.append(current)
    return segments


def _invalid_ranges(
    times: Sequence[float], invalid: Sequence[bool]
) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    start: float | None = None
    for time_s, is_invalid in zip(times, invalid):
        if is_invalid and start is None:
            start = time_s
        elif not is_invalid and start is not None:
            ranges.append((start, time_s))
            start = None
    if start is not None and times:
        ranges.append((start, times[-1]))
    return ranges


def _render_panel(
    *,
    title: str,
    unit: str,
    series: Sequence[tuple[str, str, Sequence[Any], bool]],
    times: Sequence[float],
    top: float,
    time_start: float,
    time_end: float,
    long_gap_s: float,
    invalid_flags: Sequence[bool],
    annotations: Sequence[str] = (),
    y_bounds: tuple[float, float] | None = None,
    segment_boundaries: Sequence[float] = (),
    x_ticks: bool = False,
) -> list[str]:
    width = _PLOT_WIDTH - _PLOT_LEFT - _PLOT_RIGHT
    height = _PLOT_PANEL_HEIGHT
    numeric_values: list[float] = []
    for _label, _color, values, _dashed in series:
        numeric_values.extend(
            float(value)
            for value in values
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        )
    y_min, y_max = y_bounds if y_bounds is not None else _panel_y_range(numeric_values)
    if y_max <= y_min:
        y_max = y_min + 1.0

    def x_of(time_s: float) -> float:
        if time_end <= time_start:
            return _PLOT_LEFT
        return _PLOT_LEFT + (time_s - time_start) / (time_end - time_start) * width

    def y_of(value: float) -> float:
        return top + height - (value - y_min) / (y_max - y_min) * height

    output: list[str] = []
    output.append(
        f'<text x="{_PLOT_LEFT}" y="{_svg_float(top - 10)}" '
        f'font-size="13" font-weight="600" fill="#222">{escape(title)}</text>'
    )
    output.append(
        f'<text x="{_PLOT_LEFT + 4}" y="{_svg_float(top + 13)}" '
        f'font-size="10" fill="#666">{escape(unit)}</text>'
    )
    output.append(
        f'<rect x="{_PLOT_LEFT}" y="{_svg_float(top)}" '
        f'width="{width}" height="{height}" fill="#fbfbfb" stroke="#d0d0d0"/>'
    )
    for value in (y_min, (y_min + y_max) / 2.0, y_max):
        y = y_of(value)
        output.append(
            f'<line x1="{_PLOT_LEFT}" y1="{_svg_float(y)}" '
            f'x2="{_PLOT_LEFT + width}" y2="{_svg_float(y)}" '
            'stroke="#e6e6e6" stroke-width="1"/>'
        )
        output.append(
            f'<text x="{_PLOT_LEFT - 8}" y="{_svg_float(y + 3)}" '
            f'font-size="9" text-anchor="end" fill="#555">{value:.2f}</text>'
        )
    for start_s, end_s in _invalid_ranges(times, invalid_flags):
        x1 = x_of(start_s)
        x2 = max(x_of(end_s), x1 + 1.0)
        output.append(
            f'<rect x="{_svg_float(x1)}" y="{_svg_float(top)}" '
            f'width="{_svg_float(x2 - x1)}" height="{height}" '
            'fill="#999999" fill-opacity="0.18"/>'
        )
    for boundary in segment_boundaries:
        x = x_of(boundary)
        output.append(
            f'<line x1="{_svg_float(x)}" y1="{_svg_float(top)}" '
            f'x2="{_svg_float(x)}" y2="{_svg_float(top + height)}" '
            'stroke="#555" stroke-width="1" stroke-dasharray="3 3"/>'
        )
    if x_ticks:
        for index in range(5):
            tick = time_start + (time_end - time_start) * index / 4.0
            x = x_of(tick)
            output.append(
                f'<text x="{_svg_float(x)}" y="{_svg_float(top + height + 14)}" '
                f'font-size="9" text-anchor="middle" fill="#444">'
                f'{tick:.1f}</text>'
            )
        output.append(
            f'<text x="{_svg_float(_PLOT_LEFT + width / 2.0)}" '
            f'y="{_svg_float(top + height + 27)}" font-size="9" '
            'text-anchor="middle" fill="#444">time (s)</text>'
        )
    for label, color, values, dashed in series:
        segments = _segments(
            times,
            values,
            invalid_flags,
            long_gap_s=long_gap_s,
        )
        for segment in segments:
            if len(segment) < 2:
                x = x_of(segment[0][0])
                y = y_of(segment[0][1])
                output.append(
                    f'<circle cx="{_svg_float(x)}" cy="{_svg_float(y)}" '
                    f'r="2" fill="{color}"/>'
                )
                continue
            points = " ".join(
                f"{_svg_float(x_of(time_s))},{_svg_float(y_of(value))}"
                for time_s, value in segment
            )
            dash = ' stroke-dasharray="5 4"' if dashed else ""
            output.append(
                f'<polyline fill="none" stroke="{color}" stroke-width="1.4"'
                f'{dash} points="{points}"/>'
            )
    legend_x = _PLOT_LEFT + 8
    for index, (label, color, _values, dashed) in enumerate(series):
        legend_y = top + 18 + index * 14
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        output.append(
            f'<line x1="{legend_x}" y1="{_svg_float(legend_y)}" '
            f'x2="{legend_x + 22}" y2="{_svg_float(legend_y)}" '
            f'stroke="{color}" stroke-width="2"{dash}/>'
        )
        output.append(
            f'<text x="{legend_x + 28}" y="{_svg_float(legend_y + 3)}" '
            f'font-size="10" fill="#333">{escape(label)}</text>'
        )
    annotation_y = top + height - 8
    for annotation in annotations:
        output.append(
            f'<text x="{_PLOT_LEFT + width - 8}" '
            f'y="{_svg_float(annotation_y)}" font-size="9" '
            f'text-anchor="end" fill="#8a4b00">{escape(annotation)}</text>'
        )
        annotation_y -= 12
    return output


def render_physical_state_svg(
    capture: Capture,
    admission: AdmissionResult,
    session: SessionSamplingSummary,
    *,
    config: QAConfig = DEFAULT_QA_CONFIG,
) -> str:
    """One aligned, explicitly labeled time-domain panel set per boot session."""
    rows = [row for row in capture.rows if _session_key(row) == session.session_id]
    if not rows:
        raise ValueError(
            f"session {session.session_id!r} is not present in capture "
            f"{capture.source.path!r}; refusing to merge rows from another "
            "session into one trajectory"
        )
    times, domain_status, detail = _trusted_times(capture, rows)
    if times is None:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="120">'
            '<rect width="100%" height="100%" fill="#fff"/>'
            f'<text x="20" y="40" font-size="13" fill="#b00020">'
            f'TIME_BASE_UNTRUSTED: {escape(detail)}</text></svg>'
        )
    if domain_status == TIME_BASE_TRUSTED_UPTIME:
        domain_label = "device uptime within one boot (s)"
    elif domain_status == TIME_BASE_TRUSTED_EVENT_UTC:
        domain_label = "event UTC within one boot, sync evidenced (s)"
    else:
        domain_label = "event UTC within one boot, sync unverified (s)"
    segment_boundaries = tuple(
        segment.start_s
        for segment in session.run_segments[1:]
        if segment.start_s is not None
    )
    time_start, time_end = _time_scale(times)
    invalid_flags = [
        row.overall_quality == "INVALID" for row in rows
    ]
    long_gap_s = config.long_gap_ms / 1000.0
    panels = 5
    total_height = (
        _PLOT_TOP
        + panels * _PLOT_PANEL_HEIGHT
        + (panels - 1) * _PLOT_PANEL_GAP
        + _PLOT_BOTTOM
    )
    output = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_PLOT_WIDTH}" '
        f'height="{total_height}" viewBox="0 0 {_PLOT_WIDTH} {total_height}">',
        f'<rect width="{_PLOT_WIDTH}" height="{total_height}" fill="#ffffff"/>',
        f'<text x="{_PLOT_LEFT}" y="24" font-size="15" font-weight="700" '
        f'fill="#111">ColdGuard W05 physical-state diagnostics — '
        f'{escape(capture.source.path)}</text>',
        f'<text x="{_PLOT_LEFT}" y="38" font-size="10" fill="#555">'
        f'boot {escape(session.boot_id)} · {escape(domain_label)} · '
        f'physical admission {escape(admission.status.value)} · '
        f'source SHA-256 {escape(capture.source.sha256[:16])}…</text>',
    ]
    if len(session.run_segments) > 1:
        segments_text = "; ".join(
            f"{segment.run_id or 'NOT_CARRIED'} rows={segment.row_count} "
            f"{segment.start_s:.2f}–{segment.end_s:.2f}s"
            if segment.start_s is not None and segment.end_s is not None
            else f"{segment.run_id or 'NOT_CARRIED'} rows={segment.row_count} time=NOT_ESTIMABLE"
            for segment in session.run_segments
        )
        output.append(
            f'<text x="{_PLOT_LEFT}" y="52" font-size="9" fill="#8a4b00">'
            "source run_id segments (one boot; NOT independent): "
            f"{escape(segments_text)}</text>"
        )
    top = _PLOT_TOP
    width = _PLOT_WIDTH - _PLOT_LEFT - _PLOT_RIGHT
    output.extend(
        _render_panel(
            title="Panel 1 — Chamber-air temperature (role-qualified slots)",
            unit="degC · role-qualified chamber-air channels only; TEC hot side excluded",
            series=[
                (
                    f"{slot} ({capture.sensor(slot).physical_position or 'UNKNOWN'})",
                    _PANEL_COLORS[index % len(_PANEL_COLORS)],
                    [_extract_value(capture, row, slot) for row in rows],
                    False,
                )
                for index, slot in enumerate(capture.chamber_air_slots)
            ],
            times=times,
            top=top,
            time_start=time_start,
            time_end=time_end,
            long_gap_s=long_gap_s,
            invalid_flags=invalid_flags,
            segment_boundaries=segment_boundaries,
            annotations=(
                ["no role-qualified chamber-air channel"]
                if not capture.chamber_air_slots
                else []
            ),
        )
    )
    top += _PLOT_PANEL_HEIGHT + _PLOT_PANEL_GAP
    output.extend(
        _render_panel(
            title="Panel 2 — TEC hot-side temperature (separate physical role)",
            unit="degC · never included in chamber-air mean or gradient",
            series=[
                (
                    f"{slot} ({capture.sensor(slot).physical_position})",
                    _PANEL_COLORS[1],
                    [_extract_value(capture, row, slot) for row in rows],
                    False,
                )
                for slot in capture.hot_side_slots
            ],
            times=times,
            top=top,
            time_start=time_start,
            time_end=time_end,
            long_gap_s=long_gap_s,
            invalid_flags=invalid_flags,
            segment_boundaries=segment_boundaries,
            annotations=(
                ["no role-qualified hot-side channel"]
                if not capture.hot_side_slots
                else []
            ),
        )
    )
    top += _PLOT_PANEL_HEIGHT + _PLOT_PANEL_GAP
    door_values = [
        {"CLOSED": 0.0, "OPEN": 1.0}.get(row.door_state)
        for row in rows
    ]
    door_unknown = [row.door_state == "UNKNOWN" for row in rows]
    output.extend(
        _render_panel(
            title="Panel 3 — Door state (UNKNOWN retained)",
            unit="0 = CLOSED, 1 = OPEN; UNKNOWN is hatched and never converted",
            series=[("door state", _PANEL_COLORS[3], door_values, False)],
            times=times,
            top=top,
            time_start=time_start,
            time_end=time_end,
            long_gap_s=long_gap_s,
            invalid_flags=invalid_flags,
            segment_boundaries=segment_boundaries,
            annotations=(
                [
                    "UNKNOWN rows: "
                    f"{sum(1 for flag in door_unknown if flag)}"
                ]
                if any(door_unknown)
                else []
            ),
            y_bounds=(-0.1, 1.1),
        )
    )
    for index, (start_s, end_s) in enumerate(_invalid_ranges(times, door_unknown)):
        x1 = _PLOT_LEFT + (
            (start_s - time_start) / max(time_end - time_start, 1e-9) * width
        )
        x2 = _PLOT_LEFT + (
            (end_s - time_start) / max(time_end - time_start, 1e-9) * width
        )
        output.append(
            f'<rect x="{_svg_float(x1)}" y="{_svg_float(top)}" '
            f'width="{_svg_float(max(x2 - x1, 1.0))}" '
            f'height="{_PLOT_PANEL_HEIGHT}" fill="url(#unknownHatch)" '
            'stroke="none"/>'
        )
    top += _PLOT_PANEL_HEIGHT + _PLOT_PANEL_GAP
    duty_series: list[tuple[str, str, Sequence[Any], bool]] = []
    if any(row.requested_duty_permille is not None for row in rows):
        duty_series.append(
            (
                "requested",
                _PANEL_COLORS[0],
                [row.requested_duty_permille for row in rows],
                True,
            )
        )
    if any(row.applied_duty_permille is not None for row in rows):
        duty_series.append(
            (
                "applied",
                _PANEL_COLORS[2],
                [row.applied_duty_permille for row in rows],
                False,
            )
        )
    if any(row.readback_duty_permille is not None for row in rows):
        duty_series.append(
            (
                "readback",
                _PANEL_COLORS[4],
                [row.readback_duty_permille for row in rows],
                True,
            )
        )
    if not duty_series and any(row.applied_cooling is not None for row in rows):
        duty_series.append(
            (
                "applied state (ON=1, OFF=0)",
                _PANEL_COLORS[2],
                [
                    1.0 if row.applied_cooling == "ON" else 0.0
                    if row.applied_cooling == "OFF"
                    else None
                    for row in rows
                ],
                False,
            )
        )
    output.extend(
        _render_panel(
            title="Panel 4 — Cooling duty: requested / applied / readback",
            unit="permille · applied is not the same evidence as requested or readback",
            series=duty_series,
            times=times,
            top=top,
            time_start=time_start,
            time_end=time_end,
            long_gap_s=long_gap_s,
            invalid_flags=invalid_flags,
            segment_boundaries=segment_boundaries,
            y_bounds=(
                (-0.1, 1.1)
                if duty_series
                and duty_series[0][0].startswith("applied state")
                else None
            ),
            annotations=(
                ["no cooling duty/state channel carried"] if not duty_series else []
            ),
        )
    )
    top += _PLOT_PANEL_HEIGHT + _PLOT_PANEL_GAP
    power_rows = [row for row in rows if row.cooling_power_w is not None]
    electrical_qualified = (
        bool(power_rows)
        and len(power_rows) == len(rows)
        and all(dict(row.quality).get("electrical") == "VALID" for row in rows)
        and all(
            PZEM_POWER_MIN_W <= row.cooling_power_w <= PZEM_POWER_MAX_W
            for row in power_rows
        )
    )
    power_series: list[tuple[str, str, Sequence[Any], bool]] = (
        [
            (
                "cooling-branch power",
                _PANEL_COLORS[1],
                [row.cooling_power_w for row in rows],
                not electrical_qualified,
            )
        ]
        if power_rows
        else []
    )
    output.extend(
        _render_panel(
            title="Panel 5 — PZEM cooling-branch power",
            unit="W · one cooling branch; not whole-system power",
            series=power_series,
            times=times,
            top=top,
            time_start=time_start,
            time_end=time_end,
            long_gap_s=long_gap_s,
            invalid_flags=invalid_flags,
            segment_boundaries=segment_boundaries,
            x_ticks=True,
            annotations=(
                ["no PZEM power channel carried"]
                if not power_series
                else (
                    [
                        "UNQUALIFIED PZEM VALUES — diagnostic only; "
                        "no validated power/energy claim"
                    ]
                    if not electrical_qualified
                    else []
                )
            ),
        )
    )
    output.append(
        f'<text x="{_PLOT_LEFT}" y="{total_height - 12}" font-size="9" '
        'fill="#666">Gaps are not connected; missing values are not zero; '
        'shaded regions mark source rows whose overall snapshot quality is '
        'INVALID. Diagnostic plot, not Controller-B efficacy evidence.</text>'
    )
    output.append(
        '<defs><pattern id="unknownHatch" width="6" height="6" '
        'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<line x1="0" y1="0" x2="0" y2="6" stroke="#b58900" '
        'stroke-width="1"/></pattern></defs>'
    )
    output.append("</svg>")
    return "\n".join(output)
