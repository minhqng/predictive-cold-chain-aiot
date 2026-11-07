# COLDGUARD — HỆ THỐNG BẢO VỆ CHUỖI LẠNH CHỦ ĐỘNG
## Team Execution Plan · 24-Week Delivery · Ownership · Dependencies · Gates · Evidence

> **Document:** `docs/04-team-execution-plan.md`  
> **Course:** Internet of Things (IoT) — Course Project / Bài tập lớn  
> **Project:** **ColdGuard — Hệ thống bảo vệ chuỗi lạnh chủ động**  
> **Type:** Team Execution Plan + Delivery Governance + Integration/Review Contract  
> **Status:** **PROPOSED FREEZE v1.0 — REVIEW CANDIDATE**  
> **Baseline date:** **2026-09-29**  
> **Team size:** **4 members**  
> **Planning horizon:** **24 weeks**  
> **Parents:**  
> `00-project-scope-architecture.md` — project thesis, architecture, exact purchased BOM baseline and scope.  
> `01-physical-measurement-correctness-contract.md` — physical authority, measurement semantics, legal states and safety invariants.  
> `02-aiot-closed-loop-engineering.md` — firmware, MQTT, backend/twin, inference, command, SAFE_LOCAL and recovery semantics.  
> `03-verification-experiments-demo.md` — commissioning tests, experiment design, statistical analysis, evidence and demo/defense proof.  
> **Children:**  
> `05A-member-a-embedded-thermal.md`  
> `05B-member-b-ai-experimental-data.md`  
> `05C-member-c-iot-backend-digital-twin.md`  
> `05D-member-d-control-security-resilience.md`  
> **Normative role:** source of truth for ownership, 24-week chronology, dependency graph, integration order, review rules, work-item taxonomy, release gates, handoff deadlines, workload accounting, scope-cut order, leader audit and final delivery preparation.  
> **Not source of truth for:** physical/correctness semantics (`01`), runtime protocol semantics (`02`), experiment/statistical meaning (`03`). If schedule conflicts with correctness or evidence, **Docs 00–03 win**.  
> **Execution principle:** work is organized around **proof-bearing vertical increments**. A risky mechanism is not considered delivered until the member can demonstrate implementation, quantitative evidence, integration and reproducibility in the same phase.

> **Team north star.**  
> **By Week 24, all four members must be able to start or reconstruct the system from a clean environment, identify the exact frozen hardware configuration, explain the complete sensing→prediction→policy→actuation→verification loop, reproduce at least one failure/resilience proof, trace one physical A/B experiment from raw telemetry to statistical result, and defend why the final claims are limited to what the evidence actually supports.**

---

# 0. Executive plan

## 0.1 Team structure

### Member A — Embedded & Thermal Systems

Primary ownership:

```text
exact purchased hardware testbed
ESP32-S3R2 primary controller
DS18B20 ×3
BME280
MC-38
PZEM-017
50 A / 75 mV shunt
MAX3485
IBT-2
TEC1-12715 exact purchased SKU
V1 thermal assembly
HS2 6 L chamber
12 V / 33 A power architecture
fuses / wiring / distribution
physical commissioning
sensor identity / placement
plant characterization
repeatable disturbance
physical response evidence
```

Secondary/cross-cutting:

```text
firmware acquisition quality
hardware configuration versioning
physical A/B campaign execution
final physical demo
```

North star:

> **Turn the purchased prototype into a safe, repeatable, measurable physical plant whose data are trustworthy.**

---

### Member B — AI & Experimental Data

Primary ownership:

```text
data quality analysis
dataset manifests
run-level split
label protocol
temporal features
threshold/hysteresis analytical baseline
XGBoost
prediction horizon selection
probability calibration when justified
predictive metrics
ablation
locked holdout
paired A/B statistics
confidence intervals
model card
scientific result package
```

Secondary/cross-cutting:

```text
experiment-design review
effect-size/sample-size planning
data leakage audit
report methodology/results
```

North star:

> **Prove predictive usefulness honestly without leakage, inflated sample size or score-only storytelling.**

---

### Member C — IoT Backend & Digital Twin

Primary ownership:

```text
Mosquitto / MQTT
TLS-ready broker configuration
message identity
ingestion validation
raw immutable telemetry
PostgreSQL / TimescaleDB
run metadata
reported/desired/derived twin
event/audit timeline
command lifecycle persistence
API
realtime
prediction integration
replay / duplicate / out-of-order
backup / restore
observability
Docker Compose / reproducible deployment
```

Secondary/cross-cutting:

```text
schema integration
experiment export
closed-loop traceability
demo operational reliability
```

North star:

> **Make every physical sample, prediction, command and response reconstructable end to end.**

---

### Member D — Control, Security & Resilience

Primary ownership:

```text
safety hierarchy
policy state machine
Controller A reactive baseline
Controller B predictive policy
command validation
TTL/freshness/idempotency rules
cooling-health interpretation
electrical/thermal verification rules
SAFE_LOCAL
degraded modes
network/backend/AI outage behavior
identity / TLS / ACL / backend authorization
security negative tests
resilience campaign
final safety case
```

Secondary/cross-cutting:

```text
physical control review
threat model
A/B intervention policy
defense of safety/resilience claims
```

North star:

> **No prediction may become an unsafe or unaudited physical action.**

---

## 0.2 Why this ownership split is balanced

The split follows **authority and risk boundaries**, not feature count.

A's hard problem:

```text
physical uncertainty + electrical/thermal safety + repeatability
```

B's hard problem:

```text
small independent N + temporal dependence + leakage + honest inference
```

C's hard problem:

```text
identity + ordering + durable evidence + state reconciliation
```

D's hard problem:

```text
turn prediction into bounded action under failure and adversarial/stale inputs
```

The domains have different line counts but comparable engineering/research depth.

---

## 0.3 Workload envelope

Planned focused project effort:

| Member | Core hours | Average/week | Heaviest region |
|---|---:|---:|---|
| **A** | **~276 h** | **11.5 h/week** | W3–W4, W18–W20 |
| **B** | **~278 h** | **11.6 h/week** | W10–W11, W18–W20 |
| **C** | **~279 h** | **11.6 h/week** | W5–W6, W17–W20 |
| **D** | **~279 h** | **11.6 h/week** | W17–W20 |
| **Team** | **~1112 h** | **~46.3 h/week** | W17–W20 |

This includes:

- technical study directly supporting the project;
- implementation;
- physical lab work;
- test/evidence creation;
- integration;
- review;
- report/demo preparation.

It excludes:

- unrelated lecture study;
- general coursework;
- optional features after scope-cut;
- waiting time while chamber passively resets unless the member is actively operating/analyzing.

This is a capacity reservation, not a requirement to consume every hour.

---

## 0.4 Six-phase delivery model

| Phase | Weeks | Main question |
|---|---:|---|
| **P0 — Freeze & Physical Foundation** | **W01–W04** | Is the exact purchased system safe, understood and technically connectable? |
| **P1 — Stable IoT Baseline** | **W05–W08** | Can sensing, storage, reactive control and SAFE_LOCAL operate reproducibly? |
| **P2 — Dataset + Reactive Benchmark** | **W09–W12** | Can repeatable runs support baseline/XGBoost/diagnosis without leakage? |
| **P3 — Predictive Readiness + Resilience** | **W13–W16** | Does prediction provide useful warning, and is the system safe under failure? |
| **P4 — Predictive Closed Loop + A/B** | **W17–W20** | Can prediction safely change the plant and improve a matched physical outcome? |
| **P5 — Evidence Freeze + Defense** | **W21–W24** | Can another reviewer reproduce, audit and defend the entire evidence chain? |

---

## 0.5 Project critical path

```text
Docs 00–03 freeze
      ↓
A: exact hardware commissioning
      ↓
A: repeatable 6 L plant
      ↓
C: stable identity/raw telemetry/twin
      ↓
D: Controller A + SAFE_LOCAL
      ↓
A+C: valid experiment data path
      ↓
B: grouped baseline + XGBoost
      ↓
B+D: actionable warning / policy semantics
      ↓
C+D: shadow closed-loop trace
      ↓
A+D: Controller B physical enablement
      ↓
A+B+C+D: matched A/B campaign
      ↓
B: paired statistics / uncertainty
      ↓
team: evidence / demo / defense
```

---

## 0.6 Highest-risk critical path

The most schedule-sensitive chain is:

```text
PZEM / IBT-2 / V1 / TEC commissioning
→ repeatable S2 door disturbance
→ leakage-safe predictive evidence
→ command + physical verification
→ Controller B enablement
→ final paired A/B runs
```

If this path slips:

1. stop optional PWM/energy work;
2. stop deep-model work;
3. stop UI polish;
4. reassign reviewer capacity;
5. preserve W23–W24 evidence/defense buffer.

---

# 1. Delivery philosophy

## 1.1 Proof-bearing vertical increments

Bad plan:

```text
W1–W10 everyone codes own subsystem
W11 integrate
W18 test
W23 discover hardware/model mismatch
```

Preferred:

```text
small physical path
→ connect digital path
→ force failure
→ verify evidence
→ expand
```

Example:

```text
one real telemetry snapshot
→ MQTT
→ raw DB
→ twin
→ dashboard
```

exists before polishing the complete UI.

Another:

```text
one legal ON command
→ ACK
→ PZEM current
→ thermal response
```

exists before enabling AI control.

---

## 1.2 Risk-first sequencing

Implementation priority:

```text
1. electrical / thermal safety
2. stable sensor identity
3. PZEM electrical observability
4. repeatable plant dynamics
5. raw data provenance
6. Controller A + SAFE_LOCAL
7. leakage-safe model
8. command physical verification
9. Controller B
10. final A/B evidence
11. energy/deep-model/security hardening extras
```

---

## 1.3 Test accompanies mechanism

When introducing:

```text
PZEM
```

also implement:

```text
50 A range proof
OFF envelope
reference/plausibility check
```

When introducing:

```text
QoS 1
```

also test:

```text
duplicate delivery
```

When introducing:

```text
command TTL
```

also send:

```text
expired command
```

When introducing:

```text
XGBoost
```

also run:

```text
grouped split + leakage audit + baseline
```

Never defer all verification to W23.

---

## 1.4 Correctness outranks schedule

If `04` says:

```text
enable predictive actuation in W18
```

but Gate D in `03` is red:

```text
predictive actuation remains disabled
```

The schedule slips.

The safety rule does not.

---

# 2. Work-item / tracker operating model

The tracker mirrors this plan.

GitHub currently supports:

- parent/sub-issue hierarchies;
- issue dependencies;
- milestones/labels;
- Project fields.

Use those relationships instead of manually maintaining a second dependency spreadsheet.

---

## 2.1 Hierarchy

```text
Phase
  → Week parent issue
      → Member issue pack
          → implementation / experiment sub-issues
```

Example:

```text
W08 — Physical + Data Baseline Gate
  ├─ A-W08 Repeatability + Gate A evidence
  ├─ B-W08 Dataset readiness + Gate B
  ├─ C-W08 Platform soak / recovery
  └─ D-W08 SAFE_LOCAL integration
```

---

## 2.2 Recommended fields

```text
Status
Owner
Week
Phase
Priority
EstimateHours
ActualHours
Risk
ParentDoc
Gate
TestID
Reviewer
Evidence
BlockedBy
HardwareConfig
```

---

## 2.3 Status values

Use:

```text
Backlog
Ready
In Progress
In Review
Evidence
Done
Blocked
Cut
```

Avoid:

```text
almost done
basically working
testing later
```

---

## 2.4 Priority

```text
P0-BLOCKER
P0
P1
P2
```

`P0-BLOCKER`:

- active release gate cannot pass;
- optional work stops.

---

## 2.5 WIP limit

Per member:

```text
max 2 implementation issues In Progress
```

Team:

```text
max 1 unresolved critical architecture/correctness question on the main path
```

A member may wait on physical reset while doing analysis/review, but should not accumulate unrelated half-finished features.

---

# 3. Git / review baseline

## 3.1 Branching

Member C uses one feature branch and one pull request per week. All tasks for
that week land together after software verification.

Recommended:

```text
main
feature/<issue-id>-<short-name>
fix/<issue-id>-<short-name>
experiment/<id>-<short-name>
```

Avoid semester-long:

```text
person-a
person-b
person-c
person-d
```

branches.

---

## 3.2 Merge rule

Nontrivial P0 change:

- pull request;
- the assigned member owns implementation and verifies the change;
- required tests/evidence where applicable;
- no unresolved correctness question.

Peer review is optional. Technical verification and applicable safety and
evidence gates are required. Record human approval only when it occurred.

---

## 3.3 Reviewer matrix

| Area | Primary | Suggested peer reviewer |
|---|---|---|
| Physical wiring / pin / sensing | A | D |
| PZEM/IBT-2 actuation path | A | D |
| Dataset/split/label | B | A or C |
| Feature/model/evaluation | B | D |
| MQTT/schema/twin/storage | C | A |
| Command lifecycle / replay | C | D |
| Policy / Controller A/B | D | A |
| Security/ACL | D | C |
| A/B methodology | B | A + D |
| Final evidence trace | shared | ≥2 members |

---

## 3.4 PR evidence template

```text
Issue:
Parent docs:
What changed:
Invariant / claim affected:
Hardware config affected?:
Test IDs:
Evidence path:
Reviewer focus:
Known limitation:
Out of scope:
```

---

# 4. Definition of Ready

An issue is `Ready` only when:

```text
[ ] parent doc section is known
[ ] owner is known
[ ] dependency is available or a valid fixture/simulator exists
[ ] expected output is explicit
[ ] test/evidence is named
[ ] hardware impact is understood
[ ] no member is forced to invent missing semantics
```

If not:

> design/research issue first, implementation issue later.

---

# 5. Definition of Done

The team uses one shared quality definition.

The official Scrum Guide describes Definition of Done as the formal state at which an increment meets required quality measures and creates shared transparency.

ColdGuard adapts that concept to an academic cyber-physical project.

---

## 5.1 Ordinary software issue

```text
[ ] implementation complete
[ ] local tests green
[ ] integration test when boundary matters
[ ] docs/contracts still agree
[ ] logs/errors safe and understandable
[ ] assigned owner verified the change and applicable safety/evidence gates
[ ] no hidden TODO in P0 path
```

---

## 5.2 Physical/hardware issue

Additionally:

```text
[ ] physical configuration recorded
[ ] measurement evidence exists
[ ] safety check passed
[ ] actual measured value recorded where required
[ ] repeatability checked where required
[ ] photo/diagram/version stored
```

---

## 5.3 ML/data issue

Additionally:

```text
[ ] run-level independence preserved
[ ] leakage audit
[ ] baseline comparison
[ ] versioned feature/model artifact
[ ] metric unit clearly stated
[ ] reproducible script/notebook
```

---

## 5.4 Control/security issue

Additionally:

```text
[ ] failure/negative case
[ ] stale/duplicate behavior considered
[ ] no direct AI→actuator bypass
[ ] authoritative final state asserted
[ ] evidence stored
```

---

## 5.5 Week complete

A week is GREEN only if:

```text
exit criteria
+
required evidence
+
required handoff
+
integration check
```

are complete.

“Code written” is not week completion.

---

# 6. Ownership matrix

| Subsystem / artifact | Primary | Reviewer | Backup understanding |
|---|---|---|---|
| exact BOM / hardware config | A | D | all |
| DS18B20/BME/door | A | C | D |
| PZEM/MAX3485 | A | C | D |
| IBT-2/TEC/V1 | A | D | C |
| physical characterization | A | B | D |
| run validity physical side | A | B | D |
| raw dataset QA | B | C | A |
| split/label/feature | B | D | C |
| XGBoost/model card | B | D | C |
| statistics/A-B analysis | B | A | D |
| MQTT/broker | C | D | A |
| DB/twin | C | A | B |
| command persistence/ACK audit | C | D | A |
| backup/deployment | C | A | D |
| Controller A | D | A | B |
| Controller B | D | B | A |
| SAFE_LOCAL | D + A | C | B |
| security ACL/authz | D | C | A |
| resilience campaign | D | C | A |
| final closed-loop trace | shared | all | all |

---

# 7. Evidence ownership matrix

| Evidence family | Owner |
|---|---|
| H0–H7 commissioning | A |
| sensor/calibration records | A |
| data QA/split manifest | B |
| model metrics/calibration/ablation | B |
| raw ingestion/twin/command logs | C |
| replay/duplicate/backend recovery | C |
| policy decisions/safety tests | D |
| SAFE_LOCAL/security tests | D |
| H8 closed-loop proof | A+C+D |
| final paired A/B | A+B+C+D |
| final statistics | B |
| final claim→artifact index | C + leader |
| final defense evidence selection | all |

---

# 8. Critical dependency graph

```text
Docs 00–03
   ↓
A: H0–H4 physical bring-up
   │
   ├────────────→ C: schema/broker/DB with simulator
   │                    ↓
   └→ A: H5–H7 plant ─→ C: real telemetry/twin
              │                  ↓
              │             D: Controller A
              │                  ↓
              ├────────────→ A+D: SAFE_LOCAL
              │
              └→ A: repeatable S1/S2
                         ↓
                      B: QA
                         ↓
                 B: grouped baseline
                         ↓
                    B: XGBoost
                         ↓
                  B: locked evidence
                         ↓
                B+D: predictive policy
                         ↓
                  C+D: shadow mode
                         ↓
                  A+D: Controller B
                         ↓
                A/B final campaign
                         ↓
                 B statistical proof
                         ↓
                 final evidence/demo
```

---

# 9. Blocking rules

## A blocks B

B may develop synthetic pipelines early.

B may **not** claim real predictive evidence until:

- Gate A physical;
- repeated valid runs;
- hardware config stable enough.

---

## A blocks D

D may write policy logic early.

D may **not** enable physical Controller B until:

- A has safe actuation envelope;
- H8 reactive closed-loop works.

---

## C blocks B

B can analyze exported CSV manually during early development.

Final online model/evidence requires:

- stable raw identity;
- run manifests;
- reproducible export.

---

## B blocks D

D can implement Controller A without B.

Controller B requires:

- frozen model version;
- feature/horizon semantics;
- warning threshold/persistence.

---

## D blocks final A/B

No final predictive intervention before:

- command safety;
- shadow mode;
- SAFE_LOCAL;
- response verification.

---

# 10. Cross-member handoff contracts

## 10.1 A → C

A supplies:

```text
device_id
boot_id
seq
physical schema fields
quality flags
hardware_config_id
firmware_version
calibration_id
applied actuator state
```

Handoff evidence:

- sample telemetry;
- schema fixture;
- real device capture.

---

## 10.2 A → B

A supplies:

```text
valid run IDs
physical scenario semantics
sensor positions
disturbance timestamps
calibration/config
invalid-run reasons
plant response characterization
```

B does not infer missing physical meaning from column names.

---

## 10.3 A → D

A supplies:

```text
safe operating envelope
healthy current/power range
OFF envelope
thermal response window
actuator delay
fault behavior
```

D does not invent safety thresholds before measurement.

---

## 10.4 C → B

C supplies:

```text
versioned export
run manifest
raw/normalized data
event timeline
dataset checksum
```

---

## 10.5 B → C

B supplies:

```text
feature_version
model_version
model artifact/hash
horizon
risk-score/probability semantics
inference input/output contract
```

---

## 10.6 B → D

B supplies:

```text
warning threshold
persistence recommendation
false-warning behavior
EWT distribution
AIW evidence inputs
model limitations
```

D decides action policy.

---

## 10.7 D → C

D supplies:

```text
policy_version
command reason codes
TTL/freshness
state machine
verification state
security rules
```

C persists/transports these semantics.

---

## 10.8 D → A

D supplies device-side requirements:

```text
allowed command range
local fallback thresholds
expiry handling
idempotency
SAFE_LOCAL mode transitions
```

A implements physical edge behavior.

---

# 11. Integration freeze rules

## 11.1 End W4 — physical/protocol draft freeze

Freeze enough for W5 parallel work:

- physical signal names;
- device identity;
- single cooling branch semantics;
- initial MQTT topics;
- command/ACK shape v0.

Breaking change later requires explicit review.

---

## 11.2 End W8 — baseline integration freeze

Freeze:

- telemetry schema v1;
- run identity;
- hardware config;
- Controller A interface;
- SAFE_LOCAL contract;
- DB/twin baseline.

---

## 11.3 End W12 — dataset/control baseline freeze

Freeze:

- experiment protocol;
- critical-state label family;
- baseline metrics;
- Controller A;
- diagnosis semantics.

---

## 11.4 End W16 — predictive freeze

Freeze before final closed-loop campaign:

- feature version;
- model;
- primary horizon;
- model operating threshold;
- calibration semantics;
- policy version;
- Controller B;
- A/B primary outcomes.

---

## 11.5 W17 onward

No architecture redesign unless:

- safety defect;
- correctness defect;
- irreproducible experiment;
- severe implementation bug.

Optional improvement waits until after core campaign.

---

# 12. Weekly team cadence

## Week start — 30–45 min

Review:

```text
previous exit
gate status
current blockers
invalid evidence
Ready issues
review assignments
critical path
```

No slide deck.

---

## Midweek integration — 30–60 min

Run at least one actual cross-boundary path.

Examples:

```text
real ESP telemetry → DB
command → ACK
model → policy shadow
```

---

## End-of-week review — 45–75 min

Leader checks:

```text
objective
artifact
quantitative evidence
integration
handoff
actual hours
risk
GREEN/YELLOW/RED
```

---

## Async update

Compact:

```text
Closed:
In progress:
Blocked:
Evidence:
Need review:
```

---

# 13. Leader weekly audit checklist

For each member:

```text
[ ] required artifact exists
[ ] evidence is quantitative where applicable
[ ] version/config is recorded
[ ] acceptance criterion actually passed
[ ] handoff consumer can use the output
[ ] blocker has owner
[ ] no silent scope/hardware change
[ ] next-week dependency is Ready
```

For the team:

```text
[ ] critical path remains viable
[ ] no doc authority conflict
[ ] no invalid evidence hidden
[ ] optional work has not displaced P0
```

---

# 14. Health classification

## GREEN

- week exit complete;
- gate stable;
- no critical dependency blocked.

## YELLOW

- one important item late;
- workaround/fixture exists;
- no safety/correctness ambiguity.

## RED

- physical safety uncertainty;
- repeatability failure;
- schema/correctness disagreement;
- leakage detected;
- critical path >1 week late;
- required integration cannot run.

When RED:

```text
optional P1/P2 work = 0
```

until root issue understood.

---

# 15. Blocker escalation

## >2 focused hours

Write exact issue:

```text
expected
observed
reproduction
evidence
what was tried
which doc contract applies
```

Ask reviewer.

---

## >1 working day

Parent week becomes YELLOW.

Lead decides:

- pair;
- reassign;
- use fixture;
- scope cut.

---

## >1 week on critical path

Parent phase is RED.

Immediately:

- freeze optional work;
- protect final-campaign buffer;
- revise downstream week issue packs.

---

# 16. WEEK 01 — Shared freeze, BOM audit and execution setup
**Team planned effort: ~42 h**  
A: **11 h** · B: **10 h** · C: **11 h** · D: **10 h**

## Objective

All four members operate from the same Docs 00–03 and the exact current purchased hardware configuration.

---

## Team tasks

### TEAM-W01-01 — Read/freeze Docs 00–03

Each member writes a short summary:

```text
own authority
top 5 invariants
top 5 dependencies
top 3 risks
evidence responsibilities
```

### TEAM-W01-02 — Hardware inventory audit

A leads.

Verify all 24 purchased items physically against Docs 00–01.

No electrical power required.

### TEAM-W01-03 — Repo and tracker skeleton

Create:

```text
docs/
firmware/
backend/
ml/
frontend/
infra/
experiments/
tests/
evidence/
```

Set project fields/status.

### TEAM-W01-04 — Oral architecture walkthrough

All answer:

1. Why one TEC?
2. What does PZEM prove?
3. Why ACK is not physical success?
4. Who owns `reported` state?
5. Why rows are not independent samples?
6. What happens if broker disappears?

---

## Member A

- physical BOM audit;
- board/module visual identification;
- hardware risk ledger;
- proposed GPIO review;
- sensor labels.

Deliver:

```text
hardware-audit-w01.md
photos
risk register
```

---

## Member B

- freeze central RQs and ML claim boundaries;
- create data dictionary draft from Docs 01–02;
- identify leakage risks;
- define dataset artifact convention.

---

## Member C

- backend architecture decision draft;
- broker/database/container plan;
- telemetry/command schema fixtures v0;
- environment bootstrap plan.

---

## Member D

- safety hierarchy review;
- threat/control boundary;
- command safety checklist;
- failure-mode ledger.

---

## Exit

```text
[ ] Docs 00–03 accepted as implementation baseline
[ ] exact BOM physically reconciled
[ ] no legacy INA226/2-TEC/20-L assumptions remain
[ ] ownership agreed
[ ] tracker active
[ ] no authority disagreement
```

---

## Leader review

Focus:

- Does every member understand the new hardware?
- Did anyone copy an old two-channel schema?
- Are missing seller/module details correctly marked commissioning-derived?

---

# 17. WEEK 02 — Mechanical/sensor foundation + digital skeleton
**Team planned effort: ~44 h**  
A: **12 h** · B: **10 h** · C: **11 h** · D: **11 h**

## Objective

Create safe non-TEC physical foundation and reproducible digital infrastructure.

---

## A

Execute:

```text
H0 mechanical
H1 sensor subsystem
```

- mount V1/TEC mechanically without powered TEC test;
- freeze T1/T2/T3 positions;
- discover DS18B20 ROM IDs;
- BME read;
- MC-38 polarity;
- sensor consistency check.

Evidence:

```text
H0/H1 package
ROM map
placement photo
```

---

## B

- dataset schema validator;
- synthetic run generator;
- grouped split prototype;
- label mechanics with synthetic trajectory;
- experiment manifest parser.

No real model result yet.

---

## C

- Mosquitto + PostgreSQL/Timescale Compose;
- backend skeleton;
- raw table migration;
- MQTT simulator;
- TLS-ready configuration structure.

Test:

```text
clean compose up
synthetic telemetry → raw DB
```

---

## D

- threat model v0;
- policy state-machine skeleton;
- SAFE_LOCAL contract review with A;
- command validation rules draft.

---

## Team integration

Synthetic device uses same schema intended for A's real firmware.

---

## Exit

```text
[ ] H0/H1 safe
[ ] sensor identities stable
[ ] broker/db/backend boots from clean environment
[ ] synthetic telemetry persisted
[ ] control/safety boundary documented
```

---

# 18. WEEK 03 — PZEM/RS-485 + immutable ingestion + experiment design
**Team planned effort: ~47 h**  
A: **14 h** · B: **10 h** · C: **12 h** · D: **11 h**

## Objective

Establish electrical observation and experiment/data correctness before high-power TEC work.

---

## A

Execute:

```text
H2 logic power
H3 PZEM / MAX3485
H4 IBT-2 logic partial
```

Tasks:

- XL4015 5 V verify;
- MAX3485 3.3 V;
- PZEM Modbus;
- 50 A profile;
- OFF envelope;
- 8N1/8N2 actual revision check;
- IBT-2 default-off logic without unsafe high-load assumptions.

---

## B

Freeze development methodology draft:

```text
independent run
split-by-run
candidate critical criterion
candidate horizon search
primary predictive metrics
paired A/B principle
```

Create statistical analysis plan before final data.

---

## C

Implement:

```text
telemetry_raw
normalized telemetry v0
(device_id, boot_id, seq) dedup
validation errors
run metadata skeleton
```

Test duplicate telemetry.

---

## D

Implement/test policy state-machine unit skeleton:

```text
NORMAL
WATCH
PREEMPTIVE
CRITICAL
FAULT
SAFE_LOCAL
```

No predictive actuator output yet.

---

## Exit

```text
[ ] PZEM talks reliably
[ ] 50 A range verified
[ ] raw ingestion idempotent
[ ] split policy documented
[ ] policy state machine has explicit safety precedence
```

---

# 19. WEEK 04 — TEC low-power commissioning + Twin v0 + analysis freeze
**Team planned effort: ~48 h**  
A: **14 h** · B: **12 h** · C: **10 h** · D: **12 h**

## Objective

Prove one safe real cooling path and freeze the first integrated contracts.

---

## A

Execute:

```text
H4 complete
H5 power branch
H6 conservative TEC test
```

Verify:

- branch fuse;
- high-current wiring;
- fan;
- cooling polarity;
- current/power;
- no abnormal terminal/module behavior.

Do not jump to seller “15 A” assumptions.

---

## B

Freeze v0:

- predictive metric definitions;
- EWT semantics;
- AIW distinction;
- primary/secondary metric list;
- invalid-run principle.

---

## C

Build Digital Twin v0:

```text
reported
desired
derived
```

with simulated + first real telemetry.

No desired→reported overwrite.

---

## D

Finalize command v0:

```text
command_id
TTL
device target
action
reason
```

and local rejection logic contract.

---

## Team integration

Real A telemetry:

```text
ESP32
→ MQTT
→ raw
→ normalized
→ reported twin
```

with TEC otherwise under local/manual safe control.

---

## Gate G1 — Physical/Protocol Preliminary

Required:

```text
sensor identity
PZEM valid
IBT-2 default-off
safe first TEC response
real telemetry path
twin separation
```

---

# 20. WEEK 05 — Coherent 1 Hz real telemetry
**Team planned effort: ~45 h**  
A: **11 h** · B: **10 h** · C: **13 h** · D: **11 h**

## Objective

Turn hardware readings into a stable report-grade telemetry stream.

---

## A

Firmware architecture:

```text
coherent snapshot
T1/T2/T3
BME
door
PZEM
quality
boot_id
seq
hardware config
```

Target:

```text
~1 Hz
```

Measure timing jitter.

---

## B

Real telemetry QA:

- ranges;
- missing;
- duplicate;
- sample interval;
- sensor disagreement;
- run-manifest consistency.

No serious modeling yet.

---

## C

Real-device schema freeze v1.

Implement:

- immutable raw;
- normalized single cooling branch;
- Timescale candidate;
- current reported twin.

---

## D

Connect physical-quality flags to policy input.

Ensure invalid state cannot enter predictive action path.

---

## Exit

```text
[ ] real 1 Hz path stable
[ ] no legacy two-branch fields
[ ] raw and normalized records reconcilable
[ ] quality flags visible
[ ] policy consumes explicit quality
```

---

# 21. WEEK 06 — Command/ACK and device-side safety
**Team planned effort: ~45 h**  
A: **11 h** · B: **10 h** · C: **13 h** · D: **11 h**

## Objective

Create the remote command lifecycle while keeping physical actuation bounded.

---

## A

Firmware:

- subscribe command;
- schema validation;
- TTL;
- duplicate command ID;
- applied state;
- ACK;
- safe OFF;
- allowed range.

---

## B

Prepare command/response event alignment tooling for later AIW analysis.

---

## C

Implement:

- command DB;
- publish path;
- ACK persistence;
- realtime/API v1;
- lifecycle status.

---

## D

Negative tests:

```text
expired
duplicate
wrong device
out of range
invalid state
```

No bypass path.

---

## Integration

Use low-risk command mode first.

Then one legal physical action after A/D approve.

---

## Exit

```text
[ ] command non-retained
[ ] ACK stored
[ ] duplicate idempotent
[ ] expired rejected
[ ] desired ≠ reported
[ ] one legal action trace works
```

---

# 22. WEEK 07 — Chamber geometry/repeatability + Controller A
**Team planned effort: ~46 h**  
A: **12 h** · B: **10 h** · C: **12 h** · D: **12 h**

## Objective

Freeze the experimental plant geometry and establish the deterministic baseline controller.

---

## A

- final sensor fixture;
- chamber sealing;
- repeated passive/cooling response;
- healthy gradient range;
- initial/reset-state candidate.

---

## B

Physical EDA only:

- distributions;
- slopes;
- gradient;
- repeatability;
- no model tuning.

---

## C

Implement:

- experiment table;
- run manifests;
- time-series query;
- export v0.

---

## D

Implement Controller A:

```text
threshold
hysteresis
optional persistence/dwell
```

using A's characterization.

---

## Exit

```text
[ ] geometry frozen
[ ] repeatability measured
[ ] experiment records available
[ ] Controller A works on real plant
```

---

# 23. WEEK 08 — Gate A/B + Platform baseline + SAFE_LOCAL
**Team planned effort: ~48 h**  
A: **12 h** · B: **12 h** · C: **12 h** · D: **12 h**

## Objective

Close the first major project gate.

---

## A

Gate A final:

- characterization package;
- selected safe operating envelope;
- fuse rationale;
- response-time preliminary;
- no abnormal hot-side/IBT-2 behavior.

---

## B

Gate B preliminary:

- valid-run checks;
- run grouping;
- data completeness;
- no schema ambiguity;
- dataset readiness report.

---

## C

Platform soak:

- 1 Hz extended run;
- broker reconnect;
- DB persistence;
- twin current state;
- backup test preliminary.

---

## D

SAFE_LOCAL:

- disconnect broker/backend;
- local reactive protection continues;
- reconnect path first integration.

---

## Gate G2 — Physical + Data + Reactive Baseline

Must be GREEN before serious AI dataset campaign.

If RED:

```text
W09 starts with repair
not XGBoost
```

---

# 24. WEEK 09 — Experiment protocol freeze + S1 baseline
**Team planned effort: ~45 h**  
A: **10 h** · B: **12 h** · C: **11 h** · D: **12 h**

## Objective

Start evidence-grade scenario collection.

---

## A

Execute S1 baseline runs.

Freeze:

- initial-state rule;
- reset rule;
- run operator checklist.

---

## B

Implement:

- simple threshold analytical baseline;
- hysteresis baseline evaluation;
- event-level metric code.

---

## C

Dataset export + checksum/manifests.

Ensure:

```text
run IDs
versions
quality
events
```

join correctly.

---

## D

Derive healthy cooling-health thresholds/ranges from A's characterization.

No arbitrary current threshold.

---

## Exit

```text
[ ] S1 protocol reproducible
[ ] deterministic baselines calculated
[ ] exports reproducible
[ ] healthy response state defined
```

---

# 25. WEEK 10 — S2 door pilot + feature engineering
**Team planned effort: ~49 h**  
A: **12 h** · B: **14 h** · C: **11 h** · D: **12 h**

## Objective

Create the primary disturbance trajectory and feature pipeline.

---

## A

S2 pilot:

- controlled door duration;
- repeated disturbances;
- fixture/operator protocol;
- estimate pair matching tolerance.

---

## B

Feature engineering v1:

```text
Tmean/Tmax/Tmin
gradient
slope
rolling mean/std
door time/duration
cooling state
V/I/P context
thermal exposure so far
```

Past-only audit.

---

## C

Event timeline:

- door;
- policy;
- command;
- ACK;
- physical response.

---

## D

Define safe S4 actuation-response fault method with A.

No destructive fault.

---

## Exit

```text
[ ] S2 repeatable enough for ML/A-B
[ ] feature code causal
[ ] event timeline reconstructable
[ ] fault protocol safe
```

---

# 26. WEEK 11 — XGBoost v1 + replay/fault verification
**Team planned effort: ~53 h**  
A: **12 h** · B: **15 h** · C: **12 h** · D: **12 h**

## Objective

Produce the first real predictive benchmark while proving failure semantics.

---

## A

Run:

- additional S1/S2 data;
- S4 safe actuation-response fault;
- electrical/thermal evidence.

Conditional S3 only if safe method exists.

---

## B

Train/evaluate:

```text
XGBoost v1
grouped CV / grouped development split
baseline comparison
leakage audit
```

Do not open locked test.

---

## C

Implement/test:

- duplicate telemetry;
- out-of-order;
- offline replay;
- stale current twin guard.

---

## D

Diagnosis integration:

- healthy;
- electrical response missing;
- unknown/degraded.

Avoid component root-cause overclaim.

---

## Exit

```text
[ ] first grouped XGBoost benchmark
[ ] duplicate/replay semantics pass
[ ] safe fault evidence exists
[ ] diagnosis states grounded in physical evidence
```

---

# 27. WEEK 12 — Month-3 dataset/control gate
**Team planned effort: ~46 h**  
A: **10 h** · B: **12 h** · C: **12 h** · D: **12 h**

## Objective

Freeze stable baseline before predictive-policy work.

---

## A

- calibration/consistency recheck;
- physical drift check;
- dataset-readiness signoff.

---

## B

Benchmark report:

- baseline vs XGBoost;
- grouped metrics;
- event counts;
- false warnings;
- initial EWT;
- limitations.

---

## C

- backup/restore test;
- raw export reproducibility;
- platform release candidate baseline.

---

## D

Controller A benchmark + Gate D preliminary:

- policy;
- command validation;
- SAFE_LOCAL;
- physical verify.

---

## Gate G3 — Dataset + Reactive Control

Required:

```text
[ ] physical plant stable enough
[ ] grouped dataset valid
[ ] XGBoost has interpretable benchmark
[ ] Controller A stable
[ ] command verification works
[ ] platform backup/export works
```

---

# 28. WEEK 13 — Horizon engineering + observability + predictive semantics
**Team planned effort: ~42 h**  
A: **8 h** · B: **12 h** · C: **10 h** · D: **12 h**

## Objective

Convert measured 6 L dynamics into a physically meaningful prediction/control horizon.

---

## A

Provide:

- command→electrical delay distribution;
- command→thermal delay;
- door→critical timing;
- passive/cooling time constants.

---

## B

Evaluate candidate horizons:

```text
30 s
60 s
120 s
300 s
```

or measured alternatives.

Select primary horizon using:

- event prevalence;
- EWT;
- AIW;
- false warnings.

---

## C

Observability v1:

- command IDs;
- prediction IDs;
- run correlation;
- latency metrics;
- structured logs.

---

## D

Predictive policy semantics:

- WATCH;
- PREEMPTIVE;
- transition conditions;
- no physical enable yet.

---

## Exit

```text
[ ] horizon grounded in plant physics
[ ] end-to-end latency measurable
[ ] predictive state machine specified
```

---

# 29. WEEK 14 — Calibration + A1/A2 ablation + AIW
**Team planned effort: ~48 h**  
A: **10 h** · B: **14 h** · C: **12 h** · D: **12 h**

## Objective

Prove which sensing context contributes and whether warning is actionable.

---

## A

Support data quality for:

```text
1 sensor vs 3 sensors
door-context ablation
```

No physical sensor removal required; logical ablation preferred.

---

## B

Run:

```text
A1 one T vs three T
A2 thermal vs thermal+door
probability calibration if justified
```

Compute EWT distributions.

---

## C

Twin derived state + provenance:

- feature/model version;
- risk;
- freshness.

---

## D

Compute/validate AIW with A/B timing data.

Freeze candidate safety margin before final test.

---

## Exit

```text
[ ] A1/A2 evidence
[ ] probability wording decided
[ ] AIW semantics quantitative
```

---

# 30. WEEK 15 — A3 electrical ablation + inference/security integration
**Team planned effort: ~48 h**  
A: **12 h** · B: **12 h** · C: **12 h** · D: **12 h**

## Objective

Integrate model artifact and demonstrate the value/limits of electrical observability.

---

## A

Provide stable PZEM/response data for A3.

If PWM energy is intended later, run characterization now.

---

## B

Run:

```text
A3 thermal/context vs +electrical
model inspection/stability
model freeze candidate
```

Go/No-Go on any deep model:

default:

```text
NO
```

unless clear evidence demands it.

---

## C

Integrate frozen-candidate inference:

- model artifact hash;
- feature version;
- prediction table;
- API/twin risk.

---

## D

Identity/TLS/ACL/backend authorization enforcement with C.

Predictive action still shadow-only.

---

## Exit

```text
[ ] inference online
[ ] provenance complete
[ ] A3 quantified
[ ] security baseline enforced
```

---

# 31. WEEK 16 — Locked predictive test + outage/resync gate
**Team planned effort: ~48 h**  
A: **12 h** · B: **12 h** · C: **12 h** · D: **12 h**

## Objective

Open the predictive holdout once and close resilience readiness before physical Controller B.

---

## A

Final plant response-time / drift recheck.

Confirm A/B physical pairing tolerances.

---

## B

Freeze and open locked predictive test:

- model;
- feature version;
- primary horizon;
- warning threshold;
- persistence;
- calibration.

Produce final offline early-warning result.

No retuning on test.

---

## C

Run:

- broker/backend outage;
- reconnect;
- state resync;
- stale replay rejection;
- buffer behavior if implemented.

---

## D

Run:

- AI unavailable;
- network unavailable;
- SAFE_LOCAL entry/exit;
- stale command negative test.

Freeze Controller B policy candidate.

---

## Gate G4 — Predictive/Resilience Readiness

Required before Controller B physical enablement:

```text
locked predictive evidence
positive or honestly interpretable AIW
shadow-capable inference
security baseline
SAFE_LOCAL
reconnect
command physical verify
```

A positive model result alone is insufficient.

---

# 32. WEEK 17 — Closed-loop shadow mode
**Team planned effort: ~52 h**  
A: **12 h** · B: **12 h** · C: **14 h** · D: **14 h**

## Objective

Run the full predictive decision path without allowing predictive actuation.

---

## A

Provide live plant/S2 runs.

Controller A remains physical authority.

---

## B

Package online inference and compare:

```text
online prediction
vs offline reference
```

---

## C

Trace:

```text
telemetry
→ feature
→ prediction
→ policy hypothetical
→ event/audit
```

---

## D

Run predictive policy shadow:

- state transitions;
- reason codes;
- hypothetical command;
- safety-block reasons.

---

## Exit

```text
[ ] online/offline predictions reconcile
[ ] no predictive command reaches device
[ ] complete trace exists
[ ] policy explainable
```

---

# 33. WEEK 18 — Controller B enablement
**Team planned effort: ~56 h**  
A: **14 h** · B: **14 h** · C: **14 h** · D: **14 h**

## Objective

Enable predictive physical intervention under the frozen safety envelope.

---

## Preconditions

Gate G4 GREEN.

---

## A

- supervise physical plant;
- verify current/power;
- verify thermal response;
- no hardware change.

---

## B

Monitor model/risk behavior.

Do not tune model after each physical run.

---

## C

Capture full closed-loop trace.

Ensure command outcome and verification terminal state.

---

## D

Enable Controller B for controlled dry runs.

Validate:

```text
prediction
→ policy
→ command
→ ACK
→ electrical verify
→ thermal verify
```

---

## Gate G5 preliminary

At least several clean controlled predictive runs before final paired campaign.

---

# 34. WEEK 19 — Final paired A/B campaign wave 1
**Team planned effort: ~56 h**  
A: **14 h** · B: **14 h** · C: **14 h** · D: **14 h**

## Objective

Collect first half of the frozen final S2 paired campaign.

---

## Team rules

- frozen hardware;
- frozen model/policy;
- randomized/balanced A/B order;
- frozen disturbance;
- frozen initial/reset criterion;
- all run attempts logged.

---

## A

Physical operator + plant evidence.

---

## B

Validity review + pair ledger.

Do not analyze final headline significance after every pair.

---

## C

Data capture integrity, backup.

---

## D

Controller integrity, command/verification review.

---

## Exit

Target:

```text
~50% final valid pair target
```

without changing policy.

---

# 35. WEEK 20 — Final paired A/B campaign wave 2
**Team planned effort: ~52 h**  
A: **13 h** · B: **13 h** · C: **13 h** · D: **13 h**

## Objective

Complete the pre-frozen paired target and close final physical evidence.

---

## A

Complete remaining valid pairs.

Rerun only according to predeclared invalid-pair rule.

---

## B

After target is complete:

- unlock final A/B analysis;
- compute pair outcomes;
- no model/policy retuning.

---

## C

Freeze final campaign export/checksum/backup.

---

## D

Review policy/audit anomalies and classify according to frozen rules.

---

## Gate G5 — Closed-Loop Evidence

Required:

```text
target valid pair count complete
all invalid runs logged
no silent hardware/policy change
raw evidence backed up
physical verification trace available
```

---

# 36. WEEK 21 — Resilience/security final campaign
**Team planned effort: ~40 h**  
A: **10 h** · B: **10 h** · C: **10 h** · D: **10 h**

## Objective

Close non-A/B evidence after the core physical campaign is safe.

---

## A

Support:

- sensor degraded scenario;
- safe actuation fault;
- hardware soak.

---

## B

Analyze diagnosis/robustness evidence.

No new core-model tuning.

---

## C

Run:

- duplicate;
- out-of-order;
- broker/backend outage;
- backup/restore;
- data integrity.

---

## D

Run:

- stale/duplicate/out-of-range command;
- unauthorized publish;
- TLS/auth;
- SAFE_LOCAL/reconnect.

---

## Optional opening

Only if core evidence is complete:

```text
PWM/energy-aware experiment
```

Otherwise skip.

---

# 37. WEEK 22 — Statistics, uncertainty and targeted evidence repair
**Team planned effort: ~40 h**  
A: **10 h** · B: **10 h** · C: **10 h** · D: **10 h**

## Objective

Turn raw campaign evidence into final reproducible scientific results.

---

## A

Targeted rerun only for:

- invalid pair under predeclared rule;
- missing required evidence;
- known instrument/logging failure.

No cherry-picking.

---

## B

Final:

- paired differences;
- 95% CI;
- bootstrap;
- effect size;
- sensitivity/robustness;
- predictive/A-B distinction;
- limitations.

---

## C

Evidence integrity audit:

- checksums;
- manifest;
- run count;
- version consistency.

---

## D

Final safety/security case:

- pass/fail matrix;
- residual risks;
- negative-test results.

---

## Exit

```text
headline tables/figures reproducible
all claims have uncertainty/limitations
```

---

# 38. WEEK 23 — Demo hardening + evidence package
**Team planned effort: ~42 h**  
A: **12 h** · B: **10 h** · C: **10 h** · D: **10 h**

## Objective

Stop feature development.

Make the project easy to reproduce and defend.

---

## Team

### Feature freeze

No new:

- sensor;
- model family;
- protocol;
- control mode;
- infrastructure technology.

### Clean environment

Another member follows setup from scratch.

### Evidence index

Create claim→test→artifact map.

### Demo rehearsals

At least:

```text
3 full rehearsals
```

---

## A

Physical setup hardening + spare/recovery checklist.

---

## B

Model card + result narrative + figure validation.

---

## C

Operational runbook, local demo deployment, evidence export.

---

## D

Safety/resilience demo rehearsal + attack/recovery scene.

---

# 39. WEEK 24 — Final acceptance, release and handover
**Team planned effort: ~32 h**  
A: **8 h** · B: **8 h** · C: **8 h** · D: **8 h**

## Objective

No new implementation.

Release, reproduce, defend.

---

## Team acceptance

```text
[ ] Docs 00–05 consistent
[ ] exact BOM/current hardware config recorded
[ ] clean backend deploy
[ ] firmware release build
[ ] model artifact/hash
[ ] final data backup
[ ] final analysis reproducible
[ ] all required gates green
[ ] demo rehearsed
[ ] limitations explicit
```

---

## Member A handover

- hardware config;
- pin map;
- calibration/characterization;
- physical evidence;
- operating/safety notes.

---

## Member B handover

- dataset card;
- split manifest;
- model card/artifact;
- final metrics;
- statistics scripts.

---

## Member C handover

- Compose/config;
- DB migrations;
- broker config;
- backup;
- API/twin/audit documentation.

---

## Member D handover

- policy config;
- safety case;
- security/resilience matrix;
- Controller A/B explanation.

---

# 40. Weekly effort map

| Week | A | B | C | D | Team | Risk |
|---:|---:|---:|---:|---:|---:|---|
| W01 | 11 | 10 | 11 | 10 | 42 | medium |
| W02 | 12 | 10 | 11 | 11 | 44 | high |
| W03 | 14 | 10 | 12 | 11 | 47 | **high** |
| W04 | 14 | 12 | 10 | 12 | 48 | **very high** |
| W05 | 11 | 10 | 13 | 11 | 45 | high |
| W06 | 11 | 10 | 13 | 11 | 45 | high |
| W07 | 12 | 10 | 12 | 12 | 46 | high |
| W08 | 12 | 12 | 12 | 12 | 48 | **very high** |
| W09 | 10 | 12 | 11 | 12 | 45 | medium |
| W10 | 12 | 14 | 11 | 12 | 49 | high |
| W11 | 12 | 15 | 12 | 12 | 51 | **very high** |
| W12 | 10 | 12 | 12 | 12 | 46 | high |
| W13 | 8 | 12 | 10 | 12 | 42 | medium |
| W14 | 10 | 14 | 12 | 12 | 48 | high |
| W15 | 12 | 12 | 12 | 12 | 48 | high |
| W16 | 12 | 12 | 12 | 12 | 48 | **very high** |
| W17 | 12 | 12 | 14 | 14 | 52 | high |
| W18 | 14 | 14 | 14 | 14 | 56 | **very high** |
| W19 | 14 | 14 | 14 | 14 | 56 | **very high** |
| W20 | 13 | 13 | 13 | 13 | 52 | **very high** |
| W21 | 10 | 10 | 10 | 10 | 40 | medium |
| W22 | 10 | 10 | 10 | 10 | 40 | high |
| W23 | 12 | 10 | 10 | 10 | 42 | high |
| W24 | 8 | 8 | 8 | 8 | 32 | medium |
| **Total** | **276** | **278** | **279** | **279** | **1112** | — |

---

# 41. Capacity interpretation

The schedule is intentionally heavier in:

```text
W03–W08
W17–W20
```

because those are:

- physical integration;
- final closed-loop campaign.

If sustainable capacity is lower, cut scope before compressing correctness work.

---

# 42. Phase effort

Approximate team effort:

| Phase | Weeks | Team hours |
|---|---:|---:|
| P0 | W01–W04 | 181 |
| P1 | W05–W08 | 184 |
| P2 | W09–W12 | 191 |
| P3 | W13–W16 | 186 |
| P4 | W17–W20 | 216 |
| P5 | W21–W24 | 154 |
| **Total** | | **1112** |

Phase totals are the exact sums of the authoritative weekly effort table above.

---

# 43. Gate summary

## G0 — Documentation / ownership

End W1:

```text
Docs 00–03 understood
BOM reconciled
tracker/ownership
```

## G1 — Physical preliminary

End W4:

```text
H0–H6 major foundations
real telemetry
safe first TEC response
```

## G2 — Physical/Data baseline

End W8:

```text
Gate A
dataset readiness
Controller A
SAFE_LOCAL
platform soak
```

## G3 — Data/Reactive benchmark

End W12:

```text
XGBoost v1
baseline
diagnosis
backup/export
Controller A evidence
```

## G4 — Predictive/Resilience

End W16:

```text
locked prediction
AIW
security baseline
SAFE_LOCAL/reconnect
Controller B candidate
```

## G5 — Closed-loop evidence

End W20:

```text
final paired A/B campaign complete
```

## G6 — Final validation

End W24:

```text
statistics
resilience/security
reproducibility
demo/release
```

---

# 44. Gate failure rules

## G1 red

Do not collect AI dataset.

A/C/D repair physical path.

B works synthetic tooling/methodology only.

---

## G2 red

Do not train final model on unstable data.

No Controller B work.

---

## G3 red

Do not rush predictive control.

Fix:

- dataset;
- baseline;
- command verification;
- diagnosis.

---

## G4 red

Controller B remains shadow-only.

Final A/B shifts later or optional scope is eliminated.

---

## G5 incomplete

W21 optional work is cancelled.

Use W21–W22 to complete required pairs/evidence according to predeclared protocol.

---

# 45. Scope-cut ladder

## Keep at all costs

```text
exact frozen hardware
safe commissioning
T1/T2/T3 + BME + door
PZEM branch observation
raw immutable telemetry
run manifests
Controller A
SAFE_LOCAL
XGBoost grouped evaluation
command TTL/idempotency
electrical + thermal verify
locked prediction evidence
paired A/B
uncertainty/statistical reporting
```

---

## Cut first

```text
fancy dashboard
extra frontend UX
extra reports
PWM energy optimization
GRU/TCN/LSTM
Secure Boot / Flash Encryption deployment
second ESP32 role
advanced alerting
```

---

## Cut next

```text
S3 thermal degradation if unsafe/unrepeatable
extra horizon studies beyond primary + small sensitivity set
long soak beyond useful duration
advanced anomaly classifier
```

---

## Never cut to save schedule

```text
fuse/default-off safety
sensor identity
PZEM 50 A profile proof
invalid-run logging
run-level split
baseline
command freshness/idempotency
SAFE_LOCAL
physical verification
A/B validity rules
raw evidence backup
```

---

# 46. Optional-scope opening rule

No optional item begins because a member “has free time” while a P0 blocker exists elsewhere.

If one member is free:

priority is:

```text
review
integration
evidence automation
critical-path support
documentation
then optional work
```

---

# 47. Risk register

| Risk | Probability | Impact | Owner | Mitigation |
|---|---:|---:|---|---|
| V1 hot-side rejection insufficient | High | Critical | A | W4–W8 characterization before dataset |
| exact TEC differs from generic seller values | High | High | A | measure actual I/P/response |
| IBT-2 3.3 V/module variation | Medium | High | A/D | H4 logic proof, default OFF |
| PZEM revision/serial mismatch | Medium | Medium | A | H3 8N1/8N2 commissioning |
| PZEM PWM averaging unclear | Medium | High for energy | A/B | core full/steady action; optional PWM only after characterization |
| board GPIO routing conflict | Medium | High | A | actual board bring-up before pin freeze |
| sensor placement drift | Medium | High | A | fixture/photo/config |
| insufficient repeatability | Medium | Critical | A/B | W7–W10 pilot and pair tolerances |
| too few independent runs | Medium | High | B | pilot effect/variance planning |
| temporal leakage | High early | Critical | B | run split before windows |
| model adds score but no actionable time | Medium | High | B/D | AIW in W13–W16 |
| backend schema drift | Medium | High | C | W5 v1 freeze + versioning |
| duplicate/stale command | Medium | Critical | C/D | QoS-aware idempotency/TTL tests |
| SAFE_LOCAL recovery bug | Medium | High | C/D/A | W8/W16 outage tests |
| final A/B variance too high | Medium | High | A/B | pairing/randomization/pilot |
| scope creep | High | High | all | gates + cut ladder |
| documentation drift | Medium | Medium | all | parent hierarchy + PR review |
| member bottleneck | Medium | High | lead | backup reviewer + handoff |
| final evidence not reproducible | Medium | Critical academically | B/C | W22–W24 clean analysis/export |

---

# 48. Bus-factor rule

Every critical mechanism has a second person who can:

```text
explain
run
inspect
review
```

| Mechanism | Primary | Backup |
|---|---|---|
| physical wiring/safety | A | D |
| sensor mapping | A | C |
| PZEM/RS-485 | A | C |
| IBT-2/TEC behavior | A | D |
| grouped data split | B | C |
| XGBoost artifact | B | C |
| statistics | B | A |
| MQTT/broker | C | D |
| twin/storage | C | B |
| command lifecycle | C | D |
| Controller A/B | D | A |
| SAFE_LOCAL | D/A | C |
| ACL/security | D | C |
| final A/B procedure | A+B | C+D |
| final evidence index | C | B |

---

# 49. Review checklist by boundary

## Physical

```text
[ ] exact BOM?
[ ] fused/safe?
[ ] measured rather than assumed?
[ ] config version?
[ ] physical authority correct?
```

## Sensor/data

```text
[ ] identity stable?
[ ] timestamps/seq?
[ ] quality explicit?
[ ] no silent imputation?
```

## MQTT/backend

```text
[ ] QoS assumption correct?
[ ] duplicate?
[ ] stale/out-of-order?
[ ] raw preserved?
[ ] twin authority?
```

## ML

```text
[ ] grouped split?
[ ] past-only?
[ ] baseline?
[ ] threshold chosen on development?
[ ] test locked?
```

## Control

```text
[ ] safety precedence?
[ ] TTL?
[ ] idempotent?
[ ] AI advisory only?
[ ] physical verification?
```

## Experiment

```text
[ ] one independent unit defined?
[ ] invalidation rule?
[ ] controlled variable?
[ ] paired/randomized?
[ ] evidence path?
```

---

# 50. Cross-review rotation

To avoid silos:

```text
W1–W4:
A↔D
B↔C

W5–W8:
A↔C
B↔D

W9–W12:
A↔B
C↔D

W13–W16:
A↔D
B↔C

W17–W20:
suggested peer reviewer for critical PRs follows the affected boundary

W21–W24:
reviewer chosen by evidence domain
```

---

# 51. Leader audit view

The leader should be able to inspect one week and answer:

```text
What did A promise?
What artifact proves it?
What did B need from A?
Did B actually receive it?
Which gate moved?
What is blocked next?
Was any scope changed?
Which evidence path supports DONE?
```

The four `05X` documents will expand each row into member-specific issue packs.

`04` remains the cross-team chronology.

---

# 52. Milestone-to-child mapping

Each `05X` must preserve the same weekly objective.

Example:

```text
04 W10:
S2 pilot + feature engineering

05A W10:
physical door protocol / repetitions

05B W10:
causal features

05C W10:
event timeline

05D W10:
safe S4 fault protocol
```

A child guide may add detail.

It may not move a critical team gate independently.

---

# 53. Actual-hours review

Weekly:

```text
estimate
actual
reason for >25% variance
```

Purpose:

- forecast;
- rebalance;
- detect hidden complexity.

Not:

- performance ranking.

---

# 54. Evidence debt

Treat missing evidence like technical debt.

If implementation is merged but required proof missing:

```text
Status = Evidence
```

not `Done`.

At most one week of evidence debt on P0 critical path.

---

# 55. Documentation debt

A semantic change is incomplete until parent docs/schema are updated.

Avoid:

```text
code now, docs at final week
```

because 05A–05D and future implementation depend on current docs.

---

# 56. Hardware-change governance

If physical failure requires changing purchased configuration:

1. stop comparable experiment collection;
2. record failure evidence;
3. review replacement/addition;
4. update Doc 00/01;
5. create new `hardware_config_id`;
6. re-run affected commissioning;
7. decide dataset comparability.

No silent substitution.

---

# 57. Model-change governance after W16

After locked test:

- bug fix may require new version;
- previous test is no longer untouched for the new model.

Do not re-open test repeatedly.

If a new model is necessary:

- collect/hold new independent data;
- or clearly label post-hoc/exploratory.

---

# 58. Policy-change governance after W18

During final A/B:

no threshold/persistence/duty change unless:

- safety defect;
- implementation correctness defect.

If changed:

- stop campaign;
- version policy;
- review comparability.

---

# 59. Pair-campaign operations

Before each pair:

```text
hardware config check
initial criterion
controller order
disturbance timer
run manifest
storage health
```

After each run:

```text
raw capture
validity note
no ad hoc analysis-induced policy change
reset
```

---

# 60. Invalid run handling

Invalid attempts remain logged.

If one arm invalid:

- rerun according to Doc 03 pairing rule;
- do not hide the failed attempt.

Leader audits invalid-count rate.

A high invalid rate is itself a process warning.

---

# 61. Final report ownership

Suggested writing ownership:

## A

- physical architecture;
- BOM/current hardware;
- commissioning;
- thermal/electrical characterization.

## B

- methodology;
- dataset;
- model;
- statistics;
- A/B result.

## C

- IoT architecture;
- MQTT/twin/storage;
- traceability/recovery.

## D

- policy/control;
- security;
- resilience;
- safety case.

## Shared

- abstract;
- problem;
- contribution;
- limitations;
- conclusion;
- demo narrative.

One editor reconciles terminology.

---

# 62. Final demo ownership

## A

Physical setup + sensor/electrical explanation.

## C

Live telemetry/twin/event trace.

## B

Prediction/evidence/result.

## D

Policy/physical verification/SAFE_LOCAL/security.

All members must understand the full chain.

---

# 63. Demo failure contingency

If venue network fails:

- local broker/backend;
- no public cloud dependency;
- recorded evidence replay;
- live physical sensing if possible.

If physical hardware temporarily fails:

- do not fake live success;
- switch to evidence replay;
- explain observed failure honestly.

---

# 64. Definition of project completion

The project is complete when:

```text
exact purchased system is safe and versioned
+
physical data are repeatable enough
+
digital path preserves provenance
+
baseline and XGBoost are evaluated without leakage
+
predictive action is safety-bounded
+
physical response is independently verified
+
paired A/B evidence is analyzed honestly
+
resilience/security mechanisms are demonstrated
+
another reviewer can reproduce the core evidence
```

Not when:

```text
all optional features were coded
```

---

# 65. Reference sources for execution governance

**[R1] GitHub Docs — About Issues.**  
Current GitHub Issues support sub-issues and issue dependencies for hierarchical work and blocked-by relationships.  
https://docs.github.com/en/issues/tracking-your-work-with-issues/learning-about-issues/about-issues

**[R2] GitHub Docs — Best practices for Projects.**  
Recommends using sub-issues, dependencies, milestones/labels and project information to make work relationships visible.  
https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/best-practices-for-projects

**[R3] GitHub Docs — Understanding fields.**  
Projects support text/number/date/single-select/iteration fields and parent/sub-issue progress.  
https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields

**[R4] Scrum Guide — Official current version (November 2020).**  
Definition of Done is the formal description of the state at which an Increment meets the product's required quality measures and provides a shared understanding of completion.  
https://scrumguides.org/scrum-guide.html

---

# 66. Freeze checklist for `05A–05D` generation

Before writing child playbooks:

## Global

- [ ] 24 weeks preserved.
- [ ] 4 member role names preserved.
- [ ] phase boundaries preserved.
- [ ] weekly effort map preserved unless explicit rebalance.
- [ ] each child week maps to one `04` week.
- [ ] each child has artifact/pass/fail/handoff/leader review.

## Hardware

- [ ] P1 guide uses PZEM/MAX3485/IBT-2/1 TEC/6 L.
- [ ] no INA226.
- [ ] no IRLB3813 MOSFET P0.
- [ ] no second TEC.
- [ ] no 20 L chamber.
- [ ] PSU 12 V / 33 A.
- [ ] 50 A / 75 mV shunt.

## AI

- [ ] no fixed 5/15/30 min inherited horizons.
- [ ] candidate short horizons derive from 6 L characterization.
- [ ] run-level split before windows.
- [ ] locked holdout.
- [ ] offline EWT separated from closed-loop physical outcome.

## Backend

- [ ] single cooling branch schema.
- [ ] reported/desired/derived.
- [ ] QoS 1 duplicate/idempotency.
- [ ] command non-retained.
- [ ] raw retained.

## Control

- [ ] one physical cooling channel.
- [ ] Controller A/B same core actuation magnitude.
- [ ] AI never directly actuates.
- [ ] SAFE_LOCAL.
- [ ] physical verification.

---

# 67. North star

> **The purpose of the 24-week plan is not to keep four people busy. It is to make dependencies visible early enough that one weak physical or semantic assumption cannot silently invalidate six months of downstream work.**

> **A member finishes a week only when the next member can safely build on the artifact, the leader can audit the evidence, and the project has moved one measurable step closer to a defensible closed-loop result.**
