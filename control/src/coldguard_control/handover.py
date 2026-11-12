"""Week 24 final control/security handover assessment.

Pure decision module for Doc 05D section 56 (D-W24-01..D-W24-04).
Implements policy-freeze archive coverage assessment, non-destructive smoke
matrix, and final handover completeness verification.

Key principles:
- No new safety/security feature added in W24.
- Pure assessment only, no archive writes or execution.
- Distinguish host-validated manifest from live independent execution.
- Do not claim final handover complete by default.
- Another member (not D) must execute runbook while D observes.
- Every undocumented control assumption is a blocking defect.

Handover coverage areas:
- safety hierarchy
- policy state machine
- Controller A/B
- command matrix
- verification rules
- SAFE_LOCAL
- threat model
- security config requirements
- negative-test matrix
- resilience evidence
- residual-risk register
- defense runbook
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Sequence


class HandoverAuthority(str, Enum):
    """Authority level for handover evidence."""

    HOST_VALIDATED = "HOST_VALIDATED"
    LIVE_INDEPENDENT = "LIVE_INDEPENDENT"


class HandoverCoverageArea(str, Enum):
    """Required final handover coverage areas per Doc 05D section 56."""

    SAFETY_HIERARCHY = "SAFETY_HIERARCHY"
    POLICY_STATE_MACHINE = "POLICY_STATE_MACHINE"
    CONTROLLER_A = "CONTROLLER_A"
    CONTROLLER_B = "CONTROLLER_B"
    COMMAND_MATRIX = "COMMAND_MATRIX"
    VERIFICATION_RULES = "VERIFICATION_RULES"
    SAFE_LOCAL = "SAFE_LOCAL"
    THREAT_MODEL = "THREAT_MODEL"
    SECURITY_CONFIG = "SECURITY_CONFIG"
    NEGATIVE_TEST_MATRIX = "NEGATIVE_TEST_MATRIX"
    RESILIENCE_EVIDENCE = "RESILIENCE_EVIDENCE"
    RESIDUAL_RISK_REGISTER = "RESIDUAL_RISK_REGISTER"
    DEFENSE_RUNBOOK = "DEFENSE_RUNBOOK"


class FreezeArchiveComponent(str, Enum):
    """Policy freeze archive components per D-W24-01."""

    CONTROLLER_A_CONFIG = "CONTROLLER_A_CONFIG"
    CONTROLLER_B_CONFIG = "CONTROLLER_B_CONFIG"
    POLICY_VERSION = "POLICY_VERSION"
    REASON_CODES = "REASON_CODES"
    FRESHNESS = "FRESHNESS"
    SAFE_LOCAL = "SAFE_LOCAL"


class SmokeTestCase(str, Enum):
    """Non-destructive smoke test cases per D-W24-02."""

    EXPIRED_COMMAND = "EXPIRED_COMMAND"
    DUPLICATE_COMMAND = "DUPLICATE_COMMAND"
    UNAUTHORIZED_COMMAND = "UNAUTHORIZED_COMMAND"
    SAFE_LOCAL_TRANSITION = "SAFE_LOCAL_TRANSITION"


class SmokeTestOutcome(str, Enum):
    """Required outcomes for smoke test cases."""

    REJECTED = "REJECTED"
    NO_ACTUATION = "NO_ACTUATION"
    AUDIT_EVENT = "AUDIT_EVENT"
    NO_DUPLICATE_EFFECT = "NO_DUPLICATE_EFFECT"
    ACL_DENIED = "ACL_DENIED"
    MODE_TRANSITION = "MODE_TRANSITION"
    LOCAL_PROTECTION_ACTIVE = "LOCAL_PROTECTION_ACTIVE"


REQUIRED_SMOKE_OUTCOMES: Mapping[
    SmokeTestCase, frozenset[SmokeTestOutcome]
] = MappingProxyType({
    SmokeTestCase.EXPIRED_COMMAND: frozenset({
        SmokeTestOutcome.REJECTED,
        SmokeTestOutcome.NO_ACTUATION,
        SmokeTestOutcome.AUDIT_EVENT,
    }),
    SmokeTestCase.DUPLICATE_COMMAND: frozenset({
        SmokeTestOutcome.NO_DUPLICATE_EFFECT,
    }),
    SmokeTestCase.UNAUTHORIZED_COMMAND: frozenset({
        SmokeTestOutcome.ACL_DENIED,
        SmokeTestOutcome.NO_ACTUATION,
    }),
    SmokeTestCase.SAFE_LOCAL_TRANSITION: frozenset({
        SmokeTestOutcome.MODE_TRANSITION,
        SmokeTestOutcome.LOCAL_PROTECTION_ACTIVE,
    }),
})


class RunbookExecutionStatus(str, Enum):
    """Status of runbook execution per D-W24-03."""

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED_OBSERVED = "COMPLETED_OBSERVED"
    COMPLETED_UNOBSERVED = "COMPLETED_UNOBSERVED"


class ControlAssumptionStatus(str, Enum):
    """Status of a control assumption documentation check."""

    DOCUMENTED = "DOCUMENTED"
    UNDOCUMENTED_BLOCKING = "UNDOCUMENTED_BLOCKING"
    UNDOCUMENTED_MINOR = "UNDOCUMENTED_MINOR"


@dataclass(frozen=True, slots=True)
class FreezeArchiveEntry:
    """One component of the policy freeze archive (D-W24-01)."""

    component: FreezeArchiveComponent
    version: str
    authority: HandoverAuthority
    checksum_sha256: str | None = None
    location_path: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.component, FreezeArchiveComponent):
            raise TypeError("component must be a FreezeArchiveComponent")
        if not self.version or not self.version.strip():
            raise ValueError("version must be nonempty")
        if not isinstance(self.authority, HandoverAuthority):
            raise TypeError("authority must be a HandoverAuthority")
        if self.checksum_sha256 is not None:
            if not isinstance(self.checksum_sha256, str) or not self.checksum_sha256.strip():
                raise ValueError("checksum_sha256 must be nonempty if provided")
        if self.location_path is not None:
            if not isinstance(self.location_path, str) or not self.location_path.strip():
                raise ValueError("location_path must be nonempty if provided")


@dataclass(frozen=True, slots=True)
class FreezeArchiveAssessment:
    """Assessment of the complete policy freeze archive."""

    entries: tuple[FreezeArchiveEntry, ...]
    missing_components: tuple[FreezeArchiveComponent, ...]
    all_components_present: bool
    has_live_independent: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SmokeTestEvidence:
    """Evidence for one smoke test case (D-W24-02)."""

    test_case: SmokeTestCase
    authority: HandoverAuthority
    observed_outcomes: frozenset[SmokeTestOutcome]
    destructive: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.test_case, SmokeTestCase):
            raise TypeError("test_case must be a SmokeTestCase")
        if not isinstance(self.authority, HandoverAuthority):
            raise TypeError("authority must be a HandoverAuthority")
        if not isinstance(self.observed_outcomes, frozenset):
            raise TypeError("observed_outcomes must be a frozenset")
        if not all(
            isinstance(outcome, SmokeTestOutcome)
            for outcome in self.observed_outcomes
        ):
            raise TypeError("observed_outcomes must contain SmokeTestOutcome values")
        if not isinstance(self.destructive, bool):
            raise TypeError("destructive must be a strict boolean")
        if self.destructive:
            raise ValueError("destructive tests are not allowed in W24 smoke matrix")


@dataclass(frozen=True, slots=True)
class SmokeTestAssessment:
    """Assessment for one smoke test case."""

    test_case: SmokeTestCase
    authority: HandoverAuthority
    passed: bool
    missing_outcomes: tuple[SmokeTestOutcome, ...]
    destructive: bool


@dataclass(frozen=True, slots=True)
class SmokeMatrixDecision:
    """Aggregate smoke matrix decision (D-W24-02)."""

    assessments: tuple[SmokeTestAssessment, ...]
    missing_cases: tuple[SmokeTestCase, ...]
    failed_cases: tuple[SmokeTestCase, ...]
    all_cases_pass: bool
    has_live_independent: bool
    any_destructive: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunbookExecutionRecord:
    """Record of runbook execution by another member (D-W24-03)."""

    executor_member: str  # e.g., "A", "B", "C" (not "D")
    status: RunbookExecutionStatus
    authority: HandoverAuthority = HandoverAuthority.HOST_VALIDATED
    observer_member: str | None = None  # Should be "D"
    undocumented_assumptions: tuple[str, ...] = ()
    blocking_defects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.executor_member, str):
            raise TypeError("executor_member must be a string")
        if self.executor_member not in {"A", "B", "C"}:
            raise ValueError("executor must be member A, B, or C; not D")
        if not isinstance(self.status, RunbookExecutionStatus):
            raise TypeError("status must be a RunbookExecutionStatus")
        if not isinstance(self.authority, HandoverAuthority):
            raise TypeError("authority must be a HandoverAuthority")
        if self.observer_member is not None:
            if not isinstance(self.observer_member, str) or not self.observer_member.strip():
                raise ValueError("observer_member must be nonempty if provided")
        if not isinstance(self.undocumented_assumptions, tuple):
            raise TypeError("undocumented_assumptions must be a tuple")
        if not isinstance(self.blocking_defects, tuple):
            raise TypeError("blocking_defects must be a tuple")


@dataclass(frozen=True, slots=True)
class CoverageAreaEntry:
    """One handover coverage area with its status."""

    area: HandoverCoverageArea
    documented: bool
    evidence_authority: HandoverAuthority
    location_path: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.area, HandoverCoverageArea):
            raise TypeError("area must be a HandoverCoverageArea")
        if not isinstance(self.documented, bool):
            raise TypeError("documented must be a strict boolean")
        if not isinstance(self.evidence_authority, HandoverAuthority):
            raise TypeError("evidence_authority must be a HandoverAuthority")
        if self.location_path is not None:
            if not isinstance(self.location_path, str) or not self.location_path.strip():
                raise ValueError("location_path must be nonempty if provided")
        if self.notes is not None:
            if not isinstance(self.notes, str):
                raise TypeError("notes must be a string if provided")


@dataclass(frozen=True, slots=True)
class HandoverCompletenessDecision:
    """Final handover completeness decision (D-W24-04)."""

    freeze_archive: FreezeArchiveAssessment | None
    smoke_matrix: SmokeMatrixDecision | None
    runbook_execution: RunbookExecutionRecord | None
    coverage_areas: tuple[CoverageAreaEntry, ...]

    freeze_archive_complete: bool
    smoke_matrix_complete: bool
    runbook_execution_valid: bool
    all_coverage_documented: bool
    no_blocking_defects: bool
    live_independent_evidence: bool

    handover_complete: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.freeze_archive_complete, bool):
            raise TypeError("freeze_archive_complete must be a strict boolean")
        if not isinstance(self.smoke_matrix_complete, bool):
            raise TypeError("smoke_matrix_complete must be a strict boolean")
        if not isinstance(self.runbook_execution_valid, bool):
            raise TypeError("runbook_execution_valid must be a strict boolean")
        if not isinstance(self.all_coverage_documented, bool):
            raise TypeError("all_coverage_documented must be a strict boolean")
        if not isinstance(self.no_blocking_defects, bool):
            raise TypeError("no_blocking_defects must be a strict boolean")
        if not isinstance(self.live_independent_evidence, bool):
            raise TypeError("live_independent_evidence must be a strict boolean")
        if not isinstance(self.handover_complete, bool):
            raise TypeError("handover_complete must be a strict boolean")
        if not isinstance(self.blockers, tuple):
            raise TypeError("blockers must be a tuple")


def assess_freeze_archive(
    entries: Sequence[FreezeArchiveEntry],
) -> FreezeArchiveAssessment:
    """Assess the policy freeze archive completeness (D-W24-01).

    Args:
        entries: Freeze archive entries supplied by caller.

    Returns:
        FreezeArchiveAssessment with completeness status.
    """
    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        raise TypeError("entries must be a Sequence of FreezeArchiveEntry")

    by_component: dict[FreezeArchiveComponent, FreezeArchiveEntry] = {}
    for item in entries:
        if not isinstance(item, FreezeArchiveEntry):
            raise TypeError("each entry must be a FreezeArchiveEntry")
        if item.component in by_component:
            raise ValueError(f"duplicate component: {item.component.value}")
        by_component[item.component] = item

    missing = tuple(
        comp for comp in FreezeArchiveComponent
        if comp not in by_component
    )
    all_present = len(missing) == 0
    has_live = any(
        item.authority is HandoverAuthority.LIVE_INDEPENDENT
        for item in entries
    )

    blockers: list[str] = []
    blockers.extend(f"MISSING_COMPONENT:{comp.value}" for comp in missing)
    if all_present and not has_live:
        blockers.append("NO_LIVE_INDEPENDENT_EVIDENCE_IN_ARCHIVE")

    return FreezeArchiveAssessment(
        entries=tuple(entries),
        missing_components=missing,
        all_components_present=all_present,
        has_live_independent=has_live,
        blockers=tuple(blockers),
    )


def assess_smoke_matrix(
    evidence: Sequence[SmokeTestEvidence],
) -> SmokeMatrixDecision:
    """Assess the non-destructive smoke matrix (D-W24-02).

    Args:
        evidence: Smoke test evidence supplied by caller.

    Returns:
        SmokeMatrixDecision with pass/fail status.
    """
    if isinstance(evidence, (str, bytes)) or not isinstance(evidence, Sequence):
        raise TypeError("evidence must be a Sequence of SmokeTestEvidence")

    by_case: dict[SmokeTestCase, SmokeTestEvidence] = {}
    for item in evidence:
        if not isinstance(item, SmokeTestEvidence):
            raise TypeError("each item must be SmokeTestEvidence")
        if item.test_case in by_case:
            raise ValueError(f"duplicate test case: {item.test_case.value}")
        by_case[item.test_case] = item

    assessments: list[SmokeTestAssessment] = []
    for case in SmokeTestCase:
        item = by_case.get(case)
        if item is None:
            continue
        missing = tuple(
            sorted(
                REQUIRED_SMOKE_OUTCOMES[case] - item.observed_outcomes,
                key=lambda outcome: outcome.value,
            )
        )
        assessments.append(
            SmokeTestAssessment(
                test_case=case,
                authority=item.authority,
                passed=not missing,
                missing_outcomes=missing,
                destructive=item.destructive,
            )
        )

    missing_cases = tuple(case for case in SmokeTestCase if case not in by_case)
    failed_cases = tuple(item.test_case for item in assessments if not item.passed)
    all_pass = not missing_cases and not failed_cases
    has_live = any(
        item.authority is HandoverAuthority.LIVE_INDEPENDENT
        for item in assessments
    )
    any_destructive = any(item.destructive for item in assessments)

    blockers: list[str] = []
    blockers.extend(f"MISSING_CASE:{case.value}" for case in missing_cases)
    for item in assessments:
        for outcome in item.missing_outcomes:
            blockers.append(f"MISSING_OUTCOME:{item.test_case.value}:{outcome.value}")
    if any_destructive:
        blockers.append("DESTRUCTIVE_TEST_NOT_ALLOWED_IN_W24")

    return SmokeMatrixDecision(
        assessments=tuple(assessments),
        missing_cases=missing_cases,
        failed_cases=failed_cases,
        all_cases_pass=all_pass,
        has_live_independent=has_live,
        any_destructive=any_destructive,
        blockers=tuple(blockers),
    )


def assess_runbook_execution(
    record: RunbookExecutionRecord,
) -> RunbookExecutionRecord:
    """Validate runbook execution by another member (D-W24-03).

    Args:
        record: Runbook execution record.

    Returns:
        The same record if valid.

    Raises:
        ValueError: If blocking defects exist.
    """
    if not isinstance(record, RunbookExecutionRecord):
        raise TypeError("record must be a RunbookExecutionRecord")

    if record.status is not RunbookExecutionStatus.COMPLETED_OBSERVED:
        return record

    if record.observer_member != "D":
        raise ValueError("observer must be D for COMPLETED_OBSERVED status")

    if record.blocking_defects:
        raise ValueError(
            f"blocking defects prevent completion: {record.blocking_defects}"
        )
    if record.undocumented_assumptions:
        raise ValueError(
            "undocumented assumptions prevent completion: "
            f"{record.undocumented_assumptions}"
        )

    return record


def assess_handover_completeness(
    freeze_archive: FreezeArchiveAssessment | None,
    smoke_matrix: SmokeMatrixDecision | None,
    runbook_execution: RunbookExecutionRecord | None,
    coverage_areas: Sequence[CoverageAreaEntry],
) -> HandoverCompletenessDecision:
    """Assess final handover completeness (D-W24-04).

    Args:
        freeze_archive: Policy freeze archive assessment.
        smoke_matrix: Smoke matrix assessment.
        runbook_execution: Runbook execution record.
        coverage_areas: Handover coverage area entries.

    Returns:
        HandoverCompletenessDecision with overall completion status.
    """
    if isinstance(coverage_areas, (str, bytes)) or not isinstance(
        coverage_areas, Sequence
    ):
        raise TypeError("coverage_areas must be a Sequence of CoverageAreaEntry")

    areas_list: list[CoverageAreaEntry] = []
    areas_seen: set[HandoverCoverageArea] = set()
    for item in coverage_areas:
        if not isinstance(item, CoverageAreaEntry):
            raise TypeError("each area must be a CoverageAreaEntry")
        if item.area in areas_seen:
            raise ValueError(f"duplicate coverage area: {item.area.value}")
        areas_seen.add(item.area)
        areas_list.append(item)

    freeze_complete = (
        freeze_archive is not None
        and freeze_archive.all_components_present
    )
    smoke_complete = (
        smoke_matrix is not None
        and smoke_matrix.all_cases_pass
        and not smoke_matrix.any_destructive
    )
    runbook_valid = (
        runbook_execution is not None
        and runbook_execution.status is RunbookExecutionStatus.COMPLETED_OBSERVED
        and not runbook_execution.blocking_defects
        and not runbook_execution.undocumented_assumptions
        and runbook_execution.observer_member == "D"
    )
    missing_coverage = tuple(
        area for area in HandoverCoverageArea if area not in areas_seen
    )
    all_documented = (
        not missing_coverage and all(area.documented for area in areas_list)
    )
    no_blocking = (
        runbook_execution is None
        or (
            not runbook_execution.blocking_defects
            and not runbook_execution.undocumented_assumptions
        )
    )
    live_evidence = (
        runbook_valid
        and runbook_execution is not None
        and runbook_execution.authority is HandoverAuthority.LIVE_INDEPENDENT
    )

    handover_complete = (
        freeze_complete
        and smoke_complete
        and runbook_valid
        and all_documented
        and no_blocking
        and live_evidence
    )

    blockers: list[str] = []
    if not freeze_complete:
        if freeze_archive is None:
            blockers.append("FREEZE_ARCHIVE_NOT_ASSESSED")
        else:
            blockers.extend(freeze_archive.blockers)
    if not smoke_complete:
        if smoke_matrix is None:
            blockers.append("SMOKE_MATRIX_NOT_ASSESSED")
        else:
            blockers.extend(smoke_matrix.blockers)
    if not runbook_valid:
        if runbook_execution is None:
            blockers.append("RUNBOOK_EXECUTION_NOT_RECORDED")
        elif runbook_execution.status is not RunbookExecutionStatus.COMPLETED_OBSERVED:
            blockers.append(
                f"RUNBOOK_STATUS:{runbook_execution.status.value}"
            )
        elif runbook_execution.blocking_defects:
            blockers.extend(
                f"BLOCKING_DEFECT:{d}" for d in runbook_execution.blocking_defects
            )
        elif runbook_execution.undocumented_assumptions:
            blockers.extend(
                f"UNDOCUMENTED_ASSUMPTION:{assumption}"
                for assumption in runbook_execution.undocumented_assumptions
            )
    if not all_documented:
        blockers.extend(
            f"MISSING_COVERAGE_AREA:{area.value}" for area in missing_coverage
        )
        missing_areas = [
            area.area.value for area in areas_list if not area.documented
        ]
        blockers.extend(f"UNDOCUMENTED_AREA:{a}" for a in missing_areas)
    if not no_blocking:
        blockers.append("BLOCKING_DEFECTS_EXIST")
    if not live_evidence:
        blockers.append("NO_LIVE_INDEPENDENT_EVIDENCE")

    return HandoverCompletenessDecision(
        freeze_archive=freeze_archive,
        smoke_matrix=smoke_matrix,
        runbook_execution=runbook_execution,
        coverage_areas=tuple(areas_list),
        freeze_archive_complete=freeze_complete,
        smoke_matrix_complete=smoke_complete,
        runbook_execution_valid=runbook_valid,
        all_coverage_documented=all_documented,
        no_blocking_defects=no_blocking,
        live_independent_evidence=live_evidence,
        handover_complete=handover_complete,
        blockers=tuple(blockers),
    )


def build_default_coverage_areas(
    authority: HandoverAuthority = HandoverAuthority.HOST_VALIDATED,
) -> tuple[CoverageAreaEntry, ...]:
    """Build default coverage area entries with all areas documented.

    Args:
        authority: Authority level for all entries.

    Returns:
        Tuple of CoverageAreaEntry for all required areas.
    """
    return tuple(
        CoverageAreaEntry(
            area=area,
            documented=True,
            evidence_authority=authority,
        )
        for area in HandoverCoverageArea
    )


def build_default_freeze_archive(
    authority: HandoverAuthority = HandoverAuthority.HOST_VALIDATED,
) -> tuple[FreezeArchiveEntry, ...]:
    """Build default freeze archive entries with placeholder versions.

    Args:
        authority: Authority level for all entries.

    Returns:
        Tuple of FreezeArchiveEntry for all required components.
    """
    return tuple(
        FreezeArchiveEntry(
            component=comp,
            version="v1.0.0-W24",
            authority=authority,
        )
        for comp in FreezeArchiveComponent
    )


def build_default_smoke_evidence(
    authority: HandoverAuthority = HandoverAuthority.HOST_VALIDATED,
) -> tuple[SmokeTestEvidence, ...]:
    """Build default smoke test evidence with all outcomes present.

    Args:
        authority: Authority level for all entries.

    Returns:
        Tuple of SmokeTestEvidence for all required cases.
    """
    return tuple(
        SmokeTestEvidence(
            test_case=case,
            authority=authority,
            observed_outcomes=REQUIRED_SMOKE_OUTCOMES[case],
        )
        for case in SmokeTestCase
    )
