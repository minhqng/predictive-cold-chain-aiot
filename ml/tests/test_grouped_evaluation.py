"""W11 grouped split, fold and metric semantics tests (B-W11-01/B-W11-03)."""

from __future__ import annotations

import dataclasses

import pytest

from coldguard_ml.feature_fixtures import (
    build_development_dataset,
    build_predictive_control_trajectory,
)
from coldguard_ml.grouped_evaluation import (
    EvaluationRun,
    Fold,
    FoldSupportError,
    GroupingLeakageError,
    MetricValue,
    PreprocessingLeakageError,
    aggregate_fold_ap,
    assert_train_only_fit,
    build_evaluation_runs,
    classification_metrics,
    make_grouped_folds,
    validate_folds,
    validate_run_population,
)


def _run(
    run_id: str,
    group_id: str,
    *,
    source: str | None = None,
    partition: str = "train",
    controller: str = "CONTROLLER-A",
    hardware: str = "CG-HW-TEST",
) -> EvaluationRun:
    return EvaluationRun(
        run_id=run_id,
        group_id=group_id,
        pair_id=group_id if group_id.startswith("PAIR") else None,
        source_sha256=source or f"{run_id}-sha",
        physical_source_key=f"{source or run_id}-sha:boot",
        scenario_id="S2",
        controller_id=controller,
        hardware_config_id=hardware,
        partition=partition,
    )


class _FakeSplit:
    def __init__(self, partition: str | None = "train"):
        self.partition = partition

    def partition_of(self, run_id: str) -> str | None:
        return self.partition

    def group_of(self) -> dict[str, str]:  # pragma: no cover - not used
        return {}


def _fake_split(run_id: str, partition: str | None = "train"):
    class Split:
        group_of = {run_id: run_id}
        pair_lineage: tuple = ()

        def partition_of(self, other: str) -> str | None:
            return partition

    return Split()


def test_folds_are_group_disjoint_and_deterministic():
    runs = [_run(f"R{index}", f"PAIR-{index // 2}") for index in range(8)]
    first = make_grouped_folds(runs, n_splits=4, seed=42)
    second = make_grouped_folds(runs, n_splits=4, seed=42)
    assert [fold.to_manifest(42) for fold in first.folds] == [
        fold.to_manifest(42) for fold in second.folds
    ]
    for fold in first.folds:
        assert set(fold.train_runs).isdisjoint(fold.validation_runs)
        assert set(fold.train_groups).isdisjoint(fold.validation_groups)
        assert set(fold.train_runs) | set(fold.validation_runs) == {
            run.run_id for run in runs
        }


def test_pair_lineage_never_straddles_folds():
    runs = [_run(f"R{index}", f"PAIR-{index // 2}") for index in range(8)]
    cv = make_grouped_folds(runs, n_splits=4, seed=7)
    for fold in cv.folds:
        train_groups = set(fold.train_groups)
        validation_groups = set(fold.validation_groups)
        assert train_groups.isdisjoint(validation_groups)
        for group in train_groups | validation_groups:
            members = {run.run_id for run in runs if run.group_id == group}
            sides = {
                "train" if run_id in fold.train_runs else "validation"
                for run_id in members
            }
            assert len(sides) == 1


def test_fold_count_cannot_exceed_effective_groups():
    runs = [_run("R1", "PAIR-1"), _run("R2", "PAIR-2")]
    with pytest.raises(FoldSupportError, match="fold count may never exceed"):
        make_grouped_folds(runs, n_splits=3, seed=1)


def test_duplicate_physical_source_is_refused():
    first = _run("R1", "PAIR-1", source="SAME")
    second = _run("R2", "PAIR-2", source="SAME")
    with pytest.raises(GroupingLeakageError, match="physical source"):
        validate_run_population([first, second])


def test_locked_test_run_is_refused():
    run = _run("TEST", "PAIR-TEST", partition="test")
    with pytest.raises(GroupingLeakageError, match="locked-test"):
        validate_run_population([run])


def test_validate_folds_rejects_pair_straddle():
    run_a = dataclasses.replace(_run("A", "G-A"), pair_id="PAIR-X")
    run_b = dataclasses.replace(_run("B", "G-B"), pair_id="PAIR-X")
    run_c = dataclasses.replace(_run("C", "G-C"), pair_id=None)
    fold = Fold(
        fold_id="F1",
        train_groups=("G-A",),
        validation_groups=("G-B", "G-C"),
        train_runs=("A",),
        validation_runs=("B", "C"),
        pair_lineage=(),
    )
    with pytest.raises(GroupingLeakageError, match="pair lineage straddles"):
        validate_folds([fold], [run_a, run_b, run_c])


def test_predictive_controller_is_refused():
    trajectory, _ = build_predictive_control_trajectory()
    run_id = trajectory.run_id or ""
    with pytest.raises(GroupingLeakageError, match="predictive"):
        build_evaluation_runs(
            [trajectory],
            _fake_split(run_id),
            hardware_config_by_run={run_id: "CG-HW"},
        )


def test_mixed_hardware_lineage_is_refused():
    dataset = build_development_dataset()
    development = [
        trajectory
        for trajectory in dataset.trajectories
        if dataset.partition_of(trajectory.run_id or "") in ("train", "validation")
    ]
    hardware = {
        trajectory.run_id: ("CG-HW-A" if index == 0 else "CG-HW-B")
        for index, trajectory in enumerate(development)
    }
    with pytest.raises(GroupingLeakageError, match="more than one hardware"):
        build_evaluation_runs(development, dataset.split, hardware_config_by_run=hardware)


def test_unpartitioned_run_is_refused():
    dataset = build_development_dataset()
    trajectory = dataset.trajectories[0]
    run_id = trajectory.run_id or ""
    with pytest.raises(GroupingLeakageError, match="not partitioned"):
        build_evaluation_runs(
            [trajectory],
            _fake_split(run_id, None),
            hardware_config_by_run={run_id: "CG-HW"},
        )


def test_fit_population_must_be_train_only():
    with pytest.raises(PreprocessingLeakageError, match="non-training groups"):
        assert_train_only_fit({"G1"}, {"G1", "G2"})
    assert_train_only_fit({"G1", "G2"}, {"G1"})


def test_single_class_validation_ap_is_undefined_not_zero_or_one():
    metrics = classification_metrics([0, 0, 0], [0.1, 0.2, 0.3], threshold=0.5)
    assert metrics.average_precision.value is None
    assert metrics.average_precision.reason == "SINGLE_CLASS_VALIDATION_NO_POSITIVES"
    assert metrics.roc_auc.value is None
    assert "SINGLE_CLASS_VALIDATION_NO_POSITIVES" in metrics.undefined_reasons


def test_threshold_comparison_is_explicit():
    greater = classification_metrics(
        [0, 1], [0.5, 0.5], threshold=0.5, comparison="GT"
    )
    greater_equal = classification_metrics(
        [0, 1], [0.5, 0.5], threshold=0.5, comparison="GE"
    )
    assert greater.confusion["tp"] == 0
    assert greater_equal.confusion["tp"] == 1
    assert greater.comparison == "GT"
    assert greater_equal.comparison == "GE"


def test_undefined_precision_and_f1_are_not_fabricated():
    metrics = classification_metrics([1, 1], [0.1, 0.2], threshold=0.5)
    assert metrics.precision.value is None
    assert metrics.precision.reason == "NO_PREDICTED_POSITIVES"
    assert metrics.recall.value == 0.0
    assert metrics.f1.value is None


def test_fold_ap_aggregation_reports_instability_and_refuses_missing_folds():
    defined = aggregate_fold_ap([MetricValue(0.5), MetricValue(0.7)])
    assert defined["status"] == "DEFINED"
    assert defined["mean"] == pytest.approx(0.6)
    assert defined["min"] == pytest.approx(0.5)
    assert defined["max"] == pytest.approx(0.7)
    assert defined["instability_range"] == pytest.approx(0.2)
    undefined = aggregate_fold_ap([MetricValue(0.5), MetricValue(None, "NO_POSITIVES")])
    assert undefined["status"] == "UNDEFINED"
    assert undefined["reason"] == "AT_LEAST_ONE_FOLD_AP_UNDEFINED"


def test_different_seed_changes_the_fold_assignment():
    runs = [_run(f"R{index}", f"PAIR-{index}") for index in range(6)]
    first = make_grouped_folds(runs, n_splits=3, seed=1)
    second = make_grouped_folds(runs, n_splits=3, seed=2)
    assert [fold.validation_runs for fold in first.folds] != [
        fold.validation_runs for fold in second.folds
    ]
