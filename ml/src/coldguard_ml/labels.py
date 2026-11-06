"""Canonical early-warning horizon labels ``y_t(H)`` (Doc ``03`` §41).

Conventions frozen by the canonical documents and the W01 contracts:

* ``y_t(H) = 1`` iff a qualifying critical event occurs in the half-open,
  open-left future interval ``(t, t+H]`` (Doc ``03`` §41; ``05B`` §3.1).
  An event exactly at the prediction instant ``t`` does NOT qualify, an
  event exactly at ``t + H`` DOES.
* The qualifying critical event series is **authoritative input**: the
  canonical ``T_critical`` boundary / representative temperature / horizon
  are PROVISIONAL until their predeclared freezes (claim-data-matrix §8,
  Doc ``03`` §§42–44). This module never invents a threshold and never
  derives one from provided trajectory values.
* Complete future coverage makes a definite ``0`` possible; an
  under-covered horizon yields the explicit ``CENSORED`` status — never an
  automatic negative label (Doc ``03`` §85 spirit; right-censored
  trajectories are not negative evidence).
* Missing or untrusted critical-state information inside the horizon yields
  the explicit ``UNTRUSTED_INFO`` status (data-dictionary-v0 §13: missing
  data strategies may not fabricate evidence).
* Label identity (LRK-10 W02-invariant): every record carries the horizon,
  the supplied label-spec identity, and the series provenance, so audits
  can re-derive what was frozen when.
"""

from __future__ import annotations

import datetime as _dt
import enum
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import LabelError

__all__ = [
    "CriticalEvent",
    "CriticalEventSeries",
    "LabelSpec",
    "LabelStatus",
    "LabelRecord",
    "generate_label_records",
    "labels_and_windows",
]


class LabelStatus(str, enum.Enum):
    """Explicit evaluation status of one label."""

    EVALUABLE = "EVALUABLE"  # definite y ∈ {0, 1}
    CENSORED = "CENSORED"  # incomplete horizon coverage — NOT a negative
    UNTRUSTED_INFO = "UNTRUSTED_INFO"  # missing/untrusted critical-state info in horizon


@dataclass(frozen=True)
class CriticalEvent:
    """One entry of an authoritative critical-event series.

    ``trusted=False`` marks critical-state information that is present but
    not trustworthy under the run's quality/validity ledger (§11, §13).
    Untrusted entries never silently create or deny a positive label.
    """

    time: _dt.datetime
    trusted: bool = True
    ref: str | None = None  # optional source-identity pointer for audits


@dataclass(frozen=True)
class CriticalEventSeries:
    """The per-run authoritative critical-event timeline (label ground truth)."""

    run_id: str
    events: tuple[CriticalEvent, ...]
    series_id: str  # provenance identity recorded on every label
    coverage_end: _dt.datetime | None = None  # explicit "series evaluated through"

    def __post_init__(self) -> None:
        if not self.run_id:
            raise LabelError("critical series requires a run_id")
        if not self.series_id:
            raise LabelError("critical series requires a provenance series_id")
        canonical = tuple(sorted(self.events, key=lambda e: (e.time, not e.trusted, e.ref or "")))
        if len({(e.time, e.trusted) for e in canonical}) != len(canonical):
            raise LabelError(
                f"run {self.run_id}: duplicate critical-event entries "
                f"(time, trusted) in series {self.series_id!r}"
            )
        object.__setattr__(self, "events", canonical)


@dataclass(frozen=True)
class LabelSpec:
    """Label definition identity (recorded verbatim on every label — LRK-10).

    ``horizon_s`` and the (optional) representative-temperature / boundary
    values are the values the caller freezes into this spec object; W02 does
    not invent or validate them against hardware. ``frozen_at`` stays
    ``None`` until a real predeclared freeze exists.
    """

    horizon_s: float
    spec_version: str
    representative_temperature: str | None = None
    boundary_c: float | None = None
    frozen_at: _dt.datetime | None = None

    def __post_init__(self) -> None:
        horizon = self.horizon_s
        if isinstance(horizon, bool) or not isinstance(horizon, (int, float)):
            raise LabelError(f"horizon_s must be a finite number > 0, got {horizon!r}")
        try:
            numeric = float(horizon)
        except (OverflowError, ValueError) as exc:
            raise LabelError(
                f"horizon_s {horizon!r} is outside the representable time domain"
            ) from exc
        if not math.isfinite(numeric) or horizon <= 0:
            raise LabelError(f"horizon_s must be a finite number > 0, got {horizon!r}")
        try:
            _dt.timedelta(seconds=horizon)
        except (OverflowError, ValueError) as exc:
            raise LabelError(
                f"horizon_s {horizon!r} is outside the representable time domain"
            ) from exc
        if not self.spec_version or not self.spec_version.strip():
            raise LabelError("label spec requires a non-empty spec_version")

    @property
    def identity_fields(self) -> dict[str, Any]:
        """The mandatory label-artifact identity fields (LRK-10 W02-invariant)."""
        from .observations import event_time_to_rfc3339

        return {
            "horizon_s": self.horizon_s,
            "spec_version": self.spec_version,
            "representative_temperature": self.representative_temperature,
            "boundary_c": self.boundary_c,
            "frozen_at": None if self.frozen_at is None else event_time_to_rfc3339(self.frozen_at),
        }


@dataclass(frozen=True)
class LabelRecord:
    """One evaluated early-warning label ``y_t(H)`` with full provenance."""

    run_id: str
    prediction_time: _dt.datetime
    horizon_s: float
    label_interval: tuple[_dt.datetime, _dt.datetime]  # (t, t+H] open-left/inclusive-right
    status: LabelStatus
    y: int | None  # None when CENSORED / UNTRUSTED_INFO
    matched_event: CriticalEvent | None
    series_id: str
    anchor_ref: Any = None  # recorded verbatim from the anchoring call
    spec: LabelSpec | None = None

    @property
    def spec_identity(self) -> dict[str, Any]:
        if self.spec is None:
            raise LabelError("label record was created without a spec identity")
        return self.spec.identity_fields


def _qualifying_window(
    prediction_time: _dt.datetime, horizon_s: float
) -> tuple[_dt.datetime, _dt.datetime]:
    """Canonical label interval: open at ``t`` (left), inclusive at ``t+H``."""
    return (prediction_time, prediction_time + _dt.timedelta(seconds=horizon_s))


def generate_label_records(
    run_id: str,
    anchors: Iterable[tuple[_dt.datetime, Any]],
    series: CriticalEventSeries,
    spec: LabelSpec,
    *,
    coverage_end: _dt.datetime | None,
) -> tuple[LabelRecord, ...]:
    """Evaluate ``y_t(H)`` for explicit anchor instants of one run.

    Parameters
    ----------
    anchors:
        Iterable of ``(prediction_time, anchor_ref)`` pairs. ``anchor_ref``
        is recorded verbatim for traceability (e.g. the originating window or
        sample identity).
    coverage_end:
        The last instant the critical-state information covers for this run.
        Explicit input — callers own coverage truth (typically the last
        recorded event time of the trajectory); ``series.coverage_end``
        always takes precedence when declared.
    """
    if series.run_id != run_id:
        raise LabelError(
            f"series {series.series_id!r} is for run {series.run_id!r}, not {run_id!r}"
        )
    effective_coverage = series.coverage_end if series.coverage_end is not None else coverage_end
    if effective_coverage is None:
        raise LabelError(
            f"run {run_id}: label coverage is unknown — supply coverage_end "
            "(e.g. last recorded event time of the trajectory) or declare "
            "CriticalEventSeries.coverage_end; CENSORED detection must be explicit"
        )

    records: list[LabelRecord] = []
    for prediction_time, anchor_ref in anchors:
        interval = _qualifying_window(prediction_time, spec.horizon_s)
        trusted_events = [
            e for e in series.events if e.trusted and interval[0] < e.time <= interval[1]
        ]
        untrusted_events = [
            e for e in series.events if not e.trusted and interval[0] < e.time <= interval[1]
        ]
        if trusted_events:
            status = LabelStatus.EVALUABLE
            y: int | None = 1
            matched = trusted_events[0]
        elif untrusted_events:
            status = LabelStatus.UNTRUSTED_INFO
            y = None
            matched = None
        elif effective_coverage >= interval[1]:
            status = LabelStatus.EVALUABLE
            y = 0
            matched = None
        else:
            status = LabelStatus.CENSORED
            y = None
            matched = None
        records.append(
            LabelRecord(
                run_id=run_id,
                prediction_time=prediction_time,
                horizon_s=spec.horizon_s,
                label_interval=interval,
                status=status,
                y=y,
                matched_event=matched,
                series_id=series.series_id,
                anchor_ref=anchor_ref,
                spec=spec,
            )
        )
    return tuple(records)


def _series_for_run(series: Mapping[str, CriticalEventSeries], run_id: str) -> CriticalEventSeries:
    try:
        return series[run_id]
    except KeyError as exc:
        raise LabelError(f"no critical-event series supplied for run {run_id!r}") from exc


def labels_and_windows(
    windows: Iterable[Any],
    series_by_run: Mapping[str, CriticalEventSeries],
    spec: LabelSpec,
    *,
    trajectory_ends: Mapping[str, _dt.datetime] | None = None,
    coverage_ends: Mapping[str, _dt.datetime] | None = None,
) -> tuple[tuple[Any, LabelRecord], ...]:
    """Attach labels to windows pairwise; windows are never modified.

    ``trajectory_ends`` / ``coverage_ends`` map ``run_id`` -> the last
    instant the critical-state information covers. ``coverage_ends``
    overrides ``trajectory_ends``; a series' own ``coverage_end`` always
    wins. Window order of the input is preserved in the output pairs.
    """
    ordered = tuple(windows)
    merged_coverage: dict[str, _dt.datetime] = {}
    if trajectory_ends:
        merged_coverage.update(trajectory_ends)
    if coverage_ends:
        merged_coverage.update(coverage_ends)

    grouped_by_run: dict[str, list[Any]] = {}
    for window in ordered:
        run_id = window.run_id
        grouped_by_run.setdefault(run_id, []).append(window)

    labeled_for_window: dict[Any, LabelRecord] = {}
    for run_id, run_windows in grouped_by_run.items():
        run_series = _series_for_run(series_by_run, run_id)
        run_coverage = merged_coverage.get(run_id)
        run_coverage = run_series.coverage_end or run_coverage
        if run_coverage is None:
            raise LabelError(
                f"run {run_id}: label coverage unknown (no trajectory_end/coverage_end "
                "supplied and series declares none)"
            )
        anchors = [(window.prediction_time, window) for window in run_windows]
        run_records = generate_label_records(
            run_id, anchors, run_series, spec, coverage_end=run_coverage
        )
        for window, record in zip(run_windows, run_records):
            labeled_for_window[window] = record

    return tuple((window, labeled_for_window[window]) for window in ordered)
