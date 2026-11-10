"""W15 adversarial tests for the A3 electrical/applied-state contrast."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from coldguard_ml.feature_fixtures import build_trajectory
from coldguard_ml.feature_pipeline import PipelineSample, Trajectory
from coldguard_ml.feature_registry import load_registry
from coldguard_ml.w14_ablation import W11_CONTEXT_FEATURES, population_identity
from coldguard_ml.w15_ablation import (
    A3_ELECTRICAL_FEATURES,
    A3A_EXPECTED_FEATURE_COUNT,
    A3B_EXPECTED_FEATURE_COUNT,
    RESPONSE_APPLIED_UNKNOWN,
    RESPONSE_APPLIED_WITHOUT_RESPONSE,
    RESPONSE_APPLIED_WITH_RESPONSE,
    RESPONSE_NO_COMMAND,
    RESPONSE_UNVERIFIABLE,
    RESPONSE_WITHOUT_COMMAND,
    A3ViewError,
    assess_actuator_electrical_response,
    build_a3_views,
    counter_reset_probe,
    electrical_block_invariance,
    electrical_feature_diagnostics,
    future_isolation_probe,
    transition_after_anchor_probe,
    unknown_electrical_probe,
    validate_a3_views,
)
from coldguard_ml.w14_ablation import build_ablation_dataset, compute_view_rows
from coldguard_ml.xgb_benchmark import (
    build_expanded_w11_fixture,
    load_benchmark_config,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = load_registry(ROOT / "feature-registry-v1.yaml")
CONFIG = load_benchmark_config(ROOT / "xgb-v1-config.yaml", REGISTRY)
FIXTURE = build_expanded_w11_fixture()
VIEWS = build_a3_views(REGISTRY, CONFIG)


def _mutate_sample(sample: PipelineSample, **changes) -> PipelineSample:
    return PipelineSample(**{**sample.__dict__, **changes})


def _mutate_trajectory(trajectory: Trajectory, transform) -> Trajectory:
    return Trajectory(
        **{
            **trajectory.__dict__,
            "samples": tuple(transform(sample) for sample in trajectory.samples),
        }
    )


@pytest.fixture(scope="module")
def datasets():
    return {
        arm: build_ablation_dataset(FIXTURE, REGISTRY, CONFIG, view)
        for arm, view in VIEWS.items()
    }


def test_a3_views_match_the_canonical_contrast_exactly():
    assert VIEWS["A3B"].feature_ids == CONFIG.feature_policy.allowlist
    assert VIEWS["A3B"].feature_count == A3B_EXPECTED_FEATURE_COUNT == 28
    assert VIEWS["A3A"].feature_count == A3A_EXPECTED_FEATURE_COUNT == 20
    assert tuple(
        feature_id
        for feature_id in VIEWS["A3B"].feature_ids
        if feature_id not in set(A3_ELECTRICAL_FEATURES)
    ) == VIEWS["A3A"].feature_ids
    validate_a3_views(VIEWS, REGISTRY, CONFIG)


def test_a3a_contains_no_electrical_or_actuation_input():
    assert not any(
        feature.family in ("electrical_context", "actuation_context")
        for feature in VIEWS["A3A"].features
    )
    for feature_id in A3_ELECTRICAL_FEATURES:
        assert feature_id not in VIEWS["A3A"].feature_ids


def test_a3_delta_is_exactly_the_eight_declared_features():
    delta = tuple(
        feature_id
        for feature_id in VIEWS["A3B"].feature_ids
        if feature_id not in set(VIEWS["A3A"].feature_ids)
    )
    assert delta == A3_ELECTRICAL_FEATURES
    assert set(delta) == {
        "applied_cooling",
        "applied_duty",
        "time_since_confirmed_applied_change",
        "cooling_voltage_v",
        "cooling_current_a",
        "cooling_power_w",
        "energy_counter_wh",
        "past_integrated_cooling_energy_wh",
    }


def test_a3_arms_share_thermal_door_and_environment_context():
    for family in ("instantaneous_thermal", "rolling_thermal", "door_context", "environmental_context"):
        a_ids = tuple(
            feature.feature_id
            for feature in VIEWS["A3A"].features
            if feature.family == family
        )
        b_ids = tuple(
            feature.feature_id
            for feature in VIEWS["A3B"].features
            if feature.family == family
        )
        assert a_ids == b_ids, family
    for feature_id in W11_CONTEXT_FEATURES:
        if feature_id in A3_ELECTRICAL_FEATURES:
            continue
        assert feature_id in VIEWS["A3A"].feature_ids
        assert feature_id in VIEWS["A3B"].feature_ids


def test_unadmitted_controller_request_and_readback_stay_out():
    for view in VIEWS.values():
        assert "requested_cooling" not in view.feature_ids
        assert "readback_cooling" not in view.feature_ids
        excluded = {feature_id for feature_id, _ in view.excluded_features}
        assert "requested_cooling" in excluded
        assert "readback_cooling" in excluded
        assert "T_tec_hot_side_c" in excluded


def test_a3_arms_share_the_matched_evaluable_population(datasets):
    assert population_identity(datasets["A3A"]) == population_identity(datasets["A3B"])
    for dataset in datasets.values():
        assert len(dataset.samples) == 1936
        assert dataset.positive_count == 480
        assert dataset.negative_count == 1456
        assert dataset.total_excluded == {"CENSORED": 960}
        assert dataset.horizon_s == 60.0
    assert not (
        set(datasets["A3A"].run_ids) & set(FIXTURE.split.test_runs)
    )


def test_a3a_is_invariant_to_electrical_mutation():
    trajectory = FIXTURE.development_trajectories[0]
    group = FIXTURE.split.group_of[trajectory.run_id]
    partition = FIXTURE.split.partition_of(trajectory.run_id)
    baseline = compute_view_rows(
        trajectory, REGISTRY, VIEWS["A3A"], group_id=group, partition=partition
    )
    mutated = _mutate_trajectory(
        trajectory,
        lambda sample: _mutate_sample(
            sample,
            applied_cooling="OFF" if sample.applied_cooling == "ON" else "ON",
            applied_duty=0.0 if sample.applied_duty else 1.0,
            cooling_voltage_v=999.0,
            cooling_current_a=999.0,
            cooling_power_w=9999.0,
            cooling_energy_counter_wh=0.0,
            electrical_quality="INVALID",
        ),
    )
    after = compute_view_rows(
        mutated, REGISTRY, VIEWS["A3A"], group_id=group, partition=partition
    )
    assert [row.values for row in baseline] == [row.values for row in after]


def test_a3b_is_live_to_electrical_mutation():
    trajectory = FIXTURE.development_trajectories[0]
    group = FIXTURE.split.group_of[trajectory.run_id]
    partition = FIXTURE.split.partition_of(trajectory.run_id)
    baseline = compute_view_rows(
        trajectory, REGISTRY, VIEWS["A3B"], group_id=group, partition=partition
    )
    mutated = _mutate_trajectory(
        trajectory,
        lambda sample: _mutate_sample(
            sample,
            applied_cooling="OFF" if sample.applied_cooling == "ON" else "ON",
            cooling_power_w=123.0,
        ),
    )
    after = compute_view_rows(
        mutated, REGISTRY, VIEWS["A3B"], group_id=group, partition=partition
    )
    assert any(
        left.values != right.values or left.missing_reasons != right.missing_reasons
        for left, right in zip(baseline, after)
    )


def test_future_power_and_applied_state_do_not_move_past_anchors():
    trajectory = FIXTURE.development_trajectories[0]
    group = FIXTURE.split.group_of[trajectory.run_id]
    partition = FIXTURE.split.partition_of(trajectory.run_id)
    for view in VIEWS.values():
        assert future_isolation_probe(
            trajectory,
            REGISTRY,
            view,
            group_id=group,
            partition=partition,
            anchor_index=40,
        )
        assert transition_after_anchor_probe(
            trajectory,
            REGISTRY,
            view,
            group_id=group,
            partition=partition,
            anchor_index=40,
        )


def test_unknown_electrical_quality_is_missing_never_zero_or_valid():
    trajectory = FIXTURE.development_trajectories[0]
    group = FIXTURE.split.group_of[trajectory.run_id]
    partition = FIXTURE.split.partition_of(trajectory.run_id)
    result = unknown_electrical_probe(
        trajectory,
        REGISTRY,
        VIEWS["A3B"],
        group_id=group,
        partition=partition,
        start_index=60,
    )
    assert result["pzem_features_missing_after_unknown"] is True
    assert result["pzem_never_zero_or_valid"] is True
    assert result["applied_state_still_observed"] is True
    assert result["anchors_checked"] == 121


def test_counter_reset_is_refused_never_negative_consumption():
    trajectory, _ = build_trajectory(
        "W15-TEST-RESET",
        scenario="S2",
        seed=702,
        duration_s=120.0,
        door_start_s=40.0,
        door_duration_s=20.0,
        critical_offsets_s=(100.0,),
        counter_reset_at_s=60.0,
    )
    result = counter_reset_probe(
        trajectory,
        REGISTRY,
        VIEWS["A3B"],
        group_id="W15-PAIR-X",
        partition="train",
        reset_anchor_s=60.0,
    )
    assert result == {
        "counter_present_before_reset": True,
        "counter_missing_after_reset": True,
        "reset_reason_recorded": True,
        "no_negative_counter_value": True,
    }


def test_synthetic_electrical_block_cannot_encode_scenario_identity():
    invariance = electrical_block_invariance(FIXTURE, REGISTRY, VIEWS["A3B"])
    assert invariance["electrical_block_run_invariant"] is True
    assert invariance["mismatch_count"] == 0
    assert invariance["runs_compared"] == 16


def test_electrical_diagnostics_are_diagnostic_only_and_show_run_age_risk(datasets):
    scenario_by_run = {
        trajectory.run_id: trajectory.scenario_id
        for trajectory in FIXTURE.development_trajectories
        if trajectory.run_id is not None
    }
    rows = {
        row["feature_id"]: row
        for row in electrical_feature_diagnostics(
            datasets["A3B"], VIEWS["A3B"], scenario_by_run=scenario_by_run
        )
    }
    assert set(rows) == set(A3_ELECTRICAL_FEATURES)
    for row in rows.values():
        assert row["diagnostic_only"] is True
        assert row["scenario_auc"] == pytest.approx(0.5)
    assert rows["energy_counter_wh"]["spearman_with_anchor_time"] == pytest.approx(1.0)
    assert rows["energy_counter_wh"]["monotonic_nondecreasing_within_runs"] is True
    assert rows["past_integrated_cooling_energy_wh"]["monotonic_nondecreasing_within_runs"] is True


def test_view_validation_refuses_electrical_input_in_a3a():
    tampered = dataclasses.replace(
        VIEWS["A3A"],
        features=VIEWS["A3A"].features + (VIEWS["A3B"].feature("applied_cooling"),),
    )
    with pytest.raises(A3ViewError, match="not exactly A3b minus|electrical or actuation"):
        validate_a3_views(
            {"A3A": tampered, "A3B": VIEWS["A3B"]}, REGISTRY, CONFIG
        )


def test_view_validation_refuses_changed_controlled_context():
    tampered = dataclasses.replace(
        VIEWS["A3B"],
        features=tuple(
            feature
            for feature in VIEWS["A3B"].features
            if feature.feature_id != "relative_humidity_pct"
        ),
    )
    with pytest.raises(
        A3ViewError, match="frozen W11 allowlist|controlled context family"
    ):
        validate_a3_views(
            {"A3A": VIEWS["A3A"], "A3B": tampered}, REGISTRY, CONFIG
        )


def test_view_validation_refuses_a_foreign_registry_feature():
    extra = dataclasses.replace(
        VIEWS["A3B"].feature("cooling_power_w"),
        feature_id="tampered_extra_power",
        base_feature_id="cooling_power_w",
    )
    tampered = dataclasses.replace(
        VIEWS["A3B"], features=VIEWS["A3B"].features + (extra,)
    )
    with pytest.raises(A3ViewError):
        validate_a3_views(
            {"A3A": VIEWS["A3A"], "A3B": tampered}, REGISTRY, CONFIG
        )


def test_actuator_response_interface_separates_command_from_response():
    assert (
        assess_actuator_electrical_response(
            applied_cooling=None, electrical_quality="VALID", cooling_power_w=10.0
        ).state
        == RESPONSE_APPLIED_UNKNOWN
    )
    assert (
        assess_actuator_electrical_response(
            applied_cooling="ON", electrical_quality="UNKNOWN", cooling_power_w=None
        ).state
        == RESPONSE_UNVERIFIABLE
    )
    assert (
        assess_actuator_electrical_response(
            applied_cooling="OFF", electrical_quality="VALID", cooling_power_w=0.0
        ).state
        == RESPONSE_NO_COMMAND
    )
    assert (
        assess_actuator_electrical_response(
            applied_cooling="ON", electrical_quality="VALID", cooling_power_w=55.0
        ).state
        == RESPONSE_APPLIED_WITH_RESPONSE
    )
    assert (
        assess_actuator_electrical_response(
            applied_cooling="ON", electrical_quality="VALID", cooling_power_w=0.0
        ).state
        == RESPONSE_APPLIED_WITHOUT_RESPONSE
    )
    assert (
        assess_actuator_electrical_response(
            applied_cooling="OFF", electrical_quality="VALID", cooling_power_w=12.0
        ).state
        == RESPONSE_WITHOUT_COMMAND
    )


def test_build_views_is_stable_across_calls():
    assert build_a3_views(REGISTRY, CONFIG)["A3B"].feature_ids == VIEWS[
        "A3B"
    ].feature_ids
