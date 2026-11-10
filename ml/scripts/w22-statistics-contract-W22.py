#!/usr/bin/env python3
"""W22 paired-statistics contract driver (Layer B TEST_ONLY harness).

Generates the W22 software-contract reports and manifest from small,
explicitly labelled synthetic in-memory fixtures.  It computes no physical
Controller A/B result: there is no input path, no campaign export reader, no
outcome-file ingestion, and no ability to bypass the W20 analysis lock.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path

from coldguard_ml.w20_campaign_lock import (
    ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION,
    BUNDLE_SYNTHETIC,
    CAMPAIGN_METADATA_SCHEMA,
    assess_campaign_lock,
)
from coldguard_ml.w22_paired_statistics import (
    CONTROLLER_A,
    CONTROLLER_B,
    DZ_DEFINED,
    LABEL_SYNTHETIC_TEST_ONLY,
    OUTCOME_ROLE_PRIMARY,
    OUTCOME_ROLE_SECONDARY,
    PAIR_ORDER_POLICY,
    QUANTILE_CONVENTION,
    RELATIVE_DEFINED,
    SIGN_CONVENTION,
    W22BoundaryError,
    W22StatisticsError,
    build_paired_dataset,
    describe_pairs,
    paired_effect_size,
    render_every_pair_svg,
)
from coldguard_ml.w22_readiness import (
    LIMITATIONS,
    REQUIRED_FUTURE_CONDITIONS,
    WITHHELD_RESULT_ARTIFACTS,
    assess_real_analysis_readiness,
    build_final_report_template,
    render_final_report_template_markdown,
)
from coldguard_ml.w22_sensitivity import (
    SENSITIVITY_STATUS_EXPLORATORY,
    SENSITIVITY_STATUS_PREDECLARED,
    compare_intervals,
    extreme_pair_influence,
    leave_one_pair_out,
    mean_vs_median,
    refuse_horizon_sensitivity,
    secondary_outcome_contrast,
)
from coldguard_ml.w22_uncertainty import (
    ALTERNATIVE_GREATER,
    ALTERNATIVE_TWO_SIDED,
    ASSUMPTION_LICENSE_PAIRED_T,
    ASSUMPTION_LICENSE_SIGN,
    ASSUMPTION_LICENSE_WILCOXON,
    BOOTSTRAP_DEFAULT_ITERATIONS,
    BOOTSTRAP_MIN_ITERATIONS,
    CLAIM_BOUNDARY,
    INTERVAL_ROLE_PRIMARY,
    INTERVAL_ROLE_SENSITIVITY,
    RNG_IDENTITY,
    STATUS_ESTIMABLE,
    STATUS_NOT_ESTIMABLE,
    TEST_PAIRED_T,
    TEST_REASON_ZERO_DISPERSION,
    TEST_SIGN,
    TEST_STATUS_ESTIMABLE,
    TEST_WILCOXON,
    W22InferenceError,
    assert_single_primary,
    bootstrap_percentile_interval,
    paired_t_interval,
    predeclare_interval_method,
    predeclare_test,
    resolve_primary_interval,
    run_predeclared_test,
    student_t_critical,
)

ML_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ML_ROOT / "reports" / "W22"
TOY_SEED = 20261110
TOY_METHOD_FREEZE_ID = "W22-TOY-METHOD-FREEZE-20261110"
TOY_INTERVAL_FREEZE_ID = "W22-TOY-CI-FREEZE-20261110"
TOY_PLAN_REFERENCE = "W22-TOY-PLAN-v1"
TOY_DENOMINATOR_FLOOR = 5.0

REPORT_NAMES = (
    "paired-statistics-contract-W22.md",
    "uncertainty-and-tests-W22.md",
    "sensitivity-contract-W22.md",
    "scientific-limitations-W22.md",
    "analysis-readiness-W22.md",
)
PLOT_NAME = "test-only-pair-plot-W22.svg"
MANIFEST_NAME = "w22-manifest.json"

PRIOR_ARTIFACTS = {
    "reports/W16/locked-test-manifest-W16.json": "6e7e7f23881785f76463344663e08f0cf626f5ee137aa1f98a99772e1a1fe165",
    "reports/W19/w19-manifest.json": "f3bbae932743b4b71c8e8ed7bbbb5334836353080361aa2746c3950cb989db82",
    "reports/W20/w20-manifest.json": "0d8c2ad1cb846599d3535a74ade65186b388702da59eb4bfb0271dcb5a849ece",
    "reports/W20/analysis-unlock-W20.md": "cea11179f2d58487dbc2cea5bba610c27bd4a84574b7278a3cfcd6ae43b19376",
    "reports/W20/paired-outcome-contract-W20.md": "2768273d029dc3f0894867e85df3de52a44093bb745e86efdbc6077f61cf08c1",
    "reports/W21/w21-manifest.json": "5b78141deca1d3f5fd5e16ac10b3344541261d66b5aaa6e49bb3169758fae2c3",
    "reports/W21/diagnosis-table-W21.md": "c67ada12603c810e5821546f3a3d4ebd6f780d6011f5a9f71f2190d3691477b4",
    "reports/W21/safe-local-summary-W21.md": "053095bef6e55599b45a1b468a145ca72f23acd0b90785cbecb4bb54143cb74d",
    "reports/W21/degraded-sensor-pzem-W21.md": "3cd357c61ebfdb9014116a722f4e004fa547bd9090600061ae347298d0631866",
    "reports/W21/optional-energy-gate-W21.md": "9939b5f0baa02710760551948c1395b35b6418d34c96041218b984223aa17897",
}

W22_SOURCE_FILES = (
    "src/coldguard_ml/w22_paired_statistics.py",
    "src/coldguard_ml/w22_uncertainty.py",
    "src/coldguard_ml/w22_sensitivity.py",
    "src/coldguard_ml/w22_readiness.py",
    "scripts/w22-statistics-contract-W22.py",
)
PURE_STATS_FILES = (
    "src/coldguard_ml/w22_paired_statistics.py",
    "src/coldguard_ml/w22_uncertainty.py",
    "src/coldguard_ml/w22_sensitivity.py",
)
FORBIDDEN_IMPORTS = frozenset(
    {
        "asyncio",
        "csv",
        "http",
        "mqtt",
        "multiprocessing",
        "numpy",
        "paho",
        "pandas",
        "requests",
        "scipy",
        "serial",
        "sklearn",
        "socket",
        "ssl",
        "statsmodels",
        "subprocess",
        "urllib",
        "xgboost",
    }
)
FILE_ACCESS_IMPORTS = frozenset({"csv", "json", "os", "pathlib", "shutil"})

PRIMARY_IMPROVEMENTS = (20.0, 5.0, 5.0, -5.0, 15.0, 12.0, -2.0, 17.0)
SECONDARY_IMPROVEMENTS = (4.0, -1.0, 6.0, 2.0, 0.0, 3.0)
REFERENCE_IMPROVEMENTS = (2.0, 4.5, -1.0, 0.0, 3.5, 7.0, 2.5, -3.0, 1.5, 5.5)
CONSTANT_IMPROVEMENTS = (3.0, 3.0, 3.0, 3.0)
EXTREME_IMPROVEMENTS = (3.0, 3.0, 3.0, 50.0)
SIGN_SELECTION_IMPROVEMENTS = (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -20.0)

REFERENCE = {
    "primary_mean": 8.375,
    "primary_median": 8.5,
    "primary_sd": 9.07016301633312,
    "primary_q1": 3.25,
    "primary_q3": 15.5,
    "reference_mean": 2.25,
    "reference_median": 2.25,
    "reference_sd": 3.0482235263619804,
    "reference_population_sd": 2.891798748184251,
    "reference_q1": 0.375,
    "reference_q3": 4.25,
    "t_critical_df7": 2.364624251592784,
    "t_statistic_primary": 2.611648448555221,
    "t_p_primary": 0.03482970817118022,
    "t_ci_lower_primary": 0.7921539557534638,
    "t_ci_upper_primary": 15.957846044246537,
    "sign_p_primary": 0.2890625,
    "wilcoxon_p_primary": 0.0625,
    "effect_dz_primary": 0.9233571640243616,
    "secondary_mean": 2.3333333333333335,
    "secondary_sd": 2.581988897471611,
}


def _num(value: float | None, places: int = 12) -> str:
    if value is None:
        return "NOT_ESTIMABLE"
    return f"{value:.{places}g}"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dataset(
    improvements,
    *,
    base_a: float,
    unit: str,
    outcome_id: str,
    role: str = OUTCOME_ROLE_PRIMARY,
):
    from coldguard_ml.w22_paired_statistics import PairArm, PairRecord

    records = [
        PairRecord(
            pair_id=f"P-{index:02d}",
            pair_block_id=f"BLOCK-{index:02d}",
            arm_a=PairArm(f"TOY-S2-A-{index:03d}", CONTROLLER_A, base_a, unit),
            arm_b=PairArm(
                f"TOY-S2-B-{index:03d}", CONTROLLER_B, base_a - value, unit
            ),
            outcome_id=outcome_id,
            outcome_role=role,
            session_id="TOY-SESSION-W22",
            rig_id="CG-HW-001",
        )
        for index, value in enumerate(improvements, 1)
    ]
    return build_paired_dataset(
        records, outcome_id=outcome_id, unit=unit, outcome_role=role
    )


def fixture_primary():
    return _dataset(
        PRIMARY_IMPROVEMENTS,
        base_a=120.0,
        unit="°C·s",
        outcome_id="thermal_exposure",
    )


def fixture_secondary():
    return _dataset(
        SECONDARY_IMPROVEMENTS,
        base_a=60.0,
        unit="s",
        outcome_id="recovery_time",
        role=OUTCOME_ROLE_SECONDARY,
    )


def fixture_reference():
    return _dataset(
        REFERENCE_IMPROVEMENTS,
        base_a=100.0,
        unit="°C·s",
        outcome_id="thermal_exposure",
    )


def fixture_constant():
    return _dataset(
        CONSTANT_IMPROVEMENTS,
        base_a=100.0,
        unit="°C·s",
        outcome_id="thermal_exposure",
    )


def fixture_extreme():
    return _dataset(
        EXTREME_IMPROVEMENTS,
        base_a=100.0,
        unit="°C·s",
        outcome_id="thermal_exposure",
    )


def _toy_campaign_bundle(*, fake_authorization: bool = False) -> dict:
    bundle = {
        "schema": CAMPAIGN_METADATA_SCHEMA,
        "campaign_id": "W22-TOY-METADATA-ONLY",
        "evidence_class": BUNDLE_SYNTHETIC,
        "fixture_markers": ["W22_TEST_ONLY_NOT_A_PHYSICAL_CAMPAIGN"],
    }
    if fake_authorization:
        bundle["analysis_execution_authorization"] = {
            "status": "ISSUED",
            "authority_id": "TOY-FAKE-AUTHORITY",
            "authority_role": "TEAM_LEAD",
            "canonical_ref": "TOY-NOT-REAL",
            "campaign_id": "W22-TOY-METADATA-ONLY",
            "verification_status": "NOT_VERIFIED_EXTERNALLY",
            "verification_binding": "EMBEDDED_CANONICAL_BYTES",
        }
    return bundle


def _toy_readiness(*, fake_authorization: bool = False):
    bundle = _toy_campaign_bundle(fake_authorization=fake_authorization)
    assessment = assess_campaign_lock(bundle)
    return assessment, assess_real_analysis_readiness(bundle)


def _expect_refusal(callable_, exception_type, reason_code: str | None = None):
    try:
        callable_()
    except exception_type as exc:
        if reason_code is not None:
            assert getattr(exc, "reason_code", None) == reason_code, str(exc)
        return exc
    raise AssertionError("expected a refusal, but the call returned")


def _check(name: str, expected: float, observed: float, tolerance: float) -> dict:
    passed = math.isclose(expected, observed, rel_tol=0.0, abs_tol=tolerance)
    return {
        "name": name,
        "expected": expected,
        "observed": observed,
        "tolerance": tolerance,
        "passed": passed,
    }


def _reference_checks() -> list[dict]:
    primary = describe_pairs(fixture_primary())
    reference = describe_pairs(fixture_reference())
    secondary = describe_pairs(fixture_secondary())
    interval = paired_t_interval(fixture_primary())
    test = run_predeclared_test(
        fixture_primary(),
        predeclare_test(
            preferred_test_family=TEST_PAIRED_T,
            method_freeze_id=TOY_METHOD_FREEZE_ID,
            assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T],
        ),
    )
    sign = run_predeclared_test(
        fixture_primary(),
        predeclare_test(
            preferred_test_family=TEST_SIGN,
            method_freeze_id=TOY_METHOD_FREEZE_ID,
            assumption_licenses=[ASSUMPTION_LICENSE_SIGN],
        ),
    )
    wilcoxon = run_predeclared_test(
        fixture_primary(),
        predeclare_test(
            preferred_test_family=TEST_WILCOXON,
            method_freeze_id=TOY_METHOD_FREEZE_ID,
            assumption_licenses=[ASSUMPTION_LICENSE_WILCOXON],
        ),
    )
    effect = paired_effect_size(fixture_primary(), denominator_floor=TOY_DENOMINATOR_FLOOR)
    checks = [
        _check("primary_mean", REFERENCE["primary_mean"], primary.mean_improvement, 1e-12),
        _check("primary_median", REFERENCE["primary_median"], primary.median_improvement, 1e-12),
        _check("primary_sample_sd", REFERENCE["primary_sd"], primary.sample_standard_deviation, 1e-12),
        _check("primary_q1", REFERENCE["primary_q1"], primary.q1, 1e-12),
        _check("primary_q3", REFERENCE["primary_q3"], primary.q3, 1e-12),
        _check("reference_mean", REFERENCE["reference_mean"], reference.mean_improvement, 1e-12),
        _check("reference_median", REFERENCE["reference_median"], reference.median_improvement, 1e-12),
        _check("reference_sample_sd", REFERENCE["reference_sd"], reference.sample_standard_deviation, 1e-12),
        _check("reference_population_sd", REFERENCE["reference_population_sd"], reference.population_standard_deviation, 1e-12),
        _check("reference_q1", REFERENCE["reference_q1"], reference.q1, 1e-12),
        _check("reference_q3", REFERENCE["reference_q3"], reference.q3, 1e-12),
        _check("t_critical_df7", REFERENCE["t_critical_df7"], student_t_critical(0.975, 7), 1e-9),
        _check("t_statistic_primary", REFERENCE["t_statistic_primary"], test.statistic, 1e-12),
        _check("t_p_primary", REFERENCE["t_p_primary"], test.p_value, 1e-12),
        _check("t_ci_lower_primary", REFERENCE["t_ci_lower_primary"], interval.lower, 1e-11),
        _check("t_ci_upper_primary", REFERENCE["t_ci_upper_primary"], interval.upper, 1e-11),
        _check("sign_p_primary", REFERENCE["sign_p_primary"], sign.p_value, 1e-12),
        _check("wilcoxon_p_primary", REFERENCE["wilcoxon_p_primary"], wilcoxon.p_value, 1e-12),
        _check("effect_dz_primary", REFERENCE["effect_dz_primary"], effect.standardized_dz, 1e-12),
        _check("secondary_mean", REFERENCE["secondary_mean"], secondary.mean_improvement, 1e-12),
        _check("secondary_sample_sd", REFERENCE["secondary_sd"], secondary.sample_standard_deviation, 1e-12),
    ]
    for check in checks:
        assert check["passed"], check
    return checks


def _probe(name: str, expectation: str, check) -> dict:
    try:
        check()
        passed = True
    except Exception:
        passed = False
    return {"name": name, "expectation": expectation, "passed": passed}


def _adversarial_controls() -> list[dict]:
    primary = fixture_primary()
    primary_description = describe_pairs(primary)
    probes: list[dict] = []

    def valid_pair_admitted():
        dataset = _dataset((2.0, 3.0), base_a=10.0, unit="s", outcome_id="recovery_time")
        assert dataset.pair_count == 2
        assert all(
            pair.arm_a.controller == CONTROLLER_A
            and pair.arm_b.controller == CONTROLLER_B
            for pair in dataset.pairs
        )

    def two_a_arms_refused():
        from coldguard_ml.w22_paired_statistics import PairArm, PairRecord

        record = PairRecord(
            pair_id="P-X",
            pair_block_id="BLOCK-X",
            arm_a=PairArm("RUN-A", CONTROLLER_A, 10.0, "s"),
            arm_b=PairArm("RUN-B", CONTROLLER_A, 9.0, "s"),
            outcome_id="recovery_time",
        )
        _expect_refusal(
            lambda: build_paired_dataset(
                [record], outcome_id="recovery_time", unit="s"
            ),
            W22StatisticsError,
            "ARM_CONTROLLER_LABEL_INVALID",
        )

    def duplicate_pair_id_refused():
        from coldguard_ml.w22_paired_statistics import PairArm, PairRecord

        records = [
            PairRecord("P-X", "BLOCK-1", PairArm("RUN-A1", "A", 10.0, "s"), PairArm("RUN-B1", "B", 9.0, "s"), "recovery_time"),
            PairRecord("P-X", "BLOCK-2", PairArm("RUN-A2", "A", 10.0, "s"), PairArm("RUN-B2", "B", 9.0, "s"), "recovery_time"),
        ]
        _expect_refusal(
            lambda: build_paired_dataset(records, outcome_id="recovery_time", unit="s"),
            W22StatisticsError,
            "DUPLICATE_PAIR_ID",
        )

    def run_reused_refused():
        from coldguard_ml.w22_paired_statistics import PairArm, PairRecord

        records = [
            PairRecord("P-01", "BLOCK-1", PairArm("RUN-SHARED", "A", 10.0, "s"), PairArm("RUN-B1", "B", 9.0, "s"), "recovery_time"),
            PairRecord("P-02", "BLOCK-2", PairArm("RUN-SHARED", "A", 10.0, "s"), PairArm("RUN-B2", "B", 9.0, "s"), "recovery_time"),
        ]
        _expect_refusal(
            lambda: build_paired_dataset(records, outcome_id="recovery_time", unit="s"),
            W22StatisticsError,
            "RUN_ID_REUSED_ACROSS_PAIRS",
        )

    def arm_order_reversed_refused():
        from coldguard_ml.w22_paired_statistics import PairArm, PairRecord

        record = PairRecord(
            "P-X", "BLOCK-X",
            PairArm("RUN-B", CONTROLLER_B, 9.0, "s"),
            PairArm("RUN-A", CONTROLLER_A, 10.0, "s"),
            "recovery_time",
        )
        _expect_refusal(
            lambda: build_paired_dataset([record], outcome_id="recovery_time", unit="s"),
            W22StatisticsError,
            "ARM_CONTROLLER_LABEL_INVALID",
        )

    def telemetry_windows_not_pairs():
        from coldguard_ml.w22_paired_statistics import PairArm, PairRecord

        records = [
            PairRecord(
                f"P-{index:02d}", f"BLOCK-{index:02d}",
                PairArm("RUN-A-001", "A", 10.0, "s"),
                PairArm("RUN-B-001", "B", 9.0, "s"),
                "recovery_time",
            )
            for index in range(1, 6)
        ]
        _expect_refusal(
            lambda: build_paired_dataset(records, outcome_id="recovery_time", unit="s"),
            W22StatisticsError,
            "RUN_ID_REUSED_ACROSS_PAIRS",
        )

    def arm_wise_bootstrap_refused():
        base = _dataset((1.0, -1.0, 2.0, -2.0), base_a=10.0, unit="s", outcome_id="recovery_time")
        shifted = _dataset((1.0, -1.0, 2.0, -2.0), base_a=1000.0, unit="s", outcome_id="recovery_time")
        first = bootstrap_percentile_interval(base, seed=11, iterations=300, test_only_settings=True)
        second = bootstrap_percentile_interval(shifted, seed=11, iterations=300, test_only_settings=True)
        assert first.draw_digest == second.draw_digest
        assert first.resampling_unit == "COMPLETE_MATCHED_PAIRS"

    def invalid_pair_silently_included_refused():
        from coldguard_ml.w22_paired_statistics import PairArm, PairRecord

        record = PairRecord(
            "P-X", "BLOCK-X",
            PairArm("RUN-A", "A", math.nan, "s"),
            PairArm("RUN-B", "B", 9.0, "s"),
            "recovery_time",
        )
        _expect_refusal(
            lambda: build_paired_dataset([record], outcome_id="recovery_time", unit="s"),
            W22StatisticsError,
            "NON_FINITE_OUTCOME_VALUE",
        )

    def rerun_extra_pair_refused():
        from coldguard_ml.w22_paired_statistics import PairArm, PairRecord

        records = [
            PairRecord("P-01", "BLOCK-7", PairArm("RUN-A-1", "A", 10.0, "s"), PairArm("RUN-B-1", "B", 9.0, "s"), "recovery_time"),
            PairRecord("P-01-RERUN", "BLOCK-7", PairArm("RUN-A-2", "A", 10.0, "s"), PairArm("RUN-B-2", "B", 9.5, "s"), "recovery_time"),
        ]
        _expect_refusal(
            lambda: build_paired_dataset(records, outcome_id="recovery_time", unit="s"),
            W22StatisticsError,
            "DUPLICATE_PAIR_BLOCK",
        )

    def unknown_value_not_zero():
        from coldguard_ml.w22_paired_statistics import PairArm, PairRecord

        record = PairRecord(
            "P-X", "BLOCK-X",
            PairArm("RUN-A", "A", 10.0, "s"),
            PairArm("RUN-B", "B", None, "s"),
            "recovery_time",
        )
        _expect_refusal(
            lambda: build_paired_dataset([record], outcome_id="recovery_time", unit="s"),
            W22StatisticsError,
            "MISSING_OUTCOME_VALUE",
        )

    def known_descriptives():
        assert primary_description.mean_improvement == REFERENCE["primary_mean"]
        assert primary_description.sample_standard_deviation == REFERENCE["primary_sd"]

    def sample_sd_denominator():
        reference = describe_pairs(fixture_reference())
        assert reference.sample_standard_deviation == REFERENCE["reference_sd"]
        assert reference.population_standard_deviation == REFERENCE["reference_population_sd"]
        assert reference.sample_standard_deviation > reference.population_standard_deviation

    def quantile_type7_pinned():
        reference = describe_pairs(fixture_reference())
        assert (reference.q1, reference.q3) == (0.375, 4.25)

    def negative_improvement_not_beneficial():
        negative = describe_pairs(
            _dataset((-2.0, -3.0, -4.0), base_a=10.0, unit="s", outcome_id="recovery_time")
        )
        assert negative.direction == "CONTROLLER_B_WORSENED"

    def constant_differences_refused_inference():
        interval = paired_t_interval(fixture_constant())
        assert interval.status == STATUS_NOT_ESTIMABLE
        assert interval.reason_code == "CI_NOT_ESTIMABLE_ZERO_DISPERSION"
        test = run_predeclared_test(
            fixture_constant(),
            predeclare_test(
                preferred_test_family=TEST_PAIRED_T,
                method_freeze_id=TOY_METHOD_FREEZE_ID,
                assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T],
            ),
        )
        assert test.status == "NOT_ESTIMABLE"

    def nan_inf_refused():
        from coldguard_ml.w22_paired_statistics import PairArm, PairRecord

        record = PairRecord(
            "P-X", "BLOCK-X",
            PairArm("RUN-A", "A", 10.0, "s"),
            PairArm("RUN-B", "B", math.inf, "s"),
            "recovery_time",
        )
        _expect_refusal(
            lambda: build_paired_dataset([record], outcome_id="recovery_time", unit="s"),
            W22StatisticsError,
            "NON_FINITE_OUTCOME_VALUE",
        )

    def unit_mismatch_refused():
        from coldguard_ml.w22_paired_statistics import PairArm, PairRecord

        record = PairRecord(
            "P-X", "BLOCK-X",
            PairArm("RUN-A", "A", 10.0, "s"),
            PairArm("RUN-B", "B", 9.0, "°C·s"),
            "recovery_time",
        )
        _expect_refusal(
            lambda: build_paired_dataset([record], outcome_id="recovery_time", unit="s"),
            W22StatisticsError,
            "UNIT_MISMATCH_BETWEEN_ARMS_OR_DATASET",
        )

    def every_pair_plot_complete():
        svg = render_every_pair_svg(primary)
        assert all(pair_id in svg for pair_id in primary.pair_ids)
        assert "TEST_ONLY" in svg

    def student_t_not_196():
        assert student_t_critical(0.975, 4) > 1.96
        interval = paired_t_interval(primary)
        assert interval.critical_value > 1.96

    def degrees_of_freedom():
        interval = paired_t_interval(primary)
        assert interval.degrees_of_freedom == primary.pair_count - 1

    def row_window_bootstrap_refused():
        telemetry_windows_not_pairs()

    def pair_level_bootstrap_preserves_pairing():
        base = _dataset((1.0, -1.0, 2.0, -2.0), base_a=10.0, unit="s", outcome_id="recovery_time")
        shifted = _dataset((1.0, -1.0, 2.0, -2.0), base_a=500.0, unit="s", outcome_id="recovery_time")
        first = bootstrap_percentile_interval(base, seed=3, iterations=250, test_only_settings=True)
        second = bootstrap_percentile_interval(shifted, seed=3, iterations=250, test_only_settings=True)
        assert (first.lower, first.upper, first.draw_digest) == (
            second.lower, second.upper, second.draw_digest
        )

    def unseeded_bootstrap_refused():
        estimate = bootstrap_percentile_interval(primary, seed=None)
        assert estimate.reason_code == "BOOTSTRAP_SEED_REQUIRED"

    def iteration_policy_enforced():
        refused = bootstrap_percentile_interval(
            primary, seed=TOY_SEED, iterations=BOOTSTRAP_MIN_ITERATIONS - 1
        )
        accepted = bootstrap_percentile_interval(
            primary, seed=TOY_SEED, iterations=BOOTSTRAP_MIN_ITERATIONS
        )
        assert refused.reason_code == "BOOTSTRAP_ITERATIONS_BELOW_FROZEN_MINIMUM"
        assert accepted.status == STATUS_ESTIMABLE and accepted.research_grade

    def bootstrap_collapse_not_reliability():
        estimate = bootstrap_percentile_interval(fixture_constant(), seed=TOY_SEED)
        assert estimate.status == STATUS_NOT_ESTIMABLE
        assert estimate.lower is None and estimate.upper is None

    def n_below_minimum_refused():
        dataset = _dataset((4.0,), base_a=100.0, unit="°C·s", outcome_id="thermal_exposure")
        interval = paired_t_interval(dataset)
        assert interval.reason_code == "CI_NOT_ESTIMABLE_INSUFFICIENT_PAIRS"

    def two_primary_cis_refused():
        first = paired_t_interval(primary, role=INTERVAL_ROLE_PRIMARY)
        second = bootstrap_percentile_interval(
            primary, seed=TOY_SEED, iterations=500, role=INTERVAL_ROLE_PRIMARY
        )
        _expect_refusal(
            lambda: assert_single_primary([first, second]),
            W22InferenceError,
            "MULTIPLE_PRIMARY_INTERVALS_REFUSED",
        )

    def favorable_ci_not_selected():
        first = paired_t_interval(primary, role=INTERVAL_ROLE_PRIMARY)
        second = bootstrap_percentile_interval(
            primary, seed=TOY_SEED, iterations=500,
            role=INTERVAL_ROLE_SENSITIVITY, test_only_settings=True,
        )
        declaration = predeclare_interval_method(
            primary_method="PAIRED_T_95_CI",
            method_freeze_id=TOY_INTERVAL_FREEZE_ID,
        )
        chosen = resolve_primary_interval(
            primary=first, sensitivity=second, declaration=declaration
        )
        assert chosen.method == "PAIRED_T_95_CI"
        assert chosen.role == INTERVAL_ROLE_PRIMARY

    def paired_not_independent_test():
        from coldguard_ml.w22_paired_statistics import PairArm, PairRecord

        values_a = (10.0, 12.0, 14.0, 16.0)
        values_b = (9.0, 11.0, 12.0, 15.0)
        records = [
            PairRecord(
                f"P-{index:02d}", f"BLOCK-{index:02d}",
                PairArm(f"RUN-A-{index}", "A", value_a, "s"),
                PairArm(f"RUN-B-{index}", "B", value_b, "s"),
                "recovery_time",
            )
            for index, (value_a, value_b) in enumerate(zip(values_a, values_b), 1)
        ]
        dataset = build_paired_dataset(records, outcome_id="recovery_time", unit="s")
        result = run_predeclared_test(
            dataset,
            predeclare_test(
                preferred_test_family=TEST_PAIRED_T,
                method_freeze_id=TOY_METHOD_FREEZE_ID,
                assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T],
            ),
        )
        assert abs(result.p_value - 0.015392438073302294) < 1e-12
        assert abs(result.p_value - 0.5127016478725178) > 1e-3

    def no_smallest_p_selection():
        dataset = _dataset(
            SIGN_SELECTION_IMPROVEMENTS,
            base_a=50.0,
            unit="°C·s",
            outcome_id="thermal_exposure",
        )
        declaration = predeclare_test(
            preferred_test_family=TEST_PAIRED_T,
            method_freeze_id=TOY_METHOD_FREEZE_ID,
            assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T],
        )
        chosen = run_predeclared_test(dataset, declaration)
        sign = run_predeclared_test(
            dataset,
            predeclare_test(
                preferred_test_family=TEST_SIGN,
                method_freeze_id=TOY_METHOD_FREEZE_ID,
                assumption_licenses=[ASSUMPTION_LICENSE_SIGN],
            ),
        )
        assert chosen.family == TEST_PAIRED_T
        assert sign.p_value < chosen.p_value

    def wilcoxon_license_required():
        result = run_predeclared_test(
            primary,
            predeclare_test(
                preferred_test_family=TEST_WILCOXON,
                method_freeze_id=TOY_METHOD_FREEZE_ID,
                assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T],
            ),
        )
        assert result.reason_code == "ASSUMPTION_LICENSE_MISSING"

    def zero_tie_handling():
        dataset = _dataset(
            (1.0, -2.0, 3.0, -4.0, 5.0, 0.0, 2.0, -2.0, 6.0, -7.0, 8.0, 1.0),
            base_a=50.0,
            unit="°C·s",
            outcome_id="thermal_exposure",
        )
        result = run_predeclared_test(
            dataset,
            predeclare_test(
                preferred_test_family=TEST_WILCOXON,
                method_freeze_id=TOY_METHOD_FREEZE_ID,
                assumption_licenses=[ASSUMPTION_LICENSE_WILCOXON],
            ),
        )
        assert result.non_zero_pairs == 11
        assert result.zero_differences == 1
        assert result.p_value == 0.5078125

    def two_sided_default():
        declaration = predeclare_test(
            preferred_test_family=TEST_PAIRED_T,
            method_freeze_id=TOY_METHOD_FREEZE_ID,
            assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T],
        )
        assert declaration.alternative == ALTERNATIVE_TWO_SIDED
        assert (
            run_predeclared_test(primary, declaration).alternative
            == ALTERNATIVE_TWO_SIDED
        )

    def paired_sd_effect_not_pooled():
        dataset = _dataset(
            (1.0, 2.0, 3.0, 4.0), base_a=100.0, unit="°C·s", outcome_id="thermal_exposure"
        )
        effect = paired_effect_size(dataset)
        paired_sd = describe_pairs(dataset).sample_standard_deviation
        assert abs(effect.standardized_dz - 2.5 / paired_sd) < 1e-12
        pooled = math.sqrt(
            (
                math.fsum((value - 100.0) ** 2 for value in dataset.y_a) / 3
                + math.fsum((value - 97.5) ** 2 for value in dataset.y_b) / 3
            )
            / 2.0
        )
        assert abs(effect.standardized_dz - 2.5 / pooled) > 1e-6

    def zero_sd_effect_not_infinite():
        effect = paired_effect_size(fixture_constant())
        assert effect.standardized_dz is None
        assert effect.standardized_status == "UNDEFINED_ZERO_SD"

    def relative_denominator_guard():
        no_floor = paired_effect_size(primary)
        assert no_floor.relative_status == "UNDEFINED_DENOMINATOR_FLOOR_NOT_DECLARED"
        refused = paired_effect_size(primary, denominator_floor=120.0)
        assert refused.relative_status == "UNDEFINED_DENOMINATOR_NOT_MEANINGFUL"
        defined = paired_effect_size(primary, denominator_floor=TOY_DENOMINATOR_FLOOR)
        assert defined.relative_status == RELATIVE_DEFINED
        assert defined.relative_improvement is not None

    def significance_not_usefulness():
        result = run_predeclared_test(
            primary,
            predeclare_test(
                preferred_test_family=TEST_PAIRED_T,
                method_freeze_id=TOY_METHOD_FREEZE_ID,
                assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T],
            ),
        )
        assert result.claim_boundary == CLAIM_BOUNDARY

    def extreme_pair_retained_primary():
        dataset = fixture_extreme()
        before = describe_pairs(dataset)
        extreme_pair_influence(dataset, before)
        after = describe_pairs(dataset)
        assert before == after
        assert after.pair_count == 4

    def loo_not_primary():
        results = leave_one_pair_out(
            primary,
            primary_description,
            declared_status=SENSITIVITY_STATUS_EXPLORATORY,
        )
        assert all(item.label == "SENSITIVITY_ONLY_NOT_PRIMARY" for item in results)
        assert all(item.promotion_allowed is False for item in results)

    def primary_n_unchanged():
        before = describe_pairs(primary)
        leave_one_pair_out(primary, before)
        mean_vs_median(primary, before)
        extreme_pair_influence(primary, before)
        after = describe_pairs(primary)
        assert before == after
        assert after.pair_count == len(PRIMARY_IMPROVEMENTS)

    def secondary_not_promoted():
        result = secondary_outcome_contrast(fixture_primary(), fixture_secondary())
        assert result.label == "SECONDARY_OUTCOME_NOT_PRIMARY"
        assert result.promotion_allowed is False

    def posthoc_not_preregistered():
        _expect_refusal(
            lambda: mean_vs_median(
                primary,
                primary_description,
                declared_status=SENSITIVITY_STATUS_PREDECLARED,
            ),
            W22StatisticsError,
            "PREDECLARED_SENSITIVITY_REQUIRES_PLAN_REFERENCE",
        )

    def horizon_shopping_refused():
        _expect_refusal(
            refuse_horizon_sensitivity,
            W22BoundaryError,
            "HORIZON_SENSITIVITY_REQUIRES_FROZEN_MODEL_EVIDENCE",
        )

    def synthetic_not_physical():
        assert primary.evidence_label == LABEL_SYNTHETIC_TEST_ONLY
        svg = render_every_pair_svg(primary)
        assert LABEL_SYNTHETIC_TEST_ONLY in svg
        assert "not a ColdGuard physical A/B result" in svg

    def closed_loop_ewt_refused():
        names = _function_names(
            (
                "src/coldguard_ml/w22_paired_statistics.py",
                "src/coldguard_ml/w22_uncertainty.py",
                "src/coldguard_ml/w22_sensitivity.py",
                "src/coldguard_ml/w22_readiness.py",
            )
        )
        assert not any("ewt" in name.lower() for name in names)
        template = build_final_report_template()
        assert "naive counterfactual EWT" in template["ewt_causal_boundary"]

    def one_rig_not_multiple_sites():
        assert primary_description.rig_count == 1
        assert primary_description.multi_site_claim_supported is False

    def w20_blocked_not_authorized():
        assessment, readiness = _toy_readiness()
        assert assessment.gate_decision != ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION
        assert readiness.physical_analysis == "NOT_AUTHORIZED"
        assert readiness.real_paired_statistics == "NOT_COMPUTED"
        assert assessment.outcome_access is False

    def w16_holdout_not_opened():
        manifest = _read_json(ML_ROOT / "reports" / "W21" / "w21-manifest.json")
        assert manifest["scientific_integrity"]["W16_HOLDOUT"] == "NOT_OPENED"
        for relative in (
            "src/coldguard_ml/w22_paired_statistics.py",
            "src/coldguard_ml/w22_uncertainty.py",
            "src/coldguard_ml/w22_sensitivity.py",
            "src/coldguard_ml/w22_readiness.py",
        ):
            text = (ML_ROOT / relative).read_text(encoding="utf-8")
            assert "W16" not in text
            assert "locked-test" not in text

    def fixture_not_physical_campaign():
        _expect_refusal(
            lambda: build_paired_dataset(
                [], outcome_id="thermal_exposure", unit="°C·s",
                evidence_label="PHYSICAL_CAMPAIGN_RECORD",
            ),
            W22BoundaryError,
            "REAL_OUTCOME_BRIDGE_NOT_IMPLEMENTED",
        )

    def fake_approval_refused():
        assessment, readiness = _toy_readiness(fake_authorization=True)
        assert "ANALYSIS_AUTHORIZATION_NOT_VERIFIED_EXTERNALLY" in assessment.refusal_reasons
        assert assessment.gate_decision != ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION
        assert readiness.physical_analysis == "NOT_AUTHORIZED"

    def cli_lock_bypass_refused():
        parser = build_parser()
        for flag in ("--force", "--unlock", "--ignore-lock", "--input"):
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    parser.parse_args([flag])
            except SystemExit:
                continue
            raise AssertionError(f"{flag} was accepted")
        assert build_parser().parse_args([]).out.name == "W22"

    def no_outcome_csv_artifact():
        parser = build_parser()
        options = [
            option
            for action in parser._actions
            for option in action.option_strings
        ]
        assert set(options) <= {"-h", "--help", "--out"}
        assert "--out" in options
        assert all("csv" not in option.lower() for option in options)

    def no_real_p_value():
        results = [
            run_predeclared_test(
                primary,
                predeclare_test(
                    preferred_test_family=family,
                    method_freeze_id=TOY_METHOD_FREEZE_ID,
                    assumption_licenses=[license_name],
                ),
            )
            for family, license_name in (
                (TEST_PAIRED_T, ASSUMPTION_LICENSE_PAIRED_T),
                (TEST_SIGN, ASSUMPTION_LICENSE_SIGN),
                (TEST_WILCOXON, ASSUMPTION_LICENSE_WILCOXON),
            )
        ]
        for result in results:
            assert result.evidence_label == LABEL_SYNTHETIC_TEST_ONLY
            assert all(pair_id.startswith("P-") for pair_id in primary.pair_ids)

    def g4_g5_not_promoted():
        w20 = _read_json(ML_ROOT / "reports" / "W20" / "w20-manifest.json")
        w21 = _read_json(ML_ROOT / "reports" / "W21" / "w21-manifest.json")
        assert w20["verdicts"]["G4"] == "NOT_READY"
        assert w20["verdicts"]["G5"] == "NOT_ESTABLISHED"
        assert w21["scientific_integrity"]["G4"] == "NOT_READY"
        assert w21["scientific_integrity"]["G5"] == "NOT_ESTABLISHED"

    def model_not_retuned():
        imports = _imports()
        assert not (imports & {"sklearn", "xgboost", "scipy", "statsmodels"})

    def prior_reports_unmodified():
        for relative, expected in PRIOR_ARTIFACTS.items():
            observed = _sha256_bytes((ML_ROOT / relative).read_bytes())
            assert observed == expected, relative

    probes.extend(
        [
            _probe("valid_pair_admitted", "a valid labelled A/B pair enters statistics", valid_pair_admitted),
            _probe("two_a_arms_refused", "two Controller A arms cannot form a pair", two_a_arms_refused),
            _probe("duplicate_pair_id_refused", "duplicate pair IDs are refused", duplicate_pair_id_refused),
            _probe("run_reused_across_pairs_refused", "one run cannot contribute twice", run_reused_refused),
            _probe("arm_order_reversed_refused", "reversed arm order is refused, not sign-flipped silently", arm_order_reversed_refused),
            _probe("telemetry_windows_not_pairs", "duplicate run identities cannot inflate independent N; provenance collapse is a W19-bound intake duty", telemetry_windows_not_pairs),
            _probe("arm_wise_bootstrap_refused", "bootstrap depends on paired differences, not arm values", arm_wise_bootstrap_refused),
            _probe("invalid_pair_silently_included_refused", "non-finite pair is refused", invalid_pair_silently_included_refused),
            _probe("rerun_extra_pair_refused", "a rerun in the same pair block is not an extra pair", rerun_extra_pair_refused),
            _probe("unknown_value_not_zero", "a missing value is never coerced to zero", unknown_value_not_zero),
            _probe("known_descriptives", "descriptives match independent references", known_descriptives),
            _probe("sample_sd_denominator", "sample and population SD are distinct", sample_sd_denominator),
            _probe("quantile_type7_pinned", "IQR uses the frozen type-7 quantile", quantile_type7_pinned),
            _probe("negative_improvement_not_beneficial", "negative improvement reads as worsened", negative_improvement_not_beneficial),
            _probe("constant_differences_refused_inference", "constant differences do not yield certainty", constant_differences_refused_inference),
            _probe("nan_inf_refused", "NaN and infinity are refused", nan_inf_refused),
            _probe("unit_mismatch_refused", "different units cannot be paired", unit_mismatch_refused),
            _probe("every_pair_plot_complete", "the plot contains every pair", every_pair_plot_complete),
            _probe("student_t_not_196", "small-N CI uses the Student-t critical value", student_t_not_196),
            _probe("degrees_of_freedom_n_minus_1", "CI uses df = n - 1", degrees_of_freedom),
            _probe("row_window_bootstrap_refused", "row/window bootstrap input is refused", row_window_bootstrap_refused),
            _probe("pair_level_bootstrap_preserves_pairing", "pair resampling preserves A/B pairing", pair_level_bootstrap_preserves_pairing),
            _probe("unseeded_bootstrap_refused", "an unseeded bootstrap is refused", unseeded_bootstrap_refused),
            _probe("iteration_policy_enforced", "bootstrap iteration policy is enforced", iteration_policy_enforced),
            _probe("bootstrap_collapse_not_reliability", "bootstrap collapse is not reliable uncertainty", bootstrap_collapse_not_reliability),
            _probe("n_below_minimum_refused", "N below the inferential minimum is refused", n_below_minimum_refused),
            _probe("two_primary_cis_refused", "two primary intervals are refused", two_primary_cis_refused),
            _probe("favorable_ci_not_selected", "the predeclared primary CI is returned", favorable_ci_not_selected),
            _probe("paired_not_independent_test", "the paired test is not a two-sample test", paired_not_independent_test),
            _probe("no_smallest_p_selection", "the declared family is used even when another p is smaller", no_smallest_p_selection),
            _probe("wilcoxon_license_required", "Wilcoxon requires its assumption license", wilcoxon_license_required),
            _probe("zero_tie_handling", "zero differences and ties are handled explicitly", zero_tie_handling),
            _probe("two_sided_default", "two-sided testing is the default", two_sided_default),
            _probe("paired_sd_effect_not_pooled", "d_z uses paired-difference SD", paired_sd_effect_not_pooled),
            _probe("zero_sd_effect_not_infinite", "zero SD yields an undefined effect", zero_sd_effect_not_infinite),
            _probe("relative_denominator_guard", "relative improvement needs a meaningful denominator", relative_denominator_guard),
            _probe("significance_not_usefulness", "a test statistic carries no usefulness claim", significance_not_usefulness),
            _probe("extreme_pair_retained_primary", "a valid extreme pair stays in the primary", extreme_pair_retained_primary),
            _probe("loo_not_primary", "leave-one-out stays sensitivity-only", loo_not_primary),
            _probe("primary_n_unchanged", "sensitivity never changes primary N", primary_n_unchanged),
            _probe("secondary_not_promoted", "a secondary outcome is never promoted", secondary_not_promoted),
            _probe("posthoc_not_preregistered", "a post-hoc check cannot be marked predeclared", posthoc_not_preregistered),
            _probe("horizon_shopping_refused", "prediction-horizon shopping is refused", horizon_shopping_refused),
            _probe("synthetic_not_physical", "toy statistics remain synthetic evidence", synthetic_not_physical),
            _probe("closed_loop_ewt_refused", "no naive closed-loop EWT is produced", closed_loop_ewt_refused),
            _probe("one_rig_not_multiple_sites", "one rig is not multiple independent sites", one_rig_not_multiple_sites),
            _probe("w20_blocked_not_authorized", "a blocked W20 gate refuses real analysis", w20_blocked_not_authorized),
            _probe("w16_holdout_not_opened", "the W16 holdout stays unopened", w16_holdout_not_opened),
            _probe("fixture_not_physical_campaign", "a toy fixture cannot be relabelled physical", fixture_not_physical_campaign),
            _probe("fake_approval_refused", "a fake approval cannot unlock analysis", fake_approval_refused),
            _probe("cli_lock_bypass_refused", "the CLI has no lock-bypass flag", cli_lock_bypass_refused),
            _probe("no_outcome_csv_artifact", "no outcome CSV is accepted or produced", no_outcome_csv_artifact),
            _probe("no_real_p_value", "no real physical p-value is computed", no_real_p_value),
            _probe("g4_g5_not_promoted", "G4/G5 are not promoted by toy tests", g4_g5_not_promoted),
            _probe("model_not_retuned", "W22 contains no model retuning", model_not_retuned),
            _probe("prior_reports_unmodified", "W16/W19/W20/W21 artifacts are unchanged", prior_reports_unmodified),
        ]
    )
    return probes


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _imports() -> set[str]:
    modules: set[str] = set()
    for relative in W22_SOURCE_FILES:
        tree = ast.parse((ML_ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module.split(".")[0])
    return modules


def _function_names(
    files: tuple[str, ...] = W22_SOURCE_FILES,
) -> tuple[str, ...]:
    names: list[str] = []
    for relative in files:
        tree = ast.parse((ML_ROOT / relative).read_text(encoding="utf-8"))
        names.extend(
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        )
    return tuple(names)


def _capability_audit() -> dict:
    imports = sorted(_imports())
    forbidden = sorted(set(imports) & FORBIDDEN_IMPORTS)
    pure_file_imports: list[str] = []
    for relative in PURE_STATS_FILES:
        tree = ast.parse((ML_ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                pure_file_imports.extend(
                    alias.name.split(".")[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                pure_file_imports.append(node.module.split(".")[0])
    pure_violations = sorted(set(pure_file_imports) & FILE_ACCESS_IMPORTS)
    return {
        "files_scanned": list(W22_SOURCE_FILES),
        "imports": imports,
        "forbidden_imports": forbidden,
        "pure_statistics_file_access_imports": pure_violations,
        "ewt_functions": [
            name
            for name in _function_names(
                (
                    "src/coldguard_ml/w22_paired_statistics.py",
                    "src/coldguard_ml/w22_uncertainty.py",
                    "src/coldguard_ml/w22_sensitivity.py",
                    "src/coldguard_ml/w22_readiness.py",
                )
            )
            if "ewt" in name.lower()
        ],
        "capabilities": {
            "open_real_pair_outcomes": False,
            "read_campaign_export": False,
            "run_real_paired_analysis": False,
            "compute_real_treatment_effect": False,
            "access_w16_locked_test": False,
            "activate_controller_b": False,
            "retune_model_or_policy": False,
            "promote_gate_g4_g5": False,
        },
    }


def _render_descriptive_report() -> str:
    primary = fixture_primary()
    description = describe_pairs(primary)
    effect = paired_effect_size(primary, denominator_floor=TOY_DENOMINATOR_FLOOR)
    reference = describe_pairs(fixture_reference())
    one = describe_pairs(_dataset((4.0,), base_a=100.0, unit="°C·s", outcome_id="thermal_exposure"))
    two = describe_pairs(_dataset((1.0, 3.0), base_a=100.0, unit="°C·s", outcome_id="thermal_exposure"))
    constant = describe_pairs(fixture_constant())
    negative = describe_pairs(_dataset((-2.0, -3.0, -4.0), base_a=10.0, unit="s", outcome_id="recovery_time"))
    zeros = describe_pairs(_dataset((0.0, 0.0, 0.0), base_a=100.0, unit="°C·s", outcome_id="thermal_exposure"))
    mixed = describe_pairs(_dataset((2.0, -1.0, 0.0, 5.0), base_a=100.0, unit="°C·s", outcome_id="thermal_exposure"))

    lines = [
        "# B-W22-01/04 — Paired descriptive statistics contract",
        "",
        "> **SOFTWARE CONTRACT + TOY VERIFICATION ONLY.** Every numeric value in this",
        "> report comes from an explicitly synthetic in-memory fixture labelled",
        f"> `{LABEL_SYNTHETIC_TEST_ONLY}`. No physical A/B outcome was opened, and no",
        "> real treatment effect, CI, p-value or physical claim is computed here.",
        "",
        "## Scope and layer boundary",
        "",
        "- **Layer A (pure library):** accepts in-memory numeric pairs, validates",
        "  identities, computes descriptives, intervals, tests, effects and",
        "  sensitivity. It has no file, campaign-export, telemetry, database or",
        "  broker access and imports no file-reading module.",
        "- **Layer B (this harness):** creates toy fixtures and writes reports.",
        "- **Layer C (real analysis):** not implemented in W22; it requires the",
        "  W20 campaign lock to authorize a separate execution plus a reviewed",
        "  intake bridge.",
        "",
        "## Statistical unit and sign convention",
        "",
        "- Independent unit: one accepted matched Controller A/B pair.",
        f"- Frozen convention: `{SIGN_CONVENTION}` (lower-is-better outcomes).",
        "- `I_i > 0` = Controller B improved; `I_i = 0` = no observed difference;",
        "  `I_i < 0` = Controller B worsened.",
        "- Telemetry rows, overlapping windows, repeated event samples, single",
        "  arms, duplicated runs, bootstrap draws and attempts of one pair are",
        "  never independent observations.",
        "",
        "## Requirement coverage",
        "",
        "| task | implementation | proof |",
        "|---|---|---|",
        "| B-W22-01 descriptive statistics | pair admission, `describe_pairs`, every-pair SVG | unit tests, reference table above, complete-pair plot |",
        "| B-W22-02 95% CI | paired t interval, deterministic pair bootstrap | reference t criticals/CI, determinism, degenerate refusals |",
        "| B-W22-03 test family | predeclared dispatcher (paired t, sign, Wilcoxon) | independent test references, license and no-selection probes |",
        "| B-W22-04 effect size | native-unit mean, `d_z`, guarded relative reduction | paired-SD discrimination, zero-SD and denominator probes |",
        "| B-W22-05 sensitivity | mean vs median, leave-one-out, influence, interval and secondary labels | primary-immutability tests and sensitivity report |",
        "| B-W22-06 limitations | final-report template and interpretation categories | scientific-limitations report, `NO_INTERPRETATION_ANALYSIS_NOT_RUN` |",
        "",
        "## Pair admission rules enforced by the engine",
        "",
        "- exactly one Controller A arm and one Controller B arm per pair;",
        "- unique pair ID, unique pair block, unique run ID across pairs;",
        "- a rerun cannot become an additional independent pair;",
        "- finite numeric outcomes only: missing values are not zero, NaN and",
        "  infinity are refused, strings and booleans are refused;",
        "- censored recovery and undefined energy outcomes are excluded upstream",
        "  and never enter as numeric values;",
        "- both arms and the dataset share the frozen native unit;",
        "- admitted and excluded pairs are disjoint; exclusions are listed with",
        "  reason codes, never silently dropped.",
        "",
        "## Toy pair table (TEST_ONLY)",
        "",
        f"Outcome: `{description.outcome_id}` [{description.unit}] — role "
        f"`{description.outcome_role}`.",
        "",
        "| pair | Controller A run | Controller B run | Y_A | Y_B | I_i | direction |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for pair, improvement in zip(primary.pairs, primary.improvements):
        direction = (
            "B improved"
            if improvement > 0
            else ("B worsened" if improvement < 0 else "no difference")
        )
        lines.append(
            f"| {pair.pair_id} | {pair.arm_a.run_id} | {pair.arm_b.run_id} | "
            f"{_num(pair.arm_a.value)} | {_num(pair.arm_b.value)} | "
            f"{_num(improvement)} | {direction} |"
        )
    lines.extend(
        [
            "",
            "## Toy summary statistics (TEST_ONLY)",
            "",
            "| statistic | value |",
            "|---|---:|",
            f"| valid pair count | {description.pair_count} |",
            f"| excluded pair count | {description.excluded_pair_count} |",
            f"| mean improvement | {_num(description.mean_improvement)} |",
            f"| median improvement | {_num(description.median_improvement)} |",
            f"| sample SD (n-1) | {_num(description.sample_standard_deviation)} |",
            f"| population SD (n) | {_num(description.population_standard_deviation)} |",
            f"| Q1 | {_num(description.q1)} |",
            f"| Q3 | {_num(description.q3)} |",
            f"| IQR | {_num(description.interquartile_range)} |",
            f"| minimum | {_num(description.minimum_improvement)} |",
            f"| maximum | {_num(description.maximum_improvement)} |",
            f"| positive / zero / negative differences | {description.positive_difference_count} / {description.zero_difference_count} / {description.negative_difference_count} |",
            f"| direction | {description.direction} |",
            f"| distinct sessions / rig IDs | {description.session_count} / {description.rig_count} |",
            f"| multi-site claim supported | {str(description.multi_site_claim_supported).lower()} |",
            "",
            f"Quantile convention: `{QUANTILE_CONVENTION}`. Pair ordering policy: "
            f"`{PAIR_ORDER_POLICY}`.",
            "",
            "## Special cases (TEST_ONLY)",
            "",
            "| fixture | N | mean | sample SD | direction | notes |",
            "|---|---:|---:|---:|---|---|",
        ]
    )
    for name, item in (
        ("one pair", one),
        ("two pairs", two),
        ("constant differences", constant),
        ("all zero differences", zeros),
        ("negative improvement", negative),
        ("mixed signs", mixed),
    ):
        lines.append(
            f"| {name} | {item.pair_count} | {_num(item.mean_improvement)} | "
            f"{_num(item.sample_standard_deviation)} | {item.direction} | "
            f"{'; '.join(item.notes) if item.notes else '—'} |"
        )
    lines.extend(
        [
            "",
            "## Independent numerical verification",
            "",
            "Reference values were calculated independently (hand formulas / a",
            "trusted statistics library at authoring time) and are encoded in the",
            "test suite; the driver re-checks them at generation time.",
            "",
            "| check | expected | observed | tolerance | pass |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for check in _reference_checks():
        lines.append(
            f"| {check['name']} | {_num(check['expected'])} | "
            f"{_num(check['observed'])} | {check['tolerance']} | "
            f"{str(check['passed']).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Effect size (TEST_ONLY)",
            "",
            f"- outcome: `{effect.outcome_id}` [{effect.unit}] — "
            f"{effect.evidence_label}",
            f"- native-unit absolute improvement: `{_num(effect.mean_improvement)}` "
            f"{effect.unit}",
            f"- standardized paired effect `d_z = mean(I) / SD(I)`: "
            f"`{_num(effect.standardized_dz)}` ({effect.standardized_status})",
            f"- relative reduction: `{_num(effect.relative_improvement)}` "
            f"({effect.relative_status})",
            f"- toy denominator floor: `{_num(effect.denominator_floor)}` "
            f"{effect.unit} — **toy demonstration only, not a frozen physical value**",
            f"- direction: `{effect.direction}`",
            "",
            "A synthetic d_z is a mathematical test result, not a physical effect",
            "estimate; a zero or near-zero denominator never yields an infinite or",
            "misleading percentage.",
            "",
            "## Every-pair visualization",
            "",
            f"`{PLOT_NAME}` draws all {description.pair_count} pairs once, with Controller A",
            "circles, Controller B squares, improvement direction by colour, pair",
            "identity in each element title, the primary role label and a permanent",
            "`TEST_ONLY` banner. No average-only bar chart is produced.",
            "",
            "## Unclosed scientific work",
            "",
            "The real descriptives for accepted physical pairs cannot be produced",
            "until the W20 campaign gate authorizes a separate execution and A/C/D",
            "supply the frozen outcomes with accepted source hashes.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_uncertainty_report() -> str:
    primary = fixture_primary()
    interval = paired_t_interval(primary)
    interval_declaration = predeclare_interval_method(
        primary_method="PAIRED_T_95_CI",
        method_freeze_id=TOY_INTERVAL_FREEZE_ID,
    )
    bootstrap = bootstrap_percentile_interval(
        primary,
        seed=TOY_SEED,
        iterations=BOOTSTRAP_DEFAULT_ITERATIONS,
        role=INTERVAL_ROLE_SENSITIVITY,
    )
    assert_single_primary([interval, bootstrap])
    primary_interval = resolve_primary_interval(
        primary=interval,
        sensitivity=bootstrap,
        declaration=interval_declaration,
    )
    constant_interval = paired_t_interval(fixture_constant())
    one = _dataset((4.0,), base_a=100.0, unit="°C·s", outcome_id="thermal_exposure")
    two = _dataset((1.0, 3.0), base_a=100.0, unit="°C·s", outcome_id="thermal_exposure")
    two_interval = paired_t_interval(two)
    test = run_predeclared_test(
        primary,
        predeclare_test(
            preferred_test_family=TEST_PAIRED_T,
            method_freeze_id=TOY_METHOD_FREEZE_ID,
            assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T],
        ),
    )
    fallback = run_predeclared_test(
        fixture_constant(),
        predeclare_test(
            preferred_test_family=TEST_PAIRED_T,
            method_freeze_id=TOY_METHOD_FREEZE_ID,
            assumption_licenses=[ASSUMPTION_LICENSE_PAIRED_T, ASSUMPTION_LICENSE_SIGN],
            fallback_test_family=TEST_SIGN,
            fallback_reason_code=TEST_REASON_ZERO_DISPERSION,
        ),
        fallback_evidence="TOY_ONLY: constant differences preclude a t statistic",
    )
    lines = [
        "# B-W22-02/03 — 95% confidence intervals and predeclared test family",
        "",
        "> **SOFTWARE CONTRACT + TOY VERIFICATION ONLY.** No physical outcome was",
        "> opened and no real CI or p-value exists.",
        "",
        "## Student-t critical values (independent references)",
        "",
        "| df | t(0.975, df) computed | reference | pass |",
        "|---:|---:|---:|---|",
    ]
    for degrees, expected in (
        (1, 12.706204736174694),
        (4, 2.7764451051977934),
        (7, REFERENCE["t_critical_df7"]),
        (9, 2.262157162798205),
        (19, 2.0930240544083087),
        (100, 1.983971518523552),
    ):
        observed = student_t_critical(0.975, degrees)
        lines.append(
            f"| {degrees} | {_num(observed)} | {_num(expected)} | "
            f"{str(abs(observed - expected) < 1e-9).lower()} |"
        )
    lines.extend(
        [
            "",
            "The small-N interval uses the Student-t critical value, never an",
            "automatic 1.96; the degrees of freedom are `n - 1`.",
            "",
            "## Primary paired t interval (TEST_ONLY)",
            "",
            f"- method: `{interval.method}` — role `{interval.role}`",
            f"- declared primary method: `{interval_declaration.primary_method}` "
            f"(freeze id `{interval_declaration.method_freeze_id}`)",
            f"- exactly one primary interval: `{primary_interval.method}`",
            f"- N: {interval.pair_count}, df: {interval.degrees_of_freedom}",
            f"- mean improvement: `{_num(interval.point_estimate)}` °C·s",
            f"- sample SD: `{_num(describe_pairs(primary).sample_standard_deviation)}`",
            f"- standard error: `{_num(interval.standard_error)}`",
            f"- critical value: `{_num(interval.critical_value)}`",
            f"- 95% CI: [`{_num(interval.lower)}`, `{_num(interval.upper)}`] °C·s",
            f"- research-grade settings: {str(interval.research_grade).lower()}",
            "",
            "## Pair-level bootstrap (TEST_ONLY, SENSITIVITY ROLE)",
            "",
            f"- role: `{bootstrap.role}` — a second interval method is always",
            "  labelled sensitivity and can never be primary by width or favour.",
            f"- statistic: `{bootstrap.statistic}`",
            f"- resampling unit: `{bootstrap.resampling_unit}` — complete matched pairs",
            f"- seed: `{bootstrap.seed}`, iterations: {bootstrap.iterations}, "
            f"quantile convention: `{bootstrap.quantile_convention}`",
            f"- RNG: `{bootstrap.rng_name}`",
            f"- percentile 95% CI: [`{_num(bootstrap.lower)}`, `{_num(bootstrap.upper)}`] °C·s",
            f"- draw digest: `{bootstrap.draw_digest}`",
            f"- research-grade settings: {str(bootstrap.research_grade).lower()}",
            "",
            "The canonical final setting is at least 2,000 iterations, preferably",
            "5,000–10,000, with a recorded seed. A and B arms are never resampled",
            "independently, and telemetry windows are never resampling units.",
            "",
            "Interval policy: exactly one predeclared primary interval per outcome.",
            "The bootstrap can be reported as the labelled sensitivity interval; it",
            "cannot become primary by being narrower or more favourable.",
            "",
            "## Degenerate cases (TEST_ONLY)",
            "",
            "| fixture | method | status | reason |",
            "|---|---|---|---|",
            f"| one pair | paired t | {paired_t_interval(one).status} | {paired_t_interval(one).reason_code} |",
            f"| two pairs | paired t | {two_interval.status} | {two_interval.reason_code} |",
            f"| constant differences | paired t | {constant_interval.status} | {constant_interval.reason_code} |",
            f"| constant differences | bootstrap | {bootstrap_percentile_interval(fixture_constant(), seed=TOY_SEED).status} | {bootstrap_percentile_interval(fixture_constant(), seed=TOY_SEED).reason_code} |",
            "",
            "A constant (zero-width) interval is reported as the constant with an",
            "explicit refusal, never as perfect scientific certainty.",
            "",
            "## Predeclared paired test family",
            "",
            "Supported methods: paired t-test, exact sign test, Wilcoxon signed-rank",
            "under its licensed assumption, and pair-level bootstrap uncertainty.",
            "The dispatcher runs exactly one declared family. It has no API that",
            "compares candidate p-values, and no code path selects the smallest p.",
            "A fallback runs only when the preferred method is not estimable with",
            "the exact predeclared reason code, the fallback family's assumption",
            "license is declared, and the diagnostic evidence is recorded. No",
            "normality test is implemented, so a failed normality check can never",
            "be used as an automatic switch to a favourable method.",
            "",
            "Declaration: preferred family `PAIRED_T`, method freeze id "
            f"`{TOY_METHOD_FREEZE_ID}`, alternative `two-sided`, assumption license "
            f"`{ASSUMPTION_LICENSE_PAIRED_T}` (toy declaration only).",
            "",
            "| field | value |",
            "|---|---|",
            f"| family | {test.family} |",
            f"| status | {test.status} |",
            f"| paired differences used | {test.pair_count} pairs / {test.pair_count} differences |",
            f"| statistic (t) | {_num(test.statistic)} |",
            f"| degrees of freedom | {test.degrees_of_freedom} |",
            f"| p-value (two-sided, toy) | {_num(test.p_value)} |",
            f"| claim boundary | `{test.claim_boundary}` |",
            "",
            "A low toy p-value is not a physical effect, not practical significance",
            "and not a declaration of physical superiority.",
            "",
            "### Predeclared fallback demonstration (TEST_ONLY)",
            "",
            "The t-test is not estimable for constant differences; the declaration",
            "predeclares the exact sign test with the recorded reason and license.",
            "",
            "| field | value |",
            "|---|---|",
            f"| preferred failure | `{fallback.preferred_failure_reason}` |",
            f"| fallback family | {fallback.family} |",
            f"| fallback applied | {str(fallback.fallback_applied).lower()} |",
            f"| fallback p-value (toy) | {_num(fallback.p_value)} |",
            "",
            "## Independent test verification",
            "",
            "| check | expected | observed | tolerance | pass |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for check in _reference_checks():
        if check["name"] in {
            "t_statistic_primary",
            "t_p_primary",
            "sign_p_primary",
            "wilcoxon_p_primary",
        }:
            lines.append(
                f"| {check['name']} | {_num(check['expected'])} | "
                f"{_num(check['observed'])} | {check['tolerance']} | "
                f"{str(check['passed']).lower()} |"
            )
    lines.extend(
        [
            "",
            "Wilcoxon exact p-values use midranks and the exact sign-flip",
            "permutation distribution (n_eff <= 16); above that, a tie-corrected",
            "normal approximation with continuity correction is used. Zero",
            "differences are dropped and reported as `n_zero`. For tied",
            "absolute differences the midrank permutation value is the reference;",
            "a forced-exact library call that re-ranks ties without midranks",
            "can report a different number and is not used here.",
            "",
            "## Unclosed scientific work",
            "",
            "The real primary CI, real test result and real bootstrap interval",
            "remain withheld until the W20 gate authorizes a separate execution and",
            "the frozen outcome export is admitted.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_sensitivity_report() -> str:
    primary = fixture_primary()
    description = describe_pairs(primary)
    loo = leave_one_pair_out(
        primary, description, declared_status=SENSITIVITY_STATUS_EXPLORATORY
    )
    statistic = mean_vs_median(
        primary, description, declared_status=SENSITIVITY_STATUS_EXPLORATORY
    )
    extreme = extreme_pair_influence(
        fixture_extreme(),
        describe_pairs(fixture_extreme()),
        declared_status=SENSITIVITY_STATUS_EXPLORATORY,
    )
    secondary = secondary_outcome_contrast(
        primary, fixture_secondary(), declared_status=SENSITIVITY_STATUS_EXPLORATORY
    )
    primary_interval = paired_t_interval(primary, role=INTERVAL_ROLE_PRIMARY)
    sensitivity_interval = bootstrap_percentile_interval(
        primary,
        seed=TOY_SEED,
        iterations=BOOTSTRAP_DEFAULT_ITERATIONS,
        role=INTERVAL_ROLE_SENSITIVITY,
    )
    interval_declaration = predeclare_interval_method(
        primary_method="PAIRED_T_95_CI",
        method_freeze_id=TOY_INTERVAL_FREEZE_ID,
    )
    comparison = compare_intervals(
        primary=primary_interval,
        sensitivity=sensitivity_interval,
        declaration=interval_declaration,
    )
    lines = [
        "# B-W22-05 — Sensitivity and robustness contract",
        "",
        "> **SOFTWARE CONTRACT + TOY VERIFICATION ONLY.** Sensitivity discloses",
        "> dependence on analytical choices; it is not a route to selecting a",
        "> favourable result. The primary analysis always retains all valid pairs.",
        "",
        "## Rules",
        "",
        "- The primary statistic is predeclared; every alternative is labelled",
        "  `SENSITIVITY_ONLY_NOT_PRIMARY` and cannot be promoted.",
        "- A leave-one-pair-out run reports the omitted pair, the changed N and",
        "  the difference from the primary; it never invalidates the pair and",
        "  never changes the primary result.",
        "- A valid extreme pair cannot be excluded from the primary merely because",
        "  it changes significance.",
        "- A PREDECLARED sensitivity requires a frozen plan reference; otherwise",
        "  it is EXPLORATORY.",
        "- Secondary outcomes stay secondary; no post-result promotion.",
        "- Alternate prediction horizons are not implemented in W22 because the",
        "  W13 primary horizon remains unfrozen.",
        "",
        "## Leave-one-pair-out (TEST_ONLY, EXPLORATORY)",
        "",
        "| sensitivity ID | status | omitted pair | input pairs | valid N | mean without pair | delta from primary | label | interpretation boundary |",
        "|---|---|---|---|---:|---:|---:|---|---|",
    ]
    for item in loo:
        lines.append(
            f"| {item.sensitivity_id} | {item.declared_status} | "
            f"{item.omitted_pair_ids[0]} | all admitted minus "
            f"{item.omitted_pair_ids[0]} | "
            f"{item.valid_n} | {_num(item.statistic_value)} | "
            f"{_num(item.difference_from_primary)} | `{item.label}` | "
            "primary retains every valid pair; omission is not invalidation |"
        )
    lines.extend(
        [
            "",
            f"Primary N remains {description.pair_count}; primary mean remains "
            f"`{_num(description.mean_improvement)}` °C·s. The primary result is "
            "unchanged by every sensitivity computation.",
            "",
            "## Mean versus median (TEST_ONLY)",
            "",
            "| statistic | status | value | primary statistic | primary value | label | boundary |",
            "|---|---|---:|---|---:|---|---|",
            f"| median | {statistic.declared_status} | "
            f"{_num(statistic.statistic_value)} | mean | "
            f"{_num(statistic.primary_value)} | `{statistic.label}` | "
            "primary mean unchanged |",
            "",
            "## Extreme-pair influence (TEST_ONLY, EXTREME FIXTURE)",
            "",
            "Fixture improvements: " + ", ".join(_num(value) for value in EXTREME_IMPROVEMENTS),
            "",
            "| sensitivity ID | status | omitted pair | valid N | mean without pair | delta | primary N | boundary |",
            "|---|---|---|---:|---:|---:|---:|---|",
            f"| {extreme.sensitivity_id} | {extreme.declared_status} | "
            f"{extreme.omitted_pair_ids[0]} | "
            f"{extreme.valid_n} | {_num(extreme.statistic_value)} | "
            f"{_num(extreme.difference_from_primary)} | {extreme.primary_n} | "
            "extreme pair retained in the primary |",
            "",
            "The extreme pair remains in the primary analysis; only the derived",
            "sensitivity number omits it.",
            "",
            "## Bootstrap versus parametric uncertainty (TEST_ONLY)",
            "",
            "| role | method | lower | upper |",
            "|---|---|---:|---:|",
            f"| PRIMARY | {comparison.primary_method} | "
            f"{_num(comparison.primary_lower)} | {_num(comparison.primary_upper)} |",
            f"| SENSITIVITY | {comparison.sensitivity_method} | "
            f"{_num(comparison.sensitivity_lower)} | {_num(comparison.sensitivity_upper)} |",
            "",
            f"Selection rule: `{comparison.selection_rule}`; label "
            f"`{comparison.label}`; promotion allowed: "
            f"{str(comparison.promotion_allowed).lower()}.",
            f"Sensitivity bootstrap settings: seed `{sensitivity_interval.seed}`, "
            f"iterations {sensitivity_interval.iterations}, "
            f"research-grade {str(sensitivity_interval.research_grade).lower()}.",
            "",
            "## Secondary outcome contrast (TEST_ONLY)",
            "",
            "| outcome | status | role | N | shared pair IDs with primary | mean improvement | label | promotion allowed |",
            "|---|---|---|---:|---:|---:|---|---|",
            f"| {secondary.outcome_id} | {secondary.declared_status} | secondary | "
            f"{secondary.valid_n} | {len(secondary.shared_pair_ids)} | "
            f"{_num(secondary.statistic_value)} | `{secondary.label}` | "
            f"{str(secondary.promotion_allowed).lower()} |",
            "",
            f"Contrast scope: {secondary.interpretation_boundary}",
            "",
            "## Multiple-comparison discipline",
            "",
            "- primary hypothesis: the frozen primary physical outcome;",
            "- frozen secondary outcomes: reported separately with their own N;",
            "- exploratory sensitivity checks: labelled EXPLORATORY and never used",
            "  as confirmation of the main project thesis.",
            "",
            "The pure library cannot detect an exclusion omitted upstream: the",
            "excluded-pair list must come from the complete W19 attempt ledger.",
            "The W19-bound intake is a future, separately reviewed bridge.",
            "",
            "## Unclosed scientific work",
            "",
            "Real sensitivity tables cannot be produced until the final physical",
            "pairs exist and the W20 gate authorizes analysis. Alternate-horizon",
            "sensitivity requires the W13 horizon freeze and is refused here.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_limitations_report() -> str:
    lines = [
        "# B-W22-06 — Scientific limitations and final-report contract",
        "",
        "> **TEMPLATE ONLY — NO RESULT. TEST_ONLY harness; no physical data.** The",
        "> physical analysis has not run.",
        "",
        "## Current scientific status",
        "",
        "| field | value |",
        "|---|---|",
        "| real accepted pair count | NOT_ESTABLISHED (no campaign completed) |",
        "| pair target | UNKNOWN_UNFROZEN |",
        "| statistical freeze | NOT_FROZEN |",
        "| analysis authorization | NOT_AUTHORIZED |",
        "| physical inference | NOT_COMPUTED |",
        "| W16 holdout | NOT_OPENED |",
        "| G4 | NOT_READY |",
        "| G5 | NOT_ESTABLISHED |",
        "| W20 final analysis | LOCKED |",
        "",
        "## Separate scientific questions",
        "",
        f"- **Predictive quality:** did the model identify an impending thermal",
        f"  event on eligible non-intervened data?",
        f"- **Physical treatment effect:** did Controller B actually improve the",
        f"  measured thermal or energy outcome relative to Controller A?",
        "",
        "These questions have different evidence requirements. Synthetic AP,",
        "synthetic A1/A2/A3 gains, offline EWT, model serialization checks and",
        "diagnosis software tests are not substitutes for a real physical paired",
        "A/B result.",
        "",
        "## Final report template",
        "",
        render_final_report_template_markdown(),
        "",
        "## Analysis status",
        "",
        f"`{build_final_report_template()['current_interpretation']}` is the only",
        "permitted real-result category in the current repository state.",
        "",
        "## Withheld physical artifacts",
        "",
    ]
    lines.extend(f"- {item}" for item in WITHHELD_RESULT_ARTIFACTS)
    lines.extend(["", "## Mandatory limitations", ""])
    lines.extend(f"{index}. {item}" for index, item in enumerate(LIMITATIONS, 1))
    return "\n".join(lines) + "\n"


def _render_readiness_report() -> str:
    blocked_assessment, blocked_readiness = _toy_readiness()
    fake_assessment, fake_readiness = _toy_readiness(fake_authorization=True)
    w20 = _read_json(ML_ROOT / "reports" / "W20" / "w20-manifest.json")
    w21 = _read_json(ML_ROOT / "reports" / "W21" / "w21-manifest.json")
    lines = [
        "# W22 analysis-readiness and W20 gate binding",
        "",
        "> **TEST_ONLY HARNESS — NO REAL ANALYSIS.** No physical paired analysis",
        "> is authorized or executed by W22.",
        "",
        "## Authoritative gate",
        "",
        "The W20 campaign-lock assessment remains the only admission authority.",
        "W22's readiness function accepts campaign metadata (never a pre-labelled",
        "assessment object) and calls `assess_campaign_lock` itself. It refuses",
        "real analysis unless the gate decision is",
        f"`{ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION}`, the analysis",
        "authorization status is `ISSUED`, no refusal reasons remain, and the",
        "assessment reports no outcome access. W22 introduces no second path.",
        "",
        "## Toy metadata-only gate proof",
        "",
        "| probe | gate decision | analysis authorization | readiness | outcome access |",
        "|---|---|---|---|---|",
        f"| blocked toy bundle | {blocked_assessment.gate_decision} | "
        f"{blocked_assessment.analysis_authorization_status} | "
        f"{blocked_readiness.physical_analysis} | "
        f"{str(blocked_assessment.outcome_access).lower()} |",
        f"| toy bundle with fake embedded approval | {fake_assessment.gate_decision} | "
        f"{fake_assessment.analysis_authorization_status} | "
        f"{fake_readiness.physical_analysis} | "
        f"{str(fake_assessment.outcome_access).lower()} |",
        "",
        "A fake embedded approval is rejected: the authorization must be",
        "externally verified and file-bound, and the remaining campaign groups",
        "still block the gate.",
        "",
        "## Current observed status (from W20/W21 metadata manifests)",
        "",
        "| field | value | source |",
        "|---|---|---|",
        f"| FINAL_AB_CAMPAIGN | {w20['verdicts']['FINAL_CAMPAIGN']} | W20 manifest |",
        f"| PAIR_TARGET | {w20['verdicts']['PAIR_TARGET']} | W20 manifest |",
        f"| W20_ANALYSIS | {w20['verdicts']['W20_ANALYSIS']} | W20 manifest |",
        f"| W16_HOLDOUT | {w20['verdicts']['W16_HOLDOUT']} | W20 manifest |",
        f"| W20_FINAL_ANALYSIS | {w21['scientific_integrity']['W20_FINAL_ANALYSIS']} | W21 manifest |",
        f"| G4 | {w21['scientific_integrity']['G4']} | W21 manifest |",
        f"| G5 | {w21['scientific_integrity']['G5']} | W21 manifest |",
        f"| W13 primary horizon | {w21['scientific_integrity']['W13_PRIMARY_HORIZON']} | W21 manifest |",
        f"| W15 model | {w21['scientific_integrity']['W15_MODEL']} | W21 manifest |",
        "",
        "## Necessary conditions for a future real analysis",
        "",
    ]
    lines.extend(f"{index}. {item}" for index, item in enumerate(REQUIRED_FUTURE_CONDITIONS, 1))
    lines.extend(
        [
            "",
            "## Why the pure engine cannot reach real campaign data",
            "",
            "- the pure modules accept only in-memory numeric pairs and import no",
            "  file, CSV, telemetry, database or broker module;",
            "- the W22 driver has no input-file option and cannot read a",
            "  `pair-outcomes.csv`;",
            "- the engine is not imported by the W20 preflight or W19 gates, and",
            "  those modules were not modified;",
            "- W19's no-peeking behaviour and W20's outcome-access lock remain",
            "  intact, and W16 locked-test files are untouched;",
            "- even an authorized W20 decision would only permit a separately",
            "  reviewed intake bridge, which W22 does not implement.",
            "",
            "## Verdicts",
            "",
            "```text",
            "PHYSICAL_ANALYSIS = NOT_AUTHORIZED",
            "REAL_PAIRED_STATISTICS = NOT_COMPUTED",
            "FINAL_PHYSICAL_CI = NOT_COMPUTED",
            "FINAL_PHYSICAL_P_VALUE = NOT_COMPUTED",
            "FINAL_PHYSICAL_EFFECT = NOT_ESTABLISHED",
            "W20_ANALYSIS_GATE = LOCKED",
            "G4 = NOT_READY",
            "G5 = NOT_ESTABLISHED",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _prior_layer_immutability() -> list[dict]:
    rows = []
    for relative, expected in PRIOR_ARTIFACTS.items():
        observed = _sha256_bytes((ML_ROOT / relative).read_bytes())
        rows.append(
            {
                "path": relative,
                "expected_sha256": expected,
                "observed_sha256": observed,
                "unchanged": observed == expected,
            }
        )
    return rows


def _manifest(out_dir: Path, probes: list[dict]) -> dict:
    w20 = _read_json(ML_ROOT / "reports" / "W20" / "w20-manifest.json")
    w21 = _read_json(ML_ROOT / "reports" / "W21" / "w21-manifest.json")
    blocked_assessment, blocked_readiness = _toy_readiness()
    reports = {
        name: _sha256_bytes((out_dir / name).read_bytes()) for name in REPORT_NAMES
    }
    reports[PLOT_NAME] = _sha256_bytes((out_dir / PLOT_NAME).read_bytes())
    return {
        "schema": "coldguard-w22-paired-statistics-contract-v1",
        "layer_versions": {
            "paired_statistics": "coldguard-w22-paired-statistics-v1",
            "uncertainty": "coldguard-w22-uncertainty-v1",
            "sensitivity": "coldguard-w22-sensitivity-v1",
            "readiness": "coldguard-w22-readiness-v1",
        },
        "statistical_unit": "one accepted matched Controller A/B pair",
        "sign_convention": SIGN_CONVENTION,
        "pair_order_policy": PAIR_ORDER_POLICY,
        "quantile_convention": QUANTILE_CONVENTION,
        "bootstrap_policy": {
            "resampling_unit": "COMPLETE_MATCHED_PAIRS",
            "minimum_iterations": BOOTSTRAP_MIN_ITERATIONS,
            "default_iterations": BOOTSTRAP_DEFAULT_ITERATIONS,
            "seed": TOY_SEED,
            "rng": RNG_IDENTITY,
            "quantile_convention": QUANTILE_CONVENTION,
        },
        "reproducibility": {
            "python_requires": ">=3.12",
            "third_party_runtime_dependencies": "NONE_FOR_W22_ENGINE",
            "numpy": "NOT_USED",
            "rng": RNG_IDENTITY,
            "quantile_convention": QUANTILE_CONVENTION,
            "pair_order_policy": PAIR_ORDER_POLICY,
            "bootstrap_seed": TOY_SEED,
            "determinism": "TWO_INDEPENDENT_PROCESSES_BYTE_IDENTICAL",
        },
        "interval_policy": {
            "primary_method": "PAIRED_T_95_CI",
            "confidence_level": 0.95,
            "second_method_role": INTERVAL_ROLE_SENSITIVITY,
            "selection_rule": "PREDECLARED_NO_FAVORABILITY_OR_WIDTH_SELECTION",
            "freeze_id": TOY_INTERVAL_FREEZE_ID,
        },
        "verification": {
            "reference_checks": _reference_checks(),
            "adversarial_controls": {
                "probe_count": len(probes),
                "probes_passed": sum(1 for probe in probes if probe["passed"]),
                "probes": probes,
            },
            "deterministic_replay": "TWO_INDEPENDENT_PROCESSES_COMPARED_BY_TESTS",
        },
        "capability_audit": _capability_audit(),
        "capabilities": {
            "open_real_pair_outcomes": False,
            "read_campaign_export": False,
            "run_real_paired_analysis": False,
            "compute_real_treatment_effect": False,
            "access_w16_locked_test": False,
            "activate_controller_b": False,
            "retune_model_or_policy": False,
            "promote_gate_g4_g5": False,
        },
        "toy_fixtures": {
            "label": LABEL_SYNTHETIC_TEST_ONLY,
            "primary_improvements": list(PRIMARY_IMPROVEMENTS),
            "secondary_improvements": list(SECONDARY_IMPROVEMENTS),
            "reference_improvements": list(REFERENCE_IMPROVEMENTS),
            "constant_improvements": list(CONSTANT_IMPROVEMENTS),
            "extreme_improvements": list(EXTREME_IMPROVEMENTS),
        },
        "scientific_integrity": {
            "G4": w21["scientific_integrity"]["G4"],
            "G5": w21["scientific_integrity"]["G5"],
            "W16_HOLDOUT": w20["verdicts"]["W16_HOLDOUT"],
            "W20_FINAL_ANALYSIS": w21["scientific_integrity"]["W20_FINAL_ANALYSIS"],
            "PAIR_TARGET": w20["verdicts"]["PAIR_TARGET"],
            "FINAL_AB_CAMPAIGN": w20["verdicts"]["FINAL_CAMPAIGN"],
            "PHYSICAL_ANALYSIS": blocked_readiness.physical_analysis,
            "REAL_PAIRED_STATISTICS": blocked_readiness.real_paired_statistics,
            "FINAL_PHYSICAL_CI": "NOT_COMPUTED",
            "FINAL_PHYSICAL_P_VALUE": "NOT_COMPUTED",
            "FINAL_PHYSICAL_EFFECT": "NOT_ESTABLISHED",
            "INTERPRETATION": "NO_INTERPRETATION_ANALYSIS_NOT_RUN",
        },
        "verdicts": {
            "B_W22_01_DESCRIPTIVE_STATISTICS": "SOFTWARE_VERIFIED",
            "B_W22_02_95_CI": "SOFTWARE_VERIFIED",
            "B_W22_03_TEST_FAMILY": "SOFTWARE_VERIFIED",
            "B_W22_04_EFFECT_SIZE": "SOFTWARE_VERIFIED",
            "B_W22_05_SENSITIVITY": "SOFTWARE_VERIFIED",
            "B_W22_06_LIMITATIONS": "DOCUMENTED",
            "REAL_PAIRED_ANALYSIS": "NOT_RUN",
            "FINAL_PHYSICAL_CI": "NOT_COMPUTED",
            "FINAL_PHYSICAL_P_VALUE": "NOT_COMPUTED",
            "FINAL_PHYSICAL_EFFECT": "NOT_ESTABLISHED",
            "W20_ANALYSIS_GATE": "LOCKED",
            "G4": w21["scientific_integrity"]["G4"],
            "G5": w21["scientific_integrity"]["G5"],
            "SOFTWARE": "COMPLETE",
            "DELIVERY": "PENDING_PUBLICATION",
        },
        "readiness": {
            "gate_decision": blocked_assessment.gate_decision,
            "physical_analysis": blocked_readiness.physical_analysis,
            "real_paired_statistics": blocked_readiness.real_paired_statistics,
            "reasons": list(blocked_readiness.reasons),
            "required_future_conditions": list(REQUIRED_FUTURE_CONDITIONS),
        },
        "limitations": list(LIMITATIONS),
        "prior_layer_immutability": _prior_layer_immutability(),
        "generation_inputs": {
            "reports/W20/w20-manifest.json": PRIOR_ARTIFACTS["reports/W20/w20-manifest.json"],
            "reports/W21/w21-manifest.json": PRIOR_ARTIFACTS["reports/W21/w21-manifest.json"],
        },
        "reports": reports,
    }


def generate(out_dir: Path = DEFAULT_OUT) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    probes = _adversarial_controls()
    assert all(probe["passed"] for probe in probes), [
        probe for probe in probes if not probe["passed"]
    ]
    primary = fixture_primary()
    plot = render_every_pair_svg(primary)
    reports = {
        "paired-statistics-contract-W22.md": _render_descriptive_report(),
        "uncertainty-and-tests-W22.md": _render_uncertainty_report(),
        "sensitivity-contract-W22.md": _render_sensitivity_report(),
        "scientific-limitations-W22.md": _render_limitations_report(),
        "analysis-readiness-W22.md": _render_readiness_report(),
        PLOT_NAME: plot,
    }
    for name, content in reports.items():
        _write(out_dir / name, content)
    manifest = _manifest(out_dir, probes)
    _write(
        out_dir / MANIFEST_NAME,
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    return {
        "out_dir": str(out_dir),
        "reports": sorted(reports),
        "probes": len(probes),
        "probes_passed": sum(1 for probe in probes if probe["passed"]),
        "manifest": MANIFEST_NAME,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the W22 statistics software-contract reports."
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = generate(args.out)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
