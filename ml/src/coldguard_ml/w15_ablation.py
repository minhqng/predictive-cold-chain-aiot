"""W15 A3 electrical/applied-state ablation and electrical observability audit.

The canonical A3 contrast (Doc 03 §63, Doc 04 W15, Doc 05B §43) is:

    A3a: thermal/context
    A3b: the same thermal/context + electrical/applied-state features

W15 adds only a versioned read-only view layer over the frozen W10 registry and
reuses the W14 ablation machinery and W11 grouped benchmark.  The A3b arm is
exactly the W11 28-feature allowlist; A3a is that allowlist with exactly the
eight pre-existing electrical/actuation model inputs removed.  No feature is
invented, no registry entry is mutated, and `requested_cooling` /
`readback_cooling` stay out of both arms because they were never W11 model
inputs.

Every number derived from this module is a synthetic software control
(``SYNTHETIC_SOFTWARE_CONTROL_ONLY``), never physical evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .feature_pipeline import PipelineSample, Trajectory
from .feature_registry import FeatureRegistry
from .w14_ablation import (
    AblationComparabilityError,
    AblationFeature,
    AblationView,
    AblationViewError,
    compute_view_rows,
)

W15_LAYER_VERSION = "coldguard-w15-electrical-ablation-v1"
W15_VIEW_SCHEMA = "coldguard-w15-a3-view-v1"
SYNTHETIC_SOFTWARE_CONTROL = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
REFERENCE_HORIZON_STATUS = "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN"

A3A_ARM_ID = "A3A"
A3B_ARM_ID = "A3B"
A3A_VIEW_ID = "coldguard-w15-a3a-thermal-context-v1"
A3B_VIEW_ID = "coldguard-w15-a3b-thermal-context-electrical-v1"

# Exactly the eight electrical/actuation features that W11 already admitted to
# the 28-feature model allowlist.  Order follows the frozen config allowlist.
A3_ELECTRICAL_FEATURES = (
    "applied_cooling",
    "applied_duty",
    "time_since_confirmed_applied_change",
    "cooling_voltage_v",
    "cooling_current_a",
    "cooling_power_w",
    "energy_counter_wh",
    "past_integrated_cooling_energy_wh",
)
A3_ACTUATION_FEATURES = A3_ELECTRICAL_FEATURES[:3]
A3_PZEM_FEATURES = A3_ELECTRICAL_FEATURES[3:]
A3A_EXPECTED_FEATURE_COUNT = 20
A3B_EXPECTED_FEATURE_COUNT = 28

# Registry candidates deliberately not admitted to A3.
_A3_EXCLUDED_CANDIDATES = (
    (
        "requested_cooling",
        "controller request is not proof of applied action and was not a W11 model input",
    ),
    (
        "readback_cooling",
        "readback is not a verified electrical/thermal response and was not a W11 model input",
    ),
    (
        "T_tec_hot_side_c",
        "TEC hot side is a diagnostic observation, not chamber air",
    ),
)

_CONTROLLED_THERMAL_FAMILIES = ("instantaneous_thermal", "rolling_thermal")
_CONTROLLED_CONTEXT_FAMILIES = (
    "door_context",
    "environmental_context",
)
_ELECTRICAL_FAMILIES = ("actuation_context", "electrical_context")

# Per-feature audit annotations.  Registry text supplies the frozen physical
# meaning, quality requirement and missingness; these annotations record the
# W15 leakage/shortcut assessment that the registry intentionally does not make.
_ELECTRICAL_AUDIT: Mapping[str, Mapping[str, str]] = {
    "applied_cooling": {
        "origin": "POWER_PATH controller applied state as present in the telemetry row",
        "shortcut_risk": (
            "CONTROLLER_ACTION_PROXY: the controller may already have reacted to the "
            "same thermal excursion; a classifier can recognize an intervention "
            "instead of predicting the event"
        ),
        "intended_role": "predictive input candidate and applied-state observability",
        "verified_actuation": "NO: an applied command is not proof that current flowed",
    },
    "applied_duty": {
        "origin": "POWER_PATH controller applied duty as present in the telemetry row",
        "shortcut_risk": (
            "CONTROLLER_ACTION_PROXY: duty is chosen by the controller/policy and may "
            "encode the intervention policy rather than plant state"
        ),
        "intended_role": "predictive input candidate and applied-state observability",
        "verified_actuation": "NO: duty is an applied setting, not a measured response",
    },
    "time_since_confirmed_applied_change": {
        "origin": "past-only elapsed time since the last observed applied (state, duty) change",
        "shortcut_risk": (
            "CONTROLLER_ACTION_PROXY: a recent transition is a controller event; the "
            "feature is causal at t but not a plant-state measurement"
        ),
        "intended_role": "predictive input candidate and intervention-recency diagnostic",
        "verified_actuation": "NO: an observed transition is not verified cooling",
    },
    "cooling_voltage_v": {
        "origin": "PZEM-017 cooling-branch voltage (branch observation, not whole-device power)",
        "shortcut_risk": (
            "DOWNSTREAM_RESPONSE: voltage is a branch response that may follow the "
            "controller action rather than precede the thermal event"
        ),
        "intended_role": "electrical response observability and predictive candidate",
        "verified_actuation": (
            "NO: electrical observation only; voltage does not verify actuation or "
            "thermal response"
        ),
    },
    "cooling_current_a": {
        "origin": "PZEM-017 cooling-branch current through the branch shunt",
        "shortcut_risk": (
            "DOWNSTREAM_RESPONSE: current is a response to the applied command; it is "
            "not proof of successful thermal cooling"
        ),
        "intended_role": "electrical response observability and predictive candidate",
        "verified_actuation": (
            "NO: electrical observation only; current is not proof of thermal cooling"
        ),
    },
    "cooling_power_w": {
        "origin": "PZEM-017 cooling-branch power (voltage x current x meter convention)",
        "shortcut_risk": (
            "DOWNSTREAM_RESPONSE + PWM_SAMPLING: sampled power on a PWM branch is a "
            "meter-dependent observation; branch power is not whole-system energy"
        ),
        "intended_role": "electrical response observability and predictive candidate",
        "verified_actuation": (
            "NO: electrical observation only; power is not proof of thermal response"
        ),
    },
    "energy_counter_wh": {
        "origin": "PZEM-017 cooling-branch energy register value with reset refusal",
        "shortcut_risk": (
            "RUN_AGE_OR_SCENARIO_IDENTIFIER: a cumulative counter grows with time and "
            "can act as a run-age/scenario shortcut; a reset or rollover must never be "
            "read as negative consumption"
        ),
        "intended_role": "diagnostic energy provenance; predictive candidate only with caution",
        "verified_actuation": "NO: an energy register is not a thermal-response proof",
    },
    "past_integrated_cooling_energy_wh": {
        "origin": "past-only left-rectangle integral of VALID cooling-branch power",
        "shortcut_risk": (
            "RUN_AGE_OR_SCENARIO_IDENTIFIER + DOWNSTREAM_RESPONSE: cumulative energy "
            "grows with elapsed run time and integrates the controller response"
        ),
        "intended_role": "diagnostic energy provenance; predictive candidate only with caution",
        "verified_actuation": "NO: integrated branch energy is not verified cooling",
    },
}


class A3ViewError(AblationViewError):
    """An A3 view would silently break the controlled electrical contrast."""


class A3ComparabilityError(AblationComparabilityError):
    """The A3 arms do not share the required controlled population."""


def _registry_feature(
    registry: FeatureRegistry, feature_id: str, *, transform: str
) -> AblationFeature:
    base = registry.feature(feature_id)
    return AblationFeature(
        feature_id=feature_id,
        base_feature_id=feature_id,
        family=base.family,
        source_roles=tuple(base.sensor_roles),
        transform=transform,
        time_domain=base.time_domain,
        lookback_s=base.lookback_s,
    )


def build_a3_views(
    registry: FeatureRegistry, config: Any
) -> Mapping[str, AblationView]:
    """Build A3a/A3b from the frozen allowlist without mutating the registry."""
    allowlist = tuple(config.feature_policy.allowlist)
    if len(allowlist) != A3B_EXPECTED_FEATURE_COUNT:
        raise A3ViewError(
            f"W11 allowlist has {len(allowlist)} features, expected "
            f"{A3B_EXPECTED_FEATURE_COUNT}; A3 must not invent a different contrast"
        )
    if tuple(feature for feature in allowlist if feature in A3_ELECTRICAL_FEATURES) != (
        A3_ELECTRICAL_FEATURES
    ):
        raise A3ViewError(
            "the declared electrical/actuation identities do not match the frozen allowlist"
        )
    a3b_features = tuple(
        _registry_feature(registry, feature_id, transform="FROZEN_REGISTRY")
        for feature_id in allowlist
    )
    electrical_set = set(A3_ELECTRICAL_FEATURES)
    a3a_features = tuple(
        feature
        for feature in a3b_features
        if feature.feature_id not in electrical_set
    )
    if len(a3a_features) != A3A_EXPECTED_FEATURE_COUNT:
        raise A3ViewError(
            f"A3a has {len(a3a_features)} features, expected "
            f"{A3A_EXPECTED_FEATURE_COUNT}"
        )
    excluded_from_a = tuple(
        (
            feature_id,
            "authorized electrical/actuation delta; present only in A3b",
        )
        for feature_id in A3_ELECTRICAL_FEATURES
    )
    views = {
        A3A_ARM_ID: AblationView(
            view_id=A3A_VIEW_ID,
            component="A3",
            arm_id=A3A_ARM_ID,
            description=(
                "Thermal/context arm: the 14 frozen chamber-air thermal features, "
                "the 4 authorized MC-38 door features, ambient temperature and "
                "relative humidity.  No electrical or applied-state input."
            ),
            features=a3a_features,
            excluded_features=excluded_from_a + _A3_EXCLUDED_CANDIDATES,
        ),
        A3B_ARM_ID: AblationView(
            view_id=A3B_VIEW_ID,
            component="A3",
            arm_id=A3B_ARM_ID,
            description=(
                "The identical A3a thermal/context set plus exactly the eight "
                "pre-existing W11 electrical/applied-state model inputs."
            ),
            features=a3b_features,
            excluded_features=_A3_EXCLUDED_CANDIDATES,
        ),
    }
    return views


def validate_a3_views(
    views: Mapping[str, AblationView], registry: FeatureRegistry, config: Any
) -> None:
    """Refuse any A3 contrast drift before outcomes are computed."""
    if set(views) != {A3A_ARM_ID, A3B_ARM_ID}:
        raise A3ViewError("A3 requires exactly the A3A and A3B arms")
    a3a, a3b = views[A3A_ARM_ID], views[A3B_ARM_ID]
    if a3a.component != "A3" or a3b.component != "A3":
        raise A3ViewError("A3 views are not bound to component A3")
    if a3b.feature_ids != tuple(config.feature_policy.allowlist):
        raise A3ViewError("A3b does not reproduce the frozen W11 allowlist")
    expected_a = tuple(
        feature_id
        for feature_id in a3b.feature_ids
        if feature_id not in set(A3_ELECTRICAL_FEATURES)
    )
    if a3a.feature_ids != expected_a:
        raise A3ViewError(
            "A3a is not exactly A3b minus the authorized electrical/actuation delta"
        )
    delta = tuple(
        feature.feature_id
        for feature in a3b.features
        if feature.feature_id not in set(a3a.feature_ids)
    )
    if delta != A3_ELECTRICAL_FEATURES:
        raise A3ViewError(f"A3 incremental set drift: {sorted(delta)}")
    for feature in a3b.features:
        try:
            base = registry.feature(feature.base_feature_id)
        except KeyError as exc:
            raise A3ViewError(
                f"feature {feature.feature_id!r} is absent from the frozen registry"
            ) from exc
        if feature.family != base.family:
            raise A3ViewError(
                f"feature {feature.feature_id!r} family drift: "
                f"{feature.family!r} != {base.family!r}"
            )
        if "TEC_HOT_SIDE" in feature.source_roles or feature.base_feature_id == (
            "T_tec_hot_side_c"
        ):
            raise A3ViewError("the diagnostic TEC hot side cannot enter A3")
    if any(
        feature.family in _ELECTRICAL_FAMILIES for feature in a3a.features
    ):
        raise A3ViewError("A3a contains an electrical or actuation feature")
    electrical_families = {
        feature.family
        for feature in a3b.features
        if feature.feature_id in set(A3_ELECTRICAL_FEATURES)
    }
    if electrical_families != set(_ELECTRICAL_FAMILIES):
        raise A3ViewError(
            f"A3 incremental families are {sorted(electrical_families)}, expected "
            f"{sorted(_ELECTRICAL_FAMILIES)}"
        )
    for family in _CONTROLLED_THERMAL_FAMILIES + _CONTROLLED_CONTEXT_FAMILIES:
        a_ids = tuple(
            feature.feature_id for feature in a3a.features if feature.family == family
        )
        b_ids = tuple(
            feature.feature_id for feature in a3b.features if feature.family == family
        )
        if a_ids != b_ids:
            raise A3ViewError(
                f"controlled context family {family!r} differs between A3 arms"
            )
    if any(
        feature.feature_id in {"requested_cooling", "readback_cooling"}
        for feature in a3b.features
    ):
        raise A3ViewError("unadmitted controller request/readback entered A3b")


# ---------------------------------------------------------------------------
# Electrical provenance and leakage audit
# ---------------------------------------------------------------------------


def electrical_provenance_rows(registry: FeatureRegistry) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature_id in A3_ELECTRICAL_FEATURES:
        base = registry.feature(feature_id)
        audit = _ELECTRICAL_AUDIT[feature_id]
        rows.append(
            {
                "feature_id": feature_id,
                "family": base.family,
                "sensor_role": ";".join(base.sensor_roles),
                "source_field": ";".join(base.source_fields),
                "physical_source_meaning": base.physical_meaning,
                "origin": audit["origin"],
                "quality_requirement": base.quality_requirements,
                "source_timestamp_domain": base.time_domain,
                "available_at_prediction_time": base.causal_availability_condition,
                "lookback_rule": base.lookback_rule,
                "missingness_behavior": base.missing_data_policy,
                "online_real_availability": (
                    "NOT_ESTABLISHED_FOR_PREDICTIVE_USE: zero predictive-eligible "
                    "real runs and no qualified real electrical development population"
                ),
                "leakage_or_shortcut_risk": audit["shortcut_risk"],
                "intended_role": audit["intended_role"],
                "verified_actuation": audit["verified_actuation"],
                "arm_membership": "A3B_ONLY",
            }
        )
    return rows


def _is_missing(value: Any) -> bool:
    return value is None or (
        isinstance(value, float) and math.isnan(value)
    )


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        average = (position + end) / 2.0 + 1.0
        for index in order[position : end + 1]:
            ranks[index] = average
        position = end + 1
    return ranks


def _spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    rank_x, rank_y = _ranks(xs), _ranks(ys)
    mean_x = sum(rank_x) / len(rank_x)
    mean_y = sum(rank_y) / len(rank_y)
    numerator = sum(
        (x - mean_x) * (y - mean_y) for x, y in zip(rank_x, rank_y)
    )
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x in rank_x)
        * sum((y - mean_y) ** 2 for y in rank_y)
    )
    if denominator == 0:
        return None
    return numerator / denominator


def _auc(labels: Sequence[int], values: Sequence[float]) -> float | None:
    from sklearn.metrics import roc_auc_score

    if len(set(labels)) < 2 or not values:
        return None
    return float(roc_auc_score(list(labels), list(values)))


def electrical_feature_diagnostics(
    dataset: Any,
    view: AblationView,
    *,
    scenario_by_run: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Diagnostic-only univariate audit; never a model-selection result."""
    rows: list[dict[str, Any]] = []
    samples = list(dataset.samples)
    for feature_id in A3_ELECTRICAL_FEATURES:
        index = view.feature_ids.index(feature_id)
        present = [
            (sample, float(sample.features[index]))
            for sample in samples
            if not _is_missing(sample.features[index])
        ]
        values = [value for _, value in present]
        row: dict[str, Any] = {
            "feature_id": feature_id,
            "evaluable_samples": len(samples),
            "present": len(present),
            "missing": len(samples) - len(present),
            "present_fraction": (
                len(present) / len(samples) if samples else None
            ),
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "mean": sum(values) / len(values) if values else None,
            "spearman_with_anchor_time": _spearman(
                [sample.anchor_t_s for sample, _ in present], values
            ),
            "scenario_auc": _auc(
                [
                    1 if scenario_by_run.get(sample.run_id) == "S2" else 0
                    for sample, _ in present
                ],
                values,
            ),
            "label_auc_diagnostic": _auc(
                [sample.y for sample, _ in present], values
            ),
            "monotonic_nondecreasing_within_runs": _within_run_nondecreasing(
                present
            ),
            "diagnostic_only": True,
        }
        rows.append(row)
    return rows


def _within_run_nondecreasing(
    present: Sequence[tuple[Any, float]]
) -> bool:
    by_run: dict[str, list[tuple[float, float]]] = {}
    for sample, value in present:
        by_run.setdefault(sample.run_id, []).append((sample.anchor_t_s, value))
    for series in by_run.values():
        series.sort()
        for (_, left), (_, right) in zip(series, series[1:]):
            if right < left:
                return False
    return True


def electrical_block_invariance(
    fixture: Any, registry: FeatureRegistry, view: AblationView
) -> dict[str, Any]:
    """Check whether the fixture's electrical block varies across runs at all.

    A run-invariant electrical block cannot encode scenario or controller-action
    identity in this synthetic fixture.  This is a fixture property, not a
    property of a real PZEM installation.
    """
    per_run: dict[str, dict[float, tuple[Any, ...]]] = {}
    indices = [view.feature_ids.index(feature_id) for feature_id in A3_ELECTRICAL_FEATURES]
    for trajectory in fixture.development_trajectories:
        run_id = trajectory.run_id
        if run_id is None:
            raise A3ViewError("development trajectory has no run identity")
        partition = fixture.split.partition_of(run_id)
        group_id = fixture.split.group_of.get(run_id)
        if partition is None or not group_id:
            raise A3ViewError(f"run {run_id!r} lacks split identity")
        rows = compute_view_rows(
            trajectory,
            registry,
            view,
            group_id=group_id,
            partition=partition,
        )
        per_run[run_id] = {
            row.anchor_t_s: tuple(row.values[index] for index in indices)
            for row in rows
        }
    run_ids = sorted(per_run)
    reference_run = run_ids[0]
    reference = per_run[reference_run]
    mismatches = 0
    anchors_compared = 0
    for run_id in run_ids[1:]:
        common = set(reference) & set(per_run[run_id])
        anchors_compared += len(common)
        for anchor in common:
            left, right = reference[anchor], per_run[run_id][anchor]
            if any(
                (a is None) != (b is None)
                or (a is not None and b is not None and a != b)
                for a, b in zip(left, right)
            ):
                mismatches += 1
    return {
        "runs_compared": len(run_ids),
        "anchors_compared": anchors_compared,
        "mismatch_count": mismatches,
        "electrical_block_run_invariant": mismatches == 0,
        "interpretation": (
            "fixture property only: the synthetic electrical block is identical "
            "across runs, so it cannot carry scenario/controller identity"
            if mismatches == 0
            else "electrical block varies across runs; inspect for run/scenario identity"
        ),
    }


# ---------------------------------------------------------------------------
# Causal / adversarial probes
# ---------------------------------------------------------------------------


def _mutate_samples(
    trajectory: Trajectory, transform: Any
) -> Trajectory:
    return Trajectory(
        **{
            **trajectory.__dict__,
            "samples": tuple(
                transform(index, sample)
                for index, sample in enumerate(trajectory.samples)
            ),
        }
    )


def _future_mutation(index: int, anchor_index: int, sample: PipelineSample) -> PipelineSample:
    if index <= anchor_index:
        return sample
    return PipelineSample(
        **{
            **sample.__dict__,
            "applied_cooling": "OFF" if sample.applied_cooling == "ON" else "ON",
            "applied_duty": 0.0 if sample.applied_duty else 1.0,
            "cooling_voltage_v": 999.0,
            "cooling_current_a": 999.0,
            "cooling_power_w": 9999.0,
            "cooling_energy_counter_wh": 0.0,
            "electrical_quality": "INVALID",
        }
    )


def future_isolation_probe(
    trajectory: Trajectory,
    registry: FeatureRegistry,
    view: AblationView,
    *,
    group_id: str,
    partition: str,
    anchor_index: int,
) -> bool:
    """True when mutating every future sample leaves all anchors <= anchor unchanged."""
    if not 0 <= anchor_index < len(trajectory.samples) - 1:
        raise A3ViewError("future isolation probe needs a non-terminal anchor")
    baseline = compute_view_rows(
        trajectory, registry, view, group_id=group_id, partition=partition
    )
    mutated = compute_view_rows(
        _mutate_samples(
            trajectory,
            lambda index, sample: _future_mutation(index, anchor_index, sample),
        ),
        registry,
        view,
        group_id=group_id,
        partition=partition,
    )
    return all(
        left.values == right.values and left.missing_reasons == right.missing_reasons
        for left, right in zip(baseline[: anchor_index + 1], mutated[: anchor_index + 1])
    )


def transition_after_anchor_probe(
    trajectory: Trajectory,
    registry: FeatureRegistry,
    view: AblationView,
    *,
    group_id: str,
    partition: str,
    anchor_index: int,
) -> bool:
    """True when an applied-state/duty transition after the anchor never moves it."""
    if not 0 <= anchor_index < len(trajectory.samples) - 1:
        raise A3ViewError("transition probe needs a non-terminal anchor")

    def transform(index: int, sample: PipelineSample) -> PipelineSample:
        if index <= anchor_index:
            return sample
        return PipelineSample(
            **{
                **sample.__dict__,
                "applied_cooling": "OFF" if sample.applied_cooling == "ON" else "ON",
                "applied_duty": 0.0 if sample.applied_duty else 1.0,
            }
        )

    baseline = compute_view_rows(
        trajectory, registry, view, group_id=group_id, partition=partition
    )
    mutated = compute_view_rows(
        _mutate_samples(trajectory, transform),
        registry,
        view,
        group_id=group_id,
        partition=partition,
    )
    return all(
        left.values == right.values and left.missing_reasons == right.missing_reasons
        for left, right in zip(baseline[: anchor_index + 1], mutated[: anchor_index + 1])
    )


def unknown_electrical_probe(
    trajectory: Trajectory,
    registry: FeatureRegistry,
    view: AblationView,
    *,
    group_id: str,
    partition: str,
    start_index: int,
) -> dict[str, Any]:
    """UNKNOWN electrical quality must stay missing, never zero or VALID."""

    def transform(index: int, sample: PipelineSample) -> PipelineSample:
        if index < start_index:
            return sample
        return PipelineSample(**{**sample.__dict__, "electrical_quality": "UNKNOWN"})

    rows = compute_view_rows(
        _mutate_samples(trajectory, transform),
        registry,
        view,
        group_id=group_id,
        partition=partition,
    )
    pzem_indices = [view.feature_ids.index(feature_id) for feature_id in A3_PZEM_FEATURES]
    applied_indices = [
        view.feature_ids.index(feature_id) for feature_id in A3_ACTUATION_FEATURES
    ]
    future_rows = rows[start_index:]
    pzem_missing = all(
        row.values[index] is None
        and row.missing_reasons[index]
        in ("MISSING_ELECTRICAL_UNQUALIFIED", "MISSING_INPUT")
        for row in future_rows
        for index in pzem_indices
    )
    applied_present = all(
        row.values[index] is not None for row in future_rows for index in applied_indices
    )
    return {
        "pzem_features_missing_after_unknown": pzem_missing,
        "pzem_never_zero_or_valid": all(
            row.values[index] is None for row in future_rows for index in pzem_indices
        ),
        "applied_state_still_observed": applied_present,
        "anchors_checked": len(future_rows),
    }


def counter_reset_probe(
    trajectory: Trajectory,
    registry: FeatureRegistry,
    view: AblationView,
    *,
    group_id: str,
    partition: str,
    reset_anchor_s: float,
) -> dict[str, Any]:
    """A counter reset must be reported as missing, never negative consumption."""
    rows = compute_view_rows(
        trajectory, registry, view, group_id=group_id, partition=partition
    )
    counter_index = view.feature_ids.index("energy_counter_wh")
    before = [row for row in rows if row.anchor_t_s < reset_anchor_s]
    after = [row for row in rows if row.anchor_t_s >= reset_anchor_s]
    values = [row.values[counter_index] for row in rows]
    numeric = [value for value in values if value is not None]
    return {
        "counter_present_before_reset": all(
            row.values[counter_index] is not None for row in before
        ),
        "counter_missing_after_reset": all(
            row.values[counter_index] is None for row in after
        ),
        "reset_reason_recorded": all(
            row.missing_reasons[counter_index] == "MISSING_COUNTER_RESET"
            for row in after
        ),
        "no_negative_counter_value": all(value >= 0 for value in numeric),
    }


# ---------------------------------------------------------------------------
# Diagnosis interface: applied state versus electrical response
# ---------------------------------------------------------------------------

RESPONSE_APPLIED_UNKNOWN = "APPLIED_STATE_UNKNOWN"
RESPONSE_UNVERIFIABLE = "RESPONSE_UNVERIFIABLE"
RESPONSE_NO_COMMAND = "NO_APPLIED_COMMAND"
RESPONSE_APPLIED_WITH_RESPONSE = "APPLIED_WITH_ELECTRICAL_RESPONSE"
RESPONSE_APPLIED_WITHOUT_RESPONSE = "APPLIED_WITHOUT_ELECTRICAL_RESPONSE"
RESPONSE_WITHOUT_COMMAND = "ELECTRICAL_RESPONSE_WITHOUT_APPLIED_COMMAND"


@dataclass(frozen=True)
class ActuatorResponseAssessment:
    state: str
    reason: str

    @property
    def verifiable(self) -> bool:
        return self.state in (
            RESPONSE_NO_COMMAND,
            RESPONSE_APPLIED_WITH_RESPONSE,
            RESPONSE_APPLIED_WITHOUT_RESPONSE,
            RESPONSE_WITHOUT_COMMAND,
        )


def assess_actuator_electrical_response(
    *,
    applied_cooling: str | None,
    electrical_quality: str,
    cooling_power_w: float | None,
) -> ActuatorResponseAssessment:
    """Contract-level consistency check; not a validated fault detector.

    A command is not proof that current flowed; a current reading is not proof
    of thermal cooling.  This function only classifies the observed applied
    state against a trustworthy branch-power observation.
    """
    if applied_cooling not in ("ON", "OFF"):
        return ActuatorResponseAssessment(
            RESPONSE_APPLIED_UNKNOWN, "applied actuator state is missing/unrecognised"
        )
    if electrical_quality != "VALID" or cooling_power_w is None:
        return ActuatorResponseAssessment(
            RESPONSE_UNVERIFIABLE, "no trustworthy PZEM branch-power observation"
        )
    if not math.isfinite(cooling_power_w) or cooling_power_w < 0:
        return ActuatorResponseAssessment(
            RESPONSE_UNVERIFIABLE, "branch power is not a finite non-negative value"
        )
    if applied_cooling == "ON":
        if cooling_power_w > 0:
            return ActuatorResponseAssessment(
                RESPONSE_APPLIED_WITH_RESPONSE,
                "applied ON with a trustworthy positive branch-power observation",
            )
        return ActuatorResponseAssessment(
            RESPONSE_APPLIED_WITHOUT_RESPONSE,
            "applied ON but branch power is exactly zero; verify meter and actuation",
        )
    if cooling_power_w == 0:
        return ActuatorResponseAssessment(
            RESPONSE_NO_COMMAND, "applied OFF with zero trustworthy branch power"
        )
    return ActuatorResponseAssessment(
        RESPONSE_WITHOUT_COMMAND,
        "applied OFF but branch power is positive; inspect policy and wiring",
    )


def shortcut_risk_class(feature_id: str) -> str:
    if feature_id in A3_ACTUATION_FEATURES:
        return "CONTROLLER_ACTION_PROXY"
    if feature_id in ("energy_counter_wh", "past_integrated_cooling_energy_wh"):
        return "RUN_AGE_OR_SCENARIO_IDENTIFIER"
    return "DOWNSTREAM_ELECTRICAL_RESPONSE"
