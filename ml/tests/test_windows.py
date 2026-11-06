"""B-W02-03 verification: causal run-bounded windows.

Focus (Doc `03` §46; Doc `02` §19.4; register LRK-02/03/13/14):
* windows exist only after the split; the API refuses split-less use;
* a window at t owns exactly the observations with time in ``(t - L, t]``;
* mutating future observations cannot change a window at t (LRK-03);
* duplicated arrivals collapse; identity/order contradictions raise
  instead of being silently repaired (§1.2 / LRK-13);
* shuffled arrival order yields identical windows (determinism);
* windows never cross run or boot boundaries;
* quality rollups trace invalid/absent channels; no zero fill
  (LRK-14); ``UNKNOWN`` door is preserved.
"""

from __future__ import annotations

import datetime as _dt
import math
import random
from dataclasses import replace

import pytest

from coldguard_ml import (
    IdentityContradictionError,
    RunInfo,
    SplitConfig,
    SplitProportions,
    SplitResult,
    SyntheticRunSpec,
    WindowConfig,
    WindowError,
    build_synthetic_run,
    canonical_order,
    generate_windows,
    split_runs,
    window_anchors,
)

UTC = _dt.timezone.utc
START = _dt.datetime(2026, 1, 1, tzinfo=UTC)


def _split(run_ids: tuple[str, ...]) -> SplitResult:
    infos = [
        RunInfo(
            run_id=run_id,
            scenario_id="S1",
            controller_id="CONTROLLER-A",
            hardware_config_id="CG-HW-001",
        )
        for run_id in run_ids
    ]
    return split_runs(
        infos,
        SplitConfig(
            proportions=SplitProportions(1 / 3, 1 / 3, 1 / 3),
            seed=3,
            controller_context="all-reactive-or-observational",
        ),
    )


_SPLIT = _split(("CG-S1-A-001", "CG-S2-A-001", "CG-S4-A-001"))


def _partition_of(run_id: str) -> str:
    partition = _SPLIT.partition_of(run_id)
    assert partition is not None, f"{run_id} is not partitioned"
    return partition


def _run(run_id: str, **spec_overrides):
    base: dict = dict(run_id=run_id, scenario_id="S1", seed=5)
    base.update(spec_overrides)
    return build_synthetic_run(SyntheticRunSpec(**base))


def test_window_generation_refuses_without_split():
    run = _run("CG-S1-A-001")
    with pytest.raises(WindowError, match="without a split manifest"):
        generate_windows(run.observations, None, "train")  # type: ignore[arg-type]


def test_window_owns_exactly_the_past_inclusive_of_anchor():
    run = _run("CG-S1-A-001")
    partition = _partition_of("CG-S1-A-001")
    windows = generate_windows(run.observations, _SPLIT, partition)
    times = sorted(o.time for o in run.observations)
    anchor_time = times[45]
    window = next(w for w in windows if w.prediction_time == anchor_time)
    assert window.window_start == anchor_time - _dt.timedelta(seconds=30.0)
    observed_times = [o.time for o in window.observations]
    assert all(window.window_start < t <= anchor_time for t in observed_times)
    later = [t for t in times if t > anchor_time]
    assert later and not any(t > anchor_time for t in observed_times)
    # The anchor sample itself is inside the window (inclusive right end).
    assert window.observations[-1].time == anchor_time


def test_lrk03_future_mutation_cannot_change_window_at_t():
    run = _run("CG-S1-A-001")
    partition = _partition_of("CG-S1-A-001")
    baseline = generate_windows(run.observations, _SPLIT, partition)
    times = sorted(o.time for o in run.observations)
    anchor_time = times[20]

    mutated_rows = [
        replace(o, t1_c=100.0) if o.time > anchor_time else o for o in run.observations
    ]
    mutated = generate_windows(mutated_rows, _SPLIT, partition)

    before = next(w for w in baseline if w.prediction_time == anchor_time)
    after = next(w for w in mutated if w.prediction_time == anchor_time)
    assert before == after
    assert before.quality_counts == after.quality_counts

    # ...while windows that DO contain the mutated sample move (evidence the
    # mutation went through, so the test is not vacuous).
    later_time = times[75]
    late_before = next(w for w in baseline if w.prediction_time == later_time)
    late_after = next(w for w in mutated if w.prediction_time == later_time)
    assert late_before != late_after


def test_shuffled_and_duplicated_arrivals_produce_identical_windows():
    run = _run("CG-S1-A-001")
    partition = _partition_of("CG-S1-A-001")
    rows = list(run.observations)
    shuffled = list(rows)
    random.Random(99).shuffle(shuffled)

    duplicate_arrival = replace(
        rows[5],
        backend_received_at=rows[5].backend_received_at + _dt.timedelta(milliseconds=50),
    )
    duplicated_rows = list(shuffled) + [duplicate_arrival]

    windows = generate_windows(rows, _SPLIT, partition)
    assert generate_windows(shuffled, _SPLIT, partition) == windows
    assert generate_windows(duplicated_rows, _SPLIT, partition) == windows


def test_identity_contradiction_and_order_corruption_raise():
    run = _run("CG-S1-A-001")
    partition = _partition_of("CG-S1-A-001")
    rows = list(run.observations)
    conflicting = rows + [
        replace(rows[7], time=rows[7].time + _dt.timedelta(seconds=0.5))
    ]
    with pytest.raises(IdentityContradictionError):
        generate_windows(conflicting, _SPLIT, partition)


def test_foreign_and_cross_partition_rows_are_rejected():
    run = _run("CG-S1-A-001")
    partition = _partition_of("CG-S1-A-001")
    other_run_id = next(
        rid
        for rid, p in (
            (rid, _SPLIT.partition_of(rid))
            for rid in ("CG-S2-A-001", "CG-S4-A-001")
        )
        if p != partition
    )
    other_rows = _run(other_run_id).observations
    with pytest.raises(WindowError, match="foreign-partition"):
        generate_windows(other_rows, _SPLIT, partition)
    with pytest.raises(WindowError, match="not part of the supplied split"):
        generate_windows(_run("CG-S9-A-999").observations, _SPLIT, partition)


def test_windows_never_cross_run_or_boot_boundaries():
    run = _run("CG-S1-A-001", boot_sessions=2)
    partition = _partition_of("CG-S1-A-001")
    windows = generate_windows(run.observations, _SPLIT, partition)
    assert windows
    for window in windows:
        assert all(o.boot_id == window.boot_id for o in window.observations)
        assert all(o.run_id == window.run_id for o in window.observations)
    boots = {w.boot_id for w in windows}
    assert len(boots) == 2  # one anchor set per boot


def test_quality_rollups_trace_absence_unknown_and_quality():
    run = _run("CG-S6-A-001", scenario_id="S6")
    # S6 data needs CG-S6-A-001 inside the split — extend the split fixture.
    extended = split_runs(
        [_split_info(r) for r in ("CG-S1-A-001", "CG-S6-A-001", "CG-S4-A-001")],
        SplitConfig(
            proportions=SplitProportions(1 / 3, 1 / 3, 1 / 3),
            seed=3,
            controller_context="all-reactive-or-observational",
        ),
    )
    partition = extended.partition_of("CG-S6-A-001")
    windows = generate_windows(run.observations, extended, partition)
    late = next(
        w for w in windows if w.prediction_time >= START + _dt.timedelta(seconds=62.0)
    )
    counts = late.absent_counts_by_channel
    assert counts["cooling_voltage_v"] > 0
    assert counts["t2_c"] > 0
    assert late.quality_counts_by_section["electrical"]["INVALID"] > 0
    # UNKNOWN door and None values ride along verbatim — never converted.
    unknown_rows = [o for o in late.observations if o.door_state == "UNKNOWN"]
    assert unknown_rows
    electrical_absent = [o for o in late.observations if o.cooling_voltage_v is None]
    assert electrical_absent and all(
        o.cooling_current_a is None for o in electrical_absent
    )


def test_anchor_stride_selects_every_nth_sorted_sample():
    run = _run("CG-S1-A-001")
    partition = _partition_of("CG-S1-A-001")
    config = WindowConfig(window_length_s=30.0, anchor_stride=5)
    windows = generate_windows(run.observations, _SPLIT, partition, config)
    ordered = canonical_order(run.observations)
    assert [w.prediction_time for w in windows] == [o.time for o in ordered[::5]]
    assert window_anchors(ordered, config) == tuple(ordered[::5])
    assert len(windows) == 18


def test_window_config_validation():
    with pytest.raises(WindowError, match="window_length_s"):
        WindowConfig(window_length_s=0)
    with pytest.raises(WindowError, match="anchor_stride"):
        WindowConfig(anchor_stride=0)


@pytest.mark.parametrize(
    "value", [True, 0, -1.0, math.nan, math.inf, -math.inf, 1e308, 10**400]
)
def test_window_length_rejects_nonphysical_numbers(value):
    with pytest.raises(WindowError, match="window_length_s"):
        WindowConfig(window_length_s=value)


@pytest.mark.parametrize("value", [True, 0, -1, 1.0, "1"])
def test_anchor_stride_rejects_non_integers(value):
    with pytest.raises(WindowError, match="anchor_stride"):
        WindowConfig(anchor_stride=value)


def test_valid_window_numeric_parameters_keep_semantics():
    config = WindowConfig(window_length_s=30, anchor_stride=2)
    assert config.window_length_s == 30
    assert config.anchor_stride == 2
    run = _run("CG-S1-A-001")
    partition = _partition_of("CG-S1-A-001")
    windows = generate_windows(run.observations, _SPLIT, partition, config)
    assert windows == generate_windows(tuple(run.observations), _SPLIT, partition, config)


def test_sequence_and_one_shot_iterator_inputs_produce_identical_windows():
    run = _run("CG-S1-A-001")
    partition = _partition_of("CG-S1-A-001")
    rows = list(run.observations)

    from_list = generate_windows(rows, _SPLIT, partition)
    from_tuple = generate_windows(tuple(rows), _SPLIT, partition)
    from_iterator = generate_windows(iter(rows), _SPLIT, partition)
    from_generator = generate_windows((row for row in rows), _SPLIT, partition)

    assert from_list == from_tuple == from_iterator == from_generator
    assert len(from_tuple) == len(rows) == 90


def test_empty_one_shot_iterator_follows_empty_input_policy():
    partition = _partition_of("CG-S1-A-001")
    assert generate_windows(iter(()), _SPLIT, partition) == ()
    assert generate_windows((), _SPLIT, partition) == ()
    assert generate_windows((row for row in ()), _SPLIT, partition) == ()


def test_one_shot_iterator_still_rejects_foreign_partition_rows():
    partition = _partition_of("CG-S1-A-001")
    other_run_id = next(
        rid
        for rid in ("CG-S2-A-001", "CG-S4-A-001")
        if _SPLIT.partition_of(rid) != partition
    )
    other_rows = _run(other_run_id).observations
    with pytest.raises(WindowError, match="foreign-partition"):
        generate_windows((row for row in other_rows), _SPLIT, partition)


def test_shuffled_one_shot_iterator_preserves_canonical_order():
    run = _run("CG-S1-A-001")
    partition = _partition_of("CG-S1-A-001")
    rows = list(run.observations)
    shuffled = list(rows)
    random.Random(17).shuffle(shuffled)

    assert generate_windows((row for row in shuffled), _SPLIT, partition) == (
        generate_windows(rows, _SPLIT, partition)
    )


def _split_info(run_id: str) -> RunInfo:
    return RunInfo(
        run_id=run_id,
        scenario_id="S1",
        controller_id="CONTROLLER-A",
        hardware_config_id="CG-HW-001",
    )
