# ColdGuard · Metric Hierarchy v1 (W04, Member B)

> Deliverable of **B-W04-04** (Doc `05B` §32). Freezes the primary/secondary
> metric hierarchy **before** outcome results are observed, so later analysis
> cannot select the metric that happened to look best. It also reconciles the
> W03 F1–F12 provisional ledger with the W04 decision.
>
> Companion: `analysis-contract-v1.md` (source/schema/eligibility, EWT, AIW),
> `statistical-analysis-plan-v0.md` (P1–P6, paired inference),
> `metric-spec.md` (formulas and hand-calculated examples).

| Field | Value |
|---|---|
| Owner | Member B |
| Parent docs | `00` §§0.3–0.4, 5.3–5.4 · `01` §§17, 20–24, 33, 35 · `02` §§19.4, 51, 60 · `03` §§41–49, 52–54, 68–74, 84–88, 92, 99–101, 119–122, 125, 133, 174, 176–182 · `04` §§3.3, 10, 11.1, 11.4 · `05B` §§2, 12–13, 20, 26–27, 31–32, 41–44 |
| Task | B-W04-04 |
| Status | v1 hierarchy freeze. Conceptual definitions and supported interfaces are frozen. Measurement-dependent numeric values remain PROVISIONAL_UNTIL_FREEZE at their named gates. |

Tier legend: **CANONICAL** · **DERIVED** · **IMPLEMENTATION_CHOICE** ·
**TEAM_DEPENDENCY** · **PROVISIONAL_UNTIL_FREEZE** · **SCHEDULED_DEBT**.

---

## 0. Purpose, anti-shopping rule and amendment path

The hierarchy answers one question before any data exists:

> Which predictive metric and which physical outcome decide success, and which
> outcomes are supporting, diagnostic or exploratory?

Rules:

1. The primary predictive metric and primary physical outcome are frozen at
   W04. Secondary and diagnostic outcomes cannot silently become primary.
2. A post-result promotion of a secondary metric requires a recorded
   **amendment**: a new id, a stated reason, and an explicit exploratory
   disclosure. The amendment is reported next to the result; it does not
   rewrite history.
3. A diagnostic outcome never becomes a primary physical outcome by
   substitution.
4. No metric, horizon, threshold, persistence constant, representative
   temperature or unit is selected after inspecting outcome results.
5. A null result with a correct CI is a valid verification outcome; the
   hierarchy does not promise significance.
6. The hierarchy is a reporting contract, not a claim that any outcome was
   measured. No ColdGuard result is computed here.

Executable guards live in
`coldguard_ml.evaluation_contract.MetricHierarchy` and
`assert_allowed_for_selection`.

---

## 1. Predictive evaluation hierarchy

### 1.1 Primary predictive metric

**Non-interpolated Average Precision (AP)** on grouped runs.

- Definition: canonical scikit-learn `average_precision_score` summary,
  `AP = Σₙ (Rₙ − Rₙ₋₁)·Pₙ` over thresholds.
- **AP is not trapezoidal PR-AUC.** `trapezoidal_pr_auc`, `pr_auc` and
  `area_under_pr_curve` aliases are a different summary of the PR curve; they
  are refused as the primary metric and are not interchangeable with AP.
- Input: per-window `risk_score` or calibrated probability, with EVALUABLE
  labels only.
- Population: P1/P2/P3 grouped runs. Report support as
  `(independent runs, dependent windows, prevalence, positives)`.
- Aggregation: pooled EVALUABLE windows; run-grouped resampling only for
  uncertainty. Window/row counts never enter a power formula or the
  inferential N.
- Undefined policy: a single-class EVALUABLE set makes AP **undefined for
  scientific reporting**; report the class counts, never 0/1. Censored and
  untrusted labels are excluded with counts.
- Interpretation limit: AP measures ranking quality of early-warning scores;
  it cannot prove that a physical intervention improved an outcome. That
  requires P5 paired physical runs.

### 1.2 Secondary predictive metrics

These support the primary metric but do not replace it:

| Metric | Unit / denominator | Notes |
|---|---|---|
| Precision at the frozen operating point | [0, 1]; TP/(TP+FP) | Frozen threshold/persistence from development data; zero denominator → undefined, never zero quality. |
| Recall at the frozen operating point | [0, 1]; TP/(TP+FN) | Same frozen operating point; report denominator. |
| False-warning episodes per eligible run | episodes / eligible run | Episodes, not positive samples; no-event runs contribute burden, not recall. |
| False-warning episodes per eligible hour | episodes / eligible hour | Time-normalized companion where exposure varies. |
| Missed-event rate | events missed / qualifying events | Explicit event denominator; censored events are not silently negatives. |
| EWT distribution | seconds; per event | P4 offline non-intervened trajectories only; report median, distribution, N events/runs. |
| Warning duration / repeated alerts | seconds / count | Supporting operational burden; not a substitute for AP. |
| ROC-AUC | [0, 1] | Optional secondary discrimination summary; never the primary metric. |

### 1.3 Dependence, support and event-vs-sample accounting

- Telemetry rows and overlapping windows are dependent observations. They
  never become independent N.
- The independent grouped support is the run count; report it separately from
  window count and event count.
- A warning episode is not 60 independent true positives. Event-level warning,
  false-warning and missed-event counts are reported with their own
  denominators.
- The locked holdout (P3) is never used for fitting, selection, calibration or
  threshold tuning. `assert_allowed_for_selection` refuses `test`/`locked`/
  `holdout` partitions.

### 1.4 Score versus probability

Until the W14 calibration decision, the model output is a **risk score**, not
a calibrated probability. A probability wording (e.g. `P(critical within H) =
0.72`) requires calibration evidence: reliability, Brier score, calibration
method and development-only fitting. Without that evidence, report score-only
semantics. AP and other ranking metrics do not require calibrated
probabilities, but they also do not create them.

### 1.5 Undefined and missing policy (predictive side)

- CENSORED / UNTRUSTED_INFO labels are excluded from supervised denominators
  and counted; they are never clean negatives.
- Single-class AP is undefined; zero-denominator precision/recall is
  undefined; undefined is not evidence of zero quality.
- A missing channel is a missing state, never zero or a fabricated value.
- No naive EWT from a predictively intervened trajectory.
- No AP from a contaminated intervention dataset.

### 1.6 Freeze status

Frozen now: metric family, definitions, population/aggregation rules,
sign/undefined policies, AP-vs-PR-AUC distinction, score/probability rule.

Still provisional: primary horizon H (F4/W13), operating threshold and
persistence/episode gap (F5/W15), calibration method and score/probability
semantics (W14), locked-test run IDs and one-shot evaluation (W16).

---

## 2. Physical A/B evaluation hierarchy

### 2.1 Primary physical outcome

**Thermal exposure, `thermal_exposure` — lower is better.**

Definition (CANONICAL family, Doc `01` §21; Doc `03` §68):

\[
E_T = \int \max(0, T_{rep}(t) - T_{limit})\,dt
\]

Discrete approximation:

\[
E_T \approx \sum_i \max(0, T_i - T_{limit})\,\Delta t_i
\]

Frozen at W04:

- **Metric:** thermal exposure, lower is better.
- **Unit:** **°C·s** (the canonical integral is over seconds; `°C·min` is not
  used as the primary unit).
- **Representative temperature, definition only:** a predeclared
  role-qualified chamber-air representation. It must exclude hot-side and
  non-air roles; on the current rig the literal `mean(T1,T2,T3)` and the
  all-slot `Tmax−Tmin` are therefore not legal chamber-air representations.
  The choice among `Tmax`, `Tmean` or a named chamber-air probe is **F1** and
  freezes before final-split label generation and locked evaluation, never by
  which choice makes the result look better.
- **Threshold:** `T_limit` is a testbed research boundary, not a food-safety
  or commodity regulatory limit. Its numeric value is **F2**, frozen before
  locked evaluation; W04 does not invent it.
- **Time base:** event-time or declared trusted relative time; each `Δt_i`
  is measured, not assumed to be 1.000 s.
- **Aggregation:** one per-run `E_T` → one paired difference `I_i` per valid
  A/B pair. The pair, not the row/window, is the statistical unit.
- **Missing/undefined:** missing or corrupted thermal samples create an
  excluded span with reported coverage; no interpolation and no zero-fill. A
  run below the pre-campaign coverage floor is invalid for `E_T`, not a zero
  exposure. The coverage floor is derived from W05 QA evidence and frozen
  before the A/B campaign; W04 does not set the number.
- **Interpretation limit:** exposure above a configured testbed boundary
  measures severity × duration of a thermal excursion. It is not whole-system
  energy, not thermodynamic COP, not product quality and not a component-level
  root cause. It is sensitive to the frozen representative temperature and
  `T_limit`, so both are predeclared.

**Why thermal exposure is primary (selected before outcome results):**

- **Canonical authority:** Doc `01` §21 and Doc `03` §68 define the metric
  family; Doc `03` §74 fixes the paired-difference reading.
- **Measurement meaning:** it directly represents how far and how long the
  protected chamber-air state exceeds a protection boundary — the physical
  harm the controller is meant to reduce.
- **Usefulness:** it is comparable across A/B arms under the same disturbance
  and pairing protocol, and it is not a proxy that silently changes meaning
  between arms.
- **Feasibility:** its inputs are identified (role-qualified representative
  temperature, trusted time base, predeclared `T_limit`, coverage floor). The
  representation and threshold are not yet measured, but that gates numeric
  values, not the definition.

Recovery time is scientifically meaningful but needs a target band and a
persistence requirement that the current evidence cannot bound (A W14 reports
one session and no door-open event; the pairing tolerance is deliberately
`null`). It stays a secondary outcome until characterization. The primary is
**not** selected because it is easier to move; the definition is defensible
now and its numeric parameters are explicitly gated.

If later evidence shows that the representation or time base cannot support
the definition at all, that is an explicit freeze blocker. Changing the
primary is then a recorded amendment, not a silent substitution.

### 2.2 Secondary physical outcomes

| Outcome | Definition family | Why secondary | Numeric freeze |
|---|---|---|---|
| Recovery time | `T_rec = t_recovered − t_reference`; re-entry into a target band with persistence | Requires a reference, band and `τ_stable` that characterization has not produced; otherwise censored | F8: definition at W04; numeric reference/band/persistence before locked evaluation |
| Peak temperature | Maximum representative temperature in the outcome window | A severity indicator without duration; useful but not the primary harm integral | Predeclared with the outcome window |
| Time above critical | Seconds above `T_critical` | Related to exposure but not duration-weighted by magnitude; not interchangeable | F2 threshold value |
| Time above target | Seconds outside a target band | Depends on a target band; not a substitute for exposure | Target band freeze |
| Cooling-branch energy | `E_Wh = Σ P_i Δt_i / 3600` over the cooling branch | A cost/trade-off outcome, not a thermal-safety outcome; only valid with qualified electrical coverage | F11: integrated power primary; counter cross-check only; PWM quantitative use provisional |
| Critical excursion count | Count of qualifying excursions | Event burden, not severity; event definition depends on F2 | F2/event definition |
| False-warning burden | Episodes per eligible run/hour | Predictive operational burden, not a physical outcome | F5 operating threshold/persistence |

**These outcomes are not interchangeable.** Thermal exposure, recovery time,
branch energy, peak temperature and false-warning burden answer different
questions with different units, denominators and physical meanings. No
composite scalar score may replace the hierarchy.

### 2.3 Diagnostic and exploratory outcomes

- Cooling-health states (`HEALTHY_RESPONSE`, `ELECTRICAL_RESPONSE_MISSING`,
  `THERMAL_EFFECTIVENESS_DEGRADED`, `CONTROL_ELECTRICAL_ANOMALY`, `UNKNOWN`):
  diagnostic families, not primary physical outcomes.
- Spatial gradient / probe disagreement: a diagnostic state signal; on the
  current rig the all-slot spread includes the hot side and is not a
  chamber-air spatial gradient.
- SHAP values, feature importance and future model diagnostics: explanatory
  tools. **They do not establish physical causality.** A feature-attribution
  pattern is not a controlled physical experiment and cannot promote a
  diagnostic to a primary outcome.

### 2.4 Paired improvement and sign convention

For lower-is-better outcomes:

```text
I_i = Y_A,i - Y_B,i
```

Positive `I_i` means Controller B improved the outcome. Every report shows the
raw `Y_A,i`, `Y_B,i` and `I_i`. Relative reduction `1 − Y_B/Y_A` is reported
only when the denominator is meaningful and not negligible. Higher-is-better
metrics must state their orientation explicitly and never reuse this reading.

### 2.5 Statistical unit, population and aggregation

| Element | Frozen choice |
|---|---|
| Physical comparison unit | One valid matched Controller A/B pair (`pair_id`) = one `I_i` |
| Population | P5 matched physical runs; arms role-disjoint from P1–P4 |
| Aggregation | Per-run outcome → one paired difference per valid pair; raw arms always reported |
| Invalid pair | Contributes 0 pairs; listed with reason; never rescued or re-matched post hoc |
| Predictive unit | P1/P2/P3 grouped runs; windows are dependent |
| Offline EWT unit | P4 trajectories, per event, non-intervened only |
| Excluded runs | P6, listed with reason, never silently dropped |

Rows, windows, QoS re-deliveries and repeated export views are never counted as
independent pairs or runs.

### 2.6 Missing and undefined policy (physical side)

- Thermal exposure: missing span excluded, coverage reported, no
  interpolation, no zero-fill, predeclared coverage floor; below floor →
  invalid for `E_T`.
- Recovery: not recovered before termination → censored/non-recovered, never
  a finite recovery time; report the censoring time and the predeclared
  survival/exclusion rule.
- Branch energy: missing PZEM = missing span, never zero; counter resets are
  segmented and logged; unresolvable spans invalidate the run for energy, with
  a predeclared per-outcome rule for thermal outcomes.
- Peak/time-above: same span/coverage rules as their source series.
- False-warning burden: denominator is eligible runs or eligible hours; no
  event runs contribute burden, not recall.
- Invalid A/B arms are excluded before outcome computation; valid-but-unusable
  numeric coverage is not "zero".

### 2.7 Freeze trigger, owner and interpretation limit

- **Hierarchy freeze trigger:** this W04 document, before A/B outcomes exist.
- **Owner:** Member B; A and D co-own measurement/physical inputs and the
  pre-campaign freeze.
- **Pre-campaign freeze:** primary outcome, sign convention, CI level,
  bootstrap seed/iterations, test family, invalid-pair handling and secondary
  outcomes are recorded in the statistical analysis freeze (Doc `03` §133).
- **Post-result:** no silent promotion or unit change. A promotion is a
  recorded amendment and is labeled exploratory.
- **Interpretation limit:** the primary physical outcome is a testbed research
  outcome, not a regulatory, food-safety, commodity-quality, whole-system
  energy or component-level causal claim. Safety violations trump statistical
  success.

---

## 3. Freeze ledger — W03 F1–F12 reconciled with W04

| # | W03 item | W04 decision | Classification | Remaining gate / owner |
|---|---|---|---|---|
| F1 | Representative temperature (Tmax/Tmean/named probe) | Definition/interface frozen: role-qualified chamber-air representative; hot-side/non-air roles excluded; numeric choice remains open | Frozen definition / provisional value | Choice frozen before final-split labels and locked evaluation (`03` §§42–43, 69); B with A |
| F2 | `T_critical` / `T_limit` values | Not set. W04 freezes that it is a testbed research boundary, separate from the ML decision threshold | Provisional | Numeric value before locked evaluation (`03` §42, §180); B with A/D |
| F3 | `T_reactive` semantics for offline EWT | EWT semantics and missing-state policy frozen in `analysis-contract-v1.md` §4; numeric reactive threshold remains D-owned | Frozen semantics / provisional value | D policy; W15 |
| F4 | Primary horizon (30/60/120/300 s candidates) | Not set | Provisional | B horizon freeze W13 (`05B` §41) |
| F5 | Operating threshold + persistence/episode gap | Rule shape frozen (dev-selected operating point, persistence, episode grouping); numbers not set | Frozen shape / provisional value | B/D policy freeze W15 (`05B` §43; `03` §§87–88) |
| F6 | Initial-condition tolerances | Not set; pairing tolerance is `null` in A W14 because one session cannot estimate a spread | Provisional | A/B pilot → pre-A/B freeze (`03` §§34–35) |
| F7 | AIW timing inputs | Interface and missing-data rule frozen; no measured component, distribution or AIW value produced | Frozen interface / TEAM_DEPENDENCY | A/C/D measurement freeze (`03` §57); W06 alignment |
| F8 | Recovery reference / target band / persistence | Recovery-time definition/family frozen as secondary; numeric reference/band/`τ_stable` not set | Frozen definition / provisional value | Numeric values before locked evaluation (`03` §70); B with A |
| F9 | Primary outcome selection | **Primary physical outcome = thermal exposure, lower is better; primary predictive metric = AP** | Frozen hierarchy | Numeric F1/F2 values remain gated |
| F10 | Minimum engineering-relevant improvement | Not set | Provisional | Pre-A/B, B with A/D (`03` §82) |
| F11 | Energy-counter vs integrated-power semantics | Integrated sampled power is the primary branch-energy computation; the 1 Wh counter is a cross-check with reset handling; PWM quantitative energy remains provisional | Frozen interface / provisional numeric use | A characterization (`03` §72; `01` §9.10, §35) |
| F12 | Full events/command-timeline schema | Not implemented; intake relies on A's export/index fields only | TEAM_DEPENDENCY / SCHEDULED_DEBT | C W07 semantics (`02` §14.4) |

### 3.1 Freeze classes

1. **Frozen conceptual definitions:** thermal exposure, recovery time family,
  EWT, AIW, AP, precision/recall, warning episodes, missed events, branch
  energy, score vs probability.
2. **Frozen analysis interface:** source representations, normalized fields,
  admission states, EWT/AIW states, timing provenance, missing-data rules.
3. **Frozen outcome hierarchy:** AP primary predictive; thermal exposure
  primary physical; the secondary/diagnostic lists; `I_i = Y_A − Y_B`.
4. **Provisional empirical values:** representative temperature, `T_limit`,
  horizon, operating threshold, persistence/episode gap, initial-condition
  tolerances, recovery band, minimum improvement, coverage floor, response
  delays.
5. **A/C/D team dependencies:** valid run IDs and reasons, hardware-config
  signoff, calibration, door events, qualified PZEM, clock sync, event/
  command timeline, policy/reactive semantics.
6. **Future named freeze gates:** W13 horizon; W14 calibration/score
  semantics; W15 threshold/policy and model; W16 locked test/model release.
  These remain scheduled; W04 does not pull them forward.

---

## 4. Cross-document consistency

| Check | Result |
|---|---|
| Same metric names, units and populations as `statistical-analysis-plan-v0.md` and `metric-spec.md` | Yes: AP, precision/recall, false-warning episodes, missed events, EWT, thermal exposure, recovery, branch energy; P1–P6; paired `I_i` |
| `claim-data-matrix.md` | RQ2/RQ4 families unchanged; W04 resolves its exposure-unit/primary-outcome PROVISIONAL placeholders as °C·s and thermal exposure |
| AP vs trapezoidal PR-AUC | Explicitly distinguished and enforced |
| P1/P2/P3 disjointness | Unchanged; W04 opens no split |
| EWT vs A/B outcomes | Separate populations; no naive EWT from Controller B |
| Missing PZEM as zero | Forbidden |
| Score vs calibrated probability | Score-only default; calibration gate W14 |
| Hot-side as chamber air | Forbidden; role-qualified representation required |
| Premature horizon/threshold freeze | None; F1/F2/F4/F5/F8/F10 stay gated |
| AIW when measured latency missing | `NOT_ESTIMABLE`, never a nominal substitute |
| CLI admission vs documentation | The schema checker reports the same ladder and the same current 0/0/NOT_READY result described in `analysis-contract-v1.md` §2.11 and §3.5 |

No new threshold, probability, result or model performance is computed or
claimed by this hierarchy.

---

## 5. Handoff

- **W05:** telemetry QA supplies cadence, completeness, missingness and
  coverage facts; the coverage floor for `E_T` is derived from that evidence
  and frozen before the A/B campaign.
- **W08:** the full Gate B validator consumes the admission result; W04 is not
  a substitute.
- **W13:** primary horizon freeze. **W14:** calibration/score-semantics
  freeze. **W15:** operating threshold/persistence and model freeze.
  **W16:** locked test/model release.
- **A:** valid run IDs/reasons, hardware-config signoff, calibration, door
  events, qualified PZEM, measured response distributions.
- **C:** event/command timeline, clock sync, export provenance.
- **D:** reactive threshold semantics, policy/operating decisions, command
  timing.

*Hierarchy ends. The primary metric and physical outcome are frozen; the
physical values that are not yet measured are explicitly gated, not
invented.*
