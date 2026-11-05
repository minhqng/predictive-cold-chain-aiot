"""ColdGuard W11 A-W11-04: conditional S3 feasibility, and why the answer is NO-GO.

docs/03 §31 defines S3 (THERMAL_EFFECTIVENESS_DEGRADATION) as a conditional
scenario that must produce a specific signature:

```text
electrical response remains plausible
thermal effectiveness worsens
```

docs/05A §20 A-W11-04 then says to assess whether a **safe, repeatable** method
exists on the currently frozen hardware, that ``NO-GO`` is an acceptable answer,
and that an unsafe fan obstruction must not be invented to manufacture a label.

This module does the assessment as data rather than as an opinion. It states the
measurement S3 would require, checks each candidate method against four
independent constraints, and reports the result. The conclusion is **NO-GO**, and
the decisive reason is not a soft one: the quantity S3 is *about* - the
temperature difference that a TEC drives at a given electrical power - needs a
hot-base probe and a cold-plate probe, and the shipped H8 limit table records
that neither is installed:

```text
H8_LIMIT_HOT_BASE_MAX_C  = UNRESOLVED("NO_HOT_BASE_PROBE_INSTALLED")
H8_LIMIT_COLD_PLATE_MIN_C= UNRESOLVED("NO_COLD_PLATE_PROBE_INSTALLED")
```
(``firmware/h8-bench/main/h8_limits.c:27``, read-only inspection; the same two
rows appear in the H8 boot log as ``#CG TEC_LIMIT name=hot_base_max_c
state=UNRESOLVED ... source=NO_HOT_BASE_PROBE_INSTALLED``.)

The frozen geometry compounds it: T1/T3/T4 are chamber-air positions and T2 is
the TEC hot *side*, so there is no probe on the cold plate at all. A degradation
of the cold-side heat transfer would therefore be invisible, and the only thing
that would move is the chamber air - which is what a door opening also moves.
Without a cold-side measurement, "effectiveness degraded" and "the load changed"
are the same number.

The second reason is the weaker one but it belongs in the record: with a single
physical capture available, an effectiveness *metric* has no variance, and a
label whose repeatability has never been demonstrated cannot anchor a fault
class.
"""

from __future__ import annotations

S3_FEASIBILITY_VERSION = "w11-s3-feasibility-v1"

REQUIRED_MEASUREMENTS = [
    {
        "id": "M1-qualified-electrical-power",
        "what": "electrical power delivered during the degraded state, with producer status",
        "why": "S3 is defined by electrical response staying plausible while thermal "
               "effectiveness falls; without a qualified power figure the first half of the "
               "definition cannot be asserted",
        "available_now": False,
        "evidence": "current_status and voltage_status are empty strings in all 957 rows of the "
                    "committed capture and no power_status column exists",
    },
    {
        "id": "M2-cold-side-temperature",
        "what": "cold-plate temperature at the TEC interface",
        "why": "thermal effectiveness is a temperature lift per unit power; the cold side of the "
               "lift is one of the two endpoints",
        "available_now": False,
        "evidence": "firmware/h8-bench/main/h8_limits.c:27 marks hot_base_max_c UNRESOLVED with "
                    "NO_HOT_BASE_PROBE_INSTALLED; cold_plate_min_c likewise; the frozen geometry "
                    "has no probe on the cold plate",
    },
    {
        "id": "M3-hot-base-temperature",
        "what": "hot-base / heatsink-base temperature",
        "why": "the other endpoint of the lift, and the place a fouling or contact-resistance "
               "degradation would show first",
        "available_now": False,
        "evidence": "same unresolved limit row; T2 sits on the TEC hot side, which is not the "
                    "hot base and is already excluded from chamber-air statistics",
    },
    {
        "id": "M4-repeatable-degradation-state",
        "what": "a degradation that can be set to a known magnitude and removed identically "
                "at least 4 times",
        "why": "docs/03 §31 requires the scenario to be reproducible, and Member B needs pairs",
        "available_now": False,
        "evidence": "every candidate method below either changes the frozen configuration, "
                    "damages hardware, or is not separable from S2",
    },
    {
        "id": "M5-baseline-effectiveness-variance",
        "what": "the effectiveness metric measured at least twice in the healthy state",
        "why": "a degraded label needs a distribution to be degraded *relative to*",
        "available_now": False,
        "evidence": "one physical thermal capture is committed, so no between-run spread exists "
                    "for any derived metric",
    },
]

# Constraints from docs/05A §20 A-W11-01/04 and the frozen configuration.
CONSTRAINTS = (
    "safe",
    "repeatable",
    "does_not_damage_tec_or_v1",
    "does_not_bypass_fuse_or_short_branch",
    "does_not_change_frozen_hardware_config",
    "separable_from_S2_and_S4",
)

CANDIDATE_METHODS = [
    {
        "id": "C1-fan-obstruction",
        "method": "partially block the hot-side fan",
        "verdict": "REJECTED_BY_INSTRUCTION",
        "reason": "docs/05A §20 A-W11-04 forbids inventing an unsafe fan obstruction; it also "
                  "stalls the fan, which is a fault in a different class and changes the safety "
                  "posture",
        "violates": ["safe", "does_not_damage_tec_or_v1"],
    },
    {
        "id": "C2-heat-base-fouling",
        "method": "add a controlled thermal resistance at the hot interface (gasket/dust)",
        "verdict": "NO-GO",
        "reason": "physically alters the frozen hardware configuration, is not quantified without "
                  "a hot-base probe, and is only partly reversible; the H8 limit table exists to "
                  "keep the hot path bounded and this pushes an unmeasured variable into it",
        "violates": ["does_not_change_frozen_hardware_config", "repeatable",
                     "does_not_damage_tec_or_v1"],
    },
    {
        "id": "C3-probe-displacement",
        "method": "move or re-seat a probe to fake a changed reading",
        "verdict": "NO-GO",
        "reason": "this is a sensor fault, not a thermal-effectiveness fault, and it produces "
                  "exactly the contamination the 2026-11-02 PROBE_IDENTIFICATION session is "
                  "excluded for: a hand on a probe. The label would be untrustworthy by "
                  "construction",
        "violates": ["safe", "separable_from_S2_and_S4"],
    },
    {
        "id": "C4-door_left_cracked",
        "method": "hold the door at a fixed small opening",
        "verdict": "RECLASSIFIED",
        "reason": "a steady added load with unchanged heat transfer is a load disturbance, which "
                  "is S2's mechanism; labelling it S3 would put two names on one physical effect "
                  "and destroy the contrast Member B trains on",
        "violates": ["separable_from_S2_and_S4"],
    },
    {
        "id": "C5-reduced-drive-in-software",
        "method": "cap duty or current so less power reaches the stack",
        "verdict": "RECLASSIFIED",
        "reason": "reducing the drive is an actuation-response change, which is S4; the electrical "
                  "response would NOT remain plausible, so it fails S3's first condition by "
                  "definition",
        "violates": ["separable_from_S2_and_S4"],
    },
    {
        "id": "C6-raise-ambient",
        "method": "warm the room or the bench environment",
        "verdict": "NO-GO",
        "reason": "not controllable or repeatable at 1 Hz within a supervised session, and the "
                  "ambient path is already documented as not the plant (docs/05A §16.3 ambient "
                  "path is only a candidate); it also changes the baseline every paired run "
                  "depends on",
        "violates": ["repeatable", "does_not_change_frozen_hardware_config"],
    },
]

METHOD_REQUIRED_TO_REVERSE = (
    "install a cold-plate probe and a hot-base probe, resolve hot_base_max_c and "
    "cold_plate_min_c in the limit table, qualify the electrical columns with a real "
    "producer status, and then collect at least 2 healthy and 4 degraded captures"
)

S4_OVERLAP_WARNING = (
    "if the campaign later wants a thermal-side degradation label at all, the only honest route "
    "runs through new instrumentation, not through new manipulation of the existing bench"
)

#: A-W11-04 methodology. A NO-GO is only useful if it also states what a future session
#: would have to record for the verdict to be revisitable, so that the operator is not
#: asked to "do S3" and left to invent the record themselves. Nothing here has been
#: collected; every item is a requirement on a session that has not happened.
SESSION_RECORD_REQUIREMENTS = [
    {
        "id": "R1-instrumentation-attestation",
        "record": "the cold-plate and hot-base probe ROMs, physical mounting point, and the "
                  "resolved limit-table rows for hot_base_max_c and cold_plate_min_c",
        "why": "without both endpoints of the lift there is no thermal-effectiveness quantity to "
               "degrade, only chamber air that happens to be warmer",
    },
    {
        "id": "R2-qualified-electrical-state",
        "record": "voltage, current and power for every frame, each with its producer status "
                  "emitted as OK at the source",
        "why": "S3 is 'electrical response plausible while thermal effectiveness falls'; an "
               "unqualified current cannot carry the plausible half of that sentence",
    },
    {
        "id": "R3-degradation-setting-and-magnitude",
        "record": "which method was used, its intended magnitude, how it was set, and how it was "
                  "removed - identical each time, with the operator present",
        "why": "docs/03 §31 requires a reproducible scenario; a degradation that cannot be set "
               "to a known magnitude cannot become a label",
    },
    {
        "id": "R4-matched-healthy-baseline",
        "record": "the same hardware configuration id, firmware version, sensor ROMs, physical "
                  "positions and duty as the degraded run, immediately before or after it",
        "why": "effectiveness is a ratio against the healthy state; without a matched pair the "
               "degradation is indistinguishable from drift or a different box",
    },
    {
        "id": "R5-repetition-count",
        "record": "at least 2 healthy and 4 degraded captures, each a separate session with its "
                  "own boot_id, and the timing of each edge from an operator timer",
        "why": "a degraded label needs a distribution to be degraded relative to, and one boot's "
               "segments are not independent runs",
    },
    {
        "id": "R6-confounders-and-interventions",
        "record": "ambient temperature and humidity, door state with its per-boot attestation, "
                  "fan readback, any manual intervention, and the end reason",
        "why": "the S2 door disturbance and an S4 refusal both move chamber air; if they are not "
               "recorded they silently contaminate the S3 label",
    },
    {
        "id": "R7-not-done-declaration",
        "record": "what was deliberately not attempted (shorted branch, bypassed fuse, damaged "
                  "TEC, obstructed fan) and why",
        "why": "docs/05A §20 A-W11-01 forbids those methods; the absence of a record that they "
               "were refused is indistinguishable from having quietly used one",
    },
]


def assess() -> dict:
    """The feasibility record: verdict, requirements, candidates, and what would change it."""
    verdicts = {}
    for method in CANDIDATE_METHODS:
        verdicts[method["verdict"]] = verdicts.get(method["verdict"], 0) + 1
    available = sum(1 for m in REQUIRED_MEASUREMENTS if m["available_now"])
    return {
        "version": S3_FEASIBILITY_VERSION,
        "requirement": "docs/05A §20 A-W11-04 (conditional S3 feasibility)",
        "scenario": "S3_THERMAL_EFFECTIVENESS_DEGRADATION",
        "verdict": "NO-GO",
        "verdict_basis": (
            f"{available} of {len(REQUIRED_MEASUREMENTS)} required measurements are available on "
            "the current frozen hardware, and every candidate method violates at least one "
            "constraint"
        ),
        "decisive_reason": (
            "thermal effectiveness is a lift per unit power and the lift has no measurable cold "
            "endpoint here: hot_base_max_c and cold_plate_min_c are UNRESOLVED because neither "
            "probe is installed (firmware/h8-bench/main/h8_limits.c:27), and the frozen geometry "
            "places T1/T3/T4 in chamber air and T2 on the TEC hot side"
        ),
        "required_measurements": REQUIRED_MEASUREMENTS,
        "session_record_requirements": SESSION_RECORD_REQUIREMENTS,
        "constraints": list(CONSTRAINTS),
        "candidate_methods": CANDIDATE_METHODS,
        "candidate_verdict_counts": verdicts,
        "what_would_change_the_verdict": METHOD_REQUIRED_TO_REVERSE,
        "docs03_position": (
            "docs/03 §31 already permits omitting S3 from core fault claims when no clean method "
            "exists; this record is the evidence for using that clause rather than a preference"
        ),
        "not_done": [
            "no fan obstruction was invented",
            "no hardware was modified or reconfigured",
            "no S3 run is claimed, listed or scheduled",
        ],
        "status_label": "IMPLEMENTED / HOST_VERIFIED (analysis only, no run)",
        "warning": S4_OVERLAP_WARNING,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# S3 go / no-go - thermal-effectiveness degradation",
        "",
        f"Generated by `build_w11_artifacts.py` from `firmware/tools/cg_w11_s3_feasibility.py` "
        f"({report['version']}). Requirement: {report['requirement']}.",
        "",
        f"## Verdict: **{report['verdict']}**",
        "",
        report["decisive_reason"],
        "",
        f"Basis: {report['verdict_basis']}",
        "",
        "## Measurements S3 would need",
        "",
        "| id | measurement | available now | evidence |",
        "|---|---|---|---|",
    ]
    for item in report["required_measurements"]:
        lines.append(
            f"| `{item['id']}` | {item['what']} | "
            f"{'yes' if item['available_now'] else '**no**'} | {item['evidence']} |"
        )
    lines += [
        "",
        "## Candidate methods against the constraints",
        "",
        "| id | method | verdict | constraints violated |",
        "|---|---|---|---|",
    ]
    for method in report["candidate_methods"]:
        lines.append(
            f"| `{method['id']}` | {method['method']} | {method['verdict']} | "
            f"{', '.join(method['violates'])} |"
        )
    lines += [
        "",
        "## Why each candidate fails, in full",
        "",
    ]
    for method in report["candidate_methods"]:
        lines += [f"### `{method['id']}` - {method['method']} -> {method['verdict']}", "",
                  method["reason"], ""]
    lines += [
        "## What would change the verdict",
        "",
        report["what_would_change_the_verdict"],
        "",
        "## What an S3 session must record",
        "",
        "Methodology only: no item below has been collected, and recording them does not turn "
        "this NO-GO into a GO until the instrumentation in the section above exists.",
        "",
        "| id | record | why it is required |",
        "|---|---|---|",
    ]
    for item in report["session_record_requirements"]:
        lines.append(
            f"| `{item['id']}` | {item['record']} | {item['why']} |"
        )
    shortfalls = report.get("existing_capture_shortfalls")
    if shortfalls is None:
        lines += [
            "",
            "## Why no committed capture can supply it",
            "",
            "NOT DERIVED IN THIS RENDER: the per-capture shortfall table is attached by the "
            "dossier builder from the W09 run registry, and it was not supplied here.",
        ]
    else:
        lines += [
            "",
            "## Why no committed capture can supply it",
            "",
            "Derived from the W09 run registry, per capture, so that 'we have no S3 data' is a "
            "checked statement about each source rather than a summary of the whole repository.",
            "",
            "| capture | physical | registry eligibility | supplies | falls short of |",
            "|---|---|---|---|---|",
        ]
        for entry in shortfalls:
            lines.append(
                f"| `{entry['capture_id']}` | {'yes' if entry['is_physical_measurement'] else '**no**'} "
                f"| {entry['registry_eligibility']} "
                f"| {', '.join(entry['measurements_it_could_supply']) or 'none'} "
                f"| {', '.join(entry['falls_short_of'])} |"
            )
        lines += ["", "### Per-capture reasons", ""]
        for entry in shortfalls:
            lines += [f"* `{entry['capture_id']}` ({entry['kind']})", ""]
            lines += [f"  * `{mid}`: {reason}" for mid, reason in entry["shortfall_reasons"].items()]
            lines.append("")
    lines += [
        "## Position in the plan",
        "",
        report["docs03_position"],
        "",
        "## What was deliberately not done",
        "",
    ]
    lines += [f"* {item}" for item in report["not_done"]]
    lines += [
        "",
        f"Status: **{report['status_label']}**",
        "",
        "> " + report["warning"],
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    import json
    import sys

    report = assess()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
