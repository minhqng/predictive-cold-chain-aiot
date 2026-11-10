"""W20 EWT causal boundary: no counterfactual EWT from closed-loop B runs."""

from __future__ import annotations

import pytest

from coldguard_ml.w20_causal_boundary import (
    AB_CONTRACT_ACCEPTED,
    AB_CONTRACT_REJECTED,
    AIW_ADMISSIBLE,
    AIW_NOT_ADMISSIBLE,
    AIW_UNKNOWN,
    CAUSAL_BOUNDARY_SOFTWARE_VERIFIED,
    CAUSAL_RESTRICTION_CHECKS,
    ENERGY_METADATA_OK,
    ENERGY_NOT_ADMISSIBLE,
    EWT_ADMISSIBLE,
    EWT_NOT_ADMISSIBLE,
    EWT_UNKNOWN,
    EWT_UNOBSERVED,
    PROVENANCE_CLOSED_LOOP,
    PROVENANCE_OFFLINE,
    PROVENANCE_SYNTHETIC,
    PROVENANCE_UNKNOWN,
    RECOVERY_METADATA_OK,
    RECOVERY_NOT_ADMISSIBLE,
    W20CausalBoundaryError,
    assess_aiw_admissibility,
    assess_energy_claim,
    assess_ewt_admissibility,
    assess_recovery_claim,
    causal_restriction_proof,
    classify_provenance,
    validate_ab_report_contract,
)


def _offline(**overrides):
    record = {
        "record_id": "REC-OFFLINE-001",
        "evidence_class": "OFFLINE_REPLAY",
        "controller_context": "REACTIVE",
        "intervention": "NONE",
        "timing_source": "MEASURED_EVENT_TIME",
        "reactive_crossing_observed": True,
        "synthetic_markers": [],
        "ack_only": False,
        "post_intervention_warning_used": False,
        "aiw_timing_inputs_measured": True,
        "thermal_response_verified": True,
        "electrical_observation_only": False,
        "pzem_coverage": "COMPLETE",
        "energy_scope": "COOLING_BRANCH",
    }
    record.update(overrides)
    return record


def _closed_loop(**overrides):
    record = _offline(
        record_id="REC-B-CLOSED-001",
        evidence_class="PHYSICAL",
        controller_context="PREDICTIVE",
        intervention="PREDICTIVE_COOLING_APPLIED",
        reactive_crossing_observed=False,
    )
    record.update(overrides)
    return record


def _synthetic(**overrides):
    record = _offline(
        record_id="REC-SYNTHETIC-001",
        evidence_class="SYNTHETIC",
        timing_source="SYNTHETIC_REPLAY_TIMESTAMP",
        synthetic_markers=["TEST_ONLY", "SYNTHETIC_SOFTWARE_CONTROL_ONLY"],
    )
    record.update(overrides)
    return record


def test_provenance_classes():
    assert classify_provenance(_offline()).provenance_class == PROVENANCE_OFFLINE
    assert classify_provenance(_closed_loop()).provenance_class == PROVENANCE_CLOSED_LOOP
    assert classify_provenance(_synthetic()).provenance_class == PROVENANCE_SYNTHETIC
    unknown = _offline(controller_context="UNKNOWN", intervention="UNKNOWN")
    assert classify_provenance(unknown).provenance_class == PROVENANCE_UNKNOWN


def test_offline_ewt_is_admissible_metadata_only():
    assessment = assess_ewt_admissibility(_offline())
    assert assessment.status == EWT_ADMISSIBLE
    assert assessment.value_computed is False
    assert assessment.value_status.startswith("EWT_VALUE_REQUIRES")


def test_closed_loop_b_ewt_is_refused():
    assessment = assess_ewt_admissibility(_closed_loop())
    assert assessment.status == EWT_NOT_ADMISSIBLE
    assert any(
        "COUNTERFACTUAL" in reason for reason in assessment.reasons
    )
    assert assessment.value_computed is False


def test_unobserved_crossing_is_not_zero():
    assessment = assess_ewt_admissibility(
        _offline(reactive_crossing_observed=False)
    )
    assert assessment.status == EWT_UNOBSERVED
    assert "ZERO" in assessment.value_status
    assert assessment.value_computed is False


def test_unknown_crossing_is_not_zero():
    assessment = assess_ewt_admissibility(
        _offline(reactive_crossing_observed=None)
    )
    assert assessment.status == EWT_UNKNOWN
    assert "ZERO" in assessment.value_status


def test_synthetic_ewt_is_refused():
    assessment = assess_ewt_admissibility(_synthetic())
    assert assessment.status == EWT_NOT_ADMISSIBLE


def test_ack_is_not_a_physical_response():
    assert assess_ewt_admissibility(_offline(ack_only=True)).status == (
        EWT_NOT_ADMISSIBLE
    )
    assert assess_aiw_admissibility(_offline(ack_only=True)).status == (
        AIW_NOT_ADMISSIBLE
    )


def test_aiw_requires_measured_inputs():
    assessment = assess_aiw_admissibility(
        _offline(aiw_timing_inputs_measured=False)
    )
    assert assessment.status == AIW_UNKNOWN
    assert "ZERO" in assessment.value_status


def test_aiw_admissible_metadata_only():
    assessment = assess_aiw_admissibility(_offline())
    assert assessment.status == AIW_ADMISSIBLE
    assert assessment.value_computed is False


def test_aiw_from_synthetic_timing_is_refused():
    assert assess_aiw_admissibility(_synthetic()).status == AIW_NOT_ADMISSIBLE


def test_aiw_from_closed_loop_is_refused():
    assert assess_aiw_admissibility(_closed_loop()).status == AIW_NOT_ADMISSIBLE


def test_aiw_with_unknown_provenance_fails_closed():
    assessment = assess_aiw_admissibility(
        _offline(controller_context="UNKNOWN")
    )
    assert assessment.status == AIW_NOT_ADMISSIBLE
    assert any("PROVENANCE_UNKNOWN" in reason for reason in assessment.reasons)


def test_post_intervention_warning_is_not_a_counterfactual():
    assessment = assess_ewt_admissibility(
        _offline(post_intervention_warning_used=True)
    )
    assert assessment.status == EWT_NOT_ADMISSIBLE
    assert any(
        "POST_INTERVENTION" in reason for reason in assessment.reasons
    )


def test_recovery_requires_thermal_evidence():
    assert assess_recovery_claim(_offline()).status == RECOVERY_METADATA_OK
    assert assess_recovery_claim(
        _offline(electrical_observation_only=True)
    ).status == RECOVERY_NOT_ADMISSIBLE
    assert assess_recovery_claim(
        _offline(thermal_response_verified=False)
    ).status == RECOVERY_NOT_ADMISSIBLE


def test_censored_recovery_is_not_finite():
    assessment = assess_recovery_claim(_offline(recovery_censored=True))
    assert assessment.status == RECOVERY_NOT_ADMISSIBLE
    assert any("CENSORED" in reason for reason in assessment.reasons)


def test_energy_requires_cooling_branch_pzem():
    assert assess_energy_claim(_offline()).status == ENERGY_METADATA_OK
    assert assess_energy_claim(_offline(pzem_coverage="MISSING")).status == (
        ENERGY_NOT_ADMISSIBLE
    )
    assert assess_energy_claim(_offline(pzem_coverage="PARTIAL")).status == (
        ENERGY_NOT_ADMISSIBLE
    )
    assert assess_energy_claim(_offline(whole_system_claim=True)).status == (
        ENERGY_NOT_ADMISSIBLE
    )
    assert assess_energy_claim(_offline(energy_scope="WHOLE_SYSTEM")).status == (
        ENERGY_NOT_ADMISSIBLE
    )


def test_ab_contract_rejects_naive_ewt_and_synthetic_aiw():
    rejected = validate_ab_report_contract(
        {
            "outcome_metrics": ["thermal_exposure"],
            "ewt_claims": [
                {
                    "trajectory_class": PROVENANCE_CLOSED_LOOP,
                    "crossing_observed": False,
                }
            ],
        }
    )
    assert rejected["status"] == AB_CONTRACT_REJECTED
    assert rejected["outcome_values_present"] is False
    rejected_synthetic = validate_ab_report_contract(
        {
            "outcome_metrics": ["thermal_exposure"],
            "aiw_claims": [{"timing_source": "SYNTHETIC_REPLAY_TIMESTAMP"}],
        }
    )
    assert rejected_synthetic["status"] == AB_CONTRACT_REJECTED


def test_ab_contract_accepts_only_predeclared_outcomes():
    accepted = validate_ab_report_contract(
        {"outcome_metrics": ["thermal_exposure", "recovery_time"]}
    )
    assert accepted["status"] == AB_CONTRACT_ACCEPTED
    assert accepted["reasons"] == []
    rejected = validate_ab_report_contract(
        {"outcome_metrics": ["ewt_seconds_from_closed_loop"]}
    )
    assert rejected["status"] == AB_CONTRACT_REJECTED


def test_causal_restriction_proof_is_complete():
    proof = causal_restriction_proof()
    assert proof["proof_status"] == CAUSAL_BOUNDARY_SOFTWARE_VERIFIED
    assert all(proof["checks"].values())
    assert set(proof["checks"]) == set(CAUSAL_RESTRICTION_CHECKS)
    assert proof["ewt_values_computed"] is False
    assert proof["aiw_values_computed"] is False
    assert proof["counterfactual_crossings_invented"] is False


def test_malformed_provenance_is_refused():
    with pytest.raises(W20CausalBoundaryError):
        classify_provenance({"record_id": ""})
    with pytest.raises(W20CausalBoundaryError):
        classify_provenance(_offline(controller_context="SOMETHING"))
    with pytest.raises(W20CausalBoundaryError):
        assess_ewt_admissibility(_offline(reactive_crossing_observed="yes"))
