# A-W07 acceptance

Slice: W07 geometry freeze + physical repeatability study · Branch
`feat/a-w07-plant-repeatability` · Stacked on PR #17 (`feat/a-w06-command-ack`)
Owner: Member A · Status: **ANALYSIS COMPLETE — PHYSICAL STUDY NOT STARTED**

W07 is not a GREEN week and cannot be made one by tooling. docs/05A §16 asks for
**≥3 valid pilot runs of two kinds**, measured on a frozen geometry. This
repository contains **one** cooling run and **one** passive segment from the same
boot of the same session. Everything that could be delivered without a bench
session is delivered; everything that needs one is named.

## 1. Requirement matrix (docs/05A §16)

| ID | Canonical ask | Status | Evidence |
|---|---|---|---|
| **A-W07-01** | Freeze sensor mounts, V1 position, cable paths, door alignment, chamber internal state; create a configuration photo/drawing | **PARTIAL — electrical identity frozen, physical placement NOT FROZEN** | `geometry-v1.md`: pins, ROM roles, conductor and output posture are cited to committed files; the photographs requested in `evidence/A/W04/polarity-photo.md:82-85` were never delivered, and nothing in this repo records where a probe tip actually sits |
| **A-W07-02** | ≥3 valid passive warm-up runs under similar start conditions; measure Tmean trajectory, gradient, slope | **NOT MET (0 independent runs)** | One passive segment (226 samples, 3.75 min, +0.0623 °C, +0.020464 °C/min) exists inside the H8 capture and shares its `boot_id`, so it is registered as a segment and not as a run. Tooling, definitions and the statistics are delivered and executable |
| **A-W07-03** | ≥3 valid cooling-step runs; measure current/power, command→electrical delay, thermal response, recovery | **NOT MET (1 run)** | `cooling-step-runs.jsonl`: 600 samples over 9.98 min at 999‰, peak 9.99 A, mean 7.22 A, recovery segment 131 samples +0.875 °C. One run cannot produce a spread |
| **A-W07-04** | Per outcome: mean, SD, CV where meaningful, min/max, trajectory overlays | **DELIVERED as a tool with an honest non-verdict** | `repeatability-report.md` + `repeatability-{tmean_chamber3,tmean_t2excluded}.json` + `repeatability-overlay.csv`; sample (n-1) SD stated, CV undefined at a zero mean, n=1 leaves spread empty by construction instead of inventing it |
| **A-W07-05** | Define a state-based reset criterion candidate: Tmean band, gradient bound, door CLOSED, known cooling state, valid sensors | **DELIVERED (candidate, not frozen)** | `reset-criterion-v0.yaml` + `cg_reset_criterion.py`; three gates FROZEN from canonical state semantics, two numeric gates `UNRESOLVED`, 22 tests |
| Pass criterion | Plant variation must be small enough to distinguish a deliberate S2 disturbance from random setup drift | **CANNOT BE JUDGED** | Requires the runs above and the S2 pilots of W10. The report states `plant_variation_reportable: false`, and docs/05A's own instruction if repeatability is poor — "fix plant before ML collection" — is not yet applicable, because the plant has not been measured repeatedly at all |

## 2. Two findings that matter more than the missing runs

1. **The `Tmean` definition changes the measured cooling effect by 3.4×.** On the
   single committed run, `mean(T1,T2,T3)` gives **-2.5627 °C** while `mean(T1,T3)`
   gives **-8.6875 °C**, and the 1 °C mark arrives in 2.68 min versus 0.88 min. The
   capture labels `t2_role = HOT_SIDE` on every row, and T2 rises while T1/T3/T4
   fall, so including it in a chamber-air mean flattens the response the chamber
   actually produced. docs/01 freezes T1/T2/T3 as chamber-air probes; the operator
   has confirmed T2 sits on the hot side. **This is the open contract decision, and
   W07 cannot be closed while it is open**, because every repeatability number in
   the report is defined in terms of one answer or the other. Both are computed and
   labelled rather than one chosen silently, and the reset criterion refuses a state
   measured on a different representation than the one it names.
2. **One cooldown frame shows 7.15 A with duty 0.** `device_ms=826894`,
   `state=COOLDOWN`, `pwm_req_permille=0`, `pwm_applied_permille=0`,
   `current_a=7.15` with `current_status=OK`, T2 at 39.56 °C. It is a single sample,
   so it is recorded as an observation to confirm on the next session and not
   interpreted here. It matters because it is exactly the case the applied-state
   evidence rules were built for: a duty of zero and a branch that is still moving
   current. Until it is understood, `peak_current_a` for a recovery segment is not a
   safe summary, which is a second reason n=1 statistics are not published as
   results.

## 3. Defects found while building W07

1. **A value column was read as its own status column.** `_status_key("device_ms")`
   returned `device_ms` itself, so every elapsed time failed the "status must be OK"
   test and the slope inputs came out empty — a degenerate x-axis that produced
   `None`, not a crash. Found because the test for a single-timestamp slope fired on
   real data. Fixed by keying the status lookup on a distinct `<base>_status`
   column, and pinned by `test_a_column_is_never_its_own_status`.
2. **Frames were paired positionally with the wrong expectation.** My first
   repeatability test asserted that a command acknowledged later owns fewer frames,
   which is not how attribution works: every frame at or after an ACK's uptime is
   attributed to it. The assertion was wrong, the tool was right, and the test now
   states the real rule.
3. **A recovery phase reused the cooling outcome.** `minutes_to_1c` on a recovery
   segment measures a *rise*, so reusing the cooling name would have published a
   rebound as a cooling result. Split into a direction-aware `_time_to_move` with
   both thresholds published as separate outcomes.

## 4. What is owed to close W07 (operator, minimum set)

Nothing here needs the TEC energised except item 2, and item 2 is bounded:

1. **Geometry photographs** — the two already requested in `polarity-photo.md`, plus
   one photo per probe tip with a ruler in frame and one of V1/door at rest.
2. **Three passive warm-up runs** — chamber at rest, TEC off, door closed, one 1 Hz
   capture of ≥15 min each, started from similar ambient conditions.
3. **Three cooling-step runs** — the same duty and duration each time, with the
   existing supervised-session safety gates, and an explicit note of any change
   between runs.
4. **A decision on the T2 representation** (project-level, not bench work): which
   mean is `Tmean` for datasets and control, and what happens to the already
   collected H6/H7/H8 captures under that choice.
5. Confirmation of the 7.15 A cooldown frame, if it recurs.

With 1-4, `warmup-runs.jsonl` and `cooling-step-runs.jsonl` gain entries,
`repeatability-report.md` recomputes with n≥3, and the two `UNRESOLVED` gates in
`reset-criterion-v0.yaml` get values with a measurement behind them.

## 5. Not owned by this slice

| Item | Owner / status |
|---|---|
| Baseline EDA, run-to-run variation modelling, confounding checklist (B-W07-01..04) | Member B, on the exports this dossier produces |
| `experiments` table, run lifecycle API, telemetry→run association (C-W07-01..05) | Member C |
| Threshold source and hysteresis (D-W07-01/02) | Member D — the reset criterion is a candidate input to that work, not a decision |
| The T2 semantic conflict and any change to docs/01 | project-level; docs/01 remains authoritative and unchanged |
| S1 collection proper (W09) | blocked behind this week's runs, not behind tooling |
