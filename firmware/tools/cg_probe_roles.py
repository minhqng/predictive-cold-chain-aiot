"""Single host-side source of truth for DS18B20 probe roles (A-W07 / W09 handoff).

Why this module exists
----------------------

The operator-frozen as-built record and the checked-in W02 firmware/host map state
different things about logical slot T2, and the host analysis layer previously
encoded the exclusion as a hand-written boolean per representation:

* `evidence/A/W02/sensor-rom-map.yaml:67-73` puts ROM `28AEBF2200000006` in role T2
  with `position_semantics: center`, `physical_label: PENDING`,
  `physical_position_verified: false`, and puts `283BE5C9000000A9` in SPARE
  (`:82-86`). `firmware/main/coldguard_config.h:232-239` mirrors that.
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


def is_hot_side_column(column: str) -> bool:
    return column == HOT_SIDE_COLUMN


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
        "superseded_plan": (
            "evidence/A/W02/sensor-rom-map.yaml:67-73 assigns the same ROM position_"
            "semantics `center` with physical_position_verified false; that is a "
            "superseded plan, not a live contradiction, and it is not promoted here"
        ),
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
