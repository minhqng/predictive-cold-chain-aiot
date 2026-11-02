# A-W07 acceptance

Slice: W07 geometry freeze + physical repeatability study · Branch
`feat/a-w07-plant-repeatability` · Stacked on PR #17 (`feat/a-w06-command-ack`)
Owner: Member A · Status: **GEOMETRY FROZEN FOR SENSORS · ANALYSIS COMPLETE ·
PHYSICAL STUDY NOT STARTED · CONFIGURATION PHOTOGRAPH STILL MISSING**

docs/05A §16 asks for **≥3 valid pilot runs of each of two kinds** on a frozen
geometry. The repository holds **one** cooling run plus one passive and one
recovery segment from the same boot of the same session. Everything deliverable
without a bench session is delivered; the runs are named as owed, not simulated.

## 1. Requirement matrix (docs/05A §16)

| ID | Canonical ask | Status | Evidence |
|---|---|---|---|
| **A-W07-01** | Freeze sensor mounts, V1 position, cable paths, door alignment, internal state; create a configuration photo/drawing | **PARTIAL — sensor positions FROZEN by operator-confirmed identification; V1 / cables / door alignment / load / conductor evidence / photo NOT FROZEN** | `geometry-v1.md` §1-§3 with `probe-identification-v0.md` and its 6 raw captures (233 frames, every one `state=OFF`, applied duty 0); §5 lists the four items that close it |
| **A-W07-02** | ≥3 valid passive warm-up runs; Tmean trajectory, gradient, slope | **NOT MET (0 independent runs)** — REAL_DATA_ANALYZED for the one segment that exists | `warmup-runs.jsonl`: 226 samples over 3.75 min, +0.0833 °C, whole-phase +0.027185 °C/min on the as-built air mean. Shares `boot_id` with the cooling run, so it is a segment, not a repetition |
| **A-W07-03** | ≥3 valid cooling-step runs; current/power, command→electrical delay, thermal response, recovery | **NOT MET (1 run)** — REAL_DATA_ANALYZED | `cooling-step-runs.jsonl` + `recovery-runs.jsonl`: 600 driven samples over 9.98 min, **-8.7083 °C** air mean, whole-phase -0.854771 °C/min, 1 °C at 0.85 min, mean 7.2247 A / peak 9.99 A / 85.16 W / 14.0 Wh; recovery 131 samples +5.333 °C. Command→electrical delay is not derivable from this CSV (no command event column) and is left to W13, which has H6/H7 console traces |
| **A-W07-04** | Per outcome: mean, SD, CV where meaningful, min/max, trajectory overlays | **DELIVERED — HOST_VERIFIED, verdict NOT ESTABLISHED** | `repeatability-report.md`, three `repeatability-*.json`, `repeatability-overlay.csv` (both time bases, every analysed definition); sample (n-1) spread stated, CV withheld at a zero mean, `NO_SAMPLES` outcomes listed rather than dropped |
| **A-W07-05** | State-based reset criterion candidate: Tmean band, gradient bound, door CLOSED, known cooling state, valid sensors | **DELIVERED (candidate, not frozen)** — HOST_VERIFIED | `reset-criterion-v0.yaml` + `cg_reset_criterion.py`: three gates FROZEN from canonical state semantics, two numeric gates `UNRESOLVED`, representation enforced and hot-side means refused; 24 tests |
| Pass criterion | Plant variation small enough to distinguish a deliberate S2 disturbance from random setup drift | **CANNOT BE JUDGED** | Needs the runs above plus the W10 S2 pilots. `plant_variation_reportable: false` |

## 2. What the frozen geometry changed

The 2026-11-02 identification is accepted by the operator as the official as-built
record, so the chamber-air set is known: T1 centre, T3 bottom, T4/SPARE near the
door, and **T2 on the hot side - which is not air at all**. Consequence in the one
committed cooling run:

| definition | delta | whole-phase slope |
|---|---|---|
| `tmean_airroles_v0` = mean(T1,T3,T4) — as-built air | **-8.7083 °C** | -0.854771 °C/min |
| `tmean_chamber3_v0` = mean(T1,T2,T3) — docs/01 §20.1 literal | -2.5627 °C | -0.34487 °C/min |

A factor of **3.40**, from naming alone. W07 therefore publishes both, labels every
artifact with `representation`, `representation_roles` and `includes_hot_side`, and
the reset criterion refuses a hot-side-contaminated mean rather than judging it.
The physical geometry is closed; the `docs/01` logical T1/T2/T3 naming is not, and
`geometry-v1.md` §4 states the discrepancy, the minimum coherent transition, and
who may authorize it.

## 3. Defects found and fixed while building W07

1. **A value column read as its own status column.** `_status_key("device_ms")`
   returned `device_ms`, so every elapsed time failed the status test, the slope
   inputs went empty, and a degenerate x-axis produced `None` instead of crashing.
   Fixed by keying the lookup on a distinct `<base>_status` column and pinned by
   `test_a_column_is_never_its_own_status`.
2. **Recovery reused the cooling outcome.** `minutes_to_1c` on a recovery segment
   measures a rise; publishing it under the cooling name would have sold a rebound
   as a cooling response. Now direction-aware `_time_to_move` with `minutes_to_1c`
   and `minutes_to_2c` per phase.
3. **Found by the independent review, then fixed here.** Fully-dead rows were
   dropped without being counted, an **empty** status cell was treated as `OK`,
   partial means shared the canonical label inside a phase series, rows with no
   usable applied duty were silently filed as passive, the trailing-window slope
   was published as if it summarized the phase (it reports **+0.0701** during a
   cooling phase that whole-phase measures -0.854771, because the curve rebounds
   inside the driven block), the statistics table dropped `NO_SAMPLES` outcomes and
   carried no slope definition, `warmup-runs.jsonl` held a recovery segment, the
   criterion file's "218 s" figure was not reproducible, and `reparameter()` would
   have let a duplicated YAML block re-activate an `UNRESOLVED` gate. Each is now
   counted, labelled or refused, with a test: `rows_read`/`skipped_rows`/
   `partial_term_rows`/`undetermined_rows`, `current_rows_unqualified` with
   `electrical_status_recorded: false`, two time bases in the overlay, per-file
   phase registries checked by the validator, and duplicate-block rejection.
4. **A wrong assertion of mine, not of the tool.** My first pairing test assumed a
   later acknowledgement owns fewer frames; attribution is "every frame at or after
   the ACK", so the test was corrected to state the real rule.
5. **One suspect electrical frame, now named instead of averaged.**
   `device_ms=826894`, `state=COOLDOWN`, requested and applied duty `0`,
   `current_a=7.15`, and `current_status` an **empty cell, not `OK`** - with
   electrical and thermal fields byte-identical to the two preceding driven frames.
   That is the recovery segment's "peak current", which is why the report says so
   inline instead of publishing the number bare. Consistent with documented PZEM
   register holdover; recorded for confirmation in the next supervised session, not
   interpreted as current with the bridge off.
6. **A published number I had to correct.** Mid-session I wrote that TEC stayed off
   on "134 frames"; measured against the logs the totals are 233 frames overall and
   119 in the three touch windows. The claim holds - all 233 report `state=OFF` and
   applied duty 0 - but the count was wrong and is restated in
   `probe-identification-v0.md`.

## 4. Data quality: what the one capture cannot support

`current_status` and `voltage_status` are empty in **all 957 rows**, and there is no
`power_status` or `door_status` column, so every electrical figure in this dossier
is a value with no recorded validity. The artifacts say so per row
(`electrical_status_recorded: false`) rather than implying status-checked data, and
`door_open` is `0` throughout with `door_polarity=UNCONFIRMED` - there is **no real
door-open event anywhere in committed data**, which is why S2 (W10) has tooling and
no pilot.

## 5. Physical actions still owed (consolidated)

1. Three passive warm-up runs, ≥15 min each at 1 Hz, TEC off, door closed.
2. Three cooling-step runs at the same duty and duration, under the standing
   supervised-session gates.
3. The four `geometry-v1.md` §5 items (probe-tip photos with a ruler, V1 and door
   at rest, cable/load note, conductor marking and termination photo).
4. A project decision on the `docs/01` §20.1 naming (physical geometry is final).
5. Confirmation of the `device_ms=826894` frame if it recurs, ideally with a PZEM
   reference measurement alongside the firmware read.

Nothing above is requested as automatic, and none of it was performed here: no
flash, no energized stage, no probe moved beyond hand-holding during the accepted
identification session.

## 6. Not owned by this slice

| Item | Owner / status |
|---|---|
| Baseline EDA, run-to-run variation, confounding checklist (B-W07-01..04) | Member B, on these exports |
| `experiments` table, run lifecycle, telemetry→run association (C-W07-01..05) | Member C |
| Threshold source and hysteresis (D-W07-01/02) | Member D; this criterion is an input, not a decision |
| Any change to `docs/01`, or a firmware ROM-to-role remap | project-level; not done here |
| S1 collection proper (W09) | blocked behind the runs above, not behind tooling |
