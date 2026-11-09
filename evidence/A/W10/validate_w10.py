"""Verify the W10 evidence dossier.

    py evidence/A/W10/validate_w10.py

Checks, in order:

1. every file listed in ``SHA256SUMS.txt`` exists, hashes to the pinned value, and
   every file the manifest promises is pinned;
2. no artifact carries an absolute developer path;
3. every derived artifact reproduces byte-for-byte from the delivered tooling;
4. the door claim is re-derived here, not trusted: the committed capture is counted
   again for its ``door_open`` values, the detector is re-run, and the published
   segment counts, pilot-event list and the NOT COMPUTABLE verdict must agree;
5. the horizon/pairing claims are still claims of a gap: the tolerance is null,
   neither distribution is computable today, and T2 (TEC hot side) is still
   excluded from every chamber-air statistic;
6. the prose still says what is missing - no fabricated disturbance, no selected
   ML horizon, no frozen critical threshold.

Exit code 0 only when every check passes. Nothing here touches hardware.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import pathlib
import re
import sys

DOSSIER = pathlib.Path(__file__).resolve().parent
REPO_ROOT = DOSSIER.parents[2]
TOOLS = REPO_ROOT / "firmware" / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(DOSSIER))

import build_w10_artifacts as builder  # noqa: E402
import cg_w09_capture_parser as cp  # noqa: E402
import cg_w10_door as door  # noqa: E402
import cg_w10_pairing as pairing  # noqa: E402

W04_CSV = REPO_ROOT / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"
ABSOLUTE_PATH = re.compile(r"(?:^|[\s\"'`(])[A-Za-z]:[\\/]{1,2}[^\s\"'`]*|[\\s\"'`(]/(?:home|Users)/")
FORBIDDEN_OVERSTATEMENT = re.compile(
    r"\bW10 (PASS|GREEN|COMPLETE|CLOSED)\b|\bdisturbance (was )?measured\b", re.IGNORECASE
)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(rel: str) -> dict:
    return json.loads((DOSSIER / rel).read_text(encoding="utf-8"))


def main() -> int:
    failures: list[str] = []

    sums_path = DOSSIER / "SHA256SUMS.txt"
    if not sums_path.is_file():
        print("FAIL: SHA256SUMS.txt is missing")
        return 1

    pinned: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([0-9a-f]{64})  (.+)$", line.strip())
        if not match:
            failures.append(f"SHA256SUMS.txt: unparsable line {line!r}")
            continue
        pinned[match.group(2)] = match.group(1)

    for name, digest in sorted(pinned.items()):
        path = DOSSIER / name
        if not path.is_file():
            failures.append(f"{name} is pinned but missing")
        elif sha256(path) != digest:
            failures.append(f"{name} does not hash to the pinned value")

    for name in builder.PINNED_FILES:
        if name not in pinned:
            failures.append(f"{name} is not hash-pinned")

    # --- pin-list hygiene ------------------------------------------------------
    #
    # The manifest is the dossier's contract, so it is checked in both directions:
    # nothing may sit in the folder unpinned, and nothing may be pinned that does
    # not belong there. A __pycache__/.pyc entry hashes differently on every
    # machine, so a pin list that swallowed one makes the verdict unreproducible
    # for everybody else; a CR byte is the same failure in another form, because
    # .gitattributes normalises text to LF on checkout and a CRLF file therefore
    # hashes one way here and another way in the reviewer's tree.
    on_disk = {
        found.relative_to(DOSSIER).as_posix()
        for found in DOSSIER.rglob("*")
        if found.is_file() and found.name != "SHA256SUMS.txt"
        and "__pycache__" not in found.parts and not found.name.endswith(".pyc")
    }
    for stray in sorted(on_disk - set(pinned)):
        failures.append(f"{stray} is in the dossier but not hash-pinned")
    for cache in sorted(name for name in pinned
                        if "__pycache__" in name or name.endswith(".pyc")):
        failures.append(f"{cache} is pinned; a compiled cache file hashes per machine")
    for name in sorted(pinned):
        path = DOSSIER / name
        if path.is_file() and b"\r" in path.read_bytes():
            failures.append(f"{name} carries CR bytes and would re-hash on checkout")
    if b"\r" in sums_path.read_bytes():
        failures.append("SHA256SUMS.txt carries CR bytes and would re-hash on checkout")

    for name in pinned:
        if not name.endswith((".md", ".json", ".csv", ".py", ".txt")):
            continue
        body = (DOSSIER / name).read_text(encoding="utf-8")
        hit = ABSOLUTE_PATH.search(body)
        if hit:
            failures.append(f"{name} carries a non-repository-relative path: {hit.group(0)!r}")
        if name.endswith(".md") and FORBIDDEN_OVERSTATEMENT.search(body):
            failures.append(f"{name} overstates the week as measured or complete")

    for name, text in builder.build_artifacts().items():
        path = DOSSIER / name
        if not path.is_file():
            failures.append(f"{name} is not on disk")
        elif path.open(encoding="utf-8", newline="\n").read() != text:
            failures.append(f"{name} does not reproduce from the delivered tooling")

    # --- re-derive the door claim from the source, not from the artifact -------
    with W04_CSV.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        source_rows = list(reader)
    reported_counts: dict[str, int] = {}
    for row in source_rows:
        value = row["door_open"]
        reported_counts[value] = reported_counts.get(value, 0) + 1
    open_in_source = sum(n for value, n in reported_counts.items() if value not in ("0", "UNKNOWN"))

    frames, _ = cp.read_csv_capture(W04_CSV, builder.RUN_LABEL)
    report = door.detect_events(frames)
    metric = read_json("s2-horizon/door-response-metric.json")
    events_csv = (DOSSIER / "S2-pilot.csv").read_text(encoding="utf-8").strip().splitlines()

    if len(source_rows) != len(frames):
        failures.append(
            f"the committed capture has {len(source_rows)} rows but the parser returned "
            f"{len(frames)} frames"
        )
    if metric["measured_from_the_committed_capture"]["frames_total"] != len(frames):
        failures.append("door-response-metric.json no longer states the real frame total")
    if reported_counts != {"0": 940, "UNKNOWN": 17}:
        failures.append(
            f"the source door_open values changed ({reported_counts}); the dossier's central "
            "claim must be re-derived by regenerating the artifacts, not by editing them"
        )
    if open_in_source != 0:
        failures.append("the source now carries a door-open value this dossier does not report")
    if report["s2_pilot_events"]:
        failures.append("a real S2 pilot event exists and the dossier still claims NOT COMPUTABLE")
    if metric["status"] != builder.NOT_COMPUTABLE:
        failures.append("the door->response metric is no longer reported as NOT COMPUTABLE")
    if metric["measured_from_the_committed_capture"]["open_segments"] != 0:
        failures.append("an OPEN segment is published that the source does not contain")
    if len(events_csv) - 1 != len(report["events"]):
        failures.append("S2-pilot.csv does not carry exactly the segments the detector finds")
    for row in events_csv[1:]:
        if "S2_PILOT_DISTURBANCE" in row:
            failures.append(f"S2-pilot.csv promotes a segment to a pilot disturbance: {row[:60]}")
    if not report["unknown_is_not_closed"]:
        failures.append("UNKNOWN was folded into CLOSED")
    if report["attestation"]["trustworthy"]:
        failures.append("an unattested boot was trusted as a physical door mapping")
    else:
        # Without an attestation a frame only reports a level; a bare OPEN or
        # CLOSED in the published segments would be a state nobody named.
        for event in report["events"]:
            if event["state"] not in (door.UNKNOWN, door.CLOSED_AS_REPORTED, door.OPEN_AS_REPORTED):
                failures.append(
                    f"segment {event['event_id']} is published as {event['state']!r} with no "
                    "attestation to name it"
                )
        published = metric["measured_from_the_committed_capture"]["door_state_segment_counts"]
        if published != report["state_run_counts"]:
            failures.append("the published door segment counts are not what the detector returns")
        if door.CLOSED in published or door.OPEN in published:
            failures.append("a bare CLOSED/OPEN segment count is published for an unattested boot")
    if report["polarity_inversion"]["frames_alone_can_name_door_state"]:
        failures.append("frames were allowed to name their own door state")
    if report["polarity_inversion"]["contact_inversion"]["code_level_proof_status"] != \
            door.UNCITABLE_UNTRACKED_SOURCE:
        failures.append(
            "the contact-inversion claim is presented without its citation status; the driver "
            "it points at is tracked on no ref"
        )

    # --- pairing / horizon claims stay claims of a gap -------------------------
    physics = read_json("s2-horizon/pairing-physics.json")
    floor = physics["detection_floor"]
    tolerance = physics["tolerance"]
    horizon = read_json("s2-horizon/horizon-support.json")
    recomputed_floor = pairing.minimum_detectable_disturbance(frames)
    if floor["single_frame_floor_binding_c"] != recomputed_floor["single_frame_floor_binding_c"]:
        failures.append("the published single-frame detection floor is not the measured one")
    # The published formula has to be the formula that produced the table. It once
    # named ``sigma_successive_diff`` with no z factor while the code multiplied the
    # trend-immune second-difference sigma by 2.58, so recomputing the printed T3
    # 60 s floor from the printed formula returned 0.00269 against a published
    # 0.00695 - a floor is not reproducible if its own method statement is wrong
    # (docs/01 §20.5 requires the method to be named).
    assumption = physics["noise_profile"]["assumption"]
    if "sigma_successive_diff" in assumption or "sigma_successive_diff" in floor.get(
            "detection_floor_formula", ""):
        failures.append(
            "the detection floor is published with the successive-difference estimator, which "
            "the code does not use and which a slope contaminates"
        )
    for token in ("z", "second", "sqrt(H)"):
        if token not in assumption:
            failures.append(
                f"the published noise assumption does not name the {token!r} part of the "
                "estimator it is claiming"
            )
    formula = str(floor.get("detection_floor_formula") or "")
    if str(floor["z_score"]) not in formula:
        failures.append("the detection floor formula does not state the z factor it uses")
    if "second" not in formula:
        failures.append("the detection floor formula does not name its estimator")
    z = float(floor["z_score"])
    for horizon_key, entry in floor["horizons"].items():
        seconds = int(str(horizon_key).rstrip("s"))
        for slot, sigma in floor["sigma_by_probe_c"].items():
            recomputed = round(z * sigma / math.sqrt(seconds), 5)
            if entry["per_probe_c"][slot] != recomputed:
                failures.append(
                    f"{slot} at {seconds}s is published as {entry['per_probe_c'][slot]} but the "
                    f"formula this file states gives {recomputed}"
                )
    if sorted(floor["chamber_air_slots"]) != ["t1", "t3", "t4"]:
        failures.append("TEC_HOT_SIDE was included in the chamber-air detection floor")
    if physics["noise_profile"]["probes"]["t2"]["excluded_from_chamber_mean"] == "":
        failures.append("the noise profile no longer excludes T2 from chamber air")
    if tolerance["pairing_tolerance_c"] is not None:
        failures.append("a pair-matching tolerance was published from one run")
    if tolerance["status_label"] != "NEED_USER_ACTION":
        failures.append("the tolerance estimator no longer reports the gap it cannot close")
    for name, entry in horizon["distributions_requested"].items():
        if entry["computable_now"]:
            failures.append(f"{name} is published as computable without an S2 capture")
    if horizon["s2_pilot_disturbances_available"] != 0:
        failures.append("horizon-support.json invented pilot disturbances")
    if "ML horizon choice" not in json.dumps(horizon):
        failures.append("horizon-support.json no longer leaves the horizon choice to Member B")

    prose = (DOSSIER / "README.md").read_text(encoding="utf-8") + \
        (DOSSIER / "acceptance.md").read_text(encoding="utf-8")
    for phrase in ("NOT COMPUTABLE", "NEED_USER_ACTION", "no door-open event",
                   door.UNCITABLE_UNTRACKED_SOURCE):
        if phrase not in prose:
            failures.append(f"the dossier no longer states {phrase!r}")
    for name in ("README.md", "acceptance.md", "S2-protocol-v1.md"):
        body = (DOSSIER / name).read_text(encoding="utf-8")
        if "h8_door.c" in body and door.UNCITABLE_UNTRACKED_SOURCE not in body:
            failures.append(f"{name} cites an untracked source as proof without its label")

    if not failures:
        print(
            f"W10 DOSSIER: OK ({len(pinned)} pinned files, {len(frames)} frames re-read, "
            f"{len(events_csv) - 1} door segments, 0 S2 pilot events, "
            "door->response still NOT COMPUTABLE)"
        )
        return 0

    print("W10 DOSSIER: FAIL")
    for failure in failures:
        print(f"  - {failure}")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
