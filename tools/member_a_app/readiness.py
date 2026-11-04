"""Execution-readiness gate for the 114 canonical Member A workflows.

This is not an acceptance verdict. It answers one operational question before
a timed capture is launched: what blocks this requirement right now?

The classification is derived from the existing registry fields
(handler/mode/safety/params/prerequisites), the recorded outcomes, and a live
read-only capability snapshot. No requirement description is rewritten here.
"""

from __future__ import annotations

import dataclasses
import pathlib
import time
from typing import Any, Iterable, Mapping

from . import protocol
from .device import DeviceLink
from .model import Outcome, TestDefinition, TestResult

READY_NOW = "READY_NOW"
NEEDS_PSU = "NEEDS_PSU"
NEEDS_OPERATOR = "NEEDS_OPERATOR"
NEEDS_FIRMWARE_CAPABILITY = "NEEDS_FIRMWARE_CAPABILITY"
NEEDS_EXISTING_PREREQUISITE = "NEEDS_EXISTING_PREREQUISITE"
NEEDS_EXTERNAL_TEAM_INPUT = "NEEDS_EXTERNAL_TEAM_INPUT"
HARDWARE_NONCOMPLIANT = "HARDWARE_NONCOMPLIANT"

STATES = (
    READY_NOW,
    NEEDS_PSU,
    NEEDS_OPERATOR,
    NEEDS_FIRMWARE_CAPABILITY,
    NEEDS_EXISTING_PREREQUISITE,
    NEEDS_EXTERNAL_TEAM_INPUT,
    HARDWARE_NONCOMPLIANT,
)

COMMAND_HANDLERS = {
    "command_parser", "command_expiry", "actuation_trace", "hil_smoke",
    "run_checklist", "degraded_sensor", "degraded_pzem", "soak", "run_series",
}
OPERATOR_HANDLERS = {
    "documentary", "numeric", "photo_inventory", "token_scan", "bom_csv",
    "max3485", "fuse", "fuse_final", "decision", "composite", "handover",
    "evidence_audit", "evidence_gap_list", "rerun_evidence",
    "invalidation_log", "protocol_freeze", "rehearsal", "campaign_manifest",
    "pzem_reference", "polarity", "reset_series", "run_series",
}
PSU_HANDLERS = {
    "pzem_range", "pzem_link", "fuse", "fuse_final", "pzem_reference",
    "hil_smoke",
}
TELEMETRY_HANDLERS = {
    "telemetry", "applied_state", "sensor_enumeration", "code_audit",
    "reset_series", "run_series", "actuation_trace", "soak", "degraded_sensor",
    "degraded_pzem", "hil_smoke", "pzem_range", "pzem_link",
}
HARDWARE_FAILURE_TOKENS = ("UNAPPROVED_SUBSTITUTION", "vcc_3v3_ABOVE_MAXIMUM")


@dataclasses.dataclass
class CapabilitySnapshot:
    connected: bool = False
    firmware_kind: str | None = None
    output_stage: str | None = None
    command_transport: bool | None = None
    psu_present: bool | None = None
    door_known: bool | None = None
    limits: dict[str, float] = dataclasses.field(default_factory=dict)
    frame: protocol.TelemetryFrame | None = None


@dataclasses.dataclass(frozen=True)
class ReadinessItem:
    test_id: str
    week: int
    title: str
    state: str
    reasons: tuple[str, ...]
    prerequisites: tuple[str, ...]
    prior: str
    handler: str
    mode: str
    safety: str

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _outcome(value: Any) -> str:
    return value.value if isinstance(value, Outcome) else str(value or "NOT_RUN")


def _limits_from_events(events: Iterable[protocol.ParsedLine]) -> dict[str, float]:
    limits: dict[str, float] = {}
    for event in events:
        if event.kind not in {"TEC_LIMIT", "TEC_LIMITS"}:
            continue
        name = event.kv.get("name")
        value = event.kv.get("value")
        if not name or value in {None, "", "nan", "UNRESOLVED"}:
            continue
        try:
            limits[str(name)] = float(value)
        except (TypeError, ValueError):
            continue
    return limits


def build_snapshot(link: DeviceLink | None, probe_commands: bool = True,
                   wait_s: float = 4.0) -> CapabilitySnapshot:
    """Read-only capability probe. Sends only STATUS, never ARM/START."""
    snap = CapabilitySnapshot()
    if link is None:
        return snap
    deadline = time.monotonic() + max(0.5, wait_s)
    while time.monotonic() < deadline and link.latest_frame() is None:
        time.sleep(0.1)
    frame = link.latest_frame()
    if frame is None:
        return snap
    snap.connected = True
    snap.frame = frame
    snap.firmware_kind = link.snapshot.firmware_kind
    snap.output_stage = frame.output_stage
    snap.door_known = frame.door_open is not None
    snap.psu_present = (frame.voltage_v is not None
                        and 11.5 <= float(frame.voltage_v) <= 12.5)
    events, _ = link.events_since(0)
    snap.limits = _limits_from_events(events)
    if frame.is_h8:
        snap.command_transport = False
        return snap
    if probe_commands:
        cursor = link.event_cursor()
        link.send(b"STATUS\n", "readiness STATUS probe (non-actuating)")
        event = link.wait_for_event(
            lambda item: item.kind == "TEC" and item.kv.get("event") == "STATUS",
            2.5, cursor)
        snap.command_transport = event is not None
    return snap


def _prerequisite_ids(definition: TestDefinition) -> tuple[str, ...]:
    ids = list(definition.prerequisites)
    if definition.handler in {"derived", "composite", "evidence_audit",
                              "dataset_support"}:
        ids.extend(str(item) for item in definition.params.get("requirements", []))
    if definition.handler == "derived":
        ids.extend(str(item) for item in definition.params.get("requirements", []))
    # Preserve order, remove duplicates.
    return tuple(dict.fromkeys(ids))


def _duration_s(definition: TestDefinition, requires_actuation: bool) -> float | None:
    value = definition.params.get("duration_s", definition.duration_s)
    if value is None:
        return None
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    if requires_actuation and definition.handler == "run_series":
        duration += 5.0  # run_series sends START duration + 5 s
    return duration


def evaluate(definitions: Iterable[TestDefinition],
             results: Mapping[str, TestResult],
             snapshot: CapabilitySnapshot | None,
             max_capture_s: float = 1900.0) -> list[ReadinessItem]:
    snap = snapshot or CapabilitySnapshot()
    out: list[ReadinessItem] = []
    for definition in sorted(definitions, key=lambda item: item.test_id):
        prior = results.get(definition.test_id)
        prior_state = _outcome(prior.outcome) if prior is not None else "NOT_RUN"
        reasons: list[str] = []
        if prior is not None and prior.outcome is Outcome.PASS:
            out.append(ReadinessItem(
                definition.test_id, definition.week, definition.title, READY_NOW,
                ("ALREADY_PASS",), _prerequisite_ids(definition), prior_state,
                definition.handler, definition.mode.value, definition.safety.value))
            continue

        hardware = (prior is not None and prior.outcome is Outcome.FAIL
                    and any(token in (prior.failure_reason or "")
                            for token in HARDWARE_FAILURE_TOKENS))
        team = (definition.mode.value == "TEAM_DEPENDENCY"
                or definition.handler in {"team_evidence", "unsupported"})
        if team:
            reasons.append("EXTERNAL_TEAM_DEPENDENCY")

        prereqs = _prerequisite_ids(definition)
        missing = [item for item in prereqs
                   if item not in results or results[item].outcome is not Outcome.PASS]
        if missing:
            reasons.extend(f"PREREQUISITE_NOT_PASS:{item}" for item in missing)

        scenario = str(definition.params.get("scenario", "")).upper()
        requires_actuation = bool(definition.params.get("requires_actuation")) or \
            definition.handler in {"actuation_trace", "hil_smoke"} or \
            (definition.handler == "run_series" and scenario == "COOLING_STEP") or \
            definition.test_id in {"A-W04-05", "A-W08-03"}
        requires_commands = definition.handler in COMMAND_HANDLERS
        if definition.handler == "run_series":
            requires_commands = scenario in {"WARMUP", "COOLING_STEP", "S2"} or requires_actuation
        requires_telemetry = definition.handler in TELEMETRY_HANDLERS or requires_actuation
        requires_psu = requires_actuation or definition.handler in PSU_HANDLERS or \
            (definition.handler == "telemetry"
             and definition.params.get("analysis") == "electrical") or \
            definition.test_id in {"A-W05-01", "A-W05-03", "A-W05-04"}
        requires_operator = (definition.mode.value == "GUIDED"
                             or definition.safety.value == "POWERED_GUIDED"
                             or definition.handler in OPERATOR_HANDLERS)

        if definition.handler == "unsupported":
            reasons.append("NETWORK_COMMAND_TRANSPORT_UNAVAILABLE")

        if snap.firmware_kind == "H8_BENCH" and definition.handler not in {
                "documentary", "numeric", "bom_csv", "photo_inventory", "token_scan",
                "max3485", "fuse", "fuse_final", "decision", "team_evidence",
                "composite", "evidence_audit", "handover", "evidence_gap_list",
                "rerun_evidence", "invalidation_log", "protocol_freeze", "rehearsal",
                "campaign_manifest", "pzem_reference", "dataset_support", "derived",
                "polarity", "unsupported"}:
            reasons.append("H8_IMAGE_REQUIRES_CANONICAL_FIRMWARE")

        if (requires_commands or requires_telemetry) and not snap.connected:
            reasons.append("DEVICE_NOT_CONNECTED")
        if requires_commands and snap.connected and snap.command_transport is not True:
            reasons.append("COMMAND_TRANSPORT_UNVERIFIED")
        if requires_actuation and snap.connected and \
                str(snap.output_stage or "").upper() != "ENABLED":
            reasons.append("OUTPUT_STAGE_DISABLED")
        duration = _duration_s(definition, requires_actuation)
        if duration is not None:
            if duration > max_capture_s:
                reasons.append(
                    f"DURATION_EXCEEDS_CAPTURE_LIMIT:{duration:.0f}s>{max_capture_s:.0f}s")
            on_time = snap.limits.get("on_time_max_ms")
            if requires_actuation and on_time is not None and duration * 1000.0 > on_time:
                reasons.append(
                    f"DURATION_EXCEEDS_FIRMWARE_LIMIT:{duration:.0f}s>{on_time/1000.0:.0f}s")
        if requires_psu and snap.connected and snap.psu_present is not True:
            reasons.append("PSU_OFF_OR_PZEM_UNAVAILABLE")
        if requires_operator:
            reasons.append("OPERATOR_CONFIRMATION_REQUIRED")
            if definition.handler == "run_series" and scenario == "WARMUP" \
                    and snap.connected and snap.door_known is False:
                reasons.append("DOOR_ATTESTATION_REQUIRED")

        firmware = any(item.startswith(("COMMAND_TRANSPORT", "OUTPUT_STAGE",
                                        "H8_IMAGE", "DURATION_EXCEEDS_",
                                        "NO_TELEMETRY"))
                       for item in reasons)
        if hardware:
            state = HARDWARE_NONCOMPLIANT
        elif team:
            state = NEEDS_EXTERNAL_TEAM_INPUT
        elif firmware:
            state = NEEDS_FIRMWARE_CAPABILITY
        elif missing:
            state = NEEDS_EXISTING_PREREQUISITE
        elif "PSU_OFF_OR_PZEM_UNAVAILABLE" in reasons:
            state = NEEDS_PSU
        elif reasons:
            state = NEEDS_OPERATOR
        else:
            state = READY_NOW
        out.append(ReadinessItem(
            definition.test_id, definition.week, definition.title, state,
            tuple(reasons) or ("READY_NOW",), prereqs, prior_state,
            definition.handler, definition.mode.value, definition.safety.value))
    return out


def summarize(items: Iterable[ReadinessItem]) -> dict[str, int]:
    counts = {state: 0 for state in STATES}
    for item in items:
        counts[item.state] = counts.get(item.state, 0) + 1
    return counts


def markdown(items: Iterable[ReadinessItem]) -> str:
    rows = list(items)
    counts = summarize(rows)
    lines = [
        "# Member A execution-readiness gate",
        "",
        "Readiness is not acceptance PASS. It reports what blocks an executable",
        "workflow before a timed capture is launched.",
        "",
        "| State | Count |",
        "|---|---:|",
    ]
    for state in STATES:
        lines.append(f"| {state} | {counts.get(state, 0)} |")
    lines += ["", "| ID | Wk | State | Prior | Reasons |", "|---|---:|---|---|---|"]
    for item in rows:
        reasons = ", ".join(item.reasons).replace("|", "\\|")
        lines.append(
            f"| {item.test_id} | {item.week} | {item.state} | {item.prior} | {reasons} |")
    return "\n".join(lines) + "\n"


def write_report(items: Iterable[TestDefinition],
                 results: Mapping[str, TestResult],
                 snapshot: CapabilitySnapshot | None,
                 folder: pathlib.Path,
                 max_capture_s: float = 1900.0) -> dict[str, pathlib.Path]:
    rows = evaluate(items, results, snapshot, max_capture_s=max_capture_s)
    folder.mkdir(parents=True, exist_ok=True)
    import json
    json_path = folder / "readiness-report.json"
    md_path = folder / "readiness-report.md"
    json_path.write_text(json.dumps({
        "schema": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summarize(rows),
        "snapshot": {
            "connected": (snapshot or CapabilitySnapshot()).connected,
            "firmware_kind": (snapshot or CapabilitySnapshot()).firmware_kind,
            "output_stage": (snapshot or CapabilitySnapshot()).output_stage,
            "command_transport": (snapshot or CapabilitySnapshot()).command_transport,
            "psu_present": (snapshot or CapabilitySnapshot()).psu_present,
            "door_known": (snapshot or CapabilitySnapshot()).door_known,
            "limits": (snapshot or CapabilitySnapshot()).limits,
        },
        "items": [item.as_dict() for item in rows],
    }, indent=2), encoding="utf-8")
    md_path.write_text(markdown(rows), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
