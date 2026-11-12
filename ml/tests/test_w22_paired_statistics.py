"""B-W22-01/B-W22-04 tests: pair admission, descriptives, effect sizes, plot."""

from __future__ import annotations

import math

import pytest

from coldguard_ml.w22_paired_statistics import (
    CONTROLLER_A,
    CONTROLLER_B,
    DZ_UNDEFINED_INSUFFICIENT_N,
    DZ_UNDEFINED_ZERO_SD,
    DIRECTION_IMPROVED,
    DIRECTION_NO_DIFFERENCE,
    DIRECTION_WORSENED,
    ExcludedPair,
    LABEL_SYNTHETIC_TEST_ONLY,
    OUTCOME_ROLE_PRIMARY,
    OUTCOME_ROLE_SECONDARY,
    PairArm,
    PairRecord,
    REASON_ARM_CONTROLLER,
    REASON_DUPLICATE_PAIR_BLOCK,
    REASON_DUPLICATE_PAIR_ID,
    REASON_DUPLICATE_RUN_ID,
    REASON_EVIDENCE_LABEL,
    REASON_EXCLUDED_OVERLAP,
    REASON_MISSING_OUTCOME,
    REASON_NON_FINITE_OUTCOME,
    REASON_NON_NUMERIC_OUTCOME,
    REASON_OUTCOME_MISMATCH,
    REASON_ROLE_MISMATCH,
    REASON_SAME_RUN_BOTH_ARMS,
    REASON_UNIT_MISMATCH,
    RELATIVE_DEFINED,
    RELATIVE_UNDEFINED_FLOOR,
    RELATIVE_UNDEFINED_NO_FLOOR,
    RELATIVE_UNDEFINED_NON_POSITIVE,
    SIGN_CONVENTION,
    W22BoundaryError,
    W22StatisticsError,
    build_paired_dataset,
    describe_pairs,
    paired_effect_size,
    quantile_type7,
    render_every_pair_svg,
)

UNIT = "°C·s"
OUTCOME = "thermal_exposure"


def _record(
    pair_id: str,
    a: float,
    b: float,
    *,
    block_id: str | None = None,
    unit: str = UNIT,
    outcome_id: str = OUTCOME,
    role: str = OUTCOME_ROLE_PRIMARY,
    run_a: str | None = None,
    run_b: str | None = None,
    controller_a: str = CONTROLLER_A,
    controller_b: str = CONTROLLER_B,
    session_id: str | None = "S-01",
    rig_id: str | None = "CG-HW-001",
) -> PairRecord:
    return PairRecord(
        pair_id=pair_id,
        pair_block_id=block_id or f"BLOCK-{pair_id}",
        arm_a=PairArm(
            run_a or f"CG-S2-{controller_a}-{pair_id}", controller_a, a, unit
        ),
        arm_b=PairArm(
            run_b or f"CG-S2-{controller_b}-{pair_id}", controller_b, b, unit
        ),
        outcome_id=outcome_id,
        outcome_role=role,
        session_id=session_id,
        rig_id=rig_id,
    )


def _dataset(
    improvements,
    *,
    base_a: float = 100.0,
    unit: str = UNIT,
    outcome_id: str = OUTCOME,
    role: str = OUTCOME_ROLE_PRIMARY,
    rig_id: str | None = "CG-HW-001",
    session_id: str | None = "S-01",
):
    records = [
        _record(
            f"P-{index:02d}",
            base_a,
            base_a - improvement,
            unit=unit,
            outcome_id=outcome_id,
            role=role,
            rig_id=rig_id,
            session_id=session_id,
        )
        for index, improvement in enumerate(improvements, 1)
    ]
    return build_paired_dataset(records, outcome_id=outcome_id, unit=unit, outcome_role=role)


REFERENCE_IMPROVEMENTS = [2.0, 4.5, -1.0, 0.0, 3.5, 7.0, 2.5, -3.0, 1.5, 5.5]


class TestDescriptives:
    def test_sign_convention_frozen(self):
        assert SIGN_CONVENTION == "I_i = Y_A,i - Y_B,i"
        dataset = _dataset([3.0, -1.0])
        assert dataset.improvements == (3.0, -1.0)

    def test_known_reference_values(self):
        descriptive = describe_pairs(_dataset(REFERENCE_IMPROVEMENTS))
        assert descriptive.pair_count == 10
        assert descriptive.mean_improvement == pytest.approx(2.25, abs=1e-12)
        assert descriptive.median_improvement == pytest.approx(2.25, abs=1e-12)
        assert descriptive.sample_standard_deviation == pytest.approx(
            3.0482235263619804, abs=1e-12
        )
        assert descriptive.population_standard_deviation == pytest.approx(
            2.891798748184251, abs=1e-12
        )
        assert descriptive.q1 == pytest.approx(0.375, abs=1e-12)
        assert descriptive.q3 == pytest.approx(4.25, abs=1e-12)
        assert descriptive.interquartile_range == pytest.approx(3.875, abs=1e-12)
        assert descriptive.minimum_improvement == -3.0
        assert descriptive.maximum_improvement == 7.0
        assert descriptive.pair_ids == tuple(
            f"P-{index:02d}" for index in range(1, 11)
        )
        assert descriptive.y_a[0] == 100.0
        assert descriptive.y_b[0] == 98.0

    def test_sample_vs_population_sd_distinct(self):
        descriptive = describe_pairs(_dataset([1.0, 2.0, 3.0, 4.0]))
        assert descriptive.sample_standard_deviation == pytest.approx(
            1.2909944487358056, abs=1e-12
        )
        assert descriptive.population_standard_deviation == pytest.approx(
            1.118033988749895, abs=1e-12
        )
        assert (
            descriptive.sample_standard_deviation
            > descriptive.population_standard_deviation
        )

    @pytest.mark.parametrize(
        ("values", "probability", "expected"),
        [
            ([1.0, 2.0, 3.0, 4.0], 0.25, 1.75),
            ([1.0, 2.0, 3.0, 4.0], 0.75, 3.25),
            ([0.0, 10.0, 20.0, 30.0], 0.25, 7.5),
            ([0.0, 10.0, 20.0, 30.0], 0.75, 22.5),
            ([5.0], 0.25, 5.0),
        ],
    )
    def test_quantile_type7_pinned(self, values, probability, expected):
        assert quantile_type7(values, probability) == pytest.approx(expected)

    def test_iqr_uses_type7_quantiles(self):
        descriptive = describe_pairs(_dataset([0.0, 10.0, 20.0, 30.0]))
        assert descriptive.q1 == 7.5
        assert descriptive.q3 == 22.5
        assert descriptive.interquartile_range == 15.0

    def test_one_pair_is_descriptive_only(self):
        descriptive = describe_pairs(_dataset([4.0]))
        assert descriptive.pair_count == 1
        assert descriptive.mean_improvement == 4.0
        assert descriptive.sample_standard_deviation is None
        assert descriptive.population_standard_deviation is None
        assert descriptive.q1 == descriptive.q3 == 4.0
        assert "ONE_PAIR_DESCRIPTIVE_ONLY_NO_DISPERSION" in descriptive.notes
        assert "N_BELOW_INFERENTIAL_MINIMUM" in descriptive.notes

    def test_two_pairs_sd_defined(self):
        descriptive = describe_pairs(_dataset([1.0, 3.0]))
        assert descriptive.sample_standard_deviation == pytest.approx(
            2.0 / math.sqrt(2.0)
        )

    def test_constant_differences(self):
        descriptive = describe_pairs(_dataset([2.5, 2.5, 2.5, 2.5]))
        assert descriptive.sample_standard_deviation == 0.0
        assert "CONSTANT_PAIRED_DIFFERENCES_ZERO_DISPERSION" in descriptive.notes

    def test_zero_differences(self):
        descriptive = describe_pairs(_dataset([0.0, 0.0, 0.0]))
        assert descriptive.zero_difference_count == 3
        assert descriptive.direction == DIRECTION_NO_DIFFERENCE
        assert descriptive.mean_improvement == 0.0

    def test_mixed_sign_counts_and_improved_direction(self):
        descriptive = describe_pairs(_dataset([2.0, -1.0, 0.0, 5.0]))
        assert descriptive.positive_difference_count == 2
        assert descriptive.negative_difference_count == 1
        assert descriptive.zero_difference_count == 1
        assert descriptive.direction == DIRECTION_IMPROVED

    def test_negative_improvement_is_worsened_not_beneficial(self):
        descriptive = describe_pairs(_dataset([-4.0, -2.0, -3.0]))
        assert descriptive.direction == DIRECTION_WORSENED
        assert descriptive.mean_improvement == pytest.approx(-3.0)

    def test_reordered_input_is_canonical(self):
        forward = [_record(f"P-{index:02d}", 100.0, 100.0 - value) for index, value in enumerate([1.0, 2.0, 3.0, 4.0], 1)]
        backward = list(reversed(forward))
        dataset_forward = build_paired_dataset(
            forward, outcome_id=OUTCOME, unit=UNIT
        )
        dataset_backward = build_paired_dataset(
            backward, outcome_id=OUTCOME, unit=UNIT
        )
        assert dataset_forward.pair_ids == dataset_backward.pair_ids
        assert dataset_forward.improvements == dataset_backward.improvements
        assert describe_pairs(dataset_forward) == describe_pairs(dataset_backward)

    def test_empty_dataset_rejected(self):
        with pytest.raises(W22StatisticsError):
            build_paired_dataset([], outcome_id=OUTCOME, unit=UNIT)

    def test_excluded_pairs_are_listed_not_admitted(self):
        records = [_record("P-01", 10.0, 8.0), _record("P-02", 12.0, 13.0)]
        dataset = build_paired_dataset(
            records,
            outcome_id=OUTCOME,
            unit=UNIT,
            excluded=[ExcludedPair("P-03", "CENSORED_RECOVERY")],
        )
        descriptive = describe_pairs(dataset)
        assert descriptive.pair_count == 2
        assert descriptive.excluded_pair_count == 1
        assert descriptive.excluded_reasons == (("P-03", "CENSORED_RECOVERY"),)
        assert "P-03" not in descriptive.pair_ids

    def test_excluded_pair_cannot_also_be_admitted(self):
        with pytest.raises(W22StatisticsError) as excinfo:
            build_paired_dataset(
                [_record("P-01", 10.0, 8.0)],
                outcome_id=OUTCOME,
                unit=UNIT,
                excluded=[ExcludedPair("P-01", "CENSORED_RECOVERY")],
            )
        assert excinfo.value.reason_code == REASON_EXCLUDED_OVERLAP

    def test_single_rig_not_presented_as_multiple_sites(self):
        descriptive = describe_pairs(_dataset([1.0, 2.0, 3.0], rig_id="CG-HW-001"))
        assert descriptive.rig_count == 1
        assert descriptive.multi_site_claim_supported is False

    def test_multiple_rig_ids_never_claim_sites(self):
        records = [
            _record("P-01", 10.0, 9.0, rig_id="CG-HW-001"),
            _record("P-02", 10.0, 9.0, rig_id="CG-HW-002"),
        ]
        descriptive = describe_pairs(
            build_paired_dataset(records, outcome_id=OUTCOME, unit=UNIT)
        )
        assert descriptive.rig_count == 2
        assert descriptive.multi_site_claim_supported is False
        assert "MULTIPLE_RIG_IDS_DECLARED_NOT_INDEPENDENT_SITES" in descriptive.notes


class TestPairIntegrity:
    def test_valid_pair_admitted(self):
        dataset = _dataset([2.0, 3.0])
        assert dataset.pair_count == 2
        assert all(
            pair.arm_a.controller == CONTROLLER_A
            and pair.arm_b.controller == CONTROLLER_B
            for pair in dataset.pairs
        )

    def test_two_a_arms_refused(self):
        with pytest.raises(W22StatisticsError) as excinfo:
            build_paired_dataset(
                [_record("P-01", 10.0, 9.0, controller_b=CONTROLLER_A)],
                outcome_id=OUTCOME,
                unit=UNIT,
            )
        assert excinfo.value.reason_code == REASON_ARM_CONTROLLER

    def test_arm_order_reversed_refused(self):
        with pytest.raises(W22StatisticsError) as excinfo:
            build_paired_dataset(
                [_record("P-01", 10.0, 9.0, controller_a=CONTROLLER_B)],
                outcome_id=OUTCOME,
                unit=UNIT,
            )
        assert excinfo.value.reason_code == REASON_ARM_CONTROLLER

    def test_duplicate_pair_id_refused(self):
        first = _record("P-01", 10.0, 9.0, run_a="RUN-A-1", run_b="RUN-B-1")
        second = _record("P-01", 11.0, 9.0, run_a="RUN-A-2", run_b="RUN-B-2")
        with pytest.raises(W22StatisticsError) as excinfo:
            build_paired_dataset([first, second], outcome_id=OUTCOME, unit=UNIT)
        assert excinfo.value.reason_code == REASON_DUPLICATE_PAIR_ID

    def test_run_reused_across_pairs_refused(self):
        first = _record("P-01", 10.0, 9.0, run_a="RUN-SHARED", run_b="RUN-B-1")
        second = _record("P-02", 11.0, 9.0, run_a="RUN-SHARED", run_b="RUN-B-2")
        with pytest.raises(W22StatisticsError) as excinfo:
            build_paired_dataset([first, second], outcome_id=OUTCOME, unit=UNIT)
        assert excinfo.value.reason_code == REASON_DUPLICATE_RUN_ID

    def test_rerun_cannot_become_extra_pair(self):
        first = _record("P-01", 10.0, 9.0, block_id="BLOCK-7")
        rerun = _record("P-01-RERUN", 10.0, 9.5, block_id="BLOCK-7")
        with pytest.raises(W22StatisticsError) as excinfo:
            build_paired_dataset([first, rerun], outcome_id=OUTCOME, unit=UNIT)
        assert excinfo.value.reason_code == REASON_DUPLICATE_PAIR_BLOCK

    def test_same_run_on_both_arms_refused(self):
        with pytest.raises(W22StatisticsError) as excinfo:
            build_paired_dataset(
                [_record("P-01", 10.0, 9.0, run_a="RUN-X", run_b="RUN-X")],
                outcome_id=OUTCOME,
                unit=UNIT,
            )
        assert excinfo.value.reason_code == REASON_SAME_RUN_BOTH_ARMS

    def test_telemetry_windows_cannot_fake_independent_pairs(self):
        records = [
            _record(f"P-{index:02d}", 10.0, 9.0, run_a="RUN-A-001", run_b="RUN-B-001")
            for index in range(1, 6)
        ]
        with pytest.raises(W22StatisticsError) as excinfo:
            build_paired_dataset(records, outcome_id=OUTCOME, unit=UNIT)
        assert excinfo.value.reason_code == REASON_DUPLICATE_RUN_ID

    @pytest.mark.parametrize(
        ("value", "reason"),
        [
            (math.nan, REASON_NON_FINITE_OUTCOME),
            (math.inf, REASON_NON_FINITE_OUTCOME),
            (-math.inf, REASON_NON_FINITE_OUTCOME),
            (None, REASON_MISSING_OUTCOME),
            ("3.5", REASON_NON_NUMERIC_OUTCOME),
            (True, REASON_NON_NUMERIC_OUTCOME),
        ],
    )
    def test_unknown_values_never_become_numbers_or_zero(self, value, reason):
        record = _record("P-01", 10.0, 9.0)
        broken = PairRecord(
            pair_id=record.pair_id,
            pair_block_id=record.pair_block_id,
            arm_a=record.arm_a,
            arm_b=PairArm(record.arm_b.run_id, record.arm_b.controller, value, UNIT),
            outcome_id=record.outcome_id,
            outcome_role=record.outcome_role,
        )
        with pytest.raises(W22StatisticsError) as excinfo:
            build_paired_dataset([broken], outcome_id=OUTCOME, unit=UNIT)
        assert excinfo.value.reason_code == reason

    def test_unit_mismatch_refused(self):
        record = _record("P-01", 10.0, 9.0)
        broken = PairRecord(
            pair_id="P-01",
            pair_block_id="BLOCK-P-01",
            arm_a=record.arm_a,
            arm_b=PairArm(record.arm_b.run_id, CONTROLLER_B, 9.0, "s"),
            outcome_id=OUTCOME,
        )
        with pytest.raises(W22StatisticsError) as excinfo:
            build_paired_dataset([broken], outcome_id=OUTCOME, unit=UNIT)
        assert excinfo.value.reason_code == REASON_UNIT_MISMATCH

    def test_unsupported_unit_refused(self):
        with pytest.raises(W22StatisticsError):
            build_paired_dataset(
                [_record("P-01", 10.0, 9.0)],
                outcome_id=OUTCOME,
                unit="furlongs",
            )

    def test_outcome_mismatch_refused(self):
        with pytest.raises(W22StatisticsError) as excinfo:
            build_paired_dataset(
                [_record("P-01", 10.0, 9.0, outcome_id="recovery_time")],
                outcome_id=OUTCOME,
                unit=UNIT,
            )
        assert excinfo.value.reason_code == REASON_OUTCOME_MISMATCH

    def test_role_mismatch_refused(self):
        with pytest.raises(W22StatisticsError) as excinfo:
            build_paired_dataset(
                [_record("P-01", 10.0, 9.0, role=OUTCOME_ROLE_SECONDARY)],
                outcome_id=OUTCOME,
                unit=UNIT,
            )
        assert excinfo.value.reason_code == REASON_ROLE_MISMATCH

    def test_real_data_bridge_not_implemented(self):
        with pytest.raises(W22BoundaryError) as excinfo:
            build_paired_dataset(
                [_record("P-01", 10.0, 9.0)],
                outcome_id=OUTCOME,
                unit=UNIT,
                evidence_label="PHYSICAL_CAMPAIGN",
            )
        assert excinfo.value.reason_code == REASON_EVIDENCE_LABEL
        assert "future authorized" in str(excinfo.value)


class TestEffectSize:
    def test_paired_dz_uses_paired_difference_sd(self):
        dataset = _dataset([1.0, 2.0, 3.0, 4.0], base_a=100.0)
        effect = paired_effect_size(dataset)
        paired_sd = describe_pairs(dataset).sample_standard_deviation
        assert effect.standardized_dz == pytest.approx(2.5 / paired_sd, abs=1e-12)
        assert effect.standardized_status == "DEFINED"
        assert effect.mean_improvement == pytest.approx(2.5)
        assert effect.mean_y_a == pytest.approx(100.0)
        assert effect.mean_y_b == pytest.approx(97.5)
        assert "DZ_UNSTABLE_SMALL_N" in effect.notes

    def test_dz_is_not_pooled_arm_sd(self):
        dataset = _dataset([1.0, 2.0, 3.0, 4.0], base_a=100.0)
        effect = paired_effect_size(dataset)
        values_a = list(dataset.y_a)
        values_b = list(dataset.y_b)
        pooled = math.sqrt(
            (
                math.fsum((value - 100.0) ** 2 for value in values_a) / 3
                + math.fsum((value - 97.5) ** 2 for value in values_b) / 3
            )
            / 2.0
        )
        assert effect.standardized_dz != pytest.approx(2.5 / pooled, abs=1e-6)

    def test_zero_sd_effect_is_undefined_not_infinite(self):
        effect = paired_effect_size(_dataset([3.0, 3.0, 3.0]))
        assert effect.standardized_dz is None
        assert effect.standardized_status == DZ_UNDEFINED_ZERO_SD
        assert "ZERO_SD_EFFECT_NOT_INFINITE" in effect.notes

    def test_one_pair_effect_undefined(self):
        effect = paired_effect_size(_dataset([3.0]))
        assert effect.standardized_dz is None
        assert effect.standardized_status == DZ_UNDEFINED_INSUFFICIENT_N

    def test_negative_effect_preserves_direction(self):
        effect = paired_effect_size(_dataset([-2.0, -3.0, -4.0]))
        assert effect.standardized_dz is not None
        assert effect.standardized_dz < 0
        assert effect.direction == DIRECTION_WORSENED

    def test_relative_improvement_requires_declared_floor(self):
        effect = paired_effect_size(_dataset([1.0, 2.0, 3.0]))
        assert effect.relative_improvement is None
        assert effect.relative_status == RELATIVE_UNDEFINED_NO_FLOOR

    def test_relative_improvement_defined_with_meaningful_denominator(self):
        dataset = _dataset([4.0, 4.0, 4.0], base_a=100.0)
        effect = paired_effect_size(dataset, denominator_floor=50.0)
        assert effect.relative_improvement == pytest.approx(0.04)
        assert effect.relative_status == RELATIVE_DEFINED

    def test_relative_improvement_refused_for_near_zero_denominator(self):
        dataset = _dataset([1.0, 2.0, 3.0], base_a=10.0)
        effect = paired_effect_size(dataset, denominator_floor=10.0)
        assert effect.relative_improvement is None
        assert effect.relative_status == RELATIVE_UNDEFINED_FLOOR

    def test_relative_improvement_refused_for_non_positive_denominator(self):
        dataset = _dataset([1.0, 2.0], base_a=-5.0, unit="°C", outcome_id="peak_temperature")
        effect = paired_effect_size(dataset, denominator_floor=0.5)
        assert effect.mean_y_a < 0
        assert effect.relative_improvement is None
        assert effect.relative_status == RELATIVE_UNDEFINED_NON_POSITIVE

    def test_negative_denominator_floor_rejected(self):
        with pytest.raises(W22StatisticsError):
            paired_effect_size(_dataset([1.0, 2.0]), denominator_floor=0.0)


class TestEveryPairPlot:
    def test_plot_contains_every_pair_and_test_only_banner(self):
        dataset = _dataset([3.0, -2.0, 0.0, 5.0, 1.0])
        svg = render_every_pair_svg(dataset)
        for pair_id in dataset.pair_ids:
            assert pair_id in svg
        assert "TEST_ONLY" in svg
        assert LABEL_SYNTHETIC_TEST_ONLY in svg
        assert "PRIMARY OUTCOME" in svg
        assert "#1a7f37" in svg
        assert "#cf222e" in svg

    def test_plot_secondary_role_is_explicit(self):
        dataset = _dataset(
            [1.0, 2.0],
            unit="s",
            outcome_id="recovery_time",
            role=OUTCOME_ROLE_SECONDARY,
        )
        svg = render_every_pair_svg(dataset)
        assert "SECONDARY / EXPLORATORY OUTCOME" in svg
        assert "TEST_ONLY" in svg

    def test_plot_is_deterministic(self):
        dataset = _dataset([1.0, -1.0, 2.0])
        assert render_every_pair_svg(dataset) == render_every_pair_svg(dataset)

    def test_constant_values_plot_has_no_zero_range(self):
        dataset = _dataset([2.0, 2.0])
        svg = render_every_pair_svg(dataset)
        assert "NaN" not in svg
        assert "inf" not in svg.lower()
