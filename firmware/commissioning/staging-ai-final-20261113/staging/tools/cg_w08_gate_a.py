"""W08 A-W08-04 / A-W08-05 - the SAFE_LOCAL physical-input table and Gate A package.

    py firmware/tools/cg_w08_gate_a.py [--bench-root DIR] [--json OUT.json]

Two things are assembled here, both from bytes that already exist:

``SAFE_LOCAL physical inputs`` (A-W08-04)
    the honest split between what this firmware can *observe* about the plant and
    what must come from Member D's policy. The device emits the input side; the
    decision of when to enter/leave SAFE_LOCAL, what "protective behaviour"
    means and what the limits are is `docs/02` section 2.6 + Member D's contract.
    Each row names the field on the delivered serial schema, the field on the
    bench-image wire, where it survives in the committed capture, and the gap.

``Gate A package`` (A-W08-05)
    the H0-H7 artifact index (docs/01 sections "Gate H0"..."Gate H7"), the
    per-requirement status walk of docs/05A section 17, the named gaps, and the
    consolidated operator action queue for W08. The pass criteria are reported
    as MET / NOT MET with the evidence, and nothing is promoted because a host
    number looks comfortable.

`PHYSICALLY_VERIFIED` is never emitted by this module: it reads files, it does
not measure anything. Status labels are REAL_DATA_ANALYZED for observations,
HOST_VERIFIED for the tool's behaviour, TEAM_DEPENDENCY for Member D/C items,
NEED_USER_ACTION for supervised-bench items and BLOCKED_HARDWARE where a
physical input simply does not exist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass

import cg_w08_envelope as envelope

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]

# --------------------------------------------------------------------------
# SAFE_LOCAL physical inputs
# --------------------------------------------------------------------------

# Every row is anchored on a token this repository actually contains:
#   * ``delivered`` - a field of the production serial telemetry schema as
#     emitted by firmware/main/cg_telemetry.c (host reference:
#     firmware/tools/cg_telemetry_schema.py).
#   * ``wire``      - a token of the bench image's ``#CG H8S schema=3`` line, as
#     recorded in Member A's local monitor samples.
#   * ``capture``   - the column of the committed H8-C 600 s CSV, or ABSENT.
@dataclass
class SafeLocalInput:
    input_id: str
    physical_input: str
    why_safe_local_needs_it: str
    firmware_can_observe: str            # YES / PARTIAL / NO
    delivered_schema_field: str
    bench_wire_field: str
    committed_capture_field: str
    authentic_data: str
    validity_condition: str
    recorded_unqualified: str            # true / false / n-a
    gap: str
    owner: str
    status_label: str

    def as_row(self) -> dict[str, object]:
        return self.__dict__.copy()


SAFE_LOCAL_INPUTS: tuple[SafeLocalInput, ...] = (
    SafeLocalInput(
        input_id="SL-01",
        physical_input="chamber CENTER temperature (T1, as-built CHAMBER_CENTER)",
        why_safe_local_needs_it="the controlled variable: local heating/cooling "
                                "decisions and overtemperature protection act on it",
        firmware_can_observe="YES",
        delivered_schema_field="t_inside_c + t_inside_status",
        bench_wire_field="t1 + t1_status + t1_age_ms",
        committed_capture_field="t1_c, t1_status, t1_age_ms (role column says UNASSIGNED)",
        authentic_data="957/957 frames with t1_status=OK, age 46 ms in the committed "
                       "H8-C 600 s capture",
        validity_condition="t1_status=OK and age within the acquisition period",
        recorded_unqualified="false",
        gap="the device role token is UNASSIGNED in every frame, so the mapping "
            "T1=CHAMBER_CENTER comes from the operator-frozen as-built record, not "
            "from the frame",
        owner="A (sensing) / D (which value is the control variable)",
        status_label="REAL_DATA_ANALYZED",
    ),
    SafeLocalInput(
        input_id="SL-02",
        physical_input="TEC HOT_SIDE temperature (T2, as-built TEC_HOT_SIDE)",
        why_safe_local_needs_it="the only overheat input the bench image treats as "
                                "mandatory (mandatory_roles=HOT_SIDE)",
        firmware_can_observe="YES",
        delivered_schema_field="t_hot_side_c + t_hot_side_status (NOT_ASSIGNED in the "
                               "W05 fixture)",
        bench_wire_field="t2 + t2_status + t2_role=HOT_SIDE + t2_age_ms",
        committed_capture_field="t2_c, t2_status, t2_role=HOT_SIDE, t2_age_ms",
        authentic_data="957/957 frames OK; max 39.938 C in the committed capture, "
                       "37.688 C in the H8 B-E endurance sessions",
        validity_condition="t2_status=OK; snapshot=VALID requires it present",
        recorded_unqualified="false",
        gap="the production schema still reports the hot-side channel as "
            "NOT_ASSIGNED, so the delivered build has no hot-side protection input "
            "until the role is wired end to end",
        owner="A (channel role in firmware) / D (the limit)",
        status_label="REAL_DATA_ANALYZED",
    ),
    SafeLocalInput(
        input_id="SL-03",
        physical_input="chamber BOTTOM (T3) and NEAR-DOOR (T4/SPARE)",
        why_safe_local_needs_it="spatial validity of the chamber reading and door "
                                "disturbance detection",
        firmware_can_observe="YES",
        delivered_schema_field="raw_t3_c / raw_spare_c + *_status",
        bench_wire_field="t3, t4 + *_status + *_role=UNASSIGNED + *_age_ms",
        committed_capture_field="t3_c/t3_status/t3_age_ms, t4_c/t4_status/t4_age_ms",
        authentic_data="957/957 frames OK on both channels",
        validity_condition="*_status=OK",
        recorded_unqualified="false",
        gap="both report role UNASSIGNED in every frame; no frame proves which "
            "physical probe it is, and the ROM ids are by-source (firmware ROM map), "
            "not a readback",
        owner="A",
        status_label="REAL_DATA_ANALYZED",
    ),
    SafeLocalInput(
        input_id="SL-04",
        physical_input="chamber air / humidity / pressure (BME280)",
        why_safe_local_needs_it="the air-side evidence and the pressure-gated "
                                "snapshot; docs/01 makes pressure mandatory for a "
                                "valid frame",
        firmware_can_observe="YES",
        delivered_schema_field="t_ambient_c / relative_humidity_pct + *_status",
        bench_wire_field="air_c + air_c_status + air_c_age_ms, rh_pct + rh_pct_status, "
                         "pressure_hpa + pressure_status",
        committed_capture_field="bme_air_c, bme_rh_pct (NO status column), "
                                "bme_pressure_hpa + bme_pressure_status",
        authentic_data="957/957 frames with air/rh/pressure status OK on the wire; "
                       "air age constant at 775 ms",
        validity_condition="*_status=OK",
        recorded_unqualified="true for bme_air_c and bme_rh_pct in the committed CSV "
                            "(those two columns have no status companion)",
        gap="the CSV builder dropped the air and humidity validity tokens, so an "
            "air statistic quoted from the CSV is unqualified even though the wire "
            "labelled it OK",
        owner="A",
        status_label="REAL_DATA_ANALYZED",
    ),
    SafeLocalInput(
        input_id="SL-05",
        physical_input="door state (MC-38)",
        why_safe_local_needs_it="a door-open condition changes the plant; SAFE_LOCAL "
                                "must not fight an open door with cooling effort",
        firmware_can_observe="PARTIAL",
        delivered_schema_field="door_open + door_status (UNVERIFIED in the W05 fixture)",
        bench_wire_field="door_open, door_raw, door_status, door_age_ms, door_cycles, "
                         "door_polarity",
        committed_capture_field="door_open, door_polarity - door_status and door_age_ms "
                                "are ABSENT from the CSV",
        authentic_data="door_status=VALID in 940/957 wire frames (UNVERIFIED in the 17 "
                       "pre-snapshot frames); door_polarity=CONFIRMED in 940",
        validity_condition="door_status=VALID (wire) and polarity CONFIRMED",
        recorded_unqualified="true in the committed CSV (no status column at all)",
        gap="no magnetic/door disturbance experiment has been recorded, and the "
            "polarity check is by-source, not by a documented test procedure",
        owner="A (signal) / D (what an open door forbids)",
        status_label="REAL_DATA_ANALYZED",
    ),
    SafeLocalInput(
        input_id="SL-06",
        physical_input="branch voltage / current / power (PZEM-017)",
        why_safe_local_needs_it="the only electrical proof that a commanded cooling "
                                "action actually moved power",
        firmware_can_observe="YES (with one-poll latency)",
        delivered_schema_field="voltage_v / current_a / power_w + *_status + power_age_ms",
        bench_wire_field="voltage_v, current_a, power_w + *_status + *_age_ms",
        committed_capture_field="voltage_v + voltage_status (EMPTY in all 957 rows), "
                                "current_a + current_status (EMPTY), power_w and "
                                "energy_wh with NO status column",
        authentic_data="957/957 frames OK on the wire, age 636-666 ms; V/I/P figures "
                       "in the CSV are the same numbers but unqualified",
        validity_condition="*_status=OK AND *_age_ms within the acquisition period AND "
                           "the frame is not a documented register-latency frame",
        recorded_unqualified="true",
        gap="the producer publishes a 666 ms-old sample into a 1 Hz frame and the CSV "
            "carries no token at all, so downstream consumers cannot separate fresh, "
            "stale and held-over readings",
        owner="A (producer) / B (features) / D (staleness policy)",
        status_label="REAL_DATA_ANALYZED",
    ),
    SafeLocalInput(
        input_id="SL-07",
        physical_input="accumulated energy (PZEM energy register)",
        why_safe_local_needs_it="energy-aware control (RQ6) and the "
                                "energy-per-cooling-degree statistic",
        firmware_can_observe="PARTIAL",
        delivered_schema_field="energy_wh + energy_status (present in the W05 fixture)",
        bench_wire_field="energy_wh ONLY - no energy_wh_status and no age token exists",
        committed_capture_field="energy_wh, no status column",
        authentic_data="957/957 frames carry a counter; it is monotonic non-decreasing "
                       "and quantised to 1 Wh",
        validity_condition="NONE IS PUBLISHED on the bench wire; the delivered schema "
                          "expects energy_status",
        recorded_unqualified="true",
        gap="a 1 Wh counter at ~85 W updates about every 42 s, so it cannot resolve a "
            "short run, and it has no validity token on the bench wire at all",
        owner="A",
        status_label="REAL_DATA_ANALYZED",
    ),
    SafeLocalInput(
        input_id="SL-08",
        physical_input="applied duty and its readback (IBT-2 / LEDC)",
        why_safe_local_needs_it="separating desired from applied is the whole "
                                "command-lifecycle contract",
        firmware_can_observe="YES for duty, NO for the enable pins",
        delivered_schema_field="pwm_duty + cooling_applied (FIRMWARE_OUTPUT_STATE)",
        bench_wire_field="pwm_req_permille, pwm_applied_permille, pwm_readback_permille, "
                         "pwm_freq_hz, pwm_freq_rb_hz, ren_command, len_command, "
                         "enable_readback",
        committed_capture_field="pwm_req_permille, pwm_applied_permille, "
                                "pwm_readback_permille",
        authentic_data="pwm_readback matched applied in 600/600 driven and 357/357 "
                       "idle frames; frequency readback 1000 Hz in 957/957",
        validity_condition="pwm_readback_permille == pwm_applied_permille is the only "
                           "available check",
        recorded_unqualified="false",
        gap="enable_readback reports ren:0,len:0 in EVERY frame including the 600 "
            "driven ones while ren_command=1, so the driver enable state is commanded "
            "but never observed; output verification rests on current alone",
        owner="A",
        status_label="REAL_DATA_ANALYZED",
    ),
    SafeLocalInput(
        input_id="SL-09",
        physical_input="TEC / hot-side fan running",
        why_safe_local_needs_it="hot-side heat rejection is a precondition for safe "
                                "cooling; without it the TEC self-heats",
        firmware_can_observe="NO",
        delivered_schema_field="fan_command + fan_status (NOT_COMMANDABLE)",
        bench_wire_field="fan=OPERATOR_CONFIRMED, fan_readback=NOT_ELECTRONICALLY_VERIFIED",
        committed_capture_field="fan, fan_readback",
        authentic_data="fan=OPERATOR_CONFIRMED in 940/957 frames, i.e. a human said "
                       "so; fan_readback is NOT_ELECTRONICALLY_VERIFIED in 957/957",
        validity_condition="none exists: there is no tachometer or current path to read",
        recorded_unqualified="true",
        gap="the only fan evidence is operator presence; SAFE_LOCAL cannot detect a "
            "stopped fan from any recorded field",
        owner="A (hardware/observation) / D (what a stopped fan forbids)",
        status_label="BLOCKED_HARDWARE",
    ),
    SafeLocalInput(
        input_id="SL-10",
        physical_input="safety interlock / hardware cutout",
        why_safe_local_needs_it="docs/01's independent overheat path; SAFE_LOCAL's "
                                "last resort must not depend on software",
        firmware_can_observe="NO",
        delivered_schema_field="(no field)",
        bench_wire_field="interlock_state=NOT_INSTALLED in 957/957 frames",
        committed_capture_field="ABSENT",
        authentic_data="the capture proves absence, not presence",
        validity_condition="n/a",
        recorded_unqualified="n-a",
        gap="no interlock is installed, so every stop recorded so far came from "
            "software or from the operator at the PSU",
        owner="operator (install) / A (wire it) / D (use it)",
        status_label="BLOCKED_HARDWARE",
    ),
    SafeLocalInput(
        input_id="SL-11",
        physical_input="operating limits and who approved them",
        why_safe_local_needs_it="SAFE_LOCAL is by definition a policy mode: it decides "
                                "what protective cooling is allowed without the backend",
        firmware_can_observe="PARTIAL (it reports the policy it was given)",
        delivered_schema_field="(limits table lives in cg_tec_limits.c, not in telemetry)",
        bench_wire_field="limits_policy=APPROVED, limits_operator_approved=1, "
                         "limits_enforced=1, limits_simulated_enforcement=0",
        committed_capture_field="limits_policy=APPROVED in 957/957 rows",
        authentic_data="the bench image reports an APPROVED policy; the production "
                       "build in this branch ships all six limits UNRESOLVED",
        validity_condition="cg_tec_limits_all_resolved() gates cg_tec_start(); an "
                           "unresolved table means START refuses",
        recorded_unqualified="n-a",
        gap="the six (docs/05A) / seven (docs/06) limit-count discrepancy and the "
            "numeric values are Member D's decision; the bench image's APPROVED table "
            "is not the delivered firmware's and must never be quoted as such",
        owner="D (policy/values) + A (enforcement)",
        status_label="TEAM_DEPENDENCY",
    ),
    SafeLocalInput(
        input_id="SL-12",
        physical_input="wall clock / command expiry",
        why_safe_local_needs_it="an expiring command is what makes remote actuation "
                                "safe; SAFE_LOCAL timing depends on it",
        firmware_can_observe="NO",
        delivered_schema_field="timestamp_utc=UNAVAILABLE, timestamp_utc_source="
                              "DEVICE_HAS_NO_WALL_CLOCK",
        bench_wire_field="same two tokens",
        committed_capture_field="ABSENT (the CSV has device_ms only)",
        authentic_data="every committed capture shows device-relative time only",
        validity_condition="absolute expiry is unevaluable without a synchronised clock",
        recorded_unqualified="n-a",
        gap="clock synchronisation is Member C's work; until it exists, expiry-based "
            "protection is fail-closed rather than satisfied",
        owner="C",
        status_label="TEAM_DEPENDENCY",
    ),
    SafeLocalInput(
        input_id="SL-13",
        physical_input="backend / broker reachability",
        why_safe_local_needs_it="SAFE_LOCAL is entered BECAUSE the remote path is "
                                "unavailable, so the device must know it is gone",
        firmware_can_observe="PARTIAL",
        delivered_schema_field="(no cloud field in the delivered schema)",
        bench_wire_field="cloud=NOT_PROVISIONED in 957/957 frames",
        committed_capture_field="ABSENT",
        authentic_data="no capture ever contained a cloud session",
        validity_condition="n/a",
        recorded_unqualified="n-a",
        gap="the delivered firmware has no transport, so removing the broker/backend "
            "(the literal A-W08-04 ask) cannot be tested against it; the SAFE_LOCAL "
            "mode itself is Member D's",
        owner="D (mode) / C (transport) / A (local behaviour once told)",
        status_label="TEAM_DEPENDENCY",
    ),
    SafeLocalInput(
        input_id="SL-14",
        physical_input="fault latch and why the stage stopped",
        why_safe_local_needs_it="protection must be provable after the fact",
        firmware_can_observe="YES",
        delivered_schema_field="fault_code + fault_reason",
        bench_wire_field="fault_bits, fault, stop_reason, fault_latency_us, "
                         "off_verify, off_current_limit_a",
        committed_capture_field="fault_bits, stop_reason",
        authentic_data="fault_bits=0 in 957/957 frames; stop_reason STAGE_DEADLINE in "
                       "131; off_verify PASS in 126 wire frames, PENDING in 5",
        validity_condition="fault_bits=0 AND stop_reason in the documented vocabulary",
        recorded_unqualified="false",
        gap="fault_latency_us=-1 in every frame: the fault-to-stop latency has never "
            "been measured because no fault was ever injected",
        owner="A",
        status_label="REAL_DATA_ANALYZED",
    ),
)


# --------------------------------------------------------------------------
# H0-H7 artifact index (docs/01 Gate H0 ... Gate H7)
# --------------------------------------------------------------------------

# Curated rather than a directory walk: a reviewer must be able to see which
# milestone each artifact answers, and the list must not silently grow.
H_INDEX: tuple[dict[str, str], ...] = (
    {"gate": "H0 mechanical assembly",
     "required": "V1 installed, TEC integrated, paste, fan mounted, penetration "
                 "sealed, sensor positions fixed, panel outside chamber",
     "artifact": "evidence/A/W01/hardware-audit-w01.md",
     "state": "committed"},
    {"gate": "H0 as-built positions",
     "required": "the frozen as-built pin/position record",
     "artifact": "evidence/A/as-built-pinmap-2026-10-27.md",
     "state": "committed"},
    {"gate": "H0/H1 photos",
     "required": "photographic inventory of the assembly",
     "artifact": "evidence/A/W01/photo-inventory.csv",
     "state": "committed"},
    {"gate": "H1 sensor subsystem",
     "required": "three expected DS18B20 ROM ids, BME read, MC-38 open/close",
     "artifact": "evidence/A/W02/ds18b20/ds18b20-verification.md",
     "state": "committed"},
    {"gate": "H1 ROM map",
     "required": "the by-source ROM identity table",
     "artifact": "evidence/A/W02/sensor-rom-map.yaml",
     "state": "committed"},
    {"gate": "H1 door subsystem",
     "required": "MC-38 open/close verified",
     "artifact": "evidence/A/W02/mc38/mc38-bench-report.md",
     "state": "committed"},
    {"gate": "H2 logic power",
     "required": "5 V rail verified, no TEC actuation",
     "artifact": "evidence/A/W03/logic-power-measurement.md",
     "state": "committed"},
    {"gate": "H3 PZEM / RS-485",
     "required": "Modbus response, 50 A profile, V/I/P/Wh readable",
     "artifact": "evidence/A/W03/pzem-register-readback.txt",
     "state": "committed"},
    {"gate": "H3 current profile readback",
     "required": "50 A profile verified on the wire",
     "artifact": "evidence/A/W03/hardware-2026-10-27/test-131-profile-readback.md",
     "state": "committed"},
    {"gate": "H3 OFF-state envelope",
     "required": "zero-current envelope with per-sample validity",
     "artifact": "evidence/A/W03/hardware-2026-10-27/raw/test-132b-off-envelope.csv",
     "state": "committed"},
    {"gate": "H4 IBT-2 logic",
     "required": "default OFF, enable, direction, reset, 3.3 V logic",
     "artifact": "evidence/A/W03/hardware-2026-10-27/test-133b-reset-default-off.md",
     "state": "committed"},
    {"gate": "H4 default-OFF on the delivered build",
     "required": "boot with outputs off",
     "artifact": "evidence/A/W04/boot-default-off-note.md",
     "state": "committed"},
    {"gate": "H4 IBT-2 pin map",
     "required": "the pin contract actually used",
     "artifact": "evidence/A/W03/ibt2-pin-map.md",
     "state": "committed"},
    {"gate": "H5 power branch",
     "required": "fuse installed, high-current wiring, shunt, terminal check, fan",
     "artifact": "evidence/A/W04/fuse-commissioning-note.md",
     "state": "committed (choice NOT frozen)"},
    {"gate": "H5 shunt continuity",
     "required": "series return path proven",
     "artifact": "evidence/A/W03/hardware-2026-10-27/shunt-continuity.md",
     "state": "committed"},
    {"gate": "H5 G0 electrical verification",
     "required": "branch voltage/presence evidence before any drive",
     "artifact": "evidence/A/W04/g0-electrical-verification.md",
     "state": "committed"},
    {"gate": "H6 conservative TEC test",
     "required": "current present, correct cooling face, hot side rejects, no "
                 "abnormal connector behaviour",
     "artifact": "evidence/A/W04/h6/41-h6-run-analysis.md",
     "state": "committed"},
    {"gate": "H6 trace artifact",
     "required": "the 1 Hz electrical samples",
     "artifact": "evidence/A/W04/h6/first-tec-trace.csv",
     "state": "committed"},
    {"gate": "H6 polarity",
     "required": "correct cooling face proven",
     "artifact": "evidence/A/W04/polarity-photo.md",
     "state": "committed (direction recorded, no photograph)"},
    {"gate": "H7 full characterization",
     "required": "V/I/P, actuation state, T1/T2/T3, BME, door, timing, thermal "
                 "response over the duty ladder",
     "artifact": "evidence/A/W04/tec-cooling-response-600s.csv",
     "state": "committed (one duty level: 999 per mille)"},
    {"gate": "H7 duty ladder",
     "required": "the 20-100 % staircase",
     "artifact": "h7/50-stage-20pct.md .. h7/60-h7-100pct-duty-audit.md",
     "state": "local-bench only, NOT committed in this repository"},
    {"gate": "H7 endurance / hot side",
     "required": "long runs at 100 % duty",
     "artifact": "h8/phase4e/H8_FULL_SENSOR_ENDURANCE_REPORT.md",
     "state": "local-bench only, NOT committed in this repository"},
    {"gate": "W05 timing / freshness",
     "required": "cadence and age statistics",
     "artifact": "evidence/A/W05/timing-pilot.json",
     "state": "committed (synthetic pilot capture, not a bench run)"},
    {"gate": "W06 command/ACK contract",
     "required": "desired vs applied state, idempotency, expiry",
     "artifact": "evidence/A/W06/ack-fixture.json",
     "state": "committed (host scenarios, never a device round trip)"},
    {"gate": "W07 plant repeatability",
     "required": "repeated baseline runs and their spread",
     "artifact": "evidence/A/W07",
     "state": "NOT IN THIS CHECKOUT (stacked branch, integration dependency)"},
)

# The W08 half of the consolidated operator queue. Sessions are merged so the
# operator does not re-energize the bench for each requirement.
W08_ACTION_QUEUE: tuple[dict[str, str], ...] = (
    {
        "queue_id": "OQ-W08-1",
        "requirement": "A-W08-02",
        "action": "Photograph the installed branch fuse body (rating, 250 V, "
                  "glass/ceramic) and the spare 10 A fuse; photograph the installed "
                  "power cable marking and measure its run length.",
        "power_state": "PSU OFF, branch de-energized; no flashing, no serial needed",
        "existing_evidence": "evidence/A/W04/fuse-commissioning-note.md (15 A "
                             "operator-reported, no marking photographed); "
                             "evidence/A/W01/bom-audit.csv HW-19 UNVERIFIED",
        "safety_prerequisites": "none beyond de-energized inspection",
        "expected_capture": "two photographs + a length + the cable's insulation "
                            "temperature class from the jacket marking, and the "
                            "conductor's printed cross-section (which decides whether "
                            "the 1.75 mm core diameter is a solid round conductor)",
        "unlocks": "the ampacity basis that A-W08-02 needs before any of 10/15/20 A "
                   "can be defended; closes the HW-19 audit row. It is necessary, not "
                   "sufficient: it does not clear an energized-session gate, which "
                   "also needs the duty-0 anomaly classification and Member D's "
                   "thresholds",
        "min_sessions": "1 (cold inspection, no supervision of energized parts needed)",
        "status_label": "NEED_USER_ACTION",
    },
    {
        "queue_id": "OQ-W08-2",
        "requirement": "A-W08-03",
        "action": "One supervised long run at 100 % duty for at least 1800 s with the "
                  "operator touching nothing and reporting terminal / IBT-2 / cable "
                  "temperature by touch-free measurement at t=0, 300, 600, 900, 1200, "
                  "1500, 1800 s.",
        "power_state": "energized branch, attended bench, operator at the PSU",
        "existing_evidence": "H8-E 1800 s already ran with T2 max 37.688 C, no faults, "
                             "OFF PASS (local bench, not committed); nothing in any "
                             "frame measures the terminals or the IBT-2 case",
        "safety_prerequisites": "return path replacement verified (done); PSU "
                                "continuous rating confirmed for ~85 W for 30 min; "
                                "stop immediately on abnormal smell/discolouration; "
                                "off_current_limit 0.200 A gate active",
        "expected_capture": "one samples.jsonl of >= 1800 frames plus a timed "
                            "temperature log of the terminal block and IBT-2 case",
        "unlocks": "A-W08-03's fourth bullet (terminals/IBT-2 abnormal behaviour) and "
                   "the component-thermal half of the fuse decision",
        "min_sessions": "1 (merge with OQ-W15-2's duty points only if the ladder is "
                        "re-authorized; a 100 % long run must keep its own repetition)",
        "status_label": "NEED_USER_ACTION",
    },
    {
        "queue_id": "OQ-W08-3",
        "requirement": "A-W08-04",
        "action": "SAFE_LOCAL demonstration session: with TEC running, remove "
                  "broker/backend reachability (and then restore it) while Controller "
                  "A keeps sensing and local output behaviour is recorded.",
        "power_state": "energized branch, attended",
        "existing_evidence": "none: the delivered firmware has no transport "
                             "(cloud=NOT_PROVISIONED in every frame) and Member D "
                             "owns the SAFE_LOCAL state machine",
        "safety_prerequisites": "Member D's SAFE_LOCAL policy implemented and flashed; "
                                "Member C's transport present so that 'removed' means "
                                "something; limits table resolved",
        "expected_capture": "one capture spanning connected -> disconnected -> "
                            "reconnected with local sensor continuity and the applied "
                            "state in every frame",
        "unlocks": "A-W08-04 and the docs/00 Q7 resilience claim",
        "min_sessions": "1 (depends on D + C delivering a mode to test)",
        "status_label": "TEAM_DEPENDENCY",
    },
    {
        "queue_id": "OQ-W08-4",
        "requirement": "A-W08-01 / A-W08-05",
        "action": "Deliver the committed copy of the H7 duty-ladder logs and the H8 "
                  "A-E endurance samples.jsonl into this repository (hash-pinned, "
                  "read-only), or accept that the envelope's 20-90 % rows stay "
                  "LOCAL_BENCH and unreproducible for reviewers.",
        "power_state": "no hardware at all: this is an evidence-move, not a test",
        "existing_evidence": "the files exist in Member A's local W04 tree and were "
                             "read (never copied) by these tools",
        "safety_prerequisites": "none",
        "expected_capture": "committed files + their SHA-256 in the W04 manifest",
        "unlocks": "a clean-checkout reviewer can reproduce every number in "
                   "operating-envelope-v1.yaml instead of trusting a declaration",
        "min_sessions": "0",
        "status_label": "NEED_USER_ACTION",
    },
)


# --------------------------------------------------------------------------
# package assembly
# --------------------------------------------------------------------------

def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def index_artifacts(repo_root: pathlib.Path) -> list[dict[str, object]]:
    """Resolve the H0-H7 index against this checkout, recording what is absent."""
    rows = []
    for entry in H_INDEX:
        artifact = entry["artifact"]
        path = repo_root.joinpath(*artifact.split("/"))
        present = path.is_file()
        present_dir = path.is_dir()
        rows.append({
            "gate": entry["gate"],
            "required": entry["required"],
            "artifact": artifact,
            "declared_state": entry["state"],
            "exists_in_this_checkout": "true" if (present or present_dir) else "false",
            "kind": "file" if present else "directory" if present_dir else "absent",
            "sha256_12": _sha256(path)[:12] if present else "",
            "bytes": str(path.stat().st_size) if present else "",
            "status_label": "REAL_DATA_ANALYZED" if present else "TEAM_DEPENDENCY",
        })
    return rows


def pass_criteria_walk(envelope_report: dict[str, object],
                       fuse: dict[str, object]) -> list[dict[str, str]]:
    """docs/05A section 17 pass criteria, answered with the evidence that exists."""
    h8 = envelope_report["sources"].get("W04-H8C-box-600s", {})
    return [
        {"criterion": "safe physical envelope known",
         "result": "NOT MET",
         "why": "the observed envelope exists (one duty level committed, the ladder "
                "local-only), but the fuse/conductor basis is missing so nothing can "
                "be called safe; see fuse-selection.md verdict NO_FREEZE"},
        {"criterion": "repeatable enough plant",
         "result": "NOT MET HERE",
         "why": "repeatability is W07's question and its evidence is not in this "
                "checkout; one 600 s capture cannot answer it"},
        {"criterion": "fuse selected",
         "result": "NOT MET",
         "why": fuse["verdict"] + f": no ampacity basis for the installed branch "
                f"(a {fuse['conductor']['core_diameter_mm']} mm core diameter, "
                f"{fuse['conductor']['installed_mm2']} mm2 if solid round) and no "
                "photographed fuse marking; the 15 A value is operator-reported "
                "only"},
        {"criterion": "no unresolved high-current anomaly",
         "result": "NOT PRE-JUDGED - CANDIDATE OPEN IN W15",
         "why": "fault_bits=0 in all "
                f"{h8.get('frames', 0)} committed frames and steady OFF current never "
                "exceeded the 0.02 A meter floor; the duty-0 frames above it are the "
                "two PZEM register-latency frames, named individually and left open by "
                "W15 between the register-holdover reading and the canonical "
                "CONTROL_ELECTRICAL_ANOMALY class (docs/01 22.4/23.4, high severity). "
                "This row does not decide that safety classification, and nothing here "
                "measures the terminals or the IBT-2 case either"},
        {"criterion": "SAFE_LOCAL physically possible",
         "result": "NOT DEMONSTRATED",
         "why": "the inputs exist (SL-01..SL-08) but the fan is unobservable, no "
                "interlock is installed, there is no wall clock and no transport, and "
                "the mode itself is Member D's"},
    ]


def build_package(repo_root: pathlib.Path, bench_root: pathlib.Path | None,
                  envelope_report: dict[str, object],
                  hot_side_report: dict[str, object]) -> dict[str, object]:
    fuse = hot_side_report["fuse_evaluation"]
    package = {
        "schema": "cg-w08-gate-a-1",
        "status_label": "REAL_DATA_ANALYZED",
        "gate": "Gate A (docs/05A section 17; docs/01 gates H0-H7)",
        "verdict": "GATE A NOT CLOSED",
        "safe_local_inputs": [row.as_row() for row in SAFE_LOCAL_INPUTS],
        "h0_h7_index": index_artifacts(repo_root),
        "requirement_matrix": requirement_matrix(envelope_report, hot_side_report),
        "pass_criteria": pass_criteria_walk(envelope_report, fuse),
        "named_gaps": named_gaps(envelope_report, hot_side_report),
        "operator_action_queue": list(W08_ACTION_QUEUE),
        "what_firmware_can_observe_vs_what_d_decides": {
            "firmware_observes": [
                "raw sensor conversions with per-channel status and age",
                "the snapshot completeness mask and the mandatory-role gate",
                "PZEM V/I/P with per-field status and age (one poll of latency)",
                "requested vs applied duty and the duty readback",
                "fault bits, stop reason and the OFF-current gate result",
            ],
            "member_d_must_supply": [
                "the numeric values of the six operating limits and their provenance",
                "the SAFE_LOCAL entry/exit rule and what protective cooling is "
                "allowed while the remote path is gone",
                "the staleness budget each input must satisfy before it may act",
                "the fault taxonomy that turns an anomaly into a lockout",
            ],
            "note": "the bench image reports limits_policy=APPROVED and "
                    "limits_enforced=1; that table belongs to a bench build and is "
                    "not the delivered firmware's, whose limits are all UNRESOLVED",
        },
    }
    text = json.dumps(package, sort_keys=True)
    if envelope.FORBIDDEN_STATUS in text:
        raise ValueError(f"{envelope.FORBIDDEN_STATUS} must never appear in a Gate A "
                         "package")
    return package


def requirement_matrix(envelope_report: dict[str, object],
                       hot_side_report: dict[str, object]) -> list[dict[str, str]]:
    fuse = hot_side_report["fuse_evaluation"]
    committed = [s for s, v in envelope_report["sources"].items()
                 if v["trust"] == "COMMITTED"]
    return [
        {"id": "A-W08-01", "ask": "safe operating envelope from W4-W7",
         "status": "REAL_DATA_ANALYZED (observed) / NOT FROZEN",
         "evidence": "operating-envelope-v1.yaml, envelope-by-duty.csv, "
                     "holdover-frames.csv, electrical-status-coverage.csv",
         "gap": "one committed duty level; the ladder is local-only; no limit is a "
                "rating"},
        {"id": "A-W08-02", "ask": "fuse finalization 10/15/20 A with rationale",
         "status": "BLOCKED_HARDWARE",
         "evidence": "fuse-selection.md (generated) + the observed currents table",
         "gap": f"no ampacity basis for the installed conductor "
                f"({fuse['conductor']['installed_mm2']} mm2 derived from a "
                f"{fuse['conductor']['core_diameter_mm']} mm core diameter under a "
                "solid-round assumption), no photographed fuse marking, canonical "
                "2 x 2.5 mm2 deviation open"},
        {"id": "A-W08-03", "ask": "hot-side sustainability long run",
         "status": "REAL_DATA_ANALYZED (three of four bullets) / NEED_USER_ACTION",
         "evidence": "thermal-sustainability.csv",
         "gap": "terminals/IBT-2 abnormal behaviour is unmeasured by any frame; no "
                "continuous rating may be claimed"},
        {"id": "A-W08-04", "ask": "SAFE_LOCAL integration support with D",
         "status": "TEAM_DEPENDENCY",
         "evidence": "safe-local-physical-inputs.csv (SL-01..SL-14)",
         "gap": "no transport, no wall clock, no fan observation, no interlock, and "
                "the mode itself belongs to D"},
        {"id": "A-W08-05", "ask": "Gate A package indexing all H0-H7 artifacts",
         "status": "IMPLEMENTED / HOST_VERIFIED",
         "evidence": "Gate-A-report.md + gate-a-artifact-index.csv",
         "gap": f"W07 evidence is not in this checkout; the H7/H8 raw sessions are "
                f"local-bench; committed captures in this run: {len(committed)}"},
    ]


def named_gaps(envelope_report: dict[str, object],
               hot_side_report: dict[str, object]) -> list[dict[str, str]]:
    fuse = hot_side_report["fuse_evaluation"]
    conductor = fuse["conductor"]
    coverage = envelope_report["status_coverage"]
    unqualified = sorted(s for s, c in coverage.items()
                         if not c["electrical_status_recorded"])
    return [
        {"gap": "no electrical validity token in the committed 600 s CSV",
         "detail": "voltage_status and current_status exist as columns but are empty "
                   "in all 957 rows; power_status, energy_status and door_status are "
                   "not columns at all. The same session's wire frames do carry "
                   "them, so the loss happened in the CSV builder.",
         "status_label": "REAL_DATA_ANALYZED",
         "sources": ", ".join(unqualified)},
        {"gap": "energy has no validity token anywhere on the bench wire",
         "detail": "no energy_wh_status token exists in any of the 957 raw frames; the "
                   "delivered production schema expects one.",
         "status_label": "REAL_DATA_ANALYZED"},
        {"gap": "driver enable state is commanded but never observed",
         "detail": "enable_readback=ren:0,len:0 in every frame including the 600 "
                   "driven ones, while ren_command=1 there.",
         "status_label": "REAL_DATA_ANALYZED"},
        {"gap": "fan running is not electronically observable",
         "detail": "fan_readback=NOT_ELECTRONICALLY_VERIFIED in 957/957 frames.",
         "status_label": "BLOCKED_HARDWARE"},
        {"gap": "no hardware interlock",
         "detail": "interlock_state=NOT_INSTALLED in 957/957 frames.",
         "status_label": "BLOCKED_HARDWARE"},
        {"gap": "fault-to-stop latency never measured",
         "detail": "fault_latency_us=-1 in every frame; no fault was ever injected.",
         "status_label": "NEED_USER_ACTION"},
        {"gap": "duty-0 frames with current",
         "detail": f"{len(envelope_report['duty_zero_with_current_frames'])} frames "
                   "across all sources, each listed individually in "
                   "duty-zero-current-frames.csv and excluded from both the drive and "
                   "the OFF envelope. The record names them as register-latency cases, "
                   "which is an explanation and not a classification: docs/01 "
                   "22.4/23.4 make a commanded-OFF-with-current frame a candidate "
                   "CONTROL_ELECTRICAL_ANOMALY (high severity), and W15 leaves that "
                   "option open. For device_ms=826894 the applied duty stayed 0 while "
                   "the PZEM-reported reading decayed 7.15 -> 0.56 -> 0.02 -> 0.0 A, "
                   "reaching zero at device_ms=829894, so the decay weakens "
                   "sustained-energization and supports register/transition lag - but "
                   "that trace is the meter's own report with no independent instrument "
                   "behind it, so measured value and verified physical current stay "
                   "apart and the safety qualification is open.",
         "status_label": "REAL_DATA_ANALYZED"},
        {"gap": "no continuous rating for the TEC",
         "detail": "the 55 C hot-side ceiling was provisional; the SKU continuous "
                   "rating is unestablished, so 'margin to 55 C' is not headroom.",
         "status_label": "NEED_USER_ACTION"},
        {"gap": "conductor deviation open",
         "detail": f"the record's \"1.75\" is the copper core diameter in mm (unit "
                   f"error corrected by the operator 2026-11-02), i.e. "
                   f"{conductor['installed_mm2']} mm2 if the core is round solid - a "
                   f"~{conductor['area_gap_vs_canonical_pct']} % gap to the canonical "
                   "2 x 2.5 mm2 ask rather than ~30 %, and inside the FDD2-250 "
                   "1.5-2.5 mm2 termination rating. The assumption is stated, not "
                   "proven: no marking was photographed, so no nominal 2.5 mm2 "
                   "compliance is claimed and HW-19 stays UNVERIFIED.",
         "status_label": "TEAM_DEPENDENCY"},
    ]


# --------------------------------------------------------------------------
# renderers
# --------------------------------------------------------------------------

def _csv_escape(value: str) -> str:
    if any(character in value for character in (",", '"', "\n")):
        return '"' + value.replace('"', '""') + '"'
    return value


def _fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


SAFE_LOCAL_COLUMNS = [
    "input_id", "physical_input", "why_safe_local_needs_it", "firmware_can_observe",
    "delivered_schema_field", "bench_wire_field", "committed_capture_field",
    "authentic_data", "validity_condition", "recorded_unqualified", "gap", "owner",
    "status_label",
]

INDEX_COLUMNS = ["gate", "required", "artifact", "declared_state",
                 "exists_in_this_checkout", "kind", "sha256_12", "bytes",
                 "status_label"]

QUEUE_COLUMNS = ["queue_id", "requirement", "action", "power_state",
                 "existing_evidence", "safety_prerequisites", "expected_capture",
                 "unlocks", "min_sessions", "status_label"]


def _render_csv(columns: list[str], rows: list[dict[str, object]]) -> str:
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(_csv_escape(_fmt(row.get(column))) for column in columns))
    return "\n".join(lines) + "\n"


def render_safe_local_csv(package: dict[str, object]) -> str:
    return _render_csv(SAFE_LOCAL_COLUMNS, package["safe_local_inputs"])


def render_index_csv(package: dict[str, object]) -> str:
    return _render_csv(INDEX_COLUMNS, package["h0_h7_index"])


def render_queue_csv(package: dict[str, object]) -> str:
    return _render_csv(QUEUE_COLUMNS, package["operator_action_queue"])


def render_gate_a_report(package: dict[str, object]) -> str:
    lines = [
        "# Gate A report - W08 physical characterization and SAFE_LOCAL support",
        "",
        "Generated by `firmware/tools/cg_w08_gate_a.py` through",
        "`evidence/A/W08/build_w08_artifacts.py`. **Every** statement below is one of",
        "an observation over recorded bytes, a declared dependency, or a named gap.",
        "No line is `PHYSICALLY_VERIFIED`; nothing here authorizes energizing the",
        "branch, and the produced verdict is `GATE A NOT CLOSED`.",
        "",
        "## 1. Requirement matrix (docs/05A section 17)",
        "",
        "| ID | Canonical ask | Status | Evidence | Gap |",
        "|---|---|---|---|---|",
    ]
    for row in package["requirement_matrix"]:
        lines.append(f"| **{row['id']}** | {row['ask']} | {row['status']} | "
                     f"{row['evidence']} | {row['gap']} |")
    lines += [
        "",
        "## 2. Pass-criteria walk",
        "",
        "| Criterion | Result | Why |",
        "|---|---|---|",
    ]
    for row in package["pass_criteria"]:
        lines.append(f"| {row['criterion']} | {row['result']} | {row['why']} |")
    lines += [
        "",
        "## 3. Index of H0-H7 artifacts (docs/01 Gate H0 ... Gate H7)",
        "",
        "Curated list, resolved against this checkout. `exists_in_this_checkout`",
        "false is a finding, not a formatting failure: those artifacts live on other",
        "branches or only in Member A's local bench tree.",
        "",
        "| Gate | Required | Artifact | In this checkout | SHA-256 (12) |",
        "|---|---|---|---|---|",
    ]
    for row in package["h0_h7_index"]:
        lines.append(f"| {row['gate']} | {row['required']} | `{row['artifact']}` | "
                     f"{row['exists_in_this_checkout']} | {row['sha256_12'] or '-'} |")
    lines += [
        "",
        "## 4. SAFE_LOCAL physical inputs (A-W08-04)",
        "",
        "What firmware can observe, what must come from Member D's policy, and what",
        "no recorded field measures at all. Full machine-readable table:",
        "`safe-local-physical-inputs.csv`.",
        "",
        "| ID | Input | Firmware can observe | Recorded validity | Gap |",
        "|---|---|---|---|---|",
    ]
    for row in package["safe_local_inputs"]:
        lines.append(f"| {row['input_id']} | {row['physical_input']} | "
                     f"{row['firmware_can_observe']} | "
                     f"{'UNQUALIFIED' if str(row['recorded_unqualified']).startswith('true') else str(row['recorded_unqualified'])} | "
                     f"{row['gap']} |")
    split = package["what_firmware_can_observe_vs_what_d_decides"]
    lines += [
        "",
        "### 4.1 The split, stated plainly",
        "",
        "**Firmware observes:**",
    ]
    lines += [f"* {item}" for item in split["firmware_observes"]]
    lines += ["", "**Member D must supply:**"]
    lines += [f"* {item}" for item in split["member_d_must_supply"]]
    lines += [
        "",
        f"> {split['note']}",
        "",
        "## 5. Named gaps",
        "",
        "| Gap | Detail | Status |",
        "|---|---|---|",
    ]
    for row in package["named_gaps"]:
        lines.append(f"| {row['gap']} | {row['detail']} | {row['status_label']} |")
    lines += [
        "",
        "## 6. Operator action queue (W08 half; the W15 half is in evidence/A/W15)",
        "",
        "Merged to the minimum number of supervised sessions without dropping any",
        "required repetition. The unpowered inspection (OQ-W08-1) is **necessary, not",
        "sufficient**: it produces the conductor and fuse markings, and it does not by",
        "itself clear any energized-session gate - the open CONTROL_ELECTRICAL_ANOMALY",
        "classification of the duty-0 frame and Member D's unresolved thresholds gate",
        "those sessions too, and neither is answered by a photo.",
        "",
        "| Queue | Requirement | Action | Power state | Unlocks | Sessions |",
        "|---|---|---|---|---|---|",
    ]
    for row in package["operator_action_queue"]:
        lines.append(f"| {row['queue_id']} | {row['requirement']} | {row['action']} | "
                     f"{row['power_state']} | {row['unlocks']} | "
                     f"{row['min_sessions']} |")
    lines += [
        "",
        "## 7. What this package refuses to say",
        "",
        "* it does not certify the envelope as safe (fuse/conductor basis missing);",
        "* it does not claim a continuous TEC rating, and 55 C is quoted only as the",
        "  provisional working ceiling the bench sessions were run against;",
        "* it does not claim a device received a command, that the branch may be",
        "  energized, or that SAFE_LOCAL works - there is no transport and no mode;",
        "* it does not average TEC_HOT_SIDE into any chamber statistic, and no frame",
        "  proves which physical probe is which beyond the operator-frozen as-built",
        "  record;",
        "* every electrical figure from the committed CSV is published as a value",
        "  with **no recorded validity** (`electrical_status_recorded: false`);",
        "* it does not decide the duty-0-with-current classification, and it does not",
        "  treat the PZEM's own decaying trace as proof the branch was unenergized -",
        "  a measured value and a verified physical current are different claims, and",
        "  no independent instrument stands behind any figure here;",
        "* it does not read the corrected conductor figure as compliance: ~2.405 mm2",
        "  holds only if the core is round solid, and no marking was photographed;",
        "* it does not treat a shop listing or catalogue entry as evidence about the",
        "  installed fuse body, whose marking has never been read;",
        "* it does not claim that the unpowered inspection clears an energized-session",
        "  gate.",
        "",
        "Verdict: **" + package["verdict"] + "**",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=pathlib.Path, default=REPO_ROOT)
    parser.add_argument("--bench-root", type=pathlib.Path, default=envelope.DEFAULT_BENCH_ROOT)
    parser.add_argument("--no-local", action="store_true")
    parser.add_argument("--json", type=pathlib.Path)
    args = parser.parse_args(argv)

    bench = None if args.no_local else args.bench_root
    env_report = envelope.build_envelope(args.repo_root, bench)
    import cg_w08_hot_side as hot_side
    hot_report = {
        "fuse_evaluation": hot_side.fuse_evaluation(
            hot_side.observed_currents(args.repo_root, bench)),
    }
    package = build_package(args.repo_root, bench, env_report, hot_report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8", newline="\n")
        print(f"wrote {args.json}")
    present = sum(1 for r in package["h0_h7_index"]
                  if r["exists_in_this_checkout"] == "true")
    print(f"H0-H7 index entries resolved in this checkout: {present}/"
          f"{len(package['h0_h7_index'])}")
    print(f"SAFE_LOCAL input rows: {len(package['safe_local_inputs'])}")
    print(f"named gaps: {len(package['named_gaps'])}")
    print(f"operator queue items: {len(package['operator_action_queue'])}")
    print(f"verdict: {package['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
