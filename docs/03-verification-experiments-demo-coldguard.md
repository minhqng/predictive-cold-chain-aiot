# COLDGUARD — HỆ THỐNG BẢO VỆ CHUỖI LẠNH CHỦ ĐỘNG
## Verification · Experiments · Evidence · Statistical Evaluation · Demo / Defense Contract

> **Document:** `docs/03-verification-experiments-demo.md`  
> **Course:** Internet of Things (IoT) — Course Project / Bài tập lớn  
> **Project:** **ColdGuard — Hệ thống bảo vệ chuỗi lạnh chủ động**  
> **Type:** Verification Specification + Experimental Protocol + Statistical Analysis Plan + Evidence Contract + Demo/Defense Runbook Baseline  
> **Status:** **PROPOSED FREEZE v1.0 — REVIEW CANDIDATE**  
> **Baseline date:** **2026-09-29**  
> **Parents:** `00-project-scope-architecture.md`, `01-physical-measurement-correctness-contract.md`, `02-aiot-closed-loop-engineering.md`  
> **Children:** `04-team-execution-plan.md`, `05A/05B/05C/05D`  
> **Normative role:** source of truth for how ColdGuard claims are verified: commissioning tests, physical characterization, valid-run criteria, dataset construction, label protocol, leakage prevention, predictive-model evaluation, paired closed-loop A/B experiments, ablation, fault/resilience/security campaigns, statistical reporting, evidence packaging, release gates, final demo and defense claims.  
> **Not source of truth for:** hardware identity/measurement meaning (`00/01`), runtime MQTT/backend/control semantics (`02`), ownership/calendar (`04`), or weekly issue sequence (`05A–05D`).  
> **Hardware constraint:** all physical experiments use the exact frozen P0 hardware unless the run is explicitly tagged with a different approved `hardware_config_id`. No experiment may silently substitute INA226, a second TEC, a different chamber, a different shunt or a different driver while remaining in the same comparison block.  
> **Evidence rule:** screenshots, dashboards and videos are supporting evidence only. Report-grade proof requires raw/normalized records, run manifests, configuration/version provenance, automated assertions where applicable and a reproducible analysis artifact.  
> **Change policy:** changing a primary outcome, final test split, label definition, critical threshold semantics, paired-run acceptance criterion, run exclusion rule, model-selection criterion or final statistical method after examining locked test/A-B results requires an explicit amendment and must be disclosed as post-hoc.

> **Verification thesis.**  
> **ColdGuard is credible only if every important claim is linked to a controlled question, a reproducible experiment, an authoritative oracle, a predeclared validity rule and preserved raw evidence. The goal is not to manufacture a positive result; the goal is to know exactly what the purchased system did, under which configuration, and what the data actually support.**

---

# 0. How to use this document

For every test or experiment, answer:

1. **What claim is being tested?**
2. **Which system state is authoritative?**
3. **What is held constant?**
4. **What is deliberately changed?**
5. **What constitutes one independent experimental unit?**
6. **What can fail during the run?**
7. **What makes the run invalid?**
8. **Which raw records prove the outcome?**
9. **What analysis is allowed before the final data are opened?**
10. **What exact conclusion is allowed if the result is positive, neutral or negative?**

Each verification item follows the pattern:

```text
claim
→ setup
→ controlled variable
→ procedure
→ oracle
→ evidence
→ pass/fail or quantitative result
→ allowed conclusion
```

---

# 1. Verification philosophy

## 1.1 Evidence beats screenshots

Weak:

```text
dashboard looks normal
```

Stronger:

```text
raw telemetry
+ command record
+ ACK
+ PZEM response
+ thermal response
+ automated analysis
```

A screenshot may illustrate the result.

It does not establish it.

---

## 1.2 Test the failure boundary, not only happy path

If a claim says:

> stale command is rejected

then the project must send a stale command.

If a claim says:

> duplicate QoS delivery is harmless

then a duplicate must be injected.

If a claim says:

> SAFE_LOCAL protects during backend loss

then the backend/broker path must actually be removed during an active run.

---

## 1.3 Physical truth outranks software self-report

For an actuation claim:

```text
backend says command published
```

is weaker than:

```text
device ACK
```

which is weaker than:

```text
PZEM electrical response
```

which is still not identical to:

```text
thermal response
```

Final conclusions follow Doc 01 authority.

---

## 1.4 Statistical significance is not engineering significance

A small p-value does not imply a useful cooling improvement.

A useful physical effect with wide uncertainty is still worth reporting honestly.

The analysis must combine:

- effect magnitude;
- confidence interval;
- physical meaning;
- statistical evidence.

NIST/SEMATECH explicitly distinguishes statistical significance from practical engineering significance.

---

## 1.5 One telemetry row is not one independent experiment

At 1 Hz:

```text
30-minute run = 1800 rows
```

Those rows belong to one strongly autocorrelated trajectory.

Therefore:

```text
n ≈ number of independent runs/pairs
```

for system-level inference.

---

## 1.6 Negative result is valid

Examples:

- XGBoost does not materially beat hysteresis.
- Predictive warning is early but not actionable.
- Predictive control uses more energy without thermal benefit.
- PZEM PWM readings are too uncertain for strong energy claims.

A valid negative result is stronger than an invalid positive result.

---

# 2. Claim-to-proof matrix

| Claim ID | Claim | Primary proof |
|---|---|---|
| **CL-01** | exact purchased hardware operates safely | H0–H7 commissioning evidence |
| **CL-02** | T1/T2/T3 identity is stable | ROM mapping + reboot test |
| **CL-03** | branch V/I/P are usable observations | PZEM profile + reference/plausibility characterization |
| **CL-04** | command is distinct from physical effect | command/ACK/electrical/thermal trace |
| **CL-05** | multi-point sensing adds information | A1 ablation |
| **CL-06** | model can warn before reactive criterion | locked offline predictive test |
| **CL-07** | warning is physically actionable | EWT minus measured response/latency budget |
| **CL-08** | predictive closed loop improves physical outcome | paired Controller A/B campaign |
| **CL-09** | electrical telemetry improves verification/diagnosis | A3 + controlled fault evidence |
| **CL-10** | SAFE_LOCAL survives network/backend loss | outage campaign |
| **CL-11** | duplicate/stale/unauthorized commands are safe | protocol/security negative tests |
| **CL-12** | experiment is reproducible | clean replay + manifest + analysis package |

---

# 3. Evidence classes

## E0 — Configuration evidence

Examples:

- hardware config;
- pin map;
- sensor ROM map;
- firmware/model/policy versions;
- calibration ID.

---

## E1 — Raw machine evidence

Examples:

- telemetry JSON;
- database export;
- PZEM samples;
- command records;
- event logs.

---

## E2 — Automated assertions

Examples:

- test output;
- SQL assertions;
- schema validation;
- calculated pass/fail.

---

## E3 — Analysis evidence

Examples:

- notebook/script output;
- CSV summary;
- confidence interval;
- metric table;
- figure.

---

## E4 — Human-visible demonstration

Examples:

- photo;
- wiring image;
- dashboard screenshot;
- video.

E4 supports E0–E3.

It does not replace them.

---

# 4. Evidence directory baseline

```text
evidence/
├─ commissioning/
│  ├─ H0-mechanical/
│  ├─ H1-sensors/
│  ├─ H2-logic-power/
│  ├─ H3-pzem-rs485/
│  ├─ H4-ibt2-logic/
│  ├─ H5-power-branch/
│  ├─ H6-tec-low-power/
│  ├─ H7-characterization/
│  └─ H8-closed-loop/
│
├─ calibration/
├─ runs/
│  └─ <run_id>/
│
├─ ai/
│  ├─ dataset/
│  ├─ splits/
│  ├─ models/
│  ├─ calibration/
│  └─ ablation/
│
├─ control/
├─ resilience/
├─ security/
├─ final-ab/
├─ final-demo/
└─ final-report/
```

---

# 5. Evidence-grade run manifest

Each physical run has a manifest.

Conceptual:

```yaml
run_id: CG-S2-A-001
pair_id: PAIR-001
scenario_id: S2_DOOR_DISTURBANCE
controller_id: REACTIVE

date: 2026-...
operator: ...

hardware_config_id: CG-HW-001
pin_map_version: pin-v1
firmware_version: fw-v...
backend_version: <git sha>
schema_version: 1
calibration_id: CG-CAL-...
feature_version: feat-v...
model_version: model-v...
policy_version: policy-v...

initial_condition:
  target_state: ...
  tmean_c: ...
  tmax_c: ...
  gradient_c: ...
  ambient_context: ...
  door: CLOSED

disturbance:
  type: DOOR_OPEN
  duration_s: ...
  protocol_version: ...

start_time: ...
end_time: ...

validity:
  status: PENDING
  reasons: []

notes: ...
```

---

# 6. Run lifecycle

Canonical:

```text
PLANNED
→ ARMED
→ RUNNING
→ COMPLETED_RAW
→ VALIDITY_REVIEW
→ VALID
or
→ INVALID
or
→ ABORTED
```

A run is not `VALID` merely because data exist.

---

# 7. Run invalidation principles

## Predeclared exclusion

Allowed:

- required sensor missing;
- wrong PZEM profile;
- door disturbance not executed within frozen tolerance;
- physical assembly changed;
- telemetry gap covers primary event;
- safety stop;
- operator intervention not in protocol;
- hardware config unknown.

---

## Forbidden post-hoc exclusion

Not allowed:

```text
remove run because Controller B performed badly
remove outlier because it weakens significance
remove false warning because it “looks weird”
```

Unless the run independently violates a predeclared validity rule.

---

# 8. Configuration comparability

A/B or ablation comparison must record:

- same approved hardware configuration;
- same sensor positions;
- same calibration family;
- same critical-boundary definition;
- same outcome definition.

If not:

- block/stratify;
- or do not pool.

---

# 9. Campaign stages

## Stage C0 — Commissioning

Purpose:

> prove hardware can safely produce meaningful data.

Not used as final ML test evidence.

---

## Stage C1 — Plant characterization / pilot

Purpose:

- understand time constants;
- estimate variance;
- freeze disturbance protocol;
- freeze candidate threshold/horizon;
- estimate effect sizes.

Development data.

---

## Stage C2 — Predictive dataset development

Purpose:

- train/validate XGBoost;
- develop features;
- select hyperparameters;
- calibrate if probability is claimed.

Must preserve a locked independent holdout.

---

## Stage C3 — Shadow integration

Purpose:

- online inference;
- no predictive physical actuation;
- verify semantics/timing.

---

## Stage C4 — Closed-loop A/B

Purpose:

- compare reactive and predictive physical outcome.

Model/policy frozen.

---

## Stage C5 — Resilience/security

Purpose:

- failure/replay/stale/ACL/fallback evidence.

---

## Stage C6 — Final reproducibility/demo

Purpose:

- clean run;
- evidence package;
- defense.

---

# 10. Planning envelope for total runs

The 6 L chamber makes the old long-run assumptions obsolete.

Initial planning envelope:

```text
C1 pilot/characterization:          ~8 valid runs
C2 predictive dataset:             ~24 valid runs
C4 final paired A/B:               ~24–32 valid runs
                                  ------------
total planned valid physical runs: ~56–64
```

Commissioning tests are not counted in this total.

This is a planning envelope, not a forced final `n`.

After pilot variance/effect estimates:

- increase or reduce final A/B pairs;
- document rationale before opening final outcome.

---

# 11. Runtime calculation

If mean valid run duration is 20 minutes:

### 56 runs

\[
56\times20=1120\text{ min}=18.7\text{ h}
\]

### 64 runs

\[
64\times20=1280\text{ min}=21.3\text{ h}
\]

If 30 minutes:

\[
56\times30=28\text{ h}
\]

\[
64\times30=32\text{ h}
\]

This is manageable across a 24-week project.

---

# 12. Sample-size planning for paired A/B

For a paired effect:

\[
d_z=\frac{\delta}{\sigma_d}
\]

where:

- \(\delta\): target mean paired improvement;
- \(\sigma_d\): SD of paired differences.

A rough normal-approximation planning formula for:

```text
two-sided α = 0.05
power ≈ 0.80
```

is:

\[
n\approx\left(\frac{1.96+0.84}{d_z}\right)^2
\]

Planning table:

| Standardized paired effect \(d_z\) | Approx. pairs |
|---:|---:|
| 1.0 | 8 |
| 0.8 | 13 |
| 0.7 | 16 |
| 0.6 | 22 |
| 0.5 | 32 |
| 0.4 | 49 |

This is **planning guidance**, not an exact guarantee.

Implication:

> 12–16 pairs are reasonable only if pilot suggests a fairly large and repeatable effect.

If pilot shows moderate effect/large variance, more pairs are needed or the project must report wider uncertainty.

---

# 13. Pilot re-estimation rule

Before final A/B:

1. estimate paired-like variance from repeated matched pilot disturbances;
2. define minimum engineering-relevant difference;
3. compute rough required pairs;
4. compare with available project runtime;
5. freeze final target pair count;
6. do not change it merely because early final results are inconvenient.

---

# 14. Commissioning H0 — mechanical

## Test `HW-H0-01` — V1/TEC mechanical assembly

**Setup**

No TEC electrical power.

**Verify**

- V1 physically secure;
- TEC seated evenly;
- thermal paste thin/even;
- fan mounted;
- cold side inside chamber;
- hot side outside;
- penetration sealed.

**Evidence**

- photographs;
- assembly checklist;
- hardware config.

**Pass**

No loose component, gross gap or ambiguous orientation.

---

## Test `HW-H0-02` — sensor placement freeze

Verify:

```text
T1 near door
T2 center
T3 far/opposite
BME location frozen
MC-38 alignment frozen
```

Evidence:

- labeled photograph;
- dimensional/relative-position sketch.

---

# 15. Commissioning H1 — sensor subsystem

## `SEN-H1-01` — DS18B20 discovery

Expected:

```text
3 unique ROM IDs
```

Record exact mapping.

---

## `SEN-H1-02` — reboot identity

Procedure:

- boot;
- record roles;
- reset/reboot repeatedly.

Pass:

```text
same ROM → same T role
```

---

## `SEN-H1-03` — inter-sensor consistency

Place three probes under common stable condition.

Measure:

- pairwise offsets;
- variance;
- stability.

If no traceable reference exists:

> report as consistency check, not certified calibration.

---

## `SEN-H1-04` — BME280 check

Verify:

- device responds;
- T/RH plausible;
- no obvious self-heating/mounting anomaly.

---

## `SEN-H1-05` — MC-38 polarity/debounce

Physical open/close cycles.

Pass:

- semantic `OPEN/CLOSED` matches physical state;
- transition reliable.

---

# 16. Commissioning H2 — logic power

## `PWR-H2-01` — XL4015 output

Before modules:

- measure output;
- adjust to intended 5 V logic rail.

Pass:

- within module-safe acceptable range.

Record actual measured voltage.

---

## `PWR-H2-02` — no back-power anomaly

Check development USB/logic-power combination according to actual board.

If behavior uncertain:

- use one documented development power path.

---

# 17. Commissioning H3 — PZEM / RS-485

## `ELEC-H3-01` — MAX3485 power

Verify:

```text
VCC = 3.3 V class
```

not 5 V.

---

## `ELEC-H3-02` — Modbus communication

Try shipped/documented serial profile.

If no response:

- A/B;
- power;
- address;
- CRC;
- 8N1/8N2 revision check.

---

## `ELEC-H3-03` — shunt profile

Read/set:

```text
50 A profile
```

Pass before current becomes evidence-grade.

---

## `ELEC-H3-04` — zero/off response

TEC branch OFF.

Record:

- voltage;
- current;
- power;
- noise floor.

Freeze candidate OFF envelope from repeated samples.

---

# 18. Commissioning H4 — IBT-2 logic

## `ACT-H4-01` — default OFF boot

Power logic/driver in safe setup.

Test:

- cold boot;
- reset;
- firmware restart.

Pass:

```text
no unintended TEC energization
```

---

## `ACT-H4-02` — 3.3 V control compatibility

Verify actual purchased IBT-2 responds deterministically to ESP32 outputs.

---

## `ACT-H4-03` — direction

With conservative safe power:

- identify cooling polarity;
- freeze.

No normal reverse operation.

---

# 19. Commissioning H5 — power branch

## `PWR-H5-01` — fuse present

Verify selected temporary/commissioning fuse installed.

Never bypass.

---

## `PWR-H5-02` — high-current path

Inspect:

- 2×2.5 mm² path;
- TB4504;
- IBT-2 terminals;
- shunt terminals;
- no Dupont/PCT218 in TEC current path.

---

## `PWR-H5-03` — fan

Verify V1 fan operates whenever TEC can be activated.

---

# 20. Commissioning H6 — conservative TEC test

## `THERM-H6-01` — first actuation

Start at conservative approved control level.

Observe:

- branch current;
- branch power;
- intended cold face;
- hot-side heat rejection;
- connector/wire temperature by safe inspection.

Stop on abnormal behavior.

---

## `THERM-H6-02` — response sign

Pass:

```text
cooling command
→ electrical response
→ chamber-side temperature trend eventually shifts in cooling direction
```

---

# 21. Commissioning H7 — characterization matrix

Characterization operating points:

```text
OFF
low/limited point if available
nominal/core ON point
additional PWM points only if safe/needed
```

At each point record:

- voltage;
- current;
- power;
- applied duty/state;
- T1/T2/T3;
- BME;
- door;
- duration;
- module/terminal observations.

---

# 22. H7 stop conditions

Stop a characterization point if:

- abnormal smell;
- visible connector damage;
- excessive/unexpected heating;
- fan failure;
- PSU instability;
- IBT-2 protection cycling;
- hot-side runaway;
- sensor data invalid in a way that removes safe visibility.

Exact temperature limits are based on known component constraints where measurable.

Do not invent uninstrumented junction temperature.

---

# 23. H7 output parameters

Freeze:

```text
healthy_current_range
healthy_power_range
OFF_current_envelope
core_allowed_duty/state
electrical_response_time
thermal_response_window
cooldown_curve
warmup_curve
gradient_baseline
run_reset criterion
```

---

# 24. Fuse finalization

Use measured current, wiring and terminal behavior.

The final fuse is selected from purchased:

```text
10 A / 15 A / 20 A
```

Decision evidence includes:

- steady current;
- observed transient;
- terminal/fuse-holder behavior;
- reason.

Do not choose by TEC name alone.

---

# 25. PZEM reference characterization

If a trusted reference meter is available:

At multiple operating points compare:

```text
PZEM current
reference current
PZEM voltage
reference voltage
```

Calculate:

\[
e_I=I_{PZEM}-I_{ref}
\]

\[
e_V=V_{PZEM}-V_{ref}
\]

Report:

- bias;
- absolute/relative differences;
- repeatability.

If no adequate reference:

> call the process plausibility characterization, not calibration.

---

# 26. PZEM PWM characterization

Only required if PWM energy becomes a quantitative claim.

For each duty:

```text
duty
reported V/I/P
reference/expected trend
temperature response
```

Questions:

- is PZEM power monotonic with duty?
- approximately linear?
- unstable?
- aliasing/averaging suspicious?

If unresolved:

> PWM energy optimization remains outside final primary claims.

---

# 27. Commissioning H8 — closed-loop baseline

Use Controller A first.

Trace:

```text
state
→ policy
→ command
→ device ACK
→ PZEM response
→ thermal response
→ verification
```

Pass before predictive physical actuation.

---

# 28. H8 assertion set

For one valid ON action:

- command ID exists;
- command unexpired;
- ACK accepted;
- applied state ON;
- current enters active envelope;
- thermal response appears inside response window;
- verification reaches expected terminal state.

For OFF:

- applied state OFF;
- current returns to OFF envelope.

---

# 29. Plant characterization experiments

## `CHAR-01` — passive warm-up

Starting near stable cooled state:

- cooling OFF;
- door closed;
- observe passive warming.

Purpose:

- natural thermal drift;
- slope distribution;
- response timescale.

---

## `CHAR-02` — cooling step response

From reproducible warm initial state:

- command core ON;
- observe until stable/recovery criterion.

Purpose:

- delay;
- slope;
- recovery time;
- spatial gradient.

---

## `CHAR-03` — repeated door disturbance

Fixed door-open protocol.

Purpose:

- run-to-run variance;
- disturbance reproducibility;
- candidate prediction horizon.

---

# 30. Characterization summary statistics

For repeated runs report:

- median/mean initial state;
- gradient;
- peak;
- recovery;
- within-scenario variance;
- coefficient of variation where meaningful;
- visual trajectories.

This pilot variance feeds sample-size planning.

---

# 31. Scenario definitions

## S1 — NORMAL_BASELINE

No deliberate disturbance.

Purpose:

- nominal distribution;
- false-warning behavior;
- energy/cooling baseline.

---

## S2 — DOOR_DISTURBANCE

Controlled door opening.

Purpose:

- realistic rapid thermal disturbance;
- prediction;
- recovery;
- A/B comparison.

This is the **primary final A/B scenario** unless pilot shows poor repeatability.

---

## S3 — THERMAL_EFFECTIVENESS_DEGRADATION

Conditional only.

Requires a safe, repeatable method that produces:

```text
electrical response remains plausible
thermal effectiveness worsens
```

If no clean method exists:

> S3 is omitted from core fault claims.

Do not damage the TEC/V1 merely to create a label.

---

## S4 — ACTUATION_RESPONSE_FAULT

Safe software/test-mode fault:

```text
backend requests ON
device/test harness intentionally prevents physical actuation
```

Expected:

```text
ACK/rejection semantics explicit
or
applied state/electrical response reveals non-actuation
```

No short circuit.

---

## S5 — CONNECTIVITY_LOSS

Broker/backend path removed.

Purpose:

- SAFE_LOCAL;
- buffer/reconnect;
- stale-command prevention.

---

## S6 — SENSOR/OBSERVATION_DEGRADED

Controlled low-voltage sensor/communication unavailability.

Examples:

- one DS18B20 missing;
- PZEM communication unavailable.

Purpose:

- explicit degraded state;
- fallback behavior.

---

# 32. Door-disturbance protocol

Final protocol freezes:

- chamber initial-state criterion;
- door opening geometry;
- open duration;
- whether door fully opens;
- close action;
- no manual touching inside;
- controller condition.

A human-operated door event must still be reproducible enough to pair experiments.

---

# 33. Door duration selection

Do not choose a duration merely to guarantee model success.

Pilot should find a duration that:

- produces measurable disturbance;
- does not immediately make prediction meaningless;
- allows both reactive and predictive dynamics to be observed;
- remains safe/repeatable.

Freeze before final A/B.

---

# 34. Initial-condition reset

Final runs start based on **state**, not only clock time.

Candidate state criterion:

```text
Tmean within frozen start band
gradient below frozen maximum
door closed
cooling state known
physical quality valid
```

Exact values freeze after pilot.

---

# 35. Pair-matching criterion

For Controller A/B pair:

- same scenario protocol;
- same hardware config;
- same disturbance duration;
- comparable initial Tmean;
- comparable initial gradient;
- ambient context recorded.

Candidate pilot-era tolerances may include:

```text
|Δ initial Tmean| <= ~0.5 °C
|Δ initial gradient| <= ~0.3 °C
```

These are **candidate values only**.

Final tolerances freeze from pilot repeatability before the A/B campaign.

---

# 36. Pair order randomization

Within each pair, order:

```text
A then B
or
B then A
```

is randomized/balanced where practical.

Reason:

- ambient drift;
- hardware warming;
- operator learning;
- time-of-day effects.

---

# 37. Blocking

Potential blocks:

- day/session;
- ambient band;
- hardware configuration;
- major reassembly.

Pairing within a block reduces nuisance variance.

---

# 38. Primary A/B controller definitions

## Controller A

```text
REACTIVE
threshold + hysteresis
same core allowed cooling action
```

## Controller B

```text
PREDICTIVE
XGBoost risk
→ persistence/policy
→ same core allowed cooling action earlier
```

Core comparison primarily changes **timing**.

---

# 39. Why offline prediction and closed-loop evaluation are separate

This is mandatory.

## Offline early-warning proof

Use trajectories whose future is not altered by predictive intervention.

Then:

```text
future threshold crossing
```

is observable.

---

## Closed-loop Controller B run

Once predictive action occurs:

```text
future trajectory changes
```

If B prevents the critical threshold:

- the unobserved counterfactual critical time is unknown.

Therefore do **not** compute fake EWT using a critical crossing that never happened.

---

# 40. Correct evidence split

### Claim “prediction is earlier”

Use:

```text
locked observational/reactive trajectories
```

### Claim “prediction improves physical outcome”

Use:

```text
paired Controller A vs B physical runs
```

This avoids counterfactual confusion.

---

# 41. Critical-state label

Core binary target:

> Will the predefined representative thermal criterion cross the frozen critical boundary within horizon \(H\)?

For sample at time \(t\):

\[
y_t(H)=
\begin{cases}
1 & \text{if critical event occurs in }(t,t+H]\\
0 & \text{otherwise}
\end{cases}
\]

---

# 42. Critical boundary selection

`T_critical` is a **testbed research boundary**.

It is not automatically:

- food safety limit;
- commodity regulatory threshold.

Selection process:

1. characterize stable target;
2. characterize door disturbance;
3. choose physically meaningful upper boundary;
4. ensure enough positive/negative development events;
5. freeze before locked evaluation.

---

# 43. Representative temperature for critical event

Candidate choices:

- `Tmax`;
- `Tmean`;
- named probe.

Final choice must be frozen before label generation for final splits.

Recommended for protection-oriented interpretation:

> consider `Tmax` as a conservative candidate, but justify empirically.

Do not choose the representation after comparing which gives the best model score.

---

# 44. Prediction horizon selection

Candidate exploratory horizons:

```text
30 s
60 s
120 s
300 s
```

because the 6 L plant may be fast.

Pilot evaluates:

- event prevalence;
- lead time;
- response time;
- control relevance.

Freeze one primary horizon before final test.

Secondary horizons may be reported as exploratory.

---

# 45. Label contamination rule

A prediction-training label must not depend on:

- future predictive intervention;
- future feature values leaked into input.

Core predictive dataset should primarily use:

- baseline;
- reactive;
- controlled observation trajectories.

---

# 46. Window generation

Correct order:

```text
run-level split
→ assign train/validation/test runs
→ generate windows within each split
```

Forbidden:

```text
generate overlapping windows from all runs
→ random row/window split
```

because nearly identical windows can cross partitions.

---

# 47. Grouped split

Use:

```text
group = run_id
```

at minimum.

Scikit-learn `GroupKFold`/`GroupShuffleSplit` explicitly keep groups non-overlapping across train/test partitions.

For final project:

- locked test runs chosen once;
- no hyperparameter tuning on them.

---

# 48. Suggested development split

For ~24 predictive-dataset runs, a practical planning shape:

```text
train/development: ~16 runs
validation:         ~4 runs
locked test:        ~4 runs
```

This is a minimum-sized split and may be statistically noisy.

Prefer more runs if feasible.

Alternative:

- reserve 6–8 locked test runs;
- use grouped CV on remaining development runs.

The exact split freezes after C1/C2 availability is known.

---

# 49. Final test lock

When final test run IDs are frozen:

- record IDs in versioned file;
- do not inspect test labels/metrics during tuning;
- model/policy selection uses train/validation only.

---

# 50. Hyperparameter selection

Primary model:

```text
XGBoost
```

Search space must be bounded.

Do not perform giant search that overfits a tiny run count.

Prefer:

- simple baseline;
- limited tuning;
- stability across grouped folds.

---

# 51. Predictive baselines

Mandatory:

## B0

Simple temperature threshold.

## B1

Threshold + hysteresis/persistence.

## B2

Optional simple statistical/logistic baseline if useful.

## M1

XGBoost.

XGBoost is not allowed to compete only against “no model.”

---

# 52. Primary predictive metric

Because positive impending-critical samples may be less frequent:

> **Average Precision / precision-recall behavior** is a primary discrimination metric candidate.

Scikit-learn notes precision-recall is especially useful when classes are very imbalanced.

---

# 53. Supporting predictive metrics

Report:

- precision;
- recall;
- F1 at frozen operating threshold;
- false warnings/event or per time;
- missed critical events;
- ROC-AUC as secondary if desired;
- confusion matrix at event/sample level with clear unit;
- Early Warning Lead Time.

Accuracy alone is not sufficient.

---

# 54. Event-level versus sample-level metrics

A 60-second warning episode should not be counted as 60 independent true positives.

Define event-level logic.

Example:

```text
one impending critical event
→ model may emit many positive samples
→ count warning episode/event behavior separately
```

---

# 55. Early Warning Lead Time

For an offline/reactive trajectory:

\[
EWT=t_{reactive}-t_{predictive}
\]

where:

- `t_predictive`: first valid persistent predictive warning;
- `t_reactive`: first reactive criterion time.

Positive:

```text
prediction earlier
```

Negative:

```text
prediction later
```

No warning:

- missed event.

---

# 56. Actionable Intervention Window

\[
AIW=t_{critical}-t_{warning}-T_{system}-T_{physical}
\]

Where:

- \(T_{system}\): sensing + inference + policy + command overhead;
- \(T_{physical}\): measured response delay.

Alternative equivalent definition may use empirical command→response delay.

Positive AIW:

> warning is early enough for the measured system to start affecting the plant before the ordinary critical boundary.

---

# 57. Latency components

Measure separately:

```text
sample→backend
feature/inference
policy
command publish
device receive/ACK
command→electrical response
command→thermal response
```

Do not hide all under one “latency” number.

---

# 58. Calibration of probability

If UI/report says:

```text
P(critical within H) = 0.72
```

probability calibration is required.

Use:

- reliability/calibration curve;
- Brier score;
- calibration method fit on development data only.

Scikit-learn defines Brier score as mean squared difference between predicted probability and outcome.

---

# 59. Score-only mode

If calibration is weak or data insufficient:

report:

```text
risk_score
```

not probability.

This does not invalidate the classifier.

---

# 60. Calibration leakage rule

Do not calibrate on locked final test.

Calibration fits on:

- training/calibration subset;
- or grouped development folds.

---

# 61. A1 — one temperature versus three

Compare feature sets:

```text
A1a: one designated temperature
A1b: T1/T2/T3 + derived spatial features
```

Same model family/split.

Question:

> does spatial observation improve predictive/state evidence?

---

# 62. A2 — thermal versus thermal + door

```text
A2a: thermal
A2b: thermal + MC-38 door context
```

---

# 63. A3 — thermal versus thermal + electrical

```text
A3a: thermal/context
A3b: + cooling current/power/applied state
```

Evaluate diagnosis/verification and predictive contribution separately.

---

# 64. A4 — deterministic versus XGBoost

Compare:

- threshold/hysteresis;
- XGBoost risk.

Use held-out grouped runs.

---

# 65. A5 — reactive versus predictive closed loop

Physical A/B campaign.

Primary system-level proof.

---

# 66. A6 — online versus connectivity loss

Compare system behavior:

```text
online predictive
vs
network/backend unavailable → SAFE_LOCAL
```

This is resilience evidence, not model-performance evidence.

---

# 67. A7 — energy-aware policy

Conditional only.

Not opened before core A/B passes.

---

# 68. Primary physical outcome 1 — thermal exposure

Freeze:

\[
E_T=\int \max(0,T(t)-T_{limit})\,dt
\]

Discrete:

\[
E_T\approx\sum_i \max(0,T_i-T_{limit})\Delta t_i
\]

Units:

```text
°C·s
or
°C·min
```

---

# 69. Representative temperature for exposure

Must be frozen.

Options:

- Tmax;
- Tmean.

Do not report whichever gives a nicer result after the campaign.

---

# 70. Primary physical outcome 2 — recovery time

Concept:

\[
T_{rec}=t_{recovered}-t_{reference}
\]

Need freeze:

- reference time;
- target band;
- persistence requirement for “recovered”.

Example:

```text
T representative re-enters target band
and stays for >= τ_stable
```

---

# 71. Supporting physical outcomes

- peak temperature;
- time above critical;
- time above target;
- maximum gradient;
- post-disturbance slope;
- cooling command count;
- ON duration;
- branch energy;
- electrical/thermal verification delay.

---

# 72. Cooling-branch energy

From power samples:

\[
E_{Wh}\approx\frac{1}{3600}\sum_i P_i\Delta t_i
\]

Report:

```text
cooling-branch energy
```

not whole-system energy.

---

# 73. Relative improvement

For outcome where lower is better:

\[
Reduction=1-\frac{Y_B}{Y_A}
\]

Only use if denominator is meaningful/non-negligible.

Always report raw values and paired difference too.

---

# 74. Paired difference

For pair \(i\):

\[
d_i=Y_{B,i}-Y_{A,i}
\]

If lower is better:

- negative \(d_i\) favors predictive.

Alternative reporting may define:

\[
d_i=Y_A-Y_B
\]

so positive favors predictive.

Pick one convention and freeze.

Recommended:

> define improvement as \(I_i=Y_A-Y_B\), positive = B better.

---

# 75. Pair-level analysis

Statistical unit:

```text
one A/B pair
```

Not individual telemetry row.

Compute:

- improvement per pair;
- mean/median improvement;
- 95% CI;
- distribution plot.

---

# 76. Paired t-test condition

If paired differences are reasonably symmetric/normal enough and no severe outlier issue:

- paired t-test may be used.

NIST paired-observation analysis computes the test from pairwise differences.

---

# 77. Nonparametric/robust option

If assumptions are poor:

- permutation/sign-based method;
- Wilcoxon signed-rank where appropriate;
- bootstrap CI for effect.

Do not choose a test solely because it returns significance.

---

# 78. Bootstrap rule

Bootstrap must resample:

```text
pairs/runs
```

not rows.

For \(N\) pairs:

1. sample \(N\) pairs with replacement;
2. compute statistic;
3. repeat many times;
4. use bootstrap distribution for uncertainty.

NIST describes bootstrap as resampling with replacement to estimate a statistic's uncertainty.

---

# 79. Bootstrap iterations

Planning recommendation:

```text
>= 2000
prefer 5000–10000
```

for final computational analysis because project datasets are small and compute is cheap.

The NIST handbook notes hundreds-to-thousands are typical/useful; modern compute allows more.

Seed must be recorded.

---

# 80. 95% CI

Primary effect should include a 95% confidence interval.

Do not report only:

```text
mean improved 18%
```

without uncertainty.

---

# 81. Descriptive statistics

For roughly symmetric distributions:

- mean;
- SD.

For skewed/small/outlier-prone:

- median;
- IQR;
- individual points.

With small N, plotting every pair is highly informative.

---

# 82. Practical significance

Before final A/B, define a minimum engineering-relevant improvement where possible.

Example domains:

- minutes of recovery;
- °C·min exposure;
- avoided critical excursion.

Even if not formal equivalence testing, this avoids treating a trivial numerical difference as project success.

---

# 83. Multiple metrics

Primary metrics frozen in advance.

Supporting metrics interpreted as supporting/exploratory.

Do not search 20 metrics and headline the one with p < 0.05.

---

# 84. Multiple horizons

One primary horizon frozen.

Other horizons:

```text
secondary / sensitivity analysis
```

Avoid horizon shopping.

---

# 85. Missing data

Do not silently interpolate primary event gaps.

Rules:

- short missing interval may be handled only by predeclared method;
- critical event gap may invalidate run;
- imputation cannot create physical evidence.

---

# 86. Outliers

Do not automatically delete outliers.

Investigate:

- measurement fault?
- valid extreme physical run?

If valid:

- keep;
- use robust statistics if necessary.

---

# 87. Predictive threshold selection

Select warning threshold on development data according to a predeclared tradeoff.

Candidate objective:

- adequate event recall;
- bounded false-warning rate;
- positive actionable lead time.

Do not optimize test threshold on final test.

---

# 88. Persistence gate selection

If model emits noisy scores:

```text
risk > threshold for k consecutive seconds/samples
```

Choose `k` on development/pilot.

Freeze for final.

---

# 89. False-warning metric

Possible event-level metric:

```text
false warning episodes / hour
```

or:

```text
false warning episodes / normal run
```

This is more interpretable than thousands of correlated negative samples.

---

# 90. Missed-event metric

\[
MissRate=
\frac{\# critical events without valid advance warning}
{\# critical events}
\]

Report denominator.

---

# 91. Warning duration

Supporting:

- lead time;
- warning persistence;
- repeated alert count.

A model that flickers may be operationally worse despite similar AP.

---

# 92. Locked offline predictive evaluation

Model freeze before opening locked test:

- feature version;
- hyperparameters;
- model artifact hash;
- warning threshold;
- persistence;
- calibration method;
- primary horizon.

Then evaluate once.

---

# 93. Retraining after final test

If final test reveals a bug and retraining is necessary:

- final test is no longer untouched;
- create new independent test data if claiming fresh final performance;
- otherwise disclose exploratory post-test revision.

---

# 94. Shadow-mode verification

## `AI-SHADOW-01`

Run live inference while Controller A remains physical authority.

Assert:

- predictions generated at expected cadence;
- correct model version;
- feature windows causal;
- no predictive commands published.

---

## `AI-SHADOW-02`

Replay known run through online pipeline.

Compare online prediction with offline reference.

Pass within deterministic/numerical tolerance.

---

# 95. Closed-loop A/B protocol

For each pair:

1. verify hardware/config;
2. reach initial criterion;
3. randomize controller order;
4. execute fixed disturbance;
5. record until recovery/end;
6. reset to criterion;
7. execute paired controller;
8. validate both runs;
9. compute pair outcomes only after both valid.

---

# 96. Pair failure

If one run in a pair is invalid:

Options predeclared:

- rerun the invalid arm and preserve same pair block;
- or invalidate pair.

Do not pair a failed run with an unrelated later run without rule.

---

# 97. Controller freeze

Before final A/B:

- threshold;
- hysteresis;
- model;
- feature version;
- risk threshold;
- persistence;
- command duty;
- safety limits;

are frozen.

---

# 98. Same actuation magnitude principle

Core A/B should use same characterized cooling magnitude.

This isolates:

```text
earlier timing
```

as the primary treatment.

---

# 99. A/B primary hypotheses

## H_AB1

Predictive controller reduces thermal exposure.

## H_AB2

Predictive controller reduces recovery time.

Either may be primary/secondary depending final freeze.

Do not require both to win.

---

# 100. Critical excursions

Supporting binary outcome:

```text
did representative temperature exceed Tcritical?
```

With small pair count, report:

- counts;
- paired contingency context;
- raw trajectories.

Avoid overclaiming rare-event rates.

---

# 101. Energy trade-off

For each pair:

\[
\Delta E=E_B-E_A
\]

Interpret with physical outcome.

Examples:

```text
less exposure + slightly more energy
```

may still be acceptable.

```text
same outcome + much more energy
```

weakens value.

No single scalar “efficiency score” required.

---

# 102. PZEM PWM caveat in A/B

If core A/B uses steady full/allowed ON:

energy semantics are simpler.

If PWM used:

- PWM characterization must already pass;
- same measurement method for A/B.

---

# 103. Diagnosis verification

## `DIAG-01` — healthy

Input:

```text
ON command
current/power normal
thermal response normal
```

Expected:

```text
HEALTHY_RESPONSE
```

---

## `DIAG-02` — electrical response missing

Safe fault mode prevents actuation.

Expected:

```text
ELECTRICAL_RESPONSE_MISSING
```

No claim of exact component failure.

---

## `DIAG-03` — unexpected current while OFF

Only perform if safely emulatable/testable without unsafe energization.

Software simulation may verify backend logic, but physical claim needs physical evidence.

---

## `DIAG-04` — degraded thermal effectiveness

Conditional.

Only if a safe physical degradation protocol exists.

---

# 104. Fault injection hierarchy

Prefer:

1. software/state injection;
2. network isolation;
3. safe low-voltage disconnect;
4. controlled non-destructive physical disturbance.

Avoid:

- short circuits;
- overheating;
- mains manipulation;
- destructive fan blocking;
- fuse bypass.

---

# 105. Resilience campaign

## `RES-01` — broker unavailable

During stable operation:

- stop/isolate broker.

Expected:

- device detects loss;
- SAFE_LOCAL;
- thermal control continues locally.

---

## `RES-02` — backend unavailable

Broker may remain.

Expected:

- no unsafe stale remote command;
- device fallback according to policy.

---

## `RES-03` — AI unavailable

Disable inference.

Expected:

```text
Controller B unavailable
→ Controller A/local fallback
```

---

## `RES-04` — reconnect

Restore dependencies.

Expected:

- reported state resync;
- stale commands not replayed;
- normal mode resumes only after fresh state.

---

# 106. Offline buffer verification

If implemented:

- disconnect for known interval;
- generate N samples;
- reconnect;
- verify replay count/order/identity;
- verify twin does not regress.

---

# 107. MQTT duplicate test

Inject duplicate telemetry with same:

```text
device_id + boot_id + seq
```

Expected:

- one normalized physical sample;
- duplicate metric visible.

---

# 108. Duplicate command test

Send same `command_id` twice.

Expected:

- no second independent actuation;
- canonical ACK/result.

---

# 109. Stale command test

Create command with expired TTL.

Expected:

```text
REJECTED / EXPIRED
```

No physical actuation.

---

# 110. Wrong-device command test

Payload/topic mismatch.

Expected:

- rejection;
- no actuation;
- security/protocol evidence.

---

# 111. Out-of-range duty test

Send duty outside validated range.

Expected:

```text
COMMAND_OUT_OF_RANGE
```

No actuation beyond safe policy.

---

# 112. Malformed-schema test

Invalid JSON/type/schema.

Expected:

- reject;
- no state mutation;
- visible error.

---

# 113. Unauthorized broker publish

Using unauthorized test principal:

attempt to publish device command.

Expected:

- broker ACL denies.

---

# 114. TLS/auth test

Verify secure profile rejects:

- wrong credential;
- invalid/untrusted endpoint/certificate according to configured mode.

Exact certificate laboratory setup documented.

---

# 115. Security evidence boundary

This project demonstrates a baseline.

It does not claim:

- penetration-test certification;
- production-grade zero trust;
- formal security verification.

---

# 116. Reliability metrics

Report:

- duplicate count;
- invalid message count;
- reconnect time;
- SAFE_LOCAL entry time;
- resync time;
- command ACK latency;
- verification latency.

---

# 117. Performance campaign

Performance is not web-scale throughput.

Relevant experiments:

## PERF-01

Stable 1 Hz ingestion for extended run.

## PERF-02

Command latency distribution.

## PERF-03

Reconnect/resynchronization.

## PERF-04

Dataset query/export time sufficient for analysis.

---

# 118. Long soak test

Candidate:

```text
2–4 h
```

continuous telemetry/control-safe operation.

Purpose:

- memory leak;
- reconnect;
- DB growth;
- sensor stability.

This does not need to be 24 h unless project value justifies it.

---

# 119. Data completeness

Per run:

\[
Completeness=
\frac{received\ expected\ samples}
{expected\ samples}
\]

But expected count must account for actual acquisition cadence.

For primary event window, require stronger completeness than whole-run average.

---

# 120. Timing jitter

Report distribution of:

```text
Δt between samples
```

if it affects derivative/window features.

Do not assume exact 1.000 s cadence.

---

# 121. Sensor disagreement monitoring

During baseline:

\[
G_T=T_{max}-T_{min}
\]

Track expected range.

Large unexpected change may indicate:

- chamber airflow change;
- sensor displacement;
- disturbance.

---

# 122. Data QA before ML

Automated checks:

- unique `run_id`;
- unique `(device,boot,seq)`;
- monotonic sequence within boot;
- known hardware config;
- known calibration;
- no impossible timestamps;
- sensor quality;
- no mixed units;
- correct PZEM range.

---

# 123. Leakage audit checklist

- [ ] split by run before windows;
- [ ] scaler/imputer fit on train only;
- [ ] feature normalization fit on train only;
- [ ] calibration fit on development only;
- [ ] final threshold selected without test;
- [ ] no future values in rolling features;
- [ ] no future controller outcome in current feature;
- [ ] duplicate trajectories not across splits;
- [ ] paired runs not inadvertently split in a way that leaks near-identical disturbances if this matters.

---

# 124. Label audit

Randomly inspect labeled windows around:

- critical event;
- non-event;
- door opening;
- cooling transition.

Plot raw trajectory with label boundaries.

---

# 125. Feature audit

For each feature:

```text
name
formula
input channels
window
causal?
missing behavior
version
```

---

# 126. Dataset card

Final ML dataset includes:

- purpose;
- hardware config;
- scenarios;
- date range;
- run IDs;
- split IDs;
- label rule;
- feature version;
- exclusions;
- limitations.

---

# 127. Model card

Final model record includes:

- model version/hash;
- training data;
- feature version;
- horizon;
- hyperparameters;
- validation metrics;
- locked test metrics;
- calibration status;
- known limitations;
- allowed use.

---

# 128. Probability-calibration report

If applicable:

- reliability diagram;
- Brier;
- bin counts;
- before/after calibration;
- calibration method;
- grouped split used to fit.

If positive data are too sparse:

> do not overinterpret bins.

---

# 129. Final predictive table

Example:

| Model | AP | Recall | Precision | False warnings/run | Median EWT | Missed events |
|---|---:|---:|---:|---:|---:|---:|
| Threshold | ... | ... | ... | ... | 0 | ... |
| Hysteresis | ... | ... | ... | ... | ... | ... |
| XGBoost | ... | ... | ... | ... | ... | ... |

Include confidence/variability where meaningful.

---

# 130. Final A/B table

| Pair | Controller A exposure | B exposure | Improvement | A recovery | B recovery | ΔEnergy |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | ... | ... | ... | ... | ... | ... |

Then summary:

- mean/median paired improvement;
- 95% CI;
- effect size;
- test result;
- individual-pair plot.

---

# 131. Plot requirements

## Physical trajectory plot

Show aligned:

- T1/T2/T3;
- threshold;
- door;
- cooling state;
- prediction warning;
- PZEM power.

---

## A/B pair plot

Overlay or side-by-side with common time reference.

---

## Paired effect plot

Each pair as line/point.

Better than bar chart only.

---

## PR curve

For predictive discrimination.

---

## Calibration curve

Only if probability semantics claimed.

---

# 132. Avoid misleading plots

- truncated y-axis without reason;
- smoothing that hides event timing;
- only selected “best” run;
- different scales for A/B comparison;
- screenshots without raw identifiers.

---

# 133. Statistical analysis freeze

Before final A/B data analysis, freeze:

```text
primary outcome
paired-difference sign convention
confidence level
bootstrap seed/iterations
test family
handling of invalid pair
secondary outcomes
```

---

# 134. Analysis script

Final results should be regenerated by one command/script where practical.

Example:

```text
python -m analysis.final_report --manifest final-campaign.yaml
```

Not mandatory syntax.

Reproducibility is mandatory.

---

# 135. Reproducibility package

Include:

- source commit;
- environment/dependency lock;
- run manifests;
- dataset export manifest;
- model artifact;
- policy config;
- analysis script;
- generated tables/figures.

---

# 136. Clean-room rerun

Before defense:

On clean environment:

1. deploy backend/broker/DB;
2. flash/verify firmware;
3. load model/policy;
4. ingest sample/replay;
5. regenerate at least one report.

Document unexpected manual step.

---

# 137. Release gates

## Gate A — Hardware / Physical

Required:

- H0–H7 passed;
- no unsafe hot-side/driver behavior in approved envelope;
- sensor identity stable;
- PZEM profile correct;
- disturbance/recovery repeatable enough.

**Fail → no AI dataset campaign.**

---

## Gate B — Data

Required:

- run manifests;
- synchronized telemetry/events;
- quality flags;
- raw immutable;
- grouped split;
- label protocol frozen.

---

## Gate C — Prediction

Required:

- deterministic baseline;
- XGBoost grouped evaluation;
- leakage audit;
- warning semantics;
- acceptable predictive evidence on development/locked test.

“Acceptable” does not require arbitrary 95% accuracy.

---

## Gate D — Control

Required:

- Controller A stable;
- command TTL/idempotency;
- ACK semantics;
- physical electrical verify;
- thermal verify;
- SAFE_LOCAL;
- shadow mode.

Only then Controller B physical actuation.

---

## Gate E — Final A/B readiness

Required freeze:

- model;
- feature;
- policy;
- controller actions;
- disturbance protocol;
- initial/reset criterion;
- pair tolerance;
- outcomes;
- analysis plan;
- final target pair count.

---

## Gate F — Optional scope

Only after core evidence:

- PWM energy optimization;
- advanced model;
- S3 degradation;
- extra hardening.

---

# 138. Core pass/fail summary

Project core is acceptable if:

1. hardware is safe/repeatable;
2. data/evidence provenance is complete;
3. model evaluation is leakage-safe;
4. command→physical verification works;
5. predictive mode passes safety gate;
6. A/B campaign is valid;
7. resilience works;
8. results are reported with uncertainty.

It is **not** required that every hypothesis is positive.

---

# 139. Success interpretation for H1/H2

### Positive

XGBoost provides useful held-out early warning beyond baseline.

### Neutral

Similar to baseline.

### Negative

Worse/more false warnings.

All three are reportable.

---

# 140. Success interpretation for closed loop

### Strong support

Paired physical improvement is consistent and CI/effect are meaningful.

### Mixed

One outcome improves, another worsens or CI wide.

### No support

No meaningful paired improvement.

Do not convert mixed/no-support into “AI optimized the cold chain.”

---

# 141. Demo philosophy

Final demo should demonstrate **mechanism**, not wait for a long statistical experiment live.

Statistical claims come from pre-recorded evidence.

Live demo proves:

- sensing;
- communication;
- prediction path;
- command;
- verification;
- fallback.

---

# 142. Final demo — Scene 1: physical identity

Show:

- exact 6 L chamber;
- T1/T2/T3 physical positions;
- MC-38;
- PZEM/shunt;
- IBT-2/TEC/V1;
- PSU/protection.

Explain:

> which sensor proves which fact.

---

# 143. Demo — Scene 2: live state

Dashboard:

- three temperatures;
- gradient;
- door;
- V/I/P;
- device mode;
- desired/applied/verified cooling.

Open/close door briefly.

Observe event.

---

# 144. Demo — Scene 3: predictive warning

Use a controlled/replay or live short scenario.

Show:

```text
risk rises
→ warning
→ policy reason
```

Do not claim final effect from one live run.

---

# 145. Demo — Scene 4: physical action verification

Trigger legal action.

Show timeline:

```text
command
→ ACK
→ current/power
→ temperature response
→ VERIFIED
```

This is the centerpiece.

---

# 146. Demo — Scene 5: resilience

Disconnect broker/backend path.

Show:

```text
SAFE_LOCAL
```

and continued deterministic protection.

Reconnect.

Show:

- state resync;
- no stale command replay.

---

# 147. Demo — Scene 6: evidence result

Show precomputed final A/B summary:

- number of pairs;
- individual paired effects;
- CI;
- representative trajectories.

Do not rerun the statistical campaign live.

---

# 148. Demo timing

Suggested:

```text
1–2 min physical architecture
2 min live sensing
2–3 min predictive/control trace
2 min resilience
2 min final evidence
```

Adjust to course slot.

---

# 149. Defense anchors

Every member should answer:

1. Why three DS18B20?
2. Why PZEM if command ACK exists?
3. Why one TEC?
4. Why XGBoost before deep learning?
5. Why random-row split is invalid?
6. Why EWT and A/B must be evaluated separately?
7. What does QoS 1 not guarantee?
8. What happens if backend disappears?
9. How do you know cooling actually happened?
10. Which claims are intentionally not made?

---

# 150. Evidence traceability table

Final report includes:

| Requirement / claim | Test IDs | Evidence path | Result |
|---|---|---|---|
| stable sensor identity | SEN-H1-01/02 | ... | PASS |
| PZEM valid range | ELEC-H3-03 | ... | PASS |
| default off | ACT-H4-01 | ... | PASS |
| closed-loop verification | H8 + ... | ... | PASS |
| early warning | AI-... | ... | quantitative |
| A/B physical outcome | EXP-AB-... | ... | quantitative |
| SAFE_LOCAL | RES-01 | ... | PASS |
| stale command | SEC-... | ... | PASS |

---

# 151. Final report result hierarchy

Order:

1. hardware characterization;
2. measurement quality;
3. dataset/run design;
4. baseline;
5. predictive evaluation;
6. calibration;
7. ablation;
8. closed-loop A/B;
9. resilience/security;
10. limitations.

This tells a causal story.

---

# 152. Limitations section requirements

At minimum discuss:

- 6 L testbed scale;
- one TEC;
- one physical hardware unit;
- sensor/probe accuracy;
- no biological quality ground truth;
- limited number of independent runs;
- environment/ambient variation;
- PZEM/PWM limitations if relevant;
- model generalization limited to tested config/scenarios.

---

# 153. No commercial extrapolation

Final discussion must not extrapolate:

```text
18% exposure reduction in 6 L chamber
```

to:

```text
18% spoilage reduction in warehouses
```

without evidence.

---

# 154. Research comparison discipline

When comparing to literature:

- compare methodology and problem framing;
- do not compare raw percentages across incompatible plants;
- distinguish simulation versus physical testbed;
- distinguish anomaly detection versus closed-loop intervention.

A 2026 reefer-container study evaluates early anomaly detection using controlled fault simulation and operational metrics such as time-to-detection and false positives; ColdGuard uses this as methodological context, not a claim of equivalent scale.

---

# 155. Verification ID namespace

Recommended:

```text
HW-*       mechanical/power
SEN-*      sensing
ELEC-*     PZEM/electrical
ACT-*      actuator
THERM-*    thermal
IOT-*      MQTT/backend
DATA-*     data QA
AI-*       prediction
CTRL-*     policy/control
DIAG-*     cooling health
RES-*      resilience
SEC-*      security
PERF-*     performance
EXP-*      final experiment
DEMO-*     release/demo
```

---

# 156. Minimum automated regression suite

Before final campaign:

## Firmware

- sensor identity;
- command validation;
- duplicate command;
- expiry;
- local fallback logic.

## Backend

- schema;
- dedup;
- twin ordering;
- command lifecycle;
- stale replay.

## ML

- feature causality;
- split isolation;
- deterministic inference;
- model/version mismatch.

## Integration

- command→ACK;
- reconnect;
- replay.

---

# 157. Hardware-in-loop regression

At least a small pre-campaign HIL smoke:

- all sensors valid;
- PZEM read;
- command disabled/off;
- short safe ON;
- verify current;
- return OFF;
- no unexpected fault.

---

# 158. Final-campaign change freeze

During locked A/B campaign, avoid changing:

- firmware;
- hardware;
- model;
- policy;
- sensor placement;
- threshold;
- disturbance duration.

If a critical bug forces change:

- stop;
- version change;
- decide whether earlier data remain comparable;
- document.

---

# 159. Campaign log

Record every run attempt, including invalid/aborted.

Do not keep only successful runs.

This helps detect hidden selection bias.

---

# 160. Operator protocol

To reduce human variation:

- checklist;
- timer for door;
- consistent open angle;
- no extra handling;
- record anomaly immediately.

---

# 161. Environmental context

Record:

- BME temperature/RH;
- approximate room conditions if available;
- session/day.

If ambient drift is large, block/adjust interpretation rather than ignore.

---

# 162. Pair randomization record

Store randomization seed/order list before final campaign if practical.

Example:

```text
PAIR-01 B→A
PAIR-02 A→B
...
```

---

# 163. Sequential peeking rule

Do not stop the final campaign early merely because current result becomes significant.

Follow frozen target pair count unless:

- safety;
- equipment failure;
- documented feasibility reason.

---

# 164. Repeated-model-selection warning

Every repeated test-set inspection increases overfitting risk.

One locked final evaluation is preferred.

---

# 165. Confidence interval reporting example

Instead of:

```text
Predictive reduces exposure 22%.
```

report:

```text
median paired reduction = ...
95% bootstrap CI = [...]
N = ... pairs
```

plus raw exposure values.

---

# 166. P-value reporting

If used:

- name test;
- assumptions;
- exact N;
- effect and CI alongside.

Never write:

```text
p < 0.05 therefore important
```

---

# 167. Statistical software provenance

Record:

- Python version;
- numpy/pandas/scipy/scikit-learn versions;
- random seeds;
- analysis commit.

---

# 168. PR/AP reporting nuance

Scikit-learn's Average Precision is a weighted summary of precision at recall changes and is not identical to trapezoidal PR-AUC.

Name the metric correctly:

```text
Average Precision (AP)
```

if that is what is computed.

---

# 169. ROC-AUC nuance

ROC-AUC may appear strong under class imbalance.

Do not make it the only evidence.

---

# 170. Confusion matrix unit

Clearly state whether matrix is:

- per telemetry sample;
- per warning episode;
- per critical event.

Prefer event-level interpretation for operational claims.

---

# 171. Prediction timing alignment

A prediction at time \(t\) may only use records whose physical capture time is <= \(t\).

Backend receive time must not accidentally include a future-captured record due to sorting mistakes.

---

# 172. Door-event timing audit

Compare:

- MC-38 transition;
- telemetry timestamps;
- experiment operator timer if used.

Door event is a key ground-truth treatment.

---

# 173. Command timing audit

Store:

```text
decision_at
created_at
published_at
ack_at
electrical_verified_at
thermal_verified_at
```

These permit actionable-window analysis.

---

# 174. Physical response delay

Estimate from repeated step responses.

Do not use the single fastest run.

Report distribution.

---

# 175. Detection persistence

Warning first time definition must include frozen persistence.

Example:

```text
first time risk > r for 5 consecutive valid seconds
```

if `5 s` is chosen during development.

---

# 176. Reactive warning definition

Similarly freeze:

```text
first time representative T exceeds threshold
with required persistence if any
```

Otherwise EWT is ambiguous.

---

# 177. Controller intervention timing

Record first actual applied cooling state, not merely backend decision time.

For physical comparison:

```text
device applied time
```

is more relevant.

---

# 178. A/B alignment

Plots may align at:

- door-open start;
- door-close;
- controller intervention.

State which alignment is used.

Do not shift curves to make one look better.

---

# 179. Recovery target band

Freeze after characterization.

Use physically attainable stable band.

Persistence requirement avoids one-sample crossings.

---

# 180. Exposure boundary

Freeze `T_limit` separately from model probability threshold.

Do not conflate:

- thermal criterion;
- ML decision threshold.

---

# 181. Model operating threshold

Selected to balance:

- recall;
- false warnings;
- lead time.

Document tradeoff curve if possible.

---

# 182. Event prevalence

Report how many:

- runs;
- critical events;
- positive windows;
- negative windows.

Rows alone hide prevalence.

---

# 183. Dataset overlap audit

Hash/run IDs ensure the same physical run is not duplicated under different filenames across splits.

---

# 184. Derived-feature reproducibility

Given same raw data + feature version:

- output deterministic within numeric tolerance.

Test it.

---

# 185. Model reproducibility

With fixed artifact:

- repeated inference on same feature vector gives same prediction.

Training may be nondeterministic unless configured; artifact inference should be stable.

---

# 186. Controller reproducibility

Given same frozen state/prediction/policy:

- policy output deterministic unless randomness explicitly part of design.

Core should be deterministic.

---

# 187. Fault-campaign repeatability

Each resilience/security fault repeated enough to prove mechanism, typically:

```text
>= 3 successful reproductions
```

for important deterministic mechanisms.

This is not statistical population inference; it is regression/mechanism evidence.

---

# 188. Security negative-test pass

Pass means:

- prohibited action rejected;
- no physical side effect;
- event/audit visible.

A HTTP 403 alone is incomplete if another path still actuates.

---

# 189. Data integrity test

Export a run.

Check:

- row count;
- sequence gaps;
- duplicates;
- timestamps;
- versions.

Compute checksum for final artifact.

---

# 190. Final artifact checksums

Record SHA-256 for:

- model;
- final dataset export;
- major result CSV;
- final analysis script/archive if practical.

---

# 191. Database backup proof

Before final campaign:

- backup;
- restore test on separate environment at least once.

Do not discover restore failure after the campaign.

---

# 192. Demo offline contingency

Final demo package should include a recent evidence replay in case venue Wi-Fi fails.

This is not cheating.

It demonstrates resilience and avoids dependence on external Internet.

Local broker/backend may run on LAN/laptop.

---

# 193. Internet dependency

Core ColdGuard demo should not require public cloud.

This improves reproducibility.

---

# 194. Power-loss contingency

If unexpected power loss occurs:

- mark active run aborted;
- do not silently resume same run;
- reboot creates new `boot_id`;
- inspect physical state before next run.

---

# 195. Sensor replacement rule

Replacing DS18B20:

- new ROM;
- hardware config/calibration update;
- comparability review.

Do not alias new sensor to old identity without record.

---

# 196. TEC/V1 reassembly rule

Reassembly can change thermal contact.

Requires:

- new characterization check;
- likely new hardware/config revision or block.

---

# 197. PZEM/shunt change rule

Any shunt/range change:

- config revision;
- old/new data not directly pooled without explicit handling.

---

# 198. Evidence retention

Keep:

- raw;
- manifests;
- invalid-run logs;
- analysis artifacts;

through project grading/defense.

Do not retain only cleaned data.

---

# 199. Final evidence index

Create:

```text
evidence/INDEX.md
```

mapping:

```text
claim → test → artifact
```

This helps leader and reviewers.

---

# 200. Final defense claim boundaries

Allowed if supported:

> multi-point observation captured spatial thermal differences.

Allowed if supported:

> XGBoost produced earlier warning than reactive threshold on held-out runs.

Allowed if supported:

> predictive intervention reduced thermal exposure/recovery in the tested 6 L system.

Allowed if supported:

> PZEM enabled independent electrical-response verification.

Allowed if supported:

> SAFE_LOCAL preserved minimum local thermal protection during specified network loss.

---

# 201. Prohibited defense shortcuts

Do not say:

```text
AI prevents spoilage
```

unless biological outcome measured.

Do not say:

```text
Digital Twin predicts real warehouses
```

Do not say:

```text
IBT-2 supports 43 A continuously
```

Do not say:

```text
95% accuracy proves the model is good
```

Do not say:

```text
MQTT QoS1 prevents duplicate messages
```

Do not say:

```text
ACK proves TEC worked
```

---

# 202. Final demo acceptance checklist

## Hardware

- [ ] exact BOM visually identifiable;
- [ ] fuse installed;
- [ ] no unsafe exposed high-current connection;
- [ ] fan operating.

## Sensing

- [ ] T1/T2/T3 valid;
- [ ] BME valid or explicit degraded;
- [ ] door works;
- [ ] PZEM works.

## IoT

- [ ] device connected;
- [ ] telemetry;
- [ ] twin;
- [ ] event timeline.

## AI/control

- [ ] model version shown;
- [ ] policy shown;
- [ ] command lifecycle;
- [ ] electrical verify;
- [ ] thermal verify.

## Resilience

- [ ] SAFE_LOCAL demo prepared.

## Evidence

- [ ] A/B final results;
- [ ] CI;
- [ ] run count;
- [ ] limitations.

---

# 203. Release acceptance checklist

- [ ] Docs 00–03 agree.
- [ ] frozen BOM unchanged or explicit revision.
- [ ] all commissioning gates complete.
- [ ] raw evidence backed up.
- [ ] final test split preserved.
- [ ] final A/B model/policy frozen.
- [ ] invalid runs logged.
- [ ] analysis reproducible.
- [ ] security negative tests pass.
- [ ] resilience tests pass.
- [ ] demo can run locally.
- [ ] every headline claim maps to evidence.

---

# 204. Reference methodology

**[R1] NIST/SEMATECH Engineering Statistics Handbook.**  
Engineering/scientific experimental design, measurement characterization, comparisons, uncertainty and statistical interpretation.  
https://www.nist.gov/programs-projects/nistsematech-engineering-statistics-handbook

**[R2] NIST/SEMATECH — Analysis of Paired Observations.**  
Paired observations are analyzed through pairwise differences \(d_i=Y_i-Z_i\).  
https://www.itl.nist.gov/div898/handbook/prc/section3/prc311.htm

**[R3] NIST/SEMATECH — Confidence Intervals for Differences Between Means.**  
Includes paired confidence-interval formulation.  
https://www.itl.nist.gov/div898/handbook/prc/section3/prc312.htm

**[R4] NIST/SEMATECH — Bootstrap Plot / Bootstrap Uncertainty.**  
Bootstrap resampling with replacement for estimating sampling-distribution uncertainty.  
https://www.itl.nist.gov/div898/handbook/eda/section3/bootplot.htm

**[R5] scikit-learn — GroupKFold / GroupShuffleSplit.**  
Non-overlapping groups across train/test splits. ColdGuard maps group to independent `run_id`.  
https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html  
https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupShuffleSplit.html

**[R6] scikit-learn — Precision-Recall.**  
Precision-recall evaluation is particularly useful for imbalanced classification.  
https://scikit-learn.org/stable/auto_examples/model_selection/plot_precision_recall.html

**[R7] scikit-learn — Average Precision.**  
AP summarizes the precision-recall curve using recall increments as weights.  
https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html

**[R8] scikit-learn — Calibration Curve / Brier Score.**  
Reliability diagrams and proper probabilistic scoring for probability semantics.  
https://scikit-learn.org/stable/modules/generated/sklearn.calibration.calibration_curve.html  
https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html

**[R9] OASIS — MQTT Version 5.0.**  
Transport QoS/session/message-expiry semantics used in duplicate/reconnect verification.  
https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html

**[R10] Vukšić et al. (2026) — Early Anomaly Detection in Maritime Refrigerated Containers Using a Hybrid Digital Twin and Deep Learning Framework. Applied Sciences 16(4), 1887.**  
Relevant methodological context: early warning, controlled fault evaluation, practical baselines and time-to-detection/false-alert thinking.  
https://doi.org/10.3390/app16041887

---

# 205. North star

> **The strongest ColdGuard result is not the largest accuracy number. It is a chain of evidence showing that the exact purchased hardware produced a reproducible physical trajectory, the model saw only lawful past information, the warning occurred before a deterministic baseline, the warning was early enough to matter physically, the safety-bounded controller changed the real plant, and the paired experiment quantified that physical effect with honest uncertainty.**

> **If that chain breaks, the claim is weakened or rejected — even if the dashboard looks impressive.**
