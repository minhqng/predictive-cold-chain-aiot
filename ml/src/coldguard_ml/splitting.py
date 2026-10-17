"""Leakage-safe grouped splitting (Doc ``03`` §§46–49; Doc ``00`` §5.3).

Contract rules implemented here:

* split happens BEFORE any window exists (``03`` §46; ``05B`` §12): the
  function takes runs, not rows, and returns run assignments;
* the grouping unit is ``run_id`` at minimum (``03`` §47) — one run's rows
  and windows can never straddle partitions;
* runs that share a ``pair_id`` form a single effective group (A/B arms and
  near-duplicate executions stay together — ``03`` §123 last item,
  register LRK-08); they are additionally recorded as pair lineage in the
  manifest output;
* configuration/runs metadata does NOT merge groups across the rig: for the
  single-rig dataset every run shares one ``hardware_config_id``; that
  value is comparability metadata (LRK-15) recorded in the split manifest,
  never a split axis;
* predictive (interventional) runs are excluded from the core predictive
  dataset unless the caller explicitly tags the artifact variant (LRK-09,
  ``03`` §45); the controller-id mapping is caller-supplied — no enum is
  invented here;
* physically invalid runs are dropped with their recorded reason — they are
  never silently re-validated downstream (Doc ``01`` §33 / §45);
* every partition must own at least ``min_groups_per_partition`` independent
  groups; otherwise an explicit ``SplitError`` is raised (no silent leakage);
* the assignment is deterministic given (input, config, seed) and records
  the seed it consumed (convention §11 seed policy).
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import SplitError

__all__ = [
    "RunInfo",
    "SplitProportions",
    "SplitConfig",
    "ExcludedRun",
    "SplitResult",
    "split_runs",
    "PARTITIONS",
]

PARTITIONS: tuple[str, ...] = ("train", "validation", "test")

REASON_INVALID_RUN = "invalid-run"
REASON_PREDICTIVE_CLOSED_LOOP = "predictive-closed-loop"


@dataclass(frozen=True)
class RunInfo:
    """Run-level metadata required to place a run (W01 §11 experiment key)."""

    run_id: str
    scenario_id: str
    controller_id: str
    pair_id: str | None = None
    hardware_config_id: str | None = None
    is_valid: bool = True
    invalid_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.run_id or not self.scenario_id or not self.controller_id:
            raise SplitError(
                "RunInfo requires non-empty run_id, scenario_id and controller_id "
                "(experiment key: run_id + scenario_id + controller_id)"
            )
        if not self.is_valid and not (self.invalid_reason or "").strip():
            raise SplitError(
                f"run {self.run_id!r} marked invalid requires invalid_reason "
                "(A's invalid-run ledger, Doc `01` §33)"
            )


@dataclass(frozen=True)
class SplitProportions:
    """Requested partition proportions (must be positive and sum to 1)."""

    train: float
    validation: float
    test: float

    def __post_init__(self) -> None:
        parts = {"train": self.train, "validation": self.validation, "test": self.test}
        for name, value in parts.items():
            if not (isinstance(value, (int, float)) and value > 0):
                raise SplitError(f"proportion {name} must be > 0, got {value!r}")
        if abs(sum(parts.values()) - 1.0) > 1e-9:
            raise SplitError(
                f"proportions must sum to 1.0, got {self.train}+{self.validation}"
                f"+{self.test}={sum(parts.values())!r}"
            )


@dataclass(frozen=True)
class SplitConfig:
    """Explicit split configuration (no ambient state)."""

    proportions: SplitProportions
    seed: int
    controller_context: str = "all-reactive-or-observational"
    #: Controller ids classified as predictive/interventional (LRK-09). The
    #: classification is caller-supplied; no enum is invented in this module.
    predictive_controller_ids: frozenset[str] = frozenset()
    include_predictive_variant: bool = False
    min_groups_per_partition: int = 1
    #: Optional descriptive name for dataset comparability audits (LRK-15).
    hardware_lineage: str | None = None

    def __post_init__(self) -> None:
        if not self.controller_context or not self.controller_context.strip():
            raise SplitError(
                "controller_context is mandatory in split configuration (LRK-09 "
                "W02-invariant: split manifests record the controller context)"
            )
        if not isinstance(self.seed, int):
            raise SplitError(f"seed must be an explicit integer, got {self.seed!r}")
        if not isinstance(self.min_groups_per_partition, int) or self.min_groups_per_partition < 1:
            raise SplitError("min_groups_per_partition must be an integer >= 1")


@dataclass(frozen=True)
class ExcludedRun:
    """A run deliberately left out of the split, with its recorded reason."""

    run_id: str
    reason: str


@dataclass(frozen=True)
class SplitResult:
    """Deterministic grouped assignment over independent run groups."""

    train_runs: tuple[str, ...]
    validation_runs: tuple[str, ...]
    test_runs: tuple[str, ...]
    excluded_runs: tuple[ExcludedRun, ...]
    group_of: Mapping[str, str]
    pair_lineage: tuple[dict[str, Any], ...]
    seed: int
    controller_context: str
    proportions: SplitProportions
    hardware_lineage: str | None = None

    def partition_of(self, run_id: str) -> str | None:
        """The partition owning ``run_id`` (``None`` when excluded)."""
        if run_id in self.train_runs:
            return "train"
        if run_id in self.validation_runs:
            return "validation"
        if run_id in self.test_runs:
            return "test"
        return None

    def runs_in(self, partition: str) -> tuple[str, ...]:
        if partition == "train":
            return self.train_runs
        if partition == "validation":
            return self.validation_runs
        if partition == "test":
            return self.test_runs
        raise SplitError(f"unknown partition {partition!r}; expected one of {PARTITIONS}")

    def to_manifest_dict(
        self,
        split_id: str,
        *,
        dataset_id: str,
        created_at: Any,
        created_by: str = "member-b",
        git_commit: str | None = None,
        status: str = "draft",
        content_sha256: str | None = None,
        locked_test_frozen_at: Any = None,
        locked_test_opened_at: Any = None,
    ) -> dict[str, Any]:
        """Serialize into the artifact-convention §3.2 split-manifest shape.

        ``locked_test.opened_at`` stays ``None`` through the tuning campaign
        by construction of the caller.
        """
        from .observations import event_time_to_rfc3339

        def _t(value: Any) -> Any:
            return None if value is None else event_time_to_rfc3339(value)

        return {
            "split_id": split_id,
            "dataset_id": dataset_id,
            "train_runs": list(self.train_runs),
            "validation_runs": list(self.validation_runs),
            "test_runs": list(self.test_runs),
            "grouping": {"key": "run_id"},
            "hardware_lineage": {"hardware_config_id": self.hardware_lineage},
            "locked_test": {
                "frozen_at": _t(locked_test_frozen_at),
                "opened_at": _t(locked_test_opened_at),
            },
            "controller_context": self.controller_context,
            "pair_lineage": [dict(entry) for entry in self.pair_lineage],
            "excluded_runs": [
                {"run_id": e.run_id, "reason": e.reason} for e in self.excluded_runs
            ],
            "split_seed": self.seed,
            "created_at": _t(created_at),
            "created_by": created_by,
            "git_commit": git_commit,
            "status": status,
            "content_sha256": content_sha256,
        }


def split_runs(run_infos: Sequence[RunInfo], config: SplitConfig) -> SplitResult:
    """Partition independent run groups into train/validation/test.

    Deterministic: same (runs, config, seed) -> identical partitions.
    """
    by_run_id: dict[str, RunInfo] = {}
    for info in run_infos:
        if info.run_id in by_run_id:
            raise SplitError(f"duplicate run metadata for {info.run_id!r}")
        by_run_id[info.run_id] = info
    if not by_run_id:
        raise SplitError("no runs supplied — refusing to split an empty dataset")

    excluded: dict[str, ExcludedRun] = {}
    accepted: list[RunInfo] = []
    for info in sorted(by_run_id.values(), key=lambda item: item.run_id):
        if not info.is_valid:
            excluded[info.run_id] = ExcludedRun(info.run_id, info.invalid_reason or "")
            continue
        if (
            not config.include_predictive_variant
            and info.controller_id in config.predictive_controller_ids
        ):
            excluded[info.run_id] = ExcludedRun(
                info.run_id, REASON_PREDICTIVE_CLOSED_LOOP
            )
            continue
        accepted.append(info)

    if not accepted:
        raise SplitError(
            "every run was excluded (invalid-run ledger / controller-context rules); "
            "no independent groups remain for a split"
        )

    # Effective grouping: a pair is ONE independent group (LRK-08); a lone run
    # is its own group (03 §47). run_id remains the grouping key; pair lineage
    # is recorded for audits, never used to collapse the rig (LRK-15).
    group_members: dict[str, list[str]] = {}
    for info in accepted:
        key = info.pair_id or info.run_id
        group_members.setdefault(key, []).append(info.run_id)

    pair_groups = {
        key: sorted(members)
        for key, members in sorted(group_members.items())
        if len(members) > 1
    }

    group_keys = sorted(group_members)
    shuffled = list(group_keys)
    random.Random(config.seed).shuffle(shuffled)

    n_groups = len(shuffled)
    proportions = config.proportions
    if n_groups < config.min_groups_per_partition * len(PARTITIONS):
        raise SplitError(
            f"insufficient independent groups: {n_groups} group(s) available for "
            f"{len(PARTITIONS)} partitions (train/validation/test); "
            f"{config.min_groups_per_partition} per partition is the minimum — "
            "refusing to leak by splitting below the floor"
        )

    # Cumulative-bound rounding keeps assignment deterministic and the union
    # exact; each positive-proportion partition must hold >= min groups.
    train_size = round(proportions.train * n_groups)
    train_val_size = round((proportions.train + proportions.validation) * n_groups)
    sizes = {
        "train": train_size,
        "validation": max(train_val_size - train_size, 0),
        "test": max(n_groups - train_val_size, 0),
    }
    for partition in PARTITIONS:
        if sizes[partition] < config.min_groups_per_partition:
            raise SplitError(
                f"partition {partition!r} would receive {sizes[partition]} independent "
                f"group(s) (requested proportion {getattr(proportions, partition)}; "
                f"{n_groups} groups in total) — below the configured minimum of "
                f"{config.min_groups_per_partition}; split refused instead of leaking"
            )

    assignment: dict[str, list[str]] = {partition: [] for partition in PARTITIONS}
    cursor = 0
    for partition in PARTITIONS:
        take = shuffled[cursor : cursor + sizes[partition]]
        # A group key expands to ALL its member runs — a pair's two arms are
        # placed into the same partition by one group key (LRK-08).
        for group_key in take:
            assignment[partition].extend(group_members[group_key])
        cursor += sizes[partition]
    if cursor != n_groups:
        raise SplitError(
            "internal assignment error: groups not fully partitioned "
            f"({cursor} of {n_groups} placed)"
        )

    run_to_partition = {
        run_id: partition
        for partition in PARTITIONS
        for run_id in assignment[partition]
    }
    placed = sorted(run_to_partition)
    if placed != sorted(info.run_id for info in accepted):
        raise SplitError(
            "internal assignment error: not every accepted run was placed exactly "
            "once — refusing to emit a partial split"
        )
    group_of = {
        run_id: (by_run_id[run_id].pair_id or run_id)
        for run_id in sorted(run_to_partition)
    }

    # A pair's runs inherit the same partition by construction; verify anyway.
    for pair in pair_groups.values():
        partitions = {run_to_partition[run_id] for run_id in pair}
        if len(partitions) != 1:
            raise SplitError(
                f"pair {pair} straddles partitions {sorted(partitions)} — "
                "paired runs must share one partition (03 §123)"
            )

    # Hardware comparability metadata (LRK-15/B5): record the single value
    # when all accepted runs share one configuration; a mixed-configuration
    # split requires the caller to acknowledge the convention B5 exception
    # explicitly via config.hardware_lineage — never silently rendered.
    accepted_hardware = {info.hardware_config_id for info in accepted if info.hardware_config_id}
    if config.hardware_lineage is not None:
        hardware_lineage: str | None = config.hardware_lineage
    elif len(accepted_hardware) == 1:
        hardware_lineage = next(iter(accepted_hardware))
    else:
        raise SplitError(
            "accepted runs carry more than one hardware_config_id "
            f"({sorted(accepted_hardware)}); hardware lineage is a split-manifest "
            "comparability guard (LRK-15, convention B5) — pass config.hardware_lineage "
            "as the registered-exception description reviewed with Member A"
        )

    return SplitResult(
        train_runs=tuple(sorted(assignment["train"])),
        validation_runs=tuple(sorted(assignment["validation"])),
        test_runs=tuple(sorted(assignment["test"])),
        excluded_runs=tuple(
            ExcludedRun(run_id, excluded[run_id].reason) for run_id in sorted(excluded)
        ),
        group_of=group_of,
        pair_lineage=tuple(
            {"pair_id": pair, "run_ids": members, "partition": run_to_partition[members[0]]}
            for pair, members in pair_groups.items()
        ),
        seed=config.seed,
        controller_context=config.controller_context,
        proportions=proportions,
        hardware_lineage=hardware_lineage,
    )
