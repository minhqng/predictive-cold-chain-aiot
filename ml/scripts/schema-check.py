#!/usr/bin/env python3
"""W04 deterministic schema/eligibility checker CLI (B-W04-01 / B-W04-05).

Usage::

    python ml/scripts/schema-check.py identify <source>
    python ml/scripts/schema-check.py check <source> [--a-run-index PATH]
        [--source-format auto|a-w09-export-v2|c-telemetry-json-v1]
        [--format json|text] [--out PATH] [--require-eligible]

Exit codes (documented in ``ml/analysis-contract-v1.md``):

* ``0`` — the checker ran and the source was structurally valid. This is the
  expected result for a real capture with zero eligible predictive runs: an
  honest ``NOT_READY`` admission is a successful checker result, not a failure.
* ``1`` — ``--require-eligible`` was set and no predictive admission exists,
  or an internal/IO error occurred.
* ``2`` — the source representation is unrecognized, unsupported, or
  structurally invalid; a precise refusal is printed with no field guessing.

The CLI and the importable API share one validation path
(:func:`coldguard_ml.load_capture` + :func:`coldguard_ml.evaluate_admission`).
Output contains no timestamps and no local absolute paths, so identical inputs
produce byte-identical JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:  # installed package (the normal locked-environment path)
    from coldguard_ml import (
        AdmissionResult,
        Capture,
        SourceRefusal,
        classify_source,
        evaluate_admission,
        load_capture,
    )
except ModuleNotFoundError:  # direct checkout invocation without installation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml import (
        AdmissionResult,
        Capture,
        SourceRefusal,
        classify_source,
        evaluate_admission,
        load_capture,
    )

REPORT_VERSION = "coldguard-w04-schema-check-v1"
SUPPORTED_FORMAT_CHOICES = (
    "auto",
    "a-w09-run-export-v2",
    "c-telemetry-json-v1",
)


def _quality_counts(capture: Capture) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for row in capture.rows:
        for domain, quality in row.quality:
            counts.setdefault(domain, {})
            counts[domain][quality] = counts[domain].get(quality, 0) + 1
    return {
        domain: {quality: counts[domain][quality] for quality in sorted(counts[domain])}
        for domain in sorted(counts)
    }


def _structure_status(admission: AdmissionResult) -> str:
    structural_stages = {"SOURCE_RECOGNIZED", "STRUCTURALLY_VALID"}
    return (
        "INVALID"
        if any(blocker.stage in structural_stages for blocker in admission.blockers)
        else "VALID"
    )


def _report(capture: Capture, admission: AdmissionResult) -> dict[str, Any]:
    return {
        "report_version": REPORT_VERSION,
        "source": capture.source.to_dict(),
        "source_format": capture.source.format,
        "schema_namespace": capture.source.schema_namespace,
        "structure": {
            "status": _structure_status(admission),
            "rows": len(capture.rows),
            "columns": len(capture.recognized_fields),
            "recognized_fields": list(capture.recognized_fields),
            "unknown_fields": list(capture.unknown_fields),
            "declared_unavailable_fields": list(
                capture.declared_unavailable_fields
            ),
        },
        "provenance": {
            "class": capture.source.provenance,
            "is_physical_measurement": capture.source.is_physical_measurement,
            "pinned_sources": [
                {"path": path, "sha256": digest, "exists": exists}
                for path, digest, exists in capture.source.pinned_sources
            ],
        },
        "time": capture.time.to_dict(),
        "roles": {
            "chamber_air_slots": list(capture.chamber_air_slots),
            "hot_side_slots": list(capture.hot_side_slots),
            "unknown_role_slots": list(capture.unknown_role_slots),
            "sensors": [role.to_dict() for role in capture.sensors],
        },
        "quality": {
            "counts_by_domain": _quality_counts(capture),
        },
        "a_validity": (
            None if capture.a_validity is None else capture.a_validity.to_dict()
        ),
        "admission": admission.to_dict(),
        "eligible_s1_runs": admission.eligible_s1_runs,
        "eligible_s2_runs": admission.eligible_s2_runs,
        "predictive_dataset_readiness": admission.predictive_dataset_readiness,
        "exclusions": [blocker.to_dict() for blocker in admission.blockers],
        "warnings": list(capture.warnings),
    }


def _refusal_report(source: str | Path, exc: SourceRefusal) -> dict[str, Any]:
    return {
        "report_version": REPORT_VERSION,
        "status": "REFUSED",
        "source_path": Path(source).name,
        "reason_code": exc.code,
        "reason": exc.detail,
        "structure": {"status": "INVALID"},
        "admission": {
            "status": "EXCLUDED_OR_BLOCKED",
            "highest_stage": "SOURCE_RECOGNIZED",
            "eligible": False,
        },
        "eligible_s1_runs": 0,
        "eligible_s2_runs": 0,
        "predictive_dataset_readiness": "NOT_READY",
    }


def _render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _render_text(report: dict[str, Any]) -> str:
    if report.get("status") == "REFUSED":
        return (
            f"SOURCE: {report['source_path']}\n"
            "STATUS: REFUSED\n"
            f"REASON: {report['reason_code']}: {report['reason']}\n"
            f"ELIGIBLE S1 RUNS: {report['eligible_s1_runs']}\n"
            f"ELIGIBLE S2 RUNS: {report['eligible_s2_runs']}\n"
            f"PREDICTIVE DATASET READINESS: "
            f"{report['predictive_dataset_readiness']}\n"
        )
    admission = report["admission"]
    lines = [
        f"SOURCE: {report['source']['path']}",
        f"FORMAT: {report['source_format']}",
        f"SCHEMA_NAMESPACE: {report['schema_namespace']}",
        (
            f"STRUCTURE: {report['structure']['status']} "
            f"({report['structure']['rows']} rows, "
            f"{report['structure']['columns']} columns)"
        ),
        f"PROVENANCE: {report['provenance']['class']}",
        (
            f"TIME_DOMAIN: {report['time']['domain']} "
            f"(event_time={report['time']['event_time_status']}, "
            f"clock_sync={report['time']['clock_sync']})"
        ),
        (
            "ROLES: chamber_air="
            f"{report['roles']['chamber_air_slots']} hot_side="
            f"{report['roles']['hot_side_slots']} unknown="
            f"{report['roles']['unknown_role_slots']}"
        ),
        (
            f"QUALITY_COUNTS: {json.dumps(report['quality']['counts_by_domain'], sort_keys=True)}"
        ),
        (
            f"ADMISSION: {admission['status']} "
            f"(highest stage: {admission['highest_stage']})"
        ),
    ]
    if report["exclusions"]:
        lines.append("BLOCKERS:")
        for blocker in sorted(
            report["exclusions"], key=lambda item: (item["stage"], item["code"])
        ):
            lines.append(
                f"  - {blocker['code']} ({blocker['stage']}): {blocker['detail']}"
            )
    if report["admission"]["scenarios"]:
        lines.append("SCENARIOS:")
        for scenario in report["admission"]["scenarios"]:
            lines.append(
                f"  - {scenario['scenario_id']}: "
                f"{scenario['eligible_rows']} eligible rows, "
                f"eligible={scenario['eligible']}"
            )
    lines.extend(
        [
            f"ELIGIBLE S1 RUNS: {report['eligible_s1_runs']}",
            f"ELIGIBLE S2 RUNS: {report['eligible_s2_runs']}",
            f"PREDICTIVE DATASET READINESS: {report['predictive_dataset_readiness']}",
        ]
    )
    if report["warnings"]:
        lines.append("WARNINGS:")
        for warning in sorted(report["warnings"]):
            lines.append(f"  - {warning}")
    return "\n".join(lines) + "\n"


def _emit(report: dict[str, Any], output_format: str, out: str | None) -> None:
    text = _render_json(report) if output_format == "json" else _render_text(report)
    if out:
        Path(out).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schema-check",
        description=(
            "ColdGuard W04 source-aware schema and scientific-eligibility "
            "checker. A parse never implies admission."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    identify = subparsers.add_parser(
        "identify", help="identify the source representation without mapping fields"
    )
    identify.add_argument("source")
    identify.add_argument("--format", choices=("json", "text"), default="json")
    identify.add_argument("--out")

    check = subparsers.add_parser(
        "check", help="validate structure and evaluate the admission ladder"
    )
    check.add_argument("source")
    check.add_argument(
        "--source-format",
        choices=SUPPORTED_FORMAT_CHOICES,
        default="auto",
    )
    check.add_argument(
        "--a-run-index",
        default=None,
        help="A's W09 run index (authoritative run-validity hand-off)",
    )
    check.add_argument("--format", choices=("json", "text"), default="json")
    check.add_argument("--out")
    check.add_argument(
        "--require-eligible",
        action="store_true",
        help="exit 1 when the source is not eligible for a predictive dataset",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "identify":
        classification = classify_source(args.source)
        if args.format == "json":
            text = _render_json(classification)
        else:
            text = "\n".join(
                f"{key.upper()}: {value}"
                for key, value in classification.items()
                if value is not None
            ) + "\n"
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(text)
        return 0 if classification["supported"] else 2

    try:
        capture = load_capture(
            args.source,
            source_format=args.source_format,
            a_run_index=args.a_run_index,
        )
        admission = evaluate_admission(capture)
        report = _report(capture, admission)
        _emit(report, args.format, args.out)
        if report["structure"]["status"] != "VALID":
            return 2
        if args.require_eligible and not admission.eligible:
            return 1
        return 0
    except SourceRefusal as exc:
        report = _refusal_report(args.source, exc)
        _emit(report, args.format, args.out)
        return 2
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        report = {
            "report_version": REPORT_VERSION,
            "status": "ERROR",
            "source_path": Path(args.source).name,
            "reason_code": type(exc).__name__,
            "reason": str(exc),
            "eligible_s1_runs": 0,
            "eligible_s2_runs": 0,
            "predictive_dataset_readiness": "NOT_READY",
        }
        _emit(report, args.format, args.out)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
