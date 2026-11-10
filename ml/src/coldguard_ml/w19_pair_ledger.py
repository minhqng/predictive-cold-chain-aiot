"""W19 paired-campaign ledger: schema, attempt accounting and pair state machine.

Canonical anchors: Doc 03 §§34-37, 95-98, 158-163; Doc 04 §§34-35; Doc 05B
§47 B-W19-01/02 and §48 W20 boundaries.

The ledger records the complete attempt history of a Controller A/B campaign,
not only accepted pairs.  One valid matched pair is the statistical unit; a
telemetry row, a feature window or a single arm is never an independent A/B
observation.  A pair becomes VALID only when both arms are protocol-valid,
matching evidence agrees with the frozen policy, the registered order was
followed and initial-state comparability holds inside approved tolerances.

A syntactically valid pair record is not automatically a valid physical
experimental pair.  Physical admission additionally requires a valid campaign
authorization and a fully approved campaign freeze, and synthetic fixtures are
never admitted.  This module cannot execute a campaign, create an order,
collect data or compute an outcome.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from coldguard_ml.w19_no_peeking import (
    FREEZE_FROZEN_APPROVED,
    assert_outcome_blind,
    assess_statistical_freeze,
)
from coldguard_ml.w19_validity import (
    PREDECLARED_VALIDITY_REASON_CODES,
    QUALITY_FAIL,
    QUALITY_PASS,
    QUALITY_PENDING,
    VALIDITY_INVALID,
    VALIDITY_NOT_APPLICABLE,
    VALIDITY_PENDING,
    VALIDITY_VALID,
    REASON_ATTEMPT_ABORTED,
)

PAIR_LEDGER_SCHEMA = "coldguard-w19-pair-ledger-v1"
PAIR_LEDGER_LAYER_VERSION = "coldguard-w19-paired-campaign-integrity-v1"

EVIDENCE_PHYSICAL_CAMPAIGN = "PHYSICAL_CAMPAIGN_RECORD"
EVIDENCE_SYNTHETIC_FIXTURE = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
EVIDENCE_CLASSES = frozenset({EVIDENCE_PHYSICAL_CAMPAIGN, EVIDENCE_SYNTHETIC_FIXTURE})
FIXTURE_MARKERS = ("TEST_ONLY", "SYNTHETIC_SOFTWARE_CONTROL_ONLY")

PAIR_PLANNED = "PLANNED"
PAIR_AWAITING_SECOND_ARM = "AWAITING_SECOND_ARM"
PAIR_AWAITING_VALIDITY = "AWAITING_VALIDITY"
PAIR_VALID = "PAIR_VALID"
PAIR_INVALID = "PAIR_INVALID"
PAIR_BLOCKED_MISSING_FREEZE = "PAIR_BLOCKED_MISSING_FREEZE"
PAIR_UNRESOLVED = "PAIR_UNRESOLVED"

PAIR_STATUSES = (
    PAIR_PLANNED,
    PAIR_AWAITING_SECOND_ARM,
    PAIR_AWAITING_VALIDITY,
    PAIR_VALID,
    PAIR_INVALID,
    PAIR_BLOCKED_MISSING_FREEZE,
    PAIR_UNRESOLVED,
)

ATTEMPT_KIND_INITIAL = "INITIAL"
ATTEMPT_KIND_RERUN = "RERUN"
ATTEMPT_STATUS_RECORDED = "RECORDED"
ATTEMPT_STATUS_ABORTED = "ABORTED"

FAILURE_RERUN_INVALID_ARM = "RERUN_INVALID_ARM_PRESERVE_BLOCK"
FAILURE_INVALIDATE_PAIR = "INVALIDATE_PAIR"
FAILURE_HANDLINGS = frozenset({FAILURE_RERUN_INVALID_ARM, FAILURE_INVALIDATE_PAIR})

AUTHORIZATION_AUTHORIZED = "AUTHORIZED"
AUTHORIZATION_NOT_AUTHORIZED = "NOT_AUTHORIZED"
AUTHORIZATION_FAKE_APPROVAL = "FAKE_APPROVAL_DETECTED"

FREEZE_DECLARED_NOT_VERIFIED = "DECLARED_NOT_VERIFIED"
FREEZE_MISSING_EVIDENCE = "MISSING_EVIDENCE"
FREEZE_FIELD_STATUSES = frozenset(
    {FREEZE_FROZEN_APPROVED, FREEZE_DECLARED_NOT_VERIFIED, FREEZE_MISSING_EVIDENCE}
)
FREEZE_STATUS_APPROVED = "FINAL_AB_CAMPAIGN_FREEZE_APPROVED"
FREEZE_STATUS_INCOMPLETE = "FREEZE_INCOMPLETE"
FREEZE_STATUS_MISSING = "MISSING_FREEZE_RECORD"
DEVELOPMENT_BASELINE_DOES_NOT_IMPLY_FREEZE = (
    "DEVELOPMENT_BASELINE_UNCHANGED_NEVER_IMPLIES_FINAL_AB_CAMPAIGN_FREEZE_APPROVED"
)

CAMPAIGN_FREEZE_FIELD_IDS: tuple[str, ...] = (
    "hardware_config_id",
    "calibration_id",
    "firmware_version",
    "sensor_placement",
    "model_artifact_sha256",
    "feature_schema_hash",
    "critical_target",
    "representative_temperature",
    "primary_horizon",
    "operating_threshold",
    "warning_persistence",
    "controller_policy_version",
    "cooling_action_magnitude",
    "disturbance_protocol",
    "initial_reset_criterion",
    "pair_matching_tolerances",
    "randomization_protocol",
    "validity_exclusion_rules",
    "primary_outcome",
    "statistical_method",
    "target_pair_count",
)

REASON_DUPLICATE_RUN_ID = "DUPLICATE_RUN_ID_ACROSS_RECORDS"
REASON_DUPLICATE_SOURCE_SHA = "DUPLICATE_SOURCE_SHA256_ACROSS_RECORDS"
REASON_DUPLICATE_SOURCE_PATH = "DUPLICATE_SOURCE_PATH_ACROSS_RECORDS"
REASON_AMBIGUOUS_ARM_HISTORY = "AMBIGUOUS_ARM_HISTORY"
REASON_SCENARIO_MISMATCH = "SCENARIO_MISMATCH"
REASON_SCOPE_MISMATCH = "CAMPAIGN_BLOCK_SESSION_MISMATCH"
REASON_HARDWARE_MISMATCH = "HARDWARE_CONFIG_MISMATCH"
REASON_CALIBRATION_MISMATCH = "CALIBRATION_LINEAGE_MISMATCH"
REASON_FIRMWARE_MISMATCH = "FIRMWARE_VERSION_MISMATCH"
REASON_PROTOCOL_VERSION_MISMATCH = "PROTOCOL_VERSION_MISMATCH"
REASON_DISTURBANCE_PROTOCOL_MISMATCH = "DISTURBANCE_PROTOCOL_MISMATCH"
REASON_FEATURE_MISMATCH = "FEATURE_VERSION_MISMATCH"
REASON_MODEL_ARTIFACT_MISMATCH = "MODEL_ARTIFACT_MISMATCH"
REASON_CONTROLLER_ORDER_MISSING = "CONTROLLER_ORDER_IDENTITY_INVALID"
REASON_ORDER_DEVIATION = "CONTROLLER_ORDER_DEVIATION"
REASON_ORDER_RANDOMIZATION = "CONTROLLER_ORDER_RANDOMIZATION_VIOLATION"
REASON_RANDOMIZATION_NOT_REGISTERED = "RANDOMIZATION_NOT_REGISTERED"
REASON_RANDOMIZATION_ENTRY_MISSING = "RANDOMIZATION_ENTRY_MISSING_FOR_PAIR"
REASON_MATCHING_UNFROZEN = "PAIR_MATCHING_TOLERANCES_UNFROZEN"
REASON_FAILURE_POLICY_UNFROZEN = "INVALID_ARM_HANDLING_UNFROZEN"
REASON_RERUN_NOT_COMPLETED = "PERMISSIBLE_RERUN_NOT_COMPLETED"
REASON_POLICY_INVALIDATES_PAIR = "FROZEN_POLICY_INVALIDATES_PAIR"
REASON_INITIAL_TMEAN = "INITIAL_TMEAN_DELTA_EXCEEDED"
REASON_INITIAL_GRADIENT = "INITIAL_GRADIENT_DELTA_EXCEEDED"
REASON_INITIAL_MISSING = "INITIAL_STATE_EVIDENCE_MISSING"
REASON_DOOR_NOT_CLOSED = "DOOR_NOT_CLOSED_AT_START"
REASON_COOLING_UNKNOWN = "COOLING_STATE_UNKNOWN"
REASON_VALIDITY_PENDING = "ARM_VALIDITY_PENDING"
REASON_CAMPAIGN_IDENTITY_DRIFT = "CAMPAIGN_IDENTITY_DRIFT"
REASON_FIXTURE_IN_PHYSICAL = "FIXTURE_MARKER_IN_PHYSICAL_LEDGER"
REASON_RERUN_OF_NON_INVALID_ARM = "RERUN_OF_NON_INVALID_ARM_REFUSED"
REASON_TARGET_COUNT_CONFLICT = "PAIR_TARGET_COUNT_SOURCE_CONFLICT"

SENTINEL_NOT_APPLICABLE = "NOT_APPLICABLE_CONTROLLER_A"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

LEDGER_KEYS = frozenset(
    {
        "schema",
        "campaign_id",
        "evidence_class",
        "analysis_plan_version",
        "campaign_authorization",
        "campaign_freeze",
        "matching_policy",
        "failure_policy",
        "randomization",
        "frozen_target",
        "statistical_freeze",
        "pairs",
        "attempts",
    }
)
LEDGER_REQUIRED_KEYS = frozenset(
    {"schema", "campaign_id", "evidence_class", "analysis_plan_version", "pairs", "attempts"}
)

PAIR_KEYS = frozenset(
    {
        "pair_id",
        "campaign_id",
        "scenario_id",
        "block_id",
        "session_id",
        "planned_controller_order",
        "actual_controller_order",
        "attempt_ids",
        "initial_state",
    }
)
INITIAL_STATE_KEYS = frozenset({"criterion_version", "arms"})
INITIAL_ARM_KEYS = frozenset(
    {
        "initial_tmean_c",
        "initial_gradient_c",
        "ambient_temp_c",
        "ambient_rh_pct",
        "door_state",
        "cooling_state",
    }
)

ATTEMPT_KEYS = frozenset(
    {
        "attempt_id",
        "pair_id",
        "campaign_id",
        "scenario_id",
        "block_id",
        "session_id",
        "run_id",
        "controller_arm",
        "attempt_kind",
        "attempt_status",
        "supersedes",
        "superseded_by",
        "corrections",
        "hardware_config_id",
        "calibration_id",
        "firmware_version",
        "model_artifact_id",
        "model_artifact_sha256",
        "feature_version",
        "policy_version",
        "protocol_version",
        "disturbance_protocol_id",
        "source_path",
        "source_manifest_id",
        "source_sha256",
        "quality_status",
        "validity_status",
        "validity_reason_codes",
        "validity_method",
        "audit_events",
        "fixture_markers",
    }
)
CORRECTION_KEYS = frozenset(
    {
        "correction_id",
        "field",
        "previous_value",
        "corrected_value",
        "reason",
        "recorded_by",
    }
)
AUDIT_EVENT_KEYS = frozenset({"seq", "event", "actor", "detail"})

AUTHORIZATION_KEYS = frozenset(
    {
        "authorized",
        "authority_id",
        "authority_role",
        "canonical_ref",
        "g4_status",
        "pair_target_frozen",
        "analysis_freeze_accepted",
    }
)

DRIFT_ATTEMPT_FIELDS = (
    ("hardware_config_id", "hardware_config_id"),
    ("calibration_id", "calibration_id"),
    ("firmware_version", "firmware_version"),
    ("disturbance_protocol_id", "disturbance_protocol"),
)


class W19LedgerError(ValueError):
    """Raised for structurally malformed or internally inconsistent ledgers."""


@dataclass(frozen=True)
class AuthorizationAssessment:
    status: str
    authorized: bool
    authority_id: str | None
    g4_status: str | None
    refusal_reasons: tuple[str, ...]
    approval_effect: str = "NONE_SOFTWARE_ASSESSMENT_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "authorized": self.authorized,
            "authority_id": self.authority_id,
            "g4_status": self.g4_status,
            "refusal_reasons": list(self.refusal_reasons),
            "approval_effect": self.approval_effect,
        }


@dataclass(frozen=True)
class FreezeFieldState:
    field_id: str
    value: Any
    provenance: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "value": self.value,
            "provenance": self.provenance,
            "status": self.status,
        }


@dataclass(frozen=True)
class CampaignFreezeAssessment:
    freeze_status: str
    fields: tuple[FreezeFieldState, ...]
    missing_field_ids: tuple[str, ...]
    unfrozen_field_ids: tuple[str, ...]
    approval_valid: bool
    physical_admission: str
    approval_effect: str = "NONE_SOFTWARE_ASSESSMENT_ONLY"

    @property
    def field_values(self) -> dict[str, Any]:
        return {state.field_id: state.value for state in self.fields}

    def to_dict(self) -> dict[str, Any]:
        return {
            "freeze_status": self.freeze_status,
            "fields": [state.to_dict() for state in self.fields],
            "missing_field_ids": list(self.missing_field_ids),
            "unfrozen_field_ids": list(self.unfrozen_field_ids),
            "approval_valid": self.approval_valid,
            "physical_admission": self.physical_admission,
            "approval_effect": self.approval_effect,
        }


@dataclass(frozen=True)
class FreezeDrift:
    comparison_status: str
    changed_fields: tuple[str, ...]
    comparability_decision: str
    semantics_note: str = DEVELOPMENT_BASELINE_DOES_NOT_IMPLY_FREEZE

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparison_status": self.comparison_status,
            "changed_fields": list(self.changed_fields),
            "comparability_decision": self.comparability_decision,
            "semantics_note": self.semantics_note,
        }


@dataclass(frozen=True)
class AttemptAccounting:
    total_attempts: int
    initial_attempts: int
    rerun_attempts: int
    recorded_attempts: int
    aborted_attempts: int
    valid_attempts: int
    invalid_attempts: int
    pending_attempts: int
    superseded_attempts: int
    selected_attempts: int
    synthetic_attempts: int
    physical_candidate_attempts: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_attempts": self.total_attempts,
            "initial_attempts": self.initial_attempts,
            "rerun_attempts": self.rerun_attempts,
            "recorded_attempts": self.recorded_attempts,
            "aborted_attempts": self.aborted_attempts,
            "valid_attempts": self.valid_attempts,
            "invalid_attempts": self.invalid_attempts,
            "pending_attempts": self.pending_attempts,
            "superseded_attempts": self.superseded_attempts,
            "selected_attempts": self.selected_attempts,
            "synthetic_attempts": self.synthetic_attempts,
            "physical_candidate_attempts": self.physical_candidate_attempts,
        }


@dataclass(frozen=True)
class PairAssessment:
    pair_id: str
    status: str
    reason_codes: tuple[str, ...]
    selected_attempts: Mapping[str, str | None]
    initial_state_comparison: Mapping[str, Any]
    campaign_identity_drift_fields: tuple[str, ...]
    fixture_attempt_ids: tuple[str, ...]
    physical_admissible: bool
    validity_method: str = PAIR_LEDGER_LAYER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "selected_attempts": dict(self.selected_attempts),
            "initial_state_comparison": dict(self.initial_state_comparison),
            "campaign_identity_drift_fields": list(
                self.campaign_identity_drift_fields
            ),
            "fixture_attempt_ids": list(self.fixture_attempt_ids),
            "physical_admissible": self.physical_admissible,
            "validity_method": self.validity_method,
        }


@dataclass(frozen=True)
class PairLedgerValidation:
    schema: str
    campaign_id: str
    evidence_class: str
    analysis_plan_version: str
    pair_status_counts: Mapping[str, int]
    pairs: tuple[PairAssessment, ...]
    attempt_accounting: AttemptAccounting
    authorization: Mapping[str, Any]
    campaign_freeze: Mapping[str, Any]
    statistical_freeze: Mapping[str, Any]
    refusal_reasons: tuple[str, ...]
    physical_valid_pairs: int
    software_valid_pairs: int
    physical_pair_evidence_accepted: bool
    ledger_integrity_ok: bool
    target_count_conflict: bool = False
    approval_effect: str = "NONE_LEDGER_SOFTWARE_VALIDATION_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "campaign_id": self.campaign_id,
            "evidence_class": self.evidence_class,
            "analysis_plan_version": self.analysis_plan_version,
            "pair_status_counts": dict(self.pair_status_counts),
            "pairs": [pair.to_dict() for pair in self.pairs],
            "attempt_accounting": self.attempt_accounting.to_dict(),
            "authorization": dict(self.authorization),
            "campaign_freeze": dict(self.campaign_freeze),
            "statistical_freeze": dict(self.statistical_freeze),
            "refusal_reasons": list(self.refusal_reasons),
            "physical_valid_pairs": self.physical_valid_pairs,
            "software_valid_pairs": self.software_valid_pairs,
            "physical_pair_evidence_accepted": self.physical_pair_evidence_accepted,
            "ledger_integrity_ok": self.ledger_integrity_ok,
            "target_count_conflict": self.target_count_conflict,
            "approval_effect": self.approval_effect,
        }


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise W19LedgerError(f"{context} must be an object")
    return value


def _check_keys(
    payload: Mapping[str, Any], allowed: frozenset[str], context: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise W19LedgerError(f"{context} contains unknown field(s): {', '.join(unknown)}")
    missing = sorted(allowed - set(payload))
    if missing:
        raise W19LedgerError(f"{context} lacks required field(s): {', '.join(missing)}")


def _require_non_empty_str(payload: Mapping[str, Any], field: str, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise W19LedgerError(f"{context}.{field} must be a non-empty string")
    return value


def _optional_non_empty_str(value: Any, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise W19LedgerError(f"{context} must be null or a non-empty string")
    return value


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _freeze_approval_ok(approval: Any) -> bool:
    if not isinstance(approval, Mapping):
        return False
    return bool(
        isinstance(approval.get("authority_id"), str)
        and approval.get("authority_id", "").strip()
        and isinstance(approval.get("canonical_ref"), str)
        and approval.get("canonical_ref", "").strip()
    )


def _is_ab_order(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and set(value) == {"A", "B"}
    )


def evaluate_campaign_authorization(
    record: Mapping[str, Any] | None,
) -> AuthorizationAssessment:
    """A campaign is authorized only with a complete, internally consistent record."""
    if record is None:
        return AuthorizationAssessment(
            status=AUTHORIZATION_NOT_AUTHORIZED,
            authorized=False,
            authority_id=None,
            g4_status=None,
            refusal_reasons=("AUTHORIZATION_RECORD_MISSING",),
        )
    if not isinstance(record, Mapping):
        raise W19LedgerError("campaign_authorization must be an object")
    unknown = sorted(set(record) - AUTHORIZATION_KEYS)
    if unknown:
        raise W19LedgerError(
            f"campaign_authorization contains unknown field(s): {', '.join(unknown)}"
        )
    if record.get("authorized") is not True:
        return AuthorizationAssessment(
            status=AUTHORIZATION_NOT_AUTHORIZED,
            authorized=False,
            authority_id=record.get("authority_id"),
            g4_status=record.get("g4_status"),
            refusal_reasons=(),
        )
    problems: list[str] = []
    authority_id = record.get("authority_id")
    if not isinstance(authority_id, str) or not authority_id.strip():
        problems.append("AUTHORITY_ID_MISSING")
    if record.get("authority_role") != "TEAM_LEAD":
        problems.append("AUTHORITY_ROLE_NOT_TEAM_LEAD")
    canonical_ref = record.get("canonical_ref")
    if not isinstance(canonical_ref, str) or not canonical_ref.strip():
        problems.append("AUTHORIZATION_REFERENCE_MISSING")
    if record.get("g4_status") != "READY":
        problems.append("G4_NOT_READY")
    if record.get("pair_target_frozen") is not True:
        problems.append("PAIR_TARGET_NOT_FROZEN")
    if record.get("analysis_freeze_accepted") is not True:
        problems.append("ANALYSIS_FREEZE_NOT_ACCEPTED")
    if problems:
        return AuthorizationAssessment(
            status=AUTHORIZATION_FAKE_APPROVAL,
            authorized=False,
            authority_id=authority_id if isinstance(authority_id, str) else None,
            g4_status=record.get("g4_status"),
            refusal_reasons=tuple(f"FAKE_APPROVAL:{problem}" for problem in problems),
        )
    return AuthorizationAssessment(
        status=AUTHORIZATION_AUTHORIZED,
        authorized=True,
        authority_id=authority_id,
        g4_status="READY",
        refusal_reasons=(),
    )


def _approval_shape_ok(approval: Any) -> bool:
    if not isinstance(approval, Mapping):
        return False
    return bool(
        isinstance(approval.get("authority_id"), str)
        and approval.get("authority_id", "").strip()
        and approval.get("authority_role") == "TEAM_LEAD"
        and isinstance(approval.get("canonical_ref"), str)
        and approval.get("canonical_ref", "").strip()
    )


def assess_campaign_freeze(
    record: Mapping[str, Any] | None,
) -> CampaignFreezeAssessment:
    """Shape-check the protected freeze fields; never invent an approval."""
    if record is None:
        return CampaignFreezeAssessment(
            freeze_status=FREEZE_STATUS_MISSING,
            fields=(),
            missing_field_ids=CAMPAIGN_FREEZE_FIELD_IDS,
            unfrozen_field_ids=CAMPAIGN_FREEZE_FIELD_IDS,
            approval_valid=False,
            physical_admission="BLOCKED_MISSING_FREEZE",
        )
    if not isinstance(record, Mapping):
        raise W19LedgerError("campaign_freeze must be an object")
    unknown = sorted(set(record) - {"fields", "approval"})
    if unknown:
        raise W19LedgerError(
            f"campaign_freeze contains unknown field(s): {', '.join(unknown)}"
        )
    fields_payload = record.get("fields")
    if not isinstance(fields_payload, Mapping):
        raise W19LedgerError("campaign_freeze.fields must be an object")
    unknown_fields = sorted(set(fields_payload) - set(CAMPAIGN_FREEZE_FIELD_IDS))
    if unknown_fields:
        raise W19LedgerError(
            "campaign_freeze.fields contains unknown field id(s): "
            + ", ".join(unknown_fields)
        )
    states: list[FreezeFieldState] = []
    for field_id in CAMPAIGN_FREEZE_FIELD_IDS:
        entry = fields_payload.get(field_id)
        if not isinstance(entry, Mapping):
            states.append(FreezeFieldState(field_id, None, "", FREEZE_MISSING_EVIDENCE))
            continue
        status = entry.get("status")
        if status not in FREEZE_FIELD_STATUSES:
            raise W19LedgerError(
                f"campaign_freeze.fields[{field_id!r}].status has unknown value {status!r}"
            )
        states.append(
            FreezeFieldState(
                field_id=field_id,
                value=entry.get("value"),
                provenance=str(entry.get("provenance") or ""),
                status=status,
            )
        )
    missing = tuple(
        state.field_id
        for state in states
        if state.status == FREEZE_MISSING_EVIDENCE or state.value in (None, "")
    )
    unfrozen = tuple(
        state.field_id
        for state in states
        if state.status != FREEZE_FROZEN_APPROVED or not state.provenance.strip()
    )
    approval_valid = _approval_shape_ok(record.get("approval"))
    approved = not missing and not unfrozen and approval_valid
    return CampaignFreezeAssessment(
        freeze_status=FREEZE_STATUS_APPROVED if approved else FREEZE_STATUS_INCOMPLETE,
        fields=tuple(states),
        missing_field_ids=missing,
        unfrozen_field_ids=unfrozen,
        approval_valid=approval_valid,
        physical_admission=(
            "ELIGIBLE_PENDING_AUTHORIZATION" if approved else "BLOCKED_FREEZE_INCOMPLETE"
        ),
    )


def _target_count_conflict(
    freeze: CampaignFreezeAssessment, frozen_target: Any
) -> bool:
    if freeze.freeze_status != FREEZE_STATUS_APPROVED:
        return False
    if not isinstance(frozen_target, Mapping):
        return False
    if frozen_target.get("status") != FREEZE_FROZEN_APPROVED:
        return False
    planned = frozen_target.get("planned_pair_target")
    if not isinstance(planned, int) or isinstance(planned, bool):
        return False
    frozen_value = freeze.field_values.get("target_pair_count")
    if frozen_value in (None, ""):
        return True
    try:
        frozen_int = int(str(frozen_value))
    except (TypeError, ValueError):
        return True
    return frozen_int != planned


def compare_campaign_freeze(
    baseline: Mapping[str, Any] | None,
    observed: Mapping[str, Any] | None,
) -> FreezeDrift:
    """Detect drift; comparability remains a human determination."""
    before = assess_campaign_freeze(baseline)
    after = assess_campaign_freeze(observed)
    changed: list[str] = []
    for field_id in CAMPAIGN_FREEZE_FIELD_IDS:
        before_value = before.field_values.get(field_id)
        after_value = after.field_values.get(field_id)
        if before_value != after_value:
            changed.append(field_id)
    if changed:
        return FreezeDrift(
            comparison_status="DRIFT_DETECTED",
            changed_fields=tuple(changed),
            comparability_decision="HUMAN_COMPARABILITY_DETERMINATION_REQUIRED",
        )
    return FreezeDrift(
        comparison_status="IDENTICAL",
        changed_fields=(),
        comparability_decision="NOT_APPLICABLE",
    )


def _validate_pair_structure(pair: Mapping[str, Any]) -> None:
    _require_mapping(pair, "pair")
    _check_keys(pair, PAIR_KEYS, "pair")
    for field in ("pair_id", "campaign_id", "scenario_id", "block_id", "session_id"):
        _require_non_empty_str(pair, field, "pair")
    if not _is_ab_order(pair["planned_controller_order"]):
        raise W19LedgerError(
            "pair.planned_controller_order must be a permutation of ['A', 'B']"
        )
    if pair["actual_controller_order"] is not None and not _is_ab_order(
        pair["actual_controller_order"]
    ):
        raise W19LedgerError(
            "pair.actual_controller_order must be null or a permutation of ['A', 'B']"
        )
    attempt_ids = pair["attempt_ids"]
    if not isinstance(attempt_ids, list) or not all(
        isinstance(item, str) and item.strip() for item in attempt_ids
    ):
        raise W19LedgerError("pair.attempt_ids must be a list of non-empty strings")
    if len(set(attempt_ids)) != len(attempt_ids):
        raise W19LedgerError(f"pair {pair['pair_id']!r} declares duplicate attempt ids")
    initial_state = pair["initial_state"]
    _require_mapping(initial_state, "pair.initial_state")
    _check_keys(initial_state, INITIAL_STATE_KEYS, "pair.initial_state")
    _require_non_empty_str(initial_state, "criterion_version", "pair.initial_state")
    arms = initial_state["arms"]
    _require_mapping(arms, "pair.initial_state.arms")
    if set(arms) != {"A", "B"}:
        raise W19LedgerError("pair.initial_state.arms must contain exactly A and B")
    for arm, values in arms.items():
        _require_mapping(values, f"pair.initial_state.arms[{arm!r}]")
        _check_keys(
            values, INITIAL_ARM_KEYS, f"pair.initial_state.arms[{arm!r}]"
        )


def _validate_audit_events(attempt: Mapping[str, Any]) -> None:
    events = attempt["audit_events"]
    if not isinstance(events, list) or not events:
        raise W19LedgerError(
            f"attempt {attempt['attempt_id']!r} must preserve at least one audit event"
        )
    previous_seq = 0
    for index, event in enumerate(events):
        _require_mapping(event, f"attempt.audit_events[{index}]")
        unknown = sorted(set(event) - AUDIT_EVENT_KEYS)
        if unknown:
            raise W19LedgerError(
                f"attempt.audit_events[{index}] contains unknown field(s): "
                + ", ".join(unknown)
            )
        for field in ("seq", "event", "actor"):
            if field not in event:
                raise W19LedgerError(
                    f"attempt.audit_events[{index}] lacks {field!r}"
                )
        seq = event["seq"]
        if not isinstance(seq, int) or isinstance(seq, bool) or seq <= previous_seq:
            raise W19LedgerError(
                f"attempt {attempt['attempt_id']!r} audit event seq must increase"
            )
        previous_seq = seq
        _require_non_empty_str(event, "event", f"attempt.audit_events[{index}]")
        _require_non_empty_str(event, "actor", f"attempt.audit_events[{index}]")
        if "detail" in event and not isinstance(event["detail"], str):
            raise W19LedgerError(
                f"attempt.audit_events[{index}].detail must be a text note; "
                "structured payloads could carry outcome-shaped values"
            )


def _validate_corrections(attempt: Mapping[str, Any]) -> None:
    corrections = attempt["corrections"]
    if not isinstance(corrections, list):
        raise W19LedgerError(
            f"attempt {attempt['attempt_id']!r} corrections must be a list"
        )
    for index, correction in enumerate(corrections):
        _require_mapping(correction, f"attempt.corrections[{index}]")
        _check_keys(correction, CORRECTION_KEYS, f"attempt.corrections[{index}]")
        for field in ("correction_id", "field", "reason", "recorded_by"):
            _require_non_empty_str(
                correction, field, f"attempt.corrections[{index}]"
            )
        if correction["field"] not in ATTEMPT_KEYS:
            raise W19LedgerError(
                f"attempt.corrections[{index}].field must name a recorded attempt field"
            )
        if not _is_scalar(correction["previous_value"]) or not _is_scalar(
            correction["corrected_value"]
        ):
            raise W19LedgerError(
                f"attempt.corrections[{index}] values must be scalar metadata"
            )


def _validate_attempt_structure(attempt: Mapping[str, Any]) -> None:
    _require_mapping(attempt, "attempt")
    _check_keys(attempt, ATTEMPT_KEYS, "attempt")
    for field in (
        "attempt_id",
        "pair_id",
        "campaign_id",
        "scenario_id",
        "block_id",
        "session_id",
        "run_id",
        "hardware_config_id",
        "calibration_id",
        "firmware_version",
        "model_artifact_id",
        "feature_version",
        "policy_version",
        "protocol_version",
        "disturbance_protocol_id",
        "source_path",
        "source_manifest_id",
        "validity_method",
    ):
        _require_non_empty_str(attempt, field, "attempt")
    if attempt["controller_arm"] not in {"A", "B"}:
        raise W19LedgerError("attempt.controller_arm must be 'A' or 'B'")
    if attempt["attempt_kind"] not in {ATTEMPT_KIND_INITIAL, ATTEMPT_KIND_RERUN}:
        raise W19LedgerError("attempt.attempt_kind must be INITIAL or RERUN")
    if attempt["attempt_status"] not in {ATTEMPT_STATUS_RECORDED, ATTEMPT_STATUS_ABORTED}:
        raise W19LedgerError("attempt.attempt_status must be RECORDED or ABORTED")
    if attempt["attempt_kind"] == ATTEMPT_KIND_INITIAL and attempt["supersedes"] is not None:
        raise W19LedgerError("an INITIAL attempt cannot supersede another attempt")
    if attempt["attempt_kind"] == ATTEMPT_KIND_RERUN:
        _optional_non_empty_str(attempt["supersedes"], "attempt.supersedes")
        if attempt["supersedes"] is None:
            raise W19LedgerError("a RERUN attempt must declare the attempt it supersedes")
    _optional_non_empty_str(attempt["superseded_by"], "attempt.superseded_by")
    source_sha = attempt["source_sha256"]
    if not isinstance(source_sha, str) or not _HEX64.match(source_sha):
        raise W19LedgerError("attempt.source_sha256 must be a lowercase SHA-256 hex digest")
    model_sha = attempt["model_artifact_sha256"]
    if attempt["controller_arm"] == "B":
        if not isinstance(model_sha, str) or not _HEX64.match(model_sha):
            raise W19LedgerError(
                "a Controller B attempt requires a lowercase SHA-256 model artifact digest"
            )
    elif model_sha is not None and (
        not isinstance(model_sha, str) or not _HEX64.match(model_sha)
    ):
        raise W19LedgerError(
            "attempt.model_artifact_sha256 must be null or a SHA-256 hex digest"
        )
    if attempt["quality_status"] not in {QUALITY_PASS, QUALITY_FAIL, QUALITY_PENDING}:
        raise W19LedgerError("attempt.quality_status has an unknown value")
    validity_status = attempt["validity_status"]
    if validity_status not in {
        VALIDITY_VALID,
        VALIDITY_INVALID,
        VALIDITY_PENDING,
        VALIDITY_NOT_APPLICABLE,
    }:
        raise W19LedgerError("attempt.validity_status has an unknown value")
    reason_codes = attempt["validity_reason_codes"]
    if not isinstance(reason_codes, list) or not all(
        isinstance(code, str) for code in reason_codes
    ):
        raise W19LedgerError("attempt.validity_reason_codes must be a list of strings")
    if len(set(reason_codes)) != len(reason_codes):
        raise W19LedgerError("attempt.validity_reason_codes contains duplicates")
    unknown_codes = sorted(set(reason_codes) - PREDECLARED_VALIDITY_REASON_CODES)
    if unknown_codes:
        raise W19LedgerError(
            "attempt.validity_reason_codes contains undeclared code(s): "
            + ", ".join(unknown_codes)
        )
    aborted = attempt["attempt_status"] == ATTEMPT_STATUS_ABORTED
    if aborted:
        if validity_status != VALIDITY_NOT_APPLICABLE:
            raise W19LedgerError("an ABORTED attempt must have validity NOT_APPLICABLE")
        if REASON_ATTEMPT_ABORTED not in reason_codes:
            raise W19LedgerError("an ABORTED attempt must record ATTEMPT_ABORTED")
    elif validity_status == VALIDITY_NOT_APPLICABLE:
        raise W19LedgerError(
            "only an ABORTED attempt may have validity NOT_APPLICABLE"
        )
    if validity_status == VALIDITY_VALID:
        if attempt["quality_status"] != QUALITY_PASS:
            raise W19LedgerError("a VALID attempt requires QUALITY_PASS")
        if reason_codes:
            raise W19LedgerError("a VALID attempt cannot carry validity reason codes")
    if validity_status == VALIDITY_INVALID and not reason_codes:
        raise W19LedgerError("an INVALID attempt must record objective reason codes")
    markers = attempt["fixture_markers"]
    if not isinstance(markers, list) or not all(isinstance(m, str) for m in markers):
        raise W19LedgerError("attempt.fixture_markers must be a list of strings")
    if len(set(markers)) != len(markers):
        raise W19LedgerError("attempt.fixture_markers contains duplicates")
    unknown_markers = sorted(set(markers) - set(FIXTURE_MARKERS))
    if unknown_markers:
        raise W19LedgerError(
            "attempt.fixture_markers contains unknown marker(s): "
            + ", ".join(unknown_markers)
        )
    _validate_audit_events(attempt)
    _validate_corrections(attempt)


def _index_attempts(
    pairs_by_id: Mapping[str, Mapping[str, Any]],
    attempts: Sequence[Mapping[str, Any]],
) -> tuple[
    dict[str, list[Mapping[str, Any]]],
    dict[str, Mapping[str, Any]],
]:
    by_pair: dict[str, list[Mapping[str, Any]]] = {
        pair_id: [] for pair_id in pairs_by_id
    }
    seen: dict[str, Mapping[str, Any]] = {}
    for attempt in attempts:
        pair_id = attempt["pair_id"]
        if pair_id not in by_pair:
            raise W19LedgerError(
                f"attempt {attempt['attempt_id']!r} references unknown pair {pair_id!r}"
            )
        attempt_id = attempt["attempt_id"]
        if attempt_id in seen:
            raise W19LedgerError(f"duplicate attempt identity {attempt_id!r} detected")
        seen[attempt_id] = attempt
        by_pair[pair_id].append(attempt)
    for pair_id, pair in pairs_by_id.items():
        declared = list(pair["attempt_ids"])
        actual = [attempt["attempt_id"] for attempt in by_pair[pair_id]]
        if len(declared) != len(actual) or set(declared) != set(actual):
            raise W19LedgerError(
                f"pair {pair_id!r} attempt history is incomplete or inconsistent: "
                f"declared {sorted(declared)}, recorded {sorted(actual)}"
            )
    return by_pair, seen


def _validate_supersession(
    attempts: Sequence[Mapping[str, Any]],
    seen: Mapping[str, Mapping[str, Any]],
) -> None:
    for attempt in attempts:
        supersedes = attempt["supersedes"]
        if supersedes is not None:
            target = seen.get(supersedes)
            if target is None:
                raise W19LedgerError(
                    f"attempt {attempt['attempt_id']!r} supersedes unknown attempt {supersedes!r}"
                )
            if (
                target["pair_id"] != attempt["pair_id"]
                or target["controller_arm"] != attempt["controller_arm"]
            ):
                raise W19LedgerError(
                    "a rerun must stay inside its original pair and controller arm; a "
                    "new run identity is not a new independent pair"
                )
            if target["superseded_by"] != attempt["attempt_id"]:
                raise W19LedgerError(
                    f"supersession chain broken: {supersedes!r}.superseded_by does not "
                    f"point at {attempt['attempt_id']!r}"
                )
        superseded_by = attempt["superseded_by"]
        if superseded_by is not None:
            successor = seen.get(superseded_by)
            if successor is None:
                raise W19LedgerError(
                    f"attempt {attempt['attempt_id']!r} names unknown successor {superseded_by!r}"
                )
            if successor["supersedes"] != attempt["attempt_id"]:
                raise W19LedgerError(
                    f"supersession chain broken: {superseded_by!r}.supersedes does not "
                    f"point at {attempt['attempt_id']!r}"
                )
        visited: set[str] = set()
        cursor: Mapping[str, Any] | None = attempt
        while cursor is not None and cursor["supersedes"] is not None:
            if cursor["attempt_id"] in visited:
                raise W19LedgerError("supersession cycle detected")
            visited.add(cursor["attempt_id"])
            cursor = seen.get(cursor["supersedes"])


def _duplicate_values(
    attempts: Sequence[Mapping[str, Any]], key: str
) -> frozenset[str]:
    counts: dict[str, list[str]] = {}
    for attempt in attempts:
        value = attempt[key]
        counts.setdefault(str(value), []).append(attempt["attempt_id"])
    return frozenset(value for value, ids in counts.items() if len(ids) > 1)


def _assess_matching_policy(record: Mapping[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {"frozen": False, "tmean_delta_max_c": None, "gradient_delta_max_c": None}
    if not isinstance(record, Mapping):
        raise W19LedgerError("matching_policy must be an object")
    unknown = sorted(
        set(record)
        - {
            "status",
            "initial_tmean_delta_max_c",
            "initial_gradient_delta_max_c",
            "approval",
        }
    )
    if unknown:
        raise W19LedgerError(
            f"matching_policy contains unknown field(s): {', '.join(unknown)}"
        )
    tmean = record.get("initial_tmean_delta_max_c")
    gradient = record.get("initial_gradient_delta_max_c")
    approval = record.get("approval")
    frozen = (
        record.get("status") == FREEZE_FROZEN_APPROVED
        and _is_number(tmean)
        and tmean > 0
        and _is_number(gradient)
        and gradient > 0
        and _freeze_approval_ok(approval)
    )
    return {
        "frozen": frozen,
        "tmean_delta_max_c": tmean if _is_number(tmean) else None,
        "gradient_delta_max_c": gradient if _is_number(gradient) else None,
    }


def _assess_failure_policy(record: Mapping[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {"frozen": False, "handling": None}
    if not isinstance(record, Mapping):
        raise W19LedgerError("failure_policy must be an object")
    unknown = sorted(
        set(record) - {"status", "invalid_arm_handling", "canonical_ref", "approval"}
    )
    if unknown:
        raise W19LedgerError(
            f"failure_policy contains unknown field(s): {', '.join(unknown)}"
        )
    handling = record.get("invalid_arm_handling")
    if handling is not None and handling not in FAILURE_HANDLINGS:
        raise W19LedgerError(
            "failure_policy.invalid_arm_handling must be null, "
            f"{FAILURE_RERUN_INVALID_ARM!r} or {FAILURE_INVALIDATE_PAIR!r}"
        )
    frozen = (
        record.get("status") == FREEZE_FROZEN_APPROVED
        and handling in FAILURE_HANDLINGS
        and _freeze_approval_ok(record.get("approval"))
        and bool(str(record.get("canonical_ref") or "").strip())
    )
    return {"frozen": frozen, "handling": handling if frozen else None}


def _assess_randomization(
    record: Mapping[str, Any] | None, pairs_by_id: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    if record is None:
        return {"registered": False, "orders": {}}
    if not isinstance(record, Mapping):
        raise W19LedgerError("randomization must be an object")
    unknown = sorted(
        set(record) - {"status", "seed", "order_list", "canonical_ref"}
    )
    if unknown:
        raise W19LedgerError(
            f"randomization contains unknown field(s): {', '.join(unknown)}"
        )
    if record.get("status") not in {"NOT_REGISTERED", "REGISTERED"}:
        raise W19LedgerError("randomization.status must be NOT_REGISTERED or REGISTERED")
    orders: dict[str, tuple[str, ...]] = {}
    order_list = record.get("order_list")
    if order_list is not None:
        if not isinstance(order_list, list):
            raise W19LedgerError("randomization.order_list must be a list")
        for index, entry in enumerate(order_list):
            _require_mapping(entry, f"randomization.order_list[{index}]")
            unknown_entry = sorted(set(entry) - {"pair_id", "planned_order"})
            if unknown_entry:
                raise W19LedgerError(
                    f"randomization.order_list[{index}] contains unknown field(s): "
                    + ", ".join(unknown_entry)
                )
            pair_id = _require_non_empty_str(
                entry, "pair_id", f"randomization.order_list[{index}]"
            )
            planned = entry.get("planned_order")
            if not _is_ab_order(planned):
                raise W19LedgerError(
                    f"randomization.order_list[{index}].planned_order must be a "
                    "permutation of ['A', 'B']"
                )
            if pair_id in orders:
                raise W19LedgerError(
                    f"randomization.order_list declares pair {pair_id!r} more than once"
                )
            if pair_id not in pairs_by_id:
                raise W19LedgerError(
                    f"randomization.order_list references unknown pair {pair_id!r}"
                )
            orders[pair_id] = tuple(planned)
    registered = (
        record.get("status") == "REGISTERED"
        and order_list is not None
        and bool(str(record.get("seed") or "").strip())
        and bool(str(record.get("canonical_ref") or "").strip())
    )
    return {"registered": registered, "orders": orders if registered else {}}


def _compare_initial_state(
    pair: Mapping[str, Any], matching: Mapping[str, Any]
) -> tuple[dict[str, Any], str, tuple[str, ...]]:
    state = pair["initial_state"]
    arms = state["arms"]
    comparison: dict[str, Any] = {
        "criterion_version": state["criterion_version"],
        "tolerances": {
            "tmean_delta_max_c": matching["tmean_delta_max_c"],
            "gradient_delta_max_c": matching["gradient_delta_max_c"],
        },
        "arms": {
            arm: {
                field: arms[arm].get(field)
                for field in (
                    "initial_tmean_c",
                    "initial_gradient_c",
                    "ambient_temp_c",
                    "ambient_rh_pct",
                    "door_state",
                    "cooling_state",
                )
            }
            for arm in ("A", "B")
        },
        "tmean_delta_c": None,
        "gradient_delta_c": None,
        "status": "NOT_EVALUATED",
    }
    missing: list[str] = []
    for arm in ("A", "B"):
        for field in ("initial_tmean_c", "initial_gradient_c", "ambient_temp_c"):
            if not _is_number(arms[arm].get(field)):
                missing.append(f"{arm}.{field}")
    if missing:
        comparison["status"] = "EVIDENCE_MISSING"
        return comparison, "MISSING", (REASON_INITIAL_MISSING,)
    invalid: set[str] = set()
    for arm in ("A", "B"):
        if arms[arm].get("door_state") != "CLOSED":
            invalid.add(REASON_DOOR_NOT_CLOSED)
        if arms[arm].get("cooling_state") not in {"ON", "OFF"}:
            invalid.add(REASON_COOLING_UNKNOWN)
    tmean_delta = abs(
        float(arms["A"]["initial_tmean_c"]) - float(arms["B"]["initial_tmean_c"])
    )
    gradient_delta = abs(
        float(arms["A"]["initial_gradient_c"]) - float(arms["B"]["initial_gradient_c"])
    )
    comparison["tmean_delta_c"] = round(tmean_delta, 6)
    comparison["gradient_delta_c"] = round(gradient_delta, 6)
    tmean_limit = float(matching["tmean_delta_max_c"])
    gradient_limit = float(matching["gradient_delta_max_c"])
    if tmean_delta > tmean_limit:
        invalid.add(REASON_INITIAL_TMEAN)
    if gradient_delta > gradient_limit:
        invalid.add(REASON_INITIAL_GRADIENT)
    if invalid:
        comparison["status"] = "INVALID_EVIDENCE"
        return comparison, "INVALID", tuple(sorted(invalid))
    comparison["status"] = "WITHIN_TOLERANCE"
    return comparison, "WITHIN_TOLERANCE", ()


def _matching_mismatches(
    pair: Mapping[str, Any],
    attempts: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    codes: set[str] = set()
    for attempt in attempts:
        if attempt["scenario_id"] != pair["scenario_id"]:
            codes.add(REASON_SCENARIO_MISMATCH)
        if (
            attempt["campaign_id"] != pair["campaign_id"]
            or attempt["block_id"] != pair["block_id"]
            or attempt["session_id"] != pair["session_id"]
        ):
            codes.add(REASON_SCOPE_MISMATCH)
    common_fields = (
        ("hardware_config_id", REASON_HARDWARE_MISMATCH),
        ("calibration_id", REASON_CALIBRATION_MISMATCH),
        ("firmware_version", REASON_FIRMWARE_MISMATCH),
        ("protocol_version", REASON_PROTOCOL_VERSION_MISMATCH),
        ("disturbance_protocol_id", REASON_DISTURBANCE_PROTOCOL_MISMATCH),
    )
    for field, code in common_fields:
        if attempts[0][field] != attempts[1][field]:
            codes.add(code)
    for field, code in (
        ("feature_version", REASON_FEATURE_MISMATCH),
        ("model_artifact_id", REASON_MODEL_ARTIFACT_MISMATCH),
        ("model_artifact_sha256", REASON_MODEL_ARTIFACT_MISMATCH),
    ):
        left = attempts[0].get(field)
        right = attempts[1].get(field)
        if left in (None, SENTINEL_NOT_APPLICABLE) or right in (
            None,
            SENTINEL_NOT_APPLICABLE,
        ):
            continue
        if left != right:
            codes.add(code)
    return tuple(sorted(codes))


def _campaign_drift_fields(
    pair: Mapping[str, Any],
    attempts: Sequence[Mapping[str, Any]],
    freeze: CampaignFreezeAssessment,
) -> tuple[str, ...]:
    if freeze.freeze_status != FREEZE_STATUS_APPROVED:
        return ()
    values = freeze.field_values
    drift: set[str] = set()
    for field, freeze_id in DRIFT_ATTEMPT_FIELDS:
        expected = values.get(freeze_id)
        if expected in (None, ""):
            continue
        for attempt in attempts:
            if str(attempt[field]) != str(expected):
                drift.add(freeze_id)
    expected_policy = values.get("controller_policy_version")
    if expected_policy not in (None, ""):
        for attempt in attempts:
            if attempt["controller_arm"] == "B" and str(
                attempt["policy_version"]
            ) != str(expected_policy):
                drift.add("controller_policy_version")
    expected_model = values.get("model_artifact_sha256")
    if expected_model not in (None, ""):
        for attempt in attempts:
            if attempt["controller_arm"] == "B" and str(
                attempt["model_artifact_sha256"]
            ) != str(expected_model):
                drift.add("model_artifact_sha256")
    expected_reset = values.get("initial_reset_criterion")
    if expected_reset not in (None, ""):
        if str(pair["initial_state"]["criterion_version"]) != str(expected_reset):
            drift.add("initial_reset_criterion")
    return tuple(sorted(drift))


def _terminals_by_arm(
    pair_attempts: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    terminals: dict[str, list[Mapping[str, Any]]] = {"A": [], "B": []}
    for attempt in pair_attempts:
        if attempt["superseded_by"] is None:
            terminals[attempt["controller_arm"]].append(attempt)
    return terminals


def _is_invalid_history_attempt(attempt: Mapping[str, Any]) -> bool:
    return (
        attempt["validity_status"] == VALIDITY_INVALID
        or attempt["attempt_status"] == ATTEMPT_STATUS_ABORTED
    )


def _rerun_of_non_invalid_arm(
    pair_attempts: Sequence[Mapping[str, Any]],
    attempt_index: Mapping[str, Mapping[str, Any]],
) -> bool:
    for attempt in pair_attempts:
        if attempt["attempt_kind"] != ATTEMPT_KIND_RERUN:
            continue
        target = attempt_index[attempt["supersedes"]]
        if not _is_invalid_history_attempt(target):
            return True
    return False


def _assess_pair(
    pair: Mapping[str, Any],
    pair_attempts: Sequence[Mapping[str, Any]],
    *,
    evidence_class: str,
    matching: Mapping[str, Any],
    failure: Mapping[str, Any],
    randomization: Mapping[str, Any],
    campaign_freeze: CampaignFreezeAssessment,
    authorization: AuthorizationAssessment,
    attempt_index: Mapping[str, Mapping[str, Any]],
    duplicate_run_ids: frozenset[str],
    duplicate_source_shas: frozenset[str],
    duplicate_source_paths: frozenset[str],
) -> PairAssessment:
    pair_id = pair["pair_id"]
    fixture_ids = tuple(
        attempt["attempt_id"]
        for attempt in pair_attempts
        if attempt["fixture_markers"]
    )

    def build(
        status: str,
        reasons: Sequence[str] = (),
        *,
        selected: Mapping[str, str | None] | None = None,
        comparison: Mapping[str, Any] | None = None,
        drift_fields: Sequence[str] = (),
        physical_admissible: bool = False,
    ) -> PairAssessment:
        return PairAssessment(
            pair_id=pair_id,
            status=status,
            reason_codes=tuple(sorted(set(reasons))),
            selected_attempts=dict(selected or {"A": None, "B": None}),
            initial_state_comparison=dict(
                comparison or {"status": "NOT_EVALUATED"}
            ),
            campaign_identity_drift_fields=tuple(drift_fields),
            fixture_attempt_ids=fixture_ids,
            physical_admissible=physical_admissible,
        )

    terminals = _terminals_by_arm(pair_attempts)
    selected: dict[str, str | None] = {"A": None, "B": None}
    for arm, items in terminals.items():
        if len(items) == 1:
            selected[arm] = items[0]["attempt_id"]

    if not terminals["A"] and not terminals["B"]:
        return build(PAIR_PLANNED)
    if any(len(items) > 1 for items in terminals.values()):
        return build(PAIR_UNRESOLVED, (REASON_AMBIGUOUS_ARM_HISTORY,), selected=selected)
    if not terminals["A"] or not terminals["B"]:
        return build(PAIR_AWAITING_SECOND_ARM, selected=selected)

    if _rerun_of_non_invalid_arm(pair_attempts, attempt_index):
        return build(
            PAIR_INVALID, (REASON_RERUN_OF_NON_INVALID_ARM,), selected=selected
        )

    invalid_history = [
        attempt
        for attempt in pair_attempts
        if _is_invalid_history_attempt(attempt)
    ]
    if invalid_history:
        history_reasons: set[str] = set()
        for attempt in invalid_history:
            history_reasons.update(attempt["validity_reason_codes"])
        if not failure["frozen"]:
            return build(
                PAIR_BLOCKED_MISSING_FREEZE,
                history_reasons | {REASON_FAILURE_POLICY_UNFROZEN},
                selected=selected,
            )
        if failure["handling"] == FAILURE_INVALIDATE_PAIR:
            return build(
                PAIR_INVALID,
                history_reasons | {REASON_POLICY_INVALIDATES_PAIR},
                selected=selected,
            )

    arm_a = terminals["A"][0]
    arm_b = terminals["B"][0]
    arms = (arm_a, arm_b)

    if any(attempt["validity_status"] == VALIDITY_PENDING for attempt in arms):
        return build(PAIR_AWAITING_VALIDITY, (REASON_VALIDITY_PENDING,), selected=selected)

    invalid_arms = [
        attempt
        for attempt in arms
        if attempt["validity_status"] == VALIDITY_INVALID
        or attempt["attempt_status"] == ATTEMPT_STATUS_ABORTED
    ]
    if invalid_arms:
        arm_reasons: set[str] = set()
        for attempt in invalid_arms:
            arm_reasons.update(attempt["validity_reason_codes"])
        if not failure["frozen"]:
            return build(
                PAIR_BLOCKED_MISSING_FREEZE,
                arm_reasons | {REASON_FAILURE_POLICY_UNFROZEN},
                selected=selected,
            )
        if failure["handling"] == FAILURE_INVALIDATE_PAIR:
            return build(
                PAIR_INVALID,
                arm_reasons | {REASON_POLICY_INVALIDATES_PAIR},
                selected=selected,
            )
        return build(
            PAIR_UNRESOLVED,
            arm_reasons | {REASON_RERUN_NOT_COMPLETED},
            selected=selected,
        )

    if not matching["frozen"]:
        return build(
            PAIR_BLOCKED_MISSING_FREEZE, (REASON_MATCHING_UNFROZEN,), selected=selected
        )
    if not randomization["registered"]:
        return build(
            PAIR_BLOCKED_MISSING_FREEZE,
            (REASON_RANDOMIZATION_NOT_REGISTERED,),
            selected=selected,
        )
    registered_order = randomization["orders"].get(pair_id)
    if registered_order is None:
        return build(
            PAIR_BLOCKED_MISSING_FREEZE,
            (REASON_RANDOMIZATION_ENTRY_MISSING,),
            selected=selected,
        )

    mismatches = _matching_mismatches(pair, arms)
    if mismatches:
        return build(PAIR_INVALID, mismatches, selected=selected)

    planned = tuple(pair["planned_controller_order"])
    actual = pair["actual_controller_order"]
    if not _is_ab_order(actual):
        return build(
            PAIR_INVALID, (REASON_CONTROLLER_ORDER_MISSING,), selected=selected
        )
    if tuple(actual) != planned:
        return build(PAIR_INVALID, (REASON_ORDER_DEVIATION,), selected=selected)
    if tuple(registered_order) != planned:
        return build(
            PAIR_INVALID, (REASON_ORDER_RANDOMIZATION,), selected=selected
        )

    comparison, initial_status, initial_reasons = _compare_initial_state(pair, matching)
    if initial_status == "MISSING":
        return build(
            PAIR_UNRESOLVED, initial_reasons, selected=selected, comparison=comparison
        )
    if initial_status == "INVALID":
        return build(
            PAIR_INVALID, initial_reasons, selected=selected, comparison=comparison
        )

    unresolved: set[str] = set()
    drift_fields = _campaign_drift_fields(pair, arms, campaign_freeze)
    if drift_fields:
        unresolved.add(REASON_CAMPAIGN_IDENTITY_DRIFT)
    if any(attempt["run_id"] in duplicate_run_ids for attempt in arms):
        unresolved.add(REASON_DUPLICATE_RUN_ID)
    if any(attempt["source_sha256"] in duplicate_source_shas for attempt in arms):
        unresolved.add(REASON_DUPLICATE_SOURCE_SHA)
    if any(attempt["source_path"] in duplicate_source_paths for attempt in arms):
        unresolved.add(REASON_DUPLICATE_SOURCE_PATH)
    if evidence_class == EVIDENCE_PHYSICAL_CAMPAIGN and fixture_ids:
        unresolved.add(REASON_FIXTURE_IN_PHYSICAL)
    if unresolved:
        return build(
            PAIR_UNRESOLVED,
            unresolved,
            selected=selected,
            comparison=comparison,
            drift_fields=drift_fields,
        )

    physical = (
        evidence_class == EVIDENCE_PHYSICAL_CAMPAIGN
        and authorization.status == AUTHORIZATION_AUTHORIZED
        and campaign_freeze.freeze_status == FREEZE_STATUS_APPROVED
        and not fixture_ids
    )
    return build(
        PAIR_VALID,
        (),
        selected=selected,
        comparison=comparison,
        physical_admissible=physical,
    )


def _attempt_accounting(
    attempts: Sequence[Mapping[str, Any]],
    assessments: Sequence[PairAssessment],
    evidence_class: str,
) -> AttemptAccounting:
    selected = sum(
        1
        for assessment in assessments
        for attempt_id in assessment.selected_attempts.values()
        if attempt_id is not None
    )
    synthetic = 0
    physical = 0
    for attempt in attempts:
        if evidence_class == EVIDENCE_SYNTHETIC_FIXTURE or attempt["fixture_markers"]:
            synthetic += 1
        else:
            physical += 1
    return AttemptAccounting(
        total_attempts=len(attempts),
        initial_attempts=sum(
            1 for a in attempts if a["attempt_kind"] == ATTEMPT_KIND_INITIAL
        ),
        rerun_attempts=sum(
            1 for a in attempts if a["attempt_kind"] == ATTEMPT_KIND_RERUN
        ),
        recorded_attempts=sum(
            1 for a in attempts if a["attempt_status"] == ATTEMPT_STATUS_RECORDED
        ),
        aborted_attempts=sum(
            1 for a in attempts if a["attempt_status"] == ATTEMPT_STATUS_ABORTED
        ),
        valid_attempts=sum(1 for a in attempts if a["validity_status"] == VALIDITY_VALID),
        invalid_attempts=sum(
            1 for a in attempts if a["validity_status"] == VALIDITY_INVALID
        ),
        pending_attempts=sum(
            1 for a in attempts if a["validity_status"] == VALIDITY_PENDING
        ),
        superseded_attempts=sum(
            1 for a in attempts if a["superseded_by"] is not None
        ),
        selected_attempts=selected,
        synthetic_attempts=synthetic,
        physical_candidate_attempts=physical,
    )


def validate_pair_ledger(document: Mapping[str, Any]) -> PairLedgerValidation:
    """Validate a complete campaign ledger and derive every pair state."""
    assert_outcome_blind(document, context="pair ledger")
    _require_mapping(document, "pair ledger")
    unknown = sorted(set(document) - LEDGER_KEYS)
    if unknown:
        raise W19LedgerError(
            f"pair ledger contains unknown field(s): {', '.join(unknown)}"
        )
    missing = sorted(LEDGER_REQUIRED_KEYS - set(document))
    if missing:
        raise W19LedgerError(
            f"pair ledger lacks required field(s): {', '.join(missing)}"
        )
    if document["schema"] != PAIR_LEDGER_SCHEMA:
        raise W19LedgerError(
            f"unsupported ledger schema {document['schema']!r}; expected {PAIR_LEDGER_SCHEMA!r}"
        )
    campaign_id = _require_non_empty_str(document, "campaign_id", "pair ledger")
    evidence_class = document["evidence_class"]
    if evidence_class not in EVIDENCE_CLASSES:
        raise W19LedgerError(
            f"evidence_class must be one of {sorted(EVIDENCE_CLASSES)}"
        )
    analysis_plan_version = _require_non_empty_str(
        document, "analysis_plan_version", "pair ledger"
    )
    pairs_payload = document["pairs"]
    attempts_payload = document["attempts"]
    if not isinstance(pairs_payload, list):
        raise W19LedgerError("pair ledger.pairs must be a list")
    if not isinstance(attempts_payload, list):
        raise W19LedgerError("pair ledger.attempts must be a list")

    pairs_by_id: dict[str, Mapping[str, Any]] = {}
    for pair in pairs_payload:
        _validate_pair_structure(pair)
        pair_id = pair["pair_id"]
        if pair_id in pairs_by_id:
            raise W19LedgerError(f"duplicate pair identity {pair_id!r}")
        if pair["campaign_id"] != campaign_id:
            raise W19LedgerError(
                f"pair {pair_id!r} campaign_id does not match the ledger campaign"
            )
        pairs_by_id[pair_id] = pair

    for attempt in attempts_payload:
        _validate_attempt_structure(attempt)
        if attempt["campaign_id"] != campaign_id:
            raise W19LedgerError(
                f"attempt {attempt['attempt_id']!r} campaign_id does not match the ledger"
            )

    by_pair, attempt_index = _index_attempts(pairs_by_id, attempts_payload)
    _validate_supersession(attempts_payload, attempt_index)

    for attempt in attempts_payload:
        markers = set(attempt["fixture_markers"])
        if evidence_class == EVIDENCE_SYNTHETIC_FIXTURE:
            if markers != set(FIXTURE_MARKERS):
                raise W19LedgerError(
                    f"synthetic attempt {attempt['attempt_id']!r} must carry both "
                    f"markers {FIXTURE_MARKERS}; a fixture must be permanently marked"
                )

    duplicate_run_ids = _duplicate_values(attempts_payload, "run_id")
    duplicate_source_shas = _duplicate_values(attempts_payload, "source_sha256")
    duplicate_source_paths = _duplicate_values(attempts_payload, "source_path")

    authorization = evaluate_campaign_authorization(
        document.get("campaign_authorization")
    )
    campaign_freeze = assess_campaign_freeze(document.get("campaign_freeze"))
    matching = _assess_matching_policy(document.get("matching_policy"))
    failure = _assess_failure_policy(document.get("failure_policy"))
    randomization = _assess_randomization(document.get("randomization"), pairs_by_id)
    statistical_freeze = assess_statistical_freeze(
        document.get("statistical_freeze")
    )

    assessments = tuple(
        _assess_pair(
            pair,
            by_pair[pair_id],
            evidence_class=evidence_class,
            matching=matching,
            failure=failure,
            randomization=randomization,
            campaign_freeze=campaign_freeze,
            authorization=authorization,
            attempt_index=attempt_index,
            duplicate_run_ids=duplicate_run_ids,
            duplicate_source_shas=duplicate_source_shas,
            duplicate_source_paths=duplicate_source_paths,
        )
        for pair_id, pair in pairs_by_id.items()
    )

    counts = {status: 0 for status in PAIR_STATUSES}
    for assessment in assessments:
        counts[assessment.status] += 1

    refusal_reasons: list[str] = []
    if duplicate_run_ids:
        refusal_reasons.append(REASON_DUPLICATE_RUN_ID)
    if duplicate_source_shas:
        refusal_reasons.append(REASON_DUPLICATE_SOURCE_SHA)
    if duplicate_source_paths:
        refusal_reasons.append(REASON_DUPLICATE_SOURCE_PATH)
    if authorization.status == AUTHORIZATION_FAKE_APPROVAL:
        refusal_reasons.append(AUTHORIZATION_FAKE_APPROVAL)
    if evidence_class == EVIDENCE_PHYSICAL_CAMPAIGN and any(
        attempt["fixture_markers"] for attempt in attempts_payload
    ):
        refusal_reasons.append(REASON_FIXTURE_IN_PHYSICAL)
    target_count_conflict = _target_count_conflict(
        campaign_freeze, document.get("frozen_target")
    )
    if target_count_conflict:
        refusal_reasons.append(REASON_TARGET_COUNT_CONFLICT)

    accounting = _attempt_accounting(attempts_payload, assessments, evidence_class)
    physical_valid_pairs = sum(
        1 for assessment in assessments if assessment.physical_admissible
    )
    software_valid_pairs = sum(
        1 for assessment in assessments if assessment.status == PAIR_VALID
    )
    accepted = (
        physical_valid_pairs > 0
        and not refusal_reasons
        and authorization.status == AUTHORIZATION_AUTHORIZED
        and campaign_freeze.freeze_status == FREEZE_STATUS_APPROVED
        and evidence_class == EVIDENCE_PHYSICAL_CAMPAIGN
    )
    return PairLedgerValidation(
        schema=PAIR_LEDGER_SCHEMA,
        campaign_id=campaign_id,
        evidence_class=evidence_class,
        analysis_plan_version=analysis_plan_version,
        pair_status_counts=counts,
        pairs=assessments,
        attempt_accounting=accounting,
        authorization=authorization.to_dict(),
        campaign_freeze=campaign_freeze.to_dict(),
        statistical_freeze=statistical_freeze.to_dict(),
        refusal_reasons=tuple(refusal_reasons),
        physical_valid_pairs=physical_valid_pairs,
        software_valid_pairs=software_valid_pairs,
        physical_pair_evidence_accepted=accepted,
        ledger_integrity_ok=not refusal_reasons,
        target_count_conflict=target_count_conflict,
    )


def _fixture_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_test_only_fixture_ledger() -> dict[str, Any]:
    """Build a permanently marked synthetic ledger for software controls only."""
    model_sha = _fixture_sha256("W19-FIXTURE-MODEL-ARTIFACT")
    source_a = _fixture_sha256("W19-FIXTURE-SOURCE-A")
    source_b = _fixture_sha256("W19-FIXTURE-SOURCE-B")

    def attempt(arm: str, source_sha: str) -> dict[str, Any]:
        return {
            "attempt_id": f"ATT-TEST-001-{arm}",
            "pair_id": "PAIR-TEST-001",
            "campaign_id": "CG-W19-SOFTWARE-FIXTURE",
            "scenario_id": "S2_DOOR_DISTURBANCE",
            "block_id": "BLOCK-FIXTURE-1",
            "session_id": "SESSION-FIXTURE-1",
            "run_id": f"RUN-TEST-001-{arm}",
            "controller_arm": arm,
            "attempt_kind": "INITIAL",
            "attempt_status": "RECORDED",
            "supersedes": None,
            "superseded_by": None,
            "corrections": [],
            "hardware_config_id": "CG-HW-FIXTURE-001",
            "calibration_id": "CG-CAL-FIXTURE-001",
            "firmware_version": "fw-fixture-1.0.0",
            "model_artifact_id": (
                "TEST-FIXTURE-MODEL-NOT-A-REAL-MODEL"
                if arm == "B"
                else SENTINEL_NOT_APPLICABLE
            ),
            "model_artifact_sha256": model_sha if arm == "B" else None,
            "feature_version": (
                "test-fixture-feature-v1" if arm == "B" else SENTINEL_NOT_APPLICABLE
            ),
            "policy_version": f"test-fixture-{'predictive' if arm == 'B' else 'reactive'}-policy-v1",
            "protocol_version": "test-fixture-protocol-v1",
            "disturbance_protocol_id": "DOOR-DISTURBANCE-FIXTURE-v1",
            "source_path": f"test://w19/fixture/run-{arm}",
            "source_manifest_id": "TEST-FIXTURE-MANIFEST-001",
            "source_sha256": source_sha,
            "quality_status": "QUALITY_PASS",
            "validity_status": "VALID",
            "validity_reason_codes": [],
            "validity_method": "coldguard-w19-validity-review-v1",
            "audit_events": [
                {"seq": 1, "event": "ATTEMPT_CREATED", "actor": "test-fixture"},
                {"seq": 2, "event": "VALIDITY_RECORDED", "actor": "test-fixture"},
            ],
            "fixture_markers": ["TEST_ONLY", "SYNTHETIC_SOFTWARE_CONTROL_ONLY"],
        }

    return {
        "schema": PAIR_LEDGER_SCHEMA,
        "campaign_id": "CG-W19-SOFTWARE-FIXTURE",
        "evidence_class": EVIDENCE_SYNTHETIC_FIXTURE,
        "analysis_plan_version": "w03-analysis-contract-v1-fixture",
        "campaign_authorization": {
            "authorized": False,
            "authority_id": None,
            "authority_role": None,
            "canonical_ref": None,
            "g4_status": "NOT_READY",
            "pair_target_frozen": False,
            "analysis_freeze_accepted": False,
        },
        "campaign_freeze": None,
        "matching_policy": {
            "status": "FROZEN_APPROVED",
            "initial_tmean_delta_max_c": 0.5,
            "initial_gradient_delta_max_c": 0.3,
            "approval": {
                "authority_id": "TEST_FIXTURE_ONLY",
                "authority_role": "TEAM_LEAD",
                "canonical_ref": "test://w19/fixture-matching-policy",
            },
        },
        "failure_policy": {
            "status": "FROZEN_APPROVED",
            "invalid_arm_handling": FAILURE_RERUN_INVALID_ARM,
            "canonical_ref": "test://w19/fixture-failure-policy",
            "approval": {
                "authority_id": "TEST_FIXTURE_ONLY",
                "canonical_ref": "test://w19/fixture-failure-policy-approval",
            },
        },
        "randomization": {
            "status": "REGISTERED",
            "seed": "TEST-FIXTURE-SEED",
            "order_list": [
                {"pair_id": "PAIR-TEST-001", "planned_order": ["A", "B"]}
            ],
            "canonical_ref": "test://w19/fixture-randomization",
        },
        "frozen_target": None,
        "statistical_freeze": None,
        "pairs": [
            {
                "pair_id": "PAIR-TEST-001",
                "campaign_id": "CG-W19-SOFTWARE-FIXTURE",
                "scenario_id": "S2_DOOR_DISTURBANCE",
                "block_id": "BLOCK-FIXTURE-1",
                "session_id": "SESSION-FIXTURE-1",
                "planned_controller_order": ["A", "B"],
                "actual_controller_order": ["A", "B"],
                "attempt_ids": ["ATT-TEST-001-A", "ATT-TEST-001-B"],
                "initial_state": {
                    "criterion_version": "CG-RESET-FIXTURE-v1",
                    "arms": {
                        "A": {
                            "initial_tmean_c": 24.0,
                            "initial_gradient_c": 0.40,
                            "ambient_temp_c": 23.2,
                            "ambient_rh_pct": 55.0,
                            "door_state": "CLOSED",
                            "cooling_state": "OFF",
                        },
                        "B": {
                            "initial_tmean_c": 24.1,
                            "initial_gradient_c": 0.45,
                            "ambient_temp_c": 23.3,
                            "ambient_rh_pct": 56.0,
                            "door_state": "CLOSED",
                            "cooling_state": "OFF",
                        },
                    },
                },
            }
        ],
        "attempts": [attempt("A", source_a), attempt("B", source_b)],
    }
