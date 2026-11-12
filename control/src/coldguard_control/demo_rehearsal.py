"""Week 23 demo hardening and security/resilience rehearsal.

Pure assessment module for Doc 05D section 55 (D-W23-01..D-W23-05).
Models four required demo scenes and three full rehearsal records.

Scenes:
- VERIFIED_ACTUATION: prediction/threshold → policy → command → ACK → current → thermal
- SAFE_LOCAL: disconnect, mode transition, local protection, reconnect, no stale command
- STALE_COMMAND: controlled replay with rejection
- SECURITY_EXPLANATION: TLS, ACL, authorization, TTL, idempotency (distinct purposes)

Each rehearsal record measures:
- failure_recovery: ability to recover from injected faults
- operator_clarity: clear state transitions and reason codes
- timing: end-to-end latency within bounds

Readiness requires all four scenes complete and three passing LIVE_REHEARSAL records.
Host simulation may validate the contract but must not claim rehearsal completion.
Pure assessment only, no transport/physical execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Sequence


class RehearsalScene(str, Enum):
    """The four required Week 23 demo scenes."""

    VERIFIED_ACTUATION = "VERIFIED_ACTUATION"
    SAFE_LOCAL = "SAFE_LOCAL"
    STALE_COMMAND = "STALE_COMMAND"
    SECURITY_EXPLANATION = "SECURITY_EXPLANATION"


class RehearsalAuthority(str, Enum):
    """Authority of a rehearsal record."""

    HOST_SIMULATED = "HOST_SIMULATED"
    LIVE_REHEARSAL = "LIVE_REHEARSAL"


class SceneOutcome(str, Enum):
    """Observable outcomes for each scene."""

    # VERIFIED_ACTUATION outcomes
    PREDICTION_VALID = "PREDICTION_VALID"
    THRESHOLD_CROSSED = "THRESHOLD_CROSSED"
    POLICY_DECISION_MADE = "POLICY_DECISION_MADE"
    COMMAND_ISSUED = "COMMAND_ISSUED"
    ACK_RECEIVED = "ACK_RECEIVED"
    ELECTRICAL_VERIFIED = "ELECTRICAL_VERIFIED"
    THERMAL_VERIFIED = "THERMAL_VERIFIED"

    # SAFE_LOCAL outcomes
    DISCONNECT_DETECTED = "DISCONNECT_DETECTED"
    MODE_TRANSITION_TO_SAFE_LOCAL = "MODE_TRANSITION_TO_SAFE_LOCAL"
    LOCAL_PROTECTION_ACTIVE = "LOCAL_PROTECTION_ACTIVE"
    RECONNECT_SUCCESSFUL = "RECONNECT_SUCCESSFUL"
    NO_STALE_COMMAND_REPLAY = "NO_STALE_COMMAND_REPLAY"

    # STALE_COMMAND outcomes
    STALE_COMMAND_REJECTED = "STALE_COMMAND_REJECTED"
    NO_ACTUATION_ON_STALE = "NO_ACTUATION_ON_STALE"
    AUDIT_EVENT_RECORDED = "AUDIT_EVENT_RECORDED"

    # SECURITY_EXPLANATION outcomes
    TLS_PURPOSE_EXPLAINED = "TLS_PURPOSE_EXPLAINED"
    ACL_PURPOSE_EXPLAINED = "ACL_PURPOSE_EXPLAINED"
    AUTHORIZATION_PURPOSE_EXPLAINED = "AUTHORIZATION_PURPOSE_EXPLAINED"
    TTL_PURPOSE_EXPLAINED = "TTL_PURPOSE_EXPLAINED"
    IDEMPOTENCY_PURPOSE_EXPLAINED = "IDEMPOTENCY_PURPOSE_EXPLAINED"


REQUIRED_SCENE_OUTCOMES: Mapping[
    RehearsalScene, frozenset[SceneOutcome]
] = MappingProxyType({
    RehearsalScene.VERIFIED_ACTUATION: frozenset({
        SceneOutcome.PREDICTION_VALID,
        SceneOutcome.THRESHOLD_CROSSED,
        SceneOutcome.POLICY_DECISION_MADE,
        SceneOutcome.COMMAND_ISSUED,
        SceneOutcome.ACK_RECEIVED,
        SceneOutcome.ELECTRICAL_VERIFIED,
        SceneOutcome.THERMAL_VERIFIED,
    }),
    RehearsalScene.SAFE_LOCAL: frozenset({
        SceneOutcome.DISCONNECT_DETECTED,
        SceneOutcome.MODE_TRANSITION_TO_SAFE_LOCAL,
        SceneOutcome.LOCAL_PROTECTION_ACTIVE,
        SceneOutcome.RECONNECT_SUCCESSFUL,
        SceneOutcome.NO_STALE_COMMAND_REPLAY,
    }),
    RehearsalScene.STALE_COMMAND: frozenset({
        SceneOutcome.STALE_COMMAND_REJECTED,
        SceneOutcome.NO_ACTUATION_ON_STALE,
        SceneOutcome.AUDIT_EVENT_RECORDED,
    }),
    RehearsalScene.SECURITY_EXPLANATION: frozenset({
        SceneOutcome.TLS_PURPOSE_EXPLAINED,
        SceneOutcome.ACL_PURPOSE_EXPLAINED,
        SceneOutcome.AUTHORIZATION_PURPOSE_EXPLAINED,
        SceneOutcome.TTL_PURPOSE_EXPLAINED,
        SceneOutcome.IDEMPOTENCY_PURPOSE_EXPLAINED,
    }),
})

REQUIRED_SCENE_SEQUENCE: Mapping[
    RehearsalScene, tuple[SceneOutcome, ...]
] = MappingProxyType({
    RehearsalScene.VERIFIED_ACTUATION: (
        SceneOutcome.PREDICTION_VALID,
        SceneOutcome.THRESHOLD_CROSSED,
        SceneOutcome.POLICY_DECISION_MADE,
        SceneOutcome.COMMAND_ISSUED,
        SceneOutcome.ACK_RECEIVED,
        SceneOutcome.ELECTRICAL_VERIFIED,
        SceneOutcome.THERMAL_VERIFIED,
    ),
    RehearsalScene.SAFE_LOCAL: (
        SceneOutcome.DISCONNECT_DETECTED,
        SceneOutcome.MODE_TRANSITION_TO_SAFE_LOCAL,
        SceneOutcome.LOCAL_PROTECTION_ACTIVE,
        SceneOutcome.RECONNECT_SUCCESSFUL,
        SceneOutcome.NO_STALE_COMMAND_REPLAY,
    ),
    RehearsalScene.STALE_COMMAND: (
        SceneOutcome.STALE_COMMAND_REJECTED,
        SceneOutcome.NO_ACTUATION_ON_STALE,
        SceneOutcome.AUDIT_EVENT_RECORDED,
    ),
    RehearsalScene.SECURITY_EXPLANATION: (
        SceneOutcome.TLS_PURPOSE_EXPLAINED,
        SceneOutcome.ACL_PURPOSE_EXPLAINED,
        SceneOutcome.AUTHORIZATION_PURPOSE_EXPLAINED,
        SceneOutcome.TTL_PURPOSE_EXPLAINED,
        SceneOutcome.IDEMPOTENCY_PURPOSE_EXPLAINED,
    ),
})

REQUIRED_REHEARSAL_COUNT = 3


@dataclass(frozen=True, slots=True)
class RehearsalMetrics:
    """Metrics recorded for each rehearsal."""

    failure_recovery: bool
    operator_clarity: bool
    timing_within_bounds: bool
    end_to_end_latency_ms: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.failure_recovery, bool):
            raise TypeError("failure_recovery must be a strict boolean")
        if not isinstance(self.operator_clarity, bool):
            raise TypeError("operator_clarity must be a strict boolean")
        if not isinstance(self.timing_within_bounds, bool):
            raise TypeError("timing_within_bounds must be a strict boolean")
        if isinstance(self.end_to_end_latency_ms, bool) or not isinstance(
            self.end_to_end_latency_ms, int
        ):
            raise TypeError("end_to_end_latency_ms must be an int")
        if self.end_to_end_latency_ms < 0:
            raise ValueError("end_to_end_latency_ms must be non-negative")


@dataclass(frozen=True, slots=True)
class SceneEvidence:
    """Immutable evidence for one scene in a rehearsal."""

    scene: RehearsalScene
    observed_outcomes: frozenset[SceneOutcome]
    observed_sequence: tuple[SceneOutcome, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scene, RehearsalScene):
            raise TypeError("scene must be a RehearsalScene")
        if not isinstance(self.observed_outcomes, frozenset):
            raise TypeError("observed_outcomes must be a frozenset")
        if not all(
            isinstance(outcome, SceneOutcome)
            for outcome in self.observed_outcomes
        ):
            raise TypeError("observed_outcomes must contain SceneOutcome values")
        if not isinstance(self.observed_sequence, tuple):
            raise TypeError("observed_sequence must be a tuple")
        if not all(
            isinstance(outcome, SceneOutcome)
            for outcome in self.observed_sequence
        ):
            raise TypeError("observed_sequence must contain SceneOutcome values")


@dataclass(frozen=True, slots=True)
class SceneAssessment:
    """Assessment for one scene."""

    scene: RehearsalScene
    passed: bool
    missing_outcomes: tuple[SceneOutcome, ...]
    sequence_correct: bool


@dataclass(frozen=True, slots=True)
class RehearsalRecord:
    """One complete rehearsal record with all four scenes."""

    record_id: str
    authority: RehearsalAuthority
    scene_evidence: tuple[SceneEvidence, ...]
    metrics: RehearsalMetrics
    scene_assessments: tuple[SceneAssessment, ...] = field(default_factory=tuple)
    all_scenes_pass: bool = False
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.record_id or not self.record_id.strip():
            raise ValueError("record_id must be nonempty")
        if not isinstance(self.authority, RehearsalAuthority):
            raise TypeError("authority must be a RehearsalAuthority")
        if not isinstance(self.scene_evidence, tuple):
            raise TypeError("scene_evidence must be a tuple")
        if not isinstance(self.metrics, RehearsalMetrics):
            raise TypeError("metrics must be a RehearsalMetrics")
        if not isinstance(self.scene_assessments, tuple):
            raise TypeError("scene_assessments must be a tuple")
        if not isinstance(self.all_scenes_pass, bool):
            raise TypeError("all_scenes_pass must be a strict boolean")
        if not isinstance(self.blockers, tuple):
            raise TypeError("blockers must be a tuple")


@dataclass(frozen=True, slots=True)
class RehearsalDecision:
    """Aggregate Week 23 rehearsal decision."""

    records: tuple[RehearsalRecord, ...]
    missing_records: int
    passing_records: int
    live_rehearsal_complete: bool
    readiness_achieved: bool
    blockers: tuple[str, ...]


def _assess_scene(evidence: SceneEvidence) -> SceneAssessment:
    """Assess one scene against required outcomes."""
    required = REQUIRED_SCENE_OUTCOMES[evidence.scene]
    missing = tuple(
        sorted(
            required - evidence.observed_outcomes,
            key=lambda o: o.value,
        )
    )
    sequence_correct = evidence.observed_sequence == REQUIRED_SCENE_SEQUENCE[evidence.scene]
    return SceneAssessment(
        scene=evidence.scene,
        passed=not missing and sequence_correct,
        missing_outcomes=missing,
        sequence_correct=sequence_correct,
    )


def _build_rehearsal_record(
    record_id: str,
    authority: RehearsalAuthority,
    scene_evidence: Sequence[SceneEvidence],
    metrics: RehearsalMetrics,
) -> RehearsalRecord:
    """Build and assess one rehearsal record."""
    if isinstance(scene_evidence, (str, bytes)) or not isinstance(
        scene_evidence, Sequence
    ):
        raise TypeError("scene_evidence must be a Sequence of SceneEvidence")

    by_scene: dict[RehearsalScene, SceneEvidence] = {}
    for item in scene_evidence:
        if not isinstance(item, SceneEvidence):
            raise TypeError("each item must be SceneEvidence")
        if item.scene in by_scene:
            raise ValueError(f"duplicate scene in record: {item.scene.value}")
        by_scene[item.scene] = item

    assessments: list[SceneAssessment] = []
    blockers: list[str] = []

    for scene in RehearsalScene:
        item = by_scene.get(scene)
        if item is None:
            blockers.append(f"MISSING_SCENE:{scene.value}")
            continue
        assessment = _assess_scene(item)
        assessments.append(assessment)
        if not assessment.passed:
            for outcome in assessment.missing_outcomes:
                blockers.append(f"MISSING_OUTCOME:{scene.value}:{outcome.value}")
            if not assessment.sequence_correct:
                blockers.append(f"INVALID_SCENE_SEQUENCE:{scene.value}")

    # Check metrics
    if not metrics.failure_recovery:
        blockers.append("FAILURE_RECOVERY_NOT_DEMONSTRATED")
    if not metrics.operator_clarity:
        blockers.append("OPERATOR_CLARITY_NOT_DEMONSTRATED")
    if not metrics.timing_within_bounds:
        blockers.append("TIMING_NOT_WITHIN_BOUNDS")

    all_scenes_pass = (
        len(by_scene) == len(RehearsalScene)
        and all(a.passed for a in assessments)
        and metrics.failure_recovery
        and metrics.operator_clarity
        and metrics.timing_within_bounds
    )

    return RehearsalRecord(
        record_id=record_id,
        authority=authority,
        scene_evidence=tuple(scene_evidence),
        metrics=metrics,
        scene_assessments=tuple(assessments),
        all_scenes_pass=all_scenes_pass,
        blockers=tuple(blockers),
    )


def assess_rehearsal(
    records: Sequence[RehearsalRecord],
) -> RehearsalDecision:
    """Assess the complete W23 rehearsal campaign.

    Args:
        records: Rehearsal records to assess.
    Returns:
        RehearsalDecision with readiness assessment.

    Raises:
        TypeError: If inputs have wrong types.
        ValueError: If duplicate record IDs exist.
    """
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise TypeError("records must be a Sequence of RehearsalRecord")

    by_id: dict[str, RehearsalRecord] = {}
    for rec in records:
        if not isinstance(rec, RehearsalRecord):
            raise TypeError("each record must be a RehearsalRecord")
        if rec.record_id in by_id:
            raise ValueError(f"duplicate record_id: {rec.record_id}")
        by_id[rec.record_id] = rec

    passing_records = sum(1 for rec in records if rec.all_scenes_pass)
    live_passing = sum(
        1 for rec in records
        if rec.all_scenes_pass and rec.authority is RehearsalAuthority.LIVE_REHEARSAL
    )

    live_rehearsal_complete = live_passing >= REQUIRED_REHEARSAL_COUNT
    readiness_achieved = live_rehearsal_complete

    blockers: list[str] = []
    if passing_records < REQUIRED_REHEARSAL_COUNT:
        blockers.append(
            f"INSUFFICIENT_PASSING_RECORDS:{passing_records}/{REQUIRED_REHEARSAL_COUNT}"
        )
    if live_passing < REQUIRED_REHEARSAL_COUNT:
        blockers.append(
            f"INSUFFICIENT_LIVE_REHEARSAL:{live_passing}/{REQUIRED_REHEARSAL_COUNT}"
        )

    for rec in records:
        if not rec.all_scenes_pass:
            blockers.extend(rec.blockers)

    return RehearsalDecision(
        records=tuple(records),
        missing_records=max(0, REQUIRED_REHEARSAL_COUNT - len(records)),
        passing_records=passing_records,
        live_rehearsal_complete=live_rehearsal_complete,
        readiness_achieved=readiness_achieved,
        blockers=tuple(blockers),
    )


def build_demo_rehearsal_record(
    record_id: str,
    authority: RehearsalAuthority = RehearsalAuthority.HOST_SIMULATED,
    override_outcomes: Mapping[RehearsalScene, frozenset[SceneOutcome]] | None = None,
    latency_ms: int = 150,
) -> RehearsalRecord:
    """Build a demo rehearsal record with canonical scenes.

    Args:
        record_id: Unique identifier for the record.
        authority: Authority level (HOST_SIMULATED or LIVE_REHEARSAL).
        override_outcomes: Optional overrides for specific scenes.
        latency_ms: End-to-end latency in milliseconds.

    Returns:
        RehearsalRecord with all four scenes.
    """
    if override_outcomes is None:
        override_outcomes = {}

    scene_evidence: list[SceneEvidence] = []
    for scene in RehearsalScene:
        outcomes = override_outcomes.get(scene, REQUIRED_SCENE_OUTCOMES[scene])
        scene_evidence.append(
            SceneEvidence(
                scene=scene,
                observed_outcomes=outcomes,
                observed_sequence=REQUIRED_SCENE_SEQUENCE[scene],
            )
        )

    metrics = RehearsalMetrics(
        failure_recovery=True,
        operator_clarity=True,
        timing_within_bounds=latency_ms <= 500,
        end_to_end_latency_ms=latency_ms,
    )

    return _build_rehearsal_record(
        record_id=record_id,
        authority=authority,
        scene_evidence=scene_evidence,
        metrics=metrics,
    )
