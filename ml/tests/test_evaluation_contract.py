"""B-W04-02 / B-W04-03 / B-W04-04 contract regressions.

These tests exercise the frozen *interfaces* with illustrative inputs. They
produce no ColdGuard measurement, threshold, distribution or result.
"""

from __future__ import annotations

import pytest

from coldguard_ml import (
    AIWStatus,
    Amendment,
    EWTProvenance,
    EWTStatus,
    EvaluationContractError,
    InterventionEvidence,
    LatencyComponent,
    MetricHierarchy,
    MetricHierarchyError,
    PRIMARY_PHYSICAL_OUTCOME,
    PRIMARY_PREDICTIVE_METRIC,
    assert_allowed_for_selection,
    compute_aiw,
    compute_ewt,
    paired_improvement,
)


EWT_PROV = EWTProvenance(
    run_id="CG-S1-A-001",
    event_id="EVT-ILLUSTRATIVE-001",
    warning_definition="frozen test warning definition",
    persistence_definition="frozen k-of-n persistence definition",
)


def _ewt(**overrides: object):
    return compute_ewt(provenance=EWT_PROV, **overrides)


def _components(
    *, measured: bool = True, overlapping: bool = False
) -> tuple[LatencyComponent, ...]:
    second_start = 1.0 if overlapping else 5.0
    return (
        LatencyComponent(
            name="sample_to_backend",
            owner="C",
            start_s=0.0,
            end_s=2.0,
            clock_domain="backend",
            measurement_method="receive-minus-capture",
            measured=measured,
            uncertainty_s=0.0,
        ),
        LatencyComponent(
            name="inference",
            owner="B",
            start_s=second_start,
            end_s=6.0,
            clock_domain="backend",
            measurement_method="monotonic-span",
            measured=measured,
            uncertainty_s=0.0,
        ),
    )


# ---------------------------------------------------------------------------
# EWT
# ---------------------------------------------------------------------------


def test_ewt_early_warning_is_positive() -> None:
    result = _ewt(
        t_predictive_s=100.0,
        t_reactive_s=160.0,
        warning_present=True,
        warning_persistent=True,
        reactive_crossing_observed=True,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
    )
    assert result.status is EWTStatus.ESTIMABLE
    assert result.ewt_s == 60.0


def test_ewt_late_warning_is_negative_and_reported() -> None:
    result = _ewt(
        t_predictive_s=200.0,
        t_reactive_s=160.0,
        warning_present=True,
        warning_persistent=True,
        reactive_crossing_observed=True,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
    )
    assert result.status is EWTStatus.ESTIMABLE
    assert result.ewt_s == -40.0


def test_no_warning_is_missed_state_not_zero() -> None:
    result = _ewt(
        t_predictive_s=None,
        t_reactive_s=160.0,
        warning_present=False,
        warning_persistent=False,
        reactive_crossing_observed=True,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
    )
    assert result.status is EWTStatus.MISSING_WARNING
    assert result.ewt_s is None
    assert "never EWT = 0" in result.reason


def test_non_persistent_warning_is_not_a_valid_warning() -> None:
    result = _ewt(
        t_predictive_s=100.0,
        t_reactive_s=160.0,
        warning_present=True,
        warning_persistent=False,
        reactive_crossing_observed=True,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
    )
    assert result.status is EWTStatus.MISSING_WARNING
    assert result.ewt_s is None


def test_unobserved_reactive_crossing_is_censored_not_invented() -> None:
    result = _ewt(
        t_predictive_s=100.0,
        t_reactive_s=None,
        warning_present=True,
        warning_persistent=True,
        reactive_crossing_observed=False,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
    )
    assert result.status is EWTStatus.MISSING_REACTIVE_CROSSING
    assert result.ewt_s is None


def test_predictively_intervened_trajectory_is_inadmissible() -> None:
    result = _ewt(
        t_predictive_s=100.0,
        t_reactive_s=160.0,
        warning_present=True,
        warning_persistent=True,
        reactive_crossing_observed=True,
        trajectory_non_intervened=False,
        timestamps_trusted=True,
    )
    assert result.status is EWTStatus.INADMISSIBLE_INTERVENED_TRAJECTORY
    assert result.ewt_s is None


def test_non_estimable_ewt_result_cannot_carry_a_number() -> None:
    from coldguard_ml import EWTResult

    with pytest.raises(EvaluationContractError, match="None"):
        EWTResult(
            status=EWTStatus.MISSING_WARNING,
            ewt_s=0.0,
            reason="bad construction",
            provenance=EWT_PROV,
        )


def test_estimable_ewt_result_cannot_be_constructed_without_provenance() -> None:
    with pytest.raises(EvaluationContractError, match="provenance"):
        from coldguard_ml import EWTResult

        EWTResult(
            status=EWTStatus.ESTIMABLE,
            ewt_s=10.0,
            reason="direct construction",
            provenance=None,
        )


def test_ewt_without_provenance_is_refused() -> None:
    result = compute_ewt(
        t_predictive_s=100.0,
        t_reactive_s=160.0,
        warning_present=True,
        warning_persistent=True,
        reactive_crossing_observed=True,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
        provenance=None,
    )
    assert result.status is EWTStatus.MISSING_PROVENANCE
    assert result.ewt_s is None


def test_untrusted_timestamps_refuse_ewt() -> None:
    result = _ewt(
        t_predictive_s=100.0,
        t_reactive_s=160.0,
        warning_present=True,
        warning_persistent=True,
        reactive_crossing_observed=True,
        trajectory_non_intervened=True,
        timestamps_trusted=False,
    )
    assert result.status is EWTStatus.UNTRUSTED_TIMESTAMPS
    assert result.ewt_s is None


# ---------------------------------------------------------------------------
# AIW
# ---------------------------------------------------------------------------


def test_aiw_with_measured_components_is_estimable() -> None:
    result = compute_aiw(
        t_critical_s=300.0,
        t_warning_s=100.0,
        system_components=_components(),
        physical_components=(
            LatencyComponent(
                name="electrical_response",
                owner="A",
                start_s=10.0,
                end_s=11.094,
                clock_domain="backend",
                measurement_method="step-response",
                measured=True,
                uncertainty_s=0.0,
            ),
        ),
        reference_clock_domain="backend",
    )
    assert result.status is AIWStatus.ESTIMABLE
    assert result.aiw_s == pytest.approx(300.0 - 100.0 - 3.0 - 1.094)


def test_unknown_physical_delay_makes_aiw_not_estimable() -> None:
    result = compute_aiw(
        t_critical_s=300.0,
        t_warning_s=100.0,
        system_components=_components(),
        physical_components=(
            LatencyComponent(
                name="thermal_response",
                owner="A",
                start_s=10.0,
                end_s=100.0,
                clock_domain="backend",
                measurement_method="UNMEASURED",
                measured=False,
            ),
        ),
        reference_clock_domain="backend",
    )
    assert result.status is AIWStatus.NOT_ESTIMABLE
    assert result.aiw_s is None
    assert "measured input missing/untrusted" in result.reason
    assert "thermal_response" in result.reason


def test_missing_system_component_makes_aiw_not_estimable() -> None:
    result = compute_aiw(
        t_critical_s=300.0,
        t_warning_s=100.0,
        system_components=_components(measured=False),
        physical_components=_components(),
        reference_clock_domain="backend",
    )
    assert result.status is AIWStatus.NOT_ESTIMABLE
    assert result.aiw_s is None


def test_overlapping_components_are_refused_not_double_counted() -> None:
    with pytest.raises(EvaluationContractError, match="overlap"):
        compute_aiw(
            t_critical_s=300.0,
            t_warning_s=100.0,
            system_components=_components(overlapping=True),
            physical_components=_components(),
            reference_clock_domain="backend",
        )


def test_empty_component_chain_is_not_zero() -> None:
    result = compute_aiw(
        t_critical_s=300.0,
        t_warning_s=100.0,
        system_components=(),
        physical_components=_components(),
        reference_clock_domain="backend",
    )
    assert result.status is AIWStatus.NOT_ESTIMABLE
    assert result.aiw_s is None


def test_mixed_clock_domains_make_aiw_not_estimable() -> None:
    physical = LatencyComponent(
        name="electrical_response",
        owner="A",
        start_s=10.0,
        end_s=11.0,
        clock_domain="device",
        measurement_method="step-response",
        measured=True,
        uncertainty_s=0.0,
    )
    result = compute_aiw(
        t_critical_s=300.0,
        t_warning_s=100.0,
        system_components=_components(),
        physical_components=(physical,),
        reference_clock_domain="backend",
    )
    assert result.status is AIWStatus.NOT_ESTIMABLE
    assert "mixed clock domains" in result.reason


def test_measured_component_requires_uncertainty() -> None:
    with pytest.raises(EvaluationContractError, match="uncertainty_s"):
        LatencyComponent(
            name="no_uncertainty",
            owner="A",
            start_s=0.0,
            end_s=1.0,
            clock_domain="backend",
            measurement_method="span",
            measured=True,
        )


# ---------------------------------------------------------------------------
# intervention verification chain
# ---------------------------------------------------------------------------


def test_ack_alone_does_not_imply_physical_intervention() -> None:
    evidence = InterventionEvidence(
        command_published=True,
        device_ack=True,
        electrical_response_measured=False,
        thermal_response_measured=False,
    )
    assert evidence.verified is False
    with pytest.raises(EvaluationContractError, match="not physically verified"):
        evidence.require_verified()


def test_missing_thermal_response_does_not_imply_success() -> None:
    evidence = InterventionEvidence(
        command_published=True,
        device_ack=True,
        electrical_response_measured=True,
        thermal_response_measured=False,
    )
    assert evidence.verified is False
    with pytest.raises(EvaluationContractError):
        evidence.require_verified()


def test_electrical_and_thermal_responses_verify_intervention() -> None:
    evidence = InterventionEvidence(
        command_published=True,
        device_ack=True,
        electrical_response_measured=True,
        thermal_response_measured=True,
    )
    assert evidence.verified is True
    evidence.require_verified()


# ---------------------------------------------------------------------------
# metric hierarchy
# ---------------------------------------------------------------------------


def test_primary_predictive_metric_is_non_interpolated_ap() -> None:
    hierarchy = MetricHierarchy()
    assert PRIMARY_PREDICTIVE_METRIC == "non_interpolated_average_precision"
    hierarchy.assert_primary_predictive(PRIMARY_PREDICTIVE_METRIC)
    with pytest.raises(MetricHierarchyError, match="trapezoidal"):
        hierarchy.assert_primary_predictive("trapezoidal_pr_auc")
    with pytest.raises(MetricHierarchyError, match="recorded amendment"):
        hierarchy.assert_primary_predictive("roc_auc")


def test_secondary_cannot_become_primary_without_amendment() -> None:
    hierarchy = MetricHierarchy()
    assert PRIMARY_PHYSICAL_OUTCOME == "thermal_exposure"
    hierarchy.assert_primary_physical("thermal_exposure")
    with pytest.raises(MetricHierarchyError, match="recorded amendment"):
        hierarchy.assert_primary_physical("recovery_time")


def test_recorded_amendment_allows_a_disclosed_secondary_promotion() -> None:
    hierarchy = MetricHierarchy(
        amendment=Amendment(
            amendment_id="CG-AMEND-001",
            reason="pre-result protocol constraint made exposure unmeasurable",
            disclosed_exploratory=True,
        )
    )
    hierarchy.assert_primary_physical("recovery_time")


def test_custom_primary_metric_requires_an_amendment() -> None:
    with pytest.raises(MetricHierarchyError, match="recorded amendment"):
        MetricHierarchy(primary_predictive="roc_auc")
    with pytest.raises(MetricHierarchyError, match="recorded amendment"):
        MetricHierarchy(primary_physical="recovery_time")


def test_caller_supplied_secondary_tuple_cannot_expand_the_frozen_set() -> None:
    with pytest.raises(MetricHierarchyError, match="frozen secondary"):
        MetricHierarchy(
            primary_physical="roc_auc",
            secondary_physical=("roc_auc",),
            amendment=Amendment(
                amendment_id="CG-AMEND-004",
                reason="attempt to widen the frozen set",
            ),
        )


def test_recorded_amendment_allows_a_custom_secondary_primary() -> None:
    hierarchy = MetricHierarchy(
        primary_predictive="roc_auc",
        amendment=Amendment(
            amendment_id="CG-AMEND-003",
            reason="pre-result ranking objective change",
        ),
    )
    hierarchy.assert_primary_predictive("roc_auc")


def test_undisclosed_amendment_is_rejected() -> None:
    with pytest.raises(MetricHierarchyError, match="disclosed as exploratory"):
        Amendment(
            amendment_id="CG-AMEND-002",
            reason="quiet promotion attempt",
            disclosed_exploratory=False,
        )


def test_paired_improvement_sign_convention_is_frozen() -> None:
    assert paired_improvement(10.0, 7.0, outcome_name="thermal_exposure") == 3.0
    assert paired_improvement(7.0, 10.0, outcome_name="branch_energy") == -3.0
    with pytest.raises(MetricHierarchyError, match="lower-is-better"):
        paired_improvement(1.0, 2.0, outcome_name="not_an_outcome")


def test_locked_holdout_is_never_opened_for_selection() -> None:
    assert_allowed_for_selection("train")
    assert_allowed_for_selection("validation")
    with pytest.raises(MetricHierarchyError, match="locked"):
        assert_allowed_for_selection("locked_test")
    with pytest.raises(MetricHierarchyError, match="locked"):
        assert_allowed_for_selection("holdout")
