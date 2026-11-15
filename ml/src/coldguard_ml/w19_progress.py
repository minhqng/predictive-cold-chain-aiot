"""W19 frozen-target progress accounting and readiness reporting (B-W19-04).

Canonical anchors: Doc 04 §§34-35; Doc 05B §47 B-W19-04; Doc 03 §12, §163.

Progress is arithmetic over verified records, never a scientific verdict.  A
pair target exists only when an explicitly frozen record carries an approval and
a variance/feasibility justification; a planning-table number is never promoted
to a target.  Missing targets stay ``UNKNOWN_UNFROZEN`` and a missing remaining
count stays ``NOT_COMPUTABLE``; neither is silently replaced by zero.

Only physically admitted valid pairs count toward campaign progress.  Synthetic
fixtures are counted separately and never substitute for physical pairs.
Invalid attempts and invalid pairs are reported independently.  This module
cannot authorize a campaign, approve a target or compute an outcome.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from coldguard_ml.w19_no_peeking import FREEZE_FROZEN_APPROVED
from coldguard_ml.w19_pair_ledger import (
    AUTHORIZATION_AUTHORIZED,
    EVIDENCE_PHYSICAL_CAMPAIGN,
    EVIDENCE_SYNTHETIC_FIXTURE,
    PAIR_AWAITING_SECOND_ARM,
    PAIR_AWAITING_VALIDITY,
    PAIR_BLOCKED_MISSING_FREEZE,
    PAIR_INVALID,
    PAIR_PLANNED,
    PAIR_UNRESOLVED,
    PAIR_VALID,
    PairLedgerValidation,
)

TARGET_FROZEN = "FROZEN"
TARGET_UNKNOWN_UNFROZEN = "UNKNOWN_UNFROZEN"
TARGET_NOT_APPROVED = "NOT_APPROVED"
TARGET_INVALID = "INVALID_TARGET"

REMAINING_NOT_COMPUTABLE = "NOT_COMPUTABLE"

PROGRESS_NOT_ESTABLISHED = "NOT_ESTABLISHED"
PROGRESS_ESTABLISHED = "ESTABLISHED"

TARGET_PROGRESS_COMPLETE = "COMPLETE"
TARGET_PROGRESS_IN_PROGRESS = "IN_PROGRESS"
TARGET_PROGRESS_NOT_COMPUTABLE = "NOT_COMPUTABLE"

CAMPAIGN_NOT_STARTED_BLOCKED = "NOT_STARTED_BLOCKED"
CAMPAIGN_AUTHORIZED_NOT_STARTED = "AUTHORIZED_NOT_STARTED"
CAMPAIGN_IN_PROGRESS = "IN_PROGRESS"
CAMPAIGN_TARGET_REACHED_PENDING_LOCK = "TARGET_REACHED_PENDING_LOCK"

PHYSICAL_EVIDENCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
PHYSICAL_EVIDENCE_ACCEPTED = "PHYSICAL_PAIR_LEDGER_EVIDENCE_ACCEPTED"
PHYSICAL_EVIDENCE_SYNTHETIC = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"

INVALID_ATTEMPTS_RECORDED = "RECORDED"
INVALID_ATTEMPTS_UNKNOWN = "UNKNOWN_ATTEMPT_LEDGER_UNAVAILABLE"

FIRST_WAVE_REACHED = "FIRST_WAVE_50_PERCENT_REACHED"
FIRST_WAVE_NOT_REACHED = "FIRST_WAVE_50_PERCENT_NOT_REACHED"
FIRST_WAVE_NOT_COMPUTABLE = "NOT_COMPUTABLE"

TARGET_CHANGE_ACCEPTED_REQUIRES_NEW_FREEZE = "ACCEPTED_REQUIRES_NEW_FREEZE"
TARGET_CHANGE_REFUSED_POST_CAMPAIGN_START = "REFUSED_AFTER_CAMPAIGN_START"
TARGET_CHANGE_REFUSED_MISSING_APPROVAL = "REFUSED_MISSING_APPROVAL"
TARGET_CHANGE_NONE = "NO_CHANGE"

TARGET_RECORD_KEYS = frozenset(
    {
        "status",
        "planned_pair_target",
        "approval",
        "variance_justification_ref",
    }
)


class W19ProgressError(ValueError):
    """Raised for malformed target records, never for a policy verdict."""


@dataclass(frozen=True)
class TargetAssessment:
    status: str
    planned_pair_target: int | None
    refusal_reasons: tuple[str, ...]
    approval_effect: str = "NONE_SOFTWARE_ASSESSMENT_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "planned_pair_target": self.planned_pair_target,
            "refusal_reasons": list(self.refusal_reasons),
            "approval_effect": self.approval_effect,
        }


@dataclass(frozen=True)
class TargetChangeDecision:
    decision: str
    refusal_reasons: tuple[str, ...]
    approval_effect: str = "NONE_SOFTWARE_ASSESSMENT_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "refusal_reasons": list(self.refusal_reasons),
            "approval_effect": self.approval_effect,
        }


@dataclass(frozen=True)
class CampaignProgress:
    campaign_id: str | None
    planned_pair_target: int | None
    pair_target_freeze_status: str
    valid_pairs_completed: int
    software_validated_pairs: int
    pairs_started: int
    pairs_planned: int
    pairs_awaiting_second_arm: int
    pairs_awaiting_validity: int
    invalid_pairs: int
    unresolved_pairs: int
    blocked_pairs: int
    remaining_target: int | str
    target_overshoot_pairs: int | None
    invalid_attempts: int | None
    invalid_attempts_status: str
    aborted_attempts: int | None
    superseded_attempts: int | None
    pair_status_counts: Mapping[str, int]
    campaign_authorization_status: str
    physical_evidence_class: str
    physical_campaign_status: str
    valid_pair_progress_status: str
    target_progress_status: str
    first_wave_status: str
    first_wave_fraction: float | None
    pair_target_source_conflict: bool
    refusal_reasons: tuple[str, ...]
    approval_effect: str = "NONE_SOFTWARE_ASSESSMENT_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "planned_pair_target": self.planned_pair_target,
            "pair_target_freeze_status": self.pair_target_freeze_status,
            "valid_pairs_completed": self.valid_pairs_completed,
            "software_validated_pairs": self.software_validated_pairs,
            "pairs_started": self.pairs_started,
            "pairs_planned": self.pairs_planned,
            "pairs_awaiting_second_arm": self.pairs_awaiting_second_arm,
            "pairs_awaiting_validity": self.pairs_awaiting_validity,
            "invalid_pairs": self.invalid_pairs,
            "unresolved_pairs": self.unresolved_pairs,
            "blocked_pairs": self.blocked_pairs,
            "remaining_target": self.remaining_target,
            "target_overshoot_pairs": self.target_overshoot_pairs,
            "invalid_attempts": self.invalid_attempts,
            "invalid_attempts_status": self.invalid_attempts_status,
            "aborted_attempts": self.aborted_attempts,
            "superseded_attempts": self.superseded_attempts,
            "pair_status_counts": dict(self.pair_status_counts),
            "campaign_authorization_status": self.campaign_authorization_status,
            "physical_evidence_class": self.physical_evidence_class,
            "physical_campaign_status": self.physical_campaign_status,
            "valid_pair_progress_status": self.valid_pair_progress_status,
            "target_progress_status": self.target_progress_status,
            "first_wave_status": self.first_wave_status,
            "first_wave_fraction": self.first_wave_fraction,
            "pair_target_source_conflict": self.pair_target_source_conflict,
            "refusal_reasons": list(self.refusal_reasons),
            "approval_effect": self.approval_effect,
        }


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


def assess_pair_target(record: Mapping[str, Any] | None) -> TargetAssessment:
    """A target requires an approved, justified frozen record with a positive count."""
    if record is None:
        return TargetAssessment(
            status=TARGET_UNKNOWN_UNFROZEN,
            planned_pair_target=None,
            refusal_reasons=("PAIR_TARGET_RECORD_MISSING",),
        )
    if not isinstance(record, Mapping):
        raise W19ProgressError("frozen_target must be an object")
    unknown = sorted(set(record) - TARGET_RECORD_KEYS)
    if unknown:
        raise W19ProgressError(
            f"frozen_target contains unknown field(s): {', '.join(unknown)}"
        )
    if record.get("status") != FREEZE_FROZEN_APPROVED:
        return TargetAssessment(
            status=TARGET_UNKNOWN_UNFROZEN,
            planned_pair_target=None,
            refusal_reasons=("PAIR_TARGET_NOT_FROZEN",),
        )
    problems: list[str] = []
    if not _approval_shape_ok(record.get("approval")):
        problems.append("PAIR_TARGET_APPROVAL_INVALID")
    justification = record.get("variance_justification_ref")
    if not isinstance(justification, str) or not justification.strip():
        problems.append("PAIR_TARGET_VARIANCE_JUSTIFICATION_MISSING")
    if problems:
        return TargetAssessment(
            status=TARGET_NOT_APPROVED,
            planned_pair_target=None,
            refusal_reasons=tuple(problems),
        )
    target = record.get("planned_pair_target")
    if not isinstance(target, int) or isinstance(target, bool) or target <= 0:
        return TargetAssessment(
            status=TARGET_INVALID,
            planned_pair_target=None,
            refusal_reasons=("PAIR_TARGET_NOT_A_POSITIVE_INTEGER",),
        )
    return TargetAssessment(
        status=TARGET_FROZEN,
        planned_pair_target=target,
        refusal_reasons=(),
    )


def assess_target_change(
    current_record: Mapping[str, Any] | None,
    proposed_record: Mapping[str, Any],
    *,
    valid_pairs_completed: int,
    pairs_recorded: int = 0,
) -> TargetChangeDecision:
    """Refuse target changes once any pair is recorded; never rewrite a denominator."""
    for name, value in (
        ("valid_pairs_completed", valid_pairs_completed),
        ("pairs_recorded", pairs_recorded),
    ):
        if not isinstance(value, int) or isinstance(value, bool):
            raise W19ProgressError(f"{name} must be an integer")
        if value < 0:
            raise W19ProgressError(f"{name} must not be negative")
    current = assess_pair_target(current_record)
    proposed = assess_pair_target(proposed_record)
    if current.status == proposed.status and current.planned_pair_target == (
        proposed.planned_pair_target
    ):
        return TargetChangeDecision(decision=TARGET_CHANGE_NONE, refusal_reasons=())
    if max(valid_pairs_completed, pairs_recorded) > 0:
        return TargetChangeDecision(
            decision=TARGET_CHANGE_REFUSED_POST_CAMPAIGN_START,
            refusal_reasons=("TARGET_CHANGE_AFTER_PAIRS_RECORDED",),
        )
    if proposed.status != TARGET_FROZEN:
        return TargetChangeDecision(
            decision=TARGET_CHANGE_REFUSED_MISSING_APPROVAL,
            refusal_reasons=proposed.refusal_reasons,
        )
    return TargetChangeDecision(
        decision=TARGET_CHANGE_ACCEPTED_REQUIRES_NEW_FREEZE,
        refusal_reasons=(),
    )


def compute_campaign_progress(
    ledger: PairLedgerValidation | None,
    *,
    target_record: Mapping[str, Any] | None = None,
) -> CampaignProgress:
    """Compute deterministic progress from verified records only."""
    target = assess_pair_target(target_record)
    counts: Mapping[str, int]
    if ledger is None:
        counts = {}
        invalid_attempts: int | None = None
        invalid_attempts_status = INVALID_ATTEMPTS_UNKNOWN
        aborted_attempts: int | None = None
        superseded_attempts: int | None = None
        campaign_authorization_status = "NOT_AUTHORIZED"
        evidence_class = PHYSICAL_EVIDENCE_NOT_ESTABLISHED
        software_validated = 0
        physical_valid = 0
        refusal_reasons: list[str] = ["ATTEMPT_LEDGER_UNAVAILABLE"]
    else:
        counts = dict(ledger.pair_status_counts)
        accounting = ledger.attempt_accounting
        invalid_attempts = accounting.invalid_attempts + accounting.aborted_attempts
        invalid_attempts_status = INVALID_ATTEMPTS_RECORDED
        aborted_attempts = accounting.aborted_attempts
        superseded_attempts = accounting.superseded_attempts
        campaign_authorization_status = str(ledger.authorization.get("status"))
        software_validated = ledger.software_valid_pairs
        physical_valid = ledger.physical_valid_pairs
        if ledger.evidence_class == EVIDENCE_SYNTHETIC_FIXTURE:
            evidence_class = PHYSICAL_EVIDENCE_SYNTHETIC
        elif ledger.physical_pair_evidence_accepted:
            evidence_class = PHYSICAL_EVIDENCE_ACCEPTED
        else:
            evidence_class = PHYSICAL_EVIDENCE_NOT_ESTABLISHED
        refusal_reasons = list(ledger.refusal_reasons)
    refusal_reasons.extend(target.refusal_reasons)

    authorized = campaign_authorization_status == AUTHORIZATION_AUTHORIZED
    planner_available = ledger is not None
    physical_ledger = (
        planner_available and ledger.evidence_class == EVIDENCE_PHYSICAL_CAMPAIGN
    )
    target_count_conflict = (
        bool(ledger.target_count_conflict) if planner_available else False
    )
    if target_count_conflict:
        refusal_reasons.append("PAIR_TARGET_COUNT_SOURCE_CONFLICT")
    authorized = authorized and physical_ledger
    pairs_started = sum(
        count
        for status, count in counts.items()
        if status != PAIR_PLANNED
    )
    if not authorized or not planner_available:
        physical_campaign_status = CAMPAIGN_NOT_STARTED_BLOCKED
        valid_pair_progress_status = PROGRESS_NOT_ESTABLISHED
    elif pairs_started == 0:
        physical_campaign_status = CAMPAIGN_AUTHORIZED_NOT_STARTED
        valid_pair_progress_status = PROGRESS_ESTABLISHED
    else:
        valid_pair_progress_status = PROGRESS_ESTABLISHED
        if (
            target.status == TARGET_FROZEN
            and target.planned_pair_target is not None
            and physical_valid >= target.planned_pair_target
        ):
            physical_campaign_status = CAMPAIGN_TARGET_REACHED_PENDING_LOCK
        else:
            physical_campaign_status = CAMPAIGN_IN_PROGRESS

    if (
        target.status != TARGET_FROZEN
        or valid_pair_progress_status != PROGRESS_ESTABLISHED
        or target_count_conflict
    ):
        target_progress_status = TARGET_PROGRESS_NOT_COMPUTABLE
        remaining_target: int | str = REMAINING_NOT_COMPUTABLE
        overshoot: int | None = None
        first_wave_status = FIRST_WAVE_NOT_COMPUTABLE
        first_wave_fraction: float | None = None
    else:
        planned = target.planned_pair_target
        assert planned is not None
        if physical_valid >= planned:
            target_progress_status = TARGET_PROGRESS_COMPLETE
        else:
            target_progress_status = TARGET_PROGRESS_IN_PROGRESS
        remaining_target = max(0, planned - physical_valid)
        overshoot = max(0, physical_valid - planned)
        first_wave_fraction = round(min(1.0, physical_valid / planned), 6)
        first_wave_status = (
            FIRST_WAVE_REACHED
            if physical_valid >= math.ceil(planned / 2)
            else FIRST_WAVE_NOT_REACHED
        )

    return CampaignProgress(
        campaign_id=ledger.campaign_id if ledger is not None else None,
        planned_pair_target=target.planned_pair_target,
        pair_target_freeze_status=target.status,
        valid_pairs_completed=physical_valid,
        software_validated_pairs=software_validated,
        pairs_started=pairs_started,
        pairs_planned=counts.get(PAIR_PLANNED, 0),
        pairs_awaiting_second_arm=counts.get(PAIR_AWAITING_SECOND_ARM, 0),
        pairs_awaiting_validity=counts.get(PAIR_AWAITING_VALIDITY, 0),
        invalid_pairs=counts.get(PAIR_INVALID, 0),
        unresolved_pairs=counts.get(PAIR_UNRESOLVED, 0),
        blocked_pairs=counts.get(PAIR_BLOCKED_MISSING_FREEZE, 0),
        remaining_target=remaining_target,
        target_overshoot_pairs=overshoot,
        invalid_attempts=invalid_attempts,
        invalid_attempts_status=invalid_attempts_status,
        aborted_attempts=aborted_attempts,
        superseded_attempts=superseded_attempts,
        pair_status_counts=counts,
        campaign_authorization_status=campaign_authorization_status,
        physical_evidence_class=evidence_class,
        physical_campaign_status=physical_campaign_status,
        valid_pair_progress_status=valid_pair_progress_status,
        target_progress_status=target_progress_status,
        first_wave_status=first_wave_status,
        first_wave_fraction=first_wave_fraction,
        pair_target_source_conflict=target_count_conflict,
        refusal_reasons=tuple(refusal_reasons),
        approval_effect="NONE_SOFTWARE_ASSESSMENT_ONLY",
    )
