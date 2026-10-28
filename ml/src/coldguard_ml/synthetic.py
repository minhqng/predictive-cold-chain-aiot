"""Deterministic synthetic run generator (B-W02-01).

Purpose (``05B`` §30, Doc ``04`` §17-B): produce small, reproducible
synthetic fixtures for PIPELINE CORRECTNESS ONLY — grouped splitting,
causal windowing, horizon labels. Synthetic output:

* is **not** physical evidence: every run manifest carries
  ``synthetic: true`` plus an explicit non-measurement note
  (data-dictionary-v0 §11 fixture rule), and no generated value is
  presented as a calibrated physical measurement;
* follows the W01 dictionary field semantics exactly, so downstream code
  cannot special-case fixtures: canonical sample identity
  ``(device_id, boot_id, seq)``, UTC event time, boot-scoped sequence
  restarts, per-section quality evaluation, ``None`` for absent channels
  (never 0), ``UNKNOWN`` door kept distinct from ``CLOSED``;
* prescribes critical/fault events EXPLICITLY by config offset — the
  generator never derives a critical event from the synthetic temperature
  curve (a synthetic threshold cannot be a hardware contract);
* varies meaningfully across the canonical scenario vocabulary (Doc ``03``
  §31): S1 NORMAL_BASELINE, S2 DOOR_DISTURBANCE, S3
  THERMAL_EFFECTIVENESS_DEGRADATION, S4 ACTUATION_RESPONSE_FAULT, S5
  CONNECTIVITY_LOSS, S6 SENSOR/OBSERVATION_DEGRADED;
* needs an explicit ``seed`` per run (convention §11: the seed a step
  consumes is recorded on the consuming object).
"""

from __future__ import annotations

import datetime as _dt
import enum
import random as _pyrandom
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from .errors import DataContractError
from .labels import CriticalEvent, CriticalEventSeries
from .observations import Observation, TIMEZONE_UTC, event_time_to_rfc3339, validate_observation

__all__ = [
    "TrajectoryShape",
    "SyntheticRunSpec",
    "SyntheticRun",
    "SCENARIO_NAME_BY_ID",
    "build_synthetic_run",
    "build_synthetic_runs",
    "build_synthetic_dataset",
    "SYNTHETIC_NOTE",
    "DEFAULT_SYNTHETIC_START",
]

SCENARIO_NAME_BY_ID: dict[str, str] = {
    "S1": "NORMAL_BASELINE",
    "S2": "DOOR_DISTURBANCE",
    "S3": "THERMAL_EFFECTIVENESS_DEGRADATION",
    "S4": "ACTUATION_RESPONSE_FAULT",
    "S5": "CONNECTIVITY_LOSS",
    "S6": "SENSOR/OBSERVATION_DEGRADED",
}

SYNTHETIC_NOTE = (
    "SYNTHETIC synthetic-harness fixture (B-W02-01) — not a physical "
    "measurement; values are illustrative pipeline-test data."
)

DEFAULT_SYNTHETIC_START = "2026-01-01T00:00:00Z"

_START_EPOCH = _dt.datetime(2026, 1, 1, tzinfo=TIMEZONE_UTC)


class TrajectoryShape(enum.Enum):
    """Illustrative thermal-trend families for the synthetic curves."""

    STABLE = "stable"  # S1-like nominal
    RISING = "rising"  # warming trend
    BUMP_RECOVERY = "bump-recovery"  # disturbance then recovery (S2-like)


_DEFAULT_SPEC_CONFIG = {
    "S1": {"shape": TrajectoryShape.STABLE},
    "S2": {
        "shape": TrajectoryShape.BUMP_RECOVERY,
        "door_offset_s": 30.0,
        "door_duration_s": 20.0,
    },
    "S3": {
        # Thermal-effectiveness degradation: warming trend + missing t2
        # (DEGRADED thermal section) after the degrade point. The weakened
        # cooling pull-down is expressed by the RISING trend itself — never
        # by deriving an event from the curve.
        "shape": TrajectoryShape.RISING,
        "thermal_degrade_after_s": 40.0,
    },
    "S4": {"shape": TrajectoryShape.RISING, "actuation_fault": True},
    "S5": {"shape": TrajectoryShape.STABLE, "connectivity_loss_after_s": 40.0},
    "S6": {
        "shape": TrajectoryShape.STABLE,
        "thermal_degrade_after_s": 40.0,
        "electrical_absent_after_s": 60.0,
        "door_unknown_after_s": 50.0,
    },
}


@dataclass(frozen=True)
class SyntheticRunSpec:
    """Explicit, reproducible configuration for one synthetic run.

    Exactness rules: ``seed`` is mandatory; scenario ids are the canonical
    S1–S6 vocabulary; prescribed event/door offsets are explicit; all
    degrade knobs default to a healthy, complete run unless listed.
    """

    run_id: str
    scenario_id: str
    seed: int
    controller_id: str = "CONTROLLER-A"
    pair_id: str | None = None
    device_id: str = "coldguard-001"
    hardware_config_id: str = "CG-HW-001"
    firmware_version: str = "fw-synthetic-v0"
    calibration_id: str | None = None
    schema_version: int = 1

    start_time: str | _dt.datetime | None = None  # RFC3339 UTC or tz-aware datetime
    duration_s: float = 90.0
    sample_interval_s: float = 1.0
    boot_sessions: int = 1
    boot_gap_s: float = 5.0  # wall pause between boot sessions (seq/uptime restart)

    shape: TrajectoryShape | None = None  # default: canonical scenario mapping

    # Prescribed label series inputs (NEVER derived from trajectory values)
    critical_event_offset_s: float | None = None
    untrusted_event_offset_s: float | None = None

    # Disturbance/actuation/degradation plan (None = scenario default;
    # an explicit bool always wins so callers can enable/disable faults)
    door_offset_s: float | None = None
    door_duration_s: float | None = None
    door_unknown_after_s: float | None = None
    actuation_fault: bool | None = None
    thermal_degrade_after_s: float | None = None  # t2 None, DEGRADED quality afterward
    thermal_invalid_after_s: float | None = None  # probes None, INVALID quality afterward
    electrical_absent_after_s: float | None = None  # PZEM gap: None + INVALID (LRK-14)
    connectivity_loss_after_s: float | None = None  # S5: no samples in the loss span
    connectivity_loss_until_s: float | None = None

    def __post_init__(self) -> None:
        if not (isinstance(self.seed, int) and not isinstance(self.seed, bool)):
            raise DataContractError(
                f"spec {self.run_id!r}: seed must be an explicit integer "
                "(convention §11 seed policy)"
            )
        if self.scenario_id not in SCENARIO_NAME_BY_ID:
            raise DataContractError(
                f"spec {self.run_id!r}: scenario_id must be one of "
                f"{sorted(SCENARIO_NAME_BY_ID)} (Doc `03` §31), got {self.scenario_id!r}"
            )
        if not self.controller_id:
            raise DataContractError(f"spec {self.run_id!r}: controller_id must be non-empty")
        if self.duration_s <= 0:
            raise DataContractError(f"spec {self.run_id!r}: duration_s must be > 0")
        if self.sample_interval_s <= 0:
            raise DataContractError(f"spec {self.run_id!r}: sample_interval_s must be > 0")
        if self.boot_sessions < 1:
            raise DataContractError(f"spec {self.run_id!r}: boot_sessions must be >= 1")
        if self.boot_gap_s < 0:
            raise DataContractError(f"spec {self.run_id!r}: boot_gap_s must be >= 0")
        for name in ("critical_event_offset_s", "untrusted_event_offset_s"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise DataContractError(
                    f"spec {self.run_id!r}: {name} must be >= 0 (prescribed event within "
                    "the recorded trajectory)"
                )
        for name in (
            "critical_event_offset_s",
            "untrusted_event_offset_s",
            "door_offset_s",
            "door_unknown_after_s",
            "thermal_degrade_after_s",
            "thermal_invalid_after_s",
            "electrical_absent_after_s",
        ):
            value = getattr(self, name)
            if value is not None and value > self.duration_s:
                raise DataContractError(
                    f"spec {self.run_id!r}: {name} falls beyond the recorded trajectory "
                    f"duration ({value} > {self.duration_s}); prescribe events/degradation "
                    "inside the run horizon"
                )
        if (self.door_offset_s is None) != (self.door_duration_s is None):
            raise DataContractError(
                f"spec {self.run_id!r}: door_offset_s and door_duration_s "
                "are a pair — an open door without a close time (or vice versa) is "
                "not representable (data-dictionary-v0 §6)"
            )
        if self.door_duration_s is not None and self.door_duration_s <= 0:
            raise DataContractError(f"spec {self.run_id!r}: door_duration_s must be > 0")


@dataclass(frozen=True)
class SyntheticRun:
    """One generated synthetic run with its manifest and label-series inputs."""

    spec: SyntheticRunSpec
    observations: tuple[Observation, ...]
    run_manifest: dict[str, Any]
    critical_series: CriticalEventSeries

    @property
    def run_id(self) -> str:
        return self.spec.run_id

    @property
    def observations_by_boot(self) -> dict[tuple[str, str], tuple[Observation, ...]]:
        grouped: dict[tuple[str, str], list[Observation]] = {}
        for row in self.observations:
            grouped.setdefault(row.trajectory_key, []).append(row)
        return {key: tuple(rows) for key, rows in sorted(grouped.items())}


def _resolve_start(spec: SyntheticRunSpec) -> _dt.datetime:
    if spec.start_time is None:
        return _START_EPOCH
    if isinstance(spec.start_time, _dt.datetime):
        if spec.start_time.tzinfo is None:
            raise DataContractError(
                f"spec {spec.run_id!r}: start_time must be timezone-aware"
            )
        return spec.start_time.astimezone(TIMEZONE_UTC)
    return _dt.datetime.fromisoformat(spec.start_time.replace("Z", "+00:00")).astimezone(
        TIMEZONE_UTC
    )


def _effective_plan(spec: SyntheticRunSpec) -> dict[str, Any]:
    """Scenario-driven defaults plus explicit overrides (Doc `03` §31 semantics)."""
    defaults = _DEFAULT_SPEC_CONFIG.get(spec.scenario_id, {})
    plan: dict[str, Any] = dict(defaults)
    for key in (
        "shape",
        "door_offset_s",
        "door_duration_s",
        "door_unknown_after_s",
        "actuation_fault",
        "thermal_degrade_after_s",
        "thermal_invalid_after_s",
        "electrical_absent_after_s",
        "connectivity_loss_after_s",
    ):
        explicit = getattr(spec, key)
        if explicit is not None:
            plan[key] = explicit
    plan.setdefault("shape", TrajectoryShape.STABLE)
    return plan


def build_synthetic_run(spec: SyntheticRunSpec) -> SyntheticRun:
    """Generate one deterministic synthetic run from an explicit spec."""
    started = _resolve_start(spec)
    plan = _effective_plan(spec)
    interval = spec.sample_interval_s
    segment_s = spec.duration_s / spec.boot_sessions

    rng = np.random.default_rng(spec.seed)
    jitter = _pyrandom.Random(f"{spec.seed}|{spec.run_id}")

    rows: list[Observation] = []
    boot_summaries: list[dict[str, Any]] = []
    energy_wh = 0.0
    wall = started

    # Thermal curve constants (illustrative, NOT a physical model).
    base_c = 20.0
    rise_rate = 0.05 if plan["shape"] in (TrajectoryShape.RISING,) else 0.01
    bump_peak_c = 4.0

    plan_shape: TrajectoryShape = plan["shape"]
    door_offset = plan.get("door_offset_s")
    door_duration = plan.get("door_duration_s")
    connectivity_from = plan.get("connectivity_loss_after_s")
    connectivity_until = spec.connectivity_loss_until_s or (
        (connectivity_from + 0.35 * spec.duration_s) if connectivity_from is not None else None
    )

    cooling = "OFF"
    duty: float | None = None
    faults = plan.get("actuation_fault", False)

    for session in range(spec.boot_sessions):
        session_start = wall
        session_end = session_start + _dt.timedelta(seconds=segment_s)
        # Boot identity is globally unique: (device_id, boot_id, seq) is the
        # corpus-wide physical-sample identity (§1.2), so a synthetic boot
        # encodes its run — run-local boot numbers alone would collide the
        # moment two runs share the rig's device_id.
        boot_id = f"{spec.run_id}-boot-{session + 1:03d}"
        session_rows: list[Observation] = []
        k_local = 0
        while wall < session_end:
            elapsed = (wall - started).total_seconds()
            if (
                connectivity_from is not None
                and connectivity_until is not None
                and connectivity_from <= elapsed < connectivity_until
            ):
                # S5 CONNECTIVITY_LOSS: the loss span is recorded absence —
                # no samples, no fabricated values, no interpolation.
                wall += _dt.timedelta(seconds=interval)
                continue
            seq = k_local
            uptime_ms = int(round((wall - session_start).total_seconds() * 1000.0))

            elapsed_float = elapsed
            # --- illustrative thermal curve ---------------------------------
            if plan_shape is TrajectoryShape.STABLE:
                trend = 0.15 * float(np.sin(2.0 * np.pi * seq / 60.0))
            elif plan_shape is TrajectoryShape.RISING:
                trend = rise_rate * elapsed_float
                if door_offset is not None and elapsed_float >= door_offset:
                    trend += 0.02 * (elapsed_float - door_offset)
            else:  # BUMP_RECOVERY
                trend = rise_rate * elapsed_float
                if door_offset is not None and elapsed_float >= door_offset:
                    trend += bump_peak_c * float(
                        np.exp(-max(elapsed_float - door_offset, 0.0) / 30.0)
                    )
                if faults:
                    trend += 0.01 * elapsed_float
            physical_noise = float(rng.normal(0.0, 0.05))
            t_mean = base_c + trend + physical_noise
            t1 = t_mean + 0.10 + float(rng.normal(0.0, 0.02))
            t2 = t_mean - 0.05 + float(rng.normal(0.0, 0.02))
            t3 = t_mean - 0.15 + float(rng.normal(0.0, 0.02))

            thermal_quality = "VALID"
            degrade_after = plan.get("thermal_degrade_after_s")
            if degrade_after is not None and elapsed_float >= degrade_after:
                thermal_quality = "DEGRADED"
                t2 = None
            if (
                invalidate_after := spec.thermal_invalid_after_s
            ) is not None and elapsed_float >= invalidate_after:
                thermal_quality = "INVALID"
                t1 = t2 = t3 = None

            t_air = base_c + 0.5 + float(rng.normal(0.0, 0.1))
            rh = 45.0 + float(rng.normal(0.0, 0.4))
            environment_quality = "VALID"
            if degrade_after is not None and elapsed_float >= degrade_after:
                rh = None
                environment_quality = "DEGRADED"

            # --- door state --------------------------------------------------
            door_state = "CLOSED"
            if (
                door_offset is not None
                and door_duration is not None
                and door_offset <= elapsed_float < door_offset + door_duration
            ):
                door_state = "OPEN"
            unknown_after_effective = (
                spec.door_unknown_after_s
                if spec.door_unknown_after_s is not None
                else plan.get("door_unknown_after_s")
            )
            if unknown_after_effective is not None and elapsed_float >= unknown_after_effective:
                door_state = "UNKNOWN"

            # --- actuation + electrical --------------------------------------
            if elapsed_float < 30.0:
                cooling = "OFF"
                duty = None
            else:
                cooling = "ON"
                duty = 0.6 if plan_shape is TrajectoryShape.STABLE else 0.8
            if door_state == "OPEN":
                cooling = "ON"
                duty = 0.9

            voltage = 12.0 + float(rng.normal(0.0, 0.05))
            if faults:
                current = 0.02 + float(rng.normal(0.0, 0.005))
                power = 0.25 + float(rng.normal(0.0, 0.05))
            else:
                if cooling == "ON" and duty is not None:
                    current = duty * 8.0 + float(rng.normal(0.0, 0.05))
                    power = voltage * current * 0.9
                else:
                    current = 0.01 + abs(float(rng.normal(0.0, 0.003)))
                    power = voltage * current
            electrical_quality = "VALID"
            absent_after_effective = (
                spec.electrical_absent_after_s
                if spec.electrical_absent_after_s is not None
                else plan.get("electrical_absent_after_s")
            )
            if absent_after_effective is not None and elapsed_float >= absent_after_effective:
                voltage = current = power = None
                electrical_quality = "INVALID"

            energy_wh += (power or 0.0) * interval / 3600.0
            counter = energy_wh if electrical_quality == "VALID" else None

            section_qualities = [thermal_quality, environment_quality, electrical_quality]
            overall = (
                "INVALID"
                if "INVALID" in section_qualities
                else ("DEGRADED" if "DEGRADED" in section_qualities else "VALID")
            )
            device_mode = (
                "ONLINE_NORMAL" if overall == "VALID" else "ONLINE_DEGRADED"
            )

            observation = Observation(
                device_id=spec.device_id,
                boot_id=boot_id,
                seq=seq,
                time=wall,
                uptime_ms=uptime_ms,
                run_id=spec.run_id,
                t1_c=t1,
                t2_c=t2,
                t3_c=t3,
                t_air_c=t_air,
                rh_pct=rh,
                door_state=door_state,
                cooling_voltage_v=voltage,
                cooling_current_a=current,
                cooling_power_w=power,
                cooling_energy_counter_wh=counter,
                applied_cooling=cooling,
                applied_duty=duty,
                thermal_quality=thermal_quality,
                environment_quality=environment_quality,
                electrical_quality=electrical_quality,
                overall_quality=overall,
                device_mode=device_mode,
                schema_version=spec.schema_version,
                hardware_config_id=spec.hardware_config_id,
                firmware_version=spec.firmware_version,
                calibration_id=spec.calibration_id,
                backend_received_at=wall + _dt.timedelta(milliseconds=jitter.randint(5, 80)),
            )
            validate_observation(observation)
            session_rows.append(observation)
            k_local += 1
            wall += _dt.timedelta(seconds=interval)

        if session_rows:
            boot_summaries.append(
                {
                    "boot_id": boot_id,
                    "n_observations": len(session_rows),
                    "first_time": event_time_to_rfc3339(session_rows[0].time),
                    "last_time": event_time_to_rfc3339(session_rows[-1].time),
                }
            )
            rows.extend(session_rows)
        # Wall-clock pause between power-on sessions (clock state restarts).
        wall = session_end + _dt.timedelta(seconds=spec.boot_gap_s)

    if not rows:
        raise DataContractError(
            f"spec {spec.run_id!r}: configuration produced zero observations "
            "(e.g. sample_interval_s > duration_s)"
        )

    events: list[CriticalEvent] = []
    if spec.critical_event_offset_s is not None:
        events.append(
            CriticalEvent(
                time=started + _dt.timedelta(seconds=spec.critical_event_offset_s),
                trusted=True,
                ref=f"prescribed:{spec.run_id}",
            )
        )
    if spec.untrusted_event_offset_s is not None:
        events.append(
            CriticalEvent(
                time=started + _dt.timedelta(seconds=spec.untrusted_event_offset_s),
                trusted=False,
                ref=f"prescribed-untrusted:{spec.run_id}",
            )
        )
    series = CriticalEventSeries(
        run_id=spec.run_id,
        events=tuple(events),
        series_id=f"synthetic-prescribed-series:{spec.run_id}:v0",
        coverage_end=rows[-1].time,
    )

    manifest = _run_manifest(spec, rows, boot_summaries)
    return SyntheticRun(
        spec=spec,
        observations=tuple(rows),
        run_manifest=manifest,
        critical_series=series,
    )


def _run_manifest(
    spec: SyntheticRunSpec, rows: tuple[Observation, ...], boots: list[dict[str, Any]]
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "run_id": spec.run_id,
        "scenario_id": spec.scenario_id,
        "controller_id": spec.controller_id,
        "pair_id": spec.pair_id,
        "device_id": spec.device_id,
        "hardware_config_id": spec.hardware_config_id,
        "firmware_version": spec.firmware_version,
        "calibration_id": spec.calibration_id,
        "schema_version": spec.schema_version,
        "is_valid": True,
        "invalid_reason": None,
        "synthetic": True,
        "seed": spec.seed,
        "boots": boots,
        "start_time": event_time_to_rfc3339(rows[0].time),
        "end_time": event_time_to_rfc3339(rows[-1].time),
        "note": SYNTHETIC_NOTE,
    }
    return manifest


def build_synthetic_runs(specs: Iterable[SyntheticRunSpec]) -> tuple[SyntheticRun, ...]:
    """Build runs in canonical (sorted run_id) order — deterministic."""
    built = [build_synthetic_run(spec) for spec in specs]
    built.sort(key=lambda run: run.run_id)
    return tuple(built)


def build_synthetic_dataset(
    runs: Iterable[SyntheticRun],
    dataset_id: str,
    *,
    git_commit: str,
    created_at: _dt.datetime | None = None,
    created_by: str = "member-b",
) -> tuple[dict[str, Any], tuple[SyntheticRun, ...]]:
    """Assemble the artifact-convention §3.1 dataset manifest for synthetic runs.

    ``synthetic: true`` is propagated (B7): a synthetic dataset stays
    synthetic end to end, so fixture content can never merge into a
    research dataset. ``git_commit`` is mandatory (convention §5.4:
    provenance for every manifest) and ``created_at`` should be passed
    explicitly for deterministic replay of the manifest payload.
    """
    run_list = tuple(sorted(runs, key=lambda item: item.run_id))
    if not run_list:
        raise DataContractError("synthetic dataset requires at least one run")
    if not isinstance(git_commit, str) or not git_commit.strip():
        raise DataContractError(
            "dataset manifest requires a non-empty git_commit "
            "(artifact-convention §5.4 provenance rule)"
        )
    hardware_configs = sorted({run.spec.hardware_config_id for run in run_list})
    calibration_ids = sorted({run.spec.calibration_id for run in run_list if run.spec.calibration_id})
    manifest = {
        "dataset_id": dataset_id,
        "source_runs": [run.run_id for run in run_list],
        "hardware_configs": hardware_configs,
        "schema_version": 1,
        "calibration_ids": calibration_ids,
        "export_query_hash": None,  # synthetic fixture: no dataset export query
        "created_at": event_time_to_rfc3339(created_at) if created_at else None,
        "created_by": created_by,
        "git_commit": git_commit,
        "status": "draft",
        "content_sha256": None,  # draft artifact: content hash is minted at lock time (§4)
        "synthetic": True,
    }
    return manifest, run_list
