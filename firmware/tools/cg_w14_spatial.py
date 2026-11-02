"""ColdGuard W14 role-aware spatial statistics and ablation support (A-W14-02/03).

Standard library only, host-only: nothing here drives or reads hardware, and nothing
here measured anything new. It reads captures that are already committed and answers
two questions week 14 asks:

* which sensor feature sets can be compared **on the same physical run**, so Member B
  can ablate one probe against three without a second bench session (A-W14-02);
* what the role-aware spatial structure of the field actually is, on the sessions that
  exist, and what is simply not computable (A-W14-03).

Everything role- and representation-related is imported from W07
(``cg_thermal_repeatability``) rather than restated here: ``AS_BUILT_ROLES`` is the one
slot-to-position map, ``REPRESENTATIONS``/``terms_of``/``includes_hot_side`` are the one
definition table. This module adds only what W07 does not expose - a mean over an
arbitrary term tuple, so single-probe variants exist - and a differential test pins
that helper against W07's own ``tmean`` for every registered representation, so the
two can never drift apart.

Position vocabulary (the operator-frozen geometry, via W07):

    t1 = CHAMBER_CENTER   t2 = TEC_HOT_SIDE   t3 = CHAMBER_BOTTOM   t4 = CHAMBER_NEAR_DOOR

Discipline this module exists to enforce

* **T2 never enters a chamber-air statistic.** Whether a term set touches the hot side
  is derived from W07's role map (``terms_include_hot_side``), and a variant labelled
  chamber air whose terms touch it raises instead of computing.
* **One session is one session.** Within-session sample dispersion is published as a
  `single_session_observation`; it is never called a distribution, and the repeat
  distribution the canonical ask names needs independent sessions.
* **A disturbance that was never applied has no response.** Door-open events are found
  by transition in the data; none exists in committed captures, so the answer is
  NOT_COMPUTABLE with the re-derived tally, never an estimate.
* The 2026-11-02 touch session is classed ``PROBE_IDENTIFICATION`` and is refused here
  before a single number is computed, per ``evidence/A/W07/probe-identification-v0.md``
  ("Do not reuse these captures ... for any thermal-response statistic").
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import pathlib
import statistics
import sys

import cg_thermal_repeatability as rep
from cg_thermal_repeatability import (AS_BUILT_ROLES, REPRESENTATIONS, AnalysisError,
                                      includes_hot_side, number, reading, terms_of)

SCHEMA_NOTE = "w14-spatial-v0"
MIN_SESSIONS_DEFAULT = 3
HOT_SIDE_ROLE = AS_BUILT_ROLES["t2_c"]
AIR_TERMS = tuple(term for term in AS_BUILT_ROLES if AS_BUILT_ROLES[term] != HOT_SIDE_ROLE)
IDENTIFICATION_MARKER = "PROBE_IDENTIFICATION"
IDENTIFICATION_PATH_MARKER = "probe-identification"
OPEN_DOOR_TOKENS = {"1", "OPEN", "TRUE", "Y", "YES"}
CLOSED_DOOR_TOKENS = {"0", "CLOSED", "FALSE", "N", "NO"}
UNKNOWABLE_DOOR_TOKENS = {"", "UNKNOWN", "UNCONFIRMED", "MISSING", "UNAVAILABLE", "UNRECORDED"}

REPO_ROOT = rep.REPO_ROOT


# ---------------------------------------------------------------------------
# variants: W07's registered representations, plus the single-probe sets W07 lacks
# ---------------------------------------------------------------------------

def _variant(name: str, terms: tuple[str, ...], source: str,
             kind: str) -> dict[str, object]:
    """One sensor feature set, labelled by probe, role and hot-side exposure."""
    touches_hot = terms_include_hot_side(terms)
    return {
        "name": name,
        "terms": list(terms),
        "roles": [AS_BUILT_ROLES[term] for term in terms],
        "includes_hot_side": touches_hot,
        "is_chamber_air": (not touches_hot) and len(terms) > 0,
        "kind": kind,
        "source": source,
    }


def terms_include_hot_side(terms: tuple[str, ...] | list[str]) -> bool:
    """Derived from W07's role map, so the hot side cannot be re-declared air here.

    The equivalence of this predicate with W07's own ``includes_hot_side`` flag is
    pinned by a test over every registered representation: if the two ever disagree,
    one of them is wrong and the suite says which.
    """
    return any(AS_BUILT_ROLES.get(term) == HOT_SIDE_ROLE for term in terms)


W07_SOURCE = "cg_thermal_repeatability.REPRESENTATIONS (imported, not copied)"

VARIANTS: dict[str, dict[str, object]] = {
    name: _variant(name, terms_of(name), W07_SOURCE,
                   "single_probe" if len(terms_of(name)) == 1 else "multi_probe")
    for name in REPRESENTATIONS
}
VARIANTS.update({
    name: _variant(name, terms, "cg_w14_spatial (W07 registers no single-probe set)",
                   "single_probe")
    for name, terms in (
        ("air_t1_center_v0", ("t1_c",)),
        ("air_t3_bottom_v0", ("t3_c",)),
        ("air_t4_near_door_v0", ("t4_c",)),
        ("hot_t2_surface_v0", ("t2_c",)),
        ("air_pair_center_bottom_v0", ("t1_c", "t3_c")),
        ("air_pair_center_door_v0", ("t1_c", "t4_c")),
        ("air_pair_bottom_door_v0", ("t3_c", "t4_c")),
    )
})
ABLATION_VARIANTS = tuple(name for name in VARIANTS if name != "tmean_all4_v0")


def require_air(name: str) -> dict[str, object]:
    """A variant that claims to be chamber air must not touch the hot side.

    Raising here is the mechanism behind the requirement that no chamber-air
    statistic can ever include T2: the label is checked against the role map at the
    moment a statistic is computed, not asserted in a document.
    """
    variant = VARIANTS[name]
    if variant["is_chamber_air"] and terms_include_hot_side(variant["terms"]):
        raise AnalysisError(
            f"{name} is labelled chamber air but its terms "
            f"{variant['terms']} include the {HOT_SIDE_ROLE} probe")
    return variant


# ---------------------------------------------------------------------------
# row-level value handling (mirrors W07 tallies exactly; pinned by tests)
# ---------------------------------------------------------------------------

def mean_of_terms(row: dict[str, str],
                  terms: tuple[str, ...] | list[str]) -> tuple[float | None, int, int]:
    """(mean, usable_count, term_count) over an arbitrary term tuple.

    W07's ``tmean`` only accepts a registered representation name, so arbitrary
    feature sets had nowhere to go; the value/status rules are W07's own ``number``
    and the partial-term bookkeeping matches ``tmean``'s tuple shape by test.
    """
    values = [value for value in (number(row, term) for term in terms)
              if value is not None]
    if not values:
        return None, 0, len(terms)
    return sum(values) / len(values), len(values), len(terms)


def term_points(rows: list[dict[str, str]], terms: tuple[str, ...] | list[str]
                ) -> tuple[list[tuple[float, float]], dict[str, int]]:
    """Full-term (device minutes, mean) points, with every excluded row counted.

    A row missing one term is a different quantity and joins no series
    (docs/01 517-530); that is W07's rule, kept here so partial means cannot leak into
    a spatial or ablation figure.
    """
    points: list[tuple[float, float]] = []
    tallies = {"partial_term_rows": 0, "no_term_rows": 0, "unqualified_rows": 0}
    for row in rows:
        value, usable, total = mean_of_terms(row, terms)
        if value is None:
            tallies["no_term_rows"] += 1
            continue
        if usable != total:
            tallies["partial_term_rows"] += 1
            continue
        if any(reading(row, term)[1] == "unqualified" for term in terms):
            tallies["unqualified_rows"] += 1
        points.append(((number(row, "device_ms") or 0.0) / 60000.0, value))
    return points, tallies


def least_squares(points: list[tuple[float, float]]) -> float | None:
    """Whole-series slope; agrees with W07's trailing estimator on a full window."""
    if len(points) < 2:
        return None
    n = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    return (n * sxy - sx * sy) / denom


# ---------------------------------------------------------------------------
# capture admission: class, provenance, conditioning fingerprint
# ---------------------------------------------------------------------------

def capture_class(path: pathlib.Path, rows: list[dict[str, str]]) -> str:
    """PROBE_IDENTIFICATION is refused as a statistic source; everything else is thermal."""
    lowered_path = rep.capture_id(path).lower()
    markers = [IDENTIFICATION_MARKER.lower(), IDENTIFICATION_PATH_MARKER.lower()]
    if any(marker in lowered_path for marker in markers):
        return IDENTIFICATION_MARKER
    fields = " ".join(str(row.get(key, "")) for row in rows[:3]
                      for key in ("session", "stage")).lower()
    if IDENTIFICATION_MARKER.lower() in fields or "identification" in fields:
        return IDENTIFICATION_MARKER
    return "THERMAL_RESPONSE"


def require_thermal_capture(path: pathlib.Path,
                            rows: list[dict[str, str]]) -> dict[str, object]:
    """Refuse the touch session before a number is computed, and say which rule did it."""
    kind = capture_class(path, rows)
    if kind == IDENTIFICATION_MARKER:
        raise AnalysisError(
            f"{rep.capture_id(path)} is classed {IDENTIFICATION_MARKER}: "
            "evidence/A/W07/probe-identification-v0.md forbids reusing it for any "
            "thermal-response or spatial statistic")
    boots = sorted({str(row.get("boot_id") or "UNRECORDED") for row in rows})
    return {
        "capture": rep.capture_id(path),
        "class": kind,
        "rows": len(rows),
        "boot_ids": boots,
        "independent_sessions": len(boots),
        "provenance": {
            "session": rows[0].get("session", "UNRECORDED"),
            "device_ms_first": rows[0].get("device_ms"),
            "device_ms_last": rows[-1].get("device_ms"),
        },
    }


CONDITION_COLUMNS = ("device_ms", "state", "pwm_applied_permille", "door_open", "boot_id")


def conditioning_fingerprint(rows: list[dict[str, str]]) -> str:
    """Hash of the physical-condition columns, so 'same run' is checkable, not claimed.

    Two ablation variants may differ only in which probes they read: every commanded
    and sensed condition column must hash the same, which is exactly the control
    docs/05A A-W14-02 asks for (one sensor set versus three on the same physical run).
    """
    digest = hashlib.sha256()
    for row in rows:
        digest.update("|".join(str(row.get(column, ""))
                               for column in CONDITION_COLUMNS).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()[:16]


# ---------------------------------------------------------------------------
# A-W14-02 ablation support
# ---------------------------------------------------------------------------

def variant_phase_metrics(rows: list[dict[str, str]], phase: str,
                          name: str) -> dict[str, object]:
    """One variant's response over one phase of one capture, on full-term rows only."""
    variant = require_air(name)
    terms = tuple(variant["terms"])
    points, tallies = term_points(rows, terms)
    base = {
        "variant": name,
        "phase": phase,
        "feature_terms": list(terms),
        "feature_roles": list(variant["roles"]),
        "includes_hot_side": bool(variant["includes_hot_side"]),
        "is_chamber_air": bool(variant["is_chamber_air"]),
        "variant_kind": variant["kind"],
        "variant_source": variant["source"],
        "rows_read": len(rows),
        **tallies,
    }
    if len(points) < 2:
        return {**base, "usable": False, "samples": len(points),
                "skipped_rows": len(rows) - len(points),
                "reason": "FEWER_THAN_TWO_FULL_TERM_SAMPLES"}
    whole = least_squares(points)
    trailing = rep.trailing_slope_c_per_min(points)
    return {
        **base,
        "usable": True,
        "samples": len(points),
        "skipped_rows": len(rows) - len(points),
        "duration_min": round(points[-1][0] - points[0][0], 4),
        "start_c": round(points[0][1], 4),
        "end_c": round(points[-1][1], 4),
        "min_c": round(min(p[1] for p in points), 4),
        "max_c": round(max(p[1] for p in points), 4),
        "delta_c": round(points[-1][1] - points[0][1], 4),
        "whole_phase_slope_c_per_min": None if whole is None else round(whole, 6),
        "trailing_slope_c_per_min": None if trailing is None else round(trailing, 6),
        "slope_is_not_a_phase_summary": trailing is not None and whole is not None
                                       and abs(trailing - whole) > 1e-9,
        "mean_c": round(statistics.fmean(p[1] for p in points), 4),
        "sd_within_session_sample_c": round(statistics.stdev(p[1] for p in points), 4)
                                      if len(points) > 1 else None,
    }


def ablation_matrix(paths: list[pathlib.Path], variants: tuple[str, ...] = ABLATION_VARIANTS,
                    min_sessions: int = MIN_SESSIONS_DEFAULT) -> dict[str, object]:
    """Per-variant, per-phase metrics from the SAME rows, plus the control proof."""
    out: dict[str, object] = {
        "schema": SCHEMA_NOTE,
        "purpose": ("A-W14-02 logical ablation support: one-sensor feature sets versus "
                    "the three-sensor chamber-air set, taken from the same physical "
                    "rows so a comparison is physical-condition-controlled, not "
                    "run-to-run"),
        "canonical_rule": ("docs/05A A-W14-02: do NOT unplug T2/T3 for core A1; B "
                           "selects the feature set logically from the same runs"),
        "hot_side_policy": (f"{HOT_SIDE_ROLE} is a surface on the TEC stack, never "
                            "chamber air: no variant labelled is_chamber_air may "
                            "include it (require_air raises instead)"),
        "captures": [],
        "variants": list(variants),
    }
    per_variant_rows: dict[str, list[dict[str, object]]] = {name: [] for name in variants}
    for path in paths:
        rows = rep.read_rows(path)
        admission = require_thermal_capture(path, rows)
        phases = rep.split_phases(rows)
        block_variants: dict[str, object] = {}
        fingerprint = conditioning_fingerprint(rows)
        for name in variants:
            per_phase = {}
            for phase, phase_rows in phases.items():
                if phase == "undetermined" or not phase_rows:
                    continue
                metrics = variant_phase_metrics(phase_rows, phase, name)
                metrics["conditioning_fingerprint"] = fingerprint
                per_phase[phase] = metrics
                if metrics["usable"] and phase in ("baseline", "cooling", "recovery"):
                    per_variant_rows[name].append(metrics)
            block_variants[name] = per_phase
        out["captures"].append({**admission,
                                "conditioning_fingerprint": fingerprint,
                                "condition_columns": list(CONDITION_COLUMNS),
                                "undetermined_rows": len(phases["undetermined"]),
                                "variants": block_variants})
        out["physical_condition_control"] = {
            "one_fingerprint_per_capture": True,
            "note": ("every variant of a capture is computed over the same rows: the "
                     "fingerprint hashes device_ms/state/pwm_applied_permille/door_open/"
                     "boot_id, so two variants that differ in anything but the probe "
                     "set would disagree here and are reported, not averaged"),
        }
    sessions = {boot for capture in out["captures"] for boot in capture["boot_ids"]}
    # type: ignore[union-attr]
    out["per_variant_summary"] = {
        name: _variant_summary(rows_list, min_sessions, len(sessions))
        for name, rows_list in per_variant_rows.items()}
    out["verdict"] = {
        "independent_sessions": len(sessions),
        "min_sessions_for_a_repeat_distribution": min_sessions,
        "ablation_differences_are_within_session_observations": len(sessions) < min_sessions,
        "repeat_distribution_computed": len(sessions) >= min_sessions,
        "not_a_repeat_distribution": len(sessions) < min_sessions,
        "note": ("variant differences below are measured on one session's rows, which "
                 "controls physical conditions exactly and therefore says nothing about "
                 "run-to-run behaviour: both facts are published together"),
    }
    out["notes"] = [
        "Host analysis of committed captures: nothing was energized, flashed or moved.",
        "Single-probe variants exist because A-W14-02 asks for one sensor set versus "
        "three; they are labelled by role so a reader sees which physical position a "
        "feature is standing for.",
        "hot_t2_surface_v0 is published as a surface temperature and is excluded from "
        "every chamber-air statistic by require_air.",
        "tmean_all4_v0 is a W07 sensitivity check, not an ablation candidate: it mixes "
        "a hot-side surface into an air mean, so it is dropped from ABLATION_VARIANTS.",
    ]
    return out


def _variant_summary(metrics: list[dict[str, object]], min_sessions: int,
                     sessions: int) -> dict[str, object]:
    phases = sorted({str(m["phase"]) for m in metrics})
    deltas = [float(m["delta_c"]) for m in metrics if isinstance(m.get("delta_c"), (int, float))]
    return {
        "phases": phases,
        "usable_segment_count": len(metrics),
        "segment_kind": "segments of one boot" if sessions <= 1 else "segments across sessions",
        "delta_c_values": deltas,
        "independent_sessions": sessions,
        "status": ("SINGLE_SESSION_OBSERVATION" if sessions < min_sessions
                   else "MULTI_SESSION_OBSERVATION"),
        "not_a_distribution": sessions < min_sessions,
    }


def ablation_csv_rows(report: dict[str, object]) -> list[tuple[object, ...]]:
    """Long-format, variant-labelled series so Member B can join on device_ms."""
    header = ("capture", "boot_id", "phase", "variant", "feature_terms", "feature_roles",
              "is_chamber_air", "includes_hot_side", "sample_index", "device_ms",
              "pwm_applied_permille", "door_open", "feature_c", "conditioning_fingerprint")
    rows: list[tuple[object, ...]] = [header]
    for capture in report["captures"]:  # type: ignore[union-attr]
        source = rep.capture_path(str(capture["capture"]))
        rows_read = rep.read_rows(source)
        phases = rep.split_phases(rows_read)
        by_device = {row.get("device_ms"): row for row in rows_read}
        for name in report["variants"]:  # type: ignore[union-attr]
            variant = VARIANTS[name]
            for phase, metrics in capture["variants"][name].items():  # type: ignore[union-attr,index]
                if not metrics["usable"]:
                    continue
                points, _ = term_points(phases[phase], tuple(variant["terms"]))
                for index, (minutes, value) in enumerate(points):
                    # term_points keeps the capture's own monotonic device_ms, so the
                    # join back to the conditioning columns is exact, not interpolated.
                    device_ms = round(minutes * 60000.0, 3)
                    source_row = by_device.get(_nearest_device_ms(rows_read, device_ms), {})
                    rows.append((
                        source.name, capture["boot_ids"][0] if capture["boot_ids"] else "",
                        phase, name, ";".join(variant["terms"]), ";".join(variant["roles"]),
                        int(bool(variant["is_chamber_air"])),
                        int(bool(variant["includes_hot_side"])), index,
                        round(device_ms, 3), source_row.get("pwm_applied_permille", ""),
                        source_row.get("door_open", ""), round(value, 4),
                        metrics["conditioning_fingerprint"]))
    return rows


def _nearest_device_ms(rows: list[dict[str, str]], target: float) -> str:
    """The row whose device_ms is closest, so the feature joins to its own conditions."""
    best, best_gap = "", float("inf")
    for row in rows:
        value = number(row, "device_ms")
        if value is None:
            continue
        gap = abs(value - target)
        if gap < best_gap:
            best, best_gap = row.get("device_ms", ""), gap
    return best


# ---------------------------------------------------------------------------
# A-W14-03 spatial statistics
# ---------------------------------------------------------------------------

def pair_names(terms: tuple[str, ...] | list[str]) -> list[tuple[str, str]]:
    terms = list(terms)
    return [(terms[i], terms[j]) for i in range(len(terms)) for j in range(i + 1, len(terms))]


def pair_label(a: str, b: str) -> str:
    return f"{a}-vs-{b} ({AS_BUILT_ROLES[a]} vs {AS_BUILT_ROLES[b]})"


def pairwise_series(rows: list[dict[str, str]], terms: tuple[str, ...] | list[str]
                    ) -> tuple[list[dict[str, object]], dict[str, int]]:
    """Per-sample signed differences of every pair, plus the excluded-row tallies."""
    tallies = {"usable_pairs": 0, "partial_rows": 0, "invalid_rows": 0}
    series: list[dict[str, object]] = []
    for row in rows:
        values: dict[str, float] = {}
        states: list[str] = []
        for term in terms:
            value, state = reading(row, term)
            states.append(state)
            if state in ("ok", "unqualified") and value is not None:
                values[term] = value
        if len(values) == len(terms):
            deltas = {f"{a}|{b}": round(values[a] - values[b], 4)
                      for a, b in pair_names(terms)}
            series.append({"device_ms": row.get("device_ms", ""),
                           "differences": deltas,
                           "all_terms_ok": all(s == "ok" for s in states)})
            tallies["usable_pairs"] += 1
        elif values:
            tallies["partial_rows"] += 1
        else:
            tallies["invalid_rows"] += 1
    return series, tallies


def pair_agreement(rows: list[dict[str, str]], terms: tuple[str, ...] | list[str],
                   phase: str, sessions: int,
                   min_sessions: int = MIN_SESSIONS_DEFAULT) -> dict[str, object]:
    """Within-session dispersion of each pairwise difference. A single session, named.

    The word this function must never earn is "distribution": these numbers describe
    one boot's samples, which is where a repeat distribution would need >= min_sessions
    independent sessions. The status field says which it is, from the session count it
    was given.
    """
    series, tallies = pairwise_series(rows, terms)
    per_pair: dict[str, object] = {}
    for a, b in pair_names(terms):
        key = f"{a}|{b}"
        values = [float(sample["differences"][key]) for sample in series]
        if not values:
            per_pair[pair_label(a, b)] = {"status": "NO_SAMPLES", "n": 0}
            continue
        spread = statistics.stdev(values) if len(values) > 1 else None
        extreme = max(values, key=abs)
        extreme_sample = max(series, key=lambda s: abs(float(s["differences"][key])))
        per_pair[pair_label(a, b)] = {
            "status": ("SINGLE_SESSION_OBSERVATION" if sessions < min_sessions
                       else "MULTI_SESSION_OBSERVATION"),
            "not_a_distribution": sessions < min_sessions,
            "independent_sessions": sessions,
            "n": len(values),
            "mean_c": round(statistics.fmean(values), 4),
            "sd_within_session_sample_c": None if spread is None else round(spread, 4),
            "min_c": round(min(values), 4),
            "max_c": round(max(values), 4),
            "max_abs_c": round(abs(extreme), 4),
            "max_abs_device_ms": extreme_sample["device_ms"],
            "sign_consistency_fraction": round(
                sum(1 for v in values if (v >= 0) == (extreme >= 0)) / len(values), 4),
            "hot_side_pair": terms_include_hot_side([a, b]),
            "read_as": ("surface-to-air separation, not an air gradient"
                        if terms_include_hot_side([a, b]) else
                        "air-to-air gradient inside the chamber volume"),
        }
    return {
        "phase": phase,
        "terms": list(terms),
        "roles": [AS_BUILT_ROLES[t] for t in terms],
        "includes_hot_side": terms_include_hot_side(list(terms)),
        "tallies": tallies,
        "pairs": per_pair,
        "max_pairwise_difference_c": max(
            (float(block["max_abs_c"]) for block in per_pair.values()
             if isinstance(block, dict) and "max_abs_c" in block), default=None),
    }


def disturbance_tokens(rows: list[dict[str, str]]) -> dict[str, object]:
    """What the door field actually says, recomputed rather than trusted."""
    tally: dict[str, int] = {}
    for row in rows:
        token = (row.get("door_open") or "MISSING").strip() or "MISSING"
        tally[token] = tally.get(token, 0) + 1
    open_rows = sum(count for token, count in tally.items() if token in OPEN_DOOR_TOKENS)
    return {"door_open_token_tally": dict(sorted(tally.items())),
            "rows": len(rows), "open_rows": open_rows,
            "unknowable_rows": sum(count for token, count in tally.items()
                                   if token in UNKNOWABLE_DOOR_TOKENS),
            "confirmed_closed_rows": sum(count for token, count in tally.items()
                                         if token in CLOSED_DOOR_TOKENS)}


def door_events(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    """CLOSED-to-OPEN transitions actually present in the capture (usually none)."""
    events: list[dict[str, object]] = []
    previous = None
    for row in rows:
        token = (row.get("door_open") or "MISSING").strip() or "MISSING"
        current = ("OPEN" if token in OPEN_DOOR_TOKENS else
                   "CLOSED" if token in CLOSED_DOOR_TOKENS else "UNKNOWN")
        if previous == "CLOSED" and current == "OPEN":
            events.append({"device_ms": row.get("device_ms", ""),
                           "polarity": row.get("door_polarity", "UNRECORDED")})
        if current != "UNKNOWN":
            previous = current
    return events


def disturbance_response(rows: list[dict[str, str]], terms: tuple[str, ...] | list[str],
                         min_sessions: int = MIN_SESSIONS_DEFAULT) -> dict[str, object]:
    """Disturbance-specific spatial response, or the honest reason there is none."""
    events = door_events(rows)
    tokens = disturbance_tokens(rows)
    if not events:
        return {
            "status": "NOT_COMPUTABLE",
            "reason": ("no door-open transition exists in the capture: the field is "
                       "never OPEN, so there is no applied disturbance whose spatial "
                       "response could be measured. Estimating one would be inventing "
                       "a physical event."),
            "evidence": tokens,
            "boot_ids": sorted({str(row.get("boot_id") or "UNRECORDED") for row in rows}),
            "independent_sessions": len({str(row.get("boot_id") or "UNRECORDED")
                                         for row in rows}),
            "min_sessions_required": min_sessions,
            "what_would_make_it_computable": (
                "a supervised session that opens the door to a recorded extent and "
                "holds it for a bounded window, with door_polarity CONFIRMED on the "
                "open rows, repeated at least the required number of times"),
        }
    windows = []
    for event in events:
        start = number({"device_ms": event["device_ms"]}, "device_ms") or 0.0
        segment = [row for row in rows
                   if (number(row, "device_ms") or 0.0) >= start - 30000.0]
        windows.append({"device_ms": event["device_ms"],
                        "polarity": event["polarity"],
                        "response": pair_agreement(segment, terms, "disturbance", 1,
                                                   min_sessions)})
    return {"status": "COMPUTED_FROM_RECORDED_EVENTS", "events": len(events),
            "windows": windows, "evidence": tokens}


def spatial_report(paths: list[pathlib.Path], min_sessions: int = MIN_SESSIONS_DEFAULT
                   ) -> dict[str, object]:
    """Everything A-W14-03 can honestly say about the sessions on disk."""
    captures: list[dict[str, object]] = []
    all_boot_ids: set[str] = set()
    for path in paths:
        rows = rep.read_rows(path)
        admission = require_thermal_capture(path, rows)
        all_boot_ids.update(admission["boot_ids"])  # type: ignore[arg-type]
        phases = rep.split_phases(rows)
        sessions = len(admission["boot_ids"])
        block = {**admission, "phases": {}}
        for phase in ("baseline", "cooling", "recovery"):
            phase_rows = phases.get(phase) or []
            if not phase_rows:
                block["phases"][phase] = {"status": "NO_ROWS_IN_PHASE"}
                continue
            # A phase block can only ever describe the session its rows came from, so
            # its own capture's session count labels it - not the corpus total.
            air = pair_agreement(phase_rows, list(AIR_TERMS), phase, sessions, min_sessions)
            with_hot = pair_agreement(phase_rows, list(AS_BUILT_ROLES), phase, sessions,
                                      min_sessions)
            block["phases"][phase] = {
                "air_gradient": air,
                "air_vs_hot_surface": with_hot,
                "phase_max_pairwise_difference_c": max(
                    (float(pair["max_abs_c"]) for pair in with_hot["pairs"].values()
                     if isinstance(pair, dict) and "max_abs_c" in pair), default=None),
            }
        block["disturbance_response"] = disturbance_response(rows, list(AIR_TERMS),
                                                             min_sessions)
        block["electrical_status_note"] = (
            "current/voltage status cells are empty and power/energy have no status "
            "column in this capture, so no electrical figure here is status-checked "
            "(W07 counts the same rows unqualified)"
            if any(reading(row, "current_a")[1] == "unqualified" for row in rows) else
            "electrical statuses were recorded")
        captures.append(block)

    sessions = len(all_boot_ids)
    return {
        "schema": SCHEMA_NOTE,
        "deliverable": "A-W14-03 spatial statistics",
        "air_terms": list(AIR_TERMS),
        "air_roles": [AS_BUILT_ROLES[t] for t in AIR_TERMS],
        "hot_side_term": "t2_c",
        "hot_side_role": HOT_SIDE_ROLE,
        "captures": captures,
        "gradient_distribution": {
            "status": ("NOT_COMPUTABLE_AS_DISTRIBUTION" if sessions < min_sessions
                       else "COMPUTED_ACROSS_SESSIONS"),
            "independent_sessions": sessions,
            "min_sessions_required": min_sessions,
            "within_session_gradient_series_provided": True,
            "reason": ("a distribution needs independent sessions and the captures hold "
                       f"{sessions}; the per-sample series below is a single-session "
                       "observation and is labelled so everywhere it appears"
                       if sessions < min_sessions else
                       "gradient statistics span the sessions listed above"),
        },
        "max_pairwise_difference": {
            name: [capture["phases"][name]["phase_max_pairwise_difference_c"]
                   for capture in captures
                   if isinstance(capture["phases"].get(name), dict)
                   and "phase_max_pairwise_difference_c" in capture["phases"][name]]
            for name in ("baseline", "cooling", "recovery")
        },
        "disturbance_specific_response": {
            "status": ("NOT_COMPUTABLE" if all(
                capture["disturbance_response"]["status"] == "NOT_COMPUTABLE"
                for capture in captures) else "PARTIAL"),
            "per_capture": [capture["disturbance_response"] for capture in captures],
        },
        "verdict": {
            "independent_sessions": sessions,
            "single_session_observation": sessions < min_sessions,
            "n_never_becomes_a_distribution": True,
            "distribution_computed": sessions >= min_sessions,
            "disturbance_response_computed": any(
                capture["disturbance_response"]["status"] != "NOT_COMPUTABLE"
                for capture in captures),
        },
        "notes": [
            "Air gradients are computed between the three chamber-air positions only; "
            "T2 is reported as a surface, in its own pair block, and never as air.",
            "Row counts are stated per phase so a reader can see what n=1 session means.",
            "Nothing here was measured for this report; the captures predate it.",
        ],
    }


def write_json(path: pathlib.Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: pathlib.Path, rows: list[tuple[object, ...]]) -> None:
    """LF-only CSV, so a hash pin is platform independent."""
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    path.write_bytes(buffer.getvalue().encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("captures", nargs="+", type=pathlib.Path)
    parser.add_argument("--min-sessions", type=int, default=MIN_SESSIONS_DEFAULT)
    parser.add_argument("--json", dest="json_out", type=pathlib.Path)
    parser.add_argument("--ablation-json", dest="ablation_out", type=pathlib.Path)
    parser.add_argument("--ablation-csv", dest="ablation_csv", type=pathlib.Path)
    args = parser.parse_args(argv)

    spatial = spatial_report(args.captures, args.min_sessions)
    print(f"independent_sessions={spatial['verdict']['independent_sessions']}")
    print(f"gradient_distribution={spatial['gradient_distribution']['status']}")
    print(f"disturbance_response={spatial['disturbance_specific_response']['status']}")
    for capture in spatial["captures"]:
        print(f"capture={capture['capture']} rows={capture['rows']} "
              f"boot_ids={capture['boot_ids']}")
        for phase, block in capture["phases"].items():
            if "air_gradient" not in block:
                continue
            print(f"  {phase}: air max|dT|={block['air_gradient']['max_pairwise_difference_c']} "
                  f"air-vs-surface max|dT|="
                  f"{block['phase_max_pairwise_difference_c']} "
                  f"samples={block['air_gradient']['tallies']['usable_pairs']}")
    ablation = ablation_matrix(args.captures, ABLATION_VARIANTS, args.min_sessions)
    for name in ABLATION_VARIANTS:
        summary = ablation["per_variant_summary"][name]
        print(f"variant={name} status={summary['status']} "
              f"delta_c={summary['delta_c_values']}")

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.json_out, spatial)
        print(f"json={args.json_out}")
    if args.ablation_out is not None:
        args.ablation_out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.ablation_out, ablation)
        print(f"ablation_json={args.ablation_out}")
    if args.ablation_csv is not None:
        args.ablation_csv.parent.mkdir(parents=True, exist_ok=True)
        write_csv(args.ablation_csv, ablation_csv_rows(ablation))
        print(f"ablation_csv={args.ablation_csv}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    sys.exit(main())
