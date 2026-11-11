#!/usr/bin/env python3
"""ColdGuard W07 plant EDA and repeatability CLI (B-W07-01 … B-W07-04).

Usage::

    python scripts/plant-eda-W07.py --source PATH [--a-run-index PATH]
        [--a-w07-dir DIR] [--out DIR]
        [--representation NAME] [--trailing-samples N]
        [--temperature-change-thresholds 1.0,2.0]
        [--min-runs N] [--repository-revision REV]
        [--pairing-out PATH]

The CLI consumes the W04 normalized capture model. It never re-parses A/C wire
formats, never changes the W04 admission verdict and never trains a model.

Exit codes:

* ``0`` — source loaded, EDA completed and artifacts written. An honest
  ``NOT_ESTABLISHED`` repeatability verdict is a successful W07 run.
* ``1`` — invalid CLI configuration or internal/IO error.
* ``2`` — source refused, multi-boot capture, non-monotonic boot time or an
  analysis precondition refused; no artifacts are written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

try:  # installed package (the normal locked-environment path)
    from coldguard_ml import (
        SourceRefusal,
        load_capture,
    )
    from coldguard_ml import plant_eda as _plant_module
    from coldguard_ml.plant_eda import (
        PlantEDAConfig,
        PlantEDAError,
        analyze_capture_eda,
        build_manifest,
        render_pairing_markdown,
        render_plant_svg,
        render_report,
        repeatability_csv,
    )
except ModuleNotFoundError:  # direct checkout invocation without installation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml import (
        SourceRefusal,
        load_capture,
    )
    from coldguard_ml import plant_eda as _plant_module
    from coldguard_ml.plant_eda import (
        PlantEDAConfig,
        PlantEDAError,
        analyze_capture_eda,
        build_manifest,
        render_pairing_markdown,
        render_plant_svg,
        render_report,
        repeatability_csv,
    )


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
    revision = completed.stdout.strip()
    return revision or "UNRECORDED"


def _analysis_code_sha256() -> str:
    package_dir = Path(_plant_module.__file__).resolve().parent
    paths = {
        Path(__file__).resolve(),
        package_dir / "plant_eda.py",
        package_dir / "intake.py",
        package_dir / "real_data_qa.py",
        package_dir / "timing_alignment.py",
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


def _parse_thresholds(raw: str) -> tuple[float, ...]:
    values = tuple(float(part.strip()) for part in raw.split(",") if part.strip())
    if not values:
        raise ValueError("at least one temperature-change threshold is required")
    return values


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "ColdGuard W07 plant EDA, repeatability and pairing-input analysis. "
            "Source-based only: no hardware action, no model training."
        )
    )
    parser.add_argument("--source", required=True, help="A W09 run export JSON")
    parser.add_argument("--a-run-index", help="A W09 run index JSON")
    parser.add_argument(
        "--a-w07-dir",
        default="evidence/A/W07",
        help="read-only A W07 phase-reference directory (default: evidence/A/W07)",
    )
    parser.add_argument(
        "--out",
        default="reports/W07",
        help="artifact output directory (default: reports/W07)",
    )
    parser.add_argument(
        "--representation",
        default="tmean_airroles_v0",
        choices=(
            "tmean_airroles_v0",
            "tmean_t2excluded_v0",
        ),
        help="temperature representation (default: tmean_airroles_v0)",
    )
    parser.add_argument(
        "--trailing-samples",
        type=int,
        default=120,
        help="trailing-window slope sample count (default: 120)",
    )
    parser.add_argument(
        "--temperature-change-thresholds",
        default="1.0,2.0",
        help="comma-separated diagnostic °C thresholds (default: 1.0,2.0)",
    )
    parser.add_argument(
        "--min-runs",
        type=int,
        default=3,
        help="minimum independent runs for a repeatability claim (default: 3)",
    )
    parser.add_argument(
        "--percentile-method",
        default="linear",
        choices=("linear", "nearest_rank"),
        help="quartile/percentile convention (default: linear)",
    )
    parser.add_argument(
        "--repository-revision",
        default=None,
        help="recorded repository revision (default: git HEAD or UNRECORDED)",
    )
    parser.add_argument(
        "--pairing-out",
        default=None,
        help=(
            "pairing markdown path (default: ml/pairing-candidate-variables.md)"
        ),
    )
    return parser


def _load_a_references(directory: Path) -> dict[str, dict[str, Any]]:
    mapping = {
        "baseline": "warmup-runs.jsonl",
        "cooling": "cooling-step-runs.jsonl",
        "recovery": "recovery-runs.jsonl",
    }
    references: dict[str, dict[str, Any]] = {}
    for phase, name in mapping.items():
        path = directory / name
        if not path.is_file():
            continue
        lines = [
            line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        if not lines:
            continue
        references[phase] = json.loads(lines[0])
    return references


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    try:
        thresholds = _parse_thresholds(arguments.temperature_change_thresholds)
        config = PlantEDAConfig(
            representation=arguments.representation,
            trailing_window_samples=arguments.trailing_samples,
            temperature_change_thresholds_c=thresholds,
            percentile_method=arguments.percentile_method,
            min_independent_runs=arguments.min_runs,
        )
        config.validate()
    except ValueError as exc:
        print(f"INVALID CONFIGURATION: {exc}", file=sys.stderr)
        return 1

    source = Path(arguments.source)
    run_index = Path(arguments.a_run_index) if arguments.a_run_index else None
    try:
        capture = load_capture(source, a_run_index=run_index)
    except SourceRefusal as exc:
        print(f"SOURCE REFUSED: {exc.code}: {exc.detail}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"SOURCE ERROR: {exc}", file=sys.stderr)
        return 1

    references = _load_a_references(Path(arguments.a_w07_dir))
    try:
        result = analyze_capture_eda(
            capture,
            config=config,
            a_w07_references=references or None,
        )
    except PlantEDAError as exc:
        print(f"ANALYSIS REFUSED: {exc.code}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ANALYSIS REFUSED: {exc}", file=sys.stderr)
        return 2

    output_dir = Path(arguments.out)
    pairing_path = (
        Path(arguments.pairing_out)
        if arguments.pairing_out
        else Path(__file__).resolve().parents[1] / "pairing-candidate-variables.md"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    pairing_path.parent.mkdir(parents=True, exist_ok=True)

    revision = arguments.repository_revision or _git_revision()
    code_sha = _analysis_code_sha256()
    root = _repo_root()
    command_parts = [
        "python",
        "scripts/plant-eda-W07.py",
        "--source",
        _command_path(arguments.source, root),
    ]
    if arguments.a_run_index:
        command_parts.extend(
            ["--a-run-index", _command_path(arguments.a_run_index, root)]
        )
    command_parts.extend(
        [
            "--a-w07-dir",
            _command_path(arguments.a_w07_dir, root),
            "--out",
            _command_path(arguments.out, root),
            "--representation",
            arguments.representation,
            "--trailing-samples",
            str(arguments.trailing_samples),
            "--temperature-change-thresholds",
            arguments.temperature_change_thresholds,
            "--min-runs",
            str(arguments.min_runs),
            "--percentile-method",
            arguments.percentile_method,
            "--repository-revision",
            revision,
        ]
    )
    if arguments.pairing_out:
        command_parts.extend(
            ["--pairing-out", _command_path(arguments.pairing_out, root)]
        )
    generation_command = " ".join(command_parts)

    report_path = output_dir / "plant-eda-report.md"
    csv_path = output_dir / "repeatability-summary.csv"
    svg_path = output_dir / "phase-trajectories-W07.svg"
    manifest_path = output_dir / "plant-eda-manifest-W07.json"

    report_text = render_report(
        result,
        code_sha256=code_sha,
        repository_revision=revision,
        generation_command=generation_command,
    )
    report_path.write_text(report_text, encoding="utf-8", newline="\n")
    csv_path.write_text(
        repeatability_csv(result.repeatability), encoding="utf-8", newline="\n"
    )
    svg_path.write_text(render_plant_svg(result), encoding="utf-8", newline="\n")
    pairing_path.write_text(
        render_pairing_markdown(), encoding="utf-8", newline="\n"
    )

    artifact_hashes = {
        report_path.name: _sha256_file(report_path),
        csv_path.name: _sha256_file(csv_path),
        svg_path.name: _sha256_file(svg_path),
        pairing_path.name: _sha256_file(pairing_path),
    }
    manifest_path.write_text(
        build_manifest(
            result,
            code_sha256=code_sha,
            repository_revision=revision,
            generation_command=generation_command,
            artifact_sha256=artifact_hashes,
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(
        "W07 EDA COMPLETE: "
        f"{len(capture.rows)} rows · {len(result.phases)} phase segment(s) · "
        f"repeatability {result.repeatability.verdict} · "
        f"qualified independent runs {result.repeatability.qualified_independent_runs} · "
        f"artifacts {output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
