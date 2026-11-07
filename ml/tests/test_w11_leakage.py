"""W11 executable leakage-audit tests (B-W11-06)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from coldguard_ml.event_evaluator import EventEvaluationError, EpisodePolicy, WarningSample, build_warning_episodes
from coldguard_ml.feature_fixtures import build_predictive_control_trajectory, build_trajectory
from coldguard_ml.feature_pipeline import FeaturePipelineError, feature_rows
from coldguard_ml.feature_registry import load_registry
from coldguard_ml.grouped_evaluation import (
    EvaluationRun,
    GroupingLeakageError,
    LOCKED_TEST_PARTITION,
    build_evaluation_runs,
    validate_run_population,
)
from coldguard_ml.leakage_audit import (
    BLOCKED_BY_MISSING_EVIDENCE,
    NOT_APPLICABLE,
    PASS,
    run_leakage_audit,
)
from coldguard_ml.xgb_benchmark import (
    ConfigError,
    FeaturePolicy,
    LabeledSample,
    aggregate_event_results,
    build_expanded_w11_fixture,
    build_w10_compatibility_fixture,
    feature_matrix,
    load_benchmark_config,
    run_grouped_benchmark,
)

ML_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def registry():
    return load_registry(ML_ROOT / "feature-registry-v1.yaml")


@pytest.fixture(scope="module")
def config(registry):
    return load_benchmark_config(ML_ROOT / "xgb-v1-config.yaml", registry)


@pytest.fixture(scope="module")
def benchmark(registry, config, tmp_path_factory):
    fixture = build_expanded_w11_fixture()
    out = tmp_path_factory.mktemp("w11-audit")
    result, _ = run_grouped_benchmark(fixture, registry, config, out_dir=out)
    return fixture, result


@pytest.fixture(scope="module")
def audit(benchmark, registry, config):
    fixture, result = benchmark
    return run_leakage_audit(fixture, registry, config, benchmark=result)


def test_audit_covers_all_register_risks(audit):
    risk_ids = [record.risk_id for record in audit.records]
    assert risk_ids == [f"LRK-{index:02d}" for index in range(1, 18)]
    assert audit.summary()[PASS] == 15
    assert audit.summary()[NOT_APPLICABLE] == 1
    assert audit.summary()[BLOCKED_BY_MISSING_EVIDENCE] == 1
    for probe in audit.probes:
        assert probe.status == PASS, (probe.probe_id, probe.detail)


def test_blocked_and_not_applicable_are_not_upgraded(audit):
    by_id = {record.risk_id: record for record in audit.records}
    assert by_id["LRK-16"].result == BLOCKED_BY_MISSING_EVIDENCE
    assert by_id["LRK-06"].result == NOT_APPLICABLE
    assert "PASS" not in by_id["LRK-16"].result
    assert "PASS" not in by_id["LRK-06"].result


def test_audit_report_contains_required_fields(audit):
    markdown = audit.to_markdown()
    for key in (
        "Risk",
        "Attack mechanism",
        "Preventive check",
        "Regression tests",
        "Residual limitation",
        "Scientific consequence",
    ):
        assert key in markdown
    assert "LRK-01" in markdown
    assert "LRK-17" in markdown
    assert "BLOCKED_BY_MISSING_EVIDENCE" in markdown
    assert "Executable probes" in markdown


def test_future_mutation_invariance(registry):
    trajectory, _ = build_trajectory(
        "CG-W11-LEAK-FUT-001", scenario="S2", seed=1600, door_start_s=40.0
    )
    baseline = feature_rows(trajectory, registry)
    mutated = dataclasses.replace(
        trajectory,
        samples=tuple(
            dataclasses.replace(
                sample,
                chamber_c=tuple(
                    (role, None if value is None else value + 9.0)
                    for role, value in sample.chamber_c
                ),
                door_state="OPEN",
                applied_cooling="OFF",
                applied_duty=0.0,
                cooling_power_w=None,
            )
            if sample.time_s > 50.0
            else sample
            for sample in trajectory.samples
        ),
    )
    after = feature_rows(mutated, registry)
    past_before = [row for row in baseline if row.anchor_t_s <= 50.0]
    past_after = [row for row in after if row.anchor_t_s <= 50.0]
    assert len(past_before) == len(past_after) == 51
    assert all(
        (left.values, left.missing_reasons) == (right.values, right.missing_reasons)
        for left, right in zip(past_before, past_after)
    )


def test_locked_test_boundary(benchmark):
    fixture, _ = benchmark
    test_runs = set(fixture.test_runs)
    trajectory = next(
        item for item in fixture.trajectories if item.run_id in test_runs
    )
    with pytest.raises(GroupingLeakageError):
        build_evaluation_runs(
            [trajectory],
            fixture.split,
            hardware_config_by_run={
                trajectory.run_id: fixture.hardware_config_by_run[trajectory.run_id]
            },
        )
    run = EvaluationRun(
        run_id=trajectory.run_id,
        group_id="TEST",
        pair_id=None,
        source_sha256=trajectory.source_sha256,
        physical_source_key=trajectory.physical_source_key,
        scenario_id=trajectory.scenario_id or "S2",
        controller_id="CONTROLLER-A",
        hardware_config_id="CG-HW",
        partition=LOCKED_TEST_PARTITION,
    )
    with pytest.raises(GroupingLeakageError):
        validate_run_population([run])


def test_predictive_intervention_is_refused(benchmark):
    fixture, _ = benchmark
    trajectory, _ = build_predictive_control_trajectory()
    run_id = trajectory.run_id or ""

    class Split:
        group_of = {run_id: run_id}
        pair_lineage = ()

        def partition_of(self, other: str) -> str:
            return "train"

    with pytest.raises(GroupingLeakageError, match="predictive"):
        build_evaluation_runs(
            [trajectory],
            Split(),
            hardware_config_by_run={run_id: "CG-HW"},
        )


def test_duplicate_physical_source_is_refused(benchmark):
    fixture, _ = benchmark
    trajectory = fixture.development_trajectories[0]
    first = EvaluationRun(
        run_id="A",
        group_id="G1",
        pair_id=None,
        source_sha256=trajectory.source_sha256,
        physical_source_key=trajectory.physical_source_key,
        scenario_id="S2",
        controller_id="CONTROLLER-A",
        hardware_config_id="CG-HW",
        partition="train",
    )
    second = dataclasses.replace(first, run_id="B", group_id="G2")
    with pytest.raises(GroupingLeakageError):
        validate_run_population([first, second])


def test_label_and_target_fields_cannot_enter_x(registry):
    policy = FeaturePolicy(
        allowlist=("critical_event_time_s",),
        excluded_diagnostic_features=(),
        prohibited_fields=("critical_event_time_s",),
    )
    with pytest.raises(ConfigError):
        policy.assert_safe(registry)
    policy = FeaturePolicy(
        allowlist=("T_tec_hot_side_c",),
        excluded_diagnostic_features=("T_tec_hot_side_c",),
        prohibited_fields=(),
    )
    with pytest.raises(ConfigError):
        policy.assert_safe(registry)


def test_contradictory_duplicate_delivery_is_refused():
    policy = EpisodePolicy(
        policy_version="audit-v1",
        min_persistence_s=0.0,
        bridge_gap_s=2.0,
        bridge_unknown_gaps=False,
        status="AUDIT_ONLY",
        source="W11 audit",
    )
    samples = (
        WarningSample(time_s=0.0, state="WARNING", sample_id="S"),
        WarningSample(time_s=3.0, state="NO_WARNING", sample_id="S"),
    )
    with pytest.raises(EventEvaluationError, match="contradictory duplicate"):
        build_warning_episodes(
            samples,
            policy,
            run_id="R",
            source_sha256="f" * 64,
            synthetic_control=True,
        )


def test_missing_electrical_is_nan_not_zero():
    sample = LabeledSample(
        run_id="R",
        group_id="G",
        partition="train",
        source_sha256="e" * 64,
        sample_identity="S:1",
        anchor_t_s=0.0,
        features=(float("nan"), 2.0),
        y=1,
        series_id="series",
    )
    matrix, _ = feature_matrix([sample], ("electrical", "thermal"))
    assert np.isnan(matrix[0, 0])
    assert matrix[0, 0] != 0.0


def test_eventless_population_does_not_fabricate_missed_events():
    summary = aggregate_event_results([], duration_s=0.0)
    assert summary["missed_critical_events"] is None
    assert summary["event_recall"] is None
    assert "NO_EVALUATION_RESULTS" in summary["undefined_reasons"]


def test_boot_boundary_is_enforced():
    trajectory, _ = build_trajectory(
        "CG-W11-LEAK-BOOT-001", scenario="S2", seed=1601, door_start_s=40.0
    )
    samples = list(trajectory.samples)
    samples[2] = dataclasses.replace(samples[2], boot_id="OTHER")
    with pytest.raises(FeaturePipelineError, match="belongs to boot"):
        dataclasses.replace(trajectory, samples=tuple(samples))


def test_w10_held_out_pair_is_not_in_w11_smoke(registry, config, tmp_path):
    fixture = build_w10_compatibility_fixture()
    result, _ = run_grouped_benchmark(
        fixture, registry, config, out_dir=tmp_path, n_splits_override=2
    )
    test_runs = set(fixture.test_runs)
    assert test_runs
    assert test_runs.isdisjoint(set(result.labeled.run_ids))
    assert test_runs.isdisjoint(
        {run_id for fold in result.cv.folds for run_id in fold.train_runs}
    )
    assert test_runs.isdisjoint(
        {run_id for fold in result.cv.folds for run_id in fold.validation_runs}
    )
