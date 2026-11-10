"""W20 pair-outcomes contract without outcome computation (B-W20-02).

Canonical anchors: Doc 03 §§68-75, §133; Doc 05B §48 B-W20-02; W03
``statistical-analysis-plan-v0.md`` and W03 ``metric-spec.md``.

This module prepares the future ``pair-outcomes.csv`` schema, its metric
definitions, undefined/censoring rules and the metadata-only admission plan.
It deliberately contains no integration, recovery, energy or paired-difference
implementation.  Every route that would accept a physical outcome value is
locked; an authorized analysis execution must live outside W20 and outside
this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

OUTCOME_TABLE_SCHEMA = "coldguard-w20-pair-outcomes-v1"
OUTCOME_TABLE_FILENAME = "pair-outcomes.csv"
W20_OUTCOME_CONTRACT_VERSION = "coldguard-w20-pair-outcome-contract-v1"

OUTCOME_SCHEMA_SOFTWARE_VERIFIED = "OUTCOME_SCHEMA_SOFTWARE_VERIFIED"
PHYSICAL_OUTCOME_DATA_NOT_ADMITTED = "PHYSICAL_OUTCOME_DATA_NOT_ADMITTED"
PAIR_OUTCOME_TABLE_NOT_PRODUCED = "PAIR_OUTCOME_TABLE_NOT_PRODUCED"

PRIMARY_VALUE = "PRIMARY_VALUE"
SECONDARY_VALUE = "SECONDARY_VALUE"
IDENTITY = "IDENTITY"
METADATA_ONLY = "METADATA_ONLY"

COVERAGE_COMPLETE = "COMPLETE"
COVERAGE_INCOMPLETE = "INCOMPLETE"
COVERAGE_MISSING = "MISSING"
COVERAGE_UNKNOWN = "UNKNOWN"
COVERAGE_VALUES = frozenset(
    {COVERAGE_COMPLETE, COVERAGE_INCOMPLETE, COVERAGE_MISSING, COVERAGE_UNKNOWN}
)

ANALYSIS_LOCK_MESSAGE = (
    "W20 pair-outcome values are locked: a separate authorized final-analysis "
    "execution is required after external campaign acceptance, an approved "
    "statistical freeze and an approved analysis authorization"
)

ADMISSION_METADATA_COMPLETE = "ROW_METADATA_COMPLETE_PENDING_AUTHORIZED_EXECUTION"
ADMISSION_BLOCKED_MISSING_FREEZE = "BLOCKED_MISSING_OUTCOME_FREEZE"
ADMISSION_BLOCKED_MISSING_COVERAGE = "BLOCKED_MISSING_COVERAGE_METADATA"
ADMISSION_BLOCKED_NO_VALID_PAIR = "BLOCKED_NO_VALID_PAIR"
ADMISSION_BLOCKED_EXPORT_MISMATCH = "BLOCKED_EXPORT_ATTEMPT_MISMATCH"


class W20OutcomeContractError(ValueError):
    """Raised when an outcome value or malformed contract row is presented."""


class W20AnalysisLockError(W20OutcomeContractError):
    """Raised whenever W20 is asked to produce physical outcome values."""


@dataclass(frozen=True)
class OutcomeColumn:
    name: str
    dtype: str
    role: str
    required: bool
    canonical_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "role": self.role,
            "required": self.required,
            "canonical_ref": self.canonical_ref,
        }


@dataclass(frozen=True)
class OutcomeMetricContract:
    metric_id: str
    unit: str
    role: str
    scope: str
    definition: str
    formula_contract: str
    required_inputs: tuple[str, ...]
    undefined_policy: tuple[str, ...]
    zero_fill_forbidden: bool
    whole_system_forbidden: bool
    canonical_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "unit": self.unit,
            "role": self.role,
            "scope": self.scope,
            "definition": self.definition,
            "formula_contract": self.formula_contract,
            "required_inputs": list(self.required_inputs),
            "undefined_policy": list(self.undefined_policy),
            "zero_fill_forbidden": self.zero_fill_forbidden,
            "whole_system_forbidden": self.whole_system_forbidden,
            "canonical_ref": self.canonical_ref,
        }


PAIR_OUTCOME_COLUMNS: tuple[OutcomeColumn, ...] = (
    OutcomeColumn("pair_id", "string", IDENTITY, True, "03 §95-98"),
    OutcomeColumn("run_A_id", "string", IDENTITY, True, "03 §34-37, §95-98"),
    OutcomeColumn("run_B_id", "string", IDENTITY, True, "03 §34-37, §95-98"),
    OutcomeColumn("controller_order", "string", IDENTITY, True, "03 §36"),
    OutcomeColumn("hardware_config_id", "string", IDENTITY, True, "03 §35"),
    OutcomeColumn("calibration_id", "string", IDENTITY, True, "03 §35"),
    OutcomeColumn("firmware_version", "string", IDENTITY, True, "03 §92"),
    OutcomeColumn("model_artifact_sha256_B", "string", IDENTITY, True, "03 §92"),
    OutcomeColumn("source_sha256_A", "string", IDENTITY, True, "03 §158-163"),
    OutcomeColumn("source_sha256_B", "string", IDENTITY, True, "03 §158-163"),
    OutcomeColumn("analysis_version", "string", IDENTITY, True, "03 §130-135"),
    OutcomeColumn("primary_outcome_name", "string", IDENTITY, True, "03 §133"),
    OutcomeColumn("primary_outcome_version", "string", IDENTITY, True, "03 §133"),
    OutcomeColumn("A_value", "number|UNDEFINED", PRIMARY_VALUE, True, "03 §74"),
    OutcomeColumn("B_value", "number|UNDEFINED", PRIMARY_VALUE, True, "03 §74"),
    OutcomeColumn("paired_improvement", "number|UNDEFINED", PRIMARY_VALUE, True, "03 §74"),
    OutcomeColumn("thermal_exposure_c_s", "number|UNDEFINED", SECONDARY_VALUE, True, "03 §68-69"),
    OutcomeColumn("recovery_time_s", "number|CENSORED|UNDEFINED", SECONDARY_VALUE, True, "03 §70"),
    OutcomeColumn("peak_temperature_c", "number|UNDEFINED", SECONDARY_VALUE, True, "03 §71"),
    OutcomeColumn("time_above_limit_s", "number|UNDEFINED", SECONDARY_VALUE, True, "03 §71"),
    OutcomeColumn("branch_energy_wh", "number|UNDEFINED", SECONDARY_VALUE, True, "03 §72"),
    OutcomeColumn("supporting_outcomes_json", "object|UNDEFINED", SECONDARY_VALUE, False, "05B §48"),
    OutcomeColumn("coverage_status", "object", METADATA_ONLY, True, "03 §130-135"),
    OutcomeColumn("undefined_reason_codes", "array", METADATA_ONLY, True, "metric-spec §6-8"),
    OutcomeColumn("validity_flags", "object", METADATA_ONLY, True, "03 §95-98"),
    OutcomeColumn("metric_versions", "object", METADATA_ONLY, True, "03 §130-135"),
)

OUTCOME_VALUE_COLUMNS = frozenset(
    {
        "A_value",
        "B_value",
        "paired_improvement",
        "thermal_exposure_c_s",
        "recovery_time_s",
        "peak_temperature_c",
        "time_above_limit_s",
        "branch_energy_wh",
        "supporting_outcomes_json",
    }
)
IDENTITY_COLUMNS = frozenset(
    column.name for column in PAIR_OUTCOME_COLUMNS if column.role == IDENTITY
)
METADATA_COLUMNS = frozenset(
    column.name for column in PAIR_OUTCOME_COLUMNS if column.role == METADATA_ONLY
)
ROW_METADATA_KEYS = IDENTITY_COLUMNS | METADATA_COLUMNS

OUTCOME_METRICS: tuple[OutcomeMetricContract, ...] = (
    OutcomeMetricContract(
        metric_id="thermal_exposure",
        unit="degC*s",
        role="PRIMARY",
        scope="PAIR_ARM_COOLING_ZONE",
        definition=(
            "Integral of representative temperature above the frozen limit over "
            "the frozen campaign measurement window."
        ),
        formula_contract="E_T = integral max(0, T(t) - T_limit) dt",
        required_inputs=(
            "representative_temperature_series",
            "frozen_t_limit",
            "quality_flags",
            "coverage_spans",
        ),
        undefined_policy=(
            "missing or corrupted spans are excluded and coverage is reported",
            "coverage below the frozen floor makes the outcome undefined",
            "no interpolation across gaps and no zero fill",
            "the representative-temperature choice is frozen before the campaign",
        ),
        zero_fill_forbidden=True,
        whole_system_forbidden=False,
        canonical_ref="03 §68-69; metric-spec §6",
    ),
    OutcomeMetricContract(
        metric_id="recovery_time",
        unit="s",
        role="SECONDARY",
        scope="PAIR_ARM_COOLING_ZONE",
        definition=(
            "Time from the frozen recovery reference until the representative "
            "temperature re-enters the frozen band and stays for the frozen "
            "persistence."
        ),
        formula_contract="T_recovery = t_recovered - t_reference",
        required_inputs=(
            "representative_temperature_series",
            "frozen_recovery_reference",
            "frozen_recovery_band",
            "frozen_recovery_persistence",
            "coverage_spans",
        ),
        undefined_policy=(
            "an unfinished recovery is CENSORED, never a finite recovery time",
            "a missing crossing is undefined, never zero",
            "electrical observation cannot substitute for thermal recovery",
        ),
        zero_fill_forbidden=True,
        whole_system_forbidden=False,
        canonical_ref="03 §70; metric-spec §7",
    ),
    OutcomeMetricContract(
        metric_id="peak_temperature",
        unit="degC",
        role="SECONDARY",
        scope="PAIR_ARM_COOLING_ZONE",
        definition="Maximum representative temperature on the frozen series and time base.",
        formula_contract="max(T(t)) over the frozen measurement window",
        required_inputs=("representative_temperature_series", "frozen_time_base"),
        undefined_policy=(
            "one physical measurement and one time base are used for both arms",
            "post-hoc selection of a more favorable representation is forbidden",
        ),
        zero_fill_forbidden=True,
        whole_system_forbidden=False,
        canonical_ref="03 §71; metric-spec §6",
    ),
    OutcomeMetricContract(
        metric_id="time_above_limit",
        unit="s",
        role="SECONDARY",
        scope="PAIR_ARM_COOLING_ZONE",
        definition="Measured time with representative temperature above the frozen limit.",
        formula_contract="sum(dt_i where T_i > T_limit)",
        required_inputs=("representative_temperature_series", "frozen_t_limit", "frozen_time_base"),
        undefined_policy=(
            "one physical measurement and one time base are used for both arms",
            "gaps are excluded with coverage reported; no zero fill",
        ),
        zero_fill_forbidden=True,
        whole_system_forbidden=False,
        canonical_ref="03 §71; metric-spec §6",
    ),
    OutcomeMetricContract(
        metric_id="branch_energy",
        unit="Wh",
        role="SECONDARY",
        scope="COOLING_BRANCH_PZEM_ONLY",
        definition="Electrical energy measured on the cooling branch only.",
        formula_contract="E_Wh = sum(P_i * dt_i) / 3600 over the cooling branch",
        required_inputs=(
            "cooling_branch_power_or_validated_counter",
            "coverage_spans",
            "counter_reset_log",
        ),
        undefined_policy=(
            "missing PZEM samples are missing spans, never zero Wh",
            "counter resets are segmented and logged; unresolvable spans are undefined",
            "cooling-branch energy must never be labelled whole-system energy",
        ),
        zero_fill_forbidden=True,
        whole_system_forbidden=True,
        canonical_ref="03 §72, §102; metric-spec §8",
    ),
)

UNDEFINED_REASON_CODES = {
    "thermal_exposure": (
        "TELEMETRY_GAP_COVERS_OUTCOME_WINDOW",
        "COVERAGE_BELOW_FROZEN_FLOOR",
        "REPRESENTATIVE_TEMPERATURE_UNFROZEN",
    ),
    "recovery_time": (
        "RECOVERY_CENSORED_NOT_OBSERVED",
        "RECOVERY_REFERENCE_UNFROZEN",
        "RECOVERY_BAND_UNFROZEN",
        "ELECTRICAL_OBSERVATION_IS_NOT_THERMAL_RECOVERY",
    ),
    "peak_temperature": (
        "TELEMETRY_GAP_COVERS_OUTCOME_WINDOW",
        "REPRESENTATIVE_TEMPERATURE_UNFROZEN",
    ),
    "time_above_limit": (
        "TELEMETRY_GAP_COVERS_OUTCOME_WINDOW",
        "TIME_BASE_INCONSISTENT",
    ),
    "branch_energy": (
        "PZEM_GAP_MISSING_SPAN",
        "ENERGY_COUNTER_RESET_UNRESOLVED",
        "WHOLE_SYSTEM_ENERGY_NOT_ADMISSIBLE",
    ),
}


def outcome_table_contract() -> dict[str, Any]:
    """Return the future output contract; never a produced table."""
    return {
        "schema": OUTCOME_TABLE_SCHEMA,
        "contract_version": W20_OUTCOME_CONTRACT_VERSION,
        "filename": OUTCOME_TABLE_FILENAME,
        "statistical_unit": "one valid matched Controller A/B pair",
        "columns": [column.to_dict() for column in PAIR_OUTCOME_COLUMNS],
        "metrics": [metric.to_dict() for metric in OUTCOME_METRICS],
        "undefined_reason_codes": {
            metric: list(codes) for metric, codes in UNDEFINED_REASON_CODES.items()
        },
        "outcome_values_admitted": False,
        "table_status": PAIR_OUTCOME_TABLE_NOT_PRODUCED,
        "withheld_path": f"ml/reports/W20/{OUTCOME_TABLE_FILENAME}",
    }


def schema_verdicts() -> dict[str, str]:
    return {
        "OUTCOME_SCHEMA": OUTCOME_SCHEMA_SOFTWARE_VERIFIED,
        "PHYSICAL_OUTCOME_DATA": PHYSICAL_OUTCOME_DATA_NOT_ADMITTED,
        "PAIR_OUTCOME_TABLE": PAIR_OUTCOME_TABLE_NOT_PRODUCED,
    }


def undefined_reason(metric_id: str, condition: str) -> str:
    codes = UNDEFINED_REASON_CODES.get(metric_id)
    if codes is None:
        raise W20OutcomeContractError(f"unknown outcome metric {metric_id!r}")
    if condition not in codes:
        raise W20OutcomeContractError(
            f"unknown undefined condition {condition!r} for metric {metric_id!r}"
        )
    return condition


def assert_no_zero_fill(metric_id: str, value: Any, coverage: str) -> None:
    """A missing/gapped span can never become a zero outcome value."""
    if coverage not in COVERAGE_VALUES:
        raise W20OutcomeContractError(f"unknown coverage value {coverage!r}")
    if value == 0 and coverage != COVERAGE_COMPLETE:
        raise W20OutcomeContractError(
            f"{metric_id}: zero value with coverage {coverage} would be a "
            "zero-fill violation; report the outcome as undefined/censored"
        )


def assert_outcome_values_not_admitted(row: Mapping[str, Any]) -> None:
    if not isinstance(row, Mapping):
        raise W20OutcomeContractError("pair-outcome row must be an object")
    present = sorted(set(row) & OUTCOME_VALUE_COLUMNS)
    if present:
        raise W20AnalysisLockError(
            f"{PHYSICAL_OUTCOME_DATA_NOT_ADMITTED}: outcome value column(s) "
            f"{', '.join(present)} are locked in W20; {ANALYSIS_LOCK_MESSAGE}"
        )


def validate_pair_outcome_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the metadata shell of a future row, never its outcome values."""
    assert_outcome_values_not_admitted(row)
    unknown = sorted(set(row) - ROW_METADATA_KEYS)
    if unknown:
        raise W20OutcomeContractError(
            "pair-outcome metadata row contains unknown field(s): " + ", ".join(unknown)
        )
    required = {
        "pair_id",
        "run_A_id",
        "run_B_id",
        "analysis_version",
        "primary_outcome_name",
        "primary_outcome_version",
        "coverage_status",
        "undefined_reason_codes",
        "validity_flags",
        "metric_versions",
    }
    missing = sorted(required - set(row))
    if missing:
        raise W20OutcomeContractError(
            "pair-outcome metadata row lacks field(s): " + ", ".join(missing)
        )
    coverage = row.get("coverage_status")
    if not isinstance(coverage, Mapping):
        raise W20OutcomeContractError("coverage_status must be an object")
    for metric_id, value in coverage.items():
        if metric_id not in {metric.metric_id for metric in OUTCOME_METRICS}:
            raise W20OutcomeContractError(f"unknown coverage metric {metric_id!r}")
        if value not in COVERAGE_VALUES:
            raise W20OutcomeContractError(
                f"coverage_status[{metric_id!r}] has unknown value {value!r}"
            )
    reasons = row.get("undefined_reason_codes")
    if not isinstance(reasons, list) or any(not isinstance(code, str) for code in reasons):
        raise W20OutcomeContractError("undefined_reason_codes must be a list of strings")
    known = {code for codes in UNDEFINED_REASON_CODES.values() for code in codes}
    unknown_codes = sorted(set(reasons) - known)
    if unknown_codes:
        raise W20OutcomeContractError(
            "undeclared undefined reason code(s): " + ", ".join(unknown_codes)
        )
    return {
        "pair_id": row["pair_id"],
        "status": "METADATA_VALIDATED_NO_OUTCOME_VALUES",
        "outcome_values_present": False,
        "analysis_effect": "NONE_OUTCOME_CONTRACT_METADATA_ONLY",
    }


def _freeze_approved(record: Any, *, fields: Sequence[str]) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(record, Mapping):
        return False, ("FREEZE_RECORD_MISSING",)
    problems: list[str] = []
    if record.get("status") != "FROZEN_APPROVED":
        problems.append("FREEZE_NOT_APPROVED")
    payload = record.get("fields")
    if not isinstance(payload, Mapping):
        problems.append("FREEZE_FIELDS_MISSING")
        payload = {}
    for field_id in fields:
        entry = payload.get(field_id)
        if isinstance(entry, Mapping):
            if entry.get("value") in (None, "", [], {}):
                problems.append(f"FREEZE_FIELD_NULL:{field_id}")
            if entry.get("status") != "FROZEN_APPROVED":
                problems.append(f"FREEZE_FIELD_NOT_APPROVED:{field_id}")
        elif entry in (None, "", [], {}):
            problems.append(f"FREEZE_FIELD_MISSING:{field_id}")
    approval = record.get("approval")
    if not (
        isinstance(approval, Mapping)
        and approval.get("authority_id")
        and approval.get("authority_role") == "TEAM_LEAD"
        and approval.get("canonical_ref")
    ):
        problems.append("FREEZE_APPROVAL_INVALID")
    return (not problems, tuple(sorted(problems)))


def build_admission_plan(
    *,
    ledger_validation: Any,
    outcome_definition_freeze: Mapping[str, Any] | None,
    statistical_freeze: Mapping[str, Any] | None,
    export_attempt_ids: Sequence[str] | None,
    coverage_records: Sequence[Mapping[str, Any]] | None = None,
    statistical_freeze_fields: Sequence[str] = (
        "primary_outcome",
        "paired_sign_convention",
        "confidence_level",
        "bootstrap_seed",
        "bootstrap_iterations",
        "test_family",
        "invalid_pair_handling",
        "secondary_outcomes",
    ),
) -> dict[str, Any]:
    """Prepare per-pair source requirements; never produce an outcome row."""
    statistical_ok, statistical_problems = _freeze_approved(
        statistical_freeze, fields=statistical_freeze_fields
    )
    outcome_ok, outcome_problems = _freeze_approved(
        outcome_definition_freeze,
        fields=(
            "primary_outcome",
            "representative_temperature",
            "t_limit_critical_target",
            "recovery_reference_time",
            "recovery_band",
            "recovery_persistence",
            "measurement_coverage_rules",
            "energy_source_admissibility",
        ),
    )
    coverage_by_attempt: dict[str, Mapping[str, Any]] = {}
    if coverage_records is not None:
        for record in coverage_records:
            if not isinstance(record, Mapping):
                raise W20OutcomeContractError("coverage record must be an object")
            coverage_by_attempt[str(record.get("attempt_id"))] = record
    export_ids = set(map(str, export_attempt_ids)) if export_attempt_ids is not None else None
    plans: list[dict[str, Any]] = []
    if ledger_validation is None:
        return {
            "rows": [],
            "row_count": 0,
            "table_status": PAIR_OUTCOME_TABLE_NOT_PRODUCED,
            "verdict": ADMISSION_BLOCKED_NO_VALID_PAIR,
            "freeze_problems": list(statistical_problems + outcome_problems),
            "outcome_values_present": False,
        }
    for pair in ledger_validation.pairs:
        if pair.status != "PAIR_VALID":
            continue
        run_a = pair.selected_attempts.get("A")
        run_b = pair.selected_attempts.get("B")
        problems: list[str] = []
        if not statistical_ok:
            problems.extend(f"STATISTICAL:{problem}" for problem in statistical_problems)
        if not outcome_ok:
            problems.extend(f"OUTCOME:{problem}" for problem in outcome_problems)
        if run_a is None or run_b is None:
            problems.append("PAIR_ARM_IDENTITY_MISSING")
        if export_ids is not None and (
            run_a not in export_ids or run_b not in export_ids
        ):
            problems.append(ADMISSION_BLOCKED_EXPORT_MISMATCH)
        coverage: dict[str, str] = {}
        for run_id in (run_a, run_b):
            record = coverage_by_attempt.get(str(run_id))
            if record is None:
                problems.append(f"COVERAGE_METADATA_MISSING:{run_id}")
                continue
            metrics = record.get("metrics")
            if not isinstance(metrics, Mapping):
                problems.append(f"COVERAGE_METADATA_MALFORMED:{run_id}")
                continue
            for metric in OUTCOME_METRICS:
                value = metrics.get(metric.metric_id, COVERAGE_UNKNOWN)
                if value not in COVERAGE_VALUES:
                    problems.append(f"COVERAGE_VALUE_INVALID:{run_id}:{metric.metric_id}")
                    continue
                coverage[f"{run_id}:{metric.metric_id}"] = value
                if value != COVERAGE_COMPLETE:
                    problems.append(
                        f"OUTCOME_UNDEFINED_OR_CENSORED:{run_id}:{metric.metric_id}:{value}"
                    )
        if problems:
            if not statistical_ok or not outcome_ok:
                status = ADMISSION_BLOCKED_MISSING_FREEZE
            elif any(p.startswith("COVERAGE_METADATA") for p in problems):
                status = ADMISSION_BLOCKED_MISSING_COVERAGE
            elif ADMISSION_BLOCKED_EXPORT_MISMATCH in problems:
                status = ADMISSION_BLOCKED_EXPORT_MISMATCH
            else:
                status = ADMISSION_BLOCKED_MISSING_COVERAGE
        else:
            status = ADMISSION_METADATA_COMPLETE
        plans.append(
            {
                "pair_id": pair.pair_id,
                "run_A_id": run_a,
                "run_B_id": run_b,
                "required_sources": [
                    "run_A_raw_source_receipt",
                    "run_B_raw_source_receipt",
                    "outcome_definition_freeze",
                    "statistical_freeze",
                    "per_metric_coverage_flags",
                ],
                "coverage": coverage,
                "status": status,
                "problems": sorted(set(problems)),
                "outcome_values_present": False,
            }
        )
    verdict = (
        ADMISSION_METADATA_COMPLETE
        if plans and all(plan["status"] == ADMISSION_METADATA_COMPLETE for plan in plans)
        else (ADMISSION_BLOCKED_NO_VALID_PAIR if not plans else "BLOCKED_PENDING_FIXES")
    )
    return {
        "rows": plans,
        "row_count": len(plans),
        "table_status": PAIR_OUTCOME_TABLE_NOT_PRODUCED,
        "verdict": verdict,
        "freeze_problems": sorted(set(statistical_problems + outcome_problems)),
        "outcome_values_present": False,
    }


def assert_outcome_analysis_locked(operation: str = "pair_outcomes") -> None:
    """Every W20 route to outcome values fails closed."""
    raise W20AnalysisLockError(f"{operation}: {ANALYSIS_LOCK_MESSAGE}")
