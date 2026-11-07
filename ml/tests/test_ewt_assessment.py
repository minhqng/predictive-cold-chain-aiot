"""W12 EWT contract: arithmetic, refusals and the EWT/AIW separation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coldguard_ml.ewt_assessment import (
    AIW_REASON_MISSING_CHAIN,
    EWT_REASON_ANCHOR_UNDEFINED,
    EWT_REASON_INCOMPATIBLE_CLOCK,
    EWT_REASON_INTERVENED,
    EWT_REASON_NO_COMMON_TRAJECTORY,
    REAL_AIW_STATUS,
    REAL_EWT_STATUS,
    SYNTHETIC_TIMING_LABEL,
    assess_real_ewt_aiw,
    synthetic_timing_cases,
)

ML_ROOT = Path(__file__).resolve().parents[1]
W11_MANIFEST = ML_ROOT / "reports" / "W11" / "benchmark-manifest-W11.json"
W06_MANIFEST = ML_ROOT / "reports" / "W06" / "timing-manifest-W06.json"


def _cases():
    return {case.case_id: case for case in synthetic_timing_cases()}


def test_positive_negative_zero_ewt_are_preserved():
    cases = _cases()
    assert cases["CASE_A_POSITIVE_EWT"].ewt_s == 20.0
    assert cases["CASE_B_NEGATIVE_EWT"].ewt_s == -10.0
    assert cases["CASE_C_ZERO_EWT"].ewt_s == 0.0
    assert cases["CASE_A_POSITIVE_EWT"].status == "ESTIMABLE"
    assert cases["CASE_B_NEGATIVE_EWT"].status == "ESTIMABLE"


def test_missing_warning_and_reactive_crossing_are_refused():
    cases = _cases()
    assert cases["CASE_D_NO_PERSISTENT_WARNING"].status == "MISSING_WARNING"
    assert (
        cases["CASE_D_NO_PERSISTENT_WARNING"].reason_code
        == EWT_REASON_ANCHOR_UNDEFINED
    )
    assert (
        cases["CASE_E_NO_REACTIVE_CROSSING"].status
        == "MISSING_REACTIVE_CROSSING"
    )
    assert (
        cases["CASE_E_NO_REACTIVE_CROSSING"].reason_code
        == EWT_REASON_ANCHOR_UNDEFINED
    )


def test_cross_run_and_cross_clock_are_refused():
    cases = _cases()
    assert cases["CASE_F_CROSS_RUN"].status == "REFUSED_CROSS_RUN"
    assert (
        cases["CASE_F_CROSS_RUN"].reason_code == EWT_REASON_NO_COMMON_TRAJECTORY
    )
    assert cases["CASE_G_CROSS_CLOCK"].status == "REFUSED_CROSS_CLOCK"
    assert (
        cases["CASE_G_CROSS_CLOCK"].reason_code == EWT_REASON_INCOMPATIBLE_CLOCK
    )


def test_intervention_excludes_naive_counterfactual_ewt():
    case = _cases()["CASE_H_INTERVENED"]
    assert case.status == "INADMISSIBLE_INTERVENED_TRAJECTORY"
    assert case.reason_code == EWT_REASON_INTERVENED
    assert case.intervention is True


def test_first_valid_warning_onset_is_used():
    case = _cases()["CASE_I_FIRST_VALID_ONSET"]
    assert case.status == "ESTIMABLE"
    assert case.ewt_s == 20.0
    assert case.persistence_definition.startswith("coldguard-w12-synthetic-timing")


def test_every_synthetic_case_is_labeled_test_only():
    for case in synthetic_timing_cases():
        assert case.label == SYNTHETIC_TIMING_LABEL
        assert case.population == "synthetic timing contract"


def test_real_ewt_and_aiw_are_not_estimable_for_different_reasons():
    manifest = json.loads(W11_MANIFEST.read_text(encoding="utf-8"))
    w06 = json.loads(W06_MANIFEST.read_text(encoding="utf-8"))
    report = assess_real_ewt_aiw(manifest, w06_counts=w06.get("counts", {}))
    real = report.real_status
    assert real["REAL_EWT"] == REAL_EWT_STATUS
    assert real["REAL_AIW"] == REAL_AIW_STATUS
    assert real["REAL_EWT_REASON_CODE"] == EWT_REASON_NO_COMMON_TRAJECTORY
    assert real["REAL_AIW_REASON_CODE"] == AIW_REASON_MISSING_CHAIN
    assert real["REAL_EWT_REASON_CODE"] != real["REAL_AIW_REASON_CODE"]
    assert real["ewt_does_not_imply_aiw"] is True
    assert "NO_THERMAL_VERIFIED_RESPONSE" in real["real_aiw_supporting_reasons"]
    assert "NO_ELECTRICAL_VERIFIED_RESPONSE" in real["real_aiw_supporting_reasons"]


def test_real_assessment_refuses_if_eligible_runs_appear():
    manifest = {"real_development": {"ELIGIBLE_RUNS": 1}}
    with pytest.raises(ValueError, match="eligible runs"):
        assess_real_ewt_aiw(manifest)
