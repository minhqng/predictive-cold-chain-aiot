"""W12 fold-scoped XGBoost gain diagnostics (B-W12-04).

Importance is descriptive model behavior on a synthetic fixture. It is not
physical causality, mechanism proof or source identification.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .benchmark_synthesis import SynthesisError, W11Bundle
from .feature_registry import FeatureRegistry
from .grouped_evaluation import build_evaluation_runs, make_grouped_folds
from .xgb_benchmark import (
    FIT_STATUS_FIT,
    _fit_fold,
    build_expanded_w11_fixture,
    build_labeled_dataset,
)

FEATURE_IMPORTANCE_SCHEMA = "coldguard-w12-feature-importance-v1"
IMPORTANCE_METHOD = "GAIN"
SYNTHETIC_PROVENANCE = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
INTERPRETATION_LIMIT = (
    "descriptive split-gain usage in a synthetic fixture; not physical "
    "causality, not an independent mechanism proof"
)
FAMILY_LABELS = {
    "instantaneous_thermal": "thermal",
    "rolling_thermal": "rolling thermal",
    "door_context": "door",
    "actuation_context": "actuation",
    "electrical_context": "electrical",
    "environmental_context": "environment",
    "diagnostic_thermal": "diagnostic thermal",
}


class FeatureImportanceError(ValueError):
    """A model cannot be linked to the expected fold/config/feature registry."""


@dataclass(frozen=True)
class ImportanceRow:
    feature_id: str
    feature_registry_version: str
    feature_family: str
    importance_method: str
    importance_value: float
    normalized_share: float
    model_identity: str
    fold_id: str
    strategy: str
    scope: str
    cv_scope: str
    run_group_support: int
    validation_group_count: int
    source_provenance: str
    rank: int
    missingness_context: str
    interpretation_limit: str

    def to_row(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_registry_version": self.feature_registry_version,
            "feature_family": self.feature_family,
            "importance_method": self.importance_method,
            "importance_value": self.importance_value,
            "normalized_share": self.normalized_share,
            "model_identity": self.model_identity,
            "fold_id": self.fold_id,
            "strategy": self.strategy,
            "scope": self.scope,
            "cv_scope": self.cv_scope,
            "run_group_support": self.run_group_support,
            "validation_group_count": self.validation_group_count,
            "source_provenance": self.source_provenance,
            "rank": self.rank,
            "missingness_context": self.missingness_context,
            "interpretation_limit": self.interpretation_limit,
        }


@dataclass(frozen=True)
class FeatureFamilySummary:
    feature_family: str
    feature_count: int
    fold_model_count: int
    mean_normalized_share: float
    top_feature_id: str | None
    interpretation_limit: str

    def to_row(self) -> dict[str, Any]:
        return {
            "feature_family": self.feature_family,
            "feature_count": self.feature_count,
            "fold_model_count": self.fold_model_count,
            "mean_normalized_share": self.mean_normalized_share,
            "top_feature_id": self.top_feature_id,
            "interpretation_limit": self.interpretation_limit,
        }


@dataclass(frozen=True)
class FeatureImportanceReport:
    schema: str
    rows: tuple[ImportanceRow, ...]
    family_summaries: tuple[FeatureFamilySummary, ...]
    model_identities: tuple[Mapping[str, Any], ...]
    source_identities: Mapping[str, Any]
    refusals: tuple[Mapping[str, Any], ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "rows": [row.to_row() for row in self.rows],
            "family_summaries": [
                item.to_row() for item in self.family_summaries
            ],
            "model_identities": [dict(item) for item in self.model_identities],
            "source_identities": dict(self.source_identities),
            "refusals": [dict(item) for item in self.refusals],
            "limitations": list(self.limitations),
        }


def _model_identity(
    *,
    config_sha256: str,
    feature_ids: Sequence[str],
    fold_id: str,
    strategy: str,
    model: Any,
) -> str:
    payload = {
        "config_sha256": config_sha256,
        "feature_ids": list(feature_ids),
        "fold_id": fold_id,
        "strategy": strategy,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    model_bytes = bytes(model.get_booster().save_raw(raw_format="ubj"))
    return hashlib.sha256(canonical.encode("utf-8") + model_bytes).hexdigest()


def _gain_scores(
    model: Any, feature_ids: Sequence[str]
) -> dict[str, float]:
    raw = model.get_booster().get_score(importance_type="gain")
    allowed = {f"f{index}" for index in range(len(feature_ids))}
    unexpected = sorted(set(raw) - allowed)
    if unexpected:
        raise FeatureImportanceError(
            f"model exposes unrecognized feature indices {unexpected}"
        )
    return {
        feature_id: float(raw.get(f"f{index}", 0.0))
        for index, feature_id in enumerate(feature_ids)
    }


def compute_feature_importance(
    bundle: W11Bundle,
    *,
    registry: FeatureRegistry | None = None,
    expected_config_sha256: str | None = None,
    expected_registry_sha256: str | None = None,
) -> FeatureImportanceReport:
    registry = registry or bundle.registry
    config = bundle.config
    expected_config_sha256 = (
        expected_config_sha256 or config.config_sha256
    )
    expected_registry_sha256 = (
        expected_registry_sha256 or registry.schema_sha256
    )
    if expected_config_sha256 != bundle.manifest["config"]["config_sha256"]:
        raise FeatureImportanceError(
            "model config hash does not match the W11 benchmark manifest"
        )
    if expected_registry_sha256 != bundle.manifest["registry_sha256"]:
        raise FeatureImportanceError(
            "feature registry hash does not match the W11 benchmark manifest"
        )
    if registry.schema_sha256 != bundle.manifest["registry_sha256"]:
        raise FeatureImportanceError(
            "provided feature registry is not the one registered by W11"
        )
    if config.config_sha256 != bundle.manifest["config"]["config_sha256"]:
        raise FeatureImportanceError(
            "provided model config is not the one registered by W11"
        )
    fixture = build_expanded_w11_fixture()
    if fixture.dataset_id != bundle.manifest["dataset_id"]:
        raise FeatureImportanceError(
            "feature-importance fixture does not match the W11 dataset identity"
        )
    labeled = build_labeled_dataset(fixture, registry, config)
    expected_features = tuple(config.feature_policy.allowlist)
    if labeled.feature_ids != expected_features:
        raise FeatureImportanceError(
            "label builder feature order does not match the configured allowlist"
        )
    for feature_id in expected_features:
        try:
            registry.feature(feature_id)
        except KeyError as exc:
            raise FeatureImportanceError(
                f"feature {feature_id!r} is not in the registered feature set"
            ) from exc
    evaluation_runs = build_evaluation_runs(
        fixture.development_trajectories,
        fixture.split,
        hardware_config_by_run=fixture.hardware_config_by_run,
    )
    cv = make_grouped_folds(
        evaluation_runs,
        n_splits=config.cv.n_splits,
        seed=config.cv.seed,
        min_train_groups=config.cv.min_train_groups,
        min_validation_groups=config.cv.min_validation_groups,
    )
    recorded_folds = {
        str(fold["fold_id"]): fold
        for fold in bundle.fold_manifest.get("folds", ())
    }
    if set(recorded_folds) != {fold.fold_id for fold in cv.folds}:
        raise FeatureImportanceError(
            "recomputed folds do not match the W11 fold manifest"
        )
    for fold in cv.folds:
        record = recorded_folds[fold.fold_id]
        if (
            tuple(fold.validation_runs) != tuple(record.get("validation_run_ids", ()))
            or tuple(fold.train_runs) != tuple(record.get("train_run_ids", ()))
            or tuple(fold.validation_groups)
            != tuple(record.get("validation_group_ids", ()))
            or tuple(fold.train_groups) != tuple(record.get("train_group_ids", ()))
        ):
            raise FeatureImportanceError(
                f"fold {fold.fold_id!r} membership does not match the W11 manifest"
            )
    test_runs = set(fixture.split.test_runs)
    fold_run_ids = {run_id for fold in cv.folds for run_id in fold.validation_runs}
    if test_runs & fold_run_ids:
        raise FeatureImportanceError(
            "locked-test runs appear in a fold used for importance"
        )
    rows: list[ImportanceRow] = []
    identities: list[Mapping[str, Any]] = []
    refusals: list[Mapping[str, Any]] = []
    fold_model_count = 0
    for strategy in config.strategies:
        for fold in cv.folds:
            train_samples = [
                sample
                for sample in labeled.samples
                if sample.run_id in fold.train_runs
            ]
            validation_samples = [
                sample
                for sample in labeled.samples
                if sample.run_id in fold.validation_runs
            ]
            result, model = _fit_fold(
                fold=fold,
                strategy=strategy,
                train_samples=train_samples,
                validation_samples=validation_samples,
                config=config,
                feature_ids=labeled.feature_ids,
            )
            if model is None or result.status != FIT_STATUS_FIT:
                refusals.append(
                    {
                        "fold_id": fold.fold_id,
                        "strategy": strategy,
                        "reason": result.reason or "FOLD_MODEL_REFUSED",
                        "status": result.status,
                    }
                )
                continue
            if model.n_features_in_ != len(expected_features):
                raise FeatureImportanceError(
                    "model feature count does not match the registered feature order"
                )
            identity = _model_identity(
                config_sha256=config.config_sha256,
                feature_ids=labeled.feature_ids,
                fold_id=fold.fold_id,
                strategy=strategy,
                model=model,
            )
            fold_model_count += 1
            identities.append(
                {
                    "fold_id": fold.fold_id,
                    "strategy": strategy,
                    "model_identity": identity,
                    "validation_groups": list(fold.validation_groups),
                    "validation_runs": list(fold.validation_runs),
                    "scope": "FOLD_MODEL_ONLY",
                    "cv_scope": "NOT_FULL_CV_IMPORTANCE",
                    "config_sha256": config.config_sha256,
                    "feature_ids": list(labeled.feature_ids),
                    "fit_status": result.status,
                }
            )
            gains = _gain_scores(model, labeled.feature_ids)
            total = sum(gains.values())
            ordered = sorted(
                gains.items(), key=lambda item: (-item[1], item[0])
            )
            for rank, (feature_id, gain) in enumerate(ordered, start=1):
                feature = registry.feature(feature_id)
                rows.append(
                    ImportanceRow(
                        feature_id=feature_id,
                        feature_registry_version=registry.feature_version,
                        feature_family=FAMILY_LABELS.get(
                            feature.family, feature.family
                        ),
                        importance_method=IMPORTANCE_METHOD,
                        importance_value=gain,
                        normalized_share=(gain / total if total > 0 else 0.0),
                        model_identity=identity,
                        fold_id=fold.fold_id,
                        strategy=strategy,
                        scope="FOLD_MODEL_ONLY",
                        cv_scope="NOT_FULL_CV_IMPORTANCE",
                        run_group_support=len(fold.validation_groups),
                        validation_group_count=len(fold.validation_groups),
                        source_provenance=SYNTHETIC_PROVENANCE,
                        rank=rank,
                        missingness_context=feature.missing_data_policy,
                        interpretation_limit=INTERPRETATION_LIMIT,
                    )
                )
    if not rows:
        raise FeatureImportanceError("no fold model produced feature importance")
    # Feature-family summary is descriptive across fold models, not a full-CV
    # importance estimate.
    family_rows: list[FeatureFamilySummary] = []
    by_family: dict[str, list[ImportanceRow]] = {}
    for row in rows:
        by_family.setdefault(row.feature_family, []).append(row)
    for family, items in sorted(
        by_family.items(),
        key=lambda item: (
            -sum(row.normalized_share for row in item[1]) / len(item[1]),
            item[0],
        ),
    ):
        mean_share = sum(item.normalized_share for item in items) / len(items)
        top = max(items, key=lambda item: (item.normalized_share, item.feature_id))
        family_rows.append(
            FeatureFamilySummary(
                feature_family=family,
                feature_count=len({item.feature_id for item in items}),
                fold_model_count=fold_model_count,
                mean_normalized_share=mean_share,
                top_feature_id=top.feature_id,
                interpretation_limit=INTERPRETATION_LIMIT,
            )
        )
    source_identities = {
        "dataset_id": fixture.dataset_id,
        "fixture_version": fixture.fixture_version,
        "feature_registry_version": registry.feature_version,
        "feature_registry_sha256": registry.schema_sha256,
        "config_sha256": config.config_sha256,
        "provenance": SYNTHETIC_PROVENANCE,
        "locked_test_used": False,
        "fold_model_count": fold_model_count,
    }
    limitations = (
        "Gain importance is descriptive of these synthetic fold models only.",
        "A single fold model is not full-CV importance; every row is fold-scoped.",
        "Correlated features share credit and ranks are not independent mechanism proofs.",
        "The synthetic fixture's patterns are easy to identify; importance does not "
        "transfer to physical thermal forecasting.",
        "T2 hot-side remains excluded from the configured model feature set.",
    )
    return FeatureImportanceReport(
        schema=FEATURE_IMPORTANCE_SCHEMA,
        rows=tuple(rows),
        family_summaries=tuple(family_rows),
        model_identities=tuple(identities),
        source_identities=source_identities,
        refusals=tuple(refusals),
        limitations=limitations,
    )
