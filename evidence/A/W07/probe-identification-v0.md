# PROBE_IDENTIFICATION — DS18B20 slot to physical position (2026-11-02)

Status: **ACCEPTED BY THE OPERATOR as the official as-built sensor location record**
for the current physical setup. Raw captures are in `probe-identification/` - six
files, 233 `#CG H8S` frames in total, of which 119 fall in the three touch
windows. No further identification test is requested or authorized.

> Correction of my own earlier figure: mid-session I wrote that TEC stayed off on
> "134 frames". Measured against the logs the totals are 233 frames overall and 119
> in the touch windows. The claim itself holds - every frame in all six files reports
> `state=OFF` and `pwm_applied_permille=0` - but the count was wrong, so it is
> restated here rather than left to propagate into the operator's summary.

Session class: **PROBE_IDENTIFICATION**. Excluded from S1/S2/S4 training data:
every frame here was taken with a hand on a probe, which is exactly the
disturbance the datasets must not contain. Capture dir `_probe-id/` is outside the
repository; no firmware was flashed, no mapping was edited, no git delivery was
made during this session.

## Installed firmware and frame shape (verified this session)

- Port COM4 @ 115200, read-only capture (`capture_probe_id.py`, kept outside the
  repository with the scratch capture dir, writes nothing to the port). Opening the
  port resets the board, so `boot_id` changes per window and the six windows carry six
  distinct ids: live_check 25ff9325, baseline b45af2ff, touch_1 a1732532, settle_1
  f0fef08c, touch_2 e5fde982, decay_check 3c0b622a. Host UTC timestamps are the
  session time axis; `device_ms` is per-boot.
- Frames are `#CG H8S schema=3`, 1 Hz, carrying `t1..t4` with `t{n}_status`,
  `t{n}_role`, `t{n}_age_ms`, plus `state`, `pwm_*`, `fault`, `snapshot`.
- **The frames carry no ROM id.** Slot identity is therefore direct observation;
  the ROM labels below come from the frozen ROM table in the delivered firmware
  (`firmware/main/coldguard_config.h:229-235`, `CG_ROM_T1/T2/T3/SPARE_BYTES`) and are
  marked *by-source*, not verified by reading flash back.
- Candidate installed image hash (local build):
  `01cedce3b794638f25ae4c7f1e2dfdcb4b00555fdc81a0bcf4d35ed4187f6c9f`
  (`build-t2-hot-side/coldguard_h8_bench.bin`, 258,544 B). Not re-verified against
  flash in this session.

## Safety state during the session

`state=OFF` and `pwm_applied_permille=0` in every captured frame; TEC power branch
isolated by the operator. t2 (HOT_SIDE) was never touched; its largest within-window
spread is 0.125 °C (`decay_check`), 0.062 °C in the other five.

## Evidence

| window | boot_id | seconds | frames | held by operator | max spread t1..t4 | observed |
|---|---|---|---|---|---|---|
| `live_check` | 25ff9325 | 12 | 11 | none | 0.063 | all four probes OK, t1 29.654 / t2 29.972 / t3 29.375 / t4 29.694 |
| `baseline` | b45af2ff | 45 | 44 | none | 0.063 | t1 29.651 (spread 0.063), t2 29.958, t3 29.375 flat, t4 29.694 |
| `touch_1` | a1732532 | 62 | 61 | **near the door** | 2.812 | **t4 31.438 -> 34.250 (+2.81 in window, +3.63 vs baseline)**; t1 +0.04, t2 +0.00, t3 +0.03 |
| `settle_1` | f0fef08c | 30 | 29 | **middle of the chamber** | 2.250 | **t1 29.750 -> 31.938 (+2.19)** while t4 fell 32.062 -> 31.375 (release decay) |
| `touch_2` | e5fde982 | 30 | 29 | **bottom of the chamber** | 2.437 | **t3 29.500 -> 31.875 (+2.38)** while t1 fell -0.25 and t4 fell -0.13 |
| `decay_check` | 3c0b622a | 60 | 59 | none | 0.125 | all channels back to baseline: t1 29.690, t2 29.952, t3 29.506, t4 29.733 |

Each rise happened in a **different channel in a different window**, and each
released channel decayed in the next window. The largest hands-off spread is
**0.125 °C** - t2 in `decay_check` - while `live_check` and `baseline` hold every channel
within 0.063 °C, so 0.063 °C may not be quoted as the session noise floor. Against those
spreads the touch rises are 2.25-2.81 °C within window, and t2 never responded to a touch.
Every figure in this table, including which `boot_id` belongs to which window, is
recomputed from the six captures by `validate_w07.py`.

## Official mapping

| firmware slot | role as installed | ROM (by-source, unverified) | physical position (operator) | basis |
|---|---|---|---|---|
| t1 | UNASSIGNED | `287088CA00000051` | **middle of the chamber** | in-window rise in `settle_1` + operator statement |
| t2 | **HOT_SIDE** | `28AEBF2200000006` | TEC hot side, **not moved, not to be moved** | frozen config + never responded to hands |
| t3 | UNASSIGNED | `28CBE9CA00000072` | **bottom of the chamber** | in-window rise in `touch_2` + operator statement |
| t4 (SPARE) | UNASSIGNED | `283BE5C9000000A9` | **near the door** | in-window rise in `touch_1`, unambiguous |

Not established by this session, and deliberately not claimed:
- exact distance/height of each tip, orientation, and cable routing;
- whether the three chamber probes hang in air or touch a wall/rack (positions are
  confirmed by response, heights and clearances are not recorded);
- any change to the logical T1/T2/T3 roles. The physical geometry is final; the
  docs/01 logical naming discrepancy (canonical expects T1 near door / T2 centre /
  T3 far-opposite against as-built T4 near door / T1 centre / T3 bottom) is a separate
  interface question analysed in `geometry-v1.md` §4, and no silent firmware remap is
  proposed here;
- the ROM labels beyond the *by-source* qualification above.

## Handling

- Do not reuse these captures for S1/S2/S4 or for any thermal-response statistic.
- Wire labels applied by the operator during the session are the physical record;
  this table is the logical one. If they disagree, the wires win until re-tested.
