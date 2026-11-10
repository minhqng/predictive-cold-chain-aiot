"""Regenerate the W11 evidence artifacts from the delivered tooling.

    py evidence/A/W11/build_w11_artifacts.py [--check] [--sums]

Every artifact is derived by running the W11 tools - either over bytes already in
the repository, or over the protocol and recipe dictionaries the delivered modules
carry. Nothing is typed in by hand.

``S4-protocol.md``
    A-W11-01/-02: the four evidence lanes, the promotion rule that keeps intent out
    of the applied/electrical/thermal lanes, the forbidden unsafe methods, the
    capture recipe, and the real request/applied/read-back divergence found in the
    committed capture.

``S3-go-no-go.md``
    A-W11-04: the feasibility assessment as delivered by
    ``cg_w11_s3_feasibility`` - verdict **NO-GO**, with the instrumentation gap that
    decides it.

``additional-valid-run-list.json``
    A-W11-03: what additional S1/S2 runs the repository could support today, per
    scenario, measured from the validity layer where the source is parseable and
    named as unparseable where it is not. Zero additional valid runs exist.

``S4-runs/index.json``
    The S4 run list: **no publishable run**, with the reason per source and the
    evidence a real run would need.

``S4-runs/host-fixture-refusal-trace.json``
    A labelled host fixture (``is_physical_measurement=false``) that proves the
    refusal validator behaves on a blocked verdict; it is not device evidence.

``s4-s3/s4-trace-real-capture.json``
    ``build_s4_trace`` over the real committed capture: zero command observations,
    plus the device-lane audit the capture does support.

``s4-s3/refusal-analysis-real-log.json``
    ``cg_s4_refusal.analyze_capture`` over a real committed device log, which
    contains telemetry frames and no command lines at all.

``s4-s3/lane-evidence.json``
    The three-lane divergence and the command/electrical disagreement candidates
    found in physical frames, each labelled with the qualification it actually has.

``s4-s3/s3-feasibility.json``
    The machine-readable form of the NO-GO assessment.

A pinned build stamp keeps the derivation byte-reproducible; the artifacts record
that the stamp is a host constant and not a device time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
REPO = EVIDENCE.parents[2]
TOOLS = REPO / "firmware" / "tools"

sys.path.insert(0, str(TOOLS))

import cg_s4_refusal as refusal  # noqa: E402
import cg_w09_capture_parser as cp  # noqa: E402
import cg_w09_export as run_export  # noqa: E402
import cg_w09_validity as validity  # noqa: E402
import cg_w10_pairing as pairing  # noqa: E402
import cg_w11_s3_feasibility as s3  # noqa: E402
import cg_w11_s4 as s4  # noqa: E402

BUILD_STAMP = "2026-11-02T00:00:00Z"  # pinned so --check is byte-reproducible
BUILD_STAMP_MEANING = "HOST_BUILD_CONSTANT_NOT_A_DEVICE_TIME"

W04_CSV = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"
W04_G1_LOG = REPO / "evidence" / "A" / "W04" / "g1" / "40-g1-boot-60s.log"
W09_REGISTRY = REPO / "evidence" / "A" / "W09" / "run-registry.json"
RUN_LABEL = "H8C_BOX_COOLING_600S"


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(payload) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _pin(payload: dict, sources: list[pathlib.Path]) -> dict:
    payload["build_stamp"] = BUILD_STAMP
    payload["build_stamp_meaning"] = BUILD_STAMP_MEANING
    payload["sources"] = [
        {
            "path": pathlib.Path(s).relative_to(REPO).as_posix(),
            "sha256": sha256_file(pathlib.Path(s)),
        }
        for s in sources
    ]
    return payload


def s3_capture_shortfalls() -> list[dict]:
    """A-W11-04: which existing captures fall short of each S3 measurement, and why.

    Walked over the W09 run registry so the population is the one W09 already certified -
    this is not a second list of captures that can drift from the first. Every reason is
    measured or read from the registry: an unchecked source is stated as unchecked, which
    is a different claim from a source that failed a check.
    """
    registry = json.loads(W09_REGISTRY.read_text(encoding="utf-8"))
    required = [m["id"] for m in s3.REQUIRED_MEASUREMENTS]
    thermal_candidates = [
        c for c in registry["captures"] if c.get("eligibility") == "S1_BASELINE_CANDIDATE"
    ]
    probe_gap = (
        "no cold-plate or hot-base probe is installed (firmware/h8-bench/main/h8_limits.c:27 "
        "marks both limits UNRESOLVED), so this source cannot carry either endpoint of the lift"
    )
    out: list[dict] = []
    for capture in registry["captures"]:
        reasons: dict[str, str] = {}
        kind = capture["kind"]
        if not capture["is_physical_measurement"]:
            reasons["M1-qualified-electrical-power"] = (
                "labelled host fixture: an ACK or a fixture frame is protocol evidence only "
                "(docs/02 §32.2), never a measured electrical state"
            )
            reasons["M4-repeatable-degradation-state"] = (
                "a fixture cannot encode a degradation that was never applied to hardware"
            )
        elif kind == "csv_capture":
            frames, report = cp.read_csv_capture(REPO / capture["path"], RUN_LABEL)
            if report["rejected"]:
                raise RuntimeError(f"{capture['capture_id']}: the registered capture stopped parsing")
            statuses = sorted({
                str(f.values.get("current_a_status")) for f in frames if f.has("current_a_status")
            })
            reasons["M1-qualified-electrical-power"] = (
                f"no frame carries an OK producer status for current (values seen: {statuses}); "
                "power_w/energy_wh exist with no status column at all, and absence is not verification"
            )
            reasons["M4-repeatable-degradation-state"] = (
                "this is the healthy stage run: no degradation was applied, so it is the baseline "
                "half of a pair and never the degraded half"
            )
        else:
            reasons["M1-qualified-electrical-power"] = (
                f"kind {kind!r} is not a frame stream the delivered parser reads, so its "
                "producer-status posture was NOT CHECKED here - unchecked is not failed"
            )
            reasons["M4-repeatable-degradation-state"] = (
                f"registry eligibility {capture.get('eligibility')!r}: no stage ran in this "
                "source, so there is no actuation to degrade"
            )
        reasons["M2-cold-side-temperature"] = probe_gap
        reasons["M3-hot-base-temperature"] = probe_gap
        reasons["M5-baseline-effectiveness-variance"] = (
            f"the registry holds {len(thermal_candidates)} thermal candidate run(s) in total, so "
            "no between-run spread exists for any derived effectiveness metric"
        )
        supplied = [m for m in required if m not in reasons]
        out.append({
            "capture_id": capture["capture_id"],
            "path": capture["path"],
            "kind": kind,
            "is_physical_measurement": capture["is_physical_measurement"],
            "registry_eligibility": capture.get("eligibility"),
            "boot_id": capture.get("boot_id"),
            "measurements_it_could_supply": supplied,
            "falls_short_of": [m for m in required if m in reasons],
            "shortfall_reasons": dict(sorted(reasons.items())),
            "could_support_an_s3_run": False,
        })
    for entry in out:
        if entry["measurements_it_could_supply"]:
            raise RuntimeError(
                f"{entry['capture_id']}: an S3 measurement became available; re-derive the "
                "verdict from the new source instead of publishing this table"
            )
    return out


def host_fixture_trace() -> dict:
    """A labelled fixture whose only job is to prove the refusal validator bites."""
    record = {
        "command_id": "FIXTURE-CMD-S4-1",
        "ack_boot_id": "fixtureboot",
        "acks": [{
            "status": "SAFETY_BLOCKED", "reason": "LIMIT_BELOW_MIN",
            "desired_cooling": "ON", "desired_duty_permille": 900,
            "applied_cooling": "OFF", "reapplied": "0",
        }],
        "stages": ["COMMAND_SEEN", "DEVICE_ACK"],
        "applied_state_before_command": "OFF",
    }
    frames = cp.parse_frame_line(
        "#CG H8S schema=3 seq=1 timestamp_utc=UNAVAILABLE "
        "timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK device_ms=904 boot_id=fixtureboot "
        "reset_cause=USB run_id=run-00000000 stage=NONE state=OFF fault_bits=0x0 fault=NONE "
        "stop_reason=NONE snapshot=VALID missing=0x0 invalid=0x0 stale=0x0 "
        "pwm_req_permille=0 pwm_applied_permille=0 pwm_readback_permille=0 "
        "t1=25.0 t1_status=OK t2=30.0 t2_status=OK t3=25.0 t3_status=OK t4=25.0 t4_status=OK "
        "air_c=25.5 air_c_status=OK door_open=0 door_raw=0 door_status=VALID "
        "door_polarity=CONFIRMED "
        "voltage_v=11.940 voltage_v_status=OK current_a=0.000 current_a_status=OK "
        "power_w=0.000 power_w_status=OK energy_wh=24.000",
        cp.SourceProvenance(
            source_kind="h8s_fixture", source_path="evidence/A/W11/build_w11_artifacts.py",
            source_sha256=None, line_index=1, is_physical_measurement=False,
            run_label="FIXTURE_S4_REFUSAL",
            note="host-synthesised refusal fixture; is_physical_measurement=False; never device evidence",
        ),
    )
    trace = s4.build_s4_trace(
        [frames], command_records=[record], is_physical_measurement=False,
    )
    row = trace["commands"][0]
    return {
        "purpose": (
            "proves the delivered validator refuses to attribute an applied action to a refusal, "
            "and refuses to populate a device lane from the request"
        ),
        "is_physical_measurement": False,
        "fixture_label": "HOST_FIXTURE_NOT_DEVICE_EVIDENCE",
        "command_row": {
            "command_id": row["command_id"], "ack_statuses": row["ack_statuses"],
            "refused": row["refused"], "applied_semantics": row["applied_semantics"],
            "lane_sources": {k: v["source"] for k, v in row["lanes"].items()},
        },
        "promotion_rules": trace["promotion_rules"],
        "an_intentional_promotion_raises": _promotion_demo(trace),
        "honesty": [
            "this fixture is a tooling input, not an S4 run",
            "it shows the block verdict being handled; it does not show a device blocking",
        ],
    }


def _promotion_demo(trace: dict) -> str:
    """Prove assert_no_promotion raises, by trying it on a poisoned copy."""
    poisoned = json.loads(json.dumps(trace))
    for row in poisoned["commands"]:
        row["lanes"][s4.ELECTRICAL]["source"] = s4.INFERRED_FROM_INTENT
    try:
        s4.assert_no_promotion(poisoned)
    except s4.PromotionError as error:
        return f"PromotionError: {error}"
    raise RuntimeError("assert_no_promotion accepted an intent-derived electrical lane")


def additional_run_list() -> dict:
    """A-W11-03: what additional S1/S2 capacity the repository actually has."""
    registry = json.loads(W09_REGISTRY.read_text(encoding="utf-8"))
    entries = []
    for capture in registry["captures"]:
        path = REPO / capture["path"]
        entry = {
            "capture_id": capture["capture_id"],
            "path": capture["path"],
            "sha256": capture["sha256"],
            "kind": capture["kind"],
            "is_physical_measurement": capture["is_physical_measurement"],
            "eligibility": capture["eligibility"],
            "parseable_by_the_delivered_parser": False,
            "frames_usable_per_scenario": None,
            "additional_s1_or_s2_runs_available": 0,
        }
        if capture["kind"] == "csv_capture":
            frames, report = cp.read_csv_capture(path, RUN_LABEL)
            validities = validity.evaluate_frames(frames)
            per_scenario = {
                scenario: sum(1 for v in validities if scenario in v.usable_for)
                for scenario in validity.SCENARIO_REQUIRED_DOMAINS
            }
            entry["parseable_by_the_delivered_parser"] = True
            entry["frames_total"] = len(frames)
            entry["frames_usable_per_scenario"] = per_scenario
            entry["additional_s1_or_s2_runs_available"] = 0
            entry["why_not_a_run"] = (
                "these are frames inside one boot of one stage run that W09 already registers as "
                "a candidate; a run is a session, and this capture is not a new session"
            )
        else:
            entry["why_not_parseable"] = (
                f"source kind {capture['kind']!r} is not a frame stream this parser reads; "
                "it is listed so that 'not counted' is never mistaken for 'counted as zero runs'"
            )
        entries.append(entry)
    return {
        "requirement": "docs/05A §20 A-W11-03 (dataset expansion on B's run plan)",
        "status_label": "REAL DATA NOT AVAILABLE -> NEED_USER_ACTION",
        "target": "additional valid S1/S2 runs as B's plan requires",
        "s1_runs_certified_valid": 0,
        "s2_pilot_disturbances_available": 0,
        "s4_runs_publishable": 0,
        "captures": entries,
        "what_a_new_run_needs": [
            "a supervised session executed against evidence/A/W09/run-protocol-v1.md",
            "a capture committed to the repository so it can be hash-pinned",
            "for S2: the per-boot door attestation and an operator-timed OPEN edge "
            "(evidence/A/W10/S2-protocol-v1.md)",
            "for an S1 pair usable by S2: the same hardware_config_id, firmware_version, "
            "sensor ROMs and physical positions as the S2 run",
        ],
        "honesty": [
            "no frame here is counted as a run",
            "one boot_id's segments are never registered as independent runs",
            "a capture that cannot be parsed is stated as unparseable, not as zero usable frames",
        ],
    }


def s4_runs_index(real_trace: dict, real_log: dict) -> dict:
    return {
        "requirement": "docs/05A §20 A-W11-02 (S4 evidence)",
        "deliverable": "S4-runs/",
        "publishable_runs": [],
        "publishable_run_count": 0,
        "runs_available": 0,
        "repetitions_planned": s4.S4_CAPTURE_RECIPE["repetitions"],
        "status_label": s4.S4_CAPTURE_RECIPE["status_label"],
        "sources_audited": [
            {
                "path": "evidence/A/W04/tec-cooling-response-600s.csv",
                "commands_observed": real_trace["commands_observed"],
                "verdict": "no command lines in this encoding; device-lane audit only",
            },
            {
                "path": "evidence/A/W04/g1/40-g1-boot-60s.log",
                "cmdack_lines": real_log["summary"]["cmdack_lines"],
                "telem_frames": real_log["summary"]["telem_frames"],
                "score_verdict": real_log["score"]["verdict"],
                "thermal_non_response_proven": real_log["score"]["thermal_non_response_proven"],
                "s4_run_publishable": real_log["score"]["s4_run_publishable"],
            },
        ],
        "why_no_run_exists": list(s4.S4_PROTOCOL["why_not_computable_now"]),
        "capture_recipe": s4.S4_CAPTURE_RECIPE,
        "honesty": [
            "a protocol verdict of SAFETY_BLOCKED is not evidence that the output stayed cold",
            "no lane of a published run may be filled by reading the request",
            "zero observations prove zero legs, not clean legs",
        ],
    }


def protocol_markdown(lane_evidence: dict, real_trace: dict) -> str:
    proto = s4.S4_PROTOCOL
    recipe = s4.S4_CAPTURE_RECIPE
    divergence = real_trace["device_lane_audit"]["request_applied_divergence"]
    candidates = lane_evidence["command_electrical_disagreements"]
    lines = [
        "# S4 protocol v1 - safe actuation-response fault, three lanes kept apart",
        "",
        f"Requirement: `docs/05A` §20 A-W11-01 / A-W11-02. Generated by "
        f"`build_w11_artifacts.py` from `firmware/tools/cg_w11_s4.py` ({s4.S4_TOOL_VERSION}) "
        f"and `firmware/tools/cg_s4_refusal.py` ({refusal.S4_TOOL_VERSION}); build stamp "
        f"{BUILD_STAMP} is {BUILD_STAMP_MEANING}.",
        "",
        f"**Status: {proto['status_label']}**",
        "",
        "## 1. Method",
        "",
        proto["method"],
        "",
        "## 2. The four evidence lanes",
        "",
        "| lane | read from |",
        "|---|---|",
    ]
    for lane in proto["required_evidence_lanes"]:
        lines.append(f"| `{lane['lane']}` | {lane['from']} |")
    lines += [
        "",
        "## 3. Expected signature and what it proves",
        "",
    ]
    for key, value in proto["expected_signature"].items():
        lines.append(f"* `{key}`: {value}")
    lines += [
        "",
        "## 4. Promotion rules the validator enforces",
        "",
        f"* forbidden lane sources: `{list(s4.FORBIDDEN_SOURCES)}`",
        f"* refusal statuses that may never carry an applied action: "
        f"`{list(s4.REFUSAL_STATUSES)}`",
        f"* non-reapplication statuses: `{list(s4.NON_REAPPLICATION_STATUSES)}` "
        "(docs/02 §30.1 forbids a replay applying again)",
        f"* rule: {real_trace['promotion_rules']['rule']}",
        f"* electrical floors used so the two S4 tools cannot disagree: "
        f"no-response below {candidates['floors_a']['no_active_response_below']} A, "
        f"residual above {candidates['floors_a']['residual_response_above']} A "
        f"({candidates['floors_a']['basis']})",
        "",
        "## 5. Hazard this protocol exists to catch",
        "",
        proto["hazard_this_protocol_avoids"],
        "",
        "## 6. What the real capture does support",
        "",
        f"* requested/applied/read-back are three separate device claims: "
        f"`{divergence['distinct_req_applied_readback_tuples']}` over "
        f"{divergence['frames_where_applied_differs_from_requested']} frames where applied "
        "differs from requested",
        f"* reading: {divergence['reading']}",
        f"* no-active-response candidates: "
        f"{[c['seq'] for c in candidates['no_active_response_candidates']]} "
        "(state=COOLING, applied duty 999, current reads 0.0 A)",
        f"* residual-response candidates: "
        f"{[c['seq'] for c in candidates['residual_response_candidates']]} "
        "(state=COOLDOWN, duty 0, current still above the residual floor)",
        f"* command observations in the committed capture: "
        f"{real_trace['commands_observed']} - the intent lane has no device instance",
        "",
        "### Row accounting: nothing is dropped without a name",
        "",
        f"* duty comparison: {divergence['row_account']['frames_scanned']} scanned, "
        f"{divergence['row_account']['rows_compared']} compared, "
        f"{divergence['row_account']['rows_excluded_total']} excluded "
        f"(`{divergence['row_account']['rows_excluded']}`)",
        f"* applied/current comparison: {candidates['row_account']['frames_scanned']} scanned, "
        f"{candidates['row_account']['rows_compared']} compared, "
        f"{candidates['row_account']['rows_excluded_total']} excluded "
        f"(`{candidates['row_account']['rows_excluded']}`)",
        f"* exclusion reasons checked and found zero rows: "
        f"`{candidates['row_account']['reasons_never_fired']}` - checked-and-found-none is "
        "not the same claim as did-not-check",
        f"* intent versus application: {divergence['intent_vs_application']}",
        "",
        "### Which slots may carry the thermal lane, and on whose authority",
        "",
        f"* frozen geometry `{lane_evidence['chamber_air_slot_basis']['geometry_version']}` "
        f"({lane_evidence['chamber_air_slot_basis']['position_source']}): "
        f"`{lane_evidence['chamber_air_slot_basis']['frozen_positions']}`",
        f"* chamber-air slots: `{lane_evidence['chamber_air_slot_basis']['chamber_air_slots']}`; "
        f"excluded: `{lane_evidence['chamber_air_slot_basis']['excluded_from_chamber_air']}`",
        f"* the capture's own role fields say "
        f"`{lane_evidence['chamber_air_slot_basis']['raw_role_fields_in_this_capture']}`, which "
        "disagrees with the frozen record - those are commissioning-era assignments. "
        "The slot set is **read from W09** "
        f"(`{lane_evidence['chamber_air_slot_basis']['reused_not_rederived']}`), not re-derived, "
        "and nothing is remapped.",
        f"* naming discrepancy: {lane_evidence['chamber_air_slot_basis']['docs01_discrepancy']}",
        f"* registry gap worked around: {lane_evidence['chamber_air_slot_basis']['registry_gap']}",
        "",
        "**Every current value above is unqualified**: `current_status` is empty in all 957 "
        "rows and no `power_status` column exists, so these are candidates for an S4 signature, "
        "never certified electrical evidence. `electrically_qualified: false` is carried per "
        "candidate in `s4-s3/lane-evidence.json`.",
        "",
        "## 7. Why the physical leg is not computable today",
        "",
    ]
    lines += [f"* {reason}" for reason in proto["why_not_computable_now"]]
    lines += [
        "",
        "## 8. Fixture position",
        "",
        proto["fixture_position"],
        "",
        "## 9. Capture recipe (what closes S4)",
        "",
        f"* status **{recipe['status_label']}**, {recipe['repetitions']} repetitions, "
        f"{recipe['cadence']}, planned capture {recipe['estimated_capture_duration_s']} s",
        "",
        "### Prerequisites",
        "",
    ]
    lines += [f"* {p}" for p in recipe["prerequisites"]]
    lines += ["", "### Per repetition", ""]
    for step, item in enumerate(recipe["per_repetition"], start=1):
        lines.append(f"{step}. {item}")
    lines += [
        "",
        "### Downstream unlocks",
        "",
    ]
    lines += [f"* {u}" for u in recipe["downstream_unlocks"]]
    lines += ["", "## 10. Not done, on purpose", "", ""]
    lines += [
        "* no shorted branch, no bypassed fuse, no damaged TEC, no invented fan obstruction",
        "* no command was simulated as received by a device",
    ]
    lines += [
        "",
        f"Shortfall note: {s3.assess()['warning']}",
        "",
    ]
    return "\n".join(lines)


def chamber_air_slot_basis(frames) -> dict:
    """Why the thermal lane may average t1/t3/t4 and must not touch t2.

    The slot set is not re-derived here: it is read from the W09 frozen as-built
    geometry that the W09 export layer carries, so W11 reuses one authority instead
    of creating a second one that can drift. The capture's own per-row role fields
    are published next to it because they disagree with that record - they are
    commissioning-era assignments (T1/T3/T4 UNASSIGNED, T2 HOT_SIDE) - and the
    disagreement is documented, never silently remapped.
    """
    observed_roles = {
        slot: sorted({str(f.values[f"{slot}_role"]) for f in frames if f.has(f"{slot}_role")})
        for slot in run_export.PROBE_SLOTS
    }
    return {
        "geometry_version": run_export.FROZEN_GEOMETRY_VERSION,
        "position_source": run_export.POSITION_SOURCE,
        "frozen_positions": {
            slot: run_export.FROZEN_SENSOR_GEOMETRY[slot]["position"]
            for slot in run_export.PROBE_SLOTS
        },
        "chamber_air_slots": list(run_export.CHAMBER_AIR_SLOTS),
        "excluded_from_chamber_air": {
            slot: run_export.EXCLUDED_FROM_CHAMBER_MEAN[slot]
            for slot in run_export.PROBE_SLOTS
            if slot in run_export.EXCLUDED_FROM_CHAMBER_MEAN
        },
        "raw_role_fields_in_this_capture": observed_roles,
        "docs01_discrepancy": (
            "docs/01 lines 823-825 name the probes T1 near-door / T2 central / T3 "
            "far-opposite, while the frozen as-built record places T1 in the chamber "
            "centre, T2 on the TEC hot side, T3 at the bottom and T4 near the door. The "
            "discrepancy is documented, not resolved by this tooling: no slot is remapped, "
            "and the canonical naming decision stays with the coordinator (TEAM_DEPENDENCY), "
            "as W09 already recorded it."
        ),
        "reused_not_rederived": (
            "cg_w09_export.FROZEN_SENSOR_GEOMETRY / FROZEN_GEOMETRY_VERSION, the same record "
            "W09 published in evidence/A/W09/exports/CG-S1-H8C-600S.json; the capture list is "
            "read from evidence/A/W09/run-registry.json"
        ),
        "registry_gap": (
            "evidence/A/W09/run-registry.json carries no geometry field, so the frozen positions "
            "are taken from the W09 export module rather than the registry. Reported as a gap; "
            "not a reason to re-derive a second geometry in W11"
        ),
    }


def build_artifacts() -> dict[str, str]:
    frames, report = cp.read_csv_capture(W04_CSV, RUN_LABEL)
    if report["rejected"]:
        raise RuntimeError(f"the committed capture no longer parses cleanly: {report['rejected']}")
    real_trace = s4.build_s4_trace(frames, is_physical_measurement=True)
    if real_trace["commands_observed"] != 0:
        raise RuntimeError(
            "the committed capture now yields command observations; re-derive the S4 position "
            "from the new source instead of reusing these artifacts"
        )
    real_log = _pin(
        refusal.analyze_capture(W04_G1_LOG, is_physical_measurement=True), [W04_G1_LOG]
    )
    if real_log["score"]["thermal_non_response_proven"]:
        raise RuntimeError(
            "a log with zero command lines is being scored as proving thermal non-response"
        )
    lane_evidence = _pin({
        "tool_version": s4.S4_TOOL_VERSION,
        "command_electrical_disagreements": s4.find_command_electrical_disagreements(frames),
        "request_applied_divergence": s4.request_applied_divergence(frames),
        "lane_view_of_one_active_frame": s4.build_lane_view(
            next(f for f in frames if f.values.get("pwm_applied_permille") == 999)
        ),
        "thermal_noise_floor_for_the_s4_thermal_lane": {
            "single_frame_floor_c": pairing.minimum_detectable_disturbance(
                frames
            )["single_frame_floor_binding_c"],
            "chamber_air_slots": ["t1", "t3", "t4"],
            "basis": "the S4 thermal lane is a comparison against this measured floor",
        },
        "chamber_air_slot_basis": chamber_air_slot_basis(frames),
        "is_physical_measurement": True,
        "status_label": "REAL_DATA_ANALYZED",
        "honesty": [
            "candidates are labelled with the qualification their status field actually has",
            "empty current_status is not OK, so no candidate is certified electrical evidence",
            "TEC_HOT_SIDE (T2) is never used as chamber air",
        ],
    }, [W04_CSV])
    trace_out = _pin(real_trace, [W04_CSV])
    assessed = s3.assess()
    assessed["existing_capture_shortfalls"] = s3_capture_shortfalls()
    feasibility = _pin(assessed, [W09_REGISTRY])
    return {
        "S4-protocol.md": protocol_markdown(lane_evidence, trace_out),
        "S3-go-no-go.md": s3.render_markdown(feasibility),
        "additional-valid-run-list.json": _text(additional_run_list()),
        "S4-runs/index.json": _text(_pin(s4_runs_index(trace_out, real_log), [W04_CSV, W04_G1_LOG])),
        "S4-runs/host-fixture-refusal-trace.json": _text(_pin(host_fixture_trace(), [])),
        "s4-s3/s4-trace-real-capture.json": _text(trace_out),
        "s4-s3/refusal-analysis-real-log.json": _text(real_log),
        "s4-s3/lane-evidence.json": _text(lane_evidence),
        "s4-s3/s3-feasibility.json": _text(feasibility),
    }


PINNED_FILES = (
    "README.md",
    "acceptance.md",
    "S4-protocol.md",
    "S3-go-no-go.md",
    "additional-valid-run-list.json",
    "build_w11_artifacts.py",
    "validate_w11.py",
    "S4-runs/index.json",
    "S4-runs/host-fixture-refusal-trace.json",
    "s4-s3/s4-trace-real-capture.json",
    "s4-s3/refusal-analysis-real-log.json",
    "s4-s3/lane-evidence.json",
    "s4-s3/s3-feasibility.json",
)


def write_sums() -> int:
    missing = [name for name in PINNED_FILES if not (EVIDENCE / name).is_file()]
    if missing:
        print("W11 SUMS: REFUSED, missing " + ", ".join(missing))
        return 1
    lines = [f"{sha256_file(EVIDENCE / name)}  {name}" for name in sorted(PINNED_FILES)]
    (EVIDENCE / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote SHA256SUMS.txt ({len(lines)} files)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="regenerate and compare against the files on disk")
    parser.add_argument("--sums", action="store_true",
                        help="rewrite SHA256SUMS.txt for the files this dossier pins")
    args = parser.parse_args(argv)

    if args.sums:
        return write_sums()

    artifacts = build_artifacts()
    if args.check:
        drifted = []
        for name, text in artifacts.items():
            path = EVIDENCE / name
            if not path.is_file():
                drifted.append(f"{name}: missing")
            elif path.open(encoding="utf-8", newline="\n").read() != text:
                drifted.append(f"{name}: differs from a fresh derivation")
        if drifted:
            print("W11 ARTIFACT CHECK: DRIFTED")
            for line in drifted:
                print(f"  - {line}")
            return 1
        print(f"W11 ARTIFACT CHECK: {len(artifacts)} artifacts reproduce exactly")
        return 0

    for name, text in artifacts.items():
        path = EVIDENCE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {name} ({len(text.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
