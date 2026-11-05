# Change review request CR-A-W04-01 — T2 measurement semantics

Raised by Member A on 2026-11-02. **No canonical document is changed by this
request, and no code changes behaviour.** It records a conflict between the
frozen measurement contract and the as-built bench, and asks the project to
decide.

## 1. The conflict

| Source | Says |
|---|---|
| `docs/01-physical-measurement-correctness-contract.md` §6 (PHY-DS-005) | T1/T2/T3 are **chamber-air region** measurements — near door, geometric centre, far side — and their tips must not touch the wall, cold plate or TEC |
| `evidence/A/W02/sensor-rom-map.yaml` | ROM `28AEBF2200000006` is assigned role T2 with `position_semantics: center`, `physical_position_verified: false`, `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` |
| H8 bench firmware, every frame of the 2026-11-01 session | that same ROM is emitted as `t2_role=HOT_SIDE`, and the H8 image refuses to run without a `HOT_SIDE` role |
| Operator statement, 2026-11-02 | the probe is physically attached to the TEC **hot-side** metal; T1, T3, SPARE and the BME280 are in inside-box air |
| Measured behaviour, 2026-11-01 (`tec-cooling-response-600s.csv`) | while T1/T3/SPARE fell 8–9 K, this channel rose from 29.875 °C to a 39.938 °C peak — the opposite sign to chamber air |

The channel cannot be both chamber-centre air and the hot-side block.

## 2. Why Member A cannot resolve it alone

`docs/01` opens with the rule that changing a sensor role or position identity
requires updating that document **before or together with** the implementation,
under project-level review. Redefining T2 also moves the canonical chamber-air
`Tmean`, which Member B's features and labels, Member C's normalized telemetry
and Member D's controller policy all consume.

## 3. Options for the project

| Option | What it means | Cost |
|---|---|---|
| **A. Amend the contract** | `docs/01` §6 redefines the ROM `28AEBF2200000006` channel as a hot-side protection input, and chamber air becomes T1 + T3 + SPARE (three channels, ≥ 3 satisfied). `Tmean` is redefined over the air channels only, and the hot-side value is excluded from it by definition | one-time contract edit; B/C/D must re-derive anything that assumed three air channels |
| **B. Move the probe** | keep T2 as centre air, physically relocate the probe, and find another means of hot-side protection | needs a new bench session and a new protection path; the hot-side risk is unprotected in the interval |
| **C. Status quo** | leave the contradiction in place | rejected: it makes every thermal claim ambiguous and lets a protective reading be mistaken for air |

Member A recommends **Option A**, because it matches the hardware that exists,
keeps hot-side protection active, and preserves the ≥ 3-air-channel requirement
through SPARE.

## 4. Protections that must survive any decision

- Hot-side overheating protection stays active whichever option is chosen; it is
  not negotiable and this request does not weaken it.
- The delivered W04 firmware keeps `t_hot_side_c=NOT_ASSIGNED` and does not act
  on T2 as air or as hot side, so nothing here is pre-empted by code.
- `docs/01` must be updated before or together with any firmware that consumes
  the new semantics.

## 5. Requested decision owners

Project-level review with the `docs/01` owner; Member D as reviewer of record for
Member A's physical/measurement work (`docs/04`); Member B for the `Tmean` and
feature consequences; Member C for the telemetry schema consequence.

## 6. Status

OPEN — raised as issue **#14** on 2026-11-02. Awaiting a decision. Until then A-W04-07's thermal channels and any
canonical `Tmean` claim stay unresolved, and this PR makes no thermal acceptance
claim.
