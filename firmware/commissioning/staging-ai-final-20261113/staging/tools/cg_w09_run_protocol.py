"""ColdGuard W09 run protocol as a machine-readable gate checklist.

docs/05A §18 A-W09-01 names the gates in prose - "hardware config, sensor
identity, PZEM range, initial state, door, storage online" before a run and "end
reason, manual intervention, anomaly, validity candidate" after it. Prose gates
cannot be enforced, and a checklist a human re-reads every run is a checklist
that gets skimmed. This module turns each one into a record with three
properties that matter downstream:

* ``doc_anchor`` - which contract the gate comes from, so a gate that stops
  making sense can be traced to the sentence that created it;
* ``firmware_observability`` - whether the device itself can state the gate.
  ``OBSERVABLE`` means a shipped frame field decides it; ``PARTIAL`` means the
  device states something weaker than the gate asks for (the important ones:
  the device confirms *polarity*, not physical door position; it reports a
  ``#CG ROM`` role, not the probe's physical location); ``HOST_ONLY`` means the
  firmware cannot see it at all, so an operator or the capture host owns it;
* ``blocking`` - a run that fails a blocking gate is not a validity candidate.

Two facts the gate list preserves rather than smooths over:

* Every H8 frame in the committed capture reports
  ``supervised_bench=1`` **and** ``supervised_authorized=0``. The bench was
  supervised, and this firmware still cannot express an operator authorization
  inside a frame. That is recorded as a gate the firmware cannot close, not as
  an already-passed one.
* ``interlock_state`` is ``NOT_INSTALLED`` on the H8 bench build and all six
  operating limits are not fully resolved in the delivery firmware
  (``CG_LIMIT_COUNT`` items still ``UNRESOLVED``, docs/05A §17). The electrical
  gate is therefore about the *approved limit policy*, and the policy is checked
  from the frame, not assumed.
"""

from __future__ import annotations

import dataclasses
import json

RUN_PROTOCOL_VERSION = "w09-run-protocol-v1"
SCENARIO_IDS = ("S1_NORMAL_BASELINE", "S2_DOOR_DISTURBANCE", "S4_ACTUATION_RESPONSE_FAULT")

OBSERVABLE = "OBSERVABLE"
PARTIAL = "PARTIAL"
HOST_ONLY = "HOST_ONLY"
NOT_OBSERVABLE = HOST_ONLY  # accepted spelling for readers of the JSON

PHASE_BEFORE = "BEFORE_RUN"
PHASE_DURING = "DURING_RUN"
PHASE_AFTER = "AFTER_RUN"


@dataclasses.dataclass(frozen=True)
class Gate:
    gate_id: str
    phase: str
    requirement: str
    doc_anchor: str
    firmware_observability: str
    firmware_fields: tuple[str, ...]
    host_method: str
    blocking: bool
    failure_action: str
    scenario_scope: tuple[str, ...] = SCENARIO_IDS
    note: str = ""

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["firmware_fields"] = list(self.firmware_fields)
        out["scenario_scope"] = list(self.scenario_scope)
        return out


GATES: tuple[Gate, ...] = (
    # --- BEFORE_RUN -----------------------------------------------------------
    Gate(
        gate_id="GATE-HWCONFIG",
        phase=PHASE_BEFORE,
        requirement="hardware config",
        doc_anchor="docs/05A §18 A-W09-01; docs/03 §5 run manifest",
        firmware_observability=OBSERVABLE,
        firmware_fields=("hardware_config_id", "pin_map_version", "firmware_version"),
        host_method="match the boot line `#CG LOG v=.. fw=.. hw=.. device=.. pin_map=..` "
                    "against the frozen as-built record for the campaign",
        blocking=True,
        failure_action="stop: a frame from an unidentified configuration cannot enter a run",
        note="committed evidence carries hw=CG-HW-001, pin_map=2, fw=cg-w04-0.1.0",
    ),
    Gate(
        gate_id="GATE-BOOT-IDENTITY",
        phase=PHASE_BEFORE,
        requirement="one boot_id per run, recorded before the run starts",
        doc_anchor="docs/02 §4.2 identity",
        firmware_observability=OBSERVABLE,
        firmware_fields=("boot_id", "reset_cause", "run_id"),
        host_method="open the capture before ARM so the boot line is inside the file",
        blocking=True,
        failure_action="stop: opening the port resets the board, so a boot_id first seen "
                       "mid-capture means the early frames belong to another boot",
        note="the probe-identification session changed boot_id per touch window for "
             "exactly this reason",
    ),
    Gate(
        gate_id="GATE-SENSOR-IDENTITY",
        phase=PHASE_BEFORE,
        requirement="sensor identity",
        doc_anchor="docs/05A §18 A-W09-01; docs/01 §19.3 (unknown DS18B20 identity is INVALID)",
        firmware_observability=PARTIAL,
        firmware_fields=("t1_role", "t2_role", "t3_role", "t4_role", "probes_valid",
                          "probes_expected", "missing"),
        host_method="ROM ids come from the per-boot `#CG ROM role=.. rom=.. present=..` lines, "
                    "not from the frame; the frame carries slot roles only",
        blocking=True,
        failure_action="stop: a probe whose identity is unknown cannot drive a derived state",
        note=(
            "PARTIAL because the H8S frame has no ROM field. The slot->position mapping is "
            "OPERATOR-FROZEN (T1 centre, T2 TEC hot side, T3 bottom, T4 near door) and is "
            "recorded *by-source* from the firmware ROM table; it is not verified by readback"
        ),
    ),
    Gate(
        gate_id="GATE-SENSOR-POSITION",
        phase=PHASE_BEFORE,
        requirement="each probe is physically where the frozen geometry says it is",
        doc_anchor="docs/05A §18 A-W09-03 (sensor moved invalidates a run)",
        firmware_observability=HOST_ONLY,
        firmware_fields=(),
        host_method="operator visual confirmation against the frozen geometry record; the "
                    "2026-11-02 PROBE_IDENTIFICATION session is the identity record but must "
                    "never be reused as thermal data",
        blocking=True,
        failure_action="invalidate the run; a moved probe is a physical invalidation",
        note=(
            "the device cannot see its own probes being moved; slot roles stay "
            "ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING in the boot line"
        ),
    ),
    Gate(
        gate_id="GATE-ELECTRICAL-RANGE",
        phase=PHASE_BEFORE,
        requirement="PZEM range",
        doc_anchor="docs/05A §18 A-W09-01; docs/01 §19.3 (wrong PZEM range is INVALID)",
        firmware_observability=PARTIAL,
        firmware_fields=("voltage_v_status", "current_a_status", "power_w_status",
                          "limits_policy", "limits_operator_approved", "off_current_limit_a",
                          "energy_wh"),
        host_method="confirm the PZEM configuration and the limit table the boot line echoes",
        blocking=True,
        failure_action="stop: an unqualified electrical column makes the run's energy and "
                       "active-range claims unusable",
        note=(
            "PARTIAL: the frame reports a status per electrical field and the approved limit "
            "policy, but not the instrument's configured range. The committed CSV carries "
            "voltage_status/current_status EMPTY in all 957 rows, which is exactly the failure "
            "this gate exists to catch"
        ),
    ),
    Gate(
        gate_id="GATE-INITIAL-STATE",
        phase=PHASE_BEFORE,
        requirement="initial state",
        doc_anchor="docs/05A §18 A-W09-01; docs/03 §5 initial_condition",
        firmware_observability=OBSERVABLE,
        firmware_fields=("state", "stage", "snapshot", "air_c", "t1", "t2", "t3", "t4",
                          "rh_pct", "pressure_hpa"),
        host_method="record the first VALID frame as the run's initial condition",
        blocking=True,
        failure_action="stop: a run without a valid initial condition has no baseline to differ from",
        note="docs/03 §5 wants target_state, tmean_c, tmax_c, gradient_c and door state here",
    ),
    Gate(
        gate_id="GATE-DOOR-STATE",
        phase=PHASE_BEFORE,
        requirement="door closed at rest, with a machine-readable state",
        doc_anchor="docs/05A §18 A-W09-01; docs/03 §5 (initial_condition.door: CLOSED); "
                   "docs/05A §19 A-W10-02",
        firmware_observability=PARTIAL,
        firmware_fields=("door_open", "door_raw", "door_status", "door_polarity",
                          "door_age_ms", "door_cycles"),
        host_method="operator confirms the lid is seated; MC-38 polarity is confirmed per boot "
                    "with `DOOR NEAR_LOW|NEAR_HIGH <token>`",
        blocking=True,
        failure_action=(
            "do not start: door_open=UNKNOWN is not CLOSED. A polarity confirmation only makes "
            "the level nameable, it does not prove the magnet reaches the switch"
        ),
        note=(
            "the strongest available statement is sensor level + confirmed polarity. The "
            "2026-11-01 MC-38 work documents a stuck-high input that `DOOR NEAR_HIGH` made the "
            "firmware echo as CLOSED (door_open=0, snapshot=VALID), which is why this gate stays "
            "PARTIAL rather than OBSERVABLE"
        ),
    ),
    Gate(
        gate_id="GATE-OUTPUT-GATE",
        phase=PHASE_BEFORE,
        requirement="the actuator gate and interlock posture are known before ARM",
        doc_anchor="docs/05A §17 pass criteria; docs/05A §18 A-W09-01",
        firmware_observability=OBSERVABLE,
        firmware_fields=("interlock_state", "supervised_bench", "supervised_authorized",
                          "physical_output", "limits_enforced"),
        host_method="read the `#CG H8 ACTUATOR` and BOOT_POLICY lines",
        blocking=True,
        failure_action="stop: an unknown output posture is a safety posture change",
        note="committed H8 frames report supervised_bench=1 with supervised_authorized=0",
    ),
    Gate(
        gate_id="GATE-STORAGE-ONLINE",
        phase=PHASE_BEFORE,
        requirement="storage online (capture is actually being written)",
        doc_anchor="docs/05A §18 A-W09-01",
        firmware_observability=HOST_ONLY,
        firmware_fields=(),
        host_method="the capture host confirms the file is open and growing, and that rejections "
                    "are being written beside samples rather than dropped",
        blocking=True,
        failure_action="stop: a run with no raw file is not evidence-grade and cannot be replayed",
        note=(
            "the device has no non-volatile run storage; `cloud=NOT_PROVISIONED` in every frame "
            "and there is no transport in this firmware"
        ),
    ),
    Gate(
        gate_id="GATE-CADENCE",
        phase=PHASE_DURING,
        requirement="the declared cadence is met (1 Hz nominal) and gaps are counted",
        doc_anchor="docs/05A §18 A-W09-03 (missing key telemetry)",
        firmware_observability=PARTIAL,
        firmware_fields=("seq", "device_ms", "host_ack_seq"),
        host_method="gap statistics on the host clock, e.g. the W05 timing pilot method",
        blocking=False,
        failure_action="record as a validity finding; a gap invalidates the affected interval, "
                       "not necessarily the run",
        note="device_ms is per-boot uptime; the host clock owns the cadence claim",
    ),
    Gate(
        gate_id="GATE-SUPERVISION",
        phase=PHASE_DURING,
        requirement="an operator is at the bench for the whole energized run",
        doc_anchor="docs/05A §17 pass criteria (safe physical envelope); docs/04 §5.2",
        firmware_observability=PARTIAL,
        firmware_fields=("supervised_bench", "supervised_authorized"),
        host_method="operator attestation in the run manifest",
        blocking=True,
        failure_action="stop the stage",
        note="supervised_bench is a compile-time posture, not a live human-presence sensor",
    ),
    # --- AFTER_RUN ------------------------------------------------------------
    Gate(
        gate_id="GATE-END-REASON",
        phase=PHASE_AFTER,
        requirement="end reason",
        doc_anchor="docs/05A §18 A-W09-01",
        firmware_observability=OBSERVABLE,
        firmware_fields=("stop_reason", "state", "fault_bits", "fault"),
        host_method="confirm the last frame's stop_reason is consistent with how the stage ended",
        blocking=True,
        failure_action="record; an unexplained end reason makes the run a validity candidate only "
                       "after review",
        note="the committed 600 s capture ends with stop_reason=STAGE_DEADLINE on 131 rows",
    ),
    Gate(
        gate_id="GATE-MANUAL-INTERVENTION",
        phase=PHASE_AFTER,
        requirement="manual intervention logged",
        doc_anchor="docs/05A §18 A-W09-01",
        firmware_observability=PARTIAL,
        firmware_fields=(),
        host_method="the control file (commands actually sent) plus the operator's note; the "
                    "device cannot see a hand on a probe or a magnet near a sensor",
        blocking=True,
        failure_action="invalidate the run physically (A-W09-03) and keep the raw attempt",
        note=(
            "this is the gate the 2026-11-02 touch-identification session fails by design: every "
            "frame there has a hand on a probe, which is why it is excluded from S1/S2/S4"
        ),
    ),
    Gate(
        gate_id="GATE-ANOMALY",
        phase=PHASE_AFTER,
        requirement="anomaly recorded",
        doc_anchor="docs/05A §18 A-W09-01",
        firmware_observability=PARTIAL,
        firmware_fields=("fault_bits", "fault", "off_verify", "host_ack_reject"),
        host_method="operator observation plus host-side validity analysis",
        blocking=False,
        failure_action="record; unexplained anomalies escalate to the campaign owner",
        note="fault_bits is a device-side vocabulary; a thermal excursion with no fault bit is "
             "invisible to the device",
    ),
    Gate(
        gate_id="GATE-VALIDITY-CANDIDATE",
        phase=PHASE_AFTER,
        requirement="validity candidate assigned",
        doc_anchor="docs/05A §18 A-W09-03; docs/03 §6 run lifecycle "
                   "(COMPLETED_RAW -> VALIDITY_REVIEW)",
        firmware_observability=PARTIAL,
        firmware_fields=("snapshot",),
        host_method="cg_w09_validity.evaluate_frames() over the raw capture; the producer's "
                    "snapshot flag is a first pass, not the verdict",
        blocking=True,
        failure_action="no valid S1 ID is issued; the attempt stays in the registry",
        note="never delete an invalid attempt (A-W09-03)",
    ),
    Gate(
        gate_id="GATE-PROVENANCE-PIN",
        phase=PHASE_AFTER,
        requirement="every ingested source file is hash-pinned",
        doc_anchor="docs/04 §7 evidence ownership; docs/05A §18 A-W09-02",
        firmware_observability=HOST_ONLY,
        firmware_fields=(),
        host_method="SHA-256 of each source recorded in the export and in SHA256SUMS.txt",
        blocking=True,
        failure_action="the export is not published",
        note="a dataset whose bytes are not pinned cannot be re-derived later",
    ),
    Gate(
        gate_id="GATE-SESSION-CLASS",
        phase=PHASE_AFTER,
        requirement="the run's session class is eligible for the dataset it is entering",
        doc_anchor="docs/05A §18 A-W09-03",
        firmware_observability=HOST_ONLY,
        firmware_fields=(),
        host_method="cg_w09_validity rejects frames whose run label is an excluded class",
        blocking=True,
        failure_action="reject the frames; PROBE_IDENTIFICATION may never enter S1/S2/S4",
        note="enforced by label match, not by inspecting temperatures, so it cannot be defeated "
             "by a plausible-looking touch window",
    ),
    Gate(
        gate_id="GATE-NON-PHYSICAL-FILTER",
        phase=PHASE_AFTER,
        requirement="a host fixture can never be published as a run",
        doc_anchor="docs/05A §18 A-W09-02",
        firmware_observability=HOST_ONLY,
        firmware_fields=(),
        host_method="every export refuses a source whose provenance has "
                    "is_physical_measurement=false",
        blocking=True,
        failure_action="the export raises instead of writing",
        note="validated by validate_w09.py and by the W09/W10/W11 unit tests",
    ),
    Gate(
        gate_id="GATE-S2-DISTURBANCE-CONTROL",
        phase=PHASE_AFTER,
        requirement="for S2, the disturbance was operator-controlled and timed",
        doc_anchor="docs/05A §19 A-W10-02/03",
        firmware_observability=HOST_ONLY,
        firmware_fields=("door_open", "door_cycles", "device_ms"),
        host_method="MC-38 transition as machine ground truth plus the operator timer as a "
                    "secondary check",
        blocking=True,
        failure_action="the disturbance is not an S2 pilot event; record it as an incidental door "
                       "observation instead",
        scenario_scope=("S2_DOOR_DISTURBANCE",),
        note=(
            "an incidental OPEN window inside a commissioning stage is not a protocolised "
            "disturbance and is not counted as one"
        ),
    ),
    Gate(
        gate_id="GATE-S4-NO-PROMOTION",
        phase=PHASE_AFTER,
        requirement="for S4, a refused command never appears as an applied action",
        doc_anchor="docs/05A §20 A-W11-01/02; docs/02 §32.2",
        firmware_observability=PARTIAL,
        firmware_fields=("last_ack_status", "desired_cooling", "desired_duty_permille"),
        host_method="cg_w11_s4 refuses a trace that infers applied evidence from intent",
        blocking=True,
        failure_action="reject the trace",
        scenario_scope=("S4_ACTUATION_RESPONSE_FAULT",),
        note="applied state must be read from the device, not from what was requested",
    ),
)


def gate_by_id(gate_id: str) -> Gate:
    for gate in GATES:
        if gate.gate_id == gate_id:
            return gate
    raise KeyError(gate_id)


def document(protocol_version: str = RUN_PROTOCOL_VERSION) -> dict:
    """The whole protocol as a JSON-serialisable dict."""
    counts: dict[str, int] = {}
    observability: dict[str, int] = {}
    for gate in GATES:
        counts[gate.phase] = counts.get(gate.phase, 0) + 1
        observability[gate.firmware_observability] = (
            observability.get(gate.firmware_observability, 0) + 1
        )
    return {
        "protocol_version": protocol_version,
        "source_requirement": "docs/05A §18 A-W09-01 (Week 09 run checklist)",
        "phases": [PHASE_BEFORE, PHASE_DURING, PHASE_AFTER],
        "gate_counts": counts,
        "firmware_observability_counts": observability,
        "blocking_gates": [g.gate_id for g in GATES if g.blocking],
        "gates_firmware_cannot_observe": [g.gate_id for g in GATES if g.firmware_observability == HOST_ONLY],
        "gates": [gate.as_dict() for gate in GATES],
        "honesty_notes": [
            "a gate is OBSERVABLE only when a shipped frame field decides it",
            "door polarity confirmation names a level; it does not prove a physical door position",
            "firmware has no run storage and no transport: storage and command issuance are "
            "host/operator gates by construction",
            "an invalid attempt is recorded, never deleted (docs/05A §18 A-W09-03)",
        ],
    }


def render_markdown(doc: dict) -> str:
    lines = [
        f"# S1/S2/S4 run protocol v{doc['protocol_version'].rsplit('-v', 1)[-1]}",
        "",
        f"Generated from `firmware/tools/cg_w09_run_protocol.py` "
        f"({doc['protocol_version']}); source requirement: {doc['source_requirement']}.",
        "",
        "Status: **IMPLEMENTED / HOST_VERIFIED**. No gate here was closed by a physical session; "
        "the list is the instrument Member A and the operator use to close them.",
        "",
        "`Firmware` says whether the device itself can decide the gate:",
        "",
        "| value | meaning |",
        "|---|---|",
        f"| `OBSERVABLE` | a shipped frame field decides it ({doc['firmware_observability_counts'].get(OBSERVABLE, 0)} gates) |",
        f"| `PARTIAL` | the device states something weaker than the gate asks ({doc['firmware_observability_counts'].get(PARTIAL, 0)}) |",
        f"| `HOST_ONLY` | the firmware cannot see it at all ({doc['firmware_observability_counts'].get(HOST_ONLY, 0)}) |",
        "",
    ]
    for phase in doc["phases"]:
        gates = [g for g in doc["gates"] if g["phase"] == phase]
        if not gates:
            continue
        lines += [
            f"## {phase.replace('_', ' ').title()} - {len(gates)} gate(s)",
            "",
            "| Gate | Requirement | Doc anchor | Firmware | Blocking | Frame fields |",
            "|---|---|---|---|---|---|",
        ]
        for gate in gates:
            fields = ", ".join(f"`{f}`" for f in gate["firmware_fields"]) or "*(none)*"
            lines.append(
                f"| `{gate['gate_id']}` | {gate['requirement']} | {gate['doc_anchor']} | "
                f"{gate['firmware_observability']} | {'yes' if gate['blocking'] else 'no'} | {fields} |"
            )
        lines.append("")
        for gate in gates:
            lines += [
                f"### `{gate['gate_id']}` - {gate['requirement']}",
                "",
                f"* Host method: {gate['host_method']}",
                f"* On failure: {gate['failure_action']}",
                f"* Scope: {', '.join(gate['scenario_scope'])}",
            ]
            if gate["note"]:
                lines.append(f"* Note: {gate['note']}")
            lines.append("")
    lines += [
        "## Protocol-level honesty notes",
        "",
    ]
    lines += [f"* {note}" for note in doc["honesty_notes"]]
    lines += [
        "",
        "## Gates the firmware cannot close",
        "",
        ", ".join(f"`{g}`" for g in doc["gates_firmware_cannot_observe"]),
        "",
        "These are operator or capture-host gates. A frame cannot vouch for them, so a run whose "
        "record shows them as closed only because the device was happy is not evidence-grade.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    argv = list(argv if argv is not None else __import__("sys").argv[1:])
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the machine-readable protocol")
    parser.add_argument("--markdown", action="store_true", help="print the human-readable form")
    args = parser.parse_args(argv)
    doc = document()
    if args.markdown:
        print(render_markdown(doc))
        return 0
    print(json.dumps(doc, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
