# geometry-v1 — chamber configuration freeze record (A-W07-01)

Week: **W07** · Branch `feat/a-w07-plant-repeatability` · Owner: Member A
Status: **PARTIAL — sensor positions and electrical identity FROZEN; V1 position,
cable paths, door alignment, internal load, conductor/termination evidence and the
configuration photograph NOT FROZEN by this record**

docs/05A A-W07-01 freezes five things and asks for a configuration photo or
drawing. The operator has finalized the physical sensor installation and accepted
the 2026-11-02 touch identification as the official as-built location record, so
sensor position is settled. Everything else on the list still has no evidence in
this repository, and §3 names exactly what would close it. This file is not a photo
and must not be read as one.

## 1. Sensor positions — FROZEN by operator-confirmed identification

Source: `probe-identification-v0.md` and its six raw captures
(`probe-identification/`, 233 `#CG H8S` frames at 1 Hz, `state=OFF` and
`pwm_applied_permille=0` in every one).

| slot | ROM | physical position | how established |
|---|---|---|---|
| T1 | `287088CA00000051` | **chamber CENTER** | rose 29.750 → 31.938 °C while held; fell after release |
| T2 | `28AEBF2200000006` | **TEC HOT_SIDE** (stays on the hot-side metal) | never touched; ≤0.063 °C across all windows |
| T3 | `28CBE9CA00000072` | **chamber BOTTOM** | rose 29.500 → 31.875 °C while held; other channels fell |
| T4 / SPARE | `283BE5C9000000A9` | **NEAR the chamber DOOR** | rose 31.438 → 34.250 °C while held, unambiguously |

Provenance rule, stated honestly: **the temperature response establishes the
slot-to-position mapping. The ROM ids come from the firmware's frozen ROM map
(`coldguard_config.h:218-224`), not from an independent ROM readback in these
frames** - the installed H8 image emits no ROM on the wire. Wires were labelled by
the operator during the session; if a label and this table ever disagree, the wire
wins until re-tested.

## 2. Frozen from committed evidence (electrical and configuration identity)

| Item | Value | Source |
|---|---|---|
| 1-Wire sensor bus pin | GPIO **33** (`CG_ONEWIRE_PIN`) | `firmware/main/coldguard_config.h:72`, `:221` |
| Pin map version | **2** | `coldguard_config.h:48` |
| Probe identities | four DS18B20 ROMs, roles T1/T2/T3/SPARE | `cg_rom_map.c:15-24`, mirrored from `evidence/A/W02/sensor-rom-map.yaml` |
| RS-485 to the power meter | GPIO **36** (DI) / **37** (RO), 9600 8N1, bounded 250 ms read | `coldguard_config.h:78-79`, `evidence/A/W03/` |
| IBT-2 / BTS7960 control pins | RPWM **GPIO5**, R_EN **GPIO6**, L_EN **GPIO10** | `coldguard_config.h:80-82` |
| BME280 | SDA **21** / SCL **34**; **not implemented in firmware** | `coldguard_config.h:73-75`, `cg_telemetry.h:21-22` (`:501`), A-W02-06 still asks to verify the sensor itself |
| Door sensor (MC-38) | GPIO **35**, polarity commissioned by touch only | `coldguard_config.h:77`, `evidence/A/W02/mc38/` |
| Production output posture | `CG_TEC_OUTPUT_STAGE_ENABLED 0` (`:403`), gates unverified (`:404`), requested duty 0, actuator enable disallowed (`:381`); six operating limits all `UNRESOLVED` | `coldguard_config.h`, `cg_tec_limits.h:5-8` (the count `CG_LIMIT_COUNT` is the enum at `:23-31`) |
| Installed bench image | `build-t2-hot-side`, SHA-256 `01cedce3b794638f25ae4c7f1e2dfdcb4b00555fdc81a0bcf4d35ed4187f6c9f`, 258 544 B; local-only, outside the repository | `evidence/A/W04/ARTIFACT-MANIFEST.md` |
| Telemetry cadence | 1 Hz, one line per second | `evidence/A/W05/timing-pilot.md` (955 of 956 gaps exactly 1000 ms) |

## 3. NOT FROZEN — what this record cannot assert

1. **No configuration photo or drawing exists in the repository.** The two
   photographs requested in `evidence/A/W04/polarity-photo.md:82-85` were never
   supplied, and that file's own caveat (`:60-61`) is that probes labelled "air"
   on an outside face would produce the same sign pattern - the inference does not
   prove placement. §1 now supplies what that photo was meant to supply for the
   *slot-to-position* question, by response rather than by image; it does not
   replace the photo for mounting method or clearance.
2. **Mounting method, height, clearance and orientation** of T1, T3 and T4 - not
   recorded. Whether each tip hangs in air or touches a wall or rack is unknown.
3. **V1 position, cable routing, door alignment/gap at rest, internal load state**
   - not recorded at all.
4. **The branch conductor is not frozen evidence.** Its size, 1.75 mm², is an
   operator statement, and this record lists it as *settled information* —
   `evidence/A/W04/fuse-commissioning-note.md:36` records that no marking was
   photographed and no measurement was taken, and its table at `:53` says
   explicitly: "No conductor evidence at all (today) → **no freeze**". The canonical
   ask is `2 × 2.5 mm²` (`docs/05A` A-W04-02, `docs/01` PHY-SAFE-004),
   `evidence/A/W01/bom-audit.csv` still carries HW-19 as `UNVERIFIED`, and the
   deviation register stays open. Do not read this row as compliance.
5. **Fuse selection.** Reported at 15 A; suitability for the observed 9.35-9.99 A
   loads is unproven and stays a W08 question.

## 4. Canonical naming versus the as-built rig — a discrepancy to resolve, not hide

`docs/01` §20.1 (lines 2312-2318) defines Tmean as mean(T1,T2,T3), and the earlier
probe-role text (lines 517-530) freezes T1/T2/T3 as the chamber probes with a
degraded two-sensor mean labelled separately. The as-built rig is:

```text
canonical expectation        as-built reality
T1 = near door               T4/SPARE = near door
T2 = chamber centre          T1        = chamber centre
T3 = far/opposite region     T3        = chamber BOTTOM
                             T2        = TEC HOT_SIDE (not air at all)
```

Two consequences, measured on the single committed run:

- mean(T1,T2,T3) - the literal canonical expression - averages a hot-side surface
  into an air temperature and reports **-2.5627 °C**, while the as-built air mean
  mean(T1,T3,T4) reports **-8.7083 °C**: the same physical event, a factor of 3.40
  apart, decided entirely by the naming.
- T3's real position is **bottom**. It must not be described as "far/opposite"
  unless a measured geometry establishes that equivalence; it currently does not.

Proposed offline role-explicit names, used by every W07 artifact and available to
Members B/C/D:

```text
CHAMBER_NEAR_DOOR = physical T4 / SPARE   (ROM 283BE5C9000000A9)
CHAMBER_CENTER    = physical T1           (ROM 287088CA00000051)
CHAMBER_BOTTOM    = physical T3           (ROM 28CBE9CA00000072)
TEC_HOT_SIDE      = physical T2           (ROM 28AEBF2200000006)
```

The raw firmware slot names stay exactly as they are; nothing is renamed silently.

What Member A does **not** decide here: whether `docs/01` §20.1 is amended to name
the chamber set by role rather than by slot, or whether the firmware ROM-to-role
table is re-pointed. That is a project-level change to a canonical document with a
safety consequence (T2 currently carries the only hot-side observation, and the
55 °C provisional limit depends on it). The minimum coherent transition, if the
project chooses it, is: keep `TEC_HOT_SIDE` on ROM `28AEBF2200000006` and its
protection role; assign chamber-air roles by ROM rather than by enumeration index;
publish a new `hardware_config_id` for the configuration so captures before and
after never pool; keep every historical capture's original labels intact; and
record the calibration state as it is - `calibration_id=UNRECORDED` - because no
calibration measurement exists to invent.

## 5. What closes A-W07-01

Minimum, all operator-supplied, none requiring the TEC to be energized:

1. one photograph of each probe tip with a ruler in frame, labelled by ROM;
2. one photograph of V1's position and of the door at rest, showing the gap;
3. a written note of cable routing (which side, taped or loose) and of any load
   inside the chamber during a run;
4. a photograph of the branch conductor marking and of the termination, which is
   also what §3.4 and W08's fuse question are waiting on.

With 1-3 this record becomes FROZEN for A-W07-01; with 4 the conductor and fuse
deviation register can move from "stated" to "evidenced". Until then A-W07-01 stays
**PARTIAL**, and no W07 statistic may be described as measured on a frozen
configuration.
