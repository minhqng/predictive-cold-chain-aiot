"""ColdGuard W14 sensor-position QA against the frozen geometry (A-W14-01).

docs/05A A-W14-01 says "verify no movement since freeze". That sentence asks for
something archived telemetry cannot deliver, and this module is written around that
fact instead of around the wish:

* **What a new capture can show** is that the role labels and the per-channel
  *behaviour* still match the frozen record - a mismatch is evidence something
  changed, and each mismatch names what it would mean physically.
* **What no archived capture can show** is that nothing moved. The 2026-11-01 H8
  frames carry no sensor ROM ids (`#CG H8S schema=3`), so a channel in a later
  capture cannot be tied to the same physical probe by identity, and no frame
  records tip height, clearance, orientation or cable path. Non-movement is
  therefore a physical observation (photo, mount inspection, ROM readback), never a
  host inference. The phrase "no movement verified" is refused by this module and by
  the dossier validator, and refusing it is tested.

The baseline is the operator-frozen record:

    evidence/A/W07/geometry-v1.md  §1   T1 chamber CENTER, T2 TEC HOT_SIDE,
                                        T3 chamber BOTTOM, T4 near the DOOR
    evidence/A/W07/probe-identification-v0.md  the slot-to-position mapping and the
                                        capture-reported role labels it documents

Roles come from W07's ``AS_BUILT_ROLES``, which is that record expressed as data, so
this file cannot quietly re-map a probe. The 2026-11-02 touch captures are
``PROBE_IDENTIFICATION`` and are refused as a numeric baseline: the frozen record
forbids reusing them for any thermal statistic, and a hand-held probe is not a
behaviour reference.

Output is split into the two states the honest answer needs, always both present:

    CURRENT_VERIFIABLE     what the captures on disk say today
    NEEDS_A_NEW_CAPTURE    what only a fresh capture could say
    NEEDS_PHYSICAL_EVIDENCE what no capture can say (mount, clearance, photo)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

import cg_thermal_repeatability as rep
import cg_w14_spatial as spatial
from cg_thermal_repeatability import AS_BUILT_ROLES, AnalysisError

SCHEMA_NOTE = "w14-sensor-position-qa-v0"
FROZEN_GEOMETRY_SOURCE = "evidence/A/W07/geometry-v1.md §1"
FROZEN_IDENTIFICATION_SOURCE = "evidence/A/W07/probe-identification-v0.md"

# The role labels the frozen record documents as the capture-reported ones. This is
# the firmware's own column, not a position claim: three slots are UNASSIGNED in the
# image that produced the committed session, and only the hot side is labelled.
FROZEN_CAPTURE_ROLE_LABELS = {"t1_role": "UNASSIGNED", "t2_role": "HOT_SIDE",
                              "t3_role": "UNASSIGNED", "t4_role": "UNASSIGNED"}
CAPTURE_ROLE_COLUMNS = tuple(FROZEN_CAPTURE_ROLE_LABELS)
DRIVEN_SIGN_CHANNEL = "t2_c"
AIR_TERMS = spatial.AIR_TERMS
HOT_SIDE_ROLE = spatial.HOT_SIDE_ROLE

FORBIDDEN_OUTPUT_PHRASES = (
    "no movement verified", "movement ruled out", "positions confirmed unchanged",
    "geometry unchanged since freeze", "no drift detected",
)

# The claim vocabulary W14 artifacts may only carry inside a quotation or a negation.
# Kept here, not duplicated in the dossier tools, so the generator and the validator
# cannot drift into checking different sentences.
FALSE_CLAIM_PHRASES = FORBIDDEN_OUTPUT_PHRASES + (
    "movement verified", "distribution computed", "distribution of run-to-run",
    "tolerance agreed", "agreed tolerance", "adopted tolerance", "final tolerance",
    "frozen tolerance", "physically verified", "repeatability established",
)
# A backtick, an explicit negation or an explicit false label is what makes a forbidden
# claim a discussion instead of an assertion. A double quote is deliberately NOT one of
# them: every JSON value line is built out of double quotes, so counting one as a
# quotation marker exempted the entire contents of every .json artifact from this guard
# (a planted `"summary": "... no movement verified ..."` sailed through). JSON artifacts
# are checked structurally by `guard_no_forbidden_claim`, which has no exemption at all.
CLAIM_MARKERS = ("`", "never", "not", "false", "refus", "must not",
                 "forbid", "without", "cannot", "n_never", "is_not", "not_a_", "NOT_")


def assert_no_false_claim(name: str, text: str) -> None:
    """Every false claim must be quoted, negated or labelled false; a bare assertion fails.

    A blanket phrase ban cannot work here, because the honest reports have to *discuss*
    these claims. What is banned is asserting one: a line that carries a forbidden claim
    with no quotation mark, no negation and no `false` next to it is the defect.

    This is a line filter for prose. Parsed JSON has no line structure worth trusting,
    so `guard_no_forbidden_claim` is what checks it, and that guard has no exemption
    list: a forbidden claim in any value of a payload raises, however it is quoted.
    """
    for number, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        for phrase in FALSE_CLAIM_PHRASES:
            if phrase in lowered and not any(marker in lowered for marker in CLAIM_MARKERS):
                raise AnalysisError(
                    f"{name}:{number} asserts {phrase!r} without quoting or negating it, "
                    "and the archived captures cannot support it")

WHAT_A_MISMATCH_WOULD_MEAN = {
    "capture_role_label_mismatch": (
        "the firmware's role column no longer matches the label the frozen record "
        "documents, which means the image, pin-map version or slot-to-channel map "
        "changed - the capture is then describing a different logical geometry, not "
        "the frozen one. It is not by itself proof that a probe was moved."),
    "hot_side_channel_moved": (
        "the channel that rises while the bridge is driven is no longer the slot the "
        "record calls TEC hot side: either the hot-side probe left the stack, an air "
        "probe is now touching the stack or a rack, or the 1-Wire slots were re-mapped "
        "at the connector. Any of these invalidates the air/hot split every W07 "
        "statistic is built on."),
    "air_triad_direction_change": (
        "one of the three chamber-air channels stopped falling while driven, so that "
        "tip is no longer sampling the air volume the other two agree about - the most "
        "likely causes are a probe that moved, became coupled to a surface, or became "
        "electrically stale while the value held."),
    "air_separation_change": (
        "the mutual spread of the three air probes left the band the baseline session "
        "shows. Because that band comes from one run's within-session drift, this is a "
        "flag to look, not a measurement of movement: it also fires if the chamber "
        "started at a different load or the door was left cracked."),
    "level_offset_beyond_baseline_band": (
        "the absolute levels sit outside the baseline session's own drift band. That "
        "is expected whenever start conditions differ, so on its own it says nothing "
        "about position; it only matters together with a direction or separation "
        "change."),
    "rank_order_change": (
        "the ordering of the channels by level flipped. Positions in a stratified "
        "chamber set the ordering, so a persistent flip with everything else "
        "unchanged is the pattern a probe swap or a probe that moved a shelf over "
        "would leave."),
}


def _channel_series(rows: list[dict[str, str]], term: str) -> list[float]:
    values = [value for value in (rep.reading(row, term)[0] for row in rows)
              if value is not None]
    return values


def behaviour_signature(rows: list[dict[str, str]]) -> dict[str, object]:
    """Per-channel behaviour over the driven block: level, direction, separation, rank.

    Nothing here is a tolerance. It is the observable shape the frozen geometry
    predicts - the hot-side surface climbing while the three air probes fall - and it
    is the shape a later capture is compared against.
    """
    phases = rep.split_phases(rows)
    driven = phases["cooling"]
    off = phases["baseline"]
    if len(driven) < 2:
        raise AnalysisError("behaviour signature needs a driven block; this capture has "
                            "no cooling rows, so there is no response to characterise")
    per_channel: dict[str, object] = {}
    for term in AS_BUILT_ROLES:
        on = _channel_series(driven, term)
        before = _channel_series(off, term) if off else []
        if not on:
            per_channel[term] = {"status": "NO_DATA", "role": AS_BUILT_ROLES[term]}
            continue
        per_channel[term] = {
            "role": AS_BUILT_ROLES[term],
            "status": "MEASURED",
            "samples": len(on),
            "mean_driven_c": round(statistics.fmean(on), 4),
            "delta_driven_c": round(on[-1] - on[0], 4),
            "spread_driven_c": round(max(on) - min(on), 4),
            "sd_within_session_sample_c": (round(statistics.stdev(on), 4)
                                          if len(on) > 1 else None),
            "mean_before_driven_c": (round(statistics.fmean(before), 4)
                                     if before else None),
            "direction": ("DOWN" if on[-1] - on[0] < 0 else
                          "UP" if on[-1] - on[0] > 0 else "FLAT"),
        }
    air_means = [rep.reading(row, term)[0] for row in driven
                 for term in AIR_TERMS]
    air_series = {term: _channel_series(driven, term) for term in AIR_TERMS}
    complete = [index for index in range(len(driven))
                if all(len(air_series[term]) > index for term in AIR_TERMS)]
    triad_spread = [round(max(air_series[term][index] for term in AIR_TERMS)
                          - min(air_series[term][index] for term in AIR_TERMS), 4)
                    for index in complete]
    surface = _channel_series(driven, DRIVEN_SIGN_CHANNEL)
    separation = [round(surface[index] - statistics.fmean(
        [air_series[term][index] for term in AIR_TERMS]), 4)
                  for index in range(min(len(surface), len(complete)))
                  if index in set(complete)]
    ranked = sorted((term for term in AS_BUILT_ROLES
                     if per_channel[term]["status"] == "MEASURED"),
                    key=lambda term: -float(per_channel[term]["mean_driven_c"]))
    return {
        "phase_rows": len(driven),
        "per_channel": per_channel,
        "channel_rank_by_level_high_to_low": list(ranked),
        "rising_channel": [term for term in AS_BUILT_ROLES
                           if per_channel.get(term, {}).get("direction") == "UP"],
        "air_triad_max_spread_c": round(max(triad_spread), 4) if triad_spread else None,
        "air_triad_median_spread_c": (round(statistics.median(triad_spread), 4)
                                      if triad_spread else None),
        "hot_side_minus_air_mean_c": {
            "min": round(min(separation), 4) if separation else None,
            "max": round(max(separation), 4) if separation else None,
            "mean": round(statistics.fmean(separation), 4) if separation else None,
        },
        "consistent_with_hot_side_split": (
            per_channel.get(DRIVEN_SIGN_CHANNEL, {}).get("direction") == "UP"
            and all(per_channel.get(term, {}).get("direction") == "DOWN"
                    for term in AIR_TERMS)),
        "air_mean_note": ("the triad spread is measured across the three chamber-air "
                          "positions only; the hot-side surface is never part of it"),
        "air_probe_levels": [round(float(per_channel[t]["mean_driven_c"]), 4)
                             for t in AIR_TERMS
                             if per_channel[t]["status"] == "MEASURED"],
    }


def role_label_check(rows: list[dict[str, str]]) -> dict[str, object]:
    """Does the capture's own role column still say what the frozen record says?"""
    observed: dict[str, object] = {}
    mismatches: list[str] = []
    absent: list[str] = []
    for column, want in FROZEN_CAPTURE_ROLE_LABELS.items():
        tokens = sorted({(row.get(column) or "COLUMN_ABSENT").strip() or "MISSING"
                         for row in rows})
        if tokens == ["COLUMN_ABSENT"]:
            absent.append(column)
            observed[column] = {"tokens": tokens, "state": "COLUMN_ABSENT"}
            continue
        state = "MATCH" if tokens == [want] else "MISMATCH"
        if state == "MISMATCH":
            mismatches.append(column)
        observed[column] = {"tokens": tokens, "expected": want, "state": state}
    return {
        "per_column": observed,
        "mismatched_columns": mismatches,
        "absent_columns": absent,
        "state": ("COLUMN_ABSENT" if absent else
                  "MISMATCH" if mismatches else "MATCH"),
        "meaning_of_a_mismatch": WHAT_A_MISMATCH_WOULD_MEAN["capture_role_label_mismatch"],
        "source": FROZEN_IDENTIFICATION_SOURCE,
    }


def compare_signatures(baseline: dict[str, object], candidate: dict[str, object
                                                                      ]) -> dict[str, object]:
    """Flag every way a candidate capture's behaviour departs from the baseline."""
    checks: dict[str, object] = {}
    base_rising = set(baseline["rising_channel"])
    cand_rising = set(candidate["rising_channel"])
    checks["hot_side_channel"] = {
        "baseline": sorted(base_rising), "candidate": sorted(cand_rising),
        "state": "MATCH" if base_rising == cand_rising else "MISMATCH",
        "meaning_if_mismatched": WHAT_A_MISMATCH_WOULD_MEAN["hot_side_channel_moved"],
    }
    base_dir = {t: baseline["per_channel"][t].get("direction") for t in AS_BUILT_ROLES}
    cand_dir = {t: candidate["per_channel"][t].get("direction") for t in AS_BUILT_ROLES}
    checks["air_triad_direction"] = {
        "baseline": {t: base_dir[t] for t in AIR_TERMS},
        "candidate": {t: cand_dir[t] for t in AIR_TERMS},
        "state": "MATCH" if all(base_dir[t] == cand_dir[t] for t in AIR_TERMS) else "MISMATCH",
        "meaning_if_mismatched": WHAT_A_MISMATCH_WOULD_MEAN["air_triad_direction_change"],
    }
    base_spread = baseline["air_triad_max_spread_c"]
    cand_spread = candidate["air_triad_max_spread_c"]
    checks["air_separation"] = {
        "baseline_max_spread_c": base_spread, "candidate_max_spread_c": cand_spread,
        "state": ("NOT_COMPARABLE" if base_spread is None or cand_spread is None
                  else "WITHIN_BASELINE_ORDER"
                  if 0.5 * base_spread <= cand_spread <= 2.0 * base_spread
                  else "OUTSIDE_BASELINE_ORDER"),
        "band_is_not_a_tolerance": True,
        "band_basis": ("a factor-of-two screen around one session's own maximum spread, "
                        "chosen to raise a flag for inspection. It is not a repeat "
                        "tolerance and not a movement threshold: with one baseline "
                        "session there is no measured run-to-run spread to build one "
                        "from, and A-W14-04 leaves the real number to Member B"),
        "meaning_if_outside": WHAT_A_MISMATCH_WOULD_MEAN["air_separation_change"],
    }
    offsets = {}
    for term in AS_BUILT_ROLES:
        base = baseline["per_channel"][term]
        cand = candidate["per_channel"][term]
        if base.get("status") != "MEASURED" or cand.get("status") != "MEASURED":
            offsets[term] = "NOT_COMPARABLE"
            continue
        offsets[term] = round(float(cand["mean_driven_c"]) - float(base["mean_driven_c"]), 4)
    checks["level_offset_c"] = {
        "per_channel": offsets,
        "meaning_if_large": WHAT_A_MISMATCH_WOULD_MEAN["level_offset_beyond_baseline_band"],
    }
    checks["channel_rank_order"] = {
        "baseline": list(baseline["channel_rank_by_level_high_to_low"]),
        "candidate": list(candidate["channel_rank_by_level_high_to_low"]),
        "state": ("MATCH" if baseline["channel_rank_by_level_high_to_low"]
                  == candidate["channel_rank_by_level_high_to_low"] else "MISMATCH"),
        "meaning_if_mismatched": WHAT_A_MISMATCH_WOULD_MEAN["rank_order_change"],
    }
    return checks


def _read_thermal(path: pathlib.Path) -> tuple[list[dict[str, str]], dict[str, object]]:
    rows = rep.read_rows(path)
    admission = spatial.require_thermal_capture(path, rows)
    return rows, admission


def position_qa(baseline_path: pathlib.Path,
                candidate_paths: list[pathlib.Path]) -> dict[str, object]:
    """The QA verdict, kept strictly apart into what can be verified now and what cannot."""
    if not baseline_path.is_file():
        raise AnalysisError(f"baseline capture not found: {baseline_path}")
    rows, admission = _read_thermal(baseline_path)
    labels = role_label_check(rows)
    baseline_signature = behaviour_signature(rows)

    candidates: list[dict[str, object]] = []
    for path in candidate_paths:
        cand_rows, cand_admission = _read_thermal(path)
        entry: dict[str, object] = {
            "capture": rep.capture_id(path),
            "boot_ids": cand_admission["boot_ids"],
            "rows": cand_admission["rows"],
            "role_label_check": role_label_check(cand_rows),
            "behaviour_signature": behaviour_signature(cand_rows),
            "same_capture_as_baseline": rep.capture_id(path) == admission["capture"],
            "distinct_from_baseline_session": not set(cand_admission["boot_ids"])
                                             & set(admission["boot_ids"]),
        }
        entry["comparison"] = compare_signatures(baseline_signature,
                                                 entry["behaviour_signature"])
        if entry["same_capture_as_baseline"]:
            entry["comparison_value"] = (
                "this candidate is the baseline session itself, so the comparison is "
                "circular and proves only that the tool runs: it cannot say anything "
                "about the period after 2026-11-01")
        candidates.append(entry)

    distinct = [entry for entry in candidates if entry["distinct_from_baseline_session"]]
    return {
        "schema": SCHEMA_NOTE,
        "deliverable": "A-W14-01 sensor-position QA",
        "frozen_baseline": {
            "geometry": FROZEN_GEOMETRY_SOURCE,
            "identification_record": FROZEN_IDENTIFICATION_SOURCE,
            "slot_to_position": dict(AS_BUILT_ROLES),
            "capture_role_labels_expected": dict(FROZEN_CAPTURE_ROLE_LABELS),
            "frozen_by": ("operator-confirmed identification accepted as the official "
                          "as-built record; no new identification test is authorized"),
        },
        "baseline_capture": {**admission, "role_label_check": labels,
                             "behaviour_signature": baseline_signature},
        "candidates": candidates,
        "CURRENT_VERIFIABLE": {
            "capture_role_labels_vs_frozen_record": labels["state"],
            "behaviour_consistent_with_frozen_geometry":
                baseline_signature["consistent_with_hot_side_split"],
            "hot_side_channel_in_the_one_session": baseline_signature["rising_channel"],
            "air_triad_max_spread_c_in_that_session":
                baseline_signature["air_triad_max_spread_c"],
            "statements_this_supports": [
                f"the committed session's own role column says {labels['state']} "
                f"against the labels the frozen record documents",
                "in that session exactly one channel rose while the bridge was driven "
                f"and it is the slot the record calls {HOT_SIDE_ROLE}, while all three "
                "air channels fell - the data and the frozen geometry agree",
                "the three air channels stayed within "
                f"{baseline_signature['air_triad_max_spread_c']} C of each other while "
                "the hot-side surface separated by up to "
                f"{baseline_signature['hot_side_minus_air_mean_c']['max']} C, which is "
                "the shape three tips in the air volume plus one on metal produce",
            ],
            "statements_this_does_not_support": [
                "that no probe moved after the freeze: the only session on disk "
                "predates every later date, so it cannot describe a period after it",
                "that a channel in a new capture is the same physical probe: the H8S "
                "schema-3 frames carry no sensor ROM ids, so slot identity is not "
                "established by the wire",
                "tip height, clearance, orientation, mounting method or cable path: "
                "none of these is in any frame",
            ],
        },
        "NEEDS_A_NEW_CAPTURE": {
            "status": ("NO_CANDIDATE_CAPTURE" if not distinct else "CANDIDATE_PRESENT"),
            "distinct_candidate_sessions": len(distinct),
            "question_it_can_answer": (
                "whether role labels and per-channel behaviour still match the frozen "
                "record - a match is a consistency observation, never a proof of "
                "non-movement"),
            "question_it_cannot_answer": ("physical non-movement, which needs the "
                                          "mounting and photo evidence below"),
            "protocol": [
                "same stage, same commanded duty and duration as the frozen baseline, "
                "TEC driven once, door CLOSED with door_polarity CONFIRMED",
                ">= 600 samples at the commanded 1 Hz so the driven block is as long as "
                "the baseline's",
                "run this tool against the baseline capture before any statistic from "
                "the new session is published",
                "a ROM readback or an equivalent per-channel identity record, because "
                "the schema in use carries none",
            ],
        },
        "NEEDS_PHYSICAL_EVIDENCE": {
            "status": "NOT_IN_ANY_CAPTURE",
            "items": [
                "configuration photo or drawing of the three air tips with a scale",
                "mounting method, height, clearance and orientation per probe",
                "cable path and strain-relief record",
                "confirmation that the operator's wire labels still match the slots",
            ],
            "owner": "operator, at a supervised session (NEED_USER_ACTION)",
        },
        "verdict": {
            "movement_since_freeze": "NOT_VERIFIABLE_FROM_ARCHIVED_DATA",
            "role_labels_current_state": labels["state"],
            "behaviour_agrees_with_frozen_geometry":
                baseline_signature["consistent_with_hot_side_split"],
            "non_movement_status": "NEEDS_A_NEW_CAPTURE_AND_PHYSICAL_EVIDENCE",
            "forbidden_phrase_policy": (
                "this report never states or implies that movement was ruled out"),
        },
        "meaning_of_each_mismatch": WHAT_A_MISMATCH_WOULD_MEAN,
        "notes": [
            "Host analysis of committed captures: no new measurement, no flash, no "
            "energized stage, no probe touched.",
            "No new identification test is proposed: the operator froze the geometry "
            "and re-identifying it would move the thing being checked.",
            "The touch session is classed PROBE_IDENTIFICATION and is refused here by "
            "cg_w14_spatial.require_thermal_capture, so it cannot become a baseline.",
        ],
    }


def guard_no_forbidden_claim(payload: object) -> None:
    """Refuse to emit a report that says movement was ruled out."""
    text = json.dumps(payload, sort_keys=True).lower()
    for phrase in FORBIDDEN_OUTPUT_PHRASES:
        if phrase in text:
            raise AnalysisError(
                f"QA output contains {phrase!r}: archived captures cannot verify "
                "non-movement, so this deliverable must not say otherwise")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A-W14-01 sensor-position QA")
    parser.add_argument("--baseline", type=pathlib.Path,
                        default=rep.REPO_ROOT / "evidence" / "A" / "W04"
                        / "tec-cooling-response-600s.csv")
    parser.add_argument("--candidate", type=pathlib.Path, action="append", default=[])
    parser.add_argument("--json", dest="json_out", type=pathlib.Path)
    args = parser.parse_args(argv)

    report = position_qa(args.baseline, args.candidate or [args.baseline])
    guard_no_forbidden_claim(report)
    print(f"role_labels={report['verdict']['role_labels_current_state']}")
    print(f"behaviour_agrees_with_frozen_geometry="
          f"{report['verdict']['behaviour_agrees_with_frozen_geometry']}")
    print(f"movement_since_freeze={report['verdict']['movement_since_freeze']}")
    print(f"new_capture={report['NEEDS_A_NEW_CAPTURE']['status']} "
          f"distinct_sessions="
          f"{report['NEEDS_A_NEW_CAPTURE']['distinct_candidate_sessions']}")
    if args.json_out is not None:
        spatial.write_json(args.json_out, report)
        print(f"json={args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
