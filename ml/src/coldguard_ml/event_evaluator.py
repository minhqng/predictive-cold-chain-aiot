"""W09 reusable event-level evaluator (B-W09-04).

The evaluator turns a baseline replay into typed events, warning episodes and
event-level metrics. It is deliberately independent of the model layer: W11
can feed a predictive warning stream into the same policy without reusing this
module's threshold baseline.

Scientific rules enforced here:

* warning episodes, not positive samples, are the event unit;
* a no-event run contributes false-warning burden only when its coverage is
  trustworthy and no critical event is observed;
* censored or untrusted observations never become negative controls;
* one critical event is matched at most once, and one episode is matched at
  most once; alternatives are recorded;
* zero denominators stay undefined;
* an ON transition is never silently treated as a thermal critical crossing;
* EWT compatibility is delegated to W04 ``compute_ewt``; W09 never invents a
  predictive warning stream or a measured AIW.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .baselines import (
    B0_THRESHOLD,
    B1_HYSTERESIS,
    B1_PERSISTENCE_CANDIDATE,
    CERTAINTY_INTERVAL,
    ReplayResult,
    TRANSITION_CRITERION,
    TRANSITION_OFF,
    TRANSITION_ON,
)
from .evaluation_contract import (
    EWTProvenance,
    EWTResult,
    EWTStatus,
    compute_ewt,
)

EVENT_DEFINITION_VERSION = "coldguard-w09-event-definitions-v1"
EPISODE_POLICY_VERSION = "coldguard-w09-warning-episode-policy-v1"
ASSOCIATION_POLICY_VERSION = "coldguard-w09-event-association-policy-v1"

EVENT_REACTIVE_CRITERION_CROSSING = "REACTIVE_CRITERION_CROSSING"
EVENT_REACTIVE_ON_TRANSITION = "REACTIVE_ON_TRANSITION"
EVENT_REACTIVE_OFF_TRANSITION = "REACTIVE_OFF_TRANSITION"
EVENT_WARNING_EPISODE = "WARNING_EPISODE"
EVENT_CRITICAL_EVENT = "CRITICAL_EVENT"
EVENT_NO_EVENT_OBSERVATION = "NO_EVENT_OBSERVATION"
EVENT_CENSORED_OBSERVATION = "CENSORED_OBSERVATION"
EVENT_UNTRUSTED_INTERVAL = "UNTRUSTED_INTERVAL"

EVENT_TYPES = (
    EVENT_REACTIVE_CRITERION_CROSSING,
    EVENT_REACTIVE_ON_TRANSITION,
    EVENT_REACTIVE_OFF_TRANSITION,
    EVENT_WARNING_EPISODE,
    EVENT_CRITICAL_EVENT,
    EVENT_NO_EVENT_OBSERVATION,
    EVENT_CENSORED_OBSERVATION,
    EVENT_UNTRUSTED_INTERVAL,
)

EVENT_DEFINITIONS: dict[str, dict[str, str]] = {
    EVENT_REACTIVE_CRITERION_CROSSING: {
        "version": EVENT_DEFINITION_VERSION,
        "definition": (
            "first observed transition of the configured representative "
            "temperature criterion from not-satisfied to satisfied"
        ),
        "source": "W09 B0 deterministic threshold replay",
        "evidence": "source sample identity and event-time interval",
    },
    EVENT_REACTIVE_ON_TRANSITION: {
        "version": EVENT_DEFINITION_VERSION,
        "definition": (
            "offline hysteresis replay transition to ON at the configured "
            "upper boundary; a policy intent, not an actuator command"
        ),
        "source": "W09 B1 deterministic hysteresis replay",
        "evidence": "source sample identity, prior state and policy version",
    },
    EVENT_REACTIVE_OFF_TRANSITION: {
        "version": EVENT_DEFINITION_VERSION,
        "definition": (
            "offline hysteresis replay transition to OFF at the configured "
            "lower boundary while previously ON"
        ),
        "source": "W09 B1 deterministic hysteresis replay",
        "evidence": "source sample identity, prior state and policy version",
    },
    EVENT_WARNING_EPISODE: {
        "version": EVENT_DEFINITION_VERSION,
        "definition": (
            "one contiguous warning interval after the declared persistence "
            "and bridging policy; repeated warning samples do not create "
            "extra episodes"
        ),
        "source": "W09 warning-episode policy",
        "evidence": "episode start/end, sample support and policy version",
    },
    EVENT_CRITICAL_EVENT: {
        "version": EVENT_DEFINITION_VERSION,
        "definition": (
            "an observed thermal criterion crossing on one eligible, "
            "non-predictively-intervened trajectory"
        ),
        "source": "declared B0 critical criterion",
        "evidence": "event-time interval, source and criterion definition",
    },
    EVENT_NO_EVENT_OBSERVATION: {
        "version": EVENT_DEFINITION_VERSION,
        "definition": (
            "a fully observed eligible run with no qualifying critical event; "
            "a genuine negative-control observation"
        ),
        "source": "W08 eligibility plus W09 coverage",
        "evidence": "evaluable run duration and event denominator",
    },
    EVENT_CENSORED_OBSERVATION: {
        "version": EVENT_DEFINITION_VERSION,
        "definition": (
            "an observation whose critical-event status is unknown because the "
            "trajectory ended or was interrupted before the criterion could "
            "be observed"
        ),
        "source": "W09 coverage and refused intervals",
        "evidence": "censoring time and reason",
    },
    EVENT_UNTRUSTED_INTERVAL: {
        "version": EVENT_DEFINITION_VERSION,
        "definition": (
            "an interval whose time, quality or identity cannot support a "
            "precise event timestamp"
        ),
        "source": "W04/W05/W09 quality and time gates",
        "evidence": "interval bounds and refusal reason",
    },
}

WARNING = "WARNING"
NO_WARNING = "NO_WARNING"
UNKNOWN = "UNKNOWN"

TERMINATION_RECOVERED = "RECOVERED"
TERMINATION_RUN_END = "RUN_ENDED"
TERMINATION_CENSORED = "CENSORED"
TERMINATION_GAP = "GAP_TERMINATED"

ELIGIBLE_FOR_S1_DATASET = "ELIGIBLE_FOR_S1_DATASET"
DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
BLOCKED = "BLOCKED"
NOT_ESTIMABLE = "NOT_ESTIMABLE"

AIW_STATUS = "NOT_ESTIMABLE"
AIW_REASON = (
    "W09 produces no command/ACK/electrical/thermal latency chain; AIW "
    "requires measured W06/W04 components"
)

METRIC_DEFINED = "DEFINED"
METRIC_UNDEFINED = "UNDEFINED"


class EventEvaluationError(ValueError):
    """An event-evaluation input would fabricate or conflate evidence."""


@dataclass(frozen=True)
class WarningSample:
    time_s: float
    state: str
    sample_id: str
    source_index: int | None = None
    quality: str = "EVALUABLE"

    def __post_init__(self) -> None:
        if not math.isfinite(self.time_s):
            raise EventEvaluationError("warning-sample time must be finite")
        if self.state not in (WARNING, NO_WARNING, UNKNOWN):
            raise EventEvaluationError(
                f"warning state must be one of {(WARNING, NO_WARNING, UNKNOWN)}"
            )
        if not self.sample_id.strip():
            raise EventEvaluationError("warning sample identity is required")


@dataclass(frozen=True)
class EpisodePolicy:
    policy_version: str
    min_persistence_s: float
    bridge_gap_s: float
    bridge_unknown_gaps: bool
    status: str
    source: str

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise EventEvaluationError("episode policy version is required")
        if (
            isinstance(self.min_persistence_s, bool)
            or not isinstance(self.min_persistence_s, (int, float))
            or not math.isfinite(float(self.min_persistence_s))
            or self.min_persistence_s < 0
        ):
            raise EventEvaluationError(
                "min_persistence_s must be a non-negative finite number"
            )
        if (
            isinstance(self.bridge_gap_s, bool)
            or not isinstance(self.bridge_gap_s, (int, float))
            or not math.isfinite(float(self.bridge_gap_s))
            or self.bridge_gap_s < 0
        ):
            raise EventEvaluationError(
                "bridge_gap_s must be a non-negative finite number"
            )
        if not self.status.strip() or not self.source.strip():
            raise EventEvaluationError(
                "episode policy status and source are required"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "min_persistence_s": self.min_persistence_s,
            "bridge_gap_s": self.bridge_gap_s,
            "bridge_unknown_gaps": self.bridge_unknown_gaps,
            "status": self.status,
            "source": self.source,
        }


@dataclass(frozen=True)
class WarningEpisode:
    episode_id: str
    run_id: str | None
    source_sha256: str
    start_s: float
    end_s: float | None
    duration_s: float | None
    warning_span_s: float | None
    sample_count: int
    policy_version: str
    termination: str
    censored: bool
    synthetic_control: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": EVENT_WARNING_EPISODE,
            "event_id": self.episode_id,
            "episode_id": self.episode_id,
            "run_id": self.run_id,
            "source_sha256": self.source_sha256,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "duration_s": self.duration_s,
            "warning_span_s": self.warning_span_s,
            "sample_count": self.sample_count,
            "policy_version": self.policy_version,
            "termination": self.termination,
            "censored": self.censored,
            "synthetic_control": self.synthetic_control,
        }


@dataclass(frozen=True)
class EpisodeBuildResult:
    episodes: tuple[WarningEpisode, ...]
    discarded: tuple[dict[str, Any], ...]
    policy: EpisodePolicy

    def to_dict(self) -> dict[str, Any]:
        return {
            "episodes": [item.to_dict() for item in self.episodes],
            "discarded": [dict(item) for item in self.discarded],
            "policy": self.policy.to_dict(),
        }


@dataclass(frozen=True)
class CriticalEventInput:
    event_id: str
    time_s: float | None
    run_id: str | None
    source_sha256: str
    definition_version: str
    source: str
    observed: bool = True
    censored: bool = False
    trusted: bool = True
    intervention: bool = False
    time_certainty: str = CERTAINTY_INTERVAL
    interval_start_s: float | None = None
    interval_end_s: float | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise EventEvaluationError("critical-event identity is required")
        if not self.definition_version.strip() or not self.source.strip():
            raise EventEvaluationError(
                "critical-event definition version and source are required"
            )
        if self.time_s is not None and not math.isfinite(self.time_s):
            raise EventEvaluationError("critical-event time must be finite")
        if self.observed and self.time_s is None:
            raise EventEvaluationError(
                "an observed critical event requires a finite event time"
            )
        if self.censored and self.observed:
            raise EventEvaluationError(
                "an observed event cannot also be censored"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": EVENT_CRITICAL_EVENT,
            "event_id": self.event_id,
            "time_s": self.time_s,
            "run_id": self.run_id,
            "source_sha256": self.source_sha256,
            "definition_version": self.definition_version,
            "source": self.source,
            "observed": self.observed,
            "censored": self.censored,
            "trusted": self.trusted,
            "intervention": self.intervention,
            "time_certainty": self.time_certainty,
            "interval_start_s": self.interval_start_s,
            "interval_end_s": self.interval_end_s,
        }


@dataclass(frozen=True)
class AssociationPolicy:
    policy_version: str
    pre_window_s: float
    post_window_s: float
    require_trusted_events: bool
    allow_censored_events: bool
    status: str
    source: str

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise EventEvaluationError("association policy version is required")
        for name, value in (
            ("pre_window_s", self.pre_window_s),
            ("post_window_s", self.post_window_s),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise EventEvaluationError(
                    f"{name} must be a non-negative finite number"
                )
        if not self.status.strip() or not self.source.strip():
            raise EventEvaluationError(
                "association policy status and source are required"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "pre_window_s": self.pre_window_s,
            "post_window_s": self.post_window_s,
            "require_trusted_events": self.require_trusted_events,
            "allow_censored_events": self.allow_censored_events,
            "status": self.status,
            "source": self.source,
        }


@dataclass(frozen=True)
class EpisodeMatch:
    event_id: str
    episode_id: str
    event_time_s: float
    episode_start_s: float
    delta_s: float
    alternative_episode_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "episode_id": self.episode_id,
            "event_time_s": self.event_time_s,
            "episode_start_s": self.episode_start_s,
            "delta_s": self.delta_s,
            "alternative_episode_ids": list(self.alternative_episode_ids),
        }


@dataclass(frozen=True)
class EventMetrics:
    true_matched_warning_episodes: int
    unmatched_warning_episodes: int
    missed_critical_events: int
    eligible_critical_event_denominator: int
    false_warning_episodes: int | None
    false_warning_episodes_per_eligible_run: float | None
    false_warning_episodes_per_eligible_hour: float | None
    event_precision: float | None
    event_recall: float | None
    censored_event_count: int
    untrusted_event_count: int
    intervened_event_count: int
    run_support: int
    event_support: int
    episode_support: int
    undefined_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "true_matched_warning_episodes": self.true_matched_warning_episodes,
            "unmatched_warning_episodes": self.unmatched_warning_episodes,
            "missed_critical_events": self.missed_critical_events,
            "eligible_critical_event_denominator": self.eligible_critical_event_denominator,
            "false_warning_episodes": self.false_warning_episodes,
            "false_warning_episodes_per_eligible_run": (
                self.false_warning_episodes_per_eligible_run
            ),
            "false_warning_episodes_per_eligible_hour": (
                self.false_warning_episodes_per_eligible_hour
            ),
            "event_precision": self.event_precision,
            "event_recall": self.event_recall,
            "censored_event_count": self.censored_event_count,
            "untrusted_event_count": self.untrusted_event_count,
            "intervened_event_count": self.intervened_event_count,
            "run_support": self.run_support,
            "event_support": self.event_support,
            "episode_support": self.episode_support,
            "undefined_reasons": list(self.undefined_reasons),
        }


@dataclass(frozen=True)
class EventEvaluationResult:
    run_id: str | None
    source_sha256: str
    events: tuple[dict[str, Any], ...]
    episodes: tuple[WarningEpisode, ...]
    matches: tuple[EpisodeMatch, ...]
    unmatched_episode_ids: tuple[str, ...]
    missed_event_ids: tuple[str, ...]
    metrics: EventMetrics
    episode_policy: EpisodePolicy
    association_policy: AssociationPolicy
    warning_definition: str
    coverage_trustworthy: bool
    synthetic_control: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_sha256": self.source_sha256,
            "events": [dict(item) for item in self.events],
            "episodes": [item.to_dict() for item in self.episodes],
            "matches": [item.to_dict() for item in self.matches],
            "unmatched_episode_ids": list(self.unmatched_episode_ids),
            "missed_event_ids": list(self.missed_event_ids),
            "metrics": self.metrics.to_dict(),
            "episode_policy": self.episode_policy.to_dict(),
            "association_policy": self.association_policy.to_dict(),
            "warning_definition": self.warning_definition,
            "coverage_trustworthy": self.coverage_trustworthy,
            "synthetic_control": self.synthetic_control,
        }


def event_definitions() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "event_type": event_type,
            **EVENT_DEFINITIONS[event_type],
        }
        for event_type in EVENT_TYPES
    )


def warning_samples_from_replay(
    replay: ReplayResult,
    *,
    warning_definition: str,
) -> tuple[tuple[WarningSample, ...], int]:
    """Build a deduplicated warning stream from a replay result.

    ``warning_definition`` must name the semantic source (criterion crossing
    state or reactive ON state). The caller may not leave it implicit.
    """
    if not warning_definition.strip():
        raise EventEvaluationError("warning_definition must be explicit")
    if replay.baseline not in (
        B0_THRESHOLD,
        B1_HYSTERESIS,
        B1_PERSISTENCE_CANDIDATE,
    ):
        raise EventEvaluationError(f"unknown replay baseline {replay.baseline!r}")
    samples: list[WarningSample] = []
    seen: set[str] = set()
    duplicates = 0
    for sample in replay.samples:
        if sample.sample_id in seen:
            duplicates += 1
            continue
        seen.add(sample.sample_id)
        if sample.time_s is None:
            continue
        if sample.criterion_state is None:
            state = UNKNOWN
        elif sample.criterion_state:
            state = WARNING
        else:
            state = NO_WARNING
        samples.append(
            WarningSample(
                time_s=sample.time_s,
                state=state,
                sample_id=sample.sample_id,
                source_index=sample.index,
                quality=sample.sample_status,
            )
        )
    if any(
        right.time_s < left.time_s for left, right in zip(samples, samples[1:])
    ):
        raise EventEvaluationError(
            "warning samples are not non-decreasing in event time"
        )
    return tuple(samples), duplicates


def _episode_id(
    source_sha256: str,
    policy_version: str,
    start_s: float,
    first_sample_id: str,
    index: int,
) -> str:
    import hashlib

    payload = "\0".join(
        (
            source_sha256,
            policy_version,
            str(start_s),
            first_sample_id,
            str(index),
        )
    )
    return "EP:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def build_warning_episodes(
    samples: Sequence[WarningSample],
    policy: EpisodePolicy,
    *,
    run_id: str | None,
    source_sha256: str,
    synthetic_control: bool = False,
) -> EpisodeBuildResult:
    """Merge warning samples into policy-defined episodes."""
    if not samples:
        return EpisodeBuildResult((), (), policy)
    episodes: list[WarningEpisode] = []
    discarded: list[dict[str, Any]] = []
    active_start: float | None = None
    active_last_warning: float | None = None
    active_first_sample_id: str | None = None
    active_samples: list[WarningSample] = []
    active_censored = False
    last_state: str | None = None

    def close(termination: str, end_s: float | None) -> None:
        nonlocal active_start, active_last_warning, active_first_sample_id
        nonlocal active_samples, active_censored
        if active_start is None:
            return
        span = (
            None
            if active_last_warning is None
            else round(active_last_warning - active_start, 9)
        )
        if span is None or span < policy.min_persistence_s:
            discarded.append(
                {
                    "start_s": active_start,
                    "end_s": active_last_warning,
                    "duration_s": span,
                    "sample_count": len(active_samples),
                    "reason": "PERSISTENCE_BELOW_POLICY",
                    "termination": termination,
                }
            )
        else:
            index = len(episodes)
            episodes.append(
                WarningEpisode(
                    episode_id=_episode_id(
                        source_sha256,
                        policy.policy_version,
                        active_start,
                        active_first_sample_id or "",
                        index,
                    ),
                    run_id=run_id,
                    source_sha256=source_sha256,
                    start_s=active_start,
                    end_s=end_s,
                    duration_s=(
                        None
                        if end_s is None
                        else round(end_s - active_start, 9)
                    ),
                    warning_span_s=span,
                    sample_count=len(active_samples),
                    policy_version=policy.policy_version,
                    termination=termination,
                    censored=active_censored,
                    synthetic_control=synthetic_control,
                )
            )
        active_start = None
        active_last_warning = None
        active_first_sample_id = None
        active_samples = []
        active_censored = False

    seen: set[str] = set()
    for sample in samples:
        if sample.sample_id in seen:
            continue
        seen.add(sample.sample_id)
        if sample.state == WARNING:
            if active_start is None:
                active_start = sample.time_s
                active_first_sample_id = sample.sample_id
            elif (
                active_last_warning is not None
                and sample.time_s - active_last_warning > policy.bridge_gap_s
            ):
                close(TERMINATION_GAP, active_last_warning)
                active_start = sample.time_s
                active_first_sample_id = sample.sample_id
            active_last_warning = sample.time_s
            active_samples.append(sample)
        elif sample.state == NO_WARNING:
            if (
                active_start is not None
                and active_last_warning is not None
                and sample.time_s - active_last_warning > policy.bridge_gap_s
            ):
                close(TERMINATION_RECOVERED, active_last_warning)
        else:  # UNKNOWN
            if active_start is None:
                continue
            if not policy.bridge_unknown_gaps or (
                active_last_warning is not None
                and sample.time_s - active_last_warning > policy.bridge_gap_s
            ):
                close(TERMINATION_CENSORED, active_last_warning)
            else:
                active_censored = True
        last_state = sample.state
    if active_start is not None:
        censored = active_censored or last_state != WARNING
        close(
            TERMINATION_CENSORED if censored else TERMINATION_RUN_END,
            None if censored else active_last_warning,
        )
    return EpisodeBuildResult(tuple(episodes), tuple(discarded), policy)


def critical_events_from_replay(
    replay: ReplayResult,
    *,
    definition_version: str,
    source: str,
    trajectory_non_intervened: bool = True,
) -> tuple[CriticalEventInput, ...]:
    """Derive critical events from B0 criterion crossings only.

    B1 ON/OFF transitions are intentionally refused as critical events; a
    policy state transition is not evidence of a thermal criterion crossing.
    """
    if replay.baseline != B0_THRESHOLD:
        raise EventEvaluationError(
            "critical events may only come from a declared B0 criterion; "
            "B1 ON/OFF transitions are not thermal crossings"
        )
    events: list[CriticalEventInput] = []
    for transition in replay.criterion_crossings():
        events.append(
            CriticalEventInput(
                event_id=transition.event_id,
                time_s=transition.time_s,
                run_id=replay.run_id,
                source_sha256=replay.source_sha256,
                definition_version=definition_version,
                source=source,
                observed=True,
                trusted=True,
                intervention=not trajectory_non_intervened,
                time_certainty=transition.time_certainty,
                interval_start_s=transition.crossing_interval_start_s,
                interval_end_s=transition.crossing_interval_end_s,
            )
        )
    return tuple(events)


def _window_match(
    event_time: float, episode: WarningEpisode, policy: AssociationPolicy
) -> bool:
    """Match by episode onset within the declared association window.

    ``pre_window_s`` is how far before the event a warning onset may lie;
    ``post_window_s`` is how far after the event it may lie. The rule is
    deterministic and prevents a long episode from matching by overlap alone.
    """
    return (
        episode.start_s >= event_time - policy.pre_window_s
        and episode.start_s <= event_time + policy.post_window_s
    )


def evaluate_events(
    *,
    run_id: str | None,
    source_sha256: str,
    episodes: Sequence[WarningEpisode],
    critical_events: Sequence[CriticalEventInput],
    episode_policy: EpisodePolicy,
    association_policy: AssociationPolicy,
    warning_definition: str,
    coverage_trustworthy: bool,
    eligible_run_count: int,
    evaluable_duration_s: float | None,
    untrusted_intervals: Iterable[dict[str, Any]] = (),
    synthetic_control: bool = False,
) -> EventEvaluationResult:
    """Match warning episodes to observed critical events and compute metrics."""
    if eligible_run_count < 0:
        raise EventEvaluationError("eligible_run_count cannot be negative")
    if evaluable_duration_s is not None and (
        isinstance(evaluable_duration_s, bool)
        or not isinstance(evaluable_duration_s, (int, float))
        or not math.isfinite(float(evaluable_duration_s))
        or evaluable_duration_s < 0
    ):
        raise EventEvaluationError(
            "evaluable_duration_s must be a non-negative finite number"
        )
    events_by_id: dict[str, CriticalEventInput] = {}
    for event in critical_events:
        if event.event_id in events_by_id:
            raise EventEvaluationError(
                f"duplicate critical-event identity {event.event_id!r}"
            )
        events_by_id[event.event_id] = event
    unmatched_episodes = {episode.episode_id: episode for episode in episodes}
    matches: list[EpisodeMatch] = []
    missed: list[str] = []
    censored = 0
    untrusted = 0
    intervened = 0
    excluded_events: dict[str, str] = {}
    for event in sorted(
        critical_events, key=lambda item: (item.time_s is None, item.time_s or 0.0, item.event_id)
    ):
        if not event.observed:
            censored += 1
            excluded_events[event.event_id] = "EXCLUDED_CENSORED"
            continue
        if not event.trusted:
            untrusted += 1
            excluded_events[event.event_id] = "EXCLUDED_UNTRUSTED"
            continue
        if event.intervention:
            intervened += 1
            excluded_events[event.event_id] = "EXCLUDED_INTERVENTION"
            continue
        if event.time_s is None:
            untrusted += 1
            excluded_events[event.event_id] = "EXCLUDED_UNTRUSTED"
            continue
        candidates = [
            episode
            for episode in episodes
            if episode.episode_id in unmatched_episodes
            and _window_match(event.time_s, episode, association_policy)
        ]
        if not candidates:
            missed.append(event.event_id)
            continue
        chosen = sorted(
            candidates,
            key=lambda item: (abs(item.start_s - event.time_s), item.episode_id),
        )[0]
        alternatives = tuple(
            item.episode_id
            for item in candidates
            if item.episode_id != chosen.episode_id
        )
        matches.append(
            EpisodeMatch(
                event_id=event.event_id,
                episode_id=chosen.episode_id,
                event_time_s=event.time_s,
                episode_start_s=chosen.start_s,
                delta_s=round(event.time_s - chosen.start_s, 9),
                alternative_episode_ids=alternatives,
            )
        )
        unmatched_episodes.pop(chosen.episode_id, None)
    matched_episode_ids = {match.episode_id for match in matches}
    matched_events = {match.event_id for match in matches}
    eligible_event_ids = {
        event.event_id
        for event in critical_events
        if event.observed
        and event.trusted
        and not event.intervention
        and event.event_id not in excluded_events
    }
    denominator = len(eligible_event_ids)
    true_positive_episodes = len(matched_episode_ids)
    unmatched_count = len(unmatched_episodes)
    false_warning_episodes: int | None
    undefined_reasons: list[str] = []
    if coverage_trustworthy:
        false_warning_episodes = unmatched_count
    else:
        false_warning_episodes = None
        undefined_reasons.append(
            "COVERAGE_NOT_TRUSTWORTHY_FALSE_WARNING_BURDEN_UNDEFINED"
        )
    burden_per_run: float | None = None
    burden_per_hour: float | None = None
    if false_warning_episodes is not None and eligible_run_count > 0:
        burden_per_run = false_warning_episodes / eligible_run_count
    elif eligible_run_count == 0:
        undefined_reasons.append("NO_ELIGIBLE_RUN_DENOMINATOR")
    if (
        false_warning_episodes is not None
        and evaluable_duration_s is not None
        and evaluable_duration_s > 0
    ):
        burden_per_hour = (
            false_warning_episodes / (evaluable_duration_s / 3600.0)
        )
    elif evaluable_duration_s is None or evaluable_duration_s <= 0:
        undefined_reasons.append("NO_EVALUABLE_TIME_DENOMINATOR")
    precision: float | None = None
    if true_positive_episodes + unmatched_count > 0:
        precision = true_positive_episodes / (
            true_positive_episodes + unmatched_count
        )
    else:
        undefined_reasons.append("NO_WARNING_EPISODE_DENOMINATOR")
    recall: float | None = None
    if denominator > 0:
        recall = len(matched_events) / denominator
    else:
        undefined_reasons.append("NO_ELIGIBLE_CRITICAL_EVENT_DENOMINATOR")
    metrics = EventMetrics(
        true_matched_warning_episodes=true_positive_episodes,
        unmatched_warning_episodes=unmatched_count,
        missed_critical_events=len(missed),
        eligible_critical_event_denominator=denominator,
        false_warning_episodes=false_warning_episodes,
        false_warning_episodes_per_eligible_run=burden_per_run,
        false_warning_episodes_per_eligible_hour=burden_per_hour,
        event_precision=precision,
        event_recall=recall,
        censored_event_count=censored,
        untrusted_event_count=untrusted,
        intervened_event_count=intervened,
        run_support=eligible_run_count,
        event_support=denominator,
        episode_support=len(episodes),
        undefined_reasons=tuple(undefined_reasons),
    )
    events: list[dict[str, Any]] = []
    for event in critical_events:
        item = event.to_dict()
        item["match_status"] = (
            "MATCHED"
            if event.event_id in matched_events
            else excluded_events.get(event.event_id, "MISSED")
        )
        events.append(item)
    for episode in episodes:
        events.append(episode.to_dict() | {
            "match_status": (
                "MATCHED" if episode.episode_id in matched_episode_ids else "UNMATCHED"
            )
        })
    untrusted_list = list(untrusted_intervals)
    if not coverage_trustworthy:
        events.append(
            {
                "event_type": EVENT_CENSORED_OBSERVATION,
                "event_id": f"CENSORED:{source_sha256[:16]}",
                "time_s": None,
                "definition_version": EVENT_DEFINITION_VERSION,
                "source": "W09 coverage",
                "reason": "coverage is not trustworthy for event matching",
            }
        )
    elif denominator == 0 and not untrusted_list:
        events.append(
            {
                "event_type": EVENT_NO_EVENT_OBSERVATION,
                "event_id": f"NO_EVENT:{source_sha256[:16]}",
                "time_s": None,
                "definition_version": EVENT_DEFINITION_VERSION,
                "source": "W09 coverage",
                "reason": "fully observed eligible run with no critical event",
            }
        )
    for interval in untrusted_list:
        events.append(
            {
                "event_type": EVENT_UNTRUSTED_INTERVAL,
                "event_id": f"UNTRUSTED:{source_sha256[:16]}:{interval.get('start_s')}",
                "time_s": interval.get("start_s"),
                "end_s": interval.get("end_s"),
                "definition_version": EVENT_DEFINITION_VERSION,
                "source": "W09 refused interval",
                "reason": interval.get("reason"),
            }
        )
    return EventEvaluationResult(
        run_id=run_id,
        source_sha256=source_sha256,
        events=tuple(events),
        episodes=tuple(episodes),
        matches=tuple(matches),
        unmatched_episode_ids=tuple(sorted(unmatched_episodes)),
        missed_event_ids=tuple(missed),
        metrics=metrics,
        episode_policy=episode_policy,
        association_policy=association_policy,
        warning_definition=warning_definition,
        coverage_trustworthy=coverage_trustworthy,
        synthetic_control=synthetic_control,
    )


@dataclass(frozen=True)
class ChatterPolicy:
    """Declared diagnostic rule for rapid toggling; not a controller policy."""

    max_toggles: int
    window_s: float
    status: str
    source: str

    def __post_init__(self) -> None:
        if self.max_toggles < 2:
            raise EventEvaluationError("chatter requires at least two toggles")
        if not math.isfinite(self.window_s) or self.window_s <= 0:
            raise EventEvaluationError("chatter window must be positive")
        if not self.status.strip() or not self.source.strip():
            raise EventEvaluationError(
                "chatter status and source are required"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_toggles": self.max_toggles,
            "window_s": self.window_s,
            "status": self.status,
            "source": self.source,
        }


@dataclass(frozen=True)
class S1RunAnalysis:
    run_id: str | None
    source_sha256: str
    eligibility_status: str
    eligibility_reasons: tuple[str, ...]
    observation_duration_s: float | None
    evaluable_time_s: float | None
    unknown_time_s: float | None
    unknown_fraction: float | None
    diagnostic_unmatched_episodes: int
    false_warning_episode_count: int | None
    episode_start_end: tuple[tuple[float, float | None], ...]
    episode_durations_s: tuple[float | None, ...]
    state_transition_count: int
    on_off_toggles: int | None
    chatter_event_count: int | None
    warning_burden_per_run: float | None
    warning_burden_per_eligible_hour: float | None
    outcome_status: str
    outcome_reason: str
    synthetic_control: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_sha256": self.source_sha256,
            "eligibility_status": self.eligibility_status,
            "eligibility_reasons": list(self.eligibility_reasons),
            "observation_duration_s": self.observation_duration_s,
            "evaluable_time_s": self.evaluable_time_s,
            "unknown_time_s": self.unknown_time_s,
            "unknown_fraction": self.unknown_fraction,
            "diagnostic_unmatched_episodes": self.diagnostic_unmatched_episodes,
            "false_warning_episode_count": self.false_warning_episode_count,
            "episode_start_end": [
                list(item) for item in self.episode_start_end
            ],
            "episode_durations_s": list(self.episode_durations_s),
            "state_transition_count": self.state_transition_count,
            "on_off_toggles": self.on_off_toggles,
            "chatter_event_count": self.chatter_event_count,
            "warning_burden_per_run": self.warning_burden_per_run,
            "warning_burden_per_eligible_hour": (
                self.warning_burden_per_eligible_hour
            ),
            "outcome_status": self.outcome_status,
            "outcome_reason": self.outcome_reason,
            "synthetic_control": self.synthetic_control,
        }


def _chatter_count(
    transitions: Sequence[Any], policy: ChatterPolicy
) -> int:
    times = [item.time_s for item in transitions]
    events = 0
    for index, start in enumerate(times):
        window_end = start + policy.window_s
        count = sum(
            1 for value in times[index:] if value <= window_end
        )
        if count >= policy.max_toggles:
            events += 1
    return events


def analyze_s1_run(
    replay: ReplayResult,
    evaluation: EventEvaluationResult,
    *,
    eligibility_status: str,
    eligibility_reasons: Sequence[str],
    chatter_policy: ChatterPolicy,
    coverage_trustworthy: bool,
    eligible_run_count: int,
    synthetic_control: bool = False,
) -> S1RunAnalysis:
    """Per-run S1 false-warning/stability summary with eligibility gating."""
    if eligibility_status not in (
        ELIGIBLE_FOR_S1_DATASET,
        DIAGNOSTIC_ONLY,
        BLOCKED,
    ):
        raise EventEvaluationError(
            "eligibility_status must be ELIGIBLE_FOR_S1_DATASET, "
            "DIAGNOSTIC_ONLY or BLOCKED"
        )
    coverage = replay.coverage
    transitions = replay.transitions
    toggles: int | None = None
    chatter: int | None = None
    if replay.baseline in (B1_HYSTERESIS, B1_PERSISTENCE_CANDIDATE):
        on_off = [
            item
            for item in transitions
            if item.event_type in (TRANSITION_ON, TRANSITION_OFF)
        ]
        toggles = len(on_off)
        chatter = _chatter_count(on_off, chatter_policy)
    eligible = (
        eligibility_status == ELIGIBLE_FOR_S1_DATASET
        and coverage_trustworthy
    )
    false_count = (
        evaluation.metrics.false_warning_episodes if eligible else None
    )
    burden_run = None
    burden_hour = None
    if eligible and eligible_run_count > 0 and false_count is not None:
        burden_run = false_count / eligible_run_count
    if (
        eligible
        and false_count is not None
        and coverage.evaluable_duration_s
        and coverage.evaluable_duration_s > 0
    ):
        burden_hour = false_count / (coverage.evaluable_duration_s / 3600.0)
    if eligible:
        outcome_status = METRIC_DEFINED
        outcome_reason = "eligible, fully observed S1 run under the declared policy"
    elif not coverage_trustworthy:
        outcome_status = METRIC_UNDEFINED
        outcome_reason = "coverage is not trustworthy; the run is not a negative control"
    else:
        outcome_status = METRIC_UNDEFINED
        outcome_reason = (
            "run is not eligible for the S1 dataset; diagnostic replay only"
        )
    return S1RunAnalysis(
        run_id=replay.run_id,
        source_sha256=replay.source_sha256,
        eligibility_status=eligibility_status,
        eligibility_reasons=tuple(eligibility_reasons),
        observation_duration_s=coverage.observation_duration_s,
        evaluable_time_s=coverage.evaluable_duration_s,
        unknown_time_s=coverage.unknown_duration_s,
        unknown_fraction=(
            None
            if coverage.observation_duration_s in (None, 0)
            else round(
                (coverage.unknown_duration_s or 0.0)
                / coverage.observation_duration_s,
                9,
            )
        ),
        diagnostic_unmatched_episodes=evaluation.metrics.unmatched_warning_episodes,
        false_warning_episode_count=false_count,
        episode_start_end=tuple(
            (episode.start_s, episode.end_s) for episode in evaluation.episodes
        ),
        episode_durations_s=tuple(
            episode.duration_s for episode in evaluation.episodes
        ),
        state_transition_count=len(transitions),
        on_off_toggles=toggles,
        chatter_event_count=chatter,
        warning_burden_per_run=burden_run,
        warning_burden_per_eligible_hour=burden_hour,
        outcome_status=outcome_status,
        outcome_reason=outcome_reason,
        synthetic_control=synthetic_control,
    )


@dataclass(frozen=True)
class S1Aggregate:
    runs: tuple[S1RunAnalysis, ...]
    eligible_run_count: int
    estimable_run_count: int
    false_warning_episodes_per_eligible_run: float | None
    false_warning_episodes_per_eligible_hour: float | None
    stability_status: str
    stability_reasons: tuple[str, ...]
    synthetic_control: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "runs": [item.to_dict() for item in self.runs],
            "eligible_run_count": self.eligible_run_count,
            "estimable_run_count": self.estimable_run_count,
            "false_warning_episodes_per_eligible_run": (
                self.false_warning_episodes_per_eligible_run
            ),
            "false_warning_episodes_per_eligible_hour": (
                self.false_warning_episodes_per_eligible_hour
            ),
            "stability_status": self.stability_status,
            "stability_reasons": list(self.stability_reasons),
            "synthetic_control": self.synthetic_control,
        }


def aggregate_s1(runs: Sequence[S1RunAnalysis], *, synthetic_control: bool = False) -> S1Aggregate:
    eligible = [
        item for item in runs if item.outcome_status == METRIC_DEFINED
    ]
    false_total = sum(
        item.false_warning_episode_count or 0 for item in eligible
    )
    per_run = (
        false_total / len(eligible) if eligible else None
    )
    total_hours = sum(
        (item.evaluable_time_s or 0.0) / 3600.0 for item in eligible
    )
    per_hour = false_total / total_hours if total_hours > 0 else None
    reasons: list[str] = []
    if not eligible:
        reasons.append("NO_ELIGIBLE_S1_RUN")
    if synthetic_control:
        reasons.append("SYNTHETIC_CONTROL_ONLY")
    stability = (
        "NOT_ESTABLISHED"
        if not eligible or synthetic_control
        else "DIAGNOSTIC_ONLY"
    )
    return S1Aggregate(
        runs=tuple(runs),
        eligible_run_count=len(eligible),
        estimable_run_count=len(eligible),
        false_warning_episodes_per_eligible_run=per_run,
        false_warning_episodes_per_eligible_hour=per_hour,
        stability_status=stability,
        stability_reasons=tuple(reasons),
        synthetic_control=synthetic_control,
    )


def baseline_ewt(
    *,
    t_predictive_s: float | None,
    t_reactive_s: float | None,
    warning_present: bool,
    warning_persistent: bool,
    reactive_event_type: str,
    trajectory_non_intervened: bool,
    timestamps_trusted: bool,
    provenance: EWTProvenance | None,
) -> EWTResult:
    """W04-compatible EWT wrapper that refuses non-criterion reactive events.

    An ON transition is a policy state, not a thermal crossing. Passing it as
    the reactive event yields a censored/no-crossing result, never a fake EWT.
    """
    crossing_observed = reactive_event_type == TRANSITION_CRITERION
    result = compute_ewt(
        t_predictive_s=t_predictive_s,
        t_reactive_s=t_reactive_s,
        warning_present=warning_present,
        warning_persistent=warning_persistent,
        reactive_crossing_observed=crossing_observed,
        trajectory_non_intervened=trajectory_non_intervened,
        timestamps_trusted=timestamps_trusted,
        provenance=provenance,
    )
    if not crossing_observed and result.status is EWTStatus.MISSING_REACTIVE_CROSSING:
        return EWTResult(
            status=result.status,
            ewt_s=None,
            reason=(
                "the reactive event is not a thermal criterion crossing "
                "(an ON transition is not a critical event)"
            ),
            provenance=result.provenance,
        )
    return result


def aiw_boundary_status() -> dict[str, Any]:
    return {
        "status": AIW_STATUS,
        "reason": AIW_REASON,
        "synthetic_latency_allowed": False,
    }
