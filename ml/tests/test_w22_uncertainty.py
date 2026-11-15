"""B-W22-02/B-W22-03 tests: Student-t CI, bootstrap, predeclared tests."""

from __future__ import annotations

import math

import pytest

from coldguard_ml.w22_paired_statistics import (
    PairArm,
    PairRecord,
    build_paired_dataset,
)
from coldguard_ml.w22_uncertainty import (
    ALTERNATIVE_GREATER,
    ALTERNATIVE_LESS,
    ALTERNATIVE_TWO_SIDED,
    ASSUMPTION_LICENSE_PAIRED_T,
    ASSUMPTION_LICENSE_SIGN,
    ASSUMPTION_LICENSE_WILCOXON,
    BOOTSTRAP_MIN_ITERATIONS,
    CLAIM_BOUNDARY,
    INTERVAL_ROLE_PRIMARY,
    INTERVAL_ROLE_SENSITIVITY,
    METHOD_BOOTSTRAP_PERCENTILE,
    METHOD_PAIRED_T_INTERVAL,
    REASON_BOOTSTRAP_ITERATIONS,
    REASON_BOOTSTRAP_SEED_REQUIRED,
    REASON_CONFIDENCE_LEVEL,
    REASON_INSUFFICIENT_PAIRS,
    REASON_INTERVAL_MISMATCH,
    REASON_ZERO_DISPERSION,
    STATUS_ESTIMABLE,
    STATUS_NOT_ESTIMABLE,
    TEST_PAIRED_T,
    TEST_REASON_ASSUMPTION_LICENSE,
    TEST_REASON_FALLBACK_EVIDENCE,
    TEST_REASON_FALLBACK_LICENSE,
    TEST_REASON_FREEZE_ID,
    TEST_REASON_ZERO_DISPERSION,
    TEST_SIGN,
    TEST_STATUS_ESTIMABLE,
    TEST_STATUS_NOT_ESTIMABLE,
    TEST_WILCOXON,
    TestDeclaration as Declaration,
    W22InferenceError,
    assert_single_primary,
    bootstrap_percentile_interval,
    paired_t_interval,
    predeclare_interval_method,
    predeclare_test,
    resolve_primary_interval,
    run_predeclared_test,
    student_t_cdf,
    student_t_critical,
)

UNIT = "°C·s"
OUTCOME = "thermal_exposure"

REFERENCE_T = {
    1: 12.706204736174694,
    2: 4.302652729749462,
    3: 3.1824463052837078,
    4: 2.7764451051977934,
    5: 2.5705818356363146,
    10: 2.2281388519862744,
    20: 2.085963447265864,
    30: 2.0422724563012378,
    100: 1.983971518523552,
}

REFERENCE_IMPROVEMENTS = [2.0, 4.5, -1.0, 0.0, 3.5, 7.0, 2.5, -3.0, 1.5, 5.5]


def _dataset(improvements, *, base_a=100.0, unit=UNIT, outcome_id=OUTCOME):
    records = [
        PairRecord(
            pair_id=f"P-{index:02d}",
            pair_block_id=f"BLOCK-{index:02d}",
            arm_a=PairArm(f"CG-S2-A-{index:03d}", "A", base_a, unit),
            arm_b=PairArm(
                f"CG-S2-B-{index:03d}", "B", base_a - improvement, unit
            ),
            outcome_id=outcome_id,
            session_id="S-01",
            rig_id="CG-HW-001",
        )
        for index, improvement in enumerate(improvements, 1)
    ]
    return build_paired_dataset(records, outcome_id=outcome_id, unit=unit)


def _dataset_ab(values_a, values_b):
    records = [
        PairRecord(
            pair_id=f"P-{index:02d}",
            pair_block_id=f"BLOCK-{index:02d}",
            arm_a=PairArm(f"CG-S2-A-{index:03d}", "A", value_a, UNIT),
            arm_b=PairArm(f"CG-S2-B-{index:03d}", "B", value_b, UNIT),
            outcome_id=OUTCOME,
            session_id="S-01",
            rig_id="CG-HW-001",
        )
        for index, (value_a, value_b) in enumerate(
            zip(values_a, values_b), 1
        )
    ]
    return build_paired_dataset(records, outcome_id=OUTCOME, unit=UNIT)


class TestStudentT:
    @pytest.mark.parametrize(("degrees", "expected"), sorted(REFERENCE_T.items()))
    def test_critical_values_match_reference(self, degrees, expected):
        assert student_t_critical(0.975, degrees) == pytest.approx(
            expected, abs=1e-9
        )

    @pytest.mark.parametrize(
        ("value", "degrees", "expected"),
        [
            (2.5, 10, 0.9842765778816955),
            (2.0, 4, 0.9419417382415922),
            (0.5, 5, 0.6808505641795354),
            (-1.2, 7, 0.1345859684136033),
            (0.0, 9, 0.5),
        ],
    )
    def test_cdf_matches_reference(self, value, degrees, expected):
        assert student_t_cdf(value, degrees) == pytest.approx(expected, abs=1e-11)

    def test_cdf_symmetry(self):
        for value in (0.3, 1.7, 4.2):
            assert student_t_cdf(value, 8) + student_t_cdf(-value, 8) == pytest.approx(
                1.0, abs=1e-12
            )

    def test_invalid_degrees_rejected(self):
        with pytest.raises(W22InferenceError):
            student_t_critical(0.975, 0)

    def test_critical_is_not_universal_196(self):
        critical = student_t_critical(0.975, 4)
        assert critical == pytest.approx(2.7764451051977934, abs=1e-9)
        assert critical > 1.96


class TestPairedTInterval:
    def test_reference_interval_and_degrees_of_freedom(self):
        estimate = paired_t_interval(_dataset(REFERENCE_IMPROVEMENTS))
        assert estimate.method == METHOD_PAIRED_T_INTERVAL
        assert estimate.status == STATUS_ESTIMABLE
        assert estimate.role == INTERVAL_ROLE_PRIMARY
        assert estimate.lower == pytest.approx(0.06943224947470528, abs=1e-11)
        assert estimate.upper == pytest.approx(4.430567750525295, abs=1e-11)
        assert estimate.point_estimate == pytest.approx(2.25, abs=1e-12)
        assert estimate.degrees_of_freedom == 9
        assert estimate.critical_value == pytest.approx(2.262157162798205, abs=1e-9)
        assert estimate.pair_count == 10
        assert estimate.research_grade is True

    def test_standard_error_formula(self):
        estimate = paired_t_interval(_dataset([1.0, 2.0, 2.0, 3.0]))
        expected_se = 0.816496580927726 / math.sqrt(4)
        assert estimate.standard_error == pytest.approx(expected_se, abs=1e-12)

    def test_small_n_refused(self):
        estimate = paired_t_interval(_dataset([1.0, 2.0]))
        assert estimate.status == STATUS_NOT_ESTIMABLE
        assert estimate.reason_code == REASON_INSUFFICIENT_PAIRS
        assert estimate.lower is None and estimate.upper is None

    def test_constant_differences_refused_with_constant_reported(self):
        estimate = paired_t_interval(_dataset([3.0, 3.0, 3.0]))
        assert estimate.status == STATUS_NOT_ESTIMABLE
        assert estimate.reason_code == REASON_ZERO_DISPERSION
        assert estimate.constant_value == 3.0
        assert estimate.lower is None

    def test_confidence_level_validated(self):
        with pytest.raises(W22InferenceError) as excinfo:
            paired_t_interval(_dataset([1.0, 2.0, 3.0]), confidence_level=0.90)
        assert excinfo.value.reason_code == REASON_CONFIDENCE_LEVEL
        with pytest.raises(W22InferenceError) as excinfo:
            bootstrap_percentile_interval(
                _dataset([1.0, 2.0, 3.0]),
                seed=1,
                iterations=500,
                confidence_level=0.90,
            )
        assert excinfo.value.reason_code == REASON_CONFIDENCE_LEVEL


class TestBootstrap:
    def test_reproducible_under_frozen_seed(self):
        dataset = _dataset(REFERENCE_IMPROVEMENTS)
        first = bootstrap_percentile_interval(
            dataset, seed=20261110, iterations=BOOTSTRAP_MIN_ITERATIONS
        )
        second = bootstrap_percentile_interval(
            dataset, seed=20261110, iterations=BOOTSTRAP_MIN_ITERATIONS
        )
        assert first == second
        assert first.status == STATUS_ESTIMABLE
        assert first.research_grade is True
        assert first.lower < first.point_estimate < first.upper
        assert first.resampling_unit == "COMPLETE_MATCHED_PAIRS"
        assert first.draw_digest == second.draw_digest
        assert len(first.draw_digest or "") == 64

    def test_different_seed_changes_digest(self):
        dataset = _dataset(REFERENCE_IMPROVEMENTS)
        first = bootstrap_percentile_interval(
            dataset, seed=1, iterations=500, test_only_settings=True
        )
        second = bootstrap_percentile_interval(
            dataset, seed=2, iterations=500, test_only_settings=True
        )
        assert first.draw_digest != second.draw_digest

    def test_pairs_are_resampled_not_arms(self):
        base = _dataset([1.0, -1.0, 2.0, -2.0], base_a=10.0)
        shifted = _dataset([1.0, -1.0, 2.0, -2.0], base_a=1000.0)
        first = bootstrap_percentile_interval(
            base, seed=11, iterations=300, test_only_settings=True
        )
        second = bootstrap_percentile_interval(
            shifted, seed=11, iterations=300, test_only_settings=True
        )
        assert first.draw_digest == second.draw_digest
        assert first.lower == second.lower and first.upper == second.upper

    def test_zero_dispersion_refused(self):
        estimate = bootstrap_percentile_interval(
            _dataset([2.0, 2.0, 2.0]), seed=5, iterations=500
        )
        assert estimate.status == STATUS_NOT_ESTIMABLE
        assert estimate.reason_code in {
            REASON_ZERO_DISPERSION,
            "CI_NOT_ESTIMABLE_BOOTSTRAP_COLLAPSE",
        }

    def test_insufficient_pairs_refused(self):
        estimate = bootstrap_percentile_interval(
            _dataset([1.0, 2.0]), seed=5, iterations=500
        )
        assert estimate.status == STATUS_NOT_ESTIMABLE
        assert estimate.reason_code == REASON_INSUFFICIENT_PAIRS

    def test_unseeded_bootstrap_refused(self):
        estimate = bootstrap_percentile_interval(
            _dataset([1.0, 2.0, 3.0]), seed=None
        )
        assert estimate.status == STATUS_NOT_ESTIMABLE
        assert estimate.reason_code == REASON_BOOTSTRAP_SEED_REQUIRED

    def test_iteration_policy_enforced(self):
        estimate = bootstrap_percentile_interval(
            _dataset([1.0, 2.0, 3.0]),
            seed=5,
            iterations=BOOTSTRAP_MIN_ITERATIONS - 1,
        )
        assert estimate.status == STATUS_NOT_ESTIMABLE
        assert estimate.reason_code == REASON_BOOTSTRAP_ITERATIONS

    def test_test_only_settings_are_labelled(self):
        estimate = bootstrap_percentile_interval(
            _dataset([1.0, 2.0, 3.0]),
            seed=5,
            iterations=250,
            test_only_settings=True,
        )
        assert estimate.status == STATUS_ESTIMABLE
        assert estimate.research_grade is False
        assert "IMPLEMENTATION_TEST_SETTINGS_NOT_FINAL_RESEARCH_SETTINGS" in estimate.notes

    def test_bootstrap_role_can_be_sensitivity(self):
        estimate = bootstrap_percentile_interval(
            _dataset([1.0, 2.0, 3.0]),
            seed=5,
            iterations=500,
            role=INTERVAL_ROLE_SENSITIVITY,
            test_only_settings=True,
        )
        assert estimate.role == INTERVAL_ROLE_SENSITIVITY


class TestPrimaryIntervalPolicy:
    def test_primary_is_returned_even_if_sensitivity_is_narrower(self):
        dataset = _dataset(REFERENCE_IMPROVEMENTS)
        primary = paired_t_interval(dataset, role=INTERVAL_ROLE_PRIMARY)
        sensitivity = bootstrap_percentile_interval(
            dataset,
            seed=3,
            iterations=500,
            role=INTERVAL_ROLE_SENSITIVITY,
            test_only_settings=True,
        )
        declaration = predeclare_interval_method(
            primary_method=METHOD_PAIRED_T_INTERVAL,
            method_freeze_id="CI-FREEZE-1",
        )
        chosen = resolve_primary_interval(
            primary=primary, sensitivity=sensitivity, declaration=declaration
        )
        assert chosen.method == METHOD_PAIRED_T_INTERVAL

    def test_second_primary_refused(self):
        dataset = _dataset(REFERENCE_IMPROVEMENTS)
        first = paired_t_interval(dataset, role=INTERVAL_ROLE_PRIMARY)
        second = bootstrap_percentile_interval(
            dataset, seed=3, iterations=500, role=INTERVAL_ROLE_PRIMARY
        )
        declaration = predeclare_interval_method(
            primary_method=METHOD_PAIRED_T_INTERVAL,
            method_freeze_id="CI-FREEZE-1",
        )
        with pytest.raises(W22InferenceError):
            resolve_primary_interval(
                primary=first, sensitivity=second, declaration=declaration
            )
        with pytest.raises(W22InferenceError):
            assert_single_primary([first, second])

    def test_declared_method_mismatch_refused(self):
        dataset = _dataset(REFERENCE_IMPROVEMENTS)
        primary = paired_t_interval(dataset, role=INTERVAL_ROLE_PRIMARY)
        sensitivity = bootstrap_percentile_interval(
            dataset,
            seed=3,
            iterations=500,
            role=INTERVAL_ROLE_SENSITIVITY,
            test_only_settings=True,
        )
        declaration = predeclare_interval_method(
            primary_method=METHOD_BOOTSTRAP_PERCENTILE,
            method_freeze_id="CI-FREEZE-1",
        )
        with pytest.raises(W22InferenceError) as excinfo:
            resolve_primary_interval(
                primary=primary, sensitivity=sensitivity, declaration=declaration
            )
        assert excinfo.value.reason_code == REASON_INTERVAL_MISMATCH

    def test_predeclared_interval_method_validated(self):
        with pytest.raises(W22InferenceError):
            predeclare_interval_method(
                primary_method="MAGIC_CI", method_freeze_id="CI-FREEZE-1"
            )
        with pytest.raises(W22InferenceError):
            predeclare_interval_method(
                primary_method=METHOD_PAIRED_T_INTERVAL, method_freeze_id=" "
            )

    def test_exactly_one_primary_required(self):
        dataset = _dataset(REFERENCE_IMPROVEMENTS)
        first = paired_t_interval(dataset, role=INTERVAL_ROLE_PRIMARY)
        assert assert_single_primary([first]) is first
        with pytest.raises(W22InferenceError):
            assert_single_primary([])


class TestPredeclaredTestFamily:
    def _declaration(self, family, licenses, **kwargs):
        return predeclare_test(
            preferred_test_family=family,
            method_freeze_id="W22-TOY-METHOD-FREEZE-1",
            assumption_licenses=licenses,
            **kwargs,
        )

    def test_paired_t_reference(self):
        result = run_predeclared_test(
            _dataset(REFERENCE_IMPROVEMENTS),
            self._declaration(TEST_PAIRED_T, [ASSUMPTION_LICENSE_PAIRED_T]),
        )
        assert result.family == TEST_PAIRED_T
        assert result.status == TEST_STATUS_ESTIMABLE
        assert result.statistic == pytest.approx(2.334187330372938, abs=1e-12)
        assert result.p_value == pytest.approx(0.04444134080429975, abs=1e-12)
        assert result.degrees_of_freedom == 9
        assert result.alternative == ALTERNATIVE_TWO_SIDED
        assert result.claim_boundary == CLAIM_BOUNDARY
        assert result.fallback_applied is False

    def test_sign_test_reference(self):
        result = run_predeclared_test(
            _dataset(REFERENCE_IMPROVEMENTS),
            self._declaration(TEST_SIGN, [ASSUMPTION_LICENSE_SIGN]),
        )
        assert result.statistic == 7.0
        assert result.p_value == pytest.approx(0.1796875, abs=1e-12)
        assert result.non_zero_pairs == 9
        assert result.zero_differences == 1

    def test_wilcoxon_exact_reference(self):
        result = run_predeclared_test(
            _dataset(REFERENCE_IMPROVEMENTS),
            self._declaration(TEST_WILCOXON, [ASSUMPTION_LICENSE_WILCOXON]),
        )
        assert result.statistic == pytest.approx(39.0)
        assert result.p_value == pytest.approx(0.0546875, abs=1e-12)
        assert result.exact is True
        assert result.non_zero_pairs == 9
        assert result.zero_differences == 1

    def test_wilcoxon_midrank_tie_policy(self):
        values = [1, -2, 3, -4, 5, 0, 2, -2, 6, -7, 8, 1]
        result = run_predeclared_test(
            _dataset(values),
            self._declaration(TEST_WILCOXON, [ASSUMPTION_LICENSE_WILCOXON]),
        )
        assert result.statistic == pytest.approx(41.0)
        assert result.p_value == pytest.approx(0.5078125, abs=1e-12)
        assert result.non_zero_pairs == 11
        assert result.zero_differences == 1

    def test_wilcoxon_normal_approximation_above_exact_limit(self):
        values = [float(index) for index in range(1, 18)]
        result = run_predeclared_test(
            _dataset(values),
            self._declaration(TEST_WILCOXON, [ASSUMPTION_LICENSE_WILCOXON]),
        )
        assert result.exact is False
        assert 0.0 < result.p_value < 1.0
        exact_limit = run_predeclared_test(
            _dataset(values[:16]),
            self._declaration(TEST_WILCOXON, [ASSUMPTION_LICENSE_WILCOXON]),
        )
        assert exact_limit.exact is True

    def test_paired_test_not_independent_sample_test(self):
        dataset = _dataset_ab([10, 12, 14, 16], [9, 11, 12, 15])
        result = run_predeclared_test(
            dataset,
            self._declaration(TEST_PAIRED_T, [ASSUMPTION_LICENSE_PAIRED_T]),
        )
        assert result.p_value == pytest.approx(0.015392438073302294, abs=1e-12)
        assert result.p_value != pytest.approx(0.5127016478725178, abs=1e-3)
        assert result.pair_count == 4

    def test_no_smallest_p_value_selection(self):
        dataset = _dataset([1.0, -2.0, 3.0, -4.0, 5.0, -6.0, 7.0], base_a=50.0)
        t_result = run_predeclared_test(
            dataset,
            self._declaration(TEST_PAIRED_T, [ASSUMPTION_LICENSE_PAIRED_T]),
        )
        sign_result = run_predeclared_test(
            dataset,
            self._declaration(TEST_SIGN, [ASSUMPTION_LICENSE_SIGN]),
        )
        assert t_result.family == TEST_PAIRED_T
        assert sign_result.family == TEST_SIGN
        assert t_result.family != sign_result.family

    def test_license_required(self):
        result = run_predeclared_test(
            _dataset(REFERENCE_IMPROVEMENTS),
            self._declaration(TEST_PAIRED_T, []),
        )
        assert result.status == TEST_STATUS_NOT_ESTIMABLE
        assert result.reason_code == TEST_REASON_ASSUMPTION_LICENSE

    def test_wilcoxon_license_required(self):
        result = run_predeclared_test(
            _dataset(REFERENCE_IMPROVEMENTS),
            self._declaration(TEST_WILCOXON, [ASSUMPTION_LICENSE_PAIRED_T]),
        )
        assert result.status == TEST_STATUS_NOT_ESTIMABLE
        assert result.reason_code == TEST_REASON_ASSUMPTION_LICENSE

    def test_freeze_id_required(self):
        with pytest.raises(W22InferenceError) as excinfo:
            predeclare_test(
                preferred_test_family=TEST_PAIRED_T,
                method_freeze_id="  ",
                assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T],
            )
        assert excinfo.value.reason_code == TEST_REASON_FREEZE_ID

    def test_unknown_family_rejected(self):
        with pytest.raises(W22InferenceError):
            predeclare_test(
                preferred_test_family="MAGIC_TEST",
                method_freeze_id="FREEZE-1",
                assumption_licenses=[],
            )

    def test_invalid_alternative_in_direct_declaration_rejected(self):
        declaration = Declaration(
            preferred_test_family=TEST_PAIRED_T,
            method_freeze_id="FREEZE-1",
            assumption_licenses=(ASSUMPTION_LICENSE_PAIRED_T,),
            alternative="banana",
        )
        with pytest.raises(W22InferenceError):
            run_predeclared_test(_dataset(REFERENCE_IMPROVEMENTS), declaration)

    def test_fallback_requires_reason_code(self):
        with pytest.raises(W22InferenceError):
            predeclare_test(
                preferred_test_family=TEST_PAIRED_T,
                method_freeze_id="FREEZE-1",
                assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T],
                fallback_test_family=TEST_SIGN,
            )

    def test_fallback_cannot_be_same_family(self):
        with pytest.raises(W22InferenceError):
            predeclare_test(
                preferred_test_family=TEST_PAIRED_T,
                method_freeze_id="FREEZE-1",
                assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T],
                fallback_test_family=TEST_PAIRED_T,
                fallback_reason_code=TEST_REASON_ZERO_DISPERSION,
            )

    def test_t_zero_dispersion_refused(self):
        result = run_predeclared_test(
            _dataset([2.0, 2.0, 2.0, 2.0]),
            self._declaration(TEST_PAIRED_T, [ASSUMPTION_LICENSE_PAIRED_T]),
        )
        assert result.status == TEST_STATUS_NOT_ESTIMABLE
        assert result.reason_code == TEST_REASON_ZERO_DISPERSION

    def test_t_insufficient_pairs_refused_but_sign_runs(self):
        dataset = _dataset([1.0, 3.0])
        t_result = run_predeclared_test(
            dataset,
            self._declaration(TEST_PAIRED_T, [ASSUMPTION_LICENSE_PAIRED_T]),
        )
        sign_result = run_predeclared_test(
            dataset,
            self._declaration(TEST_SIGN, [ASSUMPTION_LICENSE_SIGN]),
        )
        assert t_result.status == TEST_STATUS_NOT_ESTIMABLE
        assert sign_result.status == TEST_STATUS_ESTIMABLE

    def test_predeclared_fallback_applied_with_evidence(self):
        declaration = self._declaration(
            TEST_PAIRED_T,
            [ASSUMPTION_LICENSE_PAIRED_T, ASSUMPTION_LICENSE_SIGN],
            fallback_test_family=TEST_SIGN,
            fallback_reason_code=TEST_REASON_ZERO_DISPERSION,
        )
        result = run_predeclared_test(
            _dataset([2.0, 2.0, 2.0, 2.0]),
            declaration,
            fallback_evidence="constant paired differences preclude a t statistic",
        )
        assert result.family == TEST_SIGN
        assert result.status == TEST_STATUS_ESTIMABLE
        assert result.fallback_applied is True
        assert result.fallback_family == TEST_SIGN
        assert result.preferred_failure_reason == TEST_REASON_ZERO_DISPERSION
        assert result.p_value == pytest.approx(0.125)

    def test_fallback_without_evidence_refused(self):
        declaration = self._declaration(
            TEST_PAIRED_T,
            [ASSUMPTION_LICENSE_PAIRED_T, ASSUMPTION_LICENSE_SIGN],
            fallback_test_family=TEST_SIGN,
            fallback_reason_code=TEST_REASON_ZERO_DISPERSION,
        )
        result = run_predeclared_test(
            _dataset([2.0, 2.0, 2.0, 2.0]), declaration
        )
        assert result.status == TEST_STATUS_NOT_ESTIMABLE
        assert result.reason_code == TEST_REASON_FALLBACK_EVIDENCE

    def test_fallback_without_license_refused(self):
        declaration = self._declaration(
            TEST_PAIRED_T,
            [ASSUMPTION_LICENSE_PAIRED_T],
            fallback_test_family=TEST_SIGN,
            fallback_reason_code=TEST_REASON_ZERO_DISPERSION,
        )
        result = run_predeclared_test(
            _dataset([2.0, 2.0, 2.0, 2.0]),
            declaration,
            fallback_evidence="declared diagnostic evidence",
        )
        assert result.status == TEST_STATUS_NOT_ESTIMABLE
        assert result.reason_code == TEST_REASON_FALLBACK_LICENSE

    def test_fallback_only_for_matching_declared_reason(self):
        declaration = self._declaration(
            TEST_PAIRED_T,
            [ASSUMPTION_LICENSE_PAIRED_T, ASSUMPTION_LICENSE_SIGN],
            fallback_test_family=TEST_SIGN,
            fallback_reason_code="TEST_NOT_ESTIMABLE_INSUFFICIENT_PAIRS",
        )
        result = run_predeclared_test(
            _dataset([2.0, 2.0, 2.0, 2.0]),
            declaration,
            fallback_evidence="declared diagnostic evidence",
        )
        assert result.status == TEST_STATUS_NOT_ESTIMABLE
        assert result.reason_code == TEST_REASON_ZERO_DISPERSION
        assert result.fallback_applied is False

    def test_two_sided_is_default(self):
        declaration = predeclare_test(
            preferred_test_family=TEST_PAIRED_T,
            method_freeze_id="FREEZE-1",
            assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T],
        )
        assert declaration.alternative == ALTERNATIVE_TWO_SIDED
        result = run_predeclared_test(
            _dataset(REFERENCE_IMPROVEMENTS), declaration
        )
        assert result.alternative == ALTERNATIVE_TWO_SIDED

    def test_one_sided_requires_declaration_and_is_half_two_sided(self):
        dataset = _dataset(REFERENCE_IMPROVEMENTS)
        two_sided = run_predeclared_test(
            dataset,
            self._declaration(TEST_PAIRED_T, [ASSUMPTION_LICENSE_PAIRED_T]),
        )
        greater = run_predeclared_test(
            dataset,
            self._declaration(
                TEST_PAIRED_T,
                [ASSUMPTION_LICENSE_PAIRED_T],
                alternative=ALTERNATIVE_GREATER,
            ),
        )
        less = run_predeclared_test(
            dataset,
            self._declaration(
                TEST_PAIRED_T,
                [ASSUMPTION_LICENSE_PAIRED_T],
                alternative=ALTERNATIVE_LESS,
            ),
        )
        assert greater.p_value == pytest.approx(0.022220670402149874, abs=1e-12)
        assert two_sided.p_value == pytest.approx(2 * greater.p_value, abs=1e-12)
        assert less.p_value == pytest.approx(1 - greater.p_value, abs=1e-12)

    def test_sign_one_sided_reference(self):
        result = run_predeclared_test(
            _dataset(REFERENCE_IMPROVEMENTS),
            self._declaration(
                TEST_SIGN,
                [ASSUMPTION_LICENSE_SIGN],
                alternative=ALTERNATIVE_GREATER,
            ),
        )
        assert result.p_value == pytest.approx(0.08984375, abs=1e-12)

    def test_wilcoxon_one_sided_reference(self):
        result = run_predeclared_test(
            _dataset(REFERENCE_IMPROVEMENTS),
            self._declaration(
                TEST_WILCOXON,
                [ASSUMPTION_LICENSE_WILCOXON],
                alternative=ALTERNATIVE_GREATER,
            ),
        )
        assert result.p_value == pytest.approx(0.02734375, abs=1e-12)

    def test_all_zero_differences(self):
        sign_result = run_predeclared_test(
            _dataset([0.0, 0.0, 0.0]),
            self._declaration(TEST_SIGN, [ASSUMPTION_LICENSE_SIGN]),
        )
        wilcoxon_result = run_predeclared_test(
            _dataset([0.0, 0.0, 0.0]),
            self._declaration(TEST_WILCOXON, [ASSUMPTION_LICENSE_WILCOXON]),
        )
        assert sign_result.p_value == 1.0
        assert sign_result.zero_differences == 3
        assert wilcoxon_result.p_value == 1.0
        assert wilcoxon_result.zero_differences == 3

    def test_p_value_bounds(self):
        dataset = _dataset(REFERENCE_IMPROVEMENTS)
        for family, license_name in (
            (TEST_PAIRED_T, ASSUMPTION_LICENSE_PAIRED_T),
            (TEST_SIGN, ASSUMPTION_LICENSE_SIGN),
            (TEST_WILCOXON, ASSUMPTION_LICENSE_WILCOXON),
        ):
            result = run_predeclared_test(
                dataset, self._declaration(family, [license_name])
            )
            assert result.p_value is not None
            assert 0.0 <= result.p_value <= 1.0

    def test_result_is_deterministic(self):
        dataset = _dataset(REFERENCE_IMPROVEMENTS)
        declaration = self._declaration(
            TEST_WILCOXON, [ASSUMPTION_LICENSE_WILCOXON]
        )
        assert run_predeclared_test(dataset, declaration) == run_predeclared_test(
            dataset, declaration
        )
