"""ColdGuard W16 comparability framework and final physical freeze schema (standard library only).

Docs anchor: ``docs/05A`` section 25 (Week 16 - Final physical drift/response
freeze before predictive control), requirements A-W16-01 .. A-W16-04, and the
gate contribution "G4 cannot pass if physical response has drifted beyond the
understood range".

This tool is the *framework* that decides **when behaviour captured in an
earlier era (W07/W08) may be compared to behaviour captured in the W16 era**.
Comparing two runs that came from different physical or software configurations
would silently corrupt the drift/response freeze, so a comparison is allowed
only when every one of these dimensions matches:

    geometry / roles | cadence | limits posture | installed image hash |
    physical-output posture | hardware-config id

Two of those (limits posture, image hash) are pinned from committed build
evidence; geometry/roles come from the operator-frozen mapping; cadence is
measured from the capture itself.

Running it **on authentic data today** it has only the W04/H8-C cooling capture
committed on this branch; the W07/W08-era snapshots and the W16-era
re-measurement live in sibling workstreams and on the bench, which this host
slice cannot read or perform. So the honest result is: **no comparison can be
closed and no freeze is asserted.** The tool is written so that a freeze flag
cannot be set from host evidence - ``assert_no_freeze`` is executed on every run
and the report always carries ``frozen: false`` and ``no_g4_claim: true`` until a
real W16 re-measurement is supplied.

Requirements reflected:

* **A-W16-01 re-run short characterization** - the framework records which
  sub-captures (OFF envelope, core ON point, response delay, S2 disturbance) a
  W16 run must provide; absent them the status is NEED_USER_ACTION, never a
  number.
* **A-W16-02 compare W7/W8 vs W16** - ``compare_snapshots`` is that comparison.
* **A-W16-03 final pair tolerances** - ``response_tolerance_format`` is the
  analysis FORMAT (initial state, gradient, reset criterion, disturbance
  tolerance); it is emitted with NOT_MEASURED placeholders, never invented
  limits.
* **A-W16-04 controller B physical readiness** - ``final_freeze_evidence_schema``
  is the evidence schema the physical freeze must satisfy before A can certify
  readiness with D; it names what is still owed and never certifies it here.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import pathlib
import statistics
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "evidence" / "A"

# W16 shares the probe-identification classifier and the boot-identity helper
# with W12: a touch capture may not become a comparability baseline, and cadence
# may not be blended across a device reboot (docs/01 / W07 cadence discipline).
import cg_w12_drift_audit as _w12  # noqa: E402

# The comparison dimensions. A cross-era comparison is only legal when every
# dimension matches; a mismatch is configuration drift and blocks the freeze.
COMPARISON_DIMENSIONS = (
    "geometry_roles",
    "cadence_hz",
    "limits_policy",
    "image_sha256",
    "physical_output",
    "hardware_config_id",
)

# Values that mean "this side carries no evidence" and therefore BLOCK
# comparability. Absence must never read as a match (H3): an unlabelled geometry,
# an empty/UNQUALIFIED physical-output column, or an unresolved limits posture is
# a MISSING_SIDE, not a MATCH.
MISSING_STRINGS = {"", "unpinned", "unresolved", "unverified", "unassigned",
                   "not_measured", "none", "null"}

FROZEN_ROLES = {
    "t1": "CHAMBER_CENTER",
    "t2": "TEC_HOT_SIDE",
    "t3": "CHAMBER_BOTTOM",
    "t4": "CHAMBER_NEAR_DOOR",
}

# Installed / pinned images (from committed build evidence, docs/05A W12-W16).
# The descriptive note on the bench image is an AUTHORED operator report
# (physical_output / supervised_bench / interlock_state) - those fields appear in
# no committed artifact on this branch, so they are labelled as authored, not as
# evidence the framework read off a capture.
BENCH_IMAGE_SHA256 = ("01cedce3b794638f25ae4c7f1e2dfdcb4b00555fdc81a0bcf4d35ed4187f6c9f",
                      "installed bench image build-t2-hot-side, 258544 B, local-only; "
                      "AUTHORED operator note (physical_output=ENABLED, supervised_bench=1, "
                      "interlock_state=NOT_INSTALLED) - not present in any committed capture "
                      "on this branch")
PRODUCTION_W06_IMAGE_SHA256 = ("947c529d1987288aa960e45e9053223fe8975f3ce210fb5150e36a0d07c36e13",
                               "W06 delivery chain image, 253520 B, never flashed")


def _now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _f(value: object) -> float | None:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if out != out else out


def load_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [r for r in csv.DictReader(handle) if r]


def _cadence_hz(rows: list[dict[str, str]]) -> float | None:
    """Device-clock median frame rate; cadence is measured, never assumed.

    Refused (None) when the capture spans more than one boot identity: a device
    reboot restarts the uptime clock, so frame gaps that cross a boot boundary
    are meaningless and cadence must not be blended across eras (docs/01 / the
    W07 cadence discipline and the W12 boot-identity rule).
    """
    boots = _w12._boot_ids(rows)
    if len(boots) > 1:
        return None
    ms = [_f(r.get("device_ms")) for r in rows]
    ms = [m for m in ms if m is not None]
    if len(ms) < 3:
        return None
    gaps = [(b - a) / 1000.0 for a, b in zip(ms, ms[1:]) if b > a]
    if not gaps:
        return None
    return round(1.0 / statistics.median(gaps), 4)


def _is_missing(value: object) -> bool:
    """True when a comparison side carries no evidence (absence, not a value)."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in MISSING_STRINGS:
        return True
    if isinstance(value, str) and value.strip().upper().startswith("UNQUALIFIED"):
        return True
    return False


def _roles_seen(rows: list[dict[str, str]]) -> dict[str, str]:
    """Dominant role token per slot, uppercased; UNASSIGNED collapses to None."""
    out: dict[str, str] = {}
    for slot in FROZEN_ROLES:
        col = f"{slot}_role"
        vals = {(r.get(col) or "").strip().upper() for r in rows if r.get(col)}
        named = {v for v in vals if v and v not in
                 {"UNASSIGNED", "NOT_ASSIGNED", "UNKNOWN", "UNVERIFIED"}}
        out[slot] = sorted(named)[0] if named else None
    return out


# ---------------------------------------------------------------------------
# Freeze signature: the comparison dimensions of one capture / era snapshot
# ---------------------------------------------------------------------------
def freeze_signature(rows: list[dict[str, str]], path: pathlib.Path | None = None,
                     image_sha256: str | None = None) -> dict[str, object]:
    if not rows:
        return {"capture": (path.name if path else "inline"), "status": "EMPTY_CAPTURE",
                "is_probe_identification": False}
    first = rows[0]
    if _w12.is_probe_identification(path or pathlib.Path("inline"), rows):
        return {"capture": (path.name if path else "inline"),
                "status": "EXCLUDED_PROBE_IDENTIFICATION", "is_probe_identification": True}
    if image_sha256 is None:
        session = (first.get("session") or "").lower()
        if "01cedce3" in session:
            image_sha256 = BENCH_IMAGE_SHA256[0]
        else:
            image_sha256 = "UNPINNED"
    roles = _roles_seen(rows)
    geometry_roles_match = all(
        (roles[slot] is None or roles[slot] == FROZEN_ROLES[slot] or
         roles[slot] in FROZEN_ROLES[slot])
        for slot in FROZEN_ROLES
    )
    fully_labelled = all(roles[slot] for slot in FROZEN_ROLES)
    physical_output = (first.get("physical_output") or "").strip()
    limits = (first.get("limits_policy") or "").strip() or "UNRESOLVED"
    boots = _w12._boot_ids(rows)
    # The hardware-config identity is DERIVED from the evidence that would let it
    # mismatch, not a constant: the frozen CG-HW-001 identity is only assertable
    # when the geometry is fully labelled and consistent, the image is pinned, the
    # limits posture is resolved and a single boot is present. Otherwise it is
    # UNVERIFIED, which compare_snapshots treats as a missing side.
    config_evidence_ok = (fully_labelled and geometry_roles_match
                          and image_sha256 != "UNPINNED" and limits != "UNRESOLVED"
                          and len(boots) <= 1)
    hardware_config_id = "CG-HW-001" if config_evidence_ok else "UNVERIFIED"
    return {
        "capture": path.name if path else "inline",
        "is_probe_identification": False,
        "geometry_roles": {"observed": roles, "consistent_with_freeze": geometry_roles_match,
                           "fully_labelled": fully_labelled},
        "cadence_hz": _cadence_hz(rows),
        "limits_policy": limits,
        "image_sha256": image_sha256,
        "physical_output": physical_output or "UNQUALIFIED(empty column)",
        "hardware_config_id": hardware_config_id,
        "boot_ids": boots,
        "frames": len(rows),
    }


def _role_mapping(side: object) -> tuple[dict[str, str] | None, bool]:
    """The normalized slot->role map of one side, and whether it is missing evidence.

    This replaces comparing `consistent_with_freeze`. Two snapshots whose `observed`
    mappings disagreed entirely could both report that boolean as true and be declared
    MATCH - the summary said what the data did not. The mapping is the evidence; a summary
    flag is at most a claim about it, so a contradiction between the two is reported as a
    mismatch rather than resolved by believing the flag.
    """
    if not isinstance(side, dict):
        return None, True
    raw = side.get("observed")
    if not isinstance(raw, dict):
        raw = side
    mapping: dict[str, str] = {}
    for slot in FROZEN_ROLES:
        value = str(raw.get(slot) or "").strip().upper()
        if value in MISSING_STRINGS or value in {"UNASSIGNED", "NOT_ASSIGNED", "SPARE"}:
            return None, True          # a slot nobody labelled is not a comparable map
        mapping[slot] = value
    if not side.get("fully_labelled", True):
        return None, True
    return mapping, False


def _flag_contradicts_mapping(side: object, mapping: dict[str, str] | None) -> bool:
    """True when the summary boolean disagrees with the map it claims to summarise."""
    if mapping is None or not isinstance(side, dict):
        return False
    flag = side.get("consistent_with_freeze")
    if flag is None:
        return False
    agrees = all(mapping[slot] == role for slot, role in FROZEN_ROLES.items())
    return bool(flag) != agrees


def compare_snapshots(baseline: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    """Per-dimension match table for two era snapshots, plus the comparison verdict.

    A mismatch is configuration drift, not a rounding error: the W16-era
    behaviour may only be compared to the W07/W08-era behaviour when every
    dimension agrees. Any 'MISMATCH' or a missing W16 side blocks the freeze.
    """
    table: dict[str, dict[str, object]] = {}
    blocked = False
    for dim in COMPARISON_DIMENSIONS:
        b = baseline.get(dim)
        c = current.get(dim)
        # Geometry is comparable only when both sides fully label the frozen slots and
        # their slot->role MAPS agree. An unlabelled or partially-labelled side is a
        # MISSING side (the committed baseline labels only T2), and a side whose summary
        # flag disagrees with its own map is a mismatch, not a match.
        contradictions: list[str] = []
        if dim == "geometry_roles":
            b_map, b_missing = _role_mapping(b)
            c_map, c_missing = _role_mapping(c)
            for label, side, mapping in (("baseline", b, b_map), ("current", c, c_map)):
                if _flag_contradicts_mapping(side, mapping):
                    contradictions.append(label)
                    b_missing = c_missing = True
            b_norm, c_norm = b_map, c_map
            b_cmp, c_cmp = b, c
        else:
            b_missing = _is_missing(b)
            c_missing = _is_missing(c)
            b_norm, c_norm, b_cmp, c_cmp = b, c, b, c
        if b_missing or c_missing:
            state = "MISSING_SIDE"
            blocked = True
        elif b_norm == c_norm:
            state = "MATCH"
        else:
            state = "MISMATCH"
            blocked = True
        entry: dict[str, object] = {"baseline": b_cmp, "current": c_cmp, "state": state}
        if dim == "geometry_roles":
            entry["compared_as"] = ("slot->role map" if not (b_missing or c_missing)
                                    else "refused: one or both sides unlabelled")
            if b_map is not None:
                entry["baseline_map"] = b_map
            if c_map is not None:
                entry["current_map"] = c_map
            if contradictions:
                entry["flag_contradicts_mapping"] = contradictions
                entry["state"] = "MISMATCH"
        table[dim] = entry
    return {
        "requirement": "A-W16-02",
        "dimension_table": table,
        "comparison_allowed": not blocked,
        "verdict": "BLOCKED" if blocked else "COMPARABLE",
        "note": ("a dimension in MISSING_SIDE/MISMATCH means the two eras are not the "
                 "same physical/software configuration and their response may not be "
                 "directly compared; MISSING_SIDE is raised on ABSENCE of evidence "
                 "(null/unlabelled/UNQUALIFIED/UNVERIFIED), never counted as a match"),
    }


def configuration_drift_detection(signatures: list[dict[str, object]]) -> list[dict[str, object]]:
    """Flag any dimension whose value differs across the supplied snapshots."""
    drift = []
    for dim in COMPARISON_DIMENSIONS:
        values = []
        for sig in signatures:
            v = sig.get(dim)
            if dim == "geometry_roles" and isinstance(v, dict):
                # A geometry change is real whether the freeze-consistency flag or
                # the labelling completeness moved; compare both, not just the bool.
                v = (v.get("consistent_with_freeze"), v.get("fully_labelled"),
                     tuple(sorted((v.get("observed") or {}).items())))
            values.append(v)
        distinct = {json.dumps(x, sort_keys=True) for x in values}
        if len(distinct) > 1:
            drift.append({"dimension": dim,
                          "values": [str(x) for x in values],
                          "kind": "CONFIGURATION_DRIFT"})
    return drift


# ---------------------------------------------------------------------------
# A-W16-01 required W16 sub-captures (framework; status only, no invented data)
# ---------------------------------------------------------------------------
def w16_rerun_requirements() -> list[dict[str, object]]:
    return [
        {"item": "off_envelope", "ask": "short OFF-envelope idle current at the frozen geometry",
         "status": "NEED_USER_ACTION", "host_can_compute": False,
         "why": "a fresh supervised OFF capture is a physical action"},
        {"item": "core_on_point", "ask": "core ON point current/power at the frozen duty",
         "status": "NEED_USER_ACTION", "host_can_compute": False,
         "why": "requires an authorized energized session"},
        {"item": "response_delay", "ask": "response delay re-measured on the same geometry",
         "status": "TEAM_DEPENDENCY", "host_can_compute": False,
         "why": "needs the W16 capture to compare against the W13 baseline"},
        {"item": "s2_disturbance", "ask": "S2 disturbance response",
         "status": "NEED_USER_ACTION", "host_can_compute": False,
         "why": "S2 is a physical disturbance run; also tied to the door->critical gap"},
    ]


# ---------------------------------------------------------------------------
# A-W16-03 final response tolerance analysis FORMAT
# ---------------------------------------------------------------------------
def response_tolerance_format() -> dict[str, object]:
    """The shape of the final pair-tolerance signoff, with placeholders only.

    docs/05A A-W16-03 signs off (with B): initial state, gradient, reset
    criterion, disturbance tolerance. This is the FORMAT the measured values must
    be written into; every value is NOT_MEASURED until a real W16 re-run fills
    it. It is not a place to estimate a limit.
    """
    return {
        "requirement": "A-W16-03",
        "signed_off_with": "Member B",
        "fields": {
            "initial_state": {"value": "NOT_MEASURED", "unit": None,
                              "definition_ref": "docs/01 derived thermal-state section 20"},
            "gradient": {"value": "NOT_MEASURED", "unit": "C",
                         "definition_ref": "docs/01 section 20.3 G_T = Tmax - Tmin (chamber air)"},
            "reset_criterion": {"value": "NOT_MEASURED", "unit": None,
                                "definition_ref": "docs/01 section 20.6 recovery measured after action"},
            "disturbance_tolerance": {"value": "NOT_MEASURED", "unit": "C",
                                      "definition_ref": "frozen candidate critical definition (D)"},
        },
        "policy": "no field may be filled from host evidence; a W16 re-run is required first",
    }


# ---------------------------------------------------------------------------
# A-W16-04 final physical freeze evidence schema
# ---------------------------------------------------------------------------
def final_freeze_evidence_schema() -> dict[str, object]:
    """The evidence a physical freeze must present before A certifies Controller B readiness."""
    return {
        "requirement": "A-W16-04",
        "certified_with": "Member D",
        "required_evidence": {
            "allowed_action_still_valid": {"must_show": "same six limits posture and duty range as baseline",
                                           "status": "OPEN"},
            "no_hardware_safety_issue": {"must_show": "fuse/conductor deviation resolved or accepted",
                                         "status": "OPEN", "note": "fuse remains unphotographed / uncertified"},
            "h8_reactive_verification_stable": {"must_show": "W16 OFF/ON/response within the W13-W15 envelope",
                                                "status": "OPEN", "note": "requires the A-W16-01 re-run"},
        },
        "freeze_condition": ("only when every COMPARISON dimension matches AND all "
                             "required_evidence items are closed AND a W16 re-measurement exists"),
        "host_slice_may_set_frozen": False,
        "status_labels_allowed": ["IMPLEMENTED", "HOST_VERIFIED", "REAL_DATA_ANALYZED",
                                  "NEED_USER_ACTION", "TEAM_DEPENDENCY", "BLOCKED_HARDWARE"],
        "forbidden_labels": ["PHYSICALLY_VERIFIED (from host evidence)",
                             "TEAM_GATE_G4_GREEN"],
    }


# Whole-team / physical claims the host slice must never make. The verdict text
# for a freeze declaration is included so a rewritten "FROZEN (physical freeze
# declared)" cannot slip past the guard as an innocent string.
FORBIDDEN_CLAIMS = ("PHYSICALLY_VERIFIED", "GATE G4 GREEN", "G4 GREEN",
                    "TEAM G4 GREEN", "PHYSICAL FREEZE DECLARED",
                    "FROZEN (PHYSICAL FREEZE")


def _forbidden_claims_in(report: dict[str, object]) -> list[str]:
    """The forbidden-claim substrings present in everything except the prohibition catalogue.

    ``final_freeze_evidence_schema.forbidden_labels`` names these phrases precisely so
    they can be rejected; the guard polices the claims the tool MAKES, not the words it
    forbids, so that schema subtree is excluded from the scan.
    """
    policed = {k: v for k, v in report.items() if k != "final_freeze_evidence_schema"}
    blob = json.dumps(policed, sort_keys=True).upper()
    return [claim for claim in FORBIDDEN_CLAIMS if claim in blob]


def assert_no_freeze(report: dict[str, object]) -> None:
    """A hard runtime guard: this host slice never declares a physical freeze.

    It raises if the report sets frozen True, marks any requirement status
    PHYSICALLY_VERIFIED, or declares team gate G4 GREEN or a physical freeze. It also
    WIRES the ``no_g4_claim`` flag: when the report carries that flag it must be True,
    and the guard re-derives it from the same scan it performs, so a mutation that
    flips a claim without flipping the flag is caught. Running on every build makes
    'no freeze' a checked property, not a comment.
    """
    if report.get("frozen"):
        raise AssertionError("W16 host slice must never declare a physical freeze")
    claims = _forbidden_claims_in(report)
    if claims:
        raise AssertionError(f"forbidden whole-team/physical claim in report: {claims[0]!r}")
    # The literal no_g4_claim constant is now read by the guard: if it is present it
    # must agree with the scan (no forbidden claims found above).
    if "no_g4_claim" in report and report["no_g4_claim"] is not True:
        raise AssertionError("no_g4_claim flag contradicts the guard: a team-gate/freeze "
                             "claim is present in the report body")
    for cap in report.get("a_w16_01_rerun_requirements", []):
        if str(cap.get("status", "")).upper() == "PHYSICALLY_VERIFIED":
            raise AssertionError("a W16 re-run item was marked PHYSICALLY_VERIFIED from host evidence")


def build_report(capture_paths: list[pathlib.Path],
                 w16_snapshots: list[dict[str, object]] | None = None) -> dict[str, object]:
    baseline_sigs = [freeze_signature(load_csv(p), p) for p in capture_paths]
    # A probe-identification touch capture is not a physical-configuration baseline;
    # it is kept visible in the report but never used as the comparison side (M8).
    plant_sigs = [s for s in baseline_sigs if not s.get("is_probe_identification")]
    # A cross-era comparison needs a W16-era snapshot. On this branch none exists
    # (W16 re-measurement is a physical action), so current side is EMPTY.
    current_sig = (w16_snapshots[0] if w16_snapshots else {
        dim: None for dim in COMPARISON_DIMENSIONS})
    baseline = plant_sigs[0] if plant_sigs else {
        dim: None for dim in COMPARISON_DIMENSIONS}

    comparison = compare_snapshots(baseline, current_sig)
    report = {
        "tool": "cg_w16_comparability.py",
        "week": "W16",
        "generated_utc": _now_utc(),
        "evidence_kind": "HOST_FRAMEWORK_ON_COMMITTED_CAPTURES",
        "frozen": False,
        "physical_verified": False,
        "touches_hardware": False,
        "comparison_dimensions": list(COMPARISON_DIMENSIONS),
        "baseline_signatures": baseline_sigs,
        "w16_snapshot_present": bool(w16_snapshots),
        "cross_era_comparison": comparison,
        "configuration_drift": configuration_drift_detection(
            baseline_sigs + ([current_sig] if w16_snapshots else [])),
        "a_w16_01_rerun_requirements": w16_rerun_requirements(),
        "response_tolerance_format": response_tolerance_format(),
        "final_freeze_evidence_schema": final_freeze_evidence_schema(),
        "verdict": "NO_FREEZE (host slice; W16 re-measurement not present)",
    }
    # no_g4_claim is DERIVED from the guard's own scan, not a literal constant.
    report["no_g4_claim"] = not _forbidden_claims_in(report)
    assert_no_freeze(report)
    return report


def default_captures() -> list[pathlib.Path]:
    p = EVIDENCE / "W04" / "tec-cooling-response-600s.csv"
    return [p] if p.is_file() else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--capture", type=pathlib.Path, action="append",
                        help="committed baseline capture CSV(s)")
    parser.add_argument("--w16-snapshot", type=pathlib.Path,
                        help="optional W16-era snapshot JSON (a real re-measurement)")
    parser.add_argument("--json-out", type=pathlib.Path)
    args = parser.parse_args(argv)

    paths = args.capture if args.capture else default_captures()
    paths = [p if p.is_absolute() else REPO_ROOT / p for p in paths]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        print("MISSING_CAPTURES: " + ", ".join(missing), file=sys.stderr)
        return 2

    w16 = None
    if args.w16_snapshot and args.w16_snapshot.is_file():
        w16 = [json.loads(args.w16_snapshot.read_text(encoding="utf-8"))]

    report = build_report(paths, w16)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8", newline="\n")

    comp = report["cross_era_comparison"]
    print(f"baseline captures: {[s['capture'] for s in report['baseline_signatures']]}")
    print(f"w16_snapshot_present={report['w16_snapshot_present']} "
          f"comparison_allowed={comp['comparison_allowed']} verdict={comp['verdict']}")
    print(f"configuration_drift={report['configuration_drift']}")
    print(f"frozen={report['frozen']} no_g4_claim={report['no_g4_claim']} "
          f"verdict={report['verdict']}")
    print("assert_no_freeze: PASSED (host slice declares no physical freeze)")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
