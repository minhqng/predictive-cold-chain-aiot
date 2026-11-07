#!/usr/bin/env python3
"""ColdGuard W10 causal feature pipeline CLI.

Generates the W10 registry identity, synthetic development feature rows,
real A diagnostic feature view, development label pilot and audit artifacts.

Usage::

    python scripts/feature-pipeline-W10.py --out reports/W10
        [--registry ../feature-registry-v1.yaml]
        [--a-capture ../evidence/A/W09/exports/CG-S1-H8C-600S.json]
        [--a-w08-manifest reports/W08/gate-b-manifest-W08.json]
        [--repository-revision REV]

Exit codes:

* ``0`` — pipeline completed. A development-only or NOT_EVALUABLE scientific
  result is a successful run.
* ``1`` — invalid configuration, malformed registry/W08 manifest or I/O.
* ``2`` — refused because the requested output would fabricate evidence.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

try:  # installed package
    from coldguard_ml import load_capture
    from coldguard_ml.feature_fixtures import (
        FIXTURE_VERSION,
        build_development_dataset,
    )
    from coldguard_ml.feature_pipeline import (
        ELIGIBILITY_BLOCKED,
        EXCLUSION_ABSOLUTE_TIME_UNAVAILABLE,
        EXCLUSION_A_LEDGER_INVALID,
        EXCLUSION_NO_S2_EVIDENCE,
        EXCLUSION_RUN_IDENTITY_UNRESOLVED,
        MISSING_INSUFFICIENT_HISTORY,
        OUTPUT_DIAGNOSTIC,
        OUTPUT_ELIGIBLE,
        OUTPUT_REJECTED,
        OUTPUT_SYNTHETIC,
        PRESENT,
        FeatureRow,
        Trajectory,
        feature_rows,
        feature_schema_identity,
        summarize_feature_rows,
        trajectory_from_capture,
    )
    from coldguard_ml.feature_plot import (
        render_real_diagnostic,
        render_synthetic_audit,
    )
    from coldguard_ml.feature_registry import FeatureRegistry, load_registry
    from coldguard_ml.label_pilot import (
        CANDIDATE_HORIZONS_S,
        assess_real_pilot,
        run_label_pilot,
    )
except ModuleNotFoundError:  # direct checkout invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml import load_capture
    from coldguard_ml.feature_fixtures import (
        FIXTURE_VERSION,
        build_development_dataset,
    )
    from coldguard_ml.feature_pipeline import (
        ELIGIBILITY_BLOCKED,
        EXCLUSION_ABSOLUTE_TIME_UNAVAILABLE,
        EXCLUSION_A_LEDGER_INVALID,
        EXCLUSION_NO_S2_EVIDENCE,
        EXCLUSION_RUN_IDENTITY_UNRESOLVED,
        MISSING_INSUFFICIENT_HISTORY,
        OUTPUT_DIAGNOSTIC,
        OUTPUT_ELIGIBLE,
        OUTPUT_REJECTED,
        OUTPUT_SYNTHETIC,
        PRESENT,
        FeatureRow,
        Trajectory,
        feature_rows,
        feature_schema_identity,
        summarize_feature_rows,
        trajectory_from_capture,
    )
    from coldguard_ml.feature_plot import (
        render_real_diagnostic,
        render_synthetic_audit,
    )
    from coldguard_ml.feature_registry import FeatureRegistry, load_registry
    from coldguard_ml.label_pilot import (
        CANDIDATE_HORIZONS_S,
        assess_real_pilot,
        run_label_pilot,
    )

W10_LAYER_VERSION = "coldguard-w10-causal-feature-pipeline-v1"
W10_MANIFEST_SCHEMA = "coldguard-w10-feature-pipeline-manifest-v1"
W10_REPORT_SCHEMA = "coldguard-w10-s2-feature-report-v1"
DEVELOPMENT_PARTITIONS = ("train", "validation")


class PipelineRefusal(RuntimeError):
    pass


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _analysis_code_sha256() -> str:
    package_dir = Path(__file__).resolve().parents[1] / "src" / "coldguard_ml"
    paths = {
        Path(__file__).resolve(),
        package_dir / "feature_registry.py",
        package_dir / "feature_pipeline.py",
        package_dir / "feature_fixtures.py",
        package_dir / "feature_plot.py",
        package_dir / "label_pilot.py",
        package_dir / "labels.py",
        package_dir / "observations.py",
        package_dir / "splitting.py",
        package_dir / "intake.py",
        package_dir / "plant_eda.py",
        package_dir / "__init__.py",
    }
    hasher = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


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


def _load_w08(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "physical_gate" not in payload or "observed_status" not in payload["physical_gate"]:
        raise PipelineRefusal(
            "W08 manifest does not declare physical_gate.observed_status"
        )
    return payload


def _rows_for_partitions(
    trajectories: Iterable[Trajectory],
    registry: FeatureRegistry,
    dataset,
) -> dict[str, tuple[FeatureRow, ...]]:
    rows_by_run: dict[str, tuple[FeatureRow, ...]] = {}
    for trajectory in trajectories:
        if trajectory.run_id is None:
            continue
        partition = dataset.partition_of(trajectory.run_id)
        rows_by_run[trajectory.run_id] = feature_rows(
            trajectory, registry, partition=partition, split=dataset.split
        )
    return rows_by_run


def _door_transition_count(trajectory: Trajectory) -> int:
    count = 0
    previous = None
    for sample in trajectory.samples:
        trusted = (
            sample.door_state in ("OPEN", "CLOSED")
            and sample.door_quality == "VALID"
            and sample.door_polarity_attested
        )
        state = sample.door_state if trusted else None
        if state == "OPEN" and previous == "CLOSED":
            count += 1
        previous = state
    return count


def _mutate_after(trajectory: Trajectory, anchor_s: float) -> Trajectory:
    mutated = []
    for sample in trajectory.samples:
        if sample.time_s > anchor_s:
            sample = dataclasses.replace(
                sample,
                chamber_c=tuple(
                    (role, None if value is None else value + 5.0)
                    for role, value in sample.chamber_c
                ),
                hot_side_c=None if sample.hot_side_c is None else sample.hot_side_c + 5.0,
                door_state="CLOSED",
                door_quality="VALID",
                door_polarity_attested=True,
                applied_cooling="OFF",
                applied_duty=0.0,
                cooling_power_w=None,
                cooling_voltage_v=None,
                cooling_current_a=None,
                cooling_energy_counter_wh=None,
                electrical_quality="INVALID",
                thermal_quality="VALID",
            )
        mutated.append(sample)
    return dataclasses.replace(trajectory, samples=tuple(mutated))


def _truncate(trajectory: Trajectory, anchor_s: float) -> Trajectory:
    return dataclasses.replace(
        trajectory,
        samples=tuple(
            sample for sample in trajectory.samples if sample.time_s <= anchor_s
        ),
    )


def _compare_rows(
    left: Sequence[FeatureRow], right: Sequence[FeatureRow], *, max_anchor: float
) -> bool:
    left_rows = [row for row in left if row.anchor_t_s <= max_anchor]
    right_rows = [row for row in right if row.anchor_t_s <= max_anchor]
    if len(left_rows) != len(right_rows):
        return False
    return all(
        a.anchor_t_s == b.anchor_t_s
        and a.values == b.values
        and a.missing_reasons == b.missing_reasons
        for a, b in zip(left_rows, right_rows)
    )


def _rows_json(rows: Sequence[FeatureRow], registry: FeatureRegistry) -> str:
    return json.dumps(
        [row.to_dict(registry.feature_ids) for row in rows],
        sort_keys=True,
        separators=(",", ":"),
    )


def _feature_summary_csv(rows: Sequence[Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "population",
            "feature_id",
            "family",
            "anchors",
            "produced",
            "missing_total",
            "missing_by_reason",
            "first_eligible_anchor_s",
            "first_value_anchor_s",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.population,
                row.feature_id,
                row.family,
                row.anchors,
                row.produced,
                row.anchors - row.produced,
                json.dumps(dict(row.missing_by_reason), sort_keys=True),
                "" if row.first_eligible_anchor_s is None else row.first_eligible_anchor_s,
                "" if row.first_value_anchor_s is None else row.first_value_anchor_s,
            ]
        )
    return buffer.getvalue()


def _label_pilot_csv(result: Any, real_status: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "population",
            "horizon_s",
            "status",
            "independent_development_runs",
            "dependent_window_count",
            "positive_labels",
            "negative_labels",
            "censored_labels",
            "untrusted_labels",
            "positive_prevalence",
            "feature_available_anchors",
            "feature_values_present",
            "feature_values_total",
            "freeze_status",
            "coverage_limitations",
        ]
    )
    for horizon in result.horizons:
        writer.writerow(
            [
                result.population,
                horizon.horizon_s,
                result.status,
                horizon.independent_runs,
                horizon.anchors,
                horizon.positive,
                horizon.negative,
                horizon.censored,
                horizon.untrusted,
                "" if horizon.prevalence is None else horizon.prevalence,
                horizon.feature_available_anchors,
                horizon.feature_values_present,
                horizon.feature_values_total,
                horizon.freeze_status,
                "; ".join(horizon.coverage_limitations),
            ]
        )
    writer.writerow(
        [
            "REAL_S2",
            "",
            real_status["REAL_S2_LABEL_PILOT"],
            real_status["ELIGIBLE_S2_RUNS"],
            0,
            0,
            0,
            0,
            0,
            "",
            0,
            0,
            0,
            "NOT_FROZEN",
            real_status["reason"],
        ]
    )
    return buffer.getvalue()


def _report_markdown(
    registry: FeatureRegistry,
    dataset,
    rows_by_run: dict[str, tuple[FeatureRow, ...]],
    audit_run_id: str,
    synthetic: dict[str, Any],
    real: dict[str, Any],
    pilot,
    real_pilot: dict[str, Any],
    w08: dict[str, Any],
) -> str:
    identity = feature_schema_identity(registry)
    lines = [
        "# W10 S2 causal feature report",
        "",
        "> Software pipeline report. Synthetic results are software controls, "
        "never physical evidence. The real A capture is diagnostic only: Gate B "
        "is RED and no eligible S2 disturbance exists.",
        "",
        "## 1. Scientific status",
        "",
        "| Domain | Status |",
        "|---|---|",
        f"| W10 software | {synthetic['software_status']} |",
        "| Independent review | RECORDED_IN_STACKED_PR |",
        f"| Physical Gate B | {w08['physical_gate']} |",
        "| Eligible real S2 data | NOT_AVAILABLE |",
        f"| Real label pilot | {real_pilot['REAL_S2_LABEL_PILOT']} |",
        "| Feature causality | VERIFIED_BY_TESTS |",
        "| Real predictive benchmark | NOT_ESTABLISHED |",
        "",
        "## 2. Frozen feature registry identity",
        "",
        f"- Feature schema version: `{identity['feature_schema_version']}`",
        f"- Registry SHA-256: `{identity['registry_sha256']}`",
        f"- Feature count: {identity['feature_count']}",
        f"- Freeze status: `{registry.registry_status}`",
        "- Frozen scope: " + ", ".join(registry.frozen_scope),
        "- Not frozen here: " + ", ".join(registry.not_frozen_here),
        "",
        "| Family | Features |",
        "|---|---|",
    ]
    for family, feature_ids in identity["features_by_family"].items():
        lines.append(f"| `{family}` | {', '.join(f'`{item}`' for item in feature_ids)} |")
    lines.extend(
        [
            "",
            "Role policy: `CHAMBER_CENTER`, `CHAMBER_BOTTOM` and `CHAMBER_NEAR_DOOR` "
            "form the chamber-air aggregate; `TEC_HOT_SIDE` is a separate "
            "diagnostic feature and is never averaged into chamber air.",
            "",
            "## 3. Pipeline and split discipline",
            "",
            f"- Synthetic fixture version: `{dataset.fixture_version}`",
            f"- Paired grouped split seed: {dataset.split.seed} "
            f"(groups: {len(set(dataset.split.group_of.values()))})",
            f"- Train runs: {', '.join(dataset.split.train_runs)}",
            f"- Validation runs: {', '.join(dataset.split.validation_runs)}",
            f"- Test runs (untouched by W10): {', '.join(dataset.split.test_runs)}",
            "- Pair lineage: paired S1/S2 runs share one partition; no row-level split.",
            "- Rolling features use the `(t - lookback, t]` convention on actual "
            "event time; no future sample, no sample-count padding, no "
            "cross-boot continuity.",
            "",
            "## 4. Software-only synthetic S2 controls",
            "",
            f"- Development trajectories analysed: {synthetic['development_runs']}",
            f"- Door openings (trusted transitions): {synthetic['door_transitions']}",
            f"- Feature anchors: {synthetic['feature_anchors']}",
            f"- Feature values present: {synthetic['feature_values_present']} "
            f"of {synthetic['feature_values_total']}",
            f"- Candidate horizons: {synthetic['candidate_horizons']}",
            f"- Future-perturbation invariance: {synthetic['future_perturbation']}",
            f"- Future-truncation invariance: {synthetic['future_truncation']}",
            f"- Deterministic recompute: {synthetic['deterministic_recompute']}",
            "",
            "Synthetic label-pilot counts (development partitions only):",
            "",
            "| H (s) | Runs | Anchors | Positive | Negative | Censored | Untrusted | Prevalence |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for horizon in pilot.horizons:
        prevalence = "undefined" if horizon.prevalence is None else f"{horizon.prevalence:.4f}"
        lines.append(
            f"| {horizon.horizon_s:g} | {horizon.independent_runs} | {horizon.anchors} | "
            f"{horizon.positive} | {horizon.negative} | {horizon.censored} | "
            f"{horizon.untrusted} | {prevalence} |"
        )
    lines.extend(
        [
            "",
            "A single-class population is not evidence that supervised evaluation "
            "is ready. No model was trained and no AP benchmark was computed.",
            "",
            "## 5. Real A W09 diagnostic feature view",
            "",
            f"- Source: `{real['source_path']}`",
            f"- Source SHA-256: `{real['source_sha256']}`",
            f"- Rows: {real['rows']}",
            f"- Boot id: `{real['boot_id']}`",
            f"- Run identity: {real['run_identity']}",
            f"- Time domain: `{real['time_domain']}` (absolute device UTC not evidenced)",
            f"- W08 Gate B: `{w08['physical_gate']}`; A ledger: `{w08['a_ledger_verdict']}`",
            f"- Eligible S1 runs: {real['eligible_s1_runs']}; eligible S2 runs: {real['eligible_s2_runs']}",
            f"- Door openings observed: {real['door_openings']}",
            f"- Diagnostic feature rows: {real['feature_rows']}",
            f"- Diagnostic feature values present: {real['feature_values_present']}",
            f"- Eligible real S2 feature rows: {real['eligible_s2_feature_rows']}",
            f"- Real label pilot: `{real_pilot['REAL_S2_LABEL_PILOT']}`",
            "",
            "The real capture carries boot-scoped uptime, no verified absolute UTC, "
            "unresolved run identity, electrical quality UNKNOWN and an unconfirmed "
            "door polarity. Door and electrical features stay missing; no S2 door "
            "opening is inferred. T2 hot side is plotted separately and excluded "
            "from chamber air.",
            "",
            "## 6. First-valid-timestamp audit (synthetic development)",
            "",
            "| Feature | First eligible anchor (s) | First value anchor (s) | Missing reasons |",
            "|---|---|---|---|",
        ]
    )
    summary = summarize_feature_rows(
        [row for rows in rows_by_run.values() for row in rows],
        registry,
        population="SYNTHETIC_DEVELOPMENT",
    )
    for row in summary:
        reasons = ", ".join(
            f"`{reason}`={count}" for reason, count in row.missing_by_reason
        ) or "none"
        lines.append(
            f"| `{row.feature_id}` | {'' if row.first_eligible_anchor_s is None else row.first_eligible_anchor_s} | "
            f"{'' if row.first_value_anchor_s is None else row.first_value_anchor_s} | {reasons} |"
        )
    lines.extend(
        [
            "",
            "## 7. Artifacts",
            "",
            "```text",
            "ml/feature-registry-v1.yaml",
            "ml/src/coldguard_ml/feature_registry.py",
            "ml/src/coldguard_ml/feature_pipeline.py",
            "ml/src/coldguard_ml/feature_fixtures.py",
            "ml/src/coldguard_ml/feature_plot.py",
            "ml/src/coldguard_ml/label_pilot.py",
            "ml/scripts/feature-pipeline-W10.py",
            "ml/tests/test_feature_registry.py",
            "ml/tests/test_feature_causality.py",
            "ml/tests/test_feature_pipeline.py",
            "ml/reports/W10/S2-feature-report.md",
            "ml/reports/W10/feature-audit-W10.svg",
            "ml/reports/W10/real-diagnostic-W10.svg",
            "ml/reports/W10/feature-summary-W10.csv",
            "ml/reports/W10/label-pilot-W10.csv",
            "ml/reports/W10/feature-manifest-W10.json",
            "```",
            "",
            "## 8. Boundaries",
            "",
            "- No model training, no AP benchmark, no W11/W12 work.",
            "- No merge, no locked-test access, no physical operation.",
            "- No physical threshold, representative temperature or primary horizon "
            "is frozen by this report.",
            "",
            f"Audit trajectory: `{audit_run_id}` (software-only synthetic control).",
        ]
    )
    return "\n".join(lines) + "\n"


def build_artifacts(
    *,
    registry_path: Path,
    capture_path: Path,
    w08_path: Path,
    repository_revision: str,
    command: str,
) -> dict[str, bytes]:
    registry = load_registry(registry_path)
    w08 = _load_w08(w08_path)
    physical_gate = w08["physical_gate"]["observed_status"]
    reason_codes = tuple(w08["physical_gate"].get("reason_codes", ()))
    w08_summary = {
        "physical_gate": physical_gate,
        "a_ledger_verdict": (
            "INVALID" if "AUTHORITY_A_LEDGER_INVALID" in reason_codes else "UNKNOWN"
        ),
    }
    dataset = build_development_dataset()
    development = [
        trajectory
        for trajectory in dataset.trajectories
        if dataset.partition_of(trajectory.run_id or "") in DEVELOPMENT_PARTITIONS
    ]
    test_rows = [
        trajectory
        for trajectory in dataset.trajectories
        if dataset.partition_of(trajectory.run_id or "") == "test"
    ]
    rows_by_run = _rows_for_partitions(development, registry, dataset)
    all_rows = [row for rows in rows_by_run.values() for row in rows]

    pilot = run_label_pilot(
        development,
        dataset.series_by_run,
        rows_by_run,
        partitions=DEVELOPMENT_PARTITIONS,
        population="SYNTHETIC_DEVELOPMENT",
    )

    audit_candidates = [
        trajectory
        for trajectory in development
        if trajectory.scenario_id == "S2"
        and dataset.partition_of(trajectory.run_id or "") == "train"
    ]
    if not audit_candidates:
        raise PipelineRefusal("no synthetic S2 train trajectory for the audit plot")
    audit_trajectory = sorted(
        audit_candidates, key=lambda item: item.run_id or ""
    )[0]
    audit_rows = rows_by_run[audit_trajectory.run_id]  # type: ignore[index]

    anchor_s = 60.0
    baseline_rows = feature_rows(
        audit_trajectory,
        registry,
        partition=dataset.partition_of(audit_trajectory.run_id or ""),
        split=dataset.split,
    )
    mutated_rows = feature_rows(
        _mutate_after(audit_trajectory, anchor_s),
        registry,
        partition=dataset.partition_of(audit_trajectory.run_id or ""),
        split=dataset.split,
    )
    truncated_rows = feature_rows(
        _truncate(audit_trajectory, anchor_s),
        registry,
        partition=dataset.partition_of(audit_trajectory.run_id or ""),
        split=dataset.split,
    )
    future_ok = _compare_rows(baseline_rows, mutated_rows, max_anchor=anchor_s)
    truncation_ok = _compare_rows(baseline_rows, truncated_rows, max_anchor=anchor_s)
    deterministic_ok = _rows_json(baseline_rows, registry) == _rows_json(
        feature_rows(
            audit_trajectory,
            registry,
            partition=dataset.partition_of(audit_trajectory.run_id or ""),
            split=dataset.split,
        ),
        registry,
    )
    if not (future_ok and truncation_ok and deterministic_ok):
        raise PipelineRefusal("causal or deterministic verification failed")

    capture = load_capture(capture_path)
    real_trajectories = trajectory_from_capture(
        capture,
        physical_eligibility=ELIGIBILITY_BLOCKED,
        exclusion_reasons=(
            EXCLUSION_RUN_IDENTITY_UNRESOLVED,
            EXCLUSION_ABSOLUTE_TIME_UNAVAILABLE,
            EXCLUSION_A_LEDGER_INVALID,
            EXCLUSION_NO_S2_EVIDENCE,
            *tuple(w08["physical_gate"].get("reason_codes", ())),
        ),
    )
    real_rows = [
        row
        for trajectory in real_trajectories
        for row in feature_rows(trajectory, registry, partition=None)
    ]
    if not real_rows:
        raise PipelineRefusal("the real capture produced no diagnostic feature rows")
    real_pilot = assess_real_pilot(
        eligible_s2_runs=0,
        authoritative_series_present=False,
        gate_b_physical=physical_gate,
    )
    if physical_gate == "RED" and any(
        row.output_class == OUTPUT_ELIGIBLE for row in real_rows
    ):
        raise PipelineRefusal("a RED Gate B cannot produce eligible feature rows")

    synthetic = {
        "software_status": "GREEN",
        "development_runs": len(development),
        "door_transitions": sum(
            _door_transition_count(trajectory) for trajectory in development
        ),
        "feature_anchors": len(all_rows),
        "feature_values_present": sum(
            1 for row in all_rows for reason in row.missing_reasons if reason == PRESENT
        ),
        "feature_values_total": sum(len(row.missing_reasons) for row in all_rows),
        "candidate_horizons": list(CANDIDATE_HORIZONS_S),
        "future_perturbation": "PASS" if future_ok else "FAIL",
        "future_truncation": "PASS" if truncation_ok else "FAIL",
        "deterministic_recompute": "PASS" if deterministic_ok else "FAIL",
        "labelled_anchors": sum(horizon.anchors for horizon in pilot.horizons),
        "label_observations": sum(horizon.anchors for horizon in pilot.horizons),
        "censored_or_untrusted_label_observations": sum(
            horizon.censored + horizon.untrusted for horizon in pilot.horizons
        ),
        "test_runs_used": 0,
        "test_runs_recorded": [trajectory.run_id for trajectory in test_rows],
    }
    real = {
        "source_path": str(capture_path).replace("\\", "/"),
        "source_sha256": capture.source.sha256,
        "rows": len(capture.rows),
        "boot_id": capture.run.boot_id,
        "run_identity": capture.run.run_id_status,
        "time_domain": capture.time.domain,
        "feature_rows": len(real_rows),
        "feature_values_present": sum(
            1 for row in real_rows for reason in row.missing_reasons if reason == PRESENT
        ),
        "eligible_s2_feature_rows": sum(
            1 for row in real_rows if row.output_class == OUTPUT_ELIGIBLE
        ),
        "door_openings": sum(
            _door_transition_count(trajectory) for trajectory in real_trajectories
        ),
        "eligible_s1_runs": 0,
        "eligible_s2_runs": 0,
        "output_classes": {
            OUTPUT_SYNTHETIC: 0,
            OUTPUT_DIAGNOSTIC: len(real_rows),
            OUTPUT_ELIGIBLE: 0,
            OUTPUT_REJECTED: 0,
        },
    }
    audit_svg = render_synthetic_audit(
        audit_trajectory,
        audit_rows,
        registry,
        anchor_s=anchor_s,
        horizons_s=(30.0, 60.0, 120.0),
    )
    real_svg = render_real_diagnostic(
        real_trajectories[0], real_rows, registry
    )
    summary_csv = _feature_summary_csv(
        list(
            summarize_feature_rows(
                all_rows, registry, population="SYNTHETIC_DEVELOPMENT"
            )
        )
        + list(
            summarize_feature_rows(
                real_rows, registry, population="REAL_A_DIAGNOSTIC"
            )
        )
    )
    label_csv = _label_pilot_csv(pilot, real_pilot)
    report = _report_markdown(
        registry,
        dataset,
        rows_by_run,
        audit_trajectory.run_id or "",
        synthetic,
        real,
        pilot,
        real_pilot,
        w08_summary,
    )
    artifacts = {
        "feature-audit-W10.svg": audit_svg.encode("utf-8"),
        "real-diagnostic-W10.svg": real_svg.encode("utf-8"),
        "feature-summary-W10.csv": summary_csv.encode("utf-8"),
        "label-pilot-W10.csv": label_csv.encode("utf-8"),
        "S2-feature-report.md": report.encode("utf-8"),
    }
    manifest = {
        "schema": W10_MANIFEST_SCHEMA,
        "layer_version": W10_LAYER_VERSION,
        "report_schema": W10_REPORT_SCHEMA,
        "registry": feature_schema_identity(registry),
        "registry_policy": dict(registry.policy),
        "role_map": dict(registry.role_map),
        "fixture": {
            "version": FIXTURE_VERSION,
            "source_type": "SYNTHETIC_FIXTURE",
            "physical_authority": False,
        },
        "split": {
            "seed": dataset.split.seed,
            "train_runs": list(dataset.split.train_runs),
            "validation_runs": list(dataset.split.validation_runs),
            "test_runs": list(dataset.split.test_runs),
            "pair_lineage": list(dataset.split.pair_lineage),
            "test_partition_used": False,
        },
        "synthetic": synthetic,
        "real_a": real,
        "real_label_pilot": real_pilot,
        "w08": {
            "path": str(w08_path).replace("\\", "/"),
            "sha256": _sha256_file(w08_path),
            "physical_gate": physical_gate,
            "predictive_gate": (
                w08.get("predictive_gate", {}).get("observed_status", "NOT_READY")
                if isinstance(w08.get("predictive_gate"), dict)
                else "NOT_READY"
            ),
            "gate_preserved": True,
        },
        "verification": {
            "future_perturbation": synthetic["future_perturbation"],
            "future_truncation": synthetic["future_truncation"],
            "deterministic_recompute": synthetic["deterministic_recompute"],
            "eligible_rows_under_red_gate": 0,
            "locked_test_rows": 0,
        },
        "artifacts": {
            name: {"sha256": _sha256_bytes(payload), "bytes": len(payload)}
            for name, payload in sorted(artifacts.items())
        },
        "analysis_code_sha256": _analysis_code_sha256(),
        "generated_at_utc": "NOT_RECORDED_BY_DESIGN",
        "repository_revision": repository_revision,
        "generation_command": command,
        "deterministic": True,
    }
    artifacts["feature-manifest-W10.json"] = json.dumps(
        manifest, sort_keys=True, indent=2
    ).encode("utf-8")
    return artifacts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ColdGuard W10 causal feature pipeline. Synthetic results are "
            "software controls, never physical evidence."
        )
    )
    parser.add_argument("--out", default="reports/W10", help="artifact output directory")
    parser.add_argument(
        "--registry",
        default=str(Path(__file__).resolve().parents[1] / "feature-registry-v1.yaml"),
        help="frozen feature registry YAML",
    )
    parser.add_argument(
        "--a-capture",
        default="../evidence/A/W09/exports/CG-S1-H8C-600S.json",
        help="read-only A W09 run export",
    )
    parser.add_argument(
        "--a-w08-manifest",
        default="reports/W08/gate-b-manifest-W08.json",
        help="read-only W08 Gate B manifest",
    )
    parser.add_argument(
        "--repository-revision",
        default=None,
        help="recorded repository revision (default: git HEAD)",
    )
    args = parser.parse_args(argv)

    ml_root = Path(__file__).resolve().parents[1]
    registry_path = Path(args.registry)
    capture_path = Path(args.a_capture)
    w08_path = Path(args.a_w08_manifest)
    out_dir = Path(args.out)
    try:
        revision = args.repository_revision or _git_revision(ml_root)
        command = "python " + " ".join(sys.argv)
        artifacts = build_artifacts(
            registry_path=registry_path,
            capture_path=capture_path,
            w08_path=w08_path,
            repository_revision=revision,
            command=command,
        )
    except PipelineRefusal as exc:
        print(f"W10 REFUSED: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"W10 CONFIGURATION ERROR: {exc}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in artifacts.items():
        (out_dir / name).write_bytes(payload)
    print(
        "W10 CAUSAL FEATURE PIPELINE COMPLETE: synthetic development rows only; "
        f"real Gate B preserved; artifacts {out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
