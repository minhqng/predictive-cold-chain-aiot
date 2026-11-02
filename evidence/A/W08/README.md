# A-W08 — Observed electrical envelope, hot-side sustainability and Gate A (Member A)

Week: **W08** · Branch: `feat/a-w08-electrical-envelope` · Stacked on
`feat/a-w06-command-ack` (head `4d31fe5`)
Owner: Member A · Language: host Python 3.14 (`py`)
Status: **OBSERVED ENVELOPE ANALYZED · GATE A NOT CLOSED · NO ENERGIZED TEST**
PHYSICAL MEASUREMENT TAKEN BY THIS DOSSIER: **NONE**

Gate A: **NOT CLOSED**. This dossier analyzes captures that supervised bench
sessions already recorded. It opens no port, energizes nothing, flashes nothing,
and certifies no physical limit. Every number is a statistic over bytes that
already exist on disk, and every frame the analysis refuses to average is listed
by name instead.

## 1. What W08 delivers (docs/05A section 17)

| Requirement | Delivered | Status label |
|---|---|---|
| **A-W08-01** safe operating envelope | `operating-envelope-v1.yaml` + `envelope-by-duty.csv` + `source-summary.csv`: allowed action state, healthy current/power ranges per measured duty level, the OFF current envelope, thermal response window, stop conditions, energy and V×I consistency — all labelled as observations, with a `do_not_extrapolate` block | REAL_DATA_ANALYZED (envelope **not frozen**) |
| **A-W08-02** fuse finalization | `fuse-selection.md`: the measured load against 10/15/20 A, with `observed` and `recommended` kept in separate blocks and a **NO_FREEZE** verdict | BLOCKED_HARDWARE + TEAM_DEPENDENCY |
| **A-W08-03** hot-side sustainability | `thermal-sustainability.csv`: TEC_HOT_SIDE per session with max, margin to the *provisional* 55 °C ceiling, and a final-minute drift/plateau test; `continuous_rating_claimed: false` in every row | REAL_DATA_ANALYZED (operator-observed bullets NEED_USER_ACTION) |
| **A-W08-04** SAFE_LOCAL integration support | `safe-local-physical-inputs.csv` (SL-01…SL-14): what firmware can observe, with the exact wire/schema field and its recorded validity, versus what only Member D's policy can decide | TEAM_DEPENDENCY |
| **A-W08-05** Gate A package | `Gate-A-report.md` + `gate-a-artifact-index.csv` (docs/01 gates H0…H7, resolved against this checkout) + `gate-a-operator-queue.csv` | IMPLEMENTED / HOST_VERIFIED |

## 2. Files

| File | What it is |
|---|---|
| `README.md` | this file |
| `acceptance.md` | per-requirement matrix A-W08-01…05, the pass-criteria walk, and the physical actions still owed |
| `operating-envelope-v1.yaml` | A-W08-01 deliverable: the observed envelope, latency rule, energy/power consistency, stop conditions, open inputs |
| `envelope-by-duty.csv` | one row per (duty level × session): median/P95/min/max current, voltage and power, with excluded-frame counts |
| `holdover-frames.csv` | every register-latency and suspect frame, individually: source, seq, `device_ms`, values, classification, note |
| `duty-zero-current-frames.csv` | every duty-0 frame that reports current above the steady floor, individually — including `seq=827 device_ms=826894` at 7.15 A |
| `electrical-status-coverage.csv` | which columns carried a validity token, per source and per column; `electrical_status_recorded=false` where they did not |
| `source-summary.csv` | one row per capture: drive/OFF envelope, energy and V×I verdicts, status flag, trust class |
| `thermal-sustainability.csv` | A-W08-03 rows (TEC_HOT_SIDE per session, margin, plateau test) |
| `fuse-selection.md` | A-W08-02 deliverable: observed versus recommended, and why the answer is NO_FREEZE |
| `safe-local-physical-inputs.csv` | A-W08-04 deliverable: input-by-input observability and ownership |
| `gate-a-artifact-index.csv` | A-W08-05: the H0…H7 artifact index resolved against this checkout |
| `gate-a-operator-queue.csv` | the W08 half of the consolidated operator queue |
| `Gate-A-report.md` | the assembled package |
| `local-bench-observations.json` | **declared input**: the statistics the same code computed from Member A's local H7/H8 captures, with each source file's SHA-256; not committed originals |
| `build_w08_artifacts.py` | regenerates every artifact above; `--check` compares, `--write-declaration` re-derives the declaration, `--verify-bench` proves the declaration still matches the bench tree |
| `validate_w08.py` | hash pins + re-asserts the honest verdicts + **re-derives** the committed-capture spine + fails if any physical claim appears |

## 3. Reproduce

```bash
py firmware/tools/cg_w08_envelope.py --no-local          # git-only analysis
py firmware/tools/cg_w08_envelope.py                    # + Member A's local bench tree
py firmware/tools/cg_w08_hot_side.py --json out.json    # hot side + fuse evaluation
py firmware/tools/cg_w08_gate_a.py --json out.json      # Gate A package
py firmware/tools/run_all_checks_w08.py                 # suite + statics + validators
py evidence/A/W08/build_w08_artifacts.py --check        # artifacts reproduce byte-for-byte
py evidence/A/W08/validate_w08.py                       # pins, verdicts, spine
```

## 4. The numbers, and where each one came from

Committed in this repository (a clean checkout reproduces every one of them):

| Figure | Value | Source |
|---|---|---|
| frames, driven frames | 957 / 600 at 999 ‰ | `evidence/A/W04/tec-cooling-response-600s.csv` |
| current median / p95 / max, 100 % duty | 7.16 / 7.64 / **9.99 A** | same CSV, 599 DRIVEN frames |
| mean current, excluding / including the pre-run holdover | 7.2367 / 7.2247 A | same CSV |
| branch voltage while driven | 11.76 – 11.81 V | same CSV |
| power median / mean / max | 84.4 / 85.3015 / 117.4 W | same CSV |
| steady OFF current maximum | **0.02 A** over 355 duty-0 frames | same CSV (one PZEM LSB = noise floor) |
| latency frames at duty 0 | 2 (7.15 A held register at `device_ms=826894`, 0.56 A settling) | same CSV, listed in `holdover-frames.csv` |
| energy counter vs power integral | 108 → 122 Wh (14 Wh) vs 14.219 Wh | same CSV |
| V×I vs reported power | worst delta **0.099 W**, tolerance 0.18 W, 0 frames beyond | same CSV, all 957 frames |
| TEC_HOT_SIDE max (driven) | **39.938 °C**, margin 15.062 K to the provisional 55 °C, +0.1759 K/min over the final minute | same CSV, `t2` |
| chamber center (T1) | 30.000 → 20.875 °C, spread 9.25 K | same CSV, `t1` |
| H6 10 % point | 59 frames, 0.96 A median, 11.2 W median | `evidence/A/W04/h6/first-tec-trace.csv` |
| OFF envelope with validity | 600 rows at 0.00 A, 11.94–11.95 V, `status=OK` | `evidence/A/W03/hardware-2026-10-27/raw/test-132b-off-envelope.csv` |
| missing-sample evidence | 594 `CRC_VALID` + **7 `INVALID`** (`physical_fail=1`) of 601 | `evidence/A/W03/hardware-2026-10-20/raw/pzem-off.csv` |
| production fail-closed posture | 62 rows, `output_stage=DISABLED`, duty 0, electrical cells empty, labels `INVALID`/`NO_DATA`, `fan_status=NOT_COMMANDABLE` | `evidence/A/W04/g1/42-telemetry.csv` |

Declared, from Member A's local bench tree (`local-bench-observations.json`,
`reproducible_from_git: false`, SHA-256 recorded per file):

| Figure | Value | Source file (local) |
|---|---|---|
| H8-A 180 s | 179 frames used, 7.2 A median, 7.3263 A mean, **9.35 A** peak, 86.3933 W mean, 110.0 W peak, T2 max 37.188 °C and still warming +1.4573 K/min | `h8/phase4e/h8a-enable-fixed-2026-10-31/monitor/samples.jsonl` |
| H8-B/C/D/E at 100 % duty | 419/599/899/1799 frames used, **T2 max 37.688 °C in all four**, final-minute drift −0.012…+0.002 K/min | `h8/phase4e/h8{b,c,d,e}-*/monitor/samples.jsonl` |
| H7 duty ladder medians | 1.78 / 2.45 / 3.05 / 3.62 / 4.14 A at 200–600 ‰ (degraded return path) and 5.89 / 6.51 / 7.08 / 7.58 A at 700–1000 ‰ (after replacement); 600 ‰ shunt-diag 5.38 A | `h7/40b…75-run-*pct*.log` |
| wire freshness | electrical samples stamped **636–666 ms** old, air 775 ms; `door_status=VALID` 940 frames; `off_verify=PASS` 126 / `PENDING` 5; `interlock_state=NOT_INSTALLED` 957; `fan_readback=NOT_ELECTRONICALLY_VERIFIED` 957; `enable_readback=ren:0,len:0` in all 957 while `ren_command=1` in the 600 driven ones | `h8/box-cooling-600s-2026-11-01/monitor-final/samples.jsonl` |

## 5. Limits of this dossier — read before quoting anything

* **The committed 600 s CSV carries no electrical validity at all.** Its
  `voltage_status` and `current_status` cells are empty in all 957 rows, and it
  has no `power_status`, `energy_status` or `door_status` column. Every V/I/P
  figure taken from it is therefore published as `electrical_status_recorded:
  false`, never as status-checked. The same session's raw wire line *does* carry
  `voltage_v_status=OK`, `current_a_status=OK`, `power_w_status=OK` plus ages —
  the loss happened in the CSV builder, which is why `electrical-status-coverage.csv`
  lists both views side by side.
* **`energy_wh` has no validity token anywhere on the bench wire** (no
  `energy_wh_status` in any of the 957 raw frames) and a 1 Wh quantum, so at
  ~85 W it cannot resolve anything shorter than ~42 s.
* **One duty level is committed.** The 20–100 % ladder is real but local-only
  and recorded in two different wiring regimes: 600 ‰ drew 4.33 A through the
  degraded return path and 5.41 A after its replacement. The two halves are
  never pooled.
* **No continuous rating exists.** The 55 °C hot-side ceiling was PROVISIONAL;
  `thermal-sustainability.csv` reports a *margin to a provisional number*, which
  is not headroom.
* **A fuse is not selected.** A-W08-02 returns NO_FREEZE: the branch is
  1.75 mm² (operator-confirmed, never re-derived here) against a canonical
  `2 × 2.5 mm²` ask with no recorded insulation class, run length or bundling,
  and the installed fuse's marking has never been photographed
  (`evidence/A/W04/fuse-commissioning-note.md`,
  `evidence/A/W01/bom-audit.csv` HW-19 `UNVERIFIED`). No compliance is claimed.
* **The bench images are not this branch's firmware.** The delivered build has
  the output stage compiled out (`coldguard_config.h`), requested duty 0,
  `CG_ACTUATOR_ENABLE_ALLOWED 0`, and all six operating limits `UNRESOLVED`
  (`cg_tec_limits.h`), so `cg_tec_start()` refuses. The bench image's
  `limits_policy=APPROVED` belongs to a bench build and is not quoted as a
  delivered value.
* **Sensor roles.** T1 = chamber CENTER, T2 = TEC HOT_SIDE, T3 = chamber BOTTOM,
  T4/SPARE = NEAR DOOR is the operator-frozen as-built record. The device role
  token says `HOT_SIDE` on T2 in the 2026-11-01 frames and `HOT_FINS` on T1 in
  the 2026-10-31 image; the ROM ids are by-source from the firmware ROM map, not
  a readback. TEC_HOT_SIDE is never averaged into a chamber-air statistic.
* **Checkout line endings.** `.gitattributes` currently has no `-text` rule for
  these directories, so with `core.autocrlf=true` a checkout rewrites CRLF and
  breaks every pin. The coordinator must add `evidence/A/W08/** -text` and
  `evidence/A/W15/** -text`; this slice may not edit `.gitattributes`.
