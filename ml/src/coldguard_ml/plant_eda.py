"""W07 plant EDA, repeatability and pairing-input analysis (B-W07-01 … B-W07-04).

The module consumes the W04 normalized capture model and the W05/W06
diagnostics. It adds no competing parser, run validator or timing
implementation.

Scientific boundaries enforced here:

* phase boundaries come from an actual applied-duty state, never from a
  filename, desired command, ACK or scenario label;
* an absent applied state is ``UNDETERMINED``; it is never converted to OFF;
* the TEC hot side never enters a chamber-air representation;
* a partial chamber-air mean is not the full quantity and is excluded rather
  than substituted;
* slopes name representation, window and estimator, and a trailing-window
  slope is never presented as a phase summary;
* within-run row spread is not between-run repeatability;
* only qualified independent physical runs contribute to repeatability, and
  synthetic controls never enter the physical report;
* electrical values without a recorded qualification stay diagnostic-only,
  with no energy, COP or whole-system claim.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .intake import (
    Capture,
    NormalizedRow,
    ProbeReading,
    RoleError,
)
from .real_data_qa import (
    PERCENTILE_LINEAR,
    QAConfig,
    compute_interval_statistics,
    percentile,
)

PLANT_EDA_LAYER_VERSION = "coldguard-w07-plant-eda-v1"
PLANT_EDA_REPORT_SCHEMA = "coldguard-w07-plant-eda-report-v1"
PLANT_EDA_MANIFEST_SCHEMA = "coldguard-w07-plant-eda-manifest-v1"

PHASE_PASSIVE_WARMUP = "PASSIVE_WARMUP"
PHASE_COOLING_STEP = "COOLING_STEP"
PHASE_POST_ACTION_RECOVERY = "POST_ACTION_RECOVERY"
PHASE_UNDETERMINED = "UNDETERMINED"
PHASE_CLASSES = (
    PHASE_PASSIVE_WARMUP,
    PHASE_COOLING_STEP,
    PHASE_POST_ACTION_RECOVERY,
    PHASE_UNDETERMINED,
)

APPLIED_COOLING = "COOLING"
APPLIED_OFF = "OFF"
APPLIED_UNDETERMINED = "UNDETERMINED"

REPRESENTATION_AIRROLES = "tmean_airroles_v0"
REPRESENTATION_CHAMBER3 = "tmean_chamber3_v0"
REPRESENTATION_T2EXCLUDED = "tmean_t2excluded_v0"
REPRESENTATION_ALL4 = "tmean_all4_v0"
REPRESENTATION_NAMES = (
    REPRESENTATION_AIRROLES,
    REPRESENTATION_CHAMBER3,
    REPRESENTATION_T2EXCLUDED,
    REPRESENTATION_ALL4,
)
CHAMBER_AIR_REPRESENTATIONS = (
    REPRESENTATION_AIRROLES,
    REPRESENTATION_T2EXCLUDED,
)

KIND_CHAMBER_AIR = "CHAMBER_AIR"
KIND_CANONICAL_LITERAL_NON_AIR = "CANONICAL_LITERAL_NON_AIR"
KIND_SENSITIVITY = "SENSITIVITY"

DEFAULT_TRAILING_WINDOW_SAMPLES = 120
DEFAULT_TEMPERATURE_CHANGE_THRESHOLDS_C = (1.0, 2.0)
DEFAULT_LONG_GAP_MS = 5000
DEFAULT_MIN_INDEPENDENT_RUNS = 3
CV_NEAR_ZERO_ABS = 1e-9

REASON_NO_QUALIFIED_RUNS = "NO_QUALIFIED_INDEPENDENT_RUNS"
REASON_MIN_RUNS = "MINIMUM_INDEPENDENT_RUNS_NOT_MET"
REASON_DIAGNOSTIC_ONLY = "DIAGNOSTIC_SINGLE_SESSION_ONLY"
REASON_WITHIN_RUN_NOT_BETWEEN_RUN = "WITHIN_RUN_VARIATION_IS_NOT_BETWEEN_RUN_REPEATABILITY"
REASON_SAME_BOOT_PHASE = "SAME_BOOT_PHASE_SEGMENT_IS_NOT_AN_INDEPENDENT_RUN"
REASON_DUPLICATE_VIEW = "DUPLICATE_SOURCE_VIEW_NOT_AN_EXTRA_RUN"
REASON_PAIRED_ARM = "PAIRED_TREATMENT_ARM_IS_NOT_A_PLANT_REPLICATE"
REASON_UNDETERMINED = "APPLIED_STATE_UNDETERMINED"
REASON_LABEL_ABSENT = "APPLIED_LABEL_NOT_CARRIED"
REASON_LABEL_CONTRADICTS_DUTY = "APPLIED_LABEL_CONTRADICTS_DUTY"
REASON_REQUESTED_DIFFERS = "REQUESTED_DUTY_DIFFERS_FROM_APPLIED"
REASON_PARTIAL_REPRESENTATION = "PARTIAL_CHAMBER_AIR_REPRESENTATION"
REASON_INVALID_TERM = "REPRESENTATION_TERM_INVALID"
REASON_MISSING_TERM = "REPRESENTATION_TERM_MISSING"
REASON_PROBE_STATUS_UNQUALIFIED = "PROBE_STATUS_UNQUALIFIED"
REASON_CENSORED = "CENSORED_AT_CAPTURE_END"
REASON_ELECTRICAL_UNQUALIFIED = "ELECTRICAL_UNQUALIFIED"
REASON_ENVIRONMENT_UNQUALIFIED = "ENVIRONMENT_UNQUALIFIED"
REASON_DOOR_UNQUALIFIED = "DOOR_STATE_UNQUALIFIED"
REASON_OVERALL_INVALID = "OVERALL_QUALITY_INVALID_ROWS_INCLUDED_FOR_THERMAL_ONLY"
REASON_OFF_POWER = "OFF_STATE_WITH_NONZERO_ELECTRICAL_POWER"

CONFOUNDER_OBSERVED = "OBSERVED"
CONFOUNDER_UNQUALIFIED = "UNQUALIFIED"
CONFOUNDER_UNKNOWN = "UNKNOWN"
CONFOUNDER_NOT_CARRIED = "NOT_CARRIED"
CONFOUNDER_CONTRADICTORY = "CONTRADICTORY"
CONFOUNDER_NOT_COMPARABLE = "NOT_COMPARABLE"
CONFOUNDER_STATUSES = (
    CONFOUNDER_OBSERVED,
    CONFOUNDER_UNQUALIFIED,
    CONFOUNDER_UNKNOWN,
    CONFOUNDER_NOT_CARRIED,
    CONFOUNDER_CONTRADICTORY,
    CONFOUNDER_NOT_COMPARABLE,
)

CV_DEFINED = "DEFINED"
CV_UNDEFINED_N_LT_2 = "UNDEFINED_N_LT_2"
CV_UNDEFINED_MEAN = "UNDEFINED_ZERO_OR_NEAR_ZERO_MEAN"
CV_UNDEFINED_NON_POSITIVE = "UNDEFINED_NON_POSITIVE_MEAN"
CV_UNDEFINED_SCALE = "UNDEFINED_NOT_A_RATIO_SCALE"

REPEATABILITY_ESTABLISHED = "ESTABLISHED"
REPEATABILITY_NOT_ESTABLISHED = "NOT_ESTABLISHED"
REPEATABILITY_NOT_VERIFIED = "NOT_VERIFIED"

SCALE_RATIO = "RATIO"
SCALE_INTERVAL = "INTERVAL"
SCALE_DERIVED = "DERIVED"


@dataclass(frozen=True)
class Representation:
    name: str
    kind: str
    positions: tuple[str, ...]
    slots: tuple[str, ...]
    includes_hot_side: bool
    physical_meaning: str
    available: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "positions": list(self.positions),
            "slots": list(self.slots),
            "includes_hot_side": self.includes_hot_side,
            "physical_meaning": self.physical_meaning,
            "available": self.available,
            "reason_codes": list(self.reason_codes),
        }


_DEFINITIONS: dict[str, tuple[str, tuple[str, ...], str]] = {
    REPRESENTATION_AIRROLES: (
        KIND_CHAMBER_AIR,
        ("CHAMBER_CENTER", "CHAMBER_BOTTOM", "CHAMBER_NEAR_DOOR"),
        "As-built chamber-air mean over the three role-qualified air probes. "
        "This rig's TEC hot side is excluded.",
    ),
    REPRESENTATION_CHAMBER3: (
        KIND_CANONICAL_LITERAL_NON_AIR,
        ("CHAMBER_CENTER", "TEC_HOT_SIDE", "CHAMBER_BOTTOM"),
        "The literal docs/01 §20.1 mean(T1,T2,T3) slot expression. On this "
        "hardware it averages hot-side metal into an air temperature and is "
        "never a chamber-air quantity.",
    ),
    REPRESENTATION_T2EXCLUDED: (
        KIND_CHAMBER_AIR,
        ("CHAMBER_CENTER", "CHAMBER_BOTTOM"),
        "Degraded two-probe chamber-air mean (TEC hot side excluded).",
    ),
    REPRESENTATION_ALL4: (
        KIND_SENSITIVITY,
        (
            "CHAMBER_CENTER",
            "TEC_HOT_SIDE",
            "CHAMBER_BOTTOM",
            "CHAMBER_NEAR_DOOR",
        ),
        "All-probe sensitivity mean; includes the hot side and is not chamber air.",
    ),
}


def build_representations(capture: Capture) -> dict[str, Representation]:
    """Resolve representation terms from physical positions, never slot labels."""
    by_position: dict[str, list[str]] = {}
    for role in capture.sensors:
        if role.physical_position is not None:
            by_position.setdefault(role.physical_position, []).append(role.slot)
    representations: dict[str, Representation] = {}
    for name, (kind, positions, meaning) in _DEFINITIONS.items():
        slots: list[str] = []
        reasons: list[str] = []
        for position in positions:
            matches = sorted(by_position.get(position, []))
            if len(matches) != 1:
                reasons.append(f"POSITION_{position}_NOT_UNIQUELY_CARRIED")
            slots.extend(matches)
        includes_hot_side = "TEC_HOT_SIDE" in positions
        if kind == KIND_CHAMBER_AIR and includes_hot_side:
            raise RoleError(f"{name!r} would average the TEC hot side into chamber air")
        available = not reasons
        if available:
            expected = sorted(slots)
            if name in CHAMBER_AIR_REPRESENTATIONS:
                for slot in expected:
                    role = capture.sensor(slot)
                    if role.in_chamber_air_aggregate is not True:
                        raise RoleError(
                            f"{name!r} includes slot {slot!r}, which is not in the "
                            "role-qualified chamber-air aggregate"
                        )
        representations[name] = Representation(
            name=name,
            kind=kind,
            positions=tuple(positions),
            slots=tuple(sorted(slots)) if slots else (),
            includes_hot_side=includes_hot_side,
            physical_meaning=meaning,
            available=available,
            reason_codes=tuple(reasons),
        )
    return representations


@dataclass(frozen=True)
class RepresentationValue:
    value_c: float | None
    quality: str
    values_c: tuple[tuple[str, float | None], ...]
    reason_codes: tuple[str, ...]


def representation_value(
    capture: Capture, row: NormalizedRow, representation: Representation
) -> RepresentationValue:
    """Full-term mean only; a missing or invalid term returns ``None``."""
    if not representation.available:
        return RepresentationValue(None, "NOT_ESTIMABLE", (), representation.reason_codes)
    readings: list[tuple[str, float | None]] = []
    values: list[float] = []
    reasons: list[str] = []
    unqualified = False
    for slot in representation.slots:
        try:
            reading: ProbeReading = row.probe(slot)
        except KeyError:
            return RepresentationValue(
                None, "MISSING", (), (REASON_MISSING_TERM,)
            )
        readings.append((slot, reading.value_c))
        if reading.value_c is None:
            return RepresentationValue(
                None, "MISSING", tuple(readings), (REASON_MISSING_TERM,)
            )
        status = (reading.status or "").strip().upper()
        if status and status != "OK":
            return RepresentationValue(
                None, "INVALID", tuple(readings), (REASON_INVALID_TERM,)
            )
        if not status:
            unqualified = True
            reasons.append(REASON_PROBE_STATUS_UNQUALIFIED)
        values.append(reading.value_c)
    if len(values) != len(representation.slots):
        return RepresentationValue(
            None, "NOT_ESTIMABLE", tuple(readings), (REASON_PARTIAL_REPRESENTATION,)
        )
    return RepresentationValue(
        sum(values) / len(values),
        "UNQUALIFIED" if unqualified else "VALID",
        tuple(readings),
        tuple(sorted(set(reasons))),
    )


@dataclass(frozen=True)
class AppliedState:
    state: str
    duty_permille: int | None
    requested_permille: int | None
    label: str | None
    device_state: str | None
    reason_codes: tuple[str, ...]


def classify_applied_state(row: NormalizedRow) -> AppliedState:
    """Classify the applied cooling state from applied duty and label evidence."""
    duty = row.applied_duty_permille
    if duty is None and row.applied_duty is not None:
        duty = int(round(row.applied_duty * 1000.0))
    label = row.applied_cooling
    reasons: list[str] = []
    if duty is None:
        # A missing applied duty is not evidence of OFF. The device label may
        # be carried, but it cannot turn an unknown applied state into a phase.
        return AppliedState(
            APPLIED_UNDETERMINED,
            None,
            row.requested_duty_permille,
            label,
            row.device_state,
            (REASON_UNDETERMINED,),
        )
    duty_state = APPLIED_COOLING if duty > 0 else APPLIED_OFF
    if label == "ON":
        label_state = APPLIED_COOLING
    elif label == "OFF":
        label_state = APPLIED_OFF
    else:
        label_state = None
        reasons.append(REASON_LABEL_ABSENT)
    if label_state is not None and label_state != duty_state:
        return AppliedState(
            APPLIED_UNDETERMINED,
            duty,
            row.requested_duty_permille,
            label,
            row.device_state,
            (REASON_LABEL_CONTRADICTS_DUTY,),
        )
    if (
        row.requested_duty_permille is not None
        and row.requested_duty_permille != duty
    ):
        reasons.append(REASON_REQUESTED_DIFFERS)
    return AppliedState(
        duty_state, duty, row.requested_duty_permille, label, row.device_state,
        tuple(sorted(set(reasons))),
    )


@dataclass(frozen=True)
class PhaseSegment:
    phase: str
    phase_index: int
    start_row_index: int
    end_row_index: int
    start_s: float | None
    end_s: float | None
    rows: int
    undetermined_rows: int
    run_ids: tuple[str, ...]
    source_path: str
    source_sha256: str
    boot_id: str | None
    device_id: str | None
    reason_codes: tuple[str, ...]
    independent_experiment: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "phase_index": self.phase_index,
            "start_row_index": self.start_row_index,
            "end_row_index": self.end_row_index,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "rows": self.rows,
            "undetermined_rows": self.undetermined_rows,
            "run_ids": list(self.run_ids),
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "boot_id": self.boot_id,
            "device_id": self.device_id,
            "reason_codes": list(self.reason_codes),
            "independent_experiment": self.independent_experiment,
        }


def _row_time_s(row: NormalizedRow) -> float | None:
    return None if row.device_ms is None else row.device_ms / 1000.0


def segment_phases(capture: Capture) -> tuple[PhaseSegment, ...]:
    """Derive phase boundaries from applied state, not labels or filenames."""
    rows = capture.rows
    if not rows:
        return ()
    classes = [classify_applied_state(row).state for row in rows]
    segments: list[PhaseSegment] = []
    index = 0
    seen_cooling = False
    while index < len(rows):
        state = classes[index]
        end = index + 1
        while end < len(rows) and classes[end] == state:
            end += 1
        block = rows[index:end]
        block_reasons: set[str] = set()
        for row in block:
            applied = classify_applied_state(row)
            block_reasons.update(applied.reason_codes)
        undetermined_rows = sum(
            1 for row in block if classify_applied_state(row).state == APPLIED_UNDETERMINED
        )
        if state == APPLIED_COOLING:
            phase = PHASE_COOLING_STEP
            seen_cooling = True
        elif state == APPLIED_OFF:
            phase = PHASE_PASSIVE_WARMUP if not seen_cooling else PHASE_POST_ACTION_RECOVERY
        else:
            phase = PHASE_UNDETERMINED
        block_reasons.add(REASON_SAME_BOOT_PHASE)
        segments.append(
            PhaseSegment(
                phase=phase,
                phase_index=len(segments),
                start_row_index=index,
                end_row_index=end,
                start_s=_row_time_s(block[0]),
                end_s=_row_time_s(block[-1]),
                rows=len(block),
                undetermined_rows=undetermined_rows,
                run_ids=tuple(sorted({row.run_id for row in block if row.run_id})),
                source_path=capture.source.path,
                source_sha256=capture.source.sha256,
                boot_id=capture.run.boot_id,
                device_id=capture.run.device_id,
                reason_codes=tuple(sorted(block_reasons)),
                independent_experiment=False,
            )
        )
        index = end
    return tuple(segments)


@dataclass(frozen=True)
class PlantEDAConfig:
    representation: str = REPRESENTATION_AIRROLES
    trailing_window_samples: int = DEFAULT_TRAILING_WINDOW_SAMPLES
    temperature_change_thresholds_c: tuple[float, ...] = (
        DEFAULT_TEMPERATURE_CHANGE_THRESHOLDS_C
    )
    percentile_method: str = PERCENTILE_LINEAR
    long_gap_ms: int = DEFAULT_LONG_GAP_MS
    min_independent_runs: int = DEFAULT_MIN_INDEPENDENT_RUNS

    def validate(self) -> None:
        if self.representation not in REPRESENTATION_NAMES:
            raise ValueError(f"unknown representation {self.representation!r}")
        if self.trailing_window_samples < 2:
            raise ValueError("trailing_window_samples must be at least 2")
        if not self.temperature_change_thresholds_c:
            raise ValueError("at least one temperature-change threshold is required")
        if any(value <= 0 for value in self.temperature_change_thresholds_c):
            raise ValueError("temperature-change thresholds must be positive")
        if self.percentile_method not in (PERCENTILE_LINEAR, "nearest_rank"):
            raise ValueError(f"unsupported percentile method {self.percentile_method!r}")
        if self.long_gap_ms <= 0:
            raise ValueError("long_gap_ms must be positive")
        if self.min_independent_runs < 2:
            raise ValueError("min_independent_runs must be at least 2")

    def to_dict(self) -> dict[str, Any]:
        return {
            "representation": self.representation,
            "trailing_window_samples": self.trailing_window_samples,
            "temperature_change_thresholds_c": list(
                self.temperature_change_thresholds_c
            ),
            "percentile_method": self.percentile_method,
            "percentile_definition": (
                "linear interpolation between closest ranks"
                if self.percentile_method == PERCENTILE_LINEAR
                else "nearest-rank ceiling"
            ),
            "long_gap_ms": self.long_gap_ms,
            "min_independent_runs": self.min_independent_runs,
        }

    def replace(self, **changes: Any) -> "PlantEDAConfig":
        payload = {
            "representation": self.representation,
            "trailing_window_samples": self.trailing_window_samples,
            "temperature_change_thresholds_c": self.temperature_change_thresholds_c,
            "percentile_method": self.percentile_method,
            "long_gap_ms": self.long_gap_ms,
            "min_independent_runs": self.min_independent_runs,
        }
        payload.update(changes)
        return PlantEDAConfig(**payload)


def _least_squares_slope_c_per_min(
    points: Sequence[tuple[float, float]]
) -> float | None:
    if len(points) < 2:
        return None
    n = len(points)
    sx = sum(point[0] for point in points)
    sy = sum(point[1] for point in points)
    sxx = sum(point[0] * point[0] for point in points)
    sxy = sum(point[0] * point[1] for point in points)
    denominator = n * sxx - sx * sx
    if denominator == 0:
        return None
    return (n * sxy - sx * sy) / denominator


def _time_to_change_minutes(
    points: Sequence[tuple[float, float]], threshold_c: float, direction: str
) -> float | None:
    if len(points) < 2:
        return None
    start_t, start_value = points[0]
    for time_min, value in points:
        if direction == "DOWN" and value <= start_value - threshold_c:
            return round(time_min - start_t, 6)
        if direction == "UP" and value >= start_value + threshold_c:
            return round(time_min - start_t, 6)
    return None


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _q(values: Sequence[float], fraction: float, method: str) -> float | None:
    return percentile(values, fraction, method)


@dataclass(frozen=True)
class PhaseMetrics:
    phase: str
    phase_index: int
    representation: str
    representation_kind: str
    representation_slots: tuple[str, ...]
    representation_roles: tuple[str, ...]
    includes_hot_side: bool
    rows: int
    usable_rows: int
    skipped_rows: int
    quality_valid_rows: int
    quality_unqualified_rows: int
    quality_invalid_rows: int
    overall_quality_invalid_rows: int
    start_c: float | None
    end_c: float | None
    delta_c: float | None
    min_c: float | None
    max_c: float | None
    min_time_s: float | None
    max_time_s: float | None
    duration_min: float | None
    whole_phase_slope_c_per_min: float | None
    trailing_slope_c_per_min: float | None
    trailing_window_samples: int
    whole_phase_slope_definition: str
    trailing_slope_definition: str
    trailing_differs_from_whole_phase: bool | None
    excursion_direction: str
    initial_spread_c: float | None
    initial_probes_c: tuple[tuple[str, float | None], ...]
    end_probes_c: tuple[tuple[str, float | None], ...]
    spread_min_c: float | None
    spread_median_c: float | None
    spread_p95_c: float | None
    spread_max_c: float | None
    time_to_change_min: tuple[tuple[float, float | None], ...]
    ambient_first_c: float | None
    ambient_mean_c: float | None
    ambient_min_c: float | None
    ambient_max_c: float | None
    rh_first_pct: float | None
    rh_mean_pct: float | None
    cooling_on_rows: int
    applied_duty_min_permille: int | None
    applied_duty_max_permille: int | None
    applied_duty_mean_permille: float | None
    requested_mismatch_rows: int
    mean_voltage_v: float | None
    mean_current_a: float | None
    peak_current_a: float | None
    mean_power_w: float | None
    peak_power_w: float | None
    sampled_energy_wh: float | None
    counter_delta_wh: float | None
    electrical_qualification: str
    electrical_unqualified_rows: int
    environment_qualification: str
    door_states: tuple[tuple[str, int], ...]
    cadence_median_s: float | None
    cadence_p95_s: float | None
    long_gap_count: int
    censoring: str
    qualification: str
    reason_codes: tuple[str, ...]
    outcomes: tuple[tuple[str, float | None], ...]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
            if field_name != "outcomes"
        }
        payload["representation_slots"] = list(self.representation_slots)
        payload["representation_roles"] = list(self.representation_roles)
        payload["initial_probes_c"] = [
            [slot, value] for slot, value in self.initial_probes_c
        ]
        payload["end_probes_c"] = [
            [slot, value] for slot, value in self.end_probes_c
        ]
        payload["time_to_change_min"] = [
            [threshold, value] for threshold, value in self.time_to_change_min
        ]
        payload["door_states"] = [
            [state, count] for state, count in self.door_states
        ]
        payload["reason_codes"] = list(self.reason_codes)
        payload["outcomes"] = {
            name: value for name, value in self.outcomes if value is not None
        }
        return payload


def _phase_qualification(
    capture: Capture,
    phase: PhaseSegment,
    admission: Any | None,
) -> tuple[str, tuple[str, ...]]:
    reasons = set(phase.reason_codes)
    if admission is not None:
        status = getattr(getattr(admission, "status", None), "value", str(admission))
        highest = getattr(
            getattr(admission, "highest_stage", None), "value", None
        )
        if status != "PHYSICALLY_QUALIFIED":
            reasons.add(f"W04_ADMISSION_{status}")
        if highest is not None and highest != "PHYSICALLY_QUALIFIED":
            reasons.add(f"W04_HIGHEST_STAGE_{highest}")
        for blocker in getattr(admission, "blockers", ()) or ():
            reasons.add(getattr(blocker, "code", str(blocker)))
    if phase.phase == PHASE_UNDETERMINED:
        reasons.add(REASON_UNDETERMINED)
        return "NOT_ESTIMABLE", tuple(sorted(reasons))
    return "DIAGNOSTIC_ONLY", tuple(sorted(reasons))


def analyze_phase(
    capture: Capture,
    phase: PhaseSegment,
    representation: Representation,
    *,
    config: PlantEDAConfig,
    admission: Any | None = None,
) -> PhaseMetrics:
    rows = capture.rows[phase.start_row_index : phase.end_row_index]
    points: list[tuple[float, float]] = []
    lengths: list[float] = []
    spread_values: list[float] = []
    first_probe_values: tuple[tuple[str, float | None], ...] = ()
    last_probe_values: tuple[tuple[str, float | None], ...] = ()
    quality_valid = 0
    quality_unqualified = 0
    quality_invalid = 0
    overall_invalid = 0
    ambient_values: list[float] = []
    rh_values: list[float] = []
    voltages: list[float] = []
    currents: list[float] = []
    powers: list[float] = []
    energies: list[float] = []
    applied_duties: list[int] = []
    requested_mismatch = 0
    electrical_unqualified_rows = 0
    door_counts: dict[str, int] = {}
    reasons: set[str] = set(phase.reason_codes)
    sample_times: list[float] = []
    sample_seqs: list[int] = []
    for row in rows:
        applied = classify_applied_state(row)
        if applied.duty_permille is not None:
            applied_duties.append(applied.duty_permille)
        if REASON_REQUESTED_DIFFERS in applied.reason_codes:
            requested_mismatch += 1
        if row.overall_quality == "INVALID":
            overall_invalid += 1
        if row.door_state:
            door_counts[row.door_state] = door_counts.get(row.door_state, 0) + 1
        if row.t_air_c is not None:
            ambient_values.append(row.t_air_c)
        if row.rh_pct is not None:
            rh_values.append(row.rh_pct)
        quality = dict(row.quality)
        if quality.get("electrical") != "VALID":
            electrical_unqualified_rows += 1
        for value, bucket in (
            (row.cooling_voltage_v, voltages),
            (row.cooling_current_a, currents),
            (row.cooling_power_w, powers),
            (row.cooling_energy_counter_wh, energies),
        ):
            if value is not None:
                bucket.append(value)
        result = representation_value(capture, row, representation)
        if result.value_c is None:
            quality_invalid += 1
            reasons.update(result.reason_codes)
            continue
        quality_unqualified += 1 if result.quality == "UNQUALIFIED" else 0
        quality_valid += 1 if result.quality == "VALID" else 0
        if result.quality == "UNQUALIFIED":
            reasons.add(REASON_PROBE_STATUS_UNQUALIFIED)
        if not first_probe_values:
            first_probe_values = result.values_c
        last_probe_values = result.values_c
        time_s = _row_time_s(row)
        if time_s is None:
            continue
        points.append((time_s / 60.0, result.value_c))
        sample_times.append(time_s)
        sample_seqs.append(row.seq)
        spread = [value for _, value in result.values_c if value is not None]
        if len(spread) == len(representation.slots):
            spread_values.append(max(spread) - min(spread))
    if overall_invalid:
        reasons.add(REASON_OVERALL_INVALID)
    if electrical_unqualified_rows:
        reasons.add(REASON_ELECTRICAL_UNQUALIFIED)
    if all(dict(row.quality).get("environment") != "VALID" for row in rows):
        reasons.add(REASON_ENVIRONMENT_UNQUALIFIED)
    if all(dict(row.quality).get("door") != "VALID" for row in rows):
        reasons.add(REASON_DOOR_UNQUALIFIED)
    if phase.phase == PHASE_POST_ACTION_RECOVERY:
        reasons.add(REASON_CENSORED)
    qualification, qual_reasons = _phase_qualification(capture, phase, admission)
    reasons.update(qual_reasons)
    if len(points) < 2:
        reasons.add("FEWER_THAN_TWO_FULL_TERM_SAMPLES")
    whole = _least_squares_slope_c_per_min(points)
    trailing_points = points[-config.trailing_window_samples :]
    trailing = _least_squares_slope_c_per_min(trailing_points)
    delta = points[-1][1] - points[0][1] if len(points) >= 2 else None
    if delta is None:
        direction = "NOT_ESTIMABLE"
    elif delta <= -0.05:
        direction = "COOLING"
    elif delta >= 0.05:
        direction = "WARMING"
    else:
        direction = "FLAT"
    time_to_change: list[tuple[float, float | None]] = []
    if len(points) >= 2:
        threshold_direction = {
            PHASE_COOLING_STEP: "DOWN",
            PHASE_PASSIVE_WARMUP: "UP",
            PHASE_POST_ACTION_RECOVERY: "UP",
            PHASE_UNDETERMINED: "UP",
        }[phase.phase]
        for threshold in config.temperature_change_thresholds_c:
            time_to_change.append(
                (
                    float(threshold),
                    _time_to_change_minutes(points, threshold, threshold_direction),
                )
            )
    sampled_energy_wh: float | None = None
    if len(points) >= 2:
        energy_sum = 0.0
        any_energy = False
        for index in range(len(rows) - 1):
            left = rows[index]
            right = rows[index + 1]
            if (
                left.cooling_power_w is not None
                and left.device_ms is not None
                and right.device_ms is not None
                and right.device_ms >= left.device_ms
            ):
                energy_sum += left.cooling_power_w * (right.device_ms - left.device_ms) / 1000.0
                any_energy = True
        sampled_energy_wh = round(energy_sum / 3600.0, 6) if any_energy else None
    counter_delta_wh = (
        round(energies[-1] - energies[0], 6) if len(energies) >= 2 else None
    )
    interval = compute_interval_statistics(
        sample_times,
        sample_seqs,
        config=QAConfig(long_gap_ms=config.long_gap_ms),
    )
    spread_min = min(spread_values) if spread_values else None
    spread_median = _q(spread_values, 0.5, config.percentile_method) if spread_values else None
    spread_p95 = _q(spread_values, 0.95, config.percentile_method) if spread_values else None
    spread_max = max(spread_values) if spread_values else None
    outcomes = _phase_outcomes(
        start_c=points[0][1] if points else None,
        end_c=points[-1][1] if points else None,
        delta_c=delta,
        min_c=min((value for _, value in points), default=None),
        max_c=max((value for _, value in points), default=None),
        whole=whole,
        trailing=trailing,
        initial_spread=spread_values[0] if spread_values else None,
        time_to_change=time_to_change,
        mean_power=_mean(powers),
        peak_power=max(powers) if powers else None,
        mean_current=_mean(currents),
        peak_current=max(currents) if currents else None,
        sampled_energy=sampled_energy_wh,
        counter_delta=counter_delta_wh,
        duration_min=(points[-1][0] - points[0][0]) if len(points) >= 2 else None,
        valid_sample_fraction=(
            len(points) / len(rows) if rows else None
        ),
        spread_median=spread_median,
    )
    return PhaseMetrics(
        phase=phase.phase,
        phase_index=phase.phase_index,
        representation=representation.name,
        representation_kind=representation.kind,
        representation_slots=representation.slots,
        representation_roles=representation.positions,
        includes_hot_side=representation.includes_hot_side,
        rows=len(rows),
        usable_rows=len(points),
        skipped_rows=len(rows) - len(points),
        quality_valid_rows=quality_valid,
        quality_unqualified_rows=quality_unqualified,
        quality_invalid_rows=quality_invalid,
        overall_quality_invalid_rows=overall_invalid,
        start_c=None if not points else round(points[0][1], 6),
        end_c=None if not points else round(points[-1][1], 6),
        delta_c=None if delta is None else round(delta, 6),
        min_c=None if not points else round(min(value for _, value in points), 6),
        max_c=None if not points else round(max(value for _, value in points), 6),
        min_time_s=(
            None
            if not points
            else round(min(points, key=lambda item: item[1])[0] * 60.0, 6)
        ),
        max_time_s=(
            None
            if not points
            else round(max(points, key=lambda item: item[1])[0] * 60.0, 6)
        ),
        duration_min=(
            None
            if len(points) < 2
            else round(points[-1][0] - points[0][0], 6)
        ),
        whole_phase_slope_c_per_min=None if whole is None else round(whole, 6),
        trailing_slope_c_per_min=None if trailing is None else round(trailing, 6),
        trailing_window_samples=config.trailing_window_samples,
        whole_phase_slope_definition=(
            f"{representation.name}/whole_phase_least_squares_v0"
        ),
        trailing_slope_definition=(
            f"{representation.name}/{config.trailing_window_samples}samples/"
            "trailing_window_least_squares_v0"
        ),
        trailing_differs_from_whole_phase=(
            None
            if trailing is None or whole is None
            else abs(trailing - whole) > 1e-9
        ),
        excursion_direction=direction,
        initial_spread_c=(
            None if not spread_values else round(spread_values[0], 6)
        ),
        initial_probes_c=first_probe_values,
        end_probes_c=last_probe_values,
        spread_min_c=None if spread_min is None else round(spread_min, 6),
        spread_median_c=None if spread_median is None else round(spread_median, 6),
        spread_p95_c=None if spread_p95 is None else round(spread_p95, 6),
        spread_max_c=None if spread_max is None else round(spread_max, 6),
        time_to_change_min=tuple(time_to_change),
        ambient_first_c=ambient_values[0] if ambient_values else None,
        ambient_mean_c=None if not ambient_values else round(_mean(ambient_values), 6),
        ambient_min_c=min(ambient_values) if ambient_values else None,
        ambient_max_c=max(ambient_values) if ambient_values else None,
        rh_first_pct=rh_values[0] if rh_values else None,
        rh_mean_pct=None if not rh_values else round(_mean(rh_values), 6),
        cooling_on_rows=sum(
            1
            for row in rows
            if classify_applied_state(row).state == APPLIED_COOLING
        ),
        applied_duty_min_permille=min(applied_duties) if applied_duties else None,
        applied_duty_max_permille=max(applied_duties) if applied_duties else None,
        applied_duty_mean_permille=(
            None if not applied_duties else round(_mean(applied_duties), 6)
        ),
        requested_mismatch_rows=requested_mismatch,
        mean_voltage_v=None if not voltages else round(_mean(voltages), 6),
        mean_current_a=None if not currents else round(_mean(currents), 6),
        peak_current_a=max(currents) if currents else None,
        mean_power_w=None if not powers else round(_mean(powers), 6),
        peak_power_w=max(powers) if powers else None,
        sampled_energy_wh=sampled_energy_wh,
        counter_delta_wh=counter_delta_wh,
        electrical_qualification=(
            "VALID" if electrical_unqualified_rows == 0 else "UNQUALIFIED"
        ),
        electrical_unqualified_rows=electrical_unqualified_rows,
        environment_qualification=(
            "VALID"
            if all(dict(row.quality).get("environment") == "VALID" for row in rows)
            else "UNQUALIFIED"
        ),
        door_states=tuple(sorted(door_counts.items())),
        cadence_median_s=interval.median_dt_s,
        cadence_p95_s=interval.p95_dt_s,
        long_gap_count=interval.long_gap_count,
        censoring=(
            REASON_CENSORED
            if phase.phase == PHASE_POST_ACTION_RECOVERY
            else "NOT_CENSORED"
        ),
        qualification=qualification,
        reason_codes=tuple(sorted(reasons)),
        outcomes=outcomes,
    )


def _phase_outcomes(**values: Any) -> tuple[tuple[str, float | None], ...]:
    mapping = {
        "start_c": values["start_c"],
        "end_c": values["end_c"],
        "delta_c": values["delta_c"],
        "min_c": values["min_c"],
        "max_c": values["max_c"],
        "whole_phase_slope_c_per_min": values["whole"],
        "trailing_slope_c_per_min": values["trailing"],
        "initial_spread_c": values["initial_spread"],
        "minutes_to_1c": (
            values["time_to_change"][0][1] if values["time_to_change"] else None
        ),
        "minutes_to_2c": (
            values["time_to_change"][1][1]
            if len(values["time_to_change"]) > 1
            else None
        ),
        "mean_power_w": values["mean_power"],
        "peak_power_w": values["peak_power"],
        "mean_current_a": values["mean_current"],
        "peak_current_a": values["peak_current"],
        "sampled_energy_wh": values["sampled_energy"],
        "counter_delta_wh": values["counter_delta"],
        "duration_min": values["duration_min"],
        "valid_sample_fraction": values["valid_sample_fraction"],
        "spread_median_c": values["spread_median"],
    }
    return tuple(
        (name, None if value is None else round(float(value), 6))
        for name, value in mapping.items()
    )


# ---------------------------------------------------------------------------
# Cross-check against A's published W07 references (read-only evidence)
# ---------------------------------------------------------------------------


_A_PHASE_TO_B = {
    "baseline": PHASE_PASSIVE_WARMUP,
    "cooling": PHASE_COOLING_STEP,
    "recovery": PHASE_POST_ACTION_RECOVERY,
}


@dataclass(frozen=True)
class CrossCheckRow:
    phase: str
    field: str
    reference_source: str
    reference_value: float | int | None
    computed_value: float | int | None
    unit: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "field": self.field,
            "reference_source": self.reference_source,
            "reference_value": self.reference_value,
            "computed_value": self.computed_value,
            "unit": self.unit,
            "status": self.status,
            "detail": self.detail,
        }


def cross_check_a_references(
    metrics: Sequence[PhaseMetrics],
    references: dict[str, dict[str, Any]],
    *,
    primary_definition: str,
) -> tuple[CrossCheckRow, ...]:
    """Compare B's independent computation with A's external reference values.

    A's values are read-only cross-check targets, never copied into B's
    results. Every mismatch names the likely definitional cause instead of
    forcing agreement.
    """
    by_phase = {metric.phase: metric for metric in metrics}
    outcomes_by_metric = {metric.phase: dict(metric.outcomes) for metric in metrics}
    rows: list[CrossCheckRow] = []
    tolerance_by_field = {
        "start_c": 5e-4,
        "end_c": 5e-4,
        "delta_c": 5e-4,
        "max_c": 5e-4,
        "min_c": 5e-4,
        "whole_phase_slope_c_per_min": 1e-5,
        "slope_c_per_min": 1e-5,
        "minutes_to_1c": 5e-4,
        "minutes_to_2c": 5e-4,
        "samples": 0.5,
        "rows_read": 0.5,
    }
    field_map = {
        "start_c": ("start_c", "°C"),
        "end_c": ("end_c", "°C"),
        "delta_c": ("delta_c", "°C"),
        "max_c": ("max_c", "°C"),
        "min_c": ("min_c", "°C"),
        "whole_phase_slope_c_per_min": ("whole_phase_slope_c_per_min", "°C/min"),
        "slope_c_per_min": ("trailing_slope_c_per_min", "°C/min"),
        "minutes_to_1c": ("minutes_to_1c", "min"),
        "minutes_to_2c": ("minutes_to_2c", "min"),
        "samples": ("usable_rows", "rows"),
        "rows_read": ("rows", "rows"),
    }
    for reference_phase, payload in sorted(references.items()):
        phase = _A_PHASE_TO_B.get(reference_phase)
        if phase is None or phase not in by_phase:
            rows.append(
                CrossCheckRow(
                    phase=reference_phase,
                    field="phase",
                    reference_source="A W07 reference",
                    reference_value=None,
                    computed_value=None,
                    unit="",
                    status="NOT_COMPARABLE",
                    detail="no matching B diagnostic phase",
                )
            )
            continue
        metric = by_phase[phase]
        reference_representation = payload.get("representation")
        if (
            reference_representation
            and reference_representation != primary_definition
        ):
            rows.append(
                CrossCheckRow(
                    phase=phase,
                    field="representation",
                    reference_source="A W07 reference",
                    reference_value=None,
                    computed_value=None,
                    unit="",
                    status="NOT_COMPARABLE",
                    detail=(
                        f"A used {reference_representation!r}; B primary is "
                        f"{primary_definition!r}"
                    ),
                )
            )
        for reference_field, (metric_field, unit) in field_map.items():
            if reference_field not in payload:
                continue
            reference_value = payload.get(reference_field)
            if metric_field in outcomes_by_metric[phase]:
                computed = outcomes_by_metric[phase][metric_field]
            else:
                computed = getattr(metric, metric_field)
            if reference_value is None and computed is None:
                status = "MATCH"
                detail = "both absent"
            elif reference_value is None or computed is None:
                status = "DIFFERS"
                detail = "one side absent"
            else:
                difference = abs(float(reference_value) - float(computed))
                tolerance = tolerance_by_field.get(reference_field, 1e-5)
                if difference <= tolerance:
                    status = "MATCH"
                    detail = f"absolute difference {difference:.3g} within {tolerance:g}"
                else:
                    status = "DIFFERS"
                    detail = (
                        f"absolute difference {difference:.6g} exceeds {tolerance:g}; "
                        "check phase boundary, representation, time base and "
                        "estimator before changing a result"
                    )
            rows.append(
                CrossCheckRow(
                    phase=phase,
                    field=reference_field,
                    reference_source="A W07 reference",
                    reference_value=reference_value,
                    computed_value=computed,
                    unit=unit,
                    status=status,
                    detail=detail,
                )
            )
    return tuple(rows)


# ---------------------------------------------------------------------------
# Repeatability: independent physical units only
# ---------------------------------------------------------------------------

SCALE_BY_METRIC = {
    "start_c": SCALE_INTERVAL,
    "end_c": SCALE_INTERVAL,
    "delta_c": SCALE_INTERVAL,
    "min_c": SCALE_INTERVAL,
    "max_c": SCALE_INTERVAL,
    "whole_phase_slope_c_per_min": SCALE_DERIVED,
    "trailing_slope_c_per_min": SCALE_DERIVED,
    "minutes_to_1c": SCALE_RATIO,
    "minutes_to_2c": SCALE_RATIO,
    "initial_spread_c": SCALE_RATIO,
    "spread_median_c": SCALE_RATIO,
    "mean_power_w": SCALE_RATIO,
    "peak_power_w": SCALE_RATIO,
    "mean_current_a": SCALE_RATIO,
    "peak_current_a": SCALE_RATIO,
    "sampled_energy_wh": SCALE_RATIO,
    "counter_delta_wh": SCALE_INTERVAL,
    "duration_min": SCALE_RATIO,
    "valid_sample_fraction": SCALE_RATIO,
}

UNIT_BY_METRIC = {
    "start_c": "°C",
    "end_c": "°C",
    "delta_c": "°C",
    "min_c": "°C",
    "max_c": "°C",
    "whole_phase_slope_c_per_min": "°C/min",
    "trailing_slope_c_per_min": "°C/min",
    "minutes_to_1c": "min",
    "minutes_to_2c": "min",
    "initial_spread_c": "°C",
    "spread_median_c": "°C",
    "mean_power_w": "W",
    "peak_power_w": "W",
    "mean_current_a": "A",
    "peak_current_a": "A",
    "sampled_energy_wh": "Wh",
    "counter_delta_wh": "Wh",
    "duration_min": "min",
    "valid_sample_fraction": "fraction",
}

REQUIRED_REPEATABILITY_PHASES = (PHASE_PASSIVE_WARMUP, PHASE_COOLING_STEP)

ELECTRICAL_METRICS = frozenset(
    {
        "mean_power_w",
        "peak_power_w",
        "mean_current_a",
        "peak_current_a",
        "sampled_energy_wh",
        "counter_delta_wh",
    }
)


def _metric_quality_domain(metric: str) -> str:
    return "electrical" if metric in ELECTRICAL_METRICS else "thermal"


@dataclass(frozen=True)
class RunRecord:
    source_path: str
    source_sha256: str
    boot_id: str | None
    device_id: str | None
    run_id: str | None
    scenario_id: str | None
    scenario_status: str | None
    hardware_config_id: str | None
    hardware_config_status: str | None
    calibration_id: str | None
    calibration_status: str | None
    firmware_version: str | None
    admission_status: str | None
    a_valid: bool | None
    synthetic: bool
    pair_id: str | None
    controller_arm: str | None
    phase: str
    outcomes: tuple[tuple[str, float | None], ...]
    quality: tuple[tuple[str, str], ...]
    reason_codes: tuple[str, ...]

    @property
    def physical_source_key(self) -> tuple[str, str, str]:
        return (
            self.source_sha256,
            self.boot_id or "NO_BOOT_ID",
            self.device_id or "NO_DEVICE_ID",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "boot_id": self.boot_id,
            "device_id": self.device_id,
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "scenario_status": self.scenario_status,
            "hardware_config_id": self.hardware_config_id,
            "hardware_config_status": self.hardware_config_status,
            "calibration_id": self.calibration_id,
            "calibration_status": self.calibration_status,
            "firmware_version": self.firmware_version,
            "admission_status": self.admission_status,
            "a_valid": self.a_valid,
            "synthetic": self.synthetic,
            "pair_id": self.pair_id,
            "controller_arm": self.controller_arm,
            "phase": self.phase,
            "outcomes": {
                name: value for name, value in self.outcomes if value is not None
            },
            "quality": dict(self.quality),
            "reason_codes": list(self.reason_codes),
        }


def record_from_capture_phase(
    capture: Capture,
    admission: Any,
    metrics: PhaseMetrics,
    *,
    synthetic: bool | None = None,
) -> RunRecord:
    quality: dict[str, str] = {}
    values = [dict(row.quality) for row in capture.rows]
    for domain in ("thermal", "sequence", "provenance", "electrical", "environment", "door"):
        statuses = {value.get(domain) for value in values if value.get(domain)}
        if statuses == {"VALID"}:
            quality[domain] = "VALID"
        elif not statuses:
            quality[domain] = "NOT_CARRIED"
        else:
            quality[domain] = "UNQUALIFIED"
    source_provenance = capture.source.provenance
    return RunRecord(
        source_path=capture.source.path,
        source_sha256=capture.source.sha256,
        boot_id=capture.run.boot_id,
        device_id=capture.run.device_id,
        run_id=capture.run.run_id,
        scenario_id=capture.run.scenario_id,
        scenario_status=capture.run.scenario_status,
        hardware_config_id=capture.run.hardware_config_id,
        hardware_config_status=capture.run.hardware_config_status,
        calibration_id=capture.run.calibration_id,
        calibration_status=capture.run.calibration_status,
        firmware_version=capture.run.firmware_version,
        admission_status=getattr(
            getattr(admission, "status", None), "value", str(admission)
        ),
        a_valid=(
            None if capture.a_validity is None else capture.a_validity.is_valid
        ),
        synthetic=(
            source_provenance != "PHYSICAL" if synthetic is None else synthetic
        ),
        pair_id=None,
        controller_arm=capture.run.controller_id,
        phase=metrics.phase,
        outcomes=metrics.outcomes,
        quality=tuple(sorted(quality.items())),
        reason_codes=metrics.reason_codes,
    )


def qualify_run(record: RunRecord) -> tuple[bool, tuple[str, ...]]:
    """Apply the W07 independence/qualification gate to one run record."""
    reasons: list[str] = []
    if record.synthetic:
        reasons.append("SYNTHETIC_CONTROL_NOT_A_PHYSICAL_RUN")
    if record.a_valid is not True:
        reasons.append("A_LEDGER_NOT_VALID")
    if record.admission_status != "PHYSICALLY_QUALIFIED":
        reasons.append("ADMISSION_NOT_PHYSICALLY_QUALIFIED")
    if not record.boot_id:
        reasons.append("BOOT_IDENTITY_MISSING")
    if not record.device_id:
        reasons.append("DEVICE_IDENTITY_MISSING")
    if not record.run_id:
        reasons.append("RUN_IDENTITY_UNRESOLVED")
    if not record.hardware_config_id or (
        record.hardware_config_status or ""
    ) != "VERIFIED":
        reasons.append("HARDWARE_CONFIG_NOT_VERIFIED")
    if not record.calibration_id or (
        record.calibration_status or ""
    ) != "VERIFIED":
        reasons.append("CALIBRATION_IDENTITY_MISSING")
    if (record.scenario_status or "") != "CERTIFIED":
        reasons.append("SCENARIO_NOT_CERTIFIED")
    quality = dict(record.quality)
    if quality.get("thermal") != "VALID":
        reasons.append("THERMAL_QUALITY_NOT_VALID")
    if quality.get("sequence") != "VALID":
        reasons.append("SEQUENCE_QUALITY_NOT_VALID")
    if quality.get("provenance") != "VALID":
        reasons.append("PROVENANCE_QUALITY_NOT_VALID")
    return (not reasons, tuple(sorted(set(reasons))))


@dataclass(frozen=True)
class MetricSummary:
    group_id: str
    phase: str
    metric: str
    unit: str
    scale: str
    n_qualified: int
    n_diagnostic: int
    n_values: int
    mean: float | None
    sample_sd: float | None
    median: float | None
    q1: float | None
    q3: float | None
    iqr: float | None
    cv_pct: float | None
    cv_status: str
    minimum: float | None
    maximum: float | None
    missing_undefined: int
    repeatability_status: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "phase": self.phase,
            "metric": self.metric,
            "unit": self.unit,
            "scale": self.scale,
            "n_qualified_independent_runs": self.n_qualified,
            "n_diagnostic_sessions": self.n_diagnostic,
            "n_values": self.n_values,
            "mean": self.mean,
            "sample_sd": self.sample_sd,
            "median": self.median,
            "q1": self.q1,
            "q3": self.q3,
            "iqr": self.iqr,
            "cv_pct": self.cv_pct,
            "cv_status": self.cv_status,
            "min": self.minimum,
            "max": self.maximum,
            "missing_undefined_count": self.missing_undefined,
            "repeatability_status": self.repeatability_status,
            "reason_codes": list(self.reason_codes),
        }


def summarize_metric(
    values: Sequence[float | None],
    *,
    phase: str,
    metric: str,
    group_id: str = "",
    n_qualified: int,
    n_diagnostic: int,
    repeatability_status: str,
    reason_codes: Sequence[str] = (),
    percentile_method: str = PERCENTILE_LINEAR,
) -> MetricSummary:
    """Sample statistics with explicit n/scale/CV/denominator semantics."""
    present = [float(value) for value in values if value is not None]
    missing = max(n_qualified - len(present), 0)
    scale = SCALE_BY_METRIC.get(metric, SCALE_DERIVED)
    unit = UNIT_BY_METRIC.get(metric, "")
    reasons = list(reason_codes)
    if not present:
        reasons.append("NO_SAMPLES")
        return MetricSummary(
            group_id=group_id,
            phase=phase,
            metric=metric,
            unit=unit,
            scale=scale,
            n_qualified=n_qualified,
            n_diagnostic=n_diagnostic,
            n_values=0,
            mean=None,
            sample_sd=None,
            median=None,
            q1=None,
            q3=None,
            iqr=None,
            cv_pct=None,
            cv_status=CV_UNDEFINED_N_LT_2,
            minimum=None,
            maximum=None,
            missing_undefined=max(missing, 1 if n_diagnostic else 0),
            repeatability_status=repeatability_status,
            reason_codes=tuple(sorted(set(reasons))),
        )
    mean = statistics.fmean(present)
    median = percentile(present, 0.5, percentile_method)
    if len(present) >= 2:
        sample_sd = statistics.stdev(present)
        q1 = percentile(present, 0.25, percentile_method)
        q3 = percentile(present, 0.75, percentile_method)
        iqr = None if q1 is None or q3 is None else q3 - q1
        if scale != SCALE_RATIO:
            cv = None
            cv_status = CV_UNDEFINED_SCALE
            reasons.append(CV_UNDEFINED_SCALE)
        elif mean < 0:
            cv = None
            cv_status = CV_UNDEFINED_NON_POSITIVE
            reasons.append(CV_UNDEFINED_NON_POSITIVE)
        elif mean <= CV_NEAR_ZERO_ABS:
            cv = None
            cv_status = CV_UNDEFINED_MEAN
            reasons.append(CV_UNDEFINED_MEAN)
        else:
            cv = 100.0 * sample_sd / mean
            cv_status = CV_DEFINED
    else:
        sample_sd = None
        q1 = q3 = iqr = None
        cv = None
        cv_status = CV_UNDEFINED_N_LT_2
        reasons.append(CV_UNDEFINED_N_LT_2)
    return MetricSummary(
        group_id=group_id,
        phase=phase,
        metric=metric,
        unit=unit,
        scale=scale,
        n_qualified=n_qualified,
        n_diagnostic=n_diagnostic,
        n_values=len(present),
        mean=round(mean, 6),
        sample_sd=None if sample_sd is None else round(sample_sd, 6),
        median=None if median is None else round(median, 6),
        q1=None if q1 is None else round(q1, 6),
        q3=None if q3 is None else round(q3, 6),
        iqr=None if iqr is None else round(iqr, 6),
        cv_pct=None if cv is None else round(cv, 6),
        cv_status=cv_status,
        minimum=round(min(present), 6),
        maximum=round(max(present), 6),
        missing_undefined=missing,
        repeatability_status=repeatability_status,
        reason_codes=tuple(sorted(set(reasons))),
    )


@dataclass(frozen=True)
class RepeatabilitySummary:
    verdict: str
    min_independent_runs: int
    independent_physical_sources: int
    qualified_independent_runs: int
    excluded_records: int
    duplicate_views: int
    diagnostic_phase_records: int
    qualified_phase_counts: tuple[tuple[str, int], ...]
    rows: tuple[MetricSummary, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "min_independent_runs": self.min_independent_runs,
            "independent_physical_sources": self.independent_physical_sources,
            "qualified_independent_runs": self.qualified_independent_runs,
            "excluded_records": self.excluded_records,
            "duplicate_views": self.duplicate_views,
            "diagnostic_phase_records": self.diagnostic_phase_records,
            "qualified_phase_counts": dict(self.qualified_phase_counts),
            "reason_codes": list(self.reason_codes),
            "rows": [row.to_dict() for row in self.rows],
        }


def _collapse_units(
    records: Sequence[RunRecord],
) -> tuple[dict[tuple[str, str, str, str], RunRecord], int]:
    """One value per physical source per phase; duplicate views collapse."""
    units: dict[tuple[str, str, str, str], RunRecord] = {}
    duplicates = 0
    for record in sorted(
        records,
        key=lambda item: (
            item.phase,
            item.physical_source_key,
            item.source_path,
            item.run_id or "",
        ),
    ):
        key = (*record.physical_source_key, record.phase)
        if key in units:
            duplicates += 1
        units.setdefault(key, record)
    return units, duplicates


def _group_key(record: RunRecord) -> tuple[str, str, str, str]:
    return (
        record.scenario_id or "NO_SCENARIO",
        record.phase,
        record.hardware_config_id or "NO_HARDWARE_CONFIG",
        record.calibration_id or "NO_CALIBRATION",
    )


def _group_id(record: RunRecord) -> str:
    return "|".join(_group_key(record))


def analyze_repeatability(
    records: Sequence[RunRecord],
    *,
    min_independent_runs: int = DEFAULT_MIN_INDEPENDENT_RUNS,
    percentile_method: str = PERCENTILE_LINEAR,
) -> RepeatabilitySummary:
    """Physical repeatability over qualified independent units only.

    Comparable phase groups are separated by scenario, hardware configuration
    and calibration identity; different populations are never pooled.
    """
    physical = [record for record in records if not record.synthetic]
    synthetic = [record for record in records if record.synthetic]
    grouped: dict[tuple[str, str, str, str], list[RunRecord]] = {}
    for record in physical:
        if record.phase == PHASE_UNDETERMINED:
            continue
        grouped.setdefault(_group_key(record), []).append(record)
    rows: list[MetricSummary] = []
    qualified_phase_counts: dict[str, int] = {}
    excluded = 0
    duplicate_views = 0
    qualified_source_keys: set[tuple[str, str, str]] = set()
    diagnostic_total = 0
    reasons: set[str] = set()
    required_phase_present = {
        phase: False for phase in REQUIRED_REPEATABILITY_PHASES
    }
    required_groups_ok = True
    for group_key, group_records in sorted(grouped.items(), key=lambda item: str(item[0])):
        scenario, phase, hardware, calibration = group_key
        group_id = f"{scenario}|{phase}|{hardware}|{calibration}"
        units, duplicates = _collapse_units(group_records)
        duplicate_views += duplicates
        qualified: list[RunRecord] = []
        diagnostic: list[RunRecord] = []
        for _, record in sorted(units.items()):
            if record.pair_id is not None:
                excluded += 1
                reasons.add(REASON_PAIRED_ARM)
                continue
            diagnostic.append(record)
            ok, gate_reasons = qualify_run(record)
            if ok:
                qualified.append(record)
                qualified_source_keys.add(record.physical_source_key)
                qualified_phase_counts[phase] = qualified_phase_counts.get(phase, 0) + 1
            else:
                excluded += 1
                reasons.update(gate_reasons)
        diagnostic_total += len(diagnostic)
        status = (
            REPEATABILITY_ESTABLISHED
            if len(qualified) >= min_independent_runs
            else REPEATABILITY_NOT_ESTABLISHED
        )
        if status != REPEATABILITY_ESTABLISHED:
            reasons.add(
                REASON_MIN_RUNS if qualified else REASON_NO_QUALIFIED_RUNS
            )
        if phase in REQUIRED_REPEATABILITY_PHASES:
            required_phase_present[phase] = True
            if status != REPEATABILITY_ESTABLISHED:
                required_groups_ok = False
        for metric in SCALE_BY_METRIC:
            domain = _metric_quality_domain(metric)
            metric_qualified = [
                record
                for record in qualified
                if dict(record.quality).get(domain) == "VALID"
            ]
            metric_diagnostic = list(diagnostic)
            metric_status = (
                REPEATABILITY_ESTABLISHED
                if len(metric_qualified) >= min_independent_runs
                else REPEATABILITY_NOT_ESTABLISHED
            )
            metric_reasons = set(reasons)
            if domain == "electrical" and any(
                dict(record.quality).get("electrical") != "VALID"
                for record in metric_diagnostic
            ):
                metric_reasons.add(REASON_ELECTRICAL_UNQUALIFIED)
            if metric_status != REPEATABILITY_ESTABLISHED:
                metric_reasons.add(
                    REASON_MIN_RUNS
                    if metric_qualified
                    else REASON_NO_QUALIFIED_RUNS
                )
            qualified_values = [
                dict(record.outcomes).get(metric) for record in metric_qualified
            ]
            diagnostic_values = [
                dict(record.outcomes).get(metric) for record in metric_diagnostic
            ]
            summary = summarize_metric(
                qualified_values if metric_qualified else diagnostic_values,
                phase=phase,
                metric=metric,
                group_id=group_id,
                n_qualified=len(metric_qualified),
                n_diagnostic=len(metric_diagnostic),
                repeatability_status=metric_status,
                reason_codes=(
                    tuple(sorted(metric_reasons))
                    if metric_status != REPEATABILITY_ESTABLISHED
                    else ()
                )
                + (
                    (REASON_WITHIN_RUN_NOT_BETWEEN_RUN,)
                    if metric_diagnostic
                    else ()
                ),
                percentile_method=percentile_method,
            )
            rows.append(summary)
    verdict = (
        REPEATABILITY_ESTABLISHED
        if required_groups_ok
        and all(required_phase_present.values())
        and all(
            qualified_phase_counts.get(phase, 0) >= min_independent_runs
            for phase in REQUIRED_REPEATABILITY_PHASES
        )
        else REPEATABILITY_NOT_ESTABLISHED
    )
    if verdict != REPEATABILITY_ESTABLISHED:
        if not all(
            qualified_phase_counts.get(phase, 0) for phase in REQUIRED_REPEATABILITY_PHASES
        ):
            reasons.add(REASON_NO_QUALIFIED_RUNS)
        if not all(
            qualified_phase_counts.get(phase, 0) >= min_independent_runs
            for phase in REQUIRED_REPEATABILITY_PHASES
        ):
            reasons.add(REASON_MIN_RUNS)
    if synthetic:
        reasons.add("SYNTHETIC_CONTROLS_EXCLUDED_FROM_PHYSICAL_REPORT")
    return RepeatabilitySummary(
        verdict=verdict,
        min_independent_runs=min_independent_runs,
        independent_physical_sources=len(
            {record.physical_source_key for record in physical}
        ),
        qualified_independent_runs=len(qualified_source_keys),
        excluded_records=excluded,
        duplicate_views=duplicate_views,
        diagnostic_phase_records=diagnostic_total,
        qualified_phase_counts=tuple(sorted(qualified_phase_counts.items())),
        rows=tuple(rows),
        reason_codes=tuple(sorted(reasons)),
    )


def analyze_synthetic_control(
    records: Sequence[RunRecord],
    *,
    min_independent_runs: int = DEFAULT_MIN_INDEPENDENT_RUNS,
    percentile_method: str = PERCENTILE_LINEAR,
) -> RepeatabilitySummary:
    """Synthetic positive control: proves the statistics path, not the plant."""
    if any(not record.synthetic for record in records):
        raise ValueError("synthetic control records must all be synthetic")
    units, duplicate_views = _collapse_units(records)
    synthetic_phase_counts: dict[str, int] = {}
    rows: list[MetricSummary] = []
    for record in units.values():
        synthetic_phase_counts[record.phase] = synthetic_phase_counts.get(record.phase, 0) + 1
    for phase in PHASE_CLASSES:
        if phase == PHASE_UNDETERMINED:
            continue
        phase_records = [
            record for record in units.values() if record.phase == phase
        ]
        n = len(phase_records)
        status = (
            "SYNTHETIC_CONTROL_ONLY"
            if n >= min_independent_runs
            else "SYNTHETIC_CONTROL_INSUFFICIENT_N"
        )
        for metric in SCALE_BY_METRIC:
            values = [dict(record.outcomes).get(metric) for record in phase_records]
            rows.append(
                summarize_metric(
                    values,
                    phase=phase,
                    metric=metric,
                    n_qualified=n,
                    n_diagnostic=0,
                    repeatability_status=status,
                    reason_codes=("SYNTHETIC_CONTROL_NEVER_A_PHYSICAL_RUN",),
                    percentile_method=percentile_method,
                )
            )
    return RepeatabilitySummary(
        verdict="SYNTHETIC_CONTROL_ONLY",
        min_independent_runs=min_independent_runs,
        independent_physical_sources=0,
        qualified_independent_runs=0,
        excluded_records=0,
        duplicate_views=duplicate_views,
        diagnostic_phase_records=0,
        qualified_phase_counts=tuple(sorted(synthetic_phase_counts.items())),
        rows=tuple(rows),
        reason_codes=("SYNTHETIC_CONTROL_NEVER_A_PHYSICAL_RUN",),
    )


# ---------------------------------------------------------------------------
# Electrical anomaly visibility and confounding inventory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ElectricalAnomaly:
    row_index: int
    device_ms: int | None
    seq: int | None
    applied_state: str
    applied_duty_permille: int | None
    voltage_v: float | None
    current_a: float | None
    power_w: float | None
    previous_frame: dict[str, Any]
    next_frames: tuple[dict[str, Any], ...]
    classification: str
    competing_explanation: str
    resolution: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "device_ms": self.device_ms,
            "seq": self.seq,
            "applied_state": self.applied_state,
            "applied_duty_permille": self.applied_duty_permille,
            "voltage_v": self.voltage_v,
            "current_a": self.current_a,
            "power_w": self.power_w,
            "previous_frame": self.previous_frame,
            "next_frames": list(self.next_frames),
            "classification": self.classification,
            "competing_explanation": self.competing_explanation,
            "resolution": self.resolution,
        }


def detect_electrical_anomalies(capture: Capture) -> tuple[ElectricalAnomaly, ...]:
    """Keep OFF-state current/power frames visible; never average them away.

    Contiguous OFF-state frames above the candidate threshold form one
    anomalous episode; the first frame is the candidate trigger and the
    decaying tail stays in ``next_frames`` rather than becoming extra events.
    """
    anomalies: list[ElectricalAnomaly] = []
    index = 0
    while index < len(capture.rows):
        row = capture.rows[index]
        applied = classify_applied_state(row)
        power = row.cooling_power_w
        current = row.cooling_current_a
        if (
            applied.state != APPLIED_OFF
            or power is None
            or current is None
            or power <= 1.0
            or current <= 0.05
        ):
            index += 1
            continue
        previous = None
        if index > 0:
            candidate = capture.rows[index - 1]
            previous = {
                "device_ms": candidate.device_ms,
                "applied_state": classify_applied_state(candidate).state,
                "voltage_v": candidate.cooling_voltage_v,
                "current_a": candidate.cooling_current_a,
                "power_w": candidate.cooling_power_w,
            }
        following: list[dict[str, Any]] = []
        scan = index + 1
        while scan < len(capture.rows) and scan <= index + 7:
            item = capture.rows[scan]
            item_applied = classify_applied_state(item)
            item_power = item.cooling_power_w
            if item_applied.state != APPLIED_OFF or item_power is None:
                break
            following.append(
                {
                    "device_ms": item.device_ms,
                    "applied_state": item_applied.state,
                    "voltage_v": item.cooling_voltage_v,
                    "current_a": item.cooling_current_a,
                    "power_w": item_power,
                }
            )
            scan += 1
        anomalies.append(
            ElectricalAnomaly(
                row_index=index,
                device_ms=row.device_ms,
                seq=row.seq,
                applied_state=applied.state,
                applied_duty_permille=applied.duty_permille,
                voltage_v=row.cooling_voltage_v,
                current_a=current,
                power_w=power,
                previous_frame=previous or {},
                next_frames=tuple(following),
                classification=(
                    "CANDIDATE_CONTROL_ELECTRICAL_ANOMALY_NOT_RESOLVED_BY_HOST_TOOL"
                ),
                competing_explanation=(
                    "PZEM register/transition lag is possible; the trace decays "
                    "toward zero after this frame, but a meter trace is not a "
                    "verified zero-current measurement."
                ),
                resolution=(
                    "kept visible with provenance; no independent conclusion that "
                    "the power stage was energized; no averaging or deletion."
                ),
            )
        )
        while index < len(capture.rows):
            candidate = capture.rows[index]
            candidate_applied = classify_applied_state(candidate)
            candidate_power = candidate.cooling_power_w
            if (
                candidate_applied.state != APPLIED_OFF
                or candidate_power is None
                or candidate_power <= 1.0
            ):
                break
            index += 1
    return tuple(anomalies)


@dataclass(frozen=True)
class ConfounderEntry:
    factor: str
    status: str
    evidence: str
    source_field: str
    quality: str
    owner: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor,
            "status": self.status,
            "evidence": self.evidence,
            "source_field": self.source_field,
            "quality": self.quality,
            "owner": self.owner,
            "note": self.note,
        }


def audit_confounders(
    capture: Capture,
    metrics: Sequence[PhaseMetrics],
    admission: Any,
) -> tuple[ConfounderEntry, ...]:
    """Inventory confounding factors; absence is marked, never filled."""
    by_phase = {metric.phase: metric for metric in metrics}
    warmup = by_phase.get(PHASE_PASSIVE_WARMUP)
    cooling = by_phase.get(PHASE_COOLING_STEP)
    recovery = by_phase.get(PHASE_POST_ACTION_RECOVERY)
    run = capture.run
    entries = [
        ConfounderEntry(
            factor="Initial chamber temperature",
            status=CONFOUNDER_OBSERVED,
            evidence=(
                f"{warmup.start_c:.6f} °C at the first full-term {warmup.representation} sample"
                if warmup and warmup.start_c is not None
                else "not observed"
            ),
            source_field="t1,t3,t4 role-qualified through W04 normalized capture",
            quality="THERMAL_VALID; RUN_NOT_PHYSICALLY_QUALIFIED",
            owner="A measures / B consumes",
            note=(
                "measured pre-intervention; the run itself is diagnostic-only under "
                "the W04 admission ladder"
            ),
        ),
        ConfounderEntry(
            factor="Initial thermal gradient / spatial spread",
            status=CONFOUNDER_OBSERVED,
            evidence=(
                f"initial spread {warmup.initial_spread_c:.6f} °C (max-min across chamber probes)"
                if warmup and warmup.initial_spread_c is not None
                else "not observed"
            ),
            source_field="t1,t3,t4 per-row spread",
            quality="THERMAL_VALID; DIAGNOSTIC_ONLY",
            owner="A measures / B consumes",
            note="spread is a spatial proxy, not a heat-flux or product-quality measure",
        ),
        ConfounderEntry(
            factor="Ambient temperature and relative humidity",
            status=CONFOUNDER_UNQUALIFIED,
            evidence=(
                "BME values are carried but the environment quality domain is "
                f"{cooling.environment_qualification if cooling else 'UNKNOWN'}"
            ),
            source_field="air_c, rh_pct, pressure_hpa",
            quality="ENVIRONMENT_UNKNOWN",
            owner="A/C",
            note="not treated as controlled; no inference that ambient was constant",
        ),
        ConfounderEntry(
            factor="Hardware and session identity",
            status=CONFOUNDER_NOT_CARRIED,
            evidence=(
                f"boot_id={run.boot_id!r}; device_id={run.device_id!r}; "
                f"hardware_config_id={run.hardware_config_id!r}"
            ),
            source_field="capture run identity",
            quality=f"HARDWARE_{run.hardware_config_status}",
            owner="A/C",
            note=(
                "device identity is not carried by this encoding; the hardware "
                "configuration is a declared label, not a verified identity"
            ),
        ),
        ConfounderEntry(
            factor="Calibration identity",
            status=CONFOUNDER_NOT_CARRIED,
            evidence=f"calibration_id={run.calibration_id!r}",
            source_field="capture run identity",
            quality=f"CALIBRATION_{run.calibration_status}",
            owner="A",
            note="no calibration identity exists; it is never invented",
        ),
        ConfounderEntry(
            factor="Firmware and controller version",
            status=CONFOUNDER_NOT_CARRIED,
            evidence=(
                f"firmware_version={run.firmware_version!r}; "
                f"controller_id={run.controller_id!r}"
            ),
            source_field="capture run identity",
            quality="FIRMWARE_CARRIED; CONTROLLER_NOT_CARRIED",
            owner="A/C/D",
            note="controller identity is absent; firmware identity alone does not bind a treatment arm",
        ),
        ConfounderEntry(
            factor="Sensor placement and role",
            status=CONFOUNDER_OBSERVED,
            evidence=(
                "operator-frozen 2026-11-02 probe identification: T1 centre, "
                "T2 hot side, T3 bottom, T4 near door"
            ),
            source_field="sensor role records in the W04 capture",
            quality="POSITION_OPERATOR_FROZEN; ROM_READBACK_NOT_VERIFIED",
            owner="A",
            note=(
                "response-identified mapping, not an independent ROM readback, "
                "installed-geometry measurement or calibration"
            ),
        ),
        ConfounderEntry(
            factor="Load state and chamber geometry",
            status=CONFOUNDER_UNKNOWN,
            evidence="no load or geometry field is carried",
            source_field="not carried",
            quality="UNKNOWN",
            owner="A",
            note="cannot be held constant or compared across runs from this source",
        ),
        ConfounderEntry(
            factor="Previous run / thermal history",
            status=CONFOUNDER_UNKNOWN,
            evidence="no prior-session state or heat-accumulation history is carried",
            source_field="not carried",
            quality="UNKNOWN",
            owner="A/C",
            note="the single session is the first in this dossier; earlier history is unknown",
        ),
        ConfounderEntry(
            factor="Initial cooling and door state",
            status=CONFOUNDER_UNQUALIFIED,
            evidence=(
                f"applied cooling OFF before the step; door tokens "
                f"{dict(recovery.door_states) if recovery else 'UNKNOWN'}"
            ),
            source_field="pwm_applied_permille, door_open/door_polarity",
            quality="COOLING_OFF_OBSERVED; DOOR_UNQUALIFIED",
            owner="A",
            note=(
                f"door state is UNKNOWN for "
                f"{sum(1 for row in capture.rows if row.door_state == 'UNKNOWN')} "
                "rows and unqualified throughout"
            ),
        ),
        ConfounderEntry(
            factor="Cooling duty profile",
            status=CONFOUNDER_OBSERVED,
            evidence=(
                f"applied duty {cooling.applied_duty_min_permille}–"
                f"{cooling.applied_duty_max_permille} permille; requested differs on "
                f"{cooling.requested_mismatch_rows} rows"
                if cooling
                else "not observed"
            ),
            source_field="pwm_applied_permille, pwm_req_permille",
            quality="DEVICE_REPORTED_APPLIED_STATE; NOT_COMMAND_PROOF",
            owner="A",
            note="applied duty is observed; it is not a verified electrical envelope",
        ),
        ConfounderEntry(
            factor="Cooling-branch electrical qualification",
            status=CONFOUNDER_UNQUALIFIED,
            evidence=(
                f"electrical rows unqualified: "
                f"{cooling.electrical_unqualified_rows if cooling else 'UNKNOWN'}"
            ),
            source_field="voltage_v, current_a, power_w, energy_wh",
            quality="ELECTRICAL_UNKNOWN",
            owner="A/C",
            note=(
                "no recorded electrical validity; numeric summaries are "
                "diagnostic-only; no energy, COP or whole-system claim"
            ),
        ),
        ConfounderEntry(
            factor="Door disturbance history",
            status=CONFOUNDER_UNKNOWN,
            evidence="door state is CLOSED/UNKNOWN but door quality is unqualified and no disturbance event is certified",
            source_field="door_open, door_polarity",
            quality="DOOR_UNQUALIFIED",
            owner="A",
            note="no door-open event in this session; absence of a qualified event is not proof of no disturbance",
        ),
        ConfounderEntry(
            factor="Timing and acquisition cadence",
            status=CONFOUNDER_OBSERVED,
            evidence=(
                f"median dt {cooling.cadence_median_s if cooling else 'UNKNOWN'} s; "
                f"p95 {cooling.cadence_p95_s if cooling else 'UNKNOWN'} s; "
                f"long gaps {cooling.long_gap_count if cooling else 'UNKNOWN'}"
            ),
            source_field="device_ms, seq",
            quality="BOOT_SCOPED_UPTIME; CLOCK_SYNC_NOT_EVIDENCED",
            owner="A/C",
            note="boot-relative order only; no cross-boot or absolute-time alignment",
        ),
        ConfounderEntry(
            factor="Recovery / reset-state condition",
            status=CONFOUNDER_UNQUALIFIED,
            evidence=(
                f"recovery end {recovery.end_c:.6f} °C vs pre-action "
                f"{cooling.start_c:.6f} °C; reset criterion unresolved"
                if recovery and recovery.end_c is not None and cooling and cooling.start_c is not None
                else "not observed"
            ),
            source_field="role-qualified chamber-air representation",
            quality="CENSORED_AT_CAPTURE_END; RESET_CRITERION_UNRESOLVED",
            owner="A/D",
            note="the run ends without a frozen reset criterion; recovery is censored",
        ),
        ConfounderEntry(
            factor="Sensor drift and aging",
            status=CONFOUNDER_UNKNOWN,
            evidence="no repeated calibration, drift check or probe cross-check exists",
            source_field="not carried",
            quality="UNKNOWN",
            owner="A",
            note=(
                "a single session cannot separate sensor drift from plant variation; "
                "absent calibration is not evidence of a stable calibration"
            ),
        ),
        ConfounderEntry(
            factor="Run order and session-day effects",
            status=CONFOUNDER_NOT_COMPARABLE,
            evidence="one boot session; no randomized or balanced run order",
            source_field="capture session identity",
            quality="SINGLE_SESSION",
            owner="A/B",
            note="cannot estimate order, day, ambient-drift or operator-learning effects",
        ),
    ]
    for entry in entries:
        if entry.status not in CONFOUNDER_STATUSES:
            raise ValueError(f"invalid confounder status {entry.status!r}")
    return tuple(entries)


# ---------------------------------------------------------------------------
# Capture-level result
# ---------------------------------------------------------------------------


class PlantEDAError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PlantEDAResult:
    capture: Capture
    admission: Any
    config: PlantEDAConfig
    representations: dict[str, Representation]
    phases: tuple[PhaseSegment, ...]
    metrics: tuple[PhaseMetrics, ...]
    quality: dict[str, Any]
    anomalies: tuple[ElectricalAnomaly, ...]
    cross_check: tuple[CrossCheckRow, ...]
    repeatability: RepeatabilitySummary
    confounders: tuple[ConfounderEntry, ...]
    scientific_separation: dict[str, str]

    @property
    def primary_metrics(self) -> PhaseMetrics | None:
        for metric in self.metrics:
            if metric.representation == self.config.representation:
                return metric
        return None

    def metric_for(self, phase: str) -> PhaseMetrics | None:
        for metric in self.metrics:
            if metric.phase == phase:
                return metric
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.capture.source.to_dict(),
            "run": self.capture.run.to_dict(),
            "time": self.capture.time.to_dict(),
            "admission": self.admission.to_dict()
            if hasattr(self.admission, "to_dict")
            else str(self.admission),
            "config": self.config.to_dict(),
            "representations": [
                representation.to_dict()
                for _, representation in sorted(self.representations.items())
            ],
            "phases": [phase.to_dict() for phase in self.phases],
            "phase_metrics": [metric.to_dict() for metric in self.metrics],
            "quality": self.quality,
            "anomalies": [anomaly.to_dict() for anomaly in self.anomalies],
            "cross_check_a_w07": [row.to_dict() for row in self.cross_check],
            "repeatability": self.repeatability.to_dict(),
            "confounders": [entry.to_dict() for entry in self.confounders],
            "scientific_separation": dict(self.scientific_separation),
        }


def _w06_timing_diagnostics(capture: Capture) -> dict[str, Any]:
    """Consume W06 ordering, identity and duplicate diagnostics read-only."""
    from .timing_alignment import (
        audit_timeline,
        deduplicate_events,
        events_from_capture,
        order_timeline,
    )

    events = events_from_capture(capture)
    ordered = order_timeline(events)
    audit = audit_timeline(events)
    dedup = deduplicate_events(events)
    identity_counts: dict[str, int] = {}
    for event in events:
        identity_counts[event.identity_status] = (
            identity_counts.get(event.identity_status, 0) + 1
        )
    return {
        "w06_layer_version": "coldguard-w06-timing-v1",
        "order_status": ordered.status,
        "order_reason_codes": list(ordered.reason_codes),
        "aligned_device_id": ordered.device_id,
        "aligned_boot_id": ordered.boot_id,
        "event_count": len(events),
        "identity_status_counts": dict(sorted(identity_counts.items())),
        "domain_audits": [domain.to_dict() for domain in audit.domains],
        "duplicate_deliveries": dedup.duplicate_deliveries,
        "contradictory_identity_count": dedup.contradictory_identity_count,
        "missing_identity_events": len(dedup.missing_identity_events),
        "reboot_identity_resets": dedup.reboot_identity_resets,
    }


def _assert_single_session(capture: Capture) -> None:
    if not capture.rows:
        raise PlantEDAError("EMPTY_CAPTURE")
    boot_ids = {row.boot_id for row in capture.rows if row.boot_id is not None}
    if len(boot_ids) > 1:
        raise PlantEDAError("MULTIPLE_BOOT_SESSIONS_CANNOT_BE_POOLED")
    if not boot_ids:
        raise PlantEDAError("BOOT_IDENTITY_MISSING")
    times = [row.device_ms for row in capture.rows if row.device_ms is not None]
    if any(right < left for left, right in zip(times, times[1:])):
        raise PlantEDAError("NON_MONOTONIC_BOOT_TIME_REFUSED")


def analyze_capture_eda(
    capture: Capture,
    *,
    config: PlantEDAConfig | None = None,
    admission: Any | None = None,
    a_w07_references: dict[str, dict[str, Any]] | None = None,
) -> PlantEDAResult:
    """Run the W07 plant EDA over one W04-normalized physical capture."""
    from .intake import evaluate_admission
    from .real_data_qa import analyze_capture

    config = config or PlantEDAConfig()
    config.validate()
    _assert_single_session(capture)
    admission = admission if admission is not None else evaluate_admission(capture)
    representations = build_representations(capture)
    primary = representations[config.representation]
    if primary.kind != KIND_CHAMBER_AIR:
        raise PlantEDAError("NON_AIR_REPRESENTATION_CANNOT_BE_PRIMARY")
    phases = segment_phases(capture)
    metrics = tuple(
        analyze_phase(
            capture,
            phase,
            primary,
            config=config,
            admission=admission,
        )
        for phase in phases
    )
    qa = analyze_capture(capture, admission=admission)
    quality = {
        "statuses": qa.statuses.to_dict(),
        "sessions": [session.to_dict() for session in qa.sessions],
        "channels": [channel.to_dict() for channel in qa.channels],
        "anomaly_count": len(qa.anomalies),
        "w06_timing": _w06_timing_diagnostics(capture),
    }
    anomalies = detect_electrical_anomalies(capture)
    cross_check = (
        ()
        if a_w07_references is None
        else cross_check_a_references(
            metrics,
            a_w07_references,
            primary_definition=config.representation,
        )
    )
    records = tuple(
        record_from_capture_phase(capture, admission, metric)
        for metric in metrics
        if metric.phase != PHASE_UNDETERMINED
    )
    repeatability = analyze_repeatability(
        records,
        min_independent_runs=config.min_independent_runs,
        percentile_method=config.percentile_method,
    )
    confounders = audit_confounders(capture, metrics, admission)
    separation = {
        "W07_SOFTWARE": (
            "GREEN"
            if primary.available and phases and any(m.usable_rows for m in metrics)
            else "BLOCKED"
        ),
        "PHYSICAL_REPEATABILITY": repeatability.verdict,
        "PREDICTIVE_DATASET": str(
            getattr(admission, "predictive_dataset_readiness", "NOT_VERIFIED")
        ),
        "REAL_AIW": "NOT_ESTIMABLE",
    }
    return PlantEDAResult(
        capture=capture,
        admission=admission,
        config=config,
        representations=representations,
        phases=phases,
        metrics=metrics,
        quality=quality,
        anomalies=anomalies,
        cross_check=cross_check,
        repeatability=repeatability,
        confounders=confounders,
        scientific_separation=separation,
    )


# ---------------------------------------------------------------------------
# Pairing candidate variables (B-W07-04)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairingCandidate:
    variable: str
    variable_class: str
    measurement_definition: str
    physical_meaning: str
    source_fields: str
    time_domain: str
    quality_gate: str
    availability: str
    owner: str
    matching_rationale: str
    confounding_mechanism: str
    status: str
    missing_evidence: str


PAIRING_CANDIDATES: tuple[PairingCandidate, ...] = (
    PairingCandidate(
        variable="Initial chamber-air temperature",
        variable_class="MATCHING_VARIABLE",
        measurement_definition=(
            "tmean_airroles_v0 = mean(T1 centre, T3 bottom, T4 near door) at the "
            "first full-term, thermally VALID row of the run, before any cooling action."
        ),
        physical_meaning="Starting sensible-heat state of the chamber air.",
        source_fields="t1_c, t3_c, t4_c through the W04 normalized capture; roles from physical_position",
        time_domain="DEVICE_BOOT_UPTIME (boot-relative); pre-intervention",
        quality_gate="thermal VALID; sequence/provenance VALID; W04 physically-qualified run",
        availability="DIAGNOSTIC_ONLY in the current evidence (one session, admission blocked)",
        owner="A measures/attests; B defines and consumes",
        matching_rationale="A colder or warmer start shifts the whole cooling curve and time-to-threshold.",
        confounding_mechanism="Initial-state difference masquerades as a Controller A/B effect if arms start in different bands.",
        status="PROVISIONAL",
        missing_evidence="No qualified independent runs, no frozen initial-state band, no calibration identity.",
    ),
    PairingCandidate(
        variable="Initial spatial temperature spread",
        variable_class="MATCHING_VARIABLE",
        measurement_definition="max(T1,T3,T4) - min(T1,T3,T4) at the same pre-intervention row.",
        physical_meaning="Spatial non-uniformity / mixing state proxy, not heat flux.",
        source_fields="t1_c, t3_c, t4_c",
        time_domain="DEVICE_BOOT_UPTIME; pre-intervention",
        quality_gate="all three air probes present and thermally VALID at the same row",
        availability="DIAGNOSTIC_ONLY",
        owner="A measures; B defines",
        matching_rationale="A stratified chamber can produce a different response with the same mean.",
        confounding_mechanism="Non-uniform starting field and probe placement differences.",
        status="PROVISIONAL",
        missing_evidence="No repeatability estimate for the spread and no frozen gradient tolerance.",
    ),
    PairingCandidate(
        variable="Ambient temperature and relative humidity",
        variable_class="MEASURED_COVARIATE",
        measurement_definition="BME280 air temperature, RH and pressure during the run.",
        physical_meaning="Heat-rejection environment and condensation context.",
        source_fields="air_c, rh_pct, pressure_hpa",
        time_domain="DEVICE_BOOT_UPTIME",
        quality_gate="environment section VALID and sensor qualification proved",
        availability="UNQUALIFIED in the current capture (environment quality UNKNOWN)",
        owner="A/C",
        matching_rationale="Ambient conditions change heat rejection and passive warming.",
        confounding_mechanism="Ambient drift across sequential arms becomes a treatment-correlated nuisance.",
        status="UNAVAILABLE_VARIABLE",
        missing_evidence="Environment quality is UNKNOWN; BME implementation/qualification is unresolved.",
    ),
    PairingCandidate(
        variable="Initial door state and recent event history",
        variable_class="PROTOCOL_CONSTRAINT",
        measurement_definition="Door CLOSED at run start and no unrecorded opening during the paired block.",
        physical_meaning="Boundary condition for chamber-air exchange.",
        source_fields="door_open, door_polarity",
        time_domain="DEVICE_BOOT_UPTIME",
        quality_gate="door quality VALID, polarity commissioned, disturbance protocol executed",
        availability="UNQUALIFIED/UNKNOWN (door quality UNKNOWN; 17 UNKNOWN rows)",
        owner="A executes; B consumes",
        matching_rationale="An open or recently opened door changes the load and recovery.",
        confounding_mechanism="Unrecorded door disturbance or door-state label drift.",
        status="UNAVAILABLE_VARIABLE",
        missing_evidence="Door polarity/state qualification and disturbance history are not certified.",
    ),
    PairingCandidate(
        variable="Initial applied cooling state and duty",
        variable_class="MATCHING_VARIABLE_AND_PROTOCOL_CONSTRAINT",
        measurement_definition="Applied state OFF and applied duty 0 permille immediately before the step.",
        physical_meaning="Actuator state at the start of the intervention.",
        source_fields="pwm_applied_permille, pwm_req_permille, state",
        time_domain="DEVICE_BOOT_UPTIME; pre-intervention",
        quality_gate="applied duty carried; contradiction checks pass",
        availability="OBSERVED diagnostic (OFF/0 in the current session)",
        owner="A",
        matching_rationale="A residual prior action changes the starting thermal trajectory.",
        confounding_mechanism="Applied-state leakage from the previous arm into the next arm.",
        status="PROVISIONAL",
        missing_evidence="Applied-state observations are not command proof; no verified controller-arm identity.",
    ),
    PairingCandidate(
        variable="Hardware configuration identity",
        variable_class="PROTOCOL_CONSTRAINT",
        measurement_definition="Same verified hardware_config_id and physical assembly for both arms.",
        physical_meaning="Comparable plant and sensor installation.",
        source_fields="hardware_config_id, hardware_config_status",
        time_domain="Run-level metadata",
        quality_gate="hardware configuration VERIFIED, not merely declared",
        availability="UNQUALIFIED (declared label CG-HW-001, not verified)",
        owner="A",
        matching_rationale="Any reassembly changes the plant and invalidates pairing (docs/01 §32).",
        confounding_mechanism="Configuration drift masquerades as treatment effect.",
        status="UNAVAILABLE_VARIABLE",
        missing_evidence="No verification evidence for the declared hardware label.",
    ),
    PairingCandidate(
        variable="Calibration and sensor-role provenance",
        variable_class="PROTOCOL_CONSTRAINT",
        measurement_definition="Same calibration_id and role mapping, with ROM readback and position record.",
        physical_meaning="Comparable measurement scale and physical meaning.",
        source_fields="calibration_id, calibration_status, sensor role records",
        time_domain="Run-level metadata",
        quality_gate="calibration VERIFIED; ROM readback verified; role mapping frozen",
        availability="NOT_CARRIED (calibration identity absent; operator-frozen positions, ROM readback unverified)",
        owner="A",
        matching_rationale="A changed calibration or role mapping changes the measured outcome.",
        confounding_mechanism="Measurement-definition drift masquerades as a plant/controller effect.",
        status="UNAVAILABLE_VARIABLE",
        missing_evidence="No calibration exists on the current rig and no independent ROM readback is committed.",
    ),
    PairingCandidate(
        variable="Thermal recovery / reset condition",
        variable_class="MATCHING_VARIABLE",
        measurement_definition="Observed chamber-air state and slope at the predeclared reset point before the next arm.",
        physical_meaning="Whether the plant returned to a comparable starting condition.",
        source_fields="tmean_airroles_v0 trajectory, applied state",
        time_domain="DEVICE_BOOT_UPTIME; post-intervention but pre-next-arm state",
        quality_gate="reset criterion frozen; recovery not censored; thermal VALID",
        availability="UNQUALIFIED (reset criterion UNRESOLVED; recovery censored)",
        owner="A/D",
        matching_rationale="Incomplete recovery carries heat history into the next arm.",
        confounding_mechanism="Residual heat load and order effects.",
        status="UNAVAILABLE_VARIABLE",
        missing_evidence="No frozen reset criterion or observed reset in the current single session.",
    ),
    PairingCandidate(
        variable="Chamber load and geometry",
        variable_class="PROTOCOL_CONSTRAINT",
        measurement_definition="Same internal load, V1 position, door alignment and probe mounting.",
        physical_meaning="Plant thermal mass and boundary geometry.",
        source_fields="not carried in the capture",
        time_domain="Run-level metadata",
        quality_gate="geometry frozen and recorded",
        availability="UNKNOWN",
        owner="A",
        matching_rationale="Load or geometry changes alter thermal mass and response time.",
        confounding_mechanism="Physical configuration differences confound the comparison.",
        status="UNAVAILABLE_VARIABLE",
        missing_evidence="A-W07-01 remains PARTIAL; no configuration photo/drawing or load record.",
    ),
    PairingCandidate(
        variable="Prior session heat accumulation",
        variable_class="MATCHING_VARIABLE",
        measurement_definition="Thermal history and elapsed recovery time before the run, with the previous arm's applied state.",
        physical_meaning="Carry-over heat from earlier runs.",
        source_fields="not carried in the capture",
        time_domain="Session history",
        quality_gate="previous-session state and reset evidence available",
        availability="UNKNOWN",
        owner="A/B",
        matching_rationale="Previous heating/cooling shifts the initial state and recovery.",
        confounding_mechanism="Order and session-day effects correlated with the treatment arm.",
        status="UNAVAILABLE_VARIABLE",
        missing_evidence="No prior-session history is carried; only one session exists in the dossier.",
    ),
    PairingCandidate(
        variable="Cooling-branch electrical quality",
        variable_class="MEASURED_COVARIATE",
        measurement_definition="Qualified branch voltage/current/power/energy coverage for energy outcomes.",
        physical_meaning="Actual electrical work delivered to the cooling branch.",
        source_fields="voltage_v, current_a, power_w, energy_wh",
        time_domain="DEVICE_BOOT_UPTIME",
        quality_gate="electrical quality VALID and PZEM range/calibration verified",
        availability="UNQUALIFIED (no recorded electrical validity in the current capture)",
        owner="A/C",
        matching_rationale="Different electrical work changes the thermal response.",
        confounding_mechanism="Electrical differences and unqualified meters masquerade as controller efficiency.",
        status="UNAVAILABLE_VARIABLE",
        missing_evidence="Electrical status is unqualified; no qualified energy envelope or COP claim is allowed.",
    ),
)


def render_pairing_markdown() -> str:
    lines = [
        "# Pairing candidate variables for future Controller A/B comparisons",
        "",
        "> W07 / B-W07-04. These are candidate variables for a future physical",
        "> A/B campaign. They are provisional: no numeric matching tolerance is",
        "> set here and no pairing is performed by the W07 EDA.",
        "",
        "## Candidate table",
        "",
        "| Candidate | Class | Measurement definition | Physical meaning | Source field(s) | Time domain | Quality gate | Availability | Owner | Matching rationale | Confounding mechanism | Status | Missing-evidence reason |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for candidate in PAIRING_CANDIDATES:
        lines.append(
            "| "
            + " | ".join(
                [
                    candidate.variable,
                    candidate.variable_class,
                    candidate.measurement_definition,
                    candidate.physical_meaning,
                    candidate.source_fields,
                    candidate.time_domain,
                    candidate.quality_gate,
                    candidate.availability,
                    candidate.owner,
                    candidate.matching_rationale,
                    candidate.confounding_mechanism,
                    candidate.status,
                    candidate.missing_evidence,
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Units: temperatures °C, slopes °C/min, power W, energy Wh,",
            "current A, durations min; source fields retain their W04 normalized",
            "names and time domains.",
            "",
            "## Variable classes",
            "",
            "- **Matching variable** — measured before the intervention and used to",
            "  define comparable pairs.",
            "- **Measured covariate** — recorded and modelled/adjusted, not silently",
            "  assumed constant.",
            "- **Protocol constraint** — must be identical by design, not merely",
            "  observed afterwards.",
            "- **Unavailable variable** — no qualified source field exists yet.",
            "",
            "## Forbidden pairing inputs",
            "",
            "Post-intervention outcomes must never define a pair retrospectively:",
            "end temperature, ΔT, whole-phase slope, trailing slope,",
            "time-to-threshold, recovery delta, peak power, energy and any response",
            "derived from the future part of the run. Pairing uses only",
            "pre-intervention state and recorded protocol identity.",
            "",
            "## Tolerances",
            "",
            "No numeric matching tolerance is claimed. Docs `03` §35 lists",
            "`|Δ initial Tmean| <= ~0.5 °C` and `|Δ initial gradient| <= ~0.3 °C`",
            "as **candidate pilot-era values only**. `statistical-analysis-plan-v0.md`",
            "F6 records initial-condition tolerances as not set until pilot",
            "repeatability exists. This report does not use or freeze either value.",
            "",
            "## Consistency with W03/W04 methodology",
            "",
            "Future pairs must satisfy the pair-admission checklist: same `pair_id`",
            "on exactly two arms, same scenario/protocol/disturbance duration, same",
            "hardware and calibration lineage, initial conditions within frozen",
            "tolerances, randomized/balanced order, observed reset/recovery, and",
            "comparable outcome definitions. One inadmissible arm makes the pair",
            "invalid; it contributes zero pairs and is never repaired post hoc.",
            "",
            "## Current availability",
            "",
            "The present evidence has one boot session, no qualified independent",
            "runs, no verified calibration, no verified hardware configuration and",
            "no certified scenario. Every candidate above is therefore provisional",
            "or unavailable; none has an empirically supported tolerance.",
            "",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Repeatability CSV and markdown report
# ---------------------------------------------------------------------------


def repeatability_csv(summary: RepeatabilitySummary) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "group_id",
            "phase",
            "metric",
            "analysis_scope",
            "unit",
            "scale",
            "n_qualified_independent_runs",
            "n_diagnostic_sessions",
            "n_values",
            "mean",
            "sample_sd",
            "median",
            "q1",
            "q3",
            "iqr",
            "cv_pct",
            "cv_status",
            "min",
            "max",
            "missing_undefined_count",
            "repeatability_status",
            "reason_codes",
        ]
    )
    for row in summary.rows:
        writer.writerow(
            [
                row.group_id,
                row.phase,
                row.metric,
                (
                    "QUALIFIED_INDEPENDENT_RUNS"
                    if row.n_qualified > 0
                    else (
                        "DIAGNOSTIC_SINGLE_SESSION"
                        if row.n_diagnostic > 0
                        else "NO_SAMPLES"
                    )
                ),
                row.unit,
                row.scale,
                row.n_qualified,
                row.n_diagnostic,
                row.n_values,
                _csv_text(row.mean),
                _csv_text(row.sample_sd),
                _csv_text(row.median),
                _csv_text(row.q1),
                _csv_text(row.q3),
                _csv_text(row.iqr),
                _csv_text(row.cv_pct),
                row.cv_status,
                _csv_text(row.minimum),
                _csv_text(row.maximum),
                row.missing_undefined,
                row.repeatability_status,
                ";".join(row.reason_codes),
            ]
        )
    return buffer.getvalue()


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "NOT_ESTIMABLE"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _metric_value(metric: PhaseMetrics | None, name: str) -> Any:
    if metric is None:
        return None
    return dict(metric.outcomes).get(name)


def render_report(
    result: PlantEDAResult,
    *,
    code_sha256: str,
    repository_revision: str,
    generation_command: str,
) -> str:
    source = result.capture.source
    run = result.capture.run
    primary = result.config.representation
    by_phase = {metric.phase: metric for metric in result.metrics}
    warmup = by_phase.get(PHASE_PASSIVE_WARMUP)
    cooling = by_phase.get(PHASE_COOLING_STEP)
    recovery = by_phase.get(PHASE_POST_ACTION_RECOVERY)
    lines: list[str] = []
    add = lines.append
    add("# ColdGuard W07 — Physical baseline EDA, repeatability and pairing inputs")
    add("")
    add(
        "> Member B · W07 (B-W07-01 … B-W07-04). Source-based analysis only: no "
        "physical action, no model training, no W08 validator, no predictive "
        "dataset and no Controller A/B result."
    )
    add("")
    add("## 0. Scientific separation")
    add("")
    add("| Status | Value | Meaning |")
    add("|---|---|---|")
    add(
        f"| W07 SOFTWARE | {result.scientific_separation['W07_SOFTWARE']} | "
        "CLI completed, tests passed, artifacts deterministic |"
    )
    add(
        f"| PHYSICAL REPEATABILITY | {result.scientific_separation['PHYSICAL_REPEATABILITY']} | "
        f"qualified independent physical runs: {result.repeatability.qualified_independent_runs} |"
    )
    add(
        f"| PREDICTIVE DATASET | {result.scientific_separation['PREDICTIVE_DATASET']} | "
        "W04 admission verdict is authoritative |"
    )
    add(
        f"| REAL AIW | {result.scientific_separation['REAL_AIW']} | "
        "W07 does not compute AIW |"
    )
    add("")
    add("A software-green W07 with absent physical repeats is an acceptable engineering")
    add("result. It is not a repeatability or performance claim.")
    add("")
    add("## 1. Provenance and admission")
    add("")
    add("| Field | Value |")
    add("|---|---|")
    add(f"| Report schema | `{PLANT_EDA_REPORT_SCHEMA}` |")
    add(f"| W07 layer version | `{PLANT_EDA_LAYER_VERSION}` |")
    add(f"| Analysis code SHA-256 | `{code_sha256}` |")
    add(f"| Repository revision | `{repository_revision}` |")
    add(f"| Source path | `{source.path}` |")
    add(f"| Source SHA-256 | `{source.sha256}` |")
    add(f"| Source namespace/format | `{source.schema_namespace}` / `{source.format}` |")
    add(f"| Source provenance | `{source.provenance}` |")
    add(f"| Admission status | `{getattr(result.admission.status, 'value', result.admission.status)}` |")
    add(f"| Highest admission stage | `{getattr(result.admission.highest_stage, 'value', result.admission.highest_stage)}` |")
    add(f"| Predictive dataset readiness | `{result.admission.predictive_dataset_readiness}` |")
    add(f"| Eligible S1 / S2 runs | `{result.admission.eligible_s1_runs}` / `{result.admission.eligible_s2_runs}` |")
    add(f"| Run identity | `run_id={run.run_id!r}` (`{run.run_id_status}`); `run_ids={list(run.run_ids)}` |")
    add(f"| Boot identity | `{run.boot_id!r}` (`{run.boot_id_status}`) |")
    add(f"| Device identity | `{run.device_id!r}` (`{run.device_id_status}`) |")
    add(f"| Hardware configuration | `{run.hardware_config_id!r}` (`{run.hardware_config_status}`) |")
    add(f"| Calibration identity | `{run.calibration_id!r}` (`{run.calibration_status}`) |")
    add(f"| Scenario identity | `{run.scenario_id!r}` (`{run.scenario_status}`) |")
    add(f"| Generation command | `{generation_command}` |")
    add("")
    timing = result.quality.get("w06_timing", {})
    add("W06 timing/identity diagnostics consumed read-only:")
    add("")
    add("| W06 diagnostic | Value |")
    add("|---|---|")
    add(f"| Event ordering | `{timing.get('order_status', 'NOT_RUN')}` |")
    add(f"| Order reason codes | `{', '.join(timing.get('order_reason_codes', [])) or 'none'}` |")
    add(f"| Events / identity statuses | `{timing.get('event_count', 0)}` / `{timing.get('identity_status_counts', {})}` |")
    add(f"| Duplicate deliveries | `{timing.get('duplicate_deliveries', 0)}` |")
    add(f"| Contradictory identities | `{timing.get('contradictory_identity_count', 0)}` |")
    add(f"| Missing-identity events | `{timing.get('missing_identity_events', 0)}` |")
    add(f"| Reboot identity resets | `{timing.get('reboot_identity_resets', 0)}` |")
    add("")
    add("W04 admission blockers:")
    add("")
    for blocker in getattr(result.admission, "blockers", ()) or ():
        add(
            f"- `{blocker.code}` ({blocker.stage}) — {blocker.detail}"
        )
    add("")
    add("## 2. Evidence inventory and independence")
    add("")
    add("| Item | Value |")
    add("|---|---|")
    add(f"| Rows | {len(result.capture.rows)} |")
    add(f"| Boot sessions | {len({row.boot_id for row in result.capture.rows})} |")
    add(f"| Source run-id labels | {len(run.run_ids)} ({', '.join(run.run_ids) or 'none'}) |")
    add(f"| Source run labels create independent runs? | NO — one boot session |")
    add(f"| Phase segments | {len(result.phases)} |")
    add(f"| Undetermined phase rows | {sum(p.rows for p in result.phases if p.phase == PHASE_UNDETERMINED)} |")
    add(f"| Independent physical sources | {result.repeatability.independent_physical_sources} |")
    add(f"| Qualified independent runs | {result.repeatability.qualified_independent_runs} |")
    add(f"| Diagnostic phase records | {result.repeatability.diagnostic_phase_records} |")
    add(f"| Duplicate source views | {result.repeatability.duplicate_views} |")
    add("")
    add(
        f"The {len(run.run_ids)} raw `run_id` label(s) are segments inside one boot. "
        "They do not establish independent runs, and the phase segments inside that "
        "boot do not establish experimental repetitions."
    )
    add("")
    add("## 3. Temperature representations and physical roles")
    add("")
    add("| Representation | Kind | Slots | Physical roles | Includes hot side | Available |")
    add("|---|---|---|---|---|---|")
    for name, representation in sorted(result.representations.items()):
        add(
            f"| `{name}` | {representation.kind} | "
            f"{', '.join(representation.slots) or '—'} | "
            f"{', '.join(representation.positions)} | "
            f"{'YES' if representation.includes_hot_side else 'no'} | "
            f"{'yes' if representation.available else 'NO'} |"
        )
    add("")
    add(
        "Primary diagnostic representation: "
        f"`{primary}` = mean of the role-qualified chamber-air probes."
    )
    add(
        "`tmean_chamber3_v0` is the literal docs/01 §20.1 slot expression and "
        "averages T2 hot-side metal into an air temperature on this hardware. It "
        "is published only as a named non-air cross-check, never as chamber air."
    )
    add("")
    add("## 4. Phase segmentation")
    add("")
    add("| Phase | Index | Rows | Start (s) | End (s) | Run ids | Independent experiment | Reasons |")
    add("|---|---|---|---|---|---|---|---|")
    for phase in result.phases:
        add(
            f"| {phase.phase} | {phase.phase_index} | {phase.rows} | "
            f"{_fmt(phase.start_s, 3)} | {_fmt(phase.end_s, 3)} | "
            f"{', '.join(phase.run_ids) or '—'} | "
            f"{'yes' if phase.independent_experiment else 'NO'} | "
            f"{', '.join(phase.reason_codes)} |"
        )
    add("")
    add("Boundaries come from the applied-duty state (with the device-reported")
    add("applied label as a consistency check), not from filenames, desired")
    add("commands or ACKs. A missing applied state would be `UNDETERMINED` and")
    add("would join no phase; it is never converted to OFF.")
    add("")
    add("## 5. Phase metrics")
    add("")
    add("All temperatures are °C, slopes °C/min, power W, energy Wh. Time is")
    add("boot-relative `device_ms`; no cross-boot alignment and no interpolation")
    add("across missing or untrusted windows.")
    add("")
    add("| Metric | PASSIVE_WARMUP | COOLING_STEP | POST_ACTION_RECOVERY |")
    add("|---|---|---|---|")
    for name in (
        "start_c",
        "end_c",
        "delta_c",
        "min_c",
        "max_c",
        "whole_phase_slope_c_per_min",
        "trailing_slope_c_per_min",
        "minutes_to_1c",
        "minutes_to_2c",
        "initial_spread_c",
        "spread_median_c",
        "duration_min",
        "mean_power_w",
        "peak_power_w",
        "sampled_energy_wh",
        "counter_delta_wh",
        "valid_sample_fraction",
    ):
        add(
            f"| `{name}` | {_fmt(_metric_value(warmup, name))} | "
            f"{_fmt(_metric_value(cooling, name))} | "
            f"{_fmt(_metric_value(recovery, name))} |"
        )
    add("")
    add("Quartiles and percentiles use the configured method (`linear` by default,")
    add("linear interpolation between closest ranks; `nearest_rank` is the alternative).")
    add("")
    add("Additional per-phase facts:")
    add("")
    add("| Fact | PASSIVE_WARMUP | COOLING_STEP | POST_ACTION_RECOVERY |")
    add("|---|---|---|---|")
    for name in (
        "rows",
        "usable_rows",
        "skipped_rows",
        "quality_valid_rows",
        "quality_unqualified_rows",
        "overall_quality_invalid_rows",
        "initial_probes_c",
        "end_probes_c",
        "amplitude_direction",
        "representation",
        "trailing_slope_definition",
        "ambient_first_c",
        "ambient_mean_c",
        "ambient_min_c",
        "ambient_max_c",
        "rh_first_pct",
        "rh_mean_pct",
        "cooling_on_rows",
        "applied_duty_min_permille",
        "applied_duty_max_permille",
        "applied_duty_mean_permille",
        "requested_mismatch_rows",
        "cadence_median_s",
        "cadence_p95_s",
        "long_gap_count",
        "electrical_qualification",
        "environment_qualification",
        "censoring",
        "qualification",
    ):
        values = []
        for metric in (warmup, cooling, recovery):
            if metric is None:
                values.append("—")
            elif name == "amplitude_direction":
                values.append(metric.excursion_direction)
            elif name == "representation":
                values.append(f"`{metric.representation}`")
            elif name == "trailing_slope_definition":
                values.append(f"`{metric.trailing_slope_definition}`")
            elif name in ("initial_probes_c", "end_probes_c"):
                probes = getattr(metric, name)
                values.append(
                    ", ".join(
                        f"{slot}={_fmt(value)}" for slot, value in probes
                    )
                    or "—"
                )
            else:
                values.append(_fmt(getattr(metric, name)))
        add(f"| `{name}` | {values[0]} | {values[1]} | {values[2]} |")
    add("")
    add("Slope discipline: the trailing-window slope is a separate diagnostic and")
    add("is not a phase summary. On the cooling step the trailing slope")
    add(
        f"({_fmt(_metric_value(cooling, 'trailing_slope_c_per_min'))} °C/min) differs "
        f"from the whole-phase slope ({_fmt(_metric_value(cooling, 'whole_phase_slope_c_per_min'))} °C/min)."
    )
    add("")
    add("## 6. External cross-check against A's W07 references")
    add("")
    if result.cross_check:
        add("| Phase | Field | A reference | B computed | Unit | Status | Detail |")
        add("|---|---|---|---|---|---|---|")
        for row in result.cross_check:
            add(
                f"| {row.phase} | `{row.field}` | {_fmt(row.reference_value)} | "
                f"{_fmt(row.computed_value)} | {row.unit} | {row.status} | {row.detail} |"
            )
        add("")
        add("A's numbers are external read-only cross-check targets; B's values")
        add("above are independently computed from the W04 normalized capture.")
    else:
        add("No A W07 reference bundle was supplied to this run.")
    add("")
    add("## 7. Electrical diagnostics and source anomaly")
    add("")
    add(
        "Electrical qualification is **UNQUALIFIED** in this capture: no electrical "
        "column carries a recorded OK. Numeric electrical summaries are "
        "diagnostic-only. No qualified energy envelope, COP or whole-system power "
        "claim is made. An OFF command is not proof of measured zero current."
    )
    add("")
    add("| Phase | Mean current A | Peak current A | Mean power W | Peak power W | Sampled energy Wh (diagnostic) | Counter delta Wh (diagnostic) |")
    add("|---|---|---|---|---|---|---|")
    for metric in (warmup, cooling, recovery):
        if metric is None:
            continue
        add(
            f"| {metric.phase} | {_fmt(metric.mean_current_a)} | {_fmt(metric.peak_current_a)} | "
            f"{_fmt(metric.mean_power_w)} | {_fmt(metric.peak_power_w)} | "
            f"{_fmt(metric.sampled_energy_wh)} | {_fmt(metric.counter_delta_wh)} |"
        )
    add("")
    if result.anomalies:
        add("Source anomaly retained (not averaged away):")
        add("")
        for anomaly in result.anomalies:
            add(
                f"- `device_ms={anomaly.device_ms}` seq {anomaly.seq}: applied state "
                f"`{anomaly.applied_state}` with duty {anomaly.applied_duty_permille} permille, "
                f"yet {_fmt(anomaly.current_a)} A / {_fmt(anomaly.power_w)} W. "
                f"Classification: `{anomaly.classification}`. "
                f"Competing explanation: {anomaly.competing_explanation} "
                f"Resolution: {anomaly.resolution}"
            )
        add("")
    else:
        add("No OFF-state current/power candidate was detected.")
        add("")
    add("## 8. Repeatability")
    add("")
    add(f"**Verdict: `{result.repeatability.verdict}`**")
    add("")
    add("| Field | Value |")
    add("|---|---|")
    add(f"| Minimum independent runs (A-W07) | {result.repeatability.min_independent_runs} |")
    add(f"| Independent physical sources | {result.repeatability.independent_physical_sources} |")
    add(f"| Qualified independent runs | {result.repeatability.qualified_independent_runs} |")
    add(f"| Excluded records | {result.repeatability.excluded_records} |")
    add(f"| Duplicate source views | {result.repeatability.duplicate_views} |")
    add(f"| Reason codes | {', '.join(result.repeatability.reason_codes)} |")
    add("")
    add(
        f"No SD, IQR or CV is reported as between-run repeatability from the "
        f"{len(result.capture.rows)} telemetry rows or from the "
        f"{result.repeatability.diagnostic_phase_records} diagnostic phase record(s). "
        "A single session's within-run variation is **not** a run-to-run variance estimate."
    )
    add("")
    add("The complete per-phase/per-metric table, including undefined reasons and")
    add("denominators, is `repeatability-summary.csv`. Synthetic positive controls")
    add("used by the tests are never inserted into this physical report.")
    add("")
    add("## 9. Confounding-variable inventory")
    add("")
    add("| Factor | Status | Evidence | Source field | Quality | Owner | Note |")
    add("|---|---|---|---|---|---|---|")
    for entry in result.confounders:
        add(
            f"| {entry.factor} | {entry.status} | {entry.evidence} | "
            f"{entry.source_field} | {entry.quality} | {entry.owner} | {entry.note} |"
        )
    add("")
    add(
        "Because no certified independent repeated runs exist, run-to-run "
        "confounding cannot be quantified. Unmeasured factors are marked rather "
        "than assigned artificial variability."
    )
    add("")
    add("## 10. Pairing candidate variables")
    add("")
    add("See `ml/pairing-candidate-variables.md` (generated by the same run). It")
    add("distinguishes matching variables, outcomes, measured covariates, protocol")
    add("constraints and unavailable variables. No numeric tolerance is claimed.")
    add("")
    add("## 11. Limitations and external dependencies")
    add("")
    add(
        f"- {len({row.boot_id for row in result.capture.rows})} boot session(s), "
        f"{len(run.run_ids)} source run-id label(s) and {len(result.phases)} phase segment(s); "
        "no independent experimental repetition exists."
    )
    add(
        f"- W04 admission is `{getattr(result.admission.status, 'value', result.admission.status)}`; "
        f"the highest stage is `{getattr(result.admission.highest_stage, 'value', result.admission.highest_stage)}`."
    )
    add("- Device identity is not carried; run identity is unresolved; hardware")
    add("  configuration is declared, not verified; calibration identity is absent.")
    add("- Sensor positions are operator-frozen evidence, not an independent ROM")
    add("  readback, installed-geometry measurement or calibration.")
    add("- A-W07-01 remains PARTIAL: V1 position, cable paths, door alignment,")
    add("  internal load, conductor/termination evidence and the configuration")
    add("  photo/drawing are not frozen in the committed evidence.")
    add("- Door state and ambient environment are unqualified; electrical values are")
    add("  unqualified.")
    add("- The canonical docs/01 §20.1 `mean(T1,T2,T3)` naming disagrees with the")
    add("  as-built rig; this report uses role-qualified naming and publishes the")
    add("  literal expression only as a named non-air cross-check.")
    add("- No physical action, no Controller A/B comparison, no model training and no")
    add("  W08–W12 implementation is performed or claimed.")
    add("")
    add("## 12. Reproduce")
    add("")
    add("```bash")
    add(generation_command)
    add("```")
    add("")
    add("Repeated execution against the same source and configuration produces")
    add("identical analytical content; the manifest records the source SHA-256, the")
    add("analysis code SHA-256, the estimator settings and artifact hashes.")
    add("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Deterministic diagnostic SVG
# ---------------------------------------------------------------------------


def _esc(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _svg_polylines(
    points: Sequence[tuple[float | None, float | None]],
    xmap: Any,
    ymap: Any,
    *,
    gap_s: float = 5.0,
) -> list[str]:
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    previous_time: float | None = None
    for time_s, value in points:
        if time_s is None or value is None:
            if current:
                segments.append(current)
                current = []
            previous_time = None
            continue
        if previous_time is not None and time_s - previous_time > gap_s:
            if current:
                segments.append(current)
                current = []
        current.append((xmap(time_s), ymap(value)))
        previous_time = time_s
    if current:
        segments.append(current)
    return [
        " ".join(f"{x:.2f},{y:.2f}" for x, y in segment)
        for segment in segments
        if len(segment) >= 2
    ]


def render_plant_svg(result: PlantEDAResult) -> str:
    """Deterministic multi-panel diagnostic trace; no independent-run overlay."""
    capture = result.capture
    rows = capture.rows
    primary = result.representations[result.config.representation]
    air_slots = list(primary.slots)
    hot_slots = list(capture.hot_side_slots)
    hot_slot = hot_slots[0] if hot_slots else "t2"
    times_min = [
        row.device_ms / 60000.0 for row in rows if row.device_ms is not None
    ]
    if not times_min:
        raise PlantEDAError("NO_DEVICE_TIME")
    t0 = min(times_min)
    t1 = max(times_min)
    width = 1200
    left = 78
    right = 28
    plot_w = width - left - right
    xmap = lambda value_min: left + (value_min - t0) / max(t1 - t0, 1e-9) * plot_w
    representation_points = []
    probe_points: dict[str, list[tuple[float | None, float | None]]] = {
        slot: [] for slot in [*air_slots, hot_slot]
    }
    all_values: list[float] = []
    for row in rows:
        time_min = None if row.device_ms is None else row.device_ms / 60000.0
        result_value = representation_value(capture, row, primary)
        representation_points.append((time_min, result_value.value_c))
        if result_value.value_c is not None:
            all_values.append(result_value.value_c)
        for slot in probe_points:
            try:
                probe = row.probe(slot)
                value = probe.value_c
            except KeyError:
                value = None
            probe_points[slot].append((time_min, value))
            if value is not None:
                all_values.append(value)
    if not all_values:
        raise PlantEDAError("NO_TEMPERATURE_VALUES")
    y_min = math.floor(min(all_values)) - 1
    y_max = math.ceil(max(all_values)) + 1
    ymap = lambda value: 300 - (value - y_min) / max(y_max - y_min, 1e-9) * 170
    hot_values = [
        value for _, value in probe_points.get(hot_slot, []) if value is not None
    ]
    hot_min = math.floor(min(hot_values)) - 1 if hot_values else 0
    hot_max = math.ceil(max(hot_values)) + 1 if hot_values else 1
    hot_map = lambda value: 455 - (value - hot_min) / max(hot_max - hot_min, 1e-9) * 100
    duties = [
        classify_applied_state(row).duty_permille for row in rows
    ]
    duty_max = max([value for value in duties if value is not None] + [0])
    duty_map = lambda value: 595 - (value / max(duty_max, 1)) * 80
    power_values = [row.cooling_power_w for row in rows if row.cooling_power_w is not None]
    power_max = max(power_values + [1.0])
    power_map = lambda value: 740 - (value / power_max) * 100
    phase_colors = {
        PHASE_PASSIVE_WARMUP: "#e9c46a",
        PHASE_COOLING_STEP: "#457b9d",
        PHASE_POST_ACTION_RECOVERY: "#2a9d8f",
        PHASE_UNDETERMINED: "#e63946",
    }
    svg: list[str] = []
    add = svg.append
    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="1180" '
        'viewBox="0 0 1200 1180">'
    )
    add('<rect width="1200" height="1180" fill="#ffffff"/>')
    add(
        '<text x="78" y="28" font-family="monospace" font-size="18" '
        'font-weight="bold">ColdGuard W07 plant EDA — diagnostic single-session trace</text>'
    )
    add(
        f'<text x="78" y="48" font-family="monospace" font-size="10" fill="#444">'
        f'source {_esc(capture.source.path)} · SHA-256 {_esc(capture.source.sha256[:16])}… · '
        f'representation {_esc(primary.name)} · boot {_esc(capture.run.boot_id)}</text>'
    )
    add(
        '<text x="78" y="64" font-family="monospace" font-size="10" fill="#b00020">'
        'DIAGNOSTIC ONLY · one boot session · phases are not independent runs · '
        f'repeatability {_esc(result.repeatability.verdict)}</text>'
    )
    for phase in result.phases:
        start_min = (phase.start_s or 0.0) / 60.0
        end_min = (phase.end_s or 0.0) / 60.0
        x0 = xmap(start_min)
        x1 = xmap(end_min)
        if x1 < x0:
            x0, x1 = x1, x0
        color = phase_colors.get(phase.phase, "#999999")
        shade_width = max(0.0, x1 - x0)
        add(
            f'<rect x="{x0:.2f}" y="100" width="{shade_width:.2f}" height="700" '
            f'fill="{color}" opacity="0.10"/>'
        )
        add(
            f'<text x="{(x0 + x1) / 2:.2f}" y="114" text-anchor="middle" '
            f'font-family="monospace" font-size="10" fill="#333">{_esc(phase.phase)}</text>'
        )
    # Panel 1: chamber air probes and mean.
    add('<text x="78" y="136" font-family="monospace" font-size="11" font-weight="bold">Chamber-air probes and role-qualified mean (°C)</text>')
    add(f'<line x1="{left}" y1="140" x2="{left + plot_w}" y2="140" stroke="#ddd"/>')
    probe_colors = {
        "t1": "#1f77b4",
        "t3": "#2ca02c",
        "t4": "#9467bd",
    }
    for slot in air_slots:
        for segment in _svg_polylines(probe_points[slot], xmap, ymap):
            add(
                f'<polyline points="{segment}" fill="none" stroke="{probe_colors.get(slot, "#666")}" '
                'stroke-width="1.2" opacity="0.85"/>'
            )
    for segment in _svg_polylines(representation_points, xmap, ymap):
        add(
            f'<polyline points="{segment}" fill="none" stroke="#111111" '
            'stroke-width="2.2"/>'
        )
    add('<text x="78" y="296" font-family="monospace" font-size="9" fill="#666">T1 centre · T3 bottom · T4 near door · black = role-qualified mean</text>')
    # Panel 2: hot side.
    add('<text x="78" y="330" font-family="monospace" font-size="11" font-weight="bold">TEC hot side T2 (°C) — never chamber air</text>')
    for segment in _svg_polylines(probe_points.get(hot_slot, []), xmap, hot_map):
        add(
            f'<polyline points="{segment}" fill="none" stroke="#d62728" '
            'stroke-width="1.6"/>'
        )
    add('<text x="78" y="468" font-family="monospace" font-size="9" fill="#666">kept on a separate axis and never averaged into chamber air</text>')
    # Panel 3: applied duty.
    add('<text x="78" y="500" font-family="monospace" font-size="11" font-weight="bold">Applied duty (permille) and phase state</text>')
    duty_points: list[tuple[float | None, float | None]] = []
    for row, duty in zip(rows, duties):
        time_min = None if row.device_ms is None else row.device_ms / 60000.0
        duty_points.append((time_min, None if duty is None else float(duty)))
    for segment in _svg_polylines(duty_points, xmap, duty_map):
        add(
            f'<polyline points="{segment}" fill="none" stroke="#ff7f0e" '
            'stroke-width="1.8"/>'
        )
    add('<text x="78" y="608" font-family="monospace" font-size="9" fill="#666">requested differs from applied on cooling rows; applied state is device-reported, not command proof</text>')
    # Panel 4: electrical.
    add('<text x="78" y="638" font-family="monospace" font-size="11" font-weight="bold">Cooling-branch power (W) — UNQUALIFIED electrical source</text>')
    power_points = [
        (None if row.device_ms is None else row.device_ms / 60000.0, row.cooling_power_w)
        for row in rows
    ]
    for segment in _svg_polylines(power_points, xmap, power_map):
        add(
            f'<polyline points="{segment}" fill="none" stroke="#ff7f0e" '
            'stroke-width="1.2" stroke-dasharray="4,2"/>'
        )
    add(
        f'<text x="{left + plot_w - 4}" y="648" text-anchor="end" '
        'font-family="monospace" font-size="11" fill="#b00020">UNQUALIFIED — diagnostic only; no COP / whole-system claim</text>'
    )
    for anomaly in result.anomalies:
        if anomaly.device_ms is None:
            continue
        x = xmap(anomaly.device_ms / 60000.0)
        add(
            f'<line x1="{x:.2f}" y1="630" x2="{x:.2f}" y2="750" '
            'stroke="#b00020" stroke-width="1" stroke-dasharray="3,3"/>'
        )
        add(
            f'<text x="{x + 3:.2f}" y="755" font-family="monospace" font-size="9" '
            'fill="#b00020">OFF-state power frame</text>'
        )
    # Panel 5: door and quality.
    add('<text x="78" y="790" font-family="monospace" font-size="11" font-weight="bold">Door state and quality markings (door quality unqualified)</text>')
    for index, row in enumerate(rows):
        if row.device_ms is None:
            continue
        next_time = (
            rows[index + 1].device_ms
            if index + 1 < len(rows) and rows[index + 1].device_ms is not None
            else row.device_ms + 1000
        )
        x0 = xmap(row.device_ms / 60000.0)
        x1 = xmap(next_time / 60000.0)
        color = {"CLOSED": "#2a9d8f", "OPEN": "#e76f51", "UNKNOWN": "#9e9e9e"}.get(
            row.door_state, "#9e9e9e"
        )
        door_width = max(0.5, x1 - x0)
        add(
            f'<rect x="{x0:.2f}" y="800" width="{door_width:.2f}" height="10" '
            f'fill="{color}" opacity="0.45"/>'
        )
        if row.overall_quality == "INVALID":
            add(
                f'<rect x="{x0:.2f}" y="812" width="{door_width:.2f}" height="4" '
                'fill="#b00020" opacity="0.7"/>'
            )
    add('<text x="78" y="835" font-family="monospace" font-size="9" fill="#666">green CLOSED · grey UNKNOWN · red bar = overall INVALID row</text>')
    # Panel 6: phase-relative trajectories.
    add('<text x="78" y="880" font-family="monospace" font-size="11" font-weight="bold">Phase-relative chamber-air mean (each phase normalised to its own duration)</text>')
    by_phase = {}
    for metric in result.metrics:
        points = []
        phase = result.phases[metric.phase_index]
        phase_rows = rows[phase.start_row_index : phase.end_row_index]
        for row in phase_rows:
            value = representation_value(capture, row, primary).value_c
            if value is not None and row.device_ms is not None:
                points.append((row.device_ms / 1000.0, value))
        if len(points) >= 2:
            by_phase[f"{metric.phase}#{metric.phase_index}"] = (metric.phase, points)
    relative_values = [
        value
        for _, points in by_phase.values()
        for _, value in points
    ]
    if not relative_values:
        relative_values = all_values
    relative_y_min = math.floor(min(relative_values)) - 1
    relative_y_max = math.ceil(max(relative_values)) + 1
    rel_y = lambda value: 1040 - (value - relative_y_min) / max(relative_y_max - relative_y_min, 1e-9) * 120
    rel_x = lambda fraction: left + fraction * plot_w
    for _, (phase_name, points) in sorted(by_phase.items()):
        start = points[0][0]
        end = points[-1][0]
        coords = [
            (rel_x((time_s - start) / max(end - start, 1e-9)), rel_y(value))
            for time_s, value in points
        ]
        polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)
        add(
            f'<polyline points="{polyline}" fill="none" '
            f'stroke="{phase_colors.get(phase_name, "#333")}" stroke-width="1.6"/>'
        )
    add('<text x="78" y="1058" font-family="monospace" font-size="9" fill="#666">one diagnostic session; phases overlay for comparison, not independent-run repeatability</text>')
    add(
        '<text x="78" y="1095" font-family="monospace" font-size="10" fill="#333">'
        f'Phases: {len(result.phases)} · independent physical sources: '
        f'{result.repeatability.independent_physical_sources} · qualified independent runs: '
        f'{result.repeatability.qualified_independent_runs} · repeatability: '
        f'{_esc(result.repeatability.verdict)}</text>'
    )
    add(
        '<text x="78" y="1115" font-family="monospace" font-size="10" fill="#b00020">'
        'No fabricated overlay of independent runs. No interpolation across gaps. '
        'No hot-side-in-chamber-air averaging.</text>'
    )
    add("</svg>")
    return "\n".join(svg)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def build_manifest(
    result: PlantEDAResult,
    *,
    code_sha256: str,
    repository_revision: str,
    generation_command: str,
    artifact_sha256: dict[str, str],
) -> str:
    payload = {
        "schema": PLANT_EDA_MANIFEST_SCHEMA,
        "layer_version": PLANT_EDA_LAYER_VERSION,
        "analysis_code_sha256": code_sha256,
        "repository_revision": repository_revision,
        "generation_command": generation_command,
        "artifact_sha256": dict(sorted(artifact_sha256.items())),
        **result.to_dict(),
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
