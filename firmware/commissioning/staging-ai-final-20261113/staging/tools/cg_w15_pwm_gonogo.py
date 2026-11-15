"""W15 A-W15-04 - the METHOD for the PWM characterization go/no-go decision.

    py firmware/tools/cg_w15_pwm_gonogo.py [--json OUT.json]

`docs/05A` section 24 asks, for the optional energy-aware duty control: test a
few limited safe duty points, check IBT-2 response, PZEM power behaviour and
thermal behaviour, then decide **GO** or **NO-GO** ("no shame in NO-GO").

This module delivers the **methodology**, not the decision. On the current tree
the decision is unmakeable, and this file says exactly why in machine-readable
form: every threshold that would decide it is an `UNRESOLVED` parameter owned by
Member D (`firmware/main/cg_tec_limits.h`: all six operating limits ship
`UNRESOLVED`, and `cg_tec_limits_all_resolved()` gates `cg_tec_start()`), the
production build has its output stage compiled out, and `docs/01` section 48
makes "PZEM PWM semantics" a proof obligation that only a characterization run
can discharge.

Design commitments of the method, in order:

1. **Safety preconditions before any criterion.** A duty point is only admissible
   if the fail-closed contract, the supervised-authorization chain, the
   off-current gate and the resolved limits are all in force first. No
   precondition may be satisfied by a host-side number.
2. **Criteria are named parameters, not vibes.** Each one carries its symbol,
   its owner, its required evidence type and its current state
   (`UNRESOLVED`), so a reviewer can see what is missing rather than being
   handed an invented number.
3. **Measurements are defined by the field that produces them**, including the
   latency rule: the first frame of a driven block and the first two frames after
   the applied duty reaches 0 are register artefacts and are excluded and listed.
4. **Repetition and randomization are part of the method**, because a single
   60 s dwell per duty point - which is all the existing ladder provides, and in
   two different wiring regimes - cannot support a characterization claim.
5. **NO-GO is a legitimate, fully-supported outcome.** The optional work stays
   optional; the core gates do not depend on it.

`decide()` therefore returns `NOT_DECIDED` on this tree and refuses to emit
`GO` while any threshold is unresolved. `PHYSICALLY_VERIFIED` never appears.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]

UNRESOLVED = "UNRESOLVED"
DECISION_VOCABULARY = ("GO", "NO-GO", "NOT_DECIDED")
CURRENT_DECISION = "NOT_DECIDED"

# The canonical limit symbols, named exactly as firmware/main/cg_tec_limits.h
# names them (the enum order), with the field token the shipped table uses and
# the provenance token that explains WHY it is unresolved. The delivered table
# has six entries (CG_LIMIT_COUNT); docs/06 speaks of seven - that discrepancy
# is an open review item and is not silently reconciled here.
LIMITS: tuple[dict[str, str], ...] = (
    {"symbol": "CG_LIMIT_CURRENT_MAX_A", "field": "current_max_a", "unit": "A",
     "provenance_token": "TEC_CONTINUOUS_RATING_NOT_ESTABLISHED",
     "owner": "D (value) / A (evidence)",
     "evidence_required": "continuous-load current versus duty and voltage on the "
                          "real TEC, with wire/connector/IBT-2 thermal behaviour",
     "state": UNRESOLVED},
    {"symbol": "CG_LIMIT_VOLTAGE_MAX_V", "field": "voltage_max_v", "unit": "V",
     "provenance_token": "TEC_VMAX_NOT_ESTABLISHED",
     "owner": "D / A",
     "evidence_required": "the SKU Vmax for the exact purchased TEC1-12715 (docs/01 "
                          "section 13.2 forbids inferring it from the part number)",
     "state": UNRESOLVED},
    {"symbol": "CG_LIMIT_VOLTAGE_MIN_V", "field": "voltage_min_v", "unit": "V",
     "provenance_token": "PSU_LOAD_REGULATION_NOT_MEASURED",
     "owner": "D / A",
     "evidence_required": "loaded branch voltage across the duty points versus the "
                          "PSU regulation setpoint (observed 11.75-11.81 V at 100 %)",
     "state": UNRESOLVED},
    {"symbol": "CG_LIMIT_HOT_SIDE_MAX_C", "field": "hot_side_max_c", "unit": "C",
     "provenance_token": "HOT_SIDE_LIMIT_NOT_ESTABLISHED",
     "owner": "D / A",
     "evidence_required": "hot-side plateau plus the SKU limit; the 55 C ceiling used "
                          "on the bench was PROVISIONAL and is not a rating",
     "state": UNRESOLVED},
    {"symbol": "CG_LIMIT_DUTY_MAX_PERMILLE", "field": "duty_max_permille",
     "unit": "permille",
     "provenance_token": "DUTY_NOT_CHARACTERISED",
     "owner": "D",
     "evidence_required": "the duty ceiling the plant may be commanded to, which the "
                          "characterization is supposed to inform",
     "state": UNRESOLVED},
    {"symbol": "CG_LIMIT_ON_TIME_MAX_MS", "field": "on_time_max_ms", "unit": "ms",
     "provenance_token": "ON_TIME_NOT_CHARACTERISED",
     "owner": "D",
     "evidence_required": "maximum continuous on-time before a mandatory rest, which "
                          "needs a thermal asymptote plus component-temperature data",
     "state": UNRESOLVED},
)

# The criteria the decision rests on. Each is a parameter, not a number.
CRITERIA: tuple[dict[str, str], ...] = (
    {
        "criterion_id": "PWM-C1",
        "name": "IBT-2 responds to the commanded duty within tolerance",
        "parameter": "duty_readback_tolerance_permille",
        "state": UNRESOLVED,
        "measurement": "pwm_applied_permille versus pwm_readback_permille on every "
                       "frame, plus enable readback",
        "known_defect_to_handle": "enable_readback reports ren:0,len:0 in all 957 "
                                  "committed frames even while ren_command=1, so the "
                                  "driver enable state cannot be OBSERVED, only "
                                  "commanded; the method must not treat a matched "
                                  "duty number as proof the bridge switched",
        "owner": "A",
    },
    {
        "criterion_id": "PWM-C2",
        "name": "PZEM power behaviour is monotonic and interpretable at partial duty",
        "parameter": "power_per_duty_slope_tolerance",
        "state": UNRESOLVED,
        "measurement": "median current and median power per duty level, with the "
                       "latency frames excluded, over >= 3 repetitions per point",
        "known_defect_to_handle": "the PZEM integrates over its own cycle, so a "
                                  "PWM-fed branch's 'power' is a mean whose semantics "
                                  "versus duty are exactly what docs/01 section 48 "
                                  "requires characterization to establish",
        "owner": "A / B",
    },
    {
        "criterion_id": "PWM-C3",
        "name": "thermal behaviour stays inside the resolved hot-side limit with margin",
        "parameter": "hot_side_margin_k",
        "state": UNRESOLVED,
        "measurement": "TEC_HOT_SIDE (as-built T2) plateau per duty point, plus "
                       "chamber response, never averaged across roles",
        "known_defect_to_handle": "no continuous rating exists, the 55 C ceiling was "
                                  "provisional, and no cold-side/junction channel "
                                  "exists in any capture",
        "owner": "A / D",
    },
    {
        "criterion_id": "PWM-C4",
        "name": "component temperatures (terminals, IBT-2 case, conductor) stay "
                "inside their ratings at every duty point",
        "parameter": "component_temp_max_c",
        "state": UNRESOLVED,
        "measurement": "touch-free temperature at fixed checkpoints during the dwell",
        "known_defect_to_handle": "nothing in any recorded frame measures this; it is "
                                  "the same gap that keeps A-W08-03 open",
        "owner": "operator (measurement) / A (record) / D (limit)",
    },
    {
        "criterion_id": "PWM-C5",
        "name": "energy feature is worth its resolution cost",
        "parameter": "energy_resolution_floor_wh",
        "state": UNRESOLVED,
        "measurement": "energy_wh counter steps per dwell against the dwell length",
        "known_defect_to_handle": "the counter is 1 Wh quantised and carries no "
                                  "validity token at all; at ~85 W it updates about "
                                  "every 42 s, so a short dwell gives it nothing to "
                                  "resolve",
        "owner": "B (feature) / A (producer)",
    },
    {
        "criterion_id": "PWM-C6",
        "name": "fuse/conductor coordination survives the duty points actually used",
        "parameter": "fuse_coordination_verdict",
        "state": UNRESOLVED,
        "measurement": "observed peak and sustained current per point against the "
                       "installed conductor's ampacity basis",
        "known_defect_to_handle": "W08 returns NO_FREEZE: the installed branch has no "
                                  "recorded ampacity basis (a 1.75 mm core diameter is "
                                  "~2.405 mm2 only if it is round solid) and the fuse "
                                  "marking was never photographed, the 15 A being "
                                  "operator-reported only",
        "owner": "operator / A / D",
    },
)

# Safety preconditions: ALL of them must hold before a single duty point is
# commanded. They are stated as checks, and the current tree fails several.
PRECONDITIONS: tuple[dict[str, str], ...] = (
    {"id": "PWM-P1", "precondition": "the six (or seven, see the open review item) "
                                     "operating limits resolved and operator-approved "
                                     "in the build under test",
     "current_state": "FAIL - all UNRESOLVED in cg_tec_limits.h; START returns "
                      "START_LIMITS_UNRESOLVED",
     "owner": "D"},
    {"id": "PWM-P2", "precondition": "output stage actually compiled in and the board "
                                     "flashed with that image",
     "current_state": "FAIL by design on the delivered branch: coldguard_config.h "
                      "compiles the stage out and requested duty is 0; the bench "
                      "images that did drive are not this build",
     "owner": "A"},
    {"id": "PWM-P3", "precondition": "attended bench, operator at the PSU, explicit "
                                     "per-stage authorization, stop on zero or abnormal "
                                     "current",
     "current_state": "requires the operator; was honoured in every recorded session",
     "owner": "operator"},
    {"id": "PWM-P4", "precondition": "conductor and fuse basis decided (W08 A-W08-02)",
     "current_state": "FAIL - NO_FREEZE; no ampacity basis for the installed conductor "
                      "(1.75 mm core diameter, ~2.405 mm2 if round solid - a ~4 % area "
                      "gap to canonical, not a compliance claim), the canonical "
                      "2 x 2.5 mm2 deviation is open and the 15 A fuse value is "
                      "operator-reported with nothing legible on the body",
     "owner": "operator / A"},
    {"id": "PWM-P5", "precondition": "independent over-temperature path (hardware "
                                     "interlock) installed",
     "current_state": "FAIL - interlock_state=NOT_INSTALLED in 957/957 recorded frames",
     "owner": "operator / A"},
    {"id": "PWM-P6", "precondition": "off-current gate and duty-readback match enforced "
                                     "before and after every dwell",
     "current_state": "available: the bench image publishes off_current_limit_a=0.200 "
                      "and off_verify=PASS, and readback matched applied in every "
                      "recorded frame",
     "owner": "A"},
    {"id": "PWM-P7", "precondition": "PSU continuous rating confirmed for the longest "
                                     "planned dwell",
     "current_state": "OPEN - the endurance report flags the PSU continuous-rating "
                      "check as a precondition; 12 V / 400 W label is SOURCE VERIFIED, "
                      "not a derating statement",
     "owner": "operator"},
    {"id": "PWM-P8", "precondition": "hot-side ceiling replaced by a rated value, not "
                                     "the provisional working number",
     "current_state": "FAIL - 55 C is provisional and no continuous rating exists",
     "owner": "D / A"},
    {"id": "PWM-P9", "precondition": "fan running observable, or hot-side heat "
                                     "rejection verified another way",
     "current_state": "FAIL - fan_readback=NOT_ELECTRONICALLY_VERIFIED in 957/957 "
                      "frames; the only fan evidence is operator confirmation",
     "owner": "A"},
)

# The measurement plan, so the method is executable rather than rhetorical.
MEASUREMENT_PLAN: tuple[dict[str, object], ...] = (
    {"step": "Duty point set",
     "method": "start from the points the plant already has data for, then fill the "
               "gaps: committed 999 permille and the H6 100 permille point exist in "
               "git; the 200-900 ladder exists only in the local bench tree and in "
               "two different wiring regimes, so it is not one ladder",
     "why": "docs/05A says 'test limited safe duty points' - limited means the "
            "smallest set that spans the regime, and 'safe' is decided after P1-P9"},
    {"step": "Repetition",
     "method": "at least three dwells per duty point, randomized order, with a rest "
               "interval long enough for the hot side to return to its starting "
               "window; the rest interval is itself a parameter to be recorded, not "
               "assumed",
     "why": "the existing ladder is one 60 s dwell per point, which cannot separate "
            "duty effect from start-up transient"},
    {"step": "Dwell length",
     "method": "long enough for the hot-side plateau criterion (drift per minute "
               "below a stated floor) rather than a fixed 60 s; the plateau rule "
               "already used in cg_w08_hot_side.py is the shape of such a criterion",
     "why": "a 60 s dwell never reached a thermal steady state at 100 % duty (H8-A "
            "was still warming at 1.46 K/min after 178 s)"},
    {"step": "Per-frame exclusions",
     "method": "drop and list the first frame of every driven block and the first two "
               "frames after the applied duty reaches zero (the documented register "
               "latency), keep every excluded frame in the artifact",
     "why": "one duty-0 frame at 7.15 A otherwise enters an OFF average as if it were "
            "a measurement"},
    {"step": "Recorded fields per dwell",
     "method": "pwm_req/applied/readback, voltage/current/power/energy with their "
               "status and age tokens, T1/T2/T3/T4 with roles, door, fan, "
               "fault_bits, stop_reason, off_verify, boot_id, run_id, and the touch-"
               "free component temperatures at fixed checkpoints",
     "why": "the ablation feature set and the safety argument need the same frame, and "
            "the age tokens are what makes the values usable later"},
    {"step": "Failure criteria (all named parameters, none invented)",
     "method": "collapse of current at a commanded nonzero duty; any frame above the "
               "resolved hot-side limit; off-current gate failure at stop; any "
               "fault_bits nonzero; any component above its stated rating; energy "
               "counter inconsistent with the power integral beyond its quantum",
     "why": "a NO-GO must be provable from the capture, not argued from a feeling"},
    {"step": "Decision rule",
     "method": "GO only if every precondition holds, every criterion's parameter has "
               "a resolved value with cited provenance, and the collected dwells "
               "satisfy those parameters. Otherwise NO-GO (the evidence says stop) or "
               "NOT_DECIDED (the parameters do not exist yet).",
     "why": "these are different outcomes and must not be merged"},
)

W15_ACTION_QUEUE: tuple[dict[str, str], ...] = (
    {
        "queue_id": "OQ-W15-1",
        "requirement": "A-W15-01",
        "action": "No hardware. Commit the H7/H8 raw captures (or a W08-style export "
                  "that keeps the status and age tokens) so the electrical producer "
                  "can be audited from a clean checkout.",
        "power_state": "none",
        "existing_evidence": "the audit ran against Member A's local bench tree and "
                             "the committed 957-row CSV; the CSV lost the tokens",
        "safety_prerequisites": "none",
        "expected_capture": "files + SHA-256 pins in the W04/W08 manifest",
        "unlocks": "reproducible pzem-quality numbers for reviewers instead of a "
                   "declared table",
        "min_sessions": "0",
        "status_label": "NEED_USER_ACTION",
    },
    {
        "queue_id": "OQ-W15-2",
        "requirement": "A-W15-03",
        "action": "Reference-meter session: with the branch energized at a small set "
                  "of dwell-stable duty points, read a trusted independent meter "
                  "alongside the PZEM at each point (current, voltage, power).",
        "power_state": "energized, attended, one duty point at a time",
        "existing_evidence": "none - no calibration record exists for the PZEM or the "
                             "50 A / 75 mV shunt; consistency (V x I, energy integral) "
                             "is all A-W15-03 can report today",
        "safety_prerequisites": "same as a characterization dwell: supervised, limits "
                                "resolved, off-current gate at stop, touch-free "
                                "component temperatures",
        "expected_capture": "one paired reading per point plus meter model/serial",
        "unlocks": "a calibration statement instead of plausibility, and it discharges "
                   "the docs/01 section 48 'PZEM PWM semantics' obligation together "
                   "with OQ-W15-3",
        "min_sessions": "1 (merge with OQ-W15-3: the same dwells serve both, so no "
                        "extra energized session is needed)",
        "status_label": "NEED_USER_ACTION",
    },
    {
        "queue_id": "OQ-W15-3",
        "requirement": "A-W15-04",
        "action": "PWM characterization campaign on the limited safe duty set: "
                  ">= 3 randomized dwells per point with rest intervals, recording "
                  "IBT-2 duty readback, V/I/P/E with tokens, all four thermal "
                  "channels, and touch-free terminal/IBT-2/conductor temperatures.",
        "power_state": "energized, attended, per-stage authorization",
        "existing_evidence": "the 20-100 % ladder exists but as a single 60 s dwell "
                             "per point in two wiring regimes; a 1800 s dwell exists "
                             "at 100 % only",
        "safety_prerequisites": "PWM-P1..PWM-P9 all satisfied first - limits resolved, "
                                "output stage real, interlock installed or an explicit "
                                "accepted risk, fuse/conductor decision, PSU continuous "
                                "rating, fan observation or verified heat rejection",
        "expected_capture": "one capture per dwell with boot_id/run_id, plus the "
                            "component temperature log",
        "unlocks": "the GO/NO-GO decision itself, three of the six unresolved limits, "
                   "and the energy-aware control option (RQ6)",
        "min_sessions": "1 supervised bench day, merged with OQ-W15-2 and with "
                        "OQ-W08-2's long run; repetitions stay per point",
        "status_label": "BLOCKED_HARDWARE",
    },
    {
        "queue_id": "OQ-W15-4",
        "requirement": "A-W15-02",
        "action": "Hand `a3-run-index.csv` to Member B and agree which runs enter the "
                  "electrical ablation; no new capture is needed for the 600 s case.",
        "power_state": "none",
        "existing_evidence": "19 of 23 audited sessions carry command + applied + "
                             "V/I/P + a thermal field; 1 of them is committed in git",
        "safety_prerequisites": "none",
        "expected_capture": "an agreed run list in the W15 record",
        "unlocks": "B's ablation design without another energized run",
        "min_sessions": "0",
        "status_label": "TEAM_DEPENDENCY",
    },
)


# --------------------------------------------------------------------------
# the decision object
# --------------------------------------------------------------------------

def evaluate_thresholds() -> dict[str, object]:
    unresolved = [c["parameter"] for c in CRITERIA if c["state"] == UNRESOLVED]
    failed_preconditions = [
        p["id"] for p in PRECONDITIONS
        if p["current_state"].startswith(("FAIL", "OPEN"))
    ]
    return {
        "unresolved_criteria_parameters": unresolved,
        "criteria_total": len(CRITERIA),
        "criteria_resolved": len(CRITERIA) - len(unresolved),
        "limits_unresolved": [limit["symbol"] for limit in LIMITS],
        "failed_or_open_preconditions": failed_preconditions,
        "preconditions_total": len(PRECONDITIONS),
    }


def decide(thresholds: dict[str, object] | None = None) -> dict[str, object]:
    """Return the decision this tree can honestly support. It is not GO."""
    thresholds = thresholds or evaluate_thresholds()
    blocking = []
    if thresholds["criteria_resolved"] != thresholds["criteria_total"]:
        blocking.append(
            f"{thresholds['criteria_total'] - thresholds['criteria_resolved']} of "
            f"{thresholds['criteria_total']} decision parameters are still "
            f"{UNRESOLVED}: "
            f"{', '.join(thresholds['unresolved_criteria_parameters'])}")
    if thresholds["failed_or_open_preconditions"]:
        blocking.append(
            "safety preconditions not satisfied: "
            + ", ".join(thresholds["failed_or_open_preconditions"]))
    blocking.append(
        "the delivered build cannot actuate at all (output stage compiled out, "
        "requested duty 0, actuator enable disallowed), so no criterion can be "
        "measured on it")
    decision = "NOT_DECIDED" if blocking else "NO-GO"
    if decision == "GO":  # pragma: no cover - unreachable by construction
        raise AssertionError("a GO decision must be impossible while blockers exist")
    return {
        "requirement": "A-W15-04 PWM Go/No-Go (docs/05A section 24)",
        "decision": decision,
        "decision_vocabulary": list(DECISION_VOCABULARY),
        "why_not_go": blocking,
        "no_shame_clause": "docs/05A: 'No shame in NO-GO.' The energy-aware duty "
                           "control is optional work; the core gates do not depend on "
                           "it, and NOT_DECIDED is recorded as a defect of the "
                           "parameter set, not of the plant.",
        "what_this_file_is": "the METHODOLOGY. It deliberately does not decide Go, and "
                             "it does not invent a threshold to make itself decidable.",
        "thresholds": thresholds,
        "status_label": "BLOCKED_HARDWARE",
    }


# --------------------------------------------------------------------------
# renderers
# --------------------------------------------------------------------------

def _csv_escape(value: str) -> str:
    if any(character in value for character in (",", '"', "\n")):
        return '"' + value.replace('"', '""') + '"'
    return value


def render_criteria_csv() -> str:
    columns = ["criterion_id", "name", "parameter", "state", "measurement",
               "known_defect_to_handle", "owner"]
    lines = [",".join(columns)]
    for row in CRITERIA:
        lines.append(",".join(_csv_escape(str(row[c])) for c in columns))
    return "\n".join(lines) + "\n"


def render_preconditions_csv() -> str:
    columns = ["id", "precondition", "current_state", "owner"]
    lines = [",".join(columns)]
    for row in PRECONDITIONS:
        lines.append(",".join(_csv_escape(str(row[c])) for c in columns))
    return "\n".join(lines) + "\n"


def render_limits_csv() -> str:
    columns = ["symbol", "field", "unit", "provenance_token", "owner",
               "evidence_required", "state"]
    lines = [",".join(columns)]
    for row in LIMITS:
        lines.append(",".join(_csv_escape(str(row[c])) for c in columns))
    return "\n".join(lines) + "\n"


QUEUE_COLUMNS = ["queue_id", "requirement", "action", "power_state",
                 "existing_evidence", "safety_prerequisites", "expected_capture",
                 "unlocks", "min_sessions", "status_label"]


def render_queue_csv(queue: tuple[dict[str, str], ...] = W15_ACTION_QUEUE) -> str:
    lines = [",".join(QUEUE_COLUMNS)]
    for row in queue:
        lines.append(",".join(_csv_escape(str(row[c])) for c in QUEUE_COLUMNS))
    return "\n".join(lines) + "\n"


def render_pwm_md(decision: dict[str, object]) -> str:
    lines = [
        "# A-W15-04 - PWM characterization go/no-go: the METHOD (decision: NOT_DECIDED)",
        "",
        "Generated by `firmware/tools/cg_w15_pwm_gonogo.py` through",
        "`evidence/A/W15/build_w15_artifacts.py`. Status label: **BLOCKED_HARDWARE**.",
        "",
        "**This document does not decide GO.** On the current tree the decision is",
        "not makeable, and pretending otherwise would mean inventing a threshold -",
        "which is the specific failure `docs/05A` A-W08-02 warns about ('do not",
        "improvise silently'). It is the method, the named parameters, the safety",
        "preconditions and the blockers, in a form a reviewer can execute later.",
        "",
        "## 1. Decision",
        "",
        f"* decision: **{decision['decision']}** (vocabulary "
        f"{', '.join(decision['decision_vocabulary'])})",
        f"* why not GO: {'; '.join(decision['why_not_go'])}",
        f"* {decision['no_shame_clause']}",
        "",
        "## 2. The parameters a decision needs",
        "",
        "| Criterion | Parameter | State | Measurement | Known defect to handle | Owner |",
        "|---|---|---|---|---|---|",
    ]
    for row in CRITERIA:
        lines.append(f"| **{row['criterion_id']}** {row['name']} | "
                     f"`{row['parameter']}` | {row['state']} | {row['measurement']} | "
                     f"{row['known_defect_to_handle']} | {row['owner']} |")
    lines += [
        "",
        "## 3. The firmware limits those parameters hang on",
        "",
        "Named from `firmware/main/cg_tec_limits.h` / `cg_tec_limits.c`; the shipped",
        "table's own provenance token is quoted verbatim.",
        "",
        "| Symbol | Field | Unit | Shipped provenance | State | Evidence required | Owner |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in LIMITS:
        lines.append(f"| `{row['symbol']}` | `{row['field']}` | {row['unit']} | "
                     f"`{row['provenance_token']}` | {row['state']} | "
                     f"{row['evidence_required']} | {row['owner']} |")
    lines += [
        "",
        "`cg_tec_limits_all_resolved()` gates `cg_tec_start()`, so this build refuses",
        "to start regardless of intent. The six-versus-seven limit count between",
        "`cg_tec_limits.h` and `docs/06` is an open contract item and is not",
        "reconciled here.",
        "",
        "## 4. Safety preconditions (all must hold before any duty point)",
        "",
        "| ID | Precondition | Current state | Owner |",
        "|---|---|---|---|",
    ]
    for row in PRECONDITIONS:
        lines.append(f"| {row['id']} | {row['precondition']} | {row['current_state']} | "
                     f"{row['owner']} |")
    lines += [
        "",
        "## 5. Measurement plan",
        "",
    ]
    for step in MEASUREMENT_PLAN:
        lines += [
            f"### {step['step']}",
            "",
            f"* method: {step['method']}",
            f"* why: {step['why']}",
            "",
        ]
    lines += [
        "## 6. What the existing captures already say about partial duty",
        "",
        "They say less than a characterization needs, and the honest list is short:",
        "",
        "* one committed 100 per mille point at 60 s (H6, 0.96 A median, 11.2 W",
        "  median) and one committed 999 per mille point at 600 s (H8-C, 7.16 A",
        "  median, 84.4 W median, 9.99 A peak) - **the only two duty levels with",
        "  electrical data inside git**;",
        "* a 200-1000 per mille ladder in Member A's local bench tree, one 60 s dwell",
        "  per point, split across two wiring regimes (20-60 % through a degraded",
        "  return path at ~0.268 ohm, 70-100 % after its replacement at ~0.019-0.021",
        "  ohm): 600 per mille drew 4.33 A before and 5.41 A after the fix, so the two",
        "  halves are not one curve and were never pooled here;",
        "* duty readback matched applied in every recorded frame (600/600 driven,",
        "  357/357 idle) - the one part of the IBT-2 response that is actually",
        "  observable;",
        "* no repeated dwell at any duty level, no randomized order, no component",
        "  temperatures, no fan observation, and a PZEM counter too coarse (1 Wh) to",
        "  resolve short dwells.",
        "",
        "Consequence: the electrical-versus-duty relation in the local ladder looks",
        "smooth and monotone, which is a reason to *expect* the characterization to be",
        "informative, and not a result.",
        "",
        "## 7. Operator queue for W15 (merged with W08 where one session serves both)",
        "",
        "| Queue | Requirement | Action | Prerequisites | Unlocks | Sessions |",
        "|---|---|---|---|---|---|",
    ]
    for row in W15_ACTION_QUEUE:
        lines.append(f"| {row['queue_id']} | {row['requirement']} | {row['action']} | "
                     f"{row['safety_prerequisites']} | {row['unlocks']} | "
                     f"{row['min_sessions']} |")
    lines += [
        "",
        "## 8. Explicitly not claimed",
        "",
        "* no GO, no NO-GO, and no threshold value;",
        "* no statement that PWM control is safe, efficient, or measurable at partial",
        "  duty - the producer's semantics under PWM are the thing to be characterized;",
        "* no `PHYSICALLY_VERIFIED` label anywhere: this file reads recorded frames and",
        "  source headers, it measures nothing;",
        "* no certificate of compliance for the branch, the fuse, or the conductor.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=pathlib.Path)
    args = parser.parse_args(argv)

    thresholds = evaluate_thresholds()
    decision = decide(thresholds)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({
                "decision": decision,
                "criteria": [dict(row) for row in CRITERIA],
                "preconditions": [dict(row) for row in PRECONDITIONS],
                "limits": [dict(row) for row in LIMITS],
                "measurement_plan": [dict(row) for row in MEASUREMENT_PLAN],
                "operator_action_queue": [dict(row) for row in W15_ACTION_QUEUE],
            }, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
        print(f"wrote {args.json}")
    print(f"decision: {decision['decision']}")
    print(f"unresolved parameters: "
          f"{len(thresholds['unresolved_criteria_parameters'])}/{thresholds['criteria_total']}")
    print(f"failed or open preconditions: "
          f"{len(thresholds['failed_or_open_preconditions'])}/{thresholds['preconditions_total']}")
    for item in decision["why_not_go"]:
        print(f"  blocker: {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
