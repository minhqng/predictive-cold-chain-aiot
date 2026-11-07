"""W12 feature-importance diagnostics: fold scope, provenance and refusal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coldguard_ml.benchmark_synthesis import load_w11_bundle
from coldguard_ml.feature_importance import (
    INTERPRETATION_LIMIT,
    FeatureImportanceError,
    _gain_scores,
    compute_feature_importance,
)

ML_ROOT = Path(__file__).resolve().parents[1]
W11 = ML_ROOT / "reports" / "W11"
REGISTRY = ML_ROOT / "feature-registry-v1.yaml"
CONFIG = ML_ROOT / "xgb-v1-config.yaml"


@pytest.fixture(scope="module")
def bundle():
    return load_w11_bundle(
        W11, registry_path=REGISTRY, config_path=CONFIG
    )


@pytest.fixture(scope="module")
def importance(bundle):
    return compute_feature_importance(bundle)


def test_every_fold_model_is_fold_scoped(importance):
    assert len(importance.model_identities) == 8
    assert len(importance.rows) == 8 * 28
    assert all(row.scope == "FOLD_MODEL_ONLY" for row in importance.rows)
    assert all(
        row.cv_scope == "NOT_FULL_CV_IMPORTANCE" for row in importance.rows
    )
    assert all(
        identity["cv_scope"] == "NOT_FULL_CV_IMPORTANCE"
        for identity in importance.model_identities
    )


def test_feature_order_matches_registry_and_hot_side_is_excluded(importance):
    registry_ids = {row.feature_id for row in importance.rows}
    assert "T_tec_hot_side_c" not in registry_ids
    for identity in importance.model_identities:
        assert identity["feature_ids"] == list(
            load_w11_bundle(
                W11, registry_path=REGISTRY, config_path=CONFIG
            ).config.feature_policy.allowlist
        )


def test_unrecognized_model_feature_is_refused():
    class FakeBooster:
        def get_score(self, importance_type):
            assert importance_type == "gain"
            return {"f0": 1.0, "f99": 2.0}

    class FakeModel:
        def get_booster(self):
            return FakeBooster()

    with pytest.raises(FeatureImportanceError, match="unrecognized"):
        _gain_scores(FakeModel(), ("a", "b"))


def test_wrong_config_or_registry_hash_is_refused(bundle):
    with pytest.raises(FeatureImportanceError, match="model config hash"):
        compute_feature_importance(bundle, expected_config_sha256="0" * 64)
    with pytest.raises(FeatureImportanceError, match="registry hash"):
        compute_feature_importance(bundle, expected_registry_sha256="0" * 64)


def test_importance_is_not_labeled_causal(importance):
    for row in importance.rows:
        assert row.interpretation_limit == INTERPRETATION_LIMIT
        assert "not physical causality" in row.interpretation_limit
    for family in importance.family_summaries:
        assert "not physical causality" in family.interpretation_limit


def test_synthetic_provenance_and_locked_test_are_retained(importance):
    assert importance.source_identities["locked_test_used"] is False
    assert (
        importance.source_identities["provenance"]
        == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    )
    fold_manifest = json.loads(
        (W11 / "benchmark-manifest-W11.json").read_text(encoding="utf-8")
    )
    test_runs = {
        "CG-W11-S1-001",
        "CG-W11-S1-002",
        "CG-W11-S2-001",
        "CG-W11-S2-002",
    }
    observed_runs = {
        run_id
        for identity in importance.model_identities
        for run_id in identity["validation_runs"]
    }
    assert observed_runs.isdisjoint(test_runs)
    assert fold_manifest["cv"]["n_splits"] == 4


def test_top_feature_is_the_synthetic_door_timing_signal(importance):
    top_rows = [row for row in importance.rows if row.rank == 1]
    assert top_rows
    assert {row.feature_id for row in top_rows} == {"time_since_open"}
    assert importance.family_summaries[0].feature_family == "door"
    assert importance.family_summaries[0].top_feature_id == "time_since_open"


def test_fold_membership_must_match_w11_manifest(bundle):
    import copy
    import dataclasses

    fold_manifest = copy.deepcopy(dict(bundle.fold_manifest))
    fold_manifest["folds"][0]["validation_run_ids"].append("BOGUS-RUN")
    tampered = dataclasses.replace(bundle, fold_manifest=fold_manifest)
    with pytest.raises(FeatureImportanceError, match="membership"):
        compute_feature_importance(tampered)


def test_every_feature_has_missingness_context(importance):
    assert all(row.missingness_context for row in importance.rows)
    assert all(row.model_identity for row in importance.rows)
    assert all(row.run_group_support == 2 for row in importance.rows)
