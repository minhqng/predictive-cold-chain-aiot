"""Pure Week 21 negative/resilience campaign assessment.

The module records evidence supplied by a caller and never performs transport,
authorization, failover, reconnect, or physical-actuation work itself.  Host
simulation can validate the decision contract, but only live evidence can mark
the final campaign evidence complete.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Sequence


class NegativeCampaignCase(str, Enum):
    """The complete D-W21-01..09 matrix."""

    EXPIRED_COMMAND = "EXPIRED_COMMAND"
    DUPLICATE_COMMAND = "DUPLICATE_COMMAND"
    OUT_OF_RANGE_COMMAND = "OUT_OF_RANGE_COMMAND"
    WRONG_DEVICE_COMMAND = "WRONG_DEVICE_COMMAND"
    UNAUTHORIZED_BROKER_PUBLISH = "UNAUTHORIZED_BROKER_PUBLISH"
    BACKEND_AUTHORIZATION = "BACKEND_AUTHORIZATION"
    NETWORK_BACKEND_OUTAGE = "NETWORK_BACKEND_OUTAGE"
    AI_OUTAGE = "AI_OUTAGE"
    RECONNECT = "RECONNECT"


class EvidenceAuthority(str, Enum):
    """Authority of a result; host simulation cannot claim live completion."""

    HOST_SIMULATED = "HOST_SIMULATED"
    LIVE_EVIDENCE = "LIVE_EVIDENCE"


class NegativeOutcome(str, Enum):
    """Observable outcomes required by the Week 21 matrix."""

    REJECTED = "REJECTED"
    NO_ACTUATION = "NO_ACTUATION"
    AUDIT_EVENT = "AUDIT_EVENT"
    NO_DUPLICATE_PHYSICAL_EFFECT = "NO_DUPLICATE_PHYSICAL_EFFECT"
    ACL_DENIED = "ACL_DENIED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    SAFE_LOCAL_ENTERED = "SAFE_LOCAL_ENTERED"
    REACTIVE_LOCAL_FALLBACK = "REACTIVE_LOCAL_FALLBACK"
    NO_STALE_ACTUATION = "NO_STALE_ACTUATION"


REQUIRED_OUTCOMES: Mapping[
    NegativeCampaignCase, frozenset[NegativeOutcome]
] = MappingProxyType({
    NegativeCampaignCase.EXPIRED_COMMAND: frozenset(
        {
            NegativeOutcome.REJECTED,
            NegativeOutcome.NO_ACTUATION,
            NegativeOutcome.AUDIT_EVENT,
        }
    ),
    NegativeCampaignCase.DUPLICATE_COMMAND: frozenset(
        {NegativeOutcome.NO_DUPLICATE_PHYSICAL_EFFECT}
    ),
    NegativeCampaignCase.OUT_OF_RANGE_COMMAND: frozenset(
        {NegativeOutcome.REJECTED}
    ),
    NegativeCampaignCase.WRONG_DEVICE_COMMAND: frozenset(
        {NegativeOutcome.REJECTED}
    ),
    NegativeCampaignCase.UNAUTHORIZED_BROKER_PUBLISH: frozenset(
        {NegativeOutcome.ACL_DENIED}
    ),
    NegativeCampaignCase.BACKEND_AUTHORIZATION: frozenset(
        {NegativeOutcome.AUTHORIZATION_DENIED, NegativeOutcome.NO_ACTUATION}
    ),
    NegativeCampaignCase.NETWORK_BACKEND_OUTAGE: frozenset(
        {NegativeOutcome.SAFE_LOCAL_ENTERED}
    ),
    NegativeCampaignCase.AI_OUTAGE: frozenset(
        {NegativeOutcome.REACTIVE_LOCAL_FALLBACK}
    ),
    NegativeCampaignCase.RECONNECT: frozenset(
        {NegativeOutcome.NO_STALE_ACTUATION}
    ),
})


@dataclass(frozen=True, slots=True)
class NegativeCaseEvidence:
    """Immutable evidence supplied for one matrix case."""

    case: NegativeCampaignCase
    authority: EvidenceAuthority
    observed_outcomes: frozenset[NegativeOutcome]

    def __post_init__(self) -> None:
        if not isinstance(self.case, NegativeCampaignCase):
            raise TypeError("case must be a NegativeCampaignCase")
        if not isinstance(self.authority, EvidenceAuthority):
            raise TypeError("authority must be an EvidenceAuthority")
        if not isinstance(self.observed_outcomes, frozenset):
            raise TypeError("observed_outcomes must be a frozenset")
        if not all(
            isinstance(outcome, NegativeOutcome)
            for outcome in self.observed_outcomes
        ):
            raise TypeError("observed_outcomes must contain NegativeOutcome values")


@dataclass(frozen=True, slots=True)
class NegativeCaseAssessment:
    """Assessment for one supplied case."""

    case: NegativeCampaignCase
    authority: EvidenceAuthority
    passed: bool
    missing_outcomes: tuple[NegativeOutcome, ...]


@dataclass(frozen=True, slots=True)
class NegativeCampaignDecision:
    """Aggregate Week 21 decision with explicit evidence authority."""

    assessments: tuple[NegativeCaseAssessment, ...]
    missing_cases: tuple[NegativeCampaignCase, ...]
    failed_cases: tuple[NegativeCampaignCase, ...]
    all_cases_pass: bool
    live_evidence_complete: bool
    blockers: tuple[str, ...]
    physical_command_emitted: bool = False


def assess_negative_campaign(
    evidence: Sequence[NegativeCaseEvidence],
) -> NegativeCampaignDecision:
    """Assess the complete W21 matrix without mutating or executing evidence."""
    if isinstance(evidence, (str, bytes)) or not isinstance(evidence, Sequence):
        raise TypeError("evidence must be a Sequence of NegativeCaseEvidence")

    by_case: dict[NegativeCampaignCase, NegativeCaseEvidence] = {}
    for item in evidence:
        if not isinstance(item, NegativeCaseEvidence):
            raise TypeError("each item must be NegativeCaseEvidence")
        if item.case in by_case:
            raise ValueError(f"duplicate campaign case: {item.case.value}")
        by_case[item.case] = item

    assessments: list[NegativeCaseAssessment] = []
    for case in NegativeCampaignCase:
        item = by_case.get(case)
        if item is None:
            continue
        missing = tuple(
            sorted(
                REQUIRED_OUTCOMES[case] - item.observed_outcomes,
                key=lambda outcome: outcome.value,
            )
        )
        assessments.append(
            NegativeCaseAssessment(
                case=case,
                authority=item.authority,
                passed=not missing,
                missing_outcomes=missing,
            )
        )

    missing_cases = tuple(case for case in NegativeCampaignCase if case not in by_case)
    failed_cases = tuple(item.case for item in assessments if not item.passed)
    all_cases_pass = not missing_cases and not failed_cases
    live_evidence_complete = all_cases_pass and all(
        item.authority is EvidenceAuthority.LIVE_EVIDENCE for item in assessments
    )

    blockers: list[str] = []
    blockers.extend(f"MISSING_CASE:{case.value}" for case in missing_cases)
    for item in assessments:
        for outcome in item.missing_outcomes:
            blockers.append(f"MISSING_OUTCOME:{item.case.value}:{outcome.value}")
    if all_cases_pass and not live_evidence_complete:
        blockers.append("LIVE_EVIDENCE_REQUIRED_FOR_FINAL_CAMPAIGN")

    return NegativeCampaignDecision(
        assessments=tuple(assessments),
        missing_cases=missing_cases,
        failed_cases=failed_cases,
        all_cases_pass=all_cases_pass,
        live_evidence_complete=live_evidence_complete,
        blockers=tuple(blockers),
        physical_command_emitted=False,
    )
