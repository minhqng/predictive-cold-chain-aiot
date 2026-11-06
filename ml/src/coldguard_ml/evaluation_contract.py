"""W04 evaluation interface guards (B-W04-02, B-W04-03, B-W04-04).

These helpers freeze *shapes*, not physical constants:

* :func:`compute_ewt` encodes the conceptual EWT rule
  ``EWT = t_reactive - t_predictive`` only for a non-predictively-intervened,
  trusted, completely observed trajectory. A missing warning is a missed-event
  state, never ``EWT = 0``; an unobserved reactive crossing is censored, never
  a fabricated time.
* :func:`compute_aiw` validates the timing interface
  ``AIW = t_critical - t_warning - T_system - T_physical``. It refuses to
  estimate anything when a measured component is missing or untrusted, and it
  refuses components that overlap within one chain or across the
  T_system/T_physical decomposition, since those spans would be counted
  twice. Real time-alignment computation belongs to W06; this is an
  interface guard.
* :class:`MetricHierarchy` refuses to let a secondary/diagnostic metric become
  primary without a recorded amendment, and it refuses to open a locked
  holdout for selection or fitting.

No operating threshold, persistence constant, horizon, critical value,
response delay or measured result is produced here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

__all__ = [
    "AIWResult",
    "AIWStatus",
    "Amendment",
    "EWTProvenance",
    "EWTResult",
    "EWTStatus",
    "EvaluationContractError",
    "InterventionEvidence",
    "LatencyComponent",
    "MetricHierarchy",
    "MetricHierarchyError",
    "PRIMARY_PHYSICAL_OUTCOME",
    "PRIMARY_PREDICTIVE_METRIC",
    "SECONDARY_PHYSICAL_OUTCOMES",
    "assert_allowed_for_selection",
    "compute_aiw",
    "compute_ewt",
    "paired_improvement",
]


class EvaluationContractError(ValueError):
    """A frozen evaluation-interface rule was violated."""


class MetricHierarchyError(EvaluationContractError):
    """A metric was used outside the frozen hierarchy."""


class EWTStatus(str, Enum):
    ESTIMABLE = "ESTIMABLE"
    MISSING_WARNING = "MISSING_WARNING"
    MISSING_REACTIVE_CROSSING = "MISSING_REACTIVE_CROSSING"
    INADMISSIBLE_INTERVENED_TRAJECTORY = "INADMISSIBLE_INTERVENED_TRAJECTORY"
    UNTRUSTED_TIMESTAMPS = "UNTRUSTED_TIMESTAMPS"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"


@dataclass(frozen=True)
class EWTProvenance:
    """Identity and definitions every EWT result must carry."""

    run_id: str
    event_id: str
    warning_definition: str
    persistence_definition: str

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "event_id",
            "warning_definition",
            "persistence_definition",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise EvaluationContractError(
                    f"EWT provenance requires a non-empty {name}"
                )

    def to_dict(self) -> dict[str, str]:
        return {
            "run_id": self.run_id,
            "event_id": self.event_id,
            "warning_definition": self.warning_definition,
            "persistence_definition": self.persistence_definition,
        }


@dataclass(frozen=True)
class EWTResult:
    status: EWTStatus
    ewt_s: float | None
    reason: str
    provenance: EWTProvenance | None = None

    def __post_init__(self) -> None:
        if (
            self.status is not EWTStatus.MISSING_PROVENANCE
            and self.provenance is None
        ):
            raise EvaluationContractError(
                "an EWT result other than MISSING_PROVENANCE requires "
                "run/event provenance"
            )
        if self.status is EWTStatus.ESTIMABLE:
            if self.ewt_s is None:
                raise EvaluationContractError(
                    "an ESTIMABLE EWT result requires a numeric ewt_s"
                )
            if isinstance(self.ewt_s, bool) or not isinstance(
                self.ewt_s, (int, float)
            ) or not math.isfinite(float(self.ewt_s)):
                raise EvaluationContractError(
                    "an ESTIMABLE EWT result requires a finite numeric ewt_s"
                )
        elif self.ewt_s is not None:
            raise EvaluationContractError(
                "a non-ESTIMABLE EWT result carries ewt_s=None"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "ewt_s": self.ewt_s,
            "reason": self.reason,
            "provenance": (
                None if self.provenance is None else self.provenance.to_dict()
            ),
        }


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationContractError(f"{name} must be a real number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise EvaluationContractError(f"{name} must be finite, got {value!r}")
    return number


def compute_ewt(
    *,
    t_predictive_s: float | None,
    t_reactive_s: float | None,
    warning_present: bool,
    warning_persistent: bool,
    reactive_crossing_observed: bool,
    trajectory_non_intervened: bool,
    timestamps_trusted: bool,
    provenance: EWTProvenance | None = None,
) -> EWTResult:
    """Conceptual EWT on one eligible, offline, non-intervened trajectory.

    The caller supplies event-time seconds already mapped onto one trusted
    domain. This function never repairs timestamps and never invents a
    crossing. A Controller B trajectory is inadmissible because the
    intervention destroys the counterfactual crossing time (Doc ``03`` §45).
    Every result must carry run/event identity and the warning/persistence
    definitions; a missing provenance is its own fail-closed state.
    """
    if provenance is None:
        return EWTResult(
            status=EWTStatus.MISSING_PROVENANCE,
            ewt_s=None,
            reason=(
                "run/event identity and warning/persistence definitions are "
                "required for an EWT result"
            ),
        )
    if not trajectory_non_intervened:
        return EWTResult(
            status=EWTStatus.INADMISSIBLE_INTERVENED_TRAJECTORY,
            ewt_s=None,
            reason=(
                "a predictively intervened trajectory has no observable "
                "counterfactual reactive crossing; naive offline EWT is void"
            ),
            provenance=provenance,
        )
    if not timestamps_trusted:
        return EWTResult(
            status=EWTStatus.UNTRUSTED_TIMESTAMPS,
            ewt_s=None,
            reason="event-time domain is missing, untrusted or unsynchronised",
            provenance=provenance,
        )
    if not warning_present:
        return EWTResult(
            status=EWTStatus.MISSING_WARNING,
            ewt_s=None,
            reason=(
                "no valid predictive warning occurred: missed-warning "
                "accounting, never EWT = 0"
            ),
            provenance=provenance,
        )
    if not warning_persistent:
        return EWTResult(
            status=EWTStatus.MISSING_WARNING,
            ewt_s=None,
            reason=(
                "a warning existed but did not satisfy the frozen persistence "
                "semantics; it is not a valid first persistent warning"
            ),
            provenance=provenance,
        )
    if not reactive_crossing_observed or t_reactive_s is None:
        return EWTResult(
            status=EWTStatus.MISSING_REACTIVE_CROSSING,
            ewt_s=None,
            reason=(
                "the reactive criterion crossing was not observed; the "
                "observation is censored and no crossing time is invented"
            ),
            provenance=provenance,
        )
    if t_predictive_s is None:
        raise EvaluationContractError(
            "warning_present=true requires a numeric t_predictive_s"
        )
    t_predictive = _finite(t_predictive_s, "t_predictive_s")
    t_reactive = _finite(t_reactive_s, "t_reactive_s")
    return EWTResult(
        status=EWTStatus.ESTIMABLE,
        ewt_s=t_reactive - t_predictive,
        reason=(
            "EWT = t_reactive - t_predictive; a negative value is a late "
            "warning and is reported, not discarded"
        ),
        provenance=provenance,
    )


class AIWStatus(str, Enum):
    ESTIMABLE = "ESTIMABLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True)
class LatencyComponent:
    """One measured timing span in the AIW chain.

    ``measured=False`` means the value is missing or unqualified. It is
    preserved as a first-class state so no nominal fallback can be substituted.
    """

    name: str
    owner: str
    start_s: float
    end_s: float
    clock_domain: str
    measurement_method: str
    measured: bool = True
    uncertainty_s: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise EvaluationContractError("latency component requires a name")
        if not self.owner.strip():
            raise EvaluationContractError(
                f"latency component {self.name!r} requires an owner"
            )
        if not self.clock_domain.strip():
            raise EvaluationContractError(
                f"latency component {self.name!r} requires a clock domain"
            )
        if not self.measurement_method.strip():
            raise EvaluationContractError(
                f"latency component {self.name!r} requires a measurement method"
            )
        start = _finite(self.start_s, f"{self.name}.start_s")
        end = _finite(self.end_s, f"{self.name}.end_s")
        if end < start:
            raise EvaluationContractError(
                f"latency component {self.name!r} ends before it starts"
            )
        if self.measured and self.uncertainty_s is None:
            raise EvaluationContractError(
                f"latency component {self.name!r} is measured but carries no "
                "uncertainty_s; 0.0 is a valid measured uncertainty"
            )
        if self.uncertainty_s is not None:
            uncertainty = _finite(
                self.uncertainty_s, f"{self.name}.uncertainty_s"
            )
            if uncertainty < 0:
                raise EvaluationContractError(
                    f"latency component {self.name!r} has a negative uncertainty"
                )

    @property
    def duration_s(self) -> float:
        return float(self.end_s) - float(self.start_s)


@dataclass(frozen=True)
class AIWResult:
    status: AIWStatus
    aiw_s: float | None
    reason: str
    t_system_s: float | None = None
    t_physical_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "aiw_s": self.aiw_s,
            "t_system_s": self.t_system_s,
            "t_physical_s": self.t_physical_s,
            "reason": self.reason,
        }


def _validate_chain(
    components: Iterable[LatencyComponent], *, chain_name: str
) -> tuple[LatencyComponent, ...]:
    materialized = tuple(components)
    names = [component.name for component in materialized]
    if len(set(names)) != len(names):
        raise EvaluationContractError(
            f"{chain_name} carries duplicate component names {names}"
        )
    ordered = sorted(materialized, key=lambda component: (component.start_s, component.end_s))
    for previous, current in zip(ordered, ordered[1:]):
        if current.start_s < previous.end_s:
            raise EvaluationContractError(
                f"{chain_name} components {previous.name!r} and "
                f"{current.name!r} overlap; overlapping intervals must not be "
                "counted twice"
            )
    return materialized


def _validate_disjoint_across_chains(
    system: tuple[LatencyComponent, ...],
    physical: tuple[LatencyComponent, ...],
) -> None:
    """Refuse T_system/T_physical spans that overlap on one shared timeline.

    Non-overlap is necessary but not sufficient for subtraction: W06
    alignment evidence still decides whether two spans describe the same
    event trajectory, which this W04 interface cannot prove.
    """
    combined = sorted(
        (*system, *physical),
        key=lambda component: (component.start_s, component.end_s, component.name),
    )
    for previous, current in zip(combined, combined[1:]):
        if current.start_s < previous.end_s:
            raise EvaluationContractError(
                f"T_system/T_physical components {previous.name!r} and "
                f"{current.name!r} overlap across chains; a shared-timeline "
                "decomposition must not count the same span twice"
            )


def compute_aiw(
    *,
    t_critical_s: float,
    t_warning_s: float,
    system_components: Iterable[LatencyComponent],
    physical_components: Iterable[LatencyComponent],
    reference_clock_domain: str,
) -> AIWResult:
    """Guard the AIW interface; not a W06 time-alignment implementation."""
    critical = _finite(t_critical_s, "t_critical_s")
    warning = _finite(t_warning_s, "t_warning_s")
    if not isinstance(reference_clock_domain, str) or not reference_clock_domain.strip():
        raise EvaluationContractError(
            "compute_aiw requires a non-empty reference_clock_domain for "
            "t_critical and t_warning"
        )
    system = _validate_chain(system_components, chain_name="T_system")
    physical = _validate_chain(physical_components, chain_name="T_physical")
    unmeasured = [
        component.name
        for component in (*system, *physical)
        if not component.measured
    ]
    if unmeasured:
        return AIWResult(
            status=AIWStatus.NOT_ESTIMABLE,
            aiw_s=None,
            reason=(
                "measured input missing/untrusted: "
                + ", ".join(sorted(unmeasured))
                + "; no nominal latency is substituted"
            ),
        )
    if not system or not physical:
        return AIWResult(
            status=AIWStatus.NOT_ESTIMABLE,
            aiw_s=None,
            reason=(
                "T_system and T_physical must both be measured component "
                "chains; an empty chain is not zero"
            ),
        )
    mixed_domains = sorted(
        {
            component.clock_domain
            for component in (*system, *physical)
            if component.clock_domain != reference_clock_domain
        }
    )
    if mixed_domains:
        return AIWResult(
            status=AIWStatus.NOT_ESTIMABLE,
            aiw_s=None,
            reason=(
                "mixed clock domains "
                f"{mixed_domains} versus reference {reference_clock_domain!r}; "
                "W06 alignment evidence is required before subtracting them"
            ),
        )
    _validate_disjoint_across_chains(system, physical)
    t_system = sum(component.duration_s for component in system)
    t_physical = sum(component.duration_s for component in physical)
    return AIWResult(
        status=AIWStatus.ESTIMABLE,
        aiw_s=critical - warning - t_system - t_physical,
        t_system_s=t_system,
        t_physical_s=t_physical,
        reason=(
            "AIW = t_critical - t_warning - T_system - T_physical over measured "
            "components that do not overlap on the shared clock domain; "
            "non-overlap alone does not prove event-level alignment, so "
            "cross-chain subtraction still requires W06 evidence. A positive "
            "value is actionable only under the component provenance recorded "
            "by A/C/D"
        ),
    )


@dataclass(frozen=True)
class InterventionEvidence:
    """The verification chain; ACK is not physical effect (Doc ``02`` §32.2)."""

    command_published: bool
    device_ack: bool
    electrical_response_measured: bool
    thermal_response_measured: bool

    @property
    def verified(self) -> bool:
        return self.electrical_response_measured and self.thermal_response_measured

    def require_verified(self) -> None:
        if not self.verified:
            missing: list[str] = []
            if not self.electrical_response_measured:
                missing.append("electrical response")
            if not self.thermal_response_measured:
                missing.append("thermal response")
            raise EvaluationContractError(
                "intervention is not physically verified; missing: "
                + ", ".join(missing)
                + " (a publish acknowledgement or device ACK is not physical "
                "effect)"
            )


PRIMARY_PREDICTIVE_METRIC = "non_interpolated_average_precision"
PRIMARY_PHYSICAL_OUTCOME = "thermal_exposure"
SECONDARY_PHYSICAL_OUTCOMES: tuple[str, ...] = (
    "recovery_time",
    "peak_temperature",
    "time_above_critical",
    "time_above_target",
    "branch_energy",
    "critical_excursion_count",
    "false_warning_burden",
)
DIAGNOSTIC_PHYSICAL_OUTCOMES: tuple[str, ...] = (
    "cooling_health_state",
    "spatial_gradient",
    "feature_importance",
)
PREDICTIVE_SECONDARY_METRICS: tuple[str, ...] = (
    "precision_at_frozen_operating_point",
    "recall_at_frozen_operating_point",
    "false_warning_episodes_per_run",
    "false_warning_episodes_per_hour",
    "missed_event_rate",
    "ewt_distribution",
    "roc_auc",
    "warning_duration",
    "repeated_alert_count",
)
TRAPEZOIDAL_PR_AUC_ALIASES = frozenset(
    {"trapezoidal_pr_auc", "pr_auc", "area_under_pr_curve", "average_precision_trapezoidal"}
)
LOWER_IS_BETTER_OUTCOMES = frozenset(
    {
        "thermal_exposure",
        "recovery_time",
        "peak_temperature",
        "time_above_critical",
        "time_above_target",
        "branch_energy",
        "critical_excursion_count",
        "false_warning_burden",
    }
)


@dataclass(frozen=True)
class Amendment:
    """A recorded, disclosed hierarchy change; never a silent substitution."""

    amendment_id: str
    reason: str
    disclosed_exploratory: bool = True

    def __post_init__(self) -> None:
        if not self.amendment_id.strip():
            raise MetricHierarchyError("an amendment requires a non-empty id")
        if not self.reason.strip():
            raise MetricHierarchyError("an amendment requires a stated reason")
        if self.disclosed_exploratory is not True:
            raise MetricHierarchyError(
                "a hierarchy amendment must be disclosed as exploratory; an "
                "undisclosed promotion is not a lawful amendment"
            )


@dataclass(frozen=True)
class MetricHierarchy:
    """Frozen W04 outcome hierarchy with an explicit amendment path."""

    primary_predictive: str = PRIMARY_PREDICTIVE_METRIC
    primary_physical: str = PRIMARY_PHYSICAL_OUTCOME
    secondary_physical: tuple[str, ...] = SECONDARY_PHYSICAL_OUTCOMES
    diagnostic_physical: tuple[str, ...] = DIAGNOSTIC_PHYSICAL_OUTCOMES
    amendment: Amendment | None = None

    def __post_init__(self) -> None:
        if self.primary_predictive != PRIMARY_PREDICTIVE_METRIC:
            if self.amendment is None:
                raise MetricHierarchyError(
                    f"custom primary predictive metric "
                    f"{self.primary_predictive!r} requires a recorded amendment"
                )
            if self.primary_predictive not in PREDICTIVE_SECONDARY_METRICS:
                raise MetricHierarchyError(
                    f"custom primary predictive metric "
                    f"{self.primary_predictive!r} is not in the frozen "
                    "predictive hierarchy"
                )
        if self.primary_physical != PRIMARY_PHYSICAL_OUTCOME:
            if self.amendment is None:
                raise MetricHierarchyError(
                    f"custom primary physical outcome "
                    f"{self.primary_physical!r} requires a recorded amendment"
                )
            if self.primary_physical not in SECONDARY_PHYSICAL_OUTCOMES:
                raise MetricHierarchyError(
                    f"custom primary physical outcome "
                    f"{self.primary_physical!r} is not a frozen secondary "
                    "outcome"
                )

    def assert_primary_predictive(self, metric_name: str) -> None:
        if metric_name in TRAPEZOIDAL_PR_AUC_ALIASES:
            raise MetricHierarchyError(
                f"{metric_name!r} is a trapezoidal PR-AUC summary, not the "
                "frozen non-interpolated Average Precision; they are not "
                "interchangeable"
            )
        if metric_name == self.primary_predictive:
            return
        if metric_name in PREDICTIVE_SECONDARY_METRICS:
            if self.amendment is None:
                raise MetricHierarchyError(
                    f"{metric_name!r} is a secondary predictive metric; making "
                    "it primary after outcome inspection requires a recorded "
                    "amendment"
                )
            return
        raise MetricHierarchyError(
            f"{metric_name!r} is not in the frozen predictive hierarchy"
        )

    def assert_primary_physical(self, outcome_name: str) -> None:
        if outcome_name == self.primary_physical:
            return
        if outcome_name in self.secondary_physical:
            if self.amendment is None:
                raise MetricHierarchyError(
                    f"{outcome_name!r} is a secondary physical outcome; "
                    "promoting it after outcome inspection requires a recorded "
                    "amendment and is reported as exploratory"
                )
            return
        if outcome_name in self.diagnostic_physical:
            raise MetricHierarchyError(
                f"{outcome_name!r} is a diagnostic outcome; a diagnostic never "
                "becomes a primary physical outcome by substitution"
            )
        raise MetricHierarchyError(
            f"{outcome_name!r} is not in the frozen physical outcome family"
        )


def paired_improvement(
    y_a: float, y_b: float, *, outcome_name: str
) -> float:
    """Frozen sign convention ``I_i = Y_A - Y_B`` for lower-is-better outcomes."""
    if outcome_name not in LOWER_IS_BETTER_OUTCOMES:
        raise MetricHierarchyError(
            f"{outcome_name!r} is not a lower-is-better outcome; the frozen "
            "I_i = Y_A - Y_B reading applies only to that orientation"
        )
    return _finite(y_a, "Y_A") - _finite(y_b, "Y_B")


_LOCKED_PARTITION_NAMES = frozenset(
    {
        "test",
        "tests",
        "test_set",
        "testset",
        "locked",
        "locked_test",
        "lockedtest",
        "holdout",
        "hold_out",
        "holdout_set",
    }
)


def assert_allowed_for_selection(partition: str) -> None:
    """Locked holdout data never participates in fitting or selection."""
    normalized = (
        partition.strip().lower().replace("-", "_").replace(" ", "_")
    )
    if normalized in _LOCKED_PARTITION_NAMES:
        raise MetricHierarchyError(
            f"partition {partition!r} is locked; selection, fitting, "
            "calibration and threshold tuning are forbidden there"
        )
