"""W18 B-W18-02 trace-integrity controls.

The TEST_ONLY fixture proves parsing and refusal behavior; it never proves
electrical or thermal execution.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from coldguard_ml.feature_registry import load_registry
from coldguard_ml.w15_artifact import load_guarded_artifact
from coldguard_ml.w18_runtime_monitor import expected_runtime_identity
from coldguard_ml.w18_trace_integrity import (
    FIXTURE_EVIDENCE_CLASS,
    PHYSICAL_FIXTURE_EVIDENCE_CLASS,
    TRACE_COMPLETE_SOFTWARE_FIXTURE,
    TRACE_INCONSISTENT_IDENTITY,
    TRACE_NOT_AUTHORIZED,
    TRACE_PARTIAL_MISSING_EVIDENCE,
    TRACE_PHYSICAL_UNVERIFIED,
    TRACE_TEMPORAL_CONTRADICTION,
    TraceError,
    assess_trace,
    build_test_only_fixture,
    summarize_w17_replay_trace,
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
def fixture(expected):
    return build_test_only_fixture(
        model_artifact_sha256=expected.model_artifact_sha256,
        feature_schema_sha256=expected.feature_schema_sha256,
        ordered_feature_ids_sha256=expected.ordered_feature_ids_sha256,
    )


def _mutate(fixture, mutate) -> dict:
    candidate = copy.deepcopy(fixture)
    mutate(candidate)
    return candidate


def test_complete_fixture_is_structurally_valid(fixture):
    assessment = assess_trace(fixture)
    assert assessment.outcome == TRACE_COMPLETE_SOFTWARE_FIXTURE
    assert assessment.missing_stages == ()
    assert assessment.physical_verified is False
    assert assessment.authorized_control is False
    assert assessment.real_intervention is False
    assert assessment.controller_b_acceptance is False
    assert assessment.physical_evidence_class == PHYSICAL_FIXTURE_EVIDENCE_CLASS
    assert assessment.refusal_reasons == ()


def test_fixture_hygiene(fixture):
    assert fixture["fixture"] is True
    assert fixture["evidence_class"] == FIXTURE_EVIDENCE_CLASS
    assert fixture["claimed_physical_success"] is False
    assert fixture["command"]["dispatchable"] is False
    assert fixture["command"]["transport"] == "NONE_TEST_FIXTURE"
    assert fixture["command"]["destination"].startswith("TEST_ONLY")
    assert fixture["command"]["hypothetical_test_record"] is True
    assert fixture["policy"]["decision_status"] == "HYPOTHETICAL"
    assert fixture["policy"]["authorization"] is None


def _remove_downstream(candidate):
    for stage in ("command", "ack", "applied_state", "physical_verification"):
        candidate.pop(stage, None)


def _command_prediction_mismatch(candidate):
    candidate["command"]["prediction_id"] = "pred-other-run"


def _ack_before_command(candidate):
    candidate["ack"]["acknowledged_event_s"] = 100.9


def _ack_shortcut(candidate):
    candidate.pop("physical_verification", None)
    candidate["command"]["status"] = "SUCCEEDED"


def _fixture_claims_success(candidate):
    candidate["claimed_physical_success"] = True


def _unmarked_hypothetical_command(candidate):
    candidate["command"]["hypothetical_test_record"] = False


def _remove_thermal(candidate):
    candidate["physical_verification"]["thermal_response"] = None


def _remove_physical(candidate):
    candidate.pop("physical_verification", None)


def _mislabel_fixture(candidate):
    candidate["fixture"] = False


def _authorized_without_evidence(candidate):
    candidate["policy"]["decision_status"] = "AUTHORIZED"


def _terminal_contradiction(candidate):
    candidate["command"]["status"] = "SUCCEEDED"
    candidate["ack"]["ack_status"] = "REJECTED"


def _policy_run_mismatch(candidate):
    candidate["policy"]["run_id"] = "run-other"


def _electrical_quality_unknown(candidate):
    candidate["physical_verification"]["electrical_response"]["quality"] = "UNKNOWN"


def _claimed_success_without_command(candidate):
    for stage in ("command", "ack", "applied_state", "physical_verification"):
        candidate.pop(stage, None)
    candidate["fixture"] = False
    candidate["evidence_class"] = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    candidate["claimed_physical_success"] = True


def _remove_applied_state(candidate):
    candidate.pop("applied_state", None)


def _physical_without_command(candidate):
    for stage in ("command", "ack", "applied_state"):
        candidate.pop(stage, None)


def _parent_class_only_physical(candidate):
    candidate["fixture"] = False
    candidate["evidence_class"] = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    candidate["physical_verification"]["evidence_class"] = "MEASURED_PHYSICAL_DATA"


def _electrical_before_command_without_ack(candidate):
    candidate.pop("ack", None)
    candidate.pop("applied_state", None)
    candidate["physical_verification"]["electrical_response"][
        "observation_event_s"
    ] = 100.5


def _cross_boot(candidate):
    candidate["physical_verification"]["boot_id"] = "boot-other"


@pytest.mark.parametrize(
    "mutate, expected_outcome",
    [
        (_remove_downstream, TRACE_PARTIAL_MISSING_EVIDENCE),
        (_remove_applied_state, TRACE_PARTIAL_MISSING_EVIDENCE),
        (_command_prediction_mismatch, TRACE_INCONSISTENT_IDENTITY),
        (_policy_run_mismatch, TRACE_INCONSISTENT_IDENTITY),
        (_ack_before_command, TRACE_TEMPORAL_CONTRADICTION),
        (
            _electrical_before_command_without_ack,
            TRACE_TEMPORAL_CONTRADICTION,
        ),
        (_ack_shortcut, TRACE_PHYSICAL_UNVERIFIED),
        (_electrical_quality_unknown, TRACE_PHYSICAL_UNVERIFIED),
        (_parent_class_only_physical, TRACE_PHYSICAL_UNVERIFIED),
        (_claimed_success_without_command, TRACE_PHYSICAL_UNVERIFIED),
        (_physical_without_command, TRACE_NOT_AUTHORIZED),
        (_fixture_claims_success, TRACE_INCONSISTENT_IDENTITY),
        (_unmarked_hypothetical_command, TRACE_NOT_AUTHORIZED),
        (_remove_thermal, TRACE_PHYSICAL_UNVERIFIED),
        (_remove_physical, TRACE_PHYSICAL_UNVERIFIED),
        (_mislabel_fixture, TRACE_INCONSISTENT_IDENTITY),
        (_authorized_without_evidence, TRACE_NOT_AUTHORIZED),
        (_terminal_contradiction, TRACE_INCONSISTENT_IDENTITY),
        (_cross_boot, TRACE_INCONSISTENT_IDENTITY),
    ],
)
def test_negative_controls_are_refused(fixture, mutate, expected_outcome):
    assessment = assess_trace(_mutate(fixture, mutate))
    assert assessment.outcome == expected_outcome


def test_missing_stages_are_explicit(fixture):
    assessment = assess_trace(_mutate(fixture, _remove_downstream))
    assert "command" in assessment.missing_stages
    assert "ack" in assessment.missing_stages
    assert "physical_verification" in assessment.missing_stages


def test_ack_is_not_physical_evidence(fixture):
    assessment = assess_trace(_mutate(fixture, _ack_shortcut))
    assert "ACK_IS_NOT_PHYSICAL_EVIDENCE" in assessment.refusal_reasons
    assert assessment.physical_verified is False


def test_fixture_is_not_live_controller_b_evidence(fixture):
    assessment = assess_trace(fixture)
    assert assessment.outcome == TRACE_COMPLETE_SOFTWARE_FIXTURE
    assert assessment.controller_b_acceptance is False
    assert assessment.physical_verified is False
    assert fixture["evidence_class"] == "TEST_ONLY_SYNTHETIC_FIXTURE"


def test_w17_replay_is_partial_and_physical_chain_unavailable():
    payload = json.loads(W17_TRACE.read_text(encoding="utf-8"))
    summary = summarize_w17_replay_trace(payload)
    assert summary.outcome == TRACE_PARTIAL_MISSING_EVIDENCE
    assert summary.record_count == 783
    assert summary.records_copied is False
    assert summary.trace_sha256_valid is True
    assert summary.stage_status["policy"] == "HYPOTHETICAL_ONLY_NOT_EVALUATED"
    assert summary.stage_status["command"] == "ABSENT"
    assert summary.stage_status["physical_verification"] == "ABSENT"
    assert "command" in summary.missing_stages
    assert "physical_verification" in summary.missing_stages
    assert summary.physical_chain_status.startswith("PHYSICAL_CHAIN_UNAVAILABLE")
    assert summary.physical_control_capability is False


def test_tampered_w17_trace_is_rejected():
    payload = json.loads(W17_TRACE.read_text(encoding="utf-8"))
    payload["records"][0]["risk_score"] = 0.0
    with pytest.raises(TraceError):
        summarize_w17_replay_trace(payload)


def test_malformed_trace_is_not_missing_physical_acceptance(fixture):
    malformed = copy.deepcopy(fixture)
    malformed["identity"] = {"run_id": "run-only"}
    with pytest.raises(TraceError):
        assess_trace(malformed)


def test_wrong_trace_schema_is_rejected(fixture):
    malformed = copy.deepcopy(fixture)
    malformed["trace_schema"] = "coldguard-w17-shadow-trace-v1"
    with pytest.raises(TraceError):
        assess_trace(malformed)
