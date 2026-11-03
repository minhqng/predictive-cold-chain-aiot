# G2-A — Physical probe identification (thermal-stimulus test)

Session date: 2026-10-29. Board: ESP32-S3R2 (MAKDRIVERONE), MAC `e0:72:a1:bc:cf:4c`,
port COM4 (USB-Serial/JTAG VID_303A:1001). Firmware `cg-w04-0.1.0`, `CG-HW-001`,
patched TWDT build (app SHA-256 `39dd8332…`).

Raw captures (every device line prefixed with the host monotonic offset):

- `10-probe-warm-session.log` — boot_id `e1c19658`, boot_count 23, 480 TELEM frames / 480 s
- `11-probe-warm-session-2.log` — boot_id `42b5bb00`, boot_count 24, 241 TELEM frames / 241 s

## Method

1. Baseline: 10 consecutive `#CG TELEM` frames per session; all four probes
   `raw_*_status=OK`.
2. The operator picked one physically distinguishable probe per round, warmed ONLY
   that probe between fingers for 10–15 s (no hot air, flame, water, heater, TEC).
3. The probe was identified by which `raw_t*_c` channel rose; a rise was accepted
   only when it exceeded every other channel's change by a wide margin.
4. Probes were allowed to settle between rounds; the next round used a probe not
   previously warmed.
5. The canonical ROM→role map was NOT read from, written to, or modified by this test.
   Identification is by thermal response, not by enumeration order.

## Results

Baselines are medians of the first 10 frames; deltas are per-round maxima inside the
round window.

| Round | Probe warmed | Baseline of responding channel | Response | Other channels (same window) | Identification |
|---|---|---|---|---|---|
| 1 | operator-selected probe #1 | T2 29.875 °C | **T2 +2.750 °C** | T1 +0.06, T3 +0.125, SPARE +0.125 | **T2 = `28AEBF2200000006`** |
| 2 | operator-selected probe #2 (different) | T3 29.250 °C | **T3 +3.188 °C** | T1 +0.125, T2 +0.44 (decay from round 1), SPARE +0.125 | **T3 = `28CBE9CA00000072`** |
| 3 | operator-selected probe #3 (different) | T1 29.625 °C | **T1 +2.875 °C** | T2 0.00, T3 0.00, SPARE 0.00 | **T1 = `287088CA00000051`** |
| 4 | last remaining probe | — | round paused by operator | — | **SPARE = `283BE5C9000000A9`: present and reading, stimulus response NOT verified** |

Settle check:

- Session 1 end: T1 29.625, T2 30.000, T3 29.625, SPARE 29.688 °C.
- Session 2 end (after T1 round): T1 29.750, T2 30.000, T3 29.375, SPARE 29.688 °C.
  All channels returned to within ~0.1–0.2 °C of their baselines.

All four frozen ROMs were available and plausible throughout the session
(`raw_t1/t2/t3/spare_status=OK`, `sensor_validity=VALID`, values 29–32 °C).
The fourth ROM (SPARE) reads normally, but because round 4 was paused it was never
deliberately warmed. Its identity is therefore **exclusion-only** and is NOT claimed
as stimulus-verified.

## Transient read failures during handling

Two one-sample events, both while probes/cables were being handled:

- host +166.3 s: `role=T3 status=2` and `role=SPARE status=2` → `thermal_quality VALID→DEGRADED`,
  recovered at +167.3 s (`status=0`, back to VALID).
- host +353.3 s: `role=T2 status=2` → DEGRADED, recovered at +354.3 s.

`status=2` is `CG_READ_CRC_FAIL`; `present=1` throughout. The firmware reported the
failure as DEGRADED rather than fabricating a value and recovered on the next sample.
This is consistent with physical disturbance of the 1-Wire wiring, not with a probe
identity ambiguity. No sample was lost or invented.

## Safety invariants during the whole test (721 TELEM frames)

| Check | Result |
|---|---|
| `output_stage=DISABLED` | 721/721 |
| `pwm_duty=0` | 721/721 |
| `tec_state=OFF` | 721/721 |
| `fault_code=0x00000000` | 721/721 |
| WDT "task not found" / watchdog triggers / panic | 0 |
| Console commands sent (ARM/START/PWM) | 0 |

One reset occurred between the two captures: boot_count 23→24, boot_id changed, caused
by closing the first serial handle (DTR/RTS deassertion), not by firmware. The next
sample shows `tec_state=OFF`, `output_stage=DISABLED`, `fault_code=0` — PHY-ACT-001
re-verified incidentally.

## What this test does NOT establish

- Physical position of any probe (door/center/far/hot-side). The operator did not
  describe or label the individual probes; no placement evidence exists.
- That the probes are installed in the chamber. The test was on accessible probes.
- The SPARE probe's response to a stimulus (round 4 paused).
- Any change to the canonical map: `sensor-rom-map.yaml` and
  `coldguard_config.h` remain byte-identical and `physical_label: PENDING`.
