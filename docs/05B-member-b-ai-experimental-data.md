# COLDGUARD — HỆ THỐNG BẢO VỆ CHUỖI LẠNH CHỦ ĐỘNG
## Member B Execution Playbook · AI · Experimental Data · Predictive Evaluation · Statistics

> **Document:** `docs/05B-member-b-ai-experimental-data.md`  
> **Course:** Internet of Things (IoT) — Course Project / Bài tập lớn  
> **Project:** **ColdGuard — Hệ thống bảo vệ chuỗi lạnh chủ động**  
> **Role:** **Member B — AI & Experimental Data**  
> **Planning horizon:** **24 weeks**  
> **Planned focused effort:** **278 hours**  
> **Average:** **11.6 h/week**  
> **Parents:**  
> `00-project-scope-architecture.md`  
> `01-physical-measurement-correctness-contract.md`  
> `02-aiot-closed-loop-engineering.md`  
> `03-verification-experiments-demo.md`  
> `04-team-execution-plan.md`  
> **Sibling playbooks:** `05A`, `05C`, `05D`  
> **Normative role:** chronological execution contract for Member B. This document converts the project’s data, prediction, evaluation and statistics responsibilities into weekly issue packs, quantitative acceptance criteria, evidence artifacts, cross-member handoffs and leader-review checkpoints.  
> **Non-authority rule:** this playbook MUST NOT redefine hardware identity, physical measurement semantics, MQTT/twin semantics, control safety hierarchy, final experiment validity rules or team gates. If this file conflicts with Docs 00–04, the parent document wins.  
> **Data principle:** **one telemetry row is not one independent experiment.** The project’s statistical unit is primarily the independent physical run / matched A-B pair. Windows and 1 Hz rows are dependent observations nested within those runs.  
> **Model principle:** XGBoost is the core predictive model. Deep sequence models are conditional and require a measured need, sufficient independent runs and clear incremental value.  
> **Primary mission:** produce a predictive pipeline that is **leakage-safe, reproducible, calibrated when probability wording is used, physically interpretable, benchmarked against deterministic baselines, and statistically connected to the final closed-loop physical evidence.**

> **Member B north star.**  
> **The job is not “train a model with high accuracy.” The job is to prove, without leakage or inflated sample size, whether past-only thermal/context/electrical information creates useful warning before a reactive threshold, whether that warning is physically actionable, and whether the final predictive controller improves a real physical outcome in matched experiments.**

---

# 0. How to use this playbook

Each week must end with an artifact that another member can inspect and reproduce.

Member B must repeatedly answer:

```text
What is one independent unit?
What is the target?
What information was available at inference time?
Which runs are train/validation/test?
Which baseline are we beating?
Which metric reflects the real question?
Is this a score or a calibrated probability?
Is the warning early enough to matter physically?
Does the final physical A/B result support the claim?
```

Do not let:

```text
large row count
beautiful ROC curve
one impressive trajectory
```

substitute for experimental validity.

---

# 1. Role contract

## 1.1 Member B owns

### Dataset semantics

- run manifests;
- dataset manifests;
- split manifests;
- valid/invalid run inclusion;
- data QA;
- feature registry;
- label generation;
- window generation;
- leakage audit.

### Predictive intelligence

- deterministic analytical baselines;
- XGBoost;
- primary prediction horizon selection;
- model threshold/persistence recommendation;
- calibration when probability semantics are needed;
- model artifact/version;
- model card.

### Evaluation

- grouped CV / grouped holdout;
- Average Precision / PR analysis;
- event-level false warning / missed event;
- Early Warning Lead Time;
- Actionable Intervention Window support;
- ablation A1/A2/A3/A4;
- locked test.

### Final physical statistics

- A/B pair ledger;
- paired outcome analysis;
- bootstrap CI;
- effect size;
- sensitivity analysis;
- limitation statement;
- result tables/figures.

---

## 1.2 Member B does not own

Member B must not independently redefine:

```text
T1/T2/T3 physical identity
PZEM current meaning
which GPIO is legal
command TTL semantics
SAFE_LOCAL state machine
final actuator limits
hardware safety threshold
```

These are A/C/D + parent-doc responsibilities.

---

# 2. Core scientific distinctions

## 2.1 Row count versus independent run count

At 1 Hz:

```text
20 min run = 1200 rows
```

But:

```text
1200 rows ≠ 1200 independent experiments
```

Rows share:

- initial state;
- hardware config;
- ambient context;
- disturbance;
- temporal autocorrelation.

Therefore:

```text
model training sample = window/row
scientific independent unit = run/event/pair
```

Keep these concepts separate.

---

## 2.2 Predictive proof versus control proof

### Predictive proof

Question:

> Can a model warn before the reactive criterion?

Use:

```text
observational/reactive trajectories
```

where the future is observable without predictive intervention changing it.

### Closed-loop control proof

Question:

> Does acting on the prediction improve physical outcome?

Use:

```text
matched Controller A vs Controller B runs
```

Do not compute fake EWT inside an intervention trajectory where Controller B prevented the future threshold event.

---

## 2.3 Risk score versus calibrated probability

Default model output:

```text
risk_score
```

Only call it:

```text
P(critical within H)
```

after calibration evidence.

A classifier can discriminate well and still be poorly calibrated.

---

## 2.4 Statistical significance versus engineering value

Final interpretation must report:

```text
effect magnitude
confidence interval
raw values
engineering meaning
```

not only p-value.

---

# 3. Core mathematical objects

## 3.1 Critical target

For prediction time \(t\) and horizon \(H\):

\[
y_t(H)=
\begin{cases}
1 & \text{if critical thermal criterion occurs in }(t,t+H] \\
0 & \text{otherwise}
\end{cases}
\]

The thermal criterion itself is frozen before final evaluation.

---

## 3.2 Spatial features

\[
T_{mean}=\frac{T_1+T_2+T_3}{3}
\]

\[
T_{max}=\max(T_1,T_2,T_3)
\]

\[
T_{min}=\min(T_1,T_2,T_3)
\]

\[
G_T=T_{max}-T_{min}
\]

---

## 3.3 Temporal slope

For a past-only window:

\[
\dot T \approx \frac{\Delta T}{\Delta t}
\]

or a linear-fit slope.

Feature metadata must include:

```text
signal
window length
method
units
```

---

## 3.4 Early Warning Lead Time

For a non-intervened trajectory:

\[
EWT=t_{reactive}-t_{predictive}
\]

Positive:

```text
predictive warning earlier
```

---

## 3.5 Actionable Intervention Window

\[
AIW=t_{critical}-t_{warning}-T_{system}-T_{physical}
\]

This connects model timing to real plant timing.

---

## 3.6 Thermal exposure

Candidate final physical metric:

\[
E_T=\sum_i\max(0,T_i-T_{limit})\Delta t_i
\]

Exact representative temperature and limit are frozen in Doc 03.

---

## 3.7 Paired improvement

Recommended convention:

\[
I_i=Y_{A,i}-Y_{B,i}
\]

For a lower-is-better metric:

```text
I_i > 0
```

means Controller B improved the outcome.

---

# 4. Data hierarchy

Recommended:

```text
L0 raw
L1 validated / normalized
L2 run-aligned / analysis-ready
L3 windowed features
L4 model predictions
L5 experiment outcome tables
```

Rules:

- never overwrite L0;
- L3 must be regenerable from L0/L1 + config;
- L4 tied to model version;
- L5 tied to frozen analysis code.

---

# 5. Dataset artifact structure

```text
ml/
├─ data/
│  ├─ manifests/
│  ├─ splits/
│  ├─ qa/
│  └─ exports/
├─ features/
│  ├─ registry/
│  ├─ transforms/
│  └─ tests/
├─ baselines/
├─ training/
├─ evaluation/
├─ calibration/
├─ ablation/
├─ artifacts/
└─ reports/
```

Exact folder names may vary.

The conceptual boundaries should remain visible.

---

# 6. Mandatory identifiers

Every report-grade record or dataset must preserve enough information to recover:

```text
run_id
scenario_id
controller_id
pair_id where relevant
device_id
boot_id
seq
captured_at
hardware_config_id
firmware_version
calibration_id
schema_version
feature_version
model_version where relevant
policy_version where relevant
```

---

# 7. Dataset manifest

Conceptual:

```yaml
dataset_id: CG-DATA-...
source_runs:
  - CG-S2-A-001
  - ...
hardware_configs:
  - CG-HW-001
schema_version: 1
calibration_ids:
  - ...
export_query_hash: ...
created_at: ...
created_by: ...
git_commit: ...
```

---

# 8. Split manifest

```yaml
split_id: CG-SPLIT-001

train_runs:
  - ...

validation_runs:
  - ...

test_runs:
  - ...

grouping:
  key: run_id

locked_test:
  frozen_at: ...
  opened_at: null
```

Do not store split only in notebook memory.

---

# 9. Feature registry

Every feature:

```text
name
source signals
formula
window
causal?
missing behavior
units
feature_version
```

Example:

```yaml
name: tmean_slope_30s
sources: [t1_c, t2_c, t3_c]
window_s: 30
method: linear_regression
causal: true
```

---

# 10. Feature families

## 10.1 Instantaneous thermal

```text
T1
T2
T3
Tmean
Tmin
Tmax
gradient
std
```

---

## 10.2 Environmental/context

```text
t_air
rh
door_state
time_since_door_open
door_open_duration
door_event_count_past_window
```

---

## 10.3 Temporal

```text
slope
rolling mean
rolling std
rolling min/max
recent delta
recovery slope
time since cooling transition
```

---

## 10.4 Electrical

```text
cooling_voltage
cooling_current
cooling_power
applied cooling
duty if valid
```

---

## 10.5 Exposure/history

```text
cumulative thermal exposure in past window
recent time above target
```

All must remain past-only.

---

# 11. Features forbidden by leakage

Examples:

```text
future temperature
future critical-event time
future recovery time
future controller action
post-event outcome
future max temperature
```

If a feature requires future data to compute at inference time:

> it is not an online predictive feature.

---

# 12. Splitting contract

Use:

```text
run-level groups
```

before window generation.

Correct:

```text
runs
→ split
→ windows inside each partition
```

Forbidden:

```text
all windows
→ random train_test_split
```

Scikit-learn GroupKFold explicitly uses non-overlapping groups.

---

# 13. Pair-aware considerations

Final closed-loop A/B is not model training data for the primary early-warning claim unless explicitly separated for a later exploratory study.

Reason:

- Controller B changes the future trajectory.

Do not contaminate the locked observational predictive test with intervention data.

---

# 14. Missing-data contract

Never silently forward-fill a physical channel indefinitely.

Possible handling:

```text
drop invalid window
explicit missing flag
bounded short interpolation if predeclared
model disabled for unsupported missing state
```

Choice depends on feature/model design.

Record it in feature version.

---

# 15. Scaling / transforms

Tree-based XGBoost usually does not require standard scaling of numeric features for split behavior.

Do not add scaling merely because “ML pipeline should have scaler.”

If any transformation is fitted:

```text
fit on train only
apply to val/test
```

---

# 16. Imbalance handling

Potential approaches:

- decision threshold;
- `scale_pos_weight`;
- sample weighting;
- event-balanced sampling.

XGBoost documents `scale_pos_weight` as useful for imbalanced classes and gives a negative/positive ratio as a typical starting point.

But:

> reweighting may affect probability interpretation.

If probability calibration is important, evaluate carefully.

---

# 17. Baselines

## B0 — raw threshold

Reactive critical threshold.

---

## B1 — hysteresis/persistence

Operational deterministic baseline.

---

## B2 — optional simple linear/logistic model

Only if useful as an interpretable statistical baseline.

---

## M1 — XGBoost

Core predictive model.

---

# 18. Why XGBoost is core

Expected dataset characteristics:

```text
small independent run count
tabular engineered windows
mixed thermal/context/electrical variables
nonlinear interactions
CPU inference sufficient
```

This favors a strong tree-boosting baseline.

The project does not need GPU/deep-learning novelty.

---

# 19. XGBoost artifact policy

Use stable XGBoost model IO:

```text
save_model("model.ubj")
or
save_model("model.json")
```

Do not make Python pickle the only archival artifact.

Official XGBoost documentation guarantees backward compatibility for saved models but not memory snapshots/pickles.

Store alongside:

```text
feature_version
hyperparameters
threshold
horizon
training_dataset_id
hash
```

---

# 20. Evaluation metric hierarchy

## Primary predictive discrimination candidate

```text
Average Precision (AP)
```

Why:

- positive impending-critical state may be imbalanced;
- PR behavior is operationally meaningful.

---

## Supporting

- precision;
- recall;
- F1;
- false warnings/run or hour;
- missed events;
- ROC-AUC secondary;
- confusion matrix with unit stated.

---

## Timing

- EWT;
- AIW.

---

## Calibration

When probability is claimed:

- reliability curve;
- Brier score;
- log loss as supporting.

---

# 21. Event-level evaluation

A 30-second warning episode is not 30 independent alerts.

Define warning episodes using:

- threshold crossing;
- persistence;
- reset/refractory rule.

Report event-level operational behavior.

---

# 22. Calibration contract

Scikit-learn calibration curves compare predicted probability bins with observed fraction positive.

If calibration data are sparse:

- use few bins;
- show counts;
- avoid overconfident interpretation.

Calibration method must be trained on development data only.

---

# 23. Hyperparameter-search discipline

Use a bounded search.

Candidate dimensions:

```text
max_depth
min_child_weight
learning_rate
n_estimators
subsample
colsample_bytree
reg_alpha
reg_lambda
scale_pos_weight when justified
```

Do not run an enormous optimization loop against tiny independent N.

Prefer stable performance across grouped folds.

---

# 24. Reproducibility requirements

Record:

```text
Python version
xgboost version
scikit-learn version
numpy
pandas
random seeds
git commit
dataset manifest
split manifest
```

Training can have stochastic elements.

Final model artifact inference must be deterministic/reproducible within numerical tolerance.

---

# 25. Member B Definition of Done

By W24 hand over:

```text
dataset card
data QA report
split manifest
label spec
feature registry
baseline implementations
XGBoost artifact
hyperparameter/config record
model card
calibration report or explicit score-only decision
ablation reports
locked-test result
EWT / AIW evidence
final A/B pair table
bootstrap/statistical analysis
final figures
analysis scripts
limitations
```

---

# 26. Member B interfaces

## 26.1 A → B

A provides:

```text
valid run IDs
sensor identity/position
physical scenario semantics
door event
PZEM data
applied state
physical quality
plant timing
initial/reset criteria
pairing variables
```

---

## 26.2 C → B

C provides:

```text
versioned export
raw/normalized data
event timeline
run manifest
dataset checksum
prediction persistence
```

---

## 26.3 B → C

B provides:

```text
feature_version
model artifact/hash
model_version
horizon
input/output contract
risk semantics
calibration status
```

---

## 26.4 B → D

B provides:

```text
model operating threshold
persistence recommendation
EWT distribution
false-warning behavior
AIW inputs
model limitations
calibration semantics
```

D owns final policy/action decision.

---

# 27. Personal risk register

| Risk | Response |
|---|---|
| random-row leakage | split runs first |
| overlapping windows leak | window only after split |
| test-set peeking | locked test manifest |
| too few independent runs | report uncertainty; bounded model complexity |
| high accuracy from imbalance | AP + recall/false warnings |
| model score called probability | calibration or score-only wording |
| threshold shopping | choose on dev only |
| horizon shopping | freeze primary horizon |
| feature leakage from controller | past-only feature audit |
| intervention data used for EWT | separate offline vs closed loop |
| invalid physical runs included | use A/Doc03 validity ledger |
| PZEM missing misread as zero | quality-aware feature logic |
| one lucky run dominates result | grouped/effect distribution |
| final A/B p-hacking | primary metrics + pair target frozen |
| deep model scope creep | Go/No-Go after XGBoost evidence |

---

# 28. Evidence conventions

Recommended:

```text
evidence/B/Wxx/
```

Each week README:

```text
goal
dataset/run IDs
split ID
feature version
model version
random seed
commands
metrics
result
pass/fail
limitations
```

---

# 29. Week 01 — Research claim mapping, data dictionary and leakage-risk register
**Effort:** **10 h**  
**Parent:** `04 W01`

## Objective

Translate Docs 00–03 into a precise analytical contract before any serious ML work.

---

## B-W01-01 — Claim→data mapping

For each research claim:

```text
RQ
target/outcome
required channels
independent unit
analysis method
evidence
```

---

## B-W01-02 — Data dictionary v0

Define current frozen hardware fields:

```text
T1/T2/T3
t_air
rh
door
cooling_voltage
cooling_current
cooling_power
cooling_energy
applied_cooling
quality
run identity
```

No `current_1/current_2`.

---

## B-W01-03 — Leakage register

List potential leaks:

- random rows;
- future rolling window;
- future command;
- post-event state;
- normalization fitted globally;
- calibration on test;
- threshold selection on test;
- near-duplicate run copies.

---

## B-W01-04 — Artifact naming/versioning

Draft:

```text
dataset_id
split_id
feature_version
model_version
analysis_version
```

---

## Deliverables

```text
claim-data-matrix.md
data-dictionary-v0.md
leakage-risk-register.md
artifact-convention.md
```

---

## Pass criteria

Member B can answer:

> what exactly is predicted, what is independently sampled, and what evidence would falsify the claim?

---

## Handoff

C receives analytical field requirements.

A receives required physical metadata.

D receives distinction between prediction and policy.

---

# 30. Week 02 — Synthetic dataset harness, run-level splitting and label mechanics
**Effort:** **10 h**  
**Parent:** `04 W02`

## Objective

Build data/evaluation infrastructure before real data are available.

---

## B-W02-01 — Synthetic runs

Generate synthetic trajectories with:

```text
run_id
thermal trend
door events
cooling state
critical crossing
```

Not to demonstrate model performance.

Only pipeline correctness.

---

## B-W02-02 — Grouped split code

Implement split by:

```text
run_id
```

Add assertion:

```text
train_groups ∩ val_groups = ∅
train_groups ∩ test_groups = ∅
val_groups ∩ test_groups = ∅
```

---

## B-W02-03 — Window generator

Correct pipeline:

```text
split runs
→ window within each split
```

Test overlapping windows never cross partitions.

---

## B-W02-04 — Label generator

Implement horizon-based label from future critical event only after split.

Unit tests around boundary:

```text
event at t+H
event at t+H+ε
```

---

## B-W02-05 — Manifest parser

Read experiment/run metadata.

---

## Deliverables

```text
synthetic-run-generator
group-split-tests
window-generator-tests
label-generator-tests
```

---

## Pass criteria

No synthetic leakage under intentionally adversarial test cases.

---

# 31. Week 03 — Statistical analysis plan and metric definitions
**Effort:** **10 h**  
**Parent:** `04 W03`

## Objective

Freeze methodology before final data.

---

## B-W03-01 — Independent unit declaration

Write clearly:

```text
ML window/sample = dependent observation
run = primary grouped experimental unit
A/B pair = final physical comparative unit
```

---

## B-W03-02 — Metric definitions

Freeze formulas/units for:

- AP;
- precision;
- recall;
- false warnings/run;
- missed events;
- EWT;
- AIW support;
- thermal exposure;
- recovery;
- cooling-branch energy.

---

## B-W03-03 — Paired analysis plan

Predefine:

```text
pair difference
95% CI
bootstrap
parametric/nonparametric decision
invalid pair handling
```

---

## B-W03-04 — Sample-size planning notebook

Implement rough paired-effect planning from Doc 03.

Use pilot variance later.

---

## Deliverables

```text
statistical-analysis-plan-v0.md
metric-spec.md
sample-size-planning.ipynb/py
```

---

# 32. Week 04 — Evaluation freeze v0 and real-schema readiness
**Effort:** **12 h**  
**Parent:** `04 W04`

## Objective

Be ready for real telemetry without inheriting old hardware assumptions.

---

## B-W04-01 — Real schema adaptation

Update analytical schema to single cooling branch.

Assert forbidden legacy fields are not required.

---

## B-W04-02 — EWT definition

Freeze conceptual logic:

```text
first persistent predictive warning
versus
first reactive criterion
```

Only on non-predictively-intervened trajectory.

---

## B-W04-03 — AIW analysis interface

Specify required timing fields from A/C/D.

---

## B-W04-04 — Primary/secondary metric hierarchy

Prevent later metric shopping.

---

## B-W04-05 — Invalid-run intake

Implement/define how A's physical validity status enters dataset selection.

---

## Deliverables

```text
analysis-contract-v1.md
schema-check.py
metric-hierarchy.md
```

---

# 33. Week 05 — Real telemetry QA and physical-data audit
**Effort:** **10 h**  
**Parent:** `04 W05`

## Objective

Verify that real 1 Hz data can support later features.

---

## B-W05-01 — Sampling interval analysis

Compute:

- median Δt;
- P95;
- long gaps;
- run-level completeness.

---

## B-W05-02 — Channel QA

For each run/channel:

- missing;
- impossible;
- flatline;
- duplicate;
- stale;
- quality states.

---

## B-W05-03 — Physical-state plots

Overlay:

```text
T1/T2/T3
door
PZEM P
applied cooling
```

Look for semantic mismatch.

---

## B-W05-04 — QA report format

Make QA executable across new runs.

---

## Deliverables

```text
real-data-qa-v1.py
qa-report-W05.html/md
channel-summary.csv
```

---

## Pass criteria

No unknown unit/identity ambiguity.

If data semantics are unclear:

> stop feature engineering and fix source contract.

---

# 34. Week 06 — Timing alignment and command/response event analysis tools
**Effort:** **10 h**  
**Parent:** `04 W06`

## Objective

Build the timing layer needed for EWT/AIW and later closed-loop analysis.

---

## B-W06-01 — Event alignment

Create unified timeline for:

```text
door transition
telemetry
policy/command
ACK
electrical response
thermal response
```

---

## B-W06-02 — Clock/sequence diagnostics

Use:

- captured time;
- received time;
- boot_id/seq;
- uptime.

Flag suspicious ordering.

---

## B-W06-03 — Response-window helper

Implement analysis function:

```text
command → electrical delay
command → thermal delay
```

with configurable detection method.

---

## B-W06-04 — Duplicate event handling

Ensure retransmission does not create duplicate physical events.

---

# 35. Week 07 — Physical EDA and repeatability analysis
**Effort:** **10 h**  
**Parent:** `04 W07`

## Objective

Understand the plant before modeling it.

---

## B-W07-01 — Baseline EDA

Analyze A's repeated warm-up/cooling runs.

Metrics:

- initial state;
- slope;
- peak;
- recovery;
- gradient;
- electrical load.

---

## B-W07-02 — Run-to-run variation

Report:

- SD/IQR;
- CV where meaningful;
- overlay trajectories.

---

## B-W07-03 — Confounding checklist

Look for:

- ambient/session effect;
- changing initial state;
- sensor drift;
- warming hardware.

---

## B-W07-04 — Pairing inputs

Recommend which initial-state variables must be controlled in A/B.

---

## Deliverables

```text
plant-eda-report.md
repeatability-summary.csv
pairing-candidate-variables.md
```

---

# 36. Week 08 — Gate B data readiness
**Effort:** **12 h**  
**Parent:** `04 W08`

## Objective

Decide whether the physical/digital data path is ready for a real dataset campaign.

---

## B-W08-01 — Run validator

Automate checks:

```text
known hardware config
known calibration
required channels
sequence
timing
quality
event completeness
```

---

## B-W08-02 — Data completeness threshold draft

Use physical/event requirements.

Do not invent universal “99.9%” if not needed.

---

## B-W08-03 — Dataset readiness report

GREEN/YELLOW/RED.

---

## B-W08-04 — Development split strategy

Plan approximate run allocation.

Do not lock final test before enough real runs/scenarios exist.

---

## Exit

No serious XGBoost campaign if Gate B data readiness is RED.

---

# 37. Week 09 — Deterministic baseline and S1 analytical baseline
**Effort:** **12 h**  
**Parent:** `04 W09`

## Objective

Implement baselines before XGBoost.

---

## B-W09-01 — Threshold baseline

Calculate when raw thermal criterion would fire.

---

## B-W09-02 — Hysteresis/persistence baseline

Mirror Controller A semantics analytically.

---

## B-W09-03 — Normal-run false-warning analysis

Use S1 baseline to estimate:

- false triggers;
- stability.

---

## B-W09-04 — Baseline event evaluator

Reusable event-level evaluation module.

---

## Deliverables

```text
baselines/
baseline-report.md
event-evaluator-tests
```

---

# 38. Week 10 — S2 features and causal temporal pipeline
**Effort:** **14 h**  
**Parent:** `04 W10`

## Objective

Build feature version 1 from repeatable door disturbances.

---

## B-W10-01 — Freeze feature registry v1

Include:

- instantaneous thermal;
- gradient;
- rolling history;
- door context;
- actuation;
- electrical context.

---

## B-W10-02 — Rolling feature tests

For each rolling feature:

- first valid timestamp;
- no future sample;
- missing behavior.

---

## B-W10-03 — Door features

Examples:

```text
door_open
time_since_open
duration_so_far
count_past_60s
```

Never use final future open duration before door closes if that would be unavailable online.

---

## B-W10-04 — Label pilot

Evaluate candidate critical criteria/horizons only as development.

---

## B-W10-05 — Feature audit plots

Inspect around events.

---

## Deliverables

```text
feature-registry-v1.yaml
feature-pipeline-v1
feature-causality-tests
S2-feature-report.md
```

---

# 39. Week 11 — XGBoost v1 and grouped benchmark
**Effort:** **15 h**  
**Parent:** `04 W11`

## Objective

Produce the first defensible predictive benchmark.

---

## B-W11-01 — Development split

Use grouped runs.

No random rows.

---

## B-W11-02 — XGBoost baseline configuration

Start simple.

Example baseline family:

```text
tree_method = hist
moderate max_depth
regularization
early stopping / bounded estimators where appropriate
```

Do not over-tune.

---

## B-W11-03 — Grouped CV

Use:

```text
GroupKFold
```

or another explicit run-grouped procedure.

Report fold run IDs.

---

## B-W11-04 — Imbalance

Compare:

- no reweight;
- sensible weighting/threshold strategies.

Do not optimize only ROC-AUC.

---

## B-W11-05 — Baseline comparison

Compare to B0/B1.

---

## B-W11-06 — Leakage audit

Explicit checklist.

---

## Deliverables

```text
xgb-v1-config.yaml
cv-fold-manifest.yaml
xgb-v1-report.md
leakage-audit-W11.md
```

---

## Pass criteria

A model result is valid only if:

```text
group separation proven
features causal
baseline shown
metric unit clear
```

---

# 40. Week 12 — Benchmark report and dataset/control gate
**Effort:** **12 h**  
**Parent:** `04 W12`

## Objective

Decide whether predictive development is worth continuing and on what evidence.

---

## B-W12-01 — Consolidate grouped results

Report distributions across folds/runs.

---

## B-W12-02 — False warning / missed event

Translate model quality into operational terms.

---

## B-W12-03 — Initial EWT

Compute only on valid non-intervened trajectories.

---

## B-W12-04 — Feature importance as diagnostic only

Use XGBoost gain/SHAP only for interpretation, not causal proof.

Do not claim:

```text
feature importance = physical causality
```

---

## B-W12-05 — Gate G3 report

State:

```text
GO
GO WITH LIMITATIONS
NO-GO / FIX DATA
```

---

# 41. Week 13 — Horizon engineering
**Effort:** **12 h**  
**Parent:** `04 W13`

## Objective

Choose prediction horizon from measured plant dynamics, not old 20 L assumptions.

---

## B-W13-01 — Candidate horizons

Evaluate measured candidates such as:

```text
30 s
60 s
120 s
300 s
```

if appropriate.

---

## B-W13-02 — For each horizon report

- positive prevalence;
- AP;
- event recall;
- false warnings;
- median EWT;
- AIW distribution;
- missed events.

---

## B-W13-03 — Select primary horizon

Criteria:

```text
predictive signal
+
actionability
+
false-warning burden
```

Not highest metric alone.

---

## B-W13-04 — Freeze primary horizon candidate

Secondary horizons become sensitivity analysis.

---

## Deliverables

```text
horizon-study.md
horizon-metrics.csv
primary-horizon-decision.md
```

---

# 42. Week 14 — Calibration + A1/A2 ablation
**Effort:** **14 h**  
**Parent:** `04 W14`

## Objective

Test spatial/context value and decide whether model output can be called probability.

---

## B-W14-01 — A1 one sensor vs three

Use same run split/model family.

Feature groups:

```text
one designated T
versus
T1/T2/T3 + spatial features
```

---

## B-W14-02 — A2 thermal vs thermal + door

Same split.

---

## B-W14-03 — Calibration

If project intends probability wording:

evaluate:

- reliability curve;
- Brier;
- calibration method;
- sparse-bin limitations.

Calibration training uses development data only.

---

## B-W14-04 — Score/probability decision

Freeze one:

```text
risk_score only
or
calibrated probability
```

---

## B-W14-05 — EWT + AIW report

Combine A/C/D timing.

---

## Deliverables

```text
A1-report.md
A2-report.md
calibration-report.md
AIW-report.md
```

---

# 43. Week 15 — A3 electrical ablation and model freeze candidate
**Effort:** **12 h**  
**Parent:** `04 W15`

## Objective

Quantify what PZEM/electrical context contributes and prepare deployable model artifact.

---

## B-W15-01 — A3

Compare:

```text
thermal/context
vs
thermal/context + electrical/applied-state features
```

Use same split.

---

## B-W15-02 — Separate prediction value from diagnosis value

Electrical features may be more useful for:

```text
actuator verification / diagnosis
```

than for early prediction.

Report this honestly.

---

## B-W15-03 — Hyperparameter freeze candidate

Stop broad tuning.

---

## B-W15-04 — Model artifact

Export stable model:

```text
model.ubj/json
```

Record SHA-256.

---

## B-W15-05 — Model card draft

Include:

- data;
- features;
- target;
- horizon;
- metrics;
- calibration;
- limitations.

---

## B-W15-06 — Deep model Go/No-Go

Default:

```text
NO-GO
```

Go only if:

- XGBoost clearly misses structured temporal behavior;
- enough independent runs;
- measurable incremental question;
- time remains.

---

# 44. Week 16 — Locked predictive test
**Effort:** **12 h**  
**Parent:** `04 W16`

## Objective

Open the locked holdout once and produce the final offline early-warning claim.

---

## Preconditions

Freeze:

```text
test run IDs
feature version
model version
horizon
threshold
persistence
calibration
```

---

## B-W16-01 — Holdout integrity

Verify test runs never used for:

- tuning;
- feature selection;
- calibration;
- threshold selection.

---

## B-W16-02 — Evaluate once

Produce:

- AP;
- precision/recall;
- false warnings;
- missed events;
- EWT;
- AIW;
- calibration metrics if relevant.

---

## B-W16-03 — Interpret

Possible:

```text
supports predictive usefulness
mixed
does not support
```

Do not retune after reading result.

---

## B-W16-04 — Freeze model release candidate

Model used for shadow/closed-loop if G4 accepts it.

---

## Deliverables

```text
locked-test-manifest
locked-test-result.md
model-rc/
model-card-rc.md
```

---

# 45. Week 17 — Online shadow inference reconciliation
**Effort:** **12 h**  
**Parent:** `04 W17`

## Objective

Prove deployed inference matches offline reference before predictive actuation.

---

## B-W17-01 — Online/offline parity

For same raw window:

```text
offline feature vector
online feature vector
prediction
```

must reconcile within tolerance.

---

## B-W17-02 — Shadow logs

Record:

- predicted risk;
- hypothetical warning;
- hypothetical policy timing.

No physical Controller B action.

---

## B-W17-03 — Feature freshness

Verify live input windows do not accidentally use:

- future late-arriving sample;
- stale PZEM;
- old state after reconnect.

---

## B-W17-04 — Shadow readiness report

No tuning from live shadow unless it reveals implementation bug; any substantive model change reopens version/evaluation process.

---

# 46. Week 18 — Controller B enablement support
**Effort:** **14 h**  
**Parent:** `04 W18`

## Objective

Support predictive physical dry runs while keeping model frozen.

---

## B-W18-01 — Model runtime monitoring

Check:

- correct artifact hash;
- feature version;
- threshold;
- horizon.

---

## B-W18-02 — Predictive intervention trace

For each run:

```text
risk
warning
policy decision
applied command
physical response
```

---

## B-W18-03 — No online tuning

Do not:

```text
adjust threshold after each run
```

because that contaminates final policy freeze.

---

## B-W18-04 — Controller B readiness signoff

Confirm model behaves within expected offline/shadow envelope.

---

# 47. Week 19 — Final paired A/B campaign wave 1
**Effort:** **14 h**  
**Parent:** `04 W19`

## Objective

Maintain statistical integrity of the first half of final A/B campaign.

---

## B-W19-01 — Pair ledger

Track:

```text
pair_id
order
run A
run B
initial-state comparability
validity
```

---

## B-W19-02 — Blinded-ish validity discipline

Where feasible, validity decision uses protocol failures rather than outcome preference.

Do not invalidate because B is worse.

---

## B-W19-03 — No significance peeking

Do not repeatedly recompute headline p-value and stop early.

Can perform:

- data integrity;
- validity;
- safety checks.

---

## B-W19-04 — Pair target progress

Report:

```text
valid pairs completed
invalid attempts
remaining target
```

---

# 48. Week 20 — Final paired A/B campaign wave 2 and analysis unlock
**Effort:** **13 h**  
**Parent:** `04 W20`

## Objective

Complete frozen pair target, then open final physical outcome analysis.

---

## B-W20-01 — Campaign lock verification

Before analysis:

- pair count reached;
- no silent policy change;
- hardware config stable;
- invalid attempts retained.

---

## B-W20-02 — Pair table

Compute for each valid pair:

- thermal exposure;
- recovery;
- peak;
- time above threshold;
- cooling-branch energy;
- other frozen supporting outcomes.

---

## B-W20-03 — Primary pair differences

Use predeclared sign convention.

---

## B-W20-04 — Do not mix EWT claim

Closed-loop B runs are not used to invent unseen future reactive crossing.

---

## Deliverables

```text
pair-ledger-final.csv
pair-outcomes.csv
campaign-integrity.md
```

---

# 49. Week 21 — Resilience/diagnosis evidence analysis
**Effort:** **10 h**  
**Parent:** `04 W21`

## Objective

Analyze non-primary fault/resilience data without reopening the core model.

---

## B-W21-01 — Diagnosis tables

Evaluate:

```text
healthy
electrical response missing
degraded/unknown
```

against controlled scenarios.

---

## B-W21-02 — SAFE_LOCAL outcome summaries

Quantify:

- outage interval;
- physical state;
- recovery;
- resync.

---

## B-W21-03 — Sensor/PZEM degraded data

Check that model/policy behavior matches allowed degraded semantics.

---

## B-W21-04 — Optional energy analysis

Only if optional Gate F opened.

Do not distract from final core evidence.

---

# 50. Week 22 — Final statistics, uncertainty and sensitivity analysis
**Effort:** **10 h**  
**Parent:** `04 W22`

## Objective

Produce the final defensible quantitative result.

---

## B-W22-01 — Paired descriptive analysis

Plot every pair.

Report:

- mean;
- median;
- SD/IQR;
- min/max.

---

## B-W22-02 — 95% CI

Bootstrap at pair level.

Recommended:

```text
5000–10000 resamples
fixed seed
```

---

## B-W22-03 — Test family

Use predeclared paired test.

If assumptions fail:

- robust/nonparametric route;
- document why.

---

## B-W22-04 — Effect size

Report standardized or physically meaningful effect.

Avoid p-value-only conclusion.

---

## B-W22-05 — Sensitivity

Possible:

- with/without one extreme valid pair;
- alternate secondary horizon;
- mean vs median.

Clearly label sensitivity/exploratory.

---

## B-W22-06 — Final limitations

Write honestly:

- small independent N;
- one chamber;
- one hardware unit;
- scenario-specific model;
- no biological quality ground truth.

---

# 51. Week 23 — Model/evidence package and demo result hardening
**Effort:** **10 h**  
**Parent:** `04 W23`

## Objective

Make Member B's result reproducible by another person.

---

## B-W23-01 — Dataset card

Freeze:

- runs;
- splits;
- label;
- features;
- invalidations;
- limitations.

---

## B-W23-02 — Model card

Freeze:

- artifact hash;
- training data;
- XGBoost config;
- horizon;
- threshold;
- calibration;
- test metrics;
- intended use;
- non-use.

---

## B-W23-03 — Final plots

Required set:

- representative physical trajectories;
- PR;
- calibration if used;
- EWT;
- paired A/B effects;
- outcome CI.

Avoid cherry-picked-only plots.

---

## B-W23-04 — Clean analysis run

Another member runs final analysis command.

Fix only reproducibility defects.

---

## B-W23-05 — Demo narrative

Member B can explain in <2 minutes:

```text
how dataset was split
why XGBoost
what model predicts
how early
how actionable
what A/B actually proved
```

---

# 52. Week 24 — Final AI/data handover
**Effort:** **8 h**  
**Parent:** `04 W24`

## Objective

No new modeling.

Hand over a complete predictive/evaluation package.

---

## B-W24-01 — Final artifact checksum

Record hashes for:

- dataset export;
- split manifest;
- model;
- final result CSV;
- key analysis artifact.

---

## B-W24-02 — Reproduce final table

From clean environment:

```text
raw/export
→ analysis
→ final table/figures
```

---

## B-W24-03 — Oral defense drill

Answer:

- why not random rows?
- why AP?
- why score ≠ probability?
- why EWT separated from A/B?
- why XGBoost instead of LSTM?
- what does small N imply?
- what would invalidate the claim?

---

## B-W24-04 — Final handover

Deliver:

```text
dataset card
split manifest
feature registry
model card
model artifact
locked test report
A/B statistics
analysis scripts
figures
limitations
```

---

# 53. Weekly effort summary

| Week | Hours | Primary emphasis |
|---:|---:|---|
| 01 | 10 | claim/data/leakage contract |
| 02 | 10 | synthetic pipeline / grouped split |
| 03 | 10 | statistical analysis plan |
| 04 | 12 | real-schema/evaluation freeze |
| 05 | 10 | real telemetry QA |
| 06 | 10 | timing/event alignment |
| 07 | 10 | physical EDA/repeatability |
| 08 | 12 | Gate B readiness |
| 09 | 12 | deterministic baseline |
| 10 | 14 | feature engineering |
| 11 | 15 | XGBoost grouped benchmark |
| 12 | 12 | benchmark / G3 |
| 13 | 12 | horizon engineering |
| 14 | 14 | calibration + A1/A2 |
| 15 | 12 | A3 + model freeze |
| 16 | 12 | locked predictive test |
| 17 | 12 | shadow reconciliation |
| 18 | 14 | Controller B support |
| 19 | 14 | final A/B wave 1 |
| 20 | 13 | final A/B wave 2 |
| 21 | 10 | resilience/diagnosis analysis |
| 22 | 10 | final statistics |
| 23 | 10 | evidence/model package |
| 24 | 8 | handover |
| **Total** | **278 h** | |

---

# 54. Member B gate responsibilities

## G0

- claims mapped;
- no old hardware schema.

## G1

- analysis method ready;
- no physical result required yet.

## G2

- real data QA;
- run validator;
- split strategy.

## G3

- deterministic baseline;
- grouped XGBoost v1;
- initial EWT;
- leakage audit.

## G4

- primary horizon;
- calibration semantics;
- locked holdout;
- AIW;
- model release candidate.

## G5

- pair ledger;
- final physical outcome table.

## G6

- statistics;
- model/dataset cards;
- reproducible final figures.

---

# 55. Leader review rubric for Member B

Leader should not ask:

```text
accuracy bao nhiêu?
```

only.

Review:

## Independence

- how many runs?
- which split?
- overlap?

## Causality

- feature available at inference?
- any future information?

## Baseline

- threshold/hysteresis result?

## Metrics

- AP / false warnings / missed events / EWT?
- event-level or row-level?

## Calibration

- score or probability?

## Test discipline

- when was test opened?
- any retuning afterward?

## Physical relevance

- is warning actionable?
- does A/B improve a real outcome?

---

# 56. Common failure patterns Member B must avoid

## 56.1 Random 80/20 rows

Forbidden.

Near-identical adjacent samples leak.

---

## 56.2 Window before split

Forbidden.

Overlapping windows cross partitions.

---

## 56.3 Treat 100,000 rows as n=100,000

Scientifically wrong for run-level claims.

---

## 56.4 Accuracy as headline

Weak under imbalance.

Use PR/event/timing metrics.

---

## 56.5 Tune on final test

Forbidden.

---

## 56.6 Call `predict_proba` calibrated by default

Wrong.

Probability calibration must be checked.

---

## 56.7 Deep learning for novelty

Not justified without evidence.

---

## 56.8 Feature importance = causality

Wrong.

At most association/model usage.

---

## 56.9 Compute EWT on altered Controller B future

Wrong.

Intervention changes counterfactual.

---

## 56.10 Exclude bad A/B pair because B loses

Forbidden unless predeclared run invalidity is independently met.

---

# 57. XGBoost model-card minimum

```text
Model ID:
XGBoost version:
Artifact SHA-256:

Prediction target:
Primary horizon:
Critical criterion:

Training dataset:
Validation dataset:
Locked test dataset:

Feature version:
Features:

Hyperparameters:
Class weighting:
Random seed:

Decision threshold:
Persistence:

Calibration:
Probability wording allowed?:

Validation metrics:
Locked test metrics:
EWT:
AIW:

Known failure modes:
Intended use:
Not intended for:
```

---

# 58. Dataset-card minimum

```text
Dataset ID:
Hardware config:
Date range:
Scenarios:
Number of valid runs:
Number of invalid/aborted attempts:
Sampling cadence:
Fields:
Quality logic:

Label:
Horizon:
Critical criterion:

Train runs:
Validation runs:
Test runs:

Window generation:
Missing handling:
Exclusions:

Limitations:
```

---

# 59. Final A/B statistics package

```text
campaign manifest
pair ledger
per-run outcomes
per-pair improvement
bootstrap configuration
95% CI
paired test result
effect size
sensitivity
all-pair plot
representative trajectories
limitations
```

---

# 60. Reference sources for Member B

**[R1] scikit-learn — GroupKFold.**  
GroupKFold uses non-overlapping groups; each group is assigned as a whole to a fold. ColdGuard maps the group to `run_id`.  
https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html

**[R2] scikit-learn — Precision-Recall.**  
Precision-recall is particularly useful when classes are highly imbalanced.  
https://scikit-learn.org/stable/auto_examples/model_selection/plot_precision_recall.html

**[R3] scikit-learn — Average Precision.**  
AP summarizes the precision-recall relation using changes in recall as weights.  
https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html

**[R4] scikit-learn — Probability calibration / calibration curves.**  
Reliability diagrams compare predicted probabilities against observed positive fractions; bin count must respect available data.  
https://scikit-learn.org/stable/modules/calibration.html  
https://scikit-learn.org/stable/modules/generated/sklearn.calibration.calibration_curve.html

**[R5] scikit-learn — Brier score loss.**  
Proper probabilistic score used as supporting evidence when probability semantics are claimed.  
https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html

**[R6] XGBoost — Parameters.**  
Official parameter reference including `scale_pos_weight` for imbalanced classification and `hist` tree method.  
https://xgboost.readthedocs.io/en/stable/parameter.html

**[R7] XGBoost — Notes on Parameter Tuning.**  
Official tuning guidance, including the distinction between class weighting for overall discrimination and probability prediction considerations.  
https://xgboost.readthedocs.io/en/latest/tutorials/param_tuning.html

**[R8] XGBoost — Introduction to Model IO.**  
Stable saved-model format versus unstable memory snapshots/pickle.  
https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html

**[R9] NIST/SEMATECH Engineering Statistics Handbook.**  
Engineering experiment design, comparison, uncertainty and statistical interpretation.  
https://www.nist.gov/programs-projects/nistsematech-engineering-statistics-handbook

**[R10] NIST/SEMATECH — Paired observations / confidence intervals / bootstrap.**  
Paired differences and bootstrap uncertainty methods applicable to ColdGuard's matched A/B analysis.  
https://www.itl.nist.gov/div898/handbook/prc/section3/prc311.htm  
https://www.itl.nist.gov/div898/handbook/prc/section3/prc312.htm  
https://www.itl.nist.gov/div898/handbook/eda/section3/bootplot.htm

---

# 61. Final handover checklist

## Data

- [ ] dataset IDs/manifests;
- [ ] all run IDs;
- [ ] invalid-run records;
- [ ] split manifest;
- [ ] no overlap.

## Features

- [ ] feature registry;
- [ ] causal audit;
- [ ] missing-data behavior;
- [ ] version.

## Model

- [ ] XGBoost stable artifact;
- [ ] SHA-256;
- [ ] hyperparameters;
- [ ] model card;
- [ ] locked test.

## Metrics

- [ ] baseline;
- [ ] AP/PR;
- [ ] false warnings;
- [ ] missed events;
- [ ] EWT;
- [ ] AIW;
- [ ] calibration status.

## Ablation

- [ ] A1;
- [ ] A2;
- [ ] A3;
- [ ] A4 baseline/model.

## Closed loop

- [ ] pair ledger;
- [ ] physical outcomes;
- [ ] CI;
- [ ] effect size;
- [ ] no counterfactual EWT misuse.

## Reproducibility

- [ ] environment;
- [ ] seeds;
- [ ] analysis command;
- [ ] final figures regenerated.

---

# 62. North star

> **Member B succeeds when the team can defend every predictive number by pointing to the exact independent runs, exact split, exact causal feature pipeline, exact frozen model and exact physical event behind it.**

> **A high model score is optional. Scientific honesty is not.**

> **The strongest AI claim ColdGuard can make is not “XGBoost is accurate.” It is: on held-out independent physical trajectories, the model produced useful advance warning beyond a deterministic baseline; that warning was early enough relative to measured plant response; and when used through the frozen safety policy, the final matched experiment showed exactly what physical effect did—or did not—improve.**
