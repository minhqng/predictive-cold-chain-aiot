"""W18 B-W18-01 runtime-monitor controls.

Positive controls use the committed W17 replay record shape; negative controls
mutate an in-memory copy and must be refused for the expected reason.  No test
connects to a device or broker.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from coldguard_ml.feature_registry import load_registry
from coldguard_ml.w15_artifact import load_guarded_artifact
from coldguard_ml.w18_runtime_monitor import (
    MONITOR_SOFTWARE_VALID,
    REFUSED_EVIDENCE_CLASS,
    REFUSED_FEATURE_IDENTITY,
    REFUSED_MODEL_IDENTITY,
    REFUSED_POLICY_UNFROZEN,
    REFUSED_PREDICTION_SEMANTICS,
    REFUSED_RELEASE_AUTHORIZATION,
    REFUSED_STALE_INPUT,
    REFUSED_TEMPORAL_ORDER,
    REFUSED_UNTRUSTED_INPUT,
    MonitorError,
    MonitorRecordError,
    audit_runtime_sequence,
    expected_runtime_identity,
    monitor_runtime_record,
    monitor_runtime_records,
    policy_expectation_from_w17_header,
)
from coldguard_ml.xgb_benchmark import load_benchmark_config

ROOT = Path(__file__).resolve().parents[1]
W17_TRACE = ROOT / "reports" / "W17" / "shadow-trace-W17.json"
W15_MODEL_DIR = ROOT / "reports" / "W15" / "model"


@pytest.fixture(scope="module")
def expected():
    registry = load_registry()
    config = load_benchmark_config(ROOT / "xgb-v1-config.yaml", registry)
    model = load_guarded_artifact(
        manifest_path=W15_MODEL_DIR / "model-manifest-W15.json",
        model_path=W15_MODEL_DIR / "model.ubj",
        expected_feature_ids=config.feature_policy.allowlist,
        expected_feature_schema_hash=registry.schema_sha256,
        expected_model_config_hash=config.config_sha256,
    )
    return expected_runtime_identity(
        model_manifest=model.manifest, registry=registry, config=config
    )


@pytest.fixture(scope="module")
def trace():
    return json.loads(W17_TRACE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def policy(expected, trace):
    return policy_expectation_from_w17_header(trace["header"], expected)


@pytest.fixture(scope="module")
def record(trace):
    return copy.deepcopy(trace["records"][0])


def _mutate(record, mutate) -> dict:
    candidate = copy.deepcopy(record)
    mutate(candidate)
    return candidate


def _verdict(record, expected, policy, mutate) -> str:
    result = monitor_runtime_record(
        _mutate(record, mutate), expected=expected, policy=policy
    )
    return result.verdict


def test_positive_control_is_software_valid(record, expected, policy):
    result = monitor_runtime_record(record, expected=expected, policy=policy)
    assert result.verdict == MONITOR_SOFTWARE_VALID
    assert result.identity_match is True
    assert result.evidence_quality is True
    assert result.scientific_release_eligibility is False
    assert result.physical_authorization is False
    assert result.release_claim is False
    assert result.control_claim is False
    assert result.refusal_reasons == ()


def test_identity_match_never_implies_release_or_physical_authorization(
    record, expected, policy
):
    result = monitor_runtime_record(record, expected=expected, policy=policy)
    assert result.identity_match is True
    assert result.scientific_release_eligibility is False
    assert result.physical_authorization is False


def test_full_w17_replay_is_monitored(record, trace, expected, policy):
    audit = monitor_runtime_records(trace["records"], expected=expected, policy=policy)
    assert len(audit.results) == trace["record_count"] == 783
    assert audit.verdict_counts == {MONITOR_SOFTWARE_VALID: 783}
    assert audit.identity_match_all is True
    assert audit.release_claim_count == 0
    assert audit.control_claim_count == 0
    assert audit.sequence.passed is True
    assert audit.sequence.group_count == 16


def _wrong_model_sha(candidate):
    candidate["model"]["model_artifact_sha256"] = "0" * 64


def _wrong_artifact_id(candidate):
    candidate["model"]["artifact_id"] = "coldguard-other-model"


def _wrong_config_sha(candidate):
    candidate["model"]["model_config_sha256"] = "1" * 64


def _wrong_library(candidate):
    candidate["model"]["model_library_version"] = "0.0.0"


def _missing_model(candidate):
    candidate["model"] = {}


def _wrong_order_hash(candidate):
    candidate["ordered_feature_ids_sha256"] = "2" * 64


def _wrong_vector_hash(candidate):
    candidate["feature_vector_sha256"] = "3" * 64


def _swapped_features(candidate):
    candidate["features"][0]["feature_id"], candidate["features"][1]["feature_id"] = (
        candidate["features"][1]["feature_id"],
        candidate["features"][0]["feature_id"],
    )


def _zero_fill(candidate):
    candidate["features"][0]["value"] = 0.0
    candidate["features"][0]["missing_reason"] = "MISSING_INPUT"


def _wrong_schema(candidate):
    candidate["feature_schema_sha256"] = "4" * 64


def _release_claim(candidate):
    candidate["model"]["registered_for_operation"] = True


def _deployed_claim(candidate):
    candidate["model"]["deployed"] = True


def _physical_evidence_claim(candidate):
    candidate["evidence_class"] = "REAL_PHYSICAL_EVIDENCE"


def _frozen_warning_rule(candidate):
    candidate["hypothetical_warning"]["rule_status"] = "FROZEN_APPROVED"


def _frozen_persistence(candidate):
    candidate["prediction_policy"] = {"warning_persistence_status": "FROZEN"}


def _frozen_horizon(candidate):
    candidate["prediction_policy"] = {"horizon_status": "FROZEN"}


def _dispatchable_policy(candidate):
    candidate["hypothetical_policy"]["dispatchable"] = True


def _authorized_policy(candidate):
    candidate["hypothetical_policy"]["authorized_control_decision"] = "AUTHORIZED"


def _probability_semantics(candidate):
    candidate["score_semantics"] = "calibrated_probability"


def _missing_fresh_score(candidate):
    candidate["risk_score"] = None


def _stale_with_score(candidate):
    candidate["freshness"] = {
        "verdict": "REFUSED_STALE_INPUT",
        "disposition": "REFUSED_STALE_INPUT",
        "reasons": ["TEST_STALE"],
        "policy_status": "RUNTIME_FRESHNESS_POLICY_PENDING_C_D",
    }


def _untrusted_with_score(candidate):
    candidate["freshness"] = {
        "verdict": "REFUSED_UNTRUSTED_INPUT",
        "disposition": "REFUSED_UNTRUSTED_INPUT",
        "reasons": ["TEST_UNTRUSTED"],
        "policy_status": "RUNTIME_FRESHNESS_POLICY_PENDING_C_D",
    }


def _future_window(candidate):
    candidate["input_window_end_s"] = (
        float(candidate["prediction_anchor_event_s"]) + 1.0
    )


def _missing_event_time(candidate):
    candidate.pop("prediction_anchor_event_s", None)


def _tampered_input_ids(candidate):
    candidate["input_telemetry_ids"] = list(candidate["input_telemetry_ids"]) + [
        "tel-forged"
    ]


@pytest.mark.parametrize(
    "mutate, expected_verdict",
    [
        (_wrong_model_sha, REFUSED_MODEL_IDENTITY),
        (_wrong_artifact_id, REFUSED_MODEL_IDENTITY),
        (_wrong_config_sha, REFUSED_MODEL_IDENTITY),
        (_wrong_library, REFUSED_MODEL_IDENTITY),
        (_missing_model, REFUSED_MODEL_IDENTITY),
        (_wrong_order_hash, REFUSED_FEATURE_IDENTITY),
        (_wrong_vector_hash, REFUSED_FEATURE_IDENTITY),
        (_swapped_features, REFUSED_FEATURE_IDENTITY),
        (_zero_fill, REFUSED_FEATURE_IDENTITY),
        (_wrong_schema, REFUSED_FEATURE_IDENTITY),
        (_release_claim, REFUSED_RELEASE_AUTHORIZATION),
        (_deployed_claim, REFUSED_RELEASE_AUTHORIZATION),
        (_physical_evidence_claim, REFUSED_EVIDENCE_CLASS),
        (_frozen_warning_rule, REFUSED_POLICY_UNFROZEN),
        (_frozen_persistence, REFUSED_POLICY_UNFROZEN),
        (_frozen_horizon, REFUSED_POLICY_UNFROZEN),
        (_dispatchable_policy, REFUSED_RELEASE_AUTHORIZATION),
        (_authorized_policy, REFUSED_RELEASE_AUTHORIZATION),
        (_probability_semantics, REFUSED_PREDICTION_SEMANTICS),
        (_missing_fresh_score, REFUSED_PREDICTION_SEMANTICS),
        (_stale_with_score, REFUSED_STALE_INPUT),
        (_untrusted_with_score, REFUSED_UNTRUSTED_INPUT),
        (_future_window, REFUSED_TEMPORAL_ORDER),
        (_missing_event_time, REFUSED_TEMPORAL_ORDER),
        (_tampered_input_ids, REFUSED_STALE_INPUT),
    ],
)
def test_negative_controls_are_refused(record, expected, policy, mutate, expected_verdict):
    assert _verdict(record, expected, policy, mutate) == expected_verdict


def test_release_claim_does_not_invalidate_identity(record, expected, policy):
    result = monitor_runtime_record(
        _mutate(record, _release_claim), expected=expected, policy=policy
    )
    assert result.verdict == REFUSED_RELEASE_AUTHORIZATION
    assert result.release_claim is True
    assert result.identity_match is True
    assert result.evidence_quality is True
    assert result.scientific_release_eligibility is False


def test_dispatchable_claim_does_not_invalidate_identity(record, expected, policy):
    result = monitor_runtime_record(
        _mutate(record, _dispatchable_policy), expected=expected, policy=policy
    )
    assert result.verdict == REFUSED_RELEASE_AUTHORIZATION
    assert result.control_claim is True
    assert result.identity_match is True
    assert result.physical_authorization is False


def test_release_eligibility_claim_does_not_invalidate_identity(
    record, expected, policy
):
    def mutate(candidate):
        candidate["model"]["release_eligibility"] = "APPROVED_RELEASE_CANDIDATE"

    result = monitor_runtime_record(
        _mutate(record, mutate), expected=expected, policy=policy
    )
    assert result.verdict == REFUSED_RELEASE_AUTHORIZATION
    assert result.release_claim is True
    assert result.identity_match is True
    assert result.scientific_release_eligibility is False


def test_evidence_class_claim_does_not_invalidate_identity(
    record, expected, policy
):
    result = monitor_runtime_record(
        _mutate(record, _physical_evidence_claim), expected=expected, policy=policy
    )
    assert result.verdict == REFUSED_EVIDENCE_CLASS
    assert result.identity_match is True


def test_refused_input_without_score_is_not_trusted(record, expected, policy):
    def mutate(candidate):
        candidate["risk_score"] = None
        candidate["freshness"] = {
            "verdict": "REFUSED_STALE_INPUT",
            "disposition": "REFUSED_STALE_INPUT",
            "reasons": ["TEST_STALE"],
            "policy_status": "RUNTIME_FRESHNESS_POLICY_PENDING_C_D",
        }

    result = monitor_runtime_record(
        _mutate(record, mutate), expected=expected, policy=policy
    )
    assert result.verdict == REFUSED_STALE_INPUT
    assert "SCORE_PRODUCED_FOR_REFUSED_INPUT" not in result.refusal_reasons
    assert result.identity_match is True


def test_w17_header_policy_is_synthetic_and_pending(expected, trace):
    policy = policy_expectation_from_w17_header(trace["header"], expected)
    assert policy.operating_threshold == expected.operating_threshold
    assert policy.operating_threshold_status == "ILLUSTRATIVE_NOT_FROZEN"
    assert policy.warning_persistence_status == "NOT_FROZEN"
    assert policy.runtime_freshness_policy_status == (
        "RUNTIME_FRESHNESS_POLICY_PENDING_C_D"
    )


def test_w17_header_threshold_change_is_refused(expected, trace):
    header = copy.deepcopy(trace["header"])
    header["warning_rule"]["threshold"] = 0.6
    with pytest.raises(MonitorError):
        policy_expectation_from_w17_header(header, expected)


def test_w17_header_frozen_rule_is_refused(expected, trace):
    header = copy.deepcopy(trace["header"])
    header["warning_rule"]["status"] = "FROZEN_APPROVED"
    with pytest.raises(MonitorError):
        policy_expectation_from_w17_header(header, expected)


def _load_manifest():
    return json.loads(
        (W15_MODEL_DIR / "model-manifest-W15.json").read_text(encoding="utf-8")
    )


def _registry_and_config():
    registry = load_registry()
    config = load_benchmark_config(ROOT / "xgb-v1-config.yaml", registry)
    return registry, config


def test_expected_identity_refuses_release_claim():
    registry, config = _registry_and_config()
    manifest = _load_manifest()
    manifest["release_eligibility"] = "APPROVED_RELEASE_CANDIDATE"
    with pytest.raises(MonitorError):
        expected_runtime_identity(
            model_manifest=manifest, registry=registry, config=config
        )


def test_expected_identity_refuses_frozen_horizon():
    registry, config = _registry_and_config()
    manifest = _load_manifest()
    manifest["horizon_status"] = "FROZEN"
    with pytest.raises(MonitorError):
        expected_runtime_identity(
            model_manifest=manifest, registry=registry, config=config
        )


def test_malformed_record_is_not_a_refusal(record):
    candidate = copy.deepcopy(record)
    candidate["features"] = "not-a-list"
    with pytest.raises(MonitorRecordError):
        monitor_runtime_record(candidate, expected=None)


def test_reconnect_does_not_revive_obsolete_state(record, expected, policy):
    def mutate(candidate):
        candidate["boot_id"] = "CG-W11-S1-003-BOOT-2"
        candidate["freshness"] = {
            "verdict": "REFUSED_STALE_INPUT",
            "disposition": "REFUSED_STALE_INPUT",
            "reasons": ["TEST_RECONNECT_OBSOLETE_STATE"],
            "policy_status": "RUNTIME_FRESHNESS_POLICY_PENDING_C_D",
        }

    result = monitor_runtime_record(
        _mutate(record, mutate), expected=expected, policy=policy
    )
    assert result.verdict == REFUSED_STALE_INPUT
    assert result.identity_match is True
    assert result.evidence_quality is False


def test_sequence_audit_detects_duplicate_and_contradiction(record):
    first = copy.deepcopy(record)
    duplicate = copy.deepcopy(record)
    duplicate["prediction_id"] = "pred-w17-duplicate"
    contradictory = copy.deepcopy(record)
    contradictory["risk_score"] = 0.0001
    audit = audit_runtime_sequence([first, duplicate, contradictory])
    assert "DUPLICATE_SEQUENCE_IN_BOOT" in audit.issues
    assert "PREDICTION_ID_REUSED_WITH_CONTRADICTORY_CONTENT" in audit.issues
    assert audit.passed is False
