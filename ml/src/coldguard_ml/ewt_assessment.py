"""W12 EWT assessment and the strict EWT/AIW separation (B-W12-03).

Synthetic timing cases exist only to exercise the W04 contract. They are never
physical evidence and never establish AIW.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .evaluation_contract import (
    EWTProvenance,
    EWTStatus,
    compute_ewt,
)
from .event_evaluator import (
    WARNING,
    EpisodePolicy,
    WarningSample,
    build_warning_episodes,
)

EWT_ASSESSMENT_SCHEMA = "coldguard-w12-ewt-assessment-v1"
SYNTHETIC_TIMING_LABEL = "SYNTHETIC_TIMING_CONTRACT_TEST_ONLY"
REAL_EWT_STATUS = "NOT_ESTIMABLE"
REAL_AIW_STATUS = "NOT_ESTIMABLE"
EWT_REASON_NO_COMMON_TRAJECTORY = "EWT_UNAVAILABLE_NO_QUALIFIED_COMMON_TRAJECTORY"
EWT_REASON_ANCHOR_UNDEFINED = "EWT_UNAVAILABLE_WARNING_OR_REACTIVE_ANCHOR_NOT_DEFINED"
EWT_REASON_INCOMPATIBLE_CLOCK = "EWT_UNAVAILABLE_INCOMPATIBLE_CLOCK_DOMAIN"
EWT_REASON_INTERVENED = "EWT_UNAVAILABLE_INTERVENED_TRAJECTORY"
AIW_REASON_MISSING_CHAIN = "AIW_UNAVAILABLE_MEASURED_LATENCY_CHAIN_MISSING"
REAL_REASON_NO_POPULATION = (
    "no eligible non-intervened physical event population and no authoritative "
    "frozen warning/reactive timing pair"
)


@dataclass(frozen=True)
class TimingCaseResult:
    case_id: str
    event_id: str
    population: str
    label: str
    status: str
    ewt_s: float | None
    reason_code: str
    reason: str
    predictive_run_id: str
    reactive_run_id: str
    predictive_clock_domain: str
    reactive_clock_domain: str
    warning_definition: str
    persistence_definition: str
    intervention: bool

    def to_row(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "event_id": self.event_id,
            "population": self.population,
            "label": self.label,
            "status": self.status,
            "ewt_s": self.ewt_s,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "predictive_run_id": self.predictive_run_id,
            "reactive_run_id": self.reactive_run_id,
            "predictive_clock_domain": self.predictive_clock_domain,
            "reactive_clock_domain": self.reactive_clock_domain,
            "warning_definition": self.warning_definition,
            "persistence_definition": self.persistence_definition,
            "intervention": self.intervention,
        }


@dataclass(frozen=True)
class EWTAssessment:
    schema: str
    synthetic_cases: tuple[TimingCaseResult, ...]
    real_status: Mapping[str, Any]
    definitions: Mapping[str, str]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "synthetic_cases": [case.to_row() for case in self.synthetic_cases],
            "real_status": dict(self.real_status),
            "definitions": dict(self.definitions),
            "limitations": list(self.limitations),
        }


def assess_timing_pair(
    *,
    case_id: str,
    t_predictive_s: float | None,
    t_reactive_s: float | None,
    predictive_run_id: str,
    reactive_run_id: str,
    predictive_clock_domain: str,
    reactive_clock_domain: str,
    warning_present: bool,
    warning_persistent: bool,
    reactive_crossing_observed: bool,
    trajectory_non_intervened: bool,
    timestamps_trusted: bool,
    event_id: str,
    warning_definition: str,
    persistence_definition: str,
) -> TimingCaseResult:
    common = dict(
        event_id=event_id,
        population="synthetic timing contract",
        label=SYNTHETIC_TIMING_LABEL,
        predictive_run_id=predictive_run_id,
        reactive_run_id=reactive_run_id,
        predictive_clock_domain=predictive_clock_domain,
        reactive_clock_domain=reactive_clock_domain,
        warning_definition=warning_definition,
        persistence_definition=persistence_definition,
        intervention=not trajectory_non_intervened,
    )
    if predictive_run_id != reactive_run_id:
        return TimingCaseResult(
            case_id=case_id,
            status="REFUSED_CROSS_RUN",
            ewt_s=None,
            reason_code=EWT_REASON_NO_COMMON_TRAJECTORY,
            reason=(
                "predictive and reactive anchors come from different run "
                "identities; a cross-run EWT is not a common trajectory"
            ),
            **common,
        )
    if predictive_clock_domain != reactive_clock_domain:
        return TimingCaseResult(
            case_id=case_id,
            status="REFUSED_CROSS_CLOCK",
            ewt_s=None,
            reason_code=EWT_REASON_INCOMPATIBLE_CLOCK,
            reason=(
                "predictive and reactive anchors use different clock domains; "
                "no shared event-time axis exists"
            ),
            **common,
        )
    provenance = EWTProvenance(
        run_id=predictive_run_id,
        event_id=event_id,
        warning_definition=warning_definition,
        persistence_definition=persistence_definition,
    )
    result = compute_ewt(
        t_predictive_s=t_predictive_s,
        t_reactive_s=t_reactive_s,
        warning_present=warning_present,
        warning_persistent=warning_persistent,
        reactive_crossing_observed=reactive_crossing_observed,
        trajectory_non_intervened=trajectory_non_intervened,
        timestamps_trusted=timestamps_trusted,
        provenance=provenance,
    )
    if result.status is EWTStatus.ESTIMABLE:
        reason_code = "EWT_ESTIMABLE"
    elif result.status is EWTStatus.INADMISSIBLE_INTERVENED_TRAJECTORY:
        reason_code = EWT_REASON_INTERVENED
    elif result.status is EWTStatus.UNTRUSTED_TIMESTAMPS:
        reason_code = EWT_REASON_INCOMPATIBLE_CLOCK
    else:
        reason_code = EWT_REASON_ANCHOR_UNDEFINED
    return TimingCaseResult(
        case_id=case_id,
        status=result.status.value,
        ewt_s=result.ewt_s,
        reason_code=reason_code,
        reason=result.reason,
        **common,
    )


def _first_episode_onset() -> tuple[float, str]:
    policy = EpisodePolicy(
        policy_version="coldguard-w12-synthetic-timing-episode-v1",
        min_persistence_s=0.0,
        bridge_gap_s=2.0,
        bridge_unknown_gaps=False,
        status=SYNTHETIC_TIMING_LABEL,
        source="W12 synthetic timing contract",
    )
    samples = (
        WarningSample(time_s=80.0, state=WARNING, sample_id="w80"),
        WarningSample(time_s=81.0, state=WARNING, sample_id="w81"),
        WarningSample(time_s=120.0, state=WARNING, sample_id="w120"),
        WarningSample(time_s=121.0, state=WARNING, sample_id="w121"),
    )
    episodes = build_warning_episodes(
        samples,
        policy,
        run_id="SYNTHETIC-TIMING-RUN",
        source_sha256="synthetic-timing-source",
        synthetic_control=True,
    ).episodes
    if len(episodes) < 2:
        raise ValueError("synthetic first-onset case must yield two episodes")
    definition = (
        f"sustained warning episode with min_persistence_s="
        f"{policy.min_persistence_s:g}, bridge_gap_s={policy.bridge_gap_s:g} "
        f"({policy.policy_version})"
    )
    return episodes[0].start_s, definition


def _case(**kwargs: Any) -> TimingCaseResult:
    return assess_timing_pair(**kwargs)


def synthetic_timing_cases() -> tuple[TimingCaseResult, ...]:
    base = dict(
        predictive_run_id="SYNTHETIC-TIMING-RUN",
        reactive_run_id="SYNTHETIC-TIMING-RUN",
        predictive_clock_domain="BOOT_SCOPED_UPTIME",
        reactive_clock_domain="BOOT_SCOPED_UPTIME",
        warning_present=True,
        warning_persistent=True,
        reactive_crossing_observed=True,
        trajectory_non_intervened=True,
        timestamps_trusted=True,
        event_id="SYNTHETIC-EVENT-1",
        warning_definition="w12-persistent-risk-warning-v1",
        persistence_definition="w12-sustained-30s-v1",
    )
    first_onset, persistence_definition = _first_episode_onset()
    return (
        _case(
            case_id="CASE_A_POSITIVE_EWT",
            t_predictive_s=80.0,
            t_reactive_s=100.0,
            **base,
        ),
        _case(
            case_id="CASE_B_NEGATIVE_EWT",
            t_predictive_s=110.0,
            t_reactive_s=100.0,
            **base,
        ),
        _case(
            case_id="CASE_C_ZERO_EWT",
            t_predictive_s=100.0,
            t_reactive_s=100.0,
            **base,
        ),
        _case(
            case_id="CASE_D_NO_PERSISTENT_WARNING",
            t_predictive_s=None,
            t_reactive_s=100.0,
            **{**base, "warning_present": False},
        ),
        _case(
            case_id="CASE_E_NO_REACTIVE_CROSSING",
            t_predictive_s=80.0,
            t_reactive_s=None,
            **{**base, "reactive_crossing_observed": False},
        ),
        _case(
            case_id="CASE_F_CROSS_RUN",
            t_predictive_s=80.0,
            t_reactive_s=100.0,
            **{**base, "reactive_run_id": "OTHER-RUN"},
        ),
        _case(
            case_id="CASE_G_CROSS_CLOCK",
            t_predictive_s=80.0,
            t_reactive_s=100.0,
            **{**base, "reactive_clock_domain": "ABSOLUTE_UTC"},
        ),
        _case(
            case_id="CASE_H_INTERVENED",
            t_predictive_s=80.0,
            t_reactive_s=100.0,
            **{**base, "trajectory_non_intervened": False},
        ),
        _case(
            case_id="CASE_I_FIRST_VALID_ONSET",
            t_predictive_s=first_onset,
            t_reactive_s=100.0,
            **{**base, "persistence_definition": persistence_definition},
        ),
    )


def assess_real_ewt_aiw(
    w11_manifest: Mapping[str, Any],
    *,
    w06_counts: Mapping[str, Any] | None = None,
) -> EWTAssessment:
    real = w11_manifest.get("real_development", {})
    eligible = int(real.get("ELIGIBLE_RUNS", 0) or 0)
    if eligible:
        raise ValueError(
            "W12 refuses to keep a NOT_ESTIMABLE real EWT while eligible runs exist; "
            "re-assess from authoritative timing evidence"
        )
    real_aiw_reasons = [AIW_REASON_MISSING_CHAIN, REAL_REASON_NO_POPULATION]
    if w06_counts is not None:
        if int(w06_counts.get("real_measured_response_delays", 0) or 0) == 0:
            real_aiw_reasons.append("NO_REAL_MEASURED_RESPONSE_DELAY")
        if int(w06_counts.get("thermal_verified_responses", 0) or 0) == 0:
            real_aiw_reasons.append("NO_THERMAL_VERIFIED_RESPONSE")
        if int(w06_counts.get("electrical_verified_responses", 0) or 0) == 0:
            real_aiw_reasons.append("NO_ELECTRICAL_VERIFIED_RESPONSE")
    real_status = {
        "population": "real physical non-intervened runs",
        "eligible_runs": eligible,
        "REAL_EWT": REAL_EWT_STATUS,
        "REAL_EWT_REASON_CODE": EWT_REASON_NO_COMMON_TRAJECTORY,
        "REAL_EWT_REASON": REAL_REASON_NO_POPULATION,
        "REAL_AIW": REAL_AIW_STATUS,
        "REAL_AIW_REASON_CODE": AIW_REASON_MISSING_CHAIN,
        "REAL_AIW_REASON": (
            "no complete measured command/ACK/electrical/thermal latency chain"
        ),
        "real_aiw_supporting_reasons": real_aiw_reasons,
        "ewt_does_not_imply_aiw": True,
    }
    definitions = {
        "warning_definition": "first valid persistent predictive warning",
        "persistence_definition": "w12-sustained-30s-v1 reviewed declaration",
        "reactive_definition": "first valid reactive criterion crossing",
        "ewt_formula": "EWT = t_reactive - t_predictive",
        "aiw_formula": "AIW = t_critical - t_warning - T_system - T_physical",
        "intervention_rule": (
            "a predictively intervened trajectory is inadmissible for offline "
            "counterfactual EWT"
        ),
    }
    limitations = (
        "Synthetic timing cases demonstrate arithmetic and refusal behavior only.",
        "Real EWT and AIW remain NOT_ESTIMABLE while eligible physical runs are zero.",
        "An estimable EWT would not establish AIW or physical actionability.",
        "Negative EWT values are legitimate late-warning results and are preserved.",
    )
    return EWTAssessment(
        schema=EWT_ASSESSMENT_SCHEMA,
        synthetic_cases=synthetic_timing_cases(),
        real_status=real_status,
        definitions=definitions,
        limitations=limitations,
    )
