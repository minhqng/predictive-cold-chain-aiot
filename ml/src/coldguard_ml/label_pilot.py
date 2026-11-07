"""W10 development-only label pilot (B-W10-04).

The pilot reuses the W02 label contract. It does not invent a final critical
boundary, representative temperature or primary horizon: every spec carries
``frozen_at=None`` and an explicit development-only status. Labels are built
after features and are never written into feature rows.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .feature_pipeline import (
    PRESENT,
    FeatureRow,
    Trajectory,
)
from .labels import CriticalEventSeries, LabelSpec, LabelStatus, generate_label_records

LABEL_PILOT_VERSION = "coldguard-w10-label-pilot-v1"
DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY_NOT_FROZEN"
NOT_FROZEN = "NOT_FROZEN"
CANDIDATE_HORIZONS_S = (30.0, 60.0, 120.0, 300.0)
REPRESENTATIVE_NOT_SELECTED = "DEVELOPMENT_CANDIDATE_NOT_SELECTED"
PREDICTIVE_CONTROLLERS = frozenset(
    {"CONTROLLER-B", "CONTROLLER-B-PREDICTIVE", "PREDICTIVE_CONTROLLER_B"}
)
REAL_PILOT_NOT_EVALUABLE = "NOT_EVALUABLE"


class LabelPilotError(ValueError):
    """The pilot would present development output as frozen evidence."""


@dataclass(frozen=True)
class PilotConfig:
    horizons_s: tuple[float, ...] = CANDIDATE_HORIZONS_S
    spec_version: str = LABEL_PILOT_VERSION
    representative_temperature: str = REPRESENTATIVE_NOT_SELECTED
    boundary_c: float | None = None

    def __post_init__(self) -> None:
        if not self.horizons_s or any(value <= 0 for value in self.horizons_s):
            raise LabelPilotError("pilot horizons must be positive")
        if self.representative_temperature != REPRESENTATIVE_NOT_SELECTED:
            raise LabelPilotError(
                "the W10 pilot must not select a final representative temperature"
            )
        if self.boundary_c is not None:
            raise LabelPilotError(
                "the W10 pilot must not select a final critical boundary"
            )

    def spec_for(self, horizon_s: float) -> LabelSpec:
        return LabelSpec(
            horizon_s=horizon_s,
            spec_version=self.spec_version,
            representative_temperature=self.representative_temperature,
            boundary_c=None,
            frozen_at=None,
        )


@dataclass(frozen=True)
class HorizonPilot:
    horizon_s: float
    spec_identity: Mapping[str, Any]
    independent_runs: int
    anchors: int
    positive: int
    negative: int
    censored: int
    untrusted: int
    prevalence: float | None
    feature_available_anchors: int
    feature_values_present: int
    feature_values_total: int
    coverage_limitations: tuple[str, ...]
    source_policy_version: str
    freeze_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_s": self.horizon_s,
            "spec_identity": dict(self.spec_identity),
            "independent_development_runs": self.independent_runs,
            "dependent_window_count": self.anchors,
            "positive_labels": self.positive,
            "negative_labels": self.negative,
            "censored_labels": self.censored,
            "untrusted_labels": self.untrusted,
            "positive_prevalence": self.prevalence,
            "feature_available_anchors": self.feature_available_anchors,
            "feature_values_present": self.feature_values_present,
            "feature_values_total": self.feature_values_total,
            "coverage_limitations": list(self.coverage_limitations),
            "source_and_policy_version": self.source_policy_version,
            "freeze_status": self.freeze_status,
        }


@dataclass(frozen=True)
class LabelPilotResult:
    status: str
    config: PilotConfig
    horizons: tuple[HorizonPilot, ...]
    excluded_runs: tuple[tuple[str, str], ...]
    population: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "population": self.population,
            "config": {
                "horizons_s": list(self.config.horizons_s),
                "spec_version": self.config.spec_version,
                "representative_temperature": self.config.representative_temperature,
                "boundary_c": self.config.boundary_c,
                "frozen_at": None,
            },
            "excluded_runs": [
                {"run_id": run_id, "reason": reason}
                for run_id, reason in self.excluded_runs
            ],
            "horizons": [item.to_dict() for item in self.horizons],
        }


def _anchor_time(trajectory: Trajectory, anchor_t_s: float) -> _dt.datetime:
    if trajectory.origin_utc is None:
        raise LabelPilotError(
            f"run {trajectory.run_id!r} has no absolute origin for label anchors"
        )
    origin = _dt.datetime.fromisoformat(
        trajectory.origin_utc.replace("Z", "+00:00")
    )
    return origin + _dt.timedelta(seconds=anchor_t_s)


def run_label_pilot(
    trajectories: Sequence[Trajectory],
    series_by_run: Mapping[str, CriticalEventSeries],
    feature_rows_by_run: Mapping[str, Sequence[FeatureRow]],
    *,
    config: PilotConfig | None = None,
    partitions: Sequence[str] = ("train", "validation"),
    population: str = "SYNTHETIC_DEVELOPMENT",
) -> LabelPilotResult:
    """Evaluate candidate horizons on development partitions only.

    A predictive closed-loop trajectory is excluded: an event prevented by
    intervention is an unobserved counterfactual, not an observational
    negative. The locked test partition is never used here.
    """
    pilot_config = config or PilotConfig()
    included: list[tuple[Trajectory, Sequence[FeatureRow]]] = []
    excluded: list[tuple[str, str]] = []
    for trajectory in trajectories:
        if trajectory.run_id is None:
            excluded.append(("<unresolved-run>", "RUN_IDENTITY_UNRESOLVED"))
            continue
        partition = None
        for row in feature_rows_by_run.get(trajectory.run_id, ()):
            partition = row.split_partition
            break
        if partitions and partition not in partitions:
            excluded.append((trajectory.run_id, f"PARTITION_{partition}_NOT_DEVELOPMENT"))
            continue
        if trajectory.controller_id in PREDICTIVE_CONTROLLERS:
            excluded.append(
                (trajectory.run_id, "PREDICTIVE_CLOSED_LOOP_NOT_OBSERVATIONAL")
            )
            continue
        if trajectory.run_id not in series_by_run:
            excluded.append((trajectory.run_id, "NO_CRITICAL_EVENT_SERIES"))
            continue
        rows = feature_rows_by_run.get(trajectory.run_id, ())
        if not rows:
            excluded.append((trajectory.run_id, "NO_FEATURE_ANCHORS"))
            continue
        included.append((trajectory, rows))

    if not included:
        return LabelPilotResult(
            status=REAL_PILOT_NOT_EVALUABLE,
            config=pilot_config,
            horizons=(),
            excluded_runs=tuple(excluded),
            population=population,
        )

    horizon_results: list[HorizonPilot] = []
    for horizon_s in pilot_config.horizons_s:
        spec = pilot_config.spec_for(horizon_s)
        positive = negative = censored = untrusted = anchors = 0
        runs = 0
        available_anchors = values_present = values_total = 0
        for trajectory, rows in included:
            series = series_by_run[trajectory.run_id]  # type: ignore[index]
            anchor_pairs = [
                (_anchor_time(trajectory, row.anchor_t_s), row) for row in rows
            ]
            coverage_end = series.coverage_end
            if coverage_end is None:
                coverage_end = _anchor_time(
                    trajectory, trajectory.samples[-1].time_s
                )
            records = generate_label_records(
                trajectory.run_id,  # type: ignore[arg-type]
                anchor_pairs,
                series,
                spec,
                coverage_end=coverage_end,
            )
            runs += 1
            anchors += len(records)
            for record in records:
                if record.status is LabelStatus.EVALUABLE:
                    if record.y == 1:
                        positive += 1
                    else:
                        negative += 1
                elif record.status is LabelStatus.CENSORED:
                    censored += 1
                else:
                    untrusted += 1
            for row in rows:
                present = sum(
                    1 for reason in row.missing_reasons if reason == PRESENT
                )
                values_present += present
                values_total += len(row.missing_reasons)
                if present:
                    available_anchors += 1
        evaluable = positive + negative
        horizon_results.append(
            HorizonPilot(
                horizon_s=horizon_s,
                spec_identity=spec.identity_fields,
                independent_runs=runs,
                anchors=anchors,
                positive=positive,
                negative=negative,
                censored=censored,
                untrusted=untrusted,
                prevalence=(positive / evaluable if evaluable else None),
                feature_available_anchors=available_anchors,
                feature_values_present=values_present,
                feature_values_total=values_total,
                coverage_limitations=(
                    "development partitions only; the locked test partition is not used",
                    "censored horizons are not negatives",
                    "critical event series is a prescribed synthetic fixture; no physical authority",
                    "boundary, representative temperature and primary horizon remain unfrozen",
                ),
                source_policy_version=pilot_config.spec_version,
                freeze_status=DEVELOPMENT_ONLY,
            )
        )
    return LabelPilotResult(
        status="DEVELOPMENT_ONLY",
        config=pilot_config,
        horizons=tuple(horizon_results),
        excluded_runs=tuple(excluded),
        population=population,
    )


def assess_real_pilot(
    *,
    eligible_s2_runs: int,
    authoritative_series_present: bool,
    gate_b_physical: str,
) -> dict[str, Any]:
    """Real label-pilot status under the current Gate B restriction."""
    if gate_b_physical == "RED" and (
        eligible_s2_runs > 0 or authoritative_series_present
    ):
        raise LabelPilotError(
            "a RED Gate B cannot be overridden by a real label pilot"
        )
    if eligible_s2_runs == 0 or not authoritative_series_present:
        return {
            "REAL_S2_LABEL_PILOT": REAL_PILOT_NOT_EVALUABLE,
            "ELIGIBLE_S2_RUNS": eligible_s2_runs,
            "REAL_HORIZON_SELECTION": NOT_FROZEN,
            "reason": (
                "Gate B is RED, no eligible S2 run exists and no authoritative "
                "critical-event series is available for the real capture"
            ),
        }
    return {
        "REAL_S2_LABEL_PILOT": "EVALUABLE",
        "ELIGIBLE_S2_RUNS": eligible_s2_runs,
        "REAL_HORIZON_SELECTION": NOT_FROZEN,
        "reason": "eligible development runs exist; horizon selection still requires its own freeze",
    }
