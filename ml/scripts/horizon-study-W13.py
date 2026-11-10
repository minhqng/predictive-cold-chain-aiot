#!/usr/bin/env python3
"""ColdGuard W13 horizon engineering CLI (B-W13-01..04).

Phases
------
A. Reconcile the merged A 20261107 18-row package and the A W13 plant-timing
   report against the B admission ladder. Scenario acceptance is not
   predictive eligibility; every real run is refused with explicit reasons.
B. Screen the canonical 30/60/120/300 s candidate horizons against the
   measured plant timing (DERIVED proxy screening, never a measured verdict).
C. Run the per-horizon grouped sensitivity study on the W11 synthetic
   development fixture, reusing the W11 grouped benchmark and leakage audit.
D. Decide the primary horizon only if the evidence balance and the frozen
   selection preconditions justify it; otherwise emit the honest
   PROVISIONAL_CANDIDATE_ONLY / NO_SELECTION category.

Evidence consumption
--------------------
The 20261107 package is merged-canonical on origin/main at the pinned
A_SOURCE_REVISION but is absent from the W12 stack ancestry. Export it
read-only from that exact revision (never rebase the B stack)::

    git archive <A_SOURCE_REVISION> evidence/A/SOURCES/20261107/datasets \
        | tar -x -C <export-dir>
    python scripts/horizon-study-W13.py \
        --a-dataset-dir <export-dir>/evidence/A/SOURCES/20261107/datasets

All consumed bytes are SHA-256 pinned; a mismatch refuses the run.

Exit codes
----------
* 0 — artifacts written with honest scientific statuses.
* 2 — fail-closed refusal (configuration, pin mismatch, inconsistent
  evidence, audit fail); no partial success is reported.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

try:  # installed package
    from coldguard_ml.feature_registry import load_registry
    from coldguard_ml.horizon_engineering import (
        A_20261107_MANIFEST_SHA256,
        A_20261107_RUN_INDEX_SHA256,
        A_SOURCE_REVISION,
        A_W13_TIMING_REPORT_SHA256,
        CANDIDATE_HORIZONS_S,
        W13_LABEL_SPEC_VERSION,
        W13_LAYER_VERSION,
        W13_MANIFEST_SCHEMA,
        DatasetReconciliation,
        HorizonDecision,
        HorizonScreening,
        HorizonStudy,
        PlantTiming,
        decide_primary_horizon,
        horizon_metrics_csv_rows,
        load_plant_timing,
        reconcile_a_dataset,
        run_horizon_study,
        screen_horizon_candidates,
        verify_sha256,
    )
    from coldguard_ml.xgb_benchmark import (
        build_expanded_w11_fixture,
        load_benchmark_config,
        package_versions,
    )
except ModuleNotFoundError:  # direct checkout invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml.feature_registry import load_registry
    from coldguard_ml.horizon_engineering import (
        A_20261107_MANIFEST_SHA256,
        A_20261107_RUN_INDEX_SHA256,
        A_SOURCE_REVISION,
        A_W13_TIMING_REPORT_SHA256,
        CANDIDATE_HORIZONS_S,
        W13_LABEL_SPEC_VERSION,
        W13_LAYER_VERSION,
        W13_MANIFEST_SCHEMA,
        DatasetReconciliation,
        HorizonDecision,
        HorizonScreening,
        HorizonStudy,
        PlantTiming,
        decide_primary_horizon,
        horizon_metrics_csv_rows,
        load_plant_timing,
        reconcile_a_dataset,
        run_horizon_study,
        screen_horizon_candidates,
        verify_sha256,
    )
    from coldguard_ml.xgb_benchmark import (
        build_expanded_w11_fixture,
        load_benchmark_config,
        package_versions,
    )

CSV_COLUMNS = (
    "row_type",
    "population",
    "horizon_s",
    "method",
    "fold_id",
    "evaluable_samples",
    "positive_count",
    "negative_count",
    "positive_prevalence",
    "censored_exclusions",
    "untrusted_exclusions",
    "average_precision",
    "ap_status",
    "ap_reason",
    "event_recall",
    "false_warning_episodes_per_hour",
    "missed_critical_events",
    "unmatched_warnings",
    "ewt_status",
    "ewt_reason_code",
    "aiw_status",
    "aiw_reason_code",
    "undefined_reasons",
    "scientific_claim_status",
    "provenance",
)

ARTIFACT_NAMES = (
    "horizon-study.md",
    "horizon-metrics.csv",
    "primary-horizon-decision.md",
    "horizon-manifest-W13.json",
)

HARD_BOUNDARIES = (
    "18 exported rows/segments are never 18 independent runs; the "
    "independence ceiling is the distinct boot count and shared-boot "
    "windows carry A's independence caveat",
    "A scenario acceptance (A-W09-02 / A-W10-03 PASS) is not B predictive "
    "eligibility; the W04 admission ladder refuses every real run here",
    "synthetic per-horizon AP is a software control; the highest synthetic "
    "AP never selects a primary horizon",
    "missing timing inputs stay NOT_ESTIMABLE; they are never zero",
    "the locked test partition is never read and no horizon is frozen",
    "PR #95 is OPEN/unmerged: cited with a verified pin, never consumed as "
    "canonical evidence",
    "no W04-W12 defect is fixed inside W13; the B stack is not rebased; "
    "A/C/D source evidence is preserved byte-for-byte",
)


class CliError(RuntimeError):
    pass


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
        package / "horizon_engineering.py",
        package / "xgb_benchmark.py",
        package / "leakage_audit.py",
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


def _reconciliation_markdown(
    reconciliation: DatasetReconciliation, timing: PlantTiming
) -> str:
    lines = [
        "## Phase A — evidence reconciliation",
        "",
        f"Source: `origin/main@{reconciliation.source_revision}` (merged PR #91 "
        "package), consumed through a read-only `git archive` export; the B "
        "stack was not rebased. Pins: run_index "
        f"`{reconciliation.run_index_sha256}`, manifest "
        f"`{reconciliation.manifest_sha256}`.",
        "",
        "| Quantity | Value |",
        "|---|---|",
        f"| Exported rows/segments | {reconciliation.row_count} |",
        f"| Distinct boots (independence ceiling) | {reconciliation.distinct_boots} |",
        f"| Frames total | {reconciliation.frames_total} |",
        f"| A-accepted S1 windows | {reconciliation.accepted_s1_windows} |",
        f"| A-accepted S2 windows (door + timing) | {reconciliation.accepted_s2_windows} |",
        f"| B predictive-eligible runs | {reconciliation.predictive_eligible_runs} |",
        "",
        reconciliation.to_dict()["independence_statement"] + ".",
        "",
        "### Per-source classification",
        "",
        "| run | scenario | A classification | B classification | boot | frames | permitted use |",
        "|---|---|---|---|---|---:|---|",
    ]
    for source in reconciliation.sources:
        lines.append(
            f"| {source.run_tag} | {source.scenario} | {source.a_classification} "
            f"| {source.b_classification} | {source.boot_id} | {source.frames} "
            f"| {source.permitted_use} |"
        )
    lines += [
        "",
        "### Predictive admission refusal reasons (all real runs)",
        "",
    ]
    lines += [f"- `{reason}`" for reason in reconciliation.refusal_reasons]
    lines += [
        "",
        "### Superseded / stale evidence notes (computed, A files untouched)",
        "",
    ]
    lines += [f"- {note}" for note in reconciliation.superseded_evidence_notes]
    pr95 = reconciliation.pr95_supplement
    lines += [
        "",
        "### PR #95 supplement (cited, never consumed)",
        "",
        f"- PR #95 head `{pr95['head_revision']}`; merge status "
        f"`{pr95['merge_status']}`; classification `{pr95['classification']}`; "
        f"consumed as canonical evidence: {pr95['consumed_as_canonical_evidence']}.",
        f"- trial.json sha256 `{pr95['trial_json_sha256']}`.",
        f"- {pr95['summary']}.",
        "",
        "### A plant timing (merged evidence/A/W13/plant-timing-report.json)",
        "",
        f"- evidence kind `{timing.evidence_kind}`, physical_verified="
        f"{_fmt(timing.physical_verified)}; command->electrical "
        f"{_fmt(timing.command_to_electrical_s)} s (n={timing.electrical_n_measured}, "
        "console START-accept anchor, +/-1 s poll quantization); "
        f"command->thermal {_fmt(timing.command_to_thermal_s)} s for "
        f"{_fmt(timing.thermal_delta_c)} degC (applied-on anchor, boot 56044b74).",
        f"- cooling tau proxy {_fmt(timing.cooling_tau_s)} s, recovery tau proxy "
        f"{_fmt(timing.recovery_tau_s)} s ({timing.tau_limitation}).",
        f"- passive drift {_fmt(timing.passive_drift_c)} degC over "
        f"{_fmt(timing.passive_window_min)} min; no passive tau asserted.",
        f"- door->critical: `{timing.door_to_critical_status}` "
        "(value null; critical definition unfrozen).",
        "",
    ]
    return "\n".join(lines)


def _screening_markdown(screenings: Sequence[HorizonScreening]) -> str:
    lines = [
        "## Phase B — candidate horizon screening (DERIVED, proxy-biased)",
        "",
        "Canonical exploratory candidates 30/60/120/300 s for the fast "
        "six-litre plant (docs/03). No longer horizon is invented: the "
        "measured tau proxies are truncation-biased. AIW upper bound = "
        "H - command->thermal proxy, assuming only T_system >= 0.",
        "",
        "| H (s) | screen | AIW upper bound (s) | H / cooling tau | rationale |",
        "|---:|---|---:|---:|---|",
    ]
    for screening in screenings:
        lines.append(
            f"| {screening.horizon_s:g} | {screening.screen} "
            f"| {_fmt(screening.aiw_upper_bound_s)} "
            f"| {_fmt(screening.cooling_tau_ratio)} | {screening.rationale} |"
        )
    lines += ["", "Screening status: `" + screenings[0].status + "`.", ""]
    lines += [f"- Caveat: {caveat}" for caveat in screenings[0].caveats]
    lines.append("")
    return "\n".join(lines)


def _study_markdown(study: HorizonStudy) -> str:
    lines = [
        "## Phase C — per-horizon grouped study (synthetic software control)",
        "",
        f"Fixture `{study.fixture_dataset_id}` (`{study.fixture_version}`); "
        f"label spec `{study.spec_version}`; one-factor-at-a-time: only the "
        "label horizon changes, the W11 development split/folds/seed/features "
        "stay frozen. Population: SYNTHETIC_DEVELOPMENT — never a physical "
        "benchmark.",
        "",
        "### Label populations per horizon",
        "",
        "| H (s) | evaluable | positive | negative | prevalence | censored excl. | untrusted excl. | leakage audit |",
        "|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for metrics in study.horizons:
        lines.append(
            f"| {metrics.horizon_s:g} | {metrics.evaluable_samples} "
            f"| {metrics.positive_count} | {metrics.negative_count} "
            f"| {_fmt(metrics.prevalence)} | {metrics.censored_exclusions} "
            f"| {metrics.untrusted_exclusions} | {metrics.leakage_audit_status} |"
        )
    notes = ["", "Censored horizons are excluded, never labeled negative."]
    for metrics in study.horizons:
        if metrics.evaluable_samples == 0:
            notes.append(
                f"H={metrics.horizon_s:g} s leaves zero evaluable samples "
                f"({metrics.censored_exclusions} anchors censored); no metric "
                "is imputed."
            )
        if metrics.refusal_reason:
            notes.append(
                f"H={metrics.horizon_s:g} s benchmark evaluation is refused: "
                f"{metrics.refusal_reason}."
            )
    lines += notes + [
        "",
        "### Per-method fold AP (every fold reported; undefined stays undefined)",
        "",
        "| H (s) | method | fold | fit | AP | event recall | false warn/h | missed | unmatched |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for metrics in study.horizons:
        for fold in metrics.method_folds:
            lines.append(
                f"| {metrics.horizon_s:g} | {fold.method} | {fold.fold_id} "
                f"| {fold.fit_status} | {_fmt(fold.average_precision.value)} "
                f"| {_fmt(fold.event_recall)} "
                f"| {_fmt(fold.false_warning_episodes_per_hour)} "
                f"| {_fmt(fold.missed_critical_events)} "
                f"| {_fmt(fold.unmatched_warnings)} |"
            )
    lines += [
        "",
        "### Aggregate AP and OOF status",
        "",
        "| H (s) | method | aggregate status | mean AP | instability range | OOF |",
        "|---:|---|---|---:|---:|---|",
    ]
    for metrics in study.horizons:
        for method, aggregate in sorted(metrics.aggregate_ap.items()):
            lines.append(
                f"| {metrics.horizon_s:g} | {method} | {aggregate['status']} "
                f"| {_fmt(aggregate.get('mean'))} "
                f"| {_fmt(aggregate.get('instability_range'))} "
                f"| {metrics.oof_status.get(method, 'NOT_APPLICABLE')} |"
            )
    lines += [
        "",
        "Undefined AP carries its reason (single-class fold/population); no "
        "value is imputed. EWT and AIW are NOT_ESTIMABLE for every horizon: "
        f"EWT `{study.horizons[0].ewt_reason_code}`, AIW "
        f"`{study.horizons[0].aiw_reason_code}`.",
        "",
        "### Real physical population — refusal rows",
        "",
        "Every horizon carries a REAL_REFUSAL row in horizon-metrics.csv "
        "with all metrics null/NOT_ESTIMABLE and the Phase A refusal reasons; "
        "no real prevalence, AP, event recall, false-warning rate, EWT or AIW "
        "is fabricated.",
        "",
        "### Limitations",
        "",
    ]
    lines += [f"- {item}" for item in study.limitations]
    lines.append("")
    return "\n".join(lines)


def _study_report_markdown(
    reconciliation: DatasetReconciliation,
    timing: PlantTiming,
    screenings: Sequence[HorizonScreening],
    study: HorizonStudy,
    decision: HorizonDecision,
) -> str:
    lines = [
        "# W13 horizon study — evidence reconciliation, candidates, grouped sensitivity",
        "",
        f"Layer `{W13_LAYER_VERSION}`; label spec `{W13_LABEL_SPEC_VERSION}`.",
        "",
        f"**Scientific decision: {decision.display_category}.** Primary "
        "horizon: not selected, not frozen. Software study completed on the "
        "synthetic development population only; the real physical population "
        "is refused by the admission ladder with explicit reasons.",
        "",
        _reconciliation_markdown(reconciliation, timing),
        _screening_markdown(screenings),
        _study_markdown(study),
        "## Replay",
        "",
        "```bash",
        f"git archive {A_SOURCE_REVISION} evidence/A/SOURCES/20261107/datasets \\",
        "    | tar -x -C <export-dir>",
        "cd ml",
        "python scripts/horizon-study-W13.py \\",
        "    --a-dataset-dir <export-dir>/evidence/A/SOURCES/20261107/datasets \\",
        "    --out reports/W13 --repository-revision <stack-head>",
        "```",
        "",
        "All consumed evidence bytes are SHA-256 pinned in "
        "horizon-manifest-W13.json; any mismatch refuses the run (exit 2). "
        "Model artifacts are written to a scratch directory and hash-recorded, "
        "never committed.",
        "",
    ]
    return "\n".join(lines)


def _decision_markdown(
    decision: HorizonDecision,
    reconciliation: DatasetReconciliation,
    study: HorizonStudy,
) -> str:
    completed = sum(
        1 for metrics in study.horizons if metrics.leakage_audit_status == "PASS"
    )
    refused_text = "; ".join(
        f"H={metrics.horizon_s:g} s refused ({metrics.leakage_audit_status})"
        for metrics in study.horizons
        if metrics.refusal_reason
    ) or "none refused"
    lines = [
        "# W13 primary horizon decision",
        "",
        f"**Category: {decision.display_category}**",
        "",
        f"- Study completeness: {completed} of {len(study.horizons)} horizons "
        f"evaluated under the grouped pipeline; {refused_text}",
        f"- Primary horizon: {_fmt(decision.primary_horizon_s)} (NOT_FROZEN)",
        f"- Provisional candidates (s): "
        f"{', '.join(f'{h:g}' for h in decision.provisional_candidates_s) or 'none'}",
        f"- Deprioritized by physics proxy (s): "
        f"{', '.join(f'{h:g}' for h in decision.deprioritized_s) or 'none'}",
        "",
        "## Selection preconditions",
        "",
        "| precondition | satisfied |",
        "|---|---|",
    ]
    for name, ok in decision.selection_preconditions.items():
        lines.append(f"| {name} | {_fmt(ok)} |")
    lines += ["", "## Blockers", ""]
    lines += [f"- `{blocker}`" for blocker in decision.blockers]
    lines += ["", "## Rationale", ""]
    lines += [f"- {item}" for item in decision.rationale]
    lines += [
        "",
        "## What would close the blockers (owners, not B unilateral actions)",
        "",
        "- Member D: freeze the critical Tmean threshold / candidate critical "
        "definition (safety contract; A-W10-05 / A-W13-03 INCOMPLETE).",
        "- Member A: once D freezes, the door->critical evaluation is a pure "
        "offline rerun on the existing S2 windows (0 new physical "
        "measurements); supervised captures remain A's authority.",
        "- Member C / D: transport decision for the network command path "
        "(GAP-NETWORK-COMMAND-LATENCY) before any measured latency chain.",
        "- Leader: PR #95 merge decision; until merged it stays "
        "NOT_VERIFIED_FOR_CANONICAL_USE.",
        "- Member B (next W13 cycle, only after the above): freeze the "
        "selection rule before outcomes, re-run the real grouped evaluation, "
        "and only then consider PRIMARY_CANDIDATE_SELECTED.",
        "",
        "## Boundaries honored",
        "",
        f"- Synthetic AP (fixture `{study.fixture_dataset_id}`) was never "
        "decision-grade; no horizon was chosen on the locked test.",
        f"- Real predictive eligibility: {reconciliation.predictive_eligible_runs} "
        "runs; real metrics are NOT_ESTIMABLE, not zero.",
        "- This decision freezes nothing: T_critical, representative "
        "temperature and the primary horizon remain open ledger items.",
        "",
    ]
    return "\n".join(lines)


def _scientific_verdicts(
    study: HorizonStudy,
    reconciliation: DatasetReconciliation,
    decision: HorizonDecision,
) -> dict[str, str]:
    audits_ok = all(
        metrics.leakage_audit_status in ("PASS", "NOT_RUN_HORIZON_REFUSED")
        for metrics in study.horizons
    )
    completed = sum(
        1 for metrics in study.horizons if metrics.leakage_audit_status == "PASS"
    )
    refused = any(metrics.refusal_reason for metrics in study.horizons)
    return {
        "W13_SOFTWARE": "GREEN" if audits_ok else "REVIEW_PENDING",
        "HORIZON_EVALUATION_COMPLETENESS": (
            f"PARTIAL_{completed}_OF_{len(study.horizons)}_HORIZONS"
        ),
        "W11_PIPELINE_DEFECT": (
            "OPEN_EMPTY_RUN_POPULATION_MAX_ERROR_NOT_FIXED_IN_W13"
            if refused
            else "NOT_OBSERVED"
        ),
        "SYNTHETIC_HORIZON_STUDY": "SOFTWARE_CONTROL_ONLY",
        "REAL_PREDICTIVE_ADMISSION": (
            "REFUSED_NO_ELIGIBLE_RUNS"
            if reconciliation.predictive_eligible_runs == 0
            else "REVIEW_PENDING"
        ),
        "HORIZON_DECISION": decision.category,
        "PRIMARY_HORIZON_FROZEN": "NOT_FROZEN",
        "REAL_EWT": "NOT_ESTIMABLE",
        "REAL_AIW": "NOT_ESTIMABLE",
        "LOCKED_TEST": "UNTOUCHED",
    }


def _manifest(
    *,
    reconciliation: DatasetReconciliation,
    timing: PlantTiming,
    screenings: Sequence[HorizonScreening],
    study: HorizonStudy,
    decision: HorizonDecision,
    artifact_hashes: Mapping[str, str],
    dataset_csv_hashes: Mapping[str, str],
    repository_revision: str,
    command: str,
    analysis_code_sha256: str,
) -> dict[str, Any]:
    return {
        "schema": W13_MANIFEST_SCHEMA,
        "layer_version": W13_LAYER_VERSION,
        "generated_at_utc": "NOT_RECORDED_BY_DESIGN",
        "repository_revision": repository_revision,
        "generation_command": command,
        "analysis_code_sha256": analysis_code_sha256,
        "package_versions": package_versions(),
        "deterministic": True,
        "repository_inputs": {
            "a_timing_report": {
                "path": "evidence/A/W13/plant-timing-report.json",
                "sha256": A_W13_TIMING_REPORT_SHA256,
                "source_revision": A_SOURCE_REVISION,
            },
            "a_20261107_package": {
                "source_revision": A_SOURCE_REVISION,
                "merge_provenance": "origin/main PR #91 (merged canonical)",
                "consumption": "READ_ONLY_GIT_ARCHIVE_EXPORT_NEVER_REBASE",
                "export_command": (
                    f"git archive {A_SOURCE_REVISION} "
                    "evidence/A/SOURCES/20261107/datasets | tar -x -C <export-dir>"
                ),
                "run_index_sha256": A_20261107_RUN_INDEX_SHA256,
                "manifest_sha256": A_20261107_MANIFEST_SHA256,
                "dataset_csv_sha256": dict(sorted(dataset_csv_hashes.items())),
            },
            "pr95_supplement": dict(reconciliation.pr95_supplement),
        },
        "artifacts": {
            name: {"file": name, "sha256": artifact_hashes[name]}
            for name in sorted(artifact_hashes)
        },
        "scientific_verdicts": _scientific_verdicts(study, reconciliation, decision),
        "hard_boundaries": list(HARD_BOUNDARIES),
        "validations": [
            "A timing report, run_index and manifest SHA-256 pins verified",
            "every consumed normalized dataset CSV hashed against the "
            "manifest output pin",
            "manifest totals reconciled with run_index rows and frame sum",
            "leakage audits passed on every evaluated horizon; the refused "
            "horizon's audit was not run and is marked NOT_RUN_HORIZON_REFUSED",
            "single-class and censored populations reported as undefined / "
            "excluded, never imputed",
            "decision derived from preconditions, never from synthetic AP",
        ],
        "reconciliation": reconciliation.to_dict(),
        "plant_timing": timing.to_dict(),
        "candidate_screenings": [item.to_dict() for item in screenings],
        "study": study.to_dict(),
        "decision": decision.to_dict(),
    }


def _read_normalized_header(
    dataset_dir: Path, first_dataset_path: str, expected_sha256: str
) -> list[str]:
    csv_path = dataset_dir / first_dataset_path
    payload = csv_path.read_bytes()
    verify_sha256(payload, expected_sha256, f"dataset {csv_path.name}")
    return next(csv.reader(io.StringIO(payload.decode("utf-8"))))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ColdGuard W13 horizon engineering: evidence reconciliation, "
            "candidate screening, grouped sensitivity study, decision gate. "
            "Synthetic results are software controls, never physical evidence."
        )
    )
    parser.add_argument("--out", default="reports/W13")
    parser.add_argument("--feature-registry", default="feature-registry-v1.yaml")
    parser.add_argument("--config", default="xgb-v1-config.yaml")
    parser.add_argument(
        "--a-timing-report", default="../evidence/A/W13/plant-timing-report.json"
    )
    parser.add_argument(
        "--a-dataset-dir", default="../evidence/A/SOURCES/20261107/datasets"
    )
    parser.add_argument("--repository-revision", default=None)
    args = parser.parse_args(argv)
    ml_root = Path(__file__).resolve().parents[1]
    repo_root = ml_root.parent
    out_dir = (ml_root / args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in ARTIFACT_NAMES:
        (out_dir / stale).unlink(missing_ok=True)
    revision = args.repository_revision or _git_revision(repo_root)
    command = (
        "python scripts/horizon-study-W13.py "
        "--a-dataset-dir <A_DATASET_EXPORT>/evidence/A/SOURCES/20261107/datasets "
        f"--out reports/W13 --repository-revision {revision}"
    )
    timing_path = (ml_root / args.a_timing_report).resolve()
    dataset_dir = (ml_root / args.a_dataset_dir).resolve()
    registry_path = (ml_root / args.feature_registry).resolve()
    config_path = (ml_root / args.config).resolve()
    try:
        if not dataset_dir.is_dir():
            raise CliError(
                "the A 20261107 package is absent from this checkout (it is "
                "merged on origin/main, not in the W12 stack ancestry); "
                "export it read-only: git archive "
                f"{A_SOURCE_REVISION} evidence/A/SOURCES/20261107/datasets "
                "| tar -x -C <export-dir>, then pass --a-dataset-dir "
                "<export-dir>/evidence/A/SOURCES/20261107/datasets"
            )
        timing_bytes = timing_path.read_bytes()
        verify_sha256(
            timing_bytes, A_W13_TIMING_REPORT_SHA256, "A W13 plant-timing-report"
        )
        timing = load_plant_timing(json.loads(timing_bytes.decode("utf-8")))
        run_index_bytes = (dataset_dir / "run_index.csv").read_bytes()
        manifest_bytes = (dataset_dir / "manifest.json").read_bytes()
        manifest_payload = json.loads(manifest_bytes.decode("utf-8"))
        manifest_output_pins = {
            entry["package_path"]: entry["sha256"]
            for entry in manifest_payload.get("outputs", [])
        }
        if (
            manifest_output_pins.get("datasets/published/plant-timing-report.json")
            != A_W13_TIMING_REPORT_SHA256
        ):
            raise CliError(
                "the package manifest's plant-timing pin disagrees with the "
                "consumed timing report; evidence sets are inconsistent"
            )
        registry = load_registry(registry_path)
        config = load_benchmark_config(config_path, registry)
        header = _read_normalized_header(
            dataset_dir,
            "datasets/W10-02-normalized.csv",
            manifest_output_pins.get("datasets/W10-02-normalized.csv", ""),
        )
        reconciliation = reconcile_a_dataset(
            run_index_bytes,
            manifest_bytes,
            normalized_header=header,
            timing=timing,
            critical_criterion_frozen=(
                config.label.frozen_at is not None
                and config.label.boundary_c is not None
            ),
        )
        dataset_csv_hashes: dict[str, str] = {}
        for source in reconciliation.sources:
            csv_path = dataset_dir / source.dataset_path
            digest = verify_sha256(
                csv_path.read_bytes(), source.dataset_sha256, f"dataset {csv_path.name}"
            )
            dataset_csv_hashes[csv_path.name] = digest
        screenings = screen_horizon_candidates(timing, CANDIDATE_HORIZONS_S)
        fixture = build_expanded_w11_fixture()
        with tempfile.TemporaryDirectory(prefix="coldguard-w13-models-") as scratch:
            study = run_horizon_study(
                fixture,
                registry,
                config,
                model_out_dir=Path(scratch),
                horizons=CANDIDATE_HORIZONS_S,
                spec_version=W13_LABEL_SPEC_VERSION,
            )
        decision = decide_primary_horizon(
            study, reconciliation, timing, config, screenings
        )
        artifact_hashes: dict[str, str] = {}
        study_bytes = _study_report_markdown(
            reconciliation, timing, screenings, study, decision
        ).encode("utf-8")
        (out_dir / "horizon-study.md").write_bytes(study_bytes)
        artifact_hashes["horizon-study.md"] = _sha256_bytes(study_bytes)
        csv_bytes = _csv_text(
            horizon_metrics_csv_rows(study, reconciliation), CSV_COLUMNS
        ).encode("utf-8")
        (out_dir / "horizon-metrics.csv").write_bytes(csv_bytes)
        artifact_hashes["horizon-metrics.csv"] = _sha256_bytes(csv_bytes)
        decision_bytes = _decision_markdown(
            decision, reconciliation, study
        ).encode("utf-8")
        (out_dir / "primary-horizon-decision.md").write_bytes(decision_bytes)
        artifact_hashes["primary-horizon-decision.md"] = _sha256_bytes(decision_bytes)
        manifest = _manifest(
            reconciliation=reconciliation,
            timing=timing,
            screenings=screenings,
            study=study,
            decision=decision,
            artifact_hashes=artifact_hashes,
            dataset_csv_hashes=dataset_csv_hashes,
            repository_revision=revision,
            command=command,
            analysis_code_sha256=_analysis_code_sha256(ml_root),
        )
        manifest_bytes_out = (
            json.dumps(manifest, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        (out_dir / "horizon-manifest-W13.json").write_bytes(manifest_bytes_out)
        print(
            "W13 horizon study complete: "
            f"decision={decision.category} "
            f"real_eligible={reconciliation.predictive_eligible_runs} "
            f"horizons={len(study.horizons)} artifacts={out_dir}"
        )
        return 0
    except Exception as exc:  # fail closed; no partial success claim
        print(f"W13 REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())