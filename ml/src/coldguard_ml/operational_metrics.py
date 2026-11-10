"""W12 operational synthesis of W11 event metrics (B-W12-02).

The W09 episode matcher is reused; this module only translates its already
episode-level outputs into operational units. Warning samples never become
independent events here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .benchmark_synthesis import W11Bundle

OPERATIONAL_SCHEMA = "coldguard-w12-operational-summary-v1"
SYNTHETIC_OPERATIONAL = "SYNTHETIC_OPERATIONAL_EVALUATION_ONLY"
REAL_NOT_ESTIMABLE = "NOT_ESTIMABLE"
REAL_REASON = "NO_ELIGIBLE_PHYSICAL_S1_OR_S2_RUN"

REAL_OPERATIONAL_FIELDS = (
    "REAL_FALSE_WARNING_BURDEN",
    "REAL_MISSED_EVENT_RATE",
    "REAL_EVENT_RECALL",
)


class OperationalMetricsError(ValueError):
    """Operational units would be fabricated or conflated."""


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value: Any) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


@dataclass(frozen=True)
class OperationalRow:
    method: str
    fold_id: str
    population: str
    provenance: str
    validation_run_count: int
    group_count: int
    eligible_windows: int
    warning_episodes: int
    matched_warning_episodes: int
    unmatched_warning_episodes: int
    missed_critical_events: int | None
    eligible_critical_events: int | None
    event_precision: float | None
    event_recall: float | None
    false_warning_episodes_per_run: float | None
    false_warning_episodes_per_hour: float | None
    trusted_exposure_s: float | None
    untrusted_exposure_s: float | None
    coverage_trustworthy: bool | None
    censored_events: int | None
    untrusted_events: int | None
    first_warning_timestamp: str
    first_reactive_timestamp: str
    unit_warning_episode: str
    unit_event: str
    unit_exposure: str
    undefined_reasons: tuple[str, ...]
    scientific_claim_status: str

    def to_row(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "fold_id": self.fold_id,
            "population": self.population,
            "provenance": self.provenance,
            "validation_run_count": self.validation_run_count,
            "group_count": self.group_count,
            "eligible_windows": self.eligible_windows,
            "warning_episodes": self.warning_episodes,
            "matched_warning_episodes": self.matched_warning_episodes,
            "unmatched_warning_episodes": self.unmatched_warning_episodes,
            "missed_critical_events": self.missed_critical_events,
            "eligible_critical_events": self.eligible_critical_events,
            "event_precision": self.event_precision,
            "event_recall": self.event_recall,
            "false_warning_episodes_per_run": self.false_warning_episodes_per_run,
            "false_warning_episodes_per_hour": self.false_warning_episodes_per_hour,
            "trusted_exposure_s": self.trusted_exposure_s,
            "untrusted_exposure_s": self.untrusted_exposure_s,
            "coverage_trustworthy": self.coverage_trustworthy,
            "censored_events": self.censored_events,
            "untrusted_events": self.untrusted_events,
            "first_warning_timestamp": self.first_warning_timestamp,
            "first_reactive_timestamp": self.first_reactive_timestamp,
            "unit_warning_episode": self.unit_warning_episode,
            "unit_event": self.unit_event,
            "unit_exposure": self.unit_exposure,
            "undefined_reasons": ";".join(self.undefined_reasons),
            "scientific_claim_status": self.scientific_claim_status,
        }


@dataclass(frozen=True)
class OperationalReport:
    schema: str
    synthetic_rows: tuple[OperationalRow, ...]
    real_status: Mapping[str, Any]
    unit_statement: Mapping[str, str]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "synthetic_rows": [row.to_row() for row in self.synthetic_rows],
            "real_status": dict(self.real_status),
            "unit_statement": dict(self.unit_statement),
            "limitations": list(self.limitations),
        }


def build_operational_report(bundle: W11Bundle) -> OperationalReport:
    fold_manifest = bundle.fold_manifest
    folds = {
        str(fold["fold_id"]): fold for fold in fold_manifest.get("folds", ())
    }
    rows: list[OperationalRow] = []
    for comparison in sorted(
        bundle.comparison_rows,
        key=lambda row: (row["method"], row["fold_id"]),
    ):
        fold = folds.get(comparison["fold_id"])
        if fold is None:
            raise OperationalMetricsError(
                f"comparison row references unknown fold {comparison['fold_id']!r}"
            )
        run_ids = tuple(fold.get("validation_run_ids", ()))
        group_ids = tuple(fold.get("validation_group_ids", ()))
        undefined: list[str] = []
        for column, unit in (
            ("false_warning_episodes_per_run", "per_eligible_run"),
            ("false_warning_episodes_per_hour", "per_trusted_eligible_hour"),
            ("event_recall", "per_eligible_critical_event"),
        ):
            if _number(comparison[column]) is None:
                undefined.append(f"{column.upper()}_UNDEFINED")
        rows.append(
            OperationalRow(
                method=comparison["method"],
                fold_id=comparison["fold_id"],
                population="synthetic development runs (not physical evidence)",
                provenance=SYNTHETIC_OPERATIONAL,
                validation_run_count=len(run_ids),
                group_count=len(group_ids),
                eligible_windows=_int(comparison["eligible_sample_count"]) or 0,
                warning_episodes=_int(comparison["warning_episode_count"]) or 0,
                matched_warning_episodes=(
                    _int(comparison["matched_warning_episodes"]) or 0
                ),
                unmatched_warning_episodes=(
                    _int(comparison["unmatched_warnings"]) or 0
                ),
                missed_critical_events=_int(comparison["missed_critical_events"]),
                eligible_critical_events=_int(
                    comparison["eligible_critical_event_count"]
                ),
                event_precision=_number(comparison["event_precision"]),
                event_recall=_number(comparison["event_recall"]),
                false_warning_episodes_per_run=_number(
                    comparison["false_warning_episodes_per_run"]
                ),
                false_warning_episodes_per_hour=_number(
                    comparison["false_warning_episodes_per_hour"]
                ),
                trusted_exposure_s=_number(comparison["trusted_exposure_s"]),
                untrusted_exposure_s=_number(comparison["untrusted_exposure_s"]),
                coverage_trustworthy=_bool(comparison["coverage_trustworthy"]),
                censored_events=_int(comparison["censored_event_count"]),
                untrusted_events=_int(comparison["untrusted_event_count"]),
                first_warning_timestamp="NOT_AVAILABLE_IN_AGGREGATED_FOLD_VIEW",
                first_reactive_timestamp="NOT_AVAILABLE_IN_AGGREGATED_FOLD_VIEW",
                unit_warning_episode="warning_episode",
                unit_event="eligible_critical_event",
                unit_exposure="trusted_eligible_hour",
                undefined_reasons=tuple(dict.fromkeys(undefined)),
                scientific_claim_status=SYNTHETIC_OPERATIONAL,
            )
        )
    real_development = bundle.manifest.get("real_development", {})
    real_eligible = int(real_development.get("ELIGIBLE_RUNS", 0) or 0)
    if real_eligible > 0:
        raise OperationalMetricsError(
            "eligible real runs exist; W12 must reassess operational metrics from "
            "source evidence instead of retaining a refusal"
        )
    real_status: dict[str, Any] = {
        "population": "real physical eligible S1/S2 runs",
        "eligible_runs": real_eligible,
        "physical_gate_b": real_development.get("PHYSICAL_GATE_B"),
        "REAL_FALSE_WARNING_BURDEN": REAL_NOT_ESTIMABLE,
        "REAL_MISSED_EVENT_RATE": REAL_NOT_ESTIMABLE,
        "REAL_EVENT_RECALL": REAL_NOT_ESTIMABLE,
        "reason_codes": [REAL_REASON],
        "note": (
            "Zero qualified physical events do not create a zero rate; the "
            "mathematical result is undefined, not zero."
        ),
    }
    unit_statement = {
        "AP": "sample/window-level average precision; not event recall",
        "warning_episodes": "one contiguous warning interval counted once",
        "critical_events": "eligible observed critical events only",
        "exposure": "trusted all-channel-VALID hours, not elapsed span",
        "runs": "validation runs inside paired groups; independence is at group level, not run or window level",
    }
    limitations = (
        "Synthetic operational values are software-control observations only.",
        "No real false-warning burden, missed-event rate or event recall is "
        "established while zero eligible physical runs exist.",
        "A warning sample stream is not a set of independent events.",
        "The aggregated fold view does not expose per-run first-warning or "
        "first-reactive timestamps.",
    )
    return OperationalReport(
        schema=OPERATIONAL_SCHEMA,
        synthetic_rows=tuple(rows),
        real_status=real_status,
        unit_statement=unit_statement,
        limitations=limitations,
    )
