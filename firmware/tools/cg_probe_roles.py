"""Single host-side source of truth for DS18B20 probe roles (A-W07 / W09 handoff).

Why this module exists
----------------------

The operator-frozen as-built record and the checked-in W02 firmware/host map state
different things about **three of the four slots**, and the host analysis layer
previously encoded the exclusion as a hand-written boolean per representation:

* `evidence/A/W02/sensor-rom-map.yaml:60-92` puts T1 `287088CA00000051` at
  `position_semantics: near_door`, T2 `28AEBF2200000006` at `center` and T3
  `28CBE9CA00000072` at `far_opposite`, all with `physical_label: PENDING` and
  `physical_position_verified: false`, while `283BE5C9000000A9` sits under `spare:`
  (`:82-92`) with `assigned_role: null`. `firmware/main/coldguard_config.h:232-239`
  mirrors that. The as-built record says T1 = CHAMBER_CENTER, T2 = TEC_HOT_SIDE,
  T3 = CHAMBER_BOTTOM and that spare ROM = CHAMBER_NEAR_DOOR, so the plan mislabels
  T1, T2 and T3 and leaves the genuine near-door probe unassigned.
* `evidence/A/W07/geometry-v1.md:117` and the operator-frozen as-built record put
  the same ROM at `TEC_HOT_SIDE`, with `283BE5C9000000A9` as `CHAMBER_NEAR_DOOR`.

`evidence/A/W07/probe-identification-v0.md` is `ACCEPTED BY THE OPERATOR as the
official as-built sensor location record`, and `geometry-v1.md:88-104` explains that
the W02 text is a **superseded plan** rather than a live contradiction: it was never
claimed verified (`physical_position_verified: false` still reads false there, and
level 4 of the IHA-01 reconciliation - independent proof of no movement - is
`NOT_AVAILABLE`). So this module encodes the as-built record, and nothing here
promotes it to independently verified hardware fact.

The fragility this removes
--------------------------

Keying the exclusion on the *word* `T2` is what made it breakable: the invariant is
"a hot-side probe must not enter a chamber-air aggregate", and which column that is
has to come from the role, not from a literal that happens to be spelled `t2_c`.
Everything here is therefore keyed on the 8-byte ROM code as a 16-hex-digit string,
with the slot/column derived from it, plus one cross-check against the role token
the device itself emitted in the capture.

Scope
-----

Host analysis only. This does not touch firmware C code - the live frames still read
`t2_role=HOT_SIDE` with `t1/t3/t4_role=UNASSIGNED` and the boot line still labels
every probe `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`
(`evidence/A/W02/sensor-rom-map.yaml:28`). Do not describe the firmware as knowing
these positions.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

FROZEN_GEOMETRY_CLASS = (
    "OPERATOR_FROZEN_AS_BUILT_2026-11-02_PROBE_IDENTIFICATION_RECORD_NOT_REMEASURED"
)

# ROM (16 hex digits, wire order) -> physical position, per the frozen as-built record.
ROM_POSITION_BY_ROM: dict[str, str] = {
    "287088CA00000051": "CHAMBER_CENTER",
    "28AEBF2200000006": "TEC_HOT_SIDE",
    "28CBE9CA00000072": "CHAMBER_BOTTOM",
    "283BE5C9000000A9": "CHAMBER_NEAR_DOOR",
}

#: The ROM that must never contribute to a chamber-air aggregate.
HOT_SIDE_ROM = "28AEBF2200000006"

#: The three ROMs that sit in chamber air and may be aggregated over it.
CHAMBER_AIR_ROMS = frozenset(
    rom for rom, position in ROM_POSITION_BY_ROM.items() if position != "TEC_HOT_SIDE"
)

# ROM -> the firmware slot name it occupies today.
ROM_TO_SLOT: dict[str, str] = {
    "287088CA00000051": "t1",
    "28AEBF2200000006": "t2",
    "28CBE9CA00000072": "t3",
    "283BE5C9000000A9": "t4",
}

#: Slot -> ROM, the reverse direction the capture columns are keyed on.
SLOT_TO_ROM: dict[str, str] = {slot: rom for rom, slot in ROM_TO_SLOT.items()}


def position_of_slot(slot: str) -> str:
    """The frozen physical position of a firmware slot name (`t1`..`t4`)."""
    rom = SLOT_TO_ROM.get((slot or "").lower().strip())
    if rom is None:
        raise KeyError(f"{slot!r} is not a slot in the frozen as-built map")
    return ROM_POSITION_BY_ROM[rom]

#: Physical positions that are chamber air, as a named role set.
CHAMBER_AIR_POSITIONS = frozenset({"CHAMBER_CENTER", "CHAMBER_BOTTOM", "CHAMBER_NEAR_DOOR"})
#: Positions that are not air at all and are therefore excluded from air statistics.
NON_AIR_POSITIONS = frozenset({"TEC_HOT_SIDE"})

#: Slot names whose probe is in chamber air, derived from the ROM map above.
CHAMBER_AIR_SLOTS = tuple(
    sorted(ROM_TO_SLOT[rom] for rom in CHAMBER_AIR_ROMS)
)
HOT_SIDE_SLOT = ROM_TO_SLOT[HOT_SIDE_ROM]

#: Column names used by the W07 capture CSVs and the repeatability representations.
CHAMBER_AIR_COLUMNS = tuple(f"{slot}_c" for slot in CHAMBER_AIR_SLOTS)
HOT_SIDE_COLUMN = f"{HOT_SIDE_SLOT}_c"

#: The same roles in the uppercase slot vocabulary `cg_serial.MEASUREMENT_ROLES`
#: uses. Callers that want an air-only spread must pass this explicitly; the
#: historical default of `consistency_stats`/`max_disagreement` is left alone so
#: existing artifacts keep meaning what they meant when they were published.
CHAMBER_AIR_ROLE_NAMES = tuple(slot.upper() for slot in CHAMBER_AIR_SLOTS)
HOT_SIDE_ROLE_NAME = HOT_SIDE_SLOT.upper()

#: Device role tokens that mean "this probe is on the hot side".
DEVICE_HOT_SIDE_TOKENS = frozenset({"HOT_SIDE", "TEC_HOT_SIDE"})

#: Every known slot, so a capture can be checked slot by slot.
ALL_SLOTS = tuple(ROM_TO_SLOT.values())

#: Reason carried into every artifact, so the exclusion is explained not just done.
EXCLUDED_FROM_CHAMBER_AIR = {
    HOT_SIDE_COLUMN: "TEC_HOT_SIDE is a heatsink surface, not chamber air",
}


class HotSideInChamberAirError(RuntimeError):
    """A chamber-air aggregate was configured to include the hot-side probe."""


def position_of(rom: str) -> str | None:
    """The frozen physical position of a ROM code, or None if it is not known."""
    return ROM_POSITION_BY_ROM.get((rom or "").upper().strip())


#: `cg_serial`'s token for the fourth probe: it says SPARE, never T4.
SERIAL_SPARE_TOKEN = "SPARE"

#: Slot -> the role token `cg_serial.MEASUREMENT_ROLES` / `Sample.temps` keys use.
#: Two vocabularies address the same probe, and the difference is load-bearing:
#: `cg_serial.consistency_stats` keys the fourth probe `SPARE`, so a set spelled
#: ("T1","T3","T4") cannot address it and would raise KeyError instead of
#: producing a spread.
SLOT_TO_SERIAL_ROLE: dict[str, str] = {
    slot: (SERIAL_SPARE_TOKEN if slot == "t4" else slot.upper())
    for slot in ROM_TO_SLOT.values()
}

#: The air slots in the serial vocabulary, derived so it cannot drift.
CHAMBER_AIR_SERIAL_ROLES = tuple(
    SLOT_TO_SERIAL_ROLE[slot] for slot in CHAMBER_AIR_SLOTS)
HOT_SIDE_SERIAL_ROLE = SLOT_TO_SERIAL_ROLE[HOT_SIDE_SLOT]

#: Serial token -> slot, the reverse direction the guard needs.
SERIAL_TOKEN_TO_SLOT: dict[str, str] = {
    serial_role.lower(): slot for slot, serial_role in SLOT_TO_SERIAL_ROLE.items()
}


def slot_of_term(term: object) -> str | None:
    """Fold one aggregate term to a slot name across every vocabulary in this repo.

    A chamber-air term can arrive as the capture column `t2_c`, the bare slot `t2`,
    the uppercase role token `T2` that `cg_serial.MEASUREMENT_ROLES` uses, that
    token's column form `T2_C`, the serial spare token `SPARE`, or the 16-hex ROM
    itself. Matching only the exact string `t2_c` let the uppercase vocabulary slip
    through the guard untouched, so `require_chamber_air(("T1","T2","T3"))` - the
    literal docs/01 §20.1 mean - passed. This is the normaliser that closes it: it
    is case- and decoration-insensitive, and every branch lands on the ROM-keyed
    map rather than on a name it recognises.

    Returns None when the term addresses no known probe, which is reported as
    "not the hot side", never as "safe chamber air": a caller that needs an air set
    must ask for it by name (see `air_only_serial_roles`), so an unknown token can
    never be silently aggregated.
    """
    text = str(term or "").strip().lower()
    if not text:
        return None
    if text in ROM_TO_SLOT.values():
        return text
    if text in SERIAL_TOKEN_TO_SLOT:
        return SERIAL_TOKEN_TO_SLOT[text]
    upper = text.upper()
    if upper in ROM_TO_SLOT:          # the 16-hex ROM itself, either case
        return ROM_TO_SLOT[upper]
    for suffix in ("_c", "_role", "_temp_c", "_status"):
        if text.endswith(suffix) and text[: -len(suffix)] in ROM_TO_SLOT.values():
            return text[: -len(suffix)]
    return None


def is_hot_side_column(column: object) -> bool:
    """True for ANY spelling of the hot-side probe's term, not only `t2_c`."""
    return slot_of_term(column) == HOT_SIDE_SLOT


def hot_side_columns(columns) -> tuple[str, ...]:
    """The subset of `columns` that is the hot side, per the frozen ROM map."""
    return tuple(column for column in columns if is_hot_side_column(column))


def chamber_air_columns(columns) -> tuple[str, ...]:
    """The subset of `columns` that may enter a chamber-air aggregate."""
    return tuple(column for column in columns if not is_hot_side_column(column))


def is_chamber_air_safe(columns) -> bool:
    """True only if no term of this aggregate is the hot-side probe."""
    return not any(is_hot_side_column(column) for column in columns)


def derive_hot_side_columns_from_device(rows) -> set[str]:
    """Which columns the DEVICE itself declared hot side, from `t<n>_role` tokens.

    Read-only cross-check: it never invents a role. A capture whose role columns
    are absent contributes nothing, which is reported as no evidence rather than
    as agreement.
    """
    found: set[str] = set()
    for slot in ROM_TO_SLOT.values():
        role_column = f"{slot}_role"
        value_column = f"{slot}_c"
        for row in rows:
            token = (row.get(role_column) or "").strip().upper()
            if token in DEVICE_HOT_SIDE_TOKENS:
                found.add(value_column)
                break
    return found


def check_capture_against_frozen_map(rows) -> dict[str, object]:
    """Compare a real capture's device-emitted roles with the frozen ROM map.

    Three outcomes, kept distinct: no device role at all is `NO_DEVICE_EVIDENCE`,
    a role that matches the frozen map is `AGREES`, and a role that points at a
    different slot is a hard failure, because it means the geometry moved and
    every chamber-air aggregate built on it is void.
    """
    device_hot = sorted(derive_hot_side_columns_from_device(rows))
    role_columns_present = [f"{slot}_role" for slot in ALL_SLOTS
                            if any((row.get(f"{slot}_role") or "").strip() for row in rows)]
    unassigned = [slot for slot in ALL_SLOTS
                  if any((row.get(f"{slot}_role") or "").strip().upper() == "UNASSIGNED"
                         for row in rows)
                  and f"{slot}_role" in role_columns_present]
    if not device_hot:
        state = "NO_DEVICE_EVIDENCE"
    elif device_hot == [HOT_SIDE_COLUMN]:
        state = "AGREES"
    else:
        raise HotSideInChamberAirError(
            f"the capture's own role fields say {device_hot} is the hot side, which "
            f"contradicts the frozen map ({[HOT_SIDE_COLUMN]}); the probes moved and "
            f"every chamber-air aggregate from this capture is void")
    return {
        "geometry_class": FROZEN_GEOMETRY_CLASS,
        "hot_side_column": HOT_SIDE_COLUMN,
        "hot_side_rom": HOT_SIDE_ROM,
        "chamber_air_columns": list(CHAMBER_AIR_COLUMNS),
        "device_declared_hot_side": device_hot,
        "device_role_columns_present": role_columns_present,
        "device_role_unassigned_slots": unassigned,
        "device_role_check": state,
        "note": (
            "only the hot-side slot carries a device-emitted HOT_SIDE token in the "
            "committed capture; t1/t3/t4 are present but read UNASSIGNED, so their "
            "chamber-air membership comes from the frozen operator record, not from "
            "a device readback"
        ),
    }


def require_chamber_air(columns, *, name: str) -> None:
    """Fail closed if `columns` are published as a chamber-air aggregate."""
    offenders = hot_side_columns(columns)
    if offenders:
        raise HotSideInChamberAirError(
            f"representation {name!r} is declared as chamber air but averages the "
            f"hot-side probe {list(offenders)}; the as-built hot side is "
            f"ROM {HOT_SIDE_ROM} at slot {HOT_SIDE_SLOT}")


def air_only_serial_roles() -> tuple[str, ...]:
    """The `cg_serial` role set a chamber-air spread must be taken over.

    Self-checking: this returns the air roles only if the hot side is genuinely not
    among them and every token addresses a known slot, so a later edit to the frozen
    map cannot turn the air-only helper into the thing it exists to prevent.
    """
    unknown = [role for role in CHAMBER_AIR_SERIAL_ROLES
               if slot_of_term(role) not in CHAMBER_AIR_SLOTS]
    if unknown:
        raise HotSideInChamberAirError(
            f"the derived air role set {unknown} no longer addresses only chamber-"
            f"air slots; the frozen map and cg_serial's vocabulary disagree")
    if HOT_SIDE_SERIAL_ROLE in CHAMBER_AIR_SERIAL_ROLES:
        raise HotSideInChamberAirError(
            f"the derived air role set contains {HOT_SIDE_SERIAL_ROLE!r}, the "
            f"hot-side token (ROM {HOT_SIDE_ROM})")
    return CHAMBER_AIR_SERIAL_ROLES


def air_only_max_disagreement(stats: dict) -> float | None:
    """`max(mean) - min(mean)` over the chamber-air probes ONLY.

    Why this exists beside `cg_serial.max_disagreement` rather than instead of it:
    that function defaults to `MEASUREMENT_ROLES = ("T1","T2","T3")`, which on the
    as-built rig spans the TEC hot side, and it is what produced the `G_T = Tmax -
    Tmin` figures in the published W02/W04 artifacts. Editing its default would
    silently reinterpret evidence already delivered, so the historical function is
    left byte-for-byte alone and this is the air-only counterpart. The arithmetic is
    delegated, not re-implemented, so the two cannot drift apart.

    `stats` is a `cg_serial.consistency_stats` mapping. Because the air set includes
    the fourth probe, which `cg_serial` keys `SPARE`, stats must be built with
    `roles=cg_serial.ALL_ROLES` (or with `air_only_serial_roles()`).
    """
    from cg_serial import max_disagreement  # local: this module stays a dependency-free leaf
    roles = air_only_serial_roles()
    missing = [role for role in roles if role not in stats]
    if missing:
        raise KeyError(
            f"air-only spread needs role stats for {list(roles)}; {missing} are "
            f"absent - build them with cg_serial.consistency_stats(samples, "
            f"roles=cg_serial.ALL_ROLES)")
    return max_disagreement(stats, roles)


def air_only_pairwise_mean_differences(stats: dict) -> dict:
    """Pairwise mean differences over the air set only; same delegation rule."""
    from cg_serial import pairwise_mean_differences
    roles = air_only_serial_roles()
    missing = [role for role in roles if role not in stats]
    if missing:
        raise KeyError(f"air-only differences need role stats for {list(roles)}; "
                       f"{missing} are absent")
    return pairwise_mean_differences(stats, roles)


#: Where the superseded plan map lives, relative to the repository root.
W02_PLAN_MAP_RELPATH = "evidence/A/W02/sensor-rom-map.yaml"

#: Plan `position_semantics` tokens mapped to the as-built position vocabulary.
#: Anything not listed here is reported as its own string, never guessed at.
PLAN_SEMANTICS_TO_POSITION: dict[str, str] = {
    "near_door": "CHAMBER_NEAR_DOOR",
    "center": "CHAMBER_CENTER",
    "far_opposite": "CHAMBER_FAR_OPPOSITE",
}


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def plan_positions_from_w02_map(path: pathlib.Path | None = None) -> dict[str, dict[str, str]]:
    """ROM -> what the superseded W02 plan claimed about it, read from the file.

    Read with a targeted block scan rather than a YAML library, because this module is
    a stdlib-only leaf that many checkers import: it walks the `roles:` and `spare:`
    blocks, takes each `- ` item's `role` / `position_semantics` / `rom_hex` /
    `assigned_role` / `physical_position_verified`, and stops at the next top-level
    key. A ROM with no `position_semantics` and `assigned_role: null` is reported as
    `UNASSIGNED_IN_PLAN` rather than guessed at, because the plan really does leave
    the fourth probe unassigned - and that probe is the one sitting by the door.
    """
    path = path or (_repo_root() / W02_PLAN_MAP_RELPATH)
    if not path.is_file():
        return {}
    blocks: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_block = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if raw and not raw.startswith((" ", "\t", "#")):
            key = stripped.split(":")[0]
            in_block = key in ("roles", "spare")
            continue
        if not in_block or not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            current = {}
            blocks.append(current)
            stripped = stripped[2:].strip()
        if current is None or ":" not in stripped:
            continue
        field, _, value = stripped.partition(":")
        value = value.split("#")[0].strip().strip('"')
        current[field.strip()] = value
    found: dict[str, dict[str, str]] = {}
    for block in blocks:
        rom = block.get("rom_hex", "").upper()
        if rom not in ROM_POSITION_BY_ROM:
            continue
        semantics = block.get("position_semantics")
        if not semantics:
            semantics = ("UNASSIGNED_IN_PLAN"
                         if block.get("assigned_role", "null") in ("", "null", "None")
                         else "ASSIGNED_OTHER")
        found[rom] = {
            "position_semantics": semantics,
            "physical_position_verified": block.get("physical_position_verified", ""),
            "plan_role": block.get("role", "SPARE"),
        }
    return found


def superseded_plan_disclosure(path: pathlib.Path | None = None) -> dict[str, object]:
    """Every slot where the checked-in W02 plan and the frozen as-built map differ.

    This used to be a hand-written sentence naming T2 alone. It is now recomputed from
    `evidence/A/W02/sensor-rom-map.yaml`, and the test over it fails if the list ever
    shrinks: the plan misdescribes the chamber as a whole - T1 `near_door` against
    CHAMBER_CENTER, T2 `center` against TEC_HOT_SIDE, T3 `far_opposite` against
    CHAMBER_BOTTOM - while the probe that was supposed to sit near the door is the one
    the plan never assigned a role to at all.
    """
    plan = plan_positions_from_w02_map(path)
    mismatches: list[dict[str, object]] = []
    for rom, as_built in sorted(ROM_POSITION_BY_ROM.items()):
        entry = plan.get(rom)
        if entry is None:
            continue
        semantics = entry["position_semantics"]
        planned_position = PLAN_SEMANTICS_TO_POSITION.get(semantics, semantics)
        if planned_position != as_built:
            mismatches.append({
                "rom": rom,
                "plan_slot": ROM_TO_SLOT[rom],
                "plan_role": entry["plan_role"],
                "plan_position_semantics": semantics,
                "plan_implied_position": planned_position,
                "as_built_position": as_built,
                "physical_position_verified_in_plan": entry["physical_position_verified"],
            })
    return {
        "source": W02_PLAN_MAP_RELPATH,
        "read": bool(plan),
        "status": ("DERIVED_FROM_CHECKED_IN_PLAN" if plan else "PLAN_MAP_UNREADABLE"),
        "mismatched_slots": sorted(str(m["plan_slot"]).upper() for m in mismatches),
        "mismatches": mismatches,
        "classification": (
            "superseded plan, never claimed verified: physical_position_verified is "
            "false in the plan itself and IHA-01 level 4 (independent proof that no "
            "probe moved after the freeze) is NOT_AVAILABLE"),
        "handling": (
            "disclosed, not rewritten: the W02 file is another week's published "
            "evidence, so nothing here edits it or promotes the as-built map to a "
            "re-measured fact"),
    }


def probe_identity_export() -> dict[str, object]:
    """The per-slot role block a dataset consumer needs beside `t1_c`..`t4_c`.

    A capture column named `t2_c` says nothing about whether that probe is in
    chamber air, and `ml/data-dictionary-v0.md:101` currently defines it only as
    "Probe role T2". This is the machine-checkable supplement: every slot carries
    its ROM, its frozen physical position, whether it may enter a chamber-air
    aggregate, and why not if it may not. It is provenance for a consumer to gate
    on - it is not a re-reading of any committed capture, and it does not relabel
    historical evidence.
    """
    slots: dict[str, object] = {}
    for slot in ALL_SLOTS:
        rom = SLOT_TO_ROM[slot]
        position = ROM_POSITION_BY_ROM[rom]
        in_air = position in CHAMBER_AIR_POSITIONS
        slots[slot] = {
            "rom": rom,
            "physical_position": position,
            "serial_role": SLOT_TO_SERIAL_ROLE[slot],
            "in_chamber_air_aggregate": in_air,
            "exclusion_reason": "" if in_air else EXCLUDED_FROM_CHAMBER_AIR[f"{slot}_c"],
            "position_provenance": FROZEN_GEOMETRY_CLASS,
            "independently_verified_no_movement": False,
        }
    return {
        "schema": "coldguard.probe-roles/v0",
        "authority": [
            "evidence/A/W07/geometry-v1.md:113-121 (proposed role-explicit names)",
            "evidence/A/W07/probe-identification-v0.md:69 (operator-accepted as-built)",
            "firmware/main/coldguard_config.h:232-239 (ROM bytes, by source only)",
        ],
        "superseded_plan": superseded_plan_disclosure(),
        "serial_vocabulary": {
            "note": (
                "cg_serial keys its role stats T1/T2/T3 plus SPARE; the fourth probe "
                "is never keyed T4 there, so an air-only spread must be asked for in "
                "the serial vocabulary or it raises KeyError instead of computing"),
            "slot_to_serial_role": dict(SLOT_TO_SERIAL_ROLE),
            "chamber_air_serial_roles": list(CHAMBER_AIR_SERIAL_ROLES),
            "hot_side_serial_role": HOT_SIDE_SERIAL_ROLE,
            "chamber_air_role_names": list(CHAMBER_AIR_ROLE_NAMES),
        },
        "hot_side_rom": HOT_SIDE_ROM,
        "chamber_air_roms": sorted(CHAMBER_AIR_ROMS),
        "chamber_air_slots": list(CHAMBER_AIR_SLOTS),
        "chamber_air_columns": list(CHAMBER_AIR_COLUMNS),
        "slots": slots,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("capture", nargs="?", type=pathlib.Path,
                        help="a capture CSV with t<n>_role columns, to cross-check "
                             "the device's own role tokens against the frozen map")
    parser.add_argument("--json", dest="json_out", type=pathlib.Path)
    args = parser.parse_args(argv)

    payload = probe_identity_export()
    if args.capture is not None:
        with args.capture.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        payload["capture"] = args.capture.as_posix()
        payload["capture_rows"] = len(rows)
        payload["device_role_check"] = check_capture_against_frozen_map(rows)

    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_bytes(text.encode("utf-8"))
        print(f"json={args.json_out}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
