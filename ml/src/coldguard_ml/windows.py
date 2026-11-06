"""Causal, run-bounded temporal window generation (Doc ``03`` §46).

Contract rules implemented here:

* windows are generated ONLY after the run-level split, one partition at a
  time (``03`` §46; ``05B`` §12). The API refuses to generate windows
  without a ``SplitResult`` — generating "windows from all runs" and
  splitting later is the forbidden pipeline inversion (register LRK-02
  W02-invariant);
* a window anchored at prediction time ``t`` contains only observations
  with event time in ``(t - window_length, t]`` (``02`` §19.4: feature
  input <= t). No future observation can enter a window;
* windows never cross a run or a boot boundary (§3 reboot rule / LRK-13):
  every window carries exactly one ``(run_id, boot_id)`` trajectory key;
* rows must be owned by the requested partition; a row of a run belonging
  to another partition raises instead of being silently mixed;
* duplicate deliveries collapse to one physical sample; a payload
  contradiction raises (QoS-1 unity / dictionary §1.2);
* quality is traceable, never silently repaired: per-section quality counts
  and absent-value counts ride along with every window (LRK-14), and no
  absent value is substituted (no zero-fill, no interpolation);
* window length and anchor stride are configuration — the canonical docs
  freeze no window grammar yet (feature grammar belongs to a later
  predeclared freeze);
* generation is deterministic: the same unduplicated inputs, split and
  config produce identical windows in identical order regardless of row
  arrival order.
"""

from __future__ import annotations

import datetime as _dt
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import WindowError
from .observations import (
    Observation,
    SampleIdentity,
    canonical_order,
)
from .splitting import SplitResult

__all__ = [
    "WindowConfig",
    "Window",
    "QualityCounts",
    "AbsentCounts",
    "generate_windows",
    "window_anchors",
]

PARTITIONS = ("train", "validation", "test")
_CHANNELS = (
    "t1_c",
    "t2_c",
    "t3_c",
    "t_air_c",
    "rh_pct",
    "cooling_voltage_v",
    "cooling_current_a",
    "cooling_power_w",
    "cooling_energy_counter_wh",
    "applied_duty",
)


@dataclass(frozen=True)
class WindowConfig:
    """Window geometry (unfrozen grammar; explicit and recorded)."""

    window_length_s: float = 30.0
    anchor_stride: int = 1

    def __post_init__(self) -> None:
        length = self.window_length_s
        if isinstance(length, bool) or not isinstance(length, (int, float)):
            raise WindowError(
                f"window_length_s must be a finite number > 0, got {length!r}"
            )
        try:
            numeric = float(length)
        except (OverflowError, ValueError) as exc:
            raise WindowError(
                f"window_length_s {length!r} is outside the representable time domain"
            ) from exc
        if not math.isfinite(numeric) or length <= 0:
            raise WindowError(
                f"window_length_s must be a finite number > 0, got {length!r}"
            )
        try:
            _dt.timedelta(seconds=length)
        except (OverflowError, ValueError) as exc:
            raise WindowError(
                f"window_length_s {length!r} is outside the representable time domain"
            ) from exc
        if type(self.anchor_stride) is not int or self.anchor_stride < 1:
            raise WindowError(f"anchor_stride must be an integer >= 1, got {self.anchor_stride!r}")


#: Hashable, order-deterministic quality rollup:
#: ``((section, ((quality, count), ...)), ...)`` sorted by section/quality name.
QualityCounts = tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
#: Hashable, order-deterministic absent-value rollup: ``((channel, count), ...)``.
AbsentCounts = tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Window:
    """One causal window with full provenance and quality traceability.

    Rollups are stored as sorted hashable tuples so a ``Window`` stays
    fully comparable and hashable — the same window built twice must be
    ``==``/hash-equal, and label attachment keys records by window.
    Use the ``*_by_*`` properties for dict-shaped views.
    """

    run_id: str
    boot_id: str
    partition: str
    prediction_time: _dt.datetime
    window_start: _dt.datetime  # exclusive lower bound (t - window_length_s)
    observations: tuple[Observation, ...]
    sample_identities: tuple[SampleIdentity, ...]
    quality_counts: QualityCounts
    absent_value_counts: AbsentCounts
    max_gap_s: float | None

    @property
    def window_interval(self) -> tuple[_dt.datetime, _dt.datetime]:
        """Causal admissibility interval ``(window_start, prediction_time]``."""
        return (self.window_start, self.prediction_time)

    @property
    def quality_counts_by_section(self) -> dict[str, dict[str, int]]:
        """Dict view of the per-section quality rollup."""
        return {section: dict(qualities) for section, qualities in self.quality_counts}

    @property
    def absent_counts_by_channel(self) -> dict[str, int]:
        """Dict view of the absent-value rollup (never zero-filled upstream)."""
        return dict(self.absent_value_counts)


def window_anchors(observations: Sequence[Observation], config: WindowConfig) -> tuple[Observation, ...]:
    """Causal anchor samples for sorted boot-scoped observations (stride-applied)."""
    return tuple(observations[:: config.anchor_stride])


def generate_windows(
    rows: Iterable[Observation],
    split: SplitResult,
    partition: str,
    config: WindowConfig | None = None,
) -> tuple[Window, ...]:
    """Generate causal windows for the runs of ONE partition.

    Parameters
    ----------
    rows:
        Normalized micro-samples (e.g. an export of the partition's runs).
        Not required to be pre-ordered; duplication/order canon is applied.
    split:
        The grouped split these windows belong to. Required — the window
        generator refuses leakage-unsafe invocation without a split.
    partition:
        One of ``train`` / ``validation`` / ``test``.
    """
    if config is None:
        config = WindowConfig()
    if partition not in PARTITIONS:
        raise WindowError(f"unknown partition {partition!r}; expected one of {PARTITIONS}")
    if split is None:
        raise WindowError(
            "window generation without a split manifest is refused (runs → split → "
            "windows is the only legal order; LRK-02)"
        )

    partition_runs = split.runs_in(partition)
    partition_run_ids = set(partition_runs)
    all_split_runs = set(split.group_of)
    # Materialize once: validation and canonicalization must see the same rows
    # whether the caller supplies a list, tuple, or one-shot iterator.
    materialized_rows = tuple(rows)
    for row in materialized_rows:
        run_id = row.run_id
        if run_id not in all_split_runs:
            raise WindowError(
                f"run {run_id!r} is not part of the supplied split (excluded runs are not "
                "window sources); every row must belong to a partitioned run"
            )
        if run_id not in partition_run_ids:
            raise WindowError(
                f"run {run_id!r} belongs to partition {split.partition_of(run_id)!r} — "
                f"refusing to generate {partition!r} windows from foreign-partition rows"
            )

    canonical = canonical_order(materialized_rows)
    return _build_windows(canonical, partition, config)


def _build_windows(
    canonical_rows: tuple[Observation, ...], partition: str, config: WindowConfig
) -> tuple[Window, ...]:
    """Enumerate causal windows from canonically ordered rows."""
    by_trajectory: dict[tuple[str, str], list[Observation]] = {}
    for row in canonical_rows:
        by_trajectory.setdefault(row.trajectory_key, []).append(row)

    windows: list[Window] = []
    window_span = _dt.timedelta(seconds=config.window_length_s)
    for (run_id, boot_id) in sorted(by_trajectory):
        trajectory = by_trajectory[(run_id, boot_id)]
        for anchor in window_anchors(trajectory, config):
            t = anchor.time
            lower = t - window_span
            window_rows = [row for row in trajectory if lower < row.time <= t]
            windows.append(
                Window(
                    run_id=run_id,
                    boot_id=boot_id,
                    partition=partition,
                    prediction_time=t,
                    window_start=lower,
                    observations=tuple(window_rows),
                    sample_identities=tuple(row.identity for row in window_rows),
                    quality_counts=_quality_rollup(window_rows),
                    absent_value_counts=_absent_rollup(window_rows),
                    max_gap_s=_max_gap(window_rows),
                )
            )
    return tuple(windows)


def _quality_rollup(window_rows: Sequence[Observation]) -> QualityCounts:
    counts: dict[str, dict[str, int]] = {
        section: {quality: 0 for quality in ("VALID", "DEGRADED", "INVALID")}
        for section in ("thermal", "environment", "electrical", "overall")
    }
    section_fields = {
        "thermal": "thermal_quality",
        "environment": "environment_quality",
        "electrical": "electrical_quality",
        "overall": "overall_quality",
    }
    for row in window_rows:
        for section, field_name in section_fields.items():
            counts[section][getattr(row, field_name)] += 1
    return tuple(
        (section, tuple(sorted(sections_qualities.items())))
        for section, sections_qualities in sorted(counts.items())
    )


def _absent_rollup(window_rows: Sequence[Observation]) -> AbsentCounts:
    counts = {channel: 0 for channel in _CHANNELS}
    for row in window_rows:
        for channel in _CHANNELS:
            if getattr(row, channel) is None:
                counts[channel] += 1
    return tuple(sorted(counts.items()))


def _max_gap(window_rows: Sequence[Observation]) -> float | None:
    if len(window_rows) < 2:
        return None
    largest = max(
        (window_rows[i + 1].time - window_rows[i].time).total_seconds()
        for i in range(len(window_rows) - 1)
    )
    return largest
