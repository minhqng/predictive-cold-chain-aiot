"""W10 pipeline, split, label-pilot, artifact and CLI tests (B-W10-04/05)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from coldguard_ml.feature_fixtures import (
    FIXTURE_VERSION,
    build_censored_trajectory,
    build_development_dataset,
    build_predictive_control_trajectory,
)
from coldguard_ml.feature_pipeline import (
    ELIGIBILITY_BLOCKED,
    OUTPUT_DIAGNOSTIC,
    OUTPUT_ELIGIBLE,
    OUTPUT_SYNTHETIC,
    PRESENT,
    SOURCE_TYPE_REAL_A,
    TIME_DOMAIN_BOOT_SCOPED,
    feature_rows,
    summarize_feature_rows,
    trajectory_from_capture,
    trajectory_from_observations,
)
from coldguard_ml.feature_registry import load_registry
from coldguard_ml.label_pilot import (
    DEVELOPMENT_ONLY,
    PREDICTIVE_CONTROLLERS,
    LabelPilotError,
    PilotConfig,
    assess_real_pilot,
    run_label_pilot,
)
from coldguard_ml import load_capture
from coldguard_ml.labels import (
    CriticalEvent,
    CriticalEventSeries,
    LabelSpec,
    LabelStatus,
    generate_label_records,
)
from coldguard_ml.splitting import (
    RunInfo,
    SplitConfig,
    SplitProportions,
    split_runs,
)
from coldguard_ml.synthetic import SyntheticRunSpec, build_synthetic_runs
from coldguard_ml.windows import WindowConfig, generate_windows

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
EVIDENCE = REPO_ROOT / "evidence" / "A" / "W09" / "exports" / "CG-S1-H8C-600S.json"
W08 = ML_ROOT / "reports" / "W08" / "gate-b-manifest-W08.json"
SCRIPT = ML_ROOT / "scripts" / "feature-pipeline-W10.py"
REGISTRY = load_registry()


def _development():
    dataset = build_development_dataset()
    development = [
        trajectory
        for trajectory in dataset.trajectories
        if dataset.partition_of(trajectory.run_id or "") in ("train", "validation")
    ]
    rows_by_run = {
        trajectory.run_id: feature_rows(
            trajectory,
            REGISTRY,
            partition=dataset.partition_of(trajectory.run_id or ""),
        )
        for trajectory in development
    }
    return dataset, development, rows_by_run


def _run_cli(out_dir: Path, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ML_ROOT / "src")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out_dir), *extra],
        cwd=ML_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_synthetic_rows_carry_full_provenance_and_synthetic_class():
    dataset, development, rows_by_run = _development()
    for run_id, rows in rows_by_run.items():
        trajectory = dataset.trajectory(run_id)
        assert rows
        for row in rows:
            assert row.feature_schema_version == REGISTRY.feature_version
            assert row.registry_sha256 == REGISTRY.schema_sha256
            assert row.source_sha256 == trajectory.source_sha256
            assert row.source_type == "SYNTHETIC_FIXTURE"
            assert row.run_id == run_id
            assert row.boot_id == trajectory.boot_id
            assert row.time_domain == "UTC_ABSOLUTE"
            assert row.output_class == OUTPUT_SYNTHETIC
            assert row.physical_eligibility == "SYNTHETIC_ONLY"
            assert row.anchor_time_utc is not None
            assert len(row.values) == len(REGISTRY.features)
            assert len(row.missing_reasons) == len(REGISTRY.features)


def test_real_capture_is_diagnostic_only_and_fabricates_nothing():
    capture = load_capture(EVIDENCE)
    trajectories = trajectory_from_capture(
        capture,
        physical_eligibility=ELIGIBILITY_BLOCKED,
        exclusion_reasons=("RUN_IDENTITY_UNRESOLVED",),
    )
    assert len(trajectories) == 1
    trajectory = trajectories[0]
    assert trajectory.source_type == SOURCE_TYPE_REAL_A
    assert trajectory.clock_domain == TIME_DOMAIN_BOOT_SCOPED
    assert trajectory.origin_utc is None
    assert trajectory.run_id is None
    rows = feature_rows(trajectory, REGISTRY, partition=None)
    assert len(rows) == len(capture.rows)
    index = {feature.feature_id: i for i, feature in enumerate(REGISTRY.features)}
    for row in rows:
        assert row.anchor_time_utc is None
        assert row.output_class == OUTPUT_DIAGNOSTIC
        assert row.physical_eligibility == ELIGIBILITY_BLOCKED
        assert row.missing_reasons[index["door_open"]] in (
            "MISSING_QUALITY",
            "MISSING_UNKNOWN_DOOR",
        )
        assert row.missing_reasons[index["cooling_power_w"]] == (
            "MISSING_ELECTRICAL_UNQUALIFIED"
        )
    first = rows[0]
    assert first.values[index["T_tec_hot_side_c"]] is not None
    assert first.values[index["T_chamber_mean_c"]] is not None
    assert not any(row.output_class == OUTPUT_ELIGIBLE for row in rows)


def test_grouped_split_keeps_pairs_together_and_test_untouched():
    dataset, development, rows_by_run = _development()
    for pair in dataset.split.pair_lineage:
        partitions = {dataset.split.partition_of(run_id) for run_id in pair["run_ids"]}
        assert len(partitions) == 1
    partitions = {row.split_partition for rows in rows_by_run.values() for row in rows}
    assert partitions == {"train", "validation"}
    assert not any(
        row.run_id in dataset.split.test_runs
        for rows in rows_by_run.values()
        for row in rows
    )


def test_label_pilot_reports_development_status_and_censoring():
    dataset = build_development_dataset()
    all_rows_by_run = {
        trajectory.run_id: feature_rows(
            trajectory,
            REGISTRY,
            partition=dataset.partition_of(trajectory.run_id or ""),
        )
        for trajectory in dataset.trajectories
    }
    result = run_label_pilot(
        dataset.trajectories,
        dataset.series_by_run,
        all_rows_by_run,
        partitions=("train", "validation"),
    )
    assert result.status == "DEVELOPMENT_ONLY"
    assert len(result.horizons) == 4
    for horizon in result.horizons:
        assert horizon.freeze_status == DEVELOPMENT_ONLY
        assert horizon.positive >= 0
        assert horizon.negative >= 0
        assert horizon.censored >= 0
        assert horizon.anchors == horizon.positive + horizon.negative + horizon.censored + horizon.untrusted
        assert horizon.feature_available_anchors > 0
        if horizon.positive + horizon.negative:
            assert horizon.prevalence == pytest.approx(
                horizon.positive / (horizon.positive + horizon.negative)
            )
        else:
            assert horizon.prevalence is None
    assert any(horizon.censored > 0 for horizon in result.horizons)
    assert any(horizon.positive > 0 for horizon in result.horizons)
    assert any(
        reason == "PARTITION_test_NOT_DEVELOPMENT"
        for _, reason in result.excluded_runs
    )


def test_censored_fixture_labels_are_not_negatives():
    trajectory, series = build_censored_trajectory()
    rows = feature_rows(trajectory, REGISTRY, partition="train")
    result = run_label_pilot(
        [trajectory],
        {trajectory.run_id: series},
        {trajectory.run_id: rows},
        config=PilotConfig(horizons_s=(60.0,)),
    )
    horizon = result.horizons[0]
    assert horizon.censored > 0
    assert horizon.positive > 0
    assert horizon.negative > 0
    assert horizon.anchors == horizon.positive + horizon.negative + horizon.censored


def test_predictive_controller_trajectory_is_not_an_observational_label_source():
    trajectory, series = build_predictive_control_trajectory()
    rows = feature_rows(trajectory, REGISTRY, partition="train")
    result = run_label_pilot(
        [trajectory], {trajectory.run_id: series}, {trajectory.run_id: rows}
    )
    assert result.status == "NOT_EVALUABLE"
    assert result.horizons == ()
    assert result.excluded_runs == (
        (trajectory.run_id, "PREDICTIVE_CLOSED_LOOP_NOT_OBSERVATIONAL"),
    )


def test_real_pilot_is_not_evaluable_under_red_gate():
    status = assess_real_pilot(
        eligible_s2_runs=0,
        authoritative_series_present=False,
        gate_b_physical="RED",
    )
    assert status["REAL_S2_LABEL_PILOT"] == "NOT_EVALUABLE"
    assert status["ELIGIBLE_S2_RUNS"] == 0
    assert status["REAL_HORIZON_SELECTION"] == "NOT_FROZEN"


def test_red_gate_cannot_be_upgraded_by_a_real_pilot():
    with pytest.raises(LabelPilotError, match="RED Gate B"):
        assess_real_pilot(
            eligible_s2_runs=1,
            authoritative_series_present=True,
            gate_b_physical="RED",
        )


def test_feature_summary_first_valid_anchor_is_explicit():
    _, development, rows_by_run = _development()
    rows = [row for values in rows_by_run.values() for row in values]
    summary = summarize_feature_rows(
        rows, REGISTRY, population="SYNTHETIC_DEVELOPMENT"
    )
    by_id = {item.feature_id: item for item in summary}
    rolling = by_id["rolling_mean_temperature_60s"]
    assert rolling.first_value_anchor_s == 60.0
    assert rolling.first_eligible_anchor_s == 60.0
    assert dict(rolling.missing_by_reason)["MISSING_INSUFFICIENT_HISTORY"] == 240
    instantaneous = by_id["T_chamber_mean_c"]
    assert instantaneous.first_value_anchor_s == 0.0


def test_feature_rows_are_byte_stable_across_recomputes():
    dataset, development, _ = _development()
    trajectory = dataset.trajectory("CG-S2-A-003")
    partition = dataset.partition_of("CG-S2-A-003")
    left = feature_rows(trajectory, REGISTRY, partition=partition)
    right = feature_rows(trajectory, REGISTRY, partition=partition)
    assert left == right
    assert json.dumps([row.to_dict(REGISTRY.feature_ids) for row in left], sort_keys=True) == json.dumps(
        [row.to_dict(REGISTRY.feature_ids) for row in right], sort_keys=True
    )


def test_cli_help_is_available():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "W10 causal feature pipeline" in result.stdout


def test_cli_generates_consistent_artifacts(tmp_path: Path):
    result = _run_cli(tmp_path)
    assert result.returncode == 0, result.stderr
    expected = {
        "S2-feature-report.md",
        "feature-audit-W10.svg",
        "real-diagnostic-W10.svg",
        "feature-summary-W10.csv",
        "label-pilot-W10.csv",
        "feature-manifest-W10.json",
    }
    assert {path.name for path in tmp_path.iterdir()} == expected
    manifest = json.loads((tmp_path / "feature-manifest-W10.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "coldguard-w10-feature-pipeline-manifest-v1"
    assert manifest["registry"]["feature_schema_version"] == REGISTRY.feature_version
    assert manifest["registry"]["registry_sha256"] == REGISTRY.schema_sha256
    assert manifest["w08"]["physical_gate"] == "RED"
    assert manifest["w08"]["predictive_gate"] == "NOT_READY"
    assert manifest["synthetic"]["future_perturbation"] == "PASS"
    assert manifest["synthetic"]["future_truncation"] == "PASS"
    assert manifest["synthetic"]["deterministic_recompute"] == "PASS"
    assert manifest["synthetic"]["test_runs_used"] == 0
    assert manifest["real_a"]["eligible_s2_feature_rows"] == 0
    assert manifest["real_a"]["door_openings"] == 0
    assert manifest["real_a"]["time_domain"] == "BOOT_SCOPED_UPTIME"
    assert manifest["real_label_pilot"]["REAL_S2_LABEL_PILOT"] == "NOT_EVALUABLE"
    for name, entry in manifest["artifacts"].items():
        payload = (tmp_path / name).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        assert len(payload) == entry["bytes"]
    ET.parse(tmp_path / "feature-audit-W10.svg")
    ET.parse(tmp_path / "real-diagnostic-W10.svg")
    audit = (tmp_path / "feature-audit-W10.svg").read_text(encoding="utf-8")
    assert "future label only" in audit
    assert "future observations are shown only to construct labels" in audit
    report = (tmp_path / "S2-feature-report.md").read_text(encoding="utf-8")
    assert "Physical Gate B | RED" in report
    assert "REAL_S2_LABEL_PILOT" not in report  # report uses human-readable status
    assert "NOT_EVALUABLE" in report
    summary_csv = (tmp_path / "feature-summary-W10.csv").read_text(encoding="utf-8").splitlines()
    assert summary_csv[0].startswith("population,feature_id")
    assert len(summary_csv) == 1 + 2 * len(REGISTRY.features)


def test_cli_is_byte_deterministic_in_place(tmp_path: Path):
    first = _run_cli(tmp_path)
    assert first.returncode == 0, first.stderr
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.iterdir()
    }
    second = _run_cli(tmp_path)
    assert second.returncode == 0, second.stderr
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.iterdir()
    }
    assert before == after


def test_cli_missing_w08_manifest_is_a_configuration_error(tmp_path: Path):
    result = _run_cli(
        tmp_path, "--a-w08-manifest", str(tmp_path / "missing-W08.json")
    )
    assert result.returncode == 1


def test_fixture_version_is_recorded_and_predictive_controllers_are_declared():
    dataset = build_development_dataset()
    assert dataset.fixture_version == FIXTURE_VERSION
    assert "CONTROLLER-B-PREDICTIVE" in PREDICTIVE_CONTROLLERS
    assert "CONTROLLER-A" not in PREDICTIVE_CONTROLLERS


def test_w02_label_interval_boundaries_and_censoring():
    import datetime as _dt

    origin = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
    event = CriticalEvent(time=origin + _dt.timedelta(seconds=90), trusted=True)
    series = CriticalEventSeries(
        run_id="RUN-LABEL-001",
        events=(event,),
        series_id="synthetic-label-series",
        coverage_end=origin + _dt.timedelta(seconds=200),
    )
    spec = LabelSpec(
        horizon_s=10.0,
        spec_version="w10-development-pilot",
        representative_temperature="DEVELOPMENT_CANDIDATE_NOT_SELECTED",
        boundary_c=None,
        frozen_at=None,
    )
    anchors = [
        (origin, "a0"),
        (origin + _dt.timedelta(seconds=80), "a80"),
        (origin + _dt.timedelta(seconds=89), "a89"),
        (origin + _dt.timedelta(seconds=90), "a90"),
        (origin + _dt.timedelta(seconds=195), "a195"),
    ]
    records = generate_label_records(
        "RUN-LABEL-001",
        anchors,
        series,
        spec,
        coverage_end=origin + _dt.timedelta(seconds=200),
    )
    by_ref = {record.anchor_ref: record for record in records}
    assert by_ref["a0"].status is LabelStatus.EVALUABLE
    assert by_ref["a0"].y == 0
    assert by_ref["a80"].status is LabelStatus.EVALUABLE
    assert by_ref["a80"].y == 1
    assert by_ref["a89"].y == 1
    assert by_ref["a90"].status is LabelStatus.EVALUABLE
    assert by_ref["a90"].y == 0
    assert by_ref["a195"].status is LabelStatus.CENSORED
    assert by_ref["a195"].y is None
    untrusted_series = CriticalEventSeries(
        run_id="RUN-LABEL-001",
        events=(
            CriticalEvent(
                time=origin + _dt.timedelta(seconds=90), trusted=False
            ),
        ),
        series_id="synthetic-untrusted-series",
        coverage_end=origin + _dt.timedelta(seconds=200),
    )
    untrusted = generate_label_records(
        "RUN-LABEL-001",
        [(origin + _dt.timedelta(seconds=80), "u80")],
        untrusted_series,
        spec,
        coverage_end=origin + _dt.timedelta(seconds=200),
    )[0]
    assert untrusted.status is LabelStatus.UNTRUSTED_INFO
    assert untrusted.y is None


def test_w02_grouped_windows_are_reused_as_w10_anchors():
    specs = [
        SyntheticRunSpec(
            run_id=f"CG-S1-W02-{index}",
            scenario_id="S1",
            seed=600 + index,
            duration_s=90.0,
        )
        for index in range(3)
    ]
    runs = build_synthetic_runs(specs)
    run_infos = [
        RunInfo(
            run_id=run.run_id,
            scenario_id="S1",
            controller_id="CONTROLLER-A",
            hardware_config_id="CG-HW-SYNTHETIC",
        )
        for run in runs
    ]
    split = split_runs(
        run_infos,
        SplitConfig(
            proportions=SplitProportions(1 / 3, 1 / 3, 1 / 3),
            seed=11,
            controller_context="all-reactive-or-observational",
            min_groups_per_partition=1,
            hardware_lineage="CG-HW-SYNTHETIC",
        ),
    )
    train_run_id = split.train_runs[0]
    train_run = next(run for run in runs if run.run_id == train_run_id)
    windows = generate_windows(
        train_run.observations,
        split,
        "train",
        WindowConfig(window_length_s=30.0, anchor_stride=10),
    )
    trajectory = trajectory_from_observations(
        train_run.observations,
        source_sha256="7" * 64,
        synthetic_roles={"t1": "CHAMBER_CENTER"},
    )[0]
    origin = train_run.observations[0].time
    anchors = [
        (window.prediction_time - origin).total_seconds() for window in windows
    ]
    rows = feature_rows(trajectory, REGISTRY, partition="train", anchors=anchors)
    assert len(rows) == len(windows)
    assert [row.anchor_t_s for row in rows] == anchors
    assert all(row.split_partition == "train" for row in rows)
    assert all(row.output_class == OUTPUT_SYNTHETIC for row in rows)
