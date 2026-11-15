"""W19 outcome-blinded attempt validity review (B-W19-02).

Canonical anchors: Doc 03 §§6-8, 34-35, 95-98, 159; Doc 05B §47 B-W19-02.

Validity is derived from predeclared protocol, provenance, quality and
completeness failures.  The review input has no outcome fields by design, so a
Controller B result cannot make a run eligible or ineligible.  A protocol-valid
pair stays valid when B performed worse; a protocol-invalid run is rejected even
when B performed better.  Missing metric coverage makes that metric undefined;
it is never converted to a zero value.

This module cannot compute an outcome, a paired difference, a p-value or a
confidence interval.  It does not decide pair-level inclusion on its own; the
pair ledger combines arm decisions with matching and freeze evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from coldguard_ml.w19_no_peeking import assert_outcome_blind

VALIDITY_METHOD_VERSION = "coldguard-w19-validity-review-v1"

VALIDITY_VALID = "VALID"
VALIDITY_INVALID = "INVALID"
VALIDITY_PENDING = "PENDING"
VALIDITY_NOT_APPLICABLE = "NOT_APPLICABLE"

QUALITY_PASS = "QUALITY_PASS"
QUALITY_FAIL = "QUALITY_FAIL"
QUALITY_PENDING = "QUALITY_PENDING"

DISTURBANCE_EXECUTED_WITHIN_TOLERANCE = "EXECUTED_WITHIN_TOLERANCE"
DISTURBANCE_EXECUTED_OUT_OF_TOLERANCE = "EXECUTED_OUT_OF_TOLERANCE"
DISTURBANCE_NOT_EXECUTED = "NOT_EXECUTED"
DISTURBANCE_UNKNOWN = "UNKNOWN"

RESET_MET_VERIFIED = "MET_VERIFIED"
RESET_NOT_MET = "NOT_MET"
RESET_EVIDENCE_MISSING = "EVIDENCE_MISSING"

TIME_VALID = "VALID"
TIME_INVALID = "INVALID"
TIME_UNKNOWN = "UNKNOWN"

INTERVENTION_NONE = "NONE"
INTERVENTION_PROTOCOL = "PROTOCOL"
INTERVENTION_UNPROTOCOL = "UNPROTOCOL"

COVERAGE_COMPLETE = "COMPLETE"
COVERAGE_INCOMPLETE = "INCOMPLETE"
COVERAGE_MISSING = "MISSING"
COVERAGE_UNKNOWN = "UNKNOWN"

ADMISSIBLE = "ADMISSIBLE"
UNDEFINED_INCOMPLETE = "UNDEFINED_INCOMPLETE"

ROLE_PRIMARY = "PRIMARY"
ROLE_SECONDARY = "SECONDARY"

REASON_ATTEMPT_ABORTED = "ATTEMPT_ABORTED"
REASON_HARDWARE_IDENTITY_MISSING = "HARDWARE_IDENTITY_MISSING"
REASON_CALIBRATION_MISSING = "CALIBRATION_PROVENANCE_MISSING"
REASON_FIRMWARE_MISSING = "FIRMWARE_IDENTITY_MISSING"
REASON_PROTOCOL_VERSION_MISSING = "PROTOCOL_VERSION_MISSING"
REASON_DISTURBANCE_NOT_EXECUTED = "DISTURBANCE_NOT_EXECUTED"
REASON_DISTURBANCE_TOLERANCE = "DISTURBANCE_TOLERANCE_EXCEEDED"
REASON_DISTURBANCE_UNKNOWN = "DISTURBANCE_STATUS_UNKNOWN"
REASON_RESET_NOT_MET = "INITIAL_RESET_CRITERION_NOT_MET"
REASON_RESET_EVIDENCE_MISSING = "INITIAL_RESET_EVIDENCE_MISSING"
REASON_PHYSICAL_QUALITY_INVALID = "PHYSICAL_QUALITY_INVALID"
REASON_PHYSICAL_QUALITY_UNVERIFIED = "PHYSICAL_QUALITY_UNVERIFIED"
REASON_TEMPORAL_INVALID = "TEMPORAL_ORDER_INVALID"
REASON_TEMPORAL_UNKNOWN = "TEMPORAL_ORDER_UNVERIFIED"
REASON_CONTROLLER_ORDER_MISSING = "CONTROLLER_ORDER_RECORD_MISSING"
REASON_SAFETY_STOP = "SAFETY_STOP_RECORDED"
REASON_UNPROTOCOL_INTERVENTION = "UNPROTOCOL_OPERATOR_INTERVENTION"
REASON_PRIMARY_INCOMPLETE = "TELEMETRY_GAP_COVERS_PRIMARY_EVENT"
REASON_PRIMARY_COMPLETENESS_UNKNOWN = "PRIMARY_OUTCOME_COMPLETENESS_UNKNOWN"

INVALID_REASON_CODES = frozenset(
    {
        REASON_ATTEMPT_ABORTED,
        REASON_HARDWARE_IDENTITY_MISSING,
        REASON_CALIBRATION_MISSING,
        REASON_FIRMWARE_MISSING,
        REASON_PROTOCOL_VERSION_MISSING,
        REASON_DISTURBANCE_NOT_EXECUTED,
        REASON_DISTURBANCE_TOLERANCE,
        REASON_RESET_NOT_MET,
        REASON_RESET_EVIDENCE_MISSING,
        REASON_PHYSICAL_QUALITY_INVALID,
        REASON_TEMPORAL_INVALID,
        REASON_CONTROLLER_ORDER_MISSING,
        REASON_SAFETY_STOP,
        REASON_UNPROTOCOL_INTERVENTION,
        REASON_PRIMARY_INCOMPLETE,
    }
)

PENDING_REASON_CODES = frozenset(
    {
        REASON_DISTURBANCE_UNKNOWN,
        REASON_PHYSICAL_QUALITY_UNVERIFIED,
        REASON_TEMPORAL_UNKNOWN,
        REASON_PRIMARY_COMPLETENESS_UNKNOWN,
    }
)

PREDECLARED_VALIDITY_REASON_CODES = INVALID_REASON_CODES | PENDING_REASON_CODES


class W19ValidityError(ValueError):
    """Raised for malformed validity input, never for a policy verdict."""


@dataclass(frozen=True)
class MetricSpec:
    metric_id: str
    role: str
    coverage_key: str
    canonical_ref: str


METRIC_CONTRACTS: tuple[MetricSpec, ...] = (
    MetricSpec(
        "thermal_exposure",
        ROLE_PRIMARY,
        "thermal_primary",
        "Doc 03 §68-69; SAP §4.1",
    ),
    MetricSpec(
        "recovery_time",
        ROLE_SECONDARY,
        "thermal_recovery",
        "Doc 03 §70; SAP §4.7",
    ),
    MetricSpec(
        "branch_energy",
        ROLE_SECONDARY,
        "electrical_energy",
        "Doc 03 §72, §102; metric-spec §8",
    ),
)

COVERAGE_VALUES = frozenset(
    {COVERAGE_COMPLETE, COVERAGE_INCOMPLETE, COVERAGE_MISSING, COVERAGE_UNKNOWN}
)

ALLOWED_INPUT_FIELDS = frozenset(
    {
        "attempt_id",
        "pair_id",
        "run_id",
        "controller_arm",
        "hardware_config_id",
        "calibration_id",
        "firmware_version",
        "protocol_version",
        "disturbance_execution",
        "reset_criterion",
        "quality_status",
        "completeness",
        "time_sequence_validity",
        "controller_order_recorded",
        "safety_stop_recorded",
        "operator_intervention",
    }
)


@dataclass(frozen=True)
class AttemptValidityInput:
    attempt_id: str
    pair_id: str
    run_id: str
    controller_arm: str
    hardware_config_id: str | None
    calibration_id: str | None
    firmware_version: str | None
    protocol_version: str | None
    disturbance_execution: str
    reset_criterion: str
    quality_status: str
    completeness: Mapping[str, str]
    time_sequence_validity: str
    controller_order_recorded: bool
    safety_stop_recorded: bool
    operator_intervention: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AttemptValidityInput":
        if not isinstance(payload, Mapping):
            raise W19ValidityError("validity input must be an object")
        assert_outcome_blind(payload, context="validity input")
        unknown = sorted(set(payload) - ALLOWED_INPUT_FIELDS)
        if unknown:
            raise W19ValidityError(
                f"validity input contains unknown field(s): {', '.join(unknown)}"
            )
        missing = sorted(ALLOWED_INPUT_FIELDS - set(payload))
        if missing:
            raise W19ValidityError(
                f"validity input lacks required field(s): {', '.join(missing)}"
            )
        completeness = payload["completeness"]
        if not isinstance(completeness, Mapping):
            raise W19ValidityError("completeness must be an object of coverage values")
        return cls(
            attempt_id=str(payload["attempt_id"]),
            pair_id=str(payload["pair_id"]),
            run_id=str(payload["run_id"]),
            controller_arm=str(payload["controller_arm"]),
            hardware_config_id=payload["hardware_config_id"],
            calibration_id=payload["calibration_id"],
            firmware_version=payload["firmware_version"],
            protocol_version=payload["protocol_version"],
            disturbance_execution=str(payload["disturbance_execution"]),
            reset_criterion=str(payload["reset_criterion"]),
            quality_status=str(payload["quality_status"]),
            completeness=dict(completeness),
            time_sequence_validity=str(payload["time_sequence_validity"]),
            controller_order_recorded=payload["controller_order_recorded"],
            safety_stop_recorded=payload["safety_stop_recorded"],
            operator_intervention=str(payload["operator_intervention"]),
        )


@dataclass(frozen=True)
class MetricAdmissibility:
    metric_id: str
    role: str
    coverage: str
    admissibility: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "role": self.role,
            "coverage": self.coverage,
            "admissibility": self.admissibility,
        }


@dataclass(frozen=True)
class AttemptValidityDecision:
    attempt_id: str
    pair_id: str
    run_id: str
    controller_arm: str
    validity_status: str
    reason_codes: tuple[str, ...]
    quality_status: str
    metric_admissibility: tuple[MetricAdmissibility, ...]
    primary_pair_eligible: bool
    decision_method: str
    outcome_fields_used: bool = False
    approval_effect: str = "NONE_VALIDITY_SOFTWARE_ASSESSMENT_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "pair_id": self.pair_id,
            "run_id": self.run_id,
            "controller_arm": self.controller_arm,
            "validity_status": self.validity_status,
            "reason_codes": list(self.reason_codes),
            "quality_status": self.quality_status,
            "metric_admissibility": [
                metric.to_dict() for metric in self.metric_admissibility
            ],
            "primary_pair_eligible": self.primary_pair_eligible,
            "decision_method": self.decision_method,
            "outcome_fields_used": self.outcome_fields_used,
            "approval_effect": self.approval_effect,
        }


def _require_choice(value: str, allowed: frozenset[str], field: str) -> None:
    if value not in allowed:
        raise W19ValidityError(
            f"{field} has unknown value {value!r}; allowed: {sorted(allowed)}"
        )


def _require_identity(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _metric_admissibility(completeness: Mapping[str, str]) -> tuple[MetricAdmissibility, ...]:
    metrics: list[MetricAdmissibility] = []
    for spec in METRIC_CONTRACTS:
        coverage = completeness.get(spec.coverage_key, COVERAGE_UNKNOWN)
        if coverage not in COVERAGE_VALUES:
            raise W19ValidityError(
                f"completeness[{spec.coverage_key!r}] has unknown value {coverage!r}"
            )
        metrics.append(
            MetricAdmissibility(
                metric_id=spec.metric_id,
                role=spec.role,
                coverage=coverage,
                admissibility=(
                    ADMISSIBLE if coverage == COVERAGE_COMPLETE else UNDEFINED_INCOMPLETE
                ),
            )
        )
    return tuple(metrics)


def assess_attempt_validity(
    record: AttemptValidityInput | Mapping[str, Any],
) -> AttemptValidityDecision:
    """Derive validity from predeclared protocol/quality evidence only."""
    if isinstance(record, Mapping):
        record = AttemptValidityInput.from_mapping(record)
    if not isinstance(record, AttemptValidityInput):
        raise W19ValidityError("validity input must be AttemptValidityInput or a mapping")

    if not _require_identity(record.attempt_id) or not _require_identity(record.pair_id):
        raise W19ValidityError("attempt_id and pair_id must be non-empty strings")
    if not _require_identity(record.run_id):
        raise W19ValidityError("run_id must be a non-empty string")
    if record.controller_arm not in {"A", "B"}:
        raise W19ValidityError("controller_arm must be 'A' or 'B'")
    _require_choice(
        record.disturbance_execution,
        frozenset(
            {
                DISTURBANCE_EXECUTED_WITHIN_TOLERANCE,
                DISTURBANCE_EXECUTED_OUT_OF_TOLERANCE,
                DISTURBANCE_NOT_EXECUTED,
                DISTURBANCE_UNKNOWN,
            }
        ),
        "disturbance_execution",
    )
    _require_choice(
        record.reset_criterion,
        frozenset({RESET_MET_VERIFIED, RESET_NOT_MET, RESET_EVIDENCE_MISSING}),
        "reset_criterion",
    )
    _require_choice(
        record.quality_status,
        frozenset({QUALITY_PASS, QUALITY_FAIL, QUALITY_PENDING}),
        "quality_status",
    )
    _require_choice(
        record.time_sequence_validity,
        frozenset({TIME_VALID, TIME_INVALID, TIME_UNKNOWN}),
        "time_sequence_validity",
    )
    _require_choice(
        record.operator_intervention,
        frozenset({INTERVENTION_NONE, INTERVENTION_PROTOCOL, INTERVENTION_UNPROTOCOL}),
        "operator_intervention",
    )
    if not isinstance(record.controller_order_recorded, bool):
        raise W19ValidityError("controller_order_recorded must be a boolean")
    if not isinstance(record.safety_stop_recorded, bool):
        raise W19ValidityError("safety_stop_recorded must be a boolean")

    metric_admissibility = _metric_admissibility(record.completeness)
    invalid_reasons: set[str] = set()
    pending_reasons: set[str] = set()

    if not _require_identity(record.hardware_config_id):
        invalid_reasons.add(REASON_HARDWARE_IDENTITY_MISSING)
    if not _require_identity(record.calibration_id):
        invalid_reasons.add(REASON_CALIBRATION_MISSING)
    if not _require_identity(record.firmware_version):
        invalid_reasons.add(REASON_FIRMWARE_MISSING)
    if not _require_identity(record.protocol_version):
        invalid_reasons.add(REASON_PROTOCOL_VERSION_MISSING)

    if record.disturbance_execution == DISTURBANCE_NOT_EXECUTED:
        invalid_reasons.add(REASON_DISTURBANCE_NOT_EXECUTED)
    elif record.disturbance_execution == DISTURBANCE_EXECUTED_OUT_OF_TOLERANCE:
        invalid_reasons.add(REASON_DISTURBANCE_TOLERANCE)
    elif record.disturbance_execution == DISTURBANCE_UNKNOWN:
        pending_reasons.add(REASON_DISTURBANCE_UNKNOWN)

    if record.reset_criterion == RESET_NOT_MET:
        invalid_reasons.add(REASON_RESET_NOT_MET)
    elif record.reset_criterion == RESET_EVIDENCE_MISSING:
        invalid_reasons.add(REASON_RESET_EVIDENCE_MISSING)

    if record.quality_status == QUALITY_FAIL:
        invalid_reasons.add(REASON_PHYSICAL_QUALITY_INVALID)
    elif record.quality_status == QUALITY_PENDING:
        pending_reasons.add(REASON_PHYSICAL_QUALITY_UNVERIFIED)

    if record.time_sequence_validity == TIME_INVALID:
        invalid_reasons.add(REASON_TEMPORAL_INVALID)
    elif record.time_sequence_validity == TIME_UNKNOWN:
        pending_reasons.add(REASON_TEMPORAL_UNKNOWN)

    if not record.controller_order_recorded:
        invalid_reasons.add(REASON_CONTROLLER_ORDER_MISSING)
    if record.safety_stop_recorded:
        invalid_reasons.add(REASON_SAFETY_STOP)
    if record.operator_intervention == INTERVENTION_UNPROTOCOL:
        invalid_reasons.add(REASON_UNPROTOCOL_INTERVENTION)

    for metric in metric_admissibility:
        if metric.role != ROLE_PRIMARY:
            continue
        if metric.coverage in {COVERAGE_MISSING, COVERAGE_INCOMPLETE}:
            invalid_reasons.add(REASON_PRIMARY_INCOMPLETE)
        elif metric.coverage == COVERAGE_UNKNOWN:
            pending_reasons.add(REASON_PRIMARY_COMPLETENESS_UNKNOWN)

    if invalid_reasons:
        validity_status = VALIDITY_INVALID
        reason_codes = tuple(sorted(invalid_reasons | pending_reasons))
    elif pending_reasons:
        validity_status = VALIDITY_PENDING
        reason_codes = tuple(sorted(pending_reasons))
    else:
        validity_status = VALIDITY_VALID
        reason_codes = ()

    primary_ok = all(
        metric.admissibility == ADMISSIBLE
        for metric in metric_admissibility
        if metric.role == ROLE_PRIMARY
    )
    return AttemptValidityDecision(
        attempt_id=record.attempt_id,
        pair_id=record.pair_id,
        run_id=record.run_id,
        controller_arm=record.controller_arm,
        validity_status=validity_status,
        reason_codes=reason_codes,
        quality_status=record.quality_status,
        metric_admissibility=metric_admissibility,
        primary_pair_eligible=validity_status == VALIDITY_VALID and primary_ok,
        decision_method=VALIDITY_METHOD_VERSION,
        outcome_fields_used=False,
        approval_effect="NONE_VALIDITY_SOFTWARE_ASSESSMENT_ONLY",
    )
