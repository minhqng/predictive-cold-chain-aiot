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
| **A-W07-01** | Freeze sensor mounts, V1 position, cable paths, door alignment, internal state; create a configuration photo/drawing | **PARTIAL — sensor positions FROZEN by operator-confirmed identification; sensor MOUNTING method/height/clearance, V1 / cables / door alignment / load / conductor evidence / photo NOT FROZEN** | `geometry-v1.md` §1-§3 with `probe-identification-v0.md` and its 6 raw captures (233 frames, every one `state=OFF`, applied duty 0); §5 lists the items that close it |
| **A-W07-02** | ≥3 valid passive warm-up runs; Tmean trajectory, gradient, slope | **NOT MET (0 independent runs)** — REAL_DATA_ANALYZED for the one segment that exists | `warmup-runs.jsonl`: 226 samples over 3.75 min, +0.0833 °C, whole-phase +0.027185 °C/min on the as-built air mean. Shares `boot_id` with the cooling run, so it is a segment, not a repetition |
| **A-W07-03** | ≥3 valid cooling-step runs; current/power, command→electrical delay, thermal response, recovery | **NOT MET (1 run)** — REAL_DATA_ANALYZED | `cooling-step-runs.jsonl` + `recovery-runs.jsonl`: 600 driven samples over 9.98 min, **-8.7083 °C** air mean, whole-phase -0.854771 °C/min, 1 °C at 0.85 min, mean 7.2247 A / peak 9.99 A / 85.16 W / 14.0 Wh; recovery 131 samples +5.333 °C. Command→electrical delay is not derivable from this CSV (no command event column) and is left to W13, which has H6/H7 console traces |
| **A-W07-04** | Per outcome: mean, SD, CV where meaningful, min/max, trajectory overlays | **DELIVERED — HOST_VERIFIED, verdict NOT ESTABLISHED** | `repeatability-report.md`, four `repeatability-*.json`, `repeatability-overlay.csv` (both time bases, all four analysed definitions); sample (n-1) spread stated, CV withheld at a zero mean, `NO_SAMPLES` outcomes listed rather than dropped |
| **A-W07-05** | State-based reset criterion candidate: Tmean band, gradient bound, door CLOSED, known cooling state, valid sensors | **DELIVERED (candidate, not frozen)** — HOST_VERIFIED | `reset-criterion-v0.yaml` + `cg_reset_criterion.py`: three gates FROZEN from canonical state semantics, two numeric gates `UNRESOLVED`, representation enforced and hot-side means refused; 37 criterion tests, and the analyzer carries 38 |
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
   was published as if it summarized the phase (it reports **-0.070104** during a
   cooling phase that whole-phase measures **-0.854771**, because the driven block
   runs out in the shallow bottom of the curve), the statistics table dropped
   `NO_SAMPLES` outcomes and
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
   `current_a=7.15`, `power_w=84.2`, and `current_status` an **empty cell, not `OK`** -
   with all 14 measured fields (voltage, current, power, energy, the four probe
   temperatures and their statuses) identical to both preceding driven frames, while
   its command fields moved from duty 999 to duty 0. That is the recovery segment's
   "peak current", which is why the report says so inline instead of publishing the
   number bare. The comparison is now computed over the full measured field set and the
   differing fields are published, so the claim can fail; `docs/01` §22.4 and §23.4 make
   a commanded-OFF-with-current frame a candidate `CONTROL_ELECTRICAL_ANOMALY`, which is
   a safety classification this host tool does not decide, and PZEM register holdover
   (recorded once before in `evidence/A/W04/README.md`) is the competing explanation.
   Recorded for the next supervised session.
6. **A published number I had to correct.** Mid-session I wrote that TEC stayed off
   on "134 frames"; measured against the logs the totals are 233 frames overall and
   119 in the three touch windows. The claim holds - all 233 report `state=OFF` and
   applied duty 0 - but the count was wrong and is restated in
   `probe-identification-v0.md`.

Independent review of the first delivery of this slice found more, and every finding
below was reproduced before it was fixed:

7. **The report's prose contradicted its own table.** It asserted "the trailing-window
   slope is positive during cooling on purpose" and `README.md`/`acceptance.md` quoted
   `+0.0701`, while the generated table in the same report printed `-0.070104`. The
   sentence was a hardcoded literal copied from the synthetic fixture that *does* force
   a rebound. It is now derived from the two published numbers, and the validator fails
   if the hand-written documents quote a slope the tools did not produce.
8. **Three state gates could be activated by a status the file format cannot write.**
   `door_required`, `sensor_quality_required` and `cooling_state_required_known`
   branched on `== "UNRESOLVED"`, so a hand-built dict with `status: TRUST_ME` reached
   READY on all three while the numeric gates were already guarded. They now use the
   same activation test.
9. **A frozen requirement could name no condition at all.** `door_required: OPEN`,
   `sensor_quality_required: DEGRADED` or `cooling_state_required_known: false` loaded,
   activated, and returned READY for a chamber that satisfies nothing. A value that is
   not the condition the criterion exists to test now answers UNKNOWN, and the validator
   pins the three shipped values.
10. **`tmean_band_c: inf` was accepted as a threshold.** Infinity is the absence of a
    bound, and it made READY reachable for any temperature. `_number()` now requires
    finiteness. The boundary is deliberately finiteness, not plausibility: deciding what
    counts as a sensible chamber bound is the measurement A-W07-05 refuses to guess, so
    `1e9` still evaluates and the shipped file's `UNRESOLVED` status is what keeps it out
    of delivery.
11. **The criterion's quality gate checked the wrong probes.** It read `t1/t2/t3`
    unconditionally while the shipped mean is `t1/t3/t4`, so a frame with
    `t4_status=INVALID` still answered `VALID` quality, and the gate vouched for `t2` -
    the probe the criterion refuses to average. It now derives its probe set from the
    representation it is judging.
12. **An unregistered representation crashed instead of refusing.** Naming
    `tmean_definition: tmean_bogus` raised `KeyError` out of the evaluator. Unknown
    representations are now contradicted like any other mismatch.
13. **Power and energy were silently fully qualified.** Neither column has a status
    field in this capture, and `reading()` treated a missing status column as `ok`, so
    `power_rows_unqualified` read 0 and `electrical_status_recorded` keyed off current
    alone. Absence is not verification: they now count as unqualified, which is why the
    driven block publishes `electrical_rows_unqualified: 2400` (four columns x 600 rows)
    rather than a reassuring zero.
14. **A row could be counted twice.** Inside the driven span, a row with no applied duty
    stayed in `cooling` *and* appeared in `undetermined`. The four phase lists now
    partition the capture, proved by a test that sums them against the row count.
15. **Two validator checks asserted today's defect rather than the durable property.**
    `current_rows_unqualified == rows_read` and "exactly one cooling run" meant the
    dossier failed the moment the physical study succeeded: giving the capture recorded
    statuses, or filing a second session, broke `run_all_checks_w07.py`. They are now
    conditional - the bookkeeping must stay consistent at any run count, and the
    insufficient-runs language is required only while that is still the truth. This is
    the PHASE SNAPSHOT class from the working contract, and it is labelled as such in
    the validator.
16. **Three checks could not fail.** The identification counts were matched as strings
    (`"233" in record`) while the README claimed the validator re-checked every frame -
    deleting three frames kept it green; it now recomputes totals, per-window counts,
    `state=OFF`, zero applied duty and the six `boot_id`s. The byte-identical claim on
    the suspect frame compared five fields and published "all electrical and thermal
    fields" - it now compares fourteen and publishes any difference. The overlay
    required `>= 3` representations while the docs claimed every analysed definition,
    so `tmean_all4_v0` was missing and undetectable; the overlay now carries all four
    and the validator requires the sets to be equal.
17. **Citations and figures that were wrong.** The T2 hands-off spread is 0.125 °C in
    `decay_check`, not `<= 0.063` as all three records claimed; `settle_1` and `touch_2`
    boot ids were mis-paired and a sixth boot id was missing; the ROM table is
    `coldguard_config.h:229-235`, not `:218-224`, and `firmware/h8-bench` does not exist;
    `cg_telemetry.h:501` is impossible in a 120-line file; the 1 Hz cadence was
    attributed to `evidence/A/W05/timing-pilot.md`, which measured 61 gaps at
    980/1080 ms and says spacing is *not* 1000 ms; the probe-role text is docs/01
    823-825, not 517-530; "observed 9.35-9.99 A" and "the 55 °C provisional limit" have
    no source in this repository; `door_open` is `0` in 940 rows and `UNKNOWN` in 17,
    not `0` throughout; A-W07-01's open list omitted sensor mounting; and the artifact
    count was "three", now four.

## 4. Data quality: what the one capture cannot support

`current_status` and `voltage_status` are empty in **all 957 rows**, and there is no
`power_status` or `door_status` column at all, so every electrical figure in this
dossier is a value with no recorded validity - `power_w` and `energy_wh` are counted
unqualified for the same reason as current and voltage, because a column that was never
checked did not become checked by going missing. The artifacts say so per phase
(`electrical_rows_unqualified`, `electrical_status_recorded: false`) rather than implying
status-checked data. `door_open` is `0` in 940 rows and `UNKNOWN` in the 17 boot rows, with
`door_polarity` `CONFIRMED` (940) / `UNCONFIRMED` (17) to match - there is **no real
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
