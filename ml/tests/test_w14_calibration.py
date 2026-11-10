"""W14 calibration feasibility, group isolation and decision-gate tests."""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path

import pytest

from coldguard_ml.feature_registry import load_registry
from coldguard_ml.grouped_evaluation import build_evaluation_runs
from coldguard_ml.w14_ablation import build_ablation_views
from coldguard_ml.w14_calibration import (
    CALIBRATION_SCHEMA,
    DECISION_BLOCKED_BY_CONTRACT,
    DECISION_CALIBRATED_PROBABILITY_SUPPORTED,
    DECISION_RISK_SCORE_ONLY,
    REASON_CV_NOT_GROUP_SAFE,
    REASON_ISOTONIC_INSUFFICIENT,
    REASON_LOCKED_TEST_TOUCHED,
    REASON_NON_FINITE_SCORE,
    REASON_NON_SYNTHETIC_FIXTURE,
    REASON_OVERLAPPING_GROUPS,
    REASON_SCORE_OUT_OF_BOUNDS,
    REASON_SHARED_PAIR,
    REASON_SINGLE_CLASS_CALIBRATION,
    REASON_SINGLE_CLASS_EVALUATION,
    REASON_SPARSE_BIN,
    REASON_UNTRUSTED_LABELS,
    CalibrationEvidence,
    CalibrationRefusal,
    _ap,
    _brier,
    _perfect_separation,
    assert_calibration_class_support,
    assert_group_isolation,
    assert_label_trust,
    build_reliability_bins,
    decide_output_semantics,
    validate_calibration_strategy,
    validate_probability_scores,
)
from coldguard_ml.xgb_benchmark import (
    build_expanded_w11_fixture,
    load_benchmark_config,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = load_registry(ROOT / "feature-registry-v1.yaml")
CONFIG = load_benchmark_config(ROOT / "xgb-v1-config.yaml", REGISTRY)
FIXTURE = build_expanded_w11_fixture()
VIEWS = build_ablation_views(REGISTRY)


@pytest.fixture(scope="module")
def diagnostics():
    from coldguard_ml.w14_calibration import run_grouped_calibration

    return run_grouped_calibration(FIXTURE, REGISTRY, CONFIG, VIEWS["A1B"])


def _supported_evidence(**overrides):
    values = dict(
        real_eligible_samples=1000,
        real_eligible_groups=10,
        label_identity_frozen=True,
        horizon_frozen=True,
        grouped_fit_calibration_evaluation_disjoint=True,
        pair_lineage_disjoint=True,
        reliability_interpretable=True,
        brier_estimable=True,
        discrimination_estimable=True,
        model_feature_identity_frozen=True,
        locked_test_untouched=True,
        synthetic_only=False,
        product_requires_probability=False,
    )
    values.update(overrides)
    return CalibrationEvidence(**values)


def test_live_evidence_decides_risk_score_only():
    evidence = CalibrationEvidence(
        real_eligible_samples=0,
        real_eligible_groups=0,
        label_identity_frozen=False,
        horizon_frozen=False,
        grouped_fit_calibration_evaluation_disjoint=False,
        pair_lineage_disjoint=False,
        reliability_interpretable=False,
        brier_estimable=False,
        discrimination_estimable=False,
        model_feature_identity_frozen=False,
        locked_test_untouched=True,
        synthetic_only=True,
        product_requires_probability=False,
    )
    decision = decide_output_semantics(evidence)
    assert decision.decision == DECISION_RISK_SCORE_ONLY
    assert "CALIBRATION_BLOCKED_NO_REAL_ELIGIBLE_DEVELOPMENT_POPULATION" in decision.reasons
    assert "CALIBRATION_BLOCKED_TARGET_OR_HORIZON_NOT_FROZEN" in decision.reasons
    assert "CALIBRATION_BLOCKED_SYNTHETIC_SOFTWARE_CONTROL_ONLY" in decision.reasons
    assert "real_eligible_population" in decision.missing_requirements
    assert "percentage-risk wording" in " ".join(decision.product_contract)


def test_sufficient_real_evidence_supports_calibrated_probability():
    decision = decide_output_semantics(_supported_evidence())
    assert decision.decision == DECISION_CALIBRATED_PROBABILITY_SUPPORTED
    assert decision.missing_requirements == ()


def test_probability_required_without_evidence_is_contract_blocked():
    decision = decide_output_semantics(
        _supported_evidence(
            real_eligible_samples=0,
            real_eligible_groups=0,
            label_identity_frozen=False,
            horizon_frozen=False,
            synthetic_only=True,
            product_requires_probability=True,
        )
    )
    assert decision.decision == DECISION_BLOCKED_BY_CONTRACT
    assert (
        "CALIBRATION_BLOCKED_PROBABILITY_WORDING_REQUIRED_BUT_EVIDENCE_INSUFFICIENT"
        in decision.reasons
    )


def test_locked_test_consumption_is_refused():
    with pytest.raises(CalibrationRefusal, match=REASON_LOCKED_TEST_TOUCHED):
        decide_output_semantics(_supported_evidence(locked_test_untouched=False))


def test_single_class_calibration_subset_is_refused():
    with pytest.raises(CalibrationRefusal, match=REASON_SINGLE_CLASS_CALIBRATION):
        assert_calibration_class_support(0, 120, context="calibration subset")
    with pytest.raises(CalibrationRefusal, match=REASON_SINGLE_CLASS_CALIBRATION):
        assert_calibration_class_support(120, 0, context="calibration subset")


def test_sparse_bin_group_support_is_not_interpretable():
    bins, empty = build_reliability_bins(
        [0.1, 0.2, 0.9, 0.95],
        [0, 0, 1, 1],
        ["G1", "G1", "G2", "G2"],
        n_bins=2,
    )
    assert empty == 0
    assert all(bin.group_count == 1 for bin in bins)
    assert all(not bin.interpretable for bin in bins)
    assert all(bin.reason == REASON_SPARSE_BIN for bin in bins)


def test_balanced_bin_group_support_is_interpretable():
    bins, _ = build_reliability_bins(
        [0.1, 0.2, 0.9, 0.95],
        [0, 0, 1, 1],
        ["G1", "G2", "G1", "G2"],
        n_bins=2,
    )
    assert all(bin.group_count == 2 for bin in bins)
    assert all(bin.interpretable for bin in bins)


def test_overlapping_fit_calibration_evaluation_groups_are_refused():
    with pytest.raises(CalibrationRefusal, match=REASON_OVERLAPPING_GROUPS):
        assert_group_isolation(
            model_fit_groups=("P1", "P2"),
            calibration_groups=("P2", "P3"),
            evaluation_groups=("P4", "P5"),
            group_pair={"P1": "PAIR-1", "P2": "PAIR-2", "P3": "PAIR-3"},
        )


def test_shared_pair_lineage_is_refused():
    with pytest.raises(CalibrationRefusal, match=REASON_SHARED_PAIR):
        assert_group_isolation(
            model_fit_groups=("G1", "G2"),
            calibration_groups=("G3",),
            evaluation_groups=("G4",),
            group_pair={
                "G1": "PAIR-A",
                "G2": "PAIR-B",
                "G3": "PAIR-C",
                "G4": "PAIR-C",
            },
        )


def test_untrusted_label_population_is_refused():
    with pytest.raises(CalibrationRefusal, match=REASON_UNTRUSTED_LABELS):
        assert_label_trust(
            ("R1", "R2"),
            {"R1": {"UNTRUSTED_INFO": 0}, "R2": {"UNTRUSTED_INFO": 3}},
        )


def test_scores_outside_unit_interval_are_refused():
    with pytest.raises(CalibrationRefusal, match=REASON_SCORE_OUT_OF_BOUNDS):
        validate_probability_scores([0.1, 1.2])


def test_non_finite_scores_are_refused():
    with pytest.raises(CalibrationRefusal, match=REASON_NON_FINITE_SCORE):
        validate_probability_scores([0.1, math.nan])
    with pytest.raises(CalibrationRefusal, match=REASON_NON_FINITE_SCORE):
        validate_probability_scores([0.1, math.inf])


def test_default_cv_and_plain_refit_are_refused():
    with pytest.raises(CalibrationRefusal, match=REASON_CV_NOT_GROUP_SAFE):
        validate_calibration_strategy(
            method="sigmoid",
            estimator_mode="FROZEN_ESTIMATOR",
            cv_policy="DEFAULT_CV",
            calibration_samples=500,
        )
    with pytest.raises(CalibrationRefusal, match=REASON_CV_NOT_GROUP_SAFE):
        validate_calibration_strategy(
            method="sigmoid",
            estimator_mode="REFIT_PLAIN_ESTIMATOR",
            cv_policy="EXPLICIT_DISJOINT_GROUPS",
            calibration_samples=500,
        )


def test_isotonic_calibration_is_refused_below_the_documented_sample_caveat():
    with pytest.raises(CalibrationRefusal, match=REASON_ISOTONIC_INSUFFICIENT):
        validate_calibration_strategy(
            method="isotonic",
            estimator_mode="FROZEN_ESTIMATOR",
            cv_policy="EXPLICIT_DISJOINT_GROUPS",
            calibration_samples=500,
        )


def test_changed_model_identity_is_refused():
    from coldguard_ml.w14_calibration import run_grouped_calibration

    tampered = dataclasses.replace(
        CONFIG,
        model_params={**dict(CONFIG.model_params), "learning_rate": 0.06},
    )
    with pytest.raises(CalibrationRefusal, match="predeclared W11 model"):
        run_grouped_calibration(FIXTURE, REGISTRY, tampered, VIEWS["A1B"])


def test_non_synthetic_fixture_is_refused():
    from coldguard_ml.w14_calibration import run_grouped_calibration

    tampered = dataclasses.replace(FIXTURE, provenance="REAL_PHYSICAL")
    with pytest.raises(CalibrationRefusal, match=REASON_NON_SYNTHETIC_FIXTURE):
        run_grouped_calibration(tampered, REGISTRY, CONFIG, VIEWS["A1B"])


def test_brier_is_the_binary_mean_squared_difference():
    labels = [0, 1, 1, 0]
    scores = [0.1, 0.8, 0.6, 0.3]
    expected = sum((y - p) ** 2 for y, p in zip(labels, scores)) / len(labels)
    assert _brier(labels, scores) == pytest.approx(expected)
    assert 0.0 <= _brier(labels, scores) <= 1.0


def test_single_class_evaluation_keeps_ap_undefined_with_reason():
    value, reason = _ap([1, 1, 1], [0.2, 0.7, 0.9])
    assert value is None
    assert reason == REASON_SINGLE_CLASS_EVALUATION


def test_perfect_separation_is_detected_and_flagged():
    assert _perfect_separation([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    assert not _perfect_separation([0, 1], [0.8, 0.2])


def test_calibration_run_is_group_safe_and_synthetic(diagnostics):
    assert diagnostics.schema == CALIBRATION_SCHEMA
    assert diagnostics.scientific_class == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    assert diagnostics.view_id == VIEWS["A1B"].view_id
    assert diagnostics.feature_ids == VIEWS["A1B"].feature_ids
    assert diagnostics.reference_horizon_s == 60.0
    assert diagnostics.reference_horizon_status == (
        "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN"
    )
    assert len(diagnostics.folds) == 4
    assert all(fold.status == "FIT" for fold in diagnostics.folds)
    assert diagnostics.all_folds_group_disjoint
    assert diagnostics.all_folds_pair_disjoint
    assert diagnostics.brier_estimable
    assert diagnostics.discrimination_estimable
    assert diagnostics.perfect_separation
    assert not diagnostics.reliability_interpretable
    assert diagnostics.candidate_family == ("sigmoid",)
    assert diagnostics.isotonic_refusal == REASON_ISOTONIC_INSUFFICIENT


def test_each_development_group_is_evaluated_exactly_once(diagnostics):
    evaluation_groups = [
        group for fold in diagnostics.folds for group in fold.evaluation_groups
    ]
    assert len(evaluation_groups) == len(set(evaluation_groups))
    runs = build_evaluation_runs(
        FIXTURE.development_trajectories,
        FIXTURE.split,
        hardware_config_by_run=FIXTURE.hardware_config_by_run,
    )
    assert set(evaluation_groups) == {run.group_id for run in runs}
    for fold in diagnostics.folds:
        assert set(fold.model_fit_groups).isdisjoint(fold.calibration_groups)
        assert set(fold.model_fit_groups).isdisjoint(fold.evaluation_groups)
        assert set(fold.calibration_groups).isdisjoint(fold.evaluation_groups)
        assert len(fold.calibration_groups) == 2
        assert len(fold.model_fit_groups) == 4
        assert fold.calibration_positive > 0
        assert fold.calibration_negative > 0


def test_calibration_bins_report_counts_support_and_empty_bins(diagnostics):
    assert len(diagnostics.pooled_reliability_bins) == 2
    assert diagnostics.pooled_empty_bin_count == 3
    for bin in diagnostics.pooled_reliability_bins:
        assert bin.count == bin.positive + bin.negative
        assert bin.group_count == 8
        assert bin.mean_score is not None
        assert bin.observed_positive_fraction is not None
    assert all(fold.empty_bin_count == 3 for fold in diagnostics.folds)


def test_no_undefined_calibration_metric_is_replaced_by_zero(diagnostics):
    for fold in diagnostics.folds:
        assert fold.raw_brier is not None
        assert fold.calibrated_brier is not None
        assert fold.raw_ap is not None
        assert fold.calibrated_ap is not None
    # A refused fold would carry None + a reason, never 0.0.
    assert all(
        fold.status == "FIT" or fold.raw_brier is None for fold in diagnostics.folds
    )


def test_calibration_improves_synthetic_brier_but_not_the_claim(diagnostics):
    assert diagnostics.pooled_calibrated_brier < diagnostics.pooled_raw_brier
    assert diagnostics.pooled_raw_ap == 1.0
    assert diagnostics.pooled_calibrated_ap == 1.0
    assert diagnostics.perfect_separation
    assert not diagnostics.reliability_interpretable
