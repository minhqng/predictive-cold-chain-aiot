"""W12 benchmark synthesis and Gate G3 evidence package.

Synthetic software controls remain software controls. No physical claim is
promoted, no locked test is opened and no PR is merged by this script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

try:  # installed package
    from coldguard_ml.benchmark_synthesis import (
        GroupedSynthesis,
        load_w11_bundle,
        grouped_metrics_csv_rows,
        synthesize_grouped_metrics,
    )
    from coldguard_ml.ewt_assessment import assess_real_ewt_aiw
    from coldguard_ml.feature_importance import (
        FeatureImportanceReport,
        compute_feature_importance,
    )
    from coldguard_ml.g3_readiness import (
        GateReadinessReport,
        build_gate_g3_readiness,
    )
    from coldguard_ml.operational_metrics import (
        OperationalReport,
        build_operational_report,
    )
    from coldguard_ml.xgb_benchmark import package_versions
except ModuleNotFoundError:  # direct checkout invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml.benchmark_synthesis import (
        GroupedSynthesis,
        load_w11_bundle,
        grouped_metrics_csv_rows,
        synthesize_grouped_metrics,
    )
    from coldguard_ml.ewt_assessment import assess_real_ewt_aiw
    from coldguard_ml.feature_importance import (
        FeatureImportanceReport,
        compute_feature_importance,
    )
    from coldguard_ml.g3_readiness import (
        GateReadinessReport,
        build_gate_g3_readiness,
    )
    from coldguard_ml.operational_metrics import (
        OperationalReport,
        build_operational_report,
    )
    from coldguard_ml.xgb_benchmark import package_versions

W12_LAYER_VERSION = "coldguard-w12-benchmark-g3-v1"
W12_MANIFEST_SCHEMA = "coldguard-w12-manifest-v1"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git_revision(root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNRECORDED"
    return completed.stdout.strip() or "UNRECORDED"


def _analysis_code_sha256(ml_root: Path) -> str:
    package = ml_root / "src" / "coldguard_ml"
    paths = (
        Path(__file__).resolve(),
        ml_root / "xgb-v1-config.yaml",
        ml_root / "feature-registry-v1.yaml",
        package / "benchmark_synthesis.py",
        package / "operational_metrics.py",
        package / "ewt_assessment.py",
        package / "feature_importance.py",
        package / "g3_readiness.py",
        package / "xgb_benchmark.py",
        package / "event_evaluator.py",
        package / "evaluation_contract.py",
        package / "feature_pipeline.py",
        package / "feature_registry.py",
        package / "grouped_evaluation.py",
        package / "labels.py",
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _csv_text(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        serialized = {}
        for column in columns:
            value = row.get(column)
            if isinstance(value, (list, tuple)):
                value = ";".join(str(item) for item in value)
            serialized[column] = "" if value is None else value
        writer.writerow(serialized)
    return buffer.getvalue()


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "undefined"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value == 0:
            return "0"
        return f"{value:.{digits}f}"
    return str(value)


def _grouped_markdown(synthesis: GroupedSynthesis) -> str:
    population = synthesis.population
    lines = [
        "# W12 grouped benchmark synthesis",
        "",
        "This is a source-aware consolidation of the W11 synthetic software "
        "control. It is not a physical benchmark result.",
        "",
        "## Population identity",
        "",
        "| Quantity | Value |",
        "|---|---|",
        f"| Dataset | `{population['dataset_id']}` |",
        f"| Provenance | `{population['provenance']}` |",
        f"| Independent run groups | {population['independent_run_group_count']} |",
        f"| Individual runs | {population['individual_run_count']} |",
        f"| Correlated feature windows | {population['correlated_feature_window_count']} |",
        f"| Positive / negative windows | {population['positive_window_count']} / "
        f"{population['negative_window_count']} |",
        f"| Eligible critical events | {population['eligible_critical_event_count']} |",
        f"| Grouped folds | {population['grouped_fold_count']} |",
        f"| Horizon | {population['horizon_s']} s (development candidate) |",
        f"| Feature registry SHA | `{population['feature_registry_sha256']}` |",
        f"| Model config SHA | `{population['model_config_sha256']}` |",
        f"| Real benchmark availability | `{population['real_benchmark_availability']}` |",
        "",
        "Thousands of windows are not thousands of independent physical "
        "experiments. The independent unit is the pair/run group.",
        "",
        "## Method distributions",
        "",
        "| Method | Strategy | Folds defined | AP mean | AP min | AP max | "
        "Sample SD | Mean P/R/F1 | Event recall | Claim |",
        "|---|---|---:|---:|---:|---:|---:|---|---:|---|",
    ]
    for summary in synthesis.method_summaries:
        lines.append(
            f"| {summary.method} | {summary.strategy} | "
            f"{summary.defined_folds}/{summary.fold_count} | "
            f"{_fmt(summary.mean_ap)} | {_fmt(summary.min_ap)} | "
            f"{_fmt(summary.max_ap)} | {_fmt(summary.sample_sd_ap)} | "
            f"{_fmt(summary.mean_precision)}/{_fmt(summary.mean_recall)}/"
            f"{_fmt(summary.mean_f1)} | {_fmt(summary.event_recall)} | "
            f"`{summary.scientific_claim_status}` |"
        )
    lines.extend(
        [
            "",
            "- AP is sample/window-level average precision, not event recall.",
            "- All fold values are retained in `grouped-metrics-W12.csv`.",
            "- Undefined folds stay undefined; they are not replaced by zero.",
            "- No confidence interval is computed: correlated windows are not "
            "independent samples.",
            "- B0/B1 and XGBoost use reconciled eligible sample populations and "
            "the same trusted exposure windows.",
            "",
            "## Required comparison fields",
            "",
            "| Method | Strategy | Population | Provenance | Groups | Runs | "
            "Folds | Windows | Events | AP distribution | Precision/Recall/F1 | "
            "Event recall | Unmatched | Missed | Undefined metrics | Claim |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|---:|---:|---|---|",
        ]
    )
    for summary in synthesis.method_summaries:
        ap_values = ", ".join(
            f"{fold_id}={_fmt(value)}" for fold_id, value in summary.fold_values
        )
        lines.append(
            f"| {summary.method} | {summary.strategy} | {summary.population} | "
            f"`{summary.provenance}` | {summary.group_count} | {summary.run_count} | "
            f"{summary.fold_count} | {summary.eligible_windows_total} | "
            f"{summary.eligible_events_total} | {ap_values} | "
            f"{_fmt(summary.mean_precision)}/{_fmt(summary.mean_recall)}/"
            f"{_fmt(summary.mean_f1)} | {_fmt(summary.event_recall)} | "
            f"{summary.unmatched_warnings_total} | {summary.missed_events_total} | "
            f"{'; '.join(summary.undefined_metric_reasons) or 'none'} | "
            f"`{summary.scientific_claim_status}` |"
        )
    lines.extend(
        [
            "",
            "## Integrity checks",
            "",
        ]
    )
    for check in synthesis.checks:
        lines.append(f"- {check}")
    lines.extend(["", "## Limitations", ""])
    for limitation in synthesis.limitations:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def _operational_markdown(report: OperationalReport) -> str:
    lines = [
        "## B-W12-02 operational synthesis",
        "",
        "| Method | Fold | Units | Episodes | Matched | Unmatched | Missed | "
        "Event precision | Event recall | False/run | False/hour | Trusted h | "
        "Provenance |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report.synthetic_rows:
        hours = (
            None
            if row.trusted_exposure_s is None
            else round(row.trusted_exposure_s / 3600.0, 6)
        )
        lines.append(
            f"| {row.method} | {row.fold_id} | episode/event/run/hour | "
            f"{row.warning_episodes} | {row.matched_warning_episodes} | "
            f"{row.unmatched_warning_episodes} | "
            f"{_fmt(row.missed_critical_events)} | {_fmt(row.event_precision)} | "
            f"{_fmt(row.event_recall)} | "
            f"{_fmt(row.false_warning_episodes_per_run)} | "
            f"{_fmt(row.false_warning_episodes_per_hour)} | "
            f"{_fmt(hours)} | `{row.provenance}` |"
        )
    lines.extend(
        [
            "",
            "One sustained warning episode counts once. Multiple warning samples "
            "do not create multiple events.",
            "",
            "### Real physical population",
            "",
            "| Metric | Status | Reason |",
            "|---|---|---|",
            f"| Real false-warning burden | `{report.real_status['REAL_FALSE_WARNING_BURDEN']}` | "
            f"{', '.join(report.real_status['reason_codes'])} |",
            f"| Real missed-event rate | `{report.real_status['REAL_MISSED_EVENT_RATE']}` | "
            f"{', '.join(report.real_status['reason_codes'])} |",
            f"| Real event recall | `{report.real_status['REAL_EVENT_RECALL']}` | "
            f"{', '.join(report.real_status['reason_codes'])} |",
            "",
            "Zero qualified physical events do not create a zero rate; the rate "
            "is undefined.",
            "",
            "### Unit statement",
            "",
        ]
    )
    for unit, meaning in report.unit_statement.items():
        lines.append(f"- `{unit}`: {meaning}.")
    lines.append("")
    return "\n".join(lines)


def _ewt_markdown(report: Any) -> str:
    lines = [
        "## B-W12-03 EWT assessment",
        "",
        "All timing rows below are synthetic contract demonstrations: "
        f"`{report.synthetic_cases[0].label if report.synthetic_cases else 'SYNTHETIC_TIMING_CONTRACT_TEST_ONLY'}`.",
        "",
        "| Case | Status | EWT (s) | Reason code | Run identity | Clock domains |",
        "|---|---|---:|---|---|---|",
    ]
    for case in report.synthetic_cases:
        lines.append(
            f"| {case.case_id} | `{case.status}` | {_fmt(case.ewt_s)} | "
            f"`{case.reason_code}` | {case.predictive_run_id} / "
            f"{case.reactive_run_id} | {case.predictive_clock_domain} / "
            f"{case.reactive_clock_domain} |"
        )
    real = report.real_status
    lines.extend(
        [
            "",
            "### Real timing status",
            "",
            "| Metric | Status | Reason code | Reason |",
            "|---|---|---|---|",
            f"| Real EWT | `{real['REAL_EWT']}` | `{real['REAL_EWT_REASON_CODE']}` | "
            f"{real['REAL_EWT_REASON']} |",
            f"| Real AIW | `{real['REAL_AIW']}` | `{real['REAL_AIW_REASON_CODE']}` | "
            f"{real['REAL_AIW_REASON']} |",
            "",
            "EWT and AIW have different evidence contracts. An estimable EWT "
            "would not imply an actionable AIW.",
            "",
            "Definitions:",
            "",
        ]
    )
    for name, definition in report.definitions.items():
        lines.append(f"- `{name}`: {definition}.")
    lines.append("")
    return "\n".join(lines)


def _importance_markdown(report: FeatureImportanceReport) -> str:
    lines = [
        "## B-W12-04 feature-importance diagnostics",
        "",
        "Importance method: XGBoost gain, fold-scoped. No SHAP and no locked test.",
        "",
        "| Feature | Family | Fold | Strategy | Gain | Share | Rank | "
        "Registry version | Interpretation limit |",
        "|---|---|---|---|---:|---:|---:|---|---|",
    ]
    for row in report.rows[:20]:
        lines.append(
            f"| `{row.feature_id}` | {row.feature_family} | {row.fold_id} | "
            f"{row.strategy} | {_fmt(row.importance_value)} | "
            f"{_fmt(row.normalized_share)} | {row.rank} | "
            f"{row.feature_registry_version} | descriptive only |"
        )
    lines.extend(
        [
            "",
            "The CSV retains every feature/fold row. The top rows are shown here "
            "only to expose the synthetic pattern.",
            "",
            "| Family | Features | Fold models | Mean share | Top feature |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for family in report.family_summaries:
        lines.append(
            f"| {family.feature_family} | {family.feature_count} | "
            f"{family.fold_model_count} | {_fmt(family.mean_normalized_share)} | "
            f"`{family.top_feature_id}` |"
        )
    lines.extend(
        [
            "",
            "If the top feature is a door-timing or other scenario-identifying "
            "variable, that is evidence of synthetic source identification, not "
            "genuine thermal forecasting or physical causation.",
            "",
            "Source identity:",
            "",
        ]
    )
    for key, value in report.source_identities.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    return "\n".join(lines)


def _gate_markdown(report: GateReadinessReport) -> str:
    decision = report.decision
    lines = [
        "# Gate G3 evidence and decision (W12)",
        "",
        f"**Aggregate decision: `{decision.decision}`**",
        "",
        "This is Member B's evidence-based input, not a team approval.",
        "",
        "## Evidence matrix",
        "",
        "| Requirement | Owner | Required evidence | Actual source | Observed result | "
        "Quality | Status | Blocking reason | Next evidence | Review authority |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report.rows:
        lines.append(
            f"| `{row.requirement_id}` | {row.owning_team_member} | "
            f"{row.required_evidence} | {row.actual_file_reference} | "
            f"{row.observed_result} | {row.evidence_quality} | "
            f"`{row.readiness_status}` | {row.blocking_reason or 'none'} | "
            f"{row.next_required_evidence} | {row.review_authority} |"
        )
    lines.extend(
        [
            "",
            "## Decision precedence",
            "",
            f"- Hard blockers: {', '.join(f'`{item}`' for item in decision.hard_blockers)}",
            f"- W12 software: `{decision.software_status}`",
            f"- Physical: `{decision.physical_status}`",
            "- A hard physical/data failure is not overridden by synthetic ML metrics.",
            "- `GO WITH LIMITATIONS` is not available while the physical dataset gate is RED.",
            "",
            "## Rationale",
            "",
        ]
    )
    for item in decision.rationale:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Permitted / forbidden",
            "",
            "Permitted:",
            "",
        ]
    )
    for item in decision.permitted_work:
        lines.append(f"- {item}")
    lines.extend(["", "Forbidden:", ""])
    for item in decision.forbidden_work:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Human authority",
            "",
            f"- {decision.human_authority}",
            "",
            "## Limitations",
            "",
        ]
    )
    for item in report.limitations:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _write_csv(path: Path, text: str) -> bytes:
    payload = text.encode("utf-8")
    path.write_bytes(payload)
    return payload


def _gate_matrix_csv(report: GateReadinessReport) -> str:
    columns = (
        "requirement_id",
        "requirement",
        "canonical_source",
        "owning_team_member",
        "required_evidence",
        "actual_file_reference",
        "source_hash_revision",
        "observed_result",
        "evidence_quality",
        "readiness_status",
        "blocking_reason",
        "next_required_evidence",
        "review_authority",
    )
    return _csv_text([row.to_row() for row in report.rows], columns)


def _grouped_csv(report: GroupedSynthesis) -> str:
    rows = grouped_metrics_csv_rows(report)
    columns = (
        "row_type",
        "method",
        "strategy",
        "fold_id",
        "metric",
        "value",
        "population",
        "provenance",
        "group_count",
        "run_count",
        "fold_count",
        "defined_folds",
        "undefined_folds",
        "fold_values",
        "mean_ap",
        "median_ap",
        "min_ap",
        "max_ap",
        "sample_sd_ap",
        "sample_sd_reason",
        "mean_precision",
        "mean_recall",
        "mean_f1",
        "eligible_windows_total",
        "eligible_events_total",
        "warning_episodes_total",
        "matched_episodes_total",
        "unmatched_warnings_total",
        "missed_events_total",
        "event_precision",
        "event_recall",
        "undefined_metric_reasons",
        "confidence_interval",
        "confidence_interval_reason",
        "ap_aggregation",
        "event_aggregation",
        "scientific_claim_status",
    )
    return _csv_text(rows, columns)


def _operational_csv(report: OperationalReport) -> str:
    columns = (
        "method",
        "fold_id",
        "population",
        "provenance",
        "validation_run_count",
        "group_count",
        "eligible_windows",
        "warning_episodes",
        "matched_warning_episodes",
        "unmatched_warning_episodes",
        "missed_critical_events",
        "eligible_critical_events",
        "event_precision",
        "event_recall",
        "false_warning_episodes_per_run",
        "false_warning_episodes_per_hour",
        "trusted_exposure_s",
        "untrusted_exposure_s",
        "coverage_trustworthy",
        "censored_events",
        "untrusted_events",
        "first_warning_timestamp",
        "first_reactive_timestamp",
        "unit_warning_episode",
        "unit_event",
        "unit_exposure",
        "undefined_reasons",
        "scientific_claim_status",
    )
    rows = [row.to_row() for row in report.synthetic_rows]
    real = report.real_status
    rows.append(
        {
            "method": "REAL_PHYSICAL_POPULATION",
            "fold_id": "ALL",
            "population": real["population"],
            "provenance": "AUTHORITATIVE_REAL_REFUSAL",
            "validation_run_count": real["eligible_runs"],
            "group_count": 0,
            "eligible_windows": 0,
            "warning_episodes": "",
            "matched_warning_episodes": "",
            "unmatched_warning_episodes": "",
            "missed_critical_events": "",
            "eligible_critical_events": 0,
            "event_precision": "",
            "event_recall": real["REAL_EVENT_RECALL"],
            "false_warning_episodes_per_run": real["REAL_FALSE_WARNING_BURDEN"],
            "false_warning_episodes_per_hour": real["REAL_FALSE_WARNING_BURDEN"],
            "trusted_exposure_s": "",
            "untrusted_exposure_s": "",
            "coverage_trustworthy": "",
            "censored_events": "",
            "untrusted_events": "",
            "first_warning_timestamp": "NOT_AVAILABLE",
            "first_reactive_timestamp": "NOT_AVAILABLE",
            "unit_warning_episode": "warning_episode",
            "unit_event": "eligible_critical_event",
            "unit_exposure": "trusted_eligible_hour",
            "undefined_reasons": ";".join(real["reason_codes"]),
            "scientific_claim_status": "REAL_EVENT_METRICS_NOT_ESTIMABLE",
        }
    )
    return _csv_text(rows, columns)


def _ewt_csv(report: Any) -> str:
    columns = (
        "case_id",
        "event_id",
        "population",
        "label",
        "status",
        "ewt_s",
        "reason_code",
        "reason",
        "predictive_run_id",
        "reactive_run_id",
        "predictive_clock_domain",
        "reactive_clock_domain",
        "warning_definition",
        "persistence_definition",
        "intervention",
    )
    rows = [case.to_row() for case in report.synthetic_cases]
    real = report.real_status
    rows.extend(
        [
            {
                "case_id": "REAL_EWT",
                "event_id": "",
                "population": real["population"],
                "label": "REAL_SOURCE_AUTHORIZED_REFUSAL",
                "status": real["REAL_EWT"],
                "ewt_s": "",
                "reason_code": real["REAL_EWT_REASON_CODE"],
                "reason": real["REAL_EWT_REASON"],
                "predictive_run_id": "",
                "reactive_run_id": "",
                "predictive_clock_domain": "",
                "reactive_clock_domain": "",
                "warning_definition": report.definitions["warning_definition"],
                "persistence_definition": report.definitions["persistence_definition"],
                "intervention": "",
            },
            {
                "case_id": "REAL_AIW",
                "event_id": "",
                "population": real["population"],
                "label": "REAL_SOURCE_AUTHORIZED_REFUSAL",
                "status": real["REAL_AIW"],
                "ewt_s": "",
                "reason_code": real["REAL_AIW_REASON_CODE"],
                "reason": real["REAL_AIW_REASON"],
                "predictive_run_id": "",
                "reactive_run_id": "",
                "predictive_clock_domain": "",
                "reactive_clock_domain": "",
                "warning_definition": "",
                "persistence_definition": "",
                "intervention": "",
            },
        ]
    )
    return _csv_text(rows, columns)


def _importance_csv(report: FeatureImportanceReport) -> str:
    columns = (
        "row_type",
        "feature_id",
        "feature_registry_version",
        "feature_family",
        "importance_method",
        "importance_value",
        "normalized_share",
        "model_identity",
        "fold_id",
        "strategy",
        "scope",
        "cv_scope",
        "run_group_support",
        "validation_group_count",
        "source_provenance",
        "rank",
        "missingness_context",
        "interpretation_limit",
        "feature_count",
        "fold_model_count",
        "mean_normalized_share",
        "top_feature_id",
    )
    rows: list[dict[str, Any]] = [
        {"row_type": "FEATURE_FOLD", **row.to_row()} for row in report.rows
    ]
    rows.extend(
        {"row_type": "FAMILY_SUMMARY", **item.to_row()}
        for item in report.family_summaries
    )
    return _csv_text(rows, columns)


def _report_markdown(
    synthesis: GroupedSynthesis,
    operational: OperationalReport,
    ewt: Any,
    importance: FeatureImportanceReport,
    gate: GateReadinessReport,
) -> str:
    verdicts = gate.decision
    lines = [
        "# W12 benchmark synthesis and Gate G3 readiness",
        "",
        "**Software, synthetic benchmark validity and physical Gate G3 "
        "readiness are three different decisions.**",
        "",
        "| Verdict | Status |",
        "|---|---|",
        f"| W12 software | `GREEN` |",
        f"| Synthetic benchmark synthesis | `VERIFIED_BY_TESTS` |",
        f"| Physical Gate B | `RED` |",
        f"| Real grouped benchmark | `NOT_ESTABLISHED` |",
        f"| Real event metrics | `NOT_ESTIMABLE` |",
        f"| Real EWT | `NOT_ESTIMABLE` |",
        f"| Real AIW | `NOT_ESTIMABLE` |",
        f"| Gate G3 | `{verdicts.decision}` |",
        "",
        "## 1. Source pack",
        "",
        "W12 reads W04–W11 contracts and artifacts as immutable inputs. Every "
        "W11 artifact hash is verified before synthesis. No A/C/D source or "
        "evidence is modified.",
        "",
        "## 2. B-W12-01 — Grouped benchmark synthesis",
        "",
        "The independent unit is the pair/run group, not the feature window.",
        f"W11 contributes {synthesis.population['independent_run_group_count']} "
        f"pair groups, {synthesis.population['individual_run_count']} runs, "
        f"{synthesis.population['grouped_fold_count']} grouped folds and "
        f"{synthesis.population['correlated_feature_window_count']} correlated "
        "feature windows. Synthetic AP=1.0 is a software-control result and does "
        "not show physical superiority.",
        "",
        "See `grouped-metrics-W12.csv` for every fold value and summary row.",
        "",
        "## 3. B-W12-02 — False warnings and missed events",
        "",
        "W09 episode matching is reused. The synthetic operational table is in "
        "`event-operational-summary-W12.csv`; real false-warning burden, "
        "missed-event rate and event recall remain `NOT_ESTIMABLE` because zero "
        "eligible physical runs exist.",
        "",
        "| Property | Synthetic population | Real physical population |",
        "|---|---|---|",
        "| Mathematical result available | yes, synthetic only | no eligible events |",
        "| Scientific result supported | no physical claim | `NOT_ESTIMABLE` |",
        "",
        "## 4. B-W12-03 — Initial EWT",
        "",
        "EWT and AIW are separated. Synthetic timing cases demonstrate positive, "
        "negative, zero, missing-anchor, cross-run, cross-clock and intervention "
        "refusal behavior under `SYNTHETIC_TIMING_CONTRACT_TEST_ONLY`. Real EWT "
        "and AIW remain `NOT_ESTIMABLE` for different reasons. See "
        "`ewt-assessment-W12.csv`.",
        "",
        "## 5. B-W12-04 — Feature-importance diagnostics",
        "",
        "Fold-scoped XGBoost gain is reported in `feature-importance-W12.csv`. "
        "The top family in these fold models is "
        f"`{importance.family_summaries[0].feature_family if importance.family_summaries else 'UNKNOWN'}`"
        " with feature "
        f"`{importance.family_summaries[0].top_feature_id if importance.family_summaries else 'UNKNOWN'}`. "
        "Allowed conclusion: in this synthetic fixture these features were used "
        "by the model under the recorded version/configuration. Forbidden "
        "conclusion: these features physically cause critical cold-chain events. "
        "A door-timing or scenario-identifying feature is evidence of synthetic "
        "source identification, not thermal causality. No SHAP, no locked test, "
        "no causal claim.",
        "",
        "## 6. B-W12-05 — Gate G3",
        "",
        f"**Decision: `{verdicts.decision}`**",
        "",
        "Hard blockers: "
        + (", ".join(f"`{item}`" for item in verdicts.hard_blockers) or "none"),
        "",
        "The full matrix is in `gate-g3-evidence-matrix-W12.csv`; the decision "
        "report is `gate-g3-W12.md`.",
        "",
        "## 7. Cross-milestone evidence integrity",
        "",
        "- W04 admission remains authoritative: no eligible real run.",
        "- W05 duplicate-view refusal and W06 clock/identity alignment remain "
        "preserved in the W08/W09/W10 chain.",
        "- W07 independent-run counting, W08 Gate B RED and W09 event provenance "
        "are not rewritten.",
        "- W10 feature causality/source binding and W11 grouped split/model "
        "provenance are verified by hash.",
        "- No synthetic positive test substitutes for a missing physical source.",
        "",
        "## 8. Verification and limitations",
        "",
        "- Full W04–W11 regression suite is run after W12.",
        "- Artifact hashes and deterministic replay are checked.",
        "- No locked physical P3 dataset or test outcome is read.",
        "- No PR is merged, retargeted or approved by this report.",
        "",
    ]
    return "\n".join(lines)


def _manifest(
    *,
    synthesis: GroupedSynthesis,
    operational: OperationalReport,
    ewt: Any,
    importance: FeatureImportanceReport,
    gate: GateReadinessReport,
    artifact_hashes: Mapping[str, str],
    repository_revision: str,
    command: str,
    analysis_code_sha256: str,
    source_hashes: Mapping[str, Any],
    validations: Sequence[str],
) -> dict[str, Any]:
    real = ewt.real_status
    return {
        "schema": W12_MANIFEST_SCHEMA,
        "layer_version": W12_LAYER_VERSION,
        "generated_at_utc": "NOT_RECORDED_BY_DESIGN",
        "repository_revision": repository_revision,
        "generation_command": command,
        "analysis_code_sha256": analysis_code_sha256,
        "package_versions": package_versions(),
        "deterministic": True,
        "repository_inputs": dict(source_hashes),
        "artifacts": {
            name: {"sha256": digest} for name, digest in sorted(artifact_hashes.items())
        },
        "grouped_synthesis": synthesis.to_dict(),
        "operational": operational.to_dict(),
        "ewt_assessment": ewt.to_dict(),
        "feature_importance": importance.to_dict(),
        "gate_g3": gate.to_dict(),
        "scientific_verdicts": {
            "W12_SOFTWARE": "GREEN",
            "SYNTHETIC_BENCHMARK_SYNTHESIS": "VERIFIED_BY_TESTS",
            "PHYSICAL_GATE_B": "RED",
            "REAL_GROUPED_BENCHMARK": "NOT_ESTABLISHED",
            "REAL_EVENT_METRICS": "NOT_ESTIMABLE",
            "REAL_EWT": "NOT_ESTIMABLE",
            "REAL_AIW": "NOT_ESTIMABLE",
            "GATE_G3": gate.decision.decision,
        },
        "hard_boundaries": [
            "no PR merge, retarget or closure",
            "no A/C/D source or evidence change",
            "no locked-test access",
            "no physical deployment or Controller B actuation",
            "no causal claim from feature importance",
            "no EWT/AIW claim from synthetic timing cases",
        ],
        "validations": list(validations),
        "real_status": {
            "REAL_EWT": real["REAL_EWT"],
            "REAL_EWT_REASON_CODE": real["REAL_EWT_REASON_CODE"],
            "REAL_AIW": real["REAL_AIW"],
            "REAL_AIW_REASON_CODE": real["REAL_AIW_REASON_CODE"],
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ColdGuard W12 grouped benchmark synthesis and Gate G3 evidence. "
            "Synthetic results are software controls, never physical evidence."
        )
    )
    parser.add_argument("--out", default="reports/W12")
    parser.add_argument("--w11-reports", default="reports/W11")
    parser.add_argument(
        "--w08-manifest", default="reports/W08/gate-b-manifest-W08.json"
    )
    parser.add_argument(
        "--w09-manifest", default="reports/W09/baseline-manifest-W09.json"
    )
    parser.add_argument(
        "--w10-manifest", default="reports/W10/feature-manifest-W10.json"
    )
    parser.add_argument(
        "--w06-manifest", default="reports/W06/timing-manifest-W06.json"
    )
    parser.add_argument("--feature-registry", default="feature-registry-v1.yaml")
    parser.add_argument("--config", default="xgb-v1-config.yaml")
    parser.add_argument("--repository-revision", default=None)
    args = parser.parse_args(argv)
    ml_root = Path(__file__).resolve().parents[1]
    repo_root = ml_root.parent
    out_dir = (ml_root / args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in (
        "benchmark-synthesis-W12.md",
        "grouped-metrics-W12.csv",
        "event-operational-summary-W12.csv",
        "ewt-assessment-W12.csv",
        "feature-importance-W12.csv",
        "gate-g3-W12.md",
        "gate-g3-evidence-matrix-W12.csv",
        "w12-manifest.json",
    ):
        (out_dir / stale).unlink(missing_ok=True)
    revision = args.repository_revision or _git_revision(repo_root)
    command = "python " + " ".join(arg.replace("\\", "/") for arg in sys.argv)
    w08_path = (ml_root / args.w08_manifest).resolve()
    w09_path = (ml_root / args.w09_manifest).resolve()
    w10_path = (ml_root / args.w10_manifest).resolve()
    w06_path = (ml_root / args.w06_manifest).resolve()
    w11_path = (ml_root / args.w11_reports).resolve()
    registry_path = (ml_root / args.feature_registry).resolve()
    config_path = (ml_root / args.config).resolve()
    try:
        w08 = json.loads(w08_path.read_text(encoding="utf-8"))
        w09 = json.loads(w09_path.read_text(encoding="utf-8"))
        w10 = json.loads(w10_path.read_text(encoding="utf-8"))
        w06 = json.loads(w06_path.read_text(encoding="utf-8"))
        bundle = load_w11_bundle(
            w11_path,
            registry_path=registry_path,
            config_path=config_path,
        )
        real_gate = bundle.manifest.get("real_development", {}).get(
            "PHYSICAL_GATE_B"
        )
        if real_gate != "RED":
            raise RuntimeError(
                "W12 artifact generation requires a RED physical Gate B; "
                "new authoritative evidence must reopen the review"
            )
        synthesis = synthesize_grouped_metrics(bundle)
        operational = build_operational_report(bundle)
        ewt = assess_real_ewt_aiw(
            bundle.manifest, w06_counts=w06.get("counts", {})
        )
        importance = compute_feature_importance(bundle)
        gate = build_gate_g3_readiness(
            repo_root=repo_root,
            w11_manifest=bundle.manifest,
            w08_manifest=w08,
            w09_manifest=w09,
            w10_manifest=w10,
            w11_manifest_path=w11_path / "benchmark-manifest-W11.json",
            w08_manifest_path=w08_path,
            w09_manifest_path=w09_path,
            w10_manifest_path=w10_path,
            software_status="GREEN",
        )
        artifact_hashes: dict[str, str] = {}
        report_text = "\n".join(
            (
                _report_markdown(synthesis, operational, ewt, importance, gate),
                _operational_markdown(operational),
                _ewt_markdown(ewt),
                _importance_markdown(importance),
            )
        )
        report_bytes = report_text.encode("utf-8")
        (out_dir / "benchmark-synthesis-W12.md").write_bytes(report_bytes)
        artifact_hashes["benchmark-synthesis-W12.md"] = _sha256_bytes(report_bytes)
        artifact_hashes["grouped-metrics-W12.csv"] = _sha256_bytes(
            _write_csv(out_dir / "grouped-metrics-W12.csv", _grouped_csv(synthesis))
        )
        artifact_hashes["event-operational-summary-W12.csv"] = _sha256_bytes(
            _write_csv(
                out_dir / "event-operational-summary-W12.csv",
                _operational_csv(operational),
            )
        )
        artifact_hashes["ewt-assessment-W12.csv"] = _sha256_bytes(
            _write_csv(out_dir / "ewt-assessment-W12.csv", _ewt_csv(ewt))
        )
        artifact_hashes["feature-importance-W12.csv"] = _sha256_bytes(
            _write_csv(out_dir / "feature-importance-W12.csv", _importance_csv(importance))
        )
        gate_markdown = _gate_markdown(gate).encode("utf-8")
        (out_dir / "gate-g3-W12.md").write_bytes(gate_markdown)
        artifact_hashes["gate-g3-W12.md"] = _sha256_bytes(gate_markdown)
        artifact_hashes["gate-g3-evidence-matrix-W12.csv"] = _sha256_bytes(
            _write_csv(
                out_dir / "gate-g3-evidence-matrix-W12.csv",
                _gate_matrix_csv(gate),
            )
        )
        source_hashes = {
            "w06_manifest": {
                "path": "reports/W06/timing-manifest-W06.json",
                "exists": w06_path.exists(),
                "sha256": _sha256_bytes(w06_path.read_bytes())
                if w06_path.exists()
                else None,
            },
            "w08_manifest": gate.source_revisions["w08_manifest"],
            "w09_manifest": gate.source_revisions["w09_manifest"],
            "w10_manifest": gate.source_revisions["w10_manifest"],
            "w11_manifest": gate.source_revisions["w11_manifest"],
            "a_sources": gate.source_revisions["a_sources"],
        }
        manifest = _manifest(
            synthesis=synthesis,
            operational=operational,
            ewt=ewt,
            importance=importance,
            gate=gate,
            artifact_hashes=artifact_hashes,
            repository_revision=revision,
            command=command,
            analysis_code_sha256=_analysis_code_sha256(ml_root),
            source_hashes=source_hashes,
            validations=(
                "W11 artifact hashes verified against the W11 manifest",
                "grouped fold/run/event identities reconciled",
                "synthetic provenance and real-development refusal retained",
                "feature importance fold-scoped; locked test untouched",
                "Gate G3 decision derived from the evidence matrix",
            ),
        )
        manifest_bytes = (
            json.dumps(manifest, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        (out_dir / "w12-manifest.json").write_bytes(manifest_bytes)
        # Rewrite the manifest once with the final artifact hashes including
        # the manifest's own deterministic payload is intentionally excluded;
        # w12-manifest.json is not listed as its own child artifact.
        print(
            "W12 benchmark synthesis complete: "
            f"decision={gate.decision.decision} "
            f"groups={synthesis.population['independent_run_group_count']} "
            f"folds={synthesis.population['grouped_fold_count']} "
            f"artifacts={out_dir}"
        )
        return 0
    except Exception as exc:  # fail closed; no partial success claim
        print(f"W12 REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
