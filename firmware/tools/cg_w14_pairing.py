"""ColdGuard W14 pairing-criterion input for Member B (A-W14-04).

docs/05A A-W14-04: "With B freeze final A/B initial physical matching tolerances."
The tolerances are a joint decision, so this module deliberately cannot produce one.
It delivers Member A's **input side** in a shape B can consume: what the committed
data does support, what it categorically does not, the join keys, and the measurement
that would have to exist before any number could be proposed.

Why no number comes out of this host:

* run-to-run variability needs independent sessions and there is **one** thermal
  session on disk (a single ``boot_id``), so the only dispersion measurable is
  within-session sample drift;
* the disturbance axis (door open) has **no recorded event** anywhere in committed
  data, so no condition-matching tolerance for it can be grounded;
* the electrical columns carry no recorded validity in that session, so an
  electrical matching gate would be keyed on unqualified values.

A within-session spread and a repeat tolerance are different physical quantities, and
publishing the first under the second's name is the failure mode this file exists to
prevent. The guard below raises if a tolerance value ever appears while
``agreed_with_member_b`` is false, and the dossier validator re-checks it.

References: docs/01 §19 quality, §20.1/20.4/20.5/20.6, 517-530 (a partial mean is not
the same quantity and must not reuse the label), §17.7/§17.8; contract §13 (a
mechanism needs a matching proof), §19 (PASS/FAIL/NOT RUN kept apart).
"""

from __future__ import annotations

import argparse
import pathlib
import re
import statistics
import sys

import cg_thermal_repeatability as rep
import cg_w14_spatial as spatial
from cg_thermal_repeatability import AS_BUILT_ROLES, AnalysisError

SCHEMA_NOTE = "w14-pairing-input-v0"
STATUS = "TEAM_DEPENDENCY"
AIR_VARIANT = "tmean_airroles_v0"
DROP_PAIR_VARIANTS = ("air_pair_center_bottom_v0", "air_pair_center_door_v0",
                      "air_pair_bottom_door_v0")
SINGLE_AIR_VARIANTS = ("air_t1_center_v0", "air_t3_bottom_v0", "air_t4_near_door_v0")
CANONICAL_LITERAL_VARIANT = "tmean_chamber3_v0"


def drop_one_sensitivity(ablation: dict[str, object], phase: str = "cooling"
                         ) -> dict[str, object]:
    """How far the driven response moves when a probe leaves the air mean.

    This is the quantity B actually needs for feature-set selection: on identical rows,
    it says how much of the answer depends on which sensors are in the feature, which
    is a measurement, not a tolerance.
    """
    variants = ablation["captures"][0]["variants"]
    reference = variants[AIR_VARIANT].get(phase)
    if not reference or not reference.get("usable"):
        return {"status": "NO_USABLE_REFERENCE_SEGMENT", "phase": phase}
    rows: list[dict[str, object]] = []
    for name in (*DROP_PAIR_VARIANTS, *SINGLE_AIR_VARIANTS, CANONICAL_LITERAL_VARIANT,
                 "hot_t2_surface_v0"):
        metrics = variants[name].get(phase)
        if not metrics or not metrics.get("usable"):
            continue
        rows.append({
            "variant": name,
            "feature_terms": metrics["feature_terms"],
            "feature_roles": metrics["feature_roles"],
            "is_chamber_air": metrics["is_chamber_air"],
            "includes_hot_side": metrics["includes_hot_side"],
            "delta_c": metrics["delta_c"],
            "whole_phase_slope_c_per_min": metrics["whole_phase_slope_c_per_min"],
            "deviation_from_air3_delta_c": round(
                float(metrics["delta_c"]) - float(reference["delta_c"]), 4),
        })
    deviations = [abs(float(row["deviation_from_air3_delta_c"])) for row in rows]
    return {
        "status": "MEASURED_ON_ONE_SESSION",
        "phase": phase,
        "reference_variant": AIR_VARIANT,
        "reference_delta_c": reference["delta_c"],
        "conditioning_fingerprint": reference["conditioning_fingerprint"],
        "rows": rows,
        "max_abs_deviation_c": round(max(deviations), 4) if deviations else None,
        "air_only_max_abs_deviation_c": round(max(
            (abs(float(row["deviation_from_air3_delta_c"])) for row in rows
             if row["is_chamber_air"]), default=None) or 0.0, 4) if any(
            row["is_chamber_air"] for row in rows) else None,
        "read_as": ("how much the published response depends on the sensor set, "
                    "measured on identical rows of the same session - a confounding "
                    "magnitude, not a matching tolerance"),
        "not_a_tolerance_because": ("it is one session's value for one duty and one "
                                    "start condition; a matching tolerance has to bound "
                                    "run-to-run difference, which needs independent "
                                    "sessions"),
    }


def within_session_variability(capture: pathlib.Path, phase: str = "cooling"
                               ) -> dict[str, object]:
    """The only dispersion the data holds, named as such, per air pair and per channel."""
    rows = rep.read_rows(capture)
    admission = spatial.require_thermal_capture(capture, rows)
    phases = rep.split_phases(rows)
    segment = phases[phase]
    if len(segment) < 2:
        return {"status": "NO_SEGMENT", "phase": phase}
    block = spatial.pair_agreement(segment, list(spatial.AIR_TERMS), phase,
                                  admission["independent_sessions"])
    per_channel = {}
    for term in spatial.AIR_TERMS:
        values = [rep.number(row, term) for row in segment]
        values = [v for v in values if v is not None]
        per_channel[AS_BUILT_ROLES[term]] = {
            "term": term,
            "n": len(values),
            "min_c": round(min(values), 4),
            "max_c": round(max(values), 4),
            "range_c": round(max(values) - min(values), 4),
            "sd_within_session_sample_c": round(statistics.stdev(values), 4),
        }
    return {
        "status": "WITHIN_SESSION_ONLY",
        "phase": phase,
        "independent_sessions": admission["independent_sessions"],
        "pair_blocks": {label: {"n": pair["n"], "mean_c": pair["mean_c"],
                                "sd_within_session_sample_c":
                                    pair["sd_within_session_sample_c"],
                                "max_abs_c": pair["max_abs_c"]}
                        for label, pair in block["pairs"].items()},
        "per_channel": per_channel,
        "label_is_not_a_tolerance": True,
        "why": ("these numbers describe how far apart the probes sat inside one run. "
                "A run-to-run tolerance asks how far two *runs* sit apart, and one run "
                "cannot answer that at any confidence"),
    }


def pairing_input(captures: list[pathlib.Path], min_sessions: int = spatial.MIN_SESSIONS_DEFAULT
                  ) -> dict[str, object]:
    """The whole A-W14-04 input payload, with the tolerance slot left empty on purpose."""
    if not captures:
        raise AnalysisError("at least one capture is required to state what it supports")
    ablation = spatial.ablation_matrix(captures, spatial.ABLATION_VARIANTS, min_sessions)
    primary = captures[0]
    spatial_primary = spatial.spatial_report([primary])["captures"][0]
    sessions = ablation["verdict"]["independent_sessions"]
    tokens = spatial.disturbance_tokens(rep.read_rows(primary))
    rows = rep.read_rows(primary)
    unqualified = sum(1 for row in rows if rep.reading(row, "current_a")[1] == "unqualified")
    sensitivity = drop_one_sensitivity(ablation)
    payload: dict[str, object] = {
        "schema": SCHEMA_NOTE,
        "deliverable": "A-W14-04 pairing criterion refinement - Member A input side",
        "status": STATUS,
        "decision_owner": "Member A and Member B jointly; neither side freezes this alone",
        "tolerance_proposed": False,
        "tolerance_value": None,
        "agreed_with_member_b": False,
        "why_no_number": [
            f"independent thermal sessions on disk: {sessions}; a repeat spread needs "
            f"at least {min_sessions}",
            "door-open events recorded anywhere in committed data: "
            f"{tokens['open_rows']} of {tokens['rows']} rows (the rest are CLOSED or "
            "UNKNOWN), so the disturbance axis has no measured response to bound",
            f"rows whose current value carries no recorded status in this capture: "
            f"{unqualified}, so an electrical gate would key on unqualified values",
            "device_ms is per-boot and host wall-clock is not device time, so pairing "
            "across sessions cannot be done on absolute timestamps either",
        ],
        "captures": [spatial.require_thermal_capture(path, rep.read_rows(path))
                     for path in captures],
        "what_the_real_data_supports": {
            "drop_one_feature_sensitivity": sensitivity,
            "within_session_variability": within_session_variability(primary),
            "ablation_report_verdict": ablation["verdict"],
            "air_only_max_abs_deviation_c": sensitivity["air_only_max_abs_deviation_c"],
            "gradient_max_abs_within_session_c": {
                phase: block["air_gradient"]["max_pairwise_difference_c"]
                for phase, block in spatial_primary["phases"].items()
                if isinstance(block, dict) and "air_gradient" in block},
        },
        "what_the_real_data_cannot_support": [
            "any run-to-run matching band for temperature, gradient or duty: one "
            "session is one session and its within-session drift is a different "
            "quantity",
            "a door-open condition-matching tolerance: no such event is recorded",
            "an electrical matching gate: the values exist but nothing recorded their "
            "validity",
            "per-channel identity across boots: the H8S schema-3 frames carry no sensor "
            "ROM ids, so a later capture's t1 is a slot name, not a probe",
            "a hot-side channel in any chamber-air band: it is a surface, and W07's "
            "includes_hot_side plus cg_w14_spatial.require_air keep it out",
        ],
        "join_keys_b_can_use": {
            "capture": "repository-relative id from cg_thermal_repeatability.capture_id",
            "boot_id": "the session key; one boot_id is one session",
            "device_ms": "per-boot monotonic time; not comparable across boots",
            "conditioning_fingerprint": "hash of device_ms/state/duty/door/boot per row, "
                                        "so two variants provably share one physical run",
            "variant": "name from cg_w14_spatial.VARIANTS, carrying feature_terms, "
                       "feature_roles, is_chamber_air, includes_hot_side",
            "phase": "baseline / cooling / recovery from W07's split_phases",
        },
        "candidate_tolerance_basis_once_data_exists": {
            "form": ("per outcome, the sample (n-1) spread across independent boots, "
                     "with the number of boots stated and the confidence the count "
                     "supports - the same discipline W07 applies to repeatability"),
            "minimum_independent_sessions": min_sessions,
            "must_be_stated_with_any_number": ["n_sessions", "spread_formula",
                                               "representation", "representation_roles",
                                               "includes_hot_side", "phase",
                                               "duty_and_duration"],
            "not_yet_available": True,
        },
        "partial_mean_rule": {
            "rule": ("a mean over fewer terms is a different quantity and must not "
                     "reuse the label (docs/01 517-530); W07 excludes partial-term rows "
                     "from a phase series and counts them"),
            "partial_term_rows_in_this_capture": {
                variant: block["cooling"]["partial_term_rows"]
                for variant, block in ablation["captures"][0]["variants"].items()
                if block.get("cooling", {}).get("usable")},
            "consequence_for_b": ("feature sets differ by which probes they use, not by "
                                  "silently averaging fewer terms under the same name"),
        },
        "asks_for_member_b": [
            "the A/B pairing axes B intends to match on, so A can state which of them "
            "the captures can bound",
            "B's minimum session count per condition, because that sets when a spread "
            "becomes reportable at all",
            "whether B consumes feature sets by variant name (preferred) or by raw term "
            "list, so the labelling stays unambiguous",
            "a joint decision on the docs/01 §20.1 naming question W07 left open, since "
            "it changes which mean any band would apply to",
        ],
        "verdict": {
            "status": STATUS,
            "member_a_input": "DELIVERED",
            "host_verified": True,
            "physically_verified": False,
            "tolerance_frozen": False,
            "blocked_on": "Member B's pairing axes plus the sessions that would bound them",
        },
        "notes": [
            "Nothing here is a proposed threshold. A number appearing in this file is "
            "an observation about one session, and each one says so in its own field "
            "name.",
            "The status stays TEAM_DEPENDENCY until B signs the values; it is not "
            "BLOCKED_HARDWARE, because no hardware is needed to agree the form.",
        ],
    }
    assert_no_invented_tolerance(payload)
    return payload


def _walk(node: object, path: str = "", key: str = ""):
    """Every (path, key, value) in the payload, so the guard can be structural.

    A list element is yielded under its own key: the sentence a reader would mistake
    for an agreement usually lives in a list, not beside a number.
    """
    yield path, key, node
    if isinstance(node, dict):
        for name, value in node.items():
            yield from _walk(value, f"{path}/{name}", str(name))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]", key)


TOLERANCE_KEY = re.compile(
    r"tolerance|matching_band|_band_c|band_c_per_min|matching_tolerance")


def assert_no_invented_tolerance(payload: dict[str, object]) -> None:
    """Fail if this file ever puts a tolerance number in Member A's input.

    Structural rather than a substring scan: the defect to catch is a *numeric value*
    sitting under a tolerance-named key while B has not signed anything, which is what
    an invented band looks like in the artifact a reader actually gets. Phrases are
    checked too, because 'agreed' next to 'tolerance' is the sentence the requirement
    forbids regardless of where the number came from.
    """
    if payload.get("tolerance_proposed") is not False:
        raise AnalysisError("tolerance_proposed must stay False in Member A's input")
    if payload.get("tolerance_value") is not None:
        raise AnalysisError("tolerance_value is set: A-W14-04 freezes tolerances WITH "
                            "Member B, so this file may not carry one")
    for path, key, value in _walk(payload):
        if (TOLERANCE_KEY.search(key) and isinstance(value, (int, float))
                and not isinstance(value, bool)):
            raise AnalysisError(
                f"{path}/{key} carries the number {value}: no tolerance or matching "
                "band may be valued in Member A's input before B signs it")
        if key in ("agreed_with_member_b", "tolerance_frozen") and value is True:
            raise AnalysisError(f"{path}/{key} claims B agreement that has not happened")
    text = " ".join(str(value) for _, _, value in _walk(payload)
                    if isinstance(value, str)).lower()
    for phrase in ("tolerance agreed", "agreed tolerance", "adopted tolerance",
                   "final tolerance", "frozen tolerance", "tolerance is"):
        if phrase in text:
            raise AnalysisError(f"payload says {phrase!r}: A-W14-04 output is an input, "
                                "not an agreed value")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A-W14-04 pairing criterion input")
    parser.add_argument("captures", nargs="+", type=pathlib.Path)
    parser.add_argument("--json", dest="json_out", type=pathlib.Path)
    args = parser.parse_args(argv)
    payload = pairing_input(args.captures)
    print(f"status={payload['status']} tolerance_proposed={payload['tolerance_proposed']}")
    sensitivity = payload["what_the_real_data_supports"]["drop_one_feature_sensitivity"]
    print(f"drop_one_status={sensitivity['status']} "
          f"air_only_max_abs_deviation_c={sensitivity['air_only_max_abs_deviation_c']}")
    if args.json_out is not None:
        spatial.write_json(args.json_out, payload)
        print(f"json={args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
