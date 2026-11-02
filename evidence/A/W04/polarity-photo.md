# TEC polarity record — A-W04-06

Status: **direction recorded as operator-confirmed and supported by measured
data; the canonical "photo + frozen verdict" form is still open.** No
photograph of the TEC blocks exists anywhere in the repository, and the H6
touch-test verdict defined in `h6-tec-polarity-test-plan.md` was never
recorded — this file states what is actually known instead of inventing a
verdict.

## 1. As-built orientation (operator-confirmed 2026-11-02)

| Element | Position | Basis |
|---|---|---|
| TEC cold block | inside the foam box | operator statement |
| TEC hot block + fan | outside the box | operator statement |
| T1 `287088CA00000051` | inside-box air | operator statement |
| T2 `28AEBF2200000006` | on the hot-side metal | operator statement **and** the device's own `t2_role=HOT_SIDE` in every frame of the 2026-11-01 session |
| T3 `28CBE9CA00000072` | inside-box air | operator statement |
| SPARE `283BE5C9000000A9` | inside-box air | operator statement |
| BME280 | inside-box air | operator statement |

`evidence/A/W02/sensor-rom-map.yaml` still carries
`physical_position_verified: false` / `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`
for these ROMs. An operator statement is recorded here as such; it is not a
photograph and not a measurement of position.

## 2. What the firmware guarantees about direction

- The only enable call in the commissioning path is `set_enables(R_EN=1,
  L_EN=0)`; the adapter rejects any request with `L_EN=1` and re-forces
  `cg_actuator_force_off()` (`firmware/main/cg_tec_hw.c:28-41`).
- `firmware/main/cg_tec_platform.h` exposes no reverse function at all.
- `cg_check_firmware_w04.py` fails the build if that refusal is removed
  (`test_adapter_enable_refusal_removal_is_caught`).

So "no reverse operation" is enforced in code, independently of this record.
Which physical terminal is M+ is a wiring fact, and it is what section 3 evidences.

## 3. Measured directional evidence (cross-week, labelled as such)

`tec-cooling-response-600s.csv` / `tec-cooling-response-600s.png`, derived from
the raw monitor stream of the 2026-11-01 assembled-box run (H8 bench image
`01cedce3…`, stage H8-C, **100 % duty**, 600 s, 957 frames). Peak branch
current 9.99 A, mean of loaded frames 7.24 A, bus 11.7–11.95 V.

| Channel | Device role field | Start | End | Direction |
|---|---|---|---|---|
| T1 `287088CA…` | `UNASSIGNED` | 30.125 °C | 20.875 °C | fell 9.25 K |
| T3 `28CBE9CA…` | `UNASSIGNED` | 29.750 °C | 21.625 °C | fell 8.13 K |
| SPARE `283BE5C9…` | `UNASSIGNED` | 30.188 °C | 21.438 °C | fell 8.75 K |
| BME280 air | — | 30.658 °C | 22.906 °C | fell 7.75 K |
| T2 `28AEBF22…` | `HOT_SIDE` | 29.875 °C | 39.562 °C (peak 39.938 °C) | rose 9.69 K (10.06 K to peak) |

Three inside probes and the BME280 lose temperature while the fourth probe gains
temperature, with 84–117 W measured on the branch (peak 117.4 W).

**Conditional on the placement recorded in section 1**, that gradient is
consistent with heat being pumped from the inside face to the outside face, and
no arrangement with that same placement would give the opposite signs. The
inference does not prove the placement: a reversed module with the four
"air" probes actually on the outside face would produce the same sign pattern.
No photograph in the repository fixes which face is which, and
`h6/41-h6-run-analysis.md:85-86` already states that the gradient does not by
itself prove polarity. After OFF the inside channels rise and the hot-side
channel falls, which is the passive rewarming expected of the same arrangement.

This is a **100 % duty later-week measurement on the H8 bench image**, not a conservative W04
actuation. It evidences direction and thermal response; it does not evidence a
safe operating envelope, and it does not make W04's H6 conservative trace
complete.

## 4. What the W04-class conservative run actually shows

`h6/40-h6-run.log` → `h6/40-h6-run-analysis.md`: one 10 % duty, 60 s run,
0.97 A peak / 0.96 A mean, automatic OFF at 60.000 s. Electrical only — the H6
bench image reads no DS18B20 and no BME280, so it contains no thermal channel
and no touch verdict (`h6/41-h6-run-analysis.md:86,91-92` record the verdict as
held).

## 5. Two photographs would close A-W04-06 canonically

1. **Inside the box:** the cold block and the TEC face mounted to it, with the
   chamber wall and one probe tip in frame.
2. **Outside the box:** the hot block, its fan, and the T2 probe tip sitting on
   the hot block, with the probe's ROM label legible in the same frame.

With those two files this record becomes photo-verified and `polarity-photo.md`
can state `A-W04-06 = VERIFIED`. Until then the honest status is
**NEED_USER_INPUT**, and the direction claim rests on the operator statement
plus the measured gradient above.
