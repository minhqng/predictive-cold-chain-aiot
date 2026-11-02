"""W08 A-W08-03 - hot-side sustainability and the fuse/conductor evaluation.

    py firmware/tools/cg_w08_hot_side.py [--bench-root DIR] [--json OUT.json]

Two questions are answered here, both strictly from recorded bytes:

1. **Does the TEC hot side stay sustainable at 100 % duty for as long as the
   recorded sessions ran?** The answer is an observation, not a rating. The
   temperature channel used is the operator-frozen as-built mapping
   ``T2 = TEC_HOT_SIDE``; ``TEC_HOT_SIDE`` is never averaged into a chamber-air
   statistic, and no cold-side or junction temperature exists in any capture
   (no channel is labelled COLD_SIDE in the committed data).

   The hot-side ceiling of 55 degC is **PROVISIONAL** in this repository and the
   TEC1-12715 purchased SKU has **no continuous rating** established
   (``evidence/A/W04/g2a/22-six-limit-audit.md`` L1, and the H8 endurance
   reports). So "margin to 55 degC" is a distance to a provisional working
   number, and it is not a statement that anything may be run continuously.

2. **Can a fuse be chosen from measurement alone?** No. The branch conductor was
   recorded as "1.75 mm2", and the operator corrected that on 2026-11-02: 1.75 is
   the **diameter of the copper core in mm**, so the recorded figure carried a unit
   error. For a round solid conductor that is ``pi x (1.75/2)^2 = 2.405 mm2``,
   which is ~4 % below the canonical ``2 x 2.5 mm2`` ask by cross-sectional area
   and inside the FDD2-250 termination's 1.5-2.5 mm2 rating - not the ~30 % gap the
   old wording implied. The solid-round assumption is stated, not proven: a
   stranded core is not one round wire, and only a photographed marking settles
   what is installed, so no nominal 2.5 mm2 compliance is declared and
   ``evidence/A/W01/bom-audit.csv`` HW-19 stays ``UNVERIFIED``. The conductor's
   insulation class, run length and routing are still unrecorded, and the installed
   fuse's marking has never been photographed - the 15 A value is operator-reported
   only, with nothing legible on the body (``evidence/A/W04/fuse-commissioning-note.md``
   section 1). A fuse protects the weakest element in the branch - the cable - so
   with no ampacity basis there is nothing to coordinate against. This module
   therefore keeps ``observed`` and ``recommended`` in separate blocks and returns
   ``NO_FREEZE``.

Nothing here touches hardware. ``PHYSICALLY_VERIFIED`` is never emitted; the
status vocabulary is IMPLEMENTED / HOST_VERIFIED / REAL_DATA_ANALYZED /
NEED_USER_ACTION / TEAM_DEPENDENCY / BLOCKED_HARDWARE.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from dataclasses import dataclass

import cg_w08_envelope as envelope

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]

# The working ceiling the bench sessions were run against. It is explicitly
# provisional in the source records, and this module never upgrades it.
PROVISIONAL_HOT_SIDE_LIMIT_C = 55.0
HOT_SIDE_LIMIT_STATUS = "PROVISIONAL_NOT_A_RATING"
CONTINUOUS_RATING_CLAIMED = False

# The as-built, operator-frozen mapping. Do not re-test it, do not question it,
# and do not mix a channel between roles.
AS_BUILT_ROLES = {
    "t1": "CHAMBER_CENTER",
    "t2": "TEC_HOT_SIDE",
    "t3": "CHAMBER_BOTTOM",
    "t4": "CHAMBER_NEAR_DOOR",
}
HOT_SIDE_CHANNEL = "t2"
ROM_BY_CHANNEL = {
    # By-source ids from the firmware ROM map (cg_config.h / the W05 schema
    # fixture), not a runtime readback: the captures carry no per-conversion ROM.
    "t1": "287088CA00000051",
    "t2": "28AEBF2200000006",
    "t3": "28CBE9CA00000072",
    "t4": "283BE5C9000000A9",
    "t4_note": "SPARE slot",
}

# Conductor and fuse facts. These are declarations of the record, not analysis.
# Operator correction 2026-11-02: the recorded "1.75 mm2" was a UNIT ERROR - 1.75
# is the copper CORE DIAMETER in mm. The cross-section below is therefore a
# DERIVED reading under a stated solid-round assumption, never a measurement, and
# it must not be re-asked or quietly turned into a nominal 2.5 mm2 claim: no
# marking has been photographed, so evidence/A/W01/bom-audit.csv HW-19 stays
# UNVERIFIED and the deviation stays open.
BRANCH_CONDUCTOR_RECORDED_FIGURE = "1.75"
BRANCH_CONDUCTOR_CORE_DIAMETER_MM = 1.75
CONDUCTOR_SHAPE_ASSUMPTION = (
    "round solid copper core, area = pi x (diameter/2)^2; a stranded core is not "
    "one round wire, so only a photographed marking settles what is installed"
)
BRANCH_CONDUCTOR_MM2 = round(
    math.pi * (BRANCH_CONDUCTOR_CORE_DIAMETER_MM / 2) ** 2, 3)
CANONICAL_CONDUCTOR = "2 x 2.5 mm2"
CANONICAL_CONDUCTOR_MM2 = 2.5
CONDUCTOR_AREA_GAP_VS_CANONICAL_PCT = round(
    (CANONICAL_CONDUCTOR_MM2 - BRANCH_CONDUCTOR_MM2) / CANONICAL_CONDUCTOR_MM2
    * 100, 1)
# FDD2-250 faston termination rating, as recorded in the W04 commissioning note.
TERMINATION_RANGE_MM2 = (1.5, 2.5)
CONDUCTOR_NOMINAL_COMPLIANCE_CLAIMED = False
INSTALLED_FUSE_A_REPORTED = 15.0
FUSE_MARKING_LEGIBLE = False
CATALOGUE_IS_NOT_INSTALLED_EVIDENCE = (
    "a shop listing or catalogue entry for a fuse of that rating says nothing about "
    "the installed body and is not treated as evidence here"
)
FUSE_CANDIDATES_A = (10, 15, 20)

OFF_BENCH_GATE_A = 0.200


@dataclass
class HotSideRow:
    """One session's hot-side sustainability observation."""

    session: str
    trust: str
    reproducible_from_git: bool
    series_path_regime: str
    duty_permille: int | None
    driven_frames: int
    driven_span_s: float | None
    min_c: float | None
    max_c: float | None
    last_driven_c: float | None
    margin_to_provisional_limit_k: float | None
    frames_at_max: int
    ramp_mean_c: float | None
    final_60s_mean_c: float | None
    prior_60s_mean_c: float | None
    final_drift_k_per_min: float | None
    plateau_observed: str
    verdict: str
    caveats: str

    def as_row(self) -> dict[str, object]:
        return self.__dict__.copy()


def hot_side_series(frames: list[envelope.Frame]) -> list[tuple[float, float]]:
    """(clock_ms, temperature) for driven frames of the hot-side channel only."""
    out = []
    for frame in frames:
        value = frame.thermal.get(HOT_SIDE_CHANNEL)
        if frame.classification == envelope.DRIVEN and value is not None:
            out.append((frame.clock_ms if frame.clock_ms is not None else float(len(out)),
                        float(value)))
    return out


def _mean(values: list[float]) -> float | None:
    return None if not values else round(sum(values) / len(values), 4)


def _sustainability_session(source: str) -> bool:
    """True only for sessions actually run as hot-side endurance tests.

    The H7 ladder ran the electrical-only image and the H6 trace read no thermal
    channel, so neither can carry a sustainability result however stable their
    hot-side numbers look.
    """
    if source == "W04-H8C-box-600s":
        return True
    return any(label == source for _rel, label, _regime in envelope.H8_SESSIONS)


def _device_roles(frames: list[envelope.Frame]) -> list[str]:
    return sorted({f.roles.get(HOT_SIDE_CHANNEL, "") or "(empty)" for f in frames
                   if f.thermal.get(HOT_SIDE_CHANNEL) is not None})


def analyse_session(frames: list[envelope.Frame], *, session: str, trust: str,
                    reproducible_from_git: bool, regime: str) -> HotSideRow | None:
    """Build one hot-side sustainability row from already-classified frames."""
    series = hot_side_series(frames)
    if not series:
        return None
    values = [value for _clock, value in series]
    driven = [f for f in frames if f.classification == envelope.DRIVEN]
    span_s = None
    if len(driven) >= 2 and all(f.clock_ms is not None for f in driven):
        span_s = round((driven[-1].clock_ms - driven[0].clock_ms) / 1000.0, 3)
    maximum = max(values)
    top = series[-60:] if len(series) >= 60 else series
    prior_start = max(0, len(series) - 120)
    prior = series[prior_start:len(series) - 60]
    ramp = series[:60]
    final_60 = _mean([v for _c, v in top])
    prior_60 = _mean([v for _c, v in prior]) if prior else None
    drift = None
    if final_60 is not None and prior_60 is not None:
        # Both windows are exactly 60 frames of a 1 Hz stream, i.e. one minute.
        drift = round(final_60 - prior_60, 4)
    plateau = (
        "NEEDS_AT_LEAST_TWO_TREND_WINDOWS" if drift is None else
        "FLAT_WITHIN_0P2_K_PER_MIN" if abs(drift) <= 0.2 else
        "STILL_WARMING" if drift > 0 else "STILL_COOLING"
    )
    margin = round(PROVISIONAL_HOT_SIDE_LIMIT_C - maximum, 3)
    caveats = (
        "margin is to a PROVISIONAL working ceiling, not to a rated limit; "
        "no continuous rating exists for this TEC SKU; "
        "device-reported role token on this channel is "
        f"{'/'.join(_device_roles(frames))} and differs between bench images - "
        "the as-built mapping (T2 = TEC_HOT_SIDE) is what this row uses; "
        "hot-side values are never averaged into a chamber-air statistic"
    )
    if not _sustainability_session(session):
        caveats += ("; this session was not run as a hot-side endurance test "
                    "(H7 = electrical-only image, no thermal channel on H6), so the "
                    "row is a recording, not a sustainability result")
    verdict = (
        "OBSERVED_SUSTAINED_WITHIN_PROVISIONAL_MARGIN"
        if maximum < PROVISIONAL_HOT_SIDE_LIMIT_C else
        "PROVISIONAL_CEILING_REACHED_IN_CAPTURE_REPORT_ONLY"
    )
    if not _sustainability_session(session):
        verdict = "NOT_A_SUSTAINABILITY_RESULT_ELECTRICAL_ONLY_IMAGE"
    return HotSideRow(
        session=session,
        trust=trust,
        reproducible_from_git=reproducible_from_git,
        series_path_regime=regime,
        duty_permille=driven[0].duty_applied if driven else None,
        driven_frames=len(driven),
        driven_span_s=span_s,
        min_c=envelope.r(min(values)),
        max_c=envelope.r(maximum),
        last_driven_c=envelope.r(values[-1]),
        margin_to_provisional_limit_k=margin,
        frames_at_max=sum(1 for v in values if v == maximum),
        ramp_mean_c=_mean([v for _c, v in ramp]),
        final_60s_mean_c=final_60,
        prior_60s_mean_c=prior_60,
        final_drift_k_per_min=drift,
        plateau_observed=plateau,
        verdict=verdict,
        caveats=caveats,
    )


def analyse_all(repo_root: pathlib.Path,
                bench_root: pathlib.Path | None) -> list[HotSideRow]:
    """Hot-side rows for every capture that has a driven block with a hot side."""
    rows: list[HotSideRow] = []
    sources = envelope.load_sources(repo_root, bench_root)
    for source, frames in sorted(sources.items()):
        row = analyse_session(
            frames,
            session=source,
            trust="COMMITTED" if source in envelope.COMMITTED_SOURCES else "LOCAL_BENCH",
            reproducible_from_git=source in envelope.COMMITTED_SOURCES,
            regime=envelope.source_regime(source),
        )
        if row is not None:
            rows.append(row)
    return rows


# --------------------------------------------------------------------------
# fuse / conductor evaluation
# --------------------------------------------------------------------------

def observed_currents(repo_root: pathlib.Path,
                      bench_root: pathlib.Path | None) -> list[dict[str, object]]:
    """The measured electrical load the fuse question has to be argued against."""
    out: list[dict[str, object]] = []
    for source, frames in sorted(envelope.load_sources(repo_root, bench_root).items()):
        driven = [f for f in frames if f.classification == envelope.DRIVEN]
        if not driven:
            continue
        currents = [f.current_a for f in driven if f.current_a is not None]
        powers = [f.power_w for f in driven if f.power_w is not None]
        out.append({
            "session": source,
            "trust": "COMMITTED" if source in envelope.COMMITTED_SOURCES else "LOCAL_BENCH",
            "series_path_regime": envelope.source_regime(source),
            "duty_permille": driven[0].duty_applied,
            "driven_frames": len(driven),
            "current_median_a": envelope.distribution(currents).get("median"),
            "current_p95_a": envelope.distribution(currents).get("p95"),
            "current_max_a": envelope.distribution(currents).get("max"),
            "power_max_w": envelope.distribution(powers).get("max"),
            "electrical_status_recorded": bool(
                envelope.status_coverage(frames)[source]["electrical_status_recorded"]
            ),
        })
    return out


def fuse_evaluation(currents: list[dict[str, object]],
                    sustained_source: str = "W04-H8C-box-600s") -> dict[str, object]:
    """Fuse choice argued strictly against the recorded observations.

    The separation is the deliverable: what the captures show, what is still
    missing to turn that into a rating, and what this slice therefore refuses to
    freeze. It never certifies compliance.
    """
    committed = [c for c in currents if c["trust"] == "COMMITTED"]
    local = [c for c in currents if c["trust"] == "LOCAL_BENCH"]
    peak_committed = max((c["current_max_a"] for c in committed), default=None)
    peak_all = max((c["current_max_a"] for c in currents), default=None)
    sustained = next((c for c in currents if c["session"] == sustained_source), None)
    peak_replacing = max((c for c in currents if c["session"] == "H7-100pct"),
                        default=None)

    table = []
    for candidate in FUSE_CANDIDATES_A:
        headroom = (None if peak_all is None else round(candidate - peak_all, 3))
        table.append({
            "candidate_a": candidate,
            "relation_to_observed_peak_a": (
                f"observed peak {peak_all} A" if peak_all is not None else "no peak observed"
            ),
            "headroom_over_observed_peak_a": headroom,
            "justified_by_observation_alone": False,
            "why_not": (
                "a fuse rating is the conductor's ampacity coordinate, and the "
                f"installed branch has no recorded ampacity basis: {BRANCH_CONDUCTOR_MM2} "
                f"mm2 is derived from a {BRANCH_CONDUCTOR_CORE_DIAMETER_MM} mm core "
                "diameter under a solid-round assumption, with no insulation class, "
                "run length or bundling recorded and no marking photographed"
            ),
        })

    return {
        "requirement": "A-W08-02 fuse finalization (docs/05A section 17)",
        "status_label": "BLOCKED_HARDWARE",
        "observed": {
            "committed_captures": committed,
            "local_bench_captures": local,
            "peak_current_committed_a": peak_committed,
            "peak_current_any_source_a": peak_all,
            "sustained_600s_block": sustained,
            "highest_duty_local_reference": peak_replacing,
            "note": (
                "the committed 957-row capture carries no electrical validity token, "
                "so its V/I/P figures are published as unqualified values "
                "(electrical_status_recorded: false); the H7 ladder lines carry no "
                "validity token either"
            ),
        },
        "recommended": {
            "conservative_direction": (
                "the smallest candidate that clears the observed peak with the "
                "largest margin, pending an ampacity basis; recorded as a direction, "
                "not as a choice"
            ),
            "not_chosen": True,
        },
        "conductor": {
            "recorded_figure": BRANCH_CONDUCTOR_RECORDED_FIGURE,
            "recorded_unit_error_corrected": (
                "the record said 1.75 mm2 - a unit error; the operator corrected on "
                "2026-11-02 that 1.75 is the copper core diameter in mm"),
            "core_diameter_mm": BRANCH_CONDUCTOR_CORE_DIAMETER_MM,
            "shape_assumption": CONDUCTOR_SHAPE_ASSUMPTION,
            "installed_mm2": BRANCH_CONDUCTOR_MM2,
            "installed_mm2_basis": (
                f"derived: pi x ({BRANCH_CONDUCTOR_CORE_DIAMETER_MM}/2)^2, an "
                "arithmetic reading of the corrected record, not a measurement"),
            "provenance": "operator-corrected 2026-11-02; the area is derived from "
                          "the corrected diameter and never re-asked",
            "canonical_ask": CANONICAL_CONDUCTOR,
            "canonical_mm2": CANONICAL_CONDUCTOR_MM2,
            "area_gap_vs_canonical_pct": CONDUCTOR_AREA_GAP_VS_CANONICAL_PCT,
            "deviation_open": True,
            "nominal_canonical_compliance_claimed": CONDUCTOR_NOMINAL_COMPLIANCE_CLAIMED,
            "deviation_register": (
                "evidence/A/W04/fuse-commissioning-note.md (no marking photographed; "
                "'No conductor evidence at all (today) -> no freeze') and "
                "evidence/A/W01/bom-audit.csv HW-19 UNVERIFIED"
            ),
            "termination_in_range": (
                f"FDD2-250 faston covers {TERMINATION_RANGE_MM2[0]}-"
                f"{TERMINATION_RANGE_MM2[1]} mm2, and the derived "
                f"{BRANCH_CONDUCTOR_MM2} mm2 sits inside that range - a termination "
                "fit, not a conductor rating"),
            "insulation_class_recorded": False,
            "run_length_recorded": False,
            "bundling_recorded": False,
            "status_label": "TEAM_DEPENDENCY",
        },
        "fuse": {
            "installed_reported_a": INSTALLED_FUSE_A_REPORTED,
            "value_basis": "operator-reported only; nothing is legible on the body",
            "marking_photographed": FUSE_MARKING_LEGIBLE,
            "legible_on_installed_body": FUSE_MARKING_LEGIBLE,
            "no_rating_no_voltage_no_dielectric_no_blade_size_recorded": True,
            "catalogue_is_not_installed_evidence": CATALOGUE_IS_NOT_INSTALLED_EVIDENCE,
            "suitability_proven": False,
            "candidates_a": list(FUSE_CANDIDATES_A),
            "decision_table": table,
        },
        "bench_off_gate": {
            "limit_a": OFF_BENCH_GATE_A,
            "provenance": "H8 frame field off_current_limit_a=0.200, simulated "
                          "enforcement in the bench image; not a canonical limit",
            "observed_steady_off_max_a": 0.02,
        },
        "verdict": "NO_FREEZE",
        "gate_a_pass_criterion_safe_physical_envelope_known": "NOT_MET",
        "what_would_close_it": [
            "photograph of the installed fuse body rating (and the spare 10 A) read "
            "off that body: the 15 A figure is operator-reported today, nothing is "
            "legible on the installed body (no current rating, no 250 V, no "
            "glass/ceramic, no blade size), and a shop listing or catalogue entry "
            "for a fuse of that rating is not evidence about installed hardware",
            "insulation temperature class, run length and routing/bundling of the "
            f"installed branch (a {BRANCH_CONDUCTOR_CORE_DIAMETER_MM} mm core "
            f"diameter, {BRANCH_CONDUCTOR_MM2} mm2 if solid round), with a cited "
            "ampacity table for the real installation",
            "the conductor marking photographed, so the solid-round assumption is "
            "either confirmed or replaced by the printed cross-section; until then "
            f"the {CONDUCTOR_AREA_GAP_VS_CANONICAL_PCT} % gap to the canonical "
            "2 x 2.5 mm2 ask is an assumption-based reading and HW-19 stays "
            "UNVERIFIED",
            "either acceptance of the conductor deviation with its basis, or "
            "replacement by the canonical 2 x 2.5 mm2 with photo + marking",
            "an IBT-2/terminal temperature observation during a long run "
            "(A-W08-03's fourth bullet, which no recorded frame measures)",
        ],
    }


# --------------------------------------------------------------------------
# artifact renderers
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


THERMAL_CSV_COLUMNS = [
    "session", "trust", "reproducible_from_git", "series_path_regime",
    "hot_side_channel", "as_built_role", "provisional_limit_c", "limit_status",
    "continuous_rating_claimed", "duty_permille", "driven_frames", "driven_span_s",
    "min_c", "max_c", "last_driven_c", "margin_to_provisional_limit_k",
    "frames_at_max", "ramp_mean_c", "prior_60s_mean_c", "final_60s_mean_c",
    "final_drift_k_per_min", "plateau_observed", "verdict", "status_label",
    "caveats",
]


def render_thermal_csv(rows: list[HotSideRow]) -> str:
    lines = [",".join(THERMAL_CSV_COLUMNS)]
    for row in rows:
        data = row.as_row()
        data.update({
            "hot_side_channel": HOT_SIDE_CHANNEL,
            "as_built_role": AS_BUILT_ROLES[HOT_SIDE_CHANNEL],
            "provisional_limit_c": PROVISIONAL_HOT_SIDE_LIMIT_C,
            "limit_status": HOT_SIDE_LIMIT_STATUS,
            "continuous_rating_claimed": CONTINUOUS_RATING_CLAIMED,
            "status_label": "REAL_DATA_ANALYZED",
        })
        lines.append(",".join(_csv_escape(_fmt(data.get(column)))
                              for column in THERMAL_CSV_COLUMNS))
    return "\n".join(lines) + "\n"


def render_fuse_md(evaluation: dict[str, object]) -> str:
    observed = evaluation["observed"]
    sustained = observed.get("sustained_600s_block") or {}
    lines = [
        "# A-W08-02 - fuse selection note (observed versus recommended)",
        "",
        "Status: **BLOCKED_HARDWARE** - generated by",
        "`firmware/tools/cg_w08_hot_side.py` through",
        "`evidence/A/W08/build_w08_artifacts.py`. Nothing in this file is",
        "`PHYSICALLY_VERIFIED`: no measurement is taken here, no compliance is",
        "certified, and the branch must not be energized on the strength of it.",
        "",
        "## 1. The rule this note obeys",
        "",
        "`docs/05A` A-W08-02: choose among 10 A / 15 A / 20 A from measured",
        "current and behaviour, with rationale - and if no available fuse is",
        "defensibly suitable, **the gate fails; do not improvise silently**.",
        "",
        "## 2. What was observed",
        "",
        "| Session | Trust | Path regime | Duty | Driven frames | I median A | I p95 A | I max A | P max W |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for entry in observed["committed_captures"] + observed["local_bench_captures"]:
        lines.append(
            f"| {entry['session']} | {entry['trust']} | {entry['series_path_regime']} | "
            f"{_fmt(entry['duty_permille'])} | {_fmt(entry['driven_frames'])} | "
            f"{_fmt(entry['current_median_a'])} | {_fmt(entry['current_p95_a'])} | "
            f"{_fmt(entry['current_max_a'])} | {_fmt(entry['power_max_w'])} |"
        )
    lines += [
        "",
        f"* Highest current in a **git-committed** capture: "
        f"**{_fmt(observed['peak_current_committed_a'])} A** "
        f"(`evidence/A/W04/tec-cooling-response-600s.csv`, one frame; median "
        f"{_fmt(sustained.get('current_median_a'))} A across "
        f"{_fmt(sustained.get('driven_frames'))} driven frames of a 600 s block).",
        f"* Highest current in any capture read, including Member A's local bench "
        f"tree: **{_fmt(observed['peak_current_any_source_a'])} A**.",
        "* Every one of those figures is a value **with no recorded validity token** "
        "in its own source (the committed CSV's `voltage_status`/`current_status` "
        "cells are empty in all 957 rows and it has no `power_status` column; the "
        "H7 `H7 T` lines carry no token at all), so they are published as "
        "`electrical_status_recorded: false`.",
        "* The 20-60 % ladder was recorded through a degraded return path; the "
        "70-100 % ladder after its replacement. They are listed separately and "
        "never pooled.",
        "",
        "## 3. What is missing before any number can be chosen",
        "",
        "| Item | Record |",
        "|---|---|",
        f"| Branch conductor | recorded as **{BRANCH_CONDUCTOR_RECORDED_FIGURE}**, "
        "which the operator corrected on 2026-11-02 to the **copper core diameter "
        "in mm**, not a cross-section: the \"mm2\" in the old record was a unit "
        "error. Reading it as a round solid core gives "
        f"**{BRANCH_CONDUCTOR_MM2} mm2** = pi x "
        f"({BRANCH_CONDUCTOR_CORE_DIAMETER_MM}/2)^2 |",
        "| Conductor shape assumption | **round solid core**, stated, not proven: a "
        "stranded core is not one round wire and only the printed marking settles it |",
        f"| Canonical ask | `{CANONICAL_CONDUCTOR}` - deviation still open; the area "
        f"gap is **~{CONDUCTOR_AREA_GAP_VS_CANONICAL_PCT} %**, not the ~30 % the "
        "old unit-error wording implied, and no nominal 2.5 mm2 compliance is "
        "claimed |",
        "| Termination | FDD2-250 faston rated 1.5-2.5 mm2 covers the derived "
        f"{BRANCH_CONDUCTOR_MM2} mm2 - a fit check, not an ampacity basis |",
        "| Fuse body marking | never photographed; nothing is legible on the "
        "installed body (no current rating, no 250 V, no glass/ceramic, no blade "
        f"size - `evidence/A/W04/fuse-commissioning-note.md`); {INSTALLED_FUSE_A_REPORTED:g} A "
        "is operator-reported only, and a shop listing or catalogue entry is not "
        "evidence about installed hardware |",
        "| Insulation class / run length / bundling | not recorded anywhere |",
        f"| Ampacity basis for the installed conductor | none cited in this repository |",
        f"| BOM audit | `evidence/A/W01/bom-audit.csv` HW-19 = `UNVERIFIED` |",
        "",
        "## 4. Candidate table, argued against the observations only",
        "",
        "| Candidate | Relation to observed peak | Headroom A | Justified by "
        "observation alone | Why not |",
        "|---|---|---|---|---|",
    ]
    for row in evaluation["fuse"]["decision_table"]:
        lines.append(
            f"| {row['candidate_a']} A | {row['relation_to_observed_peak_a']} | "
            f"{_fmt(row['headroom_over_observed_peak_a'])} | "
            f"{'yes' if row['justified_by_observation_alone'] else 'NO'} | "
            f"{row['why_not']} |"
        )
    lines += [
        "",
        "## 5. Recommended versus observed - kept apart on purpose",
        "",
        "* **Observed:** the branch carried a 600 s block at 100 % duty with a",
        f"  median of {_fmt(sustained.get('current_median_a'))} A and a single peak of",
        f"  {_fmt(observed['peak_current_committed_a'])} A, and the bench OFF gate held",
        f"  steady OFF current at or below "
        f"{_fmt(evaluation['bench_off_gate']['observed_steady_off_max_a'])} A.",
        "* **Recommended (not a freeze):** prefer the candidate that keeps the",
        "  largest margin over the observed peak *once* an ampacity basis exists,",
        "  and re-run the coordination check against the replaced conductor if the",
        "  2 x 2.5 mm2 deviation is closed by replacement rather than accepted.",
        "* **Not claimed:** compliance, suitability of the installed 15 A fuse,",
        "  continuous duty, or any permission to energize the branch.",
        "* **Conductor reinterpretation, stated once:** the corrected record reads "
        f"as ~{BRANCH_CONDUCTOR_MM2} mm2 on a solid-round assumption, ~"
        f"{CONDUCTOR_AREA_GAP_VS_CANONICAL_PCT} % under the canonical 2.5 mm2 and "
        "inside the FDD2-250 1.5-2.5 mm2 termination range. That narrows the "
        "geometric gap; it does not close it, and it is still not a nominal 2.5 mm2 "
        "conductor: no marking was photographed, HW-19 stays UNVERIFIED, and a "
        "stranded core would make the derived area wrong in an unknown direction.",
        "* **Fuse evidence, stated once:** the 15 A value is operator-reported only. "
        "Nothing is legible on the installed body, and a shop listing or catalogue "
        "entry for a fuse of that rating is not evidence about installed hardware, so "
        "suitability stays unproven and the verdict stays NO_FREEZE.",
        "",
        "## 6. Verdict",
        "",
        f"`{evaluation['verdict']}` - A-W08-02 stays open. The Gate A pass criterion",
        f"`{evaluation['gate_a_pass_criterion_safe_physical_envelope_known']}`:",
        "`safe physical envelope known` is therefore **not met** by this slice.",
        "",
        "## 7. What closes it",
        "",
    ]
    lines += [f"1. {item}" for item in evaluation["what_would_close_it"]]
    lines += [
        "",
        "Status label for the whole file: **BLOCKED_HARDWARE** (physical inputs",
        "missing) with the electrical statistics above labelled",
        "**REAL_DATA_ANALYZED**, and the conductor deviation labelled",
        "**TEAM_DEPENDENCY**.",
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
    rows = analyse_all(args.repo_root, bench)
    currents = observed_currents(args.repo_root, bench)
    fuse = fuse_evaluation(currents)
    report = {
        "schema": "cg-w08-hot-side-1",
        "status_label": "REAL_DATA_ANALYZED",
        "provisional_hot_side_limit_c": PROVISIONAL_HOT_SIDE_LIMIT_C,
        "limit_status": HOT_SIDE_LIMIT_STATUS,
        "continuous_rating_claimed": CONTINUOUS_RATING_CLAIMED,
        "as_built_roles": AS_BUILT_ROLES,
        "rom_ids_by_source_only": ROM_BY_CHANNEL,
        "sessions": [row.as_row() for row in rows],
        "fuse_evaluation": fuse,
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8", newline="\n")
        print(f"wrote {args.json}")
    for row in rows:
        print(f"  {row.session:28s} duty={_fmt(row.duty_permille):>4} "
              f"frames={row.driven_frames:5} span_s={_fmt(row.driven_span_s):>7} "
              f"T2 max={_fmt(row.max_c)} margin={_fmt(row.margin_to_provisional_limit_k)} "
              f"drift={_fmt(row.final_drift_k_per_min)} {row.plateau_observed}")
    print(f"fuse verdict: {fuse['verdict']} (status {fuse['status_label']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
