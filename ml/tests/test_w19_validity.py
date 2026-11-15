"""W19 B-W19-02 outcome-blinded validity controls.

Validity is a protocol property. No outcome value is an input, so better or
worse Controller B performance can never change eligibility.
"""

from __future__ import annotations

import inspect

import pytest

from coldguard_ml.w19_no_peeking import W19OutcomeExposureError
from coldguard_ml.w19_validity import (
    ALLOWED_INPUT_FIELDS,
    ADMISSIBLE,
    UNDEFINED_INCOMPLETE,
    VALIDITY_INVALID,
    VALIDITY_METHOD_VERSION,
    VALIDITY_PENDING,
    VALIDITY_VALID,
    W19ValidityError,
    assess_attempt_validity,
)


def _input(**overrides) -> dict:
    payload = {
        "attempt_id": "ATT-VALIDITY-001",
        "pair_id": "PAIR-VALIDITY-001",
        "run_id": "RUN-VALIDITY-001",
        "controller_arm": "B",
        "hardware_config_id": "CG-HW-001",
        "calibration_id": "CG-CAL-001",
        "firmware_version": "fw-1.0.0",
        "protocol_version": "protocol-v1",
        "disturbance_execution": "EXECUTED_WITHIN_TOLERANCE",
        "reset_criterion": "MET_VERIFIED",
        "quality_status": "QUALITY_PASS",
        "completeness": {
            "thermal_primary": "COMPLETE",
            "thermal_recovery": "COMPLETE",
            "electrical_energy": "COMPLETE",
        },
        "time_sequence_validity": "VALID",
        "controller_order_recorded": True,
        "safety_stop_recorded": False,
        "operator_intervention": "NONE",
    }
    payload.update(overrides)
    return payload


def _metric(decision, metric_id: str):
    return next(
        metric
        for metric in decision.metric_admissibility
        if metric.metric_id == metric_id
    )


def test_protocol_valid_attempt_is_valid_and_primary_eligible():
    decision = assess_attempt_validity(_input())
    assert decision.validity_status == VALIDITY_VALID
    assert decision.reason_codes == ()
    assert decision.primary_pair_eligible is True
    assert decision.outcome_fields_used is False
    assert decision.decision_method == VALIDITY_METHOD_VERSION


def test_worse_performing_but_protocol_valid_b_remains_valid():
    # Performance is deliberately not part of the input contract; this record is
    # protocol-valid, so it must remain VALID even if B were much worse.
    decision = assess_attempt_validity(_input(controller_arm="B"))
    assert decision.validity_status == VALIDITY_VALID
    assert decision.primary_pair_eligible is True


def test_better_performing_but_protocol_invalid_b_is_rejected():
    decision = assess_attempt_validity(_input(quality_status="QUALITY_FAIL"))
    assert decision.validity_status == VALIDITY_INVALID
    assert "PHYSICAL_QUALITY_INVALID" in decision.reason_codes
    assert decision.primary_pair_eligible is False


def test_swapping_controller_arm_does_not_change_validity():
    arm_a = assess_attempt_validity(_input(controller_arm="A"))
    arm_b = assess_attempt_validity(_input(controller_arm="B"))
    assert arm_a.validity_status == arm_b.validity_status
    assert arm_a.reason_codes == arm_b.reason_codes


def test_swapping_values_is_impossible_because_outcomes_are_not_inputs():
    signature = inspect.signature(assess_attempt_validity)
    assert set(signature.parameters) == {"record"}
    forbidden = {
        "y_a",
        "y_b",
        "thermal_exposure",
        "recovery_time",
        "branch_energy",
        "improvement",
        "p_value",
        "effect_size",
    }
    assert not (ALLOWED_INPUT_FIELDS | set(signature.parameters)) & forbidden


def test_outcome_field_in_validity_payload_is_refused():
    payload = _input()
    payload["thermal_exposure"] = 12.5
    with pytest.raises(W19OutcomeExposureError):
        assess_attempt_validity(payload)
    payload = _input()
    payload["p_value"] = 0.04
    with pytest.raises(W19OutcomeExposureError):
        assess_attempt_validity(payload)


def test_unknown_validity_input_field_is_refused():
    payload = _input()
    payload["notes"] = "extra"
    with pytest.raises(W19ValidityError):
        assess_attempt_validity(payload)


def test_unverified_reset_evidence_is_not_accepted():
    decision = assess_attempt_validity(_input(reset_criterion="EVIDENCE_MISSING"))
    assert decision.validity_status == VALIDITY_INVALID
    assert "INITIAL_RESET_EVIDENCE_MISSING" in decision.reason_codes


def test_failed_reset_criterion_is_invalid():
    decision = assess_attempt_validity(_input(reset_criterion="NOT_MET"))
    assert decision.validity_status == VALIDITY_INVALID
    assert "INITIAL_RESET_CRITERION_NOT_MET" in decision.reason_codes


def test_unverified_quality_waits_and_failed_quality_is_invalid():
    pending = assess_attempt_validity(_input(quality_status="QUALITY_PENDING"))
    assert pending.validity_status == VALIDITY_PENDING
    assert "PHYSICAL_QUALITY_UNVERIFIED" in pending.reason_codes
    failed = assess_attempt_validity(_input(quality_status="QUALITY_FAIL"))
    assert failed.validity_status == VALIDITY_INVALID


def test_missing_provenance_invalidates_attempt():
    decision = assess_attempt_validity(
        _input(hardware_config_id=None, calibration_id=None, firmware_version=None)
    )
    assert decision.validity_status == VALIDITY_INVALID
    assert "HARDWARE_IDENTITY_MISSING" in decision.reason_codes
    assert "CALIBRATION_PROVENANCE_MISSING" in decision.reason_codes
    assert "FIRMWARE_IDENTITY_MISSING" in decision.reason_codes


def test_disturbance_failures_are_invalid_and_unknown_waits():
    not_executed = assess_attempt_validity(
        _input(disturbance_execution="NOT_EXECUTED")
    )
    assert "DISTURBANCE_NOT_EXECUTED" in not_executed.reason_codes
    out_of_tolerance = assess_attempt_validity(
        _input(disturbance_execution="EXECUTED_OUT_OF_TOLERANCE")
    )
    assert "DISTURBANCE_TOLERANCE_EXCEEDED" in out_of_tolerance.reason_codes
    unknown = assess_attempt_validity(_input(disturbance_execution="UNKNOWN"))
    assert unknown.validity_status == VALIDITY_PENDING


def test_temporal_order_invalidity_blocks_validity():
    invalid = assess_attempt_validity(_input(time_sequence_validity="INVALID"))
    assert "TEMPORAL_ORDER_INVALID" in invalid.reason_codes
    unknown = assess_attempt_validity(_input(time_sequence_validity="UNKNOWN"))
    assert unknown.validity_status == VALIDITY_PENDING


def test_missing_controller_order_record_invalidates_attempt():
    decision = assess_attempt_validity(_input(controller_order_recorded=False))
    assert "CONTROLLER_ORDER_RECORD_MISSING" in decision.reason_codes


def test_safety_stop_and_unprotocol_intervention_invalidate_attempt():
    stop = assess_attempt_validity(_input(safety_stop_recorded=True))
    assert "SAFETY_STOP_RECORDED" in stop.reason_codes
    intervention = assess_attempt_validity(
        _input(operator_intervention="UNPROTOCOL")
    )
    assert "UNPROTOCOL_OPERATOR_INTERVENTION" in intervention.reason_codes


def test_missing_energy_coverage_stays_undefined_never_zero():
    decision = assess_attempt_validity(
        _input(
            completeness={
                "thermal_primary": "COMPLETE",
                "thermal_recovery": "COMPLETE",
                "electrical_energy": "MISSING",
            }
        )
    )
    energy = _metric(decision, "branch_energy")
    assert energy.admissibility == UNDEFINED_INCOMPLETE
    assert energy.coverage == "MISSING"
    assert decision.validity_status == VALIDITY_VALID
    assert decision.primary_pair_eligible is True
    serialized = decision.to_dict()
    assert not any("value" in metric for metric in serialized["metric_admissibility"])


def test_missing_primary_thermal_coverage_invalidates_attempt():
    decision = assess_attempt_validity(
        _input(
            completeness={
                "thermal_primary": "INCOMPLETE",
                "thermal_recovery": "COMPLETE",
                "electrical_energy": "COMPLETE",
            }
        )
    )
    assert decision.validity_status == VALIDITY_INVALID
    assert "TELEMETRY_GAP_COVERS_PRIMARY_EVENT" in decision.reason_codes
    assert decision.primary_pair_eligible is False


def test_unknown_primary_coverage_waits_for_evidence():
    decision = assess_attempt_validity(
        _input(
            completeness={
                "thermal_primary": "UNKNOWN",
                "thermal_recovery": "COMPLETE",
                "electrical_energy": "COMPLETE",
            }
        )
    )
    assert decision.validity_status == VALIDITY_PENDING
    assert "PRIMARY_OUTCOME_COMPLETENESS_UNKNOWN" in decision.reason_codes


def test_primary_metric_is_admissible_only_with_complete_coverage():
    decision = assess_attempt_validity(_input())
    thermal = _metric(decision, "thermal_exposure")
    assert thermal.role == "PRIMARY"
    assert thermal.admissibility == ADMISSIBLE


def test_every_non_valid_decision_records_objective_reasons():
    for overrides in (
        {"quality_status": "QUALITY_FAIL"},
        {"reset_criterion": "NOT_MET"},
        {"disturbance_execution": "NOT_EXECUTED"},
    ):
        decision = assess_attempt_validity(_input(**overrides))
        assert decision.validity_status == VALIDITY_INVALID
        assert decision.reason_codes


def test_undeclared_enum_value_is_a_structural_error():
    with pytest.raises(W19ValidityError):
        assess_attempt_validity(_input(quality_status="MAYBE"))
    with pytest.raises(W19ValidityError):
        assess_attempt_validity(_input(controller_arm="C"))
    with pytest.raises(W19ValidityError):
        assess_attempt_validity(
            _input(completeness={"thermal_primary": "PLENTY"})
        )


def test_missing_required_input_field_is_refused():
    payload = _input()
    del payload["quality_status"]
    with pytest.raises(W19ValidityError):
        assess_attempt_validity(payload)


def test_two_arms_with_identical_protocol_state_have_identical_validity():
    a = assess_attempt_validity(_input(controller_arm="A", quality_status="QUALITY_FAIL"))
    b = assess_attempt_validity(_input(controller_arm="B", quality_status="QUALITY_FAIL"))
    assert a.validity_status == b.validity_status == VALIDITY_INVALID
    assert a.reason_codes == b.reason_codes
