"""W11 grouped development evaluation (B-W11-01 / B-W11-03).

The scientific unit is the A-validated physical run, never a telemetry row or
a rolling window. A pair's arms form one effective group. Folds are built
after run-level partitioning and before any feature window is generated; the
fold assignment is deterministic for a fixed (runs, seed, n_splits).

Metrics never substitute a number for an undefined scientific quantity: a
single-class validation fold yields ``None`` plus an explicit reason, and an
eventless fold is not a zero-failure observation.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_curve, roc_auc_score

DEVELOPMENT_PARTITIONS = ("train", "validation")
LOCKED_TEST_PARTITION = "test"

PREDICTIVE_CONTROLLER_IDS = frozenset(
    {"CONTROLLER-B", "CONTROLLER-B-PREDICTIVE", "PREDICTIVE_CONTROLLER_B"}
)

STATUS_DEFINED = "DEFINED"
STATUS_UNDEFINED = "UNDEFINED"


class GroupedEvaluationError(ValueError):
    """A grouped evaluation would leak a run, pair or physical source."""


class GroupingLeakageError(GroupedEvaluationError):
    """The requested assignment splits one independent group."""


class FoldSupportError(GroupedEvaluationError):
    """A fold has insufficient groups or class support for the request."""


class PreprocessingLeakageError(GroupedEvaluationError):
    """A transform was fitted on validation or test groups."""


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    group_id: str
    pair_id: str | None
    source_sha256: str
    physical_source_key: str
    scenario_id: str
    controller_id: str
    hardware_config_id: str
    partition: str

    @property
    def is_development(self) -> bool:
        return self.partition in DEVELOPMENT_PARTITIONS


@dataclass(frozen=True)
class Fold:
    fold_id: str
    train_groups: tuple[str, ...]
    validation_groups: tuple[str, ...]
    train_runs: tuple[str, ...]
    validation_runs: tuple[str, ...]
    pair_lineage: tuple[dict[str, Any], ...]

    def to_manifest(self, seed: int) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "train_group_ids": list(self.train_groups),
            "validation_group_ids": list(self.validation_groups),
            "train_run_ids": list(self.train_runs),
            "validation_run_ids": list(self.validation_runs),
            "pair_lineage": [dict(item) for item in self.pair_lineage],
            "seed": seed,
        }


@dataclass(frozen=True)
class GroupedCV:
    folds: tuple[Fold, ...]
    effective_groups: int
    n_splits: int
    seed: int
    grouping_key: str
    runs: tuple[EvaluationRun, ...]

    def to_manifest(self) -> dict[str, Any]:
        return {
            "grouping_key": self.grouping_key,
            "effective_independent_groups": self.effective_groups,
            "n_splits": self.n_splits,
            "seed": self.seed,
            "folds": [fold.to_manifest(self.seed) for fold in self.folds],
        }


@dataclass(frozen=True)
class MetricValue:
    value: float | None
    reason: str | None = None

    @property
    def defined(self) -> bool:
        return self.value is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "status": STATUS_DEFINED if self.defined else STATUS_UNDEFINED,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ClassificationMetrics:
    threshold: float
    sample_count: int
    positive_count: int
    negative_count: int
    average_precision: MetricValue
    roc_auc: MetricValue
    precision: MetricValue
    recall: MetricValue
    f1: MetricValue
    confusion: dict[str, int]
    pr_curve_points: int | None
    undefined_reasons: tuple[str, ...]
    comparison: str = "GE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "comparison": self.comparison,
            "sample_count": self.sample_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "average_precision": self.average_precision.to_dict(),
            "roc_auc": self.roc_auc.to_dict(),
            "precision": self.precision.to_dict(),
            "recall": self.recall.to_dict(),
            "f1": self.f1.to_dict(),
            "confusion_matrix": dict(self.confusion),
            "pr_curve_points": self.pr_curve_points,
            "undefined_reasons": list(self.undefined_reasons),
        }


def build_evaluation_runs(
    trajectories: Sequence[Any],
    split: Any,
    *,
    hardware_config_by_run: Mapping[str, str],
) -> tuple[EvaluationRun, ...]:
    """Build run-level groups from a grouped split; never from rows/windows."""
    runs: list[EvaluationRun] = []
    seen_runs: set[str] = set()
    source_owners: dict[str, str] = {}
    source_keys: dict[str, str] = {}
    for trajectory in trajectories:
        run_id = trajectory.run_id
        if run_id is None:
            raise GroupingLeakageError(
                "a trajectory without a resolved run identity cannot enter a "
                "grouped benchmark"
            )
        if run_id in seen_runs:
            raise GroupingLeakageError(f"duplicate run identity {run_id!r}")
        seen_runs.add(run_id)
        partition = split.partition_of(run_id)
        if partition is None:
            raise GroupingLeakageError(
                f"run {run_id!r} is not partitioned; refusing an unassigned run"
            )
        if partition == LOCKED_TEST_PARTITION:
            raise GroupingLeakageError(
                f"run {run_id!r} belongs to the locked test partition; W11 "
                "cannot inspect or train on it"
            )
        if partition not in DEVELOPMENT_PARTITIONS:
            raise GroupingLeakageError(
                f"run {run_id!r} has unknown partition {partition!r}"
            )
        if trajectory.controller_id in PREDICTIVE_CONTROLLER_IDS:
            raise GroupingLeakageError(
                f"run {run_id!r} is a predictive closed-loop trajectory; an "
                "interventional run cannot enter observational training"
            )
        source = trajectory.source_sha256
        key = trajectory.physical_source_key
        if source in source_owners and source_owners[source] != run_id:
            raise GroupingLeakageError(
                f"physical source {source!r} is claimed by runs "
                f"{source_owners[source]!r} and {run_id!r}; an export view or "
                "renamed file never creates a second independent run"
            )
        if key in source_keys and source_keys[key] != run_id:
            raise GroupingLeakageError(
                f"physical source key {key!r} is claimed by runs "
                f"{source_keys[key]!r} and {run_id!r}"
            )
        source_owners[source] = run_id
        source_keys[key] = run_id
        group_id = split.group_of.get(run_id)
        if not group_id:
            raise GroupingLeakageError(
                f"run {run_id!r} has no grouped split membership"
            )
        pair_id = _pair_id_from_lineage(split, run_id)
        hardware = hardware_config_by_run.get(run_id)
        if not hardware:
            raise GroupingLeakageError(
                f"run {run_id!r} has no hardware/config identity"
            )
        runs.append(
            EvaluationRun(
                run_id=run_id,
                group_id=group_id,
                pair_id=pair_id,
                source_sha256=source,
                physical_source_key=key,
                scenario_id=trajectory.scenario_id or "UNKNOWN_SCENARIO",
                controller_id=trajectory.controller_id or "OBSERVATIONAL",
                hardware_config_id=hardware,
                partition=partition,
            )
        )
    if not runs:
        raise GroupingLeakageError("no development runs supplied")
    accepted_hardware = {run.hardware_config_id for run in runs}
    if len(accepted_hardware) > 1:
        raise GroupingLeakageError(
            "development runs carry more than one hardware/config lineage "
            f"{sorted(accepted_hardware)}; comparability is not established"
        )
    return tuple(sorted(runs, key=lambda run: run.run_id))


def _pair_id_from_lineage(split: Any, run_id: str) -> str | None:
    for entry in getattr(split, "pair_lineage", ()):
        if run_id in entry.get("run_ids", ()):
            return entry.get("pair_id")
    return None


def validate_run_population(runs: Sequence[EvaluationRun]) -> None:
    """One physical source and one run identity may appear exactly once."""
    seen_runs: set[str] = set()
    source_owner: dict[str, str] = {}
    source_key_owner: dict[str, str] = {}
    for run in runs:
        if not run.run_id:
            raise GroupingLeakageError("a run without an identity is not a group")
        if run.run_id in seen_runs:
            raise GroupingLeakageError(f"duplicate run identity {run.run_id!r}")
        seen_runs.add(run.run_id)
        if run.partition == LOCKED_TEST_PARTITION:
            raise GroupingLeakageError(
                f"run {run.run_id!r} is a locked-test run"
            )
        if run.partition not in DEVELOPMENT_PARTITIONS:
            raise GroupingLeakageError(
                f"run {run.run_id!r} has non-development partition {run.partition!r}"
            )
        if run.source_sha256 in source_owner and source_owner[run.source_sha256] != run.run_id:
            raise GroupingLeakageError(
                f"physical source {run.source_sha256!r} is claimed by "
                f"{source_owner[run.source_sha256]!r} and {run.run_id!r}"
            )
        source_owner[run.source_sha256] = run.run_id
        if run.physical_source_key in source_key_owner and source_key_owner[
            run.physical_source_key
        ] != run.run_id:
            raise GroupingLeakageError(
                f"physical source key {run.physical_source_key!r} is claimed by "
                f"two run identities"
            )
        source_key_owner[run.physical_source_key] = run.run_id


def make_grouped_folds(
    runs: Sequence[EvaluationRun],
    *,
    n_splits: int,
    seed: int,
    min_train_groups: int = 1,
    min_validation_groups: int = 1,
) -> GroupedCV:
    """Deterministic, pair-preserving grouped K-fold assignment.

    This is a documented equivalent of ``GroupKFold``: whole effective groups
    are shuffled once and dealt round-robin into validation shards. The same
    seed reproduces the exact assignment.
    """
    validate_run_population(runs)
    if n_splits < 2:
        raise FoldSupportError("n_splits must be at least 2")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise FoldSupportError("seed must be an explicit integer")
    group_members: dict[str, list[str]] = {}
    for run in runs:
        group_members.setdefault(run.group_id, []).append(run.run_id)
    group_ids = sorted(group_members)
    if n_splits > len(group_ids):
        raise FoldSupportError(
            f"requested {n_splits} folds but only {len(group_ids)} effective "
            "independent groups exist; fold count may never exceed groups"
        )
    shuffled = list(group_ids)
    random.Random(seed).shuffle(shuffled)
    validation_shards = [shuffled[index::n_splits] for index in range(n_splits)]
    folds: list[Fold] = []
    for index, validation_groups in enumerate(validation_shards):
        validation_set = set(validation_groups)
        train_groups = [group for group in group_ids if group not in validation_set]
        if len(train_groups) < min_train_groups:
            raise FoldSupportError(
                f"fold {index + 1} has {len(train_groups)} training groups, "
                f"below the configured minimum {min_train_groups}"
            )
        if len(validation_groups) < min_validation_groups:
            raise FoldSupportError(
                f"fold {index + 1} has {len(validation_groups)} validation "
                f"groups, below the configured minimum {min_validation_groups}"
            )
        train_runs = sorted(
            run_id for group in train_groups for run_id in group_members[group]
        )
        validation_runs = sorted(
            run_id for group in validation_groups for run_id in group_members[group]
        )
        if set(train_runs) & set(validation_runs):
            raise GroupingLeakageError(
                f"fold {index + 1} shares runs between train and validation"
            )
        pair_lineage = tuple(
            {
                "group_id": group,
                "run_ids": sorted(group_members[group]),
                "partition": (
                    "validation" if group in validation_set else "train"
                ),
            }
            for group in sorted(group_ids)
            if len(group_members[group]) > 1
        )
        folds.append(
            Fold(
                fold_id=f"F{index + 1}",
                train_groups=tuple(sorted(train_groups)),
                validation_groups=tuple(sorted(validation_groups)),
                train_runs=tuple(train_runs),
                validation_runs=tuple(validation_runs),
                pair_lineage=pair_lineage,
            )
        )
    validate_folds(folds, runs)
    return GroupedCV(
        folds=tuple(folds),
        effective_groups=len(group_ids),
        n_splits=n_splits,
        seed=seed,
        grouping_key="run_id + pair_id (one effective group per pair)",
        runs=tuple(sorted(runs, key=lambda run: run.run_id)),
    )


def validate_folds(folds: Sequence[Fold], runs: Sequence[EvaluationRun]) -> None:
    """Fail closed on disjointness, pair, source and locked-test violations."""
    by_run = {run.run_id: run for run in runs}
    all_runs = set(by_run)
    for fold in folds:
        train = set(fold.train_runs)
        validation = set(fold.validation_runs)
        if train & validation:
            raise GroupingLeakageError(
                f"{fold.fold_id}: train and validation runs overlap"
            )
        if train | validation != all_runs:
            raise GroupingLeakageError(
                f"{fold.fold_id}: fold does not cover the development population "
                "exactly once"
            )
        if any(by_run[run_id].partition == LOCKED_TEST_PARTITION for run_id in train | validation):
            raise GroupingLeakageError(f"{fold.fold_id}: locked test run present")
        train_groups = {by_run[run_id].group_id for run_id in train}
        validation_groups = {by_run[run_id].group_id for run_id in validation}
        if train_groups & validation_groups:
            raise GroupingLeakageError(
                f"{fold.fold_id}: an effective group straddles train/validation"
            )
        for group_id in train_groups | validation_groups:
            members = {
                run_id for run_id, run in by_run.items() if run.group_id == group_id
            }
            if not members <= (train | validation):
                raise GroupingLeakageError(
                    f"{fold.fold_id}: group {group_id!r} is only partly assigned"
                )
            sides = {
                "train" if member in train else "validation" for member in members
            }
            if len(sides) != 1:
                raise GroupingLeakageError(
                    f"{fold.fold_id}: pair group {group_id!r} straddles folds"
                )
        pair_sides: dict[str, set[str]] = {}
        for run_id in train | validation:
            pair_id = by_run[run_id].pair_id
            if pair_id is not None:
                pair_sides.setdefault(pair_id, set()).add(
                    "train" if run_id in train else "validation"
                )
        straddled_pairs = sorted(
            pair_id for pair_id, sides in pair_sides.items() if len(sides) > 1
        )
        if straddled_pairs:
            raise GroupingLeakageError(
                f"{fold.fold_id}: pair lineage straddles train/validation: "
                f"{straddled_pairs}"
            )
        sources = [by_run[run_id].source_sha256 for run_id in train | validation]
        if len(sources) != len(set(sources)):
            raise GroupingLeakageError(
                f"{fold.fold_id}: duplicate physical source inside the fold"
            )


def assert_train_only_fit(
    train_groups: Iterable[str], fit_groups: Iterable[str]
) -> None:
    """A preprocessing transform may only fit on training groups."""
    train = set(train_groups)
    fit = set(fit_groups)
    if not fit <= train:
        illegal = sorted(fit - train)
        raise PreprocessingLeakageError(
            "preprocessing fit population includes non-training groups "
            f"{illegal}; validation and test data may never fit a transform"
        )


def classification_metrics(
    y_true: Sequence[int],
    y_score: Sequence[float],
    *,
    threshold: float,
    comparison: str = "GE",
) -> ClassificationMetrics:
    if comparison not in ("GT", "GE"):
        raise GroupedEvaluationError("comparison must be GT or GE")
    if len(y_true) != len(y_score):
        raise GroupedEvaluationError("label and score lengths differ")
    if not y_true:
        raise GroupedEvaluationError("no labelled samples supplied")
    labels = np.asarray([int(value) for value in y_true], dtype=int)
    if any(value not in (0, 1) for value in labels):
        raise GroupedEvaluationError("labels must be 0 or 1")
    scores = np.asarray([float(value) for value in y_score], dtype=float)
    if not np.all(np.isfinite(scores)):
        raise GroupedEvaluationError("risk scores must be finite")
    positive = int(labels.sum())
    negative = int(len(labels) - positive)
    predicted = scores > threshold if comparison == "GT" else scores >= threshold
    tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
    undefined: list[str] = []

    if positive == 0 or negative == 0:
        reason = (
            "SINGLE_CLASS_VALIDATION_NO_POSITIVES"
            if positive == 0
            else "SINGLE_CLASS_VALIDATION_NO_NEGATIVES"
        )
        ap = MetricValue(None, reason)
        auc = MetricValue(None, reason)
        undefined.append(reason)
        curve_points: int | None = None
    else:
        ap = MetricValue(float(average_precision_score(labels, scores)))
        auc = MetricValue(float(roc_auc_score(labels, scores)))
        pr_precision, pr_recall, _ = precision_recall_curve(labels, scores)
        curve_points = int(len(pr_precision))

    predicted_positive = int(tp + fp)
    if predicted_positive == 0:
        precision = MetricValue(None, "NO_PREDICTED_POSITIVES")
        undefined.append("NO_PREDICTED_POSITIVES")
    else:
        precision = MetricValue(float(tp / predicted_positive))
    if positive == 0:
        recall = MetricValue(None, "NO_POSITIVE_LABELS")
        undefined.append("NO_POSITIVE_LABELS")
    else:
        recall = MetricValue(float(tp / positive))
    if not precision.defined or not recall.defined:
        f1 = MetricValue(
            None,
            "F1_UNDEFINED_WHEN_PRECISION_OR_RECALL_UNDEFINED",
        )
        undefined.append("F1_UNDEFINED_WHEN_PRECISION_OR_RECALL_UNDEFINED")
    elif precision.value + recall.value == 0:
        f1 = MetricValue(0.0)
    else:
        f1 = MetricValue(
            float(2 * precision.value * recall.value / (precision.value + recall.value))
        )
    return ClassificationMetrics(
        threshold=threshold,
        sample_count=int(len(labels)),
        positive_count=positive,
        negative_count=negative,
        average_precision=ap,
        roc_auc=auc,
        precision=precision,
        recall=recall,
        f1=f1,
        confusion={"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        pr_curve_points=curve_points,
        undefined_reasons=tuple(dict.fromkeys(undefined)),
        comparison=comparison,
    )


def aggregate_fold_ap(fold_values: Sequence[MetricValue]) -> dict[str, Any]:
    """Preserve every fold and report instability; never fabricate an OOF AP."""
    if not fold_values:
        return {
            "status": STATUS_UNDEFINED,
            "reason": "NO_FOLDS",
            "fold_values": [],
        }
    missing = [item.reason for item in fold_values if not item.defined]
    finite = [item.value for item in fold_values if item.defined]
    if missing:
        return {
            "status": STATUS_UNDEFINED,
            "reason": "AT_LEAST_ONE_FOLD_AP_UNDEFINED",
            "undefined_fold_reasons": missing,
            "defined_values": finite,
        }
    mean = sum(finite) / len(finite)  # type: ignore[arg-type]
    variance = (
        sum((value - mean) ** 2 for value in finite) / len(finite)
        if len(finite) > 1
        else 0.0
    )
    return {
        "status": STATUS_DEFINED,
        "fold_values": finite,
        "mean": mean,
        "min": min(finite),
        "max": max(finite),
        "std": math.sqrt(variance),
        "instability_range": max(finite) - min(finite),
    }
