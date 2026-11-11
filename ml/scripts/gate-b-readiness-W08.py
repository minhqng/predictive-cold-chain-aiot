#!/usr/bin/env python3
"""ColdGuard W08 Gate B dataset-readiness CLI (B-W08-01 … B-W08-04).

Usage::

    python scripts/gate-b-readiness-W08.py --source PATH [--source PATH ...]
        [--a-run-index PATH] [--scenario S1|S2] [--dataset-purpose TEXT]
        [--completeness-policy PATH] [--run-manifest PATH ...]
        [--a-w07-manifest PATH] [--out DIR] [--min-runs N]
        [--baseline-window-s F] [--event-window-s F] [--recovery-horizon-s F]
        [--require-command-chain] [--require-electrical]
        [--require-timing-alignment] [--synthetic-control]
        [--split-seed N] [--repository-revision REV]

The CLI consumes the W04 normalized capture model and the W05/W06/W07
diagnostics. It never re-parses A/C wire formats, never changes A's validity
ledger, never trains a model and never creates or inspects a locked test.

Exit codes:

* ``0`` — inputs loaded and the readiness analysis completed. A scientific
  ``RED`` Gate B (or ``NOT_READY`` predictive dataset) is a successful run.
* ``1`` — invalid CLI configuration, malformed policy/manifest input or an
  internal/IO error.
* ``2`` — a source was refused or an analysis precondition refused; no
  artifacts are written.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

try:  # installed package (the normal locked-environment path)
    from coldguard_ml import (
        SourceRefusal,
        analyze_capture,
        evaluate_admission,
        load_capture,
    )
    from coldguard_ml import data_readiness as _w08
    from coldguard_ml.data_readiness import (
        COMPLETENESS_POLICY_VERSION,
        CompletenessPolicy,
        CompletenessThreshold,
        RunManifestLinkage,
        build_gate_b_report,
        build_gate_manifest,
        default_completeness_policy,
        default_scenario_requirement,
        render_completeness_policy,
        render_readiness_report,
        render_split_plan,
        run_validation_csv,
    )
    from coldguard_ml.real_data_qa import QAConfig
except ModuleNotFoundError:  # direct checkout invocation without installation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml import (
        SourceRefusal,
        analyze_capture,
        evaluate_admission,
        load_capture,
    )
    from coldguard_ml import data_readiness as _w08
    from coldguard_ml.data_readiness import (
        COMPLETENESS_POLICY_VERSION,
        CompletenessPolicy,
        CompletenessThreshold,
        RunManifestLinkage,
        build_gate_b_report,
        build_gate_manifest,
        default_completeness_policy,
        default_scenario_requirement,
        render_completeness_policy,
        render_readiness_report,
        render_split_plan,
        run_validation_csv,
    )
    from coldguard_ml.real_data_qa import QAConfig


def _repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return Path.cwd()


def _git_revision() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNRECORDED"
    return completed.stdout.strip() or "UNRECORDED"


def _analysis_code_sha256() -> str:
    package_dir = Path(_w08.__file__).resolve().parent
    paths = {
        Path(__file__).resolve(),
        package_dir / "data_readiness.py",
        package_dir / "intake.py",
        package_dir / "real_data_qa.py",
        package_dir / "timing_alignment.py",
        package_dir / "splitting.py",
        package_dir / "__init__.py",
    }
    hasher = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _command_path(value: str, root: Path) -> str:
    candidate = Path(value)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return Path(os.path.relpath(candidate.resolve(), root / "ml")).as_posix()
    except ValueError:
        return candidate.name


class _ArgumentParser(argparse.ArgumentParser):
    """Usage errors are invalid input (exit 1), not source refusals (exit 2)."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"INVALID CONFIGURATION: {message}", file=sys.stderr)
        raise SystemExit(1)


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        description=(
            "ColdGuard W08 Gate B dataset readiness. Read-only source analysis: "
            "no hardware action, no model training, no locked-test access."
        )
    )
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="A W09 run export JSON or C telemetry snapshot (repeatable)",
    )
    parser.add_argument("--a-run-index", help="A run-validity index JSON")
    parser.add_argument(
        "--scenario",
        default="S1",
        help="declared scenario population (default: S1)",
    )
    parser.add_argument(
        "--dataset-purpose",
        default=None,
        help="declared dataset purpose recorded verbatim",
    )
    parser.add_argument(
        "--completeness-policy",
        default=None,
        help="optional JSON override of the draft completeness policy",
    )
    parser.add_argument(
        "--run-manifest",
        action="append",
        default=[],
        help="run manifest linkage JSON (repeatable; matched by run_id)",
    )
    parser.add_argument(
        "--a-w07-manifest",
        default="reports/W07/plant-eda-manifest-W07.json",
        help="read-only W07 manifest for physical-repeatability evidence",
    )
    parser.add_argument(
        "--out",
        default="reports/W08",
        help="artifact output directory (default: reports/W08)",
    )
    parser.add_argument(
        "--min-runs",
        type=int,
        default=3,
        help="minimum independent qualified runs for the declared scenario (default: 3)",
    )
    parser.add_argument(
        "--baseline-window-s",
        type=float,
        default=120.0,
        help="pre-event baseline planning window (default: 120 s)",
    )
    parser.add_argument(
        "--event-window-s",
        type=float,
        default=60.0,
        help="primary event planning window (default: 60 s)",
    )
    parser.add_argument(
        "--recovery-horizon-s",
        type=float,
        default=900.0,
        help="recovery/follow-up planning horizon (default: 900 s)",
    )
    parser.add_argument(
        "--require-command-chain",
        action="store_true",
        help="require command/ACK/applied evidence for the declared analysis",
    )
    parser.add_argument(
        "--require-electrical",
        action="store_true",
        help="require qualified PZEM electrical evidence for the declared analysis",
    )
    parser.add_argument(
        "--require-timing-alignment",
        action="store_true",
        help=(
            "require a frozen cadence tolerance for the declared analysis; an "
            "UNRESOLVED timing threshold then prevents GREEN"
        ),
    )
    parser.add_argument(
        "--synthetic-control",
        action="store_true",
        help=(
            "label the inputs as a software-only synthetic positive control; "
            "GREEN may exercise the software branch but never certifies a "
            "measured physical dataset"
        ),
    )
    parser.add_argument(
        "--split-seed",
        type=int,
        default=0,
        help="deterministic split-planning seed (default: 0)",
    )
    parser.add_argument(
        "--repository-revision",
        default=None,
        help="recorded repository revision (default: git HEAD or UNRECORDED)",
    )
    return parser


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _policy_notes(payload: dict[str, Any], fallback: Sequence[str]) -> tuple[str, ...]:
    notes = payload.get("notes", [])
    if not isinstance(notes, list):
        raise ValueError("completeness policy notes must be a list")
    return tuple(str(note) for note in notes) or tuple(fallback)


def _load_policy(path: Path) -> CompletenessPolicy:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("completeness policy must be a JSON object")
    if "thresholds" in payload:
        raw_thresholds = payload["thresholds"]
        if not isinstance(raw_thresholds, list):
            raise ValueError("completeness policy thresholds must be a list")
        thresholds = []
        seen_dimensions: set[str] = set()
        by_dimension = {
            threshold.dimension: threshold
            for threshold in default_completeness_policy().thresholds
        }
        for item in raw_thresholds:
            if not isinstance(item, dict) or "dimension" not in item:
                raise ValueError("each threshold requires a dimension")
            dimension = str(item["dimension"])
            if dimension in seen_dimensions:
                raise ValueError(
                    f"duplicate completeness dimension {dimension!r}"
                )
            seen_dimensions.add(dimension)
            base = by_dimension.get(dimension)
            if base is None:
                raise ValueError(f"unknown completeness dimension {dimension!r}")
            thresholds.append(
                CompletenessThreshold(
                    name=base.name,
                    dimension=base.dimension,
                    applicable_scenario=base.applicable_scenario,
                    channel_family=base.channel_family,
                    required_event_window=base.required_event_window,
                    definition=base.definition,
                    denominator=base.denominator,
                    missing_semantics=base.missing_semantics,
                    source_justification=base.source_justification,
                    status=str(item.get("status", base.status)),
                    equality_behavior=base.equality_behavior,
                    blocking_severity=base.blocking_severity,
                    owner=base.owner,
                    review_authority=base.review_authority,
                    value=(
                        item["value"]
                        if "value" in item
                        else base.value
                    ),
                    freeze_evidence=(
                        None
                        if item.get("freeze_evidence") is None
                        else str(item["freeze_evidence"])
                    ),
                )
            )
        covered = {threshold.dimension for threshold in thresholds}
        thresholds.extend(
            threshold
            for dimension, threshold in by_dimension.items()
            if dimension not in covered
        )
        return CompletenessPolicy(
            policy_version=str(
                payload.get("policy_version", COMPLETENESS_POLICY_VERSION)
            ),
            thresholds=tuple(thresholds),
            notes=_policy_notes(
                payload, default_completeness_policy().notes
            ),
        )
    overrides = payload.get("overrides", payload)
    if not isinstance(overrides, dict):
        raise ValueError("policy overrides must be a JSON object")
    base_policy = default_completeness_policy()
    thresholds = []
    for threshold in base_policy.thresholds:
        override = overrides.get(threshold.dimension)
        if not isinstance(override, dict):
            thresholds.append(threshold)
            continue
        thresholds.append(
            CompletenessThreshold(
                name=threshold.name,
                dimension=threshold.dimension,
                applicable_scenario=threshold.applicable_scenario,
                channel_family=threshold.channel_family,
                required_event_window=threshold.required_event_window,
                definition=threshold.definition,
                denominator=threshold.denominator,
                missing_semantics=threshold.missing_semantics,
                source_justification=threshold.source_justification,
                status=str(override.get("status", threshold.status)),
                equality_behavior=threshold.equality_behavior,
                blocking_severity=threshold.blocking_severity,
                owner=threshold.owner,
                review_authority=threshold.review_authority,
                value=(
                    override["value"]
                    if "value" in override
                    else threshold.value
                ),
                freeze_evidence=(
                    None
                    if override.get("freeze_evidence") is None
                    else str(override["freeze_evidence"])
                ),
            )
        )
    return CompletenessPolicy(
        policy_version=str(
            payload.get("policy_version", COMPLETENESS_POLICY_VERSION)
        ),
        thresholds=tuple(thresholds),
        notes=_policy_notes(payload, base_policy.notes),
    )


def _load_run_manifests(paths: Sequence[str]) -> dict[str, RunManifestLinkage]:
    linkages: dict[str, RunManifestLinkage] = {}
    for raw in paths:
        path = Path(raw)
        payload = _load_json(path)
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("run manifest linkage must be an object")
            required = (
                "run_id",
                "boot_id",
                "scenario_id",
                "hardware_config_id",
                "source_sha256",
            )
            missing = [key for key in required if key not in item]
            if missing:
                raise ValueError(
                    f"run manifest linkage missing keys {missing}: {path}"
                )
            linkage = RunManifestLinkage(
                run_id=str(item["run_id"]),
                device_id=(
                    None
                    if item.get("device_id") is None
                    else str(item["device_id"])
                ),
                boot_id=str(item["boot_id"]),
                scenario_id=str(item["scenario_id"]),
                hardware_config_id=str(item["hardware_config_id"]),
                calibration_id=(
                    None
                    if item.get("calibration_id") is None
                    else str(item["calibration_id"])
                ),
                source_sha256=str(item["source_sha256"]),
                manifest_sha256=_sha256_file(path),
                pair_id=(
                    None if item.get("pair_id") is None else str(item["pair_id"])
                ),
                controller_id=(
                    None
                    if item.get("controller_id") is None
                    else str(item["controller_id"])
                ),
                planned_capture_duration_s=(
                    None
                    if item.get("planned_capture_duration_s") is None
                    else float(item["planned_capture_duration_s"])
                ),
            )
            linkages[linkage.run_id] = linkage
    return linkages


def _load_w07_evidence(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = _load_json(path)
    repeatability = payload.get("repeatability")
    if not isinstance(repeatability, dict):
        return None
    return {
        "manifest_path": path.as_posix(),
        "manifest_sha256": _sha256_file(path),
        "verdict": repeatability.get("verdict"),
        "qualified_independent_runs": repeatability.get(
            "qualified_independent_runs"
        ),
        "independent_physical_sources": repeatability.get(
            "independent_physical_sources"
        ),
        "reason_codes": list(repeatability.get("reason_codes", [])),
    }


def _verify_written_artifacts(output_dir: Path, report: Any) -> list[str]:
    """Post-write software check: artifact hashes and report/CSV agreement."""
    problems: list[str] = []
    manifest_path = output_dir / "gate-b-manifest-W08.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"manifest not readable: {exc}"]
    for name, digest in manifest.get("artifact_sha256", {}).items():
        path = output_dir / name
        if not path.is_file():
            problems.append(f"{name} missing")
        elif _sha256_file(path) != digest:
            problems.append(f"{name} hash mismatch")
    csv_path = output_dir / "run-validation-W08.csv"
    try:
        rows = list(
            csv.DictReader(
                io.StringIO(csv_path.read_text(encoding="utf-8"))
            )
        )
    except OSError as exc:
        return problems + [f"run-validation CSV not readable: {exc}"]
    if len(rows) != len(report.validations):
        problems.append("run-validation CSV row count differs from the report")
    else:
        for row, item in zip(rows, report.validations):
            if row.get("b_eligibility") != item.eligibility:
                problems.append(
                    f"CSV eligibility mismatch for {item.source_path}"
                )
            if row.get("a_ledger_verdict") != item.a_ledger_verdict:
                problems.append(
                    f"CSV A-ledger mismatch for {item.source_path}"
                )
    if (
        manifest.get("physical_gate", {}).get("observed_status")
        != report.physical_gate.observed_status
    ):
        problems.append("manifest physical-gate status differs from the report")
    if (
        manifest.get("split_plan", {}).get("feasibility")
        != report.split_plan.feasibility
    ):
        problems.append("manifest split feasibility differs from the report")
    if manifest.get("data_origin") != report.data_origin:
        problems.append("manifest data origin differs from the report")
    if bool(manifest.get("synthetic_control")) != report.synthetic_control:
        problems.append("manifest synthetic-control provenance differs")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    if arguments.min_runs < 1:
        print("INVALID CONFIGURATION: --min-runs must be >= 1", file=sys.stderr)
        return 1
    if min(
        arguments.baseline_window_s,
        arguments.event_window_s,
        arguments.recovery_horizon_s,
    ) <= 0:
        print(
            "INVALID CONFIGURATION: event windows must be positive",
            file=sys.stderr,
        )
        return 1
    try:
        policy = (
            _load_policy(Path(arguments.completeness_policy))
            if arguments.completeness_policy
            else default_completeness_policy()
        )
        linkages = _load_run_manifests(arguments.run_manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"INVALID CONFIGURATION: {exc}", file=sys.stderr)
        return 1

    run_index = Path(arguments.a_run_index) if arguments.a_run_index else None
    requirement = default_scenario_requirement(
        arguments.scenario,
        dataset_purpose=arguments.dataset_purpose,
        requires_command_chain=arguments.require_command_chain,
        requires_electrical_evidence=arguments.require_electrical,
        baseline_window_s=arguments.baseline_window_s,
        event_window_s=arguments.event_window_s,
        recovery_horizon_s=arguments.recovery_horizon_s,
        requires_timing_alignment=arguments.require_timing_alignment,
    )
    validations = []
    admissions = []
    for raw_source in arguments.source:
        source = Path(raw_source)
        try:
            capture = load_capture(source, a_run_index=run_index)
        except SourceRefusal as exc:
            print(f"SOURCE REFUSED: {exc.code}: {exc.detail}", file=sys.stderr)
            return 2
        except OSError as exc:
            print(f"SOURCE ERROR: {exc}", file=sys.stderr)
            return 1
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"INVALID CONFIGURATION: {exc}", file=sys.stderr)
            return 1
        admission = evaluate_admission(capture)
        qa = analyze_capture(capture, admission=admission, config=QAConfig())
        linkage = None
        if capture.run.run_id is not None:
            linkage = linkages.get(capture.run.run_id)
        validation = _w08.validate_run(
            capture,
            admission=admission,
            qa=qa,
            requirement=requirement,
            policy=policy,
            manifest_linkage=linkage,
        )
        validations.append(validation)
        admissions.append(admission)

    try:
        report = build_gate_b_report(
            validations,
            admissions,
            requirement,
            policy=policy,
            min_independent_runs=arguments.min_runs,
            w07_evidence=_load_w07_evidence(Path(arguments.a_w07_manifest)),
            limitations=(
                "The A W09 export and validity index were consumed read-only.",
                "No run manifest is fabricated; missing linkage is reported.",
                (
                    "Inputs are declared synthetic software controls, not "
                    "measured physical data."
                    if arguments.synthetic_control
                    else "Inputs are treated as measured physical data."
                ),
            ),
            synthetic_control=arguments.synthetic_control,
        )
    except Exception as exc:  # pragma: no cover - defensive software boundary
        print(f"ANALYSIS FAILED: {exc}", file=sys.stderr)
        return 1

    output_dir = Path(arguments.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    revision = arguments.repository_revision or _git_revision()
    code_sha = _analysis_code_sha256()
    root = _repo_root()
    command_parts = [
        "python",
        "scripts/gate-b-readiness-W08.py",
    ]
    for source in arguments.source:
        command_parts.extend(["--source", _command_path(source, root)])
    if arguments.a_run_index:
        command_parts.extend(
            ["--a-run-index", _command_path(arguments.a_run_index, root)]
        )
    command_parts.extend(
        [
            "--scenario",
            arguments.scenario,
            "--out",
            _command_path(arguments.out, root),
            "--min-runs",
            str(arguments.min_runs),
            "--baseline-window-s",
            str(arguments.baseline_window_s),
            "--event-window-s",
            str(arguments.event_window_s),
            "--recovery-horizon-s",
            str(arguments.recovery_horizon_s),
            "--split-seed",
            str(arguments.split_seed),
            "--repository-revision",
            revision,
        ]
    )
    if arguments.dataset_purpose:
        command_parts.extend(["--dataset-purpose", arguments.dataset_purpose])
    if arguments.completeness_policy:
        command_parts.extend(
            ["--completeness-policy", _command_path(arguments.completeness_policy, root)]
        )
    for path in arguments.run_manifest:
        command_parts.extend(["--run-manifest", _command_path(path, root)])
    if arguments.require_command_chain:
        command_parts.append("--require-command-chain")
    if arguments.require_electrical:
        command_parts.append("--require-electrical")
    if arguments.require_timing_alignment:
        command_parts.append("--require-timing-alignment")
    if arguments.synthetic_control:
        command_parts.append("--synthetic-control")
    generation_command = " ".join(command_parts)

    report_path = output_dir / "gate-b-readiness-W08.md"
    csv_path = output_dir / "run-validation-W08.csv"
    policy_path = output_dir / "completeness-policy-W08.md"
    split_path = output_dir / "development-split-plan-W08.md"
    manifest_path = output_dir / "gate-b-manifest-W08.json"
    source_index_sha = (
        _sha256_file(run_index) if run_index is not None and run_index.is_file() else None
    )
    report_path.write_text(
        render_readiness_report(
            report,
            code_sha256=code_sha,
            repository_revision=revision,
            generation_command=generation_command,
            source_index_sha256=source_index_sha,
        ),
        encoding="utf-8",
        newline="\n",
    )
    csv_path.write_text(
        run_validation_csv(report), encoding="utf-8", newline="\n"
    )
    policy_path.write_text(
        render_completeness_policy(report.policy), encoding="utf-8", newline="\n"
    )
    split_path.write_text(
        render_split_plan(report.split_plan), encoding="utf-8", newline="\n"
    )
    artifact_hashes = {
        report_path.name: _sha256_file(report_path),
        csv_path.name: _sha256_file(csv_path),
        policy_path.name: _sha256_file(policy_path),
        split_path.name: _sha256_file(split_path),
    }
    manifest_path.write_text(
        build_gate_manifest(
            report,
            code_sha256=code_sha,
            repository_revision=revision,
            generation_command=generation_command,
            artifact_sha256=artifact_hashes,
            source_index_sha256=source_index_sha,
        ),
        encoding="utf-8",
        newline="\n",
    )
    problems = _verify_written_artifacts(output_dir, report)
    if problems:
        print(
            "SOFTWARE VERIFICATION FAILED: " + "; ".join(problems),
            file=sys.stderr,
        )
        return 1
    print(
        "W08 GATE B READINESS COMPLETE: "
        f"W08 software {report.software_gate.observed_status} · "
        f"Gate B physical {report.physical_gate.observed_status} · "
        f"predictive dataset {report.predictive_gate.observed_status} · "
        f"split {report.split_plan.feasibility} · "
        f"eligible runs {len(report.eligible_runs)} · artifacts {output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
