"""W14 adversarial tests for the role-correct A1/A2 ablation views."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from coldguard_ml.feature_fixtures import build_trajectory
from coldguard_ml.feature_pipeline import PipelineSample, Trajectory
from coldguard_ml.feature_registry import load_registry
from coldguard_ml.w14_ablation import (
    A1A_SINGLE_ROLE,
    A2_DOOR_FEATURES,
    W11_CONTEXT_FEATURES,
    AblationComparabilityError,
    AblationViewError,
    assert_matched_population,
    build_ablation_dataset,
    build_ablation_views,
    compute_view_rows,
    paired_fold_comparison,
    population_identity,
    run_ablation_arm,
    run_support,
    single_probe_isolation_probe,
    validate_arm_pair,
    validate_view,
)
from coldguard_ml.xgb_benchmark import (
    BenchmarkError,
    build_expanded_w11_fixture,
    load_benchmark_config,
    run_grouped_benchmark,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = load_registry(ROOT / "feature-registry-v1.yaml")
CONFIG = load_benchmark_config(ROOT / "xgb-v1-config.yaml", REGISTRY)
FIXTURE = build_expanded_w11_fixture()
VIEWS = build_ablation_views(REGISTRY)


def _mutate_sample(sample: PipelineSample, **changes) -> PipelineSample:
    return PipelineSample(
        **{**sample.__dict__, **changes}
    )


def _mutate_trajectory(
    trajectory: Trajectory, transform
) -> Trajectory:
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


@pytest.fixture(scope="module")
def arm_results(tmp_path_factory):
    root = tmp_path_factory.mktemp("w14-arms")
    return {
        arm: run_ablation_arm(
            FIXTURE, REGISTRY, CONFIG, view, scaffold_dir=root / arm
        )[0]
        for arm, view in VIEWS.items()
    }


def test_a1b_reproduces_the_w11_allowlist_exactly():
    assert VIEWS["A1B"].feature_ids == CONFIG.feature_policy.allowlist
    assert VIEWS["A1B"].feature_count == 28
    assert VIEWS["A1A"].feature_count == 21
    assert VIEWS["A2A"].feature_count == 14
    assert VIEWS["A2B"].feature_count == 18


def test_a1a_thermal_features_bind_only_the_center_probe():
    thermal = [
        feature
        for feature in VIEWS["A1A"].features
        if feature.family in ("instantaneous_thermal", "rolling_thermal")
    ]
    assert thermal
    for feature in thermal:
        assert feature.source_roles == (A1A_SINGLE_ROLE,), feature.feature_id
    assert VIEWS["A1A"].feature("T_center_c").base_feature_id == "T_center_c"


def test_a1a_excludes_multi_probe_aggregates_gradients_and_hot_side():
    ids = set(VIEWS["A1A"].feature_ids)
    for forbidden in (
        "T_chamber_max_c",
        "T_chamber_min_c",
        "T_chamber_mean_c",
        "T_chamber_spread_c",
        "T_bottom_c",
        "T_near_door_c",
        "past_only_spatial_spread_60s",
        "T_tec_hot_side_c",
    ):
        assert forbidden not in ids
    for feature in VIEWS["A1A"].features:
        assert "TEC_HOT_SIDE" not in feature.source_roles


def test_a1a_single_probe_path_does_not_consume_other_probes():
    trajectory = FIXTURE.development_trajectories[0]
    group = FIXTURE.split.group_of[trajectory.run_id]
    partition = FIXTURE.split.partition_of(trajectory.run_id)
    assert single_probe_isolation_probe(
        trajectory,
        REGISTRY,
        VIEWS["A1A"],
        group_id=group,
        partition=partition,
    )
    # The same mutation must change A1B, otherwise the probe is vacuous.
    assert not single_probe_isolation_probe(
        trajectory,
        REGISTRY,
        VIEWS["A1B"],
        group_id=group,
        partition=partition,
    )


def test_a1a_ignores_hot_side_mutation():
    trajectory = FIXTURE.development_trajectories[0]
    group = FIXTURE.split.group_of[trajectory.run_id]
    partition = FIXTURE.split.partition_of(trajectory.run_id)
    baseline = compute_view_rows(
        trajectory, REGISTRY, VIEWS["A1A"], group_id=group, partition=partition
    )
    mutated = _mutate_trajectory(
        trajectory,
        lambda sample: _mutate_sample(
            sample,
            hot_side_c=(
                None if sample.hot_side_c is None else sample.hot_side_c + 500.0
            ),
        ),
    )
    after = compute_view_rows(
        mutated, REGISTRY, VIEWS["A1A"], group_id=group, partition=partition
    )
    assert [row.values for row in baseline] == [row.values for row in after]


def test_a1_arms_share_labels_groups_folds_and_population(datasets):
    assert_matched_population(
        datasets["A1A"], datasets["A1B"], datasets["A2A"], datasets["A2B"]
    )
    for arm in ("A1A", "A1B", "A2A", "A2B"):
        dataset = datasets[arm]
        assert len(dataset.samples) == 1936
        assert dataset.positive_count == 480
        assert dataset.negative_count == 1456
        assert dataset.total_excluded == {"CENSORED": 960}
        assert dataset.horizon_s == 60.0
        assert dataset.label_identity == datasets["A1A"].label_identity


def test_a1_arms_vary_only_the_thermal_sensing_family():
    a1a = set(VIEWS["A1A"].feature_ids)
    a1b = set(VIEWS["A1B"].feature_ids)
    only_a1a = a1a - a1b
    only_a1b = a1b - a1a
    assert all(
        VIEWS["A1A"].feature(feature_id).family
        in ("instantaneous_thermal", "rolling_thermal")
        for feature_id in only_a1a
    )
    assert all(
        VIEWS["A1B"].feature(feature_id).family
        in ("instantaneous_thermal", "rolling_thermal")
        for feature_id in only_a1b
    )
    for feature_id in W11_CONTEXT_FEATURES:
        assert feature_id in a1a and feature_id in a1b


def test_a2a_has_no_door_feature_and_a2b_has_exactly_the_authorized_four():
    assert not any(
        feature.family == "door_context" for feature in VIEWS["A2A"].features
    )
    door_ids = tuple(
        feature.feature_id
        for feature in VIEWS["A2B"].features
        if feature.family == "door_context"
    )
    assert set(door_ids) == set(A2_DOOR_FEATURES)
    assert len(door_ids) == 4


def test_a2_arms_share_an_identical_thermal_set_and_exclude_electrical():
    thermal_a = tuple(
        feature.feature_id
        for feature in VIEWS["A2A"].features
        if feature.family in ("instantaneous_thermal", "rolling_thermal")
    )
    thermal_b = tuple(
        feature.feature_id
        for feature in VIEWS["A2B"].features
        if feature.family in ("instantaneous_thermal", "rolling_thermal")
    )
    assert thermal_a == thermal_b
    for view in (VIEWS["A2A"], VIEWS["A2B"]):
        assert not any(
            feature.family
            in ("electrical_context", "actuation_context", "environmental_context")
            for feature in view.features
        )


def test_a2a_is_unaffected_by_door_state_and_unrelated_context_mutation():
    trajectory = FIXTURE.development_trajectories[0]
    group = FIXTURE.split.group_of[trajectory.run_id]
    partition = FIXTURE.split.partition_of(trajectory.run_id)
    baseline = compute_view_rows(
        trajectory, REGISTRY, VIEWS["A2A"], group_id=group, partition=partition
    )

    def mutate(sample: PipelineSample) -> PipelineSample:
        return _mutate_sample(
            sample,
            door_state="UNKNOWN",
            door_quality="UNKNOWN",
            door_polarity_attested=False,
            cooling_voltage_v=99.0,
            cooling_current_a=99.0,
            cooling_power_w=99.0,
            applied_cooling="ON" if sample.applied_cooling != "ON" else "OFF",
            applied_duty=1.0,
            t_air_c=99.0,
            rh_pct=99.0,
        )

    mutated = _mutate_trajectory(trajectory, mutate)
    after = compute_view_rows(
        mutated, REGISTRY, VIEWS["A2A"], group_id=group, partition=partition
    )
    assert [row.values for row in baseline] == [row.values for row in after]


def test_a2b_unknown_door_is_missing_never_closed():
    trajectory, _ = build_trajectory(
        "W14-DOOR-UNKNOWN",
        scenario="S2",
        seed=501,
        duration_s=120.0,
        door_start_s=40.0,
        door_duration_s=20.0,
        unknown_start_s=52.0,
        unknown_duration_s=5.0,
        critical_offsets_s=(80.0,),
    )
    rows = compute_view_rows(
        trajectory,
        REGISTRY,
        VIEWS["A2B"],
        group_id="W14-PAIR-X",
        partition="train",
    )
    feature_ids = VIEWS["A2B"].feature_ids
    door_open_index = feature_ids.index("door_open")
    duration_index = feature_ids.index("duration_so_far")
    anchors = {row.anchor_t_s: row for row in rows}
    for anchor in (52.0, 53.0, 54.0, 55.0, 56.0):
        row = anchors[anchor]
        assert row.values[door_open_index] is None
        assert row.missing_reasons[door_open_index] == "MISSING_UNKNOWN_DOOR"
        assert row.values[duration_index] is None
    # A trusted CLOSED anchor before the UNKNOWN window is explicitly 0.0.
    assert anchors[39.0].values[door_open_index] == 0.0
    assert anchors[39.0].missing_reasons[door_open_index] == "PRESENT"


def test_a2b_unattested_polarity_is_missing_never_closed():
    trajectory, _ = build_trajectory(
        "W14-DOOR-POLARITY",
        scenario="S2",
        seed=502,
        duration_s=120.0,
        door_start_s=40.0,
        door_duration_s=20.0,
        critical_offsets_s=(80.0,),
        door_polarity_attested=False,
    )
    rows = compute_view_rows(
        trajectory,
        REGISTRY,
        VIEWS["A2B"],
        group_id="W14-PAIR-X",
        partition="train",
    )
    door_open_index = VIEWS["A2B"].feature_ids.index("door_open")
    assert all(
        row.values[door_open_index] is None
        and row.missing_reasons[door_open_index] == "MISSING_POLARITY_UNATTESTED"
        for row in rows
    )


def test_a2_positive_support_is_distributed_across_independent_runs(datasets):
    support = run_support(datasets["A2B"])
    s2_runs = [row for row in support if row["run_id"].startswith("CG-W11-S2-")]
    assert len(s2_runs) == 8
    assert all(row["positive"] == 60 for row in s2_runs)
    assert sum(row["positive"] for row in s2_runs) == 480
    assert max(row["positive"] for row in s2_runs) / 480 == pytest.approx(0.125)


def test_locked_test_runs_never_enter_any_arm(datasets):
    locked = set(FIXTURE.split.test_runs)
    assert locked
    for dataset in datasets.values():
        assert not (set(dataset.run_ids) & locked)
        assert all(
            sample.partition in ("train", "validation")
            for sample in dataset.samples
        )


def test_override_refuses_changed_label_identity():
    dataset = build_ablation_dataset(FIXTURE, REGISTRY, CONFIG, VIEWS["A1B"])
    changed = dataclasses.replace(
        dataset, label_identity={"tampered": True}
    )
    with pytest.raises(BenchmarkError, match="label identity"):
        run_grouped_benchmark(
            FIXTURE,
            REGISTRY,
            CONFIG,
            labeled_override=changed,
        )


def test_override_refuses_changed_horizon():
    dataset = build_ablation_dataset(FIXTURE, REGISTRY, CONFIG, VIEWS["A1B"])
    changed = dataclasses.replace(dataset, horizon_s=300.0)
    with pytest.raises(BenchmarkError, match="horizon"):
        run_grouped_benchmark(
            FIXTURE,
            REGISTRY,
            CONFIG,
            labeled_override=changed,
        )


def test_override_refuses_missing_development_run():
    dataset = build_ablation_dataset(FIXTURE, REGISTRY, CONFIG, VIEWS["A1B"])
    changed = dataclasses.replace(dataset, run_ids=dataset.run_ids[:-1])
    with pytest.raises(BenchmarkError, match="development runs"):
        run_grouped_benchmark(
            FIXTURE,
            REGISTRY,
            CONFIG,
            labeled_override=changed,
        )


def test_override_refuses_a_label_or_diagnostic_column():
    dataset = build_ablation_dataset(FIXTURE, REGISTRY, CONFIG, VIEWS["A1B"])
    tampered = dataclasses.replace(
        dataset, feature_ids=dataset.feature_ids + ("label",)
    )
    with pytest.raises(BenchmarkError, match="prohibited/diagnostic"):
        run_grouped_benchmark(
            FIXTURE,
            REGISTRY,
            CONFIG,
            labeled_override=tampered,
        )
    tampered = dataclasses.replace(
        dataset, feature_ids=dataset.feature_ids + ("T_tec_hot_side_c",)
    )
    with pytest.raises(BenchmarkError, match="prohibited/diagnostic"):
        run_grouped_benchmark(
            FIXTURE,
            REGISTRY,
            CONFIG,
            labeled_override=tampered,
        )


def test_w11_override_path_is_result_equivalent(tmp_path):
    from coldguard_ml.w14_ablation import build_ablation_dataset

    dataset = build_ablation_dataset(FIXTURE, REGISTRY, CONFIG, VIEWS["A1B"])
    native, _ = run_grouped_benchmark(
        FIXTURE, REGISTRY, CONFIG, out_dir=tmp_path / "native"
    )
    override, _ = run_grouped_benchmark(
        FIXTURE,
        REGISTRY,
        CONFIG,
        out_dir=tmp_path / "override",
        labeled_override=dataset,
    )
    assert native.feature_ids == override.feature_ids
    assert len(native.fold_runs) == len(override.fold_runs)
    for left, right in zip(native.fold_runs, override.fold_runs):
        assert left.to_dict() == right.to_dict()
    assert native.oof == override.oof
    assert native.labeled.to_dict() == override.labeled.to_dict()


def test_view_validation_refuses_hot_side_as_chamber_air():
    view = VIEWS["A1B"]
    tampered = dataclasses.replace(
        view,
        features=view.features
        + (
            dataclasses.replace(
                view.features[0],
                feature_id="tampered_hot_side",
                base_feature_id="T_tec_hot_side_c",
                family="diagnostic_thermal",
                source_roles=("TEC_HOT_SIDE",),
            ),
        ),
    )
    with pytest.raises(AblationViewError, match="hot side|hot-side"):
        validate_view(tampered, REGISTRY)


def test_view_validation_refuses_multi_probe_binding_in_a1a():
    view = VIEWS["A1A"]
    tampered = dataclasses.replace(
        view,
        features=view.features
        + (VIEWS["A1B"].feature("T_chamber_mean_c"),),
    )
    with pytest.raises(AblationViewError, match="only CHAMBER_CENTER"):
        validate_view(tampered, REGISTRY)


def test_arm_pair_validation_refuses_uncontrolled_context():
    tampered = dataclasses.replace(
        VIEWS["A1A"],
        features=tuple(
            feature
            for feature in VIEWS["A1A"].features
            if feature.feature_id != "cooling_voltage_v"
        ),
    )
    with pytest.raises(AblationViewError, match="uncontrolled"):
        validate_arm_pair(tampered, VIEWS["A1B"])


def test_population_identity_is_identical_across_arms(datasets):
    hashes = {population_identity(dataset) for dataset in datasets.values()}
    assert len(hashes) == 1


def test_arm_results_are_synthetic_and_do_not_touch_test(arm_results):
    for result in arm_results.values():
        assert result.provenance == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
        assert result.split_identity["test_partition_used"] is False
        assert all(fold.status == "FIT" for fold in result.fold_runs)
        assert result.cv.effective_groups == 8
        assert result.cv.n_splits == 4


def test_matched_population_guard_refuses_label_drift():
    reference = build_ablation_dataset(FIXTURE, REGISTRY, CONFIG, VIEWS["A1B"])
    tampered_samples = list(reference.samples)
    first = tampered_samples[0]
    tampered_samples[0] = dataclasses.replace(first, y=1 - first.y)
    tampered = dataclasses.replace(reference, samples=tuple(tampered_samples))
    with pytest.raises(AblationComparabilityError, match="identical evaluable population"):
        assert_matched_population(reference, tampered)


def test_paired_comparison_guard_refuses_fold_identity_drift(arm_results):
    left = arm_results["A1A"]
    right = arm_results["A1B"]
    assert paired_fold_comparison(left, right)
    tampered_folds = list(right.fold_runs)
    tampered_folds[0] = dataclasses.replace(
        tampered_folds[0], validation_runs=("CG-W11-S1-999",)
    )
    tampered = dataclasses.replace(
        right, fold_runs=tuple(tampered_folds)
    )
    with pytest.raises(AblationComparabilityError, match="identical runs/groups"):
        paired_fold_comparison(left, tampered)


def test_override_refuses_flipped_label():
    dataset = build_ablation_dataset(FIXTURE, REGISTRY, CONFIG, VIEWS["A1B"])
    samples = list(dataset.samples)
    first = samples[0]
    samples[0] = dataclasses.replace(first, y=1 - first.y)
    tampered = dataclasses.replace(dataset, samples=tuple(samples))
    with pytest.raises(BenchmarkError, match="canonical labels"):
        run_grouped_benchmark(
            FIXTURE,
            REGISTRY,
            CONFIG,
            labeled_override=tampered,
        )


def test_override_refuses_dropped_anchor():
    dataset = build_ablation_dataset(FIXTURE, REGISTRY, CONFIG, VIEWS["A1B"])
    tampered = dataclasses.replace(dataset, samples=dataset.samples[:-1])
    with pytest.raises(BenchmarkError, match="canonical labels"):
        run_grouped_benchmark(
            FIXTURE,
            REGISTRY,
            CONFIG,
            labeled_override=tampered,
        )


def test_override_refuses_population_metadata_drift():
    dataset = build_ablation_dataset(FIXTURE, REGISTRY, CONFIG, VIEWS["A1B"])

    def tampered(index: int, **changes):
        samples = list(dataset.samples)
        samples[index] = dataclasses.replace(samples[index], **changes)
        return dataclasses.replace(dataset, samples=tuple(samples))

    with pytest.raises(BenchmarkError, match="foreign group"):
        run_grouped_benchmark(
            FIXTURE,
            REGISTRY,
            CONFIG,
            labeled_override=tampered(0, group_id="W11-PAIR-999"),
        )
    first_partition = dataset.samples[0].partition
    other_partition = (
        "validation" if first_partition == "train" else "train"
    )
    with pytest.raises(BenchmarkError, match="carries partition"):
        run_grouped_benchmark(
            FIXTURE,
            REGISTRY,
            CONFIG,
            labeled_override=tampered(0, partition=other_partition),
        )
    with pytest.raises(BenchmarkError, match="duplicate sample identity"):
        run_grouped_benchmark(
            FIXTURE,
            REGISTRY,
            CONFIG,
            labeled_override=tampered(
                1, sample_identity=dataset.samples[0].sample_identity
            ),
        )
    with pytest.raises(BenchmarkError, match="sample width"):
        run_grouped_benchmark(
            FIXTURE,
            REGISTRY,
            CONFIG,
            labeled_override=tampered(
                0, features=dataset.samples[0].features[:-1]
            ),
        )
    with pytest.raises(BenchmarkError, match="binary"):
        run_grouped_benchmark(
            FIXTURE,
            REGISTRY,
            CONFIG,
            labeled_override=tampered(0, y=2),
        )


def test_a2b_is_unaffected_by_electrical_mutation():
    trajectory = FIXTURE.development_trajectories[0]
    group = FIXTURE.split.group_of[trajectory.run_id]
    partition = FIXTURE.split.partition_of(trajectory.run_id)
    baseline = compute_view_rows(
        trajectory, REGISTRY, VIEWS["A2B"], group_id=group, partition=partition
    )
    mutated = _mutate_trajectory(
        trajectory,
        lambda sample: _mutate_sample(
            sample,
            cooling_voltage_v=99.0,
            cooling_current_a=99.0,
            cooling_power_w=99.0,
            applied_cooling="ON" if sample.applied_cooling != "ON" else "OFF",
            applied_duty=1.0,
            t_air_c=99.0,
            rh_pct=99.0,
        ),
    )
    after = compute_view_rows(
        mutated, REGISTRY, VIEWS["A2B"], group_id=group, partition=partition
    )
    assert [row.values for row in baseline] == [row.values for row in after]
