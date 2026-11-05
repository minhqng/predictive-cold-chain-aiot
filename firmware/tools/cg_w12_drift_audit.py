"""ColdGuard W12 drift audit and Month-3 physical/data signoff inputs (standard library only).

Docs anchor: ``docs/05A`` section 21 (Week 12 - Drift audit and Month-3
physical/data signoff), requirements A-W12-01 .. A-W12-05.

This tool answers one question and nothing else: **do the datasets collected so
far still belong to one defensible physical configuration, and what must be
re-measured before they are trusted together?** It is a *host* analysis of
already-committed captures. It touches no hardware, opens no serial port, and
declares no whole-team gate. Where a quantity cannot be computed from committed
evidence it says so as a named data gap; it never substitutes a number.

What it produces (all from committed captures under ``evidence/A``):

* **A-W12-01 sensor consistency recheck**, grouped strictly by configuration.
  For every configuration it reports the per-slot mean (probe offset), the
  agreement among the three *chamber-air* probes (max pairwise difference and
  population standard deviation over the frames where all three are valid), and
  the session-to-session spread of those statistics. The TEC hot side is a
  separate population and is never folded into a chamber-air statistic.
* **ROM / location comparison** against the operator-frozen geometry. Any
  capture whose per-slot ``_role`` fields disagree with the frozen role, or that
  carries a role not present in the mapping, is flagged. Probe-identification
  touch captures are classified as ``PROBE_IDENTIFICATION`` and are excluded
  from every drift and timing statistic (asserted, not assumed).
* **A-W12-02 PZEM zero/active audit** against the W3/W8 envelope: duty-0 frames
  that nonetheless report current are listed **individually** (they are PZEM
  register-latency stale reads and a fan idle floor, not an average), and every
  electrical figure is labelled ``UNQUALIFIED`` because ``current_status`` /
  ``voltage_status`` are empty in the capture, i.e. the figures carry no
  device-side validity token.
* **A-W12-03 mechanical audit checklist** as a machine-readable table, each item
  with a status and the exact evidence that closes it (never a fabricated
  measured value).
* **A-W12-04 hardware-config signoff preparation**: runs grouped under
  ``CG-HW-001`` with the image/identity pins that define each configuration, and
  the configuration-grouped **dataset validity table** that shows which captures
  may not be pooled.
* **A-W12-05 gate G3 input**: an *A-side* recommendation with named blockers.
  It does not declare G3 GREEN for the team and does not mark anything
  ``PHYSICALLY_VERIFIED`` from host evidence.

Run ``py firmware/tools/cg_w12_drift_audit.py --help`` for the CLI.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import pathlib
import re
import statistics
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "evidence" / "A"

# ---------------------------------------------------------------------------
# Operator-frozen geometry (docs: final, do not question, do not re-test).
# Slot -> canonical position role and its DS18B20 ROM, taken from the firmware
# ROM map and confirmed by the G2-A thermal-stimulus identification
# (evidence/A/W04/g2a/20-probe-identification.md). SPARE (T4) response to a
# stimulus was NOT verified in that session; its position is operator-frozen.
# ---------------------------------------------------------------------------
FROZEN_SLOT_ROLES: dict[str, str] = {
    "t1": "CHAMBER_CENTER",
    "t2": "TEC_HOT_SIDE",
    "t3": "CHAMBER_BOTTOM",
    "t4": "CHAMBER_NEAR_DOOR",
}
FROZEN_SLOT_ROMS: dict[str, str] = {
    "t1": "287088CA00000051",
    "t2": "28AEBF2200000006",
    "t3": "28CBE9CA00000072",
    "t4": "283BE5C9000000A9",
}
# The three probes used for the chamber-air statistic. T2 (TEC_HOT_SIDE) is kept
# as a separate population and never folded into a chamber-air statistic. This is
# a DELIBERATE, VERSIONED DEVIATION by Member A, not a docs/01 prohibition:
# docs/01 (section 6.4 / section 20.1) treats T1-T3 as chamber air and does NOT
# forbid averaging a hot-side reading. Excluding T2 here is cg-w12 representation
# v1, chosen so the TEC hot side does not bias an air-agreement figure; it is
# recorded as an authored choice so a reader cannot mistake it for a canonical ban.
CHAMBER_AIR_SLOTS: tuple[str, ...] = ("t1", "t3", "t4")
CHAMBER_AIR_REPRESENTATION_VERSION = "chamber-air-trio-v1 (authored Member A deviation)"
HOT_SIDE_SLOT: str = "t2"
# Device-side validity token (docs/01 section 19 quality vocabulary / section 20.1:
# a mean may only be taken over the valid state). A term is excluded only when its
# status column is present and not one of these tokens; an absent/empty status is
# treated as valid for backward compatibility with captures that predate the token.
VALID_STATUS_TOKENS = {"OK", "VALID", "GOOD"}
# A role token found in a capture that is neither one of the frozen roles nor
# an explicit unassigned placeholder is a role/geometry disagreement.
ROLE_UNASSIGNED_TOKENS = {"", "UNASSIGNED", "NOT_ASSIGNED", "UNKNOWN", "UNVERIFIED"}

# W07 probe-identification touch captures identify a probe by a hand-warm
# stimulus. They are PROBE_IDENTIFICATION events and must never enter a drift or
# timing statistic; any capture whose session label matches these markers is
# classified and excluded.
PROBE_IDENTIFICATION_MARKERS = (
    "probe-identification",
    "probe_id",
    "touch_",
    "thermal-stimulus",
    "hand-warm",
)

# Mechanical-audit facts sourced from committed evidence (never re-derived,
# never certified). These are observed states, not recommendations.
CONDUCTOR_CANONICAL = "2 x 2.5 mm^2"
# Operator correction, 2026-11-02: 1.75 mm is a DIAMETER measured across the copper
# core, not a cross-sectional area. The area is therefore DERIVED, and the derivation
# assumes a solid round core - nobody has confirmed that by looking at the strand, and a
# flexible stranded conductor is not one round wire. Stating the derived area without the
# assumption would be how a measurement comes to look like a certification.
CONDUCTOR_CORE_DIAMETER_MM = 1.75
CONDUCTOR_AREA_IF_SOLID_MM2 = round(3.141592653589793 * (CONDUCTOR_CORE_DIAMETER_MM / 2) ** 2, 3)
CONDUCTOR_OBSERVED = (
    f"{CONDUCTOR_CORE_DIAMETER_MM} mm copper-core diameter (operator-measured "
    f"2026-11-02); = {CONDUCTOR_AREA_IF_SOLID_MM2} mm^2 of copper IF the core is solid "
    "round - that assumption is NOT confirmed, no marking photographed, no cross-section "
    "measured, no insulation class or routing recorded")
FUSE_REPORTED_A = 15           # reported, suitability unproven
# NOTE: the driven-branch peak current is computed per capture from the frames
# themselves (see pzem_zero_active_audit); it is never carried as a constant, so
# the note in the output cannot silently lie about the next capture.


def _now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_float(value: object) -> float | None:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


# ---------------------------------------------------------------------------
# Capture loading and configuration identity
# ---------------------------------------------------------------------------
def load_capture(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def is_probe_identification(path: pathlib.Path | str,
                            rows: list[dict[str, str]] | None = None) -> bool:
    """True when a capture is a probe-identification touch capture.

    Such captures are stimulus events for naming a probe, not plant behaviour;
    they must be excluded from drift and timing. Detection reads BOTH the file
    path AND the session/content evidence (the ``session``/``run_id``/``stage``
    fields), because a capture can be a touch session even when its file name
    says nothing. It is asserted at run time (a probe-id capture that slipped
    into a statistic is a correctness defect, not a rounding one).
    """
    text = str(path).lower()
    if any(marker in text for marker in PROBE_IDENTIFICATION_MARKERS):
        return True
    for r in rows or []:
        for field in ("session", "run_id", "stage"):
            value = (r.get(field) or "").lower()
            if any(marker in value for marker in PROBE_IDENTIFICATION_MARKERS):
                return True
    return False


def _boot_ids(rows: list[dict[str, str]]) -> list[str]:
    """Distinct boot identities carried by a capture, sorted; empty when absent."""
    return sorted({(r.get("boot_id") or "").strip() for r in rows
                   if (r.get("boot_id") or "").strip()})


def _content_hash(rows: list[dict[str, str]]) -> str:
    """A hash over the capture's rows, so a byte-copy is recognisable as itself."""
    payload = json.dumps(rows, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_value(row: dict[str, str], slot: str) -> float | None:
    """Slot temperature, honoured only when the device-side quality token is valid.

    docs/01 section 19 / section 20.1: a mean may only be taken over the valid
    state. A term whose ``{slot}_status`` is present and not a valid token is
    dropped from every mean; an empty status is kept (captures that predate the
    token), so this rule only ever *removes* non-valid terms and never re-labels
    a full mean as valid on the strength of a bad token.
    """
    status = (row.get(f"{slot}_status") or "").strip().upper()
    if status and status not in VALID_STATUS_TOKENS:
        return None
    return _to_float(row.get(f"{slot}_c"))


def configuration_of(path: pathlib.Path, rows: list[dict[str, str]]) -> str:
    """A stable configuration key for pooling decisions.

    Configuration identity is the installed image plus the limits posture, NOT
    the file name. When a capture carries no installed-image evidence at all it
    cannot be shown to belong to any configuration, so it is keyed by its own
    boot identity (and a content hash) and therefore never silently merged with
    a different image that happens to share a ``limits_policy`` string. The old
    ordering tested the ``limits_policy`` column before the boot fallback, which
    collapsed two different images into one key - the inverse of this promise.
    """
    if not rows:
        return f"EMPTY::{path.name}"
    first = rows[0]
    session = (first.get("session") or "").lower()
    image: str | None = None
    # Installed bench image (the one physically on the board for the H8-C run).
    if "01cedce3" in session or "build-t2-hot-side" in session:
        image = "01cedce3b794638f25ae4c7f1e2dfdcb4b00555fdc81a0bcf4d35ed4187f6c9f"
    # An explicit image/version column is stronger evidence than the session guess.
    for key in ("image", "firmware_version"):
        val = first.get(key)
        if val:
            image = val
            break
    limits = first.get("limits_policy") or "UNRESOLVED"
    if image:
        return f"config:image={image}|limits={limits}"
    # No installed-image evidence: key by this capture's own boot identity and
    # content so it groups honestly rather than merging into a limits bucket.
    boots = _boot_ids(rows)
    boot_tag = ",".join(boots) if boots else path.name
    return f"boot:{boot_tag}|limits:{limits}|content:{_content_hash(rows)[:16]}"


def _valid_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Rows with a parseable numeric seq (drops blank trailing lines)."""
    return [r for r in rows if r.get("seq") not in (None, "")]


# ---------------------------------------------------------------------------
# A-W12-01 sensor consistency, grouped strictly by configuration
# ---------------------------------------------------------------------------
def sensor_consistency(rows: list[dict[str, str]]) -> dict[str, object]:
    """Probe offset (per-slot mean) and chamber-air agreement for one config.

    ``agreement`` measures the three chamber-air probes only. The hot side is
    reported separately and never mixed in. Every mean is taken only over frames
    whose device-side quality token is valid (docs/01 section 19 / section 20.1):
    a term with a non-valid status is skipped and counted, never averaged, and a
    per-slot mean over fewer frames is labelled with its own ``n`` so a partial
    mean cannot reuse the full-frame label. The BME280 air channel is reported as
    a distinct independent reference, not as a fourth chamber-air probe, so a
    reader cannot accidentally pool it with the DS18B20 slots.
    """
    slot_values: dict[str, list[float]] = {}
    slot_excluded: dict[str, int] = {}
    for slot in list(CHAMBER_AIR_SLOTS) + [HOT_SIDE_SLOT]:
        col = f"{slot}_c"
        numeric = [v for v in (_to_float(r.get(col)) for r in rows) if v is not None]
        kept = [v for v in (_valid_value(r, slot) for r in rows) if v is not None]
        slot_values[slot] = kept
        slot_excluded[slot] = len(numeric) - len(kept)

    trio_agreement: list[float] = []
    trio_std: list[float] = []
    trio_nonvalid_frames = 0
    for r in rows:
        vals = [_valid_value(r, s) for s in CHAMBER_AIR_SLOTS]
        numeric_present = any(_to_float(r.get(f"{s}_c")) is not None for s in CHAMBER_AIR_SLOTS)
        if all(v is not None for v in vals):
            trio_agreement.append(max(vals) - min(vals))
            if len(vals) > 1:
                trio_std.append(statistics.pstdev(vals))
        elif numeric_present:
            # at least one chamber slot carried a number but was non-valid or
            # missing: this frame is excluded from the trio series and counted.
            trio_nonvalid_frames += 1

    bme = [_to_float(r.get("bme_air_c")) for r in rows]
    bme = [v for v in bme if v is not None]

    def _summary(vals: list[float], excluded: int = 0) -> dict[str, object]:
        if not vals:
            return {"n": 0, "status": "NO_VALID_SAMPLES", "excluded_nonvalid_terms": excluded}
        out: dict[str, object] = {
            "n": len(vals),
            "mean_c": round(statistics.fmean(vals), 4),
            "min_c": round(min(vals), 4),
            "max_c": round(max(vals), 4),
            "stdev_c": round(statistics.pstdev(vals), 4) if len(vals) > 1 else 0.0,
        }
        if excluded:
            out["excluded_nonvalid_terms"] = excluded
            out["mean_basis"] = f"valid-state mean over {len(vals)} of " \
                                f"{len(vals) + excluded} numeric terms"
        return out

    return {
        "requirement": "A-W12-01",
        "representation_version": CHAMBER_AIR_REPRESENTATION_VERSION,
        "method": "per-slot arithmetic mean over frames where the slot carries a "
                  "valid quality token (non-valid terms skipped and counted, never "
                  "averaged); chamber-air agreement = max pairwise |dT| across "
                  "(T1,T3,T4) and population stdev of that trio, both per frame then "
                  "summarised. TEC_HOT_SIDE (T2) kept as a separate population "
                  "(authored deviation, see representation_version).",
        "slot_offsets": {slot: _summary(slot_values[slot], slot_excluded[slot])
                         for slot in slot_values},
        "chamber_air_agreement": _summary(trio_agreement, trio_nonvalid_frames)
                                 if trio_agreement
                                 else {"n": 0, "status": "NO_TRIPLE_VALID_FRAMES",
                                       "excluded_nonvalid_terms": trio_nonvalid_frames},
        "chamber_air_trio_pstdev": _summary(trio_std, trio_nonvalid_frames)
                                   if trio_std
                                   else {"n": 0, "status": "NO_TRIPLE_VALID_FRAMES",
                                         "excluded_nonvalid_terms": trio_nonvalid_frames},
        "independent_bme_air_reference": _summary(bme),
        "hot_side_reported_separately": True,
    }


def cross_session_drift(captures: list[dict[str, object]]) -> dict[str, object]:
    """Session-to-session spread of the chamber-air means, only within config.

    A configuration may only show intra-configuration drift when it holds more
    than one *distinct physical session*. Two captures that share a boot identity
    or are byte-identical (a copy of one session filed under a new name) are one
    session, so they must not manufacture a "zero intra-configuration drift"
    figure. Sessions are de-duplicated on boot identity (falling back to a
    content hash when a capture carries no boot_id). Across different
    configurations pooling the means is meaningless, so no single pooled number
    is ever produced; the refusal reason is derived from what is actually present.
    """
    by_config: dict[str, dict[tuple, float]] = {}
    for cap in captures:
        trio = cap.get("sensor_consistency", {}).get("slot_offsets", {}).get("t1", {})
        if trio.get("mean_c") is None:
            continue
        boots = tuple(cap.get("boot_ids") or ())
        session_key = ("boot", boots) if boots else ("content", cap.get("content_sha256"))
        by_config.setdefault(str(cap.get("configuration")), {})[session_key] = trio["mean_c"]

    configs = sorted(by_config)
    if len(configs) <= 1:
        pooled_refused_reason = (
            "only one installed-image/limits configuration is committed on this "
            "branch; there is nothing to pool across configurations, and "
            "intra-configuration drift needs two distinct physical sessions.")
    else:
        pooled_refused_reason = (
            f"captures span {len(configs)} different installed images / limits "
            "postures; the same physical configuration is not demonstrated, so no "
            "single pooled number is legal.")
    out: dict[str, object] = {"per_configuration": {}, "pooled": None,
                              "pooled_refused_reason": pooled_refused_reason}
    for config, sessions in by_config.items():
        means = list(sessions.values())
        if len(means) > 1:
            out["per_configuration"][config] = {
                "sessions": len(means),
                "mean_of_means_c": round(statistics.fmean(means), 4),
                "range_c": round(max(means) - min(means), 4),
            }
        else:
            out["per_configuration"][config] = {
                "sessions": 1,
                "mean_of_means_c": round(means[0], 4),
                "range_c": None,
                "note": "single distinct physical session - intra-configuration "
                        "drift NOT COMPUTABLE",
            }
    return out


# ---------------------------------------------------------------------------
# ROM / location comparison against the frozen mapping
# ---------------------------------------------------------------------------
def role_geometry_audit(rows: list[dict[str, str]], path: pathlib.Path) -> dict[str, object]:
    """Flag any capture whose per-slot ``_role`` fields disagree with the freeze.

    The frozen geometry assigns each slot a canonical position role. A capture
    may legitimately leave roles UNASSIGNED (it predates the freeze); that is a
    *label gap*, not a contradiction. A capture that stamps a *different* named
    role for a slot than the freeze (e.g. labels T3 as far/opposite, or hot side
    on a chamber slot) is a *contradiction* and is flagged for the signoff.
    """
    findings: list[dict[str, object]] = []
    per_slot: dict[str, set[str]] = {}
    for slot in FROZEN_SLOT_ROLES:
        col = f"{slot}_role"
        roles = {r.get(col, "").strip().upper() for r in rows if r.get(col) is not None}
        # Only named, meaningful roles count as "labelled"; the unassigned
        # placeholders (including an empty cell) are a label gap.
        per_slot[slot] = {x for x in roles if x and x not in ROLE_UNASSIGNED_TOKENS}
        for role in per_slot[slot]:
            if role in ROLE_UNASSIGNED_TOKENS:
                continue
            frozen = FROZEN_SLOT_ROLES[slot].upper()
            # Accept a superset-consistent role (e.g. HOT_SIDE == TEC_HOT_SIDE).
            if role == frozen or role in frozen or frozen in role:
                continue
            findings.append({
                "slot": slot,
                "observed_role": role,
                "frozen_role": FROZEN_SLOT_ROLES[slot],
                "kind": "ROLE_CONTRADICTION",
                "note": "capture names a position role that disagrees with the "
                        "operator-frozen geometry; cannot be pooled with a "
                        "capture that follows the freeze without re-labelling",
            })
    label_gaps = {
        slot: ("UNLABELLED" if not roles else "LABELLED")
        for slot, roles in per_slot.items()
    }
    probe_id = is_probe_identification(path, rows)
    return {
        "capture": path.name,
        "is_probe_identification": probe_id,
        "slot_role_tokens_seen": {slot: sorted(per_slot[slot]) for slot in per_slot},
        "role_label_status": label_gaps,
        "contradictions": findings,
        "verdict": ("PROBE_IDENTIFICATION_EXCLUDED" if probe_id
                    else ("ROLE_DISAGREEMENT" if findings else
                          ("CONSISTENT_WITH_FREEZE" if any(per_slot.values())
                           else "ROLES_UNASSIGNED_LABEL_GAP"))),
    }


# ---------------------------------------------------------------------------
# A-W12-02 PZEM zero/active audit
# ---------------------------------------------------------------------------
# Qualification is decided by the producer's own token, not by whether a cell is
# non-empty. cg_pzem_status_name() emits OK / TIMEOUT / CRC_ERR / BAD_SLAVE /
# BAD_FUNCTION, so only OK can vouch for a reading; docs/01 section 19 is explicit that
# UNKNOWN must not become normal. Treating "INVALID" as a recorded status - which is what
# a nonempty check does - would let an error token move a channel toward qualified.
ELECTRICAL_QUALIFYING_STATUS = "OK"
ELECTRICAL_STATUS_NAMES = ("OK", "TIMEOUT", "CRC_ERR", "BAD_SLAVE", "BAD_FUNCTION")
ELECTRICAL_QUALIFIED = "QUALIFIED"
ELECTRICAL_PARTIALLY_QUALIFIED = "PARTIALLY_QUALIFIED"
ELECTRICAL_UNQUALIFIED = "UNQUALIFIED"


def _status_class(value: str | None) -> str:
    """valid / absent / error / unsupported - the four things a status cell can be."""
    token = (value or "").strip()
    if token == "":
        return "absent"
    if token == ELECTRICAL_QUALIFYING_STATUS:
        return "valid"
    if token in ELECTRICAL_STATUS_NAMES:
        return "error"
    return "unsupported"


def _channel_qualification(rows: list[dict[str, str]], column: str) -> dict[str, object]:
    """Per-channel status census: what the capture really recorded, counted."""
    classes = [_status_class(row.get(column)) for row in rows]
    tokens = sorted({(row.get(column) or "").strip() for row in rows} - {""})
    return {
        "frames": len(rows),
        "valid": classes.count("valid"),
        "absent": classes.count("absent"),
        "error": classes.count("error"),
        "unsupported": classes.count("unsupported"),
        "tokens_seen": tokens,
    }


def pzem_zero_active_audit(rows: list[dict[str, str]]) -> dict[str, object]:
    """Compare OFF/ON separation to the envelope; list stale OFF-current frames.

    A commanded/duty-0 frame that still reports meaningful current is a PZEM
    register-latency stale read (documented in the H8 analysis: the first
    post-OFF poll can return the last loaded current, the next poll ~1 s later
    reads ~0 A). Averaging those into an "OFF envelope" would invent a phantom
    idle draw, so each such frame is listed individually with its reason.

    Electrical figures are labelled ``UNQUALIFIED`` throughout because
    ``current_status`` and ``voltage_status`` are empty in every frame of the
    committed capture: the V/I/P numbers carry no device-side validity token and
    must not be quoted as qualified measurements.
    """
    channels = {name: _channel_qualification(rows, name)
                for name in ("current_status", "voltage_status")}
    qualified_channels = [name for name, census in channels.items()
                          if census["frames"] and census["valid"] == census["frames"]]
    any_valid = any(census["valid"] for census in channels.values())
    if qualified_channels and len(qualified_channels) == len(channels):
        electrical_qualification = ELECTRICAL_QUALIFIED
    elif any_valid:
        electrical_qualification = ELECTRICAL_PARTIALLY_QUALIFIED
    else:
        electrical_qualification = ELECTRICAL_UNQUALIFIED
    duty0_current: list[dict[str, object]] = []
    for r in rows:
        duty = r.get("pwm_applied_permille")
        cur = _to_float(r.get("current_a"))
        if duty == "0" and (cur or 0.0) > 0.0:
            duty0_current.append({
                "seq": r.get("seq"),
                "device_ms": r.get("device_ms"),
                "state": r.get("state"),
                "current_a": cur,
                "voltage_v": _to_float(r.get("voltage_v")),
                "power_w": _to_float(r.get("power_w")),
                "qualification": "UNQUALIFIED (empty current_status/voltage_status)",
            })
    residual = [d["current_a"] for d in duty0_current if (d["current_a"] or 0) <= 0.1]
    stale = [d for d in duty0_current if (d["current_a"] or 0) > 0.1]
    on_currents = [_to_float(r.get("current_a")) for r in rows
                   if r.get("pwm_applied_permille") == "999"]
    on_currents = [c for c in on_currents if c is not None]
    out: dict[str, object] = {
        "requirement": "A-W12-02",
        "envelope_reference": "W3 boot-default-off / W8 electrical envelope (sibling workstreams); "
                              "this host audit reads the OFF/ON separation in the committed capture, "
                              "it does not re-certify the envelope.",
        "electrical_qualification": electrical_qualification,
        "duty0_with_current_frames": {
            "count": len(duty0_current),
            "listed_individually_never_averaged": True,
            "stale_register_frames": stale,          # > 0.1 A: PZEM last-loaded-current artifact
            "idle_noise_floor_frames_max_a": round(max(residual), 4) if residual else None,
        },
        "on_block_current_a": ({
            "n": len(on_currents),
            "peak": round(max(on_currents), 4),
            "mean": round(statistics.fmean(on_currents), 4),
            "note": f"UNQUALIFIED figures; peak current {max(on_currents):.2f} A is the "
                    "observed branch peak (recomputed from this capture's frames)",
        } if on_currents else {"n": 0, "status": "NO_DRIVEN_FRAMES"}),
        "verdict": "OFF/ON separation observable; duty-0 stale-current frames "
                   "isolated; electrical figures UNQUALIFIED pending a qualified channel",
    }
    # A qualification claim must carry its own evidence, and the evidence has to be a
    # VALIDATING token. The validator fails any QUALIFIED/PARTIALLY_QUALIFIED claim that
    # no valid frame supports; it never fails qualification itself, which is what the
    # earlier check did when it asserted today's defect as an invariant.
    out["qualified_frame_evidence"] = {
        "frames_with_valid_status": max((c["valid"] for c in channels.values()), default=0),
        "frames_with_nonempty_status": sum(1 for r in rows
                                           if (r.get("current_status") or "").strip()
                                           or (r.get("voltage_status") or "").strip()),
        "total_frames": len(rows),
        "per_channel": channels,
        "qualifying_token": ELECTRICAL_QUALIFYING_STATUS,
    }
    if electrical_qualification == ELECTRICAL_UNQUALIFIED:
        out["unqualified_reason"] = (
            "no frame carries the producer's validating current/voltage status token; the "
            "committed capture leaves current_status and voltage_status empty in every row, "
            "and power_w/energy_wh have no status column at all, so no electrical value here "
            "is qualified")
    else:
        out["unqualified_reason"] = None
    if electrical_qualification == ELECTRICAL_PARTIALLY_QUALIFIED:
        out["verdict"] = ("OFF/ON separation observable; duty-0 stale-current frames "
                          "isolated; a partially qualified channel is present - state which "
                          "channel and which frames carry the validating token before any "
                          "figure is called qualified")
    elif electrical_qualification == ELECTRICAL_QUALIFIED:
        out["verdict"] = ("OFF/ON separation observable; duty-0 stale-current frames "
                          "isolated; both electrical channels carry the validating status "
                          "token in every frame")
    else:
        out["verdict"] = "OFF/ON separation observable; duty-0 stale-current frames " \
                         "isolated; electrical figures UNQUALIFIED pending a qualified channel"
    return out


# ---------------------------------------------------------------------------
# A-W12-03 mechanical audit checklist (machine-readable)
# ---------------------------------------------------------------------------
def mechanical_audit_checklist() -> list[dict[str, object]]:
    """Each item with a status and the evidence that closes it.

    Status vocabulary is the Member-A host one (IMPLEMENTED / HOST_VERIFIED /
    REAL_DATA_ANALYZED / NEED_USER_ACTION / TEAM_DEPENDENCY / BLOCKED_HARDWARE).
    Nothing here is PHYSICALLY_VERIFIED - this tool cannot observe the bench.
    Recommended vs observed is kept apart; the fuse/conductor deviation stays
    open and is not certified.

    These rows are AUTHORED from committed evidence, not computed: the host
    cannot observe the bench, so a status here would stay written even if the
    physical gap later closed. Each item is labelled with that basis so a reader
    (and the validator) knows it is a claim to be re-derived from a fresh
    artifact, never a measurement this tool produced.
    """
    items = [
        {
            "item": "sensor_fixtures",
            "check": "all four DS18B20 fixtures seated at their frozen positions "
                     "(T1 center, T2 TEC hot side, T3 bottom, T4 near door)",
            "status": "NEED_USER_ACTION",
            "observed": "the committed cooling capture stamps T1/T3/T4 role as UNASSIGNED "
                        "(it predates the operator role freeze); T2 is stamped HOT_SIDE",
            "closes_with": "a supervised re-identification or a photo of each fixture at its "
                           "frozen position, matched to the frozen ROM ids; probe-identification "
                           "touch captures do not count",
        },
        {
            "item": "v1_mounting",
            "check": "TEC cold/hot V1 mounting unchanged since the H8 sessions",
            "status": "NEED_USER_ACTION",
            "observed": "no host artifact records a mounting torque/seat check after the H8 "
                        "sessions; the hot-side peak 37.688 C in H8-A is data, not a mount check",
            "closes_with": "a dated mounting/photo signoff from the operator, or a fresh "
                           "thermal-resistance plausibility run supervised on the bench",
        },
        {
            "item": "terminals",
            "check": "branch terminals and FDD2-250 fastons inspected (no discoloration, "
                     "no looseness)",
            "status": "NEED_USER_ACTION",
            "observed": "W01 as-built maps the faston as 1.5-2.5 mm^2 rated, which would "
                        f"cover the derived ~{CONDUCTOR_AREA_IF_SOLID_MM2} mm^2 copper area of "
                        "the observed 1.75 mm core diameter - but that agreement rests on "
                        "the unconfirmed solid-round assumption and on a termination "
                        "inspection nobody has performed, so it is a lead, not a pass",
            "closes_with": "a supervised terminal-inspection note; this is a physical check the "
                           "host cannot perform",
        },
        {
            "item": "fuse",
            "check": "installed branch fuse rating and its suitability to the conductor",
            "status": "BLOCKED_HARDWARE",
            "observed": f"fuse reported {FUSE_REPORTED_A} A but its marking was never "
                        f"photographed (evidence/A/W04/fuse-commissioning-note.md ~:36); "
                        f"observed conductor {CONDUCTOR_OBSERVED}; canonical ask "
                        f"{CONDUCTOR_CANONICAL}; W01 HW-19 still UNVERIFIED",
            "recommended_vs_observed": "observed = a 15 A fuse is reported installed; "
                                       "recommended = no rating is defensible without the "
                                       "conductor ampacity inputs. The deviation is open; "
                                       "this audit does not certify compliance.",
            "closes_with": "a photograph of the fuse body rating + conductor insulation class, "
                           "run length and bundling so an ampacity can be stated (fuse note ~:53: "
                           "'no conductor evidence today -> no freeze')",
        },
        {
            "item": "cable_positions",
            "check": "probe and power cable routing unchanged from the frozen geometry",
            "status": "NEED_USER_ACTION",
            "observed": "routing/bundling not recorded anywhere in committed evidence",
            "closes_with": "a dated routing photo set matched to the geometry freeze",
        },
    ]
    for item in items:
        item["basis"] = "AUTHORED_FROM_COMMITTED_EVIDENCE (physical check the host " \
                        "cannot compute; it closes only when the named artifact changes)"
    return items


# ---------------------------------------------------------------------------
# A-W12-04 hardware config signoff + dataset validity table
# ---------------------------------------------------------------------------
INTENDED_HARDWARE_CONFIG = "CG-HW-001"   # the label W01's as-built record gives this rig
# Verification is split into three layers that are earned separately, because a name is not
# evidence, a readable file is not an inspection, and a matching hash is not a person's act:
#   REFERENCE_VALID        a dated, resolvable, repository-relative record exists
#   EVIDENCE_REVIEWED      a named person bound that exact record by recomputed content hash
#   AUTHORIZED_PROVENANCE  an approval traceable to a record this tooling does not author
# Only the third layer, on top of the other two, may produce a VERIFIED configuration - and even
# then the claim is provenance-level. Host code cannot prove a physical inspection happened, that
# a probe has not moved, or that a human intended anything, so physical acceptance stays pending.
CONFIGURATION_EVIDENCE_REQUIREMENTS = {
    "sensor_rom_readback": ("DS18B20 ROM identities read back from the devices, not copied "
                            "from the configuration table"),
    "probe_role_labels": ("probe role labels asserted by the capture itself for every frozen "
                          "slot (t1, t2, t3, t4)"),
    "role_map_consistent_with_freeze": ("no captured role token contradicts the operator-frozen "
                                        "slot->role map. This is a consistency test against the "
                                        "frozen map held in source; it is NOT proof that a probe "
                                        "has not physically moved since the freeze"),
    "installed_image_identity": ("the installed image identified from this capture's own "
                                 "configuration identity"),
    "physical_inspection_reference_valid": ("a dated, repository-resolvable physical inspection "
                                            "record naming this configuration - reference "
                                            "validity only, not evidence that anyone reviewed it"),
}
INSPECTION_ASPECTS = ("sensor_fixtures", "v1_mounting", "terminals", "fuse_body_marking",
                      "conductor_marking")
REVIEW_RECORD_FIELDS = ("reviewed_by", "reviewed_on", "inspected_aspects", "evidence")
APPROVAL_RECORD_FIELDS = ("approval", "approved_by", "approved_on", "evidence_ref",
                          "provenance_source")
APPROVAL_SCOPE = "hardware-configuration-verification"
PLACEHOLDER_REF_TOKENS = {"todo", "tbd", "none", "n/a", "na", "unknown", "x", "placeholder", "-"}
SELF_AUTHORED_NAMESPACE = "evidence/A/W12"
DATE_PATTERN = re.compile(r"20\d{2}-\d{2}-\d{2}")
# A signoff is a person's act. These words name host machinery or roles, never an identifiable
# human, so they can neither review a physical inspection nor approve a configuration.
NON_HUMAN_PARTIES = ("host", "tool", "audit", "agent", "validator", "script", "python",
                     "cg_w12_drift_audit", "validate_w12", "coordinator", "ci", "bot",
                     "member a", "operator a", "system", "automation")


def _human_party(value: object) -> str:
    """A named person, or the empty string when the value is host tooling, a role or absent."""
    text_value = str(value or "").strip()
    if not text_value:
        return ""
    if any(token in text_value.lower() for token in NON_HUMAN_PARTIES):
        return ""
    return text_value


def _traceable_ref(ref: object) -> dict[str, object]:
    """REFERENCE_VALID: the record resolves in the repository, is dated, and is not a placeholder.

    The weakest layer by design: nothing here shows a human looked at the rig, only that a
    well-formed record exists at a path a consumer can open.
    """
    value = str(ref or "").strip()
    out: dict[str, object] = {"reference": value, "reference_valid": False, "date": None,
                              "sha256": None, "reason": "no reference given"}
    if not value or value.lower() in PLACEHOLDER_REF_TOKENS:
        out["reason"] = "empty or placeholder reference"
        return out
    if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("/", "~", "..")):
        out["reason"] = "reference is not repository-relative"
        return out
    candidate = REPO_ROOT / value.replace("\\", "/")
    if not candidate.is_file():
        out["reason"] = "referenced record does not resolve in the repository"
        return out
    try:
        data = candidate.read_bytes()
    except OSError as exc:
        out["reason"] = f"referenced record unreadable: {exc.__class__.__name__}"
        return out
    stamp = (DATE_PATTERN.search(candidate.name)
             or DATE_PATTERN.search(data.decode("utf-8", errors="replace")[:8000]))
    if stamp is None:
        out["reason"] = ("no ISO YYYY-MM-DD date in the referenced record or its name, which is "
                         "what a dated physical inspection asks for")
        return out
    out["reference_valid"] = True
    out["date"] = stamp.group(0)
    out["sha256"] = hashlib.sha256(data).hexdigest()
    out["reason"] = ""
    return out


def _slot_tokens_disagree_with_freeze(tokens: dict[str, object]) -> bool:
    """True when any captured role token conflicts with the operator-frozen map for its slot."""
    for slot, role in FROZEN_SLOT_ROLES.items():
        seen = tokens.get(slot) or []
        names = [seen] if isinstance(seen, str) else list(seen)
        frozen = role.upper()
        for name in names:
            token = str(name or "").strip().upper()
            if not token or token in ROLE_UNASSIGNED_TOKENS:
                continue
            if token != frozen and token not in frozen and frozen not in token:
                return True
    return False


def _configuration_evidence(cap: dict[str, object]) -> dict[str, bool]:
    """The capture-side census, failing closed on absence and on contradiction.

    ``probe_role_labels`` and ``role_map_consistent_with_freeze`` stay separate on purpose: four
    slots can be fully labelled and still disagree with the freeze (a hot-side token in the centre
    slot is labelled, not correct), and a labelled-but-contradictory rig must never be verifiable.
    """
    role = cap.get("role_geometry_audit", {}) or {}
    labels = role.get("role_label_status") or {}
    frozen_slots = sorted(FROZEN_SLOT_ROLES)
    labelled = bool(frozen_slots) and all(
        str(labels.get(slot, "")).upper() == "LABELLED" for slot in frozen_slots)
    contradictions = role.get("contradictions") or []
    consistent = (not contradictions
                  and str(role.get("verdict") or "").upper() == "CONSISTENT_WITH_FREEZE"
                  and not _slot_tokens_disagree_with_freeze(
                      role.get("slot_role_tokens_seen") or {}))
    identity = str(cap.get("configuration") or "")
    inspection = _traceable_ref(cap.get("physical_inspection_ref"))
    return {
        "sensor_rom_readback": bool(role.get("rom_readback_verified")),
        "probe_role_labels": bool(labelled),
        "role_map_consistent_with_freeze": bool(consistent),
        "installed_image_identity": identity.startswith("config:image="),
        "physical_inspection_reference_valid": bool(inspection["reference_valid"]),
    }


def _evidence_reviewed(cap: dict[str, object], review: object) -> dict[str, object]:
    """EVIDENCE_REVIEWED: a named person bound THIS capture's record, by hash, aspect by aspect.

    A plausible dated document that merely contains the expected words is not a review. The bound
    hash is recomputed from the file, so a self-declared hash cannot drift, and host tooling or a
    role name can never be the reviewer.
    """
    binding = _traceable_ref(cap.get("physical_inspection_ref"))
    out: dict[str, object] = {"reviewed": False, "reason": "",
                              "bound_reference": binding.get("reference"),
                              "bound_sha256": binding.get("sha256")}
    if not binding["reference_valid"]:
        out["reason"] = str(binding.get("reason") or "reference not valid")
        return out
    if not isinstance(review, dict):
        out["reason"] = "no operator review record was supplied"
        return out
    missing = [key for key in REVIEW_RECORD_FIELDS if not review.get(key)]
    if missing:
        out["reason"] = f"review record lacks {missing}"
        return out
    reviewer = _human_party(review.get("reviewed_by"))
    if not reviewer:
        out["reason"] = ("the reviewer is not a named person outside the host tooling; a tool "
                         "cannot review a physical inspection")
        return out
    if not DATE_PATTERN.fullmatch(str(review.get("reviewed_on") or "").strip()):
        out["reason"] = "review date is not an ISO YYYY-MM-DD"
        return out
    aspects = {str(item).strip() for item in (review.get("inspected_aspects") or [])}
    gaps = [aspect for aspect in INSPECTION_ASPECTS if aspect not in aspects]
    if gaps:
        out["reason"] = f"review does not cover every inspected aspect, missing {gaps}"
        return out
    bound = {str(item.get("path")): str(item.get("sha256"))
             for item in (review.get("evidence") or []) if isinstance(item, dict)}
    declared = bound.get(str(binding["reference"]))
    if declared is None:
        out["reason"] = "the review record does not bind this capture's inspection reference"
        return out
    if declared != binding["sha256"]:
        out["reason"] = ("the review binds a hash that does not match the referenced record: the "
                         "document reviewed is not the document published")
        return out
    out.update({"reviewed": True, "reviewer": reviewer,
                "reviewed_on": str(review["reviewed_on"]).strip(), "reason": ""})
    return out


def _approval_provenance(approval: object) -> dict[str, object]:
    """AUTHORIZED_PROVENANCE: an approval traceable to a record this tooling does not author.

    A matching hash proves content binding only, never that an inspection happened or that a
    person approved anything. So an approval is not accepted merely because it carries a name, a
    date and a correct hash: its provenance source must resolve, sit outside the namespace this
    tool generates, name the configuration it approves, carry a date of its own, and the approving
    party must be a person outside the host tooling. Even then the claim stays provenance-level.
    """
    out: dict[str, object] = {"valid": False, "reason": "", "approved_by": None,
                              "approved_on": None, "evidence_ref": None,
                              "provenance_source": None, "provenance_sha256": None}
    if not isinstance(approval, dict):
        out["reason"] = "no approval record was supplied"
        return out
    missing = [key for key in APPROVAL_RECORD_FIELDS
               if not str(approval.get(key) or "").strip()]
    if missing:
        out["reason"] = f"approval record lacks {missing}"
        return out
    if str(approval.get("approval") or "").strip() != APPROVAL_SCOPE:
        out["reason"] = f"approval does not declare {APPROVAL_SCOPE!r}; it authorises something else"
        return out
    person = _human_party(approval.get("approved_by"))
    if not person:
        out["reason"] = ("the approving party is not a named person outside the host tooling; no "
                         "tool, agent, validator or role can sign a physical configuration off")
        return out
    if not DATE_PATTERN.fullmatch(str(approval.get("approved_on") or "").strip()):
        out["reason"] = "approval date is not an ISO YYYY-MM-DD"
        return out
    source = str(approval.get("provenance_source") or "").strip().replace("\\", "/")
    if source.lower().startswith(SELF_AUTHORED_NAMESPACE.lower()):
        out["reason"] = ("the approval's provenance source sits inside the namespace this tool "
                         "generates, so it is self-authored and cannot attest itself")
        return out
    binding = _traceable_ref(source)
    if not binding["reference_valid"]:
        out["reason"] = str(binding.get("reason") or "provenance source not resolvable")
        return out
    evidence = _traceable_ref(approval.get("evidence_ref"))
    if not evidence["reference_valid"]:
        out["reason"] = str(evidence.get("reason") or "approval evidence not resolvable")
        return out
    body = (REPO_ROOT / source).read_text(encoding="utf-8", errors="replace")
    if INTENDED_HARDWARE_CONFIG not in body:
        out["reason"] = (f"the provenance record never names the configuration it purports to "
                         f"approve ({INTENDED_HARDWARE_CONFIG})")
        return out
    if not DATE_PATTERN.search(body):
        out["reason"] = "the provenance record carries no date of its own"
        return out
    out.update({"valid": True, "approved_by": person,
                "approved_on": str(approval["approved_on"]).strip(),
                "evidence_ref": evidence["reference"], "provenance_source": source,
                "provenance_sha256": binding["sha256"], "reason": ""})
    return out


def _verification_open_items(evidence: dict[str, bool], review: dict[str, object],
                             provenance: dict[str, object]) -> list[str]:
    """What is missing before this capture's configuration could be called verified.

    Derived per capture rather than hardcoded, so a future capture that does carry ROM readback,
    consistent labels, a pinned image and a traceable dated record closes its own items - and the
    other way round, so nothing reads as certified while a layer is unmet. Review and approval are
    listed apart from the evidence census because they are acts by a person, not properties of a
    capture.
    """
    items = [CONFIGURATION_EVIDENCE_REQUIREMENTS[key]
             for key, satisfied in evidence.items() if not satisfied]
    if not review.get("reviewed"):
        items.append("EVIDENCE_REVIEWED: a named person must bind this inspection record by "
                     "recomputed content hash and cover every inspected aspect (currently: "
                     f"{review.get('reason')})")
    if not provenance.get("valid"):
        items.append("AUTHORIZED_PROVENANCE: an approval traceable outside the host tooling is "
                     f"required (currently: {provenance.get('reason')})")
    return items


def hardware_config_signoff(captures: list[dict[str, object]],
                           review: dict[str, object] | None = None,
                           approval: dict[str, object] | None = None
                           ) -> dict[str, object]:
    """Separate what the rig is CALLED from what has been VERIFIED about it.

    Four different things were collapsed into one field before: the intended label CG-HW-001, the
    identity derived from capture evidence, the physical session identity and the signoff state. A
    dataset-validity row stamped ``hardware_config_id: CG-HW-001`` reads like a certified
    configuration even while A-W12-04 signoff is unresolved, which is how an unverified
    configuration gets pooled by a consumer that trusts the column.

    A row is VERIFIED only when all three layers hold: every capture-side evidence requirement
    (including role-map consistency with the freeze), a hash-bound named review of the physical
    inspection record, and an approval traceable to provenance this tooling does not author. An
    empty ``verification_open_items``, a resolvable file or a matching hash is not sufficient.
    Pooling eligibility is still computed, so legitimate comparisons across independent sessions
    of one configuration remain possible; it is the certification this refuses to imply.
    """
    provenance = _approval_provenance(approval)
    rows = []
    for cap in captures:
        role = cap.get("role_geometry_audit", {}) or {}
        pzem = cap.get("pzem_audit", {}) or {}
        evidence = _configuration_evidence(cap)
        review_state = _evidence_reviewed(cap, review)
        reference_valid = all(evidence.values())
        verified = bool(reference_valid and review_state["reviewed"] and provenance["valid"])
        rows.append({
            "capture": cap.get("capture"),
            "intended_hardware_config": INTENDED_HARDWARE_CONFIG,
            "evidence_derived_config_identity": cap.get("configuration"),
            "physical_session_identity": sorted(cap.get("boot_ids") or []),
            "configuration_evidence": evidence,
            "reference_valid": bool(reference_valid),
            "evidence_reviewed": bool(review_state["reviewed"]),
            "authorized_provenance_valid": bool(provenance["valid"]),
            "inspection_reference": _traceable_ref(cap.get("physical_inspection_ref")),
            "review_binding": review_state,
            "approval_provenance": provenance,
            "config_verification": "VERIFIED" if verified else "UNVERIFIED",
            "verification_open_items": _verification_open_items(evidence, review_state, provenance),
            "is_probe_identification": role.get("is_probe_identification"),
            "role_verdict": role.get("verdict"),
            "electrical_qualification": pzem.get("electrical_qualification"),
            "dataset_pooling_eligibility": (cap.get("configuration"), role.get("verdict"),
                                            pzem.get("electrical_qualification")),
        })
    groups: dict[str, list[str]] = {}
    for row in rows:
        groups.setdefault(str(row["dataset_pooling_eligibility"]), []).append(row["capture"])
    unverified = [row["capture"] for row in rows if row["config_verification"] == "UNVERIFIED"]
    # READY_FOR_SIGNOFF needs every technical requirement AND the named reviews: a resolvable
    # reference alone never lifts the state out of UNRESOLVED.
    prerequisites = bool(rows) and all(row["reference_valid"] and row["evidence_reviewed"]
                                      for row in rows)
    if rows and not unverified:
        signoff_status = "SIGNED_OFF"
    elif prerequisites:
        signoff_status = "READY_FOR_SIGNOFF"
    else:
        signoff_status = "UNRESOLVED"
    return {
        "requirement": "A-W12-04",
        "intended_hardware_config": INTENDED_HARDWARE_CONFIG,
        "configuration_signoff_status": signoff_status,
        "verification_layers": {
            "REFERENCE_VALID": ("a dated, repository-resolvable, non-placeholder physical "
                                "inspection record exists for every capture - the existence of a "
                                "record, not an act by a person"),
            "EVIDENCE_REVIEWED": ("a named person outside the host tooling bound each inspection "
                                  "record by recomputed SHA-256 and enumerated every inspected "
                                  "aspect"),
            "AUTHORIZED_PROVENANCE": ("an approval of hardware-configuration-verification traced "
                                      "to a record outside the namespace this tool generates"),
        },
        "host_cannot_verify_human_authenticity": True,
        "physical_acceptance_pending": not bool(provenance["valid"]),
        "approval_record": provenance,
        "approval_record_fields_required": list(APPROVAL_RECORD_FIELDS),
        "review_record_fields_required": list(REVIEW_RECORD_FIELDS),
        "inspection_aspects_required": list(INSPECTION_ASPECTS),
        "verification_requirements": dict(CONFIGURATION_EVIDENCE_REQUIREMENTS),
        "captures_without_verified_configuration": unverified,
        "what_the_label_is_not": ("CG-HW-001 is the intended label for this rig from the W01 "
                                  "as-built record. It is not a verified identity, not a "
                                  "signoff, and not evidence that two captures share a physical "
                                  "configuration - that is what evidence_derived_config_identity "
                                  "and the pooling columns say."),
        "what_a_matching_hash_does_not_prove": ("content binding only. It does not show that a "
                                                "physical inspection happened, that a probe has "
                                                "not moved since the freeze, or that a named "
                                                "person approved anything; those need the "
                                                "operator's own authorization provenance, which "
                                                "no host check can manufacture."),
        "what_would_close_signoff": [
            "photograph the installed fuse body and conductor marking (see A-W12-03 items)",
            "read the DS18B20 ROMs back from the devices rather than from the config table",
            "assert probe roles in the capture, or record the mapping as a witnessed inspection",
            "a named person reviews the dated inspection record and binds it by content hash",
            "a named person authorises hardware-configuration-verification through provenance "
            "this tooling does not author; a host audit cannot sign it",
        ],
        "dataset_validity_table": rows,
        "poolable_groups": {g: names for g, names in groups.items()},
        "must_not_pool": [
            "probe-identification touch captures vs any plant capture",
            "captures whose roles disagree with the freeze vs captures that follow it",
            "captures from different installed images (configuration identity differs)",
            "captures whose electrical qualification differs",
        ],
    }


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# A-W12-05 gate G3 input (A-side only, never a whole-team claim)
# ---------------------------------------------------------------------------
def gate_g3_input(audit: dict[str, object]) -> dict[str, object]:
    """The A-side signoff statement fed to the team G3 gate.

    It states Member A's position and its blockers. It does NOT declare G3
    GREEN: that is a whole-team decision this slice cannot own and is explicitly
    prohibited here. It never upgrades a host finding to PHYSICALLY_VERIFIED.

    The electrical-qualification blocker is DERIVED from the audit's own captures
    so it closes automatically if a later capture supplies a qualified channel
    (asserting it forever would fail the very OPERATOR_ACTION_QUEUE this slice
    asks for). The mechanical blockers cannot be computed from host bytes, so
    they are labelled AUTHORED - a claim to re-derive from a fresh bench artifact,
    not a live measurement - and never a whole-team GREEN.
    """
    captures = audit.get("captures", [])
    plant = [c for c in captures if not c.get("is_probe_identification")]
    electrical_unqualified = any(
        (c.get("pzem_audit", {}).get("electrical_qualification") == "UNQUALIFIED")
        for c in plant)
    blockers: list[dict[str, str]] = []
    if electrical_unqualified:
        blockers.append({
            "blocker": "no qualified electrical channel in the committed capture "
                       "(current_status/voltage_status empty) - A-W12-02 figures are UNQUALIFIED",
            "derivation": "COMPUTED_FROM_AUDIT",
            "open": True,
        })
    # Mechanical inspection and fuse deviation cannot be observed from host bytes;
    # they are authored statements, each closing only when its named artifact lands.
    blockers.append({
        "blocker": "sensor fixtures, V1 mounting, terminals and cable routing have no "
                   "post-freeze inspection record - A-W12-03 NEED_USER_ACTION",
        "derivation": "AUTHORED_FROM_COMMITTED_EVIDENCE",
        "open": True,
    })
    blockers.append({
        "blocker": "fuse/conductor deviation remains open and uncertified - A-W12-03 "
                   "BLOCKED_HARDWARE",
        "derivation": "AUTHORED_FROM_COMMITTED_EVIDENCE",
        "open": True,
    })
    a_side_status = "NEED_USER_ACTION" if any(b["open"] for b in blockers) else "READY_FROM_HOST"
    return {
        "requirement": "A-W12-05",
        "provided_by": "Member A (host drift audit only)",
        "statement": "plant stable enough for predictive development: CANNOT BE SIGNED OFF FROM "
                     "HOST EVIDENCE ALONE",
        "does_not_declare": "G3 GREEN (a whole-team gate this slice must not set)",
        "a_side_status": a_side_status,
        "blockers": blockers,
        "what_a_would_sign": "the committed datasets are internally consistent within each "
                             "configuration, but the mechanical and electrical-qualification "
                             "items above must close before A contributes a signoff",
    }


# ---------------------------------------------------------------------------
# Whole-capture pipeline
# ---------------------------------------------------------------------------
def audit_capture(path: pathlib.Path) -> dict[str, object]:
    rows = _valid_rows(load_capture(path))
    if is_probe_identification(path, rows):
        # Classified and excluded; we still record its presence so the signoff
        # shows it was seen and deliberately kept out of the statistics.
        return {
            "capture": path.name,
            "configuration": "PROBE_IDENTIFICATION::" + path.name,
            "is_probe_identification": True,
            "sensor_consistency": {"status": "EXCLUDED_PROBE_IDENTIFICATION"},
            "role_geometry_audit": {
                "capture": path.name, "is_probe_identification": True,
                "contradictions": [], "verdict": "PROBE_IDENTIFICATION_EXCLUDED",
                "slot_role_tokens_seen": {}, "role_label_status": {},
            },
            "pzem_audit": {"status": "EXCLUDED_PROBE_IDENTIFICATION"},
        }
    return {
        "capture": path.name,
        "configuration": configuration_of(path, rows),
        "is_probe_identification": False,
        "frames": len(rows),
        "boot_ids": _boot_ids(rows),
        "content_sha256": _content_hash(rows),
        "sensor_consistency": sensor_consistency(rows),
        "role_geometry_audit": role_geometry_audit(rows, path),
        "pzem_audit": pzem_zero_active_audit(rows),
    }


def build_report(capture_paths: list[pathlib.Path]) -> dict[str, object]:
    captures = [audit_capture(p) for p in capture_paths]
    real = [c for c in captures if not c.get("is_probe_identification")]
    report = {
        "tool": "cg_w12_drift_audit.py",
        "week": "W12",
        "generated_utc": _now_utc(),
        "evidence_kind": "HOST_ANALYSIS_OF_COMMITTED_CAPTURES",
        "physical_verified": False,
        "touches_hardware": False,
        "captures": captures,
        "cross_session_drift": cross_session_drift(real),
        "mechanical_audit_checklist": mechanical_audit_checklist(),
        "hardware_config_signoff": hardware_config_signoff(captures),
        "gate_g3_input": {},
    }
    report["gate_g3_input"] = gate_g3_input(report)
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def default_captures() -> list[pathlib.Path]:
    """The committed captures this audit runs on.

    Only captures whose columns are compatible with the thermal/electrical
    audit are fed in; the g1/g2a OFF-capture uses a different schema and is
    referenced for identity, not re-analysed as a cooling dataset.
    """
    paths = [EVIDENCE / "W04" / "tec-cooling-response-600s.csv"]
    return [p for p in paths if p.is_file()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--capture", type=pathlib.Path, action="append",
                        help="specific capture CSV(s) to audit; defaults to the committed W04 cooling capture")
    parser.add_argument("--json-out", type=pathlib.Path, help="write the full JSON report here")
    args = parser.parse_args(argv)

    paths = args.capture if args.capture else default_captures()
    paths = [p if p.is_absolute() else (REPO_ROOT / p) for p in paths]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        print("MISSING_CAPTURES: " + ", ".join(missing), file=sys.stderr)
        return 2

    report = build_report(paths)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8", newline="\n")
    # Human summary on stdout.
    for cap in report["captures"]:
        print(f"capture={cap['capture']} config={cap.get('configuration')} "
              f"probe_id={cap.get('is_probe_identification')}")
        rga = cap.get("role_geometry_audit", {})
        print(f"  role_verdict={rga.get('verdict')} contradictions={len(rga.get('contradictions', []))}")
        pz = cap.get("pzem_audit", {})
        if pz.get("electrical_qualification"):
            print(f"  electrical={pz['electrical_qualification']} "
                  f"duty0_stale={len(pz.get('duty0_with_current_frames', {}).get('stale_register_frames', []))}")
    print(f"gate_g3_input.status={report['gate_g3_input']['a_side_status']} "
          f"(does_not_declare={report['gate_g3_input']['does_not_declare']!r})")
    print("W12 DRIFT AUDIT: HOST_ANALYSIS_ONLY (no hardware, no PHYSICALLY_VERIFIED)")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
