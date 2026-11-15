"""W21 diagnosis classification: positive controls and meaningful refusals."""

from __future__ import annotations

import pytest

from coldguard_ml.w21_diagnosis import (
    CLASS_DEGRADED_OR_UNKNOWN,
    CLASS_DEGRADED_THERMAL_EFFECTIVENESS,
    CLASS_ELECTRICAL_RESPONSE_MISSING,
    CLASS_HEALTHY_RESPONSE,
    CLASS_NOT_ESTIMABLE,
    CLASS_OFF_STATE,
    CLASS_UNEXPECTED_OFF_CURRENT,
    CONCORDANCE_CONCORDANT,
    CONCORDANCE_DISCORDANT,
    CONCORDANCE_NOT_ESTIMABLE,
    COMMAND_OFF,
    COMMAND_ON,
    COMMAND_UNKNOWN,
    CURRENT_MEASURED_NONZERO,
    CURRENT_MEASURED_ZERO,
    CURRENT_MISSING,
    CURRENT_UNKNOWN,
    GROUND_TRUTH_CONTROLLED_INJECTION,
    GROUND_TRUTH_NONE,
    LEVEL_ELECTRICAL_RESPONSE_VERIFICATION,
    LEVEL_RECORDED_CONDITION,
    LEVEL_SOFTWARE_DIAGNOSTIC_CLASSIFICATION,
    LEVEL_THERMAL_RESPONSE_VERIFICATION,
    LEVEL_TRUSTED_CHANNEL_OBSERVATION,
    METRIC_NOT_ESTIMABLE,
    OUTPUT_STAGE_DISABLED,
    OUTPUT_STAGE_ENABLED,
    OUTPUT_STAGE_UNKNOWN,
    QUALITY_DEGRADED,
    QUALITY_INVALID,
    QUALITY_UNKNOWN,
    QUALITY_VALID,
    REFUSAL_ACK_NOT_EVIDENCE,
    REFUSAL_COMMAND_NOT_CURRENT,
    REFUSAL_ELECTRICAL_UNAVAILABLE,
    REFUSAL_MISSING_PZEM_NOT_ZERO,
    REFUSAL_OUTPUT_STAGE_DISABLED,
    REFUSAL_OVERALL_NOT_VALID,
    REFUSAL_WEAK_THERMAL_NOT_ROOT_CAUSE,
    THERMAL_ABSENT,
    THERMAL_PRESENT,
    THERMAL_UNKNOWN,
    DiagnosisCase,
    W21DiagnosisError,
    assess_diagnosis_table,
    classify_case,
    population_metrics,
    required_negative_cases,
)


def _case(**overrides) -> DiagnosisCase:
    payload = {
        "case_id": "CASE-1",
        "condition": "fixture",
        "ground_truth_source": GROUND_TRUTH_CONTROLLED_INJECTION,
        "injection_ref": "fixture",
        "command_state": COMMAND_ON,
        "ack_observed": False,
        "output_stage": OUTPUT_STAGE_ENABLED,
        "electrical_quality": QUALITY_VALID,
        "current_measurement": CURRENT_MEASURED_NONZERO,
        "current_value_a": 1.0,
        "thermal_quality": QUALITY_VALID,
        "thermal_response": THERMAL_PRESENT,
        "overall_quality": QUALITY_VALID,
        "observed_invalid_channels": (),
        "recovery_observed": True,
        "frames": 10,
        "source_sha256": "a" * 64,
        "device_id": "d1",
        "boot_id": "b1",
        "session_id": "s1",
        "expected_classification": CLASS_HEALTHY_RESPONSE,
        "unsupported_conclusions": (),
        "notes": "",
    }
    payload.update(overrides)
    return DiagnosisCase(**payload)


def test_healthy_enabled_actuator_fixture_is_diagnosed():
    result = classify_case(_case())
    assert result.classification == CLASS_HEALTHY_RESPONSE
    assert result.concordance == CONCORDANCE_CONCORDANT
    assert LEVEL_ELECTRICAL_RESPONSE_VERIFICATION in result.evidence_levels
    assert LEVEL_THERMAL_RESPONSE_VERIFICATION in result.evidence_levels
    assert LEVEL_RECORDED_CONDITION in result.evidence_levels
    assert LEVEL_TRUSTED_CHANNEL_OBSERVATION in result.evidence_levels
    assert LEVEL_SOFTWARE_DIAGNOSTIC_CLASSIFICATION in result.evidence_levels


def test_electrical_response_missing_requires_measured_zero():
    result = classify_case(
        _case(
            current_measurement=CURRENT_MEASURED_ZERO,
            current_value_a=0.0,
            thermal_response=THERMAL_ABSENT,
            expected_classification=CLASS_ELECTRICAL_RESPONSE_MISSING,
        )
    )
    assert result.classification == CLASS_ELECTRICAL_RESPONSE_MISSING
    assert result.concordance == CONCORDANCE_CONCORDANT


def test_unexpected_off_current_is_detected():
    result = classify_case(
        _case(
            command_state=COMMAND_OFF,
            thermal_response=THERMAL_UNKNOWN,
            expected_classification=CLASS_UNEXPECTED_OFF_CURRENT,
        )
    )
    assert result.classification == CLASS_UNEXPECTED_OFF_CURRENT


def test_healthy_off_state_is_not_a_diagnosis():
    result = classify_case(
        _case(
            command_state=COMMAND_OFF,
            current_measurement=CURRENT_MEASURED_ZERO,
            current_value_a=0.0,
            thermal_response=THERMAL_UNKNOWN,
            expected_classification=None,
        )
    )
    assert result.classification == CLASS_OFF_STATE
    assert result.concordance == CONCORDANCE_NOT_ESTIMABLE


def test_command_on_alone_is_not_current_flow():
    result = classify_case(
        _case(
            electrical_quality=QUALITY_UNKNOWN,
            current_measurement=CURRENT_UNKNOWN,
            thermal_quality=QUALITY_UNKNOWN,
            thermal_response=THERMAL_UNKNOWN,
            overall_quality=QUALITY_UNKNOWN,
            expected_classification=None,
        )
    )
    assert result.classification == CLASS_DEGRADED_OR_UNKNOWN
    assert REFUSAL_COMMAND_NOT_CURRENT in result.refusals
    assert REFUSAL_ELECTRICAL_UNAVAILABLE in result.refusals


def test_ack_is_not_actuation_evidence():
    result = classify_case(
        _case(
            ack_observed=True,
            electrical_quality=QUALITY_UNKNOWN,
            current_measurement=CURRENT_UNKNOWN,
            thermal_quality=QUALITY_UNKNOWN,
            thermal_response=THERMAL_UNKNOWN,
            overall_quality=QUALITY_UNKNOWN,
            expected_classification=None,
        )
    )
    assert REFUSAL_ACK_NOT_EVIDENCE in result.refusals
    assert result.classification != CLASS_HEALTHY_RESPONSE


def test_current_without_thermal_response_is_degraded_not_healthy():
    result = classify_case(
        _case(thermal_response=THERMAL_ABSENT)
    )
    assert result.classification == CLASS_DEGRADED_THERMAL_EFFECTIVENESS
    assert REFUSAL_WEAK_THERMAL_NOT_ROOT_CAUSE in result.refusals
    assert "COMPONENT_LEVEL_ROOT_CAUSE" in result.unsupported_conclusions


def test_unknown_quality_never_becomes_healthy():
    result = classify_case(
        _case(
            electrical_quality=QUALITY_UNKNOWN,
            current_measurement=CURRENT_UNKNOWN,
            thermal_quality=QUALITY_UNKNOWN,
            thermal_response=THERMAL_UNKNOWN,
            overall_quality=QUALITY_UNKNOWN,
            expected_classification=None,
        )
    )
    assert result.classification != CLASS_HEALTHY_RESPONSE
    assert result.classification != CLASS_ELECTRICAL_RESPONSE_MISSING
    assert result.classification == CLASS_DEGRADED_OR_UNKNOWN


def test_unknown_overall_quality_never_becomes_healthy_even_with_valid_channels():
    result = classify_case(
        _case(
            overall_quality=QUALITY_UNKNOWN,
            observed_invalid_channels=("T1",),
            expected_classification=None,
        )
    )
    assert result.classification == CLASS_DEGRADED_OR_UNKNOWN
    assert result.classification != CLASS_HEALTHY_RESPONSE
    assert REFUSAL_OVERALL_NOT_VALID in result.refusals


def test_duplicate_case_ids_are_rejected():
    first = _case(case_id="DUP", expected_classification=None)
    second = _case(case_id="DUP", expected_classification=None)
    with pytest.raises(W21DiagnosisError):
        assess_diagnosis_table([first, second])


def test_missing_pzem_is_not_verified_zero():
    result = classify_case(
        _case(
            command_state=COMMAND_OFF,
            electrical_quality=QUALITY_UNKNOWN,
            current_measurement=CURRENT_MISSING,
            thermal_quality=QUALITY_UNKNOWN,
            thermal_response=THERMAL_UNKNOWN,
            overall_quality=QUALITY_UNKNOWN,
            expected_classification=None,
        )
    )
    assert result.classification == CLASS_DEGRADED_OR_UNKNOWN
    assert REFUSAL_MISSING_PZEM_NOT_ZERO in result.refusals


def test_output_disabled_cannot_report_electrical_failure():
    result = classify_case(
        _case(
            output_stage=OUTPUT_STAGE_DISABLED,
            electrical_quality=QUALITY_VALID,
            current_measurement=CURRENT_MEASURED_ZERO,
            current_value_a=0.0,
            thermal_quality=QUALITY_UNKNOWN,
            thermal_response=THERMAL_UNKNOWN,
            overall_quality=QUALITY_UNKNOWN,
            expected_classification=None,
        )
    )
    assert result.classification != CLASS_ELECTRICAL_RESPONSE_MISSING
    assert result.classification != CLASS_HEALTHY_RESPONSE
    assert REFUSAL_OUTPUT_STAGE_DISABLED in result.refusals


def test_unknown_output_stage_is_not_estimable_without_degradation():
    result = classify_case(
        _case(
            output_stage=OUTPUT_STAGE_UNKNOWN,
            electrical_quality=QUALITY_VALID,
            current_measurement=CURRENT_MEASURED_NONZERO,
            thermal_quality=QUALITY_VALID,
            thermal_response=THERMAL_PRESENT,
            overall_quality=QUALITY_VALID,
            expected_classification=None,
        )
    )
    assert result.classification == CLASS_NOT_ESTIMABLE
    assert result.concordance == CONCORDANCE_NOT_ESTIMABLE


def test_no_ground_truth_has_no_concordance():
    result = classify_case(
        _case(
            ground_truth_source=GROUND_TRUTH_NONE,
            expected_classification=None,
        )
    )
    assert result.concordance == CONCORDANCE_NOT_ESTIMABLE


def test_discordant_fixture_is_reported_discordant():
    result = classify_case(
        _case(expected_classification=CLASS_ELECTRICAL_RESPONSE_MISSING)
    )
    assert result.concordance == CONCORDANCE_DISCORDANT


def test_two_test_ids_from_one_boot_are_one_session():
    first = _case(case_id="CASE-1", expected_classification=None)
    second = _case(case_id="CASE-2", expected_classification=None)
    table = assess_diagnosis_table([first, second])
    assert table.record_count == 20
    assert table.independent_session_count == 1
    assert all(case.independent_session_count == 1 for case in table.cases)


def test_different_boots_are_two_sessions():
    first = _case(case_id="CASE-1", expected_classification=None)
    second = _case(
        case_id="CASE-2", boot_id="b2", session_id="s2", expected_classification=None
    )
    assert assess_diagnosis_table([first, second]).independent_session_count == 2


def test_same_boot_different_session_labels_are_one_session():
    first = _case(case_id="CASE-1", session_id="s1", expected_classification=None)
    second = _case(case_id="CASE-2", session_id="s2", expected_classification=None)
    assert assess_diagnosis_table([first, second]).independent_session_count == 1


def test_zero_current_with_invalid_overall_is_not_electrical_missing():
    result = classify_case(
        _case(
            current_measurement=CURRENT_MEASURED_ZERO,
            current_value_a=0.0,
            overall_quality=QUALITY_INVALID,
            expected_classification=None,
        )
    )
    assert result.classification == CLASS_DEGRADED_OR_UNKNOWN
    assert result.classification != CLASS_ELECTRICAL_RESPONSE_MISSING
    assert REFUSAL_OVERALL_NOT_VALID in result.refusals


def test_population_metrics_are_not_estimable_and_not_computed():
    table = assess_diagnosis_table([_case(expected_classification=None)])
    assert all(value == METRIC_NOT_ESTIMABLE for value in table.metrics.values())
    assert all(
        value == "INSUFFICIENT_INDEPENDENT_LABELED_SUPPORT"
        for value in table.metric_reasons.values()
    )
    with pytest.raises(W21DiagnosisError):
        population_metrics(
            [_case()], admitted_independent_labeled_support=True
        )
    with pytest.raises(W21DiagnosisError):
        population_metrics([])


def test_malformed_cases_are_rejected():
    with pytest.raises(W21DiagnosisError):
        _case(command_state="MAYBE").validate()
    with pytest.raises(W21DiagnosisError):
        _case(current_measurement="ZEROISH").validate()
    with pytest.raises(W21DiagnosisError):
        _case(current_value_a=float("nan")).validate()
    with pytest.raises(W21DiagnosisError):
        _case(
            current_measurement=CURRENT_MEASURED_ZERO,
            current_value_a=1.0,
        ).validate()
    with pytest.raises(W21DiagnosisError):
        _case(
            current_measurement=CURRENT_MEASURED_NONZERO,
            current_value_a=0.0,
        ).validate()
    with pytest.raises(W21DiagnosisError):
        _case(
            current_measurement=CURRENT_MEASURED_NONZERO,
            current_value_a=None,
        ).validate()
    with pytest.raises(W21DiagnosisError):
        _case(thermal_response="YES").validate()
    with pytest.raises(W21DiagnosisError):
        _case(source_sha256="nope").validate()
    with pytest.raises(W21DiagnosisError):
        _case(frames=-1).validate()
    with pytest.raises(W21DiagnosisError):
        _case(device_id="").validate()
    with pytest.raises(W21DiagnosisError):
        _case(expected_classification="HEALTHYISH").validate()


def test_table_requires_a_case():
    with pytest.raises(W21DiagnosisError):
        assess_diagnosis_table([])


def test_required_negative_cases_are_declared():
    cases = required_negative_cases()
    assert len(cases) == 8
    names = {name for name, _ in cases}
    assert "on_command_not_current" in names
    assert "ack_not_applied_power" in names
    assert "current_not_thermal" in names
    assert "off_without_pzem_not_zero" in names
    assert "compiled_out_stage_not_failure" in names
    assert "software_injection_not_cable_disconnect" in names
    assert "weak_cooling_not_component" in names
    assert "shared_boot_not_independent" in names


def test_invalid_degraded_case_is_diagnosed_as_degraded():
    result = classify_case(
        _case(
            output_stage=OUTPUT_STAGE_DISABLED,
            electrical_quality=QUALITY_INVALID,
            current_measurement=CURRENT_MISSING,
            thermal_quality=QUALITY_DEGRADED,
            thermal_response=THERMAL_UNKNOWN,
            overall_quality=QUALITY_UNKNOWN,
            observed_invalid_channels=("T1",),
            expected_classification=CLASS_DEGRADED_OR_UNKNOWN,
        )
    )
    assert result.classification == CLASS_DEGRADED_OR_UNKNOWN
    assert result.concordance == CONCORDANCE_CONCORDANT
    assert REFUSAL_OUTPUT_STAGE_DISABLED in result.refusals


def test_unknown_command_is_not_estimable():
    result = classify_case(
        _case(command_state=COMMAND_UNKNOWN, expected_classification=None)
    )
    assert result.classification == CLASS_NOT_ESTIMABLE
