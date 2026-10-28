"""B-W02-04 verification: horizon labels y_t(H).

Focus (Doc `03` §§41–45; register LRK-10):
* the qualifying interval is ``(t, t+H]`` — an event exactly at t does NOT
  qualify, an event exactly at t+H DOES;
* a definite ``0`` requires complete horizon coverage; incomplete coverage
  is the explicit ``CENSORED`` status — never an automatic negative;
* untrusted critical-state information inside the horizon is the explicit
  ``UNTRUSTED_INFO`` status — never a silent negative/positive;
* label records carry the LRK-10 identity fields verbatim;
* label derivation is independent of what a window contains (future
  events beyond t+H never change a label).
"""

from __future__ import annotations

import datetime as _dt

import pytest

from coldguard_ml import (
    CriticalEvent,
    CriticalEventSeries,
    LabelError,
    LabelSpec,
    LabelStatus,
    SyntheticRunSpec,
    build_synthetic_run,
    build_synthetic_runs,
    generate_label_records,
    generate_windows,
    labels_and_windows,
)

UTC = _dt.timezone.utc
T0 = _dt.datetime(2026, 1, 1, tzinfo=UTC)
RUN_ID = "CG-S1-A-001"
SPEC = LabelSpec(horizon_s=60.0, spec_version="provisional-v0")


def _moment(offset_s: float) -> _dt.datetime:
    return T0 + _dt.timedelta(seconds=offset_s)


def _series(
    moments: tuple[float, ...] = (),
    *,
    covered_until: float = 90.0,
    run_id: str = RUN_ID,
) -> CriticalEventSeries:
    events = tuple(
        CriticalEvent(time=_moment(m), trusted=True, ref=f"fixture:{m}") for m in moments
    )
    return CriticalEventSeries(
        run_id=run_id,
        events=events,
        series_id=f"fixture-series:{run_id}",
        coverage_end=_moment(covered_until) if covered_until is not None else None,
    )


def test_event_at_horizon_end_qualifies_inclusive():
    # event at 40s, horizon 60: anchor t = -20s ⇒ t + H == 40 ⇒ qualifies.
    records = generate_label_records(
        RUN_ID,
        [(_moment(-20.0), "a-inclusive")],
        _series((40.0,)),
        SPEC,
        coverage_end=_moment(90.0),
    )
    (record,) = records
    assert record.status is LabelStatus.EVALUABLE
    assert record.y == 1
    assert record.label_interval == (
        _moment(-20.0),
        _moment(40.0),
    )
    assert record.matched_event is not None and record.matched_event.time == _moment(40.0)


def test_event_exactly_at_t_is_excluded_by_open_left():
    # anchor exactly at the event instant: (t, t+H] excludes t itself.
    # Coverage must reach t+H = 100s for the definite 0 decision.
    records = generate_label_records(
        RUN_ID,
        [(_moment(40.0), "a-open-left")],
        _series((40.0,), covered_until=100.0),
        SPEC,
        coverage_end=None,
    )
    (record,) = records
    assert record.status is LabelStatus.EVALUABLE
    assert record.y == 0
    assert record.matched_event is None


def test_event_beyond_t_plus_h_is_excluded():
    # event at 61s: anchor 1.0 has interval (1, 61] → EVENT qualifies.
    inside = generate_label_records(
        RUN_ID, [(_moment(1.0), "a-inside")], _series((61.0,)), SPEC,
        coverage_end=_moment(90.0),
    )
    assert inside[0].y == 1
    # anchor 0.5 has interval (0.5, 60.5] → 61 is strictly beyond → no event.
    outside = generate_label_records(
        RUN_ID, [(_moment(0.5), "a-outside")], _series((61.0,)), SPEC,
        coverage_end=_moment(90.0),
    )
    assert outside[0].y == 0
    assert outside[0].status is LabelStatus.EVALUABLE


def test_incomplete_horizon_is_censored_never_negative():
    covered_until_moment = _moment(70.0)
    series = CriticalEventSeries(
        run_id=RUN_ID,
        events=(),
        series_id="fixture-series:no-events",
        coverage_end=covered_until_moment,
    )
    # anchor 30s: interval (30, 90]; coverage ends at 70 < 90 → CENSORED.
    censored = generate_label_records(RUN_ID, [(_moment(30.0), "a")], series, SPEC,
                                      coverage_end=None)
    assert censored[0].status is LabelStatus.CENSORED
    assert censored[0].y is None
    # anchor 9s: interval (9, 69]; 70 >= 69 → the very same series gives 0.
    definite = generate_label_records(RUN_ID, [(_moment(9.0), "b")], series, SPEC,
                                      coverage_end=None)
    assert definite[0].status is LabelStatus.EVALUABLE
    assert definite[0].y == 0


def test_untrusted_event_info_is_explicit_never_a_label():
    series = CriticalEventSeries(
        run_id=RUN_ID,
        events=(CriticalEvent(time=_moment(30.0), trusted=False, ref="suspect"),),
        series_id="fixture-series:untrusted",
        coverage_end=_moment(90.0),
    )
    records = generate_label_records(
        RUN_ID, [(_moment(20.0), "a")], series, SPEC, coverage_end=None
    )
    (record,) = records
    assert record.status is LabelStatus.UNTRUSTED_INFO
    assert record.y is None
    assert record.matched_event is None


def test_trusted_event_wins_over_untrusted_inside_the_horizon():
    events = (
        CriticalEvent(time=_moment(30.0), trusted=False, ref="suspect"),
        CriticalEvent(time=_moment(35.0), trusted=True, ref="met-ledger"),
    )
    series = CriticalEventSeries(
        run_id=RUN_ID, events=events, series_id="fixture-series:mixed",
        coverage_end=_moment(90.0),
    )
    records = generate_label_records(
        RUN_ID, [(_moment(20.0), "a")], series, SPEC, coverage_end=None
    )
    assert records[0].status is LabelStatus.EVALUABLE
    assert records[0].y == 1
    assert records[0].matched_event is not None
    assert records[0].matched_event.time == _moment(35.0)


def test_series_coverage_overrides_caller_coverage():
    series = CriticalEventSeries(
        run_id=RUN_ID, events=(), series_id="fixture-series:short",
        coverage_end=_moment(70.0),
    )
    # The caller claims coverage to 90s, but the series (the closer authority)
    # stops at 70s: anchor 30 ⇒ CENSORED, not y=0.
    records = generate_label_records(
        RUN_ID, [(_moment(30.0), "a")], series, SPEC, coverage_end=_moment(90.0)
    )
    assert records[0].status is LabelStatus.CENSORED


def test_missing_coverage_fails_explicitly():
    series = CriticalEventSeries(
        run_id=RUN_ID, events=(), series_id="fixture-series:no-coverage",
        coverage_end=None,
    )
    with pytest.raises(LabelError, match="coverage is unknown"):
        generate_label_records(RUN_ID, [(_moment(0.0), "a")], series, SPEC,
                               coverage_end=None)


def test_series_run_mismatch_fails():
    series = _series((40.0,), run_id="CG-S3-A-001")
    with pytest.raises(LabelError, match="not 'CG-S1-A-001'"):
        generate_label_records(RUN_ID, [(_moment(0.0), "a")], series, SPEC,
                               coverage_end=_moment(90))


def test_label_records_carry_lrk10_identity():
    spec = LabelSpec(
        horizon_s=60.0,
        spec_version="provisional-v0",
        representative_temperature="t3_c",
        boundary_c=4.0,
        frozen_at=None,  # PROVISIONAL until the Doc `03` §42–44 freeze
    )
    records = generate_label_records(
        RUN_ID,
        [(_moment(0.0), "anchor-ref"), (_moment(1.0), 12345)],
        _series((40.0,)),
        spec,
        coverage_end=_moment(90.0),
    )
    assert [r.anchor_ref for r in records] == ["anchor-ref", 12345]
    assert records[0].spec is spec
    assert records[0].horizon_s == 60.0
    assert records[0].series_id == "fixture-series:CG-S1-A-001"
    assert records[0].spec_identity == {
        "horizon_s": 60.0,
        "spec_version": "provisional-v0",
        "representative_temperature": "t3_c",
        "boundary_c": 4.0,
        "frozen_at": None,
    }
    assert records[1].label_interval == (_moment(1.0), _moment(61.0))


def test_future_events_beyond_horizon_do_not_change_labels():
    before_series = _series((40.0,), covered_until=90.0)
    after_series = _series((40.0, 200.0), covered_until=90.0)
    before = generate_label_records(RUN_ID, [(_moment(0.0), "a")], before_series, SPEC,
                                    coverage_end=_moment(90.0))
    after = generate_label_records(RUN_ID, [(_moment(0.0), "a")], after_series, SPEC,
                                   coverage_end=_moment(90.0))
    assert before == after
    # (The anchor's y stays 1: 40s is in (0, 60]; 200s is far beyond.)
    assert before[0].y == 1


def test_label_spec_validation():
    with pytest.raises(LabelError, match="horizon_s"):
        LabelSpec(horizon_s=0.0, spec_version="v")
    with pytest.raises(LabelError, match="horizon_s"):
        LabelSpec(horizon_s=-5.0, spec_version="v")
    with pytest.raises(LabelError, match="spec_version"):
        LabelSpec(horizon_s=60.0, spec_version="   ")


def test_series_rejects_duplicates_and_sorts_canonically():
    with pytest.raises(LabelError, match="duplicate critical-event"):
        CriticalEventSeries(
            run_id=RUN_ID,
            events=(
                CriticalEvent(time=_moment(40.0), trusted=True),
                CriticalEvent(time=_moment(40.0), trusted=True),
            ),
            series_id="bad",
        )
    series = _series((50.0, 40.0), covered_until=90.0)
    assert [e.time for e in series.events] == [_moment(40.0), _moment(50.0)]


def test_labels_and_windows_integrates_with_window_generator_and_keeps_order():
    from coldguard_ml import (
        RunInfo,
        SplitConfig,
        SplitProportions,
        split_runs,
    )

    runs = build_synthetic_runs(
        [
            SyntheticRunSpec(
                run_id="CG-S1-A-001", scenario_id="S1", seed=5, critical_event_offset_s=40.0
            ),
            SyntheticRunSpec(run_id="CG-S4-A-001", scenario_id="S4", seed=6),
            SyntheticRunSpec(run_id="CG-S5-A-001", scenario_id="S5", seed=7),
        ]
    )
    run = next(r for r in runs if r.run_id == "CG-S1-A-001")
    split = split_runs(
        [
            RunInfo(
                run_id=r.run_id,
                scenario_id=r.spec.scenario_id,
                controller_id=r.spec.controller_id,
                hardware_config_id="CG-HW-001",
            )
            for r in runs
        ],
        SplitConfig(proportions=SplitProportions(1 / 3, 1 / 3, 1 / 3), seed=2,
                    controller_context="all-reactive-or-observational"),
    )
    partition = split.partition_of("CG-S1-A-001")
    windows = generate_windows(run.observations, split, partition)
    pairs = labels_and_windows(
        windows,
        {r.run_id: r.critical_series for r in runs},
        SPEC,
        trajectory_ends={r.run_id: r.observations[-1].time for r in runs},
    )
    assert len(pairs) == len(windows)
    assert [w for w, _ in pairs] == list(windows)  # window order preserved, windows unchanged
    statuses = {record.status for _, record in pairs}
    assert statuses <= {LabelStatus.EVALUABLE, LabelStatus.CENSORED}
    positives = [window for window, record in pairs if record.y == 1]
    assert positives, "event at 40s must be inside some anchors' horizons"
    # Traceability: matched label series identity rides the record.
    assert all(record.series_id == run.critical_series.series_id for _, record in pairs)
