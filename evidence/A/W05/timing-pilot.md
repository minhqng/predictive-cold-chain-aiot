# A-W05-03 — Telemetry cadence pilot (measured)

Executed: 2026-11-02 · Tool: `firmware/tools/cg_timing_analysis.py`
Source: `evidence/A/W04/g1/40-g1-boot-60s.log` — 62 real `#CG TELEM` frames,
schema 1, firmware `cg-w04-0.1.0`, committed and hash-pinned in
`evidence/A/W04/SHA256SUMS.txt`
Artifacts: `timing-pilot.json`, `timing-pilot-jitter.csv`
Reproduce: `py evidence/A/W05/build_timing_pilot.py --check`

**This is a pilot, not the W05 study.** It measures how the delivered
telemetry loop actually paced itself on real hardware during a W04 bench
session. The 30-minute capture on the W05 image is a separate, unauthorized
physical action — see §5.

## 1. Result

| Quantity | Value |
|---|---|
| Accepted frames | 62 |
| Rejected telemetry lines | 0 |
| Ignored non-telemetry lines | 896 |
| Device uptime span | 229 ms → 61 307 ms (61 078 ms) |
| Frame gaps measured | 61 |
| Gap min / max | 980 ms / 1080 ms |
| Gap mean | 1001.279 ms |
| Gap median | 980 ms |
| Gap p95 / p99 | 1080 ms / 1080 ms |
| Gap population stdev | 40.889 ms |
| Rate | 0.9987 Hz (61 intervals / 61.078 s) |
| Late (>1150 ms) / early (<850 ms) | 0 / 0 |
| Non-positive gaps | 0 |
| Duplicate device timestamps | 0 |

Gap histogram — the stream is **bimodal, not noisy**:

| Gap (ms) | Count | Share |
|---|---|---|
| 980 | 48 | 78.7 % |
| 1080 | 12 | 19.7 % |
| 1078 | 1 | 1.6 % |

## 2. What the two spacing values mean

`CG_TELEMETRY_PERIOD_MS` is 1000 ms, but the emission check
(`esp_timer_get_time() >= next_telem_us`) only runs once per commissioning-task
iteration, and that loop sleeps `CG_TEC_TICK_MS` = 100 ms. A deadline that is
missed by one tick is met at the next one, so the observed spacing lands on a
multiple of the tick rather than on the target: 980 ms and 1080 ms are 1000 ms
−20 ms and +80 ms. The mean lands at 1001.3 ms because the loop periodically
re-catches the deadline.

Consequences a downstream consumer should design against, in order of how much
they matter:

1. **`uptime_ms` deltas are quantized to ~100 ms, not to ~1 ms.** Anything that
   estimates a derivative over consecutive telemetry frames is working with a
   ±40 ms effective time grid. Over the whole window the stream used exactly
   three spacings — 980 ms (48), 1080 ms (12) and a single 1078 ms interval,
   which was the very first one (uptime 229 ms → 1307 ms, i.e. the frame emitted
   during boot before the deadline loop had settled).
2. **A frame is not lost when the gap is 1080 ms.** Over 61 intervals there were
   zero non-positive gaps and zero duplicate timestamps.
3. **The W05 `seq` field is what distinguishes "paced late" from "dropped".**
   This capture cannot demonstrate that, because schema 1 had no sequence — the
   analyzer reports `seq_frames=0` and the duplicate/missing checks as absent
   rather than as passing.

The mechanism above is inferred from the delivered source and the observed
histogram; it is **not** measured with an oscilloscope or a GPIO toggle. Confirm
it on the W05 capture, where `seq`, `thermal_seq` and `power_seq` will show
whether a wide gap ever coincides with a skipped producer observation.

## 3. Producer and read-failure tallies over the pilot

Counted by `cg_timing_analysis.py` across all 62 frames:

| Field | Tally |
|---|---|
| `t_inside_status` | OK 61, NO_DATA 1 |
| `voltage_status` | INVALID 61, NO_DATA 1 |
| `current_status` | INVALID 61, NO_DATA 1 |
| `power_status` | INVALID 61, NO_DATA 1 |
| `door_status` | UNVERIFIED 62 |

Read against the schema rules, this says three specific things:

1. **The thermal producer worked.** One frame was emitted before the first
   1-Wire observation landed (`NO_DATA`), and the other 61 carried a valid
   chamber value. So the ~1 Hz cadence in §1 was measured while the sensor task
   was genuinely publishing, not while it was silent.
2. **Every electrical observation in this window failed to decode.** In this
   stream `INVALID` means "the poll happened, in the freshness window, and did
   not produce a valid reading" — not "the sensor is absent". The capture is a
   boot/idle session with the TEC branch power off, and these bytes alone do not
   distinguish an unpowered PZEM from a wiring or addressing problem. The reason
   is not established here; it is the first thing the W05 capture has to
   characterize, because `electrical_quality=INVALID` on every frame would make
   A-W15 (electrical observability) useless.
3. **The door semantic state was never knowable.** `UNVERIFIED` on all 62 frames
   is the expected output while `CG_DOOR_POLARITY_CONFIRMED` is 0; in schema 2
   this becomes `door_quality=UNKNOWN` rather than a bare status token.

`thermal_seq` / `power_seq` / the quality vocabulary: **absent** — schema 1 never
carried them, and the analyzer reports them as absent rather than as zero.

## 4. What this pilot does and does not establish

Establishes:

* the delivered 1 Hz loop does not drift, duplicate or emit a fake sample on
  real hardware over ~61 s;
* the timing tool computes correct statistics from a real capture, including the
  saturating-age and absent-field rules;
* the serial link carried the **W04 schema-1 frames, measured at 1007–1012
  bytes each**, together with the boot noise in the same window, without a single
  rejected line.

Does **not** establish:

* that the **W05** frame size (1844 bytes typical, 2098 bytes constructed worst
  case) survives a full 1 Hz stream over time — no schema-2 frame has ever been
  put on the wire, because the W05 image has never been flashed. The bandwidth
  figure in `quality-test.md` §3 is arithmetic on the buffer budget, not a
  measured throughput;
* cadence during TEC energization, where the PZEM poll, 1-Wire conversion wait
  and console traffic overlap;
* cadence over 30 minutes, or behaviour across a task-watchdog event, a reset,
  or a producer that actually stops;
* any W05-specific field's real values, because no W05 image has run.

## 5. What remains for A-W05-03 (NEED_USER_ACTION)

A ≥30-minute capture on the W05 image, which requires, in order:

1. Operator authorization to flash. The device currently runs the H8 bench image
   (`01cedce3…`, last flash 2026-10-31). The W05 build has never run on this
   hardware. Full flash preserved, backup integrity verified, target hashes
   verified, restoration procedure established, TEC branch isolated — all before
   any write.
2. A capture with the branch **power isolated** (no energization) to get the
   idle cadence, then — only if separately authorized and supervised — one with
   the PZEM seeing real current.
3. A second console on UART0 (GPIO43/44). The native USB-Serial-JTAG port drops
   when board power is removed, so a cold-boot banner cannot be captured through
   it; this is the same limitation recorded for W04's five POWERON boots.

Deliverables on completion: `30min-telemetry.csv`, `timing-jitter.csv` (real,
from `--jitter-csv`), and an updated `timing-pilot.md` section. They are **not**
in this directory, and nothing here substitutes for them.
