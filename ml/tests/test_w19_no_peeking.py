"""W19 B-W19-03 no-significance-peeking and no-analysis guards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coldguard_ml.w19_no_peeking import (
    ALLOWED_STOP_REASONS,
    FREEZE_FROZEN_APPROVED,
    FREEZE_INCOMPLETE,
    FREEZE_NOT_FROZEN,
    HOLDOUT_NOT_OPENED,
    HOLDOUT_OPENED,
    HOLDOUT_UNKNOWN,
    MUTATION_ACCEPTED_REQUIRES_NEW_FREEZE,
    MUTATION_REFUSED_MISSING_APPROVAL,
    MUTATION_REFUSED_POST_CAMPAIGN_START,
    MUTATION_REFUSED_UNKNOWN_RULE,
    OPERATION_ALLOWED,
    OPERATION_PROHIBITED,
    OPERATION_UNKNOWN,
    REGISTERED_SIGN_CONVENTION,
    STATISTICAL_FREEZE_FIELDS,
    STOP_ALLOWED,
    STOP_REFUSED,
    W19OutcomeExposureError,
    W19PeekingError,
    assert_outcome_blind,
    assess_frozen_rule_change,
    assess_statistical_freeze,
    audit_source_capability,
    classify_w19_operation,
    require_w19_operation,
    validate_stop_reason,
    w16_holdout_status,
)

ML_ROOT = Path(__file__).resolve().parents[1]


def _w19_sources() -> list[Path]:
    return [
        ML_ROOT / "src" / "coldguard_ml" / "w19_no_peeking.py",
        ML_ROOT / "src" / "coldguard_ml" / "w19_validity.py",
        ML_ROOT / "src" / "coldguard_ml" / "w19_pair_ledger.py",
        ML_ROOT / "src" / "coldguard_ml" / "w19_progress.py",
        ML_ROOT / "scripts" / "w19-campaign-audit-W19.py",
        ML_ROOT / "tests" / "test_w19_pair_ledger.py",
        ML_ROOT / "tests" / "test_w19_validity.py",
        ML_ROOT / "tests" / "test_w19_no_peeking.py",
        ML_ROOT / "tests" / "test_w19_progress.py",
        ML_ROOT / "tests" / "test_w19_delivery.py",
    ]


def _statistical_freeze_record() -> dict:
    return {
        "status": FREEZE_FROZEN_APPROVED,
        "fields": {
            "primary_outcome": "thermal_exposure",
            "paired_sign_convention": REGISTERED_SIGN_CONVENTION,
            "confidence_level": 0.95,
            "bootstrap_seed": 20261110,
            "bootstrap_iterations": 5000,
            "test_family": "predeclared-frozen",
            "invalid_pair_handling": "predeclared-frozen",
            "secondary_outcomes": ["recovery_time", "branch_energy"],
        },
        "approval": {
            "authority_id": "TEST_FIXTURE_ONLY",
            "authority_role": "TEAM_LEAD",
            "canonical_ref": "test://w19/fixture-statistical-freeze",
        },
    }


def test_allowed_and_prohibited_operations_are_explicit():
    assert classify_w19_operation("pair_eligibility").classification == OPERATION_ALLOWED
    assert classify_w19_operation("pair_eligibility").outcome_access is False
    assert (
        classify_w19_operation("headline_p_value").classification
        == OPERATION_PROHIBITED
    )
    assert (
        classify_w19_operation("confidence_interval_final_effect").classification
        == OPERATION_PROHIBITED
    )
    assert classify_w19_operation("not_declared").classification == OPERATION_UNKNOWN


def test_prohibited_and_unknown_operations_are_refused_at_runtime():
    with pytest.raises(W19PeekingError):
        require_w19_operation("headline_p_value")
    with pytest.raises(W19PeekingError):
        require_w19_operation("mean_controller_b_benefit")
    with pytest.raises(W19PeekingError):
        require_w19_operation("unknown_operation")
    permit = require_w19_operation("campaign_progress")
    assert permit.outcome_access is False


def test_outcome_payload_is_refused_anywhere_in_a_nested_structure():
    assert_outcome_blind({"pair_id": "PAIR-1", "validity_status": "VALID"})
    with pytest.raises(W19OutcomeExposureError):
        assert_outcome_blind({"p_value": 0.04})
    with pytest.raises(W19OutcomeExposureError):
        assert_outcome_blind({"pairs": [{"outcome": 1.0}]})
    with pytest.raises(W19OutcomeExposureError):
        assert_outcome_blind({"nested": {"branch_energy": 12}})


def test_statistical_stop_reason_is_refused():
    decision = validate_stop_reason(
        "FAVORABLE_INTERIM_RESULT", "test://interim-note"
    )
    assert decision.decision == STOP_REFUSED
    assert decision.reason_class == "STATISTICAL"
    assert "STOP_REASON_STATISTICAL_PEEKING_PROHIBITED" in decision.refusal_reasons


def test_unknown_stop_reason_is_refused():
    decision = validate_stop_reason("LOOKS_GOOD", "test://note")
    assert decision.decision == STOP_REFUSED
    assert decision.reason_class == "UNKNOWN"


def test_operational_stop_requires_bound_evidence():
    refused = validate_stop_reason("SAFETY_RESTRICTION", "")
    assert refused.decision == STOP_REFUSED
    allowed = validate_stop_reason("SAFETY_RESTRICTION", "test://safety-log")
    assert allowed.decision == STOP_ALLOWED
    assert allowed.reason_class == "OPERATIONAL"
    assert allowed.effect_on_analysis == "OPERATIONAL_STOP_NOT_STATISTICAL_EVIDENCE"
    assert set(ALLOWED_STOP_REASONS) == {
        "SAFETY_RESTRICTION",
        "EQUIPMENT_FAILURE",
        "FEASIBILITY_RESTRICTION",
        "AUTHORIZED_OPERATIONAL_CHANGE",
    }


def test_frozen_rule_change_is_refused_after_pairs_are_recorded():
    decision = assess_frozen_rule_change(
        "pair_target", approval_ref="test://approval", pairs_recorded=1
    )
    assert decision.decision == MUTATION_REFUSED_POST_CAMPAIGN_START


def test_frozen_rule_change_requires_approval_before_campaign_start():
    missing = assess_frozen_rule_change(
        "invalid_pair_handling", approval_ref=None, pairs_recorded=0
    )
    assert missing.decision == MUTATION_REFUSED_MISSING_APPROVAL
    accepted = assess_frozen_rule_change(
        "primary_outcome", approval_ref="test://approval", pairs_recorded=0
    )
    assert accepted.decision == MUTATION_ACCEPTED_REQUIRES_NEW_FREEZE
    unknown = assess_frozen_rule_change(
        "something_else", approval_ref="test://approval", pairs_recorded=0
    )
    assert unknown.decision == MUTATION_REFUSED_UNKNOWN_RULE


def test_missing_statistical_freeze_is_not_frozen():
    assessment = assess_statistical_freeze(None)
    assert assessment.status == FREEZE_NOT_FROZEN
    assert assessment.registered_sign_convention == REGISTERED_SIGN_CONVENTION
    assert set(assessment.missing_fields) == set(STATISTICAL_FREEZE_FIELDS)


def test_complete_statistical_freeze_is_approved():
    assessment = assess_statistical_freeze(_statistical_freeze_record())
    assert assessment.status == FREEZE_FROZEN_APPROVED
    assert assessment.registered_sign_convention == REGISTERED_SIGN_CONVENTION


def test_statistical_freeze_sign_convention_mismatch_is_refused():
    record = _statistical_freeze_record()
    record["fields"]["paired_sign_convention"] = "I_i = Y_B - Y_A"
    assessment = assess_statistical_freeze(record)
    assert assessment.status == FREEZE_INCOMPLETE
    assert "SIGN_CONVENTION_MISMATCH" in assessment.refusal_reasons


def test_statistical_freeze_without_approval_is_incomplete():
    record = _statistical_freeze_record()
    record["approval"] = {"authority_id": "", "authority_role": "TEAM_LEAD"}
    assessment = assess_statistical_freeze(record)
    assert assessment.status == FREEZE_INCOMPLETE
    assert "STATISTICAL_FREEZE_APPROVAL_INVALID" in assessment.refusal_reasons


def test_statistical_freeze_rejects_unknown_fields():
    record = _statistical_freeze_record()
    record["extra"] = True
    with pytest.raises(W19PeekingError):
        assess_statistical_freeze(record)


def test_real_w16_manifest_holdout_is_not_opened():
    manifest = json.loads(
        (ML_ROOT / "reports" / "W16" / "locked-test-manifest-W16.json").read_text(
            encoding="utf-8"
        )
    )
    status = w16_holdout_status(manifest)
    assert status.status == HOLDOUT_NOT_OPENED
    assert not status.opened_at
    assert status.test_partition_used is not True


def test_opened_holdout_is_detected():
    manifest = {
        "split_identity": {
            "locked_test": {
                "frozen": True,
                "opened_at": "2026-01-01",
                "test_partition_used": True,
            }
        }
    }
    status = w16_holdout_status(manifest)
    assert status.status == HOLDOUT_OPENED


def test_missing_holdout_record_is_unknown():
    assert w16_holdout_status(None).status == HOLDOUT_UNKNOWN
    assert w16_holdout_status({}).status == HOLDOUT_UNKNOWN


def test_static_audit_passes_on_the_w19_source_tree():
    audit = audit_source_capability(_w19_sources())
    assert audit.passed, [finding.to_dict() for finding in audit.findings]
    assert len(audit.files_scanned) == len(_w19_sources())


def test_static_audit_detects_a_forbidden_import(tmp_path):
    path = tmp_path / "bad_import.py"
    path.write_text("import scipy.stats\n", encoding="utf-8")
    audit = audit_source_capability([path])
    assert not audit.passed
    assert audit.findings[0].kind == "FORBIDDEN_IMPORT"


def test_static_audit_detects_a_forbidden_call(tmp_path):
    path = tmp_path / "bad_call.py"
    path.write_text(
        "def run(a, b):\n    return ttest_rel(a, b)\n", encoding="utf-8"
    )
    audit = audit_source_capability([path])
    assert not audit.passed
    assert any(finding.kind == "FORBIDDEN_CALL" for finding in audit.findings)


def test_static_audit_detects_paired_improvement_import(tmp_path):
    path = tmp_path / "bad_pairs.py"
    path.write_text(
        "from coldguard_ml.evaluation_contract import paired_improvement\n",
        encoding="utf-8",
    )
    audit = audit_source_capability([path])
    assert not audit.passed
    targets = {finding.target for finding in audit.findings}
    assert "paired_improvement" in targets or any(
        "evaluation_contract" in target for target in targets
    )


def test_static_audit_detects_a_forbidden_definition(tmp_path):
    path = tmp_path / "bad_definition.py"
    path.write_text(
        "def compute_p_value(values):\n    return 0.04\n", encoding="utf-8"
    )
    audit = audit_source_capability([path])
    assert not audit.passed
    assert audit.findings[0].kind == "FORBIDDEN_DEFINITION"


def test_static_audit_fails_closed_on_unparseable_source(tmp_path):
    path = tmp_path / "broken.py"
    path.write_text("def broken(:\n", encoding="utf-8")
    audit = audit_source_capability([path])
    assert not audit.passed
    assert audit.findings[0].kind == "PARSE_ERROR"
