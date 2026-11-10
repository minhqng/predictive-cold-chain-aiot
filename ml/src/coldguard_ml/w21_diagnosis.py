"""W21 diagnosis classification with explicit evidence levels (B-W21-01).

Canonical anchors: Doc 03 section 103 (DIAG-01..04), Doc 03 sections 104-105,
Doc 01 sections 1.1-1.17, 19, 26, Doc 02 section 36, Doc 05D W03/D-W11.

The classifier never turns a command, an ACK, a current reading or a weak
thermal response into a stronger claim than the evidence supports.  A source
with the actuator output stage disabled cannot produce a healthy or missing
actuator-response diagnosis, and a single boot cannot become multiple
independent experiments.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

DIAG_01 = "DIAG-01"
DIAG_02 = "DIAG-02"
DIAG_03 = "DIAG-03"
DIAG_04 = "DIAG-04"

DIAG_CASES = (DIAG_01, DIAG_02, DIAG_03, DIAG_04)

CLASS_HEALTHY_RESPONSE = "HEALTHY_RESPONSE"
CLASS_ELECTRICAL_RESPONSE_MISSING = "ELECTRICAL_RESPONSE_MISSING"
CLASS_UNEXPECTED_OFF_CURRENT = "UNEXPECTED_OFF_CURRENT"
CLASS_DEGRADED_THERMAL_EFFECTIVENESS = "DEGRADED_THERMAL_EFFECTIVENESS"
CLASS_DEGRADED_OR_UNKNOWN = "DEGRADED_OR_UNKNOWN"
CLASS_OFF_STATE = "OFF_STATE_NOT_A_DIAGNOSIS"
CLASS_NOT_ESTIMABLE = "NOT_ESTIMABLE"

DIAGNOSIS_CLASSES = (
    CLASS_HEALTHY_RESPONSE,
    CLASS_ELECTRICAL_RESPONSE_MISSING,
    CLASS_UNEXPECTED_OFF_CURRENT,
    CLASS_DEGRADED_THERMAL_EFFECTIVENESS,
    CLASS_DEGRADED_OR_UNKNOWN,
    CLASS_OFF_STATE,
    CLASS_NOT_ESTIMABLE,
)

LEVEL_RECORDED_CONDITION = "RECORDED_CONDITION_OR_CONTROLLED_INJECTION"
LEVEL_TRUSTED_CHANNEL_OBSERVATION = "TRUSTED_CHANNEL_OBSERVATION"
LEVEL_SOFTWARE_DIAGNOSTIC_CLASSIFICATION = "SOFTWARE_DIAGNOSTIC_CLASSIFICATION"
LEVEL_ELECTRICAL_RESPONSE_VERIFICATION = "ELECTRICAL_RESPONSE_VERIFICATION"
LEVEL_THERMAL_RESPONSE_VERIFICATION = "THERMAL_RESPONSE_VERIFICATION"
LEVEL_ROOT_CAUSE_IDENTIFICATION = "ROOT_CAUSE_IDENTIFICATION"

EVIDENCE_LEVELS = (
    LEVEL_RECORDED_CONDITION,
    LEVEL_TRUSTED_CHANNEL_OBSERVATION,
    LEVEL_SOFTWARE_DIAGNOSTIC_CLASSIFICATION,
    LEVEL_ELECTRICAL_RESPONSE_VERIFICATION,
    LEVEL_THERMAL_RESPONSE_VERIFICATION,
    LEVEL_ROOT_CAUSE_IDENTIFICATION,
)

COMMAND_ON = "ON"
COMMAND_OFF = "OFF"
COMMAND_UNKNOWN = "UNKNOWN"

OUTPUT_STAGE_ENABLED = "ENABLED"
OUTPUT_STAGE_DISABLED = "DISABLED"
OUTPUT_STAGE_UNKNOWN = "UNKNOWN"

QUALITY_VALID = "VALID"
QUALITY_DEGRADED = "DEGRADED"
QUALITY_INVALID = "INVALID"
QUALITY_UNKNOWN = "UNKNOWN"

QUALITIES = (QUALITY_VALID, QUALITY_DEGRADED, QUALITY_INVALID, QUALITY_UNKNOWN)

THERMAL_PRESENT = "PRESENT"
THERMAL_ABSENT = "ABSENT"
THERMAL_UNKNOWN = "UNKNOWN"

CURRENT_MEASURED_ZERO = "MEASURED_ZERO"
CURRENT_MEASURED_NONZERO = "MEASURED_NONZERO"
CURRENT_MISSING = "MISSING"
CURRENT_UNKNOWN = "UNKNOWN"

CURRENT_MEASUREMENTS = (
    CURRENT_MEASURED_ZERO,
    CURRENT_MEASURED_NONZERO,
    CURRENT_MISSING,
    CURRENT_UNKNOWN,
)

GROUND_TRUTH_CONTROLLED_INJECTION = "CONTROLLED_INJECTION"
GROUND_TRUTH_RECORDED_CONDITION = "RECORDED_CONDITION"
GROUND_TRUTH_NONE = "NONE"

GROUND_TRUTH_SOURCES = (
    GROUND_TRUTH_CONTROLLED_INJECTION,
    GROUND_TRUTH_RECORDED_CONDITION,
    GROUND_TRUTH_NONE,
)

CONCORDANCE_CONCORDANT = "CONCORDANT_BOUNDED"
CONCORDANCE_DISCORDANT = "DISCORDANT"
CONCORDANCE_NOT_ESTIMABLE = "NOT_ESTIMABLE"

METRIC_NOT_ESTIMABLE = "NOT_ESTIMABLE"
METRIC_NOT_RUN = "NOT_RUN"
METRIC_NOT_VERIFIED = "NOT_VERIFIED"
METRIC_FAILED = "FAILED"

POPULATION_METRICS = (
    "diagnostic_accuracy",
    "fault_recall",
    "precision",
    "false_positive_rate",
)

REFUSAL_OUTPUT_STAGE_DISABLED = "OUTPUT_STAGE_DISABLED_NO_ACTUATOR_RESPONSE"
REFUSAL_ACK_NOT_EVIDENCE = "ACK_IS_NOT_ACTUATION_EVIDENCE"
REFUSAL_COMMAND_NOT_CURRENT = "COMMAND_ON_IS_NOT_MEASURED_CURRENT"
REFUSAL_ELECTRICAL_UNAVAILABLE = "ELECTRICAL_CHANNEL_UNAVAILABLE_NOT_VERIFIED_ZERO"
REFUSAL_MISSING_PZEM_NOT_ZERO = "MISSING_PZEM_IS_NOT_VERIFIED_ZERO_CURRENT"
REFUSAL_THERMAL_UNOBSERVED = "THERMAL_RESPONSE_NOT_OBSERVED"
REFUSAL_WEAK_THERMAL_NOT_ROOT_CAUSE = (
    "WEAK_THERMAL_RESPONSE_IS_NOT_COMPONENT_ROOT_CAUSE"
)
REFUSAL_CURRENT_NOT_THERMAL = "ELECTRICAL_CURRENT_IS_NOT_THERMAL_COOLING"
REFUSAL_ROOT_CAUSE = "SINGLE_OBSERVATION_CANNOT_IDENTIFY_ROOT_CAUSE"
REFUSAL_NO_GROUND_TRUTH = "NO_AUTHORITATIVE_GROUND_TRUTH"
REFUSAL_POPULATION_UNSUPPORTED = "INSUFFICIENT_INDEPENDENT_LABELED_SUPPORT"
REFUSAL_ACTUATOR_UNKNOWN = "ACTUATOR_ENABLEMENT_NOT_VERIFIED"
REFUSAL_COMMAND_UNKNOWN = "COMMAND_STATE_UNKNOWN"
REFUSAL_CURRENT_UNKNOWN = "CURRENT_OBSERVATION_MISSING"
REFUSAL_OVERALL_NOT_VALID = (
    "OVERALL_QUALITY_NOT_VALID_FOR_ACTUATOR_RESPONSE_CLASSIFICATION"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class W21DiagnosisError(ValueError):
    """Raised for a malformed diagnosis case or an unauthorized metric."""


@dataclass(frozen=True)
class DiagnosisCase:
    case_id: str
    condition: str
    ground_truth_source: str
    injection_ref: str | None
    command_state: str
    ack_observed: bool
    output_stage: str
    electrical_quality: str
    current_measurement: str
    current_value_a: float | None
    thermal_quality: str
    thermal_response: str
    overall_quality: str
    observed_invalid_channels: tuple[str, ...]
    recovery_observed: bool | None
    frames: int
    source_sha256: str
    device_id: str
    boot_id: str
    session_id: str
    expected_classification: str | None
    unsupported_conclusions: tuple[str, ...] = ()
    notes: str = ""

    def validate(self) -> None:
        if not self.case_id:
            raise W21DiagnosisError("case_id must be non-empty")
        if self.command_state not in {COMMAND_ON, COMMAND_OFF, COMMAND_UNKNOWN}:
            raise W21DiagnosisError(f"{self.case_id}: bad command_state")
        if self.current_measurement not in CURRENT_MEASUREMENTS:
            raise W21DiagnosisError(f"{self.case_id}: bad current_measurement")
        if self.current_measurement in {
            CURRENT_MEASURED_ZERO,
            CURRENT_MEASURED_NONZERO,
        } and self.current_value_a is None:
            raise W21DiagnosisError(
                f"{self.case_id}: a measured current requires a value"
            )
        if self.current_value_a is not None:
            if not isinstance(self.current_value_a, (int, float)) or not math.isfinite(
                self.current_value_a
            ):
                raise W21DiagnosisError(
                    f"{self.case_id}: current_value_a must be finite"
                )
            if (
                self.current_measurement == CURRENT_MEASURED_ZERO
                and self.current_value_a != 0
            ):
                raise W21DiagnosisError(
                    f"{self.case_id}: measured zero must be 0 A"
                )
            if (
                self.current_measurement == CURRENT_MEASURED_NONZERO
                and self.current_value_a == 0
            ):
                raise W21DiagnosisError(
                    f"{self.case_id}: measured nonzero must not be 0 A"
                )
        if self.output_stage not in {
            OUTPUT_STAGE_ENABLED,
            OUTPUT_STAGE_DISABLED,
            OUTPUT_STAGE_UNKNOWN,
        }:
            raise W21DiagnosisError(f"{self.case_id}: bad output_stage")
        for name, value in (
            ("electrical_quality", self.electrical_quality),
            ("thermal_quality", self.thermal_quality),
            ("overall_quality", self.overall_quality),
        ):
            if value not in QUALITIES:
                raise W21DiagnosisError(f"{self.case_id}: bad {name}")
        if self.thermal_response not in {
            THERMAL_PRESENT,
            THERMAL_ABSENT,
            THERMAL_UNKNOWN,
        }:
            raise W21DiagnosisError(f"{self.case_id}: bad thermal_response")
        if self.ground_truth_source not in GROUND_TRUTH_SOURCES:
            raise W21DiagnosisError(f"{self.case_id}: bad ground_truth_source")
        if self.expected_classification is not None and (
            self.expected_classification not in DIAGNOSIS_CLASSES
        ):
            raise W21DiagnosisError(f"{self.case_id}: bad expected class")
        if not _SHA256_RE.match(self.source_sha256):
            raise W21DiagnosisError(f"{self.case_id}: malformed source sha256")
        if self.frames < 0:
            raise W21DiagnosisError(f"{self.case_id}: frames must be non-negative")
        if not self.device_id or not self.boot_id or not self.session_id:
            raise W21DiagnosisError(f"{self.case_id}: identity is incomplete")

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "condition": self.condition,
            "ground_truth_source": self.ground_truth_source,
            "injection_ref": self.injection_ref,
            "command_state": self.command_state,
            "ack_observed": self.ack_observed,
            "output_stage": self.output_stage,
            "electrical_quality": self.electrical_quality,
            "current_measurement": self.current_measurement,
            "current_value_a": self.current_value_a,
            "thermal_quality": self.thermal_quality,
            "thermal_response": self.thermal_response,
            "overall_quality": self.overall_quality,
            "observed_invalid_channels": list(self.observed_invalid_channels),
            "recovery_observed": self.recovery_observed,
            "frames": self.frames,
            "source_sha256": self.source_sha256,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "session_id": self.session_id,
            "expected_classification": self.expected_classification,
            "unsupported_conclusions": list(self.unsupported_conclusions),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class DiagnosisAssessment:
    case_id: str
    classification: str
    evidence_levels: tuple[str, ...]
    refusals: tuple[str, ...]
    unsupported_conclusions: tuple[str, ...]
    concordance: str
    expected_classification: str | None
    independent_session_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "classification": self.classification,
            "evidence_levels": list(self.evidence_levels),
            "refusals": list(self.refusals),
            "unsupported_conclusions": list(self.unsupported_conclusions),
            "concordance": self.concordance,
            "expected_classification": self.expected_classification,
            "independent_session_count": self.independent_session_count,
        }


@dataclass(frozen=True)
class DiagnosisTable:
    cases: tuple[DiagnosisAssessment, ...]
    record_count: int
    independent_session_count: int
    metrics: Mapping[str, str]
    metric_reasons: Mapping[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": [case.to_dict() for case in self.cases],
            "record_count": self.record_count,
            "independent_session_count": self.independent_session_count,
            "metrics": dict(self.metrics),
            "metric_reasons": dict(self.metric_reasons),
        }


def _channel_observed(case: DiagnosisCase) -> bool:
    return (
        bool(case.observed_invalid_channels)
        or case.current_measurement != CURRENT_UNKNOWN
        or case.thermal_response != THERMAL_UNKNOWN
        or QUALITY_VALID
        in (case.electrical_quality, case.thermal_quality, case.overall_quality)
        or QUALITY_DEGRADED
        in (case.electrical_quality, case.thermal_quality, case.overall_quality)
        or QUALITY_INVALID
        in (case.electrical_quality, case.thermal_quality, case.overall_quality)
    )


def _electrical_verification_supported(case: DiagnosisCase) -> bool:
    return (
        case.output_stage == OUTPUT_STAGE_ENABLED
        and case.command_state == COMMAND_ON
        and case.electrical_quality == QUALITY_VALID
        and case.current_measurement
        in {CURRENT_MEASURED_ZERO, CURRENT_MEASURED_NONZERO}
    )


def _thermal_verification_supported(case: DiagnosisCase) -> bool:
    return (
        _electrical_verification_supported(case)
        and case.thermal_quality == QUALITY_VALID
        and case.thermal_response != THERMAL_UNKNOWN
    )


def classify_case(case: DiagnosisCase) -> DiagnosisAssessment:
    case.validate()
    levels: list[str] = [LEVEL_SOFTWARE_DIAGNOSTIC_CLASSIFICATION]
    refusals: list[str] = [REFUSAL_ROOT_CAUSE]
    unsupported: list[str] = list(case.unsupported_conclusions)

    if case.ground_truth_source != GROUND_TRUTH_NONE:
        levels.insert(0, LEVEL_RECORDED_CONDITION)
    if _channel_observed(case):
        levels.insert(
            1 if case.ground_truth_source != GROUND_TRUTH_NONE else 0,
            LEVEL_TRUSTED_CHANNEL_OBSERVATION,
        )
    if _electrical_verification_supported(case):
        levels.append(LEVEL_ELECTRICAL_RESPONSE_VERIFICATION)
    else:
        if case.ack_observed:
            refusals.append(REFUSAL_ACK_NOT_EVIDENCE)
        if case.command_state == COMMAND_ON:
            refusals.append(REFUSAL_COMMAND_NOT_CURRENT)
    if _thermal_verification_supported(case):
        levels.append(LEVEL_THERMAL_RESPONSE_VERIFICATION)
    elif _electrical_verification_supported(case):
        refusals.append(REFUSAL_THERMAL_UNOBSERVED)

    if case.output_stage != OUTPUT_STAGE_ENABLED:
        if case.output_stage == OUTPUT_STAGE_DISABLED:
            refusals.append(REFUSAL_OUTPUT_STAGE_DISABLED)
        else:
            refusals.append(REFUSAL_ACTUATOR_UNKNOWN)
        degraded = any(
            quality in {QUALITY_DEGRADED, QUALITY_INVALID}
            for quality in (
                case.electrical_quality,
                case.thermal_quality,
                case.overall_quality,
            )
        ) or bool(case.observed_invalid_channels)
        classification = (
            CLASS_DEGRADED_OR_UNKNOWN if degraded else CLASS_NOT_ESTIMABLE
        )
        if case.electrical_quality in {
            QUALITY_DEGRADED,
            QUALITY_INVALID,
            QUALITY_UNKNOWN,
        } and case.command_state == COMMAND_ON:
            refusals.append(REFUSAL_ELECTRICAL_UNAVAILABLE)
        if case.current_measurement == CURRENT_MISSING or (
            case.electrical_quality in {QUALITY_DEGRADED, QUALITY_INVALID}
        ):
            refusals.append(REFUSAL_MISSING_PZEM_NOT_ZERO)
        if case.command_state == COMMAND_UNKNOWN:
            refusals.append(REFUSAL_COMMAND_UNKNOWN)
        return _assessment(case, classification, levels, refusals, unsupported)

    if case.command_state == COMMAND_UNKNOWN:
        refusals.append(REFUSAL_COMMAND_UNKNOWN)
        return _assessment(
            case, CLASS_NOT_ESTIMABLE, levels, refusals, unsupported
        )

    if case.command_state == COMMAND_ON:
        if case.electrical_quality != QUALITY_VALID:
            refusals.append(REFUSAL_ELECTRICAL_UNAVAILABLE)
            return _assessment(
                case,
                CLASS_DEGRADED_OR_UNKNOWN,
                levels,
                refusals,
                unsupported,
            )
        if case.current_measurement == CURRENT_MISSING:
            refusals.append(REFUSAL_ELECTRICAL_UNAVAILABLE)
            return _assessment(
                case,
                CLASS_DEGRADED_OR_UNKNOWN,
                levels,
                refusals,
                unsupported,
            )
        if case.current_measurement == CURRENT_UNKNOWN:
            refusals.append(REFUSAL_CURRENT_UNKNOWN)
            return _assessment(
                case, CLASS_NOT_ESTIMABLE, levels, refusals, unsupported
            )
        if case.overall_quality != QUALITY_VALID or case.observed_invalid_channels:
            refusals.append(REFUSAL_OVERALL_NOT_VALID)
            return _assessment(
                case,
                CLASS_DEGRADED_OR_UNKNOWN,
                levels,
                refusals,
                unsupported,
            )
        if case.current_measurement == CURRENT_MEASURED_ZERO:
            return _assessment(
                case,
                CLASS_ELECTRICAL_RESPONSE_MISSING,
                levels,
                refusals,
                unsupported,
            )
        # Current is present.  It never proves useful cooling by itself.
        refusals.append(REFUSAL_CURRENT_NOT_THERMAL)
        if case.thermal_quality != QUALITY_VALID or case.thermal_response == (
            THERMAL_UNKNOWN
        ):
            refusals.append(REFUSAL_THERMAL_UNOBSERVED)
            return _assessment(
                case, CLASS_NOT_ESTIMABLE, levels, refusals, unsupported
            )
        if case.thermal_response == THERMAL_PRESENT:
            return _assessment(
                case, CLASS_HEALTHY_RESPONSE, levels, refusals, unsupported
            )
        refusals.append(REFUSAL_WEAK_THERMAL_NOT_ROOT_CAUSE)
        unsupported.append("COMPONENT_LEVEL_ROOT_CAUSE")
        return _assessment(
            case,
            CLASS_DEGRADED_THERMAL_EFFECTIVENESS,
            levels,
            refusals,
            unsupported,
        )

    # Command is OFF.
    if case.electrical_quality != QUALITY_VALID or case.current_measurement in {
        CURRENT_MISSING,
        CURRENT_UNKNOWN,
    }:
        refusals.append(REFUSAL_MISSING_PZEM_NOT_ZERO)
        return _assessment(
            case, CLASS_DEGRADED_OR_UNKNOWN, levels, refusals, unsupported
        )
    if case.current_measurement == CURRENT_MEASURED_NONZERO:
        return _assessment(
            case, CLASS_UNEXPECTED_OFF_CURRENT, levels, refusals, unsupported
        )
    return _assessment(case, CLASS_OFF_STATE, levels, refusals, unsupported)


def _assessment(
    case: DiagnosisCase,
    classification: str,
    levels: Sequence[str],
    refusals: Sequence[str],
    unsupported: Sequence[str],
) -> DiagnosisAssessment:
    concordance = _concordance(case, classification)
    if concordance == CONCORDANCE_NOT_ESTIMABLE:
        refusals = (*refusals, REFUSAL_NO_GROUND_TRUTH)
    return DiagnosisAssessment(
        case_id=case.case_id,
        classification=classification,
        evidence_levels=tuple(dict.fromkeys(levels)),
        refusals=tuple(dict.fromkeys(refusals)),
        unsupported_conclusions=tuple(dict.fromkeys(unsupported)),
        concordance=concordance,
        expected_classification=case.expected_classification,
        independent_session_count=1,
    )


def _concordance(case: DiagnosisCase, classification: str) -> str:
    if classification in {CLASS_NOT_ESTIMABLE, CLASS_OFF_STATE}:
        return CONCORDANCE_NOT_ESTIMABLE
    if case.ground_truth_source not in {
        GROUND_TRUTH_CONTROLLED_INJECTION,
        GROUND_TRUTH_RECORDED_CONDITION,
    }:
        return CONCORDANCE_NOT_ESTIMABLE
    if case.expected_classification is None:
        return CONCORDANCE_NOT_ESTIMABLE
    if case.expected_classification == classification:
        return CONCORDANCE_CONCORDANT
    return CONCORDANCE_DISCORDANT


def assess_diagnosis_table(cases: Sequence[DiagnosisCase]) -> DiagnosisTable:
    if not cases:
        raise W21DiagnosisError("diagnosis table requires at least one case")
    identifiers = [case.case_id for case in cases]
    if len(set(identifiers)) != len(identifiers):
        raise W21DiagnosisError("diagnosis case IDs must be distinct")
    assessments = [classify_case(case) for case in cases]
    sessions = {(case.device_id, case.boot_id) for case in cases}
    independent = len(sessions)
    metrics = {name: METRIC_NOT_ESTIMABLE for name in POPULATION_METRICS}
    reasons = {
        name: REFUSAL_POPULATION_UNSUPPORTED for name in POPULATION_METRICS
    }
    return DiagnosisTable(
        cases=tuple(assessments),
        record_count=sum(case.frames for case in cases),
        independent_session_count=independent,
        metrics=metrics,
        metric_reasons=reasons,
    )


def population_metrics(
    cases: Sequence[DiagnosisCase],
    *,
    admitted_independent_labeled_support: bool = False,
) -> dict[str, str]:
    if admitted_independent_labeled_support:
        raise W21DiagnosisError(
            "W21 does not compute population accuracy from bounded cases"
        )
    if not cases:
        raise W21DiagnosisError("population metrics require cases")
    return {name: METRIC_NOT_ESTIMABLE for name in POPULATION_METRICS}


def required_negative_cases() -> tuple[tuple[str, str], ...]:
    """The packet's mandatory diagnosis refusals, as executable declarations."""
    return (
        ("on_command_not_current", REFUSAL_COMMAND_NOT_CURRENT),
        ("ack_not_applied_power", REFUSAL_ACK_NOT_EVIDENCE),
        ("current_not_thermal", REFUSAL_CURRENT_NOT_THERMAL),
        ("off_without_pzem_not_zero", REFUSAL_MISSING_PZEM_NOT_ZERO),
        ("compiled_out_stage_not_failure", REFUSAL_OUTPUT_STAGE_DISABLED),
        ("software_injection_not_cable_disconnect", "EVIDENCE_CLASS_MISMATCH"),
        ("weak_cooling_not_component", REFUSAL_WEAK_THERMAL_NOT_ROOT_CAUSE),
        ("shared_boot_not_independent", "SHARED_BOOT_NOT_INDEPENDENT"),
    )


def case_fingerprint(case: DiagnosisCase) -> str:
    payload = canonical_payload(case.to_dict())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_payload(payload: Any) -> str:
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
