"""B-W22-05 tests: bounded sensitivity without primary mutation."""

from __future__ import annotations

import pytest

from coldguard_ml.w22_paired_statistics import (
    OUTCOME_ROLE_PRIMARY,
    OUTCOME_ROLE_SECONDARY,
    PairArm,
    PairRecord,
    W22BoundaryError,
    W22StatisticsError,
    build_paired_dataset,
    describe_pairs,
)
from coldguard_ml.w22_sensitivity import (
    KIND_EXTREME_PAIR_INFLUENCE,
    LABEL_SECONDARY_ONLY,
    LABEL_SENSITIVITY_ONLY,
    REASON_SECONDARY_ROLE,
    REASON_SECONDARY_SAME_OUTCOME,
    SENSITIVITY_STATUS_EXPLORATORY,
    SENSITIVITY_STATUS_PREDECLARED,
    assert_primary_intact,
    compare_intervals,
    extreme_pair_influence,
    leave_one_pair_out,
    mean_vs_median,
    refuse_horizon_sensitivity,
    secondary_outcome_contrast,
)
from coldguard_ml.w22_uncertainty import (
    INTERVAL_ROLE_PRIMARY,
    INTERVAL_ROLE_SENSITIVITY,
    METHOD_PAIRED_T_INTERVAL,
    bootstrap_percentile_interval,
    paired_t_interval,
    predeclare_interval_method,
)

UNIT = "°C·s"


def _dataset(improvements, *, role=OUTCOME_ROLE_PRIMARY, outcome_id="thermal_exposure", unit=UNIT):
    records = [
        PairRecord(
            pair_id=f"P-{index:02d}",
            pair_block_id=f"BLOCK-{index:02d}",
            arm_a=PairArm(f"CG-S2-A-{index:03d}", "A", 100.0, unit),
            arm_b=PairArm(f"CG-S2-B-{index:03d}", "B", 100.0 - value, unit),
            outcome_id=outcome_id,
            outcome_role=role,
            session_id="S-01",
            rig_id="CG-HW-001",
        )
        for index, value in enumerate(improvements, 1)
    ]
    return build_paired_dataset(
        records, outcome_id=outcome_id, unit=unit, outcome_role=role
    )


IMPROVEMENTS = [4.0, 2.0, 6.0, 1.0, 3.0]


class TestMeanVsMedian:
    def test_labels_and_values(self):
        dataset = _dataset([1.0, 2.0, 100.0])
        descriptive = describe_pairs(dataset)
        result = mean_vs_median(dataset, descriptive)
        assert result.kind == "MEAN_VS_MEDIAN"
        assert result.declared_status == SENSITIVITY_STATUS_EXPLORATORY
        assert result.statistic == "MEDIAN"
        assert result.statistic_value == 2.0
        assert result.primary_statistic == "MEAN"
        assert result.primary_value == descriptive.mean_improvement
        assert result.difference_from_primary == pytest.approx(2.0 - descriptive.mean_improvement)
        assert result.label == LABEL_SENSITIVITY_ONLY
        assert result.promotion_allowed is False
        assert result.valid_n == 3
        assert result.primary_n == 3

    def test_predeclared_requires_plan_reference(self):
        dataset = _dataset(IMPROVEMENTS)
        descriptive = describe_pairs(dataset)
        with pytest.raises(W22StatisticsError):
            mean_vs_median(
                dataset,
                descriptive,
                declared_status=SENSITIVITY_STATUS_PREDECLARED,
            )
        result = mean_vs_median(
            dataset,
            descriptive,
            declared_status=SENSITIVITY_STATUS_PREDECLARED,
            plan_reference="W22-TOY-PLAN-v1",
        )
        assert result.declared_status == SENSITIVITY_STATUS_PREDECLARED
        assert result.plan_reference == "W22-TOY-PLAN-v1"


class TestLeaveOnePairOut:
    def test_each_pair_reported_and_primary_untouched(self):
        dataset = _dataset(IMPROVEMENTS)
        descriptive = describe_pairs(dataset)
        results = leave_one_pair_out(dataset, descriptive)
        assert len(results) == len(IMPROVEMENTS)
        assert {item.omitted_pair_ids[0] for item in results} == set(
            descriptive.pair_ids
        )
        for item in results:
            assert item.kind == "LEAVE_ONE_PAIR_OUT"
            assert item.valid_n == descriptive.pair_count - 1
            assert item.primary_n == descriptive.pair_count
            assert item.primary_value == descriptive.mean_improvement
            assert item.label == LABEL_SENSITIVITY_ONLY
            assert item.promotion_allowed is False
            assert item.interpretation_boundary
        assert describe_pairs(dataset) == descriptive
        assert_primary_intact(descriptive, describe_pairs(dataset))

    def test_omitted_value_matches_manual_mean(self):
        dataset = _dataset(IMPROVEMENTS)
        descriptive = describe_pairs(dataset)
        result = leave_one_pair_out(
            dataset, descriptive, omit_pair_ids=["P-03"]
        )[0]
        remaining = [4.0, 2.0, 1.0, 3.0]
        assert result.statistic_value == pytest.approx(sum(remaining) / 4)

    def test_unknown_pair_rejected(self):
        dataset = _dataset(IMPROVEMENTS)
        descriptive = describe_pairs(dataset)
        with pytest.raises(W22StatisticsError):
            leave_one_pair_out(dataset, descriptive, omit_pair_ids=["P-99"])

    def test_omitting_does_not_invalidate_pair(self):
        dataset = _dataset(IMPROVEMENTS)
        descriptive = describe_pairs(dataset)
        result = leave_one_pair_out(
            dataset, descriptive, omit_pair_ids=["P-01"]
        )[0]
        assert result.omitted_pair_ids == ("P-01",)
        assert "neither an invalidation" in result.interpretation_boundary
        assert descriptive.excluded_pair_count == 0


class TestExtremePairInfluence:
    def test_extreme_pair_identified_and_retained(self):
        dataset = _dataset([3.0, 3.0, 3.0, 50.0])
        descriptive = describe_pairs(dataset)
        result = extreme_pair_influence(dataset, descriptive)
        assert result.kind == KIND_EXTREME_PAIR_INFLUENCE
        assert result.omitted_pair_ids == ("P-04",)
        assert result.primary_n == 4
        assert result.valid_n == 3
        assert result.promotion_allowed is False
        assert describe_pairs(dataset).pair_count == 4
        assert "P-04" in describe_pairs(dataset).pair_ids

    def test_extreme_pair_not_removed_from_primary_even_if_significance_changes(self):
        dataset = _dataset([1.0, 1.0, 1.0, 40.0])
        before = describe_pairs(dataset)
        extreme_pair_influence(dataset, before)
        after = describe_pairs(dataset)
        assert before == after
        assert after.pair_count == 4


class TestIntervalComparison:
    def test_primary_interval_is_declared_not_chosen(self):
        dataset = _dataset(IMPROVEMENTS)
        primary = paired_t_interval(dataset, role=INTERVAL_ROLE_PRIMARY)
        sensitivity = bootstrap_percentile_interval(
            dataset,
            seed=9,
            iterations=500,
            role=INTERVAL_ROLE_SENSITIVITY,
            test_only_settings=True,
        )
        comparison = compare_intervals(
            primary=primary,
            sensitivity=sensitivity,
            declaration=predeclare_interval_method(
                primary_method=METHOD_PAIRED_T_INTERVAL,
                method_freeze_id="CI-FREEZE-1",
            ),
        )
        assert comparison.primary_method == primary.method
        assert comparison.sensitivity_method == sensitivity.method
        assert comparison.label == LABEL_SENSITIVITY_ONLY
        assert comparison.promotion_allowed is False
        assert comparison.selection_rule == (
            "PREDECLARED_NO_FAVORABILITY_OR_WIDTH_SELECTION"
        )

    def test_narrower_sensitivity_cannot_become_primary(self):
        dataset = _dataset(IMPROVEMENTS)
        primary = paired_t_interval(dataset, role=INTERVAL_ROLE_PRIMARY)
        sensitivity = bootstrap_percentile_interval(
            dataset,
            seed=9,
            iterations=500,
            role=INTERVAL_ROLE_SENSITIVITY,
            test_only_settings=True,
        )
        comparison = compare_intervals(
            primary=primary,
            sensitivity=sensitivity,
            declaration=predeclare_interval_method(
                primary_method=METHOD_PAIRED_T_INTERVAL,
                method_freeze_id="CI-FREEZE-1",
            ),
        )
        assert comparison.primary_method == "PAIRED_T_95_CI"


class TestSecondaryOutcome:
    def test_secondary_outcome_not_promoted(self):
        primary = _dataset(IMPROVEMENTS)
        secondary = _dataset(
            [1.0, 1.0, 2.0, 1.0],
            role=OUTCOME_ROLE_SECONDARY,
            outcome_id="recovery_time",
            unit="s",
        )
        result = secondary_outcome_contrast(primary, secondary)
        assert result.kind == "SECONDARY_OUTCOME_CONTRAST"
        assert result.outcome_id == "recovery_time"
        assert result.label == LABEL_SECONDARY_ONLY
        assert result.promotion_allowed is False
        assert result.statistic_value == pytest.approx(1.25)

    def test_primary_outcome_cannot_be_used_as_secondary_contrast(self):
        primary = _dataset(IMPROVEMENTS)
        same_role = _dataset([1.0, 2.0])
        with pytest.raises(W22StatisticsError) as excinfo:
            secondary_outcome_contrast(primary, same_role)
        assert excinfo.value.reason_code == REASON_SECONDARY_ROLE

    def test_same_outcome_cannot_be_recast_as_secondary(self):
        primary = _dataset(IMPROVEMENTS)
        secondary = _dataset(
            [1.0, 2.0], role=OUTCOME_ROLE_SECONDARY, outcome_id="thermal_exposure"
        )
        with pytest.raises(W22StatisticsError) as excinfo:
            secondary_outcome_contrast(primary, secondary)
        assert excinfo.value.reason_code == REASON_SECONDARY_SAME_OUTCOME


class TestHorizonAndPrimaryIntegrity:
    def test_horizon_sensitivity_is_refused(self):
        with pytest.raises(W22BoundaryError) as excinfo:
            refuse_horizon_sensitivity()
        assert excinfo.value.reason_code == (
            "HORIZON_SENSITIVITY_REQUIRES_FROZEN_MODEL_EVIDENCE"
        )

    def test_primary_mutation_guard(self):
        before = describe_pairs(_dataset(IMPROVEMENTS))
        after = describe_pairs(_dataset(IMPROVEMENTS + [9.0]))
        with pytest.raises(W22StatisticsError):
            assert_primary_intact(before, after)
