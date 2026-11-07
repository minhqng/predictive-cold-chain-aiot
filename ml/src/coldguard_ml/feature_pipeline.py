"""W10 past-only feature pipeline (B-W10-02 / B-W10-03).

Every feature is computed from information observed at or before the anchor
``t``. Rolling lookbacks use actual event time, never sample counts or arrival
time. Feature computation never consumes labels or future critical-event
information; the development label pilot lives in ``label_pilot.py``.

Two provenance-preserving adapters feed the pipeline:

* W02 ``Observation`` rows (legitimately timestamped synthetic fixtures);
* W04 ``Capture``/``NormalizedRow`` rows (boot-scoped real diagnostics).

Neither adapter invents an absolute time for a boot-scoped source, and neither
promotes an unresolved run identity into a physical dataset.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    METHOD_ACTUATION_DUTY,
    METHOD_ACTUATION_SINCE_CHANGE,
    METHOD_ACTUATION_STATE,
    METHOD_DOOR_COUNT,
    METHOD_DOOR_DURATION,
    METHOD_DOOR_OPEN,
    METHOD_DOOR_TIME_SINCE_OPEN,
    METHOD_ELECTRICAL_CHANNEL,
    METHOD_ENVIRONMENT_CHANNEL,
    METHOD_INSTANTANEOUS_AGGREGATE,
    METHOD_INSTANTANEOUS_PROBE,
    METHOD_INTEGRATED_POWER,
    METHOD_ROLLING_THERMAL,
)

TIME_DOMAIN_ABSOLUTE_UTC = "UTC_ABSOLUTE"
TIME_DOMAIN_BOOT_SCOPED = "BOOT_SCOPED_UPTIME"

SOURCE_TYPE_SYNTHETIC = "SYNTHETIC_FIXTURE"
SOURCE_TYPE_REAL_A = "REAL_A_CAPTURE"

OUTPUT_SYNTHETIC = "SYNTHETIC_FEATURE_TEST"
OUTPUT_DIAGNOSTIC = "DIAGNOSTIC_PHYSICAL_FEATURE_VIEW"
OUTPUT_ELIGIBLE = "ELIGIBLE_DEVELOPMENT_FEATURE_SET"
OUTPUT_REJECTED = "REJECTED_OR_NOT_EVALUABLE"

ELIGIBILITY_ELIGIBLE = "ELIGIBLE"
ELIGIBILITY_BLOCKED = "BLOCKED"
ELIGIBILITY_SYNTHETIC = "SYNTHETIC_ONLY"

PRESENT = "PRESENT"
MISSING_INSUFFICIENT_HISTORY = "MISSING_INSUFFICIENT_HISTORY"
MISSING_INSUFFICIENT_SAMPLES = "MISSING_INSUFFICIENT_SAMPLES"
MISSING_QUALITY = "MISSING_QUALITY"
MISSING_INPUT = "MISSING_INPUT"
MISSING_GAP = "MISSING_GAP"
MISSING_UNKNOWN_DOOR = "MISSING_UNKNOWN_DOOR"
MISSING_POLARITY_UNATTESTED = "MISSING_POLARITY_UNATTESTED"
MISSING_NO_OBSERVED_TRANSITION = "MISSING_NO_OBSERVED_TRANSITION"
MISSING_ELECTRICAL_UNQUALIFIED = "MISSING_ELECTRICAL_UNQUALIFIED"
MISSING_ENVIRONMENT_UNQUALIFIED = "MISSING_ENVIRONMENT_UNQUALIFIED"
MISSING_COUNTER_RESET = "MISSING_COUNTER_RESET"

DOOR_OPEN = "OPEN"
DOOR_CLOSED = "CLOSED"

EXCLUSION_RUN_IDENTITY_UNRESOLVED = "RUN_IDENTITY_UNRESOLVED"
EXCLUSION_ABSOLUTE_TIME_UNAVAILABLE = "ABSOLUTE_TIME_NOT_EVIDENCED"
EXCLUSION_A_LEDGER_INVALID = "AUTHORITY_A_LEDGER_INVALID"
EXCLUSION_ELECTRICAL_UNQUALIFIED = "ELECTRICAL_UNQUALIFIED"
EXCLUSION_DOOR_UNATTESTED = "DOOR_POLARITY_OR_QUALITY_UNATTESTED"
EXCLUSION_NO_S2_EVIDENCE = "NO_ELIGIBLE_S2_DISTURBANCE"


class FeaturePipelineError(ValueError):
    """A feature row would fabricate a value, a lineage link or a time domain."""


@dataclass(frozen=True)
class PipelineSample:
    device_id: str | None
    boot_id: str
    seq: int
    time_s: float
    chamber_c: tuple[tuple[str, float | None], ...]
    hot_side_c: float | None
    thermal_quality: str
    door_state: str
    door_quality: str
    door_polarity_attested: bool
    applied_cooling: str | None
    applied_duty: float | None
    requested_duty_permille: int | None
    readback_duty_permille: int | None
    cooling_voltage_v: float | None
    cooling_current_a: float | None
    cooling_power_w: float | None
    cooling_energy_counter_wh: float | None
    electrical_quality: str
    t_air_c: float | None
    rh_pct: float | None
    environment_quality: str
    overall_quality: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.time_s):
            raise FeaturePipelineError("sample time must be finite")
        if not self.boot_id.strip():
            raise FeaturePipelineError("sample boot identity is required")

    @property
    def identity(self) -> str:
        return f"{self.device_id or 'UNKNOWN'}:{self.boot_id}:{self.seq}"

    def probe(self, role: str) -> float | None:
        for name, value in self.chamber_c:
            if name == role:
                return value
        return None

    def payload(self) -> tuple[Any, ...]:
        return (
            self.time_s,
            tuple(sorted(self.chamber_c)),
            self.hot_side_c,
            self.thermal_quality,
            self.door_state,
            self.door_quality,
            self.door_polarity_attested,
            self.applied_cooling,
            self.applied_duty,
            self.requested_duty_permille,
            self.readback_duty_permille,
            self.cooling_voltage_v,
            self.cooling_current_a,
            self.cooling_power_w,
            self.cooling_energy_counter_wh,
            self.electrical_quality,
            self.t_air_c,
            self.rh_pct,
            self.environment_quality,
            self.overall_quality,
        )


@dataclass(frozen=True)
class Trajectory:
    run_id: str | None
    boot_id: str
    device_id: str | None
    scenario_id: str | None
    controller_id: str | None
    source_sha256: str
    source_type: str
    clock_domain: str
    origin_utc: str | None
    physical_source_key: str
    samples: tuple[PipelineSample, ...]
    physical_eligibility: str
    exclusion_reasons: tuple[str, ...]
    source_run_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.boot_id.strip():
            raise FeaturePipelineError("trajectory boot identity is required")
        if not self.source_sha256.strip():
            raise FeaturePipelineError("trajectory source hash is required")
        if self.physical_eligibility == ELIGIBILITY_ELIGIBLE and self.run_id is None:
            raise FeaturePipelineError(
                "an eligible physical trajectory requires a resolved run identity"
            )
        previous = None
        identities: set[str] = set()
        for sample in self.samples:
            if sample.identity in identities:
                raise FeaturePipelineError(
                    f"duplicate sample identity {sample.identity!r} after adapter dedup"
                )
            identities.add(sample.identity)
            if previous is not None and sample.time_s < previous:
                raise FeaturePipelineError(
                    "trajectory samples are not non-decreasing in event time"
                )
            previous = sample.time_s


@dataclass(frozen=True)
class FeatureRow:
    feature_schema_version: str
    registry_sha256: str
    source_sha256: str
    source_type: str
    run_id: str | None
    device_id: str | None
    boot_id: str
    scenario_id: str | None
    controller_id: str | None
    physical_source_key: str
    sample_identity: str
    anchor_t_s: float
    anchor_time_utc: str | None
    time_domain: str
    split_partition: str | None
    values: tuple[float | int | None, ...]
    missing_reasons: tuple[str, ...]
    input_interval_start_s: float
    input_interval_end_s: float
    source_quality: tuple[tuple[str, str], ...]
    physical_eligibility: str
    exclusion_reasons: tuple[str, ...]
    output_class: str

    def to_dict(self, feature_ids: Sequence[str]) -> dict[str, Any]:
        return {
            "feature_schema_version": self.feature_schema_version,
            "registry_sha256": self.registry_sha256,
            "source_sha256": self.source_sha256,
            "source_type": self.source_type,
            "run_id": self.run_id,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "scenario_id": self.scenario_id,
            "controller_id": self.controller_id,
            "physical_source_key": self.physical_source_key,
            "sample_identity": self.sample_identity,
            "prediction_anchor_t_s": self.anchor_t_s,
            "prediction_anchor_utc": self.anchor_time_utc,
            "time_domain": self.time_domain,
            "split_partition": self.split_partition,
            "features": {
                feature_id: value
                for feature_id, value in zip(feature_ids, self.values)
            },
            "missing_reasons": {
                feature_id: reason
                for feature_id, reason in zip(feature_ids, self.missing_reasons)
            },
            "input_interval": [self.input_interval_start_s, self.input_interval_end_s],
            "source_quality": dict(self.source_quality),
            "physical_eligibility": self.physical_eligibility,
            "exclusion_reasons": list(self.exclusion_reasons),
            "output_class": self.output_class,
        }


@dataclass(frozen=True)
class DoorSnapshot:
    trusted_state: str | None
    untrusted_reason: str | None
    opening_times: tuple[float, ...]
    last_opening_s: float | None
    current_interval_start_s: float | None


def _is_trusted_door(sample: PipelineSample) -> tuple[str | None, str | None]:
    if sample.door_state not in (DOOR_OPEN, DOOR_CLOSED):
        return None, MISSING_UNKNOWN_DOOR
    if sample.door_quality != "VALID":
        return None, MISSING_QUALITY
    if not sample.door_polarity_attested:
        return None, MISSING_POLARITY_UNATTESTED
    return sample.door_state, None


def door_snapshots(samples: Sequence[PipelineSample]) -> tuple[DoorSnapshot, ...]:
    """Causal door state machine: no edge from UNKNOWN, no cross-boot carry."""
    snapshots: list[DoorSnapshot] = []
    openings: list[float] = []
    interval_start: float | None = None
    previous_state: str | None = None
    previous_trusted = False
    for sample in samples:
        state, reason = _is_trusted_door(sample)
        if state is not None:
            if previous_trusted and previous_state == DOOR_CLOSED and state == DOOR_OPEN:
                openings.append(sample.time_s)
                interval_start = sample.time_s
            elif state == DOOR_CLOSED:
                interval_start = None
            previous_state = state
            previous_trusted = True
        else:
            interval_start = None
            previous_state = None
            previous_trusted = False
        snapshots.append(
            DoorSnapshot(
                trusted_state=state,
                untrusted_reason=reason,
                opening_times=tuple(openings),
                last_opening_s=openings[-1] if openings else None,
                current_interval_start_s=interval_start,
            )
        )
    return tuple(snapshots)


def _chamber_roles(registry: FeatureRegistry) -> tuple[str, ...]:
    return tuple(registry.role_map["chamber_air_roles"])


def _instantaneous_mean(sample: PipelineSample, roles: Sequence[str]) -> tuple[float | None, str]:
    if sample.thermal_quality != "VALID":
        return None, MISSING_QUALITY
    values = [sample.probe(role) for role in roles]
    if any(value is None for value in values):
        return None, MISSING_INPUT
    return sum(values) / len(values), PRESENT


def _instantaneous_spread(sample: PipelineSample, roles: Sequence[str]) -> tuple[float | None, str]:
    if sample.thermal_quality != "VALID":
        return None, MISSING_QUALITY
    values = [sample.probe(role) for role in roles]
    if any(value is None for value in values):
        return None, MISSING_INPUT
    return max(values) - min(values), PRESENT


def _probe(sample: PipelineSample, role: str) -> tuple[float | None, str]:
    if sample.thermal_quality != "VALID":
        return None, MISSING_QUALITY
    if role == "TEC_HOT_SIDE":
        return (
            (sample.hot_side_c, PRESENT)
            if sample.hot_side_c is not None
            else (None, MISSING_INPUT)
        )
    value = sample.probe(role)
    return (value, PRESENT) if value is not None else (None, MISSING_INPUT)


def _aggregate(
    sample: PipelineSample, statistic: str, roles: Sequence[str]
) -> tuple[float | None, str]:
    if sample.thermal_quality != "VALID":
        return None, MISSING_QUALITY
    values = [sample.probe(role) for role in roles]
    if any(value is None for value in values):
        return None, MISSING_INPUT
    if statistic == "max":
        return max(values), PRESENT
    if statistic == "min":
        return min(values), PRESENT
    if statistic == "mean":
        return sum(values) / len(values), PRESENT
    if statistic == "spread":
        return max(values) - min(values), PRESENT
    raise FeaturePipelineError(f"unknown aggregate statistic {statistic!r}")


def _rolling_series(
    samples: Sequence[PipelineSample],
    index: int,
    config: FeatureDefinition,
    value_fn,
) -> tuple[list[tuple[float, float]], float, str | None]:
    anchor = samples[index]
    window_start = anchor.time_s - float(config.lookback_s)
    history = samples[: index + 1]
    if not any(sample.time_s <= window_start for sample in history):
        return [], window_start, MISSING_INSUFFICIENT_HISTORY
    if config.max_gap_s is not None:
        for previous, current in zip(history, history[1:]):
            if (
                current.time_s > window_start
                and current.time_s - previous.time_s > config.max_gap_s
            ):
                return [], window_start, MISSING_GAP
    contributing: list[tuple[float, float]] = []
    for sample in history:
        if sample.time_s <= window_start:
            continue
        value, reason = value_fn(sample)
        if value is None:
            return [], window_start, reason
        contributing.append((sample.time_s, value))
    if not contributing:
        return [], window_start, MISSING_INSUFFICIENT_HISTORY
    return contributing, window_start, None


def _weighted(
    contributing: Sequence[tuple[float, float]], window_start: float
) -> list[tuple[float, float]]:
    weighted: list[tuple[float, float]] = []
    previous = window_start
    for time_s, value in contributing:
        weight = time_s - previous
        if weight < 0:
            raise FeaturePipelineError("negative rolling weight")
        weighted.append((weight, value))
        previous = time_s
    return weighted


def _rolling_stat(
    samples: Sequence[PipelineSample],
    index: int,
    config: FeatureDefinition,
    roles: Sequence[str],
) -> tuple[float | None, str]:
    statistic = str(config.method_params["statistic"])
    value_fn = (
        (lambda sample: _instantaneous_spread(sample, roles))
        if statistic == "time_weighted_spread"
        else (lambda sample: _instantaneous_mean(sample, roles))
    )
    contributing, window_start, failure = _rolling_series(
        samples, index, config, value_fn
    )
    if failure is not None:
        return None, failure
    weighted = _weighted(contributing, window_start)
    total = sum(weight for weight, _ in weighted)
    if total <= 0:
        return None, MISSING_INSUFFICIENT_HISTORY
    if statistic == "min":
        return min(value for _, value in contributing), PRESENT
    if statistic == "max":
        return max(value for _, value in contributing), PRESENT
    if statistic == "delta":
        return contributing[-1][1] - contributing[0][1], PRESENT
    mean = sum(weight * value for weight, value in weighted) / total
    if statistic in ("time_weighted_mean", "time_weighted_spread"):
        return mean, PRESENT
    if statistic == "time_weighted_std":
        variance = (
            sum(weight * (value - mean) ** 2 for weight, value in weighted) / total
        )
        return math.sqrt(variance), PRESENT
    if statistic == "least_squares_slope":
        if len(contributing) < 3:
            return None, MISSING_INSUFFICIENT_SAMPLES
        times = [item[0] for item in contributing]
        values = [item[1] for item in contributing]
        mean_t = sum(times) / len(times)
        mean_v = sum(values) / len(values)
        denominator = sum((value - mean_t) ** 2 for value in times)
        if denominator == 0:
            return None, MISSING_INSUFFICIENT_SAMPLES
        numerator = sum(
            (time_s - mean_t) * (value - mean_v)
            for time_s, value in contributing
        )
        return numerator / denominator * 60.0, PRESENT
    raise FeaturePipelineError(f"unknown rolling statistic {statistic!r}")


def _electrical(
    samples: Sequence[PipelineSample], index: int, field: str
) -> tuple[float | None, str]:
    sample = samples[index]
    if sample.electrical_quality != "VALID":
        return None, MISSING_ELECTRICAL_UNQUALIFIED
    value = {
        "voltage_v": sample.cooling_voltage_v,
        "current_a": sample.cooling_current_a,
        "power_w": sample.cooling_power_w,
        "counter_wh": sample.cooling_energy_counter_wh,
    }[field]
    if value is None:
        return None, MISSING_INPUT
    if field == "counter_wh":
        last = None
        for previous in samples[: index + 1]:
            if (
                previous.electrical_quality != "VALID"
                or previous.cooling_energy_counter_wh is None
            ):
                continue
            if last is not None and previous.cooling_energy_counter_wh < last:
                return None, MISSING_COUNTER_RESET
            last = previous.cooling_energy_counter_wh
    return value, PRESENT


def _integrated_power(
    samples: Sequence[PipelineSample], index: int, config: FeatureDefinition
) -> tuple[float | None, str]:
    history = samples[: index + 1]
    first_valid = None
    for position, sample in enumerate(history):
        if sample.electrical_quality == "VALID" and sample.cooling_power_w is not None:
            first_valid = position
            break
    if first_valid is None:
        return None, MISSING_ELECTRICAL_UNQUALIFIED
    segment = history[first_valid:]
    if any(
        sample.electrical_quality != "VALID" or sample.cooling_power_w is None
        for sample in segment
    ):
        return None, MISSING_ELECTRICAL_UNQUALIFIED
    if len(segment) < 2:
        return None, MISSING_INSUFFICIENT_HISTORY
    max_gap = config.max_gap_s or 0.0
    total = 0.0
    for previous, current in zip(segment, segment[1:]):
        if current.time_s - previous.time_s > max_gap:
            return None, MISSING_GAP
        total += (previous.cooling_power_w or 0.0) * (
            current.time_s - previous.time_s
        ) / 3600.0
    return total, PRESENT


def _actuation_state(sample: PipelineSample, channel: str) -> tuple[float | None, str]:
    if channel == "requested":
        raw = sample.requested_duty_permille
    elif channel == "readback":
        raw = sample.readback_duty_permille
    else:
        raw = sample.applied_cooling
    if raw is None:
        return None, MISSING_INPUT
    if channel == "applied":
        if raw not in ("ON", "OFF"):
            return None, MISSING_INPUT
        return (1.0 if raw == "ON" else 0.0), PRESENT
    return (1.0 if raw > 0 else 0.0), PRESENT


def _applied_change_time(
    samples: Sequence[PipelineSample], index: int
) -> tuple[float | None, str]:
    last_change: float | None = None
    previous: tuple[str, float | None] | None = None
    for sample in samples[: index + 1]:
        if sample.applied_cooling is None:
            previous = None
            continue
        current = (sample.applied_cooling, sample.applied_duty)
        if previous is not None:
            state_changed = current[0] != previous[0]
            duty_changed = (
                current[1] is not None
                and previous[1] is not None
                and current[1] != previous[1]
            )
            if state_changed or duty_changed:
                last_change = sample.time_s
        previous = current
    if last_change is None:
        return None, MISSING_NO_OBSERVED_TRANSITION
    return samples[index].time_s - last_change, PRESENT


def _environment(sample: PipelineSample, field: str) -> tuple[float | None, str]:
    if sample.environment_quality != "VALID":
        return None, MISSING_ENVIRONMENT_UNQUALIFIED
    value = sample.t_air_c if field == "t_air_c" else sample.rh_pct
    return (value, PRESENT) if value is not None else (None, MISSING_INPUT)


def _compute_one(
    feature: FeatureDefinition,
    samples: Sequence[PipelineSample],
    index: int,
    snapshots: Sequence[DoorSnapshot],
    roles: Sequence[str],
) -> tuple[float | int | None, str]:
    sample = samples[index]
    snapshot = snapshots[index]
    method = feature.method
    if method == METHOD_INSTANTANEOUS_AGGREGATE:
        return _aggregate(sample, str(feature.method_params["statistic"]), roles)
    if method == METHOD_INSTANTANEOUS_PROBE:
        return _probe(sample, str(feature.method_params["role"]))
    if method == METHOD_ROLLING_THERMAL:
        return _rolling_stat(samples, index, feature, roles)
    if method == METHOD_DOOR_OPEN:
        if snapshot.trusted_state is None:
            return None, snapshot.untrusted_reason or MISSING_UNKNOWN_DOOR
        return (1.0 if snapshot.trusted_state == DOOR_OPEN else 0.0), PRESENT
    if method == METHOD_DOOR_TIME_SINCE_OPEN:
        if snapshot.last_opening_s is None:
            return None, MISSING_NO_OBSERVED_TRANSITION
        return sample.time_s - snapshot.last_opening_s, PRESENT
    if method == METHOD_DOOR_DURATION:
        if snapshot.trusted_state is None:
            return None, snapshot.untrusted_reason or MISSING_UNKNOWN_DOOR
        if snapshot.trusted_state == DOOR_CLOSED:
            return 0.0, PRESENT
        if snapshot.current_interval_start_s is None:
            return None, MISSING_NO_OBSERVED_TRANSITION
        return sample.time_s - snapshot.current_interval_start_s, PRESENT
    if method == METHOD_DOOR_COUNT:
        if snapshot.trusted_state is None and snapshot.last_opening_s is None:
            return None, snapshot.untrusted_reason or MISSING_UNKNOWN_DOOR
        lower = sample.time_s - 60.0
        count = sum(
            1 for time_s in snapshot.opening_times if lower < time_s <= sample.time_s
        )
        return count, PRESENT
    if method == METHOD_ACTUATION_STATE:
        return _actuation_state(sample, str(feature.method_params["channel"]))
    if method == METHOD_ACTUATION_DUTY:
        if sample.applied_duty is None:
            return None, MISSING_INPUT
        return sample.applied_duty, PRESENT
    if method == METHOD_ACTUATION_SINCE_CHANGE:
        if sample.applied_cooling is None or sample.applied_duty is None:
            return None, MISSING_INPUT
        return _applied_change_time(samples, index)
    if method == METHOD_ELECTRICAL_CHANNEL:
        return _electrical(samples, index, str(feature.method_params["field"]))
    if method == METHOD_INTEGRATED_POWER:
        return _integrated_power(samples, index, feature)
    if method == METHOD_ENVIRONMENT_CHANNEL:
        return _environment(sample, str(feature.method_params["field"]))
    raise FeaturePipelineError(f"unhandled feature method {method!r}")


def output_class_for(trajectory: Trajectory, partition: str | None) -> str:
    if trajectory.source_type == SOURCE_TYPE_SYNTHETIC:
        return OUTPUT_SYNTHETIC
    if trajectory.physical_eligibility != ELIGIBILITY_ELIGIBLE:
        return OUTPUT_DIAGNOSTIC
    if partition not in ("train", "validation"):
        return OUTPUT_REJECTED
    return OUTPUT_ELIGIBLE


def feature_rows(
    trajectory: Trajectory,
    registry: FeatureRegistry,
    *,
    partition: str | None = None,
    anchors: Sequence[float] | None = None,
    split: Any | None = None,
) -> tuple[FeatureRow, ...]:
    """Compute every registered feature at each past-only anchor.

    When ``split`` is supplied, the trajectory's run must belong to the
    declared partition; an eligible physical trajectory may not be processed
    without a grouped split at all.
    """
    if not trajectory.samples:
        return ()
    if partition not in (None, "train", "validation", "test"):
        raise FeaturePipelineError(f"unknown split partition {partition!r}")
    if split is not None:
        if partition is None or trajectory.run_id is None:
            raise FeaturePipelineError(
                "split-bound feature generation requires a run identity and partition"
            )
        actual = split.partition_of(trajectory.run_id)
        if actual != partition:
            raise FeaturePipelineError(
                f"run {trajectory.run_id!r} belongs to partition {actual!r}, "
                f"not the requested {partition!r}"
            )
    elif trajectory.physical_eligibility == ELIGIBILITY_ELIGIBLE:
        raise FeaturePipelineError(
            "eligible physical feature generation requires the grouped split"
        )
    roles = _chamber_roles(registry)
    snapshots = door_snapshots(trajectory.samples)
    times = [sample.time_s for sample in trajectory.samples]
    if anchors is None:
        indices = list(range(len(trajectory.samples)))
    else:
        indices = []
        for anchor in anchors:
            matches = [i for i, time_s in enumerate(times) if time_s == float(anchor)]
            if len(matches) != 1:
                raise FeaturePipelineError(
                    f"anchor {anchor!r} is ambiguous or unobserved in run "
                    f"{trajectory.run_id!r} boot {trajectory.boot_id!r}"
                )
            indices.append(matches[0])
    rows: list[FeatureRow] = []
    for index in indices:
        sample = trajectory.samples[index]
        values: list[float | int | None] = []
        reasons: list[str] = []
        for feature in registry.features:
            value, reason = _compute_one(
                feature, trajectory.samples, index, snapshots, roles
            )
            if feature.dtype == "int" and value is not None:
                value = int(value)
            values.append(value)
            reasons.append(reason)
        quality = (
            ("thermal", sample.thermal_quality),
            ("electrical", sample.electrical_quality),
            ("environment", sample.environment_quality),
            ("door", sample.door_quality),
            ("overall", sample.overall_quality),
        )
        rows.append(
            FeatureRow(
                feature_schema_version=registry.feature_version,
                registry_sha256=registry.schema_sha256,
                source_sha256=trajectory.source_sha256,
                source_type=trajectory.source_type,
                run_id=trajectory.run_id,
                device_id=trajectory.device_id,
                boot_id=trajectory.boot_id,
                scenario_id=trajectory.scenario_id,
                controller_id=trajectory.controller_id,
                physical_source_key=trajectory.physical_source_key,
                sample_identity=sample.identity,
                anchor_t_s=sample.time_s,
                anchor_time_utc=(
                    None
                    if trajectory.origin_utc is None
                    else _iso_offset(trajectory.origin_utc, sample.time_s)
                ),
                time_domain=trajectory.clock_domain,
                split_partition=partition,
                values=tuple(values),
                missing_reasons=tuple(reasons),
                input_interval_start_s=max(
                    0.0,
                    sample.time_s
                    - max(
                        (feature.lookback_s or 0.0) for feature in registry.features
                    ),
                ),
                input_interval_end_s=sample.time_s,
                source_quality=quality,
                physical_eligibility=trajectory.physical_eligibility,
                exclusion_reasons=trajectory.exclusion_reasons,
                output_class=output_class_for(trajectory, partition),
            )
        )
    return tuple(rows)


def _iso_offset(origin_utc: str, offset_s: float) -> str:
    import datetime as _dt

    moment = _dt.datetime.fromisoformat(origin_utc.replace("Z", "+00:00"))
    shifted = moment + _dt.timedelta(seconds=offset_s)
    return (
        shifted.astimezone(_dt.timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _dedupe_samples(samples: Iterable[PipelineSample]) -> tuple[PipelineSample, ...]:
    by_identity: dict[str, PipelineSample] = {}
    for sample in samples:
        existing = by_identity.get(sample.identity)
        if existing is None:
            by_identity[sample.identity] = sample
            continue
        if existing.payload() != sample.payload():
            raise FeaturePipelineError(
                f"contradictory duplicate sample identity {sample.identity!r}: "
                "input order cannot resolve the conflict"
            )
    return tuple(
        sample
        for _, sample in sorted(
            by_identity.items(), key=lambda item: (item[1].time_s, item[0])
        )
    )


def trajectory_from_observations(
    observations: Iterable[Any],
    *,
    source_sha256: str,
    source_type: str = SOURCE_TYPE_SYNTHETIC,
    clock_domain: str = TIME_DOMAIN_ABSOLUTE_UTC,
    physical_eligibility: str = ELIGIBILITY_SYNTHETIC,
    exclusion_reasons: Sequence[str] = (),
    scenario_id: str | None = None,
    controller_id: str = "CONTROLLER-A",
    synthetic_roles: Mapping[str, str] | None = None,
) -> tuple[Trajectory, ...]:
    """Adapt W02 ``Observation`` rows into one trajectory per run/boot.

    The synthetic role map is declared by the caller. W02 rows carry three
    probe slots and no near-door slot, so aggregate chamber features stay
    missing unless the fixture declares all three chamber roles; a slot that
    W02 does not carry is refused rather than guessed.
    """
    from .observations import canonical_order

    ordered = canonical_order(observations)
    role_map = dict(synthetic_roles or {})
    unsupported = set(role_map) - {"t1", "t2", "t3"}
    if unsupported:
        raise FeaturePipelineError(
            f"W02 observations do not carry slots {sorted(unsupported)}"
        )
    allowed_roles = {"CHAMBER_CENTER", "CHAMBER_BOTTOM", "CHAMBER_NEAR_DOOR"}
    if any(role not in allowed_roles for role in role_map.values()):
        raise FeaturePipelineError(
            f"synthetic chamber role map must use {sorted(allowed_roles)}"
        )
    grouped: dict[tuple[str, str], list[Any]] = {}
    for row in ordered:
        if row.run_id is None:
            raise FeaturePipelineError(
                "W02 observations without a run association cannot form a trajectory"
            )
        grouped.setdefault((row.run_id, row.boot_id), []).append(row)
    trajectories: list[Trajectory] = []
    for run_id, boot_id in sorted(grouped):
        rows = grouped[(run_id, boot_id)]
        origin = rows[0].time.isoformat(timespec="microseconds").replace("+00:00", "Z")
        samples = []
        for row in rows:
            chamber = []
            for slot, role in role_map.items():
                value = getattr(row, f"{slot}_c", None)
                if value is not None:
                    chamber.append((role, value))
            samples.append(
                PipelineSample(
                    device_id=row.device_id,
                    boot_id=row.boot_id,
                    seq=row.seq,
                    time_s=(row.time - rows[0].time).total_seconds(),
                    chamber_c=tuple(sorted(chamber)),
                    hot_side_c=None,
                    thermal_quality=row.thermal_quality,
                    door_state=row.door_state,
                    door_quality=(
                        "VALID"
                        if row.door_state in (DOOR_OPEN, DOOR_CLOSED)
                        else "UNKNOWN"
                    ),
                    door_polarity_attested=True,
                    applied_cooling=row.applied_cooling,
                    applied_duty=row.applied_duty,
                    requested_duty_permille=None,
                    readback_duty_permille=None,
                    cooling_voltage_v=row.cooling_voltage_v,
                    cooling_current_a=row.cooling_current_a,
                    cooling_power_w=row.cooling_power_w,
                    cooling_energy_counter_wh=row.cooling_energy_counter_wh,
                    electrical_quality=row.electrical_quality,
                    t_air_c=row.t_air_c,
                    rh_pct=row.rh_pct,
                    environment_quality=row.environment_quality,
                    overall_quality=row.overall_quality,
                )
            )
        trajectories.append(
            Trajectory(
                run_id=run_id,
                boot_id=boot_id,
                device_id=rows[0].device_id,
                scenario_id=scenario_id,
                controller_id=controller_id,
                source_sha256=source_sha256,
                source_type=source_type,
                clock_domain=clock_domain,
                origin_utc=origin,
                physical_source_key=f"{source_sha256}:{boot_id}",
                samples=_dedupe_samples(samples),
                physical_eligibility=physical_eligibility,
                exclusion_reasons=tuple(exclusion_reasons),
            )
        )
    return tuple(trajectories)


def trajectory_from_capture(
    capture: Any,
    *,
    clock_domain: str | None = None,
    physical_eligibility: str = ELIGIBILITY_BLOCKED,
    exclusion_reasons: Sequence[str] = (),
) -> tuple[Trajectory, ...]:
    """Adapt a W04 ``Capture`` without fabricating absolute device time."""
    from .plant_eda import build_representations

    source = capture.source
    domain = clock_domain or capture.time.domain
    representation = build_representations(capture)["tmean_airroles_v0"]
    role_by_slot = {
        slot: capture.sensor(slot).physical_position
        for slot in representation.slots
        if capture.sensor(slot).physical_position is not None
    }
    hot_slots = {
        role.slot: role.physical_position
        for role in capture.sensors
        if role.in_chamber_air_aggregate is False
        and role.physical_position is not None
    }
    grouped: dict[str, list[Any]] = {}
    for row in capture.rows:
        grouped.setdefault(row.boot_id, []).append(row)
    trajectories: list[Trajectory] = []
    for boot_id in sorted(grouped):
        rows = sorted(grouped[boot_id], key=lambda row: (row.device_ms or 0, row.seq))
        samples = []
        for row in rows:
            if row.device_ms is None:
                raise FeaturePipelineError(
                    f"boot {boot_id!r} carries a row without a boot-scoped time"
                )
            chamber = []
            for slot, role in role_by_slot.items():
                try:
                    value = row.probe(slot).value_c
                except KeyError:
                    value = None
                if value is not None:
                    chamber.append((role, value))
            hot = None
            for slot in hot_slots:
                try:
                    value = row.probe(slot).value_c
                except KeyError:
                    value = None
                if value is not None:
                    hot = value
                    break
            quality = dict(row.quality)
            samples.append(
                PipelineSample(
                    device_id=row.device_id,
                    boot_id=row.boot_id,
                    seq=row.seq,
                    time_s=row.device_ms / 1000.0,
                    chamber_c=tuple(sorted(chamber)),
                    hot_side_c=hot,
                    thermal_quality=quality.get("thermal", "UNKNOWN"),
                    door_state=row.door_state,
                    door_quality=quality.get("door", "UNKNOWN"),
                    door_polarity_attested=row.door_polarity == "CONFIRMED",
                    applied_cooling=row.applied_cooling,
                    applied_duty=row.applied_duty,
                    requested_duty_permille=row.requested_duty_permille,
                    readback_duty_permille=row.readback_duty_permille,
                    cooling_voltage_v=row.cooling_voltage_v,
                    cooling_current_a=row.cooling_current_a,
                    cooling_power_w=row.cooling_power_w,
                    cooling_energy_counter_wh=row.cooling_energy_counter_wh,
                    electrical_quality=quality.get("electrical", "UNKNOWN"),
                    t_air_c=row.t_air_c,
                    rh_pct=row.rh_pct,
                    environment_quality=quality.get("environment", "UNKNOWN"),
                    overall_quality=row.overall_quality or "UNKNOWN",
                )
            )
        trajectories.append(
            Trajectory(
                run_id=capture.run.run_id,
                boot_id=boot_id,
                device_id=capture.run.device_id,
                scenario_id=capture.run.scenario_id,
                controller_id=None,
                source_sha256=source.sha256,
                source_type=SOURCE_TYPE_REAL_A,
                clock_domain=domain,
                origin_utc=None,
                physical_source_key=f"{source.sha256}:{boot_id}",
                samples=_dedupe_samples(samples),
                physical_eligibility=physical_eligibility,
                exclusion_reasons=tuple(exclusion_reasons),
                source_run_ids=tuple(capture.run.run_ids),
            )
        )
    return tuple(trajectories)


@dataclass(frozen=True)
class FeatureSummaryRow:
    feature_id: str
    family: str
    population: str
    anchors: int
    produced: int
    missing_by_reason: tuple[tuple[str, int], ...]
    first_eligible_anchor_s: float | None
    first_value_anchor_s: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "family": self.family,
            "population": self.population,
            "anchors": self.anchors,
            "produced": self.produced,
            "missing_total": self.anchors - self.produced,
            "missing_by_reason": dict(self.missing_by_reason),
            "first_eligible_anchor_s": self.first_eligible_anchor_s,
            "first_value_anchor_s": self.first_value_anchor_s,
        }


def summarize_feature_rows(
    rows: Sequence[FeatureRow],
    registry: FeatureRegistry,
    *,
    population: str,
) -> tuple[FeatureSummaryRow, ...]:
    summaries = []
    for index, feature in enumerate(registry.features):
        reasons: dict[str, int] = {}
        produced = 0
        first_value: float | None = None
        first_eligible: float | None = None
        for row in rows:
            reason = row.missing_reasons[index]
            if reason != MISSING_INSUFFICIENT_HISTORY and first_eligible is None:
                first_eligible = row.anchor_t_s
            if reason == PRESENT:
                produced += 1
                if first_value is None:
                    first_value = row.anchor_t_s
            else:
                reasons[reason] = reasons.get(reason, 0) + 1
        summaries.append(
            FeatureSummaryRow(
                feature_id=feature.feature_id,
                family=feature.family,
                population=population,
                anchors=len(rows),
                produced=produced,
                missing_by_reason=tuple(sorted(reasons.items())),
                first_eligible_anchor_s=first_eligible,
                first_value_anchor_s=first_value,
            )
        )
    return tuple(summaries)


def feature_schema_identity(registry: FeatureRegistry) -> dict[str, Any]:
    return {
        "feature_schema_version": registry.feature_version,
        "registry_sha256": registry.schema_sha256,
        "feature_count": len(registry.features),
        "feature_ids": list(registry.feature_ids),
        "features_by_family": {
            family: list(ids) for family, ids in registry.features_by_family().items()
        },
    }
