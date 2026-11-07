"""W12 operational metrics: episodes, units and real undefined status."""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path

import pytest

from coldguard_ml.benchmark_synthesis import load_w11_bundle
from coldguard_ml.operational_metrics import (
    REAL_NOT_ESTIMABLE,
    SYNTHETIC_OPERATIONAL,
    build_operational_report,
)

ML_ROOT = Path(__file__).resolve().parents[1]
W11 = ML_ROOT / "reports" / "W11"
REGISTRY = ML_ROOT / "feature-registry-v1.yaml"
CONFIG = ML_ROOT / "xgb-v1-config.yaml"


@pytest.fixture(scope="module")
def report():
    bundle = load_w11_bundle(
        W11, registry_path=REGISTRY, config_path=CONFIG
    )
    return build_operational_report(bundle)


def test_sustained_warning_episode_is_not_sample_count(report):
    for row in report.synthetic_rows:
        assert row.warning_episodes == 2
        assert row.eligible_windows == 484
        assert row.warning_episodes < row.eligible_windows
        assert row.unit_warning_episode == "warning_episode"


def test_event_and_sample_units_are_explicit(report):
    assert report.unit_statement["AP"].startswith("sample/window-level")
    assert "warning interval" in report.unit_statement["warning_episodes"]
    assert "trusted all-channel-VALID" in report.unit_statement["exposure"]
    for row in report.synthetic_rows:
        assert row.unit_event == "eligible_critical_event"
        assert row.unit_exposure == "trusted_eligible_hour"


def test_per_hour_uses_trusted_exposure(report):
    for row in report.synthetic_rows:
        assert row.trusted_exposure_s is not None
        assert row.trusted_exposure_s > 0
        if row.false_warning_episodes_per_hour is not None:
            expected = row.unmatched_warning_episodes / (
                row.trusted_exposure_s / 3600.0
            )
            assert row.false_warning_episodes_per_hour == pytest.approx(expected)


def test_run_and_window_denominators_are_retained(report):
    for row in report.synthetic_rows:
        assert row.validation_run_count == 4
        assert row.group_count == 2
        assert row.eligible_windows == 484


def test_synthetic_rows_are_labeled_operational_only(report):
    for row in report.synthetic_rows:
        assert row.provenance == SYNTHETIC_OPERATIONAL
        assert row.scientific_claim_status == SYNTHETIC_OPERATIONAL


def test_zero_trusted_exposure_keeps_hour_rate_undefined():
    bundle = load_w11_bundle(
        W11, registry_path=REGISTRY, config_path=CONFIG
    )
    rows = [copy.deepcopy(dict(row)) for row in bundle.comparison_rows]
    target = next(
        row
        for row in rows
        if row["method"] == "B0_THRESHOLD" and row["fold_id"] == "F1"
    )
    target["trusted_exposure_s"] = "0"
    target["false_warning_episodes_per_hour"] = ""
    target["coverage_trustworthy"] = "False"
    fake = dataclasses.replace(bundle, comparison_rows=tuple(rows))
    report = build_operational_report(fake)
    row = next(
        item
        for item in report.synthetic_rows
        if item.method == "B0_THRESHOLD" and item.fold_id == "F1"
    )
    assert row.trusted_exposure_s == 0.0
    assert row.false_warning_episodes_per_hour is None
    assert "FALSE_WARNING_EPISODES_PER_HOUR_UNDEFINED" in row.undefined_reasons


def test_nonzero_unmatched_and_missed_paths_are_exercised():
    bundle = load_w11_bundle(
        W11, registry_path=REGISTRY, config_path=CONFIG
    )
    rows = [copy.deepcopy(dict(row)) for row in bundle.comparison_rows]
    target = next(
        row
        for row in rows
        if row["method"] == "B0_THRESHOLD" and row["fold_id"] == "F1"
    )
    target["warning_episode_count"] = "5"
    target["matched_warning_episodes"] = "0"
    target["unmatched_warnings"] = "5"
    target["eligible_critical_event_count"] = "2"
    target["missed_critical_events"] = "2"
    target["event_precision"] = "0"
    target["event_recall"] = "0"
    target["false_warning_episodes_per_run"] = "2.5"
    target["false_warning_episodes_per_hour"] = "37.5"
    fake = dataclasses.replace(bundle, comparison_rows=tuple(rows))
    report = build_operational_report(fake)
    row = next(
        item
        for item in report.synthetic_rows
        if item.method == "B0_THRESHOLD" and item.fold_id == "F1"
    )
    assert row.warning_episodes == 5
    assert row.unmatched_warning_episodes == 5
    assert row.missed_critical_events == 2
    assert row.event_precision == 0.0
    assert row.event_recall == 0.0
    assert row.false_warning_episodes_per_run == 2.5
    assert row.false_warning_episodes_per_hour == 37.5


def test_eligible_real_runs_force_reassessment():
    from coldguard_ml.operational_metrics import OperationalMetricsError

    bundle = load_w11_bundle(
        W11, registry_path=REGISTRY, config_path=CONFIG
    )
    manifest = copy.deepcopy(dict(bundle.manifest))
    manifest["real_development"]["ELIGIBLE_RUNS"] = 1
    fake = dataclasses.replace(bundle, manifest=manifest)
    with pytest.raises(OperationalMetricsError, match="reassess operational metrics"):
        build_operational_report(fake)


def test_real_operational_metrics_stay_not_estimable(report):
    assert report.real_status["eligible_runs"] == 0
    assert report.real_status["REAL_FALSE_WARNING_BURDEN"] == REAL_NOT_ESTIMABLE
    assert report.real_status["REAL_MISSED_EVENT_RATE"] == REAL_NOT_ESTIMABLE
    assert report.real_status["REAL_EVENT_RECALL"] == REAL_NOT_ESTIMABLE
    assert report.real_status["reason_codes"] == ["NO_ELIGIBLE_PHYSICAL_S1_OR_S2_RUN"]
