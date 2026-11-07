"""Deterministic software-only W10 fixtures.

These trajectories exist to exercise the feature pipeline and label pilot.
They carry no physical authority: no threshold, disturbance or critical event
here is evidence about the real plant. Every row is labelled
``SYNTHETIC_FIXTURE`` and every output class is ``SYNTHETIC_FEATURE_TEST``.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import math
from dataclasses import dataclass

from .labels import CriticalEvent, CriticalEventSeries
from .splitting import RunInfo, SplitConfig, SplitProportions, SplitResult, split_runs
from .feature_pipeline import (
    ELIGIBILITY_SYNTHETIC,
    SOURCE_TYPE_SYNTHETIC,
    TIME_DOMAIN_ABSOLUTE_UTC,
    PipelineSample,
    Trajectory,
    _dedupe_samples,
)

FIXTURE_VERSION = "coldguard-w10-synthetic-s2-v1"
FIXTURE_ORIGIN = "2026-01-01T00:00:00Z"
SYNTHETIC_DEVICE_ID = "cg-synthetic-001"
SYNTHETIC_CONTROLLER = "CONTROLLER-A"
PREDICTIVE_CONTROLLER = "CONTROLLER-B-PREDICTIVE"


class FixtureError(ValueError):
    pass


@dataclass(frozen=True)
class SyntheticDataset:
    fixture_version: str
    trajectories: tuple[Trajectory, ...]
    series_by_run: dict[str, CriticalEventSeries]
    split: SplitResult
    origin: str

    def trajectory(self, run_id: str) -> Trajectory:
        for item in self.trajectories:
            if item.run_id == run_id:
                return item
        raise KeyError(run_id)

    def partition_of(self, run_id: str) -> str:
        partition = self.split.partition_of(run_id)
        if partition is None:
            raise FixtureError(f"run {run_id!r} is not partitioned")
        return partition


def _origin() -> _dt.datetime:
    return _dt.datetime.fromisoformat(FIXTURE_ORIGIN.replace("Z", "+00:00"))


def _quality(thermal: str, electrical: str, environment: str) -> str:
    values = (thermal, electrical, environment)
    if "INVALID" in values:
        return "INVALID"
    if "DEGRADED" in values:
        return "DEGRADED"
    return "VALID"


def _thermal(t: float, *, scenario: str, door_start: float, door_duration: float, seed: int) -> float:
    phase = (seed % 7) * 0.013
    base = 5.0 + (seed % 3) * 0.05
    wobble = 0.05 * math.sin(2.0 * math.pi * t / 60.0 + phase)
    if scenario != "S2":
        return base + wobble
    door_end = door_start + door_duration
    if t < door_start:
        return base + wobble
    if t < door_end:
        return base + 0.08 * (t - door_start) + wobble
    return (
        base
        + 0.08 * door_duration * math.exp(-(t - door_end) / 20.0)
        + 1.2 * math.exp(-(t - door_end) / 25.0)
        + wobble
    )


def build_trajectory(
    run_id: str,
    *,
    scenario: str,
    seed: int,
    controller_id: str = SYNTHETIC_CONTROLLER,
    duration_s: float = 120.0,
    door_start_s: float | None = None,
    door_duration_s: float = 20.0,
    unknown_start_s: float | None = None,
    unknown_duration_s: float = 3.0,
    critical_offsets_s: tuple[float, ...] = (),
    degrade_after_s: float | None = None,
    gap_start_s: float | None = None,
    gap_end_s: float | None = None,
    counter_reset_at_s: float | None = None,
    door_polarity_attested: bool = True,
) -> tuple[Trajectory, CriticalEventSeries]:
    if scenario not in ("S1", "S2"):
        raise FixtureError("synthetic fixtures cover S1/S2 only")
    if scenario == "S2" and door_start_s is None:
        raise FixtureError("an S2 fixture requires a prescribed door opening")
    if scenario == "S1" and door_start_s is not None:
        raise FixtureError("an S1 fixture must not carry a door opening")
    if scenario == "S1" and critical_offsets_s:
        raise FixtureError("an S1 fixture must not carry a critical event")
    for offset in critical_offsets_s:
        if offset < 0 or offset > duration_s:
            raise FixtureError(
                f"critical offset {offset!r} falls outside the fixture duration"
            )
    if door_start_s is not None and not (0 <= door_start_s < duration_s):
        raise FixtureError("door start must fall inside the fixture duration")
    if unknown_start_s is not None and not (0 <= unknown_start_s < duration_s):
        raise FixtureError("unknown-door start must fall inside the fixture duration")
    origin = _origin()
    source_sha256 = hashlib.sha256(
        f"{FIXTURE_VERSION}:{run_id}:{scenario}:{seed}".encode("utf-8")
    ).hexdigest()
    boot_id = f"{run_id}-BOOT-1"
    samples: list[PipelineSample] = []
    counter = 0.0
    for second in range(int(duration_s) + 1):
        t = float(second)
        if (
            gap_start_s is not None
            and gap_end_s is not None
            and gap_start_s <= t < gap_end_s
        ):
            continue
        temp = _thermal(
            t,
            scenario=scenario,
            door_start=door_start_s or 0.0,
            door_duration=door_duration_s,
            seed=seed,
        )
        door_open = (
            scenario == "S2"
            and door_start_s is not None
            and door_start_s <= t < door_start_s + door_duration_s
        )
        door_state = "OPEN" if door_open else "CLOSED"
        if (
            unknown_start_s is not None
            and unknown_start_s <= t < unknown_start_s + unknown_duration_s
        ):
            door_state = "UNKNOWN"

        thermal_quality = "VALID"
        center = temp
        bottom = temp - 0.2
        near_door = temp + (0.8 if door_open else 0.3)
        if degrade_after_s is not None and t >= degrade_after_s:
            thermal_quality = "DEGRADED"
            near_door = None

        applied = "ON" if t >= 30.0 else "OFF"
        duty = 0.7 if applied == "ON" else None
        voltage = 12.0 + 0.05 * math.sin(t / 9.0)
        current = (duty or 0.02) * 8.0
        power = voltage * current * 0.9
        counter += power / 3600.0
        if counter_reset_at_s is not None and t >= counter_reset_at_s:
            counter = max(counter - 5.0, 0.0)

        electrical_quality = "VALID"
        if degrade_after_s is not None and t >= degrade_after_s:
            electrical_quality = "INVALID"
            voltage = current = power = None
            counter_value = None
        else:
            counter_value = round(counter, 9)

        environment_quality = "VALID"
        t_air = 22.0 + 0.2 * math.sin(t / 30.0)
        rh = 45.0 + 0.5 * math.cos(t / 40.0)
        if degrade_after_s is not None and t >= degrade_after_s:
            environment_quality = "DEGRADED"
            rh = None

        overall = _quality(thermal_quality, electrical_quality, environment_quality)
        samples.append(
            PipelineSample(
                device_id=SYNTHETIC_DEVICE_ID,
                boot_id=boot_id,
                seq=second,
                time_s=t,
                chamber_c=(
                    ("CHAMBER_CENTER", center),
                    ("CHAMBER_BOTTOM", bottom),
                    ("CHAMBER_NEAR_DOOR", near_door),
                ),
                hot_side_c=temp + 6.0,
                thermal_quality=thermal_quality,
                door_state=door_state,
                door_quality="VALID" if door_state != "UNKNOWN" else "UNKNOWN",
                door_polarity_attested=door_polarity_attested,
                applied_cooling=applied,
                applied_duty=duty,
                requested_duty_permille=700 if applied == "ON" else 0,
                readback_duty_permille=700 if applied == "ON" else 0,
                cooling_voltage_v=voltage,
                cooling_current_a=current,
                cooling_power_w=power,
                cooling_energy_counter_wh=counter_value,
                electrical_quality=electrical_quality,
                t_air_c=t_air,
                rh_pct=rh,
                environment_quality=environment_quality,
                overall_quality=overall,
            )
        )
    if not samples:
        raise FixtureError(f"fixture {run_id!r} produced no samples")
    trajectory = Trajectory(
        run_id=run_id,
        boot_id=boot_id,
        device_id=SYNTHETIC_DEVICE_ID,
        scenario_id=scenario,
        controller_id=controller_id,
        source_sha256=source_sha256,
        source_type=SOURCE_TYPE_SYNTHETIC,
        clock_domain=TIME_DOMAIN_ABSOLUTE_UTC,
        origin_utc=FIXTURE_ORIGIN,
        physical_source_key=f"{source_sha256}:{boot_id}",
        samples=_dedupe_samples(samples),
        physical_eligibility=ELIGIBILITY_SYNTHETIC,
        exclusion_reasons=(),
    )
    events = tuple(
        CriticalEvent(
            time=origin + _dt.timedelta(seconds=offset),
            trusted=True,
            ref=f"{run_id}:SYNTHETIC_PRESCRIBED:{offset:g}s",
        )
        for offset in critical_offsets_s
    )
    series = CriticalEventSeries(
        run_id=run_id,
        events=events,
        series_id=f"{FIXTURE_VERSION}:{run_id}",
        coverage_end=origin + _dt.timedelta(seconds=duration_s),
    )
    return trajectory, series


def build_development_dataset() -> SyntheticDataset:
    """Six paired runs: three S2 door disturbances and three S1 baselines."""
    pairs = (
        ("CG-S2-A-001", "CG-S1-A-001", 201, 101, "PAIR-001"),
        ("CG-S2-A-002", "CG-S1-A-002", 202, 102, "PAIR-002"),
        ("CG-S2-A-003", "CG-S1-A-003", 203, 103, "PAIR-003"),
    )
    trajectories: list[Trajectory] = []
    series_by_run: dict[str, CriticalEventSeries] = {}
    run_infos: list[RunInfo] = []
    for s2_run, s1_run, s2_seed, s1_seed, pair_id in pairs:
        s2, s2_series = build_trajectory(
            s2_run,
            scenario="S2",
            seed=s2_seed,
            door_start_s=40.0,
            door_duration_s=20.0,
            unknown_start_s=80.0,
            critical_offsets_s=(80.0,),
        )
        s1, s1_series = build_trajectory(
            s1_run, scenario="S1", seed=s1_seed
        )
        trajectories.extend((s2, s1))
        series_by_run[s2_run] = s2_series
        series_by_run[s1_run] = s1_series
        run_infos.extend(
            (
                RunInfo(
                    run_id=s2_run,
                    scenario_id="S2",
                    controller_id=SYNTHETIC_CONTROLLER,
                    pair_id=pair_id,
                    hardware_config_id="CG-HW-SYNTHETIC",
                ),
                RunInfo(
                    run_id=s1_run,
                    scenario_id="S1",
                    controller_id=SYNTHETIC_CONTROLLER,
                    pair_id=pair_id,
                    hardware_config_id="CG-HW-SYNTHETIC",
                ),
            )
        )
    split = split_runs(
        run_infos,
        SplitConfig(
            proportions=SplitProportions(1 / 3, 1 / 3, 1 / 3),
            seed=7,
            controller_context="all-reactive-or-observational",
            min_groups_per_partition=1,
            hardware_lineage="CG-HW-SYNTHETIC",
        ),
    )
    return SyntheticDataset(
        fixture_version=FIXTURE_VERSION,
        trajectories=tuple(sorted(trajectories, key=lambda item: item.run_id or "")),
        series_by_run=series_by_run,
        split=split,
        origin=FIXTURE_ORIGIN,
    )


def build_quality_degraded_trajectory(run_id: str = "CG-S2-QD-001") -> tuple[Trajectory, CriticalEventSeries]:
    return build_trajectory(
        run_id,
        scenario="S2",
        seed=301,
        door_start_s=40.0,
        door_duration_s=20.0,
        critical_offsets_s=(80.0,),
        degrade_after_s=70.0,
    )


def build_irregular_trajectory(run_id: str = "CG-S2-IRR-001") -> tuple[Trajectory, CriticalEventSeries]:
    """Irregular cadence with a 60 s lookback and hand-checkable values."""
    origin = _origin()
    source_sha256 = hashlib.sha256(f"{FIXTURE_VERSION}:{run_id}:irregular".encode("utf-8")).hexdigest()
    boot_id = f"{run_id}-BOOT-1"
    times = (0.0, 10.0, 20.0, 40.0, 45.0, 50.0, 55.0, 60.0, 61.0, 66.0, 71.0, 76.0, 81.0, 86.0, 91.0, 96.0, 100.0)
    samples = []
    for index, t in enumerate(times):
        value = 5.0 + t / 100.0
        samples.append(
            PipelineSample(
                device_id=SYNTHETIC_DEVICE_ID,
                boot_id=boot_id,
                seq=index,
                time_s=t,
                chamber_c=(
                    ("CHAMBER_CENTER", value),
                    ("CHAMBER_BOTTOM", value - 0.2),
                    ("CHAMBER_NEAR_DOOR", value + 0.3),
                ),
                hot_side_c=value + 6.0,
                thermal_quality="VALID",
                door_state="CLOSED",
                door_quality="VALID",
                door_polarity_attested=True,
                applied_cooling="ON",
                applied_duty=0.5,
                requested_duty_permille=500,
                readback_duty_permille=500,
                cooling_voltage_v=12.0,
                cooling_current_a=4.0,
                cooling_power_w=48.0,
                cooling_energy_counter_wh=round(48.0 * t / 3600.0, 9),
                electrical_quality="VALID",
                t_air_c=22.0,
                rh_pct=45.0,
                environment_quality="VALID",
                overall_quality="VALID",
            )
        )
    trajectory = Trajectory(
        run_id=run_id,
        boot_id=boot_id,
        device_id=SYNTHETIC_DEVICE_ID,
        scenario_id="S2",
        controller_id=SYNTHETIC_CONTROLLER,
        source_sha256=source_sha256,
        source_type=SOURCE_TYPE_SYNTHETIC,
        clock_domain=TIME_DOMAIN_ABSOLUTE_UTC,
        origin_utc=FIXTURE_ORIGIN,
        physical_source_key=f"{source_sha256}:{boot_id}",
        samples=tuple(samples),
        physical_eligibility=ELIGIBILITY_SYNTHETIC,
        exclusion_reasons=(),
    )
    series = CriticalEventSeries(
        run_id=run_id,
        events=(CriticalEvent(time=origin + _dt.timedelta(seconds=90.0), trusted=True),),
        series_id=f"{FIXTURE_VERSION}:{run_id}",
        coverage_end=origin + _dt.timedelta(seconds=100.0),
    )
    return trajectory, series


def build_gap_trajectory(run_id: str = "CG-S2-GAP-001") -> tuple[Trajectory, CriticalEventSeries]:
    return build_trajectory(
        run_id,
        scenario="S2",
        seed=302,
        door_start_s=40.0,
        door_duration_s=20.0,
        critical_offsets_s=(80.0,),
        gap_start_s=65.0,
        gap_end_s=73.0,
    )


def build_censored_trajectory(run_id: str = "CG-S2-CEN-001") -> tuple[Trajectory, CriticalEventSeries]:
    return build_trajectory(
        run_id,
        scenario="S2",
        seed=303,
        duration_s=100.0,
        door_start_s=40.0,
        door_duration_s=20.0,
        critical_offsets_s=(95.0,),
    )


def build_predictive_control_trajectory(run_id: str = "CG-S2-B-001") -> tuple[Trajectory, CriticalEventSeries]:
    return build_trajectory(
        run_id,
        scenario="S2",
        seed=304,
        door_start_s=40.0,
        door_duration_s=20.0,
        critical_offsets_s=(80.0,),
        controller_id=PREDICTIVE_CONTROLLER,
    )
