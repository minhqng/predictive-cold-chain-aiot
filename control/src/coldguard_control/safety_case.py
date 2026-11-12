"""Week 22 final safety case and residual-risk analysis.

This pure decision module converts all tests into a concise defensible
safety/resilience argument per Doc 05D section 54 (D-W22-01..D-W22-04).

The module:
- models hazard→invariant→test entries with explicit PASS/FAIL/PENDING;
- tracks residual risks with nonempty mitigation/limitation;
- uses qualitative severity and likelihood enums only (no numerical probability);
- gates optional-scope decisions on all core matrix entries passing and all
  core evidence being green.

It never claims live evidence, performs physical tests, or modifies evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Sequence

from .negative_campaign import EvidenceAuthority


class Severity(str, Enum):
    """Qualitative severity levels for hazards and residual risks."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Likelihood(str, Enum):
    """Qualitative likelihood levels for hazards and residual risks."""

    RARE = "RARE"
    UNLIKELY = "UNLIKELY"
    POSSIBLE = "POSSIBLE"
    LIKELY = "LIKELY"
    ALMOST_CERTAIN = "ALMOST_CERTAIN"


class MatrixResult(str, Enum):
    """Explicit test result for a hazard/invariant/test entry."""

    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"


class HazardCategory(str, Enum):
    """Categories of hazards per Doc 05D hazard ledger."""

    COMMAND_INTEGRITY = "COMMAND_INTEGRITY"
    SAFETY_HIERARCHY = "SAFETY_HIERARCHY"
    SECURITY_THREAT = "SECURITY_THREAT"
    RESILIENCE_FAILURE = "RESILIENCE_FAILURE"
    PHYSICAL_VERIFICATION = "PHYSICAL_VERIFICATION"
    LOCAL_PROTECTION = "LOCAL_PROTECTION"


@dataclass(frozen=True, slots=True)
class SafetyMatrixEntry:
    """One row in the hazard→invariant→test matrix (D-W22-01)."""

    hazard_id: str
    hazard_description: str
    hazard_category: HazardCategory
    severity: Severity
    invariant: str
    test_id: str
    test_description: str
    result: MatrixResult
    evidence_authority: EvidenceAuthority = field(default=EvidenceAuthority.HOST_SIMULATED)

    def __post_init__(self) -> None:
        if not self.hazard_id or not self.hazard_id.strip():
            raise ValueError("hazard_id must be nonempty")
        if not self.hazard_description or not self.hazard_description.strip():
            raise ValueError("hazard_description must be nonempty")
        if not self.invariant or not self.invariant.strip():
            raise ValueError("invariant must be nonempty")
        if not self.test_id or not self.test_id.strip():
            raise ValueError("test_id must be nonempty")
        if not self.test_description or not self.test_description.strip():
            raise ValueError("test_description must be nonempty")
        if not isinstance(self.hazard_category, HazardCategory):
            raise TypeError("hazard_category must be a HazardCategory")
        if not isinstance(self.severity, Severity):
            raise TypeError("severity must be a Severity")
        if not isinstance(self.result, MatrixResult):
            raise TypeError("result must be a MatrixResult")
        if not isinstance(self.evidence_authority, EvidenceAuthority):
            raise TypeError("evidence_authority must be an EvidenceAuthority")


@dataclass(frozen=True, slots=True)
class ResidualRisk:
    """One residual risk entry with required mitigation and limitation (D-W22-02)."""

    risk_id: str
    risk_description: str
    severity: Severity
    likelihood: Likelihood
    mitigation: str
    limitation: str

    def __post_init__(self) -> None:
        if not self.risk_id or not self.risk_id.strip():
            raise ValueError("risk_id must be nonempty")
        if not self.risk_description or not self.risk_description.strip():
            raise ValueError("risk_description must be nonempty")
        if not isinstance(self.severity, Severity):
            raise TypeError("severity must be a Severity")
        if not isinstance(self.likelihood, Likelihood):
            raise TypeError("likelihood must be a Likelihood")
        if not self.mitigation or not self.mitigation.strip():
            raise ValueError("mitigation must be nonempty")
        if not self.limitation or not self.limitation.strip():
            raise ValueError("limitation must be nonempty")


@dataclass(frozen=True, slots=True)
class OptionalScopeItem:
    """One optional-scope item (Secure Boot, Flash Encryption, PWM policy)."""

    item_id: str
    item_name: str
    description: str
    core_prerequisite_met: bool
    status: str  # e.g., "NOT_STARTED", "RESEARCH_ONLY", "LAB_PLAN_DRAFTED"

    def __post_init__(self) -> None:
        if not self.item_id or not self.item_id.strip():
            raise ValueError("item_id must be nonempty")
        if not self.item_name or not self.item_name.strip():
            raise ValueError("item_name must be nonempty")
        if not self.description or not self.description.strip():
            raise ValueError("description must be nonempty")
        if not isinstance(self.core_prerequisite_met, bool):
            raise TypeError("core_prerequisite_met must be a strict boolean")
        if not self.status or not self.status.strip():
            raise ValueError("status must be nonempty")


@dataclass(frozen=True, slots=True)
class SafetyCaseSummary:
    """Aggregate safety case decision (D-W22-01..D-W22-04)."""

    matrix_entries: tuple[SafetyMatrixEntry, ...]
    residual_risks: tuple[ResidualRisk, ...]
    optional_scope_items: tuple[OptionalScopeItem, ...]

    passed_entries: tuple[SafetyMatrixEntry, ...]
    failed_entries: tuple[SafetyMatrixEntry, ...]
    pending_entries: tuple[SafetyMatrixEntry, ...]

    core_matrix_all_pass: bool
    core_evidence_green: bool
    optional_scope_allowed: bool

    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.matrix_entries, tuple):
            raise TypeError("matrix_entries must be a tuple")
        if not isinstance(self.residual_risks, tuple):
            raise TypeError("residual_risks must be a tuple")
        if not isinstance(self.optional_scope_items, tuple):
            raise TypeError("optional_scope_items must be a tuple")
        if not isinstance(self.passed_entries, tuple):
            raise TypeError("passed_entries must be a tuple")
        if not isinstance(self.failed_entries, tuple):
            raise TypeError("failed_entries must be a tuple")
        if not isinstance(self.pending_entries, tuple):
            raise TypeError("pending_entries must be a tuple")
        if not isinstance(self.core_matrix_all_pass, bool):
            raise TypeError("core_matrix_all_pass must be a strict boolean")
        if not isinstance(self.core_evidence_green, bool):
            raise TypeError("core_evidence_green must be a strict boolean")
        if not isinstance(self.optional_scope_allowed, bool):
            raise TypeError("optional_scope_allowed must be a strict boolean")
        if not isinstance(self.blockers, tuple):
            raise TypeError("blockers must be a tuple")


def _categorize_entries(
    entries: Sequence[SafetyMatrixEntry],
) -> tuple[
    tuple[SafetyMatrixEntry, ...],
    tuple[SafetyMatrixEntry, ...],
    tuple[SafetyMatrixEntry, ...],
]:
    """Categorize entries by result."""
    passed = []
    failed = []
    pending = []
    for entry in entries:
        if entry.result is MatrixResult.PASS:
            passed.append(entry)
        elif entry.result is MatrixResult.FAIL:
            failed.append(entry)
        else:
            pending.append(entry)
    return (tuple(passed), tuple(failed), tuple(pending))


def _check_core_evidence_green(entries: Sequence[SafetyMatrixEntry]) -> bool:
    """Check if all core matrix entries have at least HOST_SIMULATED evidence."""
    if not entries:
        return False
    for entry in entries:
        if entry.evidence_authority not in (
            EvidenceAuthority.HOST_SIMULATED,
            EvidenceAuthority.LIVE_EVIDENCE,
        ):
            return False
    return True


def _check_optional_prerequisites(
    entries: Sequence[SafetyMatrixEntry],
) -> bool:
    """Check if all core matrix entries pass (prerequisite for optional scope)."""
    if not entries:
        return False
    return all(entry.result is MatrixResult.PASS for entry in entries)


def assess_safety_case(
    matrix_entries: Sequence[SafetyMatrixEntry],
    residual_risks: Sequence[ResidualRisk],
    optional_scope_items: Sequence[OptionalScopeItem] | None = None,
) -> SafetyCaseSummary:
    """Assess the complete W22 safety case (D-W22-01..D-W22-04).

    Args:
        matrix_entries: Hazard→invariant→test entries.
        residual_risks: Residual risks with mitigation/limitation.
        optional_scope_items: Optional items (Secure Boot, Flash Encryption, PWM).

    Returns:
        SafetyCaseSummary with categorization and gating decisions.

    Raises:
        TypeError: If inputs have wrong types.
        ValueError: If residual_risks is empty or any entry is invalid.
    """
    if isinstance(matrix_entries, (str, bytes)) or not isinstance(
        matrix_entries, Sequence
    ):
        raise TypeError("matrix_entries must be a Sequence of SafetyMatrixEntry")
    if isinstance(residual_risks, (str, bytes)) or not isinstance(
        residual_risks, Sequence
    ):
        raise TypeError("residual_risks must be a Sequence of ResidualRisk")
    if not residual_risks:
        raise ValueError("residual_risks must be nonempty (D-W22-02)")

    entries_list: list[SafetyMatrixEntry] = []
    for item in matrix_entries:
        if not isinstance(item, SafetyMatrixEntry):
            raise TypeError("each matrix entry must be a SafetyMatrixEntry")
        entries_list.append(item)

    risks_list: list[ResidualRisk] = []
    for item in residual_risks:
        if not isinstance(item, ResidualRisk):
            raise TypeError("each residual risk must be a ResidualRisk")
        risks_list.append(item)

    optional_list: list[OptionalScopeItem] = []
    if optional_scope_items is not None:
        if isinstance(optional_scope_items, (str, bytes)) or not isinstance(
            optional_scope_items, Sequence
        ):
            raise TypeError(
                "optional_scope_items must be a Sequence of OptionalScopeItem"
            )
        for item in optional_scope_items:
            if not isinstance(item, OptionalScopeItem):
                raise TypeError("each optional item must be an OptionalScopeItem")
            optional_list.append(item)

    passed, failed, pending = _categorize_entries(entries_list)
    core_matrix_all_pass = len(failed) == 0 and len(pending) == 0 and len(passed) > 0
    core_evidence_green = _check_core_evidence_green(entries_list)
    optional_prerequisites_met = all(
        item.core_prerequisite_met for item in optional_list
    )
    optional_scope_allowed = (
        core_matrix_all_pass
        and core_evidence_green
        and optional_prerequisites_met
    )

    blockers: list[str] = []
    if failed:
        blockers.extend(f"FAILED_ENTRY:{e.hazard_id}" for e in failed)
    if pending:
        blockers.extend(f"PENDING_ENTRY:{e.hazard_id}" for e in pending)
    if not passed:
        blockers.append("NO_PASSING_ENTRIES")
    if not core_evidence_green:
        blockers.append("CORE_EVIDENCE_NOT_GREEN")
    for opt in optional_list:
        if not opt.core_prerequisite_met:
            blockers.append(
                f"OPTIONAL_SCOPE_NOT_ALLOWED:{opt.item_id} "
                "(prerequisite not confirmed)"
            )

    return SafetyCaseSummary(
        matrix_entries=tuple(entries_list),
        residual_risks=tuple(risks_list),
        optional_scope_items=tuple(optional_list),
        passed_entries=passed,
        failed_entries=failed,
        pending_entries=pending,
        core_matrix_all_pass=core_matrix_all_pass,
        core_evidence_green=core_evidence_green,
        optional_scope_allowed=optional_scope_allowed,
        blockers=tuple(blockers),
    )


DEFAULT_CORE_HAZARDS: Mapping[HazardCategory, Sequence[dict]] = MappingProxyType({
    HazardCategory.COMMAND_INTEGRITY: [
        {
            "hazard_id": "CTRL-STALE-01",
            "hazard_description": "Stale command causes unintended actuation",
            "severity": Severity.HIGH,
            "invariant": "Expired commands are rejected with no actuation",
            "test_id": "SEC-EXP-01",
            "test_description": "Send expired command; verify REJECTED + NO_ACTUATION",
        },
        {
            "hazard_id": "CTRL-DUP-01",
            "hazard_description": "Duplicate command causes repeated physical action",
            "severity": Severity.HIGH,
            "invariant": "Idempotent command handling prevents duplicate effect",
            "test_id": "CTRL-IDEM-01",
            "test_description": "Send same command_id twice; verify single physical effect",
        },
    ],
    HazardCategory.RESILIENCE_FAILURE: [
        {
            "hazard_id": "RES-CLOUD-01",
            "hazard_description": "Cloud/broker outage removes all protection",
            "severity": Severity.CRITICAL,
            "invariant": "SAFE_LOCAL provides local deterministic protection",
            "test_id": "RES-SL-01",
            "test_description": "Disconnect broker; verify SAFE_LOCAL entry + local control",
        },
        {
            "hazard_id": "RES-AI-01",
            "hazard_description": "AI/model unavailable causes unsafe behavior",
            "severity": Severity.HIGH,
            "invariant": "Controller A fallback when prediction unavailable",
            "test_id": "RES-AI-01",
            "test_description": "Disable prediction; verify reactive/local fallback",
        },
    ],
    HazardCategory.PHYSICAL_VERIFICATION: [
        {
            "hazard_id": "PHYS-ACK-01",
            "hazard_description": "ACK-only success claim without physical verify",
            "severity": Severity.HIGH,
            "invariant": "Physical verification required for success claim",
            "test_id": "CTRL-VER-01",
            "test_description": "Verify electrical + thermal response tracked separately from ACK",
        },
    ],
    HazardCategory.SECURITY_THREAT: [
        {
            "hazard_id": "SEC-UNAUTH-01",
            "hazard_description": "Unauthorized client publishes command",
            "severity": Severity.CRITICAL,
            "invariant": "ACL + authorization deny unauthorized command",
            "test_id": "SEC-ACL-01",
            "test_description": "Use unauthorized credential; verify ACL_DENIED",
        },
    ],
})


def build_default_safety_case(
    result_override: Mapping[str, MatrixResult] | None = None,
    evidence_authority: EvidenceAuthority = EvidenceAuthority.HOST_SIMULATED,
    include_optional: bool = False,
) -> SafetyCaseSummary:
    """Build a default safety case with canonical hazards from Doc 05D.

    Args:
        result_override: Optional mapping from hazard_id to result.
        evidence_authority: Authority for all entries.
        include_optional: Whether to include optional-scope items.

    Returns:
        SafetyCaseSummary with default hazards and residual risks.
    """
    if result_override is None:
        result_override = {}

    entries: list[SafetyMatrixEntry] = []
    for category, hazards in DEFAULT_CORE_HAZARDS.items():
        for h in hazards:
            result = result_override.get(h["hazard_id"], MatrixResult.PASS)
            entries.append(
                SafetyMatrixEntry(
                    hazard_id=h["hazard_id"],
                    hazard_description=h["hazard_description"],
                    hazard_category=category,
                    severity=h["severity"],
                    invariant=h["invariant"],
                    test_id=h["test_id"],
                    test_description=h["test_description"],
                    result=result,
                    evidence_authority=evidence_authority,
                )
            )

    residual_risks = [
        ResidualRisk(
            risk_id="RR-01",
            risk_description="Single physical hardware unit limits fault coverage",
            severity=Severity.MEDIUM,
            likelihood=Likelihood.LIKELY,
            mitigation="Comprehensive simulation and host-based negative testing",
            limitation="Hardware-specific failure modes may remain unobserved",
        ),
        ResidualRisk(
            risk_id="RR-02",
            risk_description="No formal penetration test or security certification",
            severity=Severity.MEDIUM,
            likelihood=Likelihood.POSSIBLE,
            mitigation="Baseline ACL, authorization, TTL, idempotency enforcement",
            limitation="Lab threat model; not production-grade security validation",
        ),
        ResidualRisk(
            risk_id="RR-03",
            risk_description="Optional Secure Boot / Flash Encryption not deployed",
            severity=Severity.LOW,
            likelihood=Likelihood.UNLIKELY,
            mitigation="Security hardening remains optional per Doc 05D section 26",
            limitation="Physical tampering or firmware modification not prevented",
        ),
        ResidualRisk(
            risk_id="RR-04",
            risk_description="Uninstrumented internal TEC junction temperature",
            severity=Severity.LOW,
            likelihood=Likelihood.RARE,
            mitigation="External thermal sensors + electrical verification",
            limitation="Junction overheating may not be directly detected",
        ),
    ]

    optional_items: list[OptionalScopeItem] = []
    if include_optional:
        optional_items = [
            OptionalScopeItem(
                item_id="OPT-01",
                item_name="Secure Boot Research",
                description="ESP32-S3 Secure Boot v2 feasibility study",
                core_prerequisite_met=True,
                status="RESEARCH_ONLY",
            ),
            OptionalScopeItem(
                item_id="OPT-02",
                item_name="Flash Encryption Lab Plan",
                description="Lab plan for Flash Encryption with recovery procedure",
                core_prerequisite_met=True,
                status="LAB_PLAN_DRAFTED",
            ),
            OptionalScopeItem(
                item_id="OPT-03",
                item_name="PWM Energy Policy",
                description="PWM-based energy optimization policy research",
                core_prerequisite_met=True,
                status="NOT_STARTED",
            ),
        ]

    return assess_safety_case(
        matrix_entries=entries,
        residual_risks=residual_risks,
        optional_scope_items=optional_items if include_optional else None,
    )
