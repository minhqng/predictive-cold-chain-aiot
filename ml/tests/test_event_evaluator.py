"""W09 event-level evaluator adversarial tests (task §14 items 23-36)."""

from __future__ import annotations

import pytest

from coldguard_ml.baselines import (
    B0_THRESHOLD,
    B1_HYSTERESIS,
    CERTAINTY_EXACT,
    CERTAINTY_INTERVAL,
    ReplayResult,
    TRANSITION_CRITERION,
    TRANSITION_ON,
)
from coldguard_ml.evaluation_contract import EWTProvenance, EWTStatus
from coldguard_ml.event_evaluator import (
    ASSOCIATION_POLICY_VERSION,
    EVENT_CRITICAL_EVENT,
    EVENT_CENSORED_OBSERVATION,
    EVENT_NO_EVENT_OBSERVATION,
    EVENT_TYPES,
    EVENT_UNTRUSTED_INTERVAL,
    EVENT_WARNING_EPISODE,
    EPISODE_POLICY_VERSION,
    WARNING,
    NO_WARNING,
    UNKNOWN,
    AssociationPolicy,
    ChatterPolicy,
    CriticalEventInput,
    EpisodePolicy,
    EventEvaluationError,
    WarningSample,
    aiw_boundary_status,
    analyze_s1_run,
    aggregate_s1,
    baseline_ewt,
    build_warning_episodes,
    critical_events_from_replay,
    evaluate_events,
    event_definitions,
)
from coldguard_ml.event_evaluator import METRIC_DEFINED, METRIC_UNDEFINED

STATUS = "SYNTHETIC_ILLUSTRATIVE"
SOURCE = "b" * 64
RUN = "RUN-1"


def _episode_policy(
    *,
    min_persistence=0.0,
    bridge_gap=2.0,
    bridge_unknown=False,
) -> EpisodePolicy:
    return EpisodePolicy(
        policy_version="ep-v1",
        min_persistence_s=min_persistence,
        bridge_gap_s=bridge_gap,
        bridge_unknown_gaps=bridge_unknown,
        status=STATUS,
        source="synthetic",
    )


def _association(
    *, pre=30.0, post=30.0
) -> AssociationPolicy:
    return AssociationPolicy(
        policy_version="assoc-v1",
        pre_window_s=pre,
        post_window_s=post,
        require_trusted_events=True,
        allow_censored_events=False,
        status=STATUS,
        source="synthetic",
    )


def _episodes(samples, policy=None):
    return build_warning_episodes(
        samples,
        policy or _episode_policy(),
        run_id=RUN,
        source_sha256=SOURCE,
        synthetic_control=True,
    )


def _event(
    event_id: str,
    time_s: float,
    *,
    observed=True,
    trusted=True,
    intervention=False,
    censored=False,
):
    return CriticalEventInput(
        event_id=event_id,
        time_s=time_s,
        run_id=RUN,
        source_sha256=SOURCE,
        definition_version="synthetic-def-v1",
        source="synthetic",
        observed=observed,
        censored=censored,
        trusted=trusted,
        intervention=intervention,
        time_certainty=CERTAINTY_INTERVAL,
    )


def _evaluate(
    episodes,
    events,
    *,
    coverage_trustworthy=True,
    eligible_runs=1,
    duration=600.0,
    untrusted=(),
):
    return evaluate_events(
        run_id=RUN,
        source_sha256=SOURCE,
        episodes=episodes,
        critical_events=events,
        episode_policy=_episode_policy(),
        association_policy=_association(),
        warning_definition="synthetic warning",
        coverage_trustworthy=coverage_trustworthy,
        eligible_run_count=eligible_runs,
        evaluable_duration_s=duration,
        untrusted_intervals=untrusted,
        synthetic_control=True,
    )


def _warning_samples(count: int, start=0.0, step=1.0):
    return tuple(
        WarningSample(
            time_s=start + index * step,
            state=WARNING,
            sample_id=f"S{index}",
        )
        for index in range(count)
    )


# ---------------------------------------------------------------------------
# Episode construction
# ---------------------------------------------------------------------------


def test_one_sustained_warning_is_one_episode():
    result = _episodes(_warning_samples(10))
    assert len(result.episodes) == 1
    assert result.episodes[0].sample_count == 10
    assert result.episodes[0].start_s == 0.0
    assert result.episodes[0].end_s == 9.0


def test_many_warning_samples_do_not_inflate_episode_count():
    result = _episodes(_warning_samples(60))
    assert len(result.episodes) == 1


def test_two_distinct_warning_runs_are_two_episodes():
    samples = (
        WarningSample(0.0, WARNING, "A"),
        WarningSample(1.0, WARNING, "B"),
        WarningSample(2.0, NO_WARNING, "C"),
        WarningSample(3.0, NO_WARNING, "D"),
        WarningSample(10.0, WARNING, "E"),
        WarningSample(11.0, WARNING, "F"),
    )
    result = _episodes(
        samples, _episode_policy(bridge_gap=2.0)
    )
    assert len(result.episodes) == 2


def test_duplicate_warning_samples_do_not_inflate_episodes():
    samples = (
        WarningSample(0.0, WARNING, "A"),
        WarningSample(0.0, WARNING, "A"),
        WarningSample(1.0, WARNING, "B"),
    )
    result = _episodes(samples)
    assert len(result.episodes) == 1
    assert result.episodes[0].sample_count == 2


def test_short_warning_below_persistence_is_discarded():
    samples = (
        WarningSample(0.0, WARNING, "A"),
        WarningSample(1.0, WARNING, "B"),
        WarningSample(2.0, NO_WARNING, "C"),
    )
    result = _episodes(
        samples, _episode_policy(min_persistence=5.0)
    )
    assert result.episodes == ()
    assert result.discarded
    assert result.discarded[0]["reason"] == "PERSISTENCE_BELOW_POLICY"


def test_brief_gap_is_bridged_when_policy_allows():
    samples = (
        WarningSample(0.0, WARNING, "A"),
        WarningSample(1.0, WARNING, "B"),
        WarningSample(2.0, NO_WARNING, "C"),
        WarningSample(3.0, WARNING, "D"),
        WarningSample(4.0, WARNING, "E"),
    )
    result = _episodes(samples, _episode_policy(bridge_gap=3.0))
    assert len(result.episodes) == 1


def test_unknown_sample_resets_when_not_bridged():
    samples = (
        WarningSample(0.0, WARNING, "A"),
        WarningSample(1.0, WARNING, "B"),
        WarningSample(2.0, UNKNOWN, "C"),
        WarningSample(3.0, WARNING, "D"),
        WarningSample(4.0, WARNING, "E"),
    )
    result = _episodes(
        samples, _episode_policy(bridge_gap=5.0, bridge_unknown=False)
    )
    assert len(result.episodes) == 2


def test_unknown_gap_can_be_bridged_only_when_declared():
    samples = (
        WarningSample(0.0, WARNING, "A"),
        WarningSample(1.0, WARNING, "B"),
        WarningSample(2.0, UNKNOWN, "C"),
        WarningSample(3.0, WARNING, "D"),
        WarningSample(4.0, WARNING, "E"),
    )
    result = _episodes(
        samples, _episode_policy(bridge_gap=5.0, bridge_unknown=True)
    )
    assert len(result.episodes) == 1
    assert result.episodes[0].censored is True


# ---------------------------------------------------------------------------
# Matching and denominators
# ---------------------------------------------------------------------------


def _single_episode(start=10.0, end=14.0):
    samples = tuple(
        WarningSample(time_s=start + index, state=WARNING, sample_id=f"S{index}")
        for index in range(int(end - start) + 1)
    )
    return _episodes(samples).episodes


def test_one_event_is_not_matched_repeatedly():
    episodes = _single_episode()
    duplicate_episode = _episodes(
        (WarningSample(10.0, WARNING, "D0"),)
        + tuple(
            WarningSample(10.0 + index, WARNING, f"D{index}")
            for index in range(1, 5)
        )
    ).episodes
    result = _evaluate(episodes + duplicate_episode, [_event("E1", 12.0)])
    assert result.metrics.true_matched_warning_episodes == 1
    assert result.metrics.unmatched_warning_episodes == 1


def test_multiple_candidate_warnings_choose_one_and_record_alternatives():
    episodes = list(_single_episode()) + list(
        _episodes(
            tuple(
                WarningSample(11.0 + index, WARNING, f"U{index}")
                for index in range(4)
            )
        ).episodes
    )
    result = _evaluate(episodes, [_event("E1", 12.0)])
    assert len(result.matches) == 1
    assert result.matches[0].alternative_episode_ids
    assert result.metrics.unmatched_warning_episodes == 1


def test_unmatched_warning_and_missed_event_are_both_reported():
    episodes = _single_episode(10.0, 11.0)
    result = _evaluate(
        episodes,
        [_event("E1", 100.0), _event("E2", 300.0)],
    )
    assert result.metrics.true_matched_warning_episodes == 0
    assert result.metrics.unmatched_warning_episodes == 1
    assert result.metrics.missed_critical_events == 2


def test_no_event_run_contributes_false_burden_only_when_observed():
    episodes = _single_episode(10.0, 11.0)
    observed = _evaluate(episodes, [])
    assert observed.metrics.false_warning_episodes == 1
    assert observed.metrics.false_warning_episodes_per_eligible_run == 1.0
    assert observed.metrics.false_warning_episodes_per_eligible_hour == pytest.approx(6.0)
    untrusted = _evaluate(episodes, [], coverage_trustworthy=False)
    assert untrusted.metrics.false_warning_episodes is None
    assert any(
        "COVERAGE_NOT_TRUSTWORTHY" in reason
        for reason in untrusted.metrics.undefined_reasons
    )


def test_censored_event_is_not_a_negative_control():
    episodes = _single_episode(10.0, 11.0)
    result = _evaluate(
        episodes,
        [_event("E1", 10.0, observed=False, censored=True)],
    )
    assert result.metrics.censored_event_count == 1
    assert result.metrics.missed_critical_events == 0
    assert result.metrics.event_recall is None


def test_untrusted_event_does_not_receive_precise_matching():
    episodes = _single_episode(10.0, 11.0)
    result = _evaluate(
        episodes,
        [_event("E1", 10.0, trusted=False)],
    )
    assert result.metrics.untrusted_event_count == 1
    assert result.metrics.true_matched_warning_episodes == 0


def test_zero_denominators_are_undefined_not_zero():
    result = _evaluate((), [], eligible_runs=0, duration=None)
    assert result.metrics.event_precision is None
    assert result.metrics.event_recall is None
    assert result.metrics.false_warning_episodes_per_eligible_run is None
    assert result.metrics.false_warning_episodes_per_eligible_hour is None
    assert "NO_ELIGIBLE_CRITICAL_EVENT_DENOMINATOR" in result.metrics.undefined_reasons


def test_association_window_boundary_is_declared_and_deterministic():
    episodes = _single_episode(10.0, 10.0)
    inside = _evaluate(episodes, [_event("E1", 40.0)])
    outside = _evaluate(episodes, [_event("E2", 41.0)])
    assert inside.metrics.true_matched_warning_episodes == 1
    assert outside.metrics.true_matched_warning_episodes == 0


def test_duplicate_critical_event_ids_are_rejected():
    with pytest.raises(EventEvaluationError):
        _evaluate(
            _single_episode(10.0, 11.0),
            [_event("E1", 10.0), _event("E1", 20.0)],
        )


def test_no_event_and_untrusted_observation_events_are_typed():
    no_event = _evaluate(_single_episode(10.0, 11.0), [])
    assert any(
        item["event_type"] == EVENT_NO_EVENT_OBSERVATION
        for item in no_event.events
    )
    untrusted = _evaluate(
        (),
        [],
        coverage_trustworthy=False,
        untrusted=({"start_s": 1.0, "end_s": 2.0, "reason": "STALE"},),
    )
    types = {item["event_type"] for item in untrusted.events}
    assert EVENT_CENSORED_OBSERVATION in types
    assert EVENT_UNTRUSTED_INTERVAL in types


def test_event_definitions_cover_all_required_types():
    definitions = event_definitions()
    assert {item["event_type"] for item in definitions} == set(EVENT_TYPES)
    assert len(EVENT_TYPES) == 8


# ---------------------------------------------------------------------------
# S1 analysis and EWT/AIW boundaries
# ---------------------------------------------------------------------------


class _ReplayStub:
    def __init__(self, transitions=()):
        self.baseline = B0_THRESHOLD
        self.transitions = tuple(transitions)
        self.coverage = type(
            "Coverage",
            (),
            {
                "observation_duration_s": 600.0,
                "evaluable_duration_s": 600.0,
                "unknown_duration_s": 0.0,
            },
        )()
        self.run_id = RUN
        self.source_sha256 = SOURCE

    def criterion_crossings(self):
        return tuple(
            item
            for item in self.transitions
            if getattr(item, "event_type", "") == TRANSITION_CRITERION
        )


def _analysis(evaluation, *, eligible=True, coverage=True):
    return analyze_s1_run(
        _ReplayStub(),
        evaluation,
        eligibility_status=(
            "ELIGIBLE_FOR_S1_DATASET" if eligible else "BLOCKED"
        ),
        eligibility_reasons=() if eligible else ("A_LEDGER_INVALID",),
        chatter_policy=ChatterPolicy(
            max_toggles=2, window_s=10.0, status=STATUS, source="synthetic"
        ),
        coverage_trustworthy=coverage,
        eligible_run_count=1 if eligible else 0,
        synthetic_control=True,
    )


def test_s1_metrics_are_gated_by_eligibility():
    evaluation = _evaluate(_single_episode(10.0, 11.0), [])
    eligible = _analysis(evaluation, eligible=True)
    assert eligible.false_warning_episode_count == 1
    blocked = _analysis(evaluation, eligible=False)
    assert blocked.false_warning_episode_count is None
    assert blocked.outcome_status == METRIC_UNDEFINED


def test_s1_unknown_outcome_is_not_a_negative():
    evaluation = _evaluate(
        _single_episode(10.0, 11.0), [], coverage_trustworthy=False
    )
    analysis = _analysis(evaluation, eligible=True, coverage=False)
    assert analysis.false_warning_episode_count is None
    assert analysis.outcome_status == METRIC_UNDEFINED


def test_no_eligible_s1_run_yields_not_established():
    analysis = _analysis(
        _evaluate(_single_episode(10.0, 11.0), []), eligible=False
    )
    aggregate = aggregate_s1([analysis], synthetic_control=True)
    assert aggregate.eligible_run_count == 0
    assert aggregate.false_warning_episodes_per_eligible_run is None
    assert aggregate.stability_status == "NOT_ESTABLISHED"


def test_ewt_negative_and_no_warning_are_preserved():
    provenance = EWTProvenance(
        run_id=RUN,
        event_id="E1",
        warning_definition="synthetic",
        persistence_definition="synthetic",
    )
    late = baseline_ewt(
        t_predictive_s=200.0,
        t_reactive_s=160.0,
        warning_present=True,
        warning_persistent=True,
        reactive_event_type=TRANSITION_CRITERION,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
        provenance=provenance,
    )
    assert late.status is EWTStatus.ESTIMABLE
    assert late.ewt_s == -40.0
    missing = baseline_ewt(
        t_predictive_s=None,
        t_reactive_s=160.0,
        warning_present=False,
        warning_persistent=False,
        reactive_event_type=TRANSITION_CRITERION,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
        provenance=provenance,
    )
    assert missing.status is EWTStatus.MISSING_WARNING


def test_controller_b_intervention_blocks_naive_ewt():
    provenance = EWTProvenance(
        run_id=RUN,
        event_id="E1",
        warning_definition="synthetic",
        persistence_definition="synthetic",
    )
    result = baseline_ewt(
        t_predictive_s=100.0,
        t_reactive_s=160.0,
        warning_present=True,
        warning_persistent=True,
        reactive_event_type=TRANSITION_CRITERION,
        trajectory_non_intervened=False,
        timestamps_trusted=True,
        provenance=provenance,
    )
    assert result.status is EWTStatus.INADMISSIBLE_INTERVENED_TRAJECTORY
    assert result.ewt_s is None


def test_on_transition_is_not_a_thermal_critical_crossing():
    provenance = EWTProvenance(
        run_id=RUN,
        event_id="E1",
        warning_definition="synthetic",
        persistence_definition="synthetic",
    )
    result = baseline_ewt(
        t_predictive_s=100.0,
        t_reactive_s=160.0,
        warning_present=True,
        warning_persistent=True,
        reactive_event_type=TRANSITION_ON,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
        provenance=provenance,
    )
    assert result.status is EWTStatus.MISSING_REACTIVE_CROSSING
    assert "not a thermal criterion crossing" in result.reason


def test_aiw_is_not_synthesized():
    status = aiw_boundary_status()
    assert status["status"] == "NOT_ESTIMABLE"
    assert status["synthetic_latency_allowed"] is False
