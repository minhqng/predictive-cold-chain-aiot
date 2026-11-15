"""W14 calibration feasibility, group-safe diagnostics and output decision.

B-W14-03 / B-W14-04. The existence of ``predict_proba`` is not calibration
evidence. Real calibration is blocked while no real predictive-eligible
development population, frozen target and frozen horizon exist. A deterministic
synthetic software control is still run to exercise the methodology:

* one predeclared candidate family (sigmoid only); isotonic is refused when the
  calibration population is below the official ~1000-sample caveat;
* an already-fitted XGBoost model is wrapped in ``FrozenEstimator`` so the
  calibrator is fitted on explicitly disjoint calibration groups;
* the outer validation groups are evaluation-only and never fit the model or
  the calibrator;
* no default ``CalibratedClassifierCV`` CV is used: its internal splitter is
  row-level and cannot be assumed to respect ColdGuard run groups;
* every undefined metric keeps its reason instead of becoming zero.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import average_precision_score, brier_score_loss
from xgboost import XGBClassifier

from .grouped_evaluation import build_evaluation_runs, make_grouped_folds
from .w14_ablation import (
    AblationView,
    SYNTHETIC_SOFTWARE_CONTROL,
    build_ablation_dataset,
    validate_view,
)
from .xgb_benchmark import (
    SOFTWARE_ONLY,
    SOURCE_TYPE_SYNTHETIC,
    SYNTHETIC_PROVENANCE,
    BenchmarkConfig,
    BenchmarkFixture,
    LabeledDataset,
    feature_matrix,
    package_versions,
)

CALIBRATION_SCHEMA = "coldguard-w14-calibration-diagnostics-v1"
CALIBRATION_LAYER_VERSION = "coldguard-w14-group-safe-calibration-v1"

# The exact W11 development model. A calibration experiment that changes any
# parameter is no longer the predeclared model and must refuse.
W11_PREDECLARED_MODEL_PARAMS = {
    "objective": "binary:logistic",
    "tree_method": "hist",
    "max_depth": 3,
    "learning_rate": 0.05,
    "n_estimators": 60,
    "subsample": 1.0,
    "colsample_bytree": 1.0,
    "reg_lambda": 1.0,
    "reg_alpha": 0.0,
    "random_state": 42,
    "n_jobs": 1,
}

DECISION_RISK_SCORE_ONLY = "RISK_SCORE_ONLY"
DECISION_CALIBRATED_PROBABILITY_SUPPORTED = "CALIBRATED_PROBABILITY_SUPPORTED"
DECISION_BLOCKED_BY_CONTRACT = "DECISION_BLOCKED_BY_CONTRACT"

REASON_NO_REAL_POPULATION = "CALIBRATION_BLOCKED_NO_REAL_ELIGIBLE_DEVELOPMENT_POPULATION"
REASON_TARGET_NOT_FROZEN = "CALIBRATION_BLOCKED_TARGET_OR_HORIZON_NOT_FROZEN"
REASON_SYNTHETIC_ONLY = "CALIBRATION_BLOCKED_SYNTHETIC_SOFTWARE_CONTROL_ONLY"
REASON_RELIABILITY_NOT_INTERPRETABLE = (
    "CALIBRATION_BLOCKED_RELIABILITY_BINS_NOT_INTERPRETABLE"
)
REASON_PRODUCT_PROBABILITY_REQUIRED = (
    "CALIBRATION_BLOCKED_PROBABILITY_WORDING_REQUIRED_BUT_EVIDENCE_INSUFFICIENT"
)
REASON_LOCKED_TEST_TOUCHED = "CALIBRATION_REFUSED_LOCKED_TEST_ACCESS"
REASON_SINGLE_CLASS_CALIBRATION = (
    "CALIBRATION_REFUSED_SINGLE_CLASS_CALIBRATION_SUBSET"
)
REASON_SINGLE_CLASS_EVALUATION = (
    "CALIBRATION_EVALUATION_UNDEFINED_SINGLE_CLASS"
)
REASON_OVERLAPPING_GROUPS = (
    "CALIBRATION_REFUSED_OVERLAPPING_FIT_CALIBRATION_EVALUATION_GROUPS"
)
REASON_SHARED_PAIR = "CALIBRATION_REFUSED_SHARED_PAIR_LINEAGE"
REASON_SPARSE_BIN = "CALIBRATION_RELIABILITY_SPARSE_GROUP_SUPPORT"
REASON_PERFECT_SEPARATION = (
    "CALIBRATION_PERFECT_SEPARATION_SYNTHETIC_SCENARIO"
)
REASON_SCORE_OUT_OF_BOUNDS = "CALIBRATION_REFUSED_SCORE_OUTSIDE_UNIT_INTERVAL"
REASON_NON_FINITE_SCORE = "CALIBRATION_REFUSED_NON_FINITE_SCORE"
REASON_UNTRUSTED_LABELS = "CALIBRATION_REFUSED_UNTRUSTED_LABEL_POPULATION"
REASON_IDENTITY_MISMATCH = (
    "CALIBRATION_REFUSED_FEATURE_OR_MODEL_IDENTITY_MISMATCH"
)
REASON_ISOTONIC_INSUFFICIENT = (
    "CALIBRATION_ISOTONIC_REFUSED_INSUFFICIENT_CALIBRATION_SAMPLES"
)
REASON_CV_NOT_GROUP_SAFE = "CALIBRATION_CV_NOT_GROUP_SAFE"
REASON_EMPTY_POPULATION = "CALIBRATION_REFUSED_EMPTY_POPULATION"
REASON_EMPTY_BINS = "CALIBRATION_EMPTY_RELIABILITY_BINS_PRESENT"
REASON_NON_SYNTHETIC_FIXTURE = "CALIBRATION_REFUSED_NON_SYNTHETIC_FIXTURE"

BRIER_POSITIVE_CLASS = "y=1 (critical event within the reference horizon)"
BRIER_SCALE = "[0, 1] mean squared difference (binary, pos_label=1)"

_ISOTONIC_MIN_SAMPLES = 1000


class CalibrationRefusal(ValueError):
    """A calibration request cannot support the claim it asks for."""

    def __init__(self, reason_code: str, detail: str):
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


@dataclass(frozen=True)
class CalibrationEvidence:
    real_eligible_samples: int
    real_eligible_groups: int
    label_identity_frozen: bool
    horizon_frozen: bool
    grouped_fit_calibration_evaluation_disjoint: bool
    pair_lineage_disjoint: bool
    reliability_interpretable: bool
    brier_estimable: bool
    discrimination_estimable: bool
    model_feature_identity_frozen: bool
    locked_test_untouched: bool
    synthetic_only: bool
    product_requires_probability: bool

    def missing_requirements(self) -> tuple[str, ...]:
        checks = (
            ("real_eligible_population", self.real_eligible_samples > 0),
            ("real_independent_groups", self.real_eligible_groups > 0),
            ("label_identity_frozen", self.label_identity_frozen),
            ("horizon_frozen", self.horizon_frozen),
            (
                "group_disjoint_fit_calibration_evaluation",
                self.grouped_fit_calibration_evaluation_disjoint,
            ),
            ("pair_lineage_disjoint", self.pair_lineage_disjoint),
            ("reliability_interpretable", self.reliability_interpretable),
            ("brier_estimable", self.brier_estimable),
            ("discrimination_estimable", self.discrimination_estimable),
            ("model_feature_identity_frozen", self.model_feature_identity_frozen),
            ("locked_test_untouched", self.locked_test_untouched),
            ("not_synthetic_only", not self.synthetic_only),
        )
        return tuple(name for name, ok in checks if not ok)

    def requires_probability_supported(self) -> bool:
        return not self.missing_requirements()


@dataclass(frozen=True)
class ProbabilityDecision:
    decision: str
    reasons: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    product_contract: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": list(self.reasons),
            "missing_requirements": list(self.missing_requirements),
            "product_contract": list(self.product_contract),
        }


SCORE_ONLY_CONTRACT = (
    "The model output is a risk_score, not an empirically calibrated probability.",
    "No percentage-risk wording and no claim such as '72% chance of critical temperature within H' is permitted.",
    "Display and interpretation must state that the score is an uncalibrated decision statistic.",
    "Any later transition to probability wording requires a new evidence-backed decision.",
)


def decide_output_semantics(evidence: CalibrationEvidence) -> ProbabilityDecision:
    """Apply the predeclared decision gate; never infer calibration from scores."""
    if not evidence.locked_test_untouched:
        raise CalibrationRefusal(
            REASON_LOCKED_TEST_TOUCHED,
            "a calibration decision may not consume the locked final test",
        )
    missing = evidence.missing_requirements()
    reasons: list[str] = []
    if evidence.real_eligible_samples <= 0 or evidence.real_eligible_groups <= 0:
        reasons.append(REASON_NO_REAL_POPULATION)
    if not evidence.label_identity_frozen or not evidence.horizon_frozen:
        reasons.append(REASON_TARGET_NOT_FROZEN)
    if evidence.synthetic_only:
        reasons.append(REASON_SYNTHETIC_ONLY)
    if not evidence.reliability_interpretable:
        reasons.append(REASON_RELIABILITY_NOT_INTERPRETABLE)
    if not missing:
        return ProbabilityDecision(
            decision=DECISION_CALIBRATED_PROBABILITY_SUPPORTED,
            reasons=(),
            missing_requirements=(),
            product_contract=(
                "Calibrated probability wording is supported by the provided evidence.",
            ),
        )
    if evidence.product_requires_probability:
        reasons.append(REASON_PRODUCT_PROBABILITY_REQUIRED)
        return ProbabilityDecision(
            decision=DECISION_BLOCKED_BY_CONTRACT,
            reasons=tuple(dict.fromkeys(reasons)),
            missing_requirements=missing,
            product_contract=(
                "The product contract requires probability wording but calibration "
                "evidence is insufficient; neither safe score-only semantics nor a "
                "valid probability decision is currently available.",
            ),
        )
    return ProbabilityDecision(
        decision=DECISION_RISK_SCORE_ONLY,
        reasons=tuple(dict.fromkeys(reasons)),
        missing_requirements=missing,
        product_contract=SCORE_ONLY_CONTRACT,
    )


def assess_w14_real_calibration_evidence(
    *,
    real_eligible_samples: int,
    real_eligible_groups: int,
    label_identity_frozen: bool,
    horizon_frozen: bool,
    product_requires_probability: bool,
) -> CalibrationEvidence:
    """Real-evidence view: synthetic controls never promote a probability claim."""
    real_population = real_eligible_samples > 0 and real_eligible_groups > 0
    return CalibrationEvidence(
        real_eligible_samples=real_eligible_samples,
        real_eligible_groups=real_eligible_groups,
        label_identity_frozen=label_identity_frozen,
        horizon_frozen=horizon_frozen,
        grouped_fit_calibration_evaluation_disjoint=False,
        pair_lineage_disjoint=False,
        reliability_interpretable=False,
        brier_estimable=False,
        discrimination_estimable=False,
        model_feature_identity_frozen=False,
        locked_test_untouched=True,
        synthetic_only=not real_population,
        product_requires_probability=product_requires_probability,
    )


@dataclass(frozen=True)
class ReliabilityBin:
    bin_index: int
    lower: float
    upper: float
    count: int
    positive: int
    negative: int
    group_count: int
    mean_score: float | None
    observed_positive_fraction: float | None
    interpretable: bool
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bin_index": self.bin_index,
            "lower": self.lower,
            "upper": self.upper,
            "count": self.count,
            "positive": self.positive,
            "negative": self.negative,
            "group_count": self.group_count,
            "mean_score": self.mean_score,
            "observed_positive_fraction": self.observed_positive_fraction,
            "interpretable": self.interpretable,
            "reason": self.reason,
        }


def build_reliability_bins(
    scores: Sequence[float],
    labels: Sequence[int],
    groups: Sequence[str],
    *,
    n_bins: int = 5,
) -> tuple[tuple[ReliabilityBin, ...], int]:
    """Uniform bins with explicit counts; empty bins are reported, never zeroed."""
    if not (len(scores) == len(labels) == len(groups)):
        raise CalibrationRefusal(
            REASON_EMPTY_POPULATION, "score, label and group arrays differ in length"
        )
    if len(scores) == 0:
        raise CalibrationRefusal(REASON_EMPTY_POPULATION, "no evaluation samples")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    indices = np.clip(
        np.digitize(np.asarray(scores, dtype=float), edges[1:-1], right=False),
        0,
        n_bins - 1,
    )
    bins: list[ReliabilityBin] = []
    empty = 0
    for index in range(n_bins):
        mask = indices == index
        count = int(mask.sum())
        if count == 0:
            empty += 1
            continue
        bin_scores = np.asarray(scores, dtype=float)[mask]
        bin_labels = np.asarray(labels, dtype=int)[mask]
        bin_groups = np.asarray(groups, dtype=object)[mask]
        unique_groups = sorted({str(group) for group in bin_groups})
        group_counts = {
            group: int((bin_groups == group).sum()) for group in unique_groups
        }
        dominant_share = max(group_counts.values()) / count
        group_support = len(unique_groups) >= 2 and dominant_share <= 0.5
        bins.append(
            ReliabilityBin(
                bin_index=index,
                lower=float(edges[index]),
                upper=float(edges[index + 1]),
                count=count,
                positive=int(bin_labels.sum()),
                negative=int(count - bin_labels.sum()),
                group_count=len(unique_groups),
                mean_score=float(bin_scores.mean()),
                observed_positive_fraction=float(bin_labels.mean()),
                interpretable=group_support,
                reason=None if group_support else REASON_SPARSE_BIN,
            )
        )
    return tuple(bins), empty


def validate_probability_scores(scores: Sequence[float]) -> None:
    array = np.asarray(scores, dtype=float)
    if array.size == 0:
        raise CalibrationRefusal(REASON_EMPTY_POPULATION, "no scores supplied")
    if not np.all(np.isfinite(array)):
        raise CalibrationRefusal(
            REASON_NON_FINITE_SCORE, "scores contain NaN or infinity"
        )
    if np.any(array < 0.0) or np.any(array > 1.0):
        raise CalibrationRefusal(
            REASON_SCORE_OUT_OF_BOUNDS,
            f"scores range [{array.min():.6g}, {array.max():.6g}]",
        )


def validate_calibration_strategy(
    *,
    method: str,
    estimator_mode: str,
    cv_policy: str,
    calibration_samples: int,
) -> None:
    if method not in ("sigmoid", "isotonic"):
        raise CalibrationRefusal(
            REASON_CV_NOT_GROUP_SAFE, f"unsupported calibration method {method!r}"
        )
    if method == "isotonic" and calibration_samples < _ISOTONIC_MIN_SAMPLES:
        raise CalibrationRefusal(
            REASON_ISOTONIC_INSUFFICIENT,
            f"isotonic calibration has {calibration_samples} samples; official "
            f"scikit-learn guidance is >~{_ISOTONIC_MIN_SAMPLES}",
        )
    if estimator_mode != "FROZEN_ESTIMATOR":
        raise CalibrationRefusal(
            REASON_CV_NOT_GROUP_SAFE,
            "only an already-fitted FrozenEstimator may be calibrated; refitting "
            "inside CalibratedClassifierCV would use its row-level default CV",
        )
    if cv_policy != "EXPLICIT_DISJOINT_GROUPS":
        raise CalibrationRefusal(
            REASON_CV_NOT_GROUP_SAFE,
            "CalibratedClassifierCV's default cv is StratifiedKFold over rows; "
            "ColdGuard requires explicit run-group isolation",
        )


def assert_calibration_class_support(
    positive: int, negative: int, *, context: str
) -> None:
    if positive == 0 or negative == 0:
        raise CalibrationRefusal(
            REASON_SINGLE_CLASS_CALIBRATION,
            f"{context} has {positive} positive and {negative} negative samples; "
            "a calibrator is not fitted on a single-class subset",
        )


def assert_label_trust(
    evaluation_runs: Sequence[str], excluded_by_run: Mapping[str, Mapping[str, int]]
) -> None:
    untrusted = {
        run_id: int(excluded_by_run.get(run_id, {}).get("UNTRUSTED_INFO", 0))
        for run_id in evaluation_runs
    }
    affected = {run_id: count for run_id, count in untrusted.items() if count}
    if affected:
        raise CalibrationRefusal(
            REASON_UNTRUSTED_LABELS,
            f"evaluation runs carry untrusted-label exclusions: {affected}",
        )


def assert_group_isolation(
    *,
    model_fit_groups: Sequence[str],
    calibration_groups: Sequence[str],
    evaluation_groups: Sequence[str],
    group_pair: Mapping[str, str | None],
) -> None:
    fit = set(model_fit_groups)
    calibration = set(calibration_groups)
    evaluation = set(evaluation_groups)
    if fit & calibration or fit & evaluation or calibration & evaluation:
        raise CalibrationRefusal(
            REASON_OVERLAPPING_GROUPS,
            "model-fit, calibration and evaluation groups must be pairwise disjoint",
        )
    owners: dict[str, str] = {}
    for name, groups in (
        ("fit", fit),
        ("calibration", calibration),
        ("evaluation", evaluation),
    ):
        for group in groups:
            pair = group_pair.get(group)
            if pair is None:
                continue
            if pair in owners and owners[pair] != name:
                raise CalibrationRefusal(
                    REASON_SHARED_PAIR,
                    f"pair {pair!r} is shared by {owners[pair]} and {name} groups",
                )
            owners[pair] = name


@dataclass(frozen=True)
class CalibrationFoldResult:
    fold_id: str
    status: str
    reason: str | None
    detail: str | None
    model_fit_groups: tuple[str, ...]
    calibration_groups: tuple[str, ...]
    evaluation_groups: tuple[str, ...]
    model_fit_runs: tuple[str, ...]
    calibration_runs: tuple[str, ...]
    evaluation_runs: tuple[str, ...]
    model_fit_samples: int
    calibration_samples: int
    evaluation_samples: int
    calibration_positive: int
    calibration_negative: int
    evaluation_positive: int
    evaluation_negative: int
    raw_brier: float | None
    calibrated_brier: float | None
    brier_delta: float | None
    raw_ap: float | None
    calibrated_ap: float | None
    ap_reason: str | None
    reliability_bins: tuple[ReliabilityBin, ...]
    empty_bin_count: int
    calibration_curve_prob_true: tuple[float, ...]
    calibration_curve_prob_pred: tuple[float, ...]
    perfect_separation: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "status": self.status,
            "reason": self.reason,
            "detail": self.detail,
            "model_fit_groups": list(self.model_fit_groups),
            "calibration_groups": list(self.calibration_groups),
            "evaluation_groups": list(self.evaluation_groups),
            "model_fit_runs": list(self.model_fit_runs),
            "calibration_runs": list(self.calibration_runs),
            "evaluation_runs": list(self.evaluation_runs),
            "model_fit_samples": self.model_fit_samples,
            "calibration_samples": self.calibration_samples,
            "evaluation_samples": self.evaluation_samples,
            "calibration_positive": self.calibration_positive,
            "calibration_negative": self.calibration_negative,
            "evaluation_positive": self.evaluation_positive,
            "evaluation_negative": self.evaluation_negative,
            "raw_brier": self.raw_brier,
            "calibrated_brier": self.calibrated_brier,
            "brier_delta": self.brier_delta,
            "raw_ap": self.raw_ap,
            "calibrated_ap": self.calibrated_ap,
            "ap_reason": self.ap_reason,
            "reliability_bins": [bin.to_dict() for bin in self.reliability_bins],
            "empty_bin_count": self.empty_bin_count,
            "calibration_curve_prob_true": list(self.calibration_curve_prob_true),
            "calibration_curve_prob_pred": list(self.calibration_curve_prob_pred),
            "perfect_separation": self.perfect_separation,
        }


@dataclass(frozen=True)
class CalibrationDiagnostics:
    schema: str
    layer_version: str
    scientific_class: str
    reference_horizon_s: float
    reference_horizon_status: str
    view_id: str
    feature_ids: tuple[str, ...]
    registry_sha256: str
    config_sha256: str
    folds: tuple[CalibrationFoldResult, ...]
    pooled_raw_brier: float | None
    pooled_calibrated_brier: float | None
    pooled_raw_ap: float | None
    pooled_calibrated_ap: float | None
    pooled_reliability_bins: tuple[ReliabilityBin, ...]
    pooled_empty_bin_count: int
    pooled_group_count: int
    all_folds_group_disjoint: bool
    all_folds_pair_disjoint: bool
    reliability_interpretable: bool
    brier_estimable: bool
    discrimination_estimable: bool
    perfect_separation: bool
    candidate_family: tuple[str, ...]
    isotonic_refusal: str | None
    limitations: tuple[str, ...]
    versions: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "layer_version": self.layer_version,
            "scientific_class": self.scientific_class,
            "reference_horizon_s": self.reference_horizon_s,
            "reference_horizon_status": self.reference_horizon_status,
            "view_id": self.view_id,
            "feature_ids": list(self.feature_ids),
            "registry_sha256": self.registry_sha256,
            "config_sha256": self.config_sha256,
            "folds": [fold.to_dict() for fold in self.folds],
            "pooled_raw_brier": self.pooled_raw_brier,
            "pooled_calibrated_brier": self.pooled_calibrated_brier,
            "pooled_raw_ap": self.pooled_raw_ap,
            "pooled_calibrated_ap": self.pooled_calibrated_ap,
            "pooled_reliability_bins": [
                bin.to_dict() for bin in self.pooled_reliability_bins
            ],
            "pooled_empty_bin_count": self.pooled_empty_bin_count,
            "pooled_group_count": self.pooled_group_count,
            "all_folds_group_disjoint": self.all_folds_group_disjoint,
            "all_folds_pair_disjoint": self.all_folds_pair_disjoint,
            "reliability_interpretable": self.reliability_interpretable,
            "brier_estimable": self.brier_estimable,
            "discrimination_estimable": self.discrimination_estimable,
            "perfect_separation": self.perfect_separation,
            "candidate_family": list(self.candidate_family),
            "isotonic_refusal": self.isotonic_refusal,
            "limitations": list(self.limitations),
            "versions": dict(self.versions),
            "brier_definition": {
                "positive_class": BRIER_POSITIVE_CLASS,
                "scale": BRIER_SCALE,
            },
        }


def _samples_for_runs(dataset: LabeledDataset, runs: Sequence[str]) -> list[Any]:
    run_set = set(runs)
    return [sample for sample in dataset.samples if sample.run_id in run_set]


def _brier(labels: Sequence[int], scores: Sequence[float]) -> float:
    if not labels:
        raise CalibrationRefusal(REASON_EMPTY_POPULATION, "no Brier samples")
    validate_probability_scores(scores)
    return float(brier_score_loss(list(labels), list(scores), pos_label=1))


def _ap(labels: Sequence[int], scores: Sequence[float]) -> tuple[float | None, str | None]:
    if len(set(labels)) < 2:
        return None, REASON_SINGLE_CLASS_EVALUATION
    return float(average_precision_score(list(labels), list(scores))), None


def run_grouped_calibration(
    fixture: BenchmarkFixture,
    registry: Any,
    config: BenchmarkConfig,
    view: AblationView,
    *,
    calibration_groups_per_fold: int = 2,
    n_bins: int = 5,
) -> CalibrationDiagnostics:
    """Synthetic software control of group-safe calibration.

    The caller must not treat this result as probability evidence for the plant.
    """
    if fixture.provenance not in (SOFTWARE_ONLY, SYNTHETIC_PROVENANCE):
        raise CalibrationRefusal(
            REASON_NON_SYNTHETIC_FIXTURE,
            "calibration diagnostics require a synthetic software-control "
            f"fixture, got provenance {fixture.provenance!r}",
        )
    if any(
        trajectory.source_type != SOURCE_TYPE_SYNTHETIC
        for trajectory in fixture.trajectories
    ):
        raise CalibrationRefusal(
            REASON_NON_SYNTHETIC_FIXTURE,
            "a physical trajectory cannot enter the W14 calibration control",
        )
    validate_view(view, registry)
    dataset = build_ablation_dataset(fixture, registry, config, view)
    runs = build_evaluation_runs(
        fixture.development_trajectories,
        fixture.split,
        hardware_config_by_run=fixture.hardware_config_by_run,
    )
    group_pair = {run.group_id: run.pair_id for run in runs}
    cv = make_grouped_folds(
        runs,
        n_splits=config.cv.n_splits,
        seed=config.cv.seed,
        min_train_groups=config.cv.min_train_groups,
        min_validation_groups=config.cv.min_validation_groups,
    )
    if dict(config.model_params) != W11_PREDECLARED_MODEL_PARAMS:
        raise CalibrationRefusal(
            REASON_IDENTITY_MISMATCH,
            "the W14 calibration model must remain the predeclared W11 model; "
            f"got {dict(config.model_params)!r}",
        )
    results: list[CalibrationFoldResult] = []
    pooled_scores: list[float] = []
    pooled_calibrated: list[float] = []
    pooled_labels: list[int] = []
    pooled_groups: list[str] = []
    pair_disjoint_flags: list[bool] = []
    for index, fold in enumerate(cv.folds):
        fold_id = fold.fold_id
        train_pool = sorted(fold.train_groups)
        if len(train_pool) < calibration_groups_per_fold + 2:
            results.append(
                _refused_fold(
                    fold,
                    REASON_EMPTY_POPULATION,
                    "insufficient train-pool groups for model fit and calibration",
                )
            )
            continue
        shuffled = list(train_pool)
        random.Random(config.cv.seed + 1000 + index).shuffle(shuffled)
        calibration_groups = tuple(shuffled[:calibration_groups_per_fold])
        model_fit_groups = tuple(shuffled[calibration_groups_per_fold:])
        evaluation_groups = tuple(fold.validation_groups)
        assert_group_isolation(
            model_fit_groups=model_fit_groups,
            calibration_groups=calibration_groups,
            evaluation_groups=evaluation_groups,
            group_pair=group_pair,
        )
        pair_owners: dict[str, str] = {}
        pair_disjoint = True
        for name, groups in (
            ("fit", model_fit_groups),
            ("calibration", calibration_groups),
            ("evaluation", evaluation_groups),
        ):
            for group in groups:
                pair = group_pair.get(group)
                if pair is None:
                    pair_disjoint = False
                    continue
                if pair in pair_owners and pair_owners[pair] != name:
                    pair_disjoint = False
                pair_owners[pair] = name
        pair_disjoint_flags.append(pair_disjoint)
        run_by_group = {}
        for run in runs:
            run_by_group.setdefault(run.group_id, []).append(run.run_id)
        fit_runs = tuple(
            run_id
            for group in model_fit_groups
            for run_id in sorted(run_by_group.get(group, ()))
        )
        calibration_runs = tuple(
            run_id
            for group in calibration_groups
            for run_id in sorted(run_by_group.get(group, ()))
        )
        evaluation_runs = tuple(
            run_id
            for group in evaluation_groups
            for run_id in sorted(run_by_group.get(group, ()))
        )
        fit_samples = _samples_for_runs(dataset, fit_runs)
        calibration_samples = _samples_for_runs(dataset, calibration_runs)
        evaluation_samples = _samples_for_runs(dataset, evaluation_runs)
        if not fit_samples or not calibration_samples or not evaluation_samples:
            results.append(
                _refused_fold(fold, REASON_EMPTY_POPULATION, "empty fold population")
            )
            continue
        try:
            assert_label_trust(evaluation_runs, dataset.excluded_by_run)
        except CalibrationRefusal as exc:
            results.append(_refused_fold(fold, exc.reason_code, exc.detail))
            continue
        fit_positive = sum(1 for sample in fit_samples if sample.y == 1)
        fit_negative = len(fit_samples) - fit_positive
        cal_positive = sum(1 for sample in calibration_samples if sample.y == 1)
        cal_negative = len(calibration_samples) - cal_positive
        eval_positive = sum(1 for sample in evaluation_samples if sample.y == 1)
        eval_negative = len(evaluation_samples) - eval_positive
        if fit_positive == 0 or fit_negative == 0:
            results.append(
                _refused_fold(
                    fold,
                    "SINGLE_CLASS_TRAINING_FOLD",
                    "model-fit groups are single-class",
                )
            )
            continue
        try:
            assert_calibration_class_support(
                cal_positive, cal_negative, context="calibration subset"
            )
        except CalibrationRefusal as exc:
            results.append(_refused_fold(fold, exc.reason_code, exc.detail))
            continue
        try:
            validate_calibration_strategy(
                method="sigmoid",
                estimator_mode="FROZEN_ESTIMATOR",
                cv_policy="EXPLICIT_DISJOINT_GROUPS",
                calibration_samples=len(calibration_samples),
            )
        except CalibrationRefusal as exc:
            results.append(_refused_fold(fold, exc.reason_code, exc.detail))
            continue
        X_fit, y_fit = feature_matrix(fit_samples, dataset.feature_ids)
        X_cal, y_cal = feature_matrix(calibration_samples, dataset.feature_ids)
        X_eval, y_eval = feature_matrix(evaluation_samples, dataset.feature_ids)
        params = dict(config.model_params)
        params["scale_pos_weight"] = 1.0
        params["n_jobs"] = 1
        params["verbosity"] = 0
        model = XGBClassifier(**params)
        model.fit(X_fit, y_fit)
        raw_calibration = np.asarray(model.predict_proba(X_cal)[:, 1], dtype=float)
        raw_eval = np.asarray(model.predict_proba(X_eval)[:, 1], dtype=float)
        try:
            validate_probability_scores(raw_calibration)
            validate_probability_scores(raw_eval)
        except CalibrationRefusal as exc:
            results.append(_refused_fold(fold, exc.reason_code, exc.detail))
            continue
        calibrator = CalibratedClassifierCV(
            estimator=FrozenEstimator(model),
            method="sigmoid",
            cv=None,
        )
        calibrator.fit(X_cal, y_cal)
        calibrated_eval = np.asarray(
            calibrator.predict_proba(X_eval)[:, 1], dtype=float
        )
        calibrated_calibration = np.asarray(
            calibrator.predict_proba(X_cal)[:, 1], dtype=float
        )
        try:
            validate_probability_scores(calibrated_eval)
            validate_probability_scores(calibrated_calibration)
        except CalibrationRefusal as exc:
            results.append(_refused_fold(fold, exc.reason_code, exc.detail))
            continue
        raw_brier = _brier(list(y_eval), raw_eval)
        calibrated_brier = _brier(list(y_eval), calibrated_eval)
        raw_ap, ap_reason = _ap(list(y_eval), raw_eval)
        calibrated_ap, _ = _ap(list(y_eval), calibrated_eval)
        eval_group_by_identity = {
            sample.sample_identity: sample.group_id for sample in evaluation_samples
        }
        eval_groups = [
            eval_group_by_identity[sample.sample_identity]
            for sample in evaluation_samples
        ]
        bins, empty_bins = build_reliability_bins(
            calibrated_eval, list(y_eval), eval_groups, n_bins=n_bins
        )
        curve_true, curve_pred = calibration_curve(
            y_eval, calibrated_eval, pos_label=1, n_bins=n_bins, strategy="uniform"
        )
        perfect = _perfect_separation(list(y_eval), raw_eval)
        results.append(
            CalibrationFoldResult(
                fold_id=fold_id,
                status="FIT",
                reason=None,
                detail=None,
                model_fit_groups=model_fit_groups,
                calibration_groups=calibration_groups,
                evaluation_groups=evaluation_groups,
                model_fit_runs=fit_runs,
                calibration_runs=calibration_runs,
                evaluation_runs=evaluation_runs,
                model_fit_samples=len(fit_samples),
                calibration_samples=len(calibration_samples),
                evaluation_samples=len(evaluation_samples),
                calibration_positive=cal_positive,
                calibration_negative=cal_negative,
                evaluation_positive=eval_positive,
                evaluation_negative=eval_negative,
                raw_brier=raw_brier,
                calibrated_brier=calibrated_brier,
                brier_delta=calibrated_brier - raw_brier,
                raw_ap=raw_ap,
                calibrated_ap=calibrated_ap,
                ap_reason=ap_reason,
                reliability_bins=bins,
                empty_bin_count=empty_bins,
                calibration_curve_prob_true=tuple(float(v) for v in curve_true),
                calibration_curve_prob_pred=tuple(float(v) for v in curve_pred),
                perfect_separation=perfect,
            )
        )
        pooled_scores.extend(float(v) for v in raw_eval)
        pooled_calibrated.extend(float(v) for v in calibrated_eval)
        pooled_labels.extend(int(v) for v in y_eval)
        pooled_groups.extend(eval_groups)
    if pooled_scores:
        pooled_raw_brier = _brier(pooled_labels, pooled_scores)
        pooled_calibrated_brier = _brier(pooled_labels, pooled_calibrated)
        pooled_raw_ap, _ = _ap(pooled_labels, pooled_scores)
        pooled_calibrated_ap, _ = _ap(pooled_labels, pooled_calibrated)
        pooled_bins, pooled_empty = build_reliability_bins(
            pooled_calibrated, pooled_labels, pooled_groups, n_bins=n_bins
        )
        perfect_separation = _perfect_separation(pooled_labels, pooled_scores)
        if perfect_separation:
            pooled_ap_reason = REASON_PERFECT_SEPARATION
    else:
        pooled_raw_brier = pooled_calibrated_brier = None
        pooled_raw_ap = pooled_calibrated_ap = None
        pooled_bins, pooled_empty = (), 0
        perfect_separation = False
        pooled_ap_reason = None
    fitted = [fold for fold in results if fold.status == "FIT"]
    all_group_disjoint = len(fitted) == len(results) and all(
        set(fold.model_fit_groups).isdisjoint(fold.calibration_groups)
        and set(fold.model_fit_groups).isdisjoint(fold.evaluation_groups)
        and set(fold.calibration_groups).isdisjoint(fold.evaluation_groups)
        for fold in fitted
    )
    all_pair_disjoint = (
        len(pair_disjoint_flags) == len(results) and all(pair_disjoint_flags)
    )
    reliability_interpretable = bool(
        pooled_bins
        and len(pooled_bins) >= 3
        and all(bin.interpretable for bin in pooled_bins)
        and not perfect_separation
    )
    brier_estimable = pooled_raw_brier is not None and pooled_calibrated_brier is not None
    discrimination_estimable = (
        pooled_raw_ap is not None and pooled_calibrated_ap is not None
    )
    limitations = (
        "synthetic development population only; never physical probability evidence",
        "the synthetic fixture is perfectly separable on its scenario-identifying "
        "door/thermal pattern; perfect AP is not a plant result",
        "reliability bins with one independent group are not interpretable",
        "four outer folds reuse correlated development groups; no significance claim",
        "the calibrator is fitted on development groups disjoint from model fit and "
        "evaluation, but the whole experiment remains a software control",
        "CalibratedClassifierCV's default cv is not used; group isolation is explicit",
        "isotonic calibration is refused below the official ~1000-sample caveat",
    )
    return CalibrationDiagnostics(
        schema=CALIBRATION_SCHEMA,
        layer_version=CALIBRATION_LAYER_VERSION,
        scientific_class=SYNTHETIC_SOFTWARE_CONTROL,
        reference_horizon_s=config.label.horizon_s,
        reference_horizon_status="ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN",
        view_id=view.view_id,
        feature_ids=view.feature_ids,
        registry_sha256=registry.schema_sha256,
        config_sha256=config.config_sha256,
        folds=tuple(results),
        pooled_raw_brier=pooled_raw_brier,
        pooled_calibrated_brier=pooled_calibrated_brier,
        pooled_raw_ap=pooled_raw_ap,
        pooled_calibrated_ap=pooled_calibrated_ap,
        pooled_reliability_bins=pooled_bins,
        pooled_empty_bin_count=pooled_empty,
        pooled_group_count=len(set(pooled_groups)),
        all_folds_group_disjoint=all_group_disjoint,
        all_folds_pair_disjoint=all_pair_disjoint,
        reliability_interpretable=reliability_interpretable,
        brier_estimable=brier_estimable,
        discrimination_estimable=discrimination_estimable,
        perfect_separation=perfect_separation,
        candidate_family=("sigmoid",),
        isotonic_refusal=REASON_ISOTONIC_INSUFFICIENT,
        limitations=limitations,
        versions=package_versions(),
    )


def _perfect_separation(labels: Sequence[int], scores: Sequence[float]) -> bool:
    positives = [score for score, label in zip(scores, labels) if label == 1]
    negatives = [score for score, label in zip(scores, labels) if label == 0]
    if not positives or not negatives:
        return False
    return bool(min(positives) > max(negatives))


def _refused_fold(fold: Any, reason: str, detail: str) -> CalibrationFoldResult:
    return CalibrationFoldResult(
        fold_id=fold.fold_id,
        status="REFUSED",
        reason=reason,
        detail=detail,
        model_fit_groups=(),
        calibration_groups=(),
        evaluation_groups=tuple(fold.validation_groups),
        model_fit_runs=(),
        calibration_runs=(),
        evaluation_runs=tuple(fold.validation_runs),
        model_fit_samples=0,
        calibration_samples=0,
        evaluation_samples=0,
        calibration_positive=0,
        calibration_negative=0,
        evaluation_positive=0,
        evaluation_negative=0,
        raw_brier=None,
        calibrated_brier=None,
        brier_delta=None,
        raw_ap=None,
        calibrated_ap=None,
        ap_reason=reason,
        reliability_bins=(),
        empty_bin_count=0,
        calibration_curve_prob_true=(),
        calibration_curve_prob_pred=(),
        perfect_separation=False,
    )


def calibration_fold_rows(diagnostics: CalibrationDiagnostics) -> list[dict[str, Any]]:
    rows = []
    for fold in diagnostics.folds:
        rows.append(
            {
                "fold_id": fold.fold_id,
                "status": fold.status,
                "reason": fold.reason,
                "detail": fold.detail,
                "model_fit_groups": ";".join(fold.model_fit_groups),
                "calibration_groups": ";".join(fold.calibration_groups),
                "evaluation_groups": ";".join(fold.evaluation_groups),
                "model_fit_samples": fold.model_fit_samples,
                "calibration_samples": fold.calibration_samples,
                "evaluation_samples": fold.evaluation_samples,
                "calibration_positive": fold.calibration_positive,
                "calibration_negative": fold.calibration_negative,
                "evaluation_positive": fold.evaluation_positive,
                "evaluation_negative": fold.evaluation_negative,
                "raw_brier": fold.raw_brier,
                "calibrated_brier": fold.calibrated_brier,
                "brier_delta": fold.brier_delta,
                "raw_ap": fold.raw_ap,
                "calibrated_ap": fold.calibrated_ap,
                "ap_reason": fold.ap_reason,
                "non_empty_bins": len(fold.reliability_bins),
                "empty_bins": fold.empty_bin_count,
                "perfect_separation": fold.perfect_separation,
            }
        )
    return rows


def calibration_bin_rows(diagnostics: CalibrationDiagnostics) -> list[dict[str, Any]]:
    rows = []
    for scope, bins in (
        ("POOLED_OOF", diagnostics.pooled_reliability_bins),
        *((fold.fold_id, fold.reliability_bins) for fold in diagnostics.folds),
    ):
        for bin in bins:
            rows.append(
                {
                    "scope": scope,
                    **bin.to_dict(),
                }
            )
    return rows
