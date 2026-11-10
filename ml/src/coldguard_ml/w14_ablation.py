"""W14 role-correct A1/A2 ablation views (B-W14-01 / B-W14-02).

The frozen W10 registry (``feature-registry-v1.yaml``) is never mutated here.
W14 adds versioned, read-only ablation views:

* ``A1A`` applies the frozen rolling formulas to ``CHAMBER_CENTER`` only and
  records new feature ids, so a single-sensor column can never masquerade as a
  multi-probe aggregate;
* ``A1B`` is exactly the W11 28-feature chamber-air allowlist;
* ``A2A`` is the thermal-only family;
* ``A2B`` is the identical thermal set plus the four authorized MC-38 door
  features.

The observed rig maps T2 to ``TEC_HOT_SIDE``. The canonical Doc 03/05B example
``T1/T2/T3`` is an abstract three-temperature example, not authority to treat
the hot-side probe as chamber air. Every chamber-air aggregate here is built
from T1/T3/T4 (CHAMBER_CENTER, CHAMBER_BOTTOM, CHAMBER_NEAR_DOOR).
"""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .feature_pipeline import (
    PipelineSample,
    Trajectory,
    _compute_one,
    door_snapshots,
)
from .feature_registry import FeatureDefinition, FeatureRegistry
from .labels import LabelStatus, generate_label_records
from .xgb_benchmark import (
    BenchmarkConfig,
    BenchmarkFixture,
    BenchmarkResult,
    LabeledDataset,
    LabeledSample,
    run_grouped_benchmark,
)

W14_LAYER_VERSION = "coldguard-w14-role-correct-ablation-v1"
W14_VIEW_SCHEMA = "coldguard-w14-ablation-view-v1"
SYNTHETIC_SOFTWARE_CONTROL = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"

A1A_SINGLE_ROLE = "CHAMBER_CENTER"
A1A_RATIONALE = (
    "CHAMBER_CENTER (T1) is the only predeclared single chamber-air probe: it is "
    "the central chamber-air role in the frozen W10 role map, is not the "
    "door-adjacent probe, is not the bottom probe and is not the TEC hot side. "
    "The choice is fixed by role semantics before any W14 outcome is computed."
)

A1B_ROLES = ("CHAMBER_CENTER", "CHAMBER_BOTTOM", "CHAMBER_NEAR_DOOR")
A2_DOOR_FEATURES = (
    "door_open",
    "time_since_open",
    "duration_so_far",
    "count_past_60s",
)

_THERMAL_FAMILIES = ("instantaneous_thermal", "rolling_thermal")
_CONTEXT_FAMILIES = (
    "door_context",
    "actuation_context",
    "electrical_context",
    "environmental_context",
)

# Exactly the W11 non-thermal allowlist. requested_cooling and readback_cooling
# are registry candidates but were not model inputs in W11, so A1 must not
# introduce them while claiming to isolate sensor count.
W11_CONTEXT_FEATURES = (
    "door_open",
    "time_since_open",
    "duration_so_far",
    "count_past_60s",
    "applied_cooling",
    "applied_duty",
    "time_since_confirmed_applied_change",
    "cooling_voltage_v",
    "cooling_current_a",
    "cooling_power_w",
    "energy_counter_wh",
    "past_integrated_cooling_energy_wh",
    "ambient_temperature_c",
    "relative_humidity_pct",
)

_SINGLE_ROLE_ROLLING = (
    (
        "A1A_single_center_rolling_mean_temperature_60s",
        "rolling_mean_temperature_60s",
    ),
    (
        "A1A_single_center_rolling_std_temperature_60s",
        "rolling_std_temperature_60s",
    ),
    (
        "A1A_single_center_rolling_min_temperature_60s",
        "rolling_min_temperature_60s",
    ),
    (
        "A1A_single_center_rolling_max_temperature_60s",
        "rolling_max_temperature_60s",
    ),
    (
        "A1A_single_center_past_only_slope_c_per_min_60s",
        "past_only_slope_c_per_min_60s",
    ),
    (
        "A1A_single_center_past_only_temperature_delta_60s",
        "past_only_temperature_delta_60s",
    ),
)


class AblationViewError(ValueError):
    """A view would silently change role provenance or comparison support."""


class AblationComparabilityError(AblationViewError):
    """Two arms do not share labels, groups or the evaluable population."""


@dataclass(frozen=True)
class AblationFeature:
    feature_id: str
    base_feature_id: str
    family: str
    source_roles: tuple[str, ...]
    transform: str
    time_domain: str
    lookback_s: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "base_feature_id": self.base_feature_id,
            "family": self.family,
            "source_roles": list(self.source_roles),
            "transform": self.transform,
            "time_domain": self.time_domain,
            "lookback_s": self.lookback_s,
        }


@dataclass(frozen=True)
class AblationView:
    view_id: str
    component: str
    arm_id: str
    description: str
    features: tuple[AblationFeature, ...]
    excluded_features: tuple[tuple[str, str], ...]
    scientific_class: str = SYNTHETIC_SOFTWARE_CONTROL

    @property
    def feature_ids(self) -> tuple[str, ...]:
        return tuple(feature.feature_id for feature in self.features)

    @property
    def base_feature_ids(self) -> tuple[str, ...]:
        return tuple(feature.base_feature_id for feature in self.features)

    @property
    def feature_count(self) -> int:
        return len(self.features)

    def feature(self, feature_id: str) -> AblationFeature:
        for feature in self.features:
            if feature.feature_id == feature_id:
                return feature
        raise KeyError(feature_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": W14_VIEW_SCHEMA,
            "layer_version": W14_LAYER_VERSION,
            "view_id": self.view_id,
            "component": self.component,
            "arm_id": self.arm_id,
            "description": self.description,
            "scientific_class": self.scientific_class,
            "feature_count": self.feature_count,
            "features": [feature.to_dict() for feature in self.features],
            "excluded_features": [
                {"feature_id": feature_id, "reason": reason}
                for feature_id, reason in self.excluded_features
            ],
        }


def _feature_from_registry(
    registry: FeatureRegistry,
    feature_id: str,
    *,
    source_roles: tuple[str, ...],
    transform: str,
) -> AblationFeature:
    base = registry.feature(feature_id)
    return AblationFeature(
        feature_id=feature_id,
        base_feature_id=feature_id,
        family=base.family,
        source_roles=source_roles,
        transform=transform,
        time_domain=base.time_domain,
        lookback_s=base.lookback_s,
    )


def _single_role_feature(
    registry: FeatureRegistry, feature_id: str, base_id: str
) -> AblationFeature:
    base = registry.feature(base_id)
    if base.family != "rolling_thermal":
        raise AblationViewError(f"{base_id!r} is not a rolling_thermal base feature")
    return AblationFeature(
        feature_id=feature_id,
        base_feature_id=base_id,
        family=base.family,
        source_roles=(A1A_SINGLE_ROLE,),
        transform="FROZEN_FORMULA_SINGLE_ROLE_APPLICATION",
        time_domain=base.time_domain,
        lookback_s=base.lookback_s,
    )


def _ordered_registry_features(
    registry: FeatureRegistry, families: Sequence[str]
) -> tuple[FeatureDefinition, ...]:
    return tuple(
        feature for feature in registry.features if feature.family in families
    )


def build_ablation_views(registry: FeatureRegistry) -> Mapping[str, AblationView]:
    thermal = _ordered_registry_features(registry, _THERMAL_FAMILIES)
    door = tuple(
        feature for feature in registry.features if feature.family == "door_context"
    )
    thermal_ids = tuple(feature.feature_id for feature in thermal)
    context_ids = W11_CONTEXT_FEATURES
    door_ids = tuple(feature.feature_id for feature in door)
    if set(door_ids) != set(A2_DOOR_FEATURES):
        raise AblationViewError(
            f"authorized door feature identities changed: {sorted(door_ids)}"
        )

    a1a_features: list[AblationFeature] = [
        _feature_from_registry(
            registry,
            "T_center_c",
            source_roles=(A1A_SINGLE_ROLE,),
            transform="FROZEN_REGISTRY_SINGLE_PROBE",
        )
    ]
    a1a_features.extend(
        _single_role_feature(registry, feature_id, base_id)
        for feature_id, base_id in _SINGLE_ROLE_ROLLING
    )
    a1a_features.extend(
        _feature_from_registry(
            registry,
            feature_id,
            source_roles=tuple(registry.feature(feature_id).sensor_roles),
            transform="FROZEN_REGISTRY_CONTEXT",
        )
        for feature_id in context_ids
    )
    a1b_features = [
        _feature_from_registry(
            registry,
            feature_id,
            source_roles=tuple(registry.feature(feature_id).sensor_roles),
            transform="FROZEN_REGISTRY",
        )
        for feature_id in thermal_ids + context_ids
    ]
    a2a_features = [
        _feature_from_registry(
            registry,
            feature_id,
            source_roles=tuple(registry.feature(feature_id).sensor_roles),
            transform="FROZEN_REGISTRY",
        )
        for feature_id in thermal_ids
    ]
    a2b_features = a2a_features + [
        _feature_from_registry(
            registry,
            feature_id,
            source_roles=tuple(registry.feature(feature_id).sensor_roles),
            transform="FROZEN_REGISTRY_CONTEXT",
        )
        for feature_id in A2_DOOR_FEATURES
    ]

    a1_excluded = (
        ("T_bottom_c", "other chamber-air probe; excluded from the single-probe arm"),
        ("T_near_door_c", "other chamber-air probe; excluded from the single-probe arm"),
        ("T_chamber_max_c", "multi-probe aggregate leaks other probes"),
        ("T_chamber_min_c", "multi-probe aggregate leaks other probes"),
        ("T_chamber_mean_c", "multi-probe aggregate leaks other probes"),
        ("T_chamber_spread_c", "multi-probe spatial statistic leaks other probes"),
        (
            "past_only_spatial_spread_60s",
            "multi-probe spatial statistic is undefined for one sensor",
        ),
        (
            "T_tec_hot_side_c",
            "TEC hot side is not chamber air and is excluded from both arms",
        ),
    )
    a2_excluded = tuple(
        (feature_id, "door context excluded from the thermal-only arm")
        for feature_id in door_ids
    ) + (
        (
            "T_tec_hot_side_c",
            "TEC hot side is not chamber air and is excluded from both arms",
        ),
        (
            "electrical/actuation/environment",
            "A3 owns electrical context; A2 controls it by excluding it from both arms",
        ),
    )

    views = {
        "A1A": AblationView(
            view_id="coldguard-w14-a1a-single-center-v1",
            component="A1",
            arm_id="A1A",
            description=(
                "One predeclared chamber-air probe (CHAMBER_CENTER) with the "
                "frozen thermal formulas applied to that probe only, plus the "
                "identical non-thermal context used in A1B."
            ),
            features=tuple(a1a_features),
            excluded_features=a1_excluded,
        ),
        "A1B": AblationView(
            view_id="coldguard-w14-a1b-three-chamber-air-v1",
            component="A1",
            arm_id="A1B",
            description=(
                "Three role-qualified chamber-air probes (T1/T3/T4) with the "
                "W11 28-feature allowlist. T2 TEC hot side is excluded."
            ),
            features=tuple(a1b_features),
            excluded_features=(
                (
                    "T_tec_hot_side_c",
                    "TEC hot side is not chamber air and is excluded from both arms",
                ),
            ),
        ),
        "A2A": AblationView(
            view_id="coldguard-w14-a2a-thermal-v1",
            component="A2",
            arm_id="A2A",
            description="Thermal-only feature family; no door, electrical or actuation context.",
            features=tuple(a2a_features),
            excluded_features=a2_excluded,
        ),
        "A2B": AblationView(
            view_id="coldguard-w14-a2b-thermal-door-v1",
            component="A2",
            arm_id="A2B",
            description=(
                "The identical A2A thermal feature set plus the four authorized "
                "MC-38 door-context features."
            ),
            features=tuple(a2b_features),
            excluded_features=(
                (
                    "T_tec_hot_side_c",
                    "TEC hot side is not chamber air and is excluded from both arms",
                ),
                (
                    "electrical/actuation/environment",
                    "A3 owns electrical context; A2 controls it by excluding it from both arms",
                ),
            ),
        ),
    }
    return views


def validate_view(view: AblationView, registry: FeatureRegistry) -> None:
    """Refuse role-provenance drift before any computation."""
    if not view.features:
        raise AblationViewError(f"view {view.view_id!r} has no features")
    seen: set[str] = set()
    for feature in view.features:
        if feature.feature_id in seen:
            raise AblationViewError(f"duplicate feature id {feature.feature_id!r}")
        seen.add(feature.feature_id)
        try:
            base = registry.feature(feature.base_feature_id)
        except KeyError as exc:
            raise AblationViewError(
                f"base feature {feature.base_feature_id!r} is absent from the frozen registry"
            ) from exc
        if feature.family != base.family:
            raise AblationViewError(
                f"feature {feature.feature_id!r} family drift: "
                f"{feature.family!r} != {base.family!r}"
            )
        if "TEC_HOT_SIDE" in feature.source_roles:
            raise AblationViewError(
                f"feature {feature.feature_id!r} binds the TEC hot side as chamber air"
            )
        if feature.base_feature_id == "T_tec_hot_side_c":
            raise AblationViewError("the diagnostic hot-side feature cannot enter W14 X")
    if view.arm_id == "A1A":
        for feature in view.features:
            if feature.family in _THERMAL_FAMILIES and feature.source_roles != (
                A1A_SINGLE_ROLE,
            ):
                raise AblationViewError(
                    f"A1A thermal feature {feature.feature_id!r} binds "
                    f"{feature.source_roles}; only {A1A_SINGLE_ROLE} is permitted"
                )
        if "T_center_c" not in view.feature_ids:
            raise AblationViewError("A1A does not carry the declared center probe")
        if view.feature("T_center_c").source_roles != (A1A_SINGLE_ROLE,):
            raise AblationViewError("A1A does not bind the declared center probe")
    if view.arm_id == "A2A":
        if any(feature.family == "door_context" for feature in view.features):
            raise AblationViewError("A2A thermal-only view contains a door feature")
        if any(feature.family in _CONTEXT_FAMILIES for feature in view.features):
            raise AblationViewError("A2A contains non-thermal context")
    if view.arm_id == "A2B":
        door_ids = tuple(
            feature.feature_id
            for feature in view.features
            if feature.family == "door_context"
        )
        if set(door_ids) != set(A2_DOOR_FEATURES):
            raise AblationViewError(
                f"A2B door features must be exactly {sorted(A2_DOOR_FEATURES)}"
            )
        if any(
            feature.family in ("electrical_context", "actuation_context")
            for feature in view.features
        ):
            raise AblationViewError("A2B must not contain electrical/actuation context")


def validate_arm_pair(view_a: AblationView, view_b: AblationView) -> None:
    if view_a.component != view_b.component:
        raise AblationViewError("paired arms belong to different components")
    if view_a.arm_id == view_b.arm_id:
        raise AblationViewError("paired arm identities are identical")
    if view_a.component == "A1":
        thermal_a = {
            feature.base_feature_id
            for feature in view_a.features
            if feature.family in _THERMAL_FAMILIES
        }
        thermal_b = {
            feature.base_feature_id
            for feature in view_b.features
            if feature.family in _THERMAL_FAMILIES
        }
        if thermal_a == thermal_b:
            raise AblationViewError("A1 arms do not differ in thermal sensing")
        context_a = tuple(
            feature.feature_id
            for feature in view_a.features
            if feature.family in _CONTEXT_FAMILIES
        )
        context_b = tuple(
            feature.feature_id
            for feature in view_b.features
            if feature.family in _CONTEXT_FAMILIES
        )
        if context_a != context_b:
            raise AblationViewError(
                "A1 arms vary uncontrolled non-thermal context instead of sensor count"
            )
    if view_a.component == "A2":
        thermal_a = tuple(
            feature.feature_id
            for feature in view_a.features
            if feature.family in _THERMAL_FAMILIES
        )
        thermal_b = tuple(
            feature.feature_id
            for feature in view_b.features
            if feature.family in _THERMAL_FAMILIES
        )
        if thermal_a != thermal_b:
            raise AblationViewError("A2 arms do not share an identical thermal set")
        if any(feature.family == "door_context" for feature in view_a.features):
            raise AblationViewError("A2A must not contain door context")


@dataclass(frozen=True)
class AblationRow:
    run_id: str
    group_id: str
    partition: str
    source_sha256: str
    sample_identity: str
    anchor_t_s: float
    values: tuple[float | int | None, ...]
    missing_reasons: tuple[str, ...]

    def to_dict(self, feature_ids: Sequence[str]) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "group_id": self.group_id,
            "partition": self.partition,
            "source_sha256": self.source_sha256,
            "sample_identity": self.sample_identity,
            "anchor_t_s": self.anchor_t_s,
            "features": dict(zip(feature_ids, self.values)),
            "missing_reasons": dict(zip(feature_ids, self.missing_reasons)),
        }


def compute_view_rows(
    trajectory: Trajectory,
    registry: FeatureRegistry,
    view: AblationView,
    *,
    group_id: str,
    partition: str,
) -> tuple[AblationRow, ...]:
    """Compute a view at every observed anchor, past-only and label-free."""
    validate_view(view, registry)
    samples = trajectory.samples
    snapshots = door_snapshots(samples)
    rows: list[AblationRow] = []
    for index, sample in enumerate(samples):
        values: list[float | int | None] = []
        reasons: list[str] = []
        for feature in view.features:
            base = registry.feature(feature.base_feature_id)
            value, reason = _compute_one(
                base, samples, index, snapshots, feature.source_roles
            )
            if base.dtype == "int" and value is not None:
                value = int(value)
            values.append(value)
            reasons.append(reason)
        rows.append(
            AblationRow(
                run_id=trajectory.run_id or "",
                group_id=group_id,
                partition=partition,
                source_sha256=trajectory.source_sha256,
                sample_identity=sample.identity,
                anchor_t_s=sample.time_s,
                values=tuple(values),
                missing_reasons=tuple(reasons),
            )
        )
    return tuple(rows)


def _anchor_datetime(trajectory: Trajectory, anchor_t_s: float) -> _dt.datetime:
    if trajectory.origin_utc is None:
        raise AblationViewError(
            f"run {trajectory.run_id!r} has no absolute origin for labels"
        )
    origin = _dt.datetime.fromisoformat(trajectory.origin_utc.replace("Z", "+00:00"))
    return origin + _dt.timedelta(seconds=anchor_t_s)


def build_ablation_dataset(
    fixture: BenchmarkFixture,
    registry: FeatureRegistry,
    config: BenchmarkConfig,
    view: AblationView,
) -> LabeledDataset:
    """Attach the configured development labels to one view's feature matrix.

    Labels are generated independently of the view, so every arm sees exactly
    the same evaluable population. Missing feature values stay NaN and never
    change sample eligibility.
    """
    validate_view(view, registry)
    spec = config.label.spec()
    samples: list[LabeledSample] = []
    excluded_by_run: dict[str, dict[str, int]] = {}
    total_excluded: dict[str, int] = {}
    run_ids: list[str] = []
    for trajectory in fixture.development_trajectories:
        run_id = trajectory.run_id
        if run_id is None:
            raise AblationViewError("development trajectory has no run identity")
        partition = fixture.split.partition_of(run_id)
        if partition is None:
            raise AblationViewError(f"run {run_id!r} is not partitioned")
        group_id = fixture.split.group_of.get(run_id)
        if not group_id:
            raise AblationViewError(f"run {run_id!r} has no group identity")
        series = fixture.series_by_run.get(run_id)
        if series is None:
            raise AblationViewError(f"run {run_id!r} has no critical-event series")
        rows = compute_view_rows(
            trajectory,
            registry,
            view,
            group_id=group_id,
            partition=partition,
        )
        coverage_end = series.coverage_end or _anchor_datetime(
            trajectory, trajectory.samples[-1].time_s
        )
        anchors = [(_anchor_datetime(trajectory, row.anchor_t_s), row) for row in rows]
        records = generate_label_records(
            run_id,
            anchors,
            series,
            spec,
            coverage_end=coverage_end,
        )
        excluded: dict[str, int] = {}
        for row, record in zip(rows, records):
            if record.status is not LabelStatus.EVALUABLE or record.y is None:
                reason = (
                    "CENSORED"
                    if record.status is LabelStatus.CENSORED
                    else "UNTRUSTED_INFO"
                )
                excluded[reason] = excluded.get(reason, 0) + 1
                total_excluded[reason] = total_excluded.get(reason, 0) + 1
                continue
            features = tuple(
                math.nan if value is None else float(value) for value in row.values
            )
            samples.append(
                LabeledSample(
                    run_id=run_id,
                    group_id=group_id,
                    partition=partition,
                    source_sha256=trajectory.source_sha256,
                    sample_identity=row.sample_identity,
                    anchor_t_s=row.anchor_t_s,
                    features=features,
                    y=int(record.y),
                    series_id=series.series_id,
                )
            )
        excluded_by_run[run_id] = excluded
        run_ids.append(run_id)
    if not samples:
        raise AblationViewError("no evaluable development labels exist")
    samples.sort(key=lambda sample: (sample.run_id, sample.anchor_t_s))
    return LabeledDataset(
        samples=tuple(samples),
        feature_ids=view.feature_ids,
        label_identity=dict(spec.identity_fields),
        horizon_s=spec.horizon_s,
        spec_version=spec.spec_version,
        excluded_by_run={
            run_id: dict(value) for run_id, value in excluded_by_run.items()
        },
        total_excluded=dict(total_excluded),
        run_ids=tuple(sorted(run_ids)),
    )


def population_identity(dataset: LabeledDataset) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            sample.run_id,
            sample.group_id,
            sample.partition,
            sample.sample_identity,
            sample.anchor_t_s,
            sample.y,
            sample.series_id,
        )
        for sample in dataset.samples
    )


def assert_matched_population(*datasets: LabeledDataset) -> None:
    if len(datasets) < 2:
        raise AblationComparabilityError("at least two arm datasets are required")
    reference = population_identity(datasets[0])
    for dataset in datasets[1:]:
        if population_identity(dataset) != reference:
            raise AblationComparabilityError(
                "arms do not share an identical evaluable population, label "
                "identity, group assignment or run assignment"
            )
        if dataset.horizon_s != datasets[0].horizon_s:
            raise AblationComparabilityError("arms use different horizons")
        if dict(dataset.label_identity) != dict(datasets[0].label_identity):
            raise AblationComparabilityError("arms use different label identities")


def run_ablation_arm(
    fixture: BenchmarkFixture,
    registry: FeatureRegistry,
    config: BenchmarkConfig,
    view: AblationView,
    *,
    scaffold_dir: Any,
) -> tuple[BenchmarkResult, LabeledDataset]:
    """Run the shared W11 grouped pipeline on one arm's explicit matrix."""
    dataset = build_ablation_dataset(fixture, registry, config, view)
    result, _ = run_grouped_benchmark(
        fixture,
        registry,
        config,
        out_dir=scaffold_dir,
        labeled_override=dataset,
    )
    if tuple(result.feature_ids) != view.feature_ids:
        raise AblationViewError("benchmark result feature identity drifted from the arm view")
    return result, dataset


def run_support(dataset: LabeledDataset) -> tuple[dict[str, Any], ...]:
    rows: dict[str, dict[str, Any]] = {}
    for sample in dataset.samples:
        row = rows.setdefault(
            sample.run_id,
            {
                "run_id": sample.run_id,
                "group_id": sample.group_id,
                "partition": sample.partition,
                "anchors": 0,
                "positive": 0,
                "negative": 0,
            },
        )
        row["anchors"] += 1
        row["positive" if sample.y == 1 else "negative"] += 1
    return tuple(rows[run_id] for run_id in sorted(rows))


def fold_metric_rows(result: BenchmarkResult) -> list[dict[str, Any]]:
    rows = []
    for fold in result.fold_runs:
        metrics = fold.metrics or {}
        event = fold.event_metrics or {}

        def value(name: str, field: str = "value") -> Any:
            return (metrics.get(name) or {}).get(field)

        rows.append(
            {
                "fold_id": fold.fold_id,
                "strategy": fold.strategy,
                "status": fold.status,
                "reason": fold.reason,
                "validation_groups": ";".join(fold.validation_groups),
                "validation_runs": ";".join(fold.validation_runs),
                "train_samples": fold.train_sample_count,
                "validation_samples": fold.validation_sample_count,
                "train_positive": fold.train_positive,
                "train_negative": fold.train_negative,
                "validation_positive": fold.validation_positive,
                "validation_negative": fold.validation_negative,
                "average_precision": value("average_precision"),
                "ap_status": value("average_precision", "status"),
                "ap_reason": value("average_precision", "reason"),
                "roc_auc": value("roc_auc"),
                "precision": value("precision"),
                "recall": value("recall"),
                "f1": value("f1"),
                "warning_episodes": event.get("warning_episode_count"),
                "matched_episodes": event.get("matched_warning_episodes"),
                "unmatched_warnings": event.get("unmatched_warnings"),
                "missed_events": event.get("missed_critical_events"),
                "event_precision": event.get("event_precision"),
                "event_recall": event.get("event_recall"),
                "false_warnings_per_hour": event.get(
                    "false_warning_episodes_per_hour"
                ),
                "censored_exclusions": fold.censored_exclusions,
                "untrusted_exclusions": fold.untrusted_exclusions,
            }
        )
    return rows


def arm_summary(result: BenchmarkResult, view: AblationView) -> dict[str, Any]:
    rows = [row for row in result.fold_runs if row.status == "FIT"]
    ap_values = [
        row.metrics["average_precision"]["value"]
        for row in rows
        if row.metrics and row.metrics["average_precision"]["value"] is not None
    ]
    return {
        "arm_id": view.arm_id,
        "view_id": view.view_id,
        "feature_count": view.feature_count,
        "group_count": result.cv.effective_groups,
        "fold_count": len(result.cv.folds),
        "evaluable_samples": len(result.labeled.samples),
        "positive": result.labeled.positive_count,
        "negative": result.labeled.negative_count,
        "censored_exclusions": result.labeled.total_excluded.get("CENSORED", 0),
        "untrusted_exclusions": result.labeled.total_excluded.get(
            "UNTRUSTED_INFO", 0
        ),
        "fit_folds": len(rows),
        "strategy_count": len(result.oof),
        "strategy_fold_ap_values": {
            strategy: [
                row.metrics["average_precision"]["value"]
                for row in rows
                if row.strategy == strategy
                and row.metrics
                and row.metrics["average_precision"]["value"] is not None
            ]
            for strategy in result.oof
        },
        "fold_ap_min": min(ap_values) if ap_values else None,
        "fold_ap_max": max(ap_values) if ap_values else None,
        "oof_ap": {
            strategy: payload.get("metrics", {})
            .get("average_precision", {})
            .get("value")
            for strategy, payload in result.oof.items()
        },
        "scientific_class": SYNTHETIC_SOFTWARE_CONTROL,
    }


def paired_fold_comparison(
    result_a: BenchmarkResult, result_b: BenchmarkResult
) -> list[dict[str, Any]]:
    """Pair arms by fold and strategy; never by best-looking fold."""
    keyed_a = {(row.fold_id, row.strategy): row for row in result_a.fold_runs}
    keyed_b = {(row.fold_id, row.strategy): row for row in result_b.fold_runs}
    if set(keyed_a) != set(keyed_b):
        raise AblationComparabilityError("arms do not share identical fold identities")
    rows = []
    for key in sorted(keyed_a):
        left, right = keyed_a[key], keyed_b[key]
        if (
            left.validation_runs != right.validation_runs
            or left.train_runs != right.train_runs
            or left.validation_groups != right.validation_groups
            or left.train_groups != right.train_groups
        ):
            raise AblationComparabilityError(
                f"fold {key[0]!r} does not assign identical runs/groups in both arms"
            )
        if (
            left.validation_sample_count != right.validation_sample_count
            or left.validation_positive != right.validation_positive
            or left.validation_negative != right.validation_negative
        ):
            raise AblationComparabilityError(
                f"fold {key[0]!r} does not share a matched population"
            )

        def ap(row: Any) -> float | None:
            if row.metrics is None:
                return None
            return row.metrics["average_precision"]["value"]

        def event(row: Any, name: str) -> Any:
            return (row.event_metrics or {}).get(name)

        rows.append(
            {
                "fold_id": key[0],
                "strategy": key[1],
                "ap_a": ap(left),
                "ap_b": ap(right),
                "delta_ap_b_minus_a": (
                    None
                    if ap(left) is None or ap(right) is None
                    else ap(right) - ap(left)
                ),
                "event_recall_a": event(left, "event_recall"),
                "event_recall_b": event(right, "event_recall"),
                "false_warnings_a": event(left, "false_warning_episodes_per_hour"),
                "false_warnings_b": event(right, "false_warning_episodes_per_hour"),
                "missed_events_a": event(left, "missed_critical_events"),
                "missed_events_b": event(right, "missed_critical_events"),
            }
        )
    return rows


def provenance_rows(
    view: AblationView, registry: FeatureRegistry
) -> list[dict[str, Any]]:
    observed_slots = registry.role_map.get("observed_rig", {}).get("slots", {})
    role_to_field = {
        str(payload.get("physical_position")): f"{slot}_c"
        for slot, payload in observed_slots.items()
    }
    rows = []
    for feature in view.features:
        base = registry.feature(feature.base_feature_id)
        if feature.source_roles and all(
            role in role_to_field for role in feature.source_roles
        ):
            view_source_fields = tuple(
                role_to_field[role] for role in feature.source_roles
            )
        else:
            view_source_fields = tuple(base.source_fields)
        rows.append(
            {
                "feature_id": feature.feature_id,
                "base_feature_id": feature.base_feature_id,
                "family": feature.family,
                "registry_source_fields": ";".join(base.source_fields),
                "registry_sensor_roles": ";".join(base.sensor_roles),
                "view_source_roles": ";".join(feature.source_roles),
                "view_source_fields": ";".join(view_source_fields),
                "transform": feature.transform,
                "time_domain": feature.time_domain,
                "lookback_s": feature.lookback_s,
                "aggregation_definition": base.aggregation_definition,
            }
        )
    return rows


def single_probe_isolation_probe(
    trajectory: Trajectory,
    registry: FeatureRegistry,
    view: AblationView,
    *,
    group_id: str,
    partition: str,
) -> bool:
    """True when mutating every non-center probe leaves the arm unchanged."""
    baseline = compute_view_rows(
        trajectory, registry, view, group_id=group_id, partition=partition
    )
    mutated_samples = []
    for sample in trajectory.samples:
        mutated = []
        for role, value in sample.chamber_c:
            if role != A1A_SINGLE_ROLE and value is not None:
                mutated.append((role, value + 1000.0))
            else:
                mutated.append((role, value))
        mutated_samples.append(
            PipelineSample(
                device_id=sample.device_id,
                boot_id=sample.boot_id,
                seq=sample.seq,
                time_s=sample.time_s,
                chamber_c=tuple(mutated),
                hot_side_c=(
                    None if sample.hot_side_c is None else sample.hot_side_c + 1000.0
                ),
                thermal_quality=sample.thermal_quality,
                door_state=sample.door_state,
                door_quality=sample.door_quality,
                door_polarity_attested=sample.door_polarity_attested,
                applied_cooling=sample.applied_cooling,
                applied_duty=sample.applied_duty,
                requested_duty_permille=sample.requested_duty_permille,
                readback_duty_permille=sample.readback_duty_permille,
                cooling_voltage_v=sample.cooling_voltage_v,
                cooling_current_a=sample.cooling_current_a,
                cooling_power_w=sample.cooling_power_w,
                cooling_energy_counter_wh=sample.cooling_energy_counter_wh,
                electrical_quality=sample.electrical_quality,
                t_air_c=sample.t_air_c,
                rh_pct=sample.rh_pct,
                environment_quality=sample.environment_quality,
                overall_quality=sample.overall_quality,
            )
        )
    mutated_trajectory = Trajectory(
        run_id=trajectory.run_id,
        boot_id=trajectory.boot_id,
        device_id=trajectory.device_id,
        scenario_id=trajectory.scenario_id,
        controller_id=trajectory.controller_id,
        source_sha256=trajectory.source_sha256,
        source_type=trajectory.source_type,
        clock_domain=trajectory.clock_domain,
        origin_utc=trajectory.origin_utc,
        physical_source_key=trajectory.physical_source_key,
        samples=tuple(mutated_samples),
        physical_eligibility=trajectory.physical_eligibility,
        exclusion_reasons=trajectory.exclusion_reasons,
        source_run_ids=trajectory.source_run_ids,
    )
    changed = compute_view_rows(
        mutated_trajectory, registry, view, group_id=group_id, partition=partition
    )
    return all(
        left.values == right.values and left.missing_reasons == right.missing_reasons
        for left, right in zip(baseline, changed)
    )
