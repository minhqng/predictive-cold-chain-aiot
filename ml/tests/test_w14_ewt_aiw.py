"""W14 EWT/AIW estimability refusal tests and report truth checks."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from coldguard_ml.evaluation_contract import (
    AIWStatus,
    EWTProvenance,
    LatencyComponent,
    compute_aiw,
    compute_ewt,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "W14" / "AIW-report.md"
PROVENANCE = EWTProvenance(
    run_id="W14-CONTRACT",
    event_id="W14-EVENT",
    warning_definition="persistent risk_score warning",
    persistence_definition="predeclared persistence",
)


def test_missing_critical_semantics_never_produce_numeric_ewt():
    result = compute_ewt(
        t_predictive_s=10.0,
        t_reactive_s=None,
        warning_present=True,
        warning_persistent=True,
        reactive_crossing_observed=False,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
        provenance=PROVENANCE,
    )
    assert result.ewt_s is None
    assert result.status.value == "MISSING_REACTIVE_CROSSING"


def test_intervened_trajectory_is_not_a_counterfactual():
    result = compute_ewt(
        t_predictive_s=10.0,
        t_reactive_s=30.0,
        warning_present=True,
        warning_persistent=True,
        reactive_crossing_observed=True,
        trajectory_non_intervened=False,
        timestamps_trusted=True,
        provenance=PROVENANCE,
    )
    assert result.ewt_s is None
    assert result.status.value == "INADMISSIBLE_INTERVENED_TRAJECTORY"


def test_missing_warning_is_not_ewt_zero():
    result = compute_ewt(
        t_predictive_s=None,
        t_reactive_s=30.0,
        warning_present=False,
        warning_persistent=False,
        reactive_crossing_observed=True,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
        provenance=PROVENANCE,
    )
    assert result.ewt_s is None
    assert result.status.value == "MISSING_WARNING"


def test_ewt_estimable_only_with_both_trusted_anchors():
    result = compute_ewt(
        t_predictive_s=10.0,
        t_reactive_s=30.0,
        warning_present=True,
        warning_persistent=True,
        reactive_crossing_observed=True,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
        provenance=PROVENANCE,
    )
    assert result.ewt_s == 20.0


def test_unmeasured_aiw_component_is_not_zero_filled():
    result = compute_aiw(
        t_critical_s=100.0,
        t_warning_s=10.0,
        system_components=(
            LatencyComponent(
                name="network",
                owner="Member C",
                start_s=0.0,
                end_s=2.0,
                clock_domain="UTC",
                measurement_method="unavailable",
                measured=False,
            ),
        ),
        physical_components=(
            LatencyComponent(
                name="thermal",
                owner="Member A",
                start_s=2.0,
                end_s=62.0,
                clock_domain="UTC",
                measurement_method="thermal response",
                measured=True,
                uncertainty_s=1.0,
            ),
        ),
        reference_clock_domain="UTC",
    )
    assert result.status is AIWStatus.NOT_ESTIMABLE
    assert result.aiw_s is None


def test_empty_aiw_chain_is_not_zero():
    result = compute_aiw(
        t_critical_s=100.0,
        t_warning_s=10.0,
        system_components=(),
        physical_components=(
            LatencyComponent(
                name="thermal",
                owner="Member A",
                start_s=0.0,
                end_s=60.0,
                clock_domain="UTC",
                measurement_method="thermal response",
                measured=True,
                uncertainty_s=1.0,
            ),
        ),
        reference_clock_domain="UTC",
    )
    assert result.status is AIWStatus.NOT_ESTIMABLE
    assert result.aiw_s is None


def test_mixed_clock_domains_are_not_subtracted():
    result = compute_aiw(
        t_critical_s=100.0,
        t_warning_s=10.0,
        system_components=(
            LatencyComponent(
                name="console",
                owner="Member A",
                start_s=0.0,
                end_s=1.0,
                clock_domain="CONSOLE",
                measurement_method="console anchor",
                measured=True,
                uncertainty_s=1.0,
            ),
        ),
        physical_components=(
            LatencyComponent(
                name="thermal",
                owner="Member A",
                start_s=2.0,
                end_s=62.0,
                clock_domain="UTC",
                measurement_method="thermal response",
                measured=True,
                uncertainty_s=1.0,
            ),
        ),
        reference_clock_domain="UTC",
    )
    assert result.status is AIWStatus.NOT_ESTIMABLE
    assert result.aiw_s is None


def test_overlapping_aiw_spans_are_refused_not_double_counted():
    with pytest.raises(Exception, match="overlap"):
        compute_aiw(
            t_critical_s=100.0,
            t_warning_s=10.0,
            system_components=(
                LatencyComponent(
                    name="inference",
                    owner="Member B",
                    start_s=0.0,
                    end_s=5.0,
                    clock_domain="UTC",
                    measurement_method="measured",
                    measured=True,
                    uncertainty_s=0.1,
                ),
            ),
            physical_components=(
                LatencyComponent(
                    name="thermal",
                    owner="Member A",
                    start_s=4.0,
                    end_s=62.0,
                    clock_domain="UTC",
                    measurement_method="thermal response",
                    measured=True,
                    uncertainty_s=1.0,
                ),
            ),
            reference_clock_domain="UTC",
        )


def test_aiw_estimable_only_with_complete_disjoint_measured_chain():
    result = compute_aiw(
        t_critical_s=100.0,
        t_warning_s=10.0,
        system_components=(
            LatencyComponent(
                name="network",
                owner="Member C",
                start_s=0.0,
                end_s=2.0,
                clock_domain="UTC",
                measurement_method="measured network command path",
                measured=True,
                uncertainty_s=0.05,
            ),
        ),
        physical_components=(
            LatencyComponent(
                name="thermal",
                owner="Member A",
                start_s=2.0,
                end_s=62.0,
                clock_domain="UTC",
                measurement_method="command->thermal",
                measured=True,
                uncertainty_s=1.0,
            ),
        ),
        reference_clock_domain="UTC",
    )
    assert result.status is AIWStatus.ESTIMABLE
    assert result.aiw_s == pytest.approx(28.0)


def test_aiw_report_does_not_fabricate_a_numeric_aiw_or_ewt():
    text = REPORT.read_text(encoding="utf-8")
    assert "NOT_ESTIMABLE" in text
    assert "AIW_UNAVAILABLE_MEASURED_LATENCY_CHAIN_MISSING" in text
    assert "EWT_UNAVAILABLE_NO_QUALIFIED_COMMON_TRAJECTORY" in text
    assert not re.search(r"AIW\s*=\s*-?\d", text)
    assert not re.search(r"EWT\s*=\s*-?\d", text)


def test_aiw_report_maps_every_gap_to_an_owner():
    text = REPORT.read_text(encoding="utf-8")
    for owner in ("Member A", "Member C", "Member D", "Leader"):
        assert owner in text
    for gap in (
        "GAP-NETWORK-COMMAND-LATENCY",
        "EVENT_UTC_UNAVAILABLE_DEVICE_HAS_NO_WALL_CLOCK",
        "CLOCK_SYNC_NOT_EVIDENCED_IN_PACKAGE",
        "RUN_IDENTITY_UNRESOLVED_FOR_CG_RUN_PATTERN",
        "CALIBRATION_TRACEABILITY_ABSENT_FROM_PACKAGE_SCHEMA",
        "CRITICAL_CRITERION_AND_REPRESENTATIVE_T_NOT_FROZEN",
    ):
        assert gap in text
    assert "console" in text.lower()
    assert "network command path" in text.lower()
    assert "not a measured AIW distribution" in text
