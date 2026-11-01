# G2-A — Physical placement plan and cold/hot-side gap

Status: **PROPOSAL ONLY — no probe was installed, moved or labelled in this task.**
All four probes keep `physical_label: PENDING` and `physical_position_verified: false`
in `evidence/A/W02/sensor-rom-map.yaml`.

## 1. Role semantics (contract)

`docs/01 §6.4` fixes the position semantics, `§6.5` fixes identity by ROM:

| Role | ROM | Position semantics | Measurement intent |
|---|---|---|---|
| T1 | `287088CA00000051` | near-door region | chamber air, door-end |
| T2 | `28AEBF2200000006` | central region | chamber air, geometric centre; source of `t_inside_c` |
| T3 | `28CBE9CA00000072` | far/opposite region | chamber air, opposite end |
| SPARE | `283BE5C9000000A9` | unassigned | no measurement role (PHY-DS-002) |

`cg_telemetry.c` derives `t_inside_c` from T2 with `t_inside_src=T2`; T1/T2/T3 must stay
three distinct ROMs (PHY-DS-001).

## 2. Placement plan (for the operator to execute and photograph)

| Probe | Target position | Mechanical rule | Why |
|---|---|---|---|
| T1 | door-end interior, mid-height | not touching the door gasket, TEC faces or box walls; free air ≥20 mm from surfaces | captures the region disturbed by door openings |
| T2 | geometric centre of the chamber | not touching product, TEC or walls; ~mid-height | `t_inside_c` must represent bulk air, not a surface |
| T3 | opposite end from the door | not touching the cold plate or return-air path | far/opposite reference for stratification |
| SPARE | leave unassigned (or hot-side candidate, section 4) | must remain explicitly SPARE until a documented remap | PHY-DS-002 forbids implicit substitution |

Prerequisites before the plan can be called "installed":

- probe cables strain-relieved so air movement cannot move them (PHY-DS-003: moving a
  probe is a configuration change);
- photograph of each probe, its label and its position in one frame, with the label
  text readable;
- date, operator and box configuration recorded next to the photos;
- then update `sensor-rom-map.yaml` `physical_label` / `physical_position_verified`
  and the placement section of the W04 evidence dossier in a separately reviewed change.

## 3. Current placement status

| Item | Status | Evidence |
|---|---|---|
| Probe identity (ROM ↔ role) | T1/T2/T3 stimulus-verified; SPARE present, unconfirmed by stimulus | `20-probe-identification.md` |
| Physical labels | NOT APPLIED | ROM map `physical_label: PENDING`; no label photos |
| Mounting positions | NOT VERIFIED | no photos, no coordinates, no operator statement |
| Mechanical H0 (box/probe fixture) | DEFERRED (A-W02-01) | W02 acceptance |
| Presence of all four probes | VERIFIED this session (all `raw_*_status=OK`) | captures 10/11 |

No claim of installation or labelling is made here.

## 4. Hot-side / cold-side monitoring gap

Firmware exposes `t_cold_side_c` and `t_hot_side_c`; both are `nan` with
`NOT_ASSIGNED` because no probe has a documented cold-side or hot-side role
(`cg_commission.c build_inputs()` sets both valid flags false; `docs/06 §3.3`).

- **Cold side:** no probe assigned. T1/T2/T3 are chamber-air probes, not cold-plate
  contact probes. A contact probe (or a documented reuse of one role) is required
  before `t_cold_side` can be anything but `NOT_ASSIGNED`.
- **Hot side:** no probe assigned. `PHY-TEC-001` requires a valid hot-side channel
  before START; without it the controller refuses to start — correct behaviour.
- **SPARE as hot-side candidate:** technically the natural candidate (one spare DS18B20,
  same bus, already in the frozen table as an explicit non-role). But adopting it is:
  1. a documented ROM→new-role configuration change (not a parser change);
  2. a mechanical change (contact with the hot block, thermal paste, heatsink-side
     placement, not air);
  3. a telemetry-contract change (`t_hot_side_c` source, `t_hot_side_status`), with
     tests and review;
  4. subject to `docs/06 §9` (output-stage opening conditions).
  None of this was done. It is a **proposal**, not an approved remapping.
- **Consequence:** two independent contact measurements (cold side and hot side) are
  still required. One spare probe can cover at most one of them; the other needs a
  hardware addition or a documented role decision.

## 5. What G2 (docs/06) still requires

`docs/06 §G2` asks for: fan powered at its rating on an independent supply, airflow
verified, hot-side probe contact + thermal paste, gentle external warming of the hot
block with a 5-minute stability record, and a documented role mapping.

G2-A delivered only the probe-identity half (and not for SPARE). The fan test, contact
test and role mapping remain open; TEC power is still not authorized.
