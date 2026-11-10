"""W11 grouped XGBoost benchmark (B-W11-01 ... B-W11-06).

This module is deliberately a benchmark layer, not a production predictor:

* development runs are split before any window exists;
* features come from the frozen W10 registry and an explicit allowlist;
* labels come from the W02 label contract and are development-only;
* XGBoost scores are ``risk_score`` values, never calibrated probabilities;
* the W09 baseline state machines and event evaluator are reused unchanged;
* a real training table is admitted only after matching W08 evidence, A
  authority, source identity, frozen policy evidence and split membership.

Synthetic fixtures are software controls. Their metrics are not physical
evidence about the real plant.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import xgboost
import yaml
from xgboost import XGBClassifier

from .baselines import (
    CERTAINTY_EXACT,
    EVALUABILITY_DIAGNOSTIC,
    INITIAL_OFF,
    OPERATOR_GT,
    REPRESENTATIVE_MEAN,
    STATUS_SYNTHETIC,
    TIME_BOOT_SCOPED_UPTIME,
    HysteresisConfig,
    RepresentativeTemperature,
    ThermalQualityPolicy,
    ThresholdConfig,
    evaluate_b0,
    evaluate_b1,
)
from .event_evaluator import (
    UNKNOWN,
    WARNING,
    NO_WARNING,
    AssociationPolicy,
    CriticalEventInput,
    EpisodePolicy,
    WarningSample,
    build_warning_episodes,
    evaluate_events,
    warning_samples_from_replay,
)
from .feature_fixtures import (
    FIXTURE_VERSION,
    SYNTHETIC_CONTROLLER,
    build_development_dataset,
    build_trajectory,
)
from .feature_pipeline import (
    SOURCE_TYPE_SYNTHETIC,
    FeatureRow,
    Trajectory,
    feature_rows,
)
from .feature_registry import FeatureRegistry, load_registry
from .grouped_evaluation import (
    DEVELOPMENT_PARTITIONS,
    LOCKED_TEST_PARTITION,
    ClassificationMetrics,
    EvaluationRun,
    Fold,
    GroupedCV,
    GroupedEvaluationError,
    MetricValue,
    PreprocessingLeakageError,
    aggregate_fold_ap,
    assert_train_only_fit,
    build_evaluation_runs,
    classification_metrics,
    make_grouped_folds,
)
from .intake import (
    Capture,
    NormalizedRow,
    ProbeReading,
    RunIdentity,
    SensorRole,
    SourceIdentity,
    TimeSemantics,
)
from .labels import CriticalEventSeries, LabelSpec, LabelStatus, generate_label_records
from .splitting import (
    RunInfo,
    SplitConfig,
    SplitProportions,
    SplitResult,
    split_runs,
)

CONFIG_SCHEMA = "coldguard-xgb-v1-config-v1"
W11_LAYER_VERSION = "coldguard-w11-grouped-xgb-benchmark-v1"
SYNTHETIC_PROVENANCE = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
SOFTWARE_ONLY = "SOFTWARE_ONLY"
NOT_A_SCIENTIFIC_BENCHMARK = "NOT_A_SCIENTIFIC_GROUPED_BENCHMARK"
REAL_NOT_FEASIBLE = "NOT_FEASIBLE"
FIT_STATUS_FIT = "FIT"
FIT_STATUS_REFUSED = "REFUSED"
OOF_DEFINED = "DEFINED"
OOF_UNDEFINED = "UNDEFINED"
NON_ESTIMABLE_RUN_REASON = "DEV_RUN_WITHOUT_EVALUABLE_ANCHORS"

STRATEGY_UNWEIGHTED = "UNWEIGHTED"
STRATEGY_TRAIN_FOLD_CLASS_WEIGHT = "TRAIN_FOLD_CLASS_WEIGHT"
IMBALANCE_STRATEGIES = (STRATEGY_UNWEIGHTED, STRATEGY_TRAIN_FOLD_CLASS_WEIGHT)

WARNING_DEFINITION_B0 = "B0_THRESHOLD_CRITERION"
WARNING_DEFINITION_B1 = "B1_HYSTERESIS_ON_STATE"
WARNING_DEFINITION_XGB = "XGB_RISK_SCORE_THRESHOLD"

EVENT_DEFINITION_SYNTHETIC = "coldguard-w11-prescribed-critical-event-v1"
EVENT_SOURCE_SYNTHETIC = "W11_SYNTHETIC_FIXTURE"

EWT_REASON_NO_COMMON_TRAJECTORY = (
    "EWT_UNAVAILABLE_NO_QUALIFIED_COMMON_TRAJECTORY"
)
AIW_REASON_MISSING_LATENCY_CHAIN = (
    "AIW_UNAVAILABLE_MEASURED_LATENCY_CHAIN_MISSING"
)
EWT_TEXT = (
    "no authoritative physical, non-intervened trajectory with frozen warning "
    "and reactive definitions supplies both anchors in one trusted event-time "
    "domain; synthetic benchmark rows are not physical EWT evidence"
)
AIW_TEXT = (
    "no complete measured command, ACK and thermal response latency chain is "
    "available; EWT availability would not establish AIW"
)
TRUSTED_EXPOSURE_POLICY = "ALL_CHANNEL_VALID_V1"
EPISODE_CUTOFF_POLICY = "ONSET_BEFORE_CUTOFF_INPUTS_TRUNCATED_V1"

HARDWARE_W10 = "CG-HW-SYNTHETIC"
HARDWARE_W11 = "CG-HW-SYNTHETIC-W11"
FIXTURE_W11_VERSION = "coldguard-w11-synthetic-grouped-v1"
DEVELOPMENT_ONLY_LABEL = "DEVELOPMENT_CANDIDATE_NOT_FROZEN"


class BenchmarkError(ValueError):
    """The benchmark would fabricate, leak or overstate evidence."""


class ConfigError(BenchmarkError):
    pass


class ModelFitRefusal(BenchmarkError):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail or reason


class NonEstimableRunError(BenchmarkError):
    """A declared development run has zero evaluable label anchors.

    Refuse the whole benchmark rather than drop the run or invent an
    evaluation endpoint.
    """

    reason_code = NON_ESTIMABLE_RUN_REASON

    def __init__(self, runs: Sequence[tuple[str, Mapping[str, int]]]):
        self.runs = tuple((run_id, dict(reasons)) for run_id, reasons in runs)
        detail = ", ".join(
            f"{run_id} (CENSORED={reasons.get('CENSORED', 0)}, "
            f"UNTRUSTED_INFO={reasons.get('UNTRUSTED_INFO', 0)})"
            for run_id, reasons in self.runs
        )
        super().__init__(
            f"{NON_ESTIMABLE_RUN_REASON}: {len(self.runs)} development run(s) "
            f"have zero evaluable label anchors: {detail}; the grouped benchmark "
            "is refused rather than dropping a declared run or inventing an "
            "evaluation endpoint"
        )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_sha(payload: Any) -> str:
    return _sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeaturePolicy:
    allowlist: tuple[str, ...]
    excluded_diagnostic_features: tuple[str, ...]
    prohibited_fields: tuple[str, ...]

    def assert_safe(self, registry: FeatureRegistry) -> None:
        if not self.allowlist:
            raise ConfigError("feature allowlist must be explicit and non-empty")
        if len(set(self.allowlist)) != len(self.allowlist):
            raise ConfigError("feature allowlist contains duplicate ids")
        for feature_id in self.allowlist:
            try:
                feature = registry.feature(feature_id)
            except KeyError as exc:
                raise ConfigError(
                    f"allowlist feature {feature_id!r} is not in the frozen registry"
                ) from exc
            if feature_id in self.prohibited_fields:
                raise ConfigError(
                    f"feature {feature_id!r} is a provenance/target field, not X"
                )
            if feature.family == "diagnostic_thermal":
                raise ConfigError(
                    f"diagnostic feature {feature_id!r} requires a separately "
                    "justified diagnostic model; the chamber-air model excludes it"
                )
            if feature_id in self.excluded_diagnostic_features:
                raise ConfigError(
                    f"excluded diagnostic feature {feature_id!r} is present in X"
                )


@dataclass(frozen=True)
class LabelConfig:
    spec_version: str
    horizon_s: float
    representative_temperature: str
    boundary_c: float | None
    frozen_at: str | None
    status: str

    def spec(self) -> LabelSpec:
        return LabelSpec(
            horizon_s=self.horizon_s,
            spec_version=self.spec_version,
            representative_temperature=self.representative_temperature,
            boundary_c=self.boundary_c,
            frozen_at=None,
        )

    def identity(self) -> dict[str, Any]:
        payload = self.spec().identity_fields
        payload["status"] = self.status
        return payload


@dataclass(frozen=True)
class GroupedCVConfig:
    n_splits: int
    seed: int
    min_train_groups: int
    min_validation_groups: int


@dataclass(frozen=True)
class BaselineSettings:
    raw: Mapping[str, Any]

    @property
    def warning_threshold(self) -> float:
        return float(self.raw["warning_threshold"])

    def representative(self) -> RepresentativeTemperature:
        payload = self.raw["representative"]
        return RepresentativeTemperature(
            name=str(payload["name"]),
            mode=str(payload["mode"]),
            slots=tuple(str(slot) for slot in payload["slots"]),
            unit=str(payload["unit"]),
            source=str(payload["source"]),
            freeze_status=str(payload["freeze_status"]),
        )

    def b0(self, *, run_id: str, scenario_id: str) -> ThresholdConfig:
        payload = self.raw["b0"]
        return ThresholdConfig(
            representation=self.representative(),
            threshold_c=float(payload["threshold_c"]),
            operator=str(payload["operator"]),
            time_domain=str(self.raw["time_domain"]),
            quality=ThermalQualityPolicy(),
            threshold_source=str(payload["threshold_source"]),
            threshold_status=str(payload["threshold_status"]),
            max_continuity_gap_s=float(self.raw["max_continuity_gap_s"]),
            run_id=run_id,
            scenario_id=scenario_id,
        )

    def b1(self, *, run_id: str, scenario_id: str) -> HysteresisConfig:
        payload = self.raw["b1"]
        return HysteresisConfig(
            representation=self.representative(),
            upper_on_c=float(payload["upper_on_c"]),
            lower_off_c=float(payload["lower_off_c"]),
            initial_state=str(payload["initial_state"]),
            initial_state_source=str(payload["initial_state_source"]),
            time_domain=str(self.raw["time_domain"]),
            quality=ThermalQualityPolicy(),
            upper_lower_source=str(payload["upper_lower_source"]),
            freeze_status=str(payload["freeze_status"]),
            max_continuity_gap_s=float(self.raw["max_continuity_gap_s"]),
            run_id=run_id,
            scenario_id=scenario_id,
            policy_version="coldguard-w11-synthetic-b1-v1",
        )

    def episode_policy(self) -> EpisodePolicy:
        payload = self.raw["episode_policy"]
        return EpisodePolicy(
            policy_version=str(payload["policy_version"]),
            min_persistence_s=float(payload["min_persistence_s"]),
            bridge_gap_s=float(payload["bridge_gap_s"]),
            bridge_unknown_gaps=bool(payload["bridge_unknown_gaps"]),
            status=str(payload["status"]),
            source=str(payload["source"]),
        )

    def association_policy(self) -> AssociationPolicy:
        payload = self.raw["association_policy"]
        return AssociationPolicy(
            policy_version=str(payload["policy_version"]),
            pre_window_s=float(payload["pre_window_s"]),
            post_window_s=float(payload["post_window_s"]),
            require_trusted_events=bool(payload["require_trusted_events"]),
            allow_censored_events=bool(payload["allow_censored_events"]),
            status=str(payload["status"]),
            source=str(payload["source"]),
        )


@dataclass(frozen=True)
class BenchmarkConfig:
    raw: Mapping[str, Any]
    config_version: str
    status: str
    provenance: str
    feature_policy: FeaturePolicy
    label: LabelConfig
    cv: GroupedCVConfig
    strategies: tuple[str, ...]
    baseline: BaselineSettings
    model_params: Mapping[str, Any]
    risk_threshold: float
    score_semantics: str
    calibration_status: str
    primary_metric: str
    config_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONFIG_SCHEMA,
            "config_version": self.config_version,
            "status": self.status,
            "provenance": self.provenance,
            "feature_allowlist": list(self.feature_policy.allowlist),
            "excluded_diagnostic_features": list(
                self.feature_policy.excluded_diagnostic_features
            ),
            "label": self.label.identity(),
            "grouped_cv": {
                "n_splits": self.cv.n_splits,
                "seed": self.cv.seed,
                "min_train_groups": self.cv.min_train_groups,
                "min_validation_groups": self.cv.min_validation_groups,
            },
            "imbalance_strategies": list(self.strategies),
            "model_params": dict(self.model_params),
            "risk_threshold": self.risk_threshold,
            "score_semantics": self.score_semantics,
            "calibration_status": self.calibration_status,
            "primary_metric": self.primary_metric,
            "config_sha256": self.config_sha256,
        }


_MODEL_KEYS = (
    "objective",
    "tree_method",
    "max_depth",
    "learning_rate",
    "n_estimators",
    "subsample",
    "colsample_bytree",
    "reg_lambda",
    "reg_alpha",
    "random_state",
    "n_jobs",
)


def load_benchmark_config(
    path: str | Path, registry: FeatureRegistry
) -> BenchmarkConfig:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ConfigError("benchmark config root must be a mapping")
    if payload.get("schema") != CONFIG_SCHEMA:
        raise ConfigError(f"benchmark config schema must be {CONFIG_SCHEMA}")
    for key in ("config_version", "status", "provenance", "score_semantics"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ConfigError(f"benchmark config field {key!r} is required")
    if payload["score_semantics"] != "risk_score":
        raise ConfigError("XGBoost outputs must be labelled risk_score, not probability")
    if payload.get("calibration_status") != "NOT_PERFORMED":
        raise ConfigError("this score-only benchmark performs no calibration")
    if payload.get("primary_metric") != "AVERAGE_PRECISION":
        raise ConfigError("the predeclared primary metric must be AVERAGE_PRECISION")
    feature_payload = payload.get("feature_policy")
    if not isinstance(feature_payload, Mapping):
        raise ConfigError("feature_policy is required")
    feature_policy = FeaturePolicy(
        allowlist=tuple(feature_payload.get("allowlist", ())),
        excluded_diagnostic_features=tuple(
            feature_payload.get("excluded_diagnostic_features", ())
        ),
        prohibited_fields=tuple(feature_payload.get("prohibited_fields", ())),
    )
    feature_policy.assert_safe(registry)
    label_payload = payload.get("label")
    if not isinstance(label_payload, Mapping):
        raise ConfigError("label config is required")
    label = LabelConfig(
        spec_version=str(label_payload.get("spec_version", "")),
        horizon_s=float(label_payload.get("horizon_s", 0)),
        representative_temperature=str(
            label_payload.get("representative_temperature", "")
        ),
        boundary_c=label_payload.get("boundary_c"),
        frozen_at=label_payload.get("frozen_at"),
        status=str(label_payload.get("status", "")),
    )
    if not label.spec_version or label.horizon_s <= 0:
        raise ConfigError("label spec version and positive horizon are required")
    if label.frozen_at is not None or label.boundary_c is not None:
        raise ConfigError(
            "W11 uses a development-only label candidate; no physical freeze is allowed"
        )
    cv_payload = payload.get("grouped_cv")
    if not isinstance(cv_payload, Mapping):
        raise ConfigError("grouped_cv config is required")
    cv = GroupedCVConfig(
        n_splits=int(cv_payload.get("n_splits", 0)),
        seed=int(cv_payload.get("seed", 0)),
        min_train_groups=int(cv_payload.get("min_train_groups", 1)),
        min_validation_groups=int(cv_payload.get("min_validation_groups", 1)),
    )
    if not 2 <= cv.n_splits <= 10:
        raise ConfigError("grouped CV n_splits must be between 2 and 10")
    strategies = tuple(payload.get("imbalance", {}).get("strategies", ()))
    if not strategies or any(item not in IMBALANCE_STRATEGIES for item in strategies):
        raise ConfigError(
            f"imbalance strategies must be drawn from {IMBALANCE_STRATEGIES}"
        )
    baseline_payload = payload.get("baseline")
    if not isinstance(baseline_payload, Mapping):
        raise ConfigError("baseline config is required")
    baseline = BaselineSettings(baseline_payload)
    model_params: dict[str, Any] = {}
    for key in _MODEL_KEYS:
        if key not in payload:
            raise ConfigError(f"model parameter {key!r} is required")
        model_params[key] = payload[key]
    if not isinstance(model_params["max_depth"], int) or not 1 <= model_params["max_depth"] <= 6:
        raise ConfigError("max_depth must be a bounded integer in [1, 6]")
    if not isinstance(model_params["n_estimators"], int) or not 1 <= model_params["n_estimators"] <= 200:
        raise ConfigError("n_estimators must be a bounded integer in [1, 200]")
    risk_threshold = float(payload.get("risk_threshold", 0))
    if not 0 < risk_threshold < 1:
        raise ConfigError("risk_threshold must be strictly between 0 and 1")
    return BenchmarkConfig(
        raw=payload,
        config_version=str(payload["config_version"]),
        status=str(payload["status"]),
        provenance=str(payload["provenance"]),
        feature_policy=feature_policy,
        label=label,
        cv=cv,
        strategies=strategies,
        baseline=baseline,
        model_params=model_params,
        risk_threshold=risk_threshold,
        score_semantics=str(payload["score_semantics"]),
        calibration_status=str(payload["calibration_status"]),
        primary_metric=str(payload["primary_metric"]),
        config_sha256=_canonical_sha(payload),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BenchmarkFixture:
    dataset_id: str
    fixture_version: str
    status: str
    provenance: str
    trajectories: tuple[Trajectory, ...]
    series_by_run: Mapping[str, CriticalEventSeries]
    split: SplitResult
    hardware_config_by_run: Mapping[str, str]
    limitations: tuple[str, ...]

    @property
    def development_trajectories(self) -> tuple[Trajectory, ...]:
        return tuple(
            trajectory
            for trajectory in self.trajectories
            if self.split.partition_of(trajectory.run_id or "")
            in DEVELOPMENT_PARTITIONS
        )

    @property
    def test_runs(self) -> tuple[str, ...]:
        return tuple(self.split.test_runs)


def build_w10_compatibility_fixture() -> BenchmarkFixture:
    dataset = build_development_dataset()
    hardware = {
        trajectory.run_id: HARDWARE_W10
        for trajectory in dataset.trajectories
        if trajectory.run_id is not None
    }
    return BenchmarkFixture(
        dataset_id="W10_SYNTHETIC_DEVELOPMENT_COMPATIBILITY",
        fixture_version=FIXTURE_VERSION,
        status=NOT_A_SCIENTIFIC_BENCHMARK,
        provenance=SOFTWARE_ONLY,
        trajectories=dataset.trajectories,
        series_by_run=dataset.series_by_run,
        split=dataset.split,
        hardware_config_by_run=hardware,
        limitations=(
            "two development pair groups only; not a credible scientific population",
            "candidate horizon 300 has no development negative labels in this fixture",
            "the W10 held-out synthetic test pair is untouched by W11",
            "metrics are software controls, not physical evidence",
        ),
    )


def build_expanded_w11_fixture() -> BenchmarkFixture:
    pairs = tuple(
        (
            f"CG-W11-S2-{index:03d}",
            f"CG-W11-S1-{index:03d}",
            900 + index,
            1000 + index,
            f"W11-PAIR-{index:03d}",
        )
        for index in range(1, 11)
    )
    trajectories: list[Trajectory] = []
    series_by_run: dict[str, CriticalEventSeries] = {}
    run_infos: list[RunInfo] = []
    for s2_run, s1_run, s2_seed, s1_seed, pair_id in pairs:
        s2, s2_series = build_trajectory(
            s2_run,
            scenario="S2",
            seed=s2_seed,
            duration_s=180.0,
            door_start_s=40.0,
            door_duration_s=20.0,
            critical_offsets_s=(100.0,),
        )
        s1, s1_series = build_trajectory(
            s1_run,
            scenario="S1",
            seed=s1_seed,
            duration_s=180.0,
        )
        trajectories.extend((s2, s1))
        series_by_run[s2_run] = s2_series
        series_by_run[s1_run] = s1_series
        run_infos.extend(
            (
                RunInfo(
                    run_id=s2_run,
                    scenario_id="S2",
                    controller_id=SYNTHETIC_CONTROLLER,
                    pair_id=pair_id,
                    hardware_config_id=HARDWARE_W11,
                ),
                RunInfo(
                    run_id=s1_run,
                    scenario_id="S1",
                    controller_id=SYNTHETIC_CONTROLLER,
                    pair_id=pair_id,
                    hardware_config_id=HARDWARE_W11,
                ),
            )
        )
    split = split_runs(
        run_infos,
        SplitConfig(
            proportions=SplitProportions(0.4, 0.4, 0.2),
            seed=42,
            controller_context="all-reactive-or-observational",
            min_groups_per_partition=1,
            hardware_lineage=HARDWARE_W11,
        ),
    )
    hardware = {
        trajectory.run_id: HARDWARE_W11
        for trajectory in trajectories
        if trajectory.run_id is not None
    }
    return BenchmarkFixture(
        dataset_id="W11_EXPANDED_SYNTHETIC_GROUPED",
        fixture_version=FIXTURE_W11_VERSION,
        status=SYNTHETIC_PROVENANCE,
        provenance=SYNTHETIC_PROVENANCE,
        trajectories=tuple(sorted(trajectories, key=lambda item: item.run_id or "")),
        series_by_run=series_by_run,
        split=split,
        hardware_config_by_run=hardware,
        limitations=(
            "deterministic synthetic fixture; its data-generating process does not "
            "approximate real thermal performance",
            "no real physical data is borrowed, inspected or modified",
            "the W10 held-out synthetic test pair is untouched by W11",
            "metrics are software controls, not a ColdGuard predictive-science result",
        ),
    )


# ---------------------------------------------------------------------------
# Labels and feature matrices
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LabeledSample:
    run_id: str
    group_id: str
    partition: str
    source_sha256: str
    sample_identity: str
    anchor_t_s: float
    features: tuple[float, ...]
    y: int
    series_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "group_id": self.group_id,
            "partition": self.partition,
            "source_sha256": self.source_sha256,
            "sample_identity": self.sample_identity,
            "anchor_t_s": self.anchor_t_s,
            "y": self.y,
            "series_id": self.series_id,
        }


@dataclass(frozen=True)
class LabeledDataset:
    samples: tuple[LabeledSample, ...]
    feature_ids: tuple[str, ...]
    label_identity: Mapping[str, Any]
    horizon_s: float
    spec_version: str
    excluded_by_run: Mapping[str, Mapping[str, int]]
    total_excluded: Mapping[str, int]
    run_ids: tuple[str, ...]

    @property
    def positive_count(self) -> int:
        return sum(1 for sample in self.samples if sample.y == 1)

    @property
    def negative_count(self) -> int:
        return sum(1 for sample in self.samples if sample.y == 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": len(self.samples),
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "feature_ids": list(self.feature_ids),
            "label_identity": dict(self.label_identity),
            "horizon_s": self.horizon_s,
            "spec_version": self.spec_version,
            "excluded_by_run": {
                run_id: dict(value) for run_id, value in self.excluded_by_run.items()
            },
            "total_excluded": dict(self.total_excluded),
            "run_ids": list(self.run_ids),
        }


def _anchor_datetime(trajectory: Trajectory, anchor_t_s: float) -> Any:
    import datetime as _dt

    if trajectory.origin_utc is None:
        raise BenchmarkError(
            f"run {trajectory.run_id!r} has no absolute origin for labels"
        )
    origin = _dt.datetime.fromisoformat(trajectory.origin_utc.replace("Z", "+00:00"))
    return origin + _dt.timedelta(seconds=anchor_t_s)


def build_labeled_dataset(
    fixture: BenchmarkFixture,
    registry: FeatureRegistry,
    config: BenchmarkConfig,
) -> LabeledDataset:
    """Attach development-only labels after run-level splits and features."""
    spec = config.label.spec()
    index = {feature_id: position for position, feature_id in enumerate(registry.feature_ids)}
    allowlist = config.feature_policy.allowlist
    missing_allowlist = [item for item in allowlist if item not in index]
    if missing_allowlist:
        raise ConfigError(f"allowlist ids absent from registry: {missing_allowlist}")
    feature_positions = [index[item] for item in allowlist]
    samples: list[LabeledSample] = []
    excluded_by_run: dict[str, dict[str, int]] = {}
    total_excluded: dict[str, int] = {}
    run_ids: list[str] = []
    for trajectory in fixture.development_trajectories:
        run_id = trajectory.run_id
        if run_id is None:
            raise BenchmarkError("development trajectory has no run identity")
        partition = fixture.split.partition_of(run_id)
        if partition not in DEVELOPMENT_PARTITIONS:
            raise BenchmarkError(
                f"run {run_id!r} is not in a development partition"
            )
        series = fixture.series_by_run.get(run_id)
        if series is None:
            raise BenchmarkError(f"run {run_id!r} has no critical-event series")
        rows = feature_rows(
            trajectory,
            registry,
            partition=partition,
            split=fixture.split,
        )
        coverage_end = series.coverage_end or _anchor_datetime(
            trajectory, trajectory.samples[-1].time_s
        )
        anchors = [(_anchor_datetime(trajectory, row.anchor_t_s), row) for row in rows]
        records = generate_label_records(
            run_id,
            [(anchor, row) for anchor, row in anchors],
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
                float("nan")
                if row.values[position] is None
                else float(row.values[position])
                for position in feature_positions
            )
            samples.append(
                LabeledSample(
                    run_id=run_id,
                    group_id=fixture.split.group_of[run_id],
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
        raise BenchmarkError("no evaluable development labels exist")
    samples.sort(key=lambda sample: (sample.run_id, sample.anchor_t_s))
    return LabeledDataset(
        samples=tuple(samples),
        feature_ids=allowlist,
        label_identity=dict(spec.identity_fields),
        horizon_s=spec.horizon_s,
        spec_version=spec.spec_version,
        excluded_by_run={
            run_id: dict(value) for run_id, value in excluded_by_run.items()
        },
        total_excluded=dict(total_excluded),
        run_ids=tuple(sorted(run_ids)),
    )


def feature_matrix(
    samples: Sequence[LabeledSample], feature_ids: Sequence[str]
) -> tuple[np.ndarray, np.ndarray]:
    """None becomes NaN; a missing electrical value is never silently zero."""
    matrix = np.full((len(samples), len(feature_ids)), np.nan, dtype=float)
    labels = np.zeros(len(samples), dtype=int)
    for row_index, sample in enumerate(samples):
        if len(sample.features) != len(feature_ids):
            raise BenchmarkError("sample feature width differs from the schema")
        for column_index, value in enumerate(sample.features):
            if value is None:
                continue
            numeric = float(value)
            if not math.isfinite(numeric):
                continue
            matrix[row_index, column_index] = numeric
        labels[row_index] = sample.y
    return matrix, labels


# ---------------------------------------------------------------------------
# W04 capture representation for W09 baselines
# ---------------------------------------------------------------------------


CHAMBER_SLOT_BY_ROLE = {
    "CHAMBER_CENTER": "t1",
    "CHAMBER_BOTTOM": "t3",
    "CHAMBER_NEAR_DOOR": "t4",
}
HOT_SLOT = "t2"


def _sensor_roles() -> tuple[SensorRole, ...]:
    roles = []
    for slot, position, in_aggregate in (
        ("t1", "CHAMBER_CENTER", True),
        ("t2", "TEC_HOT_SIDE", False),
        ("t3", "CHAMBER_BOTTOM", True),
        ("t4", "CHAMBER_NEAR_DOOR", True),
    ):
        roles.append(
            SensorRole(
                slot=slot,
                rom=f"ROM-{slot}",
                rom_source="SYNTHETIC",
                rom_readback_verified=True,
                physical_position=position,
                position_source="DECLARED",
                in_chamber_air_aggregate=in_aggregate,
                exclusion_reason=None if in_aggregate else "HOT_SIDE",
                raw_roles=(slot.upper(),),
                role_conflict=None,
            )
        )
    return tuple(roles)


def capture_from_trajectory(
    trajectory: Trajectory, *, hardware_config_id: str
) -> Capture:
    """Represent one synthetic trajectory as a W04 capture for W09 replay only."""
    if trajectory.run_id is None or trajectory.device_id is None:
        raise BenchmarkError(
            "the synthetic baseline adapter requires resolved run/device identity"
        )
    rows: list[NormalizedRow] = []
    for sample in trajectory.samples:
        probes = []
        for slot in ("t1", "t2", "t3", "t4"):
            position = {
                "t1": "CHAMBER_CENTER",
                "t2": "TEC_HOT_SIDE",
                "t3": "CHAMBER_BOTTOM",
                "t4": "CHAMBER_NEAR_DOOR",
            }[slot]
            if slot == HOT_SLOT:
                value = sample.hot_side_c
                role = "HOT_SIDE"
            else:
                role = position
                value = sample.probe(role)
            probes.append(
                ProbeReading(
                    slot=slot,
                    value_c=value,
                    status="OK" if value is not None else "NONE",
                    role=role,
                    age_ms=10,
                    rom=f"ROM-{slot}",
                    physical_position=position,
                )
            )
        electrical_fields = tuple(
            name
            for name, value in (
                ("cooling_voltage_v", sample.cooling_voltage_v),
                ("cooling_current_a", sample.cooling_current_a),
                ("cooling_power_w", sample.cooling_power_w),
                ("cooling_energy_counter_wh", sample.cooling_energy_counter_wh),
            )
            if value is not None
        )
        rows.append(
            NormalizedRow(
                seq=sample.seq,
                boot_id=sample.boot_id,
                run_id=trajectory.run_id,
                device_id=trajectory.device_id,
                hardware_config_id=hardware_config_id,
                firmware_version="W11-SYNTHETIC",
                device_ms=int(round(sample.time_s * 1000.0)),
                event_time_utc=None,
                host_capture_time_utc=None,
                probes=tuple(probes),
                t_air_c=sample.t_air_c,
                rh_pct=sample.rh_pct,
                pressure_hpa=None,
                door_state=sample.door_state,
                door_polarity="CONFIRMED" if sample.door_polarity_attested else None,
                cooling_voltage_v=sample.cooling_voltage_v,
                cooling_current_a=sample.cooling_current_a,
                cooling_power_w=sample.cooling_power_w,
                cooling_energy_counter_wh=sample.cooling_energy_counter_wh,
                electrical_measured_fields=electrical_fields,
                applied_cooling=sample.applied_cooling,
                applied_duty=sample.applied_duty,
                applied_duty_permille=(
                    None
                    if sample.applied_duty is None
                    else int(round(sample.applied_duty * 1000))
                ),
                requested_duty_permille=sample.requested_duty_permille,
                readback_duty_permille=sample.readback_duty_permille,
                device_state="COOLING" if sample.applied_cooling == "ON" else "IDLE",
                experiment_phase="W11_SYNTHETIC",
                quality=(
                    ("thermal", sample.thermal_quality),
                    ("electrical", sample.electrical_quality),
                    ("environment", sample.environment_quality),
                    ("producer", "VALID"),
                    ("overall", sample.overall_quality),
                ),
                overall_quality=sample.overall_quality,
                producer_quality="VALID",
                usable_for=tuple(
                    scenario
                    for scenario in (trajectory.scenario_id or "",)
                    if scenario
                ),
                invalidation_reasons=(),
                source_line_index=sample.seq + 2,
                dedup_key=(sample.boot_id, str(sample.seq)),
            )
        )
    return Capture(
        source=SourceIdentity(
            path=f"w11-synthetic/{trajectory.run_id}.json",
            sha256=trajectory.source_sha256,
            format="A_W09_EXPORT",
            schema_namespace="coldguard.a",
            provenance="SYNTHETIC",
            is_physical_measurement=False,
        ),
        run=RunIdentity(
            run_id=trajectory.run_id,
            run_id_status="RESOLVED",
            run_ids=(trajectory.run_id,),
            boot_id=trajectory.boot_id,
            boot_id_status="SOURCE_CARRIED",
            device_id=trajectory.device_id,
            device_id_status="RESOLVED",
            hardware_config_id=hardware_config_id,
            hardware_config_status="VERIFIED",
            firmware_version="W11-SYNTHETIC",
            firmware_version_status="RESOLVED",
            calibration_id="CAL-W11-SYNTHETIC",
            calibration_status="VERIFIED",
            scenario_id=trajectory.scenario_id,
            scenario_status="DECLARED",
            controller_id=trajectory.controller_id or "OBSERVATIONAL",
            controller_status="DECLARED",
            device_run_label=None,
        ),
        time=TimeSemantics(
            domain="BOOT_SCOPED_UPTIME",
            event_time_status="UNAVAILABLE",
            clock_sync="SYNTHETIC_EXACT",
            boot_scoped=True,
            cross_boot_join_allowed=False,
            absolute_latency_supported=False,
            detail="W11 deterministic synthetic fixture",
        ),
        rows=tuple(rows),
        sensors=_sensor_roles(),
        a_validity=None,
        declared_unavailable_fields=(),
        recognized_fields=(),
        unknown_fields=(),
        warnings=(),
    )


# ---------------------------------------------------------------------------
# Model fitting and grouped benchmark
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FoldRunResult:
    fold_id: str
    strategy: str
    status: str
    reason: str | None
    detail: str | None
    train_groups: tuple[str, ...]
    validation_groups: tuple[str, ...]
    train_runs: tuple[str, ...]
    validation_runs: tuple[str, ...]
    train_sample_count: int
    validation_sample_count: int
    train_positive: int
    train_negative: int
    validation_positive: int
    validation_negative: int
    censored_exclusions: int
    untrusted_exclusions: int
    scale_pos_weight: float | None
    weight_formula: str | None
    metrics: Mapping[str, Any] | None
    event_metrics: Mapping[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "strategy": self.strategy,
            "status": self.status,
            "reason": self.reason,
            "detail": self.detail,
            "train_group_ids": list(self.train_groups),
            "validation_group_ids": list(self.validation_groups),
            "train_run_ids": list(self.train_runs),
            "validation_run_ids": list(self.validation_runs),
            "train_sample_count": self.train_sample_count,
            "validation_sample_count": self.validation_sample_count,
            "train_positive": self.train_positive,
            "train_negative": self.train_negative,
            "validation_positive": self.validation_positive,
            "validation_negative": self.validation_negative,
            "censored_exclusions": self.censored_exclusions,
            "untrusted_exclusions": self.untrusted_exclusions,
            "scale_pos_weight": self.scale_pos_weight,
            "weight_formula": self.weight_formula,
            "metrics": dict(self.metrics) if self.metrics is not None else None,
            "event_metrics": (
                dict(self.event_metrics) if self.event_metrics is not None else None
            ),
        }


@dataclass(frozen=True)
class BenchmarkResult:
    mode: str
    status: str
    provenance: str
    dataset_id: str
    fixture_version: str
    config_sha256: str
    registry_sha256: str
    feature_ids: tuple[str, ...]
    label_identity: Mapping[str, Any]
    cv: GroupedCV
    labeled: LabeledDataset
    fold_runs: tuple[FoldRunResult, ...]
    oof: Mapping[str, Any]
    baseline_rows: tuple[dict[str, Any], ...]
    model_artifact: Mapping[str, Any] | None
    versions: Mapping[str, str]
    split_identity: Mapping[str, Any]
    limitations: tuple[str, ...]
    reason_codes: tuple[str, ...]


def _class_counts(samples: Sequence[LabeledSample]) -> tuple[int, int]:
    positive = sum(1 for sample in samples if sample.y == 1)
    return positive, len(samples) - positive


def _fit_fold(
    *,
    fold: Fold,
    strategy: str,
    train_samples: Sequence[LabeledSample],
    validation_samples: Sequence[LabeledSample],
    config: BenchmarkConfig,
    feature_ids: Sequence[str],
) -> tuple[FoldRunResult, XGBClassifier | None]:
    train_positive, train_negative = _class_counts(train_samples)
    validation_positive, validation_negative = _class_counts(validation_samples)
    base = {
        "fold_id": fold.fold_id,
        "strategy": strategy,
        "train_groups": fold.train_groups,
        "validation_groups": fold.validation_groups,
        "train_runs": fold.train_runs,
        "validation_runs": fold.validation_runs,
        "train_sample_count": len(train_samples),
        "validation_sample_count": len(validation_samples),
        "train_positive": train_positive,
        "train_negative": train_negative,
        "validation_positive": validation_positive,
        "validation_negative": validation_negative,
        "censored_exclusions": 0,
        "untrusted_exclusions": 0,
        "scale_pos_weight": None,
        "weight_formula": None,
        "metrics": None,
        "event_metrics": None,
    }
    if not train_samples or not validation_samples:
        return (
            FoldRunResult(
                status=FIT_STATUS_REFUSED,
                reason="EMPTY_FOLD_POPULATION",
                detail="train or validation population is empty",
                **base,
            ),
            None,
        )
    if train_positive == 0 or train_negative == 0:
        return (
            FoldRunResult(
                status=FIT_STATUS_REFUSED,
                reason="SINGLE_CLASS_TRAINING_FOLD",
                detail=(
                    f"train fold has {train_positive} positive and "
                    f"{train_negative} negative labels; supervised fit is refused"
                ),
                **base,
            ),
            None,
        )
    if strategy == STRATEGY_UNWEIGHTED:
        weight = 1.0
        formula = "scale_pos_weight = 1.0"
    else:
        weight = train_negative / train_positive
        formula = "scale_pos_weight = train_negative / train_positive"
        if not math.isfinite(weight) or weight <= 0:
            return (
                FoldRunResult(
                    status=FIT_STATUS_REFUSED,
                    reason="NON_FINITE_CLASS_WEIGHT",
                    detail="train-fold class weighting is undefined",
                    **base,
                ),
                None,
            )
    X_train, y_train = feature_matrix(train_samples, feature_ids)
    X_validation, y_validation = feature_matrix(validation_samples, feature_ids)
    params = dict(config.model_params)
    params["scale_pos_weight"] = weight
    params["random_state"] = config.model_params["random_state"]
    params["n_jobs"] = 1
    params["verbosity"] = 0
    model = XGBClassifier(**params)
    model.fit(X_train, y_train)
    scores = np.asarray(model.predict_proba(X_validation)[:, 1], dtype=float)
    metrics = classification_metrics(
        list(y_validation), list(scores), threshold=config.risk_threshold
    )
    base.update(
        {
            "scale_pos_weight": weight,
            "weight_formula": formula,
            "metrics": metrics.to_dict(),
        }
    )
    return (
        FoldRunResult(
            status=FIT_STATUS_FIT,
            reason=None,
            detail=None,
            **base,
        ),
        model,
    )


def _warning_samples_from_scores(
    samples: Sequence[LabeledSample],
    scores: Sequence[float],
    *,
    threshold: float,
) -> tuple[WarningSample, ...]:
    result = []
    for sample, score in zip(samples, scores):
        state = WARNING if float(score) >= threshold else NO_WARNING
        result.append(
            WarningSample(
                time_s=sample.anchor_t_s,
                state=state,
                sample_id=sample.sample_identity,
                quality="EVALUABLE",
            )
        )
    if any(
        right.time_s < left.time_s for left, right in zip(result, result[1:])
    ):
        raise BenchmarkError("XGBoost warning samples are not event-time ordered")
    return tuple(result)


def _critical_event_inputs(
    trajectory: Trajectory, series: CriticalEventSeries
) -> tuple[CriticalEventInput, ...]:
    origin = _anchor_datetime(trajectory, 0.0)
    inputs = []
    for index, event in enumerate(series.events):
        time_s = (event.time - origin).total_seconds()
        inputs.append(
            CriticalEventInput(
                event_id=f"{series.series_id}:{index}:{event.ref or 'EVENT'}",
                time_s=time_s,
                run_id=series.run_id,
                source_sha256=trajectory.source_sha256,
                definition_version=EVENT_DEFINITION_SYNTHETIC,
                source=EVENT_SOURCE_SYNTHETIC,
                observed=True,
                trusted=event.trusted,
                intervention=False,
                time_certainty=CERTAINTY_EXACT,
                interval_start_s=time_s,
                interval_end_s=time_s,
            )
        )
    return tuple(inputs)


@dataclass(frozen=True)
class TrustedExposure:
    policy_version: str
    evaluation_end_s: float
    first_trusted_observation_s: float | None
    trusted_duration_s: float
    untrusted_duration_s: float
    fully_observed: bool


def _fully_valid(sample: Any) -> bool:
    return all(
        getattr(sample, name) == "VALID"
        for name in (
            "thermal_quality",
            "electrical_quality",
            "environment_quality",
            "door_quality",
        )
    )


def trusted_exposure(
    trajectory: Trajectory,
    *,
    evaluation_end_s: float,
    max_continuity_gap_s: float,
) -> TrustedExposure:
    """Trusted, evaluable exposure through the evaluation cutoff.

    Only intervals between two consecutive all-channel VALID samples no wider
    than the declared continuity bound count as observed time. Time before the
    first trusted sample and any missing/invalid interval are unobservable,
    never silently folded into a rate denominator.
    """
    if not math.isfinite(evaluation_end_s) or evaluation_end_s <= 0:
        raise BenchmarkError("evaluation_end_s must be positive and finite")
    samples = tuple(
        sample for sample in trajectory.samples if sample.time_s <= evaluation_end_s
    )
    if len(samples) < 2:
        return TrustedExposure(
            policy_version=TRUSTED_EXPOSURE_POLICY,
            evaluation_end_s=evaluation_end_s,
            first_trusted_observation_s=None,
            trusted_duration_s=0.0,
            untrusted_duration_s=evaluation_end_s,
            fully_observed=False,
        )
    trusted = 0.0
    untrusted = 0.0
    first_trusted = next(
        (
            sample.time_s
            for sample in samples
            if _fully_valid(sample)
        ),
        None,
    )
    if samples[0].time_s > 0:
        untrusted += samples[0].time_s
    for left, right in zip(samples, samples[1:]):
        delta = right.time_s - left.time_s
        if (
            delta > 0
            and _fully_valid(left)
            and _fully_valid(right)
            and delta <= max_continuity_gap_s
        ):
            trusted += delta
        else:
            untrusted += delta
    if evaluation_end_s > samples[-1].time_s:
        untrusted += evaluation_end_s - samples[-1].time_s
    trusted = round(trusted, 9)
    untrusted = round(untrusted, 9)
    fully_observed = untrusted == 0 and trusted > 0
    return TrustedExposure(
        policy_version=TRUSTED_EXPOSURE_POLICY,
        evaluation_end_s=evaluation_end_s,
        first_trusted_observation_s=first_trusted,
        trusted_duration_s=trusted,
        untrusted_duration_s=untrusted,
        fully_observed=fully_observed,
    )


def _censor_after_cutoff(
    events: Sequence[CriticalEventInput], evaluation_end_s: float
) -> tuple[CriticalEventInput, ...]:
    """Events beyond the anchor cutoff are right-censored, never dropped."""
    return tuple(
        event
        if event.time_s is None or event.time_s <= evaluation_end_s
        else replace(event, observed=False, censored=True)
        for event in events
    )


def _truncate_samples(
    samples: Sequence[WarningSample], evaluation_end_s: float
) -> tuple[WarningSample, ...]:
    """An online warning onset may use only samples at or before the cutoff."""
    return tuple(sample for sample in samples if sample.time_s <= evaluation_end_s)


def _event_result(
    *,
    trajectory: Trajectory,
    samples: Sequence[WarningSample],
    critical_events: Sequence[CriticalEventInput],
    episode_policy: EpisodePolicy,
    association_policy: AssociationPolicy,
    warning_definition: str,
    evaluation_end_s: float,
    trusted_exposure_s: float,
    coverage_trustworthy: bool,
) -> Any:
    episodes = build_warning_episodes(
        _truncate_samples(samples, evaluation_end_s),
        episode_policy,
        run_id=trajectory.run_id,
        source_sha256=trajectory.source_sha256,
        synthetic_control=True,
    ).episodes
    return evaluate_events(
        run_id=trajectory.run_id,
        source_sha256=trajectory.source_sha256,
        episodes=episodes,
        critical_events=_censor_after_cutoff(
            critical_events, evaluation_end_s
        ),
        episode_policy=episode_policy,
        association_policy=association_policy,
        warning_definition=warning_definition,
        coverage_trustworthy=coverage_trustworthy,
        eligible_run_count=1,
        evaluable_duration_s=trusted_exposure_s,
        synthetic_control=True,
    )


def aggregate_event_results(
    results: Sequence[Any], *, duration_s: float, untrusted_duration_s: float = 0.0
) -> dict[str, Any]:
    if not results:
        return {
            "warning_episode_count": None,
            "matched_warning_episodes": None,
            "unmatched_warnings": None,
            "missed_critical_events": None,
            "eligible_critical_event_count": None,
            "censored_event_count": None,
            "untrusted_event_count": None,
            "false_warning_episodes_per_run": None,
            "false_warning_episodes_per_hour": None,
            "event_precision": None,
            "event_recall": None,
            "trusted_exposure_s": duration_s,
            "untrusted_exposure_s": untrusted_duration_s,
            "coverage_trustworthy": None,
            "undefined_reasons": ["NO_EVALUATION_RESULTS"],
            "per_run_undefined_reasons": [],
        }
    matched = sum(item.metrics.true_matched_warning_episodes for item in results)
    unmatched = sum(item.metrics.unmatched_warning_episodes for item in results)
    missed = sum(item.metrics.missed_critical_events for item in results)
    episode_count = sum(item.metrics.episode_support for item in results)
    event_count = sum(
        item.metrics.eligible_critical_event_denominator for item in results
    )
    censored_events = sum(item.metrics.censored_event_count for item in results)
    untrusted_events = sum(item.metrics.untrusted_event_count for item in results)
    run_support = sum(item.metrics.run_support for item in results)
    coverage_trustworthy = all(item.coverage_trustworthy for item in results)
    per_run_undefined: list[str] = []
    for item in results:
        per_run_undefined.extend(item.metrics.undefined_reasons)
    undefined: list[str] = []
    if episode_count == 0:
        precision = None
        undefined.append("NO_WARNING_EPISODES")
    else:
        precision = matched / episode_count
    if event_count == 0:
        recall = None
        undefined.append("NO_ELIGIBLE_CRITICAL_EVENTS")
    elif coverage_trustworthy:
        recall = matched / event_count
    else:
        recall = None
        undefined.append(
            "EVENT_RECALL_UNDEFINED_INCOMPLETE_COVERAGE"
        )
    false_warning_defined = coverage_trustworthy
    per_run = (
        unmatched / run_support
        if false_warning_defined and run_support > 0
        else None
    )
    per_hour = (
        unmatched / (duration_s / 3600.0)
        if false_warning_defined and duration_s > 0
        else None
    )
    if not false_warning_defined:
        undefined.append("FALSE_WARNING_BURDEN_UNDEFINED_INCOMPLETE_COVERAGE")
    if run_support <= 0:
        undefined.append("NO_RUN_SUPPORT")
    if duration_s <= 0:
        undefined.append("NO_EVALUABLE_DURATION")
    return {
        "warning_episode_count": episode_count,
        "matched_warning_episodes": matched,
        "unmatched_warnings": unmatched,
        "missed_critical_events": missed,
        "eligible_critical_event_count": event_count,
        "censored_event_count": censored_events,
        "untrusted_event_count": untrusted_events,
        "false_warning_episodes_per_run": per_run,
        "false_warning_episodes_per_hour": per_hour,
        "event_precision": precision,
        "event_recall": recall,
        "trusted_exposure_s": round(duration_s, 9),
        "untrusted_exposure_s": round(untrusted_duration_s, 9),
        "coverage_trustworthy": coverage_trustworthy,
        "undefined_reasons": list(dict.fromkeys(undefined)),
        "per_run_undefined_reasons": list(dict.fromkeys(per_run_undefined)),
    }


@dataclass
class _BaselineRun:
    trajectory: Trajectory
    series: CriticalEventSeries
    capture: Capture
    event_inputs: tuple[CriticalEventInput, ...]
    b0_episodes: Any
    b1_episodes: Any
    b0_scores: Mapping[float, float | None]
    b1_scores: Mapping[float, float | None]
    b0_events: Any | None
    b1_events: Any | None
    b0_evaluability: str
    b1_evaluability: str
    duration_s: float
    untrusted_duration_s: float
    coverage_trustworthy: bool
    first_trusted_observation_s: float | None


def _prepare_baseline_run(
    trajectory: Trajectory,
    series: CriticalEventSeries,
    *,
    hardware_config_id: str,
    config: BenchmarkConfig,
    evaluation_end_s: float,
) -> _BaselineRun:
    scenario = trajectory.scenario_id or "UNKNOWN"
    capture = capture_from_trajectory(trajectory, hardware_config_id=hardware_config_id)
    run_id = trajectory.run_id or ""
    exposure = trusted_exposure(
        trajectory,
        evaluation_end_s=evaluation_end_s,
        max_continuity_gap_s=config.baseline.raw["max_continuity_gap_s"],
    )
    b0 = evaluate_b0(capture, config.baseline.b0(run_id=run_id, scenario_id=scenario))
    b1 = evaluate_b1(capture, config.baseline.b1(run_id=run_id, scenario_id=scenario))
    episode_policy = config.baseline.episode_policy()
    association_policy = config.baseline.association_policy()
    b0_samples = (
        _truncate_samples(
            warning_samples_from_replay(
                b0, warning_definition=WARNING_DEFINITION_B0
            )[0],
            evaluation_end_s,
        )
        if b0.evaluability == EVALUABILITY_DIAGNOSTIC
        else ()
    )
    b1_samples = (
        _truncate_samples(
            warning_samples_from_replay(
                b1, warning_definition=WARNING_DEFINITION_B1
            )[0],
            evaluation_end_s,
        )
        if b1.evaluability == EVALUABILITY_DIAGNOSTIC
        else ()
    )
    b0_episodes = build_warning_episodes(
        b0_samples,
        episode_policy,
        run_id=run_id,
        source_sha256=trajectory.source_sha256,
        synthetic_control=True,
    ).episodes
    b1_episodes = build_warning_episodes(
        b1_samples,
        episode_policy,
        run_id=run_id,
        source_sha256=trajectory.source_sha256,
        synthetic_control=True,
    ).episodes
    event_inputs = _censor_after_cutoff(
        _critical_event_inputs(trajectory, series), evaluation_end_s
    )
    duration_s = exposure.trusted_duration_s
    b0_events = (
        evaluate_events(
            run_id=run_id,
            source_sha256=trajectory.source_sha256,
            episodes=b0_episodes,
            critical_events=event_inputs,
            episode_policy=episode_policy,
            association_policy=association_policy,
            warning_definition=WARNING_DEFINITION_B0,
            coverage_trustworthy=exposure.fully_observed,
            eligible_run_count=1,
            evaluable_duration_s=duration_s,
            synthetic_control=True,
        )
        if b0.evaluability == EVALUABILITY_DIAGNOSTIC
        else None
    )
    b1_events = (
        evaluate_events(
            run_id=run_id,
            source_sha256=trajectory.source_sha256,
            episodes=b1_episodes,
            critical_events=event_inputs,
            episode_policy=episode_policy,
            association_policy=association_policy,
            warning_definition=WARNING_DEFINITION_B1,
            coverage_trustworthy=exposure.fully_observed,
            eligible_run_count=1,
            evaluable_duration_s=duration_s,
            synthetic_control=True,
        )
        if b1.evaluability == EVALUABILITY_DIAGNOSTIC
        else None
    )
    b0_scores = {
        sample.time_s: sample.representative_c
        for sample in b0.samples
        if sample.time_s is not None and sample.time_s <= evaluation_end_s
    }
    b1_scores = {
        sample.time_s: (
            None
            if sample.new_state is None
            else (1.0 if sample.new_state == "ON" else 0.0)
        )
        for sample in b1.samples
        if sample.time_s is not None and sample.time_s <= evaluation_end_s
    }
    return _BaselineRun(
        trajectory=trajectory,
        series=series,
        capture=capture,
        event_inputs=event_inputs,
        b0_episodes=b0_episodes,
        b1_episodes=b1_episodes,
        b0_scores=b0_scores,
        b1_scores=b1_scores,
        b0_events=b0_events,
        b1_events=b1_events,
        b0_evaluability=b0.evaluability,
        b1_evaluability=b1.evaluability,
        duration_s=duration_s,
        untrusted_duration_s=exposure.untrusted_duration_s,
        coverage_trustworthy=exposure.fully_observed,
        first_trusted_observation_s=exposure.first_trusted_observation_s,
    )


def _validate_labeled_override(
    fixture: BenchmarkFixture,
    registry: FeatureRegistry,
    config: BenchmarkConfig,
    labeled: LabeledDataset,
) -> None:
    """Refuse an arm matrix that changes labels, groups or the run population."""
    expected_identity = dict(config.label.spec().identity_fields)
    if dict(labeled.label_identity) != expected_identity:
        raise BenchmarkError(
            "labeled override changes the configured label identity"
        )
    if labeled.horizon_s != config.label.horizon_s:
        raise BenchmarkError("labeled override changes the configured horizon")
    development_runs = {
        trajectory.run_id
        for trajectory in fixture.development_trajectories
        if trajectory.run_id is not None
    }
    if set(labeled.run_ids) != development_runs:
        raise BenchmarkError(
            "labeled override does not cover exactly the development runs"
        )
    if not labeled.feature_ids:
        raise BenchmarkError("labeled override has no feature columns")
    if len(set(labeled.feature_ids)) != len(labeled.feature_ids):
        raise BenchmarkError("labeled override feature allowlist contains duplicates")
    banned = set(config.feature_policy.prohibited_fields) | set(
        config.feature_policy.excluded_diagnostic_features
    ) | {"T_tec_hot_side_c"}
    leaked = sorted(banned & set(labeled.feature_ids))
    if leaked:
        raise BenchmarkError(
            f"labeled override includes prohibited/diagnostic fields: {leaked}"
        )
    seen: set[str] = set()
    for sample in labeled.samples:
        if sample.run_id not in development_runs:
            raise BenchmarkError(
                f"labeled override contains non-development run {sample.run_id!r}"
            )
        partition = fixture.split.partition_of(sample.run_id)
        if partition not in DEVELOPMENT_PARTITIONS:
            raise BenchmarkError(
                f"labeled override run {sample.run_id!r} is outside development"
            )
        if sample.partition != partition:
            raise BenchmarkError(
                f"labeled override run {sample.run_id!r} carries partition "
                f"{sample.partition!r}, not {partition!r}"
            )
        if fixture.split.group_of.get(sample.run_id) != sample.group_id:
            raise BenchmarkError(
                f"labeled override run {sample.run_id!r} carries a foreign group"
            )
        if sample.sample_identity in seen:
            raise BenchmarkError(
                f"duplicate sample identity {sample.sample_identity!r} in override"
            )
        seen.add(sample.sample_identity)
        if len(sample.features) != len(labeled.feature_ids):
            raise BenchmarkError("override sample width differs from its allowlist")
        if sample.y not in (0, 1):
            raise BenchmarkError("override labels must be binary")
    canonical = build_labeled_dataset(fixture, registry, config)
    canonical_rows = {
        (
            sample.run_id,
            sample.sample_identity,
            sample.anchor_t_s,
            sample.y,
            sample.series_id,
        )
        for sample in canonical.samples
    }
    override_rows = {
        (
            sample.run_id,
            sample.sample_identity,
            sample.anchor_t_s,
            sample.y,
            sample.series_id,
        )
        for sample in labeled.samples
    }
    if canonical_rows != override_rows:
        raise BenchmarkError(
            "labeled override changes canonical labels, anchors or sample identity"
        )
    if dict(canonical.excluded_by_run) != dict(labeled.excluded_by_run):
        raise BenchmarkError(
            "labeled override changes the canonical censored/untrusted exclusions"
        )


def run_grouped_benchmark(
    fixture: BenchmarkFixture,
    registry: FeatureRegistry,
    config: BenchmarkConfig,
    *,
    out_dir: Path | None = None,
    n_splits_override: int | None = None,
    labeled_override: LabeledDataset | None = None,
) -> tuple[BenchmarkResult, dict[str, XGBClassifier]]:
    if fixture.provenance not in (SOFTWARE_ONLY, SYNTHETIC_PROVENANCE):
        raise BenchmarkError("only synthetic fixtures may be benchmarked in W11")
    if any(
        trajectory.source_type != SOURCE_TYPE_SYNTHETIC
        for trajectory in fixture.trajectories
    ):
        raise BenchmarkError(
            "a physical trajectory was supplied to a synthetic benchmark fixture"
        )
    for trajectory in fixture.trajectories:
        if trajectory.run_id is None:
            raise BenchmarkError("a fixture trajectory has no run identity")
        if fixture.split.partition_of(trajectory.run_id) is None:
            raise BenchmarkError(
                f"fixture run {trajectory.run_id!r} is not partitioned; refusing "
                "to omit it silently"
            )
    labeled = (
        build_labeled_dataset(fixture, registry, config)
        if labeled_override is None
        else labeled_override
    )
    if labeled_override is not None:
        _validate_labeled_override(fixture, registry, config, labeled)
    runs_with_evaluable_labels = {sample.run_id for sample in labeled.samples}
    non_estimable_runs = [
        (run_id, labeled.excluded_by_run.get(run_id, {}))
        for run_id in labeled.run_ids
        if run_id not in runs_with_evaluable_labels
    ]
    if non_estimable_runs:
        raise NonEstimableRunError(non_estimable_runs)
    evaluation_end_by_run = {
        run_id: max(
            sample.anchor_t_s
            for sample in labeled.samples
            if sample.run_id == run_id
        )
        for run_id in labeled.run_ids
    }
    baselines: dict[str, _BaselineRun] = {}
    trajectory_by_run = {
        trajectory.run_id: trajectory
        for trajectory in fixture.development_trajectories
        if trajectory.run_id is not None
    }
    for run_id, trajectory in trajectory_by_run.items():
        series = fixture.series_by_run.get(run_id)
        if series is None:
            raise BenchmarkError(f"no critical-event series for {run_id!r}")
        baselines[run_id] = _prepare_baseline_run(
            trajectory,
            series,
            hardware_config_id=fixture.hardware_config_by_run[run_id],
            config=config,
            evaluation_end_s=evaluation_end_by_run[run_id],
        )
    evaluation_runs = build_evaluation_runs(
        fixture.development_trajectories,
        fixture.split,
        hardware_config_by_run=fixture.hardware_config_by_run,
    )
    n_splits = n_splits_override or config.cv.n_splits
    cv = make_grouped_folds(
        evaluation_runs,
        n_splits=n_splits,
        seed=config.cv.seed,
        min_train_groups=config.cv.min_train_groups,
        min_validation_groups=config.cv.min_validation_groups,
    )
    fold_runs: list[FoldRunResult] = []
    oof_payload: dict[str, dict[str, Any]] = {}
    baseline_rows: list[dict[str, Any]] = []
    models: dict[str, XGBClassifier] = {}
    for fold in cv.folds:
        validation_samples = [
            sample for sample in labeled.samples if sample.run_id in fold.validation_runs
        ]
        _add_baseline_method_rows(
            baseline_rows,
            fold=fold,
            validation_samples=validation_samples,
            baselines=baselines,
            config=config,
            censored_exclusions=sum(
                labeled.excluded_by_run.get(run_id, {}).get("CENSORED", 0)
                for run_id in fold.validation_runs
            ),
            untrusted_exclusions=sum(
                labeled.excluded_by_run.get(run_id, {}).get("UNTRUSTED_INFO", 0)
                for run_id in fold.validation_runs
            ),
        )
    for strategy in config.strategies:
        oof_scores: list[float] = []
        oof_labels: list[int] = []
        fold_values: list[MetricValue] = []
        fitted_folds = 0
        for fold in cv.folds:
            train_samples = [
                sample for sample in labeled.samples if sample.run_id in fold.train_runs
            ]
            validation_samples = [
                sample
                for sample in labeled.samples
                if sample.run_id in fold.validation_runs
            ]
            result, model = _fit_fold(
                fold=fold,
                strategy=strategy,
                train_samples=train_samples,
                validation_samples=validation_samples,
                config=config,
                feature_ids=labeled.feature_ids,
            )
            censored = sum(
                labeled.excluded_by_run.get(run_id, {}).get("CENSORED", 0)
                for run_id in fold.validation_runs
            )
            untrusted = sum(
                labeled.excluded_by_run.get(run_id, {}).get("UNTRUSTED_INFO", 0)
                for run_id in fold.validation_runs
            )
            result = FoldRunResult(
                **{
                    **result.__dict__,
                    "censored_exclusions": censored,
                    "untrusted_exclusions": untrusted,
                }
            )
            if model is not None:
                fitted_folds += 1
                models.setdefault(strategy, model)
                X_val, y_val = feature_matrix(validation_samples, labeled.feature_ids)
                scores = np.asarray(model.predict_proba(X_val)[:, 1], dtype=float)
                oof_scores.extend(float(value) for value in scores)
                oof_labels.extend(int(value) for value in y_val)
                fold_values.append(
                    MetricValue(
                        float(result.metrics["average_precision"]["value"])
                        if result.metrics["average_precision"]["value"] is not None
                        else None,
                        result.metrics["average_precision"]["reason"],
                    )
                )
                per_run_events = []
                for run_id in fold.validation_runs:
                    run_samples = [
                        sample
                        for sample in validation_samples
                        if sample.run_id == run_id
                    ]
                    run_scores = [
                        float(score)
                        for sample, score in zip(validation_samples, scores)
                        if sample.run_id == run_id
                    ]
                    if not run_samples:
                        continue
                    warning_samples = _warning_samples_from_scores(
                        run_samples, run_scores, threshold=config.risk_threshold
                    )
                    per_run_events.append(
                        _event_result(
                            trajectory=trajectory_by_run[run_id],
                            samples=warning_samples,
                            critical_events=baselines[run_id].event_inputs,
                            episode_policy=config.baseline.episode_policy(),
                            association_policy=config.baseline.association_policy(),
                            warning_definition=WARNING_DEFINITION_XGB,
                            evaluation_end_s=evaluation_end_by_run[run_id],
                            trusted_exposure_s=baselines[run_id].duration_s,
                            coverage_trustworthy=(
                                baselines[run_id].coverage_trustworthy
                            ),
                        )
                    )
                duration = sum(
                    baselines[run_id].duration_s for run_id in fold.validation_runs
                )
                untrusted_duration = sum(
                    baselines[run_id].untrusted_duration_s
                    for run_id in fold.validation_runs
                )
                event_summary = aggregate_event_results(
                    per_run_events,
                    duration_s=duration,
                    untrusted_duration_s=untrusted_duration,
                )
                result = FoldRunResult(
                    **{**result.__dict__, "event_metrics": event_summary}
                )
            else:
                fold_values.append(
                    MetricValue(
                        None,
                        result.reason or "FOLD_REFUSED_NO_PREDICTIONS",
                    )
                )
            fold_runs.append(result)
            _add_xgb_comparison_row(
                baseline_rows,
                fold=fold,
                validation_samples=validation_samples,
                xgb_result=result,
                baselines=baselines,
            )
        oof_payload[strategy] = _oof_payload(
            oof_labels,
            oof_scores,
            config,
            fold_values,
            folds_total=len(cv.folds),
            folds_fitted=fitted_folds,
        )
    status = fixture.status
    reason_codes = [status, fixture.provenance]
    if fixture.dataset_id.startswith("W10_"):
        reason_codes.append("TWO_DEVELOPMENT_GROUPS_ONLY")
    if any(item.status == FIT_STATUS_REFUSED for item in fold_runs):
        reason_codes.append("FOLD_FIT_REFUSED")
    if any(
        payload["status"] == OOF_UNDEFINED for payload in oof_payload.values()
    ):
        reason_codes.append("OOF_AP_UNDEFINED")
    model_artifact = None
    if models:
        first_strategy = config.strategies[0]
        model = models.get(first_strategy) or next(iter(models.values()))
        X_probe, _ = feature_matrix(labeled.samples[:5], labeled.feature_ids)
        model_artifact = _save_model_artifacts(
            model, out_dir=out_dir, probe_matrix=X_probe
        )
    result = BenchmarkResult(
        mode=fixture.dataset_id,
        status=status,
        provenance=fixture.provenance,
        dataset_id=fixture.dataset_id,
        fixture_version=fixture.fixture_version,
        config_sha256=config.config_sha256,
        registry_sha256=registry.schema_sha256,
        feature_ids=labeled.feature_ids,
        label_identity=dict(labeled.label_identity),
        cv=cv,
        labeled=labeled,
        fold_runs=tuple(fold_runs),
        oof=oof_payload,
        baseline_rows=tuple(baseline_rows),
        model_artifact=model_artifact,
        versions=package_versions(),
        split_identity={
            "seed": fixture.split.seed,
            "train_runs": list(fixture.split.train_runs),
            "validation_runs": list(fixture.split.validation_runs),
            "test_runs": list(fixture.split.test_runs),
            "pair_lineage": [dict(item) for item in fixture.split.pair_lineage],
            "test_partition_used": False,
        },
        limitations=fixture.limitations,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
    )
    return result, models


def _oof_payload(
    labels: Sequence[int],
    scores: Sequence[float],
    config: BenchmarkConfig,
    fold_values: Sequence[MetricValue],
    *,
    folds_total: int,
    folds_fitted: int,
) -> dict[str, Any]:
    base = {
        "fold_count_total": folds_total,
        "fold_count_fitted": folds_fitted,
        "fold_ap": aggregate_fold_ap(fold_values),
    }
    if folds_fitted < folds_total:
        return {
            **base,
            "status": OOF_UNDEFINED,
            "reason": "REFUSED_FOLDS_EXCLUDED_FROM_OOF",
        }
    if not labels:
        return {
            **base,
            "status": OOF_UNDEFINED,
            "reason": "NO_OUT_OF_FOLD_PREDICTIONS",
        }
    if len(set(labels)) < 2:
        return {
            **base,
            "status": OOF_UNDEFINED,
            "reason": "OOF_SINGLE_CLASS",
        }
    metrics = classification_metrics(
        list(labels), list(scores), threshold=config.risk_threshold
    )
    return {
        **base,
        "status": OOF_DEFINED,
        "metrics": metrics.to_dict(),
    }


def _add_baseline_method_rows(
    rows: list[dict[str, Any]],
    *,
    fold: Fold,
    validation_samples: Sequence[LabeledSample],
    baselines: Mapping[str, _BaselineRun],
    config: BenchmarkConfig,
    censored_exclusions: int,
    untrusted_exclusions: int,
) -> None:
    for method, score_map, event_result, threshold, comparison, version in (
        (
            "B0_THRESHOLD",
            "b0",
            "b0_events",
            float(config.raw["baseline"]["b0"]["threshold_c"]),
            "GT",
            "coldguard-w09-b0-threshold-v1",
        ),
        (
            "B1_HYSTERESIS",
            "b1",
            "b1_events",
            1.0,
            "GE",
            "coldguard-w09-b1-hysteresis-v1",
        ),
    ):
        pooled_samples: list[tuple[LabeledSample, float]] = []
        for run_id in fold.validation_runs:
            selected_map = getattr(baselines[run_id], f"{score_map}_scores")
            for sample in validation_samples:
                if sample.run_id != run_id:
                    continue
                score = selected_map.get(sample.anchor_t_s)
                if score is None or not math.isfinite(float(score)):
                    continue
                pooled_samples.append((sample, float(score)))
        pooled_metrics = (
            classification_metrics(
                [sample.y for sample, _ in pooled_samples],
                [score for _, score in pooled_samples],
                threshold=threshold,
                comparison=comparison,
            )
            if pooled_samples
            else None
        )
        sample_metrics = [pooled_metrics] if pooled_metrics is not None else []
        evaluable_events = [
            getattr(baselines[run_id], event_result)
            for run_id in fold.validation_runs
            if getattr(baselines[run_id], event_result) is not None
        ]
        not_evaluable = [
            run_id
            for run_id in fold.validation_runs
            if getattr(baselines[run_id], event_result) is None
        ]
        event_summary = aggregate_event_results(
            evaluable_events,
            duration_s=sum(
                baselines[run_id].duration_s
                for run_id in fold.validation_runs
                if getattr(baselines[run_id], event_result) is not None
            ),
            untrusted_duration_s=sum(
                baselines[run_id].untrusted_duration_s
                for run_id in fold.validation_runs
                if getattr(baselines[run_id], event_result) is not None
            ),
        )
        evaluability_reasons = list(event_summary["undefined_reasons"])
        if not_evaluable:
            evaluability_reasons.append("BASELINE_REPLAY_NOT_EVALUABLE")
        rows.append(
            {
                "method": method,
                "version": version,
                "fold_id": fold.fold_id,
                "run_groups": sorted(
                    {
                        sample.group_id
                        for sample in validation_samples
                        if sample.run_id in fold.validation_runs
                    }
                ),
                "validation_run_ids": list(fold.validation_runs),
                "baseline_evaluability": [
                    getattr(baselines[run_id], f"{score_map}_evaluability")
                    for run_id in fold.validation_runs
                ],
                "not_evaluable_runs": not_evaluable,
                "eligible_sample_count": sum(
                    metric.sample_count for metric in sample_metrics
                ),
                "eligible_critical_event_count": event_summary[
                    "eligible_critical_event_count"
                ],
                "censored_event_count": event_summary["censored_event_count"],
                "untrusted_event_count": event_summary["untrusted_event_count"],
                "trusted_exposure_s": event_summary["trusted_exposure_s"],
                "untrusted_exposure_s": event_summary["untrusted_exposure_s"],
                "coverage_trustworthy": event_summary["coverage_trustworthy"],
                "first_trusted_observation_by_run": [
                    baselines[run_id].first_trusted_observation_s
                    for run_id in fold.validation_runs
                ],
                "exposure_policy": TRUSTED_EXPOSURE_POLICY,
                "episode_cutoff_policy": EPISODE_CUTOFF_POLICY,
                "warning_episode_count": event_summary["warning_episode_count"],
                "matched_warning_episodes": event_summary[
                    "matched_warning_episodes"
                ],
                "unmatched_warnings": event_summary["unmatched_warnings"],
                "missed_critical_events": event_summary[
                    "missed_critical_events"
                ],
                "false_warning_episodes_per_run": event_summary[
                    "false_warning_episodes_per_run"
                ],
                "false_warning_episodes_per_hour": event_summary[
                    "false_warning_episodes_per_hour"
                ],
                "event_precision": event_summary["event_precision"],
                "event_recall": event_summary["event_recall"],
                "sample_ap": _combine_metric_values(
                    [metric.average_precision for metric in sample_metrics]
                ),
                "sample_precision": _combine_metric_values(
                    [metric.precision for metric in sample_metrics]
                ),
                "sample_recall": _combine_metric_values(
                    [metric.recall for metric in sample_metrics]
                ),
                "sample_f1": _combine_metric_values(
                    [metric.f1 for metric in sample_metrics]
                ),
                "sample_threshold": threshold,
                "sample_comparison": comparison,
                "sample_undefined_reasons": (
                    list(pooled_metrics.undefined_reasons)
                    if pooled_metrics is not None
                    else ["NO_BASELINE_SAMPLE_METRICS"]
                ),
                "xgb_sample_count": len(validation_samples),
                "sample_population_differs": (
                    pooled_metrics is None
                    or pooled_metrics.sample_count != len(validation_samples)
                ),
                "ewt": "NOT_ESTIMABLE",
                "ewt_reason_code": EWT_REASON_NO_COMMON_TRAJECTORY,
                "ewt_reason": EWT_TEXT,
                "aiw": "NOT_ESTIMABLE",
                "aiw_reason_code": AIW_REASON_MISSING_LATENCY_CHAIN,
                "aiw_reason": AIW_TEXT,
                "undefined_reasons": evaluability_reasons,
                "censored_exclusions": censored_exclusions,
                "untrusted_exclusions": untrusted_exclusions,
                "exclusion_reason_codes": [
                    reason
                    for reason, count in (
                        ("CENSORED_LABELS_EXCLUDED", censored_exclusions),
                        ("UNTRUSTED_LABELS_EXCLUDED", untrusted_exclusions),
                    )
                    if count
                ],
                "score_semantics": (
                    "representative temperature threshold"
                    if method == "B0_THRESHOLD"
                    else "reactive hysteresis ON state"
                ),
            }
        )


def _add_xgb_comparison_row(
    rows: list[dict[str, Any]],
    *,
    fold: Fold,
    validation_samples: Sequence[LabeledSample],
    xgb_result: FoldRunResult,
    baselines: Mapping[str, _BaselineRun],
) -> None:
    rows.append(
        {
            "method": f"XGBOOST_V1_{xgb_result.strategy}",
            "version": "coldguard-xgb-v1-development-v1",
            "fold_id": fold.fold_id,
            "run_groups": sorted(
                {
                    sample.group_id
                    for sample in validation_samples
                    if sample.run_id in fold.validation_runs
                }
            ),
            "validation_run_ids": list(fold.validation_runs),
            "eligible_sample_count": xgb_result.validation_sample_count,
            "eligible_critical_event_count": (
                xgb_result.event_metrics or {}
            ).get("eligible_critical_event_count"),
            "censored_event_count": (xgb_result.event_metrics or {}).get(
                "censored_event_count"
            ),
            "untrusted_event_count": (xgb_result.event_metrics or {}).get(
                "untrusted_event_count"
            ),
            "trusted_exposure_s": (xgb_result.event_metrics or {}).get(
                "trusted_exposure_s"
            ),
            "untrusted_exposure_s": (xgb_result.event_metrics or {}).get(
                "untrusted_exposure_s"
            ),
            "coverage_trustworthy": (xgb_result.event_metrics or {}).get(
                "coverage_trustworthy"
            ),
            "first_trusted_observation_by_run": [
                baselines[run_id].first_trusted_observation_s
                for run_id in fold.validation_runs
            ],
            "exposure_policy": TRUSTED_EXPOSURE_POLICY,
            "episode_cutoff_policy": EPISODE_CUTOFF_POLICY,
            "warning_episode_count": (xgb_result.event_metrics or {}).get(
                "warning_episode_count"
            ),
            "matched_warning_episodes": (xgb_result.event_metrics or {}).get(
                "matched_warning_episodes"
            ),
            "unmatched_warnings": (xgb_result.event_metrics or {}).get(
                "unmatched_warnings"
            ),
            "missed_critical_events": (xgb_result.event_metrics or {}).get(
                "missed_critical_events"
            ),
            "false_warning_episodes_per_run": (xgb_result.event_metrics or {}).get(
                "false_warning_episodes_per_run"
            ),
            "false_warning_episodes_per_hour": (
                xgb_result.event_metrics or {}
            ).get("false_warning_episodes_per_hour"),
            "event_precision": (xgb_result.event_metrics or {}).get(
                "event_precision"
            ),
            "event_recall": (xgb_result.event_metrics or {}).get("event_recall"),
            "sample_ap": (
                xgb_result.metrics["average_precision"]["value"]
                if xgb_result.metrics is not None
                else None
            ),
            "sample_precision": (
                xgb_result.metrics["precision"]["value"]
                if xgb_result.metrics is not None
                else None
            ),
            "sample_recall": (
                xgb_result.metrics["recall"]["value"]
                if xgb_result.metrics is not None
                else None
            ),
            "sample_f1": (
                xgb_result.metrics["f1"]["value"]
                if xgb_result.metrics is not None
                else None
            ),
            "ewt": "NOT_ESTIMABLE",
            "ewt_reason_code": EWT_REASON_NO_COMMON_TRAJECTORY,
            "ewt_reason": EWT_TEXT,
            "aiw": "NOT_ESTIMABLE",
            "aiw_reason_code": AIW_REASON_MISSING_LATENCY_CHAIN,
            "aiw_reason": AIW_TEXT,
            "undefined_reasons": (xgb_result.event_metrics or {}).get(
                "undefined_reasons", []
            ),
            "censored_exclusions": xgb_result.censored_exclusions,
            "untrusted_exclusions": xgb_result.untrusted_exclusions,
            "exclusion_reason_codes": [
                reason
                for reason, count in (
                    ("CENSORED_LABELS_EXCLUDED", xgb_result.censored_exclusions),
                    ("UNTRUSTED_LABELS_EXCLUDED", xgb_result.untrusted_exclusions),
                )
                if count
            ],
            "score_semantics": "risk_score (not calibrated_probability)",
        }
    )


def _combine_metric_values(values: Sequence[MetricValue]) -> float | None:
    if not values or any(not value.defined for value in values):
        return None
    return sum(value.value for value in values if value.value is not None) / len(values)


def package_versions() -> dict[str, str]:
    import pandas
    import sklearn

    return {
        "python": "3.12",
        "xgboost": xgboost.__version__,
        "scikit_learn": sklearn.__version__,
        "numpy": np.__version__,
        "pandas": pandas.__version__,
    }


def _save_model_artifacts(
    model: XGBClassifier, *, out_dir: Path | None, probe_matrix: np.ndarray
) -> dict[str, Any]:
    base = Path(out_dir) if out_dir is not None else Path(".")
    base.mkdir(parents=True, exist_ok=True)
    stems = {
        "ubj": base / "model-synthetic-smoke.ubj",
        "json": base / "model-synthetic-smoke.json",
    }
    for path in stems.values():
        model.save_model(str(path))
    loaded = XGBClassifier()
    loaded.load_model(str(stems["ubj"]))
    original = np.asarray(model.predict_proba(probe_matrix)[:, 1], dtype=float)
    restored = np.asarray(loaded.predict_proba(probe_matrix)[:, 1], dtype=float)
    if not np.allclose(original, restored, rtol=0.0, atol=1e-12):
        raise BenchmarkError("saved model predictions changed after load")
    return {
        "provenance": SYNTHETIC_PROVENANCE,
        "classification": SYNTHETIC_PROVENANCE,
        "files": {
            name: {"file": path.name, "sha256": _sha256(path.read_bytes())}
            for name, path in stems.items()
        },
        "load_predictions_match": True,
        "promotable_to_physical_model": False,
    }


# ---------------------------------------------------------------------------
# Real admission gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    mode: str
    gate: str
    reasons: tuple[str, ...]
    admitted_run_ids: tuple[str, ...]
    evidence: Mapping[str, Any]
    manifest_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "mode": self.mode,
            "gate": self.gate,
            "reasons": list(self.reasons),
            "admitted_run_ids": list(self.admitted_run_ids),
            "evidence": dict(self.evidence),
            "manifest_sha256": self.manifest_sha256,
        }


def load_w08_manifest(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BenchmarkError("W08 manifest root must be a mapping")
    gate = payload.get("physical_gate")
    if not isinstance(gate, dict) or gate.get("observed_status") not in (
        "GREEN",
        "YELLOW",
        "RED",
    ):
        raise BenchmarkError("W08 manifest lacks a recognised physical gate")
    evidence = gate.get("evidence_sha256")
    if not isinstance(evidence, list) or not evidence:
        raise BenchmarkError("W08 manifest lacks bound evidence hashes")
    runs = payload.get("runs")
    if not isinstance(runs, list) or not runs:
        raise BenchmarkError("W08 manifest lacks run-validation receipts")
    return payload


def assess_real_admission(
    w08: Mapping[str, Any],
    *,
    capture: Capture | None,
    capture_sha256: str | None,
    split_plan: Mapping[str, Any] | None = None,
) -> AdmissionDecision:
    reasons: list[str] = []
    gate = str(w08["physical_gate"]["observed_status"])
    evidence_hashes = {str(item) for item in w08["physical_gate"]["evidence_sha256"]}
    receipts = list(w08["runs"])
    admitted: list[str] = []
    source_receipts: list[dict[str, Any]] = []
    if w08.get("data_origin") != "MEASURED_PHYSICAL_DATA":
        reasons.append("DATA_ORIGIN_NOT_MEASURED_PHYSICAL")
    if w08.get("synthetic_control") is not False:
        reasons.append("SYNTHETIC_CONTROL_CANNOT_ADMIT_REAL_TRAINING")
    if gate != "GREEN":
        reasons.append(f"PHYSICAL_GATE_{gate}")
    if capture is None or not capture_sha256:
        reasons.append("CAPTURE_NOT_SUPPLIED")
        reasons.append("SOURCE_HASH_NOT_BOUND_BY_W08")
    else:
        if capture_sha256 not in evidence_hashes:
            reasons.append("SOURCE_HASH_NOT_BOUND_BY_W08")
        source_receipts = [
            receipt
            for receipt in receipts
            if str(receipt.get("source_sha256") or "") == capture_sha256
        ]
        if not source_receipts:
            reasons.append("NO_W08_RECEIPT_FOR_SOURCE")
        if capture.run.run_id is None:
            reasons.append("RUN_IDENTITY_UNRESOLVED")
        if capture.run.device_id is None:
            reasons.append("DEVICE_IDENTITY_MISSING")
        if capture.time.domain != "EVENT_UTC":
            reasons.append("ABSOLUTE_EVENT_TIME_NOT_EVIDENCED")
    split_plan = split_plan or w08.get("split_plan") or {}
    development_runs = set(split_plan.get("development_runs", ()) or ())
    p3 = set(split_plan.get("P3_future_locked_planning_candidates", ()) or ())
    if split_plan.get("feasibility") in (None, "NOT_FEASIBLE", ""):
        reasons.append("REAL_DEVELOPMENT_SPLIT_NOT_FEASIBLE")
    if not development_runs:
        reasons.append("NO_ADMITTED_DEVELOPMENT_SPLIT_MEMBERS")
    policy = w08.get("completeness_policy") or {}
    thresholds = policy.get("thresholds") or []
    for threshold in thresholds:
        if threshold.get("threshold_status") != "FROZEN":
            reasons.append("COMPLETENESS_POLICY_NOT_FROZEN")
            break
        if not str(threshold.get("freeze_evidence") or "").strip():
            reasons.append("COMPLETENESS_FREEZE_EVIDENCE_MISSING")
            break
    for receipt in source_receipts:
        run_id = receipt.get("run_id")
        reasons_for_run: list[str] = []
        if not run_id:
            reasons_for_run.append("RUN_IDENTITY_UNRESOLVED")
        if receipt.get("device_id") is None:
            reasons_for_run.append("DEVICE_IDENTITY_MISSING")
        if receipt.get("boot_id") in (None, ""):
            reasons_for_run.append("BOOT_IDENTITY_MISSING")
        if str(receipt.get("a_ledger_verdict") or "").upper() != "VALID":
            reasons_for_run.append("A_LEDGER_NOT_VALID")
        if receipt.get("eligibility") != "ELIGIBLE_FOR_DATASET":
            reasons_for_run.append("NOT_ELIGIBLE_FOR_PREDICTIVE_DATASET")
        if receipt.get("admission_highest_stage") != "ELIGIBLE_FOR_PREDICTIVE_DATASET":
            reasons_for_run.append("ADMISSION_STAGE_BELOW_PREDICTIVE_DATASET")
        if receipt.get("hardware_config_status") != "VERIFIED":
            reasons_for_run.append("HARDWARE_CONFIG_NOT_VERIFIED")
        if receipt.get("calibration_status") != "VERIFIED":
            reasons_for_run.append("CALIBRATION_NOT_VERIFIED")
        if receipt.get("time_domain") != "EVENT_UTC":
            reasons_for_run.append("TIME_DOMAIN_NOT_ABSOLUTE_UTC")
        if receipt.get("clock_sync_status") in (None, "", "NOT_EVIDENCED"):
            reasons_for_run.append("CLOCK_SYNC_NOT_EVIDENCED")
        if str(receipt.get("scenario_status") or "") in ("", "CANDIDATE_NOT_CERTIFIED"):
            reasons_for_run.append("SCENARIO_NOT_CERTIFIED")
        gate_scenario = str(w08["physical_gate"].get("scenario") or "")
        if gate_scenario and not str(receipt.get("scenario_id") or "").upper().startswith(
            gate_scenario.upper()
        ):
            reasons_for_run.append("SCENARIO_NOT_IN_GATE_POPULATION")
        for check in receipt.get("checks", ()) or ():
            if (
                check.get("severity") == "BLOCKING"
                and check.get("status") in ("FAIL", "NOT_EVALUABLE")
            ):
                reasons_for_run.append("BLOCKING_RUN_VALIDATION_FAILURE")
                break
        if run_id and run_id not in development_runs:
            reasons_for_run.append("RUN_NOT_IN_GROUPED_DEVELOPMENT_SPLIT")
        if run_id and run_id in p3:
            reasons_for_run.append("RUN_IS_LOCKED_TEST_PLANNING_CANDIDATE")
        reasons.extend(reasons_for_run)
        if run_id and not reasons_for_run:
            admitted.append(str(run_id))
    if len(set(admitted)) < 2:
        reasons.append("INSUFFICIENT_ADMITTED_REAL_RUNS_FOR_GROUPED_CV")
    admitted = sorted(set(admitted))
    reasons = list(dict.fromkeys(reasons))
    return AdmissionDecision(
        allowed=not reasons,
        mode="real-development",
        gate=gate,
        reasons=tuple(reasons),
        admitted_run_ids=tuple(admitted),
        evidence={
            "physical_gate": gate,
            "source_hash_bound": bool(capture_sha256 in evidence_hashes),
            "source_receipt_count": len(source_receipts),
            "eligible_run_count": len(admitted),
            "split_feasibility": split_plan.get("feasibility"),
            "data_origin": w08.get("data_origin"),
            "capture_run_identity": (
                capture.run.run_id_status if capture is not None else None
            ),
            "capture_time_domain": (
                capture.time.domain if capture is not None else None
            ),
        },
        manifest_sha256=_canonical_sha(dict(w08)),
    )


def real_development_status(
    w08: Mapping[str, Any],
    *,
    capture: Capture | None,
    capture_sha256: str | None,
) -> dict[str, Any]:
    decision = assess_real_admission(
        w08, capture=capture, capture_sha256=capture_sha256
    )
    reasons = list(decision.reasons)
    if decision.allowed:
        reasons.append("REAL_TRAINING_EXECUTION_NOT_IMPLEMENTED_IN_W11")
    return {
        "MODE": "real-development",
        "PHYSICAL_GATE_B": decision.gate,
        "ELIGIBLE_RUNS": len(decision.admitted_run_ids),
        "TRAINING_EXECUTED": "NO",
        "BENCHMARK_STATUS": REAL_NOT_FEASIBLE,
        "REAL_DEVELOPMENT_SPLIT": (
            "FEASIBLE" if decision.allowed else REAL_NOT_FEASIBLE
        ),
        "REAL_XGBOOST_BENCHMARK": "NOT_ESTABLISHED",
        "REAL_BASELINE_COMPARISON": "NOT_ESTABLISHED",
        "REAL_EWT": "NOT_ESTIMABLE",
        "REAL_AIW": "NOT_ESTIMABLE",
        "REAL_EWT_REASON_CODE": EWT_REASON_NO_COMMON_TRAJECTORY,
        "REAL_AIW_REASON_CODE": AIW_REASON_MISSING_LATENCY_CHAIN,
        "REASONS": reasons,
        "ADMISSION": decision.to_dict(),
    }
