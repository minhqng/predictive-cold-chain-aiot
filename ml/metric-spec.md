# ColdGuard · Metric Specification (W03, Member B)

> Deliverable of **B-W03-02**, Doc `05B` §31. Freezes metric *definitions,
> formulas, units, populations, and undefined-case policies* before final
> data. Computes no ColdGuard result: every numeric illustration is a
> hand-calculated example with labeled illustrative inputs (§9).
> Companion: `statistical-analysis-plan-v0.md` (units, populations P1–P6,
> paired inference), `scripts/sample_size_planning.py`.

| Field | Value |
|---|---|
| Owner | Member B |
| Parent docs | `03` §§41–45, 57–60, 68–74, 83–88, 204 [R6][R7] · `05B` §§12–13, 27, 31 · W01 dictionary/register/convention · W02 `labels.py` statuses |
| Task | B-W03-02 |
| Status | v0; W04 freezes the analysis contract and metric hierarchy (definitions, interfaces); measurement-dependent values remain provisional until their named §10 gates (W13–W16 where scheduled) |

Conventions used for every metric below: **Definition · Formula ·
Inputs/source · Unit · Evaluation population · Aggregation level ·
Undefined/missing-data policy · Interpretation · Freeze dependency.**
Populations P1–P6 are the analysis plan's §2. Tiers reuse the plan legend;
CANONICAL items cite Docs `00`–`03`.

Global rules (CANONICAL): only `EVALUABLE` W02 labels enter supervised
counts — `CENSORED`/`UNTRUSTED_INFO` are excluded support, never clean
negatives (`labels.py`; `03` §85). Missing PZEM samples are missing spans,
never zeros (dictionary §9; LRK-14). No naive EWT from B-controlled
trajectories (`03` §45). AP never proves closed-loop benefit (§1.7).

---

## 1. Average Precision — primary grouped predictive metric

- **Definition.** Canonical scikit-learn non-interpolated AP ([R7]): the
  `average_precision_score` summary of the precision–recall curve,
  `AP = Σₙ (Rₙ − Rₙ₋₁)·Pₙ` over thresholds. AP is **not** trapezoidal
  PR-AUC; the two are distinct summaries of the precision–recall curve and
  must not be treated as interchangeable (neither a universal equality nor
  a universal ordering between them is asserted).
- **Inputs/source.** Per-window risk **scores** (`risk_score`) on grouped
  runs; `EVALUABLE` labels `y ∈ {0,1}` only (`y_t(H)=1` iff a qualifying
  critical event falls in `(t, t+H]`, `03` §41). Positive class = event
  occurrence within horizon H. Score-vs-probability wording follows the W14
  calibration decision (`05B` §42): until then, outputs are scores.
- **Unit.** Dimensionless, [0, 1].
- **Population.** P1/P2/P3 grouped runs. Report support as
  (independent runs, dependent windows, prevalence, #positives).
- **Aggregation.** Computed once over pooled EVALUABLE windows **with
  run-grouped resampling only for uncertainty**; the point estimate's
  inferential N remains the run count. Class prevalence and run count
  accompany every AP value.
- **Undefined policy.** Single-class EVALUABLE set (all 0 / all 1) → AP is
  **undefined for scientific reporting**; report "AP undefined (single
  class; N₁=…/N₀=…)", never 0/1. This is a project reporting rule, not a
  claim about scikit-learn: `average_precision_score` does not always return
  NaN — it can return 0.0 (no positives) or 1.0 (all positives) for a
  single-class input — so undefined status must be assigned by the analysis
  contract, never inferred from the library. Censored/untrusted samples
  excluded before counting; exclusion counts reported.
- **Interpretation + limit.** AP measures ranking quality of early-warning
  scores on grouped runs. It **cannot** prove physical intervention
  effectiveness — that claim needs P5 paired outcomes (plan §2).
- **Freeze dependency.** Conceptual label/metric definitions and the
  label-spec interface freeze at W04; horizon H remains
  PROVISIONAL_UNTIL_FREEZE until W13; numeric event-boundary and
  representative-temperature choices remain provisional until frozen before
  locked evaluation / final-split label generation (`03` §§42–43), never
  invented at W04.

## 2. Precision / recall at a frozen operating point

- **Formulas.** `Precision = TP/(TP+FP)`; `Recall = TP/(TP+FN)` ([R6]).
- **Inputs.** Binarized warnings at the **frozen** operating threshold +
  persistence (TEAM_DEPENDENCY D policy version; B recommendation W15),
  EVALUABLE labels only.
- **Unit.** Dimensionless, [0, 1]. **Population/aggregation.** Same
  grouping discipline as AP; sample-level primary, event-level companion
  (§3) where defined. Always report denominators (TP+FP, TP+FN).
- **Undefined policy.** Zero denominator → metric **undefined**, reported
  as "undefined (no predicted positives)" / "undefined (no actual
  positives)" with support counts. Undefined precision is **never** evidence
  of zero model quality. Missing/uncertain labels excluded, counts shown.
- **Threshold discipline.** Selection uses development data only (P1 ∪ P2;
  P1 for fitting, P2 for held-back development selection); locked holdout
  (P3) never sets the threshold (LRK-07).

## 3. False warnings and missed events (episode-level)

- **Warning-episode grouping rule.** Repeated positive *samples* ≠
  independent warning episodes. Positives merge into one episode while gaps
  below a frozen gap parameter stay bridged; the gap/persistence parameters
  (`τ_persist`, episode gap) are PROVISIONAL_UNTIL_FREEZE (W15, `03` §§87–88)
  — this plan freezes the rule shape, not the numbers, and invents no value
  merely because the formula needs one.
- **False-warning episodes per eligible run** = episodes with no matched
  critical event within the frozen association window; plus an optional
  time-normalized rate (episodes per eligible hour) where exposure varies.
  Matched vs unmatched status is reported; no-event runs contribute
  false-warning burden (denominator = eligible runs/hours), never "recall".
- **Missed critical events** = qualifying events with no matched warning;
  denominator = event count (event-level recall companion). Persistent-warning
  requirement, ambiguous/unobserved-event handling (UNTRUSTED_INFO →
  excluded, counted), and the no-event-run rule above are all explicit.

## 4. Early Warning Time (offline, reactive)

- **Definition (CANONICAL, `03` §44).** `EWT = t_reactive − t_predictive`:
  first valid persistent predictive warning vs first reactive-criterion
  occurrence on the same non-intervened trajectory. Positive = earlier valid
  warning. Inputs: predictive warning stream (frozen threshold/persistence)
  + reactive criterion series (TEAM_DEPENDENCY threshold semantics).
- **Unit/population.** Seconds; P4 only. Per-event values; report median +
  distribution + N events/runs.
- **Undefined policy.** No-warning → EWT recorded as **no-warning**
  (missed-event accounting), never 0 or imputed. Multiple warnings → first
  valid persistent one. Late warning (after `t_reactive`) → negative EWT
  (reported, counted against usefulness). Incomplete run (reactive crossing
  unobserved — censored horizon) → **excluded** from EWT, counted as
  censored support.
- **Critical restriction (CANONICAL, `03` §45).** Never compute naive EWT
  from Controller B physical runs whose intervention may have prevented the
  crossing — closed-loop intervention destroys the counterfactual. B arms
  are inadmissible for EWT; violation voids the estimate.

## 5. Actionable Intervention Window (support)

- **Definition (CANONICAL, Doc `03` narrative + `05B` §13).**
  `AIW = t_critical − t_warning − T_system − T_physical`. Distinguishes
  early warning (EWT>0) → physically actionable warning (AIW>0) → verified
  physical response (electrical + thermal per `01` §1.7).
- **Inputs (TEAM_DEPENDENCY, measured only):** event/measurement time (A/C),
  backend/transport delay + inference time + policy/command delay (C/D),
  electrical response + thermal response (A). An AIW is estimated **only**
  when its inputs are known and the methodology is valid for that
  trajectory — guessed latencies or synthetic delays are forbidden
  substitutes. Units seconds; per-event estimates on P4-style trajectories.

- **Inputs (TEAM_DEPENDENCY, measured only):** event/measurement time (A/C),
  backend/transport delay + inference time + policy/command delay (C/D),
  electrical response + thermal response (A). An AIW is estimated **only**
  when its inputs are known and the methodology is valid for that
  trajectory — guessed latencies or synthetic delays are forbidden
  substitutes. Units seconds; per-event estimates on P4-style trajectories.

## 6. Thermal exposure (primary physical outcome candidate)

- **Definition (CANONICAL, `03` §68).**
  `E_T = ∫ max(0, T(t) − T_limit) dt`, discrete
  `E_T ≈ Σᵢ max(0, Tᵢ − T_limit)·Δtᵢ`.
- **Inputs.** Representative-temperature series (Tmax/Tmean choice
  PROVISIONAL_UNTIL_FREEZE — never the nicer-result variant, `03` §69),
  threshold `T_limit` provenance (numeric value PROVISIONAL_UNTIL_FREEZE
  until frozen before locked evaluation, `03` §42), uniform or measured
  `Δtᵢ` time base with irregular-interval handling, per-sample quality
  flags.
- **Unit/population.** °C·s (or °C·min — one frozen at W04); P5 pairs
  (P4 characterization where defined). Per-run value → paired `I_i`.
- **Undefined policy.** Missing/corrupted samples → excluded span with
  coverage fraction reported; runs below the frozen coverage floor are
  invalid for `E_T`. No interpolation across gaps, no zero-fill.

## 7. Recovery time (primary physical outcome candidate)

- **Definition (CANONICAL, `03` §70).**
  `T_recovery = t_recovered − t_reference`.
- **Inputs.** Reference event (e.g. disturbance end / reactive onset —
  frozen choice), target band + recovery persistence `τ_stable`
  ("re-enters band and stays ≥ τ_stable"), representative series.
  Interfaces are defined at W04; numeric value choices are
  PROVISIONAL_UNTIL_FREEZE and freeze only before locked evaluation
  (`03` §70).
- **Unit/population.** Seconds (or minutes — one frozen); P5 pairs.
- **Undefined policy.** Non-recovered before termination →
  **censored/non-recovered**, never a finite time. Report censoring time
  and treat per the frozen survival/exclusion rule (exclusion default;
  any survival analysis is predeclared, never improvised).

## 8. Cooling-branch electrical energy (supporting outcome)

- **Definition (CANONICAL, `03` §72).**
  `E_Wh = Σᵢ (Pᵢ·Δtᵢ)/3600` over the measured cooling branch only —
  never whole-system energy (`00` §3.10). Where the hardware supplies a
  cumulative energy counter, its semantics (discontinuities, resets,
  rollover) are verified against integrated power before either is trusted.
- **Inputs.** `cooling_power_w` samples or validated energy counter
  (dictionary §1.1 PZEM path), coverage span, gap log.
- **Unit/population.** Wh; P5 pairs with valid electrical coverage.
- **Undefined policy.** Missing PZEM samples = missing span (excluded,
  coverage reported) — never zero consumption (LRK-14). Counter resets →
  segmented integration with the discontinuity logged; unresolvable spans
  invalidate the run for energy (thermal outcomes may survive under a
  predeclared per-outcome rule, §4.7 of the plan).

- **Undefined policy.** Missing PZEM samples = missing span (excluded,
  coverage reported) — never zero consumption (LRK-14). Counter resets →
  segmented integration with the discontinuity logged; unresolvable spans
  invalidate the run for energy (thermal outcomes may survive under a
  predeclared per-outcome rule, §4.7 of the plan).

## 9. Hand-calculated verification examples (illustrative inputs — not data)

Each example checks signs, units, denominators, and undefined cases.

- **AP (sklearn non-interpolated).** Scores/labels (EVALUABLE):
  y=[0,0,1,1], s=[0.1,0.4,0.35,0.8] →
  AP = 0.5 × 1 + 0.5 × (2/3) = 5/6 ≈ **0.8333** (verified against
  `sklearn.metrics.average_precision_score` for this ordering). Single-class
  set y=[0,0,0] → **undefined by the reporting policy** (support N₁=0
  reported), never 0; scikit-learn itself returns 0.0 here (and 1.0 for an
  all-positive single class) with a warning, not NaN.
- **Precision/recall.** TP=4, FP=2, FN=1 → P=4/6=**0.667**,
  R=4/5=**0.800**. Zero predicted positives (TP+FP=0) → precision
  **undefined** ("no predicted positives"), not zero quality.
- **Warning episodes.** Positives at t=10–14 s (gap-bridged) + lone spike
  t=60 s, association window ±30 s around one event at t=12 s → episodes=2,
  matched=1, **false-warning episodes=1** on an eligible 10-min run
  (rate 6/hour). No-event run with 1 episode → burden=1, recall N/A.
- **EWT.** `t_predictive`=100 s, `t_reactive`=160 s → **EWT=+60 s**
  (earlier valid warning). Warning at 200 s → EWT=−40 s (late, counted
  against). No warning → **no-warning** (missed), never 0.
- **AIW.** `t_critical`=300 s, `t_warning`=100 s, `T_system`=25 s,
  `T_physical`=90 s → **AIW=85 s** actionable. Guessed latencies →
  **no estimate** (inputs unknown).
- **Thermal exposure.** T−T_limit excess [1.0, 2.0, 0.0] °C at Δt=1 s →
  **E_T=3.0 °C·s**. Missing middle sample → span excluded, coverage 2/3
  reported; below floor → run invalid for `E_T`.
- **Recovery.** `t_reference`=0 s, re-enters band at 240 s, stays ≥
  τ_stable=60 s → **T_rec=240 s**. Never re-enters → **non-recovered**
  (censored at end time), never finite.
- **Energy.** P=[12, 12] W over Δt=[300, 300] s →
  **E_Wh=(12·300+12·300)/3600=2.0 Wh** (cooling branch only). Missing
  second sample → span excluded (not 0 W); counter reset mid-span →
  segmented integration with logged discontinuity.

## 10. Provisional-until-freeze ledger (gates)

Freeze classes: conceptual definitions and supported interfaces are frozen by
the W04 analysis contract and metric hierarchy; the numeric values below are
measurement-dependent and freeze only at their named gates (including W13
horizon, W14 calibration, W15 threshold/policy and model, W16 locked test).
W04 does not invent critical temperatures, recovery bands, response delays,
or outcome tolerances.

| # | Item | Gate / owner |
|---|---|---|
| F1 | Representative temperature (Tmax/Tmean/named probe) | Definition/interface at W04; numeric choice frozen before final-split labels and locked evaluation (`03` §§42–43, 69) |
| F2 | `T_critical`/`T_limit` values | Numeric value frozen before locked evaluation (`03` §42); not set by the W04 analysis-contract freeze |
| F3 | `T_reactive` semantics for offline EWT | Semantics frozen at W04 (`03` §§44, 84); numeric policy threshold remains D-owned/PROVISIONAL |
| F4 | Primary horizon (candidates 30/60/120/300 s) | B horizon freeze W13 (`05B` §41) |
| F5 | Operating threshold + persistence/episode gap | B/D policy freeze W15 (`05B` §43; `03` §§87–88) |
| F6 | Initial-condition tolerances (final numerics; pilots `03` §35) | A/B pilot → pre-A/B freeze |
| F7 | AIW timing inputs (all components, measured) | A/C/D measurement freeze (`03` §57) |
| F8 | Recovery reference / target band / persistence | Definition at W04; numeric reference/band/persistence frozen before locked evaluation (`03` §70) |
| F9 | Primary outcome selection | Metric-hierarchy freeze at W04 (`05B` §32); measurement-dependent values stay provisional |
| F10 | Minimum engineering-relevant improvement | Pre-A/B, B with A/D (`03` §82) |
| F11 | Energy-counter vs integrated-power semantics | A characterization + B W04 (`03` §72) |
| F12 | Full events/command-timeline schema | C W07 semantics (`02` §14.4), TEAM_DEPENDENCY |

No provisional choice above is quoted as a measured or agreed fact.

## 11. Cross-document consistency (Phase C gate)

Plan ↔ metric-spec share metric names, units, populations, and the
`I_i = Y_A − Y_B` reading. Sample-size planning counts pairs, never rows.
EWT analysis (P4) is separated from A/B outcomes (P5). Censored/untrusted
labels never enter as negatives. W01 quality/versioning stays authoritative;
W02 split/manifest provenance supplies §3 identities; inputs needing
unimplemented C/A/D schemas are marked dependencies. No fictional dataset,
probability, result, or performance appears in either document.

## 12. Handoff / scheduled debt

B owns this contract, `metric-spec.md`, the planning script + tests, and
traceability to W01/W02 identities. A owns sensing/calibration/validity/
disturbance/thermal timing/energy validity. C owns exports/metadata/event
timestamps/quality/linkage. D owns reactive semantics/applied state/frozen
threshold-persistence/command timing. SCHEDULED_DEBT: real bootstrap-CI +
actual A/B analysis code (W04+, B); hash-recompute audit checker
(convention §9). A/C data-facing review of W01–W03 remains pending by
explicit operator choice (`04` §3.3) — recorded, never auto-requested.

---

*Spec ends. No dataset, threshold, probability, experiment result, or model
performance is computed or claimed — the formulas above are the contract
future data will be judged against.*



