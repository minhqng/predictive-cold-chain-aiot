"""W11 integrity regressions for R1 (EWT/AIW) and R2 (exposure/censoring)."""

from __future__ import annotations

import datetime as _dt
from dataclasses import replace

import pytest

from coldguard_ml.evaluation_contract import EWTProvenance, compute_ewt
from coldguard_ml.event_evaluator import WARNING, WarningSample
from coldguard_ml.feature_fixtures import SYNTHETIC_CONTROLLER, build_trajectory
from coldguard_ml.feature_registry import load_registry
from coldguard_ml.labels import CriticalEvent, CriticalEventSeries
from coldguard_ml.splitting import RunInfo, SplitConfig, SplitProportions, split_runs
from coldguard_ml.xgb_benchmark import (
    AIW_REASON_MISSING_LATENCY_CHAIN,
    EWT_REASON_NO_COMMON_TRAJECTORY,
    HARDWARE_W11,
    NON_ESTIMABLE_RUN_REASON,
    BenchmarkError,
    BenchmarkFixture,
    NonEstimableRunError,
    _censor_after_cutoff,
    _critical_event_inputs,
    _event_result,
    _prepare_baseline_run,
    build_expanded_w11_fixture,
    build_labeled_dataset,
    build_w10_compatibility_fixture,
    load_benchmark_config,
    run_grouped_benchmark,
    trusted_exposure,
)

from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ML_ROOT / "xgb-v1-config.yaml"
REGISTRY_PATH = ML_ROOT / "feature-registry-v1.yaml"


@pytest.fixture(scope="module")
def config():
    return load_benchmark_config(
        CONFIG_PATH, load_registry(REGISTRY_PATH)
    )


@pytest.fixture(scope="module")
def smoke(tmp_path_factory):
    fixture = build_w10_compatibility_fixture()
    out = tmp_path_factory.mktemp("w11-integrity")
    result, _ = run_grouped_benchmark(
        fixture,
        load_registry(REGISTRY_PATH),
        load_benchmark_config(CONFIG_PATH, load_registry(REGISTRY_PATH)),
        out_dir=out,
        n_splits_override=2,
    )
    return result


def _series(trajectory, offsets):
    origin = _dt.datetime.fromisoformat(
        trajectory.origin_utc.replace("Z", "+00:00")
    )
    return CriticalEventSeries(
        run_id=trajectory.run_id,
        events=tuple(
            CriticalEvent(
                time=origin + _dt.timedelta(seconds=offset),
                ref=f"ev-{offset:g}",
            )
            for offset in offsets
        ),
        series_id=f"integrity-{trajectory.run_id}",
        coverage_end=origin
        + _dt.timedelta(seconds=trajectory.samples[-1].time_s),
    )


def _event_result_for(trajectory, series, samples, *, end, exposure, coverage):
    return _event_result(
        trajectory=trajectory,
        samples=samples,
        critical_events=_critical_event_inputs(trajectory, series),
        episode_policy=load_benchmark_config(
            CONFIG_PATH, load_registry(REGISTRY_PATH)
        ).baseline.episode_policy(),
        association_policy=load_benchmark_config(
            CONFIG_PATH, load_registry(REGISTRY_PATH)
        ).baseline.association_policy(),
        warning_definition="INTEGRITY_PROBE",
        evaluation_end_s=end,
        trusted_exposure_s=exposure,
        coverage_trustworthy=coverage,
    )


def test_w11_rows_do_not_explain_ewt_by_missing_latency(smoke):
    assert smoke.baseline_rows
    for row in smoke.baseline_rows:
        assert row["ewt"] == "NOT_ESTIMABLE"
        assert row["ewt_reason_code"] == EWT_REASON_NO_COMMON_TRAJECTORY
        assert "latency" not in row["ewt_reason"].lower()
        assert row["aiw"] == "NOT_ESTIMABLE"
        assert row["aiw_reason_code"] == AIW_REASON_MISSING_LATENCY_CHAIN
        assert "latency" in row["aiw_reason"].lower()


def test_ewt_positive_and_negative_do_not_require_command_ack():
    provenance = EWTProvenance(
        run_id="R1-RUN",
        event_id="EV-1",
        warning_definition="persistent-warning-v1",
        persistence_definition="sustained-v1",
    )
    common = dict(
        warning_present=True,
        warning_persistent=True,
        reactive_crossing_observed=True,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
        provenance=provenance,
    )
    early = compute_ewt(t_predictive_s=80.0, t_reactive_s=100.0, **common)
    late = compute_ewt(t_predictive_s=110.0, t_reactive_s=100.0, **common)
    assert early.ewt_s == 20.0
    assert late.ewt_s == -10.0
    assert early.status.value == "ESTIMABLE"
    assert late.status.value == "ESTIMABLE"


def test_trusted_exposure_excludes_internal_gap(config):
    trajectory, _ = build_trajectory(
        "R2-GAP",
        scenario="S2",
        seed=12,
        duration_s=180.0,
        door_start_s=40.0,
        critical_offsets_s=(100.0,),
        gap_start_s=60.0,
        gap_end_s=120.0,
    )
    exposure = trusted_exposure(
        trajectory,
        evaluation_end_s=180.0,
        max_continuity_gap_s=10.0,
    )
    assert exposure.trusted_duration_s == 119.0
    assert exposure.untrusted_duration_s == 61.0
    assert exposure.fully_observed is False


def test_trusted_exposure_excludes_invalid_interval(config):
    trajectory, _ = build_trajectory(
        "R2-INV",
        scenario="S2",
        seed=13,
        duration_s=180.0,
        door_start_s=40.0,
        critical_offsets_s=(100.0,),
        degrade_after_s=60.0,
    )
    exposure = trusted_exposure(
        trajectory,
        evaluation_end_s=180.0,
        max_continuity_gap_s=10.0,
    )
    assert exposure.trusted_duration_s == 59.0
    assert exposure.untrusted_duration_s == 121.0


def test_trusted_exposure_starts_at_first_trusted_observation(config):
    trajectory, _ = build_trajectory(
        "R2-LATE",
        scenario="S2",
        seed=14,
        duration_s=180.0,
        door_start_s=40.0,
        critical_offsets_s=(100.0,),
    )
    late = replace(trajectory, samples=trajectory.samples[10:])
    exposure = trusted_exposure(
        late,
        evaluation_end_s=180.0,
        max_continuity_gap_s=10.0,
    )
    assert exposure.first_trusted_observation_s == 10.0
    assert exposure.trusted_duration_s == 170.0
    assert exposure.untrusted_duration_s == 10.0


def test_trusted_exposure_excludes_tail_after_last_sample(config):
    trajectory, _ = build_trajectory(
        "R2-TAIL",
        scenario="S1",
        seed=15,
        duration_s=170.0,
    )
    exposure = trusted_exposure(
        trajectory,
        evaluation_end_s=180.0,
        max_continuity_gap_s=10.0,
    )
    assert exposure.trusted_duration_s == 170.0
    assert exposure.untrusted_duration_s == 10.0
    assert exposure.fully_observed is False


def test_warning_episode_cannot_extend_past_evaluation_cutoff(config):
    trajectory, _ = build_trajectory(
        "R2-CUT",
        scenario="S2",
        seed=21,
        duration_s=200.0,
        door_start_s=40.0,
        critical_offsets_s=(170.0,),
    )
    series = _series(trajectory, (170.0,))
    result = _event_result_for(
        trajectory,
        series,
        (
            WarningSample(time_s=154.0, state=WARNING, sample_id="w154"),
            WarningSample(time_s=155.5, state=WARNING, sample_id="w1555"),
        ),
        end=155.0,
        exposure=155.0,
        coverage=True,
    )
    assert len(result.episodes) == 1
    assert result.episodes[0].start_s == 154.0
    assert result.episodes[0].end_s == 154.0


def test_critical_event_after_cutoff_is_censored_not_dropped(config):
    trajectory, _ = build_trajectory(
        "R2-EVCUT",
        scenario="S2",
        seed=22,
        duration_s=200.0,
        door_start_s=40.0,
        critical_offsets_s=(170.0,),
    )
    series = _series(trajectory, (170.0,))
    baseline = _prepare_baseline_run(
        trajectory,
        series,
        hardware_config_id=HARDWARE_W11,
        config=config,
        evaluation_end_s=155.0,
    )
    assert len(baseline.event_inputs) == 1
    assert baseline.event_inputs[0].observed is False
    assert baseline.b0_events.metrics.censored_event_count == 1
    assert baseline.b0_events.metrics.eligible_critical_event_denominator == 0
    assert baseline.b0_events.metrics.missed_critical_events == 0


def test_untrusted_critical_event_is_counted_not_dropped(config):
    trajectory, _ = build_trajectory(
        "R2-EVUNTRUSTED",
        scenario="S2",
        seed=30,
        duration_s=120.0,
        door_start_s=40.0,
        critical_offsets_s=(100.0,),
    )
    origin = _dt.datetime.fromisoformat(
        trajectory.origin_utc.replace("Z", "+00:00")
    )
    series = CriticalEventSeries(
        run_id=trajectory.run_id,
        events=(
            CriticalEvent(
                time=origin + _dt.timedelta(seconds=100.0),
                trusted=False,
                ref="untrusted",
            ),
        ),
        series_id=f"integrity-untrusted-{trajectory.run_id}",
        coverage_end=origin
        + _dt.timedelta(seconds=trajectory.samples[-1].time_s),
    )
    baseline = _prepare_baseline_run(
        trajectory,
        series,
        hardware_config_id=HARDWARE_W11,
        config=config,
        evaluation_end_s=120.0,
    )
    assert len(baseline.event_inputs) == 1
    assert baseline.event_inputs[0].trusted is False
    assert baseline.b0_events.metrics.untrusted_event_count == 1
    assert baseline.b0_events.metrics.eligible_critical_event_denominator == 0


def test_critical_event_exactly_at_cutoff_is_eligible(config):
    trajectory, _ = build_trajectory(
        "R2-EVBOUND",
        scenario="S2",
        seed=23,
        duration_s=200.0,
        door_start_s=40.0,
        critical_offsets_s=(155.0,),
    )
    series = _series(trajectory, (155.0,))
    baseline = _prepare_baseline_run(
        trajectory,
        series,
        hardware_config_id=HARDWARE_W11,
        config=config,
        evaluation_end_s=155.0,
    )
    assert baseline.event_inputs[0].observed is True
    assert baseline.b0_events.metrics.eligible_critical_event_denominator == 1
    assert baseline.b0_events.metrics.missed_critical_events == 1


def test_incomplete_eventless_run_is_not_a_no_event_observation(config):
    trajectory, _ = build_trajectory(
        "R2-NOEV",
        scenario="S1",
        seed=24,
        duration_s=180.0,
        gap_start_s=60.0,
        gap_end_s=120.0,
    )
    series = _series(trajectory, ())
    exposure = trusted_exposure(
        trajectory,
        evaluation_end_s=180.0,
        max_continuity_gap_s=10.0,
    )
    assert exposure.fully_observed is False
    result = _event_result_for(
        trajectory,
        series,
        (WarningSample(time_s=10.0, state=WARNING, sample_id="w10"),),
        end=180.0,
        exposure=exposure.trusted_duration_s,
        coverage=exposure.fully_observed,
    )
    assert result.metrics.false_warning_episodes is None
    assert result.metrics.false_warning_episodes_per_eligible_hour is None
    event_types = [event["event_type"] for event in result.events if "event_type" in event]
    assert "CENSORED_OBSERVATION" in event_types
    assert "NO_EVENT_OBSERVATION" not in event_types


def test_zero_trusted_exposure_leaves_hour_rate_undefined(config):
    trajectory, _ = build_trajectory(
        "R2-ZERO",
        scenario="S1",
        seed=25,
        duration_s=60.0,
        degrade_after_s=0.0,
    )
    series = _series(trajectory, ())
    exposure = trusted_exposure(
        trajectory,
        evaluation_end_s=60.0,
        max_continuity_gap_s=10.0,
    )
    assert exposure.trusted_duration_s == 0.0
    assert exposure.fully_observed is False
    result = _event_result_for(
        trajectory,
        series,
        (WarningSample(time_s=10.0, state=WARNING, sample_id="w10"),),
        end=60.0,
        exposure=exposure.trusted_duration_s,
        coverage=exposure.fully_observed,
    )
    assert result.metrics.false_warning_episodes_per_eligible_hour is None
    assert "NO_EVALUABLE_TIME_DENOMINATOR" in result.metrics.undefined_reasons


def test_warning_at_cutoff_boundary_is_deterministic(config):
    trajectory, _ = build_trajectory(
        "R2-WBOUND",
        scenario="S1",
        seed=27,
        duration_s=200.0,
    )
    series = _series(trajectory, ())
    for sample_time, expected in ((155.0, 1), (155.5, 0)):
        result = _event_result_for(
            trajectory,
            series,
            (
                WarningSample(
                    time_s=sample_time, state=WARNING, sample_id=f"w{sample_time}"
                ),
            ),
            end=155.0,
            exposure=155.0,
            coverage=True,
        )
        assert result.metrics.episode_support == expected


def test_identical_warning_counts_use_trusted_hours(config):
    from coldguard_ml.xgb_benchmark import aggregate_event_results

    results = []
    durations = []
    for run_id, duration in (("R2-HOUR-A", 120.0), ("R2-HOUR-B", 240.0)):
        trajectory, _ = build_trajectory(
            run_id, scenario="S1", seed=26, duration_s=duration
        )
        exposure = trusted_exposure(
            trajectory,
            evaluation_end_s=duration,
            max_continuity_gap_s=10.0,
        )
        assert exposure.fully_observed is True
        durations.append(exposure.trusted_duration_s)
        results.append(
            _event_result_for(
                trajectory,
                _series(trajectory, ()),
                (WarningSample(time_s=10.0, state=WARNING, sample_id="w10"),),
                end=duration,
                exposure=exposure.trusted_duration_s,
                coverage=exposure.fully_observed,
            )
        )
    assert durations == [120.0, 240.0]
    summary = aggregate_event_results(results, duration_s=sum(durations))
    assert summary["unmatched_warnings"] == 2
    assert summary["false_warning_episodes_per_run"] == 1.0
    assert summary["false_warning_episodes_per_hour"] == 20.0
    assert summary["trusted_exposure_s"] == 360.0


def test_mixed_coverage_keeps_false_warning_burden_undefined(config):
    from coldguard_ml.xgb_benchmark import aggregate_event_results

    full, _ = build_trajectory("R2-MIX-FULL", scenario="S1", seed=28, duration_s=120.0)
    gap, _ = build_trajectory(
        "R2-MIX-GAP",
        scenario="S1",
        seed=29,
        duration_s=120.0,
        gap_start_s=40.0,
        gap_end_s=80.0,
    )
    results = []
    durations = []
    for trajectory in (full, gap):
        exposure = trusted_exposure(
            trajectory,
            evaluation_end_s=120.0,
            max_continuity_gap_s=10.0,
        )
        durations.append(exposure.trusted_duration_s)
        results.append(
            _event_result_for(
                trajectory,
                _series(trajectory, ()),
                (WarningSample(time_s=10.0, state=WARNING, sample_id="w10"),),
                end=120.0,
                exposure=exposure.trusted_duration_s,
                coverage=exposure.fully_observed,
            )
        )
    summary = aggregate_event_results(
        results,
        duration_s=sum(durations),
        untrusted_duration_s=40.0,
    )
    assert summary["coverage_trustworthy"] is False
    assert summary["false_warning_episodes_per_hour"] is None
    assert summary["false_warning_episodes_per_run"] is None
    assert "FALSE_WARNING_BURDEN_UNDEFINED_INCOMPLETE_COVERAGE" in summary[
        "undefined_reasons"
    ]
    assert summary["unmatched_warnings"] == 2


def test_baseline_and_xgb_rows_share_the_trusted_window(smoke):
    baseline = [row for row in smoke.baseline_rows if row["method"] == "B0_THRESHOLD"]
    xgb = [
        row
        for row in smoke.baseline_rows
        if row["method"].startswith("XGBOOST_V1_")
    ]
    assert baseline and xgb
    for base_row in baseline:
        pair = [
            row for row in xgb if row["fold_id"] == base_row["fold_id"]
        ][0]
        assert pair["trusted_exposure_s"] == base_row["trusted_exposure_s"]
        assert pair["untrusted_exposure_s"] == base_row["untrusted_exposure_s"]


def test_censor_after_cutoff_preserves_exact_boundary():
    from coldguard_ml.event_evaluator import CERTAINTY_INTERVAL, CriticalEventInput

    def event(time_s):
        return CriticalEventInput(
            event_id=f"EV-{time_s}",
            time_s=time_s,
            run_id="R",
            source_sha256="sha",
            definition_version="v1",
            source="probe",
            time_certainty=CERTAINTY_INTERVAL,
        )

    at, after = _censor_after_cutoff((event(100.0), event(101.0)), 100.0)
    assert at.observed is True
    assert after.observed is False
    assert after.censored is True


# ---------------------------------------------------------------------------
# Zero-evaluable-run refusal (W11 evaluation_end_by_run empty-population fix)
# ---------------------------------------------------------------------------


def _probe_variant(config, horizon_s):
    return replace(
        config,
        label=replace(
            config.label,
            horizon_s=float(horizon_s),
            spec_version="w11-empty-run-probe",
        ),
    )


def _scenario_only_fixture(scenario: str) -> BenchmarkFixture:
    source = build_expanded_w11_fixture()
    trajectories = tuple(
        trajectory
        for trajectory in source.development_trajectories
        if trajectory.run_id.startswith(f"CG-W11-{scenario}-")
    )
    run_infos = [
        RunInfo(
            run_id=trajectory.run_id,
            scenario_id=scenario,
            controller_id=SYNTHETIC_CONTROLLER,
            pair_id=f"SOLO-{trajectory.run_id}",
            hardware_config_id=HARDWARE_W11,
        )
        for trajectory in trajectories
    ]
    split = split_runs(
        run_infos,
        SplitConfig(
            proportions=SplitProportions(0.4, 0.4, 0.2),
            seed=42,
            controller_context="all-reactive-or-observational",
            min_groups_per_partition=1,
            hardware_lineage=HARDWARE_W11,
        ),
    )
    return BenchmarkFixture(
        dataset_id=f"W11_PROBE_{scenario}_ONLY",
        fixture_version=source.fixture_version,
        status=source.status,
        provenance=source.provenance,
        trajectories=trajectories,
        series_by_run={
            trajectory.run_id: source.series_by_run[trajectory.run_id]
            for trajectory in trajectories
        },
        split=split,
        hardware_config_by_run={
            trajectory.run_id: HARDWARE_W11 for trajectory in trajectories
        },
        limitations=("probe fixture",),
    )


def _censor_run_coverage(fixture: BenchmarkFixture, run_id: str) -> BenchmarkFixture:
    trajectory = next(
        item for item in fixture.trajectories if item.run_id == run_id
    )
    origin = _dt.datetime.fromisoformat(
        trajectory.origin_utc.replace("Z", "+00:00")
    )
    return replace(
        fixture,
        series_by_run={
            **fixture.series_by_run,
            run_id: replace(fixture.series_by_run[run_id], coverage_end=origin),
        },
    )


def test_horizon_with_zero_evaluable_runs_is_refused_not_a_raw_max(tmp_path):
    registry = load_registry(REGISTRY_PATH)
    config = load_benchmark_config(CONFIG_PATH, registry)
    fixture = build_expanded_w11_fixture()
    with pytest.raises(NonEstimableRunError) as caught:
        run_grouped_benchmark(
            fixture,
            registry,
            _probe_variant(config, 300.0),
            out_dir=tmp_path,
        )
    error = caught.value
    assert error.reason_code == NON_ESTIMABLE_RUN_REASON
    assert len(error.runs) == 8
    assert all(run_id.startswith("CG-W11-S1-") for run_id, _ in error.runs)
    assert all(reasons.get("CENSORED", 0) > 0 for _, reasons in error.runs)
    assert "zero evaluable label anchors" in str(error)


def test_one_fully_censored_run_refuses_the_declared_population(tmp_path):
    registry = load_registry(REGISTRY_PATH)
    config = load_benchmark_config(CONFIG_PATH, registry)
    fixture = build_expanded_w11_fixture()
    victim = next(
        trajectory.run_id
        for trajectory in fixture.development_trajectories
        if trajectory.run_id.startswith("CG-W11-S1-")
    )
    censored = _censor_run_coverage(fixture, victim)
    labeled = build_labeled_dataset(censored, registry, _probe_variant(config, 60.0))
    assert victim in labeled.run_ids
    assert victim not in {sample.run_id for sample in labeled.samples}
    assert labeled.positive_count > 0
    assert labeled.negative_count > 0
    with pytest.raises(NonEstimableRunError) as caught:
        run_grouped_benchmark(
            censored,
            registry,
            _probe_variant(config, 60.0),
            out_dir=tmp_path,
        )
    assert [run_id for run_id, _ in caught.value.runs] == [victim]


def test_fully_ineligible_population_is_refused_at_the_label_contract(tmp_path):
    registry = load_registry(REGISTRY_PATH)
    config = load_benchmark_config(CONFIG_PATH, registry)
    fixture = _scenario_only_fixture("S1")
    for run_id in (item.run_id for item in fixture.trajectories):
        fixture = _censor_run_coverage(fixture, run_id)
    with pytest.raises(BenchmarkError, match="no evaluable development labels") as caught:
        run_grouped_benchmark(
            fixture,
            registry,
            _probe_variant(config, 60.0),
            out_dir=tmp_path,
        )
    assert not isinstance(caught.value, NonEstimableRunError)


def test_single_class_population_never_yields_a_defined_ap(tmp_path):
    registry = load_registry(REGISTRY_PATH)
    config = load_benchmark_config(CONFIG_PATH, registry)
    fixture = _scenario_only_fixture("S2")
    result, models = run_grouped_benchmark(
        fixture,
        registry,
        _probe_variant(config, 300.0),
        out_dir=tmp_path,
        n_splits_override=4,
    )
    assert result.labeled.positive_count > 0
    assert result.labeled.negative_count == 0
    assert result.fold_runs
    assert all(run.status == "REFUSED" for run in result.fold_runs)
    assert all(run.reason == "SINGLE_CLASS_TRAINING_FOLD" for run in result.fold_runs)
    assert all(payload["status"] == "UNDEFINED" for payload in result.oof.values())
    assert "OOF_AP_UNDEFINED" in result.reason_codes
    assert result.model_artifact is None
    assert not models
    for row in result.baseline_rows:
        assert row["sample_ap"] is None
