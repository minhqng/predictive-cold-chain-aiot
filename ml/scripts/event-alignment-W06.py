#!/usr/bin/env python3
"""ColdGuard W06 executable event alignment (B-W06-01 … B-W06-04).

Usage::

    python ml/scripts/event-alignment-W06.py
        [--source PATH ...] [--a-run-index PATH]
        [--a-command-log PATH ...] [--a-command-provenance LABEL]
        [--event-fixture PATH ...] [--out DIR]
        [--baseline-window-s F] [--electrical-max-window-s F]
        [--thermal-max-window-s F] [--max-gap-s F]
        [--sustained-observations N]
        [--electrical-min-change-a F] [--thermal-min-change-c F]
        [--repository-revision REV] [--format md|json|both]

The CLI consumes the W04 normalized capture model for A exports and C
snapshots. A's ``#CG CMDACK schema=1`` serial command log has its own
versioned adapter; serial telemetry frames are never fed through the C JSON
telemetry parser.

Exit codes:

* ``0`` — every input loaded and the analysis completed. An honest
  ``ABSENT`` command-lifecycle evidence result is a successful W06 run.
* ``1`` — invalid CLI configuration or internal/IO error.
* ``2`` — a source, command log or fixture was refused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

try:  # installed package
    from coldguard_ml import (
        SourceRefusal,
        __version__ as PACKAGE_VERSION,
        evaluate_admission,
        load_capture,
        summarize_readiness,
    )
    from coldguard_ml import timing_alignment as _timing
    from coldguard_ml.timing_alignment import (
        DEFAULT_ELECTRICAL_POLICY,
        DEFAULT_THERMAL_POLICY,
        EVENT_APPLIED_STATE,
        EVENT_COMMAND_CREATED_OR_PUBLISHED,
        EVENT_DEVICE_ACK,
        EVENT_DOOR_TRANSITION,
        EVENT_ELECTRICAL_RESPONSE,
        EVENT_TELEMETRY_SAMPLE,
        EVENT_THERMAL_RESPONSE,
        PROVENANCE_PHYSICAL_MEASURED,
        RESPONSE_VERIFIED_MEASURED_RESPONSE,
        ResponsePolicy,
        W06_LAYER_VERSION,
        ack_to_applied,
        audit_timeline,
        command_to_ack,
        command_to_response,
        deduplicate_events,
        event_counts,
        event_manifest,
        event_timeline_csv,
        events_from_capture,
        load_a_command_events,
        load_event_fixture,
        order_timeline,
        response_summary_csv,
    )
except ModuleNotFoundError:  # direct checkout invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml import (
        SourceRefusal,
        __version__ as PACKAGE_VERSION,
        evaluate_admission,
        load_capture,
        summarize_readiness,
    )
    from coldguard_ml import timing_alignment as _timing
    from coldguard_ml.timing_alignment import (
        DEFAULT_ELECTRICAL_POLICY,
        DEFAULT_THERMAL_POLICY,
        EVENT_APPLIED_STATE,
        EVENT_COMMAND_CREATED_OR_PUBLISHED,
        EVENT_DEVICE_ACK,
        EVENT_DOOR_TRANSITION,
        EVENT_ELECTRICAL_RESPONSE,
        EVENT_TELEMETRY_SAMPLE,
        EVENT_THERMAL_RESPONSE,
        PROVENANCE_PHYSICAL_MEASURED,
        RESPONSE_VERIFIED_MEASURED_RESPONSE,
        ResponsePolicy,
        W06_LAYER_VERSION,
        ack_to_applied,
        audit_timeline,
        command_to_ack,
        command_to_response,
        deduplicate_events,
        event_counts,
        event_manifest,
        event_timeline_csv,
        events_from_capture,
        load_a_command_events,
        load_event_fixture,
        order_timeline,
        response_summary_csv,
    )

REPORT_SCHEMA = "coldguard-w06-timing-report-v1"
_UNAVAILABLE = "NOT_ESTIMABLE"


def _repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return Path.cwd()


def _safe_path(path: str, root: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        root_candidate = root / candidate
        if root_candidate.exists():
            return candidate.as_posix()
        resolved = candidate.resolve()
    else:
        resolved = candidate.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.name


def _command_path(path: str, root: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return Path(os.path.relpath(candidate.resolve(), root / "ml")).as_posix()
    except ValueError:
        return candidate.name


def _analysis_code_sha256() -> str:
    package_dir = Path(_timing.__file__).resolve().parent
    paths = {
        Path(__file__).resolve(),
        package_dir / "timing_alignment.py",
        package_dir / "intake.py",
        package_dir / "real_data_qa.py",
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


def _number(value: float | None, digits: int = 6) -> str:
    if value is None:
        return _UNAVAILABLE
    return f"{value:.{digits}f}"


def _md_cell(value: Any) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(_md_cell(h) for h in headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def _policies(args: argparse.Namespace) -> tuple[ResponsePolicy, ResponsePolicy]:
    electrical = ResponsePolicy(
        name="electrical-current-step-v1",
        channel="cooling_current_a",
        physical_role="COOLING_BRANCH_ELECTRICAL",
        quality_key="electrical",
        expected_direction="UP",
        min_change=args.electrical_min_change_a,
        baseline_window_s=args.baseline_window_s,
        max_window_s=args.electrical_max_window_s,
        sustained_observations=args.sustained_observations,
        max_gap_s=args.max_gap_s,
        max_uncertainty_s=args.max_uncertainty_s,
    )
    thermal = ResponsePolicy(
        name="chamber-air-temperature-step-v1",
        channel="chamber_air_mean_c",
        physical_role="CHAMBER_AIR",
        quality_key="thermal",
        expected_direction="DOWN",
        min_change=args.thermal_min_change_c,
        baseline_window_s=args.baseline_window_s,
        max_window_s=args.thermal_max_window_s,
        sustained_observations=args.sustained_observations,
        max_gap_s=args.max_gap_s,
        max_uncertainty_s=args.max_uncertainty_s,
    )
    return electrical, thermal


def _run_index_metadata(path: str | None, root: Path) -> dict[str, Any] | None:
    if path is None:
        return None
    index_path = Path(path)
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    return {
        "path": _safe_path(path, root),
        "sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "index_version": payload.get("index_version"),
        "runs_total": len(payload.get("runs") or []),
        "valid_s1_run_ids_for_member_b": list(
            payload.get("valid_s1_run_ids_for_member_b") or []
        ),
        "blocked_run_ids": list(payload.get("blocked_run_ids") or []),
    }


def _source_inventory(
    captures, command_logs, fixtures, root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sources: list[dict[str, Any]] = []
    for capture in captures:
        admission = evaluate_admission(capture)
        sources.append(
            {
                "kind": "CAPTURE",
                "path": capture.source.path,
                "sha256": capture.source.sha256,
                "format": capture.source.format,
                "schema_namespace": capture.source.schema_namespace,
                "provenance": capture.source.provenance,
                "is_physical_measurement": capture.source.is_physical_measurement,
                "device_id": capture.run.device_id,
                "boot_id": capture.run.boot_id,
                "run_id": capture.run.run_id,
                "run_id_status": capture.run.run_id_status,
                "time_domain": capture.time.domain,
                "clock_sync": capture.time.clock_sync,
                "admission_status": admission.status.value,
                "predictive_dataset_readiness": (
                    admission.predictive_dataset_readiness
                ),
                "rows": len(capture.rows),
            }
        )
    for load, path, provenance in command_logs:
        sources.append(
            {
                "kind": "A_COMMAND_LOG",
                "path": _safe_path(path, root),
                "sha256": (
                    load.events[0].source_sha256
                    if load.events
                    else hashlib.sha256(Path(path).read_bytes()).hexdigest()
                ),
                "format": "coldguard.command-ack-serial/v1",
                "schema_namespace": "coldguard.command-ack-serial/v1",
                "provenance": provenance,
                "is_physical_measurement": False,
                "device_id": None,
                "boot_id": None,
                "run_id": None,
                "run_id_status": "NOT_CARRIED",
                "time_domain": "DEVICE_BOOT_UPTIME",
                "clock_sync": "PER_ACK_FIELD",
                "admission_status": "EXCLUDED_OR_BLOCKED",
                "predictive_dataset_readiness": "NOT_READY",
                "rows": len(load.events),
                "ignored_telemetry_lines": load.ignored_telemetry_lines,
                "source_line_count": load.source_line_count,
            }
        )
    for events, path in fixtures:
        sources.append(
            {
                "kind": "W06_EVENT_FIXTURE",
                "path": _safe_path(path, root),
                "sha256": (
                    events[0].source_sha256
                    if events
                    else hashlib.sha256(Path(path).read_bytes()).hexdigest()
                ),
                "format": _timing.W06_EVENT_FIXTURE_SCHEMA,
                "schema_namespace": "coldguard.w06-event-fixture/v1",
                "provenance": "SYNTHETIC_FIXTURE",
                "is_physical_measurement": False,
                "device_id": None,
                "boot_id": None,
                "run_id": None,
                "run_id_status": "NOT_CARRIED",
                "time_domain": "DECLARED_PER_EVENT",
                "clock_sync": "SYNTHETIC_EXACT",
                "admission_status": "EXCLUDED_OR_BLOCKED",
                "predictive_dataset_readiness": "NOT_READY",
                "rows": len(events),
            }
        )
    return sources, [source["path"] for source in sources]


def _safe_events(events, root: Path):
    return [
        replace(event, source_path=_safe_path(event.source_path, root))
        for event in events
    ]


def _responses_for_source(
    events,
    electrical_policy: ResponsePolicy,
    thermal_policy: ResponsePolicy,
):
    from coldguard_ml.timing_alignment import (
        EVENT_COMMAND_CREATED_OR_PUBLISHED,
        EVENT_DEVICE_ACK,
        EVENT_TELEMETRY_SAMPLE,
        RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR,
        analyze_response,
    )

    commands = [
        event
        for event in events
        if event.event_type == EVENT_COMMAND_CREATED_OR_PUBLISHED
    ]
    acks = [event for event in events if event.event_type == EVENT_DEVICE_ACK]
    applied = [event for event in events if event.event_type == EVENT_APPLIED_STATE]
    telemetry = [
        event for event in events if event.event_type == EVENT_TELEMETRY_SAMPLE
    ]
    responses = list(command_to_ack(commands, acks))
    responses.extend(ack_to_applied(acks, applied))
    if not acks:
        responses.append(_missing_anchor_response("ACK_TO_APPLIED_STATE"))
    if not commands:
        if not acks:
            responses.append(_missing_anchor_response("COMMAND_TO_ACK"))
        responses.extend(
            _missing_anchor_response(relationship)
            for relationship in ("COMMAND_TO_ELECTRICAL", "COMMAND_TO_THERMAL")
        )
    else:
        responses.extend(
            command_to_response(
                commands,
                applied,
                telemetry,
                electrical_policy,
                relationship="COMMAND_TO_ELECTRICAL",
            )
        )
        responses.extend(
            command_to_response(
                commands,
                applied,
                telemetry,
                thermal_policy,
                relationship="COMMAND_TO_THERMAL",
            )
        )
    for anchor in sorted(applied, key=lambda event: event.event_id):
        applied_to = anchor.field("applied_to") or anchor.field("applied_cooling")
        electrical_direction = "UP" if applied_to == "ON" else "DOWN"
        thermal_direction = "DOWN" if applied_to == "ON" else "UP"
        responses.append(
            analyze_response(
                "APPLIED_TO_ELECTRICAL",
                anchor,
                telemetry,
                replace(electrical_policy, expected_direction=electrical_direction),
            )
        )
        responses.append(
            analyze_response(
                "APPLIED_TO_THERMAL",
                anchor,
                telemetry,
                replace(thermal_policy, expected_direction=thermal_direction),
            )
        )
    if not applied:
        responses.extend(
            _missing_anchor_response(relationship)
            for relationship in ("APPLIED_TO_ELECTRICAL", "APPLIED_TO_THERMAL")
        )
    source_path = events[0].source_path if events else None
    return [replace(result, source_path=source_path) for result in responses]


def _missing_anchor_response(relationship: str):
    from coldguard_ml.timing_alignment import (
        DEFAULT_ELECTRICAL_POLICY,
        RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR,
        ResponseResult,
    )

    return ResponseResult(
        relationship=relationship,
        state=RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR,
        command_id=None,
        anchor_event_id=None,
        latency_s=None,
        uncertainty_s=None,
        evidence_class="NOT_ESTIMABLE",
        independent_application=None,
        sample_count=0,
        baseline_median=None,
        policy_name=DEFAULT_ELECTRICAL_POLICY.name,
        reason_codes=("NO_ANCHOR_EVENT",),
    )


def _group_by_source(events):
    groups: dict[tuple[str, str], list[Any]] = {}
    for event in events:
        groups.setdefault((event.source_path, event.source_sha256), []).append(event)
    return groups


def _real_command_lifecycle_status(events, responses) -> str:
    physical_commands = [
        event
        for event in events
        if event.event_type == EVENT_COMMAND_CREATED_OR_PUBLISHED
        and event.provenance == PROVENANCE_PHYSICAL_MEASURED
    ]
    physical_acks = [
        event
        for event in events
        if event.event_type == EVENT_DEVICE_ACK
        and event.provenance == PROVENANCE_PHYSICAL_MEASURED
    ]
    if not physical_commands and not physical_acks:
        return "ABSENT"
    qualified = any(
        result.state == RESPONSE_VERIFIED_MEASURED_RESPONSE
        for result in responses
    )
    return "PRESENT_QUALIFIED" if qualified and physical_commands else "PARTIAL"


def _render_markdown(
    *,
    sources,
    events,
    dedup,
    ordering,
    audit,
    responses,
    counts,
    policies,
    revision,
    code_sha256,
    command,
    statuses,
    run_index,
) -> str:
    lines = [
        "# ColdGuard W06 — Event Alignment and Timing Audit",
        "",
        "Provenance-aware event alignment, clock/sequence diagnostics, bounded "
        "response detection and deterministic duplicate handling. No model "
        "training, no W07 plant EDA, no W08 Gate B, no W12 evaluation.",
        "",
        "## 0. Scientific separation",
        "",
        _md_table(
            ["Status", "Value", "Meaning"],
            [
                (
                    "W06 SOFTWARE VERIFICATION",
                    statuses["w06_software_verification"],
                    "CLI completed and artifacts are deterministic; pytest is the stronger evidence",
                ),
                (
                    "REAL COMMAND-LIFECYCLE EVIDENCE",
                    statuses["real_command_lifecycle_evidence"],
                    "no physical command/ACK round trip exists in the committed evidence",
                ),
                (
                    "PHYSICAL DATA ELIGIBILITY",
                    statuses["physical_data_eligibility"],
                    "authoritative W04 admission over the analyzed captures",
                ),
                (
                    "REAL AIW",
                    statuses["real_aiw"],
                    "W06 supplies candidate inputs only; compute_aiw remains the gate",
                ),
            ],
        ),
        "",
        "A software-green W06 with absent real command evidence is an acceptable "
        "engineering result. It is not a physical verification claim.",
        "",
        "## 1. Provenance",
        "",
        _md_table(
            ["Field", "Value"],
            [
                ("Report schema", REPORT_SCHEMA),
                ("Package version", PACKAGE_VERSION),
                ("W06 layer version", W06_LAYER_VERSION),
                ("Analysis code SHA-256", f"`{code_sha256}`"),
                ("Repository revision", revision),
                ("A run index", run_index["path"] if run_index else "NONE"),
                ("Generation command", f"`{command}`"),
            ],
        ),
        "",
        "## 2. Source inventory",
        "",
        _md_table(
            [
                "Kind",
                "Path",
                "SHA-256",
                "Namespace",
                "Provenance",
                "Time domain",
                "Clock sync",
                "Admission",
                "Rows/events",
            ],
            [
                (
                    source["kind"],
                    source["path"],
                    source["sha256"],
                    source["schema_namespace"],
                    source["provenance"],
                    source["time_domain"],
                    source["clock_sync"],
                    source["admission_status"],
                    source["rows"],
                )
                for source in sources
            ],
        ),
        "",
        "## 3. Source-contract ledger",
        "",
        _md_table(
            [
                "Source field",
                "Namespace/version",
                "Time domain",
                "Identity",
                "Quality",
                "Authority",
                "W06 use",
            ],
            [
                (
                    row["source_field"],
                    row["namespace"],
                    row["time_domain"],
                    row["identity"],
                    row["quality"],
                    row["authority"],
                    row["w06_use"],
                )
                for row in _timing.source_contract_ledger()
            ],
        ),
        "",
        "Command-log inputs: "
        f"{sum(source.get('ignored_telemetry_lines', 0) for source in sources)} "
        "embedded `#CG TELEM` line(s) were ignored; serial telemetry is never "
        "fed through the C JSON parser.",
        "",
        "## 4. Event counts (canonical, after duplicate collapse)",
        "",
        _md_table(
            ["Count", "Value"],
            [
                ("Telemetry events", counts["telemetry_events"]),
                ("Door transitions", counts["door_transitions"]),
                ("Command events", counts["command_events"]),
                ("ACK events", counts["ack_events"]),
                ("Applied-state observations", counts["applied_state_observations"]),
                ("Electrical response events", counts["electrical_response_events"]),
                ("Thermal response events", counts["thermal_response_events"]),
                ("Electrical responses (numeric)", counts["electrical_responses"]),
                ("Thermal responses (numeric)", counts["thermal_responses"]),
                (
                    "Verified electrical responses",
                    counts["electrical_verified_responses"],
                ),
                (
                    "Verified thermal responses",
                    counts["thermal_verified_responses"],
                ),
                ("Duplicate deliveries", counts["duplicate_deliveries"]),
                ("Contradictory identities", counts["contradictory_identities"]),
                ("Contradictory events", counts["contradictory_events"]),
                ("Missing-identity events", counts["missing_identity_events"]),
                ("Unalignable events", counts["unalignable_events"]),
                (
                    "Real measured response delays",
                    counts["real_measured_response_delays"],
                ),
                (
                    "Synthetic example delays",
                    counts["synthetic_example_delays"],
                ),
                ("Not-estimable responses", counts["not_estimable_responses"]),
                ("Censored responses", counts["censored_responses"]),
                ("Contradictory responses", counts["contradictory_responses"]),
            ],
        ),
        "",
        "Per-source counts:",
        "",
        _md_table(
            [
                "Source",
                "Telemetry",
                "Door",
                "Command",
                "ACK",
                "Applied",
                "Electrical",
                "Thermal",
            ],
            [
                (
                    source["path"],
                    sum(
                        1
                        for event in events
                        if event.source_path == source["path"]
                        and event.event_type == EVENT_TELEMETRY_SAMPLE
                    ),
                    sum(
                        1
                        for event in events
                        if event.source_path == source["path"]
                        and event.event_type == EVENT_DOOR_TRANSITION
                    ),
                    sum(
                        1
                        for event in events
                        if event.source_path == source["path"]
                        and event.event_type == EVENT_COMMAND_CREATED_OR_PUBLISHED
                    ),
                    sum(
                        1
                        for event in events
                        if event.source_path == source["path"]
                        and event.event_type == EVENT_DEVICE_ACK
                    ),
                    sum(
                        1
                        for event in events
                        if event.source_path == source["path"]
                        and event.event_type == EVENT_APPLIED_STATE
                    ),
                    sum(
                        1
                        for event in events
                        if event.source_path == source["path"]
                        and event.event_type == EVENT_ELECTRICAL_RESPONSE
                    ),
                    sum(
                        1
                        for event in events
                        if event.source_path == source["path"]
                        and event.event_type == EVENT_THERMAL_RESPONSE
                    ),
                )
                for source in sources
            ],
        ),
        "",
        "## 5. Ordering and clock/sequence diagnostics",
        "",
        _md_table(
            [
                "Clock domain",
                "Device",
                "Boot",
                "Events",
                "First time (s)",
                "Last time (s)",
                "Median interval (s)",
                "P95 interval (s)",
                "Monotonic",
                "Seq gaps",
                "Seq dups",
                "Reversals",
                "Uptime resets",
                "Receive conflicts",
                "Max uncertainty (s)",
                "Reason codes",
            ],
            [
                (
                    domain.clock_domain,
                    domain.device_id or "NOT_CARRIED",
                    domain.boot_id or "NOT_CARRIED",
                    domain.event_count,
                    _number(domain.first_time, 3),
                    _number(domain.last_time, 3),
                    _number(domain.median_interval_s),
                    _number(domain.p95_interval_s),
                    domain.monotonic,
                    domain.sequence_gaps,
                    domain.sequence_duplicates,
                    domain.timestamp_reversals,
                    domain.uptime_resets,
                    domain.capture_receive_conflicts,
                    _number(domain.max_uncertainty_s),
                    ", ".join(domain.reason_codes) or "NONE",
                )
                for domain in audit.domains
            ],
        ),
        "",
        _md_table(
            ["Ordered session", "Status", "Reason codes"],
            [
                (
                    f"{item.clock_domain} / {item.device_id or 'NO_DEVICE_ID'} / "
                    f"{item.boot_id or 'NO_BOOT_ID'}",
                    item.status,
                    ", ".join(item.reason_codes) or "NONE",
                )
                for item in ordering
            ],
        ),
        "",
        "Uptime is boot-scoped. No host capture time is promoted to device event "
        "time, no backend receive time is a source acquisition time, and no "
        "cross-boot uptime subtraction is performed.",
        "",
        "## 6. Duplicate and idempotency handling",
        "",
        _md_table(
            ["Field", "Value"],
            [
                ("Canonical events", len(dedup.canonical_events)),
                ("Contradictory events", len(dedup.contradictory_events)),
                ("Missing-identity events", len(dedup.missing_identity_events)),
                ("Identical duplicate deliveries", dedup.duplicate_deliveries),
                ("DUPLICATE_CANONICAL replies", dedup.duplicate_canonical_acks),
                (
                    "Commands with multiple ACKs and no DUPLICATE_CANONICAL",
                    dedup.multiple_ack_without_canonical,
                ),
                ("Reboot identity resets", dedup.reboot_identity_resets),
                (
                    "New command IDs with the same requested action",
                    dedup.new_commands_same_action,
                ),
                ("Reason codes", ", ".join(dedup.reason_codes) or "NONE"),
            ],
        ),
        "",
        "Identical repeated delivery collapses to one logical event while retaining "
        "`delivery_count`. Contradictory payloads sharing one identity are retained "
        "and reported, never resolved by choosing a favorable payload. A "
        "DUPLICATE_CANONICAL reply is not another independent application, and a "
        "cross-boot uptime match is never duplicate proof.",
        "",
        "## 7. Command and response results",
        "",
        _md_table(
            [
                "Source",
                "Relationship",
                "Command",
                "State",
                "Latency (s)",
                "Uncertainty (s)",
                "Evidence class",
                "Samples",
                "Baseline",
                "Policy",
                "Reason codes",
            ],
            [
                (
                    result.source_path or "NOT_APPLICABLE",
                    result.relationship,
                    result.command_id or "NOT_APPLICABLE",
                    result.state,
                    _number(result.latency_s),
                    _number(result.uncertainty_s),
                    result.evidence_class,
                    result.sample_count,
                    _number(result.baseline_median),
                    result.policy_name,
                    ", ".join(result.reason_codes) or "NONE",
                )
                for result in responses
            ],
        ),
        "",
        "A numeric latency is emitted only for synthetic unit-test controls or "
        "for physical evidence whose anchor, channel quality and clock evidence "
        "are qualified. `VERIFIED_MEASURED_RESPONSE` is the only state that may be "
        "read as a measured physical response. `NOT_ESTIMABLE_*` and `CENSORED` "
        "are not zero-second responses.",
        "",
        "## 8. Scientific limits",
        "",
        "- The A W06 command fixtures are host-generated/synthetic: no transport, "
        "no backend issuer and no energized round trip exist.",
        "- An ACCEPTED ACK is protocol evidence, not applied cooling and not "
        "electrical or thermal response.",
        "- Device uptime is boot-scoped; no absolute UTC epoch is carried by the "
        "A serial command line.",
        "- Numeric PZEM power under UNKNOWN quality is never a certified "
        "electrical response; the TEC hot side is never chamber-air response.",
        "- The real A W09 capture has no command/ACK lines; its applied-state "
        "observations are device-reported and not command-linked.",
        "- W06 does not compute AIW. `compute_aiw` in the W04 contract remains "
        "the gate for a complete, non-overlapping multi-component chain.",
        "- Response thresholds are configurable analysis floors recorded in the "
        "manifest, not frozen hardware contract thresholds.",
        "",
        "## 9. Reproduction",
        "",
        "```bash",
        "cd ml",
        f"uv run --locked --python 3.12 --extra test python scripts/{command}",
        "```",
        "",
        "Repeated execution on the same inputs and configuration produces "
        "identical artifacts. The report contains no runtime timestamp and no "
        "local absolute path.",
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-alignment-W06.py",
        description=(
            "ColdGuard W06 provenance-aware event alignment, clock/sequence "
            "diagnostics, response-window helpers and duplicate-event handling."
        ),
    )
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--a-run-index", default=None)
    parser.add_argument("--a-command-log", action="append", default=[])
    parser.add_argument(
        "--a-command-provenance",
        choices=("HOST_GENERATED_SYNTHETIC", "UNVERIFIED"),
        default="UNVERIFIED",
        help="explicit provenance label for A's host-generated command logs",
    )
    parser.add_argument("--event-fixture", action="append", default=[])
    parser.add_argument("--out", default="reports/W06")
    parser.add_argument("--baseline-window-s", type=float, default=10.0)
    parser.add_argument("--electrical-max-window-s", type=float, default=60.0)
    parser.add_argument("--thermal-max-window-s", type=float, default=300.0)
    parser.add_argument("--max-gap-s", type=float, default=5.0)
    parser.add_argument("--sustained-observations", type=int, default=3)
    parser.add_argument(
        "--electrical-min-change-a",
        type=float,
        default=0.05,
        help="named analysis floor; not a frozen hardware threshold",
    )
    parser.add_argument(
        "--thermal-min-change-c",
        type=float,
        default=0.25,
        help="named analysis floor; not a frozen hardware threshold",
    )
    parser.add_argument("--max-uncertainty-s", type=float, default=10.0)
    parser.add_argument("--repository-revision", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    root = _repo_root()
    if not (args.source or args.a_command_log or args.event_fixture):
        print(
            "CONFIGURATION_ERROR: supply at least one --source, "
            "--a-command-log or --event-fixture",
            file=sys.stderr,
        )
        return 1
    try:
        electrical_policy, thermal_policy = _policies(args)
    except ValueError as exc:
        print(f"CONFIGURATION_ERROR: {exc}", file=sys.stderr)
        return 1

    captures = []
    refusals: list[str] = []
    for source in args.source:
        try:
            captures.append(load_capture(source, a_run_index=args.a_run_index))
        except SourceRefusal as exc:
            refusals.append(f"{_safe_path(source, root)}: {exc.code}: {exc.detail}")
        except Exception as exc:
            refusals.append(
                f"{_safe_path(source, root)}: {type(exc).__name__}: {exc}"
            )
    command_logs = []
    for path in args.a_command_log:
        try:
            command_logs.append(
                (
                    load_a_command_events(
                        path, provenance=args.a_command_provenance
                    ),
                    path,
                    args.a_command_provenance,
                )
            )
        except _timing.TimingAlignmentError as exc:
            refusals.append(f"{_safe_path(path, root)}: {exc.code}: {exc.detail}")
    fixtures = []
    for path in args.event_fixture:
        try:
            fixtures.append((load_event_fixture(path), path))
        except _timing.TimingAlignmentError as exc:
            refusals.append(f"{_safe_path(path, root)}: {exc.code}: {exc.detail}")
    if refusals:
        for refusal in refusals:
            print(f"REFUSED: {refusal}", file=sys.stderr)
        return 2
    if not captures and not command_logs and not fixtures:
        print("REFUSED: no analyzable inputs", file=sys.stderr)
        return 2

    raw_events = []
    for capture in captures:
        raw_events.extend(events_from_capture(capture))
    for load, _path, _provenance in command_logs:
        raw_events.extend(load.events)
    for events, _path in fixtures:
        raw_events.extend(events)
    raw_events = _safe_events(raw_events, root)
    dedup = deduplicate_events(raw_events)
    events = sorted(
        (
            list(dedup.canonical_events)
            + list(dedup.contradictory_events)
            + list(dedup.missing_identity_events)
        ),
        key=lambda event: (
            event.source_path,
            str(event.device_id),
            str(event.boot_id),
            event.clock_domain,
            event.device_uptime_ms if event.device_uptime_ms is not None else -1,
            event.event_time_utc or "",
            event.seq if event.seq is not None else -1,
            event.event_type,
            event.event_id,
        ),
    )
    analysis_events = list(dedup.canonical_events)
    audit = audit_timeline(events)
    ordering = []
    session_keys = sorted(
        {
            (
                event.source_path,
                event.clock_domain,
                event.device_id,
                event.boot_id,
            )
            for event in analysis_events
            if event.clock_domain
            in ("DEVICE_BOOT_UPTIME", "DEVICE_EVENT_UTC")
        },
        key=lambda item: str(item),
    )
    for source_path, clock_domain, device_id, boot_id in session_keys:
        session_events = [
            event
            for event in analysis_events
            if event.source_path == source_path
            and event.clock_domain == clock_domain
            and event.device_id == device_id
            and event.boot_id == boot_id
        ]
        ordering.append(order_timeline(session_events))
    responses = []
    for _key, source_events in sorted(
        _group_by_source(analysis_events).items(), key=lambda item: str(item[0])
    ):
        responses.extend(
            _responses_for_source(
                source_events, electrical_policy, thermal_policy
            )
        )
    responses = tuple(
        sorted(
            responses,
            key=lambda result: (
                result.source_path or "",
                result.relationship,
                result.command_id or "",
                result.anchor_event_id or "",
                result.state,
            ),
        )
    )
    sources, _paths = _source_inventory(captures, command_logs, fixtures, root)
    counts = event_counts(events, responses, dedup, ordering, audit)
    readiness = summarize_readiness(
        [evaluate_admission(capture) for capture in captures]
    )
    physical_eligibility = (
        readiness.predictive_dataset_readiness if captures else "NOT_VERIFIED"
    )
    statuses = {
        "w06_software_verification": "PASS",
        "real_command_lifecycle_evidence": _real_command_lifecycle_status(
            events, responses
        ),
        "physical_data_eligibility": physical_eligibility,
        "real_aiw": "NOT_ESTIMABLE",
    }
    try:
        run_index = _run_index_metadata(args.a_run_index, root)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"REFUSED: run index: {exc}", file=sys.stderr)
        return 2
    revision = args.repository_revision or _repository_revision(root)
    command = _command_line(args, root)
    code_sha256 = _analysis_code_sha256()

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown = _render_markdown(
        sources=sources,
        events=events,
        dedup=dedup,
        ordering=ordering,
        audit=audit,
        responses=responses,
        counts=counts,
        policies=(electrical_policy, thermal_policy),
        revision=revision,
        code_sha256=code_sha256,
        command=command,
        statuses=statuses,
        run_index=run_index,
    )
    (output_dir / "timing-audit-W06.md").write_text(
        markdown, encoding="utf-8", newline="\n"
    )
    (output_dir / "event-timeline-W06.csv").write_text(
        event_timeline_csv(events), encoding="utf-8", newline="\n"
    )
    (output_dir / "response-summary-W06.csv").write_text(
        response_summary_csv(responses), encoding="utf-8", newline="\n"
    )
    manifest = event_manifest(
        events,
        responses,
        dedup,
        ordering,
        audit,
        command=command,
        repository_revision=revision,
        analysis_code_sha256=code_sha256,
        sources=sources,
        configs=(electrical_policy, thermal_policy),
        statuses=statuses,
        run_index=run_index,
    )
    (output_dir / "timing-manifest-W06.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        "W06 ALIGNMENT COMPLETE: "
        f"{len(sources)} source(s), {len(events)} event(s), "
        f"command lifecycle {statuses['real_command_lifecycle_evidence']}, "
        f"physical eligibility {physical_eligibility}; artifacts in {args.out}"
    )
    return 0


def _command_line(args: argparse.Namespace, root: Path) -> str:
    parts = ["event-alignment-W06.py"]
    for source in args.source:
        parts.extend(["--source", _command_path(source, root)])
    if args.a_run_index:
        parts.extend(["--a-run-index", _command_path(args.a_run_index, root)])
    for path in args.a_command_log:
        parts.extend(["--a-command-log", _command_path(path, root)])
    parts.extend(["--a-command-provenance", args.a_command_provenance])
    for path in args.event_fixture:
        parts.extend(["--event-fixture", _command_path(path, root)])
    parts.extend(["--out", _command_path(args.out, root)])
    parts.extend(["--baseline-window-s", str(args.baseline_window_s)])
    parts.extend(["--electrical-max-window-s", str(args.electrical_max_window_s)])
    parts.extend(["--thermal-max-window-s", str(args.thermal_max_window_s)])
    parts.extend(["--max-gap-s", str(args.max_gap_s)])
    parts.extend(["--sustained-observations", str(args.sustained_observations)])
    parts.extend(["--electrical-min-change-a", str(args.electrical_min_change_a)])
    parts.extend(["--thermal-min-change-c", str(args.thermal_min_change_c)])
    parts.extend(["--max-uncertainty-s", str(args.max_uncertainty_s)])
    if args.repository_revision:
        parts.extend(["--repository-revision", args.repository_revision])
    return " ".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
