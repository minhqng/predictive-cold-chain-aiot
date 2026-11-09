# Member A requirement coverage — A-W07-01 .. A-W16-04

Canonical source: `docs/05A` §16-§25, with the handover list in §5 and the interfaces in
§6.1 (A→B), §6.2 (A→C), §6.3 (A→D). 44 assigned items.

## Current audit (2026-11-09 — authoritative)

Statuses: `COMPLETE` requirement satisfied with committed evidence · `SOFTWARE_COMPLETE`
software/method deliverable satisfied, physical acceptance pending by design ·
`BLOCKED_PHYSICAL` needs a supervised hardware session · `BLOCKED_DEPENDENCY` an input is
owned by B/C/D or the operator. Store verdicts are the authoritative acceptance outcomes
(`evidence/A/h8-captures/capture-20261104T092140Z`, branch `feat/a-acceptance-app`,
recounted 2026-11-09: 114 items = 80 PASS / 2 FAIL / 7 INCOMPLETE / 25 NOT_RUN).
Every row below names the committed artifact that backs it.

| ID | Ask (short) | Status | Backing artifact / verdict |
|---|---|---|---|
| A-W07-01 | Geometry freeze | **COMPLETE** | store PASS; `evidence/A/W07/geometry-v1.md` frozen as-built + W23 photo cross-checks (fuse block, wiring, kit) |
| A-W07-02 | ≥3 passive warm-up reps | **COMPLETE** | store PASS; warm-up/recovery segments in the accepted dataset `evidence/A/SOURCES/20261107/datasets/` |
| A-W07-03 | ≥3 cooling-step reps | **COMPLETE** | store PASS; W07 repeats + H8 C/D/E cooling segments in the same dataset |
| A-W07-04 | Repeatability summary | **COMPLETE** | store PASS; repeatability numbers restated from real runs |
| A-W07-05 | Reset criterion | **COMPLETE** | store PASS; reset criterion evaluated on the 1 Hz campaign phase |
| A-W08-01 | Safe operating envelope | **COMPLETE (observed, not a rating)** | store PASS; envelope-from-observations published (`evidence/A/W08/`), one-session/limited-session basis stated |
| A-W08-02 | Fuse finalization | **COMPLETE (with recorded limitation)** | store PASS (2026-11-05): 15 A vs measured bases 5.03 A / 9.35 A peaks; conductor ampacity NOT certified; body marking unobtainable (operator statement of record) |
| A-W08-03 | Hot-side sustainability | **BLOCKED_PHYSICAL + BLOCKED_DEPENDENCY** | store NOT_RUN; needs D's six-limit freeze, stage-enabled W06 flash consent, slot-3 fuse insertion, supervised ARM/START; H8-C 600 s data is bench-grammar, excluded by the evaluator |
| A-W08-04 | SAFE_LOCAL support | **COMPLETE** | store PASS; D owns mode rules (team dependency documented) |
| A-W08-05 | Gate A package | **COMPLETE** | store PASS; Gate-A report with the high-current anomaly kept visible |
| A-W09-01 | Run checklist | **COMPLETE** | store PASS; `evidence/A/W09/run-protocol-v1.md` gates host-verified |
| A-W09-02 | S1 baseline (≥4 valid runs) | **COMPLETE** | store PASS; 4 accepted S1 runs (dataset gates coverage ≥ 0.85; trial2-4 1.0000, trial1-imported 0.9983) |
| A-W09-03 | Physical invalidation logging | **COMPLETE** | store PASS; invalidation rules + retained invalid attempts |
| A-W09-04 | Healthy response reference | **BLOCKED_DEPENDENCY** | store NOT_RUN; prereq A-W08-03 |
| A-W10-01 | Door protocol | **COMPLETE** | store PASS; S2 protocol anchored to committed captures |
| A-W10-02 | Timing methodology | **COMPLETE** | store PASS; MC-38-authoritative method |
| A-W10-03 | Repeated S2 pilot | **COMPLETE** | store PASS; 4 door runs + 1 timing window in the accepted dataset |
| A-W10-04 | Pairing tolerance evidence | **COMPLETE (evidence); freeze is B's** | store PASS; `pairing-physics` evidence delivered |
| A-W10-05 | Prediction horizon support | **BLOCKED_DEPENDENCY** | store INCOMPLETE `NO_DOOR_CRITICAL_SAMPLES`; D's frozen critical-Tmean threshold, then offline rerun (0 new captures) |
| A-W11-01 | S4 method | **COMPLETE** | store PASS; `firmware/tools/cg_w11_s4.py` + `S4-protocol.md` (no unsafe method) |
| A-W11-02 | S4 refusal evidence | **COMPLETE (refusal-state); 0 publishable S4 run sessions claimed** | store PASS; handler refusal verified (start refused, 0.0 A applied-current proof of state, no claim of physical S4 campaign) |
| A-W11-03 | Dataset expansion | **COMPLETE** | store PASS (2026-11-09); genuine additional 600 s S1 trial at `evidence/A/SOURCES/20261109/s1/s1-20261109T081304Z/` |
| A-W11-04 | S3 feasibility decision | **COMPLETE (NO-GO)** | store PASS; `S3-go-no-go.md` with instrumentation basis |
| A-W12-01 | Sensor consistency recheck | **COMPLETE** | store PASS; drift re-evaluated per-image honestly |
| A-W12-02 | PZEM zero/active validation | **COMPLETE** | store PASS; zero-vs-absent rule + status-coverage artifacts |
| A-W12-03 | Mechanical audit | **COMPLETE** | store PASS; photo-supported audit vs geometry-v1 (2026-11-05) |
| A-W12-04 | HW config signoff | **COMPLETE (A's half)** | store PASS; team signoff remains a joint record |
| A-W12-05 | Gate G3 input | **COMPLETE (A input only)** | store PASS; G3 gate itself not declared GREEN by Member A |
| A-W13-01 | Command→electrical delay | **COMPLETE** | store PASS; response-delay stats from real campaign captures |
| A-W13-02 | Command→thermal response | **COMPLETE** | store PASS; per-session labelling intact |
| A-W13-03 | Door→critical time | **BLOCKED_DEPENDENCY** | store INCOMPLETE; same D threshold input as A-W10-05 |
| A-W13-04 | Time-constant proxies | **COMPLETE** | store PASS; labelled proxies from real runs |
| A-W14-01 | Sensor-position QA | **COMPLETE** | store PASS; spatial QA against frozen geometry |
| A-W14-02 | Logical ablation support | **COMPLETE** | store PASS; logical-only ablation (no probe unplugging) |
| A-W14-03 | Spatial statistics | **COMPLETE** | store PASS; agreement stats from real runs |
| A-W14-04 | Pairing criterion refinement | **BLOCKED_DEPENDENCY** | store NOT_RUN; B's freeze with A's evidence |
| A-W15-01 | Electrical feature integrity | **COMPLETE** | store PASS |
| A-W15-02 | A3 dataset support | **COMPLETE** | store PASS; provenance rows carry caveats |
| A-W15-03 | PZEM reference check | **COMPLETE (self-consistency; absolute accuracy explicitly NOT claimed)** | store PASS; external meter gap documented |
| A-W15-04 | PWM Go/No-Go | **COMPLETE (NO-GO)** | store PASS; decision NO-GO recorded (no characterized canonical duty ladder) |
| A-W16-01 | Re-run short characterization | **BLOCKED_PHYSICAL** | store NOT_RUN; prereq A-W08-03; stage-enabled image + session |
| A-W16-02 | W07/W08 vs W16 comparison | **BLOCKED_PHYSICAL** | store NOT_RUN; needs A-W16-01 captures |
| A-W16-03 | Final pair tolerances | **BLOCKED_DEPENDENCY + PHYSICAL** | store NOT_RUN; S-2/S-3 outputs + B's freeze |
| A-W16-04 | Controller B physical readiness | **BLOCKED_DEPENDENCY** | store NOT_RUN; B's freeze; A contributes the physical half, verdict `NO_FREEZE` recorded |

W07–W16 tally against the 44 assigned items: **35 COMPLETE** (each backed by a store PASS
verdict; several carry explicit recorded limitations — envelope ≠ rating, no certified
ampacity, refusal-state ≠ physical S4 campaign, PWM NO-GO), 2 INCOMPLETE (W10-05, W13-03 —
one D input each), 7 NOT_RUN (W08-03, W09-04, W14-04, W16-01..04 — one physical gate chain
plus B's freeze): 35 + 2 + 7 = 44. Outside W07–W16 the store also holds 2 FAIL (operator hardware: A-W01-01, A-W03-02), 5 INCOMPLETE (A-W06-01/02/03/06
Member C contracts; A-W23-03 physical labels) and 18 further NOT_RUN items (W17–W24
shadow/campaign scope) — listed here so the 80 PASS count is never misread as
"everything is done".

## Historical snapshot (pre-dataset era — retained for traceability)

The tables below were written before the accepted 2026-11-07 dataset and before the
authoritative store verdicts were recorded. They are retained unchanged for history; every
"zero valid runs", "NOT_ESTABLISHED", "IN FLIGHT"/"FIX"/"DATA" statement in them describes
the situation at that time and is superseded by the audit above where the two disagree.

Delivery states used here — they are deliberately not the same thing as "done":
`HOST` tooling exists and passes host checks · `PR` published as an open pull request
(not merged) · `FIX` reviewed, defects confirmed, repair in progress on a task branch ·
`DATA` blocked until a real session supplies the measurement · `TEAM` another member owns
the decision.

| ID | Canonical ask | State | Where it lives | What is still missing |
|---|---|---|---|---|
| A-W07-01 | Geometry freeze | **PR #18** partial | `evidence/A/W07/geometry-v1.md` §1-§3 | mounting method/height/clearance, V1, cables, door alignment, load, conductor evidence, configuration photo → session S-0 |
| A-W07-02 | ≥3 passive warm-up reps | **DATA** | `evidence/A/W07/warmup-runs.jsonl` has 1 segment of 226 samples | 3 independent passive sessions (fresh boot each) → S-1 |
| A-W07-03 | ≥3 cooling-step reps | **DATA** | `cooling-step-runs.jsonl` has 1 of 600 samples | 3 independent cooling sessions → S-2, gated on §1 safety |
| A-W07-04 | Repeatability summary | **PR** host-complete | `repeatability-report.md`, 4 `repeatability-tmean_*.json`, overlay CSV 3 828 rows | the summary stays `NOT ESTABLISHED` until A-W07-02/03 supply runs |
| A-W07-05 | Reset criterion candidate | **PR** candidate | `reset-criterion-v0.yaml`, `cg_reset_criterion.py` (37 tests) | `tmean_band_c`, `gradient_bound_c_per_min` UNRESOLVED → S-1; plus the Tmean project decision |
| A-W08-01 | Safe operating envelope | **FIX** | `feat/a-w08-electrical-envelope` `evidence/A/W08/` | observed envelope is published (peak 9.99 A, mean 7.2247 A over 600 driven frames, idle floor 0.02 A) but from ONE session; envelope ≠ rating |
| A-W08-02 | Fuse finalization | **DATA + TEAM** | `evidence/A/W04/fuse-commissioning-note.md` §3-§4 | installed conductor ampacity at real insulation class/routing; no number is defensible today and none was invented |
| A-W08-03 | Hot-side sustainability | **FIX** | `evidence/A/W08/thermal-sustainability.csv` | T2 is hot-side observation only; no sustained-duty thermal proof exists |
| A-W08-04 | SAFE_LOCAL support | **TEAM** | `evidence/A/W08/safe-local-physical-inputs.csv` | Member D owns the mode rules |
| A-W08-05 | Gate A package | **FIX** | `evidence/A/W08/Gate-A-report.md` | a Gate-A row that read "no unresolved high-current anomaly: MET" is being softened: the frame is unresolved |
| A-W09-01 | Run checklist | **FIX** | `feat/a-w09-dataset-tooling` `evidence/A/W09/run-protocol-v1.md` | fail-closed defects found (absent status read as satisfied) |
| A-W09-02 | S1 baseline (~4 valid runs) | **DATA** | `s1-run-index.json`, `run-registry.json` | zero valid S1 runs exist; tooling is what ships today |
| A-W09-03 | Physical invalidation logging | **FIX** | `invalidation-summary.json` | 6 HIGH findings; the export claim (26 cols vs 24 delivered) is one of them |
| A-W09-04 | Healthy response reference | **FIX** | `healthy-ranges.json` | gradient estimator was unlabelled and 3× a least-squares fit over the same rows |
| A-W10-01 | Door protocol candidates | **FIX** | `evidence/A/W10/S2-protocol-v1.md` | cites an untracked driver file as its proof; must be re-anchored |
| A-W10-02 | Timing method (MC-38 + timer) | **FIX** | `door-event-validation.csv` | method is right; state naming without attestation is being corrected |
| A-W10-03 | Repeated S2 pilot (4-6) | **DATA** | `door-response-metric.json` = NOT_COMPUTABLE | no real door-open event exists anywhere: `door_open` is `0` in 940 rows, `UNKNOWN` in 17 |
| A-W10-04 | Pair tolerance evidence | **DATA + TEAM** | `pairing-physics.json` (tolerance `null`) | needs S-3 variation; B freezes the tolerance |
| A-W10-05 | Horizon support | **DATA** | `horizon-support.json` (`computable_now: false`) | door→critical distribution cannot exist before S-3; A must not pick the ML horizon |
| A-W11-01 | S4 method | **IN FLIGHT** | `feat/a-w09-dataset-tooling` `cg_w11_s3_feasibility.py` | unfinished: W11 is being completed and committed now |
| A-W11-02 | S4 evidence | **DATA** | `cg_w11_s4.py`, `cg_s4_refusal.py` | no refusal session has run; needs D's thresholds first |
| A-W11-03 | Dataset expansion | **DATA** | reuses W09 run registry | additional valid S1/S2 runs |
| A-W11-04 | Conditional S3 feasibility | **FIX/PENDING** | `cg_w11_s3_feasibility.py` | methodology only; one skipped test must be resolved or explained |
| A-W12-01 | Sensor consistency recheck | **FIX** | `feat/a-w12-physical-readiness` `drift-audit.json` | HIGH: configuration keying collapsed two different images into one key and manufactured zero drift |
| A-W12-02 | PZEM zero/active check | **FIX** | `electrical-status-coverage` rows on W08 side | zero-vs-absent rule exists; validator skipped 18 byte checks silently |
| A-W12-03 | Mechanical audit | **DATA** | `mechanical-audit-checklist.csv` | static authored strings, not derived → session S-0 closes it |
| A-W12-04 | Hardware config signoff | **TEAM + DATA** | `gate-g3-input.json` (`frozen: false`) | signoff is not Member A's alone; blockers must be derived, not hardcoded |
| A-W12-05 | Gate G3 input | **TEAM** | `gate-g3-input.json` | Member A input only; no whole-team gate declared GREEN |
| A-W13-01 | Command→electrical delay | **DATA (n=1)** | `response-delay.csv` `median=p95=max=1.094 s` | one sample only; a latency-exclusion rule that cannot fail is being fixed |
| A-W13-02 | Command→thermal response | **FIX** | `1 C at 0.85 min` from the 600 s session | single-session basis; window/estimator labelling |
| A-W13-03 | Door→critical time | **DATA** | `status=NOT_COMPUTABLE, value_s=null` | only S-3 can produce it; no numeric door value exists anywhere |
| A-W13-04 | Passive/cooling time constants | **FIX** | `cooling_tau=174 s`, `recovery_tau=86 s` | labelled proxies; biased low by window truncation (stated) |
| A-W14-01 | Sensor-position QA | **IN FLIGHT** | `feat/a-w14-spatial-statistics` | method + baseline only; cannot claim "no movement verified" without a new capture |
| A-W14-02 | Logical ablation support | **IN FLIGHT** | same branch | must stay logical (same physical runs); T2/T3 are not to be unplugged |
| A-W14-03 | Spatial statistics | **IN FLIGHT** + **DATA** | same branch | agreement from one session is an observation, not a distribution; disturbance-specific response needs S-3 |
| A-W14-04 | Pairing criterion refinement | **TEAM** | same branch | A supplies evidence; B freezes tolerances |
| A-W15-01 | Electrical feature integrity | **FIX** | `evidence/A/W15/` | see A-W12-02 |
| A-W15-02 | A3 dataset support | **FIX** | `a3-feature-provenance.csv`, `A3-run-index.csv` | run-index dropped its caveats column, so an H7 row can be over-trusted |
| A-W15-03 | PZEM reference check | **DATA + EXTERNAL** | W15 gap report | needs a trusted independent meter; self-consistency is not accuracy |
| A-W15-04 | PWM Go/No-Go | **TEAM** | `decision: NOT_DECIDED`, 6 criteria + 6 limits UNRESOLVED | method only; no Go declared and none reachable by construction |
| A-W16-01 | Re-run short characterization | **DATA** | `evidence/A/W16/` framework | no W16-era session exists |
| A-W16-02 | Compare W07/W08 vs W16 | **DATA** | `cross_era_comparison` = all six dims `MISSING_SIDE` | comparability must not pass by copying the baseline's nulls — under repair |
| A-W16-03 | Final pair tolerances | **TEAM + DATA** | all four tolerances `NOT_MEASURED` | needs S-2/S-3 plus B's freeze |
| A-W16-04 | Controller B physical readiness | **TEAM** | `verdict: NO_FREEZE` | A contributes the physical half only |

## Counts

- Software-side items with a published PR today: **1** (A-W07-01/04/05 on PR #18, unmerged).
- Items whose tooling exists but whose **acceptance data does not**: A-W07-02, A-W07-03,
  A-W09-02, A-W10-03, A-W10-04, A-W10-05, A-W11-02, A-W11-03, A-W12-03, A-W13-01, A-W13-03,
  A-W16-01, A-W16-03 — **13 items blocked on sessions**, not on code.
- Items where another member owns the decision: A-W08-04, A-W12-04, A-W12-05, A-W14-04,
  A-W15-04, A-W16-04, plus the Tmean definition behind A-W07-05.
- No item is reported physically verified on the strength of a host test.

## What the single committed session can and cannot support

One capture, `evidence/A/W04/tec-cooling-response-600s.csv`, 957 rows, **one** `boot_id`
`56044b74`, carrying **two** `run_id` values (`run-00000000` 226 rows = the passive segment,
`run-00000001` 731 rows). Because two run ids live inside one boot, `run_id` is not an
independence key on this rig and W09 blocks those ids rather than handing them to Member B.
It supports: one cooling step (600 driven frames, mean 7.2247 A, peak 9.99 A), one passive
segment (226 samples, 224.99 s), one recovery segment (131 samples), and the 3.40× disagreement
between chamber-air and canonical-literal means. It does **not** support any repeatability,
distribution, tolerance or horizon claim, and it contains 357 zero-duty frames whose current
is 0.0 / 0.02 / 0.56 / 7.15 A — the 7.15 A one being the unresolved anomaly in §1 of the
session plan.
