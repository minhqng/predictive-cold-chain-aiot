"""W10 causal feature and door-state tests (B-W10-02 / B-W10-03)."""

from __future__ import annotations

import dataclasses
import datetime as _dt
from pathlib import Path

import pytest

from coldguard_ml.feature_fixtures import (
    build_development_dataset,
    build_gap_trajectory,
    build_irregular_trajectory,
    build_quality_degraded_trajectory,
    build_trajectory,
)
from coldguard_ml.feature_pipeline import (
    MISSING_ELECTRICAL_UNQUALIFIED,
    MISSING_GAP,
    MISSING_INPUT,
    MISSING_NO_OBSERVED_TRANSITION,
    MISSING_POLARITY_UNATTESTED,
    MISSING_QUALITY,
    MISSING_UNKNOWN_DOOR,
    PRESENT,
    ELIGIBILITY_SYNTHETIC,
    SOURCE_TYPE_SYNTHETIC,
    TIME_DOMAIN_ABSOLUTE_UTC,
    PipelineSample,
    Trajectory,
    door_snapshots,
    feature_rows,
    trajectory_from_capture,
    trajectory_from_observations,
)
from coldguard_ml.feature_registry import load_registry
from coldguard_ml.observations import IdentityContradictionError
from coldguard_ml.synthetic import SyntheticRunSpec, build_synthetic_run

REGISTRY = load_registry()
INDEX = {feature.feature_id: i for i, feature in enumerate(REGISTRY.features)}
EVIDENCE = Path(__file__).resolve().parents[2] / "evidence" / "A" / "W09" / "exports" / "CG-S1-H8C-600S.json"


def _rows(trajectory, partition=None):
    return feature_rows(trajectory, REGISTRY, partition=partition)


def _at(rows, anchor):
    matches = [row for row in rows if row.anchor_t_s == anchor]
    assert len(matches) == 1
    return matches[0]


def _value(row, feature_id):
    return row.values[INDEX[feature_id]]


def _reason(row, feature_id):
    return row.missing_reasons[INDEX[feature_id]]


def _mutate_after(trajectory, anchor):
    mutated = []
    for sample in trajectory.samples:
        if sample.time_s > anchor:
            sample = dataclasses.replace(
                sample,
                chamber_c=tuple(
                    (role, None if value is None else value + 5.0)
                    for role, value in sample.chamber_c
                ),
                hot_side_c=None if sample.hot_side_c is None else sample.hot_side_c + 5.0,
                door_state="OPEN",
                applied_cooling="OFF",
                applied_duty=0.0,
                cooling_power_w=None,
                electrical_quality="INVALID",
            )
        mutated.append(sample)
    return dataclasses.replace(trajectory, samples=tuple(mutated))


def _custom_trajectory(door_states, *, boot_id="B1", run_id="CG-CUSTOM-001", attested=True):
    samples = []
    for index, (time_s, state) in enumerate(door_states):
        samples.append(
            PipelineSample(
                device_id="cg-synthetic-001",
                boot_id=boot_id,
                seq=index,
                time_s=float(time_s),
                chamber_c=(
                    ("CHAMBER_CENTER", 5.0),
                    ("CHAMBER_BOTTOM", 4.8),
                    ("CHAMBER_NEAR_DOOR", 5.3),
                ),
                hot_side_c=11.0,
                thermal_quality="VALID",
                door_state=state,
                door_quality="VALID" if state != "UNKNOWN" else "UNKNOWN",
                door_polarity_attested=attested,
                applied_cooling="ON",
                applied_duty=0.5,
                requested_duty_permille=500,
                readback_duty_permille=500,
                cooling_voltage_v=12.0,
                cooling_current_a=4.0,
                cooling_power_w=48.0,
                cooling_energy_counter_wh=0.0,
                electrical_quality="VALID",
                t_air_c=22.0,
                rh_pct=45.0,
                environment_quality="VALID",
                overall_quality="VALID",
            )
        )
    return Trajectory(
        run_id=run_id,
        boot_id=boot_id,
        device_id="cg-synthetic-001",
        scenario_id="S2",
        controller_id="CONTROLLER-A",
        source_sha256="c" * 64,
        source_type=SOURCE_TYPE_SYNTHETIC,
        clock_domain=TIME_DOMAIN_ABSOLUTE_UTC,
        origin_utc="2026-01-01T00:00:00Z",
        physical_source_key=f"{'c'*64}:{boot_id}",
        samples=tuple(samples),
        physical_eligibility=ELIGIBILITY_SYNTHETIC,
        exclusion_reasons=(),
    )


def test_future_mutation_does_not_change_past_features():
    trajectory, _ = build_trajectory(
        "CG-S2-FUT-001",
        scenario="S2",
        seed=401,
        door_start_s=40.0,
        critical_offsets_s=(80.0,),
    )
    baseline = _rows(trajectory)
    mutated = _rows(_mutate_after(trajectory, 60.0))
    past = [row for row in baseline if row.anchor_t_s <= 60.0]
    mutated_past = [row for row in mutated if row.anchor_t_s <= 60.0]
    assert len(past) == len(mutated_past) == 61
    for left, right in zip(past, mutated_past):
        assert left.values == right.values
        assert left.missing_reasons == right.missing_reasons


def test_future_truncation_preserves_past_features():
    trajectory, _ = build_trajectory(
        "CG-S2-TRUNC-001",
        scenario="S2",
        seed=402,
        door_start_s=40.0,
    )
    baseline = _rows(trajectory)
    truncated = dataclasses.replace(
        trajectory,
        samples=tuple(sample for sample in trajectory.samples if sample.time_s <= 60.0),
    )
    truncated_rows = _rows(truncated)
    for left, right in zip(
        [row for row in baseline if row.anchor_t_s <= 60.0], truncated_rows
    ):
        assert left.anchor_t_s == right.anchor_t_s
        assert left.values == right.values
        assert left.missing_reasons == right.missing_reasons
    assert len(truncated_rows) == 61


def test_rolling_uses_actual_event_time_not_sample_count():
    trajectory, _ = build_irregular_trajectory()
    row = _at(_rows(trajectory), 100.0)
    assert _reason(row, "rolling_mean_temperature_60s") == PRESENT
    assert _value(row, "rolling_mean_temperature_60s") == pytest.approx(
        5.757666666666666, abs=1e-12
    )
    assert _value(row, "past_only_slope_c_per_min_60s") == pytest.approx(0.6, abs=1e-12)
    contributing = [
        (5.0 + 0.03333333333333333 + sample.time_s / 100.0)
        for sample in trajectory.samples
        if 40.0 < sample.time_s <= 100.0
    ]
    sample_count_mean = sum(contributing) / len(contributing)
    assert abs(sample_count_mean - _value(row, "rolling_mean_temperature_60s")) > 1e-4


def test_rolling_first_value_requires_full_history():
    trajectory, _ = build_trajectory(
        "CG-S2-FIRST-001",
        scenario="S2",
        seed=403,
        door_start_s=40.0,
    )
    rows = _rows(trajectory)
    assert all(
        _reason(row, "rolling_mean_temperature_60s") == "MISSING_INSUFFICIENT_HISTORY"
        for row in rows
        if row.anchor_t_s < 60.0
    )
    assert _reason(_at(rows, 59.0), "rolling_mean_temperature_60s") == (
        "MISSING_INSUFFICIENT_HISTORY"
    )
    assert _reason(_at(rows, 60.0), "rolling_mean_temperature_60s") == PRESENT


def test_gap_blocks_rolling_features():
    trajectory, _ = build_gap_trajectory()
    rows = _rows(trajectory)
    for anchor in (80.0, 100.0, 120.0):
        row = [item for item in rows if item.anchor_t_s == anchor]
        if not row:
            continue
        assert _reason(row[0], "rolling_mean_temperature_60s") == MISSING_GAP


def test_quality_degradation_blocks_thermal_and_electrical_features():
    trajectory, _ = build_quality_degraded_trajectory()
    rows = _rows(trajectory)
    row = _at(rows, 80.0)
    assert _reason(row, "T_chamber_mean_c") == MISSING_QUALITY
    assert _reason(row, "rolling_mean_temperature_60s") == MISSING_QUALITY
    assert _reason(row, "cooling_power_w") == MISSING_ELECTRICAL_UNQUALIFIED
    assert _reason(row, "ambient_temperature_c") == "MISSING_ENVIRONMENT_UNQUALIFIED"


def test_counter_reset_is_not_silently_integrated():
    reset, _ = build_trajectory(
        "CG-S2-RESET-001",
        scenario="S2",
        seed=404,
        door_start_s=40.0,
        counter_reset_at_s=90.0,
    )
    clean, _ = build_trajectory(
        "CG-S2-CLEAN-001",
        scenario="S2",
        seed=404,
        door_start_s=40.0,
    )
    reset_row = _at(_rows(reset), 90.0)
    clean_row = _at(_rows(clean), 90.0)
    assert _reason(clean_row, "energy_counter_wh") == PRESENT
    assert _reason(reset_row, "energy_counter_wh") == "MISSING_COUNTER_RESET"


def test_hot_side_is_not_in_the_chamber_mean():
    trajectory, _ = build_trajectory(
        "CG-S2-HOT-001",
        scenario="S2",
        seed=405,
        door_start_s=40.0,
    )
    row = _at(_rows(trajectory), 50.0)
    center = _value(row, "T_center_c")
    bottom = _value(row, "T_bottom_c")
    near = _value(row, "T_near_door_c")
    hot = _value(row, "T_tec_hot_side_c")
    assert _value(row, "T_chamber_mean_c") == pytest.approx((center + bottom + near) / 3)
    assert _value(row, "T_chamber_mean_c") != pytest.approx(
        (center + bottom + near + hot) / 4
    )


def test_missing_required_probe_blocks_aggregate():
    run = build_synthetic_run(SyntheticRunSpec(run_id="CG-SYN-ROLE-001", scenario_id="S1", seed=501))
    trajectories = trajectory_from_observations(
        run.observations,
        source_sha256="d" * 64,
        synthetic_roles={"t1": "CHAMBER_CENTER", "t3": "CHAMBER_BOTTOM"},
    )
    rows = _rows(trajectories[0])
    row = _at(rows, 10.0)
    assert _reason(row, "T_chamber_mean_c") == MISSING_INPUT
    assert _reason(row, "T_center_c") == PRESENT
    assert _reason(row, "T_bottom_c") == PRESENT
    assert _reason(row, "T_near_door_c") == MISSING_INPUT


def test_duplicate_delivery_is_idempotent_in_the_adapter():
    run = build_synthetic_run(SyntheticRunSpec(run_id="CG-SYN-DUP-001", scenario_id="S1", seed=502))
    duplicated = tuple(run.observations) + (run.observations[5],)
    clean = trajectory_from_observations(
        run.observations, source_sha256="e" * 64, synthetic_roles={"t1": "CHAMBER_CENTER"}
    )[0]
    with_duplicate = trajectory_from_observations(
        duplicated, source_sha256="e" * 64, synthetic_roles={"t1": "CHAMBER_CENTER"}
    )[0]
    assert clean.samples == with_duplicate.samples
    assert len(clean.samples) == len(run.observations)


def test_contradictory_duplicate_sample_is_refused():
    run = build_synthetic_run(SyntheticRunSpec(run_id="CG-SYN-CON-001", scenario_id="S1", seed=503))
    conflicting = dataclasses.replace(run.observations[5], t1_c=99.0)
    with pytest.raises(IdentityContradictionError):
        trajectory_from_observations(
            tuple(run.observations) + (conflicting,),
            source_sha256="f" * 64,
            synthetic_roles={"t1": "CHAMBER_CENTER"},
        )


def test_boot_boundary_resets_rolling_history():
    run = build_synthetic_run(
        SyntheticRunSpec(
            run_id="CG-SYN-BOOT-001",
            scenario_id="S1",
            seed=504,
            duration_s=140.0,
            boot_sessions=2,
            boot_gap_s=5.0,
        )
    )
    trajectories = trajectory_from_observations(
        run.observations, source_sha256="a" * 64, synthetic_roles={"t1": "CHAMBER_CENTER"}
    )
    assert len(trajectories) == 2
    for trajectory in trajectories:
        rows = _rows(trajectory)
        assert rows[0].anchor_t_s == 0.0
        assert all(
            _reason(row, "rolling_mean_temperature_60s") == "MISSING_INSUFFICIENT_HISTORY"
            for row in rows
            if row.anchor_t_s < 60.0
        )
        assert _reason(_at(rows, 60.0), "rolling_mean_temperature_60s") in (
            PRESENT,
            MISSING_INPUT,
        )


def test_trusted_door_transition_and_duration():
    trajectory, _ = build_trajectory(
        "CG-S2-DOOR-001",
        scenario="S2",
        seed=406,
        door_start_s=40.0,
        door_duration_s=20.0,
    )
    rows = _rows(trajectory)
    at_open = _at(rows, 40.0)
    assert _value(at_open, "door_open") == 1.0
    assert _value(at_open, "duration_so_far") == 0.0
    assert _value(at_open, "time_since_open") == 0.0
    at_ten = _at(rows, 50.0)
    assert _value(at_ten, "duration_so_far") == 10.0
    assert _value(at_ten, "time_since_open") == 10.0


def test_unknown_door_is_missing_and_never_closed():
    trajectory, _ = build_trajectory(
        "CG-S2-UNK-001",
        scenario="S2",
        seed=407,
        door_start_s=40.0,
        unknown_start_s=80.0,
        unknown_duration_s=3.0,
    )
    rows = _rows(trajectory)
    for anchor in (80.0, 81.0, 82.0):
        row = _at(rows, anchor)
        assert _reason(row, "door_open") == MISSING_UNKNOWN_DOOR
        assert _reason(row, "duration_so_far") == MISSING_UNKNOWN_DOOR
        assert _value(row, "time_since_open") == anchor - 40.0


def test_initial_open_without_edge_is_missing_duration():
    trajectory = _custom_trajectory([(0, "OPEN"), (1, "OPEN"), (2, "CLOSED")])
    row = _at(_rows(trajectory), 1.0)
    assert _value(row, "door_open") == 1.0
    assert _reason(row, "duration_so_far") == MISSING_NO_OBSERVED_TRANSITION
    assert _reason(row, "time_since_open") == MISSING_NO_OBSERVED_TRANSITION


def test_unknown_interruption_breaks_open_continuity():
    trajectory = _custom_trajectory(
        [(0, "CLOSED"), (1, "OPEN"), (2, "OPEN"), (3, "UNKNOWN"), (4, "OPEN"), (5, "OPEN")]
    )
    rows = _rows(trajectory)
    assert _value(_at(rows, 2.0), "duration_so_far") == 1.0
    assert _reason(_at(rows, 3.0), "duration_so_far") == MISSING_UNKNOWN_DOOR
    after = _at(rows, 4.0)
    assert _value(after, "door_open") == 1.0
    assert _reason(after, "duration_so_far") == MISSING_NO_OBSERVED_TRANSITION


def test_duplicate_open_samples_do_not_create_extra_transitions():
    trajectory = _custom_trajectory(
        [(0, "CLOSED"), (10, "OPEN"), (11, "OPEN"), (12, "OPEN"), (13, "CLOSED")]
    )
    rows = _rows(trajectory)
    assert _value(_at(rows, 12.0), "count_past_60s") == 1


def test_opening_count_boundary_is_open_left_closed_right():
    trajectory = _custom_trajectory(
        [(0, "CLOSED"), (10, "OPEN"), (20, "CLOSED"), (70, "OPEN"), (130, "CLOSED")]
    )
    rows = _rows(trajectory)
    assert _value(_at(rows, 70.0), "count_past_60s") == 1
    assert _value(_at(rows, 130.0), "count_past_60s") == 0


def test_future_close_does_not_change_past_duration():
    trajectory, _ = build_trajectory(
        "CG-S2-FUTCLOSE-001",
        scenario="S2",
        seed=408,
        door_start_s=40.0,
        door_duration_s=20.0,
    )
    baseline = _at(_rows(trajectory), 50.0)
    mutated = _at(_rows(_mutate_after(trajectory, 50.0)), 50.0)
    assert _value(baseline, "duration_so_far") == 10.0
    assert _value(mutated, "duration_so_far") == 10.0
    assert _value(baseline, "time_since_open") == 10.0
    assert _value(mutated, "time_since_open") == 10.0


def test_missing_polarity_attestation_blocks_door_features():
    trajectory, _ = build_trajectory(
        "CG-S2-POL-001",
        scenario="S2",
        seed=409,
        door_start_s=40.0,
        door_polarity_attested=False,
    )
    rows = _rows(trajectory)
    for anchor in (0.0, 50.0, 100.0):
        row = _at(rows, anchor)
        assert _reason(row, "door_open") == MISSING_POLARITY_UNATTESTED
        assert _reason(row, "duration_so_far") == MISSING_POLARITY_UNATTESTED
        assert _reason(row, "time_since_open") == MISSING_NO_OBSERVED_TRANSITION


def test_cross_boot_door_continuity_is_refused():
    first = _custom_trajectory([(0, "CLOSED"), (10, "OPEN")], boot_id="B1")
    second = _custom_trajectory([(0, "OPEN"), (5, "OPEN")], boot_id="B2")
    rows_first = _rows(first)
    rows_second = _rows(second)
    assert _value(_at(rows_first, 10.0), "door_open") == 1.0
    after_reboot = _at(rows_second, 5.0)
    assert _value(after_reboot, "door_open") == 1.0
    assert _reason(after_reboot, "duration_so_far") == MISSING_NO_OBSERVED_TRANSITION
    assert _reason(after_reboot, "time_since_open") == MISSING_NO_OBSERVED_TRANSITION


def test_real_w09_capture_produces_no_fabricated_door_openings():
    from coldguard_ml import load_capture

    capture = load_capture(EVIDENCE)
    trajectories = trajectory_from_capture(capture)
    assert len(trajectories) == 1
    trajectory = trajectories[0]
    rows = _rows(trajectory)
    for row in rows:
        assert _reason(row, "door_open") in (
            MISSING_QUALITY,
            MISSING_POLARITY_UNATTESTED,
            MISSING_UNKNOWN_DOOR,
        )
        assert _reason(row, "duration_so_far") != PRESENT
        assert _reason(row, "time_since_open") != PRESENT
    transitions = [
        snapshot
        for snapshot in door_snapshots(trajectory.samples)
        if snapshot.opening_times
    ]
    assert transitions == []


def test_requested_applied_readback_are_distinct_and_measured_zero_is_not_missing():
    trajectory, _ = build_trajectory(
        "CG-S2-ACT-001",
        scenario="S2",
        seed=410,
        door_start_s=40.0,
    )
    samples = list(trajectory.samples)
    samples[50] = dataclasses.replace(
        samples[50],
        requested_duty_permille=0,
        readback_duty_permille=0,
        applied_cooling="ON",
        applied_duty=0.5,
        cooling_power_w=0.0,
    )
    custom = dataclasses.replace(trajectory, samples=tuple(samples))
    row = _at(_rows(custom), 50.0)
    assert _value(row, "requested_cooling") == 0.0
    assert _value(row, "applied_cooling") == 1.0
    assert _value(row, "readback_cooling") == 0.0
    assert _value(row, "applied_duty") == 0.5
    assert _value(row, "cooling_power_w") == 0.0
    assert _reason(row, "cooling_power_w") == PRESENT

    missing_power = dataclasses.replace(
        custom,
        samples=tuple(
            dataclasses.replace(sample, cooling_power_w=None)
            if sample.time_s == 50.0
            else sample
            for sample in custom.samples
        ),
    )
    missing_row = _at(_rows(missing_power), 50.0)
    assert _reason(missing_row, "cooling_power_w") == MISSING_INPUT
    assert _value(missing_row, "cooling_power_w") is None


def test_invalid_thermal_segment_blocks_thermal_features():
    trajectory, _ = build_trajectory(
        "CG-S2-INV-001",
        scenario="S2",
        seed=411,
        door_start_s=40.0,
    )
    samples = list(trajectory.samples)
    samples[70] = dataclasses.replace(
        samples[70],
        thermal_quality="INVALID",
        chamber_c=tuple((role, None) for role, _ in samples[70].chamber_c),
        hot_side_c=None,
    )
    custom = dataclasses.replace(trajectory, samples=tuple(samples))
    row = _at(_rows(custom), 70.0)
    assert _reason(row, "T_chamber_mean_c") == MISSING_QUALITY
    assert _reason(row, "T_tec_hot_side_c") == MISSING_QUALITY
    assert _reason(row, "rolling_mean_temperature_60s") == MISSING_QUALITY


def test_same_run_different_sources_never_share_history():
    first = _custom_trajectory(
        [(time_s, "CLOSED") for time_s in range(0, 121)], run_id="CG-SAME-001"
    )
    second = dataclasses.replace(
        _custom_trajectory(
            [(0, "CLOSED"), (1, "CLOSED")], run_id="CG-SAME-001", boot_id="B2"
        ),
        source_sha256="9" * 64,
        physical_source_key=f"{'9'*64}:B2",
    )
    first_rows = _rows(first)
    second_rows = _rows(second)
    assert _reason(_at(first_rows, 120.0), "rolling_mean_temperature_60s") == PRESENT
    assert _reason(_at(second_rows, 1.0), "rolling_mean_temperature_60s") == (
        "MISSING_INSUFFICIENT_HISTORY"
    )


def test_arrival_order_does_not_change_canonical_samples():
    run = build_synthetic_run(SyntheticRunSpec(run_id="CG-SYN-ORDER-001", scenario_id="S1", seed=505))
    forward = trajectory_from_observations(
        run.observations, source_sha256="8" * 64, synthetic_roles={"t1": "CHAMBER_CENTER"}
    )[0]
    backward = trajectory_from_observations(
        tuple(reversed(run.observations)),
        source_sha256="8" * 64,
        synthetic_roles={"t1": "CHAMBER_CENTER"},
    )[0]
    assert forward.samples == backward.samples


def test_unsupported_synthetic_scenario_is_refused():
    from coldguard_ml.feature_fixtures import FixtureError

    with pytest.raises(FixtureError, match="S1/S2"):
        build_trajectory("CG-S3-X-001", scenario="S3", seed=506)


def test_inconsistent_clock_domain_is_refused():
    from coldguard_ml.feature_pipeline import FeaturePipelineError

    trajectory, _ = build_trajectory(
        "CG-S2-CLOCK-001", scenario="S2", seed=507, door_start_s=40.0
    )
    with pytest.raises(FeaturePipelineError, match="boot-scoped"):
        dataclasses.replace(
            trajectory,
            clock_domain="BOOT_SCOPED_UPTIME",
            origin_utc="2026-01-01T00:00:00Z",
        )
    with pytest.raises(FeaturePipelineError, match="absolute-time"):
        dataclasses.replace(
            trajectory, clock_domain="UTC_ABSOLUTE", origin_utc=None
        )
    with pytest.raises(FeaturePipelineError, match="unknown clock domain"):
        dataclasses.replace(trajectory, clock_domain="LOCAL_WALL_CLOCK")
