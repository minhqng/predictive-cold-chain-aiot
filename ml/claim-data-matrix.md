# ColdGuard · Claim → Data Mapping (W01, Member B)

> Deliverable of task **B-W01-01** (Doc `05B` §29).
> Contract document: it states how each research question maps to concrete data, the unit
> of independence, the analysis method, and the evidence that would **falsify** the claim.
> It ships no data, trains no model, and freezes no thresholds.

| Field | Value |
|---|---|
| Owner | Member B |
| Reviewer focus | Dataset/split reviewer: A or C (Doc `04` §3.3) |
| Parent docs | Doc `00` §0.3–0.4, §§1.4, 3.1–3.11, 5.1–5.4 · Doc `01` §§1, 6, 16, 20, 22–25, 33–35, 39, 43 · Doc `02` §§13.3, 14.3–14.4, 14.6, 19.7, 22, 31, 37–39, 51 · Doc `03` §§1.4–1.6, 7, 10, 15, 17, 31–33, 41–103, 105–106, 116, 124, 126–127, 129–133, 159, 162, 182, 204 · Doc `04` §§3.3, 10.2, 10.4–10.6, 16 · Doc `05B` §§2–3, 10, 12, 20, 26, 29, 31–32 |
| Task ID | B-W01-01 |
| Companion files | `data-dictionary-v0.md`, `leakage-risk-register.md`, `artifact-convention.md` (same folder) |

## Status tier legend (shared by all four W01 contract files)

- **CANONICAL** — fixed by Docs `00`–`03`. Member B restates it; B must not redefine it. Resolves to an explicit Docs `00`–`03` section.
- **DERIVED** — computed downstream from CANONICAL inputs under a versioned formula (`feature_version`). The formula choice is a versioned engineering decision, not a new physical fact.
- **PROVISIONAL** — owned by a later, predeclared freeze (B or team). The current candidate value is a plan, not a result; it must never be used as a measured or agreed fact.
- **TEAM_DEPENDENCY** — depends on another member's delivered/committed artifact. Recorded here verbatim with its source path; not B-owned, not re-derived by B.
- **SCHEDULED_DEBT** — deliberately deferred to a named later week with an owner. Not neglect; a recorded handoff.

Docs `00`–`03` outrank all playbook-level statements: Doc `05B`'s own header (Non-authority rule) says that if it conflicts with Docs `00`–`04`, the parent document wins, and `05B` must not redefine hardware/physical semantics (`01` is the measurement-contract authority).

---

## 1. Claim vocabulary ordering the mapping

Every row below depends on five vocabulary distinctions fixed by Doc `01` §1 (CANONICAL):

| Distinction | Canonical anchor | Why it matters for claims |
|---|---|---|
| Physical fact vs observed state | `01` §1.1–1.2 | Sensor readings are observations, not raw physical facts; claim wording must respect this. |
| Commanded vs applied state | `01` §1.3–1.4 | Control claims (RQ4) use **applied** state, not command intent (see `data-dictionary-v0.md` §10). |
| Electrical vs thermal response | `01` §1.5–1.6 | RQ3 separates "branch drew current" (PZEM) from "chamber responded" (DS18B20). |
| Verified physical action | `01` §1.7 | A cooling intervention is only *verified* after independent electrical + thermal evidence. |
| Independent unit = run, not row | `00` §5.3, `03` §1.5 | All grouped evaluation maps `group = run_id` (`leakage-risk-register.md` LRK-01/02). |

---

## 2. RQ → data map (six research questions, incl. conditional RQ6)

Sources: Doc `00` §0.3 (claim text) and §0.4 (hypotheses, minimum acceptable evidence). Claim wording is CANONICAL; B paraphrases minimally and never strengthens it.

### RQ1 — Thermal observability ↔ H1

- **Claim** (CANONICAL, `00` §0.3): multi-point sensing provides useful state information beyond a single temperature sensor.
- **Target/outcome**: measurable difference in state characterization and/or predictive usefulness between one-designated-temperature and three-probe feature sets (`03` §61). Not a new target variable — an ablation contrast on the same prediction task.
- **Required channels** (dictionary §4): `t1_c`, `t2_c`, `t3_c` + DERIVED spatial features (Tmean/Tmin/Tmax/gradient std, `01` §20; `05B` §3.2, §10.1) + `thermal_quality`. Door/environment context held comparable per `03` §62 (A2 pairing).
- **Independent unit**: `run_id` (grouped; `00` §5.3). Ablations use the SAME split as the core model so results are comparable (`03` §61: "Same model family/split").
- **Analysis method**: A1a vs A1b ablation (`03` §61); grouped evaluation semantics (GroupKFold/GroupShuffleSplit keep groups non-overlapping — `03` §47, `03` §204 [R5]); pre-frozen feature_version pair; effects reported with run-grouped distributions, not a single fold (`03` §81 style, `05B` §27).
- **Evidence family**: `SEN-H1-03` inter-sensor consistency commissioning record (`03` §15) + ablation delta on grouped folds + dataset card (`03` §126).
- **Falsifier** (`00` §0.4 H1): A1 ablation shows no measurable difference in either state characterization or predictive usefulness across grouped folds. Plain negative result is reportable (`00` §0.4 closing rule, `03` §1.6).
- **Tiers**: feature *roster* DERIVED (versioned later); split shape PROVISIONAL (`03` §48 planning envelope); ROM↔role map TEAM_DEPENDENCY (A's ROM map, `01` §6.5, `04` §10.2).

### RQ2 — Early predictive usefulness ↔ H2, H3

- **Claim** (CANONICAL, `00` §0.3): past-only temporal features + a practical ML model identify an impending critical thermal state **earlier** than threshold/hysteresis monitoring on held-out independent runs.
- **Target/outcome**: binary critical-crossing-within-horizon label `y_t(H)` (CANONICAL formula, `03` §41); boundary/label-episode semantics (boundary window, label gap handling) are PROVISIONAL label-spec items, frozen before final splits (`03` §45, §49). `T_critical`, representative temperature (Tmax/Tmean candidate), and horizon H are PROVISIONAL (`03` §42–44: frozen before locked evaluation; never chosen post-hoc by score).
- **Required channels** (dictionary §3–§9): `t1_c/t2_c/t3_c`, `t_air_c`, `rh_pct`, `door_state` + door context features, applied-state + electrical context (`cooling_*`) as *past-only* inputs (LEAKAGE boundary: `leakage-risk-register.md` LRK-03/04), per-section `*_quality`, time semantics (§3).
- **Independent unit**: `run_id`; windows generated **only inside** an already-computed split (`03` §46–47; `05B` §12).
- **Analysis method**: B0/B1/B2 baselines vs XGBoost M1 (`03` §51); grouped split before any windowing (`05B` §12); AP primary candidate (`03` §52, `05B` §20, `03` §204 [R6][R7]); supporting precision/recall/F1/false-warnings-run/missed events (`03` §53, §89–91); **EWT** = `t_reactive − t_predictive` on reactive/observational trajectories only (`03` §55); calibration only if probability is claimed (`03` §58–60); score-only wording otherwise (`03` §59, `02` §19.7).
- **Evidence family**: locked-test result table (`03` §92, §129), label audit spot-plot set (`03` §124), model card (`03` §127), EWT distribution.
- **Falsifier** (`00` §0.4 H2/H3): held-out EWT not positive for a meaningful fraction of valid events (the "meaningful fraction" is deliberately unfrozen until the W03/W04 metric freeze — PROVISIONAL), or missed-event/false-warning behavior worsens versus B0/B1 baselines, or the warning is not actionable (AIW ≤ 0 for the event subset claimed, `03` §56).
- **Tiers**: intervention-free (reactive/observational) training runs are required by definition (`03` §45); the *run-count envelope* (~8 pilot / ~24 predictive-dev / ~24–32 valid A/B runs, candidate ~16/4/4 split) is PROVISIONAL planning context only (`03` §§10, 48).

### RQ3 — Actuator observability and diagnosis ↔ H5

- **Claim** (CANONICAL, `00` §0.3): adding command + cooling-branch current/power + thermal response improves distinguishing "cooling requested" from "cooling physically effective".
- **Target/outcome**: verified-cooling-response classification families (`01` §22–§23): HEALTHY_RESPONSE / ELECTRICAL_RESPONSE_MISSING / THERMAL_EFFECTIVENESS_DEGRADED / CONTROL_ELECTRICAL_ANOMALY / UNKNOWN (`03` §103 DIAG family; cooling-health states in `01` §23).
- **Required channels** (dictionary §7–§8): `applied_cooling`, `cooling_current_a`, `cooling_power_w`, `cooling_voltage_v`, `cooling_energy_counter_wh`, DS18B20 responses, plus command record fields (§10) for intent-vs-applied alignment.
- **Independent unit**: verified actuation episodes inside runs; each verification anchored to (command_id → applied state → electrical response → thermal response) chain (`01` §1.7).
- **Analysis method**: A3a vs A3b ablation (`03` §63) + controlled DIAG-01..04 cases (`03` §103) + electrical-state transition checks (`01` §22); probability wording only if calibrated (`03` §59).
- **Evidence family**: DIAG campaign evidence (`03` §103) + A3 ablation delta + PZEM ELEC-H3 commissioning records (`03` §17).
- **Falsifier** (`00` §0.4 H5): electrical channels add no additional discrimination/verification value in controlled comparisons. **Boundary** (CANONICAL, `00` §0.3 RQ3 rule): ColdGuard must **not** infer a component-specific root cause that the sensors cannot prove; diagnoses stay at the response-family level.
- **Tiers**: OFF-envelope and healthy current/power ranges are commissioning-derived (CG-OE values PROVISIONAL, `01` §39.3); PWM-based quantitative use is PROVISIONAL/conditional (`01` §34, `00` §3.11, `03` §102).

### RQ4 — Closed-loop intervention ↔ H4

- **Claim** (CANONICAL, `00` §0.3): under matched disturbances, predictive intervention improves **at least one** physical outcome (thermal exposure, recovery time, critical excursion occurrence/severity) versus reactive threshold control.
- **Target/outcome**: primary physical outcome1 = thermal exposure `E_T` (`03` §68; unit °C·s or °C·min — unit choice PROVISIONAL at statistics freeze, `03` §133); outcome2 = recovery time `T_rec` with frozen reference band + persistence requirement (`03` §70, §179); supporting outcome: critical excursion counts (`03` §100). Either H_AB1 or H_AB2 may be primary — frozen before the campaign (`03` §99); both need not win (CANONICAL).
- **Required channels**: full run telemetry (dictionary §3–§9) + command record + pairing metadata (pair_id, block, order, randomization record — `03` §95, §162) + run validity ledger (`03` §7). Energy context from cooling-branch only (`00` §3.10).
- **Independent unit**: **one A/B pair**, never a telemetry row (`03` §75; `05B` §2.1). Pair failure handling predeclared (`03` §96).
- **Analysis method**: paired difference `I_i = Y_A,i − Y_B,i` (positive favors predictive; convention frozen) (`03` §74); primary effect with 95 % CI; bootstrap resamples **pairs, not rows** (`03` §78–80, `03` §204 [R4]); paired t only if assumptions reasonable, else permutation/sign-based (`03` §76–77); no metric shopping (`03` §83); minimum engineering-relevant improvement declared pre-campaign (`03` §82); energy trade-off interpreted against exposure, never as a single scalar score (`03` §101).
- **Evidence family**: final A/B table + raw pair trajectories (`03` §130, §131); campaign log & pair randomization record (`03` §159, §162).
- **Falsifier** (`00` §0.4 H4): the single frozen primary outcome does not improve (CI excludes the frozen minimum-relevant improvement) or any safety invariant is violated during B runs. Safety violation trumps statistical success (hierarchy: `02` §22, `01` §25).
- **Tiers**: controller-side thresholds/duty/safety limits are D-owned, frozen before final A/B (`03` §97; B supplies operating-threshold/persistence/EWT-limitations inputs, `05B` §26.4). PZEM PWM-energy semantics used only if characterization passed (`03` §102).

### RQ5 — Resilience ↔ H6

- **Claim** (CANONICAL, `00` §0.3): basic thermal protection remains available when backend, broker, or predictive inference is unavailable.
- **Target/outcome**: protocol assertions from RES-01..04 (`03` §105): SAFE_LOCAL entry on connectivity loss; Controller-A/local fallback continues bounded control; no stale remote command actuation; reconnect resync without twin regression or command replay (`02` §§37–39). Plus reliability metrics (`03` §116).
- **Required channels**: `device_mode`, device lifecycle, connection state, SAFE_LOCAL local inputs, command TTL/freshness semantics (`02` §31), offline-buffer replay evidence if implemented (`03` §106).
- **Independent unit**: one resilience scenario execution (S5 CONNECTIVITY_LOSS planning: `03` §31); paired arms (online vs degraded) verified with controlled reassembly where physical (`01` §25 — no unsafe fault injection).
- **Analysis method**: defect-style assertions + timing distributions (`03` §116); **no model-quality metric is claimed from resilience runs** (`03` §66: resilience evidence ≠ model-performance evidence). SAFE_LOCAL timing numbers remain unmeasured until D/A measurement (T_system/T_physical are AIW inputs — `03` §56–57).
- **Evidence family**: RES-01..04 evidence records + telemetry showing mode transitions + resync evidence.
- **Falsifier** (`00` §0.4 H6): a loss scenario leaves a protection gap — SAFE_LOCAL never entered, local control unbounded, stale command actuates, or resync regresses twin state.
- **Tiers**: SAFE_LOCAL contracts/thresholds are D-owned (TEAM_DEPENDENCY); B's role is limited to data-contract support of these runs (dictionary §10–§11) and analysis of recorded behavior.

### RQ6 — Energy–thermal trade-off ↔ H7 (CONDITIONAL STRETCH)

- **Claim** (CANONICAL, `00` §0.3, marked conditional): after the core closed loop is proven, can control reduce unnecessary cooling effort without worsening thermal safety outcomes?
- **Target/outcome**: joint reporting of `ΔE` (pair energy difference) against thermal outcomes (`03` §101, §102). No single "efficiency score" (CANONICAL prohibition).
- **Required channels**: `cooling_power_w` sampled integration for run energy (`00` §3.10; `01` §35.2), `cooling_energy_counter_wh` as cross-check only (1 Wh resolution; not `Total System Energy` — `00` §3.10), PZEM PWM caveat honored (`03` §102).
- **Independent unit**: one A/B pair, same as RQ4.
- **Analysis method**: paired-difference reporting next to RQ4 outcomes; PWM optimization strictly conditional on prior characterization gates.
- **Evidence family**: per-pair Δ-energy vs Δ-exposure table (extension of `03` §101).
- **Falsifier** (`00` §0.4 H7): energy reduction arrives with a worsened thermal/safety outcome, or the core gates never open this analysis (conditional by definition, `00` §0.3).
- **Tiers**: never allowed to delay safe hardware / calibrated sensing / reactive baseline / predictive evaluation / verified closed loop (CANONICAL, `00` §0.3 RQ6 note).

---

## 3. Hypothesis → experiment alignment (from `00` §0.4, CANONICAL)

| Hypothesis | Claim digest | Claim served by | Candidate primary experiments (`03`) | Data dictionary anchor |
|---|---|---|---|---|
| H1 | multi-point > single temperature | RQ1 | A1 (`03` §61) with A2 pairing care (§62) | §4 |
| H2 | predictive state → useful advance warning | RQ2 | A4 (§64), offline locked test (§92) | §3–§6, §12 |
| H3 | warning physically actionable | RQ2/RQ4 | AIW check (§56), latency split (§57) | §3, §10–§11 |
| H4 | closed-loop improves physical outcome | RQ4 | A5 paired A/B (§65, §95) | §7–§11 |
| H5 | electrical telemetry improves diagnosis | RQ3 | A3 (§63), DIAG-01..04 (§103) | §7–§8, §10 |
| H6 | local fallback preserves protection | RQ5 | A6 (§66), RES-01..04 (§105) | §9, §11 |
| H7 | energy-aware effort reduction | RQ6 (conditional) | A7 (§67), only after core gates | §7 |

No hypothesis pre-commits marketing-style numbers (accuracy %, energy-saving %) before data exist (CANONICAL, `00` §0.4).

---

## 4. Channel → claim coverage

Frozen hardware channels (BOM CANONICAL, `00` §3.1) and the claims they legally serve. Dictionary §-anchors give exact fields/units/enums.

| Channel (frozen BOM) | RQ1 | RQ2 | RQ3 | RQ4 | RQ5 | RQ6 | Notes / legal-use boundary |
|---|:-:|:-:|:-:|:-:|:-:|:-:|---|
| DS18B20 ×3 → `t1_c`/`t2_c`/`t3_c` (ROM-mapped roles) | ● | ● | ● | ● | ● | ● | Roles fixed by ROM map, never re-derived (`01` §6.4–6.5); missing channel ⇒ DEGRADED path. |
| BME280 → `t_air_c`, `rh_pct` | ○ | ● | ○ | ● | ○ | ○ | Context only; never a substitute for spatial probes (`00` §3.3 BME note). |
| MC-38 → `door_state` (OPEN/CLOSED/UNKNOWN) | ○ | ● | ○ | ● | ○ | ○ | UNKNOWN may not be read as CLOSED (dictionary §6). |
| PZEM-017 + 50 A / 75 mV shunt → `cooling_voltage_v`/`cooling_current_a`/`cooling_power_w`/`cooling_energy_counter_wh` | ○ | ● | ● | ● | ○ | ● | Cooling-branch only; energy counter = cross-check (1 Wh resolution); OFF-envelope usage conditional until characterized (`00` §3.10–3.11). |
| IBT-2 → `applied_cooling`, `applied_duty` (device edge-applied state) | ○ | ● | ● | ● | ● | ● | Edge **observed/applied** state is authoritative for features — not command intent (dictionary §8). |
| Command record (`command_id`, reason, TTL, controller) — backend consumer view | ○ | ○ | ● | ● | ● | ● | Intent metadata for verification chains; never a past-only feature substitute for applied state (register LRK-04). |
| Quality = per-section + overall + `device_mode` | ● | ● | ● | ● | ● | ● | Quality propagation is part of every feature's validity (dictionary §9, §13). |
| Run metadata (`run_id`, scenario, controller, `hardware_config_id`, `firmware_version`, `calibration_id`) | ● | ● | ● | ● | ● | ● | Mandatory provenance per record (`00` §5.4, `05B` §6). |

● = primary/critical use · ○ = contextual/optional use. (The specific feature *selection* is a later versioned decision — `DERIVED`; this table fixes only legality.)

---

## 5. Claim boundaries (what these claims are NOT)

1. **No shelf-life / commodity-safety claims** — `T_critical` is a testbed research boundary, not automatically a food-safety or regulatory limit (`03` §42; `00` §1.4; `01` §43).
2. **No whole-system energy claims** — the measurement path is the cooling branch; canonical wording is cooling-branch power/energy (`00` §3.10).
3. **No probability semantics without calibration** — default is `risk_score`; `calibrated_probability` only after calibration contract passes (`03` §58–59; `02` §19.7; `05B` §2.3).
4. **No component-level root cause** from telemetry-only evidence (`00` §0.3 RQ3 guard).
5. **No row-as-experiment arithmetic** — 1 Hz rows of one trajectory are dependent observations (`00` §5.3; `03` §1.5).
6. **Statistical significance ≠ engineering significance** — always report raw effect + CI + practical relevance (`03` §1.4, §82; `05B` §2.4).
7. **Negative results are valid** outcomes of valid experiments (`03` §1.6).
8. **No legacy hardware semantics** — any `current_1/current_2`, two-TEC, 20 L, INA226 assumption invalidates the involved record's comparability (`00` §3.2; `02` §14.3).

---

## 6. Pass-criterion answers ("what is predicted, what is independently sampled, what falsifies")

Point answer for Doc `05B` §29 pass criteria; each item traces back to §2.

1. **What exactly is predicted?** The binary event `y_t(H)`: "the predefined representative temperature crosses the frozen critical boundary within horizon H" (`03` §41) for candidate horizons {30, 60, 120, 300 s} — the horizon freezes one primary value before final test (`03` §44; PROVISIONAL). The emitted quantity is `risk_score` (default) or calibrated probability only if the calibration contract passes (`02` §19.7; `03` §59).
2. **What is independently sampled?** One `run_id` trajectory = one independently sampled physical experiment at every model/feature/label stage; one A/B pair = one statistical unit for closed-loop claims (`00` §5.3; `03` §75). Rows, QoS re-deliveries (`02` §13.3), and overlapping windows are NOT independent samples (register LRK-01/02/12).
3. **What evidence would falsify each claim?** Per-claim falsifiers in §2 (RQ1: null ablation delta; RQ2: non-positive held-out EWT / worse missed-event or false-warning behavior vs baselines / AIW ≤ 0; RQ3: no added electrical discrimination on controlled DIAG cases; RQ4: frozen primary outcome not improved beyond frozen minimum-relevance, or safety violation; RQ5: protection gap in any RES scenario; RQ6: effort cut worsens thermal outcome or never unlocked).

---

## 7. What Member B needs from whom (handoff inputs)

Derived from Doc `04` §10.2 (A → B), §10.4 (C → B), `05B` §26.2; Team-dependency framing only — no new schema invented. **Rule (CANONICAL, `04` §10.2): B does not infer missing physical meaning from column names.**

### From A (`04` §10.2)
- valid run IDs + invalid-run reasons; sensor identity/position (ROM↔T1/T2/T3 map); physical scenario semantics; door/disturbance timestamps; calibration/config (`CG-HW-…`, `CG-CAL-…`); initial/reset criteria; pairing variables; plant response characterization.

### From C (`04` §10.4, `05B` §26.2)
- versioned dataset export + checksum; raw/normalized tables (observed TEAM_DEPENDENCY state: `backend` migration 0002/0003); run manifest; event timeline (`events` table — realization SCHEDULED_DEBT, C W07 per `backend` migration 0003 docstring); prediction persistence (`predictions` table — `02` §14.6).

### To C (`04` §10.5, `05B` §26.3)
- analytical field requirements this workstream owns: provenance columns to keep (`00` §5.4 list), time semantics (event vs arrival), quality propagation in exports, dataset manifest + checksum + export hash expectations (`02` §51).

### To A (`05B` §26.1)
- required physical metadata: ROM map registration; position-change records (`01` §6.6 PHY-DS-003); calibration-event id (`01` §39.2); explicit "run invalid, reason" records (`01` §33); no silent scenario re-labeling.

### To D (`04` §10.6)
- prediction **vs policy** distinction: the model produces `risk_score`/probability + warning state; the *action* (threshold chosen for command behavior, persistence, safety gating, duty) belongs to D's policy version — model output can constrain but never decide policy (`05B` §26.4: D owns final policy/action decision). B supplies operating-threshold recommendation, persistence recommendation, EWT distribution, false-warning behavior, AIW inputs, model limitations later in the campaign.

---

## 8. Unfrozen-elements ledger (data needs whose freeze point is later)

| Element | Current tier | Freeze point / owner | Canonical anchor |
|---|---|---|---|
| Primary prediction horizon (candidates 30/60/120/300 s) | PROVISIONAL | B, before final predictive test | `03` §44, §84 |
| `T_critical` boundary value | PROVISIONAL | B, before locked evaluation | `03` §42 |
| Representative temperature (Tmax / Tmean / named probe) | PROVISIONAL | B, frozen before label generation; not score-chosen | `03` §43 |
| Label mechanics detail (event episode rule, gap policy) | PROVISIONAL | B, before final splits | `03` §§41, 45; register LRK-10 |
| Split shape (~16/4/4 planning envelope or 6–8 locked-test alternative) | PROVISIONAL | B after C1/C2 availability known | `03` §48 |
| Event prevalence / "meaningful fraction of events" constants | PROVISIONAL | B, metric freeze W03/W04 | `03` §182; `05B` §31–32 |
| Door-duration tolerance + protocol doors | PROVISIONAL | A/B protocol freeze | `03` §§32–33 |
| OFF-envelope / healthy current-power ranges | PROVISIONAL | A (commissioning) | `01` §39.3 |
| TEC fuse final value | PROVISIONAL | A, commissioning | `01` §16 |
| PZEM/PWM quantitative use; PWM energy semantics | PROVISIONAL | A+B characterization; conditional | `00` §3.11; `01` §34 |
| T_config / latency component numbers | PROVISIONAL | measured, never assumed | `03` §57 |
| `events` table realization for event-timeline consumers | TEAM_DEPENDENCY / SCHEDULED_DEBT | C (W07) | `backend` migration 0003 docstring; `02` §14.4 |
| Synthetic-fixture exclusion at dataset export | TEAM_DEPENDENCY | C export; B manifest rule | `backend/fixtures/*` self-labeling |

Final definitions of these leaves live in the label/evaluation freeze artifacts (B-W03/W04 per `05B` §31–32) — **not** pulled forward into W01 (explicit W01 exclusion; see `leakage-risk-register.md` intro note on scope discipline).

---

Document ends. Next W01 checkpoints: `data-dictionary-v0.md` defines the field identities this mapping assumes; any claim-implementing definition that cannot cite Docs `00`–`03` is either PROVISIONAL, TEAM_DEPENDENCY, or SCHEDULED_DEBT — and turning those tiers into recorded decisions is exactly what the register and convention files govern.
