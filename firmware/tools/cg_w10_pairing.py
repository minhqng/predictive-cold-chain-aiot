"""ColdGuard W10 pairing-tolerance estimator and S2 horizon support.

docs/05A §19 A-W10-04 asks Member A to "estimate variation of initial Tmean,
initial gradient, response" and hand Member B the evidence to freeze a
pair-matching tolerance, and A-W10-05 asks for a ``door->critical`` and
``controller response`` distribution "do not select the ML horizon yourself".

The honest difficulty is that S2 has no data yet, so a tolerance cannot be
estimated *from* S2 pairs. What can be computed, and is, is the **noise floor**:
the smallest temperature change this instrument chain can distinguish from
nothing at all, measured from real thermal frames. That number is the lower
bound on any tolerance worth freezing - a pairing band narrower than the noise
floor would match runs by luck, and a disturbance smaller than it is not
detectable however well the runs were paired. So this module reports:

* the per-probe noise, measured from real thermal frames on contiguous
  quiescent runs of the committed capture. The estimator is **trend-immune**: it
  uses second differences (``sigma = std(second diff)/sqrt(6)``) and rejects any
  run whose fitted slope exceeds a stated threshold. That rejection does work -
  the committed capture has a second OFF segment (seq 832-957) that is the box
  *recovering* after cooling, at 0.043-0.071 degC/s, and pooling it naively with
  the resting segment produced a 0.36 degC "noise" figure roughly 18x the truth;
* the derived minimum detectable disturbance at several horizons, per probe and
  for the chamber-air mean, at a stated z-score, plus a single-frame bound that
  needs no averaging assumption at all;
* what that implies for the S2 protocol: planned door durations whose expected
  rise falls under the floor should not be run at all, because a paired analysis
  of them cannot separate the disturbance from nothing;
* the horizon-support analysis, which states exactly which distributions are
  missing and what capture would fill each one - it does **not** pick a horizon.

The estimator also reports the *achievable* tolerance from the real number of
available runs, which is why the headline answer to "freeze the pair tolerance"
is: the floor can be stated today, the tolerance cannot be frozen until the S2
pilot exists.
"""

from __future__ import annotations

import math

import cg_w09_export as run_export
import cg_w09_noise as noise  # noqa: E402  (the noise figure W09 measured)
import cg_w09_validity as validity
from cg_w09_capture_parser import Frame

PAIRING_VERSION = "w10-pairing-v2"

# Detection z-scores. Stated as choices, not facts: B freezes the operating
# point, Member A only reports what each one costs in detectable magnitude.
Z_SCORES = (1.96, 2.58, 3.0)

# Horizons (seconds after the disturbance onset) at which the floor is reported.
DETECTION_HORIZONS_S = (30, 60, 120, 300, 600)

# The per-probe noise estimator is W09 evidence, not W10 evidence: A-W09-04 publishes
# it in evidence/A/W09/healthy-ranges.json, measured from the S1 capture. It lived in
# this module while both weeks sat on one branch, and the W09 dossier imported it from
# here - which meant the S1 dossier could not be reproduced from a W09-only checkout.
# The estimator now lives in cg_w09_noise.py and this week imports it; these names are
# re-exported so the public surface the published floor formula names is unchanged.
MEASUREMENT_RESOLUTION_C = noise.MEASUREMENT_RESOLUTION_C
QUANTISATION_NOISE_FLOOR_C = noise.QUANTISATION_NOISE_FLOOR_C
WHITE_NOISE_ASSUMPTION = noise.WHITE_NOISE_ASSUMPTION
probe_noise_profile = noise.probe_noise_profile
linear_slope_c_per_s = noise.linear_slope_c_per_s
second_difference_sigma = noise.second_difference_sigma
successive_difference_sigma = noise.successive_difference_sigma


def detection_floor_formula(z: float) -> str:
    """The formula with the z factor it is actually evaluated at, spelled out."""
    return (
        f"floor(H) = {z} * sigma_second_diff / sqrt(H)   "
        "[z = the detection z-score; sigma_second_diff = std(second differences)/sqrt(6), "
        "the trend-immune estimator of probe_noise_profile(); H in seconds at 1 Hz cadence]"
    )


def minimum_detectable_disturbance(frames: list[Frame], z: float = 2.58) -> dict:
    """The smallest rise detectable at each horizon, per probe and per mean.

    This is the number Member B actually needs before freezing a pairing band:
    a tolerance below this measures noise, not a worse-matched pair.
    """
    profile = probe_noise_profile(frames)
    per_probe = {
        slot: entry["sigma_c"]
        for slot, entry in profile["probes"].items()
        if entry.get("sigma_c") is not None and slot != "t2"
    }
    if not per_probe:
        return {"error": "no quiescent segment found; the floor cannot be estimated"}
    mean_sigma = math.sqrt(sum(v ** 2 for v in per_probe.values()) / len(per_probe) ** 2)
    horizons: dict[str, dict] = {}
    for horizon in DETECTION_HORIZONS_S:
        shrink = 1.0 / math.sqrt(horizon)
        horizons[f"{horizon}s"] = {
            "per_probe_c": {
                slot: round(z * sigma * shrink, 5) for slot, sigma in sorted(per_probe.items())
            },
            "chamber_air_mean_c": round(z * mean_sigma * shrink, 5),
        }
    worst_probe = max(per_probe, key=lambda s: per_probe[s])
    single_frame = {
        slot: round(z * sigma, 5) for slot, sigma in sorted(per_probe.items())
    }
    return {
        "estimator_version": PAIRING_VERSION,
        "z_score": z,
        "z_score_meaning": (
            "the detection z-score is a multiplier on the sigma, not a property of the rig: the "
            "floor below is z * sigma / sqrt(H), so a reader who recomputes it without the z "
            "factor gets a number 1/z of the published one"
        ),
        "detection_floor_formula": detection_floor_formula(z),
        "sigma_estimator": profile["estimator"],
        "sigma_by_probe_c": {k: round(v, 6) for k, v in sorted(per_probe.items())},
        "sigma_chamber_air_mean_c": round(mean_sigma, 6),
        "chamber_air_slots": list(per_probe),
        "single_frame_floor_c": single_frame,
        "single_frame_floor_binding_c": round(max(single_frame.values()), 5),
        "single_frame_floor_reading": (
            "a rise on one probe in one frame is separable from nothing above "
            f"{round(max(single_frame.values()), 4)} degC; this bound needs no averaging "
            "assumption and is the conservative one"
        ),
        "horizons": horizons,
        "binding_probe": worst_probe,
        "binding_position": run_export.FROZEN_SENSOR_GEOMETRY[worst_probe]["position"],
        "practical_floor_c": round(
            z * per_probe[worst_probe] * (1.0 / math.sqrt(DETECTION_HORIZONS_S[1])), 5
        ),
        "practical_floor_horizon_s": DETECTION_HORIZONS_S[1],
        "assumption": WHITE_NOISE_ASSUMPTION,
        "profile": profile,
        "reading": (
            "any door disturbance whose chamber-air rise within "
            f"{DETECTION_HORIZONS_S[1]} s is below "
            f"{round(z * per_probe[worst_probe] / math.sqrt(DETECTION_HORIZONS_S[1]), 4)} degC is "
            "indistinguishable from nothing on this rig, no matter how well the pair is matched"
        ),
        "is_physical_measurement": True,
        "note": (
            "the sigma is measured from real thermal frames; the detectable-magnitude statement "
            "is a property of the instrument chain, not of any disturbance that has been captured"
        ),
    }


def achievable_tolerance_from_available_runs(frames_by_run: dict[str, list[Frame]]) -> dict:
    """Report what the current run count can and cannot support.

    A pairing tolerance is a spread statistic over matched pairs. With one real
    capture there is no spread to estimate, so the answer must be 'not yet'
    rather than a number dressed up from a single sample.
    """
    counts = {}
    for label, frames in sorted(frames_by_run.items()):
        usable = sum(
            1 for verdict in validity.evaluate_frames(frames)
            if "S1_NORMAL_BASELINE" in verdict.usable_for
        )
        counts[label] = {"frames": len(frames), "usable_frames": usable}
    n_runs = len(frames_by_run)
    return {
        "runs_available": n_runs,
        "per_run": counts,
        "initial_tmean_spread_c": None if n_runs < 2 else "computable",
        "initial_gradient_spread_c_per_s": None if n_runs < 2 else "computable",
        "response_spread": None if n_runs < 2 else "computable",
        "pairing_tolerance_c": None,
        "status_label": "NEED_USER_ACTION",
        "why": (
            f"{n_runs} physical capture(s) are available; a tolerance is a between-run spread and "
            "cannot be estimated from one run. Reporting a number here would be inventing a "
            "variance that was never observed."
        ),
        "what_can_be_frozen_now": (
            "only the noise floor from minimum_detectable_disturbance(): it bounds any tolerance "
            "B chooses, and it is measured rather than assumed"
        ),
    }


def horizon_support(s2_events_available: int, floor: dict) -> dict:
    """A-W10-05: what B needs to pick a horizon, and what is missing.

    Deliberately does not choose a horizon; it prices the two distributions in
    captures.
    """
    return {
        "requirement": "docs/05A §19 A-W10-05",
        "status_label": "NEED_USER_ACTION" if s2_events_available == 0 else "REAL_DATA_ANALYZED",
        "s2_pilot_disturbances_available": s2_events_available,
        "target": ">=4-6 valid pilot disturbances (docs/05A §19 A-W10-03)",
        "distributions_requested": {
            "door_to_critical_s": {
                "computable_now": False,
                "requires": [
                    "an operator-timed OPEN edge per run",
                    "a frozen critical candidate threshold (that is Member D's safety contract, "
                    "not a Member A number)",
                    "chamber-air series that crosses it after the edge",
                ],
                "blocking_reason": "no S2 pilot capture exists",
            },
            "controller_response_s": {
                "computable_now": False,
                "requires": [
                    "a running controller, which is Member D's; the shipped firmware runs no "
                    "policy state (docs/05A §17 notes device_mode is the controller state only)",
                    "the same S2 disturbances replayed under that controller",
                ],
                "blocking_reason": "no controller in the loop and no S2 capture",
            },
        },
        "what_is_supported_today": {
            "noise_floor_c": floor.get("practical_floor_c"),
            "noise_floor_horizon_s": floor.get("practical_floor_horizon_s"),
            "single_frame_floor_c": floor.get("single_frame_floor_binding_c"),
            "horizon_curve_c": {k: v["chamber_air_mean_c"] for k, v in floor.get("horizons", {}).items()},
            "reading": (
                "the shortest horizon at which a disturbance is separable from nothing can be "
                "stated today; the door->critical *distribution* cannot"
            ),
        },
        "member_b_decision_inputs_not_supplied_by_member_a": [
            "ML horizon choice",
            "pair-matching tolerance value",
            "critical-threshold definition",
        ],
        "honesty": [
            "no distribution here was fabricated from a single run",
            "the floor is an optimistic bound under the stated white-noise assumption",
        ],
    }
