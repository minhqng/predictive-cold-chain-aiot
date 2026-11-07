#!/usr/bin/env python3
"""ColdGuard W05 executable real-telemetry QA (B-W05-01 … B-W05-04).

Usage::

    python ml/scripts/real-data-qa-v1.py --source PATH [--source PATH ...]
        [--a-run-index PATH] [--out DIR] [--format md|html|both]
        [--long-gap-ms N] [--flatline-min-observations N]
        [--flatline-temperature-tolerance-c F] [--stale-age-ms N]
        [--nominal-cadence-ms F] [--percentile linear|nearest_rank]

The CLI consumes the W04 source-aware intake only. It never re-parses A/C wire
formats and never changes the W04 physical-admission verdict.

Exit codes:

* ``0`` — every source loaded, the QA analysis completed, and every source is
  structurally valid. An honest ``NOT_READY`` physical verdict is a successful
  QA run, not a CLI failure.
* ``1`` — internal/IO error or invalid CLI configuration.
* ``2`` — at least one source was refused, unsupported, or structurally
  invalid; a precise reason is printed and no artifacts are written.
"""

from __future__ import annotations

import argparse
import hashlib
import html as _html
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

try:  # installed package (the normal locked-environment path)
    from coldguard_ml import (
        QAAnalysis,
        QAConfig,
        QASuiteSummary,
        SourceRefusal,
        __version__ as PACKAGE_VERSION,
        analyze_captures,
        channel_summary_csv,
        load_a_run_index,
        load_capture,
        qa_manifest,
        render_physical_state_svg,
        summarize_qa_suite,
    )
    from coldguard_ml import real_data_qa as _qa_module
    from coldguard_ml.real_data_qa import QA_LAYER_VERSION
except ModuleNotFoundError:  # direct checkout invocation without installation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml import real_data_qa as _qa_module
    from coldguard_ml import (
        QAAnalysis,
        QAConfig,
        QASuiteSummary,
        SourceRefusal,
        __version__ as PACKAGE_VERSION,
        analyze_captures,
        channel_summary_csv,
        load_a_run_index,
        load_capture,
        qa_manifest,
        render_physical_state_svg,
        summarize_qa_suite,
    )
    from coldguard_ml.real_data_qa import QA_LAYER_VERSION

REPORT_VERSION = "coldguard-w05-qa-report-v2"
_MD = "md"
_HTML = "html"
_BOTH = "both"
_UNAVAILABLE = "NOT_ESTIMABLE"


def _safe_path(path: str, root: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.name


def _command_path(path: str, root: Path) -> str:
    """Path as written for the documented ``cd ml`` reproduction context."""
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return Path(os.path.relpath(candidate.resolve(), root / "ml")).as_posix()
    except ValueError:
        return candidate.name


def _repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return Path.cwd()


def _analysis_code_sha256() -> str:
    """SHA-256 over the QA layer, CLI and the W04 contracts it consumes."""
    package_dir = Path(_qa_module.__file__).resolve().parent
    paths = {
        Path(__file__).resolve(),
        package_dir / "real_data_qa.py",
        package_dir / "intake.py",
        package_dir / "evaluation_contract.py",
        package_dir / "__init__.py",
    }
    hasher = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _repository_revision(root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "NOT_RECORDED"
    revision = completed.stdout.strip()
    return revision if revision else "NOT_RECORDED"


def _number(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return _UNAVAILABLE
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def _percent(value: float | None) -> str:
    if value is None:
        return _UNAVAILABLE
    return f"{value * 100.0:.3f}%"


def _code_list(values: Sequence[str]) -> str:
    return ", ".join(values) if values else "NONE"


def _md_cell(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = ["| " + " | ".join(_md_cell(header) for header in headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def _html_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    parts = ["<table><thead><tr>"]
    parts.extend(f"<th>{_html.escape(header)}</th>" for header in headers)
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>")
        parts.extend(f"<td>{_html.escape(cell)}</td>" for cell in row)
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def _plot_name(index: int, session_index: int, total_sources: int, total_sessions: int) -> str:
    if total_sources == 1 and total_sessions == 1:
        return "physical-state-W05.svg"
    return f"physical-state-W05-source{index + 1}-session{session_index + 1}.svg"


def _source_index_metadata(
    a_run_index: str | None, root: Path
) -> dict[str, Any] | None:
    if a_run_index is None:
        return None
    payload = load_a_run_index(a_run_index)
    path = Path(a_run_index).resolve()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": _safe_path(a_run_index, root),
        "sha256": digest,
        "index_version": payload.get("index_version"),
        "runs_total": payload.get("runs_total"),
        "runs_usable_majority": payload.get("runs_usable_majority"),
        "valid_s1_run_ids_for_member_b": list(
            payload.get("valid_s1_run_ids_for_member_b") or []
        ),
        "blocked_run_ids": list(payload.get("blocked_run_ids") or []),
    }


def _command_line(args: argparse.Namespace, root: Path) -> str:
    parts = ["real-data-qa-v1.py"]
    for source in args.source:
        parts.extend(["--source", _command_path(source, root)])
    if args.a_run_index:
        parts.extend(["--a-run-index", _command_path(args.a_run_index, root)])
    parts.extend(["--format", args.format])
    parts.extend(["--long-gap-ms", str(args.long_gap_ms)])
    parts.extend(
        ["--flatline-min-observations", str(args.flatline_min_observations)]
    )
    parts.extend(["--flatline-min-span-s", str(args.flatline_min_span_s)])
    parts.extend(
        [
            "--flatline-temperature-tolerance-c",
            str(args.flatline_temperature_tolerance_c),
        ]
    )
    parts.extend(["--stale-age-ms", str(args.stale_age_ms)])
    parts.extend(["--percentile", args.percentile])
    if args.nominal_cadence_ms is not None:
        parts.extend(["--nominal-cadence-ms", str(args.nominal_cadence_ms)])
    if args.repository_revision is not None:
        parts.extend(["--repository-revision", args.repository_revision])
    parts.extend(["--out", _command_path(args.out, root)])
    return " ".join(parts)


def _status_rows(
    analysis: QAAnalysis, *, conflicting: bool = False
) -> list[tuple[str, str]]:
    statuses = analysis.statuses
    admission_status = statuses.physical_admission_status
    readiness = statuses.predictive_dataset_readiness
    if conflicting:
        view_only = " (VIEW ONLY; not the authoritative source verdict)"
        admission_status += view_only
        readiness += view_only
    rows = [
        ("QA_EXECUTION_STATUS", statuses.qa_execution_status),
        ("SOURCE_STRUCTURE_STATUS", statuses.source_structure_status),
        ("CHANNEL_QUALITY_STATUS", statuses.channel_quality_status),
        (
            "PHYSICAL_ADMISSION_STATUS",
            f"{admission_status} "
            f"(highest stage: {statuses.physical_highest_stage})",
        ),
        ("PREDICTIVE_DATASET_READINESS", readiness),
    ]
    if conflicting:
        rows.append(
            (
                "DUPLICATE_VIEW_ADMISSION_CONFLICT",
                "TRUE — this view-level verdict is not the authoritative "
                "source verdict; the source is excluded and the suite "
                "readiness is NOT_READY",
            )
        )
    return rows


_VIEW_ONLY = "VIEW ONLY; not the authoritative source verdict"
_AUTHORITATIVE_SOURCE_STATUS = "EXCLUDED_OR_BLOCKED"


def _view_value(value: str, conflicting: bool) -> str:
    return f"{value} ({_VIEW_ONLY})" if conflicting else value


def _conflict_warning_md() -> str:
    return (
        "> **DUPLICATE_VIEW_ADMISSION_CONFLICT:** this view-level verdict is "
        "not the authoritative source verdict. The suite excludes the source "
        "and reports `NOT_READY`; the authoritative source status is "
        f"`{_AUTHORITATIVE_SOURCE_STATUS}`."
    )


def _conflict_warning_html() -> str:
    return (
        "<blockquote><strong>DUPLICATE_VIEW_ADMISSION_CONFLICT:</strong> this "
        "view-level verdict is not the authoritative source verdict. The suite "
        "excludes the source and reports <code>NOT_READY</code>; the "
        "authoritative source status is "
        f"<code>{_AUTHORITATIVE_SOURCE_STATUS}</code>.</blockquote>"
    )


def _conflict_view_keys(suite: QASuiteSummary) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for conflict in suite.conflicts:
        for view in conflict.get("view_verdicts", []):
            path = view.get("source_path")
            sha256 = view.get("source_sha256")
            if isinstance(path, str) and isinstance(sha256, str):
                keys.add((path, sha256))
    return keys


def _conflict_rows(
    suite: QASuiteSummary,
) -> list[tuple[str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str]] = []
    for conflict in suite.conflicts:
        rows.append(
            (
                ", ".join(conflict.get("source_paths") or [conflict.get("source_path", "")]),
                str(conflict.get("status", "")),
                str(conflict.get("highest_stage", "")),
                _code_list(
                    [
                        str(blocker.get("code", ""))
                        for blocker in conflict.get("blockers", [])
                    ]
                ),
                str(conflict.get("views", "")),
            )
        )
    return rows


def _evidence_category(analysis: QAAnalysis) -> str:
    provenance = analysis.capture.source.provenance
    physical = analysis.capture.source.is_physical_measurement
    if provenance == "PHYSICAL" and physical is True:
        return "REAL MEASURED (producer declares physical)"
    if provenance == "SYNTHETIC":
        return "SYNTHETIC / NOT A PHYSICAL MEASUREMENT"
    if provenance == "NON_PHYSICAL":
        return "NON_PHYSICAL"
    return "UNVERIFIED PROVENANCE"


def _source_preamble_md(analysis: QAAnalysis, index: int) -> list[str]:
    capture = analysis.capture
    lines = [
        f"### Source {index + 1} — `{capture.source.path}`",
        "",
        _md_table(
            ["Field", "Value"],
            [
                ("Source file", f"`{capture.source.path}`"),
                ("SHA-256", f"`{capture.source.sha256}`"),
                ("Source format", f"`{capture.source.format}`"),
                ("Schema namespace", f"`{capture.source.schema_namespace}`"),
                (
                    "Companion row-validity CSV SHA-256",
                    f"`{capture.source.companion_sha256}`"
                    if capture.source.companion_sha256
                    else "NONE",
                ),
                ("Physical evidence category", _evidence_category(analysis)),
                ("Producer physical flag", str(capture.source.is_physical_measurement)),
                ("A validity evidence", "NONE" if capture.a_validity is None else capture.a_validity.status),
                ("Rows", str(len(capture.rows))),
                ("Analyzed sessions", str(len(analysis.sessions))),
            ],
        ),
        "",
    ]
    if capture.source.pinned_sources:
        lines.extend(
            [
                _md_table(
                    ["Pinned L0 source", "SHA-256", "Exists"],
                    [
                        (path, digest or "NONE", str(exists))
                        for path, digest, exists in capture.source.pinned_sources
                    ],
                ),
                "",
            ]
        )
    return lines


def _source_preamble_html(analysis: QAAnalysis, index: int) -> list[str]:
    capture = analysis.capture
    rows = [
        ("Source file", capture.source.path),
        ("SHA-256", capture.source.sha256),
        ("Source format", capture.source.format),
        ("Schema namespace", capture.source.schema_namespace),
        (
            "Companion row-validity CSV SHA-256",
            capture.source.companion_sha256 or "NONE",
        ),
        ("Physical evidence category", _evidence_category(analysis)),
        ("Producer physical flag", str(capture.source.is_physical_measurement)),
        (
            "A validity evidence",
            "NONE" if capture.a_validity is None else capture.a_validity.status,
        ),
        ("Rows", str(len(capture.rows))),
        ("Analyzed sessions", str(len(analysis.sessions))),
    ]
    parts = [
        f"<h3>Source {index + 1} — <code>{_html.escape(capture.source.path)}</code></h3>",
        _html_table(("Field", "Value"), rows),
    ]
    if capture.source.pinned_sources:
        parts.append(
            _html_table(
                ("Pinned L0 source", "SHA-256", "Exists"),
                [
                    (path, digest or "NONE", str(exists))
                    for path, digest, exists in capture.source.pinned_sources
                ],
            )
        )
    return parts


def _run_segments_md(analysis: QAAnalysis) -> str:
    rows = []
    for session in analysis.sessions:
        for segment in session.run_segments:
            rows.append(
                (
                    session.session_id,
                    segment.run_id or "NOT_CARRIED",
                    str(segment.row_count),
                    _number(segment.start_s, 3),
                    _number(segment.end_s, 3),
                )
            )
    if not rows:
        return "**Source run_id segments:** NOT_ESTIMABLE."
    multiple = any(len(session.run_segments) > 1 for session in analysis.sessions)
    note = (
        " Multiple `run_id` segments inside one boot are **not** independent "
        "runs and are not split into separate sessions or trajectories."
        if multiple
        else ""
    )
    return (
        "**Source run_id segments (one boot; not independent runs):**"
        + note
        + "\n\n"
        + _md_table(
            ["Session", "Source run_id", "Rows", "Start (s)", "End (s)"],
            rows,
        )
    )


def _run_segments_html(analysis: QAAnalysis) -> str:
    rows = []
    for session in analysis.sessions:
        for segment in session.run_segments:
            rows.append(
                (
                    session.session_id,
                    segment.run_id or "NOT_CARRIED",
                    str(segment.row_count),
                    _number(segment.start_s, 3),
                    _number(segment.end_s, 3),
                )
            )
    if not rows:
        return "<p><strong>Source run_id segments:</strong> NOT_ESTIMABLE.</p>"
    multiple = any(len(session.run_segments) > 1 for session in analysis.sessions)
    note = (
        " Multiple <code>run_id</code> segments inside one boot are <strong>not</strong> "
        "independent runs and are not split into separate sessions or trajectories."
        if multiple
        else ""
    )
    return (
        "<p><strong>Source run_id segments (one boot; not independent runs):</strong>"
        + note
        + "</p>"
        + _html_table(
            ("Session", "Source run_id", "Rows", "Start (s)", "End (s)"),
            rows,
        )
    )


def _inventory_md(analysis: QAAnalysis) -> list[str]:
    run = analysis.capture.run
    time = analysis.capture.time
    session_rows = [
        (
            session.session_id,
            str(session.row_count),
            str(session.unique_identity_count),
            str(session.duplicate_identity_count),
            str(session.scientific_usable_rows),
            _percent(session.scientific_sample_coverage),
        )
        for session in analysis.sessions
    ]
    lines = [
        "#### Run / session inventory",
        "",
        _md_table(
            ["Identity field", "Value", "Status"],
            [
                ("run_id", str(run.run_id), run.run_id_status),
                ("run_ids", ", ".join(run.run_ids) or "NONE", run.run_id_status),
                ("boot_id", str(run.boot_id), run.boot_id_status),
                ("device_id", str(run.device_id), run.device_id_status),
                (
                    "hardware_config_id",
                    str(run.hardware_config_id),
                    run.hardware_config_status,
                ),
                (
                    "firmware_version",
                    str(run.firmware_version),
                    run.firmware_version_status,
                ),
                ("calibration_id", str(run.calibration_id), run.calibration_status),
                ("scenario_id", str(run.scenario_id), run.scenario_status),
                ("controller_id", str(run.controller_id), run.controller_status),
                ("device_run_label", str(run.device_run_label), "LABEL_NOT_A_RUN_ID"),
                ("time domain", time.domain, time.event_time_status),
                ("clock sync", time.clock_sync, time.detail),
            ],
        ),
        "",
        _md_table(
            [
                "Session",
                "Rows",
                "Unique identities",
                "Duplicate identities",
                "Scientific usable rows",
                "Scientific sample coverage",
            ],
            session_rows,
        ),
        "",
        _run_segments_md(analysis),
        "Chamber-air slots: "
        f"{list(analysis.capture.chamber_air_slots) or 'NONE'}; "
        f"TEC hot-side slots: {list(analysis.capture.hot_side_slots) or 'NONE'}; "
        f"unknown role slots: {list(analysis.capture.unknown_role_slots) or 'NONE'}.",
        "",
        "**Sensor role evidence (canonical vs as-built):** Doc 01 §6.4 defines "
        "canonical T1/T2/T3 as near-door/central/far air regions. This hardware's "
        "source carries an operator-frozen as-built record; the table below is "
        "the authoritative role mapping used here. W05 does not apply the "
        "canonical three-air-probe wording to this as-built slot map, and T2 "
        "never enters a chamber-air aggregate.",
        "",
        _md_table(
            [
                "Slot",
                "ROM",
                "ROM readback verified",
                "Physical position",
                "Position source",
                "In chamber-air aggregate",
                "Raw roles in capture",
                "Role conflict",
            ],
            [
                (
                    role.slot,
                    role.rom or "NONE",
                    str(role.rom_readback_verified),
                    role.physical_position or "UNKNOWN",
                    role.position_source or "NONE",
                    str(role.in_chamber_air_aggregate),
                    ", ".join(role.raw_roles) or "NONE",
                    role.role_conflict or "NONE",
                )
                for role in analysis.capture.sensors
            ],
        ),
        "",
    ]
    if analysis.capture.unknown_role_slots:
        lines.append(
            "> Unknown ROM/role slots remain unknown. They are excluded from "
            "role-dependent diagnostics and never silently reassigned."
        )
        lines.append("")
    if any(role.rom_readback_verified is False for role in analysis.capture.sensors):
        lines.append(
            "> ROM readback is not verified by the source. Positions are the "
            "operator-frozen as-built record, not a W05 physical re-measurement; "
            "this limitation is carried into W08."
        )
        lines.append("")
    return lines


def _inventory_html(analysis: QAAnalysis) -> list[str]:
    run = analysis.capture.run
    time = analysis.capture.time
    inventory = [
        ("run_id", str(run.run_id), run.run_id_status),
        ("run_ids", ", ".join(run.run_ids) or "NONE", run.run_id_status),
        ("boot_id", str(run.boot_id), run.boot_id_status),
        ("device_id", str(run.device_id), run.device_id_status),
        (
            "hardware_config_id",
            str(run.hardware_config_id),
            run.hardware_config_status,
        ),
        (
            "firmware_version",
            str(run.firmware_version),
            run.firmware_version_status,
        ),
        ("calibration_id", str(run.calibration_id), run.calibration_status),
        ("scenario_id", str(run.scenario_id), run.scenario_status),
        ("controller_id", str(run.controller_id), run.controller_status),
        ("device_run_label", str(run.device_run_label), "LABEL_NOT_A_RUN_ID"),
        ("time domain", time.domain, time.event_time_status),
        ("clock sync", time.clock_sync, time.detail),
    ]
    session_rows = [
        (
            session.session_id,
            str(session.row_count),
            str(session.unique_identity_count),
            str(session.duplicate_identity_count),
            str(session.scientific_usable_rows),
            _percent(session.scientific_sample_coverage),
        )
        for session in analysis.sessions
    ]
    parts = [
        "<h4>Run / session inventory</h4>",
        _html_table(("Identity field", "Value", "Status"), inventory),
        _html_table(
            (
                "Session",
                "Rows",
                "Unique identities",
                "Duplicate identities",
                "Scientific usable rows",
                "Scientific sample coverage",
            ),
            session_rows,
        ),
        _run_segments_html(analysis),
        "<p>Chamber-air slots: "
        f"{_html.escape(str(list(analysis.capture.chamber_air_slots) or ['NONE']))}; "
        f"TEC hot-side slots: {_html.escape(str(list(analysis.capture.hot_side_slots) or ['NONE']))}; "
        f"unknown role slots: {_html.escape(str(list(analysis.capture.unknown_role_slots) or ['NONE']))}.</p>",
        "<p><strong>Sensor role evidence (canonical vs as-built):</strong> "
        "Doc 01 §6.4 defines canonical T1/T2/T3 as near-door/central/far air "
        "regions. This hardware's source carries an operator-frozen as-built "
        "record; the table below is the authoritative role mapping used here. "
        "W05 does not apply the canonical three-air-probe wording to this "
        "as-built slot map, and T2 never enters a chamber-air aggregate.</p>",
        _html_table(
            (
                "Slot",
                "ROM",
                "ROM readback verified",
                "Physical position",
                "Position source",
                "In chamber-air aggregate",
                "Raw roles in capture",
                "Role conflict",
            ),
            [
                (
                    role.slot,
                    role.rom or "NONE",
                    str(role.rom_readback_verified),
                    role.physical_position or "UNKNOWN",
                    role.position_source or "NONE",
                    str(role.in_chamber_air_aggregate),
                    ", ".join(role.raw_roles) or "NONE",
                    role.role_conflict or "NONE",
                )
                for role in analysis.capture.sensors
            ],
        ),
    ]
    if analysis.capture.unknown_role_slots:
        parts.append(
            "<blockquote>Unknown ROM/role slots remain unknown. They are "
            "excluded from role-dependent diagnostics and never silently "
            "reassigned.</blockquote>"
        )
    if any(role.rom_readback_verified is False for role in analysis.capture.sensors):
        parts.append(
            "<blockquote>ROM readback is not verified by the source. Positions "
            "are the operator-frozen as-built record, not a W05 physical "
            "re-measurement; this limitation is carried into W08.</blockquote>"
        )
    return parts


def _spread_md(analysis: QAAnalysis) -> str:
    rows = []
    for session in analysis.sessions:
        spread = session.chamber_air_spread
        if spread is None:
            rows.append(
                (session.session_id, "NOT_ESTIMABLE", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A")
            )
            continue
        rows.append(
            (
                session.session_id,
                ", ".join(spread.slots),
                str(spread.n),
                _number(spread.min_c, 3),
                _number(spread.median_c, 3),
                _number(spread.p95_c, 3),
                _number(spread.max_c, 3),
                _number(spread.max_time_s, 3),
            )
        )
    return (
        "**Chamber-air spread G_T = max − min (Doc 03 §121):** computed only "
        "from role-qualified chamber-air slots; the TEC hot-side channel is "
        "never included. This is a diagnostic distribution, not a threshold "
        "or a product-quality claim.\n\n"
        + _md_table(
            (
                "Session",
                "Air slots",
                "n",
                "Min (°C)",
                "Median (°C)",
                "P95 (°C)",
                "Max (°C)",
                "Max at (s)",
            ),
            rows,
        )
    )


def _spread_html(analysis: QAAnalysis) -> str:
    rows = []
    for session in analysis.sessions:
        spread = session.chamber_air_spread
        if spread is None:
            rows.append(
                (session.session_id, "NOT_ESTIMABLE", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A")
            )
            continue
        rows.append(
            (
                session.session_id,
                ", ".join(spread.slots),
                str(spread.n),
                _number(spread.min_c, 3),
                _number(spread.median_c, 3),
                _number(spread.p95_c, 3),
                _number(spread.max_c, 3),
                _number(spread.max_time_s, 3),
            )
        )
    return (
        "<p><strong>Chamber-air spread G_T = max − min (Doc 03 §121):</strong> "
        "computed only from role-qualified chamber-air slots; the TEC hot-side "
        "channel is never included. This is a diagnostic distribution, not a "
        "threshold or a product-quality claim.</p>"
        + _html_table(
            (
                "Session",
                "Air slots",
                "n",
                "Min (°C)",
                "Median (°C)",
                "P95 (°C)",
                "Max (°C)",
                "Max at (s)",
            ),
            rows,
        )
    )


def _sampling_md(analysis: QAAnalysis) -> list[str]:
    rows = []
    for session in analysis.sessions:
        stats = session.interval_stats
        rows.append(
            (
                session.session_id,
                stats.time_base_status,
                str(session.row_count),
                str(stats.interval_count),
                _number(stats.median_dt_s, 6),
                _number(stats.p95_dt_s, 6),
                f"{_number(stats.min_positive_dt_s, 6)} / {_number(stats.max_positive_dt_s, 6)}",
                f"{_number(stats.nominal_dt_s, 6)} ({stats.nominal_source}, {stats.nominal_confidence})",
                f"{_number(stats.jitter_median_abs_s, 6)} / {_number(stats.jitter_p95_abs_s, 6)}",
                str(stats.long_gap_count),
                _number(stats.long_gap_total_s, 3),
                str(stats.zero_interval_count),
                str(stats.negative_interval_count),
                _number(stats.seq_missing_estimate),
                _number(stats.time_missing_estimate),
                _number(stats.observation_window_s, 3),
                _number(stats.expected_samples_provisional),
                _percent(stats.captured_frame_completeness),
                stats.completeness_status,
                session.campaign_completeness,
            )
        )
    lines = [
        "#### Sampling QA (B-W05-01)",
        "",
        "Percentile method: "
        f"`{analysis.config.percentile_method}`. "
        "Long-gap rule: a positive interval strictly greater than "
        f"`{analysis.config.long_gap_ms} ms` "
        f"(`{analysis.config.to_dict()['long_gap_policy']}`).",
        "",
        _md_table(
            [
                "Session",
                "Time base",
                "Rows",
                "Intervals",
                "Median Δt (s)",
                "P95 Δt (s)",
                "Min / max positive Δt (s)",
                "Nominal cadence (s)",
                "Jitter median / P95 abs (s)",
                "Long gaps",
                "Long-gap duration (s)",
                "Zero intervals",
                "Negative intervals",
                "Seq-missing estimate",
                "Time-missing estimate",
                "Observed window (s)",
                "Expected samples",
                "Captured-frame completeness",
                "Completeness status",
                "Campaign completeness",
            ],
            rows,
        ),
        "",
        "> Captured-frame completeness is provisional: the nominal cadence is "
        "inferred from observed intervals unless the caller supplied "
        "`--nominal-cadence-ms`, and acquisition boundaries/schedule are not "
        "carried by the source. It is not an authoritative campaign percentage.",
        "",
        "> The observed window is `last time − first time` inside one boot, "
        "not a campaign duration; the source's acquisition schedule and stop "
        "boundary are not carried, so campaign completeness is NOT_ESTIMABLE.",
        "",
        "> A sequence gap is not proof of a missing physical sample unless the "
        "source's sequence semantics are unit-incrementing; the classification "
        "is recorded per session.",
        "",
        _spread_md(analysis),
        "",
    ]
    return lines


def _sampling_html(analysis: QAAnalysis) -> list[str]:
    rows = []
    for session in analysis.sessions:
        stats = session.interval_stats
        rows.append(
            (
                session.session_id,
                stats.time_base_status,
                str(session.row_count),
                str(stats.interval_count),
                _number(stats.median_dt_s, 6),
                _number(stats.p95_dt_s, 6),
                f"{_number(stats.min_positive_dt_s, 6)} / {_number(stats.max_positive_dt_s, 6)}",
                f"{_number(stats.nominal_dt_s, 6)} ({stats.nominal_source}, {stats.nominal_confidence})",
                f"{_number(stats.jitter_median_abs_s, 6)} / {_number(stats.jitter_p95_abs_s, 6)}",
                str(stats.long_gap_count),
                _number(stats.long_gap_total_s, 3),
                str(stats.zero_interval_count),
                str(stats.negative_interval_count),
                _number(stats.seq_missing_estimate),
                _number(stats.time_missing_estimate),
                _number(stats.observation_window_s, 3),
                _number(stats.expected_samples_provisional),
                _percent(stats.captured_frame_completeness),
                stats.completeness_status,
                session.campaign_completeness,
            )
        )
    return [
        "<h4>Sampling QA (B-W05-01)</h4>",
        "<p>Percentile method: "
        f"<code>{_html.escape(analysis.config.percentile_method)}</code>. "
        "Long-gap rule: a positive interval strictly greater than "
        f"<code>{analysis.config.long_gap_ms} ms</code> "
        f"(<code>{_html.escape(analysis.config.to_dict()['long_gap_policy'])}</code>).</p>",
        _html_table(
            (
                "Session",
                "Time base",
                "Rows",
                "Intervals",
                "Median Δt (s)",
                "P95 Δt (s)",
                "Min / max positive Δt (s)",
                "Nominal cadence (s)",
                "Jitter median / P95 abs (s)",
                "Long gaps",
                "Long-gap duration (s)",
                "Zero intervals",
                "Negative intervals",
                "Seq-missing estimate",
                "Time-missing estimate",
                "Observed window (s)",
                "Expected samples",
                "Captured-frame completeness",
                "Completeness status",
                "Campaign completeness",
            ),
            rows,
        ),
        "<blockquote>Captured-frame completeness is provisional: the nominal "
        "cadence is inferred from observed intervals unless the caller supplied "
        "<code>--nominal-cadence-ms</code>, and acquisition boundaries/schedule "
        "are not carried by the source. It is not an authoritative campaign "
        "percentage.</blockquote>",
        "<blockquote>The observed window is <code>last time − first time</code> "
        "inside one boot, not a campaign duration; the source's acquisition "
        "schedule and stop boundary are not carried, so campaign completeness "
        "is NOT_ESTIMABLE.</blockquote>",
        "<blockquote>A sequence gap is not proof of a missing physical sample "
        "unless the source's sequence semantics are unit-incrementing; the "
        "classification is recorded per session.</blockquote>",
        _spread_html(analysis),
    ]


def _pzem_state(analysis: QAAnalysis) -> str:
    powers = [
        channel for channel in analysis.channels if channel.channel == "cooling_power_w"
    ]
    energies = [
        channel
        for channel in analysis.channels
        if channel.channel == "cooling_energy_counter_wh"
    ]
    if not powers and not energies:
        return "ABSENT"
    if all(channel.present_count == 0 for channel in powers + energies):
        return "MISSING"
    power_qualified = bool(powers) and all(
        channel.present_count == channel.row_count
        and channel.quality_valid == channel.row_count
        and channel.impossible_count == 0
        for channel in powers
    )
    energy_qualified = bool(energies) and all(
        channel.present_count == channel.row_count
        and channel.quality_valid == channel.row_count
        and channel.impossible_count == 0
        for channel in energies
    )
    if power_qualified and (not energies or energy_qualified):
        return "QUALIFIED"
    if power_qualified and energies and not energy_qualified:
        return "POWER_QUALIFIED_ENERGY_UNQUALIFIED"
    return "UNQUALIFIED"


def _pzem_note_md(analysis: QAAnalysis) -> str:
    state = _pzem_state(analysis)
    if state == "ABSENT":
        return (
            "**PZEM qualification:** no cooling-branch PZEM channel is carried "
            "by this source."
        )
    if state == "MISSING":
        return (
            "**PZEM qualification:** cooling-branch power/energy values are not "
            "present in this source; no power or energy claim can be made."
        )
    if state == "QUALIFIED":
        return (
            "**PZEM qualification:** the cooling-branch electrical domain is "
            "VALID for every row; this report still makes no whole-system or "
            "COP claim, and the PZEM covers one cooling branch only."
        )
    if state == "POWER_QUALIFIED_ENERGY_UNQUALIFIED":
        return (
            "**PZEM power/energy qualification:** power is VALID for every row, "
            "but energy-counter coverage is missing or unqualified. No energy, "
            "COP or whole-system claim is made from this source."
        )
    return (
        "**UNQUALIFIED PZEM:** cooling-branch power/energy are present but the "
        "electrical quality domain is not VALID for every row, a value is "
        "missing, or an impossible value is present. They are plotted for "
        "diagnostics only and never become validated power, energy, COP or "
        "whole-system claims."
    )


def _pzem_note_html(analysis: QAAnalysis) -> str:
    state = _pzem_state(analysis)
    if state == "ABSENT":
        return (
            "<p><strong>PZEM qualification:</strong> no cooling-branch PZEM "
            "channel is carried by this source.</p>"
        )
    if state == "MISSING":
        return (
            "<p><strong>PZEM qualification:</strong> cooling-branch power/energy "
            "values are not present in this source; no power or energy claim "
            "can be made.</p>"
        )
    if state == "QUALIFIED":
        return (
            "<p><strong>PZEM qualification:</strong> the cooling-branch "
            "electrical domain is VALID for every row; this report still makes "
            "no whole-system or COP claim, and the PZEM covers one cooling "
            "branch only.</p>"
        )
    if state == "POWER_QUALIFIED_ENERGY_UNQUALIFIED":
        return (
            "<p><strong>PZEM power/energy qualification:</strong> power is "
            "VALID for every row, but energy-counter coverage is missing or "
            "unqualified. No energy, COP or whole-system claim is made from "
            "this source.</p>"
        )
    return (
        "<p><strong>UNQUALIFIED PZEM:</strong> cooling-branch power/energy are "
        "present but the electrical quality domain is not VALID for every row, "
        "a value is missing, or an impossible value is present. They are "
        "plotted for diagnostics only and never become validated power, energy, "
        "COP or whole-system claims.</p>"
    )


def _channel_md(analysis: QAAnalysis) -> list[str]:
    rows = [
        (
            channel.session_id,
            channel.channel,
            channel.family,
            channel.physical_role,
            channel.unit or "NONE",
            str(channel.row_count),
            str(channel.present_count),
            str(channel.missing_count),
            _percent(channel.missing_fraction),
            f"{channel.quality_valid}/{channel.quality_degraded}/{channel.quality_invalid}/{channel.quality_unknown}",
            str(channel.impossible_count),
            str(channel.flatline_candidate_count)
            if channel.flatline_candidate_count is not None
            else "N/A",
            str(channel.stale_candidate_count)
            if channel.stale_candidate_count is not None
            else "N/A",
            str(channel.duplicate_identity_count),
            channel.diagnostic_status,
            _code_list(channel.reason_codes),
        )
        for channel in analysis.channels
    ]
    return [
        "#### Channel QA (B-W05-02)",
        "",
        "Quality columns are `VALID/DEGRADED/INVALID/UNKNOWN` counts from the "
        "source's quality domain applicable to the channel; when the source "
        "carries no verdict for that domain the row is counted as UNKNOWN and "
        "the reason code says so. Missing, measured zero, duplicate identity, "
        "flatline candidate and stale candidate remain distinct.",
        "",
        _md_table(
            [
                "Session",
                "Channel",
                "Family",
                "Physical role",
                "Unit",
                "Rows",
                "Present",
                "Missing",
                "Missing %",
                "V/D/I/U",
                "Impossible",
                "Flatline candidates",
                "Stale candidates",
                "Duplicate identity",
                "Diagnostic status",
                "Reason codes",
            ],
            rows,
        ),
        "",
        "The machine-readable equivalent with all required columns is "
        "`channel-summary.csv`.",
        "",
        _pzem_note_md(analysis),
        "",
    ]


def _channel_html(analysis: QAAnalysis) -> list[str]:
    rows = [
        (
            channel.session_id,
            channel.channel,
            channel.family,
            channel.physical_role,
            channel.unit or "NONE",
            str(channel.row_count),
            str(channel.present_count),
            str(channel.missing_count),
            _percent(channel.missing_fraction),
            f"{channel.quality_valid}/{channel.quality_degraded}/{channel.quality_invalid}/{channel.quality_unknown}",
            str(channel.impossible_count),
            str(channel.flatline_candidate_count)
            if channel.flatline_candidate_count is not None
            else "N/A",
            str(channel.stale_candidate_count)
            if channel.stale_candidate_count is not None
            else "N/A",
            str(channel.duplicate_identity_count),
            channel.diagnostic_status,
            _code_list(channel.reason_codes),
        )
        for channel in analysis.channels
    ]
    return [
        "<h4>Channel QA (B-W05-02)</h4>",
        "<p>Quality columns are <code>VALID/DEGRADED/INVALID/UNKNOWN</code> "
        "counts from the source's quality domain applicable to the channel; "
        "when the source carries no verdict for that domain the row is counted "
        "as UNKNOWN and the reason code says so. Missing, measured zero, "
        "duplicate identity, flatline candidate and stale candidate remain "
        "distinct.</p>",
        _html_table(
            (
                "Session",
                "Channel",
                "Family",
                "Physical role",
                "Unit",
                "Rows",
                "Present",
                "Missing",
                "Missing %",
                "V/D/I/U",
                "Impossible",
                "Flatline candidates",
                "Stale candidates",
                "Duplicate identity",
                "Diagnostic status",
                "Reason codes",
            ),
            rows,
        ),
        "<p>The machine-readable equivalent is <code>channel-summary.csv</code>.</p>",
        _pzem_note_html(analysis),
    ]


def _anomalies_md(analysis: QAAnalysis) -> list[str]:
    rows = [
        (
            anomaly.code,
            anomaly.severity,
            anomaly.scope,
            anomaly.channel or "NONE",
            str(anomaly.count) if anomaly.count is not None else "N/A",
            anomaly.detail,
        )
        for anomaly in analysis.anomalies
    ]
    return [
        "#### Findings and anomalies",
        "",
        _md_table(
            ["Code", "Severity", "Scope", "Channel", "Count", "Evidence"],
            rows,
        )
        if rows
        else "No diagnostic anomalies were produced.",
        "",
    ]


def _anomalies_html(analysis: QAAnalysis) -> list[str]:
    rows = [
        (
            anomaly.code,
            anomaly.severity,
            anomaly.scope,
            anomaly.channel or "NONE",
            str(anomaly.count) if anomaly.count is not None else "N/A",
            anomaly.detail,
        )
        for anomaly in analysis.anomalies
    ]
    return [
        "<h4>Findings and anomalies</h4>",
        _html_table(
            ("Code", "Severity", "Scope", "Channel", "Count", "Evidence"),
            rows,
        )
        if rows
        else "<p>No diagnostic anomalies were produced.</p>",
    ]


def _admission_md(
    analysis: QAAnalysis, *, conflicting: bool = False
) -> list[str]:
    admission = analysis.admission
    blockers = [
        (blocker.stage, blocker.code, blocker.detail)
        for blocker in admission.blockers
    ]
    scenarios = [
        (
            scenario.scenario_id,
            _view_value(str(scenario.eligible), conflicting),
            str(scenario.eligible_rows),
            _code_list([blocker.code for blocker in scenario.blockers]),
            _code_list(list(scenario.required_domains)),
        )
        for scenario in admission.scenarios
    ]
    admission_rows = [
        ("status", _view_value(admission.status.value, conflicting)),
        ("highest stage", _view_value(admission.highest_stage.value, conflicting)),
        ("eligible", _view_value(str(admission.eligible), conflicting)),
        (
            "eligible S1 runs",
            _view_value(str(admission.eligible_s1_runs), conflicting),
        ),
        (
            "eligible S2 runs",
            _view_value(str(admission.eligible_s2_runs), conflicting),
        ),
        (
            "predictive dataset readiness",
            _view_value(admission.predictive_dataset_readiness, conflicting),
        ),
    ]
    if conflicting:
        admission_rows.extend(
            [
                ("SOURCE_AUTHORITATIVE_STATUS", _AUTHORITATIVE_SOURCE_STATUS),
                ("SOURCE_AUTHORITATIVE_READINESS", "NOT_READY"),
                ("SOURCE_AUTHORITATIVE_ELIGIBLE_S1_RUNS", "0"),
                ("SOURCE_AUTHORITATIVE_ELIGIBLE_S2_RUNS", "0"),
            ]
        )
    lines = [
        "#### W04 admission verdict (unchanged by W05)",
        "",
    ]
    if conflicting:
        lines.extend([_conflict_warning_md(), ""])
    lines.extend(
        [
            _md_table(["Admission field", "Value"], admission_rows),
            "",
        ]
    )
    if blockers:
        lines.extend(
            [
                _md_table(["Stage", "Blocker", "Detail"], blockers),
                "",
            ]
        )
    if scenarios:
        lines.extend(
            [
                _md_table(
                    [
                        "Scenario",
                        "Eligible",
                        "Eligible rows",
                        "Blockers",
                        "Required domains",
                    ],
                    scenarios,
                ),
                "",
            ]
        )
    return lines


def _admission_html(
    analysis: QAAnalysis, *, conflicting: bool = False
) -> list[str]:
    admission = analysis.admission
    blockers = [
        (blocker.stage, blocker.code, blocker.detail)
        for blocker in admission.blockers
    ]
    scenarios = [
        (
            scenario.scenario_id,
            _view_value(str(scenario.eligible), conflicting),
            str(scenario.eligible_rows),
            _code_list([blocker.code for blocker in scenario.blockers]),
            _code_list(list(scenario.required_domains)),
        )
        for scenario in admission.scenarios
    ]
    admission_rows = [
        ("status", _view_value(admission.status.value, conflicting)),
        ("highest stage", _view_value(admission.highest_stage.value, conflicting)),
        ("eligible", _view_value(str(admission.eligible), conflicting)),
        (
            "eligible S1 runs",
            _view_value(str(admission.eligible_s1_runs), conflicting),
        ),
        (
            "eligible S2 runs",
            _view_value(str(admission.eligible_s2_runs), conflicting),
        ),
        (
            "predictive dataset readiness",
            _view_value(admission.predictive_dataset_readiness, conflicting),
        ),
    ]
    if conflicting:
        admission_rows.extend(
            [
                ("SOURCE_AUTHORITATIVE_STATUS", _AUTHORITATIVE_SOURCE_STATUS),
                ("SOURCE_AUTHORITATIVE_READINESS", "NOT_READY"),
                ("SOURCE_AUTHORITATIVE_ELIGIBLE_S1_RUNS", "0"),
                ("SOURCE_AUTHORITATIVE_ELIGIBLE_S2_RUNS", "0"),
            ]
        )
    parts = ["<h4>W04 admission verdict (unchanged by W05)</h4>"]
    if conflicting:
        parts.append(_conflict_warning_html())
    parts.append(
        _html_table(
            ("Admission field", "Value"),
            admission_rows,
        )
    )
    if blockers:
        parts.append(
            _html_table(("Stage", "Blocker", "Detail"), blockers)
        )
    if scenarios:
        parts.append(
            _html_table(
                (
                    "Scenario",
                    "Eligible",
                    "Eligible rows",
                    "Blockers",
                    "Required domains",
                ),
                scenarios,
            )
        )
    return parts


def _plots_md(analysis: QAAnalysis, plot_names: Sequence[str]) -> list[str]:
    lines = ["#### Physical-state plots (B-W05-03)", ""]
    for session, name in zip(analysis.sessions, plot_names):
        lines.extend(
            [
                f"![Physical-state diagnostics for {session.session_id}]({name})",
                "",
                f"Session `{session.session_id}`: one aligned time domain per "
                "panel set. Gaps are not connected, missing values are not "
                "zero-filled, TEC hot-side is separate from chamber air, and "
                "unqualified PZEM power is dashed and marked diagnostic-only.",
                "",
            ]
        )
    return lines


def _plots_html(analysis: QAAnalysis, svgs: Sequence[str]) -> list[str]:
    parts = ["<h4>Physical-state plots (B-W05-03)</h4>"]
    for session, svg in zip(analysis.sessions, svgs):
        parts.append(
            f'<div class="plot">{svg}</div>'
            f"<p>Session <code>{_html.escape(session.session_id)}</code>: one "
            "aligned time domain per panel set. Gaps are not connected, "
            "missing values are not zero-filled, TEC hot-side is separate from "
            "chamber air, and unqualified PZEM power is dashed and marked "
            "diagnostic-only.</p>"
        )
    return parts


def _limits_md(
    analysis: QAAnalysis, *, conflicting: bool = False
) -> list[str]:
    limits = [
        "Captured-frame completeness is provisional; campaign completeness is NOT_ESTIMABLE without source-carried acquisition boundaries.",
        "Long-gap and stale thresholds are named diagnostic-only configuration, not feature-eligibility limits.",
        "Flatline results are FLATLINE_CANDIDATE only; repeated equal values do not prove sensor failure, and state/counter channels are not flatline-tested. Spans break on a missing value, a source-quality INVALID row, an interval above the long-gap threshold, or a value leaving the configured tolerance band, not on every gap in the timestamp series.",
        "PZEM power/energy values are diagnostic only while the electrical quality domain is not VALID; no validated power, energy, COP or whole-system claim is made.",
        "TEC hot-side temperature is never chamber air and never enters a chamber-air mean or gradient.",
        "Unknown ROM/role, unknown door polarity and UNKNOWN door state remain unknown; none is silently converted.",
        (
            "This view-level W04 verdict is not the authoritative source verdict; "
            "conflicting duplicate views are excluded by the suite, whose "
            "authoritative result is EXCLUDED_OR_BLOCKED / NOT_READY. Readable "
            "diagnostics never upgrade run validity."
            if conflicting
            else "The W04 admission verdict is authoritative and unchanged; "
            "readable diagnostics never upgrade run validity."
        ),
        "No interpolation, invented sensor value, cross-boot uptime subtraction or cross-boot absolute-time comparison is performed.",
        "No B-side run manifest exists in this repository; W05 consumes A's run index and reports run/session identity. Run-manifest consistency remains an A/C dependency.",
    ]
    if analysis.statuses.predictive_dataset_readiness == "NOT_READY":
        limits.append(
            "Predictive dataset readiness is NOT_READY; this report is a diagnostic audit, not a research dataset."
        )
    return ["#### Scientific limits", ""] + [f"- {item}" for item in limits] + [""]


def _limits_html(
    analysis: QAAnalysis, *, conflicting: bool = False
) -> list[str]:
    items = [
        "Captured-frame completeness is provisional; campaign completeness is NOT_ESTIMABLE without source-carried acquisition boundaries.",
        "Long-gap and stale thresholds are named diagnostic-only configuration, not feature-eligibility limits.",
        "Flatline results are FLATLINE_CANDIDATE only; repeated equal values do not prove sensor failure, and state/counter channels are not flatline-tested. Spans break on a missing value, a source-quality INVALID row, an interval above the long-gap threshold, or a value leaving the configured tolerance band, not on every gap in the timestamp series.",
        "PZEM power/energy values are diagnostic only while the electrical quality domain is not VALID; no validated power, energy, COP or whole-system claim is made.",
        "TEC hot-side temperature is never chamber air and never enters a chamber-air mean or gradient.",
        "Unknown ROM/role, unknown door polarity and UNKNOWN door state remain unknown; none is silently converted.",
        (
            "This view-level W04 verdict is not the authoritative source verdict; "
            "conflicting duplicate views are excluded by the suite, whose "
            "authoritative result is EXCLUDED_OR_BLOCKED / NOT_READY. Readable "
            "diagnostics never upgrade run validity."
            if conflicting
            else "The W04 admission verdict is authoritative and unchanged; "
            "readable diagnostics never upgrade run validity."
        ),
        "No interpolation, invented sensor value, cross-boot uptime subtraction or cross-boot absolute-time comparison is performed.",
        "No B-side run manifest exists in this repository; W05 consumes A's run index and reports run/session identity. Run-manifest consistency remains an A/C dependency.",
    ]
    if analysis.statuses.predictive_dataset_readiness == "NOT_READY":
        items.append(
            "Predictive dataset readiness is NOT_READY; this report is a diagnostic audit, not a research dataset."
        )
    return ["<h4>Scientific limits</h4><ul>"] + [
        f"<li>{_html.escape(item)}</li>" for item in items
    ] + ["</ul>"]


def _handoff_md(
    analysis: QAAnalysis, *, conflicting: bool = False
) -> list[str]:
    timing = []
    for session in analysis.sessions:
        stats = session.interval_stats
        timing.append(
            f"`{session.session_id}`: time base `{stats.time_base_status}`, "
            f"median Δt {_number(stats.median_dt_s, 6)} s, P95 "
            f"{_number(stats.p95_dt_s, 6)} s, long gaps "
            f"{stats.long_gap_count}, zero intervals "
            f"{stats.zero_interval_count}, sequence semantics "
            f"`{stats.seq_semantics}`."
        )
    readiness = analysis.statuses.predictive_dataset_readiness
    admission = analysis.admission
    lines = [
        "#### W06 / W08 handoff",
        "",
        "**W06 (timing alignment) observations only — no W06 implementation:**",
        "",
    ]
    lines.extend(f"- {item}" for item in timing)
    lines.extend(
        [
            "",
            "**W08 (dataset readiness) observations only — no W08 implementation:**",
            "",
        ]
    )
    if conflicting:
        lines.extend([_conflict_warning_md(), ""])
        lines.extend(
            [
                f"- View-level predictive dataset readiness: `{readiness}` "
                f"({_VIEW_ONLY}); view-level eligible S1 runs "
                f"{admission.eligible_s1_runs}; eligible S2 runs "
                f"{admission.eligible_s2_runs}.",
                "- Authoritative source result: "
                f"`{_AUTHORITATIVE_SOURCE_STATUS}`; authoritative suite "
                "readiness `NOT_READY`; authoritative eligible S1/S2 runs 0.",
            ]
        )
    else:
        lines.append(
            f"- Predictive dataset readiness: `{readiness}`; eligible S1 runs "
            f"{admission.eligible_s1_runs}; eligible S2 runs "
            f"{admission.eligible_s2_runs}."
        )
    lines.extend(
        [
            f"- Run identity status: `{analysis.capture.run.run_id_status}`; "
            "multiple filenames or row labels were not counted as independent runs.",
            (
                "- Channel/run validity observations are in "
                "`channel-summary.csv`; this view's verdict is not authoritative "
                "for the conflicting source."
                if conflicting
                else "- Channel/run validity observations are in "
                "`channel-summary.csv`; the W04 admission ledger remains "
                "authoritative."
            ),
            "",
        ]
    )
    return lines


def _handoff_html(
    analysis: QAAnalysis, *, conflicting: bool = False
) -> list[str]:
    timing = []
    for session in analysis.sessions:
        stats = session.interval_stats
        timing.append(
            f"{session.session_id}: time base {stats.time_base_status}, "
            f"median Δt {_number(stats.median_dt_s, 6)} s, P95 "
            f"{_number(stats.p95_dt_s, 6)} s, long gaps {stats.long_gap_count}, "
            f"zero intervals {stats.zero_interval_count}, sequence semantics "
            f"{stats.seq_semantics}."
        )
    admission = analysis.admission
    return (
        ["<h4>W06 / W08 handoff</h4>",
         "<p><strong>W06 (timing alignment) observations only — no W06 "
         "implementation:</strong></p><ul>"]
        + [f"<li>{_html.escape(item)}</li>" for item in timing]
        + [
            "</ul><p><strong>W08 (dataset readiness) observations only — no "
            "W08 implementation:</strong></p>",
        ]
        + ([_conflict_warning_html()] if conflicting else [])
        + [
            "<ul>",
            (
                f"<li>View-level predictive dataset readiness: "
                f"<code>{_html.escape(analysis.statuses.predictive_dataset_readiness)}</code> "
                f"({_html.escape(_VIEW_ONLY)}); view-level eligible S1 runs "
                f"{admission.eligible_s1_runs}; eligible S2 runs "
                f"{admission.eligible_s2_runs}.</li>"
                "<li>Authoritative source result: "
                f"<code>{_html.escape(_AUTHORITATIVE_SOURCE_STATUS)}</code>; "
                "authoritative suite readiness <code>NOT_READY</code>; "
                "authoritative eligible S1/S2 runs 0.</li>"
                if conflicting
                else f"<li>Predictive dataset readiness: "
                f"<code>{_html.escape(analysis.statuses.predictive_dataset_readiness)}</code>; "
                f"eligible S1 runs {admission.eligible_s1_runs}; eligible S2 runs "
                f"{admission.eligible_s2_runs}.</li>"
            ),
            f"<li>Run identity status: "
            f"<code>{_html.escape(analysis.capture.run.run_id_status)}</code>; "
            "multiple filenames or row labels were not counted as independent "
            "runs.</li>",
            (
                "<li>Channel/run validity observations are in "
                "<code>channel-summary.csv</code>; this view's verdict is not "
                "authoritative for the conflicting source.</li>"
                if conflicting
                else "<li>Channel/run validity observations are in "
                "<code>channel-summary.csv</code>; the W04 admission ledger "
                "remains authoritative.</li>"
            ),
            "</ul>",
        ]
    )


def _header_md(
    analyses: Sequence[QAAnalysis],
    suite: QASuiteSummary,
    *,
    revision: str,
    command: str,
    output_label: str,
    code_sha256: str,
    source_index: dict[str, Any] | None,
) -> list[str]:
    conflict_views = _conflict_view_keys(suite)
    lines = [
        "# ColdGuard W05 — Real Telemetry QA Report",
        "",
        "Diagnostic QA over the W04 source-aware intake. No model training, no "
        "predictive feature construction, and no physical re-adjudication.",
        "",
        "## 0. Five independent statuses",
        "",
    ]
    for index, analysis in enumerate(analyses):
        conflicting = (
            analysis.capture.source.path,
            analysis.capture.source.sha256,
        ) in conflict_views
        rows = _status_rows(analysis, conflicting=conflicting)
        lines.extend(
            [
                f"**Source {index + 1}: `{analysis.capture.source.path}`**",
                "",
                _md_table(["Status", "Value"], rows),
                "",
            ]
        )
    lines.extend(
        [
            "A single `PASS` never implies that all five statuses are green.",
            "",
            "## 1. Provenance",
            "",
            _md_table(
                ["Field", "Value"],
                [
                    ("Report schema", REPORT_VERSION),
                    ("Package version", PACKAGE_VERSION),
                    ("QA layer version", QA_LAYER_VERSION),
                    ("Analysis code SHA-256", f"`{code_sha256}`"),
                    ("Repository revision", revision),
                    ("Generation command", f"`{command}`"),
                    ("Output directory", f"`{output_label}`"),
                    (
                        "A run index",
                        "NONE"
                        if source_index is None
                        else f"`{source_index['path']}` (SHA-256 `{source_index['sha256']}`)",
                    ),
                ],
            ),
            "",
        ]
    )
    if source_index is not None:
        lines.extend(
            [
                _md_table(
                    ["Run-index field", "Value"],
                    [
                        ("index_version", str(source_index["index_version"])),
                        ("runs_total", str(source_index["runs_total"])),
                        (
                            "runs_usable_majority",
                            str(source_index["runs_usable_majority"]),
                        ),
                        (
                            "valid S1 run IDs for B",
                            _code_list(source_index["valid_s1_run_ids_for_member_b"]),
                        ),
                        (
                            "blocked run IDs",
                            _code_list(
                                [
                                    str(item.get("run_id") or item.get("boot_id"))
                                    for item in source_index["blocked_run_ids"]
                                ]
                            ),
                        ),
                    ],
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## 2. Suite summary",
            "",
            _md_table(
                ["Field", "Value"],
                [
                    ("Analyzed sources", str(suite.analyzed_sources)),
                    (
                        "Unique physical sources",
                        str(suite.unique_physical_sources),
                    ),
                    ("Duplicate views", str(suite.duplicate_views)),
                    ("Eligible S1 runs", str(suite.eligible_s1_runs)),
                    ("Eligible S2 runs", str(suite.eligible_s2_runs)),
                    (
                        "Predictive dataset readiness",
                        suite.predictive_dataset_readiness,
                    ),
                    (
                        "Conflicting duplicate-view admissions",
                        str(len(suite.conflicts)),
                    ),
                ],
            ),
            "",
            "### Row / boot / run / eligibility separation",
            "",
            _md_table(
                ["Concept", "Count", "Meaning"],
                [
                    (
                        "Recorded rows",
                        str(sum(len(analysis.capture.rows) for analysis in analyses)),
                        "observations in the analyzed sources; not experiments",
                    ),
                    (
                        "Analyzed boot sessions",
                        str(sum(len(analysis.sessions) for analysis in analyses)),
                        "one boot domain per session; uptime is never joined across boots",
                    ),
                    (
                        "Unique physical sources",
                        str(suite.unique_physical_sources),
                        "deduplicated by device/boot session, not by filename or run label",
                    ),
                    (
                        "Duplicate views",
                        str(suite.duplicate_views),
                        "repeated exports of one physical source; not new independent runs",
                    ),
                    (
                        "A-valid S1 run IDs",
                        str(
                            len(source_index["valid_s1_run_ids_for_member_b"])
                            if source_index is not None
                            else 0
                        ),
                        "authoritative A hand-off list",
                    ),
                    (
                        "W04 eligible S1 runs",
                        str(suite.eligible_s1_runs),
                        "physically qualified and predictively admissible",
                    ),
                    (
                        "W04 eligible S2 runs",
                        str(suite.eligible_s2_runs),
                        "physically qualified and predictively admissible",
                    ),
                    (
                        "Predictive dataset readiness",
                        suite.predictive_dataset_readiness,
                        "training/validation availability under W04 admission",
                    ),
                ],
            ),
            "",
            "> These counts are not interchangeable. A large row count, a boot "
            "session, an A-valid run and an ML-eligible run are four different "
            "units.",
            "",
        ]
    )
    return lines


def _header_html(
    analyses: Sequence[QAAnalysis],
    suite: QASuiteSummary,
    *,
    revision: str,
    command: str,
    output_label: str,
    code_sha256: str,
    source_index: dict[str, Any] | None,
) -> list[str]:
    conflict_views = _conflict_view_keys(suite)
    parts = [
        "<h1>ColdGuard W05 — Real Telemetry QA Report</h1>",
        "<p>Diagnostic QA over the W04 source-aware intake. No model training, "
        "no predictive feature construction, and no physical re-adjudication.</p>",
        "<h2>0. Five independent statuses</h2>",
    ]
    for index, analysis in enumerate(analyses):
        conflicting = (
            analysis.capture.source.path,
            analysis.capture.source.sha256,
        ) in conflict_views
        parts.append(
            f"<p><strong>Source {index + 1}: "
            f"<code>{_html.escape(analysis.capture.source.path)}</code></strong></p>"
        )
        parts.append(
            _html_table(
                ("Status", "Value"),
                _status_rows(analysis, conflicting=conflicting),
            )
        )
    parts.append(
        "<p>A single <code>PASS</code> never implies that all five statuses "
        "are green.</p><h2>1. Provenance</h2>"
    )
    parts.append(
        _html_table(
            ("Field", "Value"),
            [
                ("Report schema", REPORT_VERSION),
                ("Package version", PACKAGE_VERSION),
                ("QA layer version", QA_LAYER_VERSION),
                ("Analysis code SHA-256", code_sha256),
                ("Repository revision", revision),
                ("Generation command", command),
                ("Output directory", output_label),
                (
                    "A run index",
                    "NONE"
                    if source_index is None
                    else f"{source_index['path']} (SHA-256 {source_index['sha256']})",
                ),
            ],
        )
    )
    if source_index is not None:
        parts.append(
            _html_table(
                ("Run-index field", "Value"),
                [
                    ("index_version", str(source_index["index_version"])),
                    ("runs_total", str(source_index["runs_total"])),
                    (
                        "runs_usable_majority",
                        str(source_index["runs_usable_majority"]),
                    ),
                    (
                        "valid S1 run IDs for B",
                        _code_list(source_index["valid_s1_run_ids_for_member_b"]),
                    ),
                    (
                        "blocked run IDs",
                        _code_list(
                            [
                                str(item.get("run_id") or item.get("boot_id"))
                                for item in source_index["blocked_run_ids"]
                            ]
                        ),
                    ),
                ],
            )
        )
    parts.append("<h2>2. Suite summary</h2>")
    parts.append(
        _html_table(
            ("Field", "Value"),
            [
                ("Analyzed sources", str(suite.analyzed_sources)),
                ("Unique physical sources", str(suite.unique_physical_sources)),
                ("Duplicate views", str(suite.duplicate_views)),
                ("Eligible S1 runs", str(suite.eligible_s1_runs)),
                ("Eligible S2 runs", str(suite.eligible_s2_runs)),
                (
                    "Predictive dataset readiness",
                    suite.predictive_dataset_readiness,
                ),
                (
                    "Conflicting duplicate-view admissions",
                    str(len(suite.conflicts)),
                ),
            ],
        )
    )
    parts.append("<h3>Row / boot / run / eligibility separation</h3>")
    parts.append(
        _html_table(
            ("Concept", "Count", "Meaning"),
            [
                (
                    "Recorded rows",
                    str(sum(len(analysis.capture.rows) for analysis in analyses)),
                    "observations in the analyzed sources; not experiments",
                ),
                (
                    "Analyzed boot sessions",
                    str(sum(len(analysis.sessions) for analysis in analyses)),
                    "one boot domain per session; uptime is never joined across boots",
                ),
                (
                    "Unique physical sources",
                    str(suite.unique_physical_sources),
                    "deduplicated by device/boot session, not by filename or run label",
                ),
                (
                    "Duplicate views",
                    str(suite.duplicate_views),
                    "repeated exports of one physical source; not new independent runs",
                ),
                (
                    "A-valid S1 run IDs",
                    str(
                        len(source_index["valid_s1_run_ids_for_member_b"])
                        if source_index is not None
                        else 0
                    ),
                    "authoritative A hand-off list",
                ),
                (
                    "W04 eligible S1 runs",
                    str(suite.eligible_s1_runs),
                    "physically qualified and predictively admissible",
                ),
                (
                    "W04 eligible S2 runs",
                    str(suite.eligible_s2_runs),
                    "physically qualified and predictively admissible",
                ),
                (
                    "Predictive dataset readiness",
                    suite.predictive_dataset_readiness,
                    "training/validation availability under W04 admission",
                ),
            ],
        )
    )
    parts.append(
        "<blockquote>These counts are not interchangeable. A large row count, "
        "a boot session, an A-valid run and an ML-eligible run are four "
        "different units.</blockquote>"
    )
    return parts


def _render_markdown(
    analyses: Sequence[QAAnalysis],
    suite: QASuiteSummary,
    *,
    revision: str,
    command: str,
    output_label: str,
    code_sha256: str,
    source_index: dict[str, Any] | None,
    plot_names: Sequence[Sequence[str]],
) -> str:
    lines = _header_md(
        analyses,
        suite,
        revision=revision,
        command=command,
        output_label=output_label,
        code_sha256=code_sha256,
        source_index=source_index,
    )
    conflict_views = _conflict_view_keys(suite)
    lines.extend(["## 3. Per-source QA", ""])
    for index, analysis in enumerate(analyses):
        conflicting = (
            analysis.capture.source.path,
            analysis.capture.source.sha256,
        ) in conflict_views
        lines.extend(_source_preamble_md(analysis, index))
        lines.extend(_inventory_md(analysis))
        lines.extend(_sampling_md(analysis))
        lines.extend(_channel_md(analysis))
        lines.extend(_plots_md(analysis, plot_names[index]))
        lines.extend(_anomalies_md(analysis))
        lines.extend(_limits_md(analysis, conflicting=conflicting))
        lines.extend(_handoff_md(analysis, conflicting=conflicting))
        lines.extend(_admission_md(analysis, conflicting=conflicting))
    lines.extend(
        [
            "## 4. Reproduction",
            "",
            "```bash",
            "cd ml",
            f"uv run --locked --python 3.12 --extra test python scripts/{command}",
            "```",
            "",
            "Repeated execution on the same source and configuration produces "
            "identical analytical numbers and stable serialized report content. "
            "The report contains no runtime generation timestamp and no local "
            "absolute path.",
            "",
        ]
    )
    if suite.conflicts:
        lines.extend(
            [
                "## 5. Duplicate-view admission conflicts",
                "",
                "`summary_readiness` failed closed on contradictory views of one "
                "physical source. The source is excluded; no favorable view was "
                "kept. Per-view verdicts remain in `qa-manifest-W05.json`.",
                "",
                _md_table(
                    [
                        "Source paths",
                        "Adjudicated status",
                        "Highest stage",
                        "Blockers",
                        "Views",
                    ],
                    _conflict_rows(suite),
                ),
                "",
            ]
        )
    return "\n".join(lines).rstrip("\n") + "\n"


def _render_html(
    analyses: Sequence[QAAnalysis],
    suite: QASuiteSummary,
    *,
    revision: str,
    command: str,
    output_label: str,
    code_sha256: str,
    source_index: dict[str, Any] | None,
    svgs: Sequence[Sequence[str]],
) -> str:
    style = """
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:2rem auto;max-width:1380px;padding:0 1rem;color:#1c1c1c;line-height:1.45}
h1,h2,h3,h4{line-height:1.2}code{background:#f2f2f2;padding:1px 4px;border-radius:3px}
table{border-collapse:collapse;width:100%;margin:0.6rem 0 1.2rem;font-size:13px}
th,td{border:1px solid #d8d8d8;padding:5px 7px;text-align:left;vertical-align:top}
th{background:#f5f5f5}blockquote{border-left:4px solid #d0a000;margin:0.8rem 0;padding:0.2rem 1rem;background:#fffaf0}
.plot{overflow-x:auto;border:1px solid #ddd;margin:0.8rem 0}.plot svg{display:block;min-width:1000px}
"""
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<title>ColdGuard W05 Real Telemetry QA</title>",
        f"<style>{style}</style></head><body>",
    ]
    parts.extend(
        _header_html(
            analyses,
            suite,
            revision=revision,
            command=command,
            output_label=output_label,
            code_sha256=code_sha256,
            source_index=source_index,
        )
    )
    conflict_views = _conflict_view_keys(suite)
    parts.append("<h2>3. Per-source QA</h2>")
    for index, analysis in enumerate(analyses):
        conflicting = (
            analysis.capture.source.path,
            analysis.capture.source.sha256,
        ) in conflict_views
        parts.extend(_source_preamble_html(analysis, index))
        parts.extend(_inventory_html(analysis))
        parts.extend(_sampling_html(analysis))
        parts.extend(_channel_html(analysis))
        parts.extend(_plots_html(analysis, svgs[index]))
        parts.extend(_anomalies_html(analysis))
        parts.extend(_limits_html(analysis, conflicting=conflicting))
        parts.extend(_handoff_html(analysis, conflicting=conflicting))
        parts.extend(_admission_html(analysis, conflicting=conflicting))
    parts.append(
        "<h2>4. Reproduction</h2><pre><code>cd ml\nuv run --locked "
        "--python 3.12 --extra test python scripts/"
        f"{_html.escape(command)}</code></pre>"
        "<p>Repeated execution on the same source and configuration produces "
        "identical analytical numbers and stable serialized report content. "
        "The report contains no runtime generation timestamp and no local "
        "absolute path.</p>"
    )
    if suite.conflicts:
        parts.append(
            "<h2>5. Duplicate-view admission conflicts</h2>"
            "<p><code>summary_readiness</code> failed closed on contradictory "
            "views of one physical source. The source is excluded; no favorable "
            "view was kept. Per-view verdicts remain in "
            "<code>qa-manifest-W05.json</code>.</p>"
        )
        parts.append(
            _html_table(
                (
                    "Source paths",
                    "Adjudicated status",
                    "Highest stage",
                    "Blockers",
                    "Views",
                ),
                _conflict_rows(suite),
            )
        )
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="real-data-qa-v1.py",
        description=(
            "ColdGuard W05 real-telemetry QA: sampling intervals, per-channel "
            "quality, physical-state plots and a reproducible report over the "
            "W04 source-aware intake."
        ),
    )
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="A W09 export or C telemetry-v1 snapshot; repeat for multiple sources",
    )
    parser.add_argument(
        "--a-run-index",
        default=None,
        help="A's W09 run index (authoritative physical-validity hand-off)",
    )
    parser.add_argument(
        "--out",
        default="reports/W05",
        help="output directory for report, CSV, plots and manifest",
    )
    parser.add_argument(
        "--format",
        choices=(_MD, _HTML, _BOTH),
        default=_BOTH,
        help="report serialization format",
    )
    parser.add_argument("--long-gap-ms", type=int, default=5000)
    parser.add_argument("--flatline-min-observations", type=int, default=10)
    parser.add_argument("--flatline-min-span-s", type=float, default=0.0)
    parser.add_argument(
        "--flatline-temperature-tolerance-c", type=float, default=0.0625
    )
    parser.add_argument("--stale-age-ms", type=int, default=5000)
    parser.add_argument("--nominal-cadence-ms", type=float, default=None)
    parser.add_argument(
        "--percentile",
        choices=("linear", "nearest_rank"),
        default="linear",
    )
    parser.add_argument(
        "--repository-revision",
        default=None,
        help=(
            "record this repository revision instead of asking git; used when "
            "the analyzed code commit is known before artifact publication"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    root = _repo_root()
    try:
        config = QAConfig(
            long_gap_ms=args.long_gap_ms,
            flatline_min_observations=args.flatline_min_observations,
            flatline_min_span_s=args.flatline_min_span_s,
            flatline_temperature_tolerance_c=args.flatline_temperature_tolerance_c,
            stale_age_ms=args.stale_age_ms,
            nominal_cadence_ms=args.nominal_cadence_ms,
            percentile_method=args.percentile,
        )
        config.validate()
    except ValueError as exc:
        print(f"CONFIGURATION_ERROR: {exc}", file=sys.stderr)
        return 1

    captures = []
    refusals: list[str] = []
    for source in args.source:
        try:
            captures.append(
                load_capture(source, a_run_index=args.a_run_index)
            )
        except SourceRefusal as exc:
            refusals.append(f"{_safe_path(source, root)}: {exc.code}: {exc.detail}")
        except Exception as exc:
            refusals.append(
                f"{_safe_path(source, root)}: {type(exc).__name__}: {exc}"
            )
    if refusals or not captures:
        for refusal in refusals:
            print(f"REFUSED: {refusal}", file=sys.stderr)
        return 2

    analyses = analyze_captures(captures, config=config)
    if any(
        analysis.statuses.source_structure_status != "VALID"
        for analysis in analyses
    ):
        for analysis in analyses:
            if analysis.statuses.source_structure_status != "VALID":
                print(
                    "STRUCTURE_INVALID: "
                    f"{analysis.capture.source.path}: "
                    f"{[blocker.code for blocker in analysis.admission.blockers if blocker.stage in ('SOURCE_RECOGNIZED', 'STRUCTURALLY_VALID')]}",
                    file=sys.stderr,
                )
        return 2

    suite = summarize_qa_suite(analyses)
    try:
        source_index = _source_index_metadata(args.a_run_index, root)
    except SourceRefusal as exc:
        print(f"REFUSED: run index: {exc.code}: {exc.detail}", file=sys.stderr)
        return 2
    command = _command_line(args, root)
    revision = args.repository_revision or _repository_revision(root)

    plot_names: list[list[str]] = []
    svg_documents: list[list[str]] = []
    for source_index_number, analysis in enumerate(analyses):
        names: list[str] = []
        documents: list[str] = []
        for session_index, session in enumerate(analysis.sessions):
            name = _plot_name(
                source_index_number,
                session_index,
                len(analyses),
                len(analysis.sessions),
            )
            names.append(name)
            documents.append(
                render_physical_state_svg(
                    analysis.capture,
                    analysis.admission,
                    session,
                    config=config,
                )
            )
        plot_names.append(names)
        svg_documents.append(documents)

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_label = _safe_path(args.out, root)
    code_sha256 = _analysis_code_sha256()
    markdown = _render_markdown(
        analyses,
        suite,
        revision=revision,
        command=command,
        output_label=output_label,
        code_sha256=code_sha256,
        source_index=source_index,
        plot_names=plot_names,
    )
    html_report = _render_html(
        analyses,
        suite,
        revision=revision,
        command=command,
        output_label=output_label,
        code_sha256=code_sha256,
        source_index=source_index,
        svgs=svg_documents,
    )
    if args.format in (_MD, _BOTH):
        (output_dir / "qa-report-W05.md").write_text(
            markdown, encoding="utf-8", newline="\n"
        )
    if args.format in (_HTML, _BOTH):
        (output_dir / "qa-report-W05.html").write_text(
            html_report, encoding="utf-8", newline="\n"
        )
    (output_dir / "channel-summary.csv").write_text(
        channel_summary_csv(analyses), encoding="utf-8", newline="\n"
    )
    for names, documents in zip(plot_names, svg_documents):
        for name, document in zip(names, documents):
            (output_dir / name).write_text(
                document, encoding="utf-8", newline="\n"
            )
    manifest = qa_manifest(
        analyses,
        suite,
        config=config,
        command=command,
        repository_revision=revision,
        analysis_code_sha256=code_sha256,
        source_index=source_index,
    )
    (output_dir / "qa-manifest-W05.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        "W05 QA COMPLETE: "
        f"{len(analyses)} source(s), "
        f"{suite.unique_physical_sources} unique physical source(s), "
        f"readiness {suite.predictive_dataset_readiness}; "
        f"artifacts in {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
