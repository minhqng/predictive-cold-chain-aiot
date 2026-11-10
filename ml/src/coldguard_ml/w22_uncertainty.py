"""W22 paired uncertainty and the predeclared test family (Layer A).

Canonical anchors: Doc 03 sections 76-80 and 133; analysis plan sections
4.4-4.6.  The module is pure: no files, no campaign exports, no telemetry.
It provides the paired Student-t interval, a deterministic complete-pair
percentile bootstrap, and a small predeclared test-family dispatcher.
Method choice is never made by comparing p-values.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Sequence

from .w22_paired_statistics import (
    LABEL_SYNTHETIC_TEST_ONLY,
    MIN_PAIRS_FOR_INFERENCE,
    QUANTILE_CONVENTION,
    W22StatisticsError,
    PairedDataset,
    quantile_type7,
)

W22_UNCERTAINTY_LAYER_VERSION = "coldguard-w22-uncertainty-v1"

METHOD_PAIRED_T_INTERVAL = "PAIRED_T_95_CI"
METHOD_BOOTSTRAP_PERCENTILE = "PAIR_BOOTSTRAP_PERCENTILE_95_CI"
INTERVAL_METHODS = (METHOD_PAIRED_T_INTERVAL, METHOD_BOOTSTRAP_PERCENTILE)
INTERVAL_ROLE_PRIMARY = "PRIMARY"
INTERVAL_ROLE_SENSITIVITY = "SENSITIVITY"
FROZEN_CONFIDENCE_LEVEL = 0.95

STATUS_ESTIMABLE = "ESTIMABLE"
STATUS_NOT_ESTIMABLE = "NOT_ESTIMABLE"

REASON_INSUFFICIENT_PAIRS = "CI_NOT_ESTIMABLE_INSUFFICIENT_PAIRS"
REASON_ZERO_DISPERSION = "CI_NOT_ESTIMABLE_ZERO_DISPERSION"
REASON_BOOTSTRAP_COLLAPSE = "CI_NOT_ESTIMABLE_BOOTSTRAP_COLLAPSE"
REASON_BOOTSTRAP_SEED_REQUIRED = "BOOTSTRAP_SEED_REQUIRED"
REASON_BOOTSTRAP_ITERATIONS = "BOOTSTRAP_ITERATIONS_BELOW_FROZEN_MINIMUM"
REASON_UNKNOWN_STATISTIC = "UNKNOWN_CI_STATISTIC"
REASON_MULTIPLE_PRIMARY = "MULTIPLE_PRIMARY_INTERVALS_REFUSED"
REASON_PRIMARY_NOT_DECLARED = "PRIMARY_INTERVAL_NOT_DECLARED"
REASON_PRIMARY_ROLE = "PRIMARY_INTERVAL_ROLE_INVALID"
REASON_CONFIDENCE_LEVEL = "CONFIDENCE_LEVEL_NOT_FROZEN_95"
REASON_INTERVAL_DECLARATION = "PRIMARY_INTERVAL_DECLARATION_INVALID"
REASON_INTERVAL_MISMATCH = "PRIMARY_INTERVAL_DECLARATION_MISMATCH"

BOOTSTRAP_MIN_ITERATIONS = 2000
BOOTSTRAP_DEFAULT_ITERATIONS = 5000
BOOTSTRAP_MAX_ITERATIONS = 100000
BOOTSTRAP_STATISTIC_MEAN = "MEAN"
BOOTSTRAP_STATISTIC_MEDIAN = "MEDIAN"
RESAMPLING_UNIT_COMPLETE_PAIRS = "COMPLETE_MATCHED_PAIRS"
RNG_IDENTITY = "PYTHON_RANDOM_MT19937_RANDOM_SEQUENCE_V1"

TEST_PAIRED_T = "PAIRED_T"
TEST_SIGN = "SIGN_TEST"
TEST_WILCOXON = "WILCOXON_SIGNED_RANK"
TEST_FAMILIES = (TEST_PAIRED_T, TEST_SIGN, TEST_WILCOXON)

ASSUMPTION_LICENSE_PAIRED_T = "PAIRED_T_SYMMETRY_OR_NORMALITY_LICENSED"
ASSUMPTION_LICENSE_SIGN = "SIGN_TEST_WITHIN_PAIR_EXCHANGEABILITY_LICENSED"
ASSUMPTION_LICENSE_WILCOXON = "WILCOXON_SYMMETRIC_DIFFERENCES_LICENSED"
REQUIRED_LICENSE = {
    TEST_PAIRED_T: ASSUMPTION_LICENSE_PAIRED_T,
    TEST_SIGN: ASSUMPTION_LICENSE_SIGN,
    TEST_WILCOXON: ASSUMPTION_LICENSE_WILCOXON,
}

ALTERNATIVE_TWO_SIDED = "two-sided"
ALTERNATIVE_GREATER = "greater"
ALTERNATIVE_LESS = "less"
ALTERNATIVES = (ALTERNATIVE_TWO_SIDED, ALTERNATIVE_GREATER, ALTERNATIVE_LESS)

TEST_STATUS_ESTIMABLE = "ESTIMABLE"
TEST_STATUS_NOT_ESTIMABLE = "NOT_ESTIMABLE"
TEST_REASON_INSUFFICIENT_PAIRS = "TEST_NOT_ESTIMABLE_INSUFFICIENT_PAIRS"
TEST_REASON_ZERO_DISPERSION = "TEST_NOT_ESTIMABLE_ZERO_DISPERSION"
TEST_REASON_ASSUMPTION_LICENSE = "ASSUMPTION_LICENSE_MISSING"
TEST_REASON_FALLBACK_LICENSE = "FALLBACK_ASSUMPTION_LICENSE_MISSING"
TEST_REASON_FALLBACK_EVIDENCE = "FALLBACK_EVIDENCE_MISSING"
TEST_REASON_FREEZE_ID = "METHOD_FREEZE_ID_REQUIRED"
TEST_REASON_DECLARATION = "TEST_DECLARATION_INVALID"
CLAIM_BOUNDARY = "TEST_STATISTIC_ONLY_NOT_A_PHYSICAL_CLAIM"

WILCOXON_EXACT_MAX_N = 16


class W22InferenceError(W22StatisticsError):
    """An inferential request violates the frozen statistical contract."""


@dataclass(frozen=True)
class IntervalEstimate:
    """One interval estimate; exactly one primary is allowed per outcome."""

    method: str
    confidence_level: float
    status: str
    role: str
    statistic: str
    evidence_label: str
    pair_count: int
    point_estimate: float | None = None
    lower: float | None = None
    upper: float | None = None
    standard_error: float | None = None
    degrees_of_freedom: int | None = None
    critical_value: float | None = None
    constant_value: float | None = None
    iterations: int | None = None
    seed: int | None = None
    resampling_unit: str | None = None
    rng_name: str | None = None
    quantile_convention: str = QUANTILE_CONVENTION
    research_grade: bool = False
    reason_code: str | None = None
    draw_digest: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TestDeclaration:
    """Predeclared method freeze; fallbacks require a declared reason."""

    preferred_test_family: str
    method_freeze_id: str
    assumption_licenses: tuple[str, ...]
    alternative: str = ALTERNATIVE_TWO_SIDED
    fallback_test_family: str | None = None
    fallback_reason_code: str | None = None


@dataclass(frozen=True)
class IntervalDeclaration:
    """Predeclared primary CI method; a second method is sensitivity only."""

    primary_method: str
    confidence_level: float
    method_freeze_id: str


@dataclass(frozen=True)
class PairedTestResult:
    """A single predeclared paired test result."""

    family: str
    method_freeze_id: str
    alternative: str
    status: str
    evidence_label: str
    pair_count: int
    statistic: float | None = None
    p_value: float | None = None
    direction_count: int | None = None
    degrees_of_freedom: int | None = None
    non_zero_pairs: int | None = None
    zero_differences: int | None = None
    exact: bool | None = None
    fallback_applied: bool = False
    fallback_family: str | None = None
    fallback_reason_code: str | None = None
    preferred_failure_reason: str | None = None
    reason_code: str | None = None
    claim_boundary: str = CLAIM_BOUNDARY
    notes: tuple[str, ...] = ()


def _betacf(a: float, b: float, x: float) -> float:
    max_iterations = 300
    epsilon = 3.0e-14
    tiny = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, max_iterations + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < epsilon:
            break
    return h


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    front = math.exp(log_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_cdf(t: float, degrees_of_freedom: int) -> float:
    """Student-t cumulative distribution (two-sided symmetric)."""
    if degrees_of_freedom < 1:
        raise W22InferenceError(
            TEST_REASON_DECLARATION, "degrees_of_freedom must be >= 1"
        )
    if not math.isfinite(t):
        raise W22InferenceError(
            TEST_REASON_DECLARATION, "t must be finite in student_t_cdf"
        )
    x = degrees_of_freedom / (degrees_of_freedom + t * t)
    tail = 0.5 * _regularized_incomplete_beta(degrees_of_freedom / 2.0, 0.5, x)
    return 1.0 - tail if t >= 0.0 else tail


def student_t_critical(probability: float, degrees_of_freedom: int) -> float:
    """Upper-tail Student-t critical value via deterministic bisection."""
    if degrees_of_freedom < 1:
        raise W22InferenceError(
            TEST_REASON_DECLARATION, "degrees_of_freedom must be >= 1"
        )
    if not 0.5 < probability < 1.0:
        raise W22InferenceError(
            TEST_REASON_DECLARATION, "probability must lie in (0.5, 1)"
        )
    low = 0.0
    high = 1.0
    while student_t_cdf(high, degrees_of_freedom) < probability:
        high *= 2.0
        if high > 1.0e9:
            raise W22InferenceError(
                TEST_REASON_DECLARATION, "student-t critical value did not converge"
            )
    for _ in range(200):
        middle = (low + high) / 2.0
        if student_t_cdf(middle, degrees_of_freedom) < probability:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _sample_sd(values: Sequence[float], mean_value: float) -> float:
    return math.sqrt(
        math.fsum((value - mean_value) ** 2 for value in values)
        / (len(values) - 1)
    )


def paired_t_interval(
    dataset: PairedDataset,
    *,
    confidence_level: float = 0.95,
    role: str = INTERVAL_ROLE_PRIMARY,
) -> IntervalEstimate:
    """Canonical paired t interval: mean ± t(0.975, n-1)·s/√n."""
    if role not in (INTERVAL_ROLE_PRIMARY, INTERVAL_ROLE_SENSITIVITY):
        raise W22InferenceError(REASON_PRIMARY_ROLE, f"unknown role {role!r}")
    if confidence_level != FROZEN_CONFIDENCE_LEVEL:
        raise W22InferenceError(
            REASON_CONFIDENCE_LEVEL,
            f"only the frozen {FROZEN_CONFIDENCE_LEVEL:.0%} level is supported",
        )
    values = list(dataset.improvements)
    count = len(values)
    evidence = dataset.evidence_label
    if count < MIN_PAIRS_FOR_INFERENCE:
        return IntervalEstimate(
            method=METHOD_PAIRED_T_INTERVAL,
            confidence_level=confidence_level,
            status=STATUS_NOT_ESTIMABLE,
            role=role,
            statistic=BOOTSTRAP_STATISTIC_MEAN,
            evidence_label=evidence,
            pair_count=count,
            reason_code=REASON_INSUFFICIENT_PAIRS,
            research_grade=False,
            notes=("N_BELOW_APPROVED_INFERENTIAL_MINIMUM",),
        )
    mean_value = _mean(values)
    sd_value = _sample_sd(values, mean_value)
    if sd_value == 0.0:
        return IntervalEstimate(
            method=METHOD_PAIRED_T_INTERVAL,
            confidence_level=confidence_level,
            status=STATUS_NOT_ESTIMABLE,
            role=role,
            statistic=BOOTSTRAP_STATISTIC_MEAN,
            evidence_label=evidence,
            pair_count=count,
            point_estimate=mean_value,
            constant_value=mean_value,
            reason_code=REASON_ZERO_DISPERSION,
            research_grade=False,
            notes=("CONSTANT_DIFFERENCES_CI_UNDEFINED_NOT_PERFECT_CERTAINTY",),
        )
    degrees = count - 1
    critical = student_t_critical(1.0 - (1.0 - confidence_level) / 2.0, degrees)
    standard_error = sd_value / math.sqrt(count)
    margin = critical * standard_error
    return IntervalEstimate(
        method=METHOD_PAIRED_T_INTERVAL,
        confidence_level=confidence_level,
        status=STATUS_ESTIMABLE,
        role=role,
        statistic=BOOTSTRAP_STATISTIC_MEAN,
        evidence_label=evidence,
        pair_count=count,
        point_estimate=mean_value,
        lower=mean_value - margin,
        upper=mean_value + margin,
        standard_error=standard_error,
        degrees_of_freedom=degrees,
        critical_value=critical,
        research_grade=True,
    )


def _bootstrap_draws(
    values: Sequence[float],
    *,
    statistic: str,
    seed: int,
    iterations: int,
) -> tuple[list[float], str]:
    generator = random.Random(seed)
    count = len(values)
    draws: list[float] = []
    for _ in range(iterations):
        sample = [values[int(generator.random() * count)] for _ in range(count)]
        draws.append(
            math.fsum(sample) / count
            if statistic == BOOTSTRAP_STATISTIC_MEAN
            else _median(sample)
        )
    digest = hashlib.sha256()
    for draw in draws:
        digest.update(format(draw, ".17g").encode("ascii") + b"\n")
    return draws, digest.hexdigest()


def bootstrap_percentile_interval(
    dataset: PairedDataset,
    *,
    seed: int,
    iterations: int = BOOTSTRAP_DEFAULT_ITERATIONS,
    confidence_level: float = 0.95,
    statistic: str = BOOTSTRAP_STATISTIC_MEAN,
    role: str = INTERVAL_ROLE_PRIMARY,
    test_only_settings: bool = False,
) -> IntervalEstimate:
    """Deterministic complete-pair percentile bootstrap (never arm-wise)."""
    if role not in (INTERVAL_ROLE_PRIMARY, INTERVAL_ROLE_SENSITIVITY):
        raise W22InferenceError(REASON_PRIMARY_ROLE, f"unknown role {role!r}")
    if statistic not in (BOOTSTRAP_STATISTIC_MEAN, BOOTSTRAP_STATISTIC_MEDIAN):
        raise W22InferenceError(REASON_UNKNOWN_STATISTIC, f"unknown {statistic!r}")
    if seed is None or isinstance(seed, bool) or not isinstance(seed, int):
        return IntervalEstimate(
            method=METHOD_BOOTSTRAP_PERCENTILE,
            confidence_level=confidence_level,
            status=STATUS_NOT_ESTIMABLE,
            role=role,
            statistic=statistic,
            evidence_label=dataset.evidence_label,
            pair_count=dataset.pair_count,
            iterations=iterations,
            seed=None,
            reason_code=REASON_BOOTSTRAP_SEED_REQUIRED,
            research_grade=False,
            notes=("A_FIXED_RECORDED_SEED_IS_MANDATORY",),
        )
    if not 0.5 < confidence_level < 1.0:
        raise W22InferenceError(
            TEST_REASON_DECLARATION, "confidence_level must lie in (0.5, 1)"
        )
    if confidence_level != FROZEN_CONFIDENCE_LEVEL:
        raise W22InferenceError(
            REASON_CONFIDENCE_LEVEL,
            f"only the frozen {FROZEN_CONFIDENCE_LEVEL:.0%} level is supported",
        )
    if iterations < 1 or iterations > BOOTSTRAP_MAX_ITERATIONS:
        raise W22InferenceError(
            TEST_REASON_DECLARATION,
            f"iterations must lie in [1, {BOOTSTRAP_MAX_ITERATIONS}]",
        )
    values = list(dataset.improvements)
    count = len(values)
    if count < MIN_PAIRS_FOR_INFERENCE:
        return IntervalEstimate(
            method=METHOD_BOOTSTRAP_PERCENTILE,
            confidence_level=confidence_level,
            status=STATUS_NOT_ESTIMABLE,
            role=role,
            statistic=statistic,
            evidence_label=dataset.evidence_label,
            pair_count=count,
            iterations=iterations,
            seed=seed,
            reason_code=REASON_INSUFFICIENT_PAIRS,
            research_grade=False,
        )
    if len(set(values)) == 1:
        return IntervalEstimate(
            method=METHOD_BOOTSTRAP_PERCENTILE,
            confidence_level=confidence_level,
            status=STATUS_NOT_ESTIMABLE,
            role=role,
            statistic=statistic,
            evidence_label=dataset.evidence_label,
            pair_count=count,
            iterations=iterations,
            seed=seed,
            constant_value=values[0],
            reason_code=REASON_ZERO_DISPERSION,
            research_grade=False,
            notes=("CONSTANT_DIFFERENCES_CI_UNDEFINED_NOT_PERFECT_CERTAINTY",),
        )
    research_grade = iterations >= BOOTSTRAP_MIN_ITERATIONS and not test_only_settings
    if not research_grade:
        if iterations < BOOTSTRAP_MIN_ITERATIONS and not test_only_settings:
            return IntervalEstimate(
                method=METHOD_BOOTSTRAP_PERCENTILE,
                confidence_level=confidence_level,
                status=STATUS_NOT_ESTIMABLE,
                role=role,
                statistic=statistic,
                evidence_label=dataset.evidence_label,
                pair_count=count,
                iterations=iterations,
                seed=seed,
                reason_code=REASON_BOOTSTRAP_ITERATIONS,
                research_grade=False,
                notes=(
                    f"FROZEN_MINIMUM_IS_{BOOTSTRAP_MIN_ITERATIONS}_ITERATIONS",
                ),
            )
    draws, digest = _bootstrap_draws(
        values, statistic=statistic, seed=seed, iterations=iterations
    )
    if len(set(draws)) == 1:
        return IntervalEstimate(
            method=METHOD_BOOTSTRAP_PERCENTILE,
            confidence_level=confidence_level,
            status=STATUS_NOT_ESTIMABLE,
            role=role,
            statistic=statistic,
            evidence_label=dataset.evidence_label,
            pair_count=count,
            iterations=iterations,
            seed=seed,
            constant_value=draws[0],
            reason_code=REASON_BOOTSTRAP_COLLAPSE,
            research_grade=False,
            notes=("BOOTSTRAP_DISTRIBUTION_DEGENERATE",),
        )
    alpha = 1.0 - confidence_level
    lower = quantile_type7(draws, alpha / 2.0)
    upper = quantile_type7(draws, 1.0 - alpha / 2.0)
    notes = [] if research_grade else ["IMPLEMENTATION_TEST_SETTINGS_NOT_FINAL_RESEARCH_SETTINGS"]
    return IntervalEstimate(
        method=METHOD_BOOTSTRAP_PERCENTILE,
        confidence_level=confidence_level,
        status=STATUS_ESTIMABLE,
        role=role,
        statistic=statistic,
        evidence_label=dataset.evidence_label,
        pair_count=count,
        point_estimate=_mean(draws),
        lower=lower,
        upper=upper,
        iterations=iterations,
        seed=seed,
        resampling_unit=RESAMPLING_UNIT_COMPLETE_PAIRS,
        rng_name=RNG_IDENTITY,
        research_grade=research_grade,
        draw_digest=digest,
        notes=tuple(notes),
    )


def predeclare_interval_method(
    *,
    primary_method: str,
    method_freeze_id: str,
    confidence_level: float = FROZEN_CONFIDENCE_LEVEL,
) -> IntervalDeclaration:
    """Freeze exactly one primary interval method before seeing outcomes."""
    if primary_method not in INTERVAL_METHODS:
        raise W22InferenceError(
            REASON_INTERVAL_DECLARATION,
            f"unknown primary interval method {primary_method!r}",
        )
    if not isinstance(method_freeze_id, str) or not method_freeze_id.strip():
        raise W22InferenceError(
            REASON_INTERVAL_DECLARATION, "method_freeze_id is required"
        )
    if confidence_level != FROZEN_CONFIDENCE_LEVEL:
        raise W22InferenceError(
            REASON_CONFIDENCE_LEVEL,
            f"only the frozen {FROZEN_CONFIDENCE_LEVEL:.0%} level is supported",
        )
    return IntervalDeclaration(
        primary_method=primary_method,
        confidence_level=confidence_level,
        method_freeze_id=method_freeze_id.strip(),
    )


def resolve_primary_interval(
    *,
    primary: IntervalEstimate,
    sensitivity: IntervalEstimate,
    declaration: IntervalDeclaration,
) -> IntervalEstimate:
    """Return the predeclared primary interval; never the narrower one."""
    if not isinstance(declaration, IntervalDeclaration):
        raise W22InferenceError(
            REASON_INTERVAL_DECLARATION,
            "a frozen IntervalDeclaration is required",
        )
    if primary.role != INTERVAL_ROLE_PRIMARY:
        raise W22InferenceError(
            REASON_PRIMARY_NOT_DECLARED,
            "the supplied primary interval is not labelled PRIMARY",
        )
    if sensitivity.role != INTERVAL_ROLE_SENSITIVITY:
        raise W22InferenceError(
            REASON_MULTIPLE_PRIMARY,
            "the second interval must be labelled SENSITIVITY",
        )
    if primary.method != declaration.primary_method:
        raise W22InferenceError(
            REASON_INTERVAL_MISMATCH,
            f"primary method {primary.method!r} does not match the declared "
            f"{declaration.primary_method!r}",
        )
    if primary.confidence_level != declaration.confidence_level:
        raise W22InferenceError(
            REASON_INTERVAL_MISMATCH,
            "primary confidence level does not match the declaration",
        )
    if primary.method == sensitivity.method:
        raise W22InferenceError(
            REASON_PRIMARY_NOT_DECLARED,
            "primary and sensitivity must be different methods",
        )
    return primary


def assert_single_primary(intervals: Sequence[IntervalEstimate]) -> IntervalEstimate:
    primaries = [item for item in intervals if item.role == INTERVAL_ROLE_PRIMARY]
    if len(primaries) != 1:
        raise W22InferenceError(
            REASON_MULTIPLE_PRIMARY,
            f"expected exactly one primary interval, found {len(primaries)}",
        )
    return primaries[0]


def predeclare_test(
    *,
    preferred_test_family: str,
    method_freeze_id: str,
    assumption_licenses: Sequence[str],
    alternative: str = ALTERNATIVE_TWO_SIDED,
    fallback_test_family: str | None = None,
    fallback_reason_code: str | None = None,
) -> TestDeclaration:
    """Validate a predeclared method freeze before any outcome is observed."""
    if preferred_test_family not in TEST_FAMILIES:
        raise W22InferenceError(
            TEST_REASON_DECLARATION,
            f"unknown preferred_test_family {preferred_test_family!r}",
        )
    if not isinstance(method_freeze_id, str) or not method_freeze_id.strip():
        raise W22InferenceError(TEST_REASON_FREEZE_ID, "method_freeze_id is required")
    if alternative not in ALTERNATIVES:
        raise W22InferenceError(
            TEST_REASON_DECLARATION, f"unknown alternative {alternative!r}"
        )
    licenses = tuple(dict.fromkeys(str(item) for item in assumption_licenses))
    if fallback_test_family is None and fallback_reason_code is not None:
        raise W22InferenceError(
            TEST_REASON_DECLARATION,
            "fallback_reason_code requires a fallback_test_family",
        )
    if fallback_test_family is not None:
        if fallback_test_family not in TEST_FAMILIES:
            raise W22InferenceError(
                TEST_REASON_DECLARATION,
                f"unknown fallback_test_family {fallback_test_family!r}",
            )
        if fallback_test_family == preferred_test_family:
            raise W22InferenceError(
                TEST_REASON_DECLARATION, "fallback must differ from the primary method"
            )
        if not isinstance(fallback_reason_code, str) or not fallback_reason_code.strip():
            raise W22InferenceError(
                TEST_REASON_DECLARATION,
                "a fallback requires its predeclared reason code",
            )
    return TestDeclaration(
        preferred_test_family=preferred_test_family,
        method_freeze_id=method_freeze_id.strip(),
        assumption_licenses=licenses,
        alternative=alternative,
        fallback_test_family=fallback_test_family,
        fallback_reason_code=(
            fallback_reason_code.strip() if fallback_reason_code else None
        ),
    )


def _paired_t_test(
    values: Sequence[float], alternative: str
) -> tuple[float | None, float | None, int | None, str | None]:
    count = len(values)
    if count < MIN_PAIRS_FOR_INFERENCE:
        return None, None, None, TEST_REASON_INSUFFICIENT_PAIRS
    mean_value = _mean(values)
    sd_value = _sample_sd(values, mean_value)
    if sd_value == 0.0:
        return None, None, None, TEST_REASON_ZERO_DISPERSION
    degrees = count - 1
    statistic = mean_value / (sd_value / math.sqrt(count))
    if alternative == ALTERNATIVE_TWO_SIDED:
        p_value = 2.0 * (1.0 - student_t_cdf(abs(statistic), degrees))
    elif alternative == ALTERNATIVE_GREATER:
        p_value = 1.0 - student_t_cdf(statistic, degrees)
    else:
        p_value = student_t_cdf(statistic, degrees)
    return statistic, min(1.0, max(0.0, p_value)), degrees, None


def _sign_test(
    values: Sequence[float], alternative: str
) -> tuple[int, float, int, int]:
    positive = sum(1 for value in values if value > 0)
    negative = sum(1 for value in values if value < 0)
    zeros = len(values) - positive - negative
    non_zero = positive + negative
    if non_zero == 0:
        return 0, 1.0, 0, zeros
    denominator = Fraction(1, 2**non_zero)
    if alternative == ALTERNATIVE_TWO_SIDED:
        tail = sum(
            math.comb(non_zero, index)
            for index in range(0, min(positive, negative) + 1)
        )
        p_value = float(min(Fraction(1, 1), 2 * tail * denominator))
    elif alternative == ALTERNATIVE_GREATER:
        tail = sum(
            math.comb(non_zero, index) for index in range(positive, non_zero + 1)
        )
        p_value = float(tail * denominator)
    else:
        tail = sum(
            math.comb(non_zero, index) for index in range(0, positive + 1)
        )
        p_value = float(tail * denominator)
    return positive, min(1.0, max(0.0, p_value)), non_zero, zeros


def _average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (abs(values[index]), index))
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and abs(values[order[end + 1]]) == abs(
            values[order[position]]
        ):
            end += 1
        average = (position + 1 + end + 1) / 2.0
        for index in range(position, end + 1):
            ranks[order[index]] = average
        position = end + 1
    return ranks


def _wilcoxon_exact_p(rank_twos: Sequence[int], observed_twos: int) -> float:
    distribution = {0: 1}
    for rank in rank_twos:
        updated: dict[int, int] = {}
        for total, count in distribution.items():
            updated[total] = updated.get(total, 0) + count
            updated[total + rank] = updated.get(total + rank, 0) + count
        distribution = updated
    assignments = 2 ** len(rank_twos)
    lower = sum(
        count for total, count in distribution.items() if total <= observed_twos
    )
    upper = sum(
        count for total, count in distribution.items() if total >= observed_twos
    )
    return min(1.0, 2.0 * float(min(Fraction(lower, assignments), Fraction(upper, assignments))))


def _wilcoxon_test(
    values: Sequence[float], alternative: str
) -> tuple[float | None, float | None, int, int, bool | None, str | None]:
    """Wilcoxon signed-rank with explicit zero and tie conventions.

    Zero differences are dropped and reported.  Ties use midranks and the
    exact sign-flip permutation distribution of the observed midranks
    (n_eff <= 16); above that the normal approximation uses the tie
    correction and a continuity correction.  The reported statistic is W+
    in rank units.
    """
    non_zero_values = [value for value in values if value != 0.0]
    zeros = len(values) - len(non_zero_values)
    non_zero = len(non_zero_values)
    if non_zero == 0:
        return 0.0, 1.0, 0, zeros, True, None
    ranks = _average_ranks(non_zero_values)
    rank_twos = [int(round(rank * 2)) for rank in ranks]
    positive_twos = sum(
        rank_two
        for rank_two, value in zip(rank_twos, non_zero_values)
        if value > 0
    )
    if non_zero <= WILCOXON_EXACT_MAX_N:
        exact = True
        if alternative == ALTERNATIVE_TWO_SIDED:
            p_value = _wilcoxon_exact_p(rank_twos, positive_twos)
        else:
            distribution = {0: 1}
            for rank in rank_twos:
                updated: dict[int, int] = {}
                for total, count in distribution.items():
                    updated[total] = updated.get(total, 0) + count
                    updated[total + rank] = updated.get(total + rank, 0) + count
                distribution = updated
            assignments = 2**non_zero
            if alternative == ALTERNATIVE_GREATER:
                tail = sum(
                    count
                    for total, count in distribution.items()
                    if total >= positive_twos
                )
            else:
                tail = sum(
                    count
                    for total, count in distribution.items()
                    if total <= positive_twos
                )
            p_value = float(Fraction(tail, assignments))
    else:
        exact = False
        mean_w = non_zero * (non_zero + 1) / 4.0
        tie_counts: dict[float, int] = {}
        for rank in ranks:
            tie_counts[rank] = tie_counts.get(rank, 0) + 1
        tie_correction = sum(
            count**3 - count for count in tie_counts.values() if count > 1
        )
        variance = (
            non_zero * (non_zero + 1) * (2 * non_zero + 1) / 24.0
            - tie_correction / 48.0
        )
        statistic_rank = positive_twos / 2.0
        if variance <= 0.0:
            p_value = 1.0
        else:
            z_value = (abs(statistic_rank - mean_w) - 0.5) / math.sqrt(variance)
            z_value = max(0.0, z_value)
            if alternative == ALTERNATIVE_TWO_SIDED:
                p_value = 2.0 * (1.0 - _standard_normal_cdf(z_value))
            elif alternative == ALTERNATIVE_GREATER:
                z_value = (statistic_rank - mean_w - 0.5) / math.sqrt(variance)
                p_value = 1.0 - _standard_normal_cdf(z_value)
            else:
                z_value = (statistic_rank - mean_w + 0.5) / math.sqrt(variance)
                p_value = _standard_normal_cdf(z_value)
    statistic = positive_twos / 2.0
    return statistic, min(1.0, max(0.0, p_value)), non_zero, zeros, exact, None


def _standard_normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _run_family(
    dataset: PairedDataset, family: str, alternative: str
) -> PairedTestResult:
    values = list(dataset.improvements)
    if family == TEST_PAIRED_T:
        statistic, p_value, degrees, failure = _paired_t_test(values, alternative)
        if failure is not None:
            return PairedTestResult(
                family=family,
                method_freeze_id="",
                alternative=alternative,
                status=TEST_STATUS_NOT_ESTIMABLE,
                evidence_label=dataset.evidence_label,
                pair_count=len(values),
                reason_code=failure,
            )
        return PairedTestResult(
            family=family,
            method_freeze_id="",
            alternative=alternative,
            status=TEST_STATUS_ESTIMABLE,
            evidence_label=dataset.evidence_label,
            pair_count=len(values),
            statistic=statistic,
            p_value=p_value,
            degrees_of_freedom=degrees,
        )
    if family == TEST_SIGN:
        positive, p_value, non_zero, zeros = _sign_test(values, alternative)
        return PairedTestResult(
            family=family,
            method_freeze_id="",
            alternative=alternative,
            status=TEST_STATUS_ESTIMABLE,
            evidence_label=dataset.evidence_label,
            pair_count=len(values),
            statistic=float(positive),
            p_value=p_value,
            direction_count=positive,
            non_zero_pairs=non_zero,
            zero_differences=zeros,
        )
    statistic, p_value, non_zero, zeros, exact, failure = _wilcoxon_test(
        values, alternative
    )
    if failure is not None:
        return PairedTestResult(
            family=family,
            method_freeze_id="",
            alternative=alternative,
            status=TEST_STATUS_NOT_ESTIMABLE,
            evidence_label=dataset.evidence_label,
            pair_count=len(values),
            reason_code=failure,
        )
    return PairedTestResult(
        family=family,
        method_freeze_id="",
        alternative=alternative,
        status=TEST_STATUS_ESTIMABLE,
        evidence_label=dataset.evidence_label,
        pair_count=len(values),
        statistic=statistic,
        p_value=p_value,
        non_zero_pairs=non_zero,
        zero_differences=zeros,
        exact=exact,
    )


def run_predeclared_test(
    dataset: PairedDataset,
    declaration: TestDeclaration,
    *,
    fallback_evidence: str | None = None,
) -> PairedTestResult:
    """Run exactly the predeclared test; never select by smallest p-value."""
    if declaration.preferred_test_family not in TEST_FAMILIES:
        raise W22InferenceError(
            TEST_REASON_DECLARATION, "declaration names an unknown family"
        )
    if declaration.alternative not in ALTERNATIVES:
        raise W22InferenceError(
            TEST_REASON_DECLARATION,
            f"declaration names an unknown alternative {declaration.alternative!r}",
        )
    if not declaration.method_freeze_id:
        raise W22InferenceError(TEST_REASON_FREEZE_ID, "method_freeze_id is required")
    required = REQUIRED_LICENSE[declaration.preferred_test_family]
    if required not in declaration.assumption_licenses:
        return PairedTestResult(
            family=declaration.preferred_test_family,
            method_freeze_id=declaration.method_freeze_id,
            alternative=declaration.alternative,
            status=TEST_STATUS_NOT_ESTIMABLE,
            evidence_label=dataset.evidence_label,
            pair_count=dataset.pair_count,
            reason_code=TEST_REASON_ASSUMPTION_LICENSE,
        )
    result = _run_family(
        dataset, declaration.preferred_test_family, declaration.alternative
    )
    result = replace(result, method_freeze_id=declaration.method_freeze_id)
    if result.status == TEST_STATUS_ESTIMABLE:
        return result
    declared_fallback = declaration.fallback_test_family
    if declared_fallback is None or declaration.fallback_reason_code != result.reason_code:
        return result
    if not fallback_evidence or not fallback_evidence.strip():
        return replace(
            result,
            reason_code=TEST_REASON_FALLBACK_EVIDENCE,
            preferred_failure_reason=result.reason_code,
        )
    fallback_required = REQUIRED_LICENSE[declared_fallback]
    if fallback_required not in declaration.assumption_licenses:
        return replace(
            result,
            reason_code=TEST_REASON_FALLBACK_LICENSE,
            preferred_failure_reason=result.reason_code,
        )
    fallback = _run_family(dataset, declared_fallback, declaration.alternative)
    return replace(
        fallback,
        method_freeze_id=declaration.method_freeze_id,
        fallback_applied=True,
        fallback_family=declared_fallback,
        fallback_reason_code=declaration.fallback_reason_code,
        preferred_failure_reason=result.reason_code,
        notes=(
            "PREDECLARED_FALLBACK_APPLIED",
            f"EVIDENCE={fallback_evidence.strip()}",
        ),
    )
