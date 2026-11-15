"""W22 bounded sensitivity analysis (Layer A, test-only statistics).

Canonical anchors: Doc 03 sections 83-84; Doc 05B section 50.  Sensitivity
discloses how conclusions depend on defensible analytical choices.  The
primary analysis always retains every valid pair; a leave-one-pair-out run
is derived evidence labelled ``SENSITIVITY_ONLY_NOT_PRIMARY`` and can never
replace or mutate the primary result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .w22_paired_statistics import (
    W22BoundaryError,
    W22StatisticsError,
    PairedDataset,
    PairedDescriptive,
    describe_pairs,
)
from .w22_uncertainty import (
    INTERVAL_ROLE_PRIMARY,
    INTERVAL_ROLE_SENSITIVITY,
    IntervalDeclaration,
    IntervalEstimate,
    W22InferenceError,
)

W22_SENSITIVITY_LAYER_VERSION = "coldguard-w22-sensitivity-v1"

SENSITIVITY_STATUS_PREDECLARED = "PREDECLARED"
SENSITIVITY_STATUS_EXPLORATORY = "EXPLORATORY"
SENSITIVITY_STATUSES = (
    SENSITIVITY_STATUS_PREDECLARED,
    SENSITIVITY_STATUS_EXPLORATORY,
)

KIND_MEAN_VS_MEDIAN = "MEAN_VS_MEDIAN"
KIND_LEAVE_ONE_PAIR_OUT = "LEAVE_ONE_PAIR_OUT"
KIND_EXTREME_PAIR_INFLUENCE = "EXTREME_PAIR_INFLUENCE"
KIND_BOOTSTRAP_VS_PARAMETRIC = "BOOTSTRAP_VS_PARAMETRIC"
KIND_SECONDARY_OUTCOME = "SECONDARY_OUTCOME_CONTRAST"

LABEL_SENSITIVITY_ONLY = "SENSITIVITY_ONLY_NOT_PRIMARY"
LABEL_SECONDARY_ONLY = "SECONDARY_OUTCOME_NOT_PRIMARY"

REASON_PREDECLARED_NEEDS_PLAN = "PREDECLARED_SENSITIVITY_REQUIRES_PLAN_REFERENCE"
REASON_UNKNOWN_PAIR = "UNKNOWN_PAIR_ID"
REASON_HORIZON_NOT_FROZEN = "HORIZON_SENSITIVITY_REQUIRES_FROZEN_MODEL_EVIDENCE"
REASON_SECONDARY_ROLE = "SECONDARY_CONTRAST_REQUIRES_SECONDARY_OUTCOME"
REASON_SECONDARY_SAME_OUTCOME = "SECONDARY_CONTRAST_OUTCOME_MUST_DIFFER"
REASON_PRIMARY_MUTATED = "PRIMARY_RESULT_MUTATED_BY_SENSITIVITY"

INTERPRETATION_BOUNDARY_LOO = (
    "Sensitivity only. The primary analysis retains all valid pairs; "
    "omitting a pair is neither an invalidation nor a significance-driven "
    "exclusion, and a legitimate extreme pair cannot be dropped from the "
    "primary result."
)
INTERPRETATION_BOUNDARY_STATISTIC = (
    "Sensitivity only. The predeclared primary statistic is unchanged; this "
    "alternative statistic may not be promoted after inspecting outcomes."
)
INTERVAL_SELECTION_RULE = "PREDECLARED_NO_FAVORABILITY_OR_WIDTH_SELECTION"


@dataclass(frozen=True)
class SensitivityResult:
    """One labelled sensitivity computation derived from the primary data."""

    sensitivity_id: str
    outcome_id: str
    kind: str
    declared_status: str
    plan_reference: str | None
    statistic: str
    statistic_value: float | None
    primary_statistic: str
    primary_value: float | None
    valid_n: int
    primary_n: int
    omitted_pair_ids: tuple[str, ...]
    difference_from_primary: float | None
    label: str
    promotion_allowed: bool
    evidence_label: str
    interpretation_boundary: str
    shared_pair_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntervalComparison:
    """Primary versus sensitivity interval labelling (no width selection)."""

    outcome_id: str
    primary_method: str
    sensitivity_method: str
    primary_lower: float | None
    primary_upper: float | None
    sensitivity_lower: float | None
    sensitivity_upper: float | None
    selection_rule: str
    label: str
    promotion_allowed: bool


def _resolve_status(
    declared_status: str, plan_reference: str | None
) -> str:
    if declared_status not in SENSITIVITY_STATUSES:
        raise W22StatisticsError(
            REASON_PREDECLARED_NEEDS_PLAN,
            f"unknown sensitivity status {declared_status!r}",
        )
    if declared_status == SENSITIVITY_STATUS_PREDECLARED:
        if not isinstance(plan_reference, str) or not plan_reference.strip():
            raise W22StatisticsError(
                REASON_PREDECLARED_NEEDS_PLAN,
                "a PREDECLARED sensitivity requires a frozen plan reference; "
                "otherwise it is EXPLORATORY",
            )
        return plan_reference.strip()
    return plan_reference.strip() if plan_reference else None


def _mean_for_pairs(dataset: PairedDataset, omitted: Sequence[str]) -> float | None:
    remaining = [
        improvement
        for pair, improvement in zip(dataset.pairs, dataset.improvements)
        if pair.pair_id not in omitted
    ]
    if not remaining:
        return None
    return math.fsum(remaining) / len(remaining)


def _loo_result(
    dataset: PairedDataset,
    descriptive: PairedDescriptive,
    omitted: str,
    *,
    kind: str,
    declared_status: str,
    plan_reference: str | None,
    sensitivity_id: str,
) -> SensitivityResult:
    reference = _resolve_status(declared_status, plan_reference)
    if omitted not in descriptive.pair_ids:
        raise W22StatisticsError(
            REASON_UNKNOWN_PAIR, f"pair {omitted!r} is not admitted"
        )
    value = _mean_for_pairs(dataset, (omitted,))
    difference = (
        None if value is None else value - float(descriptive.mean_improvement)
    )
    return SensitivityResult(
        sensitivity_id=sensitivity_id,
        outcome_id=dataset.outcome_id,
        kind=kind,
        declared_status=declared_status,
        plan_reference=reference,
        statistic="MEAN_WITHOUT_ONE_PAIR",
        statistic_value=value,
        primary_statistic="MEAN_ALL_VALID_PAIRS",
        primary_value=descriptive.mean_improvement,
        valid_n=descriptive.pair_count - 1,
        primary_n=descriptive.pair_count,
        omitted_pair_ids=(omitted,),
        difference_from_primary=difference,
        label=LABEL_SENSITIVITY_ONLY,
        promotion_allowed=False,
        evidence_label=dataset.evidence_label,
        interpretation_boundary=INTERPRETATION_BOUNDARY_LOO,
    )


def mean_vs_median(
    dataset: PairedDataset,
    descriptive: PairedDescriptive,
    *,
    declared_status: str = SENSITIVITY_STATUS_EXPLORATORY,
    plan_reference: str | None = None,
) -> SensitivityResult:
    """Alternative central-tendency statistic; primary mean stays primary."""
    reference = _resolve_status(declared_status, plan_reference)
    difference = (
        None
        if descriptive.median_improvement is None
        else descriptive.median_improvement - float(descriptive.mean_improvement)
    )
    return SensitivityResult(
        sensitivity_id="SENS-MEAN-VS-MEDIAN",
        outcome_id=dataset.outcome_id,
        kind=KIND_MEAN_VS_MEDIAN,
        declared_status=declared_status,
        plan_reference=reference,
        statistic="MEDIAN",
        statistic_value=descriptive.median_improvement,
        primary_statistic="MEAN",
        primary_value=descriptive.mean_improvement,
        valid_n=descriptive.pair_count,
        primary_n=descriptive.pair_count,
        omitted_pair_ids=(),
        difference_from_primary=difference,
        label=LABEL_SENSITIVITY_ONLY,
        promotion_allowed=False,
        evidence_label=dataset.evidence_label,
        interpretation_boundary=INTERPRETATION_BOUNDARY_STATISTIC,
    )


def leave_one_pair_out(
    dataset: PairedDataset,
    descriptive: PairedDescriptive,
    *,
    omit_pair_ids: Sequence[str] | None = None,
    declared_status: str = SENSITIVITY_STATUS_EXPLORATORY,
    plan_reference: str | None = None,
) -> tuple[SensitivityResult, ...]:
    """One-at-a-time omission summaries; never mutate the primary analysis."""
    targets = (
        list(omit_pair_ids)
        if omit_pair_ids is not None
        else list(descriptive.pair_ids)
    )
    if len(set(targets)) != len(targets):
        raise W22StatisticsError(REASON_UNKNOWN_PAIR, "duplicate omitted pair id")
    return tuple(
        _loo_result(
            dataset,
            descriptive,
            pair_id,
            kind=KIND_LEAVE_ONE_PAIR_OUT,
            declared_status=declared_status,
            plan_reference=plan_reference,
            sensitivity_id=f"SENS-LOO-{pair_id}",
        )
        for pair_id in targets
    )


def extreme_pair_influence(
    dataset: PairedDataset,
    descriptive: PairedDescriptive,
    *,
    declared_status: str = SENSITIVITY_STATUS_EXPLORATORY,
    plan_reference: str | None = None,
) -> SensitivityResult:
    """Leave-one-out for the pair farthest from the primary mean."""
    mean_value = float(descriptive.mean_improvement)
    target = max(
        dataset.pairs,
        key=lambda pair: (
            abs(
                (pair.arm_a.value - pair.arm_b.value) - mean_value
            ),
            pair.pair_id,
        ),
    )
    return _loo_result(
        dataset,
        descriptive,
        target.pair_id,
        kind=KIND_EXTREME_PAIR_INFLUENCE,
        declared_status=declared_status,
        plan_reference=plan_reference,
        sensitivity_id=f"SENS-EXTREME-{target.pair_id}",
    )


def compare_intervals(
    *,
    primary: IntervalEstimate,
    sensitivity: IntervalEstimate,
    declaration: IntervalDeclaration,
) -> IntervalComparison:
    """Label a predeclared primary interval against a sensitivity interval."""
    if not isinstance(declaration, IntervalDeclaration):
        raise W22InferenceError(
            "PRIMARY_INTERVAL_DECLARATION_INVALID",
            "a frozen IntervalDeclaration is required",
        )
    if primary.role != INTERVAL_ROLE_PRIMARY:
        raise W22InferenceError(
            "PRIMARY_INTERVAL_NOT_DECLARED",
            "primary interval must carry the PRIMARY role",
        )
    if sensitivity.role != INTERVAL_ROLE_SENSITIVITY:
        raise W22InferenceError(
            "MULTIPLE_PRIMARY_INTERVALS_REFUSED",
            "sensitivity interval must carry the SENSITIVITY role",
        )
    if primary.method != declaration.primary_method:
        raise W22InferenceError(
            "PRIMARY_INTERVAL_DECLARATION_MISMATCH",
            f"primary method {primary.method!r} does not match the declared "
            f"{declaration.primary_method!r}",
        )
    if primary.method == sensitivity.method:
        raise W22InferenceError(
            "PRIMARY_INTERVAL_NOT_DECLARED",
            "primary and sensitivity intervals must use different methods",
        )
    return IntervalComparison(
        outcome_id="",
        primary_method=primary.method,
        sensitivity_method=sensitivity.method,
        primary_lower=primary.lower,
        primary_upper=primary.upper,
        sensitivity_lower=sensitivity.lower,
        sensitivity_upper=sensitivity.upper,
        selection_rule=INTERVAL_SELECTION_RULE,
        label=LABEL_SENSITIVITY_ONLY,
        promotion_allowed=False,
    )


def secondary_outcome_contrast(
    primary_dataset: PairedDataset,
    secondary_dataset: PairedDataset,
    *,
    declared_status: str = SENSITIVITY_STATUS_EXPLORATORY,
    plan_reference: str | None = None,
) -> SensitivityResult:
    """Approved secondary outcome stays secondary; no post-result promotion."""
    reference = _resolve_status(declared_status, plan_reference)
    if secondary_dataset.outcome_role == "PRIMARY":
        raise W22StatisticsError(
            REASON_SECONDARY_ROLE,
            "a secondary contrast requires a SECONDARY-labelled outcome",
        )
    if secondary_dataset.outcome_id == primary_dataset.outcome_id:
        raise W22StatisticsError(
            REASON_SECONDARY_SAME_OUTCOME,
            "secondary contrast must use a different outcome id",
        )
    secondary = describe_pairs(secondary_dataset)
    primary = describe_pairs(primary_dataset)
    shared = tuple(
        pair_id
        for pair_id in secondary.pair_ids
        if pair_id in set(primary.pair_ids)
    )
    difference = (
        None
        if secondary.mean_improvement is None
        else secondary.mean_improvement - float(primary.mean_improvement)
    )
    paired_scope = (
        "PAIRED_SECONDARY_CONTRAST_SAME_PAIR_SET"
        if shared == secondary.pair_ids == primary.pair_ids
        else "UNPAIRED_DESCRIPTIVE_CONTRAST_ON_DIFFERENT_PAIR_SETS"
    )
    return SensitivityResult(
        sensitivity_id=f"SENS-SECONDARY-{secondary_dataset.outcome_id}",
        outcome_id=secondary_dataset.outcome_id,
        kind=KIND_SECONDARY_OUTCOME,
        declared_status=declared_status,
        plan_reference=reference,
        statistic="SECONDARY_MEAN_IMPROVEMENT",
        statistic_value=secondary.mean_improvement,
        primary_statistic="PRIMARY_MEAN_IMPROVEMENT",
        primary_value=primary.mean_improvement,
        valid_n=secondary.pair_count,
        primary_n=primary.pair_count,
        omitted_pair_ids=(),
        difference_from_primary=difference,
        label=LABEL_SECONDARY_ONLY,
        promotion_allowed=False,
        evidence_label=secondary_dataset.evidence_label,
        interpretation_boundary=(
            "Secondary outcome contrast only. It cannot be promoted to the "
            f"primary result after inspecting outcomes. {paired_scope}."
        ),
        shared_pair_ids=shared,
    )


def refuse_horizon_sensitivity() -> None:
    """W22 implements no prediction-horizon shopping."""
    raise W22BoundaryError(
        REASON_HORIZON_NOT_FROZEN,
        "alternate prediction-horizon sensitivity requires a frozen W13 "
        "primary horizon and scientific evidence; W22 does not implement it",
    )


def assert_primary_intact(
    before: PairedDescriptive, after: PairedDescriptive
) -> None:
    """Guard that a sensitivity computation did not rewrite the primary."""
    if (
        before.pair_count != after.pair_count
        or before.mean_improvement != after.mean_improvement
        or before.pair_ids != after.pair_ids
    ):
        raise W22StatisticsError(
            REASON_PRIMARY_MUTATED,
            "the primary descriptive result changed during sensitivity analysis",
        )
