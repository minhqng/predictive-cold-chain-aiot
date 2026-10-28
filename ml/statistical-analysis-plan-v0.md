# ColdGuard · Statistical Analysis Plan v0 (W03, Member B)

> Deliverable of **B-W03-01** (independent units + populations) and
> **B-W03-03** (paired Controller A/B inference), Doc `05B` §31.
> Methodology contract only: it freezes *how* future runs and pairs are
> admitted, compared, and reported. It ships no data, trains no model, and
> computes no ColdGuard result. Companions: `metric-spec.md`,
> `scripts/sample_size_planning.py`, W01 contracts, W02 pipeline modules.

| Field | Value |
|---|---|
| Owner | Member B |
| Parent docs | `00` §§5.3–5.4 · `01` §§1, 18, 33, 38–39, 45 · `03` §§1.4–1.6, 8, 12, 31–49, 57–60, 74–83, 133, 204 · `04` §§3.3, 10 · `05B` §§2–3, 7–8, 12–13, 24, 26–27, 29, 31–32 |
| Tasks | B-W03-01, B-W03-03 |
| Status | v0 methodology draft; analysis freeze gate is W04 (`05B` §32) |

Tier legend: **CANONICAL** (Docs `00`–`03` fix it) · **DERIVED** (follows
from CANONICAL + a stated assumption) · **IMPLEMENTATION_CHOICE** (B's
executable-documentation choice, no statistical meaning change) ·
**TEAM_DEPENDENCY** (A/C/D-owned input, never invented by B) ·
**PROVISIONAL_UNTIL_FREEZE** (unset parameter + named gate in §10; never a
measured fact) · **SCHEDULED_DEBT** (deferred mechanics, owner + week).

> **W03/W04 boundary** (CANONICAL, `05B` §31 vs §32). W03 freezes the
> mathematical contract. Every threshold, horizon, constant, and campaign
> parameter not yet measured stays PROVISIONAL_UNTIL_FREEZE (§10). W04
> performs the evaluation/measurement freeze.

---

## 1. Independent statistical units (B-W03-01)

### 1.1 Three distinct units (CANONICAL: `03` §47; `00` §5.3)

| Unit | Role | Independent? |
|---|---|---|
| Telemetry row / feature window | Dependent observation nested in a run | **No** — rows and overlapping windows in one run are correlated |
| Physical experimental run (`run_id`) | Primary grouped predictive-evaluation unit | **Yes, conditionally** — one run counts once, subject to §3 admission; same-rig repeats carry session dependence (§5) |
| Matched Controller A/B pair (`pair_id`) | Final physical comparison unit | **Yes** — one valid pair contributes exactly one paired improvement |

DERIVED consequences:

1. A 60-minute 1 Hz run (≈3 600 rows) is **one** grouped run, not 3 600
   experiments. Thousands of overlapping windows add **zero** inferential
   degrees of freedom beyond that run (W02 `windows.py` observations).
2. A paired A/B observation is **one** paired difference from two matched
   arms — never two independent treatment samples.
3. Sample-size planning counts **independent matched pairs**; row/window
   counts must never enter a power formula.

### 1.2 Worked unit-counting examples (DERIVED, illustrative — not real data)

- *One run, thousands of windows.* `CG-S2-A-001` yields 3 400 causal
  windows → grouped N contribution = **1 run**. Holdout support reports
  "1 run / 3 400 dependent windows", never "N = 3 400".
- *Five dependent runs, one session.* Five S2 runs back-to-back on one rig
  = **5 grouped runs** with noted session dependence; pair arms stay
  together in any split (W02 pair-group rule, `03` §123).
- *One invalid A/B arm.* Pair `P-007`, arm B with an A-ledger fault entry
  (`01` §33) → pair contributes **0 pairs** to the primary analysis (§8).
- *Shared/mismatched `pair_id`.* Arms sharing a `pair_id` across scenarios,
  or intended pairs with divergent ids, are **inadmissible as a pair**
  until source identity is repaired. B never reassigns `pair_id` post hoc.
- *Unreliable provenance.* Missing calibration identity or INVALID overall
  quality (dictionary §9) → run excluded from every population with its
  reason recorded, never repaired or down-weighted into inclusion.

## 2. Evaluation populations (B-W03-01)

Six populations (CANONICAL structure, `03` §§45–49, 87–93; `05B` §§12–13):

| # | Population | Contents | May a run also appear elsewhere? |
|---|---|---|---|
| P1 | Training / development | `train`/`validation` runs; all windows, scalers, thresholds, calibration derive here | Exactly one of P1/P2/P3 per run (split disjointness). P1 artifacts are *applied* downstream, never refit there |
| P2 | Grouped predictive validation | Held-back runs for model/horizon selection | Disjoint from P1/P3 at run level; development use only |
| P3 | Locked predictive holdout | Runs under `locked_test` discipline (`03` §49; convention §3.2): opened once, analyzed under the frozen plan | Disjoint from P1/P2. Re-viewing or re-selecting after opening converts the analysis to exploratory (LRK-11) |
| P4 | Non-predictively-intervened trajectories (offline EWT) | Reactive/observational runs replayed offline for EWT | A P1–P3 run may supply a P4 trajectory only with non-predictive controller context (LRK-09) and past-only replay. P4 is offline-warning evidence, never a closed-loop outcome |
| P5 | Matched physical Controller A/B runs | Valid pairs per §8; primary closed-loop population | Role-disjoint from P1–P4: a final A/B arm must not train/validate the model under test (`03` §45). Pair arms stay together in any split |
| P6 | Excluded / invalid runs | Runs failing §3 admission | In no other population; listed with reasons in every report (§7) |

Contamination rules (CANONICAL):

- **Never** combine offline EWT (P4) with closed-loop A/B outcomes (P5) as
  one counterfactual (`03` §45; matrix RQ3/RQ4). P4: "would the warning have
  preceded the reactive crossing unintervened?". P5: "did predictive control
  improve the physical outcome?". Different questions.
- **Never** train/select on P3 or final P5 arms and report the same data as
  unbiased evidence (LRK-06/07/11).
- **Never** admit `CENSORED`/`UNTRUSTED_INFO` labels as clean negatives;
  only `EVALUABLE` labels enter supervised denominators (metric-spec §1).

## 3. Run and pair identity — admission contract (B-W03-01)

### 3.1 Required identities (CANONICAL reuse — B invents none)

`run_id` (`CG-S<scenario>-<arm>-<serial>`), `scenario_id` (S1–S6),
controller arm / `controller_id`, `pair_id` (set iff a claimed A/B arm),
`hardware_config_id` (`CG-HW-…`), `calibration_id` (`CG-CAL-…`),
`device_id`/`boot_id`/`firmware_version`, experiment protocol version
(TEAM_DEPENDENCY — A/C schema), timing provenance (event vs arrival,
boot-scoped order; LRK-13), quality provenance (per-section
VALID/DEGRADED/INVALID + absent counts; dictionary §9), exclusion reason
(`invalid_reason` verbatim from A's ledger). Unimplemented C/A/D schemas
(full `events` timeline, command linkage, latency components) stay
TEAM_DEPENDENCY with owner + gate — never treated as available.

### 3.2 Run admission checklist (verify per candidate run)

1. `run_id` pattern-valid, resolved in the dataset manifest `source_runs`
   (convention B1). 2. Scenario/protocol/hardware/calibration consistent;
   single `hardware_config_id` per family unless an A-reviewed registered
   exception exists (convention B5; LRK-15). 3. `is_valid` true, no
   `invalid_reason`; otherwise P6 (`01` §33). 4. Timing intact: boot-scoped
   order, no cross-boot joins, event time present (`01` §18; LRK-13).
5. Quality intact: INVALID-overall sections excluded; missing PZEM = missing,
   never zero (LRK-14). 6. Controller context fits the population (LRK-09).
7. Coverage complete for the metric; incomplete → censored/excluded per
   metric-spec, never imputed.

### 3.3 Pair admission checklist (both arms +)

Same `pair_id` on exactly two arms; same scenario/protocol/disturbance
duration; same hardware + calibration lineage (`03` §35); initial conditions
within frozen tolerances (PROVISIONAL_UNTIL_FREEZE — pilot candidates
`|ΔTmean| ≤ ~0.5 °C`, `|Δgradient| ≤ ~0.3 °C`, `03` §35; final values freeze
pre-campaign); randomized recorded order (`03` §36); observed reset/recovery
(`03` §37; TEAM_DEPENDENCY A/D); comparable outcome definitions both arms;
full electrical coverage for energy outcomes. One inadmissible arm ⇒
**invalid pair**, 0 contribution to the primary analysis (§8).

    full electrical coverage for energy outcomes. One inadmissible arm ⇒
    **invalid pair**, 0 contribution to the primary analysis (§8).

## 4. Paired inference (B-W03-03)

### 4.1 Sign convention — frozen (CANONICAL recommendation, `03` §74)

Primary paired improvement for pair `i`:

```text
I_i = Y_A,i − Y_B,i
```

`Y_A,i`, `Y_B,i` = same physical outcome on the two arms under the same
definition. For **lower-is-better** outcomes (thermal exposure, recovery
time, branch energy where reduction is claimed):

```text
I_i > 0 → B improved · I_i = 0 → no observed difference · I_i < 0 → B worsened
```

Higher-is-better metrics must state their orientation explicitly and never
silently reuse this reading. Every report shows raw `Y_A,i`, `Y_B,i`
alongside `I_i`; relative reduction `1 − Y_B/Y_A` only with a
meaningful denominator (`03` §§73–74).

> `03` §74 defines the raw difference `d_i = Y_B − Y_A` (negative favors
> predictive when lower is better) then recommends freezing improvement
> `I_i = Y_A − Y_B` (positive favors predictive). This plan freezes the
> recommended improvement form; the two differ by sign only.

### 4.2 Blocking and randomization (statistical implications)

B designs the analysis; A/D own execution (TEAM_DEPENDENCY). Same
scenario/protocol + matched initial conditions make the pair a **blocking
factor** removing shared session variation. Valid lineage keeps the block
interpretable; lineage change breaks it (§8). Randomized recorded order
(`03` §36) guards drift bias. Observed reset/recovery (`03` §37) is what
makes "matched" credible — incomplete recovery invalidates the pair, with
no post-hoc covariate rescue. Only valid matched pairs enter the primary
analysis.

### 4.3 Descriptive statistics (predefined shell — no W03 results)

Valid-pair N; excluded-pair N + reasons; the N individual `I_i` (table +
plot of every pair — mandatory at small N, `03` §81); mean + median; SD
(with mean) / IQR (with median); descriptive `d_z = mean/SD`; 95% CI
(§4.4); paired before/after + improvement plots. No window/row-level plot
may stand as pair evidence.

### 4.4 Confidence intervals (primary 95% CI)

- **Default:** paired-sample t CI `mean ± t_{0.975,N−1}·SD/√N` when
  differences are approximately symmetric without severe outliers (`03`
  §76), with the diagnostic reading stated.
- **Robust alternative:** pair-level bootstrap percentile CI (§4.5) when
  symmetry is doubtful, N small, or outliers present (`03` §§77–78), with
  iterations + seed + small-N candor.
- **Degenerate cases:** constant differences (SD = 0) → report the
  constant + "CI undefined/degenerate", never a zero-width proof. N < 3 or
  bootstrap collapse → "CI not estimable" with reason.
- Exactly one CI is primary per outcome (frozen pre-campaign); any second
  method is a labeled sensitivity check. No method shopping.

### 4.5 Bootstrap discipline (CANONICAL, `03` §§78–79)

Resample **complete independent pairs** with replacement (N from N,
recompute, repeat). **Forbidden:** rows, windows, single arms,
cross-pair arm mixing, window-overlap N inflation — each voids the
interval. Final-analysis setting: **≥ 2 000 iterations, preferably
5 000–10 000** (`03` §79); seed recorded (convention §11). W03 documents
the choice; the bootstrap engine is SCHEDULED_DEBT (W04+, B).

### 4.6 Parametric vs nonparametric decision (predeclared)

| Method | Valid when | Reports |
|---|---|---|
| Paired t-test + t CI | Reasonably symmetric, no severe outliers | Mean diff, 95% CI, N, diagnostic note |
| Sign / permutation | Symmetry doubtful, within-pair exchangeability holds | Direction evidence; CI via bootstrap |
| Wilcoxon signed-rank | Symmetric-difference assumption specifically licensed (not a skew default) | Median-oriented summary + assumption note |
| Bootstrap CI (pair-level) | Always admissible as uncertainty alongside any above (§4.5) | 95% percentile CI, iterations, seed |

Primary method frozen pre-campaign on blinded/pilot shape only — never on
which p-value looks favorable. No method is promised significance. Failure
at analysis time falls back to the predeclared robust alternative (LRK-17).

Primary method frozen pre-campaign on blinded/pilot shape only — never on
which p-value looks favorable. No method is promised significance. Failure
at analysis time falls back to the predeclared robust alternative (LRK-17).

### 4.7 Invalid and incomplete pairs (CANONICAL, `03` §38)

The following make a pair **invalid for the primary analysis** (pair
contributes 0 pairs; both arms excluded from P5): one arm missing /
interrupted; one arm physically invalid (A ledger, `01` §33); corrupted
sensor provenance either arm; unmatched initial conditions beyond frozen
tolerances; incomplete recovery between arms; changed hardware/calibration
lineage between arms; missing electrical coverage either arm (for
energy-involving outcomes).

Handling: invalid pairs are **listed with reasons**, never silently
dropped; failed arms are **never replaced** with unrelated future runs and
pairs **never re-matched** post hoc; per-outcome partial inclusion (e.g.
thermal survives where only energy coverage failed) must be predeclared
pre-campaign — undeclared partial inclusion is post-hoc analysis. Primary
N = fully valid pairs; any sensitivity N reported separately with its rule.

### 4.8 Multiple outcomes and limitations

**Primary outcome(s)** frozen pre-campaign from {thermal exposure,
recovery time} with the representative/reference choices of metric-spec
§§6–7 (PROVISIONAL_UNTIL_FREEZE, §10; gate: W04 evaluation freeze, `05B`
§32). **Secondary outcomes** (peak, time-above, branch energy, warning
burden) use the same paired machinery but stay secondary — no post-result
promotion. **Exploratory** work is labeled exploratory with post-hoc status
disclosed (`03` change policy: post-lock changes need an explicit
amendment). No metric/horizon shopping, no repeated holdout peeking
(LRK-07/11/17). Uncertainty and limitations are reported **even under a
null result** — a null with a correct CI is a successful verification
outcome (`03` verification thesis).

## 5. Dependence and pseudoreplication (B-W03-01)

- *Same-apparatus repeats* share rig/session context: note the session
  layer, randomize order, never present within-session replication as
  multi-site evidence. - *Matching* is deliberate dependence — analyze one
  `I_i` per pair, never 2N arms as independent samples. - *Overlapping
  windows* (W02 construction): window-level resampling/CIs/N are
  pseudoreplication. - *Within-run correlated events*: aggregate events
  within runs first (metric-spec §3). - *Order/drift* (ambient, residual
  heat): randomization (§4.2) + reset criteria (TEAM_DEPENDENCY A/D) +
  recorded order; drift-corrupted pairs excluded via §4.7, not modeled
  away. - *Reassembly/relocation* breaks lineage: same
  `hardware_config_id` per family (convention B5) or a new family with its
  own plan instance. - *Hierarchy* run ⊂ session ⊂ hardware-config:
  primary analysis at pair level within one family; cross-family pooling
  needs a predeclared hierarchical model — SCHEDULED_DEBT, not W03/W04.

## 6. Metric bindings (identical names/units in both W03 documents)

| Metric | Unit | Population | Aggregation |
|---|---|---|---|
| AP | [0, 1] | P1/P2/P3, EVALUABLE only | run-grouped; report runs + windows + prevalence |
| Precision / recall | [0, 1] | same, frozen threshold | sample-level + denominators; event companion |
| False-warning episodes | episodes / eligible run (+/hour) | P2/P3 (+P4 replay) | within-run episodes → per-run rate |
| Missed events | count + event recall | same | events within runs; runs first |
| EWT (offline) | seconds | P4 only | per-event median + distribution |
| AIW support | seconds | P4 trajectories × measured inputs | per-event, only when inputs known |
| Thermal exposure | °C·s (or °C·min, frozen) | P5 pairs | per-run → paired `I_i` |
| Recovery time | s (or min, frozen) | P5 pairs | per-run → paired `I_i` |
| Branch energy | Wh | P5 pairs, valid coverage | per-run → paired `I_i` |

Censored/untrusted labels never enter denominators; missing PZEM never
enters as zero; B-controlled trajectories never supply naive EWT. Formulas
and hand-calculated examples live in `metric-spec.md`.

Censored/untrusted labels never enter denominators; missing PZEM never
enters as zero; B-controlled trajectories never supply naive EWT. Formulas
and hand-calculated examples live in `metric-spec.md`.

## 7. Reporting shell (frozen — instantiated once per outcome, W04+)

Population table (P1–P6 counts + pair/run flow with reasons); exclusion
table (every P6 entry with rule citation); method statement (primary CI,
bootstrap setting, test choice with assumption license); descriptives
(§4.3) with raw arms + `I_i` table/plot; primary 95% CI + interpretation
(magnitude/direction/uncertainty — never bare "significance");
sensitivity/exploratory section (labeled, post-hoc disclosed); limitations
(dependence, N honesty, provisional citations); provenance
(dataset/split/manifest ids, seeds, code version, freeze-gate citations).

## 8. Invalid-pair operator card

A pair is **VALID** iff every box ticks, else invalid per §4.7 (0 pairs,
listed with reason, never rescued post hoc):

```text
[ ] both arms present and complete
[ ] both arms physically valid (no A-ledger invalid reason)
[ ] same pair_id on exactly these two arms
[ ] same scenario / protocol / disturbance duration
[ ] same hardware_config_id + calibration lineage
[ ] initial conditions within frozen tolerances
[ ] controller order randomized and recorded
[ ] reset/recovery observed between arms
[ ] comparable outcome definitions both arms
[ ] electrical coverage complete (energy outcomes)
```

## 9. Traceability to W01/W02

`run_id`/`pair_id`/grouping → `splitting.py` (`RunInfo`, pair-group rule,
`group_of`); manifest shapes → `manifests.py` + convention §§2–5; window
dependence → `windows.py`; label statuses → `labels.py`; quality/missingness
→ dictionary §§9, 13; leakage guards → register LRK-01–17 (notably LRK-08
pair blocking, LRK-09 intervention exclusion, LRK-11 lock discipline,
LRK-14 missing≠zero, LRK-17 freeze binding). W03 assumes W02 provenance
supplies §3 identities; inputs needing unimplemented C/A/D schemas stay
TEAM_DEPENDENCY, never silently available.

## 10. Provisional-until-freeze ledger

| # | Item | Gate / owner |
|---|---|---|
| F1 | Representative temperature (Tmax/Tmean/named probe) | B evaluation freeze W04 (`03` §§42–43, 69) |
| F2 | `T_critical`/`T_limit` values | B evaluation freeze W04 (`03` §42) |
| F3 | `T_reactive` semantics for offline EWT | B evaluation freeze W04 (`03` §§44, 84) |
| F4 | Primary horizon (candidates 30/60/120/300 s) | B horizon freeze W13 (`05B` §41) |
| F5 | Operating threshold + persistence/episode gap | B/D policy freeze W15 (`05B` §43) |
| F6 | Initial-condition tolerances (final numerics) | A/B pilot → pre-A/B freeze (`03` §§34–35) |
| F7 | AIW timing inputs (measured components) | A/C/D measurement freeze (`03` §57) |
| F8 | Recovery reference / target band / persistence | B evaluation freeze W04 (`03` §70) |
| F9 | Primary outcome selection | B evaluation freeze W04 (`05B` §32) |
| F10 | Minimum engineering-relevant improvement | Pre-A/B, B with A/D (`03` §82) |
| F11 | Energy-counter vs integrated-power semantics | A characterization + B W04 (`03` §72) |
| F12 | Full events/command-timeline schema | C W07 semantics (TEAM_DEPENDENCY) |

## 11. Adversarial self-check (contract blocks each attack)

10 000 windows as N → §1 (0 inferential N; runs reported). Two arms as
two pairs → §§1/4.2/5 (one pair = one `I_i`; two-sample forbidden).
Negative improvement as benefit → §4.1 + raw-values rule. Invalid arm
kept → §§3–4.7 + §8 card (0 pairs, listed). Non-recovery as finite time
→ metric-spec §7 (censored, never finite). Missing-telemetry guess →
metric-spec §§1–3 (EVALUABLE only). PZEM-missing as zero → §3.2 +
metric-spec §8 (excluded span). B-trajectory EWT → plan §2 + metric-spec
§4 (inadmissible; voids estimate). AP as physical proof → §§2/6
(AP is P1–P3; proof is P5). Downward rounding → script `ceil` + floor 2.
Post-data outcome shopping → §4.8 + LRK-17 (frozen primary; post-hoc =
exploratory + amendment).

## 12. Handoff and scheduled debt

B owns this contract, `metric-spec.md`, the planning script + tests. A
owns sensing, calibration, validity, disturbance, thermal timing, energy
validity. C owns exports, metadata, event timestamps, quality, linkage.
D owns reactive semantics, applied state, frozen threshold/persistence,
command timing. SCHEDULED_DEBT: real bootstrap-CI + actual A/B analysis
code (W04+, B); hierarchical cross-family model (conditional);
hash-recompute checker (convention §9). A/C data-facing review of W01–W03
pending by explicit operator choice (`04` §3.3) — recorded, never
auto-requested.

---

*Plan ends. No dataset, threshold, probability, result, or model
performance is computed or claimed — the mathematics above is the
contract future data will be judged against.*




