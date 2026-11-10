"""W20 final campaign-lock verification and analysis-readiness gate (B-W20-01).

Canonical anchors: Doc 03 §§95-102, 130-137, 158-163; Doc 04 W20 and Gate G5;
Doc 05B §48 B-W20-01/03 and the W22 analysis boundary.

The gate is metadata-only.  It reuses the W19 attempt ledger, campaign-freeze,
statistical-freeze and pair-target contracts instead of duplicating them.  It
checks whether the final physical A/B campaign is *ready for external review
and a separate analysis authorization*; it never opens a physical outcome
payload, integrates temperature or energy, computes an EWT, a paired
difference, a p-value or a confidence interval.

A structurally valid synthetic fixture can pass the software gate, but its
result is permanently labelled ``TEST_ONLY_SOFTWARE_GATE_PROOF``.  The
``ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION`` state additionally requires a
physical evidence class and an externally verified analysis-execution
authorization artifact bound to actual bytes.  A fixture cannot grant real
world authority.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from coldguard_ml.w19_no_peeking import (
    FREEZE_FROZEN_APPROVED,
    W19OutcomeExposureError,
    assess_statistical_freeze,
    assert_outcome_blind,
)
from coldguard_ml.w19_pair_ledger import (
    AUTHORIZATION_AUTHORIZED,
    EVIDENCE_PHYSICAL_CAMPAIGN,
    EVIDENCE_SYNTHETIC_FIXTURE,
    FREEZE_STATUS_APPROVED,
    PAIR_VALID,
    W19LedgerError,
    assess_campaign_freeze,
    evaluate_campaign_authorization,
    validate_pair_ledger,
)
from coldguard_ml.w19_progress import (
    TARGET_FROZEN,
    W19ProgressError,
    assess_pair_target,
)

W20_CAMPAIGN_LOCK_LAYER_VERSION = "coldguard-w20-campaign-lock-v1"
CAMPAIGN_METADATA_SCHEMA = "coldguard-w20-campaign-metadata-v1"

BUNDLE_METADATA_ONLY = "METADATA_RECORD_ONLY"
BUNDLE_PHYSICAL = EVIDENCE_PHYSICAL_CAMPAIGN
BUNDLE_SYNTHETIC = EVIDENCE_SYNTHETIC_FIXTURE
BUNDLE_EVIDENCE_CLASSES = frozenset(
    {BUNDLE_METADATA_ONLY, BUNDLE_PHYSICAL, BUNDLE_SYNTHETIC}
)

GROUP_AUTHORIZATION = "A_CAMPAIGN_AUTHORIZATION"
GROUP_PAIR_TARGET = "B_FROZEN_PAIR_TARGET"
GROUP_PAIR_COMPLETION = "C_VALID_PAIR_COMPLETION"
GROUP_STABILITY = "D_HARDWARE_PROTOCOL_STABILITY"
GROUP_SCIENTIFIC_FREEZE = "E_SCIENTIFIC_FREEZE"
GROUP_EXPORT = "F_EXPORT_RAW_INTEGRITY"

GROUP_IDS = (
    GROUP_AUTHORIZATION,
    GROUP_PAIR_TARGET,
    GROUP_PAIR_COMPLETION,
    GROUP_STABILITY,
    GROUP_SCIENTIFIC_FREEZE,
    GROUP_EXPORT,
)

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_UNKNOWN = "UNKNOWN"

ANALYSIS_PREFLIGHT_BLOCKED = "ANALYSIS_PREFLIGHT_BLOCKED"
ANALYSIS_METADATA_READY_PENDING_AUTHORIZATION = (
    "ANALYSIS_METADATA_READY_PENDING_AUTHORIZATION"
)
ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION = (
    "ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION"
)

CLOSEOUT_PAIR_TARGET_NOT_FROZEN = "PAIR_TARGET_NOT_FROZEN"
CLOSEOUT_PAIR_TARGET_NOT_REACHED = "PAIR_TARGET_NOT_REACHED"
CLOSEOUT_PAIR_TARGET_REACHED_PENDING_INTEGRITY = (
    "PAIR_TARGET_REACHED_PENDING_INTEGRITY"
)
CLOSEOUT_CAMPAIGN_LOCK_INCOMPLETE = "CAMPAIGN_LOCK_INCOMPLETE"
CLOSEOUT_CAMPAIGN_LOCK_READY_FOR_EXTERNAL_REVIEW = (
    "CAMPAIGN_LOCK_READY_FOR_EXTERNAL_REVIEW"
)

PROOF_TEST_ONLY = "TEST_ONLY_SOFTWARE_GATE_PROOF"
PROOF_METADATA_ONLY = "METADATA_ONLY_FOR_REAL_CAMPAIGN"
PROOF_PHYSICAL = "PHYSICAL_CAMPAIGN_METADATA"

VERIFICATION_NOT_VERIFIED = "NOT_VERIFIED_EXTERNALLY"
VERIFICATION_VERIFIED_EXTERNAL = "VERIFIED_EXTERNAL"
VERIFICATION_STATUSES = frozenset(
    {VERIFICATION_NOT_VERIFIED, VERIFICATION_VERIFIED_EXTERNAL}
)

BINDING_EMBEDDED = "EMBEDDED_CANONICAL_BYTES"
BINDING_FILE = "VERIFIED_FILE_BYTES"
BINDING_VALUES = frozenset({BINDING_EMBEDDED, BINDING_FILE})

APPROVAL_EFFECT = "NONE_SOFTWARE_ASSESSMENT_ONLY"

PROTECTED_IDENTITIES: tuple[str, ...] = (
    "hardware_config_id",
    "sensor_placement",
    "calibration_id",
    "firmware_version",
    "model_artifact_sha256",
    "model_config_sha256",
    "feature_version",
    "feature_schema_hash",
    "feature_order_sha256",
    "model_calibration_semantics",
    "primary_horizon",
    "critical_target",
    "reactive_threshold_hysteresis",
    "predictive_threshold",
    "warning_persistence",
    "controller_policy_version",
    "cooling_action_magnitude",
    "safety_limits",
    "disturbance_protocol_id",
    "initial_reset_criterion",
    "pair_matching_tolerances",
    "randomization_protocol",
    "analysis_plan_version",
    "primary_outcome",
    "target_pair_count",
)

IDENTITY_OWNERS: Mapping[str, str] = {
    "hardware_config_id": "A",
    "sensor_placement": "A",
    "calibration_id": "A",
    "firmware_version": "A/C",
    "model_artifact_sha256": "B",
    "model_config_sha256": "B",
    "feature_version": "B",
    "feature_schema_hash": "B",
    "feature_order_sha256": "B",
    "model_calibration_semantics": "B",
    "primary_horizon": "B/D",
    "critical_target": "A/B",
    "reactive_threshold_hysteresis": "D",
    "predictive_threshold": "B/D",
    "warning_persistence": "B/D",
    "controller_policy_version": "D",
    "cooling_action_magnitude": "D",
    "safety_limits": "D",
    "disturbance_protocol_id": "A",
    "initial_reset_criterion": "A",
    "pair_matching_tolerances": "A/B",
    "randomization_protocol": "A",
    "analysis_plan_version": "B",
    "primary_outcome": "B",
    "target_pair_count": "TEAM_LEAD",
}

IDENTITY_CANONICAL_REFS: Mapping[str, str] = {
    "hardware_config_id": "03 §34-37, §95-98",
    "sensor_placement": "03 §34-37; 01 §1.5",
    "calibration_id": "03 §35; 01 §18",
    "firmware_version": "03 §92; 05A W20",
    "model_artifact_sha256": "03 §92; 05B §46",
    "model_config_sha256": "03 §92",
    "feature_version": "03 §92; 05B §9",
    "feature_schema_hash": "03 §92; 02 §60.5",
    "feature_order_sha256": "03 §92; 02 §60.5",
    "model_calibration_semantics": "03 §58-60",
    "primary_horizon": "03 §44, §92; 05B §41",
    "critical_target": "03 §42-43",
    "reactive_threshold_hysteresis": "03 §44, §84; 05D",
    "predictive_threshold": "03 §87; 05B §43",
    "warning_persistence": "03 §88; 05B §43",
    "controller_policy_version": "02 §1.6; 04 §11.4",
    "cooling_action_magnitude": "03 §102; 05D",
    "safety_limits": "06; 05D",
    "disturbance_protocol_id": "03 §34-38, §95-98",
    "initial_reset_criterion": "03 §37",
    "pair_matching_tolerances": "03 §35",
    "randomization_protocol": "03 §36",
    "analysis_plan_version": "03 §130-135; 05B §48",
    "primary_outcome": "03 §68-75, §133",
    "target_pair_count": "03 §99-101; 04 W20",
}

# (source kind, key) pairs used to observe a protected identity independently
# of the campaign manifest itself.
IDENTITY_SOURCES: Mapping[str, tuple[tuple[str, str], ...]] = {
    "hardware_config_id": (
        ("attempt", "hardware_config_id"),
        ("campaign_freeze", "hardware_config_id"),
    ),
    "sensor_placement": (("campaign_freeze", "sensor_placement"),),
    "calibration_id": (
        ("attempt", "calibration_id"),
        ("campaign_freeze", "calibration_id"),
    ),
    "firmware_version": (
        ("attempt", "firmware_version"),
        ("campaign_freeze", "firmware_version"),
    ),
    "model_artifact_sha256": (
        ("attempt", "model_artifact_sha256"),
        ("campaign_freeze", "model_artifact_sha256"),
        ("pinned_baseline", "w16_model_artifact_sha256"),
    ),
    "model_config_sha256": (("pinned_baseline", "w18_model_config_sha256"),),
    "feature_version": (
        ("attempt", "feature_version"),
        ("pinned_baseline", "w18_feature_version"),
    ),
    "feature_schema_hash": (
        ("campaign_freeze", "feature_schema_hash"),
        ("pinned_baseline", "w18_feature_schema_hash"),
    ),
    "feature_order_sha256": (
        ("pinned_baseline", "w18_feature_order_sha256"),
    ),
    "model_calibration_semantics": (
        ("pinned_baseline", "w18_calibration_semantics"),
    ),
    "primary_horizon": (("campaign_freeze", "primary_horizon"),),
    "critical_target": (("campaign_freeze", "critical_target"),),
    "reactive_threshold_hysteresis": (("external_d", "reactive_threshold_version"),),
    "predictive_threshold": (("campaign_freeze", "operating_threshold"),),
    "warning_persistence": (("campaign_freeze", "warning_persistence"),),
    "controller_policy_version": (
        ("attempt", "policy_version"),
        ("campaign_freeze", "controller_policy_version"),
    ),
    "cooling_action_magnitude": (("campaign_freeze", "cooling_action_magnitude"),),
    "safety_limits": (("external_d", "safety_limits_version"),),
    "disturbance_protocol_id": (
        ("attempt", "disturbance_protocol_id"),
        ("campaign_freeze", "disturbance_protocol"),
    ),
    "initial_reset_criterion": (
        ("campaign_freeze", "initial_reset_criterion"),
        ("pair_initial_state", "criterion_version"),
    ),
    "pair_matching_tolerances": (("campaign_freeze", "pair_matching_tolerances"),),
    "randomization_protocol": (
        ("campaign_freeze", "randomization_protocol"),
        ("randomization", "status"),
    ),
    "analysis_plan_version": (("ledger", "analysis_plan_version"),),
    "primary_outcome": (
        ("campaign_freeze", "primary_outcome"),
        ("statistical_freeze", "primary_outcome"),
        ("outcome_definition_freeze", "primary_outcome"),
    ),
    "target_pair_count": (
        ("campaign_freeze", "target_pair_count"),
        ("pair_target", "planned_pair_target"),
    ),
}

OUTCOME_DEFINITION_FIELDS: tuple[str, ...] = (
    "primary_outcome",
    "representative_temperature",
    "t_limit_critical_target",
    "recovery_reference_time",
    "recovery_band",
    "recovery_persistence",
    "measurement_coverage_rules",
    "energy_source_admissibility",
    "peak_temperature_basis",
    "time_above_limit_basis",
)

STATISTICAL_UNIT_PAIR = "PAIR"

CHANGE_DECISIONS = frozenset(
    {"COMPARABLE", "POOLABLE_WITH_DECLARED_STRATIFICATION", "INCOMPARABLE"}
)
CHANGE_APPROVER_ROLES = frozenset({"TEAM_LEAD", "MEMBER_A", "MEMBER_D"})

CHANGE_KEYS = frozenset(
    {
        "change_id",
        "identity_id",
        "old_version",
        "new_version",
        "reason",
        "approver",
        "affected_attempts",
        "affected_pairs",
        "comparability_decision",
        "analysis_implications",
    }
)

BUNDLE_KEYS = frozenset(
    {
        "schema",
        "campaign_id",
        "evidence_class",
        "fixture_markers",
        "campaign_manifest",
        "authorization",
        "controller_b_enablement",
        "analysis_execution_authorization",
        "pair_target",
        "target_history",
        "target_freeze_stage",
        "campaign_freeze",
        "statistical_freeze",
        "outcome_definition_freeze",
        "pair_ledger",
        "selection_policy",
        "rematch_history",
        "n_inflation_claims",
        "export",
        "physical_verification",
        "changes",
        "external_links",
        "pinned_baseline",
    }
)
BUNDLE_REQUIRED_KEYS = frozenset(
    {"schema", "campaign_id", "evidence_class", "fixture_markers"}
)

W20_FORBIDDEN_ANALYSIS_KEYS = frozenset(
    {
        "effect_direction",
        "excluded_after_results",
        "selection_by_effect",
        "best_pairs",
        "worst_pairs",
        "post_hoc_selection",
        "significance",
        "significance_flag",
        "headline_p_value",
        "mean_treatment_improvement",
        "bootstrap_ci",
        "paired_effect",
    }
)

FORBIDDEN_RUNTIME_IMPORTS = frozenset(
    {
        "asyncio",
        "http",
        "httpx",
        "mqtt",
        "multiprocessing",
        "paho",
        "requests",
        "scipy",
        "serial",
        "sklearn",
        "socket",
        "ssl",
        "statsmodels",
        "subprocess",
        "urllib",
        "xgboost",
    }
)
FORBIDDEN_CALL_NAMES = frozenset(
    {
        "compute_aiw",
        "compute_branch_energy",
        "compute_ewt",
        "compute_p_value",
        "compute_paired_difference",
        "compute_recovery_time",
        "compute_thermal_exposure",
        "confidence_interval",
        "cumtrapz",
        "dispatch_command",
        "effect_size",
        "fit",
        "integrate",
        "load_outcome_series",
        "open_outcome_series",
        "paired_effect",
        "paired_improvement",
        "predict",
        "publish_command",
        "read_power_series",
        "read_temperature_series",
        "send_command",
        "train",
        "trapezoid",
        "trapz",
    }
)
FORBIDDEN_DEFINITION_PATTERN = re.compile(
    r"^(compute_ewt.*|compute_aiw.*|compute_thermal_exposure.*|compute_recovery.*"
    r"|compute_energy.*|compute_paired.*|compute_p_value.*|compute_confidence.*"
    r"|read_outcome.*|load_outcome.*"
    r"|fit_.*|train_.*|paired_effect|paired_improvement|bootstrap_.*)$"
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class W20EvidenceError(ValueError):
    """Raised for structurally malformed campaign metadata."""


class W20OutcomeAccessError(W19OutcomeExposureError):
    """Raised when a metadata-only route tries to open outcome-shaped bytes."""


@dataclass(frozen=True)
class RequirementRow:
    requirement_id: str
    group: str
    owner: str
    canonical_ref: str
    classification: str
    status: str
    evidence: str
    blocking_consequence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "group": self.group,
            "owner": self.owner,
            "canonical_ref": self.canonical_ref,
            "classification": self.classification,
            "status": self.status,
            "evidence": self.evidence,
            "blocking_consequence": self.blocking_consequence,
        }


@dataclass(frozen=True)
class GroupAssessment:
    group_id: str
    status: str
    reasons: tuple[str, ...]
    rows: tuple[RequirementRow, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "status": self.status,
            "reasons": list(self.reasons),
            "rows": [row.to_dict() for row in self.rows],
        }


@dataclass(frozen=True)
class StabilityAssessment:
    status: str
    reasons: tuple[str, ...]
    identity_rows: tuple[RequirementRow, ...]
    applied_change_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "identity_rows": [row.to_dict() for row in self.identity_rows],
            "applied_change_ids": list(self.applied_change_ids),
        }


@dataclass(frozen=True)
class SelectionAssessment:
    status: str
    rule: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "rule": self.rule,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class CampaignLockAssessment:
    campaign_id: str
    evidence_class: str
    proof_class: str
    groups: tuple[GroupAssessment, ...]
    stability: StabilityAssessment
    selection: SelectionAssessment
    gate_decision: str
    closeout_state: str
    authorization_status: str
    pair_target_status: str
    planned_pair_target: int | None
    counted_valid_pairs: int
    counted_pairs_kind: str
    analysis_authorization_status: str
    refusal_reasons: tuple[str, ...]
    outcome_access: bool = False
    analysis_actions: tuple[str, ...] = ()
    approval_effect: str = APPROVAL_EFFECT

    def group(self, group_id: str) -> GroupAssessment:
        for assessment in self.groups:
            if assessment.group_id == group_id:
                return assessment
        raise KeyError(group_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "evidence_class": self.evidence_class,
            "proof_class": self.proof_class,
            "groups": [group.to_dict() for group in self.groups],
            "stability": self.stability.to_dict(),
            "selection": self.selection.to_dict(),
            "gate_decision": self.gate_decision,
            "closeout_state": self.closeout_state,
            "authorization_status": self.authorization_status,
            "pair_target_status": self.pair_target_status,
            "planned_pair_target": self.planned_pair_target,
            "counted_valid_pairs": self.counted_valid_pairs,
            "counted_pairs_kind": self.counted_pairs_kind,
            "analysis_authorization_status": self.analysis_authorization_status,
            "refusal_reasons": list(self.refusal_reasons),
            "outcome_access": self.outcome_access,
            "analysis_actions": list(self.analysis_actions),
            "approval_effect": self.approval_effect,
        }


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
        ).encode("utf-8")
    ).hexdigest()


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX64.match(value))


def _approval_shape_ok(approval: Any) -> bool:
    return bool(
        isinstance(approval, Mapping)
        and isinstance(approval.get("authority_id"), str)
        and approval.get("authority_id", "").strip()
        and approval.get("authority_role") == "TEAM_LEAD"
        and isinstance(approval.get("canonical_ref"), str)
        and approval.get("canonical_ref", "").strip()
    )


def _is_present(value: Any) -> bool:
    return value not in (None, "", [], {})


def assert_no_analysis_payload(payload: Any, *, context: str = "campaign metadata") -> None:
    """Refuse outcome/effect-shaped input before it reaches the gate."""
    assert_outcome_blind(payload, context=context)
    if isinstance(payload, Mapping):
        for raw_key, value in payload.items():
            key = re.sub(r"[^a-z0-9]+", "_", str(raw_key).strip().lower()).strip("_")
            if key in W20_FORBIDDEN_ANALYSIS_KEYS:
                raise W20EvidenceError(
                    f"{context} contains analysis field {raw_key!r}; the W20 "
                    "campaign gate accepts metadata only"
                )
            assert_no_analysis_payload(value, context=f"{context}.{raw_key}")
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            assert_no_analysis_payload(item, context=f"{context}[{index}]")


def _validate_bundle(evidence: Mapping[str, Any]) -> None:
    if not isinstance(evidence, Mapping):
        raise W20EvidenceError("campaign metadata must be an object")
    unknown = sorted(set(evidence) - BUNDLE_KEYS)
    if unknown:
        raise W20EvidenceError(
            "campaign metadata contains unknown field(s): " + ", ".join(unknown)
        )
    missing = sorted(BUNDLE_REQUIRED_KEYS - set(evidence))
    if missing:
        raise W20EvidenceError(
            "campaign metadata lacks required field(s): " + ", ".join(missing)
        )
    if evidence["schema"] != CAMPAIGN_METADATA_SCHEMA:
        raise W20EvidenceError(
            f"unsupported campaign metadata schema {evidence['schema']!r}; "
            f"expected {CAMPAIGN_METADATA_SCHEMA!r}"
        )
    if evidence["evidence_class"] not in BUNDLE_EVIDENCE_CLASSES:
        raise W20EvidenceError(
            "evidence_class must be one of " + ", ".join(sorted(BUNDLE_EVIDENCE_CLASSES))
        )
    markers = evidence["fixture_markers"]
    if not isinstance(markers, list) or any(not isinstance(m, str) for m in markers):
        raise W20EvidenceError("fixture_markers must be a list of strings")
    if evidence["evidence_class"] == BUNDLE_SYNTHETIC and not markers:
        raise W20EvidenceError(
            "a synthetic metadata bundle must carry permanent fixture markers"
        )
    if evidence["evidence_class"] != BUNDLE_SYNTHETIC and markers:
        raise W20EvidenceError(
            "fixture markers may appear only on a synthetic metadata bundle"
        )


def _row(
    requirement_id: str,
    group: str,
    owner: str,
    canonical_ref: str,
    classification: str,
    status: str,
    evidence: str,
    consequence: str,
) -> RequirementRow:
    return RequirementRow(
        requirement_id=requirement_id,
        group=group,
        owner=owner,
        canonical_ref=canonical_ref,
        classification=classification,
        status=status,
        evidence=evidence,
        blocking_consequence=consequence,
    )


def _group(group_id: str, rows: Sequence[RequirementRow]) -> GroupAssessment:
    reasons = tuple(
        f"{row.requirement_id}:{row.evidence}"
        for row in rows
        if row.status in {STATUS_FAIL, STATUS_UNKNOWN}
    )
    statuses = {row.status for row in rows}
    if STATUS_FAIL in statuses:
        status = STATUS_FAIL
    elif STATUS_UNKNOWN in statuses:
        status = STATUS_UNKNOWN
    else:
        status = STATUS_PASS
    return GroupAssessment(group_id=group_id, status=status, reasons=reasons, rows=tuple(rows))


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except (W19LedgerError, W19ProgressError, ValueError) as exc:
        return None, str(exc)


def _assess_authorization(
    evidence: Mapping[str, Any], manifest: Mapping[str, Any] | None
) -> GroupAssessment:
    rows: list[RequirementRow] = []
    block = "analysis preflight remains blocked"
    section = evidence.get("authorization")
    if section is None:
        rows.append(
            _row(
                "A1", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137; 04 W20; 05B §48",
                "TEAM_DEPENDENCY", STATUS_FAIL, "AUTHORIZATION_RECORD_MISSING", block,
            )
        )
        rows.append(
            _row(
                "A5", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §133; 04 W20",
                "TEAM_DEPENDENCY", STATUS_FAIL, "APPROVED_FREEZE_VERSION_MISSING", block,
            )
        )
        rows.append(
            _row(
                "A4", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137",
                "TEAM_DEPENDENCY", STATUS_FAIL, "REVIEW_AUTHORITY_MISSING", block,
            )
        )
        rows.append(
            _row(
                "A6", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137; 05D",
                "TEAM_DEPENDENCY", STATUS_FAIL, "CONTROLLER_B_ENABLEMENT_MISSING", block,
            )
        )
        return _group(GROUP_AUTHORIZATION, rows)
    if not isinstance(section, Mapping):
        raise W20EvidenceError("authorization section must be an object")
    record = section.get("record")
    assessment, error = _safe_call(evaluate_campaign_authorization, record)
    if error is not None:
        rows.append(
            _row(
                "A1", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137; 04 W20; 05B §48",
                "CANONICAL", STATUS_FAIL, f"AUTHORIZATION_RECORD_MALFORMED:{error}", block,
            )
        )
    elif assessment is None or assessment.status != AUTHORIZATION_AUTHORIZED:
        status = assessment.status if assessment is not None else "MISSING"
        reasons = ";".join(assessment.refusal_reasons) if assessment else "NO_RECORD"
        rows.append(
            _row(
                "A1", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137; 04 W20; 05B §48",
                "CANONICAL", STATUS_FAIL,
                f"AUTHORIZATION_STATUS={status};{reasons or 'NO_REFUSAL_DETAIL'}", block,
            )
        )
        if assessment is not None and assessment.status == "FAKE_APPROVAL_DETECTED":
            rows.append(
                _row(
                    "A2", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137",
                    "CANONICAL", STATUS_FAIL, "FAKE_APPROVAL_METADATA", block,
                )
            )
    else:
        rows.append(
            _row(
                "A1", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137; 04 W20; 05B §48",
                "CANONICAL", STATUS_PASS,
                f"AUTHORIZATION_STATUS={assessment.status};authority={assessment.authority_id}",
                "none",
            )
        )
        rows.append(
            _row(
                "A2", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137",
                "CANONICAL", STATUS_PASS,
                "G4_READY;PAIR_TARGET_FROZEN;ANALYSIS_FREEZE_ACCEPTED",
                "none",
            )
        )
    if isinstance(manifest, Mapping):
        if section.get("campaign_id") == evidence.get("campaign_id"):
            rows.append(
                _row(
                    "A3a", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137",
                    "CANONICAL", STATUS_PASS, "AUTHORIZED_CAMPAIGN_IDENTIFIER_MATCHES", "none",
                )
            )
        else:
            rows.append(
                _row(
                    "A3a", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137",
                    "CANONICAL", STATUS_FAIL, "AUTHORIZED_CAMPAIGN_IDENTIFIER_MISMATCH", block,
                )
            )
        if section.get("approved_freeze_version") == manifest.get("freeze_version"):
            rows.append(
                _row(
                    "A5", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §133; 04 W20",
                    "CANONICAL", STATUS_PASS, "APPROVED_FREEZE_VERSION_MATCHES", "none",
                )
            )
        else:
            rows.append(
                _row(
                    "A5", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §133; 04 W20",
                    "CANONICAL", STATUS_FAIL, "APPROVED_FREEZE_VERSION_MISMATCH", block,
                )
            )
    else:
        rows.append(
            _row(
                "A3a", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137",
                "CANONICAL", STATUS_FAIL, "CAMPAIGN_MANIFEST_MISSING", block,
            )
        )
        rows.append(
            _row(
                "A5", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §133; 04 W20",
                "CANONICAL", STATUS_FAIL, "APPROVED_FREEZE_VERSION_UNVERIFIABLE", block,
            )
        )
    if (
        isinstance(section.get("review_authority_id"), str)
        and section.get("review_authority_id", "").strip()
        and section.get("review_authority_role") == "TEAM_LEAD"
    ):
        rows.append(
            _row(
                "A4", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137",
                "CANONICAL", STATUS_PASS, "REVIEW_AUTHORITY_RECORDED", "none",
            )
        )
    else:
        rows.append(
            _row(
                "A4", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137",
                "CANONICAL", STATUS_FAIL, "REVIEW_AUTHORITY_MISSING", block,
            )
        )
    if evidence.get("evidence_class") == BUNDLE_PHYSICAL:
        external = evidence.get("external_links")
        w18_g4 = external.get("w18_g4") if isinstance(external, Mapping) else None
        record_g4 = record.get("g4_status") if isinstance(record, Mapping) else None
        if w18_g4 is None:
            rows.append(
                _row(
                    "A8", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137; 04 W20",
                    "CANONICAL", STATUS_FAIL, "G4_EVIDENCE_MISSING", block,
                )
            )
        elif record_g4 != w18_g4:
            rows.append(
                _row(
                    "A8", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137; 04 W20",
                    "CANONICAL", STATUS_FAIL,
                    f"G4_STATUS_DISAGREES_WITH_W18_EVIDENCE:{record_g4}!={w18_g4}", block,
                )
            )
        else:
            rows.append(
                _row(
                    "A8", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137; 04 W20",
                    "CANONICAL", STATUS_PASS, "G4_MATCHES_W18_EVIDENCE", "none",
                )
            )
    else:
        rows.append(
            _row(
                "A8", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137; 04 W20",
                "IMPLEMENTATION_CHOICE", STATUS_PASS,
                "TEST_FIXTURE_G4_IS_NOT_REAL_EVIDENCE", "none",
            )
        )
    enablement = evidence.get("controller_b_enablement")
    if (
        isinstance(enablement, Mapping)
        and enablement.get("status") == "APPROVED"
        and _approval_shape_ok(enablement.get("approver"))
    ):
        rows.append(
            _row(
                "A6", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137; 05D",
                "TEAM_DEPENDENCY", STATUS_PASS,
                "CONTROLLER_B_ENABLEMENT_METADATA_SHAPE_OK", "none",
            )
        )
    else:
        rows.append(
            _row(
                "A6", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137; 05D",
                "TEAM_DEPENDENCY", STATUS_FAIL, "CONTROLLER_B_ENABLEMENT_WITHHELD", block,
            )
        )
    if section.get("verification_status") in VERIFICATION_STATUSES:
        rows.append(
            _row(
                "A7", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137",
                "IMPLEMENTATION_CHOICE", STATUS_PASS,
                f"AUTHORITY_VERIFICATION={section.get('verification_status')}", "none",
            )
        )
    else:
        rows.append(
            _row(
                "A7", GROUP_AUTHORIZATION, "TEAM_LEAD", "03 §137",
                "IMPLEMENTATION_CHOICE", STATUS_FAIL,
                "AUTHORITY_VERIFICATION_STATUS_UNKNOWN", block,
            )
        )
    return _group(GROUP_AUTHORIZATION, rows)


def _assess_pair_target(
    evidence: Mapping[str, Any], manifest: Mapping[str, Any] | None
) -> tuple[GroupAssessment, Any]:
    rows: list[RequirementRow] = []
    block = "analysis preflight remains blocked"
    record = evidence.get("pair_target")
    target, error = _safe_call(assess_pair_target, record)
    if error is not None:
        rows.append(
            _row(
                "B1", GROUP_PAIR_TARGET, "TEAM_LEAD", "03 §99-101; 04 W20",
                "CANONICAL", STATUS_FAIL, f"PAIR_TARGET_MALFORMED:{error}", block,
            )
        )
        return _group(GROUP_PAIR_TARGET, rows), target
    if target is None or target.status != TARGET_FROZEN:
        reasons = ";".join(target.refusal_reasons) if target else "NO_TARGET"
        rows.append(
            _row(
                "B1", GROUP_PAIR_TARGET, "TEAM_LEAD", "03 §99-101; 04 W20",
                "CANONICAL", STATUS_FAIL,
                f"PAIR_TARGET_STATUS={target.status if target else 'MISSING'};{reasons}", block,
            )
        )
        return _group(GROUP_PAIR_TARGET, rows), target
    rows.append(
        _row(
            "B1", GROUP_PAIR_TARGET, "TEAM_LEAD", "03 §99-101; 04 W20",
            "CANONICAL", STATUS_PASS,
            f"PAIR_TARGET={target.planned_pair_target}", "none",
        )
    )
    if isinstance(record, Mapping) and record.get("variance_justification_ref"):
        rows.append(
            _row(
                "B4", GROUP_PAIR_TARGET, "B/TEAM_LEAD", "03 §99-101",
                "CANONICAL", STATUS_PASS, "SAMPLE_SIZE_JUSTIFICATION_PRESENT", "none",
            )
        )
    else:
        rows.append(
            _row(
                "B4", GROUP_PAIR_TARGET, "B/TEAM_LEAD", "03 §99-101",
                "CANONICAL", STATUS_FAIL, "SAMPLE_SIZE_JUSTIFICATION_MISSING", block,
            )
        )
    stage = evidence.get("target_freeze_stage")
    if stage == "BEFORE_CAMPAIGN_START":
        rows.append(
            _row(
                "B3", GROUP_PAIR_TARGET, "TEAM_LEAD", "03 §99-101, §163",
                "CANONICAL", STATUS_PASS, "TARGET_FROZEN_BEFORE_CAMPAIGN_START", "none",
            )
        )
    else:
        rows.append(
            _row(
                "B3", GROUP_PAIR_TARGET, "TEAM_LEAD", "03 §99-101, §163",
                "CANONICAL", STATUS_FAIL, f"TARGET_FREEZE_STAGE={stage or 'MISSING'}", block,
            )
        )
    manifest_ok = isinstance(manifest, Mapping)
    if manifest_ok and manifest.get("target_record_sha256") == canonical_sha256(record):
        rows.append(
            _row(
                "B2", GROUP_PAIR_TARGET, "TEAM_LEAD", "03 §99-101",
                "CANONICAL", STATUS_PASS, "TARGET_RECORD_DIGEST_BOUND", "none",
            )
        )
    else:
        rows.append(
            _row(
                "B2", GROUP_PAIR_TARGET, "TEAM_LEAD", "03 §99-101",
                "CANONICAL", STATUS_FAIL, "TARGET_RECORD_DIGEST_UNBOUND_OR_CHANGED", block,
            )
        )
    history = evidence.get("target_history")
    no_silent_change = True
    history_evidence = "NO_TARGET_CHANGE_RECORD"
    if history is not None and not isinstance(history, list):
        no_silent_change = False
        history_evidence = "TARGET_HISTORY_MALFORMED"
    elif isinstance(history, list) and history:
        for entry in history:
            if not isinstance(entry, Mapping):
                no_silent_change = False
                history_evidence = "TARGET_HISTORY_MALFORMED"
                break
            if entry.get("pairs_recorded_when_changed") not in (0, None):
                no_silent_change = False
                history_evidence = "TARGET_CHANGED_AFTER_ATTEMPTS_STARTED"
                break
            if not _approval_shape_ok(entry.get("approved_by")):
                no_silent_change = False
                history_evidence = "TARGET_CHANGE_APPROVAL_INVALID"
                break
        if no_silent_change:
            newest = history[-1].get("target_record_sha256")
            if newest != canonical_sha256(record):
                no_silent_change = False
                history_evidence = "TARGET_CHANGED_AFTER_FREEZE"
            else:
                history_evidence = "TARGET_CHANGE_HISTORY_CONSISTENT"
    rows.append(
        _row(
            "B5", GROUP_PAIR_TARGET, "TEAM_LEAD", "03 §99-101, §163",
            "CANONICAL", STATUS_PASS if no_silent_change else STATUS_FAIL,
            history_evidence, "none" if no_silent_change else block,
        )
    )
    return _group(GROUP_PAIR_TARGET, rows), target


def _assess_selection(evidence: Mapping[str, Any]) -> SelectionAssessment:
    policy = evidence.get("selection_policy")
    if not isinstance(policy, Mapping):
        return SelectionAssessment(
            status=STATUS_FAIL,
            rule="MISSING",
            reasons=("SELECTION_POLICY_MISSING",),
        )
    rule = policy.get("rule")
    reasons: list[str] = []
    if rule != "ALL_PREDECLARED":
        reasons.append("SELECTION_RULE_NOT_PREDECLARED")
    exclusions = policy.get("exclusions")
    if exclusions is None:
        exclusions = []
    if not isinstance(exclusions, list):
        reasons.append("SELECTION_EXCLUSIONS_MALFORMED")
    else:
        for entry in exclusions:
            if not isinstance(entry, Mapping):
                reasons.append("SELECTION_EXCLUSION_MALFORMED")
                continue
            if entry.get("predeclared") is not True:
                reasons.append("PAIR_EXCLUDED_WITHOUT_PREDECLARED_RULE")
            if not _is_present(entry.get("reason_code")):
                reasons.append("PAIR_EXCLUSION_REASON_MISSING")
    if isinstance(evidence.get("rematch_history"), list) and evidence["rematch_history"]:
        reasons.append("POST_HOC_REMATCH_RECORDED")
    return SelectionAssessment(
        status=STATUS_FAIL if reasons else STATUS_PASS,
        rule=str(rule),
        reasons=tuple(sorted(set(reasons))),
    )


def _attempts_from_ledger(ledger: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(ledger, Mapping):
        return []
    attempts = ledger.get("attempts")
    if not isinstance(attempts, list):
        return []
    return [attempt for attempt in attempts if isinstance(attempt, Mapping)]


def _ledger_binding_row(
    evidence: Mapping[str, Any],
    ledger: Mapping[str, Any],
    *,
    requirement_id: str,
    group_id: str,
    owner: str,
    canonical_ref: str,
    label: str,
    ledger_key: str,
    bundle_key: str,
) -> RequirementRow:
    ledger_value = ledger.get(ledger_key)
    bundle_value = evidence.get(bundle_key)
    bound = canonical_sha256(ledger_value) == canonical_sha256(bundle_value)
    return _row(
        requirement_id,
        group_id,
        owner,
        canonical_ref,
        "CANONICAL",
        STATUS_PASS if bound else STATUS_FAIL,
        f"{label}={'BOUND' if bound else 'MISMATCH'}",
        "none" if bound else "analysis preflight remains blocked",
    )


def _ledger_binding_rows(
    evidence: Mapping[str, Any], ledger: Mapping[str, Any] | None
) -> dict[str, RequirementRow]:
    if not isinstance(ledger, Mapping):
        return {}
    return {
        GROUP_AUTHORIZATION: _ledger_binding_row(
            evidence,
            ledger,
            requirement_id="A3b",
            group_id=GROUP_AUTHORIZATION,
            owner="TEAM_LEAD",
            canonical_ref="03 §137; 05B §48",
            label="LEDGER_CAMPAIGN_IDENTITY",
            ledger_key="campaign_id",
            bundle_key="campaign_id",
        ),
        GROUP_PAIR_TARGET: _ledger_binding_row(
            evidence,
            ledger,
            requirement_id="B6",
            group_id=GROUP_PAIR_TARGET,
            owner="TEAM_LEAD",
            canonical_ref="03 §99-101",
            label="LEDGER_FROZEN_TARGET",
            ledger_key="frozen_target",
            bundle_key="pair_target",
        ),
        GROUP_SCIENTIFIC_FREEZE: _ledger_binding_row(
            evidence,
            ledger,
            requirement_id="E4",
            group_id=GROUP_SCIENTIFIC_FREEZE,
            owner="TEAM_LEAD",
            canonical_ref="03 §130-135; 05B §48",
            label="LEDGER_STATISTICAL_FREEZE",
            ledger_key="statistical_freeze",
            bundle_key="statistical_freeze",
        ),
    }


def _ledger_campaign_freeze_row(
    evidence: Mapping[str, Any], ledger: Mapping[str, Any] | None
) -> RequirementRow | None:
    if not isinstance(ledger, Mapping):
        return None
    return _ledger_binding_row(
        evidence,
        ledger,
        requirement_id="E0b",
        group_id=GROUP_SCIENTIFIC_FREEZE,
        owner="TEAM_LEAD",
        canonical_ref="03 §133; 04 W20",
        label="LEDGER_CAMPAIGN_FREEZE",
        ledger_key="campaign_freeze",
        bundle_key="campaign_freeze",
    )


def _append_binding(
    group: GroupAssessment, extra: Sequence[RequirementRow]
) -> GroupAssessment:
    if not extra:
        return group
    return _group(group.group_id, tuple(group.rows) + tuple(extra))


def _observed_identity_values(
    identity_id: str,
    evidence: Mapping[str, Any],
    ledger: Mapping[str, Any] | None,
    validation: Any,
    freeze_values: Mapping[str, Any],
    statistical_fields: Mapping[str, Any],
    outcome_fields: Mapping[str, Any],
) -> list[tuple[str, str, Any]]:
    observations: list[tuple[str, str, Any]] = []
    attempts = _attempts_from_ledger(ledger)
    selected_ids: set[str] = set()
    if validation is not None:
        for pair in validation.pairs:
            if pair.status == PAIR_VALID:
                selected_ids.update(
                    attempt_id
                    for attempt_id in pair.selected_attempts.values()
                    if attempt_id is not None
                )
    accepted = [a for a in attempts if not selected_ids or a.get("attempt_id") in selected_ids]
    pinned = evidence.get("pinned_baseline")
    external = evidence.get("external_links")
    pair_target = evidence.get("pair_target")
    for kind, key in IDENTITY_SOURCES.get(identity_id, ()):
        if kind == "attempt":
            for attempt in accepted:
                if identity_id in {
                    "model_artifact_sha256",
                    "controller_policy_version",
                    "feature_version",
                } and attempt.get("controller_arm") != "B":
                    continue
                value = attempt.get(key)
                if _is_present(value):
                    observations.append(("attempt", str(attempt.get("attempt_id")), value))
        elif kind == "campaign_freeze":
            value = freeze_values.get(key)
            if _is_present(value):
                observations.append(("campaign_freeze", key, value))
        elif kind == "statistical_freeze":
            value = statistical_fields.get(key)
            if _is_present(value):
                observations.append(("statistical_freeze", key, value))
        elif kind == "outcome_definition_freeze":
            value = outcome_fields.get(key)
            if _is_present(value):
                observations.append(("outcome_definition_freeze", key, value))
        elif kind == "ledger":
            value = ledger.get(key) if isinstance(ledger, Mapping) else None
            if _is_present(value):
                observations.append(("ledger", key, value))
        elif kind == "pair_initial_state":
            if isinstance(ledger, Mapping):
                pairs = ledger.get("pairs")
                if isinstance(pairs, list):
                    for pair in pairs:
                        if not isinstance(pair, Mapping):
                            continue
                        initial = pair.get("initial_state")
                        if isinstance(initial, Mapping) and _is_present(initial.get(key)):
                            observations.append(
                                ("pair_initial_state", str(pair.get("pair_id")), initial[key])
                            )
        elif kind == "randomization":
            if isinstance(ledger, Mapping):
                randomization = ledger.get("randomization")
                if isinstance(randomization, Mapping) and _is_present(randomization.get(key)):
                    observations.append(("randomization", key, randomization[key]))
        elif kind == "pair_target":
            if isinstance(pair_target, Mapping) and _is_present(pair_target.get(key)):
                observations.append(("pair_target", key, pair_target[key]))
        elif kind == "pinned_baseline":
            if isinstance(pinned, Mapping) and _is_present(pinned.get(key)):
                observations.append(("pinned_baseline", key, pinned[key]))
        elif kind == "external_d":
            if isinstance(external, Mapping):
                d_record = external.get("d_policy_freeze")
                if isinstance(d_record, Mapping) and _is_present(d_record.get(key)):
                    observations.append(("external_d", key, d_record[key]))
    return observations


def _change_for_identity(
    identity_id: str, evidence: Mapping[str, Any]
) -> tuple[Mapping[str, Any] | None, tuple[str, ...]]:
    changes = evidence.get("changes")
    if not isinstance(changes, list):
        return None, ("CHANGE_RECORD_MALFORMED",)
    found: list[Mapping[str, Any]] = []
    problems: list[str] = []
    for entry in changes:
        if not isinstance(entry, Mapping):
            problems.append("CHANGE_RECORD_MALFORMED")
            continue
        if entry.get("identity_id") != identity_id:
            continue
        found.append(entry)
        unknown = sorted(set(entry) - CHANGE_KEYS)
        missing = sorted(CHANGE_KEYS - set(entry))
        if unknown or missing:
            problems.append("CHANGE_CONTROL_FIELDS_INCOMPLETE")
            continue
        if not _approval_shape_ok(entry.get("approver")) or entry.get(
            "approver", {}
        ).get("authority_role") not in CHANGE_APPROVER_ROLES:
            problems.append("CHANGE_APPROVER_NOT_AUTHORIZED")
        if entry.get("comparability_decision") not in CHANGE_DECISIONS:
            problems.append("CHANGE_COMPARABILITY_DECISION_INVALID")
        elif entry.get("comparability_decision") == "INCOMPARABLE":
            problems.append("CHANGE_DECLARED_INCOMPARABLE")
        if not _is_present(entry.get("analysis_implications")):
            problems.append("CHANGE_ANALYSIS_IMPLICATIONS_MISSING")
    if not found:
        return None, tuple(sorted(set(problems))) or ("NO_CHANGE_RECORD_FOR_DRIFT",)
    return found[0], tuple(sorted(set(problems)))


def _assess_stability(
    evidence: Mapping[str, Any],
    manifest: Mapping[str, Any] | None,
    ledger: Mapping[str, Any] | None,
    validation: Any,
    freeze_values: Mapping[str, Any],
    statistical_fields: Mapping[str, Any],
    outcome_fields: Mapping[str, Any],
) -> StabilityAssessment:
    rows: list[RequirementRow] = []
    applied: list[str] = []
    reasons: list[str] = []
    if not isinstance(manifest, Mapping):
        for identity_id in PROTECTED_IDENTITIES:
            rows.append(
                _row(
                    f"D:{identity_id}",
                    GROUP_STABILITY,
                    IDENTITY_OWNERS[identity_id],
                    IDENTITY_CANONICAL_REFS[identity_id],
                    "CANONICAL",
                    STATUS_FAIL,
                    "CAMPAIGN_MANIFEST_MISSING",
                    "analysis preflight remains blocked",
                )
            )
        return StabilityAssessment(
            status=STATUS_FAIL,
            reasons=("CAMPAIGN_MANIFEST_MISSING",),
            identity_rows=tuple(rows),
            applied_change_ids=(),
        )
    identities = manifest.get("identities")
    if not isinstance(identities, Mapping):
        identities = {}
    for identity_id in PROTECTED_IDENTITIES:
        expected = identities.get(identity_id)
        if not _is_present(expected):
            rows.append(
                _row(
                    f"D:{identity_id}",
                    GROUP_STABILITY,
                    IDENTITY_OWNERS[identity_id],
                    IDENTITY_CANONICAL_REFS[identity_id],
                    "CANONICAL",
                    STATUS_FAIL,
                    "MANIFEST_IDENTITY_MISSING",
                    "analysis preflight remains blocked",
                )
            )
            reasons.append(f"{identity_id}:MANIFEST_IDENTITY_MISSING")
            continue
        observations = _observed_identity_values(
            identity_id,
            evidence,
            ledger,
            validation,
            freeze_values,
            statistical_fields,
            outcome_fields,
        )
        if not observations:
            rows.append(
                _row(
                    f"D:{identity_id}",
                    GROUP_STABILITY,
                    IDENTITY_OWNERS[identity_id],
                    IDENTITY_CANONICAL_REFS[identity_id],
                    "CANONICAL",
                    STATUS_UNKNOWN,
                    "INDEPENDENT_SOURCE_MISSING",
                    "analysis preflight remains blocked",
                )
            )
            reasons.append(f"{identity_id}:INDEPENDENT_SOURCE_MISSING")
            continue
        expected_hash = canonical_sha256(expected)
        mismatches = [
            (source_kind, provenance, value)
            for source_kind, provenance, value in observations
            if canonical_sha256(value) != expected_hash
        ]
        if not mismatches:
            rows.append(
                _row(
                    f"D:{identity_id}",
                    GROUP_STABILITY,
                    IDENTITY_OWNERS[identity_id],
                    IDENTITY_CANONICAL_REFS[identity_id],
                    "CANONICAL",
                    STATUS_PASS,
                    "OBSERVED_SOURCES="
                    + ",".join(sorted({kind for kind, _, _ in observations})),
                    "none",
                )
            )
            continue
        change, problems = _change_for_identity(identity_id, evidence)
        if change is None or problems:
            status = STATUS_FAIL
            detail = "DRIFT_UNRESOLVED:" + ",".join(
                sorted({kind for kind, _, _ in mismatches})
            )
            if problems:
                detail += "; " + ";".join(problems)
            reasons.append(f"{identity_id}:{detail}")
        else:
            affected_attempts = change.get("affected_attempts")
            affected_ok = isinstance(affected_attempts, list) and (
                "*" in affected_attempts
                or all(
                    provenance in affected_attempts
                    for kind, provenance, _ in mismatches
                    if kind == "attempt"
                )
            )
            if not affected_ok:
                status = STATUS_FAIL
                detail = "CHANGE_SCOPE_MISMATCH"
                reasons.append(f"{identity_id}:{detail}")
            else:
                status = STATUS_PASS
                detail = f"CHANGE_RECORD_APPLIED:{change.get('change_id')}"
                applied.append(str(change.get("change_id")))
        rows.append(
            _row(
                f"D:{identity_id}",
                GROUP_STABILITY,
                IDENTITY_OWNERS[identity_id],
                IDENTITY_CANONICAL_REFS[identity_id],
                "CANONICAL",
                status,
                detail,
                "none" if status == STATUS_PASS else "analysis preflight remains blocked",
            )
        )
    statuses = {row.status for row in rows}
    if STATUS_FAIL in statuses:
        status = STATUS_FAIL
    elif STATUS_UNKNOWN in statuses:
        status = STATUS_UNKNOWN
    else:
        status = STATUS_PASS
    return StabilityAssessment(
        status=status,
        reasons=tuple(sorted(set(reasons))),
        identity_rows=tuple(rows),
        applied_change_ids=tuple(sorted(set(applied))),
    )


def _assess_pair_completion(
    evidence: Mapping[str, Any],
    manifest: Mapping[str, Any] | None,
    ledger: Mapping[str, Any] | None,
    validation: Any,
    ledger_error: str | None,
    target: Any,
    selection: SelectionAssessment,
) -> tuple[GroupAssessment, int, str]:
    rows: list[RequirementRow] = []
    block = "analysis preflight remains blocked"
    counted = 0
    kind = "NONE"
    if ledger_error is not None:
        rows.append(
            _row(
                "C1", GROUP_PAIR_COMPLETION, "B", "03 §95-98; 05B §47",
                "CANONICAL", STATUS_FAIL, f"LEDGER_STRUCTURE_INVALID:{ledger_error}", block,
            )
        )
        return _group(GROUP_PAIR_COMPLETION, rows), counted, kind
    if ledger is None or validation is None:
        rows.append(
            _row(
                "C1", GROUP_PAIR_COMPLETION, "B", "03 §95-98; 05B §47",
                "CANONICAL", STATUS_FAIL, "PAIR_LEDGER_MISSING", block,
            )
        )
        return _group(GROUP_PAIR_COMPLETION, rows), counted, kind
    bundle_class = evidence.get("evidence_class")
    ledger_class = validation.evidence_class
    expected_class = (
        EVIDENCE_PHYSICAL_CAMPAIGN
        if bundle_class == BUNDLE_PHYSICAL
        else EVIDENCE_SYNTHETIC_FIXTURE
    )
    rows.append(
        _row(
            "C0", GROUP_PAIR_COMPLETION, "B", "03 §95-98, §158-163",
            "CANONICAL",
            STATUS_PASS if validation.ledger_integrity_ok else STATUS_FAIL,
            "LEDGER_REFUSAL_REASONS="
            + (",".join(validation.refusal_reasons) or "NONE"),
            "none" if validation.ledger_integrity_ok else block,
        )
    )
    if ledger_class == expected_class:
        rows.append(
            _row(
                "C1a", GROUP_PAIR_COMPLETION, "B", "03 §95-98; 05B §47",
                "CANONICAL", STATUS_PASS, f"LEDGER_EVIDENCE_CLASS={ledger_class}", "none",
            )
        )
    else:
        rows.append(
            _row(
                "C1a", GROUP_PAIR_COMPLETION, "B", "03 §95-98; 05B §47",
                "CANONICAL", STATUS_FAIL,
                f"LEDGER_EVIDENCE_CLASS_MISMATCH:{ledger_class}!={expected_class}", block,
            )
        )
    if bundle_class == BUNDLE_PHYSICAL:
        counted = validation.physical_valid_pairs
        kind = "PHYSICAL_VALID_PAIRS"
    elif bundle_class == BUNDLE_SYNTHETIC:
        counted = validation.software_valid_pairs
        kind = "SOFTWARE_VALID_PAIRS_TEST_ONLY"
    else:
        rows.append(
            _row(
                "C1b", GROUP_PAIR_COMPLETION, "B", "03 §95-98",
                "DERIVED", STATUS_FAIL, "METADATA_ONLY_BUNDLE_HAS_NO_PAIR_EVIDENCE", block,
            )
        )
    if isinstance(manifest, Mapping):
        pairs_payload = ledger.get("pairs") if isinstance(ledger, Mapping) else None
        ledger_pair_ids = {
            str(pair.get("pair_id"))
            for pair in pairs_payload or []
            if isinstance(pair, Mapping)
        }
        registered = manifest.get("registered_pair_ids")
        registered_ok = isinstance(registered, list) and set(map(str, registered)) == (
            ledger_pair_ids
        )
        rows.append(
            _row(
                "C3a", GROUP_PAIR_COMPLETION, "B", "03 §95-98",
                "CANONICAL", STATUS_PASS if registered_ok else STATUS_FAIL,
                "REGISTERED_PAIR_ROSTER_MATCHES" if registered_ok else "PAIR_ROSTER_MISMATCH",
                "none" if registered_ok else block,
            )
        )
        attempts = _attempts_from_ledger(ledger)
        ledger_attempt_ids = {str(a.get("attempt_id")) for a in attempts}
        registered_attempts = manifest.get("registered_attempt_ids")
        attempts_ok = (
            isinstance(registered_attempts, list)
            and set(map(str, registered_attempts)) == ledger_attempt_ids
        )
        rows.append(
            _row(
                "C4", GROUP_PAIR_COMPLETION, "B", "03 §95-98, §158-163",
                "CANONICAL", STATUS_PASS if attempts_ok else STATUS_FAIL,
                "ATTEMPT_HISTORY_COMPLETE" if attempts_ok else "ATTEMPT_HISTORY_MISMATCH",
                "none" if attempts_ok else block,
            )
        )
        if manifest.get("statistical_unit") == STATISTICAL_UNIT_PAIR:
            rows.append(
                _row(
                    "C9", GROUP_PAIR_COMPLETION, "B", "03 §47, §95-98",
                    "CANONICAL", STATUS_PASS, "STATISTICAL_UNIT=PAIR", "none",
                )
            )
        else:
            rows.append(
                _row(
                    "C9", GROUP_PAIR_COMPLETION, "B", "03 §47, §95-98",
                    "CANONICAL", STATUS_FAIL, "STATISTICAL_UNIT_NOT_PAIR", block,
                )
            )
    else:
        rows.append(
            _row(
                "C3a", GROUP_PAIR_COMPLETION, "B", "03 §95-98",
                "CANONICAL", STATUS_FAIL, "CAMPAIGN_MANIFEST_MISSING", block,
            )
        )
        rows.append(
            _row(
                "C4", GROUP_PAIR_COMPLETION, "B", "03 §95-98, §158-163",
                "CANONICAL", STATUS_FAIL, "ATTEMPT_HISTORY_UNVERIFIABLE", block,
            )
        )
        rows.append(
            _row(
                "C9", GROUP_PAIR_COMPLETION, "B", "03 §47, §95-98",
                "CANONICAL", STATUS_FAIL, "STATISTICAL_UNIT_UNVERIFIABLE", block,
            )
        )
    invalid_attempts = validation.attempt_accounting.invalid_attempts
    aborted = validation.attempt_accounting.aborted_attempts
    rows.append(
        _row(
            "C5", GROUP_PAIR_COMPLETION, "B", "03 §158-163; 05B §47",
            "CANONICAL", STATUS_PASS,
            f"INVALID_ATTEMPTS_RETAINED={invalid_attempts};ABORTED_RETAINED={aborted}",
            "none",
        )
    )
    rows.append(
        _row(
            "C6", GROUP_PAIR_COMPLETION, "B", "03 §98; 05B §47",
            "CANONICAL", STATUS_PASS, "RERUN_RULE_ENFORCED_BY_W19_LEDGER", "none",
        )
    )
    if target is not None and target.status == TARGET_FROZEN and target.planned_pair_target:
        reached = counted >= target.planned_pair_target
        rows.append(
            _row(
                "C7", GROUP_PAIR_COMPLETION, "B", "03 §99-101",
                "CANONICAL", STATUS_PASS if reached else STATUS_FAIL,
                f"VALID_PAIRS={counted};TARGET={target.planned_pair_target}", block,
            )
        )
    else:
        rows.append(
            _row(
                "C7", GROUP_PAIR_COMPLETION, "B", "03 §99-101",
                "CANONICAL", STATUS_FAIL, "PAIR_TARGET_NOT_FROZEN", block,
            )
        )
    rows.append(
        _row(
            "C8", GROUP_PAIR_COMPLETION, "B", "03 §47, §95-98",
            "DERIVED", STATUS_PASS, "ONE_PAIR_CONTRIBUTES_AT_MOST_ONE_OBSERVATION", "none",
        )
    )
    inflation_claims = evidence.get("n_inflation_claims")
    if inflation_claims is not None and not isinstance(inflation_claims, list):
        rows.append(
            _row(
                "C9b", GROUP_PAIR_COMPLETION, "B", "03 §47",
                "CANONICAL", STATUS_FAIL,
                "TELEMETRY_WINDOW_INFLATION_CLAIM_MALFORMED", block,
            )
        )
    elif isinstance(inflation_claims, list) and inflation_claims:
        rows.append(
            _row(
                "C9b", GROUP_PAIR_COMPLETION, "B", "03 §47",
                "CANONICAL", STATUS_FAIL, "TELEMETRY_WINDOW_INFLATION_CLAIM_PRESENT", block,
            )
        )
    else:
        rows.append(
            _row(
                "C9b", GROUP_PAIR_COMPLETION, "B", "03 §47",
                "CANONICAL", STATUS_PASS, "NO_TELEMETRY_WINDOW_INFLATION_CLAIM", "none",
            )
        )
    rematch = evidence.get("rematch_history")
    if isinstance(rematch, list):
        rematch_ok = all(
            isinstance(entry, Mapping)
            and entry.get("pairs_recorded") in (0, None)
            and _approval_shape_ok(entry.get("approval"))
            for entry in rematch
        )
    else:
        rematch_ok = rematch is None
    rows.append(
        _row(
            "C10", GROUP_PAIR_COMPLETION, "B", "03 §38; 05B §47",
            "CANONICAL", STATUS_PASS if rematch_ok else STATUS_FAIL,
            "NO_POST_HOC_REMATCH" if rematch_ok else "POST_HOC_REMATCH_RECORDED",
            "none" if rematch_ok else block,
        )
    )
    rows.append(
        _row(
            "C11", GROUP_PAIR_COMPLETION, "B", "03 §163",
            "CANONICAL", selection.status,
            f"SELECTION_RULE={selection.rule};" + ";".join(selection.reasons),
            "none" if selection.status == STATUS_PASS else block,
        )
    )
    external = evidence.get("external_links")
    holdout = external.get("w16_holdout") if isinstance(external, Mapping) else None
    holdout_status = holdout.get("status") if isinstance(holdout, Mapping) else None
    holdout_ok = isinstance(holdout, Mapping) and holdout_status == "NOT_OPENED"
    rows.append(
        _row(
            "C12", GROUP_PAIR_COMPLETION, "B", "03 §92-93; 05B §48",
            "CANONICAL", STATUS_PASS if holdout_ok else STATUS_FAIL,
            f"W16_HOLDOUT_STATUS={holdout_status if holdout_status is not None else 'MISSING'}",
            "none" if holdout_ok else block,
        )
    )
    return _group(GROUP_PAIR_COMPLETION, rows), counted, kind


def _assess_outcome_definition_freeze(
    record: Mapping[str, Any] | None,
) -> tuple[str, dict[str, Any], tuple[str, ...]]:
    if record is None:
        return (
            STATUS_FAIL,
            {},
            ("OUTCOME_DEFINITION_FREEZE_MISSING",),
        )
    if not isinstance(record, Mapping):
        raise W20EvidenceError("outcome_definition_freeze must be an object")
    unknown = sorted(set(record) - {"status", "fields", "approval"})
    if unknown:
        raise W20EvidenceError(
            "outcome_definition_freeze contains unknown field(s): " + ", ".join(unknown)
        )
    fields = record.get("fields")
    if not isinstance(fields, Mapping):
        fields = {}
    problems: list[str] = []
    values: dict[str, Any] = {}
    for field_id in OUTCOME_DEFINITION_FIELDS:
        entry = fields.get(field_id)
        if not isinstance(entry, Mapping):
            problems.append(f"MISSING_OUTCOME_FREEZE_FIELD:{field_id}")
            continue
        if entry.get("status") != FREEZE_FROZEN_APPROVED:
            problems.append(f"OUTCOME_FREEZE_FIELD_NOT_APPROVED:{field_id}")
        if not _is_present(entry.get("value")):
            problems.append(f"OUTCOME_FREEZE_FIELD_NULL:{field_id}")
        if not str(entry.get("provenance") or "").strip():
            problems.append(f"OUTCOME_FREEZE_FIELD_PROVENANCE_MISSING:{field_id}")
        values[field_id] = entry.get("value")
    if not _approval_shape_ok(record.get("approval")):
        problems.append("OUTCOME_DEFINITION_APPROVAL_INVALID")
    if record.get("status") != FREEZE_FROZEN_APPROVED:
        problems.append("OUTCOME_DEFINITION_NOT_FROZEN_APPROVED")
    return (STATUS_FAIL if problems else STATUS_PASS, values, tuple(sorted(problems)))


def _assess_scientific_freeze(
    evidence: Mapping[str, Any],
    manifest: Mapping[str, Any] | None,
) -> tuple[GroupAssessment, Mapping[str, Any], Mapping[str, Any]]:
    rows: list[RequirementRow] = []
    block = "analysis preflight remains blocked"
    statistical, error = _safe_call(
        assess_statistical_freeze, evidence.get("statistical_freeze")
    )
    statistical_fields: Mapping[str, Any] = {}
    record = evidence.get("statistical_freeze")
    if isinstance(record, Mapping) and isinstance(record.get("fields"), Mapping):
        statistical_fields = record["fields"]
    campaign_freeze, campaign_freeze_error = _safe_call(
        assess_campaign_freeze, evidence.get("campaign_freeze")
    )
    if campaign_freeze_error is not None:
        rows.append(
            _row(
                "E0", GROUP_SCIENTIFIC_FREEZE, "TEAM_LEAD", "03 §133; 04 W20",
                "CANONICAL", STATUS_FAIL,
                f"CAMPAIGN_FREEZE_MALFORMED:{campaign_freeze_error}", block,
            )
        )
    elif campaign_freeze is None or campaign_freeze.freeze_status != FREEZE_STATUS_APPROVED:
        rows.append(
            _row(
                "E0", GROUP_SCIENTIFIC_FREEZE, "TEAM_LEAD", "03 §133; 04 W20",
                "CANONICAL", STATUS_FAIL,
                "CAMPAIGN_FREEZE_NOT_APPROVED"
                + (
                    ";MISSING_FIELDS=" + ",".join(campaign_freeze.missing_field_ids)
                    if campaign_freeze is not None and campaign_freeze.missing_field_ids
                    else ""
                )
                + (
                    ";UNFROZEN_FIELDS=" + ",".join(campaign_freeze.unfrozen_field_ids)
                    if campaign_freeze is not None and campaign_freeze.unfrozen_field_ids
                    else ""
                ),
                block,
            )
        )
    else:
        rows.append(
            _row(
                "E0", GROUP_SCIENTIFIC_FREEZE, "TEAM_LEAD", "03 §133; 04 W20",
                "CANONICAL", STATUS_PASS, "CAMPAIGN_FREEZE_APPROVED", "none",
            )
        )
    if error is not None:
        rows.append(
            _row(
                "E1", GROUP_SCIENTIFIC_FREEZE, "TEAM_LEAD", "03 §130-135; 05B §48",
                "CANONICAL", STATUS_FAIL, f"STATISTICAL_FREEZE_MALFORMED:{error}", block,
            )
        )
    elif statistical.status != FREEZE_FROZEN_APPROVED:
        rows.append(
            _row(
                "E1", GROUP_SCIENTIFIC_FREEZE, "TEAM_LEAD", "03 §130-135; 05B §48",
                "CANONICAL", STATUS_FAIL,
                f"STATISTICAL_FREEZE_STATUS={statistical.status};"
                + ";".join(statistical.refusal_reasons),
                block,
            )
        )
    else:
        rows.append(
            _row(
                "E1", GROUP_SCIENTIFIC_FREEZE, "TEAM_LEAD", "03 §130-135; 05B §48",
                "CANONICAL", STATUS_PASS, "STATISTICAL_FREEZE_APPROVED", "none",
            )
        )
    try:
        outcome_status, outcome_values, outcome_problems = _assess_outcome_definition_freeze(
            evidence.get("outcome_definition_freeze")
        )
    except W20EvidenceError as exc:
        outcome_status, outcome_values, outcome_problems = STATUS_FAIL, {}, (str(exc),)
    if outcome_status == STATUS_PASS:
        rows.append(
            _row(
                "E2", GROUP_SCIENTIFIC_FREEZE, "B/TEAM_LEAD", "03 §68-75; 05B §48",
                "CANONICAL", STATUS_PASS, "OUTCOME_DEFINITION_FREEZE_APPROVED", "none",
            )
        )
    else:
        rows.append(
            _row(
                "E2", GROUP_SCIENTIFIC_FREEZE, "B/TEAM_LEAD", "03 §68-75; 05B §48",
                "CANONICAL", STATUS_FAIL, ";".join(outcome_problems) or "NOT_FROZEN", block,
            )
        )
    manifest_primary = None
    if isinstance(manifest, Mapping) and isinstance(manifest.get("identities"), Mapping):
        manifest_primary = manifest["identities"].get("primary_outcome")
    sources = {
        "statistical_freeze": statistical_fields.get("primary_outcome"),
        "outcome_definition_freeze": outcome_values.get("primary_outcome"),
    }
    if manifest_primary is None:
        rows.append(
            _row(
                "E3", GROUP_SCIENTIFIC_FREEZE, "B", "03 §133; 05B §48",
                "CANONICAL", STATUS_FAIL, "PRIMARY_OUTCOME_MANIFEST_IDENTITY_MISSING", block,
            )
        )
    else:
        mismatches = [
            source
            for source, value in sources.items()
            if _is_present(value) and canonical_sha256(value) != canonical_sha256(manifest_primary)
        ]
        missing = [source for source, value in sources.items() if not _is_present(value)]
        if mismatches or missing:
            rows.append(
                _row(
                    "E3", GROUP_SCIENTIFIC_FREEZE, "B", "03 §133; 05B §48",
                    "CANONICAL", STATUS_FAIL,
                    "PRIMARY_OUTCOME_SOURCE_CONFLICT:"
                    + ",".join(sorted(mismatches + missing)),
                    block,
                )
            )
        else:
            rows.append(
                _row(
                    "E3", GROUP_SCIENTIFIC_FREEZE, "B", "03 §133; 05B §48",
                    "CANONICAL", STATUS_PASS, "PRIMARY_OUTCOME_BOUND_ACROSS_FREEZES", "none",
                )
            )
    return _group(GROUP_SCIENTIFIC_FREEZE, rows), statistical_fields, outcome_values


def _verify_embedded(payload: Any, declared: Any, label: str) -> tuple[bool, str]:
    if not _is_hex64(declared):
        return False, f"{label}_HASH_INVALID"
    if canonical_sha256(payload) != declared:
        return False, f"{label}_HASH_UNBOUND"
    return True, f"{label}_HASH_BOUND"


def _assess_export(
    evidence: Mapping[str, Any],
    ledger: Mapping[str, Any] | None,
    validation: Any,
    counted_pairs: int,
    verified_artifacts: Mapping[str, str] | None,
) -> GroupAssessment:
    rows: list[RequirementRow] = []
    block = "analysis preflight remains blocked"
    export = evidence.get("export")
    if not isinstance(export, Mapping):
        for requirement_id, ref in (
            ("F1", "03 §130-135; 05C W20"),
            ("F3", "03 §130-135; 05C W20"),
            ("F4", "03 §158-163; 05C W20"),
            ("F7", "03 §130-135; 05C W20"),
            ("F8", "03 §137; 05A W20"),
        ):
            rows.append(
                _row(
                    requirement_id, GROUP_EXPORT, "C/A", ref,
                    "TEAM_DEPENDENCY", STATUS_FAIL, "FINAL_EXPORT_METADATA_MISSING", block,
                )
            )
        return _group(GROUP_EXPORT, rows)
    manifest = export.get("manifest")
    if not isinstance(manifest, Mapping):
        rows.append(
            _row(
                "F1", GROUP_EXPORT, "C", "03 §130-135; 05C W20",
                "TEAM_DEPENDENCY", STATUS_FAIL, "EXPORT_MANIFEST_MISSING", block,
            )
        )
        manifest = {}
    else:
        binding = export.get("manifest_verification")
        declared = export.get("manifest_sha256")
        if binding == BINDING_FILE:
            path = export.get("manifest_path")
            verified = (verified_artifacts or {}).get(str(path))
            ok = _is_hex64(declared) and verified == declared
            detail = "EXPORT_MANIFEST_FILE_BYTES_BOUND" if ok else "EXPORT_MANIFEST_FILE_UNVERIFIED"
        elif binding == BINDING_EMBEDDED:
            ok, detail = _verify_embedded(manifest, declared, "EXPORT_MANIFEST_EMBEDDED")
            if ok and evidence.get("evidence_class") == BUNDLE_PHYSICAL:
                ok, detail = False, "PHYSICAL_EXPORT_REQUIRES_FILE_BINDING"
        else:
            ok, detail = False, "EXPORT_MANIFEST_VERIFICATION_METHOD_INVALID"
        rows.append(
            _row(
                "F1", GROUP_EXPORT, "C", "03 §130-135; 05C W20",
                "TEAM_DEPENDENCY", STATUS_PASS if ok else STATUS_FAIL, detail,
                "none" if ok else block,
            )
        )
        rows.append(
            _row(
                "F3", GROUP_EXPORT, "C", "03 §130-135; 05C W20",
                "TEAM_DEPENDENCY", STATUS_PASS if ok else STATUS_FAIL,
                "MANIFEST_CHECKSUMS_BOUND" if ok else "MANIFEST_CHECKSUMS_UNBOUND",
                "none" if ok else block,
            )
        )
    attempts = _attempts_from_ledger(ledger)
    ledger_attempt_ids = {str(a.get("attempt_id")) for a in attempts}
    export_attempt_ids = manifest.get("attempt_ids")
    attempts_ok = (
        isinstance(export_attempt_ids, list)
        and set(map(str, export_attempt_ids)) == ledger_attempt_ids
        and bool(ledger_attempt_ids)
    )
    rows.append(
        _row(
            "F4", GROUP_EXPORT, "C", "03 §158-163; 05C W20",
            "TEAM_DEPENDENCY", STATUS_PASS if attempts_ok else STATUS_FAIL,
            "FULL_ATTEMPT_LIST_PRESERVED" if attempts_ok else "ATTEMPT_LIST_MISMATCH",
            "none" if attempts_ok else block,
        )
    )
    ledger_hashes = {
        str(a.get("attempt_id")): str(a.get("source_sha256")) for a in attempts
    }
    references = manifest.get("source_references")
    sources_ok = isinstance(references, list) and bool(references)
    if sources_ok:
        covered = set()
        for reference in references:
            if not isinstance(reference, Mapping):
                sources_ok = False
                break
            attempt_id = str(reference.get("attempt_id"))
            if reference.get("sha256") != ledger_hashes.get(attempt_id):
                sources_ok = False
                break
            covered.add(attempt_id)
        sources_ok = sources_ok and covered == ledger_attempt_ids
    rows.append(
        _row(
            "F2", GROUP_EXPORT, "C", "03 §130-135; 05C W20",
            "TEAM_DEPENDENCY", STATUS_PASS if sources_ok else STATUS_FAIL,
            "SOURCE_RECEIPTS_BOUND_TO_LEDGER" if sources_ok else "SOURCE_RECEIPT_MISMATCH",
            "none" if sources_ok else block,
        )
    )
    provenance_ok = bool(str(manifest.get("event_time_domain") or "").strip())
    quality_ok = manifest.get("quality_flags_complete") is True
    rows.append(
        _row(
            "F5", GROUP_EXPORT, "C", "01 §18; 05C W20",
            "TEAM_DEPENDENCY", STATUS_PASS if provenance_ok else STATUS_FAIL,
            "EVENT_TIME_PROVENANCE_RECORDED" if provenance_ok else "EVENT_TIME_PROVENANCE_MISSING",
            "none" if provenance_ok else block,
        )
    )
    rows.append(
        _row(
            "F6", GROUP_EXPORT, "C", "01 §33; 05C W20",
            "TEAM_DEPENDENCY", STATUS_PASS if quality_ok else STATUS_FAIL,
            "QUALITY_FLAGS_COMPLETE" if quality_ok else "QUALITY_FLAGS_INCOMPLETE",
            "none" if quality_ok else block,
        )
    )
    backup = export.get("backup")
    backup_ok = False
    backup_detail = "BACKUP_EVIDENCE_MISSING"
    if isinstance(backup, Mapping):
        if backup.get("status") != "VERIFIED":
            backup_detail = f"BACKUP_STATUS={backup.get('status')}"
        elif backup.get("verification") == BINDING_FILE:
            path = backup.get("evidence_path")
            verified = (verified_artifacts or {}).get(str(path))
            backup_ok = _is_hex64(backup.get("evidence_sha256")) and verified == backup.get(
                "evidence_sha256"
            )
            backup_detail = "BACKUP_FILE_BYTES_BOUND" if backup_ok else "BACKUP_FILE_UNVERIFIED"
        elif backup.get("verification") == BINDING_EMBEDDED:
            backup_ok, backup_detail = _verify_embedded(
                backup.get("evidence"), backup.get("evidence_sha256"), "BACKUP_EVIDENCE"
            )
            if backup_ok and evidence.get("evidence_class") == BUNDLE_PHYSICAL:
                backup_ok, backup_detail = False, "PHYSICAL_BACKUP_REQUIRES_FILE_BINDING"
        else:
            backup_detail = "BACKUP_VERIFICATION_METHOD_INVALID"
    rows.append(
        _row(
            "F7", GROUP_EXPORT, "C", "03 §130-135; 05C W20",
            "TEAM_DEPENDENCY", STATUS_PASS if backup_ok else STATUS_FAIL,
            backup_detail, "none" if backup_ok else block,
        )
    )
    missing_runs = export.get("missing_runs")
    missing_attempts = export.get("missing_attempts")
    missing_ok = missing_runs == [] and missing_attempts == []
    rows.append(
        _row(
            "F9", GROUP_EXPORT, "C", "03 §158-163",
            "TEAM_DEPENDENCY", STATUS_PASS if missing_ok else STATUS_FAIL,
            "NO_UNEXPLAINED_MISSING_RUN_OR_ATTEMPT" if missing_ok else "MISSING_RUN_OR_ATTEMPT",
            "none" if missing_ok else block,
        )
    )
    physical = evidence.get("physical_verification")
    physical_ok = False
    physical_detail = "PHYSICAL_VERIFICATION_TRACE_MISSING"
    if isinstance(physical, Mapping):
        coverage = physical.get("coverage_pairs")
        required = physical.get("required_pairs")
        coverage_ok = (
            isinstance(coverage, int)
            and isinstance(required, int)
            and required >= counted_pairs
            and coverage >= required
        )
        if physical.get("status") != "VERIFIED":
            physical_detail = f"PHYSICAL_VERIFICATION_STATUS={physical.get('status')}"
        elif not coverage_ok:
            physical_detail = "PHYSICAL_VERIFICATION_COVERAGE_INSUFFICIENT"
        elif physical.get("verification") == BINDING_FILE:
            path = physical.get("evidence_path")
            verified = (verified_artifacts or {}).get(str(path))
            physical_ok = _is_hex64(
                physical.get("evidence_sha256")
            ) and verified == physical.get("evidence_sha256")
            physical_detail = (
                "PHYSICAL_TRACE_FILE_BYTES_BOUND"
                if physical_ok
                else "PHYSICAL_TRACE_FILE_UNVERIFIED"
            )
        elif physical.get("verification") == BINDING_EMBEDDED:
            physical_ok, physical_detail = _verify_embedded(
                physical.get("evidence"),
                physical.get("evidence_sha256"),
                "PHYSICAL_TRACE_EVIDENCE",
            )
            if physical_ok and evidence.get("evidence_class") == BUNDLE_PHYSICAL:
                physical_ok, physical_detail = False, "PHYSICAL_TRACE_REQUIRES_FILE_BINDING"
        else:
            physical_detail = "PHYSICAL_VERIFICATION_METHOD_INVALID"
    rows.append(
        _row(
            "F8", GROUP_EXPORT, "A", "03 §137; 05A W20",
            "TEAM_DEPENDENCY", STATUS_PASS if physical_ok else STATUS_FAIL,
            physical_detail, "none" if physical_ok else block,
        )
    )
    return _group(GROUP_EXPORT, rows)


def _proof_class(evidence: Mapping[str, Any]) -> str:
    evidence_class = evidence.get("evidence_class")
    if evidence_class == BUNDLE_SYNTHETIC or evidence.get("fixture_markers"):
        return PROOF_TEST_ONLY
    if evidence_class == BUNDLE_PHYSICAL:
        return PROOF_PHYSICAL
    return PROOF_METADATA_ONLY


def _analysis_authorization_state(
    evidence: Mapping[str, Any],
    verified_artifacts: Mapping[str, str] | None,
) -> tuple[str, tuple[str, ...]]:
    section = evidence.get("analysis_execution_authorization")
    if not isinstance(section, Mapping):
        return "NOT_ISSUED", ("ANALYSIS_AUTHORIZATION_RECORD_MISSING",)
    status = section.get("status")
    verification = section.get("verification_status")
    problems: list[str] = []
    if status != "ISSUED":
        problems.append(f"ANALYSIS_AUTHORIZATION_STATUS={status}")
    if verification != VERIFICATION_VERIFIED_EXTERNAL:
        problems.append("ANALYSIS_AUTHORIZATION_NOT_VERIFIED_EXTERNALLY")
    if not _is_present(section.get("authority_id")):
        problems.append("ANALYSIS_AUTHORIZATION_AUTHORITY_MISSING")
    if section.get("authority_role") != "TEAM_LEAD":
        problems.append("ANALYSIS_AUTHORIZATION_AUTHORITY_ROLE_NOT_TEAM_LEAD")
    if not _is_present(section.get("canonical_ref")):
        problems.append("ANALYSIS_AUTHORIZATION_REFERENCE_MISSING")
    if section.get("campaign_id") != evidence.get("campaign_id"):
        problems.append("ANALYSIS_AUTHORIZATION_CAMPAIGN_ID_MISMATCH")
    declared = section.get("verification_artifact_sha256")
    binding = section.get("verification_binding")
    if binding != BINDING_FILE:
        problems.append("ANALYSIS_AUTHORIZATION_REQUIRES_EXTERNAL_FILE_BINDING")
    else:
        path = str(section.get("verification_artifact_path") or "")
        verified = (verified_artifacts or {}).get(path)
        if not (
            path.startswith("evidence/leader/")
            or path.startswith("evidence/authorization/")
        ):
            problems.append("ANALYSIS_AUTHORIZATION_ARTIFACT_PATH_NOT_AUTHORIZED")
        if not (_is_hex64(declared) and verified == declared):
            problems.append("ANALYSIS_AUTHORIZATION_ARTIFACT_UNVERIFIED")
    return status or "NOT_ISSUED", tuple(sorted(set(problems)))


def assess_campaign_lock(
    evidence: Mapping[str, Any],
    *,
    verified_artifacts: Mapping[str, str] | None = None,
) -> CampaignLockAssessment:
    """Assess final campaign-lock metadata without touching outcome data."""
    assert_no_analysis_payload(evidence)
    _validate_bundle(evidence)
    campaign_id = str(evidence["campaign_id"])
    evidence_class = str(evidence["evidence_class"])
    manifest = evidence.get("campaign_manifest")
    if manifest is not None and not isinstance(manifest, Mapping):
        raise W20EvidenceError("campaign_manifest must be an object or null")
    ledger = evidence.get("pair_ledger")
    if ledger is not None and not isinstance(ledger, Mapping):
        raise W20EvidenceError("pair_ledger must be an object or null")
    validation = None
    ledger_error = None
    if ledger is not None:
        try:
            validation = validate_pair_ledger(ledger)
        except (W19LedgerError, W19OutcomeExposureError) as exc:
            ledger_error = str(exc)

    authorization_group = _assess_authorization(evidence, manifest)
    target_group, target = _assess_pair_target(evidence, manifest)
    selection = _assess_selection(evidence)

    freeze_values: Mapping[str, Any] = {}
    if isinstance(evidence.get("campaign_freeze"), Mapping):
        try:
            freeze = assess_campaign_freeze(evidence["campaign_freeze"])
            freeze_values = freeze.field_values
        except (W19LedgerError, ValueError):
            freeze_values = {}
    statistical_group, statistical_fields, outcome_fields = _assess_scientific_freeze(
        evidence, manifest
    )

    stability = _assess_stability(
        evidence,
        manifest,
        ledger,
        validation,
        freeze_values,
        statistical_fields,
        outcome_fields,
    )
    completion_group, counted, counted_kind = _assess_pair_completion(
        evidence,
        manifest,
        ledger,
        validation,
        ledger_error,
        target,
        selection,
    )
    export_group = _assess_export(
        evidence, ledger, validation, counted, verified_artifacts
    )

    binding_rows = _ledger_binding_rows(evidence, ledger)
    campaign_freeze_binding = _ledger_campaign_freeze_row(evidence, ledger)
    scientific_extra: list[RequirementRow] = []
    if GROUP_SCIENTIFIC_FREEZE in binding_rows:
        scientific_extra.append(binding_rows[GROUP_SCIENTIFIC_FREEZE])
    if campaign_freeze_binding is not None:
        scientific_extra.append(campaign_freeze_binding)
    groups = (
        _append_binding(
            authorization_group,
            [binding_rows[GROUP_AUTHORIZATION]]
            if GROUP_AUTHORIZATION in binding_rows
            else [],
        ),
        _append_binding(
            target_group,
            [binding_rows[GROUP_PAIR_TARGET]]
            if GROUP_PAIR_TARGET in binding_rows
            else [],
        ),
        completion_group,
        _group(GROUP_STABILITY, stability.identity_rows),
        _append_binding(statistical_group, scientific_extra),
        export_group,
    )

    analysis_status, analysis_problems = _analysis_authorization_state(
        evidence, verified_artifacts
    )

    group_statuses = {group.group_id: group.status for group in groups}
    all_pass = all(status == STATUS_PASS for status in group_statuses.values())
    any_fail = any(status == STATUS_FAIL for status in group_statuses.values())
    any_unknown = any(status == STATUS_UNKNOWN for status in group_statuses.values())

    if target is None or target.status != TARGET_FROZEN:
        closeout = CLOSEOUT_PAIR_TARGET_NOT_FROZEN
    elif ledger is None or validation is None or ledger_error is not None:
        closeout = CLOSEOUT_CAMPAIGN_LOCK_INCOMPLETE
    elif target.planned_pair_target is not None and counted < target.planned_pair_target:
        closeout = CLOSEOUT_PAIR_TARGET_NOT_REACHED
    elif all_pass:
        closeout = CLOSEOUT_CAMPAIGN_LOCK_READY_FOR_EXTERNAL_REVIEW
    elif any_unknown and not any_fail:
        closeout = CLOSEOUT_PAIR_TARGET_REACHED_PENDING_INTEGRITY
    else:
        closeout = CLOSEOUT_CAMPAIGN_LOCK_INCOMPLETE

    refusal_reasons: list[str] = []
    for group in groups:
        refusal_reasons.extend(group.reasons)
    refusal_reasons.extend(selection.reasons)
    refusal_reasons.extend(stability.reasons)
    if closeout != CLOSEOUT_CAMPAIGN_LOCK_READY_FOR_EXTERNAL_REVIEW:
        refusal_reasons.append(f"CLOSEOUT={closeout}")

    if closeout != CLOSEOUT_CAMPAIGN_LOCK_READY_FOR_EXTERNAL_REVIEW:
        gate = ANALYSIS_PREFLIGHT_BLOCKED
    elif (
        evidence_class == BUNDLE_PHYSICAL
        and analysis_status == "ISSUED"
        and not analysis_problems
    ):
        gate = ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION
    else:
        gate = ANALYSIS_METADATA_READY_PENDING_AUTHORIZATION

    if gate != ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION:
        refusal_reasons.extend(analysis_problems)

    return CampaignLockAssessment(
        campaign_id=campaign_id,
        evidence_class=evidence_class,
        proof_class=_proof_class(evidence),
        groups=groups,
        stability=stability,
        selection=selection,
        gate_decision=gate,
        closeout_state=closeout,
        authorization_status=authorization_group.status,
        pair_target_status=target.status if target is not None else "MISSING",
        planned_pair_target=(
            target.planned_pair_target if target is not None else None
        ),
        counted_valid_pairs=counted,
        counted_pairs_kind=counted_kind,
        analysis_authorization_status=analysis_status,
        refusal_reasons=tuple(sorted(set(refusal_reasons))),
        outcome_access=False,
        analysis_actions=(),
    )


class MetadataOnlyReader:
    """Read guard that only opens allowlisted metadata bytes."""

    DEFAULT_FORBIDDEN_TOKENS = (
        "outcome",
        "thermal_series",
        "temperature_series",
        "power_series",
        "energy_series",
        "raw_telemetry",
        "telemetry_raw",
    )

    def __init__(
        self,
        root: str | Path,
        allowed_paths: Sequence[str],
        *,
        forbidden_tokens: Sequence[str] | None = None,
    ) -> None:
        self._root = Path(root).resolve()
        self._allowed = {Path(path).as_posix() for path in allowed_paths}
        self._forbidden = tuple(forbidden_tokens or self.DEFAULT_FORBIDDEN_TOKENS)
        self.read_log: list[str] = []

    def _resolve(self, relative_path: str) -> tuple[Path, str]:
        rel = Path(relative_path).as_posix()
        lowered = rel.lower()
        for token in self._forbidden:
            if token in lowered:
                raise W20OutcomeAccessError(
                    f"metadata-only reader refuses outcome-shaped path {rel!r}"
                )
        if rel not in self._allowed:
            raise W20OutcomeAccessError(
                f"metadata-only reader refuses non-allowlisted path {rel!r}"
            )
        path = (self._root / rel).resolve()
        if self._root not in path.parents:
            raise W20OutcomeAccessError(
                f"metadata-only reader refuses path outside the repository {rel!r}"
            )
        return path, rel

    def read_bytes(self, relative_path: str) -> bytes:
        path, rel = self._resolve(relative_path)
        self.read_log.append(rel)
        return path.read_bytes()

    def read_json(self, relative_path: str) -> dict[str, Any]:
        payload = json.loads(self.read_bytes(relative_path).decode("utf-8"))
        if not isinstance(payload, dict):
            raise W20EvidenceError(f"{relative_path} must contain a JSON object")
        return payload

    def sha256(self, relative_path: str) -> str:
        return hashlib.sha256(self.read_bytes(relative_path)).hexdigest()


@dataclass(frozen=True)
class ChecksumVerification:
    root: str
    sums_path: str
    verified: Mapping[str, str]
    unverified: tuple[str, ...]
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "sums_path": self.sums_path,
            "verified": dict(self.verified),
            "unverified": list(self.unverified),
            "passed": self.passed,
        }


def verify_checksum_listing(
    reader: MetadataOnlyReader,
    *,
    root: str,
    sums_path: str,
    allowed_files: Sequence[str],
) -> ChecksumVerification:
    """Verify a SHA256SUMS listing against actual bytes of allowlisted metadata."""
    allowed = {Path(path).as_posix() for path in allowed_files}
    verified: dict[str, str] = {}
    unverified: list[str] = []
    text = reader.read_bytes(sums_path).decode("utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            unverified.append(line)
            continue
        declared, name = parts[0], Path(parts[1]).as_posix()
        relative = f"{Path(root).as_posix()}/{name}"
        if relative not in allowed:
            unverified.append(relative)
            continue
        actual = reader.sha256(relative)
        if actual != declared:
            unverified.append(relative)
            continue
        verified[relative] = actual
    return ChecksumVerification(
        root=Path(root).as_posix(),
        sums_path=Path(sums_path).as_posix(),
        verified=verified,
        unverified=tuple(unverified),
        passed=not unverified,
    )


@dataclass(frozen=True)
class CapabilityFinding:
    path: str
    line: int
    kind: str
    target: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "kind": self.kind,
            "target": self.target,
        }


@dataclass(frozen=True)
class CapabilityAudit:
    files_scanned: tuple[str, ...]
    findings: tuple[CapabilityFinding, ...]
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_scanned": list(self.files_scanned),
            "findings": [finding.to_dict() for finding in self.findings],
            "passed": self.passed,
        }


def audit_w20_capability(
    paths: Sequence[str | Path], *, display_root: str | Path | None = None
) -> CapabilityAudit:
    """Statically prove that a W20 source tree carries no analysis capability."""
    findings: list[CapabilityFinding] = []
    scanned: list[str] = []
    root = Path(display_root) if display_root is not None else None

    def display(path: Path) -> str:
        if root is not None:
            try:
                return path.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                return path.as_posix()
        return str(path)

    for raw_path in paths:
        path = Path(raw_path)
        scanned.append(display(path))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            findings.append(
                CapabilityFinding(str(path), 0, "PARSE_ERROR", type(exc).__name__)
            )
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    if module.split(".")[0] in FORBIDDEN_RUNTIME_IMPORTS:
                        findings.append(
                            CapabilityFinding(
                                display(path), node.lineno, "FORBIDDEN_IMPORT", module
                            )
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".")[0] in FORBIDDEN_RUNTIME_IMPORTS:
                    findings.append(
                        CapabilityFinding(
                            display(path), node.lineno, "FORBIDDEN_IMPORT", module
                        )
                    )
                for alias in node.names:
                    if alias.name in FORBIDDEN_CALL_NAMES:
                        findings.append(
                            CapabilityFinding(
                                display(path), node.lineno, "FORBIDDEN_IMPORT", alias.name
                            )
                        )
            elif isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name in FORBIDDEN_CALL_NAMES:
                    findings.append(
                        CapabilityFinding(
                            display(path), node.lineno, "FORBIDDEN_CALL", name
                        )
                    )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if FORBIDDEN_DEFINITION_PATTERN.match(node.name):
                    findings.append(
                        CapabilityFinding(
                            display(path), node.lineno, "FORBIDDEN_DEFINITION", node.name
                        )
                    )
    return CapabilityAudit(
        files_scanned=tuple(scanned),
        findings=tuple(findings),
        passed=not findings,
    )
