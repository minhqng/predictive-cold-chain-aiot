"""B-W02 end-to-end pipeline integrity.

Order checks (Doc `03` §46; 05B §12): runs → split → windows-per-partition
→ labels. Every sample traces to its run + interval + partition, partitions
cannot mix, and the whole harness replays byte-identically under the same
seed. Synthetic provenance (B7) is kept end to end.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from coldguard_ml import (
    LabelError,
    LabelSpec,
    LabelStatus,
    RunInfo,
    SplitConfig,
    SplitProportions,
    SyntheticRunSpec,
    WindowConfig,
    WindowError,
    bind_dataset_to_run_records,
    bind_split_to_dataset,
    bind_split_to_run_records,
    build_synthetic_dataset,
    build_synthetic_runs,
    generate_windows,
    labels_and_windows,
    parse_dataset_manifest,
    parse_run_manifests,
    parse_split_manifest,
    split_runs,
)

UTC = _dt.timezone.utc
WHEN = _dt.datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
GIT = "f" * 40
BOOT_GAP = 12.0


def _specs():
    return [
        SyntheticRunSpec(
            run_id="CG-S1-A-001", scenario_id="S1", seed=101, critical_event_offset_s=40.0
        ),
        SyntheticRunSpec(
            run_id="CG-S2-A-001",
            scenario_id="S2",
            seed=102,
            critical_event_offset_s=50.0,
            untrusted_event_offset_s=25.0,
            boot_sessions=2,
            boot_gap_s=BOOT_GAP,
        ),
        SyntheticRunSpec(run_id="CG-S3-A-001", scenario_id="S3", seed=103),
        SyntheticRunSpec(run_id="CG-S4-A-001", scenario_id="S4", seed=104),
        SyntheticRunSpec(
            run_id="CG-S5-A-001",
            scenario_id="S5",
            seed=105,
            critical_event_offset_s=45.0,
        ),
        SyntheticRunSpec(run_id="CG-S6-A-001", scenario_id="S6", seed=106),
    ]


def _harness():
    runs = build_synthetic_runs(_specs())
    dataset_raw, runs = build_synthetic_dataset(
        runs, "CG-DATA-001", git_commit=GIT, created_at=WHEN
    )
    run_records = parse_run_manifests([r.run_manifest for r in runs])
    run_infos = [
        RunInfo(
            run_id=r.run_id,
            scenario_id=r.spec.scenario_id,
            controller_id=r.spec.controller_id,
            pair_id=r.spec.pair_id,
            hardware_config_id=r.spec.hardware_config_id,
        )
        for r in runs
    ]
    split = split_runs(
        run_infos,
        SplitConfig(
            proportions=SplitProportions(0.4, 0.3, 0.3),
            seed=42,
            controller_context="all-reactive-or-observational",
        ),
    )
    split_raw = split.to_manifest_dict(
        "CG-SPLIT-001",
        dataset_id="CG-DATA-001",
        created_at=WHEN,
        git_commit=GIT,
    )
    return {
        "runs": runs,
        "dataset_raw": dataset_raw,
        "run_records": run_records,
        "split": split,
        "split_raw": split_raw,
        "series_by_run": {r.run_id: r.critical_series for r in runs},
        "trajectory_ends": {
            r.run_id: r.observations[-1].time for r in runs
        },
    }


_LABEL_SPEC = LabelSpec(horizon_s=60.0, spec_version="provisional-v0")


def test_grouped_split_and_manifest_bindings_accept_conforming_harness():
    r = _harness()
    dataset = parse_dataset_manifest(r["dataset_raw"])
    split_manifest = parse_split_manifest(r["split_raw"])
    bind_split_to_dataset(split_manifest, dataset)
    bind_dataset_to_run_records(dataset, r["run_records"])
    bind_split_to_run_records(split_manifest, r["run_records"])
    # All six runs are partitioned; none excluded; split lineage is the rig.
    assert len(split_manifest.partitioned_runs) == 6
    assert split_manifest.excluded_run_ids == frozenset()
    assert split_manifest.hardware_lineage == "CG-HW-001"
    assert split_manifest.controller_context == "all-reactive-or-observational"
    assert dataset.synthetic is True  # B7 keeps the synthetic chain intact


def test_generated_pair_lineage_binds_and_keeps_arms_together():
    specs = _specs()
    specs[0] = SyntheticRunSpec(
        run_id="CG-S1-A-001",
        scenario_id="S1",
        seed=101,
        critical_event_offset_s=40.0,
        pair_id="PAIR-001",
    )
    specs[1] = SyntheticRunSpec(
        run_id="CG-S2-A-001",
        scenario_id="S2",
        seed=102,
        critical_event_offset_s=50.0,
        untrusted_event_offset_s=25.0,
        boot_sessions=2,
        boot_gap_s=BOOT_GAP,
        pair_id="PAIR-001",
    )
    runs = build_synthetic_runs(specs)
    dataset_raw, runs = build_synthetic_dataset(
        runs, "CG-DATA-001", git_commit=GIT, created_at=WHEN
    )
    records = parse_run_manifests([r.run_manifest for r in runs])
    split = split_runs(
        [
            RunInfo(
                run_id=r.run_id,
                scenario_id=r.spec.scenario_id,
                controller_id=r.spec.controller_id,
                pair_id=r.spec.pair_id,
                hardware_config_id=r.spec.hardware_config_id,
            )
            for r in runs
        ],
        SplitConfig(
            proportions=SplitProportions(0.4, 0.3, 0.3),
            seed=42,
            controller_context="all-reactive-or-observational",
        ),
    )
    split_raw = split.to_manifest_dict(
        "CG-SPLIT-001", dataset_id="CG-DATA-001", created_at=WHEN, git_commit=GIT
    )
    dataset = parse_dataset_manifest(dataset_raw)
    split_manifest = parse_split_manifest(split_raw)
    bind_split_to_dataset(split_manifest, dataset)
    bind_dataset_to_run_records(dataset, records)
    bind_split_to_run_records(split_manifest, records)

    pair_entries = [
        entry for entry in split_manifest.pair_lineage if entry["pair_id"] == "PAIR-001"
    ]
    assert len(pair_entries) == 1
    entry = pair_entries[0]
    assert set(entry["run_ids"]) == {"CG-S1-A-001", "CG-S2-A-001"}
    partition = split_manifest.partition_of["CG-S1-A-001"]
    assert split_manifest.partition_of["CG-S2-A-001"] == partition
    assert entry["partition"] == partition


def test_windows_cannot_be_generated_outside_the_partition_order():
    r = _harness()
    # LRK-02: feeding rows before the split manifest does NOT exist here —
    # windows are generated strictly from a SplitResult, per partition.
    train_partition = "train"
    train_runs = set(r["split"].runs_in(train_partition))
    rows = [o for o in r["runs"][0].observations]  # CG-S1 rows
    other_run_id = next(
        run_id
        for run_id in r["series_by_run"]
        if r["split"].partition_of(run_id) != train_partition
    )
    other_rows = [
        o
        for run in r["runs"]
        if run.run_id == other_run_id
        for o in run.observations
    ]
    with pytest.raises(WindowError, match="foreign-partition"):
        generate_windows(rows + list(other_rows), r["split"], train_partition)


def test_every_window_and_label_traces_to_run_interval_partition():
    r = _harness()
    windows_partition: dict[str, tuple] = {}
    for partition in ("train", "validation", "test"):
        partition_runs = set(r["split"].runs_in(partition))
        rows = [o for run in r["runs"] if run.run_id in partition_runs for o in run.observations]
        windows_partition[partition] = generate_windows(
            rows, r["split"], partition, WindowConfig(window_length_s=30.0)
        )
        for window in windows_partition[partition]:
            # provenance: run identity, partition identity, causal interval
            assert window.partition == partition
            assert window.run_id in partition_runs
            assert window.prediction_time > window.window_start
            assert window.boot_id
            for observation in window.observations:
                assert observation.run_id == window.run_id
                assert observation.boot_id == window.boot_id
                assert window.window_start < observation.time <= window.prediction_time

    pairs = []
    for partition in ("train", "validation", "test"):
        pairs.extend(
            labels_and_windows(
                windows_partition[partition],
                r["series_by_run"],
                _LABEL_SPEC,
                trajectory_ends=r["trajectory_ends"],
            )
        )
    assert len(pairs) == sum(len(v) for v in windows_partition.values())
    for window, record in pairs:
        assert record.prediction_time == window.prediction_time
        assert record.run_id == window.run_id
        assert record.anchor_ref == window  # traceable to the exact window
        assert record.series_id.startswith("synthetic-prescribed-series:")
        assert record.spec is _LABEL_SPEC
        if record.status is LabelStatus.EVALUABLE and record.y == 0:
            assert record.label_interval[1] <= r["trajectory_ends"][window.run_id]
        if record.status is LabelStatus.CENSORED:
            assert record.y is None
            assert record.label_interval[1] > r["trajectory_ends"][window.run_id]
        if record.y == 1:
            assert record.status is LabelStatus.EVALUABLE
            assert record.matched_event is not None


def test_prescribed_event_produces_positive_labels_before_the_event():
    r = _harness()
    positive_seen: dict[str, int] = {}
    for partition in ("train", "validation", "test"):
        partition_runs = set(r["split"].runs_in(partition))
        rows = [o for run in r["runs"] if run.run_id in partition_runs for o in run.observations]
        windows = generate_windows(rows, r["split"], partition, WindowConfig(window_length_s=30.0))
        pairs = labels_and_windows(
            windows, r["series_by_run"], _LABEL_SPEC, trajectory_ends=r["trajectory_ends"]
        )
        for window, record in pairs:
            if record.y == 1:
                positive_seen[window.run_id] = positive_seen.get(window.run_id, 0) + 1
                event_time = record.matched_event.time
                # the qualifying event is inside the declared horizon horizon
                assert window.prediction_time < event_time <= window.prediction_time + _dt.timedelta(
                    seconds=record.horizon_s
                )
    # CG-S1/S2/S5 prescribe trusted events at 40/50/45s — those must surface
    # as positive labels somewhere (whichever partition holds the run).
    for prescribed_run in ("CG-S1-A-001", "CG-S2-A-001", "CG-S5-A-001"):
        assert positive_seen.get(prescribed_run, 0) > 0


def test_excluded_runs_can_never_remain_window_sources():
    runs = build_synthetic_runs(
        [
            SyntheticRunSpec(
                run_id="CG-S1-A-001", scenario_id="S1", seed=201, controller_id="REACTIVE"
            ),
            SyntheticRunSpec(
                run_id="CG-S4-A-001", scenario_id="S4", seed=202, controller_id="PREDICTIVE"
            ),
            SyntheticRunSpec(
                run_id="CG-S5-A-001", scenario_id="S5", seed=203, controller_id="REACTIVE"
            ),
            SyntheticRunSpec(
                run_id="CG-S6-A-001", scenario_id="S6", seed=204, controller_id="REACTIVE"
            ),
        ]
    )
    split = split_runs(
        [
            RunInfo(
                run_id=run.run_id,
                scenario_id=run.spec.scenario_id,
                controller_id=run.spec.controller_id,
                hardware_config_id="CG-HW-001",
            )
            for run in runs
        ],
        SplitConfig(
            proportions=SplitProportions(1 / 3, 1 / 3, 1 / 3),
            seed=5,
            controller_context="all-reactive-or-observational",
            predictive_controller_ids=frozenset({"PREDICTIVE"}),
        ),
    )
    excluded = {e.run_id for e in split.excluded_runs}
    assert excluded == {"CG-S4-A-001"}
    partition = split.partition_of("CG-S1-A-001")
    all_rows = [o for run in runs for o in run.observations]
    with pytest.raises(WindowError, match="not part of the supplied split"):
        generate_windows(all_rows, split, partition)


def test_full_harness_replay_is_deterministic():
    first = _harness()
    second = _harness()
    assert first["dataset_raw"] == second["dataset_raw"]
    assert first["split_raw"] == second["split_raw"]
    assert first["split"] == second["split"]
    assert first["run_records"] == second["run_records"]
    for left_run, right_run in zip(first["runs"], second["runs"]):
        assert left_run.observations == right_run.observations
        assert left_run.critical_series == right_run.critical_series
    # windows deterministic per partition
    for partition in ("train", "validation", "test"):
        left_runs = set(first["split"].runs_in(partition))
        right_runs = set(second["split"].runs_in(partition))
        assert left_runs == right_runs
        rows_a = [o for run in first["runs"] if run.run_id in left_runs for o in run.observations]
        rows_b = [o for run in second["runs"] if run.run_id in right_runs for o in run.observations]
        assert generate_windows(rows_a, first["split"], partition, WindowConfig(window_length_s=30.0)) == (
            generate_windows(rows_b, second["split"], partition, WindowConfig(window_length_s=30.0))
        )


def test_label_generation_refuses_windows_without_series():
    r = _harness()
    partition = "train"
    train_runs = set(r["split"].runs_in(partition))
    rows = [o for run in r["runs"] if run.run_id in train_runs for o in run.observations]
    windows = generate_windows(rows, r["split"], partition, WindowConfig(window_length_s=30.0))

    incomplete = {
        run_id: series for run_id, series in r["series_by_run"].items() if run_id in train_runs
    }
    del incomplete[next(iter(train_runs))]  # one run deliberately missing
    with pytest.raises(LabelError, match="no critical-event series"):
        labels_and_windows(
            windows, incomplete, _LABEL_SPEC, trajectory_ends=r["trajectory_ends"]
        )
