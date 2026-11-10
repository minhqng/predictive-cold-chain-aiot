"""W20 pair-outcomes contract: schema, undefined rules and the analysis lock."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from coldguard_ml.w19_pair_ledger import validate_pair_ledger
from coldguard_ml.w20_outcome_contract import (
    ADMISSION_BLOCKED_MISSING_COVERAGE,
    ADMISSION_BLOCKED_NO_VALID_PAIR,
    ADMISSION_METADATA_COMPLETE,
    OUTCOME_METRICS,
    OUTCOME_SCHEMA_SOFTWARE_VERIFIED,
    OUTCOME_TABLE_FILENAME,
    PAIR_OUTCOME_TABLE_NOT_PRODUCED,
    PHYSICAL_OUTCOME_DATA_NOT_ADMITTED,
    UNDEFINED_REASON_CODES,
    W20AnalysisLockError,
    W20OutcomeContractError,
    assert_no_zero_fill,
    assert_outcome_analysis_locked,
    build_admission_plan,
    outcome_table_contract,
    schema_verdicts,
    undefined_reason,
    validate_pair_outcome_metadata,
)

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
SCRIPT = ML_ROOT / "scripts" / "w20-campaign-preflight-W20.py"
W16 = ML_ROOT / "reports" / "W16" / "locked-test-manifest-W16.json"
W18_BASELINE = ML_ROOT / "reports" / "W18" / "freeze-baseline-W18.json"
W20_DIR = ML_ROOT / "reports" / "W20"


def _load_driver():
    spec = importlib.util.spec_from_file_location("w20_driver_outcome", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fixture_bundle():
    driver = _load_driver()
    reader = driver._make_reader()
    w16 = reader.read_json(W16.relative_to(REPO_ROOT).as_posix())
    w18 = reader.read_json(W18_BASELINE.relative_to(REPO_ROOT).as_posix())
    return driver.build_test_only_metadata_bundle(w16, w18)


def _metadata_row(**overrides):
    row = {
        "pair_id": "PAIR-TEST-001",
        "run_A_id": "ATT-TEST-001-A",
        "run_B_id": "ATT-TEST-001-B",
        "controller_order": "A,B",
        "hardware_config_id": "CG-HW-FIXTURE-001",
        "calibration_id": "CG-CAL-FIXTURE-001",
        "firmware_version": "fw-fixture-1.0.0",
        "model_artifact_sha256_B": "0" * 64,
        "source_sha256_A": "1" * 64,
        "source_sha256_B": "2" * 64,
        "analysis_version": "coldguard-w03-analysis-contract-v1",
        "primary_outcome_name": "PRIMARY_THERMAL_EXPOSURE_CONTRACT_V1",
        "primary_outcome_version": "v1",
        "coverage_status": {
            metric.metric_id: "COMPLETE" for metric in OUTCOME_METRICS
        },
        "undefined_reason_codes": [],
        "validity_flags": {"pair_status": "PAIR_VALID"},
        "metric_versions": {"thermal_exposure": "v1"},
    }
    row.update(overrides)
    return row


def test_schema_carries_identity_metric_and_metadata_columns():
    contract = outcome_table_contract()
    assert contract["schema"] == "coldguard-w20-pair-outcomes-v1"
    assert contract["filename"] == OUTCOME_TABLE_FILENAME
    names = {column["name"] for column in contract["columns"]}
    for required in (
        "pair_id",
        "run_A_id",
        "run_B_id",
        "controller_order",
        "hardware_config_id",
        "source_sha256_A",
        "source_sha256_B",
        "primary_outcome_name",
        "A_value",
        "B_value",
        "paired_improvement",
        "thermal_exposure_c_s",
        "recovery_time_s",
        "peak_temperature_c",
        "time_above_limit_s",
        "branch_energy_wh",
        "coverage_status",
        "undefined_reason_codes",
        "analysis_version",
    ):
        assert required in names
    assert contract["outcome_values_admitted"] is False
    assert contract["table_status"] == PAIR_OUTCOME_TABLE_NOT_PRODUCED


def test_metric_contracts_freeze_undefined_policies():
    metrics = {metric.metric_id: metric for metric in OUTCOME_METRICS}
    assert set(metrics) == {
        "thermal_exposure",
        "recovery_time",
        "peak_temperature",
        "time_above_limit",
        "branch_energy",
    }
    assert metrics["thermal_exposure"].zero_fill_forbidden
    assert "CENSORED" in " ".join(metrics["recovery_time"].undefined_policy)
    assert metrics["branch_energy"].whole_system_forbidden
    assert "COOLING_BRANCH" in metrics["branch_energy"].scope
    for metric in metrics.values():
        assert metric.canonical_ref
        assert metric.formula_contract


def test_metadata_row_validates_without_outcome_values():
    result = validate_pair_outcome_metadata(_metadata_row())
    assert result["status"] == "METADATA_VALIDATED_NO_OUTCOME_VALUES"
    assert result["outcome_values_present"] is False


def test_outcome_value_column_is_locked():
    with pytest.raises(W20AnalysisLockError):
        validate_pair_outcome_metadata(_metadata_row(A_value=3.2))
    with pytest.raises(W20AnalysisLockError):
        validate_pair_outcome_metadata(_metadata_row(paired_improvement=0.4))
    with pytest.raises(W20AnalysisLockError):
        validate_pair_outcome_metadata(_metadata_row(branch_energy_wh=1.0))


def test_unknown_metadata_column_is_refused():
    with pytest.raises(W20OutcomeContractError):
        validate_pair_outcome_metadata(_metadata_row(surprise="value"))


def test_missing_required_metadata_field_is_refused():
    row = _metadata_row()
    del row["coverage_status"]
    with pytest.raises(W20OutcomeContractError):
        validate_pair_outcome_metadata(row)


def test_undefined_reason_codes_are_frozen():
    assert undefined_reason("thermal_exposure", "TELEMETRY_GAP_COVERS_OUTCOME_WINDOW")
    assert undefined_reason("branch_energy", "PZEM_GAP_MISSING_SPAN")
    with pytest.raises(W20OutcomeContractError):
        undefined_reason("thermal_exposure", "GAP_IS_ZERO")
    assert set(UNDEFINED_REASON_CODES) == {
        metric.metric_id for metric in OUTCOME_METRICS
    }


def test_zero_fill_is_refused_for_incomplete_coverage():
    with pytest.raises(W20OutcomeContractError):
        assert_no_zero_fill("branch_energy", 0, "MISSING")
    with pytest.raises(W20OutcomeContractError):
        assert_no_zero_fill("thermal_exposure", 0, "INCOMPLETE")
    assert_no_zero_fill("branch_energy", 0, "COMPLETE")


def test_schema_verdicts_keep_data_unadmitted():
    verdicts = schema_verdicts()
    assert verdicts["OUTCOME_SCHEMA"] == OUTCOME_SCHEMA_SOFTWARE_VERIFIED
    assert verdicts["PHYSICAL_OUTCOME_DATA"] == PHYSICAL_OUTCOME_DATA_NOT_ADMITTED
    assert verdicts["PAIR_OUTCOME_TABLE"] == PAIR_OUTCOME_TABLE_NOT_PRODUCED


def test_admission_plan_without_ledger_is_blocked():
    plan = build_admission_plan(
        ledger_validation=None,
        outcome_definition_freeze=None,
        statistical_freeze=None,
        export_attempt_ids=None,
    )
    assert plan["row_count"] == 0
    assert plan["verdict"] == ADMISSION_BLOCKED_NO_VALID_PAIR
    assert plan["table_status"] == PAIR_OUTCOME_TABLE_NOT_PRODUCED
    assert plan["outcome_values_present"] is False


def _fixture_inputs(fixture_bundle):
    ledger = validate_pair_ledger(fixture_bundle["pair_ledger"])
    attempt_ids = fixture_bundle["export"]["manifest"]["attempt_ids"]
    coverage = [
        {
            "attempt_id": attempt_id,
            "metrics": {metric.metric_id: "COMPLETE" for metric in OUTCOME_METRICS},
        }
        for attempt_id in attempt_ids
    ]
    return ledger, attempt_ids, coverage


def test_fixture_admission_plan_is_metadata_ready(fixture_bundle):
    ledger, attempt_ids, coverage = _fixture_inputs(fixture_bundle)
    plan = build_admission_plan(
        ledger_validation=ledger,
        outcome_definition_freeze=fixture_bundle["outcome_definition_freeze"],
        statistical_freeze=fixture_bundle["statistical_freeze"],
        export_attempt_ids=attempt_ids,
        coverage_records=coverage,
    )
    assert plan["verdict"] == ADMISSION_METADATA_COMPLETE
    assert plan["row_count"] == 1
    row = plan["rows"][0]
    assert row["status"] == ADMISSION_METADATA_COMPLETE
    assert row["outcome_values_present"] is False
    assert "A_value" not in row
    assert row["coverage"]


def test_admission_plan_without_coverage_is_blocked(fixture_bundle):
    ledger, attempt_ids, _ = _fixture_inputs(fixture_bundle)
    plan = build_admission_plan(
        ledger_validation=ledger,
        outcome_definition_freeze=fixture_bundle["outcome_definition_freeze"],
        statistical_freeze=fixture_bundle["statistical_freeze"],
        export_attempt_ids=attempt_ids,
        coverage_records=None,
    )
    assert plan["rows"][0]["status"] == ADMISSION_BLOCKED_MISSING_COVERAGE
    assert plan["verdict"] != ADMISSION_METADATA_COMPLETE


def test_admission_plan_without_freeze_is_blocked(fixture_bundle):
    ledger, attempt_ids, coverage = _fixture_inputs(fixture_bundle)
    plan = build_admission_plan(
        ledger_validation=ledger,
        outcome_definition_freeze=None,
        statistical_freeze=None,
        export_attempt_ids=attempt_ids,
        coverage_records=coverage,
    )
    assert plan["verdict"] != ADMISSION_METADATA_COMPLETE
    assert plan["freeze_problems"]


def test_analysis_lock_always_refuses():
    with pytest.raises(W20AnalysisLockError):
        assert_outcome_analysis_locked("pair-outcomes.csv")


def test_pair_outcomes_csv_is_not_created():
    assert not (W20_DIR / OUTCOME_TABLE_FILENAME).exists()
