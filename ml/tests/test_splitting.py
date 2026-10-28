"""B-W02-02 verification: leakage-safe grouped splitting.

Focus (Doc `03` §§46–49; register LRK-01/02/08/09/15):
* grouping unit ``run_id``; pair arms are ONE independent group and never
  straddle partitions;
* deterministic per (runs, config, seed); identical for shuffled input
  order (LRK-01 replay);
* predictive-closed-loop runs excluded with recorded reason unless the
  caller opts into the variant artifact (LRK-09);
* invalid runs excluded with the A-ledger reason and never re-validated;
* explicit failure below the min-groups floor (no silent leakage);
* hardware lineage recorded; multi-config input requires an explicit
  registered exception (LRK-15);
* sklearn-group-semantics sanity on the recorded group ids.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from coldguard_ml import (
    RunInfo,
    SplitConfig,
    SplitError,
    SplitProportions,
    split_runs,
)

UTC = _dt.timezone.utc
WHEN = _dt.datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
GIT = "1" * 40


def _info(
    run_id: str,
    *,
    pair: str | None = None,
    controller: str = "CONTROLLER-A",
    hardware: str = "CG-HW-001",
    valid: bool = True,
    invalid_reason: str | None = None,
) -> RunInfo:
    return RunInfo(
        run_id=run_id,
        scenario_id="S1",
        controller_id=controller,
        pair_id=pair,
        hardware_config_id=hardware,
        is_valid=valid,
        invalid_reason=invalid_reason,
    )


def _config(seed: int = 7, **overrides) -> SplitConfig:
    base = dict(
        proportions=SplitProportions(1 / 3, 1 / 3, 1 / 3),
        seed=seed,
        controller_context="all-reactive-or-observational",
    )
    base.update(overrides)
    return SplitConfig(**base)


def _six_infos() -> list[RunInfo]:
    return [
        _info("CG-S1-A-001"),
        _info("CG-S2-A-001", pair="CG-S2-A-001"),
        _info("CG-S2-B-001", pair="CG-S2-A-001"),
        _info("CG-S4-A-001"),
        _info("CG-S5-A-001"),
        _info("CG-S6-A-001"),
    ]


def test_every_run_is_partitioned_exactly_once():
    result = split_runs(_six_infos(), _config())
    assigned = [
        run for partition in ("train", "validation", "test") for run in result.runs_in(partition)
    ]
    assert sorted(assigned) == sorted(info.run_id for info in _six_infos())
    assert len(result.group_of) == len(assigned)


def test_pair_arms_share_one_partition_and_are_recorded_as_lineage():
    result = split_runs(_six_infos(), _config(seed=42))
    a, b = "CG-S2-A-001", "CG-S2-B-001"
    assert result.partition_of(a) == result.partition_of(b)
    (entry,) = result.pair_lineage
    assert entry == {
        "pair_id": "CG-S2-A-001",
        "run_ids": sorted([a, b]),
        "partition": result.partition_of(a),
    }
    # The arms count as ONE independent group: 6 runs -> 5 groups.
    assert len(set(result.group_of.values())) == 5
    assert result.group_of[a] == "CG-S2-A-001"
    assert result.group_of[a] == result.group_of[b]


def test_same_seed_replay_and_shuffled_input_identical():
    infos = _six_infos()
    first = split_runs(infos, _config(seed=3))
    second = split_runs(infos, _config(seed=3))
    assert (first.train_runs, first.validation_runs, first.test_runs) == (
        second.train_runs,
        second.validation_runs,
        second.test_runs,
    )
    reversed_input = split_runs(list(reversed(infos)), _config(seed=3))
    assert (first.train_runs, first.validation_runs, first.test_runs) == (
        reversed_input.train_runs,
        reversed_input.validation_runs,
        reversed_input.test_runs,
    )
    assert first.pair_lineage == reversed_input.pair_lineage


def test_predictive_exclusion_records_reason_and_variant_optin():
    predictive = frozenset({"CONTROLLER-P"})
    infos = [
        _info("CG-S1-A-001"),
        _info("CG-S2-A-001", controller="CONTROLLER-P"),
        _info("CG-S4-A-001"),
        _info("CG-S5-A-001"),
    ]
    core = split_runs(infos, _config(predictive_controller_ids=predictive))
    excluded = {e.run_id: e.reason for e in core.excluded_runs}
    assert excluded == {"CG-S2-A-001": "predictive-closed-loop"}
    assert "CG-S2-A-001" not in core.group_of
    assert sorted(core.group_of) == ["CG-S1-A-001", "CG-S4-A-001", "CG-S5-A-001"]

    variant = split_runs(
        infos,
        _config(predictive_controller_ids=predictive, include_predictive_variant=True),
    )
    assert variant.excluded_runs == ()
    assert set(variant.group_of) == {"CG-S1-A-001", "CG-S2-A-001", "CG-S4-A-001", "CG-S5-A-001"}


def test_invalid_run_is_excluded_with_recorded_reason_never_revalidated():
    infos = [
        _info("CG-S1-A-001", valid=False, invalid_reason="thermal-contradiction"),
        _info("CG-S2-A-001"),
        _info("CG-S4-A-001"),
        _info("CG-S5-A-001"),
    ]
    result = split_runs(infos, _config(seed=0))
    excluded = {e.run_id: e.reason for e in result.excluded_runs}
    assert excluded == {"CG-S1-A-001": "thermal-contradiction"}
    assert set(result.group_of) == {"CG-S2-A-001", "CG-S4-A-001", "CG-S5-A-001"}
    with pytest.raises(SplitError, match="invalid_reason"):
        split_runs(
            [_info("CG-S1-A-001", valid=False)],
            _config(),
        )


def test_insufficient_groups_fail_explicitly():
    few = [_info("CG-S1-A-001"), _info("CG-S2-A-001", pair="CG-S2-A-001"), _info("CG-S4-A-001")]
    with pytest.raises(SplitError, match="insufficient independent groups"):
        split_runs(
            few,
            _config(min_groups_per_partition=2),
        )
    # Enough groups in total, but the requested geometry would starve a
    # partition below the floor: refuse without leaking.
    six = [_info(f"CG-S{i}-A-00{i}") for i in (1, 2, 3, 4, 5, 6)]
    with pytest.raises(SplitError, match="below the configured minimum"):
        split_runs(
            six,
            SplitConfig(
                proportions=SplitProportions(0.8, 0.1, 0.1),
                seed=9,
                controller_context="all-reactive-or-observational",
                min_groups_per_partition=2,
            ),
        )


def test_partitions_are_disjoint():
    result = split_runs(_six_infos(), _config(seed=11))
    train, val, test = (
        set(result.runs_in(p)) for p in ("train", "validation", "test")
    )
    assert not (train & val or train & test or val & test)


def test_hardware_lineage_single_value_and_multi_config_guard():
    single = split_runs(
        [_info("CG-S1-A-001"), _info("CG-S2-A-001"), _info("CG-S4-A-001")],
        _config(seed=1),
    )
    assert single.hardware_lineage == "CG-HW-001"

    infos = [
        _info("CG-S1-A-001"),
        _info("CG-S2-A-001", hardware="CG-HW-002"),
        _info("CG-S4-A-001"),
    ]
    with pytest.raises(SplitError, match="more than one hardware_config_id"):
        split_runs(infos, _config(seed=1))
    registered = split_runs(
        infos,
        _config(seed=1, hardware_lineage="LRK-15-registered-exception-reviewed-with-A"),
    )
    assert registered.hardware_lineage == "LRK-15-registered-exception-reviewed-with-A"


def test_manifest_dict_records_required_split_fields():
    result = split_runs(_six_infos(), _config(seed=17))
    manifest = result.to_manifest_dict(
        "CG-SPLIT-001",
        dataset_id="CG-DATA-001",
        created_at=WHEN,
        git_commit=GIT,
    )
    assert manifest["split_id"] == "CG-SPLIT-001"
    assert manifest["dataset_id"] == "CG-DATA-001"
    assert manifest["grouping"] == {"key": "run_id"}
    assert manifest["hardware_lineage"] == {"hardware_config_id": "CG-HW-001"}
    assert manifest["locked_test"] == {"frozen_at": None, "opened_at": None}
    assert manifest["controller_context"] == "all-reactive-or-observational"
    assert manifest["split_seed"] == 17
    assert manifest["status"] == "draft"
    assert sorted(manifest["train_runs"] + manifest["validation_runs"] + manifest["test_runs"]) == sorted(
        result.group_of
    )
    assert manifest["excluded_runs"] == []


def test_group_ids_satisfy_sklearn_group_semantics():
    from sklearn.model_selection import GroupShuffleSplit

    result = split_runs(_six_infos(), _config(seed=23))
    # Three synthetic rows per run: the group of every row is the run's
    # independent execution group (pair arms share it).
    rows = []
    groups = []
    for run_id in sorted(result.group_of):
        group = result.group_of[run_id]
        for seq in range(3):
            rows.append((run_id, seq))
            groups.append(group)

    splitter = GroupShuffleSplit(
        n_splits=1, train_size=0.6, test_size=0.4, random_state=result.seed
    )
    (train_idx, test_idx), = splitter.split(rows, groups=groups)
    train_groups = {groups[i] for i in train_idx}
    test_groups = {groups[i] for i in test_idx}
    assert not (train_groups & test_groups)
    # Row sets are disjoint and leave no row behind.
    assert len(train_idx) + len(test_idx) == len(rows)
