# ColdGuard · Leakage-Risk Register (W01, Member B)

> Deliverable of task **B-W01-03** (Doc `05B` §29). A leakage mechanism corrupts an evaluation
> silently: the metric looks excellent while the claim it certifies has already been broken.
> This register inventories how each named leak could happen in ColdGuard, what it would corrupt,
> the rule that prevents it, and the future test that detects it if the rule is not honored.

| Field | Value |
|---|---|
| Owner | Member B |
| Reviewer focus | Dataset/split reviewer: A or C; feature/model reviewer: D (Doc `04` §3.3) |
| Parent docs | Doc `03` §§37, 39, 43, 45–47, 49, 55, 58–60, 74, 84–85, 87–88, 92–93, 107, 119, 122–125, 127–128, 133, 161, 163–164, 171, 183–184, 201, 204 · Doc `05B` §§2, 9–13, 15, 22–23, 27, 29–34, 42–44 · Doc `01` §§1.4, 2.6–2.7, 18, 22, 33, 39, 40, 45 · Doc `02` §§13, 19, 39 · Doc `00` §§5.3–5.4 |
| Status | v0 (W01 contract; register grows weekly — see §5) |

Tier legend shared with the other three W01 files. Scikit-learn references cited inline below ([R5] grouping semantics; [R8] probability calibration) resolve to the canonical citation list, Doc `03` §204; the metric-family references [R6]/[R7] (precision-recall/Average Precision) are cited in the claim-data matrix.

**Scope-discipline note (explicit, per W01 exclusions):** this register defines *rules and future tests only*. No grouped-split code, no windowing, no labels, no W02-pull-forward implementation exists in or because of this file. Mechanism = concrete wrongdoing; Consequence = which claim/RQ number gets inflated; Prevention = the rule (canonical citation where Docs `00`–`03` fix it); Detection = the future test (executable once synthetic/real data exist); "W02-invariant" marks prevention that is mechanically assertable in the W02 synthetic harness per `04` §17-B02-B04 without fixture-based runtimes.

---

## 1. Mapping the register to canonical checklists

Every class listed in `05B` §29 B-W01-03 and every checklist item in `03` §123 maps to a register ID (no orphans in either direction):

| Canonical trigger class | Register IDs |
|---|---|
| random rows | LRK-01 |
| future rolling window | LRK-02, LRK-03 |
| future command | LRK-04 |
| post-event state | LRK-04, LRK-10 |
| normalization fitted globally | LRK-05 |
| calibration on test | LRK-06 |
| threshold selection on test | LRK-07 |
| near-duplicate run copies | LRK-08, LRK-12 |

| Doc `03` §123 checklist item | Register IDs |
|---|---|
| split by run before windows | LRK-01, LRK-02 |
| scaler/imputer fit on train only | LRK-05 |
| feature normalization fit on train only | LRK-05 |
| calibration fit on development only | LRK-06 |
| final threshold selected without test | LRK-07 |
| no future values in rolling features | LRK-03 |
| no future controller outcome in current feature | LRK-04 |
| duplicate trajectories not across splits | LRK-08, LRK-12 |
| paired runs not split to leak near-identical disturbances | LRK-08 |

Registers also cover classes the canonical lists imply elsewhere: LRK-09 (intervention contamination, `03` §45; `05B` §13), LRK-11 (locked-test peeking/repeated selection, `03` §92–93, §163), LRK-13 (time semantics, `01` §18; `02` §13), LRK-14 (PZEM missing ⇒ zero, `05B` §27), LRK-15 (configuration identity, `01` §39; `03` §8), LRK-16 (ambient/day covariate drift, `03` §161), LRK-17 (metric/definition shopping across freezes, `03` §§43, 84, 133).

---

## 2. Register

Notation: **Mechanism** → how it happens; **Consequence** → what is inflated/corrupted; **Prevention** → rule, with source authority; **Detection** → future test. All Prevention rules are CANONICAL where a Docs `00`–`03` anchor is cited; implementation detail is PROVISIONAL and binds to the artifact conventions file.

### LRK-01 — Random row/window split (roles of one run split across partitions)
- **Mechanism**: `train_test_split` on telemetry rows or on generated windows treats temporally correlated samples of one trajectory as interchangeable; consecutive/overlapping rows share thermal memory, so test partitions memorize the training trajectory's future.
- **Consequence**: RQ2's "earlier than baseline on held-out independent runs" becomes untruthful; AP/MissRate/false-warning counts absorb memorization; also violates `00` §5.3 (dependent rows are one experiment) and `03` §47.
- **Prevention**: group = `run_id` at minimum (`03` §47 CANONICAL; `05B` §12; `01` §45). `GroupKFold`/`GroupShuffleSplit` semantics: groups never straddle train/test (`03` §204 [R5]). **W02-invariant**: `train_groups ∩ val_groups = ∅`, `train_groups ∩ test_groups = ∅`, `val_groups ∩ test_groups = ∅` asserted in split code (B-W02-02, `05B` §30).
- **Detection**: split audit script deduplicates group membership across partitions; coverage metric reports each run's partition assignment; over-the-split row/window duplication check = `03` §183 dataset-overlap audit.

### LRK-02 — Windowing before split (overlapping windows cross partitions)
- **Mechanism**: windows are generated from all runs first, then split; overlapping windows contain shared physical seconds, so near-identical context occupies both train and test. Also "future rolling window" — a window generated from a training-run tail extends into the run's own future relative to its label.
- **Consequence**: RQ2 inflates massively (classic near-duplicate leak); EWT becomes meaningless (window futures are already memorized).
- **Prevention**: pipeline order is fixed and inversion is forbidden: `runs → split → windows inside each partition` (`03` §46 CANONICAL; `05B` §12). **W02-invariant**: window generator API refuses raw frames without a split manifest (B-W02-03, `05B` §30); validator asserts every window's [start,end] of test folds intersect no training-run time intervals.
- **Detection**: overlap audit per run pair (window interval intersection across partitions == ∅); recorded in QA report before any model artifact is minted.

### LRK-03 — Future values in temporal features (not past-only)
- **Mechanism**: rolling means/MinMax/slopes computed centered or trailing-forward; gradient features using next-sample values; summary features computed across the whole run ("future max temperature", "future recovery time" — `05B` §11 forbidden list).
- **Consequence**: prediction input contains the future the label is drawn from; AP/EWT evidence invalid (`02` §19.4 CANONICAL past-only rule (`feature input ≤ t`); `05B` §11 forbidden-feature list).
- **Prevention**: features registered with `causal: true`, computed strictly from `<= t` (`03` §125 feature audit fields; `05B` §9; `05B` §10.5 all-families-past-only rule). **W02-invariant**: feature pipeline regression test re-computes features at truncated histories and asserts bit-level/numeric-tolerance equality (`03` §184 derived-feature reproducibility).
- **Detection**: feature audit per registered feature (`03` §125): re-derive features from a truncated raw history and compare; any mismatch fails the feature version.

### LRK-04 — Future command/controller outcome as current feature (post-event state leakage)
- **Mechanism**: features ingest the (later) command, ACK, verification outcome, or predictive-controller action for an event that is still unfolding; e.g., "the controller later turned cooling ON" is attached to an earlier prediction sample, or post-event trajectory summaries around critical events are used as context (`03` §123 "no future controller outcome in current feature"; `05B` §11 "future controller action", "post-event outcome").
- **Consequence**: RQ2/RQ3 diagnostic separations become tautological (the feature reveals the outcome the model is supposed to predict); any "warning" quality is fabricated (`01` §45 no-future-command rule; `02` §19.4).
- **Prevention**: feature-time semantics use only the edge-applied state observed strictly before time t (`01` §1.4 applied state; §45 CANONICAL), and command intent metadata is excluded from predictive feature sets unless its device-side application happened before t. Model *target-side* uses of command outcomes are limited to RQ3/RQ4 verification analysis, never RQ2 training (`05B` §2.2 separation). **W02-invariant**: synthetic harness runs a "future pointer" mutation (inject a post-t command) and the feature extractor must ignore it.
- **Detection**: causal-window replay on synthetic trajectory with planted future command → feature vector must be bit-identical; recorded in the feature-audit QA file.

### LRK-05 — Normalization/scaling/imputation/selection fitted globally (on train+test)
- **Mechanism**: any fitted statistic (scaler, imputer center/scale, normalization baselines, feature-selection decisions, PCA components) computed over combined partitions, "EWT-cleaning" statistics across all runs, or ambient baselines from test runs (`03` §123 two items; `05B` §15).
- **Consequence**: test partition statistics leak into preprocessing; RQ2's locked-test discrimination is optimistic (esp. harmful because partitions are few runs).
- **Prevention**: everything fitted is fitted on the TRAIN partition only and applied frozen to val/test (`03` §123; `05B` §15 CANONICAL: "fit on train only, apply to val/test"). XGBoost's tree splits need no global scaler — do not add one without purpose (`05B` §15). **W02-invariant**: harness unit test fits any transform on a train-only fixture and asserts val/test rows are untouched by training-set statistics reflection.
- **Detection**: "fit-affect" audit — record each fitted statistic's source run-set identity in the artifact manifest (convention §9 binding); checker verifies source set ⊆ train runs.

### LRK-06 — Calibration performed on test (both fitting and reporting)
- **Mechanism**: probability calibration method (isotonic/Platt/binning) fitted using test outcomes; or calibrated probabilities reported after inspecting test reliability curves without a frozen protocol (`03` §58, §60, §128).
- **Consequence**: probability semantics (calibrated_probability vs risk_score) become unverifiable; if calibration is claimed, the RQ2/H2 claim language escalates ("meaningful fraction with calibration") without evidence.
- **Prevention**: calibration fits only on development/training-calibration subsets (`03` §60 CANONICAL; `05B` §22); sparse-positive data uses few bins + counts; score-only fallback is a first-class outcome (`03` §59); probability-semantic tooling per `03` §204 [R8].
- **Detection**: calibration artifact records fit-run-set + grouped folds used; checker compares against split manifest (`03` §128 grouped-split-required field). LOCKED test freeze gate rejects any calibration artifact minted after test unlock.

### LRK-07 — Operating-threshold/persistence selection on test
- **Mechanism**: warning threshold or persistence gate `k` tuned by inspecting locked-test metric surfaces (`03` §87, §88); equivalently picking the horizon or label definition that maximized the locked-test result.
- **Consequence**: EWT/false-warning trade-offs become post-hoc artifacts; RQ2's threshold-free evidence claim breaks (`03` §133 statistics-freeze CANONICAL; `05B` §27 "threshold shopping" risk).
- **Prevention**: thresholds/persistence selected on development data under a predeclared tradeoff (`03` §87–88), frozen into the model artifact before test unlock (`03` §92 freeze list includes warning threshold + persistence + calibration method + horizon). **W02-invariant**: threshold/persistence inputs are manifest fields, not environment variables; evaluator reads them from the frozen artifact record.
- **Detection**: model-freeze bundle check (`03` §§92, 127): all seven frozen fields present + hash; evaluator refuses to run without them. Deviation from dev-set-only selection = register hit requiring disclosure/re-test (`03` §93).

### LRK-08 — Near-duplicate trajectories across splits
- **Mechanism**: repeated executions of the same scenario (paired A/B arms of the same disturbance protocol; commissioning duplicates after device reposition; repeated S2 disturbances with near-identical shapes) land in different partitions; near-identical disturbance contexts are split across train/test (`03` §123 last item; `05B` §29 "near-duplicate run copies").
- **Consequence**: RQ2's held-out independence claim weakens; RQ4's pair-level inference leaks if arm runs of one pair straddle partitions (though Arm A/B runs are NOT model training data for RQ2 — see LRK-09 — partition duplication matters for any later exploratory reuse).
- **Prevention**: near-duplicate screening via run-similarity QA before split placement (candidate tooling: scenario-shape metrics over aligned thermal responses); split manifests record blocking/day/`pair_id` context so assignment is auditable (`03` §37 blocking concept; §161 environmental context); comparator validated in the QA report (`03` §183).
- **Detection**: overlap audit tool: pairwise nearest-neighbour run similarity test (derived-feature space) raising flags above a PROVISIONAL threshold (threshold itself frozen before final split when data exist — `03` §183).

### LRK-09 — Closed-loop intervention trajectories contaminating predictive training/EWT
- **Mechanism**: Controller-B (predictive, physically interventional) runs — where the model's own action changes the trajectory — enter predictive training/validation/test or EWT computation; the resulting trajectories embed the controller's intervention, breaking the counterfactual meaning of EWT (`03` §39—"offline early-warning proof" uses locked observational/reactive trajectories; §45 label contamination; `05B` §13).
- **Consequence**: RQ2 collapses: "earlier warning observation vs baseline" becomes self-referential (intervention erases the critical event the label expects); H2/H3 evidence silently degrades.
- **Prevention**: the core predictive dataset = baseline/reactive/controlled-observation runs (`03` §45 CANONICAL); A/B run data kept as an L5-style separate evidence family (`05B` §13); EWT computed only on offline/reactive trajectories (`03` §55 "for an offline/reactive trajectory"). **W02-invariant**: split manifest schema has a `controller_context` field and the trainer refuses runs tagged predictive-closed-loop unless the artifact is explicitly the A/B analysis variant.
- **Detection**: run-provenance audit of every dataset/split manifest: every run's `controller_id` field compared against the intervention-exclusion invariant; any predictive-control run found inside the predictive-training dataset fails the audit.

### LRK-10 — Label contamination via future intervention (label depends on an intervention-affected future)
- **Mechanism**: label window extends into, or the representative-temperature/boundary choice was tuned against, a future in which predictive intervention changes the trajectory — a label whose occurrence is *conditioned* by an intervention it is supposed to predict. It also covers frozen-after-shopping: choosing `T_critical`/representative temperature AFTER seeing scores (`03` §43: "Do not choose the representation after comparing which gives the best model score").
- **Consequence**: labels become circular; RQ2's AP on such runs certifies a tautology (`03` §45 leak definition of future predictive intervention).
- **Prevention**: label spec freeze before final splits (`03` §43 CANONICAL), applied to non-intervention runs; boundary selection documented as frozen decision with any validation checks restricted to dev folds. **W02-invariant**: label generator version records: boundary value + representative temperature + horizon + frozen-at timestamp, all mandatory in the label artifact identity.
- **Detection**: label audit (`03` §124): randomized inspection of labeled windows around events requiring spot-check plots; boundary/representative choices re-derived from the recorded freeze artifacts and compared.

### LRK-11 — Locked-test peeking / sequential model selection against test
- **Mechanism**: locked test runs unlocked during tuning; repeated test evaluation while model changes; "test-first" reporting after retraining without fresh test data (`03` §49, §92, §163 sequential peeking rule; §93 retraining-after-final-test).
- **Consequence**: claims about locked-test generalization lose their one-shot meaning; H2/H4 numeric floors sampled until satisfied (`03` §201 prohibited defense shortcuts).
- **Prevention**: locked test manifest frozen once, `opened_at` stays null through the whole tuning campaign; model freeze bundle (feature_version, hyperparameters, artifact hash, threshold, persistence, calibration method, primary horizon) recorded BEFORE unlock (`03` §92); if post-test bug-fix retraining happens, either new independent test data or explicit exploratory-revision disclosure (`03` §93 CANONICAL).
- **Detection**: split manifest (`opened_at` timestamps) audited against model-artifact creation timestamps; violation = artifact epoch mismatch → claim rejected.

### LRK-12 — Row-multiplicity leakage (correlated evidence counted independently; duplicates/re-delivery inflation)
- **Mechanism**: metric denominators or "evidence" statements count rows / QoS-1 re-deliveries / replayed offline samples as independent observations; value lies in `(device_id, boot_id, seq)` identities rather than runs (`02` §13.3; `00` §5.3; `01` §40.1).
- **Consequence**: empirical floors ("N independent events seen") appear larger than reality — systematically favorable to RQ2 event-prevalence statements and RQ4 counts (`03` §1.5; `05B` §2.1).
- **Prevention**: all statistical units declared in run/pair terms (matrix §2; `00` §5.3); dataset exports must receive backend dedup semantics (unique normalized identity) and expose duplicate counts as separate columns (`03` §107 duplicate test as concept). **W02-invariant**: dataset build QA reports the triple `unique runs`, `unique (device_id, boot_id, seq)` identities, `duplicate deliveries observed`; consumers using counts must cite the run count, not the row count.
- **Detection**: `03` §122 QA checklist "unique run_id", "unique (device,boot,seq)", and the completeness formula's cadence-awareness (`03` §119) run at every export; violations block dataset publication (freeze gate).

### LRK-13 — Time-semantics leakage (event vs arrival mixing; boot-boundary windows; replayed stale data as current)
- **Mechanism**: features/windows ordered by `backend_received_at` instead of `captured_at` (`01` §18.1–18.2: they are never interchangeable); sequence axes joined across boots while ignoring `boot_id` resets; stale/replayed offline-buffered telemetry re-injected as fresh (`02` §39 offline replay identity preservation; `01` §40.2 out-of-order guard).
- **Consequence**: causality inversions (arrived-later-but-earlier-captured samples corrupt window logic); window crossing a reboot mixes two thermal regimes; EWT timing references attach to arrival times and inflate lead times (`03` §171 prediction timing alignment audit as the gate).
- **Prevention**: every window/label uses event time axis with boot-scoped monotonicity (dictionary §3); feature pipeline must reject cross-boot windows; dataset export exposes both times; time-sync state must be recorded (dictionary §3 note) before final offline datasets. **W02-invariant**: synthetic harness generates out-of-order + cross-boot mixtures and the pipeline must produce identical partitioning/features as the clean ordering (deterministic equivalence assertions).
- **Detection**: prediction-timing audit (`03` §171) and dataset QA (`03` §122 "no impossible timestamps", "monotonic sequence within boot").

### LRK-14 — Quality-blind zero-fill (PZEM missing ⇒ 0 W; degraded values as valid)
- **Mechanism**: absent electrical samples silently become zero power (downstream counter/time integrations then conclude "no cooling energy used"); INVALID-quality values enter features; `UNKNOWN` door treated as CLOSED (dictionary §6, §9; `05B` §27 "PZEM missing misread as zero").
- **Consequence**: whole-run energy/feature semantics flip sign silently; RQ3/RQ6 diagnosis and energy claims corrupt (`01` §22 electrical-state distinctions depend on absent ≠ zero).
- **Prevention**: missing/absent channels stay None with non-VALID quality (dictionary §9 rules; C contract realized); integrations skip or explicitly flag missing intervals (`03` §85: imputation cannot create physical evidence; `01` §2.6 derived must not hide missing raw CANONICAL). **W02-invariant**: feature/label pipeline tests with planted "PZEM gap" harness fixtures produce NaN/flag, never 0; absent→0 is not an available feature-level missing-behavior for a measured physical channel (dictionary §13(a) forbids it) — a zeros convention for such a channel would need a contract revision, not a feature-version declaration.
- **Detection**: feature-audit missing-behavior fields are asserted against raw-sample QA (`03` §122 "sensor quality" check + export QA filter summing absent-vs-zero intervals).

### LRK-15 — Configuration-identity leakage (hardware/calibration/firmware mixing)
- **Mechanism**: runs spanning different `hardware_config_id` / `calibration_id` / `firmware_version` bins partitioned without blocking; sensor/extrusion replacements mid-campaign silently re-baseline a channel (`03` §195 sensor replacement, §196 TEC/V1 reassembly, §197 PZEM/shunt change rules); a changed ROM→role map re-merges positions and reads as data drift.
- **Consequence**: models latch onto configuration identity (e.g., calibration offset) rather than physics; splits evaluate across non-comparable configurations (`01` §2.7 CANONICAL: physical comparison requires configuration comparability); RQ1's spatial analysis silently remixes probe roles.
- **Prevention**: configuration comparability IS the split-axis metadata requirement — identical `hardware_config_id` + known-good `calibration_id` lineage for a given split family, recorded in split/dataset manifests (`00` §5.4 provenance CANONICAL; `01` §39 configuration objects); hardware changes version config and update Docs 00–03 BEFORE mixing data (`00` §3.2 rule 5).
- **Detection**: export QA asserts known hardware/calibration identities (`03` §122 "known hardware config", "known calibration"); ROM-role remap events invalidate affected runs via the physical invalidation ledger (`01` §33 identity-mismatch trigger).

### LRK-16 — Ambient/day-level covariate drift aligned with split assignment
- **Mechanism**: outdoor/room temperature, humidity, or chamber pre-condition drift across collection days so that a partition boundary coincides with a regime boundary; model learns day identity instead of trajectory dynamics (`03` §161 environmental context record).
- **Consequence**: RQ2 holds out precisely the "end of project" regime; locked test peaks on a shift rather than predictive skill — evaluation confidence collapses when new days appear.
- **Prevention**: record environmental context per run (ambient t_air outside/at start; A supplies, protocol §161); stratify/monitor split assignment against day/environment at split creation (PROVISIONAL rule — no numeric threshold; formal check when real data exist); avoid splitting offset in a hard day/night boundary where possible (`03` §37 blocking pattern).
- **Detection**: distribution-comparison audit across partitions for ambient t_air and run start temperature; split manifests store `env_context_profile` per run (`03` §161-style record) — concretized at W04 evaluation freeze (`05B` §32).

### LRK-17 — Metric/definition shopping across freezes (post-hoc definition drift)
- **Mechanism**: primary metric, paired-difference sign convention, horizon set, representative temperature, or exposure unit changes after inspecting result distributions, then re-reported as pre-declared (`03` §83 metrics CANONICAL; §84 horizon shopping prohibition; §133 statistical-analysis freeze; §74 pair-difference convention freeze).
- **Consequence**: the claim chases the strongest-looking label; "no p < 0.05 headline if 20 metrics searched" broken; W04's evaluation-freeze contract retroactively diluted — this is the meta-leak that turns all other registers into shuffle-able targets.
- **Prevention**: metric freeze artifacts (signed/committed manifest of primary metric + sign convention + horizon + representative temperature + confidence level + bootstrap seed/iterations + test family) before any locked evaluation; registration in the artifact-convention identity system (`05B` §23 hyperparameter discipline same pattern); any deviation = explicit revision artifact with its own version.
- **Detection**: cross-check that analysis code (analysis_version) references only frozen manifest values (convention §9 bindings); `03` §164 repeated-model-selection warning governs report review.

---

## 3. Register-implementation bridge to W02 (synthetic harness invariants)

These prevention rules are the W02-era mechanical invariants (all anchored by `05B` §30 and `04` §17 Member-B task list — no W01 pull-forward; only the *specification* lives here):

| Invariant | Home rule | Implementer week |
|---|---|---|
| grouped disjointness assertions (train/val/test) | LRK-01 | B-W02-02 (`05B` §30) |
| windowing refuses unsplitted data | LRK-02 | B-W02-03 (`05B` §30) |
| label generator records frozen boundary/horizon identity | LRK-10 | B-W02-04 (`05B` §30) |
| manifest parser validates split/run/controller-context fields | LRK-09, LRK-11 | W02 manifest parser (`04` §17 Member-B "experiment manifest parser") |

LRK-05/06/07/12/13/14/16/17 do not all have a W02 code home; their mechanical checks appear with the harness exports/evaluations (LRK-05 transform-fit test; LRK-12 export QA triple; LRK-13 deterministic-equivalence test) — see the tier ledger in §4 for each rule's first mechanical-check week; those later instrumentation homes are logged by owner B as SCHEDULED_DEBT and tracked through the weekly ritual (§5.1).

---

## 4. Tier ledger (all prevention/detection instrumentation status)

| ID | Prevention authority | Prevention instrumentation | Detection instrumentation | First mechanical check |
|---|---|---|---|---|
| LRK-01 | CANONICAL (`03` §47; `00` §5.3) | W02 grouped-split assertions | export/split QA audit | W02 |
| LRK-02 | CANONICAL (`03` §46; `05B` §12) | W02 window-generator guard | window-overlap audit | W02 |
| LRK-03 | CANONICAL (`02` §19.4; `01` §45) | feature registry `causal` field | truncated-history replay test | W02 (harness), forever after |
| LRK-04 | CANONICAL (`01` §45; `03` §123) | applied-state-only feature policy | future-pointer mutation test | W02 (harness) |
| LRK-05 | CANONICAL (`03` §123; `05B` §15) | fit-on-train pipeline contract | fit-source set audit | W02-W04 |
| LRK-06 | CANONICAL (`03` §60; `05B` §22) | calibration fit-run-set manifest | pre-unlock gate check | W14 (`05B` §42) |
| LRK-07 | CANONICAL (`03` §§87–88, 92; `05B` §27) | threshold-in-manifest rule | freeze-bundle completeness check | W15 (`05B` §43) |
| LRK-08 | CANONICAL (`03` §123 last item) | split blocking/metadata fields | duplicate-trajectory similarity audit | W04/W05 (real data QA) |
| LRK-09 | CANONICAL (`03` §45; `05B` §13) | controller-context run exclusion | run-provenance audit | W02 (harness simulator plays A/B arms) |
| LRK-10 | CANONICAL (`03` §§43, 45) | label-artifact identity fields | label spot-audit plots | W02 (label generator) |
| LRK-11 | CANONICAL (`03` §§49, 92–93, 163) | `opened_at` null discipline | epoch timestamp cross-check | W16 locked test (`05B` §44) |
| LRK-12 | CANONICAL (`00` §5.3; `02` §13.3) | export dedup + duplicate-count columns | QA triple (runs / identities / deliveries) | W05 real telemetry QA (`05B` §33) |
| LRK-13 | CANONICAL (`01` §18; `02` §39) | event-time + boot-scoped windows | timing-alignment audit (`03` §171) | W06 timing tools (`05B` §34) |
| LRK-14 | CANONICAL (`01` §2.6; `03` §85) | None+quality missing contract | absent-vs-zero interval QA | W02 (harness) |
| LRK-15 | CANONICAL (`01` §§2.7, 38–39; `00` §5.4) | config blocks/hardware lineage | known hardware/calibration QA | W05 (`03` §122) |
| LRK-16 | PROVISIONAL (`03` §161 record) | ambient-context record + stratify rule | cross-partition ambient distribution compare | W05+ (real data) |
| LRK-17 | CANONICAL (`03` §§83–84, 133) | statistics-freeze manifest | analysis-vs-manifest binding check | W03/W04 statistic freeze (`05B` §31–32) |

## 5. Governance of this register

1. **Living artifact**: the register goes weekly through Member-B PRs; every new leak discovered (or post-review counterexample) lands as a new LRK-nn with the same four fields, before the containing week's evaluation happens (defect-first: `03` §1.1 evidence beats screenshots).
2. **Canonical supremacy**: no prevention rule in this register may weaken a Docs `00`–`03` anchor; if `05B` conflicts with Docs `00`–`03`, the docs win (`04` §0). Where no doc anchors a rule, the rule is PROVISIONAL until a predeclared freeze instates it.
3. **Counterexample discipline**: the candidate reviewer (D for feature/model, A/C for dataset/split per `04` §3.3) is invited to *construct* violating workflows from the written rules; a prevention rule with no mechanical violation path is a candidate SCHEDULED_DEBT, not a claimed-safe state.
4. **Traceable linkage**: any register finding reported to the tracker references the LRK-nn (never a prose paraphrase) so the anti-leak chain survives re-planning.
5. **Not-exhaustive clause**: a leakage path absent from this register is not thereby lawful; `03` §123 checklist and `05B` §27 remain primary hunting grounds; W05+ QA reports re-run the canonical checklist directly (`05B` §33).
