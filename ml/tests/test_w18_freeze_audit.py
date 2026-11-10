"""W18 B-W18-03 freeze-drift and change-control controls."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from coldguard_ml.feature_registry import load_registry
from coldguard_ml.w15_artifact import load_guarded_artifact
from coldguard_ml.w18_freeze_audit import (
    CHANGE_ACCEPTED_PENDING_REVIEW,
    CHANGE_ACCEPTED_REQUIRES_NEW_EVALUATION,
    CHANGE_REFUSED_COMPARABILITY_UNDECLARED,
    CHANGE_REFUSED_FAKE_APPROVAL,
    CHANGE_REFUSED_INCOMPLETE,
    CHANGE_REFUSED_LOCKED_TEST_REUSE,
    CHANGE_REFUSED_NOT_A_NEW_IDENTITY,
    DEVELOPMENT_BASELINE_CHANGED,
    DEVELOPMENT_BASELINE_UNCHANGED,
    MISSING_FREEZE_RECORD,
    FreezeAuditError,
    apply_declared_change,
    assess_change_request,
    build_freeze_baseline,
    compare_freeze_state,
    load_pinned_baseline,
    observe_protected_values,
    verify_model_file_binding,
)
from coldguard_ml.xgb_benchmark import load_benchmark_config

ROOT = Path(__file__).resolve().parents[1]
W15_MODEL_DIR = ROOT / "reports" / "W15" / "model"
FREEZE_BASELINE = ROOT / "reports" / "W18" / "freeze-baseline-W18.json"


@pytest.fixture(scope="module")
def context():
    registry = load_registry()
    config = load_benchmark_config(ROOT / "xgb-v1-config.yaml", registry)
    model = load_guarded_artifact(
        manifest_path=W15_MODEL_DIR / "model-manifest-W15.json",
        model_path=W15_MODEL_DIR / "model.ubj",
        expected_feature_ids=config.feature_policy.allowlist,
        expected_feature_schema_hash=registry.schema_sha256,
        expected_model_config_hash=config.config_sha256,
    )
    baseline = build_freeze_baseline(
        model_manifest=model.manifest,
        manifest_path=W15_MODEL_DIR / "model-manifest-W15.json",
        registry=registry,
        config=config,
        model_path=W15_MODEL_DIR / "model.ubj",
    )
    return model, registry, config, baseline


def _valid_change(baseline) -> dict:
    return {
        "artifact_id": "coldguard-w15-candidate-next",
        "model_artifact_sha256": "a" * 64,
        "model_config_sha256": "b" * 64,
        "feature_schema_hash": baseline.values["feature_schema_hash"],
        "ordered_feature_ids_sha256": baseline.values["ordered_feature_ids_sha256"],
        "reason": "CONTROL_CONTRACT_TEST",
        "owner": "B",
        "affected_evidence": ["ml/reports/W15"],
        "evaluation_implications": "REQUIRES_NEW_INDEPENDENT_EVALUATION",
        "review_gate": {"status": "PENDING_REVIEW"},
        "comparability": "REQUIRES_NEW_INDEPENDENT_EVALUATION",
    }


def test_baseline_matches_actual_files(context):
    model, registry, config, baseline = context
    assert baseline.values["model_artifact_sha256"] == model.manifest[
        "model_artifact_sha256"
    ]
    assert baseline.values["feature_schema_hash"] == registry.schema_sha256
    assert baseline.values["model_config_sha256"] == config.config_sha256
    assert baseline.model_file_sha256 == model.manifest["model_artifact_sha256"]


def test_development_baseline_is_unchanged(context):
    model, registry, config, baseline = context
    observed = build_freeze_baseline(
        model_manifest=model.manifest,
        manifest_path=W15_MODEL_DIR / "model-manifest-W15.json",
        registry=registry,
        config=config,
        model_path=W15_MODEL_DIR / "model.ubj",
    )
    comparison = compare_freeze_state(baseline, observed.values)
    assert comparison.development_status == DEVELOPMENT_BASELINE_UNCHANGED
    assert comparison.drift_fields == ()
    assert comparison.issues == ()
    assert comparison.drift_detected is False


def test_pinned_baseline_matches_current_files(context):
    model, registry, config, _ = context
    baseline = load_pinned_baseline(FREEZE_BASELINE)
    observed = observe_protected_values(
        registry=registry,
        config=config,
        model_manifest=model.manifest,
        manifest_path=W15_MODEL_DIR / "model-manifest-W15.json",
        model_path=W15_MODEL_DIR / "model.ubj",
    )
    comparison = compare_freeze_state(baseline, observed)
    assert comparison.development_status == DEVELOPMENT_BASELINE_UNCHANGED
    assert comparison.drift_fields == ()
    assert baseline.approved_freeze_status == MISSING_FREEZE_RECORD


def test_empty_observation_is_drift_not_unchanged(context):
    _, _, _, baseline = context
    comparison = compare_freeze_state(baseline, {})
    assert comparison.development_status == DEVELOPMENT_BASELINE_CHANGED
    assert comparison.drift_detected is True


def test_invalid_approved_freeze_record_is_refused(context):
    model, registry, config, _ = context
    manifest = copy.deepcopy(model.manifest)
    manifest["approved_freeze_record"] = {"anything": "whatever"}
    with pytest.raises(FreezeAuditError):
        build_freeze_baseline(
            model_manifest=manifest,
            manifest_path=W15_MODEL_DIR / "model-manifest-W15.json",
            registry=registry,
            config=config,
            model_path=W15_MODEL_DIR / "model.ubj",
        )


def test_unbound_approved_freeze_record_is_refused(context):
    model, registry, config, _ = context
    manifest = copy.deepcopy(model.manifest)
    manifest["approved_freeze_record"] = {
        "authority_id": "TEAM_LEAD",
        "evidence_sha256": "a" * 64,
        "canonical_ref": "04 §33",
        "model_artifact_sha256": "b" * 64,
    }
    with pytest.raises(FreezeAuditError):
        build_freeze_baseline(
            model_manifest=manifest,
            manifest_path=W15_MODEL_DIR / "model-manifest-W15.json",
            registry=registry,
            config=config,
            model_path=W15_MODEL_DIR / "model.ubj",
        )


def test_declared_approved_record_is_never_reported_unchanged(context):
    model, registry, config, baseline = context
    manifest = copy.deepcopy(model.manifest)
    manifest["approved_freeze_record"] = {
        "authority_id": "TEAM_LEAD",
        "evidence_sha256": "a" * 64,
        "canonical_ref": "04 §33",
        "model_artifact_sha256": baseline.values["model_artifact_sha256"],
    }
    declared = build_freeze_baseline(
        model_manifest=manifest,
        manifest_path=W15_MODEL_DIR / "model-manifest-W15.json",
        registry=registry,
        config=config,
        model_path=W15_MODEL_DIR / "model.ubj",
    )
    assert declared.approved_freeze_status == (
        "APPROVED_RELEASE_FREEZE_DECLARED_UNVERIFIED"
    )


def test_development_baseline_is_not_release_freeze(context):
    _, _, _, baseline = context
    comparison = compare_freeze_state(baseline)
    assert baseline.approved_freeze_status == MISSING_FREEZE_RECORD
    assert comparison.approved_status == MISSING_FREEZE_RECORD
    assert comparison.development_unchanged_implies_release_freeze is False
    assert comparison.development_status == DEVELOPMENT_BASELINE_UNCHANGED


@pytest.mark.parametrize(
    "field_id, value",
    [
        (
            "operating_threshold",
            {"value": 0.6, "status": "ILLUSTRATIVE_NOT_FROZEN", "config_value": 0.5},
        ),
        (
            "warning_persistence",
            {"status": "FROZEN", "k": 3},
        ),
        (
            "primary_horizon",
            {
                "horizon_s": 120.0,
                "horizon_status": "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN",
                "config_horizon_s": 60.0,
            },
        ),
        (
            "calibration_semantics",
            {
                "status": "CALIBRATED",
                "score_semantics": "calibrated_probability",
                "config_status": "NOT_PERFORMED",
            },
        ),
        (
            "event_matching_policy",
            {"episode_status": "FROZEN_APPROVED", "association_status": "SYNTHETIC_ILLUSTRATIVE"},
        ),
        ("feature_schema_hash", "f" * 64),
        ("ordered_feature_ids_sha256", "e" * 64),
    ],
)
def test_protected_field_drift_is_detected(context, field_id, value):
    _, _, _, baseline = context
    observed = apply_declared_change(baseline, {field_id: value})
    comparison = compare_freeze_state(baseline, observed)
    assert comparison.development_status == DEVELOPMENT_BASELINE_CHANGED
    assert field_id in comparison.drift_fields


def test_model_swap_preserving_old_identity_is_detected(context):
    _, _, _, baseline = context
    observed = apply_declared_change(
        baseline, {"model_artifact_sha256": "c" * 64}
    )
    comparison = compare_freeze_state(baseline, observed)
    assert comparison.identity_reused is True
    assert "MODEL_IDENTITY_REUSED_FOR_NEW_BYTES" in comparison.issues
    assert "model_artifact_sha256" in comparison.drift_fields


def test_model_bytes_changed_without_identity_update_is_detected(
    context, tmp_path
):
    _, _, _, baseline = context
    tampered = tmp_path / "model.ubj"
    payload = bytearray((W15_MODEL_DIR / "model.ubj").read_bytes())
    payload[0] ^= 0xFF
    tampered.write_bytes(bytes(payload))
    result = verify_model_file_binding(baseline, tampered)
    assert result["matches"] is False
    assert result["reason_code"] == "MODEL_BYTES_CHANGED_WITHOUT_IDENTITY_UPDATE"


def test_missing_model_file_is_detected(context, tmp_path):
    _, _, _, baseline = context
    result = verify_model_file_binding(baseline, tmp_path / "missing.ubj")
    assert result["matches"] is False
    assert result["reason_code"] == "MODEL_FILE_MISSING"


def test_baseline_refuses_model_bytes_that_do_not_match_manifest(
    context, tmp_path
):
    model, registry, config, _ = context
    tampered = tmp_path / "model.ubj"
    payload = bytearray((W15_MODEL_DIR / "model.ubj").read_bytes())
    payload[-1] ^= 0xFF
    tampered.write_bytes(bytes(payload))
    with pytest.raises(FreezeAuditError):
        build_freeze_baseline(
            model_manifest=model.manifest,
            manifest_path=W15_MODEL_DIR / "model-manifest-W15.json",
            registry=registry,
            config=config,
            model_path=tampered,
        )


def test_valid_change_requires_new_evaluation(context):
    _, _, _, baseline = context
    decision = assess_change_request(
        _valid_change(baseline), baseline=baseline, locked_test_exposed=False
    )
    assert decision.decision == CHANGE_ACCEPTED_REQUIRES_NEW_EVALUATION
    assert decision.approval_effect == "NONE_B_W18_READ_ONLY_ASSESSMENT"


def test_change_without_comparability_declaration_is_pending(context):
    _, _, _, baseline = context
    request = _valid_change(baseline)
    request.pop("comparability")
    decision = assess_change_request(
        request, baseline=baseline, locked_test_exposed=False
    )
    assert decision.decision == CHANGE_ACCEPTED_PENDING_REVIEW


def test_incomplete_change_is_refused(context):
    _, _, _, baseline = context
    request = _valid_change(baseline)
    request.pop("reason")
    decision = assess_change_request(
        request, baseline=baseline, locked_test_exposed=False
    )
    assert decision.decision == CHANGE_REFUSED_INCOMPLETE


def test_unchanged_identity_is_refused(context):
    _, _, _, baseline = context
    request = _valid_change(baseline)
    request["artifact_id"] = baseline.values["model_artifact_id"]
    request["model_artifact_sha256"] = baseline.values["model_artifact_sha256"]
    decision = assess_change_request(
        request, baseline=baseline, locked_test_exposed=False
    )
    assert decision.decision == CHANGE_REFUSED_NOT_A_NEW_IDENTITY


def test_fake_approval_metadata_is_refused(context):
    _, _, _, baseline = context
    request = _valid_change(baseline)
    request["review_gate"] = {
        "status": "APPROVED_BY_AUTHORITY",
        "reviewer": "anonymous",
    }
    decision = assess_change_request(
        request, baseline=baseline, locked_test_exposed=False
    )
    assert decision.decision == CHANGE_REFUSED_FAKE_APPROVAL


def test_post_locked_test_comparability_overclaim_is_refused(context):
    _, _, _, baseline = context
    request = _valid_change(baseline)
    request["comparability"] = "PRIOR_TESTS_COMPARABLE"
    decision = assess_change_request(
        request, baseline=baseline, locked_test_exposed=True
    )
    assert decision.decision == CHANGE_REFUSED_LOCKED_TEST_REUSE


def test_post_locked_test_requires_new_evaluation(context):
    _, _, _, baseline = context
    decision = assess_change_request(
        _valid_change(baseline), baseline=baseline, locked_test_exposed=True
    )
    assert decision.decision == CHANGE_ACCEPTED_REQUIRES_NEW_EVALUATION


def test_post_locked_test_comparability_must_be_declared(context):
    _, _, _, baseline = context
    request = _valid_change(baseline)
    request.pop("comparability")
    decision = assess_change_request(
        request, baseline=baseline, locked_test_exposed=True
    )
    assert decision.decision == CHANGE_REFUSED_COMPARABILITY_UNDECLARED
