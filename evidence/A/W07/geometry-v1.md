# geometry-v1 — chamber configuration freeze record (A-W07-01)

Week: **W07** · Branch `feat/a-w07-plant-repeatability` · Owner: Member A
Status: **PARTIALLY FROZEN — electrical identity frozen from evidence, physical
placement NOT FROZEN (no configuration photo exists in this repository)**

This record freezes what can be frozen from artifacts already committed, and names
what cannot be. It is not a photo or a drawing, and it must not be read as one:
docs/05A A-W07-01 asks for a "configuration photo/drawing", and that is operator
supplied. Marking A-W07-01 complete on the strength of this file would be a false
acceptance.

## 1. Frozen by evidence (verifiable in this repository)

| Item | Frozen value | Source |
|---|---|---|
| 1-Wire sensor bus pin | GPIO **33** (`CG_ONEWIRE_PIN`) | `firmware/main/coldguard_config.h:72,221` |
| Pin map version | **2** | `coldguard_config.h:48` |
| Probe identities | four distinct DS18B20 ROMs, roles `T1`, `T2`, `T3`, `SPARE` | `firmware/main/cg_rom_map.c:15-24`, mirrored from `evidence/A/W02/sensor-rom-map.yaml` |
| RS-485 to the power meter | GPIO **36** (DI) / **37** (RO), 9600 8N1, bounded 250 ms read | `coldguard_config.h:78-79`, `evidence/A/W03/` |
| IBT-2 / BTS7960 control pins | RPWM **GPIO5**, R_EN **GPIO6**, L_EN **GPIO10** | `coldguard_config.h:80-82` |
| BME280 | SDA **21** / SCL **34**, **not implemented** in firmware | `coldguard_config.h:73-75`, docs/05A A-W02-06 |
| Door sensor (MC38) | GPIO **35**, polarity commissioned by touch only | `coldguard_config.h:77`, `evidence/A/W02/mc38/` |
| TEC conductor | **1.75 mm²** branch conductor, operator-stated | `evidence/A/W04/fuse-commissioning-note.md`, operator confirmation 2026-11-02 |
| Output stage posture | compiled out: `CG_TEC_OUTPUT_STAGE_ENABLED 0`, all six operating limits `UNRESOLVED` | `coldguard_config.h`, `firmware/main/cg_tec_limits.h:23-31` |
| Capture cadence | 1 Hz telemetry, one line per second | `evidence/A/W05/timing-pilot.md` |

## 2. NOT frozen — what the committed evidence cannot settle

1. **Physical probe placement.** No configuration photo or drawing exists in the
   repository. `evidence/A/W04/polarity-photo.md:82-85` lists the two photographs
   that were requested and never delivered, and states plainly that probes labelled
   "air" on an outside face would produce the same sign pattern as the ones inside.
   Until the photographs exist, the geometry of the measurement volume is asserted,
   not recorded.
2. **The T2 role conflict.** docs/01 freezes T1/T2/T3 as chamber-air probes, while
   the committed H8 capture labels T2 `HOT_SIDE` (`tec-cooling-response-600s.csv`,
   column `t2_role`, every row) and shows it rising while T1/T3/T4 fall during
   cooling. `repeatability-report.md` quantifies the consequence: the same single run
   reads **-2.5627 °C** on `mean(T1,T2,T3)` and **-8.6875 °C** on `mean(T1,T3)`. This
   is a project-level contract decision, not a Member A choice, and it is not resolved
   anywhere in W07.
3. **V1 position, cable paths, door alignment, internal load state.** No measured or
   photographed record. Each needs either a photograph with something in frame for
   scale, or a ruler measurement written down by the operator.
4. **Sensor mounting method** (taped, clipped, embedded) — unknown; the only physical
   description available is the probe type from `evidence/A/W01/bom-audit.csv`
   (waterproof DS18B20, 1 m lead).

## 3. What closes A-W07-01

Minimum set, all operator-supplied, no bench energisation needed for any of it:

- two photographs as already requested in `polarity-photo.md` (inside face: cold
  block, TEC face, wall, one probe tip; outside: hot block, fan, T2 tip on the hot
  block with the probe's ROM label legible);
- one photograph of each probe tip's position inside the chamber with a ruler in
  frame, labelled T1/T2/T3/SPARE;
- V1's position and the door gap at rest, in one photo;
- a written note of cable routing (which side, taped or loose) and of whatever load
  is inside the chamber during a run.

When those arrive, this file gains a `configuration-v1.yaml` section with the
measured positions and their photo references, and A-W07-01 becomes VERIFIED.
Nothing in W07's analysis changes if the geometry is later found different — the
tools read what a capture says — but the *interpretation* of every trajectory does,
which is why the gap is stated rather than papered over.
