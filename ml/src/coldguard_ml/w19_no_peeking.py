"""W19 no-significance-peeking and no-outcome-analysis guards (B-W19-03).

Canonical anchors: Doc 03 §163; Doc 05B §47 B-W19-03; W19 campaign-integrity
scope.  W19 may inspect attempt identity, completeness, quality, validity,
progress, safety and provenance.  It must not compute a headline p-value, a
confidence interval, a paired improvement or any treatment-effect summary, and
it must not stop the campaign because interim results look favorable.

The prohibition is structural: W19 contains no outcome-analysis implementation,
this module refuses prohibited operation identifiers at runtime, and
``audit_source_capability`` statically rejects outcome-analysis imports, calls
or definitions in a W19 source tree.  A comment is not proof; the audit and the
negative probes are.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

PEEKING_GUARD_VERSION = "coldguard-w19-peeking-guard-v1"

OPERATION_ALLOWED = "ALLOWED"
OPERATION_PROHIBITED = "PROHIBITED"
OPERATION_UNKNOWN = "UNKNOWN"

STOP_ALLOWED = "STOP_PERMITTED_OPERATIONAL_REASON"
STOP_REFUSED = "STOP_REFUSED"
OPERATIONAL_STOP_EFFECT = "OPERATIONAL_STOP_NOT_STATISTICAL_EVIDENCE"

MUTATION_ACCEPTED_REQUIRES_NEW_FREEZE = "ACCEPTED_REQUIRES_NEW_FREEZE"
MUTATION_REFUSED_POST_CAMPAIGN_START = "REFUSED_AFTER_CAMPAIGN_START"
MUTATION_REFUSED_MISSING_APPROVAL = "REFUSED_MISSING_APPROVAL"
MUTATION_REFUSED_UNKNOWN_RULE = "REFUSED_UNKNOWN_FROZEN_RULE"

HOLDOUT_NOT_OPENED = "NOT_OPENED"
HOLDOUT_OPENED = "OPENED"
HOLDOUT_UNKNOWN = "UNKNOWN"

FREEZE_FROZEN_APPROVED = "FROZEN_APPROVED"
FREEZE_NOT_FROZEN = "NOT_FROZEN"
FREEZE_INCOMPLETE = "INCOMPLETE"

REGISTERED_SIGN_CONVENTION = "I_i = Y_A,i - Y_B,i"

ALLOWED_W19_COMPUTATIONS: dict[str, str] = {
    "attempt_identity_validation": "Check attempt/run/pair identities and duplicates.",
    "run_completeness": "Check that an attempt record carries its required evidence.",
    "pair_eligibility": "Derive the pair state machine from protocol evidence.",
    "data_quality_status": "Inspect declared quality and completeness flags.",
    "protocol_violations": "Evaluate predeclared protocol failure codes.",
    "campaign_progress": "Count pairs and attempts against a frozen target.",
    "safety_record_inspection": "Read safety-stop and abort records.",
    "provenance_integrity_checks": "Verify source hashes and identity binding.",
}

PROHIBITED_W19_COMPUTATIONS: dict[str, str] = {
    "headline_p_value": "Final A/B significance belongs to W20.",
    "confidence_interval_final_effect": "Final-effect intervals belong to W20.",
    "pairwise_improvement_distribution": "Paired improvement is outcome analysis.",
    "mean_controller_b_benefit": "Treatment benefit summaries belong to W20.",
    "best_worst_outcome_selection": "Outcome-based selection is analysis.",
    "interim_model_policy_optimization": "W19 must not tune from outcomes.",
    "significance_based_early_stopping": "Doc 03 §163 forbids significance peeking.",
    "final_physical_effectiveness_verdict": "Final effectiveness belongs to W20.",
}

ALLOWED_STOP_REASONS: dict[str, str] = {
    "SAFETY_RESTRICTION": "documented safety restriction",
    "EQUIPMENT_FAILURE": "equipment failure",
    "FEASIBILITY_RESTRICTION": "genuine feasibility restriction",
    "AUTHORIZED_OPERATIONAL_CHANGE": "authorized operational change",
}

STATISTICAL_STOP_REASON_CODES = frozenset(
    {
        "STATISTICAL_SIGNIFICANCE",
        "FAVORABLE_INTERIM_RESULT",
        "TREATMENT_BENEFIT_OBSERVED",
        "P_VALUE_THRESHOLD_REACHED",
        "CI_EXCLUDES_ZERO",
    }
)

FROZEN_RULE_IDS = frozenset(
    {
        "pair_target",
        "invalid_pair_handling",
        "validity_exclusion_rules",
        "primary_outcome",
    }
)

STATISTICAL_FREEZE_FIELDS = (
    "primary_outcome",
    "paired_sign_convention",
    "confidence_level",
    "bootstrap_seed",
    "bootstrap_iterations",
    "test_family",
    "invalid_pair_handling",
    "secondary_outcomes",
)

FORBIDDEN_OUTCOME_FIELD_NAMES = frozenset(
    {
        "p_value",
        "pvalue",
        "p_val",
        "confidence_interval",
        "ci_lower",
        "ci_upper",
        "ci_low",
        "ci_high",
        "effect_size",
        "paired_difference",
        "paired_improvement",
        "improvement",
        "improvement_pct",
        "mean_improvement",
        "mean_benefit",
        "benefit",
        "treatment_effect",
        "thermal_exposure",
        "recovery_time",
        "branch_energy",
        "energy_wh",
        "energy_delta",
        "peak_temp",
        "peak_temperature",
        "time_above_critical",
        "time_above_target",
        "y_a",
        "y_b",
        "y_a_i",
        "y_b_i",
        "outcome",
        "outcomes",
        "outcome_values",
    }
)

FORBIDDEN_IMPORT_ROOTS = frozenset({"scipy", "statsmodels", "pingouin", "pymc", "arviz"})
FORBIDDEN_MODULE_PREFIXES = ("coldguard_ml.evaluation_contract",)
FORBIDDEN_CALL_NAMES = frozenset(
    {
        "paired_improvement",
        "compute_p_value",
        "p_value",
        "ttest_ind",
        "ttest_rel",
        "mannwhitneyu",
        "wilcoxon",
        "bootstrap",
        "bootstrap_ci",
        "confidence_interval",
        "mean_improvement",
        "effect_size",
    }
)
FORBIDDEN_DEFINITION_PATTERN = re.compile(
    r"^(compute_p_value|compute_confidence|estimate_effect|analyze_outcome"
    r"|paired_effect|paired_improvement|bootstrap_.*)$"
)


class W19PeekingError(ValueError):
    """Raised when a caller requests a computation W19 may not perform."""


class W19OutcomeExposureError(W19PeekingError):
    """Raised when an outcome-shaped payload reaches the validity route."""


@dataclass(frozen=True)
class OperationPermit:
    operation_id: str
    classification: str
    description: str
    outcome_access: bool
    analysis_scope: str = "VALIDITY_COMPLETENESS_AND_PROGRESS_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "classification": self.classification,
            "description": self.description,
            "outcome_access": self.outcome_access,
            "analysis_scope": self.analysis_scope,
        }


@dataclass(frozen=True)
class CampaignStopDecision:
    reason_code: str
    decision: str
    reason_class: str
    evidence_bound: bool
    refusal_reasons: tuple[str, ...]
    effect_on_analysis: str = OPERATIONAL_STOP_EFFECT

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "decision": self.decision,
            "reason_class": self.reason_class,
            "evidence_bound": self.evidence_bound,
            "refusal_reasons": list(self.refusal_reasons),
            "effect_on_analysis": self.effect_on_analysis,
        }


@dataclass(frozen=True)
class RuleChangeDecision:
    rule_id: str
    decision: str
    refusal_reasons: tuple[str, ...]
    approval_effect: str = "NONE_SOFTWARE_ASSESSMENT_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "decision": self.decision,
            "refusal_reasons": list(self.refusal_reasons),
            "approval_effect": self.approval_effect,
        }


@dataclass(frozen=True)
class StatisticalFreezeAssessment:
    status: str
    missing_fields: tuple[str, ...]
    refusal_reasons: tuple[str, ...]
    registered_sign_convention: str
    approval_effect: str = "NONE_SOFTWARE_ASSESSMENT_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "missing_fields": list(self.missing_fields),
            "refusal_reasons": list(self.refusal_reasons),
            "registered_sign_convention": self.registered_sign_convention,
            "approval_effect": self.approval_effect,
        }


@dataclass(frozen=True)
class HoldoutStatus:
    status: str
    frozen: bool | None
    opened_at: Any
    test_partition_used: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "frozen": self.frozen,
            "opened_at": self.opened_at,
            "test_partition_used": self.test_partition_used,
        }


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


def classify_w19_operation(operation_id: str) -> OperationPermit:
    """Classify an operation identifier without raising."""
    if not isinstance(operation_id, str) or not operation_id:
        return OperationPermit(
            operation_id=str(operation_id),
            classification=OPERATION_UNKNOWN,
            description="empty or non-string operation identifier",
            outcome_access=False,
        )
    if operation_id in ALLOWED_W19_COMPUTATIONS:
        return OperationPermit(
            operation_id=operation_id,
            classification=OPERATION_ALLOWED,
            description=ALLOWED_W19_COMPUTATIONS[operation_id],
            outcome_access=False,
        )
    if operation_id in PROHIBITED_W19_COMPUTATIONS:
        return OperationPermit(
            operation_id=operation_id,
            classification=OPERATION_PROHIBITED,
            description=PROHIBITED_W19_COMPUTATIONS[operation_id],
            outcome_access=True,
        )
    return OperationPermit(
        operation_id=operation_id,
        classification=OPERATION_UNKNOWN,
        description="operation is not declared in the W19 allowlist",
        outcome_access=False,
    )


def require_w19_operation(operation_id: str) -> OperationPermit:
    """Return a permit for an allowed W19 operation; refuse everything else."""
    permit = classify_w19_operation(operation_id)
    if permit.classification == OPERATION_PROHIBITED:
        raise W19PeekingError(
            f"prohibited W19 computation {operation_id!r}: {permit.description}"
        )
    if permit.classification != OPERATION_ALLOWED:
        raise W19PeekingError(
            f"unknown W19 operation {operation_id!r}; the guard fails closed"
        )
    return permit


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def assert_outcome_blind(payload: Any, *, context: str = "payload") -> None:
    """Refuse any outcome-shaped field before it can enter a W19 decision path."""
    if isinstance(payload, Mapping):
        for raw_key, value in payload.items():
            key = _normalize_key(str(raw_key))
            if key in FORBIDDEN_OUTCOME_FIELD_NAMES:
                raise W19OutcomeExposureError(
                    f"{context} contains outcome field {raw_key!r}; W19 accepts "
                    "metadata-only records and must not load physical outcomes"
                )
            assert_outcome_blind(value, context=f"{context}.{raw_key}")
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            assert_outcome_blind(item, context=f"{context}[{index}]")


def validate_stop_reason(reason_code: str, evidence_ref: str) -> CampaignStopDecision:
    """A campaign stop is operational evidence only, never a statistical result."""
    if not isinstance(reason_code, str) or not reason_code:
        raise W19PeekingError("stop reason code must be a non-empty string")
    if reason_code in ALLOWED_STOP_REASONS:
        reason_class = "OPERATIONAL"
        refusal_reasons: tuple[str, ...] = ()
        decision = STOP_ALLOWED if evidence_ref else STOP_REFUSED
        if not evidence_ref:
            refusal_reasons = ("STOP_REASON_EVIDENCE_MISSING",)
    elif reason_code in STATISTICAL_STOP_REASON_CODES:
        reason_class = "STATISTICAL"
        decision = STOP_REFUSED
        refusal_reasons = ("STOP_REASON_STATISTICAL_PEEKING_PROHIBITED",)
    else:
        reason_class = "UNKNOWN"
        decision = STOP_REFUSED
        refusal_reasons = ("STOP_REASON_NOT_PREDECLARED",)
    return CampaignStopDecision(
        reason_code=reason_code,
        decision=decision,
        reason_class=reason_class,
        evidence_bound=bool(evidence_ref),
        refusal_reasons=refusal_reasons,
    )


def assess_frozen_rule_change(
    rule_id: str,
    *,
    approval_ref: str | None,
    pairs_recorded: int,
) -> RuleChangeDecision:
    """Refuse post-observation changes to the target, validity or outcome rules."""
    if not isinstance(pairs_recorded, int) or isinstance(pairs_recorded, bool):
        raise W19PeekingError("pairs_recorded must be an integer")
    if pairs_recorded < 0:
        raise W19PeekingError("pairs_recorded must not be negative")
    if rule_id not in FROZEN_RULE_IDS:
        return RuleChangeDecision(
            rule_id=str(rule_id),
            decision=MUTATION_REFUSED_UNKNOWN_RULE,
            refusal_reasons=("FROZEN_RULE_ID_UNKNOWN",),
        )
    if pairs_recorded > 0:
        return RuleChangeDecision(
            rule_id=rule_id,
            decision=MUTATION_REFUSED_POST_CAMPAIGN_START,
            refusal_reasons=("RULE_CHANGE_AFTER_PAIRS_RECORDED",),
        )
    if not approval_ref:
        return RuleChangeDecision(
            rule_id=rule_id,
            decision=MUTATION_REFUSED_MISSING_APPROVAL,
            refusal_reasons=("RULE_CHANGE_APPROVAL_MISSING",),
        )
    return RuleChangeDecision(
        rule_id=rule_id,
        decision=MUTATION_ACCEPTED_REQUIRES_NEW_FREEZE,
        refusal_reasons=(),
    )


def _approval_shape_ok(approval: Any) -> bool:
    if not isinstance(approval, Mapping):
        return False
    return bool(
        approval.get("authority_id")
        and approval.get("authority_role") == "TEAM_LEAD"
        and approval.get("canonical_ref")
    )


def assess_statistical_freeze(record: Mapping[str, Any] | None) -> StatisticalFreezeAssessment:
    """Shape-check the Doc 03 §133 freeze record without computing anything."""
    if record is None:
        return StatisticalFreezeAssessment(
            status=FREEZE_NOT_FROZEN,
            missing_fields=STATISTICAL_FREEZE_FIELDS,
            refusal_reasons=("STATISTICAL_FREEZE_RECORD_MISSING",),
            registered_sign_convention=REGISTERED_SIGN_CONVENTION,
        )
    if not isinstance(record, Mapping):
        raise W19PeekingError("statistical_freeze must be an object")
    allowed = {"status", "fields", "approval"}
    unknown = sorted(set(record) - allowed)
    if unknown:
        raise W19PeekingError(
            f"statistical_freeze contains unknown field(s): {', '.join(unknown)}"
        )
    fields = record.get("fields")
    if not isinstance(fields, Mapping):
        fields = {}
    missing = tuple(
        field
        for field in STATISTICAL_FREEZE_FIELDS
        if fields.get(field) in (None, "", [])
    )
    refusal_reasons: list[str] = []
    if missing:
        refusal_reasons.append("STATISTICAL_FREEZE_INCOMPLETE")
    if not _approval_shape_ok(record.get("approval")):
        refusal_reasons.append("STATISTICAL_FREEZE_APPROVAL_INVALID")
    sign_convention = fields.get("paired_sign_convention")
    if sign_convention is not None and sign_convention != REGISTERED_SIGN_CONVENTION:
        refusal_reasons.append("SIGN_CONVENTION_MISMATCH")
    frozen = record.get("status") == FREEZE_FROZEN_APPROVED
    status = (
        FREEZE_FROZEN_APPROVED
        if frozen and not refusal_reasons
        else FREEZE_INCOMPLETE
    )
    return StatisticalFreezeAssessment(
        status=status,
        missing_fields=missing,
        refusal_reasons=tuple(refusal_reasons),
        registered_sign_convention=REGISTERED_SIGN_CONVENTION,
    )


def w16_holdout_status(manifest: Mapping[str, Any] | None) -> HoldoutStatus:
    """Read the W16 lock record; a W19 ledger never releases it."""
    if not isinstance(manifest, Mapping):
        return HoldoutStatus(HOLDOUT_UNKNOWN, None, None, None)
    split_identity = manifest.get("split_identity")
    if not isinstance(split_identity, Mapping):
        return HoldoutStatus(HOLDOUT_UNKNOWN, None, None, None)
    locked_test = split_identity.get("locked_test")
    if not isinstance(locked_test, Mapping):
        return HoldoutStatus(HOLDOUT_UNKNOWN, None, None, None)
    opened_at = locked_test.get("opened_at")
    test_partition_used = locked_test.get("test_partition_used")
    opened = bool(opened_at) or test_partition_used is True
    return HoldoutStatus(
        status=HOLDOUT_OPENED if opened else HOLDOUT_NOT_OPENED,
        frozen=locked_test.get("frozen") if isinstance(locked_test.get("frozen"), bool) else None,
        opened_at=opened_at,
        test_partition_used=(
            test_partition_used if isinstance(test_partition_used, bool) else None
        ),
    )


def audit_source_capability(
    paths: Sequence[str | Path], *, display_root: str | Path | None = None
) -> CapabilityAudit:
    """Statically prove that a W19 source tree carries no outcome-analysis code."""
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
                    if module.split(".")[0] in FORBIDDEN_IMPORT_ROOTS:
                        findings.append(
                            CapabilityFinding(str(path), node.lineno, "FORBIDDEN_IMPORT", module)
                        )
                    if module.startswith(FORBIDDEN_MODULE_PREFIXES):
                        findings.append(
                            CapabilityFinding(str(path), node.lineno, "FORBIDDEN_IMPORT", module)
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".")[0] in FORBIDDEN_IMPORT_ROOTS:
                    findings.append(
                        CapabilityFinding(str(path), node.lineno, "FORBIDDEN_IMPORT", module)
                    )
                if module.startswith(FORBIDDEN_MODULE_PREFIXES):
                    findings.append(
                        CapabilityFinding(str(path), node.lineno, "FORBIDDEN_IMPORT", module)
                    )
                for alias in node.names:
                    if alias.name in FORBIDDEN_CALL_NAMES:
                        findings.append(
                            CapabilityFinding(
                                str(path), node.lineno, "FORBIDDEN_IMPORT", alias.name
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
                        CapabilityFinding(str(path), node.lineno, "FORBIDDEN_CALL", name)
                    )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if FORBIDDEN_DEFINITION_PATTERN.match(node.name):
                    findings.append(
                        CapabilityFinding(
                            str(path), node.lineno, "FORBIDDEN_DEFINITION", node.name
                        )
                    )
    return CapabilityAudit(
        files_scanned=tuple(scanned),
        findings=tuple(findings),
        passed=not findings,
    )
