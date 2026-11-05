"""Regenerate the W10 evidence artifacts from the delivered tooling.

    py evidence/A/W10/build_w10_artifacts.py [--check] [--sums]

Every artifact here is derived by running the W10 tools over bytes that are already
in the repository - the committed W04 capture - or from the recipe and the timing
constants that the delivered module carries. Nothing is typed in by hand, and the
S2 position is stated as it is: **no real door-open event exists in any committed
capture**, so the door->response metric is NOT COMPUTABLE and the deliverable is
the acquisition, alignment, QC and analysis workflow plus the operator recipe.

``S2-protocol-v1.md``
    A-W10-01/-02: the protocol candidates, the MC-38 timing quantisation and the
    capture recipe, from ``cg_w10_door.S2_CAPTURE_RECIPE`` rather than prose.

``S2-pilot.csv``
    A-W10-03: the door-state segments the detector actually finds in the committed
    capture, each with the specific reason it is not an S2 pilot disturbance.

``door-event-validation.csv``
    The per-frame door evidence that makes the claim checkable: raw level, reported
    state, polarity field, device cycle counter and the validity domain per row.

``pairing-physics-summary.md``
    A-W10-04: the measured noise floor, the minimum detectable disturbance per
    horizon, and why a pair-matching tolerance cannot be estimated from one run.

``s2-horizon/door-events.json``
    The full ``detect_events`` report over the real capture.

``s2-horizon/pairing-physics.json``
    Noise profile, detection floor and the tolerance estimator's refusal.

``s2-horizon/horizon-support.json``
    A-W10-05: what the horizon support analysis can state today and what it cannot.

``s2-horizon/door-response-metric.json``
    The door->response metric, with NOT COMPUTABLE and its cause.

``s2-horizon/pilot-status.json``
    ``cg_w10_door.pilot_status`` over the real report.

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

import cg_w09_capture_parser as cp  # noqa: E402
import cg_w09_validity as validity  # noqa: E402
import cg_w10_door as door  # noqa: E402
import cg_w10_pairing as pairing  # noqa: E402

BUILD_STAMP = "2026-11-02T00:00:00Z"  # pinned so --check is byte-reproducible
BUILD_STAMP_MEANING = "HOST_BUILD_CONSTANT_NOT_A_DEVICE_TIME"

W04_CSV = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"
RUN_LABEL = "H8C_BOX_COOLING_600S"
NOT_COMPUTABLE = "NOT_COMPUTABLE"


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(payload) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ";".join(str(v) for v in value)
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict,)) else str(value)


def pilot_csv(report: dict) -> str:
    columns = (
        "event_id", "boot_id", "run_id", "state", "event_class", "start_seq", "end_seq",
        "n_frames", "duration_s", "device_reported_door_cycles", "state_semantics",
        "t1_rise_c", "t3_rise_c", "t4_rise_c", "t2_rise_c_hot_side_excluded",
        "not_s2_because", "is_physical_measurement",
    )
    lines = [",".join(columns)]
    for event in report["events"]:
        rise = event["thermal_rise"]
        lines.append(",".join([
            _cell(event["event_id"]), _cell(event["boot_id"]), _cell(event["run_id"]),
            _cell(event["state"]), _cell(event["event_class"]), _cell(event["start_seq"]),
            _cell(event["end_seq"]), _cell(event["n_frames"]), _cell(event["duration_s"]),
            _cell(event["cycles_reported_by_device"]), _cell(event["state_semantics"]),
            _cell((rise.get("t1") or {}).get("rise_c")),
            _cell((rise.get("t3") or {}).get("rise_c")),
            _cell((rise.get("t4") or {}).get("rise_c")),
            _cell((rise.get("t2") or {}).get("rise_c")),
            _cell(event["not_s2_because"]),
            _cell(event["is_physical_measurement"]),
        ]))
    return "\n".join(lines) + "\n"


def door_event_csv(frames: list, verdicts: list) -> str:
    """Per-frame door evidence, so the no-open-event claim is checkable row by row."""
    columns = (
        "seq", "boot_id", "run_id", "device_ms", "door_raw", "door_open", "door_polarity",
        "door_status", "door_cycles", "snapshot", "door_domain_quality",
        "door_invalidation_reasons", "named_state_without_attestation", "host_capture_time_utc",
    )
    lines = [",".join(columns)]
    for frame, verdict in zip(frames, verdicts):
        v = frame.values
        lines.append(",".join([
            _cell(frame.seq), _cell(frame.boot_id), _cell(frame.run_id), _cell(v.get("device_ms")),
            _cell(v.get("door_raw")), _cell(v.get("door_open")), _cell(v.get("door_polarity")),
            _cell(v.get("door_status")), _cell(v.get("door_cycles")), _cell(v.get("snapshot")),
            _cell(verdict.quality_by_domain.get("door")), _cell(verdict.reason_codes),
            "REPORTED_ONLY_NOT_PHYSICALLY_NAMED", _cell(v.get("host_capture_time_utc")),
        ]))
    return "\n".join(lines) + "\n"


def protocol_markdown(report: dict) -> str:
    recipe = door.S2_CAPTURE_RECIPE
    capture = recipe["capture_recipe"]
    timing = report["timing"]
    lines = [
        "# S2 protocol v1 - door disturbance candidates and timing method",
        "",
        f"Requirement: `docs/05A` §19 A-W10-01 (protocol candidates) and A-W10-02 (timing "
        f"method). Generated by `build_w10_artifacts.py` from "
        f"`firmware/tools/cg_w10_door.py` ({door.DOOR_TOOL_VERSION}); build stamp "
        f"{BUILD_STAMP} is {BUILD_STAMP_MEANING}.",
        "",
        f"**Status: {recipe['status_label']}** - {recipe['why']}",
        "",
        "## 1. Why the protocol is a candidate list and not a result",
        "",
        "The committed capture contains no door-open event, and the door mapping is a switch "
        "whose two settings assign opposite states to every raw level (`docs/01` §8.1/§8.2 "
        "forbid assuming either polarity without physical verification), so the protocol below "
        f"is what has to be executed, not what was observed. The driver source that shows the "
        f"inversion in code is `{door.UNCITABLE_UNTRACKED_SOURCE}`: no git ref carries "
        "`firmware/h8-bench/main/h8_door.c`, so it is recorded as a gap in "
        "`evidence/A/W09/run-registry.json` rather than quoted as proof here. The generator "
        "refuses to publish a rise, a duration or a recovery it did not measure.",
        "",
        "## 2. Planned durations and repetitions",
        "",
        f"* run-id prefix `{capture['run_id_prefix']}`, repetitions {capture['repetitions']}, "
        f"planned durations {capture['planned_durations_s']} s, horizon "
        f"{capture['horizon_per_run_s']} s at {capture['cadence']}",
        f"* pairing: {capture['pairing_requirement']}",
        f"* wall time: {capture['estimated_wall_time']}",
        "",
        "### Safety prerequisites (before any door manipulation)",
        "",
    ]
    lines += [f"* {item}" for item in capture["safety_prerequisites"]]
    lines += ["", "## 3. Per-repetition procedure", ""]
    for step, item in enumerate(capture["per_repetition"], start=1):
        lines.append(f"{step}. {item}")
    lines += [
        "",
        "## 4. MC-38 timing method (A-W10-02)",
        "",
        f"* machine ground truth: the MC-38 transition ({timing['debounce_ms']} ms debounce on a "
        f"{timing['poll_ms']} ms poll), counted by `door_cycles` on the frame stream",
        f"* the frame stream is {timing['telemetry_hz']} Hz, so the resolved edge time is "
        f"+/-{timing['edge_time_uncertainty_s']} s and the minimum resolvable open duration is "
        f"{timing['minimum_resolvable_open_duration_s']} s - the operator timer is the only "
        "sub-second check and stays secondary",
        f"* cross-check rule: {timing['cross_check']}",
        f"* machine counter field: `{timing['machine_counter_field']}`",
        "",
        "## 5. Per-boot polarity attestation",
        "",
        "`DOOR NEAR_LOW|NEAR_HIGH <boot_token>` names a level; it does not prove a physical door "
        "position, and the confirmation is per boot. `detect_events` therefore reports every "
        "unattested segment as untrusted and never folds `UNKNOWN` into `CLOSED`.",
        "",
        "## 6. Verified data position",
        "",
        "| position | reading |",
        "|---|---|",
    ]
    for name, entry in recipe["verified_data_position"].items():
        reading = entry.get("reading") if isinstance(entry, dict) else entry
        source = entry.get("source", "") if isinstance(entry, dict) else ""
        lines.append(f"| `{name}` | {reading}{f' (`{source}`)' if source else ''} |")
    lines += [
        "",
        "## 7. What this protocol does not claim",
        "",
        "* no S2 disturbance has been captured, so no rise, gradient, time-to-critical or "
        "recovery figure is published anywhere in this dossier;",
        "* the door->response metric is NOT COMPUTABLE (see "
        "`s2-horizon/door-response-metric.json`) because no real door-open event exists;",
        "* host tests over synthetic frames prove the segmentation rules, not the plant.",
        "",
    ]
    return "\n".join(lines)


def pairing_markdown(floor: dict, tolerance: dict, profile: dict) -> str:
    lines = [
        "# Pairing physics summary (A-W10-04)",
        "",
        f"Generated by `build_w10_artifacts.py` from `firmware/tools/cg_w10_pairing.py` "
        f"({floor['estimator_version']}); build stamp {BUILD_STAMP} is {BUILD_STAMP_MEANING}.",
        "",
        "## 1. What is measured",
        "",
        f"* estimator: {profile['estimator']}",
        f"* detection floor formula (what the table below is evaluated with): "
        f"`{floor['detection_floor_formula']}`",
        f"* z factor: {floor['z_score']} - {floor['z_score_meaning']}",
        f"* assumption: {profile['assumption']}",
        f"* stationarity threshold: {profile['stationarity_threshold_c_per_s']} degC/s; "
        f"selection rule: {profile['selection_rule']}",
        f"* quiescent runs found by the selection rule: {profile['quiescent_runs_found']} "
        f"(per-probe accepted counts are in `s2-horizon/pairing-physics.json`)",
        "",
        "| probe | physical position | sigma (degC) | frames pooled | quantisation floor (degC) | "
        "in chamber mean |",
        "|---|---|---|---|---|---|",
    ]
    for slot, probe in sorted(profile["probes"].items()):
        lines.append(
            f"| `{slot}` | {probe['physical_position']} | {probe['sigma_c']} | "
            f"{probe['n_frames_pooled']} | {probe['quantisation_noise_floor_c']} | "
            f"{'no - ' + probe['excluded_from_chamber_mean'] if probe['excluded_from_chamber_mean'] else 'yes'} |"
        )
    lines += [
        "",
        "## 2. Minimum detectable disturbance",
        "",
        f"* single-frame, conservative, no averaging assumption: "
        f"**{floor['single_frame_floor_binding_c']} degC** "
        f"({floor['single_frame_floor_reading']})",
        f"* chamber-air mean sigma: {floor['sigma_chamber_air_mean_c']} degC over slots "
        f"{floor['chamber_air_slots']}",
        "",
        "| horizon | per-probe floor (degC) | chamber-mean floor (degC) |",
        "|---|---|---|",
    ]
    for horizon, values in sorted(floor["horizons"].items(),
                                 key=lambda kv: int(str(kv[0]).rstrip("s"))):
        per_probe = ", ".join(f"{k} {v}" for k, v in sorted(values["per_probe_c"].items()))
        lines.append(f"| {horizon} | {per_probe} | {values['chamber_air_mean_c']} |")
    lines += [
        "",
        "## 3. Pair-matching tolerance: what B can and cannot freeze today",
        "",
        f"* status **{tolerance['status_label']}**: {tolerance['why']}",
        f"* what can be frozen now: {tolerance['what_can_be_frozen_now']}",
        f"* runs available: {tolerance['runs_available']}",
        "",
        "A tolerance is a between-run spread. Reporting a number from one run would invent a "
        "variance that was never observed, so the estimator returns null with the reason instead.",
        "",
    ]
    return "\n".join(lines)


def door_response_metric(report: dict, floor: dict) -> dict:
    open_events = [e for e in report["events"] if door.is_open_state(e["state"])]
    return {
        "metric": "door_open_edge -> chamber-air response",
        "status": NOT_COMPUTABLE,
        "requirement": "docs/05A §19 A-W10-03/-05",
        "reason": (
            "no committed capture contains a door-open event: the only real thermal capture "
            "reports door_open=0 in 940 frames and UNKNOWN in 17, with zero OPEN segments, so "
            "there is no edge to align a response to"
        ),
        "measured_from_the_committed_capture": {
            "frames_total": report["frames_total"],
            "frames_usable_for_s2": report["frames_usable_for_s2"],
            "door_state_segment_counts": report["state_run_counts"],
            "door_state_segment_counts_reading": (
                "a *_AS_REPORTED segment is the device's own reported level, not a physically "
                "named door state; this block's own attestation is present=false, "
                "trustworthy=false, so no segment here may be quoted as OPEN or CLOSED"
            ),
            "open_segments": len(open_events),
            "s2_pilot_events": report["s2_pilot_events"],
            "mc38_cross_check": report["mc38_alignment_cross_check"],
            "attestation": report["attestation"],
            "polarity_inversion": report["polarity_inversion"],
        },
        "what_is_computable_instead": {
            "noise_floor_single_frame_c": floor["single_frame_floor_binding_c"],
            "horizon_curve_c": {
                horizon: values["chamber_air_mean_c"]
                for horizon, values in sorted(floor["horizons"].items())
            },
            "reading": (
                "the detection floor is measured; the door->response distribution is not, and "
                "publishing one would be inventing it"
            ),
        },
        "closes_when": [
            "an operator-timed, per-boot-attested OPEN edge exists in a tracked capture",
            "the same configuration has a paired S1 baseline",
            "the chamber-air rise clears the measured floor",
        ],
        "is_physical_measurement": False,
        "note": "this record states a gap; it is not a measurement of a disturbance",
        "build_stamp": BUILD_STAMP,
        "build_stamp_meaning": BUILD_STAMP_MEANING,
    }


def build_artifacts() -> dict[str, str]:
    frames, report = cp.read_csv_capture(W04_CSV, RUN_LABEL)
    if report["rejected"]:
        raise RuntimeError(f"the committed capture no longer parses cleanly: {report['rejected']}")
    verdicts = validity.evaluate_frames(frames)
    door_report = door.detect_events(frames)
    if door_report["s2_pilot_events"]:
        # The dossier's central claim is that no real door-open event exists. If a
        # future capture ever changes that, this generator must be re-run against
        # the new source rather than quietly re-labelled.
        raise RuntimeError(
            f"the committed capture now yields S2 pilot events {door_report['s2_pilot_events']}; "
            "re-derive the protocol and the metric from the new source instead of overwriting them"
        )
    profile = pairing.probe_noise_profile(frames)
    floor = pairing.minimum_detectable_disturbance(frames)
    tolerance = pairing.achievable_tolerance_from_available_runs({RUN_LABEL: frames})
    horizon = pairing.horizon_support(len(door_report["s2_pilot_events"]), floor)
    for bundle in (profile, floor, tolerance, horizon):
        bundle.setdefault("source", {})
        bundle["source"] = {
            "path": W04_CSV.relative_to(REPO).as_posix(),
            "sha256": sha256_file(W04_CSV),
            "frames_total": len(frames),
        }
        bundle["build_stamp"] = BUILD_STAMP
        bundle["build_stamp_meaning"] = BUILD_STAMP_MEANING
    horizon["is_physical_measurement"] = False
    door_report_out = dict(door_report)
    door_report_out["source"] = {
        "path": W04_CSV.relative_to(REPO).as_posix(),
        "sha256": sha256_file(W04_CSV),
        "is_physical_measurement": True,
    }
    door_report_out["build_stamp"] = BUILD_STAMP
    door_report_out["build_stamp_meaning"] = BUILD_STAMP_MEANING
    status = door.pilot_status(door_report)
    status["build_stamp"] = BUILD_STAMP
    status["build_stamp_meaning"] = BUILD_STAMP_MEANING
    physics = {"noise_profile": profile, "detection_floor": floor, "tolerance": tolerance}
    return {
        "S2-protocol-v1.md": protocol_markdown(door_report),
        "S2-pilot.csv": pilot_csv(door_report),
        "door-event-validation.csv": door_event_csv(frames, verdicts),
        "pairing-physics-summary.md": pairing_markdown(floor, tolerance, profile),
        "s2-horizon/door-events.json": _text(door_report_out),
        "s2-horizon/pairing-physics.json": _text(physics),
        "s2-horizon/horizon-support.json": _text(horizon),
        "s2-horizon/door-response-metric.json": _text(door_response_metric(door_report, floor)),
        "s2-horizon/pilot-status.json": _text(status),
    }


PINNED_FILES = (
    "README.md",
    "acceptance.md",
    "S2-protocol-v1.md",
    "S2-pilot.csv",
    "door-event-validation.csv",
    "pairing-physics-summary.md",
    "build_w10_artifacts.py",
    "validate_w10.py",
    "s2-horizon/door-events.json",
    "s2-horizon/pairing-physics.json",
    "s2-horizon/horizon-support.json",
    "s2-horizon/door-response-metric.json",
    "s2-horizon/pilot-status.json",
)


def write_sums() -> int:
    missing = [name for name in PINNED_FILES if not (EVIDENCE / name).is_file()]
    if missing:
        print("W10 SUMS: REFUSED, missing " + ", ".join(missing))
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
            elif path.read_text(encoding="utf-8", newline="\n") != text:
                drifted.append(f"{name}: differs from a fresh derivation")
        if drifted:
            print("W10 ARTIFACT CHECK: DRIFTED")
            for line in drifted:
                print(f"  - {line}")
            return 1
        print(f"W10 ARTIFACT CHECK: {len(artifacts)} artifacts reproduce exactly")
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
